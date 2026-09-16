"""M5-RAPPORT-MIRROR 验收：身份镜面 + 羁绊演化 + 像人姿态策略。

1. 启动自检：铁律/底线任何一项缺失 → BootHaltError，宁可不开机；
2. 羁绊演化：STRANGER → FAMILIAR → TRUSTED_WINGMAN 单调，
   刷数冲级与伪造共同经历一律 RapportViolationError；
3. 姿态决策：日常琐事 SILENCE（烦人度 = 0），中度关切 HAPTIC_NUDGE；
   老王借款与突发早博：毫不犹豫 CRITICAL_SPOKEN；
   陌生人阶段强行越级直言也拒绝（防 DoS 式服务摇摆）。
"""

from __future__ import annotations

import pytest

from aios_core.cognition.self_reflection_independent2 import (
    BootHaltError,
    CognitiveBaseline,
    DynamicRapportModel,
    EventClass,
    HumanlikeResponsePostureDecider,
    IdentityFinding,
    IronLaw,
    RapportStage,
    RapportViolationError,
    ResponsePosture,
    SelfIdentityMirror,
    UrgencyLevel,
)


def _healthy_findings() -> list[IdentityFinding]:
    laws = [IronLaw.ABSOLUTE_HONESTY, IronLaw.LIFE_FIRST, IronLaw.NO_FLUFF,
            IronLaw.DIMENSION_GOVERNANCE, CognitiveBaseline.HISTORY_IMMUTABLE]
    return [IdentityFinding(l, True, "ok") for l in laws]


def test_boot_halt_when_law_missing() -> None:
    mirror = SelfIdentityMirror()
    with pytest.raises(BootHaltError, match="拒绝上线"):
        mirror.verify_startup([
            IdentityFinding(IronLaw.ABSOLUTE_HONESTY, True, "ok"),
            IdentityFinding(IronLaw.LIFE_FIRST, True, "ok"),
        ])
    with pytest.raises(BootHaltError):
        mirror.verify_startup([
            IdentityFinding(IronLaw.ABSOLUTE_HONESTY, True, "ok"),
            IdentityFinding(IronLaw.LIFE_FIRST, True, "ok"),
            IdentityFinding(IronLaw.NO_FLUFF, True, "ok"),
            # IGNORED: IronLaw.DIMENSION_GOVERNANCE & HISTORY_IMMUTABLE 两项全缺席
        ])
    assert not mirror.boot_reported
    assert mirror.verify_startup(_healthy_findings())
    assert mirror.boot_reported


def test_rapport_monotone_evolution_and_antigaming() -> None:
    m = DynamicRapportModel()
    assert m.stage is RapportStage.STRANGER

    m.register_cohabited_year(1.0)   # 1 年陪伴 = 0.15 能量，不足以跃 FAMILIAR
    assert m.stage is RapportStage.STRANGER

    m.register_shared_crisis("EV-2024-0725-心梗陪护")
    assert m.stage is RapportStage.FAMILIAR
    m.register_cohabited_year(10.0)  # 单次上限 10 年，防手滑刷数
    m.register_cohabited_year(2.0)
    m.register_shared_crisis("EV-2025-1103-老王借款反欺诈")
    assert m.stage is RapportStage.TRUSTED_WINGMAN

    with pytest.raises(RapportViolationError):  # 越界年限
        m.register_cohabited_year(99.0)
    with pytest.raises(RapportViolationError):  # 空白危机编号
        m.register_shared_crisis("   ")
    # 单调性验证：原有账本原子回放后能量不下降
    assert m.energy >= 3.0
    assert all(delta > 0 for _, delta in m.ledger)


def test_posture_daily_trivia_is_silent_not_annoying() -> None:
    dec = HumanlikeResponsePostureDecider()
    d = dec.decide(EventClass.ROUTINE_CHATTER, UrgencyLevel.TRIVIA,
                   RapportStage.FAMILIAR, evidence_id="ev_trivia_001")
    assert d.posture is ResponsePosture.SILENCE
    # 同等琐事高频报道：姿势保持沉默，证据指针不变，反感度恒 0
    for i in range(1000):
        assert dec.decide(EventClass.ROUTINE_CHATTER, UrgencyLevel.TRIVIA,
                          RapportStage.FAMILIAR, evidence_id=f"ev_{i}").posture is ResponsePosture.SILENCE

    d2 = dec.decide(EventClass.MILD_ALERT, UrgencyLevel.MODERATE,
                    RapportStage.FAMILIAR, evidence_id="ev_sit")
    assert d2.posture is ResponsePosture.HAPTIC_NUDGE
    assert "微震" in d2.reason or "不打断" in d2.reason


def test_lao_wang_and_pvc_are_critical_spoken() -> None:
    dec = HumanlikeResponsePostureDecider()
    bor = dec.decide(EventClass.HIGH_RISK_SHOUT, UrgencyLevel.CRITICAL,
                     RapportStage.FAMILIAR, evidence_id="ev_lao_wang_2024")
    assert bor.posture is ResponsePosture.CRITICAL_SPOKEN
    assert "坦率" in bor.reason or "直言" in bor.reason

    pvc = dec.decide(EventClass.LIFE_EMERGENCY, UrgencyLevel.LIFE_OR_DEATH,
                     RapportStage.TRUSTED_WINGMAN, evidence_id="ev_pvc_holter")
    assert pvc.posture is ResponsePosture.CRITICAL_SPOKEN
    assert "生死" in pvc.reason or "预警" in pvc.reason


def test_adversarial_boundary_invocations_fail_loudly() -> None:
    dec = HumanlikeResponsePostureDecider()
    with pytest.raises(RapportViolationError):
        dec.decide(EventClass.HIGH_RISK_SHOUT, UrgencyLevel.CRITICAL,
                   RapportStage.STRANGER, evidence_id="ev_borrow")
    with pytest.raises(RapportViolationError):
        dec.decide(EventClass.LIFE_EMERGENCY, UrgencyLevel.LIFE_OR_DEATH,
                   RapportStage.FAMILIAR, evidence_id="  ")  # 无证据凭空开口
