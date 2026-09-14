"""M0-020 historical world reads and Knowledge Cutoff leakage tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios_core.contracts import ObjectType, Observation, OperationRequest, TemporalExtent, new_object_id
from aios_core.contracts.enums import ErrorCode
from aios_core.query import HistoricalWorldQuery
from aios_core.storage import SQLiteWorldStore, StoreError


T9 = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
T10 = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
T11 = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
T12 = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
NEXT_DAY = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)


def op(expected: int, key: str) -> OperationRequest:
    return OperationRequest(
        operation_name="world.commit",
        expected_world_revision=expected,
        reason="M0-020 historical read test",
        idempotency_key=key,
    )


def obs(
    object_id: str,
    revision: int,
    value: str,
    *,
    learned_at: datetime,
    recorded_at: datetime | None = None,
    subject_id: str = "user_1",
) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id=subject_id,
        revision=revision,
        occurred=TemporalExtent.point(T9),
        learned_at=learned_at,
        recorded_at=recorded_at or learned_at,
        created_by="m0-020-test",
        source_kind="simulator",
        modality="text",
        value=value,
    )


def test_h01_today_cutoff_returns_rev1_when_rev2_is_learned_tomorrow(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, 1, "today", learned_at=T9)], op(0, "h01-1"))
    store.commit([obs(oid, 2, "FUTURE_SECRET", learned_at=NEXT_DAY)], op(1, "h01-2"))

    payload = store.get_payload(oid, knowledge_cutoff=T10)
    assert payload["revision"] == 1
    assert payload["value"] == "today"
    assert "FUTURE_SECRET" not in str(payload)


def test_h02_exact_future_revision_is_not_visible_before_learned_at(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, 1, "today", learned_at=T9)], op(0, "h02-1"))
    store.commit([obs(oid, 2, "future", learned_at=NEXT_DAY)], op(1, "h02-2"))

    with pytest.raises(StoreError) as exc:
        store.get_payload(oid, revision=2, knowledge_cutoff=T10)
    assert exc.value.code == ErrorCode.NOT_FOUND
    assert "future" not in str(exc.value)


def test_h03_world_revision_reconstructs_old_object_revision(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, 1, "v1", learned_at=T9)], op(0, "h03-1"))
    store.commit([obs(oid, 2, "v2", learned_at=T10)], op(1, "h03-2"))

    assert store.get_payload(oid, as_of_world_revision=1)["value"] == "v1"
    assert store.get_payload(oid, as_of_world_revision=2)["value"] == "v2"


def test_h04_combined_world_and_knowledge_cutoffs_choose_latest_visible_intersection(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, 1, "v1", learned_at=T9)], op(0, "h04-1"))
    store.commit([obs(oid, 2, "v2", learned_at=T11)], op(1, "h04-2"))
    store.commit([obs(oid, 3, "v3", learned_at=T12)], op(2, "h04-3"))

    assert store.get_payload(
        oid,
        as_of_world_revision=3,
        knowledge_cutoff=T10,
    )["value"] == "v1"
    assert store.get_payload(
        oid,
        as_of_world_revision=2,
        knowledge_cutoff=T12,
    )["value"] == "v2"


def test_h05_visibility_is_learned_at_not_recorded_at(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    # The system learned the fact at 09:00 but only recorded it durably at 12:00.
    # A 10:00 knowledge lens must include it; filtering only by recorded_at would leak semantics.
    store.commit(
        [obs(oid, 1, "known-by-ten", learned_at=T9, recorded_at=T12)],
        op(0, "h05-1"),
    )

    payload = store.get_payload(oid, knowledge_cutoff=T10)
    assert payload["value"] == "known-by-ten"


def test_h06_historical_list_returns_latest_visible_revision_per_object(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)
    store.commit(
        [obs(a, 1, "a1", learned_at=T9), obs(b, 1, "b1", learned_at=T9)],
        op(0, "h06-1"),
    )
    store.commit([obs(a, 2, "a2-future", learned_at=NEXT_DAY)], op(1, "h06-2"))

    payloads = store.list_payloads(knowledge_cutoff=T10)
    values = {payload["object_id"]: payload["value"] for payload in payloads}
    assert values == {a: "a1", b: "b1"}


def test_h07_subject_filter_applies_after_historical_revision_selection(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit(
        [obs(oid, 1, "old-owner", learned_at=T9, subject_id="alice")],
        op(0, "h07-1"),
    )
    store.commit(
        [obs(oid, 2, "new-owner", learned_at=T10, subject_id="bob")],
        op(1, "h07-2"),
    )

    assert len(store.list_payloads(subject_id="alice", as_of_world_revision=1)) == 1
    assert store.list_payloads(subject_id="alice", as_of_world_revision=2) == []
    latest_bob = store.list_payloads(subject_id="bob", as_of_world_revision=2)
    assert [item["value"] for item in latest_bob] == ["new-owner"]


def test_h08_historical_query_reports_actual_snapshot_revision_and_coverage(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    query = HistoricalWorldQuery(store)
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)
    store.commit(
        [obs(a, 1, "a", learned_at=T9), obs(b, 1, "b", learned_at=T9)],
        op(0, "h08-1"),
    )

    result = query.list(as_of_world_revision=1, knowledge_cutoff=T10)
    assert result.world_revision == 1
    assert result.knowledge_cutoff == T10
    assert result.coverage.returned_objects == 2
    assert len(result.payloads) == 2


def test_h09_query_without_explicit_world_revision_pins_current_snapshot(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    query = HistoricalWorldQuery(store)
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, 1, "v1", learned_at=T9)], op(0, "h09-1"))

    result = query.get(oid, knowledge_cutoff=T10)
    assert result.world_revision == 1
    assert result.payloads[0]["value"] == "v1"


def test_h10_requested_future_world_revision_is_clamped_to_actual_world(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    query = HistoricalWorldQuery(store)
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, 1, "v1", learned_at=T9)], op(0, "h10-1"))

    result = query.list(as_of_world_revision=999, knowledge_cutoff=T10)
    assert result.world_revision == 1
    assert result.coverage.returned_objects == 1


def test_h11_naive_knowledge_cutoff_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, 1, "v1", learned_at=T9)], op(0, "h11-1"))

    with pytest.raises(ValueError):
        store.get_payload(oid, knowledge_cutoff=datetime(2026, 9, 14, 10, 0))
