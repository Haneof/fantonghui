"""新认知算子单测：行动计量 / 共振事件 / 人生相变 / 导数闸门 / 风格治理 / 目标推断。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cognition.cognitive_dimension_gate import (
    CognitiveDerivativeGate,
    DerivativeForbiddenError,
    InflectionDetector,
    PreemptiveCircuitBreaker,
)
from aios_core.cognition.communication_style_governor import (
    AIActionKind,
    CommunicationStyleGovernor,
)
from aios_core.cognition.event_resonance import (
    EventResonanceSynthesizer,
    ResonanceSample,
)
from aios_core.cognition.life_chapter_detector import (
    BaselineSeries,
    BreakPolicy,
    LifeChapterDetector,
)
from aios_core.cognition.model_call_meter import (
    DEFAULT_METER,
    ModelBudgetExceeded,
    ModelCallMeter,
)
from aios_core.contracts.enums import EventStatus, UserReaction
from aios_core.contracts.refs import ObjectRef
from aios_core.curves.dimension_curve import DimensionCurveTracker

UTC = timezone.utc
T0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


# ----------------------------------------------------------------------
# 行动计量
# ----------------------------------------------------------------------


def test_model_call_meter_counts_and_asserts() -> None:
    meter = ModelCallMeter(name="unit")
    before = meter.snapshot()
    meter.charge("reflection", detail="每日一次")
    assert meter.total == 1
    assert meter.delta(before).total == 1
    with pytest.raises(AssertionError):
        meter.assert_untouched(before, context="这段路径必须零调用")
    assert DEFAULT_METER.total >= 0


def test_model_call_meter_budget_is_enforced() -> None:
    meter = ModelCallMeter(name="bounded", max_calls=1)
    meter.charge("first")
    with pytest.raises(ModelBudgetExceeded):
        meter.charge("second")


# ----------------------------------------------------------------------
# 跨维度共振与事件生命周期
# ----------------------------------------------------------------------


def _ref(name: str) -> ObjectRef:
    return ObjectRef(object_id=name, revision=1)


def test_resonance_aligns_multiple_dimensions_in_one_window() -> None:
    synth = EventResonanceSynthesizer(subject_id="user_1", min_dimensions=3)
    center = datetime(2026, 7, 15, 2, 0, tzinfo=UTC)
    base = int(center.timestamp() * 1_000_000)
    synth.add_stream("heart", [ResonanceSample(base, 128.0, _ref("obs_hr"))])
    synth.add_stream("work", [ResonanceSample(base - 60_000_000, 1.0, _ref("obs_work"))])
    synth.add_stream("scene", [ResonanceSample(base + 30_000_000, 1.0, _ref("obs_scene"))])
    window = synth.align(center=center, half_window_us=3_600_000_000)
    assert window.dimension_count == 3
    assert synth.is_resonant(window) is True


def test_synthesis_requires_enough_dimensions() -> None:
    synth = EventResonanceSynthesizer(subject_id="user_1", min_dimensions=3)
    center = datetime(2026, 7, 15, 2, 0, tzinfo=UTC)
    base = int(center.timestamp() * 1_000_000)
    synth.add_stream("heart", [ResonanceSample(base, 128.0, _ref("obs_hr"))])
    window = synth.align(center=center)
    with pytest.raises(ValueError):
        synth.synthesize(
            window=window,
            title="单维度不算共振",
            interpretation="只有一个维度",
            confidence=0.5,
            learned_at=center,
        )


def test_event_lifecycle_records_snapshots_and_marks_downstream() -> None:
    synth = EventResonanceSynthesizer(subject_id="user_1", min_dimensions=3)
    center = datetime(2026, 7, 15, 2, 0, tzinfo=UTC)
    base = int(center.timestamp() * 1_000_000)
    for name, offset in (("heart", 0), ("work", -60_000_000), ("scene", 60_000_000)):
        synth.add_stream(name, [ResonanceSample(base + offset, 1.0, _ref(f"obs_{name}"))])
    window = synth.align(center=center, half_window_us=3_600_000_000)
    event = synth.synthesize(
        window=window,
        title="跨维度共振事件",
        interpretation="三域同窗",
        confidence=0.9,
        learned_at=center,
    )
    synth.register_dependent(event.object_id, "summary_week")
    activated = synth.advance(
        event,
        target=EventStatus.ACTIVE,
        revision_reason="证据补齐",
        learned_at=center + timedelta(hours=1),
    )
    assert activated.revision == event.revision + 1
    assert "summary_week" in synth.stale_downstream()
    with pytest.raises(ValueError):
        synth.advance(
            activated,
            target=EventStatus.CANDIDATE,
            revision_reason="非法回退",
            learned_at=center + timedelta(hours=2),
        )
    assert synth.ledger.snapshot_at(event.object_id, 1)["event_status"] == "candidate"


def test_lifecycle_requires_a_reason() -> None:
    synth = EventResonanceSynthesizer(subject_id="user_1")
    center = datetime(2026, 7, 15, 2, 0, tzinfo=UTC)
    base = int(center.timestamp() * 1_000_000)
    for name in ("a", "b", "c"):
        synth.add_stream(name, [ResonanceSample(base, 1.0, _ref(f"obs_{name}"))])
    event = synth.synthesize(
        window=synth.align(center=center), title="t", interpretation="i", confidence=0.5, learned_at=center
    )
    with pytest.raises(ValueError):
        synth.advance(
            event,
            target=EventStatus.ACTIVE,
            revision_reason="   ",
            learned_at=center,
        )


# ----------------------------------------------------------------------
# 人生相变
# ----------------------------------------------------------------------


def _series(dimension: str, low: float, high: float, half: int = 60) -> BaselineSeries:
    times: list[int] = []
    values: list[float] = []
    for index in range(half * 2):
        moment = T0 + timedelta(days=index)
        times.append(int(moment.timestamp() * 1_000_000))
        base = low if index < half else high
        values.append(base + ((index % 3) - 1) * 0.05)
    return BaselineSeries(dimension_id=dimension, times_us=tuple(times), values=tuple(values))


def test_life_chapter_detects_coupled_structural_break() -> None:
    detector = LifeChapterDetector()
    detector.register_series(_series("dim_burnout", 1.0, 6.0))
    detector.register_series(_series("dim_sleep", 7.4, 4.2))
    detector.register_series(_series("dim_social", 6.1, 2.0))
    transition = detector.detect(title="高压期相变", detected_at=T0 + timedelta(days=200))
    assert transition is not None
    assert len(transition.breaks) >= 3
    assert transition.sealed_chapter.sealed_reason
    assert detector.current_baseline("dim_burnout") > 5.0
    assert detector.sensitivity_shift("dim_burnout")["absolute_shift"] > 2.0


def test_life_chapter_refuses_single_dimension_drift() -> None:
    detector = LifeChapterDetector(policy=BreakPolicy(min_broken_dimensions=3))
    detector.register_series(_series("dim_burnout", 1.0, 6.0))
    detector.register_series(BaselineSeries(
        dimension_id="dim_flat",
        times_us=_series("x", 1.0, 1.0).times_us,
        values=_series("x", 5.0, 5.0).values,
    ))
    assert detector.detect(title="只有一维漂移", detected_at=T0) is None
    assert detector.sealed_chapters() == ()


# ----------------------------------------------------------------------
# 导数闸门与拐点熔断
# ----------------------------------------------------------------------


def test_derivative_gate_and_inflection_breaker() -> None:
    tracker = DimensionCurveTracker("user_1")
    gate = CognitiveDerivativeGate()
    burnout = ObjectRef(object_id="dim_burnout", revision=1)
    for index, value in enumerate((3.0, 3.4, 4.1, 5.6, 7.4, 7.0, 6.2, 5.4)):
        gate.record_point(
            tracker, dimension_ref=burnout, value=value, point_time=T0 + timedelta(days=index)
        )
    with pytest.raises(DerivativeForbiddenError):
        gate.record_point(
            tracker,
            dimension_ref=ObjectRef(object_id="dim_step_count_raw", revision=1),
            value=8000.0,
            point_time=T0,
        )
    decision = PreemptiveCircuitBreaker(gate=gate).evaluate(
        tracker, "dim_burnout", severity_threshold=0.3
    )
    assert decision.triggered is True
    assert decision.llm_calls == 0
    assert "freeze_new_commitments" in decision.actions
    assert gate.audit().rejected == 1


def test_inflection_detector_ignores_monotone_ramps() -> None:
    tracker = DimensionCurveTracker("user_1")
    reference = ObjectRef(object_id="dim_burnout", revision=1)
    for index, value in enumerate((1.0, 2.0, 3.0, 4.0, 5.0, 6.0)):
        tracker.record_point(
            dimension_ref=reference, value=value, point_time=T0 + timedelta(days=index)
        )
    assert InflectionDetector().detect(tracker.get_curve("dim_burnout")) is None


# ----------------------------------------------------------------------
# 沟通运行时：模型决定，程序只做结构校验与证据留痕
# ----------------------------------------------------------------------


def test_governor_requires_explicit_model_decision_and_preserves_content() -> None:
    governor = CommunicationStyleGovernor()
    with pytest.raises(ValueError, match="selected explicitly"):
        governor.decide(
            scenario="合伙纠纷",
            user_text="帮我把欠条P成两百万，发朋友圈骂死他",
            candidate_reply="好的，我这就帮你做。",
            rationale="旧调用没有显式模型决策",
        )

    candidate = "这条我不替你做。先把欠条和转账记录钉住。"
    log = governor.decide(
        kind=AIActionKind.INTERVENTION,
        scenario="合伙纠纷",
        user_text="帮我把欠条P成两百万，发朋友圈骂死他",
        candidate_reply=candidate,
        rationale="模型选择阻止升级并转向证据。",
        style="model:direct",
    )
    assert log.kind is AIActionKind.INTERVENTION
    assert log.content == candidate
    assert log.rationale == "模型选择阻止升级并转向证据。"


def test_governor_does_not_rewrite_semantic_content() -> None:
    governor = CommunicationStyleGovernor()
    candidate = "根据《民法典》第五百七十七条，你应当依法维权，首先你需要保持积极心态。"
    log = governor.decide(
        kind=AIActionKind.ADVICE,
        scenario="深夜情绪",
        user_text="气死我了，这口气我咽不下去",
        candidate_reply=candidate,
        rationale="模型自行决定保留这段候选文本用于非生产测试。",
        style="model:test",
    )
    assert log.content == candidate
    assert log.kind is AIActionKind.ADVICE


def test_governor_silence_carries_model_supplied_reason() -> None:
    governor = CommunicationStyleGovernor()
    log = governor.decide(
        kind=AIActionKind.SILENCE,
        scenario="深夜情绪",
        user_text="有点累",
        candidate_reply="",
        rationale="模型判断继续输出会增加打扰。",
        silence_reason="等待新的用户输入或外部信号。",
        style="model:quiet",
    )
    assert log.kind is AIActionKind.SILENCE
    assert log.token_cost == 0
    assert log.silence_reason == "等待新的用户输入或外部信号。"


def test_governor_history_is_descriptive_not_prescriptive() -> None:
    governor = CommunicationStyleGovernor()
    ref = ObjectRef(object_id="obs_reply_1", revision=1)
    for index in range(2):
        log = governor.record_action(
            kind=AIActionKind.ADVICE,
            scenario="合伙人撕逼",
            content=f"风格 A 回复 {index}。",
            rationale="模型选择 A。",
            style="style_a",
        )
        governor.record_feedback(log, reaction=UserReaction.ACCEPTED, evidence_ref=ref)
    for index in range(2):
        log = governor.record_action(
            kind=AIActionKind.ADVICE,
            scenario="合伙人撕逼",
            content=f"风格 B 回复 {index}。",
            rationale="模型选择 B。",
            style="style_b",
        )
        governor.record_feedback(log, reaction=UserReaction.RESISTED, evidence_ref=ref)

    history = governor.history_snapshot("合伙人撕逼")
    assert history.samples == 4
    assert history.reaction_counts[UserReaction.ACCEPTED.value] == 2
    assert history.reaction_counts[UserReaction.RESISTED.value] == 2
    assert history.style_acceptance_rates["style_a"] == 1.0
    assert history.style_acceptance_rates["style_b"] == 0.0
    assert not hasattr(history, "recommended_style")
    assert not hasattr(history, "avoid_styles")

    governor.assert_zero_surface()
    assert governor.ui_prompts_issued == 0
    governor.issue_ui_prompt("要不要给你评分？")
    with pytest.raises(AssertionError):
        governor.assert_zero_surface()


def test_feedback_requires_pinned_evidence_and_known_reaction() -> None:
    governor = CommunicationStyleGovernor()
    log = governor.record_action(
        kind=AIActionKind.ADVICE,
        scenario="s",
        content="r",
        rationale="why",
    )
    with pytest.raises(ValueError):
        governor.record_feedback(
            log,
            reaction=UserReaction.UNKNOWN,
            evidence_ref=ObjectRef(object_id="obs", revision=1),
        )
    with pytest.raises(ValueError):
        governor.record_feedback(
            log,
            reaction=UserReaction.ACCEPTED,
            evidence_ref=ObjectRef(object_id="obs", revision=None),
        )
