from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError


_SET_ITEMS = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
]


def _seed_order(seed: int) -> str:
    code = "items=" + repr(_SET_ITEMS) + "; print(repr(set(items)))"
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = str(seed)
    return subprocess.check_output(
        [sys.executable, "-c", code],
        env=env,
        text=True,
    ).strip()


def _different_hash_seeds() -> tuple[int, int]:
    seen: dict[str, int] = {}
    for seed in range(1, 33):
        order = _seed_order(seed)
        for previous_order, previous_seed in seen.items():
            if order != previous_order:
                return previous_seed, seed
        seen[order] = seed
    pytest.skip("could not find two PYTHONHASHSEED values with different set order")


def _run_cross_process_commit(db_path: Path, seed: int) -> dict[str, object]:
    script = textwrap.dedent(
        f"""
        import json
        from datetime import datetime, timezone
        from aios_core.contracts import ObjectType, Observation, OperationRequest, TemporalExtent
        from aios_core.storage import SQLiteWorldStore, StoreError

        db_path = {str(db_path)!r}
        items = {_SET_ITEMS!r}
        now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
        obj = Observation(
            object_id="observation_cross_process_set",
            subject_id="gate-user",
            revision=1,
            occurred=TemporalExtent.point(now),
            learned_at=now,
            recorded_at=now,
            created_by="m0-gate-fourth-followup",
            source_kind="test",
            modality="json",
            value={{"labels": set(items)}},
        )
        request = OperationRequest(
            operation_id="operation_cross_process_set",
            session_id="session_cross_process_set",
            operation_name="world.commit",
            arguments={{"labels": set(items)}},
            expected_world_revision=0,
            reason="cross-process collection replay must be stable",
            idempotency_key="idempotency_cross_process_set",
        )
        store = SQLiteWorldStore(db_path)
        try:
            result = store.commit([obj], request)
        except StoreError as exc:
            print(json.dumps({{"ok": False, "code": exc.code.value, "context": exc.context}}, sort_keys=True))
        else:
            print(json.dumps({{
                "ok": True,
                "world_revision": result.world_revision,
                "idempotent_replay": result.idempotent_replay,
                "stored": store.get_payload(obj.object_id),
                "audit": store.operation_record(request.operation_id),
            }}, sort_keys=True))
        """
    )
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = str(seed)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        check=True,
        capture_output=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_b8_cross_process_unordered_collection_exact_replay_is_stable(tmp_path):
    first_seed, second_seed = _different_hash_seeds()
    path = tmp_path / "world.db"

    first = _run_cross_process_commit(path, first_seed)
    assert first["ok"] is True
    assert first["world_revision"] == 1
    assert first["idempotent_replay"] is False

    replay = _run_cross_process_commit(path, second_seed)
    assert replay["ok"] is True, replay
    assert replay["world_revision"] == 1
    assert replay["idempotent_replay"] is True

    store = SQLiteWorldStore(path)
    assert store.current_world_revision() == 1
    payload = store.get_payload("observation_cross_process_set")
    labels = payload["value"]["labels"]
    assert labels == sorted(_SET_ITEMS)
    audit = store.operation_record("operation_cross_process_set")
    assert json.loads(audit["arguments_json"])["labels"] == sorted(_SET_ITEMS)


def test_b9_non_busy_operational_error_with_busy_word_is_not_retryable_lock(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")

    with pytest.raises(StoreError) as exc:
        with store._connection() as conn:  # precise classifier probe at storage boundary
            conn.execute("SELECT * FROM busy_missing_internal_table").fetchall()

    assert exc.value.code is ErrorCode.STORAGE_FAILURE
    assert exc.value.context["reason"] == "sqlite_operational_error"
    assert isinstance(exc.value.__cause__, sqlite3.OperationalError)
    assert getattr(exc.value.__cause__, "sqlite_errorcode", None) != sqlite3.SQLITE_BUSY
    assert getattr(exc.value.__cause__, "sqlite_errorcode", None) != sqlite3.SQLITE_LOCKED
