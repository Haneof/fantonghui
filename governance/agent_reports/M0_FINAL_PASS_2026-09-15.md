# AIOS Core M0 — FINAL PASS

**Gate authority:** Chief Engineer / Integrator  
**Date:** 2026-09-15  
**Verdict:** `M0 FINAL PASS`  
**Next milestone:** M1 may begin after this governance record is committed.

## 1. Production pin

Active production branch:

`arena/01a09bc6-fantonghui`

Final M0 production HEAD:

`f2107656d404bb9cac526f71175cbfc1fbbb91cb`

Promotion was performed as a non-force fast-forward from the previously observed production HEAD:

`8dd96ab767c6d359728da2d64a49e47642c93b31`

Immediately before promotion the production branch was re-read and still matched the expected base. Immediately after promotion the branch was re-read and matched the final SHA above.

## 2. Production exact-head CI — authoritative Gate evidence

GitHub Actions run:

`34872128566`

Job:

`104070337643`

Environment:

- CPython `3.12.14`
- Pydantic `2.13.5`
- pytest `8.4.2`

Results on the exact production HEAD:

- formal repository suite: **558 passed / 0 failed**
- Reference suite: **15 passed / 0 failed**
- workflow conclusion: **SUCCESS**

Candidate CI was not substituted for this result; this run was created only after the active production ref had advanced to the final SHA.

## 3. Independent frozen review convergence

Before production promotion, the exact repair source was verified against two previously frozen independent suites without changing their test-file contents.

Verification branch:

`arena/verify-f210-frozen488-20260915`

Verification commit:

`efba7754c94bf7afbdcc09c142009ee96570eefe`

GitHub Actions:

- run `34871739186`
- job `104069033003`
- CPython `3.12.14`
- Pydantic `2.13.5`
- pytest `8.4.2`

Frozen evidence:

1. 394-case suite
   - Git blob: `705aba3f28694347e6d7750f4dc6be7bfed6af8b`
   - original SHA-256: `180dc1bac647e6cee6688dd4475dab8a063cc9fa9545acdc0e907036e9bea97d`
2. independent 94-case suite
   - Git blob: `f165291bd592fc1c767bbe872728f6b1c893cf3e`
   - original SHA-256: `d2c09a428f0f53d49b0ed21af6fd2e9bcdf7b62cef502330081c84e1a8d08042`

Combined result:

- **1046 collected** = current formal 558 + frozen 394 + frozen independent 94
- **1046 passed / 0 failed**
- Reference: **15 passed / 0 failed**

The verification commit added only the unchanged frozen test blobs and test-environment glue; product source was the same as the repair candidate subsequently promoted to production.

## 4. Final blocker sequence and closure

M0 was deliberately kept open through multiple green-but-insufficient candidates. Evidence quality, not reviewer vote count, controlled the Gate.

The final sequence included closure and regression coverage for historical B1–B13 and later cross-cutting findings, including:

- canonical object-type/schema dispatch;
- recursive non-string Mapping key rejection and collision prevention;
- actual `ObjectRef` / `SourceRef` preservation under `Any`;
- durable serialization/protocol error normalization;
- semantic idempotency identity for typed refs versus opaque dictionaries;
- dirty Pydantic instance revalidation and extra-field preservation/rejection;
- legacy idempotency ambiguity fail-closed behavior;
- durable-normal-form replay for unordered containers;
- dataclass-contained actual typed-reference preservation into M0-019 reference validation;
- datetime and SQLite integer boundary classification;
- fail-closed `STORAGE_FAILURE` mapping for corrupt durable JSON/world-revision/idempotency state;
- transaction atomicity and no-partial-write guarantees on rejected paths.

The last Chief-only re-falsification of predecessor `b9b5921c3e31a40528b0b96e689ae721c334bd7c` produced X8/X9/X10 and therefore rejected that predecessor despite earlier green suites.

Chief probe commit:

`125ff791c8bbdd0ac72343070789d0dece968eeb`

Chief adjudication/report commit:

`f3e2fcfd538a49ca4578ed80f903b66e9e5559b9`

The unchanged Chief regression file contributes 14 tests to the final 558-test production suite and is green at the final production HEAD.

## 5. Candidate history disposition

The following are historical/intermediate candidates and must not be treated as production Gate authority:

- PR #4 / `524f4d99...` — rejected by later blocker evidence.
- PR #5 / `b6588bda...` — rejected by frozen X5/X6/X7 evidence.
- PR #6 / `b9b5921c...` — superseded after Chief X8/X9/X10 reproduction.
- PR #7 / `f2107656...` — unified promotion record; production was advanced by non-force fast-forward to this exact SHA.

Only the active production branch plus the production exact-head CI in section 2 is authoritative for final M0 status.

## 6. Evidence-retention note

An older 100-probe suite against `524f4d99...` was not retained and could not be recovered. It is not represented as replayed evidence and no reconstructed suite is labelled as the original.

The Gate compensated transparently by requiring newly frozen, persisted independent suites with stable hashes and by replaying the retained 394-case and 94-case suites unchanged against the final repair source.

This is recorded as an audit-evidence retention lesson, not hidden or rewritten as a successful original replay.

## 7. Toolchain note

The canonical M0 Gate environment is the environment recorded above with Pydantic `2.13.5`.

A prior compatibility check on Pydantic `2.10.6` showed a pre-existing raw `model_json_schema()` snapshot hash difference on both the old baseline and repaired candidates while behavioral storage/idempotency tests remained green. The frozen schema snapshot was not weakened or rewritten merely to make 2.10.6 green.

Any future change to cross-version schema-hash normalization must be a separate governance decision; it does not alter this exact M0 Gate pin.

## 8. Gate decision

All required M0 conditions are now satisfied on the active production revision:

- frozen contracts and core storage behavior are implemented;
- historical blockers have retained regression coverage;
- newly discovered cross-cutting blockers have been independently reproduced, repaired, and replayed;
- independent frozen suites converge green on the promoted source;
- active production exact-head formal and Reference suites are green;
- no unresolved concrete M0 blocker remains in the evidence set used for this Gate.

Therefore:

`M0 FINAL PASS`

The previous M1 freeze is lifted by this record. M1 work may begin from the pinned production baseline `f2107656d404bb9cac526f71175cbfc1fbbb91cb`.
