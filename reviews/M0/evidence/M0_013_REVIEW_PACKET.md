# M0-013 Review Packet

Task: Goal（一等目标对象）
Date: 2026-09-14
Chief verdict: FINAL PASS
Frozen semantic commit: `f30987395a034d4e9f826c9193dc82e00165a2e8`
Pre-task base: `c31da78bf8f4b4053ed0bfb310444676a153fcdc`

## Authoritative requirements checked

- Long-lived Goal is distinct from short-lived Task.
- Explicit user goal, AI-inferred user goal and App goal are distinguishable by source semantics.
- Goal keeps owner/source/title/description/status/success criteria/related dimensions-events-tasks-apps/confidence.
- Goal does not auto-create Task.
- Task links Goal through ObjectRef, not free-text `goal`.
- User denial of an inferred Goal leaves related Task identifiable for later review.
- Help systems can trace a Task/action context back to a first-class Goal object.

## R2 contract correction

Old scaffold GoalStatus was not R2-exact:
`CANDIDATE, ACTIVE, PAUSED, ACHIEVED, ABANDONED, REJECTED`.

Frozen R2 values are:
`PROPOSED, ACTIVE, PAUSED, ACHIEVED, ABANDONED, UNKNOWN`.

Production changes therefore only align the enum and Goal default status to R2.

## Source semantics freeze

- USER_EXPLICIT = user explicitly states the goal.
- USER_INFERRED = AI infers that the user may have the goal.
- AI_SELF = AI's own goal, not a user-inferred goal.
- APP = application-scoped goal.
- EXTERNAL = externally sourced goal.

A text match does not collapse these semantic origins.

## Goal / Task separation evidence

Tests prove:
- Goal has no Task runtime state/deadline/wake/completion fields.
- `Task.goal_ref` is `ObjectRef | None`, never `str`.
- committing a Goal leaves the Task collection empty unless a Task is explicitly created.
- success criteria remain Goal-level conditions and are not implied by Task completion.

## Denial / reviewability scenario

Persisted sequence:
1. Goal@1 USER_INFERRED / PROPOSED.
2. Task@1 pins `goal_ref=Goal@1`.
3. After explicit user denial, Goal@2 becomes ABANDONED and explicitly links `Task@1` in `related_task_refs`.
4. Goal@1 remains historically replayable; Task@1 continues to expose the old reason link.

This is sufficient for later dependency/correction machinery to locate the affected Task. Automatic cancellation/review scheduling is intentionally deferred.

## CI evidence

Frozen semantic head: `f30987395a034d4e9f826c9193dc82e00165a2e8`
GitHub Actions run: `34807182442`
Job: `103861241239`
Environment: CPython 3.12.14 / pytest 8.4.2

- formal suite: 297 passed, 1 pre-existing expected serializer warning
- Reference suite: 15 passed
- conclusion: SUCCESS

## Scope verification

Compare `c31da78...` → `f309873...`:
- status ahead
- ahead_by 4
- behind_by 0
- production files changed only `src/aios_core/contracts/enums.py` and `src/aios_core/contracts/models.py`
- added tests only `tests/unit/test_goal.py` and `tests/unit/test_goal_reviewability.py`

No Goal service, Task scheduler, dependency propagation, Worker behavior, DB migration or M2/M3 implementation was pulled forward.

## Deferred intentionally

- `goal.create/update/query/assess_progress` services;
- automatic Task generation from Goal;
- automatic Task cancellation/review when Goal changes;
- progress assessment engine;
- reverse dependency propagation.

Final verdict: **M0-013 FINAL PASS @ `f30987395a034d4e9f826c9193dc82e00165a2e8`**
