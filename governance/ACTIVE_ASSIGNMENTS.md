# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- 中文职位：总工程师 / 总工
- Status: AUTHORIZED / OWNER / NOT STARTED
- Task: M0-020 — 历史世界读取与 Knowledge Cutoff
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen base: `f1dc7cc8ca07131f75d7afe5c505f534c2f3dbe8` (M0-019 FINAL PASS)
- Parallel safety: NOT PARALLEL_SAFE for another core writer

### Authority basis

The authoritative taskbook marks M0-020 `负责人级别：总工程师亲自代码` and depends on M0-004 and M0-018.

### M0-020 required outcome

Formally freeze historical world reads and knowledge-cutoff semantics:
- read an exact object revision;
- read latest object state as of a world revision;
- read latest object state visible before a knowledge cutoff;
- combine world revision and knowledge cutoff without future leakage;
- list queries must select the newest visible revision per object under the same constraints;
- learned_at, not recorded_at alone, controls knowledge visibility;
- preserve UTC/DST-safe comparisons and historical replay;
- expose the actual historical slice cleanly for later query/workspace layers;
- do not let AI Worker bypass Core with direct SQL.

`core-01` must NOT start M0-020 unless this assignment is explicitly changed.

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

M0-019 FINAL PASS:

- semantic frozen commit: `f1dc7cc8ca07131f75d7afe5c505f534c2f3dbe8`
- formal suite: 366 passed
- Reference suite: 15 passed
- Python: 3.12.14
- reference validation mandatory at persistence boundary; public bypass removed
- missing/future refs rejected, same-transaction legal refs preserved
- current-revision self-citation rejected; historical self-link remains legal
- formal review: `reviews/M0/M0-019_final_PASS_2026-09-14.md`

## Operator handoff rule

The human operator does not transport result text between agents. The operator may simply say a role “做完了” or “继续下一任务”; the Chief Engineer reads cloud state and actual GitHub evidence and updates the authoritative state.
