"""M5 dimension lifecycle triple-gate and overlay red-team tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aios_core.cognition.dimension_engine import (
    AnomalyEvent,
    CrossDimensionalAnomalyDetector,
    DimensionLifecycleStateMachine,
    DimensionOverlayOperator,
    DimensionStatus,
    Entity,
    HighOrderDimensionDistiller,
)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _seed_three_day_streak(
    machine: DimensionLifecycleStateMachine,
    *,
    now: datetime = NOW,
) -> None:
    events = (
        AnomalyEvent(
            now - timedelta(days=3),
            "heart_rate",
            "静息心率连续异常升高",
            event_id="anomaly_heart",
            evidence_object_id="obs_heart",
        ),
        AnomalyEvent(
            now - timedelta(days=2),
            "billing",
            "深夜咖啡账单异常增加",
            event_id="anomaly_bill",
            evidence_object_id="obs_bill",
        ),
        AnomalyEvent(
            now - timedelta(days=1),
            "chat",
            "聊天显示连续通宵与疲惫",
            event_id="anomaly_chat",
            evidence_object_id="obs_chat",
        ),
    )
    for event in events:
        machine.detector.add_event(event)


def test_candidate_rejected_before_three_consecutive_cross_domain_days():
    machine = DimensionLifecycleStateMachine()
    machine.detector.add_event(
        AnomalyEvent(NOW - timedelta(days=2), "heart_rate", "心率异常")
    )
    machine.detector.add_event(
        AnomalyEvent(NOW - timedelta(days=1), "billing", "账单异常")
    )
    assert machine.detector.detect_continuous_anomaly(NOW) is False
    with pytest.raises(ValueError, match="Threshold 1"):
        machine.propose_dimension("DIM_BURNOUT_RISK", NOW)

    # Three distinct but non-consecutive dates cannot game the gate.
    other = DimensionLifecycleStateMachine()
    for offset, domain in ((3, "heart_rate"), (1, "billing"), (0, "chat")):
        other.detector.add_event(
            AnomalyEvent(NOW - timedelta(days=offset), domain, f"异常 {offset}")
        )
    with pytest.raises(ValueError, match="Threshold 1"):
        other.propose_dimension("DIM_CREDIT_RISK", NOW)


def test_thirty_day_prediction_trial_and_daily_reflection_are_hard_gates():
    machine = DimensionLifecycleStateMachine()
    _seed_three_day_streak(machine)
    state = machine.propose_dimension("DIM_BURNOUT_RISK", NOW)
    assert state.status is DimensionStatus.CANDIDATE
    assert state.anomaly_dates == (
        (NOW - timedelta(days=3)).date(),
        (NOW - timedelta(days=2)).date(),
        (NOW - timedelta(days=1)).date(),
    )
    assert state.anomaly_domains == frozenset({"health", "finance", "social"})
    with pytest.raises(AttributeError):
        state.status = DimensionStatus.REGISTERED  # type: ignore[misc]
    with pytest.raises(TypeError):
        machine.dimensions["forged"] = state  # type: ignore[index]

    reflection_time = NOW + timedelta(days=15)
    machine.reflect_and_validate(
        state.name,
        reflection_time,
        successful_prediction=True,
        prediction_id="prediction_burnout_day15",
    )
    with pytest.raises(ValueError, match="Threshold 3"):
        machine.reflect_and_validate(
            state.name,
            reflection_time + timedelta(hours=1),
            successful_prediction=True,
            prediction_id="prediction_quota_attack",
        )

    with pytest.raises(
        ValueError,
        match="Threshold 2.*30-day",
    ):
        machine.attempt_register(
            state.name,
            NOW + timedelta(days=29, hours=23, minutes=59),
        )
    registered = machine.attempt_register(state.name, NOW + timedelta(days=30))
    assert registered is state
    assert state.status is DimensionStatus.REGISTERED


def test_elapsed_time_alone_cannot_replace_prediction_validation():
    machine = DimensionLifecycleStateMachine()
    _seed_three_day_streak(machine)
    machine.propose_dimension("DIM_CREDIT_RISK", NOW)
    with pytest.raises(ValueError, match="Prediction validation"):
        machine.attempt_register("DIM_CREDIT_RISK", NOW + timedelta(days=31))


def test_reflection_quota_is_global_not_one_per_candidate():
    machine = DimensionLifecycleStateMachine()
    _seed_three_day_streak(machine)
    machine.propose_dimension("DIM_BURNOUT_RISK", NOW)
    machine.propose_dimension("DIM_CREDIT_RISK", NOW)

    when = NOW + timedelta(days=5)
    machine.reflect_and_validate("DIM_BURNOUT_RISK", when, True)
    with pytest.raises(ValueError, match="Threshold 3"):
        machine.reflect_and_validate("DIM_CREDIT_RISK", when, True)
    assert machine.dimensions["DIM_CREDIT_RISK"].predictions_attempted == 0


def test_high_order_distiller_is_allowlisted_and_domain_specific():
    machine = DimensionLifecycleStateMachine()
    events = (
        (3, "heart_rate", "心率异常"),
        (2, "sleep", "连续熬夜"),
        (1, "chat", "向家人表达持续疲惫"),
    )
    for offset, domain, description in events:
        machine.detector.add_event(
            AnomalyEvent(NOW - timedelta(days=offset), domain, description)
        )
    distiller = HighOrderDimensionDistiller(machine)

    assert distiller.distill("DIM_RANDOM_STORY", NOW) is None
    burnout = distiller.distill("DIM_BURNOUT_RISK", NOW)
    assert burnout is not None
    assert burnout.status is DimensionStatus.CANDIDATE

    # Credit risk requires finance + social, not merely a generic streak.
    assert distiller.distill("DIM_CREDIT_RISK", NOW) is None


def test_registered_overlay_is_append_only_and_externally_read_only():
    machine = DimensionLifecycleStateMachine()
    _seed_three_day_streak(machine)
    state = machine.propose_dimension("DIM_CREDIT_RISK", NOW)
    machine.reflect_and_validate(state.name, NOW + timedelta(days=10), True)
    machine.attempt_register(state.name, NOW + timedelta(days=30))

    entity = Entity(id="ent_wang")
    operator = DimensionOverlayOperator()
    first = operator.overlay_dimension(
        entity, state, current_time=NOW + timedelta(days=30)
    )
    second = operator.overlay_dimension(
        entity, state, current_time=NOW + timedelta(days=31)
    )

    assert first == second
    assert entity.tags == frozenset({"DIM_CREDIT_RISK"})
    assert len(operator.overlays_for(entity)) == 1
    with pytest.raises(AttributeError):
        entity.tags.add("DIM_INVENTED")  # type: ignore[attr-defined]


def test_unregistered_overlay_is_rejected():
    machine = DimensionLifecycleStateMachine()
    _seed_three_day_streak(machine)
    state = machine.propose_dimension("DIM_CREDIT_RISK", NOW)
    with pytest.raises(ValueError, match="Cannot overlay unregistered dimension"):
        DimensionOverlayOperator().overlay_dimension(Entity("ent_wang"), state)


def test_detector_replay_is_idempotent_and_conflicts_are_rejected():
    detector = CrossDimensionalAnomalyDetector()
    event = AnomalyEvent(
        NOW,
        "heart_rate",
        "心率异常",
        event_id="stable_event",
    )
    assert detector.add_event(event) is True
    assert detector.add_event(event) is False
    with pytest.raises(ValueError, match="conflicting immutable content"):
        detector.add_event(
            AnomalyEvent(
                NOW,
                "heart_rate",
                "伪造的不同内容",
                event_id="stable_event",
            )
        )
