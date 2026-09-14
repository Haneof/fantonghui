BLOCKER FOUND

# AIOS 2.0 M0 Gate Independent Red-Team Audit

- AUDITOR_ID: `auditor-d`
- TRACK: `E — Cross-cutting / Unknown Unknowns`
- exact semantic candidate: `659157b849a0dbaad241c3e316dcd98eb7c72df7`
- observed production HEAD: `5acef4a4f43895a0762462e1f30e4f923da979a0`
- audit date: `2026-09-14`
- adversarial probe branch: `arena/auditor-e-m0-redteam-20260914`
- adversarial probe commit: `099acf3188ab28389ff70d1b265bdfd0cc82b2aa`

> Provenance note: this review initially selected `auditor-e`, but `governance/agent_reports/m0-parallel-audits/auditor-e.md` was already occupied by another auditor report. The formal parallel-audit instruction forbids overwriting another auditor's report, so this independent review is filed as `auditor-d`. The probe branch name remains `auditor-e-m0-redteam-20260914`; no production code was modified.

## 1. Verdict

`BLOCKER FOUND`.

I found a new current-M0 false-green class, designated **B10 — canonical durable subtype contract bypass / object_type masquerading**.

The durable write boundary revalidates each incoming object using `type(obj).model_validate(...)`, rather than dispatching the durable payload through the frozen canonical contract implied by `object_type`. A caller can therefore construct a base `WorldObject` whose `object_type` says `dependency`, `evidence_set`, `task`, `event`, etc., while omitting the required fields and validators of that canonical subtype. `SQLiteWorldStore.commit()` accepts such an object and writes it durably under the claimed `object_type`.

For `Dependency`, this is not merely malformed data at rest. It can poison the durable dependency set so that a later legitimate Dependency commit calls `Dependency.model_validate(...)` on the malformed stored row and leaks a raw Pydantic `ValidationError` out of the public store API. This is a reproducible protocol-boundary failure and invalidates the current M0 Gate candidate.

## 2. Candidate -> HEAD comparison

Independent compare:

- base: `659157b849a0dbaad241c3e316dcd98eb7c72df7`
- head: `5acef4a4f43895a0762462e1f30e4f923da979a0`
- status: `ahead`
- ahead_by: `2`
- behind_by: `0`
- changed file(s): only `reviews/M0/M0_gate_B8_B9_followup_2026-09-14.md`

Conclusion: there is **no production semantic source change after the semantic candidate**. B10 therefore applies equally to the observed production HEAD.

## 3. CI independently verified

### Existing candidate/source-equivalent green evidence

I independently fetched the raw GitHub Actions logs for:

- run: `34831608087`
- job: `103935994524`
- checkout: `d180091c73be63bcce680748048ef731316f848b`
- CPython: `3.12.14`
- pytest: `8.4.2`
- formal: `420 passed, 1 warning`
- Reference: `15 passed`
- conclusion: `SUCCESS`

This confirms the prior green suite, but that suite did not include the B10 class.

### New adversarial red evidence

Probe branch commit:

`099acf3188ab28389ff70d1b265bdfd0cc82b2aa`

GitHub Actions:

- run: `34833864406`
- job: `103943128899`
- CPython: `3.12.14`
- pytest: `8.4.2`
- collected: `423`
- result: **420 passed / 3 failed / 1 warning**
- Reference suite: skipped because formal stage failed

The three failures are exactly the new B10 probes described below.

## 4. New adversarial probes

Added only on the independent audit branch:

`tests/unit/test_auditor_e_b10_contract_dispatch.py`

### Probe B10-1 — base WorldObject masquerading as Dependency

Minimal reproduction:

```python
fake = WorldObject(
    object_id="dep-masquerade",
    object_type=ObjectType.DEPENDENCY,
    subject_id="auditor-e-subject",
    revision=1,
    occurred=TemporalExtent.point(T),
    learned_at=T,
    recorded_at=T,
    created_by="auditor-e",
)
store.commit([fake], op(0, "reject-fake-dependency"))
```

Expected invariant:

A durable row labelled `dependency` must satisfy the frozen `Dependency` contract, including `dependent_ref`, `dependency_ref`, `dependency_type`, pinned refs, and Dependency validators.

