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
S9  字面量提及未注册号且允许清单里没有它 ⇒ CG-3
S10 扩大哨兵区以掩盖数字回潮    ⇒ CG-5 哨兵区 >5% 全文
S11 篡改 as-built 审计工件字节  ⇒ CG-1 哈希不符（审计工件同样受清单保护）
S12 改**被测源码**但不重跑审计  ⇒ CG-1 审计溯源断裂（subject_sha256 不符）
S13 派工单注册表多声明一个不存在的交付物 ⇒ CG-6 交付物缺口棘轮被突破
S14 改 M1-001R 被测源码 ⇒ 只有该模块的审计工件失效，M1-017 的不得被牵连（expect_absent）
S15 篡改跨 ref（M5）审计探针但不重跑 ⇒ CG-1 必须照样开火
S16 被审 src 文件以相同字节落地本树 ⇒ 必须强制改走工作树双向溯源（分叉版本只记录不打红，由 S0 对照）

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


def manifest_targets() -> list[str]:
    """复制集合**从两份 SHA256SUMS 派生**，而不是手抄一份文件清单。

    手抄清单会随证据增加而漏项（本轮就漏了 as-built 审计探针与三份审计工件，
    导致对照场景 S0 因为"清单条目指向不存在的文件"而假失败）。派生 = 自维护。
    """
    out: list[str] = []
    sums = [(f"{EV_REL}/verify_reconstruction_design_SHA256SUMS", ""),
            ("governance/issue_registry/evidence/SHA256SUMS", "governance/issue_registry")]
    for rel_sums, root in sums:
        p = REPO / rel_sums
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rel = line.partition("  ")[2].strip()
            for cand in ([rel, f"{root}/{rel}"] if root else [rel]):
                if (REPO / cand).exists():
                    out.append(cand)
                    break
    return sorted(set(out))


def audit_subjects(dst: Path) -> list[str]:
    """审计工件的 `provenance.subject_under_test` 指向被测源码 ⇒ 必须一并复制，
    否则 CG-1 的双向溯源在临时树里只能报"文件不存在"，测不出真正的"源码已变更"。"""
    out = []
    for art in sorted((dst / EV_REL).glob("verify_landed_*_result.json")):
        try:
            prov = json.loads(art.read_text(encoding="utf-8")).get("provenance") or {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        subj = prov.get("subject_under_test")
        if subj and (REPO / subj).exists():
            out.append(subj)
    return sorted(set(out))


DISPATCH_REL = "governance/dispatches/TASK_DISPATCH_REGISTRY.md"


def dispatch_deliverables() -> list[str]:
    """CG-6 的输入集合 = 派工单注册表声明的交付源码。

    不复制它们，临时树里"存在的交付物"也会被判缺失（本轮 S0 因此假失败：真实缺口 2 项，
    树里报 4 项 ⇒ 棘轮被虚假突破）。与 manifest_targets() 同理：**派生，不手抄**。
    """
    import re as _re
    p = REPO / DISPATCH_REL
    if not p.exists():
        return []
    row = _re.compile(r"^\|\s*\*\*\d+号提示词\*\*\s*\|")
    path = _re.compile(r"`((?:src|tests)/[^`]+\.py)`")
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if row.match(line.strip()):
            out.extend(path.findall(line))
    return sorted({r for r in out if (REPO / r).exists()})


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
    for rel in COPY_FILES + manifest_targets() + dispatch_deliverables():
        src, out = REPO / rel, dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, out)
    for rel in audit_subjects(dst):
        src, out = REPO / rel, dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
    # 派工单注册表：CG-6 的输入（在 governance/ 下，已整棵复制；此处仅确保存在）
    disp = DISPATCH_REL
    if not (dst / disp).exists() and (REPO / disp).exists():
        (dst / disp).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / disp, dst / disp)


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


def scenario(name: str, expect: str, skip_probe: bool = True, expect_absent: str = ""):
    """expect_absent：断言失败列表里**不得**出现的片段。

    有些门的正确性不只体现为"该报的报了"，还体现为"不该报的没报"
    （S14：改了 A 模块的源码，只允许 A 的审计工件失效，B 的必须继续有效）。
    只做正向断言的话，"把所有工件都判失效"这种粗暴实现也能通过自测。
    """
    def deco(fn):
        SCENARIOS.append((name, expect, fn, skip_probe, expect_absent))
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


@scenario("S11 篡改 as-built 审计工件字节", "哈希不符")
def s11(tree: Path) -> None:
    f = tree / f"{EV_REL}/verify_landed_m1_017_cjk_1m_result.json"
    b = bytearray(f.read_bytes())
    b[-3] = (b[-3] + 1) % 256
    f.write_bytes(bytes(b))


@scenario("S12 改被测源码但不重跑审计（审计溯源断裂）", "审计溯源断裂")
def s12(tree: Path) -> None:
    """这一条是**新门的新风险**：别人修了 `cjk_inverted_index.py`（比如真的把 V3G-001 修好了），
    旧审计工件里的 442/382 ms 就不再描述当前代码。若门不拦，就会出现
    "拿着旧实测数继续下结论"——正是铁律 2 要禁止的事。"""
    f = tree / "src/aios_core/query/cjk_inverted_index.py"
    f.write_text(f.read_text(encoding="utf-8") + "\n# patched by fix\n", encoding="utf-8")


