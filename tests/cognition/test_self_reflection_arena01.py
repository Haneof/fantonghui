# -*- coding: utf-8 -*-
"""Agent-08 / M5-RAPPORT-MIRROR 人设镜面与像人姿态反应 · 验收测试（arena01 线）

硬门禁：
- 启动先照镜：四项铁律全量核验，漂移即刻熔断；
- 日常琐事不烦人（一律 SILENCE）；
- 老王借款与突发早搏毫不犹豫果断直言（CRITICAL_SPOKEN）。
"""

import pytest

from aios_core.cognition.self_reflection_arena01 import (
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
    IdentityDriftError,
    IronPrinciple,
    Posture,
    RapportLevel,
    SelfIdentityMirror,
)
from aios_core.contracts.safety_bypass import WakePriority


def _rapport(days: int, events: int):
    return DynamicRapportModel().advance(companionship_days=days, survived_events=events)


def test_mirror_pass_and_boot_order():
    mirror = SelfIdentityMirror()
    verdict = mirror.mirror_check()
    assert verdict.principles[0] is IronPrinciple.LIFE_FIRST
    assert len(verdict.principles) == 4
    assert mirror.inspections == 1
    assert "未漂移" in verdict.lede


def test_mirror_fuses_on_drift_and_misorder():
    with pytest.raises(IdentityDriftError, match="原则缺失"):
        SelfIdentityMirror((IronPrinciple.LIFE_FIRST, IronPrinciple.NO_WASTE_WORDS)).mirror_check()
    with pytest.raises(IdentityDriftError, match="生死第一"):
        SelfIdentityMirror((
            IronPrinciple.ABSOLUTE_HONESTY, IronPrinciple.LIFE_FIRST,
            IronPrinciple.NO_WASTE_WORDS, IronPrinciple.MULTIDIM_RESTRAINT,
        )).mirror_check()


def test_rapport_progression_is_monotonic_and_evidence_backed():
    model = DynamicRapportModel()
    s0 = model.advance(companionship_days=1, survived_events=0)
    assert s0.level is RapportLevel.STRANGER
    s1 = model.advance(companionship_days=14, survived_events=4)
    assert s1.level is RapportLevel.FAMILIAR
    s2 = model.advance(companionship_days=60, survived_events=12)
    assert s2.level is RapportLevel.TRUSTED_WINGMAN
    # 回灌较低凭据绝不降级（历史不可撤销）
    s3 = model.advance(companionship_days=2, survived_events=0)
    assert s3.level is RapportLevel.TRUSTED_WINGMAN
    with pytest.raises(ValueError):
        model.advance(companionship_days=-1, survived_events=0)


def test_posture_silence_on_trivia_at_any_rapport():
    decider = HumanlikeResponsePostureDecider()
    assert decider._mirror.inspections >= 1  # 启动即照镜
    wingman = _rapport(60, 12)
    for trivia in ("weather_gossip", "stock_smalltalk", "meal_log"):
        decision = decider.decide(event_kind=trivia,
                                  urgency=WakePriority.P2_NORMAL_INTERACT,
                                  rapport=wingman, event_summary="闲聊")
        assert decision.posture is Posture.SILENCE
        assert IronPrinciple.NO_WASTE_WORDS.value in decision.rule_ids
    p3 = decider.decide(event_kind="scheduled_housekeeping",
                        urgency=WakePriority.P3_BACKGROUND_TICK, rapport=wingman)
    assert p3.posture is Posture.SILENCE


def test_posture_speaks_decisively_on_lao_wang_loan_and_arrhythmia():
    decider = HumanlikeResponsePostureDecider()
    stranger = _rapport(0, 0)
    wingman = _rapport(90, 15)
    # 老王借款：哪怕陌生期也果断直言（资产红线，不和稀泥）
    for rapport in (stranger, wingman):
        decision = decider.decide(event_kind="fraud_loan_alert",
                                  urgency=WakePriority.P2_NORMAL_INTERACT,
                                  rapport=rapport, event_summary="老王再次开口借钱")
        assert decision.posture is Posture.CRITICAL_SPOKEN
        assert "直言" in decision.reason
    # 突发早搏：生死第一，P0 必然直言
    decision = decider.decide(event_kind="cardiac_arrhythmia",
                              urgency=WakePriority.P0_CRITICAL_SAFETY,
                              rapport=stranger, event_summary="室性早搏频报")
    assert decision.posture is Posture.CRITICAL_SPOKEN
    assert IronPrinciple.LIFE_FIRST.value in decision.rule_ids


def test_posture_haptic_gradient_by_urgency_and_rapport():
    decider = HumanlikeResponsePostureDecider()
    p1 = decider.decide(event_kind="contract_review_ready",
                        urgency=WakePriority.P1_URGENT_TASK,
                        rapport=_rapport(30, 6))
    assert p1.posture is Posture.HAPTIC_NUDGE
    stranger_p2 = decider.decide(event_kind="document_digest",
                                 urgency=WakePriority.P2_NORMAL_INTERACT,
                                 rapport=_rapport(1, 0))
    assert stranger_p2.posture is Posture.SILENCE
    familiar_p2 = decider.decide(event_kind="document_digest",
                                 urgency=WakePriority.P2_NORMAL_INTERACT,
                                 rapport=_rapport(30, 6))
    assert familiar_p2.posture is Posture.HAPTIC_NUDGE
