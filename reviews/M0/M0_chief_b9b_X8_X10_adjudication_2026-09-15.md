# M0 Chief Adjudication — b9b5921c X8/X9/X10

Date: 2026-09-15 (Asia/Taipei)
Role: Chief Engineer / Integrator

## Verdict

`BLOCKER FOUND / REPAIR REQUIRED`

Exact candidate rejected for production promotion:

`b9b5921c3e31a40528b0b96e689ae721c334bd7c`

Production was not modified. M1 remains frozen.

## Why this adjudication exists

A second reviewer reported a new frozen 228-case suite with 60 failures in three broad areas, but the corresponding exact 228-case artifact was not discoverable in the currently visible Git refs. Rather than treating the reported failure count as a verdict, Chief independently created minimal test-only probes directly from exact candidate b9b and adjudicated the root causes against already-frozen M0 requirements.

Audit-only branch:

`arena/chief-b9b-boundary-adjudication-20260915`

Test-only probe commit:

`125ff791c8bbdd0ac72343070789d0dece968eeb`

No implementation source was changed in that commit.

GitHub Actions:

- run: `34868790806`
- job: `104059247758`
- CPython: `3.12.14`
- Pydantic: `2.13.5`
- pytest: `8.4.2`
- collected: 558
- result: **14 failed / 544 existing formal tests passed**
- Reference step skipped only because the formal pytest command exited non-zero after the new probes failed.

The pre-existing exact b9b canonical CI remains separately green at 544 formal + 15 Reference; this adjudication demonstrates a coverage gap rather than unrelated suite breakage.

## X8 — accepted dataclass values can launder real typed-reference semantics

### Result

**M0 BLOCKER**

Five minimal probes fail:

- ObjectRef nested in dataclass under Observation.metadata, missing target: commit succeeds.
- SourceRef nested in dataclass under Observation.metadata, missing target: commit succeeds.
- ObjectRef nested in dataclass under Observation.value, missing target: commit succeeds.
- SourceRef nested in dataclass under Observation.value, missing target: commit succeeds.
- current self ObjectRef nested in dataclass: commit succeeds.

Representative shape:

```python
@dataclass(frozen=True)
class RefBox:
    ref: object

obj = Observation(..., metadata={
    "boxed": RefBox(ObjectRef(object_id="missing", revision=1))
})
store.commit([obj], request)
```

Actual: successful durable commit.

Expected boundary: a real ObjectRef/SourceRef must not become an unvalidated opaque durable dict merely because it is nested inside a caller value accepted through `Any`.

### Contract basis

M0-019 freezes recursive validation of real ObjectRef/SourceRef values before commit, including existence and current-self checks. Historical B12 additionally established that actual typed refs accepted under `Any` cannot be erased by normalization before `_collect_refs`.

This ruling does **not** add a requirement that M0 support arbitrary dataclass types as a public contract. The implementation may either:

1. recursively snapshot supported dataclass fields while preserving actual typed-reference objects until reference validation, or
2. fail closed with a protocol-level invalid-input error before persistence.

What is forbidden is the current third behavior: accept and persist the dataclass while silently erasing the embedded typed-reference semantics.

### Root cause

`SQLiteWorldStore._collect_refs()` traverses BaseModel, dict, list/tuple/set and typed refs, but not dataclass instances. The durable serialization path can nevertheless serialize such dataclass values accepted through `Any`, so the reference disappears from the validation graph.

## X9 — time and query numeric boundaries leak raw runtime exceptions

### Result

**M0 BLOCKER**

Four minimal probes fail.

### X9-a extreme timezone-aware datetime

A dirty WorldObject produced by `model_copy(update=...)` with:

```python
datetime.min.replace(tzinfo=timezone(timedelta(hours=14)))
```

in either `learned_at` or `recorded_at` reaches persistence revalidation and leaks:

`OverflowError: date value out of range`

Stack reaches `contracts/time.py::as_utc()` -> `datetime.astimezone(timezone.utc)`.

This is not a request to accept an unrepresentable timestamp. It must be rejected through the protocol boundary rather than leak a Python runtime exception.

### X9-b oversized query integers

Public M0 query calls:

```python
store.get_payload("anchor", revision=1 << 100)
store.list_payloads(as_of_world_revision=1 << 100)
```

leak:

`OverflowError: Python int too large to convert to SQLite INTEGER`

from SQLite parameter binding.

### Contract basis

M0-002 freezes unified protocol exceptions and states that Core internal exceptions are converted into protocol errors. M0-020 explicitly exposes historical read parameters including revision/world-revision/cutoff through Core query methods.

Chief freezes the repair classification as:

- invalid caller query bounds -> `INVALID_ARGUMENT`;
- invalid fresh dirty durable object/time -> `INVALID_ARGUMENT`;
- existing-key invalid/altered retry continues to obey the already-frozen idempotency-conflict priority.

## X10 — corrupt durable state leaks JSON/value exceptions instead of storage protocol errors

### Result

**M0 BLOCKER**

Five minimal probes fail:

1. malformed `object_revisions.payload_json` -> `get_payload()` leaks `JSONDecodeError`;
2. same corruption -> `list_payloads()` leaks `JSONDecodeError`;
3. malformed `idempotency_records.result_json` -> retry leaks `JSONDecodeError`;
4. legacy replay with malformed stored `operations.arguments_json` -> `stored_request_fingerprint()` leaks `JSONDecodeError`;
5. non-integer `world_meta.world_revision` -> `current_world_revision()` leaks `ValueError`.

### Contract basis

This finding does **not** require Core to repair arbitrary database corruption.

M0-002 requires internal Core/storage exceptions to be converted to protocol errors. The already-frozen Chief B5-b ruling defines internal storage/schema failures as `STORAGE_FAILURE`, and the current implementation already follows that rule for corrupt Dependency payloads and invalid stored fingerprint types.

Therefore malformed/inconsistent durable state discovered through a public storage/query/replay path must fail closed as `STORAGE_FAILURE` with diagnostic reason/context rather than leak raw parser/runtime exceptions.

## Gate decision

The following evidence remains useful regression evidence for b9b but cannot override these newly reproduced blockers:

- exact b9b formal suite: 544 passed;
- Reference suite: 15 passed;
- unchanged prior frozen 394-case suite on b9b source: 394 passed;
- separate independent frozen 94-case suite: 94 passed and final `NO NEW M0 BLOCKER FOUND`.

Those results prove prior blocker coverage; the Chief 14-case reproducer proves additional M0 coverage gaps.

Therefore:

- `b9b5921c3e31a40528b0b96e689ae721c334bd7c`: **REJECTED AS M0 PROMOTION CANDIDATE**
- PR #6: remain draft / do not merge
- production: unchanged
- M0: open
- M1: frozen

A repair must land on a new isolated candidate and must re-run formal, Reference, the frozen prior-review evidence, and targeted X8-X10 regression coverage before any production promotion.