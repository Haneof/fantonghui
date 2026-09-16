from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from aios_core.wake.cooldown_queue import (
    EnqueueStatus,
    SleepState,
    WakeCategory,
    WakeCooldownQueue,
    WakePulse,
    WakeUrgency,
)

START = datetime(2026, 9, 16, 2, 15, tzinfo=UTC)


def _pulse(
    index: int,
    *,
    at: datetime,
    episode: str = "post-badminton-vitals",
    category: WakeCategory = WakeCategory.PHYSICAL_VITAL,
    urgency: WakeUrgency = WakeUrgency.P2_ROUTINE,
) -> WakePulse:
    return WakePulse(
        event_id=f"pulse-{episode}-{index:04d}",
        episode_key=episode,
        occurred_at=at,
        urgency=urgency,
        category=category,
        sensor_type="heart_rate" if index % 2 == 0 else "accelerometer",
        value=88.0 + (index % 70),
        hardware_action_code=(
            "CARDIAC_FALL_SOS" if urgency is WakeUrgency.P0_LIFE_SAFETY else None
        ),
    )


def test_250_sensor_pulses_in_five_seconds_emit_one_downstream_batch() -> None:
    motor = MagicMock()
    queue = WakeCooldownQueue(motor_vibrate=motor)

    for index in range(250):
        status = queue.enqueue(
            _pulse(index, at=START + timedelta(milliseconds=index * 19))
        )
        assert status is EnqueueStatus.MERGED
    assert motor.call_count == 0

    presentation = queue.advance(START + timedelta(seconds=5, milliseconds=1))

    assert presentation is not None
    assert len(presentation.batches) == 1
    batch = presentation.batches[0]
    assert batch.pulse_count == 250
    assert len(batch.event_ids) == 250
    assert len(set(batch.event_ids)) == 250
    assert batch.sensor_types == ("accelerometer", "heart_rate")
    assert presentation.total_unique_pulses == 250
    assert presentation.motor_vibration_count == 1
    assert queue.motor_vibration_count == 1
    motor.assert_called_once_with(presentation)


def test_adaptive_cooldown_holds_normal_wakes_for_15_to_30_minutes() -> None:
    motor = MagicMock()
    queue = WakeCooldownQueue(motor_vibrate=motor)
    queue.enqueue(_pulse(0, at=START, episode="initial-reminder"))
    first = queue.advance(START + timedelta(seconds=5))
    assert first is not None
    assert (
        timedelta(minutes=15)
        <= first.cooldown_until - first.presented_at
        <= timedelta(minutes=30)
    )
    assert first.cooldown_seconds == 15 * 60

    held_at = START + timedelta(minutes=1)
    queue.enqueue(_pulse(1, at=held_at, episode="held-task-reminder"))
    assert queue.advance(held_at + timedelta(seconds=5)) is None
    assert queue.pending_batch_count == 1
    assert motor.call_count == 1

    released = queue.advance(first.cooldown_until)
    assert released is not None
    assert released.batches[0].episode_key == "held-task-reminder"
    assert motor.call_count == 2


def test_deep_sleep_silences_all_normal_categories_but_p0_bypasses() -> None:
    motor = MagicMock()
    emergency = MagicMock()
    queue = WakeCooldownQueue(
        motor_vibrate=motor,
        emergency_dispatch=emergency,
    )
    assert queue.set_sleep_state(SleepState.DEEP_SLEEP, observed_at=START) is None

    categories = (
        WakeCategory.GENERAL_NOTIFICATION,
        WakeCategory.REFLECTION,
        WakeCategory.TASK_REMINDER,
    )
    for index, category in enumerate(categories):
        queue.enqueue(
            _pulse(
                index,
                at=START + timedelta(seconds=index),
                episode=f"sleep-{category.value}",
                category=category,
            )
        )
    assert queue.advance(START + timedelta(seconds=10)) is None
    assert queue.silent_batch_count == 3
    assert queue.motor_vibration_count == 0
    motor.assert_not_called()

    p0 = _pulse(
        99,
        at=START + timedelta(seconds=11),
        episode="acute-cardiac-fall",
        urgency=WakeUrgency.P0_LIFE_SAFETY,
    )
    assert queue.enqueue(p0) is EnqueueStatus.P0_DISPATCHED
    emergency.assert_called_once_with(p0)
    assert queue.emergency_dispatch_count == 1
    assert queue.motor_vibration_count == 0
    motor.assert_not_called()


