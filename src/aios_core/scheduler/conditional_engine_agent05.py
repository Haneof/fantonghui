"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。
独立命名并存线（agent-05）：本模块为同工单独立命名交付版本，与共享分支上的规范实现并存，零覆盖；详见批次报告 agent-05-m2m3-sim-batch-20260916。

实战业务情境：长期高压的创业企业法务总监，日程中挂载 200 项跨周期复杂条件任务
（"当诉讼对方实控人出现股权变更时提醒"、"当连续 3 天晚间心率超过 95bpm 时启动
心内科预约建档"、"在回到上海办公室且处于非深度专注状态时提示签署对赌回购协议"）。

四大硬门禁（宪法级承诺）：

1. **未成熟任务 Token 严格为 0**：DORMANT 任务在看板组装与常规会话中绝对物理
   隐形 —— 渲染片段严格为空串，``estimate_tokens`` 严格为 0，严禁把未成熟任务
   灌入 LLM Prompt；
2. **Level-1 机械快轨 0 Token 判定**：纯时间绝对到期、地理围栏、心率阈值等
   客观物理条件由底层调度器纯 Python 在 1ms 内判定，大模型调用次数严格为 0，
   成熟任务直接 DORMANT → READY；
3. **Level-2 机会式捎带（Opportunistic Piggyback）**：依赖语义环境的任务只在
   用户**主动唤醒** AI 且处于相关场景时顺路捎带评估（``piggyback_semantic``
   必须携带 ``wake_ref``，引擎不存在任何自主唤醒/自主评估入口）；
4. **状态机非法跃迁 100% 拦截**：严格捍卫 DORMANT → READY → RUNNING →
   COMPLETED 单向链，任何其它跃迁（含 DORMANT→RUNNING 越级触发执行）直接
   抛出 ``IllegalStateTransitionError``。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from math import asin, cos, radians, sin, sqrt
from typing import Callable, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple, Union

__all__ = [
    "BiometricThresholdCondition",
    "ConditionalTask",
    "ConditionalTaskEngine",
    "ConditionalTaskState",
    "CompositeAndCondition",
    "ContextFlagCondition",
    "GeofenceCondition",
    "IllegalStateTransitionError",
    "PhysicalContext",
    "SemanticSceneCondition",
    "TimeAbsoluteCondition",
    "TokenMeter",
    "build_legal_director_schedule",
]

# ----------------------------------------------------------------------
# 状态机（门禁 4）：严格单向链 DORMANT → READY → RUNNING → COMPLETED
# ----------------------------------------------------------------------


class ConditionalTaskState(StrEnum):
    DORMANT = "dormant"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"


#: 唯一合法的跃迁表（任何其它组合 100% 拦截）
_ALLOWED_TRANSITIONS: Dict[ConditionalTaskState, FrozenSet[ConditionalTaskState]] = {
    ConditionalTaskState.DORMANT: frozenset({ConditionalTaskState.READY}),
    ConditionalTaskState.READY: frozenset({ConditionalTaskState.RUNNING}),
    ConditionalTaskState.RUNNING: frozenset({ConditionalTaskState.COMPLETED}),
    ConditionalTaskState.COMPLETED: frozenset(),
}


class IllegalStateTransitionError(RuntimeError):
    """状态机非法跃迁：从未就绪状态直接触发执行等操作被物理拦截。"""


def _transition(task: "ConditionalTask", target: ConditionalTaskState, reason: str) -> None:
    allowed = _ALLOWED_TRANSITIONS[task.state]
    if target not in allowed:
        raise IllegalStateTransitionError(
            f"illegal state transition {task.state.value} -> {target.value} "
            f"for task {task.task_id!r} (reason={reason!r}); "
            "only DORMANT->READY->RUNNING->COMPLETED is allowed"
        )
    task.state = target
    task.maturity_reason = reason


# ----------------------------------------------------------------------
# 条件模型
# ----------------------------------------------------------------------

Comparator = Callable[[float, float], bool]


def _gt(a: float, b: float) -> bool:
    return a > b


def _lt(a: float, b: float) -> bool:
    return a < b


