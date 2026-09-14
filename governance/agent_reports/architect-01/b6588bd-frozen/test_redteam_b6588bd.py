"""New independent suite for b6588bdaaa36d9dace4f9959dda0a89a370e1674.

This is NOT the unavailable 100-case suite for 524f4d99.
Freeze this file and its SHA-256 BEFORE collection/execution. Do not edit expected
outcomes after freezing. All negative checks compare complete rows in all five
durable tables, including world_meta, even if an unexpected exception is raised.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from pydantic import BaseModel, ConfigDict

from aios_core.contracts import (
    Dependency, EvidenceSet, KnowledgeWindow, ObjectRef, Observation,
    OperationRequest, SourceRef, TemporalExtent, WorldObject,
)
from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.models import EvidenceSelector
from aios_core.storage import SQLiteWorldStore, StoreError

SHA = "b6588bdaaa36d9dace4f9959dda0a89a370e1674"
T = datetime(2026, 9, 14, 10, tzinfo=timezone.utc)
TABLES = ("world_meta", "world_commits", "object_revisions", "operations", "idempotency_records")
PLACES = ("metadata", "value", "arguments", "selector.filters")


def base(oid, **updates):
    result = dict(object_id=oid, subject_id="subject", learned_at=T,
                  recorded_at=T, created_by="architect-01")
    result.update(updates)
    return result


def obs(oid="reader", value="safe", **updates):
    return Observation(**base(oid), source_kind="test", modality="json", value=value, **updates)


def op(key="request", rev=0, **updates):
    result = dict(operation_id="op-" + key, session_id="session", operation_name="commit",
                  arguments={"a": 1, "b": 2}, expected_world_revision=rev,
                  reason="independent contract check", idempotency_key=key)
    result.update(updates)
    return OperationRequest(**result)


def request_at(place, value, *, rev=1, key="request"):
    request = op(key, rev)
    if place == "metadata":
        obj = obs(metadata={"item": value})
    elif place == "value":
        obj = obs(value=value)
    elif place == "arguments":
        obj = obs()
        request.arguments = {"item": value}
    else:
        obj = EvidenceSet(
            **base("reader"), purpose="independent selector check",
            knowledge_window=KnowledgeWindow(knowledge_cutoff=T),
            selector=EvidenceSelector(selector_type="explicit", subject_id="subject",
                time_range=TemporalExtent.unknown_time(), algorithm_version="1",
                filters={"item": value}), selection_method="explicit")
    return obj, request


def state(path):
    with sqlite3.connect(path) as conn:
        return tuple(tuple(conn.execute("SELECT * FROM " + table + " ORDER BY rowid").fetchall())
                     for table in TABLES)


def error_without_writes(store, objects, request, expected):
    before = state(store.db_path)
    caught = None
    result = None
    try:
        result = store.commit(objects, request)
    except Exception as exc:
        caught = exc
    after = state(store.db_path)
    assert after == before, "FAILED ATTEMPT CHANGED DURABLE TABLES"
    assert isinstance(caught, StoreError), (
        f"expected StoreError({expected.value}); actual exception={type(caught).__name__}; result={result!r}"
    )
    assert caught.code is expected, (caught.code, caught.context)
    return caught


def replay_without_writes(store, objects, request):
    before = state(store.db_path)
    try:
        result = store.commit(objects, request)
    finally:
        assert state(store.db_path) == before
    assert result.idempotent_replay is True
    return result


def seeded(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    store.commit([obs("target")], op("seed"))
    return store


def remove_semantic_fingerprint(path, key):
    # Simulate the explicitly supported pre-fingerprint record format. This changes
    # only the disposable test DB, before the before/after atomicity measurement.
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT result_json FROM idempotency_records WHERE idempotency_key=?", (key,)).fetchone()
        data = json.loads(row[0])
        assert data.pop("_request_fingerprint", None) is not None
        conn.execute("UPDATE idempotency_records SET result_json=? WHERE idempotency_key=?", (json.dumps(data), key))


@pytest.mark.parametrize("ref_type", [ObjectRef, SourceRef])
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("direction", ["opaque-to-typed", "typed-to-opaque"])
@pytest.mark.parametrize("legacy", [False, True])
def test_x1_semantic_identity_both_directions(tmp_path, ref_type, place, direction, legacy):
    store = seeded(tmp_path)
    typed = ref_type(object_id="target", revision=1)
    opaque = typed.model_dump()
    first, second = (opaque, typed) if direction == "opaque-to-typed" else (typed, opaque)
    obj, request = request_at(place, first)
    store.commit([obj], request)
    if legacy:
        remove_semantic_fingerprint(store.db_path, request.idempotency_key)
    changed, changed_request = request_at(place, second)
    error_without_writes(SQLiteWorldStore(store.db_path), [changed], changed_request, ErrorCode.IDEMPOTENCY_CONFLICT)


@pytest.mark.parametrize("ref_type", [ObjectRef, SourceRef])
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("legacy", [False, True])
def test_x1_exact_typed_restart(tmp_path, ref_type, place, legacy):
    store = seeded(tmp_path)
    obj, request = request_at(place, ref_type(object_id="target", revision=1))
    store.commit([obj], request)
    if legacy:
        remove_semantic_fingerprint(store.db_path, request.idempotency_key)
        error_without_writes(SQLiteWorldStore(store.db_path), [obj], request, ErrorCode.IDEMPOTENCY_CONFLICT)
    else:
        replay_without_writes(SQLiteWorldStore(store.db_path), [obj], request)


@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("shaped", [False, True])
def test_legacy_json_exact_replay(tmp_path, place, shaped):
    store = seeded(tmp_path)
    value = {"object_id": "target", "revision": 1} if shaped else {"label": [1, "x", None]}
    obj, request = request_at(place, value)
    store.commit([obj], request)
    remove_semantic_fingerprint(store.db_path, request.idempotency_key)
    replay_without_writes(SQLiteWorldStore(store.db_path), [obj], request)


@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("marker", [
    ["$aios-ref", "object", "target", 1],
    {"$aios-ref": ["object", "target", 1]},
    ["$mapping", [["object_id", "target"], ["revision", 1]]],
])
def test_x1_marker_shaped_values_remain_distinct(tmp_path, place, marker):
    store = seeded(tmp_path)
    obj, request = request_at(place, marker)
    store.commit([obj], request)
    changed, changed_request = request_at(place, ObjectRef(object_id="target", revision=1))
    error_without_writes(store, [changed], changed_request, ErrorCode.IDEMPOTENCY_CONFLICT)


def bad_value(kind):
    if kind == "surrogate": return "\ud800"
    if kind == "bytes": return b"\xff\xfe"
    if kind == "huge-int": return 10 ** 5000
    if kind == "nan": return float("nan")
    if kind == "infinity": return float("inf")
    if kind == "unsupported": return object()
    if kind == "non-string-key": return {1: "integer", "1": "string"}
    if kind == "cycle":
        value = []; value.append(value); return value
    value = "leaf"
    for _ in range(1500): value = [value]
    return value


@pytest.mark.parametrize("kind", ["surrogate", "bytes", "huge-int", "nan", "infinity", "unsupported", "non-string-key", "cycle", "depth"])
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("retry", [False, True])
def test_x2_protocol_and_five_table_atomicity(tmp_path, kind, place, retry):
    store = seeded(tmp_path)
    original, request = request_at(place, "safe")
    if retry: store.commit([original], request)
    obj, dirty = request_at(place, bad_value(kind))
    error_without_writes(SQLiteWorldStore(store.db_path), [obj], dirty,
                         ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


class ExtraBox(BaseModel):
    model_config = ConfigDict(extra="allow")
    value: str


@pytest.mark.parametrize("place", PLACES)
def test_x3_nested_extras_preserved_and_affect_identity(tmp_path, place):
    store = seeded(tmp_path)
    first = ExtraBox(value="outer", inner=ExtraBox(value="inner", extra_data="one"))
    second = ExtraBox(value="outer", inner=ExtraBox(value="inner", extra_data="two"))
    obj, request = request_at(place, first)
    store.commit([obj], request)
    payload = (json.loads(store.operation_record(request.operation_id)["arguments_json"])
               if place == "arguments" else store.get_payload("reader"))
    if place in ("metadata", "selector.filters"):
        payload = payload["metadata"] if place == "metadata" else payload["selector"]["filters"]
    nested = payload["value"] if place == "value" else payload["item"]
    assert nested == {"value": "outer", "inner": {"value": "inner", "extra_data": "one"}}
    altered, changed = request_at(place, second)
    error_without_writes(store, [altered], changed, ErrorCode.IDEMPOTENCY_CONFLICT)


@pytest.mark.parametrize("target", ["object", "operation", "selector", "ref"])
@pytest.mark.parametrize("method", ["model-copy", "pydantic-extra", "shadow-extra"])
@pytest.mark.parametrize("retry", [False, True])
def test_x3_dirty_extra_never_silently_erased(tmp_path, target, method, retry):
    store = seeded(tmp_path)
    obj, request = request_at("selector.filters" if target == "selector" else "metadata",
                              ObjectRef(object_id="target", revision=1) if target == "ref" else "safe")
    if retry: store.commit([obj], request)
    node = {"object": obj, "operation": request, "selector": getattr(obj, "selector", None),
            "ref": obj.metadata.get("item")}[target]
    name = next(iter(type(node).model_fields)) if method == "shadow-extra" else "unrecognized"
    if method == "model-copy":
        dirty = node.model_copy(update={name: "must-not-disappear"})
    else:
        dirty = node.model_copy(deep=True)
        object.__setattr__(dirty, "__pydantic_extra__", {name: "must-not-disappear"})
    if target == "object": obj = dirty
    elif target == "operation": request = dirty
    elif target == "selector": obj.selector = dirty
    else: obj.metadata["item"] = dirty
    error_without_writes(store, [obj], request,
                         ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize("ref_type", [ObjectRef, SourceRef])
@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("revision", ["1", "bad", -1, None])
@pytest.mark.parametrize("retry", [False, True])
def test_x4_dirty_revision_revalidation(tmp_path, ref_type, place, revision, retry):
    store = seeded(tmp_path)
    canonical_revision = 1 if revision == "1" else revision
    original, request = request_at(place, ref_type(object_id="target", revision=1))
    if retry: store.commit([original], request)
    dirty_ref = ref_type(object_id="target", revision=1).model_copy(update={"revision": revision})
    obj, dirty_request = request_at(place, dirty_ref)
    if revision == "1":
        if retry: replay_without_writes(store, [obj], dirty_request)
        else:
            store.commit([obj], dirty_request)
            canonical, clean_request = request_at(place, ref_type(object_id="target", revision=canonical_revision))
            replay_without_writes(SQLiteWorldStore(store.db_path), [canonical], clean_request)
    elif revision is None and not retry:
        store.commit([obj], dirty_request)
        replay_without_writes(SQLiteWorldStore(store.db_path), [obj], dirty_request)
    else:
        error_without_writes(store, [obj], dirty_request,
                             ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize("field,value", [
    ("idempotency_key", b"request"), ("idempotency_key", ["request"]),
    ("idempotency_key", None), ("idempotency_key", " "),
    ("expected_world_revision", "1"), ("expected_world_revision", "bad"),
    ("expected_world_revision", -1), ("operation_id", b"op-request"),
    ("operation_id", []), ("operation_id", None), ("operation_id", " "),
])
@pytest.mark.parametrize("retry", [False, True])
def test_dirty_operation_routing(tmp_path, field, value, retry):
    store = seeded(tmp_path)
    obj, request = request_at("value", "safe")
    if retry: store.commit([obj], request)
    dirty = request.model_copy(update={field: value})
    valid = isinstance(value, bytes) or (field == "expected_world_revision" and value == "1")
    if valid:
        if retry: replay_without_writes(store, [obj], dirty)
        else:
            store.commit([obj], dirty)
            replay_without_writes(SQLiteWorldStore(store.db_path), [obj], request)
    else:
        # Invalid or changed routing key cannot identify the old receipt.
        expected = ErrorCode.IDEMPOTENCY_CONFLICT if retry and field != "idempotency_key" else ErrorCode.INVALID_ARGUMENT
        error_without_writes(store, [obj], dirty, expected)


@pytest.mark.parametrize("field,value", [
    ("operation_id", "other"), ("session_id", "other"), ("operation_name", "other"),
    ("arguments", {"a": 2}), ("expected_world_revision", 90), ("reason", "changed"),
])
def test_b1_changed_request_conflicts(tmp_path, field, value):
    store = seeded(tmp_path); obj = obs(); request = op(rev=1)
    store.commit([obj], request)
    error_without_writes(store, [obj], request.model_copy(update={field: value}), ErrorCode.IDEMPOTENCY_CONFLICT)


def test_b1_object_order_and_argument_key_order(tmp_path):
    store = seeded(tmp_path); objects = [obs("a"), obs("b")]; request = op(rev=1)
    store.commit(objects, request)
    replay_without_writes(SQLiteWorldStore(store.db_path), list(reversed(objects)),
                          request.model_copy(update={"arguments": {"b": 2, "a": 1}}))


@pytest.mark.parametrize("object_type", [ObjectType.DEPENDENCY, ObjectType.EVIDENCE_SET, ObjectType.CLAIM])
def test_b10_canonical_subtype_required(tmp_path, object_type):
    store = SQLiteWorldStore(tmp_path / "world.db")
    bare = WorldObject(**base("bare"), object_type=object_type)
    error_without_writes(store, [bare], op(), ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize("ref_type", [ObjectRef, SourceRef])
@pytest.mark.parametrize("revision", [None, 1])
def test_b4_self_reference_rejected(tmp_path, ref_type, revision):
    store = SQLiteWorldStore(tmp_path / "world.db")
    obj = obs(metadata={"ref": ref_type(object_id="reader", revision=revision)})
    error_without_writes(store, [obj], op(), ErrorCode.DEPENDENCY_INVALID)


def test_historical_self_and_distinct_mutual_references(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    a = obs("a", metadata={"ref": ObjectRef(object_id="b")})
    b = obs("b", metadata={"ref": SourceRef(object_id="a")})
    store.commit([a, b], op())
    second = obs("a", metadata={"ref": ObjectRef(object_id="a", revision=1)}).model_copy(update={"revision": 2})
    store.commit([second], op("history", 1))
    assert store.current_world_revision() == 2


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("seconds", [-1, 0, 1])
def test_evidence_frozen_cutoff_intersection(tmp_path, pending, seconds):
    store = SQLiteWorldStore(tmp_path / "world.db")
    at = T + timedelta(seconds=seconds)
    target = obs("target").model_copy(update={"learned_at": at, "recorded_at": at})
    evidence = EvidenceSet(**base("evidence", learned_at=T+timedelta(hours=1), recorded_at=T+timedelta(hours=1)),
        purpose="cutoff", knowledge_window=KnowledgeWindow(knowledge_cutoff=T),
        member_refs=[ObjectRef(object_id="target", revision=1)], selection_method="explicit")
    if not pending: store.commit([target], op("seed"))
    objects = [target, evidence] if pending else [evidence]
    request = op(rev=0 if pending else 1)
    if seconds > 0: error_without_writes(store, objects, request, ErrorCode.NOT_FOUND)
    else: assert store.commit(objects, request).world_revision == (1 if pending else 2)


def test_b6_coercible_nested_value_restart(tmp_path):
    store = seeded(tmp_path)
    evidence = EvidenceSet(**base("evidence"), purpose="normalization",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=T),
        member_refs=[ObjectRef(object_id="target", revision=1)], selection_method="explicit")
    evidence.coverage.observed_count = "1"
    request = op(rev=1); store.commit([evidence], request)
    assert store.get_payload("evidence")["coverage"]["observed_count"] == 1
    replay_without_writes(SQLiteWorldStore(store.db_path), [evidence], request)


def test_b6_unordered_cross_process_identity(tmp_path):
    code = '''import sys
from datetime import datetime,timezone
from aios_core.contracts import Observation,OperationRequest
from aios_core.storage import SQLiteWorldStore
t=datetime(2026,9,14,10,tzinfo=timezone.utc)
o=Observation(object_id='o',subject_id='s',learned_at=t,recorded_at=t,created_by='audit',source_kind='x',modality='json',value={'labels':{'alpha','beta','gamma','delta'}})
r=OperationRequest(operation_id='op',operation_name='commit',expected_world_revision=0,reason='audit',idempotency_key='key',arguments={'labels':{'alpha','beta','gamma','delta'}})
print(SQLiteWorldStore(sys.argv[1]).commit([o],r).idempotent_replay)
'''
    path = tmp_path / "world.db"
    first = subprocess.run([sys.executable, "-c", code, str(path)], env=os.environ | {"PYTHONHASHSEED": "1"}, capture_output=True, text=True, check=True)
    before = state(path)
    second = subprocess.run([sys.executable, "-c", code, str(path)], env=os.environ | {"PYTHONHASHSEED": "2"}, capture_output=True, text=True, check=True)
    assert state(path) == before
    assert first.stdout.strip() == "False" and second.stdout.strip() == "True"


def test_mid_insert_rollback_and_recovery(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("CREATE TRIGGER reject_second BEFORE INSERT ON object_revisions WHEN NEW.object_id='b' BEGIN SELECT RAISE(ABORT,'independent failure'); END")
    error_without_writes(store, [obs("a"), obs("b")], op(), ErrorCode.STORAGE_FAILURE)
    with sqlite3.connect(store.db_path) as conn: conn.execute("DROP TRIGGER reject_second")
    assert store.commit([obs("a"), obs("b")], op()).world_revision == 1


@pytest.mark.parametrize("same_key", [False, True])
def test_competing_writers_one_success(tmp_path, same_key):
    path = tmp_path / "world.db"
    stores = [SQLiteWorldStore(path), SQLiteWorldStore(path)]
    gate = Barrier(2)
    def run(i):
        gate.wait()
        request = op("shared" if same_key else str(i), operation_id="op-"+str(i))
        try: return stores[i].commit([obs(str(i))], request)
        except StoreError as exc: return exc
    with ThreadPoolExecutor(max_workers=2) as executor: results = list(executor.map(run, range(2)))
    failures = [result for result in results if isinstance(result, StoreError)]
    assert len(failures) == 1
    assert failures[0].code is (ErrorCode.IDEMPOTENCY_CONFLICT if same_key else ErrorCode.VERSION_CONFLICT)
    snapshot = state(path)
    assert snapshot[0] == (("world_revision", "1"),)
    assert all(len(rows) == 1 for rows in snapshot[1:])


def test_stale_world_rejects_new_request_without_writes(tmp_path):
    store = seeded(tmp_path)
    error_without_writes(store, [obs()], op(rev=0), ErrorCode.VERSION_CONFLICT)


def test_two_lens_history(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    future = obs("future").model_copy(update={"learned_at": T+timedelta(days=1), "recorded_at": T+timedelta(days=1)})
    store.commit([future], op("first"))
    store.commit([obs("backfill")], op("second", 1))
    before = state(store.db_path)
    assert store.get_payload("future", as_of_world_revision=1)
    assert store.get_payload("backfill", knowledge_cutoff=T)
    for oid in ("future", "backfill"):
        with pytest.raises(StoreError) as caught:
            store.get_payload(oid, as_of_world_revision=1, knowledge_cutoff=T)
        assert caught.value.code is ErrorCode.NOT_FOUND
        assert state(store.db_path) == before
