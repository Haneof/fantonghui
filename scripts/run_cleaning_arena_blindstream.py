"""AIOS 3.0 数据清洗竞技场——跨 Git 交叉做题一键运行器（做题战队 01a0aa2c-fantonghui）。

执行 Master Dispatch #11 第二/三/四阶段的完整闭环：

1. **做题**：``BlindStreamPurifier`` 接管底座清洗对手盲卷（10,000 题），
   答卷落盘 ``benchmarks/data_cleaning/answers/ans_<solver>_on_<gen>.jsonl``；
2. **阅卷**：合并出题方独立落盘的标答（``ground_truth/gt_<gen>.jsonl``），
   用主干 ``DirectionalSemanticMatcher`` 方向性机器阅卷（方向对即给分）；
3. **归因取证**：失败样本按 NOISE_LEAK / ENTITY_MISSED / INTENT_DRIFT /
   FALSE_ALARM / DIMENSION_MISMATCH / FACT_MISS 分桶落盘，供错题归因进化。

用法（在仓库根目录）::

    PYTHONPATH=src python scripts/run_cleaning_arena_solver.py \
        --questions benchmarks/data_cleaning/questions/questions_agent_a9f6.jsonl \
        --ground-truth benchmarks/data_cleaning/ground_truth/gt_agent_a9f6.jsonl \
        --label v1

本脚本不写任何断言；验收判据在 ``tests/``，这里只负责取证与排版。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aios_core.ingest.purifier_01a0aa2c_fantonghui_blindstream import (
    P0_BYPASS_BUDGET_MS,
    SOLVER_AGENT_ID,
    BlindStreamPurifier,
)
from aios_core.simulation.cleaning_arena_protocol import (
    CleaningAnswerSubmission,
    CleaningQuestion,
    DirectionalScoringReport,
    DirectionalSemanticFact,
    DirectionalSemanticMatcher,
    ExtractedFactSubmission,
)

UTC = timezone.utc


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _to_models(
    question: Dict[str, Any], gt: Dict[str, Any], answer: Dict[str, Any]
) -> tuple[CleaningQuestion, CleaningAnswerSubmission]:
    merged = dict(question)
    merged["ground_truth_facts"] = [
        DirectionalSemanticFact(**f) for f in gt.get("ground_truth_facts", [])
    ]
    merged["ground_truth_junk_ids"] = list(gt.get("ground_truth_junk_ids", []))
    cq = CleaningQuestion(**merged)
    sub = CleaningAnswerSubmission(
        question_id=answer["question_id"],
        solver_agent=answer["solver_agent"],
        generator_agent=answer["generator_agent"],
        extracted_facts=[
            ExtractedFactSubmission(**f) for f in answer.get("extracted_facts", [])
        ],
        pruned_junk_ids=list(answer.get("pruned_junk_ids", [])),
        execution_time_ms=float(answer.get("execution_time_ms", 0.0)),
        llm_tokens_used=int(answer.get("llm_tokens_used", 0)),
    )
    return cq, sub


def _attribute_failures(
    q: CleaningQuestion, sub: CleaningAnswerSubmission, rep: DirectionalScoringReport
) -> List[str]:
    """把单题扣分归因到错误类型桶。"""
    buckets: List[str] = []
    gt_junks = set(q.ground_truth_junk_ids)
    sub_pruned = set(sub.pruned_junk_ids)
    leaked = gt_junks - sub_pruned
    if leaked:
        buckets.append("NOISE_LEAK")
    over_pruned = sub_pruned - gt_junks
    if over_pruned and len(over_pruned) > len(gt_junks):
        buckets.append("OVER_PRUNE")

    matched_gt = set()
    for gt_fact in q.ground_truth_facts:
        for sf in sub.extracted_facts:
            ok, _ = DirectionalSemanticMatcher.is_direction_aligned(gt_fact, sf)
            if ok:
                matched_gt.add(gt_fact.fact_id)
                break
    missed_gt = [f for f in q.ground_truth_facts if f.fact_id not in matched_gt]
    if missed_gt:
        # 区分漏检（完全没提）与方向/维度/实体偏离
        sub_intents = {sf.semantic_intent.upper() for sf in sub.extracted_facts}
        sub_dims = {sf.dimension_id for sf in sub.extracted_facts}
        for gf in missed_gt:
            if gf.semantic_intent.upper() not in sub_intents and gf.dimension_id not in sub_dims:
                buckets.append("FACT_MISS")
                break
            if gf.dimension_id not in sub_dims:
                buckets.append("DIMENSION_MISMATCH")
                break
        if not buckets:
            buckets.append("INTENT_DRIFT")
    if rep.hallucination_count > 0:
        buckets.append("HALLUCINATION")
    if not buckets and rep.final_score < 90.0:
        buckets.append("ENTITY_MISSED")
    return buckets or ["UNCATEGORIZED"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", type=Path, required=True, help="对手盲卷 jsonl")
    ap.add_argument(
        "--ground-truth", type=Path, required=True, help="出题方独立标答 jsonl（仅供阅卷）"
    )
    ap.add_argument("--label", default="v1", help="版本标签（v1 / v2 ...）")
    ap.add_argument("--answers-out", type=Path, default=None)
    ap.add_argument("--report-out", type=Path, default=None)
    ap.add_argument("--failures-out", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0=全量）")
    args = ap.parse_args()

    questions = _load_jsonl(args.questions)
    gts = {r["question_id"]: r for r in _load_jsonl(args.ground_truth)}
    if args.limit:
        questions = questions[: args.limit]

    solver = BlindStreamPurifier()
    gen_agent = questions[0].get("generator_agent", "unknown")
    stem = f"ans_{SOLVER_AGENT_ID}_blindstream_on_{gen_agent}"

    answers_out = args.answers_out or (
        Path("benchmarks/data_cleaning/answers") / f"{stem}.jsonl"
    )
    report_out = args.report_out or (
        Path("benchmarks/data_cleaning/reports")
        / f"report_{SOLVER_AGENT_ID}_blindstream_on_{gen_agent}.json"
    )
    failures_out = args.failures_out or (
        Path("benchmarks/data_cleaning/reports")
        / f"failures_{SOLVER_AGENT_ID}_blindstream_on_{gen_agent}_{args.label}.jsonl"
    )
    for p in (answers_out, report_out, failures_out):
        p.parent.mkdir(parents=True, exist_ok=True)

    # ------------------ 第二阶段：做题（接管底座清洗） ------------------
    t0 = time.perf_counter()
    answers: List[Dict[str, Any]] = []
    audits: List[Dict[str, Any]] = []
    for q in questions:
        answer, audit = solver.purify(q)
        answers.append(answer)
        audits.append(
            {
                "question_id": audit.question_id,
                "p0_bypass_triggered": audit.p0_bypass_triggered,
                "p0_bypass_latency_ms": round(audit.p0_bypass_latency_ms, 4),
                "p0_within_budget": audit.p0_within_budget,
                "total_latency_ms": round(audit.total_latency_ms, 3),
                "pruned_count": audit.pruned_count,
                "signal_intents": audit.signal_intents,
            }
        )
    solve_seconds = time.perf_counter() - t0

    with answers_out.open("w", encoding="utf-8") as fh:
        for a in answers:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")

    # ------------------ 第三阶段：方向性机器阅卷 ------------------
    reports: List[DirectionalScoringReport] = []
    failures: List[Dict[str, Any]] = []
    for q, a, aud in zip(questions, answers, audits):
        gt = gts.get(q["question_id"])
        if gt is None:
            print(f"[WARN] 缺标答: {q['question_id']}", file=sys.stderr)
            continue
        cq, sub = _to_models(q, gt, a)
        rep = DirectionalSemanticMatcher.evaluate_submission(cq, sub)
        reports.append(rep)
        if rep.verdict != "PASS":
            failures.append(
                {
                    "question_id": rep.question_id,
                    "final_score": rep.final_score,
                    "direction_match_rate": rep.direction_match_rate,
                    "entity_recall_rate": rep.entity_recall_rate,
                    "junk_prune_rate": rep.junk_prune_rate,
                    "dimension_accuracy": rep.dimension_accuracy,
                    "hallucination_count": rep.hallucination_count,
                    "critique_notes": rep.critique_notes,
                    "attribution_buckets": _attribute_failures(cq, sub, rep),
                    "submitted_intents": [
                        f["semantic_intent"] for f in a.get("extracted_facts", [])
                    ],
                    "submitted_dims": [
                        f["dimension_id"] for f in a.get("extracted_facts", [])
                    ],
                    "gt_intents": [
                        f.get("semantic_intent") for f in gt.get("ground_truth_facts", [])
                    ],
                    "gt_dims": [
                        f.get("dimension_id") for f in gt.get("ground_truth_facts", [])
                    ],
                }
            )

    # ------------------ 聚合 ------------------
    n = len(reports)
    agg = {
        "solver_agent": SOLVER_AGENT_ID,
        "generator_agent": gen_agent,
        "label": args.label,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "questions_total": len(questions),
        "graded_total": n,
        "pass_count": sum(1 for r in reports if r.verdict == "PASS"),
        "pass_rate": round(sum(1 for r in reports if r.verdict == "PASS") / max(n, 1), 4),
        "mean_final_score": round(sum(r.final_score for r in reports) / max(n, 1), 4),
        "mean_direction_match_rate": round(
            sum(r.direction_match_rate for r in reports) / max(n, 1), 4
        ),
        "mean_entity_recall_rate": round(
            sum(r.entity_recall_rate for r in reports) / max(n, 1), 4
        ),
        "mean_dimension_accuracy": round(
            sum(r.dimension_accuracy for r in reports) / max(n, 1), 4
        ),
        "mean_junk_prune_rate": round(
            sum(r.junk_prune_rate for r in reports) / max(n, 1), 4
        ),
        "total_hallucination_count": sum(r.hallucination_count for r in reports),
        "self_solving_violations": sum(1 for r in reports if r.is_self_solving_violation),
        "solve_wall_seconds": round(solve_seconds, 2),
        "llm_tokens_used_total": 0,
        "p0": {
            "triggered_questions": sum(1 for a in audits if a["p0_bypass_triggered"]),
            "max_bypass_latency_ms": round(
                max((a["p0_bypass_latency_ms"] for a in audits), default=0.0), 4
            ),
            "budget_ms": P0_BYPASS_BUDGET_MS,
            "all_within_budget": all(a["p0_within_budget"] for a in audits),
            "llm_calls": 0,
        },
    }

    # 按出题方意图分桶的得分（用于错题归因）
    per_intent: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "dir_sum": 0.0, "ent_sum": 0.0, "dim_sum": 0.0, "score_sum": 0.0}
    )
    for q, a, rep in zip(questions, answers, reports):
        gt = gts.get(q["question_id"], {})
        for f in gt.get("ground_truth_facts", []):
            key = f.get("semantic_intent", "?")
            b = per_intent[key]
            b["n"] += 1
            b["dir_sum"] += rep.direction_match_rate
            b["ent_sum"] += rep.entity_recall_rate
            b["dim_sum"] += rep.dimension_accuracy
            b["score_sum"] += rep.final_score
    agg["per_intent"] = {
        k: {
            "n": v["n"],
            "direction_match": round(v["dir_sum"] / v["n"], 4),
            "entity_recall": round(v["ent_sum"] / v["n"], 4),
            "dimension_acc": round(v["dim_sum"] / v["n"], 4),
            "mean_score": round(v["score_sum"] / v["n"], 2),
        }
        for k, v in sorted(per_intent.items())
    }

    bucket_counter = Counter(
        b for f in failures for b in f["attribution_buckets"]
    )
    agg["failure_attribution"] = dict(bucket_counter.most_common())

    # 维度错位明细（期望 vs 提交）
    dim_mismatch = Counter()
    for f in failures:
        for gi, gd, si, sd in zip(
            f["gt_intents"], f["gt_dims"], f["submitted_intents"], f["submitted_dims"]
        ):
            if gi and si and gi.upper() in si.upper() and gd != sd:
                dim_mismatch[f"{gi}: {gd} != {sd}"] += 1
    agg["dimension_mismatch_detail"] = dict(dim_mismatch.most_common(30))

    with report_out.open("w", encoding="utf-8") as fh:
        json.dump(agg, fh, ensure_ascii=False, indent=2)
    with failures_out.open("w", encoding="utf-8") as fh:
        for f in failures:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    # ------------------ 控制台速览 ------------------
    print("=" * 72)
    print(f"答题战队 {SOLVER_AGENT_ID} × 出题战队 {gen_agent} ({args.label})")
    print("=" * 72)
    print(f"阅卷题数        : {n}")
    print(f"PASS 率         : {agg['pass_rate']:.2%}")
    print(f"平均总分        : {agg['mean_final_score']:.2f} / 100")
    print(f"方向吻合率      : {agg['mean_direction_match_rate']:.4f}  (门禁 ≥90%)")
    print(f"实体召回率      : {agg['mean_entity_recall_rate']:.4f}  (门禁 ≥95%)")
    print(f"垃圾剪枝率      : {agg['mean_junk_prune_rate']:.4f}  (门禁 ≥95%)")
    print(f"维度正确率      : {agg['mean_dimension_accuracy']:.4f}  (门禁 ≥95%)")
    print(f"幻觉总数        : {agg['total_hallucination_count']}  (门禁 =0)")
    print(f"P0 旁路         : {agg['p0']['triggered_questions']} 题触发, "
          f"最大时延 {agg['p0']['max_bypass_latency_ms']:.3f}ms "
          f"(预算 {P0_BYPASS_BUDGET_MS:.0f}ms), 全部达标: {agg['p0']['all_within_budget']}")
    print(f"做题总耗时      : {agg['solve_wall_seconds']}s ({agg['solve_wall_seconds']*1000/max(n,1):.2f}ms/题), 大模型调用 0")
    print(f"错题归因分桶    : {agg['failure_attribution']}")
    print(f"答卷            : {answers_out}")
    print(f"阅卷报告        : {report_out}")
    print(f"错题样本        : {failures_out} ({len(failures)} 题)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
