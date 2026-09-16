# AIOS 2.0 Core - M0-001 仓库骨架

> 当前分支：`aios-2.0`（唯一开发主线） + `arena/01a09bc6-fantonghui` 工作分支
> 宪法基线：`AIOS核心系统宪法v3.0.md`（唯一基线）+《AIOS宪法v3.0修改案_R4.md》(待批准)
> 任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 当前任务：M0-001 仓库骨架、包边界与依赖方向
> 正式 Python 基线：`>=3.12` (参考实现 pyproject.toml 原始要求)

## 1. 当前阶段是什么

第一阶段目标不是做完整 Linux OS，而是用虚拟世界和模拟数据证明 AIOS Core 的核心认知机制成立：

- 持续运行、可追溯、可纠错的多维世界
- AI 自主选择观察尺度和查询路径
- 带不确定性的认知（Claim + EvidenceSet）
- 管理未来任务（Task Center）
- 学习更有效地使用世界（OperationExperience）

## 2. 五个主要代码包

| 包 | 职责 | DB写权限说明 |
|---|---|---|
| `src/aios_core` | 世界、对象、版本、写入、查询唯一正式实现 | 唯一被允许通过 `SQLiteWorldStore.commit()` 写入 |
| `src/ai_worker` | 调用大模型，通过 Core 公共接口操作世界 | 正式代码架构禁止直接访问SQLite，并由自动架构测试阻止已定义的直接依赖方式 |
| `src/console` | 开发者调试，查看时间轴、对象、证据、下钻 | 只读，通过 Core 查询接口 |
| `src/simulator` | 虚拟人生、虚拟时钟、观测生成 | 写入 Observation，但走 Core commit |
| `src/evaluator` | 隐藏真值、评分、B0/B1/B2 基线 | 保存隐藏答案，`aios_core` 绝不能 import evaluator |

`tests/` 包含 unit / integration / architecture / fixtures

`aios_core_r2_reference/` 是总工提供的冻结参考实现快照，不得删除，不得用另一套模型替换。

## 3. 如何安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

正式要求 Python 3.12+。当前代码可能兼容 3.11，但正式项目最低版本保持 >=3.12，不因开发机环境降低。

## 4. 如何运行测试

```bash
# 从项目根目录
python3.12 -m pytest -v
# 兼容环境
python -m pytest -v
# 架构边界
pytest tests/architecture -v
# 参考实现
pytest aios_core_r2_reference/tests -v
```

## 5. 参考代码和正式 src 的关系

- `aios_core_r2_reference/` = 总工第一批核心语义参考实现（ID、三类时间、Claim分离、EvidenceSet一等对象、Event生命周期、SQLite追加式版本库、World Revision、幂等、历史读取、状态机、15测试）
- `src/aios_core/` = 正式产品代码，M0-001 将参考实现 **move/refactor** 迁入，语义保持不变，不重写。
- 后续 M0-002~M0-022 在 `src/aios_core` 上继续扩展。

## 6. 哪一个模块拥有数据库写权限

正式架构中，只有 `src/aios_core/storage/sqlite_store.py` 的 `SQLiteWorldStore.commit()` 被允许作为世界写入的唯一实现。

所有其他包（ai_worker, console, simulator, evaluator）必须通过 Core 公共接口操作世界。

**注意**：当前架构测试属于“代码架构政策检查”，不是操作系统级安全沙箱。正式代码架构禁止 AI Worker 直接访问 SQLite，并由自动架构测试阻止已定义的直接依赖方式（import sqlite3 / import aios_core.storage 等），而非声称技术上绝对不可能。

## 7. AI Worker 为什么不能直接访问数据库

- 防止绕过版本、引用、幂等、审计校验
- 保证所有写入有 `operation_id / expected_world_revision / idempotency_key / reason`
- 保证历史世界可回放，knowledge cutoff 可隔离未来信息
- 保证控制台和 AI 看到的是同一个世界规则

## 8. Evaluator 为什么需要隐藏真值隔离

Evaluator 保存虚拟人真实隐藏状态、评分标准、未来观测。

如果 Core 或 AI Worker 能直接 import evaluator 真值，就无法证明 AI 是通过世界查询和推理得到的结论，测试泄露。

因此：

- `aios_core -> evaluator` 禁止
- `ai_worker -> evaluator` 隐藏真值模块禁止
- `simulator` 可按测试协议与 evaluator 协作，但正式查询接口不能读真值

## 9. 正式文档唯一真源

根目录中的正式 AIOS 文档为唯一权威版本，包括：

- AIOS宪法2.0.txt
- AIOS宪法2.0及开发规格修改案_R1.md / R2.md
- AIOS Core 系统架构图与开发规划.md
- AIOS认知工作台功能规格.md
- AIOS虚拟世界测试规范.md
- AIOS_Core_详细开发任务拆分_R2.md
- AIOS_Core_详细开发任务拆分_R2_总工程师版.md

`docs/` 目录不得保存这些文档的第二份可编辑副本，仅保留 `docs/README.md` 说明和 `docs/DEV_LOG.md` 开发日志。历史版本未来进入 archive/ 后另行管理。

## 10. M0-001 执行程序员施工自检

- [x] src layout 已建立
- [x] aios_core 唯一 Core 实现
- [x] ai_worker / console / simulator / evaluator 物理隔离
- [x] 架构边界自动测试（递归扫描 src/ai_worker, src/aios_core）
- [x] scanner 回归测试 12 cases (含 storage绕过、fail-closed)
- [x] 原参考测试继续通过
- [x] pytest 根目录执行成功 33 passed
- [x] pyproject.toml 可用 (requires-python >=3.12，无未授权MIT)
- [x] .gitignore 存在并包含 .venv/__pycache__/.pytest_cache/build/dist/egg-info/.env/*.db
- [x] 未删除宪法/架构文档（根为权威）
- [x] 未开始 M0-002 以后内容

总工程师代码复审：
CODE PASS (R2, SHA256 6e9dafa95060ad1c0aca2ac916e4a1433385e0374294fc397a35c3d8daccebb8, 33/33 + 15/15, Python 3.13.5 独立验证, wheel 构建+安装验证, storage绕过/fail-closed攻击测试通过)

总工程师最终项目验收：
FINAL PASS (冻结提交 8197c4f943c8e06f87bf25f18d79aceef982e196, Manifest 8ea4a102954f0d3f82bd2bb14a84aefe076b14675af304f9f493c7a619dee803)

下一授权任务：
M0-002 统一错误码、协议级错误结构与机器可恢复异常契约 (已授权开始)

## 11. M0-002 错误协议

code：机器分支语义
message：人类可读说明
context：机器可读细节

不得基于 message 文本做业务判断。

- ErrorCode 定义发生什么类别问题 (INVALID_ARGUMENT, NOT_FOUND, VERSION_CONFLICT, INCOMPLETE_DATA, STALE_INDEX, BUDGET_EXHAUSTED, PERMISSION_DENIED, DEPENDENCY_INVALID, OUTCOME_UNKNOWN, IDEMPOTENCY_CONFLICT)
- ErrorResponse 为 Pydantic 协议响应 (code, message, context JSON)
- AIOSProtocolError 为统一协议异常，StoreError 继承它
- StoreError 携带结构化 context (world revision, object revision, object_id, referenced_object_id 等)
- OUTCOME_UNKNOWN 表示真实结果未知，非 FAILED
- 业务逻辑必须按 code 分支，不得依赖 message 文本
- 协议响应不得泄露 traceback/内部异常 repr
