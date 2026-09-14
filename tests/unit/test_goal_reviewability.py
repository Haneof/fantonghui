"""M0-013 guard that denial of an inferred Goal leaves related Task review links explicit."""
import uuid
from datetime import datetime, timedelta, timezone

from aios_core.contracts.enums import GoalSourceType, GoalStatus, ObjectType, TaskState, TaskType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import Goal, Task
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def op(rev: int) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_013_reviewability",
        expected_world_revision=rev,
        reason="goal reviewability test",
        idempotency_key=str(uuid.uuid4()),
    )


def test_denied_inferred_goal_revision_explicitly_keeps_related_task_reviewable(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    goal_id = new_object_id(ObjectType.GOAL)
    goal_v1 = Goal(
        object_id=goal_id,
        subject_id="user-1",
        revision=1,
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        owner_id="user-1",
        source_type=GoalSourceType.USER_INFERRED,
        title="用户可能想减肥",
        description="AI根据可见资料提出的待确认目标",
        goal_status=GoalStatus.PROPOSED,
        confidence=0.6,
    )
    store.commit([goal_v1], op(0))

    task = Task(
        object_id=new_object_id(ObjectType.TASK),
        subject_id="user-1",
        revision=1,
        learned_at=BASE + timedelta(seconds=1),
        recorded_at=BASE + timedelta(seconds=1),
        created_by="test",
        task_type=TaskType.FOLLOW_UP,
        task_state=TaskState.DRAFT,
        goal_ref=ObjectRef(object_id=goal_id, revision=1),
        title="确认用户是否真的有减肥目标",
    )
    store.commit([task], op(1))

    goal_v2 = Goal(
        object_id=goal_id,
        subject_id="user-1",
        revision=2,
        learned_at=BASE + timedelta(seconds=2),
        recorded_at=BASE + timedelta(seconds=2),
        created_by="test",
        owner_id="user-1",
        source_type=GoalSourceType.USER_INFERRED,
        title="用户可能想减肥",
        description="用户明确否认，因此该推断目标废弃；相关Task需要复核",
        goal_status=GoalStatus.ABANDONED,
        related_task_refs=[ObjectRef(object_id=task.object_id, revision=1)],
        confidence=0.0,
    )
    store.commit([goal_v2], op(2))

    revised = store.get_payload(goal_id, revision=2)
    linked_task = store.get_payload(task.object_id, revision=1)
    assert revised["related_task_refs"] == [
        {"object_id": task.object_id, "revision": 1}
    ]
    assert linked_task["goal_ref"] == {"object_id": goal_id, "revision": 1}
    assert revised["goal_status"] == GoalStatus.ABANDONED.value
