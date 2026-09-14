# architect-01 — M0 Gate interrupted third review continuation

Status: **AUTHORIZED / REQUIRED / WAITING FOR ARCHITECT CAPACITY**

This supplements and supersedes the candidate references in `REREVIEW_REQUEST.md` after the third GPT-6 Work session was interrupted by quota exhaustion before it could update `LATEST.md`.

## 1. Important provenance rule

Do **not** treat the current `LATEST.md` as the result of the interrupted third review. It is still the prior formal report for candidate `268d403...`.

During the interrupted review, the architect visibly identified two additional concerns before quota exhaustion:

- B8: cross-process collection serialization can make the same logical idempotent request unreplayable;
- B9: string matching on the word `busy` can misclassify a non-lock SQLite OperationalError as retryable contention.

Chief independently reproduced both in committed tests before patching. This file does not impersonate or reconstruct a missing GPT-6 verdict.

## 2. Red-before-green evidence

Pre-fix reproducer commit:
`83a23302ff3c88a409db988059c03e5ec27a7ace`

CI:
- run `34831346707`
- job `103935164027`
- formal result: **418 passed / 2 failed / 1 warning**

The two deliberate failures were exactly:

1. `test_b8_cross_process_unordered_collection_exact_replay_is_stable`
   - second Python process, different `PYTHONHASHSEED`
   - same logical request / same idempotency key
   - observed `IDEMPOTENCY_CONFLICT / request_fingerprint_mismatch`

2. `test_b9_non_busy_operational_error_with_busy_word_is_not_retryable_lock`
   - query references a missing table named `busy_missing_internal_table`
   - ordinary SQLITE_ERROR text happens to contain `busy`
   - old substring classifier incorrectly emitted `VERSION_CONFLICT / storage_busy`

Reference suite was skipped because formal failed.

## 3. Chief repair

Semantic repair commit:
`659157b849a0dbaad241c3e316dcd98eb7c72df7`

B8 repair:
- deterministic durable JSON canonicalization shared by persistence and fingerprinting;
- list/tuple order remains semantic and preserved;
- set/frozenset are recursively normalized then sorted by canonical JSON;
- OperationRequest.arguments and WorldObject payload persistence now use the same canonical representation used by replay identity.

B9 repair:
- lock contention is classified from SQLite result codes, not message substrings;
- only base `SQLITE_BUSY` / `SQLITE_LOCKED` map to `VERSION_CONFLICT / storage_busy`;
- other OperationalError remains `STORAGE_FAILURE / sqlite_operational_error` (or storage_unavailable during connection establishment).

Chief repair review:
`reviews/M0/M0_gate_B8_B9_followup_2026-09-14.md`

## 4. Green evidence

Exact source-equivalent archive head tested:
`d180091c73be63bcce680748048ef731316f848b`

CI:
- run `34831608087`
- job `103935994524`
- CPython 3.12.14 / pytest 8.4.2
- formal: **420 passed, 1 known warning**
- Reference: **15 passed**
- SUCCESS

Both B8/B9 red reproducers are now green.

Subsequent production commits may contain only review/progress documentation. Architect must compare current production HEAD against semantic repair `659157b...` before starting and flag any non-documentation source change.

## 5. Required continuation attacks

Continue the unfinished third review. Re-run the existing `REREVIEW_REQUEST.md` scope for B6/B7/B5/R4 and M0 regression, then add:

### B8

Attack deterministic replay across process boundaries with:
- multiple `PYTHONHASHSEED` values;
- nested set/frozenset inside OperationRequest.arguments;
- nested set/frozenset inside WorldObject Any/dict payloads;
- sets containing JSON-normalizable compound values if supported;
- ordered list permutations must remain different requests;
- dict key ordering must remain equivalent;
- restart replay and crash/no-receipt retry;
- altered set membership must conflict;
- verify canonicalization does not collapse materially distinct ordered payloads.

Explicitly judge the M0 compatibility consequence: pre-B8 temporary databases that persisted unordered set-as-list representations may not be inferentially distinguishable from ordered lists. M0 has not shipped; determine whether no migration is acceptable or whether a compatibility rule is required before Gate.

### B9

Attack SQLite error classification with:
- SQLITE_BUSY;
- SQLITE_LOCKED and extended result codes;
- SQLITE_ERROR whose text contains `busy` or `locked` but base code is not BUSY/LOCKED;
- missing schema/table;
- malformed DB;
- connection unavailable;
- read-only/permission failures where reproducible.

Required invariant: retryable lock classification is based on SQLite result semantics, not arbitrary error text.

## 6. Deliverable

When capacity is available, update:
`governance/agent_reports/architect-01/LATEST.md`

First line exactly one of:
- `ARCHITECTURE PASS`
- `RULING REQUIRED`
- `BLOCKER FOUND`

The final report must explicitly say the previous Work session was interrupted and that B8/B9 were independently re-audited against the repaired candidate.

Do not modify production code. Do not declare M0 FINAL PASS. Final Gate authority remains with `chief-01`.
