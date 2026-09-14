# AIOS 2.0 Active Assignments

This file is the cloud roster. An AI agent must not self-assign production work that is not listed here.

## Assignment A — `core-01` Core Implementation Engineer

- Agent ID: `core-01`
- Status: PATCH REQUIRED / ACTIVE
- Task: M0-010-R1 — Entity + Relation test hardening
- Role: Core Implementation Engineer
- Role prompt: `governance/roles/IMPLEMENTATION_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Patch base commit: `225eb7636f9e88f8373de32aa332eeb83c37fd16`
- Required cloud result: `governance/agent_reports/core-01/LATEST.md` on the production branch
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
- update `governance/agent_reports/core-01/LATEST.md` after the final push

### Completion state allowed

- PATCH COMPLETE / WAITING CHIEF REVIEW
- BLOCKED

Never FINAL PASS.

## Assignment B — `chief-01` Chief Engineer

- Agent ID: `chief-01`
- Status: ACTIVE
- Role: Chief Engineer
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Current task: wait for and review `core-01` M0-010-R1 result
- Required reads after operator says `core-01 做完了`:
  - this file
  - `governance/CONTROL_PANEL.md`
  - production branch `governance/agent_reports/core-01/LATEST.md`
  - actual branch HEAD/diff/source/reviews/CI
- Responsibility: issue M0-010 FINAL PASS or another bounded PATCH REQUIRED, update cloud control state, then authorize or hold M0-011.

## Assignment C — `architect-01` Principal Architect / GPT-6 Red Team

- Agent ID: `architect-01`
- Status: STANDBY
- Role: Principal Architect / Red Team
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Required cloud result when invoked: `governance/agent_reports/architect-01/LATEST.md` on its assigned audit branch
- Trigger: only according to `MODEL_ROUTING_POLICY.md`
- Mandatory future engagement: M0 milestone Gate independent architecture/red-team audit.
- Current instruction: DO NOT self-start.

## Assignment D — `parallel-01` Parallel Implementation Engineer

- Agent ID: `parallel-01`
- Status: NOT AUTHORIZED
- Role: Parallel Implementation Engineer
- Role prompt: `governance/roles/IMPLEMENTATION_ENGINEER.md`
- Required cloud result when activated: `governance/agent_reports/parallel-01/LATEST.md`
- Current task: NONE
- May start production work only when explicitly assigned and marked `PARALLEL_SAFE`.

## Assignment E — `parallel-02` Parallel Implementation Engineer

- Agent ID: `parallel-02`
- Status: NOT AUTHORIZED
- Role: Parallel Implementation Engineer
- Role prompt: `governance/roles/IMPLEMENTATION_ENGINEER.md`
- Required cloud result when activated: `governance/agent_reports/parallel-02/LATEST.md`
- Current task: NONE
- May start production work only when explicitly assigned and marked `PARALLEL_SAFE`.

## Operator handoff rule

The human operator does not transport result text between agents.

The operator only needs to say things like:

- `core-01 做完了`
- `architect-01 做完了`
- `parallel-01 做完了`

The Chief Engineer then reads the cloud report and actual GitHub state, updates authoritative state, and tells the operator which agent ID should read its next assignment from the cloud.
