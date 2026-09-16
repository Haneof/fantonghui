#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AST 检查器：`assert a, b` 中把**比较表达式**当断言消息的误用（V3G-014）。

为什么必须走 AST 而不是正则
--------------------------
`assert x == 0, y == 0` 里逗号后的表达式是**断言消息**（仅在断言失败时求值），
不是第二条断言。作者本意通常是"再核对一个来源"，结果那个核对**从未执行**，
且失败时诊断退化为 `AssertionError: False`，无法定位。

本审查方第一次用 ERE 正则扫这个模式，在 129 个文件上得到 **0 命中（假阴性）**——
连已知的唯一一处都没匹配上：ERE 括号表达式内的 `\\[` `\\]` 是**字面量反斜杠 + 括号**，
不是转义，字符类因此被写坏。教训写进设计书 §3.7.8：**语法模式检查必须走 AST**。
判据是精确的语法签名——`ast.Assert` 节点的 `msg` 是 `Compare` / `BoolOp` / `UnaryOp`，
这既不会漏（任何比较式消息都命中），也不会把正常的字符串/ f-string 消息误报。

只用标准库（本仓库 CI 门不得依赖第三方包，见 NUMCI-001）。

用法
----
    python3 governance/ci/lint_assert_msg_ast.py                  # 扫默认根，人读输出
    python3 governance/ci/lint_assert_msg_ast.py --json OUT.json  # 同时写工件
    python3 governance/ci/lint_assert_msg_ast.py --self-test      # 探测器自证（必须开火 + 不误报）

退出码：命中 > 0 ⇒ 1；无命中 ⇒ 0；`--self-test` 失败 ⇒ 2。
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import pathlib
import sys
from typing import Iterable

TOOL_VERSION = "1.0.0"
DEFAULT_ROOTS = ("tests", "src", "governance")
SKIP_PARTS = {"__pycache__", ".git", ".venv", "node_modules", "build", "dist"}
# 精确签名：断言消息本身是一个"判断"，而不是"说明"
MSG_EXPR_TYPES = (ast.Compare, ast.BoolOp, ast.UnaryOp)


def iter_python_files(roots: Iterable[str], repo: pathlib.Path) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for root in roots:
        base = repo / root
        if not base.exists():
            continue
        if base.is_file() and base.suffix == ".py":
            out.append(base)
            continue
        for path in sorted(base.rglob("*.py")):
            if SKIP_PARTS.intersection(path.parts):
                continue
            out.append(path)
    return out


def scan_source(text: str, rel: str) -> list[dict]:
    """返回命中列表；语法错误的文件单列（不得静默跳过——那会掩盖问题）。"""
    hits: list[dict] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [{
            "file": rel, "line": exc.lineno or 0, "kind": "SYNTAX_ERROR",
            "source": (exc.text or "").strip()[:200],
            "why": f"文件无法解析（{exc.msg}）⇒ 本检查器对它无覆盖，必须先修语法",
        }]
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.msg, MSG_EXPR_TYPES):
            hits.append({
                "file": rel,
                "line": node.lineno,
                "kind": "ASSERT_MSG_IS_COMPARISON",
                "source": ast.unparse(node)[:240],
                "why": ("逗号后的比较表达式是断言消息，仅在断言失败时求值 ⇒ 该核对从未执行；"
                        "失败诊断退化为 AssertionError: False/True，无法定位"),
                "fix": "拆成两条 assert；消息位改用字符串或 f-string 描述期望值",
            })
    return hits


def scan_repo(repo: pathlib.Path, roots: Iterable[str] = DEFAULT_ROOTS) -> dict:
    files = iter_python_files(roots, repo)
    all_hits: list[dict] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            all_hits.append({"file": str(path.relative_to(repo)), "line": 0,
                             "kind": "UNREADABLE", "source": "", "why": str(exc)})
            continue
        all_hits.extend(scan_source(text, str(path.relative_to(repo))))
    return {
        "tool": "governance/ci/lint_assert_msg_ast.py",
        "tool_version": TOOL_VERSION,
        "detector": "ast.Assert.msg ∈ {Compare, BoolOp, UnaryOp}",
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roots": list(roots),
        "scanned_files": len(files),
        "hit_count": len(all_hits),
        "hits": all_hits,
        "verdict": "FAIL" if all_hits else "PASS",
    }


