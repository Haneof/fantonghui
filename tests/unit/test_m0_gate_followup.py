from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from aios_core.contracts import (
    Claim,
    ClaimType,
    KnowledgeState,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    SourceRef,
    TemporalExtent,
    new_object_id,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError

NOW = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)


def op(expected: int, key: str, operation_id: str) -> OperationRequest:
    return OperationRequest(
        operation_id=operation_id,
        session_id="gate-followup",
        operation_name="world.commit",
        arguments={"gate": "followup"},
        expected_world_revision=expected,
        reason="M0 Gate B4/B5 follow-up",
        idempotency_key=key,
    )


def observation(object_id: str, *, source_refs=None) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        source_refs=source_refs or [],
        created_by="m0-gate-followup",
        source_kind="test",
        modality="text",
        value="payload",
    )


def test_b4_floating_objectref_self_reference_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    claim_id = new_object_id(ObjectType.CLAIM)
    claim = Claim(
        object_id=claim_id,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-gate-followup",
        claimant_id="gate-user",
        claim_type=ClaimType.HYPOTHESIS,
        content="must not support itself through latest",
        asserted_at=NOW,
        knowledge_state=KnowledgeState.HYPOTHESIS,
        confidence=0.99,
        support_evidence_set_refs=[ObjectRef(object_id=claim_id, revision=None)],
    )

    with pytest.raises(StoreError) as exc:
        store.commit([claim], op(0, "b4-object", "b4-object-op"))
    assert exc.value.code is ErrorCode.DEPENDENCY_INVALID
    assert exc.value.context["reason"] == "self_reference"
    assert exc.value.context["referenced_revision"] is None
    assert store.current_world_revision() == 0


def test_b4_floating_sourceref_self_reference_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    object_id = new_object_id(ObjectType.OBSERVATION)
    obj = observation(
        object_id,
        source_refs=[SourceRef(object_id=object_id, revision=None)],
    )

    with pytest.raises(StoreError) as exc:
        store.commit([obj], op(0, "b4-source", "b4-source-op"))
    assert exc.value.code is ErrorCode.DEPENDENCY_INVALID
    assert exc.value.context["reason"] == "self_reference"
    assert store.current_world_revision() == 0


def test_b4_previous_pinned_revision_self_link_remains_legal(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    object_id = new_object_id(ObjectType.OBSERVATION)
    first = observation(object_id)
    store.commit([first], op(0, "history-1", "history-op-1"))

    second = first.model_copy(
        update={
            "revision": 2,
            "source_refs": [SourceRef(object_id=object_id, revision=1)],
        }
    )
    result = store.commit([second], op(1, "history-2", "history-op-2"))
    assert result.world_revision == 2


def test_b5_reused_operation_id_with_new_key_is_protocol_conflict(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    first_id = new_object_id(ObjectType.OBSERVATION)
    second_id = new_object_id(ObjectType.OBSERVATION)
    store.commit([observation(first_id)], op(0, "first-key", "shared-operation"))

    with pytest.raises(StoreError) as exc:
        store.commit([observation(second_id)], op(1, "second-key", "shared-operation"))
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert exc.value.context["reason"] == "operation_id_reused"
    assert store.current_world_revision() == 1
    with pytest.raises(StoreError) as missing:
        store.get_payload(second_id)
    assert missing.value.code is ErrorCode.NOT_FOUND


def test_b5_real_sqlite_lock_maps_to_protocol_error(tmp_path, monkeypatch):
    monkeypatch.setattr(SQLiteWorldStore, "SQLITE_BUSY_TIMEOUT_MS", 25)
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    object_id = new_object_id(ObjectType.OBSERVATION)

    blocker = sqlite3.connect(path, timeout=0.1)
    try:
        blocker.execute("PRAGMA journal_mode = WAL")
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(StoreError) as exc:
            store.commit([observation(object_id)], op(0, "lock-key", "lock-op"))
        assert exc.value.code is ErrorCode.VERSION_CONFLICT
        assert exc.value.context["reason"] == "storage_busy"
        assert store.current_world_revision() == 0
    finally:
        blocker.rollback()
        blocker.close()