def test_first_awake_safe_window_releases_silent_backlog_in_order_losslessly() -> None:
    motor = MagicMock()
    queue = WakeCooldownQueue(motor_vibrate=motor)
    queue.set_sleep_state(SleepState.DEEP_SLEEP, observed_at=START)
    source_ids: list[str] = []

    for episode_index, minute in enumerate((5, 25, 55)):
        for pulse_index in range(4):
            pulse = _pulse(
                episode_index * 10 + pulse_index,
                at=START + timedelta(minutes=minute, milliseconds=pulse_index * 100),
                episode=f"silent-episode-{episode_index}",
                category=(
                    WakeCategory.TASK_REMINDER
                    if episode_index == 0
                    else WakeCategory.GENERAL_NOTIFICATION
                ),
            )
            source_ids.append(pulse.event_id)
            queue.enqueue(pulse)
    morning = START + timedelta(hours=5)
    assert queue.advance(morning - timedelta(minutes=1)) is None
    assert queue.silent_batch_count == 3

    presentation = queue.set_sleep_state(SleepState.AWAKE, observed_at=morning)

    assert presentation is not None
    assert [batch.episode_key for batch in presentation.batches] == [
        "silent-episode-0",
        "silent-episode-1",
        "silent-episode-2",
    ]
    released_ids = [
        event_id for batch in presentation.batches for event_id in batch.event_ids
    ]
    assert released_ids == source_ids
    assert presentation.total_unique_pulses == 12
    assert queue.silent_batch_count == 0
    assert queue.pending_batch_count == 0
    motor.assert_called_once_with(presentation)


def test_duplicate_pulses_never_inflate_batch_or_repeat_p0_dispatch() -> None:
    emergency = MagicMock()
    queue = WakeCooldownQueue(emergency_dispatch=emergency)
    normal = _pulse(1, at=START, episode="dedupe-normal")

    assert queue.enqueue(normal) is EnqueueStatus.MERGED
    assert queue.enqueue(normal) is EnqueueStatus.DUPLICATE_IGNORED
    presentation = queue.advance(START + timedelta(seconds=5))
    assert presentation is not None
    assert presentation.total_unique_pulses == 1

    p0 = _pulse(
        2,
        at=START + timedelta(minutes=20),
        episode="dedupe-p0",
        urgency=WakeUrgency.P0_LIFE_SAFETY,
    )
    assert queue.enqueue(p0) is EnqueueStatus.P0_DISPATCHED
    assert queue.enqueue(p0) is EnqueueStatus.DUPLICATE_IGNORED
    emergency.assert_called_once_with(p0)


def test_rejected_out_of_order_pulse_does_not_poison_deduplication() -> None:
    queue = WakeCooldownQueue()
    queue.enqueue(_pulse(1, at=START + timedelta(seconds=2), episode="ordered"))
    out_of_order = _pulse(2, at=START + timedelta(seconds=1), episode="ordered")

    with pytest.raises(ValueError, match="increase within an episode"):
        queue.enqueue(out_of_order)

    corrected = out_of_order.model_copy(
        update={"occurred_at": START + timedelta(seconds=3)}
    )
    assert queue.enqueue(corrected) is EnqueueStatus.MERGED


def test_wake_contract_rejects_naive_time_and_non_p0_hardware_action() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _pulse(1, at=datetime(2026, 9, 16, 2, 0))  # noqa: DTZ001
    with pytest.raises(ValidationError, match="non-P0"):
        WakePulse(
            event_id="bad-hardware-action",
            episode_key="bad",
            occurred_at=START,
            urgency=WakeUrgency.P2_ROUTINE,
            category=WakeCategory.TASK_REMINDER,
            sensor_type="task",
            hardware_action_code="SHOULD_NOT_BYPASS",
        )
