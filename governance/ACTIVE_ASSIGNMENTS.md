# AIOS 2.0 Active Assignments

This file is the cloud roster. An AI agent must not self-assign production work that is not listed here.

## Assignment A — `chief-01` Chief Engineer

- Agent ID: `chief-01`
- Status: ACTIVE / OWNER
- Task: M0-011 — DimensionDefinition / DimensionMembership / DimensionDerivation three-layer contract
- Role: Chief Engineer
- Role prompt: `governance/roles/CHIEF_ENGINEER.md`
- Production branch: `arena/01a09bc6-fantonghui`
- Frozen base commit: `949e90e58bd073c1da5d23664bfcb1cb8154ebde`
- Parallel safety: NOT PARALLEL_SAFE for another core writer
- Next task M0-012: HOLD

### Authority basis

The authoritative taskbook marks M0-011 `负责人级别：总工程师亲自代码`.
Therefore M0-011 is not assigned to `core-01`.

### Required task outcome

Freeze a three-layer dimension contract:
- DimensionDefinition = what the dimension is
- DimensionMembership = which object is mounted to the dimension
- DimensionDerivation = how a higher-level dimension is derived from lower-level inputs/evidence

Must preserve the taskbook rules:
- one object may have multiple memberships
- derivation inputs may include dimensions, events, Claims, Summaries, EvidenceSets; not numeric curves only
- high-level dimensions must drill down to inputs
- raw Observation must not be copied into each dimension as private data
- dimension data_shape must not be forced to vector/curve only

### Current production scaffold

Existing `models.py` already contains:
- `DimensionDefinition`
- `DimensionMembership`
- `DimensionDerivation`

Chief Engineer must independently decide minimal validators/tests before writing.

## Assignment B — `core-01` Core Implementation Engineer

- Agent ID: `core-01`
- Status: REPORT SYNC REQUIRED THEN IDLE
- Task: M0-010-R1 closeout only
- Role: Core Implementation Engineer
- Role prompt: `governance/roles/IMPLEMENTATION_ENGINEER.md`
- Working branch: `arena/01a09bc6-fantonghui`
- Accepted HEAD: `949e90e58bd073c1da5d23664bfcb1cb8154ebde`
- Required cloud result: `governance/agent_reports/core-01/LATEST.md` on the working branch
- Production scope: NONE

### Required closeout work

- create/update `governance/agent_reports/core-01/LATEST.md`
- record task `M0-010-R1`
- status `PATCH COMPLETE / ACCEPTED BY CHIEF`
- head commit `949e90e58bd073c1da5d23664bfcb1cb8154ebde`
- production R1 diff: NO CHANGE
- local result: 253 passed + Reference 15 passed
- exact-head CI: SUCCESS, Python 3.12.14, 253 passed
- unresolved issues: NONE
- next requested action: NONE / IDLE
- do not modify `src/aios_core/**`
- do not start M0-011
- push the report commit and stop

## Assignment C — `architect-01` Principal Architect / GPT-6 Red Team

- Agent ID: `architect-01`
- Status: STANDBY
- Role: Principal Architect / Red Team
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Required cloud result when invoked: `governance/agent_reports/architect-01/LATEST.md` on its assigned audit branch
- Trigger: only according to `MODEL_ROUTING_POLICY.md`
- Mandatory future engagement: M0 milestone Gate independent architecture/red-team audit
- Current instruction: DO NOT self-start

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
