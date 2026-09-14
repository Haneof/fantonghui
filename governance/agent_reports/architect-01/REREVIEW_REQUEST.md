# architect-01 — M0 Gate follow-up patch independent re-review request

Status: **AUTHORIZED / REQUIRED / READY TO START**

You are `architect-01`, the independent GPT-6-class Principal Architect / Red Team.

Two independent red-team lines now exist:

1. governance report commit `c6b0191797ab3ef06b4ee031003431a0d9527d48` — `BLOCKER FOUND` (B1/B2/B3)
2. arena branch `arena/01a09edf-fantonghui` report commit `42f19a3f39a1e4ac375ac315d6dcf8f487725830` — independently reconfirmed B1 and added B4/B5/R3 analysis

Chief has patched/ruled the combined findings. This re-review supersedes the older B1/B2/B3-only request.

## Review base

Repository: `Haneof/fantonghui`

Production branch: `arena/01a09bc6-fantonghui`

Original M0 Gate candidate:
`95cec4142bdd9a87011bbad197e05ec1d27aeb57`

B1/B3 semantic patch:
`8ab574c6b33b2238b468c812992a92ba56ab3f71`

B2 static-policy hardening:
`e06bc80e43ea26be2be726232158cb2719092f11`

B4/B5 semantic patch:
`a99326c5034118b3a497e3be0d53ac9466445467`

Current exact green candidate:
`268d403836b107a1969a9a5d8b85e4955baec9bf`

Production progress archive:
`83577317e96224f9cdb271a8a835a4e48f3aa78c`

Chief reviews:
- `reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`
- `reviews/M0/M0_gate_followup_B4_B5_R3_2026-09-14.md`

Exact latest green CI:
- run `34823226166`
- job `103909332923`
- CPython 3.12.14
- formal **405 passed**, 1 known warning
- Reference **15 passed**
- SUCCESS

An immediately prior CI run `34822952167` was not hidden: 404 tests passed and one old M0-018 test failed only because B5 intentionally changed the public boundary from raw `sqlite3.IntegrityError` to `StoreError`. The five new B4/B5 probes were green in that run. The stale test expectation was then corrected, preserving rollback semantics.

## Required attacks

### B1 — idempotency

Falsify the rule that an idempotency key replays only an identical durable commit request.

Attack at least:
- changed operation_id;
- changed session_id;
- changed operation_name;
- changed arguments, including key-order equivalence;
- changed expected_world_revision;
- changed reason;
- changed object set;
- changed object revision;
- changed object payload;
- same objects in different input order;
- restart replay;
- concurrent same-key different requests;
- rollback/crash interaction using existing atomicity machinery.

Verify mismatch returns `IDEMPOTENCY_CONFLICT` before stale-world behavior and leaves world/object/operation/idempotency state unchanged.

Inspect whether reconstructing the stored fingerprint from durable `operations` + same-world `object_revisions` is actually equivalent to original request identity.

### B2 — Worker isolation threat model

Chief ruling:
- M0 is a modular monolith with trusted reviewed Python code;
- static scanner is architecture-policy defense-in-depth, not hostile-code sandbox proof;
- Worker production wiring must not receive DB path, sqlite connection, storage object, or raw store capability;
- Worker uses Core public interfaces;
- if future runtime executes untrusted Python, a real process/capability boundary becomes mandatory.

Audit this wording against Constitution/R1/R2/taskbook. Verify no review/test still claims hostile Python cannot bypass same-process imports.

The scanner must catch at least the known counterexamples:
- `__import__('sqlite3')`
- `importlib.import_module('aios_core.storage')`

Do not treat passing static tests as sandbox proof.

### B3 — durable Dependency cycles

Try to persist:
- same-transaction 2-edge cycle;
- cycle completed across multiple commits;
- longer A->B->C->A;
- concurrent competing edge additions;
- revisions of existing Dependency objects that replace old current edges;
- exact-revision cycles.

Verify any commit containing Dependency objects checks the resulting current graph made from latest durable edges plus pending edges, and rejects a cycle before writes.

