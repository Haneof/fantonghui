# AIOS 2.0 Agent Report Protocol

This protocol removes the need for the user to copy/paste agent completion reports into the Chief Engineer conversation.

## Required per-agent report

Every execution agent with an ACTIVE assignment MUST maintain one cloud result file on its assigned working branch:

`governance/agent_reports/<agent_id>/LATEST.md`

Examples:

- `governance/agent_reports/core-01/LATEST.md`
- `governance/agent_reports/parallel-01/LATEST.md`
- `governance/agent_reports/architect-01/LATEST.md`

The report is execution evidence only. It never grants FINAL PASS.

## Required report fields

```text
# <agent_id> latest report

agent_id:
role:
task:
status: CODE COMPLETE | PATCH COMPLETE | BLOCKED | WAITING CHIEF REVIEW
working_branch:
base_commit:
head_commit:
production_files_changed:
tests_run:
test_result:
reference_result:
ci_status:
review_artifacts:
known_issues:
requested_chief_action:
```

For architecture/red-team agents, use:

```text
status: ARCHITECTURE PASS | RULING REQUIRED | BLOCKER FOUND
```

and include:

- audited scope
- counterexamples found
- frozen contracts affected
- recommendation
- residual risks

## Write timing

The agent MUST update `LATEST.md` after it has:

1. completed or blocked its assigned work;
2. committed and pushed all authorized repository changes;
3. written task review/evidence artifacts;
4. recorded the exact pushed HEAD;
5. recorded CI truth if visible, otherwise `CI_PENDING_CHIEF_VERIFICATION`.

The report must describe the repository state that actually exists at its named HEAD.

## Chief Engineer consumption

When the user says an agent is done, the Chief Engineer reads:

1. `governance/CONTROL_PANEL.md`
2. `governance/ACTIVE_ASSIGNMENTS.md`
3. the agent's `LATEST.md`
4. the actual assigned branch HEAD/diff/source/tests/reviews/CI

The Chief Engineer does not require the user to paste the report into chat.

The report is a locator and summary, not proof. Actual GitHub state is the proof.

## Stale-report rule

If `LATEST.md.head_commit` does not equal the current assigned branch HEAD, the report is STALE. The Chief Engineer must inspect the newer branch state and may require the agent to refresh its report before review.

## Multi-agent rule

Every concurrently active agent must have a distinct `agent_id`, assignment, branch, owned files, and `LATEST.md` path. A report from one agent never authorizes another agent's next work.
