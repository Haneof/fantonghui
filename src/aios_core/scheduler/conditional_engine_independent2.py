"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

业务情境：高压法务总监挂载 200 项跨周期复杂条件任务
（股权监控 / 连续心率 / 地理围栏+专注度联合等）。

四大硬门禁与实现位置的映射：

1. 【未成熟任务 Token 严格为 0】
   ``ConditionalTaskEngine.prompt_view()`` 只物化 READY/RUNNING 任务，
   DORMANT 在看板与常规会话中**物理缺席**——不存在于字符串，自然 0 Token。
   引擎同时提供 ``dormant_token_cost()`` 恒 0 的合同面。

2. 【Level-1 机械快轨 0 Token 判定】
   纯时间绝对到期 / 地理围栏 / 连续心率阈值三类客观物理条件，
   由 ``mechanical_sweep()`` 用纯 Python（无任何 I/O 与模型调用）
   一次扫描完成 DORMANT→READY；``llm_invocations`` 实现期硬编码恒 0。

3. 【Level-2 机会式捎带（Opportunistic Piggyback)】
   语义型条件**不存在**独立评估入口——唯一入口是
   ``piggyback_on_wake(scene_tags)``，必须携带一次真实用户唤醒的场景标签；
   场景不相交则任务留在 DORMANT，绝不主动唤醒大模型。

4. 【状态机非法跃迁 100% 拦截】
   唯一合法迁移表：DORMANT→READY→RUNNING→COMPLETED。
   其他一切跃迁（含重复完成、逆向回退）一律 ``IllegalStateTransitionError``。

工程护栏（超出工单的自卫项，全部声明在此，不加暗桩）：
   - ``piggyback_on_wake`` 带空场景标签视为调用方缺陷，``ValueError`` 拒绝；
   - 任务触发的物理条件输入为只读 ``SensorSnapshot``（冻结 dataclass），
     判定函数无副作用、可重入、线程安全（无共享可变状态）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------

class TaskState(Enum):
    DORMANT = "DORMANT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


_ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    TaskState.DORMANT: frozenset({TaskState.READY}),
    TaskState.READY: frozenset({TaskState.RUNNING}),
    TaskState.RUNNING: frozenset({TaskState.COMPLETED}),
    TaskState.COMPLETED: frozenset(),
}


class IllegalStateTransitionError(RuntimeError):
    """任何偏离 DORMANT→READY→RUNNING→COMPLETED 的跃迁。"""

    def __init__(self, task_id: str, current: TaskState, target: TaskState) -> None:
        super().__init__(
            f"任务 {task_id} 非法跃迁 {current.value} -> {target.value}；"
            f"唯一合法流水线：DORMANT→READY→RUNNING→COMPLETED"
        )
        self.task_id = task_id
        self.current = current
        self.target = target


class TaskPriority(IntEnum):
    ROUTINE = 10
    HIGH = 20
    CRITICAL = 30


# ---------------------------------------------------------------------------
# 传感器快照（判定输入，只读）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SensorSnapshot:
    """一次机械判定的全部物理输入。冻结、可重入。"""

    at_ns: int
    heart_rate_bpm: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    #: 近 N 个"晚间"心率读数（旧→新）。连续阈值触发器消费。
    evening_hr_series: tuple[float, ...] = ()
    location_label: str | None = None


# ---------------------------------------------------------------------------
# Level-1 机械触发器（0 Token，纯 Python）
# ---------------------------------------------------------------------------

class MechanicalTrigger:
    """客观物理条件的判定协议。子类必须纯函数实现。"""

    def evaluate(self, snapshot: SensorSnapshot) -> bool:  # pragma: no cover
        raise NotImplementedError


@dataclass(frozen=True)
class AbsoluteTimeTrigger(MechanicalTrigger):
    """纯时间绝对到期。"""

    due_at_ns: int

    def evaluate(self, snapshot: SensorSnapshot) -> bool:
        return snapshot.at_ns >= self.due_at_ns


@dataclass(frozen=True)
class GeofenceTrigger(MechanicalTrigger):
    """地理围栏：当前位置落在以中心点为圆心 radius_m 内。"""

    center_lat: float
    center_lng: float
    radius_m: float

    def evaluate(self, snapshot: SensorSnapshot) -> bool:
        if snapshot.latitude is None or snapshot.longitude is None:
            return False
        return (
            _haversine_m(
                snapshot.latitude, snapshot.longitude, self.center_lat, self.center_lng
            )
            <= self.radius_m
        )


_EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class SustainedHeartRateTrigger(MechanicalTrigger):
    """连续 N 天晚间心率全部高于阈值才命中（单日尖峰不构成条件）。"""

    threshold_bpm: float
    min_consecutive_days: int

    def evaluate(self, snapshot: SensorSnapshot) -> bool:
        series = snapshot.evening_hr_series
        if len(series) < self.min_consecutive_days:
            return False
        recent = series[-self.min_consecutive_days :]
        return all(v > self.threshold_bpm for v in recent)


