#!/usr/bin/env python3
"""check_traceability.py —— 追溯矩阵（governance/traceability_matrix.csv）机械校验器。

M0' 冻结门第③条「traceability matrix CI 绿」的执行体；M0-023 验收锚 CONFLICT/UNMAPPED=0。

校验的是"矩阵还在不在法律里"，不是"矩阵写得好不好看"：
  1. 表头 = 冻结的 9 列；
  2. stable_key 全局唯一、格式 C\d{2}-[a-z0-9_]+、前缀覆盖全部 C01..C33（C 系列断层即红）；
  3. module 词表 = {G, C01..C16, C06b}（ADJ-010 模块表）；
  4. world_objects 每个 token 必须解析到 contracts/ 下真实类（AST 提取，不是正则幻觉）
     或运行时结构白名单（物化视图/倒排表——它们不是类但确实是合法引用）；
  5. issues = '-' 或 M[0-8]-\d{3}(~\d{3})?；scenarios = '-' / M\d闭幕实验 / V\d{1,2}(~V\d{1,2})?；
  6. acceptance 只能引用结构化锚号（A/R/V/ART/ADJ/L/G 族）或显式白名单自由词；
  7. 全文零 CONFLICT、零 UNMAPPED（M0-023 的硬判词）；
  8. V21..V45 覆盖完整（G1 中试场景带，区间形 V21~V45 展开计数，V4 归一化为 V04）。

fail-closed：任何一条破例即退出 1。无 --fix 选项——修矩阵是治理动作，不是脚本动作。
"""

from __future__ import annotations

import argparse
import ast
import csv
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = REPO_ROOT / "governance" / "traceability_matrix.csv"
CONTRACTS_DIR = REPO_ROOT / "src" / "aios_core" / "contracts"

EXPECTED_HEADER = [
    "stable_key", "clause_alias", "clause_title", "module",
    "world_objects", "issues", "scenarios", "acceptance", "notes",
]

MODULE_VOCAB = {"G", "C06b"} | {f"C{i:02d}" for i in range(1, 17)}
# 物化视图 / 倒排表 / 缓存表：合法引用但不是契约类。
RUNTIME_STRUCTS = {"ready_view", "term_postings", "entity_postings", "dependency_walk_cache"}

# 计划层对象（前向引用）：名字合法 ≠ 对象存在；它绑定到"必须把它落为契约的那个 Issue"。
# 矩阵行引用它们时，issues 列必须字面包含归属 Issue——前向引用必须带着赎它的罚单。
# 当该 Issue 落地契约类后，预期矩阵会把名字换成真实类名；本表是过渡期的守夜人名单。
PLANNED_OBJECTS: dict[str, str] = {
    "CockpitManifest": "M1-022",      # C15 K1 装配契约（M0-029 落 ManifestInstance 为快照实例；装配器本体的完整契约在 M1-022）
    "ManifestInstance": "M1-022",     # 已落地——保留以便语义同族查询（真实类名通过 classes 校验走主通道）
    "ContextSnapshot": "M2-017",      # 物化快照对象
    "Conversation": "M2-018",         # 会话流 envelope 契约
    "Watermark": "M2-019",            # 水位契约对象
    "FactorLog": "M2-016",            # 就绪因子日志对象
    "NotificationEpoch": "M2-021",    # 放音 epoch（投放语义）
    "Port": "M2-023",                 # 投放端口对象
    "AppManifest": "M6-001",          # 轻应用清单
    "CapabilityDescriptor": "M6-005", # 能力描述符
    "AmbientCanvas": "M6-005",        # 23cm 环境画布对象
    "SkillCard": "M6-005",            # 技能卡对象
}

RE_KEY = re.compile(r"^C\d{2}-[a-z0-9_]+$")
RE_ISSUE = re.compile(r"^M[0-8]-\d{3}(~\d{3})?$")
RE_SCENARIO_RANGE = re.compile(r"^V(\d{1,2})~V(\d{1,2})$")
RE_SCENARIO_ONE = re.compile(r"^V(\d{1,2})$")
RE_CLOSING = re.compile(r"^M\d闭幕实验$")
RE_WO_QUALIFIED = re.compile(r"^([A-Z][A-Za-z0-9]*)(\([A-Z_]+\))?$")
RE_ACCEPT_STRUCTURED = re.compile(r"^[A-Z][A-Za-z0-9]*([-.~][A-Za-z0-9]+)*$")
ACCEPT_FREEWORDS = {"core-thesis", "scope-boundary", "scenario-law", "edu-metrics", "veto-registry"}

MIN_ROWS = 100
V_BAND = range(21, 46)


