# M0-020 Review Packet

Semantic frozen commit: `426ea4c8e1292f0dd5f57e01f8663014071f7004`
Base archival HEAD before task: `ce8486f28cb94f2aa96a33bef825f3577c695b02`

## Production diff

Changed production files:
- `src/aios_core/storage/sqlite_store.py`
- `src/aios_core/query/history.py`
- `src/aios_core/query/__init__.py`

Tests:
- `tests/unit/test_history_m020.py`

## Review focus

- exact object revision reads
- as-of world revision reads
- knowledge cutoff based on learned_at
- zero future-data leakage
- combined world revision + knowledge cutoff
- latest-visible revision selection before mutable filters
- actual snapshot revision surfaced to callers
- minimal coverage surfaced to callers
- timezone-aware cutoff enforcement

## Important semantic correction

The pre-M0-020 historical list helper applied `subject_id` filtering before choosing the latest visible revision per object. Because `subject_id` is intentionally allowed to change across revisions, that could resurrect an older matching revision even when the latest visible revision belonged to a different subject. M0-020 now reconstructs the latest visible revision first and only then applies object_type/subject filters.

## CI

Run `34813251515`, job `103878594196`:
- Python 3.12.14
- formal 377 passed
- Reference 15 passed
- conclusion SUCCESS

## Scope boundary

No M1 search/navigation service is claimed. The M0 query facade is read-only and deliberately small.
