"""AIOS 3.0 心智维度演化与生命周期引擎（M5-002 / 宪法最高第五铁律工程化）。

本模块是"维度不爆炸"这条最高铁律的**唯一合法入口**，负责三件事：

1. **跨域物理异常探测**（``CrossDimensionalAnomalyDetector``）
   真实世界的异常体征从来不是单域的：深夜心率骤升往往同时伴随加班工时、
   咖啡因账单与聊天记录里的抱怨。探测器要求**跨域**（≥2 个物理域）且
   **连续 ≥3 天**的组合异常，才承认"体征锁定"成立——单域噪声、偶然一天
   的波动一律不予立案。

2. **三重硬门槛状态机**（``DimensionLifecycleStateMachine``）
   - 门槛一：物理跨域异常连续 3 天，未达即拒（``CrossDomainGateError``）；
   - 门槛二：候选维度进入 **30 天试用期**，且预测验证准确率 ≥70%
     （``TrialPeriodGateError`` / ``PredictionAccuracyGateError``）；
   - 门槛三：**每日最多 1 次反思配额**，第二次反思当日直接拒
     （``ReflectionQuotaExceededError``）。
   只有三关全过（且是按顺序过），维度才能 ``REGISTERED``。

3. **高阶维度提炼与只读挂载**（``HighOrderDimensionDistiller`` /
   ``DimensionOverlayOperator``）
   把低阶物理感知事实提炼成高阶认知维度（``DIM_BURNOUT_RISK`` 过劳猝死风险、
   ``DIM_CREDIT_RISK`` 商业信用破产、``DIM_PARENT_HEALTH`` 亲人健康关切），
   并以**只读标签**挂载到实体/关系/事件上——标签一旦挂上就不允许业务代码
   私自涂改，改标签等于改历史，直接抛 ``OverlayReadOnlyError``。

兼容承诺：本模块保留 M1 时代全部公开符号与方法签名（``AnomalyEvent`` /
``DimensionStatus`` / ``Entity`` / ``propose_dimension`` / ``reflect_and_validate`` /
``attempt_register`` / ``distill`` / ``overlay_dimension``），内部语义收紧但错误类型
仍继承 ``ValueError``，旧调用方无需改动。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from aios_core.contracts.refs import ObjectRef

UTC = _dt.timezone.utc


# ===========================================================================
# 异常类型：全部继承 ValueError，保证 M1 旧调用方（pytest.raises(ValueError)）兼容
# ===========================================================================
class CrossDomainGateError(ValueError):
    """门槛一未过：物理跨域异常未连续满 3 天。"""


class TrialPeriodGateError(ValueError):
    """门槛二未过：候选维度试用期不足 30 天。"""


class PredictionAccuracyGateError(ValueError):
    """门槛二未过：预测验证准确率不达标。"""


class ReflectionQuotaExceededError(ValueError):
    """门槛三未过：当日反思配额（每日 1 次）已用尽。"""


class OverlayReadOnlyError(ValueError):
    """只读挂载保护：高阶维度标签禁止任何形式的就地篡改。"""


class DimensionStateError(ValueError):
    """状态机非法跃迁（如对已注册维度重复立案）。"""


# ===========================================================================
# 1. 跨域物理异常探测器
# ===========================================================================
class AnomalyDomain(StrEnum):
    """物理域分类（与检索层 ``derive_dimension`` 的口径对齐）。"""

    HEALTH = "health"
    FINANCE = "finance"
    SOCIAL = "social"
    WORK = "work"
    BEHAVIOR = "behavior"
    UNKNOWN = "unknown"


_DOMAIN_ALIASES: Mapping[str, AnomalyDomain] = {
    # 生理/健康
    "heart_rate": AnomalyDomain.HEALTH,
    "hrv": AnomalyDomain.HEALTH,
    "sleep": AnomalyDomain.HEALTH,
    "biometrics": AnomalyDomain.HEALTH,
    "arrhythmia": AnomalyDomain.HEALTH,
    "health": AnomalyDomain.HEALTH,
    "medical": AnomalyDomain.HEALTH,
    # 财务
    "finance": AnomalyDomain.FINANCE,
    "transaction": AnomalyDomain.FINANCE,
    "bill": AnomalyDomain.FINANCE,
    "bank": AnomalyDomain.FINANCE,
    "loan": AnomalyDomain.FINANCE,
    "contract": AnomalyDomain.FINANCE,
    "receipt": AnomalyDomain.FINANCE,
    # 社交
    "chat": AnomalyDomain.SOCIAL,
    "call": AnomalyDomain.SOCIAL,
    "social": AnomalyDomain.SOCIAL,
    "message": AnomalyDomain.SOCIAL,
    # 工作
    "work_log": AnomalyDomain.WORK,
    "calendar": AnomalyDomain.WORK,
    "meeting": AnomalyDomain.WORK,
    "code": AnomalyDomain.WORK,
    "overtime": AnomalyDomain.WORK,
    "work": AnomalyDomain.WORK,
    # 行为
    "behavior": AnomalyDomain.BEHAVIOR,
    "location": AnomalyDomain.BEHAVIOR,
}


def normalize_domain(raw: Any) -> AnomalyDomain:
    """把来源标签/字符串归一化到物理域枚举（未知来源落到 UNKNOWN）。"""
    key = str(raw or "").strip().lower()
    if not key:
        return AnomalyDomain.UNKNOWN
    try:
        return AnomalyDomain(key)
    except ValueError:
        return _DOMAIN_ALIASES.get(key, AnomalyDomain.UNKNOWN)


@dataclass
class AnomalyEvent:
    """一条物理异常事件（保持 M1 的三位置参数签名不变）。"""

    timestamp: _dt.datetime
    domain: str
    description: str
    severity: float = 1.0
    evidence_ref: Optional[ObjectRef] = None

    @property
    def day(self) -> _dt.date:
        """事件所在自然日。"""
        return self.timestamp.date()

    @property
    def physical_domain(self) -> AnomalyDomain:
        """归一化物理域。"""
        return normalize_domain(self.domain)


@dataclass(frozen=True)
class AnomalyFinding:
    """跨域异常窗口的判定结论（可审计、可回放）。"""

    is_locked: bool
    reason: str
    required_days: int
    min_domains: int
    per_day_min_domains: int
    days: Tuple[_dt.date, ...] = ()
    domains: FrozenSet[AnomalyDomain] = frozenset()
    per_day_domains: Mapping[_dt.date, FrozenSet[AnomalyDomain]] = field(default_factory=dict)
    evidence_refs: Tuple[ObjectRef, ...] = ()
    event_count: int = 0

    def describe(self) -> str:
        """一行式人话结论（供体检报告与审计日志使用）。"""
        if not self.is_locked:
            return f"未锁定：{self.reason}"
        day_span = f"{self.days[0]}~{self.days[-1]}" if self.days else "-"
        return (
            f"跨域锁定成立：{len(self.days)} 天（{day_span}）"
            f"× {len(self.domains)} 域 {sorted(d.value for d in self.domains)}"
        )


class CrossDimensionalAnomalyDetector:
    """跨域物理异常探测器（心率 + 账单 + 聊天 + 工时）。

    判定口径与宪法第五铁律一致：
    - **连续性**：以"最新异常日"为锚，向前要求 ``required_days`` 个自然日**逐日有异常**；
    - **跨域性**：窗口内至少 ``min_domains`` 个物理域被点亮；
    - **强度门（严格档）**：``per_day_min_domains`` 要求"每一天都不是单域孤证"，
      这是 ``detect_cross_domain_lock`` 的默认档位，用于真正的体征锁定立案。
    """

    def __init__(
        self,
        *,
        required_days: int = 3,
        min_domains: int = 2,
        per_day_min_domains: int = 1,
    ) -> None:
        self.events: List[AnomalyEvent] = []
        self.required_days = required_days
        self.min_domains = min_domains
        self.per_day_min_domains = per_day_min_domains
        self._ingested_observation_ids: Set[str] = set()

    # ---- 事件灌注 --------------------------------------------------------
    def add_event(self, event: AnomalyEvent) -> AnomalyEvent:
        """登记一条异常事件（M1 旧接口，保留）。"""
        self.events.append(event)
        self.events.sort(key=lambda e: e.timestamp)
        return event

    def record(
        self,
        *,
        domain: Any,
        timestamp: _dt.datetime,
        description: str = "",
        severity: float = 1.0,
        evidence_ref: Optional[ObjectRef] = None,
    ) -> AnomalyEvent:
        """语义化登记接口（推荐路径）。"""
        return self.add_event(
            AnomalyEvent(
                timestamp=timestamp,
                domain=str(domain),
                description=description,
                severity=severity,
                evidence_ref=evidence_ref,
            )
        )

    def ingest_observations(self, payloads: Iterable[Mapping[str, Any]]) -> int:
        """从真实世界载荷批量灌注异常事件。

        观测对象（``object_type == "observation"``）按 ``source_kind`` 映射到物理域，
        事件时间取 ``occurred.start``（缺失时回退 ``learned_at``），证据指针取
        ``ObjectRef(object_id, revision)`` —— 提炼出的高阶维度因此**天生带着
        可回指的物证**，而不是一句空话。幂等：同一 object_id 只会被吞入一次。
        """
        ingested = 0
        for payload in payloads:
            if str(payload.get("object_type", "")) != "observation":
                continue
            object_id = str(payload.get("object_id", ""))
            revision = payload.get("revision")
            if not object_id or not isinstance(revision, int):
                continue
            if object_id in self._ingested_observation_ids:
                continue
            occurred = payload.get("occurred") or {}
            ts_raw = occurred.get("start") if isinstance(occurred, dict) else None
            ts = _coerce_datetime(ts_raw) or _coerce_datetime(payload.get("learned_at"))
            if ts is None:
                continue
            value = payload.get("value")
            description = value if isinstance(value, str) else str(value)
            self.record(
                domain=payload.get("source_kind", ""),
                timestamp=ts,
                description=description,
                severity=1.0,
                evidence_ref=ObjectRef(object_id=object_id, revision=revision),
            )
            self._ingested_observation_ids.add(object_id)
            ingested += 1
        return ingested

    # ---- 判定 ------------------------------------------------------------
    def detect_window(
        self,
        current_time: _dt.datetime,
        *,
        required_days: int = 3,
        min_domains: int = 2,
        per_day_min_domains: int = 1,
    ) -> AnomalyFinding:
        """核心判定：返回结构化的跨域异常窗口结论。"""
        recent = [
            e
            for e in self.events
            if 0 <= (current_time - e.timestamp).total_seconds() and (current_time - e.timestamp).days <= required_days
        ]
        if not recent:
            return AnomalyFinding(
                is_locked=False,
                reason="窗口内没有任何异常事件",
                required_days=required_days,
                min_domains=min_domains,
                per_day_min_domains=per_day_min_domains,
            )

        per_day: Dict[_dt.date, Set[AnomalyDomain]] = {}
        for event in recent:
            per_day.setdefault(event.day, set()).add(event.physical_domain)

        anchor_day = max(per_day)
        window_days = tuple(anchor_day - _dt.timedelta(days=offset) for offset in range(required_days - 1, -1, -1))
        missing = [day for day in window_days if day not in per_day]
        domains: Set[AnomalyDomain] = set()
        for day in window_days:
            domains |= per_day.get(day, set())

        evidence_refs = tuple(
            dict.fromkeys(
                e.evidence_ref
                for e in recent
                if e.day in window_days and e.evidence_ref is not None
            )
        )
        base = dict(
            required_days=required_days,
            min_domains=min_domains,
            per_day_min_domains=per_day_min_domains,
            days=window_days if not missing else tuple(sorted(per_day)),
            domains=frozenset(domains),
            per_day_domains={day: frozenset(per_day.get(day, set())) for day in window_days},
            evidence_refs=evidence_refs,
            event_count=len(recent),
        )

        if missing:
            return AnomalyFinding(
                is_locked=False,
                reason=f"连续 {required_days} 天要求未满足，缺口 {[str(d) for d in missing]}",
                **base,
            )
        if len(domains) < min_domains:
            return AnomalyFinding(
                is_locked=False,
                reason=f"窗口内仅 {len(domains)} 个物理域，低于跨域门限 {min_domains}",
                **base,
            )
        thin_days = [day for day in window_days if len(per_day.get(day, set())) < per_day_min_domains]
        if thin_days:
            return AnomalyFinding(
                is_locked=False,
                reason=f"单域孤证日 {[str(d) for d in thin_days]} 不足 {per_day_min_domains} 域",
                **base,
            )
        return AnomalyFinding(is_locked=True, reason="跨域连续异常成立", **base)

    def detect_continuous_anomaly(
        self,
        current_time: _dt.datetime,
        required_days: int = 3,
    ) -> bool:
        """M1 兼容入口：连续 ``required_days`` 天 + 跨 ≥2 域即视为成立。"""
        return self.detect_window(
            current_time,
            required_days=required_days,
            min_domains=2,
            per_day_min_domains=1,
        ).is_locked

    def detect_cross_domain_lock(
        self,
        current_time: _dt.datetime,
        *,
        required_days: int = 3,
        min_domains: int = 2,
        per_day_min_domains: int = 2,
    ) -> AnomalyFinding:
        """严格档：每一天都必须有 ≥2 个物理域佐证，才是真正"跨域体征锁定"。"""
        return self.detect_window(
            current_time,
            required_days=required_days,
            min_domains=min_domains,
            per_day_min_domains=per_day_min_domains,
        )

    def audit(self) -> Dict[str, Any]:
        """探测器审计切片（事件规模、域分布、证据覆盖率）。"""
        with_evidence = sum(1 for e in self.events if e.evidence_ref is not None)
        by_domain: Dict[str, int] = {}
        for event in self.events:
            by_domain[event.physical_domain.value] = by_domain.get(event.physical_domain.value, 0) + 1
        return {
            "events": len(self.events),
            "domains": by_domain,
            "evidence_coverage": (with_evidence / len(self.events)) if self.events else 0.0,
            "required_days": self.required_days,
            "min_domains": self.min_domains,
        }


def _coerce_datetime(raw: Any) -> Optional[_dt.datetime]:
    """把载荷里的时间字段（ISO 字符串 / datetime）统一为 aware UTC。"""
    if raw is None:
        return None
    if isinstance(raw, _dt.datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, str):
        try:
            parsed = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


# ===========================================================================
# 2. 三重硬门槛生命周期状态机
# ===========================================================================
class DimensionStatus(Enum):
    UNINIT = auto()
    PROPOSED = auto()
    CANDIDATE = auto()  # 30 天试用期
    REGISTERED = auto()
    REJECTED = auto()
    EXPIRED = auto()  # 试用期满仍未验证通过


@dataclass
class DimensionState:
    """维度生命周期状态（含三关证据链与预测验证账本）。"""

    name: str
    status: DimensionStatus = DimensionStatus.UNINIT
    proposal_time: Optional[_dt.datetime] = None
    last_reflection_time: Optional[_dt.date] = None
    reflection_count_today: int = 0
    prediction_attempts: int = 0
    predictions_validated: int = 0
    high_order_key: Optional[str] = None
    label: str = ""
    evidence_refs: List[ObjectRef] = field(default_factory=list)
    finding_summary: str = ""
    registered_at: Optional[_dt.datetime] = None
    expired_at: Optional[_dt.datetime] = None
    rejection_reason: str = ""

    @property
    def prediction_accuracy(self) -> float:
        """预测命中率（无预测记录时为 0.0，绝不用"1.0 空账"粉饰）。"""
        if self.prediction_attempts <= 0:
            return 0.0
        return self.predictions_validated / self.prediction_attempts

    def trial_days(self, current_time: _dt.datetime) -> int:
        """已走过的试用天数（未立案返回 0）。"""
        if self.proposal_time is None:
            return 0
        return max(0, (current_time - self.proposal_time).days)


class DimensionLifecycleStateMachine:
    """三重硬门槛状态机（宪法最高第五铁律的唯一入口）。"""

    TRIAL_DAYS: int = 30
    PREDICTION_ACCURACY_FLOOR: float = 0.70
    REFLECTION_QUOTA_PER_DAY: int = 1

    def __init__(self, *, detector: Optional[CrossDimensionalAnomalyDetector] = None) -> None:
        self.dimensions: Dict[str, DimensionState] = {}
        self.detector = detector or CrossDimensionalAnomalyDetector()
        self.registration_log: List[Tuple[str, _dt.datetime]] = []
        self.expiry_log: List[Tuple[str, _dt.datetime, str]] = []
        #: 全局反思账本（自然日 → 当日已消耗配额），每实例独立，避免跨实例串账
        self._reflection_ledger: Dict[_dt.date, int] = {}

    # ---- 门槛一：物理跨域异常连续 3 天 -----------------------------------
    def propose_dimension(
        self,
        name: str,
        current_time: _dt.datetime,
        *,
        evidence_refs: Sequence[ObjectRef] = (),
        label: str = "",
        high_order_key: Optional[str] = None,
        finding: Optional[AnomalyFinding] = None,
        strict: bool = False,
    ) -> DimensionState:
        """立案候选维度。门槛一不过即拒，绝不"先建了再说"。"""
        existing = self.dimensions.get(name)
        if existing is not None and existing.status in (
            DimensionStatus.CANDIDATE,
            DimensionStatus.REGISTERED,
        ):
            raise DimensionStateError(
                f"Dimension '{name}' already exists in status {existing.status.name}"
            )

        if finding is None:
            finding = (
                self.detector.detect_cross_domain_lock(current_time)
                if strict
                else self.detector.detect_window(current_time, required_days=3, min_domains=2, per_day_min_domains=1)
            )
        if not finding.is_locked:
            raise CrossDomainGateError(
                f"Cannot propose dimension '{name}'. "
                f"Threshold 1 (3-day physical cross-domain anomaly) not met: {finding.reason}"
            )

        state = DimensionState(
            name=name,
            status=DimensionStatus.CANDIDATE,
            proposal_time=current_time,
            high_order_key=high_order_key,
            label=label,
            evidence_refs=list(evidence_refs) or list(finding.evidence_refs),
            finding_summary=finding.describe(),
        )
        self.dimensions[name] = state
        return state

    # ---- 门槛三：每日 1 次反思配额 ---------------------------------------
    def quota_used(self, day: _dt.date) -> int:
        """查询某日已消耗的反思配额（按全局反思账本口径）。"""
        return self._reflection_ledger.get(day, 0)

    def quota_remaining(self, day: _dt.date) -> int:
        """查询某日剩余反思配额。"""
        return max(0, self.REFLECTION_QUOTA_PER_DAY - self.quota_used(day))

    def reflect_and_validate(
        self,
        name: str,
        current_time: _dt.datetime,
        successful_prediction: bool,
    ) -> DimensionState:
        """每日至多一次的自省与预测验证（门槛三 + 门槛二证据累积）。"""
        state = self._require(name)
        if state.status != DimensionStatus.CANDIDATE:
            raise DimensionStateError(f"Dimension '{name}' is not in CANDIDATE status.")

        current_date = current_time.date()
        if state.last_reflection_time == current_date:
            if state.reflection_count_today >= self.REFLECTION_QUOTA_PER_DAY:
                raise ReflectionQuotaExceededError(
                    f"Threshold 3 (Daily reflection quota of 1) exceeded for '{name}' on {current_date}."
                )
            state.reflection_count_today += 1
        else:
            state.last_reflection_time = current_date
            state.reflection_count_today = 1
        self._reflection_ledger[current_date] = self.quota_used(current_date) + 1

        state.prediction_attempts += 1
        if successful_prediction:
            state.predictions_validated += 1
        return state

    # ---- 门槛二：30 天试用期 + 预测准确率 --------------------------------
    def attempt_register(self, name: str, current_time: _dt.datetime) -> DimensionState:
        """试用期满且预测验证达标，才允许正式注册。"""
        state = self._require(name)
        if state.status != DimensionStatus.CANDIDATE:
            raise DimensionStateError(f"Dimension '{name}' is not in CANDIDATE status.")

        days_in_trial = state.trial_days(current_time)
        if days_in_trial < self.TRIAL_DAYS:
            raise TrialPeriodGateError(
                f"Cannot register dimension '{name}'. "
                f"Threshold 2 (30-day trial period) not met. Current days: {days_in_trial}"
            )
        if state.predictions_validated <= 0:
            raise PredictionAccuracyGateError(
                f"Cannot register dimension '{name}'. "
                f"Threshold 2 (Prediction validation) not met."
            )
        if state.prediction_accuracy < self.PREDICTION_ACCURACY_FLOOR:
            raise PredictionAccuracyGateError(
                f"Cannot register dimension '{name}'. "
                f"Threshold 2 (Prediction validation) not met: "
                f"accuracy {state.prediction_accuracy:.0%} < {self.PREDICTION_ACCURACY_FLOOR:.0%}."
            )

        state.status = DimensionStatus.REGISTERED
        state.registered_at = current_time
        self.registration_log.append((name, current_time))
        return state

    def expire(self, name: str, current_time: _dt.datetime, *, reason: str = "trial_period_elapsed") -> DimensionState:
        """试用期满仍未通过验证的候选维度作废（防止僵尸维度长期占位）。"""
        state = self._require(name)
        if state.status != DimensionStatus.CANDIDATE:
            raise DimensionStateError(f"Dimension '{name}' is not in CANDIDATE status.")
        if state.trial_days(current_time) < self.TRIAL_DAYS:
            raise TrialPeriodGateError(
                f"Cannot expire dimension '{name}': Threshold 2 (30-day trial period) not elapsed."
            )
        state.status = DimensionStatus.EXPIRED
        state.expired_at = current_time
        state.rejection_reason = reason
        self.expiry_log.append((name, current_time, reason))
        return state

    def reject(self, name: str, current_time: _dt.datetime, *, reason: str) -> DimensionState:
        """人工/规则否决一个候选维度（留档原因，可审计）。"""
        state = self._require(name)
        state.status = DimensionStatus.REJECTED
        state.expired_at = current_time
        state.rejection_reason = reason
        return state

    # ---- 对外审计 --------------------------------------------------------
    def gate_status(self, name: str, current_time: _dt.datetime) -> Dict[str, Any]:
        """三关体检切片（用于看板与战训体检报告）。"""
        state = self._require(name)
        return {
            "name": name,
            "status": state.status.name,
            "gate1_cross_domain": bool(state.evidence_refs) or bool(state.finding_summary),
            "gate1_summary": state.finding_summary,
            "gate2_trial_days": state.trial_days(current_time),
            "gate2_trial_required": self.TRIAL_DAYS,
            "gate2_prediction_accuracy": state.prediction_accuracy,
            "gate2_prediction_floor": self.PREDICTION_ACCURACY_FLOOR,
            "gate3_quota_today": state.reflection_count_today,
            "gate3_quota_limit": self.REFLECTION_QUOTA_PER_DAY,
        }

    def audit(self) -> Dict[str, Any]:
        """状态机全局审计：各状态维度数量、注册/作废流水。"""
        by_status: Dict[str, int] = {}
        for state in self.dimensions.values():
            by_status[state.status.name] = by_status.get(state.status.name, 0) + 1
        return {
            "dimensions": len(self.dimensions),
            "by_status": by_status,
            "registered": [name for name, _ in self.registration_log],
            "expired": [name for name, _, _ in self.expiry_log],
            "reflection_days": len(self._reflection_ledger),
        }

    # ---- 内部 ------------------------------------------------------------
    def _require(self, name: str) -> DimensionState:
        if name not in self.dimensions:
            raise DimensionStateError(f"Dimension '{name}' not found.")
        return self.dimensions[name]


# ===========================================================================
# 3. 高阶维度提炼器（高阶维度 + 只读标签）
# ===========================================================================
@dataclass(frozen=True)
class DimensionRecipe:
    """高阶维度的提炼配方：语义键、中文标签、需点亮的物理域。"""

    key: str
    label: str
    description: str
    required_domains: FrozenSet[AnomalyDomain]
    advisory: str = ""


DIM_BURNOUT_RISK = "DIM_BURNOUT_RISK"
DIM_CREDIT_RISK = "DIM_CREDIT_RISK"
DIM_PARENT_HEALTH = "DIM_PARENT_HEALTH"

DIMENSION_RECIPES: Mapping[str, DimensionRecipe] = MappingProxyType(
    {
        DIM_BURNOUT_RISK: DimensionRecipe(
            key=DIM_BURNOUT_RISK,
            label="身心衰竭指数（过劳猝死风险）",
            description="深夜心率骤升 + 咖啡因/异常账单 + 加班聊天抱怨的跨域组合异常",
            required_domains=frozenset({AnomalyDomain.HEALTH, AnomalyDomain.WORK, AnomalyDomain.FINANCE}),
            advisory="连续 3 晚深夜心率为跨域锁定信号，优先安排强制停工与心内科复查",
        ),
        DIM_CREDIT_RISK: DimensionRecipe(
            key=DIM_CREDIT_RISK,
            label="商业信用破产风险",
            description="大额资金流出 + 对方口头承诺拖延 + 法院/判决信息的跨域组合异常",
            required_domains=frozenset({AnomalyDomain.FINANCE, AnomalyDomain.SOCIAL}),
            advisory="资金追偿窗口有限，建议同步启动法律动作并冻结追加出借",
        ),
        DIM_PARENT_HEALTH: DimensionRecipe(
            key=DIM_PARENT_HEALTH,
            label="亲人健康关切（老寒腿/受凉）",
            description="母亲膝关节疼痛主诉 + 既往笨重家电闲置教训的跨域组合异常",
            required_domains=frozenset({AnomalyDomain.HEALTH, AnomalyDomain.SOCIAL}),
            advisory="礼品选择应遵循轻便免水洗原则，避免加重腰部与膝盖负担",
        ),
    }
)


class HighOrderDimensionDistiller:
    """从低阶物理感知事实提炼高阶认知维度。"""

    def __init__(self, state_machine: DimensionLifecycleStateMachine) -> None:
        self.state_machine = state_machine
        self.distilled: List[str] = []

    def recipe(self, name: str) -> Optional[DimensionRecipe]:
        """取配方（兼容以维度名或语义键调用）。"""
        return DIMENSION_RECIPES.get(name)

    def distill(
        self,
        name: str,
        current_time: _dt.datetime,
    ) -> Optional[DimensionState]:
        """M1 兼容入口：门槛一不过时返回 ``None``（不抛错）。"""
        try:
            return self.distill_strict(name, current_time, strict=False)
        except (CrossDomainGateError, DimensionStateError):
            return None

    def distill_strict(
        self,
        name: str,
        current_time: _dt.datetime,
        *,
        evidence_refs: Sequence[ObjectRef] = (),
        finding: Optional[AnomalyFinding] = None,
        strict: bool = True,
    ) -> DimensionState:
        """严格提炼：门槛一不过立即抛 ``CrossDomainGateError``。"""
        recipe = self.recipe(name)
        if recipe is None:
            raise DimensionStateError(f"Unknown high-order dimension key: {name}")
        if finding is None:
            finding = (
                self.state_machine.detector.detect_cross_domain_lock(current_time)
                if strict
                else self.state_machine.detector.detect_window(current_time)
            )
        if finding.is_locked:
            missing_domains = recipe.required_domains - set(finding.domains)
            if missing_domains:
                raise CrossDomainGateError(
                    f"Cannot distill '{name}'. "
                    f"Threshold 1 (3-day physical cross-domain anomaly) not met: "
                    f"recipe requires domains {sorted(d.value for d in recipe.required_domains)}, "
                    f"missing {sorted(d.value for d in missing_domains)}"
                )
        state = self.state_machine.propose_dimension(
            recipe.key,
            current_time,
            evidence_refs=evidence_refs,
            label=recipe.label,
            high_order_key=recipe.key,
            finding=finding,
            strict=strict,
        )
        if recipe.key not in self.distilled:
            self.distilled.append(recipe.key)
        return state

    def distill_from_world(
        self,
        payloads: Iterable[Mapping[str, Any]],
        name: str,
        current_time: _dt.datetime,
        *,
        strict: bool = True,
    ) -> DimensionState:
        """从真实世界观测载荷提炼高阶维度（证据指针全部来自真实物证）。"""
        detector = self.state_machine.detector
        detector.ingest_observations(payloads)
        return self.distill_strict(name, current_time, strict=strict)


# ===========================================================================
# 4. 只读维度标签挂载
# ===========================================================================
@dataclass
class Entity:
    """M1 兼容实体（``tags`` 保留可写语义，供旧调用方迁移期使用）。"""

    id: str
    tags: Set[str] = field(default_factory=set)


@dataclass(frozen=True)
class OverlayTag:
    """一条只读高阶维度标签。"""

    dimension_key: str
    label: str
    target_id: str
    target_kind: str
    mounted_at: _dt.datetime
    evidence_refs: Tuple[ObjectRef, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        """序列化切片（看板/体检报告用）。"""
        return {
            "dimension_key": self.dimension_key,
            "label": self.label,
            "target_id": self.target_id,
            "target_kind": self.target_kind,
            "mounted_at": self.mounted_at.isoformat(),
            "evidence_refs": [ref.object_id for ref in self.evidence_refs],
        }


class ReadOnlyOverlay:
    """只读标签视图：挂载后禁止任何就地写入，违者抛 ``OverlayReadOnlyError``。"""

    def __init__(self, target_id: str, target_kind: str, tags: Mapping[str, OverlayTag]) -> None:
        self.target_id = target_id
        self.target_kind = target_kind
        self._tags: Mapping[str, OverlayTag] = MappingProxyType(dict(tags))

    @property
    def tags(self) -> Mapping[str, OverlayTag]:
        """只读标签映射（``MappingProxyType``，写操作直接 TypeError/自定义异常）。"""
        return self._tags

    def keys(self) -> FrozenSet[str]:
        """已挂载的维度键集合。"""
        return frozenset(self._tags)

    def labels(self) -> Tuple[str, ...]:
        """已挂载维度的中文标签序列。"""
        return tuple(tag.label for tag in self._tags.values())

    def has(self, dimension_key: str) -> bool:
        """是否已挂载某维度。"""
        return dimension_key in self._tags

    def get(self, dimension_key: str) -> Optional[OverlayTag]:
        """取某维度标签。"""
        return self._tags.get(dimension_key)

    def evidence_refs(self, dimension_key: str) -> Tuple[ObjectRef, ...]:
        """取某维度标签背后的物证指针。"""
        tag = self._tags.get(dimension_key)
        return tag.evidence_refs if tag else ()

    # ---- 任何写意图一律拦截（改标签 = 改历史） ---------------------------
    def add(self, *_: Any, **__: Any) -> None:
        """禁止新增标签。"""
        raise OverlayReadOnlyError(
            f"overlay tags on {self.target_kind}:{self.target_id} are read-only; re-distill instead of patching"
        )

    def discard(self, *_: Any, **__: Any) -> None:
        """禁止摘除标签。"""
        raise OverlayReadOnlyError(
            f"overlay tags on {self.target_kind}:{self.target_id} are read-only; removal is not permitted"
        )

    def clear(self, *_: Any, **__: Any) -> None:
        """禁止清空标签。"""
        raise OverlayReadOnlyError(
            f"overlay tags on {self.target_kind}:{self.target_id} are read-only; clearing is not permitted"
        )

    def update(self, *_: Any, **__: Any) -> None:
        """禁止批量覆盖标签。"""
        raise OverlayReadOnlyError(
            f"overlay tags on {self.target_kind}:{self.target_id} are read-only; bulk update is not permitted"
        )

    def __setitem__(self, *_: Any) -> None:
        raise OverlayReadOnlyError("overlay mapping is read-only")


class DimensionOverlayOperator:
    """把已注册的高阶维度以只读标签挂载到实体/关系/事件上。"""

    VALID_KINDS = ("entity", "relation", "event")

    def __init__(self, *, state_machine: Optional[DimensionLifecycleStateMachine] = None) -> None:
        self.state_machine = state_machine
        self._overlays: Dict[Tuple[str, str], Dict[str, OverlayTag]] = {}

    # ---- M1 兼容入口 -----------------------------------------------------
    def overlay_dimension(self, entity: Entity, dimension: DimensionState) -> Entity:
        """M1 旧接口：把已注册维度写入实体的可写标签集合（迁移期兼容）。"""
        self._require_registered(dimension)
        entity.tags.add(dimension.name)
        return entity

    # ---- 只读挂载（推荐路径） -------------------------------------------
    def mount(
        self,
        *,
        target_id: str,
        target_kind: str,
        dimension: DimensionState,
        at: Optional[_dt.datetime] = None,
    ) -> ReadOnlyOverlay:
        """挂载只读标签；未注册（或已作废）维度一律拒绝。"""
        if target_kind not in self.VALID_KINDS:
            raise DimensionStateError(f"Unsupported overlay target kind: {target_kind}")
        self._require_registered(dimension)
        key = (target_kind, target_id)
        bucket = self._overlays.setdefault(key, {})
        bucket[dimension.name] = OverlayTag(
            dimension_key=dimension.name,
            label=dimension.label or self._default_label(dimension),
            target_id=target_id,
            target_kind=target_kind,
            mounted_at=at or _dt.datetime.now(UTC),
            evidence_refs=tuple(dimension.evidence_refs),
        )
        return ReadOnlyOverlay(target_id, target_kind, bucket)

    def overlay(self, target_id: str, target_kind: str = "entity") -> ReadOnlyOverlay:
        """读取某个目标上的只读标签视图。"""
        if target_kind not in self.VALID_KINDS:
            raise DimensionStateError(f"Unsupported overlay target kind: {target_kind}")
        return ReadOnlyOverlay(target_id, target_kind, self._overlays.get((target_kind, target_id), {}))

    def tags_of(self, target_id: str, target_kind: str = "entity") -> FrozenSet[str]:
        """目标已挂载的维度键集合。"""
        return frozenset(self._overlays.get((target_kind, target_id), {}))

    def audit(self) -> Dict[str, Any]:
        """挂载审计：目标数、标签数、只读语义版本。"""
        return {
            "targets": len(self._overlays),
            "tags": sum(len(bucket) for bucket in self._overlays.values()),
            "read_only": True,
            "valid_kinds": list(self.VALID_KINDS),
        }

    # ---- 内部 ------------------------------------------------------------
    @staticmethod
    def _default_label(dimension: DimensionState) -> str:
        recipe = DIMENSION_RECIPES.get(dimension.name)
        return recipe.label if recipe else dimension.name

    @staticmethod
    def _require_registered(dimension: DimensionState) -> None:
        if dimension.status != DimensionStatus.REGISTERED:
            raise DimensionStateError(f"Cannot overlay unregistered dimension '{dimension.name}'.")