def contract_class_names() -> set[str]:
    """AST 提取 contracts 下全部类名——矩阵引用的对象必须真实存在。"""
    names: set[str] = set()
    for py in sorted(CONTRACTS_DIR.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
    return names


def fail(msg: str, violations: list[str]) -> None:
    violations.append(msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="校验矩阵（默认动作）")
    ap.add_argument("--matrix", default=os.environ.get("TRACE_MATRIX_PATH", str(DEFAULT_MATRIX)))
    args = ap.parse_args()

    matrix = Path(args.matrix)
    violations: list[str] = []
    warnings: list[str] = []

    if not matrix.is_file():
        print(f"FATAL: 矩阵缺失 {matrix}", file=sys.stderr)
        return 2
    rows_raw = matrix.read_text(encoding="utf-8").splitlines()
    if "\r\n" in matrix.read_text(encoding="utf-8"):
        warnings.append("CRLF 行尾（冻结种子即为 CRLF，允许，不允许混排）")

    reader = csv.DictReader(matrix.open(encoding="utf-8"))
    if reader.fieldnames != EXPECTED_HEADER:
        fail(f"表头漂移: {reader.fieldnames}", violations)
    rows = list(reader)
    if len(rows) < MIN_ROWS:
        fail(f"行数 {len(rows)} < 冻结下限 {MIN_ROWS}", violations)

    classes = contract_class_names()
    if len(classes) < 10:
        fail(f"contracts 类名提取异常（{len(classes)} 个）——AST 步断", violations)

    keys: set[str] = set()
    clause_prefixes: set[str] = set()
    v_seen: set[int] = set()
    for i, r in enumerate(rows, start=2):  # 行号 1 = 表头
        key = (r.get("stable_key") or "").strip()
        if not RE_KEY.match(key):
            fail(f"L{i} stable_key 非法: {key!r}", violations)
        elif key in keys:
            fail(f"L{i} stable_key 重复: {key}", violations)
        keys.add(key)
        clause_prefixes.add(key[:3])

        modules = [m.strip() for m in (r.get("module") or "").split(";") if m.strip()]
        if not modules:
            fail(f"L{i} module 空", violations)
        for m in modules:
            if m not in MODULE_VOCAB:
                fail(f"L{i} module 越出 ADJ-010 词表: {m}", violations)

        wo = (r.get("world_objects") or "-").strip()
        if wo != "-":
            for tok in wo.split(";"):
                tok = tok.strip()
                if tok in RUNTIME_STRUCTS:
                    continue
                m = RE_WO_QUALIFIED.match(tok)
                if not m:
                    fail(f"L{i} world_object token 非法: {tok!r}", violations)
                    continue
                base = m.group(1)
                if base in classes:
                    continue
                owner = PLANNED_OBJECTS.get(base)
                if owner is None:
                    fail(f"L{i} world_object 未解析到契约类/运行时结构/计划对象: {tok}", violations)
                elif owner not in (r.get("issues") or ""):
                    fail(f"L{i} 计划对象 {base} 必须引用归属 Issue {owner}（前向引用须带赎单）", violations)

        for tok in (r.get("issues") or "-").split(";"):
            tok = tok.strip()
            if tok != "-" and not RE_ISSUE.match(tok):
                fail(f"L{i} issue 引用非法: {tok!r}", violations)

        for tok in (r.get("scenarios") or "-").split(";"):
            tok = tok.strip()
            if tok == "-" or RE_CLOSING.match(tok):
                continue
            one, rng = RE_SCENARIO_ONE.match(tok), RE_SCENARIO_RANGE.match(tok)
            if one:
                v = int(one.group(1))
                v_seen.add(v)
                if tok != f"V{v:02d}":
                    warnings.append(f"L{i} 场景写法非规范（{tok} → V{v:02d}），统计已归一化")
            elif rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if a > b:
                    fail(f"L{i} 场景区间倒置: {tok}", violations)
                v_seen.update(range(a, b + 1))
            else:
                fail(f"L{i} scenario token 非法: {tok!r}", violations)

        for tok in (r.get("acceptance") or "-").split(";"):
            tok = tok.strip()
            if tok == "-" or tok in ACCEPT_FREEWORDS:
                continue
            if not RE_ACCEPT_STRUCTURED.match(tok):
                fail(f"L{i} acceptance 锚非法: {tok!r}", violations)

        joined = "|".join((r.get(c) or "") for c in EXPECTED_HEADER)
        for bad in ("CONFLICT", "UNMAPPED"):
            if bad in joined:
                fail(f"L{i} 含 M0-023 硬判词 {bad}（要求 =0）", violations)

    missing_clauses = {f"C{i:02d}" for i in range(1, 34)} - clause_prefixes
    if missing_clauses:
        fail(f"C 系列断层: {sorted(missing_clauses)} 无任何矩阵行", violations)
    missing_v = sorted(set(V_BAND) - v_seen)
    if missing_v:
        fail(f"V21~V45 中试带覆盖缺口: {[f'V{v}' for v in missing_v]}", violations)

    for w in warnings:
        print(f"  warn: {w}")
    if violations:
        print("\n".join(f"  VIOLATION: {v}" for v in violations), file=sys.stderr)
        print(f"\ntraceability matrix RED: {len(violations)} violations", file=sys.stderr)
        return 1
    print(
        f"traceability matrix green: {len(rows)} rows, {len(keys)} keys, "
        f"C01..C33 full, V21..V45 full, CONFLICT/UNMAPPED=0"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
