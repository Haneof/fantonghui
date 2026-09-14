BLOCKER FOUND

# Independent M0 Gate Audit Report — Track E

**Auditor ID:** `AUDITOR-E-01`  
**Track:** Cross-cutting integration / unknown-unknowns  
**Date:** 2026-09-14  
**Candidate reviewed:** `659157b849a0dbaad241c3e316dcd98eb7c72df7`  
**Observed production HEAD:** `5acef4a4f43895a0762462e1f30e4f923da979a0`  
**Audit-only branch:** `arena/auditor-e-m0-redteam-20260914`  
**Audit branch probe HEAD:** `731759c5ec78c09bc4bbdda22c7d1b764324ff9f`

## Verdict

`BLOCKER FOUND`.

The candidate remains green on the established 420-test suite, but two new cross-cutting persistence invariants are falsified by independently added audit-only probes. The failures are not regressions in the probe branch production code: the branch was created from the candidate and only audit tests were added.

The two defects are:

1. **B10 — durable `object_type` can disagree with the frozen canonical object schema.** A plain `WorldObject` can claim `ObjectType.DEPENDENCY` or `ObjectType.EVIDENCE_SET` and be committed without satisfying the required `Dependency` / `EvidenceSet` fields. A later legitimate dependency commit then reads the malformed durable row as a `Dependency` and leaks a raw Pydantic `ValidationError` from the public storage boundary.
2. **B11 — canonical mapping-key coercion can silently collapse distinct accepted values and alias idempotent replay.** A mapping containing both integer key `1` and string key `"1"` is accepted by an `Any`-typed Observation value, but canonicalization converts both keys to the same JSON key. One entry is silently lost, and a materially different retry can produce the same stored fingerprint and be treated as an exact replay rather than an idempotency conflict.

Both findings are reproducible on the candidate source and violate durable-boundary / idempotency guarantees required for M0 closure.

## Candidate / production equivalence

Independent comparison of candidate `659157b849a0dbaad241c3e316dcd98eb7c72df7` to production HEAD `5acef4a4f43895a0762462e1f30e4f923da979a0` showed production is two commits ahead and the only changed path is the B8/B9 review document. There is no source-code delta relevant to B10/B11, so the findings apply equally to the observed production source state.

The original candidate CI remains valid baseline evidence: the known suite is green (420 tests plus Reference suite), but those tests did not cover the two interactions below.

## B10 — canonical object-type/schema dispatch gap

### Contract expectation

The repository freezes concrete durable world-object schemas such as `Dependency` and `EvidenceSet`. Their `object_type` fields are literal discriminators and their domain-required fields are part of the persisted contract. A durable row labelled `dependency` therefore must be valid as a `Dependency`; a row labelled `evidence_set` must be valid as an `EvidenceSet`.

### Implementation interaction

The persistence normalization path revalidates a world object using its **runtime Python class** (`type(obj).model_validate(...)`). The generic base `WorldObject` is instantiable and permits an arbitrary enum `object_type`. Therefore:

- `WorldObject(object_type=ObjectType.DEPENDENCY, ...)` is revalidated only as `WorldObject`;
- it can be written with SQL `object_type='dependency'` while lacking `dependent_ref`, `dependency_ref`, and `dependency_type`;
- dependency-graph loading later selects durable rows by the SQL discriminator and calls `Dependency.model_validate(...)` on that malformed payload;
- the resulting Pydantic `ValidationError` is not mapped to the storage protocol error surface.

The same entry-path problem is demonstrated for `ObjectType.EVIDENCE_SET`, where a row can claim the frozen type without the required EvidenceSet members / selector / knowledge-window semantics.

### Audit-only reproducer

File on audit branch:

`tests/unit/test_auditor_e_b10_contract_dispatch.py`

Commit:

`099acf3188ab28389ff70d1b265bdfd0cc82b2aa`

Workflow:

- Run ID `34833864406`
- Job ID `103943128899`
- Python `3.12.14`
- pytest `8.4.2`
- pydantic `2.13.5`
- Result: **3 failed, 420 passed, 1 warning**

Observed failures:

- `test_b10_plain_worldobject_cannot_claim_dependency_type`: expected durable-boundary rejection, but commit succeeded.
- `test_b10_plain_worldobject_cannot_claim_evidence_set_type`: expected durable-boundary rejection, but commit succeeded.
- `test_b10_masqueraded_dependency_poison_must_not_leak_raw_validationerror`: after the malformed dependency-labelled row is accepted, a later legitimate dependency commit reaches `_validate_dependency_graph` and raises raw `pydantic_core.ValidationError` for missing `dependent_ref`, `dependency_ref`, and `dependency_type`.

### Why this is M0-blocking

This is not the already-approved M1 service-layer state-transition residual. It is a lower-level durable schema identity problem inside M0 storage itself. The database discriminator can assert one frozen object contract while the payload satisfies another weaker runtime class. That makes durable state internally inconsistent and can break later valid commits through an exception outside the protocol error surface.

### Minimal repair direction

