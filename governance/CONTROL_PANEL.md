# AIOS 2.0 Cloud Control Panel

This is the operator-facing cloud dashboard for AIOS development. The user should not need to paste agent reports into ChatGPT. The Chief Engineer reads the cloud state directly.

Last control-plane sync: 2026-09-14
Control-plane branch: `governance/aios-control-plane`

## Current project state

- Milestone: M0 — IN PROGRESS
- Frozen through: M0-010
- Active task: M0-011 — DimensionDefinition / DimensionMembership / DimensionDerivation three-layer contract
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen base: `949e90e58bd073c1da5d23664bfcb1cb8154ebde`
- M0-012: HOLD
- Core writer mode: SINGLE-WRITER

## Role board

| Agent ID | Role | Preferred model class | Current status | Current task | Work/result location | Last authoritative result | Next action |
|---|---|---|---|---|---|---|---|
| `chief-01` | Chief Engineer | GPT-5.6 Sol-class or stronger | ACTIVE / OWNER | M0-011 — Dimension three-layer contract; taskbook marks this `总工程师亲自代码` | production branch + control plane + `reviews/`; chief result recorded by authoritative review/state updates | M0-010 FINAL PASS @ `949e90e58bd073c1da5d23664bfcb1cb8154ebde` | Design/implement/review M0-011 directly; keep M0-012 HOLD |
| `core-01` | Core Implementation Engineer | strong coding agent / Terra-class / Gemini-class | REPORT SYNC THEN IDLE | M0-010-R1 closeout only | branch `arena/01a09bc6-fantonghui`; must write `governance/agent_reports/core-01/LATEST.md` | M0-010-R1 accepted; exact-head CI Python 3.12.14, 253 passed; production R1 NO CHANGE | Publish cloud `LATEST.md`, record M0-010 FINAL PASS acknowledgement, then stop; do not start M0-011 |
| `architect-01` | Principal Architect / Red Team | GPT-6-class | STANDBY | None | future audit branch + `governance/agent_reports/architect-01/LATEST.md` | Not invoked for current task | Mandatory at M0 Gate; earlier only if routing trigger fires |
| `parallel-01` | Parallel Implementation Engineer | strong coding agent / Terra/Gemini-class | NOT AUTHORIZED | None | future isolated branch + `governance/agent_reports/parallel-01/LATEST.md` | No core assignment | Wait for `PARALLEL_SAFE` assignment |
| `parallel-02` | Parallel Implementation Engineer | strong coding agent / Terra/Gemini-class | NOT AUTHORIZED | None | future isolated branch + `governance/agent_reports/parallel-02/LATEST.md` | No core assignment | Wait for `PARALLEL_SAFE` assignment |
| `ci` | Mechanical verifier | GitHub Actions | LAST RUN PASS | exact-head regression tests | GitHub Actions | `949e90e58bd073c1da5d23664bfcb1cb8154ebde`: Python 3.12.14, 253 passed, 1 expected adversarial warning | Re-run on next production push |

## User interaction contract

The user does NOT need to copy/paste implementation summaries into the Chief Engineer chat.

The user only needs to send a short completion signal, for example:

- `core-01 做完了`
- `parallel-01 做完了`
- `architect-01 做完了`

After such a signal, the Chief Engineer MUST:

1. read this panel and `ACTIVE_ASSIGNMENTS.md`;
2. locate the agent's assigned branch and `LATEST.md` report;
3. inspect actual branch HEAD, ancestry/diff, source, tests, review artifacts, and exact-head CI;
4. never trust the report as proof by itself;
5. issue the authoritative verdict;
6. update `CURRENT_STATE.md`, this panel, and `ACTIVE_ASSIGNMENTS.md`;
7. tell the user exactly which agent ID should read the cloud next and execute.

## Agent launch contract

Core implementation agent:

`你是 core-01。去 Haneof/fantonghui 的 governance/aios-control-plane 读取 AGENTS.md，认领你当前被分配的角色和任务，按云端规则执行。完成后按 AGENT_REPORT_PROTOCOL 写回 LATEST.md 并停止。`

Principal Architect / GPT-6:

`你是 architect-01。读取云端 AGENTS.md 和你的角色/assignment；如果当前不是 ACTIVE/ESCALATED，不要自行开展架构审计。`

Future parallel agent:

`你是 parallel-01。读取云端 AGENTS.md；只有你的 assignment 标记 PARALLEL_SAFE 才开始生产施工。`

## Authority rule

- Agent reports are execution evidence, not final truth.
- Chief Engineer verdicts are authoritative project-state updates.
- Principal Architect findings are audit inputs until incorporated by the Chief Engineer.
- CI is mechanical evidence only.
