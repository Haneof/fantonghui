"""Independent adversarial evidence. Production code is not modified.
Run: PYTHONPATH=<exact-source>/src python -m pytest -q -o addopts='' test_m0_gate_sixth_followup.py
Failures are assertions of the frozen contract, not tests asserting that bugs exist.
"""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from aios_core.contracts import (
    Observation,
    OperationRequest,
    ObjectRef,
    SourceRef,
    EvidenceSet,
    KnowledgeWindow,
    Relation,
    Dependency,
    Task,
    EventAnchor,
)
from aios_core.contracts.models import EvidenceSelector
from aios_core.contracts.time import TemporalExtent
from aios_core.contracts.enums import ErrorCode, TaskState, TaskType, EventStatus
from aios_core.storage import SQLiteWorldStore, StoreError
from aios_core.storage.idempotency import normalize_world_object_for_persistence
from aios_core.services.state_machines import validate_task_revision_transition

T = datetime(2026, 9, 14, 9, tzinfo=timezone.utc)


def base(oid, **kw):
    d = dict(
        object_id=oid,
        subject_id="audit-subject",
        learned_at=T,
        recorded_at=T,
        created_by="auditor-e-02",
    )
    d.update(kw)
    return d


def obs(oid="o", **kw):
    return Observation(**base(oid, source_kind="test", modality="json", **kw))


def op(key="k", rev=0, **kw):
    d = dict(
        operation_id="op-" + key,
        operation_name="world.commit",
        expected_world_revision=rev,
        idempotency_key=key,
        reason="independent audit",
    )
    d.update(kw)
    return OperationRequest(**d)


def counts(path):
    with sqlite3.connect(path) as conn:
        return (
            int(
                conn.execute(
                    "SELECT value FROM world_meta WHERE key='world_revision'"
                ).fetchone()[0]
            ),
        ) + tuple(
            conn.execute("SELECT count(*) FROM " + name).fetchone()[0]
            for name in (
                "world_commits",
                "object_revisions",
                "operations",
                "idempotency_records",
            )
        )


@pytest.mark.parametrize(
    "kind", ["missing", "source-missing", "floating-self", "pinned-self"]
)
def test_typed_refs_are_not_erased_before_validation(tmp_path, kind):
    s = SQLiteWorldStore(tmp_path / "world.db")
    ref = (
        SourceRef(object_id="missing", revision=1)
        if kind == "source-missing"
        else ObjectRef(
            object_id="missing" if kind == "missing" else "o",
            revision=None if kind == "floating-self" else 1,
        )
    )
    obj = obs(metadata={"nested": [{"typed": ref}]})
    assert s._collect_refs(obj) == [
        ref
    ]  # Actual typed ref, NOT an input pseudo-ref dict.
    with pytest.raises(StoreError) as exc:
        s.commit([obj], op())
    assert exc.value.code is (
        ErrorCode.NOT_FOUND if "missing" in kind else ErrorCode.DEPENDENCY_INVALID
    )
    assert counts(s.db_path) == (0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "placement", ["metadata", "selector.filters", "observation.value"]
)
def test_typed_ref_cutoff_cannot_be_laundered_by_normalization(tmp_path, placement):
    s = SQLiteWorldStore(tmp_path / "world.db")
    late = obs(
        "late", learned_at=T + timedelta(hours=1), recorded_at=T + timedelta(hours=1)
    )
    s.commit([obs("early"), late], op())
    ref = ObjectRef(object_id="late", revision=1)
    if placement == "observation.value":
        obj = obs(
            "reader", value={"typed": ref}
        )  # learned at 09:00, target learned at 10:00
    else:
        obj = EvidenceSet(
            **base(
                "ev",
                learned_at=T + timedelta(hours=1),
                recorded_at=T + timedelta(hours=1),
            ),
            purpose="frozen evidence",
            knowledge_window=KnowledgeWindow(knowledge_cutoff=T, world_revision=1),
            member_refs=[ObjectRef(object_id="early", revision=1)],
            selection_method="explicit",
        )
        if placement == "metadata":
            obj.metadata["typed"] = ref
        else:
            obj.selector = EvidenceSelector(
                selector_type="test",
                subject_id="audit-subject",
                time_range=TemporalExtent.unknown_time(),
                algorithm_version="v1",
                filters={"typed": ref},
            )
    assert ref in s._collect_refs(obj)
    before = counts(s.db_path)
    with pytest.raises(StoreError) as exc:
        s.commit([obj], op("second", 1))
    assert exc.value.code is ErrorCode.NOT_FOUND
    assert counts(s.db_path) == before


