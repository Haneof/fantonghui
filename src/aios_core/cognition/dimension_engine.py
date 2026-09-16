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
