"""轻量条件事件求值器（Lightweight Conditional Event Evaluator，ToolProposal TLP-LCE-003）。

宪法依据
--------
* 第十五条第 18 款：**禁止每次唤醒无差别执行全部待办事项**；
* 第八十六条：条件驱动的任务在条件未成熟时应当**零 Token 空转**；
* 第八十六条之一：预算与算力硬约束（端侧尤其）。

为什么既有实现不够
------------------
仓库既有 ``scheduler.conditional_engine.Level1FastTrack.scan(tasks, signal)``
对**全部** DORMANT 任务做线性扫描：每来一个机械信号，它都要遍历 ``tasks``，
对每个任务的每条 Level-1 条件重新求值一次。任务量 10 万时，一次 tick 就要
"看" 10 万遍 —— 虽然每次判定是微秒级常量比较（Token 确实为 0），但 CPU 与
端侧电量在**长期静默期**被无意义地烧掉，这正是宪法第 18 款要防的"无差别执行"。

本求值器把"宽相位（wide phase）+ 窄相位（narrow phase）"引入条件调度：

* 注册期按条件种类建索引 —— 绝对时间进**最小堆**（只按到期顺序弹），
  地理围栏按 ``place_key`` 分桶，生理阈值按 ``metric`` 分桶；
* tick 期**只碰命中的桶**：没有地理事件就不看地理桶，没有新生理值就不看生理桶，
  堆顶未到期就连堆都不弹；
* 于是单次 tick 的求值次数从 ``O(全部任务)`` 降到 ``O(命中桶大小)``，
  审计字段 ``tasks_evaluated`` 与 ``tasks_registered`` 直接给出"省了多少"。

对语义条件（``SEMANTIC_SCENE``）本求值器**永不求值**：机械前提成立的语义任务只被
标记为 ``blocked_by_semantics``，留给机会式捎带（Level-2）—— 机械快轨绝不允许
偷跑大模型判定。
"""

from __future__ import annotations

import heapq
import time
from bisect import bisect_left
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import as_utc
from aios_core.scheduler.conditional_engine import Condition, ConditionKind

__all__ = [
    "ConditionRegistration",
    "EvaluationReport",
    "EvaluatorSignals",
    "LightweightConditionalEventEvaluator",
    "ConditionalEventEvaluator",
]


