#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIOS 3.0 清洗竞技场 —— 第三阶段: 方向性机器阅卷 (Judge).

用法:
    PYTHONPATH=src python3 scripts/judge_solver_on_bank.py \
        --questions benchmarks/data_cleaning/questions/questions_agent_a9f6.jsonl \
        --answers   benchmarks/data_cleaning/answers/ans_agent-01a0aa2c_on_agent-a9f6.jsonl \
        --gt-ref    origin/arena/01a0a9f6-fantonghui:benchmarks/data_cleaning/ground_truth/gt_agent_a9f6.jsonl \
        --report    benchmarks/data_cleaning/reports/report_agent-01a0aa2c_on_agent-a9f6.json

纪律:
  - 本脚本是【裁判】, 不是【做题人】. 标答 (GT) 仅用于阅卷打分,
    通过 `git show <ref>` 以流式读取, **永不落盘到工作区、永不提交**.
  - 求解器 (`purifier_agent_01a0aa2c.py`) 在任何情况下都不读取 GT.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


def stream_gt(gt_ref: str):
    """以流式从 git 对象库读取标答, 不落盘."""
    proc = subprocess.Popen(
        ["git", "show", gt_ref],
        stdout=subprocess.PIPE, text=True, bufsize=1024 * 1024,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line:
            yield json.loads(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"git show {gt_ref} failed rc={proc.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser(description="AIOS 清洗竞技场方向性阅卷")
    ap.add_argument("--questions", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--gt-ref", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--progress-every", type=int, default=2000)
    args = ap.parse_args()

    sys.path.insert(0, "src")
    from aios_core.simulation.cleaning_arena_protocol import (
        CleaningAnswerSubmission,
        CleaningQuestion,
        DirectionalSemanticMatcher,
    )

    print("[judge] loading answers...", flush=True)
    answers = {}
    with open(args.answers, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                a = json.loads(line)
                answers[a["question_id"]] = a
    print(f"[judge] answers={len(answers)}; loading questions...", flush=True)
    questions = {}
    with open(args.questions, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                q = json.loads(line)
                questions[q["question_id"]] = q
    print(f"[judge] questions={len(questions)}; streaming GT (no disk write)...", flush=True)

    n = 0
    sum_dir = sum_ent = sum_dim = sum_junk = sum_score = 0.0
    passes = fails = violations = hallucinations = 0
    by_difficulty: dict = {}
    failures: list = []
    verdicts: list = []

    for g in stream_gt(args.gt_ref):
        qid = g["question_id"]
        q = questions.get(qid)
        a = answers.get(qid)
        if q is None or a is None:
            continue
        question = CleaningQuestion.model_validate({
            **q,
            "ground_truth_facts": g["ground_truth_facts"],
            "ground_truth_junk_ids": g["ground_truth_junk_ids"],
        })
        submission = CleaningAnswerSubmission.model_validate(a)
        rep = DirectionalSemanticMatcher.evaluate_submission(question, submission)
        n += 1
        sum_dir += rep.direction_match_rate
        sum_ent += rep.entity_recall_rate
        sum_dim += rep.dimension_accuracy
        sum_junk += rep.junk_prune_rate
        sum_score += rep.final_score
        if rep.is_self_solving_violation:
            violations += 1
        if rep.verdict == "PASS":
            passes += 1
        else:
            fails += 1
            if len(failures) < 60:
                failures.append({
                    "question_id": qid,
                    "difficulty": q.get("difficulty"),
                    "final_score": rep.final_score,
                    "direction_match_rate": rep.direction_match_rate,
                    "entity_recall_rate": rep.entity_recall_rate,
                    "dimension_accuracy": rep.dimension_accuracy,
                    "junk_prune_rate": rep.junk_prune_rate,
                    "hallucination_count": rep.hallucination_count,
                    "critique_notes": rep.critique_notes,
                })
        hallucinations += rep.hallucination_count
        d = by_difficulty.setdefault(q.get("difficulty", "?"),
                                     {"n": 0, "pass": 0, "score": 0.0})
        d["n"] += 1
        d["score"] += rep.final_score
        if rep.verdict == "PASS":
            d["pass"] += 1
        verdicts.append({"question_id": qid, "verdict": rep.verdict,
                         "final_score": rep.final_score})
        if n % args.progress_every == 0:
            print(f"[judge] {n} graded, pass_rate={passes / n:.4f}", flush=True)

    for d in by_difficulty.values():
        d["avg_score"] = round(d["score"] / max(d["n"], 1), 2)
        d["pass_rate"] = round(d["pass"] / max(d["n"], 1), 4)
        del d["score"]

    report = {
        "solver_agent": "agent-01a0aa2c",
        "generator_agent": "agent-a9f6",
        "protocol": "DirectionalSemanticMatcher (方向给分, 不抠字眼)",
        "total_graded": n,
        "passes": passes,
        "fails": fails,
        "pass_rate": round(passes / max(n, 1), 4),
        "avg_final_score": round(sum_score / max(n, 1), 2),
        "avg_direction_match_rate": round(sum_dir / max(n, 1), 4),
        "avg_entity_recall_rate": round(sum_ent / max(n, 1), 4),
        "avg_dimension_accuracy": round(sum_dim / max(n, 1), 4),
        "avg_junk_prune_rate": round(sum_junk / max(n, 1), 4),
        "total_hallucinations": hallucinations,
        "self_solving_violations": violations,
        "by_difficulty": by_difficulty,
        "failure_samples": failures,
        "verdicts": verdicts,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("failure_samples", "verdicts")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