@pytest.mark.parametrize("slot", ["object", "arguments"])
@pytest.mark.parametrize("retry", [False, True])
def test_non_utf8_bytes_get_protocol_error_and_zero_writes(tmp_path, slot, retry):
    s = SQLiteWorldStore(tmp_path / "world.db")
    obj, request = obs(value="ok"), op(arguments={"value": "ok"})
    if retry:
        s.commit([obj], request)
    before = counts(s.db_path)
    if slot == "object":
        obj.value = b"\xff"
    else:
        request.arguments["value"] = b"\xff"
    # Both live model construction and frozen-model revalidation accept this value.
    if slot == "object":
        assert normalize_world_object_for_persistence(obj).value == b"\xff"
    try:
        with pytest.raises(StoreError) as exc:
            s.commit([obj], request)
        assert exc.value.code is (
            ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT
        )
    finally:
        assert counts(s.db_path) == before


# Controls explicitly keep deferred plain pseudo-ref dictionaries distinct from typed refs.
def test_opaque_dictionary_is_not_promoted_to_typed_ref(tmp_path):
    s = SQLiteWorldStore(tmp_path / "w.db")
    s.commit([obs(metadata={"opaque": {"object_id": "missing", "revision": 1}})], op())
    assert s.current_world_revision() == 1


def test_replay_order_restart_different_request_and_dirty_operation(tmp_path):
    path = tmp_path / "w.db"
    s = SQLiteWorldStore(path)
    obj = obs()
    request = op()
    s.commit([obj], request)
    s.commit([obs("other")], op("other", 1))
    s = SQLiteWorldStore(path)
    assert s.commit([obj], request).idempotent_replay  # expected=0, world=2
    bad = request.model_copy(deep=True)
    bad.arguments["changed"] = True
    with pytest.raises(StoreError) as exc:
        s.commit([obj], bad)
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    dirty = op("dirty", 2)
    with pytest.raises(ValidationError):
        dirty.reason = " "
    before = counts(path)
    with pytest.raises(StoreError) as exc:
        s.commit([obs("dirty")], dirty)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(path) == before


@pytest.mark.parametrize(
    "table",
    [
        "world_commits",
        "object_revisions",
        "operations",
        "idempotency_records",
        "world_meta",
    ],
)
def test_fault_rollback_retry_all_durable_tables(tmp_path, table):
    path = tmp_path / "w.db"
    s = SQLiteWorldStore(path)
    event = "UPDATE" if table == "world_meta" else "INSERT"
    condition = "WHEN NEW.object_id='second'" if table == "object_revisions" else ""
    with sqlite3.connect(path) as c:
        c.execute(
            f"CREATE TRIGGER injected BEFORE {event} ON {table} {condition} BEGIN SELECT RAISE(ABORT,'busy_locked_but_not_lock'); END"
        )
    before = counts(path)
    objects = [obs("first"), obs("second")]
    request = op()
    with pytest.raises(StoreError) as exc:
        s.commit(objects, request)
    assert exc.value.code is ErrorCode.STORAGE_FAILURE
    assert counts(path) == before
    with sqlite3.connect(path) as c:
        c.execute("DROP TRIGGER injected")
    assert s.commit(objects, request).world_revision == 1
    assert s.commit(objects, request).idempotent_replay
    assert counts(path) == (1, 1, 2, 1, 1)


def test_real_lock_and_nonlock_code_classification(tmp_path):
    path = tmp_path / "w.db"
    s = SQLiteWorldStore(path)
    s.SQLITE_BUSY_TIMEOUT_MS = 1
    with sqlite3.connect(path) as c:
        c.execute("BEGIN IMMEDIATE")
        with pytest.raises(StoreError) as exc:
            s.commit([obs()], op())
        assert exc.value.code is ErrorCode.VERSION_CONFLICT
        assert exc.value.context["reason"] == "storage_busy"
        assert exc.value.context["sqlite_errorcode"] & 255 in (
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_LOCKED,
        )
    with s._connection() as c:
        c.execute("DROP TABLE operations")
        c.commit()
    with pytest.raises(StoreError) as exc:
        s.operation_record("busy_locked")
    assert exc.value.code is ErrorCode.STORAGE_FAILURE
    assert exc.value.context["sqlite_errorcode"] & 255 == sqlite3.SQLITE_ERROR


def test_formal_refs_same_tx_historical_self_and_relation_cycle(tmp_path):
    path = tmp_path / "w.db"
    s = SQLiteWorldStore(path)
    a = obs("a", source_refs=[SourceRef(object_id="b", revision=1)])
    b = obs("b", source_refs=[SourceRef(object_id="a", revision=1)])
    s.commit([a, b], op())
    a2 = obs("a", revision=2, source_refs=[SourceRef(object_id="a", revision=1)])
    s.commit([a2], op("a2", 1))
    for rev in (None, 3):
        with pytest.raises(StoreError) as exc:
            s.commit(
                [
                    obs(
                        "a",
                        revision=3,
                        source_refs=[SourceRef(object_id="a", revision=rev)],
                    )
                ],
                op("self", 2),
            )
        assert exc.value.code is ErrorCode.DEPENDENCY_INVALID
    r1 = Relation(
        **base("r1"),
        left=ObjectRef(object_id="a", revision=2),
        right=ObjectRef(object_id="b", revision=1),
        relation_type="related",
        confidence=0.5,
    )
    r2 = Relation(
        **base("r2"),
        left=r1.right,
        right=r1.left,
        relation_type="related",
        confidence=0.5,
    )
    s.commit([r1, r2], op("relation", 2))
    d1 = Dependency(
        **base("d1"),
        dependent_ref=r1.left,
        dependency_ref=r1.right,
        dependency_type="proof",
    )
    d2 = Dependency(
        **base("d2"),
        dependent_ref=r1.right,
        dependency_ref=r1.left,
        dependency_type="proof",
    )
    before = counts(path)
    with pytest.raises(StoreError) as exc:
        s.commit([d1, d2], op("cycle", 3))
    assert exc.value.code is ErrorCode.DEPENDENCY_INVALID
    assert counts(path) == before


