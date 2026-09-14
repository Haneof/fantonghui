# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS / FOLLOW-UP PATCH GREEN / WAITING REQUIRED ARCHITECT RE-REVIEW
- M1: BLOCKED
- Parallel core development: BLOCKED
- Production branch: `arena/01a09bc6-fantonghui`

## Gate history

Original M0-022 Chief Gate candidate:
- `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- CI: 391 formal + 15 Reference, SUCCESS

Independent architecture red-team #1:
- governance report commit: `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- verdict: `BLOCKER FOUND`
- accepted findings: B1 idempotency aliasing, B2 Worker-isolation overclaim/threat-model mismatch, B3 durable Dependency cycle bypass

Independent red-team #2 discovered on another arena branch:
- branch: `arena/01a09edf-fantonghui`
- report commit: `42f19a3f39a1e4ac375ac315d6dcf8f487725830`
- verdict: `BLOCKER FOUND`
- important new finding: B4 floating self-reference bypasses M0-019 self-evidence guard
- additional hardening item: B5 raw SQLite exception leakage / lock behavior
- R3 ruling item: public historical "what AI knew then" query must bind world snapshot + knowledge cutoff

## Reopened contracts

Until independent re-review closes them:

- M0-015 Dependency — REOPENED / PATCHED
- M0-016 Operation/idempotency — REOPENED / PATCHED
- M0-019 reference validation — REOPENED / PATCHED

M0-001/M0-017 Worker-isolation wording remains narrowed: M0 is a trusted reviewed-code modular monolith, not a hostile-Python sandbox.
M0-020 storage/query primitives remain frozen; R3 adds a mandatory future service-binding rule rather than changing the low-level API.

## Current patch lineage

- B1/B3 semantic patch: `8ab574c6b33b2238b468c812992a92ba56ab3f71`
- B2 static-policy hardening: `e06bc80e43ea26be2be726232158cb2719092f11`
- B4/B5 semantic patch: `a99326c5034118b3a497e3be0d53ac9466445467`
- M0-018 rollback test aligned with protocol error boundary: `268d403836b107a1969a9a5d8b85e4955baec9bf`
- production progress archive after green evidence: `83577317e96224f9cdb271a8a835a4e48f3aa78c`

Exact green CI on `268d403...`:
- run `34823226166`
- job `103909332923`
- CPython 3.12.14 / pytest 8.4.2
- formal: **405 passed**, 1 known adversarial warning
- Reference: **15 passed**
- conclusion: SUCCESS

The immediately prior archive run `34822952167` intentionally exposed one stale test expectation after B5 changed the public error boundary: production correctly returned `StoreError` instead of raw `sqlite3.IntegrityError`; 404 tests passed including all five new B4/B5 probes. The stale test was then corrected, preserving rollback semantics.

## Patched semantics

### B1 idempotency

An existing idempotency key replays only when the full durable commit request fingerprint matches. Same key with any identity/payload mismatch returns `IDEMPOTENCY_CONFLICT` before stale-world checking and performs no mutation.

### B3 Dependency cycles

Whenever a commit contains Dependency objects, the durable SQLite boundary checks the union of latest durable Dependency edges and pending transaction edges. A resulting exact-version cycle is rejected with `DEPENDENCY_INVALID` before writes.

### B2 Worker isolation

M0 threat model is trusted reviewed Python code. Worker must use Core public interfaces; production wiring must not hand it DB paths, sqlite connections, or storage objects. Static checks are defense-in-depth, not sandbox proof.

### B4 floating self-reference

Any declared ObjectRef/SourceRef pointing to the same stable object with `revision=None` is rejected at the durable reference-validation boundary, because it may resolve to current/pending self and is semantically equivalent to current-revision self-evidence. Historical pinned self-links such as `X@2 -> X@1` remain legal.

### B5 protocol boundary

- reused `operation_id` with a different idempotency key now returns `IDEMPOTENCY_CONFLICT` instead of relying on a raw SQLite UNIQUE error;
- SQLite busy/lock is mapped to `VERSION_CONFLICT` / `reason=storage_busy` with an explicit busy timeout;
- raw sqlite integrity/operational exceptions are not public Core protocol responses.

## R3 — double-lens service ruling

M0-020 low-level store reads may still use world revision and knowledge cutoff independently. However, any M1 public query claiming to answer "what the AI knew then" must bind both:

1. a resolved world snapshot revision, and
2. a knowledge cutoff.

M2 Session executor must bind all Session reads to `Session.snapshot_world_revision` plus the session's knowledge-cutoff semantics. Worker must not receive raw store-read capability. These are mandatory future milestone Gates.

Chief review: `reviews/M0/M0_gate_followup_B4_B5_R3_2026-09-14.md`

## Current assignments

- `chief-01`: patch mechanically green; waiting for independent architect re-review of latest candidate
- `core-01`: IDLE
- `architect-01`: REQUIRED TO RE-REVIEW B1/B2/B3/B4/B5 + R3 before M0 can pass
- `parallel-01/02`: NOT AUTHORIZED

## Gate rule

M0 remains not passed. Chief must not authorize M1, mark M0 22/22, or enable parallel core development until architect-01 independently reviews the latest patch and returns an acceptable Gate verdict.

## Recovery rule

Read: `AGENTS.md` → `governance/CONTROL_PANEL.md` → this file → `governance/ACTIVE_ASSIGNMENTS.md` → `TASK_PROGRESS_R2.md` → `governance/agent_reports/architect-01/LATEST.md` → current Gate reviews/evidence → taskbook.
