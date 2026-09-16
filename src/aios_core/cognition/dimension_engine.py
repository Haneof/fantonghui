"""M5-DIM-LIFECYCLE 心智维度演化引擎（铁律 5 三重硬门槛 + 高阶提炼）。

对应 Agent-07 工单。与 M3-001R ``dimensions.evolution_guard``（单维
守卫）互补，本模块是**跨域探测 → 立项 → 试用 → 高阶提炼**的完整引擎。

* **CrossDimensionalAnomalyDetector**：心率 + 账单 + 聊天等多物理域
  日粒度流，机械判定单域异常日；跨 ≥2 域且持续 ≥3 天 → 锁定
  :class:`CrossDomainAnomalyLock`（0 大模型调用）。
* **TripleGateMachine**（铁律 5）：门槛一 3 天跨域异常才准立项；
  门槛二 30 天试用 + 预测验证（≥70%）否则 EXPIRED；门槛三每日反思
  配额 1 次，超额抛 :class:`QuotaExceededBlockError`。对抗性越界
  （未满 30 天晋升 / 当日第 2 次反思）一律抛异常拒绝。
* **HighOrderDimensionDistiller**：从锁定异常 + 试用证据提炼高阶维度
  （DIM_BURNOUT_RISK 过劳猝死风险 / DIM_CREDIT_RISK 老王信用破产），
  挂载**只读**证据标签（frozen + sealed，篡改即 ValidationError）。
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import require_aware

__all__ = [
    "ACTIVE_CAP",
    "CrossDimensionalAnomalyDetector",
    "CrossDomainAnomalyLock",
    "DailyDomainSample",
    "DimensionEngine",
    "DimensionState",
    "HighOrderDimension",
    "HighOrderDimensionDistiller",
    "PrematurePromotionError",
    "QuotaExceededBlockError",
    "TripleGateMachine",
    "TRIAL_DAYS",
    "TRIAL_ACCURACY_FLOOR",
]

TRIAL_DAYS = 30
TRIAL_ACCURACY_FLOOR = 0.70
ACTIVE_CAP = 32
DAILY_REFLECTION_QUOTA = 1


class DimensionState(StrEnum):
    LOCKED_ANOMALY = "locked_anomaly"     # 跨域异常已锁定（可立项）
    CANDIDATE = "candidate"
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class PrematurePromotionError(Exception):
    """对抗性越界：试用期未满 30 天即申请晋升。"""

    def __init__(self, dimension_id: str, served_days: int, required: int) -> None:
        super().__init__(
            f"{dimension_id}: trial served {served_days}d < required {required}d"
        )
        self.served_days = served_days
        self.required_days = required


class QuotaExceededBlockError(Exception):
    """当日反思配额（1 次）已用尽。"""


# ----------------------------------------------------------------------
# 跨域物理异常探测器
# ----------------------------------------------------------------------

class DailyDomainSample(BaseModel):
    """单域单日样本：value 超出 (low, high) 判为该域异常日。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: StrictStr = Field(min_length=1)          # hr / bills / chat ...
    day: datetime                                     # 当日 00:00（aware）
    value: StrictFloat
    low: StrictFloat
    high: StrictFloat
    note: str = ""

    @model_validator(mode="after")
    def _validate(self) -> "DailyDomainSample":
        require_aware(self.day, "day")
        return self

    @property
    def is_anomalous(self) -> bool:
        return not (self.low <= self.value <= self.high)