@dataclass(frozen=True)
class TimeAbsoluteCondition:
    """纯时间绝对到期（Level-1 机械快轨）。"""

    fires_at: datetime


@dataclass(frozen=True)
class GeofenceCondition:
    """地理围栏触发（Level-1 机械快轨）。"""

    zone_id: str
    center_lat: float
    center_lng: float
    radius_m: float


@dataclass(frozen=True)
class ContextFlagCondition:
    """客观上下文标志（Level-1 机械快轨），如"非深度专注状态"。"""

    flag: str
    expected_value: bool


@dataclass(frozen=True)
class BiometricThresholdCondition:
    """生理阈值 + 连续 N 天（Level-1 机械快轨，逐日计数由引擎维护）。"""

    metric: str
    comparator: Comparator
    threshold: float
    required_consecutive_days: int = 1

    @classmethod
    def above(cls, metric: str, threshold: float, required_consecutive_days: int = 1):
        return cls(metric, _gt, threshold, required_consecutive_days)

    @classmethod
    def below(cls, metric: str, threshold: float, required_consecutive_days: int = 1):
        return cls(metric, _lt, threshold, required_consecutive_days)


@dataclass(frozen=True)
class CompositeAndCondition:
    """客观条件合取（Level-1 机械快轨）：全部子条件满足才成熟。"""

    children: Tuple[Union[TimeAbsoluteCondition, GeofenceCondition, ContextFlagCondition, BiometricThresholdCondition], ...]


@dataclass(frozen=True)
class SemanticSceneCondition:
    """语义场景条件（**仅** Level-2 机会式捎带评估，严禁 Level-1 触碰）。"""

    required_scenes: FrozenSet[str]


ObjectiveCondition = Union[
    TimeAbsoluteCondition,
    GeofenceCondition,
    ContextFlagCondition,
    BiometricThresholdCondition,
    CompositeAndCondition,
]
AnyCondition = Union[ObjectiveCondition, SemanticSceneCondition]


# ----------------------------------------------------------------------
# 物理上下文与 Token 计量
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalContext:
    """Level-1 机械快轨的判定输入（客观物理量，无 LLM 参与）。"""

    now: datetime
    location: Optional[Tuple[float, float]] = None  # (lat, lng)
    biometrics: Mapping[str, float] = field(default_factory=dict)
    flags: Mapping[str, bool] = field(default_factory=dict)


