# architect-01 — M0 Gate blocker patch independent re-review request

Status: **AUTHORIZED / REQUIRED / READY TO START**

You are `architect-01`, the independent GPT-6-class Principal Architect / Red Team.

Your previous report at governance commit `c6b0191797ab3ef06b4ee031003431a0d9527d48` returned `BLOCKER FOUND` with B1/B2/B3. Chief accepted those findings and produced a patch candidate.

## Review base

Repository: `Haneof/fantonghui`

Production branch: `arena/01a09bc6-fantonghui`

Original Gate candidate: `95cec4142bdd9a87011bbad197e05ec1d27aeb57`

Current patch candidate: `8b3bca9ef3bf8fde2ee09b73a2631a3a2f12db0a`

Key semantic patch commit: `8ab574c6b33b2238b468c812992a92ba56ab3f71`

B2 static-policy hardening: `e06bc80e43ea26be2be726232158cb2719092f11`

Chief ruling/review: `reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`

Exact patch CI:
- run `34821050459`
- job `103902471146`
- CPython 3.12.14
- formal 400 passed / 1 known warning
- Reference 15 passed
- SUCCESS

## Required attacks

### B1 idempotency

Try to falsify the new rule that an idempotency key replays only an identical durable commit request.

Attack:
- changed operation_id;
- changed session_id;
- changed operation_name;
- changed arguments, including semantically equivalent ordering cases;
- changed expected_world_revision;
- changed reason;
- changed object set;
- changed object revision;
- changed object payload;
- same objects in different input order;
- restart replay;
- concurrent same-key different requests;
- crash/rollback interaction using existing atomicity machinery.

Verify mismatch returns `IDEMPOTENCY_CONFLICT` before stale-world behavior and leaves world/object/operation/idempotency state unchanged.

Inspect `src/aios_core/storage/idempotency.py` and integration into `sqlite_store.py`. Check whether reconstructing the stored fingerprint from `operations` + same-world `object_revisions` is actually equivalent to persisting the original request identity, including old M0 database compatibility.

### B3 Dependency cycles

Try to persist:
- same-transaction two-edge cycle;
- cycle completed across multiple commits;
- longer A->B->C->A cycle;
- concurrent competing edge additions;
- dependency object revision replacing an old edge;
- cycles involving exact revisions.

Verify generic durable commit cannot persist a current Dependency graph cycle when Dependency objects are written, while ordinary Relation cycles remain legal.

Check whether latest-revision selection for Dependency WorldObjects is the correct current-graph semantics and whether any bypass remains.

### B2 Worker isolation ruling

Chief explicitly narrowed M0 threat model:
- modular monolith;
- trusted reviewed Python code;
- Worker direct storage access is an architecture dependency rule, not a hostile-code sandbox;
- Worker must use Core public interfaces and production wiring must not inject DB path/connection/storage capabilities;
- if future runtime executes untrusted Python, a real process/capability boundary becomes mandatory.

Audit whether this ruling is consistent with Constitution/R1/R2/taskbook and whether historical claims have been honestly narrowed rather than disguised.

Verify new static scanner catches the two counterexamples you previously supplied:
- `__import__('sqlite3')`
- `importlib.import_module('aios_core.storage')`

Do not treat the scanner as sandbox proof.

## Regression Gate

Re-check the original M0 Gate areas sufficiently to ensure the patch did not create a new foundational failure. In particular:
- exact candidate ancestry/diff;
- full CI logs;
- M0 schema snapshot still passes;
- four required Gate fixtures still pass;
- world revision / rollback / reference validation ordering was not broken;
- M0-009 persistence-revalidation ordering remains valid except for the newly required idempotency conflict comparison at an existing key.

## Deliverable

Update:

`governance/agent_reports/architect-01/LATEST.md`

First line must be exactly one of:

- `ARCHITECTURE PASS`
- `RULING REQUIRED`
- `BLOCKER FOUND`

If PASS, explicitly list residual risks, including any issue you judge acceptable only because it is deferred to M1/M2/M3.

If ruling/blocker, give a minimal reproducible counterexample and affected patch/frozen contracts.

Do not modify production code. Do not declare M0 FINAL PASS; final authority remains with `chief-01`.
