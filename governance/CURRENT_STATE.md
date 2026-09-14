# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS / GATE BLOCKERS PATCHED / WAITING ARCHITECT RE-REVIEW
- M1: BLOCKED
- Parallel core development: BLOCKED
- Production branch: `arena/01a09bc6-fantonghui`

## Gate history

Original M0-022 Chief Gate candidate:
- `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- CI: 391 formal + 15 Reference, SUCCESS

Independent architecture red-team:
- report commit: `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- verdict: `BLOCKER FOUND`
- blockers accepted by Chief: B1 idempotency aliasing, B2 Worker isolation overclaim/threat-model mismatch, B3 Dependency cycle guard not connected to durable write boundary

## Reopened contracts

The Gate invalidated the previous closure of two foundational contracts until patch re-review:

- M0-015 Dependency — REOPENED for durable cycle rejection
- M0-016 Operation/idempotency — REOPENED for altered-request conflict semantics

M0-001/M0-017 Worker-isolation wording is narrowed by Chief architectural ruling: M0 is a trusted reviewed-code modular-monolith dependency boundary, not a hostile-Python sandbox.

## Current patch candidate

Chief patch lineage includes:
- semantic B1/B3 patch: `8ab574c6b33b2238b468c812992a92ba56ab3f71`
- B2 static-policy hardening: `e06bc80e43ea26be2be726232158cb2719092f11`
- Chief blocker-resolution ruling/review: `8b3bca9ef3bf8fde2ee09b73a2631a3a2f12db0a`

Exact-head CI on `8b3bca9...`:
- run `34821050459`
- job `103902471146`
- CPython 3.12.14 / pytest 8.4.2
- formal: **400 passed**, 1 known adversarial warning
- Reference: **15 passed**
- conclusion: SUCCESS

## Patched semantics

### B1 idempotency

An existing idempotency key now replays only when the entire durable commit request fingerprint matches: operation identity/session/name/arguments/expected revision/reason/key plus intended object IDs/revisions and canonical payloads. Object input order is ignored. Same key with any mismatch returns `IDEMPOTENCY_CONFLICT` before stale-world checking and performs no mutation.

The fingerprint is reconstructed from the atomically persisted `operations` row and the operation world revision's `object_revisions`; no runtime schema ALTER is introduced, preserving compatibility with M0 databases.

### B3 Dependency cycles

Whenever a commit contains Dependency objects, the durable SQLite write boundary now builds the current Dependency graph from latest durable Dependency revisions plus pending transaction revisions and rejects a resulting exact-version cycle with `DEPENDENCY_INVALID` / `reason=dependency_cycle` before any write.

Relation cycles remain legal. Persistent reverse indexes and correction propagation remain later work.

### B2 Worker isolation threat model

M0 does not claim a hostile Python sandbox inside one interpreter. The enforceable M0 rule is trusted reviewed code + architecture dependency policy: AI Worker must use Core public interfaces and production wiring must not hand it DB paths, sqlite connections, or storage objects. Static checks now also catch the red-team's obvious constant-string dynamic-import examples. A stronger process/capability boundary becomes mandatory if the future threat model permits untrusted executable code.

Chief review: `reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`

## Current assignments

- `chief-01`: patch verified mechanically; preparing independent architect re-review
- `core-01`: IDLE
- `architect-01`: REQUIRED TO RE-REVIEW B1/B2/B3 patch before M0 can pass
- `parallel-01/02`: NOT AUTHORIZED

## Gate rule

M0 remains not passed. Chief must not authorize M1 or sign M0-022 FINAL PASS until `architect-01` independently verifies the patched branch and returns an acceptable Gate verdict.

## Recovery rule

Read: `AGENTS.md` → `governance/CONTROL_PANEL.md` → this file → `governance/ACTIVE_ASSIGNMENTS.md` → `TASK_PROGRESS_R2.md` → `governance/agent_reports/architect-01/LATEST.md` → current Gate reviews/evidence → taskbook.