@scenario("S13 派工单多声明一个不存在的交付物（CG-6 棘轮）", "交付物缺口棘轮被突破")
def s13(tree: Path) -> None:
    f = tree / "governance/dispatches/TASK_DISPATCH_REGISTRY.md"
    t = f.read_text(encoding="utf-8")
    row = ("| **9号提示词** | `TASK_DISPATCH_AGENT_9_M9_999.md` | `M9-999` 虚构工单 | "
           "`arena/agent-09` | `src/aios_core/does_not_exist_probe.py` |\n")
    f.write_text(t.rstrip("\n") + "\n" + row, encoding="utf-8")


@scenario("S14 改 M1-001R 被测源码（多支探针须按工件各自溯源）",
          "multimodal_edge.py 已被修改",
          expect_absent="cjk_inverted_index.py 已被修改")
def s14(tree: Path) -> None:
    """这一条钉的是**我自己刚犯过的错**：CG-1 曾把所有审计工件都拿去和 M1-017 那支探针比哈希，
    于是 M1-001R 的工件被误判"溯源断裂"。修好之后必须有断言防止回潮，而且要断言两面：
    ① 改 A 模块 ⇒ A 的工件必须失效；② B 模块的工件**不得**被牵连。"""
    f = tree / "src/aios_core/ingest/multimodal_edge.py"
    f.write_text(f.read_text(encoding="utf-8") + "\n# patched by another agent\n",
                 encoding="utf-8")


@scenario("S15 篡改跨 ref 审计探针（M5）但不重跑工件",
          "跨 ref 审计探针溯源断裂")
def s15(tree: Path) -> None:
    """跨 ref 工件（被审代码在另一条 ref 上）不做工作树比对，但**探针完整性必须照样守**。
    否则改探针不重跑就能让任何结论"合法"归档——这正是 §3.7.9 里那个假 PASS 教训的门禁化。"""
    f = tree / "reviews/architecture/evidence/verify_landed_m5_batch.py"
    f.write_text(f.read_text(encoding="utf-8") + "\n# patched after artifact was produced\n",
                 encoding="utf-8")


@scenario("S16 被审 src 文件以**相同字节**落地本树（必须改走工作树双向溯源）",
          "相同字节")
def s16(tree: Path) -> None:
    """钉住跨 ref 处置的防呆：一旦**同一份字节**的被审代码落地本树，跨 ref 工件的旧数字就必须改走
    工作树双向溯源，否则会出现"用 582e187 快照的实测数描述本树代码"这种最难发现的溯源谎言。
    模拟手法：把工件记录的 subject_file_sha256 改成本树该文件的真实哈希（= 被审代码原样落地）。
    注意：这同时会触发工件自身哈希不符（S1 的判据），本场景只断言**迁移门**开火。
    反面由 S0 对照覆盖——真实树当前就是"不同字节的分叉交付"状态，那种情况**只记录不打红**，
    若 S0 出现失败即说明分叉被误判为迁移。"""
    import hashlib
    import json as _json
    art = tree / "reviews/architecture/evidence/verify_landed_m5_batch_result.json"
    data = _json.loads(art.read_text(encoding="utf-8"))
    target = "src/aios_core/cognition/self_reflection.py"
    f = tree / target
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text("# integrated into this tree\n", encoding="utf-8")
    data.setdefault("subject_file_sha256", {})[target] = hashlib.sha256(f.read_bytes()).hexdigest()
    art.write_text(_json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if not RUNNER.exists():
        print(f"FATAL: 找不到 runner {RUNNER}", file=sys.stderr)
        return 2
    root = Path("/tmp/aios_gate_selftest")
    results = []
    t_start = time.time()
    for name, expect, fn, skip, expect_absent in SCENARIOS:
        tree = root / f"case_{name.split()[0]}"
        build_tree(tree)
        fn(tree)
        args = ["--skip-probe"] if skip else ["--scale", "50k"]
        code, data = run(tree, *args)
        fails = data.get("hard_failures", [])
        absent_hit = [f for f in fails if expect_absent and expect_absent in f]
        if expect == "":
            ok = code == 0 and not fails
        else:
            ok = code == 1 and any(expect in f for f in fails) and not absent_hit
        if expect == "" and not ok:
            print("      对照场景未通过 ⇒ 临时树环境不完整，后续场景无意义，早停。")
            print("      完整失败列表：" + json.dumps(fails, ensure_ascii=False)[:800])
        results.append({"scenario": name, "expected_marker": expect or "(PASS)",
                        "expected_absent_marker": expect_absent or None,
                        "exit": code, "hard_failures": len(fails),
                        "first_failures": fails[:3], "verdict": "PASS" if ok else "FAIL"})
        verdict_txt = ("对照通过" if not expect and ok else
                       ("未按预期" if not ok else
                        f"命中「{expect}」" + (f"、且未误报「{expect_absent}」" if expect_absent else "")))
        print(f"[{'✅' if ok else '❌'}] {name}: exit={code} hard={len(fails)} {verdict_txt}")
        if absent_hit:
            print(f"      - 不该报却报了：{absent_hit[0][:160]}")
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
    print("结论：CG-1（哈希+双向溯源）/ CG-2（治理债棘轮）/ CG-3（文档↔registry）/ "
          "CG-4（探针门）/ CG-5（数字回潮+哨兵）/ CG-6（交付物缺口棘轮）**全部会开火**。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
