# AIOS 2.0 Current State

Last authoritative update: 2026-09-14

This file is the short cloud checkpoint used to recover project state after long conversations or agent handoffs.

## Current milestone

- Milestone: M0 — freeze world contracts and core storage
- Status: IN PROGRESS / GATE NEXT
- Progress: 21/22 tasks FINAL PASS
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
- M0-016 FINAL PASS — `cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3`
- M0-017 FINAL PASS — `c9bd2d85ff0047515f6f4cc5b9e7058c70cff6dc`
- M0-018 FINAL PASS — `f00735193e09b6a337ade39dc040510c003d8f54`
- M0-019 FINAL PASS — `f1dc7cc8ca07131f75d7afe5c505f534c2f3dbe8`
- M0-020 FINAL PASS — `426ea4c8e1292f0dd5f57e01f8663014071f7004`
- M0-021 FINAL PASS — semantic frozen commit `8818dba83d97f73e3e48df97df9a18e3c450ba9d`

## M0-021 accepted contract

Task and Event legal transition matrices are explicit and exhaustively tested. Task terminal states cannot restart; Event MERGED/SPLIT are terminal. The mandatory canaries RUNNING->WAITING_RESULT and CANDIDATE->REJECTED are legal, while COMPLETED->RUNNING and MERGED->ACTIVE are rejected. Revision-level transition validators require the same object_id and exactly revision+1 before accepting the state transition, so a state change is represented as new append-only history rather than an in-place durable update.

Exact semantic-head CI:
- GitHub Actions run `34813790092`
- job `103880165317`
- CPython 3.12.14 / pytest 8.4.2
- formal: 385 passed, 1 previously accepted adversarial warning
- Reference: 15 passed
- conclusion: SUCCESS

Formal review: `reviews/M0/M0-021_final_PASS_2026-09-14.md`

## Active / next task

- M0-022 — M0 契约总测试与冻结快照 / M0 Gate
- Status: AUTHORIZED / CHIEF ENGINEER GATE / NOT STARTED
- Chief owner: `chief-01`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen semantic base through M0-021: `8818dba83d97f73e3e48df97df9a18e3c450ba9d`
- Goal: full M0 contract regression, schema snapshot/hash, required fixtures, gate report, and explicit freeze before M1
- `core-01`: IDLE / no production assignment
- `architect-01`: AUTHORIZED / REQUIRED FOR M0 GATE / NOT STARTED; independent GPT-6-class red-team must pass before M0 FINAL PASS and before M1
- `parallel-01/02`: NOT AUTHORIZED until M0 Gate passes

## Chief-review discipline

- Coding agents never self-declare FINAL PASS.
- Chief Engineer independently checks actual GitHub HEAD, compare/diff, source, tests, reviews, and exact-head CI.
- A task is frozen only when the Chief Engineer names the exact accepted commit.
- Review/progress commits after a semantic freeze do not silently redefine the frozen production contract.
- M0-022 cannot be signed FINAL PASS from CI alone; the independent GPT-6 architecture red-team is mandatory.

## Recovery rule

If chat context is lost, re-read:
`AGENTS.md` → `governance/CONTROL_PANEL.md` → this file → `governance/ACTIVE_ASSIGNMENTS.md` → `TASK_PROGRESS_R2.md` → current task reviews → taskbook.
