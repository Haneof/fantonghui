import datetime
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set

class DimensionStatus(Enum):
    UNINIT = auto()
    PROPOSED = auto()
    CANDIDATE = auto() # Under 30 days trial
    REGISTERED = auto()
    REJECTED = auto()

@dataclass
class AnomalyEvent:
    timestamp: datetime.datetime
    domain: str
    description: str

class CrossDimensionalAnomalyDetector:
    def __init__(self):
        self.events: List[AnomalyEvent] = []

    def add_event(self, event: AnomalyEvent):
        self.events.append(event)

    def detect_continuous_anomaly(self, current_time: datetime.datetime, required_days: int = 3) -> bool:
        """
        Detect if there's continuous cross-domain physical anomaly for at least `required_days`.
        We assume we need events on at least `required_days` distinct days within the last `required_days` days,
        and multiple domains involved.
        """
        if not self.events:
            return False
        
        recent_events = [e for e in self.events if (current_time - e.timestamp).days <= required_days and (current_time - e.timestamp).total_seconds() >= 0]
        
        if not recent_events:
            return False

        active_days = set()
        domains = set()
        for e in recent_events:
            active_days.add(e.timestamp.date())
            domains.add(e.domain)

        if len(active_days) >= required_days and len(domains) >= 2:
            return True
            
        return False

@dataclass
class DimensionState:
    name: str
    status: DimensionStatus = DimensionStatus.UNINIT
    proposal_time: Optional[datetime.datetime] = None
    last_reflection_time: Optional[datetime.date] = None
    reflection_count_today: int = 0
    predictions_validated: int = 0
    evidence: List[str] = field(default_factory=list)  # M5-002：蒸馏依据（低阶物理事实描述）
    
class DimensionLifecycleStateMachine:
    def __init__(self):
        self.dimensions: Dict[str, DimensionState] = {}
        self.detector = CrossDimensionalAnomalyDetector()

    def propose_dimension(self, name: str, current_time: datetime.datetime):
        if not self.detector.detect_continuous_anomaly(current_time, 3):
            raise ValueError(f"Cannot propose dimension '{name}'. Threshold 1 (3-day physical cross-domain anomaly) not met.")
        
        self.dimensions[name] = DimensionState(
            name=name,
            status=DimensionStatus.CANDIDATE,
            proposal_time=current_time
        )

    def reflect_and_validate(self, name: str, current_time: datetime.datetime, successful_prediction: bool):
        if name not in self.dimensions:
            raise ValueError(f"Dimension '{name}' not found.")
            
        state = self.dimensions[name]
        
        if state.status != DimensionStatus.CANDIDATE:
            raise ValueError(f"Dimension '{name}' is not in CANDIDATE status.")

        current_date = current_time.date()
        if state.last_reflection_time == current_date:
            if state.reflection_count_today >= 1:
                raise ValueError("Threshold 3 (Daily reflection quota of 1) exceeded.")
            state.reflection_count_today += 1
        else:
            state.last_reflection_time = current_date
            state.reflection_count_today = 1

        if successful_prediction:
            state.predictions_validated += 1

    def attempt_register(self, name: str, current_time: datetime.datetime):
        if name not in self.dimensions:
            raise ValueError(f"Dimension '{name}' not found.")
            
        state = self.dimensions[name]
        if state.status != DimensionStatus.CANDIDATE:
            raise ValueError(f"Dimension '{name}' is not in CANDIDATE status.")

        days_in_trial = (current_time - state.proposal_time).days
        if days_in_trial < 30:
            raise ValueError(f"Cannot register dimension '{name}'. Threshold 2 (30-day trial period) not met. Current days: {days_in_trial}")
            
        if state.predictions_validated <= 0:
            raise ValueError(f"Cannot register dimension '{name}'. Threshold 2 (Prediction validation) not met.")

        state.status = DimensionStatus.REGISTERED

class HighOrderDimensionDistiller:
    def __init__(self, state_machine: DimensionLifecycleStateMachine):
        self.state_machine = state_machine

    def distill(self, name: str, current_time: datetime.datetime) -> Optional[DimensionState]:
        try:
            self.state_machine.propose_dimension(name, current_time)
            return self.state_machine.dimensions.get(name)
        except ValueError as e:
            return None

@dataclass
class Entity:
    id: str
    tags: Set[str] = field(default_factory=set)

class DimensionOverlayOperator:
    def overlay_dimension(self, entity: Entity, dimension: DimensionState):
        if dimension.status != DimensionStatus.REGISTERED:
            raise ValueError(f"Cannot overlay unregistered dimension '{dimension.name}'.")
        # Mount as a read-only tag
        entity.tags.add(dimension.name)


