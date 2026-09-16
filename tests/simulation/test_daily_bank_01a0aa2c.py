"""样卷出卷包测试：编织/自审/盲卷拆分/方向阅卷。"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks" / "data_cleaning"))

from question_bank_daily_01a0aa2c.__main__ import audit
from question_bank_daily_01a0aa2c.builder import (
    PaperBuilder, eligible_arcs, split_ground_truth, strip_ground_truth)
from question_bank_daily_01a0aa2c.judge import score_bank, score_paper
from question_bank_daily_01a0aa2c.pools import ARCS, DIM_ORDER, PERSONAS


def _arc(aid):
    return next(a for a in ARCS if a["id"] == aid)


def _paper(persona_name="林晓", arc_id="REBUKE_BREAKUP", seed=7):
    rng = random.Random(seed)
    p = next(x for x in PERSONAS if x["name"] == persona_name)
    return PaperBuilder(rng).build(1, p, _arc(arc_id))


def test_build_single_paper_schema():
    q = _paper()
    assert set(q) >= {"question_id", "persona", "cleaned_daily_stream",
                      "directional_ground_truth"}
    assert 15 <= len(q["cleaned_daily_stream"]) <= 25
    assert list(q["directional_ground_truth"].keys()) == DIM_ORDER


def test_audit_small_bank_passes():
    from collections import Counter
    rng = random.Random(11)
    b = PaperBuilder(rng)
    use: Counter = Counter()
    papers = []
    for i in range(64):
        p = PERSONAS[i % len(PERSONAS)]
        cands = sorted(eligible_arcs(p), key=lambda a: (use[a["id"]], rng.random()))
        use[cands[0]["id"]] += 1
        papers.append(b.build(i + 1, p, cands[0]))
    stats = audit(papers, 64)
    assert stats["personas"] >= 12 and len(stats["arcs"]) >= 15


def test_split_and_strip():
    q = _paper()
    blind, gt = split_ground_truth(q)
    assert "directional_ground_truth" not in blind
    assert gt["question_id"] == q["question_id"]
    assert "directional_ground_truth" in gt
    assert "directional_ground_truth" not in strip_ground_truth(q)


def test_judge_synonym_full_credit_and_oracle_pass():
    q = _paper()
    gt = q["directional_ground_truth"]
    syn = {d: "，".join(a["accept"][0] for a in gt[d]["anchors"]) for d in DIM_ORDER}
    r = score_paper(gt, syn)
    assert r["total"] == 100.0 and r["pass"] and not r["vetoes"]


def test_judge_redline_veto():
    q = _paper()  # REBUKE_BREAKUP：social 红线含 甜蜜/恩爱/求婚/复合
    gt = q["directional_ground_truth"]
    ans = {d: gt[d]["core"] for d in DIM_ORDER}
    ans["dim:social"] = "两人甜蜜恩爱，求婚成功，感情升温。"
    r = score_paper(gt, ans)
    assert r["dims"]["dim:social"]["score"] == 0.0
    assert r["dims"]["dim:social"]["veto"] is True
    assert "dim:social" in r["vetoes"]


def test_judge_neutral_abstain_and_empty():
    q = _paper()  # finance 为 neutral
    gt = q["directional_ground_truth"]
    assert gt["dim:finance"]["neutral"] is True
    ans = {d: gt[d]["core"] for d in DIM_ORDER}
    ans["dim:finance"] = "今日无大额收支记录。"
    assert score_paper(gt, ans)["dims"]["dim:finance"]["score"] == 100.0
    ans["dim:finance"] = "今日被骗走巨额资金，欠债累累。"
    assert score_paper(gt, ans)["dims"]["dim:finance"]["score"] == 0.0
    r = score_paper(gt, {d: "" for d in DIM_ORDER})
    assert r["total"] < 60.0 and r["pass"] is False


def test_score_bank_aggregates():
    q = _paper()
    gt = q["directional_ground_truth"]
    oracle = {d: gt[d]["core"] for d in DIM_ORDER}
    agg = score_bank([gt, gt], [oracle, {d: "" for d in DIM_ORDER}])
    assert agg["n"] == 2 and 0.0 < agg["pass_rate"] < 1.0
