"""M5-DIM-LIFECYCLE 验收：铁律 5 三重硬门槛 + 对抗性越界注册。

1. 跨域探测器：单域 3 天 / 双域 2 天都构成不了资格；双域 3 天才放行；
2. 门槛一：证据不足 → DimensionGateRejection（连 CANDIDATE 都不建）；
3. 门槛二对抗：未满 30 天任何注册/挂载动作 → RegistrationLockedError；
   满 30 天 + 准确率 ≥70% → ACTIVE；零样本 → EXPIRED；
4. 门槛三对抗：每日第 2 次反思必须被配额拒绝 QuotaExceededBlockError；
5. 高阶维度提炼：心动+睡眠簇 → DIM_BURNOUT_RISK；账单+聊天 → DIM_CREDIT_RISK；
   标签只读：任何写尝试 TypeError/MappingProxy 保护。
"""

from __future__ import annotations

import pytest

from aios_core.cognition.dimension_engine_independent2 import (
    AnomalyChain,
    AnomalyObservation,
    CrossDimensionalAnomalyDetector,
    DimensionGateRejection,
    DimensionLifecycleEngine,
    DimensionState,
    Domain,
    HighOrderDimensionDistiller,
    QuotaExceededBlockError,
    RegistrationLockedError,
)


def test_detector_locks_only_two_domains_three_days() -> None:
    # 单曲 3 天：不成链
    single = [AnomalyObservation(Domain.HEART_RATE, d, True) for d in (10, 11, 12)]
    assert CrossDimensionalAnomalyDetector.lock(single) is None
    # 两曲但只有 2 天
    two_days = [
        AnomalyObservation(Domain.HEART_RATE, 10, True),
        AnomalyObservation(Domain.BILLING_FLOW, 10, True),
        AnomalyObservation(Domain.HEART_RATE, 11, True),
        AnomalyObservation(Domain.BILLING_FLOW, 11, True),
    ]
    assert CrossDimensionalAnomalyDetector.lock(two_days) is None
    # 三域 3 天：放行
    chain = CrossDimensionalAnomalyDetector.lock([
        AnomalyObservation(Domain.HEART_RATE, 10, True),
        AnomalyObservation(Domain.BILLING_FLOW, 11, True),
        AnomalyObservation(Domain.CHAT_SENTIMENT, 11, True),
        AnomalyObservation(Domain.HEART_RATE, 12, True),
        AnomalyObservation(Domain.BILLING_FLOW, 12, True),
        AnomalyObservation(Domain.CHAT_SENTIMENT, 12, True),
        AnomalyObservation(Domain.HEART_RATE, 12, True),
    ])
    assert chain is not None
    assert set(chain.domains) == {Domain.HEART_RATE, Domain.BILLING_FLOW, Domain.CHAT_SENTIMENT}
    assert chain.sustained_days == 3


def _chain(domains: tuple[Domain, ...] = (Domain.HEART_RATE, Domain.SLEEP)) -> AnomalyChain:
    return AnomalyChain(domains=domains, start_day=0, end_day=2)


def test_gate_one_blocks_unqualified() -> None:
    engine = DimensionLifecycleEngine()
    with pytest.raises(DimensionGateRejection):
        engine.submit("dim_x", "单域", AnomalyChain((Domain.HEART_RATE,), 0, 2), day=3)
    with pytest.raises(DimensionGateRejection):
        engine.submit("dim_y", "短链", AnomalyChain((Domain.HEART_RATE, Domain.SLEEP), 0, 1), day=3)
    with pytest.raises(DimensionGateRejection):
        engine.submit("dim_z", "逆时序提交", _chain(), day=1)  # 提交早于链结束


def test_gate_two_adversarial_early_registration() -> None:
    engine = DimensionLifecycleEngine()
    engine.submit("dim_a", "过劳心率链", _chain(), day=3)
    for d in range(4, 15):
        engine.record_prediction("dim_a", day=d, success=d % 3 != 0)

    with pytest.raises(RegistrationLockedError, match="对抗性越界"):
        engine.register_if_mature("dim_a", day=10)   # 才 7 天，强行注册
    with pytest.raises(RegistrationLockedError):
        engine.register_if_mature("dim_a", day=29)   # 差 1 天也不行

    state = engine.register_if_mature("dim_a", day=33)
    assert state is DimensionState.ACTIVE
    assert engine.state_of("dim_a") is DimensionState.ACTIVE


def test_gate_two_zero_sample_expires_and_below_threshold_expires() -> None:
    engine = DimensionLifecycleEngine()
    engine.submit("dim_zero", "零样本", _chain((Domain.BILLING_FLOW, Domain.CHAT_SENTIMENT)), day=3)
    assert engine.register_if_mature("dim_zero", day=33) is DimensionState.EXPIRED

    engine.submit("dim_50", "半胜率", _chain((Domain.BILLING_FLOW, Domain.CHAT_SENTIMENT)), day=3)
    for d in range(4, 14):
        # 5:5 → 50% < 70%
        engine.record_prediction("dim_50", day=d, success=d % 2 == 0)
    assert engine.register_if_mature("dim_50", day=33) is DimensionState.EXPIRED


def test_gate_three_second_reflection_rejected() -> None:
    engine = DimensionLifecycleEngine()
    engine.submit("dim_r", "可省链", _chain(), day=3)
    assert engine.reflect("dim_r", day=4).startswith("reflect:")
    with pytest.raises(QuotaExceededBlockError):
        engine.reflect("dim_r", day=4)
    # 新的一天配额复位
    assert engine.reflect("dim_r", day=5).startswith("reflect:")


def test_read_only_label_is_truly_immutable() -> None:
    engine = DimensionLifecycleEngine()
    engine.submit("dim_burn", "过劳心率链", _chain(), day=3)
    for d in range(4, 14):
        engine.record_prediction("dim_burn", day=d, success=True)
    engine.register_if_mature("dim_burn", day=33)

    engine.submit("dim_credit", "信用链", _chain((Domain.BILLING_FLOW, Domain.CHAT_SENTIMENT)), day=3)
    for d in range(4, 14):
        engine.record_prediction("dim_credit", day=d, success=True)
    engine.register_if_mature("dim_credit", day=33)

    minted = HighOrderDimensionDistiller.distill(engine)
    assert set(minted) == {"DIM_BURNOUT_RISK", "DIM_CREDIT_RISK"}

    label = engine.label_of("DIM_BURNOUT_RISK")
    assert label["name"] == "过劳猝死风险"
    assert label["level"] == "P0-HEALTH"
    with pytest.raises(TypeError):
        label["level"] = "P3-LOW"  # type: ignore[index]

    # 幂等：二次 distill 不重复铸造
    assert HighOrderDimensionDistiller.distill(engine) == ()


def test_unknown_dimension_and_foreign_label_blow_up() -> None:
    engine = DimensionLifecycleEngine()
    with pytest.raises(KeyError):
        engine.reflect("ghost", day=1)
    with pytest.raises(KeyError):
        engine.label_of("ghost")
    with pytest.raises(ValueError):
        engine.submit("dup", "x", _chain(), day=3)
        engine.submit("dup", "x", _chain(), day=3)
