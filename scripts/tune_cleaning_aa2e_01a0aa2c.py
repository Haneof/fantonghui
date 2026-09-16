#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对手卷求解器调参台 · 战队 ``01a0aa2c-fantonghui``

用途：在**跨 Git 交叉做题**过程中，用可见的对手题库切片做小样本评估，
验证「证据强度阶梯 / 跨切片互证 / 垃圾剪枝」等旋钮的收益，避免凭感觉调参。

用法示例::

    # 单组配置（对 2000:3000 切片）
    python scripts/tune_cleaning_aa2e_01a0aa2c.py --bank <bank.jsonl> --lexicon <lex.json> \
        --slice 2000:3000 --knobs '{"STRONG_CUE_SCORE": 1.5}'

    # 单旋钮扫描
    python scripts/tune_cleaning_aa2e_01a0aa2c.py --bank <bank.jsonl> --lexicon <lex.json> \
        --slice 2000:3000 --sweep 'STRONG_CUE_SCORE=1.0,1.2,1.5,1.8'

评估口径与裁判端 :class:`DirectionalSemanticMatcher` 完全一致（方向 / 实体 / 垃圾 / 维度 / 幻觉）。
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.ingest.purifier_01a0aa2c import strip_ground_truth  # noqa: E402
from aios_core.ingest.purifier_01a0aa2c_aa2e import DEFAULT_LEXICON, CleaningSolver01a0aa2cAa2e  # noqa: E402
from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningQuestion,
    DirectionalSemanticMatcher,
)

DEFAULT_BANK = REPO_ROOT / "benchmarks" / "data_cleaning" / "questions" / "questions_fantonghui_aa2e.jsonl"


def load_slice(bank: Path, span: str) -> List[Mapping[str, Any]]:
    start_text, _, end_text = span.partition(":")
    start, end = int(start_text or 0), int(end_text or 0)
    questions: List[Mapping[str, Any]] = []
    with bank.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if end and index >= end:
                break
            if index < start or not line.strip():
                continue
            questions.append(json.loads(line))
    return questions


def evaluate(
    questions: Sequence[Mapping[str, Any]],
    *,
    lexicon_path: Path,
    knobs: Mapping[str, Any],
    per_question_samples: int = 0,
) -> Dict[str, Any]:
    for name, value in knobs.items():
        setattr(CleaningSolver01a0aa2cAa2e, name, value)
    solver = CleaningSolver01a0aa2cAa2e(lexicon_path=lexicon_path)

    scores: List[float] = []
    directions: List[float] = []
    entities: List[float] = []
    junks: List[float] = []
    dimensions: List[float] = []
    hallucinations = 0
    passed = 0
    bucket = collections.defaultdict(list)
    samples: List[Dict[str, Any]] = []
    gt_total = 0
    gt_hit = 0

    for question in questions:
        submission = solver.purify(strip_ground_truth(question))
        report = DirectionalSemanticMatcher.evaluate_submission(CleaningQuestion(**question), submission)
        scores.append(report.final_score)
        directions.append(report.direction_match_rate)
        entities.append(report.entity_recall_rate)
        junks.append(report.junk_prune_rate)
        dimensions.append(report.dimension_accuracy)
        hallucinations += report.hallucination_count
        passed += 1 if report.verdict == "PASS" else 0
        bucket[(len(question.get("ground_truth_facts") or []), len(submission.extracted_facts))].append(report.final_score)
        got = {(fact.semantic_intent, fact.dimension_id) for fact in submission.extracted_facts}
        for fact in question.get("ground_truth_facts") or []:
            gt_total += 1
            if (fact.get("semantic_intent"), fact.get("dimension_id")) in got:
                gt_hit += 1
        if len(samples) < per_question_samples:
            samples.append({
                "question_id": submission.question_id,
                "gt_facts": [(f.get("semantic_intent"), f.get("dimension_id")) for f in question.get("ground_truth_facts") or []],
                "our_facts": [(f.semantic_intent, f.dimension_id) for f in submission.extracted_facts],
                "score": report.final_score,
                "critique": report.critique_notes,
            })

    return {
        "n": len(questions),
        "mean": round(statistics.fmean(scores), 3) if scores else 0.0,
        "pass_rate": round(passed / len(questions), 4) if questions else 0.0,
        "direction": round(statistics.fmean(directions), 4) if directions else 0.0,
        "entity": round(statistics.fmean(entities), 4) if entities else 0.0,
        "junk": round(statistics.fmean(junks), 4) if junks else 0.0,
        "dimension": round(statistics.fmean(dimensions), 4) if dimensions else 0.0,
        "hallucination": hallucinations,
        "fact_recall": round(gt_hit / gt_total, 4) if gt_total else 0.0,
        "buckets": {f"gt{k[0]}_our{k[1]}": round(statistics.fmean(v), 2) for k, v in sorted(bucket.items())},
        "buckets_n": {f"gt{k[0]}_our{k[1]}": len(v) for k, v in sorted(bucket.items())},
        "samples": samples,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="对手卷求解器调参台（评估口径与裁判端一致）")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--lexicon", type=Path, default=None)
    parser.add_argument("--slice", dest="span", default="2000:3000", help="评估切片 start:end")
    parser.add_argument("--knobs", default="{}", help="JSON 字典形式的旋钮覆盖")
    parser.add_argument("--sweep", default="", help="单旋钮扫描，如 STRONG_CUE_SCORE=1.0,1.2,1.5")
    parser.add_argument("--samples", type=int, default=0, help="附带打印 N 道错题样本")
    args = parser.parse_args(argv)

    lexicon_path = args.lexicon or DEFAULT_LEXICON
    questions = load_slice(args.bank, args.span)
    base = json.loads(args.knobs)

    configs: List[Dict[str, Any]] = []
    if args.sweep:
        name, _, values = args.sweep.partition("=")
        for raw in values.split(","):
            knob = dict(base)
            knob[name] = float(raw) if "." in raw else int(raw)
            configs.append(knob)
    else:
        configs.append(base)

    for knob in configs:
        metrics = evaluate(questions, lexicon_path=lexicon_path, knobs=knob, per_question_samples=args.samples)
        print(json.dumps({"knobs": knob, **metrics}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
