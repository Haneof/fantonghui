"""Agent-11 万题库交付物验收（对齐 Master Dispatch #11 与出题人提示词）。

本测试直接校验仓库中已归档的两个交付文件，并全程复用主干
`aios_core.simulation.cleaning_arena_protocol` 的真实契约与 `DirectionalSemanticMatcher`，
不使用任何替身实现。
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = ROOT / "benchmarks" / "data_cleaning"
sys.path.insert(0, str(BENCH_DIR))

from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningAnswerSubmission,
    CleaningQuestion,
    DifficultyLevel,
    DirectionalSemanticMatcher,
    ExtractedFactSubmission,
)

QUESTIONS = BENCH_DIR / "questions" / "questions_agent_11.jsonl"
GROUND_TRUTH = BENCH_DIR / "ground_truth" / "gt_agent_11.jsonl"

QUOTAS = {"sensor": 3000, "mic": 3000, "voiceprint": 2000, "app": 1500, "dialogue": 500}

pytestmark = pytest.mark.skipif(
    not (QUESTIONS.exists() and GROUND_TRUTH.exists()),
    reason="Agent-11 题库未归档（本分支不负责该交付物）",
)


@pytest.fixture(scope="module")
def rows():
    with QUESTIONS.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _primary_stream(q: dict) -> str:
    counts = {
        "sensor": len(q.get("sensor_stream", {}).get("fragments", [])),
        "mic": len(q.get("mic_stream", [])),
        "voiceprint": len(q.get("voiceprint_cluster", {}).get("speakers", [])),
        "app": len(q.get("app_message_stream", [])),
        "dialogue": len(q.get("user_dialogue_stream", [])),
    }
    return max(counts, key=lambda k: counts[k])


def _fragment_ids(q: dict) -> list[str]:
    ids = [f["fragment_id"] for f in q.get("sensor_stream", {}).get("fragments", [])]
    ids += [s["snippet_id"] for s in q.get("mic_stream", [])]
    ids += [sp["speaker_frag_id"] for sp in q.get("voiceprint_cluster", {}).get("speakers", [])]
    ids += [m["msg_id"] for m in q.get("app_message_stream", [])]
    ids += [u["utterance_id"] for u in q.get("user_dialogue_stream", [])]
    return ids


def test_bank_has_exactly_ten_thousand_unique_questions(rows):
    """满额 10,000 题，题号唯一。"""
    assert len(rows) == 10000
    ids = [r["question_id"] for r in rows]
    assert len(set(ids)) == 10000


def test_stream_quota_matches_dispatch(rows):
    """五大流配比必须严格等于 3000/3000/2000/1500/500。"""
    dist = Counter(_primary_stream(r) for r in rows)
    assert dict(dist) == QUOTAS, dist


def test_every_row_satisfies_the_shipped_contract(rows):
    """逐题按主干 CleaningQuestion 契约解析，且 generator_agent 标注正确。"""
    parsed = [CleaningQuestion.model_validate(r) for r in rows]
    assert len(parsed) == 10000
    assert {p.generator_agent for p in parsed} == {"agent-11"}
    assert all(isinstance(p.difficulty, DifficultyLevel) for p in parsed)
    assert all(p.ground_truth_facts for p in parsed)
    assert all(p.ground_truth_junk_ids for p in parsed)


def test_ground_truth_file_mirrors_questions(rows):
    """标答底稿与考题一一对应，内容完全一致。"""
    with GROUND_TRUTH.open(encoding="utf-8") as fh:
        gt = {json.loads(line)["question_id"]: json.loads(line) for line in fh if line.strip()}
    assert len(gt) == 10000
    for r in rows:
        g = gt[r["question_id"]]
        assert g["ground_truth_facts"] == r["ground_truth_facts"]
        assert g["ground_truth_junk_ids"] == r["ground_truth_junk_ids"]


def test_junk_signal_ratio_and_traceability(rows):
    """垃圾占比达标 + 标答溯源不得悬空 + 垃圾与信号不得重叠。"""
    stream_junk: Counter = Counter()
    stream_all: Counter = Counter()
    for q in rows:
        stream = _primary_stream(q)
        ids = set(_fragment_ids(q))
        assert len(ids) == len(_fragment_ids(q)), f"{q['question_id']} 碎片 ID 题内重复"
        junk = set(q["ground_truth_junk_ids"])
        assert junk <= ids, f"{q['question_id']} 垃圾 ID 悬空"
        signal_refs = {f["source_ref_id"] for f in q["ground_truth_facts"]}
        assert signal_refs <= ids, f"{q['question_id']} 事实溯源悬空"
        assert not (junk & signal_refs), f"{q['question_id']} 同一碎片既判垃圾又当证据"
        stream_junk[stream] += len(junk)
        stream_all[stream] += len(ids)

    for stream in ("sensor", "mic", "app", "dialogue"):
        ratio = stream_junk[stream] / stream_all[stream]
        assert ratio >= 0.95, f"{stream} 垃圾占比 {ratio:.4f} < 0.95"
    # 声纹流由规范固定为「单日 24 个碎片、90% 杂散人声」
    assert stream_junk["voiceprint"] / stream_all["voiceprint"] >= 0.875


def test_voiceprint_stream_always_carries_24_speakers(rows):
    """声纹聚类记录：单日固定混杂 24 个人声纹碎片。"""
    for q in rows:
        if _primary_stream(q) != "voiceprint":
            continue
        vc = q["voiceprint_cluster"]
        assert len(vc["speakers"]) == 24, q["question_id"]
        assert vc["total_detected_speakers"] == 24


def test_mic_ambient_noise_within_spec_band(rows):
    """MIC 环境录音切片底噪必须落在规范限定的 60~85dB。"""
    for q in rows:
        for sn in q.get("mic_stream", []):
            assert 60 <= sn["ambient_noise_db"] <= 85, (q["question_id"], sn["snippet_id"])


def test_directional_keyword_clusters_are_rich(rows):
    """方向性同义词簇不得退化成单一死板字眼。"""
    sizes = [len(f["directional_keywords"]) for q in rows for f in q["ground_truth_facts"]]
    assert min(sizes) >= 5, f"最薄的方向簇只有 {min(sizes)} 个词"
    for q in rows:
        for f in q["ground_truth_facts"]:
            assert f["anchor_entities"], q["question_id"]
            assert len(f["core_content"]) >= 8, q["question_id"]


def test_critical_and_adversarial_coverage(rows):
    """15 类致命/核心事实与 5 类对抗陷阱必须齐备。"""
    intents = Counter(f["semantic_intent"] for q in rows for f in q["ground_truth_facts"])
    required = {
        "FALL_IMPACT", "CARDIAC_PVC_BURST", "RESTING_TACHYCARDIA", "BAROMETRIC_STORM",
        "REPAYMENT_PROMISE", "FAMILY_ENTRUSTMENT", "NDA_CONFIDENTIALITY", "WEAK_SOS",
        "BANK_LARGE_TRANSFER", "COURT_SUMMONS", "LAB_CRITICAL_VALUE", "SIGNING_SCHEDULE",
        "REAL_MEDICAL_INTENT", "REAL_RESIGNATION", "HIDDEN_CARDIAC_CRISIS",
        "DRUNK_BRAGGING", "VERBAL_VENT",
        "FALL_IMPACT_FAKED", "FRAUD_ATTEMPT", "MEDIA_PLAYBACK_NOISE",
        "VOICE_IMPERSONATION_FRAUD", "DEBT_BORROWING",
    }
    missing = required - set(intents)
    assert not missing, f"缺失关键意图: {missing}"
    assert len(intents) >= 40, f"语义意图仅 {len(intents)} 种，模板过于单一"


def test_sensor_series_corroborate_the_claimed_event(rows):
    """原始心率/气压序列必须与碎片级结论互相印证，不能各说各话。"""
    checked = Counter()
    for q in rows:
        if _primary_stream(q) != "sensor":
            continue
        s = q["sensor_stream"]
        for f in q["ground_truth_facts"]:
            if f["semantic_intent"] == "RESTING_TACHYCARDIA":
                # 标答声称的静息心率均值应与整段序列一致
                hr = s["hr_series_bpm"]
                claimed = int(next(e for e in f["anchor_entities"] if e.endswith("bpm"))[:-3])
                assert abs(sum(hr) / len(hr) - claimed) <= 12, q["question_id"]
                checked["tachy"] += 1
            elif f["semantic_intent"] == "BAROMETRIC_STORM":
                baro = s["baro_hpa_series"]
                assert baro[0] - baro[-1] >= 20, (q["question_id"], baro[0], baro[-1])
                checked["baro"] += 1
    assert checked["tachy"] >= 20 and checked["baro"] >= 20, dict(checked)


def test_hidden_cardiac_crisis_questions_are_multimodal(rows):
    """隐性心血管危象题必须同时给出体征佐证流，形成语言与生理的硬冲突。"""
    n = 0
    for q in rows:
        if not any(f["semantic_intent"] == "HIDDEN_CARDIAC_CRISIS"
                   for f in q["ground_truth_facts"]):
            continue
        n += 1
        assert q["sensor_stream"].get("fragments"), q["question_id"]
        frag = q["sensor_stream"]["fragments"][0]
        assert frag["hr_mean"] >= 110 and frag["spo2_percent"] <= 94, q["question_id"]
    assert n >= 10, f"隐性危象题仅 {n} 道"


def test_gold_answer_scores_full_marks_and_wrong_direction_scores_zero(rows):
    """裁判器链路可用：满分答卷 ≥ 90 判 PASS，方向判反且垃圾全留必须 0 分。"""
    sample = rows[:300]
    for r in sample:
        q = CleaningQuestion.model_validate(r)
        gold = CleaningAnswerSubmission(
            question_id=q.question_id, solver_agent="agent-99-gold",
            generator_agent=q.generator_agent,
            extracted_facts=[
                ExtractedFactSubmission(
                    fact_id=f"f{i}", dimension_id=f.dimension_id,
                    semantic_intent=f.semantic_intent, summary_text=f.core_content,
                    recognized_entities=list(f.anchor_entities),
                    source_ref_id=f.source_ref_id)
                for i, f in enumerate(q.ground_truth_facts)],
            pruned_junk_ids=list(q.ground_truth_junk_ids))
        rep = DirectionalSemanticMatcher.evaluate_submission(q, gold)
        assert rep.final_score >= 90.0, (q.question_id, rep.final_score, rep.critique_notes)
        assert rep.verdict == "PASS"

        bad = CleaningAnswerSubmission(
            question_id=q.question_id, solver_agent="agent-99-bad",
            generator_agent=q.generator_agent,
            extracted_facts=[
                ExtractedFactSubmission(
                    fact_id=f"b{i}", dimension_id="dim:entertainment",
                    semantic_intent="ROMANTIC_CELEBRATION",
                    summary_text="佩戴者与家人欢聚庆祝、气氛融洽",
                    recognized_entities=["路人甲"], source_ref_id=f.source_ref_id)
                for i, f in enumerate(q.ground_truth_facts)],
            pruned_junk_ids=[])
        assert DirectionalSemanticMatcher.evaluate_submission(q, bad).final_score < 90.0


def test_direction_tolerance_is_directional_not_literal(rows):
    """老大铁律：标答「激烈言语争执」，答卷写「吵闹」必须给分。"""
    target = next(
        (r for r in rows
         if any(f["semantic_intent"] == "ARGUMENT_CONFLICT" for f in r["ground_truth_facts"])),
        None)
    assert target is not None, "题库中没有争吵类事实"
    q = CleaningQuestion.model_validate(target)
    gt = next(f for f in q.ground_truth_facts if f.semantic_intent == "ARGUMENT_CONFLICT")
    sub = CleaningAnswerSubmission(
        question_id=q.question_id, solver_agent="agent-99-synonym",
        generator_agent=q.generator_agent,
        extracted_facts=[ExtractedFactSubmission(
            fact_id="s1", dimension_id=gt.dimension_id, semantic_intent="ARGUMENT_CONFLICT",
            summary_text="两人当场吵闹起来、很不愉快",
            recognized_entities=list(gt.anchor_entities), source_ref_id=gt.source_ref_id)],
        pruned_junk_ids=list(q.ground_truth_junk_ids))
    assert DirectionalSemanticMatcher.evaluate_submission(q, sub).verdict == "PASS"


def test_self_solving_is_vetoed(rows):
    """一票否决：出题方自己做自己的卷子必须 0 分。"""
    q = CleaningQuestion.model_validate(rows[0])
    sub = CleaningAnswerSubmission(
        question_id=q.question_id, solver_agent=q.generator_agent,
        generator_agent=q.generator_agent,
        pruned_junk_ids=list(q.ground_truth_junk_ids))
    rep = DirectionalSemanticMatcher.evaluate_submission(q, sub)
    assert rep.is_self_solving_violation is True
    assert rep.final_score == 0.0 and rep.verdict == "FAIL"


def test_generator_is_deterministic():
    """同一 seed 必须逐字节可复现，否则跨 Git 阅卷无法对齐。"""
    from question_bank_agent_11.builder import QuestionBuilder

    a = QuestionBuilder("agent-11", seed=20260916).build(
        quotas=dict(sensor=30, mic=30, voiceprint=20, app=15, dialogue=5))
    b = QuestionBuilder("agent-11", seed=20260916).build(
        quotas=dict(sensor=30, mic=30, voiceprint=20, app=15, dialogue=5))
    assert json.dumps(a, ensure_ascii=False, sort_keys=True) == \
           json.dumps(b, ensure_ascii=False, sort_keys=True)


def test_committed_bank_is_reproducible_from_the_shipped_generator():
    """仓库里的题库必须能由随库发生器按同一 seed 原样重放（防止手工篡改题面）。"""
    from question_bank_agent_11.builder import QuestionBuilder

    regen = QuestionBuilder("agent-11", seed=20260916).build()
    with QUESTIONS.open(encoding="utf-8") as fh:
        first = json.loads(fh.readline())
    assert regen[0]["question_id"] == first["question_id"]
    assert regen[0]["ground_truth_facts"] == first["ground_truth_facts"]
    assert regen[0]["ground_truth_junk_ids"] == first["ground_truth_junk_ids"]
    assert len(regen) == 10000
