# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS核心系统宪法v3.0.md`（唯一基线）+《AIOS宪法v3.0修改案_R4.md》(待批准)
> 工程重构与模块编号唯一账本：《AIOS_Core_工程重构与任务拆分设计书_R4_首席架构师版.md》
> CAM 验收矩阵：`schemas/constitution_acceptance.py`（46+9 项，CI 闸门 tests/architecture/test_cam_coverage.py）
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-16 (M0′ R4 候选契约层冻结落地 + CAM 矩阵上线；等待 R4 修改案签核与 M0-022R 合并复审)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 — v2.0 契约集全绿 + **M0′ R4 候选契约层落地**；等待 R4 签核与 M0-022R 合并复审 | 16/22 FINAL PASS；5 项 REOPENED+PATCHED；M0-022 BLOCKED→待改签 022R；**M0′ 契约增量 6/8 候选冻结（M0-023~028），CAM M0-029 已交付，M0-030 待开工** |
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
| M0-001 | 仓库骨架 | FINAL PASS / Worker隔离措辞收窄 | Gate全量418+15 | 8197c4f | threat model=trusted reviewed modular-monolith code，不是 hostile-Python sandbox |
| M0-002 | 统一错误码 | **REOPENED / PATCHED / WAITING ARCHITECT** | Gate全量418+15 | patch `f38fdd2` | B5-b：新增 `STORAGE_FAILURE`，内部 storage/schema 故障不再伪装 INVALID_ARGUMENT |
| M0-003 | 稳定对象 ID | FINAL PASS | Gate全量418+15 | f705e38 | stable prefix+UUID4 |
| M0-004 | 唯一时间轴、三类时间、跨时区规范化与 Knowledge Cutoff | FINAL PASS / recorded_at ownership ruling | Gate全量418+15 | 3678ab8 | recorded_at=受控AIOS/模拟时间记录时刻；physical DB commit=`world_commits.committed_at`; M1 ingestion须约束伪造时间 |
| M0-005 | WorldObject 公共字段与 Append-Only Revision | FINAL PASS | Gate全量418+15 | e15a0f9 | revision+1, append-only, object/world revision分离 |
| M0-006 | ObjectRef / SourceRef 版本化引用与知识可见性 | FINAL PASS | Gate全量418+15 | eacd160 | pinned vs floating, knowledge visibility |
| M0-007 | Observation 契约冻结 | FINAL PASS | Gate全量418+15 | 9bee623 | Observation!=Wake |
| M0-008 | Claim 语义模型冻结 | FINAL PASS | Gate全量418+15 | 65f1dd2 | FACT!=truth, claimant!=subject |
| M0-009 | EvidenceSet 契约冻结 | **REOPENED / PATCHED / WAITING ARCHITECT** | Gate全量418+15 | patch `f38fdd2` | R4：typed evidence refs 必须在 EvidenceSet 自身 frozen knowledge_cutoff 可见；完整 world snapshot/materialization 仍在 M1-006 |
| M0-010 | Entity + Relation 契约 | FINAL PASS | Gate全量418+15 | 949e90e | stable identity, Relation history |
| M0-011 | Dimension 三层契约 | FINAL PASS | Gate全量418+15 | 295d2a1 | R2 lifecycle exact |
| M0-012 | EventAnchor 生命周期 | FINAL PASS | Gate全量418+15 | 5ab6ed1 | event lifecycle/history |
| M0-013 | Goal 一等对象 | FINAL PASS | Gate全量418+15 | f309873 | Goal!=Task |
| M0-014 | Task / Wake / Session / Action / Outcome | FINAL PASS | Gate全量418+15 | af49c27 | durable active-system contracts |
| M0-015 | Dependency 契约 | **FINAL PASS RESTORED AFTER INDEPENDENT RE-REVIEW** | Gate全量418+15 | original `3b4e8b6`, patch `8ab574c` | architect latest re-review 独立确认 durable cycle bypass 已关闭；不含 M3 correction/reverse-index |
| M0-016 | OperationRequest、审计与幂等 | **REOPENED / PATCHED / WAITING ARCHITECT** | Gate全量418+15 | patch `f38fdd2` | B6 canonical normalized fingerprint；B7 OperationRequest durable revalidation；exact stale replay 优先保持 |
| M0-017 | SQLite 追加式世界存储 | **REOPENED / PATCHED / WAITING ARCHITECT** | Gate全量418+15 | patch `f38fdd2` | connect/setup 纳入 StoreError boundary；busy=VERSION_CONFLICT；内部故障=STORAGE_FAILURE |
| M0-018 | 全局 World Revision 与原子提交 | FINAL PASS | Gate全量418+15 | f007351 | one logical commit=one world revision；rollback/no-gap regression green |
| M0-019 | 引用存在性与同事务引用验证 | **REOPENED / PATCHED / WAITING ARCHITECT** | Gate全量418+15 | patches `a99326c` + `f38fdd2` | current/floating self-ref durable拒绝；EvidenceSet ref 使用 frozen cutoff；历史 pinned self-link与合法same-tx保留 |
| M0-020 | 历史世界读取与 Knowledge Cutoff | FINAL PASS / R3 future service ruling | Gate全量418+15 | 426ea4c | store独立透镜保留；M1 public historical AI view 必须 world snapshot+cutoff 双绑定 |
| M0-021 | Task / Event 状态机冻结 | FINAL PASS | Gate全量418+15 | 8818dba | exhaustive matrices + revision transition helper |
| M0-022 | M0 契约总测试与冻结快照 | **BLOCKED / LATEST PATCH CANDIDATE GREEN / WAITING GPT-6 RE-REVIEW** | **418+15** | candidate `9c080f6` | latest repair green；未获准进入M1 |
| M0-023 | 写入来源分类 source_class 与触发豁免契约 | **契约层已冻结（R4 候选）/ 待签核** | tests/unit/test_m0_prime_contracts.py | governance/issues/M0-023_issue.md | 遗留运行面：M1 迁移+部分索引，M2-002 豁免过滤器 |
| M0-024 | LifeChapter 契约冻结 | **契约层已冻结（R4 候选）/ 待签核** | 同上 | M0-024_issue.md | 勘误：Summary 已在 M0 注册表，真实缺口仅 LifeChapter |
| M0-025 | Prediction Register 契约冻结 | **契约层已冻结（R4 候选）/ 待签核** | 同上 | M0-025_issue.md | 第 53 条立项理由空白拒写已入校验 |
| M0-026 | CommunicationExperience 契约冻结 | **契约层已冻结（R4 候选）/ 待签核** | 同上 | M0-026_issue.md | OpExp/ToolProposal 已冻（见 024 勘误），不重复 |
| M0-027 | Reinterpretation 契约冻结（R4-01） | **契约层已冻结（R4 候选）/ 待签核** | 同上 | M0-027_issue.md | M3-013 双透镜读面；撤销=MAINTENANCE |
| M0-028 | BudgetPolicy/AssemblyPolicy 契约冻结 | **契约层已冻结（R4 候选）/ 待签核** | 同上 | M0-028_issue.md | MeteringRecord/网关执法=M2-018 |
| M0-029 | CAM 宪法验收矩阵 + CI 映射 gate | **FINAL（本地实现层）** | tests/architecture/test_cam_coverage.py（7 用例） | schemas/constitution_acceptance.py | 55/55 项映射；R4 项批准前锁 proposed_pending_R4 |
| M0-030 | runtime_profile（virtual/band_v0）契约 | **待开工** | — | R4 设计书 §2.4 | 依赖 R4-09 批准 |

