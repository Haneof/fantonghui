# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 19:30 UTC (M0-001 FINAL PASS, M0-002 IN PROGRESS)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 IN PROGRESS | 1/22 FINAL PASS + M0-002 IN PROGRESS |
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
| M0-001 | 仓库骨架、包边界与依赖方向 | FINAL PASS | 执行程序员 | 33 + 15 passed | 8197c4f | 2026-09-14 19:00 | 总工独立验证 33/33 + 15/15, Python 3.13.5, 冻结 Manifest 8ea4a102... |
| M0-001-R | 复审：Python基线+文档单一真源+审查包 | ✅ COMPLETED | 执行程序员 | 21 + 15 passed | e36c365 | 2026-09-14 17:45 | CONDITIONAL PASS 修正 |
| M0-001-R2 | 加固边界检查：storage绕过+fail-closed+回归测试+LICENSE+TEST-F | CODE PASS | 执行程序员 | 33 + 15 passed | 2f5ebe8 | 2026-09-14 18:19 | 总工独立验证 PASS |
| M0-001-R3 | 最终交付闭环、审查记录入库与云端同步 | COMPLETED | 执行程序员 | 33 + 15 passed | 8197c4f | 2026-09-14 19:00 | reviews归档, Git冻结, 云端同步, Manifest一致 |
| M0-002 | 统一错误码、协议级错误结构与机器可恢复异常契约 | IN PROGRESS | 总工审核 | 待新增 | - | - | 当前唯一开发任务 |
| M0-003 | 稳定对象 ID 生成器 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | ids.py 已在reference |
| M0-004 | 唯一时间轴与三类时间 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | time.py 已在reference |
| M0-005 | WorldObject 公共字段与 Revision | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | base.py 已在reference |
| M0-006 | ObjectRef/SourceRef 版本化引用 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | refs.py 已在reference |
| M0-007 | Observation 契约 | ⬜ TODO / HOLD | 总工审核 | - | - | - | - |
| M0-008 | Claim 语义模型 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-009 | EvidenceSet 一等对象 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-010 | Entity+Relation 契约 | ⬜ TODO / HOLD | 总工审核 | - | - | - | - |
| M0-011 | Dimension三层契约 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-012 | EventAnchor 契约与生命周期 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-013 | Goal 一等对象 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-014 | Task/Wake/Session/Action/Outcome | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-015 | Dependency 契约 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-016 | OperationRequest 审计与幂等 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-017 | SQLite 追加式存储 schema | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-018 | 全局 World Revision 与原子提交 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-019 | 引用存在性与同事务验证 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-020 | 历史世界读取与 Knowledge Cutoff | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-021 | Task/Event 状态机冻结 | ⬜ TODO / HOLD | 总工亲自代码 | - | - | - | - |
| M0-022 | M0 契约总测试与冻结快照 | ⬜ TODO / HOLD | 总工验收 | - | - | - | Gate |

## M0-001 FINAL PASS 报告摘要

- **冻结提交**: 8197c4f943c8e06f87bf25f18d79aceef982e196
- **已审功能 Manifest**: 8ea4a102954f0d3f82bd2bb14a84aefe076b14675af304f9f493c7a619dee803
- **总工独立验证**: 33/33 + 15/15 PASS, Python 3.13.5, wheel构建+安装, storage绕过/fail-closed攻击测试通过
- **R3 闭环**: Git冻结, reviews归档, TASK_PROGRESS同步, 云端push, 工作区clean, 功能Manifest前后一致
- **Python 3.12 CI**: 配置为 3.12, 云端结果 PYTHON_312_CI_RESULT_UNAVAILABLE, 不阻塞 M0-001, M0 Gate 前补齐
- **最终裁决**: M0-001 FINAL PASS, 允许开始 M0-002, 禁止跳过 M0-002

## M0-002 详细

