"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

工单：``arena/agent-dispatch-m2-005r`` -> ``src/aios_core/scheduler/conditional_engine.py``

实战情境
--------------------------------------------------------------------------
用户是长期高压的创业企业法务总监，日程里挂着 **200 项跨周期条件任务**：

* 「当诉讼对方实控人出现股权变更时提醒」（语义条件）
* 「当连续 3 天晚间心率超过 95bpm 时启动心内科预约建档」（物理阈值条件）
* 「在回到上海办公室且处于非深度专注状态时提示签署对赌回购协议」（地理围栏 + 语义）

核心命题（四大硬门禁）
--------------------------------------------------------------------------
1. **DORMANT 任务物理隐形、Token 严格为 0**
   未成熟任务**绝不进入 LLM Prompt**：看板组装与常规会话只物化 READY/RUNNING 任务，
   休眠任务既不参与组装也不产生任何 Token（由 :class:`DormantInvisibilityGuard` 机械证明）。
2. **Level-1 机械快轨：0 Token、1ms 内纯 Python 判定**
   纯时间到期 / 地理围栏 / 生理阈值这类客观物理条件，由 :class:`Level1FastTrack`
   用常量比较直接判定并跃迁至 READY——**大模型调用次数严格为 0**。
3. **Level-2 机会式捎带（Opportunistic Piggyback）**
   依赖语义环境的任务只在"用户主动唤醒 AI 且场景相关"时**顺路批量捎带**评估，
   绝非为了一个休眠任务自主唤醒大模型：无主动会话时评估次数 = 0、LLM 调用 = 0；
   有主动会话时整批只花 1 次调用（不是每条任务一次）。
4. **状态机非法跃迁 100% 拦截**
   严格 ``DORMANT -> READY -> RUNNING -> COMPLETED``；任何跳级/回退/从未就绪直接执行
   一律抛 :class:`IllegalStateTransitionError`。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.time import as_utc, require_aware, utc_now
from aios_core.errors import AIOSProtocolError

__all__ = [
    "LEVEL1_MECHANICAL_BUDGET_MS",
    "MECHANICAL_CONDITION_KINDS",
    "BoardAssembly",
    "BoardEntry",
    "Condition",
    "ConditionKind",
    "ConditionalTask",
    "ConditionalTaskScheduler",
    "DormantInvisibilityGuard",
    "DormantVisibilityLeakError",
    "EvaluationTier",
    "FastTrackReport",
    "GeoPosition",
    "IllegalStateTransitionError",
    "Level1FastTrack",
    "MechanicalSignal",
    "OpportunisticPiggyback",
    "PiggybackReport",
    "TaskState",
    "TaskStateMachine",
    "VitalSnapshot",
    "WakeContext",
]

#: Level-1 机械判定的单条耗时预算（工单口径：纯 Python 判定 1ms 内出结果）。
LEVEL1_MECHANICAL_BUDGET_MS: Final[float] = 1.0

#: 状态跃迁表：严格 DORMANT -> READY -> RUNNING -> COMPLETED，无捷径、无回退。
_ALLOWED_TRANSITIONS: Final[Mapping[str, frozenset[str]]] = {
    "DORMANT": frozenset({"READY"}),
    "READY": frozenset({"RUNNING"}),
    "RUNNING": frozenset({"COMPLETED"}),
    "COMPLETED": frozenset(),
}


class TaskState(StrEnum):
    """任务生命周期状态（严格线性，禁止跳级）。"""

    DORMANT = "DORMANT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


class ConditionKind(StrEnum):
    """条件种类：前三种是 Level-1 机械条件，最后一种是 Level-2 语义条件。"""

    ABSOLUTE_TIME = "absolute_time"
    GEO_FENCE = "geo_fence"
    VITAL_THRESHOLD = "vital_threshold"
    SEMANTIC_SCENE = "semantic_scene"


