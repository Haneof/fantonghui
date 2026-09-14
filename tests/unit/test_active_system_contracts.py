"""M0-014 Task/Wake/Session/Action/Outcome basic contract tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import (
    ActionStatus,
    ObjectType,
    TaskState,
    TaskType,
    WakeSource,
    WakeState,
)
from aios_core.contracts.errors import ErrorCode, StoreError
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import Action, Outcome, Session, Task, Wake
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore


BASE = datetime(2026, 9, 14, 12, 30, tzinfo=timezone.utc)


def make_op(expected_world_revision: int) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_014_test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-014 test",
        idempotency_key=str(uuid.uuid4()),
    )


def common(object_type: ObjectType, *, learned_at: datetime = BASE) -> dict:
    return {
        "object_id": new_object_id(object_type),
        "subject_id": "user-1",
        "occurred": TemporalExtent.unknown_time(),
        "learned_at": learned_at,
        "recorded_at": learned_at,
        "created_by": "test",
    }


def make_task(**overrides) -> Task:
    data = {
        **common(ObjectType.TASK),
        "task_type": TaskType.FOLLOW_UP,
        "task_state": TaskState.DRAFT,
        "title": "复查学习效果",
    }
    data.update(overrides)
    return Task(**data)


def make_wake(**overrides) -> Wake:
    data = {
        **common(ObjectType.WAKE),
        "wake_source": WakeSource.TASK_DUE,
        "first_hit_at": BASE,
        "last_hit_at": BASE,
    }
    data.update(overrides)
    return Wake(**data)


def make_session(**overrides) -> Session:
    data = {
        **common(ObjectType.SESSION),
        "snapshot_world_revision": 0,
    }
    data.update(overrides)
    return Session(**data)


def make_action(**overrides) -> Action:
    data = {
        **common(ObjectType.ACTION),
        "execution_id": str(uuid.uuid4()),
        "action_type": "send_message",
        "payload": {"text": "提醒用户复习"},
        "expected_outcome": "用户收到提醒",
    }
    data.update(overrides)
    return Action(**data)


def make_outcome(action_ref: ObjectRef, **overrides) -> Outcome:
    data = {
        **common(ObjectType.OUTCOME),
        "action_ref": action_ref,
        "outcome_state": "unknown",
    }
    data.update(overrides)
    return Outcome(**data)


def test_a01_exact_literal_object_types_and_core_field_annotations():
    expected = {
        Task: ObjectType.TASK,
        Wake: ObjectType.WAKE,
        Session: ObjectType.SESSION,
        Action: ObjectType.ACTION,
        Outcome: ObjectType.OUTCOME,
    }
    for cls, object_type in expected.items():
        hints = get_type_hints(cls)
        assert get_origin(hints["object_type"]) is Literal
        assert get_args(hints["object_type"]) == (object_type,)

    task_hints = get_type_hints(Task)
    assert task_hints["task_type"] is TaskType
    assert task_hints["task_state"] is TaskState
    assert set(get_args(task_hints["goal_ref"])) == {ObjectRef, type(None)}
    assert get_args(task_hints["reason_refs"]) == (ObjectRef,)
    assert get_args(task_hints["dependency_refs"]) == (ObjectRef,)
    assert get_args(task_hints["execution_refs"]) == (ObjectRef,)
    assert get_args(task_hints["outcome_refs"]) == (ObjectRef,)


def test_a02_task_type_exact_ten_categories():
    assert {item.value for item in TaskType} == {
        "immediate",
        "scheduled",
        "deadline",
        "todo",
        "recurring",
        "follow_up",
        "observation",
        "verification",
        "maintenance",
        "app",
    }


def test_a03_task_runtime_fields_are_durable_not_model_context():
    task = make_task(
        priority=87,
        next_wake_at=BASE + timedelta(hours=2),
        deadline=BASE + timedelta(days=1),
        timezone_name="Asia/Shanghai",
        next_step="等待复测结果",
        completion_condition={"requires": "quiz_result"},
        cancel_condition={"if": "goal_abandoned"},
        attempts=2,
    )
    dumped = task.model_dump(mode="python")
    for field_name in [
        "task_type",
        "task_state",
        "priority",
        "next_wake_at",
        "deadline",
        "timezone_name",
        "next_step",
        "completion_condition",
        "cancel_condition",
        "attempts",
    ]:
        assert field_name in dumped


def test_a04_task_time_fields_require_aware_datetime_and_valid_timezone():
    naive = datetime(2026, 9, 15, 9, 0)
    with pytest.raises(ValidationError):
        make_task(next_wake_at=naive)
    with pytest.raises(ValidationError):
        make_task(deadline=naive)
    with pytest.raises(ValidationError):
        make_task(timezone_name="Mars/Olympus_Mons")


def test_a05_task_reason_execution_outcome_refs_are_pinned_but_navigation_refs_may_float():
    pinned = ObjectRef(object_id="obj-a", revision=1)
    for field_name in ["reason_refs", "execution_refs", "outcome_refs"]:
        with pytest.raises(ValidationError):
            make_task(**{field_name: [ObjectRef(object_id="obj-a", revision=None)]})
        assert getattr(make_task(**{field_name: [pinned]}), field_name)[0].revision == 1

    task = make_task(
        goal_ref=ObjectRef(object_id="goal-a", revision=None),
        dependency_refs=[ObjectRef(object_id="dep-a", revision=None)],
        related_entity_refs=[ObjectRef(object_id="entity-a", revision=None)],
    )
    assert task.goal_ref.revision is None
    assert task.dependency_refs[0].revision is None
    assert task.related_entity_refs[0].revision is None


def test_a06_wake_is_separate_durable_object_and_keeps_hit_evidence():
    wake = make_wake(
        wake_source=WakeSource.USER_INTERACTION,
        wake_state=WakeState.NEW,
        hit_count=3,
        evidence_refs=[ObjectRef(object_id="obs-a", revision=1)],
        priority=90,
        dedupe_key="user-interaction-1",
    )
    assert wake.object_type is ObjectType.WAKE
    assert wake.hit_count == 3
    assert wake.evidence_refs[0].revision == 1
    assert "task_type" not in Wake.model_fields


def test_a07_wake_evidence_is_pinned_and_cross_timezone_order_uses_instants():
    with pytest.raises(ValidationError):
        make_wake(evidence_refs=[ObjectRef(object_id="obs-a", revision=None)])

    first = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    later_same_instant_order = datetime(2026, 9, 14, 20, 30, tzinfo=timezone(timedelta(hours=8)))
    wake = make_wake(first_hit_at=first, last_hit_at=later_same_instant_order)
    assert wake.last_hit_at == later_same_instant_order

    earlier = datetime(2026, 9, 14, 19, 0, tzinfo=timezone(timedelta(hours=8)))
    with pytest.raises(ValidationError):
        make_wake(first_hit_at=first, last_hit_at=earlier)


def test_a08_session_pins_wake_and_freezes_world_snapshot_for_recovery():
    session = make_session(
        wake_ref=ObjectRef(object_id="wake-a", revision=2),
        snapshot_world_revision=17,
        operation_ids=["op-1", "op-2"],
        checkpoint={"next": "wait for user response"},
        session_state="waiting",
    )
    assert session.wake_ref.revision == 2
    assert session.snapshot_world_revision == 17
    assert session.operation_ids == ["op-1", "op-2"]
    assert session.checkpoint["next"] == "wait for user response"

    with pytest.raises(ValidationError):
        make_session(wake_ref=ObjectRef(object_id="wake-a", revision=None))


def test_a09_action_has_stable_execution_receipt_identity_and_pinned_task_origin():
    execution_id = "exec-001"
    action = make_action(
        execution_id=execution_id,
        task_ref=ObjectRef(object_id="task-a", revision=1),
        action_status=ActionStatus.SUBMITTED,
    )
    assert action.execution_id == execution_id
    assert action.task_ref.revision == 1
    assert action.action_status is ActionStatus.SUBMITTED

    with pytest.raises(ValidationError):
        make_action(task_ref=ObjectRef(object_id="task-a", revision=None))


def test_a10_outcome_is_not_action_and_can_remain_unknown():
    action = make_action()
    outcome = make_outcome(ObjectRef(object_id=action.object_id, revision=1))
    assert outcome.object_type is ObjectType.OUTCOME
    assert outcome.action_ref.object_id == action.object_id
    assert outcome.outcome_state == "unknown"
    assert "action_status" not in Outcome.model_fields
    assert "outcome_state" not in Action.model_fields


def test_a11_outcome_action_and_evidence_refs_are_pinned():
    with pytest.raises(ValidationError):
        make_outcome(ObjectRef(object_id="action-a", revision=None))
    with pytest.raises(ValidationError):
        make_outcome(
            ObjectRef(object_id="action-a", revision=1),
            evidence_refs=[ObjectRef(object_id="obs-a", revision=None)],
        )


def test_a12_notification_delivery_does_not_prove_learning_success():
    notify_task = make_task(
        task_type=TaskType.FOLLOW_UP,
        title="发送复习提醒",
        completion_condition={"requires": "delivery_receipt"},
    )
    learning_task = make_task(
        task_type=TaskType.VERIFICATION,
        title="验证是否掌握知识点",
        completion_condition={"requires": "quiz_result"},
    )
    action = make_action(task_ref=ObjectRef(object_id=notify_task.object_id, revision=1))
    delivery = make_outcome(
        ObjectRef(object_id=action.object_id, revision=1),
        outcome_state="delivered",
    )

    assert notify_task.completion_condition != learning_task.completion_condition
    assert delivery.outcome_state == "delivered"
    assert learning_task.task_state is TaskState.DRAFT


def test_a13_five_objects_roundtrip_and_refs_survive_sqlite(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")

    task = make_task()
    store.commit([task], make_op(0))

    wake = make_wake(evidence_refs=[ObjectRef(object_id=task.object_id, revision=1)])
    store.commit([wake], make_op(1))

    session = make_session(
        wake_ref=ObjectRef(object_id=wake.object_id, revision=1),
        snapshot_world_revision=2,
        operation_ids=["op-a"],
        checkpoint={"state": "started"},
    )
    store.commit([session], make_op(2))

    action = make_action(task_ref=ObjectRef(object_id=task.object_id, revision=1))
    store.commit([action], make_op(3))

    outcome = make_outcome(
        ObjectRef(object_id=action.object_id, revision=1),
        outcome_state="unknown",
    )
    store.commit([outcome], make_op(4))

    assert store.get_payload(task.object_id)["object_type"] == ObjectType.TASK.value
    assert store.get_payload(wake.object_id)["evidence_refs"][0]["revision"] == 1
    assert store.get_payload(session.object_id)["snapshot_world_revision"] == 2
    assert store.get_payload(action.object_id)["execution_id"] == action.execution_id
    assert store.get_payload(outcome.object_id)["outcome_state"] == "unknown"


def test_a14_post_validation_mutation_of_task_provenance_is_rejected_atomically(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    task = make_task(reason_refs=[ObjectRef(object_id="reason-a", revision=1)])
    task.reason_refs.append(ObjectRef(object_id="reason-b", revision=None))

    with pytest.raises(StoreError) as exc_info:
        store.commit([task], make_op(0))
    assert exc_info.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc_info.value.context["reason"] == "persistence_revalidation_failed"
    assert store.world_revision == 0
    assert store.list_payloads(object_type=ObjectType.TASK) == []


def test_a15_post_validation_mutation_of_wake_evidence_is_rejected_atomically(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    wake = make_wake(evidence_refs=[ObjectRef(object_id="obs-a", revision=1)])
    wake.evidence_refs.append(ObjectRef(object_id="obs-b", revision=None))

    with pytest.raises(StoreError) as exc_info:
        store.commit([wake], make_op(0))
    assert exc_info.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc_info.value.context["reason"] == "persistence_revalidation_failed"
    assert store.world_revision == 0


def test_a16_action_completion_and_outcome_are_independent_states():
    action = make_action(action_status=ActionStatus.COMPLETED)
    unknown = make_outcome(ObjectRef(object_id=action.object_id, revision=1), outcome_state="unknown")
    rejected = make_outcome(ObjectRef(object_id=action.object_id, revision=1), outcome_state="user_rejected")

    assert action.action_status is ActionStatus.COMPLETED
    assert unknown.outcome_state == "unknown"
    assert rejected.outcome_state == "user_rejected"
    assert unknown.outcome_state != rejected.outcome_state


def test_a17_task_status_is_not_goal_or_outcome_status():
    task = make_task(task_state=TaskState.COMPLETED)
    assert task.task_state is TaskState.COMPLETED
    assert "goal_status" not in Task.model_fields
    assert "outcome_state" not in Task.model_fields


def test_a18_no_scheduler_service_is_implemented_by_contract_fixture():
    # M0-014 freezes durable objects only. Runtime scheduling remains a later M2 concern.
    assert "scheduler" not in Task.model_fields
    assert "dispatch" not in Wake.model_fields
    assert "retry_policy_engine" not in Action.model_fields
