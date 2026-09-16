"""M2-005R：条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

对应《AIOS 核心系统宪法 v3.0》第八十六条：待办任务**严禁**在每次 AI 醒来时
无条件跑一遍；未就绪任务必须在后台静默休眠，**严禁挤占模型上下文**。

业务情境：法务总监挂载 200 项跨周期复杂条件任务（股权变更提醒、连续 3 天
夜间心率超阈启动建档、回到上海办公室且非深度专注时提示签署回购协议）。
若每次唤醒都把 200 项灌进 Prompt，仅任务区块就是 5k~8k token/次。

双轨设计
--------
**Level-1 机械快轨**：纯时间到期、地理围栏、心率阈值等客观物理条件，
由调度器用纯 Python 在亚毫秒内判定，**大模型调用次数恒为 0**，
命中即自动跃迁 DORMANT → READY。

**Level-2 机会式捎带**：依赖语义环境的条件（"非深度专注状态"、
"对方实控人出现股权变更"这类需要理解的判断）**不自行唤醒模型**，
只在用户已经主动唤醒 AI、且当前场景相关时顺路评估。
绝不为评估一个休眠任务而自主唤醒大模型。

与 M0 冻结契约的关系
--------------------
``contracts/enums.py`` 的 ``TaskState`` 是 M0 冻结枚举，**没有 DORMANT 值**
（它用 ``WAITING_TIME`` / ``WAITING_EVIDENCE`` 表达"未就绪"）。
本模块**不修改冻结枚举**，而是定义调度器本地状态 ``ConditionalTaskState``，
并提供到冻结 ``TaskState`` 的双向映射（见 :func:`to_frozen_task_state`）。
DORMANT 是调度器的运行时视图，不是新的世界对象状态。

同理 ``ErrorCode`` 也是冻结的，没有 ``ILLEGAL_STATE_TRANSITION``；
:meth:`IllegalStateTransitionError` 复用 ``INVALID_ARGUMENT`` 并在
``context`` 里携带机器可读的 from/to，不改冻结枚举。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ErrorCode, TaskState
from aios_core.contracts.time import as_utc, require_aware
from aios_core.errors import AIOSProtocolError

__all__ = [
    "ConditionalTaskRecord",
    "ConditionalTaskState",
    "EvaluationContext",
    "EvaluationLevel",
    "EvaluationOutcome",
    "GeofenceCondition",
    "HeartRateCondition",
    "IllegalStateTransitionError",
    "PiggybackEvaluationReport",
    "SemanticCondition",
    "TimeReachedCondition",
    "TriggerCondition",
    "TwoTrackConditionalScheduler",
]


class ConditionalTaskState(StrEnum):
    """调度器本地状态机。刻意不含 WAITING_* 细分——那是冻结 TaskState 的职责。"""

    DORMANT = "dormant"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[ConditionalTaskState, frozenset[ConditionalTaskState]] = {
    ConditionalTaskState.DORMANT: frozenset(
        {
            ConditionalTaskState.READY,
            ConditionalTaskState.EXPIRED,
            ConditionalTaskState.CANCELLED,
        }
    ),
    ConditionalTaskState.READY: frozenset(
        {
            ConditionalTaskState.RUNNING,
            ConditionalTaskState.DORMANT,  # 条件再次不成立可退回休眠
            ConditionalTaskState.EXPIRED,
            ConditionalTaskState.CANCELLED,
        }
    ),
    ConditionalTaskState.RUNNING: frozenset(
        {
            ConditionalTaskState.COMPLETED,
            ConditionalTaskState.DORMANT,  # 周期任务完成后回到休眠等待下一轮
            ConditionalTaskState.EXPIRED,
            ConditionalTaskState.CANCELLED,
        }
    ),
    ConditionalTaskState.COMPLETED: frozenset(),
    ConditionalTaskState.EXPIRED: frozenset(),
    ConditionalTaskState.CANCELLED: frozenset(),
}

# 到 M0 冻结 TaskState 的映射：DORMANT 落在 WAITING_* 上，不新增枚举值。
_TO_FROZEN: dict[ConditionalTaskState, TaskState] = {
    ConditionalTaskState.DORMANT: TaskState.WAITING_TIME,
    ConditionalTaskState.READY: TaskState.READY,
    ConditionalTaskState.RUNNING: TaskState.RUNNING,
    ConditionalTaskState.COMPLETED: TaskState.COMPLETED,
    ConditionalTaskState.EXPIRED: TaskState.EXPIRED,
    ConditionalTaskState.CANCELLED: TaskState.CANCELLED,
}


def to_frozen_task_state(state: ConditionalTaskState) -> TaskState:
    """把调度器本地状态投影到 M0 冻结 ``TaskState``（持久化时用）。"""
    return _TO_FROZEN[state]


class IllegalStateTransitionError(AIOSProtocolError):
    """任何跳过就绪判定的执行尝试都必须被拦截（门禁 4）。"""

    def __init__(
        self,
        task_id: str,
        current: ConditionalTaskState,
        attempted: ConditionalTaskState,
    ) -> None:
        super().__init__(
            ErrorCode.INVALID_ARGUMENT,
            f"illegal task state transition for {task_id}: "
            f"{current.value} -> {attempted.value}",
            context={
                "task_id": task_id,
                "from_state": current.value,
                "to_state": attempted.value,
                "allowed": sorted(s.value for s in _ALLOWED_TRANSITIONS[current]),
            },
        )


class EvaluationLevel(StrEnum):
    LEVEL1_MECHANICAL = "level1_mechanical"
    LEVEL2_PIGGYBACK = "level2_piggyback"


# ---------------------------------------------------------------------------
# 条件模型
# ---------------------------------------------------------------------------


class TimeReachedCondition(BaseModel):
    """绝对时间到期。Level-1 机械可判。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = "time_reached"
    due_at: datetime

    @model_validator(mode="after")
    def due_at_must_be_aware(self) -> TimeReachedCondition:
        require_aware(self.due_at, "due_at")
        return self

    @property
    def level(self) -> EvaluationLevel:
        return EvaluationLevel.LEVEL1_MECHANICAL


