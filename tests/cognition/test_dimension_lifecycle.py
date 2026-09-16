import pytest
import datetime
from aios_core.cognition.dimension_engine import (
    CrossDimensionalAnomalyDetector,
    DimensionLifecycleStateMachine,
    HighOrderDimensionDistiller,
    DimensionOverlayOperator,
    AnomalyEvent,
    DimensionStatus,
    Entity
)

def test_anomaly_detection_under_3_days():
    sm = DimensionLifecycleStateMachine()
    distiller = HighOrderDimensionDistiller(sm)
    
    base_time = datetime.datetime(2026, 9, 10, 12, 0)
    
    # 2 days of anomalies
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=2), "heart_rate", "High heart rate"))
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=1), "sleep", "Stayed up late"))

    # Attempt to distill
    dim = distiller.distill("DIM_BURNOUT_RISK", base_time)
    
    # Assert rejection
    assert dim is None
    with pytest.raises(ValueError, match="Threshold 1"):
        sm.propose_dimension("DIM_BURNOUT_RISK", base_time)

def test_successful_dimension_registration():
    sm = DimensionLifecycleStateMachine()
    
    base_time = datetime.datetime(2026, 8, 1, 12, 0)
    
    # 3 days of anomalies across multiple domains
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=3), "heart_rate", "High heart rate"))
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=2), "finance", "Large caffeine expense"))
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=1), "sleep", "Stayed up late"))

    # Should succeed now
    sm.propose_dimension("DIM_BURNOUT_RISK", base_time)
    
    dim_state = sm.dimensions["DIM_BURNOUT_RISK"]
    assert dim_state.status == DimensionStatus.CANDIDATE
    
    # Reflect and validate within trial period (e.g., at day 15)
    reflect_time = base_time + datetime.timedelta(days=15)
    sm.reflect_and_validate("DIM_BURNOUT_RISK", reflect_time, successful_prediction=True)
    
    # Exceed reflection quota for the same day
    with pytest.raises(ValueError, match="Threshold 3"):
        sm.reflect_and_validate("DIM_BURNOUT_RISK", reflect_time, successful_prediction=True)

    # Attempt to register before 30 days
    with pytest.raises(ValueError, match="Threshold 2"):
        sm.attempt_register("DIM_BURNOUT_RISK", reflect_time)
        
    # Complete 30-day trial period
    register_time = base_time + datetime.timedelta(days=30)
    sm.attempt_register("DIM_BURNOUT_RISK", register_time)
    
    assert dim_state.status == DimensionStatus.REGISTERED
    
    # Overlay onto entity
    entity = Entity(id="user_123")
    operator = DimensionOverlayOperator()
    operator.overlay_dimension(entity, dim_state)
    
    assert "DIM_BURNOUT_RISK" in entity.tags

def test_overlay_unregistered_dimension():
    sm = DimensionLifecycleStateMachine()
    base_time = datetime.datetime(2026, 8, 1, 12, 0)
    
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=3), "heart_rate", "High heart rate"))
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=2), "finance", "Large expense"))
    sm.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=1), "sleep", "No sleep"))

    sm.propose_dimension("DIM_CREDIT_RISK", base_time)
    
    dim_state = sm.dimensions["DIM_CREDIT_RISK"]
    assert dim_state.status == DimensionStatus.CANDIDATE
    
    entity = Entity(id="user_123")
    operator = DimensionOverlayOperator()
    
    with pytest.raises(ValueError, match="Cannot overlay unregistered dimension"):
        operator.overlay_dimension(entity, dim_state)
