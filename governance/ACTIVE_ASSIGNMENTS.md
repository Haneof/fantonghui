# AIOS 2.0 Active Assignments

This is the cloud roster. AI agents must not self-assign production work.

## Assignment A — `chief-01` 总工程师 / 总工

- Agent ID: `chief-01`
- Status: PATCH VERIFIED / WAITING ARCHITECT RE-REVIEW
- Task: M0-022 Gate blocker resolution
- Production branch: `arena/01a09bc6-fantonghui`
- Original Gate candidate: `95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- Architect blocker report: `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- Current patch candidate: `8b3bca9ef3bf8fde2ee09b73a2631a3a2f12db0a`
- Exact patch CI: run `34821050459`, job `103902471146`, formal 400 passed + Reference 15, SUCCESS
- Review: `reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`

Chief accepted and patched:
- B1 idempotency altered-request aliasing;
- B3 durable Dependency cycles;
- B2 Worker-isolation threat-model overclaim, with static policy hardening and explicit trusted-code ruling.

Current instruction: M0 remains blocked until architect-01 independently re-reviews the patch. Do not authorize M1 or parallel core development.

## Assignment B — `core-01` 核心程序员 / 主程序员

- Agent ID: `core-01`
- Status: IDLE
- Task: NONE
- Production scope: NONE

## Assignment C — `architect-01` GPT-6 架构审计员 / GPT-6 首席架构师

- Agent ID: `architect-01`
- Status: AUTHORIZED / REQUIRED / READY FOR RE-REVIEW
- Task: M0 GATE BLOCKER PATCH INDEPENDENT RE-REVIEW
- Preferred model class: GPT-6-class
- Role prompt: `governance/roles/PRINCIPAL_ARCHITECT_RED_TEAM.md`
- Prior report: `governance/agent_reports/architect-01/LATEST.md` (`BLOCKER FOUND`)
- Re-review request: `governance/agent_reports/architect-01/REREVIEW_REQUEST.md`
- Required result: replace/update `governance/agent_reports/architect-01/LATEST.md`
- Required verdict: `ARCHITECTURE PASS | RULING REQUIRED | BLOCKER FOUND`

Re-review must independently verify at least:
- same key + changed operation/arguments/object payload now yields `IDEMPOTENCY_CONFLICT` with zero mutation;
- exact retry still replays before stale expected-world checking and survives restart;
- same-key different requests under concurrency cannot both succeed;
- same-transaction and cross-commit Dependency cycles cannot persist;
- Relation cycles remain legal and correction/reverse-index scope is not accidentally expanded;
- Worker isolation wording now matches the explicit trusted-reviewed-code threat model and tests do not claim sandbox security;
- original M0 Gate snapshot and four fixtures remain green;
- no new regression was introduced by the patch.

Do not modify production code. Report residual risks. Final Gate authority remains with chief-01.

## Assignment D — `parallel-01`

- Status: NOT AUTHORIZED
- Task: NONE

## Assignment E — `parallel-02`

- Status: NOT AUTHORIZED
- Task: NONE

## Operator handoff rule

When `architect-01` completes the re-review, the operator only needs to say `GPT-6架构审计员做完了`; chief-01 reads the cloud report and decides the Gate.
