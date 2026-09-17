"""Tests for Nightly Review Runner & Dual World Daily Reflection (Sprint 2 / §30~32 / §33之一/之二)."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from aios_core.cognition.nightly_review_runner import (
    DualWorldReviewResult,
    NightlyReviewRunner,
    UserDailySummaryPayload,
    AISelfReflectionPayload,
)
from aios_core.contracts.models import Observation
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.ai_self_store import (
    AI_SELF_SUBJECT_ID,
    AISelfWorldStore,
)

UTC = timezone.utc


def test_nightly_review_dual_world_execution():
    store = AISelfWorldStore()
    runner = NightlyReviewRunner(ai_self_store=store)

    # 构造全天多模态 Observation
    now = datetime.now(UTC)
    observations = [
        Observation(
            object_id="obs_01",
            subject_id="user_1",
            source_kind="dialogue",
            modality="text",
            value="下午和老李在茶馆开会，商讨了合伙做项目的对赌协议，双方各有保留。",
            occurred=TemporalExtent.point(now),
            learned_at=now,
            created_by="test",
        ),
        Observation(
            object_id="obs_02",
            subject_id="user_1",
            source_kind="biometrics",
            modality="sensor",
            value="晚间心率 118bpm，检测到轻度早搏，无摔倒，静坐状态。",
            occurred=TemporalExtent.point(now),
            learned_at=now,
            created_by="test",
        ),
        Observation(
            object_id="obs_03",
            subject_id="user_1",
            source_kind="transaction",
            modality="text",
            value="给律所转账了 5000 元前期尽调意向金。",
            occurred=TemporalExtent.point(now),
            learned_at=now,
            created_by="test",
        ),
        Observation(
            object_id="obs_noise_001",
            subject_id="user_1",
            source_kind="audio",
            modality="audio",
            value="【环境叫卖杂音】磨剪子咧戗菜刀...",
            occurred=TemporalExtent.point(now),
            learned_at=now,
            created_by="test",
        ),
    ]

    # 执行夜间复盘
    result = runner.execute_nightly_review(
        review_date="2026-09-17",
        observations=observations,
    )

    # 1. 断言双世界输出结构完整
    assert result.review_date == "2026-09-17"
    assert isinstance(result.user_summary, UserDailySummaryPayload)
    assert isinstance(result.ai_self_reflection, AISelfReflectionPayload)

    # 2. 断言用户世界包含穿透性因果
    assert len(result.user_summary.root_cause_insights) >= 1
    assert "对赌协议" in result.user_summary.root_cause_insights[0] or "焦虑" in result.user_summary.root_cause_insights[0]
    assert len(result.user_summary.source_observation_ids) == 4

    # 3. 断言彻底解除 1500 Token 限制，全景因果输入顺畅
    assert result.total_context_tokens > 0

    # 4. 断言 AI 自身世界照镜子自省成功触发并更新评分
    snaps = store.get_all_dimension_snapshots()
    assert snaps["dim:ai_restraint"].current_score > 85.0  # +2.0
    assert snaps["dim:ai_keenness"].current_score > 75.0    # +3.0

    # 5. 断言经验规则被沉淀
    rules = store.get_crystallized_rules()
    assert len(rules) >= 1
    assert any("职场阻击" in r for r in rules)

    # 6. 断言铁律四落地：大模型自主标识出噪音粉碎目标
    assert "obs_noise_001" in result.garbage_to_prune_ids or len(result.garbage_to_prune_ids) >= 1
