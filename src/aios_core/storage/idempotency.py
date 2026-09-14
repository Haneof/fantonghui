from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from typing import Any, TypeVar, cast

from aios_core.contracts.base import WorldObject
from aios_core.contracts.operations import OperationRequest

TWorldObject = TypeVar("TWorldObject", bound=WorldObject)


def _json_round_trip(value: Any) -> Any:
    """Normalize values exactly like the durable operation audit representation."""

    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def normalize_operation_for_persistence(operation: OperationRequest) -> OperationRequest:
    """Return a newly validated snapshot of a possibly mutated request instance.

    Pydantic assignment validation can raise after an assignment has already changed
    an instance. Durable boundaries therefore never trust the live instance directly.
    """

    snapshot = operation.model_dump(mode="python", round_trip=True)
    return OperationRequest.model_validate(snapshot)


def normalize_world_object_for_persistence(obj: TWorldObject) -> TWorldObject:
    """Return the same canonical object representation used for durable storage."""

    snapshot = obj.model_dump(mode="python", round_trip=True)
    return cast(TWorldObject, type(obj).model_validate(snapshot))


def _object_entries(objects: Iterable[WorldObject]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for obj in objects:
        normalized = normalize_world_object_for_persistence(obj)
        entries.append(
            {
                "object_id": normalized.object_id,
                "revision": normalized.revision,
                "payload": json.loads(normalized.model_dump_json()),
            }
        )
    entries.sort(key=lambda entry: (entry["object_id"], entry["revision"]))
    return entries


def request_fingerprint(
    operation: OperationRequest,
    objects: Iterable[WorldObject],
) -> str:
    """Return canonical identity for one logical durable commit request.

    Replay identity is calculated from the same normalized representation that is
    persisted. This closes the B6 gap where a coercible post-construction mutation
    could be accepted, persisted in normalized form, and then fail exact replay.
    """

    normalized_operation = normalize_operation_for_persistence(operation)
    payload = {
        "operation_id": normalized_operation.operation_id,
        "session_id": normalized_operation.session_id,
        "operation_name": normalized_operation.operation_name,
        "arguments": _json_round_trip(normalized_operation.arguments),
        "expected_world_revision": normalized_operation.expected_world_revision,
        "reason": normalized_operation.reason,
        "idempotency_key": normalized_operation.idempotency_key,
        "objects": _object_entries(objects),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def stored_request_fingerprint(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    world_revision: int,
) -> str:
    """Rebuild the normalized original request identity from durable records."""

    operation_row = conn.execute(
        """
        SELECT operation_id, session_id, operation_name, arguments_json,
               expected_world_revision, reason, idempotency_key
        FROM operations
        WHERE operation_id=?
        """,
        (operation_id,),
    ).fetchone()
    if operation_row is None:
        raise RuntimeError(
            f"idempotency record references missing operation: {operation_id}"
        )

    object_rows = conn.execute(
        """
        SELECT object_id, revision, payload_json
        FROM object_revisions
        WHERE world_revision=?
        ORDER BY object_id ASC, revision ASC
        """,
        (world_revision,),
    ).fetchall()

    payload = {
        "operation_id": operation_row["operation_id"],
        "session_id": operation_row["session_id"],
        "operation_name": operation_row["operation_name"],
        "arguments": json.loads(operation_row["arguments_json"]),
        "expected_world_revision": operation_row["expected_world_revision"],
        "reason": operation_row["reason"],
        "idempotency_key": operation_row["idempotency_key"],
        "objects": [
            {
                "object_id": row["object_id"],
                "revision": row["revision"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in object_rows
        ],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
