"""M3-001R 动态维度衍生三重硬门限单测（宪法铁律五 · 防维度爆炸）。

三道门限 + 32 维硬上限 + 恶意反思套娃递归切断，逐条断言。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from aios_core.contracts.enums import DimensionLifecycle, ErrorCode
from aios_core.dimensions.evolution_guard_independent import (
    MAX_ACTIVE_DIMENSIONS,
    MAX_INTROSPECTIONS_PER_DAY,
    MAX_REFLECTION_DEPTH,
    MIN_DISTINCT_DOMAINS,
    MIN_PERSISTENCE_DAYS,
    MIN_PREDICTION_ACCURACY,
    MIN_TRIAL_DAYS,
    DimensionProposal,
    DimensionTrialState,
    EvolutionGuard,
    PhysicalDomain,
    QuotaExceededBlockError,
    RecursionDepthExceededError,
    to_frozen_lifecycle,
)
from aios_core.errors import AIOSProtocolError

NOW = datetime(2026, 9, 16, 9, 0, 0, tzinfo=UTC)


def _proposal(
    dimension_id: str,
    domains: tuple[PhysicalDomain, ...],
    days: int,
    *,
    label: str = "衍生维度",
) -> DimensionProposal:
    """构造跨域持续异常的申请：每个域 × 每一天各一条观测。"""
    start = date(2026, 9, 1)
    observations = tuple(
        (domain, start + timedelta(days=d))
        for domain in domains
        for d in range(days)
    )
    return DimensionProposal(
        dimension_id=dimension_id,
        label=label,
        anomaly_observations=observations,
        rationale="跨域持续异常",
    )


def _valid_proposal(dimension_id: str = "dim_stress_recovery") -> DimensionProposal:
    return _proposal(
        dimension_id,
        (PhysicalDomain.HEALTH, PhysicalDomain.WORK),
        MIN_PERSISTENCE_DAYS,
        label="高压期恢复力维度",
    )


# ---------------------------------------------------------------------------
# 门限一：物理域持续性（≥2 域 且 ≥3 天）
# ---------------------------------------------------------------------------


def test_gate1_cross_domain_sustained_anomaly_is_admitted() -> None:
    guard = EvolutionGuard()
    record = guard.admit_candidate(_valid_proposal(), now=NOW)

    assert record.state is DimensionTrialState.CANDIDATE
    assert record.trial_started_at == NOW
    # 门限一常量本身被锁死
    assert MIN_DISTINCT_DOMAINS == 2
    assert MIN_PERSISTENCE_DAYS == 3


@pytest.mark.parametrize(
    ("domains", "days"),
    [
        ((PhysicalDomain.HEALTH,), 3),                      # 单域持续
        ((PhysicalDomain.HEALTH, PhysicalDomain.WORK), 1),  # 跨域但瞬时
        ((PhysicalDomain.HEALTH, PhysicalDomain.WORK), 2),  # 跨域但仅 2 天
        ((PhysicalDomain.FINANCE,), 1),                     # 单点异常
        ((), 0),                                            # 无观测
    ],
)
def test_gate1_transient_or_single_domain_is_rejected(
    domains: tuple[PhysicalDomain, ...], days: int
) -> None:
    guard = EvolutionGuard()
    proposal = _proposal("dim_transient", domains, days)

    ok, reason = guard.evaluate_physical_persistence(proposal)
    assert ok is False
    assert reason != "ok"

    with pytest.raises(AIOSProtocolError) as excinfo:
        guard.admit_candidate(proposal, now=NOW)

    assert excinfo.value.code is ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["gate"] == "physical_persistence"
    # 被拒绝的维度从未进入登记册
    assert "dim_transient" not in guard.stats()
    assert guard.rejection_reason("dim_transient") == reason


def test_gate1_three_distinct_domains_over_three_days_is_admitted() -> None:
    guard = EvolutionGuard()
    proposal = _proposal(
        "dim_three_domain",
        (PhysicalDomain.HEALTH, PhysicalDomain.FINANCE, PhysicalDomain.ENVIRONMENT),
        3,
    )
    assert guard.admit_candidate(proposal, now=NOW).state is DimensionTrialState.CANDIDATE


def test_gate1_duplicate_observations_rejected_by_model() -> None:
    day = date(2026, 9, 1)
    with pytest.raises(ValueError, match="duplicates"):
        DimensionProposal(
            dimension_id="dup",
            label="重复观测",
            anomaly_observations=(
                (PhysicalDomain.HEALTH, day),
                (PhysicalDomain.HEALTH, day),
            ),
        )


# ---------------------------------------------------------------------------
# 门限二：30 天试用期 + 预测准确率 ≥70%
# ---------------------------------------------------------------------------


def test_gate2_accuracy_above_70_percent_promotes_to_active() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal(), now=NOW)

    # 30 天试用期，21/30 = 70% 恰好达标
    state = guard.run_full_trial("dim_stress_recovery", hits=21, total=30, now=NOW)

    assert state is DimensionTrialState.ACTIVE
    assert guard.get("dim_stress_recovery").prediction_accuracy == pytest.approx(0.70)
    assert guard.get("dim_stress_recovery").trial_days_elapsed == MIN_TRIAL_DAYS


def test_gate2_accuracy_below_70_percent_expires() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal(), now=NOW)

    # 20/30 = 66.7% 未达标
    state = guard.run_full_trial("dim_stress_recovery", hits=20, total=30, now=NOW)

    assert state is DimensionTrialState.EXPIRED
    assert guard.get("dim_stress_recovery").prediction_accuracy < MIN_PREDICTION_ACCURACY
    assert "66.67%" in (guard.rejection_reason("dim_stress_recovery") or "")


def test_gate2_expired_dimension_cannot_be_revived() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal(), now=NOW)
    guard.run_full_trial("dim_stress_recovery", hits=1, total=30, now=NOW)

    # 事后补预测：物理上不允许
    with pytest.raises(AIOSProtocolError) as excinfo:
        guard.record_prediction("dim_stress_recovery", hit=True, now=NOW)
    assert "cannot be scored" in str(excinfo.value)

    # 再推进试用期也不得复活
    for day in range(60):
        guard.advance_trial_day("dim_stress_recovery", now=NOW + timedelta(days=day))
    assert guard.get("dim_stress_recovery").state is DimensionTrialState.EXPIRED


def test_gate2_trial_does_not_conclude_before_30_days() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal(), now=NOW)
    for _ in range(10):
        guard.record_prediction("dim_stress_recovery", hit=True, now=NOW)

    # 只推进 29 天：无论准确率多高都不得提前转正
    for day in range(MIN_TRIAL_DAYS - 1):
        state = guard.advance_trial_day("dim_stress_recovery", now=NOW + timedelta(days=day + 1))
    assert state is DimensionTrialState.TRIAL
    assert guard.get("dim_stress_recovery").trial_days_elapsed == 29

    # 第 30 天才裁决
    state = guard.advance_trial_day("dim_stress_recovery", now=NOW + timedelta(days=30))
    assert state is DimensionTrialState.ACTIVE


# ---------------------------------------------------------------------------
# 门限三：每日自省配额严格 1 次
# ---------------------------------------------------------------------------


def test_gate3_daily_introspection_quota_is_exactly_one() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal(), now=NOW)

    guard.introspect("dim_stress_recovery", now=NOW)
    assert guard.get("dim_stress_recovery").introspections_today == 1

    with pytest.raises(QuotaExceededBlockError) as excinfo:
        guard.introspect("dim_stress_recovery", now=NOW + timedelta(hours=3))

    assert excinfo.value.code is ErrorCode.BUDGET_EXHAUSTED
    assert excinfo.value.dimension_id == "dim_stress_recovery"
    assert excinfo.value.context["max_per_day"] == MAX_INTROSPECTIONS_PER_DAY == 1
    # 配额未被超额消耗
    assert guard.get("dim_stress_recovery").introspections_today == 1


def test_gate3_quota_resets_on_a_new_day() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal(), now=NOW)

    guard.introspect("dim_stress_recovery", now=NOW)
    guard.introspect("dim_stress_recovery", now=NOW + timedelta(days=1))
    guard.introspect("dim_stress_recovery", now=NOW + timedelta(days=2))

    assert guard.get("dim_stress_recovery").introspections_today == 1


def test_gate3_quota_is_per_dimension() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal("dim_a"), now=NOW)
    guard.admit_candidate(_valid_proposal("dim_b"), now=NOW)

    guard.introspect("dim_a", now=NOW)
    # dim_b 的配额不受 dim_a 影响
    assert guard.introspect("dim_b", now=NOW).introspections_today == 1
    with pytest.raises(QuotaExceededBlockError):
        guard.introspect("dim_b", now=NOW)


# ---------------------------------------------------------------------------
# 全局活跃维度硬上限 ≤32
# ---------------------------------------------------------------------------


def test_active_cap_is_32_and_evicts_least_active_as_archived() -> None:
    guard = EvolutionGuard()
    assert guard.max_active == MAX_ACTIVE_DIMENSIONS == 32

    # dim_000 最早登记且此后毫无活动
    guard.admit_candidate(_valid_proposal("dim_000"), now=NOW)
    # 其余 31 个陆续登记并产生活动
    for i in range(1, 32):
        dimension_id = f"dim_{i:03d}"
        guard.admit_candidate(_valid_proposal(dimension_id), now=NOW + timedelta(days=i))
        guard.record_prediction(dimension_id, hit=True, now=NOW + timedelta(days=i))

    assert guard.active_count() == 32

    # 第 33 个到来 → 必须淘汰末位
    guard.admit_candidate(_valid_proposal("dim_032"), now=NOW + timedelta(days=40))

    assert guard.active_count() == 32
    assert guard.get("dim_000").state is DimensionTrialState.ARCHIVED
    assert guard.archived_ids() == ("dim_000",)
    assert "cap 32 reached" in (guard.rejection_reason("dim_000") or "")
    assert guard.get("dim_032").state is DimensionTrialState.CANDIDATE


def test_active_cap_never_exceeded_under_a_flood_of_proposals() -> None:
    guard = EvolutionGuard()
    for i in range(100):
        guard.admit_candidate(
            _valid_proposal(f"dim_{i:03d}"), now=NOW + timedelta(hours=i)
        )
        assert guard.active_count() <= MAX_ACTIVE_DIMENSIONS

    assert guard.active_count() == MAX_ACTIVE_DIMENSIONS
    assert len(guard.archived_ids()) == 100 - MAX_ACTIVE_DIMENSIONS


def test_archived_dimension_cannot_be_scored() -> None:
    guard = EvolutionGuard()
    guard.admit_candidate(_valid_proposal("dim_000"), now=NOW)
    for i in range(1, 33):
        dimension_id = f"dim_{i:03d}"
        guard.admit_candidate(_valid_proposal(dimension_id), now=NOW + timedelta(days=i))
        guard.record_prediction(dimension_id, hit=True, now=NOW + timedelta(days=i))
    guard.admit_candidate(_valid_proposal("dim_last"), now=NOW + timedelta(days=40))

    with pytest.raises(AIOSProtocolError, match="cannot be scored"):
        guard.record_prediction("dim_000", hit=True, now=NOW)


# ---------------------------------------------------------------------------
# 恶意反思套娃：第 2 层物理切断
# ---------------------------------------------------------------------------


def test_recursion_is_cut_at_the_second_layer() -> None:
    guard = EvolutionGuard()
    assert MAX_REFLECTION_DEPTH == 2

    # 合法的 2 层反思可以完成
    assert guard.reflect("复盘昨天的判断", requested_depth=2) == ["layer-1", "layer-2"]

    # 恶意套娃：请求 5 层，第 3 层被物理切断
    with pytest.raises(RecursionDepthExceededError) as excinfo:
        guard.reflect("反思我的上一次反思，并反思这次反思……", requested_depth=5)

    assert excinfo.value.depth == 3
    assert excinfo.value.max_depth == 2
    assert excinfo.value.code is ErrorCode.INVALID_ARGUMENT
    assert guard.recursion.cut_count == 1


def test_recursion_depth_returns_to_zero_after_a_cut() -> None:
    guard = EvolutionGuard()
    with pytest.raises(RecursionDepthExceededError):
        guard.reflect("套娃", requested_depth=4)
    # 断路器不会卡死在高位
    assert guard.recursion.depth == 0
    # 之后仍可正常做 1 层反思
    assert guard.reflect("正常反思", requested_depth=1) == ["layer-1"]


# ---------------------------------------------------------------------------
# 冻结契约投影
# ---------------------------------------------------------------------------


def test_local_states_project_onto_frozen_lifecycle_without_new_values() -> None:
    assert to_frozen_lifecycle(DimensionTrialState.CANDIDATE) is DimensionLifecycle.CANDIDATE
    assert to_frozen_lifecycle(DimensionTrialState.TRIAL) is DimensionLifecycle.TRIAL
    assert to_frozen_lifecycle(DimensionTrialState.ACTIVE) is DimensionLifecycle.ACTIVE
    assert to_frozen_lifecycle(DimensionTrialState.EXPIRED) is DimensionLifecycle.REJECTED
    assert to_frozen_lifecycle(DimensionTrialState.ARCHIVED) is DimensionLifecycle.DORMANT
    # 冻结枚举本身未被改动：没有 EXPIRED / ARCHIVED
    frozen_values = {s.value for s in DimensionLifecycle}
    assert "expired" not in frozen_values
    assert "archived" not in frozen_values


def test_unknown_dimension_raises_keyerror() -> None:
    guard = EvolutionGuard()
    with pytest.raises(KeyError):
        guard.get("nope")