@dataclass
class TokenMeter:
    """LLM 调用与 Token 计量器（门禁 1/2 的可审计口径）。"""

    llm_calls: int = 0
    tokens: int = 0

    def record_llm_call(self, tokens: int) -> None:
        self.llm_calls += 1
        self.tokens += tokens


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    rlat1, rlat2, rlng1, rlng2 = map(radians, (lat1, lat2, lng1, lng2))
    h = sin((rlat2 - rlat1) / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin((rlng2 - rlng1) / 2) ** 2
    return 2 * asin(sqrt(h)) * 6_371_000.0


# ----------------------------------------------------------------------
# 任务模型
# ----------------------------------------------------------------------


@dataclass
class ConditionalTask:
    """条件任务：默认 DORMANT（休眠、物理隐形），成熟后跃迁 READY。"""

    task_id: str
    description: str
    condition: AnyCondition
    created_at: datetime
    priority: str = "P2"
    state: ConditionalTaskState = ConditionalTaskState.DORMANT
    ready_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    maturity_reason: Optional[str] = None
    # 内部：BiometricThresholdCondition 的逐日满足记录（day -> satisfied）
    _biometric_history: Dict[date, bool] = field(default_factory=dict, repr=False)

    @property
    def is_dormant(self) -> bool:
        return self.state is ConditionalTaskState.DORMANT


# ----------------------------------------------------------------------
# 双轨调度引擎
# ----------------------------------------------------------------------


class ConditionalTaskEngine:
    """条件驱动任务调度双轨引擎。

    - Level-1 机械快轨：``evaluate_physical`` 纯 Python 判定客观条件，
      0 LLM 调用、0 Token、1ms 内完成；
    - Level-2 机会式捎带：``piggyback_semantic`` 仅在用户主动唤醒
      （``wake_ref`` 非空）时顺路评估语义条件；
    - DORMANT 任务物理隐形：``cockpit_fragment`` 只渲染非休眠任务。
    """

    def __init__(self, *, meter: Optional[TokenMeter] = None) -> None:
        self.meter = meter or TokenMeter()
        self._tasks: Dict[str, ConditionalTask] = {}
        self._biometric_tasks: Dict[str, BiometricThresholdCondition] = {}

    # ---------------- 注册 ----------------

    def register(self, task: ConditionalTask) -> ConditionalTask:
        if task.task_id in self._tasks:
            raise ValueError(f"task {task.task_id!r} already registered")
        if task.state is not ConditionalTaskState.DORMANT:
            raise ValueError("newly registered tasks must start DORMANT")
        if isinstance(task.condition, BiometricThresholdCondition):
            self._biometric_tasks[task.task_id] = task.condition
        self._tasks[task.task_id] = task
        return task

    def register_all(self, tasks: Sequence[ConditionalTask]) -> int:
        for task in tasks:
            self.register(task)
        return len(tasks)

    def get(self, task_id: str) -> ConditionalTask:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise KeyError(f"unknown task_id: {task_id!r}") from None

    @property
    def tasks(self) -> Tuple[ConditionalTask, ...]:
        return tuple(self._tasks.values())

    def by_state(self, state: ConditionalTaskState) -> Tuple[ConditionalTask, ...]:
        return tuple(t for t in self._tasks.values() if t.state is state)

    # ---------------- Level-1 机械快轨（0 Token / 0 LLM / <1ms） ----------------

    def evaluate_physical(self, ctx: PhysicalContext) -> Tuple[ConditionalTask, ...]:
        """纯 Python 客观条件判定。返回本次新成熟（DORMANT→READY）的任务。

        严禁在本路径调用任何大模型：``self.meter`` 保持零增长。
        """
        matured: list[ConditionalTask] = []
        day = ctx.now.date()
        for task in self._tasks.values():
            if task.state is not ConditionalTaskState.DORMANT:
                continue
            condition = task.condition
            if isinstance(condition, SemanticSceneCondition):
                continue  # 语义条件只走 Level-2 捎带，机械快轨绝不触碰
            if self._objective_matured(task, condition, ctx, day):
                _transition(task, ConditionalTaskState.READY, f"level1:{_condition_desc(condition)}")
                task.ready_at = ctx.now
                matured.append(task)
        return tuple(matured)

    def _objective_matured(
        self, task: ConditionalTask, condition: ObjectiveCondition, ctx: PhysicalContext, day: date
    ) -> bool:
        if isinstance(condition, TimeAbsoluteCondition):
            return ctx.now >= condition.fires_at
        if isinstance(condition, GeofenceCondition):
            if ctx.location is None:
                return False
            lat, lng = ctx.location
            return _haversine_m(lat, lng, condition.center_lat, condition.center_lng) <= condition.radius_m
        if isinstance(condition, ContextFlagCondition):
            return ctx.flags.get(condition.flag, False) is condition.expected_value
        if isinstance(condition, BiometricThresholdCondition):
            value = ctx.biometrics.get(condition.metric)
            satisfied = value is not None and condition.comparator(value, condition.threshold)
            # 逐日"或"归并：当日任一样本达标即记为达标（晚间峰值不被夜间回落覆盖）
            task._biometric_history[day] = task._biometric_history.get(day, False) or satisfied
            streak = 0
            probe = day
            while task._biometric_history.get(probe, False):
                streak += 1
                probe = probe - timedelta(days=1)
            return streak >= condition.required_consecutive_days
        if isinstance(condition, CompositeAndCondition):
            return all(
                self._objective_matured(task, child, ctx, day)
                if isinstance(child, BiometricThresholdCondition)
                else self._leaf_matured(child, ctx)
                for child in condition.children
            )
        raise TypeError(f"unsupported objective condition: {condition!r}")

    @staticmethod
    def _leaf_matured(child: Union[TimeAbsoluteCondition, GeofenceCondition, ContextFlagCondition], ctx: PhysicalContext) -> bool:
        if isinstance(child, TimeAbsoluteCondition):
            return ctx.now >= child.fires_at
        if isinstance(child, GeofenceCondition):
            if ctx.location is None:
                return False
            lat, lng = ctx.location
            return _haversine_m(lat, lng, child.center_lat, child.center_lng) <= child.radius_m
        if isinstance(child, ContextFlagCondition):
            return ctx.flags.get(child.flag, False) is child.expected_value
        raise TypeError(f"unsupported leaf condition: {child!r}")

    # ---------------- Level-2 机会式捎带（仅用户主动唤醒时） ----------------

    def piggyback_semantic(
        self, *, wake_ref: str, scene_tags: FrozenSet[str], at: Optional[datetime] = None
    ) -> Tuple[ConditionalTask, ...]:
        """机会式捎带评估：必须携带用户主动唤醒引用（``wake_ref`` 非空）。

        引擎不存在任何自主唤醒入口 —— 未唤醒时语义条件保持 DORMANT 零评估。
        """
        if not isinstance(wake_ref, str) or not wake_ref.strip():
            raise ValueError(
                "piggyback evaluation requires an active user wake_ref "
                "(fail-closed: no autonomous wake of the LLM path)"
            )
        matured: list[ConditionalTask] = []
        for task in self._tasks.values():
            if task.state is not ConditionalTaskState.DORMANT:
                continue
            condition = task.condition
            if not isinstance(condition, SemanticSceneCondition):
                continue
            if condition.required_scenes <= scene_tags:
                _transition(
                    task,
                    ConditionalTaskState.READY,
                    f"level2:piggyback:{wake_ref}:scenes={','.join(sorted(condition.required_scenes))}",
                )
                task.ready_at = at if at is not None else datetime.now(_utcnow_tz())
                matured.append(task)
        return tuple(matured)

    # ---------------- 状态机操作（门禁 4） ----------------

    def start(self, task_id: str, *, at: datetime) -> ConditionalTask:
        task = self.get(task_id)
        _transition(task, ConditionalTaskState.RUNNING, f"start@{at.isoformat()}")
        return task

    def complete(self, task_id: str, *, at: datetime) -> ConditionalTask:
        task = self.get(task_id)
        _transition(task, ConditionalTaskState.COMPLETED, f"complete@{at.isoformat()}")
        task.completed_at = at
        return task

    # ---------------- 门禁 1：DORMANT 物理隐形（Token 严格为 0） ----------------

    def cockpit_fragment(self, tasks: Optional[Sequence[ConditionalTask]] = None) -> str:
        """看板可见片段：只渲染非 DORMANT 任务。DORMANT 任务物理隐形。"""
        pool = list(tasks) if tasks is not None else list(self._tasks.values())
        visible = [t for t in pool if not t.is_dormant]
        if not visible:
            return ""
        lines = [f"[{t.task_id}] {t.description}" for t in visible]
        return "\n".join(lines)

    def dormant_token_footprint(self, tasks: Optional[Sequence[ConditionalTask]] = None) -> int:
        """DORMANT 任务的 Token 足迹：渲染片段为空串 → 严格为 0。"""
        from aios_core.cockpit.pipeline import estimate_tokens

        pool = list(tasks) if tasks is not None else list(self._tasks.values())
        dormant = [t for t in pool if t.is_dormant]
        fragment = self.cockpit_fragment(dormant)
        assert fragment == "", "DORMANT tasks must render to an empty fragment (physical invisibility)"
        return estimate_tokens(fragment)


def _condition_desc(condition: AnyCondition) -> str:
    return type(condition).__name__


def _utcnow_tz():
    from datetime import timezone

    return timezone.utc


# ----------------------------------------------------------------------
# 法务总监 200 项跨周期条件任务场景（严禁低幼化样例）
# ----------------------------------------------------------------------

_SHANGHAI_OFFICE = (31.2304, 121.4737)
_HOMES = {"shanghai": (31.1999, 121.4375), "beijing": (39.9042, 116.4074)}


def build_legal_director_schedule(
    *,
    start: datetime,
    count: int = 200,
    seed: int = 20260916,
) -> Tuple[ConditionalTask, ...]:
    """构建法务总监的 200 项跨周期复杂条件任务（确定性种子）。

    旗舰任务（工单原文三例）：
    - ``task:equity-change:counterparty``：诉讼对方实控人股权变更提醒（Level-2 语义）；
    - ``task:cardiology:hr-3day``：连续 3 天晚间心率 > 95bpm → 心内科预约建档（Level-1）；
    - ``task:buyback-sign:shanghai``：回到上海办公室且非深度专注 → 签署对赌回购协议（Level-1 合取）。
    """
    rng = random.Random(seed)
    tasks: list[ConditionalTask] = [
        ConditionalTask(
            task_id="task:equity-change:counterparty",
            description="当诉讼对方实控人出现股权变更时提醒（工商公示监控）",
            condition=SemanticSceneCondition(frozenset({"external_event:equity_change"})),
            priority="P1",
            created_at=start,
        ),
        ConditionalTask(
            task_id="task:cardiology:hr-3day",
            description="连续 3 天晚间心率超过 95bpm 时启动心内科预约建档",
            condition=BiometricThresholdCondition.above("evening_heart_rate_bpm", 95.0, 3),
            priority="P1",
            created_at=start,
        ),
        ConditionalTask(
            task_id="task:buyback-sign:shanghai",
            description="回到上海办公室且处于非深度专注状态时提示签署对赌回购协议",
            condition=CompositeAndCondition(
                (
                    GeofenceCondition("office_shanghai", *_SHANGHAI_OFFICE, radius_m=300.0),
                    ContextFlagCondition("deep_focus", False),
                )
            ),
            priority="P1",
            created_at=start,
        ),
    ]

    zones = [
        GeofenceCondition("office_shanghai", *_SHANGHAI_OFFICE, radius_m=500.0),
        GeofenceCondition("home_shanghai", *_HOMES["shanghai"], radius_m=800.0),
        GeofenceCondition("court_huangpu", 31.2102, 121.4906, radius_m=600.0),
        GeofenceCondition("home_beijing", *_HOMES["beijing"], radius_m=800.0),
    ]
    kinds = ["time", "geofence", "biometric", "flag", "composite"]
    for i in range(count - len(tasks)):
        kind = kinds[i % len(kinds)]
        offset_days = rng.randint(0, 364)
        fire = start + timedelta(days=offset_days, hours=rng.randint(8, 21))
        if kind == "time":
            condition: AnyCondition = TimeAbsoluteCondition(fire)
            desc = f"跨周期截止：第 {offset_days} 天 {fire:%H:%M} 合同节点复核提醒"
        elif kind == "geofence":
            zone = zones[i % len(zones)]
            condition = zone
            desc = f"到达 {zone.zone_id} 时提示当日待签文件清单"
        elif kind == "biometric":
            if i % 2 == 0:
                condition = BiometricThresholdCondition.above("heart_rate_bpm", 92.0 + (i % 5), 1 + (i % 3))
                desc = f"晚间心率持续 > {92 + (i % 5)}bpm 时提示就医与日程减压"
            else:
                condition = BiometricThresholdCondition.below("hrv_ms", 40.0 + (i % 10), 1 + (i % 2))
                desc = f"HRV 低于 {40 + (i % 10)}ms 持续时提示副交感恢复训练"
        elif kind == "flag":
            condition = ContextFlagCondition("calendar_free", i % 3 == 0)
            desc = "日程空档出现时提示批阅积压对赌协议" if i % 3 == 0 else "深度专注状态退出时提示回复监管问询"
        else:
            zone = zones[i % len(zones)]
            condition = CompositeAndCondition(
                (zone, ContextFlagCondition("deep_focus", False), TimeAbsoluteCondition(fire))
            )
            desc = f"到达 {zone.zone_id}、非深度专注且 {fire:%m-%d %H:%M} 后提示开庭材料装订"
        tasks.append(
            ConditionalTask(
                task_id=f"task:legal:{i:03d}",
                description=desc,
                condition=condition,
                priority="P1" if i % 9 == 0 else "P2",
                created_at=start,
            )
        )
    return tuple(tasks)
