# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- 中文职位：总工程师 / 总工
- Status: AUTHORIZED / OWNER / NOT STARTED
- Task: M0-014 — Task / Wake / Session / Action / Outcome 基础契约
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Previous frozen semantic commit: `f30987395a034d4e9f826c9193dc82e00165a2e8` (M0-013 FINAL PASS)
- Parallel safety: NOT PARALLEL_SAFE for another core writer

### Authority basis

The authoritative taskbook marks M0-014 `负责人级别：总工程师亲自代码` and depends on M0-005 + M0-013.

### M0-014 high-level outcome

Freeze the five foundational active-system contracts without implementing the M2 scheduler:
- Task: type/state/Goal/priority/next wake/deadline/dependencies/completion/cancel/executions/outcomes;
- Wake: source/hits/evidence/priority/dedupe;
- Session: fixed world snapshot/execution context;
- Action: stable `execution_id` and execution status;
- Outcome: reality/result remains separate from Action and may represent unknown outcome semantics.

Required semantic proof: “reminder delivered” may complete a notification Task but does not prove “user learned”; an Action timeout must not be silently converted into success/failure if reality is unknown.

Explicit prohibitions: model context cannot substitute for persistent Task; message delivery cannot equal help success.

`core-01` must NOT start M0-014 unless this assignment is explicitly changed.

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

M0-013 FINAL PASS:

- semantic frozen commit: `f30987395a034d4e9f826c9193dc82e00165a2e8`
- formal suite: 297 passed
- Reference suite: 15 passed
- Python: 3.12.14
- exact R2 GoalStatus and Goal/Task/source-semantics boundary frozen
- formal review: `reviews/M0/M0-013_final_PASS_2026-09-14.md`

## Operator handoff rule

The human operator does not transport result text between agents. The operator may simply say a role “做完了” or “继续下一任务”; the Chief Engineer reads cloud state and actual GitHub evidence and updates the authoritative state.
