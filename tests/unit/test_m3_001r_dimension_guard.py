"""M3-001R 验收测试：动态维度衍生三重硬门限状态机（铁律 5）。

工单：``arena/agent-cognition-m3-001r``
实现：``src/aios_core/dimensions/evolution_guard.py``

实战情境
--------------------------------------------------------------------------
同一位长期高压用户（法务总监）连续多日出现**睡眠异常 + 血压异常**的跨域信号。
系统必须极度克制：不足 3 天不许立项、30 天试用期预测准确率不足 70% 立即失效、
每天最多做 1 次新维度自省、活跃维度全局硬顶 32、反思套娃第 2 层直接熔断。

四大硬门禁 ↔ 用例
--------------------------------------------------------------------------
1. 三重门限准入状态机 —— ``test_gate1_*``
2. 活跃维度全局硬顶 32 + 末位淘汰 —— ``test_gate2_*``
3. 自问自答死循环第 2 层熔断 —— ``test_gate3_*``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.dimensions.evolution_guard import (
    DAILY_REFLECTION_QUOTA,
    DIMENSION_TRIAL_DAYS,
    GATE1_MIN_DAYS,
    GATE1_MIN_DOMAINS,
    GATE2_MIN_ACCURACY,
    MAX_ACTIVE_DIMENSIONS,
    MAX_REFLECTION_RECURSION_DEPTH,
    CandidateStatus,
    DimensionCandidate,
    DimensionRegistry,
    EvolutionGuard,
    ImmaturePatternRejectedError,
    PhysicalDomain,
    QuotaExceededBlockError,
    RecursiveReflectionCutError,
    ReflectionQuota,
    ReflectionRecursionGuard,
    ReviewOutcome,
    retention_summary,
)

# ---------------------------------------------------------------------------
# 基线
# ---------------------------------------------------------------------------

T_DAY0 = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
SLEEP = PhysicalDomain.SLEEP
CARDIO = PhysicalDomain.CARDIOVASCULAR
METABOLIC = PhysicalDomain.METABOLIC

CROSS_DOMAIN = (SLEEP, CARDIO)
TRIAL_DAYS = DIMENSION_TRIAL_DAYS


def _feed_cross_domain_anomalies(
    guard: EvolutionGuard,
    *,
    days: int,
    domains: tuple[PhysicalDomain, ...] = CROSS_DOMAIN,
    start: datetime = T_DAY0,
) -> None:
    """连续 days 天在多个物理域上都出现客观异常（客观事实，不是模型臆想）。"""
    for offset in range(days):
        moment = start - timedelta(days=offset)
        for domain in domains:
            metric = "sleep_efficiency" if domain is SLEEP else "blood_pressure_systolic"
            value = 0.42 if domain is SLEEP else 148.0
            guard.observe_anomaly(
                domain, observed_at=moment, metric=metric, value=value, severity=0.8
            )


def _active_candidate(index: int, *, activity: float, contribution: float) -> DimensionCandidate:
    return DimensionCandidate(
        candidate_id=f"dim_{index:03d}",
        name=f"衍生维度 #{index:03d}",
        domains=CROSS_DOMAIN,
        proposed_at=T_DAY0 - timedelta(days=60),
        activity_score=activity,
        contribution_score=contribution,
    )


# ===========================================================================
# 硬门禁 1：三重门限准入状态机
# ===========================================================================


def test_gate1_single_domain_anomaly_is_rejected_without_burning_quota() -> None:
    """门限一：只跨 1 个物理域 —— 无论多久都不许立项，且不消耗当日自省配额。"""
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=10, domains=(SLEEP,))
    verdict = guard.gate_one_verdict((SLEEP,))

    assert verdict.allowed is False
    assert verdict.distinct_domains == 1 < GATE1_MIN_DOMAINS
    assert "未达跨域门限" in verdict.reason

    with pytest.raises(ImmaturePatternRejectedError) as excinfo:
        guard.submit_candidate("dim_sleep_only", name="睡眠单域", domains=[SLEEP], now=T_DAY0)
    assert excinfo.value.context["reason"] == "immature_pattern"
    assert excinfo.value.context["distinct_domains"] == 1
    # 机械拒绝不烧配额：当天那次自省机会必须留着给真正成熟的模式
    assert guard.quota.used_on(T_DAY0.date()) == 0
    assert guard.quota.remaining(T_DAY0) == DAILY_REFLECTION_QUOTA


def test_gate1_cross_domain_but_too_short_is_rejected() -> None:
    """门限一：跨了 2 个域，但共同持续只有 2 天（<3 天）—— 仍然不许立项。"""
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=GATE1_MIN_DAYS - 1)

    verdict = guard.gate_one_verdict()
    assert verdict.allowed is False
    assert verdict.distinct_domains == GATE1_MIN_DOMAINS
    assert verdict.overlapping_days == GATE1_MIN_DAYS - 1
    assert f"共同持续不足 {GATE1_MIN_DAYS} 天" in verdict.reason

    with pytest.raises(ImmaturePatternRejectedError):
        guard.submit_candidate("dim_too_short", name="太短", domains=CROSS_DOMAIN, now=T_DAY0)
    assert guard.quota.used_on(T_DAY0.date()) == 0


def test_gate1_cross_domain_sustained_three_days_opens_the_candidate() -> None:
    """门限一通过：跨 2 域且共同持续 >= 3 天 —— 允许提交 CANDIDATE。"""
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=5)

    verdict = guard.gate_one_verdict()
    assert verdict.allowed is True
    assert verdict.distinct_domains == 2 and verdict.overlapping_days >= GATE1_MIN_DAYS
    assert set(verdict.domains) == set(CROSS_DOMAIN)
    assert all(span.days >= GATE1_MIN_DAYS for span in verdict.spans)

    admission = guard.submit_candidate(
        "dim_stress_recovery",
        name="压力-恢复失衡象限",
        description="睡眠结构碎片化与夜间血压持续上冲同时成立",
        domains=CROSS_DOMAIN,
        now=T_DAY0,
    )
    assert admission.candidate.status is CandidateStatus.CANDIDATE
    assert admission.candidate.trial_ends_at == T_DAY0 + timedelta(days=TRIAL_DAYS)
    assert admission.quota_used_today == 1
    assert guard.audit()["candidates_on_trial"] == ["dim_stress_recovery"]


def test_gate1_quota_blocks_the_second_reflection_of_the_day() -> None:
    """门限三：每日 1 次 —— 第二条候选当天直接熔断。"""
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=5)
    guard.submit_candidate("dim_first", name="第一条", domains=CROSS_DOMAIN, now=T_DAY0)

    with pytest.raises(QuotaExceededBlockError) as excinfo:
        guard.submit_candidate("dim_second", name="第二条", domains=CROSS_DOMAIN, now=T_DAY0)
    context = excinfo.value.context
    assert context["reason"] == "reflection_quota_exceeded"
    assert context["used"] == 1 and context["limit"] == DAILY_REFLECTION_QUOTA
    assert context["day"] == T_DAY0.date().isoformat()

    # 次日配额自动复位（不是永久封禁）
    tomorrow = T_DAY0 + timedelta(days=1)
    assert guard.quota.remaining(tomorrow) == DAILY_REFLECTION_QUOTA
    guard.submit_candidate("dim_second", name="第二条", domains=CROSS_DOMAIN, now=tomorrow)
    assert guard.quota.used_on(tomorrow.date()) == 1


def test_gate1_quota_is_strictly_one_reflection_per_day() -> None:
    quota = ReflectionQuota()
    assert quota.consume(T_DAY0) == 1
    assert quota.remaining(T_DAY0) == 0
    for _ in range(3):
        with pytest.raises(QuotaExceededBlockError):
            quota.consume(T_DAY0)
    assert quota.used_on(T_DAY0.date()) == DAILY_REFLECTION_QUOTA == 1


def test_gate1_trial_requires_seventy_percent_prediction_accuracy() -> None:
    """门限二：30 天试用期预测检验，>=70% 才晋升，低于即失效。"""
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=5)
    guard.submit_candidate("dim_strong", name="强解释力", domains=CROSS_DOMAIN, now=T_DAY0)
    guard.submit_candidate(
        "dim_weak", name="弱解释力", domains=CROSS_DOMAIN, now=T_DAY0 + timedelta(days=1)
    )

    day20 = T_DAY0 + timedelta(days=20)
    strong = guard.review_candidate(
        "dim_strong", now=day20, predictions_total=20, predictions_correct=14, explanation_days=20
    )
    assert strong.outcome is ReviewOutcome.PROMOTED, "70% 恰好达标必须晋升"
    assert strong.accuracy == pytest.approx(GATE2_MIN_ACCURACY)
    assert guard.candidate("dim_strong").status is CandidateStatus.ACTIVE
    assert guard.active_count == 1

    weak = guard.review_candidate(
        "dim_weak", now=day20 + timedelta(days=1), predictions_total=20, predictions_correct=13, explanation_days=20
    )
    assert weak.outcome is ReviewOutcome.EXPIRED, "65% 必须自动失效"
    assert weak.accuracy < GATE2_MIN_ACCURACY
    assert guard.candidate("dim_weak").status is CandidateStatus.EXPIRED
    assert guard.active_count == 1, "失效候选绝不占用全局硬顶"


def test_gate1_trial_expires_when_thirty_days_pass_without_proof() -> None:
    """门限二：30 天期满仍未证明解释力 -> 自动 EXPIRED。"""
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=5)
    guard.submit_candidate("dim_late", name="迟到者", domains=CROSS_DOMAIN, now=T_DAY0)

    after_trial = T_DAY0 + timedelta(days=TRIAL_DAYS + 1)
    review = guard.review_candidate(
        "dim_late",
        now=after_trial,
        predictions_total=3,
        predictions_correct=2,
        explanation_days=3,  # 解释力不连续（只有 3 天）
    )
    assert review.outcome is ReviewOutcome.EXPIRED
    assert review.explanations_continuous is False
    assert "30 天试用期届满" in review.reason
    assert guard.registry.expired() == ()
    assert guard.candidate("dim_late").status is CandidateStatus.EXPIRED


def test_gate1_candidate_cannot_be_reviewed_twice_or_after_expiry() -> None:
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=5)
    guard.submit_candidate("dim_once", name="一次性", domains=CROSS_DOMAIN, now=T_DAY0)
    guard.review_candidate(
        "dim_once",
        now=T_DAY0 + timedelta(days=10),
        predictions_total=10,
        predictions_correct=5,
        explanation_days=10,
    )
    with pytest.raises(Exception) as excinfo:
        guard.review_candidate(
            "dim_once",
            now=T_DAY0 + timedelta(days=11),
            predictions_total=11,
            predictions_correct=9,
            explanation_days=11,
        )
    assert getattr(excinfo.value, "context", {}).get("reason") == "candidate_not_on_trial"

    with pytest.raises(Exception) as unknown:
        guard.review_candidate(
            "dim_ghost", now=T_DAY0, predictions_total=1, predictions_correct=1, explanation_days=1
        )
    assert getattr(unknown.value, "context", {}).get("reason") == "unknown_candidate"


def test_gate1_duplicate_candidate_id_is_rejected() -> None:
    guard = EvolutionGuard()
    _feed_cross_domain_anomalies(guard, days=5)
    guard.submit_candidate("dim_dup", name="首次", domains=CROSS_DOMAIN, now=T_DAY0)
    with pytest.raises(Exception) as excinfo:
        guard.submit_candidate(
            "dim_dup", name="重复", domains=CROSS_DOMAIN, now=T_DAY0 + timedelta(days=1)
        )
    assert getattr(excinfo.value, "context", {}).get("reason") == "duplicate_candidate"


def test_gate1_gap_days_break_the_sustained_window() -> None:
    """中间断了 2 天：连续窗口被切断，之前的 3 天不再算"持续"。"""
    guard = EvolutionGuard()
    for offset in (10, 9, 8, 0):  # 8/9/10 号连续 3 天 + 今天单点，中间 7 天断档
        moment = T_DAY0 - timedelta(days=offset)
        for domain in CROSS_DOMAIN:
            guard.observe_anomaly(domain, observed_at=moment, metric="m", value=1.0)

    verdict = guard.gate_one_verdict()
    assert verdict.allowed is False, "断档后不得再认定为连续异常"
    with pytest.raises(ImmaturePatternRejectedError):
        guard.submit_candidate("dim_gap", name="断档", domains=CROSS_DOMAIN, now=T_DAY0)


# ===========================================================================
# 硬门禁 2：活跃维度全局硬顶 32 + 末位淘汰
# ===========================================================================


def test_gate2_active_dimensions_respect_cap_and_default_capacity_is_512() -> None:
    # 默认解除 32 限制，认知空间释放至 512
    default_registry = DimensionRegistry()
    assert default_registry.max_active == MAX_ACTIVE_DIMENSIONS == 512

    # 指定容量 cap=32 时，严格保持末位淘汰
    registry = DimensionRegistry(max_active=32)
    assert registry.max_active == 32

    peak = 0
    for index in range(60):
        registry.admit(_active_candidate(index, activity=0.5 + index * 0.001, contribution=0.5))
        peak = max(peak, registry.active_count)

    assert registry.active_count == 32, "活跃维度硬顶必须严格守住"
    assert peak <= 32
    assert len(registry.archived()) == 60 - 32
    assert all(c.status is CandidateStatus.ARCHIVED for c in registry.archived())


def test_gate2_full_registry_evicts_the_lowest_utility_dimension() -> None:
    registry = DimensionRegistry(max_active=32)
    for index in range(32):
        registry.admit(
            _active_candidate(index, activity=0.9 - index * 0.01, contribution=0.8 - index * 0.01)
        )
    expected_victim = registry.admission_plan()
    assert expected_victim is not None and expected_victim.candidate_id == "dim_031", (
        "活跃度/贡献度双低的末位必须成为淘汰对象"
    )

    newcomer = _active_candidate(999, activity=1.0, contribution=1.0)
    archived_id = registry.admit(newcomer)

    assert archived_id == "dim_031"
    assert registry.active_count == 32, "淘汰后立即补位，硬顶不变"
    assert registry.archived()[0].candidate_id == "dim_031"
    assert registry.archived()[0].status is CandidateStatus.ARCHIVED
    assert "容量上限" in (registry.archived()[0].status_reason or "")
    assert any(c.candidate_id == "dim_999" for c in registry.active())


def test_gate2_promotion_through_the_guard_respects_the_cap() -> None:
    """走守卫正规路径晋升：硬顶已满时，晋升必须伴随一次归档（不静默超限）。"""
    registry = DimensionRegistry(max_active=32)
    for index in range(32):
        registry.admit(
            _active_candidate(index, activity=0.9 - index * 0.01, contribution=0.9 - index * 0.01)
        )
    guard = EvolutionGuard(registry=registry)
    _feed_cross_domain_anomalies(guard, days=5)
    guard.submit_candidate("dim_newcomer", name="新维度", domains=CROSS_DOMAIN, now=T_DAY0)

    review = guard.review_candidate(
        "dim_newcomer",
        now=T_DAY0 + timedelta(days=21),
        predictions_total=20,
        predictions_correct=18,
        explanation_days=21,
    )
    assert review.outcome is ReviewOutcome.PROMOTED
    assert review.archived_dimension_id == "dim_031"
    assert guard.active_count == 32
    assert guard.audit()["archived_dimensions"] == ["dim_031"]

    summary = retention_summary(guard.registry)
    assert summary == {"active": 32, "archived": 1, "expired": 0}
    print(
        f"[M3-001R 容量] 活跃={summary['active']}/32 "
        f"归档={summary['archived']} 淘汰末位={review.archived_dimension_id}"
    )


def test_gate2_registry_cap_must_be_positive() -> None:
    with pytest.raises(Exception) as excinfo:
        DimensionRegistry(max_active=0)
    assert getattr(excinfo.value, "context", {}).get("reason") == "invalid_dimension_cap"


# ===========================================================================
# 硬门禁 3：自问自答死循环在第二层熔断
# ===========================================================================


def test_gate3_reflection_recursion_is_cut_at_the_second_layer() -> None:
    guard = EvolutionGuard()
    assert guard.recursion_guard.max_depth == MAX_REFLECTION_RECURSION_DEPTH == 1

    # 第 1 层自省：允许（一次有意义的反思）
    assert guard.consider_reflection(1) == 1
    assert guard.recursion_guard.admitted_count == 1

    # 恶意 Prompt 诱导的套娃：第 2 层立即物理切断
    with pytest.raises(RecursiveReflectionCutError) as excinfo:
        guard.consider_reflection(2)
    context = excinfo.value.context
    assert context["reason"] == "reflection_recursion_cut"
    assert context["depth"] == 2 and context["max_depth"] == MAX_REFLECTION_RECURSION_DEPTH
    assert guard.recursion_guard.cut_count == 1
    assert guard.audit()["reflection_cuts"] == 1


def test_gate3_malicious_self_interrogation_loop_is_cut_immediately() -> None:
    """模拟"追问到底"的死循环攻击：第 2 层就被斩断，绝不放行到第 3、4… 层。"""
    guard = EvolutionGuard()
    cut_at: list[int] = []
    for depth in range(1, 6):
        try:
            guard.consider_reflection(depth)
        except RecursiveReflectionCutError as error:
            cut_at.append(error.context["depth"])
            break

    assert cut_at == [2], "熔断必须发生在第 2 层，而不是拖到更深处"
    assert guard.recursion_guard.admitted_count == 1
    assert guard.recursion_guard.cut_count == 1


def test_gate3_recursion_guard_rejects_invalid_depths() -> None:
    guard = ReflectionRecursionGuard()
    for bad_depth in (0, -1):
        with pytest.raises(Exception) as excinfo:
            guard.enter(bad_depth)
        assert getattr(excinfo.value, "context", {}).get("reason") == "invalid_reflection_depth"


# ===========================================================================
# 端到端：一个月的克制演化
# ===========================================================================


def test_month_of_restrained_evolution_end_to_end() -> None:
    guard = EvolutionGuard()

    # 第 1 周：睡眠 + 血压跨域异常持续出现；曾有一次单域噪声被机械拒绝
    _feed_cross_domain_anomalies(guard, days=7)
    guard.observe_anomaly(
        METABOLIC, observed_at=T_DAY0, metric="fasting_glucose", value=5.4, severity=0.3
    )
    with pytest.raises(ImmaturePatternRejectedError):
        guard.submit_candidate("dim_noise", name="单域噪声", domains=[METABOLIC], now=T_DAY0)

    # 第 1 天：立项（唯一一次自省）
    guard.submit_candidate(
        "dim_stress_recovery", name="压力-恢复失衡", domains=CROSS_DOMAIN, now=T_DAY0
    )
    with pytest.raises(QuotaExceededBlockError):
        guard.submit_candidate("dim_greedy", name="贪心第二条", domains=CROSS_DOMAIN, now=T_DAY0)

    # 第 24 天：预测检验达标 -> 晋升
    review = guard.review_candidate(
        "dim_stress_recovery",
        now=T_DAY0 + timedelta(days=24),
        predictions_total=24,
        predictions_correct=18,
        explanation_days=24,
    )
    assert review.outcome is ReviewOutcome.PROMOTED
    assert review.accuracy >= GATE2_MIN_ACCURACY

    # 同期：一个不达标的候选（跨域成立但预测力不足）自动失效
    guard.submit_candidate(
        "dim_hypothesis", name="假说", domains=CROSS_DOMAIN, now=T_DAY0 + timedelta(days=2)
    )
    expired = guard.review_candidate(
        "dim_hypothesis",
        now=T_DAY0 + timedelta(days=25),
        predictions_total=10,
        predictions_correct=6,
        explanation_days=10,
    )
    assert expired.outcome is ReviewOutcome.EXPIRED

    audit = guard.audit()
    assert audit["active_dimensions"] == 1
    assert audit["candidates_on_trial"] == []
    assert audit["expired_candidates"] == ["dim_hypothesis"], "试用期未达标的候选必须留下失效记录"
    assert audit["expired_dimensions"] == [], "它从未成为活跃维度，不该污染活跃维度台账"
    assert guard.registry.active()[0].candidate_id == "dim_stress_recovery"
    print(
        f"[M3-001R 一个月] 事实数={audit['anomaly_observations']} 活跃维度={audit['active_dimensions']} "
        f"失效候选={audit['expired_candidates']} 归档={audit['archived_dimensions']} "
        f"熔断次数={audit['reflection_cuts']}"
    )
