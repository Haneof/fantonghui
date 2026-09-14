"""M0-013 Goal first-class contract and source-semantics tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import (
    GoalSourceType,
    GoalStatus,
    ObjectType,
    TaskState,
    TaskType,
)
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import Goal, Task
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def make_op(expected_world_revision: int) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_013_test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-013 test",
        idempotency_key=str(uuid.uuid4()),
    )


def make_goal(
    *,
    object_id: str | None = None,
    revision: int = 1,
    source_type: GoalSourceType = GoalSourceType.USER_EXPLICIT,
    goal_status: GoalStatus = GoalStatus.PROPOSED,
    title: str = "一年学会英语",
    description: str = "用户希望在一年内显著提升英语能力",
    learned_at: datetime = BASE,
    confidence: float = 0.9,
    **overrides,
) -> Goal:
    data = dict(
        object_id=object_id or new_object_id(ObjectType.GOAL),
        subject_id="user-1",
        revision=revision,
        occurred=TemporalExtent.unknown_time(),
        learned_at=learned_at,
        recorded_at=learned_at,
        created_by="test",
        owner_id="user-1",
        source_type=source_type,
        title=title,
        description=description,
        goal_status=goal_status,
        success_criteria=["能够通过约定的英语能力复测"],
        confidence=confidence,
    )
    data.update(overrides)
    return Goal(**data)


def test_g01_exact_goal_schema_and_literal_object_type():
    hints = get_type_hints(Goal)
    assert get_origin(hints["object_type"]) is Literal
    assert get_args(hints["object_type"]) == (ObjectType.GOAL,)
    assert hints["owner_id"] is str
    assert hints["source_type"] is GoalSourceType
    assert hints["title"] is str
    assert hints["description"] is str
    assert hints["goal_status"] is GoalStatus
    assert get_origin(hints["success_criteria"]) is list
    assert get_args(hints["success_criteria"]) == (str,)
    for field_name in ["related_dimension_refs", "related_event_refs", "related_task_refs"]:
        assert get_origin(hints[field_name]) is list
        assert get_args(hints[field_name]) == (ObjectRef,)
    assert get_origin(hints["app_ids"]) is list
    assert get_args(hints["app_ids"]) == (str,)
    assert hints["confidence"] is float


def test_g02_goal_status_exact_r2_values_and_default_proposed():
    assert {item.value for item in GoalStatus} == {
        "proposed",
        "active",
        "paused",
        "achieved",
        "abandoned",
        "unknown",
    }
    assert make_goal().goal_status is GoalStatus.PROPOSED


def test_g03_explicit_and_inferred_same_text_are_semantically_distinct():
    explicit = make_goal(
        source_type=GoalSourceType.USER_EXPLICIT,
        title="我要减肥",
        confidence=1.0,
    )
    inferred = make_goal(
        source_type=GoalSourceType.USER_INFERRED,
        title="我要减肥",
        confidence=0.55,
    )
    assert explicit.title == inferred.title
    assert explicit.source_type is GoalSourceType.USER_EXPLICIT
    assert inferred.source_type is GoalSourceType.USER_INFERRED
    assert explicit.confidence != inferred.confidence


def test_g04_app_goal_has_distinct_source_and_app_link():
    goal = make_goal(
        source_type=GoalSourceType.APP,
        title="完成本阶段英语课程",
        app_ids=["education-app"],
    )
    assert goal.source_type is GoalSourceType.APP
    assert goal.app_ids == ["education-app"]


def test_g05_ai_self_is_not_user_inferred():
    user_inferred = make_goal(source_type=GoalSourceType.USER_INFERRED)
    ai_self = make_goal(source_type=GoalSourceType.AI_SELF, owner_id="ai-self")
    assert user_inferred.source_type is not ai_self.source_type
    assert user_inferred.owner_id == "user-1"
    assert ai_self.owner_id == "ai-self"


def test_g06_confidence_bounds():
    for value in (0.0, 0.5, 1.0):
        assert make_goal(confidence=value).confidence == value
    for value in (-0.01, 1.01):
        with pytest.raises(ValidationError):
            make_goal(confidence=value)


def test_g07_goal_is_not_task_and_does_not_embed_task_runtime_fields():
    goal_fields = Goal.model_fields
    assert "task_state" not in goal_fields
    assert "deadline" not in goal_fields
    assert "next_wake_at" not in goal_fields
    assert "completion_condition" not in goal_fields
    assert "goal_status" in goal_fields
    assert "success_criteria" in goal_fields

    task_hints = get_type_hints(Task)
    goal_ref_args = set(get_args(task_hints["goal_ref"]))
    assert goal_ref_args == {ObjectRef, type(None)}
    assert str not in goal_ref_args


def test_g08_committing_goal_does_not_auto_create_task(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    goal = make_goal(goal_status=GoalStatus.ACTIVE)
    result = store.commit([goal], make_op(0))
    assert result.world_revision == 1
    assert len(store.list_payloads(object_type=ObjectType.GOAL)) == 1
    assert store.list_payloads(object_type=ObjectType.TASK) == []


def test_g09_same_text_different_sources_persist_as_distinct_goals(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    explicit = make_goal(
        source_type=GoalSourceType.USER_EXPLICIT,
        title="我要减肥",
        confidence=1.0,
    )
    inferred = make_goal(
        source_type=GoalSourceType.USER_INFERRED,
        title="我要减肥",
        confidence=0.45,
    )
    store.commit([explicit, inferred], make_op(0))
    payloads = store.list_payloads(object_type=ObjectType.GOAL)
    assert len(payloads) == 2
    assert {p["source_type"] for p in payloads} == {
        GoalSourceType.USER_EXPLICIT.value,
        GoalSourceType.USER_INFERRED.value,
    }
    assert explicit.object_id != inferred.object_id


def test_g10_related_links_are_navigation_not_copied_objects():
    dimension_id = new_object_id(ObjectType.DIMENSION_DEFINITION)
    event_id = new_object_id(ObjectType.EVENT)
    task_id = new_object_id(ObjectType.TASK)
    goal = make_goal(
        related_dimension_refs=[ObjectRef(object_id=dimension_id, revision=None)],
        related_event_refs=[ObjectRef(object_id=event_id, revision=None)],
        related_task_refs=[ObjectRef(object_id=task_id, revision=None)],
    )
    assert goal.related_dimension_refs[0].object_id == dimension_id
    assert goal.related_event_refs[0].object_id == event_id
    assert goal.related_task_refs[0].object_id == task_id
    assert goal.related_task_refs[0].revision is None


def test_g11_user_denial_is_new_goal_revision_and_linked_task_stays_reviewable(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    goal_id = new_object_id(ObjectType.GOAL)
    inferred = make_goal(
        object_id=goal_id,
        revision=1,
        source_type=GoalSourceType.USER_INFERRED,
        goal_status=GoalStatus.PROPOSED,
        title="用户可能想减肥",
        confidence=0.62,
    )
    store.commit([inferred], make_op(0))

    task = Task(
        object_id=new_object_id(ObjectType.TASK),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=BASE + timedelta(seconds=1),
        recorded_at=BASE + timedelta(seconds=1),
        created_by="test",
        task_type=TaskType.FOLLOW_UP,
        task_state=TaskState.DRAFT,
        goal_ref=ObjectRef(object_id=goal_id, revision=1),
        title="复核减肥目标",
    )
    store.commit([task], make_op(1))

    denied = make_goal(
        object_id=goal_id,
        revision=2,
        source_type=GoalSourceType.USER_INFERRED,
        goal_status=GoalStatus.ABANDONED,
        title="用户可能想减肥",
        description="用户随后明确否认该推断目标",
        learned_at=BASE + timedelta(seconds=2),
        confidence=0.0,
    )
    store.commit([denied], make_op(2))

    old_goal = store.get_payload(goal_id, revision=1)
    new_goal = store.get_payload(goal_id, revision=2)
    task_payload = store.get_payload(task.object_id)
    assert old_goal["goal_status"] == GoalStatus.PROPOSED.value
    assert new_goal["goal_status"] == GoalStatus.ABANDONED.value
    assert task_payload["goal_ref"] == {"object_id": goal_id, "revision": 1}
    assert store.get_payload(goal_id, as_of_world_revision=1)["revision"] == 1
    assert store.get_payload(goal_id, as_of_world_revision=3)["revision"] == 2


def test_g12_success_criteria_are_goal_level_not_task_completion():
    goal = make_goal(
        success_criteria=[
            "英语复测达到约定标准",
            "延迟一个月后仍保持能力",
        ]
    )
    assert len(goal.success_criteria) == 2
    assert all(isinstance(item, str) for item in goal.success_criteria)
