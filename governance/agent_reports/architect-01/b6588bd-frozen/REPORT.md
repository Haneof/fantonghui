BLOCKER FOUND

# AIOS Core M0 — Independent Software Quality Review

- Reviewer: architect-01 / Independent Software Quality Reviewer
- Exact candidate: `b6588bdaaa36d9dace4f9959dda0a89a370e1674`
- Candidate branch: `arena/integrator-typedref-replay-20260914`
- PR: [#5](https://github.com/Haneof/fantonghui/pull/5), inspected as open/draft, not merged.
- Evidence branch: `audit/architect-01-b6588bd-frozen-20260914`
- Scope: local Python model validation, serialization, persistence, idempotency, SQLite transactions and regression testing.
- Production implementation changed by reviewer: **NONE**.
- Final M0 acceptance authority: **chief-01**. This report does not grant M0 FINAL PASS or authorize M1.

## 1. Result

The two newly frozen files collect **294 cases**. On CPython **3.12.14**, Pydantic **2.13.5**, pytest **8.4.2**:

| Suite | Passed | Failed | Evidence |
|---|---:|---:|---|
| Initial newly frozen file | 266 | 16 | [redteam.log](redteam.log) |
| Initial collection | 282 collected | 0 collection errors | [collect-only.log](collect-only.log) |
| Initial file + separately frozen quality addendum | **278** | **16** | [combined-suite.log](combined-suite.log) |
| Combined collection | **294 collected** | 0 collection errors | [combined-collect-only.log](combined-collect-only.log) |
| Formal, after combined suite | **526** | **0** | [formal-after-addendum.log](formal-after-addendum.log) |
| Reference, after formal | **15** | **0** | [reference-after-addendum.log](reference-after-addendum.log) |

All 12 additional checks passed. The original 16 failures remain; no expected result was changed. No skip or xfail was introduced. The formal and Reference tests were not edited.

Two reproducible issues prevent acceptance:

1. **F1 / REDTEAM-X1 continuation:** a legacy record without semantic fingerprint accepts a typed-to-plain-dict change as exact replay. Eight cases fail across both reference classes and all four requested placements.
2. **F2 / REDTEAM-X3 continuation:** an extra entry with the same name as a declared model field is silently discarded. Four fresh requests are accepted and committed when rejection is required; four changed retries are incorrectly reported as exact replay.

These are different failure mechanisms. F1 concerns the information available in an older receipt. F2 concerns lossy normalization before validation and identity calculation.

## 2. Freeze provenance

This is a **new** suite. It is not a recreation of the unavailable 100-case artifact for `524f4d99...`; no result is attributed to that missing file.

| File | SHA-256 | Remote commit before first collection/execution |
|---|---|---|
| [test_redteam_b6588bd.py](test_redteam_b6588bd.py) | `780cd8d978ec584faa7678dd98c0d3f4a9db2a18a05a82f019144c72f5885647` | `a52e0918a13d86949a977b30d0c49d40618257b0` |
| [test_quality_addendum_b6588bd.py](test_quality_addendum_b6588bd.py) | `ca6a49dcb648bda2593c3d79f489205cae928c72d5eceae88f276b29c612d641` | `2bc5fbcc9fe8aeab4479ea75afa90e75fc673551` |

The first hash was recorded at `2026-09-14T14:33:07Z`. Its remote freeze preceded collection at `14:34:40Z` and execution at `14:34:41Z`. The addendum hash was recorded at `2026-09-14T14:56:33Z` and committed before its first collection. It adds the later clarified missing-reference and dirty-object-type requirements; it does not replace or correct the initial file.

Archive placement correction: the addendum's first remote copy at `2bc5fbcc...` was accidentally created as `undefinedtest_quality_addendum_b6588bd.py` on the repository's default `aios-2.0` branch, rather than the review branch. That misplaced copy was removed by `3c7fcf328ae0a4c7b60c89c96161b7f65d16ae58`. The identical frozen bytes are included in the final review-branch evidence directory. This mistake affected evidence placement, not test content, expectations, or the candidate/production branches; it is disclosed rather than omitted from the provenance.

[FREEZE.md](FREEZE.md), [ADDENDUM_FREEZE.md](ADDENDUM_FREEZE.md), [execution.json](execution.json), and [execution-addendum.json](execution-addendum.json) retain the chronology, exact commands, exit codes, and before/after digests. Both file digests are unchanged. The first remote frozen file was fetched and compared byte-for-byte with the local frozen content.

Some cases were informed by prior source inspection and exploratory observations on this candidate. This is a freeze before executing these new test files, not a claim of no prior knowledge of the implementation.

## 3. Environment and candidate isolation

- CPython: **3.12.14**.
- Primary Pydantic: **2.13.5**.
- pytest: **8.4.2**.
- Additional Pydantic: **2.10.6**, installed in a separate dependency directory.
- Exact source tree: detached checkout of `b6588bdaaa36d9dace4f9959dda0a89a370e1674`.
- All test commands explicitly select that source directory with pytest `pythonpath`; Reference selects its own source directory instead.
- Test files and generated logs reside outside the candidate working tree. Tracked candidate state was clean before and after the runs.
- The review branch was created from the exact candidate. Only evidence files were added there.

See [environment.txt](environment.txt), [environment-pydantic2106.txt](environment-pydantic2106.txt), [version-commands.txt](version-commands.txt), and [exact_candidate.txt](exact_candidate.txt).

Independent cloud inspection of PR #5 established base `524f4d99ea1827941300de47b76810d97a6c23e7` and head `b6588bda...`. The seven-file patch modifies two storage files and five tests; no model-schema or frozen snapshot change appears in that patch. The supplied Actions run `34853601694`, job `104007394770`, was also checked through its raw log: checkout `b6588bda...`, Python 3.12.14, Pydantic 2.13.5, 526 formal and 15 Reference passes. The local results above provide independent execution evidence; CI success is not the verdict.

## 4. F1 — legacy typed-to-dict false replay

**Classification: BLOCKER / High.** Affects M0-016 request identity and M0-017 durable receipt compatibility at this exact candidate. Keep those contracts and M0-022 open.

Failing test family:

`test_x1_semantic_identity_both_directions[True-typed-to-opaque-<place>-<ref_type>]`

- `<place>`: metadata, value, arguments, selector.filters.
- `<ref_type>`: ObjectRef, SourceRef.
- Expected: StoreError with `IDEMPOTENCY_CONFLICT`; all durable tables unchanged.
- Actual: no exception; `CommitResult(... world_revision=2, idempotent_replay=True)`.
- State before/after attempted replay: exactly equal in all five tables. The receipt is semantically incorrect even though it causes no new writes.

Minimal reproduction using the frozen file's helpers:

```python
store = seeded(tmp_path)                 # target@1, world 1
typed, request = request_at("metadata", ObjectRef(object_id="target", revision=1))
store.commit([typed], request)           # world 2
remove_semantic_fingerprint(store.db_path, request.idempotency_key)
plain, same_request = request_at("metadata", {"object_id": "target", "revision": 1})
result = SQLiteWorldStore(store.db_path).commit([plain], same_request)
assert result.idempotent_replay          # actual; required result is a conflict
```

The legacy setup removes only the internal `_request_fingerprint` member in a disposable database before the before/after measurement. It is a deliberate construction of the supported older receipt format, as in the integrator's own legacy tests; this suite does not claim to possess an original production database from the old release.

Relevant source:

- `src/aios_core/storage/sqlite_store.py`: `_get_idempotent_result()` falls back when the receipt lacks `_request_fingerprint`.
- `src/aios_core/storage/idempotency.py`: `legacy_request_fingerprint()` checks `_contains_typed_reference()` only on the **incoming** normalized request. A plain incoming dict passes that check. `stored_request_fingerprint()` reconstructs only the older JSON representation, which lacks the old runtime reference type.
- `tests/unit/test_integrator_legacy_replay_identity.py`: tests old plain dict to incoming typed ref, and exact plain JSON. It does not test an old typed ref to incoming plain dict.

Important compatibility constraint: two old requests, one containing a typed ref and one containing the equivalent plain dict, can leave identical stored JSON. If no independent provenance survives, their original types cannot be reconstructed. Keeping unrestricted exact legacy replay for ref-shaped plain JSON while also rejecting the indistinguishable typed-to-dict case is not achievable using those bytes alone.

Minimum remediation boundary: define an explicit compatibility policy with Chief. Preserve trusted original semantic provenance where it exists; otherwise reject ambiguous older receipts rather than guess. If Chief chooses to narrow legacy JSON compatibility, that is an explicit contract decision, and the old passing tests must remain archived with their original expectations. Do not silently change the current frozen suite. Do not solve this by treating all typed refs as plain dictionaries or by instructing callers to retry committed work under a new key.

M1 and later implication: a public operation could report that a semantically different request was already completed. That undermines operation audit identity and any recovery process relying on exact replay.

## 5. F2 — same-name extra data is silently discarded

**Classification: BLOCKER / High.** Affects REDTEAM-X3, M0-009/M0-016 persistence normalization and the M0-017 storage boundary at this exact candidate. Keep those contracts and M0-022 open.

Failing test families:

`test_x3_dirty_extra_never_silently_erased[False-shadow-extra-<target>]`

`test_x3_dirty_extra_never_silently_erased[True-shadow-extra-<target>]`

Targets: canonical Observation, OperationRequest, EvidenceSelector, and nested ObjectRef.

- Fresh expected: StoreError `INVALID_ARGUMENT`, zero durable changes.
- Fresh actual: no exception; a complete new world commit is written after the extra entry is dropped.
- Retry expected: StoreError `IDEMPOTENCY_CONFLICT`, zero durable changes.
- Retry actual: no exception; `idempotent_replay=True` after ignoring the changed extra data.

Minimal fresh reproduction:

```python
store = seeded(tmp_path)
obj = obs()
object.__setattr__(obj, "__pydantic_extra__", {"object_id": "must-not-disappear"})
store.commit([obj], op(rev=1))           # actual success; required rejection
```

This deliberately supplies a dirty Pydantic instance, within the specified durable revalidation scope. It is not a claim that an ordinary validated JSON constructor produces duplicate field names. The same conflict can exist in the separate declared-field and extra-field dictionaries of a live instance.

Mechanism: `_model_items()` in `src/aios_core/storage/idempotency.py` first copies declared fields, then uses `data.setdefault(key, item)` for `__pydantic_extra__`. An extra key already present as a declared field is discarded before canonical validation and fingerprinting. Later validation cannot reject data it no longer sees.

Fresh before/after summary, identical for all four targets:

| State | Before | Actual after |
|---|---:|---:|
| world revision | 1 | 2 |
| world_commits rows | 1 | 2 |
| object_revisions rows | 1 | 2 |
| operations rows | 1 | 2 |
| idempotency_records rows | 1 | 2 |

The new rows consistently describe the accepted request with the extra entry removed. This is an incorrect acceptance/data-preservation result, **not** a partial transaction. On the four retry variants, the world remains at 2 and every table remains byte-for-byte equal; the returned replay result is incorrect.

Existing tests cover extras with new names and preservation of allowed nested extras. They do not cover an extra name colliding with a declared field. The new file tests both paths without modifying the implementation.

Minimum remediation boundary: detect conflicting declared/extra namespaces before flattening; return the frozen fresh/retry protocol error rather than silently choosing one value. Apply consistently to OperationRequest, canonical WorldObject, nested models and refs. The error conversion must also cover failures raised during the initial snapshot operation. Ordinary allowed extras with distinct names must continue to survive.

M1 and later implication: accepted audit inputs and stored payloads can disagree, and retries can ignore meaningful submitted data. That breaks the preservation and identity assumptions used by downstream services.

## 6. Coverage and bounded conclusions

| Required area | New evidence / conclusion |
|---|---|
| X1 / A, typed vs dict | Both directions, ObjectRef/SourceRef, all four placements, store reopen, stale original expected revision, exact typed/plain retries and marker-shaped values. New semantic receipts pass; legacy reverse direction fails F1. |
| X2 / B | 72 cases: four placements × fresh/retry × nine values, including all requested serialization values plus non-string mapping keys. All pass with full table comparison; no unhandled serialization exception observed in these cases. |
| X3 / C | Allowed extras nested two levels survive and alter identity. Ordinary unknown extras/model_copy fields reject. Eight same-name extra cases fail F2. |
| X4 / D | ObjectRef/SourceRef across four placements: coercible string revision, malformed/negative revision, floating None, fresh/retry and canonical integer replay. All pass. None is tested where a floating ref is allowed, not as a claim that EvidenceSet members may float. |
| Operation normalization / E | 22 routing cases, plus changed B1 request fields and X2 arguments. Valid bytes and integer strings normalize; list/None/blank and malformed scalars follow the expected fresh/retry priority. |
| Legacy / F | Pure JSON exact replay passes, including ref-shaped dicts; typed incoming legacy requests conservatively conflict. These passing controls expose the compatibility tension with F1. |
| Reference consistency / G | Both current/floating self refs reject; pinned historical self and distinct same-transaction mutual refs succeed; exact cutoff before/at/after cases and stale writer rejection pass. Addendum supplies six direct missing-reference cases, all passing. |
| Canonical identity / H, B10 | Bare WorldObject claiming Dependency/EvidenceSet/Claim rejects. Addendum verifies wrong concrete Observation claims, invalid dirty object_type and valid string-to-enum normalization; all pass. |
| B1 | Changed operation fields conflict; object input ordering and argument-key ordering remain equivalent; concurrent same-key requests commit once. |
| B4 | Current/floating self checks and legal historical self/mutual references remain consistent. |
| B6 | Coercible nested coverage value replays after reopen. Identical unordered values replay across separate processes using different Python hash seeds. |
| B11 | Integer and string mapping-key collision input is rejected across fresh/retry placements instead of losing one entry. |
| Atomic transactions | Trigger failure after first object INSERT rolls back all five tables; following transaction succeeds without revision gap. Concurrent writers produce one complete winner. |
| History | World-only and cutoff-only controls differ as expected; combined lenses exclude both future-known content and later backfills from the older snapshot. |

The formal suite additionally rechecks state machines, schema snapshot and four required M0 fixtures. Their green results do not invalidate F1/F2 and do not prove future service wiring.

## 7. Atomicity interpretation

`error_without_writes()` records all rows of world_meta, world_commits, object_revisions, operations and idempotency_records before and after every expected failed commit. It does this even if the implementation returns success or raises an unexpected exception, before checking the expected exception class/code. Thus the new evidence is stronger than checking only row counts.

- All expected-error cases that passed retained the complete prior state.
- Eight F1 failures and four F2 retry failures also retained prior state, but returned an incorrect replay success.
- Four F2 fresh failures changed state because they were incorrectly accepted. The zero-write assertions remain red and are not waived.
- The explicit mid-insert failure leaves no partial rows, consumes no world revision and permits a following valid transaction.
- Concurrent tests account for the legitimate winning transaction: exactly one world commit/object/operation/receipt remains at world revision 1. A losing writer cannot leave an additional record.

No physical power-loss, disk-full, filesystem fault, or every possible commit-system-call checkpoint is claimed as covered by this new suite.

## 8. Pydantic 2.10.6 and residual risks

The identical frozen files also collect/run as ordinary behavioral tests under CPython 3.12.14 / Pydantic 2.10.6 / pytest 8.4.2:

- Combined new suite: **278 passed / 16 failed**, same F1/F2 cases.
- Formal: **525 passed / 1 failed**, solely `test_m0_schema_snapshot_matches_frozen_contract`.
- Reference: **15 passed**.

See [combined-suite-pydantic2106.log](combined-suite-pydantic2106.log), [formal-pydantic2106.log](formal-pydantic2106.log), [reference-pydantic2106.log](reference-pydantic2106.log). The initial 282-case repeat and its metadata are preserved separately.

The supported dependency range does not, by itself, promise identical internal `model_json_schema()` rendering across Pydantic minor versions. This observed hash difference is tracked as a toolchain reproducibility issue, not counted as an X1–X4 behavior regression or a new blocker here. The old 524f4d99 suite/artifact was not reconstructed or rerun. Pin the snapshot-generation environment or formally define a versioned snapshot policy.

Other residuals:

- Legacy compatibility needs a documented policy for information absent from older records; no inference can recover a discarded type tag.
- Scope is trusted Python software and specified data boundaries. Arbitrary custom serializers, model callbacks and every possible Python object are not exhaustively characterized.
- The new tests do not implement M1 service-level endpoint typing, EvidenceSet materialization/coverage consistency, M2 session read binding/recovery, or M3 correction propagation. Their deferred status must not be described as implemented.
- Fixture and structural-schema passes cannot prove all behavioral invariants; keep these exact new files as a separate permanent Gate input.

## 9. Recommendation to Chief

1. Keep PR #5 / exact `b6588bda...` blocked for M0 acceptance on F1/F2.
2. Decide the ambiguous legacy-receipt policy explicitly; do not silently weaken exact semantic identity or the retained JSON-compatibility tests.
3. Correct same-name extra handling before normalization loses the distinction, preserving both ordinary allowed extras and fresh/retry protocol precedence.
4. Assign implementation work separately. This reviewer made no implementation changes.
5. Run these unchanged frozen files against the next exact candidate. Preserve this run and its 16 failures. Any formally approved expectation change must be a separately versioned suite with documented rationale.
6. Re-run formal and Reference after integration and obtain Chief's final decision. This report does not merge anything or start M1.

## 10. Evidence inventory

The directory contains the two frozen test files, both freeze records, explicit test digest, primary and combined collection outputs, complete pytest outputs for all recorded runs, environment/command metadata, exact candidate identifier, reproducible runners, this report, and [SHA256SUMS](SHA256SUMS).

`SHA256SUMS` covers every other delivered regular evidence file (it does not hash itself). All files are committed on the independent review branch. The existing candidate source and tests remain unchanged.
