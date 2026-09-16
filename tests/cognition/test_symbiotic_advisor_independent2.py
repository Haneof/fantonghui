"""M5-SYMBIOTIC-ADVISOR 验收：共生决策推演能力。

1. 送礼推演：四年证据链→轻便膝盖热敷仪；缺年证 → KeyError；
   含套话 → ValueError；证据指空 → UnfoundedFabricationError；
2. 反欺诈推演：法院+微信欠证 → 冷拒+追偿；金额非法 → ValueError；
3. 熔断推演：<3 晚通宵 → ValueError (不构成因果链)；≥3 晚 → 强制停工；
4. 全部建议必须携带 ObjectRef（contracts 真身），严禁凭空编造。
"""

from __future__ import annotations

import pytest

from aios_core.contracts.refs import ObjectRef
from aios_core.cognition.symbiotic_advisor_independent2 import (
    ActionableAdvice,
    EvidenceLedger,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    MomBirthdayGiftAdvisor,
    SymbioticAdvisor,
    UnfoundedFabricationError,
)


def _ledger() -> EvidenceLedger:
    return EvidenceLedger({
        "gift_2023_scarf": "2023-05-12 妈妈生日送丝巾，互相都好",
        "gift_2024_footbath_idle": "2024-05-12 送足浴盆，后闲置且倒水闪了腰",
        "gift_2025_massage_chair": "2025-05-12 送按摩椅，一周用 5 次的好评",
        "health_2026_knee_cold": "2026-04-20 膝盖受冷痛，医嘱热敷",
        "court_judgment_2024": "法院判决书：老王未兑现还款义务",
        "wechat_loan_unpaid_2024": "2024-12-03 微信借款 5 万元，至2026 未还",
        "work_all_nighter_chain": "连续 5 晚 02:30 后下班的打卡链",
        "pvc_holter_report": "Holter: PVC 负荷 6.8/1000",
    })


def _refs(keys: list[str]) -> dict[str, ObjectRef]:
    return {k: ObjectRef(object_id=k, revision=1) for k in keys}


def test_mom_birthday_gift_advice_uses_four_year_chain() -> None:
    adv = MomBirthdayGiftAdvisor(_ledger())
    decision = adv.advise(_refs(["gift_2023_scarf", "gift_2024_footbath_idle",
                                 "gift_2025_massage_chair", "health_2026_knee_cold"]))
    assert decision.advice_id == "advice_mom_birthday_2026"
    assert "轻便膝盖热敷仪" in decision.action or "膝盖热敷" in decision.action
    assert len(decision.evidence) == 4
    # 证据必须落在账本里
    for r in decision.evidence:
        assert _ledger().exists(r)
    assert all(u not in decision.rationale for u in ("心意", "送什么都好"))


def test_mom_birthday_missing_year_evidence_fails() -> None:
    adv = MomBirthdayGiftAdvisor(_ledger())
    with pytest.raises(KeyError, match="关键年度证据"):
        adv.advise(_refs(["gift_2023_scarf", "gift_2025_massage_chair"]))


def test_advisor_rejects_generic_fluff_and_fabricated_evidence() -> None:
    ledger = _ledger()
    advisor = SymbioticAdvisor(ledger)
    fluff = ActionableAdvice(
        advice_id="bad1", action="a", rationale="送礼送心意即可",
        evidence=(ObjectRef(object_id="gift_2023_scarf", revision=1),),
    )
    with pytest.raises(ValueError, match="套话"):
        advisor._build(fluff)

    fabricated = ActionableAdvice(
        advice_id="bad2", action="a", rationale="正常建议",
        evidence=(ObjectRef(object_id="ghost_ref_404", revision=1),),
    )
    with pytest.raises(UnfoundedFabricationError):
        advisor._build(fabricated)

    no_evidence = ActionableAdvice(
        advice_id="bad3", action="a", rationale="r", evidence=(),
    )
    with pytest.raises(UnfoundedFabricationError):
        advisor._build(no_evidence)


def test_fraud_prevention_refuses_and_gives_legal_pointer() -> None:
    adv = FraudPreventionAdvisor(_ledger())
    adv_dec = adv.advise(_refs(["court_judgment_2024", "wechat_loan_unpaid_2024"]),
                         requested_amount_cny=200_000)
    assert "冷拒" in adv_dec.action
    assert "老王" in adv_dec.action
    assert "200000" in adv_dec.action.replace(",", "")
    assert "诉讼时效" in adv_dec.action or "追偿" in adv_dec.action
    assert len(adv_dec.evidence) == 2

    with pytest.raises(ValueError):
        adv.advise(_refs(["court_judgment_2024", "wechat_loan_unpaid_2024"]),
                   requested_amount_cny=-1)


def test_health_breaker_causal_chain_and_guardrails() -> None:
    adv = HealthFatigueBreakerAdvisor(_ledger())
    decision = adv.advise(_refs(["work_all_nighter_chain", "pvc_holter_report"]),
                          consecutive_all_nighters=3, pvc_burden_per_1000=6.8)
    assert "强制停工" in decision.action
    assert "心内科" in decision.action
    assert "3" in decision.action and "6.8" in decision.action
    assert len(decision.evidence) == 2

    with pytest.raises(ValueError, match="因果链"):
        adv.advise(_refs(["work_all_nighter_chain", "pvc_holter_report"]),
                   consecutive_all_nighters=2, pvc_burden_per_1000=6.8)
    with pytest.raises(ValueError):
        adv.advise(_refs(["work_all_nighter_chain", "pvc_holter_report"]),
                   consecutive_all_nighters=5, pvc_burden_per_1000=0.0)
