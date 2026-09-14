from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from aios_core.contracts import (
    Dependency,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    TemporalExtent,
    new_object_id,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError

NOW = datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)


def obs(object_id: str, value: str) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-gate-blocker-test",
        source_kind="test",
        modality="text",
        value=value,
    )


def op(expected: int, key: str, *, operation_id: str, arguments=None) -> OperationRequest:
    return OperationRequest(
        operation_id=operation_id,
        session_id="gate-session",
        operation_name="world.commit",
        arguments=arguments or {"kind": "gate"},
        expected_world_revision=expected,
        reason="M0 Gate blocker regression",
        idempotency_key=key,
    )


def dep(dependent: str, dependency: str) -> Dependency:
    return Dependency(
        object_id=new_object_id(ObjectType.DEPENDENCY),
        subject_id="gate-user",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-gate-blocker-test",
        dependent_ref=ObjectRef(object_id=dependent, revision=1),
        dependency_ref=ObjectRef(object_id=dependency, revision=1),
        dependency_type="proof_basis",
    )


def test_b1_same_key_different_operation_identity_is_conflict(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(oid, "original")], op(0, "K", operation_id="op-original"))

    with pytest.raises(StoreError) as exc:
        store.commit([obs(oid, "original")], op(999, "K", operation_id="op-altered"))
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert exc.value.context["reason"] == "request_fingerprint_mismatch"
    assert store.current_world_revision() == 1


def test_b1_same_key_altered_arguments_is_conflict(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    request = op(0, "K", operation_id="op-1", arguments={"value": "ORIGINAL"})
    store.commit([obs(oid, "payload")], request)

    altered = request.model_copy(update={"arguments": {"value": "ALTERED"}})
    with pytest.raises(StoreError) as exc:
        store.commit([obs(oid, "payload")], altered)
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


def test_b1_same_key_altered_object_payload_is_conflict(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    oid = new_object_id(ObjectType.OBSERVATION)
    request = op(0, "K", operation_id="op-1")
    store.commit([obs(oid, "ORIGINAL")], request)

    with pytest.raises(StoreError) as exc:
        store.commit([obs(oid, "ALTERED")], request)
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert store.get_payload(oid)["value"] == "ORIGINAL"


def test_b1_exact_replay_survives_restart(tmp_path):
    path = tmp_path / "world.db"
    oid = new_object_id(ObjectType.OBSERVATION)
    request = op(0, "K", operation_id="op-1")
    first = SQLiteWorldStore(path).commit([obs(oid, "same")], request)
    replay = SQLiteWorldStore(path).commit([obs(oid, "same")], request)
    assert replay.world_revision == first.world_revision == 1
    assert replay.idempotent_replay is True


def test_b1_concurrent_same_key_different_requests_one_wins_other_conflicts(tmp_path):
    path = tmp_path / "world.db"
    SQLiteWorldStore(path)
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)

    def run(which: str):
        store = SQLiteWorldStore(path)
        oid = a if which == "a" else b
        try:
            result = store.commit(
                [obs(oid, which)],
                op(0, "shared-K", operation_id=f"op-{which}", arguments={"which": which}),
            )
            return ("ok", result.operation_id)
        except StoreError as exc:
            return ("error", exc.code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["a", "b"]))
    assert sum(kind == "ok" for kind, _ in results) == 1
    assert sum(value is ErrorCode.IDEMPOTENCY_CONFLICT for _, value in results) == 1
    assert SQLiteWorldStore(path).current_world_revision() == 1


def test_b3_same_transaction_dependency_cycle_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(a, "a"), obs(b, "b")], op(0, "seed", operation_id="seed-op"))

    with pytest.raises(StoreError) as exc:
        store.commit(
            [dep(a, b), dep(b, a)],
            op(1, "cycle", operation_id="cycle-op"),
        )
    assert exc.value.code is ErrorCode.DEPENDENCY_INVALID
    assert exc.value.context["reason"] == "dependency_cycle"
    assert store.current_world_revision() == 1


def test_b3_cycle_split_across_commits_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    a = new_object_id(ObjectType.OBSERVATION)
    b = new_object_id(ObjectType.OBSERVATION)
    store.commit([obs(a, "a"), obs(b, "b")], op(0, "seed", operation_id="seed-op"))
    store.commit([dep(a, b)], op(1, "edge-1", operation_id="edge-1-op"))

    with pytest.raises(StoreError) as exc:
        store.commit([dep(b, a)], op(2, "edge-2", operation_id="edge-2-op"))
    assert exc.value.code is ErrorCode.DEPENDENCY_INVALID
    assert store.current_world_revision() == 2
    assert len(store.list_payloads(object_type=ObjectType.DEPENDENCY)) == 1
