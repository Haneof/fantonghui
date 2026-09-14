BLOCKER FOUND

# Independent M0 Gate red-team audit — auditor-e-02

- **AUDITOR_ID:** auditor-e-02. Initially selected auditor-e; changed after inspecting the governance filenames because auditor-e.md and auditor-e-01.md already exist. Neither report was overwritten. This report is not authored by either prior auditor.
- **TRACK:** E — cross-cutting / unknown unknowns.
- **Date:** 2026-09-14.
- **Exact requested semantic candidate:** `659157b849a0dbaad241c3e316dcd98eb7c72df7`.
- **Requested production HEAD:** `5acef4a4f43895a0762462e1f30e4f923da979a0`.
- **Observed production HEAD, checked twice:** `4781826184ec680582fac11e965582c5070b053f` on `arena/01a09bc6-fantonghui`.
- **Governance input revision:** `480c3c9668bb6f774fa85c629194789f70f8f8b9` on `governance/aios-control-plane`.
- **Audit working branch:** `arena/01a09fa9-fantonghui`. This session cannot switch branches or push another branch. Evidence/report are submitted from this branch for governance integration, not directly committed to the governance branch. Production code, production branch, and architect-01/LATEST.md were not modified.
- **Verdict scope:** new counterexamples reproduce against BOTH the requested candidate and observed HEAD. Proposed finding IDs **E-B12** and **E-B13** below are local to this audit; chief-01 owns global numbering/adjudication.

## 1. Provenance and actual candidate-to-HEAD comparison

First action was fetching `governance/agent_reports/PARALLEL_M0_REVIEW_REQUEST.md` directly through GitHub API. Subsequently fetched git objects and read CURRENT_STATE, REREVIEW_REQUEST, REREVIEW_CONTINUATION_B8_B9, the referenced Chief blocker/follow-up reviews, and relevant authoritative Constitution/R1/R2/taskbook passages. No user file copying was requested. Candidate and observed HEAD were extracted with `git archive` into separate workspaces, without checking out either production or governance branch.

Independent git results:

1. `659157b...` is an ancestor of `5acef4a...`. Their tree diff is only `reviews/M0/M0_gate_B8_B9_followup_2026-09-14.md` (99 added lines). The requested comparison really is documentation-only.
2. `659157b... -> d180091...` also changes only that review archive. That CI is source-equivalent to the requested candidate.
3. **Actual HEAD is NOT source-equivalent to 659157b.** Diff to `4781826...`: eight files, 617 insertions, 97 deletions, including:
   - new `src/aios_core/contracts/registry.py`;
   - changed `src/aios_core/storage/idempotency.py`;
   - changed `src/aios_core/storage/sqlite_store.py`;
   - new `tests/unit/test_m0_gate_fifth_followup.py`;
   - changed `tests/unit/test_reference_validation_m019.py`;
   - three review files.
4. Inspected those actual source diffs. The observed HEAD uses the canonical ObjectType registry, rejects non-string Mapping keys, and adds corrupt Dependency payload mapping. I do not present B10/B11 as newly discovered, unrepaired findings. Their Chief review is input, not proof that the entire HEAD passes.

The production branch remained at the observed SHA on the final remote check during this audit. Conclusions are pinned to these SHAs, not to any later moving HEAD.

## 2. Independently checked CI and local environment limits

### GitHub evidence

