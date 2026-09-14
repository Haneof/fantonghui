from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from aios_core.contracts import Observation, ObjectRef, OperationRequest, SourceRef
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError


T = datetime(2026, 9, 14, 9, tzinfo=timezone.utc)
TABLES = ("world_commits", "object_revisions", "operations", "idempotency_records")


def _observation(object_id: str = "holder", **kwargs) -> Observation:
    data = {
        "object_id": object_id,
        "subject_id": "integrator-x5-x7",
        "learned_at": T,
        "recorded_at": T,
        "created_by": "integrator-x5-x7",
        "source_kind": "test",
        "modality": "json",
    }
    data.update(kwargs)
    return Observation(**data)


def _operation(key: str = "case", revision: int = 1, **kwargs) -> OperationRequest:
    data = {
        "operation_id": f"op-{key}",
        "operation_name": "world.commit",
        "expected_world_revision": revision,
        "idempotency_key": key,
        "reason": "integrator X5-X7 regression",
    }
    data.update(kwargs)
    return OperationRequest(**data)


def _state(store: SQLiteWorldStore):
    with sqlite3.connect(store.db_path) as conn:
        revision = int(
            conn.execute(
                "SELECT value FROM world_meta WHERE key='world_revision'"
            ).fetchone()[0]
        )
        rows = tuple(
            tuple(conn.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall())
            for table in TABLES
        )
    return (revision,) + rows


def _reject(store, objects, request, code: ErrorCode) -> None:
    before = _state(store)
    try:
        with pytest.raises(StoreError) as exc:
            store.commit(objects, request)
        assert exc.value.code == code
    finally:
        assert _state(store) == before


def _replay(store, objects, request) -> None:
    before = _state(store)
    result = store.commit(objects, request)
    assert result.idempotent_replay is True
    assert _state(store) == before


def _seeded(path) -> SQLiteWorldStore:
    store = SQLiteWorldStore(path)
    store.commit([_observation("anchor")], _operation("seed", revision=0))
    return store


def _at(slot: str, value):
    request = _operation()
    if slot == "value":
        return _observation(value=value), request
    if slot == "metadata":
        return _observation(metadata={"probe": value}), request
    if slot == "arguments":
        return _observation(), _operation(arguments={"probe": value})
    raise AssertionError(slot)


def _durable_at(store: SQLiteWorldStore, slot: str):
    if slot == "arguments":
        with sqlite3.connect(store.db_path) as conn:
            row = conn.execute(
                "SELECT arguments_json FROM operations WHERE operation_id='op-case'"
            ).fetchone()
        return json.loads(row[0])["probe"]
    payload = store.get_payload("holder")
    if slot == "value":
        return payload["value"]
    if slot == "metadata":
        return payload["metadata"]["probe"]
    raise AssertionError(slot)


def _legacy_fixture(store: SQLiteWorldStore) -> None:
    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT result_json FROM idempotency_records WHERE idempotency_key='case'"
        ).fetchone()
        data = json.loads(row[0])
        data.pop("_request_fingerprint")
        conn.execute(
            "UPDATE idempotency_records SET result_json=? WHERE idempotency_key='case'",
            (json.dumps(data),),
        )


@pytest.mark.parametrize("slot", ["metadata", "value", "arguments"])
@pytest.mark.parametrize("ref_cls", [ObjectRef, SourceRef])
def test_x5_legacy_typed_to_opaque_fails_closed(tmp_path, slot, ref_cls):
    store = _seeded(tmp_path / "world.db")
    ref = ref_cls(object_id="anchor", revision=1)
    typed_obj, typed_request = _at(slot, ref)
    store.commit([typed_obj], typed_request)
    _legacy_fixture(store)

    opaque_obj, opaque_request = _at(slot, ref.model_dump(mode="python"))
    _reject(
        SQLiteWorldStore(store.db_path),
        [opaque_obj],
        opaque_request,
        ErrorCode.IDEMPOTENCY_CONFLICT,
    )


@pytest.mark.parametrize("target", ["world", "operation", "ObjectRef", "SourceRef"])
@pytest.mark.parametrize("retry", [False, True])
def test_x6_underscore_dirty_unknown_field_is_revalidated(tmp_path, target, retry):
    store = _seeded(tmp_path / "world.db")
    if target in ("ObjectRef", "SourceRef"):
        ref_cls = ObjectRef if target == "ObjectRef" else SourceRef
        ref = ref_cls(object_id="anchor", revision=1)
        clean, request = _at("metadata", {"nested": [ref]})
        dirty, changed_request = _at(
            "metadata",
            {"nested": [ref.model_copy(update={"_rogue": "payload"})]},
        )
    else:
        clean, request = _at("value", "safe")
        dirty = (
            clean.model_copy(update={"_rogue": "payload"})
            if target == "world"
            else clean
        )
        changed_request = (
            request.model_copy(update={"_rogue": "payload"})
            if target == "operation"
            else request
        )

    if retry:
        store.commit([clean], request)
    _reject(
        SQLiteWorldStore(store.db_path),
        [dirty],
        changed_request,
        ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT,
    )


@pytest.mark.parametrize("slot", ["metadata", "value", "arguments"])
def test_x7_unordered_value_replays_from_durable_normal_form(tmp_path, slot):
    store = _seeded(tmp_path / "world.db")
    obj, request = _at(slot, {"unordered": frozenset({"alpha", "beta"})})
    store.commit([obj], request)

    normal = _durable_at(store, slot)
    assert normal == {"unordered": ["alpha", "beta"]}

    obj2, request2 = _at(slot, normal)
    _replay(SQLiteWorldStore(store.db_path), [obj2], request2)
