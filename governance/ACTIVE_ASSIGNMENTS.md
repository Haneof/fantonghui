# AIOS 2.0 Active Assignments

This file is the cloud roster. An AI agent must not self-assign production work that is not listed here.

## Assignment A — Core Implementation Engineer

- Status: ACTIVE
- Task: M0-010 — Entity + Relation contract
- Role: Core Implementation Engineer
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen base commit: `cda888f371fed812cda1b5e08d8a27db5e0c240a`
- Parallel safety: NOT PARALLEL_SAFE for another core writer
- Next task M0-011: HOLD

### Allowed production scope

- `src/aios_core/contracts/models.py`
- only minimal `Entity` / `Relation` validators required by the Chief Engineer command

### Production files that must remain unchanged

- `src/aios_core/storage/sqlite_store.py`
- `src/aios_core/contracts/refs.py`
- `src/aios_core/contracts/base.py`
- `src/aios_core/contracts/time.py`
- `src/aios_core/contracts/enums.py`
- `src/aios_core/contracts/ids.py`
- all unrelated models

### Required non-production work

- `tests/unit/test_entity_relation.py`
- M0-009 FINAL PASS archive
- M0-010 review/evidence files
- `TASK_PROGRESS_R2.md`

### Completion state allowed

- CODE COMPLETE / WAITING CHIEF REVIEW
- BLOCKED

Never FINAL PASS.

## Assignment B — Chief Engineer

- Status: ACTIVE
- Role: Chief Engineer
- Responsibility: review Assignment A, inspect exact GitHub state and CI, issue M0-010 FINAL PASS or PATCH REQUIRED, then authorize or hold M0-011.

## Principal Architect / GPT-6 Red Team

- Status: STANDBY
- Trigger: only according to `MODEL_ROUTING_POLICY.md`
- Mandatory future engagement: M0 milestone Gate independent architecture/red-team audit.

## Parallel Implementation Engineer

- Status: NOT YET AUTHORIZED for core production code
- May perform read-only audit/test-design work only if separately assigned by Chief Engineer.