| Run | API head SHA | Independently observed result |
| --- | --- | --- |
| [34831346707](https://github.com/Haneof/fantonghui/actions/runs/34831346707) | `83a23302ff3c88a409db988059c03e5ec27a7ace` | failure; metadata archived |
| [34831608087](https://github.com/Haneof/fantonghui/actions/runs/34831608087) | `d180091c73be63bcce680748048ef731316f848b` | success; job `103935994524`, pytest and Reference steps success |
| [34837086293](https://github.com/Haneof/fantonghui/actions/runs/34837086293) | `4781826184ec680582fac11e965582c5070b053f` | **failure**; job `103953253641`, pytest failure, Reference skipped |

GitHub check annotations for current HEAD additionally report exit code 1. **Raw CI logs could not be retrieved**: both `gh run view --log` and jobs/logs redirected to external result/blob hosts that failed with TLS/EOF. Therefore the earlier Chief-reported CI test counts and exact CI dependency versions are NOT claimed as independently verified raw-log evidence. API status, SHA, job and step conclusions were independently verified and saved.

### Local execution

Actual local environment: **CPython 3.11.2**, pytest **8.4.2**, Pydantic **2.13.5**; also repeated the new probes on **Pydantic 2.10.6**. Exact runtime details are in `evidence/auditor-e-02/environment.txt`.

The project declares Python >=3.12. Attempted to obtain CPython 3.12.14 through uv/GitHub release assets and python.org; downloads were blocked by certificate/TLS/EOF failures. **These local runs are supplementary falsification, not supported-runtime exact CI certification.** A 3.12 repeat of the attached probes is a required verification boundary before closure. The identical failures under both tested Pydantic versions, plus the source-level transformation, strongly locate the defects; this report does not hide the runtime limitation.

| Local run | Result |
| --- | --- |
| Requested candidate, entire formal suite | **420 passed, 1 warning** |
| Requested candidate, separate Reference source/suite | **15 passed** |
| Observed HEAD, entire formal suite | **24 failed, 409 passed, 1 warning** |
| New independent probes against requested candidate | **11 failed, 17 passed** |
| Same probes against observed HEAD | **11 failed, 17 passed** |
| Same observed-HEAD probes on Pydantic 2.10.6 | **11 failed, 17 passed** |

Tests assert the intended frozen contract; failures are not disguised as passing tests that assert a defect exists.

The 24 HEAD baseline failures include old Dummy/custom canonical-type fixtures in test_errors, test_refs, test_time, test_world_object_revision. In particular, cases expecting later revision/reference error codes now fail at canonical schema revalidation. This is a real **red regression Gate**, not proof that all 24 corresponding production invariants are broken. The new controls use actual canonical Observation/Relation/EvidenceSet/Dependency models to avoid that ambiguity. Do not delete the failing coverage or loosen the registry just to make CI green.

## 3. E-B12 — typed references erased before durable reference validation

**Severity: HIGH / BLOCKER FOUND.** Present at requested candidate AND observed HEAD. Interaction: normalization + Any payload + typed references + self-reference/cutoff enforcement.

### Minimal reproduction

With the supplied probe helpers:

```python
s = SQLiteWorldStore(path)
x = obs('o', metadata={
    'nested': [{'typed': ObjectRef(object_id='missing', revision=1)}]
})
assert s._collect_refs(x) == [ObjectRef(object_id='missing', revision=1)]
s.commit([x], op())  # ACTUAL: success, world revision 1
```

The input is a **real ObjectRef**, not a caller-supplied `{'object_id': ..., 'revision': ...}` pseudo-ref dictionary, custom WorldObject subclass, monkeypatch, or raw database modification.

Observed mechanism:

```text
_collect_refs(original) -> [ObjectRef(...)]
normalize_world_object_for_persistence(original)
_collect_refs(normalized) -> []
commit -> success; metadata persists the now-untyped dictionary
```

`model_dump(mode='python', round_trip=True)` recursively converts a BaseModel stored under Any into a dictionary. `model_validate` reconstructs refs in formally typed fields but does NOT reconstruct them in `metadata`, `Observation.value`, or `EvidenceSelector.filters`. The store replaces its object list with that normalized version before reference collection.

Independent probes demonstrate seven improper successes:

1. ObjectRef to nonexistent object in nested metadata.
2. SourceRef to nonexistent object in nested metadata.
3. Floating ObjectRef to the object's own current identity.
4. Pinned ObjectRef to the object's own pending/current revision.
5. EvidenceSet metadata typed ref to a target learned after its frozen cutoff.
6. EvidenceSelector.filters typed ref to that same future-known target.
7. Observation.value typed ref to a target learned after the referencing Observation.

Cutoff reproduction: commit `early` at 09:00 and `late` at 10:00; create EvidenceSet at 10:00 with cutoff 09:00, formal member `early@1`, and metadata `{'typed': ObjectRef('late',1)}`. **Actual:** EvidenceSet commits at world revision 2 and stores `late@1` in metadata. **Expected:** NOT_FOUND / reference_not_visible_or_missing, no writes. Both normal objects and the EvidenceSet are canonical frozen models.

### Affected files

At observed HEAD:

- `src/aios_core/storage/idempotency.py:93-103`: destructive typed-to-dict normalization before ref checking.
- `src/aios_core/storage/sqlite_store.py:313-334`: collector recognizes genuine ObjectRef/SourceRef but not already-erased type information.
- `src/aios_core/storage/sqlite_store.py:458-474,532-567`: object replacement occurs before recursive reference validation.
- `src/aios_core/contracts/base.py::WorldObject.metadata` and models.py Any/filter fields are accepted entry points, not themselves necessarily defective.

Equivalent paths exist in the original candidate; the canonical registry patch does not restore nested Any type information.

### Frozen contracts violated / scope defense

- Authoritative chief taskbook **M0-019 A/C/H/I**: validate references before any durable write; recursively collect ObjectRef/SourceRef in Pydantic objects; no broken refs; do not silently discard invalid refs to pass validation.
- `reviews/M0/M0-019_final_PASS_2026-09-14.md`: recursive ObjectRef/SourceRef validation is mandatory for every world commit; missing/not-yet-visible targets fail before writes.
- Chief B4 ruling: current/floating self-reference rejected; historical pinned self-reference stays legal.
- Chief R4 ruling, `M0_gate_B6_B7_B5_R4_resolution... §2.4`, and REREVIEW_REQUEST §6: recursively collected typed refs contained by EvidenceSet obey its own cutoff.

**This is not a demand to interpret opaque input dictionaries in M0.** A separate passing negative control verifies that an input plain pseudo-ref dictionary remains opaque. The defect is silently turning a real, presently discoverable typed reference into such an opaque dictionary before mandatory validation. If chief-01 instead intends “only references declared in schema fields count, regardless of actual typed values accepted elsewhere,” that requires an explicit narrowing of the current recursive-typed-ref contract; it is not a closure already established by the M1 pseudo-ref deferral.

### Why existing tests miss it / false-green

B4/R4 tests place refs in schema-declared fields that Pydantic reconstructs. B6/B8 canonicalization tests exercise Any containers but not the preservation of reference-validation semantics across normalization. The schema snapshot describes field shapes, not runtime type erasure. Therefore original candidate can pass all 420 formal tests while all seven new behavioral assertions fail.

### Minimum repair boundary — recommendation only, no fix applied

Preserve and validate the semantic typed-ref information through the normalization boundary, or explicitly reject typed references in unsupported opaque fields before information is lost. Keep canonical model enforcement, normalized identity, stale replay priority, correct cutoff, historical self-links and same-tx mutual refs intact. Do not simply reinterpret every lookalike dictionary as a ref. Replay semantics also need attention: typed ref-bearing input must not silently become equivalent to unvalidated opaque data in a way that bypasses the frozen guarantee.

Keep **M0-009 / M0-017 / M0-019 / M0-022** open; review **M0-016** when deciding typed-vs-opaque normalization/replay identity. This finding alone does not show a new exact-version Dependency-cycle failure.

## 4. E-B13 — canonicalization failure escapes the protocol on new writes and retries

**Severity: MEDIUM / BLOCKER FOUND (protocol/idempotency boundary).** Present at both SHAs; no partial-write corruption observed.

### Minimal reproduction

```python
obj = obs(value='ok')
request = op(arguments={'value': 'ok'})
s.commit([obj], request)
request.arguments['value'] = b'\xff'
s.commit([obj], request)
# ACTUAL: raw UnicodeDecodeError
# EXPECTED: StoreError(IDEMPOTENCY_CONFLICT), zero writes
```

On a fresh key, either `Observation.value=b'\xff'` or `OperationRequest.arguments['value']=b'\xff'` also passes live schema acceptance but escapes as **UnicodeDecodeError**, rather than protocol INVALID_ARGUMENT. No arbitrary code execution/custom classes are needed. Revalidation confirms the bytes remain accepted under the current Any schema.

Four probe variants cover fresh/retry × object/arguments. All fail the expected protocol assertion. Every variant independently confirms no change to `(world revision, world_commits, object_revisions, operations, idempotency_records)`.

### Affected files / root cause

- `src/aios_core/storage/idempotency.py:59-64`: fallback calls TypeAdapter JSON conversion, which can raise UnicodeDecodeError; other exploratory inputs also exposed PydanticSerializationError or UnicodeEncodeError, but the verdict's automated reproducer only relies on non-UTF8 bytes.
- `src/aios_core/storage/sqlite_store.py:208-219`: current retry handler catches ValidationError, DurableJSONError and TypeError, not this conversion failure.
- `src/aios_core/storage/sqlite_store.py:476-492`: the new-write preflight has the same incomplete classification.

### Affected contracts

- M0-002 structured protocol / machine-readable branching.
- M0-016 and B1/B6/B7: a materially different or invalid existing-key retry must conflict without mutation; returning a raw decoder exception is not the frozen conflict protocol.
- Current B11 repair review explicitly defines unsafe durable JSON new writes as INVALID_ARGUMENT and invalid existing-key retries as IDEMPOTENCY_CONFLICT. Non-string Mapping keys are not the only unsafe JSON inputs.

This is NOT B9: it is not a SQLite error and must not be classified as storage_busy or STORAGE_FAILURE merely because serialization occurs inside commit. A caller input encoding failure must remain distinguishable from storage infrastructure failure.

### Why existing tests miss it

B8 uses UTF-8-safe strings and containers; B11 covers Mapping key collisions and catches its own new DurableJSONError. Existing tests do not force the shared Pydantic serialization fallback to fail using otherwise accepted Any payload data, especially during existing-key replay. Rollback success alone is insufficient behavior proof.

### Minimum repair boundary

Define the accepted durable scalar/encoding domain and consistently convert failures from the shared normalization/serialization boundary into the frozen new-write/retry protocol categories. Cover bytes, unsupported Any scalars and invalid Unicode separately; avoid a blanket exception swallow that misclassifies database faults. Preserve zero-write rollback and exact stale-replay priority. No production repair was made.

Keep **M0-002 / M0-016 / M0-017 / M0-022** open. A 3.12 rerun of the exact four probes is required before claiming closure or runtime-exact confirmation.

## 5. Mandatory common spot-check matrix

The new file contains **28 cases**. Original full formal suite was also run; where relevant it supplies existing exhaustive coverage, not a substitute for the new probes.

| Required surface | Evidence / outcome |
| --- | --- |
| 1. stale exact replay before expected-world | New replay control: commit world 1, advance world 2, restart store, retry expected=0: replay succeeds with no new revision |
| 2. same key/different request conflicts | New altered-arguments and concurrent-same-key controls pass for valid JSON; E-B13 shows invalid encoding escapes the error protocol |
| 3. cross-process hash stability | New nested frozenset of tuples + nested set in BOTH object and arguments; seeds 1,17,31337; results false/true/true replay flags |
| 4. failed assignment dirty OperationRequest | New reason=' ' after-validator failure, fresh key/current expected revision: INVALID_ARGUMENT and all counts unchanged |
| 5. busy/locked by result code | New real BEGIN contention checks base SQLITE_BUSY/LOCKED code; inspected masking of extended code in _connection; no claim of inducing every real LOCKED variant |
| 6. non-lock SQLite failure | Missing operations table -> STORAGE_FAILURE; RAISE(ABORT,'busy_locked_but_not_lock') in fault probes -> STORAGE_FAILURE, not retryable lock |
| 7. full transaction rollback | Five injected trigger locations: world_commits; second object insert; operations; idempotency_records; final world_meta update. All counters unchanged, fault removed, same request succeeds at world 1, next retry replays |
| 8. current/floating self-ref | Formal source_refs controls reject both; **E-B12 typed refs inside Any containers bypass both** |
| 9. X@2 -> X@1 | New canonical Observation historical SourceRef control succeeds |
| 10. EvidenceSet own cutoff | All five formal paths member/support/counter/context/selector.dimension_refs reject future target; **E-B12 metadata/filter typed paths bypass** |
| 11. same-tx mutual refs | New canonical Observation a@1 <-> b@1 succeeds; equal-cutoff same-tx evidence targets also succeed with +08:00 equivalent timestamp |
| 12. Dependency vs Relation cycles | New Relation A<->B succeeds, explicit Dependency A<->B fails with unchanged durable counts; existing Dependency regression suite also executed |
| 13. historical dual lens | New old-visible/new-invisible revision selection, world-only contrast, subject filter after latest-visible selection all pass |
| 14. Task/Event frozen state machine | Actual transition source unchanged candidate->HEAD; existing exhaustive test_state_machines_m021 suite executed in full baseline runs; no state-machine test failures |
| 15. snapshot is structural only | Existing snapshot passes while new E-B12/E-B13 fail. Independently inspected snapshot diff: cumulative pre-B6->9c080f changes only ErrorCode addition and ErrorResponse hash. The isolated 9c080f commit corrects a transient Observation hash typo, not a new model contract |

New concurrency probes additionally verify same-snapshot distinct writers produce one success + VERSION_CONFLICT and same-key distinct requests produce one success + IDEMPOTENCY_CONFLICT.

## 6. Scope discipline: not promoted to unsupported M0 blockers

- **Task/Event generic persistence bypass:** M0-021 final review explicitly says generic storage is not forced to understand domain transitions; later services must invoke validators. Taskbook M0-021 C/I likewise places enforcement in state-changing services. Helper-vs-generic-store distinction alone is not a new M0 blocker under this frozen scope. M1 Event service / M2 Task service must prove wiring.
- **EvidenceSet full world_revision materialization:** R2 §5.2/5.3 requires reconstructible frozen evidence; M0-009 provides schema/ref/cutoff constraints; taskbook M1-006 explicitly owns materialization and world snapshot freezing. No new unambiguous contradiction established here. Do not defer the already-frozen typed-ref cutoff, which is E-B12's issue.
- **recorded_at:** did not find a cited authority requiring it to equal physical commit time rather than controlled world/ingestion time; committed_at remains separate. Do not infer that arbitrary production callers may forge knowledge time at M1.
- **Worker isolation:** bounded trusted reviewed-code/module dependency rule accepted for M0, not a hostile Python sandbox proof. No attempted sandbox “escape” is reported as a new M0 defect.
- **Endpoint types and plain opaque pseudo-refs:** keep future validation Gate. E-B12 deliberately starts with actual typed refs and includes a passing opaque-dictionary negative control.
- **Historical world reads:** bare store single-lens queries remain a lower-level capability, not a Worker-safe “what AI knew then” interface.

No additional independent **RULING REQUIRED** is asserted in this report. Narrowing away recursive typed-ref semantics to dismiss E-B12 would itself require a new explicit Chief ruling.

## 7. Residual risks and future Gates

Current evidence limits, not implicitly tested:

- Supported CPython 3.12 reproduction and raw CI log verification remain outstanding due sandbox network/runtime constraints.
- Cross-process tests simulate successful durable commit with no retained in-process receipt by starting fresh processes; no actual process kill at SQLite commit boundary was injected.
- Not a complete file-permission/read-only disk/full-disk/real SQLITE_LOCKED/PRAGMA-stage contention campaign. Main track is E, not a complete C audit.
- No old pre-B6/pre-B8 database migration certification. Pre-B8 unordered values persisted as lists cannot generally be distinguished from semantically ordered input afterward; a release/import compatibility policy is still required before real persisted user data is supported.
- No claim that all accepted Python Any values are injective, strict JSON, or safe after restart. Nonfinite numbers/unsupported scalar serialization deserve additional bounded audit.
- No claim about arbitrary attacker-supplied Python model serializers, registry tampering, or hostile same-process execution; those are not needed for these findings.
- Current baseline's 24 failing tests need canonical fixture adaptation without losing their original behavior assertions, followed by exact-head full formal + Reference CI. Do not interpret the earlier 420-green as proof of current HEAD correctness.

Mandatory future Gates:

- **M1:** public double-lens query binding and resolved snapshot metadata; Worker capability wiring; endpoint-type validation; explicit opaque-vs-typed policy; controlled ingestion/provenance for learned_at/recorded_at; EvidenceSet materialization/coverage/roles/world freeze (M1-006); Event service transition validation; adversarial behavior coverage beyond schema snapshots; dependency/runtime reproducibility policy.
- **M2:** fixed Session snapshot + cutoff for all reads; Task transition wiring/recovery/scheduling; defined runtime status vocabulary; retry/stop/escalate decisions by code/reason including encoding-invalid input vs storage fault vs actual lock contention.
- **M3:** reverse index, correction/stale propagation, evidence-loop discipline, bounded re-review task propagation. Current exact-version Dependency cycle checks are not completion of these services.

## 8. Previously FINAL PASS contracts / recommendation

- **Do not close M0-022.** Requested candidate has behavioral false-green; observed HEAD also has a mechanically red CI.
- Continue/reopen as necessary **M0-002, M0-009, M0-016, M0-017, M0-019** for the described new boundary failures.
- Do not reopen **M0-020** or **M0-021** merely for already-deferred public service binding; their bounded controls passed.
- These new probes do not independently require reopening **M0-015** beyond the separately recorded B10 adjudication. New canonical Dependency cycle control passes. Do not represent that as full M3 proof-graph approval.
- Earlier individual architecture PASS reports cannot establish whole-candidate PASS in the face of these counterexamples. This audit neither overwrites nor claims authorship of them.

## 9. Reproduction and evidence inventory

Report-relative directory: `evidence/auditor-e-02/`.

- `test_auditor_e_02.py`: complete self-contained probes and controls.
- `probes-candidate.log`, `probes-head.log`, `probes-head-pydantic210.log`: exact failing assertions/tracebacks and summaries.
- `baseline.log`, `head-baseline.log`, `reference.log`: local regression evidence.
- `ci-red-metadata.json`, `ci-green-metadata.json`, `ci-head-metadata.json`: retrieved GitHub run/job/step metadata, NOT raw CI logs.
- `candidate-to-request-head.txt`, `candidate-to-observed-head.txt`, `environment.txt`, `SHA256SUMS`.

Reproduce without modifying production:

```bash
# Run from a read-only extracted exact tree, with an appropriate existing venv.
# Prefer the required Python 3.12 runtime for closure verification.
export PYTHONPATH=/absolute/path/to/extracted-exact-SHA/src
python -m pytest -q -o addopts='' /absolute/path/to/test_auditor_e_02.py
# Current observed output on the documented local environments:
# 11 failed, 17 passed
```

Tests use temporary databases, no network and no production store. Source snapshots and dependency environments are not included in the Git patch; fetch/archive the specified SHAs to reproduce. Only this uniquely named report and its evidence are submitted. No fixes were applied.

**This is an independent blocker report, not M0 FINAL PASS, M1 START, or authorization for parallel core development. Final disposition belongs exclusively to chief-01.**
