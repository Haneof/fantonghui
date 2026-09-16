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
# M5-002 维度生命周期强化测试（工单 #7 / Agent-07）
#
# 验收要点：
#   1. 跨域锁定必须"≥2 物理域 × 连续 ≥3 天"，两天窗口一律拒绝立案；
#   2. 三重硬门槛按序生效：门槛一跨域连续、门槛二 30 天试用 + 预测准确率 ≥70%、
#      门槛三每日最多 1 次反思配额；
#   3. 高阶维度（过劳猝死 / 商业信用 / 亲人健康）必须从**真实观测物证**提炼，
#      并以**只读标签**挂载，任何就地涂改都被拦截；
#   4. 对抗性越界注册（未满 30 天 / 每日第 2 次反思）必须抛异常。
# ===========================================================================

import datetime as dt

from aios_core.bench.life_world_kit import (
    build_anomaly_window,
    build_anomaly_windows,
)
from aios_core.cognition.dimension_engine import (
    DIM_BURNOUT_RISK,
    DIM_CREDIT_RISK,
    DIM_PARENT_HEALTH,
    DIMENSION_RECIPES,
    AnomalyDomain,
    CrossDomainGateError,
    DimensionStatus,
    OverlayReadOnlyError,
    PredictionAccuracyGateError,
    ReflectionQuotaExceededError,
    TrialPeriodGateError,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore

WINDOW_START = dt.datetime(2026, 9, 10, 2, 0, tzinfo=dt.timezone.utc)
WINDOW_NOW = dt.datetime(2026, 9, 12, 12, 0, tzinfo=dt.timezone.utc)


def _store(tmp_path, name: str) -> SQLiteWorldStore:
    return SQLiteWorldStore(str(tmp_path / name))


def _load_windows(store: SQLiteWorldStore, *, days: int = 3, start: dt.datetime = WINDOW_START):
    return build_anomaly_windows(store, start=start, days=days, seed=11)


def _detector_over(store: SQLiteWorldStore, window, *, strict: bool = True):
    """把窗口观测灌进探测器（真实物证 → 异常事件）。"""
    from aios_core.cognition.dimension_engine import CrossDimensionalAnomalyDetector

    detector = CrossDimensionalAnomalyDetector()
    ingested = detector.ingest_observations(window.payloads(store))
    assert ingested == len(window.observation_ids), "窗口观测必须全部被探测器吞入"
    return detector


def _matured_state_machine(store, window, *, now: dt.datetime = WINDOW_NOW):
    """构造一台已锁定的状态机（门槛一已过，候选维度已立案）。"""
    from aios_core.cognition.dimension_engine import DimensionLifecycleStateMachine

    detector = _detector_over(store, window)
    sm = DimensionLifecycleStateMachine(detector=detector)
    return sm


def test_cross_domain_lock_requires_three_consecutive_days(tmp_path):
    store = _store(tmp_path, "lock.db")
    windows = _load_windows(store)
    window = windows["burnout"]
    detector = _detector_over(store, window)

    finding = detector.detect_cross_domain_lock(WINDOW_NOW)
    assert finding.is_locked is True
    assert len(finding.days) == 3
    assert {"health", "work", "finance"}.issubset({d.value for d in finding.domains})
    assert finding.evidence_refs, "跨域锁定必须携带真实物证指针"
    for ref in finding.evidence_refs:
        assert store.get_payload(ref.object_id)["object_id"] == ref.object_id
    assert "跨域锁定成立" in finding.describe()

    # 控制组：只有两天异常（历史窗口），以最新异常日为锚仍缺 1 天 → 拒绝锁定
    short_start = dt.datetime(2026, 9, 5, 2, 0, tzinfo=dt.timezone.utc)
    short = build_anomaly_window(store, profile="burnout", start=short_start, days=2, seed=23)
    short_detector = _detector_over(store, short)
    short_finding = short_detector.detect_cross_domain_lock(
        dt.datetime(2026, 9, 6, 12, 0, tzinfo=dt.timezone.utc)
    )
    assert short_finding.is_locked is False
    assert "连续 3 天要求未满足" in short_finding.reason

    # 控制组：连续 3 天但只有单一物理域（心率孤证）→ 跨域性不足，拒绝锁定
    from aios_core.cognition.dimension_engine import AnomalyEvent, CrossDimensionalAnomalyDetector

    single = CrossDimensionalAnomalyDetector()
    for offset in range(3):
        single.add_event(
            AnomalyEvent(WINDOW_NOW - dt.timedelta(days=offset), "heart_rate", "单域心率异常（无账单/聊天佐证）")
        )
    isolated = single.detect_cross_domain_lock(WINDOW_NOW)
    assert isolated.is_locked is False
    assert "物理域" in isolated.reason


def test_adversarial_distill_before_three_days_is_refused(tmp_path):
    store = _store(tmp_path, "gate1.db")
    short = build_anomaly_window(
        store,
        profile="burnout",
        start=dt.datetime(2026, 9, 11, 2, 0, tzinfo=dt.timezone.utc),
        days=2,
        seed=5,
    )
    sm = _matured_state_machine(store, short)
    sm.detector.ingest_observations(short.payloads(store))

    distiller = HighOrderDimensionDistiller(sm)
    # 严格档：未满 3 天必须抛门槛一异常，绝不"先建了再说"
    with pytest.raises(CrossDomainGateError, match="Threshold 1"):
        distiller.distill_strict(DIM_BURNOUT_RISK, WINDOW_NOW)
    # 兼容档（M1 语义）：返回 None，但状态机里绝不能留下候选维度
    assert distiller.distill(DIM_BURNOUT_RISK, WINDOW_NOW) is None
    assert DIM_BURNOUT_RISK not in sm.dimensions

    # 立案也要被门槛一拦住
    with pytest.raises(CrossDomainGateError, match="Threshold 1"):
        sm.propose_dimension(DIM_BURNOUT_RISK, WINDOW_NOW)


def test_adversarial_missing_required_domain_is_refused(tmp_path):
    store = _store(tmp_path, "domain.db")
    windows = _load_windows(store)
    sm = _matured_state_machine(store, windows["burnout"])
    sm.detector.ingest_observations(windows["burnout"].payloads(store))
    distiller = HighOrderDimensionDistiller(sm)

    # 过劳窗口（health/work/finance）不足以支撑信用破产维度（需要 finance+social）
    with pytest.raises(CrossDomainGateError) as excinfo:
        distiller.distill_strict(DIM_CREDIT_RISK, WINDOW_NOW)
    assert "social" in str(excinfo.value)

    # 换成真正的信用窗口即可立案
    sm.detector.ingest_observations(windows["credit"].payloads(store))
    state = distiller.distill_strict(DIM_CREDIT_RISK, WINDOW_NOW)
    assert state.status == DimensionStatus.CANDIDATE
    assert state.label == DIMENSION_RECIPES[DIM_CREDIT_RISK].label


def test_adversarial_registration_before_thirty_days_is_refused(tmp_path):
    store = _store(tmp_path, "gate2.db")
    windows = _load_windows(store)
    sm = _matured_state_machine(store, windows["burnout"])
    sm.detector.ingest_observations(windows["burnout"].payloads(store))
    distiller = HighOrderDimensionDistiller(sm)

    state = distiller.distill_strict(DIM_BURNOUT_RISK, WINDOW_NOW)
    assert state.status == DimensionStatus.CANDIDATE

    sm.reflect_and_validate(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=10), True)
    sm.reflect_and_validate(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=20), True)

    # 第 29 天注册 → 门槛二拦住
    with pytest.raises(TrialPeriodGateError, match="Threshold 2"):
        sm.attempt_register(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=29))
    assert state.status == DimensionStatus.CANDIDATE

    # 满 30 天但准确率不足 70%：先制造 1 次失败预测（2/2 → 2/3=66.7%）
    sm.reflect_and_validate(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=25), False)
    assert abs(state.prediction_accuracy - 2 / 3) < 1e-9
    with pytest.raises(PredictionAccuracyGateError, match="Threshold 2"):
        sm.attempt_register(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=30))
    assert state.status == DimensionStatus.CANDIDATE

    # 再补一次命中（3/4 = 75% ≥ 70%）才允许注册
    sm.reflect_and_validate(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=31), True)
    assert state.prediction_accuracy >= sm.PREDICTION_ACCURACY_FLOOR
    registered = sm.attempt_register(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=32))
    assert registered.status == DimensionStatus.REGISTERED
    assert registered.registered_at == WINDOW_NOW + dt.timedelta(days=32)
    assert sm.audit()["registered"] == [DIM_BURNOUT_RISK]

    # 已注册维度不得重复立案
    from aios_core.cognition.dimension_engine import DimensionStateError

    with pytest.raises(DimensionStateError):
        sm.propose_dimension(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=33))


