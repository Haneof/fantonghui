from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one match in {path}, found {count}: {old[:80]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# X8: preserve typed-reference semantics nested inside accepted dataclass values.
replace_once(
    "src/aios_core/storage/idempotency.py",
    "from collections.abc import Iterable, Mapping\nfrom datetime import date, datetime, time\n",
    "from collections.abc import Iterable, Mapping\nfrom dataclasses import fields, is_dataclass\nfrom datetime import date, datetime, time\n",
)
replace_once(
    "src/aios_core/storage/idempotency.py",
    """        if isinstance(value, SourceRef):\n            return SourceRef.model_validate(snapshot)\n        return snapshot\n\n    if isinstance(value, Mapping):\n""",
    """        if isinstance(value, SourceRef):\n            return SourceRef.model_validate(snapshot)\n        return snapshot\n\n    if is_dataclass(value) and not isinstance(value, type):\n        marker = id(value)\n        if marker in active:\n            return value\n        active.add(marker)\n        try:\n            return {\n                field.name: _persistence_snapshot(\n                    getattr(value, field.name), active=active, depth=depth + 1\n                )\n                for field in fields(value)\n            }\n        finally:\n            active.remove(marker)\n\n    if isinstance(value, Mapping):\n""",
)

# X9-a: normalize datetime overflow into ValueError so Pydantic can classify it.
replace_once(
    "src/aios_core/contracts/time.py",
    """def as_utc(\n    value: datetime,\n    field_name: str = \"timestamp\",\n) -> datetime:\n    require_aware(value, field_name)\n    return value.astimezone(timezone.utc)\n""",
    """def as_utc(\n    value: datetime,\n    field_name: str = \"timestamp\",\n) -> datetime:\n    require_aware(value, field_name)\n    try:\n        return value.astimezone(timezone.utc)\n    except (OverflowError, OSError, ValueError) as exc:\n        raise ValueError(\n            f\"{field_name} is outside the supported datetime range\"\n        ) from exc\n""",
)

# X9-b / X10: protocol-safe query bounds and durable-state decoding.
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """        super().__init__(code, message, context=context)\n\n\nclass SQLiteWorldStore:\n""",
    """        super().__init__(code, message, context=context)\n\n\n_SQLITE_INT64_MIN = -(1 << 63)\n_SQLITE_INT64_MAX = (1 << 63) - 1\n\n\ndef _normalize_query_integer(value: object, field_name: str) -> int:\n    if (\n        isinstance(value, bool)\n        or not isinstance(value, int)\n        or value < _SQLITE_INT64_MIN\n        or value > _SQLITE_INT64_MAX\n    ):\n        raise StoreError(\n            ErrorCode.INVALID_ARGUMENT,\n            f\"{field_name} is outside the supported SQLite integer range\",\n            context={\n                \"field\": field_name,\n                \"value\": repr(value),\n                \"reason\": \"query_integer_out_of_range\",\n            },\n        )\n    return value\n\n\ndef _normalize_query_cutoff(value: datetime, field_name: str = \"knowledge_cutoff\") -> str:\n    try:\n        return canonical_utc_iso(value, field_name)\n    except (OverflowError, OSError, TypeError, ValueError) as exc:\n        raise StoreError(\n            ErrorCode.INVALID_ARGUMENT,\n            f\"{field_name} is not a supported timestamp\",\n            context={\n                \"field\": field_name,\n                \"reason\": \"query_timestamp_invalid\",\n            },\n        ) from exc\n\n\ndef _parse_world_revision_row(row: sqlite3.Row | None) -> int:\n    if row is None:\n        raise StoreError(\n            ErrorCode.STORAGE_FAILURE,\n            \"world store is missing the world revision record\",\n            context={\"reason\": \"missing_world_revision\"},\n        )\n    try:\n        value = int(row[\"value\"])\n    except (TypeError, ValueError, OverflowError) as exc:\n        raise StoreError(\n            ErrorCode.STORAGE_FAILURE,\n            \"world store contains an invalid world revision\",\n            context={\"reason\": \"corrupt_world_revision\"},\n        ) from exc\n    if value < 0 or value > _SQLITE_INT64_MAX:\n        raise StoreError(\n            ErrorCode.STORAGE_FAILURE,\n            \"world store contains an out-of-range world revision\",\n            context={\"reason\": \"corrupt_world_revision\"},\n        )\n    return value\n\n\ndef _decode_durable_object_json(\n    raw: object,\n    *,\n    reason: str,\n    object_id: str | None = None,\n) -> dict:\n    try:\n        if not isinstance(raw, (str, bytes, bytearray)):\n            raise TypeError(\"durable JSON payload must be text or bytes\")\n        value = json.loads(raw)\n    except (json.JSONDecodeError, UnicodeError, TypeError, RecursionError) as exc:\n        context: dict[str, JsonValue] = {\"reason\": reason}\n        if object_id is not None:\n            context[\"object_id\"] = object_id\n        raise StoreError(\n            ErrorCode.STORAGE_FAILURE,\n            \"durable JSON payload is corrupt\",\n            context=context,\n        ) from exc\n    if not isinstance(value, dict):\n        context = {\"reason\": reason}\n        if object_id is not None:\n            context[\"object_id\"] = object_id\n        raise StoreError(\n            ErrorCode.STORAGE_FAILURE,\n            \"durable JSON payload has an invalid shape\",\n            context=context,\n        )\n    return value\n\n\nclass SQLiteWorldStore:\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """            row = conn.execute(\n                \"SELECT value FROM world_meta WHERE key='world_revision'\"\n            ).fetchone()\n            return int(row[\"value\"])\n""",
    """            row = conn.execute(\n                \"SELECT value FROM world_meta WHERE key='world_revision'\"\n            ).fetchone()\n            return _parse_world_revision_row(row)\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """        data = json.loads(row[\"result_json\"])\n        original_fingerprint = data.pop(_REQUEST_FINGERPRINT_KEY, None)\n""",
    """        data = _decode_durable_object_json(\n            row[\"result_json\"],\n            reason=\"corrupt_idempotency_result\",\n        )\n        original_fingerprint = data.pop(_REQUEST_FINGERPRINT_KEY, None)\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """            original_fingerprint = stored_request_fingerprint(\n                conn,\n                operation_id=str(row[\"operation_id\"]),\n                world_revision=int(row[\"world_revision\"]),\n            )\n""",
    """            try:\n                original_fingerprint = stored_request_fingerprint(\n                    conn,\n                    operation_id=str(row[\"operation_id\"]),\n                    world_revision=int(row[\"world_revision\"]),\n                )\n            except (\n                DurableJSONError,\n                json.JSONDecodeError,\n                RuntimeError,\n                TypeError,\n                ValueError,\n                OverflowError,\n            ) as exc:\n                raise StoreError(\n                    ErrorCode.STORAGE_FAILURE,\n                    \"legacy idempotency records are internally inconsistent\",\n                    context={\n                        \"idempotency_key\": lookup_key,\n                        \"operation_id\": str(row[\"operation_id\"]),\n                        \"reason\": \"corrupt_legacy_idempotency_state\",\n                    },\n                ) from exc\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """        data[\"idempotent_replay\"] = True\n        return CommitResult.model_validate(data)\n""",
    """        data[\"idempotent_replay\"] = True\n        try:\n            return CommitResult.model_validate(data)\n        except (ValidationError, TypeError, ValueError) as exc:\n            raise StoreError(\n                ErrorCode.STORAGE_FAILURE,\n                \"idempotency result payload is inconsistent with its contract\",\n                context={\n                    \"idempotency_key\": lookup_key,\n                    \"operation_id\": str(row[\"operation_id\"]),\n                    \"reason\": \"corrupt_idempotency_result\",\n                },\n            ) from exc\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """                current_world_revision = int(\n                    conn.execute(\n                        \"SELECT value FROM world_meta WHERE key='world_revision'\"\n                    ).fetchone()[\"value\"]\n                )\n""",
    """                current_world_revision = _parse_world_revision_row(\n                    conn.execute(\n                        \"SELECT value FROM world_meta WHERE key='world_revision'\"\n                    ).fetchone()\n                )\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """        if revision is not None:\n            clauses.append(\"revision=?\")\n            params.append(revision)\n        if as_of_world_revision is not None:\n            clauses.append(\"world_revision<=?\")\n            params.append(as_of_world_revision)\n        if knowledge_cutoff is not None:\n            clauses.append(\"learned_at<=?\")\n            params.append(canonical_utc_iso(knowledge_cutoff, \"knowledge_cutoff\"))\n""",
    """        if revision is not None:\n            revision = _normalize_query_integer(revision, \"revision\")\n            clauses.append(\"revision=?\")\n            params.append(revision)\n        if as_of_world_revision is not None:\n            as_of_world_revision = _normalize_query_integer(\n                as_of_world_revision, \"as_of_world_revision\"\n            )\n            clauses.append(\"world_revision<=?\")\n            params.append(as_of_world_revision)\n        if knowledge_cutoff is not None:\n            clauses.append(\"learned_at<=?\")\n            params.append(_normalize_query_cutoff(knowledge_cutoff))\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """            return json.loads(row[\"payload_json\"])\n\n    def list_payloads(\n""",
    """            return _decode_durable_object_json(\n                row[\"payload_json\"],\n                reason=\"corrupt_object_payload\",\n                object_id=object_id,\n            )\n\n    def list_payloads(\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """        \"\"\"Return the newest visible revision of each object under the supplied cutoff.\"\"\"\n        if as_of_world_revision is not None or knowledge_cutoff is not None:\n""",
    """        \"\"\"Return the newest visible revision of each object under the supplied cutoff.\"\"\"\n        if as_of_world_revision is not None:\n            as_of_world_revision = _normalize_query_integer(\n                as_of_world_revision, \"as_of_world_revision\"\n            )\n        if as_of_world_revision is not None or knowledge_cutoff is not None:\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """        with self._connection() as conn:\n            return [json.loads(row[\"payload_json\"]) for row in conn.execute(sql, tuple(params)).fetchall()]\n\n    def _list_payloads_historical(\n""",
    """        with self._connection() as conn:\n            rows = conn.execute(sql, tuple(params)).fetchall()\n        return [\n            _decode_durable_object_json(\n                row[\"payload_json\"],\n                reason=\"corrupt_object_payload\",\n            )\n            for row in rows\n        ]\n\n    def _list_payloads_historical(\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """        if as_of_world_revision is not None:\n            clauses.append(\"world_revision<=?\")\n            params.append(as_of_world_revision)\n        if knowledge_cutoff is not None:\n            clauses.append(\"learned_at<=?\")\n            params.append(canonical_utc_iso(knowledge_cutoff, \"knowledge_cutoff\"))\n""",
    """        if as_of_world_revision is not None:\n            as_of_world_revision = _normalize_query_integer(\n                as_of_world_revision, \"as_of_world_revision\"\n            )\n            clauses.append(\"world_revision<=?\")\n            params.append(as_of_world_revision)\n        if knowledge_cutoff is not None:\n            clauses.append(\"learned_at<=?\")\n            params.append(_normalize_query_cutoff(knowledge_cutoff))\n""",
)
replace_once(
    "src/aios_core/storage/sqlite_store.py",
    """            selected.append((row[\"recorded_at\"], json.loads(row[\"payload_json\"])))\n""",
    """            selected.append(\n                (\n                    row[\"recorded_at\"],\n                    _decode_durable_object_json(\n                        row[\"payload_json\"],\n                        reason=\"corrupt_object_payload\",\n                        object_id=object_id,\n                    ),\n                )\n            )\n""",
)

# Remove one-shot patch plumbing from the resulting repair commit.
Path("tools/apply_x8_x10_patch.py").unlink(missing_ok=True)
Path(".github/workflows/apply-x8-x10-repair.yml").unlink(missing_ok=True)
