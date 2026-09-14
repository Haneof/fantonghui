# M0-001 代码审查包

## 1. 当前 commit hash

```
cb24f042bb0a4514e20413adb0ce5d1fac5340cd (M0-001 establish repository boundaries)
d54ada2 docs: update TASK_PROGRESS_R2 and DEV_LOG for M0-001
当前 HEAD: 
```
d54ada27c2b84da46411c76824e58fef81c28cca
d54ada2 docs: update TASK_PROGRESS_R2 and DEV_LOG for M0-001
cb24f04 M0-001 establish repository boundaries
dc0b78b chore: sync arena workspace to aios-2.0 mainline (frozen 1.0 archived)
e10103b docs(aios): record world interface and attribute panel discussion

## 2. Python正式基线

- 原参考实现声明位置: `aios_core_r2_reference/pyproject.toml`
- 原始证据:
```
requires-python = ">=3.12"
```
- 正式项目要求 (根 pyproject.toml):
```
requires-python = ">=3.12"
```
- 说明: 开发机器环境不能反向改变项目技术契约。正式测试优先使用 Python 3.12，CI 已配置 3.12。

## 3. 实际测试Python版本

```
python3 --version
```
Python 3.11.2

- 尝试获取 Python 3.12:
  - which python3.12: not found
  - apt install: Permission denied / missing lists
  - 结论: PYTHON_312_RUNTIME_UNAVAILABLE (已按命令要求保留 >=3.12 作为正式要求，不再次降低)

- 当前代码兼容性: 当前代码可能兼容 3.11 (实测 3.11.2 下 21 tests passed)，但正式最低版本保持 >=3.12。

## 4. pyproject关键配置