@pytest.mark.parametrize(
    "field",
    [
        "member_refs",
        "support_refs",
        "counter_refs",
        "context_refs",
        "selector.dimension_refs",
    ],
)
def test_formal_evidence_refs_obey_cutoff(tmp_path, field):
    s = SQLiteWorldStore(tmp_path / "w.db")
    early, late = (
        obs("early"),
        obs(
            "late",
            learned_at=T + timedelta(hours=1),
            recorded_at=T + timedelta(hours=1),
        ),
    )
    ev = EvidenceSet(
        **base("ev", learned_at=late.learned_at, recorded_at=late.recorded_at),
        purpose="cutoff",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=T),
        member_refs=[ObjectRef(object_id="early", revision=1)],
        selection_method="explicit",
    )
    ref = ObjectRef(object_id="late", revision=1)
    if field == "selector.dimension_refs":
        ev.selector = EvidenceSelector(
            selector_type="test",
            subject_id="audit-subject",
            time_range=TemporalExtent.unknown_time(),
            dimension_refs=[ref],
            algorithm_version="1",
        )
    else:
        setattr(ev, field, [ref])
    with pytest.raises(StoreError) as exc:
        s.commit([early, late, ev], op())
    assert exc.value.code is ErrorCode.NOT_FOUND
    # Equal instant, different timezone, same-transaction target must work.
    late.learned_at = T.astimezone(timezone(timedelta(hours=8)))
    assert s.commit([early, late, ev], op()).world_revision == 1


def test_dual_lens_and_subject_filter(tmp_path):
    s = SQLiteWorldStore(tmp_path / "w.db")
    s.commit([obs("x")], op())
    s.commit(
        [
            obs(
                "x",
                revision=2,
                subject_id="other",
                learned_at=T + timedelta(hours=1),
                recorded_at=T + timedelta(hours=1),
            )
        ],
        op("x2", 1),
    )
    assert (
        s.get_payload("x", as_of_world_revision=2, knowledge_cutoff=T)["revision"] == 1
    )
    assert (
        s.get_payload(
            "x", as_of_world_revision=1, knowledge_cutoff=T + timedelta(hours=2)
        )["revision"]
        == 1
    )
    assert s.get_payload("x", as_of_world_revision=2)["revision"] == 2
    assert (
        s.list_payloads(
            subject_id="audit-subject",
            as_of_world_revision=2,
            knowledge_cutoff=T + timedelta(hours=2),
        )
        == []
    )


def test_same_snapshot_concurrent_writers_and_same_key(tmp_path):
    path = tmp_path / "w.db"
    s = SQLiteWorldStore(path)

    def write(i):
        try:
            return s.commit([obs(str(i))], op(str(i))).world_revision
        except StoreError as e:
            return e.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, [1, 2]))
    assert sorted(str(x) for x in results) == sorted(
        [str(1), str(ErrorCode.VERSION_CONFLICT)]
    )
    s2 = SQLiteWorldStore(tmp_path / "same.db")

    def same(i):
        try:
            return s2.commit([obs(str(i))], op()).world_revision
        except StoreError as e:
            return e.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(same, [1, 2]))
    assert sorted(str(x) for x in results) == sorted(
        [str(1), str(ErrorCode.IDEMPOTENCY_CONFLICT)]
    )


def test_nested_unordered_cross_process_and_ordered_separation(tmp_path):
    script = """
import json,sys
from test_m0_gate_sixth_followup import *
s=SQLiteWorldStore(sys.argv[1])
v={'nested':[frozenset({('alpha','beta'),('gamma','delta')}),{'set':set(['a','b','c','d'])}], 'ordered':['a','b']}
r=s.commit([obs(value=v)],op(arguments=v))
print(json.dumps(r.model_dump()))
"""
    results = []
    for seed in ("1", "17", "31337"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path(__file__).parent), os.environ["PYTHONPATH"]]
        )
        results.append(
            json.loads(
                subprocess.check_output(
                    [sys.executable, "-c", script, str(tmp_path / "w.db")],
                    env=env,
                    text=True,
                )
            )
        )
    assert [r["idempotent_replay"] for r in results] == [False, True, True]
    s = SQLiteWorldStore(tmp_path / "ordered.db")
    s.commit([obs(value=["a", "b"])], op())
    with pytest.raises(StoreError) as exc:
        s.commit([obs(value=["b", "a"])], op())
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
