# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 19:00 UTC (M0-001-R3 进行中)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 CODE PASS / DELIVERY CLOSURE | 1/22 + R + R2 CODE PASS, R3 IN PROGRESS, 待 FINAL PASS |
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
| M0-001 | 仓库骨架、包边界与依赖方向 | CODE PASS / DELIVERY CLOSURE | 执行程序员 | 架构6 + 回归12 + 单元15 =33 passed | 2f5ebe8 | 2026-09-14 18:19 | R2 CODE PASS, 等待 R3 闭环 |
| M0-001-R | 复审：Python基线+文档单一真源+审查包 | ✅ COMPLETED | 执行程序员 | 21 + 15 passed | e36c365 | 2026-09-14 17:45 | CONDITIONAL PASS 修正 |
| M0-001-R2 | 加固边界检查：storage绕过+fail-closed+回归测试+LICENSE+TEST-F | CODE PASS | 执行程序员 | 架构18 + 单元15 =33 passed | 2f5ebe8 | 2026-09-14 18:19 | 总工独立验证 33/33 + 15/15 PASS, Python 3.13.5 |
| M0-001-R3 | 最终交付闭环、审查记录入库与云端同步 | IN PROGRESS | 执行程序员 | 33 + 15 passed | 待提交 | 2026-09-14 19:00 | 归档 reviews/, Git冻结, 云端同步 |
| M0-002 | 统一错误码和协议级异常 | ⬜ TODO / HOLD | 总工审核 | - | - | - | 禁止提前开始，等待 M0-001 FINAL PASS |
| M0-003 | 稳定对象 ID 生成器 | ⬜ TODO (参考已存在) | 总工亲自代码 | - | - | - | ids.py 已在reference |
| M0-004 | 唯一时间轴与三类时间 | ⬜ TODO (参考已存在) | 总工亲自代码 | - | - | - | time.py 已在reference |
| M0-005 | WorldObject 公共字段与 Revision | ⬜ TODO (参考已存在) | 总工亲自代码 | - | - | - | base.py 已在reference |
| M0-006 | ObjectRef/SourceRef 版本化引用 | ⬜ TODO (参考已存在) | 总工亲自代码 | - | - | - | refs.py 已在reference |
| M0-007 | Observation 契约 | ⬜ TODO | 总工审核 | - | - | - | - |
| M0-008 | Claim 语义模型 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-009 | EvidenceSet 一等对象 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-010 | Entity+Relation 契约 | ⬜ TODO | 总工审核 | - | - | - | - |
| M0-011 | Dimension三层契约 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-012 | EventAnchor 契约与生命周期 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-013 | Goal 一等对象 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-014 | Task/Wake/Session/Action/Outcome | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-015 | Dependency 契约 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-016 | OperationRequest 审计与幂等 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-017 | SQLite 追加式存储 schema | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-018 | 全局 World Revision 与原子提交 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-019 | 引用存在性与同事务验证 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-020 | 历史世界读取与 Knowledge Cutoff | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-021 | Task/Event 状态机冻结 | ⬜ TODO | 总工亲自代码 | - | - | - | - |
| M0-022 | M0 契约总测试与冻结快照 | ⬜ TODO | 总工验收 | - | - | - | Gate |

## M0-001 / R / R2 / R3 完成报告摘要

- **正式 Python 基线**: >=3.12 (原参考 aios_core_r2_reference/pyproject.toml:6 证据，正式 pyproject.toml 已恢复，不因 3.11 环境降低)
- **实际测试环境**: Python 3.11.2 (PYTHON_312_RUNTIME_UNAVAILABLE)，当前代码可能兼容 3.11，但正式保持 >=3.12，CI 已配置 3.12
- **总工独立验证**: Python 3.13.5, 33/33 + 15/15 PASS, wheel 构建+安装验证, storage绕过/fail-closed攻击测试通过
- **M0-001 交付**: src 12包, 5大单元隔离, tests 21 passed, docs归档, CI, README
- **M0-001-R 修正**: Python基线恢复, 文档SHA256校验8份 identical后删除docs重复, 保留docs/README权威说明, README措辞修正, 审查包生成
- **M0-001-R2 修正**:
  - 修复 TEST-B 绕过: 新增检测 `from aios_core import storage` / `from aios_core import storage as xxx`
  - AST fail-closed: 统一 _parse_file_or_fail，OSError/UnicodeError/SyntaxError 必须抛 AssertionError，禁止返回 False
  - 增加 scanner 回归测试: 12 cases
  - 修正 TEST-F 为 repository_test_configuration_present
  - 删除 MIT License
  - .gitignore 确认并包含在新ZIP
  - Wheel 构建验证
- **M0-001-R3 闭环**:
  - 功能Manifest校验: 8ea4a102954f0d3f82bd2bb14a84aefe076b14675af304f9f493c7a619dee803
  - 创建 reviews/ + reviews/README.md + reviews/M0/PATCH_REQUIRED + reviews/M0/R2_CODE_PASS_DELIVERY_PENDING
  - 证据移动到 reviews/M0/evidence/
  - README 状态修正为“执行程序员施工自检” + CODE PASS / PENDING DELIVERY CLOSURE / M0-002 HOLD
  - TASK_PROGRESS 更新为 CODE PASS / DELIVERY CLOSURE, R2 CODE PASS, R3 IN PROGRESS, M0-002 HOLD
  - Git提交冻结 + 云端同步 + 功能Manifest复核
- **测试**: 正式 33 passed (架构18 + 单元15), reference 15 passed, wheel 构建成功
- **状态**: M0-001 CODE PASS / DELIVERY CLOSURE, 等待总工签发 FINAL PASS, 禁止进入 M0-002

## 已知冲突 / 待总工裁决

| 冲突 | 描述 | 状态 | 处理 |
|---|---|---|---|
| Python版本 | 参考实现要求 >=3.12，当前CI环境 3.11.2，无法安装3.12 | 已记录 | 保留>=3.12，CI配置3.12，报告PYTHON_312_RUNTIME_UNAVAILABLE |
| GitHub workflow权限 | GitHub App 无 workflows 权限无法直接推送 .github/workflows/ci.yml | 已记录 | 备份在 docs/workflow_backup/ci.yml.txt, 报告 GITHUB_WORKFLOW_PERMISSION_BLOCKED / PYTHON_312_CI_RESULT_UNAVAILABLE |

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
- 19:00 M0-001-R3: 校验Manifest 8ea4a102..., 创建 reviews/ + 2份审查记录 + evidence/, 更新README为施工自检 + CODE PASS / PENDING, 更新TASK_PROGRESS为 CODE PASS / DELIVERY CLOSURE, 准备提交 R3

## 运行证据归档

- aios_core_r2_reference: 15 passed
- M0-001: tests 21 passed
- M0-001-R: 21 + 15 passed, review.zip SHA256 c33e64e7...
- M0-001-R2: tests 33 passed (18 arch + 15 unit) + 15 ref, wheel build success, ZIP SHA256 6e9dafa9...
- 总工独立验证: Python 3.13.5 33/33 + 15/15 PASS, wheel构建+安装, 攻击测试通过
- R2功能Manifest: 8ea4a102954f0d3f82bd2bb14a84aefe076b14675af304f9f493c7a619dee803
