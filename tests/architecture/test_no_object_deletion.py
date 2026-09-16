"""R4-07a 归档审计·静态层（M1-019 施工图的先行执法件）。

宪法 33.5（R4 改订）：世界对象的历史只有 tombstone 修订，没有物理删除。
本测试在 M1 Gate 之前即生效——它锁的不是未来功能，而是当下就成立的
append-only 承诺；任何为"归档"开 DELETE 先例的实现都会被它直接拦下。

禁止集：针对 world_objects / object_revisions / world_commits 真相表的
`DELETE FROM` / `DROP TABLE` / `TRUNCATE`。
豁免面：投影表（search_*、summary、ref_counts 类）可整删重建——它们本来
就不是真相；迁移重建的临时表（*_m023、*_m1_019、*_old）随迁移收尾属白名单。
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "aios_core"

TRUTH_TABLES = r"(?:world_objects|object_revisions|world_commits)"
FORBIDDEN = re.compile(
    rf"(?:DELETE\s+FROM|DROP\s+TABLE(?:\s+IF\s+EXISTS)?|TRUNCATE\s+TABLE)\s+"
    rf"\"?{TRUTH_TABLES}\"?\b",
    re.IGNORECASE,
)
# 迁移重建模式：先把真相表改名走 *_old/*_m0xx 再建新表——DROP 的是带后缀的替身，
# 正则只匹配裸真相表名，天然不命中；此处再显式放行含迁移注释的行，防误伤。
MIGRATION_EXEMPT = re.compile(r"#\s*r4-07-exempt\s+(?:rename-rebuild)", re.IGNORECASE)


def _iter_py():
    return (p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_physical_deletion_of_truth_tables():
    offenders: list[str] = []
    for path in _iter_py():
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if FORBIDDEN.search(line) and not MIGRATION_EXEMPT.search(line):
                offenders.append(f"{path.relative_to(SRC.parents[1])}:{lineno}: {line.strip()}")
    assert not offenders, (
        "R4-07 归档审计违例：真相表被物理删除（33.5 要求 tombstone 修订替代删除）\n"
        + "\n".join(offenders)
    )


def test_guard_itself_detects_a_synthetic_violation(tmp_path):
    """守卫防自嗨：造一个假违例文件必须被抓到（用真实 src 树外副本验证正则语义）。"""
    probe = "conn.execute(\"DELETE FROM world_objects WHERE object_id='x'\")"
    assert FORBIDDEN.search(probe)
    benign_rename = "conn.execute('DROP TABLE world_commits_old')  # r4-07-exempt rename-rebuild"
    assert not FORBIDDEN.search(benign_rename)
