"""M0 Gate clarification: Worker isolation is a trusted-code dependency policy.

This is defense-in-depth static enforcement, not a Python sandbox. It rejects
ordinary imports plus obvious constant-string dynamic imports. The architectural
security claim is intentionally narrower: reviewed AI Worker code must use Core
public interfaces and must never be handed DB paths, sqlite connections, or
storage objects. Hostile Python executed in the same interpreter is outside the
M0 threat model.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "src" / "ai_worker"
FORBIDDEN_MODULES = ("sqlite3", "aios_core.storage")


def _is_forbidden(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in FORBIDDEN_MODULES
    )


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    importlib_aliases: set[str] = {"importlib"}
    import_module_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    violations.append(f"line {node.lineno}: import {alias.name}")
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_forbidden(module):
                violations.append(f"line {node.lineno}: from {module} import ...")
            if module == "aios_core" and any(alias.name == "storage" for alias in node.names):
                violations.append(f"line {node.lineno}: from aios_core import storage")
            if module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_names.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        target = _constant_string(node.args[0])
        if target is None or not _is_forbidden(target):
            continue

        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            violations.append(f"line {node.lineno}: __import__({target!r})")
            continue
        if isinstance(node.func, ast.Name) and node.func.id in import_module_names:
            violations.append(f"line {node.lineno}: import_module({target!r})")
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in importlib_aliases
        ):
            violations.append(f"line {node.lineno}: importlib.import_module({target!r})")

    return violations


def test_worker_has_no_forbidden_static_or_obvious_dynamic_storage_imports():
    violations: list[str] = []
    for path in WORKER.rglob("*.py"):
        for detail in _violations(path):
            violations.append(f"{path.relative_to(ROOT)}: {detail}")
    assert not violations, "AI Worker must use Core public interfaces; violations: " + repr(violations)


def test_scanner_catches_architect_dynamic_import_counterexamples(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text(
        "__import__('sqlite3').connect('x')\n"
        "import importlib as il\n"
        "il.import_module('aios_core.storage').SQLiteWorldStore('x')\n",
        encoding="utf-8",
    )
    violations = _violations(probe)
    assert any("sqlite3" in violation for violation in violations)
    assert any("aios_core.storage" in violation for violation in violations)
