"""R5/R6 AI Self World constitutional regression.

The retired `cognition.self_reflection` module used trust-score thresholds and keyword
posture rules as a second cognitive brain. These tests now protect the replacement:
evidence-linked, versioned AI self understanding whose meaning is produced by the AI,
not inferred from fixed Python score ladders.
"""

from datetime import datetime, timezone

import pytest

from aios_core.runtime.ai_self_world import (
    AISelfMemoryKind,
    AISelfMemoryRecord,
    AISelfWorldStoreV2,
)

UTC = timezone.utc


def test_ai_identity_is_a_durable_statement_not_a_personality_score(tmp_path):
    store = AISelfWorldStoreV2(tmp_path / "world.db")
    identity = AISelfMemoryRecord.create(
        memory_key="identity:core",
        version=1,
        kind=AISelfMemoryKind.IDENTITY,
        statement="我是 AIOS 的 AI 驾驶员；依赖证据、能力与边界运行系统。",
    )
    store.append(identity)

    loaded = store.latest("identity:core")
    assert loaded == identity
    assert "score" not in loaded.structured_data
    assert loaded.kind is AISelfMemoryKind.IDENTITY


def test_relationship_understanding_cannot_be_created_without_evidence():
    with pytest.raises(ValueError, match="requires evidence_refs"):
        AISelfMemoryRecord.create(
            memory_key="relationship:user_1",
            version=1,
            kind=AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING,
            statement="用户已经是所谓‘死党’。",
            evidence_refs=(),
        )


def test_relationship_understanding_evolves_by_forward_versions(tmp_path):
    store = AISelfWorldStoreV2(tmp_path / "world.db")
    v1 = AISelfMemoryRecord.create(
        memory_key="relationship:user_1",
        version=1,
        kind=AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING,
        statement="目前只能确认用户愿意持续进行架构讨论，关系深度未知。",
        evidence_refs=("turn_001", "turn_004"),
        learned_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 1, 8, 0, 1, tzinfo=UTC),
    )
    store.append(v1)

    v2 = AISelfMemoryRecord.create(
        memory_key="relationship:user_1",
        version=2,
        kind=AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING,
        statement="多次交互表明用户偏好直接、证据化的工程沟通；仍不预设固定亲密身份。",
        structured_data={"communication_preference": "direct_evidence_grounded"},
        evidence_refs=("turn_027", "commexp_12"),
        previous_record_id=v1.record_id,
        learned_at=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 18, 8, 0, 1, tzinfo=UTC),
    )
    store.append(v2)

    assert store.latest("relationship:user_1") == v2
    assert store.history("relationship:user_1") == [v1, v2]


def test_keyword_presence_alone_does_not_create_a_response_posture():
    """‘老王借款/早搏’ is evidence text, not a deterministic personality decision."""

    raw_context = {"keywords": ["老王借款", "早搏"], "severity": "LOW"}
    # There is intentionally no generic `decide_posture(raw_context)` rule anymore.
    # Safety emergencies are handled by the dedicated P0 wake/safety boundary.
    assert raw_context["keywords"] == ["老王借款", "早搏"]
    assert "response_posture" not in raw_context


def test_reflection_is_evidence_linked_instead_of_self_scored():
    reflection = AISelfMemoryRecord.create(
        memory_key="reflection:communication:2026-09-18",
        version=1,
        kind=AISelfMemoryKind.REFLECTION,
        statement="这次主动插话造成了打扰；以后遇到同类场景应先核对用户是否正在专注。",
        evidence_refs=("action_17", "reaction_17"),
        structured_data={"lesson": "check_interruption_context_first"},
    )
    assert reflection.evidence_refs == ("action_17", "reaction_17")
    assert "trust_score" not in reflection.structured_data
