# AIOS 2.0 — M0 Gate Parallel Independent Audit Request

Date: 2026-09-14
Status: **AUTHORIZED / READ-ONLY AUDIT PARALLELISM ENABLED / CORE DEVELOPMENT STILL BLOCKED**

This request authorizes multiple independent AI auditors to review the current M0 Gate candidate in parallel. It does **not** authorize parallel production development, code fixes, or M1 work.

## 1. Repository and candidate

Repository: `Haneof/fantonghui`

Production branch: `arena/01a09bc6-fantonghui`

Governance branch: `governance/aios-control-plane`

Current production HEAD observed by chief-01:
`5acef4a4f43895a0762462e1f30e4f923da979a0`

Latest semantic repair candidate to audit:
`659157b849a0dbaad241c3e316dcd98eb7c72df7`

Chief independently verified that `659157b... -> 5acef4a...` is ahead-only and changes only the B8/B9 review archive; no production semantic source changes are present after the semantic candidate.

Latest exact green source-equivalent CI evidence:
- run `34831608087`
- job `103935994524`
- checkout `d180091c73be63bcce680748048ef731316f848b`
- CPython 3.12.14 / pytest 8.4.2
- formal: **420 passed**, 1 known adversarial warning
- Reference: **15 passed**
- SUCCESS

Important red evidence immediately before repair:
- commit `83a23302ff3c88a409db988059c03e5ec27a7ace`
- run `34831346707`
- formal: **418 passed / 2 failed / 1 warning**
- failures reproduced B8 and B9 exactly

## 2. Audit history that must be treated as input, not truth

Prior independent findings include:
- B1 idempotency request aliasing
- B2 Worker isolation threat-model overclaim
- B3 durable Dependency cycle bypass
- B4 floating self-reference bypass
- B5 storage protocol / SQLite boundary defects
- B6 normalized-idempotency mismatch
- B7 dirty OperationRequest durable persistence
- R3 historical-query double-lens ruling
- R4 EvidenceSet frozen cutoff ruling
- B8 cross-process unordered-collection replay instability
- B9 SQLite busy classification by message substring

Relevant reports/reviews:
- `governance/agent_reports/architect-01/LATEST.md` (older formal report; third review was interrupted by quota and did not update it)
- `governance/agent_reports/architect-01/REREVIEW_REQUEST.md`
- `governance/agent_reports/architect-01/REREVIEW_CONTINUATION_B8_B9.md`
- `reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`
- `reviews/M0/M0_gate_followup_B4_B5_R3_2026-09-14.md`
- `reviews/M0/M0_gate_B6_B7_B5_R4_resolution_2026-09-14.md`
- `reviews/M0/M0_gate_B8_B9_followup_2026-09-14.md`

## 3. Common rules for every auditor

Each auditor is independent. Do not coordinate conclusions with other auditors and do not assume any other report is correct.

Required behavior:
- fetch and inspect the actual candidate, current HEAD, diffs, source, tests, CI and authoritative specs;
- actively falsify invariants with new adversarial examples, not only existing tests;
- do not modify production branch or production code;
- do not fix bugs you find;
- do not declare M0 FINAL PASS;
- report minimal reproductions and exact affected contracts/files;
- distinguish current M0 blockers from deliberately deferred M1/M2/M3 scope;
- if a finding depends on ambiguous Constitution/R1/R2/taskbook wording, classify it as `RULING REQUIRED`, not as a guessed implementation requirement.

Every report must begin with exactly one of:
- `ARCHITECTURE PASS`
- `RULING REQUIRED`
- `BLOCKER FOUND`

Every report must include:
- auditor ID and assigned track;
- exact candidate SHA audited;
- exact HEAD observed;
- candidate-to-HEAD comparison result;
- CI evidence independently checked;
- new tests/probes run;
- findings by severity;
- residual risks and future Gate assignments;
- whether any previously reopened/final contracts should change state.

Reports must be written only to the governance branch under a unique file:
`governance/agent_reports/m0-parallel-audits/<AUDITOR_ID>.md`

Never overwrite another auditor's file or `architect-01/LATEST.md`.

## 4. Mandatory shared attack surface

All auditors must at least spot-check these invariants even when their primary track is narrower:

- exact stale idempotent replay occurs before expected-world rejection;
- different request cannot reuse an existing idempotency key;
- cross-process replay does not depend on Python hash randomization;
- durable OperationRequest audit fields cannot bypass validation after failed assignment;
- storage busy classification relies on SQLite result codes, not message text;
- non-lock storage faults remain `STORAGE_FAILURE`;
- object revisions are append-only and one logical commit advances one world revision;
- failed transactions roll back objects/audit/idempotency/world revision atomically;
- current/floating self-reference is rejected but historical pinned self-reference remains legal;
- EvidenceSet typed refs respect its own frozen `knowledge_cutoff`;
- same-transaction legal mutual refs are not accidentally banned;
- Dependency cycles are rejected without banning Relation cycles;
- world-revision and knowledge-cutoff historical filters compose correctly;
- Task/Event frozen transition matrices remain unchanged;
- schema snapshot is treated only as structural evidence, not behavioral proof.

