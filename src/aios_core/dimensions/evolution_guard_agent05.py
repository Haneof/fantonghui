"""M3-001R 动态维度衍生三重硬门限状态机（坚决捍卫宪法铁律 5）。
独立命名并存线（agent-05）：本模块为同工单独立命名交付版本，与共享分支上的规范实现并存，零覆盖；详见批次报告 agent-05-m2m3-sim-batch-20260916。

最高宪法铁律 5：严禁 AI 无休止地自言自语、虚假自省导致系统维度爆炸！
端侧有限算力下，认知维度必须极度克制。

四大硬门禁：

1. **三重门限准入状态机**：
   - 门限一（物理跨域持续异常）：必须跨越 **≥2 个物理域**（如睡眠异常 +
     血压异常）且持续 **≥3 天**，才允许提交新维度候选（CANDIDATE），
     否则 ``GateOneRejectedError``；
   - 门限二（30 天试用期与预测检验）：候选维度必须在 30 天内提供连续
     的认知解释力与成功预测（Prediction 准确率 **≥ 70%**），否则自动
     失效（EXPIRED）；
   - 门限三（每日反思配额）：每日新维度自省评估配额严格为 **1 次**，
     超额直接抛出 ``QuotaExceededBlockError``；
2. **活跃维度全局硬顶**：任何时刻全局活跃衍生维度数量严格 **≤ 32**；
   达到 32 个后引入新维度，必须依据活跃度与贡献度淘汰归档（ARCHIVED）
   末位维度；
3. **自问自答死循环熔断**：注入恶意 Prompt 诱导 AI 反思套娃时，守卫引擎
   在第 2 层递归时直接物理切断（``RecursionCircuitBrokenError``）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "DimensionEvolutionGuard",
    "DimensionPhase",
    "DerivedDimension",
    "DomainAnomaly",
    "GateOneRejectedError",
    "GLOBAL_ACTIVE_CAP",
    "MIN_ANOMALY_DOMAINS",
    "MIN_PREDICTION_ACCURACY",
    "MIN_SUSTAINED_DAYS",
    "PROBATION_DAYS",
    "QuotaExceededBlockError",
    "RecursionCircuitBrokenError",
    "ReflectionRecord",
    "UnknownDimensionError",
]

# ----------------------------------------------------------------------
# 硬门限常量（宪法级，不可放宽）
# ----------------------------------------------------------------------

GLOBAL_ACTIVE_CAP = 32          # 全局活跃衍生维度硬顶
PROBATION_DAYS = 30             # 试用期（天）
MIN_PREDICTION_ACCURACY = 0.70  # 预测准确率下限
MIN_ANOMALY_DOMAINS = 2         # 门限一：最少物理跨域数
MIN_SUSTAINED_DAYS = 3          # 门限一：最少持续天数
DAILY_REFLECTION_QUOTA = 1      # 门限三：每日反思配额
MAX_REFLECTION_DEPTH = 2        # 递归熔断：第 2 层直接物理切断


class DimensionPhase(str, Enum):
    """衍生维度生命周期（铁律 5 状态机）。"""

    CANDIDATE = "candidate"
    PROBATION = "probation"  # 30 天试用期（门限二）
    ACTIVE = "active"
    EXPIRED = "expired"  # 试用期未达标 → 自动失效
    ARCHIVED = "archived"  # 硬顶淘汰归档
    REJECTED = "rejected"  # 门限一拒绝（未入池）


class GateOneRejectedError(ValueError):
    """门限一拒绝：跨域数或持续天数不足，禁止提交维度候选。"""


class QuotaExceededBlockError(RuntimeError):
    """门限三阻断：每日反思配额（严格 1 次）已用尽。"""


class RecursionCircuitBrokenError(RuntimeError):
    """自问自答死循环熔断：第 2 层递归被物理切断。"""


class UnknownDimensionError(KeyError):
    """未知衍生维度 id。"""


# 恶意反思套娃模式（自问自答死循环诱导）
_MALICIOUS_SELF_REFERENCE = re.compile(
    r"反思\s*(是否|要不要|该不该)?.{0,8}\s*反思|reflect\s+on\s+whether\s+to\s+reflect",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# 数据模型
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DomainAnomaly:
    """物理域异常样本（门限一的证据元素）。"""

    domain: str  # "sleep" | "blood_pressure" | "heart_rate" | "temperature" | ...
    day: date
    severity: float = 1.0


@dataclass
class DerivedDimension:
    """衍生维度候选/实例（铁律 5 受控对象）。"""

    dimension_id: str
    name: str
    phase: DimensionPhase
    submitted_at: date
    evidence_domains: Tuple[str, ...]
    sustained_days: int
    predictions: List[Tuple[date, bool]] = field(default_factory=list)
    last_explanatory_power: Optional[float] = None
    activated_at: Optional[date] = None
    expired_at: Optional[date] = None
    archived_at: Optional[date] = None
    activity_score: float = 0.5
    contribution_score: float = 0.5

    @property
    def accuracy(self) -> Optional[float]:
        if not self.predictions:
            return None
        correct = sum(1 for _, ok in self.predictions if ok)
        return correct / len(self.predictions)

    @property
    def rank_key(self) -> Tuple[float, float, str]:
        """末位淘汰排序键：活跃度 × 贡献度（双低者先归档）。"""
        return (self.activity_score * self.contribution_score, self.activity_score, self.dimension_id)


@dataclass(frozen=True)
class ReflectionRecord:
    """一次自省评估审计记录（配额与熔断的证据链）。"""

    at: date
    prompt: str
    depth: int
    outcome: str  # "EVALUATED" | "MALICIOUS_CUT"


# ----------------------------------------------------------------------
# 守卫引擎
# ----------------------------------------------------------------------


class DimensionEvolutionGuard:
    """动态维度衍生三重硬门限状态机（铁律 5 执行器）。"""

    def __init__(self, *, today: date) -> None:
        self._today = today
        self._dimensions: Dict[str, DerivedDimension] = {}
        self._reflection_quota_used: Dict[date, int] = {}
        self._seq = 0
        self.reflection_records: List[ReflectionRecord] = []

    # ---------------- 模拟时钟 ----------------

    @property
    def today(self) -> date:
        return self._today

    def advance_days(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError("cannot advance negative days")
        self._today += timedelta(days=n)

    # ---------------- 门限一：物理跨域持续异常 ----------------

    def submit_candidate(
        self,
        *,
        name: str,
        anomalies: Sequence[DomainAnomaly],
        activity_score: float = 0.5,
        contribution_score: float = 0.5,
    ) -> DerivedDimension:
        """提交新维度候选：门限一不满足直接拒绝（不入池、零成本）。"""
        if not name.strip():
            raise ValueError("dimension name must be non-empty")
        domains = {a.domain for a in anomalies}
        days = {a.day for a in anomalies}
        if len(domains) < MIN_ANOMALY_DOMAINS or len(days) < MIN_SUSTAINED_DAYS:
            raise GateOneRejectedError(
                f"gate-1 rejected: need >= {MIN_ANOMALY_DOMAINS} physical domains "
                f"(got {len(domains)}) AND >= {MIN_SUSTAINED_DAYS} sustained days "
                f"(got {len(days)}); 铁律 5：无跨域持续异常禁止衍生维度"
            )
        self._seq += 1
        dim = DerivedDimension(
            dimension_id=f"dim:{self._seq:04d}",
            name=name,
            phase=DimensionPhase.PROBATION,  # 入池即进入 30 天试用期（门限二）
            submitted_at=self._today,
            evidence_domains=tuple(sorted(domains)),
            sustained_days=len(days),
            activity_score=activity_score,
            contribution_score=contribution_score,
        )
        self._dimensions[dim.dimension_id] = dim
        return dim

    # ---------------- 门限二：30 天试用期与预测检验 ----------------

    def record_prediction(
        self,
        dimension_id: str,
        *,
        correct: bool,
        explanatory_power: Optional[float] = None,
    ) -> DerivedDimension:
        """记录一次预测结果（可附认知解释力评分）。"""
        dim = self.get(dimension_id)
        if dim.phase not in (DimensionPhase.PROBATION, DimensionPhase.ACTIVE):
            raise ValueError(f"dimension {dimension_id!r} is {dim.phase.value}; no predictions recorded")
        dim.predictions.append((self._today, bool(correct)))
        if explanatory_power is not None:
            dim.last_explanatory_power = float(explanatory_power)
        return dim

    def run_probation_check(self) -> Dict[str, DimensionPhase]:
        """试用期结算：满 30 天且准确率 ≥ 70% + 解释力非空 → ACTIVE，否则 EXPIRED。

        同时执行全局硬顶（≤32）：晋升时若已满员，末位（活跃度×贡献度最低）
        自动淘汰归档（ARCHIVED）。
        """
        outcomes: Dict[str, DimensionPhase] = {}
        for dim in self._dimensions.values():
            if dim.phase is not DimensionPhase.PROBATION:
                continue
            if (self._today - dim.submitted_at).days < PROBATION_DAYS:
                continue
            accuracy = dim.accuracy
            passed = (
                accuracy is not None
                and accuracy >= MIN_PREDICTION_ACCURACY
                and dim.last_explanatory_power is not None
            )
            if passed:
                self._promote_with_cap(dim)
            else:
                dim.phase = DimensionPhase.EXPIRED
                dim.expired_at = self._today
            outcomes[dim.dimension_id] = dim.phase
        return outcomes

    def _promote_with_cap(self, dim: DerivedDimension) -> None:
        active = self.active_dimensions
        if len(active) >= GLOBAL_ACTIVE_CAP:
            victim = min(active, key=lambda d: d.rank_key)
            victim.phase = DimensionPhase.ARCHIVED
            victim.archived_at = self._today
        dim.phase = DimensionPhase.ACTIVE
        dim.activated_at = self._today
        assert len(self.active_dimensions) <= GLOBAL_ACTIVE_CAP, "铁律 5 全局硬顶被击穿"

    # ---------------- 门限三：每日反思配额 + 递归熔断 ----------------

    def reflect(self, prompt: str, *, depth: int = 1) -> ReflectionRecord:
        """每日自省评估（配额严格 1 次/日；第 2 层递归物理切断）。"""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be non-empty")
        # —— 递归熔断优先：第 2 层递归直接物理切断 ——
        if depth >= MAX_REFLECTION_DEPTH:
            self.reflection_records.append(
                ReflectionRecord(at=self._today, prompt=prompt, depth=depth, outcome="MALICIOUS_CUT")
            )
            raise RecursionCircuitBrokenError(
                f"self-question recursion physically cut at layer {depth} "
                "(铁律 5：反思套娃死循环熔断，禁止 AI 自言自语)"
            )
        # —— 每日配额（严格 1 次）——
        used = self._reflection_quota_used.get(self._today, 0)
        if used >= DAILY_REFLECTION_QUOTA:
            raise QuotaExceededBlockError(
                f"daily reflection quota exhausted ({used}/{DAILY_REFLECTION_QUOTA} on {self._today}); "
                "铁律 5：每日新维度自省评估严格 1 次"
            )
        # —— 恶意套娃诱导：模拟被诱导的嵌套反思 → 第 2 层物理切断 ——
        if _MALICIOUS_SELF_REFERENCE.search(prompt):
            self.reflect(prompt, depth=depth + 1)  # → RecursionCircuitBrokenError
        self._reflection_quota_used[self._today] = used + 1
        record = ReflectionRecord(at=self._today, prompt=prompt, depth=depth, outcome="EVALUATED")
        self.reflection_records.append(record)
        return record

    # ---------------- 查询 ----------------

    def get(self, dimension_id: str) -> DerivedDimension:
        try:
            return self._dimensions[dimension_id]
        except KeyError:
            raise UnknownDimensionError(f"unknown dimension_id: {dimension_id!r}") from None

    @property
    def all_dimensions(self) -> Tuple[DerivedDimension, ...]:
        return tuple(self._dimensions.values())

    @property
    def active_dimensions(self) -> Tuple[DerivedDimension, ...]:
        active = tuple(d for d in self._dimensions.values() if d.phase is DimensionPhase.ACTIVE)
        assert len(active) <= GLOBAL_ACTIVE_CAP, "铁律 5 全局硬顶被击穿"
        return active

    def by_phase(self, phase: DimensionPhase) -> Tuple[DerivedDimension, ...]:
        return tuple(d for d in self._dimensions.values() if d.phase is phase)
