# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- 中文职位：总工程师 / 总工
- Status: AUTHORIZED / M0 GATE OWNER / NOT STARTED
- Task: M0-022 — M0 契约总测试与冻结快照
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen semantic base: `8818dba83d97f73e3e48df97df9a18e3c450ba9d` (M0-021 FINAL PASS)
- Parallel safety: NOT PARALLEL_SAFE for another core writer until Gate passes

### Authority basis

The authoritative taskbook marks M0-022 `负责人级别：总工程师验收`, depends on M0-001~021, and forbids entering M1 before the Gate is complete.

### M0-022 required outcome

- full M0 contract regression covering schema, enums, time, refs, revisions, world revision, idempotency, knowledge cutoff, and Task/Event state machines;
- schema snapshot or stable structural hash committed under `schemas/r2/`;
- at least four required Gate fixtures: sports-day, unknown-person, future-prediction, Goal/Task separation;
- M0 Gate report with exact-head CI evidence;
- no silent foundational contract change during Gate cleanup;
- M0 FINAL PASS only after the independent architecture red-team below passes or all blockers/rulings are resolved.

`core-01` must remain IDLE until the Gate changes this assignment.

## Assignment B — `core-01` 核心程序员 / 主程序员

- Agent ID: `core-01`
- 中文职位：核心程序员 / 主程序员
- Status: IDLE
- Task: NONE
- Role prompt: `governance/roles/IMPLEMENTATION_ENGINEER.md`
- Last accepted production task: M0-010-R1
- Production scope: NONE

Current instruction: remain IDLE until the Chief Engineer assigns post-Gate M1 work.

## Assignment C — `architect-01` GPT-6 架构审计员 / GPT-6 首席架构师

- Agent ID: `architect-01`
- 中文职位：GPT-6 架构审计员 / GPT-6 首席架构师
- Status: AUTHORIZED / REQUIRED / NOT STARTED
- Task: M0 GATE INDEPENDENT ARCHITECTURE RED-TEAM
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Required cloud result: `governance/agent_reports/architect-01/LATEST.md`
- Review base: all frozen M0 semantic commits through M0-021, plus M0-022 Gate artifacts when available
- Required verdict: `ARCHITECTURE PASS | RULING REQUIRED | BLOCKER FOUND`

### Independent review requirements

Architect must independently red-team at least:
- time / learned-at / historical replay semantics;
- object revision vs global world revision;
- pinned/floating reference semantics and persistence-boundary validation;
- Claim/EvidenceSet/Event/Dimension/Goal provenance and epistemic separation;
- Dependency anti-self-evidence behavior;
- Task/Wake/Session/Action/Outcome boundaries;
- idempotency, atomic commit, concurrency, rollback, history replay;
- AI Worker raw DB isolation / permission boundary;
- Task/Event terminal-state and revision-transition discipline;
- M0 schema snapshot and Gate fixtures.

Current instruction: begin only as an independent Gate review; do not rewrite production code or self-declare M0 FINAL PASS.

## Assignment D — `parallel-01` 并行程序员1

- Agent ID: `parallel-01`
- Status: NOT AUTHORIZED
- Task: NONE
- May start production work only after M0 Gate explicitly marks a task `PARALLEL_SAFE`.

## Assignment E — `parallel-02` 并行程序员2

- Agent ID: `parallel-02`
- Status: NOT AUTHORIZED
- Task: NONE
- May start production work only after explicit assignment.

## Last authoritative completion

M0-021 FINAL PASS:

- semantic frozen commit: `8818dba83d97f73e3e48df97df9a18e3c450ba9d`
- formal suite: 385 passed
- Reference suite: 15 passed
- Python: 3.12.14
- exhaustive Task/Event transition matrices frozen
- terminal-state resurrection blocked
- revision-level transition helpers require same object and exact next revision
- formal review: `reviews/M0/M0-021_final_PASS_2026-09-14.md`

## Operator handoff rule

The human operator does not transport result text between agents. The operator may simply say a role “做完了” or “继续下一任务”; the Chief Engineer reads cloud state and actual GitHub evidence and updates the authoritative state.
