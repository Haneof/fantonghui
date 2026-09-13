from __future__ import annotations

from aios_core.contracts.enums import EventStatus, TaskState


_TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
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
    TaskState.WAITING_RESULT: {TaskState.READY, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.BLOCKED: {TaskState.READY, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.EXPIRED: set(),
    TaskState.CANCELLED: set(),
}

_EVENT_TRANSITIONS: dict[EventStatus, set[EventStatus]] = {
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
    EventStatus.REVISED: {EventStatus.ACTIVE, EventStatus.RESOLVED, EventStatus.REJECTED, EventStatus.MERGED, EventStatus.SPLIT},
    EventStatus.REJECTED: {EventStatus.REVISED},
    EventStatus.MERGED: set(),
    EventStatus.SPLIT: set(),
}


def validate_task_transition(current: TaskState, target: TaskState) -> None:
    if target not in _TASK_TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current.value} -> {target.value}")


def validate_event_transition(current: EventStatus, target: EventStatus) -> None:
    if target not in _EVENT_TRANSITIONS[current]:
        raise ValueError(f"invalid event transition: {current.value} -> {target.value}")
