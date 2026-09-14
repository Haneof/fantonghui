from pathlib import Path

path = Path("src/aios_core/storage/sqlite_store.py")
text = path.read_text(encoding="utf-8")
old = '''def _normalize_query_cutoff(value: datetime, field_name: str = "knowledge_cutoff") -> str:\n    try:\n        return canonical_utc_iso(value, field_name)\n    except (OverflowError, OSError, TypeError, ValueError) as exc:\n        raise StoreError(\n            ErrorCode.INVALID_ARGUMENT,\n            f"{field_name} is not a supported timestamp",\n            context={\n                "field": field_name,\n                "reason": "query_timestamp_invalid",\n            },\n        ) from exc\n'''
new = '''def _normalize_query_cutoff(value: datetime, field_name: str = "knowledge_cutoff") -> str:\n    # Preserve the already-frozen public contract for naive datetimes: callers\n    # receive the original ValueError. Protocol mapping applies to aware values\n    # that still fail canonical UTC conversion (for example datetime overflow).\n    if isinstance(value, datetime) and (\n        value.tzinfo is None or value.utcoffset() is None\n    ):\n        return canonical_utc_iso(value, field_name)\n    try:\n        return canonical_utc_iso(value, field_name)\n    except (AttributeError, OverflowError, OSError, TypeError, ValueError) as exc:\n        raise StoreError(\n            ErrorCode.INVALID_ARGUMENT,\n            f"{field_name} is not a supported timestamp",\n            context={\n                "field": field_name,\n                "reason": "query_timestamp_invalid",\n            },\n        ) from exc\n'''
if text.count(old) != 1:
    raise RuntimeError(f"expected exactly one cutoff helper, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
Path("tools/fix_cutoff_contract_compat.py").unlink(missing_ok=True)
Path(".github/workflows/apply-cutoff-contract-compat.yml").unlink(missing_ok=True)