Observed:

`SQLiteWorldStore.commit()` **succeeds**. The probe failed with:

`Failed: DID NOT RAISE StoreError`

### Probe B10-2 — base WorldObject masquerading as EvidenceSet

Minimal reproduction:

```python
fake = WorldObject(
    object_id="evidence-masquerade",
    object_type=ObjectType.EVIDENCE_SET,
    subject_id="auditor-e-subject",
    revision=1,
    occurred=TemporalExtent.point(T),
    learned_at=T,
    recorded_at=T,
    created_by="auditor-e",
)
store.commit([fake], op(0, "reject-fake-evidence"))
```

Expected invariant:

A durable row labelled `evidence_set` must satisfy the frozen `EvidenceSet` contract, including its evidence-content validator, `KnowledgeWindow`, pinned typed refs, selector rules, and frozen cutoff semantics.

Observed:

`SQLiteWorldStore.commit()` **succeeds**. The probe failed with:

`Failed: DID NOT RAISE StoreError`

This demonstrates that R4 cutoff enforcement is type-instance-dependent rather than durable-object-type-dependent: a masqueraded `evidence_set` bypasses EvidenceSet-specific validation entirely.

### Probe B10-3 — malformed durable Dependency poisons later public commits

Minimal reproduction:

1. Commit a base `WorldObject` labelled `ObjectType.DEPENDENCY`; candidate accepts it and advances world revision to 1.
2. Create two valid Observations and one genuine `Dependency`.
3. Commit them at expected world revision 1.
4. `_validate_dependency_graph()` loads all latest rows whose SQLite `object_type='dependency'` and executes:

```python
dependency = Dependency.model_validate(json.loads(row["payload_json"]))
```

5. The malformed durable row lacks `dependent_ref`, `dependency_ref`, and `dependency_type`.

Observed public failure:

raw `pydantic_core.ValidationError` escapes from `SQLiteWorldStore.commit()`.

CI reproduced:

- `dependent_ref`: Field required
- `dependency_ref`: Field required
- `dependency_type`: Field required

This is not mapped to `StoreError` / `AIOSProtocolError`.

## 5. Root cause

Affected implementation:

`src/aios_core/storage/idempotency.py`

```python
def normalize_world_object_for_persistence(obj):
    snapshot = obj.model_dump(mode="python", round_trip=True)
    return type(obj).model_validate(snapshot)
```

The revalidation trusts the caller-provided Python runtime class. It does **not** verify that this runtime class is the canonical frozen model corresponding to `snapshot["object_type"]`.

Affected implementation:

`src/aios_core/storage/sqlite_store.py`

- commit accepts `Iterable[WorldObject]`, so the base class is a legal public Python input type.
- persistence writes `obj.object_type.value` directly into the durable `object_revisions.object_type` column.
- EvidenceSet-specific cutoff selection uses `isinstance(obj, EvidenceSet)`, so a masqueraded base object labelled `evidence_set` does not receive EvidenceSet semantics.
- dependency pending validation uses `isinstance(obj, Dependency)`, so a masqueraded base object labelled `dependency` bypasses the dependency graph guard when first written.
- later `_validate_dependency_graph()` trusts the durable `object_type='dependency'` label and reparses the malformed payload as canonical `Dependency`, leaking raw ValidationError.

## 6. Affected files

Current production semantic files directly implicated:

- `src/aios_core/contracts/base.py`
- `src/aios_core/contracts/models.py`
- `src/aios_core/storage/idempotency.py`
- `src/aios_core/storage/sqlite_store.py`

Relevant existing tests that demonstrate the false-green gap:

- `tests/unit/test_dependency.py`
- `tests/unit/test_evidence_set.py`
- `tests/unit/test_reference_validation_m019.py`
- `tests/unit/contracts/test_m0_schema_snapshot.py`

New reproduction:

- `tests/unit/test_auditor_e_b10_contract_dispatch.py` on audit commit `099acf3188ab28389ff70d1b265bdfd0cc82b2aa`

## 7. Affected frozen contracts

### M0-009 — EvidenceSet first-class frozen contract

