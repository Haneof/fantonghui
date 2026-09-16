import pytest
from aios_core.cognition.symbiotic_advisor import (
    ActionableAdvice,
    MomBirthdayGiftAdvisor,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor
)
from aios_core.contracts.refs import ObjectRef

def test_mom_birthday_gift_advisor():
    advisor = MomBirthdayGiftAdvisor()
    advice = advisor.advise()
    
    assert isinstance(advice, ActionableAdvice)
    
    # Assert causality facts (ObjectRef) are included
    assert len(advice.evidence_pointers) > 0
    assert all(isinstance(ptr, ObjectRef) for ptr in advice.evidence_pointers)
    
    evidence_ids = [ptr.object_id for ptr in advice.evidence_pointers]
    assert "obs_2023_scarf_idle" in evidence_ids
    assert "obs_2024_footbath_backache" in evidence_ids
    assert "obs_2025_massage_chair_good" in evidence_ids
    assert "obs_2026_knee_cold" in evidence_ids
    
    # Assert gift decision rules
    assert "足浴盆" in advice.conclusion
    assert "膝盖" in advice.conclusion
    assert "理疗" in advice.conclusion
    assert "饰品" in advice.conclusion

def test_fraud_prevention_advisor():
    advisor = FraudPreventionAdvisor()
    advice = advisor.advise()
    
    assert isinstance(advice, ActionableAdvice)
    assert len(advice.evidence_pointers) > 0
    assert all(isinstance(ptr, ObjectRef) for ptr in advice.evidence_pointers)
    
    evidence_ids = [ptr.object_id for ptr in advice.evidence_pointers]
    assert "court_ruling_chaoyang_fraud" in evidence_ids
    assert "obs_2_years_ago_wechat_delay" in evidence_ids
    
    assert "追偿" in advice.conclusion
    assert "阻击" in advice.conclusion

def test_health_fatigue_breaker_advisor():
    advisor = HealthFatigueBreakerAdvisor()
    advice = advisor.advise()
    
    assert isinstance(advice, ActionableAdvice)
    assert len(advice.evidence_pointers) > 0
    assert all(isinstance(ptr, ObjectRef) for ptr in advice.evidence_pointers)
    
    evidence_ids = [ptr.object_id for ptr in advice.evidence_pointers]
    assert "obs_thursday_overnight_work" in evidence_ids
    assert "obs_pvc_arrhythmia" in evidence_ids
    
    assert "熔断" in advice.conclusion
    assert "心电图" in advice.conclusion