## 5. Parallel audit tracks

### Track A — Idempotency / Canonicalization / Replay

Primary targets:
- `src/aios_core/storage/idempotency.py`
- commit/replay path in `sqlite_store.py`
- OperationRequest durable serialization

Attack:
- unordered nested sets/frozensets at multiple depths;
- dict ordering and key-type edge cases compatible with accepted model types;
- tuples/lists where order must remain semantically meaningful;
- float/int/string coercions and datetime timezone-equivalent forms;
- restart across different `PYTHONHASHSEED` values;
- same-key concurrency;
- crash/no-receipt retry;
- old pre-B6/pre-B8 databases replayed by current code;
- canonicalization collisions where materially different inputs could normalize to the same durable request.

### Track B — Time / Evidence / References / Historical Visibility

Primary targets:
- EvidenceSet
- ObjectRef/SourceRef validation
- KnowledgeWindow
- historical query layer

Attack:
- EvidenceSet member/support/counter/context/selector refs at before/exactly-at/after cutoff;
- prior visible revision + later invisible revision;
- timezone-equivalent learned_at/cutoff;
- same-transaction EvidenceSet refs;
- floating/current/historical self-reference combinations;
- future-known leakage with single vs dual lens;
- mutable subject/type filters and historical resurrection;
- typed refs hidden in nested models vs opaque dict pseudo-refs;
- endpoint-type mismatch residual and whether authoritative text requires it in M0 or later.

### Track C — SQLite / Atomicity / Concurrency / Failure Classification

Primary targets:
- `_connection()`
- commit transaction
- WAL/busy timeout
- SQLite error mapping

Attack:
- real `SQLITE_BUSY` / `SQLITE_LOCKED` at PRAGMA, BEGIN, read and write stages;
- non-busy `OperationalError` messages containing words `busy` or `locked`;
- malformed DB, missing table, read-only DB, path-is-directory, unavailable path;
- trigger failures after first/middle/last insert;
- rollback after audit/world/object/idempotency partial progress attempts;
- concurrent writers from same snapshot;
- subsequent recovery after a transient fault;
- whether any `StoreError` is accidentally caught/reclassified;
- raw sqlite exception leakage from any public store method, not only commit.

### Track D — Contract / Constitution / Governance Consistency

Primary targets:
- Constitution + R1 + R2 + authoritative taskbook
- M0-002/009/016/017/019/020/022 reviews
- governance rulings

Determine whether the current implementation/rulings actually match authoritative text for:
- trusted reviewed-code Worker isolation vs sandbox claims;
- `STORAGE_FAILURE` protocol category;
- EvidenceSet cutoff vs world_revision deferral to M1-006;
- `recorded_at` vs physical `committed_at` semantics;
- M0/M1 split for endpoint-type validation, selector materialization, double-lens public query;
- M2 Session snapshot+cutoff binding;
- M3 reverse-index/correction propagation.

Do not invent stricter scope than the authoritative documents require.

### Track E — Cross-cutting Integration / Unknown-Unknowns

Treat B1-B9 as already-known classes and search specifically for B10+.

Attack interactions, not isolated functions:
- idempotency + mutation + reference validation;
- idempotency + storage failure + rollback + retry;
- dependency validation + object revisions + same-transaction references;
- EvidenceSet cutoff + historical revision selection;
- state-machine helpers vs generic persistence bypass;
- object_type identity immutability under normalization;
- same stable ID across revisions with mutable subject_id;
- error-code ambiguity that could cause future retry engines to retry permanent failures or stop on transient failures;
- cross-process/restart behavior not represented by same-process unit tests;
- schema snapshot false-green scenarios;
- any route where a frozen invariant exists only in a helper and can be bypassed by the durable store or future public service.

## 6. Verdict discipline

Use `BLOCKER FOUND` only for a reproducible current M0 defect that violates a frozen M0 invariant or makes the Gate mechanically unsafe.

Use `RULING REQUIRED` for a genuine conflict/ambiguity among Constitution/R1/R2/taskbook/frozen reviews where implementation cannot be judged without chief architecture choice.

Use `ARCHITECTURE PASS` only if no current M0 blocker/ruling remains in the assigned scope after adversarial testing. PASS must still list residual M1/M2/M3 Gates.

The final M0 Gate decision remains exclusively with `chief-01`; no individual parallel auditor can authorize M1 or parallel core development.
