from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from aios_core.contracts import (
    Dependency,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    TemporalExtent,
    WorldObject,
    new_object_id,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError

NOW = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)


def op(expected: int, key: str) -> OperationRequest:
    return OperationRequest(
        operation_id=f"op-{key}",
        session_id="m0-fifth-followup",
        operation_name="world.commit",
        arguments={"gate": "B10-B11"},
        expected_world_revision=expected,
        reason="M0 Gate B10/B11 follow-up",
        idempotency_key=key,
    )


def obs(object_id: str, value) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-gate-fifth-followup",
        source_kind="test",
        modality="json",
        value=value,
    )


def fake(object_type: ObjectType) -> WorldObject:
    return WorldObject(
        object_id=f"fake-{object_type.value}",
        object_type=object_type,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-gate-fifth-followup",
    )


@pytest.mark.parametrize(
    "object_type",
    [
        ObjectType.DEPENDENCY,
        ObjectType.EVIDENCE_SET,
        ObjectType.TASK,
        ObjectType.EVENT,
        ObjectType.CLAIM,
        ObjectType.RELATION,
        ObjectType.DIMENSION_DEFINITION,
    ],
)
def test_b10_base_worldobject_cannot_masquerade_as_canonical_type(tmp_path, object_type):
    store = SQLiteWorldStore(tmp_path / "world.db")
    with pytest.raises(StoreError) as exc:
        store.commit([fake(object_type)], op(0, f"b10-{object_type.value}"))
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 0
    assert store.list_payloads() == []


def test_b10_legacy_poisoned_dependency_row_maps_to_storage_failure(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    poison_id = new_object_id(ObjectType.OBSERVATION)
    a_id = new_object_id(ObjectType.OBSERVATION)
    b_id = new_object_id(ObjectType.OBSERVATION)
    store.commit(
        [obs(poison_id, "poison"), obs(a_id, "a"), obs(b_id, "b")],
        op(0, "seed-poison"),
    )

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT payload_json FROM object_revisions WHERE object_id=? AND revision=1",
            (poison_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["object_type"] = ObjectType.DEPENDENCY.value
        conn.execute(
            "UPDATE object_revisions SET object_type=?, payload_json=? WHERE object_id=? AND revision=1",
            (ObjectType.DEPENDENCY.value, json.dumps(payload), poison_id),
        )
        conn.commit()

    dependency = Dependency(
        object_id=new_object_id(ObjectType.DEPENDENCY),
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-gate-fifth-followup",
        dependent_ref=ObjectRef(object_id=a_id, revision=1),
        dependency_ref=ObjectRef(object_id=b_id, revision=1),
        dependency_type="requires",
    )

    with pytest.raises(StoreError) as exc:
        store.commit([dependency], op(1, "after-poison"))
    assert exc.value.code is ErrorCode.STORAGE_FAILURE
    assert exc.value.context["reason"] == "corrupt_dependency_payload"
    assert store.current_world_revision() == 1


def test_b11_non_string_mapping_key_is_rejected_without_data_loss(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    object_id = new_object_id(ObjectType.OBSERVATION)
    value = {1: "numeric-key", "1": "string-key"}

    with pytest.raises(StoreError) as exc:
        store.commit([obs(object_id, value)], op(0, "b11-collision"))
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc.value.context["reason"] == "durable_json_validation_failed"
    assert store.current_world_revision() == 0
    assert store.list_payloads() == []


def test_b11_nested_non_string_mapping_key_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    object_id = new_object_id(ObjectType.OBSERVATION)
    with pytest.raises(StoreError) as exc:
        store.commit([obs(object_id, {"outer": {1: "x"}})], op(0, "b11-nested"))
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc.value.context["reason"] == "durable_json_validation_failed"
    assert store.current_world_revision() == 0


def test_b11_invalid_retry_cannot_alias_existing_idempotency_key(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    object_id = new_object_id(ObjectType.OBSERVATION)
    request = op(0, "b11-retry")
    store.commit([obs(object_id, {"1": "string-key"})], request)

    altered = obs(object_id, {1: "numeric-key", "1": "string-key"})
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([altered], request)
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert exc.value.context["reason"] == "request_revalidation_failed"
    assert SQLiteWorldStore(path).current_world_revision() == 1


def test_b11_operation_arguments_nested_non_string_key_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    request = op(0, "b11-operation")
    request.arguments["nested"] = {1: "x"}
    with pytest.raises(StoreError) as exc:
        store.commit([obs(new_object_id(ObjectType.OBSERVATION), "ok")], request)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc.value.context["reason"] == "durable_json_validation_failed"
    assert store.current_world_revision() == 0


def test_b11_string_mapping_keys_remain_lossless(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    object_id = new_object_id(ObjectType.OBSERVATION)
    value = {"1": "string-key", "nested": {"2": "two"}}
    result = store.commit([obs(object_id, value)], op(0, "b11-valid"))
    assert result.world_revision == 1
    assert store.get_payload(object_id)["value"] == value
