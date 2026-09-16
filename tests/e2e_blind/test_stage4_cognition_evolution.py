"""阶段四盲测：高阶认知演进 + 维度三重门槛 + 人生相变。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cognition.cognitive_dimension_gate import (
    CognitiveDerivativeGate,
    DerivativeForbiddenError,
)
from aios_core.contracts.refs import ObjectRef
from aios_core.curves.dimension_curve import DimensionCurveTracker
from aios_core.dimensions.evolution_guard import (
    EvolutionGuard,
    ImmaturePatternRejectedError,
    PhysicalDomain,
    QuotaExceededBlockError,
)
from aios_core.simulation.blind_bench_harness import BenchRunResult

UTC = timezone.utc


def test_derivative_only_on_high_order_cognition(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S4")
    assert stage.fact("hardware_dimension_rejected") is True
    assert stage.fact("derivative_gate_rejected") == 1
    assert stage.fact("derivative_gate_allowed") >= 100


def test_hardware_derivative_is_refused_by_gate() -> None:
    gate = CognitiveDerivativeGate()
    tracker = DimensionCurveTracker("user_1")
    moment = datetime(2026, 9, 1, tzinfo=UTC)
    with pytest.raises(DerivativeForbiddenError):
        gate.record_point(
            tracker,
            dimension_ref=ObjectRef(object_id="dim_imu_raw", revision=1),
            value=1.2,
            point_time=moment,
        )


def test_inflection_triggers_mechanical_circuit_break(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S4")
    assert stage.fact("inflection_triggered") is True
    assert stage.fact("circuit_break_llm_calls") == 0
    assert "freeze_new_commitments" in stage.fact("circuit_break_actions")


def test_gate_one_rejects_immature_pattern_without_burning_quota() -> None:
    guard = EvolutionGuard()
    day = datetime(2026, 9, 1, tzinfo=UTC)
    guard.observe_anomaly(PhysicalDomain.CARDIOVASCULAR, observed_at=day, metric="hrv", value=18.0)
    with pytest.raises(ImmaturePatternRejectedError):
        guard.submit_candidate(
            "dim_premature",
            name="偶发异常",
            domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
            now=day,
        )
    # 门限一机械拒绝连当天的自省配额都不消耗（不成熟就闭嘴）
    assert guard.quota.remaining(day) == 1


def test_reflection_quota_is_one_per_day() -> None:
    guard = EvolutionGuard()
    day = datetime(2026, 9, 1, tzinfo=UTC)
    for offset in range(4):
        moment = day + timedelta(days=offset)
        guard.observe_anomaly(
            PhysicalDomain.CARDIOVASCULAR, observed_at=moment, metric="hrv", value=17.0
        )
        guard.observe_anomaly(
            PhysicalDomain.SLEEP, observed_at=moment, metric="sleep_efficiency", value=0.6
        )
    last_day = day + timedelta(days=3)
    admission = guard.submit_candidate(
        "dim_once",
        name="当日唯一",
        domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
        now=last_day,
    )
    assert admission.quota_used_today == 1
    assert guard.quota.remaining(last_day) == 0
    with pytest.raises(QuotaExceededBlockError):
        guard.submit_candidate(
            "dim_twice",
            name="贪心第二条",
            domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
            now=last_day,
        )


def test_trial_review_rejects_weak_and_patchy(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S4")
    assert stage.fact("trial_promotion_outcome") == "promoted"
    assert stage.fact("trial_weak_prediction_outcome") == "expired"
    assert stage.fact("trial_weak_accuracy") < 0.7
    assert stage.fact("trial_patchy_outcome") == "expired"
    assert stage.fact("trial_patchy_continuous") is False


def test_life_chapter_phase_transition_seals_and_resets(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S4")
    assert stage.fact("life_chapter_detected") is True
    assert stage.fact("broken_dimensions") >= 2
    assert "结构性断裂" in stage.fact("sealed_chapter_reason")
    assert abs(stage.fact("baseline_shift_burnout")) > 0.1