class CrossDomainAnomalyLock(BaseModel):
    """跨域持续异常锁定（≥2 域 × ≥3 天，0 大模型判定）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lock_id: StrictStr = Field(min_length=1)
    domains: tuple[StrictStr, ...] = Field(min_length=2)
    first_anomalous_day: datetime
    last_anomalous_day: datetime
    sustained_days: StrictInt = Field(ge=1)
    sample_count: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def _validate(self) -> "CrossDomainAnomalyLock":
        require_aware(self.first_anomalous_day, "first_anomalous_day")
        require_aware(self.last_anomalous_day, "last_anomalous_day")
        if self.last_anomalous_day < self.first_anomalous_day:
            raise ValueError("last day before first day")
        return self


class CrossDimensionalAnomalyDetector:
    """多物理域持续异常探测器（心率+账单+聊天跨 3 天锁定）。"""

    MIN_DOMAINS = 2
    MIN_SUSTAINED_DAYS = 3

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._samples: list[DailyDomainSample] = []

    def ingest(self, samples: Sequence[DailyDomainSample]) -> None:
        with self._lock:
            self._samples.extend(samples)

    def detect(self, *, at: datetime) -> CrossDomainAnomalyLock | None:
        require_aware(at, "at")
        with self._lock:
            anomalous = [s for s in self._samples if s.is_anomalous and s.day <= at]
        by_domain: dict[str, set[str]] = {}
        for sample in anomalous:
            by_domain.setdefault(sample.domain, set()).add(sample.day.date().isoformat())
        qualified = {
            domain: days
            for domain, days in by_domain.items()
            if len(days) >= self.MIN_SUSTAINED_DAYS
        }
        if len(qualified) < self.MIN_DOMAINS:
            return None
        all_days: set[str] = set()
        for days in qualified.values():
            all_days |= days
        first = min(all_days)
        last = max(all_days)
        day0 = datetime.fromisoformat(first).replace(tzinfo=at.tzinfo)
        day1 = datetime.fromisoformat(last).replace(tzinfo=at.tzinfo)
        sustained = (day1 - day0).days + 1
        if sustained < self.MIN_SUSTAINED_DAYS:
            return None
        return CrossDomainAnomalyLock(
            lock_id=f"lock_{first}_{'+'.join(sorted(qualified))}",
            domains=tuple(sorted(qualified)),
            first_anomalous_day=day0,
            last_anomalous_day=day1,
            sustained_days=sustained,
            sample_count=len(anomalous),
        )


# ----------------------------------------------------------------------
# 三重硬门槛状态机（铁律 5）
# ----------------------------------------------------------------------

class TripleGateMachine:
    """门槛一（3 天跨域异常）/门槛二（30 天试用+预测）/门槛三（每日反思配额 1）。"""

    def __init__(self, *, active_cap: int = ACTIVE_CAP) -> None:
        self._lock = threading.RLock()
        self._cap = active_cap
        self._states: dict[str, dict[str, Any]] = {}
        self._reflection_used: dict[str, int] = {}

    # -- 门槛一 ---------------------------------------------------------

    def propose(self, dimension_id: str, anomaly: CrossDomainAnomalyLock) -> None:
        if len(anomaly.domains) < 2 or anomaly.sustained_days < 3:
            raise ValueError("gate-1: requires >=2 domains sustained >=3 days")
        with self._lock:
            if dimension_id in self._states:
                raise ValueError(f"{dimension_id} already proposed")
            self._states[dimension_id] = {
                "state": DimensionState.CANDIDATE,
                "anomaly": anomaly,
                "trial_started": None,
                "predictions": [],
            }

    # -- 门槛二 ---------------------------------------------------------

    def begin_trial(self, dimension_id: str, *, at: datetime) -> None:
        require_aware(at, "at")
        with self._lock:
            record = self._require(dimension_id)
            if record["state"] is not DimensionState.CANDIDATE:
                raise ValueError("begin_trial requires CANDIDATE")
            record["state"] = DimensionState.TRIAL
            record["trial_started"] = at

    def record_prediction(self, dimension_id: str, prediction_id: str, *, correct: bool) -> None:
        with self._lock:
            record = self._require(dimension_id)
            if record["state"] is not DimensionState.TRIAL:
                raise ValueError("predictions require TRIAL")
            record["predictions"].append((prediction_id, correct))

    def promote(self, dimension_id: str, *, at: datetime) -> DimensionState:
        """试用届满晋升；未满 30 天抛 PrematurePromotionError（对抗性越界拦截）。"""
        require_aware(at, "at")
        with self._lock:
            record = self._require(dimension_id)
            if record["state"] is not DimensionState.TRIAL:
                raise ValueError("promote requires TRIAL")
            served = (at - record["trial_started"]).days
            if served < TRIAL_DAYS:
                raise PrematurePromotionError(dimension_id, served, TRIAL_DAYS)
            predictions = record["predictions"]
            accuracy = (
                sum(1 for _, ok in predictions if ok) / len(predictions)
                if predictions
                else 0.0
            )
            active_count = sum(
                1 for r in self._states.values() if r["state"] is DimensionState.ACTIVE
            )
            if accuracy < TRIAL_ACCURACY_FLOOR or active_count >= self._cap:
                record["state"] = DimensionState.EXPIRED
                return DimensionState.EXPIRED
            record["state"] = DimensionState.ACTIVE
            return DimensionState.ACTIVE

    # -- 门槛三 ---------------------------------------------------------

    def reflection_allowance(self, *, at: datetime) -> int:
        require_aware(at, "at")
        day_key = at.date().isoformat()
        with self._lock:
            used = self._reflection_used.get(day_key, 0)
            if used >= DAILY_REFLECTION_QUOTA:
                raise QuotaExceededBlockError(day_key)
            self._reflection_used[day_key] = used + 1
            return DAILY_REFLECTION_QUOTA - used

    def state(self, dimension_id: str) -> DimensionState:
        with self._lock:
            return self._require(dimension_id)["state"]

    def _require(self, dimension_id: str) -> dict[str, Any]:
        record = self._states.get(dimension_id)
        if record is None:
            raise KeyError(f"unknown dimension {dimension_id}")
        return record


# ----------------------------------------------------------------------
# 高阶维度提炼器
# ----------------------------------------------------------------------

class HighOrderDimension(BaseModel):
    """高阶衍生维度（只读证据标签，frozen + sealed）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: StrictStr = Field(min_length=1)     # DIM_BURNOUT_RISK / DIM_CREDIT_RISK
    title: StrictStr = Field(min_length=1)
    state: DimensionState = DimensionState.ACTIVE
    read_only: StrictBool = True                       # sealed：只读标签
    domains: tuple[StrictStr, ...] = Field(min_length=1)
    labels: tuple[StrictStr, ...] = Field(default=())
    evidence_refs: tuple[ObjectRef, ...] = Field(min_length=1)
    derived_from: StrictStr = Field(min_length=1)      # 源异常锁 / 试用记录
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    created_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> "HighOrderDimension":
        require_aware(self.created_at, "created_at")
        if not self.read_only:
            raise ValueError("high-order dimensions are sealed read-only labels")
        for ref in self.evidence_refs:
            if ref.revision is None:
                raise ValueError("evidence refs must pin revisions")
        return self


