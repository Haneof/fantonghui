import datetime
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple

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


# ===========================================================================
# M5-002 演进（Agent-07）：严格跨域锁定 / 高阶信号包 / 只读挂载
# 铁律 5：三重硬门槛从严执行；挂载只读，防止任何下游"顺手改写"维度语义。
# ===========================================================================

HIGH_ORDER_SIGNAL_PACKS: Dict[str, Set[str]] = {
    # 身心衰竭指数：睡眠 × 心率 × 咖啡因消费（finance 桶覆盖咖啡账单）
    "DIM_BURNOUT_RISK": {"sleep", "heart_rate", "hrv", "caffeine", "finance"},
    # 商业信用风险：账单 × 聊天拖延 × 司法文书
    "DIM_CREDIT_RISK": {"finance", "billing", "chat", "legal", "court"},
    # 亲情健康关切：父母体征 × 环境 × 亲情沟通
    "DIM_PARENT_HEALTH": {"parent_health", "knee", "weather", "medical", "chat"},
}


def _as_aware_utc(ts: datetime.datetime, field_name: str) -> datetime.datetime:
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError(f"dimension_engine: {field_name} must be timezone-aware (宪法时区铁律)")
    return ts.astimezone(datetime.timezone.utc)


def detect_strict_cross_domain_lock(
    events: List[AnomalyEvent],
    current_time: datetime.datetime,
    *,
    required_days: int = 3,
    min_domains: int = 2,
    allowed_domains: Optional[Set[str]] = None,
) -> Tuple[bool, Set[str], List[datetime.date]]:
    """严格锁定：以 current_time 结尾的连续 required_days 个自然日，
    每日都必须有异常事件、全域累计 >= min_domains 个不同物理域参与。

    与旧版"窗口内数天数"的宽松口径不同，本函数拒绝任何断档
    （如第 1 天有、第 2 天空、第 3 天有 → 不锁定），并且只认
    tz-aware 时间戳，未来事件一律忽略——防止倒填数据骗过门槛一。
    """
    now = _as_aware_utc(current_time, "current_time")
    today = now.date()
    required_days = max(1, int(required_days))
    window: List[datetime.date] = [today - datetime.timedelta(days=k) for k in range(required_days)]
    window.reverse()

    covered: List[datetime.date] = []
    domains: Set[str] = set()
    for day in window:
        day_hits = []
        for e in events:
            ts = _as_aware_utc(e.timestamp, "event.timestamp")
            if ts > now:
                continue  # 未来/倒填事件永不采信
            if ts.date() == day and (allowed_domains is None or e.domain in allowed_domains):
                day_hits.append(e)
        if not day_hits:
            return False, set(), covered
        covered.append(day)
        domains |= {e.domain for e in day_hits}
    if len(domains) < max(2, min_domains):
        return False, domains, covered
    return True, domains, covered


def cross_dimensional_lock_3d(
    detector: "CrossDimensionalAnomalyDetector",
    current_time: datetime.datetime,
    *,
    allowed_domains: Optional[Set[str]] = None,
) -> Tuple[bool, Set[str]]:
    """探测器严格口径门面：连续 3 天跨域异常锁定（工单点名的心率+账单+聊天场景）。"""
    locked, domains, _ = detect_strict_cross_domain_lock(
        detector.events, current_time, required_days=3, min_domains=2,
        allowed_domains=allowed_domains,
    )
    return locked, domains


class ReadOnlyOverlayRegistry:
    """高阶维度只读标签挂载账本（append-only，视图不可变）。"""

    def __init__(self) -> None:
        self._mounts: Dict[str, Set[str]] = {}
        self.mount_log: List[Tuple[str, str, datetime.datetime]] = []

    def mount(self, entity_id: str, dimension: "DimensionState") -> frozenset:
        if dimension.status != DimensionStatus.REGISTERED:
            raise ValueError(
                f"Cannot overlay unregistered dimension '{dimension.name}' "
                "onto entity (只读挂载仅限 REGISTERED 维度)".strip()
            )
        bucket = self._mounts.setdefault(entity_id, set())
        if dimension.name not in bucket:
            bucket.add(dimension.name)
            self.mount_log.append((entity_id, dimension.name, datetime.datetime.now(datetime.timezone.utc)))
        return self.view(entity_id)

    def view(self, entity_id: str) -> frozenset:
        return frozenset(self._mounts.get(entity_id, set()))

    # 宪法姿态：本类刻意不提供 unmount/overwrite/remap API。


class HighOrderDimensionDistillerV2:
    """高阶维度提炼器 V2：按信号包自动识别应衍生的高阶维度名。"""

    def __init__(self, state_machine: "DimensionLifecycleStateMachine") -> None:
        self.state_machine = state_machine

    def distill_high_order(self, current_time: datetime.datetime) -> List[str]:
        promoted: List[str] = []
        for name, pack in HIGH_ORDER_SIGNAL_PACKS.items():
            locked, _domains = cross_dimensional_lock_3d(
                self.state_machine.detector, current_time, allowed_domains=set(pack)
            )
            if not locked:
                continue
            if name in self.state_machine.dimensions:
                continue  # 幂等：同一高阶维度不重复开候选
            try:
                self.state_machine.propose_dimension(name, current_time)
            except ValueError:
                continue  # 宽门槛一在严格锁后仍不满足时静默跳过（防御）
            promoted.append(name)
        return promoted


def mount_registered_readonly(
    operator: "DimensionOverlayOperator",
    registry: ReadOnlyOverlayRegistry,
    entity: "Entity",
    dimension: "DimensionState",
) -> frozenset:
    """兼容桥：旧的实体 tags 挂载 + 新的只读账本挂载同时生效。"""
    operator.overlay_dimension(entity, dimension)
    return registry.mount(entity.id, dimension)
