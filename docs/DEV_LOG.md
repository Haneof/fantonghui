# AIOS 2.0 开发日志

## 2026-09-14 M0-001 仓库骨架、包边界与依赖方向

### 执行前检查

**A. 当前目录树**
- 根: 8个md规格 + README + aios_core_r2_reference + test_output
- 无 src/, 无 pyproject.toml, 有 .git, 有 reference

**B. 参考代码目录树**
- aios_core_r2_reference/src/aios_core/contracts/ 8文件
- storage/sqlite_store.py 459行
- services/state_machines.py
- tests/ 15 tests

**C. pyproject.toml**
- 根: 不存在
- reference: 存在, name=aios-core-r2-reference, requires-python>=3.12, pydantic>=2.10, pytest>=8

**D. .git**
- 存在, branch arena/01a09bc6-fantonghui, 已同步至 aios-2.0

**E. Python包结构**
- 仅 aios_core_r2_reference/src/aios_core/__init__.py

**F. 测试结构**
- 仅 aios_core_r2_reference/tests/

**G. pytest**
- 可执行, pytest 9.1.1, python 3.11.2

**H. 参考测试结果**
- 15 passed

**I. 冲突**
- 无 src/，符合M0-001预期，需新建

### 执行步骤

1. mkdir -p src/aios_core/{contracts,storage,services,query,world,dependency,tasks,wake,workspace,actions,summaries,dimensions} src/ai_worker src/console src/simulator src/evaluator tests/{unit,integration,architecture,fixtures} docs .github/workflows
2. cp reference contracts/storage/services -> src/aios_core/
3. 创建占位 __init__.py，写入边界红线说明
4. 创建 pyproject.toml src layout
5. 创建 tests/architecture/test_boundaries.py AST扫描
6. 复制 reference tests -> tests/unit/
7. 创建 docs/归档 + CI + README + TASK_PROGRESS_R2.md
8. pytest tests -v -> 21 passed
9. pytest reference -> 15 passed
10. git commit cb24f04

### 架构边界实现细节

- TEST-A/B: 扫描 ai_worker/*.py AST，禁止 sqlite3 和 aios_core.storage
- TEST-C: 扫描 aios_core/*.py 禁止 evaluator
- TEST-D: 扫描 ai_worker 禁止 evaluator
- TEST-E: importlib.import_module 8个包
- TEST-F: 检查 pyproject.toml 存在

### 验收

- 正式 src layout 已建立
- aios_core 唯一 Core 实现
- 5大运行单元物理隔离
- 架构测试6 + 单元15 =21 passed
- 原参考15 tests仍通过
- pytest根目录执行成功
- pyproject.toml可用
- README边界说明
- 未删宪法/架构文档
- 未开始M0-002

### 下一步

等待总工审查 M0-001，通过后进入 M0-002 统一错误码和协议级异常

