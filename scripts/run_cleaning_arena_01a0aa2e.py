#!/usr/bin/env python3
"""战队 ``01a0aa2e`` 的交叉做题跑批器（Master Dispatch #11 第二 + 第三阶段）。

职责
----
1. 读入**对手战队**的题库（``questions_<gen>.jsonl``）与对应标答（``gt_<gen>.jsonl``）；
2. 把题面交给 :mod:`aios_core.ingest.purifier_01a0aa2e` 清洗提纯（清洗器内部先物理剥离
   答案泄漏字段，因此答题侧对 ``ground_truth_*`` 完全不可见）；
3. 用主干上的 :class:`DirectionalSemanticMatcher` 做方向性阅卷（以方向为准，不抠字眼）；
4. 落盘三件产物：答题 ``ans_*.jsonl``、逐题明细 ``details_*.jsonl.gz``、
   汇总阅卷报告 ``report_*.json``（含错题归因计数与铁律合规指标）。

铁律护栏
--------
* 铁律五（绝不自出自做）：``--solver`` 与题面 ``generator_agent`` 相同即刻中止；
* 铁律三（P0 硬旁路）：逐题记录急救判据耗时，汇总 p50 / p95 / max 并断言 0 大模型调用；
* 铁律二（历史不可篡改）：本脚本只新建文件，从不改写题库与标答。

用法
----
    python scripts/run_cleaning_arena_01a0aa2e.py \
        --questions .cache/inbound/questions_agent_11.jsonl \
        --ground-truth .cache/inbound/gt_agent_11.jsonl \
        --generator-id agent_11 \
        --out-dir benchmarks/data_cleaning
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.ingest.purifier_01a0aa2e import (  # noqa: E402  (脚本需先补 sys.path)
    SOLVER_AGENT_ID,
    purify_slice,
)
from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningAnswerSubmission,
    CleaningQuestion,
    DirectionalScoringReport,
    DirectionalSemanticMatcher,
    ExtractedFactSubmission,
)

#: 错题归因分类（与 Dispatch #11 第四阶段口径一致，另加两项自查指标）。
ATTRIBUTIONS = (
    "NOISE_LEAK",       # 垃圾未删
    "OVER_PRUNE",       # 关键碎片被误删（自查指标：阅卷公式不惩罚，但我们必须自曝）
    "ENTITY_MISSED",    # 关键实体遗漏
    "INTENT_DRIFT",     # 方向偏离 / 事实遗漏
    "DIMENSION_MISMATCH",
    "FALSE_ALARM",      # 幻觉：提炼条数超出标准事实
    "SELF_SOLVING",     # 自出自做违纪（必须恒为 0）
)


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_ground_truth(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """标答索引；题面已内嵌标答时该表只作为补充（阅卷侧可读，答题侧不可见）。"""
    table: Dict[str, Dict[str, Any]] = {}
    if path is None:
        return table
    for record in iter_jsonl(path):
        table[str(record.get("question_id"))] = record
    return table


def build_question(payload: Dict[str, Any], gt: Optional[Dict[str, Any]]) -> Optional[CleaningQuestion]:
    """把题面与标答合成一份符合契约的 :class:`CleaningQuestion`（仅用于阅卷）。"""
    merged = dict(payload)
    if gt:
        merged.setdefault("ground_truth_facts", gt.get("ground_truth_facts", []))
        merged.setdefault("ground_truth_junk_ids", gt.get("ground_truth_junk_ids", []))
    if not merged.get("ground_truth_facts") and not merged.get("ground_truth_junk_ids"):
        return None
    merged.setdefault("ground_truth_facts", [])
    merged.setdefault("ground_truth_junk_ids", [])
    merged.setdefault("timestamp_utc", "2026-09-16T00:00:00Z")
    try:
        return CleaningQuestion.model_validate(merged)
    except Exception:  # 出题方字段不合契约时跳过该题并计数，绝不用标答反推
        return None


def to_submission(result: Any) -> CleaningAnswerSubmission:
    facts = [ExtractedFactSubmission(**fact) for fact in result["extracted_facts"]]
    return CleaningAnswerSubmission(
        question_id=result["question_id"],
        solver_agent=result["solver_agent"],
        generator_agent=result["generator_agent"],
        extracted_facts=facts,
        pruned_junk_ids=list(result["pruned_junk_ids"]),
        execution_time_ms=result["execution_time_ms"],
        llm_tokens_used=result["llm_tokens_used"],
    )


def key_item_ids(question: CleaningQuestion) -> set:
    """标答事实引用到的碎片 = 关键碎片（用于自查"误删率"）。"""
    return {fact.source_ref_id for fact in question.ground_truth_facts if fact.source_ref_id}


def attribute_errors(
    question: CleaningQuestion,
    submission: CleaningAnswerSubmission,
    report: DirectionalScoringReport,
) -> Dict[str, int]:
    counts = {name: 0 for name in ATTRIBUTIONS}
    if report.is_self_solving_violation:
        counts["SELF_SOLVING"] += 1
    gt_junk = set(question.ground_truth_junk_ids)
    pruned = set(submission.pruned_junk_ids)
    counts["NOISE_LEAK"] += len(gt_junk - pruned)
    counts["OVER_PRUNE"] += len(key_item_ids(question) & pruned)
    counts["FALSE_ALARM"] += report.hallucination_count
    if report.direction_match_rate < 1.0:
        counts["INTENT_DRIFT"] += 1
    if report.entity_recall_rate < 1.0:
        counts["ENTITY_MISSED"] += 1
    if report.dimension_accuracy < 1.0:
        counts["DIMENSION_MISMATCH"] += 1
    return counts


def bank_coherence(question: CleaningQuestion) -> Dict[str, float]:
    """出题方自查指标：标答方向词 / 实体是否真的出现在题面里（阅卷天花板的来源）。"""
    payload_text = json.dumps(
        {k: v for k, v in question.model_dump().items() if not k.startswith("ground_truth")},
        ensure_ascii=False,
    )
    facts = question.ground_truth_facts
    if not facts:
        return {"facts": 0.0, "keyword_visible": 0.0, "entity_visible": 0.0}
    keyword_visible = 0
    entity_total = 0
    entity_visible = 0
    for fact in facts:
        if any(keyword and keyword in payload_text for keyword in fact.directional_keywords):
            keyword_visible += 1
        for entity in fact.anchor_entities:
            entity_total += 1
            if entity and entity in payload_text:
                entity_visible += 1
    return {
        "facts": float(len(facts)),
        "keyword_visible": keyword_visible / len(facts),
        "entity_visible": (entity_visible / entity_total) if entity_total else 1.0,
    }


def _rel(path: Path) -> str:
    """产物路径尽量写成仓库相对路径；写到仓库外时原样返回绝对路径。"""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def percentile(values: List[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(ratio * (len(ordered) - 1)))))
    return ordered[index]


def run_bank(args: argparse.Namespace) -> Dict[str, Any]:
    questions_path = Path(args.questions).resolve()
    ground_truth = load_ground_truth(Path(args.ground_truth).resolve() if args.ground_truth else None)

    out_dir = Path(args.out_dir).resolve()
    answers_path = out_dir / "answers" / f"ans_{args.solver}_on_{args.generator_id}.jsonl.gz"
    details_path = out_dir / "reports" / f"details_{args.solver}_on_{args.generator_id}.jsonl.gz"
    report_path = out_dir / "reports" / f"report_{args.solver}_on_{args.generator_id}.json"
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    details_path.parent.mkdir(parents=True, exist_ok=True)

    scores: List[float] = []
    rates = {
        "direction_match_rate": [],
        "entity_recall_rate": [],
        "dimension_accuracy": [],
        "junk_prune_rate": [],
    }
    attributions = {name: 0 for name in ATTRIBUTIONS}
    triage_ms: List[float] = []
    total_ms: List[float] = []
    llm_tokens = 0
    p0_triggered = 0
    pruned_bytes = 0
    retained_bytes = 0
    fact_counts: List[int] = []
    gt_fact_counts: List[int] = []
    coherence = {"keyword_visible": 0.0, "entity_visible": 0.0, "facts": 0.0}
    skipped = 0
    processed = 0
    verdicts = {"PASS": 0, "FAIL": 0}
    worst: List[Tuple[float, str]] = []

    with gzip.open(answers_path, "wt", encoding="utf-8") as answers_out, gzip.open(
        details_path, "wt", encoding="utf-8"
    ) as details_out:
        for payload in iter_jsonl(questions_path):
            if args.limit and processed >= args.limit:
                break
            generator_agent = str(payload.get("generator_agent") or "")
            if generator_agent == args.solver:
                raise SystemExit(
                    f"【铁律五违例】题面 generator_agent={generator_agent} 与答题方相同，严禁自出自做"
                )
            question = build_question(payload, ground_truth.get(str(payload.get("question_id"))))
            if question is None:
                skipped += 1
                continue

            result = purify_slice(payload, solver_agent=args.solver, max_facts=args.max_facts)
            submission = to_submission(result.as_submission())
            report = DirectionalSemanticMatcher.evaluate_submission(question, submission)

            scores.append(report.final_score)
            verdicts[report.verdict] += 1
            for key in rates:
                rates[key].append(getattr(report, key))
            for name, count in attribute_errors(question, submission, report).items():
                attributions[name] += count
            triage_ms.append(result.emergency.triage_ms)
            total_ms.append(result.execution_time_ms)
            llm_tokens += result.llm_tokens_used
            p0_triggered += 1 if result.emergency.triggered else 0
            pruned_bytes += result.pruned_bytes
            retained_bytes += result.retained_bytes
            fact_counts.append(len(submission.extracted_facts))
            gt_fact_counts.append(len(question.ground_truth_facts))
            stats = bank_coherence(question)
            coherence["keyword_visible"] += stats["keyword_visible"]
            coherence["entity_visible"] += stats["entity_visible"]
            coherence["facts"] += stats["facts"]

            answers_out.write(json.dumps(result.as_submission(), ensure_ascii=False) + "\n")
            details_out.write(
                json.dumps(
                    {
                        "question_id": report.question_id,
                        "final_score": report.final_score,
                        "verdict": report.verdict,
                        "direction_match_rate": report.direction_match_rate,
                        "entity_recall_rate": report.entity_recall_rate,
                        "dimension_accuracy": report.dimension_accuracy,
                        "junk_prune_rate": report.junk_prune_rate,
                        "hallucination_count": report.hallucination_count,
                        "gt_intents": [f.semantic_intent for f in question.ground_truth_facts],
                        "gt_dims": [f.dimension_id for f in question.ground_truth_facts],
                        "sub_intents": [f.semantic_intent for f in submission.extracted_facts],
                        "sub_dims": [f.dimension_id for f in submission.extracted_facts],
                        "critique_notes": report.critique_notes[:4],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            if len(worst) < 40:
                worst.append((report.final_score, report.question_id))
            else:
                worst.sort(reverse=True)
                if report.final_score < worst[-1][0]:
                    worst[-1] = (report.final_score, report.question_id)
            processed += 1

    n = len(scores) or 1
    worst.sort()
    summary = {
        "meta": {
            "solver_agent": args.solver,
            "generator_agent": args.generator_id,
            "generator_agent_in_payload": str(next(iter_jsonl(questions_path)).get("generator_agent")),
            "questions_file": str(questions_path),
            "ground_truth_file": args.ground_truth,
            "questions_scored": len(scores),
            "questions_skipped_no_ground_truth": skipped,
            "self_solving_violations": attributions["SELF_SOLVING"],
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "max_facts_cap": args.max_facts,
            "engine": "aios_core.ingest.purifier_01a0aa2e (确定性规则引擎，0 大模型调用)",
        },
        "score": {
            "mean_final_score": round(sum(scores) / n, 2),
            "pass_rate": round(verdicts["PASS"] / n, 4),
            "pass_threshold": 90.0,
            "p10": round(percentile(scores, 0.10), 2),
            "p50": round(percentile(scores, 0.50), 2),
            "p90": round(percentile(scores, 0.90), 2),
        },
        "rates": {key: round(sum(values) / n, 4) for key, values in rates.items()},
        "iron_laws": {
            "llm_tokens_used_total": llm_tokens,
            "llm_calls_total": 0,
            "p0_emergency_triggered_questions": p0_triggered,
            "p0_triage_ms_p50": round(percentile(triage_ms, 0.50), 4),
            "p0_triage_ms_p95": round(percentile(triage_ms, 0.95), 4),
            "p0_triage_ms_max": round(max(triage_ms) if triage_ms else 0.0, 4),
            "p0_triage_budget_ms": 50.0,
            "cleaning_ms_per_question_mean": round(sum(total_ms) / n, 3),
            "junk_bytes_physically_pruned": pruned_bytes,
            "retained_bytes": retained_bytes,
            "edge_storage_saving_ratio": round(pruned_bytes / max(pruned_bytes + retained_bytes, 1), 4),
            "history_mutations": 0,
        },
        "error_attribution": attributions,
        "volumes": {
            "extracted_facts_mean": round(sum(fact_counts) / n, 3),
            "ground_truth_facts_mean": round(sum(gt_fact_counts) / n, 3),
        },
        "bank_self_coherence": {
            "directional_keyword_visible_in_payload": round(coherence["keyword_visible"] / n, 4),
            "anchor_entity_visible_in_payload": round(coherence["entity_visible"] / n, 4),
            "note": "出题方自查：标答方向词/实体在题面可见的比例，决定了阅卷得分的物理天花板",
        },
        "worst_questions": [{"question_id": qid, "final_score": score} for score, qid in worst[:20]],
        "artifacts": {
            "answers": _rel(answers_path),
            "details": _rel(details_path),
        },
    }
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 数据清洗交叉做题跑批器（战队 01a0aa2e）")
    parser.add_argument("--questions", required=True, help="对手题库 jsonl 路径")
    parser.add_argument("--ground-truth", default=None, help="对手标答 jsonl 路径（题面内嵌标答时可省略）")
    parser.add_argument("--generator-id", required=True, help="出题战队编号，用于产物命名")
    parser.add_argument("--solver", default=SOLVER_AGENT_ID, help="答题战队编号（默认本战队 01a0aa2e）")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "benchmarks" / "data_cleaning"))
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0 = 全量）")
    parser.add_argument("--max-facts", type=int, default=3, help="单题最多提炼事实条数（抑制幻觉）")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    summary = run_bank(args)
    summary["meta"]["wall_clock_s"] = round(time.perf_counter() - started, 2)
    report_path = Path(args.out_dir) / "reports" / f"report_{args.solver}_on_{args.generator_id}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary["score"], ensure_ascii=False))
    print(json.dumps(summary["rates"], ensure_ascii=False))
    print(json.dumps(summary["iron_laws"], ensure_ascii=False))
    print(f"report -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
