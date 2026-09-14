# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 (M0 GATE BLOCKERS PATCHED / WAITING ARCHITECT RE-REVIEW)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 — Gate blocker patch 已全绿，等待 GPT-6 复审 | 19/22 当前未重开 FINAL PASS；M0-015/016 REOPENED+PATCHED；M0-022 BLOCKED |
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
| M0-001 | 仓库骨架 | FINAL PASS / Worker隔离措辞被Gate裁决收窄 | 33+15 + Gate scanner | 8197c4f | M0 threat model=trusted reviewed modular-monolith code，不是 hostile-Python sandbox；Worker 仍禁止直接 storage/SQLite |
| M0-002 | 统一错误码 | FINAL PASS | 72+15 | 3430e13 | - |
| M0-003 | 稳定对象 ID | FINAL PASS | 103+15 | f705e38 | ids.py SHA256 9972e1d4... |
| M0-004 | 唯一时间轴、三类时间、跨时区规范化与 Knowledge Cutoff | FINAL PASS | 146+15 | 3678ab8 | time.py SHA256 0a243b69... |
| M0-005 | WorldObject 公共字段与 Append-Only Revision | FINAL PASS | 163+15 | e15a0f9 | 11字段, revision+1, append-only, world vs object分离, object_type immutable |
| M0-006 | ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性 | FINAL PASS | 181+15 | eacd160 | pinned vs floating, knowledge visibility, canary, DST |
| M0-007 | Observation（基础观测）契约冻结 | FINAL PASS | 194+15 | 9bee623 | Observation!=Wake |
| M0-008 | Claim（主张）语义模型冻结 | FINAL PASS | 211+15 | 65f1dd2 | FACT!=truth, claimant!=subject |
| M0-009 | EvidenceSet（一等证据集合）契约冻结 | FINAL PASS | 234+15 | cda888f | persistence revalidation generic |
| M0-010 | Entity + Relation（实体与关系）契约冻结 | FINAL PASS | 253+15 | 949e90e | stable identity, Relation history |
| M0-011 | DimensionDefinition / Membership / Derivation 三层契约 | FINAL PASS | 268+15 | 295d2a1 | R2 lifecycle exact |
| M0-012 | EventAnchor（事件锚点）契约与生命周期 | FINAL PASS | 284+15 | 5ab6ed1 | event lifecycle/history |
| M0-013 | Goal（目标）一等对象 | FINAL PASS | 297+15 | f309873 | Goal!=Task |
| M0-014 | Task / Wake / Session / Action / Outcome 基础契约 | FINAL PASS | 315+15 | af49c27 | durable active-system contracts |
| M0-015 | Dependency（依赖）契约 | **REOPENED / PATCHED / WAITING ARCHITECT** | Gate全量400+15 | patch `8ab574c` | GPT-6发现cycle helper可被durable write绕过；现已在SQLite persistence boundary检查 durable latest + pending Dependency graph，环=>DEPENDENCY_INVALID |
| M0-016 | OperationRequest、审计与幂等契约 | **REOPENED / PATCHED / WAITING ARCHITECT** | Gate全量400+15 | patch `8ab574c` | same key只有完整request fingerprint一致才replay；不一致=>IDEMPOTENCY_CONFLICT，无写入 |
| M0-017 | SQLite 追加式世界存储 schema | FINAL PASS / Worker隔离措辞收窄 | 353+15 + Gate tests | c9bd2d8 | storage invariants保留；M0不再宣称同进程 hostile Python sandbox |
| M0-018 | 全局 World Revision 与原子提交 | FINAL PASS | 358+15 | f007351 | one logical commit=one world revision |
| M0-019 | 引用存在性与同事务引用验证 | FINAL PASS | 366+15 | f1dc7cc | mandatory reference validation |
| M0-020 | 历史世界读取与 Knowledge Cutoff | FINAL PASS | 377+15 | 426ea4c | zero future leakage under frozen semantics |
| M0-021 | Task / Event 状态机冻结 | FINAL PASS | 385+15 | 8818dba | exhaustive matrices + revision transition validator |
| M0-022 | M0 契约总测试与冻结快照 | **BLOCKED / PATCH CANDIDATE GREEN / WAITING GPT-6 RE-REVIEW** | **400+15** | candidate `8b3bca9` | 原Gate `95cec41` 被GPT-6判BLOCKER FOUND；B1/B2/B3已修/裁决；exact CI run 34821050459 SUCCESS；未获准进入M1 |

## Gate blocker evidence

- architect-01 blocker report: governance commit `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- B1/B3 semantic patch: `8ab574c6b33b2238b468c812992a92ba56ab3f71`
- B2 scanner hardening: `e06bc80e43ea26be2be726232158cb2719092f11`
- Chief ruling/review: `reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`
- current patch candidate: `8b3bca9ef3bf8fde2ee09b73a2631a3a2f12db0a`
- exact CI: run `34821050459`, job `103902471146`, formal 400 passed / Reference 15 passed / SUCCESS

M0 不得在 architect-01 独立复审给出可接受 verdict 前恢复为 22/22 FINAL PASS。
