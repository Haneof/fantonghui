# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-001 操作经验蒸馏验收（用户贴文赛道定义）。

  A 暴力扫描：15k~50k token 真值裁判（机械、慢、永远对）
  B 朴素关键词：不含维度/实体/时间面 —— 画饼充饥，允许命中偏多
  C 拓扑分级下钻（search_mind）：≤500 token 逼近真值
  黄金路径：≥3 次观测且 100% 准确晋升；单次 ≤500 token 顶；sqlite 持久化。
  任何路径不进黄金池的条件：一次不达标即一票否决，再无翻身机会（record 门禁）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.enums import ClaimType, KnowledgeState
from aios_core.contracts.models import Claim
from aios_core.contracts.operations import OperationRequest
from aios_core.cognition_m5.operation_experience import (
    GOLDEN_MIN_OBSERVATIONS,
    GOLDEN_TOKEN_CEILING,
    OperationExperienceDistiller,
    PathwayComparator,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

T0 = datetime(2026, 9, 16, 8, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path) -> SQLiteWorldStore:
    return SQLiteWorldStore(tmp_path / "world.db")


def _commit(store, objs, key: str) -> None:
    store.commit(list(objs), OperationRequest(
        operation_id=f"exp-{key}", operation_name="world.commit",
        expected_world_revision=store.current_world_revision(),
        reason="seed", idempotency_key=f"exp-{key}"))


def _claim(oid: str, content: str, at: datetime) -> Claim:
    return Claim(
        object_id=oid, claimant_id="director", claim_type=ClaimType.FACT,
        content=content, asserted_at=at,
        knowledge_state=KnowledgeState.OBSERVED, confidence=0.9,
        **world_kwargs(subject_id="director", learned_at=at, recorded_at=at),
    )


def _seed_arena(store: SQLiteWorldStore, mass: int = 60) -> None:
    """血压赛道 4 件真值 + 60 件噪声杂项，噪声内容膨胀逼出 A 的大账单。"""
    truth = [
        ("exp-bp-1", "血压晨测 118/76 心率 62", T0 - timedelta(days=3)),
        ("exp-bp-2", "血压复查 122/79，连续两周稳定", T0 - timedelta(days=2)),
        ("exp-bp-3", "血压夜间记录 125/82，网友建议补钾", T0 - timedelta(days=1)),
        ("exp-bp-4", "血压午间 119/77，散步后回落", T0 - timedelta(hours=6)),
    ]
    for i, (oid, content, at) in enumerate(truth):
        _commit(store, [_claim(oid, content, at)], f"t{i}")
    filler = "杂项记录流水账：" + "生活琐事流水 " * 60  # 每件噪声内容数百字
    for i in range(mass):
        _commit(store, [_claim(f"exp-noise-{i}", f"{filler} 编号{i}",
                               T0 - timedelta(hours=12 + i))], f"n{i}")


# ---------------------------------------------------------------------------
# 三赛道对比
# ---------------------------------------------------------------------------


def test_pathway_a_is_ground_truth_and_costly(tmp_path):
    store = _store(tmp_path)
    _seed_arena(store)
    comparator = PathwayComparator(store)
    report = comparator.compare({"keywords": ["血压"]})
    assert report.path("A").hit_ids == {"exp-bp-1", "exp-bp-2", "exp-bp-3", "exp-bp-4"}
    assert report.path("A").tokens >= 15_000, "A 暴力全扫必须付出 15k 级真值账单"


def test_pathway_c_reproduces_truth_within_500_tokens(tmp_path):
    store = _store(tmp_path)
    _seed_arena(store)
    comparator = PathwayComparator(store)
    report = comparator.compare({"keywords": ["血压"]})
    c = report.path("C")
    assert c.tokens <= 500
    assert c.accuracy_vs_truth == 1.0


def test_token_delta_proves_the_writeup(tmp_path):
    store = _store(tmp_path)
    _seed_arena(store)
    report = PathwayComparator(store).compare({"keywords": ["血压"]})
    a, c = report.path("A"), report.path("C")
    assert a.tokens / max(1, c.tokens) >= 30, "15k~50k → ≤500 的落差是这次蒸馏的存在意义"


# ---------------------------------------------------------------------------
# 黄金路径蒸馏
# ---------------------------------------------------------------------------


QUERY_SIMPLE = {"keywords": ["血压"]}


def test_golden_requires_three_perfect_observations(tmp_path):
    store = _store(tmp_path)
    _seed_arena(store)
    distiller = OperationExperienceDistiller(store)
    assert distiller.golden_for(QUERY_SIMPLE) is None
    for i in range(GOLDEN_MIN_OBSERVATIONS - 1):
        distiller.record(QUERY_SIMPLE)
        assert distiller.golden_for(QUERY_SIMPLE) is None, f"第 {i+1} 次观测不得提前晋升"
    distiller.record(QUERY_SIMPLE)
    golden = distiller.golden_for(QUERY_SIMPLE)
    assert golden is not None, "三连全对才准晋升"
    assert golden.observations == GOLDEN_MIN_OBSERVATIONS
    assert golden.accuracy == 1.0
    assert golden.truth_ids == ("exp-bp-1", "exp-bp-2", "exp-bp-3", "exp-bp-4")
    assert all(t <= GOLDEN_TOKEN_CEILING for t in golden.pathway_tokens.values())


def test_one_miss_locks_golden_forever(tmp_path):
    """一票否决：C 因封套裁切实实在在漏过真值一次，该签名终身不得晋升。"""
    store = _store(tmp_path)
    _seed_arena(store)
    # 30 件血压真值：C 的 150 token 封套装不下 → 必然漏真 → 准确率 <100%
    for i in range(30):
        _commit(store, [_claim(f"exp-bp-flood-{i}",
                               f"血压抽查批次{i}：118/76 心率 62",
                               T0 + timedelta(minutes=i + 10))], f"bf{i}")
    crowded = {"keywords": ["血压"]}
    distiller = OperationExperienceDistiller(store)
    report = distiller.record(crowded)
    assert report.path("C").accuracy_vs_truth < 1.0, "封套裁切必须被真值法官点名"
    for _ in range(GOLDEN_MIN_OBSERVATIONS + 2):
        distiller.record(crowded)
    assert distiller.golden_for(crowded) is None, "历史污点不抹：一次失手，永不晋升"

    # 对照面：换一个洁净签名（时间窗切出小真值集），C 三连全对照常晋升
    windowed = {"keywords": ["血压"],
                "time_range": (T0 - timedelta(days=4), T0 - timedelta(hours=25))}
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    clean_store = _store(clean_dir)
    _seed_arena(clean_store)
    distiller2 = OperationExperienceDistiller(clean_store)
    for _ in range(GOLDEN_MIN_OBSERVATIONS):
        distiller2.record(windowed)
    golden = distiller2.golden_for(windowed)
    assert golden is not None and golden.truth_ids == ("exp-bp-1", "exp-bp-2")


def test_golden_persists_across_process_restart(tmp_path):
    store = _store(tmp_path)
    _seed_arena(store)
    d1 = OperationExperienceDistiller(store)
    for _ in range(GOLDEN_MIN_OBSERVATIONS):
        d1.record(QUERY_SIMPLE)
    assert d1.golden_for(QUERY_SIMPLE) is not None

    d2 = OperationExperienceDistiller(store)  # 新实例 = 重开进程
    golden = d2.golden_for(QUERY_SIMPLE)
    assert golden is not None, "黄金必须落 sqlite，不靠内存寄存"
    assert golden.truth_ids == d1.golden_for(QUERY_SIMPLE).truth_ids


def test_golden_invalidated_by_new_evidence(tmp_path):
    store = _store(tmp_path)
    _seed_arena(store)
    d = OperationExperienceDistiller(store)
    for _ in range(GOLDEN_MIN_OBSERVATIONS):
        d.record(QUERY_SIMPLE)
    assert d.golden_for(QUERY_SIMPLE) is not None
    _commit(store, [_claim("exp-bp-7", "血压异常 145/95，立即复查", T0 + timedelta(hours=2))], "x")
    assert d.golden_for(QUERY_SIMPLE) is None, "黄金不是铁饭碗：真值集动，黄金废"


def test_arena_report_persisted_with_full_accounting(tmp_path):
    store = _store(tmp_path)
    _seed_arena(store)
    d = OperationExperienceDistiller(store)
    report = d.record({"keywords": ["血压"], "dimension": "DIM_BODY_VITALS"})
    rows = d.list_observations()
    assert rows and any(r["kind"] == "observation" for r in rows)
    assert report.notice, "对比报告必须给一句能写进经验库的人话"
