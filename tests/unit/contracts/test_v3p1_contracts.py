"""Contract tests for the V3.0.1 extension world objects (M0' patch).

Every behavior asserted here anchors to a clause / ADJ ruling:
- ADJ-004: two-stage tombstone, DeletionLog testament, revocation classes.
- ADJ-005: retrospective annotation is backward-reaching only.
- ADJ-009: speaker clusters retire, never resurrect.
- R4 §3.4 I1/I2/I4: bounded AST, manifest budget discipline, zero-LLM epoch budget.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums_v3 import (
    BudgetLane,
    EpochState,
    ExtractionStatus,
    InteractionChannel,
    JobState,
    LifeChapterStatus,
    ObjectTypeV3,
    OutcomeDelivery,
    PredictionStatus,
    RetentionClass,
    SafetyVerdict,
    SpeakerClusterStatus,
    TombstoneStage,
    TriState,
    TrustLane,
)
from aios_core.contracts.models_v3 import (
    BudgetLedgerEntry,
    CommunicationExperience,
    ConversationTurn,
    DeletionLog,
    EpochBudget,
    EventMatched,
    ExtractionJob,
    InvalidationEpoch,
    LifeChapter,
    ManifestInstance,
    MechanicalPredicate,
    NotificationReceipt,
    Prediction,
    PredictionCheckWindow,
    RetentionTombstone,
    RetrospectiveAnnotation,
    SafetyGateVerdict,
    SemanticPredicate,
    SlotRef,
    SpeakerCluster,
    TimeReached,
    TriggerExpression,
    TriggerExpressionObject,
)
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from tests.unit.conftest import AWARE, AWARE_LATER, ref, world_kwargs


def _pred(**kw):
    base = dict(
        object_id="pred-1",
        claim_ref=ObjectRef(object_id="c1", revision=3),
        check_window=PredictionCheckWindow(opens_at=AWARE, closes_at=AWARE_LATER),
        evaluator_version="eval-v1",
    )
    base.update(kw)
    return Prediction(**base, **world_kwargs())


def test_prediction_terminal_requires_outcome_refs():
    with pytest.raises(ValidationError):
        _pred(prediction_status=PredictionStatus.FALSIFIED)
    ok = _pred(
        prediction_status=PredictionStatus.INCONCLUSIVE,
        outcome_refs=[ref("obs-1", 1)],
    )
    assert ok.prediction_status is PredictionStatus.INCONCLUSIVE


def test_prediction_window_must_be_ordered():
    with pytest.raises(ValidationError):
        PredictionCheckWindow(opens_at=AWARE_LATER, closes_at=AWARE)


def test_prediction_claim_ref_must_be_pinned():
    with pytest.raises(ValidationError):
        _pred(claim_ref=ObjectRef(object_id="c1"))


def test_chapter_confirm_requires_persistence_evidence():
    with pytest.raises(ValidationError):
        LifeChapter(
            object_id="lc-1",
            label="创业期",
            chapter_status=LifeChapterStatus.ACTIVE,
            change_point_dimension_refs=[ref("d1", 1), ref("d2", 1)],
            **world_kwargs(),
        )
    ok = LifeChapter(
        object_id="lc-1",
        label="创业期",
        chapter_status=LifeChapterStatus.ACTIVE,
        change_point_dimension_refs=[ref("d1", 1), ref("d2", 1)],
        persistence_evidence_refs=[ref("obs-99", 2)],
        **world_kwargs(),
    )
    assert ok.chapter_status is LifeChapterStatus.ACTIVE


def test_chapter_single_dimension_change_point_rejected():
    with pytest.raises(ValidationError):
        LifeChapter(
            object_id="lc-1",
            label="bad",
            change_point_dimension_refs=[ref("d1", 1)],
            **world_kwargs(),
        )


def test_comm_exp_without_sycophancy_assertion_is_unregistrable():
    with pytest.raises(ValidationError):
        CommunicationExperience(
            object_id="ce-1",
            pattern="夸用户爽",
            derived_from_refs=[ref("a1", 1)],
            avoids_sycophancy=False,
            **world_kwargs(),
        )


def test_retrospective_annotation_cannot_reach_future():
    from datetime import timedelta

    future_extent = TemporalExtent.point(AWARE_LATER + timedelta(days=365))
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(
            object_id="ra-1",
            anchor_ref=ref("obs-1", 1),
            valid_time=future_extent,
            payload={"mood": "angry"},
            evidence_refs=[ref("c1", 1)],
            **world_kwargs(),
        )


def test_retrospective_annotation_physically_append_only_shape():
    ok = RetrospectiveAnnotation(
        object_id="ra-1",
        anchor_ref=ref("obs-1", 1),
        valid_time=TemporalExtent.point(AWARE),
        payload={"mood": "恼火"},
        evidence_refs=[ref("c1", 1)],
        **world_kwargs(),
    )
    assert ok.anchor_ref.revision == 1


def _atom_temporal() -> TriggerExpression:
    return TriggerExpression(
        op="atom",
        leaf=TimeReached(at=AWARE_LATER),
    )


def test_trigger_ast_bounds():
    expr = TriggerExpression(op="all_of", children=[_atom_temporal(), _atom_temporal()])
    assert expr.node_count() == 3
    assert expr.depth() == 2

    # 深度超限（构造第 9 层 NOT 时即被模型校验拒绝）
    node = _atom_temporal()
    with pytest.raises(ValidationError):
        for _ in range(9):
            node = TriggerExpression(op="not", children=[node])


def test_trigger_semantic_never_mechanical_confusion():
    sem = TriggerExpression(
        op="atom", leaf=SemanticPredicate(kind="context_fit", prompt_signature="p:v1")
    )
    mech = TriggerExpression(
        op="atom", leaf=MechanicalPredicate(kind="obs_threshold", params={"x": 1})
    )
    assert sem.has_semantic() and not sem.has_mechanical()
    assert mech.has_mechanical() and not mech.has_semantic()


def test_trigger_not_requires_single_child():
    with pytest.raises(ValidationError):
        TriggerExpression(op="not", children=[_atom_temporal(), _atom_temporal()])


def test_trigger_object_freezes_subscription_keys():
    obj = TriggerExpressionObject(
        object_id="trg-1",
        ast=TriggerExpression(
            op="all_of",
            children=[
                _atom_temporal(),
                TriggerExpression(
                    op="atom", leaf=EventMatched(object_type="observation", match={"k": "心率"})
                ),
            ],
        ),
        subscription_keys=[{"key_kind": "time_due", "key_value": "2026-09-17T09:00:00Z"}],
        **world_kwargs(),
    )
    assert obj.object_type is ObjectTypeV3.TRIGGER_EXPRESSION


def test_turn_skipped_requires_reason():
    with pytest.raises(ValidationError):
        ConversationTurn(
            object_id="t-1",
            conv_id="cv",
            seq=1,
            speaker="user",
            utterance="x",
            finalized_at=AWARE,
            extraction_status=ExtractionStatus.SKIPPED,
            **world_kwargs(),
        )


def test_manifest_budget_hard_cap():
    with pytest.raises(ValidationError):
        ManifestInstance(
            object_id="m-1",
            lane="notify",
            token_budget=2000,
            token_used=2001,
            snapshot_world_revision=42,
            step0_safety=SafetyGateVerdict(
                verdict=SafetyVerdict.OK, hard_safe_ok=True, convenience="OK"
            ),
            **world_kwargs(),
        )


def test_manifest_partial_requires_omissions():
    with pytest.raises(ValidationError):
        ManifestInstance(
            object_id="m-1",
            lane="investigate",
            token_budget=12000,
            token_used=100,
            step0_safety=SafetyGateVerdict(
                verdict=SafetyVerdict.QUIET, hard_safe_ok=True, convenience="QUIET"
            ),
            partial=True,
            snapshot_world_revision=42,
            **world_kwargs(),
        )


def test_manifest_sections_hold_slotrefs():
    m = ManifestInstance(
        object_id="m-1",
        lane="investigate",
        token_budget=12000,
        token_used=300,
        step0_safety=SafetyGateVerdict(
            verdict=SafetyVerdict.OK, hard_safe_ok=True, convenience="OK"
        ),
        ready_task_refs=[ref("task-1", 2)],
        snapshot_world_revision=42,
        **world_kwargs(),
    )
    assert m.manifest_version == 1


def test_spoken_channels_require_epoch_shape():
    receipt = NotificationReceipt(
        object_id="nr-1",
        notification_epoch_ref=ref("epoch-1", 1),
        channel=InteractionChannel.PRIVATE_AUDIO,
        delivery=OutcomeDelivery.DELIVERED,
        **world_kwargs(),
    )
    assert receipt.delivery is OutcomeDelivery.DELIVERED


def test_tombstone_stage2_requires_deletion_log():
    with pytest.raises(ValidationError):
        RetentionTombstone(
            object_id="tb-1",
            target_ref=ref("obs-1", 3),
            tombstone_stage=TombstoneStage.STAGE2_SHREDDED,
            source_key_hash="h" * 32,
            tombstoned_at=AWARE,
            **world_kwargs(),
        )


def test_deletion_log_under_legal_hold_is_unconstitutional():
    with pytest.raises(ValidationError):
        DeletionLog(
            object_id="dl-1",
            deleted_ref=ref("obs-1", 1),
            reason="ttl",
            authorized_by="retention-worker-01",
            mechanical_check_passed=True,
            legal_hold_at_time=True,
            **world_kwargs(),
        )


def test_ledger_used_never_exceeds_budget():
    with pytest.raises(ValidationError):
        BudgetLedgerEntry(
            object_id="b-1",
            lane=BudgetLane.NOTIFY,
            period_start=AWARE,
            budget=8000,
            used=8001,
            **world_kwargs(),
        )


def test_epoch_budget_zero_llm_marking_phase():
    with pytest.raises(ValidationError):
        EpochBudget(llm_calls=1)


def test_epoch_requires_pinned_root():
    with pytest.raises(ValidationError):
        InvalidationEpoch(
            object_id="ep-1",
            root_ref=ObjectRef(object_id="claim-1"),
            root_new_revision=5,
            **world_kwargs(),
        )


def test_speaker_cluster_time_ordering():
    with pytest.raises(ValidationError):
        SpeakerCluster(
            object_id="sc-1",
            first_heard_at=AWARE_LATER,
            last_heard_at=AWARE,
            **world_kwargs(),
        )


def test_conversation_turn_ai_finalization_not_before_learned():
    from datetime import timedelta

    past = AWARE - timedelta(days=5)
    with pytest.raises(ValidationError):
        ConversationTurn(
            object_id="t-2",
            conv_id="cv",
            seq=1,
            speaker="ai",
            utterance="回答",
            finalized_at=past,
            **world_kwargs(),
        )
