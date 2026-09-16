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


# =====================================================================
# M5-002 演化件：异常窗口审计、低阶事实高阶提炼、只读挂载
# =====================================================================

from aios_core.cognition.dimension_engine import (
    AnomalyWindow,
    detect_anomaly_window,
    DistillationOutcome,
    DimensionOverlayOperatorV2,
    HighOrderDimensionDistillerV2,
    ReadOnlyDimensionError,
    ReadOnlyDimensionTag,
)

def _three_day_cross_domain_facts(base_time):
    """深夜熬夜 + 心率骤升 + 咖啡因消费：横跨 3 天 3 域的物理异常。"""
    d = datetime.timedelta(days=1)
    return [
        {"domain": "sleep", "occurred_at": base_time - 3 * d, "description": "深夜熬夜到凌晨三点"},
        {"domain": "heart_rate", "occurred_at": base_time - 3 * d, "description": "静息心率 112"},
        {"domain": "sleep", "occurred_at": base_time - 2 * d, "description": "连续通宵"},
        {"domain": "finance", "occurred_at": base_time - 2 * d, "description": "88 元大杯咖啡因消费"},
        {"domain": "heart_rate", "occurred_at": base_time - 1 * d, "description": "室性早搏 12 次/分"},
        {"domain": "sleep", "occurred_at": base_time - 1 * d, "description": "睡眠 2.5 小时"},
    ]


def test_anomaly_window_is_auditable():
    sm = DimensionLifecycleStateMachine()
    base_time = datetime.datetime(2026, 9, 10, 12, 0)
    for fact in _three_day_cross_domain_facts(base_time):
        sm.detector.add_event(AnomalyEvent(fact["occurred_at"], fact["domain"], fact["description"]))

    window = detect_anomaly_window(sm.detector.events, base_time)
    assert isinstance(window, AnomalyWindow)
    assert window.day_span == 3
    assert set(window.domains) == {"sleep", "heart_rate", "finance"}
    assert window.event_count == 6

    # 只给 2 天数据：窗口必须探测不出来
    sm2 = DimensionLifecycleStateMachine()
    sm2.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=1), "sleep", "熬夜"))
    sm2.detector.add_event(AnomalyEvent(base_time - datetime.timedelta(days=2), "heart_rate", "心率飙升"))
    assert detect_anomaly_window(sm2.detector.events, base_time) is None


def test_distill_from_facts_burnout_candidate():
    sm = DimensionLifecycleStateMachine()
    distiller = HighOrderDimensionDistillerV2(sm)
    base_time = datetime.datetime(2026, 9, 10, 12, 0)

    outcome = distiller.distill_from_facts(_three_day_cross_domain_facts(base_time), base_time)

    assert "DIM_BURNOUT_RISK" in outcome.proposed
    state = outcome.proposed["DIM_BURNOUT_RISK"]
    assert state.status == DimensionStatus.CANDIDATE
    assert len(state.evidence) >= 4  # 证据链逐条留痕
    assert outcome.windows["DIM_BURNOUT_RISK"].day_span == 3


def test_distill_from_facts_credit_risk_and_parent_health():
    base_time = datetime.datetime(2026, 9, 10, 12, 0)
    d = datetime.timedelta(days=1)

    sm_credit = DimensionLifecycleStateMachine()
    credit_facts = [
        {"domain": "finance", "occurred_at": base_time - 3 * d, "description": "老王借款逾期第 30 天"},
        {"domain": "social", "occurred_at": base_time - 2 * d, "description": "微信催款已读不回"},
        {"domain": "finance", "occurred_at": base_time - 1 * d, "description": "朝阳法院判决生效"},
        {"domain": "social", "occurred_at": base_time - 1 * d, "description": "老王仍在朋友圈晒消费"},
    ]
    outcome = HighOrderDimensionDistillerV2(sm_credit).distill_from_facts(credit_facts, base_time)
    assert "DIM_CREDIT_RISK" in outcome.proposed

    sm_parent = DimensionLifecycleStateMachine()
    parent_facts = [
        {"domain": "family", "occurred_at": base_time - 3 * d, "description": "老妈电话说膝盖疼"},
        {"domain": "health", "occurred_at": base_time - 2 * d, "description": "母亲血压偏高记录"},
        {"domain": "family", "occurred_at": base_time - 1 * d, "description": "陪母亲挂号复查"},
        {"domain": "health", "occurred_at": base_time - 1 * d, "description": "母亲膝盖受凉诊断"},
    ]
    outcome = HighOrderDimensionDistillerV2(sm_parent).distill_from_facts(parent_facts, base_time)
    assert "DIM_PARENT_HEALTH" in outcome.proposed


def test_distill_from_facts_two_day_anomaly_hard_blocked():
    """对抗用例：物理异常未满 3 天，高阶维度提炼必须被门槛 1 整体拦截。"""
    sm = DimensionLifecycleStateMachine()
    distiller = HighOrderDimensionDistillerV2(sm)
    base_time = datetime.datetime(2026, 9, 10, 12, 0)
    d = datetime.timedelta(days=1)

    two_day_facts = [
        {"domain": "sleep", "occurred_at": base_time - 2 * d, "description": "熬夜"},
        {"domain": "heart_rate", "occurred_at": base_time - 2 * d, "description": "心率偏高"},
        {"domain": "sleep", "occurred_at": base_time - 1 * d, "description": "又熬夜"},
        {"domain": "heart_rate", "occurred_at": base_time - 1 * d, "description": "早搏"},
    ]
    outcome = distiller.distill_from_facts(two_day_facts, base_time)

    assert not outcome.any_proposed
    assert "DIM_BURNOUT_RISK" in outcome.rejected
    assert "门槛1拦截" in outcome.rejected["DIM_BURNOUT_RISK"]
    assert sm.dimensions == {}


