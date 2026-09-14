# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

This file is the short cloud checkpoint used to recover project state after long conversations or agent handoffs.

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS
- Progress: 14/22 tasks FINAL PASS
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
- M0-014 FINAL PASS — semantic frozen commit `af49c27c95527ca1d2b28cddd88115b0264b48c4`

## M0-014 accepted contract

The active system now has five durable first-class objects: Task, Wake, Session, Action, Outcome.

Accepted invariants:
- future work must survive as durable Task state; model context is not a Task store;
- Task remains distinct from Goal and keeps type/state/priority/time/dependencies/completion/cancel/execution/outcome fields;
- Task reason/execution/outcome history refs are pinned provenance, while Goal/dependency/entity links retain generic navigation semantics;
- Wake is a separate WorldObject with source/hit times/hit count/evidence/priority/dedupe; wake evidence is pinned;
- Wake time ordering compares UTC instants, not wall-clock fields;
- Session pins its originating Wake and freezes a world revision plus operation IDs/checkpoint for later recovery;
- Action carries a stable execution_id and pins the exact Task revision when linked;
- Outcome is separate from Action; action/evidence refs are pinned and outcome may remain `unknown`;
- Action completion or message delivery never implies user acceptance, Goal improvement, or learning success;
- M0-009 persistence-boundary revalidation blocks post-validation mutation of active-system provenance;
- M0-014 does not implement the scheduler/runtime; those mechanics remain later work.

Exact semantic-head CI:
- GitHub Actions run `34807928978`
- job `103863350345`
- CPython 3.12.14 / pytest 8.4.2
- formal: 315 passed, 1 previously accepted adversarial warning
- Reference: 15 passed

Formal review: `reviews/M0/M0-014_final_PASS_2026-09-14.md`

## Active / next task

- M0-015 — Dependency（依赖）契约
- Status: AUTHORIZED / CHIEF ENGINEER OWNED / NOT STARTED
- Owner: `chief-01`
- Production branch: `arena/01a09bc6-fantonghui`
- M0-014 semantic base for next work: `af49c27c95527ca1d2b28cddd88115b0264b48c4`
- Goal: record exact dependency versions for later correction/review and reverse lookup; ordinary semantic links must not be confused with evidence dependency
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
