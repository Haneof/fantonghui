"""Tool B 共现召回加速器测试：真实 E2E 世界上的基线一致性对撞（禁止自编自答）。"""

import os
import tempfile

import pytest

from aios_core.query.search import WorldSearchIndex
from aios_core.simulation.adversarial_life_bench import (
    AdversarialLifeGenerator,
    DailyFactStream,
    EdgePurifier,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.tools.cooccurrence_recall_accelerator import (
    CooccurrenceRecallAccelerator,
    build_tool_proposal,
)
from aios_core.tools.proposal_pipeline import ToolProposalPipeline

CO_KEYWORDS = ["合伙", "借贷", "撕逼", "银行流水"]
UTC_NOW = "2026-09-15T12:00:00+00:00"


@pytest.fixture(scope="module")
def e2e_world():
    """灌入真实对抗生命世界（小 IMU 规模，对象量级与 2M 版一致 ~19.5k）。"""
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteWorldStore(db)
    gen = AdversarialLifeGenerator(imu_sample_count=20_000)
    raw = gen.generate_raw_streams()
    EdgePurifier(store, gen.key_events).purify_and_populate(raw, DailyFactStream().generate())
    idx = WorldSearchIndex(db, store=store)
    # 索引 catch-up 是惰性的（postings 随基线查询填充）→ 显式触发一次，
    # 保证加速器直接读投影时两侧处于同一 watermark
    idx.co_search(CO_KEYWORDS)
    acc = CooccurrenceRecallAccelerator(db)
    yield store, idx, acc, db
    os.remove(db)


def test_recall_pair_is_the_fight_event(e2e_world):
    _, idx, acc, _ = e2e_world
    assert acc.recall(["撕逼", "流水"]) == {"obs_e2e_partner_fight"}


def test_single_keyword_recall_matches_baseline(e2e_world):
    """单关键词：加速器 vs 基线 search_mind，object_id 集合必须一致。"""
    _, idx, acc, _ = e2e_world
    for kw in CO_KEYWORDS:
        baseline = {h.object_id for h in idx.search_mind(keywords=[kw], limit=5000).hits}
        acc_set = acc.recall([kw])
        assert acc_set == baseline, f"关键词 {kw} 召回漂移: {acc_set ^ baseline}"


def test_collision_pair_identical(e2e_world):
    """非退化对撞：成对共现两侧完全一致。"""
    _, idx, acc, _ = e2e_world
    v = acc.verify_against_baseline(["撕逼", "流水"], idx)
    assert v.identical is True
    assert v.missing_in_accelerator == ()
    assert v.missing_in_baseline == ()
    assert v.accelerator_count == 1
    assert v.detail["baseline_status"] == "ok"


def test_collision_4kw_consistent(e2e_world):
    """4 词全共现（AND 语义）：两侧一致（本世界无单对象同时含 4 词，应为空集一致）。"""
    _, idx, acc, _ = e2e_world
    v = acc.verify_against_baseline(CO_KEYWORDS, idx)
    assert v.identical is True
    assert v.baseline_count == v.accelerator_count


def test_zero_hit_keyword(e2e_world):
    _, idx, acc, _ = e2e_world
    assert acc.recall(["量子纠缠"]) == set()
    v = acc.verify_against_baseline(["量子纠缠"], idx)
    assert v.identical and v.baseline_count == 0


def test_top_ranking(e2e_world):
    _, _, acc, _ = e2e_world
    top = acc.top(["流水", "撕逼"], limit=10)
    assert top, "top 结果不应为空"
    top_ids = [row["object_id"] for row in top]
    assert "obs_e2e_partner_fight" in top_ids
    for row in top:
        assert row["co_score"] > 0
        assert row["revision"] >= 1


def test_invalid_keywords(e2e_world):
    _, _, acc, _ = e2e_world
    with pytest.raises(ValueError):
        acc.recall([])
    with pytest.raises(ValueError):
        acc.recall(["  "])


def test_keyword_postings_and_semantics(e2e_world):
    """4 字词 = 3 个二元组分词全含才进预过滤（AND 分词语义）。"""
    _, _, acc, _ = e2e_world
    postings = acc.keyword_postings(["银行流水"])
    assert postings["银行流水"], "'银行流水' 分词 posting 交集不应为空"
    assert "obs_e2e_partner_bank_flow" in postings["银行流水"]


def test_build_tool_proposal_lifecycle():
    build = build_tool_proposal(
        subject_id="user_e2e_1", t_now=_utc(UTC_NOW),
        measured={"baseline_ms": 9932.0, "accelerator_ms": 40.0, "speedup": 248.3, "identical": True},
    )
    pipeline = ToolProposalPipeline()
    pipeline.submit_proposal(build)
    assert build.status == "submitted"
    pipeline.review_proposal(build.object_id, "approve")
    pipeline.execute_proposal(build.object_id)
    assert build.status == "executed"
    assert "248.3x" in build.expected_benefit


def _utc(iso: str):
    from datetime import datetime, timezone

    return datetime.fromisoformat(iso).astimezone(timezone.utc)