## Latest Gate evidence

- architect latest blocker report: governance commit `c068fc1fa0de528ab17cbfc4a4c6f9112b3ae164`
- accepted latest findings: B6 normalized-idempotency mismatch, B7 dirty OperationRequest persistence, B5-a connect boundary, B5-b storage error classification, R4 EvidenceSet frozen cutoff
- semantic repair: `f38fdd2aa64e31b92c5353206a8aef62c9322087`
- Chief review: `reviews/M0/M0_gate_B6_B7_B5_R4_resolution_2026-09-14.md`
- expected schema-drift CI: run `34827058782`, job `103921528459`: **417 passed / 1 snapshot mismatch**；mismatch 仅来自 approved `STORAGE_FAILURE` contract expansion / ErrorResponse schema hash change；Reference skipped
- latest exact green candidate: `9c080f693917c2c99bfbe6aa924e5f3cb54744a0`
- exact CI: run `34827250470`, job `103922130589`, CPython 3.12.14, formal **418 passed, 1 known warning**, Reference **15 passed**, SUCCESS
- production review/archive head after candidate may be newer；semantic candidate 与文档归档 commit 必须分开引用

M0 不得在 `architect-01` 对 `9c080f6...` 最新候选独立复审给出可接受 verdict 且 `chief-01` 最终签 Gate 前恢复为 22/22 FINAL PASS。M1 与并行核心开发继续暂停。

**M0′ 说明（2026-09-16）**：R4 修改案批准前，M0-023~028 以候选契约形态进入 registry/snapshot（`gate_version=M0-R2+R4-delta-candidate`），全量套件 586 passed / 1 环境性失败（b8 跨进程重放在沙箱 py3.11，CI 3.12.14 全绿）。批准动作 = 仅改 gate_version 字符串；驳回动作 = revert 契约 delta 并再生成快照。M1 开工 Gate 改为 **M0-022R**（v2.0 集 + R4 delta + CAM 55/55 映射 合并复审）。 **签核材料已打包**（`governance/M0-022R_ratification_package.md`，含五项风险摊开与批准/驳回单步动作）；M1-019 施工图与 R4-07a 静态守卫以 Gate 前文档/守卫形态先行就位（`governance/issues/M1-019_blueprint.md`）。 M1-020 HotCard 施工图同批就位（`governance/issues/M1-020_blueprint.md`，含摘要不回写教义与四槽位契约字段映射）；R2 改订草案已附于签核包 §7。
