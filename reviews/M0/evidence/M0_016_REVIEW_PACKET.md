# M0-016 Review Packet — OperationRequest、审计与幂等契约

日期：2026-09-14

## Authoritative requirement

Taskbook M0-016 requires every world modification to carry `operation_id / session_id / expected_world_revision / reason / idempotency_key`, storage must check idempotency before optimistic concurrency, replay must return the original result, stale expected revision must surface `VERSION_CONFLICT`, and audit data must remain queryable.

## Semantic head

`cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3`

Base:
`d16d10f053b528490f4276f216e06feeb003bbab`

Compare is ahead-only, 3 commits, behind 0.

Changed files:
- `src/aios_core/contracts/operations.py`
- `src/aios_core/contracts/__init__.py`
- `tests/unit/test_operations.py`

Existing `SQLiteWorldStore` implementation was independently inspected and already satisfies the required ordering and durable audit persistence, so no storage production change was needed in this task.

## Contract freeze

`OperationRequest` fields remain exactly:
- operation_id
- session_id
- operation_name
- arguments
- expected_world_revision
- reason
- idempotency_key

The contract now rejects blank operation identity / reason / key values and validates assignment mutations.

`OperationAuditRecord` is added as a typed durable audit view for committed operations.

## Idempotency and concurrency invariants

Verified:
1. same idempotency key replay is checked before expected-world-revision validation;
2. same operation retry returns the original world revision/object refs with `idempotent_replay=True`;
3. retry does not advance the world revision a second time;
4. stale expected revision with a new key raises `VERSION_CONFLICT`;
5. the conflict is not swallowed and does not overwrite another writer;
6. committed operation metadata is queryable from the operations audit table;
7. idempotency and audit records survive store restart.

## Test matrix

Added 12 focused tests covering:
- exact schema;
- blank / invalid fields;
- assignment validation;
- replay-on-same-key;
- replay precedence over now-stale expected revision;
- optimistic concurrency conflict;
- complete audit record;
- restart durability;
- audit NOT_FOUND;
- no conflict swallowing;
- stable replay result.

## Exact-head CI

GitHub Actions run `34810519222`
job `103870768750`
head `cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3`
Ubuntu 24.04.5
CPython 3.12.14
pytest 8.4.2

Formal suite: **341 passed**, 1 previously accepted adversarial warning.
Reference suite: **15 passed**.
Workflow conclusion: **SUCCESS**.

## Scope discipline

Not implemented here:
- M0-017 storage schema redesign/migrations;
- M0-018 new world-revision transaction semantics;
- external Action execution idempotency runtime;
- automatic retry loops that hide version conflicts.

This task freezes the operation/audit/idempotency contract on top of the existing store implementation without pulling later milestones forward.