class GeofenceCondition(BaseModel):
    """地理围栏。Level-1 机械可判（坐标 + 半径的纯算术）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = "geofence"
    fence_id: str = Field(min_length=1)
    center_lat: float = Field(ge=-90.0, le=90.0)
    center_lon: float = Field(ge=-180.0, le=180.0)
    radius_m: float = Field(gt=0.0)
    require_dwell_seconds: int = Field(default=0, ge=0)

    @property
    def level(self) -> EvaluationLevel:
        return EvaluationLevel.LEVEL1_MECHANICAL


class HeartRateCondition(BaseModel):
    """心率阈值超标 + 连续天数。Level-1 机械可判。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = "heart_rate"
    threshold_bpm: int = Field(gt=0)
    window: str = Field(default="night", pattern="^(night|day|any)$")
    consecutive_days_required: int = Field(default=1, ge=1)

    @property
    def level(self) -> EvaluationLevel:
        return EvaluationLevel.LEVEL1_MECHANICAL


class SemanticCondition(BaseModel):
    """需要语义理解的条件。**只能**走 Level-2 机会式捎带。

    这类条件（"非深度专注状态"、"对方实控人出现股权变更"）无法机械判定。
    宪法的约束是：不得为了评估它而自主唤醒大模型。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = "semantic"
    predicate: str = Field(min_length=1)
    relevance_keywords: tuple[str, ...] = Field(default_factory=tuple)
    estimated_llm_tokens: int = Field(default=0, ge=0)

    @property
    def level(self) -> EvaluationLevel:
        return EvaluationLevel.LEVEL2_PIGGYBACK


TriggerCondition = (
    TimeReachedCondition | GeofenceCondition | HeartRateCondition | SemanticCondition
)


class EvaluationContext(BaseModel):
    """一次判定的现场快照。Level-1 只用其中的客观字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    now: datetime
    lat: float | None = None
    lon: float | None = None
    dwelled_seconds: int = Field(default=0, ge=0)
    heart_rate_bpm: int | None = None
    heart_rate_window: str = Field(default="any", pattern="^(night|day|any)$")
    consecutive_night_breach_days: int = Field(default=0, ge=0)
    # Level-2 才有意义：用户本次主动唤醒时带来的场景语义
    active_scene_keywords: tuple[str, ...] = Field(default_factory=tuple)
    user_initiated: bool = False

    @model_validator(mode="after")
    def now_must_be_aware(self) -> EvaluationContext:
        require_aware(self.now, "now")
        return self


class EvaluationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_kind: str
    satisfied: bool
    level: EvaluationLevel
    # 门禁 2 的核心：Level-1 判定的大模型调用数必须为 0
    llm_calls: int = Field(default=0, ge=0)
    reason: str = ""


# ---------------------------------------------------------------------------
# 任务记录
# ---------------------------------------------------------------------------


class ConditionalTaskRecord(BaseModel):
    """一项条件任务。DORMANT 是默认态——未就绪即隐形。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    conditions: tuple[TriggerCondition, ...] = Field(min_length=1)
    combine: str = Field(default="and", pattern="^(and|or)$")
    # 看板渲染成本：DORMANT 任务永不被渲染，因此这个成本永不发生
    manifest_tokens_if_ready: int = Field(default=120, ge=0)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def expires_must_be_aware(self) -> ConditionalTaskRecord:
        require_aware(self.expires_at, "expires_at")
        return self

    @property
    def required_level(self) -> EvaluationLevel:
        """只要含一个语义条件，整条任务就必须走 Level-2。"""
        if any(
            c.level == EvaluationLevel.LEVEL2_PIGGYBACK for c in self.conditions
        ):
            return EvaluationLevel.LEVEL2_PIGGYBACK
        return EvaluationLevel.LEVEL1_MECHANICAL


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------


class PiggybackEvaluationReport(BaseModel):
    """Level-2 捎带评估的结果与开销账。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluated_task_ids: tuple[str, ...] = ()
    skipped_task_ids: tuple[str, ...] = ()
    llm_calls: int = Field(default=0, ge=0)
    llm_tokens: int = Field(default=0, ge=0)
    # 关键账目：为评估休眠任务而**自主**唤醒模型的次数，必须恒为 0
    autonomous_wakes_for_evaluation: int = Field(default=0, ge=0)


