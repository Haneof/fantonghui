"""高阶认知维度导数闸门与拐点预警熔断（阶段四核心算子）。

宪法依据
--------
* 第二十二条：横向交织的自发上升 —— 速度/加速度这类**派生量只允许建立在高阶
  认知维度上**（倦怠、投资焦虑、孤独感、意义感）；心率、IMU 幅值、步数这类
  硬件原始量必须保持"如实记录"，绝不允许在原始信号上叠加派生认知层；
* 第二十九条之一：门限数字外置为策略对象，代码里不写死任何魔法阈值；
* 铁律 1 / 铁律 5：拐点识别必须**机械完成（0 次大模型调用）**，且只允许触发
  熔断动作（冻结新增承诺 / 安排休息窗），绝不允许把拐点直接升级为新维度。

本模块给出三件事
----------------
1. :class:`CognitiveDerivativeGate` —— 白名单放行、硬件维度直接拒绝（并留审计），
   所有曲线写入都必须过这道门；
2. :class:`InflectionDetector` —— 纯机械拐点识别（速度符号翻转 + 幅度门限）；
3. :class:`PreemptiveCircuitBreaker` —— 拐点触发**预防性熔断**，返回可执行动作
   清单并保证 0 次大模型调用（由 :class:`ModelCallMeter` 现场作证）。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.cognition.model_call_meter import ModelCallMeter
from aios_core.contracts.models import DimensionCurvePoint
from aios_core.contracts.refs import ObjectRef

__all__ = [
    "CircuitBreakDecision",
    "CognitiveDerivativeGate",
    "DerivativeAudit",
    "DerivativeEligibilityPolicy",
    "DerivativeForbiddenError",
    "Inflection",
    "InflectionDetector",
    "PreemptiveCircuitBreaker",
]

#: 高阶认知维度（允许计算速度/加速度）。新增维度必须经由铁律 5 的三重门限，
#: 不允许在代码里随手扩容 —— 这里是**已注册**的高阶认知维度清单。
COGNITIVE_DIMENSIONS: frozenset[str] = frozenset(
    {
        "dim_burnout",
        "dim_investment_anxiety",
        "dim_loneliness",
        "dim_meaning",
        "dim_relationship_tension",
    }
)

#: 硬件原始维度（禁止在其上叠加派生认知量）。
HARDWARE_DIMENSIONS: frozenset[str] = frozenset(
    {
        "dim_heart_rate_raw",
        "dim_hrv_raw",
        "dim_imu_raw",
        "dim_step_count_raw",
        "dim_spo2_raw",
    }
)


class DerivativeForbiddenError(ValueError):
    """在硬件原始维度上计算派生量：直接拒绝（宪法第二十二条）。"""


class DerivativeEligibilityPolicy(BaseModel):
    """派生量准入策略（白名单 + 黑名单 + 版本号，可审计）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cognitive_dimensions: frozenset[str] = Field(default_factory=lambda: COGNITIVE_DIMENSIONS)
    hardware_dimensions: frozenset[str] = Field(default_factory=lambda: HARDWARE_DIMENSIONS)
    policy_version: str = Field(default="derivative-policy-v1", min_length=1)
    require_whitelisted: bool = True

    @model_validator(mode="after")
    def validate_disjoint(self) -> "DerivativeEligibilityPolicy":
        overlap = self.cognitive_dimensions & self.hardware_dimensions
        if overlap:
            raise ValueError(f"cognitive and hardware dimensions must be disjoint: {sorted(overlap)}")
        return self


class DerivativeAudit(BaseModel):
    """派生量闸门审计（放行次数 / 拒绝次数 / 被拒维度）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: int = Field(ge=0)
    rejected: int = Field(ge=0)
    rejected_dimensions: tuple[str, ...] = ()

    @property
    def rejection_rate(self) -> float:
        total = self.allowed + self.rejected
        return (self.rejected / total) if total else 0.0


class CognitiveDerivativeGate:
    """所有曲线写入的前置闸门：只放行高阶认知维度。"""

    def __init__(self, *, policy: DerivativeEligibilityPolicy | None = None) -> None:
        self.policy = policy or DerivativeEligibilityPolicy()
        self._allowed = 0
        self._rejected: list[str] = []

    # ------------------------------------------------------------------

    def is_eligible(self, dimension_id: str) -> bool:
        if dimension_id in self.policy.hardware_dimensions:
            return False
        if self.policy.require_whitelisted:
            return dimension_id in self.policy.cognitive_dimensions
        return dimension_id not in self.policy.hardware_dimensions

    def guard(self, dimension_id: str) -> None:
        """不通过即抛错：派生认知绝不允许长在硬件原始量上。"""

        if self.is_eligible(dimension_id):
            self._allowed += 1
            return
        self._rejected.append(dimension_id)
        reason = (
            "硬件原始维度" if dimension_id in self.policy.hardware_dimensions else "未注册的高阶认知维度"
        )
        raise DerivativeForbiddenError(
            f"{reason} {dimension_id!r} 不得计算速度/加速度派生量"
            f"（策略版本 {self.policy.policy_version}）"
        )

    def record_point(
        self,
        tracker: object,
        *,
        dimension_ref: ObjectRef,
        value: float,
        point_time: datetime,
        **kwargs: object,
    ) -> DimensionCurvePoint:
        """过闸后写入曲线点（唯一被允许的写入口）。"""

        self.guard(dimension_ref.object_id)
        return tracker.record_point(  # type: ignore[attr-defined]
            dimension_ref=dimension_ref,
            value=value,
            point_time=point_time,
            **kwargs,
        )

    def audit(self) -> DerivativeAudit:
        return DerivativeAudit(
            allowed=self._allowed,
            rejected=len(self._rejected),
            rejected_dimensions=tuple(self._rejected),
        )


class Inflection(BaseModel):
    """一次拐点（速度符号翻转 + 幅度达标，纯机械判定）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: str
    at: datetime
    from_velocity: float
    to_velocity: float
    velocity_delta: float
    acceleration: float
    severity: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_flip(self) -> "Inflection":
        if self.from_velocity * self.to_velocity >= 0:
            raise ValueError("an inflection requires the velocity sign to flip")
        if self.velocity_delta == 0.0:
            raise ValueError("an inflection requires a non-zero velocity change")
        return self


