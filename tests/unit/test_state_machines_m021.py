"""M0-021 exhaustive Task/Event transition freeze and revision semantics."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios_core.contracts import (
    EventAnchor,
    EventStatus,
    ObjectRef,
    Task,
    TaskState,
    TaskType,
    TemporalExtent,
    new_object_id,
)
from aios_core.contracts.enums import ObjectType
from aios_core.services import (
    allowed_event_transitions,
    allowed_task_transitions,
    validate_event_revision_transition,
    validate_event_transition,
    validate_task_revision_transition,
    validate_task_transition,
)

NOW = datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)

EXPECTED_TASK = {
    TaskState.DRAFT: {TaskState.READY, TaskState.CANCELLED},
    TaskState.READY: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.EXPIRED},
    TaskState.RUNNING: {
        TaskState.WAITING_TIME,
        TaskState.WAITING_EVIDENCE,
        TaskState.WAITING_USER,
        TaskState.WAITING_RESULT,
        TaskState.BLOCKED,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING_TIME: {TaskState.READY, TaskState.CANCELLED, TaskState.EXPIRED},
    TaskState.WAITING_EVIDENCE: {TaskState.READY, TaskState.CANCELLED, TaskState.EXPIRED},
    TaskState.WAITING_USER: {TaskState.READY, TaskState.CANCELLED, TaskState.EXPIRED},
    TaskState.WAITING_RESULT: {
        TaskState.READY,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.BLOCKED: {TaskState.READY, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.EXPIRED: set(),
    TaskState.CANCELLED: set(),
}

EXPECTED_EVENT = {
    EventStatus.CANDIDATE: {
        EventStatus.ACTIVE,
        EventStatus.REVISED,
        EventStatus.REJECTED,
        EventStatus.MERGED,
        EventStatus.SPLIT,
    },
    EventStatus.ACTIVE: {
        EventStatus.RESOLVED,
        EventStatus.REVISED,
        EventStatus.REJECTED,
        EventStatus.MERGED,
        EventStatus.SPLIT,
    },
    EventStatus.RESOLVED: {EventStatus.REVISED, EventStatus.MERGED, EventStatus.SPLIT},
    EventStatus.REVISED: {
        EventStatus.ACTIVE,
        EventStatus.RESOLVED,
        EventStatus.REJECTED,
        EventStatus.MERGED,
        EventStatus.SPLIT,
    },
    EventStatus.REJECTED: {EventStatus.REVISED},
    EventStatus.MERGED: set(),
    EventStatus.SPLIT: set(),
}


def make_task(object_id: str, revision: int, state: TaskState) -> Task:
    return Task(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-021-test",
        task_type=TaskType.TODO,
        task_state=state,
        title="state-machine task",
    )


def make_event(object_id: str, revision: int, status: EventStatus) -> EventAnchor:
    kwargs = dict(
        object_id=object_id,
        subject_id="user_1",
        revision=revision,
        occurred=TemporalExtent.point(NOW),
        learned_at=NOW,
        recorded_at=NOW,
        created_by="m0-021-test",
        title="state-machine event",
        interpretation="event interpretation",
        event_status=status,
        event_time=TemporalExtent.point(NOW),
        confidence=0.5,
    )
    if status is EventStatus.REVISED:
        kwargs["supersedes_refs"] = [ObjectRef(object_id=object_id, revision=max(1, revision - 1))]
        kwargs["revision_reason"] = "revised interpretation"
    elif status is EventStatus.REJECTED:
        kwargs["revision_reason"] = "evidence rejected interpretation"
    elif status is EventStatus.MERGED:
        kwargs["merged_into_ref"] = ObjectRef(
            object_id=new_object_id(ObjectType.EVENT), revision=1
        )
        kwargs["revision_reason"] = "merged duplicate"
    elif status is EventStatus.SPLIT:
        kwargs["split_child_refs"] = [
            ObjectRef(object_id=new_object_id(ObjectType.EVENT), revision=1)
        ]
        kwargs["revision_reason"] = "split composite event"
    return EventAnchor(**kwargs)


def test_m021_task_transition_matrix_is_exact_and_complete():
    assert set(EXPECTED_TASK) == set(TaskState)
    for current in TaskState:
        assert allowed_task_transitions(current) == frozenset(EXPECTED_TASK[current])
        for target in TaskState:
            if target in EXPECTED_TASK[current]:
                validate_task_transition(current, target)
            else:
                with pytest.raises(ValueError, match="invalid task transition"):
                    validate_task_transition(current, target)


def test_m021_event_transition_matrix_is_exact_and_complete():
    assert set(EXPECTED_EVENT) == set(EventStatus)
    for current in EventStatus:
        assert allowed_event_transitions(current) == frozenset(EXPECTED_EVENT[current])
        for target in EventStatus:
            if target in EXPECTED_EVENT[current]:
                validate_event_transition(current, target)
            else:
                with pytest.raises(ValueError, match="invalid event transition"):
                    validate_event_transition(current, target)


def test_m021_mandatory_canaries():
    validate_task_transition(TaskState.RUNNING, TaskState.WAITING_RESULT)
    with pytest.raises(ValueError):
        validate_task_transition(TaskState.COMPLETED, TaskState.RUNNING)
    validate_event_transition(EventStatus.CANDIDATE, EventStatus.REJECTED)
    with pytest.raises(ValueError):
        validate_event_transition(EventStatus.MERGED, EventStatus.ACTIVE)


def test_m021_task_state_change_requires_next_revision_same_object():
    oid = new_object_id(ObjectType.TASK)
    current = make_task(oid, 1, TaskState.RUNNING)
    target = make_task(oid, 2, TaskState.WAITING_RESULT)
    validate_task_revision_transition(current, target)

    with pytest.raises(ValueError, match="same object_id"):
        validate_task_revision_transition(
            current,
            make_task(new_object_id(ObjectType.TASK), 2, TaskState.WAITING_RESULT),
        )
    with pytest.raises(ValueError, match="exactly the next object revision"):
        validate_task_revision_transition(
            current,
            make_task(oid, 3, TaskState.WAITING_RESULT),
        )


def test_m021_task_revision_helper_cannot_bypass_terminal_state():
    oid = new_object_id(ObjectType.TASK)
    current = make_task(oid, 1, TaskState.COMPLETED)
    target = make_task(oid, 2, TaskState.RUNNING)
    with pytest.raises(ValueError, match="invalid task transition"):
        validate_task_revision_transition(current, target)


def test_m021_event_state_change_requires_next_revision_same_object():
    oid = new_object_id(ObjectType.EVENT)
    current = make_event(oid, 1, EventStatus.CANDIDATE)
    target = make_event(oid, 2, EventStatus.REJECTED)
    validate_event_revision_transition(current, target)

    with pytest.raises(ValueError, match="same object_id"):
        validate_event_revision_transition(
            current,
            make_event(new_object_id(ObjectType.EVENT), 2, EventStatus.REJECTED),
        )
    with pytest.raises(ValueError, match="exactly the next object revision"):
        validate_event_revision_transition(
            current,
            make_event(oid, 3, EventStatus.REJECTED),
        )


def test_m021_event_revision_helper_cannot_revive_merged_event():
    oid = new_object_id(ObjectType.EVENT)
    current = make_event(oid, 1, EventStatus.MERGED)
    target = make_event(oid, 2, EventStatus.ACTIVE)
    with pytest.raises(ValueError, match="invalid event transition"):
        validate_event_revision_transition(current, target)


def test_m021_transition_maps_are_immutable_to_callers():
    task_allowed = allowed_task_transitions(TaskState.RUNNING)
    event_allowed = allowed_event_transitions(EventStatus.CANDIDATE)
    assert isinstance(task_allowed, frozenset)
    assert isinstance(event_allowed, frozenset)
    with pytest.raises(AttributeError):
        task_allowed.add(TaskState.DRAFT)  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        event_allowed.add(EventStatus.RESOLVED)  # type: ignore[attr-defined]
