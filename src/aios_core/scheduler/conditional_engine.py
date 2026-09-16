"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

场景：长期高压的创业企业法务总监，日程挂载 200 项跨周期复杂条件任务
（"诉讼对方实控人出现股权变更时提醒"、"连续 3 天晚间心率超过 95bpm
时启动心内科预约建档"、"回到上海办公室且非深度专注时提示签署对赌
回购协议"）。双轨引擎保证未成熟任务零 Token 隐形、机械条件零 LLM
快判、语义条件机会式捎带、状态机非法跃迁全拦截。
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.contracts.time import as_utc

__all__ = [
    "ConditionalTask",
    "ConditionalTaskEngine",
    "ConditionalTaskState",
    "ConditionKind",
    "IllegalStateTransitionError",
    "LEGAL_TASK_TRANSITIONS",
]


class ConditionalTaskState(StrEnum):
    """条件任务生命周期（M2-005R 专用四态，单向流转）。"""

    DORMANT = "dormant"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"


class IllegalStateTransitionError(ValueError):
    """任务状态机非法跃迁：任何从未就绪状态直接触发执行的操作。"""


class ConditionKind(StrEnum):
    """触发条件类别：前三类为 Level-1 机械客观条件，第四类为 Level-2 语义。"""

    TIME_DUE = "time_due"
    GEOFENCE_ENTER = "geofence_enter"
    HEART_RATE_THRESHOLD = "heart_rate_threshold"
    SEMANTIC_SCENE = "semantic_scene"


#: 状态机铁律：DORMANT -> READY -> RUNNING -> COMPLETED 单向流转。
LEGAL_TASK_TRANSITIONS: dict[ConditionalTaskState, frozenset[ConditionalTaskState]] = {
    ConditionalTaskState.DORMANT: frozenset({ConditionalTaskState.READY}),
    ConditionalTaskState.READY: frozenset({ConditionalTaskState.RUNNING}),
    ConditionalTaskState.RUNNING: frozenset({ConditionalTaskState.COMPLETED}),
    ConditionalTaskState.COMPLETED: frozenset(),
}

_LEVEL1_KINDS = frozenset(
    {
        ConditionKind.TIME_DUE,
        ConditionKind.GEOFENCE_ENTER,
        ConditionKind.HEART_RATE_THRESHOLD,
    }
)


@dataclass
class ConditionalTask:
    """一项条件任务（休眠即隐形，成熟方可进入看板视野）。"""

    task_id: str
    title: str
    condition_kind: ConditionKind
    condition_params: dict[str, Any] = field(default_factory=dict)
    state: ConditionalTaskState = ConditionalTaskState.DORMANT
    ready_at: datetime | None = None

    @property
    def level(self) -> int:
        return 1 if self.condition_kind in _LEVEL1_KINDS else 2


