# -*- coding: utf-8 -*-
"""跨 Git 交叉做题 + 方向性机器阅卷 + 错题归因 —— 战队 01a0aa2d-fantonghui（Solver）。

流程（Master Dispatch #11 第二~四阶段）：
  1) 读取对手战队题库 questions_<gen>.jsonl（跨 Git 拉取至本地）；
  2) 运行 purifier_01a0aa2d_fantonghui 执行清洗提纯，写出 ans_<solver>_on_<gen>.jsonl；
  3) 调用主干官方 DirectionalSemanticMatcher 逐题阅卷，写出 report_<solver>_on_<gen>.json；
  4) 聚合错题归因（NOISE_LEAK / ENTITY_MISSED / INTENT_DRIFT / FALSE_ALARM）。

用法：
  python3 scripts/arena_solve_grade_01a0aa2d.py --bank agent-11 [--limit 500] [--skip 6000]
      [--no-kb] [--tag heldout]
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "aios_core" / "ingest"))

from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningAnswerSubmission,
    CleaningQuestion,
    DirectionalSemanticMatcher,
    ExtractedFactSubmission,
)
from purifier_01a0aa2d_fantonghui import AiosDataPurifier, SOLVER_AGENT, load_kb  # noqa: E402

BANK_FILES = {
    "agent-11": ("questions_agent_11.jsonl", "gt_agent_11.jsonl"),
    "agent-a9f6": ("questions_agent_a9f6.jsonl", "gt_agent_a9f6.jsonl"),
    "fantonghui": ("questions_fantonghui.jsonl", "gt_fantonghui.jsonl"),
    "01a0a9ff-fantonghui": ("questions_01a0a9ff-fantonghui.jsonl", "gt_01a0a9ff-fantonghui.jsonl"),
}


def load_jsonl(path: Path, skip: int = 0, limit: int | None = None):
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < skip:
                continue
            if limit is not None and i >= skip + limit:
                break
            out.append(json.loads(line))
    return out


def grade_bank(qs, answers, gts):
    """官方方向性阅卷 + 归因聚合。"""
    rep = {
        "n": len(qs), "final_scores": [], "direction": [], "entity": [], "junk": [],
        "dimension": [], "halluc": 0, "p0_ms": [], "p0_max_ms": 0.0,
        "fail_examples": defaultdict(list), "miss_junk_samples": Counter(),
        "intent_confusion": Counter(), "dim_miss": Counter(), "halluc_by_n": Counter(),
    }
    gt_by_q = {g["question_id"]: g for g in gts} if gts else {}
    for q, ans in zip(qs, answers):
        qd = dict(q)
        if not qd.get("ground_truth_facts") and qd["question_id"] in gt_by_q:
            g = gt_by_q[qd["question_id"]]
            qd["ground_truth_facts"] = g["ground_truth_facts"]
            qd["ground_truth_junk_ids"] = g["ground_truth_junk_ids"]
        cq = CleaningQuestion.model_validate(qd)
        sub = CleaningAnswerSubmission.model_validate({
            **{k: ans[k] for k in ("question_id", "solver_agent", "generator_agent",
                                   "extracted_facts", "pruned_junk_ids",
                                   "execution_time_ms", "llm_tokens_used")},
            "extracted_facts": [
                {k: f[k] for k in ("fact_id", "dimension_id", "semantic_intent",
                                   "summary_text", "recognized_entities", "source_ref_id")}
                for f in ans["extracted_facts"]],
        })
        r = DirectionalSemanticMatcher.evaluate_submission(cq, sub)
        rep["final_scores"].append(r.final_score)
        rep["direction"].append(r.direction_match_rate)
        rep["entity"].append(r.entity_recall_rate)
        rep["junk"].append(r.junk_prune_rate)
        rep["dimension"].append(r.dimension_accuracy)
        rep["halluc"] += r.hallucination_count
        rep["halluc_by_n"][r.hallucination_count] += 1
        if ans.get("p0_bypass"):
            rep["p0_ms"].append(ans["execution_time_ms"])
            rep["p0_max_ms"] = max(rep["p0_max_ms"], ans["execution_time_ms"])
        if r.final_score < 90:
            for note in r.critique_notes:
                if note.startswith("垃圾剪枝不足"):
                    rep["fail_examples"]["NOISE_LEAK"].append((q["question_id"], note))
                    for jid in list(set(qd.get("ground_truth_junk_ids", [])) - set(ans["pruned_junk_ids"]))[:3]:
                        rep["miss_junk_samples"][jid.split("-")[0][:14]] += 1
                elif note.startswith("遗漏/偏离事实"):
                    rep["fail_examples"]["INTENT_DRIFT"].append((q["question_id"], note[:120]))
                    gt_ft = next((f for f in qd.get("ground_truth_facts", [])
                                  if f["fact_id"] in note), None)
                    gt_int = gt_ft["semantic_intent"] if gt_ft else "?"
                    gt_dim = gt_ft["dimension_id"] if gt_ft else "?"
                    my_ints = "+".join(sorted({f["semantic_intent"] for f in ans["extracted_facts"]})) or "∅"
                    my_dims = "+".join(sorted({f["dimension_id"] for f in ans["extracted_facts"]})) or "∅"
                    rep["intent_confusion"][(f"{gt_int}|{gt_dim}", f"{my_ints[:60]}|{my_dims[:30]}")] += 1
                elif "实体覆盖" in note:
                    rep["fail_examples"]["ENTITY_MISSED"].append((q["question_id"], note[:120]))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True, choices=list(BANK_FILES))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--no-kb", action="store_true", help="关闭知识库（v1 基线，用于前后对比）")
    ap.add_argument("--tag", default="full")
    args = ap.parse_args()

    qf, gtf = BANK_FILES[args.bank]
    questions = load_jsonl(ROOT / "benchmarks/data_cleaning/questions" / qf, args.skip, args.limit)
    gts = load_jsonl(ROOT / "benchmarks/data_cleaning/ground_truth" / gtf, args.skip, args.limit)
    gen_id = questions[0]["generator_agent"]

    purifier = AiosDataPurifier(use_kb=not args.no_kb)
    purifier.warmup()  # 铁律3：P0 计时不含知识库冷启动
    gc.disable()       # 铁律3：实时清洗路径禁用 GC 停顿（端侧硬实时惯例）
    t0 = time.perf_counter()
    answers = []
    for q in questions:
        answers.append(purifier.solve(q))
    wall = time.perf_counter() - t0
    gc.enable()

    answers_dir = ROOT / "benchmarks/data_cleaning/answers"
    reports_dir = ROOT / "benchmarks/data_cleaning/reports"
    answers_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    tag = f"_{args.tag}" if args.tag != "full" else ""
    ans_path = answers_dir / f"ans_{SOLVER_AGENT}_on_{gen_id}{tag}.jsonl"
    with open(ans_path, "w", encoding="utf-8") as fh:
        for a in answers:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")

    rep = grade_bank(questions, answers, gts)
    scores = rep["final_scores"]
    n = len(scores)
    summary = {
        "solver_agent": SOLVER_AGENT,
        "generator_agent": gen_id,
        "split": args.tag,
        "n_questions": n,
        "kb_enabled": not args.no_kb,
        "avg_final_score": round(sum(scores) / n, 2),
        "pass_rate": round(sum(1 for s in scores if s >= 90) / n, 4),
        "avg_direction_match": round(sum(rep["direction"]) / n, 4),
        "avg_entity_recall": round(sum(rep["entity"]) / n, 4),
        "avg_junk_prune": round(sum(rep["junk"]) / n, 4),
        "avg_dimension_accuracy": round(sum(rep["dimension"]) / n, 4),
        "total_hallucination": rep["halluc"],
        "p0_questions": len(rep["p0_ms"]),
        "p0_max_exec_ms": round(rep["p0_max_ms"], 3),
        "solver_wall_time_s": round(wall, 1),
        "error_attribution": {
            et: {"count": len(v), "rate": round(len(v) / n, 4),
                 "examples": [list(e) for e in v[:8]]}
            for et, v in rep["fail_examples"].items()},
        "intent_confusion_top": [[list(k), v] for k, v in rep["intent_confusion"].most_common(15)],
        "miss_junk_top": rep["miss_junk_samples"].most_common(10),
    }
    rep_path = reports_dir / f"report_{SOLVER_AGENT}_on_{gen_id}{tag}.json"
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)

    print(f"== {args.bank} [{args.tag}] kb={'ON' if not args.no_kb else 'OFF'} n={n} "
          f"avg={summary['avg_final_score']} pass={summary['pass_rate']:.1%} "
          f"dir={summary['avg_direction_match']} ent={summary['avg_entity_recall']} "
          f"junk={summary['avg_junk_prune']} dim={summary['avg_dimension_accuracy']} "
          f"halluc={rep['halluc']} P0max={summary['p0_max_exec_ms']}ms wall={wall:.0f}s")
    for et, v in summary["error_attribution"].items():
        print(f"   {et}: {v['count']} ({v['rate']:.1%})")
    print("   answers ->", ans_path.name, "| report ->", rep_path.name)


if __name__ == "__main__":
    main()
