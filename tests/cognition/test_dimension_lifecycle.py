"""Agent-07 / M5-DIM-LIFECYCLE：跨域异常探测 + 铁律5三重门槛 + 高阶提炼。

对抗性用例：未满 30 天晋升必须抛 PrematurePromotionError；当日第 2 次
反思必须被配额拒绝（QuotaExceededBlockError）；高阶维度只读标签篡改
必须 ValidationError。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.cognition.dimension_engine import (
    CrossDimensionalAnomalyDetector,
    DailyDomainSample,
    DimensionState,
    HighOrderDimensionDistiller,
    PrematurePromotionError,
    QuotaExceededBlockError,
    TripleGateMachine,
)
from aios_core.contracts.refs import ObjectRef

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)


def _stream(days: int, domains: tuple[str, ...]) -> list[DailyDomainSample]:
    bands = {
        "hr": (55, 85, 103),          # value 103 超上限 → 异常
        "bills": (0, 5000, 18600),    # 超支
        "chat": (0, 10, 47),          # 高压话术频次
        "sleep": (300, 540, 260),     # 低于下限
    }
    samples = []
    for d in range(days):
        for domain in domains:
            low, high, bad = bands[domain]
            samples.append(DailyDomainSample(
                domain=domain, day=T0 + timedelta(days=d),
                value=bad if d >= days - 5 else (low + high) / 2,
                low=low, high=high,
            ))
    return samples


def test_cross_domain_3day_lock() -> None:
    detector = CrossDimensionalAnomalyDetector()
    detector.ingest(_stream(9, ("hr", "bills", "chat")))
    lock = detector.detect(at=T0 + timedelta(days=9))
    assert lock is not None
    assert set(lock.domains) == {"hr", "bills", "chat"}
    assert lock.sustained_days >= 3


def test_single_domain_or_short_span_never_locks() -> None:
    detector = CrossDimensionalAnomalyDetector()
    detector.ingest(_stream(9, ("hr",)))
    assert detector.detect(at=T0 + timedelta(days=9)) is None
    short = CrossDimensionalAnomalyDetector()
    # 双域但仅 2 天异常（第 5、6 天）→ 铁律5 门槛1 拒绝锁定
    samples = _stream(9, ("hr", "bills"))[:8] + [  # 仅第0-3天（正常段）
        DailyDomainSample(domain="hr", day=T0 + timedelta(days=5), value=103, low=55, high=85),
        DailyDomainSample(domain="bills", day=T0 + timedelta(days=5), value=18600, low=0, high=5000),
        DailyDomainSample(domain="hr", day=T0 + timedelta(days=6), value=103, low=55, high=85),
        DailyDomainSample(domain="bills", day=T0 + timedelta(days=6), value=18600, low=0, high=5000),
    ]
    short.ingest(samples)
    assert short.detect(at=T0 + timedelta(days=6)) is None


def test_gate1_and_trial_flow() -> None:
    detector = CrossDimensionalAnomalyDetector()
    detector.ingest(_stream(9, ("hr", "bills", "chat")))
    lock = detector.detect(at=T0 + timedelta(days=9))
    gates = TripleGateMachine()
    gates.propose("dim_founder_burnout", lock)
    assert gates.state("dim_founder_burnout") is DimensionState.CANDIDATE
    trial_start = T0 + timedelta(days=10)
    gates.begin_trial("dim_founder_burnout", at=trial_start)
    for i in range(12):
        gates.record_prediction("dim_founder_burnout", f"p{i}", correct=i % 4 != 3)
    assert gates.promote("dim_founder_burnout", at=trial_start + timedelta(days=30)) is (
        DimensionState.ACTIVE
    )


def test_adversarial_premature_promotion_rejected() -> None:
    detector = CrossDimensionalAnomalyDetector()
    detector.ingest(_stream(9, ("hr", "bills")))
    lock = detector.detect(at=T0 + timedelta(days=9))
    gates = TripleGateMachine()
    gates.propose("dim_credit_risk", lock)
    gates.begin_trial("dim_credit_risk", at=T0 + timedelta(days=10))
    for i in range(12):
        gates.record_prediction("dim_credit_risk", f"p{i}", correct=True)
    with pytest.raises(PrematurePromotionError) as excinfo:
        gates.promote("dim_credit_risk", at=T0 + timedelta(days=10 + 29))
    assert excinfo.value.served_days == 29 and excinfo.value.required_days == 30
    assert gates.state("dim_credit_risk") is DimensionState.TRIAL  # 状态未被越界改动


def test_adversarial_second_reflection_blocked_by_quota() -> None:
    gates = TripleGateMachine()
    day = T0 + timedelta(days=3)
    gates.reflection_allowance(at=day)                      # 第 1 次：通过
    with pytest.raises(QuotaExceededBlockError):
        gates.reflection_allowance(at=day + timedelta(hours=1))
    with pytest.raises(QuotaExceededBlockError):
        gates.reflection_allowance(at=day + timedelta(hours=23))
    gates.reflection_allowance(at=day + timedelta(days=1))  # 次日刷新


def test_high_order_dimensions_are_sealed_read_only() -> None:
    detector = CrossDimensionalAnomalyDetector()
    detector.ingest(_stream(9, ("hr", "bills", "chat")))
    lock = detector.detect(at=T0 + timedelta(days=9))
    distiller = HighOrderDimensionDistiller()
    dim = distiller.distill(
        "burnout",
        anomaly_lock=lock,
        trial_dimension_id="dim_founder_burnout",
        evidence_refs=(
            ObjectRef(object_id="obs_sleep_0605", revision=1),
            ObjectRef(object_id="obs_hrv_0606", revision=2),
            ObjectRef(object_id="claim_vc_pressure", revision=1),
        ),
        confidence=0.9,
        at=T0 + timedelta(days=9, hours=8),
    )
    assert dim.dimension_id == "DIM_BURNOUT_RISK"
    assert dim.read_only is True
    assert dim.state is DimensionState.ACTIVE
    with pytest.raises(ValidationError):
        dim.read_only = False  # type: ignore[misc]
    credit = distiller.distill(
        "credit",
        anomaly_lock=lock,
        trial_dimension_id="dim_laowang_credit",
        evidence_refs=(ObjectRef(object_id="obs_court_2024", revision=1),),
        confidence=0.95,
        at=T0 + timedelta(days=9, hours=9),
    )
    assert credit.dimension_id == "DIM_CREDIT_RISK"
    assert "信用破产" in credit.title
