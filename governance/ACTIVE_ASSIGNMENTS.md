# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- Status: FOLLOW-UP PATCH VERIFIED / WAITING ARCHITECT RE-REVIEW
- Task: M0-022 Gate blocker resolution
- Production branch: `arena/01a09bc6-fantonghui`
- Original Gate candidate: `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- Original architect blocker report: `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- Additional independent red-team branch: `arena/01a09edf-fantonghui` @ `42f19a3f39a1e4ac375ac315d6dcf8f487725830`
- Current exact green candidate: `268d403836b107a1969a9a5d8b85e4955baec9bf`
- Production progress archive: `83577317e96224f9cdb271a8a835a4e48f3aa78c`
- Exact CI: run `34823226166`, job `103909332923`, formal 405 passed + Reference 15, SUCCESS
- Reviews:
  - `reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`
  - `reviews/M0/M0_gate_followup_B4_B5_R3_2026-09-14.md`

Chief accepted/patched/ruled:
- B1 idempotency altered-request aliasing;
- B2 Worker-isolation threat-model overclaim, with static-policy hardening and explicit trusted-reviewed-code ruling;
- B3 durable Dependency cycles;
- B4 floating current-self reference bypass;
- B5 raw SQLite exception / lock protocol leakage;
- R3 public historical-read service rule: "what AI knew then" requires world snapshot + knowledge cutoff, with Session binding deferred but mandatory at M2.

Current instruction: M0 remains blocked until architect-01 independently re-reviews the latest candidate. Do not authorize M1 or parallel core development.

## Assignment B — `core-01` 核心程序员 / 主程序员

- Agent ID: `core-01`
- Status: IDLE
- Task: NONE
- Production scope: NONE

## Assignment C — `architect-01` GPT-6 架构审计员 / GPT-6 首席架构师

- Agent ID: `architect-01`
- Status: AUTHORIZED / REQUIRED / READY FOR LATEST RE-REVIEW
- Task: M0 GATE FOLLOW-UP PATCH INDEPENDENT RE-REVIEW
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Prior report: `governance/agent_reports/architect-01/LATEST.md` (`BLOCKER FOUND`)
- Updated re-review request: `governance/agent_reports/architect-01/REREVIEW_REQUEST.md`
- Required result: replace/update `governance/agent_reports/architect-01/LATEST.md`
- Required verdict: `ARCHITECTURE PASS | RULING REQUIRED | BLOCKER FOUND`

Re-review must independently verify at least:
- B1 same-key changed operation/session/name/arguments/expected revision/reason/object set/revision/payload conflicts with zero mutation; exact retry still replays across restart and before stale expected-world checking;
- B2 Worker-isolation wording matches the trusted-reviewed modular-monolith threat model and scanner is not misrepresented as sandbox proof;
- B3 same-transaction, cross-commit and longer Dependency cycles cannot persist, while Relation cycles remain legal;
- B4 floating ObjectRef/SourceRef self-reference is rejected, while pinned prior-revision self-history remains legal;
- B5 reused operation_id/new key yields protocol conflict, real SQLite busy/lock maps to StoreError, rollback/atomicity remains intact and raw SQLite exceptions do not escape as public Core protocol;
- R3 ruling is consistent with M0-020 scope: low-level store may expose independent lenses, but M1 public "what AI knew then" queries and M2 Session execution must bind both world snapshot and knowledge cutoff semantics;
- schema snapshot and four Gate fixtures remain green;
- no new foundational regression was introduced.

Do not modify production code. Report residual risks. Final Gate authority remains with chief-01.

## Assignment D — `parallel-01`

- Status: NOT AUTHORIZED
- Task: NONE

## Assignment E — `parallel-02`

- Status: NOT AUTHORIZED
- Task: NONE

## Operator handoff rule

When `architect-01` completes the re-review, the operator only needs to say `GPT-6架构审计员做完了`; chief-01 reads the cloud report and decides the Gate.
