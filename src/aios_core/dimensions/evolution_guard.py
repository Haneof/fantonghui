"""M3-001R 动态维度衍生三重硬门限状态机（宪法铁律 5 落实）。

对应 R3-ARCH 蓝图 M3-006/012（动态维度生命周期、DimensionDerivation），
宪法依据：V3 §15-4/§15-11（禁止维度/反思无价值膨胀）、§64（认知变化
不允许无限自我唤醒）、§74（Candidate→Trial→Active 生命周期：工程性
检查 + 可测收益）、§76（维度不能无限爆炸，登记评分可辅助资源调度）。

三重门限（顺序固定，全部通过才可能 ACTIVE）：

1. **门限一（物理跨域持续异常）**：候选提案必须横跨 ≥2 个物理域
   （如睡眠异常 + 血压异常），且异常持续时间 ≥3 天，否则当场拒绝。
2. **门限二（30 天试用期与预测检验）**：CANDIDATE 进入 TRIAL 后，
   必须累积 Prediction 对撞记录；试用期（≥30 天）届满复核，
   预测准确率 ≥70% 才晋升 ACTIVE，否则自动 EXPIRED。
3. **门限三（每日反思配额）**：每日新维度自省评估配额严格 1 次，
   超额抛 :class:`QuotaExceededBlockError`。

全局硬顶：ACTIVE 衍生维度 ≤32 个；满员晋升时按（活跃度+贡献度）
末位淘汰归档（ARCHIVED），历史与引用完整保留（§75 低频≠无价值）。

递归熔断：反思会话嵌套深度达到第 2 层时物理切断
（:class:`ReflectionLoopCutError`），彻底掐灭自问自答死循环。
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, model_validator

from aios_core.contracts.time import require_aware

__all__ = [
    "ACTIVE_DIMENSION_HARD_CAP",
    "CandidateDimension",
    "CandidateRejectedError",
    "DimensionLifecycleState",
    "DomainAnomaly",
    "EvolutionGuard",
    "PredictionTrialRecord",
    "QuotaExceededBlockError",
    "ReflectionLoopCutError",
    "TRIAL_DAYS",
    "TRIAL_PREDICTION_ACCURACY_FLOOR",
]

#: 门限一：跨域数量的下限（≥2 个物理域）。
MIN_CROSS_DOMAINS = 2
#: 门限一：异常持续时间的下限（≥3 天）。
MIN_ANOMALY_DAYS = 3
#: 门限二：试用期长度（30 天）。
TRIAL_DAYS = 30
#: 门限二：预测准确率晋升地板（≥70%）。
TRIAL_PREDICTION_ACCURACY_FLOOR = 0.70
#: 活跃衍生维度全局硬顶（严格 ≤32）。
ACTIVE_DIMENSION_HARD_CAP = 32
#: 反思会话允许的最大嵌套深度（第 2 层即切断）。
MAX_REFLECTION_DEPTH = 1


class DimensionLifecycleState(StrEnum):
    CANDIDATE = "candidate"
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class CandidateRejectedError(Exception):
    """门限一拒绝：跨域数不足或持续时间不足。"""

    def __init__(self, reason: str, **context: Any) -> None:
        super().__init__(f"dimension candidate rejected: {reason}")
        self.reason = reason
        self.context = context


class QuotaExceededBlockError(Exception):
    """门限三拒绝：每日反思配额（1 次）已用尽。"""

    def __init__(self, day_key: str, quota: int = 1) -> None:
        super().__init__(
            f"daily reflection quota exhausted for {day_key} (quota={quota})"
        )
        self.day_key = day_key
        self.quota = quota


class ReflectionLoopCutError(Exception):
    """自问自答死循环熔断：反思嵌套达到第 2 层被物理切断。"""

    def __init__(self, depth: int) -> None:
        super().__init__(
            f"reflection recursion physically cut at depth {depth} "
            f"(max allowed={MAX_REFLECTION_DEPTH})"
        )
        self.depth = depth


class DomainAnomaly(BaseModel):
    """单物理域的持续异常区间（门限一的判定输入）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: StrictStr = Field(min_length=1)      # sleep / blood_pressure / hr / finance ...
    first_seen: datetime
    last_seen: datetime
    severity_note: str = ""

    @model_validator(mode="after")
    def _validate(self) -> "DomainAnomaly":
        require_aware(self.first_seen, "first_seen")
        require_aware(self.last_seen, "last_seen")
        if self.last_seen < self.first_seen:
            raise ValueError("last_seen must not be before first_seen")
        return self


