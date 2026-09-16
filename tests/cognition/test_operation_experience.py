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


# =====================================================================
# M5-001 三大检索路径对比执行器实测（A 暴力全扫 / B 朴素关键词 / C 拓扑分级下钻）
# =====================================================================

from aios_core.cognition.operation_experience import (
    PathwayComparisonExecutor,
    PathwayProbe,
)
from aios_core.contracts.models import Entity, Observation, TemporalExtent
from aios_core.contracts.ids import new_operation_id
from aios_core.contracts.enums import SourceClass
from datetime import timedelta as _timedelta
from aios_core.contracts.operations import OperationRequest
from aios_core.operations.world_operator import WorldOperatorSuite

_FILLER_TEXTS = (
    "清晨例行通勤路况平稳记录",
    "午间简餐营养搭配常规记录",
    "傍晚户外散步天气情况记录",
    "日常家居物品采购清单记录",
    "晚间例行阅读放松时光记录",
)


def _build_pathway_world(tmp_path):
    """构造 3 年跨度高熵世界：约 230 条生活噪声 + 3 条金标因果事实。"""
    store = SQLiteWorldStore(str(tmp_path / "pathway_world.db"))
    suite = WorldOperatorSuite(store)

    def _obs(oid, value, source_kind, ts):
        return Observation(
            object_id=oid,
            subject_id="user_1",
            revision=1,
            source_kind=source_kind,
            modality="text",
            value=value,
            occurred=TemporalExtent.point(ts),
            learned_at=ts,
            recorded_at=ts,
            created_by="pathway-test",
        )

    t0 = datetime(2023, 3, 1, 8, 0, tzinfo=UTC)
    ent_me = Entity(
        object_id="ent_me",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="我",
        aliases=["自己"],
        occurred=TemporalExtent.point(t0),
        learned_at=t0,
        recorded_at=t0,
        created_by="pathway-test",
    )

    # 金标因果链（早搏 <- 连续通宵 <- 高咖啡因摄入）
    golden_cardiac = _obs(
        "obs_golden_cardiac_pvc",
        "深夜心电监测捕捉到室性早搏，每分钟 12 次，心率飙升",
        "biometrics",
        datetime(2026, 9, 10, 2, 30, tzinfo=UTC),
    )
    golden_allnighter = _obs(
        "obs_golden_allnighter",
        "周四连续通宵赶项目，彻夜未眠直接干到第二天中午",
        "sleep",
        datetime(2026, 9, 9, 23, 50, tzinfo=UTC),
    )
    golden_caffeine = _obs(
        "obs_golden_caffeine",
        "单日第三杯 88 元大杯浓缩咖啡因，摄入量明显超标",
        "transaction",
        datetime(2026, 9, 9, 15, 20, tzinfo=UTC),
    )

    def _filler_batch(start_idx, count):
        batch = []
        for i in range(start_idx, start_idx + count):
            ts = t0 + _timedelta(days=i * 4, hours=9)
            batch.append(
                _obs(f"obs_filler_{i:04d}", f"{_FILLER_TEXTS[i % len(_FILLER_TEXTS)]}第{i}期", "work_log", ts)
            )
        return batch

    op1 = OperationRequest(
        operation_id=new_operation_id(),
        operation_name="init.world",
        expected_world_revision=0,
        reason="pathway world batch 1",
        idempotency_key="pathway_b1",
        source_class=SourceClass.AI_COGNITION,
    )
    store.commit([ent_me, golden_cardiac] + _filler_batch(0, 115), op1)

    op2 = OperationRequest(
        operation_id=new_operation_id(),
        operation_name="update.world",
        expected_world_revision=store.current_world_revision(),
        reason="pathway world batch 2",
        idempotency_key="pathway_b2",
        source_class=SourceClass.AI_COGNITION,
    )
    store.commit(_filler_batch(115, 115) + [golden_allnighter, golden_caffeine], op2)

    golden_ids = ["obs_golden_cardiac_pvc", "obs_golden_allnighter", "obs_golden_caffeine"]
    return store, suite, golden_ids


_PATHWAY_INTENT = "回溯连续通宵与早搏之间的因果链"
_TOPO_PROBES = (
    PathwayProbe(keywords=("早搏",), dimension="dim_health"),
    PathwayProbe(keywords=("通宵",), dimension="dim_health"),
    PathwayProbe(keywords=("咖啡因",), dimension="dim_finance"),
)


def test_pathway_comparison_proves_topo_drill_down_dominance(tmp_path):
    store, suite, golden_ids = _build_pathway_world(tmp_path)
    executor = PathwayComparisonExecutor(store, suite, context_window_tokens=16000)

    report = executor.compare(
        _PATHWAY_INTENT,
        golden_ids,
        naive_keywords=["早搏"],
        topo_probes=_TOPO_PROBES,
    )

    # Pathway A：暴力全扫，15,000~50,000 Token 量级，且窗口外事实必然迷失
    assert 15000 <= report.receipt_brute_force.token_cost <= 50000
    assert report.receipt_brute_force.recall_accuracy < 1.0

    # Pathway B：朴素关键词省 Token，但无关键词的隐性因果（通宵/咖啡因）必漏
    assert report.receipt_keyword.token_cost < report.receipt_brute_force.token_cost
    assert report.receipt_keyword.recall_accuracy < 1.0

    # Pathway C：拓扑分级下钻，100% 召回且总 Token <= 500
    assert report.receipt_topo.recall_accuracy == 1.0
    assert report.receipt_topo.token_cost <= 500
    assert report.receipt_topo.latency_ms < 50.0

    # 压缩比与胜者判定
    assert report.compression_ratio >= 30.0
    assert report.winner_pathway == PathwayType.HIERARCHICAL_TOPO


def test_golden_experience_distilled_from_repeated_pathway_runs(tmp_path):
    store, suite, golden_ids = _build_pathway_world(tmp_path)
    executor = PathwayComparisonExecutor(store, suite, context_window_tokens=16000)
    distiller = OperationExperienceDistiller(store)

    strategy = None
    for _ in range(3):
        _report, strategy = executor.compare_and_distill(
            distiller,
            _PATHWAY_INTENT,
            golden_ids,
            naive_keywords=["早搏"],
            topo_probes=_TOPO_PROBES,
        )

    # 反复实测后，黄金经验必须锁定拓扑分级下钻：极简 Token、100% 准确
    assert strategy.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert strategy.expected_tokens <= 500
    assert strategy.expected_accuracy == 1.0
    assert strategy.sample_size == 9

    # 持久化重载：换一个蒸馏器实例也能取回同一条黄金经验
    reloaded = OperationExperienceDistiller(store).get_strategy(_PATHWAY_INTENT)
    assert reloaded.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert reloaded.expected_tokens <= 500
    assert reloaded.expected_accuracy == 1.0


def test_single_hit_token_envelope_within_150(tmp_path):
    """铁律：单次命中切片 Token 必须 <= 150。"""
    store, suite, _golden = _build_pathway_world(tmp_path)
    results = suite.search.query(keywords=["早搏"], dimension="dim_health", limit=10)
    assert results, "应当命中早搏心电事实"
    for r in results:
        assert 0 < r["estimated_tokens"] <= 150
