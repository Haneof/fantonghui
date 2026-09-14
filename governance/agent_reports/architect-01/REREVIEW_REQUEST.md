# architect-01 — M0 Gate third-patch independent re-review request

Status: **AUTHORIZED / REQUIRED / READY TO START**

You are `architect-01`, the independent GPT-6-class Principal Architect / Red Team.

This request supersedes all earlier re-review requests. Do not assume any Chief patch or green CI is correct; falsify it independently.

## 1. Review base

Repository: `Haneof/fantonghui`

Production branch: `arena/01a09bc6-fantonghui`

Original Gate candidate:
`95cec4142bdd9a87011bbad197e05ec1d27aeb57`

Prior red-team evidence:
- first report `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- second independent arena report `42f19a3f39a1e4ac375ac315d6dcf8f487725830`
- latest formal re-review report `c068fc1fa0de528ab17cbfc4a4c6f9112b3ae164` — `BLOCKER FOUND`

Earlier patches:
- B1/B3 `8ab574c6b33b2238b468c812992a92ba56ab3f71`
- B2 `e06bc80e43ea26be2be726232158cb2719092f11`
- B4/B5 first patch `a99326c5034118b3a497e3be0d53ac9466445467`

Latest semantic repair:
`f38fdd2aa64e31b92c5353206a8aef62c9322087`

Current exact green candidate, including explicitly approved schema snapshot change:
`9c080f693917c2c99bfbe6aa924e5f3cb54744a0`

Chief latest review:
`reviews/M0/M0_gate_B6_B7_B5_R4_resolution_2026-09-14.md`

Production progress/review commits after `9c080f...` are documentation archives only and must not be confused with the semantic candidate.

## 2. CI evidence to verify independently

Expected structural-drift run after semantic repair:
- run `34827058782`
- job `103921528459`
- formal: 417 functional tests passed, exactly one failure in `test_m0_schema_snapshot_matches_frozen_contract`
- reason claimed by Chief: adding approved `STORAGE_FAILURE` changed ErrorCode enum and ErrorResponse schema hash while snapshot still held the previous frozen form
- Reference skipped because formal stage failed

Latest exact candidate CI:
- run `34827250470`
- job `103922130589`
- checkout `9c080f693917c2c99bfbe6aa924e5f3cb54744a0`
- CPython 3.12.14 / pytest 8.4.2
- formal **418 passed**, 1 known warning
- Reference **15 passed**
- SUCCESS

Verify raw logs and commit ancestry yourself. Do not accept the Chief's classification of the failed run without checking the diff and generated snapshot.

## 3. B6 — normalized idempotency identity

Original counterexample from your previous report:
- mutate nested `EvidenceCoverage.observed_count` to string `"1"` after construction;
- first write succeeds because persistence revalidation normalizes it to integer `1`;
- retry/restart previously fingerprinted the unnormalized live object and conflicted with normalized durable state.

Chief patch claim:
- `normalize_world_object_for_persistence()` and `normalize_operation_for_persistence()` define the canonical representation;
- incoming idempotency fingerprint is computed from this normalized representation;
- durable writes use the same normalization path;
- exact stale replay still happens before expected-world rejection;
- valid altered request still returns `IDEMPOTENCY_CONFLICT` with zero mutation.

Attack at least:
1. the exact original coercible nested mutation reproduction, before and after store restart;
2. nested string->int, int->float, enum/string, datetime timezone-equivalent representations where Pydantic may normalize;
3. arguments JSON ordering/equivalent serialization;
4. objects input ordering;
5. a normalization that changes a payload but remains Pydantic-valid;
6. invalid mutated object on an already-used key;
7. invalid mutated OperationRequest on an already-used key;
8. same-key/different-normalized-request concurrency;
9. old pre-B6 databases produced by the prior candidate;
10. crash/no-receipt retry.

Required invariant:
- one logical accepted durable request has one stable replay identity;
- exact retry after restart replays the original result and never advances world revision again;
- semantically/durably different request cannot alias the old key;
- normalization cannot silently turn materially distinct valid requests into the same identity unless that equivalence is explicitly justified by durable serialization semantics.

Check whether normalizing for fingerprint and then normalizing again for persistence can diverge through mutable/custom model behavior, validators, default factories, or time-dependent validation.

## 4. B7 — OperationRequest durable revalidation

Original counterexample:

```python
r = valid_request()
try:
    r.reason = " "
