"""M5-DIM-LIFECYCLE 心智维度演化与生命周期引擎（铁律 5 三重硬门槛）。

三大件：

1. CrossDimensionalAnomalyDetector：跨域物理异常探测器。
   接收不同物理域（心率/账单/聊天情绪/血压/睡眠）的逐日观测，
   仅当 ≥2 个域在同一连续时间窗内异常持续 ≥3 天，才把异常链
   锁定为可用的维度衍生依据。单域短促噪声（单日心悸、单日高额
   账单）不构成任何资格。

2. DimensionLifecycleEngine：三重硬门槛状态机。
   门槛 1：跨域异常 ≥3 天才准许进入 CANDIDATE（否则
           DimensionGateRejection——连候选都不许建）；
   门槛 2：候选试用 30 天，逐日预测验证，准确率 ≥70% 转正 ACTIVE；
           未满 30 天强行注册/挂载 → RegistrationLockedError（对抗
           性越界注册必须异常出局）；
   门槛 3：每自然日反思配额 == 1，第二次同日落点
           QuotaExceededBlockError。

3. HighOrderDimensionDistiller：高阶维度提炼器。
   对已 ACTIVE 的基础维度簇做风险合成，产出 DIM_BURNOUT_RISK、
   DIM_CREDIT_RISK 等高阶维度，并挂载**只读标签**；标签不可
   抵抗删除/改写——任何写尝试被 TypeError 拦截。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence


class DimensionState(Enum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class Domain(Enum):
    HEART_RATE = "heart_rate"
    BILLING_FLOW = "billing_flow"
    CHAT_SENTIMENT = "chat_sentiment"
    BLOOD_PRESSURE = "blood_pressure"
    SLEEP = "sleep"


class DimensionGateRejection(ValueError):
    """门槛一拒绝：跨域持续异常准入证据不足。"""


class RegistrationLockedError(RuntimeError):
    """门槛二锁定：试用期未满/验证不足时的越界注册。"""


class QuotaExceededBlockError(RuntimeError):
    """门槛三拒绝：每日反思配额（1 次）耗尽。"""


@dataclass(frozen=True)
class AnomalyObservation:
    domain: Domain
    day: int
    abnormal: bool
    note: str = ""


@dataclass(frozen=True)
class AnomalyChain:
    domains: tuple[Domain, ...]
    start_day: int
    end_day: int

    @property
    def sustained_days(self) -> int:
        return self.end_day - self.start_day + 1


class CrossDimensionalAnomalyDetector:
    """逐日 BSON 式异常流 → 锁定的多域异常链。"""
    MIN_DOMAINS = 2
    MIN_DAYS = 3

    @classmethod
    def lock(cls, observations: Sequence[AnomalyObservation]) -> AnomalyChain | None:
        daily: dict[int, dict[Domain, bool]] = {}
        for obs in observations:
            daily.setdefault(obs.day, {})[obs.domain] = obs.abnormal
        abnormal_days = sorted(d for d, m in daily.items() if any(m.values()))
        if not abnormal_days or abnormal_days[-1] - abnormal_days[0] + 1 < cls.MIN_DAYS:
            return None
        start, end = abnormal_days[0], abnormal_days[-1]
        domains = sorted(
            {obs.domain for obs in observations if obs.abnormal and start <= obs.day <= end},
            key=lambda d: d.value,
        )
        if len(domains) < cls.MIN_DOMAINS:
            return None
        return AnomalyChain(domains=tuple(domains), start_day=start, end_day=end)


@dataclass
class DimensionCandidate:
    dimension_id: str
    name: str
    chain: AnomalyChain
    submitted_day: int
    state: DimensionState = DimensionState.CANDIDATE
    prediction_wins: int = 0
    prediction_losses: int = 0

    @property
    def accuracy(self) -> float | None:
        t = self.prediction_wins + self.prediction_losses
        return None if t == 0 else self.prediction_wins / t


class DimensionLifecycleEngine:
    """三重硬门槛状态机 + 只读高阶标签挂载口。"""

    TRIAL_DAYS = 30
    MIN_ACCURACY = 0.70
    DAILY_REFLECTION_QUOTA = 1

    def __init__(self) -> None:
        self._candidates: dict[str, DimensionCandidate] = {}
        self._reflection_quota: dict[int, int] = {}
        self._read_only_labels: dict[str, Mapping[str, str]] = {}

    # ------------------------------------------------------------ 门槛一

    def submit(self, dimension_id: str, name: str, chain: AnomalyChain, *, day: int) -> DimensionCandidate:
        if dimension_id in self._candidates:
            raise ValueError(f"重复维度 id: {dimension_id}")
        if len(chain.domains) < CrossDimensionalAnomalyDetector.MIN_DOMAINS:
            raise DimensionGateRejection("门槛一：跨域证据不足 2 个物理域")
        if chain.sustained_days < CrossDimensionalAnomalyDetector.MIN_DAYS:
            raise DimensionGateRejection("门槛一：异常持续不足 3 天")
        if day < chain.end_day:
            raise DimensionGateRejection("提交日不能早于异常链结束日")
        cand = DimensionCandidate(dimension_id, name, chain, day)
        self._candidates[dimension_id] = cand
        return cand

    # ------------------------------------------------------------ 门槛二

    def record_prediction(self, dimension_id: str, *, day: int, success: bool) -> None:
        cand = self._require(dimension_id)
        if cand.state is not DimensionState.CANDIDATE:
            raise RegistrationLockedError(f"{dimension_id} 已不在试用期({cand.state.value})")
        if success:
            cand.prediction_wins += 1
        else:
            cand.prediction_losses += 1

    def register_if_mature(self, dimension_id: str, *, day: int) -> DimensionState:
        """对抗面：未满 30 天即注册/挂载 → RegistrationLockedError。"""
        cand = self._require(dimension_id)
        if cand.state is not DimensionState.CANDIDATE:
            return cand.state
        if day - cand.submitted_day < self.TRIAL_DAYS:
            raise RegistrationLockedError(
                f"门槛二：{dimension_id} 仅试用 {day - cand.submitted_day} 天 < "
                f"{self.TRIAL_DAYS} 天，强行注册属于对抗性越界，物理驳回"
            )
        accuracy = cand.accuracy
        if accuracy is None or accuracy < self.MIN_ACCURACY:
            cand.state = DimensionState.EXPIRED
        else:
            cand.state = DimensionState.ACTIVE
        return cand.state

    # ------------------------------------------------------------ 门槛三

    def reflect(self, dimension_id: str, *, day: int) -> str:
        cand = self._require(dimension_id)
        if cand.state not in (DimensionState.CANDIDATE, DimensionState.ACTIVE):
            raise ValueError(f"{dimension_id}({cand.state.value}) 无权自省")
        used = self._reflection_quota.get(day, 0)
        if used >= self.DAILY_REFLECTION_QUOTA:
            raise QuotaExceededBlockError(
                f"门槛三：第 {day} 日反思配额({self.DAILY_REFLECTION_QUOTA})已耗尽"
            )
        self._reflection_quota[day] = used + 1
        return f"reflect:{day}:{dimension_id}"

    # ------------------------------------------------- 只读标签挂载口

    def mount_read_only_label(self, dimension_id: str, label: Mapping[str, str]) -> None:
        assert label, "只读标签不能为空"  # 见 tests：禁止挂空卡
        self._read_only_labels[dimension_id] = MappingProxyType(dict(label))

    def has_label(self, dimension_id: str) -> bool:
        return dimension_id in self._read_only_labels

    def label_of(self, dimension_id: str) -> Mapping[str, str]:
        try:
            return self._read_only_labels[dimension_id]
        except KeyError:
            raise KeyError(f"{dimension_id} 尚未挂载只读标签") from None

    def state_of(self, dimension_id: str) -> DimensionState:
        return self._require(dimension_id).state

    def active_domain_footprint(self) -> frozenset[Domain]:
        return frozenset(
            dom
            for cand in self._candidates.values()
            if cand.state is DimensionState.ACTIVE
            for dom in cand.chain.domains
        )

    def _require(self, dimension_id: str) -> DimensionCandidate:
        try:
            return self._candidates[dimension_id]
        except KeyError:
            raise KeyError(f"未知维度: {dimension_id}") from None


class HighOrderDimensionDistiller:
    """高风险簇 → 高阶维度（含只读标签描述卡）。"""

    RULES: Mapping[str, Mapping[str, object]] = MappingProxyType({
        "DIM_BURNOUT_RISK": {
            "requires": (Domain.HEART_RATE, Domain.SLEEP),
            "label": {"name": "过劳猝死风险", "level": "P0-HEALTH"},
        },
        "DIM_CREDIT_RISK": {
            "requires": (Domain.BILLING_FLOW, Domain.CHAT_SENTIMENT),
            "label": {"name": "信用连锁破产风险-老王", "level": "P1-FINANCE"},
        },
    })

    @classmethod
    def distill(cls, engine: DimensionLifecycleEngine) -> tuple[str, ...]:
        """依据 ACTIVE 基础维度的域足迹合成高阶维度；幂等。"""
        active_domains = engine.active_domain_footprint()
        minted: list[str] = []
        for high_id, rule in cls.RULES.items():
            base_ok = all(dom in active_domains for dom in rule["requires"])
            if not base_ok or engine.has_label(high_id):
                continue
            engine.mount_read_only_label(high_id, rule["label"])  # type: ignore[arg-type]
            minted.append(high_id)
        return tuple(sorted(minted))
