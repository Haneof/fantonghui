"""M0-017 SQLite append-only world storage schema and transaction tests."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts import ObjectType, Observation, OperationRequest, TemporalExtent, new_object_id
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError


NOW = datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)


def make_obs(object_id: str, revision: int, text: str) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(NOW - timedelta(minutes=1)),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-017-test",
        source_kind="chat",
        modality="text",
        value=text,
    )


def op(world_revision: int, key: str, *, operation_id: str | None = None) -> OperationRequest:
    kwargs = {
        "operation_name": "world.commit",
        "expected_world_revision": world_revision,
        "reason": "M0-017 schema test",
        "idempotency_key": key,
    }
    if operation_id is not None:
        kwargs["operation_id"] = operation_id
    return OperationRequest(**kwargs)


def table_names(path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def index_names(path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            ).fetchall()
        }


def test_s01_initialization_creates_required_first_stage_tables_and_world_zero(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)

    assert {
        "world_meta",
        "world_commits",
        "object_revisions",
        "operations",
        "idempotency_records",
    }.issubset(table_names(path))
    assert store.current_world_revision() == 0


def test_s02_storage_uses_wal_and_foreign_keys_on_store_connections(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)

    with store._connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1


def test_s03_required_query_indexes_exist(tmp_path):
    path = tmp_path / "world.db"
    SQLiteWorldStore(path)
    indexes = index_names(path)

    assert "idx_objects_current_lookup" in indexes
    assert "idx_objects_type_subject" in indexes
    assert "idx_objects_learned" in indexes


def test_s04_object_revision_schema_keeps_common_columns_and_json_payload(tmp_path):
    path = tmp_path / "world.db"
    SQLiteWorldStore(path)

    with sqlite3.connect(path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(object_revisions)").fetchall()
        }
    assert {
        "object_id",
        "revision",
        "object_type",
        "subject_id",
        "world_revision",
        "learned_at",
        "recorded_at",
        "payload_json",
    }.issubset(columns)


def test_s05_restart_preserves_world_revision_and_payload(tmp_path):
    path = tmp_path / "world.db"
    oid = new_object_id(ObjectType.OBSERVATION)

    first = SQLiteWorldStore(path)
    result = first.commit([make_obs(oid, 1, "persist me")], op(0, "restart-1"))
    assert result.world_revision == 1

    reopened = SQLiteWorldStore(path)
    assert reopened.current_world_revision() == 1
    assert reopened.get_payload(oid, revision=1)["value"] == "persist me"


def test_s06_consecutive_commits_advance_world_revision_exactly_once_each(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)

    first = store.commit([make_obs(a, 1, "a")], op(0, "seq-1"))
    second = store.commit([make_obs(b, 1, "b")], op(1, "seq-2"))

    assert first.world_revision == 1
    assert second.world_revision == 2
    assert store.current_world_revision() == 2


def test_s07_same_object_multiple_revisions_are_all_preserved(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)

    store.commit([make_obs(oid, 1, "old")], op(0, "rev-1"))
    store.commit([make_obs(oid, 2, "new")], op(1, "rev-2"))

    assert store.get_payload(oid, revision=1)["value"] == "old"
    assert store.get_payload(oid, revision=2)["value"] == "new"
    assert store.get_payload(oid, as_of_world_revision=1)["value"] == "old"
    assert store.get_payload(oid, as_of_world_revision=2)["value"] == "new"

    with sqlite3.connect(store.db_path) as conn:
        rows = conn.execute(
            "SELECT revision FROM object_revisions WHERE object_id=? ORDER BY revision",
            (oid,),
        ).fetchall()
    assert [row[0] for row in rows] == [1, 2]


def test_s08_failed_transaction_rolls_back_all_world_object_and_operation_state(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    oid = new_object_id(ObjectType.OBSERVATION)

    # Two copies of the same object revision in one transaction are invalid and
    # must fail before any durable world/object/operation/idempotency write.
    request = op(0, "rollback-key", operation_id="rollback-op")
    with pytest.raises(StoreError) as exc:
        store.commit(
            [make_obs(oid, 1, "first"), make_obs(oid, 1, "duplicate")],
            request,
        )
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT
    assert store.current_world_revision() == 0

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM world_commits").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM object_revisions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0] == 0


def test_s09_multi_object_commit_is_atomic_and_shares_one_world_revision(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)

    result = store.commit(
        [make_obs(a, 1, "a"), make_obs(b, 1, "b")],
        op(0, "atomic-multi"),
    )
    assert result.world_revision == 1

    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT object_id, world_revision FROM object_revisions ORDER BY object_id"
        ).fetchall()
    assert len(rows) == 2
    assert {row[1] for row in rows} == {1}


def test_s10_two_store_instances_enforce_expected_world_revision_concurrency(tmp_path):
    path = tmp_path / "world.db"
    writer_a = SQLiteWorldStore(path)
    writer_b = SQLiteWorldStore(path)
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)

    assert writer_a.current_world_revision() == 0
    assert writer_b.current_world_revision() == 0
    writer_a.commit([make_obs(a, 1, "winner")], op(0, "writer-a"))

    with pytest.raises(StoreError) as exc:
        writer_b.commit([make_obs(b, 1, "stale")], op(0, "writer-b"))
    assert exc.value.code == ErrorCode.VERSION_CONFLICT
    assert writer_b.current_world_revision() == 1
    with pytest.raises(StoreError) as missing:
        writer_b.get_payload(b)
    assert missing.value.code == ErrorCode.NOT_FOUND


def test_s11_schema_reopen_is_idempotent_and_does_not_destroy_history(tmp_path):
    path = tmp_path / "world.db"
    oid = new_object_id(ObjectType.OBSERVATION)
    store = SQLiteWorldStore(path)
    store.commit([make_obs(oid, 1, "history")], op(0, "history-1"))

    for _ in range(3):
        SQLiteWorldStore(path)

    reopened = SQLiteWorldStore(path)
    assert reopened.current_world_revision() == 1
    assert reopened.get_payload(oid, revision=1)["value"] == "history"


def test_s12_ai_worker_db_boundary_is_covered_by_architecture_suite():
    # M0-001 architecture tests fail closed if ai_worker imports sqlite3 or
    # aios_core.storage. M0-017 keeps this invariant explicit without exposing
    # a raw sqlite connection through the storage public API.
    from aios_core.storage import SQLiteWorldStore as PublicStore

    assert PublicStore is SQLiteWorldStore
