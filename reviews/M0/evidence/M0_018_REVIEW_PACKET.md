# M0-018 Review Packet — 全局 World Revision 与原子提交

日期：2026-09-14

## Authoritative requirement

Taskbook M0-018 requires one logical world transaction to produce exactly one global world revision; `expected_world_revision` must be checked at transaction start; multiple objects in one commit share the same next revision; all validation happens before durable commit; a failure must leave no half-written world; concurrent writers from the same snapshot must not both succeed; Session must be able to hold a stable snapshot revision.

## Semantic head

`f00735193e09b6a337ade39dc040510c003d8f54`

M0-017 accepted archive base before M0-018 work:
`99c61029690d26441b3330a8579fe002805c71e7`

Production implementation inspected:
`src/aios_core/storage/sqlite_store.py`

The existing store already used `BEGIN IMMEDIATE`, idempotency lookup, expected-world-revision optimistic concurrency, full pre-insert validation, one `next_world_revision` per commit, one `world_commits` row per logical transaction, all object rows stamped with that same world revision, `world_meta` increment only at the end, and rollback on any exception. Therefore M0-018 did not require changing production storage code; this task freezes those semantics through focused adversarial tests.

## Added M0-018 tests

`tests/unit/test_world_revision_atomicity.py`

Five focused scenarios:

1. Three objects committed together receive one shared global world revision and world revision advances only once.
2. A real SQLite trigger forces failure after inserts have begun; rollback leaves zero world commit, zero object revisions, zero operations, zero idempotency records, and world revision remains unchanged.
3. Two concurrent writers starting from expected revision 0 race through two store instances; exactly one succeeds at world revision 1 and the other receives `VERSION_CONFLICT`.
4. A persisted Session keeps `snapshot_world_revision=1` even after the live world advances to revision 3; historical reads at world revision 1 exclude later Session/Observation objects.
5. A failed multi-object transaction does not consume a world revision; the next valid commit receives the skipped logical number, not a gap.

## Exact-head CI

GitHub Actions run `34811297016`
job `103873014736`
head `f00735193e09b6a337ade39dc040510c003d8f54`
Ubuntu 24.04.5
CPython 3.12.14
pytest 8.4.2

Formal suite: **358 passed**, 1 previously accepted adversarial warning.
Reference suite: **15 passed**.
Workflow conclusion: **SUCCESS**.

## Scope discipline

Not implemented here:
- M0-019 additional reference validation semantics;
- any per-object world revision increment;
- distributed multi-database transactions;
- automatic retry that hides `VERSION_CONFLICT`;
- migration redesign.

M0-018 freezes the existing single-SQLite-store transaction/world-revision contract and validates it under true mid-transaction failure and concurrent-writer contention.
