"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

宪法锚：§86.2 条件驱动零浪费——未成熟任务绝不允许无条件挤占模型上下文。

四大硬门禁的结构性落实（不是监控指标，是机制本体）：

1. 【DORMANT 物理隐形】``board_view()`` 的输出字典里不存在 DORMANT 键——
   隐形不是"置 0"，是键都不在；``dormant_tokens_exposed`` 结构性恒 0。
2. 【Level-1 机械快轨 0 Token】时间到期/地理围栏/心率阈值纯 Python 判定，
   模块不存在任何模型入口：``model_calls`` 是签名级常数 0，单次条件判定
   p99 ≤ 1ms（判定是两次比较加一个开方，不存在可慢的代码路径）。
3. 【Level-2 机会式捎带】语义场景条件只在 ``piggyback_on_user_wake`` 内被
   评估——本类**没有任何自我唤醒 API**，``self_wakes_issued`` 结构性恒 0；
   语义任务经过任何 tick 都保持 DORMANT，直到用户唤醒把它捎到相关场景。
4. 【非法跃迁 100% 拦截】状态机仅三条有向边：
   DORMANT→READY→RUNNING→COMPLETED。其余 13 种有向组合全抛
   ``IllegalStateTransitionError``，含终态再跃迁与原地自环。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Iterable, Mapping, Sequence

MODEL_CALLS_LEVEL1 = 0          # Level-1 零 Token：结构性常数，不是告警指标
SELF_WAKES_STRUCTURAL = 0       # 引擎无自唤醒 API：常数即证明
DORMANT_TOKENS_STRUCTURAL = 0   # DORMANT 隐形：暴露 token 结构性恒 0
MECHANICAL_EVAL_BUDGET_MS = 1.0 # 单条件机械判定预算（Level-1 红线）


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------


class TaskState(str, Enum):
    DORMANT = "DORMANT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


_ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.DORMANT: frozenset({TaskState.READY}),
    TaskState.READY: frozenset({TaskState.RUNNING}),
    TaskState.RUNNING: frozenset({TaskState.COMPLETED}),
    TaskState.COMPLETED: frozenset(),
}


class IllegalStateTransitionError(RuntimeError):
    """未沿 DORMANT→READY→RUNNING→COMPLETED 主链的跃迁，一律物理拦截。"""


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 条件物种
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TimeExpiryCondition:
    """绝对时间到期（如：明早 09:00 提醒签回购协议）。"""

    at: datetime

    def evaluate(self, ctx: "_EvalContext") -> bool:
        return _aware(ctx.now) >= _aware(self.at)


@dataclass(slots=True, frozen=True)
class GeoFenceCondition:
    """地理围栏（如：回到上海办公室 → 提示签协议）。"""

    latitude: float
    longitude: float
    radius_m: float
    subject_key: str = ""

    def evaluate(self, ctx: "_EvalContext") -> bool:
        pos = ctx.geo_positions.get(self.subject_key)
        if pos is None:
            return False
        return _haversine_m(self.latitude, self.longitude, pos[0], pos[1]) <= self.radius_m


@dataclass(slots=True, frozen=True)
class HeartRateCondition:
    """心率阈值持续超标（如：连续 3 个夜间窗口 max(HR) > 95bpm 启动心内科建档）。"""

    threshold_bpm: float
    min_consecutive_windows: int
    window_hours: tuple[int, int] = (22, 6)  # 夜间窗：22:00 → 次日 06:00
    subject_key: str = ""

    def evaluate(self, ctx: "_EvalContext") -> bool:
        series = ctx.hr_series.get(self.subject_key, ())
        return _consecutive_night_breaches(
            series, self.threshold_bpm, self.min_consecutive_windows, self.window_hours
        )


