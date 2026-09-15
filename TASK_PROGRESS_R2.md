# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`  
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2  
> Active production / default main：`aios-2.0`  
> M0 冻结 production baseline：`f2107656d404bb9cac526f71175cbfc1fbbb91cb`  
> M0 最终 Gate：`governance/agent_reports/M0_FINAL_PASS_2026-09-15.md`  
> M0 22项对账：`governance/agent_reports/M0_001_022_RECONCILIATION_2026-09-15.md`  
> M0→M1 分支清理：`governance/BRANCH_CLEANUP_M0_TO_M1_2026-09-15.md`  
> M1 职务/并行分配：`governance/M1_ROLE_AND_PARALLEL_ASSIGNMENT_R2_2026-09-15.md`  
> 最后更新：2026-09-15（M1-001 assigned / in progress）

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | **FINAL PASS** | **22/22** |
| M1 | 可写、可查、可下钻的共同世界 | **IN PROGRESS — M1-001** | 0/16 |
| M2 | 主动运行闭环 | 未开始 | 0/15 |
| M3 | 长期纠错与多尺度认知 | 未开始 | 0/11 |
| M4 | 连续一个月虚拟人生 | 未开始 | 0/4 |
| M5 | AI 操作经验 A/B | 未开始 | 0/3 |
| M6 | 教育 App | 未开始 | 0/4 |
| M7 | 一年虚拟运行 | 未开始 | 0/4 |
| M8 | 消融与机制裁决 | 未开始 | 0/3 |

## M0 详细

> 说明：早期逐项任务保留原始历史提交。M0-009～022 的“关闭基线”统一指向最终 production `f2107656...`，并不声称这些 Issue 都是在该单一 commit 首次实现；它表示最终验收时这些要求全部同时存在且通过 exact-head CI。历史 review 不删除、不改写。