Verify ordinary Relation cycles remain legal and M3 persistent reverse index/correction propagation has not been accidentally pulled into M0.

### B4 — floating self-reference

Attack all declared ObjectRef/SourceRef paths with same stable object id and `revision=None`.

At minimum reproduce the old counterexample:
- Claim X with a declared ref `ObjectRef(X, None)`

Also test SourceRef and a generic typed ObjectRef holder.

Expected result:
- `DEPENDENCY_INVALID`
- zero world mutation
- no pending-self fallback bypass.

Then verify pinned historical self-links remain legal:
- X@2 -> X@1 must still persist if X@1 exists and is knowledge-visible.

Check that the patch does not introduce an arbitrary ban on mutual references between distinct objects; M0-019 same-transaction mutual non-evidence refs remain legal.

### B5 — storage protocol boundary

Attack:
1. reused committed `operation_id` with a different idempotency key;
2. real SQLite lock/busy overlap;
3. forced mid-transaction SQLite integrity failure;
4. rollback after at least one object INSERT;
5. subsequent successful commit after failure.

Expected public behavior:
- reused operation id => `IDEMPOTENCY_CONFLICT`, no mutation;
- busy/lock => Core `StoreError` / `VERSION_CONFLICT` with machine-readable `reason=storage_busy`, not raw sqlite exception;
- SQLite integrity/operational implementation details do not escape as public Core protocol;
- atomic rollback and no world-revision gap remain intact.

Judge whether mapping non-lock SQLite integrity/operational errors to the chosen ErrorCode is acceptable for M0 or needs a narrower ruling. If it is unsafe, return RULING/BLOCKER with a minimal counterexample.

### R3 — historical read double-lens ruling

Chief ruling does **not** change M0-020 low-level store APIs. `as_of_world_revision` and `knowledge_cutoff` remain independently usable primitives.

But the following future Gate is now mandatory:

- M1 public query surface claiming to answer “what the AI knew then” must bind both resolved world snapshot revision and knowledge cutoff;
- M2 Session executor must bind all session reads to `Session.snapshot_world_revision` plus session knowledge-cutoff semantics;
- Worker must not be given raw store-read capability.

Audit whether this is consistent with the frozen M0-020 scope and whether it safely contains P6 future-known leakage without falsely claiming bare store reads are safe historical-AI views.

If this conflicts with Constitution/R1/R2/taskbook, return `RULING REQUIRED` and cite the competing texts.

## Regression Gate

Re-check enough of the original M0 Gate to catch regression:
- exact ancestry/diff of current candidate;
- full exact-head CI evidence;
- schema snapshot remains green, but explicitly treat it only as structural drift detection, not behavioral proof;
- four required Gate fixtures remain green;
- B1/B3/B4/B5 adversarial tests actually test the intended invariant;
- M0-009 persistence revalidation ordering remains safe;
- M0-018 atomicity/concurrency/revision guarantees remain intact;
- M0-019 legal same-transaction mutual refs and historical self-links remain intact;
- M0-020 dual-lens composition remains correct;
- Task/Event state-machine tests remain green.

## Residual-risk review

Do not ignore the second red-team residual list. Explicitly state whether each is:
- closed now;
- acceptable M0 residual with a named M1/M2/M3 Gate;
- ruling needed;
- blocker.

At minimum address:
- EvidenceSet member learned_at vs its knowledge_window cutoff;
- ref endpoint type validation;
- plain-dict pseudo-ref shapes not collected as refs;
- recorded_at ownership semantics;
- open-string status vocabularies;
- schema snapshot behavioral false-green class;
- dependency/reverse-index/correction propagation deferral;
- CI dependency version drift if still relevant.

## Deliverable

Update:
`governance/agent_reports/architect-01/LATEST.md`

First line exactly one of:
- `ARCHITECTURE PASS`
- `RULING REQUIRED`
- `BLOCKER FOUND`

If PASS, list residual risks and mandatory future Gates.
If RULING/BLOCKER, provide a minimal reproducible counterexample, affected files/commits/contracts, and smallest remediation boundary.

Do not modify production code. Do not declare M0 FINAL PASS. Final authority remains with `chief-01`.
