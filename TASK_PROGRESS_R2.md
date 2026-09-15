# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 (M0 THIRD GATE PATCH GREEN / WAITING ARCHITECT RE-REVIEW)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 — B6/B7/B5/R4 patch 已全绿，等待 GPT-6 复审 | 16/22 当前保持 FINAL PASS；M0-002/009/016/017/019 REOPENED+PATCHED；M0-022 BLOCKED |
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

## 架构评审备注（2026-09-15，不改变任何任务状态）

《AIOS核心系统宪法v3.0》已有 4 份主审 + 3 份 Gap Audit + 1 份元裁决在库。统一裁决见
`reviews/architecture/AIOS_V3_MULTI_REVIEW_META_AUDIT_NO_GO_2026-09-16.md`：
**`PATCH_REQUIRED / AS-WRITTEN NO-GO`**（v3.0 可作愿景与目标架构基线，但当前文本不得作为可直接执行的冻结合同）。

**统一整改母表（派单前必读）**：
`reviews/architecture/AIOS_V3_UNIFIED_BACKLOG_AND_AS_BUILT_VERIFICATION_2026-09-16.md`
——按元裁决 §6.1 第 5 项「以 D 为底稿合并 E/F」生成，含 Issue 同号异义仲裁表（§3.2）、
`TS-*`/`ACC-*`/`PAR-*`/`ARCH-*`/`WB-*`/`MOD-C*` 命名空间定稿（§3.3~3.4）、55 项母表（§4）、
可引用与不可引用实测数字登记（§5）、五张 12 要素 Issue 卡片（§6）。
**在该母表被 v3.0.1 修正案采纳前，禁止按 D/E/F 任一份的 Issue 编号派单。**

最新一份补充评审（as-built 压力实测）：
`reviews/architecture/AIOS_v3.0_CHIEF_REVIEW_R2_AS_BUILT_STRESS_PROBE_2026-09-15.md`
（证据：`reviews/architecture/evidence/aios_v3_as_built_probe.{py,log}`、`..._result.json`、
`..._environment.txt`、`..._SHA256SUMS`）。它服从上述元裁决，不另立口径。

与本进度表直接相关的两条治理阻断：

- **G1 双基线冲突**：v3.0 宣称唯一宪法基线，但 `schemas/r2/m0_contract_snapshot.json` 仍为
  `gate_version=M0-R2`，且 v3.0 所需的 `Prediction` / `LifeChapter` / `CommunicationExperience` /
  `TaskType.PREDICTION_CHECK` / `WakeSource.RELATION_RHYTHM` 均不在冻结契约内。
  须按第一百一十五条第 3 款提交正式架构变更并重冻结快照后，M0-022 才能与 v3.0 对齐。
- **G2 验收缺口**：第一百一十四条的验收表中，v3.0 十项机制只有 3 条软性新增验收（V3-01/02/03）
  + 2 条弱覆盖（A06/A07），无延迟/存储/token SLO、无中文检索可用性、无 FSM 误触率验收。
  候选补充项见该报告 7.4；最终编号须与报告 D 的 `V31~V45` 消歧后由统一修正案分配。

as-built 实测要点（供 M1 排期参考，非产品 SLO）：当前冻结 schema 上多关键词共现 1.28~1.36 s、
`occurred_at` 时间窗口查询 1.20~1.47 s（与窗口无关）、单次枢纽实体修正的依赖传播 9.3 s 且波及
51,822 个对象（≈15.55 M token 复核）；加入派生投影后分别降至 7~47 ms、0.66~112 ms、0.82~10.82 ms。

评审结论与元裁决一致：上述阻断项关闭前，M1 大规模编码保持暂停。
放行顺序为 **`NUMCI-001`（编号 registry + CI 门转绿）→ v3.0.1 修正案 → Gate 0（M0-023~M0-032）→
Gate 1（M1，含 `PROBE-CI-002` 四支探针入 CI）→ Gate 2（M2）→ Gate 3（M3）**；
Gate 0 未过时只允许做修正案、契约、迁移 fixture 与测试夹具。

> ⚠️ **上面出现的 `M0-023~M0-032` 等号位目前不具备派单效力**：同一号段被 5 套方案重复分配
> （争用面 66 个号，交叉矩阵见统一母表 §9.2）。号位真源已移至
> `governance/issue_registry/v3_issue_registry.json`（0.2.0-PROPOSAL 种子），
> CI 门 `governance/issue_registry/check_issue_registry.py` 当前实跑 **GATE = RED**
> （规则 A 0 / UNREGISTERED 0 / CONFLICT 39 / UNRATIFIED 21，exit 1；负向对照已验证门会开火）。
> 派单一律以 registry 的 `slug` 为准，号仅作显示。
