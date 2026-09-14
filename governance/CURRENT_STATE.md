# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

This file is the short cloud checkpoint used to recover project state after long conversations or agent handoffs. It must stay concise and factual.

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS
- Progress: 11/22 tasks FINAL PASS
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
- M0-011 FINAL PASS — semantic frozen commit `295d2a162f8814c9479d7281bd5988ccd2d8b6f5`

## M0-011 accepted contract

Dimension architecture is frozen into three first-class WorldObjects:

- `DimensionDefinition`: what a dimension means and its data shape/lifecycle/update metadata.
- `DimensionMembership`: which world object is mounted to which dimension, with pinned historical provenance refs.
- `DimensionDerivation`: how a higher-level dimension derives from pinned heterogeneous inputs/evidence/counterexamples.

Accepted invariants:

- `data_shape` is not curve/vector-only.
- one object may persist under multiple memberships.
- derivation inputs remain generic `ObjectRef` and can represent dimensions/events/Claims/Summaries/EvidenceSets.
- raw Observation content is referenced, not copied into dimension-private storage.
- Membership and Derivation historical/provenance refs are pinned.
- post-validation mutation remains blocked by M0-009 durable revalidation.
- R2 DimensionLifecycle exact values: `CANDIDATE, TRIAL, ACTIVE, LOW_ACTIVITY, DORMANT, MERGED, SPLIT, REVISED, REJECTED, REACTIVATED`.

Exact semantic-head CI:

- GitHub Actions run `34805946078`
- CPython 3.12.14 / pytest 8.4.2
- formal: 268 passed, 1 previously accepted adversarial warning
- Reference: 15 passed
- Reference suite is now part of GitHub Actions for every core build.

Formal review: `reviews/M0/M0-011_final_PASS_2026-09-14.md`

## Active / next task

- M0-012 — EventAnchor（事件锚点）契约与生命周期
- Status: AUTHORIZED / CHIEF ENGINEER OWNED / NOT STARTED
- Owner: `chief-01`
- Production branch: `arena/01a09bc6-fantonghui`
- M0-011 semantic base for next work: `295d2a162f8814c9479d7281bd5988ccd2d8b6f5`
- production branch also contains M0-011 review/progress archival commits after the semantic freeze
- `core-01`: IDLE / no production assignment
- `architect-01`: STANDBY; mandatory at M0 Gate, no current escalation trigger
- `parallel-01/02`: NOT AUTHORIZED

## Chief-review discipline

- Coding agents never self-declare FINAL PASS.
- Chief Engineer independently checks actual GitHub HEAD, compare/diff, source, tests, reviews, and exact-head CI.
- A task is frozen only when the Chief Engineer names the exact accepted commit.
- Frozen semantic commits may be followed by review/governance-only archival commits; those do not silently change the accepted production contract.

## Recovery rule

If chat context is lost, do not reconstruct project state from memory. Re-read:

`AGENTS.md` → `governance/CONTROL_PANEL.md` → this file → `governance/ACTIVE_ASSIGNMENTS.md` → `TASK_PROGRESS_R2.md` → current task reviews → taskbook.
