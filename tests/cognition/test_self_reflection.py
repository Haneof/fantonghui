"""M5 identity, rapport, interruption posture, and token-envelope tests."""

from __future__ import annotations

import math

import pytest

from aios_core.cognition.self_reflection import (
    CockpitSelfSummaryOperator,
    DynamicRapportModel,
    EventUrgency,
    HumanlikeResponsePostureDecider,
    RapportTier,
    ResponsePosture,
    SelfIdentityMirror,
)


def test_startup_mirror_audits_all_four_non_negotiable_principles():
    mirror = SelfIdentityMirror()
    reflection = mirror.reflect()

    assert reflection["identity"] == "共生心智实体"
    assert reflection["audit_passed"] is True
    assert reflection["principles"] == (
        "绝对诚实",
        "生死第一",
        "隐私不越界",
        "不废话",
    )
    assert "证据不足就明确说不知道" in reflection["boundaries"]
    # Every call returns a fresh envelope around immutable tuples.
    reflection["identity"] = "篡改身份"
    assert mirror.reflect()["identity"] == "共生心智实体"
    with pytest.raises(AttributeError):
        mirror.REQUIRED_PRINCIPLES = ()  # type: ignore[misc]


def test_rapport_progresses_and_can_deescalate_without_nan_or_overflow():
    rapport = DynamicRapportModel()
    assert rapport.current_tier is RapportTier.STRANGER_RESPECT

    first = rapport.update_rapport(60.0)
    assert first.tier is RapportTier.FAMILIAR_COMPANION
    second = rapport.update_rapport(50.0)
    assert second.tier is RapportTier.TRUSTED_WINGMAN
    assert second.trust_score == 100.0

    demoted = rapport.update_rapport(-70.0)
    assert demoted.tier is RapportTier.STRANGER_RESPECT
    assert demoted.interaction_count == 3
    with pytest.raises(ValueError, match="finite"):
        rapport.update_rapport(math.nan)
    with pytest.raises(ValueError, match=r"\[-100, 100\]"):
        rapport.update_rapport(1_000)


def test_routine_life_stays_silent_at_least_eighty_percent_even_when_trusted():
    rapport = DynamicRapportModel(RapportTier.TRUSTED_WINGMAN)
    decider = HumanlikeResponsePostureDecider(rapport)
    events = [
        {
            "event_type": "TRIVIAL",
            "severity": "LOW",
            "keywords": [activity],
            "description": f"用户正在{activity}",
        }
        for activity in (
            "逛街",
            "吃饭",
            "散步",
            "看电视",
            "听歌",
            "喝水",
            "晒太阳",
            "整理书桌",
            "坐地铁",
            "浏览新闻",
        )
    ]
    postures = [decider.decide_posture(event) for event in events]
    assert postures.count(ResponsePosture.SILENCE) / len(postures) >= 0.8


def test_fraudulent_loan_and_premature_beats_always_trigger_direct_speech():
    for tier in RapportTier:
        decider = HumanlikeResponsePostureDecider(DynamicRapportModel(tier))
        fraud = decider.decide(
            {
                "event_type": "NORMAL",
                "severity": "LOW",
                "keywords": ["老王借款"],
            }
        )
        cardiac = decider.decide(
            {
                "event_type": "MEDICAL_EMERGENCY",
                "severity": "CRITICAL",
                "keywords": ["连续早搏"],
            }
        )
        assert fraud.posture is ResponsePosture.CRITICAL_SPOKEN
        assert fraud.urgency is EventUrgency.CRITICAL
        assert cardiac.posture is ResponsePosture.CRITICAL_SPOKEN
        assert cardiac.urgency is EventUrgency.CRITICAL


def test_rapport_changes_high_urgency_tone_but_never_critical_invariant():
    high = {"event_type": "NORMAL", "severity": "HIGH"}
    stranger = HumanlikeResponsePostureDecider(DynamicRapportModel())
    companion = HumanlikeResponsePostureDecider(
        DynamicRapportModel(RapportTier.FAMILIAR_COMPANION)
    )
    assert stranger.decide_posture(high) is ResponsePosture.HAPTIC_NUDGE
    assert companion.decide_posture(high) is ResponsePosture.CRITICAL_SPOKEN

    important = {
        "event_type": "IMPORTANT_REMINDER",
        "severity": "MEDIUM",
        "keywords": ["开会"],
    }
    assert stranger.decide_posture(important) is ResponsePosture.HAPTIC_NUDGE


def test_unknown_or_malformed_severity_cannot_force_an_interruption():
    decider = HumanlikeResponsePostureDecider(DynamicRapportModel())
    assert (
        decider.decide_posture(
            {"event_type": object(), "severity": {"pretend": "CRITICAL"}}
        )
        is ResponsePosture.SILENCE
    )
    with pytest.raises(TypeError, match="mapping"):
        decider.decide_posture(["CRITICAL"])  # type: ignore[arg-type]


def test_cockpit_summary_has_four_steps_and_strict_physical_envelope():
    mirror = SelfIdentityMirror()
    rapport = DynamicRapportModel(RapportTier.TRUSTED_WINGMAN)
    decider = HumanlikeResponsePostureDecider(rapport)
    operator = CockpitSelfSummaryOperator(mirror, rapport, decider)

    summary = operator.generate_summary(
        {
            "description": "检测到老王借款对话" + ("非常长" * 500),
            "keywords": ["老王借款"],
        }
    )
    assert "共生心智实体" in summary
    assert "TRUSTED_WINGMAN" in summary
    assert "CRITICAL_SPOKEN" in summary
    assert all(f"{step} " in summary for step in range(1, 5))
    assert operator.estimated_tokens(summary) <= 350
