from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts import Observation, ObjectRef, OperationRequest, SourceRef
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError


T = datetime(2026, 9, 14, 9, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RefBox:
    ref: object


def obs(object_id: str = "holder", **kwargs) -> Observation:
    data = {
        "object_id": object_id,
        "subject_id": "chief-b9b-boundary",
        "learned_at": T,
        "recorded_at": T,
        "created_by": "chief-b9b-boundary",
        "source_kind": "test",
        "modality": "json",
    }
    data.update(kwargs)
    return Observation(**data)


def op(key: str, rev: int = 0, **kwargs) -> OperationRequest:
    data = {
        "operation_id": f"op-{key}",
        "operation_name": "world.commit",
        "expected_world_revision": rev,
        "idempotency_key": key,
        "reason": "chief b9b boundary adjudication",
    }
    data.update(kwargs)
    return OperationRequest(**data)


def seed(path) -> SQLiteWorldStore:
    store = SQLiteWorldStore(path)
    store.commit([obs("anchor")], op("seed"))
    return store


@pytest.mark.parametrize("ref_cls", [ObjectRef, SourceRef])
@pytest.mark.parametrize("slot", ["metadata", "value"])
def test_real_ref_hidden_in_dataclass_must_not_bypass_missing_ref_validation(tmp_path, ref_cls, slot):
    store = seed(tmp_path / "world.db")
    boxed = RefBox(ref_cls(object_id="missing", revision=1))
    obj = obs(metadata={"boxed": boxed}) if slot == "metadata" else obs(value=boxed)
    with pytest.raises(StoreError) as exc:
        store.commit([obj], op(f"dc-{ref_cls.__name__}-{slot}", rev=1))
    assert exc.value.code is ErrorCode.NOT_FOUND


def test_real_self_ref_hidden_in_dataclass_must_not_commit(tmp_path):
    store = seed(tmp_path / "world.db")
    obj = obs(metadata={"boxed": RefBox(ObjectRef(object_id="holder", revision=1))})
    with pytest.raises(StoreError) as exc:
        store.commit([obj], op("dc-self", rev=1))
    assert exc.value.code is ErrorCode.DEPENDENCY_INVALID


@pytest.mark.parametrize("field", ["learned_at", "recorded_at"])
def test_dirty_extreme_aware_datetime_must_not_leak_overflow(tmp_path, field):
    store = seed(tmp_path / "world.db")
    extreme = datetime.min.replace(tzinfo=timezone(timedelta(hours=14)))
    dirty = obs().model_copy(update={field: extreme})
    with pytest.raises(StoreError) as exc:
        store.commit([dirty], op(f"time-{field}", rev=1))
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.parametrize("method", ["revision", "world_revision"])
def test_huge_query_integer_must_not_leak_sqlite_binder_overflow(tmp_path, method):
    store = seed(tmp_path / "world.db")
    huge = 1 << 100
    with pytest.raises(StoreError) as exc:
        if method == "revision":
            store.get_payload("anchor", revision=huge)
        else:
            store.list_payloads(as_of_world_revision=huge)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.parametrize("which", ["get", "list"])
def test_corrupt_payload_json_must_map_to_storage_failure(tmp_path, which):
    store = seed(tmp_path / "world.db")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE object_revisions SET payload_json='{' WHERE object_id='anchor' AND revision=1")
        conn.commit()
    with pytest.raises(StoreError) as exc:
        if which == "get":
            store.get_payload("anchor")
        else:
            store.list_payloads()
    assert exc.value.code is ErrorCode.STORAGE_FAILURE


def test_corrupt_idempotency_result_json_must_map_to_storage_failure(tmp_path):
    store = seed(tmp_path / "world.db")
    obj = obs("holder")
    request = op("idem-corrupt", rev=1)
    store.commit([obj], request)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE idempotency_records SET result_json='{' WHERE idempotency_key=?", (request.idempotency_key,))
        conn.commit()
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(store.db_path).commit([obj], request)
    assert exc.value.code is ErrorCode.STORAGE_FAILURE


def test_corrupt_legacy_operation_json_must_map_to_storage_failure(tmp_path):
    store = seed(tmp_path / "world.db")
    obj = obs("holder", metadata={"ordinary": {"label": "x"}})
    request = op("legacy-corrupt", rev=1)
    store.commit([obj], request)
    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute("SELECT result_json FROM idempotency_records WHERE idempotency_key=?", (request.idempotency_key,)).fetchone()
        result = json.loads(row[0])
        result.pop("_request_fingerprint", None)
        conn.execute("UPDATE idempotency_records SET result_json=? WHERE idempotency_key=?", (json.dumps(result), request.idempotency_key))
        conn.execute("UPDATE operations SET arguments_json='{' WHERE operation_id=?", (request.operation_id,))
        conn.commit()
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(store.db_path).commit([obj], request)
    assert exc.value.code is ErrorCode.STORAGE_FAILURE


def test_corrupt_world_revision_must_map_to_storage_failure(tmp_path):
    store = seed(tmp_path / "world.db")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE world_meta SET value='not-an-int' WHERE key='world_revision'")
        conn.commit()
    with pytest.raises(StoreError) as exc:
        store.current_world_revision()
    assert exc.value.code is ErrorCode.STORAGE_FAILURE