@dataclass(frozen=True)
class AnyOfTrigger(MechanicalTrigger):
    """多条件析取（任一机械条件命中即到期）。仍是纯机械判定。"""

    triggers: tuple[MechanicalTrigger, ...]

    def evaluate(self, snapshot: SensorSnapshot) -> bool:
        return any(t.evaluate(snapshot) for t in self.triggers)


# ---------------------------------------------------------------------------
# Level-2 语义触发器（仅捎带评估，不主动唤醒）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticSceneTrigger:
    """依赖语义场景的条件：只记录所需场景标签，由 wake 捎带比对。"""

    scene_tags: frozenset[str]

    def matches(self, wake_scene_tags: Iterable[str]) -> bool:
        return not self.scene_tags.isdisjoint(wake_scene_tags)


# ---------------------------------------------------------------------------
# 条件任务
# ---------------------------------------------------------------------------

@dataclass
class ConditionalTask:
    task_id: str
    title: str
    trigger: MechanicalTrigger
    priority: TaskPriority = TaskPriority.ROUTINE
    semantic: SemanticSceneTrigger | None = None
    state: TaskState = TaskState.DORMANT
    created_at_ns: int = 0
    ready_reason: str = ""

    def transition_to(self, target: TaskState, *, reason: str = "") -> None:
        """唯一状态变更入口：查表校验，非法即抛 IllegalStateTransitionError。"""
        if target not in _ALLOWED[self.state]:
            raise IllegalStateTransitionError(self.task_id, self.state, target)
        self.state = target
        if target is TaskState.READY and reason:
            self.ready_reason = reason

    def start_execution(self) -> None:
        """非 READY 直接触发执行的一律拦截。"""
        self.transition_to(TaskState.RUNNING)

    def complete(self) -> None:
        self.transition_to(TaskState.COMPLETED)


# ---------------------------------------------------------------------------
# 调度引擎
# ---------------------------------------------------------------------------

class ConditionalTaskEngine:
    """双轨调度：Level-1 机械快轨 + Level-2 机会式捎带。

    ``llm_invocations`` 恒 0：机械条件纯 Python 判定；
    语义条件仅在用户已唤醒时捎带（调用大模型的责任在上游会话，
    引擎自身绝不为其主动发起）。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ConditionalTask] = {}
        self.llm_invocations: int = 0  # 门禁 2/3 的合同计数器：实现期恒 0
        self.wake_piggyback_count: int = 0

    # ---------------- 注册 ----------------

    def register(self, task: ConditionalTask) -> None:
        if task.task_id in self._tasks:
            raise ValueError(f"重复注册任务: {task.task_id}")
        self._tasks[task.task_id] = task

    def get(self, task_id: str) -> ConditionalTask:
        return self._tasks[task_id]

    # ---------------- Level-1 机械快轨 ----------------

    def mechanical_sweep(self, snapshot: SensorSnapshot) -> list[str]:
        """一次纯 Python 扫描：机械条件到期的 DORMANT 任务直接跃迁 READY。

        无任何 I/O、无模型调用（llm_invocations 保持恒 0）。
        语义型任务即使存在机械触发，机械命中也照常跃迁（机械轨不读语义）。
        返回本轮跃迁的任务 id（按注册序）。
        """
        promoted: list[str] = []
        for task in self._tasks.values():
            if task.state is not TaskState.DORMANT:
                continue
            if task.trigger.evaluate(snapshot):
                task.transition_to(TaskState.READY, reason="L1机械条件命中")
                promoted.append(task.task_id)
        return promoted

    # ---------------- Level-2 机会式捎带 ----------------

    def piggyback_on_wake(self, wake_scene_tags: Iterable[str]) -> list[str]:
        """用户已唤醒的场景下，顺路评估语义型 DORMANT 任务。

        场景标签必须非空（视为一次真实唤醒的证据）；空标签属于调用方缺陷。
        场景不相交的任务保持 DORMANT，绝不触发唤醒。
        """
        tags = frozenset(wake_scene_tags)
        if not tags:
            raise ValueError("捎带评估必须携带真实唤醒的场景标签，空标签拒绝")
        self.wake_piggyback_count += 1
        promoted: list[str] = []
        for task in self._tasks.values():
            if task.state is not TaskState.DORMANT or task.semantic is None:
                continue
            if task.semantic.matches(tags):
                task.transition_to(TaskState.READY, reason="L2唤醒捎带命中")
                promoted.append(task.task_id)
        return promoted

    # ---------------- 看板物化（门禁 1：DORMANT 物理隐形） ----------------

    def prompt_view(self) -> list[str]:
        """只物化 READY / RUNNING 任务的看板行；DORMANT 物理缺席。"""
        lines: list[str] = []
        for task in self._tasks.values():
            if task.state in (TaskState.READY, TaskState.RUNNING):
                state_tag = "【就绪】" if task.state is TaskState.READY else "【执行中】"
                lines.append(f"{state_tag}{task.title}（{task.priority.name}）")
        return lines

    def dormant_token_cost(self) -> int:
        """合同面：DORMANT 任务的看板 Token 消耗，恒为 0。"""
        return 0

    # ---------------- 观察性 ----------------

    def state_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in TaskState}
        for task in self._tasks.values():
            counts[task.state.value] += 1
        return counts
