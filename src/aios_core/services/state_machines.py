from __future__ import annotations

from aios_core.contracts.enums import EventStatus, TaskState
from aios_core.contracts.models import EventAnchor, Task


_TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.DRAFT: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.READY: frozenset({TaskState.RUNNING, TaskState.CANCELLED, TaskState.EXPIRED}),
    TaskState.RUNNING: frozenset(
        {
            TaskState.WAITING_TIME,
            TaskState.WAITING_EVIDENCE,
            TaskState.WAITING_USER,
            TaskState.WAITING_RESULT,
            TaskState.BLOCKED,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING_TIME: frozenset(
        {TaskState.READY, TaskState.CANCELLED, TaskState.EXPIRED}
    ),
    TaskState.WAITING_EVIDENCE: frozenset(
        {TaskState.READY, TaskState.CANCELLED, TaskState.EXPIRED}
    ),
    TaskState.WAITING_USER: frozenset(
        {TaskState.READY, TaskState.CANCELLED, TaskState.EXPIRED}
    ),
    TaskState.WAITING_RESULT: frozenset(
        {TaskState.READY, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.BLOCKED: frozenset(
        {TaskState.READY, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.EXPIRED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}

_EVENT_TRANSITIONS: dict[EventStatus, frozenset[EventStatus]] = {
    EventStatus.CANDIDATE: frozenset(
        {
            EventStatus.ACTIVE,
            EventStatus.REVISED,
            EventStatus.REJECTED,
            EventStatus.MERGED,
            EventStatus.SPLIT,
        }
    ),
    EventStatus.ACTIVE: frozenset(
        {
            EventStatus.RESOLVED,
            EventStatus.REVISED,
            EventStatus.REJECTED,
            EventStatus.MERGED,
            EventStatus.SPLIT,
        }
    ),
    EventStatus.RESOLVED: frozenset(
        {EventStatus.REVISED, EventStatus.MERGED, EventStatus.SPLIT}
    ),
    EventStatus.REVISED: frozenset(
        {
            EventStatus.ACTIVE,
            EventStatus.RESOLVED,
            EventStatus.REJECTED,
            EventStatus.MERGED,
            EventStatus.SPLIT,
        }
    ),
    EventStatus.REJECTED: frozenset({EventStatus.REVISED}),
    EventStatus.MERGED: frozenset(),
    EventStatus.SPLIT: frozenset(),
}


def allowed_task_transitions(current: TaskState) -> frozenset[TaskState]:
    return _TASK_TRANSITIONS[current]


def allowed_event_transitions(current: EventStatus) -> frozenset[EventStatus]:
    return _EVENT_TRANSITIONS[current]


def validate_task_transition(current: TaskState, target: TaskState) -> None:
    if target not in _TASK_TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current.value} -> {target.value}")


def validate_event_transition(current: EventStatus, target: EventStatus) -> None:
    if target not in _EVENT_TRANSITIONS[current]:
        raise ValueError(f"invalid event transition: {current.value} -> {target.value}")


def validate_task_revision_transition(current: Task, target: Task) -> None:
    """Validate that one Task state change is expressed as the next object revision."""

    if target.object_id != current.object_id:
        raise ValueError("task transition revisions must keep the same object_id")
    if target.revision != current.revision + 1:
        raise ValueError(
            "task transition must create exactly the next object revision: "
            f"{current.revision} -> {target.revision}"
        )
    validate_task_transition(current.task_state, target.task_state)


def validate_event_revision_transition(current: EventAnchor, target: EventAnchor) -> None:
    """Validate that one Event state change is expressed as the next object revision."""

    if target.object_id != current.object_id:
        raise ValueError("event transition revisions must keep the same object_id")
    if target.revision != current.revision + 1:
        raise ValueError(
            "event transition must create exactly the next object revision: "
            f"{current.revision} -> {target.revision}"
        )
    validate_event_transition(current.event_status, target.event_status)
