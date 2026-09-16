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


# ===========================================================================
# M5-002 对抗性验收（Agent-07）：越界注册必须抛异常、配额必须拒第二枪、
# 心率+账单+聊天跨域 3 天锁定、高阶提炼命中、只读挂载不可篡改。
# ===========================================================================

from aios_core.cognition.dimension_engine import (  # noqa: E402
    HIGH_ORDER_SIGNAL_PACKS,
    ReadOnlyOverlayRegistry,
    cross_dimensional_lock_3d,
    detect_strict_cross_domain_lock,
    mount_registered_readonly,
    HighOrderDimensionDistillerV2,
)

AWARE_BASE = datetime.datetime(2026, 9, 16, 13, 0, tzinfo=datetime.timezone.utc)


def _aware_event(days_ago: int, domain: str, desc: str = "x") -> AnomalyEvent:
    return AnomalyEvent(AWARE_BASE - datetime.timedelta(days=days_ago), domain, desc)


def test_strict_lock_rejects_gap_days():
    """第 1 天有、第 2 天空、第 3 天有 —— 宽松版会误判锁定，严格版必须拒绝。"""
    sm = DimensionLifecycleStateMachine()
    sm.detector.add_event(_aware_event(2, "heart_rate"))
    sm.detector.add_event(_aware_event(0, "billing"))
    locked, domains = cross_dimensional_lock_3d(sm.detector, AWARE_BASE)
    assert locked is False


def test_strict_lock_heart_rate_billing_chat_three_days():
    """工单点名场景：心率 + 账单 + 聊天跨域持续 3 天 → 锁定。"""
    sm = DimensionLifecycleStateMachine()
    for day, domain in [(2, "heart_rate"), (2, "chat"), (1, "billing"), (0, "heart_rate")]:
        sm.detector.add_event(_aware_event(day, domain))
    locked, domains = cross_dimensional_lock_3d(sm.detector, AWARE_BASE)
    assert locked is True
    assert {"heart_rate", "billing", "chat"} <= domains


def test_naive_timestamps_and_future_events_rejected():
    naive = AnomalyEvent(datetime.datetime(2026, 9, 14, 13, 0), "heart_rate", "naive")
    with pytest.raises(ValueError, match="timezone-aware"):
        detect_strict_cross_domain_lock([naive], AWARE_BASE)
    # 未来倒填事件永不采信
    sm = DimensionLifecycleStateMachine()
    sm.detector.add_event(AnomalyEvent(AWARE_BASE + datetime.timedelta(days=1), "sleep", "future"))
    sm.detector.add_event(_aware_event(1, "heart_rate"))
    locked, _ = cross_dimensional_lock_3d(sm.detector, AWARE_BASE)
    assert locked is False


def test_adversarial_register_before_30_days_raises():
    """对抗性越界注册：未满 30 天 attempt_register 必须抛异常，状态不许漂移。"""
    sm = DimensionLifecycleStateMachine()
    for day, domain in [(2, "sleep"), (1, "heart_rate"), (0, "caffeine")]:
        sm.detector.add_event(_aware_event(day, domain))
    sm.propose_dimension("DIM_BURNOUT_RISK", AWARE_BASE)
    with pytest.raises(ValueError, match="Threshold 2"):
        sm.attempt_register("DIM_BURNOUT_RISK", AWARE_BASE + datetime.timedelta(days=29, hours=23))
    assert sm.dimensions["DIM_BURNOUT_RISK"].status == DimensionStatus.CANDIDATE


