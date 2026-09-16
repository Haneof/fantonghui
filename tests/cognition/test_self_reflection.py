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