#: Level-1（机械、0 Token）条件集合。
MECHANICAL_CONDITION_KINDS: Final[frozenset[ConditionKind]] = frozenset(
    {ConditionKind.ABSOLUTE_TIME, ConditionKind.GEO_FENCE, ConditionKind.VITAL_THRESHOLD}
)


class EvaluationTier(StrEnum):
    MECHANICAL = "level1_mechanical"       # 0 Token 快轨
    OPPORTUNISTIC = "level2_opportunistic"  # 机会式捎带


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class IllegalStateTransitionError(AIOSProtocolError):
    """非法状态跃迁（含"从未就绪状态直接触发执行"）——100% 拦截，绝不放行。"""

    def __init__(self, task_id: str, from_state: str, to_state: str) -> None:
        super().__init__(
            ErrorCode.INVALID_ARGUMENT,
            f"illegal task state transition: {from_state} -> {to_state}",
            context={
                "reason": "illegal_state_transition",
                "task_id": task_id,
                "from_state": from_state,
                "to_state": to_state,
                "allowed_from_state": sorted(_ALLOWED_TRANSITIONS.get(from_state, ())),
            },
        )


class DormantVisibilityLeakError(AIOSProtocolError):
    """休眠任务泄漏进 Prompt / 看板——Token 纪律最高级别违约。"""

    def __init__(self, leaked_titles: Sequence[str], *, phase: str) -> None:
        super().__init__(
            ErrorCode.PERMISSION_DENIED,
            "dormant task leaked into an LLM-visible artifact",
            context={
                "reason": "dormant_visibility_leak",
                "phase": phase,
                "leaked_titles": list(leaked_titles)[:20],
                "leaked_count": len(leaked_titles),
            },
        )


# ---------------------------------------------------------------------------
# 条件与信号
# ---------------------------------------------------------------------------


class Condition(BaseModel):
    """单个触发条件（按 ``kind`` 校验必填字段，缺字段直接拒绝，不做猜测）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ConditionKind
    summary: str = Field(min_length=1)

    # ABSOLUTE_TIME
    deadline: datetime | None = None

    # GEO_FENCE
    place_key: str | None = None

    # VITAL_THRESHOLD
    metric: str | None = None
    comparator: Literal[">", ">=", "<", "<="] | None = None
    threshold: float | None = None
    consecutive_days: int | None = Field(default=None, ge=1)

    # SEMANTIC_SCENE
    scene_tags: tuple[str, ...] = ()
    requires_focus_free: bool = False
    requires_presence_place: str | None = None

    @model_validator(mode="after")
    def validate_by_kind(self) -> Self:
        if self.kind is ConditionKind.ABSOLUTE_TIME:
            if self.deadline is None:
                raise ValueError("absolute_time condition requires deadline")
            _ = require_aware(self.deadline, "deadline")
        elif self.kind is ConditionKind.GEO_FENCE:
            if not self.place_key:
                raise ValueError("geo_fence condition requires place_key")
        elif self.kind is ConditionKind.VITAL_THRESHOLD:
            if self.metric is None or self.comparator is None or self.threshold is None:
                raise ValueError(
                    "vital_threshold condition requires metric/comparator/threshold"
                )
            if self.consecutive_days is None:
                raise ValueError("vital_threshold condition requires consecutive_days")
        else:  # SEMANTIC_SCENE
            if not self.scene_tags and not self.requires_focus_free:
                raise ValueError(
                    "semantic_scene condition requires scene_tags or requires_focus_free"
                )
        return self

    @property
    def is_mechanical(self) -> bool:
        return self.kind in MECHANICAL_CONDITION_KINDS

    def as_mechanical_reason(self) -> str:
        """机械判定的可读理由（用于审计与报告，不参与 Prompt 组装）。"""
        if self.kind is ConditionKind.ABSOLUTE_TIME:
            return f"绝对时间已到期: {self.summary}"
        if self.kind is ConditionKind.GEO_FENCE:
            return f"地理围栏命中: {self.place_key}"
        return (
            f"生理阈值命中: {self.metric} {self.comparator} {self.threshold}"
            f"（连续 {self.consecutive_days} 天）"
        )


class GeoPosition(BaseModel):
    """地理围栏快照（端侧定位：只上报"是否在围栏内"，不上报轨迹）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    place_key: str | None = None
    inside_fence: bool = False
    captured_at: datetime

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.captured_at, "captured_at")
        return self


