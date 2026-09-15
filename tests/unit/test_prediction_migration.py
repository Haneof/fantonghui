"""M0-024 migration fixture tests: inline PREDICTION claims → Prediction objects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aios_core.contracts.enums import ClaimType, KnowledgeState, ObjectType
from aios_core.contracts.models import Claim
from aios_core.contracts.models_v3 import PredictionCheckWindow, PredictionStatus
from aios_core.contracts.time import TemporalExtent
from aios_core.contracts.ids import new_object_id
from aios_core.migrations.prediction_v1 import (
    migrate_all_inline_predictions,
    migrate_inline_prediction,
)

NOW = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
WINDOW = PredictionCheckWindow(
    opens_at=NOW, closes_at=NOW + timedelta(days=7)
)


def _inline_prediction(content: str = "明天我会考上") -> Claim:
    return Claim(
        object_id=new_object_id(ObjectType.CLAIM),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="test",
        claimant_id="user-1",
        claim_type=ClaimType.PREDICTION,
        content=content,
        asserted_at=NOW,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.7,
    )


def test_migration_produces_deterministic_idempotent_prediction():
    claim = _inline_prediction()
    p1 = migrate_inline_prediction(claim, WINDOW, "eval-v1")
    p2 = migrate_inline_prediction(claim, WINDOW, "eval-v1")
    assert p1.object_id == p2.object_id
    assert p1.object_id.startswith("pred-mig-")
    assert p1.prediction_status is PredictionStatus.PENDING
    assert p1.claim_ref.object_id == claim.object_id
    assert p1.claim_ref.revision == claim.revision


def test_migration_rejects_non_prediction_claim():
    claim = _inline_prediction()
    claim = claim.model_copy(update={"claim_type": ClaimType.FACT})
    import pytest

    with pytest.raises(ValueError):
        migrate_inline_prediction(claim, WINDOW, "eval-v1")


def test_bulk_migration_dedupes_reruns():
    objs = [_inline_prediction(), _inline_prediction()]
    first = migrate_all_inline_predictions(objs, WINDOW, "eval-v1")
    second = migrate_all_inline_predictions(objs, WINDOW, "eval-v1")
    assert {p.object_id for p in first} == {p.object_id for p in second}
    assert len(first) == len(second) == len({p.object_id for p in first})
