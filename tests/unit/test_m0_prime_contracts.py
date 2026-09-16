"""M0′ 契约增量（M0-023~028，随《AIOS宪法v3.0修改案_R4》批准转正）。

覆盖六组新契约的冻结语义；性能/运行面验收分别在 M1(G-M1P)/M2(V21b)/M3(R4-06)
按 R4 设计书 §3.4 落地，不属于本文件。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aios_core.contracts import (
    AnnotationSlot,
    AssemblyPolicy,
    BudgetOnExceed,
    BudgetPolicy,
    BudgetScope,
    CommunicationExperience,
    LifeChapter,
    MaintenanceClass,
    ObjectRef,
    Prediction,
    PredictionVerificationState,
    Reinterpretation,
    SourceClass,
    UserReaction,
    OperationRequest,
    TemporalExtent,
)
from aios_core.contracts.registry import canonical_model_for_object_type
from aios_core.contracts.enums import ObjectType

NOW = datetime(2026, 9, 16, 8, 0, 0, tzinfo=timezone.utc)
WINDOW = TemporalExtent.point(NOW)


def common(**overrides):
    base = {
        "object_id": "obj_1",
        "subject_id": "user_1",
        "learned_at": NOW,
        "recorded_at": NOW,
        "created_by": "m0-prime-tests",
    }
    base.update(overrides)
    return base


# ---------------- M0-023: SourceClass / 触发豁免的契约地基 ----------------


def test_maintenance_writes_must_declare_maintenance_class():
    with pytest.raises(ValidationError, match="maintenance_class"):
        OperationRequest(
            operation_name="summary.mark_stale",
            expected_world_revision=0,
            reason="propagate correction",
            idempotency_key="k1",
            source_class=SourceClass.MAINTENANCE,
        )


def test_non_maintenance_writes_cannot_smuggle_maintenance_class():
    with pytest.raises(ValidationError, match="only valid for MAINTENANCE"):
        OperationRequest(
            operation_name="claim.create",
            expected_world_revision=0,
            reason="user confession",
            idempotency_key="k2",
            source_class=SourceClass.AI_COGNITION,
            maintenance_class=MaintenanceClass.STALE_MARK,
        )


def test_default_source_class_keeps_existing_callers_compatible():
    request = OperationRequest(
        operation_name="observation.write",
        expected_world_revision=0,
        reason="ingest",
        idempotency_key="k3",
    )
    assert request.source_class is SourceClass.AI_COGNITION


# ---------------- M0-025: Prediction（50~53 条） ----------------


def test_prediction_requires_pinned_claim_and_reasoning():
    with pytest.raises(ValidationError, match="pinned"):
        Prediction(
            **common(object_type=ObjectType.PREDICTION),
            source_claim_ref=ObjectRef(object_id="claim_x"),  # 无 revision
            expected_change="今晚深睡低于30分钟",
            time_window=WINDOW,
            confidence=0.7,
            reasoning="连续3天熬夜+静息心率升5bpm，心衰早期假说",
        )
    with pytest.raises(ValidationError, match="reasoning"):
        Prediction(
            **common(object_type=ObjectType.PREDICTION),
            source_claim_ref=ObjectRef(object_id="claim_x", revision=1),
            expected_change="今晚深睡低于30分钟",
            time_window=WINDOW,
            confidence=0.7,
            reasoning="   ",
        )


def test_prediction_verdict_requires_outcome_evidence():
    with pytest.raises(ValidationError, match="actual_outcome_ref"):
        Prediction(
            **common(object_type=ObjectType.PREDICTION),
            source_claim_ref=ObjectRef(object_id="claim_x", revision=1),
            expected_change="今晚深睡低于30分钟",
            time_window=WINDOW,
            confidence=0.7,
            reasoning="熬夜假说验证",
            verification_state=PredictionVerificationState.FALSIFIED,
        )


# ---------------- M0-024: LifeChapter（29 条） ----------------


def test_sealed_life_chapter_requires_reason():
    fields = common(
        object_type=ObjectType.LIFE_CHAPTER,
        baseline_refs=[ObjectRef(object_id="dim_sleep", revision=3)],
        status="sealed",
    )
    with pytest.raises(ValidationError, match="sealed_reason"):
        LifeChapter(**fields)
    chapter = LifeChapter(**fields, sealed_reason="作息/社交/情绪基线结构性重组（第 29 条）")
    assert chapter.status == "sealed"


# ---------------- M0-027: Reinterpretation（R4-01） ----------------


def test_reinterpretation_pins_target_and_keeps_history_untouched():
    with pytest.raises(ValidationError, match="pinned"):
        Reinterpretation(
            **common(object_type=ObjectType.REINTERPRETATION),
            target_ref=ObjectRef(object_id="observation_afternoon"),
            slot=AnnotationSlot.EMOTION,
            statement="当天下午的平稳不是平静，是被当众训斥后的极度憋屈",
            confidence=0.9,
        )
    annotation = Reinterpretation(
        **common(object_type=ObjectType.REINTERPRETATION),
        target_ref=ObjectRef(object_id="observation_afternoon", revision=1),
        slot=AnnotationSlot.EMOTION,
        statement="当天下午的平稳不是平静，是被当众训斥后的极度憋屈",
        confidence=0.9,
        evidence_set_ref=ObjectRef(object_id="evidence_confession", revision=2),
    )
    # 第 93 条：标注诞生于 T_now——learned_at 即写入时刻；被指向对象不产生新 revision
    assert annotation.learned_at == NOW
    assert annotation.target_ref.revision == 1
    assert annotation.supersedes_id is None


# ---------------- M0-026: CommunicationExperience（12/69 条） ----------------


def test_communication_experience_records_reaction_and_counterexamples():
    experience = CommunicationExperience(
        **common(object_type=ObjectType.COMMUNICATION_EXPERIENCE),
        scenario="用户加班后倾诉受挫",
        style="损友式短句+一句行动建议",
        user_reaction=UserReaction.ACCEPTED,
        counterexample_refs=[ObjectRef(object_id="session_1902", revision=4)],
    )
    assert experience.user_reaction is UserReaction.ACCEPTED
    with pytest.raises(ValidationError):
        CommunicationExperience(
            **common(object_type=ObjectType.COMMUNICATION_EXPERIENCE),
            scenario="s",
            style="x",
            user_reaction=UserReaction.ACCEPTED,
            action_ref=ObjectRef(object_id="action_1"),  # 必须 pinned
        )


# ---------------- M0-028: BudgetPolicy / AssemblyPolicy（86 条之一） ----------------


def test_budget_policy_requires_at_least_one_cap():
    with pytest.raises(ValidationError, match="at least one cap"):
        BudgetPolicy(**common(object_type=ObjectType.BUDGET_POLICY), scope=BudgetScope.DAY)
    policy = BudgetPolicy(
        **common(object_type=ObjectType.BUDGET_POLICY),
        scope=BudgetScope.BACKGROUND_DAY,
        max_model_calls=40,
        on_exceed=BudgetOnExceed.DEFER_TO_IDLE,
    )
    assert policy.max_model_calls == 40


def test_assembly_policy_section_caps_must_match_order():
    with pytest.raises(ValidationError, match="outside section_order"):
        AssemblyPolicy(
            **common(object_type=ObjectType.ASSEMBLY_POLICY),
            section_order=["wake_pointer", "work_state", "recall", "recent_dialog"],
            section_token_caps={"ghost_layer": 800},
            max_prefill_tokens=4096,
            data_source_allowlist=["hot_cards", "world_search", "task_center"],
        )
    policy = AssemblyPolicy(
        **common(object_type=ObjectType.ASSEMBLY_POLICY),
        section_order=["wake_pointer", "work_state", "recall", "recent_dialog"],
        section_token_caps={"recall": 800},
        max_prefill_tokens=4096,
        data_source_allowlist=["hot_cards", "world_search", "task_center"],
    )
    assert policy.data_source_allowlist[0] == "hot_cards"


# ---------------- 注册表一致性 ----------------


@pytest.mark.parametrize(
    "object_type",
    [
        ObjectType.PREDICTION,
        ObjectType.LIFE_CHAPTER,
        ObjectType.REINTERPRETATION,
        ObjectType.COMMUNICATION_EXPERIENCE,
        ObjectType.BUDGET_POLICY,
        ObjectType.ASSEMBLY_POLICY,
    ],
)
def test_registry_resolves_new_object_types(object_type):
    model = canonical_model_for_object_type(object_type)
    assert model is not None
    assert model.model_fields["object_type"].default == object_type
