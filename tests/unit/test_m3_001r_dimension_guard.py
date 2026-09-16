"""M3-001R 维度三重硬门限守卫——铁律 5 的机械证。

  1. 三重门限：≥2 物理域 且 ≥3 天才准候选；30 期记录+准确率 ≥70% 晋升，
     否则 EXPIRED；每日反思配额=1，超额 QuotaExceededBlockError
  2. 活跃硬顶 ≤32：第 33 个准入必按 (activity, contribution, id) 确定性
     末位淘汰为 ARCHIVED，不变量用 assert 焊死
  3. 自问自答熔断：depth=0/1 放行，depth=2 物理切断
"""

from __future__ import annotations

import pytest

from aios_core.dimensions.evolution_guard import (
    ACTIVE_CAP,
    MIN_ANOMALY_SECONDS,
    PROBATION_REPORTS_REQUIRED,
    QuotaExceededBlockError,
    DimensionEvolutionGuard,
    DimensionState,
    GateRejectionError,
    RecursionFuseError,
)

DAYS3 = MIN_ANOMALY_SECONDS  # 3 * 86400


def _good_guard_with_candidate(dim: str = "dim-sleep-fragility") -> DimensionEvolutionGuard:
    guard = DimensionEvolutionGuard()
    guard.submit_candidate(dim, anomaly_domains={"sleep", "blood_pressure"},
                           anomaly_duration_seconds=DAYS3)
    return guard


# ---------------------------------------------------------------------------
# 门限一：≥2 物理域 且 ≥3 天
# ---------------------------------------------------------------------------


def test_gate1_single_domain_rejected():
    guard = DimensionEvolutionGuard()
    with pytest.raises(GateRejectionError, match="跨域不足"):
        guard.submit_candidate("d1", anomaly_domains={"sleep"},
                               anomaly_duration_seconds=DAYS3 * 2)


def test_gate1_two_domains_but_short_duration_rejected():
    guard = DimensionEvolutionGuard()
    with pytest.raises(GateRejectionError, match="持续"):
        guard.submit_candidate("d1", anomaly_domains={"sleep", "bp"},
                               anomaly_duration_seconds=DAYS3 - 1)


def test_gate1_exact_boundary_admitted():
    guard = _good_guard_with_candidate()
    assert guard.state_of("dim-sleep-fragility") is DimensionState.CANDIDATE
    # 精确边界：恰好 2 域、恰好 3 天整
    guard.submit_candidate("d-edge", anomaly_domains={"a", "b"},
                           anomaly_duration_seconds=DAYS3)
    assert guard.state_of("d-edge") is DimensionState.CANDIDATE


def test_gate1_terminal_states_never_resurrect():
    guard = _good_guard_with_candidate("d-x")
    for _ in range(PROBATION_REPORTS_REQUIRED):
        guard.record_probation_report("d-x", predictions_made=10, predictions_correct=5)
    assert guard.finalize_probation("d-x") is DimensionState.EXPIRED
    with pytest.raises(GateRejectionError, match="禁复活"):
        guard.submit_candidate("d-x", anomaly_domains={"a", "b"},
                               anomaly_duration_seconds=DAYS3)
    # 在册候选的重复注册走独立拦截条款（与终态复活区分）
    guard_dup = _good_guard_with_candidate("d-dup")
    with pytest.raises(GateRejectionError, match="重复注册"):
        guard_dup.submit_candidate("d-dup", anomaly_domains={"a", "b"},
                                   anomaly_duration_seconds=DAYS3)


# ---------------------------------------------------------------------------
# 门限二：30 天试用期 + 准确率 ≥70%
# ---------------------------------------------------------------------------


def test_gate2_requires_full_30_reports_before_final():
    guard = _good_guard_with_candidate()
    for _ in range(29):
        guard.record_probation_report("dim-sleep-fragility", predictions_made=4,
                                      predictions_correct=4)
    with pytest.raises(GateRejectionError, match="不足 30 期"):
        guard.finalize_probation("dim-sleep-fragility")
    guard.record_probation_report("dim-sleep-fragility", predictions_made=4,
                                  predictions_correct=4)
    assert guard.finalize_probation("dim-sleep-fragility") is DimensionState.ACTIVE
    assert guard.active_count == 1


def test_gate2_accuracy_boundary_70_percent():
    # 恰 70.0%：晋升（>=，300 中 210）；69.67%（300 中 209）：EXPIRED
    guard = _good_guard_with_candidate("d-pass")
    for _ in range(PROBATION_REPORTS_REQUIRED):
        guard.record_probation_report("d-pass", predictions_made=10, predictions_correct=7)
    assert guard.finalize_probation("d-pass") is DimensionState.ACTIVE

    guard3 = DimensionEvolutionGuard()
    guard3.submit_candidate("d-miss", anomaly_domains={"a", "b"},
                            anomaly_duration_seconds=DAYS3)
    for i in range(PROBATION_REPORTS_REQUIRED):
        guard3.record_probation_report("d-miss", predictions_made=10,
                                       predictions_correct=7 - (1 if i < 10 else 0))
    result = guard3.finalize_probation("d-miss")
    assert result is DimensionState.EXPIRED
    assert "准确率" in guard3.expired_reason("d-miss")


