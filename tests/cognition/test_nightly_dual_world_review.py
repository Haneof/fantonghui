"""Nightly dual-world review regression under R5/R6."""

from __future__ import annotations

from datetime import datetime, timezone

from aios_core.cognition.nightly_review_runner import (
    AISelfReflectionPayload,
    DualWorldReviewResult,
    NightlyReviewRunner,
    UserDailySummaryPayload,
)
from aios_core.contracts.models import Observation
from aios_core.contracts.time import TemporalExtent
from aios_core.runtime.ai_self_world import AISelfMemoryKind, AISelfWorldStoreV2

UTC = timezone.utc


def test_nightly_review_is_evidence_linked_and_cleanup_is_only_a_proposal(tmp_path):
    store = AISelfWorldStoreV2(tmp_path / "world.db")
    runner = NightlyReviewRunner(ai_self_store=store)

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

    result = runner.execute_nightly_review(
        review_date="2026-09-17",
        observations=observations,
    )

    assert isinstance(result, DualWorldReviewResult)
    assert isinstance(result.user_summary, UserDailySummaryPayload)
    assert isinstance(result.ai_self_reflection, AISelfReflectionPayload)
    assert len(result.user_summary.source_observation_ids) == 4
    assert len(result.user_summary.root_cause_insights) >= 1
    assert result.total_context_tokens > 0

    # AI-self reflection is a durable, evidence-linked forward record; no score delta.
    reflection = store.latest("reflection:nightly:2026-09-17")
    assert reflection is not None
    assert reflection.kind is AISelfMemoryKind.REFLECTION
    assert reflection.record_id == result.ai_self_record_id
    assert set(reflection.evidence_refs) == {"obs_01", "obs_02", "obs_03", "obs_noise_001"}
    assert "dimension_score_adjustments" not in reflection.structured_data
    assert "crystallized_insights" in reflection.structured_data

    # Model can nominate low-value records, but this runner does not tombstone/delete.
    assert "obs_noise_001" in result.cleanup_candidate_ids
    assert store.latest("reflection:nightly:2026-09-17") == reflection


def test_prompt_assembly_does_not_keyword_bucket_world_facts(tmp_path):
    store = AISelfWorldStoreV2(tmp_path / "world.db")
    runner = NightlyReviewRunner(ai_self_store=store)
    now = datetime.now(UTC)
    observations = [
        Observation(
            object_id="obs_ambiguous",
            subject_id="user_1",
            source_kind="dialogue",
            modality="text",
            value="妈妈说项目的钱先别转，我有点烦。",
            occurred=TemporalExtent.point(now),
            learned_at=now,
            created_by="test",
        )
    ]

    prompt, _, refs = runner._assemble_adaptive_review_prompt(
        "2026-09-17",
        observations,
    )
    assert refs == ["obs_ambiguous"]
    assert "[chronological evidence]" in prompt
    assert "ref=obs_ambiguous" in prompt
    # Runtime supplies evidence; it does not decide one fixed cognitive dimension.
    assert "[健康生理流]" not in prompt
    assert "[人际社交流]" not in prompt
    assert "[财务与契约流]" not in prompt
