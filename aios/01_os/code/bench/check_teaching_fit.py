# -*- coding: utf-8 -*-
"""验收 K（教学适配 · 微积分反例）的**机械判分器** —— 见 docs/08_ACCEPTANCE_TESTS.md V0.2 §K

两个模式：
    python3 bench/check_teaching_fit.py                    # 夹具自检（不判模型，只查一致性）
    python3 bench/check_teaching_fit.py --grade <file.json> # 判候选答案 K1/K2/K4/K5/K3

设计纪律：
- 判分**零模型、零网络、零模糊匹配**：只用档位标记词表做确定性命中。文本相似度一律不用
  （本项目明令禁止用 difflib/相似度做判断，见宪法 §4 与归档区 forbidden_scan）。
- 档位阶梯（tier ladder）是判分依据：答得"对"没用，答得"高于用户已掌握档位"就是错——
  这正是宪法 §13.1「答对 ≠ 有帮助」的可执行形式。
- 判分器只判"是否合宪"，不判"教得好不好"；后者归 Evolution 的用户反馈环（K7）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "teaching_fit_v0.jsonl")
TEMPLATE = os.path.join(HERE, "template_v0.txt")

SPEC_KEYS = ("version", "acceptance", "task_id", "problem", "prompt_template_file",
             "anti_cheat", "tier_ladder", "output_contract")
CASE_KEYS = ("case_id", "user_id", "problem_ref", "world_model", "evidence_events", "truth")
WM_KEYS = ("mastered_max_level", "allowed_max_level", "mastered", "not_learned")
OUT_KEYS = ("explanation", "cited_evidence", "epistemic", "next_step")


def load_fixture(path=FIXTURE):
    spec, cases = None, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") == "spec":
                spec = rec
            elif rec.get("kind") == "case":
                cases.append(rec)
    return spec, cases


# ============================ 判分 ============================

def hit_levels(text: str, ladder):
    """返回 {level: [命中的标记词]}，只统计命中，不做任何模糊匹配。"""
    out = {}
    for rung in ladder:
        hits = [m for m in rung["markers"] if m in text]
        if hits:
            out[rung["level"]] = hits
    return out


def grade_case(case: dict, output: dict, spec: dict, label: str = ""):
    """返回一条判分结果。violation 为空 = 该条通过。"""
    ladder = spec["tier_ladder"]
    truth, wm = case["truth"], case["world_model"]
    field = output.get("explanation", "") + "\n" + output.get("next_step", "")
    hits = hit_levels(field, ladder)
    levels = sorted(hits)
    max_level = levels[-1] if levels else 0
    min_level = levels[0] if levels else 0
    v = []

    # K1 档位上限（对低档位用户不得超纲）
    cap = truth.get("expect_level_max")
    if cap is not None:
        for lv in levels:
            if lv > cap:
                name = next(r["name"] for r in ladder if r["level"] == lv)
                v.append({"rule": "K1_超纲", "level": lv, "tier": name,
                          "markers": hits[lv],
                          "detail": f"用户 allowed_max_level={wm['allowed_max_level']}，出现 {lv} 档（{name}）"})
    # K2 档位下限（对高档位用户不得重复讲解基础）
    floor = truth.get("expect_level_min")
    if floor is not None and max_level < floor:
        v.append({"rule": "K2_重复讲解", "level_found": max_level, "required_min": floor,
                  "detail": "已掌握档位之上的内容未出现，等于把已会的东西再讲一遍（无效教学）"})
    if truth.get("must_offer_extension") and not any(k in field for k in ("变式", "提升", "推广", "讨论")):
        v.append({"rule": "K2_无延伸", "detail": "高档位用户须给变式/提升，文本未见任何延伸标记"})
    # K4 证据可追：引用的证据必须真实存在于该用户世界模型
    allowed_ev = set(case.get("evidence_events", []))
    cited = list(output.get("cited_evidence", []))
    if truth.get("must_reference_evidence") and not cited:
        v.append({"rule": "K4_无证据", "detail": "教学决策未引用任何 obs_/chg_ 证据（凭对话字面猜）"})
    ghost = [e for e in cited if e not in allowed_ev]
    if ghost:
        v.append({"rule": "K4_虚构证据", "cited": ghost,
                  "detail": f"引用了不存在的证据 id；该用户可用证据 = {sorted(allowed_ev)}"})
    # K5 知识状态诚实：能力推断必须是 INFERRED，不得伪装 KNOWN
    req = truth.get("required_epistemic")
    got = output.get("epistemic")
    if got not in spec["output_contract"]["epistemic_enum"]:
        v.append({"rule": "K5_非法知识状态", "epistemic": got, "expect": "closed set 之内"})
    elif req and got != req:
        v.append({"rule": "K5_冒充事实", "epistemic": got, "expect": req,
                  "detail": "能力档位属推断结论，标 KNOWN 即把推断当事实（违反三树隔离）"})

    return {"case_id": case["case_id"], "user_id": case["user_id"], "label": label,
            "level_found": {"min": min_level, "max": max_level,
                            "tiers": {str(l): hits[l] for l in levels}},
            "ok": not v, "violations": v}


def check_template_anti_cheat(spec: dict):
    """反作弊：两个用户必须共用同一模板，模板内禁止出现用户分支。"""
    errs = []
    if not os.path.exists(TEMPLATE):
        return [f"缺模板文件 {TEMPLATE}"]
    txt = open(TEMPLATE, encoding="utf-8").read()
    for tok in spec["anti_cheat"]["forbidden_tokens"]:
        if tok in txt:
            errs.append(f"模板内出现用户分支 token `{tok}` —— 超纲若来自硬编码而非底座，K 无效")
    for ph in ("{problem}", "{world_model}", "{evidence}"):
        if ph not in txt:
            errs.append(f"模板缺占位符 {ph}（世界模型必须由底座注入，不得写死）")
    return errs


def selfcheck(spec: dict, cases: list):
    errs = []
    if spec is None:
        return ["夹具缺 spec 行"]
    for k in SPEC_KEYS:
        if k not in spec:
            errs.append(f"spec 缺字段 {k}")
    lv = [r["level"] for r in spec.get("tier_ladder", [])]
    if lv != list(range(len(lv))):
        errs.append(f"tier_ladder 层级必须从 0 连续：{lv}")
    seen = {}
    for r in spec.get("tier_ladder", []):
        if not r.get("markers"):
            errs.append(f"层级 {r['level']} 标记词表为空（无法机械判分）")
        for m in r.get("markers", []):
            if m in seen:
                errs.append(f"标记词 `{m}` 同时属于 {seen[m]} 档与 {r['level']} 档（判分会自相矛盾）")
            seen[m] = r["level"]
    ids = [c["case_id"] for c in cases]
    if len(ids) != len(set(ids)):
        errs.append("case_id 重复")
    for c in cases:
        for k in CASE_KEYS:
            if k not in c:
                errs.append(f"{c.get('case_id')} 缺字段 {k}")
        for k in WM_KEYS:
            if k not in c.get("world_model", {}):
                errs.append(f"{c['case_id']} world_model 缺 {k}")
        for k in ("expect_level_max", "expect_level_min"):
            val = c.get("truth", {}).get(k)
            if val is not None and not (0 <= val <= max(lv)):
                errs.append(f"{c['case_id']} truth.{k}={val} 越出档位阶梯 0..{max(lv)}")
        if not c.get("evidence_events"):
            errs.append(f"{c['case_id']} 无 evidence_events（K4 无从判起）")
        if c.get("problem_ref") != spec.get("task_id"):
            errs.append(f"{c['case_id']} problem_ref 与 spec.task_id 不一致")
    if len({c["user_id"] for c in cases}) != len(cases):
        errs.append("不同 case 必须对应不同世界模型（K3 差异可测的前提）")
    errs += check_template_anti_cheat(spec)
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grade", metavar="FILE", help="候选答案文件（含 submissions[]）")
    ap.add_argument("--fixture", default=FIXTURE)
    args = ap.parse_args()

    spec, cases = load_fixture(args.fixture)
    errs = selfcheck(spec, cases)
    print(f"=== 验收 K 夹具自检（{len(cases)} 个世界模型）===")
    for e in errs:
        print(f"  ❌ {e}")
    if not errs:
        print(f"  ✓ spec/case/档位词表/模板反作弊 全部一致（version={spec['version']}）")
    if not args.grade:
        print("\n提示：--grade <file.json> 判候选答案。当前无候选 → 不判分（不得把自检当作 K 通过）")
        return 1 if errs else 0

    sub = json.load(open(args.grade, encoding="utf-8"))
    by_case = {c["case_id"]: c for c in cases}
    results = []
    print(f"\n=== 判分：{os.path.basename(args.grade)} ===")
    for srec in sub["submissions"]:
        cid = srec["case_id"]
        if cid not in by_case:
            print(f"  ❌ {cid} 不在夹具内"); errs.append(f"未知 case {cid}"); continue
        for k in OUT_KEYS:
            if k not in srec["output"]:
                print(f"  ❌ {cid} 输出缺字段 {k}（不合 §5.4 结构化产出契约）")
        r = grade_case(by_case[cid], srec["output"], spec, srec.get("label", ""))
        results.append(r)
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['case_id']}  {r['label']}  "
              f"档位命中={r['level_found']['min']}..{r['level_found']['max']}")
        for viol in r["violations"]:
            print(f"        · {viol['rule']}: {viol.get('detail', viol)}")

    # K3 差异可测：同一模型同一模板，仅世界模型不同 → 两个用户的档位必须显著分叉
    base = {}
    for srec, r in zip([x for x in sub["submissions"]], results):
        if "底座式" in srec.get("label", ""):
            base[srec["case_id"]] = r["level_found"]["max"]
    print("\n  --- K3 差异可测（底座是否真的在起作用）---")
    if len(base) == len(cases) and len(cases) >= 2:
        vals = [base[c["case_id"]] for c in cases]
        spread = max(vals) - min(vals)
        ok = spread >= 1
        print(f"  [{'PASS' if ok else 'FAIL'}] 各用户命中档位 = {vals}，极差 {spread}"
              f"（判据 ≥1：差异必须来自世界模型而非运气）")
        if not ok:
            errs.append("K3 差异不可测：两个用户答案同档位——底座没有产生差别")
    else:
        print(f"  SKIP 仅 {len(base)}/{len(cases)} 个 case 有『底座式』答案，K3 不判（不得以部分数据宣称通过）")
    print("\n" + ("全部判据通过 ✓" if not errs and all(r['ok'] for r in results) else "存在未通过项 ❌"))
    return 0 if (not errs and results and all(r["ok"] for r in results)) else 1


if __name__ == "__main__":
    sys.exit(main())
