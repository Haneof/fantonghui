# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

This file is the short cloud checkpoint used to recover project state after long conversations or agent handoffs.

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS
- Progress: 16/22 tasks FINAL PASS
- Core development mode: SINGLE-WRITER for production contracts until M0 Gate

## Frozen tasks

- M0-001 FINAL PASS — `8197c4f`
- M0-002 FINAL PASS — `3430e13`
- M0-003 FINAL PASS — `f705e38`
- M0-004 FINAL PASS — `3678ab8`
- M0-005 FINAL PASS — `e15a0f9`
- M0-006 FINAL PASS — `eacd160`
- M0-007 FINAL PASS — `9bee623`
- M0-008 FINAL PASS — `65f1dd2`
- M0-009 FINAL PASS — `cda888f371fed812cda1b5e08d8a27db5e0c240a`
- M0-010 FINAL PASS — `949e90e58bd073c1da5d23664bfcb1cb8154ebde`
- M0-011 FINAL PASS — `295d2a162f8814c9479d7281bd5988ccd2d8b6f5`
- M0-012 FINAL PASS — `5ab6ed1c21f2c3f2664104faff3494113bdd5bc1`
- M0-013 FINAL PASS — `f30987395a034d4e9f826c9193dc82e00165a2e8`
- M0-014 FINAL PASS — `af49c27c95527ca1d2b28cddd88115b0264b48c4`
- M0-015 FINAL PASS — `3b4e8b603e52830d8be44d33141f722bbba244a0`
- M0-016 FINAL PASS — semantic frozen commit `cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3`

## M0-016 accepted contract

OperationRequest now has a hardened explicit contract for operation/session identity, arguments, expected world revision, reason, and idempotency key. Same-key replay remains ordered before optimistic concurrency validation, so exact retries return the original result without advancing world revision twice. A new-key stale writer gets VERSION_CONFLICT and is not allowed to overwrite concurrent work. Committed operations remain durably auditable and queryable across store restart.

Exact semantic-head CI:
- GitHub Actions run `34810519222`
- job `103870768750`
- CPython 3.12.14 / pytest 8.4.2
- formal: 341 passed, 1 previously accepted adversarial warning
- Reference: 15 passed
- conclusion: SUCCESS

Formal review: `reviews/M0/M0-016_final_PASS_2026-09-14.md`

## Active / next task

- M0-017 — SQLite 追加式世界存储 schema
- Status: AUTHORIZED / CHIEF ENGINEER OWNED / NOT STARTED
- Owner: `chief-01`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen semantic base: `cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3`
- Goal: formally freeze the first-stage append-only SQLite world schema, restart behavior, rollback safety, multi-revision history, WAL/transactions/indexes, and expected-revision concurrency behavior without exposing DB connections to AI Worker
- `core-01`: IDLE / no production assignment
- `architect-01`: STANDBY; mandatory at M0 Gate, no current escalation trigger
- `parallel-01/02`: NOT AUTHORIZED

## Chief-review discipline

- Coding agents never self-declare FINAL PASS.
- Chief Engineer independently checks actual GitHub HEAD, compare/diff, source, tests, reviews, and exact-head CI.
- A task is frozen only when the Chief Engineer names the exact accepted semantic commit.
- Review/progress commits after a semantic freeze do not silently redefine the frozen production contract.

## Recovery rule

If chat context is lost, re-read:
`AGENTS.md` → `governance/CONTROL_PANEL.md` → this file → `governance/ACTIVE_ASSIGNMENTS.md` → `TASK_PROGRESS_R2.md` → current task reviews → taskbook.