class ConditionRegistration(BaseModel):
    """一次任务注册（条件集合 + 审计标签）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    conditions: tuple[Condition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_conditions(self) -> "ConditionRegistration":
        if not any(condition.is_mechanical for condition in self.conditions):
            raise ValueError(
                "registration requires at least one Level-1 mechanical condition"
            )
        return self

    @property
    def mechanical_conditions(self) -> tuple[Condition, ...]:
        return tuple(c for c in self.conditions if c.is_mechanical)

    @property
    def has_semantic(self) -> bool:
        return any(not c.is_mechanical for c in self.conditions)


class EvaluatorSignals(BaseModel):
    """一次 tick 的现实信号（只携带真正发生变化的那几路，绝不伪造全量）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    now: datetime
    present_places: tuple[str, ...] = ()
    vitals: Mapping[str, tuple[float, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_now(self) -> "EvaluatorSignals":
        _ = as_utc(self.now, "now")
        return self

    @classmethod
    def from_mechanical_signal(cls, signal: Any) -> "EvaluatorSignals":
        """适配既有 ``MechanicalSignal``（位置 + 指标历史），保持调用方零改动。"""

        places: tuple[str, ...] = ()
        position = getattr(signal, "position", None)
        if position is not None and getattr(position, "inside_fence", False):
            place_key = getattr(position, "place_key", None)
            if place_key:
                places = (str(place_key),)
        vitals: dict[str, tuple[float, ...]] = {}
        snapshot = getattr(signal, "vitals", None)
        if snapshot is not None:
            metric_names = set(getattr(snapshot, "metric_history", {}) or {})
            if getattr(snapshot, "heart_rate_bpm", None) is not None:
                metric_names.add("heart_rate_bpm")
            if getattr(snapshot, "hrv_ms", None) is not None:
                metric_names.add("hrv_ms")
            for metric in metric_names:
                vitals[str(metric)] = tuple(snapshot.values_for(str(metric)))
        return cls(
            now=as_utc(getattr(signal, "now"), "now"),
            present_places=places,
            vitals=vitals,
        )


class EvaluationReport(BaseModel):
    """一次 tick 的可审计报告（含"省下多少次求值"的直接证据）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks_registered: int = Field(ge=0)
    tasks_evaluated: int = Field(ge=0)
    narrow_phase_hits: int = Field(ge=0)
    fired_task_ids: tuple[str, ...] = ()
    blocked_by_semantics: tuple[str, ...] = ()
    unmet_reasons: tuple[str, ...] = ()
    time_heap_popped: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)
    llm_calls: int = Field(default=0, ge=0)

    @property
    def touched_ratio(self) -> float:
        if self.tasks_registered == 0:
            return 0.0
        return self.tasks_evaluated / self.tasks_registered


def _compare(value: float, comparator: str | None, threshold: float | None) -> bool:
    if comparator == ">":
        return value > threshold  # type: ignore[operator]
    if comparator == ">=":
        return value >= threshold  # type: ignore[operator]
    if comparator == "<":
        return value < threshold  # type: ignore[operator]
    if comparator == "<=":
        return value <= threshold  # type: ignore[operator]
    raise ValueError(f"unsupported comparator: {comparator!r}")


class LightweightConditionalEventEvaluator:
    """索引化条件求值器：宽相位建索引，窄相位只碰命中桶。"""

    def __init__(self) -> None:
        self._registrations: dict[str, ConditionRegistration] = {}
        # 绝对时间：最小堆 (deadline_us, task_id, condition_index)
        self._time_heap: list[tuple[int, str, int]] = []
        self._heap_edges: set[tuple[int, str, int]] = set()
        # 地理：place_key -> {task_id: condition_index}
        self._geo_index: dict[str, dict[str, int]] = {}
        # 生理：metric -> {task_id: condition_index}
        self._vital_index: dict[str, dict[str, int]] = {}
        # 已由机械前提放行、等待语义确认的任务（绝不偷跑 LLM）
        self._blocked_pending: set[str] = set()
        self._fired: set[str] = set()
        self._llm_calls = 0
        self._tick_count = 0

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(
        self,
        task_id: str,
        *,
        title: str,
        conditions: Sequence[Condition],
    ) -> ConditionRegistration:
        if task_id in self._registrations:
            raise ValueError(f"task {task_id!r} already registered")
        registration = ConditionRegistration(
            task_id=task_id,
            title=title,
            conditions=tuple(conditions),
        )
        self._registrations[task_id] = registration
        for index, condition in enumerate(registration.mechanical_conditions):
            if condition.kind is ConditionKind.ABSOLUTE_TIME:
                assert condition.deadline is not None  # 由 Condition 契约保证
                entry = (
                    int(as_utc(condition.deadline, "deadline").timestamp() * 1_000_000),
                    task_id,
                    index,
                )
                if entry not in self._heap_edges:
                    self._heap_edges.add(entry)
                    heapq.heappush(self._time_heap, entry)
            elif condition.kind is ConditionKind.GEO_FENCE:
                assert condition.place_key is not None
                self._geo_index.setdefault(condition.place_key, {})[task_id] = index
            elif condition.kind is ConditionKind.VITAL_THRESHOLD:
                assert condition.metric is not None
                self._vital_index.setdefault(condition.metric, {})[task_id] = index
        return registration

    def register_many(self, registrations: Iterable[ConditionRegistration]) -> int:
        count = 0
        for registration in registrations:
            self.register(
                registration.task_id,
                title=registration.title,
                conditions=registration.conditions,
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # 求值
    # ------------------------------------------------------------------

    def tick(self, signals: EvaluatorSignals) -> EvaluationReport:
        """一次窄相位 tick：只碰与信号相关的桶。"""

        started = time.perf_counter()
        now = as_utc(signals.now, "now")
        now_us = int(now.timestamp() * 1_000_000)

        evaluated = 0
        popped = 0
        fired: list[str] = []
        unmet: list[str] = []
        blocked: list[str] = []

        # 1) 绝对时间：堆顶未到期则连弹都不弹（O(1) 空转）
        while self._time_heap and self._time_heap[0][0] <= now_us:
            _deadline_us, task_id, _index = heapq.heappop(self._time_heap)
            popped += 1
            evaluated += 1
            self._resolve(task_id, signals, fired, unmet, blocked)

        # 2) 地理：仅当本 tick 真的出现在某个围栏内才处理该围栏的桶
        for place_key in signals.present_places:
            bucket = self._geo_index.get(place_key)
            if not bucket:
                continue
            for task_id in tuple(bucket):
                evaluated += 1
                self._resolve(task_id, signals, fired, unmet, blocked)

        # 3) 生理：仅当该指标本 tick 带来新值时处理该指标的桶
        for metric, values in signals.vitals.items():
            bucket = self._vital_index.get(metric)
            if not bucket or not values:
                continue
            for task_id in tuple(bucket):
                evaluated += 1
                self._resolve(task_id, signals, fired, unmet, blocked)

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._tick_count += 1
        return EvaluationReport(
            tasks_registered=len(self._registrations),
            tasks_evaluated=evaluated,
            narrow_phase_hits=evaluated,
            fired_task_ids=tuple(fired),
            blocked_by_semantics=tuple(blocked),
            unmet_reasons=tuple(unmet[:16]),
            time_heap_popped=popped,
            elapsed_ms=elapsed_ms,
            llm_calls=self._llm_calls,
        )

    def _resolve(
        self,
        task_id: str,
        signals: EvaluatorSignals,
        fired: list[str],
        unmet: list[str],
        blocked: list[str],
    ) -> None:
        if task_id in self._fired:
            return
        registration = self._registrations[task_id]
        for condition in registration.mechanical_conditions:
            reason = self._unsatisfied_reason(condition, signals)
            if reason is not None:
                unmet.append(f"{task_id}: {reason}")
                return
        if registration.has_semantic:
            self._blocked_pending.add(task_id)
            blocked.append(task_id)
            return
        self._fired.add(task_id)
        fired.append(task_id)

    @staticmethod
    def _unsatisfied_reason(
        condition: Condition, signals: EvaluatorSignals
    ) -> str | None:
        if condition.kind is ConditionKind.ABSOLUTE_TIME:
            assert condition.deadline is not None
            if as_utc(signals.now, "now") >= as_utc(condition.deadline, "deadline"):
                return None
            return f"绝对时间未到期（{condition.deadline.isoformat()}）"
        if condition.kind is ConditionKind.GEO_FENCE:
            if condition.place_key in signals.present_places:
                return None
            return f"不在围栏 {condition.place_key!r} 内"
        if condition.kind is ConditionKind.VITAL_THRESHOLD:
            values = signals.vitals.get(str(condition.metric), ())
            required = condition.consecutive_days or 1
            if len(values) < required:
                return f"指标 {condition.metric} 历史不足（{len(values)}/{required} 天）"
            window = values[-required:]
            hits = sum(
                1
                for value in window
                if _compare(value, condition.comparator, condition.threshold)
            )
            if hits == required:
                return None
            return (
                f"指标 {condition.metric} 连续命中 {hits}/{required} 天"
                f"（阈值 {condition.comparator}{condition.threshold}）"
            )
        raise ValueError(
            "semantic condition must not reach the mechanical evaluator "
            f"(kind={condition.kind.value})"
        )

    # ------------------------------------------------------------------
    # 只读视图
    # ------------------------------------------------------------------

    @property
    def llm_calls(self) -> int:
        return self._llm_calls

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def fired_task_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._fired))

    def blocked_task_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._blocked_pending))

    def earliest_pending_us(self) -> int | None:
        return self._time_heap[0][0] if self._time_heap else None

    def index_sizes(self) -> dict[str, int]:
        return {
            "time_heap": len(self._time_heap),
            "geo_places": len(self._geo_index),
            "vital_metrics": len(self._vital_index),
        }

    def least_upper_bound_deadline(self, target_us: int) -> int:
        """只读探针：返回堆中第一个不早于 ``target_us`` 的到期时刻（供断点续算）。"""

        deadlines = sorted(entry[0] for entry in self._time_heap)
        index = bisect_left(deadlines, target_us)
        if index >= len(deadlines):
            return -1
        return deadlines[index]


#: 兼容别名（与仓库既有命名风格保持一致）。
ConditionalEventEvaluator = LightweightConditionalEventEvaluator
