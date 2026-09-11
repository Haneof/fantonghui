# -*- coding: utf-8 -*-
"""policy_scan · 「没有东西是写死的」的机械执行器

指挥官纪律（2026-09-11）：本项目没有任何东西写死，哪怕标记了也可能改。
这条纪律若要成立，不能靠人自觉，只能靠两件事：
  ① 所有可调参数登记在 policies_v0.json（默认值 + 地板 + 天花板 + 谁能调 + 改了有何后果）
  ② 代码里出现"看着像策略阈值"的常量或 id 引用 → 扫描器当场拦下
本文件就是 ②。它的立场不是"数字不许出现"，而是：**数字必须有户口**。

    python3 policy_scan.py            # 人读
    python3 policy_scan.py --json     # 机器读（给 tests 与 CI）
    python3 policy_scan.py --strict    # 把 INFO 也当失败（新代码上线前用）

规则：
  RULE-1 注册表完整性：id 唯一、必填键齐、floor<=default<=ceiling、bool 型 floor=false/ceiling=true
  RULE-2 安全底线：safety_linked=true ⇒ ai_may_relax=false 且 owner 只有 user 且必须有 user_confirm
  RULE-3 留痕：owner 含 ai ⇒ audit 不得为 none（AI 每次调阈值都要能被审计与回滚）
  RULE-4 双向引用闭合：代码里引用的 policy id 必须已登记；登记的 id 若无人引用记 INFO
  RULE-5 魔法数字：服务/总线/SDK 的模块级常量名命中策略特征词（INTERVAL|TIMEOUT|WINDOW|THRESHOLD|
         BUDGET|LIMIT|MAX_|MIN_|_HZ|_MS|_S）且值为数值字面量 ⇒ 必须已登记或在 waivers 里说明理由
  RULE-6 每条旋钮必须写 rationale 与 hot_effect（否则改了不知道何时生效、为什么这么定，登记表就会烂掉）
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))                      # code/
REGISTRY = os.path.join(HERE, "policies_v0.json")
SCAN_DIRS = ["services", "bus", "aios_sdk", "aiosd", "simulator", "bench", "tests"]
HOT_EFFECTS = {"immediate",          # 改完立刻影响下一条
               "next_window",         # 下一个采样/聚合窗口起效
               "next_cycle",           # 下一次总结周期起效
               "next_tick",            # 下一次巡检 tick 起效
               "next_session",         # 下一次 AI 会话起效
               "next_adjust"}          # 下一次 AI 自调时起效（夹逼区间这类不能中途换）
ID_PREFIX = r"(?:sample|duty|safety|agg|retain|summarize|trigger|dim|privacy|budget)"
MAGIC_NAME = re.compile(r"(INTERVAL|TIMEOUT|WINDOW|THRESHOLD|BUDGET|LIMIT|CAP|SIZE|MAX_|MIN_|_HZ$|_MS$|_S$)")
REQUIRED = ("id", "cn", "unit", "default", "floor", "ceiling", "owner",
            "ai_may_relax", "safety_linked", "hot_effect", "audit", "desc", "rationale")


def load_registry(path=REGISTRY):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return doc


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_registry(doc):
    errs, warns, infos = [], [], []
    knobs = doc.get("knobs", [])
    seen = set()
    declared = set()
    for kb in knobs:
        kid = kb.get("id", "?")
        cc = kb.get("code_const")
        if cc:
            declared.add(cc.strip())
        if kid in seen:
            errs.append(f"RULE-1 id 重复：{kid}")
        seen.add(kid)
        for key in REQUIRED:
            if key not in kb:
                errs.append(f"RULE-1 {kid} 缺必填键 {key}")
        if len(str(kb.get("rationale", ""))) < 12:
            errs.append(f"RULE-6 {kid} 的 rationale 太短（为什么定这个值必须写下来）")
        if kb.get("hot_effect") not in HOT_EFFECTS:
            errs.append(f"RULE-6 {kid} hot_effect 非法：{kb.get('hot_effect')} ∈ {sorted(HOT_EFFECTS)}")
        f_, d_, c_ = kb.get("floor"), kb.get("default"), kb.get("ceiling")
        if kb.get("unit") == "bool":
            if not (f_ is False and c_ is True):
                errs.append(f"RULE-1 {kid} bool 型必须 floor=false / ceiling=true")
        elif num(f_) and num(d_) and num(c_):
            if not (f_ <= d_ <= c_):
                errs.append(f"RULE-1 {kid} 越界：floor={f_} default={d_} ceiling={c_}")
        else:
            errs.append(f"RULE-1 {kid} floor/default/ceiling 必须同为数值")
        owner = kb.get("owner", [])
        if kb.get("safety_linked"):
            if kb.get("ai_may_relax"):
                errs.append(f"RULE-2 {kid} 安全底线却 ai_may_relax=true（AI 可调安全阈值 = 违宪）")
            if owner != ["user"]:
                errs.append(f"RULE-2 {kid} 安全底线 owner 必须只有 user，当前 {owner}")
            if not kb.get("user_confirm"):
                errs.append(f"RULE-2 {kid} 安全底线必须由人显式确认（缺 user_confirm）")
        if "ai" in owner and kb.get("audit") in (None, "none"):
            errs.append(f"RULE-3 {kid} 允许 AI 自调但 audit={kb.get('audit')}（改动必须留痕可回滚）")
    return errs, warns, infos, seen, {k["id"]: k for k in knobs}, declared


def scan_sources(waives, declared):
    refs, magic = {}, []
    for d in SCAN_DIRS:
        base = os.path.join(HERE, d)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                rel = os.path.relpath(path, HERE)
                txt = open(path, encoding="utf-8").read()
                for m in re.finditer(r"[\x22\x27](" + ID_PREFIX + r"\.[a-z_0-9]+)[\x22\x27]", txt):
                    refs.setdefault(m.group(1), set()).add(rel)
                try:
                    tree = ast.parse(txt)
                except SyntaxError:
                    continue
                for node in tree.body:                       # 只看模块级
                    if not isinstance(node, ast.Assign):
                        continue
                    for tgt in node.targets:
                        if not (isinstance(tgt, ast.Name) and MAGIC_NAME.search(tgt.id)):
                            continue
                        val = node.value
                        lit = val if isinstance(val, ast.Constant) else None
                        if lit is None or not num(lit.value):
                            continue
                        if isinstance(lit.value, bool):
                            continue
                        if _waived(waives, rel, tgt.id) or _claimed(declared, f"{rel}:{tgt.id}"):
                            continue
                        magic.append((f"{rel}:{tgt.id}", lit.value))
    return refs, magic


def _claimed(declared, token):
    """旋钮用 code_const 声明"我就是这个常量的户口"：登记先于接线，接线见 NEXT_TASK 任务 J。"""
    return token in declared


def _waived(waives, rel, name):
    """waiver 形如 "bus/aios_busd.py:MAX_FRAME"：路径命中且常量名命中才算豁免（防止一条豁免吃掉整个目录）。"""
    for w in waives:
        where = str(w.get("where", ""))
        path_part, _, tok_part = where.partition(":")
        if not path_part or not tok_part:
            continue
        if (path_part in rel or rel.endswith(path_part)) and tok_part.strip() in (name, "*"):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="INFO 也算失败（新代码上线前用）")
    args = ap.parse_args()

    doc = load_registry()
    errs, warns, infos, seen_ids, by_id, declared = check_registry(doc)
    refs, magic = scan_sources(doc.get("waivers", []), declared)

    for pid, where in sorted(refs.items()):
        if pid not in seen_ids:
            errs.append(f"RULE-4 代码引用了未登记的 policy id `{pid}`（{', '.join(sorted(where))}）")
    unused = sorted(seen_ids - set(refs))
    for kid in unused:
        infos.append(f"RULE-4 旋钮 {kid} 尚无人读取（登记先于接线，属正常；接线见 NEXT_TASK 任务 J）")
    for token, val in magic:
        errs.append(f"RULE-5 魔法数字 {token} = {val}：策略性常量必须进 policies_v0.json（或在 waivers 说明为何豁免）")

    result = {"ok": not errs, "knobs": len(seen_ids), "errors": errs,
              "warnings": warns, "info": infos, "referenced_ids": sorted(refs)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"=== AIOS 参数注册表扫描（{doc['_meta']['version']}，{len(seen_ids)} 个旋钮）===")
        for e in errs:
            print(f"  ❌ {e}")
        for i in infos:
            print(f"  · {i}")
        if not errs:
            print(f"  ✓ RULE-1/2/3/4/5/6 全部通过：{len(seen_ids)} 个旋钮有户口，"
                  f"{len(refs)} 个已被代码引用，安全底线 {sum(1 for k in by_id.values() if k.get('safety_linked'))} 条 AI 无权放宽")
        if args.strict and infos:
            print(f"  （--strict：{len(infos)} 条 INFO 视为失败）")
    fail = bool(errs) or (args.strict and bool(infos))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
