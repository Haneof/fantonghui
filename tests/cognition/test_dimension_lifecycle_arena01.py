# -*- coding: utf-8 -*-
"""Agent-07 / M5-DIM-LIFECYCLE 心智维度演化与生命周期 · 验收测试（arena01 线）

对抗性越界用例硬门禁：
- 未满 30 天注册/转正必须抛 TrialWindowNotMetError；
- 每天第 2 次反思必须被 ReflectionQuotaExceededError 配额拒绝；
- 心率+账单+聊天跨域持续 3 天异常才可锁定；
- 高阶维度标签只读（frozen，改写即抛 FrozenInstanceError）。
"""

from dataclasses import FrozenInstanceError
from datetime import date, timedelta

import pytest

from aios_core.cognition.dimension_engine_arena01 import (
    CrossDimensionalAnomalyDetector,
    DimensionLifecycleGate,
    DomainAnomaly,
    HighOrderDimensionDistiller,
    LifecycleGateError,
    LifecycleStage,
    ReflectionQuotaExceededError,
    TrialWindowNotMetError,
)

DAY0 = date(2026, 3, 1)


def _three_day_lock(domains=("heartrate", "billing", "chat")):
    detector = CrossDimensionalAnomalyDetector()
    for d in range(3):
        for i, dom in enumerate(domains):
            detector.ingest(DomainAnomaly(
                domain=dom, day=DAY0 + timedelta(days=d),
                severity=0.8, text=f"{dom}异常{d}",
            ))
    lock = detector.try_lock("self")
    assert lock is not None
    return detector, lock


def test_gate1_cross_domain_detector_locks_only_on_3x3_evidence():
    # 单域三来日 → 不锁（必须跨 ≥2 个物理分离域）
    weak = CrossDimensionalAnomalyDetector()
    for d in range(3):
        weak.ingest(DomainAnomaly("heartrate", DAY0 + timedelta(days=d), 0.9, "心率异常"))
    assert weak.try_lock() is None

    # 三域 2 日 → 不锁；三日 → 锁定
    detector = CrossDimensionalAnomalyDetector()
    for d in range(2):
        for dom in ("heartrate", "billing", "chat"):
            detector.ingest(DomainAnomaly(dom, DAY0 + timedelta(days=d), 0.8, "异常"))
    assert detector.try_lock("self") is None
    for dom in ("heartrate", "billing", "chat"):
        detector.ingest(DomainAnomaly(dom, DAY0 + timedelta(days=2), 0.8, "异常"))
    lock = detector.try_lock("self")
    assert lock is not None
    assert set(lock.domains) == {"heartrate", "billing", "chat"}
    assert len(lock.covered_days) == 3 and lock.span_days == 3
    assert detector.try_lock("self") is None  # 锁定清账，不重复开票


def test_gate2_full_lifecycle_and_trial_window_guard():
    _, lock = _three_day_lock()
    gate = DimensionLifecycleGate()
    gate.register_candidate("dim-stress-signal", lock)
    assert gate.stage_of("dim-stress-signal") is LifecycleStage.CANDIDATE

    gate.begin_trial("dim-stress-signal", lock.last_anomaly_day)
    # 对抗：未满 30 天即转正必须抛异常
    with pytest.raises(TrialWindowNotMetError):
        gate.activate("dim-stress-signal", lock.last_anomaly_day + timedelta(days=28))

    trial_start = lock.last_anomaly_day
    for d in range(30):
        day = trial_start + timedelta(days=d)
        gate.record_prediction("dim-stress-signal", day, correct=(d % 4 != 0))
    track = gate.activate("dim-stress-signal", trial_start + timedelta(days=29))
    assert track.stage is LifecycleStage.ACTIVE


def test_gate2_adversarial_predate_and_replay_rejected():
    _, lock = _three_day_lock()
    gate = DimensionLifecycleGate()
    gate.register_candidate("dim-x", lock)
    with pytest.raises(LifecycleGateError):
        gate.begin_trial("dim-x", lock.last_anomaly_day - timedelta(days=1))
    gate.begin_trial("dim-x", lock.last_anomaly_day)
    gate.record_prediction("dim-x", lock.last_anomaly_day, True)
    with pytest.raises(LifecycleGateError, match="replay"):
        gate.record_prediction("dim-x", lock.last_anomaly_day, False)


def test_gate2_expired_when_thresholds_missed():
    _, lock = _three_day_lock()
    gate = DimensionLifecycleGate()
    gate.register_candidate("dim-weak", lock)
    gate.begin_trial("dim-weak", lock.last_anomaly_day)
    for d in range(20):  # 覆盖 20/30 = 0.667 < 0.80
        gate.record_prediction("dim-weak", lock.last_anomaly_day + timedelta(days=d), True)
    with pytest.raises(LifecycleGateError, match="expired"):
        gate.activate("dim-weak", lock.last_anomaly_day + timedelta(days=29))
    assert gate.stage_of("dim-weak") is LifecycleStage.EXPIRED


def test_gate3_second_reflection_same_day_quota_refused():
    _, lock = _three_day_lock()
    gate = DimensionLifecycleGate()
    gate.register_candidate("dim-quota", lock)
    assert gate.reflect("dim-quota", lock.last_anomaly_day) == 1
    with pytest.raises(ReflectionQuotaExceededError):
        gate.reflect("dim-quota", lock.last_anomaly_day)
    # 次日配额重置
    assert gate.reflect("dim-quota", lock.last_anomaly_day + timedelta(days=1)) == 1


def test_gate1_weak_lock_cannot_register_candidate():
    detector = CrossDimensionalAnomalyDetector()
    for d in range(3):
        detector.ingest(DomainAnomaly("heartrate", DAY0 + timedelta(days=d), 0.9, "x"))
    gate = DimensionLifecycleGate()
    with pytest.raises(LifecycleGateError):
        # 未获取锁定，直接伪造一个单域锁定体也不行——直接走 register 校验
        from aios_core.cognition.dimension_engine_arena01 import CrossDomainLock
        fake = CrossDomainLock("LOCK-fake", ("heartrate",), (DAY0,), 1, DAY0)
        gate.register_candidate("dim-fake", fake)


def test_high_order_distiller_labels_are_readonly_and_grounded():
    detector, lock = _three_day_lock()
    corpus = [
        "老王名下民事判决进入恢复执行程序，多笔逾期债务赖账",
        "老王违约告知函已送达，法律责任明确",
        "连续通宵加班三晚，动态心电图频报室性早搏，心悸明显，猝死风险话术已触发",
    ]
    labels = HighOrderDimensionDistiller().distill(locks=[lock], claim_texts=corpus)
    codes = {label.code for label in labels}
    assert "DIM_CREDIT_RISK" in codes
    assert "老王" in next(l for l in labels if l.code == "DIM_CREDIT_RISK").title
    # 只读标签：改写立即抛 FrozenInstanceError
    label = labels[0]
    with pytest.raises(FrozenInstanceError):
        label.title = "被篡改"  # type: ignore[misc]


def test_detector_window_of_single_day_spam_never_locks():
    detector = CrossDimensionalAnomalyDetector()
    for i in range(50):
        detector.ingest(DomainAnomaly("heartrate", DAY0, 0.9, "抖动"))
        detector.ingest(DomainAnomaly("billing", DAY0, 0.9, "抖动"))
    assert detector.try_lock("self") is None  # 同一天刷屏 ≠ 持续 3 天体征