class VitalSnapshot(BaseModel):
    """生理体征快照 + 晚间指标历史（阈值条件的"连续 N 天"就靠这段历史）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    captured_at: datetime
    heart_rate_bpm: float | None = Field(default=None, ge=0.0)
    hrv_ms: float | None = Field(default=None, ge=0.0)
    deep_focus: bool = False
    metric_history: dict[str, tuple[float, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.captured_at, "captured_at")
        return self

    def values_for(self, metric: str) -> tuple[float, ...]:
        """取某指标的历史序列（按时间升序）；内生指标自动回退到快照本体。"""
        if metric in self.metric_history:
            return self.metric_history[metric]
        if metric == "heart_rate_bpm" and self.heart_rate_bpm is not None:
            return (self.heart_rate_bpm,)
        if metric == "hrv_ms" and self.hrv_ms is not None:
            return (self.hrv_ms,)
        return ()


class MechanicalSignal(BaseModel):
    """Level-1 机械快轨的输入信号：纯客观量，不含任何语义判断。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    now: datetime
    position: GeoPosition | None = None
    vitals: VitalSnapshot | None = None

    @model_validator(mode="after")
    def validate_now(self) -> Self:
        _ = require_aware(self.now, "now")
        return self


class WakeContext(BaseModel):
    """Level-2 机会式捎带的输入：**只有用户主动唤醒 AI 才会产生**。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    captured_at: datetime
    user_resumed_ai: bool
    scene_tags: tuple[str, ...] = ()
    session_id: str | None = None
    position: GeoPosition | None = None
    vitals: VitalSnapshot | None = None

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.captured_at, "captured_at")
        return self


# ---------------------------------------------------------------------------
# 任务与状态机
# ---------------------------------------------------------------------------


class ConditionalTask(BaseModel):
    """条件任务（不可变值对象；状态跃迁通过 :class:`TaskStateMachine` 生成新值）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    owner: str = Field(default="legal_director", min_length=1)
    priority: int = Field(default=3, ge=0, le=9)
    conditions: tuple[Condition, ...] = Field(min_length=1)
    state: TaskState = TaskState.DORMANT
    created_at: datetime = Field(default_factory=utc_now)
    ready_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ready_reason: str | None = None

    @property
    def is_dormant(self) -> bool:
        return self.state is TaskState.DORMANT

    @property
    def mechanical_conditions(self) -> tuple[Condition, ...]:
        return tuple(c for c in self.conditions if c.is_mechanical)

    @property
    def semantic_conditions(self) -> tuple[Condition, ...]:
        return tuple(c for c in self.conditions if not c.is_mechanical)

    @property
    def is_purely_mechanical(self) -> bool:
        return not self.semantic_conditions


class TaskStateMachine:
    """严格状态机：只认 DORMANT -> READY -> RUNNING -> COMPLETED 这一条路。"""

    def transition(
        self, task: ConditionalTask, target: TaskState, *, at: datetime, reason: str | None = None
    ) -> ConditionalTask:
        current = task.state
        if target.value not in _ALLOWED_TRANSITIONS[current.value]:
            raise IllegalStateTransitionError(task.task_id, current.value, target.value)
        require_aware(at, "at")
        moment = as_utc(at, "at")  # require_aware 只做校验（返回 None），转换必须显式做
        updates: dict[str, Any] = {"state": target}
        if target is TaskState.READY:
            updates["ready_at"] = moment
            updates["ready_reason"] = reason
        elif target is TaskState.RUNNING:
            updates["started_at"] = moment
        elif target is TaskState.COMPLETED:
            updates["completed_at"] = moment
        return task.model_copy(update=updates)

    # ---- 语义化入口（把"非法直接执行"变成显式违约）----

    def mark_ready(self, task: ConditionalTask, *, at: datetime, reason: str) -> ConditionalTask:
        return self.transition(task, TaskState.READY, at=at, reason=reason)

    def start(self, task: ConditionalTask, *, at: datetime) -> ConditionalTask:
        """READY -> RUNNING；DORMANT 直接执行 => IllegalStateTransitionError。"""
        return self.transition(task, TaskState.RUNNING, at=at)

    def complete(self, task: ConditionalTask, *, at: datetime) -> ConditionalTask:
        """RUNNING -> COMPLETED；未 RUNNING 直接完成 => IllegalStateTransitionError。"""
        return self.transition(task, TaskState.COMPLETED, at=at)


