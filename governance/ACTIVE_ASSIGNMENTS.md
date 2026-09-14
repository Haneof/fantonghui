# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- 中文职位：总工程师 / 总工
- Status: AUTHORIZED / OWNER / NOT STARTED
- Task: M0-021 — Task / Event 状态机冻结
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen base: `426ea4c8e1292f0dd5f57e01f8663014071f7004` (M0-020 FINAL PASS)
- Parallel safety: NOT PARALLEL_SAFE for another core writer

### Authority basis

The authoritative taskbook marks M0-021 `负责人级别：总工程师亲自代码` and depends on M0-012 and M0-014.

### M0-021 required outcome

Formally freeze Task and Event state-machine semantics:
- legal Task transitions are encoded as an explicit matrix;
- legal Event transitions are encoded as an explicit matrix;
- `RUNNING -> WAITING_RESULT` is legal;
- `COMPLETED -> RUNNING` is rejected;
- `CANDIDATE -> REJECTED` is legal;
- `MERGED -> ACTIVE` is rejected;
- state changes are represented by a new object revision rather than a durable in-place UPDATE;
- service-layer transition helpers must not silently bypass the validators;
- no M1/M2 scheduler behavior is pulled into this task.

`core-01` must NOT start M0-021 unless this assignment is explicitly changed.

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

M0-020 FINAL PASS:

- semantic frozen commit: `426ea4c8e1292f0dd5f57e01f8663014071f7004`
- formal suite: 377 passed
- Reference suite: 15 passed
- Python: 3.12.14
- exact object/world-revision + learned-at knowledge-cutoff reads frozen
- zero future-data leakage regression covered
- historical latest-visible selection precedes mutable subject filtering
- query facade reports actual snapshot revision and minimal coverage
- formal review: `reviews/M0/M0-020_final_PASS_2026-09-14.md`

## Operator handoff rule

The human operator does not transport result text between agents. The operator may simply say a role “做完了” or “继续下一任务”; the Chief Engineer reads cloud state and actual GitHub evidence and updates the authoritative state.
