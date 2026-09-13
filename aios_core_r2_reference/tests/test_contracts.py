from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts import (
    Claim,
    ClaimType,
    EvidenceCoverage,
    EvidenceSet,
    KnowledgeState,
    KnowledgeWindow,
    ObjectRef,
    ObjectType,
    Observation,
    TemporalExtent,
    TimePrecision,
    new_object_id,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_temporal_extent_rejects_naive_datetime():
    with pytest.raises(ValueError):
        TemporalExtent.point(datetime(2026, 9, 14, 12, 0))


def test_observation_carries_three_time_semantics():
    obj = Observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        subject_id="user_1",
        occurred=TemporalExtent.point(NOW - timedelta(days=1), TimePrecision.MINUTE),
        learned_at=NOW,
        recorded_at=NOW + timedelta(seconds=2),
        created_by="ingest",
        source_kind="chat",
        modality="text",
        value="昨天我去了医院",
    )
    assert obj.occurred.start.date().isoformat() == "2026-09-13"
    assert obj.learned_at.date().isoformat() == "2026-09-14"
    assert obj.recorded_at > obj.learned_at


def test_claim_distinguishes_prediction_from_observed_utterance():
    claim = Claim(
        object_id=new_object_id(ObjectType.CLAIM),
        subject_id="user_1",
        learned_at=NOW,
        recorded_at=NOW,
        created_by="ai",
        claimant_id="user_1",
        claim_type=ClaimType.PREDICTION,
        content="用户预测明天会被某学校录取",
        asserted_at=NOW,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.62,
    )
    assert claim.claim_type is ClaimType.PREDICTION
    assert claim.knowledge_state is KnowledgeState.REPORTED


def test_evidence_set_requires_members_or_selector():
    with pytest.raises(ValueError):
        EvidenceSet(
            object_id=new_object_id(ObjectType.EVIDENCE_SET),
            subject_id="user_1",
            learned_at=NOW,
            recorded_at=NOW,
            created_by="ai",
            purpose="support event",
            knowledge_window=KnowledgeWindow(knowledge_cutoff=NOW, world_revision=0),
            selection_method="manual",
            coverage=EvidenceCoverage(),
        )


def test_evidence_set_can_hold_versioned_refs():
    evidence = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="user_1",
        learned_at=NOW,
        recorded_at=NOW,
        created_by="ai",
        purpose="support sports event",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=NOW, world_revision=3),
        member_refs=[ObjectRef(object_id="obs_abc", revision=1)],
        support_refs=[ObjectRef(object_id="obs_abc", revision=1)],
        selection_method="same-time-window",
        coverage=EvidenceCoverage(observed_count=1, coverage_ratio=1.0),
    )
    assert evidence.member_refs[0].revision == 1
