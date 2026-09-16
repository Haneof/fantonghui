"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

实战情境：长期高压的创业企业法务总监，日程挂载 200 项跨周期复杂条件任务
（诉讼对方实控人股权变更、连续 3 天晚间心率超标启动心内科预约建档、回到
上海办公室且非深度专注时提示签署对赌回购协议……）。

四大硬门禁的工程落点：

1. **未成熟任务 Token 严格为 0**：``DORMANT``（休眠）状态任务在看板组装
   （``assemble_board``）中**绝对不参与任何序列化**——其标题、详情、条件文本
   一律不进入 Prompt 字符串，Token 计入严格为 0（结构式隐形，而非"写了再删"）；
2. **Level-1 机械快轨 0 Token 判定**：纯时间绝对到期、地理围栏进入、心率
   阈值超标等客观物理条件，由 ``tick`` 以纯 Python 算术判定（单次评估
   < 1ms），路径上**结构性不存在 LLM 句柄**（引擎的语义评估器只在
   ``piggyback_on_user_wake`` 中被触碰），命中即 DORMANT → READY；
3. **Level-2 机会式捎带**：语义环境任务只在用户**主动唤醒** AI 且任务要求
   的场景标签被唤醒场景完整覆盖（``requirement.scene_tags ⊆ wake.scene_tags``）
   时才顺路评估；调度器绝不为了评估休眠任务而自行唤醒大模型——
   除用户唤醒回调外没有任何代码路径调用语义评估器；
4. **非法跃迁 100% 拦截**：状态机法定边集
   ``DORMANT → READY → RUNNING → COMPLETED``，任何越级/回退/跳步（含从未
   就绪状态直接触发执行）一律抛出 ``IllegalStateTransitionError``。

本模块为零依赖纯引擎（仅复用 C04 的 ``estimate_tokens`` 做审计计量），
时钟与传感器快照由调用方注入，测试可完全确定性地推进 200 项任务全周期。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from aios_core.cockpit.pipeline import estimate_tokens

__all__ = [
    "ConditionalTaskState",
    "MechanicalConditionKind",
    "MechanicalCondition",
    "SemanticRequirement",
    "ConditionalTask",
    "SensorSnapshot",
    "UserWakeEvent",
    "BoardAssembly",
    "IllegalStateTransitionError",
    "DualTrackScheduler",
]


class IllegalStateTransitionError(Exception):
    """非法状态跃迁：任何脱离法定边集的任务流转均被物理拦截。"""


class ConditionalTaskState(StrEnum):
    """工单法定状态机：DORMANT → READY → RUNNING → COMPLETED。"""

    DORMANT = "dormant"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"


#: 法定跃迁边集（单一事实来源）。
_ALLOWED_TRANSITIONS: Dict[ConditionalTaskState, frozenset] = {
    ConditionalTaskState.DORMANT: frozenset({ConditionalTaskState.READY}),
    ConditionalTaskState.READY: frozenset({ConditionalTaskState.RUNNING}),
    ConditionalTaskState.RUNNING: frozenset({ConditionalTaskState.COMPLETED}),
    ConditionalTaskState.COMPLETED: frozenset(),
}


class MechanicalConditionKind(StrEnum):
    """Level-1 客观物理条件：纯 Python 可判，零语义歧义。"""

    TIME_ABSOLUTE = "time_absolute"  # 纯时间绝对到期
    GEO_FENCE_ENTER = "geo_fence_enter"  # 地理围栏进入
    HEART_RATE_THRESHOLD = "heart_rate_threshold"  # 心率阈值超标
    METRIC_THRESHOLD = "metric_threshold"  # 通用物理指标阈值


@dataclass(frozen=True)
class MechanicalCondition:
    """一条 Level-1 机械条件（全部字段均可被算术判定）。"""

    kind: MechanicalConditionKind
    due_at: Optional[datetime] = None  # TIME_ABSOLUTE：绝对到期时刻
    center_lat: Optional[float] = None  # GEO_FENCE_ENTER：围栏圆心
    center_lon: Optional[float] = None
    radius_m: Optional[float] = None
    metric: Optional[str] = None  # HEART_RATE_THRESHOLD / METRIC_THRESHOLD
    threshold: Optional[float] = None
    comparator: str = ">="  # >= / <= / > / <


