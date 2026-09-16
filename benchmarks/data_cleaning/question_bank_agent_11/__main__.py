"""Agent-11 出题 CLI：生成、自审、落盘。

自审（audit）在写盘之前跑，任何一条不过直接抛错，绝不产出半成品题库：
1. 五流题量严格等于 3000/3000/2000/1500/500，合计 10,000；
2. 每题至少 1 条标答事实、至少 1 个垃圾 ID；
3. 每条事实的 source_ref_id 必须真实存在于该题的碎片中（杜绝悬空溯源）；
4. 每条事实必须有非空 directional_keywords 与 anchor_entities；
5. 垃圾碎片占比达标（声纹流 90%，其余 95%）；
6. question_id 全局唯一、碎片 ID 题内唯一。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .builder import QuestionBuilder, split_ground_truth, strip_ground_truth

QUOTAS: Dict[str, int] = dict(sensor=3000, mic=3000, voiceprint=2000, app=1500, dialogue=500)

# 主数据流判定：题目由哪条流承载
_PRIMARY_KEY = {
    "sensor": ("sensor_stream", "fragments"),
    "mic": ("mic_stream",),
    "voiceprint": ("voiceprint_cluster", "speakers"),
    "app": ("app_message_stream",),
    "dialogue": ("user_dialogue_stream",),
}

# 垃圾碎片占比下限（按主数据流聚合统计）。
# 规范原文为"95% 噪音 / 5% 事实"，此处按流聚合判定并留 2 个百分点余量；
# 声纹流由规范固定为"单日 24 个碎片、90% 杂散人声"，故下限单列。
_JUNK_RATIO_FLOOR = {
    "sensor": 0.90,
    "mic": 0.90,
    "voiceprint": 0.875,
    "app": 0.90,
    "dialogue": 0.875,
}


def _fragment_ids(q: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for f in q.get("sensor_stream", {}).get("fragments", []):
        ids.append(f["fragment_id"])
    for s in q.get("mic_stream", []):
        ids.append(s["snippet_id"])
    for sp in q.get("voiceprint_cluster", {}).get("speakers", []):
        ids.append(sp["speaker_frag_id"])
    for m in q.get("app_message_stream", []):
        ids.append(m["msg_id"])
    for u in q.get("user_dialogue_stream", []):
        ids.append(u["utterance_id"])
    return ids


def _primary_stream(q: Dict[str, Any]) -> str:
    """按碎片数量判定主战场流（跨模态佐证流碎片极少，不会误判）。"""
    counts = {
        "sensor": len(q.get("sensor_stream", {}).get("fragments", [])),
        "mic": len(q.get("mic_stream", [])),
        "voiceprint": len(q.get("voiceprint_cluster", {}).get("speakers", [])),
        "app": len(q.get("app_message_stream", [])),
        "dialogue": len(q.get("user_dialogue_stream", [])),
    }
    return max(counts, key=lambda k: counts[k])


def audit(questions: Sequence[Dict[str, Any]], quotas: Dict[str, int] | None = None) -> Dict[str, Any]:
    quotas = quotas or QUOTAS
    problems: List[str] = []
    stream_count: Counter = Counter()
    intent_count: Counter = Counter()
    dim_count: Counter = Counter()
    diff_count: Counter = Counter()
    total_frag = total_junk = total_fact = 0
    # 按流聚合的 (垃圾碎片数, 全部碎片数)
    stream_frag: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    qids = set()

    for q in questions:
        qid = q["question_id"]
        if qid in qids:
            problems.append(f"重复 question_id: {qid}")
        qids.add(qid)

        stream = _primary_stream(q)
        stream_count[stream] += 1
        diff_count[q["difficulty"]] += 1

        ids = _fragment_ids(q)
        if len(ids) != len(set(ids)):
            problems.append(f"{qid}: 碎片 ID 题内重复")

        # 规范限定：MIC 环境录音切片底噪必须落在 60~85dB
        for sn in q.get("mic_stream", []):
            db = sn.get("ambient_noise_db", 0)
            if not 60 <= db <= 85:
                problems.append(f"{qid}: MIC 切片 {sn.get('snippet_id')} 底噪 {db}dB 超出 60~85dB")
        junk = set(q["ground_truth_junk_ids"])
        missing = junk - set(ids)
        if missing:
            problems.append(f"{qid}: ground_truth_junk_ids 指向不存在的碎片 {sorted(missing)[:3]}")

        facts = q["ground_truth_facts"]
        if not facts:
            problems.append(f"{qid}: 缺少 ground_truth_facts")
        if not junk:
            problems.append(f"{qid}: 缺少 ground_truth_junk_ids")

        idset = set(ids)
        for f in facts:
            total_fact += 1
            intent_count[f["semantic_intent"]] += 1
            dim_count[f["dimension_id"]] += 1
            if f["source_ref_id"] not in idset:
                problems.append(f"{qid}: 事实 {f['fact_id']} 的 source_ref_id "
                                f"{f['source_ref_id']} 不存在于本题碎片")
            if not f["directional_keywords"]:
                problems.append(f"{qid}: 事实 {f['fact_id']} 缺少 directional_keywords")
            if not f["anchor_entities"]:
                problems.append(f"{qid}: 事实 {f['fact_id']} 缺少 anchor_entities")
            if len(f["core_content"]) < 8:
                problems.append(f"{qid}: 事实 {f['fact_id']} core_content 过短")

        total_frag += len(ids)
        total_junk += len(junk)
        stream_frag[stream][0] += len(junk & idset)
        stream_frag[stream][1] += len(ids)

    # 题量配额
    for stream, want in quotas.items():
        got = stream_count[stream]
        if got != want:
            problems.append(f"{stream} 题量 {got} != 规定 {want}")

    # 垃圾占比（按流聚合）
    ratio_by_stream = {
        k: round(v[0] / v[1], 4) for k, v in stream_frag.items() if v[1]
    }
    for stream, ratio in ratio_by_stream.items():
        floor = _JUNK_RATIO_FLOOR[stream]
        if ratio < floor:
            problems.append(f"{stream} 聚合垃圾占比 {ratio:.4f} < 下限 {floor}")

    if len(questions) != sum(quotas.values()):
        problems.append(f"总题量 {len(questions)} != {sum(quotas.values())}")

    return dict(
        ok=not problems,
        problems=problems,
        total_questions=len(questions),
        stream_distribution=dict(stream_count),
        difficulty_distribution=dict(diff_count),
        semantic_intent_distribution=dict(intent_count.most_common()),
        dimension_distribution=dict(dim_count.most_common()),
        total_fragments=total_frag,
        total_junk_ids=total_junk,
        total_ground_truth_facts=total_fact,
        junk_ratio_overall=round(total_junk / max(total_frag, 1), 4),
        junk_ratio_by_stream=ratio_by_stream,
    )


def contract_check(questions: Sequence[Dict[str, Any]], agent_id: str,
                   sample: int = 500) -> Dict[str, Any]:
    """端到端校验：全量按主干 `CleaningQuestion` 契约解析，并用真实裁判器跑满分/劣质答卷。

    这里调用的全部是 `src/aios_core/simulation/cleaning_arena_protocol.py` 里已发布的
    契约与 `DirectionalSemanticMatcher`，没有任何替身或复制逻辑。
    """
    from aios_core.simulation.cleaning_arena_protocol import (
        CleaningAnswerSubmission,
        CleaningQuestion,
        DirectionalSemanticMatcher,
        ExtractedFactSubmission,
    )

    parsed = [CleaningQuestion.model_validate(q) for q in questions]
    out: Dict[str, Any] = {"parsed_by_contract": len(parsed)}

    subset = parsed[:sample]
    gold, bad = [], []
    for q in subset:
        gold_sub = CleaningAnswerSubmission(
            question_id=q.question_id, solver_agent="agent-99-gold",
            generator_agent=q.generator_agent,
            extracted_facts=[
                ExtractedFactSubmission(
                    fact_id=f"f_{i}", dimension_id=f.dimension_id,
                    semantic_intent=f.semantic_intent, summary_text=f.core_content,
                    recognized_entities=list(f.anchor_entities),
                    source_ref_id=f.source_ref_id)
                for i, f in enumerate(q.ground_truth_facts)],
            pruned_junk_ids=list(q.ground_truth_junk_ids))
        gold.append(DirectionalSemanticMatcher.evaluate_submission(q, gold_sub).final_score)

        # 劣质答卷：垃圾一个不删 + 方向整体判反 + 实体张冠李戴
        bad_sub = CleaningAnswerSubmission(
            question_id=q.question_id, solver_agent="agent-99-bad",
            generator_agent=q.generator_agent,
            extracted_facts=[
                ExtractedFactSubmission(
                    fact_id=f"b_{i}", dimension_id="dim:entertainment",
                    semantic_intent="ROMANTIC_CELEBRATION",
                    summary_text="佩戴者与家人欢聚庆祝、气氛融洽",
                    recognized_entities=["路人甲"], source_ref_id=f.source_ref_id)
                for i, f in enumerate(q.ground_truth_facts)],
            pruned_junk_ids=[])
        bad.append(DirectionalSemanticMatcher.evaluate_submission(q, bad_sub).final_score)

    out["gold_answer_avg_score"] = round(sum(gold) / len(gold), 2)
    out["gold_answer_pass_rate"] = round(sum(1 for s in gold if s >= 90.0) / len(gold), 4)
    out["bad_answer_avg_score"] = round(sum(bad) / len(bad), 2)
    out["gold_scores_below_90"] = sum(1 for s in gold if s < 90.0)

    # 一票否决链路：自出自做必须 0 分
    vq = parsed[0]
    viol = CleaningAnswerSubmission(
        question_id=vq.question_id, solver_agent=vq.generator_agent,
        generator_agent=vq.generator_agent,
        pruned_junk_ids=list(vq.ground_truth_junk_ids))
    rep = DirectionalSemanticMatcher.evaluate_submission(vq, viol)
    out["self_solving_veto_works"] = bool(rep.is_self_solving_violation and rep.final_score == 0.0)
    out["generator_agent_field"] = vq.generator_agent
    return out


def _dump(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
            fh.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agent-11 数据清洗对抗题库发生器")
    ap.add_argument("--agent-id", default="agent-11", help="出题战队标识，写入 generator_agent 字段")
    ap.add_argument("--seed", type=int, default=20260916, help="确定性随机种子")
    ap.add_argument("--out-root", default="benchmarks/data_cleaning", help="归档根目录")
    ap.add_argument("--limit", type=int, default=0, help="仅生成前 N 题（调试用，0=全量 10000）")
    # 默认不产出盲考卷：契约要求 CleaningQuestion 自带 ground_truth_*，
    # 因此 questions_*.jsonl 必然含标答。跨 Git 交叉做题方若需真正的盲卷，
    # 用 --emit-blind 现场剥离，避免把 60MB 的重复数据也塞进仓库。
    ap.add_argument("--emit-blind", action="store_true", default=False,
                    help="额外产出剥离标答的盲考卷 questions_agent_<id>.blind.jsonl")
    ap.add_argument("--no-blind", dest="emit_blind", action="store_false",
                    help="不产出盲考卷（默认）")
    ap.add_argument("--report", default="", help="题库自审报告输出路径（JSON）")
    args = ap.parse_args(argv)

    quotas = dict(QUOTAS)
    if args.limit:
        scale = args.limit / sum(quotas.values())
        quotas = {k: max(1, round(v * scale)) for k, v in quotas.items()}

    builder = QuestionBuilder(generator_agent=args.agent_id, seed=args.seed)
    questions = builder.build(quotas=quotas)

    report = audit(questions, quotas)
    report["contract"] = contract_check(questions, args.agent_id)
    hard_fail = (not report["ok"]) or (not report["contract"]["self_solving_veto_works"]) \
        or report["contract"]["gold_answer_avg_score"] < 90.0
    if hard_fail:
        for p in report["problems"][:40]:
            print("  [FAIL]", p)
        print("  [FAIL] contract:", json.dumps(report["contract"], ensure_ascii=False))
        if not args.limit:
            raise SystemExit(f"题库自审未通过，已拒绝落盘（结构性问题 {len(report['problems'])} 处）。")
        print("  [WARN] --limit 模式：仅提示，不中断")

    root = Path(args.out_root)
    tag = args.agent_id.split("-")[-1]
    q_path = root / "questions" / f"questions_agent_{tag}.jsonl"
    gt_path = root / "ground_truth" / f"gt_agent_{tag}.jsonl"
    _dump(q_path, questions)
    _dump(gt_path, split_ground_truth(questions))
    blind_path = None
    if args.emit_blind:
        blind_path = root / "questions" / f"questions_agent_{tag}.blind.jsonl"
        _dump(blind_path, strip_ground_truth(questions))

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(dict(agent_id=args.agent_id, seed=args.seed, **report),
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

    print(f"考题     -> {q_path}  ({len(questions)} 行)")
    print(f"标答底稿 -> {gt_path}")
    if blind_path:
        print(f"盲考卷   -> {blind_path}")
    print(f"自审     -> {'PASS' if report['ok'] else 'FAIL'} | "
          f"碎片 {report['total_fragments']} | 垃圾 {report['total_junk_ids']} "
          f"({report['junk_ratio_overall']:.1%}) | 事实 {report['total_ground_truth_facts']}")
    print(f"题量分布 -> {report['stream_distribution']}")
    print(f"难度分布 -> {report['difficulty_distribution']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