def test_adversarial_second_reflection_same_day_hits_quota(tmp_path):
    store = _store(tmp_path, "gate3.db")
    windows = _load_windows(store)
    sm = _matured_state_machine(store, windows["burnout"])
    sm.detector.ingest_observations(windows["burnout"].payloads(store))
    state = HighOrderDimensionDistiller(sm).distill_strict(DIM_BURNOUT_RISK, WINDOW_NOW)

    day_one = WINDOW_NOW + dt.timedelta(days=1)
    sm.reflect_and_validate(DIM_BURNOUT_RISK, day_one, True)
    assert state.reflection_count_today == 1
    assert sm.quota_remaining(day_one.date()) == 0

    # 当天第二次反思 → 配额拒绝（对抗性用例）
    with pytest.raises(ReflectionQuotaExceededError, match="Threshold 3"):
        sm.reflect_and_validate(DIM_BURNOUT_RISK, day_one + dt.timedelta(hours=6), True)

    # 跨日自动复位，配额恢复
    day_two = day_one + dt.timedelta(days=1)
    assert sm.quota_remaining(day_two.date()) == 1
    sm.reflect_and_validate(DIM_BURNOUT_RISK, day_two, True)
    assert state.reflection_count_today == 1
    assert state.prediction_attempts == 2
    assert sm.quota_used(day_two.date()) == 1


