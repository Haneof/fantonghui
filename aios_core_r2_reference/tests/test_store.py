from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts import (
    Claim,
    ClaimType,
    KnowledgeState,
    ObjectType,
    Observation,
    OperationRequest,
    TemporalExtent,
    new_object_id,
)
from aios_core.storage import SQLiteWorldStore, StoreError
from aios_core.contracts.enums import ErrorCode

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def make_obs(object_id: str, revision: int, text: str, learned_at=NOW):
    return Observation(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(NOW - timedelta(hours=1)),
        learned_at=learned_at,
        recorded_at=learned_at,
        created_by="ingest",
        source_kind="chat",
        modality="text",
        value=text,
    )


def op(world_revision: int, key: str) -> OperationRequest:
    return OperationRequest(
        operation_name="test.commit",
        expected_world_revision=world_revision,
        reason="test",
        idempotency_key=key,
    )


def test_append_only_revision_and_world_revision(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    r1 = store.commit([make_obs(oid, 1, "first")], op(0, "k1"))
    assert r1.world_revision == 1
    r2 = store.commit([make_obs(oid, 2, "second")], op(1, "k2"))
    assert r2.world_revision == 2
    assert store.get_payload(oid, revision=1)["value"] == "first"
    assert store.get_payload(oid, revision=2)["value"] == "second"


def test_version_conflict_blocks_write(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([make_obs(oid, 1, "first")], op(0, "k1"))
    with pytest.raises(StoreError) as exc:
        store.commit([make_obs(oid, 2, "second")], op(0, "k2"))
    assert exc.value.code == ErrorCode.VERSION_CONFLICT


def test_idempotency_replay_does_not_advance_world(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    request = op(0, "same-key")
    first = store.commit([make_obs(oid, 1, "first")], request)
    replay = store.commit([make_obs(oid, 1, "first")], request)
    assert first.world_revision == replay.world_revision == 1
    assert replay.idempotent_replay is True
    assert store.current_world_revision() == 1


def test_historical_world_read(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([make_obs(oid, 1, "old")], op(0, "k1"))
    store.commit([make_obs(oid, 2, "new")], op(1, "k2"))
    assert store.get_payload(oid, as_of_world_revision=1)["value"] == "old"
    assert store.get_payload(oid, as_of_world_revision=2)["value"] == "new"


def test_learned_at_cutoff_hides_future_known_revision(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([make_obs(oid, 1, "known now", NOW)], op(0, "k1"))
    future = NOW + timedelta(days=1)
    store.commit([make_obs(oid, 2, "learned tomorrow", future)], op(1, "k2"))
    assert store.get_payload(oid, knowledge_cutoff=NOW)["value"] == "known now"


def test_wrong_object_revision_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    with pytest.raises(StoreError) as exc:
        store.commit([make_obs(oid, 2, "bad")], op(0, "k1"))
    assert exc.value.code == ErrorCode.VERSION_CONFLICT
