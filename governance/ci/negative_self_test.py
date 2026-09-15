#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`run_gates.py` 的负向自测：证明五道门**会开火**，而不是摆设（I7 反空转纪律的门版本）。

手法：把仓库的必要子树复制到临时目录（`AIOS_GATES_REPO` 指向副本），先跑一次**对照**
（必须 PASS），再逐个注入违规、每次只改一处，断言：
① 门必须以 exit 1 失败；② 失败信息必须命中预期的那条规则。
任何一个场景"注入了违规却仍然通过"⇒ 本自测失败 ⇒ 说明门是纸做的。

场景表
------
S1  篡改 1M 工件字节            ⇒ CG-1 哈希不符
S2  改探针脚本但不重跑工件      ⇒ CG-1 溯源断裂（script_sha256 不符）
S3  改 registry 里 RC-001 的 slug ⇒ CG-3 slug 不一致
S4  设计书引用不存在的 RC-099   ⇒ CG-3 引用未注册号
S5  把 baseline 的 CONFLICT 调低 ⇒ CG-2 治理债棘轮被突破
S6  哨兵区外写回旧运行值        ⇒ CG-5 数字回潮
S7  删掉 HISTORICAL 哨兵        ⇒ CG-5 缺哨兵（无法区分披露与回潮）
S8  收紧探针门限使采纳计划超门  ⇒ CG-4 探针门失败（50k 档实跑）

只用标准库。运行：`python3 governance/ci/negative_self_test.py`（约 1 分钟，含一次 50k 探针实跑）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("AIOS_GATES_REPO") or HERE.parent.parent).resolve()
RUNNER = REPO / "governance/ci/run_gates.py"
BOOK_REL = ("reviews/architecture/AIOS_Core_重构设计书_独立首席架构师版_"
            "可执行验证_2026-09-16.md")
EV_REL = "reviews/architecture/evidence"

COPY_DIRS = ["governance", ".github"]
COPY_FILES = [
    BOOK_REL,
    f"{EV_REL}/verify_reconstruction_design.py",
    f"{EV_REL}/verify_reconstruction_design_1m_result.json",
    f"{EV_REL}/verify_reconstruction_design_1m.log",
    f"{EV_REL}/verify_reconstruction_design_100k_result.json",
    f"{EV_REL}/verify_reconstruction_design_100k.log",
    f"{EV_REL}/verify_reconstruction_design_SHA256SUMS",
    "governance/issue_registry/evidence/SHA256SUMS",
]


def scope_docs() -> list[str]:
    """CG-2 要调用 registry 检查器，检查器会打开 registry.scope_docs 里的每份文档 ⇒
    临时树必须带上它们，否则对照场景会因为环境缺文件而假失败。"""
    reg = json.loads((REPO / "governance/issue_registry/v3_issue_registry.json")
                     .read_text(encoding="utf-8"))
    return list(reg.get("scope_docs", []))


def build_tree(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    for d in COPY_DIRS:
        # 整棵复制（含两个 evidence 目录与 .github/workflows）：清单里列了它们，
        # 少复制一个文件，对照场景就会假失败。只排除 __pycache__。
        shutil.copytree(REPO / d, dst / d, ignore=shutil.ignore_patterns("__pycache__"),
                        dirs_exist_ok=True)
    for rel in scope_docs():
        src, out = REPO / rel, dst / rel
        if src.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
    for rel in COPY_FILES:
        src, out = REPO / rel, dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, out)


def run(tree: Path, *extra: str) -> tuple[int, dict]:
    env = dict(os.environ, AIOS_GATES_REPO=str(tree))
    proc = subprocess.run([sys.executable, str(RUNNER), *extra, "--json",
                           "--no-provenance-write"], cwd=tree, capture_output=True,
                          text=True, env=env, timeout=1800)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"hard_failures": [], "parse_error": proc.stdout[-400:] + proc.stderr[-400:]}
    return proc.returncode, data