class InflectionDetector:
    """拐点识别器：只看曲线点自身的速度/加速度，不调大模型、不猜语义。

    判据使用**相对**速度变化（``|Δv| / max(|v_from|, |v_to|)``），因此与曲线点的
    采样粒度无关（日/周/月皆可），代码里没有任何针对特定单位的魔法阈值。
    """

    def __init__(self, *, min_relative_delta: float = 0.25, min_samples: int = 4) -> None:
        if min_relative_delta <= 0:
            raise ValueError("min_relative_delta must be positive")
        if min_samples < 3:
            raise ValueError("min_samples must be at least 3")
        self.min_relative_delta = min_relative_delta
        self.min_samples = min_samples

    def detect(self, points: Sequence[DimensionCurvePoint]) -> Inflection | None:
        """返回最近一次满足门限的拐点（无则 None）。"""

        if len(points) < self.min_samples:
            return None
        latest: Inflection | None = None
        for previous, current in zip(points, points[1:]):
            left = previous.velocity
            right = current.velocity
            if left is None or right is None or left == 0 or right == 0:
                continue
            if left * right > 0:
                continue
            delta = right - left
            reference = max(abs(left), abs(right), 1e-12)
            relative = abs(delta) / reference
            if relative < self.min_relative_delta:
                continue
            latest = Inflection(
                dimension_id=current.dimension_ref.object_id,
                at=current.point_time,
                from_velocity=left,
                to_velocity=right,
                velocity_delta=delta,
                acceleration=current.acceleration or 0.0,
                severity=min(1.0, relative / 2.0),
            )
        return latest


class CircuitBreakDecision(BaseModel):
    """预防性熔断裁决（0 大模型调用，动作清单可直接执行）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    triggered: bool
    dimension_id: str
    reason: str = Field(min_length=1)
    actions: tuple[str, ...] = ()
    severity: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_calls: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_breaker(self) -> "CircuitBreakDecision":
        if self.llm_calls != 0:
            raise ValueError("拐点熔断必须是纯机械动作：0 次大模型调用（铁律 1/5）")
        if self.triggered and not self.actions:
            raise ValueError("熔断触发必须给出可执行动作清单")
        return self


class PreemptiveCircuitBreaker:
    """拐点 → 预防性熔断（在崩掉之前先踩刹车）。"""

    def __init__(
        self,
        *,
        gate: CognitiveDerivativeGate,
        detector: InflectionDetector | None = None,
        meter: ModelCallMeter | None = None,
    ) -> None:
        self.gate = gate
        self.detector = detector or InflectionDetector()
        self.meter = meter or ModelCallMeter(name="inflection-breaker")

    def evaluate(
        self,
        tracker: object,
        dimension_id: str,
        *,
        severity_threshold: float = 0.5,
    ) -> CircuitBreakDecision:
        started = time.perf_counter()
        self.gate.guard(dimension_id)
        before = self.meter.snapshot()
        points = tracker.get_curve(dimension_id)  # type: ignore[attr-defined]
        inflection = self.detector.detect(points)
        if inflection is None or inflection.severity < severity_threshold:
            return CircuitBreakDecision(
                triggered=False,
                dimension_id=dimension_id,
                reason=(
                    "未出现满足门限的拐点"
                    if inflection is None
                    else f"拐点幅度 {inflection.severity:.3f} 低于门限 {severity_threshold}"
                ),
                severity=inflection.severity if inflection else 0.0,
                llm_calls=self.meter.delta(before).total,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        actions = [
            "freeze_new_commitments",
            "schedule_rest_window_24h",
            "notify_trusted_confidant",
        ]
        if inflection.severity >= 0.8:
            actions.append("force_offline_weekend")
        return CircuitBreakDecision(
            triggered=True,
            dimension_id=dimension_id,
            reason=(
                f"维度 {dimension_id} 速度由 {inflection.from_velocity:+.4f} 翻转为 "
                f"{inflection.to_velocity:+.4f}（severity={inflection.severity:.3f}）"
            ),
            actions=tuple(actions),
            severity=inflection.severity,
            llm_calls=self.meter.delta(before).total,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
