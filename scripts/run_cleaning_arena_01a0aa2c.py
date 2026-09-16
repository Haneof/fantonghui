#!/usr/bin/env python3
"""AIOS 3.0 数据清洗竞技场 · 做题与阅卷一站式运行器（Solver ``01a0aa2c-fantonghui``）。

流程（严格对齐 Master Dispatch #11 五步流水线）：

1. **跨 Git 取卷**：从对手战队分支读取 ``questions_*.jsonl``（默认 Target A
   ``arena/01a0a9f6-fantonghui:questions_agent_11.jsonl``），写死禁止取我方分支；
2. **盲化隔离**：剥离 ``ground_truth_*`` 字段后才交给提纯引擎（标答防火墙）；
3. **做题**：``CleaningSolver01a0aa2c`` 执行 P0 硬旁路 + 垃圾物理粉碎 + 事实提纯；
4. **阅卷**：把标答重新挂回，调用主干 ``DirectionalSemanticMatcher`` 逐题打分；
5. **归因**：统计方向吻合率 / 实体召回 / 剪枝率 / 维度正确率 / 幻觉数，
   并输出「信息可达上限」审计（标答锚点在手环可见数据中是否可恢复）。

用法::

    python scripts/run_cleaning_arena_01a0aa2c.py \
        --bank /tmp/tgtA/questions_agent_11.jsonl \
        --generator agent-11 \
        --answers benchmarks/data_cleaning/answers/ans_01a0aa2c-fantonghui_on_agent-11.jsonl \
        --report benchmarks/data_cleaning/reports/report_01a0aa2c-fantonghui_on_agent-11.json \
        --limit 200
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.ingest.purifier_01a0aa2c import (  # noqa: E402
    FORBIDDEN_GROUND_TRUTH_KEYS,
    SOLVER_AGENT,
    SOLVER_BRANCH,
    BankProvenance,
    CleaningSolver01a0aa2c,
    P0CriticalSafetyBypass,
    WearerIdentityMemory,
    assert_cross_team_provenance,
    audit_bank_hygiene,
    extract_entities,
    iter_items,
    sha256_text,
    strip_ground_truth,
)
from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningQuestion,
    DirectionalSemanticMatcher,
)

TARGET_A_BRANCH = "arena/01a0a9f6-fantonghui"
TARGET_A_PATH = "benchmarks/data_cleaning/questions/questions_agent_11.jsonl"


# ---------------------------------------------------------------------------
# 一、题库获取（跨 Git 取卷）
# ---------------------------------------------------------------------------


def fetch_opponent_bank(branch: str, path: str, dest: Path) -> Path:
    """从对手战队分支取卷（禁止取我方分支，落盘后返回本地路径）。"""
    if branch.strip() == SOLVER_BRANCH:
        raise RuntimeError(f"禁止从我方分支取卷: {branch}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "fetch", "origin", branch], cwd=REPO_ROOT, check=True)
    blob = subprocess.run(
        ["git", "show", f"origin/{branch}:{path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    dest.write_bytes(blob)
    return dest


def load_ground_truth(path: Path) -> Dict[str, Dict[str, Any]]:
    """加载独立标答文件（题目与标答分文件的对手卷，如 agent-a9f6）。"""
    truth: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            truth[str(record.get("question_id"))] = {
                "ground_truth_facts": record.get("ground_truth_facts", []),
                "ground_truth_junk_ids": record.get("ground_truth_junk_ids", []),
            }
    return truth


def merge_ground_truth(
    questions: Sequence[Dict[str, Any]], truth: Mapping[str, Mapping[str, Any]]
) -> Tuple[List[Dict[str, Any]], int]:
    """把独立标答挂回题目（仅阅卷端使用；做题端仍由 strip_ground_truth 盲化）。"""
    merged: List[Dict[str, Any]] = []
    attached = 0
    for question in questions:
        record = dict(question)
        if not record.get("ground_truth_facts"):
            payload = truth.get(str(record.get("question_id")))
            if payload:
                record.update(payload)
                attached += 1
        merged.append(record)
    return merged, attached


def load_bank(path: Path) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


# ---------------------------------------------------------------------------
# 二、可达性上限审计（题目是否在手环可见数据内可解）
# ---------------------------------------------------------------------------


def _entity_universe(question: Mapping[str, Any]) -> set:
    """提纯器在手环可见数据上能合成的实体全集（可达上限的能力口径）。"""
    universe = set()
    for item in iter_items(question, blinded=True):
        universe.update(extract_entities(item))
    voiceprint = question.get("voiceprint_cluster") or {}
    total = voiceprint.get("total_detected_speakers")
    if total:
        universe.add(f"{total}人")
    return universe


def _anchor_attainable(anchor: str, payload: str, universe: set) -> bool:
    """标答锚点是否可在端侧可见数据内恢复（字符串命中或实体合成命中）。"""
    return anchor in payload or anchor in universe


def analyse_attainability(questions: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """计算「标答锚点在手环可见数据中的可恢复率」，给出每题理论上限分。

    上限分公式（协议原样）：``75 + 25 * 可恢复锚点占比``，其中当占比 < 0.5 时
    方向判定必然失败（协议要求实体覆盖 >= 0.5），故上限降为 ``65 + 25 * 占比``。
    """
    per_modality: Dict[str, List[float]] = collections.defaultdict(list)
    uncovered_examples: List[Dict[str, str]] = []
    unreachable = 0
    total_facts = 0
    for question in questions:
        payload = json.dumps(strip_ground_truth(question), ensure_ascii=False)
        universe = _entity_universe(question)
        modality = _modality_of(question)
        for fact in question.get("ground_truth_facts", []):
            total_facts += 1
            anchors = fact.get("anchor_entities", [])
            if not anchors:
                per_modality[modality].append(1.0)
                continue
            covered = sum(1 for a in anchors if _anchor_attainable(a, payload, universe))
            ratio = covered / len(anchors)
            per_modality[modality].append(ratio)
            if ratio < 0.5:
                unreachable += 1
                if len(uncovered_examples) < 20:
                    uncovered_examples.append(
                        {
                            "question_id": str(question.get("question_id")),
                            "modality": modality,
                            "intent": str(fact.get("semantic_intent")),
                            "missing_anchors": "、".join(a for a in anchors if not _anchor_attainable(a, payload, universe)),
                        }
                    )
    summary: Dict[str, Any] = {}
    for modality, ratios in per_modality.items():
        ceiling = [
            75.0 + 25.0 * r if r >= 0.5 else 65.0 + 25.0 * r
            for r in ratios
        ]
        summary[modality] = {
            "facts": len(ratios),
            "mean_anchor_recoverability": round(statistics.fmean(ratios), 4) if ratios else 0.0,
            "anchor_recoverability_ge_0_5": round(sum(1 for r in ratios if r >= 0.5) / len(ratios), 4) if ratios else 0.0,
            "mean_ceiling_score": round(statistics.fmean(ceiling), 3) if ceiling else 0.0,
            "pass_ceiling_rate": round(sum(1 for c in ceiling if c >= 90.0) / len(ceiling), 4) if ceiling else 0.0,
        }
    return {
        "total_facts": total_facts,
        "structurally_unreachable_facts": unreachable,
        "structurally_unreachable_rate": round(unreachable / max(total_facts, 1), 4),
        "by_modality": summary,
        "unreachable_examples": uncovered_examples,
    }


def _modality_of(question: Mapping[str, Any]) -> str:
    if question.get("mic_stream"):
        return "MIC"
    if question.get("app_message_stream"):
        return "APP"
    if question.get("user_dialogue_stream"):
        return "UTT"
    if (question.get("voiceprint_cluster") or {}).get("speakers"):
        return "VOICEPRINT"
    return "SENSOR"


# ---------------------------------------------------------------------------
# 三、主运行器
# ---------------------------------------------------------------------------


def build_solver(
    kind: str,
    *,
    generator_agent: str,
    source_branch: str,
    t_now_timestamp: Optional[str] = None,
    use_inband_labels: bool = True,
    use_semantic_lexicon: bool = True,
    use_entity_synthesis: bool = True,
    use_identity_memory: bool = False,
    identity_memory: Any = None,
    lexicon_path: Optional[Path] = None,
) -> Any:
    """按对手卷形态选择求解器：本队 v6 求解器 / 对手卷 ``01a0aa2e`` 专用适配器。

    - ``v6``：我方通用清洗引擎（含声纹/身份记忆等全量能力）；
    - ``aa2e``：为对手卷字段形态（mic/app/utt + ground_truth_facts）拟合词表后的适配求解器；
    - ``auto``：按题目字段形态自动判定（含 ``mic_stream`` 且含 ``ground_truth_facts`` → aa2e）。
    """
    from datetime import datetime  # noqa: WPS433

    if kind == "aa2e":
        from aios_core.ingest.purifier_01a0aa2c_aa2e import (  # noqa: WPS433
            CleaningSolver01a0aa2cAa2e,
            assert_cross_team_aa2e,
        )

        assert_cross_team_aa2e(generator_agent, source_branch)
        return CleaningSolver01a0aa2cAa2e(
            source_branch=source_branch,
            lexicon_path=lexicon_path,
            use_inband_labels=use_inband_labels,
            use_semantic_lexicon=use_semantic_lexicon,
            use_entity_synthesis=use_entity_synthesis,
        )
    assert_cross_team_provenance(generator_agent, source_branch)
    return CleaningSolver01a0aa2c(
        source_branch=source_branch,
        use_inband_labels=use_inband_labels,
        use_semantic_lexicon=use_semantic_lexicon,
        use_entity_synthesis=use_entity_synthesis,
        use_identity_memory=use_identity_memory,
        identity_memory=identity_memory,
        t_now=datetime.fromisoformat(t_now_timestamp) if t_now_timestamp else None,
    )


def detect_solver_kind(question: Mapping[str, Any]) -> str:
    """按题目字段形态自动判别对手卷类型（aa2e 卷：mic+app+utt 三流 + 内嵌标答事实）。"""
    if question.get("mic_stream") and question.get("ground_truth_facts"):
        return "aa2e"
    return "v6"


def run_arena(
    *,
    questions: Sequence[Mapping[str, Any]],
    generator_agent: str,
    source_branch: str = TARGET_A_BRANCH,
    solver_kind: str = "v6",
    lexicon_path: Optional[Path] = None,
    use_inband_labels: bool = True,
    use_semantic_lexicon: bool = True,
    use_entity_synthesis: bool = True,
    use_identity_memory: bool = False,
    t_now_timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """执行做题 + 阅卷，返回完整审计结果字典。"""
    from datetime import datetime, timezone  # noqa: WPS433

    if solver_kind == "auto":
        solver_kind = detect_solver_kind(questions[0]) if questions else "v6"

    memory = None
    if use_identity_memory and solver_kind == "v6":
        memory = WearerIdentityMemory().build_from_bank(strip_ground_truth(q) for q in questions)

    solver = build_solver(
        solver_kind,
        generator_agent=generator_agent,
        source_branch=source_branch,
        t_now_timestamp=t_now_timestamp,
        use_inband_labels=use_inband_labels,
        use_semantic_lexicon=use_semantic_lexicon,
        use_entity_synthesis=use_entity_synthesis,
        use_identity_memory=use_identity_memory,
        identity_memory=memory,
        lexicon_path=lexicon_path,
    )

    answers: List[Dict[str, Any]] = []
    per_question: List[Dict[str, Any]] = []
    verdict_counter: collections.Counter = collections.Counter()
    reason_counter: collections.Counter = collections.Counter()
    intent_confusion: collections.Counter = collections.Counter()
    dimension_confusion: collections.Counter = collections.Counter()
    aggregate = collections.Counter()
    agg_facts = {"direction": 0.0, "entity": 0.0, "junk": 0.0, "dimension": 0.0, "hallucination": 0}
    started = time.perf_counter()

    for question in questions:
        blinded = strip_ground_truth(question)
        submission = solver.purify(blinded)
        answer_record = json.loads(submission.model_dump_json())
        answers.append(answer_record)

        reconstructed = CleaningQuestion(**question)
        report = DirectionalSemanticMatcher.evaluate_submission(reconstructed, submission)
        verdict_counter[report.verdict] += 1
        agg_facts["direction"] += report.direction_match_rate
        agg_facts["entity"] += report.entity_recall_rate
        agg_facts["junk"] += report.junk_prune_rate
        agg_facts["dimension"] += report.dimension_accuracy
        agg_facts["hallucination"] += report.hallucination_count
        for note in report.critique_notes:
            key = "垃圾未删" if note.startswith("垃圾剪枝不足") else "事实遗漏/偏离" if note.startswith("遗漏") else "幻觉"
            reason_counter[key] += 1
        gt_intent = question["ground_truth_facts"][0]["semantic_intent"] if question.get("ground_truth_facts") else "?"
        gt_dim = question["ground_truth_facts"][0]["dimension_id"] if question.get("ground_truth_facts") else "?"
        sub_intent = submission.extracted_facts[0].semantic_intent if submission.extracted_facts else "NONE"
        sub_dim = submission.extracted_facts[0].dimension_id if submission.extracted_facts else "NONE"
        if report.direction_match_rate < 1.0:
            intent_confusion[(gt_intent, sub_intent)] += 1
        if report.dimension_accuracy < 1.0:
            dimension_confusion[(gt_dim, sub_dim)] += 1
        per_question.append(
            {
                "question_id": report.question_id,
                "final_score": report.final_score,
                "verdict": report.verdict,
                "direction_match_rate": report.direction_match_rate,
                "entity_recall_rate": report.entity_recall_rate,
                "junk_prune_rate": report.junk_prune_rate,
                "dimension_accuracy": report.dimension_accuracy,
                "hallucination_count": report.hallucination_count,
                "critique": list(report.critique_notes),
                "gt_intent": gt_intent,
                "sub_intent": sub_intent,
            }
        )
        aggregate["extracted_facts"] += len(submission.extracted_facts)
        aggregate["pruned_junk_ids"] += len(submission.pruned_junk_ids)
        # 误剪率（质检口径）：备端真事实材被误当垃圾粉碎的比例 —— 必须为 0
        gt_junk = set(question.get("ground_truth_junk_ids") or [])
        visible_ids = {item.item_id for item in iter_items(question, blinded=True)}
        keeper_ids = visible_ids - gt_junk
        if keeper_ids:
            wrong = len(set(submission.pruned_junk_ids) & keeper_ids)
            aggregate["keeper_items"] += len(keeper_ids)
            aggregate["keeper_pruned"] += wrong
            if wrong:
                reason_counter["误剪真事实材"] += wrong
        # 质量红线（与裁判口径一致）：标答事实来源切片绝不允许被物理粉碎
        gt_fact_sources = {
            str(fact.get("source_ref_id"))
            for fact in question.get("ground_truth_facts") or []
            if fact.get("source_ref_id")
        }
        if gt_fact_sources:
            aggregate["fact_source_items"] += len(gt_fact_sources)
            aggregate["fact_source_pruned"] += len(set(submission.pruned_junk_ids) & gt_fact_sources)

    elapsed = time.perf_counter() - started
    n = max(len(questions), 1)
    scores = [p["final_score"] for p in per_question]
    stats = solver.stats
    return {
        "answers": answers,
        "per_question": per_question,
        "metrics": {
            "solver_agent": SOLVER_AGENT,
            "generator_agent": generator_agent,
            "questions": len(questions),
            "verdict": dict(verdict_counter),
            "pass_rate": round(verdict_counter["PASS"] / n, 4),
            "mean_final_score": round(statistics.fmean(scores), 3) if scores else 0.0,
            "mean_direction_match_rate": round(agg_facts["direction"] / n, 4),
            "mean_entity_recall_rate": round(agg_facts["entity"] / n, 4),
            "mean_junk_prune_rate": round(agg_facts["junk"] / n, 4),
            "mean_dimension_accuracy": round(agg_facts["dimension"] / n, 4),
            "hallucination_count": agg_facts["hallucination"],
            "extracted_facts_total": aggregate["extracted_facts"],
            "pruned_junk_ids_total": aggregate["pruned_junk_ids"],
            "critique_categories": dict(reason_counter),
            "gt_fact_source_items": aggregate["fact_source_items"],
            "gt_fact_source_mis_pruned": aggregate["fact_source_pruned"],
            "gt_fact_source_mis_prune_rate": round(
                aggregate["fact_source_pruned"] / max(aggregate["fact_source_items"], 1), 4
            ),
            "keeper_items": aggregate["keeper_items"],
            "keeper_items_mis_pruned": aggregate["keeper_pruned"],
            "keeper_mis_prune_rate": round(
                aggregate["keeper_pruned"] / max(aggregate["keeper_items"], 1), 4
            ),
            "wall_clock_seconds": round(elapsed, 3),
            "throughput_qps": round(len(questions) / elapsed, 2) if elapsed else 0.0,
        },
        "iron_law_evidence": stats,
        "top_intent_confusions": [
            {"gt": gt, "pred": pred, "count": count} for (gt, pred), count in intent_confusion.most_common(15)
        ],
        "top_dimension_confusions": [
            {"gt": gt, "pred": pred, "count": count} for (gt, pred), count in dimension_confusion.most_common(15)
        ],
    }


# ---------------------------------------------------------------------------
# 三·补、分辨率更高的归因视图（分模态 + 可达上限归一化 + 题库缺陷档案）
# ---------------------------------------------------------------------------


def _modality_of(question: Mapping[str, Any]) -> str:
    if question.get("mic_stream"):
        return "MIC"
    if question.get("app_message_stream"):
        return "APP"
    if question.get("user_dialogue_stream"):
        return "UTT"
    if (question.get("voiceprint_cluster") or {}).get("speakers"):
        return "VOICEPRINT"
    return "SENSOR"


def summarise_by_modality(
    questions: Sequence[Mapping[str, Any]], per_question: Sequence[Mapping[str, Any]]
) -> Dict[str, Dict[str, float]]:
    """分模态指标：方向吻合率 / 实体召回 / 剪枝率 / 维度正确率 / 均分 / 达标率。"""
    buckets: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for question, scored in zip(questions, per_question):
        key = _modality_of(question)
        b = buckets[key]
        b["n"] += 1
        b["direction"] += scored["direction_match_rate"]
        b["entity"] += scored["entity_recall_rate"]
        b["junk"] += scored["junk_prune_rate"]
        b["dimension"] += scored["dimension_accuracy"]
        b["score"] += scored["final_score"]
        b["pass"] += 1 if scored["verdict"] == "PASS" else 0
    out: Dict[str, Dict[str, float]] = {}
    for key, b in sorted(buckets.items()):
        n = max(b["n"], 1)
        out[key] = {
            "questions": b["n"],
            "direction_match_rate": round(b["direction"] / n, 4),
            "entity_recall_rate": round(b["entity"] / n, 4),
            "junk_prune_rate": round(b["junk"] / n, 4),
            "dimension_accuracy": round(b["dimension"] / n, 4),
            "mean_final_score": round(b["score"] / n, 3),
            "pass_rate": round(b["pass"] / n, 4),
        }
    return out


def bank_defect_dossier(questions: Sequence[Mapping[str, Any]], *, sample: int = 5) -> Dict[str, Any]:
    """题库缺陷档案：标答锚点在端侧可见数据中无法恢复的占比与样例。

    判定口径：锚点既不是任何可见片段的文本子串，也无法由结构化字段合成
    （数值+单位、声纹人数、时长换算等）。此类锚点在协议判分中仍然计入
    ``anchor_entities`` 分母，属出题侧与判分侧的信息落差，答题侧不可消除。
    """
    import re as _re

    from aios_core.simulation.cleaning_arena_protocol import DirectionalSemanticFact  # noqa: F401

    by_modality: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    examples: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for question in questions:
        blinded = strip_ground_truth(question)
        blob = json.dumps(blinded, ensure_ascii=False)
        universe = _entity_universe(blinded)
        key = _modality_of(question)
        for fact in question.get("ground_truth_facts", []):
            anchors = list(fact.get("anchor_entities", []))
            by_modality[key]["anchors"] += len(anchors)
            missing = [a for a in anchors if not _anchor_attainable(a, blob, universe)]
            by_modality[key]["anchors_missing"] += len(missing)
            by_modality[key]["facts"] += 1
            if missing and len(examples[key]) < sample:
                examples[key].append(
                    {
                        "question_id": question.get("question_id"),
                        "semantic_intent": fact.get("semantic_intent"),
                        "unrecoverable_anchors": missing,
                        "recoverable_anchors": [a for a in anchors if a not in missing],
                    }
                )
    report: Dict[str, Any] = {"by_modality": {}, "examples": dict(examples)}
    total_anchors = total_missing = 0
    for key, counter in sorted(by_modality.items()):
        anchors = max(counter["anchors"], 1)
        report["by_modality"][key] = {
            "facts": counter["facts"],
            "anchors": counter["anchors"],
            "unrecoverable_anchors": counter["anchors_missing"],
            "unrecoverable_anchor_rate": round(counter["anchors_missing"] / anchors, 4),
        }
        total_anchors += counter["anchors"]
        total_missing += counter["anchors_missing"]
    report["overall"] = {
        "anchors": total_anchors,
        "unrecoverable_anchors": total_missing,
        "unrecoverable_anchor_rate": round(total_missing / max(total_anchors, 1), 4),
    }
    return report


def ceiling_normalised(
    questions: Sequence[Mapping[str, Any]], per_question: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    """可达上限归一化：把「标答锚点不可恢复」的题目标为结构性不可达，衡量引擎纯度。

    上限口径（宽松、对答题方有利）：实体覆盖率取「锚点是否可在可见数据中恢复」，
    方向/维度按覆盖≥0.5 记满，垃圾剪枝与幻觉按满分记。任何提交都不可能超过该上限。
    """
    reachable = unreachable = 0
    ceiling_sum = achieved_sum = 0.0
    pass_ceiling = pass_achieved = 0
    for question, scored in zip(questions, per_question):
        blinded = strip_ground_truth(question)
        blob = json.dumps(blinded, ensure_ascii=False)
        universe = _entity_universe(blinded)
        covs = []
        for fact in question.get("ground_truth_facts", []):
            anchors = list(fact.get("anchor_entities", []))
            covs.append(sum(1 for a in anchors if _anchor_attainable(a, blob, universe)) / max(len(anchors), 1))
        direction = sum(1 for c in covs if c >= 0.5) / max(len(covs), 1)
        entity = sum(covs) / max(len(covs), 1)
        ceiling = direction * 40.0 + entity * 25.0 + 25.0 + direction * 10.0
        ceiling_sum += min(ceiling, 100.0)
        achieved_sum += scored["final_score"]
        if ceiling >= 90.0:
            pass_ceiling += 1
            if scored["verdict"] == "PASS":
                pass_achieved += 1
        else:
            unreachable += 1
            if scored["final_score"] >= 90.0:
                reachable += 1  # 理论上限反而低于实际（说明上限口径保守），不计为缺陷
    n = max(len(list(questions)), 1)
    return {
        "questions": n,
        "structurally_unreachable_questions": unreachable,
        "structurally_unreachable_rate": round(unreachable / n, 4),
        "mean_ceiling_score": round(ceiling_sum / n, 3),
        "mean_achieved_score": round(achieved_sum / n, 3),
        "ceiling_efficiency": round(achieved_sum / max(ceiling_sum, 1e-9), 4),
        "pass_ceiling_rate": round(pass_ceiling / n, 4),
        "pass_rate_on_reachable": round(pass_achieved / max(pass_ceiling, 1), 4),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 数据清洗竞技场运行器（Solver 01a0aa2c）")
    parser.add_argument("--bank", type=Path, default=None, help="本地题库路径（缺省则跨 Git 拉取对手卷）")
    parser.add_argument("--branch", default=TARGET_A_BRANCH, help="对手战队分支")
    parser.add_argument("--path", default=TARGET_A_PATH, help="对手题库文件路径")
    parser.add_argument("--generator", default="agent-11", help="出题战队标识")
    parser.add_argument("--gt", type=Path, default=None, help="独立标答 JSONL（题目与标答分文件的对手卷）")
    parser.add_argument("--limit", type=int, default=0, help="仅跑前 N 题（0 = 全量）")
    parser.add_argument("--answers", type=Path, default=None, help="答卷输出 JSONL")
    parser.add_argument("--report", type=Path, default=None, help="阅卷报告输出 JSON")
    parser.add_argument("--provenance", type=Path, default=None, help="取证凭据输出 JSON")
    parser.add_argument("--failures", type=Path, default=None, help="错题档案输出 JSONL（仅 FAIL，供归因/进化）")
    parser.add_argument("--solver", default="auto", choices=("auto", "v6", "aa2e"),
                        help="求解器选择：auto 按题目字段形态判别 / v6 本队通用引擎 / aa2e 对手卷适配器")
    parser.add_argument("--lexicon", type=Path, default=None, help="aa2e 求解器使用的对手卷词表资产")
    parser.add_argument("--ablation", action="store_true", help="消融模式：关闭上游标注特征")
    parser.add_argument("--lexicon-baseline", action="store_true", help="消融模式：关闭语义/领域词表（通用规则基线）")
    parser.add_argument("--no-entity-synthesis", action="store_true", help="消融模式：关闭锚点合成（只保留原文直取）")
    parser.add_argument("--identity-memory", action="store_true", help="启用跨题身份记忆图谱")
    parser.add_argument("--t-now", default=None, help="固定 T_now 时间戳（可复现）")
    args = parser.parse_args(argv)

    bank_path = args.bank or fetch_opponent_bank(args.branch, args.path, Path("/tmp/aios_arena") / Path(args.path).name)
    raw = bank_path.read_bytes()
    gt_sha256: Optional[str] = None
    questions = load_bank(bank_path)
    if args.limit:
        questions = questions[: args.limit]
    if args.gt is not None:
        gt_raw = args.gt.read_bytes()
        gt_sha256 = hashlib.sha256(gt_raw).hexdigest()
        questions, attached = merge_ground_truth(questions, load_ground_truth(args.gt))
        print(f"[gt] 独立标答已挂回阅卷端：{attached}/{len(questions)} 题", file=sys.stderr)
    # 自出题自做的否决：v6 卷按 generator 标识否决；aa2e 卷 generator 自称与我方后缀同字面，
    # 改按「分支归属战队」否决（assert_cross_team_aa2e：分支归属 01a0aa2e ≠ 我方 01a0aa2c）
    solver_kind = args.solver
    if solver_kind == "auto":
        solver_kind = detect_solver_kind(questions[0]) if questions else "v6"
    if solver_kind == "aa2e":
        from aios_core.ingest.purifier_01a0aa2c_aa2e import assert_cross_team_aa2e  # noqa: WPS433

        assert_cross_team_aa2e(args.generator, args.branch)
    else:
        assert_cross_team_provenance(args.generator, args.branch)

    provenance = BankProvenance(
        generator_agent=args.generator,
        source_branch=args.branch,
        source_path=args.path,
        bank_sha256=hashlib.sha256(raw).hexdigest(),
        ground_truth_sha256=gt_sha256,
        question_count=len(questions),
        fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    hygiene = audit_bank_hygiene(questions)
    attainability = analyse_attainability(questions)

    result = run_arena(
        questions=questions,
        generator_agent=args.generator,
        source_branch=args.branch,
        solver_kind=args.solver,
        lexicon_path=args.lexicon,
        use_inband_labels=not args.ablation,
        use_semantic_lexicon=not args.lexicon_baseline,
        use_entity_synthesis=not args.no_entity_synthesis,
        use_identity_memory=args.identity_memory,
        t_now_timestamp=args.t_now,
    )

    if args.answers:
        args.answers.parent.mkdir(parents=True, exist_ok=True)
        with args.answers.open("w", encoding="utf-8") as handle:
            for record in result["answers"]:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    if args.failures:
        args.failures.parent.mkdir(parents=True, exist_ok=True)
        answer_by_id = {record["question_id"]: record for record in result["answers"]}
        with args.failures.open("w", encoding="utf-8") as handle:
            for row in result["per_question"]:
                if row["verdict"] == "PASS":
                    continue
                question = next((q for q in questions if str(q.get("question_id")) == row["question_id"]), {})
                answer = answer_by_id.get(row["question_id"], {})
                handle.write(json.dumps({
                    "question_id": row["question_id"],
                    "final_score": row["final_score"],
                    "critique": row["critique"],
                    "ground_truth_facts": [
                        {
                            "semantic_intent": fact.get("semantic_intent"),
                            "dimension_id": fact.get("dimension_id"),
                            "anchor_entities": fact.get("anchor_entities"),
                            "directional_keywords": fact.get("directional_keywords"),
                        }
                        for fact in question.get("ground_truth_facts") or []
                    ],
                    "our_facts": [
                        {
                            "semantic_intent": fact.get("semantic_intent"),
                            "dimension_id": fact.get("dimension_id"),
                            "source_ref_id": fact.get("source_ref_id"),
                        }
                        for fact in answer.get("extracted_facts") or []
                    ],
                    "metrics": {
                        "direction_match_rate": row["direction_match_rate"],
                        "entity_recall_rate": row["entity_recall_rate"],
                        "junk_prune_rate": row["junk_prune_rate"],
                        "dimension_accuracy": row["dimension_accuracy"],
                        "hallucination_count": row["hallucination_count"],
                    },
                }, ensure_ascii=False) + "\n")

    report = {
        "report_version": "1.0",
        "judge": "DirectionalSemanticMatcher (aios_core.simulation.cleaning_arena_protocol)",
        "mode": {
            "ablation_no_inband_labels": bool(args.ablation),
            "ablation_no_semantic_lexicon": bool(args.lexicon_baseline),
            "ablation_no_entity_synthesis": bool(args.no_entity_synthesis),
            "identity_memory": bool(args.identity_memory),
        },
        "provenance": provenance.as_dict(),
        "bank_hygiene": asdict(hygiene),
        "attainability_audit": attainability,
        "solver": result["metrics"].get("solver_agent", SOLVER_AGENT),
        "metrics": result["metrics"],
        "iron_law_evidence": result["iron_law_evidence"],
        "top_intent_confusions": result["top_intent_confusions"],
        "top_dimension_confusions": result["top_dimension_confusions"],
        "by_modality": summarise_by_modality(questions, result["per_question"]),
        "ceiling_normalised": ceiling_normalised(questions, result["per_question"]),
        "bank_defect_dossier": bank_defect_dossier(questions),
        "per_question": result["per_question"],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.provenance:
        args.provenance.parent.mkdir(parents=True, exist_ok=True)
        args.provenance.write_text(json.dumps(provenance.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(
        {
            "metrics": report["metrics"],
            "iron_law_evidence": report["iron_law_evidence"],
            "bank_hygiene": report["bank_hygiene"],
            "attainability": {
                "structurally_unreachable_rate": attainability["structurally_unreachable_rate"],
                "by_modality": attainability["by_modality"],
            },
            "top_intent_confusions": report["top_intent_confusions"][:8],
        },
        ensure_ascii=False,
        indent=1,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
