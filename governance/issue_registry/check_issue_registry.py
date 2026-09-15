#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue 编号唯一真源的 CI 门（临时号 `NUMCI-001`）。

背景
----
同一 `M*-***` 号段在本仓库被 **5 套方案**重复分配给互不相同的工作
（见 `reviews/architecture/AIOS_V3_UNIFIED_BACKLOG_AND_AS_BUILT_VERIFICATION_2026-09-16.md`
§9.2 的 36 号 × 6 文档终局冲突矩阵）。其中最锋利的单点证据是：设计书 P2 用来
"检测同一编号出现两套语义即 fail" 的那个 CI Issue，自己编号为 `M0-027`，而
`M0-027` 已被 3 套语义占用 —— 用来消灭编号冲突的 Issue 本身就是编号冲突。

因此编号权必须从"文档自我宣告"移到"一个文件 + 一个检查器"：
`v3_issue_registry.json` 是唯一真源，本脚本是它的门。

五条规则
--------
A  registry 自身完整性：无重号；slug 唯一且非空；号段与里程碑前缀一致；
   冻结基线号段不得被 registry 重新分配；**alias 完整性**（A6）：别名自身不得是号、
   别名全 registry 唯一、别名必须来自临时命名空间；**A7 反虚构**：别名必须在
   `scope_docs` 中真实出现（防止登记一个没有任何文档使用过的标签）。
B  `scope_docs` 中**定义**（表格首列 / 列表项）的非基线 `M*-***` 号必须在
   registry 注册，否则记为 UNREGISTERED。
C  `open_conflicts` 中 `distinct_semantics >= 2` 且未 `RESOLVED*` 的号 ⇒ CONFLICT；
   仅单方声明的号 ⇒ UNRATIFIED（同样保持红色，直到治理方裁决注册）。
D  临时命名空间（`RC-`）完整性：条目必须有 slug（受 A2/A3 约束）、`status` 只能是
   `PROPOSAL*`、必须有 `maps_to`（非空）或 `origin=NEW_NO_PRIOR_CLAIM`、`gate` 必须属
   已知门集合、必须声明 `convergence_class`；`scope_docs` 中以表格首列**定义**的 `RC-*`
   必须已注册或已登记为某号的 alias，否则 UNREGISTERED_PROVISIONAL。
   设计意图：文档可以自带标签（RC-*）便于阅读，但**标签不等于号**——同 slug 收敛必须
   登记为 alias 而不是发新号，这样"一 slug 一号"在任何命名空间下都不被绕过。
E  `gate_disputes` 完整性：每条必须有 `raised_by/registry_gate/proposed_gate/status`，
   `status` 只能是 `OPEN` 或 `RESOLVED*`；OPEN 的争议计入红色统计（但不单独致命，
   与 CONFLICT 同级展示），确保"两份文档对同一号给出不同门"不会被静默吞掉。

退出码：0 = 全绿；1 = 存在 CONFLICT / UNREGISTERED / 规则 A 或 D 违规 / OPEN gate_dispute；
        2 = 环境或文件错误。

用法
----
    python3 governance/issue_registry/check_issue_registry.py            # 摘要
    python3 governance/issue_registry/check_issue_registry.py --verbose   # 逐条列出
    python3 governance/issue_registry/check_issue_registry.py --json      # 机器可读

只用标准库：本沙箱 `pip install` 受 PEP 668 阻断，CI 门不得依赖第三方包。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_REGISTRY = HERE / "v3_issue_registry.json"

ID_RE = re.compile(r"\bM(\d)-(\d{3})\b")
# 表格行首列 / 列表项里的号 = "定义位"；行中提及 = 仅引用，不计入规则 B。
DEF_TABLE_RE = re.compile(r"^\s*\|\s*(?:新增\s*\|\s*)?\*{0,2}(M\d-\d{3})\*{0,2}\s*\|(.*)$")
DEF_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+.*?\*{0,2}(M\d-\d{3})\*{0,2}\s*(.*)$")
ACTION_WORDS = {
    "新增", "重写", "升级", "拆分", "保留", "删除", "前移", "修订", "REWRITE", "UPGRADE",
    "KEEP", "SPLIT", "DROP", "NEW", "MOVE",
}
# 临时命名空间：文档自带标签，编号权仍在 registry（R7_provisional）。
PROVISIONAL_RE = re.compile(r"\bRC-(\d{3})\b")
DEF_PROVISIONAL_TABLE_RE = re.compile(r"^\s*\|\s*(?:新增\s*\|\s*)?\*{0,2}(RC-\d{3})\*{0,2}\s*\|(.*)$")
KNOWN_GATES = {"Gate0", "Gate0.5", "Gate1", "Gate2", "Gate2.5", "Gate3", "Gate4", "Gate5",
               "Gate4~5", "Gate3~4"}


