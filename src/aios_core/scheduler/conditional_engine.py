"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

对应 R3-ARCH 蓝图 M2-020（条件驱动任务执行引擎），宪法依据：
V3 §86-2（条件驱动的任务零浪费执行法则）、§15-18（禁止每次唤醒无差别
执行全部待办）、§84-3（看板仅挂载当前已满足激活条件的任务）。

双轨设计（Level-1 / Level-2）：

* **Level-1 机械快轨**：纯时间到期、地理围栏、生理阈值等客观物理条件
  由本引擎在纯 Python 内判定（无任何大模型调用面），命中即自动
  ``DORMANT -> READY`` 跃迁。
* **Level-2 机会式捎带（Opportunistic Piggyback）**：依赖语义环境的
  任务，只在调用方显式提交会话场景上下文（用户已主动唤醒 AI 且场景
  相关）时，经调用方提供的评估器顺路判定。引擎自身**没有任何唤醒
  能力**——绝不为评估一个休眠任务而自主唤醒大模型。

DORMANT 隐形机制：看板装配只输出 READY 任务的简报，DORMANT 任务在
装配路径上**物理不存在**（不进列表、不进字符串、Token 贡献严格为 0）。

状态机铁律：``DORMANT -> READY -> RUNNING -> COMPLETED``，任何非法
跃迁抛出 :class:`IllegalStateTransitionError`。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from aios_core.contracts.time import require_aware

__all__ = [
    "ConditionalSchedulerEngine",
    "ConditionalTask",
    "GeoFenceCondition",
    "HeartRateThresholdCondition",
    "IllegalStateTransitionError",
    "MechanicalCondition",
    "SemanticCondition",
    "TaskState",
    "TimeDueCondition",
]

_TASK_STATE_VALUES = ("dormant", "ready", "running", "completed")


class TaskState(StrEnum):
    DORMANT = "dormant"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"


class IllegalStateTransitionError(Exception):
    """非法状态跃迁（含从未就绪状态直接触发执行）。"""

    def __init__(self, task_id: str, current: TaskState, requested: str) -> None:
        super().__init__(
            f"task {task_id}: illegal transition {current.value} -> {requested}"
        )
        self.task_id = task_id
        self.current = current
        self.requested = requested


class TimeDueCondition(BaseModel):
    """Level-1：绝对时间到期（如"09:00 提示签署对赌回购协议"）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["time_due"] = "time_due"
    due_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> "TimeDueCondition":
        require_aware(self.due_at, "due_at")
        return self

    def is_satisfied(self, ctx: Mapping[str, Any]) -> bool:
        now = ctx.get("now")
        return isinstance(now, datetime) and now >= self.due_at


class GeoFenceCondition(BaseModel):
    """Level-1：地理围栏（如"回到上海办公室"）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["geo_fence"] = "geo_fence"
    region_key: StrictStr = Field(min_length=1)

    def is_satisfied(self, ctx: Mapping[str, Any]) -> bool:
        return ctx.get("current_region") == self.region_key


class HeartRateThresholdCondition(BaseModel):
    """Level-1：生理阈值（如"连续 3 天晚间心率超过 95bpm"的当日判定）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["hr_threshold"] = "hr_threshold"
    bpm_greater_than: int = Field(ge=60, le=220)
    consecutive_windows: int = Field(default=1, ge=1, le=30)

    def is_satisfied(self, ctx: Mapping[str, Any]) -> bool:
        streak = ctx.get("hr_over_threshold_streak")
        return (
            isinstance(streak, int)
            and streak >= self.consecutive_windows
            and isinstance(ctx.get("hr_bpm"), (int, float))
            and ctx["hr_bpm"] > self.bpm_greater_than
        )


MechanicalCondition = Annotated[
    TimeDueCondition | GeoFenceCondition | HeartRateThresholdCondition,
    Field(discriminator="kind"),
]


class SemanticCondition(BaseModel):
    """Level-2：依赖语义环境（仅在机会式捎带会话中评估）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["semantic"] = "semantic"
    required_scene_tags: tuple[StrictStr, ...] = Field(min_length=1)


AnyCondition = Annotated[
    TimeDueCondition | GeoFenceCondition | HeartRateThresholdCondition | SemanticCondition,
    Field(discriminator="kind"),
]


