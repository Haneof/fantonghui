# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`

## 里程碑总览

| 里程碑 | 目标 | 状态 |
|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 M0-001 |
| M1 | 可写、可查、可下钻的共同世界 | 未开始 |
| M2 | 主动运行闭环 | 未开始 |
| M3 | 长期纠错与多尺度认知 | 未开始 |
| M4 | 连续一个月虚拟人生 | 未开始 |
| M5 | AI 操作经验 A/B | 未开始 |
| M6 | 教育 App | 未开始 |
| M7 | 一年虚拟运行 | 未开始 |
| M8 | 消融与机制裁决 | 未开始 |

## M0 详细

| 任务 | 名称 | 状态 | 负责人 | 测试 | 备注 |
|---|---|---|---|---|---|
| M0-001 | 仓库骨架、包边界与依赖方向 | COMPLETED | 执行程序员 | 架构测试6 + 单元15 | 2026-09-14 |
| M0-002 | 统一错误码和协议级异常 | TODO | - | - | 需总工审核 |
| M0-003 | 稳定对象 ID 生成器 | TODO (参考实现已存在) | 总工 | - | 已在 reference |
| M0-004 | 唯一时间轴与三类时间 | TODO (参考实现已存在) | 总工 | - | 已在 reference |
| M0-005 | WorldObject 公共字段与 Revision | TODO (参考实现已存在) | 总工 | - | 已在 reference |
| M0-006 | ObjectRef/SourceRef 版本化引用 | TODO (参考实现已存在) | 总工 | - | 已在 reference |
| M0-007 | Observation 契约 | TODO | 总工审核 | - | - |
| M0-008 | Claim 语义模型 | TODO | 总工 | - | - |
| M0-009 | EvidenceSet 一等对象 | TODO | 总工 | - | - |
| M0-010 | Entity+Relation 契约 | TODO | 总工审核 | - | - |
| M0-011 | Dimension三层契约 | TODO | 总工 | - | - |
| M0-012 | EventAnchor 契约与生命周期 | TODO | 总工 | - | - |
| M0-013 | Goal 一等对象 | TODO | 总工 | - | - |
| M0-014 | Task/Wake/Session/Action/Outcome | TODO | 总工 | - | - |
| M0-015 | Dependency 契约 | TODO | 总工 | - | - |
| M0-016 | OperationRequest 审计与幂等 | TODO | 总工 | - | - |
| M0-017 | SQLite 追加式存储 schema | TODO | 总工 | - | - |
| M0-018 | 全局 World Revision 与原子提交 | TODO | 总工 | - | - |
| M0-019 | 引用存在性与同事务验证 | TODO | 总工 | - | - |
| M0-020 | 历史世界读取与 Knowledge Cutoff | TODO | 总工 | - | - |
| M0-021 | Task/Event 状态机冻结 | TODO | 总工 | - | - |
| M0-022 | M0 契约总测试与冻结快照 | TODO | 总工验收 | - | Gate |

## 已知冲突 / 待总工裁决

- NONE

## 运行证据

- M0-001: pytest 21 passed (15 reference + 6 architecture)
- 参考实现测试: 15 passed

