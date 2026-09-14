# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

This file is the short cloud checkpoint used to recover project state after long conversations or agent handoffs. It must stay concise and factual.

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS
- Core development mode: SINGLE-WRITER for production contracts until M0 Gate

## Frozen tasks

- M0-001 FINAL PASS — frozen commit `8197c4f`
- M0-002 FINAL PASS — frozen commit `3430e13`
- M0-003 FINAL PASS — frozen commit `f705e38`
- M0-004 FINAL PASS — frozen commit `3678ab8`
- M0-005 FINAL PASS — frozen commit `e15a0f9`
- M0-006 FINAL PASS — frozen commit `eacd160`
- M0-007 FINAL PASS — frozen commit `9bee623`
- M0-008 FINAL PASS — frozen commit `65f1dd2`
- M0-009 FINAL PASS — frozen commit `cda888f371fed812cda1b5e08d8a27db5e0c240a`

## Active task

- M0-010 — Entity + Relation contract
- Status: PATCH REQUIRED / TEST ONLY
- Production branch: `arena/01a09bc6-fantonghui`
- Reviewed implementation HEAD: `225eb7636f9e88f8373de32aa332eeb83c37fd16`
- Production Entity/Relation validators: PASS / FROZEN pending final test hardening
- M0-011: HOLD

## Current blockers

Chief review of M0-010 found two test-contract defects:

1. `ER01` contains a false-green `assert "object_type" in e_hints or True` and does not actually freeze Entity/Relation `object_type` annotations as exact `Literal[...]` types.
2. `ER18` uses nonexistent Relation endpoint entity IDs. If durable persistence revalidation is removed, reference validation can fail on missing endpoints before the intended floating `evidence_set_refs` bypass is exercised, so the adversarial test does not prove the claimed failure mode. ER18 must use real committed Entity endpoints.

The patch must be test-only; no `src/aios_core/**` production change is authorized.

## Recent architectural freeze

M0-009 additionally froze a generic durable-write invariant:

`SQLiteWorldStore.commit` must revalidate the complete current Pydantic object graph before durable writes so post-validation mutation cannot bypass object contracts.

The preserved order is:

idempotency replay → expected world revision → persistence revalidation → revision/type validation → reference validation → durable write.

## Chief-review discipline

- Coding agents never self-declare FINAL PASS.
- Chief Engineer independently checks actual GitHub HEAD, compare/diff, source, tests, reviews, and exact-head CI.
- A task is frozen only when the Chief Engineer names the exact accepted commit.
- The next core task remains HOLD until the current task is FINAL PASS.

## Recovery rule

If chat context is lost, do not reconstruct project state from memory. Re-read:

`AGENTS.md` → this file → `TASK_PROGRESS_R2.md` → `ACTIVE_ASSIGNMENTS.md` → current task reviews → taskbook.