class TwoTrackConditionalScheduler:
    """双轨条件调度器。

    不变量（对应工单四大硬门禁）：
    1. DORMANT 任务在 :meth:`assemble_ready_manifest` 中**物理不出现**，
       其 token 贡献严格为 0——不是"渲染成空串"，是根本不进列表。
    2. Level-1 判定全程纯 Python，``llm_calls`` 恒为 0。
    3. Level-2 只在 ``user_initiated=True`` 且场景关键词相关时评估；
       ``autonomous_wakes_for_evaluation`` 恒为 0。
    4. 任何非法状态跃迁抛 :class:`IllegalStateTransitionError`。
    """

    def __init__(self, tasks: Iterable[ConditionalTaskRecord] = ()) -> None:
        self._tasks: dict[str, ConditionalTaskRecord] = {}
        self._states: dict[str, ConditionalTaskState] = {}
        for task in tasks:
            self.register(task)
        self._last_piggyback_report: PiggybackEvaluationReport | None = None

    # ------------------------------------------------------------- 注册/查询

    def register(self, task: ConditionalTaskRecord) -> None:
        if task.task_id in self._tasks:
            raise ValueError(f"duplicate task_id: {task.task_id}")
        self._tasks[task.task_id] = task
        # 默认 DORMANT：注册即隐形
        self._states[task.task_id] = ConditionalTaskState.DORMANT

    def state_of(self, task_id: str) -> ConditionalTaskState:
        return self._states[self._require(task_id)]

    def tasks_in_state(self, state: ConditionalTaskState) -> tuple[str, ...]:
        return tuple(
            task_id for task_id, s in self._states.items() if s == state
        )

    @property
    def dormant_count(self) -> int:
        return len(self.tasks_in_state(ConditionalTaskState.DORMANT))

    def _require(self, task_id: str) -> str:
        if task_id not in self._tasks:
            raise KeyError(f"unknown task_id: {task_id}")
        return task_id

    # ------------------------------------------------------------- 状态机

    def transition(
        self, task_id: str, to_state: ConditionalTaskState
    ) -> ConditionalTaskState:
        task_id = self._require(task_id)
        current = self._states[task_id]
        if to_state not in _ALLOWED_TRANSITIONS[current]:
            raise IllegalStateTransitionError(task_id, current, to_state)
        self._states[task_id] = to_state
        return to_state

    def start(self, task_id: str) -> ConditionalTaskState:
        """执行入口。**唯一**合法路径是 READY → RUNNING。

        从 DORMANT 直接 start 必须被拦截——这正是门禁 4 要防的
        "未就绪就触发执行"。
        """
        return self.transition(task_id, ConditionalTaskState.RUNNING)

    def complete(self, task_id: str) -> ConditionalTaskState:
        return self.transition(task_id, ConditionalTaskState.COMPLETED)

    # ------------------------------------------------- Level-1 机械快轨

    def evaluate_level1(
        self, task: ConditionalTaskRecord, context: EvaluationContext
    ) -> tuple[EvaluationOutcome, ...]:
        """纯 Python 判定所有机械条件。**不得**调用任何模型。"""
        outcomes: list[EvaluationOutcome] = []
        for condition in task.conditions:
            if condition.level != EvaluationLevel.LEVEL1_MECHANICAL:
                # 语义条件不在本轨处理；标记为未满足但不消耗模型
                outcomes.append(
                    EvaluationOutcome(
                        condition_kind=condition.kind,
                        satisfied=False,
                        level=EvaluationLevel.LEVEL2_PIGGYBACK,
                        llm_calls=0,
                        reason="deferred to level-2 piggyback",
                    )
                )
                continue
            outcomes.append(self._eval_mechanical(condition, context))
        return tuple(outcomes)

    def _eval_mechanical(
        self, condition: TriggerCondition, context: EvaluationContext
    ) -> EvaluationOutcome:
        if isinstance(condition, TimeReachedCondition):
            ok = as_utc(context.now, "now") >= as_utc(condition.due_at, "due_at")
            return EvaluationOutcome(
                condition_kind=condition.kind,
                satisfied=ok,
                level=EvaluationLevel.LEVEL1_MECHANICAL,
                llm_calls=0,
                reason="absolute due time reached" if ok else "not yet due",
            )

        if isinstance(condition, GeofenceCondition):
            if context.lat is None or context.lon is None:
                return EvaluationOutcome(
                    condition_kind=condition.kind,
                    satisfied=False,
                    level=EvaluationLevel.LEVEL1_MECHANICAL,
                    llm_calls=0,
                    reason="no fix available",
                )
            distance = _haversine_m(
                context.lat, context.lon, condition.center_lat, condition.center_lon
            )
            inside = distance <= condition.radius_m
            dwell_ok = context.dwelled_seconds >= condition.require_dwell_seconds
            ok = inside and dwell_ok
            return EvaluationOutcome(
                condition_kind=condition.kind,
                satisfied=ok,
                level=EvaluationLevel.LEVEL1_MECHANICAL,
                llm_calls=0,
                reason=(
                    f"inside fence, dwell {context.dwelled_seconds}s"
                    if ok
                    else f"distance {distance:.0f}m / dwell {context.dwelled_seconds}s"
                ),
            )

        if isinstance(condition, HeartRateCondition):
            if context.heart_rate_bpm is None:
                return EvaluationOutcome(
                    condition_kind=condition.kind,
                    satisfied=False,
                    level=EvaluationLevel.LEVEL1_MECHANICAL,
                    llm_calls=0,
                    reason="no heart rate sample",
                )
            window_ok = condition.window in ("any", context.heart_rate_window)
            breach = context.heart_rate_bpm > condition.threshold_bpm
            days_ok = (
                context.consecutive_night_breach_days
                >= condition.consecutive_days_required
            )
            ok = window_ok and breach and days_ok
            return EvaluationOutcome(
                condition_kind=condition.kind,
                satisfied=ok,
                level=EvaluationLevel.LEVEL1_MECHANICAL,
                llm_calls=0,
                reason=(
                    f"{context.heart_rate_bpm}bpm > {condition.threshold_bpm}bpm "
                    f"for {context.consecutive_night_breach_days}d"
                    if ok
                    else "threshold or consecutive-day requirement not met"
                ),
            )

        raise TypeError(f"not a mechanical condition: {type(condition).__name__}")

    def advance_level1(self, context: EvaluationContext) -> tuple[str, ...]:
        """扫描全部 DORMANT 的 Level-1 任务，命中即跃迁 READY。

        开销是 O(休眠任务数) 的纯算术，不触碰模型；200 项任务在亚毫秒级完成。
        """
        promoted: list[str] = []
        for task_id in self.tasks_in_state(ConditionalTaskState.DORMANT):
            task = self._tasks[task_id]
            if task.required_level != EvaluationLevel.LEVEL1_MECHANICAL:
                continue
            if self._is_expired(task, context):
                self.transition(task_id, ConditionalTaskState.EXPIRED)
                continue
            outcomes = self.evaluate_level1(task, context)
            if self._combine(task, outcomes):
                self.transition(task_id, ConditionalTaskState.READY)
                promoted.append(task_id)
        return tuple(promoted)

    def _is_expired(
        self, task: ConditionalTaskRecord, context: EvaluationContext
    ) -> bool:
        return (
            task.expires_at is not None
            and as_utc(context.now, "now") > as_utc(task.expires_at, "expires_at")
        )

    @staticmethod
    def _combine(
        task: ConditionalTaskRecord, outcomes: Sequence[EvaluationOutcome]
    ) -> bool:
        # 语义条件被推迟时视为"未知"，不得当作满足
        decisive = [o for o in outcomes if o.level == EvaluationLevel.LEVEL1_MECHANICAL]
        if not decisive:
            return False
        if task.combine == "and":
            # and 语义下只要还有语义条件未决，就不能判定就绪
            if len(decisive) != len(task.conditions):
                return False
            return all(o.satisfied for o in decisive)
        return any(o.satisfied for o in decisive)

    # ------------------------------------------------- Level-2 机会式捎带

    def evaluate_level2_piggyback(
        self,
        context: EvaluationContext,
        *,
        semantic_judge: Any = None,
    ) -> PiggybackEvaluationReport:
        """仅在用户已主动唤醒且场景相关时，顺路评估语义条件。

        ``autonomous_wakes_for_evaluation`` 恒为 0：本方法**从不**自行唤醒模型，
        它只搭用户这次唤醒的便车。若 ``user_initiated`` 为假，直接全部跳过。
        """
        if not context.user_initiated:
            report = PiggybackEvaluationReport(
                skipped_task_ids=self.tasks_in_state(ConditionalTaskState.DORMANT),
                autonomous_wakes_for_evaluation=0,
            )
            self._last_piggyback_report = report
            return report

        evaluated: list[str] = []
        skipped: list[str] = []
        llm_calls = 0
        llm_tokens = 0

        for task_id in self.tasks_in_state(ConditionalTaskState.DORMANT):
            task = self._tasks[task_id]
            if task.required_level != EvaluationLevel.LEVEL2_PIGGYBACK:
                continue
            if self._is_expired(task, context):
                self.transition(task_id, ConditionalTaskState.EXPIRED)
                continue
            if not self._scene_relevant(task, context):
                skipped.append(task_id)
                continue

            semantic_conditions = [
                c
                for c in task.conditions
                if c.level == EvaluationLevel.LEVEL2_PIGGYBACK
            ]
            relevant = _relevant_keywords(task, context)
            for condition in semantic_conditions:
                # 关键：只有场景确实相关时才付出模型开销，且这是"搭便车"，
                # 不是为评估而唤醒。
                satisfied = bool(
                    semantic_judge(condition.predicate, relevant)
                ) if semantic_judge is not None else bool(relevant)
                llm_calls += 1
                llm_tokens += condition.estimated_llm_tokens
                if satisfied and self._mechanical_part_ok(task, context):
                    self.transition(task_id, ConditionalTaskState.READY)
                    evaluated.append(task_id)
                    break
            else:
                skipped.append(task_id)

        report = PiggybackEvaluationReport(
            evaluated_task_ids=tuple(evaluated),
            skipped_task_ids=tuple(skipped),
            llm_calls=llm_calls,
            llm_tokens=llm_tokens,
            autonomous_wakes_for_evaluation=0,
        )
        self._last_piggyback_report = report
        return report

    def _mechanical_part_ok(
        self, task: ConditionalTaskRecord, context: EvaluationContext
    ) -> bool:
        mechanical = [
            c
            for c in task.conditions
            if c.level == EvaluationLevel.LEVEL1_MECHANICAL
        ]
        if not mechanical:
            return True
        outcomes = [self._eval_mechanical(c, context) for c in mechanical]
        if task.combine == "or":
            return True  # 语义条件已满足即可
        return all(o.satisfied for o in outcomes)

    @staticmethod
    def _scene_relevant(
        task: ConditionalTaskRecord, context: EvaluationContext
    ) -> bool:
        if not context.active_scene_keywords:
            return False
        for condition in task.conditions:
            if condition.level != EvaluationLevel.LEVEL2_PIGGYBACK:
                continue
            if not condition.relevance_keywords:
                return True
            if set(condition.relevance_keywords) & set(context.active_scene_keywords):
                return True
        return False

    # --------------------------------------------------- 门禁 1：看板装配

    def assemble_ready_manifest(self) -> tuple[ConditionalTaskRecord, ...]:
        """只装配 READY 任务。DORMANT 任务**物理上不进入返回列表**。

        这是门禁 1 的实现要点：不是把休眠任务渲染成空串（那样仍然占位、
        仍然可能被序列化进 Prompt），而是根本不出现在数据里。
        """
        return tuple(
            self._tasks[task_id]
            for task_id in self.tasks_in_state(ConditionalTaskState.READY)
        )

    def dormant_manifest_tokens(self) -> int:
        """DORMANT 任务对看板 token 的贡献，按定义恒为 0。"""
        return 0

    def ready_manifest_tokens(self) -> int:
        return sum(t.manifest_tokens_if_ready for t in self.assemble_ready_manifest())

    @property
    def last_piggyback_report(self) -> PiggybackEvaluationReport | None:
        return self._last_piggyback_report


# ---------------------------------------------------------------------------
# 纯函数工具
# ---------------------------------------------------------------------------


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点球面距离（米）。纯算术，无第三方依赖。"""
    import math

    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def _relevant_keywords(
    task: ConditionalTaskRecord, context: EvaluationContext
) -> tuple[str, ...]:
    wanted: set[str] = set()
    for condition in task.conditions:
        if condition.level == EvaluationLevel.LEVEL2_PIGGYBACK:
            wanted.update(condition.relevance_keywords)
    if not wanted:
        return tuple(context.active_scene_keywords)
    return tuple(wanted & set(context.active_scene_keywords))
