from datetime import datetime, timezone

import aios_core.cognition.symbiotic_advisor as legacy
from aios_core.cognition.evidence_grounded_advisor import (
    AdviceDecisionKind,
    ModelAdviceDecision,
)
from aios_core.contracts.refs import ObjectRef

UTC = timezone.utc


def test_hardcoded_advisor_classes_are_removed() -> None:
    for name in (
        "MomBirthdayGiftAdvisor",
        "FraudPreventionAdvisor",
        "HealthFatigueBreakerAdvisor",
    ):
        assert not hasattr(legacy, name)


def test_legacy_actionable_advice_is_only_a_model_decision_contract() -> None:
    text = (
        "亲爱的用户，这只是模型自主输出。"
        "首先这个旧触发词必须原样保留。"
        "保持积极心态也不能被 Python 正则删掉。"
        "第四句保留。第五句继续保留。"
    )
    decision = legacy.ActionableAdvice(
        decision=AdviceDecisionKind.RESPOND,
        intent="test",
        conclusion=text,
        action="model-selected action",
        rationale="model-selected rationale",
        evidence_pointers=(ObjectRef(object_id="obs_1", revision=1),),
        produced_at=datetime(2026, 9, 18, tzinfo=UTC),
        token_estimate=123,
    )
    assert isinstance(decision, ModelAdviceDecision)
    assert decision.conclusion == text
    assert decision.action == "model-selected action"


def test_model_decision_contract_requires_pinned_evidence() -> None:
    try:
        legacy.ActionableAdvice(
            decision=AdviceDecisionKind.RESPOND,
            intent="test",
            conclusion="reply",
            action=None,
            rationale="why",
            evidence_pointers=(ObjectRef(object_id="obs_1", revision=None),),
            produced_at=datetime(2026, 9, 18, tzinfo=UTC),
            token_estimate=1,
        )
    except ValueError as exc:
        assert "pin an exact revision" in str(exc)
    else:
        raise AssertionError("unpinned evidence must be rejected structurally")
