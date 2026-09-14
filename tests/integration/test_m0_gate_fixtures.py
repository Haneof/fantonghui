from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from aios_core.contracts.enums import (
    ClaimType,
    EventStatus,
    GoalSourceType,
    GoalStatus,
    KnowledgeState,
    ObjectType,
    TaskState,
    TaskType,
)
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import Claim, Entity, EventAnchor, Goal, Task
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.query import HistoricalWorldQuery
from aios_core.services import validate_event_revision_transition, validate_task_revision_transition
from aios_core.storage import SQLiteWorldStore


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def op(expected: int, reason: str) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_gate_fixture",
        arguments={"fixture": reason},
        expected_world_revision=expected,
        reason=reason,
        idempotency_key=str(uuid.uuid4()),
    )


def common(object_type: ObjectType, *, revision: int = 1, learned_at: datetime = BASE) -> dict:
    return {
        "object_id": new_object_id(object_type),
        "subject_id": "user-1",
        "revision": revision,
        "occurred": TemporalExtent.unknown_time(),
        "learned_at": learned_at,
        "recorded_at": learned_at,
        "created_by": "m0-gate",
    }


def test_gate_fixture_sports_day_revision_is_historically_replayable(tmp_path):
    store = SQLiteWorldStore(tmp_path / "sports.db")
    event_id = new_object_id(ObjectType.EVENT)
    rev1 = EventAnchor(
        **{**common(ObjectType.EVENT), "object_id": event_id},
        title="可能是学校运动会",
        interpretation="操场活动信号支持候选体育事件",
        event_status=EventStatus.CANDIDATE,
        event_time=TemporalExtent.point(BASE),
        confidence=0.45,
    )
    store.commit([rev1], op(0, "sports-day candidate"))
    rev2 = EventAnchor(
        **{**common(ObjectType.EVENT, revision=2, learned_at=BASE + timedelta(minutes=1)), "object_id": event_id},
        title="学校运动会",
        interpretation="后续资料确认运动会解释",
        event_status=EventStatus.ACTIVE,
        event_time=TemporalExtent.point(BASE),
        confidence=0.82,
    )
    validate_event_revision_transition(rev1, rev2)
    store.commit([rev2], op(1, "sports-day active"))

    history = HistoricalWorldQuery(store)
    assert history.get(event_id, as_of_world_revision=1).payloads[0]["revision"] == 1
    assert history.get(event_id, as_of_world_revision=1).payloads[0]["event_status"] == "candidate"
    assert history.get(event_id, as_of_world_revision=2).payloads[0]["revision"] == 2
    assert history.get(event_id, as_of_world_revision=2).payloads[0]["event_status"] == "active"
    assert store.current_world_revision() == 2


def test_gate_fixture_unknown_person_preserves_unknown_identity(tmp_path):
    store = SQLiteWorldStore(tmp_path / "unknown-person.db")
    person = Entity(
        **common(ObjectType.ENTITY),
        entity_kind="person",
        canonical_name=None,
        aliases=["操场边穿蓝衣的人"],
        identity_claim_refs=[],
    )
    store.commit([person], op(0, "unknown-person"))
    payload = store.get_payload(person.object_id)

    assert payload["object_type"] == "entity"
    assert payload["entity_kind"] == "person"
    assert payload["canonical_name"] is None
    assert payload["aliases"] == ["操场边穿蓝衣的人"]
    assert payload["identity_claim_refs"] == []


def test_gate_fixture_future_prediction_is_claim_not_future_fact(tmp_path):
    store = SQLiteWorldStore(tmp_path / "prediction.db")
    future = BASE + timedelta(days=1)
    prediction = Claim(
        **common(ObjectType.CLAIM),
        claimant_id="ai-self",
        claim_type=ClaimType.PREDICTION,
        content="用户明天可能参加跑步训练",
        valid_time=TemporalExtent.point(future),
        asserted_at=BASE,
        knowledge_state=KnowledgeState.INFERRED,
        confidence=0.61,
    )
    store.commit([prediction], op(0, "future-prediction"))
    payload = store.get_payload(prediction.object_id)

    assert payload["claim_type"] == "prediction"
    assert payload["knowledge_state"] == "inferred"
    assert payload["confidence"] == 0.61
    assert payload["asserted_at"].startswith("2026-09-14")
    assert payload["valid_time"]["start"].startswith("2026-09-15")
    assert payload["claim_type"] != "fact"


def test_gate_fixture_goal_and_task_remain_separate_lifecycles(tmp_path):
    store = SQLiteWorldStore(tmp_path / "goal-task.db")
    goal = Goal(
        **common(ObjectType.GOAL),
        owner_id="user-1",
        source_type=GoalSourceType.USER_EXPLICIT,
        title="提升英语能力",
        description="长期目标",
        goal_status=GoalStatus.ACTIVE,
        success_criteria=["英语复测达到约定标准"],
        confidence=1.0,
    )
    store.commit([goal], op(0, "goal"))

    task_id = new_object_id(ObjectType.TASK)
    task1 = Task(
        **{**common(ObjectType.TASK, learned_at=BASE + timedelta(seconds=1)), "object_id": task_id},
        task_type=TaskType.IMMEDIATE,
        task_state=TaskState.RUNNING,
        goal_ref=ObjectRef(object_id=goal.object_id, revision=1),
        title="完成一次英语练习",
        completion_condition={"exercise_submitted": True},
    )
    store.commit([task1], op(1, "task-running"))
    task2 = Task(
        **{**common(ObjectType.TASK, revision=2, learned_at=BASE + timedelta(seconds=2)), "object_id": task_id},
        task_type=TaskType.IMMEDIATE,
        task_state=TaskState.COMPLETED,
        goal_ref=ObjectRef(object_id=goal.object_id, revision=1),
        title="完成一次英语练习",
        completion_condition={"exercise_submitted": True},
    )
    validate_task_revision_transition(task1, task2)
    store.commit([task2], op(2, "task-completed"))

    goal_payload = store.get_payload(goal.object_id)
    task_payload = store.get_payload(task_id)
    assert task_payload["task_state"] == "completed"
    assert goal_payload["goal_status"] == "active"
    assert goal_payload["goal_status"] != "achieved"
    assert task_payload["goal_ref"] == {"object_id": goal.object_id, "revision": 1}
    assert len(store.list_payloads(object_type=ObjectType.GOAL)) == 1
    assert len(store.list_payloads(object_type=ObjectType.TASK)) == 1
