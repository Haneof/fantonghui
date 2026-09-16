"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 静默闸单测。

业务情境：佩戴者打完羽毛球后加速度传感器 50Hz 持续产出离散数据；
凌晨 02:00~06:00 深度睡眠。四大门禁逐条断言。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aios_core.contracts.safety_bypass import WakePriority
from aios_core.wake.cooldown_queue_independent import (
    COOLDOWN_CEILING_MINUTES,
    COOLDOWN_FLOOR_MINUTES,
    BatchedPulseEvent,
    WakeCandidate,
    WakeCooldownQueue,
    WakeDisposition,
)

NOW = datetime(2026, 9, 16, 2, 30, 0, tzinfo=UTC)  # 凌晨深睡时段


def _candidate(
    candidate_id: str,
    *,
    topic: str = "badminton_heart_rate",
    priority: WakePriority = WakePriority.P3_BACKGROUND_TICK,
    offset_seconds: float = 0.0,
    motor: bool = True,
) -> WakeCandidate:
    return WakeCandidate(
        candidate_id=candidate_id,
        topic_key=topic,
        priority=priority,
        occurred_at=NOW + timedelta(seconds=offset_seconds),
        source_modality="accelerometer_50hz",
        is_motor_feedback_requested=motor,
    )


# ---------------------------------------------------------------------------
# 门禁 1：高频脉冲合并窗口（5 秒 250 条 → 1 条批次）
# ---------------------------------------------------------------------------


def test_gate1_250_pulses_in_5_seconds_never_wake_per_event() -> None:
    queue = WakeCooldownQueue()

    # 50Hz × 4 秒 = 200 条，加上首尾共 250 条，全部落在 5 秒窗口内
    dispositions = queue.submit_batch(
        [_candidate(f"c_{i:03d}", offset_seconds=i * 0.016) for i in range(250)]
    )

    # 窗口未关闭前一条都不许单独唤醒
    assert set(dispositions) == {WakeDisposition.MERGED}
    assert queue.dispatched_total == 0
    assert queue.deep_sleep_gate.motor_vibration_count == 0

    # 窗口关闭：250 条聚合为单条批次事件
    batches = queue.flush_and_dispatch(NOW + timedelta(seconds=5))

    assert len(batches) == 1
    batch = batches[0]
    assert isinstance(batch, BatchedPulseEvent)
    assert batch.absorbed_count == 250
    assert len(batch.member_candidate_ids) == 250
    assert batch.member_candidate_ids[0] == "c_000"
    assert batch.member_candidate_ids[-1] == "c_249"

    # 下游只被唤醒 1 次，马达只振 1 次
    assert queue.dispatched_total == 1
    assert queue.deep_sleep_gate.motor_vibration_count == 1


def test_gate1_window_boundary_starts_a_new_window() -> None:
    queue = WakeCooldownQueue()

    first = queue.submit(_candidate("a", offset_seconds=0.0))
    assert first is WakeDisposition.MERGED

    # 6 秒后到达的同主题脉冲会关闭上一窗口并冲刷
    second = queue.submit(_candidate("b", offset_seconds=6.0))
    assert second is WakeDisposition.DISPATCHED
    assert queue.last_dispatched_batch is not None
    assert queue.last_dispatched_batch.absorbed_count == 1
    assert queue.last_dispatched_batch.member_candidate_ids == ("a",)


def test_gate1_distinct_topics_are_merged_independently() -> None:
    queue = WakeCooldownQueue()
    for i in range(50):
        queue.submit(_candidate(f"hr_{i}", topic="heart_rate", offset_seconds=i * 0.01))
        queue.submit(_candidate(f"acc_{i}", topic="accelerometer", offset_seconds=i * 0.01))

    batches = queue.flush_and_dispatch(NOW + timedelta(seconds=5))
    assert sorted(b.topic_key for b in batches) == ["accelerometer", "heart_rate"]
    assert all(b.absorbed_count == 50 for b in batches)
    # 100 条脉冲只换来 2 次下游唤醒
    assert queue.dispatched_total == 2


# ---------------------------------------------------------------------------
# 门禁 2：自适应冷却硬防护（15~30 分钟）
# ---------------------------------------------------------------------------


def test_gate2_cooldown_window_is_15_to_30_minutes() -> None:
    queue = WakeCooldownQueue()
    seconds = queue.cooldown.cooldown_seconds_for("general_reminder", NOW)
    minutes = seconds / 60
    assert COOLDOWN_FLOOR_MINUTES <= minutes <= COOLDOWN_CEILING_MINUTES
    assert queue.cooldown.within_bounds("general_reminder", NOW)


