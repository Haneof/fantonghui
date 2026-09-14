"""M0-016 OperationRequest, audit, optimistic concurrency, and idempotency tests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.contracts import (
    ObjectType,
    Observation,
    OperationAuditRecord,
    OperationRequest,
    TemporalExtent,
    new_object_id,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError


NOW = datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)


def make_obs(object_id: str, revision: int, text: str) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(NOW - timedelta(minutes=5)),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-016-test",
        source_kind="chat",
        modality="text",
        value=text,
    )


def make_operation(
    expected_world_revision: int,
    key: str,
    *,
    operation_id: str = "op_m0_016_001",
    session_id: str | None = "session_001",
    reason: str = "M0-016 durable write",
    arguments: dict | None = None,
) -> OperationRequest:
    return OperationRequest(
        operation_id=operation_id,
        session_id=session_id,
        operation_name="world.commit",
        arguments=arguments or {"source": "m0-016"},
        expected_world_revision=expected_world_revision,
        reason=reason,
        idempotency_key=key,
    )


def audit_model(raw: dict) -> OperationAuditRecord:
    return OperationAuditRecord(
        operation_id=raw["operation_id"],
        session_id=raw["session_id"],
        operation_name=raw["operation_name"],
        arguments=json.loads(raw["arguments_json"]),
        expected_world_revision=raw["expected_world_revision"],
        reason=raw["reason"],
        idempotency_key=raw["idempotency_key"],
        status=raw["status"],
        result_world_revision=raw["result_world_revision"],
        error_code=raw["error_code"],
        error_message=raw["error_message"],
        created_at=datetime.fromisoformat(raw["created_at"]),
    )


def test_o01_operation_request_freezes_required_fields():
    assert set(OperationRequest.model_fields) == {
        "operation_id",
        "session_id",
        "operation_name",
        "arguments",
        "expected_world_revision",
        "reason",
        "idempotency_key",
    }
    assert set(OperationAuditRecord.model_fields) == {
        "operation_id",
        "session_id",
        "operation_name",
        "arguments",
        "expected_world_revision",
        "reason",
        "idempotency_key",
        "status",
        "result_world_revision",
        "error_code",
        "error_message",
        "created_at",
    }


def test_o02_operation_request_rejects_blank_identity_fields_and_extra_keys():
    for field_name in ["operation_id", "operation_name", "reason", "idempotency_key"]:
        kwargs = {
            "operation_id": "op-1",
            "operation_name": "world.commit",
            "expected_world_revision": 0,
            "reason": "reason",
            "idempotency_key": "key-1",
        }
        kwargs[field_name] = "   "
        with pytest.raises(ValidationError):
            OperationRequest(**kwargs)

    with pytest.raises(ValidationError):
        OperationRequest(
            operation_id="op-1",
            operation_name="world.commit",
            expected_world_revision=0,
            reason="reason",
            idempotency_key="key-1",
            invented_field=True,
        )


def test_o03_operation_request_rejects_negative_world_revision_and_blank_session():
    with pytest.raises(ValidationError):
        make_operation(-1, "key-negative")
    with pytest.raises(ValidationError):
        make_operation(0, "key-session", session_id="   ")


def test_o04_validate_assignment_keeps_frozen_operation_identity_valid():
    request = make_operation(0, "key-assignment")
    with pytest.raises(ValidationError):
        request.reason = "   "
    with pytest.raises(ValidationError):
        request.idempotency_key = ""


def test_o05_same_key_retry_returns_original_result_and_advances_world_once(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    request = make_operation(0, "same-key")

    first = store.commit([make_obs(oid, 1, "first")], request)
    replay = store.commit([make_obs(oid, 1, "first")], request)

    assert first.operation_id == replay.operation_id == request.operation_id
    assert first.world_revision == replay.world_revision == 1
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert store.current_world_revision() == 1
    assert len(store.list_payloads(object_type=ObjectType.OBSERVATION)) == 1


def test_o06_idempotency_replay_precedes_now_stale_expected_revision(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    request = make_operation(0, "replay-before-version-check")

    first = store.commit([make_obs(oid, 1, "first")], request)
    assert store.current_world_revision() == 1

    # expected_world_revision=0 is stale now, but this is the exact same logical
    # operation/key and therefore must replay before optimistic concurrency rejects it.
    replay = store.commit([make_obs(oid, 1, "first")], request)
    assert replay.world_revision == first.world_revision == 1
    assert replay.idempotent_replay is True


def test_o07_old_expected_revision_with_new_key_is_version_conflict(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit(
        [make_obs(oid, 1, "first")],
        make_operation(0, "key-1", operation_id="op-1"),
    )

    with pytest.raises(StoreError) as exc:
        store.commit(
            [make_obs(oid, 2, "must-not-overwrite")],
            make_operation(0, "key-2", operation_id="op-2"),
        )
    assert exc.value.code == ErrorCode.VERSION_CONFLICT
    assert store.current_world_revision() == 1
    assert store.get_payload(oid, revision=1)["value"] == "first"
    with pytest.raises(StoreError) as missing:
        store.get_payload(oid, revision=2)
    assert missing.value.code == ErrorCode.NOT_FOUND


def test_o08_successful_operation_audit_is_queryable_and_complete(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    request = make_operation(
        0,
        "audit-key",
        operation_id="op-audit",
        session_id="session-audit",
        reason="user correction write",
        arguments={"source": "chat", "correction": True},
    )
    result = store.commit([make_obs(oid, 1, "audited")], request)

    raw = store.operation_record("op-audit")
    audit = audit_model(raw)
    assert audit.operation_id == request.operation_id
    assert audit.session_id == request.session_id
    assert audit.operation_name == request.operation_name
    assert audit.arguments == request.arguments
    assert audit.expected_world_revision == 0
    assert audit.reason == request.reason
    assert audit.idempotency_key == request.idempotency_key
    assert audit.status == "committed"
    assert audit.result_world_revision == result.world_revision == 1
    assert audit.error_code is None
    assert audit.error_message is None
    assert audit.created_at.tzinfo is not None


def test_o09_operation_audit_and_idempotency_survive_store_restart(tmp_path):
    path = tmp_path / "world.db"
    oid = new_object_id(ObjectType.OBSERVATION)
    request = make_operation(0, "restart-key", operation_id="op-restart")

    first_store = SQLiteWorldStore(path)
    first = first_store.commit([make_obs(oid, 1, "persisted")], request)

    reopened = SQLiteWorldStore(path)
    audit = audit_model(reopened.operation_record("op-restart"))
    replay = reopened.commit([make_obs(oid, 1, "persisted")], request)

    assert audit.status == "committed"
    assert audit.result_world_revision == 1
    assert replay.world_revision == first.world_revision == 1
    assert replay.idempotent_replay is True
    assert reopened.current_world_revision() == 1


def test_o10_unknown_operation_audit_returns_not_found(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    with pytest.raises(StoreError) as exc:
        store.operation_record("missing-operation")
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_o11_version_conflict_is_not_swallowed_or_retried_as_overwrite(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)

    store.commit(
        [make_obs(a, 1, "winner")],
        make_operation(0, "winner-key", operation_id="winner-op"),
    )

    stale = make_operation(0, "stale-key", operation_id="stale-op")
    with pytest.raises(StoreError) as exc:
        store.commit([make_obs(b, 1, "stale writer")], stale)
    assert exc.value.code == ErrorCode.VERSION_CONFLICT
    assert store.current_world_revision() == 1
    with pytest.raises(StoreError) as missing:
        store.get_payload(b)
    assert missing.value.code == ErrorCode.NOT_FOUND


def test_o12_commit_result_is_stable_on_idempotent_replay(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    request = make_operation(0, "stable-result-key", operation_id="op-stable")

    first = store.commit([make_obs(oid, 1, "stable")], request)
    replay = store.commit([make_obs(oid, 1, "stable")], request)

    assert replay.operation_id == first.operation_id
    assert replay.world_revision == first.world_revision
    assert replay.object_refs == first.object_refs
    assert replay.idempotent_replay is True
