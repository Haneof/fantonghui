from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"missing patch anchor in {path}: {old[:120]!r}")
    if text.count(old) != 1:
        raise RuntimeError(f"non-unique patch anchor in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


STORE = "src/aios_core/storage/sqlite_store.py"

replace_once(
    STORE,
    '''from aios_core.storage.idempotency import (\n    normalize_operation_for_persistence,\n    normalize_world_object_for_persistence,\n    request_fingerprint,\n    stored_request_fingerprint,\n)\n''',
    '''from aios_core.storage.idempotency import (\n    canonical_json_dumps,\n    normalize_operation_for_persistence,\n    normalize_world_object_for_persistence,\n    request_fingerprint,\n    stored_request_fingerprint,\n)\n''',
)

replace_once(
    STORE,
    '''        except sqlite3.OperationalError as exc:\n            message = str(exc).lower()\n            if "locked" in message or "busy" in message:\n                raise StoreError(\n                    ErrorCode.VERSION_CONFLICT,\n                    "world store is busy; retry from a fresh snapshot",\n                    context={"reason": "storage_busy"},\n                ) from exc\n            reason = "storage_unavailable" if conn is None else "sqlite_operational_error"\n            raise StoreError(\n                ErrorCode.STORAGE_FAILURE,\n                "SQLite storage operation failed",\n                context={"reason": reason},\n            ) from exc\n''',
    '''        except sqlite3.OperationalError as exc:\n            sqlite_code = getattr(exc, "sqlite_errorcode", None)\n            base_code = sqlite_code & 0xFF if isinstance(sqlite_code, int) else None\n            if base_code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:\n                raise StoreError(\n                    ErrorCode.VERSION_CONFLICT,\n                    "world store is busy; retry from a fresh snapshot",\n                    context={\n                        "reason": "storage_busy",\n                        "sqlite_errorcode": sqlite_code,\n                    },\n                ) from exc\n            reason = "storage_unavailable" if conn is None else "sqlite_operational_error"\n            raise StoreError(\n                ErrorCode.STORAGE_FAILURE,\n                "SQLite storage operation failed",\n                context={\n                    "reason": reason,\n                    "sqlite_errorcode": sqlite_code,\n                },\n            ) from exc\n''',
)

replace_once(
    STORE,
    '''                for obj in object_list:\n                    payload = obj.model_dump_json()\n                    conn.execute(\n''',
    '''                for obj in object_list:\n                    payload = canonical_json_dumps(\n                        obj.model_dump(mode="python", round_trip=True)\n                    )\n                    conn.execute(\n''',
)

replace_once(
    STORE,
    '''                        json.dumps(operation.arguments, ensure_ascii=False, default=str),\n''',
    '''                        canonical_json_dumps(operation.arguments),\n''',
)

# The reproducer remains in-tree as the permanent regression proof.
Path(".github/workflows/m0-gate-b8-b9-patch.yml").unlink(missing_ok=True)
Path("tools/apply_m0_gate_b8_b9_patch.py").unlink(missing_ok=True)
try:
    Path("tools").rmdir()
except OSError:
    pass
