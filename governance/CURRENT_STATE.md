# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS / THIRD GATE PATCH GREEN / WAITING REQUIRED ARCHITECT RE-REVIEW
- M1: BLOCKED
- Parallel core development: BLOCKED
- Production branch: `arena/01a09bc6-fantonghui`

## Gate / red-team history

Original M0-022 Chief Gate candidate:
- `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- CI: 391 formal + 15 Reference, SUCCESS

Independent red-team #1:
- report commit `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- verdict `BLOCKER FOUND`
- B1/B2/B3

Independent red-team #2:
- branch `arena/01a09edf-fantonghui`
- report commit `42f19a3f39a1e4ac375ac315d6dcf8f487725830`
- verdict `BLOCKER FOUND`
- B4/B5/R3

Architect formal re-review of candidate `268d403...`:
- governance report commit `c068fc1fa0de528ab17cbfc4a4c6f9112b3ae164`
- verdict `BLOCKER FOUND`
- new blockers B6/B7
- B5 not fully closed
- R4 EvidenceSet cutoff ruling required
- B2/B3/B4 narrow fixes independently accepted
- R3 accepted as M1/M2 future Gate

## Chief rulings after latest report

### B6

Idempotency identity must be calculated from the same normalized representation used for durable persistence. Exact stale replay priority remains unchanged.

### B7

OperationRequest is revalidated at the durable boundary for new writes after replay/conflict + expected-world checks and before WorldObject persistence validation/writes.

### B5

M0-002 and M0-017 reopened. New protocol code:

`STORAGE_FAILURE`

- busy/locked => `VERSION_CONFLICT / storage_busy`
- connect unavailable => `STORAGE_FAILURE / storage_unavailable`
- internal integrity/operational/database faults => `STORAGE_FAILURE` with machine-readable reason
- raw sqlite errors are not public Core protocol

### R4

M0-009 and M0-019 reopened. EvidenceSet typed refs must be visible at the EvidenceSet's own `knowledge_window.knowledge_cutoff`, not merely at EvidenceSet.learned_at. Full world-revision materialization remains M1-006 scope.

### recorded_at

Chief ruling: `recorded_at` is controlled AIOS/simulator recording time; `world_commits.committed_at` is physical durable DB commit time. M1 ingestion must police ordinary production callers from forging knowledge time while simulator/import paths retain provenance.

## Current patch lineage

Earlier:
- B1/B3: `8ab574c6b33b2238b468c812992a92ba56ab3f71`
- B2: `e06bc80e43ea26be2be726232158cb2719092f11`
- B4/B5 first patch: `a99326c5034118b3a497e3be0d53ac9466445467`

Latest semantic repair:
- `f38fdd2aa64e31b92c5353206a8aef62c9322087`

Current exact green candidate including approved snapshot change:
- `9c080f693917c2c99bfbe6aa924e5f3cb54744a0`

Production review/progress archive currently newer than candidate; those documentation commits do not redefine the semantic candidate.

## CI evidence

Expected structural-drift run after adding `STORAGE_FAILURE`:
- run `34827058782`
- job `103921528459`
- 417 functional tests passed
- exactly one failure: frozen schema snapshot still represented the old ErrorCode set / old ErrorResponse schema
- Reference skipped because formal stage failed
- failure is preserved, not hidden

Latest exact green candidate `9c080f...`:
- run `34827250470`
- job `103922130589`
- CPython 3.12.14 / pytest 8.4.2
- formal **418 passed**, 1 known adversarial warning
- Reference **15 passed**
- SUCCESS

Chief review:
`reviews/M0/M0_gate_B6_B7_B5_R4_resolution_2026-09-14.md`

## Reopened contracts

Waiting for architect re-review:
- M0-002 — REOPENED / PATCHED
- M0-009 — REOPENED / PATCHED
- M0-016 — REOPENED / PATCHED
- M0-017 — REOPENED / PATCHED
- M0-019 — REOPENED / PATCHED
- M0-022 — BLOCKED / PATCH CANDIDATE GREEN

M0-015 is restored to FINAL PASS after the latest independent architect re-review confirmed the durable Dependency-cycle repair in its bounded M0 scope. This does not claim M3 correction propagation/reverse-index completion.

## Current assignments

- `chief-01`: repair mechanically verified; waiting architect re-review
- `core-01`: IDLE
- `architect-01`: AUTHORIZED / REQUIRED to independently attack candidate `9c080f...`
- `parallel-01/02`: NOT AUTHORIZED

## Gate rule

M0 remains not passed. Chief must not authorize M1, mark M0 22/22, or enable parallel core development until architect-01 independently reviews the latest candidate and returns an acceptable verdict, followed by chief-01 final Gate ruling.

## Recovery rule

Read: `AGENTS.md` → `governance/CONTROL_PANEL.md` → this file → `governance/ACTIVE_ASSIGNMENTS.md` → `TASK_PROGRESS_R2.md` → `governance/agent_reports/architect-01/LATEST.md` → `REREVIEW_REQUEST.md` → current Gate reviews/evidence → taskbook.
