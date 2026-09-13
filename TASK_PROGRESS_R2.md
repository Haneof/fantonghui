# AIOS 2.0 任务进度表

> 总任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2
> 当前主线：`aios-2.0`
> 工作分支：`arena/01a09bc6-fantonghui`
> 最后更新：2026-09-14 17:40 UTC

## 里程碑总览

| 里程碑 | 目标 | 状态 | 完成度 |
|---|---|---|---|
| M0 | 冻结世界契约与核心存储 | 进行中 | 1/22 (M0-001完成) |
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
| M0-001 | 仓库骨架、包边界与依赖方向 | ✅ COMPLETED | 执行程序员 | 架构6 + 单元15 =21 passed | cb24f04 | 2026-09-14 | 已同步aios-2.0主线 |
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

## M0-001 完成报告摘要

- **目标**: 建立正式 Python src layout，五大运行单元边界明确
- **交付**:
  - pyproject.toml (src layout)
  - src/aios_core (contracts/storage/services/query/world/dependency/tasks/wake/workspace/actions/summaries/dimensions)
  - src/ai_worker / console / simulator / evaluator 物理隔离
  - tests/unit (15) + tests/architecture (6) = 21 passed
  - docs/ 归档 8 正式文档
  - .github/workflows/ci.yml 最小CI
  - README 边界说明
- **架构边界**:
  - TEST-A: ai_worker 禁止 import sqlite3
  - TEST-B: ai_worker 禁止 import aios_core.storage
  - TEST-C: aios_core 禁止 import evaluator
  - TEST-D: ai_worker 禁止 import evaluator 真值
  - TEST-E: 所有包可 import
  - TEST-F: pytest 根目录执行
- **测试命令**:
  ```
  PYTHONPATH=src python3 -m pytest tests -v
  -> 21 passed
  PYTHONPATH=aios_core_r2_reference/src python3 -m pytest aios_core_r2_reference/tests -v
  -> 15 passed
  ```
- **参考实现**: 未删除，语义保持不变，已迁入 src/aios_core
- **Commit**: cb24f042bb0a4514e20413adb0ce5d1fac5340cd
- **验收**: 全部满足 M0-001 16项标准

## 已知冲突 / 待总工裁决

| 冲突 | 描述 | 状态 |
|---|---|---|
| Python版本 | 参考实现要求 >=3.12，当前CI环境 3.11.2 | 记录，兼容为 >=3.11，生产仍要求3.12 |

## 开发日志

### 2026-09-14
- 01:23 chore(freeze): 冻结 AIOS 1.0 至 aios 分支，Tag v1.0-frozen (负责人操作)
- 17:29 feat(aios-2.0): 初始化 2.0 主线，含宪法2.0、R1/R2、架构、认知工作台、虚拟世界规范、R2任务拆分、参考实现 (负责人操作)
- 17:31 arena分支同步至 aios-2.0: `dc0b78b chore: sync arena workspace to aios-2.0 mainline`
- 17:37-17:40 M0-001 执行:
  - 扫描根目录、参考代码、pyproject、git、包结构、pytest
  - 建立 src/ 12个包边界
  - 迁移 reference contracts/storage/services 到 src/aios_core
  - 创建 pyproject.toml (src layout)
  - 创建 tests/architecture/test_boundaries.py (6 tests)
  - 复制 reference tests 到 tests/unit (15 tests)
  - 创建 docs/ + .github/workflows/ci.yml + README 边界说明
  - pytest 21 passed, reference 15 passed
  - 提交 cb24f04 M0-001 establish repository boundaries
- 待办: 等待总工审查 M0-001，下一任务 M0-002

## 运行证据归档

- aios_core_r2_reference_test_output.txt: 15 passed
- tests/unit: 15 passed
- tests/architecture: 6 passed
- 总计: 21 passed (正式) + 15 passed (参考)