def fail(msg: str) -> None:
    print(f"[check_issue_registry] FATAL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def expand_ranges(ranges: list[str]) -> set[str]:
    """'M0-001~M0-022' -> {'M0-001', ..., 'M0-022'}；也接受单个号。"""
    out: set[str] = set()
    for item in ranges:
        item = item.strip()
        m = re.fullmatch(r"(M\d)-(\d{3})\s*[~～-]\s*(?:(M\d)-)?(\d{3})", item)
        if m:
            prefix, lo, prefix2, hi = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
            if prefix2 and prefix2 != prefix:
                fail(f"冻结基线号段跨里程碑：{item}")
            for n in range(lo, hi + 1):
                out.add(f"{prefix}-{n:03d}")
            continue
        if ID_RE.fullmatch(item):
            out.add(item)
            continue
        fail(f"无法解析冻结基线号段：{item!r}")
    return out


def rule_a(reg: dict, baseline: set[str]) -> list[str]:
    problems: list[str] = []
    ids = [i["id"] for i in reg.get("issues", [])]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    if dupes:
        problems.append(f"A1 重号：{', '.join(dupes)}")

    slugs: dict[str, list[str]] = {}
    for it in reg.get("issues", []):
        slug = (it.get("slug") or "").strip()
        if not slug:
            problems.append(f"A2 空 slug：{it['id']}")
            continue
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            problems.append(f"A2 slug 非法（须为小写短横线式）：{it['id']} = {slug!r}")
        slugs.setdefault(slug, []).append(it["id"])
    for slug, owners in sorted(slugs.items()):
        if len(owners) > 1:
            problems.append(f"A3 一号一 slug 被违反：slug {slug!r} 同时属于 {', '.join(owners)}")

    for it in reg.get("issues", []):
        iid = it["id"]
        m = ID_RE.fullmatch(iid)
        if not m:
            continue  # 临时命名空间（NUMCI-/PROBE-）不受 M 号段约束
        if iid in baseline:
            problems.append(f"A4 registry 不得重分配冻结基线号：{iid}")
        if it.get("milestone") and it["milestone"] != f"M{m.group(1)}":
            problems.append(f"A5 里程碑前缀不一致：{iid} 标为 {it['milestone']}")

    # A6 alias 完整性：别名是"同一语义的第二个标签"，不是第二个号。
    id_set = set(ids)
    seen_alias: dict[str, str] = {}
    for it in reg.get("issues", []):
        for alias in it.get("aliases", []) or []:
            if alias in id_set:
                problems.append(f"A6 别名自身是一个已注册号：{alias}（alias of {it['id']}）")
            if alias in seen_alias:
                problems.append(
                    f"A6 别名被重复登记：{alias} 同时是 {seen_alias[alias]} 与 {it['id']} 的别名")
            seen_alias[alias] = it["id"]
            if not PROVISIONAL_RE.fullmatch(alias):
                problems.append(f"A6 别名必须来自临时命名空间（RC-***）：{alias} on {it['id']}")
    # A7 反虚构：每个 alias 必须在 scope_docs 中真实出现过（否则是凭空登记的标签）。
    if seen_alias:
        corpus = ""
        for rel in reg.get("scope_docs", []):
            path = REPO / rel
            if path.exists():
                corpus += path.read_text(encoding="utf-8")
        for alias, owner in sorted(seen_alias.items()):
            if alias not in corpus:
                problems.append(f"A7 别名在任何 scope_docs 中都不存在（虚构标签）：{alias} on {owner}")
    return problems


def rule_b(reg: dict, baseline: set[str], registered: set[str]) -> tuple[list[str], int]:
    unregistered: dict[str, set[str]] = {}
    scanned = 0
    for rel in reg.get("scope_docs", []):
        path = REPO / rel
        if not path.exists():
            fail(f"scope_docs 中的文件不存在：{rel}")
        scanned += 1
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = DEF_TABLE_RE.match(line) or DEF_LIST_RE.match(line)
            if not m:
                continue
            iid, rest = m.group(1), m.group(2)
            if iid in baseline or iid in registered:
                continue
            # 第二列若只是动作词（KEEP/REWRITE/新增…），视为裁决表而非定义位。
            cell = rest.lstrip("|").strip()
            head = re.split(r"[|：:，,]", cell, 1)[0].strip().strip("*` ")
            if head in ACTION_WORDS or len(head) < 4:
                continue
            unregistered.setdefault(iid, set()).add(f"{rel}:L{lineno}")
    items = [
        f"B {iid}：未在 registry 注册，定义位 = {', '.join(sorted(sites)[:3])}"
        for iid, sites in sorted(unregistered.items())
    ]
    return items, scanned


def rule_c(reg: dict) -> tuple[list[str], list[str]]:
    """返回 (CONFLICT 列表, UNRATIFIED 单声明者列表)。"""
    conflicts: list[str] = []
    unratified: list[str] = []
    for c in reg.get("open_conflicts", []):
        status = str(c.get("status", "")).upper()
        claims = c.get("claims", {})
        n = c.get("distinct_semantics")
        if status.startswith("RESOLVED"):
            continue
        if status == "SINGLE_CLAIM" or (isinstance(n, int) and n < 2):
            who = ", ".join(sorted(claims))
            unratified.append(f"U {c['id']}：仅 {who} 单方声明，尚无跨文档冲突，但未经治理方裁决注册")
            continue
        if not isinstance(n, int):
            conflicts.append(f"C {c['id']}：distinct_semantics 缺失，无法判定语义簇数 —— 须补填")
            continue
        detail = "; ".join(f"{k}={v}" for k, v in list(claims.items())[:6])
        conflicts.append(f"C {c['id']}：{n} 套语义未消解 —— {detail}")
    return conflicts, unratified


def rule_d(reg: dict, registered: set[str], aliases: set[str]) -> tuple[list[str], list[str], int]:
    """临时命名空间（RC-*）完整性 + scope_docs 中 RC 定义位是否已登记。"""
    problems: list[str] = []
    provisional = [i for i in reg.get("issues", []) if i.get("namespace") == "RC"]
    for it in provisional:
        rid = it["id"]
        if not PROVISIONAL_RE.fullmatch(rid):
            problems.append(f"D1 namespace=RC 但号形不合 RC-***：{rid}")
        if rid in registered and rid != it["id"]:
            problems.append(f"D1 临时号与正式号重号：{rid}")
        status = str(it.get("status", ""))
        if not status.upper().startswith("PROPOSAL"):
            problems.append(f"D2 临时号 status 必须是 PROPOSAL*：{rid} = {status!r}")
        if not (it.get("maps_to") or it.get("origin") == "NEW_NO_PRIOR_CLAIM"):
            problems.append(f"D3 临时号必须声明 maps_to 或 origin=NEW_NO_PRIOR_CLAIM：{rid}")
        if it.get("gate") not in KNOWN_GATES:
            problems.append(f"D4 临时号 gate 不属已知门集合：{rid} = {it.get('gate')!r}")
        if it.get("convergence_class") not in {"NEW_SEMANTIC_KEY", "ALIAS_OF_PRIOR_CLAIM"}:
            problems.append(f"D5 临时号缺 convergence_class：{rid}")
        if rid in registered:
            pass  # 已在 A1 覆盖重号

    unregistered: dict[str, set[str]] = {}
    for rel in reg.get("scope_docs", []):
        path = REPO / rel
        if not path.exists():
            continue  # 规则 B 已 fail，此处不重复报错
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = DEF_PROVISIONAL_TABLE_RE.match(line)
            if not m:
                continue
            rid, rest = m.group(1), m.group(2)
            if rid in registered or rid in aliases:
                continue
            cell = rest.lstrip("|").strip()
            head = re.split(r"[|：:，,]", cell, 1)[0].strip().strip("*` ")
            if head in ACTION_WORDS or len(head) < 4:
                continue
            unregistered.setdefault(rid, set()).add(f"{rel}:L{lineno}")
    items = [
        f"D6 临时号 {rid}：文档中以定义位出现但未注册/未登记 alias = {', '.join(sorted(s)[:3])}"
        for rid, s in sorted(unregistered.items())
    ]
    return problems, items, len(provisional)


def rule_e(reg: dict) -> tuple[list[str], list[str]]:
    """gate_disputes 完整性；返回 (格式违规, OPEN 争议)。"""
    problems: list[str] = []
    open_disputes: list[str] = []
    for it in reg.get("issues", []):
        for d in it.get("gate_disputes", []) or []:
            missing = [k for k in ("raised_by", "registry_gate", "proposed_gate", "status")
                       if k not in d]
            if missing:
                problems.append(f"E1 gate_dispute 缺字段 {missing}：{it['id']}")
                continue
            status = str(d["status"]).upper()
            if not (status == "OPEN" or status.startswith("RESOLVED")):
                problems.append(f"E2 gate_dispute status 非法：{it['id']} = {d['status']!r}")
            if status == "OPEN":
                open_disputes.append(
                    f"E {it['id']}：{d['raised_by']} 主张 {d['proposed_gate']}，"
                    f"registry 现为 {d['registry_gate']} —— 待裁决")
    return problems, open_disputes


def main() -> int:
    ap = argparse.ArgumentParser(description="Issue 编号 registry 的 CI 门（NUMCI-001）")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--verbose", action="store_true", help="逐条列出违规")
    ap.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = ap.parse_args()

    reg_path = Path(args.registry)
    if not reg_path.exists():
        fail(f"registry 不存在：{reg_path}")
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"registry 不是合法 JSON：{exc}")

    baseline = expand_ranges(reg.get("frozen_baseline", []))
    registered = {i["id"] for i in reg.get("issues", [])}
    aliases = {al for i in reg.get("issues", []) for al in (i.get("aliases") or [])}

    a = rule_a(reg, baseline)
    b, scanned = rule_b(reg, baseline, registered)
    c, u = rule_c(reg)
    d, d_unreg, n_provisional = rule_d(reg, registered, aliases)
    e_fmt, e_open = rule_e(reg)
    d_all = d + d_unreg + e_fmt

    result = {
        "registry": str(reg_path.relative_to(REPO)) if reg_path.is_relative_to(REPO) else str(reg_path),
        "registry_version": reg.get("registry_version"),
        "registry_status": reg.get("status"),
        "frozen_baseline_ids": len(baseline),
        "registered_ids": len(registered),
        "alias_ids": len(aliases),
        "provisional_rc_ids": n_provisional,
        "scope_docs_scanned": scanned,
        "counts": {"RULE_A": len(a), "UNREGISTERED": len(b), "CONFLICT": len(c),
                   "UNRATIFIED_SINGLE_CLAIM": len(u), "RULE_D": len(d_all),
                   "GATE_DISPUTE_OPEN": len(e_open)},
        "rule_a": a,
        "unregistered": b,
        "conflicts": c,
        "unratified_single_claim": u,
        "rule_d": d_all,
        "gate_disputes_open": e_open,
        "gate": "GREEN" if not (a or b or c or u or d_all or e_open) else "RED",
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["gate"] == "GREEN" else 1

    print("=" * 78)
    print("NUMCI-001 Issue 编号 CI 门  |  registry "
          f"{result['registry']} @ {result['registry_version']}")
    print("=" * 78)
    print(f"冻结基线号 {len(baseline)} 个；registry 已注册 {len(registered)} 个；"
          f"扫描 scope_docs {scanned} 份")
    print(f"规则 A（registry 完整性）违规 : {len(a)}")
    print(f"规则 B（UNREGISTERED 未注册号）: {len(b)}")
    print(f"规则 C（CONFLICT 未消解同号异义）: {len(c)}")
    print(f"规则 C 附（UNRATIFIED 单方声明号）  : {len(u)}")
    print(f"规则 D（临时命名空间 RC-* 完整性）: {len(d_all)}"
          f"   [RC 条目 {n_provisional} 个 / alias {len(aliases)} 个]")
    print(f"规则 E（OPEN gate 分歧待裁决）    : {len(e_open)}")
    print("-" * 78)
    print(f"GATE = {result['gate']}")
    if args.verbose:
        for section, items in (("RULE A", a), ("UNREGISTERED", b), ("CONFLICT", c),
                               ("UNRATIFIED_SINGLE_CLAIM", u), ("RULE D", d_all),
                               ("GATE_DISPUTE_OPEN", e_open)):
            if items:
                print(f"\n[{section}]")
                for it in items:
                    print(f"  - {it}")
    if result["gate"] == "RED":
        print("\n门为红色 ⇒ 按本报告 §9.3 R5：任何 M*-*** 派单一律视为无效单，"
              "直到治理方逐号裁决并写入 registry 的 resolution。")
        if e_open:
            print("另有 gate 分歧未裁决（规则 E）：同一号在两份文档中被放在不同门 ⇒ "
                  "放行顺序无法确定，必须先裁决再派单。")
    return 0 if result["gate"] == "GREEN" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CI 门必须给出可读错误而不是 traceback
        fail(f"{type(exc).__name__}: {exc}")
