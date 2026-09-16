"""推断目标与任务解耦治理（Goal Inference & Decoupling，阶段六核心算子）。

宪法依据
--------
* 第十五条第 7 款：**禁止 AI 猜测直接变成绝对事实** —— 推断必须是"源类型 +
  置信度"齐全的一等对象，而不是隐性的系统默认；
* 第七条第 1 款（隐式纠偏）：用户在日常对话里否认，系统**不得**反问确认，
  而应直接把原话作为高优先级 Observation 吸收，并静默撤销推断；
* 第十五条第 18 款 + 第八十六条：目标与任务解耦 —— 目标被撤销不等于任务被静默
  执行，未成熟任务必须休眠，绝不空转 Token。

本模块提供的机制
----------------
1. ``infer_goal``：把一次推断固化为 ``GoalSourceType.USER_INFERRED`` 的 Goal，
   并记录推断依据（Observation 指针）与置信度；同时可以挂一个**独立**的 Task；
2. ``retract``：用户否认时立刻把 Goal 置为 ABANDONED，把否认原话写成 Observation
   留痕，把关联任务取消，并产出一条反思记录（CommunicationExperience 语义的五元组）——
   整个过程是"静默"的：不向用户确认、不弹 UI（宪法第六条）；
3. ``audit``：目标与任务的解耦账目（有多少任务是无目标支撑的、有多少目标无任务）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import (
    GoalSourceType,
    GoalStatus,
    ObjectType,
    SourceClass,
    TaskState,
    TaskType,
)
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import Goal, Observation, Task, TemporalExtent
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import as_utc
from aios_core.services.state_machines import validate_task_transition
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

__all__ = [
    "GoalInferenceRegistry",
    "GoalRetraction",
    "InferenceAudit",
]


class GoalRetraction(BaseModel):
    """一次用户否认触发的撤销回执（含反思记录，全部留痕）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_id: str
    retracted_at: datetime
    denial_observation_id: str
    cancelled_task_ids: tuple[str, ...] = ()
    reflection: str = Field(min_length=1)
    asked_user_to_confirm: bool = False