No production fix was made by this auditor. The chief engineer should require one authoritative mapping between frozen `ObjectType` values and their canonical model classes at the persistence boundary (or an equivalent discriminated-union validation strategy), then reject payloads whose declared durable type cannot validate under that canonical schema. The error should be mapped to an existing protocol-level validation/storage code according to the chief engineer's taxonomy.

The repair must preserve intentionally supported generic-reference test helpers only if they do not claim a frozen canonical durable type without satisfying that type's schema.

## B11 — mapping-key collapse breaks persistence fidelity and idempotency separation

### Contract expectation

A materially different request must not reuse an idempotency key as an exact replay. Canonicalization may equate representations only when the durable serialization contract intentionally makes them equivalent without losing distinct accepted data.

### Implementation interaction

`canonical_json_value` canonicalizes a `Mapping` with effectively:

`{str(key): canonical_json_value(item) for key, item in value.items()}`

For an accepted nested mapping such as:

`{1: "numeric-key", "1": "string-key"}`

both keys canonicalize to `"1"`. The second entry overwrites the first. This has two consequences:

1. a committed Observation value can silently lose one accepted entry at the durable boundary;
2. the above two-entry value and the materially different one-entry value `{"1": "string-key"}` can canonicalize to the same durable payload/fingerprint, so a retry using the same idempotency key is returned as an exact replay instead of an idempotency conflict.

This is distinct from B8 set/frozenset deterministic ordering. B8 intentionally imposed stable ordering on unordered collections. B11 is a **key collision after coercion**, which drops information.

### Audit-only reproducer

File on audit branch:

`tests/unit/test_auditor_e_b11_mapping_key_consistency.py`

Commit:

`731759c5ec78c09bc4bbdda22c7d1b764324ff9f`

Workflow:

- Run ID `34834424189`
- Job ID `103944891465`
- Candidate source plus audit-only tests
- Result: **5 failed, 420 passed, 1 warning**

The five failures are the three B10 probes plus two B11 probes:

- `test_b11_distinct_mapping_keys_must_not_be_silently_collapsed`: candidate accepts a mapping whose two distinct keys collide after string coercion instead of rejecting it.
- `test_b11_mapping_key_collapse_must_not_alias_idempotent_retry`: after the first value is accepted, the materially different one-entry value reusing the same idempotency key is not rejected; the probe therefore demonstrates fingerprint aliasing caused by the key collapse.

### Why this is M0-blocking

This reaches the core M0 idempotency invariant directly: materially different accepted requests can become indistinguishable after normalization. It also produces silent durable data loss. Either non-string / colliding mapping keys must be rejected before persistence, or the canonical representation must preserve key identity without collision. Merely sorting mappings is insufficient.

### Minimal repair direction

No production fix was made by this auditor. A repair should define and enforce a single mapping-key contract before fingerprinting and persistence. If durable structured values are JSON objects, reject non-string keys (including nested ones) before the write. If broader Python mapping keys are intentionally supported, encode key type and value injectively so distinct accepted keys cannot collapse.

Regression tests must cover at least `1` versus `"1"` and verify both persistence fidelity and idempotency conflict behavior.

## Shared M0 surface re-check

The existing 420-test suite still passes alongside the new probe files; the only failures in audit CI are the deliberately added B10/B11 invariants. This is useful evidence that the findings do not arise from unrelated breakage in B1-B9 coverage.

Source review also reconfirmed the following previously resolved behavior remains intact in the candidate:

- stale exact replay is checked before expected-world revision rejection;
- B8 set/frozenset ordering is deterministic through canonical JSON sorting;
- B9 SQLite busy/locked classification uses result codes rather than message substring matching;
- transaction rollback remains wrapped around the full commit path;
- EvidenceSet cutoff handling remains explicit at reference validation;
- dependency cycle validation still applies to canonical `Dependency` instances;
- historical query logic continues to combine world-revision and knowledge-time filters;
- M0-021's deliberate service-layer state-transition boundary remains a future M1 gate and is **not** being reclassified here as an M0 defect.

The new blockers arise precisely where these otherwise-correct mechanisms interact with inputs the current regression suite did not model.

## Scope and branch discipline

No production source code was modified. Only two audit probe files were added on `arena/auditor-e-m0-redteam-20260914`. The governance report is written separately to `governance/aios-control-plane`.

Audit-only changes:

- `099acf3188ab28389ff70d1b265bdfd0cc82b2aa` — B10 canonical schema-dispatch probes
- `731759c5ec78c09bc4bbdda22c7d1b764324ff9f` — B11 mapping-key consistency probes

These commits must not be merged into production as fixes; they are evidence / regression-test candidates for the chief engineer to adopt or rewrite during repair.

## Required gate action

M0 should remain open. `chief-01` should treat B10 and B11 as new blocker candidates, assign repairs, and require fresh independent re-verification after the fixes land. A final M0 pass should not rely on the pre-existing `auditor-e.md` PASS report because that report predates these independently reproduced cases.

Final M0 gate authority remains with `chief-01`.
