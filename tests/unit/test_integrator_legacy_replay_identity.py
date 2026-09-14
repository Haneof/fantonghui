from __future__ import annotations

import json
import sqlite3

import pytest

from aios_core.contracts import ObjectRef
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError
from tests.unit.test_m0_gate_sixth_followup import counts, obs, op


def _drop_semantic_fingerprint(path, key: str) -> None:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT result_json FROM idempotency_records WHERE idempotency_key=?",
            (key,),
        ).fetchone()
        payload = json.loads(row[0])
        payload.pop("_request_fingerprint", None)
        conn.execute(
            "UPDATE idempotency_records SET result_json=? WHERE idempotency_key=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), key),
        )
        conn.commit()


def test_legacy_row_can_still_replay_exact_json_only_request(tmp_path):
    path = tmp_path / "legacy-exact.db"
    store = SQLiteWorldStore(path)
    request = op("legacy-exact")
    obj = obs("reader", metadata={"opaque": {"object_id": "missing", "revision": 1}})
    store.commit([obj], request)
    _drop_semantic_fingerprint(path, request.idempotency_key)
    before = counts(path)

    replay = SQLiteWorldStore(path).commit([obj], request)

    assert replay.idempotent_replay is True
    assert counts(path) == before


def test_legacy_row_must_not_guess_typed_ref_equals_opaque_dict(tmp_path):
    path = tmp_path / "legacy-typed.db"
    store = SQLiteWorldStore(path)
    request = op("legacy-typed")
    opaque = obs("reader", metadata={"ref": {"object_id": "missing", "revision": 1}})
    store.commit([opaque], request)
    _drop_semantic_fingerprint(path, request.idempotency_key)
    before = counts(path)

    typed = obs("reader", metadata={"ref": ObjectRef(object_id="missing", revision=1)})
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([typed], request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(path) == before


def test_legacy_row_must_not_guess_typed_ref_in_arguments_equals_opaque_dict(tmp_path):
    path = tmp_path / "legacy-args.db"
    store = SQLiteWorldStore(path)
    request = op(
        "legacy-args",
        arguments={"ref": {"object_id": "missing", "revision": 1}},
    )
    obj = obs("reader")
    store.commit([obj], request)
    _drop_semantic_fingerprint(path, request.idempotency_key)
    before = counts(path)

    typed_request = request.model_copy(
        update={"arguments": {"ref": ObjectRef(object_id="missing", revision=1)}}
    )
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([obj], typed_request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(path) == before