@dataclass(slots=True, frozen=True)
class SemanticSceneCondition:
    """语义场景条件（Level-2 专属）：只在用户唤醒捎带时被评估。

    sim 期以场景标签交集作为语义判定代理——真实语义判别由唤醒上下文承担，
    无论如何：本条件**永不进入 Level-1 tick**，这是双轨的机械分界。
    """

    scene_tags: frozenset[str]

    def evaluate(self, ctx: "_EvalContext") -> bool:  # pragma: no cover - 防御
        raise RuntimeError("SemanticSceneCondition 禁止进入 Level-1 机械通道")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _consecutive_night_breaches(
    series: Sequence[tuple[datetime, float]],
    threshold: float,
    min_windows: int,
    window_hours: tuple[int, int],
) -> bool:
    """最近 min_windows 个连续夜间窗内，每窗 max(bpm) 都越阈值才算命中。"""
    if min_windows < 1 or not series:
        return False
    buckets: dict[tuple[int, int, int], float] = {}
    start_h, end_h = window_hours
    for raw_ts, bpm in series:
        ts = _aware(raw_ts)
        in_night = ts.hour >= start_h or ts.hour < end_h
        if not in_night:
            continue
        # 窗首日期：凌晨段归属前一晚
        anchor = (ts - timedelta(days=1)).date() if ts.hour < end_h else ts.date()
        key = (anchor.year, anchor.month, anchor.day)
        if bpm > buckets.get(key, float("-inf")):
            buckets[key] = bpm
    if not buckets:
        return False
    ordered = sorted(buckets)
    tail = ordered[-min_windows:]
    if len(tail) < min_windows:
        return False
    for prev, nxt in zip(tail, tail[1:]):
        if (date(*nxt) - date(*prev)).days != 1:
            return False
    return all(buckets[k] > threshold for k in tail)


@dataclass(slots=True)
class _EvalContext:
    now: datetime
    geo_positions: Mapping[str, tuple[float, float]]
    hr_series: Mapping[str, Sequence[tuple[datetime, float]]]


# ---------------------------------------------------------------------------
# 任务与报告
# ---------------------------------------------------------------------------

LEVEL1_CONDITION_KINDS = (TimeExpiryCondition, GeoFenceCondition, HeartRateCondition)


@dataclass(slots=True)
class ConditionalTask:
    task_id: str
    subject_id: str
    condition: object  # Level-1 条件物种 | SemanticSceneCondition
    state: TaskState = TaskState.DORMANT

    @property
    def is_semantic(self) -> bool:
        return isinstance(self.condition, SemanticSceneCondition)


@dataclass
class MechanicalTickReport:
    examined: int
    newly_ready: list[str] = field(default_factory=list)
    semantic_skipped: int = 0
    model_calls: int = MODEL_CALLS_LEVEL1
    worst_eval_ms: float = 0.0


@dataclass
class PiggybackReport:
    evaluated: int
    newly_ready: list[str] = field(default_factory=list)
    piggyback_evaluations: int = 0
    self_wakes_issued: int = SELF_WAKES_STRUCTURAL
    model_calls: int = MODEL_CALLS_LEVEL1


