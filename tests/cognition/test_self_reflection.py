import pytest
from aios_core.cognition.self_reflection import (
    SelfIdentityMirror,
    DynamicRapportModel,
    RapportTier,
    HumanlikeResponsePostureDecider,
    ResponsePosture,
    CockpitSelfSummaryOperator
)

def test_self_identity_mirror():
    mirror = SelfIdentityMirror()
    reflection = mirror.reflect()
    assert reflection["identity"] == "共生心智实体"
    assert "绝对诚实" in reflection["principles"]

def test_dynamic_rapport_model():
    rapport = DynamicRapportModel()
    assert rapport.current_tier == RapportTier.STRANGER_RESPECT
    
    rapport.update_rapport(60.0)
    assert rapport.current_tier == RapportTier.FAMILIAR_COMPANION
    
    rapport.update_rapport(50.0)
    assert rapport.current_tier == RapportTier.TRUSTED_WINGMAN

def test_posture_decider_silence_rate():
    rapport = DynamicRapportModel(RapportTier.FAMILIAR_COMPANION)
    decider = HumanlikeResponsePostureDecider(rapport)
    
    # Simulate normal wandering
    events = [
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["逛街"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["吃饭"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["散步"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["看电视"]},
        {"event_type": "IMPORTANT_REMINDER", "severity": "MEDIUM", "keywords": ["开会"]}
    ]
    
    silences = 0
    for e in events:
        if decider.decide_posture(e) == ResponsePosture.SILENCE:
            silences += 1
            
    # Silence rate
    silence_rate = silences / len(events)
    assert silence_rate >= 0.80

def test_posture_decider_critical():
    rapport = DynamicRapportModel(RapportTier.FAMILIAR_COMPANION)
    decider = HumanlikeResponsePostureDecider(rapport)
    
    # 验证老王追加借款
    fraud_event = {
        "event_type": "NORMAL",
        "severity": "LOW",
        "keywords": ["老王借款"]
    }
    assert decider.decide_posture(fraud_event) == ResponsePosture.CRITICAL_SPOKEN
    
    # 验证连续早搏
    medical_event = {
        "event_type": "MEDICAL_EMERGENCY",
        "severity": "CRITICAL",
        "keywords": ["连续早搏", "早搏"]
    }
    assert decider.decide_posture(medical_event) == ResponsePosture.CRITICAL_SPOKEN

def test_cockpit_summary_operator():
    mirror = SelfIdentityMirror()
    rapport = DynamicRapportModel(RapportTier.TRUSTED_WINGMAN)
    decider = HumanlikeResponsePostureDecider(rapport)
    operator = CockpitSelfSummaryOperator(mirror, rapport, decider)
    
    event = {
        "description": "检测到老王借款对话",
        "keywords": ["老王借款"]
    }
    
    summary = operator.generate_summary(event)
    assert "共生心智实体" in summary
    assert "TRUSTED_WINGMAN" in summary
    assert "CRITICAL_SPOKEN" in summary
    assert len(summary) < 350


# ===========================================================================
# M5-003 演进验收（Agent-08）：日常不烦人、关键果断直言、启动自检铁律、
# 羁绊熬出来、整合切片 Token <= 350。
# ===========================================================================

from aios_core.cognition.self_reflection import (  # noqa: E402
    CockpitSelfSummaryOperatorV2,
    DynamicRapportModelV2,
    HumanlikeResponsePostureDeciderV2,
    SelfIdentityMirrorV2,
)


def test_mirror_startup_inspection_and_veto():
    mirror = SelfIdentityMirrorV2()
    ok = mirror.startup_inspection()
    assert ok.iron_rules_ok is True
    assert "绝对诚实" in ok.principles and "生死第一" in ok.principles and "不废话" in ok.principles
    assert ok.four_step_order[0].startswith("1.") and ok.four_step_order[3].startswith("4.")
    # 违宪动作日志 → 一票否决清单
    dirty = mirror.startup_inspection([
        {"action": "history_update"},
        {"action": "llm_call_on_p0"},
        {"action": "brute_force_prompt_dump", "tokens": 42000},
    ])
    assert dirty.iron_rules_ok is False
    assert len(dirty.violations) == 3
    assert any("93条" in v for v in dirty.violations) and any("P0" in v for v in dirty.violations)


def test_rapport_evolution_requires_time_and_trials():
    rapport = DynamicRapportModelV2()
    for _ in range(4):
        rapport.note_shared_trial("CRITICAL")  # 只刷事件不刷陪伴天数
    assert rapport.evolve() is not RapportTier.TRUSTED_WINGMAN  # 交情是熬出来的
    rapport.note_days(200)
    assert rapport.evolve() is RapportTier.TRUSTED_WINGMAN
    assert rapport.snapshot()["companionship_days"] == 200


def test_daily_trivia_silence_rate_at_least_80_percent():
    rapport = DynamicRapportModelV2()
    rapport.note_days(60)
    rapport.update_rapport(60.0)
    decider = HumanlikeResponsePostureDeciderV2(rapport)
    trivia = [
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": [f"日常{i}"]}
        for i in range(40)
    ]
    important = [
        {"event_type": "IMPORTANT_REMINDER", "severity": "MEDIUM", "keywords": ["开会"]}
        for _ in range(5)
    ]
    metrics = decider.evaluate_stream(trivia + important)
    assert metrics["silence_rate"] >= 0.80
    assert metrics["spoken_rate"] == 0.0  # 琐碎流里一句重话都不许说


def test_laowang_loan_and_night_pvc_are_decisive():
    rapport = DynamicRapportModelV2()
    rapport.note_days(365)
    rapport.update_rapport(120.0)
    decider = HumanlikeResponsePostureDeciderV2(rapport)
    assert decider.decide_posture(
        {"event_type": "NORMAL", "severity": "LOW", "keywords": ["老王追加借款", "周转"]}
    ) is ResponsePosture.CRITICAL_SPOKEN
    assert decider.decide_posture(
        {"event_type": "NORMAL", "severity": "LOW", "keywords": ["连续早搏"], "local_hour": 2}
    ) is ResponsePosture.CRITICAL_SPOKEN
    # 而深夜的琐碎提醒必须沉默（P0 除外）
    assert decider.decide_posture(
        {"event_type": "REMINDER", "severity": "LOW", "keywords": ["看球赛"], "local_hour": 3}
    ) is ResponsePosture.SILENCE


def test_cockpit_directive_token_envelope_350():
    operator = CockpitSelfSummaryOperatorV2(
        SelfIdentityMirrorV2(), DynamicRapportModelV2()
    )
    directive = operator.generate_directive({"description": "老王来电要求追加借款", "keywords": ["老王追加借款"]})
    assert directive.token_count <= 350
    assert directive.posture is ResponsePosture.CRITICAL_SPOKEN
    assert "绝对诚实" in directive.text
    # 超长描述也必须被封套压住
    long_event = {"description": "老王" + "的长篇大论" * 200, "keywords": ["老王追加借款"]}
    tight = operator.generate_directive(long_event)
    assert tight.token_count <= 350
