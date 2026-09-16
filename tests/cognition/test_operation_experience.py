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