class InferenceAudit(BaseModel):
    """目标/任务解耦账目。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inferred_goals: int = Field(ge=0)
    active_inferred_goals: int = Field(ge=0)
    abandoned_inferred_goals: int = Field(ge=0)
    goals_without_tasks: int = Field(ge=0)
    tasks_without_goals: int = Field(ge=0)
    dormant_tasks: int = Field(ge=0)


class GoalInferenceRegistry:
    """推断目标的登记、解耦与撤销（全部落库，可审计）。"""

    def __init__(self, store: SQLiteWorldStore, *, subject_id: str = "user_1") -> None:
        self.store = store
        self.subject_id = subject_id
        self._goals: dict[str, Goal] = {}
        self._tasks: dict[str, Task] = {}
        self._retractions: list[GoalRetraction] = []

    # ------------------------------------------------------------------
    # 推断登记
    # ------------------------------------------------------------------

    def infer_goal(
        self,
        *,
        title: str,
        description: str,
        evidence_refs: Sequence[ObjectRef],
        confidence: float,
        learned_at: datetime,
        commit: bool = True,
    ) -> Goal:
        """把一次推断写成 Goal（source_type=USER_INFERRED，带证据指针与置信度）。"""

        stamp = as_utc(learned_at, "learned_at")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        for ref in evidence_refs:
            if ref.revision is None:
                raise ValueError("inferred goal requires pinned evidence revisions")
        goal = Goal(
            object_id=new_object_id(ObjectType.GOAL),
            subject_id=self.subject_id,
            revision=1,
            owner_id=self.subject_id,
            source_type=GoalSourceType.USER_INFERRED,
            title=title,
            description=description,
            goal_status=GoalStatus.PROPOSED,
            confidence=confidence,
            related_event_refs=list(evidence_refs),
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            created_by="goal_inference_registry",
            metadata={"inference_basis": [ref.object_id for ref in evidence_refs]},
        )
        self._goals[goal.object_id] = goal
        if commit:
            self._commit([goal], "world.goal.infer", f"推断目标：{title}")
        return goal

    def attach_task(
        self,
        *,
        goal: Goal | None,
        title: str,
        task_type: TaskType = TaskType.FOLLOW_UP,
        next_wake_at: datetime | None = None,
        priority: int = 50,
        learned_at: datetime,
        commit: bool = True,
    ) -> Task:
        """为目标挂一个**独立**任务（目标可为 None：任务不依赖目标存在）。"""

        stamp = as_utc(learned_at, "learned_at")
        task = Task(
            object_id=new_object_id(ObjectType.TASK),
            subject_id=self.subject_id,
            revision=1,
            task_type=task_type,
            task_state=TaskState.DRAFT,
            goal_ref=(
                ObjectRef(object_id=goal.object_id, revision=goal.revision)
                if goal is not None
                else None
            ),
            title=title,
            priority=priority,
            next_wake_at=next_wake_at,
            timezone_name="UTC",
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            created_by="goal_inference_registry",
        )
        self._tasks[task.object_id] = task
        if commit:
            payload: list[Any] = [task]
            if goal is not None:
                successor = goal.model_copy(
                    update={
                        "revision": self._next_revision(goal.object_id),
                        "related_task_refs": [
                            *goal.related_task_refs,
                            ObjectRef(object_id=task.object_id, revision=task.revision),
                        ],
                    }
                )
                self._goals[goal.object_id] = successor
                payload.append(successor)
            self._commit(payload, "world.task.attach", f"挂任务：{title}")
        elif goal is not None:
            self._goals[goal.object_id] = goal.model_copy(
                update={
                    "related_task_refs": [
                        *goal.related_task_refs,
                        ObjectRef(object_id=task.object_id, revision=task.revision),
                    ]
                }
            )
        return task

    # ------------------------------------------------------------------
    # 用户否认 → 静默撤销
    # ------------------------------------------------------------------

    def retract(
        self,
        goal_id: str,
        *,
        denial_statement: str,
        learned_at: datetime,
        reflection: str | None = None,
        commit: bool = True,
    ) -> GoalRetraction:
        """用户在对话中否认该推断目标：立即撤销 + 取消任务 + 留痕 + 反思。

        注意宪法第七条：**绝不向用户确认**"是否更新记忆"——否认原话直接作为
        高优先级 Observation 吸收，撤销静默完成。
        """

        if not denial_statement.strip():
            raise ValueError("denial statement must not be blank")
        goal = self._goals.get(goal_id)
        if goal is None:
            raise KeyError(f"unknown goal: {goal_id!r}")
        stamp = as_utc(learned_at, "learned_at")

        denial = Observation(
            object_id=new_object_id(ObjectType.OBSERVATION),
            subject_id=self.subject_id,
            revision=1,
            source_kind="user_utterance",
            modality="text",
            value=denial_statement,
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            created_by="goal_inference_registry",
            metadata={"channel": "dialogue", "implicit_correction": True},
        )

        abandoned = goal.model_copy(
            update={
                "revision": self._next_revision(goal_id),
                "goal_status": GoalStatus.ABANDONED,
                "confidence": 0.0,
                "learned_at": stamp,
                "recorded_at": stamp,
            }
        )
        self._goals[goal_id] = abandoned

        cancelled: list[str] = []
        updated_tasks: list[Task] = []
        for task in list(self._tasks.values()):
            if task.goal_ref is None or task.goal_ref.object_id != goal_id:
                continue
            if task.task_state in {TaskState.CANCELLED, TaskState.COMPLETED}:
                continue
            validate_task_transition(task.task_state, TaskState.CANCELLED)
            successor = task.model_copy(
                update={
                    "revision": self._next_revision(task.object_id),
                    "task_state": TaskState.CANCELLED,
                    "learned_at": stamp,
                    "recorded_at": stamp,
                }
            )
            self._tasks[successor.object_id] = successor
            updated_tasks.append(successor)
            cancelled.append(successor.object_id)

        note = reflection or (
            "把'替他操心'当成了'他要做的事'：推断目标被用户否认，"
            "下次先问一句他到底想不想做，而不是直接建任务。"
        )
        retraction = GoalRetraction(
            goal_id=goal_id,
            retracted_at=stamp,
            denial_observation_id=denial.object_id,
            cancelled_task_ids=tuple(cancelled),
            reflection=note,
            asked_user_to_confirm=False,
        )
        self._retractions.append(retraction)

        if commit:
            self._commit(
                [denial, *updated_tasks, abandoned],
                "world.goal.retract",
                "用户否认推断目标：静默撤销并取消关联任务",
            )
        return retraction

    # ------------------------------------------------------------------
    # 只读视图
    # ------------------------------------------------------------------

    def goal(self, goal_id: str) -> Goal:
        return self._goals[goal_id]

    def task(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def retractions(self) -> tuple[GoalRetraction, ...]:
        return tuple(self._retractions)

    def audit(self) -> InferenceAudit:
        inferred = len(self._goals)
        active = sum(
            1
            for goal in self._goals.values()
            if goal.goal_status in {GoalStatus.PROPOSED, GoalStatus.ACTIVE}
        )
        abandoned = sum(
            1 for goal in self._goals.values() if goal.goal_status is GoalStatus.ABANDONED
        )
        goals_without_tasks = sum(1 for goal in self._goals.values() if not goal.related_task_refs)
        tasks_without_goals = sum(1 for task in self._tasks.values() if task.goal_ref is None)
        dormant = sum(
            1
            for task in self._tasks.values()
            if task.task_state in {TaskState.DRAFT, TaskState.WAITING_TIME, TaskState.BLOCKED}
        )
        return InferenceAudit(
            inferred_goals=inferred,
            active_inferred_goals=active,
            abandoned_inferred_goals=abandoned,
            goals_without_tasks=goals_without_tasks,
            tasks_without_goals=tasks_without_goals,
            dormant_tasks=dormant,
        )

    # ------------------------------------------------------------------

    def _next_revision(self, object_id: str) -> int:
        """世界里的下一个修订号（永远以存储现状为唯一真相，不做本地记账猜测）。"""

        try:
            payload = self.store.get_payload(object_id)
        except Exception:
            return 1
        return int(payload.get("revision", 1)) + 1

    def _commit(self, objects: Sequence[Any], operation_name: str, reason: str) -> None:
        self.store.commit(
            list(objects),
            OperationRequest(
                operation_id=new_operation_id(),
                operation_name=operation_name,
                expected_world_revision=self.store.current_world_revision(),
                reason=reason,
                idempotency_key=new_operation_id(),
                source_class=SourceClass.AI_COGNITION,
            ),
        )


class GoalDecouplingVerifier(BaseModel):
    """解耦不变量的显式声明（供看板/报告引用，避免口头承诺）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_retraction_cancels_tasks: bool = True
    task_may_exist_without_goal: bool = True
    retraction_asks_user: bool = False

    @model_validator(mode="after")
    def validate_invariants(self) -> "GoalDecouplingVerifier":
        if self.retraction_asks_user:
            raise ValueError("宪法第七条：隐式纠偏绝不向用户确认")
        if not self.goal_retraction_cancels_tasks:
            raise ValueError("目标被否认后必须连带取消未成熟任务")
        return self
