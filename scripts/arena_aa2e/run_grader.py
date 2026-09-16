# -*- coding: utf-8 -*-
"""方向性机器阅卷：用主干 DirectionalSemanticMatcher 对 agent-aa2e 的 10k 答卷打分。"""
from __future__ import annotations

import collections
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "cleaning_arena_protocol", REPO / "src/aios_core/simulation/cleaning_arena_protocol.py")
proto = importlib.util.module_from_spec(spec)
sys.modules["cleaning_arena_protocol"] = proto
spec.loader.exec_module(proto)
proto.CleaningQuestion.model_rebuild(_types_namespace=vars(proto))
proto.CleaningAnswerSubmission.model_rebuild(_types_namespace=vars(proto))

QUESTIONS = REPO / "benchmarks/data_cleaning/questions/questions_fantonghui.jsonl"
ANSWERS = REPO / "benchmarks/data_cleaning/answers/ans_agent_aa2e_on_fantonghui.jsonl"
REPORT = REPO / "benchmarks/data_cleaning/reports/report_agent_aa2e_on_fantonghui.json"


def main() -> None:
    answers = {}
    with ANSWERS.open(encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            answers[a["question_id"]] = a

    agg = collections.defaultdict(float)
    n = 0
    pass_n = 0
    halluc_total = 0
    fails = []
    score_hist = collections.Counter()
    per_difficulty = collections.defaultdict(lambda: [0, 0.0])

    with QUESTIONS.open(encoding="utf-8") as f:
        for line in f:
            qd = json.loads(line)
            q = proto.CleaningQuestion.model_validate(qd)
            sub = proto.CleaningAnswerSubmission.model_validate(answers[q.question_id])
            rep = proto.DirectionalSemanticMatcher.evaluate_submission(q, sub)
            n += 1
            agg["direction_match_rate"] += rep.direction_match_rate
            agg["entity_recall_rate"] += rep.entity_recall_rate
            agg["dimension_accuracy"] += rep.dimension_accuracy
            agg["junk_prune_rate"] += rep.junk_prune_rate
            agg["final_score"] += rep.final_score
            halluc_total += rep.hallucination_count
            if rep.verdict == "PASS":
                pass_n += 1
            else:
                if len(fails) < 200:
                    fails.append({
                        "question_id": rep.question_id,
                        "difficulty": qd["difficulty"],
                        "final_score": rep.final_score,
                        "direction_match_rate": rep.direction_match_rate,
                        "entity_recall_rate": rep.entity_recall_rate,
                        "junk_prune_rate": rep.junk_prune_rate,
                        "hallucination_count": rep.hallucination_count,
                        "critique_notes": rep.critique_notes,
                    })
            score_hist[int(rep.final_score // 10) * 10] += 1
            d = per_difficulty[qd["difficulty"]]
            d[0] += 1
            d[1] += rep.final_score

    summary = {
        "solver_agent": "agent-aa2e",
        "generator_agent": "fantonghui",
        "total_questions": n,
        "pass_count": pass_n,
        "pass_rate": round(pass_n / n, 4),
        "avg_direction_match_rate": round(agg["direction_match_rate"] / n, 4),
        "avg_entity_recall_rate": round(agg["entity_recall_rate"] / n, 4),
        "avg_dimension_accuracy": round(agg["dimension_accuracy"] / n, 4),
        "avg_junk_prune_rate": round(agg["junk_prune_rate"] / n, 4),
        "avg_final_score": round(agg["final_score"] / n, 2),
        "hallucination_total": halluc_total,
        "score_histogram": dict(sorted(score_hist.items())),
        "avg_score_by_difficulty": {k: round(v[1] / v[0], 2) for k, v in per_difficulty.items()},
        "failed_samples": fails,
    }
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, v in summary.items():
        if k != "failed_samples":
            print(k, "=", v)
    print("fails listed:", len(fails), "-> report:", REPORT)


if __name__ == "__main__":
    main()
