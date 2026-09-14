from __future__ import annotations

import sqlite3
import warnings
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.contracts import (
    EvidenceSet,
    KnowledgeWindow,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    TemporalExtent,
    new_object_id,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError

T = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)


def op(expected: int, key: str, *, operation_id: str | None = None) -> OperationRequest:
    return OperationRequest(
        operation_id=operation_id or f"op-{key}",
        session_id="gate-third-followup",
        operation_name="world.commit",
        arguments={"gate": "third-followup"},
        expected_world_revision=expected,
        reason="M0 Gate B6/B7/B5/R4 follow-up",
        idempotency_key=key,
    )


def obs(object_id: str, *, learned_at: datetime = T) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(learned_at),
        learned_at=learned_at,
        recorded_at=learned_at,
        created_by="m0-gate-third-followup",
        source_kind="test",
        modality="text",
        value="payload",
    )


def db_state(path) -> tuple[list[tuple], ...]:
    with sqlite3.connect(path) as conn:
        return tuple(
            conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in (
                "world_meta",
                "world_commits",
                "object_revisions",
                "operations",
                "idempotency_records",
            )
        )


def test_b6_coercible_nested_mutation_replays_from_same_normalized_identity(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    observation_id = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(observation_id)], op(0, "seed"))

    evidence_id = new_object_id(ObjectType.EVIDENCE_SET)
    evidence = EvidenceSet(
        object_id=evidence_id,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(T),
        learned_at=T,
        recorded_at=T,
        created_by="m0-gate-third-followup",
        purpose="B6 normalized retry",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=T, world_revision=1),
        member_refs=[ObjectRef(object_id=observation_id, revision=1)],
        selection_method="explicit",
    )
    evidence.coverage.observed_count = "1"  # type: ignore[assignment]
    request = op(1, "b6")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Pydantic serializer warnings:")
        first = store.commit([evidence], request)
        replay = SQLiteWorldStore(path).commit([evidence], request)

    assert first.world_revision == replay.world_revision == 2
    assert replay.idempotent_replay is True
    assert SQLiteWorldStore(path).get_payload(evidence_id)["coverage"]["observed_count"] == 1
    assert SQLiteWorldStore(path).current_world_revision() == 2


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("operation_id", " "),
        ("session_id", " "),
        ("operation_name", " "),
        ("reason", " "),
        ("idempotency_key", " "),
    ],
)
def test_b7_failed_assignment_cannot_persist_dirty_operation(tmp_path, field, bad_value):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    request = op(0, f"b7-{field}", operation_id=f"b7-op-{field}")

    with pytest.raises(ValidationError):
        setattr(request, field, bad_value)
    assert getattr(request, field) == bad_value

    before = db_state(path)
    with pytest.raises(StoreError) as exc:
        store.commit([obs(new_object_id(ObjectType.OBSERVATION))], request)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc.value.context["reason"] == "operation_persistence_revalidation_failed"
    assert db_state(path) == before


def test_b5_connect_failure_is_storage_failure_not_raw_sqlite(tmp_path):
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(tmp_path / "missing-parent" / "world.db")
    assert exc.value.code is ErrorCode.STORAGE_FAILURE
    assert exc.value.context["reason"] == "storage_unavailable"
    assert isinstance(exc.value.__cause__, sqlite3.OperationalError)


def test_b5_internal_schema_failure_is_storage_failure(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE operations")
        conn.commit()

    with pytest.raises(StoreError) as exc:
        store.commit([obs(new_object_id(ObjectType.OBSERVATION))], op(0, "schema-fault"))
    assert exc.value.code is ErrorCode.STORAGE_FAILURE
    assert exc.value.context["reason"] == "sqlite_operational_error"
    assert isinstance(exc.value.__cause__, sqlite3.OperationalError)


@pytest.mark.parametrize("role", ["member_refs", "support_refs", "counter_refs", "context_refs"])
def test_r4_evidence_refs_must_be_visible_at_frozen_cutoff(tmp_path, role):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    old_id = new_object_id(ObjectType.OBSERVATION)
    later_id = new_object_id(ObjectType.OBSERVATION)
    old_time = T - timedelta(hours=2)
    cutoff = T - timedelta(hours=1)
    store.commit(
        [obs(old_id, learned_at=old_time), obs(later_id, learned_at=T)],
        op(0, f"seed-{role}"),
    )

    kwargs = {
        "member_refs": [ObjectRef(object_id=old_id, revision=1)],
        role: [ObjectRef(object_id=later_id, revision=1)],
    }
    if role == "member_refs":
        kwargs["member_refs"] = [ObjectRef(object_id=later_id, revision=1)]

    evidence = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(T),
        learned_at=T,
        recorded_at=T,
        created_by="m0-gate-third-followup",
        purpose=f"R4 {role}",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=cutoff, world_revision=1),
        selection_method="explicit",
        **kwargs,
    )

    before = db_state(path)
    with pytest.raises(StoreError) as exc:
        store.commit([evidence], op(1, f"evidence-{role}"))
    assert exc.value.code is ErrorCode.NOT_FOUND
    assert exc.value.context["referenced_object_id"] == later_id
    assert db_state(path) == before


def test_r4_same_transaction_member_visible_at_cutoff_remains_legal(tmp_path):
    path = tmp_path / "world.db"
    store = SQLiteWorldStore(path)
    observation_id = new_object_id(ObjectType.OBSERVATION)
    evidence_id = new_object_id(ObjectType.EVIDENCE_SET)
    observation = obs(observation_id, learned_at=T)
    evidence = EvidenceSet(
        object_id=evidence_id,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(T),
        learned_at=T,
        recorded_at=T,
        created_by="m0-gate-third-followup",
        purpose="same transaction frozen evidence",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=T, world_revision=None),
        member_refs=[ObjectRef(object_id=observation_id, revision=1)],
        selection_method="explicit",
    )

    result = store.commit([observation, evidence], op(0, "same-tx-evidence"))
    assert result.world_revision == 1
    assert {ref[0] for ref in result.object_refs} == {observation_id, evidence_id}
