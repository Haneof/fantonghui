# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- 中文职位：总工程师 / 总工
- Status: WAITING FOR REQUIRED ARCHITECT RED-TEAM
- Task: M0-022 — M0 契约总测试与冻结快照 / M0 Gate
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen semantic base: `8818dba83d97f73e3e48df97df9a18e3c450ba9d` (M0-021 FINAL PASS)
- Chief Gate candidate: `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- Parallel safety: NOT PARALLEL_SAFE until Gate FINAL PASS

### Chief-side Gate result

- schema/hash snapshot committed under `schemas/r2/`;
- required sports-day / unknown-person / future-prediction / Goal-Task-separation fixtures committed;
- no production semantic implementation changed during Gate preparation;
- exact candidate CI run `34814629456`, job `103882644741`: formal 391 passed + Reference 15, SUCCESS;
- formal Chief readiness review exists at `reviews/M0/M0-022_chief_gate_ready_2026-09-14.md`;
- M0 remains 21/22 FINAL PASS until Assignment C completes and Chief resolves its verdict.

Current instruction: do not authorize M1 and do not sign M0 FINAL PASS before the required architecture report is reviewed.

## Assignment B — `core-01` 核心程序员 / 主程序员

- Agent ID: `core-01`
- 中文职位：核心程序员 / 主程序员
- Status: IDLE
- Task: NONE
- Role prompt: `governance/roles/IMPLEMENTATION_ENGINEER.md`
- Production scope: NONE

Current instruction: remain IDLE until M0 Gate passes and Chief assigns post-Gate work.

## Assignment C — `architect-01` GPT-6 架构审计员 / GPT-6 首席架构师

- Agent ID: `architect-01`
- 中文职位：GPT-6 架构审计员 / GPT-6 首席架构师
- Status: AUTHORIZED / REQUIRED / READY TO START
- Task: M0 GATE INDEPENDENT ARCHITECTURE RED-TEAM
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Review request: `governance/agent_reports/architect-01/REQUEST.md`
- Required cloud result: `governance/agent_reports/architect-01/LATEST.md`
- Review base: frozen M0 semantics through `8818dba83d97f73e3e48df97df9a18e3c450ba9d` plus Gate candidate `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- Required verdict: `ARCHITECTURE PASS | RULING REQUIRED | BLOCKER FOUND`

### Independent review requirements

Architect must independently red-team at least:
- time / learned-at / historical replay / future-data leakage;
- object revision vs global world revision;
- pinned/floating reference semantics and persistence-boundary validation;
- Claim/EvidenceSet/Event/Dimension/Goal provenance and epistemic separation;
- Dependency anti-self-evidence behavior;
- Task/Wake/Session/Action/Outcome boundaries;
- idempotency, atomic commit, concurrent writers, rollback, history replay;
- AI Worker raw DB isolation / permission boundary;
- Task/Event terminal-state and revision-transition discipline;
- M0 schema snapshot and all four Gate fixtures.

Current instruction: independently inspect source and evidence; do not rewrite production code and do not self-declare M0 FINAL PASS. Write `LATEST.md` with one required verdict and explicit residual risks/counterexamples.

## Assignment D — `parallel-01` 并行程序员1

- Agent ID: `parallel-01`
- Status: NOT AUTHORIZED
- Task: NONE
- May start production work only after M0 Gate explicitly authorizes a `PARALLEL_SAFE` task.

## Assignment E — `parallel-02` 并行程序员2

- Agent ID: `parallel-02`
- Status: NOT AUTHORIZED
- Task: NONE
- May start production work only after explicit assignment.

## Operator handoff rule

The human operator does not transport result text between agents. When `architect-01` finishes, the operator may simply say `GPT-6架构审计员做完了`; the Chief Engineer reads `LATEST.md`, actual GitHub evidence, and decides the Gate.
