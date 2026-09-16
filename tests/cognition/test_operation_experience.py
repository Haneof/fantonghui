"""AI 操作经验蒸馏与极简看盘看板测试 (Operation Experience & Manifest Tests).

贯彻最高宪法第二十章（§67~70）与第二十四章（§84~85）：
1. 验证 OperationExperienceDistiller 从实测回执中自主蒸馏黄金检索路径并持久化；
2. 验证 CockpitManifestOptimizer 严格执行心智启动四步序与 <= 500 Token 门禁。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
import pytest

from aios_core.cognition.operation_experience import (
    OperationExperienceDistiller,
    PathwayType,
    QueryExecutionReceipt,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from ai_worker.manifest_optimizer import CockpitManifestOptimizer

UTC = timezone.utc


@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteWorldStore(path)
    try:
        yield store
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def test_experience_distiller_prior_and_learning(temp_store: SQLiteWorldStore):
    distiller = OperationExperienceDistiller(temp_store)

    # 1. 无历史实测回执时，提供宪法拓扑分级下钻先验策略
    prior_strategy = distiller.distill_for_intent("老王诈骗案定罪回溯")
    assert prior_strategy.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert prior_strategy.expected_tokens <= 500
    assert prior_strategy.sample_size == 1

    # 2. 模拟多次真实检索回执录入
    # 路径 A: 暴力全扫 (昂贵且慢)
    distiller.record_receipt(
        QueryExecutionReceipt(
            query_intent="老王借款纠纷",
            pathway_type=PathwayType.BRUTE_FORCE_SCAN,
            token_cost=16500,
            latency_ms=620.0,
            recall_accuracy=0.92,
            facts_retrieved_count=250,
        )
    )
    # 路径 B: 关键词检索 (漏查隐性因果)
    distiller.record_receipt(
        QueryExecutionReceipt(
            query_intent="老王借款纠纷",
            pathway_type=PathwayType.KEYWORD_SEARCH,
            token_cost=3200,
            latency_ms=110.0,
            recall_accuracy=0.68,
            facts_retrieved_count=45,
        )
    )
    # 路径 C: 拓扑分级下钻 (极快、极省、100% 命中)
    distiller.record_receipt(
        QueryExecutionReceipt(
            query_intent="老王借款纠纷",
            pathway_type=PathwayType.HIERARCHICAL_TOPO,
            token_cost=360,
            latency_ms=22.5,
            recall_accuracy=1.0,
            facts_retrieved_count=3,
        )
    )

    # 3. 蒸馏黄金经验策略
    learned = distiller.distill_for_intent("老王借款纠纷")
    assert learned.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert learned.expected_tokens == 360
    assert learned.expected_accuracy == 1.0
    assert learned.sample_size == 3
    assert len(learned.pathway_steps) >= 4

    # 4. 验证 SQLite 持久化与重新加载
    new_distiller = OperationExperienceDistiller(temp_store)
    persisted = new_distiller.get_strategy("老王借款纠纷")
    assert persisted.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert persisted.expected_tokens == 360
    assert persisted.expected_accuracy == 1.0


def test_cockpit_manifest_four_steps_and_token_ceiling():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)

    manifest = CockpitManifestOptimizer.assemble_cockpit(
        wake_reason="老王还款期限已至且银行流水异动",
        user_name="老大",
        rapport_tier="生死死党/损友僚机",
        rapport_notes="深度信任，关键建议直言不讳",
        self_identity="AIOS 3.0 端侧心智实体，坚守宪法底线",
        posture_tone="严肃警惕、冷静果断",
        active_focus_facts=[
            {"fact_id": "obs_wang_loan", "type": "loan", "amount": 500000},
            {"fact_id": "anno_wang_fraud", "type": "reinterpretation", "is_invalidating": True},
        ],
        ready_tasks=[
            {"task_id": "task_monitor_restitution", "title": "监测老王退赔资金流"},
        ],
        now=now,
    )

    # 1. 验证心智启动四步序不可颠倒与完整性
    assert "【AI身份与底线】" in manifest.step1_self_mirror
    assert "【与老大羁绊模型】" in manifest.step2_rapport_model
    assert "【当前姿态与音调】" in manifest.step3_posture_and_tone
    assert manifest.step4_world_inspection["wake_reason"] == "老王还款期限已至且银行流水异动"
    assert len(manifest.step4_world_inspection["focused_fact_pointers"]) == 2
    assert len(manifest.step4_world_inspection["condition_ready_tasks"]) == 1

    # 2. 验证宪法 Token 封套门禁 (<= 500 tokens)
    assert manifest.manifest_token_count <= 500
    assert manifest.manifest_token_count > 50  # 有实质内容


# ===========================================================================
# M5-001 三大检索路径对比执行器测试（工单 #6 / Agent-06）
#
# 验收要点：
#   1. 路径 A（暴力全扫）在 15,000~50,000 Token 量级且大面积违反 150 Token 单命中门禁；
#   2. 路径 B（朴素关键词）便宜但**系统性漏召回**无关键词的隐性因果；
#   3. 路径 C（拓扑分级下钻）在 ≤500 Token 内对齐暴力真值 100% 召回，单命中 ≤150 Token，
#      因果骨架（锚点/主张/证据集）完整进 Prompt；
#   4. 多次检索后由 OperationExperienceDistiller 提炼并持久化"黄金路径"，跨进程重载仍生效。
# ===========================================================================

from aios_core.bench.life_world_kit import build_canonical_life_world, estimate_tokens
from aios_core.cognition.operation_experience import (
    BruteForceScanExecutor,
    GoldenPathwayNotVerifiedError,
    GoldenPathwayPlaybook,
    NaiveKeywordExecutor,
    PathwayComparisonReport,
    PathwayExecution,
    RetrievalIntent,
    SingleHitTokenBudgetError,
    SingleHitTokenGuard,
    TopologicalDrillDownExecutor,
    run_pathway_comparison,
)
from aios_core.query.search import MultidimensionalSearchEngine


@pytest.fixture(scope="module")
def search_world(tmp_path_factory):
    """装配 240 对象的高熵世界（含四大剧情线 + 噪声流），使路径 A 落在宪法标注的 15k~50k Token 量级。"""
    db_path = tmp_path_factory.mktemp("m5_search") / "world.db"
    store = SQLiteWorldStore(str(db_path))
    world = build_canonical_life_world(store, target_count=240, seed=20260916)
    index = MultidimensionalSearchEngine(store.db_path, store=store)
    index.rebuild()
    return world, index


def _wang_intent(world) -> RetrievalIntent:
    return RetrievalIntent(
        intent_key="老王借款纠纷能否追偿",
        question="老王借的钱还能不能要回来？",
        keywords=("老王", "借款", "还款"),
        seed_entity_ids=(world.entity("old_wang"),),
        evidence_horizon=3,
    )


def test_pathway_c_matches_bruteforce_truth_within_500_tokens(search_world):
    world, index = search_world
    oracle = world.closure([world.entity("old_wang")], max_depth=3)
    assert len(oracle) >= 9, "证据闭包必须至少覆盖老王剧情线的核心对象"

    report = run_pathway_comparison(world.store, _wang_intent(world), oracle_ids=oracle, index=index)
    brute = report.executions[PathwayType.BRUTE_FORCE_SCAN.value]
    topo = report.executions[PathwayType.HIERARCHICAL_TOPO.value]

    # 1. 暴力全扫：Token 量级与单命中门禁违规
    assert brute.token_cost >= 15_000, f"暴力全扫应达到 15k Token 量级，实测 {brute.token_cost}"
    assert brute.recall_accuracy == 1.0
    assert brute.single_hit_violations > 0, "暴力整包灌入必然违反 150 Token 单命中门禁"
    assert brute.max_hit_tokens > SingleHitTokenGuard.MAX_SINGLE_HIT_TOKENS

    # 2. 拓扑下钻：≤500 Token / 召回 100% / 单命中合规
    assert topo.token_cost <= 500, f"黄金路径 Prompt 载荷必须 ≤500 Token，实测 {topo.token_cost}"
    assert topo.recall_accuracy == 1.0, "拓扑下钻必须对齐暴力真值 100% 召回"
    assert topo.max_hit_tokens <= SingleHitTokenGuard.MAX_SINGLE_HIT_TOKENS
    assert topo.single_hit_violations == 0
    assert topo.causal_skeleton_complete, "事件锚点/主张/证据集构成的因果骨架必须完整进 Prompt"

    # 3. 压缩比与门禁结论
    assert report.token_compression_ratio >= 0.90, f"降幅应 ≥90%，实测 {report.token_compression_ratio:.2%}"
    assert topo.token_cost < brute.token_cost / 30
    assert report.accuracy_verified and report.token_budget_verified and report.single_hit_verified
    assert "老王借款纠纷能否追偿" in report.summary_line()

    # 4. 拓扑下钻不得被海量日常噪声流污染（噪声对象无引用边，不该出现在证据集合里）
    assert all(not oid.startswith(("obs_bio_stream_", "obs_chat_stream_", "obs_finance_stream_")) for oid in topo.fact_ids)


def test_naive_keyword_pathway_misses_implicit_causality(search_world):
    world, index = search_world
    oracle = world.closure([world.entity("old_wang")], max_depth=3)
    report = run_pathway_comparison(world.store, _wang_intent(world), oracle_ids=oracle, index=index)

    naive = report.executions[PathwayType.KEYWORD_SEARCH.value]
    topo = report.executions[PathwayType.HIERARCHICAL_TOPO.value]

    # 便宜，但看得见的关键词事实远少于隐性因果（证据集/锚点/关联实体）
    assert naive.token_cost < topo.token_cost, "朴素关键词路径的卖点就是便宜"
    assert naive.recall_accuracy < 1.0, "朴素关键词路径必然漏掉无关键词的隐性因果"
    assert naive.recall_accuracy < topo.recall_accuracy
    assert any("漏召回" in note for note in report.notes)

    # 被漏掉的正是"证据集/事件锚点"这类没有用户原话关键词的因果骨架
    missed = oracle - set(naive.fact_ids)
    assert missed, "必须存在漏召回事实"
    assert any(oid.startswith(("evset_", "anchor_")) for oid in missed), (
        f"漏召回集合应包含证据集或事件锚点，实测 {sorted(missed)}"
    )


def test_single_hit_token_guard_blocks_oversized_hit():
    guard = SingleHitTokenGuard
    compact = [("obs_ok", "obs_ok|observation|膝盖受凉，需要轻便热敷")]
    assert guard.enforce(compact) <= guard.MAX_SINGLE_HIT_TOKENS
    assert guard.violations(compact) == []

    oversized = [("obs_huge", "x" * 4000)]
    with pytest.raises(SingleHitTokenBudgetError):
        guard.enforce(oversized)
    assert guard.violations(oversized) == ["obs_huge"]


def test_golden_path_distilled_and_persisted_across_instances(search_world):
    world, index = search_world
    intent = _wang_intent(world)
    oracle = world.closure([world.entity("old_wang")], max_depth=3)
    report = run_pathway_comparison(world.store, intent, oracle_ids=oracle, index=index)

    distiller = OperationExperienceDistiller(world.store)
    strategy = distiller.learn_golden_path(report)
    assert strategy.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert strategy.expected_tokens <= 500
    assert strategy.expected_accuracy == 1.0
    assert strategy.sample_size >= 3  # A/B/C 三条路径全部入账为样本

    playbook = distiller.playbook_for(intent.intent_key)
    assert isinstance(playbook, GoldenPathwayPlaybook)
    assert playbook.required_accuracy == 1.0
    assert playbook.single_hit_token_ceiling == SingleHitTokenGuard.MAX_SINGLE_HIT_TOKENS
    assert playbook.expected_tokens <= 500
    assert playbook.compression_ratio >= 0.90
    assert len(playbook.ladder_steps) >= 4, "黄金路径手册必须留下可复现的四级阶梯"

    # 手册对合规实测放行、对越界实测拦截
    golden_execution = report.golden
    playbook.verify(golden_execution)
    over_budget = golden_execution.model_copy(update={"token_cost": 501})
    with pytest.raises(GoldenPathwayNotVerifiedError):
        playbook.verify(over_budget)

    # 换一个进程内新实例（重新打开 SQLite）也必须读得到沉淀经验
    reloaded = OperationExperienceDistiller(world.store)
    assert reloaded.get_strategy(intent.intent_key).preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert reloaded.playbook_for(intent.intent_key) is not None


def test_golden_path_learning_rejects_unverified_reports(search_world):
    world, index = search_world
    intent = _wang_intent(world)
    oracle = world.closure([world.entity("old_wang")], max_depth=3)
    report = run_pathway_comparison(world.store, intent, oracle_ids=oracle, index=index)
    distiller = OperationExperienceDistiller(world.store)

    # 伪造一份"召回不达标"的报告 → 严禁沉淀为经验
    broken = report.model_copy(update={"accuracy_verified": False})
    with pytest.raises(GoldenPathwayNotVerifiedError):
        distiller.learn_golden_path(broken)

    # 超限命中样本同样禁止入账
    leaky = report.golden.model_copy(update={"single_hit_violations": 2})
    with pytest.raises(SingleHitTokenBudgetError):
        distiller.record_pathway_execution(leaky)


def test_multi_intent_distillation_yields_per_intent_golden_paths(search_world):
    """多次检索后按意图分别沉淀黄金路径：每一条都必须是拓扑下钻且 ≤500 Token/100% 召回。"""
    world, index = search_world
    distiller = OperationExperienceDistiller(world.store)
    intents = [
        RetrievalIntent(
            intent_key="老王诈骗案定罪回溯",
            keywords=("老王", "诈骗"),
            seed_entity_ids=(world.entity("old_wang"),),
        ),
        RetrievalIntent(
            intent_key="妈妈生日礼物不闲置推演",
            keywords=("妈妈", "生日", "礼物"),
            seed_entity_ids=(world.entity("mom"),),
        ),
        RetrievalIntent(
            intent_key="通宵加班与室性早搏因果链",
            keywords=("加班", "早搏"),
            seed_entity_ids=(world.entity("user"),),
        ),
    ]
    for intent in intents:
        oracle = world.closure(list(intent.seed_entity_ids), max_depth=3)
        assert oracle, f"{intent.intent_key} 的真值闭包不得为空"
        report = run_pathway_comparison(world.store, intent, oracle_ids=oracle, index=index)
        topo = report.executions[PathwayType.HIERARCHICAL_TOPO.value]
        assert topo.recall_accuracy == 1.0, f"{intent.intent_key} 拓扑召回未达 100%"
        assert topo.token_cost <= 500
        strategy = distiller.learn_golden_path(report)
        assert strategy.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
        assert strategy.expected_accuracy == 1.0
        assert strategy.expected_tokens <= 500

    # 三条意图各自独立沉淀，互不覆盖
    for intent in intents:
        assert distiller.playbook_for(intent.intent_key) is not None
    assert len({distiller.playbook_for(i.intent_key).intent_key for i in intents}) == 3


def test_pathway_execution_receipt_records_measured_costs(search_world):
    world, index = search_world
    intent = _wang_intent(world)
    oracle = world.closure([world.entity("old_wang")], max_depth=3)

    topo = TopologicalDrillDownExecutor(world.store, index=index, oracle_ids=oracle)
    execution = topo.execute(intent)
    assert isinstance(execution, PathwayExecution)
    assert execution.pathway_type == PathwayType.HIERARCHICAL_TOPO
    assert execution.token_cost == estimate_tokens(execution.prompt_payload)
    assert execution.expanded_nodes > 0, "拓扑扩张必须真实解引用载荷（而不是凭空攒指针）"
    assert len(set(execution.fact_ids) & oracle) >= max(1, len(oracle) // 2)

    receipt = execution.to_receipt()
    assert receipt.query_intent == intent.intent_key
    assert receipt.pathway_type == PathwayType.HIERARCHICAL_TOPO
    assert receipt.token_cost == execution.token_cost
    assert receipt.facts_retrieved_count == len(execution.fact_ids)

    # 显式注入真值裁判前，召回口径不做虚高承诺（由调用方负责注入，避免自证）
    naive = NaiveKeywordExecutor(world.store, index=index)
    assert naive.execute(intent).recall_accuracy >= 0.0
    brute = BruteForceScanExecutor(world.store, oracle_ids=oracle)
    assert brute.execute(intent).recall_accuracy == 1.0
