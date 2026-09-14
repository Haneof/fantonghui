# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

This file is the short cloud checkpoint used to recover project state after long conversations or agent handoffs.

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS
- Progress: 12/22 tasks FINAL PASS
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
- M0-012 FINAL PASS — semantic frozen commit `5ab6ed1c21f2c3f2664104faff3494113bdd5bc1`

## M0-012 accepted contract

EventAnchor is an interpretation/anchor over the multidimensional world, not raw fact storage.

Accepted invariants:
- lifecycle values remain `CANDIDATE, ACTIVE, RESOLVED, REVISED, REJECTED, MERGED, SPLIT`;
- low-confidence candidates are legal; create never requires confidence=1;
- primary Claim refs, generic EvidenceSet refs, explicit support/counter EvidenceSet refs, and event-history refs are pinned provenance;
- participant refs may remain floating navigation by stable Entity ID;
- REVISED requires historical supersedes refs; MERGED/SPLIT retain explicit links;
- REVISED/REJECTED/MERGED/SPLIT record `revision_reason`;
- append-only revisions preserve the original event interpretation and allow world-revision replay;
- Event payload does not copy raw Observation contents;
- M0-009 persistence-boundary revalidation blocks post-validation provenance mutation.

Exact semantic-head CI:
- GitHub Actions run `34806790239`
- job `103860118133`
- CPython 3.12.14 / pytest 8.4.2
- formal: 284 passed, 1 previously accepted adversarial warning
- Reference: 15 passed

Formal review: `reviews/M0/M0-012_final_PASS_2026-09-14.md`

## Active / next task

- M0-013 — Goal（目标）一等对象
- Status: AUTHORIZED / CHIEF ENGINEER OWNED / NOT STARTED
- Owner: `chief-01`
- Production branch: `arena/01a09bc6-fantonghui`
- M0-012 semantic base for next work: `5ab6ed1c21f2c3f2664104faff3494113bdd5bc1`
- production branch also contains M0-012 review/progress archival commits after semantic freeze
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
