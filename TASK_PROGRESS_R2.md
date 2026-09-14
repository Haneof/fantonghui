# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 (M0-022 CHIEF GATE READY / WAITING ARCHITECT)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS — 等待 GPT-6 架构 Gate | 21/22 FINAL PASS |
| M1 | 可写、可查、可下钻的共同世界 | 未开始 / M0 Gate 前禁止启动 | 0/16 |
| M2 | 主动运行闭环 | 未开始 | 0/15 |
| M3 | 长期纠错与多尺度认知 | 未开始 | 0/11 |
| M4 | 连续一个月虚拟人生 | 未开始 | 0/4 |
| M5 | AI 操作经验 A/B | 未开始 | 0/3 |
| M6 | 教育 App | 未开始 | 0/4 |
| M7 | 一年虚拟运行 | 未开始 | 0/4 |
| M8 | 消融与机制裁决 | 未开始 | 0/3 |

## M0 详细

| 任务 | 名称 | 状态 | 测试 | Commit | 备注 |
|---|---|---|---|---|---|
| M0-001 | 仓库骨架 | FINAL PASS | 33+15 | 8197c4f | Manifest 8ea4a102... |
| M0-002 | 统一错误码 | FINAL PASS | 72+15 | 3430e13 | - |
| M0-003 | 稳定对象 ID | FINAL PASS | 103+15 | f705e38 | ids.py SHA256 9972e1d4... |
| M0-004 | 唯一时间轴、三类时间、跨时区规范化与 Knowledge Cutoff | FINAL PASS | 146+15 | 3678ab8 | time.py SHA256 0a243b69... |
| M0-005 | WorldObject 公共字段与 Append-Only Revision | FINAL PASS | 163+15 | e15a0f9 | 11字段, revision+1, append-only, world vs object分离, object_type immutable |
| M0-006 | ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性 | FINAL PASS | 181+15 | eacd160 | pinned vs floating, knowledge visibility, canary, DST, Dependency exact ObjectRef, CI SUCCESS Python 3.12.14 |
| M0-007 | Observation（基础观测）契约冻结 | FINAL PASS | 194+15 | 9bee623 | Observation基础观测, 无高层语义, 统一时间轴, !=Wake, 无衍生, helper纪律, CI SUCCESS Python 3.12.14 |
| M0-008 | Claim（主张）语义模型冻结 | FINAL PASS | 211+15 | 65f1dd2 | Claim语义, claim_type vs knowledge_state, FACT!=truth, claimant!=subject, 独立revision, exact types, CI SUCCESS Python 3.12.14 |
| M0-009 | EvidenceSet（一等证据集合）契约冻结 | FINAL PASS | 234+15 | cda888f | EvidenceSet可复核可冻结可重建, pinned refs, fixed time_range, frozen cutoff, support/counter/context分离, coverage/missingness, pinned history, stale/rebuild, persistence revalidation generic, CI SUCCESS Python 3.12.14 |
| M0-010 | Entity + Relation（实体与关系）契约冻结 | FINAL PASS | 253+15 | 949e90e | stable Entity ID, canonical_name非key, identity provenance pinned, Relation独立历史与evidence pinned, CI SUCCESS Python 3.12.14 |
| M0-011 | DimensionDefinition / Membership / Derivation 三层契约 | FINAL PASS | 268+15 | 295d2a1 | data_shape开放, multi-membership, high-level drill-down, pinned provenance, raw Observation不复制, R2 lifecycle exact, Reference 15纳入CI |
| M0-012 | EventAnchor（事件锚点）契约与生命周期 | FINAL PASS | 284+15 | 5ab6ed1 | candidate/active/resolved/revised/rejected/merged/split, support/counter evidence, pinned provenance, revision_reason, sports-day->track-test历史回放, raw Observation不复制, CI SUCCESS Python 3.12.14 |
| M0-013 | Goal（目标）一等对象 | FINAL PASS | 297+15 | f309873 | Goal!=Task, R2 GoalStatus exact, explicit/inferred/App source semantics, Goal不自动建Task, 否认推断目标后Task仍可追溯复核, CI SUCCESS Python 3.12.14 |
| M0-014 | Task / Wake / Session / Action / Outcome 基础契约 | FINAL PASS | 315+15 | af49c27 | durable Task, Wake provenance, Session snapshot/checkpoint, stable execution_id, Action!=Outcome, outcome可UNKNOWN, 消息送达!=帮助成功, CI SUCCESS Python 3.12.14 |
| M0-015 | Dependency（依赖）契约 | FINAL PASS | 329+15 | 3b4e8b6 | exact-version Dependency, pinned endpoints, open dependency_type, direct self-dependency拒绝, explicit dependency cycle guard, Relation环不受影响, exact-revision reverse impact scan, CI SUCCESS Python 3.12.14 |
| M0-016 | OperationRequest、审计与幂等契约 | FINAL PASS | 341+15 | cdbd7ff | exact OperationRequest fields, nonblank identity/reason/key, same-key replay before version check, world revision advances once, VERSION_CONFLICT not swallowed, durable operation audit query/restart, CI SUCCESS Python 3.12.14 |
| M0-017 | SQLite 追加式世界存储 schema | FINAL PASS | 353+15 | c9bd2d8 | world_meta/world_commits/object_revisions/operations/idempotency, WAL+foreign keys, restart-safe, append-only revisions, rollback atomicity, multi-object one world revision, stale writer VERSION_CONFLICT, AI Worker DB isolation, CI SUCCESS Python 3.12.14 |
| M0-018 | 全局 World Revision 与原子提交 | FINAL PASS | 358+15 | f007351 | one logical commit=one world revision, 3 objects share one revision, true mid-insert rollback, concurrent writers only one succeeds, Session snapshot stays fixed, failed tx consumes no revision, CI SUCCESS Python 3.12.14 |
| M0-019 | 引用存在性与同事务引用验证 | FINAL PASS | 366+15 | f1dc7cc | mandatory persistence-boundary ref validation, no bypass flag, pinned/floating knowledge visibility, legal same-tx refs, current-revision self-citation rejected, historical self-link legal, CI SUCCESS Python 3.12.14 |
| M0-020 | 历史世界读取与 Knowledge Cutoff | FINAL PASS | 377+15 | 426ea4c | object/world revision + learned_at knowledge cutoff, zero future leakage, latest-visible snapshot before mutable filters, actual snapshot revision + minimal coverage, CI SUCCESS Python 3.12.14 |
| M0-021 | Task / Event 状态机冻结 | FINAL PASS | 385+15 | 8818dba | exhaustive Task/Event matrices, terminal-state guards, immutable transition views, state change requires same object + exact next revision, CI SUCCESS Python 3.12.14 |
| M0-022 | M0 契约总测试与冻结快照 | CHIEF GATE READY / WAITING ARCHITECT | 391+15 | 95cec41 | schema/hash snapshot + four required Gate fixtures green; no production semantic diff; GPT-6 independent architecture red-team required before FINAL PASS / M1 |