SCENARIOS: list[tuple[str, str, str, callable]] = []


def scenario(name: str, expect: str, skip_probe: bool = True):
    def deco(fn):
        SCENARIOS.append((name, expect, fn, skip_probe))
        return fn
    return deco


@scenario("S0 对照（不注入任何违规）", "", skip_probe=True)
def s0(tree: Path) -> None:
    return None


@scenario("S1 篡改 1M 工件字节", "哈希不符")
def s1(tree: Path) -> None:
    f = tree / f"{EV_REL}/verify_reconstruction_design_1m_result.json"
    b = bytearray(f.read_bytes())
    b[-3] = (b[-3] + 1) % 256
    f.write_bytes(bytes(b))


@scenario("S2 改探针脚本但不重跑工件（溯源断裂）", "溯源断裂")
def s2(tree: Path) -> None:
    f = tree / f"{EV_REL}/verify_reconstruction_design.py"
    f.write_text(f.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")


@scenario("S3 改 registry 中 RC-001 的 slug", "slug 不一致")
def s3(tree: Path) -> None:
    f = tree / "governance/issue_registry/v3_issue_registry.json"
    reg = json.loads(f.read_text(encoding="utf-8"))
    for i in reg["issues"]:
        if i["id"] == "RC-001":
            i["slug"] = "mod-c-responsibility-freeze-RENAMED"
    f.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


@scenario("S4 设计书引用不存在的 RC-099", "不存在的临时号")
def s4(tree: Path) -> None:
    f = tree / BOOK_REL
    f.write_text(f.read_text(encoding="utf-8") + "\n参见 **RC-099** 的要求。\n", encoding="utf-8")


@scenario("S5 把 baseline 的 CONFLICT 调低 1（棘轮）", "治理债棘轮被突破")
def s5(tree: Path) -> None:
    f = tree / "governance/ci/gate_baseline.json"
    b = json.loads(f.read_text(encoding="utf-8"))
    b["debt_baseline"]["CONFLICT"] -= 1
    f.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")


@scenario("S6 哨兵区外写回旧运行值", "数字回潮")
def s6(tree: Path) -> None:
    f = tree / BOOK_REL
    f.write_text(f.read_text(encoding="utf-8") + "\n实测遍历求值 p95 = 2181.75 ms。\n",
                 encoding="utf-8")


@scenario("S7 删掉 HISTORICAL 哨兵", "哨兵")
def s7(tree: Path) -> None:
    f = tree / BOOK_REL
    t = f.read_text(encoding="utf-8")
    t = t.replace("<!-- HISTORICAL-RUN-VALUES:BEGIN", "<!-- X:BEGIN")
    t = t.replace("<!-- HISTORICAL-RUN-VALUES:END -->", "<!-- X:END -->")
    f.write_text(t, encoding="utf-8")


@scenario("S8 收紧探针门限使采纳计划超门", "探针门失败", skip_probe=False)
def s8(tree: Path) -> None:
    f = tree / f"{EV_REL}/verify_reconstruction_design.py"
    t = f.read_text(encoding="utf-8")
    assert '"co_search_p95_ms": 50.0' in t
    f.write_text(t.replace('"co_search_p95_ms": 50.0', '"co_search_p95_ms": 0.0001', 1),
                 encoding="utf-8")


@scenario("S9 字面量提及未注册号且允许清单里没有它", "不在 baseline 的")
def s9(tree: Path) -> None:
    """允许清单不能成为后门：把未注册号藏进代码跨度里，若没登记理由仍须 fail。

    实现要点：**不依赖某个魔法号**。做法是把副本 baseline 里 `RC-098` 的允许条目删掉，
    再在书中以字面量提及它 ⇒ 触发"字面量未注册号且不在允许清单"。这样即使允许清单日后扩容，
    本场景仍然在测同一条规则，而不会因为"号被登记过了"而静默失效。
    """
    bl = tree / "governance/ci/gate_baseline.json"
    doc = json.loads(bl.read_text(encoding="utf-8"))
    doc.get("quoted_label_allowlist", {}).pop("RC-098", None)
    bl.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    f = tree / BOOK_REL
    f.write_text(f.read_text(encoding="utf-8") + "\n另见 `RC-098` 的要求。\n", encoding="utf-8")


@scenario("S10 扩大哨兵区以掩盖回潮（>5% 全文）", "哨兵区域占全文")
def s10(tree: Path) -> None:
    f = tree / BOOK_REL
    t = f.read_text(encoding="utf-8")
    # 在文中前部开一个巨大的哨兵区，把大半篇文档包进去
    marker = "<!-- HISTORICAL-RUN-VALUES:BEGIN -->\n" + ("填充内容。" * 8000) + "\n<!-- HISTORICAL-RUN-VALUES:END -->\n"
    i = t.index("## 1.1")
    f.write_text(t[:i] + marker + t[i:], encoding="utf-8")


def main() -> int:
    if not RUNNER.exists():
        print(f"FATAL: 找不到 runner {RUNNER}", file=sys.stderr)
        return 2
    root = Path("/tmp/aios_gate_selftest")
    results = []
    t_start = time.time()
    for name, expect, fn, skip in SCENARIOS:
        tree = root / f"case_{name.split()[0]}"
        build_tree(tree)
        fn(tree)
        args = ["--skip-probe"] if skip else ["--scale", "50k"]
        code, data = run(tree, *args)
        fails = data.get("hard_failures", [])
        if expect == "":
            ok = code == 0 and not fails
        else:
            ok = code == 1 and any(expect in f for f in fails)
        if expect == "" and not ok:
            print("      对照场景未通过 ⇒ 临时树环境不完整，后续场景无意义，早停。")
            print("      完整失败列表：" + json.dumps(fails, ensure_ascii=False)[:800])
        results.append({"scenario": name, "expected_marker": expect or "(PASS)",
                        "exit": code, "hard_failures": len(fails),
                        "first_failures": fails[:3], "verdict": "PASS" if ok else "FAIL"})
        print(f"[{'✅' if ok else '❌'}] {name}: exit={code} hard={len(fails)} "
              f"{'命中「' + expect + '」' if expect and ok else ('对照通过' if not expect and ok else '未按预期')}")
        for f in fails[:3]:
            print(f"      - {f[:180]}")
    wall = round(time.time() - t_start, 1)
    bad = [r for r in results if r["verdict"] != "PASS"]
    out = REPO / "governance/ci/evidence"
    out.mkdir(parents=True, exist_ok=True)
    # 文件名不带日期（容器 UTC 与仓库本地日期可能不同）；内容刻意**不含 wall 时间**，
    # 以便同一仓库状态下重复运行产出**字节相同**的工件 —— 它要进 SHA256SUMS。
    (out / "gate_runner_negative_self_test.json").write_text(
        json.dumps({"scenarios": [{k: v for k, v in r.items() if k != "first_failures"}
                                  for r in results],
                    "all_pass": not bad,
                    "runner": str(RUNNER.relative_to(REPO))},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("-" * 78)
    print(f"负向自测：{len(results)} 个场景，失败 {len(bad)} 个，wall {wall} s")
    if bad:
        print("以下场景未按预期 ⇒ 对应的门是纸做的，必须修：")
        for r in bad:
            print(f"  ✗ {r['scenario']} 期望 {r['expected_marker']} 实际 exit={r['exit']} "
                  f"hard={r['hard_failures']}")
        return 1
    print("结论：CG-1（哈希+溯源）/ CG-2（棘轮）/ CG-3（文档↔registry）/ CG-4（探针门）/ "
          "CG-5（数字回潮+哨兵）**全部会开火**。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
