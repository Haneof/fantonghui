# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- 中文职位：总工程师 / 总工
- Status: AUTHORIZED / OWNER / NOT STARTED
- Task: M0-012 — EventAnchor（事件锚点）契约与生命周期
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Previous frozen semantic commit: `295d2a162f8814c9479d7281bd5988ccd2d8b6f5` (M0-011 FINAL PASS)
- Parallel safety: NOT PARALLEL_SAFE for another core writer

### Authority basis

The authoritative taskbook marks M0-012 `负责人级别：总工程师亲自代码`.

### M0-012 high-level outcome

EventAnchor must be an interpretation/anchor over the multidimensional world, not a raw collection fact. It must support candidate → active/resolved and later revised/rejected/merged/split history without overwriting prior revisions. Exact design and tests must be re-read from the taskbook before implementation.

`core-01` must NOT start M0-012 unless this assignment is explicitly changed.

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

M0-011 FINAL PASS:

- semantic frozen commit: `295d2a162f8814c9479d7281bd5988ccd2d8b6f5`
- formal suite: 268 passed
- Reference suite: 15 passed
- Python: 3.12.14
- three-layer dimension contract frozen
- exact R2 DimensionLifecycle frozen
- Reference suite added to GitHub Actions

## Operator handoff rule

The human operator does not transport result text between agents.

The operator may simply say:
- `核心程序员做完了`
- `GPT-6架构审计员做完了`
- `并行程序员1做完了`
- `总工程师继续下一任务`

The Chief Engineer then reads cloud state and actual GitHub evidence, issues the authoritative verdict, and updates the cloud control plane.
