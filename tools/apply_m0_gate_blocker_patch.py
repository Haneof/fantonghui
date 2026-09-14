from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected patch anchor missing in {path}: {old[:80]!r}")
    if text.count(old) != 1:
        raise RuntimeError(f"patch anchor is not unique in {path}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


STORE = "src/aios_core/storage/sqlite_store.py"
replace_once(
    STORE,
    "from aios_core.contracts.base import WorldObject\nfrom aios_core.contracts.enums import ErrorCode, ObjectType\nfrom aios_core.contracts.operations import CommitResult, OperationRequest\n",
    "from aios_core.contracts.base import WorldObject\nfrom aios_core.contracts.enums import ErrorCode, ObjectType\nfrom aios_core.contracts.models import Dependency\nfrom aios_core.contracts.operations import CommitResult, OperationRequest\n",
)
replace_once(
    STORE,
    "from aios_core.contracts.time import as_utc, canonical_utc_iso, utc_now\nfrom aios_core.errors import AIOSProtocolError\n",
    "from aios_core.contracts.time import as_utc, canonical_utc_iso, utc_now\nfrom aios_core.dependency import validate_dependency_graph_acyclic\nfrom aios_core.errors import AIOSProtocolError\nfrom aios_core.storage.idempotency import request_fingerprint, stored_request_fingerprint\n",
)
replace_once(
    STORE,
    '''    def _get_idempotent_result(self, conn: sqlite3.Connection, key: str) -> CommitResult | None:\n        row = conn.execute(\n            "SELECT result_json FROM idempotency_records WHERE idempotency_key=?",\n            (key,),\n        ).fetchone()\n        if not row:\n            return None\n        data = json.loads(row["result_json"])\n        data["idempotent_replay"] = True\n        return CommitResult.model_validate(data)\n''',
    '''    def _get_idempotent_result(\n        self,\n        conn: sqlite3.Connection,\n        operation: OperationRequest,\n        objects: list[WorldObject],\n    ) -> CommitResult | None:\n        row = conn.execute(\n            """\n            SELECT operation_id, world_revision, result_json\n            FROM idempotency_records\n            WHERE idempotency_key=?\n            """,\n            (operation.idempotency_key,),\n        ).fetchone()\n        if not row:\n            return None\n\n        incoming_fingerprint = request_fingerprint(operation, objects)\n        original_fingerprint = stored_request_fingerprint(\n            conn,\n            operation_id=str(row["operation_id"]),\n            world_revision=int(row["world_revision"]),\n        )\n        if incoming_fingerprint != original_fingerprint:\n            raise StoreError(\n                ErrorCode.IDEMPOTENCY_CONFLICT,\n                "idempotency key was already used for a different request",\n                context={\n                    "idempotency_key": operation.idempotency_key,\n                    "original_operation_id": str(row["operation_id"]),\n                    "operation_id": operation.operation_id,\n                    "reason": "request_fingerprint_mismatch",\n                },\n            )\n\n        data = json.loads(row["result_json"])\n        data["idempotent_replay"] = True\n        return CommitResult.model_validate(data)\n''',
)
replace_once(
    STORE,
    '''        walk(value)\n        return refs\n\n    def commit(\n''',
    '''        walk(value)\n        return refs\n\n    def _validate_dependency_graph(\n        self,\n        conn: sqlite3.Connection,\n        objects: list[WorldObject],\n    ) -> None:\n        pending = [obj for obj in objects if isinstance(obj, Dependency)]\n        if not pending:\n            return\n\n        rows = conn.execute(\n            """\n            SELECT o.payload_json\n            FROM object_revisions o\n            JOIN (\n                SELECT object_id, MAX(revision) AS max_revision\n                FROM object_revisions\n                WHERE object_type=?\n                GROUP BY object_id\n            ) latest\n            ON latest.object_id=o.object_id AND latest.max_revision=o.revision\n            WHERE o.object_type=?\n            """,\n            (ObjectType.DEPENDENCY.value, ObjectType.DEPENDENCY.value),\n        ).fetchall()\n\n        current_by_id: dict[str, Dependency] = {}\n        for row in rows:\n            dependency = Dependency.model_validate(json.loads(row["payload_json"]))\n            current_by_id[dependency.object_id] = dependency\n        for dependency in pending:\n            current_by_id[dependency.object_id] = dependency\n\n        try:\n            validate_dependency_graph_acyclic(current_by_id.values())\n        except ValueError as exc:\n            raise StoreError(\n                ErrorCode.DEPENDENCY_INVALID,\n                str(exc),\n                context={\n                    "reason": "dependency_cycle",\n                    "pending_dependency_ids": [dep.object_id for dep in pending],\n                },\n            ) from exc\n\n    def commit(\n''',
)
replace_once(
    STORE,
    '''                replay = self._get_idempotent_result(conn, operation.idempotency_key)\n''',
    '''                replay = self._get_idempotent_result(conn, operation, object_list)\n''',
)
replace_once(
    STORE,
    '''                                },\n                            )\n\n                next_world_revision = current_world_revision + 1\n''',
    '''                                },\n                            )\n\n                self._validate_dependency_graph(conn, object_list)\n\n                next_world_revision = current_world_revision + 1\n''',
)

# Focused blocker regression suite.
Path("tests/unit/test_m0_gate_blockers.py").write_text(
    r'''from __future__ import annotations

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
''',
    encoding="utf-8",
)

# Remove the one-shot patch machinery from the resulting semantic commit.
Path("tools/apply_m0_gate_blocker_patch.py").unlink()
Path(".github/workflows/m0-gate-blocker-patch.yml").unlink()
