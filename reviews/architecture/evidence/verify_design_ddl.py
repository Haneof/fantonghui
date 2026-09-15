"""把设计书里的全部 DDL 对仓库真实 schema 逐句执行，验证不与冻结表冲突。

用法: PYTHONPATH=src python reviews/architecture/evidence/verify_design_ddl.py
"""
from __future__ import annotations
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "src/aios_core/storage/sqlite_store.py"
DOC = ROOT / "reviews/architecture/AIOS_Core_全盘工程重构方案与详细任务拆分设计书_2026-09-16.md"


def statements(sql: str) -> list[str]:
    clean = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in clean.split(";") if s.strip()]


def main() -> int:
    con = sqlite3.connect(":memory:")
    real = re.findall(r"CREATE (?:TABLE|INDEX|VIRTUAL TABLE)[^;]*?;", STORE.read_text("utf-8"), re.S)
    applied = 0
    for stmt in real:
        con.execute(" ".join(stmt.split()))
        applied += 1
    print(f"repo schema statements applied: {applied}")

    blocks = re.findall(r"```sql\n(.*?)```", DOC.read_text("utf-8"), re.S)
    total = errors = 0
    for i, block in enumerate(blocks, 1):
        for stmt in statements(block):
            if not stmt.upper().startswith("CREATE"):
                continue
            total += 1
            try:
                con.execute(stmt)
            except sqlite3.Error as exc:
                errors += 1
                print(f"  block{i} ERR: {exc}\n    {' '.join(stmt.split())[:110]}")
    print(f"design-doc DDL statements: {total}, errors: {errors}")
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%' ORDER BY name")]
    print("tables:", tables)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