# =====================================================================
# M5-002 维度生命周期演化件（最高宪法第五铁律：三重硬门槛，防维度爆炸）
# =====================================================================
#
# 在 v1 状态机之上补齐三件事：
# 1. 跨域异常探测器提供**可审计的异常窗口**（哪几天、哪些域、多少事件），
#    而不是只回一个 bool——高阶维度提炼必须拿得到证据；
# 2. HighOrderDimensionDistiller 从**低阶物理感知事实**真实提炼
#    DIM_BURNOUT_RISK / DIM_CREDIT_RISK / DIM_PARENT_HEALTH，
#    门槛 1（连续 3 天跨域物理异常）不满足就整体拦截，绝不开后门；
# 3. DimensionOverlayOperator 的挂载升级为**只读标签**：
#    冻结记录、幂等挂载、禁止撤销篡改（历史不容涂抹）。

from collections.abc import Iterable as _Iterable, Mapping as _Mapping


class ReadOnlyDimensionError(ValueError):
    """只读维度标签被尝试修改/撤销时抛出（宪法：历史与挂载不可篡改）。"""


@dataclass(frozen=True)
class AnomalyWindow:
    """跨域连续异常的可审计窗口快照。"""

    active_days: tuple          # tuple[datetime.date, ...] 异常发生的自然日
    domains: tuple              # tuple[str, ...] 涉及物理域
    event_count: int
    started_at: datetime.datetime
    ended_at: datetime.datetime

    @property
    def day_span(self) -> int:
        return len(self.active_days)


@dataclass(frozen=True)
class HighOrderPattern:
    """高阶维度提炼模式：低阶物理域组合 -> 高阶认知维度。"""

    dimension_name: str
    label: str
    core_domains: frozenset     # 必须全部出现的物理域
    min_active_days: int = 3


HIGH_ORDER_PATTERNS: tuple = (
    HighOrderPattern("DIM_BURNOUT_RISK", "身心衰竭指数", frozenset({"sleep", "heart_rate"})),
    HighOrderPattern("DIM_CREDIT_RISK", "商业信用风险", frozenset({"finance", "social"})),
    HighOrderPattern("DIM_PARENT_HEALTH", "亲情健康关切", frozenset({"family", "health"})),
)


def detect_anomaly_window(
    events: _Iterable,
    current_time: datetime.datetime,
    required_days: int = 3,
    required_domains: int = 2,
) -> Optional[AnomalyWindow]:
    """在给定事件流上探测连续跨域异常窗口；不满足三重门槛则返回 None。

    口径与 v1 ``detect_continuous_anomaly`` 完全一致：最近 ``required_days``
    天内、至少 ``required_days`` 个不同自然日、至少 ``required_domains`` 个物理域。
    """
    recent = [
        e
        for e in events
        if 0 <= (current_time - e.timestamp).total_seconds()
        and (current_time - e.timestamp).days <= required_days
    ]
    if not recent:
        return None
    days = sorted({e.timestamp.date() for e in recent})
    domains = sorted({e.domain for e in recent})
    if len(days) < required_days or len(domains) < required_domains:
        return None
    return AnomalyWindow(
        active_days=tuple(days),
        domains=tuple(domains),
        event_count=len(recent),
        started_at=min(e.timestamp for e in recent),
        ended_at=max(e.timestamp for e in recent),
    )


def _append_if_absent(detector: "CrossDimensionalAnomalyDetector", event: AnomalyEvent) -> None:
    for existing in detector.events:
        if (
            existing.timestamp == event.timestamp
            and existing.domain == event.domain
            and existing.description == event.description
        ):
            return
    detector.add_event(event)


@dataclass
class DistillationOutcome:
    """一次高阶维度提炼的完整回执：谁被提议、谁被拦截、为什么。"""

    proposed: Dict[str, DimensionState] = field(default_factory=dict)
    rejected: Dict[str, str] = field(default_factory=dict)
    windows: Dict[str, AnomalyWindow] = field(default_factory=dict)

    @property
    def any_proposed(self) -> bool:
        return bool(self.proposed)