def test_distill_from_facts_single_domain_hard_blocked():
    """对抗用例：只有单一物理域异常（天数够但跨域不足），照样拦截。"""
    sm = DimensionLifecycleStateMachine()
    distiller = HighOrderDimensionDistillerV2(sm)
    base_time = datetime.datetime(2026, 9, 10, 12, 0)
    d = datetime.timedelta(days=1)

    single_domain = [
        {"domain": "heart_rate", "occurred_at": base_time - 3 * d, "description": "心率快"},
        {"domain": "heart_rate", "occurred_at": base_time - 2 * d, "description": "早搏"},
        {"domain": "heart_rate", "occurred_at": base_time - 1 * d, "description": "心悸"},
    ]
    outcome = distiller.distill_from_facts(single_domain, base_time)
    assert not outcome.any_proposed
    assert "门槛1拦截" in outcome.rejected["DIM_BURNOUT_RISK"]


def test_register_before_30_days_adversarial():
    """对抗用例：候选维度未满 30 天试用期，正式注册必须被门槛 2 拒绝。"""
    sm = DimensionLifecycleStateMachine()
    base_time = datetime.datetime(2026, 9, 1, 12, 0)
    outcome = HighOrderDimensionDistillerV2(sm).distill_from_facts(
        _three_day_cross_domain_facts(base_time), base_time
    )
    assert "DIM_BURNOUT_RISK" in outcome.proposed

    with pytest.raises(ValueError, match="Threshold 2"):
        sm.attempt_register("DIM_BURNOUT_RISK", base_time + datetime.timedelta(days=10))
    assert sm.dimensions["DIM_BURNOUT_RISK"].status == DimensionStatus.CANDIDATE


def test_second_daily_reflection_quota_adversarial():
    """对抗用例：同一日第二次反思必须被门槛 3（每日 1 次配额）拒绝。"""
    sm = DimensionLifecycleStateMachine()
    base_time = datetime.datetime(2026, 9, 1, 12, 0)
    HighOrderDimensionDistillerV2(sm).distill_from_facts(
        _three_day_cross_domain_facts(base_time), base_time
    )

    first = base_time + datetime.timedelta(days=5, hours=2)
    sm.reflect_and_validate("DIM_BURNOUT_RISK", first, successful_prediction=True)
    with pytest.raises(ValueError, match="Threshold 3"):
        sm.reflect_and_validate("DIM_BURNOUT_RISK", first + datetime.timedelta(hours=6), successful_prediction=True)

    # 次日配额恢复
    sm.reflect_and_validate("DIM_BURNOUT_RISK", first + datetime.timedelta(days=1), successful_prediction=True)


def _registered_burnout(base_time):
    sm = DimensionLifecycleStateMachine()
    HighOrderDimensionDistillerV2(sm).distill_from_facts(
        _three_day_cross_domain_facts(base_time), base_time
    )
    reflect_time = base_time + datetime.timedelta(days=15)
    sm.reflect_and_validate("DIM_BURNOUT_RISK", reflect_time, successful_prediction=True)
    sm.attempt_register("DIM_BURNOUT_RISK", base_time + datetime.timedelta(days=30))
    return sm.dimensions["DIM_BURNOUT_RISK"]


def test_read_only_overlay_mount_revoke_and_immutability():
    base_time = datetime.datetime(2026, 8, 1, 12, 0)
    dim_state = _registered_burnout(base_time)
    entity = Entity(id="user_123")
    overlay = DimensionOverlayOperatorV2()

    tag = overlay.mount_read_only(entity, dim_state, mounted_at=base_time + datetime.timedelta(days=31))
    assert isinstance(tag, ReadOnlyDimensionTag)
    assert tag.dimension_name == "DIM_BURNOUT_RISK"
    assert tag.target_entity_id == "user_123"
    assert len(tag.evidence) >= 4
    assert "DIM_BURNOUT_RISK" in entity.tags

    # 幂等挂载：重复挂载返回同一枚标签，不产生副作用
    assert overlay.mount_read_only(entity, dim_state) is tag
    assert len(overlay.mounted_tags("user_123")) == 1

    # 只读铁律：禁止修改字段、禁止撤销
    with pytest.raises(ReadOnlyDimensionError):
        tag.dimension_name = "DIM_HACKED"
    with pytest.raises(ReadOnlyDimensionError):
        overlay.revoke(tag)

    # 未注册维度禁止挂载
    sm2 = DimensionLifecycleStateMachine()
    HighOrderDimensionDistillerV2(sm2).distill_from_facts(
        _three_day_cross_domain_facts(base_time), base_time
    )
    with pytest.raises(ValueError, match="Cannot overlay unregistered dimension"):
        overlay.mount_read_only(Entity(id="user_999"), sm2.dimensions["DIM_BURNOUT_RISK"])
