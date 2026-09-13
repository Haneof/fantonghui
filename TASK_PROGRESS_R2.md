# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 17:45 UTC (M0-001-R 完成)

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 | 1/22 + R审查完成 |
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
| M0-001 | 仓库骨架、包边界与依赖方向 | ✅ COMPLETED | 执行程序员 | 架构6 + 单元15 =21 passed | cb24f04 | 2026-09-14 17:40 | 已同步aios-2.0主线 |
| M0-001-R | 复审：Python基线+文档单一真源+审查包 | ✅ COMPLETED | 执行程序员 | 21 + 15 passed | e36c365 | 2026-09-14 17:45 | CONDITIONAL PASS 已修正 |
| M0-002 | 统一错误码和协议级异常 | ⬜ TODO | 总工审核 | - | - | - | 需冻结ErrorCode |
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

## M0-001 / M0-001-R 完成报告摘要

- **M0-001 目标**: 建立正式 Python src layout，五大运行单元边界明确
- **M0-001 交付**: pyproject.toml, src/aios_core 12包, ai_worker/console/simulator/evaluator隔离, tests/unit 15 + architecture 6 =21 passed, docs归档, CI, README边界
- **M0-001-R 修正**:
  - Python基线恢复 >=3.12 (原参考证据 aios_core_r2_reference/pyproject.toml:6)
  - 实际环境 3.11.2 -> PYTHON_312_RUNTIME_UNAVAILABLE，已保留正式要求
  - 文档SHA256校验8份文件完全一致，删除docs重复，保留docs/README.md权威说明
  - 架构测试递归确认，覆盖 sqlite3 / storage.sqlite_store 子模块
  - README措辞修正为政策检查，非OS沙箱
  - 重新测试 21+15 passed
  - 生成审查包 M0_001_REVIEW_PACKET.md + TEST_OUTPUT.txt + review.zip (c33e64e7...)
- **参考实现**: 未删除，语义不变，已迁入 src/aios_core
- **Commits**: cb24f04 (M0-001), d54ada2 (progress log), e36c365 (M0-001-R)
- **验收**: 全部满足 M0-001 + M0-001-R 标准，未进入M0-002

## 已知冲突 / 待总工裁决

| 冲突 | 描述 | 状态 | 处理 |
|---|---|---|---|
| Python版本 | 参考实现要求 >=3.12，当前CI环境 3.11.2，无法安装3.12 | 已记录 | 保留>=3.12，CI配置3.12，报告PYTHON_312_RUNTIME_UNAVAILABLE，当前代码可能兼容3.11 |

## 开发日志

### 2026-09-14
- 01:23 chore(freeze): 冻结 AIOS 1.0 至 aios 分支，Tag v1.0-frozen (负责人)
- 17:29 feat(aios-2.0): 初始化 2.0 主线 (负责人)
- 17:31 dc0b78b sync arena workspace to aios-2.0
- 17:37-17:40 M0-001 执行: 扫描A-I, 建src 12包, 迁移reference, pyproject.toml, architecture 6 tests, unit 15 tests, docs+CI+README, pytest 21+15 passed, cb24f04
- 17:40 d54ada2 更新 TASK_PROGRESS_R2 + DEV_LOG
- 17:42-17:45 M0-001-R 执行:
  - Python基线检查与恢复 >=3.12, PYTHON_312_RUNTIME_UNAVAILABLE
  - 文档SHA256 8份 identical, 删除docs重复, 建docs/README权威说明
  - 架构测试递归复查
  - README措辞修正
  - 重新测试 21+15 passed
  - 生成 M0_001_REVIEW_PACKET.md + TEST_OUTPUT.txt + AIOS_2.0_M0-001_review.zip (c33e64e7)
  - e36c365 提交
- 待办: 等待总工审查 M0-001-R，禁止进入M0-002

## 运行证据归档

- aios_core_r2_reference_test_output.txt: 15 passed
- tests/unit: 15 passed
- tests/architecture: 6 passed
- M0_001_REVIEW_TEST_OUTPUT.txt: 21 passed (正式) + 15 passed (reference)
- AIOS_2.0_M0-001_review.zip: 172K, SHA256 c33e64e745db457d23d719872033e61579e893f8f8037860bb75d7013b8340e0

