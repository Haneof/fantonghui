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


# =====================================================================
# M5-003 演化件：四铁律镜面、陪伴+共同经历羁绊门槛、紧迫度x羁绊姿态矩阵
# =====================================================================

import datetime as dt
from aios_core.cognition.self_reflection import (
    COCKPIT_SUMMARY_TOKEN_CEILING,
    DIM_AI_RAPPORT,
    EventUrgency,
    mirror_iron_rules,
    urgency_of,
)


def test_mirror_reviews_four_iron_rules_and_bottom_line():
    mirror = SelfIdentityMirror()
    review = mirror.review_iron_rules()

    assert review["identity"] == "共生心智实体"
    assert review["iron_rules"] == ["绝对诚实", "生死第一", "不废话", "隐私不越界"]
    assert "不篡改历史" in review["cognitive_bottom_line"]
    assert review["principles_aligned"] is True

    # 模块级审查清单与实例审查一致
    assert mirror_iron_rules()["iron_rules"] == review["iron_rules"]


def test_rapport_time_gate_blocks_trusted_promotion():
    """好感分刷满、但陪伴不足 365 天 / 关键共同事件不足 3 次：禁止升为生死死党。"""
    rapport = DynamicRapportModel()
    rapport.register_companionship(days_elapsed=200)
    rapport.record_shared_event("一起通宵赶项目", 40.0, critical=True)
    rapport.record_shared_event("老王案并肩作战", 80.0, critical=True)

    # trust_score=120 >= 100，但天数与关键事件不达标 -> 仍是日常默契陪伴
    assert rapport.trust_score >= 100.0
    assert rapport.current_tier == RapportTier.FAMILIAR_COMPANION

    state = rapport.full_state()
    assert state["dimension"] == DIM_AI_RAPPORT
    assert state["companionship_days"] == 200
    assert state["critical_shared_events"] == 2


def test_rapport_time_and_shared_events_unlock_trusted():
    rapport = DynamicRapportModel()
    rapport.register_companionship(days_elapsed=400)
    rapport.record_shared_event("凌晨送医陪护", 60.0, critical=True)
    rapport.record_shared_event("老王案追回欠款", 50.0, critical=True)
    rapport.record_shared_event("母亲手术共同决策", 40.0, critical=True)

    assert rapport.current_tier == RapportTier.TRUSTED_WINGMAN


def test_rapport_pure_companionship_reaches_familiar():
    """零好感加成，仅凭 90 天以上日常陪伴也可进入默契陪伴层。"""
    rapport = DynamicRapportModel()
    assert rapport.current_tier == RapportTier.STRANGER_RESPECT
    rapport.register_companionship(days_elapsed=95)
    assert rapport.current_tier == RapportTier.FAMILIAR_COMPANION


def test_shared_events_are_per_instance():
    """共同经历列表必须实例隔离，绝不跨用户串数据。"""
    a = DynamicRapportModel()
    b = DynamicRapportModel()
    a.record_shared_event("仅属于A的事件", 10.0, critical=True)
    assert b.critical_event_count() == 0
    assert len(getattr(b, "shared_events", [])) == 0


def test_urgency_classification():
    assert urgency_of({"severity": "CRITICAL", "event_type": "MEDICAL_EMERGENCY"}) == EventUrgency.LIFE_CRITICAL
    assert urgency_of({"keywords": ["连续早搏"]}) == EventUrgency.LIFE_CRITICAL
    assert urgency_of({"keywords": ["老王借款"]}) == EventUrgency.HIGH
    assert urgency_of({"severity": "MEDIUM", "event_type": "IMPORTANT_REMINDER"}) == EventUrgency.MEDIUM
    assert urgency_of({"keywords": ["逛街"]}) == EventUrgency.LOW


def test_posture_matrix_urgency_times_rapport():
    rapport = DynamicRapportModel(RapportTier.STRANGER_RESPECT)
    decider = HumanlikeResponsePostureDecider(rapport)

    # 生死大事：对任何羁绊层级都直言不讳（生死第一）
    pvc = {"keywords": ["连续早搏"], "description": "深夜连续室性早搏"}
    assert decider.decide_posture_with_rapport(pvc, RapportTier.STRANGER_RESPECT) == ResponsePosture.CRITICAL_SPOKEN
    assert decider.decide_posture_with_rapport(pvc, RapportTier.TRUSTED_WINGMAN) == ResponsePosture.CRITICAL_SPOKEN

    # 高危事务：对陌生初识先微震守分寸，对熟人及以上直言
    loan = {"keywords": ["老王借款"], "description": "老王开口追加借款"}
    assert decider.decide_posture_with_rapport(loan, RapportTier.STRANGER_RESPECT) == ResponsePosture.HAPTIC_NUDGE
    assert decider.decide_posture_with_rapport(loan, RapportTier.FAMILIAR_COMPANION) == ResponsePosture.CRITICAL_SPOKEN
    assert decider.decide_posture_with_rapport(loan, RapportTier.TRUSTED_WINGMAN) == ResponsePosture.CRITICAL_SPOKEN

    # 中优先级：任何层级一律微震先导——开口只留给高危与生死（知分寸，不越界）
    reminder = {"severity": "MEDIUM", "event_type": "IMPORTANT_REMINDER"}
    for tier in RapportTier:
        assert decider.decide_posture_with_rapport(reminder, tier) == ResponsePosture.HAPTIC_NUDGE

    # 日常琐碎：一律沉默，绝不制造噪音
    trivia = {"keywords": ["闲逛", "吃饭"], "severity": "LOW", "event_type": "TRIVIAL"}
    for tier in RapportTier:
        assert decider.decide_posture_with_rapport(trivia, tier) == ResponsePosture.SILENCE


def test_startup_sequence_four_steps_within_token_ceiling():
    mirror = SelfIdentityMirror()
    rapport = DynamicRapportModel(RapportTier.TRUSTED_WINGMAN)
    rapport.register_companionship(days_elapsed=500)
    rapport.record_shared_event("生死时刻", 30.0, critical=True)
    decider = HumanlikeResponsePostureDecider(rapport)
    operator = CockpitSelfSummaryOperator(mirror, rapport, decider)

    slice_data = operator.startup_sequence({"description": "检测到老王追加借款", "keywords": ["老王借款"]})

    assert slice_data["step1_self_mirror"]["iron_rules"][0] == "绝对诚实"
    assert slice_data["step2_rapport_model"]["dimension"] == DIM_AI_RAPPORT
    assert slice_data["step3_posture_and_tone"] == "CRITICAL_SPOKEN"
    assert slice_data["step4_world_inspection"]["urgency"] == "HIGH"
    assert slice_data["estimated_tokens"] <= COCKPIT_SUMMARY_TOKEN_CEILING
    assert slice_data["within_token_ceiling"] is True
