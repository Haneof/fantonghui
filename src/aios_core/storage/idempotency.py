from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from aios_core.contracts.base import WorldObject
from aios_core.contracts.operations import OperationRequest


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


def _object_entries(objects: Iterable[WorldObject]) -> list[dict[str, Any]]:
    entries = [
        {
            "object_id": obj.object_id,
            "revision": obj.revision,
            "payload": json.loads(obj.model_dump_json()),
        }
        for obj in objects
    ]
    entries.sort(key=lambda entry: (entry["object_id"], entry["revision"]))
    return entries


def request_fingerprint(
    operation: OperationRequest,
    objects: Iterable[WorldObject],
) -> str:
    """Return the canonical identity of one logical durable commit request.

    An idempotency key is safe to replay only when every identity-bearing request
    field and every intended object revision/payload match the original request.
    Object ordering is deliberately ignored because commit ordering is not a
    semantic part of the write request.
    """

    payload = {
        "operation_id": operation.operation_id,
        "session_id": operation.session_id,
        "operation_name": operation.operation_name,
        "arguments": _json_round_trip(operation.arguments),
        "expected_world_revision": operation.expected_world_revision,
        "reason": operation.reason,
        "idempotency_key": operation.idempotency_key,
        "objects": _object_entries(objects),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def stored_request_fingerprint(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    world_revision: int,
) -> str:
    """Rebuild the original request identity from atomically durable records.

    M0 intentionally avoids a schema migration here: the operation row and every
    object payload written at the operation's world revision already form the
    durable canonical request record. Reconstructing the fingerprint from those
    rows is equivalent to persisting a duplicate digest while remaining compatible
    with databases created before the stricter idempotency rule.
    """

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
