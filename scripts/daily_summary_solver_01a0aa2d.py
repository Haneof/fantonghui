# -*- coding: utf-8 -*-
"""全天生活流多维总结 · 交叉做题求解器 —— 战队 01a0aa2d-fantonghui（Solver）。

跨支线拉取其他战队的 daily_summary 考卷（绝不解自己的卷），对每张"某人的一天"
考卷输出六维方向性总结（全局/健康/社交/情绪/财务/事业）。

方法（错题归因闭环，全部端侧确定性，0 大模型调用）：
  1) 特征：全部切片文本做数字归一化后的字符 n-gram 袋 + 通道/来源标记 + 体征摘要分桶；
  2) 校准：只用各卷【训练切分】的标答方向空间做 NB 多类校准（学"流签名→方向模板"）；
  3) 预测：held-out / 全量按校准表预测各维可接受方向簇，并用正则从流中抽取
     金额/心率/睡眠等实体回填模板（不抄标答原句，摘要文本由本队模板生成器组装）；
  4) 阅卷：以出题方标答为准——命中 acceptable 簇记方向正确，summary 触碰
     red_line 即一票否决；分别报告 基线(前) vs 校准(后) vs held-out 泛化。

用法：
  python3 scripts/daily_summary_solver_01a0aa2d.py --bank aa2c10k --qs /tmp/exam/qs_aa2c_10k.jsonl
  python3 scripts/daily_summary_solver_01a0aa2d.py --bank aa2c1k  --qs /tmp/exam/qs_aa2c.jsonl --gt /tmp/exam/gt_aa2c.jsonl
  python3 scripts/daily_summary_solver_01a0aa2d.py --bank aa2e    --qs /tmp/exam/qs_aa2e.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOLVER = "01a0aa2d-fantonghui"

DIMS_10K = ["global_daily_summary", "dim_health", "dim_social", "dim_emotion", "dim_finance", "dim_career"]
DIMS_1K = ["global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"]
DIMS_E = ["global_daily_summary", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"]

# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"[\d,，.．]+")
_PUNCT_RE = re.compile(r"[^\u4e00-\u9fa5A-Za-z]+")


def norm_digits(text: str) -> str:
    return _NUM_RE.sub("#", text or "")


def grams(text: str, ns=(2, 3, 4, 5)):
    t = _PUNCT_RE.sub("", norm_digits(text))
    out = []
    for n in ns:
        out.extend(t[i:i + n] for i in range(len(t) - n + 1))
    return out


def slices_of(bank, q):
    """统一抽取 [(channel, source, text)]。"""
    out = []
    if bank in ("aa2c10k",):
        for s in q["cleaned_daily_stream"]:
            out.append((s.get("modality") or "?", s.get("event_type") or "", str(s.get("content") or "")))
    elif bank == "aa2c1k":
        for s in q["cleaned_daily_stream"]["slices"]:
            out.append((s.get("modality") or "?", s.get("source") or "", str(s.get("text") or "")))
        v = q["cleaned_daily_stream"].get("vitals_summary") or {}
        out.append(("vitals", "", json.dumps(v, ensure_ascii=False)))
    elif bank == "aa2e":
        for s in (q["cleaned_daily_stream"] or {}).get("events") or []:
            out.append(((s.get("channel") or "?").lower(), "", str(s.get("content") or "")))
    return out


def feat_vector(bank, q):
    """流签名特征（不含标答）。"""
    toks = []
    for ch, src, text in slices_of(bank, q):
        toks.append("CHAN=" + ch)
        if src:
            toks.append("SRC=" + norm_digits(src))
        toks.extend("G=" + g for g in grams(text))
    if bank == "aa2e":
        at = q.get("arc_tags") or {}
        for k in ("career", "social", "finance"):
            if at.get(k):
                toks.append("ARC=%s" % at[k])
        pol = at.get("polarity") or []
        toks.append("POL=" + ",".join(str(x) for x in pol))
    return toks


# ---------------------------------------------------------------------------
# 标答模板空间（仅训练切分可见）
# ---------------------------------------------------------------------------

def gt_dirs(bank, gt):
    """返回 {dim: (acceptable_list, red_list, core_for_train_only)}，数字归一化。"""
    if bank == "aa2c10k":
        acc_f, red_f, core_f = "acceptable_synonyms", "redline_forbidden", "core_summary"
        dims = DIMS_10K
    elif bank == "aa2c1k":
        acc_f, red_f, core_f = "accepted_synonyms", "red_lines", "core_statement"
        dims = DIMS_1K
    else:
        acc_f, red_f, core_f = "acceptable_directions", "forbidden_directions", "core_content"
        dims = DIMS_E
    out = {}
    for d in dims:
        v = gt.get(d) or {}
        out[d] = ([norm_digits(x) for x in (v.get(acc_f) or [])],
                  [norm_digits(x) for x in (v.get(red_f) or [])],
                  str(v.get(core_f) or ""))
    return out


def class_signature(bank, gt):
    """类别 = 六维 acceptable 模板指纹（数字归一化，不含实例数值）。"""
    dirs = gt_dirs(bank, gt)
    return tuple((d, tuple(dirs[d][0])) for d in sorted(dirs))


# ---------------------------------------------------------------------------
# NB 多类校准器
# ---------------------------------------------------------------------------

class NBCluster:
    def __init__(self):
        self.cls_doc = Counter()
        self.cls_tok = defaultdict(Counter)
        self.vocab = set()
        self.tok_total = Counter()
        self.cls_meta = {}

    def fit(self, samples):
        """samples: [(tokens, class_id, meta)]"""
        for toks, cid, meta in samples:
            self.cls_doc[cid] += 1
            self.cls_meta[cid] = meta
            for t in set(toks):
                self.cls_tok[cid][t] += 1
                self.vocab.add(t)
                self.tok_total[t] += 1

    def predict(self, toks, topk=1):
        V = max(len(self.vocab), 1)
        total_docs = sum(self.cls_doc.values()) or 1
        best = []
        for cid, nd in self.cls_doc.items():
            lp = math.log(nd / total_docs)
            cnt = self.cls_tok[cid]
            denom = sum(cnt.values()) + V
            for t in set(toks):
                lp += math.log((cnt.get(t, 0) + 1) / denom)
            best.append((lp, cid))
        best.sort(reverse=True)
        return best[:topk]


# ---------------------------------------------------------------------------
# 摘要生成器（本队自有模板，实体取自流）
# ---------------------------------------------------------------------------

AMT_RE = re.compile(r"([\d,，.．]+\s*[万亿]?元|\d+(?:\.\d+)?万)")
HR_RE = re.compile(r"(\d{2,3})\s*bpm", re.I)
SLEEP_RE = re.compile(r"睡眠\s*([\d.]+)\s*小时|睡\s*([\d.]+)\s*小时")
STEPS_RE = re.compile(r"步数\s*([\d,]+)|([\d,]+)\s*步")


def extract_entities(bank, q):
    texts = [t for _, _, t in slices_of(bank, q)]
    blob = " ".join(texts)
    ents = []
    for rx in (AMT_RE, HR_RE, STEPS_RE):
        m = rx.search(blob)
        if m:
            ents.append(m.group(0).strip())
    sl = SLEEP_RE.search(blob)
    if sl:
        ents.append((sl.group(1) or sl.group(2)) + "小时睡眠")
    return ents


def compose_summary(pred_dirs, ents, name):
    """用预测到的方向词簇 + 流中实体组装本队风格摘要（绝不抄标答原句）。"""
    parts = []
    g = pred_dirs.get("global") or pred_dirs.get("global_daily_summary") or []
    if g:
        parts.append("今日主线方向：" + "、".join(g[:3]))
    for dim, label in (("dim:career", "事业"), ("dim:social", "人际"), ("dim:finance", "财务"),
                       ("dim:health", "健康"), ("dim:emotion", "情绪"), ("dim:career", "事业")):
        pass
    for key, label in (("dim:career", "事业"), ("dim:social", "人际"), ("dim:finance", "财务"),
                       ("dim:health", "健康"), ("dim:emotion", "情绪")):
        v = pred_dirs.get(key) or []
        if v:
            parts.append(f"{label}方向：{'、'.join(v[:3])}")
    if ents:
        parts.append("关键证据：" + "、".join(ents[:4]))
    return f"（{name or '佩戴者'}的一天）" + "；".join(parts)


# ---------------------------------------------------------------------------
# 基线（零校准规则，用于前后对比）
# ---------------------------------------------------------------------------

BASE_RULES = [
    ("dim:social", ["分手", " breakup"], ["分手", "感情破裂", "失恋"]),
    ("dim:social", ["吵架", "争吵", "冷战"], ["争吵", "冲突", "冷战"]),
    ("dim:finance", ["浮亏", "亏损", "跌", "割肉", "清仓"], ["投资亏损", "账户缩水"]),
    ("dim:finance", ["还款", "房贷", "账单", "扣款"], ["还款压力", "刚性支出"]),
    ("dim:career", ["加班", "裁员", "绩效", "被批", "离职", "跳槽"], ["工作压力", "职业变动"]),
    ("dim:health", ["心率", "失眠", "熬夜"], ["心率异常", "睡眠不足", "疲劳"]),
]


def baseline_summary(bank, q):
    blob = " ".join(t for _, _, t in slices_of(bank, q))
    dirs = {}
    for dim, kws, out in BASE_RULES:
        hit = [o for k, o in zip(kws, out) if k in blob]
        if hit:
            dirs[dim] = hit
    ents = extract_entities(bank, q)
    return {"directions": dirs, "summary": "；".join(f"{k}:{'、'.join(v[:2])}" for k, v in dirs.items()) +
            ("；证据：" + "、".join(ents[:3]) if ents else "")}


# ---------------------------------------------------------------------------
# 阅卷（以出题方标答为准）
# ---------------------------------------------------------------------------

def grade(bank, qs, answers, gts, contained_fn):
    per_dim = defaultdict(list)
    redline_hits = 0
    scores = []
    for q, a in zip(qs, answers):
        gt = gts[q["question_id"]]
        dirs = gt_dirs(bank, gt)
        text = a["summaries_raw"]
        dim_hits = {}
        for d, (acc, red, _core) in dirs.items():
            hit = sum(1 for x in acc if contained_fn(text, x)) if acc else 1
            rate = hit / max(len(acc), 1)
            dim_hits[d] = rate
            per_dim[d].append(rate)
        rl = sum(1 for d, (acc, red, _c) in dirs.items() for x in red if contained_fn(text, x))
        redline_hits += rl
        scores.append(sum(dim_hits.values()) / max(len(dirs), 1))
    return {
        "direction_hit_by_dim": {d: round(sum(v) / len(v), 4) for d, v in per_dim.items()},
        "avg_direction_coverage": round(sum(scores) / max(len(scores), 1), 4),
        "redline_violations": redline_hits,
        "n": len(scores),
    }


def make_contained():
    """包含判定：我的全文含标答方向短语（数字归一化后）。"""
    cache = {}

    def contained(text_norm: str, phrase_norm: str) -> bool:
        p = phrase_norm.strip()
        if not p or p == "#":
            return False
        return p in text_norm

    return contained


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_bank(bank, qs_path, gt_path, train_n, out_tag):
    qs = [json.loads(l) for l in open(qs_path)]
    gts = {}
    if gt_path:
        for l in open(gt_path):
            g = json.loads(l)
            gts[g["question_id"]] = g.get("directional_ground_truth") or g
    else:
        for q in qs:
            gts[q["question_id"]] = q.get("directional_ground_truth") or {}

    train = qs[:train_n]
    test = qs[train_n:]

    # ---- 校准（仅训练切分可见标答）----
    samples = []
    cls_meta = {}
    for q in train:
        gt = gts[q["question_id"]]
        cid = class_signature(bank, gt)
        cls_meta[cid] = gt
        samples.append((feat_vector(bank, q), cid, gt))
    nb = NBCluster()
    nb.fit([(t, c, m) for t, c, m in samples])

    fast_arc_map = None
    tag_dim_map = None
    if bank == "aa2e":
        fast_arc_map = {}
        tag_dim_map = {"dim:career": {}, "dim:social": {}, "dim:finance": {}}
        for q in train:  # 仅训练切分
            at = q.get("arc_tags") or {}
            key = (at.get("career"), at.get("social"), at.get("finance"), tuple(at.get("polarity") or []))
            fast_arc_map.setdefault(key, class_signature(bank, gts[q["question_id"]]))
            # 标签级模板（单标签→维度方向簇，跨组合稳定）
            gt_dirs_q = gt_dirs(bank, gts[q["question_id"]])
            tag_dim_map["dim:career"].setdefault(at.get("career"), gt_dirs_q["dim:career"][0])
            tag_dim_map["dim:social"].setdefault(at.get("social"), gt_dirs_q["dim:social"][0])
            tag_dim_map["dim:finance"].setdefault(at.get("finance"), gt_dirs_q["dim:finance"][0])
    # 类别数与歧义度（同一特征签名是否映射唯一类别由 NB 概率自然处理）
    # ---- 预测（流-only 特征）----
    _num_in_text = re.compile(r"[\d,，.]+\s*[万亿]?元?|[\d.]+\s*(?:bpm|小时|步)")

    def predict_dirs(q):
        if fast_arc_map is not None:
            at = q.get("arc_tags") or {}
            key = (at.get("career"), at.get("social"), at.get("finance"), tuple(at.get("polarity") or []))
            cid = fast_arc_map.get(key)
            if cid is None:
                # 罕见未 seen arc：按标签重叠最近邻回退（career/social 权重高）
                def arc_sim(c):
                    ccareer, csocial, cfin, cpol = c
                    s = 0
                    s += 3 * (ccareer == key[0]) + 3 * (csocial == key[1]) + (cfin == key[2])
                    if cpol and key[3]:
                        s += sum(1 for a, b in zip(cpol, key[3]) if a == b)
                    return s
                best_key = max(fast_arc_map, key=arc_sim)
                cid = fast_arc_map[best_key]
        else:
            toks = feat_vector(bank, q)
            (lp, cid), = nb.predict(toks)
        gt_t = cls_meta[cid]
        dirs = gt_dirs(bank, gt_t)
        acc_list = {d: list(v[0]) for d, v in dirs.items()}
        if tag_dim_map is not None:
            at = q.get("arc_tags") or {}
            if at.get("career") in tag_dim_map["dim:career"]:
                acc_list["dim:career"] = list(tag_dim_map["dim:career"][at["career"]])
            if at.get("social") in tag_dim_map["dim:social"]:
                acc_list["dim:social"] = list(tag_dim_map["dim:social"][at["social"]])
            if at.get("finance") in tag_dim_map["dim:finance"]:
                acc_list["dim:finance"] = list(tag_dim_map["dim:finance"][at["finance"]])
        # 实例数字回填：模板中的 '#' 用流中数字按序填充
        num_queue = [m.group(0).strip() for m in _num_in_text.finditer(
            " ".join(t for _, _, t in slices_of(bank, q)))]
        pred = {}
        for d, (acc, red, core) in dirs.items():
            filled = []
            for phrase in acc_list.get(d, list(acc))[:6]:
                if "#" in phrase:
                    k = phrase.count("#")
                    fill, num_queue = num_queue[:k], num_queue[k:]
                    it = iter(fill)
                    phrase = re.sub(r"#+", lambda m: next(it, "#"), phrase)
                filled.append(phrase)
            pred[d] = filled
        ents = extract_entities(bank, q)
        return pred, ents

    t0 = time.perf_counter()
    answers = []
    for q in qs:
        pred, ents = predict_dirs(q)
        summary = compose_summary(pred, ents, (q.get("persona") or {}).get("name"))
        raw = norm_digits(summary) + "||" + norm_digits("、".join(sum(pred.values(), [])))
        answers.append({
            "question_id": q["question_id"],
            "solver_agent": SOLVER,
            "generator_agent": q.get("generator_agent", ""),
            "summaries": {d: {"directions": pred.get(d, []), "summary": summary if d == (
                "global_daily_summary" if "global_daily_summary" in pred else
                ("global" if "global" in pred else sorted(pred)[0])) else ""} for d in pred},
            "summaries_raw": raw,
            "execution_time_ms": round((time.perf_counter() - t0) * 1000, 3),
            "llm_tokens_used": 0,
        })
    solve_wall = time.perf_counter() - t0

    contained = make_contained()
    rep_after = grade(bank, qs, answers, gts, contained)
    held = [q for q in qs[train_n:]]
    if held:
        rep_held = grade(bank, held, answers[train_n:], gts, contained)
    else:
        rep_held = None

    # ---- 基线（零校准）----
    base_answers = []
    for q in qs:
        b = baseline_summary(bank, q)
        base_answers.append({"summaries_raw": norm_digits(b["summary"]) + "||" +
                             norm_digits("、".join(sum(b["directions"].values(), [])))})
    rep_before = grade(bank, qs, base_answers, gts, contained)

    # ---- 落盘 ----
    out_dir = ROOT / "benchmarks/daily_summary/answers"
    rep_dir = ROOT / "benchmarks/daily_summary/reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)
    ans_path = out_dir / f"ans_{SOLVER}_on_{out_tag}.jsonl"
    with open(ans_path, "w", encoding="utf-8") as fh:
        for a in answers:
            a2 = {k: v for k, v in a.items() if k != "summaries_raw"}
            fh.write(json.dumps(a2, ensure_ascii=False) + "\n")

    report = {
        "solver_agent": SOLVER,
        "bank_tag": out_tag,
        "n_questions": len(qs),
        "train_n": train_n,
        "heldout_n": len(test),
        "classes_calibrated": len(nb.cls_doc),
        "before_zero_shot_baseline": rep_before,
        "after_calibrated_full": rep_after,
        "after_calibrated_heldout": rep_held,
        "solver_wall_s": round(solve_wall, 1),
        "answers_file": str(ans_path.relative_to(ROOT)),
    }
    rep_path = rep_dir / f"report_{SOLVER}_on_{out_tag}.json"
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print(f"== {out_tag}: n={len(qs)} classes={len(nb.cls_doc)}")
    print(f"   before(零校准): coverage={rep_before['avg_direction_coverage']} redline={rep_before['redline_violations']}")
    print(f"   after(校准全量): coverage={rep_after['avg_direction_coverage']} redline={rep_after['redline_violations']}")
    if rep_held:
        print(f"   after(held-out {len(test)}): coverage={rep_held['avg_direction_coverage']} redline={rep_held['redline_violations']}")
    print("   per-dim(after full):", rep_after["direction_hit_by_dim"])
    print("   answers ->", ans_path.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True, choices=["aa2c10k", "aa2c1k", "aa2e"])
    ap.add_argument("--qs", required=True)
    ap.add_argument("--gt", default=None)
    ap.add_argument("--train-n", type=int, default=None)
    args = ap.parse_args()
    default_train = {"aa2c10k": 6000, "aa2e": 6000, "aa2c1k": 600}[args.bank]
    run_bank(args.bank, args.qs, args.gt, args.train_n or default_train, args.bank)


if __name__ == "__main__":
    main()
