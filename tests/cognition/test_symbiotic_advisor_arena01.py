# -*- coding: utf-8 -*-
"""Agent-09 / M5-SYMBIOTIC-ADVISOR 共生决策推演与行动建议 · 验收测试（arena01 线）

硬门禁：
- 无中生有即熔断（evidence=() 或缺锚点必须抛 MissingEvidenceError）；
- 泛泛套话 lint 熔断；所有建议携带可追溯因果证据指针 ObjectRef；
- 送礼：2023 丝巾 → 2024 足浴盆闲置倒水腰疼 → 2025 按摩椅好评 → 2026 膝盖
  受凉，收敛「轻便膝盖热敷仪」；
- 反欺诈：判决+微信借款 → 拒绝 + 恢复执行指针；早搏×通宵 → 强制停工。
"""

import pytest

from aios_core.cognition.symbiotic_advisor_arena01 import (
    ActionableAdvice,
    AdvisorEvidence,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    MissingEvidenceError,
    MomBirthdayGiftAdvisor,
    VagueAdviceLintError,
    _lint_and_cost,
)
from aios_core.contracts.refs import ObjectRef


def _ref(name: str) -> ObjectRef:
    return ObjectRef(object_id=name, revision=1)


GIFT_EVIDENCE = (
    AdvisorEvidence(_ref("g-2023"), "gift_history", 2023, "2023 母亲节丝巾已送出"),
    AdvisorEvidence(_ref("g-2024"), "gift_history", 2024, "2024 足浴盆闲置倒水腰疼"),
    AdvisorEvidence(_ref("g-2025"), "gift_history", 2025, "2025 按摩椅长期好评"),
    AdvisorEvidence(_ref("g-2026"), "gift_history", 2026, "2026 夜间膝盖受凉酸胀"),
)


def test_mom_birthday_gift_converges_to_knee_heat_pad():
    advice = MomBirthdayGiftAdvisor().advise(GIFT_EVIDENCE)
    assert "膝盖热敷仪" in advice.verdict
    assert len(advice.causal_chain) == 4
    assert len(advice.evidence) == 4
    assert {r.object_id for r in advice.evidence} == {"g-2023", "g-2024", "g-2025", "g-2026"}
    # 泛套话不得出现
    for phrase in ("看情况", "再说", "可以考虑"):
        assert phrase not in advice.verdict


def test_mom_birthday_gift_missing_anchor_fuses():
    with pytest.raises(MissingEvidenceError, match="2024"):
        MomBirthdayGiftAdvisor().advise(GIFT_EVIDENCE[:1] + GIFT_EVIDENCE[2:])
    with pytest.raises(MissingEvidenceError):
        ActionableAdvice(advice_id="x", headline="h", verdict="v",
                         causal_chain=("c",), evidence=(), token_cost=1)
    with pytest.raises(MissingEvidenceError):
        ActionableAdvice(advice_id="x", headline="h", verdict="v",
                         causal_chain=(), evidence=(_ref("e"),), token_cost=1)


def test_vague_lint_fuses():
    with pytest.raises(VagueAdviceLintError):
        _lint_and_cost("标题", "看情况吧", ("链",))


def test_fraud_prevention_refuses_and_points_to_execution():
    evidence = (
        AdvisorEvidence(_ref("loan-wechat"), "chat_wechat", 2024,
                        "微信转账借条：老王借款 6 万承诺三个月归还未清偿"),
        AdvisorEvidence(_ref("judgment-001"), "judicial", 2025,
                        "法院民事判决书：老王同类借款被限期清偿仍拖延"),
    )
    advice = FraudPreventionAdvisor().advise(evidence)
    assert "拒绝" in advice.verdict and "执行" in advice.verdict
    assert evidence[0].ref in advice.evidence and evidence[1].ref in advice.evidence
    assert advice.token_cost <= 300
    with pytest.raises(MissingEvidenceError):
        FraudPreventionAdvisor().advise(e for e in evidence if e.domain != "judicial")


def test_health_fatigue_breaker_forces_shutdown():
    evidence = (
        AdvisorEvidence(_ref("ot-log"), "calendar", 2026, "连续三晚通宵批注对赌合同"),
        AdvisorEvidence(_ref("holter-09"), "health", 2026, "室性早搏频报，医嘱复查"),
    )
    advice = HealthFatigueBreakerAdvisor().advise(evidence)
    assert "停下" in advice.verdict or "停工" in advice.headline
    assert len(advice.evidence) == 2
    with pytest.raises(MissingEvidenceError):
        HealthFatigueBreakerAdvisor().advise(evidence[:1])
