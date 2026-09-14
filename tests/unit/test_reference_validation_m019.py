"""M0-019 reference existence and same-transaction validation tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios_core.contracts import (
    EvidenceCoverage,
    EvidenceSet,
    KnowledgeWindow,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    Relation,
    SourceRef,
    TemporalExtent,
    new_object_id,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError

NOW = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)


def op(expected: int, key: str) -> OperationRequest:
    return OperationRequest(
        operation_name="world.commit",
        expected_world_revision=expected,
        reason="M0-019 reference validation",
        idempotency_key=key,
    )


def obs(
    object_id: str,
    revision: int = 1,
    *,
    learned_at: datetime = NOW,
    source_refs: list[SourceRef] | None = None,
) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(learned_at),
        learned_at=learned_at,
        recorded_at=learned_at,
        source_refs=source_refs or [],
        created_by="m0-019-test",
        source_kind="chat",
        modality="text",
        value="raw evidence",
    )


def relation(
    object_id: str,
    left: ObjectRef,
    right: ObjectRef,
    *,
    revision: int = 1,
    learned_at: datetime = NOW,
) -> Relation:
    return Relation(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(learned_at),
        learned_at=learned_at,
        recorded_at=learned_at,
        created_by="m0-019-test",
        left=left,
        relation_type="linked",
        right=right,
        confidence=0.5,
    )


def test_m019_01_missing_object_ref_rejected_without_partial_commit(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    holder = relation(
        new_object_id(ObjectType.RELATION),
        ObjectRef(object_id="missing-a", revision=1),
        ObjectRef(object_id="missing-b", revision=1),
    )

    with pytest.raises(StoreError) as exc:
        store.commit([holder], op(0, "missing-ref"))

    assert exc.value.code == ErrorCode.NOT_FOUND
    assert store.current_world_revision() == 0
    assert store.list_payloads() == []


def test_m019_02_same_transaction_evidence_set_can_reference_new_observation(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    observation_id = new_object_id(ObjectType.OBSERVATION)
    evidence_id = new_object_id(ObjectType.EVIDENCE_SET)
    observation = obs(observation_id)
    evidence = EvidenceSet(
        object_id=evidence_id,
        subject_id="user_1",
        revision=1,
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-019-test",
        purpose="support claim",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=NOW, world_revision=0),
        member_refs=[ObjectRef(object_id=observation_id, revision=1)],
        support_refs=[ObjectRef(object_id=observation_id, revision=1)],
        selection_method="explicit",
        coverage=EvidenceCoverage(expected_count=1, observed_count=1, coverage_ratio=1.0),
    )

    result = store.commit([observation, evidence], op(0, "same-tx-evidence"))

    assert result.world_revision == 1
    assert store.get_payload(evidence_id)["member_refs"][0] == {
        "object_id": observation_id,
        "revision": 1,
    }


def test_m019_03_same_transaction_mutual_non_evidence_refs_remain_legal(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    a_id = new_object_id(ObjectType.RELATION)
    b_id = new_object_id(ObjectType.RELATION)
    a = relation(
        a_id,
        ObjectRef(object_id=b_id, revision=1),
        ObjectRef(object_id=b_id, revision=1),
    )
    b = relation(
        b_id,
        ObjectRef(object_id=a_id, revision=1),
        ObjectRef(object_id=a_id, revision=1),
    )

    result = store.commit([a, b], op(0, "mutual-links"))
    assert result.world_revision == 1


def test_m019_04_current_revision_objectref_self_reference_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    object_id = new_object_id(ObjectType.RELATION)
    holder = relation(
        object_id,
        ObjectRef(object_id=object_id, revision=1),
        ObjectRef(object_id=object_id, revision=1),
    )

    with pytest.raises(StoreError) as exc:
        store.commit([holder], op(0, "self-object-ref"))
    assert exc.value.code == ErrorCode.DEPENDENCY_INVALID
    assert store.current_world_revision() == 0


def test_m019_05_current_revision_sourceref_self_reference_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    object_id = new_object_id(ObjectType.OBSERVATION)
    holder = obs(
        object_id,
        source_refs=[SourceRef(object_id=object_id, revision=1)],
    )

    with pytest.raises(StoreError) as exc:
        store.commit([holder], op(0, "self-source-ref"))
    assert exc.value.code == ErrorCode.DEPENDENCY_INVALID
    assert store.current_world_revision() == 0


def test_m019_06_previous_revision_self_link_is_historical_and_legal(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    endpoint_id = new_object_id(ObjectType.OBSERVATION)
    relation_id = new_object_id(ObjectType.RELATION)
    endpoint = obs(endpoint_id)
    first = relation(
        relation_id,
        ObjectRef(object_id=endpoint_id, revision=1),
        ObjectRef(object_id=endpoint_id, revision=1),
    )
    store.commit([endpoint, first], op(0, "self-history-v1"))

    second = relation(
        relation_id,
        ObjectRef(object_id=relation_id, revision=1),
        ObjectRef(object_id=endpoint_id, revision=1),
        revision=2,
    )
    result = store.commit([second], op(1, "self-history-v2"))
    assert result.world_revision == 2


def test_m019_07_commit_has_no_public_reference_validation_bypass(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    holder = relation(
        new_object_id(ObjectType.RELATION),
        ObjectRef(object_id="missing-a", revision=1),
        ObjectRef(object_id="missing-b", revision=1),
    )

    with pytest.raises(TypeError):
        store.commit([holder], op(0, "no-bypass"), validate_references=False)  # type: ignore[call-arg]
    assert store.current_world_revision() == 0


def test_m019_08_pending_future_reference_rejected_by_knowledge_cutoff(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    older = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)
    target_id = new_object_id(ObjectType.OBSERVATION)
    holder = relation(
        new_object_id(ObjectType.RELATION),
        ObjectRef(object_id=target_id, revision=1),
        ObjectRef(object_id=target_id, revision=1),
        learned_at=older,
    )
    target = obs(target_id, learned_at=newer)

    with pytest.raises(StoreError) as exc:
        store.commit([holder, target], op(0, "future-pending"))
    assert exc.value.code == ErrorCode.NOT_FOUND
    assert exc.value.context["reason"] == "reference_not_visible_or_missing"
    assert store.current_world_revision() == 0
