"""方向性机器阅卷运行器（裁判：DirectionalSemanticMatcher）。

用法：
    python scripts/eval_cleaning_arena.py --gen-tag agent_11
    python scripts/eval_cleaning_arena.py --all

阅卷数据源：
* agent-a9f6：题目无内嵌 GT，从 /tmp/opp/gt_agent_a9f6.jsonl 按 question_id 连接；
* 其余：题目内嵌 ground_truth_*。
"""
from __future__ import annotations

import argparse
import json
import sys
import statistics
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aios_core.simulation.cleaning_arena_protocol import (
    CleaningQuestion, CleaningAnswerSubmission, DirectionalSemanticMatcher)

SOLVER_AGENT = "01a0aa2c-fantonghui"
OPP = Path("/tmp/opp")
BANKS2 = Path("/tmp/banks")
QFILE = {
    "agent_11": OPP / "questions_agent_11.jsonl",
    "agent_a9f6": OPP / "questions_agent_a9f6.jsonl",
    "fantonghui": OPP / "questions_fantonghui.jsonl",
    "01a0a9ff-fantonghui": OPP / "questions_01a0a9ff-fantonghui.jsonl",
    "agent-01": OPP / "questions_agent-01.jsonl",
    "01a0aa2d-fantonghui": BANKS2 / "clean_a2d.jsonl",
}
GT_EXTRA = {"agent_a9f6": OPP / "gt_agent_a9f6.jsonl",
            "01a0aa2d-fantonghui": BANKS2 / "gt_clean_a2d_full.jsonl"}


def load_gt_extra(tag: str) -> dict:
    gt = {}
    p = GT_EXTRA.get(tag)
    if p and p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                g = json.loads(line)
                gt[g["question_id"]] = g
    return gt


def eval_bank(tag: str, limit: int = 0) -> dict:
    root = Path(__file__).resolve().parents[1]
    ans_path = root / "benchmarks" / "data_cleaning" / "answers" / f"ans_{SOLVER_AGENT}_on_{tag}.jsonl"
    answers = {}
    with open(ans_path, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            answers[a["question_id"]] = a
    gt_extra = load_gt_extra(tag)
    scores, dm, er, da, jp, hal = [], [], [], [], [], []
    verdicts = Counter()
    self_viol = 0
    worst: list = []
    n = 0
    with open(QFILE[tag], encoding="utf-8") as f:
        for line in f:
            qd = json.loads(line)
            qid = qd["question_id"]
            if qid not in answers:
                continue
            if tag in GT_EXTRA:
                g = gt_extra.get(qid, {})
                qd = dict(qd)
                qd["ground_truth_facts"] = g.get("ground_truth_facts", [])
                qd["ground_truth_junk_ids"] = g.get("ground_truth_junk_ids", [])
            try:
                q = CleaningQuestion.model_validate(qd)
                sub = CleaningAnswerSubmission.model_validate(answers[qid])
            except Exception as e:  # schema 违例记 0 分
                scores.append(0.0)
                worst.append((0.0, qid, f"schema_error: {e}"))
                n += 1
                continue
            rep = DirectionalSemanticMatcher.evaluate_submission(q, sub)
            scores.append(rep.final_score)
            dm.append(rep.direction_match_rate)
            er.append(rep.entity_recall_rate)
            da.append(rep.dimension_accuracy)
            jp.append(rep.junk_prune_rate)
            hal.append(rep.hallucination_count)
            verdicts[rep.verdict] += 1
            if rep.is_self_solving_violation:
                self_viol += 1
            if rep.final_score < 60.0 and len(worst) < 60:
                worst.append((rep.final_score, qid, "; ".join(rep.critique_notes[:2])))
            n += 1
            if limit and n >= limit:
                break
    def avg(x):
        return round(statistics.mean(x), 4) if x else 0.0
    report = {
        "solver_agent": SOLVER_AGENT, "generator_tag": tag, "count": n,
        "avg_final_score": avg(scores),
        "pass_rate": round(verdicts.get("PASS", 0) / max(n, 1), 4),
        "verdicts": dict(verdicts),
        "avg_direction_match": avg(dm), "avg_entity_recall": avg(er),
        "avg_dimension_accuracy": avg(da), "avg_junk_prune": avg(jp),
        "total_hallucinations": int(sum(hal)),
        "avg_hallucination": round(sum(hal) / max(n, 1), 4),
        "self_solving_violations": self_viol,
        "score_histogram": {b: sum(1 for s in scores if lo <= s < hi)
                            for b, lo, hi in [("0-60", 0, 60), ("60-80", 60, 80),
                                              ("80-90", 80, 90), ("90-100", 90, 101)]},
        "worst_cases": [{"score": s, "question_id": i, "notes": t} for s, i, t in worst[:40]],
    }
    out = root / "benchmarks" / "data_cleaning" / "reports" / f"report_{SOLVER_AGENT}_on_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-tag", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    tags = list(QFILE) if args.all else [args.gen_tag]
    for tag in tags:
        rep = eval_bank(tag, args.limit)
        print(f"[{tag}] n={rep['count']} avg={rep['avg_final_score']} pass={rep['pass_rate']} "
              f"dir={rep['avg_direction_match']} ent={rep['avg_entity_recall']} "
              f"dim={rep['avg_dimension_accuracy']} junk={rep['avg_junk_prune']} "
              f"hal_total={rep['total_hallucinations']} self_viol={rep['self_solving_violations']}")
        print(f"  hist={rep['score_histogram']}")


if __name__ == "__main__":
    main()