@dataclass(frozen=True)
class SemanticRequirement:
    """一条 Level-2 语义环境条件：只能借用户唤醒机会顺路评估。"""

    scene_tags: Tuple[str, ...]  # 唤醒事件场景与该集合有交集才评估
    prompt_template: str  # 捎带时的评估提示模板（不外泄到看板）


@dataclass(frozen=True)
class ConditionalTask:
    """一项跨周期条件任务（DORMANT 出厂，READY 前对世界隐形）。"""

    task_id: str
    title: str
    detail: str
    mechanical: Optional[MechanicalCondition] = None
    semantic: Optional[SemanticRequirement] = None
    priority: int = 50
    created_by: str = "legal-ops"

    def __post_init__(self) -> None:
        if (self.mechanical is None) == (self.semantic is None):
            raise ValueError("task must carry exactly one kind of condition (mechanical XOR semantic)")


@dataclass(frozen=True)
class SensorSnapshot:
    """底层调度器一次 tick 的客观物理快照。"""

    lat: Optional[float] = None
    lon: Optional[float] = None
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class UserWakeEvent:
    """用户主动唤醒 AI 的事件（Level-2 捎带评估的唯一入口）。"""

    occurred_at: datetime
    scene_tags: Tuple[str, ...]
    text: str = ""


@dataclass(frozen=True)
class BoardAssembly:
    """一次看板组装的不可变审计快照。

    不变量：``dormant_token_charge`` 恒为 0——DORMANT 任务的任何文本在
    ``prompt_text`` 中结构性缺席（零写入，而非写入后清除）。
    """

    prompt_text: str
    included_task_ids: Tuple[str, ...]
    hidden_dormant_count: int
    estimated_prompt_tokens: int
    dormant_token_charge: int  # 恒 0 的显性审计位


_EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点球面距离（米），纯算术满足 <1ms 硬预算。"""
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * asin(sqrt(a))


def _compare(value: float, comparator: str, threshold: float) -> bool:
    if comparator == ">=":
        return value >= threshold
    if comparator == ">":
        return value > threshold
    if comparator == "<=":
        return value <= threshold
    if comparator == "<":
        return value < threshold
    raise ValueError(f"unknown comparator: {comparator!r}")


@dataclass
class _TaskRecord:
    task: ConditionalTask
    state: ConditionalTaskState = ConditionalTaskState.DORMANT
    state_changed_at: Optional[datetime] = None


class DualTrackScheduler:
    """条件任务双轨调度引擎（Level-1 机械快轨 + Level-2 捎带慢轨）。

    结构性承诺：
    - ``tick`` 的调用栈上不存在任何语义评估器引用；
    - ``_semantic_evaluator`` 只被 ``piggyback_on_user_wake`` 触碰；
    - 看板组装只迭代 READY/RUNNING 记录，DORMANT 记录不被读取文本。
    """

    def __init__(
        self,
        *,
        semantic_evaluator: Optional[Callable[[ConditionalTask, UserWakeEvent], bool]] = None,
        token_estimator: Callable[[str], int] = estimate_tokens,
    ) -> None:
        self._semantic_evaluator = semantic_evaluator
        self._token_estimator = token_estimator
        self._records: Dict[str, _TaskRecord] = {}
        self._stats: Dict[str, int] = {
            "registered": 0,
            "mechanical_evals": 0,
            "mechanical_hits": 0,
            "piggyback_evals": 0,
            "llm_calls": 0,  # 语义评估器被调用次数（只允许在捎带路径增长）
            "board_assemblies": 0,
            "dormant_token_charge_total": 0,  # 铁律审计：必须恒 0
            "illegal_transition_blocked": 0,
        }
        self._last_tick_wall_ms: float = 0.0

    # ------------------------------------------------------------------
    # 注册与状态机
    # ------------------------------------------------------------------

    def register_task(self, task: ConditionalTask) -> None:
        if task.task_id in self._records:
            raise ValueError(f"task already registered: {task.task_id}")
        if not task.task_id.strip() or not task.title.strip():
            raise ValueError("task_id/title must be non-empty")
        self._records[task.task_id] = _TaskRecord(task=task)
        self._stats["registered"] += 1

    def state_of(self, task_id: str) -> ConditionalTaskState:
        return self._records[task_id].state

    def _transition(
        self, task_id: str, target: ConditionalTaskState, *, at: Optional[datetime] = None
    ) -> None:
        record = self._records[task_id]
        if target not in _ALLOWED_TRANSITIONS[record.state]:
            self._stats["illegal_transition_blocked"] += 1
            raise IllegalStateTransitionError(
                f"illegal transition blocked: {record.state.value} -> {target.value} "
                f"(task={task_id!r}, 法定边集 DORMANT→READY→RUNNING→COMPLETED)"
            )
        record.state = target
        record.state_changed_at = at

    # ------------------------------------------------------------------
    # Level-1 机械快轨：纯 Python 判定，零 Token，零 LLM
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_mechanical(
        condition: MechanicalCondition, now: datetime, snapshot: SensorSnapshot
    ) -> bool:
        kind = condition.kind
        if kind is MechanicalConditionKind.TIME_ABSOLUTE:
            if condition.due_at is None:
                raise ValueError("TIME_ABSOLUTE requires due_at")
            return now >= condition.due_at
        if kind is MechanicalConditionKind.GEO_FENCE_ENTER:
            if None in (condition.center_lat, condition.center_lon, condition.radius_m):
                raise ValueError("GEO_FENCE_ENTER requires center_lat/center_lon/radius_m")
            if snapshot.lat is None or snapshot.lon is None:
                return False  # 无定位即未触发（fail-closed）
            return (
                _haversine_m(snapshot.lat, snapshot.lon, condition.center_lat, condition.center_lon)
                <= condition.radius_m
            )
        if kind in (
            MechanicalConditionKind.HEART_RATE_THRESHOLD,
            MechanicalConditionKind.METRIC_THRESHOLD,
        ):
            if condition.metric is None or condition.threshold is None:
                raise ValueError("threshold condition requires metric/threshold")
            value = snapshot.metrics.get(condition.metric)
            if value is None:
                return False
            return _compare(value, condition.comparator, condition.threshold)
        raise ValueError(f"unknown mechanical kind: {kind!r}")

    def tick(self, now: datetime, snapshot: Optional[SensorSnapshot] = None) -> List[str]:
        """一次机械快轨巡检：只评估 DORMANT 且携带机械条件的任务。

        纯 Python 算术路径：无 I/O、无网络、无大模型——``llm_calls`` 在该
        路径上结构性不可变。返回本轮新跃迁 READY 的任务 id（稳定排序）。
        """
        snapshot = snapshot or SensorSnapshot()
        fired: List[str] = []
        for record in self._records.values():
            if record.state is not ConditionalTaskState.DORMANT:
                continue
            if record.task.mechanical is None:
                continue  # 语义任务在快轨上结构性不可见
            self._stats["mechanical_evals"] += 1
            if self._evaluate_mechanical(record.task.mechanical, now, snapshot):
                self._transition(record.task.task_id, ConditionalTaskState.READY, at=now)
                fired.append(record.task.task_id)
                self._stats["mechanical_hits"] += 1
        return sorted(fired)

    # ------------------------------------------------------------------
    # Level-2 机会式捎带：只在用户主动唤醒时顺路评估
    # ------------------------------------------------------------------

    def piggyback_on_user_wake(self, wake: UserWakeEvent) -> List[str]:
        """用户唤醒捎带评估：要求场景被完整覆盖的语义 DORMANT 任务才动用评估器。

        唤醒场景未完整覆盖任务要求场景的任务**不消耗任何语义评估调用**（0 LLM），
        引擎自身绝不为了评估而发起唤醒——本方法是评估器的唯一入口。
        """
        wake_tags = frozenset(wake.scene_tags)
        fired: List[str] = []
        for record in self._records.values():
            if record.state is not ConditionalTaskState.DORMANT:
                continue
            requirement = record.task.semantic
            if requirement is None:
                continue
            if not frozenset(requirement.scene_tags).issubset(wake_tags):
                continue  # 唤醒场景未完整覆盖任务要求场景：连评估器都不调用（0 LLM）
            self._stats["piggyback_evals"] += 1
            if self._semantic_evaluator is None:
                continue  # 未配置评估器时 fail-closed：保持休眠，不臆断
            self._stats["llm_calls"] += 1
            if self._semantic_evaluator(record.task, wake):
                self._transition(record.task.task_id, ConditionalTaskState.READY, at=wake.occurred_at)
                fired.append(record.task.task_id)
        return sorted(fired)

    # ------------------------------------------------------------------
    # 看板组装：DORMANT 绝对物理隐形，Token 严格 0
    # ------------------------------------------------------------------

    def assemble_board(self, now: datetime, *, max_items: int = 32) -> BoardAssembly:
        """装配会话/看板 Prompt：仅 READY/RUNNING 任务可见。

        DORMANT 记录的 ``title/detail`` 在循环体内根本不被读取——其文本
        物理上不可能出现在 ``prompt_text`` 中，Token 应计恒为 0。
        """
        visible = [
            record
            for record in self._records.values()
            if record.state in (ConditionalTaskState.READY, ConditionalTaskState.RUNNING)
        ]
        visible.sort(key=lambda r: (-r.task.priority, r.task.task_id))
        visible = visible[:max_items]

        hidden_dormant = sum(
            1 for record in self._records.values() if record.state is ConditionalTaskState.DORMANT
        )
        lines = [f"[ready-board {now.isoformat()}]"]
        for record in visible:
            state_tag = "▶" if record.state is ConditionalTaskState.RUNNING else "◆"
            lines.append(f"{state_tag} ({record.task.priority:>3}) {record.task.title}")
        prompt_text = "\n".join(lines)

        self._stats["board_assemblies"] += 1
        estimated = self._token_estimator(prompt_text)
        return BoardAssembly(
            prompt_text=prompt_text,
            included_task_ids=tuple(record.task.task_id for record in visible),
            hidden_dormant_count=hidden_dormant,
            estimated_prompt_tokens=estimated,
            dormant_token_charge=0,
        )

    # ------------------------------------------------------------------
    # 受保护的动作入口（非法跃迁 100% 抛出）
    # ------------------------------------------------------------------

    def execute(self, task_id: str, *, at: Optional[datetime] = None) -> None:
        """触发执行：仅 READY → RUNNING 合法；其余一律 IllegalStateTransitionError。"""
        self._transition(task_id, ConditionalTaskState.RUNNING, at=at)

    def complete(self, task_id: str, *, at: Optional[datetime] = None) -> None:
        """收官执行：仅 RUNNING → COMPLETED 合法。"""
        self._transition(task_id, ConditionalTaskState.COMPLETED, at=at)

    def force_state(
        self, task_id: str, target: ConditionalTaskState, *, at: Optional[datetime] = None
    ) -> None:
        """测试/管理面强制跃迁入口：同样只接受法定边集，越权即抛。"""
        self._transition(task_id, target, at=at)

    # ------------------------------------------------------------------
    # 只读审计
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def tasks_in(self, state: ConditionalTaskState) -> Tuple[str, ...]:
        return tuple(sorted(tid for tid, r in self._records.items() if r.state is state))

    def measure_mechanical_eval_ms(self, samples: int = 1) -> float:
        """自检：单次机械评估墙钟均值（毫秒），供 <1ms 硬预算断言。"""
        dormant_mech = [
            r.task.mechanical
            for r in self._records.values()
            if r.task.mechanical is not None
        ]
        if not dormant_mech:
            return 0.0
        now = datetime.now(timezone.utc)
        snapshot = SensorSnapshot(
            lat=31.2304, lon=121.4737, metrics={"heart_rate": 96.0, "bp_sys": 138.0}
        )
        started = time.perf_counter()
        for _ in range(max(1, samples)):
            for condition in dormant_mech:
                self._evaluate_mechanical(condition, now, snapshot)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return elapsed_ms / (max(1, samples) * len(dormant_mech))
