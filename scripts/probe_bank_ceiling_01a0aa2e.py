#!/usr/bin/env python3
"""对手题库"阅卷天花板探针"（战队 ``01a0aa2e`` 的第四阶段归因工具）。

为什么需要它
------------
交叉做题的得分不只取决于答题方，还取决于出题方把多少标答信息真的写进了题面。
本脚本量化三件事，用来把"我们清洗得不好"与"标答在题面里根本不可达"分开：

1. ``directional_keyword_visible``：标答方向词是否出现在题面（阅卷靠方向判定）；
2. ``anchor_entity_visible``：标答实体锚点是否出现在题面；
3. ``entity_gate_reachable``：单条事实的可见实体占比能否达到阅卷器要求的 50% 门槛
   （``DirectionalSemanticMatcher.is_direction_aligned`` 里 ``entity_overlap >= 0.5``
   是硬门槛，达不到就一票判为方向偏离，与意图是否判对无关）；
4. ``oracle_score``：**天花板探针**——直接借用标答的维度与意图、但实体只允许从
   被引用碎片的可见文本里抽取，垃圾全剪。它不是提交结果，只用于回答
   "一个不犯任何分类错误的清洗器，在这套题上最多能拿多少分"。

用法
----
    python scripts/probe_bank_ceiling_01a0aa2e.py \
        --questions .cache/inbound/questions_agent_11.jsonl \
        --ground-truth .cache/inbound/gt_agent_11.jsonl \
        --generator-id agent_11 --limit 2000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.ingest.purifier_01a0aa2e import (  # noqa: E402
    SliceItem,
    extract_entities,
    strip_answer_leak,
)
from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningAnswerSubmission,
    CleaningQuestion,
    DirectionalSemanticMatcher,
    ExtractedFactSubmission,
)

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from run_cleaning_arena_01a0aa2e import build_question, iter_jsonl, load_ground_truth  # noqa: E402


def _items_by_id(payload: Dict[str, Any]) -> Dict[str, Mapping]:
    index: Dict[str, Any] = {}
    sensor = payload.get("sensor_stream") or {}
    if isinstance(sensor, dict):
        for key in ("fragments", "segments"):
            for record in sensor.get(key) or []:
                if isinstance(record, dict):
                    index[str(record.get("fragment_id") or record.get("seg_id"))] = record
    for record in payload.get("mic_stream") or []:
        index[str(record.get("snippet_id"))] = record
    for record in payload.get("app_message_stream") or []:
        index[str(record.get("msg_id"))] = record
    for record in payload.get("user_dialogue_stream") or []:
        index[str(record.get("utterance_id"))] = record
    voice = payload.get("voiceprint_cluster") or {}
    if isinstance(voice, dict):
        for key, id_key in (("speakers", "speaker_frag_id"), ("detected_speakers", "spk_id")):
            for record in voice.get(key) or []:
                if isinstance(record, dict):
                    index[str(record.get(id_key))] = record
    return index


def _visible_text(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    return json.dumps(strip_answer_leak(record), ensure_ascii=False)


def probe(args: argparse.Namespace) -> Dict[str, Any]:
    ground_truth = load_ground_truth(Path(args.ground_truth).resolve() if args.ground_truth else None)
    facts_total = 0
    keyword_visible = 0
    entity_total = 0
    entity_visible = 0
    gate_reachable = 0
    keyword_in_cited_item = 0
    scores: List[float] = []

    for payload in iter_jsonl(Path(args.questions).resolve()):
        if args.limit and facts_total and len(scores) >= args.limit:
            break
        gt = ground_truth.get(str(payload.get("question_id")))
        question = build_question(payload, gt)
        if question is None:
            continue
        visible = strip_answer_leak(payload)
        payload_text = json.dumps(visible, ensure_ascii=False)
        index = _items_by_id(visible)

        oracle_facts: List[ExtractedFactSubmission] = []
        for fact in question.ground_truth_facts:
            facts_total += 1
            entities = [entity for entity in fact.anchor_entities if entity]
            hits = [entity for entity in entities if entity in payload_text]
            entity_total += len(entities)
            entity_visible += len(hits)
            if any(keyword and keyword in payload_text for keyword in fact.directional_keywords):
                keyword_visible += 1
            overlap = len(hits) / max(len(entities), 1)
            if overlap >= 0.5 or not entities:
                gate_reachable += 1
            cited = _visible_text(index.get(fact.source_ref_id))
            if cited and any(keyword and keyword in cited for keyword in fact.directional_keywords):
                keyword_in_cited_item += 1

            item = index.get(fact.source_ref_id)
            text = " ".join(
                str(value)
                for value in (item or {}).values()
                if isinstance(value, (str, int, float))
            ) if isinstance(item, dict) else ""
            slice_item = SliceItem(
                item_id=fact.source_ref_id,
                modality="probe",
                text=text,
                metrics={k: v for k, v in (item or {}).items() if isinstance(v, (int, float))},
                raw=item or {},
            )
            oracle_facts.append(
                ExtractedFactSubmission(
                    fact_id=f"ORACLE_{fact.fact_id}",
                    dimension_id=fact.dimension_id,
                    semantic_intent=fact.semantic_intent,
                    summary_text=text[:200],
                    recognized_entities=list(extract_entities([slice_item], {}, include_wearer=True)),
                    source_ref_id=fact.source_ref_id,
                )
            )

        submission = CleaningAnswerSubmission(
            question_id=question.question_id,
            solver_agent="oracle-probe",
            generator_agent=question.generator_agent,
            extracted_facts=oracle_facts,
            pruned_junk_ids=list(question.ground_truth_junk_ids),
        )
        report = DirectionalSemanticMatcher.evaluate_submission(question, submission)
        scores.append(report.final_score)

    n = max(facts_total, 1)
    q = max(len(scores), 1)
    return {
        "generator_agent": args.generator_id,
        "questions_probed": len(scores),
        "ground_truth_facts": facts_total,
        "directional_keyword_visible_in_payload": round(keyword_visible / n, 4),
        "directional_keyword_visible_in_cited_item": round(keyword_in_cited_item / n, 4),
        "anchor_entity_visible_in_payload": round(entity_visible / max(entity_total, 1), 4),
        "entity_gate_reachable_ratio": round(gate_reachable / n, 4),
        "oracle_mean_score": round(sum(scores) / q, 2),
        "oracle_pass_rate": round(sum(1 for s in scores if s >= 90.0) / q, 4),
        "reading": (
            "oracle 探针借用标答的维度/意图、实体只从被引用碎片可见文本抽取、垃圾全剪；"
            "它给出的是'分类零失误'情形下的得分上限，不是本战队的提交结果。"
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="对手题库阅卷天花板探针")
    parser.add_argument("--questions", required=True)
    parser.add_argument("--ground-truth", default=None)
    parser.add_argument("--generator-id", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=None, help="可选：把探针结果写入 json 文件")
    args = parser.parse_args(argv)
    result = probe(args)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
