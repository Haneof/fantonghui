"""Daily 方向性阅卷运行器。

* daily_01a0aa2d：官方裁判 DailySummaryDirectionalMatcher（vendored）。
* daily_agent-aa2e：该库未发布裁判器，采用同语义自评（键映射后走同一 matcher：
  core_content→core_plot，forbidden_directions→redline_violations，
  anchor_entities→core_anchors；权重/PASS≥80/红线否决一致）。

用法：
    python scripts/eval_daily_arena.py --gen-tag daily_01a0aa2d --questions /tmp/banks/daily_a2d.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _vendor_daily_protocol_a2d import (DailySummaryDirectionalMatcher as M,
                                        DirectionalGroundTruthAnchor)

SOLVER_AGENT = "01a0aa2c-fantonghui"
WEIGHTS = {"global_daily_summary": 0.25, "dim:health": 0.15, "dim:social": 0.15,
           "dim:emotion": 0.15, "dim:finance": 0.15, "dim:career": 0.15}
SUBKEY = {"global_daily_summary": "generated_global_summary", "dim:health": "generated_health_summary",
          "dim:social": "generated_social_summary", "dim:emotion": "generated_emotion_summary",
          "dim:finance": "generated_finance_summary", "dim:career": "generated_career_summary"}


def to_anchor(g: dict) -> DirectionalGroundTruthAnchor:
    return DirectionalGroundTruthAnchor(
        core_plot=g.get("core_plot", g.get("core_content", "")),
        core_anchors=g.get("core_anchors", g.get("anchor_entities", [])),
        acceptable_directions=g.get("acceptable_directions", []),
        redline_violations=g.get("redline_violations", g.get("forbidden_directions", [])),
        key_evidence_refs=g.get("key_evidence_refs", []),
    )


def eval_bank(tag: str, questions: Path, limit: int = 0) -> dict:
    root = Path(__file__).resolve().parents[1]
    ans_path = root / "benchmarks" / "daily_summary" / "answers" / f"ans_{SOLVER_AGENT}_on_{tag}.jsonl"
    answers = {}
    with open(ans_path, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            answers[a["question_id"]] = a
    scores, vetoes, verdicts = [], 0, Counter()
    dim_scores: dict = {d: [] for d in WEIGHTS}
    dim_dir: dict = {d: [] for d in WEIGHTS}
    worst: list = []
    n = 0
    with open(questions, encoding="utf-8") as f:
        for line in f:
            qd = json.loads(line)
            qid = qd["question_id"]
            if qid not in answers:
                continue
            if qd.get("generator_agent") == SOLVER_AGENT:
                scores.append(0.0)
                n += 1
                continue
            sub = answers[qid]
            gt = qd["directional_ground_truth"]
            total, fatal = 0.0, False
            notes = []
            for dim, w in WEIGHTS.items():
                r = M.evaluate_dimension(dim, sub.get(SUBKEY[dim], ""), to_anchor(gt[dim]))
                dim_scores[dim].append(r.score)
                dim_dir[dim].append(1.0 if r.direction_matched else 0.0)
                total += r.score * w
                if r.triggered_redline_violations:
                    fatal = True
                    notes.append(f"{dim}:RED{r.triggered_redline_violations[:2]}")
            if fatal:
                total = 0.0
                vetoes += 1
            total = round(total, 2)
            scores.append(total)
            verdicts["PASS" if (total >= 80.0 and not fatal) else "FAIL"] += 1
            if (total < 80.0 or fatal) and len(worst) < 60:
                worst.append((total, qid, "; ".join(notes[:3]) if notes else "low-score"))
            n += 1
            if limit and n >= limit:
                break
    def avg(x):
        return round(statistics.mean(x), 4) if x else 0.0
    report = {
        "solver_agent": SOLVER_AGENT, "generator_tag": tag, "count": n,
        "avg_overall": avg(scores),
        "pass_rate": round(verdicts.get("PASS", 0) / max(n, 1), 4),
        "verdicts": dict(verdicts),
        "redline_veto_papers": vetoes,
        "veto_rate": round(vetoes / max(n, 1), 4),
        "per_dim_avg": {d: avg(v) for d, v in dim_scores.items()},
        "per_dim_direction": {d: avg(v) for d, v in dim_dir.items()},
        "histogram": {b: sum(1 for s in scores if lo <= s < hi)
                      for b, lo, hi in [("0-60", 0, 60), ("60-80", 60, 80),
                                        ("80-90", 80, 90), ("90-100", 90, 101)]},
        "worst_cases": [{"score": s, "question_id": i, "notes": t} for s, i, t in worst[:40]],
    }
    out = root / "benchmarks" / "daily_summary" / "reports" / f"report_{SOLVER_AGENT}_on_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-tag", default="")
    ap.add_argument("--questions", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    rep = eval_bank(args.gen_tag, Path(args.questions), args.limit)
    print(f"[{rep['generator_tag']}] n={rep['count']} avg={rep['avg_overall']} pass={rep['pass_rate']} "
          f"vetoes={rep['redline_veto_papers']}({rep['veto_rate']})")
    print(f"  per_dim={rep['per_dim_avg']}")
    print(f"  per_dim_dir={rep['per_dim_direction']}")
    print(f"  hist={rep['histogram']}")


if __name__ == "__main__":
    main()