class PredictionTrialRecord(BaseModel):
    """试用期单次预测对撞记录（门限二的判定输入）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prediction_id: StrictStr = Field(min_length=1)
    at: datetime
    correct: bool


class CandidateDimension(BaseModel):
    """衍生维度候选（状态机主体）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: StrictStr = Field(min_length=1)
    name: StrictStr = Field(min_length=1)
    state: DimensionLifecycleState = DimensionLifecycleState.CANDIDATE
    domains: tuple[StrictStr, ...] = Field(default=())
    created_at: datetime
    trial_started_at: datetime | None = None
    trial_predictions: tuple[PredictionTrialRecord, ...] = Field(default=())
    activity_score: StrictFloat = Field(default=0.0, ge=0.0)
    contribution_score: StrictFloat = Field(default=0.0, ge=0.0)
    archived_reason: str = ""

    @model_validator(mode="after")
    def _validate(self) -> "CandidateDimension":
        require_aware(self.created_at, "created_at")
        return self

    def trial_accuracy(self) -> float | None:
        if not self.trial_predictions:
            return None
        correct = sum(1 for p in self.trial_predictions if p.correct)
        return correct / len(self.trial_predictions)


class EvolutionGuard:
    """动态维度进化守卫：三重门限 + 全局硬顶 + 递归熔断。"""

    def __init__(self, *, active_cap: int = ACTIVE_DIMENSION_HARD_CAP) -> None:
        if active_cap < 1:
            raise ValueError("active_cap must be >= 1")
        self._cap = active_cap
        self._lock = threading.RLock()
        self._dimensions: dict[str, CandidateDimension] = {}
        self._reflection_quota_used: dict[str, int] = {}
        self._reflection_depth = 0
        self._demoted_last: str | None = None

    # ------------------------------------------------------------------
    # 门限一：物理跨域持续异常 → CANDIDATE
    # ------------------------------------------------------------------

    def propose_dimension(
        self,
        dimension_id: str,
        name: str,
        anomalies: Sequence[DomainAnomaly],
        *,
        at: datetime,
    ) -> CandidateDimension:
        require_aware(at, "at")
        distinct_domains = {a.domain for a in anomalies}
        if len(distinct_domains) < MIN_CROSS_DOMAINS:
            raise CandidateRejectedError(
                "cross-domain threshold not met",
                distinct_domains=sorted(distinct_domains),
                required=MIN_CROSS_DOMAINS,
            )
        span_days = (
            max(a.last_seen for a in anomalies) - min(a.first_seen for a in anomalies)
        ).total_seconds() / 86_400.0
        if span_days < MIN_ANOMALY_DAYS:
            raise CandidateRejectedError(
                "anomaly duration below 3-day floor",
                span_days=round(span_days, 2),
                required_days=MIN_ANOMALY_DAYS,
            )
        with self._lock:
            if dimension_id in self._dimensions:
                raise ValueError(f"dimension {dimension_id} already exists")
            candidate = CandidateDimension(
                dimension_id=dimension_id,
                name=name,
                state=DimensionLifecycleState.CANDIDATE,
                domains=tuple(sorted(distinct_domains)),
                created_at=at,
            )
            self._dimensions[dimension_id] = candidate
            return candidate

    # ------------------------------------------------------------------
    # 门限二：30 天试用期 + 预测检验 → ACTIVE / EXPIRED
    # ------------------------------------------------------------------

    def begin_trial(self, dimension_id: str, *, at: datetime) -> None:
        """CANDIDATE → TRIAL（工程性检查通过即可开闸，语义价值留待验证）。"""
        require_aware(at, "at")
        with self._lock:
            dim = self._require(dimension_id)
            if dim.state is not DimensionLifecycleState.CANDIDATE:
                raise ValueError(
                    f"begin_trial requires CANDIDATE, got {dim.state.value}"
                )
            self._dimensions[dimension_id] = dim.model_copy(
                update={"state": DimensionLifecycleState.TRIAL, "trial_started_at": at}
            )

    def record_prediction(
        self,
        dimension_id: str,
        prediction_id: str,
        *,
        at: datetime,
        correct: bool,
    ) -> None:
        require_aware(at, "at")
        with self._lock:
            dim = self._require(dimension_id)
            if dim.state is not DimensionLifecycleState.TRIAL:
                raise ValueError("predictions can only be recorded during TRIAL")
            record = PredictionTrialRecord(
                prediction_id=prediction_id, at=at, correct=correct
            )
            self._dimensions[dimension_id] = dim.model_copy(
                update={
                    "trial_predictions": (*dim.trial_predictions, record),
                    # 每条被使用的预测提升活跃度
                    "activity_score": dim.activity_score + 0.5,
                }
            )

    def review_trial(self, dimension_id: str, *, at: datetime) -> DimensionLifecycleState:
        """试用期届满复核：准确率 ≥70% 晋升 ACTIVE，否则 EXPIRED。"""
        require_aware(at, "at")
        with self._lock:
            dim = self._require(dimension_id)
            if dim.state is not DimensionLifecycleState.TRIAL:
                raise ValueError("review_trial requires TRIAL state")
            started = dim.trial_started_at
            if started is None:
                raise ValueError("trial_started_at missing")
            if (at - started).days < TRIAL_DAYS:
                return dim.state  # 未满试用期：保持 TRIAL
            accuracy = dim.trial_accuracy()
            if accuracy is None or accuracy < TRIAL_PREDICTION_ACCURACY_FLOOR:
                self._dimensions[dimension_id] = dim.model_copy(
                    update={"state": DimensionLifecycleState.EXPIRED}
                )
                return DimensionLifecycleState.EXPIRED
            self._promote_to_active(dimension_id, at=at)
            return DimensionLifecycleState.ACTIVE

    def _promote_to_active(self, dimension_id: str, *, at: datetime) -> None:
        """晋升 ACTIVE；满员时按（活跃度+贡献度）末位淘汰归档。"""
        active_ids = [
            d_id
            for d_id, d in self._dimensions.items()
            if d.state is DimensionLifecycleState.ACTIVE
        ]
        if dimension_id not in active_ids and len(active_ids) >= self._cap:
            victim = min(
                active_ids,
                key=lambda d_id: (
                    self._dimensions[d_id].activity_score
                    + self._dimensions[d_id].contribution_score,
                    d_id,
                ),
            )
            self._dimensions[victim] = self._dimensions[victim].model_copy(
                update={
                    "state": DimensionLifecycleState.ARCHIVED,
                    "archived_reason": (
                        "hard-cap eviction: lowest activity+contribution "
                        f"at {at.isoformat()}"
                    ),
                }
            )
            self._demoted_last = victim
        self._dimensions[dimension_id] = self._dimensions[dimension_id].model_copy(
            update={"state": DimensionLifecycleState.ACTIVE}
        )

    # ------------------------------------------------------------------
    # 门限三：每日反思配额（严格 1 次）
    # ------------------------------------------------------------------

    def daily_reflection_allowance(self, *, at: datetime) -> int:
        """领取当日反思配额。剩余 0 时抛 QuotaExceededBlockError。"""
        require_aware(at, "at")
        day_key = at.date().isoformat()
        with self._lock:
            used = self._reflection_quota_used.get(day_key, 0)
            if used >= 1:
                raise QuotaExceededBlockError(day_key, quota=1)
            self._reflection_quota_used[day_key] = used + 1
            return 1 - (used + 1)

    # ------------------------------------------------------------------
    # 自问自答死循环熔断
    # ------------------------------------------------------------------

    def begin_reflection(self) -> int:
        """进入反思会话：返回当前深度；第 2 层被物理切断（整栈摧毁）。"""
        with self._lock:
            self._reflection_depth += 1
            if self._reflection_depth > MAX_REFLECTION_DEPTH:
                # 物理切断：套娃栈整体归零，不留任何可继续递归的层
                self._reflection_depth = 0
                raise ReflectionLoopCutError(MAX_REFLECTION_DEPTH + 1)
            return self._reflection_depth

    def end_reflection(self) -> None:
        with self._lock:
            if self._reflection_depth > 0:
                self._reflection_depth -= 1

    # ------------------------------------------------------------------
    # 活跃度/贡献度记账与观测
    # ------------------------------------------------------------------

    def record_contribution(self, dimension_id: str, delta: float) -> None:
        with self._lock:
            dim = self._require(dimension_id)
            self._dimensions[dimension_id] = dim.model_copy(
                update={"contribution_score": max(dim.contribution_score + delta, 0.0)}
            )

    def active_dimensions(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                sorted(
                    d_id
                    for d_id, d in self._dimensions.items()
                    if d.state is DimensionLifecycleState.ACTIVE
                )
            )

    def dimension_state(self, dimension_id: str) -> DimensionLifecycleState:
        with self._lock:
            return self._require(dimension_id).state

    def last_evicted(self) -> str | None:
        with self._lock:
            return self._demoted_last

    def _require(self, dimension_id: str) -> CandidateDimension:
        dim = self._dimensions.get(dimension_id)
        if dim is None:
            raise KeyError(f"unknown dimension {dimension_id}")
        return dim
