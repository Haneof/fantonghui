"""AI 操作经验蒸馏与 Cockpit 布局回归测试。

验证：
1. OperationExperienceDistiller 从真实回执中蒸馏检索路径并持久化；
2. Cockpit 保留 step1~step4 稳定布局和 token 工程预算，但不得把布局误解成固定思维顺序；
3. 关系与沟通姿态只作为候选/提示，不由测试固化为永久人格规则。
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

    # 1. 无历史实测回执时，提供一个可替换的工程先验，而不是认知真理。
    prior_strategy = distiller.distill_for_intent("老王诈骗案定罪回溯")
    assert prior_strategy.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert prior_strategy.expected_tokens <= 500
    assert prior_strategy.sample_size == 1

    # 2. 模拟多次真实检索回执录入。
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

    # 3. 蒸馏经验策略。
    learned = distiller.distill_for_intent("老王借款纠纷")
    assert learned.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert learned.expected_tokens == 360
    assert learned.expected_accuracy == 1.0
    assert learned.sample_size == 3
    assert len(learned.pathway_steps) >= 4

    # 4. 验证 SQLite 持久化与重新加载。
    new_distiller = OperationExperienceDistiller(temp_store)
    persisted = new_distiller.get_strategy("老王借款纠纷")
    assert persisted.preferred_pathway == PathwayType.HIERARCHICAL_TOPO
    assert persisted.expected_tokens == 360
    assert persisted.expected_accuracy == 1.0


def test_cockpit_manifest_compatible_layout_and_token_ceiling():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)

    manifest = CockpitManifestOptimizer.assemble_cockpit(
        wake_reason="老王还款期限已至且银行流水异动",
        user_name="老大",
        rapport_tier="待当前证据校准",
        rapport_notes="当前关系状态仅作为候选描述，需由历史交互和证据判断",
        self_identity="AIOS 3.0 的 AI 驾驶员；依据证据理解世界并遵守安全与权限边界",
        posture_tone="自然、直接；根据当前语境自主决定详略",
        active_focus_facts=[
            {"fact_id": "obs_wang_loan", "type": "loan", "amount": 500000},
            {"fact_id": "anno_wang_fraud", "type": "reinterpretation", "is_invalidating": True},
        ],
        ready_tasks=[
            {"task_id": "task_monitor_restitution", "title": "监测老王退赔资金流"},
        ],
        now=now,
    )

    # step1~step4 是兼容布局，不是 AI 必须按顺序执行的思维链。
    assert "【AI自身世界与原则】" in manifest.step1_self_mirror
    assert "【关系模型候选】" in manifest.step2_rapport_model
    assert "待当前证据校准" in manifest.step2_rapport_model
    assert "【沟通策略提示】" in manifest.step3_posture_and_tone
    assert manifest.step4_world_inspection["wake_reason"] == "老王还款期限已至且银行流水异动"
    assert len(manifest.step4_world_inspection["focused_fact_pointers"]) == 2
    assert len(manifest.step4_world_inspection["condition_ready_tasks"]) == 1

    # Token 上限是工程预算，不是认知正确性的硬边界；此样例仍应保持小型 cockpit。
    assert manifest.manifest_token_count <= 500
    assert manifest.manifest_token_count > 50