class ConditionalTaskEngine:
    """双轨条件调度引擎：Level-1 机械快轨 + Level-2 机会式捎带。"""

    def __init__(self) -> None:
        self._tasks: dict[str, ConditionalTask] = {}
        self._evening_hr_streaks: dict[str, int] = {}
        self.llm_calls = 0
        self.level1_evaluations = 0
        self.last_level1_latency_ms = 0.0

    # -- 登记与状态机 ---------------------------------------------------------

    def register_task(
        self,
        task_id: str,
        title: str,
        condition_kind: ConditionKind,
        condition_params: Mapping[str, Any] | None = None,
    ) -> ConditionalTask:
        if not task_id or not task_id.strip():
            raise ValueError("task_id must not be blank")
        if task_id in self._tasks:
            raise ValueError(f"task {task_id!r} already registered")
        task = ConditionalTask(
            task_id=task_id,
            title=title,
            condition_kind=condition_kind,
            condition_params=dict(condition_params or {}),
        )
        self._tasks[task_id] = task
        return task

    def task(self, task_id: str) -> ConditionalTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"task {task_id!r} is not registered") from exc

    def tasks_in_state(self, state: ConditionalTaskState) -> tuple[ConditionalTask, ...]:
        return tuple(t for t in self._tasks.values() if t.state is state)

    def transition(self, task_id: str, target: ConditionalTaskState) -> ConditionalTask:
        """受控状态跃迁：非法跃迁 100% 抛 IllegalStateTransitionError。"""

        task = self.task(task_id)
        allowed = LEGAL_TASK_TRANSITIONS[task.state]
        if target not in allowed:
            raise IllegalStateTransitionError(
                f"illegal task transition {task.state.value} -> {target.value}"
                f" for task {task_id!r}; legal chain is"
                " DORMANT -> READY -> RUNNING -> COMPLETED"
            )
        task.state = target
        return task

    # -- DORMANT 隐形与 Token 预算 ---------------------------------------------

    def visible_tasks(self) -> tuple[ConditionalTask, ...]:
        """看板可见任务：一切 DORMANT 任务绝对物理隐形。"""

        return tuple(t for t in self._tasks.values() if t.state is not ConditionalTaskState.DORMANT)

    def assemble_session_prompt(self) -> str:
        """常规会话 Prompt 组装：DORMANT 任务一个字节都不允许进入。"""

        return "\n".join(
            f"[{t.task_id}] {t.title}" for t in self.visible_tasks()
        )

    def dormant_token_consumption(self) -> int:
        """DORMANT 任务的 Token 消耗：按构造恒为 0（物理隐形证明）。"""

        prompt = self.assemble_session_prompt()
        dormant = self.tasks_in_state(ConditionalTaskState.DORMANT)
        leaked = sum(1 for t in dormant if t.title and t.title in prompt)
        if leaked:
            raise AssertionError("DORMANT tasks leaked into session prompt")
        return 0

    # -- Level-1 机械快轨：0 LLM、1ms 内纯 Python 判定 -------------------------

    def observe_evening_heart_rate(self, bpm: float) -> None:
        """喂养心率阈值类任务的连续超标计数（客观体征，无大模型参与）。"""

        for task in self._tasks.values():
            if task.condition_kind is not ConditionKind.HEART_RATE_THRESHOLD:
                continue
            threshold = float(task.condition_params.get("threshold_bpm", 95.0))
            streak = self._evening_hr_streaks.get(task.task_id, 0)
            self._evening_hr_streaks[task.task_id] = (
                streak + 1 if bpm > threshold else 0
            )

    def evaluate_level1(self, snapshot: Mapping[str, Any]) -> list[str]:
        """机械快轨批量判定：全部客观物理条件，纯 Python，0 大模型。

        ``snapshot`` 支持键：``now``（datetime）、``location``（str）、
        ``heart_rate_bpm``（float）。返回本轮跃迁至 READY 的任务 ID。
        """

        started = time.perf_counter()
        now = snapshot.get("now")
        location = snapshot.get("location")
        newly_ready: list[str] = []
        evaluated = 0

        for task in self._tasks.values():
            if task.state is not ConditionalTaskState.DORMANT or task.level != 1:
                continue
            evaluated += 1
            hit = False
            kind = task.condition_kind
            params = task.condition_params
            if kind is ConditionKind.TIME_DUE:
                due_at = params["due_at"]
                hit = now is not None and as_utc(now) >= as_utc(due_at)
            elif kind is ConditionKind.GEOFENCE_ENTER:
                hit = location is not None and location in params.get("locations", ())
            elif kind is ConditionKind.HEART_RATE_THRESHOLD:
                required = int(params.get("required_consecutive_days", 3))
                streak = self._evening_hr_streaks.get(task.task_id, 0)
                if "heart_rate_bpm" in snapshot:
                    bpm = float(snapshot["heart_rate_bpm"])
                    threshold = float(params.get("threshold_bpm", 95.0))
                    if bpm > threshold:
                        streak += 1
                        self._evening_hr_streaks[task.task_id] = streak
                hit = streak >= required
            if hit:
                self.transition(task.task_id, ConditionalTaskState.READY)
                task.ready_at = now
                newly_ready.append(task.task_id)

        self.level1_evaluations += evaluated
        self.last_level1_latency_ms = (time.perf_counter() - started) * 1000.0
        return newly_ready

    # -- Level-2 机会式捎带：绝不自主唤醒大模型 ---------------------------------

    def piggyback_level2(
        self,
        *,
        user_initiated: bool,
        scene: str | None,
        llm_sink: Callable[[tuple[ConditionalTask, ...], str], dict[str, bool]],
    ) -> list[str]:
        """机会式捎带评估：仅用户主动唤醒且场景相关时顺路执行。

        ``llm_sink`` 接收（匹配到的休眠任务元组, 场景）并返回
        ``{task_id: 是否成熟}`` 裁决；每次捎带恰好计 1 次大模型调用。
        非用户主动或场景不匹配时原路返回，大模型调用次数严格为 0。
        """

        if not user_initiated or not scene:
            return []
        candidates = tuple(
            t
            for t in self._tasks.values()
            if t.state is ConditionalTaskState.DORMANT
            and t.condition_kind is ConditionKind.SEMANTIC_SCENE
            and t.condition_params.get("scene") == scene
        )
        if not candidates:
            return []
        self.llm_calls += 1
        verdicts = llm_sink(candidates, scene)
        newly_ready: list[str] = []
        for task in candidates:
            if verdicts.get(task.task_id):
                self.transition(task.task_id, ConditionalTaskState.READY)
                newly_ready.append(task.task_id)
        return newly_ready

    # -- 执行链 ---------------------------------------------------------------

    def start_task(self, task_id: str) -> ConditionalTask:
        """READY -> RUNNING；DORMANT 直接触发执行将被状态机拦截。"""

        return self.transition(task_id, ConditionalTaskState.RUNNING)

    def complete_task(self, task_id: str) -> ConditionalTask:
        return self.transition(task_id, ConditionalTaskState.COMPLETED)
