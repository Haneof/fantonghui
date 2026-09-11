# -*- coding: utf-8 -*-
"""验收 K/T/U/V 的**机械判分器**（教学适配 · 微积分反例 + 缺曲线 + 跨域迁移 + 自注册口径） —— 见 docs/08_ACCEPTANCE_TESTS.md V0.2 §K

两个模式：
    python3 bench/check_teaching_fit.py                    # 夹具自检（不判模型，只查一致性）
    python3 bench/check_teaching_fit.py --grade <file.json> # 判候选答案 K1/K2/K4/K5/K3 + K8/K9/K10

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
FIXTURE = os.path.join(HERE, "teaching_fit_v1.jsonl")
POLICIES = os.path.join(os.path.dirname(HERE), "policies_v0.json")   # 判分口径跟着旋钮走，不写死


def load_policy_cap(knob_id="trigger.insufficient_cap"):
    """从参数注册表取置信度封顶。取不到就报错——宁可判分器不跑，也不用一个悄悄写死的默认数。"""
    try:
        with open(POLICIES, encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        raise SystemExit(f"判分器需要 {POLICIES}：{e}")
    for kb in doc.get("knobs", []):
        if kb.get("id") == knob_id:
            return float(kb["default"]), kb
    raise SystemExit(f"policies_v0.json 里找不到旋钮 {knob_id}（判分口径失去依据）")
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


def grade_case(case: dict, output: dict, spec: dict, label: str = "", cap_from_registry: float = 0.5):
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

    # ---- K8 缺曲线是一等信息（docs/11 §2）：ABSENT 不得被讲成"不会/零基础" ----
    absent = set(truth.get("absent_dims", []))
    declared = set(output.get("unknowns") or [])
    fam_kw = spec.get("family_keywords", {})
    for fam in sorted(absent):
        kw = fam_kw.get(fam, fam)
        if kw in field:
            if fam not in declared:
                v.append({"rule": "K8_未声明未知", "dim_family": fam,
                          "detail": f"文本谈到「{kw}」，但该曲线 state=ABSENT（从没测过）。"
                                     f"必须在 unknowns[] 里显式承认；把没测过当不会=最贵的一类 bug"})
            zero = [m for m in spec.get("zero_like_markers", []) if m in field]
            if zero:
                v.append({"rule": "K8_把缺数讲成差", "markers": zero,
                          "detail": "对 ABSENT 域使用了零基础/不会一类的降格表述（11 号文档明令禁止）"})
    # ---- K9 跨域迁移必须声明依据，且缺数必须降档（docs/11 §7） ----
    if truth.get("must_declare_transfer"):
        tr = output.get("transfer")
        dec = {d["dim_id"]: d for d in wm.get("declarable_dims", [])}
        if not tr:
            v.append({"rule": "K9_未声明依据",
                      "detail": "跨域教学结论没带 transfer（从哪条曲线推来的）——等于凭对话字面猜档位"})
        else:
            froms = tr.get("from_dims", []) or []
            ghost = [x.get("dim_id") for x in froms if x.get("dim_id") not in dec]
            if ghost:
                v.append({"rule": "K9_虚构依据曲线", "dims": ghost,
                          "detail": f"引用了不存在的依据；该用户可声明的曲线 = {sorted(dec)}"})
            incomplete = [x.get("dim_id") for x in froms
                          if x.get("dim_id") in dec
                          and dec[x["dim_id"]]["state"] in spec.get("bad_transfer_states", [])]
            cap = cap_from_registry
            fixture_cap = truth.get("transfer_confidence_cap_when_incomplete")
            if fixture_cap is not None and abs(float(fixture_cap) - cap) > 1e-9:
                v.append({"rule": "K9_夹具与注册表口径不一致", "fixture": fixture_cap,
                          "registry_default": cap,
                          "detail": "判分阈值改了但夹具没跟着改（或反之）——口径漂移比没判更糟"})
            if incomplete and cap is not None:
                conf = tr.get("confidence")
                if conf is None or conf > cap or not tr.get("incomplete_basis"):
                    v.append({"rule": "K9_缺数未降档", "incomplete_dims": incomplete,
                              "detail": f"依据里有 ABSENT/INSUFFICIENT/STALE 的曲线，confidence 必须 ≤{cap}"
                                        f" 且标 incomplete_basis=true（当前 {conf}）"})
    # ---- K10 AI 自注册维度：口径必须可查、换尺子必须留断点、必须可证伪（docs/11 §5） ----
    if truth.get("must_cite_rubric"):
        ref = output.get("rubric_ref")
        if not ref:
            v.append({"rule": "K10_口径未声明",
                      "detail": "情绪/压力这类 AI 自注册维度的结论未带 rubric_ref，"
                                "数字不可复核、不可跨时间比较"})
        else:
            if ref.get("rubric_version") != truth.get("expected_rubric_version"):
                v.append({"rule": "K10_版本不符", "rubric_version": ref.get("rubric_version"),
                          "expect": truth.get("expected_rubric_version")})
            if truth.get("crosses_series_break") and not ref.get("series_break_ack"):
                v.append({"rule": "K10_换尺子未打断点",
                          "detail": f"区间跨越 v{truth.get('break_version')}→v{truth.get('expected_rubric_version')} "
                                    f"口径变更却画成连续趋势：「用户变好了」可能只是换了公式"})
            if truth.get("require_falsify_clause") and not ref.get("falsify_clause"):
                v.append({"rule": "K10_不可证伪", "detail": "自注册维度必须带退出条件（用户连续否证即下线），否则是装饰品"})
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


def selfcheck(spec: dict, cases: list, cap: float = 0.5):
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
    if not spec.get("zero_like_markers"): errs.append("spec 缺 zero_like_markers（K8 无从判起）")
    if not spec.get("bad_transfer_states"): errs.append("spec 缺 bad_transfer_states（K9 无从判起）")
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
        if c.get("problem_ref") not in spec.get("task_ids", [spec.get("task_id")]):
            errs.append(f"{c['case_id']} problem_ref 不在 spec.task_ids 内")
        dec = c.get("world_model", {}).get("declarable_dims", [])
        states = set(spec.get("curve_states", []))
        for d in dec:
            if "dim_id" not in d or d.get("state") not in states:
                errs.append(f"{c['case_id']} declarable_dims 条目不合法：{d}")
        fam_of = {d["dim_id"].split("/")[2] for d in dec if d.get("dim_id", "").count("/") == 3}
        for fam in c.get("truth", {}).get("absent_dims", []):
            if fam not in fam_of:
                errs.append(f"{c['case_id']} absent_dims={fam} 没有对应的 declarable_dims 登记（夹具自相矛盾）")
        if c.get("truth", {}).get("must_declare_transfer") and not dec:
            errs.append(f"{c['case_id']} 要求声明 transfer 却没有 declarable_dims（无从判定真伪）")
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
    cap, cap_kb = load_policy_cap()
    errs = selfcheck(spec, cases, cap)
    print(f"  ✓ 判分口径来自注册表：trigger.insufficient_cap.default={cap}"
          f"（owner={cap_kb['owner']}，AI 可在 [{cap_kb['floor']}, {cap_kb['ceiling']}] 内调）")
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
        r = grade_case(by_case[cid], srec["output"], spec, srec.get("label", ""), cap)
        results.append(r)
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['case_id']}  {r['label']}  "
              f"档位命中={r['level_found']['min']}..{r['level_found']['max']}")
        for viol in r["violations"]:
            print(f"        · {viol['rule']}: {viol.get('detail', viol)}")

    # K3 差异可测：同一模型同一模板，仅世界模型不同 → 两个用户的档位必须显著分叉
    # K3 只在"同一道题、不同世界模型"之间比：跨题比较档位极差没有意义
    same_task = [c for c in cases if c.get("problem_ref") == spec.get("task_id")]
    base = {r["case_id"]: r["level_found"]["max"]
            for srec, r in zip(sub["submissions"], results) if "底座式" in srec.get("label", "")}
    on_task = {c["case_id"] for c in same_task}
    base_same = {k: v for k, v in base.items() if k in on_task}
    print("\n  --- K3 差异可测（同一道题、只换世界模型）---")
    if len(base_same) == len(on_task) and len(same_task) >= 2:
        vals = [base_same[c["case_id"]] for c in same_task]
        spread = max(vals) - min(vals)
        ok = spread >= 1
        print(f"  [{'PASS' if ok else 'FAIL'}] 各用户命中档位 = {vals}，极差 {spread}"
              f"（判据 ≥1：差异必须来自世界模型而非运气）")
        if not ok:
            errs.append("K3 差异不可测：两个用户答案同档位——底座没有产生差别")
    else:
        print(f"  SKIP 同题 case {len(same_task)} 个、已有底座式答案 {len(base_same)} 个，"
              f"K3 不判（不得以部分数据宣称通过）")
    # 结论按 expect 算：反例"被判失败"是通过，不是未通过项（旧写法把反例算成失败，逐条对、总结错）
    exp_pass = exp_pass_ok = exp_fail = exp_fail_ok = 0
    for srec, r in zip(sub["submissions"], results):
        want = srec.get("expect")
        if want not in ("pass", "fail"):
            errs.append(f"{r['case_id']}: 提交缺 expect 字段（只能是 pass/fail，不许让判分器猜 label）")
            continue
        if want == "pass":
            exp_pass += 1
            exp_pass_ok += 1 if r["ok"] else 0
            if not r["ok"]:
                errs.append(f"{r['case_id']} 底座式未通过：{[v['rule'] for v in r['violations']]}")
        else:
            exp_fail += 1
            hit = {v["rule"].split("_")[0] for v in r["violations"]}
            want_rules = set(srec.get("expect_rules") or [])
            good = (not r["ok"]) and (not want_rules or want_rules <= hit)
            exp_fail_ok += 1 if good else 0
            if not good:
                errs.append(f"{r['case_id']} 反例未按预期失败（应命中 {sorted(want_rules)}，实得 {sorted(hit)}）")
    print(f"\n  结论：底座 {exp_pass_ok}/{exp_pass} 通过 ｜ 反例 {exp_fail_ok}/{exp_fail} 按预期被判失败"
          f"（反例被抓住 = 判分器有效，不是缺陷）")
    ok = (not errs) and results and exp_pass and exp_pass_ok == exp_pass and exp_fail_ok == exp_fail
    print(("全部判据按预期收口 ✓" if ok else "存在与预期不符项 ❌（详见 errs）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
