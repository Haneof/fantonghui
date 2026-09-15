"""Migration fixture for M0-024: inline Claim(type=PREDICTION) → Prediction object.

Deterministic, replayable: same input Claim payload → same Prediction object_id
(via content hash), so a re-run is an idempotent upsert, never a duplicate.
"""

from __future__ import annotations

import hashlib
import json

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ClaimType
from aios_core.contracts.models import Claim
from aios_core.contracts.models_v3 import Prediction, PredictionCheckWindow
from aios_core.contracts.refs import ObjectRef


def migrate_inline_prediction(
    claim: Claim,
    check_window: PredictionCheckWindow,
    evaluator_version: str,
) -> Prediction:
    """Project a legacy inline PREDICTION claim into a first-class Prediction."""
    if claim.claim_type is not ClaimType.PREDICTION:
        raise ValueError(
            "migration source must be a Claim with claim_type=PREDICTION"
        )
    canonical = json.dumps(
        {
            "object_id": claim.object_id,
            "revision": claim.revision,
            "window": check_window.model_dump(mode="json"),
            "evaluator": evaluator_version,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    migration_fp = hashlib.sha256(canonical).hexdigest()[:24]
    return Prediction(
        object_id=f"pred-mig-{migration_fp}",
        subject_id=claim.subject_id,
        revision=1,
        occurred=claim.occurred,
        learned_at=claim.learned_at,
        source_refs=claim.source_refs,
        created_by=f"migration:{evaluator_version}",
        claim_ref=ObjectRef(
            object_id=claim.object_id,
            revision=claim.revision,
        ),
        check_window=check_window,
        evaluator_version=evaluator_version,
    )


def migrate_all_inline_predictions(
    objects: list[WorldObject],
    check_window: PredictionCheckWindow,
    evaluator_version: str,
) -> list[Prediction]:
    seen: set[str] = set()
    out: list[Prediction] = []
    for obj in objects:
        if not isinstance(obj, Claim) or obj.claim_type is not ClaimType.PREDICTION:
            continue
        pred = migrate_inline_prediction(obj, check_window, evaluator_version)
        if pred.object_id in seen:
            continue
        seen.add(pred.object_id)
        out.append(pred)
    return out
