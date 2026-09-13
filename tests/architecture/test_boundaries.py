"""M0-001 架构边界自动测试

TEST-A: ai_worker 不能直接 import sqlite3
TEST-B: ai_worker 不能直接 import aios_core.storage 内部实现 (含 from aios_core import storage 绕过)
TEST-C: aios_core 不能 import evaluator
TEST-D: ai_worker 不能 import evaluator 隐藏真值模块
TEST-E: 所有正式 Python 包能够 import
TEST-F: 仓库测试配置存在 (原 TEST-F 误导名称已修正)
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

def _parse_file_or_fail(file_path: pathlib.Path) -> ast.AST:
    """统一 parse helper，fail-closed：读取/解析失败必须让测试失败"""
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        raise AssertionError(f"无法读取文件 {file_path}: {e}") from e
    try:
        return ast.parse(text, filename=str(file_path))
    except SyntaxError as e:
        raise AssertionError(f"文件 {file_path} 存在语法错误，无法进行架构检查: {e}") from e
    except Exception as e:
        raise AssertionError(f"文件 {file_path} AST 解析失败: {e}") from e

def _has_import_sqlite3(file_path: pathlib.Path) -> bool:
    tree = _parse_file_or_fail(file_path)
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
    """检测 AI Worker 是否通过正常 import 语义取得 aios_core.storage 或子模块

    违规形式：
    - import aios_core.storage
    - import aios_core.storage.sqlite_store
    - from aios_core.storage import ...
    - from aios_core.storage.sqlite_store import ...
    - from aios_core import storage
    - from aios_core import storage as xxx
    - import aios_core.storage as xxx (已覆盖)
    """
    tree = _parse_file_or_fail(file_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "aios_core.storage" or alias.name.startswith("aios_core.storage."):
                    return True
        if isinstance(node, ast.ImportFrom):
            mod = node.module
            if not mod:
                continue
            if mod == "aios_core.storage" or mod.startswith("aios_core.storage."):
                return True
            if mod == "aios_core":
                for alias in node.names:
                    if alias.name == "storage" or alias.name.startswith("storage."):
                        return True
    return False

def _has_import_evaluator(file_path: pathlib.Path) -> bool:
    tree = _parse_file_or_fail(file_path)
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
    violations = []
    for py in _iter_py_files("ai_worker"):
        if _has_import_sqlite3(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"ai_worker 禁止直接 import sqlite3, 发现: {violations}"

def test_b_ai_worker_no_storage_internal():
    violations = []
    for py in _iter_py_files("ai_worker"):
        if _has_import_storage_internal(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"ai_worker 禁止直接 import aios_core.storage (含 from aios_core import storage 绕过), 发现: {violations}"

def test_c_core_no_evaluator():
    violations = []
    for py in _iter_py_files("aios_core"):
        if _has_import_evaluator(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"aios_core 禁止 import evaluator, 发现: {violations}"

def test_d_ai_worker_no_evaluator_truth():
    violations = []
    for py in _iter_py_files("ai_worker"):
        if _has_import_evaluator(py):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"ai_worker 禁止 import evaluator 隐藏真值, 发现: {violations}"

def test_e_all_packages_importable():
    src_str = str(SRC)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    import importlib
    packages = ["aios_core", "aios_core.contracts", "aios_core.storage", "aios_core.services",
                "ai_worker", "console", "simulator", "evaluator"]
    for pkg in packages:
        mod = importlib.import_module(pkg)
        assert mod is not None

def test_f_repository_test_configuration_present():
    assert ROOT.exists()
    assert (ROOT / "pyproject.toml").exists()
    assert (ROOT / "tests").exists()
    assert (ROOT / "src").exists()