def test_high_order_dimensions_carry_real_world_evidence(tmp_path):
    store = _store(tmp_path, "evidence.db")
    windows = _load_windows(store)
    sm = _matured_state_machine(store, windows["burnout"])
    for window in windows.values():
        sm.detector.ingest_observations(window.payloads(store))
    distiller = HighOrderDimensionDistiller(sm)

    for key, profile in (
        (DIM_BURNOUT_RISK, "burnout"),
        (DIM_CREDIT_RISK, "credit"),
        (DIM_PARENT_HEALTH, "parent_health"),
    ):
        state = distiller.distill_strict(key, WINDOW_NOW)
        assert state.status == DimensionStatus.CANDIDATE
        assert state.high_order_key == key
        assert state.label == DIMENSION_RECIPES[key].label
        assert state.evidence_refs, f"{key} 必须携带物证指针"
        # 每一条物证都必须能在世界里被解引用（严禁凭空编造证据 ID）
        for ref in state.evidence_refs:
            payload = store.get_payload(ref.object_id)
            assert ref.object_id.startswith("obs_window_")
            assert payload["object_id"] == ref.object_id
        assert any(ref.object_id.startswith(f"obs_window_{profile}_") for ref in state.evidence_refs)

    audit = sm.audit()
    assert audit["by_status"]["CANDIDATE"] == 3
    assert audit["dimensions"] == 3


