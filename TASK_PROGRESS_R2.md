# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 23:59 UTC (M0-005 FINAL PASS, M0-006 CODE COMPLETE)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS | 5/22 FINAL PASS + M0-006 CODE COMPLETE |
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
| M0-006 | ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性 | CODE COMPLETE / WAITING CHIEF REVIEW | 179+15 | 待 | pinned vs floating, knowledge visibility, pending mutual |
