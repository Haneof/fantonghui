# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- 中文职位：总工程师 / 总工
- Status: ACTIVE / OWNER
- Task: M0-016 — OperationRequest、审计与幂等契约
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen base: `3b4e8b603e52830d8be44d33141f722bbba244a0` (M0-015 FINAL PASS)
- Parallel safety: NOT PARALLEL_SAFE for another core writer

### Current work

The Chief Engineer is implementing and reviewing M0-016 directly.

Required contract:
- OperationRequest keeps operation_id/session_id/operation_name/arguments/expected_world_revision/reason/idempotency_key explicit;
- safe replay checks the idempotency record before optimistic world revision validation;
- a successful replay returns the original result and does not advance the world revision;
- a stale expected_world_revision on a new request returns VERSION_CONFLICT and must not overwrite concurrent work;
- committed operations remain auditable;
- do not prematurely implement M0-017 storage schema migration policy or M0-018 broader world-revision mechanics beyond what M0-016 needs.

Work already started on the production branch: OperationRequest validation was hardened and an OperationAuditRecord contract was introduced. Tests, exact-head CI, formal review, and freeze are still pending.

`core-01` must NOT start M0-016 unless this assignment is explicitly changed.

## Assignment B — `core-01` 核心程序员 / 主程序员

- Agent ID: `core-01`
- 中文职位：核心程序员 / 主程序员
- Status: IDLE
- Task: NONE
- Role prompt: `governance/roles/IMPLEMENTATION_ENGINEER.md`
- Last accepted production task: M0-010-R1
- Last cloud result: `governance/agent_reports/core-01/LATEST.md`
- Production scope: NONE

Current instruction: remain IDLE until the Chief Engineer assigns a new task.

## Assignment C — `architect-01` GPT-6 架构审计员 / GPT-6 首席架构师

- Agent ID: `architect-01`
- 中文职位：GPT-6 架构审计员 / GPT-6 首席架构师
- Status: STANDBY
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Required cloud result when invoked: `governance/agent_reports/architect-01/LATEST.md`
- Mandatory future engagement: M0 milestone Gate independent architecture/red-team audit
- Current escalation trigger: NONE
- Current instruction: DO NOT self-start

## Assignment D — `parallel-01` 并行程序员1

- Agent ID: `parallel-01`
- Status: NOT AUTHORIZED
- Task: NONE
- May start production work only when explicitly assigned and marked `PARALLEL_SAFE`.

## Assignment E — `parallel-02` 并行程序员2

- Agent ID: `parallel-02`
- Status: NOT AUTHORIZED
- Task: NONE
- May start production work only when explicitly assigned and marked `PARALLEL_SAFE`.

## Last authoritative completion

M0-015 FINAL PASS:

- semantic frozen commit: `3b4e8b603e52830d8be44d33141f722bbba244a0`
- formal suite: 329 passed
- Reference suite: 15 passed
- Python: 3.12.14
- exact-version Dependency, dependency-cycle guard, reverse impact helper frozen
- formal review: `reviews/M0/M0-015_final_PASS_2026-09-14.md`

## Operator handoff rule

The human operator does not transport result text between agents. The operator may simply say a role “做完了” or “继续下一任务”; the Chief Engineer reads cloud state and actual GitHub evidence and updates the authoritative state.
