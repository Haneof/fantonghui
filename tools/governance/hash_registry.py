#!/usr/bin/env python3
"""hash_registry.py —— 规范版本注册表（governance/normative_versions/registry.md）的哈希机械臂。

M0-023（V3 Authority & Traceability Freeze）声明的交付物；registry.md 表头指名依赖本工具。

两条宪法纪律的机器化：
  规则①  一行 = 一份规范的一个版本 → 本工具解析表格行，对"占位哈希格"（文字含
         "回填"/"补登"/"待"）在文件存在时补登 sha256；
  规则②  已入库的行禁止改写 → 本工具对**已含 64-hex 哈希的格绝不改写**；
         `--check` 模式下重新计算文件哈希并与表格比对，漂移即非零退出（CI 红）。

规则①②③ 联合起来会撞出一个死结（2026-09-16，两条工作线各自独立撞上）：
  规则② 要求"已入库的行禁止改写，追加新版本行代替"，但 check() 若把**每一行**的哈希
  都与**当前**文件内容比对，则一份已登记文件一旦合法演进（如 runtime_policy
  1.0.0 → 1.1.0），旧版本行就永久漂移、CI 永红；而改写旧行哈希格又被规则②明令禁止。
  **规则②给出的唯一合法出路，恰好是规则③判红的唯一形态。** 注册表原本不存在任何一条
  路径允许一份已登记文件演进。这不是实现瑕疵，是三条规则的组合缺陷 ——
  且它只会在第一次有人认真修改一份已登记文件时暴露，也就是恰好在治理开始起作用的那一刻。

本工具采用**位置语义**解决（追加序即时间序）：
  同一 (规范编号, 路径) 可以有多行；只有**该组表内最后一行**参与漂移比对，更早的行视为 archived，
  其历史哈希永久封存、绝不改写（规则②），也绝不与当前文件比对（比对本就无意义）。
  历史哈希留在表内即是审计证据（ADJ-004 版本链永存）：它记录"该版本曾以此哈希签署"，
  而不承诺"文件现在仍是这个内容"。

  另一条工作线曾独立提出**标记语义**（状态格写 HISTORICAL-ROW + 强制要求同路径存在
  CURRENT/REGISTERED 活继任者，否则判红）。两者都能解决死结，此处采纳位置语义，理由：
    · 不需要人工填写标记 —— 少一个人为字段就少一种填错的方式；
    · 不存在"豁免权"这个概念，因而不需要防滥用不变量：最后一行永远被校验，
      没有任何一行能靠自我声明退出比对；
    · 与规则①"一行 = 一份规范的一个版本"天然一致：版本顺序就是表格顺序。
  标记语义的唯一优势是显式可读，该优势已由 archived 的报告文案补足。

  但位置语义有一个必须显式限定的边界：**归组键是 (spec_id, path)，不是 path**。
  复合行（路径列含"+"）取"+"之后的路径段，于是 CONST-v3.0.1 与 ADJ-v3.0.1 会指向同一个
  裁决集文件；若按 path 归组，当前生效的宪基 CONST-v3.0.1 就会被判成"已被后续版本行取代"
  而 archived，静默移出哈希校验，且落在 skipped 桶里不判红。实测踩过，已修正并加回归。

⚠️ 位置语义引入的唯一新风险，已由 --check 显式判红：
  若某路径的**最后一行**是未补登的占位（无 64-hex），则该文件当前**不受任何哈希保护**，
  而旧行又被 archived —— 在表格末尾追加一行占位即可让任意已登记文件静默退出校验。
  因此 check() 对"最后一行是占位"判为漂移而非跳过。这是本工具最重要的防滥用不变量。

复合行（路径列含 "+"，如 CONST-v3.0.1 = 宪法原文 + 裁决集）约定：
  取 "+" 之后的路径段计算哈希；回填形态为 "同上 + `<hash>`"；
  `--check` 时取行内最后一个 hex64 与该路径段比对。

⚠️ 作业顺序陷阱（2026-09-16 实测踩中，是规则②正确行为造成的）：
  --fill 必须是**提交前的最后一步**。补登之后再修改被登记的文件会让该行哈希漂移，
  而 --fill 依规则②拒绝改写已钉住的哈希格 —— 于是陷入"改不动、又不能不绿"。
  正确顺序：(1) 改完所有已登记文件的内容；(2) 追加新版本行，哈希格写占位（如「（待回填）」）；
  (3) 最后跑 --fill，再 --check，再提交。
  若补登后又改了文件：该行**尚未提交**时恢复成占位再 --fill 即可（未入 git 的行不构成历史）；
  该行**已提交**时只能再追加一个新版本行 —— 那是规则②要的代价，不要试图绕过它。

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
        row = Row(i, cells, defstrip(cells[0]), path_cell, cells[3])
        row._raw_cells = m.group("cells").split("|")  # noqa: SLF001 - 保留原始排版
        rows.append(row)
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
        raw = row.raw_cells
        old = raw[3]
        # 保留该格原有的前导/尾随空白，使 diff 只显示"哈希格变了"，而不是整行被重排。
        # 治理表是靠 diff 审计的：一次只改一格的补登若把整行改写，评审者就无法一眼看出
        # 动了哪一格 —— 而"看不出动了哪一格"正是篡改最想要的属性。这是可审计性缺陷，
        # 不是美观问题。（2026-09-16 实测：--fill 曾把真实注册表两行压扁成无空格形态。）
        lead = old[: len(old) - len(old.lstrip())]
        trail = old[len(old.rstrip()):]
        raw[3] = f"{lead}{prefix}`{digest}`{trail}"
        row.cells[3] = f"{prefix}`{digest}`"
        repo_rows[row.line_no] = "|" + "|".join(raw) + "|"
        filled.append(f"[{row.spec_id}] {p.relative_to(REPO_ROOT)} → {digest[:16]}…")
    return repo_rows, filled, problems


def check(rows: list[Row]) -> tuple[list[str], list[str], list[str]]:
    """核对已登记行。返回 (ok, drift, skipped)。

    追加式注册表的版本语义：同一文件可以有多行（v1.0.0、v1.1.0……），
    旧行记录"该版本曾以此哈希签署"这一不可变事实；磁盘上的文件只有一个，
    因此 --check 只对**每一路径的表内最后一行**（追加序即时间序）做漂移比对，
    更早的行标记为 archived——它们的历史哈希值永不改写（规则②）。
    """
    # 版本链按 (spec_id, path) 归组，**不是**按 path。
    # 规则① 的"一份规范"= spec_id：不同 spec_id 即使指向同一文件，也是不同的规范工件，
    # 各自都必须被校验。实测反例（2026-09-16）：CONST-v3.0.1 是复合行
    # （宪法v3.0.md + 裁决集），target_path 取"+"之后的裁决集；而 ADJ-v3.0.1 也指向裁决集。
    # 若按 path 归组，CONST-v3.0.1 会被判为"已被后续版本行取代"而 archived ——
    # **当前生效的宪基被静默移出哈希校验**，且 archived 落在 skipped 桶里不判红。
    # 该文件当时仍有 ADJ-v3.0.1 兜底，所以没有真正失守；但报告是错的
    # （宪基并未被取代），而且一旦 ADJ 行被删除或调序，宪基就会无声失去保护。
    latest_idx: dict[tuple[str, Path], int] = {}
    for idx, row in enumerate(rows):
        p = target_path(row)
        if p is not None:
            latest_idx[(row.spec_id, p)] = idx

    ok: list[str] = []
    drift: list[str] = []
    skipped: list[str] = []
    for idx, row in enumerate(rows):
        p = target_path(row)
        if p is not None and latest_idx[(row.spec_id, p)] != idx:
            skipped.append(
                f"L{row.line_no+1} [{row.spec_id} {row.cells[2].strip()}] archived"
                f"（同一规范编号+路径已有更晚的版本行，本行哈希封存、不再与当前文件比对）"
            )
            continue
        hexes = re.findall(r"([0-9a-f]{64})", row.hash_cell)
        if not hexes:
            # 走到这里说明 row 是该路径的**最后一行**（更早的行已在上面 archived 掉）。
            # 末行是占位 = 该文件当前不受任何哈希保护，而旧行已封存不再比对；
            # 在表尾追加一行占位即可让任意已登记文件静默退出校验 —— 必须判红，不能跳过。
            drift.append(
                f"L{row.line_no+1} [{row.spec_id}] 该路径的最后一行仍是占位哈希："
                f"{row.path_cell} 当前不受哈希保护（更早的版本行已 archived 封存）。"
                f"请运行 --fill 补登，或删除这行占位。"
            )
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
