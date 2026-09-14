# AIOS 2.0 Active Assignments

This file is the cloud roster. An AI agent must not self-assign production work that is not listed here.

## Assignment A — Core Implementation Engineer

- Status: PATCH REQUIRED / ACTIVE
- Task: M0-010-R1 — Entity + Relation test hardening
- Role: Core Implementation Engineer
- Production branch: `arena/01a09bc6-fantonghui`
- Patch base commit: `225eb7636f9e88f8373de32aa332eeb83c37fd16`
- Parallel safety: NOT PARALLEL_SAFE for another core writer
- Next task M0-011: HOLD

### Production scope

TEST ONLY PATCH.

No production files are authorized to change.

### Production files that must remain unchanged

- all `src/aios_core/**`
- especially `src/aios_core/contracts/models.py`
- especially `src/aios_core/storage/sqlite_store.py`

### Required patch work

- harden `tests/unit/test_entity_relation.py`
- remove ER01 false-green `or True`
- freeze Entity `object_type` as exact `Literal[ObjectType.ENTITY]`
- freeze Relation `object_type` as exact `Literal[ObjectType.RELATION]`
- fix ER18 so both Relation endpoints are real committed Entity objects; the test must isolate the floating `evidence_set_refs` mutation bypass rather than fail later because endpoints are missing
- update M0-010 review/evidence files and `TASK_PROGRESS_R2.md`

### Completion state allowed

- PATCH COMPLETE / WAITING CHIEF REVIEW
- BLOCKED

Never FINAL PASS.

## Assignment B — Chief Engineer

- Status: ACTIVE
- Role: Chief Engineer
- Responsibility: review M0-010-R1 exact GitHub diff/tests/CI, issue M0-010 FINAL PASS or another bounded PATCH REQUIRED, then authorize or hold M0-011.

## Principal Architect / GPT-6 Red Team

- Status: STANDBY
- Trigger: only according to `MODEL_ROUTING_POLICY.md`
- Mandatory future engagement: M0 milestone Gate independent architecture/red-team audit.

## Parallel Implementation Engineer

- Status: NOT YET AUTHORIZED for core production code
- May perform read-only audit/test-design work only if separately assigned by Chief Engineer.
