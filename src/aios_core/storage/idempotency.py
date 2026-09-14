from __future__ import annotations

import hashlib
import json
import math
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
_MAX_CANONICAL_DEPTH = 128


class DurableJSONError(ValueError):
    """Accepted Python data cannot be represented injectively as durable JSON."""


def _validate_json_string(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise DurableJSONError("durable JSON strings must be valid UTF-8") from exc
    return value


def _validate_json_integer(value: int) -> int:
    try:
        str(value)
    except ValueError as exc:
        raise DurableJSONError("integer cannot be represented safely as durable JSON") from exc
    return value


def _model_items(value: BaseModel) -> dict[str, Any]:
    """Expose declared, allowed-extra and dirty model-copy fields without dropping data."""

    data = {
        field_name: getattr(value, field_name)
        for field_name in type(value).model_fields
    }
    extras = getattr(value, "__pydantic_extra__", None)
    if isinstance(extras, dict):
        for key, item in extras.items():
            data.setdefault(key, item)
    for key, item in vars(value).items():
        if key.startswith("_") or key in data:
            continue
        data[key] = item
    return data


def _encoded_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (UnicodeError, ValueError, OverflowError, RecursionError, TypeError) as exc:
        raise DurableJSONError("value cannot be encoded safely as durable JSON") from exc


def canonical_json_value(value: Any) -> Any:
    """Convert a Python value to the deterministic JSON value used durably.

    Ordered containers keep their order. Unordered sets/frozensets are sorted by
    their canonical JSON representation so a logical request has the same durable
    identity across Python processes and hash seeds. Cycles, excessive nesting,
    invalid UTF-8 and values that Python cannot convert to JSON are rejected at the
    durable boundary instead of leaking raw runtime exceptions.
    """

    return _canonical_json_value(value, active=set(), depth=0)


def _canonical_json_value(value: Any, *, active: set[int], depth: int) -> Any:
    if depth > _MAX_CANONICAL_DEPTH:
        raise DurableJSONError("durable JSON value is nested too deeply")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _validate_json_string(value)
    if isinstance(value, int):
        return _validate_json_integer(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DurableJSONError("non-finite floats are not valid durable JSON")
        return value
    if isinstance(value, Enum):
        return _canonical_json_value(value.value, active=active, depth=depth + 1)
    if isinstance(value, BaseModel):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic model graph is not valid durable JSON")
        active.add(marker)
        try:
            return {
                _validate_json_string(key): _canonical_json_value(
                    item, active=active, depth=depth + 1
                )
                for key, item in _model_items(value).items()
            }
        finally:
            active.remove(marker)
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic mapping is not valid durable JSON")
        active.add(marker)
        try:
            normalized: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise DurableJSONError(
                        "durable JSON object keys must be strings; "
                        f"got {type(key).__name__}: {key!r}"
                    )
                normalized[_validate_json_string(key)] = _canonical_json_value(
                    item, active=active, depth=depth + 1
                )
            return normalized
        finally:
            active.remove(marker)
    if isinstance(value, (set, frozenset)):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic set is not valid durable JSON")
        active.add(marker)
        try:
            normalized_items = [
                _canonical_json_value(item, active=active, depth=depth + 1)
                for item in value
            ]
            normalized_items.sort(key=_encoded_json)
            return normalized_items
        finally:
            active.remove(marker)
    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic sequence is not valid durable JSON")
        active.add(marker)
        try:
            return [
                _canonical_json_value(item, active=active, depth=depth + 1)
                for item in value
            ]
        finally:
            active.remove(marker)
    if isinstance(value, (datetime, date, time)):
        try:
            converted = _JSON_ADAPTER.dump_python(value, mode="json")
        except (
            UnicodeError,
            PydanticSerializationError,
            ValueError,
            OverflowError,
            RecursionError,
            TypeError,
        ) as exc:
            raise DurableJSONError(
                f"value cannot be represented safely as durable JSON: {type(value).__name__}"
            ) from exc
        return _canonical_json_value(converted, active=active, depth=depth + 1)

    try:
        converted = _JSON_ADAPTER.dump_python(value, mode="json")
    except (
        UnicodeError,
        PydanticSerializationError,
        ValueError,
        OverflowError,
        RecursionError,
        TypeError,
    ) as exc:
        raise DurableJSONError(
            f"value cannot be represented safely as durable JSON: {type(value).__name__}"
        ) from exc
    if converted is value:
        raise DurableJSONError(
            f"value is not durably JSON serializable: {type(value)!r}"
        )
    return _canonical_json_value(converted, active=active, depth=depth + 1)


def _canonical_json(value: Any) -> str:
    return _encoded_json(canonical_json_value(value))


def canonical_json_dumps(value: Any) -> str:
    """Serialize exactly the deterministic representation used durably."""

    return _canonical_json(value)


def _persistence_snapshot(
    value: Any,
    *,
    active: set[int] | None = None,
    depth: int = 0,
) -> Any:
    """Build a deep revalidation snapshot without erasing semantic references.

    Real ObjectRef/SourceRef values are reconstructed through their canonical models
    so ``model_copy(update=...)`` cannot smuggle unvalidated fields or scalar types.
    Other BaseModel extras/dirty fields are retained in the snapshot instead of being
    silently deleted. Cycles/excessive depth are left intact here and rejected by the
    durable/identity encoder, where they map to the storage protocol cleanly.
    """

    if active is None:
        active = set()
    if depth > _MAX_CANONICAL_DEPTH:
        return value
    if value is None or isinstance(
        value, (str, int, float, bool, Enum, datetime, date, time)
    ):
        return value

    if isinstance(value, BaseModel):
        marker = id(value)
        if marker in active:
            return value
        active.add(marker)
        try:
            snapshot = {
                key: _persistence_snapshot(item, active=active, depth=depth + 1)
                for key, item in _model_items(value).items()
            }
        finally:
            active.remove(marker)
        if isinstance(value, ObjectRef):
            return ObjectRef.model_validate(snapshot)
        if isinstance(value, SourceRef):
            return SourceRef.model_validate(snapshot)
        return snapshot

    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active:
            return value
        active.add(marker)
        try:
            return {
                key: _persistence_snapshot(item, active=active, depth=depth + 1)
                for key, item in value.items()
            }
        finally:
            active.remove(marker)
    if isinstance(value, list):
        marker = id(value)
        if marker in active:
            return value
        active.add(marker)
        try:
            return [
                _persistence_snapshot(item, active=active, depth=depth + 1)
                for item in value
            ]
        finally:
            active.remove(marker)
    if isinstance(value, tuple):
        marker = id(value)
        if marker in active:
            return value
        active.add(marker)
        try:
            return tuple(
                _persistence_snapshot(item, active=active, depth=depth + 1)
                for item in value
            )
        finally:
            active.remove(marker)
    if isinstance(value, (set, frozenset)):
        marker = id(value)
        if marker in active:
            return value
        active.add(marker)
        try:
            items = [
                _persistence_snapshot(item, active=active, depth=depth + 1)
                for item in value
            ]
        finally:
            active.remove(marker)
        try:
            return type(value)(items)
        except TypeError:
            return value
    return value


def normalize_operation_for_persistence(operation: OperationRequest) -> OperationRequest:
    """Return a newly validated snapshot of a possibly mutated request instance."""

    snapshot = _persistence_snapshot(operation)
    return OperationRequest.model_validate(snapshot)


def normalize_world_object_for_persistence(obj: TWorldObject) -> WorldObject:
    """Validate through the canonical frozen model selected by durable object_type."""

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


def _identity_json_from_encoded(value: Any) -> str:
    return _encoded_json(value)


def _semantic_identity_value(value: Any) -> Any:
    """Encode request identity without erasing runtime semantic types."""

    return _semantic_identity_value_inner(value, active=set(), depth=0)


def _semantic_identity_value_inner(
    value: Any,
    *,
    active: set[int],
    depth: int,
) -> Any:
    if depth > _MAX_CANONICAL_DEPTH:
        raise DurableJSONError("request identity is nested too deeply")
    if isinstance(value, ObjectRef):
        return [
            "$aios-ref",
            "object",
            _validate_json_string(value.object_id),
            None if value.revision is None else _validate_json_integer(value.revision),
        ]
    if isinstance(value, SourceRef):
        return [
            "$aios-ref",
            "source",
            _validate_json_string(value.object_id),
            None if value.revision is None else _validate_json_integer(value.revision),
            None
            if value.source_locator is None
            else _validate_json_string(value.source_locator),
        ]
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _validate_json_string(value)
    if isinstance(value, int):
        return _validate_json_integer(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DurableJSONError("non-finite floats are not valid request identity")
        return value
    if isinstance(value, Enum):
        return _semantic_identity_value_inner(
            value.value, active=active, depth=depth + 1
        )
    if isinstance(value, BaseModel):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic model graph is not valid request identity")
        active.add(marker)
        try:
            model_value = _model_items(value)
            return _semantic_identity_value_inner(
                model_value, active=active, depth=depth + 1
            )
        finally:
            active.remove(marker)
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic mapping is not valid request identity")
        active.add(marker)
        try:
            entries: list[list[Any]] = []
            for key, item in value.items():
                if not isinstance(key, str):
                    raise DurableJSONError(
                        "durable JSON object keys must be strings; "
                        f"got {type(key).__name__}: {key!r}"
                    )
                entries.append(
                    [
                        _validate_json_string(key),
                        _semantic_identity_value_inner(
                            item, active=active, depth=depth + 1
                        ),
                    ]
                )
            entries.sort(key=lambda entry: entry[0])
            return ["$mapping", entries]
        finally:
            active.remove(marker)
    if isinstance(value, (set, frozenset)):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic set is not valid request identity")
        active.add(marker)
        try:
            normalized_items = [
                _semantic_identity_value_inner(
                    item, active=active, depth=depth + 1
                )
                for item in value
            ]
            normalized_items.sort(key=_identity_json_from_encoded)
            return ["$set", normalized_items]
        finally:
            active.remove(marker)
    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in active:
            raise DurableJSONError("cyclic sequence is not valid request identity")
        active.add(marker)
        try:
            return [
                "$sequence",
                [
                    _semantic_identity_value_inner(
                        item, active=active, depth=depth + 1
                    )
                    for item in value
                ],
            ]
        finally:
            active.remove(marker)
    if isinstance(value, (datetime, date, time)):
        try:
            converted = _JSON_ADAPTER.dump_python(value, mode="json")
        except (
            UnicodeError,
            PydanticSerializationError,
            ValueError,
            OverflowError,
            RecursionError,
            TypeError,
        ) as exc:
            raise DurableJSONError(
                f"value cannot be represented safely in request identity: {type(value).__name__}"
            ) from exc
        return _semantic_identity_value_inner(
            converted, active=active, depth=depth + 1
        )

    try:
        converted = _JSON_ADAPTER.dump_python(value, mode="json")
    except (
        UnicodeError,
        PydanticSerializationError,
        ValueError,
        OverflowError,
        RecursionError,
        TypeError,
    ) as exc:
        raise DurableJSONError(
            f"value cannot be represented safely in request identity: {type(value).__name__}"
        ) from exc
    if converted is value:
        raise DurableJSONError(
            f"value is not durably JSON serializable: {type(value)!r}"
        )
    return _semantic_identity_value_inner(
        converted, active=active, depth=depth + 1
    )


def _semantic_identity_json(value: Any) -> str:
    return _identity_json_from_encoded(_semantic_identity_value(value))


def _semantic_object_entries(objects: Iterable[WorldObject]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for obj in objects:
        normalized = normalize_world_object_for_persistence(obj)
        entries.append(
            {
                "object_id": normalized.object_id,
                "revision": normalized.revision,
                "payload": normalized,
            }
        )
    entries.sort(key=lambda entry: (entry["object_id"], entry["revision"]))
    return entries


def request_fingerprint(
    operation: OperationRequest,
    objects: Iterable[WorldObject],
) -> str:
    """Return semantic identity for one logical durable commit request."""

    normalized_operation = normalize_operation_for_persistence(operation)
    payload = {
        "operation_id": normalized_operation.operation_id,
        "session_id": normalized_operation.session_id,
        "operation_name": normalized_operation.operation_name,
        "arguments": normalized_operation.arguments,
        "expected_world_revision": normalized_operation.expected_world_revision,
        "reason": normalized_operation.reason,
        "idempotency_key": normalized_operation.idempotency_key,
        "objects": _semantic_object_entries(objects),
    }
    try:
        encoded = _semantic_identity_json(payload).encode("utf-8")
    except UnicodeError as exc:
        raise DurableJSONError("request fingerprint is not valid UTF-8") from exc
    return hashlib.sha256(encoded).hexdigest()


def _contains_typed_reference(
    value: Any,
    *,
    active: set[int] | None = None,
) -> bool:
    """Return whether runtime semantics include a real typed reference.

    Legacy idempotency rows persisted only durable JSON and therefore cannot prove
    whether a ref-shaped object was originally an opaque mapping or a real
    ObjectRef/SourceRef. When semantic fingerprints are absent, typed-ref retries
    must fail closed instead of guessing equivalence from the lossy JSON shape.
    """

    if isinstance(value, (ObjectRef, SourceRef)):
        return True
    if active is None:
        active = set()
    if isinstance(value, BaseModel):
        marker = id(value)
        if marker in active:
            return False
        active.add(marker)
        try:
            return any(
                _contains_typed_reference(item, active=active)
                for item in _model_items(value).values()
            )
        finally:
            active.remove(marker)
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active:
            return False
        active.add(marker)
        try:
            return any(
                _contains_typed_reference(key, active=active)
                or _contains_typed_reference(item, active=active)
                for key, item in value.items()
            )
        finally:
            active.remove(marker)
    if isinstance(value, (list, tuple, set, frozenset)):
        marker = id(value)
        if marker in active:
            return False
        active.add(marker)
        try:
            return any(
                _contains_typed_reference(item, active=active) for item in value
            )
        finally:
            active.remove(marker)
    return False


def legacy_request_fingerprint(
    operation: OperationRequest,
    objects: Iterable[WorldObject],
) -> str:
    """Return the pre-semantic fingerprint for legacy idempotency rows only."""

    normalized_operation = normalize_operation_for_persistence(operation)
    normalized_objects = [normalize_world_object_for_persistence(obj) for obj in objects]
    if _contains_typed_reference(normalized_operation) or any(
        _contains_typed_reference(obj) for obj in normalized_objects
    ):
        raise DurableJSONError(
            "legacy idempotency identity cannot prove typed-reference semantics"
        )
    payload = {
        "operation_id": normalized_operation.operation_id,
        "session_id": normalized_operation.session_id,
        "operation_name": normalized_operation.operation_name,
        "arguments": canonical_json_value(normalized_operation.arguments),
        "expected_world_revision": normalized_operation.expected_world_revision,
        "reason": normalized_operation.reason,
        "idempotency_key": normalized_operation.idempotency_key,
        "objects": _object_entries(normalized_objects),
    }
    try:
        encoded = _canonical_json(payload).encode("utf-8")
    except UnicodeError as exc:
        raise DurableJSONError("legacy request fingerprint is not valid UTF-8") from exc
    return hashlib.sha256(encoded).hexdigest()


def stored_request_fingerprint(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    world_revision: int,
) -> str:
    """Rebuild the legacy normalized request identity from durable records."""

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
