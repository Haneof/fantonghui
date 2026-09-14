import pytest

from aios_core.contracts.enums import EventStatus, TaskState
from aios_core.services import validate_event_transition, validate_task_transition


def test_task_state_machine_allows_waiting():
    validate_task_transition(TaskState.RUNNING, TaskState.WAITING_RESULT)


def test_task_state_machine_rejects_completed_to_running():
    with pytest.raises(ValueError):
        validate_task_transition(TaskState.COMPLETED, TaskState.RUNNING)


def test_event_candidate_can_be_rejected():
    validate_event_transition(EventStatus.CANDIDATE, EventStatus.REJECTED)


def test_event_merged_is_terminal():
    with pytest.raises(ValueError):
        validate_event_transition(EventStatus.MERGED, EventStatus.ACTIVE)
