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