| 任务 | 名称 | 状态 | 主要验证 | 关闭基线 / 历史提交 | 备注 |
|---|---|---|---|---|---|
| M0-001 | 仓库骨架、包边界与依赖方向 | FINAL PASS | architecture boundaries + scanner + worker policy | 历史 `8197c4f`; final `f2107656` | Core 唯一正式写入层；Evaluator 真值隔离 |
| M0-002 | 统一错误码与协议级异常 | FINAL PASS | `test_errors.py` | 历史 `3430e13`; final `f2107656` | code/message/context；无 traceback 协议泄露 |
| M0-003 | 稳定对象 ID | FINAL PASS | `test_ids.py`（含 100k uniqueness） | 历史 `f705e38`; final `f2107656` | rename/revise 不改 ID |
| M0-004 | 唯一时间轴、三类时间与 Knowledge Cutoff | FINAL PASS | `test_time.py` | 历史 `3678ab8`; final `f2107656` | aware datetime、跨时区、DST/边界回归 |
| M0-005 | WorldObject 公共字段与 Append-Only Revision | FINAL PASS | `test_world_object_revision.py` | 历史 `e15a0f9`; final `f2107656` | revision 连续、历史保留、world/object revision 分离 |
| M0-006 | ObjectRef / SourceRef 版本化引用 | FINAL PASS | `test_refs.py` + ref regressions | 历史 `eacd160`; final `f2107656` | pinned/floating、knowledge visibility |
| M0-007 | Observation 基础观测契约 | FINAL PASS | `test_observation.py` | 历史 `9bee623`; final `f2107656` | 不做高层语义；Observation != Wake |
| M0-008 | Claim 主张语义模型 | FINAL PASS | `test_claim.py` | 历史 `65f1dd2`; final `f2107656` | claim_type != knowledge_state；FACT != 自动真值 |
| M0-009 | EvidenceSet 一等证据集合 | FINAL PASS | `test_evidence_set.py` + persistence boundary regressions | final `f2107656` | 旧 `WAITING CHIEF REVIEW` 状态由最终 Chief/Gate 证据取代 |
| M0-010 | Entity + Relation 契约 | FINAL PASS | `test_entity_relation.py` | final `f2107656` | 未知身份、同名不自动合并、关系历史 |
| M0-011 | DimensionDefinition / Membership / Derivation 三层契约 | FINAL PASS | `test_dimensions.py` + persistence/lifecycle tests | final `f2107656` | 同一对象可多维挂载；高层可追溯；原始证据不复制 |
| M0-012 | EventAnchor 契约与生命周期 | FINAL PASS | `test_event_anchor.py` | final `f2107656` | candidate/active/revised/rejected/merged/split；历史可回放 |
| M0-013 | Goal 一等对象 | FINAL PASS | `test_goal.py` + reviewability | final `f2107656` | Goal != Task；explicit/inferred/app/AI self 分离 |
| M0-014 | Task / Wake / Session / Action / Outcome 基础契约 | FINAL PASS | `test_active_system_contracts.py` | final `f2107656` | Action != Outcome；Session 固定 snapshot；调度留到 M2 |
| M0-015 | Dependency 契约 | FINAL PASS | `test_dependency.py` | final `f2107656` | pinned revision、循环保护、反向影响查询基础 |
| M0-016 | OperationRequest、审计与幂等 | FINAL PASS | `test_operations.py` + retained idempotency regressions | final `f2107656` | exact replay、重启 replay、冲突 fail-closed |
| M0-017 | SQLite 追加式世界存储 schema | FINAL PASS | `test_sqlite_schema.py` | final `f2107656` | WAL、索引、重启、rollback、append-only |
| M0-018 | 全局 World Revision 与原子提交 | FINAL PASS | `test_world_revision_atomicity.py` | final `f2107656` | 一事务一 world revision；并发只有一个 writer 成功 |
| M0-019 | 引用存在性与同事务引用验证 | FINAL PASS | `test_reference_validation_m019.py` + typed-ref regressions | final `f2107656` | 缺失 ref 拒绝、同事务 ref 合法、自当前 revision 保护 |
| M0-020 | 历史世界读取与 Knowledge Cutoff | FINAL PASS | `test_history_m020.py` | final `f2107656` | future knowledge 0 泄露；实际 snapshot/coverage 可见 |
| M0-021 | Task / Event 状态机冻结 | FINAL PASS | `test_state_machines_m021.py` + reference tests | final `f2107656` | 全转换矩阵；非法转换明确拒绝；状态变化新 revision |
| M0-022 | M0 契约总测试与冻结快照 | FINAL PASS | schema snapshot + 4 integration fixtures + exact-head CI | final `f2107656` | production CI 558/558；Reference 15/15；冻结独立收敛 1046/1046 |

## M0 Gate 权威证据

- default main / active production：`aios-2.0`
- M0 frozen SHA：`f2107656d404bb9cac526f71175cbfc1fbbb91cb`
- GitHub Actions run：`34872128566`
- job：`104070337643`
- formal repository suite：`558 passed / 0 failed`
- R2 Reference suite：`15 passed / 0 failed`
- schema snapshot：`schemas/r2/m0_contract_snapshot.json`
- required gate fixtures：`tests/integration/test_m0_gate_fixtures.py`
- reconciliation report：`governance/agent_reports/M0_001_022_RECONCILIATION_2026-09-15.md`

## M1 当前执行

### M1-001 Observation 接入服务与去重

状态：**ASSIGNED / IN PROGRESS**

Core implementation branch：
`m1/core-m1-001-observation-ingest-20260915`

Independent tests branch：
`m1/parallel-m1-001-tests-20260915`

任务范围、验收和禁止事项严格来自总工程师任务母表。当前没有授权 M1-002～M1-016 提前开发；后续只在前置依赖 PASS 后解锁。

M1 的维度挂载、关键词超链、证据下钻分别仍按母表进入 `M1-004`、`M1-012`、`M1-013`；日/周/月总结仍按冻结路线进入 `M3-004/M3-005`，不得擅自前移或后移。