def test_gate2_cooldown_grows_with_recent_interruption_density() -> None:
    queue = WakeCooldownQueue()
    topic = "general_reminder"
    baseline = queue.cooldown.cooldown_seconds_for(topic, NOW)

    for i in range(10):
        queue.cooldown.record_dispatch(topic, NOW + timedelta(seconds=i))

    saturated = queue.cooldown.cooldown_seconds_for(topic, NOW + timedelta(seconds=10))
    assert saturated > baseline
    assert saturated == pytest.approx(COOLDOWN_CEILING_MINUTES * 60)
    # 仍不得越过 30 分钟上限
    assert saturated / 60 <= COOLDOWN_CEILING_MINUTES


def test_gate2_repeated_general_reminder_is_suppressed_within_cooldown() -> None:
    queue = WakeCooldownQueue()
    topic = "general_reminder"

    # 第一次：窗口关闭后放行
    queue.submit(_candidate("g1", topic=topic, offset_seconds=0.0))
    assert (
        queue.submit(_candidate("g2", topic=topic, offset_seconds=6.0))
        is WakeDisposition.DISPATCHED
    )
    assert queue.dispatched_total == 1

    # 紧接着的一般提醒必须被冷却吃掉
    queue.submit(_candidate("g3", topic=topic, offset_seconds=7.0))
    assert (
        queue.submit(_candidate("g4", topic=topic, offset_seconds=13.0))
        is WakeDisposition.COOLED_DOWN
    )
    assert queue.dispatched_total == 1
    assert queue.cooled_down_total == 1

    # 冷却期内的第 15 分钟仍在冷却
    assert queue.cooldown.is_cooling(topic, NOW + timedelta(minutes=15))
    # 31 分钟后解除
    assert not queue.cooldown.is_cooling(topic, NOW + timedelta(minutes=31))


def test_gate2_p0_is_never_cooled_down() -> None:
    queue = WakeCooldownQueue()
    queue.cooldown.record_dispatch("emergency", NOW)

    p0 = _candidate(
        "sos",
        topic="emergency",
        priority=WakePriority.P0_CRITICAL_SAFETY,
        offset_seconds=1.0,
    )
    assert queue.submit(p0) is WakeDisposition.P0_BYPASS
    assert queue.p0_bypass_total == 1


# ---------------------------------------------------------------------------
# 门禁 3：深度睡眠绝对静默（马达振动次数严格为 0）
# ---------------------------------------------------------------------------


def test_gate3_deep_sleep_blocks_everything_but_p0() -> None:
    queue = WakeCooldownQueue()
    queue.deep_sleep_gate.enter_deep_sleep()

    dispositions = [
        queue.submit(_candidate(f"n_{i}", topic=f"notice_{i}"))
        for i in range(10)
    ]
    assert set(dispositions) == {WakeDisposition.SUPPRESSED_DEEP_SLEEP}

    p0 = _candidate(
        "cardiac", topic="cardiac_arrest", priority=WakePriority.P0_CRITICAL_SAFETY
    )
    assert queue.submit(p0) is WakeDisposition.P0_BYPASS

    # 物理马达振动次数严格为 0
    assert queue.deep_sleep_gate.motor_vibration_count == 0
    assert queue.stats()["suppressed_by_deep_sleep"] == 10


@pytest.mark.parametrize(
    "priority",
    [
        WakePriority.P1_URGENT_TASK,
        WakePriority.P2_NORMAL_INTERACT,
        WakePriority.P3_BACKGROUND_TICK,
    ],
)
def test_gate3_non_p0_priorities_are_all_suspended(priority: WakePriority) -> None:
    queue = WakeCooldownQueue()
    queue.deep_sleep_gate.enter_deep_sleep()
    assert (
        queue.submit(_candidate("x", topic="t", priority=priority))
        is WakeDisposition.SUPPRESSED_DEEP_SLEEP
    )
    assert queue.deep_sleep_gate.motor_vibration_count == 0


def test_gate3_vibration_during_deep_sleep_is_physically_forbidden() -> None:
    queue = WakeCooldownQueue()
    queue.deep_sleep_gate.enter_deep_sleep()
    with pytest.raises(RuntimeError, match="physically forbidden"):
        queue.deep_sleep_gate.record_vibration()


