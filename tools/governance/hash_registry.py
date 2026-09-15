#!/usr/bin/env python3
"""hash_registry.py —— 规范版本注册表（governance/normative_versions/registry.md）的哈希机械臂。

M0-023（V3 Authority & Traceability Freeze）声明的交付物；registry.md 表头指名依赖本工具。

两条宪法纪律的机器化：
  规则①  一行 = 一份规范的一个版本 → 本工具解析表格行，对"占位哈希格"（文字含
         "回填"/"补登"/"待"）在文件存在时补登 sha256；
  规则②  已入库的行禁止改写 → 本工具对**已含 64-hex 哈希的格绝不改写**；
         `--check` 模式下重新计算文件哈希并与表格比对，漂移即非零退出（CI 红）。

复合行（路径列含 "+"，如 CONST-v3.0.1 = 宪法原文 + 裁决集）约定：
  取 "+" 之后的路径段计算哈希；回填形态为 "同上 + `<hash>`"；
  `--check` 时取行内最后一个 hex64 与该路径段比对。

用法：
  python tools/governance/hash_registry.py --fill    # 补登占位哈希（只填空，不改旧值）
  python tools/governance/hash_registry.py --check   # 校验所有已登记哈希无漂移
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "governance" / "normative_versions" / "registry.md"

_ROW = re.compile(r"^\|(?P<cells>.*)\|\s*$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER = re.compile(r"回填|补登|待")


@dataclass
class Row:
    line_no: int
    cells: list[str]
    spec_id: str
    path_cell: str
    hash_cell: str


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


defstrip = lambda s: s.strip().strip("*").strip()  # noqa: E731


def parse_rows(text: str) -> tuple[list[str], list[Row]]:
    lines = text.splitlines()
    rows: list[Row] = []
    for i, line in enumerate(lines):
        m = _ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group("cells").split("|")]
        if len(cells) < 6 or cells[0] in {"规范编号", "---", ":---"} or set(cells[0]) <= {"-", ":"}:
            continue
        path_cell = defstrip(cells[1]).strip("`")
        if not path_cell or "/" not in path_cell and not path_cell.endswith((".md", ".txt", ".csv", ".json")):
            continue
        rows.append(Row(i, cells, defstrip(cells[0]), path_cell, cells[3]))
    return lines, rows


def target_path(row: Row) -> Path | None:
    """复合行取 '+' 之后的路径段；单文件行取整段。"""
    seg = row.path_cell.split("+")[-1].strip().strip("`")
    p = REPO_ROOT / seg
    return p if p.suffix else None


def fill(repo_rows: list[str], rows: list[Row]) -> tuple[list[str], list[str], list[str]]:
    """只填空：占位格 + 文件存在 → 写入哈希。返回 (lines, filled, problems)。"""
    filled: list[str] = []
    problems: list[str] = []
    for row in rows:
        if not _PLACEHOLDER.search(row.hash_cell):
            continue  # 已登记旧值——规则② 绝不改写
        p = target_path(row)
        if p is None or not p.is_file():
            problems.append(f"L{row.line_no+1} [{row.spec_id}] 文件缺失，无法补登: {row.path_cell}")
            continue
        digest = sha256_of(p)
        prefix = "同上 + " if "+" in row.path_cell else ""
        row.cells[3] = f"{prefix}`{digest}`"
        repo_rows[row.line_no] = "|" + "|".join(row.cells) + "|"
        filled.append(f"[{row.spec_id}] {p.relative_to(REPO_ROOT)} → {digest[:16]}…")
    return repo_rows, filled, problems


def check(rows: list[Row]) -> tuple[list[str], list[str], list[str]]:
    """核对已登记行。返回 (ok, drift, skipped)。

    追加式注册表的版本语义：同一文件可以有多行（v1.0.0、v1.1.0……），
    旧行记录"该版本曾以此哈希签署"这一不可变事实；磁盘上的文件只有一个，
    因此 --check 只对**每一路径的表内最后一行**（追加序即时间序）做漂移比对，
    更早的行标记为 archived——它们的历史哈希值永不改写（规则②）。
    """
    latest_idx: dict[Path, int] = {}
    for idx, row in enumerate(rows):
        p = target_path(row)
        if p is not None:
            latest_idx[p] = idx

    ok: list[str] = []
    drift: list[str] = []
    skipped: list[str] = []
    for idx, row in enumerate(rows):
        p = target_path(row)
        if p is not None and latest_idx[p] != idx:
            skipped.append(f"L{row.line_no+1} [{row.spec_id}] archived（已被后续版本行取代，哈希封存）")
            continue
        hexes = re.findall(r"([0-9a-f]{64})", row.hash_cell)
        if not hexes:
            skipped.append(f"L{row.line_no+1} [{row.spec_id}] 占位未登记（--fill 或治理作业补齐）")
            continue
        if p is None or not p.is_file():
            drift.append(f"L{row.line_no+1} [{row.spec_id}] 已登记但文件缺失: {row.path_cell}")
            continue
        actual = sha256_of(p)
        expected = hexes[-1]  # 复合行取最后一个 hex64
        if actual == expected:
            ok.append(f"[{row.spec_id}] match {actual[:16]}…")
        else:
            drift.append(
                f"L{row.line_no+1} [{row.spec_id}] 哈希漂移!\n"
                f"    表内: {expected}\n"
                f"    文件: {actual}  ({p.relative_to(REPO_ROOT)})"
            )
    return ok, drift, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fill", action="store_true", help="补登占位哈希（只填空）")
    g.add_argument("--check", action="store_true", help="校验已登记哈希无漂移")
    ap.add_argument("--write", action="store_true", help="与 --fill 同义（习惯用名）")
    args = ap.parse_args()

    text = REGISTRY_PATH.read_text(encoding="utf-8")
    lines, rows = parse_rows(text)
    if not rows:
        print("FATAL: registry.md 未解析出任何规范行", file=sys.stderr)
        return 2

    if args.check:
        ok, drift, skipped = check(rows)
        for s in ok:
            print(f"  OK {s}")
        for s in skipped:
            print(f"  .. {s}")
        if drift:
            print("\n".join(drift), file=sys.stderr)
            print(f"\n{len(drift)} 行哈希漂移 —— 规则③：漂移即红检", file=sys.stderr)
            return 1
        print(f"registry hash check green ({len(ok)} rows verified, {len(skipped)} placeholders)")
        return 0

    lines, filled, problems = fill(lines, rows)
    for s in filled:
        print(f"  + {s}")
    for s in problems:
        print(f"  ! {s}", file=sys.stderr)
    if filled:
        REGISTRY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"filled {len(filled)} placeholder hashes into {REGISTRY_PATH.relative_to(REPO_ROOT)}")
    else:
        print("nothing to fill")
    return 2 if problems and not filled else 0


if __name__ == "__main__":
    sys.exit(main())
