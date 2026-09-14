# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 23:59 UTC (M0-010 CODE COMPLETE)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS | 9/22 FINAL PASS + M0-010 CODE COMPLETE |
| M1 | 可写、可查、可下钻的共同世界 | 未开始 | 0/16 |
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
| M0-010 | Entity + Relation（实体与关系）契约冻结 | CODE COMPLETE / WAITING CHIEF REVIEW | 252+15 | 待 | Entity稳定ID, canonical_name非key, unknown P001->妈妈, identity Claim provenance pinned, 同名小王不合并, Relation独立对象 left/right按ID, evidence pinned, colleague->former_colleague, world revision replay, valid_time exact, durable mutation ER17/18 |