# ---------------------------------------------------------------- 探测器自证
_BAD = 'def t(a, b):\n    assert a == 0, b == 0\n'
_BAD_BOOLOP = 'def t(a, b, c):\n    assert a, b and c\n'
_BAD_UNARY = 'def t(a, b):\n    assert a, not b\n'
_GOOD_STR = 'def t(a):\n    assert a == 0, "a 必须为 0"\n'
_GOOD_FSTRING = 'def t(a):\n    assert a == 0, f"a 实际为 {a}"\n'
_GOOD_NAME = 'def t(a, reason):\n    assert a == 0, reason\n'
_GOOD_NOMSG = 'def t(a):\n    assert a == 0\n'


def self_test() -> int:
    """探测器必须：① 对三种误用全部开火；② 对四种正常写法零误报。"""
    cases = [
        ("比较式消息（本仓库实际命中形态）", _BAD, 1),
        ("BoolOp 消息", _BAD_BOOLOP, 1),
        ("UnaryOp 消息", _BAD_UNARY, 1),
        ("字符串消息（正常）", _GOOD_STR, 0),
        ("f-string 消息（正常）", _GOOD_FSTRING, 0),
        ("Name 消息（正常，虽不理想）", _GOOD_NAME, 0),
        ("无消息（正常）", _GOOD_NOMSG, 0),
    ]
    failures = 0
    for label, src, expect in cases:
        got = len(scan_source(src, "<self-test>"))
        ok = got == expect
        failures += 0 if ok else 1
        print(f"  [{'命中' if ok else '失败'}] {label}: 期望 {expect} 实得 {got}")
    # 语法错误必须被单列上报，不得静默跳过（否则检查器"看起来通过"）
    broken = scan_source("def t(:\n  pass\n", "<broken>")
    ok = len(broken) == 1 and broken[0]["kind"] == "SYNTAX_ERROR"
    failures += 0 if ok else 1
    print(f"  [{'命中' if ok else '失败'}] 语法错误文件被上报而非静默跳过: {broken[0]['kind'] if broken else '无'}")
    print(f"探测器自证：{len(cases) + 1} 项，失败 {failures} 项 ⇒ "
          f"{'探测器可信（会开火且不误报）' if failures == 0 else '探测器不可信'}")
    return 0 if failures == 0 else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=None, help="仓库根（默认：本文件的上两级目录）")
    ap.add_argument("--roots", nargs="*", default=list(DEFAULT_ROOTS), help="扫描根（默认 tests src governance）")
    ap.add_argument("--json", default=None, help="把结果写为 JSON 工件")
    ap.add_argument("--self-test", action="store_true", help="只跑探测器自证")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    repo = pathlib.Path(args.repo) if args.repo else pathlib.Path(__file__).resolve().parents[2]
    rep = scan_repo(repo, args.roots)

    print(f"AST 检查器 v{TOOL_VERSION}：判据 {rep['detector']}")
    print(f"扫描 {rep['scanned_files']} 个 .py 文件（roots = {' '.join(rep['roots'])}）")
    print(f"命中 {rep['hit_count']} 处 ⇒ VERDICT = {rep['verdict']}")
    for hit in rep["hits"]:
        print(f"\n  {hit['file']}:{hit['line']}  [{hit['kind']}]")
        if hit["source"]:
            print(f"    {hit['source']}")
        print(f"    为什么是缺陷：{hit['why']}")
        if hit.get("fix"):
            print(f"    修法：{hit['fix']}")

    if args.json:
        out = pathlib.Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n工件已写入：{out}")
    return 1 if rep["hit_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