class HighOrderDimensionDistiller:
    """从锁定异常提炼高阶维度（DIM_BURNOUT_RISK / DIM_CREDIT_RISK）。"""

    _PRESETS: Mapping[str, tuple[str, tuple[str, ...]]] = {
        "burnout": (
            "DIM_BURNOUT_RISK",
            ("过劳猝死风险", "连续深睡不足+静息心率抬升+财务压力话术激增"),
        ),
        "credit": (
            "DIM_CREDIT_RISK",
            ("老王信用破产", "履约失约+关联担保暴雷+回避沟通"),
        ),
    }

    def distill(
        self,
        preset: Literal["burnout", "credit"],
        *,
        anomaly_lock: CrossDomainAnomalyLock,
        trial_dimension_id: str,
        evidence_refs: Sequence[ObjectRef],
        confidence: float,
        at: datetime,
    ) -> HighOrderDimension:
        require_aware(at, "at")
        if preset not in self._PRESETS:
            raise KeyError(f"unknown preset {preset}")
        dimension_id, labels = self._PRESETS[preset]
        return HighOrderDimension(
            dimension_id=dimension_id,
            title=labels[0],
            domains=anomaly_lock.domains,
            labels=labels,
            evidence_refs=tuple(evidence_refs),
            derived_from=trial_dimension_id or anomaly_lock.lock_id,
            confidence=confidence,
            created_at=at,
        )


class DimensionEngine:
    """引擎门面：探测 → 立项 → 试用 → 晋升 → 高阶提炼 全流程编排。"""

    def __init__(self) -> None:
        self.detector = CrossDimensionalAnomalyDetector()
        self.gates = TripleGateMachine()
        self.distiller = HighOrderDimensionDistiller()
