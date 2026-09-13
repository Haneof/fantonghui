# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 20:00 UTC (M0-001 FINAL PASS, M0-002 CODE COMPLETE)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS | 1/22 FINAL PASS + M0-002 CODE COMPLETE |
| M1 | 可写、可查、可下钻的共同世界 | 未开始 | 0/16 |
| M2 | 主动运行闭环 | 未开始 | 0/15 |
| M3 | 长期纠错与多尺度认知 | 未开始 | 0/11 |
| M4 | 连续一个月虚拟人生 | 未开始 | 0/4 |
| M5 | AI 操作经验 A/B | 未开始 | 0/3 |
| M6 | 教育 App | 未开始 | 0/4 |
| M7 | 一年虚拟运行 | 未开始 | 0/4 |
| M8 | 消融与机制裁决 | 未开始 | 0/3 |

## M0 详细 (世界契约与核心存储冻结)

| 任务 | 名称 | 状态 | 负责人级别 | 测试 | Commit | 完成时间 | 备注 |
|---|---|---|---|---|---|---|---|
| M0-001 | 仓库骨架、包边界与依赖方向 | FINAL PASS | 执行程序员 | 33 + 15 passed | 8197c4f | 2026-09-14 19:00 | 冻结 Manifest 8ea4a102... |
| M0-001-R | 复审：Python基线+文档单一真源+审查包 | ✅ COMPLETED | 执行程序员 | 21 + 15 passed | e36c365 | 2026-09-14 17:45 | - |
| M0-001-R2 | 加固边界检查 | CODE PASS | 执行程序员 | 33 + 15 passed | 2f5ebe8 | 2026-09-14 18:19 | - |
| M0-001-R3 | 最终交付闭环 | COMPLETED | 执行程序员 | 33 + 15 passed | 8197c4f | 2026-09-14 19:00 | - |
| M0-002 | 统一错误码、协议级错误结构与机器可恢复异常契约 | CODE COMPLETE / WAITING CHIEF REVIEW | 总工审核 | 57 + 15 passed | 待提交 | 2026-09-14 20:00 | 24新增, 57总, reference 15, 对抗验证通过 |
| M0-003 | 稳定对象 ID 生成器 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | 禁止提前开始 |
| M0-004 | 唯一时间轴与三类时间 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-005 | WorldObject 公共字段与 Revision | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-006 | ObjectRef/SourceRef 版本化引用 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-007 | Observation 契约 | ⬜ TODO / HOLD | 总工审核 | - | - | - | - |
| M0-008 | Claim 语义模型 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-009 | EvidenceSet 一等对象 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-010 | Entity+Relation 契约 | ⬜ TODO / HOLD | 总工审核 | - | - | - | - |
| M0-011 | Dimension三层契约 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-012 | EventAnchor 契约与生命周期 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-013 | Goal 一等对象 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-014 | Task/Wake/Session/Action/Outcome | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-015 | Dependency 契约 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-016 | OperationRequest 审计与幂等 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | 完整幂等检测由本任务完成 |
| M0-017 | SQLite 追加式存储 schema | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-018 | 全局 World Revision 与原子提交 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-019 | 引用存在性与同事务验证 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-020 | 历史世界读取与 Knowledge Cutoff | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-021 | Task/Event 状态机冻结 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-022 | M0 契约总测试与冻结快照 | ⬜ TODO / HOLD | 总工验收 | - | - | - | Gate |

## M0-001 FINAL PASS 摘要
- 冻结提交 8197c4f, Manifest 8ea4a102...
- 总工独立验证 33/33 + 15/15 PASS, Python 3.13.5
- FINAL PASS 已归档 reviews/M0/M0-001_final_PASS_2026-09-14.md

## M0-002 完成摘要
- ErrorCode 冻结10个
- ErrorResponse (extra forbid, frozen, JsonValue)
- AIOSProtocolError (code, message, context, to_response)
- StoreError 继承 AIOSProtocolError + 结构化 context
- 测试 57 passed (33原 + 24新增) + 15 reference
- 对抗验证 A-E 有效
- 未越界 M0-016/Action Runtime/API
- 状态 CODE COMPLETE / WAITING CHIEF REVIEW

## 已知冲突
- Python 3.11.2 vs >=3.12 基线, PYTHON_312_RUNTIME_UNAVAILABLE
- GitHub workflow 权限已解决 CI_WORKFLOW_PRESENT, 但云端3.12运行结果 PYTHON_312_CI_RESULT_UNAVAILABLE