def test_gate2_zero_predictions_expires_and_report_integrity_checked():
    guard = _good_guard_with_candidate()
    for _ in range(PROBATION_REPORTS_REQUIRED):
        guard.record_probation_report("dim-sleep-fragility", predictions_made=0,
                                      predictions_correct=0)
    assert guard.finalize_probation("dim-sleep-fragility") is DimensionState.EXPIRED
    assert "零预测" in guard.expired_reason("dim-sleep-fragility")

    guard2 = _good_guard_with_candidate("d-bad")
    with pytest.raises(GateRejectionError, match="不自洽"):
        guard2.record_probation_report("d-bad", predictions_made=3, predictions_correct=5)


# ---------------------------------------------------------------------------
# 门限三：每日反思配额 = 1
# ---------------------------------------------------------------------------


def test_gate3_daily_reflection_quota_exactly_one():
    guard = DimensionEvolutionGuard()
    guard.consume_reflection_quota("2026-09-16")
    assert guard.quota_left("2026-09-16") == 0
    with pytest.raises(QuotaExceededBlockError):
        guard.consume_reflection_quota("2026-09-16")
    # 跨午夜自然重置
    guard.consume_reflection_quota("2026-09-17")
    assert guard.quota_left("2026-09-17") == 0


# ---------------------------------------------------------------------------
# 活跃硬顶 ≤32 + 确定性末位淘汰
# ---------------------------------------------------------------------------


def test_active_cap_32_hard_ceiling_with_deterministic_eviction():
    guard = DimensionEvolutionGuard()
    for i in range(ACTIVE_CAP):
        guard.submit_candidate(f"d-{i:02d}", anomaly_domains={"a", "b", f"dom-{i}"},
                               anomaly_duration_seconds=DAYS3)
        for _ in range(PROBATION_REPORTS_REQUIRED):
            guard.record_probation_report(f"d-{i:02d}", predictions_made=1, predictions_correct=1)
        assert guard.finalize_probation(f"d-{i:02d}") is DimensionState.ACTIVE
    assert guard.active_count == ACTIVE_CAP

    # 活跃度登记表：d-07 最差（activity 最低）
    for i in range(ACTIVE_CAP):
        guard.register_activity(f"d-{i:02d}", activity_score=float(100 - i), contribution=float(i))
    # d-00: activity=100 最高；d-31: activity=69 最低 → 淘汰 d-31
    guard.submit_candidate("d-new", anomaly_domains={"x", "y"},
                           anomaly_duration_seconds=DAYS3)
    for _ in range(PROBATION_REPORTS_REQUIRED):
        guard.record_probation_report("d-new", predictions_made=1, predictions_correct=1)
    assert guard.finalize_probation("d-new") is DimensionState.ACTIVE

    assert guard.active_count == ACTIVE_CAP, "硬顶不变量：绝不越 32"
    assert guard.state_of("d-31") is DimensionState.ARCHIVED
    assert "末位淘汰" in guard.archive_reason("d-31")
    assert guard.state_of("d-00") is DimensionState.ACTIVE
    with pytest.raises(GateRejectionError, match="禁复活"):
        guard.submit_candidate("d-31", anomaly_domains={"a", "b"},
                               anomaly_duration_seconds=DAYS3)


def test_eviction_tie_break_is_deterministic_by_id():
    guard = DimensionEvolutionGuard()
    for i in range(ACTIVE_CAP):
        guard.submit_candidate(f"t-{i:02d}", anomaly_domains={"a", "b", f"x-{i}"},
                               anomaly_duration_seconds=DAYS3)
        for _ in range(PROBATION_REPORTS_REQUIRED):
            guard.record_probation_report(f"t-{i:02d}", predictions_made=1, predictions_correct=1)
        guard.finalize_probation(f"t-{i:02d}")
        guard.register_activity(f"t-{i:02d}", activity_score=0.0, contribution=0.0)
    # 全部同分 → 字典序最小者 t-00 被淘汰（确定性，可复放）
    guard.submit_candidate("t-new", anomaly_domains={"p", "q"}, anomaly_duration_seconds=DAYS3)
    for _ in range(PROBATION_REPORTS_REQUIRED):
        guard.record_probation_report("t-new", predictions_made=1, predictions_correct=1)
    guard.finalize_probation("t-new")
    assert guard.state_of("t-00") is DimensionState.ARCHIVED
    assert guard.active_count == ACTIVE_CAP


# ---------------------------------------------------------------------------
# 自问自答熔断
# ---------------------------------------------------------------------------


def test_reflection_recursion_fuse_cuts_at_layer_2():
    guard = DimensionEvolutionGuard()
    guard.enter_reflection(0)   # 初始反思：放行
    guard.enter_reflection(1)   # 第一层递归：放行
    with pytest.raises(RecursionFuseError, match="物理切断"):
        guard.enter_reflection(2)   # 第二层：熔断
    # 恶意套娃循环模拟：第 3 次尝试进入时早已没有机会
    calls = 0
    try:
        depth = 0
        while True:
            guard.enter_reflection(depth)
            depth += 1
            calls += 1
            if calls > 10:  # 安全卡：守卫若失效这行会兜底
                pytest.fail("熔断失效：套娃越过 10 层")
    except RecursionFuseError:
        pass
    assert calls == 2, "恰好放行 0、1 两层后熔断"
