# AIOS 2.0 Agent Bootstrap

This repository uses GitHub as the cloud source of truth for AI-assisted development.

Before doing any work, every AI agent MUST read, in order:

1. `governance/CONTROL_PANEL.md`
2. `governance/CURRENT_STATE.md`
3. `TASK_PROGRESS_R2.md`
4. `governance/ROLE_REGISTRY.md`
5. `governance/MODEL_ROUTING_POLICY.md`
6. `governance/MULTI_AGENT_POLICY.md`
7. `governance/ACTIVE_ASSIGNMENTS.md`
8. `governance/AGENT_REPORT_PROTOCOL.md`
9. The role prompt named by the assignment under `governance/roles/`
10. The authoritative taskbook: `AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
11. The current task's latest file under `reviews/` and `reviews/*/evidence/`

## Non-negotiable rules

- The taskbook and constitution/R1/R2 files are architectural authority. Do not silently reinterpret them.
- A coding agent may report `CODE COMPLETE`, `PATCH COMPLETE`, `BLOCKED`, or `WAITING CHIEF REVIEW`. It MUST NOT declare `FINAL PASS`.
- Only the Chief Engineer may issue `FINAL PASS`, freeze a commit, authorize the next core task, or change shared architectural contracts.
- Do not start a task unless it appears in `governance/ACTIVE_ASSIGNMENTS.md` or the Chief Engineer explicitly authorizes it in the current instruction.
- Do not modify files outside the assignment's allowed scope. If the task requires scope expansion, STOP and report the exact reason.
- Do not change a previously FINAL PASS core contract without Chief Engineer escalation. If a frozen contract must change, the task is escalated according to `MODEL_ROUTING_POLICY.md`.
- Coding agents update execution evidence and progress, but never rewrite architectural history.
- All durable review evidence belongs in `reviews/`.
- Every production change must be backed by tests and exact Git/CI evidence.
- Every ACTIVE execution agent must publish/update `governance/agent_reports/<agent_id>/LATEST.md` on its assigned working branch before announcing completion.
- Never invent commit hashes, CI status, test counts, or file contents.

## Startup response

After reading the required cloud files, an agent should identify:

- agent_id
- assigned role
- assigned task
- branch
- frozen/base commit
- allowed files
- forbidden files
- required tests
- required `LATEST.md` report path
- escalation conditions

If any of these are ambiguous, STOP rather than guessing.

## Completion response

After committing/pushing authorized work, update the agent report required by `AGENT_REPORT_PROTOCOL.md`, then stop at the status allowed by the assignment. The user should not need to copy the report into another chat.
