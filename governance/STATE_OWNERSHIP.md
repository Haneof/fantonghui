# AIOS 2.0 State Ownership

This file defines who may update which cloud project state.

## Implementation agent owns execution state

During an authorized task, the implementation agent updates:

- `TASK_PROGRESS_R2.md` to `CODE COMPLETE / WAITING CHIEF REVIEW`, `PATCH COMPLETE`, or `BLOCKED`
- task implementation/review packet evidence under `reviews/`
- test output evidence

The implementation agent MUST NOT mark its own task FINAL PASS, authorize the next task, or alter frozen historical rulings.

## Chief Engineer owns authoritative state

After independent GitHub review, the Chief Engineer updates or causes an authorized update to:

- `governance/CURRENT_STATE.md`
- `governance/ACTIVE_ASSIGNMENTS.md`
- FINAL PASS review records
- frozen commit references
- next-task authorization / HOLD state
- model-routing or multi-agent policy when architecture changes

## Principal Architect owns escalation findings, not project status

The Principal Architect / Red Team writes an audit/ruling artifact. The Chief Engineer incorporates the accepted ruling into authoritative project state.

## Recovery priority

When sources disagree, use this precedence:

1. constitution + R1/R2 + authoritative taskbook for architecture
2. latest Chief Engineer FINAL PASS / ruling
3. `governance/CURRENT_STATE.md`
4. `governance/ACTIVE_ASSIGNMENTS.md`
5. `TASK_PROGRESS_R2.md`
6. implementation-agent reports

Any disagreement is a STOP condition until resolved.
