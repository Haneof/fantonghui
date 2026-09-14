from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from enum import Enum
from typing import Any, TypeVar, cast

from pydantic import BaseModel, TypeAdapter
from pydantic_core import PydanticSerializationError

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.contracts.registry import canonical_model_for_object_type

TWorldObject = TypeVar("TWorldObject", bound=WorldObject)
_JSON_ADAPTER: TypeAdapter[Any] = TypeAdapter(Any)
_OBJECT_TYPE_ADAPTER = TypeAdapter(ObjectType)


class DurableJSONError(ValueError):
    """Accepted Python data cannot be represented injectively as durable JSON."""


def canonical_json_value(value: Any) -> Any:
    """Convert a Python value to the deterministic JSON value used durably.

    Ordered containers keep their order. Unordered sets/frozensets are sorted by
    their canonical JSON representation so a logical request has the same durable
    identity across Python processes and hash seeds. Mapping keys are sorted by the
    final JSON encoder, not here.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return canonical_json_value(value.value)
    if isinstance(value, BaseModel):
        return canonical_json_value(value.model_dump(mode="python", round_trip=True))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DurableJSONError(
                    "durable JSON object keys must be strings; "
                    f"got {type(key).__name__}: {key!r}"
                )
            normalized[key] = canonical_json_value(item)
        return normalized
    if isinstance(value, (set, frozenset)):
        normalized_items = [canonical_json_value(item) for item in value]
        normalized_items.sort(key=_canonical_json)
        return normalized_items
    if isinstance(value, (list, tuple)):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return _JSON_ADAPTER.dump_python(value, mode="json")

    # Keep Pydantic's JSON-mode semantics for supported scalar/custom values such
    # as bytes while recursively canonicalizing any container it returns. Conversion
    # failures are part of the durable-input contract, never raw protocol exceptions.
    try:
        converted = _JSON_ADAPTER.dump_python(value, mode="json")
    except (UnicodeError, PydanticSerializationError) as exc:
        raise DurableJSONError(
            f"value cannot be represented safely as durable JSON: {type(value).__name__}"
        ) from exc
    if converted is value:
        raise DurableJSONError(
            f"value is not durably JSON serializable: {type(value)!r}"
        )
    return canonical_json_value(converted)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_dumps(value: Any) -> str:
    """Serialize exactly the deterministic representation used for fingerprints."""

    return _canonical_json(value)


def _persistence_snapshot(value: Any) -> Any:
    """Build a deep revalidation snapshot without erasing real typed references.

    ``BaseModel.model_dump`` recursively turns models stored below ``Any`` into
    plain dictionaries. That is normally useful for revalidation, but ObjectRef and
    SourceRef carry semantic meaning for the store even when they occur in an opaque
    ``Any`` container. Preserve those frozen reference instances while converting
    every other model/container recursively so the canonical outer model is still
    fully revalidated and custom subtype fields cannot bypass ``extra='forbid'``.
    """

    if isinstance(value, (ObjectRef, SourceRef)):
        return value
    if isinstance(value, BaseModel):
        return {
            field_name: _persistence_snapshot(getattr(value, field_name))
            for field_name in type(value).model_fields
        }
    if isinstance(value, Mapping):
        return {
            key: _persistence_snapshot(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_persistence_snapshot(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_persistence_snapshot(item) for item in value)
    if isinstance(value, set):
        return {_persistence_snapshot(item) for item in value}
    if isinstance(value, frozenset):
        return frozenset(_persistence_snapshot(item) for item in value)
    return value


def normalize_operation_for_persistence(operation: OperationRequest) -> OperationRequest:
    """Return a newly validated snapshot of a possibly mutated request instance.

    Pydantic assignment validation can raise after an assignment has already changed
    an instance. Durable boundaries therefore never trust the live instance directly.
    """

    snapshot = _persistence_snapshot(operation)
    return OperationRequest.model_validate(snapshot)


def normalize_world_object_for_persistence(obj: TWorldObject) -> WorldObject:
    """Validate through the canonical frozen model selected by durable object_type.

    The caller's runtime Python class is not an authority. A base/custom WorldObject
    cannot claim a reserved canonical ObjectType while bypassing that subtype's
    required fields and validators. Real ObjectRef/SourceRef instances nested under
    ``Any`` remain typed so recursive reference validation cannot be laundered by
    the normalization boundary.
    """

    snapshot = _persistence_snapshot(obj)
    object_type = _OBJECT_TYPE_ADAPTER.validate_python(obj.object_type)
    canonical_model = canonical_model_for_object_type(object_type)
    return canonical_model.model_validate(snapshot)


def canonical_world_object_payload(obj: WorldObject) -> dict[str, Any]:
    """Return the deterministic durable JSON payload for a validated WorldObject."""

    normalized = normalize_world_object_for_persistence(obj)
    value = canonical_json_value(normalized)
    if not isinstance(value, dict):
        raise TypeError("WorldObject durable JSON payload must be an object")
    return value


def _object_entries(objects: Iterable[WorldObject]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for obj in objects:
        payload = canonical_world_object_payload(obj)
        entries.append(
            {
                "object_id": payload["object_id"],
                "revision": payload["revision"],
                "payload": payload,
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
    persisted. Unordered Python collections are converted deterministically before
    either hashing or persistence, so process hash randomization cannot change an
    accepted request's replay identity.
    """

    normalized_operation = normalize_operation_for_persistence(operation)
    payload = {
        "operation_id": normalized_operation.operation_id,
        "session_id": normalized_operation.session_id,
        "operation_name": normalized_operation.operation_name,
        "arguments": canonical_json_value(normalized_operation.arguments),
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