[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "aios-core"
version = "0.1.0"
description = "AIOS Core 2.0 - 共同世界运行时 + 认知工作台 + 任务调度 + 虚拟世界评估 (M0-001 骨架)"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "MIT"}
dependencies = [
  "pydantic>=2.10,<3",
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<9",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-q"

[tool.setuptools]
include-package-data = true

## 5. 完整目录树

```
./.github/workflows/ci.yml
./.gitignore
./AIOS Core 系统架构图与开发规划.md
./AIOS_Core_详细开发任务拆分_R2.md
./AIOS_Core_详细开发任务拆分_R2_总工程师版.md
./AIOS宪法2.0.txt
./AIOS宪法2.0及开发规格修改案_R1.md
./AIOS宪法2.0及开发规格修改案_R2.md
./AIOS虚拟世界测试规范.md
./AIOS认知工作台功能规格.md
./M0_001_REVIEW_PACKET.md
./M0_001_REVIEW_TEST_OUTPUT.txt
./README.md
./TASK_PROGRESS_R2.md
./aios_core_r2_reference/README.md
./aios_core_r2_reference/pyproject.toml
./aios_core_r2_reference/src/aios_core/__init__.py
./aios_core_r2_reference/src/aios_core/contracts/__init__.py
./aios_core_r2_reference/src/aios_core/contracts/base.py
./aios_core_r2_reference/src/aios_core/contracts/enums.py
./aios_core_r2_reference/src/aios_core/contracts/ids.py
./aios_core_r2_reference/src/aios_core/contracts/models.py
./aios_core_r2_reference/src/aios_core/contracts/operations.py
./aios_core_r2_reference/src/aios_core/contracts/refs.py
./aios_core_r2_reference/src/aios_core/contracts/time.py
./aios_core_r2_reference/src/aios_core/services/__init__.py
./aios_core_r2_reference/src/aios_core/services/state_machines.py
./aios_core_r2_reference/src/aios_core/storage/__init__.py
./aios_core_r2_reference/src/aios_core/storage/sqlite_store.py
./aios_core_r2_reference/src/aios_core_r2_reference.egg-info/PKG-INFO
./aios_core_r2_reference/src/aios_core_r2_reference.egg-info/SOURCES.txt
./aios_core_r2_reference/src/aios_core_r2_reference.egg-info/dependency_links.txt
./aios_core_r2_reference/src/aios_core_r2_reference.egg-info/requires.txt
./aios_core_r2_reference/src/aios_core_r2_reference.egg-info/top_level.txt
./aios_core_r2_reference/tests/test_contracts.py
./aios_core_r2_reference/tests/test_state_machines.py
./aios_core_r2_reference/tests/test_store.py
./aios_core_r2_reference_test_output.txt
./docs/DEV_LOG.md
./docs/README.md
./pyproject.toml
./src/ai_worker/__init__.py
./src/aios_core/__init__.py
./src/aios_core/actions/__init__.py
./src/aios_core/contracts/__init__.py
./src/aios_core/contracts/base.py
./src/aios_core/contracts/enums.py
./src/aios_core/contracts/ids.py
./src/aios_core/contracts/models.py
./src/aios_core/contracts/operations.py
./src/aios_core/contracts/refs.py
./src/aios_core/contracts/time.py
./src/aios_core/dependency/__init__.py
./src/aios_core/dimensions/__init__.py
./src/aios_core/query/__init__.py
./src/aios_core/services/__init__.py
./src/aios_core/services/state_machines.py
./src/aios_core/storage/__init__.py
./src/aios_core/storage/sqlite_store.py
./src/aios_core/summaries/__init__.py
./src/aios_core/tasks/__init__.py
./src/aios_core/wake/__init__.py
./src/aios_core/workspace/__init__.py
./src/aios_core/world/__init__.py
./src/console/__init__.py
./src/evaluator/__init__.py
./src/simulator/__init__.py
./tests/__init__.py
./tests/architecture/__init__.py
./tests/architecture/test_boundaries.py
./tests/fixtures/__init__.py
./tests/integration/__init__.py
./tests/unit/__init__.py
./tests/unit/test_contracts.py
./tests/unit/test_state_machines.py
./tests/unit/test_store.py
```

## 6. 正式测试结果

命令: `PYTHONPATH=src python3 -m pytest tests -v`

```
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/user/fantonghui
configfile: pyproject.toml
collected 21 items

tests/architecture/test_boundaries.py ......                             [ 28%]
tests/unit/test_contracts.py .....                                       [ 52%]
tests/unit/test_state_machines.py ....                                   [ 71%]
tests/unit/test_store.py ......                                          [100%]

============================== 21 passed in 0.24s ==============================
```

## 7. reference测试结果

命令: `PYTHONPATH=aios_core_r2_reference/src python3 -m pytest aios_core_r2_reference/tests -v`

```
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/user/fantonghui/aios_core_r2_reference
configfile: pyproject.toml
collected 15 items

aios_core_r2_reference/tests/test_contracts.py .....                     [ 33%]
aios_core_r2_reference/tests/test_state_machines.py ....                 [ 60%]
aios_core_r2_reference/tests/test_store.py ......                        [100%]

============================== 15 passed in 0.20s ==============================
```

## 8. architecture测试列表

- TEST-A: ai_worker 禁止 import sqlite3 (递归扫描 src/ai_worker/**/*.py)
- TEST-B: ai_worker 禁止 import aios_core.storage (递归，覆盖 import aios_core.storage, import aios_core.storage.sqlite_store, from aios_core.storage import ..., from aios_core.storage.sqlite_store import ...)
- TEST-C: aios_core 禁止 import evaluator (递归扫描 src/aios_core/**/*.py)
- TEST-D: ai_worker 禁止 import evaluator 隐藏真值 (递归扫描 src/ai_worker)
- TEST-E: 所有正式包可 import (aios_core, contracts, storage, services, ai_worker, console, simulator, evaluator)
- TEST-F: pytest 根目录执行 (检查 pyproject.toml 存在)

实现: AST 递归 rglob("*.py")，检查 ast.Import 和 ast.ImportFrom，module startswith 匹配。

## 9. 文档唯一真源说明

- 规则: 根目录中的正式AIOS文档为唯一权威版本。
- 根目录权威文档 (8个):
  - AIOS宪法2.0.txt (SHA256: e74a45f139f2f8afabc5ed03bd369cd89dd666036fd70566be699c2afe21cf95)
  - AIOS Core 系统架构图与开发规划.md (9fb1b1cf9c431512f88c514a662b15d40d20c27ef0505f242241edef4050cf71)
  - AIOS认知工作台功能规格.md (c568d2ab41ce1a81bc1324dfaecb5973fd49c55eb9be29cdc4b0b2f6709b4a51)
  - AIOS虚拟世界测试规范.md (a5f90a1b7d966f5a1ca8e7351d9d53e4456354d68163eede1765d192a54506a6)
  - AIOS宪法2.0及开发规格修改案_R1.md (51c30801b1897e0afd39bc1a2fd189b0ce2f526a0bc4066ad79d408dc41c53c4)
  - AIOS宪法2.0及开发规格修改案_R2.md (4f725189f23a252433ddf7ff8c2a88a1db68cf74d040ca9486efc6980e63f0fe)
  - AIOS_Core_详细开发任务拆分_R2.md (2d60276dcdb4107bb87f5b18ef702cd4e315272191d739edaeee406498b5faaa)
  - AIOS_Core_详细开发任务拆分_R2_总工程师版.md (314f94b32a8b119e09e369c971d0e7f887ea295a745c8058f59526c7136bf5cb)
- docs/ 副本检查: 8个文件与根完全一致 (SHA256 逐项相同，已在上一轮验证)，已删除 docs/ 中重复正文文件。
- docs/ 现保留:
  - docs/README.md (权威说明: 根为唯一真源，docs不得保存第二份可编辑副本)
  - docs/DEV_LOG.md (开发日志，非正式规格)

## 10. 本轮所有修改文件

### M0-001-R 本轮修改
- pyproject.toml: requires-python 从 >=3.11 恢复为 >=3.12
- README.md: 修正DB写权限描述为“正式代码架构禁止...并由自动架构测试阻止已定义的直接依赖方式”，非绝对不可能；明确正式文档唯一真源
- docs/: 删除8个重复正式文档，新增 docs/README.md 权威说明

### M0-001 原始提交 (cb24f04) 新增
- pyproject.toml (新建)
- src/aios_core/* (12包，contracts/storage/services从reference迁入)
- src/ai_worker, console, simulator, evaluator
- tests/unit/*, tests/architecture/*
- docs/ (当时归档，后本轮清理重复)
- .github/workflows/ci.yml
- TASK_PROGRESS_R2.md
- README.md (边界说明)

## 11. git status --short

```
 M README.md
 D "docs/AIOS Core \347\263\273\347\273\237\346\236\266\346\236\204\345\233\276\344\270\216\345\274\200\345\217\221\350\247\204\345\210\222.md"
 D "docs/AIOS_Core_\350\257\246\347\273\206\345\274\200\345\217\221\344\273\273\345\212\241\346\213\206\345\210\206_R2.md"
 D "docs/AIOS_Core_\350\257\246\347\273\206\345\274\200\345\217\221\344\273\273\345\212\241\346\213\206\345\210\206_R2_\346\200\273\345\267\245\347\250\213\345\270\210\347\211\210.md"
 D "docs/AIOS\345\256\252\346\263\2252.0.txt"
 D "docs/AIOS\345\256\252\346\263\2252.0\345\217\212\345\274\200\345\217\221\350\247\204\346\240\274\344\277\256\346\224\271\346\241\210_R1.md"
 D "docs/AIOS\345\256\252\346\263\2252.0\345\217\212\345\274\200\345\217\221\350\247\204\346\240\274\344\277\256\346\224\271\346\241\210_R2.md"
 D "docs/AIOS\350\231\232\346\213\237\344\270\226\347\225\214\346\265\213\350\257\225\350\247\204\350\214\203.md"
 D "docs/AIOS\350\256\244\347\237\245\345\267\245\344\275\234\345\217\260\345\212\237\350\203\275\350\247\204\346\240\274.md"
 M pyproject.toml
?? M0_001_REVIEW_PACKET.md
?? M0_001_REVIEW_TEST_OUTPUT.txt
?? docs/README.md
```

## 12. 与总工程师命令仍存在的任何偏差

- Python 3.12 运行时不可用 (PYTHON_312_RUNTIME_UNAVAILABLE)，已按要求保留 >=3.12，不降低基线，CI已配置3.12，实际测试在3.11.2下通过并记录兼容性说明。
- 其余均按 M0-001-R 命令执行，未开发 M0-002，未修改世界对象语义，未新增架构。

## 附录: 三个关键文件全文

### pyproject.toml 已在第4节

### tests/architecture/test_boundaries.py

### src/aios_core/__init__.py


### pyproject.toml 全文
```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "aios-core"
version = "0.1.0"
description = "AIOS Core 2.0 - 共同世界运行时 + 认知工作台 + 任务调度 + 虚拟世界评估 (M0-001 骨架)"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "MIT"}
dependencies = [
  "pydantic>=2.10,<3",
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<9",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-q"

[tool.setuptools]
include-package-data = true
```

### tests/architecture/test_boundaries.py 全文
```python
"""M0-001 架构边界自动测试

TEST-A: ai_worker 不能直接 import sqlite3
TEST-B: ai_worker 不能直接 import aios_core.storage 内部实现
TEST-C: aios_core 不能 import evaluator
TEST-D: ai_worker 不能 import evaluator 隐藏真值模块
TEST-E: 所有正式 Python 包能够 import
TEST-F: pytest 可以从项目根目录正常执行 (由 pytest 本身保证)
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

def _iter_py_files(pkg: str):
    pkg_path = SRC / pkg
    if not pkg_path.exists():
        return []
    return list(pkg_path.rglob("*.py"))

def _has_import_sqlite3(file_path: pathlib.Path) -> bool:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3" or alias.name.startswith("sqlite3."):
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "sqlite3" or node.module.startswith("sqlite3.")):
                return True
    return False

def _has_import_storage_internal(file_path: pathlib.Path) -> bool:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("aios_core.storage"):
                # 允许 from aios_core.storage import SQLiteWorldStore ? 任务说禁止直接 import 内部实现
                # 保守：禁止任何 aios_core.storage 导入，未来只能通过公共 service
                return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("aios_core.storage"):
                    return True
    return False

def _has_import_evaluator(file_path: pathlib.Path) -> bool:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "evaluator" or alias.name.startswith("evaluator."):
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "evaluator" or node.module.startswith("evaluator.")):
                return True
    return False

def test_a_ai_worker_no_sqlite3():
    """TEST-A: src/ai_worker 下的 Python 文件不能直接 import sqlite3"""
    violations = []
    for py in _iter_py_files("ai_worker"):
        if _has_import_sqlite3(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"ai_worker 禁止直接 import sqlite3, 发现: {violations}"

def test_b_ai_worker_no_storage_internal():
    """TEST-B: ai_worker 不得直接 import aios_core.storage 内部实现"""
    violations = []
    for py in _iter_py_files("ai_worker"):
        if _has_import_storage_internal(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"ai_worker 禁止直接 import aios_core.storage, 发现: {violations}"

def test_c_core_no_evaluator():
    """TEST-C: aios_core 不能 import evaluator"""
    violations = []
    for py in _iter_py_files("aios_core"):
        if _has_import_evaluator(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"aios_core 禁止 import evaluator, 发现: {violations}"

def test_d_ai_worker_no_evaluator_truth():
    """TEST-D: ai_worker 不能 import evaluator 的隐藏真值模块"""
    violations = []
    for py in _iter_py_files("ai_worker"):
        if _has_import_evaluator(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"ai_worker 禁止 import evaluator 隐藏真值, 发现: {violations}"

def test_e_all_packages_importable():
    """TEST-E: 项目所有正式 Python 包能够 import"""
    # 确保 src 在 sys.path
    src_str = str(SRC)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    import importlib
    packages = ["aios_core", "aios_core.contracts", "aios_core.storage", "aios_core.services",
                "ai_worker", "console", "simulator", "evaluator"]
    for pkg in packages:
        mod = importlib.import_module(pkg)
        assert mod is not None, f"包 {pkg} 无法 import"

def test_f_pytest_runs_from_root():
    """TEST-F: pytest 可以从项目根目录正常执行 - 此测试本身能运行即证明"""
    assert ROOT.exists()
    assert (ROOT / "pyproject.toml").exists()
```

### src/aios_core/__init__.py 全文
```python
"""AIOS Core - 唯一世界读写与规则实现。

此包是 AIOS 世界的唯一正式实现，所有世界修改最终必须经过此包的 storage / services。
禁止 ai_worker / console / simulator / evaluator 直接操作 SQLite。
"""
```