The frozen review states EvidenceSet has an exact schema and durable boundary revalidation. A payload can currently be durably labelled `evidence_set` while containing none of the EvidenceSet fields or validators. This makes the schema snapshot structural-only and creates a behavioral false-green.

### M0-015 — Dependency contract / cycle guard

The taskbook requires `Dependency` to contain `dependent_ref`, `dependency_ref`, and `dependency_type`, and states that proof/evidence dependency cycles are not allowed. A row durably labelled `dependency` can currently omit every one of those fields and bypass initial cycle validation.

### M0-017 — SQLite append-only world storage

The durable store is persisting rows whose declared `object_type` does not satisfy the frozen object contract represented by that type. This breaks the assumption that historical rows can later be safely deserialized according to `object_type`.

### M0-019 — mandatory reference validation

The frozen M0-019 review removed a public reference-validation bypass and states recursive reference validation is mandatory for every world commit. A masqueraded canonical subtype can avoid subtype-declared ObjectRefs entirely because its runtime object graph is only a base `WorldObject`.

### M0-022 — M0 contract total test / snapshot Gate

The existing schema snapshot verifies class schemas but does not verify that the generic durable entry point enforces canonical `object_type -> model` dispatch. Therefore the Gate is false-green against this behavioral class.

### M0-002 / B5 protocol boundary

After poisoning, a normal public `commit()` can leak raw Pydantic `ValidationError`, contrary to the protocol-level failure boundary discipline that was reopened and repaired for SQLite exceptions.

## 8. Severity

**BLOCKER / High**.

Reason:

- current M0 scope;
- reproducible on exact candidate semantics;
- allows invalid durable truth rows under frozen object types;
- bypasses subtype-specific validators and cross-object invariants;
- can poison future valid commits;
- can leak a raw implementation exception from a public store API;
- existing formal suite is green without detecting it, i.e. a direct Gate false-green.

I do not classify this as merely an M1 service-layer concern. The M0 taskbook explicitly freezes the object contracts and durable store and requires all object validation before insert. M0-021's service-layer deferral for Task/Event **state transitions** does not authorize the durable store to persist an object claiming to be `Task`, `Event`, `Dependency`, or `EvidenceSet` while not satisfying the frozen schema for that object type.

## 9. Why existing tests missed it

The current tests instantiate the expected concrete subclasses (`Dependency`, `EvidenceSet`, `Task`, `EventAnchor`, etc.) before calling `commit()`. That means Pydantic subtype construction already guarantees the canonical fields, so persistence revalidation appears strong.

M0-009 mutation tests only mutate an already-correct `EvidenceSet` instance and verify `type(obj).model_validate(...)` repairs/rejects mutation. They do not challenge whether `type(obj)` itself is the correct canonical type for `obj.object_type`.

M0-015 tests verify `Dependency` schema and graph behavior using actual `Dependency` instances. They do not submit a base/custom `WorldObject` carrying `object_type=DEPENDENCY`.

M0-019 tests intentionally define custom `WorldObject` subclasses with `object_type=ENTITY`, which demonstrates the store permits caller-defined subclasses, but they do not test reserved canonical object-type impersonation.

The schema snapshot cannot catch this because every canonical class schema is individually correct; the defect is in **runtime dispatch at the persistence boundary**, not in the schema definitions themselves.

## 10. Minimum repair boundary

Do not repair in this audit. The smallest reasonable repair boundary for chief-01 is:

1. Define an authoritative mapping from each frozen `ObjectType` to its canonical contract model.
2. At the durable boundary, validate the normalized payload through that canonical model selected by `object_type`, not through arbitrary caller `type(obj)`.
3. Reject runtime class / canonical object_type mismatches where required, or normalize to the canonical class before all subtype-specific semantic checks.
4. Ensure EvidenceSet cutoff logic and Dependency graph logic operate on the canonical normalized object, not only on caller-supplied `isinstance` identity.
5. Convert malformed stored-row reparse failures at public boundaries into a protocol-level `StoreError`/`STORAGE_FAILURE` (or another chief-ratified durable-corruption category) rather than leaking raw Pydantic exceptions.
6. Add adversarial tests for every reserved canonical `ObjectType` using base/custom WorldObject masquerading, with at least Dependency, EvidenceSet, Task, Event, Claim, Relation, and Dimension types.

