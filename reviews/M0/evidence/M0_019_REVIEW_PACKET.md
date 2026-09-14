# M0-019 Review Packet — 引用存在性与同事务引用验证

日期：2026-09-14

## Authoritative requirement

Taskbook M0-019 requires durable writes to validate every ObjectRef/SourceRef before persistence, allow legal same-transaction references, reject missing or not-yet-visible targets, and block an object from citing its own current revision as evidence/source. More complex graph-cycle rules remain later work.

## Semantic head

`f1dc7cc8ca07131f75d7afe5c505f534c2f3dbe8`

Base archive head:
`3497e58f1d9168bad1823c98d3e6163ac31cffe1`

Compare is ahead-only, 2 commits, behind 0.

Production change:
- `src/aios_core/storage/sqlite_store.py`

Test addition:
- `tests/unit/test_reference_validation_m019.py`

## Chief finding and fix

The existing store already implemented recursive reference collection, DB/pending lookup, knowledge-cutoff visibility, same-transaction references, and current-revision self-reference rejection. However, `commit()` exposed a public `validate_references=False` switch. That switch could bypass the persistence-boundary invariant and durably write broken references.

M0-019 removes that bypass. Reference validation is now mandatory for every `commit()` call.

No new arbitrary cycle detector was added. Ordinary semantic mutual references remain legal, preserving the M0-006 contract.

## Frozen behavior

1. Pinned ObjectRef/SourceRef requires the exact target revision to exist and be visible at the referencing object's `learned_at` cutoff.
2. Floating generic refs remain navigation refs and succeed when at least one target revision is visible at cutoff.
3. Pending objects in the same transaction count as valid targets when their learned_at is not in the referencing object's future.
4. Same-transaction mutual non-evidence links remain legal.
5. Missing or not-yet-visible refs raise `NOT_FOUND` before durable writes.
6. An object citing its own current revision raises `DEPENDENCY_INVALID`.
7. A later revision may legitimately refer to an earlier revision of the same object.
8. Callers cannot disable reference validation through the public commit API.
9. Failed reference validation leaves world revision and durable objects unchanged.

## Focused M0-019 tests

Added 8 focused tests covering:
- missing pinned ref rejection and no partial commit;
- same-transaction EvidenceSet -> new Observation success;
- legal same-transaction mutual ordinary refs;
- ObjectRef current-revision self-reference rejection;
- SourceRef current-revision self-reference rejection;
- historical self-link to previous revision remains legal;
- no public `validate_references=False` bypass;
- pending future target rejected by knowledge cutoff.

These extend the existing M0-006 reference suite, which already covers pinned/floating semantics, persisted future visibility, SourceRef visibility, same-transaction refs, and DST fold correctness.

## Exact-head CI

GitHub Actions run `34811844771`
job `103874600156`
head `f1dc7cc8ca07131f75d7afe5c505f534c2f3dbe8`
Ubuntu 24.04.5
CPython 3.12.14
pytest 8.4.2

Formal suite: **366 passed**, 1 previously accepted adversarial warning.
Reference suite: **15 passed**.
Workflow conclusion: **SUCCESS**.

## Scope discipline

Not implemented here:
- arbitrary semantic-graph cycle rejection;
- M0-020 historical query API expansion;
- M1/M3 dependency propagation and complex proof-cycle reasoning;
- automatic removal or repair of broken refs.

Broken refs are rejected, never silently deleted.
