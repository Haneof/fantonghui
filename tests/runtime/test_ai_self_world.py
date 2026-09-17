"""R5 AI Self World: evidence/version history, not personality score bars."""

from datetime import datetime, timezone

import pytest

from aios_core.runtime.ai_self_world import (
    AISelfMemoryKind,
    AISelfMemoryRecord,
    AISelfWorldConflict,
    AISelfWorldStoreV2,
)

UTC = timezone.utc


def test_relationship_understanding_evolves_forward_with_evidence(tmp_path):
    store = AISelfWorldStoreV2(tmp_path / "world.db")
    v1 = AISelfMemoryRecord.create(
        memory_key="relationship:user_1",
        version=1,
        kind=AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING,
        statement="目前只知道用户愿意持续交流，关系深度仍需观察。",
        structured_data={"confidence": 0.35},
        evidence_refs=("turn_001", "turn_004"),
        learned_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 1, 10, 0, 1, tzinfo=UTC),
    )
    store.append(v1)

    v2 = AISelfMemoryRecord.create(
        memory_key="relationship:user_1",
        version=2,
        kind=AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING,
        statement="用户在技术架构讨论中偏好直接、证据化交流，但不应推断为固定亲密身份。",
        structured_data={"communication_preference": "direct_evidence_grounded"},
        evidence_refs=("turn_027", "commexp_12"),
        learned_at=datetime(2026, 9, 18, 10, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 18, 10, 0, 1, tzinfo=UTC),
        previous_record_id=v1.record_id,
    )
    store.append(v2)

    assert store.latest("relationship:user_1") == v2
    assert store.history("relationship:user_1") == [v1, v2]
    assert store.get("relationship:user_1", 1) == v1
    assert "score" not in v2.structured_data


def test_reflection_requires_evidence():
    with pytest.raises(ValueError):
        AISelfMemoryRecord.create(
            memory_key="reflection:2026-09-18",
            version=1,
            kind=AISelfMemoryKind.REFLECTION,
            statement="今天我觉得自己表现不错。",
            evidence_refs=(),
        )


def test_identity_can_exist_as_stable_governed_self_description(tmp_path):
    store = AISelfWorldStoreV2(tmp_path / "world.db")
    identity = AISelfMemoryRecord.create(
        memory_key="identity:core",
        version=1,
        kind=AISelfMemoryKind.IDENTITY,
        statement="我是 AIOS 的 AI 驾驶员，通过世界与工具帮助用户，而不是规则引擎人格分数。",
        evidence_refs=(),
    )
    store.append(identity)
    assert store.latest_by_kind(AISelfMemoryKind.IDENTITY) == [identity]


def test_memory_stream_cannot_skip_version_or_change_kind(tmp_path):
    store = AISelfWorldStoreV2(tmp_path / "world.db")
    v1 = AISelfMemoryRecord.create(
        memory_key="commitment:user_1:followup",
        version=1,
        kind=AISelfMemoryKind.COMMITMENT,
        statement="后续继续核对任务结果。",
    )
    store.append(v1)

    v3 = AISelfMemoryRecord.create(
        memory_key=v1.memory_key,
        version=3,
        kind=AISelfMemoryKind.COMMITMENT,
        statement="错误跳版。",
        previous_record_id=v1.record_id,
    )
    with pytest.raises(AISelfWorldConflict):
        store.append(v3)

    wrong_kind = AISelfMemoryRecord.create(
        memory_key=v1.memory_key,
        version=2,
        kind=AISelfMemoryKind.IDENTITY,
        statement="错误换类型。",
        previous_record_id=v1.record_id,
    )
    with pytest.raises(AISelfWorldConflict):
        store.append(wrong_kind)