def test_overlay_is_read_only_and_requires_registration(tmp_path):
    store = _store(tmp_path, "overlay.db")
    windows = _load_windows(store)
    sm = _matured_state_machine(store, windows["burnout"])
    sm.detector.ingest_observations(windows["burnout"].payloads(store))
    distiller = HighOrderDimensionDistiller(sm)
    state = distiller.distill_strict(DIM_BURNOUT_RISK, WINDOW_NOW)

    operator = DimensionOverlayOperator()
    # 未注册维度禁止挂载（M1 旧接口的错误语义必须保留）
    with pytest.raises(ValueError, match="Cannot overlay unregistered dimension"):
        operator.overlay_dimension(Entity(id="user_1"), state)

    sm.reflect_and_validate(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=5), True)
    sm.attempt_register(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=31))

    overlay = operator.mount(target_id="ent_user_me", target_kind="entity", dimension=state)
    assert overlay.has(DIM_BURNOUT_RISK)
    assert overlay.labels() == (DIMENSION_RECIPES[DIM_BURNOUT_RISK].label,)
    assert overlay.evidence_refs(DIM_BURNOUT_RISK), "只读标签必须保留物证回指"
    assert operator.tags_of("ent_user_me") == frozenset({DIM_BURNOUT_RISK})

    # 只读保护：任何就地涂改都被拦截（改标签 = 改历史）
    for mutate in (overlay.add, overlay.discard, overlay.clear, overlay.update):
        with pytest.raises(OverlayReadOnlyError):
            mutate(DIM_CREDIT_RISK)
    assert operator.tags_of("ent_user_me") == frozenset({DIM_BURNOUT_RISK})

    # 关系/事件目标同样支持只读挂载
    operator.mount(target_id="anchor_wang_fraud_timeline", target_kind="event", dimension=state)
    assert operator.overlay("anchor_wang_fraud_timeline", "event").has(DIM_BURNOUT_RISK)
    assert operator.audit() == {
        "targets": 2,
        "tags": 2,
        "read_only": True,
        "valid_kinds": ["entity", "relation", "event"],
    }

    # M1 兼容写接口仍在（迁移期实体标签集合）
    entity = Entity(id="legacy_user")
    operator.overlay_dimension(entity, state)
    assert DIM_BURNOUT_RISK in entity.tags

    # 非法挂载目标类型直接拒绝
    from aios_core.cognition.dimension_engine import DimensionStateError

    with pytest.raises(DimensionStateError):
        operator.mount(target_id="x", target_kind="planet", dimension=state)


def test_zombie_candidate_expires_after_trial_period(tmp_path):
    store = _store(tmp_path, "expire.db")
    windows = _load_windows(store)
    sm = _matured_state_machine(store, windows["burnout"])
    sm.detector.ingest_observations(windows["burnout"].payloads(store))
    state = HighOrderDimensionDistiller(sm).distill_strict(DIM_BURNOUT_RISK, WINDOW_NOW)

    # 试用期未满不允许作废
    with pytest.raises(TrialPeriodGateError):
        sm.expire(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=10))

    expired = sm.expire(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=31), reason="prediction_never_attempted")
    assert expired.status == DimensionStatus.EXPIRED
    assert expired.rejection_reason == "prediction_never_attempted"
    with pytest.raises(ValueError):
        sm.attempt_register(DIM_BURNOUT_RISK, WINDOW_NOW + dt.timedelta(days=32))
    assert sm.audit()["expired"] == [DIM_BURNOUT_RISK]


def test_dimension_recipes_are_complete_and_specific():
    assert set(DIMENSION_RECIPES) == {DIM_BURNOUT_RISK, DIM_CREDIT_RISK, DIM_PARENT_HEALTH}
    for key, recipe in DIMENSION_RECIPES.items():
        assert recipe.key == key
        assert recipe.label and recipe.description and recipe.advisory
        assert recipe.required_domains, "配方必须声明需点亮的物理域"
        assert recipe.advisory not in recipe.description, "行动建议不得与描述同文（禁止套话复读）"
    assert AnomalyDomain.HEALTH in DIMENSION_RECIPES[DIM_BURNOUT_RISK].required_domains
    assert AnomalyDomain.FINANCE in DIMENSION_RECIPES[DIM_CREDIT_RISK].required_domains
