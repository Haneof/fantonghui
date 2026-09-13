# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 22:00 UTC (M0-002 FINAL PASS, M0-003 PATCH COMPLETE)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS | 2/22 FINAL PASS + M0-003 PATCH COMPLETE |
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
| M0-001 | 仓库骨架 | FINAL PASS | 33+15 | 8197c4f | - |
| M0-002 | 统一错误码 | FINAL PASS | 72+15 | 3430e13 | - |
| M0-003 | 稳定对象 ID | PATCH COMPLETE / WAITING CHIEF REVIEW | 103+15 | ac8edcc -> R1待提交 | 生产代码PASS, 测试补强 |
| M0-003-R1 | 删除性能Gate, 补强名称测试 | PATCH COMPLETE / WAITING CHIEF REVIEW | 103+15 | 待提交 | 删除elapsed<60, 补强test_name_not_in_id |
| M0-004 | 唯一时间轴 | TODO / HOLD | - | - | 禁止提前开始 |