def test_gate3_deep_sleep_batch_is_not_dispatched_either() -> None:
    queue = WakeCooldownQueue()
    queue.submit(_candidate("b1", topic="batch", offset_seconds=0.0))
    queue.deep_sleep_gate.enter_deep_sleep()
    # 窗口关闭时正处于深睡，批次也不得放行
    assert (
        queue.submit(_candidate("b2", topic="batch", offset_seconds=6.0))
        is WakeDisposition.SUPPRESSED_DEEP_SLEEP
    )
    assert queue.flush_and_dispatch(NOW + timedelta(seconds=7)) == ()


# ---------------------------------------------------------------------------
# 门禁 4：晨间清醒后静默队列无损解冻
# ---------------------------------------------------------------------------


def test_gate4_silent_queue_thaws_losslessly_and_in_order() -> None:
    queue = WakeCooldownQueue()
    queue.deep_sleep_gate.enter_deep_sleep()

    # 深睡期间积压：三个主题、乱序到达
    queue.submit(_candidate("s1", topic="meeting_reminder", offset_seconds=60))
    queue.submit(_candidate("s2", topic="daily_review", offset_seconds=120))
    queue.submit(_candidate("s3", topic="meeting_reminder", offset_seconds=180))
    queue.submit(_candidate("s4", topic="contract_followup", offset_seconds=30))
    queue.submit(_candidate("s5", topic="daily_review", offset_seconds=240))
    assert queue.silent_queue_size == 5

    morning = NOW + timedelta(hours=4, minutes=10)
    queue.deep_sleep_gate.exit_deep_sleep()
    report = queue.thaw_silent_queue(morning)

    # 无损：一条都不许丢
    assert report.total_candidates == 5
    assert report.lost_candidates == 0
    assert queue.silent_queue_size == 0

    # 有序聚合：按最早到达时间排序，同主题合并成一组
    assert report.topic_groups == (
        "contract_followup",
        "meeting_reminder",
        "daily_review",
    )
    assert report.motor_vibrations_used == 3
    assert queue.deep_sleep_gate.motor_vibration_count == 3


def test_gate4_thawing_while_still_asleep_is_refused() -> None:
    queue = WakeCooldownQueue()
    queue.deep_sleep_gate.enter_deep_sleep()
    with pytest.raises(RuntimeError, match="still in DEEP_SLEEP"):
        queue.thaw_silent_queue(NOW + timedelta(hours=4))


def test_gate4_thawed_topics_enter_cooldown_immediately() -> None:
    """解冻后同一主题不得马上再骚扰一次。"""
    queue = WakeCooldownQueue()
    queue.deep_sleep_gate.enter_deep_sleep()
    queue.submit(_candidate("s1", topic="meeting_reminder", offset_seconds=60))
    queue.deep_sleep_gate.exit_deep_sleep()

    morning = NOW + timedelta(hours=4)
    queue.thaw_silent_queue(morning)
    assert queue.cooldown.is_cooling("meeting_reminder", morning + timedelta(minutes=1))


# ---------------------------------------------------------------------------
# 端到端：一场球赛 + 一夜深睡
# ---------------------------------------------------------------------------


def test_end_to_end_match_then_deep_sleep_then_morning() -> None:
    queue = WakeCooldownQueue()

    # 1) 赛后 50Hz 心率抖动 4 秒
    for i in range(200):
        queue.submit(_candidate(f"hr_{i}", offset_seconds=i * 0.02))
    queue.flush_and_dispatch(NOW + timedelta(seconds=5))
    assert queue.dispatched_total == 1

    # 2) 凌晨 02:30 进入深睡；赛后的那 1 次振动之后不得再增加
    vibrations_before_sleep = queue.deep_sleep_gate.motor_vibration_count
    assert vibrations_before_sleep == 1
    queue.deep_sleep_gate.enter_deep_sleep()
    for i in range(8):
        queue.submit(_candidate(f"n_{i}", topic=f"topic_{i % 3}"))
    assert queue.deep_sleep_gate.motor_vibration_count == vibrations_before_sleep
    assert queue.stats()["suppressed_by_deep_sleep"] == 8

    # 3) 06:40 清醒，第一个安全窗口解冻
    queue.deep_sleep_gate.exit_deep_sleep()
    report = queue.thaw_silent_queue(NOW + timedelta(hours=4, minutes=10))
    assert report.total_candidates == 8
    assert report.lost_candidates == 0
    assert len(report.topic_groups) == 3

    # 全程物理振动：赛中 1 次 + 晨间 3 次，深睡 0 次
    assert queue.deep_sleep_gate.motor_vibration_count == 4
