"""M5-001 增补验收（Agent-06）：三大检索路径对比执行器 + 黄金优选经验蒸馏。

在真实装配的世界（SQLiteWorldStore + WorldSearchIndex + CognitionAnnotation）上
同题三跑：
- A 暴力全扫：召回 100% 但 Token 巨耗（≥30× 于 C）；
- B 朴素关键词：漏掉"无关键词的隐性因果事实"与"今天挂载的外挂注记"；
- C 拓扑分级下钻：实体跳 + 注记联合召回 100%、单命中 Token ≤ 150、
  意图总封套 ≤ 500，蒸馏出的黄金策略必须锁定 C。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cognition.pathway_comparator import (
    MAX_HIT_TOKENS,
    MAX_INTENT_TOKENS,
    PathwayComparatorExecutor,
)
from aios_core.cognition.operation_experience import (
    OperationExperienceDistiller,
    PathwayType,
)
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import Claim, Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.contracts.time import TemporalExtent
from aios_core.operations.world_operator import CognitionOperator
from aios_core.query.search import WorldSearchIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc
TWO_YEARS_AGO = datetime(2024, 9, 15, 21, 30, tzinfo=UTC)
TODAY = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
LAOWANG_ENTITY = "ent_laowang_001"


def _obs(oid: str, *, text: str, at: datetime, refs: list[ObjectRef] | None = None) -> Observation:
    return Observation(
        object_id=oid,
        subject_id="user_boss",
        occurred=TemporalExtent.point(at),
        learned_at=at,
        recorded_at=at,
        created_by="m5-search-test",
        source_kind="chat_log",
        modality="text",
        value=text,
        source_refs=[SourceRef(object_id=r.object_id, revision=r.revision) for r in (refs or [])],
    )


@pytest.fixture()
def world(tmp_path):
    store = SQLiteWorldStore(str(tmp_path / "world.db"))
    objects: list = []
    # —— 老王实体（提供"老王"别名 → 索引 alias 展开让实体跳可判定）——
    from aios_core.contracts.models import Entity

    ent_at = TWO_YEARS_AGO - timedelta(days=30)  # 严格早于一切引用它的观测（知识可见性截断）
    objects.append(
        Entity(
            object_id=LAOWANG_ENTITY,
            subject_id="user_boss",
            occurred=TemporalExtent.point(ent_at),
            learned_at=ent_at,
            recorded_at=ent_at,
            created_by="m5-search-test",
            entity_kind="person",
            canonical_name="老王",
            aliases=["王总"],
        )
    )
    # —— 隐性因果事实：心率记录，文本里没有"老王/借款"关键词，但引用实体对象 ——
    objects.append(
        Observation(
            object_id="obs_hr_spike_that_night",
            subject_id="user_boss",
            occurred=TemporalExtent.point(TWO_YEARS_AGO + timedelta(minutes=42)),
            learned_at=TWO_YEARS_AGO,
            recorded_at=TWO_YEARS_AGO,
            created_by="m5-search-test",
            source_kind="wristband_sensor",
            modality="heart_rate",
            value="avg_bpm=118 签完字那晚心跳如鼓，是兴奋的",
            source_refs=[SourceRef(object_id=LAOWANG_ENTITY, revision=1)],
        )
    )
    # —— 关键词可见的原始事实 ——
    objects.append(
        _obs("obs_loan_chat_2024", text="老王：借款五十万帮我周转一下，下月连本带利还你。", at=TWO_YEARS_AGO, refs=[ObjectRef(object_id=LAOWANG_ENTITY, revision=1)])
    )
    objects.append(
        _obs("obs_partner_agreement_2024", text="与老王合伙开公司的协议已签，信任拉满。", at=TWO_YEARS_AGO - timedelta(days=9), refs=[ObjectRef(object_id=LAOWANG_ENTITY, revision=1)])
    )
    for i in range(120):  # 噪声海：无关日常观测
        objects.append(
            _obs(f"obs_noise_{i:04d}", text=f"周三午饭吃了第{i}号食堂套餐，口味一般。", at=TODAY - timedelta(days=i % 40, hours=i % 9))
        )
    entity_only = OperationRequest(
        operation_id="m5-search-seed-entity",
        session_id="m5-search",
        operation_name="world.commit",
        arguments={},
        expected_world_revision=store.current_world_revision(),
        reason="seed laowang entity first for referential integrity",
        idempotency_key="m5-search-seed-entity",
    )
    store.commit([objects.pop(0)], entity_only)  # 引用完整性：实体先入账
    claim = Claim(
        object_id="clm_wang_fraud_today",
        subject_id="user_boss",
        occurred=TemporalExtent.point(TODAY),
        learned_at=TODAY,
        recorded_at=TODAY,
        created_by="user",
        claimant_id="user_boss",
        claim_type="fact",
        content="今天查明：老王是骗子，借款至今一分未还",
        asserted_at=TODAY,
        knowledge_state="observed",
        confidence=0.99,
    )
    objects.append(claim)
    request = OperationRequest(
        operation_id="m5-search-seed",
        session_id="m5-search",
        operation_name="world.commit",
        arguments={},
        expected_world_revision=store.current_world_revision(),
        reason="seed multidimensional world for pathway comparison",
        idempotency_key="m5-search-seed",
    )
    store.commit(objects, request)

    # —— 今天挂载的外挂解释注记（C05 语义图层，历史不可变）——
    operator = CognitionOperator(store)
    annotation = operator.record_realization_today(
        LAOWANG_ENTITY,
        ObjectType.ENTITY,
        reinterpretation_claim="后来查明：老王是骗子（对两年前一切'信任'行为的重解释）",
        is_invalidating=False,
        now=TODAY,
    )
    index = WorldSearchIndex(store.db_path, store=store)
    index.catch_up()
    return store, index, annotation


# ---------------------------------------------------------------------------


def test_three_pathways_compared_on_real_world(world):
    store, index, annotation = world
    executor = PathwayComparatorExecutor(store, index=index)
    truth = {"obs_loan_chat_2024", "obs_hr_spike_that_night", annotation.annotation_id}
    outcomes = executor.compare(
        query_intent="老王借款诈骗回溯",
        keywords=["老王", "借款"],
        ground_truth_ids=sorted(truth),
        entity_id=LAOWANG_ENTITY,
        time_range=(TWO_YEARS_AGO - timedelta(days=30), TODAY),
    )
    a = outcomes[PathwayType.BRUTE_FORCE_SCAN]
    b = outcomes[PathwayType.KEYWORD_SEARCH]
    c = outcomes[PathwayType.HIERARCHICAL_TOPO]

    # A：全见但巨贵
    assert a.recall == 1.0 and a.token_cost >= 30 * max(1, c.token_cost)
    # B：朴素关键词漏掉隐性因果 + 外挂注记
    assert b.recall < 1.0
    assert "obs_hr_spike_that_night" not in b.retrieved_ids
    # C：拓扑下钻 100% 召回今天挂载的外挂注记与隐性事实
    assert c.recall == 1.0, f"拓扑路径必须全量命中: {c.retrieved_ids}"
    assert annotation.annotation_id in c.retrieved_ids
    assert c.max_single_hit_tokens <= MAX_HIT_TOKENS
    assert c.token_cost <= MAX_INTENT_TOKENS


def test_golden_strategy_distilled_and_persisted(world):
    store, index, _anno = world
    executor = PathwayComparatorExecutor(store, index=index)
    truth = {"obs_loan_chat_2024", "obs_hr_spike_that_night"}
    # 多意图反复对比后蒸馏（工单：多次检索后提炼最优路径）
    for intent, kws, ent in [
        ("老王借款诈骗回溯", ["老王", "借款"], LAOWANG_ENTITY),
        ("老王合伙信任史", ["老王", "合伙"], LAOWANG_ENTITY),
        ("老王拖延还款链", ["老王", "周转"], LAOWANG_ENTITY),
    ]:
        executor.compare(
            query_intent=intent,
            keywords=kws,
            ground_truth_ids=list(truth),
            entity_id=ent,
            time_range=(TWO_YEARS_AGO - timedelta(days=30), TODAY),
        )
        strategy = executor.distill_golden_strategy(intent)
        assert strategy.preferred_pathway is PathwayType.HIERARCHICAL_TOPO
        assert strategy.expected_accuracy >= 0.999
        assert strategy.expected_tokens <= MAX_INTENT_TOKENS

    # 持久化：换一个 distiller 实例（模拟进程重启）仍能读到黄金经验
    reloaded = OperationExperienceDistiller(store)
    stored = reloaded.get_strategy("老王借款诈骗回溯")
    assert stored.preferred_pathway is PathwayType.HIERARCHICAL_TOPO
    assert stored.expected_accuracy >= 0.999


def test_single_hit_token_cap_enforced(world):
    store, index, _anno = world
    executor = PathwayComparatorExecutor(store, index=index)
    outcomes = executor.compare(
        query_intent="老王线全景",
        keywords=["老王"],
        ground_truth_ids=["obs_loan_chat_2024", "obs_partner_agreement_2024"],
        entity_id=LAOWANG_ENTITY,
    )
    c = outcomes[PathwayType.HIERARCHICAL_TOPO]
    assert all(len(hit) <= 200 for hit in c.retrieved_ids)  # 指针即命中，无载荷灌入
    assert c.max_single_hit_tokens <= MAX_HIT_TOKENS
    # B 路径即使多命中，也必须被逐条渲染复核后仍受 150 闸约束
    b = outcomes[PathwayType.KEYWORD_SEARCH]
    assert b.max_single_hit_tokens <= MAX_HIT_TOKENS


def test_backward_compatible_with_co_search(world):
    store, index, _anno = world
    page = index.co_search(keywords=["老王", "借款"], subject="user_boss", limit=20)
    assert page.status == "ok"
    assert any(hit.object_id == "obs_loan_chat_2024" for hit in page.hits)