except ValidationError:
    pass
assert r.reason == " "
store.commit([obj], r)  # previously succeeded
```

Chief patch claim:
- existing-key replay/conflict is still first;
- reused-operation check remains before new-write validation;
- expected-world check remains before new-write validation;
- then a fresh `OperationRequest.model_validate(round_trip_dump)` snapshot is required before any durable insert;
- a dirty invalid request on a new write returns `INVALID_ARGUMENT / operation_persistence_revalidation_failed` and leaves all durable state unchanged;
- a dirty invalid retry using an already committed idempotency key must not mutate state or accidentally bypass conflict logic.

Attack every identity/audit field:
- operation_id
- session_id
- operation_name
- arguments
- expected_world_revision
- reason
- idempotency_key

Include after-validator failures, field-validator/type-coercion cases, nested arguments mutations, stale expected revision, reused operation_id, and existing-key retries.

Verify the exact ordering does not reopen B1:

existing-key replay/conflict → reused operation-id check → expected-world check → OperationRequest revalidation → WorldObject revalidation → revision/type/ref/dependency validation → writes.

If a better ordering is required, explain the minimal counterexample and which frozen promise changes.

## 5. B5 — storage protocol closure

Chief reopened M0-002/M0-017 and added:

`ErrorCode.STORAGE_FAILURE`

Claimed mapping:
- busy/locked => `VERSION_CONFLICT`, `reason=storage_busy`
- connect unavailable => `STORAGE_FAILURE`, `reason=storage_unavailable`
- IntegrityError => `STORAGE_FAILURE`, `reason=sqlite_integrity_error`
- non-lock OperationalError => `STORAGE_FAILURE`, `reason=sqlite_operational_error`
- other DatabaseError => `STORAGE_FAILURE`, `reason=sqlite_database_error`

The connection creation and PRAGMA/setup lifecycle are now claimed to be inside the same mapped boundary with safe close.

Attack at least:
1. parent directory missing / connect failure;
2. database path is a directory;
3. read-only DB / permission-style SQLite error where reproducible;
4. missing/corrupt schema table;
5. malformed database file if safely reproducible in a temp path;
6. busy/locked at connect/PRAGMA/BEGIN stages;
7. forced constraint/integrity failure after one or more inserts;
8. failure during initialization;
9. subsequent successful recovery where the fault is removed;
10. ensure `StoreError` itself is not accidentally rewrapped by the sqlite exception handlers.

Judge whether `STORAGE_FAILURE` is a coherent M0-002 protocol category and whether any SQLite fault still leaks as raw implementation exception through public Store APIs.

Do not require M0 to implement the future runtime retry engine. But ensure the error code/reason is sufficient for later retry/stop/escalate policy and does not misclassify a caller input error as infrastructure failure without a defensible rule.

## 6. R4 — EvidenceSet frozen knowledge cutoff

Original counterexample:
- Observation learned at 10:00
- EvidenceSet learned at 10:00
- EvidenceSet frozen knowledge cutoff 09:00
- member_refs includes that Observation
- old store persisted it although the member is invisible under the set's own declared cutoff.

Chief ruling / patch claim:
- all recursively collected typed ObjectRef/SourceRef contained by an EvidenceSet are checked using `EvidenceSet.knowledge_window.knowledge_cutoff`;
- this includes member/support/counter/context refs and selector dimension refs;
- other WorldObjects continue using their own learned_at visibility rule;
- same-transaction EvidenceSet->new member remains legal when the pending member learned_at is <= frozen cutoff;
- current/floating self-reference protections remain;
- M0 does **not** claim to enforce full `knowledge_window.world_revision` materialization semantics; selector materialization/world snapshot freeze remains M1-006 Gate.

Attack at least:
1. each member/support/counter/context role with target learned after cutoff;
2. selector.dimension_refs after cutoff;
3. target learned exactly at cutoff;
4. UTC-equivalent timestamps / timezone offsets;
5. same-transaction target before/at/after cutoff;
6. existing target prior revision visible at cutoff while later revision is not;
7. floating refs if any EvidenceSet path can still contain one through mutation/revalidation;
8. historical self-link and unrelated same-tx mutual refs regression;
9. whether using generic recursive `_collect_refs` accidentally applies evidence cutoff to metadata or opaque dicts that are not typed refs;
10. whether `world_revision` deferral to M1 creates an M0 contradiction with R2 §5.2/5.3 or M0-009/M1-006 taskbook wording.

If full world_revision enforcement is constitutionally required in M0, return `RULING REQUIRED` with exact conflicting text. Otherwise explicitly record M1-006 as mandatory Gate.

## 7. recorded_at ruling

Chief ruling:
- `recorded_at` = controlled AIOS/simulator recording time on the canonical simulated/user world timeline;
- `world_commits.committed_at` = physical durable SQLite commit time;
- M1 production ingestion must prevent arbitrary callers from forging learned/recording time; simulator/import path must carry provenance.

Audit this interpretation against Constitution/R1/R2/taskbook and historical M0-004/M0-005/M0-020 semantics.

Return `RULING REQUIRED` if any frozen text unambiguously defines `recorded_at` as physical DB ingestion time such that this interpretation would be a semantic rewrite.

## 8. Snapshot change

Because `STORAGE_FAILURE` changes the frozen ErrorCode enum, Chief explicitly approved a structural snapshot update.

Verify the candidate snapshot change is exactly justified:
- ErrorCode adds only `STORAGE_FAILURE`;
- ErrorResponse schema hash changes as a consequence;
- no unrelated model hashes/transitions were silently altered;
- the first failed snapshot run is consistent with that diff;
- no manual snapshot editing accidentally changed another hash.

Remember: snapshot green is structural evidence only, not behavioral proof.

## 9. Regression Gate

Re-run/falsify enough of the whole M0 surface to ensure the third patch did not regress:
- B1 altered request isolation and stale exact replay;
- B2 threat-model wording / scanner not treated as sandbox proof;
- B3 durable Dependency cycles, including current revision replacement and concurrency;
- B4 floating/current self-reference and legal historical pinned self-link;
- M0-009 mutation/persistence boundary;
- M0-018 atomic commit/rollback/no world-revision gap/concurrent writers;
- M0-019 same-tx refs and visibility;
- M0-020 world revision + knowledge cutoff intersection and mutable subject behavior;
- M0-021 Task/Event transition matrices;
- schema snapshot;
- four named Gate fixtures.

Pay particular attention to whether the new generic normalization helper changes object identity, revision, timestamps, refs, or JSON representation in ways existing tests do not cover.

## 10. Residuals that remain future Gates unless you find a present contradiction

Explicitly classify:
- endpoint-type validation for typed refs — M1 candidate Gate;
- opaque/plain dict pseudo-ref semantics — M1 Gate;
- schema behavioral false-green class — M1 adversarial-test discipline;
- CI dependency drift / reproducibility policy — M1 Gate;
- Worker raw-read capability wiring — M1 Gate;
- public double-lens historical query — M1 Gate;
- Session fixed snapshot+cutoff execution — M2 Gate;
- open-string runtime status vocabulary — M2 Gate;
- reverse index/correction propagation/independent evidence loops — M3 Gate.

Do not promote a deliberately deferred feature into an M0 blocker unless authoritative text actually requires it now. Conversely, do not downgrade a current self-contradictory durable contract merely because a service exists later.

## 11. Deliverable

Update:
`governance/agent_reports/architect-01/LATEST.md`

First line exactly one of:
- `ARCHITECTURE PASS`
- `RULING REQUIRED`
- `BLOCKER FOUND`

If PASS:
- list exact candidate audited;
- list exact CI independently verified;
- state B6/B7/B5/R4 closure separately;
- list residual risks + mandatory M1/M2/M3 Gates.

If RULING/BLOCKER:
- provide minimal reproducible counterexample;
- affected files/commits/contracts;
- why current tests missed it;
- smallest repair boundary;
- whether any previously restored FINAL PASS must reopen.

Do not modify production code. Do not declare M0 FINAL PASS. Final Gate authority remains with `chief-01`.
