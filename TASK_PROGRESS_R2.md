# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 21:30 UTC (M0-002 FINAL PASS, M0-003 CODE COMPLETE)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS | 2/22 FINAL PASS + M0-003 CODE COMPLETE |
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
| M0-001 | 仓库骨架、包边界与依赖方向 | FINAL PASS | 33 + 15 | 8197c4f | Manifest 8ea4a102... |
| M0-002 | 统一错误码、协议级错误结构 | FINAL PASS | 72 + 15 | 3430e13 | ErrorCode10, ErrorResponse, AIOSProtocolError, StoreError, strict JSON, context隔离 |
| M0-002-R1 | 强化协议不变量 | COMPLETED | 72 + 15 | 3430e13 | P01-P09 S01-S03 |
| M0-003 | 稳定对象 ID 生成器 | CODE COMPLETE / WAITING CHIEF REVIEW | 103 + 15 | 待提交 | 31新增, 100k唯一性, rename/revision稳定性, UUID4冻结 |
| M0-004 | 唯一时间轴与三类时间 | TODO / HOLD | - | - | 禁止提前开始 |
| M0-005 | WorldObject 公共字段 | TODO / HOLD | - | - | - |
| M0-006 | ObjectRef/SourceRef | TODO / HOLD | - | - | - |

## M0-002 FINAL PASS 摘要
- 冻结提交 3430e13
- 总工确认：构造即验证、context隔离、NaN/Infinity拒绝、empty/duplicate/self-current测试、ErrorCode未变、reference未改
- 72 passed + 15 reference

## M0-003 完成摘要
- ids.py SHA256 9972e1d4d7e272019da26d8fb466a9391dea868039e43b5fc9cdaf33073a8993 与总工冻结一致
- Prefix 19个冻结，唯一，非空，覆盖全部 ObjectType
- 格式 <prefix>_[0-9a-f]{32}, op_[0-9a-f]{32}, exec_[0-9a-f]{32}
- 100k唯一性 100k/100k 碰撞0 耗时~0.4s
- Rename稳定性：未知人物A -> 妈妈 同一 object_id
- Revision稳定性：Event revision1/2 复用 object_id
- 名称不进入ID：签名仅 object_type, ID不含妈妈
- Truth leakage：secret_truth not in ID, 签名无truth参数
- UUID版本：version 4 冻结
- 测试 103 passed + 15 reference, 对抗 A-E 有效
- 状态 CODE COMPLETE / WAITING CHIEF REVIEW
