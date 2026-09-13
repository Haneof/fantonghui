# AIOS 2.0 Core - M0-001 仓库骨架

> 当前分支：`aios-2.0`（唯一开发主线） + `arena/01a09bc6-fantonghui` 工作分支
> 宪法基线：`AIOS宪法2.0.txt` + R1/R2 修改案
> 任务母表：`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`
> 当前任务：M0-001 仓库骨架、包边界与依赖方向

## 1. 当前阶段是什么

第一阶段目标不是做完整 Linux OS，而是用虚拟世界和模拟数据证明 AIOS Core 的核心认知机制成立：

- 持续运行、可追溯、可纠错的多维世界
- AI 自主选择观察尺度和查询路径
- 带不确定性的认知（Claim + EvidenceSet）
- 管理未来任务（Task Center）
- 学习更有效地使用世界（OperationExperience）

## 2. 五个主要代码包

| 包 | 职责 | 是否可写DB |
|---|---|---|
| `src/aios_core` | 世界、对象、版本、写入、查询唯一正式实现 | **唯一可写** SQLite，WAL，追加式 revision |
| `src/ai_worker` | 调用大模型，通过 Core 公共接口操作世界 | **禁止** `import sqlite3` / `aios_core.storage` 内部 |
| `src/console` | 开发者调试，查看时间轴、对象、证据、下钻 | 只读，通过 Core 查询接口 |
| `src/simulator` | 虚拟人生、虚拟时钟、观测生成 | 写入 Observation，但走 Core commit |
| `src/evaluator` | 隐藏真值、评分、B0/B1/B2 基线 | 保存隐藏答案，`aios_core` 绝不能 import evaluator |

`tests/` 包含 unit / integration / architecture / fixtures

`aios_core_r2_reference/` 是总工提供的冻结参考实现快照，不得删除，不得用另一套模型替换。

## 3. 如何安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

要求 Python 3.12+ (生产)，当前 CI 兼容 3.11。

## 4. 如何运行测试

```bash
# 从项目根目录
python -m pytest -v
# 或
pytest tests/architecture -v
pytest aios_core_r2_reference/tests -v
```

## 5. 参考代码和正式 src 的关系

- `aios_core_r2_reference/` = 总工第一批核心语义参考实现（ID、三类时间、Claim分离、EvidenceSet一等对象、Event生命周期、SQLite追加式版本库、World Revision、幂等、历史读取、状态机、15测试）
- `src/aios_core/` = 正式产品代码，M0-001 将参考实现 **move/refactor** 迁入，语义保持不变，不重写。
- 后续 M0-002~M0-022 在 `src/aios_core` 上继续扩展。

## 6. 哪一个模块拥有数据库写权限

只有 `src/aios_core/storage/sqlite_store.py` 的 `SQLiteWorldStore.commit()` 拥有写权限。

所有其他包必须通过它。

`ai_worker` 获得 `sqlite3.Connection` 即视为架构违规，architecture test 会失败。

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

## 9. M0-001 验收

- [x] src layout 已建立
- [x] aios_core 唯一 Core 实现
- [x] ai_worker / console / simulator / evaluator 物理隔离
- [x] 架构边界自动测试
- [x] 原参考测试继续通过
- [x] pytest 根目录执行成功
- [x] pyproject.toml 可用
- [x] 未删除宪法/架构文档
- [x] 未开始 M0-002 以后内容
