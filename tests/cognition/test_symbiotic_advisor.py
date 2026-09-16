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


# =====================================================================
# M5-004 演化件：证据台账驱动的顾问——指针必须真实，缺证宁可不答
# =====================================================================

import datetime as dt
from aios_core.cognition.symbiotic_advisor import (
    EvidenceLedger,
    FraudPreventionAdvisorV2,
    HealthFatigueBreakerAdvisorV2,
    MissingEvidenceError,
    MomBirthdayGiftAdvisorV2,
)


def _gift_ledger():
    return EvidenceLedger(
        {
            "obs_2023_scarf_idle": {
                "kind": "gift_history",
                "gift_category": "饰品",
                "year": 2023,
                "text": "2023 年送的真丝丝巾在柜子里落灰，一次都没戴过",
            },
            "obs_2024_footbath_backache": {
                "kind": "gift_history",
                "gift_category": "笨重水洗家电",
                "year": 2024,
                "text": "2024 年的足浴盆太笨重，倒水闪了腰疼，彻底闲置",
            },
            "obs_2025_massage_chair_good": {
                "kind": "gift_history",
                "gift_category": "理疗器械",
                "year": 2025,
                "text": "2025 年的按摩椅获得全家好评，老妈天天用",
            },
            "obs_2026_knee_cold": {
                "kind": "observation",
                "text": "2026 年 9 月观测：老妈膝盖老寒腿受凉，上下楼关节疼",
            },
        }
    )


def test_gift_advisor_v2_derives_knee_therapy_from_evidence():
    advice = MomBirthdayGiftAdvisorV2().advise(_gift_ledger(), budget_yuan=500)

    assert isinstance(advice, ActionableAdvice)
    assert advice.advice_id.startswith("advice_gift_")
    assert "膝盖气囊热敷理疗仪" in advice.conclusion or "膝盖" in advice.conclusion
    # 禁区必须被点名：笨重水洗家电与饰品
    assert "笨重水洗家电" in advice.conclusion
    assert "饰品" in advice.conclusion
    # 每一条证据指针都必须真实存在于台账
    ledger = _gift_ledger()
    assert advice.evidence_pointers
    for ptr in advice.evidence_pointers:
        assert ledger.has(ptr.object_id), f"虚指证据 {ptr.object_id}"
    ids = {p.object_id for p in advice.evidence_pointers}
    assert "obs_2026_knee_cold" in ids
    # 备选方案不得包含足浴盆与饰品
    assert all("足浴" not in a and "首饰" not in a and "丝巾" not in a for a in advice.alternatives)


def test_gift_advisor_v2_budget_downgrade():
    advice = MomBirthdayGiftAdvisorV2().advise(_gift_ledger(), budget_yuan=100)
    # 299 元理疗仪超预算，自动降级到膝盖理疗类目内的平价替代
    assert "保暖护膝" in advice.conclusion or "理疗贴" in advice.conclusion


def test_gift_advisor_v2_refuses_without_knee_evidence():
    ledger = _gift_ledger()
    ledger = EvidenceLedger({k: ledger.get(k) for k in ledger.ids() if k != "obs_2026_knee_cold"})
    with pytest.raises(MissingEvidenceError):
        MomBirthdayGiftAdvisorV2().advise(ledger)


def test_fraud_advisor_v2_hard_refusal_with_full_chain():
    ledger = EvidenceLedger(
        {
            "court_ruling_chaoyang_fraud": {
                "kind": "court_judgment",
                "text": "朝阳法院生效判决：老王合伙借款构成合同诈骗，责令退赔",
            },
            "obs_2_years_ago_wechat_delay": {
                "kind": "wechat_record",
                "text": "两年前微信催款切片：老王已读不回，一再拖延还款",
            },
        }
    )
    advice = FraudPreventionAdvisorV2().advise(ledger)

    assert advice.hard_refusal is True
    assert "阻击" in advice.conclusion and "追偿" in advice.conclusion
    ids = {p.object_id for p in advice.evidence_pointers}
    assert ids == {"court_ruling_chaoyang_fraud", "obs_2_years_ago_wechat_delay"}
    assert any("强制执行" in a or "律师函" in a for a in advice.alternatives)


def test_fraud_advisor_v2_refuses_on_incomplete_chain():
    # 只有判决、没有历史拖延记录：证据链不完整，禁止凭空定性
    partial = EvidenceLedger(
        {"court_ruling": {"kind": "court_judgment", "text": "法院判决老王败诉"}}
    )
    with pytest.raises(MissingEvidenceError):
        FraudPreventionAdvisorV2().advise(partial)

    with pytest.raises(MissingEvidenceError):
        FraudPreventionAdvisorV2().advise(EvidenceLedger())


def test_fatigue_breaker_v2_forced_stop_with_causal_chain():
    ledger = EvidenceLedger(
        {
            "obs_thursday_overnight_work": {
                "kind": "overnight_work",
                "text": "周四连续通宵赶版本上线",
                "occurred_at": dt.datetime(2026, 9, 10, 3, 30),
            },
            "obs_pvc_arrhythmia": {
                "kind": "pvc",
                "text": "凌晨心电捕捉室性早搏 12 次/分",
                "occurred_at": dt.datetime(2026, 9, 10, 4, 10),
            },
        }
    )
    advice = HealthFatigueBreakerAdvisorV2().advise(ledger)

    assert advice.forced_action is True
    assert "熔断" in advice.conclusion and "心电图" in advice.conclusion
    ids = {p.object_id for p in advice.evidence_pointers}
    assert ids == {"obs_thursday_overnight_work", "obs_pvc_arrhythmia"}


def test_fatigue_breaker_v2_rejects_reversed_causality():
    ledger = EvidenceLedger(
        {
            "obs_overnight": {
                "kind": "overnight_work",
                "text": "通宵加班",
                "occurred_at": dt.datetime(2026, 9, 11, 3, 0),
            },
            "obs_pvc": {
                "kind": "pvc",
                "text": "室性早搏",
                "occurred_at": dt.datetime(2026, 9, 10, 4, 0),  # 早搏先于通宵
            },
        }
    )
    with pytest.raises(MissingEvidenceError, match="因果方向"):
        HealthFatigueBreakerAdvisorV2().advise(ledger)
