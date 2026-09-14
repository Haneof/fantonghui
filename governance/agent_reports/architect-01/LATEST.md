BLOCKER FOUND

# architect-01 — M0 Gate independent architecture red-team

- agent_id: `architect-01`
- role: Principal Architect / Red Team
- task: M0 GATE INDEPENDENT ARCHITECTURE RED-TEAM
- status: `BLOCKER FOUND`
- production branch audited: `arena/01a09bc6-fantonghui`
- frozen semantic base: `8818dba83d97f73e3e48df97df9a18e3c450ba9d`
- Chief Gate candidate: `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- production branch documentation head observed: `1ea11a11197d4a5d61659e0f6254aef1f5f46581`
- governance branch base observed: `41b5a65ea122a1c10d9a553ed9eccd2a70a1925e`
- report date: 2026-09-14

## 1. Verdict

M0 should not pass at the current candidate. At least two independently reproducible foundational failures exist:

1. an idempotency key is accepted as an unconditional alias for a prior result even when the retry has a different operation identity, arguments, expected world revision, and object set;
2. the claimed AI Worker raw-SQLite isolation is an AST convention test, not an architectural capability boundary, and is bypassed by ordinary dynamic import or indirect access.

A third foundational concern is that the proof/dependency cycle guard is not connected to the durable write boundary. The current tests prove that a caller who remembers to invoke the helper can detect a supplied in-memory cycle; they do not prove that a proof cycle cannot be persisted.

The Gate fixtures and schema snapshot are green but do not falsify these paths. Final Gate authority remains with `chief-01`; this report does not declare M0 FINAL PASS.

## 2. Cloud evidence actually read

Read directly from GitHub clone/API, not supplied chat excerpts:

- `AGENTS.md`
- `governance/CONTROL_PANEL.md`
- `governance/CURRENT_STATE.md`
- `governance/ACTIVE_ASSIGNMENTS.md`
- `governance/ROLE_REGISTRY.md`
- `governance/MODEL_ROUTING_POLICY.md`
- `governance/MULTI_AGENT_POLICY.md`
- `governance/AGENT_REPORT_PROTOCOL.md`
- `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- `governance/agent_reports/architect-01/REQUEST.md`
- `TASK_PROGRESS_R2.md`
- `AIOS宪法2.0.txt`
- `AIOS宪法2.0及开发规格修改案_R1.md`
- `AIOS宪法2.0及开发规格修改案_R2.md`
- `AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
- all M0 `*_final_PASS_2026-09-14.md` reviews present at the production head and the associated M0 evidence inventory
- all current production modules under `src/aios_core`, the architecture tests, contract/unit tests, and the M0 Gate fixtures
- `schemas/r2/m0_contract_snapshot.json`
- `tests/unit/contracts/test_m0_schema_snapshot.py`
- `tests/integration/test_m0_gate_fixtures.py`
- `reviews/M0/M0-022_chief_gate_ready_2026-09-14.md`
- `reviews/M0/evidence/M0_022_GATE_PACKET.md`
- Git history/diff from `8818dba...` through candidate `95cec414...`, plus later review/evidence-only production commits through `1ea11a1...`
- GitHub Actions run `34814629456`, job `103882644741`, including raw log
- GitHub Actions bootstrap run `34814547088`, job `103882399817`, including raw log

Note: the two M0-022 review/evidence files are later production-branch documentation commits (`f7f9071...`, `d4a6e55...`) and are not present in candidate `95cec414...` itself. That is acceptable as evidence-location chronology, but they must not be represented as files contained in the candidate tree.

## 3. Mechanical verification

- Candidate checkout: exact detached `95cec4142bdd9a87011bbad197e05ec1d27aeb57`.
- Local Python 3.12 / pytest 8.4.2 run: `391 passed`, with the one known Pydantic serializer warning in `test_e23_time_range_mutation`.
- Cloud green CI: exact candidate SHA; job conclusion `success`; formal suite collected and passed 391 tests; Reference step passed 15 tests; CPython 3.12.14.
- Bootstrap CI: job conclusion `failure`; formal result was exactly `390 passed / 1 failed / 1 warning`; the failure was `test_m0_schema_snapshot_matches_frozen_contract`, where expected `{}` differed from the emitted generated snapshot. The four Gate fixtures passed before that failure. The Reference step was skipped because pytest failed.

### Bootstrap finding

The team's narrow explanation is supported by the raw log and commit sequence (`189f874...` test, `0ab566c...` empty seed, `6f08930...` fixtures, `95cec414...` generated snapshot). I found no evidence that bootstrap run `34814547088` hid another failing invariant. It is benign only as a one-time capture mechanism; it is not evidence that the captured schema is semantically complete.

## 4. Reproducible blockers

### B1 — altered request with reused idempotency key is silently accepted

- Severity: Critical / M0 Gate blocker
- Frozen contract to reopen: M0-016 (`cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3`), with storage behavior inherited by M0-017/M0-018 and candidate `95cec414...`
- Affected files: `src/aios_core/storage/sqlite_store.py`, `src/aios_core/contracts/operations.py`, `tests/unit/test_operations.py`

Minimal counterexample:

1. Commit object `o@1` with `operation_id=op1`, `idempotency_key=K`, arguments `{value: ORIGINAL}`, expected world revision 0.
2. Submit a different object `evil@1` with `operation_id=op2`, the same key `K`, arguments `{value: ALTERED}`, and even expected world revision 999.
3. `SQLiteWorldStore.commit()` executes `_get_idempotent_result()` before comparing any request fingerprint and returns the result for `op1` with `idempotent_replay=True`.
4. No `IDEMPOTENCY_CONFLICT` is raised; the returned operation ID is `op1`, and the second caller receives a success-shaped result for a request that was never executed.

Observed output:

`IDEMPOTENCY_ALTERED_REPLAY {'operation_id': 'op1', 'world_revision': 1, 'object_refs': [('o', 1)], 'idempotent_replay': True}; evil_exists=False`

Mechanism: `idempotency_records` stores only key → prior result/operation, while replay does not compare canonical operation name, arguments, object payload/object refs, session, or operation identity. The existing tests retry the exact same request only. The presence of `ErrorCode.IDEMPOTENCY_CONFLICT` does not make this path safe because the store never emits it here.

Why it breaks M1–M8: network retry bugs, key reuse, crash recovery, or an altered action/write can be acknowledged as the wrong prior operation. A Worker may checkpoint false success, omit intended world changes, or associate the wrong external action with a durable result. This destroys trustworthy replay and audit semantics.

Minimum repair boundary:

- define and freeze the canonical idempotency request fingerprint (at minimum operation name, normalized arguments, intended object IDs/revisions and canonical serialized payloads; decide explicitly whether operation_id/session/reason/expected revision participate);
- persist that fingerprint atomically with the idempotency record;
- exact match returns the prior result before stale-world checking;
- same key plus non-matching fingerprint returns `IDEMPOTENCY_CONFLICT` without mutation;
- add restart, concurrent-writer, crash/replay, and altered-object/request tests.

### B2 — AI Worker raw SQLite isolation is not an enforceable architecture boundary

- Severity: High / foundational isolation blocker
- Frozen contract to reopen: M0-001 and the isolation claim repeated in M0-017 (`c9bd2d85ff0047515f6f4cc5b9e7058c70cff6dc`)
- Affected files: `tests/architecture/test_boundaries.py`, `tests/architecture/test_scanner_regression.py`, package/runtime topology under `src/ai_worker` and `src/aios_core/storage`

Minimal counterexamples that the scanner reports as legal:

- `__import__('sqlite3').connect(path)`
- `import importlib; importlib.import_module('aios_core.storage').SQLiteWorldStore(path)`
- a helper module outside `src/ai_worker` imports storage and hands the Worker a store/connection
- dependency injection passes a `sqlite3.Connection` or `SQLiteWorldStore` object into Worker code

The scanner visits only static `ast.Import` and `ast.ImportFrom` nodes in `src/ai_worker`. The packages execute in the same Python process/environment; `aios_core.storage` publicly exports `SQLiteWorldStore`; there is no process boundary, capability-limited interface, restricted import environment, or runtime authorization check.

Why it breaks M1–M8: once Worker code becomes non-empty, accidental or agent-generated indirect access can bypass Core query/write policy, snapshot enforcement, reference validation, hidden-truth separation assumptions, and audit/idempotency. Tests currently prove only that prohibited literal import statements are absent.

Minimum repair boundary: Chief must choose and freeze whether this is (A) a trusted-code lint convention, in which case governance/reviews must stop claiming “cannot obtain raw connection”, or (B) a real capability boundary, in which case Worker must run behind a narrow Core API/process boundary and never receive DB paths/connections/storage objects. Add adversarial dynamic-import, alias/helper, and dependency-injection tests appropriate to the chosen threat model.

### B3 — proof cycles can be durably persisted without invoking the cycle guard

- Severity: High
- Frozen contract to reopen or explicitly narrow: M0-015 (`3b4e8b603e52830d8be44d33141f722bbba244a0`)
- Affected files: `src/aios_core/dependency/graph.py`, `src/aios_core/storage/sqlite_store.py`, future dependency service boundary, `tests/unit/test_dependency.py`

The cycle helper correctly detects a supplied collection such as `A@1 -> B@1 -> C@1 -> A@1`. However, `SQLiteWorldStore.commit()` validates each `Dependency` structurally and validates endpoint existence, but never loads the existing dependency graph or invokes `validate_dependency_graph_acyclic`. No current dependency service enforces it. Therefore a caller can persist the edges over one or more commits, and nothing marks the graph invalid.

This contradicts the final review's broad wording that multi-node proof cycles are “detected and rejected” and the taskbook acceptance that constructed evidence cycles are rejected or flagged. The tests only call the helper directly.

Why it breaks M1–M8: correction propagation and confidence/provenance traversal can enter self-supporting loops; an AI inference can indirectly become evidence for itself; reverse impact traversal may avoid infinite loops using `visited`, but that does not make the proof epistemically valid.

Minimum repair boundary: define the single authorized `dependency.create` persistence boundary, check the union of durable exact-version edges and pending edges atomically, reject/flag cycles there, and prohibit generic callers from persisting Dependency outside that boundary. Test cycles split across commits, same-transaction cycles, concurrent stale writers, and exact-revision correction chains.

## 5. Mandatory attack areas

1. **Canonical timeline:** aware datetime validation, instant comparison via UTC, IANA Task timezone validation, and fixed-shape UTC index values are sound for covered cases. `occurred`, `learned_at`, and `recorded_at` are distinct. Residual: stored payload retains original offsets while indexed columns are UTC; consumers must compare instants, not payload strings.
2. **Knowledge Cutoff:** store selection correctly intersects `learned_at <= cutoff` with optional world revision and chooses the newest visible object revision. No direct future-payload leak was reproduced when both constraints are used. Residual: cutoff alone is not a session snapshot; backfilled objects with old `learned_at` become visible to a later retrospective query. Session consumers must always pin world revision.
3. **Object vs world revision:** separated and transactionally enforced; object revision is `+1`, one commit advances one world revision, rollback/concurrent stale writers are covered. Same object cannot currently contribute multiple sequential revisions in one commit; this is acceptable unless a later bulk-import contract requires it.
4. **Pinned/floating refs:** evidence/provenance paths are mostly pinned; floating refs intentionally remain for identity/navigation. Same-transaction existence and learned-time visibility work. Residual: `KnowledgeWindow.world_revision` is not cross-checked against referenced objects or the resulting transaction revision; same-transaction EvidenceSet fixtures use window revision 0 while citing an object that becomes visible at revision 1. This needs an explicit Chief ruling before relying on that field for reproducible evidence snapshots.
5. **Persistence mutation:** generic Pydantic graph revalidation blocks tested post-construction mutations. Plain `metadata`/arbitrary dictionaries are intentionally opaque and are not reference contracts. The durable boundary is effective for declared model refs.
6. **Claim epistemics:** `claim_type` and `knowledge_state` are distinct; claimant and subject are distinct; FACT does not mechanically imply truth/confidence. Core intentionally performs structural, not semantic truth judgment. Fixture coverage is narrow and does not prevent a caller from constructing semantically bad FACT claims; later services/evaluators must enforce policy.
7. **EvidenceSet:** fixed cutoff, pinned lists, selector time extent, roles, coverage, stale field, and mutation defense exist. Risks: role lists need not be subsets/partitions of `member_refs`; coverage fields have no internal arithmetic consistency rule; selector reproducibility depends on future materialization service; `knowledge_window.world_revision` inconsistency noted above.
8. **Entity identity:** stable object ID survives canonical name/alias revision; canonical name is not a key. Identity claims are pinned. Merge/split/entity-resolution service semantics remain deferred, so long-term deduplication correctness is not yet proved.
9. **Relation/Event/DimensionDerivation/Goal replay:** pinned provenance is strong where validators require it; Relation endpoints and Event participants intentionally float for entity navigation. Event revisions preserve explicit history fields. Goal status/progress proof and several generic related refs depend on later services/Dependency records.
10. **Dependency:** exact-version reverse scan and in-memory cycle detection work; persistent reverse index/correction propagation are correctly deferred. Durable anti-cycle enforcement is missing (B3).
11. **Goal != Task:** separate object types/lifecycles are frozen; the fixture proves Task completion does not mutate Goal in the generic store. It does not prove future goal assessment services will require success criteria/evidence.
12. **Task/Wake/Session/Action/Outcome:** separate contracts exist; Wake is not Observation; Action and Outcome are distinct; no automatic message-delivery=help-success rule exists. `Outcome.outcome_state` is an open string, so `UNKNOWN` can be represented but not canonically constrained. Full runtime semantics are deferred.
13. **execution_id/OperationRequest/idempotency:** `execution_id` is a stable field but uniqueness/external side-effect recovery is deferred. OperationRequest audit and stale-writer checks work. Altered-request idempotency fails critically (B1).
14. **SQLite atomicity:** `BEGIN IMMEDIATE`, one global revision per multi-object commit, validations-before-inserts, rollback, stale writer, restart, WAL, and foreign keys were verified. Simulated process kill at every SQLite instruction was not performed; SQLite transaction guarantees are relied upon.
15. **Session snapshot isolation:** the historical query facade can pin a supplied revision, but `Session.snapshot_world_revision` is data only. Nothing automatically binds all reads during a Session to it. The M2 workspace/session executor is explicitly deferred; it must be a Gate before Worker reads become real.
16. **Worker DB isolation:** failed as a real architectural constraint (B2). Current evidence is only static lint plus an empty Worker package.
17. **Task/Event state machines:** transition matrices and revision helpers are correct and exhaustive. Generic store accepts a direct `COMPLETED@1 -> RUNNING@2` write if the caller skips the helper; reproduced output was `TERMINAL_RESURRECTION_PERSISTED running`. M0-021 review explicitly calls storage enforcement a non-goal and requires later state-changing Core services to invoke validators. This is therefore a mandatory future service Gate, not an additional undisclosed M0-021 blocker.
18. **Schema snapshot:** useful for Pydantic JSON-schema shape, enum values, and explicit Task/Event maps. It cannot detect validator-body, query, persistence, dependency-graph, permission-boundary, normalization, or idempotency semantic changes. Removing `EvidenceSet` cutoff validation or changing `SQLiteWorldStore.commit()` behavior leaves the snapshot unchanged. The broad-coverage test counts models/enums but does not bind behavioral contracts. Treat it as structural drift detection only.
19. **Four fixtures:** all four pass, but each is a narrow demonstrator. Sports-day manually calls the validator and omits evidence/provenance; unknown-person proves nullable name round-trip but not later identity resolution; future-prediction proves one well-formed prediction but not prevention of semantic promotion; Goal/Task proves no generic-store side effect but not future service behavior.
20. **Authority documents:** R2/taskbook and frozen code are broadly aligned on the inspected M0 structures. Two scope/wording conflicts require Chief clarification: (a) M0-001/M0-017 say Worker cannot obtain raw SQLite while implementation provides only lint; (b) M0-015 review says cycles are rejected while implementation only offers an optional helper. `TASK_PROGRESS_R2.md` differs between the production candidate lineage and governance current-state summary due to historical progress commits; governance is clearly intended as the current control plane, but progress documents should be reconciled after the Gate.

## 6. Gate fixture evaluation

| Fixture | What it proves | What it does not prove |
|---|---|---|
| sports-day | two Event revisions can be stored and read by world revision | evidence-backed event creation, automatic transition enforcement, revise/reject/merge/split provenance |
| unknown-person | nullable canonical name, alias, empty identity refs persist | stable identity resolution, collision/merge handling, later pinned identity claim behavior |
| future-prediction | one prediction remains typed prediction after round-trip | semantic prevention of future FACT creation or high-confidence promotion |
| Goal/Task | completing a Task does not automatically mutate an already stored Goal | goal assessment service cannot equate task completion with achieved criteria |

They satisfy the taskbook's requirement to reproduce four fixtures, but they are not proofs of the full named invariants.

## 7. Schema snapshot evaluation

The bootstrap capture is authentic and the stored snapshot matches the generated candidate shape. The design nevertheless has a large false-green class:

- Pydantic `model_validator` body changes do not necessarily change JSON Schema.
- `as_utc`, reference visibility, historical selection, transaction order, idempotency logic, dependency cycle logic, architecture scanner logic, and state-transition helper implementation are outside the model hashes.
- Only Task/Event transition outputs are separately captured; other behavioral tables/policies are not.
- The snapshot can also be updated together with an unauthorized contract change and will turn green; governance/code review, not the hash, is the approval boundary.

Recommendation: retain this snapshot, rename its claim to **structural contract snapshot**, and add behavior canaries/fingerprints for the few foundational semantics intended to be mechanically frozen. Do not hash source blindly as a substitute for tests; add falsifying tests for each invariant.

## 8. Residual risks (not all are M0 blockers)

- `KnowledgeWindow.world_revision` semantics for same-transaction evidence are ambiguous and unenforced.
- EvidenceSet role membership and coverage arithmetic consistency are not enforced.
- open-string statuses (`WorldObject.status`, `Outcome.outcome_state`, `Session.session_state`) permit vocabulary drift until service contracts freeze them.
- `operation_id` collision with a different idempotency key surfaces a raw SQLite integrity error rather than a protocol error.
- no explicit DB schema version/migration framework exists yet; long-term replay across schema evolution is unproved.
- query coverage is only a returned-object count, intentionally not completeness.
- entity merge/split and identity collision policy are deferred.
- generic storage cannot enforce domain transition policy; future services are trusted until a single write capability is enforced.
- persistence revalidation emits an expected serializer warning for deliberately corrupted nested state; warning behavior may change across Pydantic versions.

## 9. Deliberately deferred beyond M0

Not treated as defects merely for being absent:

- M1 world services, search, drill-down, selector materialization, entity resolution, event expansion, and authorized dependency service;
- M2 scheduler, Wake runtime, Session executor/checkpoint recovery, action/outcome external side-effect engine, execution_id uniqueness and retry reconciliation;
- M3 persistent reverse dependency index, correction propagation, stale/rebuild workflows, multi-scale summary recomputation;
- full schema migration machinery, distributed coordination, and long-duration replay/performance work in later milestones.

These deferrals remain safe only if M1/M2 services cannot bypass the Core persistence/query capability boundaries.

## 10. Required next action for chief-01

1. Do not sign M0-022 or authorize M1.
2. Reopen M0-016 and implement/freeze altered-request idempotency conflict semantics with a canonical persisted fingerprint.
3. Issue an architectural ruling on Worker isolation threat model: honest lint convention versus real process/capability boundary. Align code, tests, and governance wording.
4. Reopen or explicitly narrow M0-015: make proof-cycle rejection durable at the authorized dependency write boundary, or state that M0 only supplies a helper and add an M1 blocker before any Dependency writes.
5. Rule on `KnowledgeWindow.world_revision` for same-transaction EvidenceSets and add consistency tests.
6. Add the red-team counterexamples to the formal suite, rerun exact-head Python 3.12 CI and Reference suite, then request a new independent architecture Gate on the patched exact commit.

## 11. Scope integrity

No production code, frozen schema, tests, reviews, or task history were modified by architect-01. Only this authorized report file is added/updated on the governance branch.
