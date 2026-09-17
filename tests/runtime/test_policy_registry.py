"""R6 policy registry must preserve governance class, evidence and rollback history."""

from datetime import datetime, timezone

import pytest

from aios_core.runtime.policy_registry import (
    CognitivePolicyRegistry,
    CognitivePolicyVersion,
    PolicyAuthorizationError,
    PolicyClass,
    PolicyConflict,
)

UTC = timezone.utc


def _base_policy(**overrides):
    data = dict(
        policy_id="recall.expand_threshold",
        scope="global_default",
        policy_class=PolicyClass.COGNITIVE_POLICY,
        default_value=0.50,
        current_value=0.50,
        allowed_range_or_choices={"min": 0.10, "max": 0.90},
        mutable_by_ai=True,
        reason="initial evidence-backed default",
        evidence_refs=("review:recall-baseline",),
        changed_by="governance",
        changed_at=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
        version=1,
        previous_version=None,
        rollback_pointer=None,
        evaluation_window="30d",
    )
    data.update(overrides)
    return CognitivePolicyVersion(**data)


def test_ai_can_update_only_registered_mutable_cognitive_policy_with_evidence(tmp_path):
    registry = CognitivePolicyRegistry(tmp_path / "world.db")
    v1 = _base_policy()
    registry.append(v1)

    v2 = _base_policy(
        current_value=0.42,
        reason="old-topic recall missed relevant memories during evaluation window",
        evidence_refs=("outcome:recall-miss-17", "outcome:recall-miss-21"),
        changed_by="ai_runtime",
        changed_at=datetime(2026, 10, 18, 8, 0, tzinfo=UTC),
        version=2,
        previous_version=1,
    )
    registry.append(v2, actor_is_ai=True)

    assert registry.latest(v1.policy_id) == v2
    assert registry.history(v1.policy_id) == [v1, v2]


def test_ai_policy_change_without_evidence_is_denied(tmp_path):
    registry = CognitivePolicyRegistry(tmp_path / "world.db")
    registry.append(_base_policy())

    v2 = _base_policy(
        current_value=0.42,
        reason="model simply prefers another number",
        evidence_refs=(),
        changed_by="ai_runtime",
        version=2,
        previous_version=1,
    )
    with pytest.raises(PolicyAuthorizationError):
        registry.append(v2, actor_is_ai=True)


def test_hard_boundary_cannot_be_ai_mutable():
    with pytest.raises(ValueError):
        CognitivePolicyVersion(
            policy_id="history.raw_mutation",
            scope="global",
            policy_class=PolicyClass.HARD_BOUNDARY,
            default_value=False,
            current_value=False,
            mutable_by_ai=True,
            reason="history protection",
            changed_by="governance",
            version=1,
            evaluation_window="permanent",
        )


def test_ai_cannot_create_its_own_policy_authority(tmp_path):
    registry = CognitivePolicyRegistry(tmp_path / "world.db")
    with pytest.raises(PolicyAuthorizationError):
        registry.append(_base_policy(changed_by="ai_runtime"), actor_is_ai=True)


def test_ordinary_update_cannot_reclassify_policy(tmp_path):
    registry = CognitivePolicyRegistry(tmp_path / "world.db")
    registry.append(_base_policy())

    with pytest.raises(PolicyConflict):
        registry.append(
            _base_policy(
                policy_class=PolicyClass.ENGINEERING_PARAMETER,
                mutable_by_ai=False,
                version=2,
                previous_version=1,
                reason="illegal reclassification",
            )
        )


def test_rollback_appends_new_version_instead_of_rewriting_history(tmp_path):
    registry = CognitivePolicyRegistry(tmp_path / "world.db")
    v1 = _base_policy()
    registry.append(v1)
    v2 = _base_policy(
        current_value=0.42,
        reason="trial adjustment",
        evidence_refs=("outcome:trial",),
        changed_by="ai_runtime",
        version=2,
        previous_version=1,
    )
    registry.append(v2, actor_is_ai=True)

    v3 = registry.rollback(
        v1.policy_id,
        1,
        changed_by="ai_runtime",
        reason="evaluation window showed worse false recall",
        evidence_refs=("outcome:false-recall-regression",),
        actor_is_ai=True,
    )

    assert v3.version == 3
    assert v3.previous_version == 2
    assert v3.rollback_pointer == 1
    assert v3.current_value == v1.current_value
    assert registry.get(v1.policy_id, 2) == v2
