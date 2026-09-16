"""24h 日总结题库契约测试（01a0aa2c-fantonghui）。

覆盖：银行规模/schema/标答四字段/红线卫生/锚点可观测/陷阱覆盖/
文本熵/极性覆盖/确定性 + 裁判器（抄标答满分/红线否决/瞎猜低分/自做否决）。
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "daily_summary" / "generators"))
import daily24h_generator_01a0aa2c as G
import daily24h_matcher_01a0aa2c as M

BANK = ROOT / "benchmarks" / "daily_summary" / "questions" / "questions_daily24h_01a0aa2c.jsonl"
MANIFEST = ROOT / "benchmarks" / "daily_summary" / "questions" / "manifest_daily24h_01a0aa2c.json"
NARROW = ("热搜", "明星", "官宣", "转发", "分期", "免息", "抽奖", "领取",
          "砍一刀", "拼单", "大理", "辞职", "中奖")


def load_all() -> list:
    return [json.loads(l) for l in open(BANK, encoding="utf-8")]


def test_bank_count_and_manifest():
    qs = load_all()
    assert len(qs) == 10000
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert man["total_questions"] == 10000
    assert man["sha256"] == hashlib.sha256(BANK.read_bytes()).hexdigest()


def test_schema_keys_exact():
    for q in load_all():
        assert list(q.keys()) == ["question_id", "generator_agent", "persona", "arc_tags",
                                  "cleaned_daily_stream", "directional_ground_truth"]
        assert set(q["persona"].keys()) == {"name", "gender", "age", "occupation", "city"}
        assert set(q["arc_tags"].keys()) == {"career", "social", "finance", "polarity"}
        for e in q["cleaned_daily_stream"]["events"]:
            assert set(e.keys()) == {"time", "channel", "content"}
            assert e["channel"] in ("SENSOR", "MIC", "APP")


def test_qid_unique_format():
    qs = load_all()
    ids = [q["question_id"] for q in qs]
    assert len(set(ids)) == 10000
    assert all(i.startswith("QD_01a0aa2c-fantonghui_") for i in ids)


def test_time_and_tail():
    for q in load_all():
        evs = q["cleaned_daily_stream"]["events"]
        assert 16 <= len(evs) <= 26
        ts = [e["time"] for e in evs]
        assert ts == sorted(ts)
        assert evs[-1]["time"] == "23:30" and evs[-1]["channel"] == "SENSOR"


def test_gt_four_fields_nonempty():
    dims = {"global_daily_summary", "dim:health", "dim:social", "dim:emotion",
            "dim:finance", "dim:career"}
    for q in load_all():
        gt = q["directional_ground_truth"]
        assert set(gt.keys()) == dims
        for dim, g in gt.items():
            assert set(g.keys()) == {"core_content", "acceptable_directions",
                                     "forbidden_directions", "anchor_entities"}, dim
            assert g["core_content"] and g["acceptable_directions"]
            assert g["forbidden_directions"] and g["anchor_entities"], dim


def test_syn_red_disjoint():
    for q in load_all():
        for dim, g in q["directional_ground_truth"].items():
            for a in g["acceptable_directions"]:
                for f in g["forbidden_directions"]:
                    assert not (a == f or a in f or f in a), (q["question_id"], dim, a, f)


def test_anchors_observable_and_amount():
    for q in load_all():
        blob = (" ".join(e["content"] for e in q["cleaned_daily_stream"]["events"])).replace(" ", "")
        tags = q["arc_tags"]
        allowed = {q["persona"]["name"], q["persona"]["occupation"], "佩戴者",
                   tags["career"], tags["social"]}
        for dim, g in q["directional_ground_truth"].items():
            for a in g["anchor_entities"]:
                assert a in allowed or a.replace(" ", "") in blob, (q["question_id"], dim, a)


def test_generator_selfcheck_resample():
    rng = random.Random(2401)
    names = G.make_persona_names(rng, 1000)
    for i in [0, 1, 2, 99, 555, 1234, 4321, 7777, 9998, 9999]:
        q, trap_idx = G.build_question(i, 2401, names)
        assert G.self_check(q, trap_idx) == [], i


def test_trap_and_entropy_gates():
    qs = load_all()
    trap = sum(1 for q in qs if any(
        m in " ".join(e["content"] for e in q["cleaned_daily_stream"]["events"]) for m in NARROW))
    assert trap / len(qs) >= 0.50, trap
    c = Counter()
    for q in qs:
        for e in q["cleaned_daily_stream"]["events"]:
            c[e["content"]] += 1
    assert len(c) >= 80000, len(c)
    assert max(c.values()) <= 1000, max(c.values())


def test_polarity_and_arc_coverage():
    qs = load_all()
    pols = Counter(tuple(q["arc_tags"]["polarity"]) for q in qs)
    assert set(pols.keys()) == {(-1, -1), (-1, 1), (1, 1), (1, -1), (0, -1), (0, 1)}
    assert set(q["arc_tags"]["career"] for q in qs) == {f"C{i:02d}" for i in range(1, 13)}
    assert set(q["arc_tags"]["social"] for q in qs) == {f"S{i:02d}" for i in range(1, 13)}
    assert set(q["arc_tags"]["finance"] for q in qs) == {f"F{i:02d}" for i in range(1, 9)}


def test_determinism_head():
    rng = random.Random(2401)
    names = G.make_persona_names(rng, 1000)
    file_head = [json.loads(l) for l, _ in zip(open(BANK, encoding="utf-8"), range(5))]
    for i in range(5):
        q, _ = G.build_question(i, 2401, names)
        assert q == file_head[i], i


def _perfect_sub(q: dict) -> dict:
    gt = q["directional_ground_truth"]
    sub = {"question_id": q["question_id"], "solver_agent": "someone-else",
           "generator_agent": q["generator_agent"]}
    for dim, sk in M.SUBKEY.items():
        sub[sk] = gt[dim]["core_content"] + "；" + "；".join(gt[dim]["anchor_entities"])
    return sub


def test_grader_copy_gt_full_marks():
    qs = load_all()
    for q in qs[::997]:
        r = M.evaluate_paper(q, _perfect_sub(q))
        assert r["overall"] == 100.0 and r["verdict"] == "PASS", q["question_id"]


def test_grader_redline_veto():
    qs = load_all()
    for q in qs[::997]:
        sub = _perfect_sub(q)
        f = q["directional_ground_truth"]["dim:career"]["forbidden_directions"][0]
        sub["generated_career_summary"] += "；" + f
        r = M.evaluate_paper(q, sub)
        assert r["overall"] == 0.0 and r["verdict"] == "FAIL" and r["fatal_redline"]


def test_grader_empty_and_gibberish():
    qs = load_all()
    for q in qs[::997]:
        sub = {"question_id": q["question_id"], "solver_agent": "someone-else",
               "generator_agent": q["generator_agent"]}
        for sk in M.SUBKEY.values():
            sub[sk] = ""
        r = M.evaluate_paper(q, sub)
        assert r["overall"] == 0.0 and r["verdict"] == "FAIL"
        # 瞎猜：只复读陷阱/琐事（取开头3条非SENSOR事件），必须 FAIL
        filler = [e["content"] for e in q["cleaned_daily_stream"]["events"]
                  if e["channel"] != "SENSOR"][:3]
        for sk in M.SUBKEY.values():
            sub[sk] = "；".join(filler)
        r = M.evaluate_paper(q, sub)
        assert r["verdict"] == "FAIL", (q["question_id"], r["overall"])


def test_grader_self_solving_violation():
    q = load_all()[0]
    sub = _perfect_sub(q)
    sub["solver_agent"] = q["generator_agent"]
    r = M.evaluate_paper(q, sub)
    assert r["overall"] == 0.0 and r["verdict"] == "FAIL"