A narrow patch that only catches the raw ValidationError in `_validate_dependency_graph()` is insufficient; it would leave the durable type masquerading and validator bypass intact.

## 11. Mandatory shared attack surface spot-checks

I independently inspected/reverified the following shared requirements while focusing Track E:

- stale exact idempotent replay path is before expected-world rejection;
- same idempotency key with different fingerprint conflicts;
- B8 deterministic unordered-collection canonicalization is present;
- OperationRequest durable revalidation is present;
- B9 SQLite busy classification uses SQLite result codes;
- non-lock SQLite OperationalError maps to STORAGE_FAILURE;
- commit uses one transaction and rollback on exception;
- current/floating self-reference rejection and pinned historical self-link code remain present;
- R4 EvidenceSet cutoff logic is present for actual `EvidenceSet` instances;
- same-transaction ref support is present;
- Dependency graph cycle guard is present for actual `Dependency` instances and Relation cycles are not globally banned;
- historical `as_of_world_revision` + `knowledge_cutoff` dual-lens implementation remains present;
- frozen Task/Event matrices were not modified after candidate;
- schema snapshot is structural evidence only and, in fact, B10 demonstrates its behavioral blind spot.

I did not find a new blocker in these previously known classes beyond B10, but B10 can bypass some of those protections by impersonating canonical object types.

## 12. Residual risks

Even after B10 is repaired, re-audit should include:

- custom subclasses of canonical contracts that weaken validators or alter serialization;
- custom validator/default-factory nondeterminism interacting with idempotency normalization;
- canonical `object_type` dispatch across restarts and old B10-poisoned databases;
- historical databases already containing malformed canonical-type rows and whether M0 requires a migration/rejection strategy before Gate;
- whether stable object ID revision history can be poisoned with an initially masqueraded canonical type and later real subtype;
- whether `SourceRef`/`ObjectRef` collection from custom BaseModels can hide typed refs through non-field properties or serializers;
- protocol mapping for durable corruption discovered during reads, not just dependency graph rebuilds.

## 13. M1 / M2 / M3 future Gates

These remain future scope unless separately contradicted by authoritative text:

### M1

- canonical public world service front doors;
- endpoint-type validation for typed refs;
- opaque dict pseudo-ref semantics;
- EvidenceSet selector materialization / full world-revision snapshot semantics (M1-006);
- public double-lens query contract;
- Worker raw-read capability wiring;
- historical malformed-row migration/recovery policy if M0 artifacts are retained.

### M2

- Session fixed snapshot + knowledge cutoff execution binding;
- runtime task/action recovery policy;
- open-string runtime status governance.

### M3

- Dependency reverse index;
- correction propagation;
- stale/rebuild cascades;
- independent evidence-loop detection beyond the current M0 cycle guard.

## 14. Previously FINAL PASS contracts to reopen

Recommended reopen / keep reopened pending B10 repair and independent re-review:

- `M0-009` — because a durable row labelled EvidenceSet can bypass the frozen EvidenceSet contract.
- `M0-015` — because a durable row labelled Dependency can bypass required fields and graph validation.
- `M0-017` — because the durable store accepts canonical-type/schema mismatches and can be poisoned.
- `M0-019` — because mandatory ref validation can be bypassed by canonical-type masquerading.
- `M0-022` — remains blocked; current green Gate suite is proven false-green against B10.

M0-002/B5 should also be reviewed for the raw `ValidationError` leak path, but the core root cause is B10 durable type poisoning rather than SQLite classification.

## 15. Final recommendation

Do not accept the current M0 Gate candidate as architecturally closed.

B10 is a reproducible current-M0 blocker. Repair should remain narrowly focused on canonical durable contract dispatch and corruption-safe public error handling, followed by independent red-team rerun of the exact probes above plus regression of B1-B9/R3/R4.

This report does **not** declare M0 FINAL PASS, does **not** authorize M1, and does **not** authorize parallel core development. Final Gate authority remains exclusively with `chief-01`.