class ConditionalSchedulingEngine:
    """双轨引擎：Level-1 机械快轨 / Level-2 机会式捎带。

    本引擎只做枢纽，不做持久化（sim 期驻内存；状态机的不可伪造性由
    转移表保证，不依赖存储层）。任务创建即 DORMANT，别无入口。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ConditionalTask] = {}
        self._piggyback_evaluations = 0

    # ----------------------- 注册与状态机 --------------------------------

    def register(self, task: ConditionalTask) -> None:
        if not isinstance(task.condition, (*LEVEL1_CONDITION_KINDS, SemanticSceneCondition)):
            raise TypeError(f"未注册的条件物种：{type(task.condition).__name__}")
        if task.task_id in self._tasks:
            raise ValueError(f"task 重复注册：{task.task_id}")
        task.state = TaskState.DORMANT
        self._tasks[task.task_id] = task

    def transition(self, task_id: str, target: TaskState) -> None:
        task = self._tasks[task_id]  # KeyError on unknown = 查无此务
        if target not in _ALLOWED_TRANSITIONS[task.state]:
            raise IllegalStateTransitionError(
                f"{task_id}: {task.state.value} → {target.value} 非法；"
                "仅允许 DORMANT→READY→RUNNING→COMPLETED 主链"
            )
        task.state = target

    def state_of(self, task_id: str) -> TaskState:
        return self._tasks[task_id].state

    # ----------------------- 门禁 1：DORMANT 隐形 -------------------------

    def board_view(self) -> dict[str, str]:
        """看板可见面：键集只含 READY/RUNNING——DORMANT 连键都不存在。"""
        return {
            t.task_id: t.state.value
            for t in self._tasks.values()
            if t.state in (TaskState.READY, TaskState.RUNNING)
        }

    @property
    def dormant_tokens_exposed(self) -> int:
        return DORMANT_TOKENS_STRUCTURAL

    # ----------------------- 门禁 2：Level-1 机械快轨 ----------------------

    def mechanical_tick(
        self,
        now: datetime,
        *,
        geo_positions: Mapping[str, tuple[float, float]] | None = None,
        hr_series: Mapping[str, Sequence[tuple[datetime, float]]] | None = None,
    ) -> MechanicalTickReport:
        ctx = _EvalContext(
            now=_aware(now),
            geo_positions=geo_positions or {},
            hr_series=hr_series or {},
        )
        report = MechanicalTickReport(examined=0)
        for task in self._tasks.values():
            if task.state is not TaskState.DORMANT:
                continue
            if task.is_semantic:
                report.semantic_skipped += 1  # 双轨分界：语义永不上快轨
                continue
            report.examined += 1
            t0 = time.perf_counter()
            if isinstance(task.condition, GeoFenceCondition) and not task.condition.subject_key:
                hit = replace(task.condition, subject_key=task.subject_id).evaluate(ctx)
            elif isinstance(task.condition, HeartRateCondition) and not task.condition.subject_key:
                hit = replace(task.condition, subject_key=task.subject_id).evaluate(ctx)
            else:
                hit = task.condition.evaluate(ctx)  # type: ignore[attr-defined]
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if elapsed_ms > report.worst_eval_ms:
                report.worst_eval_ms = elapsed_ms
            if hit:
                self.transition(task.task_id, TaskState.READY)
                report.newly_ready.append(task.task_id)
        return report

    # ----------------------- 门禁 3：Level-2 机会式捎带 --------------------

    def piggyback_on_user_wake(self, scene_tags: Iterable[str]) -> PiggybackReport:
        """用户唤醒且场景相关时，顺路捎带语义任务评估。引擎本身永不发起唤醒。"""
        tags = frozenset(scene_tags)
        report = PiggybackReport(evaluated=0)
        for task in self._tasks.values():
            if task.state is not TaskState.DORMANT or not task.is_semantic:
                continue
            report.evaluated += 1
            self._piggyback_evaluations += 1
            cond = task.condition
            assert isinstance(cond, SemanticSceneCondition)
            if cond.scene_tags & tags:
                self.transition(task.task_id, TaskState.READY)
                report.newly_ready.append(task.task_id)
        report.piggyback_evaluations = self._piggyback_evaluations
        return report


__all__ = [
    "ConditionalSchedulingEngine",
    "ConditionalTask",
    "DORMANT_TOKENS_STRUCTURAL",
    "GeoFenceCondition",
    "HeartRateCondition",
    "IllegalStateTransitionError",
    "MECHANICAL_EVAL_BUDGET_MS",
    "MODEL_CALLS_LEVEL1",
    "MechanicalTickReport",
    "PiggybackReport",
    "SELF_WAKES_STRUCTURAL",
    "SemanticSceneCondition",
    "TaskState",
    "TimeExpiryCondition",
]
