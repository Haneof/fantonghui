"""AIOS 3.0 全天生活流出卷生成器（01a0aa2c-fantonghui）真值自检。

出卷本身就是被测对象：如果标答锚点不可观测、同义词簇与红线判据含混、
时间轴越界或生成不确定，下游解题方的一切成绩都无从谈起。这里钉住
生成器的七条硬性质：

1. 素材库完整性：原型→五维状态引用合法、事件池结构统一；
2. 试卷四键结构：question_id / persona / cleaned_daily_stream / directional_ground_truth；
3. 可观测性铁律：每个锚点实体必须出现在当日生活流文本中；
4. 方向性判卷结构：六维齐全、同义词∩红线=∅、证据事件真实存在；
5. 时间轴铁律：事件全部落在 07:00~23:30 且单调不减；
6. 确定性：同种子逐字节可复现、question_id 全局唯一；
7. 陷阱纯净性：语义陷阱（玩笑/吹牛/惊悚标题/他人生活）不得混入任何标答方向。
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

GENERATOR_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "daily_summary" / "generators"
sys.path.insert(0, str(GENERATOR_DIR))

import daily_life_generator_01a0aa2c as G  # noqa: E402
import daily_life_pools_01a0aa2c as P  # noqa: E402

REQUIRED_KEYS = {"question_id", "persona", "cleaned_daily_stream", "directional_ground_truth"}
DIM_IDS = ["dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"]


@pytest.fixture(scope="module")
def sample_questions():
    return [G.build_question(i) for i in range(1, 151)]


# ---------------------------------------------------------------- 素材库


def test_pools_archetype_state_refs_valid():
    for key, arch in P.ARCHETYPES.items():
        assert arch["social"] in P.SOCIAL_STATES, (key, "social")
        assert arch["emotion"] in P.EMOTION_STATES, (key, "emotion")
        assert arch["health"] in P.HEALTH_STATES, (key, "health")
        assert arch["career"] in P.CAREER_STATES, (key, "career")
        assert arch["weight"] > 0 and arch["spine"] and arch["spine_syns"] and arch["spine_reds"]


def test_pools_event_pool_arity_uniform():
    for e in P.TRIVIAL_EVENTS + P.TRAP_EVENTS:
        assert len(e) == 5, e
        assert e[1] in ("mic", "app", "sensor"), e


def test_pools_finance_events_schema():
    for key, fdef in P.FINANCE_EVENTS.items():
        assert fdef["gt_core"] and fdef["syns"] and fdef["reds"]
        assert not (set(fdef["syns"]) & set(fdef["reds"])), key
        if fdef["event"] is not None:
            assert len(fdef["event"]) == 4, key


def test_pools_every_state_has_directional_triplet():
    for pool_name, pool in (
        ("social", P.SOCIAL_STATES), ("emotion", P.EMOTION_STATES),
        ("health", P.HEALTH_STATES), ("career", P.CAREER_STATES),
    ):
        for key, st in pool.items():
            assert st["core"] and st["syns"] and st["reds"], (pool_name, key)
            assert not (set(st["syns"]) & set(st["reds"])), (pool_name, key)


# ---------------------------------------------------------------- 结构


def test_question_schema_four_keys(sample_questions):
    for q in sample_questions:
        assert REQUIRED_KEYS.issubset(q)
        p = q["persona"]
        assert {"persona_id", "age", "occupation", "city", "relationship", "personality"} <= set(p)
        assert q["question_id"] == f"QDAY_01a0aa2c-fantonghui_{int(q['question_id'][-5:]):05d}"


def test_event_schema(sample_questions):
    for q in sample_questions:
        for e in q["cleaned_daily_stream"]["events"]:
            assert {"id", "t", "src", "text"} <= set(e)
            if e["src"] == "mic":
                assert "from" in e and "scene" in e
            elif e["src"] == "app":
                assert "app" in e and "from" in e
            else:
                assert e["src"] == "sensor"


def test_stream_has_mic_app_sensor_mix(sample_questions):
    for q in sample_questions:
        srcs = {e["src"] for e in q["cleaned_daily_stream"]["events"]}
        assert {"mic", "app", "sensor"} <= srcs


# ---------------------------------------------------------------- 可观测性 + 方向性


def test_verify_question_passes(sample_questions):
    for q in sample_questions:
        assert G.verify_question(q) == [], q["question_id"]


def test_gt_six_dimensions_ordered(sample_questions):
    for q in sample_questions:
        gt = q["directional_ground_truth"]
        assert [d["dimension_id"] for d in gt["dimensions"]] == DIM_IDS
        g = gt["global_daily_summary"]
        assert g["dimension_id"] == "global"
        for b in [g] + gt["dimensions"]:
            assert b["core_anchor"] and b["accepted_synonyms"] and b["redline_criteria"]
            assert not (set(b["accepted_synonyms"]) & set(b["redline_criteria"]))
            ids = {e["id"] for e in q["cleaned_daily_stream"]["events"]}
            assert set(b["evidence_event_ids"]) <= ids


def test_global_summary_backed_by_multiple_sources(sample_questions):
    """铁律③：每题必须含跨维度冲突或转折——全局证据≥3 且覆盖≥2 个事件来源。"""
    for q in sample_questions:
        g = q["directional_ground_truth"]["global_daily_summary"]
        assert len(g["evidence_event_ids"]) >= 3
        srcs = {
            next(e["src"] for e in q["cleaned_daily_stream"]["events"] if e["id"] == ev_id)
            for ev_id in g["evidence_event_ids"]
        }
        assert len(srcs) >= 2


# ---------------------------------------------------------------- 时间轴


def test_events_within_window_and_monotonic(sample_questions):
    for q in sample_questions:
        ts = [e["t"] for e in q["cleaned_daily_stream"]["events"]]
        assert ts == sorted(ts), q["question_id"]
        assert all("07:00" <= t <= "23:30" for t in ts), q["question_id"]
        assert len(ts) >= 15


def test_quiet_weekend_falls_on_weekend(sample_questions):
    for q in sample_questions:
        g = q["directional_ground_truth"]["global_daily_summary"]
        if g["plot_family"].startswith("平静基线（小确幸"):
            d = date.fromisoformat(q["date"])
            assert d.weekday() >= 5, q["question_id"]


def test_sensor_summary_present(sample_questions):
    for q in sample_questions:
        ss = q["cleaned_daily_stream"]["sensor_summary"]
        assert 40 <= ss["morning_rest_hr"] <= 100
        assert 1000 <= ss["total_steps"] <= 30000
        assert 3.0 <= ss["sleep_hours"] <= 9.0
        assert len(ss["sleep_window"].split("-")) == 2


# ---------------------------------------------------------------- 确定性 + 唯一性


def test_determinism_byte_identical():
    a = json.dumps(G.build_question(4242), ensure_ascii=False, sort_keys=True)
    b = json.dumps(G.build_question(4242), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_question_ids_unique(sample_questions):
    ids = [q["question_id"] for q in sample_questions]
    assert len(ids) == len(set(ids))


def test_difficulty_labels_valid(sample_questions):
    for q in sample_questions:
        assert q["difficulty"] in {"EASY", "MEDIUM", "HARD", "ADVERSARIAL"}


# ---------------------------------------------------------------- 陷阱纯净性


TRAP_MARKERS = ("收购腾讯", "砍一刀", "明星官宣离婚", "辞职去大理", "环游世界ing",
                "搬工位", "90后体检异常率")


def test_trap_semantics_never_in_gt(sample_questions):
    for q in sample_questions:
        gt = q["directional_ground_truth"]
        for b in [gt["global_daily_summary"]] + gt["dimensions"]:
            for marker in TRAP_MARKERS:
                assert marker not in b["core_anchor"], (q["question_id"], marker)


def test_traps_present_and_speaker_is_other(sample_questions):
    """陷阱说话者必须是他人（同事/老同学/三姨/系统），不得被写成佩戴者本人。"""
    n_traps_total = 0
    for q in sample_questions:
        for e in q["cleaned_daily_stream"]["events"]:
            if any(m in e["text"] for m in TRAP_MARKERS):
                n_traps_total += 1
                if e["src"] == "mic":
                    assert e["from"] not in ("本人", "我"), q["question_id"]
    assert n_traps_total > 0, "抽样内应存在语义陷阱事件"


# ---------------------------------------------------------------- 财务解耦


def test_finance_dim_decoupled_from_archetype():
    """同原型在不同题目中应滚出不同财务事件（防原型→财务指纹捷径）。"""
    fin_by_arch = {}
    for q in (G.build_question(i) for i in range(1, 601)):
        arch = q["directional_ground_truth"]["global_daily_summary"]["plot_family"]
        fin = next(d for d in q["directional_ground_truth"]["dimensions"]
                   if d["dimension_id"] == "dim:finance")["core_anchor"]
        fin_by_arch.setdefault(arch, set()).add(fin[:6])
    multi = sum(1 for v in fin_by_arch.values() if len(v) >= 2)
    assert multi >= len(fin_by_arch) * 0.6, fin_by_arch


def test_generate_small_batch_end_to_end(tmp_path):
    out = tmp_path / "q.jsonl"
    stats = G.generate(25, out, verify=True)
    assert stats["total_questions"] == 25
    assert stats["observability_check"] == "passed"
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 25
    for line in lines:
        assert REQUIRED_KEYS.issubset(json.loads(line))
    manifest = tmp_path / "manifest_q.json"
    assert manifest.exists() and json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
