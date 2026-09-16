"""AIOS 3.0 跨战队数据清洗对抗考场 —— 答题端流水线执行器。

职责：
  1. **取卷**：读取对手战队落盘的 10,000 道题库（跨 Git 拉取，铁律五）；
  2. **切分**：把题库切成 *校准集* 与 *评测集*，两者严格不相交；
  3. **校准**：只在校准集上拟合认知模型（禁止用评测集调参）；
  4. **盲审答题**：对评测集逐题剥离标准答案后求解；
  5. **阅卷**：按方向性语义评分（方向对即给分，不抠字眼）；
  6. **归因进化**：统计错题根因，产出可执行的升级建议。

命令行::

    python -m aios_core.perception.cleaning_arena_runner \\
        --questions benchmarks/data_cleaning/questions/questions_x.jsonl \\
        --solver-agent agent-01a0aa2e \\
        --answers benchmarks/data_cleaning/answers/answers_x.jsonl \\
        --report  benchmarks/data_cleaning/reports/report_x.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence, Tuple

from aios_core.perception.cleaning_model import CalibratedCleaningModel
from aios_core.perception.cleaning_solver import (
    CleaningSolver,
    SolvedAnswer,
    SolverConfig,
    assert_cross_team,
    blind_view,
)
from aios_core.perception.p0_safety_bypass import evaluate_question_p0

#: PASS 门槛（百分制）。
PASS_THRESHOLD = 90.0
#: 铁律三：P0 穿透耗时上限。
P0_BUDGET_MS = 50.0


# --------------------------------------------------------------------------
# 阅卷：方向性语义评分（与 cleaning_arena_protocol.DirectionalSemanticMatcher 同构）
# --------------------------------------------------------------------------


@dataclass
class QuestionScore:
    """单题评分明细。"""

    question_id: str
    difficulty: str
    final_score: float
    direction_match_rate: float
    entity_recall_rate: float
    dimension_accuracy: float
    junk_prune_rate: float
    hallucination_count: int
    verdict: str
    missed_facts: List[str] = field(default_factory=list)
    leaked_junk: List[str] = field(default_factory=list)
    over_pruned: List[str] = field(default_factory=list)


def _direction_aligned(gt: Mapping[str, Any], sub: Mapping[str, Any]) -> Tuple[bool, float]:
    """判定提交事实与标准事实是否同方向，并返回实体覆盖率。"""
    if gt.get("dimension_id") != sub.get("dimension_id"):
        return False, 0.0
    gt_intent = str(gt.get("semantic_intent") or "").upper()
    sub_intent = str(sub.get("semantic_intent") or "").upper()
    intent_matched = (
        gt_intent == sub_intent or gt_intent in sub_intent or sub_intent in gt_intent
    )
    summary = str(sub.get("summary_text") or "")
    keywords = gt.get("directional_keywords") or []
    keyword_matched = any(k in summary for k in keywords) if keywords else True

    gt_ents = set(gt.get("anchor_entities") or ())
    sub_ents = set(sub.get("recognized_entities") or ())
    sub_ents |= {e for e in gt_ents if e in summary}
    overlap = len(gt_ents & sub_ents) / max(len(gt_ents), 1)

    if (intent_matched or keyword_matched) and (overlap >= 0.5 or not gt_ents):
        return True, overlap
    return False, overlap


def grade(question: Mapping[str, Any], submission: Mapping[str, Any]) -> QuestionScore:
    """对单题提交执行方向性阅卷。"""
    gt_junk = set(question.get("ground_truth_junk_ids") or ())
    pruned = set(submission.get("pruned_junk_ids") or ())
    junk_rate = len(gt_junk & pruned) / len(gt_junk) if gt_junk else 1.0

    gt_facts = [f for f in (question.get("ground_truth_facts") or ()) if isinstance(f, Mapping)]
    sub_facts = [f for f in (submission.get("extracted_facts") or ()) if isinstance(f, Mapping)]

    matched = 0
    dim_ok = 0
    entity_total = 0.0
    missed: List[str] = []
    for gt in gt_facts:
        best = False
        for sub in sub_facts:
            aligned, overlap = _direction_aligned(gt, sub)
            if aligned:
                best = True
                dim_ok += 1
                entity_total += overlap
                break
        if best:
            matched += 1
        else:
            missed.append(str(gt.get("fact_id") or gt.get("semantic_intent") or "?"))

    n = max(len(gt_facts), 1)
    direction = matched / n
    dimension = dim_ok / n
    entity = entity_total / n
    hallucination = max(0, len(sub_facts) - len(gt_facts))

    raw = (
        direction * 40.0
        + entity * 25.0
        + junk_rate * 25.0
        + dimension * 10.0
        - hallucination * 15.0
    )
    final = max(0.0, min(100.0, raw))

    all_ids = set()
    for key, id_field in (
        ("mic_stream", "snippet_id"),
        ("app_message_stream", "msg_id"),
        ("user_dialogue_stream", "utterance_id"),
    ):
        for item in question.get(key) or ():
            if isinstance(item, Mapping) and item.get(id_field):
                all_ids.add(str(item[id_field]))

    return QuestionScore(
        question_id=str(question.get("question_id") or ""),
        difficulty=str(question.get("difficulty") or ""),
        final_score=round(final, 2),
        direction_match_rate=round(direction, 4),
        entity_recall_rate=round(entity, 4),
        dimension_accuracy=round(dimension, 4),
        junk_prune_rate=round(junk_rate, 4),
        hallucination_count=hallucination,
        verdict="PASS" if final >= PASS_THRESHOLD else "FAIL",
        missed_facts=missed,
        leaked_junk=sorted(gt_junk - pruned),
        over_pruned=sorted((pruned - gt_junk) & all_ids),
    )


# --------------------------------------------------------------------------
# 错题归因进化（铁律：用大量测试总结经验）
# --------------------------------------------------------------------------

#: 归因类型 -> 工程升级建议。
_UPGRADE_PLAYBOOK: Dict[str, str] = {
    "NOISE_LEAK": "扩充垃圾语义先验词表并降低 junk 判定阈值；对遗漏样本做字符 n-gram 增量校准。",
    "OVER_PRUNE": "提高 junk 判定阈值并增加「关键通知/医嘱/法院传票」白名单，避免误删高价值认知。",
    "INTENT_DRIFT": "增大场景先验权重 context_weight，让同场景片段互相佐证，纠正孤立片段的方向漂移。",
    "ENTITY_MISSED": "放宽锚点实体策略 min_ratio，并把声纹绑定名册与发信人并入实体证据链。",
    "DIMENSION_MISMATCH": "重建意图->维度映射表，对跨维度歧义意图按场景主题二次判别。",
    "HALLUCINATION": "收紧 cardinality 预测，宁可少报不可多报（每条幻觉扣 15 分）。",
    "FACT_UNDER_RECALL": "放宽 cardinality 上限并启用次优语义方向补位，填满零风险预算。",
}


@dataclass
class FailureAttribution:
    """错题归因条目。"""

    error_type: str
    occurrences: int
    sample_question_ids: List[str]
    root_cause_analysis: str
    upgrade_action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "occurrences": self.occurrences,
            "sample_question_ids": self.sample_question_ids[:8],
            "root_cause_analysis": self.root_cause_analysis,
            "upgrade_action_taken": self.upgrade_action,
        }


def attribute_failures(scores: Sequence[QuestionScore]) -> List[FailureAttribution]:
    """对全部错题做根因归类，产出可执行的升级建议。"""
    buckets: Dict[str, List[str]] = defaultdict(list)
    for s in scores:
        if s.verdict == "PASS":
            continue
        if s.leaked_junk:
            buckets["NOISE_LEAK"].append(s.question_id)
        if s.over_pruned:
            buckets["OVER_PRUNE"].append(s.question_id)
        if s.hallucination_count:
            buckets["HALLUCINATION"].append(s.question_id)
        if s.direction_match_rate < 1.0:
            # 方向没命中：区分"完全没提这条事实"还是"提了但方向偏"
            if s.direction_match_rate == 0.0:
                buckets["INTENT_DRIFT"].append(s.question_id)
            else:
                buckets["FACT_UNDER_RECALL"].append(s.question_id)
        if s.direction_match_rate > 0 and s.entity_recall_rate < 0.6:
            buckets["ENTITY_MISSED"].append(s.question_id)
        if s.dimension_accuracy < s.direction_match_rate:
            buckets["DIMENSION_MISMATCH"].append(s.question_id)

    causes = {
        "NOISE_LEAK": "垃圾片段未被识别，端侧存储被无价值二进制/营销文本占用（违反铁律四）。",
        "OVER_PRUNE": "把高价值认知误判为垃圾并物理删除，属于不可逆的认知损失。",
        "INTENT_DRIFT": "片段孤立看语义模糊，未借助同场景其他证据做因果比对，方向判偏。",
        "ENTITY_MISSED": "锚点实体（人物/金额/时间）召回不足，事实虽对但证据链不完整。",
        "DIMENSION_MISMATCH": "意图归属维度判错，导致裁判端维度硬约束直接失配。",
        "HALLUCINATION": "提交事实数超出真值，凭空多报被重罚。",
        "FACT_UNDER_RECALL": "部分真值事实未被提纯出来，预算或显著性判定过于保守。",
    }
    out: List[FailureAttribution] = []
    for etype, qids in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        out.append(
            FailureAttribution(
                error_type=etype,
                occurrences=len(qids),
                sample_question_ids=qids,
                root_cause_analysis=causes.get(etype, ""),
                upgrade_action=_UPGRADE_PLAYBOOK.get(etype, ""),
            )
        )
    return out


# --------------------------------------------------------------------------
# 流水线
# --------------------------------------------------------------------------


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


@dataclass
class ArenaResult:
    """整场考试的汇总结果。"""

    generator_agent: str
    solver_agent: str
    total_questions: int
    calibration_size: int
    evaluated: int
    mean_score: float
    pass_rate: float
    metrics: Dict[str, float]
    by_difficulty: Dict[str, Dict[str, float]]
    p0: Dict[str, Any]
    model_report: Dict[str, Any]
    attributions: List[Dict[str, Any]]
    throughput_ms_per_question: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generator_agent": self.generator_agent,
            "solver_agent": self.solver_agent,
            "total_questions": self.total_questions,
            "calibration_size": self.calibration_size,
            "evaluated": self.evaluated,
            "mean_score": round(self.mean_score, 2),
            "pass_rate": round(self.pass_rate, 4),
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "by_difficulty": self.by_difficulty,
            "p0_safety_bypass": self.p0,
            "model_calibration": self.model_report,
            "failure_attribution": self.attributions,
            "throughput_ms_per_question": round(self.throughput_ms_per_question, 3),
        }


def run_arena(
    questions_path: Path,
    solver_agent: str,
    calibration_size: int = 2000,
    answers_path: Path | None = None,
    limit: int | None = None,
    entity_policy: Tuple[float, int] | None = None,
) -> ArenaResult:
    """执行完整的取卷 -> 校准 -> 盲审答题 -> 阅卷 -> 归因流水线。

    Args:
        entity_policy: 锚点实体策略 ``(min_ratio, max_n)``。默认 ``None``
            表示由内部留出集自动择优；显式传入 ``(0.25, 12)`` 可切换到
            "严格模式"——只提交高频典型锚点，结果更接近人工书写的事实卡片。
            两种模式的差异已在报告 ``entity_policy`` 字段中留痕，便于审计。
    """
    questions = list(iter_jsonl(questions_path))
    if limit:
        questions = questions[:limit]
    if not questions:
        raise ValueError(f"题库为空：{questions_path}")

    generator_agent = str(questions[0].get("generator_agent") or "")
    # 铁律五：绝不自出自做
    assert_cross_team(solver_agent, generator_agent)

    calibration = questions[:calibration_size]
    evaluation = questions[calibration_size:]
    if not evaluation:
        raise ValueError("评测集为空：请调小 --calibration-size。")

    model = CalibratedCleaningModel()
    model_report = model.fit(calibration).to_dict()
    if entity_policy is not None:
        model._apply_entity_policy(entity_policy)
        model_report["entity_policy"] = list(entity_policy)
        model_report["entity_policy_mode"] = "explicit_strict"
    else:
        model_report["entity_policy_mode"] = "auto_tuned"
    model_report["entity_policy_note"] = (
        "锚点实体 = 意图典型槽位 + 本题金额/时间 + 声纹名册。"
        "min_ratio 越低召回越高；该取值对总分影响显著，已在此留痕以供审计。"
    )

    solver = CleaningSolver(
        SolverConfig(solver_agent=solver_agent, t_now=time.strftime("%Y-%m-%dT%H:%M:%SZ")),
        cognitive_model=model,
    )

    scores: List[QuestionScore] = []
    p0_hits = 0
    p0_latencies: List[float] = []
    writer = answers_path.open("w", encoding="utf-8") if answers_path else None
    started = time.perf_counter()
    try:
        for question in evaluation:
            # 铁律三：调度器入口首行 P0 判定（独立计时，0 次大模型调用）
            verdict = evaluate_question_p0(question)
            p0_latencies.append(verdict.elapsed_ms)
            if verdict.triggered:
                p0_hits += 1

            answer: SolvedAnswer = solver.solve(blind_view(question))
            payload = answer.to_submission_dict()
            if writer:
                writer.write(json.dumps(payload, ensure_ascii=False) + "\n")
            scores.append(grade(question, payload))
    finally:
        if writer:
            writer.close()
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    n = len(scores)
    mean_score = sum(s.final_score for s in scores) / n
    pass_rate = sum(1 for s in scores if s.verdict == "PASS") / n
    metrics = {
        "direction_match_rate": sum(s.direction_match_rate for s in scores) / n,
        "entity_recall_rate": sum(s.entity_recall_rate for s in scores) / n,
        "dimension_accuracy": sum(s.dimension_accuracy for s in scores) / n,
        "junk_prune_rate": sum(s.junk_prune_rate for s in scores) / n,
        "hallucination_per_question": sum(s.hallucination_count for s in scores) / n,
    }

    by_diff: Dict[str, Dict[str, float]] = {}
    grouped: Dict[str, List[QuestionScore]] = defaultdict(list)
    for s in scores:
        grouped[s.difficulty].append(s)
    for diff, items in sorted(grouped.items()):
        by_diff[diff] = {
            "count": len(items),
            "mean_score": round(sum(i.final_score for i in items) / len(items), 2),
            "pass_rate": round(sum(1 for i in items if i.verdict == "PASS") / len(items), 4),
            "junk_prune_rate": round(sum(i.junk_prune_rate for i in items) / len(items), 4),
        }

    p0_summary = {
        "triggered_questions": p0_hits,
        "trigger_rate": round(p0_hits / n, 4),
        "max_latency_ms": round(max(p0_latencies), 4) if p0_latencies else 0.0,
        "mean_latency_ms": round(statistics.fmean(p0_latencies), 6) if p0_latencies else 0.0,
        "p0_budget_ms": P0_BUDGET_MS,
        "budget_respected": (max(p0_latencies) if p0_latencies else 0.0) <= P0_BUDGET_MS,
        "llm_calls": 0,
    }

    return ArenaResult(
        generator_agent=generator_agent,
        solver_agent=solver_agent,
        total_questions=len(questions),
        calibration_size=len(calibration),
        evaluated=n,
        mean_score=mean_score,
        pass_rate=pass_rate,
        metrics=metrics,
        by_difficulty=by_diff,
        p0=p0_summary,
        model_report=model_report,
        attributions=[a.to_dict() for a in attribute_failures(scores)],
        throughput_ms_per_question=elapsed_ms / n,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 数据清洗对抗考场答题端")
    parser.add_argument("--questions", required=True, type=Path, help="对手战队题库 JSONL")
    parser.add_argument("--solver-agent", required=True, help="本战队标识（禁止等于出题方）")
    parser.add_argument("--calibration-size", type=int, default=2000, help="校准集题数")
    parser.add_argument("--limit", type=int, default=None, help="只取前 N 题（调试用）")
    parser.add_argument("--answers", type=Path, default=None, help="答卷落盘路径 JSONL")
    parser.add_argument("--report", type=Path, default=None, help="评测报告落盘路径 JSON")
    parser.add_argument(
        "--strict-entities",
        action="store_true",
        help="锚点实体严格模式(0.25,12)：只提交高频典型锚点，更接近人工事实卡片",
    )
    args = parser.parse_args(argv)

    if args.answers:
        args.answers.parent.mkdir(parents=True, exist_ok=True)

    result = run_arena(
        questions_path=args.questions,
        solver_agent=args.solver_agent,
        calibration_size=args.calibration_size,
        answers_path=args.answers,
        limit=args.limit,
        entity_policy=(0.25, 12) if args.strict_entities else None,
    )
    blob = result.to_dict()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    json.dump(blob, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
