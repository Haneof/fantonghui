"""M0-018 global World Revision and atomic commit contract tests."""
from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts import (
    ObjectType,
    Observation,
    OperationRequest,
    Session,
    TemporalExtent,
    new_object_id,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError


NOW = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)


def make_obs(object_id: str, text: str, *, revision: int = 1) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(NOW - timedelta(minutes=1)),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-018-test",
        source_kind="chat",
        modality="text",
        value=text,
    )


def make_session(object_id: str, snapshot_world_revision: int) -> Session:
    return Session(
        object_id=object_id,
        subject_id="user_1",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-018-test",
        snapshot_world_revision=snapshot_world_revision,
        operation_ids=[],
        checkpoint={},
        session_state="open",
    )


def op(expected: int, key: str, operation_id: str) -> OperationRequest:
    return OperationRequest(
        operation_id=operation_id,
        operation_name="world.commit",
        expected_world_revision=expected,
        reason="M0-018 atomic world transaction test",
        idempotency_key=key,
    )


def test_w01_three_objects_share_one_global_world_revision(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    ids = [new_object_id(ObjectType.OBSERVATION) for _ in range(3)]

    result = store.commit(
        [make_obs(ids[0], "a"), make_obs(ids[1], "b"), make_obs(ids[2], "c")],
        op(0, "three-at-once", "op-three-at-once"),
    )

    assert result.world_revision == 1
    assert store.current_world_revision() == 1
    assert set(result.object_refs) == {(ids[0], 1), (ids[1], 1), (ids[2], 1)}

    with sqlite3.connect(path) as conn:
        object_rows = conn.execute(
            "SELECT object_id, revision, world_revision FROM object_revisions ORDER BY object_id"
        ).fetchall()
        world_rows = conn.execute(
            "SELECT world_revision, operation_id FROM world_commits"
        ).fetchall()

    assert len(object_rows) == 3
    assert {row[2] for row in object_rows} == {1}
    assert world_rows == [(1, "op-three-at-once")]


def test_w02_failed_mid_insert_rolls_back_the_entire_world_transaction(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    ids = [new_object_id(ObjectType.OBSERVATION) for _ in range(3)]

    # Force a genuine SQLite failure after the transaction has started writing.
    # The first object sorts before the failing object in the supplied list, so
    # this exercises rollback after at least one INSERT has executed. The storage
    # capability boundary must translate raw SQLite failure into StoreError while
    # preserving the original all-or-nothing rollback invariant.
    failing_id = ids[1]
    with sqlite3.connect(path) as conn:
        escaped = failing_id.replace("'", "''")
        conn.execute(
            f"""
            CREATE TRIGGER fail_m0_018_second_object
            BEFORE INSERT ON object_revisions
            WHEN NEW.object_id = '{escaped}'
            BEGIN
                SELECT RAISE(ABORT, 'forced M0-018 mid-transaction failure');
            END;
            """
        )
        conn.commit()

    with pytest.raises(StoreError) as exc:
        store.commit(
            [make_obs(ids[0], "first"), make_obs(ids[1], "boom"), make_obs(ids[2], "third")],
            op(0, "mid-insert-failure", "op-mid-insert-failure"),
        )
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc.value.context["reason"] == "sqlite_integrity_error"

    assert store.current_world_revision() == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM world_commits").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM object_revisions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0] == 0


def test_w03_two_concurrent_writers_from_same_snapshot_only_one_commits(tmp_path):
    path = tmp_path / "world.db"
    SQLiteWorldStore(path)
    barrier = threading.Barrier(2)
    ids = [new_object_id(ObjectType.OBSERVATION) for _ in range(2)]

    def write(index: int):
        writer = SQLiteWorldStore(path)
        barrier.wait(timeout=5)
        try:
            result = writer.commit(
                [make_obs(ids[index], f"writer-{index}")],
                op(0, f"writer-key-{index}", f"writer-op-{index}"),
            )
            return ("success", result.world_revision, ids[index])
        except StoreError as exc:
            return ("error", exc.code, ids[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [0, 1]))

    successes = [result for result in results if result[0] == "success"]
    failures = [result for result in results if result[0] == "error"]

    assert len(successes) == 1
    assert successes[0][1] == 1
    assert len(failures) == 1
    assert failures[0][1] == ErrorCode.VERSION_CONFLICT

    reopened = SQLiteWorldStore(path)
    assert reopened.current_world_revision() == 1
    payloads = reopened.list_payloads(object_type=ObjectType.OBSERVATION)
    assert len(payloads) == 1
    assert payloads[0]["object_id"] == successes[0][2]


def test_w04_session_snapshot_revision_stays_fixed_while_world_advances(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    first_ids = [new_object_id(ObjectType.OBSERVATION) for _ in range(3)]

    store.commit(
        [make_obs(first_ids[0], "a"), make_obs(first_ids[1], "b"), make_obs(first_ids[2], "c")],
        op(0, "snapshot-world", "op-snapshot-world"),
    )
    assert store.current_world_revision() == 1

    session_id = new_object_id(ObjectType.SESSION)
    store.commit(
        [make_session(session_id, snapshot_world_revision=1)],
        op(1, "session-freeze", "op-session-freeze"),
    )
    assert store.current_world_revision() == 2

    later_id = new_object_id(ObjectType.OBSERVATION)
    store.commit(
        [make_obs(later_id, "later")],
        op(2, "later-world", "op-later-world"),
    )
    assert store.current_world_revision() == 3

    session_payload = store.get_payload(session_id)
    assert session_payload["snapshot_world_revision"] == 1

    snapshot_payloads = store.list_payloads(as_of_world_revision=1)
    assert {payload["object_id"] for payload in snapshot_payloads} == set(first_ids)
    assert later_id not in {payload["object_id"] for payload in snapshot_payloads}
    assert session_id not in {payload["object_id"] for payload in snapshot_payloads}


def test_w05_failed_multi_object_commit_does_not_consume_world_revision(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    first_id = new_object_id(ObjectType.OBSERVATION)
    store.commit(
        [make_obs(first_id, "world-one")],
        op(0, "world-one", "op-world-one"),
    )
    assert store.current_world_revision() == 1

    duplicate_id = new_object_id(ObjectType.OBSERVATION)
    with pytest.raises(StoreError) as exc:
        store.commit(
            [make_obs(duplicate_id, "x"), make_obs(duplicate_id, "duplicate")],
            op(1, "failed-world-two", "op-failed-world-two"),
        )
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT
    assert store.current_world_revision() == 1

    final_id = new_object_id(ObjectType.OBSERVATION)
    result = store.commit(
        [make_obs(final_id, "real-world-two")],
        op(1, "real-world-two", "op-real-world-two"),
    )
    assert result.world_revision == 2
    assert store.current_world_revision() == 2
