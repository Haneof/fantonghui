# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- Status: THIRD PATCH VERIFIED / WAITING ARCHITECT RE-REVIEW
- Task: M0-022 Gate blocker resolution
- Production branch: `arena/01a09bc6-fantonghui`
- Original Gate candidate: `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- Latest architect blocker report: `c068fc1fa0de528ab17cbfc4a4c6f9112b3ae164`
- Latest semantic repair: `f38fdd2aa64e31b92c5353206a8aef62c9322087`
- Current exact green candidate: `9c080f693917c2c99bfbe6aa924e5f3cb54744a0`
- Exact CI: run `34827250470`, job `103922130589`, formal 418 passed + Reference 15, SUCCESS
- Review: `reviews/M0/M0_gate_B6_B7_B5_R4_resolution_2026-09-14.md`

Chief accepted/patched/ruled:
- B6 canonical normalized request identity;
- B7 durable OperationRequest revalidation;
- B5-a connection lifecycle error boundary;
- B5-b new `STORAGE_FAILURE` error category;
- R4 EvidenceSet typed refs must be visible at its own frozen knowledge cutoff;
- recorded_at = controlled AIOS/simulator recording time; physical DB durable time = `world_commits.committed_at`.

Current instruction: M0 remains blocked until architect-01 independently attacks the latest candidate. Do not authorize M1 or parallel core development.

## Assignment B — `core-01` 核心程序员 / 主程序员

- Agent ID: `core-01`
- Status: IDLE
- Task: NONE
- Production scope: NONE

## Assignment C — `architect-01` GPT-6 架构审计员 / GPT-6 首席架构师

- Agent ID: `architect-01`
- Status: AUTHORIZED / REQUIRED / READY FOR THIRD RE-REVIEW
- Task: M0 GATE THIRD PATCH INDEPENDENT RE-REVIEW
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Prior report: `governance/agent_reports/architect-01/LATEST.md` (`BLOCKER FOUND`)
- Updated request: `governance/agent_reports/architect-01/REREVIEW_REQUEST.md`
- Required result: replace/update `governance/agent_reports/architect-01/LATEST.md`
- Required verdict: `ARCHITECTURE PASS | RULING REQUIRED | BLOCKER FOUND`

Re-review must independently verify at least:
- B6 coercible nested mutations use the same canonical representation for persistence and replay identity; restart exact replay succeeds; altered request still conflicts;
- B7 failed assignment dirtying any OperationRequest identity/audit field cannot persist; stale exact replay ordering remains intact;
- B5 connect failure cannot leak raw sqlite error; internal storage/schema faults are `STORAGE_FAILURE`; busy/lock remains `VERSION_CONFLICT/storage_busy`; rollback/no-gap remains intact;
- R4 all EvidenceSet typed refs obey its own frozen `knowledge_cutoff`, while legal same-transaction cutoff-visible refs remain allowed and full world-revision materialization is not falsely claimed;
- M0-002 snapshot change is exactly the approved `STORAGE_FAILURE` addition and ErrorResponse schema consequence;
- B1/B2/B3/B4/R3 previously closed/rule-bounded behavior has not regressed;
- full M0 Gate fixtures, schema snapshot, atomicity, refs, historical query, state-machine tests remain green.

Do not modify production code. Report residual risks. Final Gate authority remains with chief-01.

## Assignment D — `parallel-01`

- Status: NOT AUTHORIZED
- Task: NONE

## Assignment E — `parallel-02`

- Status: NOT AUTHORIZED
- Task: NONE

## Operator handoff rule

When `architect-01` completes the re-review, the operator only needs to say `GPT-6架构审计员做完了`; chief-01 reads the cloud report and decides the Gate.
