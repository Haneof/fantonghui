# AIOS 2.0 Cloud Control Panel

This is the operator-facing cloud dashboard for AIOS development. The user should not need to paste agent reports into ChatGPT. The Chief Engineer reads the cloud state directly.

Last control-plane sync: 2026-09-14
Control-plane branch: `governance/aios-control-plane`

## Current project state

- Milestone: M0 — IN PROGRESS
- Frozen through: M0-009
- Active task: M0-010-R1 — Entity + Relation test hardening
- Production branch: `arena/01a09bc6-fantonghui`
- Patch base: `225eb7636f9e88f8373de32aa332eeb83c37fd16`
- M0-011: HOLD
- Core writer mode: SINGLE-WRITER

## Role board

| Agent ID | Role | Preferred model class | Current status | Current task | Work/result location | Last authoritative result | Next action |
|---|---|---|---|---|---|---|---|
| `chief-01` | Chief Engineer | GPT-5.6 Sol-class or stronger | ACTIVE | Review M0-010-R1 when submitted; maintain control plane | control plane + production branch + `reviews/` | M0-010 at `225eb76` = PATCH REQUIRED / TEST ONLY | Wait for `core-01` cloud report, independently verify, then FINAL PASS or bounded patch |
| `core-01` | Core Implementation Engineer | strong coding agent / Terra-class / Gemini-class | ASSIGNED | M0-010-R1 | branch `arena/01a09bc6-fantonghui`; required report `governance/agent_reports/core-01/LATEST.md` on that branch | M0-010 initial implementation at `225eb76`: 252 tests, production PASS, tests need patch | Read cloud assignment, execute TEST ONLY patch, push, sync report, stop |
| `architect-01` | Principal Architect / Red Team | GPT-6-class | STANDBY | None | future audit branch + `governance/agent_reports/architect-01/LATEST.md` | Not invoked for current task | Mandatory at M0 Gate; earlier only if routing trigger fires |
| `parallel-01` | Parallel Implementation Engineer | strong coding agent / Terra/Gemini-class | NOT AUTHORIZED | None | future isolated branch + `governance/agent_reports/parallel-01/LATEST.md` | No core assignment | Wait for `PARALLEL_SAFE` assignment |
| `parallel-02` | Parallel Implementation Engineer | strong coding agent / Terra/Gemini-class | NOT AUTHORIZED | None | future isolated branch + `governance/agent_reports/parallel-02/LATEST.md` | No core assignment | Wait for `PARALLEL_SAFE` assignment |
| `ci` | Mechanical verifier | GitHub Actions | LAST RUN PASS | exact-head regression tests | GitHub Actions | `225eb7636f9e88f8373de32aa332eeb83c37fd16`: Python 3.12.14, 252 passed, 1 expected adversarial warning | Re-run automatically after M0-010-R1 push |

## User interaction contract

The user does NOT need to copy/paste implementation summaries into the Chief Engineer chat.

The user only needs to send a short completion signal, for example:

- `core-01 做完了`
- `parallel-01 做完了`
- `GPT-6 / architect-01 做完了`

After such a signal, the Chief Engineer MUST:

1. read this panel and `ACTIVE_ASSIGNMENTS.md`;
2. locate the agent's assigned branch and `LATEST.md` report;
3. inspect actual branch HEAD, ancestry/diff, source, tests, review artifacts, and exact-head CI;
4. never trust the report as proof by itself;
5. issue the authoritative verdict;
6. update `CURRENT_STATE.md`, this panel, and `ACTIVE_ASSIGNMENTS.md`;
7. tell the user exactly which agent ID should read the cloud next and execute.

## Agent launch contract

The user should be able to start an agent with a short instruction such as:

`你是 core-01。去 Haneof/fantonghui 的 governance/aios-control-plane 读取 AGENTS.md，认领你当前被分配的角色和任务，按云端规则执行。`

For GPT-6:

`你是 architect-01。读取云端 AGENTS.md 和你的角色/assignment；如果当前不是 ACTIVE/ESCALATED，不要自行开展架构审计。`

For future parallel agents:

`你是 parallel-01。读取云端 AGENTS.md；只有你的 assignment 标记 PARALLEL_SAFE 时才开始生产施工。`

## Authority rule

- Agent reports are execution evidence, not final truth.
- Chief Engineer verdicts are authoritative project-state updates.
- Principal Architect findings are audit inputs until incorporated by the Chief Engineer.
- CI is mechanical evidence only.