class ConditionalTask(BaseModel):
    """带激活条件的任务（DORMANT 即物理隐形，Token 贡献为 0）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: StrictStr = Field(min_length=1)
    title: StrictStr = Field(min_length=1)
    condition: AnyCondition
    brief: StrictStr = Field(min_length=1)
    state: TaskState = TaskState.DORMANT
    priority: int = Field(default=50, ge=0, le=100)


class _EngineCounters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanical_evaluations: int = 0
    mechanical_promotions: int = 0
    piggyback_sessions: int = 0
    semantic_promotions: int = 0
    llm_calls: int = 0
    last_mechanical_sweep_ms: float = 0.0


class ConditionalSchedulerEngine:
    """双轨条件调度引擎。

    引擎本体**零大模型依赖**：``llm_calls`` 计数只可能因调用方通过
    :meth:`piggyback_evaluate` 显式注入评估器而增长；机械快轨永不触碰。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, ConditionalTask] = {}
        self._counters = _EngineCounters()

    # -- 登记 ---------------------------------------------------------

    def register(self, task: ConditionalTask) -> None:
        with self._lock:
            if task.task_id in self._tasks:
                raise ValueError(f"task {task.task_id} already registered")
            self._tasks[task.task_id] = task

    def register_many(self, tasks: Sequence[ConditionalTask]) -> None:
        for task in tasks:
            self.register(task)

    # -- Level-1：机械快轨（0 Token / 0 LLM） ---------------------------

    def mechanical_sweep(self, ctx: Mapping[str, Any]) -> tuple[str, ...]:
        """对全部 DORMANT 机械条件任务做一次纯 Python 判定。

        命中者立即跃迁 READY。全程无大模型调用；单次扫描耗时可计量
        （200 任务量级应在毫秒级内完成）。
        """
        started = time.perf_counter()
        promoted: list[str] = []
        with self._lock:
            for task in self._tasks.values():
                if task.state is not TaskState.DORMANT:
                    continue
                condition = task.condition
                if not isinstance(
                    condition,
                    (TimeDueCondition, GeoFenceCondition, HeartRateThresholdCondition),
                ):
                    continue
                self._counters.mechanical_evaluations += 1
                if condition.is_satisfied(ctx):
                    promoted_task = task.model_copy(update={"state": TaskState.READY})
                    self._tasks[task.task_id] = promoted_task
                    self._counters.mechanical_promotions += 1
                    promoted.append(task.task_id)
            self._counters.last_mechanical_sweep_ms = (
                (time.perf_counter() - started) * 1000.0
            )
        return tuple(promoted)

    # -- Level-2：机会式捎带（仅在用户会话中顺路评估） ------------------

    def piggyback_evaluate(
        self,
        *,
        session_id: str,
        scene_tags: tuple[str, ...],
        llm_evaluator: Callable[[ConditionalTask, Mapping[str, Any]], bool],
        session_ctx: Mapping[str, Any],
    ) -> tuple[str, ...]:
        """在调用方显式提供的会话场景中顺路评估语义条件任务。

        纪律：本方法是引擎唯一可能触碰评估器（大模型）的入口；没有
        用户会话就绝无评估——引擎没有自主唤醒能力。
        """
        if not session_id:
            raise ValueError("piggyback requires an explicit user session")
        promoted: list[str] = []
        with self._lock:
            self._counters.piggyback_sessions += 1
            for task in self._tasks.values():
                if task.state is not TaskState.DORMANT:
                    continue
                condition = task.condition
                if not isinstance(condition, SemanticCondition):
                    continue
                if not set(condition.required_scene_tags) <= set(scene_tags):
                    continue
                self._counters.llm_calls += 1
                verdict = bool(llm_evaluator(task, session_ctx))
                if verdict:
                    self._tasks[task.task_id] = task.model_copy(
                        update={"state": TaskState.READY}
                    )
                    self._counters.semantic_promotions += 1
                    promoted.append(task.task_id)
        return tuple(promoted)

    # -- 看板装配（DORMANT 物理隐形） -----------------------------------

    def assemble_kanban(self) -> tuple[dict[str, str], ...]:
        """只输出 READY 任务的看板条目。

        DORMANT 任务不进入返回结构（键、值、字符串都不存在），
        其 Token 贡献严格为 0。
        """
        with self._lock:
            ready = sorted(
                (t for t in self._tasks.values() if t.state is TaskState.READY),
                key=lambda t: (-t.priority, t.task_id),
            )
            return tuple(
                {"task_id": t.task_id, "brief": t.brief, "priority": t.priority}
                for t in ready
            )

    # -- 状态机（非法跃迁 100% 拦截） ------------------------------------

    def start(self, task_id: str) -> None:
        self._transition(task_id, TaskState.RUNNING, allowed_from=(TaskState.READY,))

    def complete(self, task_id: str) -> None:
        self._transition(
            task_id, TaskState.COMPLETED, allowed_from=(TaskState.RUNNING,)
        )

    def _transition(
        self,
        task_id: str,
        target: TaskState,
        *,
        allowed_from: tuple[TaskState, ...],
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"unknown task {task_id}")
            if task.state not in allowed_from:
                raise IllegalStateTransitionError(
                    task_id, task.state, target.value
                )
            self._tasks[task_id] = task.model_copy(update={"state": target})

    # -- 观测 ---------------------------------------------------------

    def task_state(self, task_id: str) -> TaskState:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"unknown task {task_id}")
            return task.state

    def stats(self) -> dict[str, float | int]:
        with self._lock:
            return {
                "tasks_total": len(self._tasks),
                "mechanical_evaluations": self._counters.mechanical_evaluations,
                "mechanical_promotions": self._counters.mechanical_promotions,
                "piggyback_sessions": self._counters.piggyback_sessions,
                "semantic_promotions": self._counters.semantic_promotions,
                "llm_calls": self._counters.llm_calls,
                "last_mechanical_sweep_ms": self._counters.last_mechanical_sweep_ms,
            }