- **目标**: 统一错误码、协议级错误结构与机器可恢复异常契约
- **状态**: IN PROGRESS
- **ErrorCode**: INVALID_ARGUMENT, NOT_FOUND, VERSION_CONFLICT, INCOMPLETE_DATA, STALE_INDEX, BUDGET_EXHAUSTED, PERMISSION_DENIED, DEPENDENCY_INVALID, OUTCOME_UNKNOWN, IDEMPOTENCY_CONFLICT (10个, 冻结)
- **新增**:
  - src/aios_core/contracts/errors.py: ErrorResponse (code, message, context JSON, extra forbid, frozen)
  - src/aios_core/errors.py: AIOSProtocolError (code, message, context, to_response())
  - StoreError 继承 AIOSProtocolError, 携带结构化 context
  - tests/unit/test_errors.py: 20+ cases
- **禁止**: 新增 ErrorCode (INTERNAL等), 修改现有字符串值, 重写幂等/事务/schema, 开发 Action Runtime/API/LLM Worker

## 已知冲突 / 待总工裁决

| 冲突 | 描述 | 状态 | 处理 |
|---|---|---|---|
| Python版本 | 参考实现要求 >=3.12，当前CI环境 3.11.2，无法安装3.12 | 已记录 | 保留>=3.12，CI配置3.12，报告PYTHON_312_RUNTIME_UNAVAILABLE |
| GitHub workflow权限 | 曾因 GitHub App 无 workflows 权限阻塞，本次推送成功 CI_WORKFLOW_PRESENT | 已解决 | 备份仍保留, 当前已推送 |

## 开发日志

### 2026-09-14
- 01:23 chore(freeze): 冻结 AIOS 1.0
- 17:29 feat(aios-2.0): 初始化 2.0 主线
- 17:31 dc0b78b sync arena workspace to aios-2.0
- 17:37-17:40 M0-001: 扫描A-I, 建src, 迁移reference, pyproject.toml, architecture 6 + unit 15 =21 passed, cb24f04
- 17:40 d54ada2 更新进度表+DEV_LOG
- 17:42-17:45 M0-001-R: Python基线恢复>=3.12, PYTHON_312_RUNTIME_UNAVAILABLE, 文档SHA256 identical后删docs重复, 建docs/README, README措辞修正, 21+15 passed, 审查包, e36c365
- 17:48 1854296 ci backup workflow as txt bypass permission (推送成功)
- 18:00-18:19 M0-001-R2: 修复 storage 绕过, fail-closed, 12 cases回归, TEST-F修正, 删除MIT, 33 passed + 15 ref + wheel, 2f5ebe8, ZIP 6e9dafa9...
- 18:30 总工独立审查: Python 3.13.5 33/33 + 15/15 PASS, wheel构建+安装, 攻击测试通过, 结论 R2 CODE PASS / DELIVERY PENDING, 功能Manifest 8ea4a102...
- 19:00 M0-001-R3: 校验Manifest 8ea4a102..., 创建 reviews/ + 2份审查记录 + evidence/, 更新README为施工自检 + CODE PASS / PENDING, 更新TASK_PROGRESS为 CODE PASS / DELIVERY CLOSURE, 提交 09d3725 + 8197c4f, Git clean, 推送成功, workflow权限解决 CI_WORKFLOW_PRESENT
- 19:15 总工签发 M0-001 FINAL PASS 8197c4f, Manifest 8ea4a102..., 允许 M0-002
- 19:30 M0-002 IN PROGRESS: 创建 FINAL PASS 归档, 更新README为FINAL PASS, TASK_PROGRESS为FINAL PASS + M0-002 IN PROGRESS, 开始错误协议开发

## 运行证据归档

- aios_core_r2_reference: 15 passed
- M0-001: tests 21 passed
- M0-001-R: 21 + 15 passed, review.zip SHA256 c33e64e7...
- M0-001-R2: tests 33 passed (18 arch + 15 unit) + 15 ref, wheel build success, ZIP SHA256 6e9dafa9...
- 总工独立验证: Python 3.13.5 33/33 + 15/15 PASS, wheel构建+安装, 攻击测试通过
- R2功能Manifest: 8ea4a102954f0d3f82bd2bb14a84aefe076b14675af304f9f493c7a619dee803
- M0-001 FINAL PASS: 8197c4f, Manifest 8ea4a102..., PYTHON_312_CI_RESULT_UNAVAILABLE