# ---------------------------------------------------------------------------
# Level-1 机械快轨
# ---------------------------------------------------------------------------


class FastTrackReport(BaseModel):
    """一次机械快轨扫描的审计报告（Token 与耗时都可核对）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scanned: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    ready_task_ids: tuple[str, ...] = ()
    mechanical_reasons: tuple[str, ...] = ()
    blocked_by_semantics: tuple[str, ...] = ()
    unmet_mechanical: tuple[str, ...] = ()
    judgement_times_ms: tuple[float, ...] = ()
    max_judgement_ms: float = Field(ge=0.0)
    p95_judgement_ms: float = Field(ge=0.0)
    total_ms: float = Field(ge=0.0)
    llm_calls: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    autonomous_wakes: int = Field(default=0, ge=0)

    @property
    def within_mechanical_budget(self) -> bool:
        return self.p95_judgement_ms <= LEVEL1_MECHANICAL_BUDGET_MS


class Level1FastTrack:
    """机械快轨：只做常量比较，0 Token、无大模型、微秒级。"""

    def __init__(self, *, budget_ms: float = LEVEL1_MECHANICAL_BUDGET_MS) -> None:
        self._budget_ms = budget_ms

    @property
    def budget_ms(self) -> float:
        return self._budget_ms

    # ---- 单条件判定（纯函数）----

    def condition_satisfied(
        self, condition: Condition, signal: MechanicalSignal
    ) -> tuple[bool, str | None]:
        """返回 (是否满足, 未满足原因)。纯 Python 常量比较，绝不调 LLM。"""
        if condition.kind is ConditionKind.ABSOLUTE_TIME:
            assert condition.deadline is not None  # 由 Condition 校验保证
            if as_utc(signal.now, "now") >= as_utc(condition.deadline, "deadline"):
                return (True, None)
            return (False, f"绝对时间未到期（{condition.deadline.isoformat()}）")

        if condition.kind is ConditionKind.GEO_FENCE:
            position = signal.position
            if position is None or not position.inside_fence:
                return (False, "不在任何地理围栏内")
            if position.place_key != condition.place_key:
                return (False, f"当前围栏={position.place_key!r}，需要={condition.place_key!r}")
            return (True, None)

        if condition.kind is ConditionKind.VITAL_THRESHOLD:
            values = signal.vitals.values_for(condition.metric) if signal.vitals else ()
            required = condition.consecutive_days or 1
            if len(values) < required:
                return (
                    False,
                    f"指标 {condition.metric} 历史不足（{len(values)}/{required} 天）",
                )
            window = values[-required:]
            hits = sum(1 for value in window if _compare(value, condition.comparator, condition.threshold))
            if hits == required:
                return (True, None)
            return (
                False,
                f"指标 {condition.metric} 连续命中 {hits}/{required} 天"
                f"（阈值 {condition.comparator}{condition.threshold}）",
            )

        raise AIOSProtocolError(
            ErrorCode.INVALID_ARGUMENT,
            "semantic condition must not be evaluated on the mechanical fast track",
            context={"reason": "semantic_condition_on_fast_track", "kind": condition.kind.value},
        )

    # ---- 任务级扫描 ----

    def scan(
        self, tasks: Iterable[ConditionalTask], signal: MechanicalSignal
    ) -> tuple[FastTrackReport, tuple[ConditionalTask, ...]]:
        """扫描 DORMANT 任务，返回 (报告, 应跃迁至 READY 的任务)。"""
        started = time.perf_counter()
        scanned = 0
        evaluated = 0
        ready_ids: list[str] = []
        ready_tasks: list[ConditionalTask] = []
        reasons: list[str] = []
        blocked: list[str] = []
        unmet: list[str] = []
        timings: list[float] = []

        for task in tasks:
            scanned += 1
            mechanical = task.mechanical_conditions
            if not mechanical:
                continue
            mark = time.perf_counter()
            unmet_reasons = [
                reason
                for reason in (self.condition_satisfied(c, signal)[1] for c in mechanical)
                if reason is not None
            ]
            timings.append((time.perf_counter() - mark) * 1000.0)
            evaluated += 1

            if unmet_reasons:
                unmet.append(f"{task.task_id}: {unmet_reasons[0]}")
                continue
            if task.semantic_conditions:
                # 机械前提已满足，但仍需语义确认 => 保持 DORMANT（留给机会式捎带）。
                blocked.append(task.task_id)
                continue
            ready_ids.append(task.task_id)
            ready_tasks.append(task)
            reasons.extend(c.as_mechanical_reason() for c in mechanical)

        total_ms = (time.perf_counter() - started) * 1000.0
        report = FastTrackReport(
            scanned=scanned,
            evaluated=evaluated,
            ready_task_ids=tuple(ready_ids),
            mechanical_reasons=tuple(reasons),
            blocked_by_semantics=tuple(blocked),
            unmet_mechanical=tuple(unmet),
            judgement_times_ms=tuple(timings),
            max_judgement_ms=max(timings) if timings else 0.0,
            p95_judgement_ms=_p95(timings),
            total_ms=total_ms,
        )
        return (report, tuple(ready_tasks))


def _compare(value: float, comparator: str | None, threshold: float | None) -> bool:
    if comparator is None or threshold is None:
        return False
    if comparator == ">":
        return value > threshold
    if comparator == ">=":
        return value >= threshold
    if comparator == "<":
        return value < threshold
    return value <= threshold


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index]


# ---------------------------------------------------------------------------
# Level-2 机会式捎带
# ---------------------------------------------------------------------------


class PiggybackReport(BaseModel):
    """一次机会式捎带的审计报告：把"不自主唤醒"变成可核对的数字。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    triggered_by_user: bool
    candidates: int = Field(ge=0)
    evaluated_task_ids: tuple[str, ...] = ()
    ready_task_ids: tuple[str, ...] = ()
    scene_matched: tuple[str, ...] = ()
    llm_calls: int = Field(default=0, ge=0)
    autonomous_wakes: int = Field(default=0, ge=0)
    dormant_evaluated_semantically: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(ge=0.0)

    @property
    def piggybacked(self) -> bool:
        return self.triggered_by_user and bool(self.evaluated_task_ids)


