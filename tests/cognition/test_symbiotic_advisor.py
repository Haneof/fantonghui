"""M5 symbiotic advisors must derive every pointer from verified evidence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from aios_core.cognition.symbiotic_advisor import (
    ActionableAdvice,
    AdviceScenario,
    EvidenceFact,
    EvidenceIntegrityError,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    InMemoryEvidenceRepository,
    InsufficientEvidenceError,
    MomBirthdayGiftAdvisor,
    WorldEvidenceRepository,
)
from aios_core.contracts.refs import ObjectRef


def _fact(
    object_id: str,
    text: str,
    *,
    year: int = 2026,
    revision: int = 1,
    object_type: str = "observation",
) -> EvidenceFact:
    return EvidenceFact(
        ref=ObjectRef(object_id=object_id, revision=revision),
        object_type=object_type,
        text=text,
        occurred_at=datetime(year, 6, 1, tzinfo=UTC),
        source_kind="linux_simulation",
    )


@pytest.fixture
def evidence_repository() -> InMemoryEvidenceRepository:
    return InMemoryEvidenceRepository(
        (
            _fact("memory-a", "母亲收到丝巾后一直落灰未使用", year=2023),
            _fact("memory-b", "足浴盆很笨重，倒水让母亲腰疼，后来闲置", year=2024),
            _fact("memory-c", "按摩椅体验极佳，母亲喜欢而且常用", year=2025),
            _fact("memory-d", "母亲膝盖老寒腿，受凉后疼痛", year=2026),
            _fact(
                "legal-a",
                "北京市朝阳区法院判决：相关借款构成合同诈骗",
                object_type="claim",
            ),
            _fact("chat-a", "历史微信聊天显示对方反复拖延还款并推脱"),
            _fact("work-a", "周四连续通宵加班，整夜未睡"),
            _fact("health-a", "穿戴观测记录到频发室性早搏 PVC"),
        )
    )


def _assert_all_pointers_resolve(
    advice: ActionableAdvice,
    repository: InMemoryEvidenceRepository,
) -> None:
    assert advice.evidence_pointers
    assert all(pointer.revision is not None for pointer in advice.evidence_pointers)
    assert all(repository.resolve(pointer) for pointer in advice.evidence_pointers)


def test_mom_gift_uses_four_real_memories_and_excludes_failed_categories(
    evidence_repository: InMemoryEvidenceRepository,
):
    advice = MomBirthdayGiftAdvisor(evidence_repository).advise(budget_cny=1_800)

    assert advice.scenario is AdviceScenario.MOM_BIRTHDAY_GIFT
    assert "膝盖气囊热敷理疗仪" in advice.conclusion
    assert "足浴盆" in advice.conclusion
    assert "丝巾饰品" in advice.conclusion
    assert {pointer.object_id for pointer in advice.evidence_pointers} == {
        "memory-a",
        "memory-b",
        "memory-c",
        "memory-d",
    }
    _assert_all_pointers_resolve(advice, evidence_repository)


def test_mom_gift_refuses_to_invent_a_missing_history_fact(
    evidence_repository: InMemoryEvidenceRepository,
):
    incomplete = InMemoryEvidenceRepository(
        fact
        for fact in evidence_repository.list_facts()
        if fact.ref.object_id != "memory-c"
    )
    with pytest.raises(InsufficientEvidenceError, match="massage-chair"):
        MomBirthdayGiftAdvisor(incomplete).advise(1_800)


def test_fraud_advice_links_court_and_chat_then_blocks_new_exposure(
    evidence_repository: InMemoryEvidenceRepository,
):
    advice = FraudPreventionAdvisor(evidence_repository).advise(
        "老王再次请求借款，并提议新合伙项目"
    )

    assert advice.scenario is AdviceScenario.FRAUD_PREVENTION
    assert "阻击" in advice.conclusion
    assert "追偿" in advice.conclusion
    assert {pointer.object_id for pointer in advice.evidence_pointers} == {
        "legal-a",
        "chat-a",
    }
    _assert_all_pointers_resolve(advice, evidence_repository)


def test_health_advice_triggers_fatigue_breaker_and_real_medical_followup(
    evidence_repository: InMemoryEvidenceRepository,
):
    advice = HealthFatigueBreakerAdvisor(evidence_repository).advise()

    assert advice.scenario is AdviceScenario.HEALTH_FATIGUE_BREAKER
    assert "疲劳熔断" in advice.conclusion
    assert "停止工作" in advice.conclusion
    assert "心电图" in advice.conclusion
    assert "急救" in advice.conclusion
    assert {pointer.object_id for pointer in advice.evidence_pointers} == {
        "work-a",
        "health-a",
    }
    _assert_all_pointers_resolve(advice, evidence_repository)


def test_no_repository_or_forged_pointer_can_be_used_as_evidence(
    evidence_repository: InMemoryEvidenceRepository,
):
    with pytest.raises(InsufficientEvidenceError, match="hardcoded pointers"):
        HealthFatigueBreakerAdvisor().advise()

    forged = ObjectRef(object_id="made-up-evidence", revision=1)
    with pytest.raises(EvidenceIntegrityError, match="not found"):
        FraudPreventionAdvisor(evidence_repository).advise(
            "请求借款",
            evidence=(forged,),
        )

    with pytest.raises(EvidenceIntegrityError, match="pin a revision"):
        FraudPreventionAdvisor(evidence_repository).advise(
            "请求借款",
            evidence=(ObjectRef(object_id="legal-a"),),
        )


def test_negated_court_or_cardiac_text_cannot_masquerade_as_positive_evidence():
    repository = InMemoryEvidenceRepository(
        (
            _fact(
                "legal-negative",
                "法院判决明确不构成诈骗，诈骗罪不成立",
                object_type="claim",
            ),
            _fact("chat-positive", "微信聊天显示对方反复拖延还款"),
            _fact("work-positive", "周四连续通宵加班"),
            _fact("health-negative", "本次检查未发现早搏，排除室性早搏"),
        )
    )
    with pytest.raises(InsufficientEvidenceError, match="court fraud ruling"):
        FraudPreventionAdvisor(repository).advise("请求借款")
    with pytest.raises(InsufficientEvidenceError, match="premature beats"):
        HealthFatigueBreakerAdvisor(repository).advise()


def test_actionable_advice_physically_rejects_unpinned_or_empty_evidence():
    with pytest.raises(ValidationError, match="pin revisions"):
        ActionableAdvice(
            scenario=AdviceScenario.FRAUD_PREVENTION,
            conclusion="拒绝转账",
            evidence_pointers=(ObjectRef(object_id="unpinned"),),
            action_steps=("停止付款",),
            expected_benefit="避免损失",
        )
    with pytest.raises(ValidationError):
        ActionableAdvice(
            scenario=AdviceScenario.FRAUD_PREVENTION,
            conclusion="拒绝转账",
            evidence_pointers=(),
            action_steps=("停止付款",),
            expected_benefit="避免损失",
        )


def test_world_repository_resolves_the_exact_persisted_revision():
    payload = {
        "object_id": "persisted-fact",
        "revision": 2,
        "object_type": "observation",
        "source_kind": "chat",
        "value": "真实持久化聊天记录",
        "learned_at": "2026-09-16T12:00:00+00:00",
    }

    class Store:
        db_path = ""

        @staticmethod
        def get_payload(object_id, *, revision):
            if object_id != "persisted-fact" or revision != 2:
                raise KeyError(object_id)
            return payload

        @staticmethod
        def list_payloads(*, object_type):
            return [payload] if object_type.value == "observation" else []

    repository = WorldEvidenceRepository(Store())
    ref = ObjectRef(object_id="persisted-fact", revision=2)
    resolved = repository.resolve(ref)
    assert resolved.ref == ref
    assert resolved.text == "真实持久化聊天记录"
    assert any(fact.ref == ref for fact in repository.list_facts())