class HighOrderDimensionDistillerV2:
    """从低阶物理感知事实提炼高阶认知维度（证据驱动，门槛 1 一票否决）。

    事实格式：``{"domain": str, "occurred_at": datetime, "description": str}``。
    """

    def __init__(self, state_machine: DimensionLifecycleStateMachine, patterns: _Iterable = HIGH_ORDER_PATTERNS):
        self.state_machine = state_machine
        self.patterns = tuple(patterns)

    def distill_from_facts(
        self,
        facts: _Iterable[_Mapping],
        current_time: datetime.datetime,
        *,
        required_days: int = 3,
    ) -> DistillationOutcome:
        outcome = DistillationOutcome()
        fact_list = list(facts)

        # 先把全部低阶事实登记进探测器（幂等），形成可审计轨迹
        for fact in fact_list:
            _append_if_absent(
                self.state_machine.detector,
                AnomalyEvent(
                    timestamp=fact["occurred_at"],
                    domain=str(fact["domain"]),
                    description=str(fact.get("description", "")),
                ),
            )

        for pattern in self.patterns:
            covered_days = set()
            seen_core_domains = set()
            evidence_lines: List[str] = []
            for fact in fact_list:
                if fact["domain"] not in pattern.core_domains:
                    continue
                delta = current_time - fact["occurred_at"]
                if delta.total_seconds() < 0 or delta.days > required_days:
                    continue
                covered_days.add(fact["occurred_at"].date())
                seen_core_domains.add(fact["domain"])
                evidence_lines.append(
                    f"[{fact['domain']}] {fact['occurred_at'].date()} {fact.get('description', '')}"
                )

            if seen_core_domains != set(pattern.core_domains):
                outcome.rejected[pattern.dimension_name] = (
                    f"门槛1拦截：核心物理域未齐备，仅见 {sorted(seen_core_domains)}，"
                    f"要求 {sorted(pattern.core_domains)}"
                )
                continue
            if len(covered_days) < max(required_days, pattern.min_active_days):
                outcome.rejected[pattern.dimension_name] = (
                    f"门槛1拦截：跨域物理异常仅持续 {len(covered_days)} 天，"
                    f"不足 {max(required_days, pattern.min_active_days)} 天"
                )
                continue

            try:
                self.state_machine.propose_dimension(pattern.dimension_name, current_time)
            except ValueError as exc:  # 状态机门槛兜底（含 3 天跨域硬校验）
                outcome.rejected[pattern.dimension_name] = f"状态机拦截：{exc}"
                continue

            state = self.state_machine.dimensions[pattern.dimension_name]
            state.evidence = sorted(evidence_lines)
            outcome.proposed[pattern.dimension_name] = state
            window = detect_anomaly_window(
                self.state_machine.detector.events, current_time, required_days
            )
            if window is not None:
                outcome.windows[pattern.dimension_name] = window

        return outcome


class ReadOnlyDimensionTag:
    """只读维度挂载标签：一旦铸造，字段冻结，禁止撤销与改写。"""

    __slots__ = ("_dimension_name", "_target_entity_id", "_mounted_at", "_evidence")

    def __init__(
        self,
        dimension_name: str,
        target_entity_id: str,
        mounted_at: datetime.datetime,
        evidence: tuple = (),
    ) -> None:
        object.__setattr__(self, "_dimension_name", dimension_name)
        object.__setattr__(self, "_target_entity_id", target_entity_id)
        object.__setattr__(self, "_mounted_at", mounted_at)
        object.__setattr__(self, "_evidence", tuple(evidence))

    @property
    def dimension_name(self) -> str:
        return self._dimension_name

    @property
    def target_entity_id(self) -> str:
        return self._target_entity_id

    @property
    def mounted_at(self) -> datetime.datetime:
        return self._mounted_at

    @property
    def evidence(self) -> tuple:
        return self._evidence

    def __setattr__(self, key, value) -> None:
        raise ReadOnlyDimensionError(f"只读维度标签禁止修改字段 {key}")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"ReadOnlyDimensionTag({self._dimension_name} -> {self._target_entity_id})"


class DimensionOverlayOperatorV2:
    """高阶维度只读挂载器：仅 REGISTERED 维度可挂载，挂载即冻结，撤销即违法。"""

    def __init__(self) -> None:
        self._mounted: Dict[str, ReadOnlyDimensionTag] = {}

    def mount_read_only(
        self,
        entity: Entity,
        dimension: DimensionState,
        *,
        mounted_at: Optional[datetime.datetime] = None,
    ) -> ReadOnlyDimensionTag:
        if dimension.status != DimensionStatus.REGISTERED:
            raise ValueError(f"Cannot overlay unregistered dimension '{dimension.name}'.")
        key = f"{entity.id}::{dimension.name}"
        existing = self._mounted.get(key)
        if existing is not None:
            return existing  # 幂等：重复挂载不产生副作用
        tag = ReadOnlyDimensionTag(
            dimension_name=dimension.name,
            target_entity_id=entity.id,
            mounted_at=mounted_at or datetime.datetime.now(),
            evidence=tuple(dimension.evidence),
        )
        self._mounted[key] = tag
        entity.tags.add(dimension.name)  # 兼容 v1 视图：实体侧仍可见标签
        return tag

    def revoke(self, tag: ReadOnlyDimensionTag) -> None:
        raise ReadOnlyDimensionError(
            f"只读维度标签 {tag.dimension_name} 禁止撤销：历史与挂载不可篡改"
        )

    def mounted_tags(self, entity_id: Optional[str] = None) -> List[ReadOnlyDimensionTag]:
        return [
            tag
            for key, tag in self._mounted.items()
            if entity_id is None or key.startswith(f"{entity_id}::")
        ]