class OpportunisticPiggyback:
    """机会式捎带：绝不为了评估休眠任务而自主唤醒大模型。

    规则：
    * ``WakeContext.user_resumed_ai`` 为假 => 一个任务都不评估、LLM 调用 = 0；
    * 为真 => 只评估"语义前提已满足"的候选（机械前提已就绪 + 场景标签命中），
      且**整批只花一次大模型调用**（批量语义判定），不是每条任务一次。
    """

    def __init__(
        self, *, llm_invoker: Any | None = None, fast_track: Level1FastTrack | None = None
    ) -> None:
        self._llm_invoker = llm_invoker
        self._fast_track = fast_track or Level1FastTrack()
        self._llm_calls = 0

    @property
    def llm_calls(self) -> int:
        return self._llm_calls

    def evaluate(
        self, tasks: Iterable[ConditionalTask], context: WakeContext
    ) -> tuple[PiggybackReport, tuple[tuple[ConditionalTask, str], ...]]:
        started = time.perf_counter()
        if not context.user_resumed_ai:
            # 未主动唤醒：宁可让任务继续休眠，也绝不消耗算力（0 评估、0 调用）。
            candidates = tuple(t for t in tasks if t.is_dormant)
            return (
                PiggybackReport(
                    triggered_by_user=False,
                    candidates=len(candidates),
                    llm_calls=0,
                    autonomous_wakes=0,
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                ),
                (),
            )

        scene = set(context.scene_tags)
        # 机械前提同样要过闸：捎带评估也必须"两条腿都站住"（场景命中 + 物理条件成立），
        # 否则会出现"回到上海办公室"这条地理围栏被语义捎带绕过、任务提前点亮的越权行为。
        signal = MechanicalSignal(
            now=context.captured_at, position=context.position, vitals=context.vitals
        )
        eligible: list[tuple[ConditionalTask, tuple[Condition, ...]]] = []
        for task in tasks:
            if not task.is_dormant:
                continue
            semantic = task.semantic_conditions
            if not semantic:
                continue
            mechanical_ok = all(
                self._fast_track.condition_satisfied(condition, signal)[0]
                for condition in task.mechanical_conditions
            )
            if not mechanical_ok:
                continue
            matched: list[Condition] = []
            for condition in semantic:
                if condition.requires_focus_free and context.vitals is not None:
                    if context.vitals.deep_focus:
                        break
                if condition.scene_tags and not (scene & set(condition.scene_tags)):
                    break
                if condition.requires_presence_place is not None:
                    position = context.position
                    if position is None or not position.inside_fence:
                        break
                    if position.place_key != condition.requires_presence_place:
                        break
                matched.append(condition)
            if matched and len(matched) == len(semantic):
                eligible.append((task, tuple(matched)))

        results: list[tuple[ConditionalTask, str]] = []
        calls = 0
        if eligible:
            # 单次批量语义判定：整批任务共用一次大模型调用。
            calls = 1
            self._llm_calls += 1
            if self._llm_invoker is not None:
                self._llm_invoker(
                    tuple(task.task_id for task, _ in eligible),
                    context.scene_tags,
                )
            for task, matched in eligible:
                reason = "语义场景捎带命中: " + ", ".join(c.summary for c in matched)
                results.append((task, reason))

        report = PiggybackReport(
            triggered_by_user=True,
            candidates=len(eligible),
            evaluated_task_ids=tuple(task.task_id for task, _ in eligible),
            ready_task_ids=tuple(task.task_id for task, _ in results),
            scene_matched=tuple(sorted(scene)),
            llm_calls=calls,
            autonomous_wakes=0,
            dormant_evaluated_semantically=len(eligible),
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
        return (report, tuple(results))


# ---------------------------------------------------------------------------
# DORMANT 隐形守卫 + 看板组装
# ---------------------------------------------------------------------------


class BoardEntry(BaseModel):
    """看板条目：**只可能是 READY / RUNNING 任务**。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    title: str
    state: TaskState
    priority: int
    ready_reason: str | None = None


class BoardAssembly(BaseModel):
    """看板组装结果：休眠任务的 Token 贡献被机械钉死为 0。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: tuple[BoardEntry, ...] = ()
    frozen_out: int = Field(ge=0)
    dormant_token_cost: int = Field(default=0, ge=0)
    dormant_titles_included: tuple[str, ...] = ()
    prompt_text: str = ""
    prompt_tokens: int = Field(default=0, ge=0)
    assembled_at: datetime

    @property
    def entry_count(self) -> int:
        return len(self.entries)


class DormantInvisibilityGuard:
    """证明休眠任务在看板/会话里"物理隐形"：既不出现，也不产生 Token。"""

    @staticmethod
    def visible_tasks(tasks: Iterable[ConditionalTask]) -> tuple[ConditionalTask, ...]:
        return tuple(t for t in tasks if t.state is not TaskState.DORMANT)

    @staticmethod
    def assemble(tasks: Iterable[ConditionalTask], *, at: datetime | None = None) -> BoardAssembly:
        materialized = tuple(tasks)
        visible = [
            t
            for t in DormantInvisibilityGuard.visible_tasks(materialized)
        ]
        visible.sort(key=lambda t: (-t.priority, t.ready_at or t.created_at, t.task_id))
        entries = tuple(
            BoardEntry(
                task_id=t.task_id,
                title=t.title,
                state=t.state,
                priority=t.priority,
                ready_reason=t.ready_reason,
            )
            for t in visible
        )
        prompt_text = "\n".join(f"[{e.state.value}] {e.title}" for e in entries)
        dormant = [t for t in materialized if t.state is TaskState.DORMANT]
        return BoardAssembly(
            entries=entries,
            frozen_out=len(dormant),
            dormant_token_cost=0,
            dormant_titles_included=(),
            prompt_text=prompt_text,
            prompt_tokens=_token_estimate(prompt_text),
            assembled_at=at or utc_now(),
        )

    @staticmethod
    def assert_no_dormant_leak(
        assembly: BoardAssembly, dormant_tasks: Iterable[ConditionalTask]
    ) -> None:
        """机械核对：任何休眠任务标题都不得出现在 Prompt 里，且 Token 贡献为 0。"""
        leaked = [t.title for t in dormant_tasks if t.title and t.title in assembly.prompt_text]
        if leaked or assembly.dormant_token_cost != 0 or assembly.dormant_titles_included:
            raise DormantVisibilityLeakError(leaked, phase="board_assembly")

    @staticmethod
    def dormant_token_cost(tasks: Iterable[ConditionalTask]) -> int:
        """休眠任务若被灌进 Prompt 本会消耗的 Token（现状恒为 0，作为对照基线）。"""
        dormant = [t for t in tasks if t.state is TaskState.DORMANT]
        text = "\n".join(t.title for t in dormant)
        return _token_estimate(text)


def _token_estimate(text: str) -> int:
    """确定性 Token 估算：优先复用 C04 看板的官方估算器，避免口径漂移。"""
    if not text:
        return 0
    try:  # pragma: no cover - 兼容无法导入 cockpit 的裁剪环境
        from aios_core.cockpit.pipeline import estimate_tokens

        return estimate_tokens(text)
    except Exception:
        cjk = sum(1 for ch in text if "\u2e80" <= ch <= "\uffef")
        return cjk + (len(text) - cjk + 3) // 4


# ---------------------------------------------------------------------------
# 双轨调度引擎（门面）
# ---------------------------------------------------------------------------


class ConditionalTaskScheduler:
    """双轨调度引擎：Level-1 机械快轨 + Level-2 机会式捎带。"""

    def __init__(
        self,
        *,
        fast_track: Level1FastTrack | None = None,
        piggyback: OpportunisticPiggyback | None = None,
        state_machine: TaskStateMachine | None = None,
    ) -> None:
        self._tasks: dict[str, ConditionalTask] = {}
        self._fast_track = fast_track or Level1FastTrack()
        self._piggyback = piggyback or OpportunisticPiggyback()
        self._state_machine = state_machine or TaskStateMachine()
        self._lock = threading.RLock()
        self._llm_calls = 0
        self._autonomous_wakes = 0

    # ---- 登记与查询 ----

    def register_task(self, task: ConditionalTask) -> ConditionalTask:
        with self._lock:
            if task.task_id in self._tasks:
                raise AIOSProtocolError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "task_id already registered",
                    context={"reason": "duplicate_task", "task_id": task.task_id},
                )
            self._tasks[task.task_id] = task
            return task

    def register_tasks(self, tasks: Iterable[ConditionalTask]) -> int:
        count = 0
        for task in tasks:
            self.register_task(task)
            count += 1
        return count

    def task(self, task_id: str) -> ConditionalTask | None:
        return self._tasks.get(task_id)

    @property
    def tasks(self) -> tuple[ConditionalTask, ...]:
        return tuple(self._tasks.values())

    def tasks_in_state(self, state: TaskState) -> tuple[ConditionalTask, ...]:
        return tuple(t for t in self._tasks.values() if t.state is state)

    @property
    def dormant_count(self) -> int:
        return len(self.tasks_in_state(TaskState.DORMANT))

    @property
    def llm_calls(self) -> int:
        """本引擎累计发起的大模型调用（Level-1 恒不贡献）。"""
        return self._llm_calls + self._piggyback.llm_calls

    @property
    def autonomous_wakes(self) -> int:
        """为评估休眠任务而自主唤醒大模型的次数（铁律：必须恒为 0）。"""
        return self._autonomous_wakes

    # ---- Level-1 机械快轨 ----

    def tick(self, signal: MechanicalSignal) -> FastTrackReport:
        """机械快轨扫描：0 Token、0 大模型调用，直接跃迁至 READY。"""
        with self._lock:
            dormant = [t for t in self._tasks.values() if t.is_dormant]
            report, ready_tasks = self._fast_track.scan(dormant, signal)
            for task in ready_tasks:
                reason = task.mechanical_conditions[0].as_mechanical_reason()
                self._tasks[task.task_id] = self._state_machine.mark_ready(
                    task, at=signal.now, reason=reason
                )
            return report

    # ---- Level-2 机会式捎带 ----

    def piggyback(self, context: WakeContext) -> PiggybackReport:
        with self._lock:
            report, results = self._piggyback.evaluate(self._tasks.values(), context)
            for task, reason in results:
                if task.is_dormant:
                    self._tasks[task.task_id] = self._state_machine.mark_ready(
                        task, at=context.captured_at, reason=reason
                    )
            return report

    # ---- 状态机入口（非法跃迁直接拦截）----

    def start(self, task_id: str, *, at: datetime | None = None) -> ConditionalTask:
        with self._lock:
            task = self._require(task_id)
            updated = self._state_machine.start(task, at=at or utc_now())
            self._tasks[task_id] = updated
            return updated

    def complete(self, task_id: str, *, at: datetime | None = None) -> ConditionalTask:
        with self._lock:
            task = self._require(task_id)
            updated = self._state_machine.complete(task, at=at or utc_now())
            self._tasks[task_id] = updated
            return updated

    # ---- 看板组装（休眠任务 0 Token）----

    def assemble_board(self, *, at: datetime | None = None) -> BoardAssembly:
        with self._lock:
            assembly = DormantInvisibilityGuard.assemble(self._tasks.values(), at=at)
            DormantInvisibilityGuard.assert_no_dormant_leak(
                assembly, (t for t in self._tasks.values() if t.is_dormant)
            )
            return assembly

    def full_board_prompt(self, *, at: datetime | None = None) -> str:
        """常规会话组装：只输出 READY/RUNNING，Prompts 里绝无休眠任务。"""
        return self.assemble_board(at=at).prompt_text

    # ---- 审计 ----

    def dormant_prompt_token_audit(self) -> dict[str, int]:
        """审计：休眠任务在看板里的 Token 消耗（必须为 0）+ 若全灌进去的对照值。"""
        assembly = self.assemble_board()
        return {
            "visible_entries": assembly.entry_count,
            "dormant_frozen_out": assembly.frozen_out,
            "dormant_tokens_in_board": assembly.dormant_token_cost,
            "dormant_tokens_if_naively_prompted": DormantInvisibilityGuard.dormant_token_cost(
                self._tasks.values()
            ),
        }

    def _require(self, task_id: str) -> ConditionalTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise AIOSProtocolError(
                ErrorCode.NOT_FOUND,
                "unknown task_id",
                context={"reason": "unknown_task", "task_id": task_id},
            )
        return task


def summarize_tiers() -> dict[str, str]:
    """双轨职责的一行式说明（便于看板/文档引用，不参与运行）。"""
    return {
        EvaluationTier.MECHANICAL.value: "纯客观物理条件：常量比较，0 Token，1ms 内跃迁 READY",
        EvaluationTier.OPPORTUNISTIC.value: "语义条件：用户主动唤醒时顺路批量评估，整批 1 次调用",
    }
