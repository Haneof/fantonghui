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


# ===========================================================================
# M5-004 演进验收（Agent-09）：证据驱动推演、缺证罢工、禁套话、
# 送礼决策严格排除足浴盆与饰品并命中膝盖热敷。
# ===========================================================================

from datetime import date as _date  # noqa: E402

from aios_core.cognition.symbiotic_advisor import (  # noqa: E402
    AdviceEvidenceInsufficientError,
    EvidenceLedger,
    Fact,
    FraudPreventionAdvisorV2,
    HealthFatigueBreakerAdvisorV2,
    MomBirthdayGiftAdvisorV2,
    build_canonical_laowang_mom_ledger,
)


def test_mom_gift_derivation_excludes_and_targets():
    advisor = MomBirthdayGiftAdvisorV2()
    advice = advisor.advise(target_year=2026)
    assert "足浴盆" in advice.conclusion and "严禁" in advice.conclusion
    assert "饰品" in advice.conclusion
    assert "膝盖" in advice.conclusion and ("热敷" in advice.conclusion and "理疗" in advice.conclusion)
    ids = {p.object_id for p in advice.evidence_pointers}
    assert {"obs_2024_footbath_backache", "obs_2023_scarf_idle", "obs_2026_knee_cold"} <= ids
    for banal in ("因人而异", "多喝热水", "仅供参考", "量力而行"):
        assert banal not in advice.conclusion


def test_mom_gift_refuses_without_knee_evidence():
    ledger = build_canonical_laowang_mom_ledger()
    ledger._facts = [f for f in ledger._facts if f.kind != "knee_cold"]
    with pytest.raises(AdviceEvidenceInsufficientError, match="膝盖受凉"):
        MomBirthdayGiftAdvisorV2(ledger).advise(target_year=2026)
    # 也不许替 2027 年凭空假设
    fresh = EvidenceLedger([
        Fact("obs_2027_knee", "knee_cold", _date(2027, 9, 1), frozenset({"knee"})),
    ])
    with pytest.raises(AdviceEvidenceInsufficientError):
        MomBirthdayGiftAdvisorV2(fresh).advise(target_year=2026)


def test_fraud_advisor_requires_both_pillars():
    advisor = FraudPreventionAdvisorV2()
    advice = advisor.advise()
    ids = {p.object_id for p in advice.evidence_pointers}
    assert "court_ruling_chaoyang_fraud" in ids and "obs_2_years_ago_wechat_delay" in ids
    assert "阻击" in advice.conclusion and "追偿" in advice.conclusion
    # 抽掉判决 → 罢工，绝不凭空阻击
    no_judgement = EvidenceLedger(
            [f for f in build_canonical_laowang_mom_ledger()._facts if f.kind != "judgement"]
    )
    with pytest.raises(AdviceEvidenceInsufficientError, match="法院判决"):
        FraudPreventionAdvisorV2(no_judgement).advise()


def test_health_breaker_links_causal_chain_same_day():
    advice = HealthFatigueBreakerAdvisorV2().advise()
    ids = [p.object_id for p in advice.evidence_pointers]
    assert "obs_thursday_overnight_work" in ids and "obs_pvc_arrhythmia" in ids
    assert "熔断" in advice.conclusion and "心电图" in advice.conclusion
    assert any("心内科" in advice.conclusion or "面诊" in advice.conclusion for _ in [0])
    # 因果链指针必须同日对齐：单独早搏（无当日通宵）不允许触发"通宵因果"措辞
    lone = EvidenceLedger([Fact("obs_pvc_only", "pvc", _date(2026, 9, 20),
                                frozenset({"ventricular"}), {"burden": 12})])
    with pytest.raises(AdviceEvidenceInsufficientError, match="通宵"):
        HealthFatigueBreakerAdvisorV2(lone).advise()


def test_ledger_forbids_overwrite_of_evidence():
    ledger = build_canonical_laowang_mom_ledger()
    with pytest.raises(ValueError, match="不可覆写"):
        ledger.add(Fact("obs_2026_knee_cold", "knee_cold", _date(2026, 9, 2), frozenset()))
