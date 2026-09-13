# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 21:00 UTC (M0-001 FINAL PASS, M0-002 PATCH COMPLETE)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS | 1/22 FINAL PASS + M0-002 PATCH COMPLETE |
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
| M0-001 | 仓库骨架、包边界与依赖方向 | FINAL PASS | 33 + 15 passed | 8197c4f | 冻结 Manifest 8ea4a102... |
| M0-001-R3 | 最终交付闭环 | COMPLETED | 33 + 15 passed | 8197c4f | - |
| M0-002 | 统一错误码、协议级错误结构 | PATCH COMPLETE / WAITING CHIEF REVIEW | 72 + 15 passed | b59cc71 -> R1待提交 | R1修复协议不变量漏洞 |
| M0-002-R1 | 强化协议错误对象不变量、严格JSON、context不可污染 | PATCH COMPLETE / WAITING CHIEF REVIEW | 72 + 15 passed | 待提交 | 新增 P01-P09 S01-S03 15 tests |
| M0-003 | 稳定对象 ID 生成器 | TODO / HOLD | - | - | 禁止提前开始 |

## M0-002-R1 修复摘要

- **阻塞问题1**: AIOSProtocolError构造时未验证context -> 修复：构造即通过 ErrorResponse 验证，非法context立即失败
- **阻塞问题2**: context可被外部污染 -> 修复：内部保存 model_copy(deep=True)，原始dict修改不污染，getter返回 deepcopy，to_response 返回 deep copy 稳定
- **阻塞问题3**: 严格JSON数值 NaN/Infinity -> 修复：ErrorResponse ConfigDict allow_inf_nan=False，拒绝 NaN/Infinity/-Infinity
- **新增测试**: P01-P09 (构造验证、NaN/Infinity、json.dumps strict、原始隔离、getter隔离、to_response稳定) + S01-S03 (empty_commit, duplicate_revision, self-current reference)
- **测试**: 72 passed (原57 + 新增15), reference 15 passed
- **对抗验证**: A-E 均有效
- **未修改**: ErrorCode集合、schema、事务、world revision、reference validation、idempotency算法、Action Runtime、HTTP层

## 已知冲突
- Python 3.11.2 vs >=3.12, PYTHON_312_RUNTIME_UNAVAILABLE
- CI_WORKFLOW_PRESENT, 但云端3.12结果 PYTHON_312_CI_RESULT_UNAVAILABLE
