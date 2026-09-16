"""M3-001R 动态维度衍生三重硬门限状态机（宪法铁律 5 落实）。

铁律 5：严禁 AI 无休止地自言自语、虚假自省导致系统维度爆炸。端侧算力
有限，认知维度必须极度克制。本守卫引擎以三重硬门限 + 全局硬顶 +
反思递归熔断捍卫该铁律：

1. 门限一（物理跨域持续异常）：必须跨越 >= 2 个物理域且持续 >= 3 天，
   才允许提交新维度候选（CANDIDATE）；
2. 门限二（30 天试用期与预测检验）：候选维度须在 30 天内提供预测
   准确率 >= 70% 的认知解释力，否则自动失效（EXPIRED）；
3. 门限三（每日反思配额）：每日新维度自省评估配额严格为 1 次，
   超额直接抛 QuotaExceededBlockError；
4. 全局活跃维度硬顶 <= 32：引入新维度时按活跃度与贡献度淘汰末位至
   ARCHIVED；自问自答递归在第 2 层被物理切断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "MAX_ACTIVE_DIMENSIONS",
    "DimensionAdmissionError",
    "DimensionEvolutionGuard",
    "GuardLifecycle",
    "QuotaExceededBlockError",
    "ReflectionLoopCircuitError",
    "TrackedDimension",
]

MAX_ACTIVE_DIMENSIONS = 32


class QuotaExceededBlockError(RuntimeError):
    """每日反思配额超额：第 2 次当日自省评估被硬性拦截。"""


class ReflectionLoopCircuitError(RuntimeError):
    """自问自答死循环熔断：反思递归进入第 2 层即被物理切断。"""


class DimensionAdmissionError(ValueError):
    """门限一准入失败：跨域数或持续时长不满足硬门限。"""


class GuardLifecycle(StrEnum):
    """守卫侧维度生命周期（准入 -> 试用 -> 活跃 / 失效 / 归档）。"""

    CANDIDATE = "candidate"
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


@dataclass
class TrackedDimension:
    """一枚被守卫追踪的衍生维度档案。"""

    dimension_id: str
    name: str
    anomaly_domains: tuple[str, ...]
    anomaly_duration_days: int
    submitted_day: int
    lifecycle: GuardLifecycle = GuardLifecycle.CANDIDATE
    trial_started_day: int | None = None
    predictions_correct: int = 0
    predictions_total: int = 0
    activity_score: float = 0.0
    contribution_score: float = 0.0
    archived_day: int | None = None

    @property
    def combined_score(self) -> float:
        return self.activity_score + self.contribution_score

    @property
    def prediction_accuracy(self) -> float | None:
        if self.predictions_total == 0:
            return None
        return self.predictions_correct / self.predictions_total


class DimensionEvolutionGuard:
    """维度演化守卫：三重门限准入 + 32 活跃硬顶 + 反思递归熔断。"""

    MAX_ACTIVE_DIMENSIONS = MAX_ACTIVE_DIMENSIONS
    DAILY_REFLECTION_QUOTA = 1
    TRIAL_DAYS = 30
    MIN_PREDICTION_ACCURACY = 0.70
    MIN_ANOMALY_DOMAINS = 2
    MIN_ANOMALY_DAYS = 3
    MAX_REFLECTION_DEPTH = 2  # 第 2 层递归物理切断

    def __init__(self) -> None:
        self._dimensions: dict[str, TrackedDimension] = {}
        self._reflection_used_days: set[int] = set()
        self._reflection_depth = 0

    # -- 门限一：物理跨域持续异常准入 -------------------------------------------

    def submit_candidate(
        self,
        dimension_id: str,
        name: str,
        anomaly_domains: tuple[str, ...] | list[str],
        anomaly_duration_days: int,
        day: int,
    ) -> TrackedDimension:
        """提交新维度候选：跨域 >= 2 且持续 >= 3 天方可准入。"""

        if dimension_id in self._dimensions:
            raise ValueError(f"dimension {dimension_id!r} already tracked")
        domains = tuple(dict.fromkeys(anomaly_domains))
        if len(domains) < self.MIN_ANOMALY_DOMAINS:
            raise DimensionAdmissionError(
                f"gate-1 rejected {dimension_id!r}: anomaly spans"
                f" {len(domains)} physical domain(s),"
                f" requires >= {self.MIN_ANOMALY_DOMAINS}"
            )
        if anomaly_duration_days < self.MIN_ANOMALY_DAYS:
            raise DimensionAdmissionError(
                f"gate-1 rejected {dimension_id!r}: anomaly persisted"
                f" {anomaly_duration_days} day(s),"
                f" requires >= {self.MIN_ANOMALY_DAYS}"
            )
        record = TrackedDimension(
            dimension_id=dimension_id,
            name=name,
            anomaly_domains=domains,
            anomaly_duration_days=anomaly_duration_days,
            submitted_day=day,
            lifecycle=GuardLifecycle.CANDIDATE,
            trial_started_day=day,
        )
        self._dimensions[dimension_id] = record
        return record

    def dimension(self, dimension_id: str) -> TrackedDimension:
        try:
            return self._dimensions[dimension_id]
        except KeyError as exc:
            raise KeyError(f"dimension {dimension_id!r} is not tracked") from exc

    # -- 门限二：30 天试用期与预测检验 -------------------------------------------

    def record_prediction(self, dimension_id: str, *, correct: bool) -> None:
        record = self.dimension(dimension_id)
        if record.lifecycle not in (GuardLifecycle.CANDIDATE, GuardLifecycle.TRIAL):
            raise ValueError(
                f"dimension {dimension_id!r} is not in trial"
                f" (lifecycle={record.lifecycle.value})"
            )
        record.lifecycle = GuardLifecycle.TRIAL
        record.predictions_total += 1
        if correct:
            record.predictions_correct += 1

    def conclude_trial(self, dimension_id: str, day: int) -> GuardLifecycle:
        """试用期满裁决：预测准确率 >= 70% 且在 30 天窗口内 -> ACTIVE。"""

        record = self.dimension(dimension_id)
        if record.trial_started_day is None:
            raise ValueError(f"dimension {dimension_id!r} never entered trial")
        within_window = day - record.trial_started_day <= self.TRIAL_DAYS
        accuracy = record.prediction_accuracy
        if (
            within_window
            and accuracy is not None
            and accuracy >= self.MIN_PREDICTION_ACCURACY
        ):
            record.lifecycle = GuardLifecycle.ACTIVE
            self._enforce_active_cap(day)
            return record.lifecycle
        record.lifecycle = GuardLifecycle.EXPIRED
        return record.lifecycle

    # -- 全局活跃硬顶：<= 32，末位淘汰归档 ----------------------------------------

    def active_dimensions(self) -> tuple[TrackedDimension, ...]:
        return tuple(
            d
            for d in self._dimensions.values()
            if d.lifecycle is GuardLifecycle.ACTIVE
        )

    def note_scores(
        self,
        dimension_id: str,
        *,
        activity_delta: float = 0.0,
        contribution_delta: float = 0.0,
    ) -> None:
        record = self.dimension(dimension_id)
        record.activity_score += activity_delta
        record.contribution_score += contribution_delta

    def force_admit_active(self, dimension_id: str, day: int) -> list[str]:
        """把指定维度升为 ACTIVE 并执行硬顶淘汰；返回本轮归档的末位 ID。"""

        record = self.dimension(dimension_id)
        record.lifecycle = GuardLifecycle.ACTIVE
        return self._enforce_active_cap(day)

    def _enforce_active_cap(self, day: int) -> list[str]:
        evicted: list[str] = []
        while len(self.active_dimensions()) > self.MAX_ACTIVE_DIMENSIONS:
            victim = min(
                self.active_dimensions(),
                key=lambda d: (d.combined_score, d.submitted_day),
            )
            victim.lifecycle = GuardLifecycle.ARCHIVED
            victim.archived_day = day
            evicted.append(victim.dimension_id)
        return evicted

    # -- 门限三：每日反思配额 ---------------------------------------------------

    def begin_reflection(self, day: int) -> None:
        """当日自省评估配额核销：配额严格为 1，超额直接熔断。"""

        if day in self._reflection_used_days:
            raise QuotaExceededBlockError(
                f"daily reflection quota (={self.DAILY_REFLECTION_QUOTA})"
                f" already consumed on day {day}; AI self-chatter is banned"
            )
        self._reflection_used_days.add(day)

    # -- 自问自答死循环熔断 ------------------------------------------------------

    def enter_reflection_scope(self, topic: str) -> int:
        """进入一层反思作用域；第 2 层递归物理切断。"""

        next_depth = self._reflection_depth + 1
        if next_depth >= self.MAX_REFLECTION_DEPTH:
            raise ReflectionLoopCircuitError(
                f"reflection recursion on topic {topic!r} cut at depth"
                f" {next_depth}; self-answering loops are physically banned"
            )
        self._reflection_depth = next_depth
        return next_depth

    def exit_reflection_scope(self) -> None:
        if self._reflection_depth <= 0:
            raise ReflectionLoopCircuitError("no active reflection scope to exit")
        self._reflection_depth -= 1

    @property
    def reflection_depth(self) -> int:
        return self._reflection_depth