def test_adversarial_second_reflection_same_day_quota_denied():
    """每天第 2 次反思必须被配额拒绝；次日恢复 1 次。"""
    sm = DimensionLifecycleStateMachine()
    for day, domain in [(2, "sleep"), (1, "heart_rate"), (0, "caffeine")]:
        sm.detector.add_event(_aware_event(day, domain))
    sm.propose_dimension("DIM_BURNOUT_RISK", AWARE_BASE)
    day1 = AWARE_BASE + datetime.timedelta(days=1)
    sm.reflect_and_validate("DIM_BURNOUT_RISK", day1, successful_prediction=True)
    with pytest.raises(ValueError, match="Threshold 3"):
        sm.reflect_and_validate("DIM_BURNOUT_RISK", day1 + datetime.timedelta(hours=2), True)
    sm.reflect_and_validate(
        "DIM_BURNOUT_RISK", day1 + datetime.timedelta(days=1), successful_prediction=True
    )  # 次日放行


def test_high_order_distiller_locks_correct_packs():
    sm = DimensionLifecycleStateMachine()
    # burnout 包：sleep+hr+caffeine；credit 包：billing+chat；同一 3 天窗口内混灌
    for day, domain in [(2, "sleep"), (1, "heart_rate"), (0, "caffeine")]:
        sm.detector.add_event(_aware_event(day, domain))
    sm.detector.add_event(_aware_event(2, "billing"))
    sm.detector.add_event(_aware_event(1, "chat"))
    distiller = HighOrderDimensionDistillerV2(sm)
    distilled = distiller.distill_high_order(AWARE_BASE)
    assert "DIM_BURNOUT_RISK" in distilled
    assert "DIM_CREDIT_RISK" not in distilled  # billing+chat 只盖住 2 天缺口? day0 缺失
    assert set(HIGH_ORDER_SIGNAL_PACKS) == {"DIM_BURNOUT_RISK", "DIM_CREDIT_RISK", "DIM_PARENT_HEALTH"}


def test_overlay_mount_is_readonly_and_idempotent():
    """完整通过 30 天验证的候选：正式注册 + 只读挂载成功；视图不可篡改、重复挂载幂等。"""
    sm = DimensionLifecycleStateMachine()
    for day, domain in [(2, "sleep"), (1, "heart_rate"), (0, "caffeine")]:
        sm.detector.add_event(_aware_event(day, domain))
    sm.propose_dimension("DIM_BURNOUT_RISK", AWARE_BASE)
    for probe in range(1, 31):  # 试用期内每天 1 次反思配额，交替预测
        sm.reflect_and_validate(
            "DIM_BURNOUT_RISK",
            AWARE_BASE + datetime.timedelta(days=probe),
            successful_prediction=(probe % 3 != 0),
        )
    sm.attempt_register("DIM_BURNOUT_RISK", AWARE_BASE + datetime.timedelta(days=30))
    assert sm.dimensions["DIM_BURNOUT_RISK"].status == DimensionStatus.REGISTERED

    registry = ReadOnlyOverlayRegistry()
    operator = DimensionOverlayOperator()
    entity = Entity(id="user_007")
    view = mount_registered_readonly(operator, registry, entity, sm.dimensions["DIM_BURNOUT_RISK"])
    assert view == frozenset({"DIM_BURNOUT_RISK"})
    assert "DIM_BURNOUT_RISK" in entity.tags
    # 幂等重挂
    again = registry.mount("user_007", sm.dimensions["DIM_BURNOUT_RISK"])
    assert again == view
    assert len(registry.mount_log) == 1
    # 只读：视图对象本身不可变，账本无卸载 API
    with pytest.raises(AttributeError):
        view.add("DIM_SNEAK_IN")
    for forbidden in ("unmount", "unoverlay", "remove_tag", "overwrite"):
        assert not hasattr(registry, forbidden)
    # 未注册维度禁止挂载
    sm2 = DimensionLifecycleStateMachine()
    for day, domain in [(2, "knee"), (1, "weather"), (0, "parent_health")]:
        sm2.detector.add_event(_aware_event(day, domain))
    sm2.propose_dimension("DIM_PARENT_HEALTH", AWARE_BASE)
    with pytest.raises(ValueError, match="unregistered"):
        registry.mount("mom_001", sm2.dimensions["DIM_PARENT_HEALTH"])
