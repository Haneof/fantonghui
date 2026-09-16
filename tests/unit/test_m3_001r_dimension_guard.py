"""M3-001R 动态维度衍生三重硬门限状态机 —— 铁律 5 落实压测。

宪法铁律 5：严禁 AI 无休止地自言自语、虚假自省导致维度爆炸。
（本测试不使用"借钱/买礼物/聊天"类低幼样例，全部基于高压创业者
的跨域生理-商业信号：睡眠剥夺、血压异常、对赌回购压力、心律失常。）

四大硬门禁：
1. 三重门限准入：跨 ≥2 物理域 + 持续 ≥3 天才准立项；30 天试用 +
   预测准确率 ≥70%；每日反思配额严格 1 次（超额抛
   QuotaExceededBlockError）；
2. 活跃维度全局硬顶 ≤32：满员晋升自动末位淘汰归档；
3. 自问自答死循环熔断：第 2 层递归物理切断。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.dimensions.evolution_guard import (
    ACTIVE_DIMENSION_HARD_CAP,
    CandidateDimension,
    CandidateRejectedError,
    DimensionLifecycleState,
    DomainAnomaly,
    EvolutionGuard,
    QuotaExceededBlockError,
    ReflectionLoopCutError,
    TRIAL_DAYS,
    TRIAL_PREDICTION_ACCURACY_FLOOR,
)

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 8, 0, 0, tzinfo=UTC)


def _valid_anomalies() -> list[DomainAnomaly]:
    """睡眠 + 血压双物理域，持续 6 天的真实异常区间。"""
    return [
        DomainAnomaly(
            domain="sleep",
            first_seen=T0,
            last_seen=T0 + timedelta(days=6),
            severity_note="连续深夜 01:40 后入睡，深睡占比 <8%",
        ),
        DomainAnomaly(
            domain="blood_pressure",
            first_seen=T0 + timedelta(hours=8),
            last_seen=T0 + timedelta(days=6, hours=4),
            severity_note="晨间收缩压均值抬升 18mmHg",
        ),
    ]


# ======================================================================
# 门禁一：三重门限准入状态机
# ======================================================================

def test_gate1_valid_cross_domain_proposal_admitted() -> None:
    guard = EvolutionGuard()
    candidate = guard.propose_dimension(
        "dim_founder_burnout",
        "创始人过载综合征（睡眠×血压×对赌压力）",
        _valid_anomalies(),
        at=T0 + timedelta(days=7),
    )
    assert candidate.state is DimensionLifecycleState.CANDIDATE
    assert set(candidate.domains) == {"sleep", "blood_pressure"}


def test_gate1_rejects_single_domain() -> None:
    guard = EvolutionGuard()
    with pytest.raises(CandidateRejectedError) as excinfo:
        guard.propose_dimension(
            "dim_sleep_only",
            "单域提案（不足）",
            [DomainAnomaly(domain="sleep", first_seen=T0, last_seen=T0 + timedelta(days=9))],
            at=T0 + timedelta(days=10),
        )
    assert "cross-domain" in excinfo.value.reason


def test_gate1_rejects_short_anomaly_duration() -> None:
    guard = EvolutionGuard()
    with pytest.raises(CandidateRejectedError) as excinfo:
        guard.propose_dimension(
            "dim_short_burst",
            "48小时双域短促异常（不足）",
            [
                DomainAnomaly(domain="sleep", first_seen=T0, last_seen=T0 + timedelta(days=2)),
                DomainAnomaly(domain="hr", first_seen=T0, last_seen=T0 + timedelta(days=2)),
            ],
            at=T0 + timedelta(days=2, hours=1),
        )
    assert "duration" in excinfo.value.reason


def test_gate1_trial_requires_30_days_and_70pct_accuracy() -> None:
    guard = EvolutionGuard()
    guard.propose_dimension(
        "dim_founder_burnout", "创始人过载综合征", _valid_anomalies(),
        at=T0 + timedelta(days=7),
    )
    guard.begin_trial("dim_founder_burnout", at=T0 + timedelta(days=7))
    # 12 条预测：9 对 3 错 = 75%（≥70%）
    for i in range(12):
        guard.record_prediction(
            "dim_founder_burnout",
            f"pred_{i:03d}",
            at=T0 + timedelta(days=7 + i * 2),
            correct=i % 4 != 3,
        )
    # 未满 30 天：复核不改变状态
    assert guard.review_trial(
        "dim_founder_burnout", at=T0 + timedelta(days=7 + TRIAL_DAYS - 3)
    ) is DimensionLifecycleState.TRIAL
    # 满 30 天：75% ≥ 70% → ACTIVE
    assert guard.review_trial(
        "dim_founder_burnout", at=T0 + timedelta(days=7 + TRIAL_DAYS)
    ) is DimensionLifecycleState.ACTIVE


def test_gate1_trial_expires_below_accuracy_floor() -> None:
    guard = EvolutionGuard()
    guard.propose_dimension(
        "dim_weak_signal", "弱信号维度（应失效）", _valid_anomalies(),
        at=T0 + timedelta(days=7),
    )
    guard.begin_trial("dim_weak_signal", at=T0 + timedelta(days=7))
    for i in range(10):  # 40% 准确率 < 70%
        guard.record_prediction(
            "dim_weak_signal", f"pred_{i:02d}",
            at=T0 + timedelta(days=9 + i * 2), correct=i % 10 < 4,
        )
    assert guard.review_trial(
        "dim_weak_signal", at=T0 + timedelta(days=7 + TRIAL_DAYS)
    ) is DimensionLifecycleState.EXPIRED


def test_gate1_no_predictions_at_all_expires() -> None:
    guard = EvolutionGuard()
    guard.propose_dimension(
        "dim_silent", "零预测维度（无解释力证据）", _valid_anomalies(),
        at=T0 + timedelta(days=7),
    )
    guard.begin_trial("dim_silent", at=T0 + timedelta(days=7))
    assert guard.review_trial(
        "dim_silent", at=T0 + timedelta(days=7 + TRIAL_DAYS)
    ) is DimensionLifecycleState.EXPIRED


def test_gate1_daily_reflection_quota_is_strictly_one() -> None:
    guard = EvolutionGuard()
    day = T0 + timedelta(days=30)
    guard.daily_reflection_allowance(at=day)          # 第 1 次：通过
    with pytest.raises(QuotaExceededBlockError):
        guard.daily_reflection_allowance(at=day + timedelta(hours=1))
    with pytest.raises(QuotaExceededBlockError):
        guard.daily_reflection_allowance(at=day + timedelta(hours=2))
    # 次日配额刷新
    guard.daily_reflection_allowance(at=day + timedelta(days=1))


# ======================================================================
# 门禁二：活跃维度全局硬顶 ≤32 与末位淘汰
# ======================================================================

def test_gate2_active_cap_32_with_lru_eviction() -> None:
    guard = EvolutionGuard()
    at = T0
    for i in range(ACTIVE_DIMENSION_HARD_CAP):
        dim_id = f"dim_{i:02d}"
        guard.propose_dimension(
            dim_id,
            f"衍生维度#{i}",
            _valid_anomalies(),
            at=at,
        )
        guard.begin_trial(dim_id, at=at)
        # 全部给满分预测：12/12 = 100% 准确率
        for p in range(12):
            guard.record_prediction(
                dim_id, f"p{i}_{p}", at=at + timedelta(days=p % 20 + 1), correct=True
            )
        guard.review_trial(dim_id, at=at + timedelta(days=TRIAL_DAYS))
        at = at + timedelta(hours=1)

    assert len(guard.active_dimensions()) == ACTIVE_DIMENSION_HARD_CAP
    assert guard.last_evicted() is None  # 尚未满员晋升

    # 第 33 个维度晋升：必须先末位淘汰贡献最低者
    guard.record_contribution("dim_00", 0.0)   # dim_00 贡献最低
    for p in range(12):
        guard.record_contribution(f"dim_{i:02d}", 0.0)
    guard.propose_dimension(
        "dim_overflow", "第33维度", _valid_anomalies(), at=at,
    )
    guard.begin_trial("dim_overflow", at=at)
    for p in range(12):
        guard.record_prediction("dim_overflow", f"po_{p}", at=at + timedelta(days=p + 1), correct=True)
    assert guard.review_trial("dim_overflow", at=at + timedelta(days=TRIAL_DAYS)) is (
        DimensionLifecycleState.ACTIVE
    )
    # 活跃数仍然严格 ≤ 32
    assert len(guard.active_dimensions()) == ACTIVE_DIMENSION_HARD_CAP
    # 被淘汰者是贡献/活跃度最低者，且状态为 ARCHIVED（历史保留）
    assert guard.last_evicted() == "dim_00"
    assert guard.dimension_state("dim_00") is DimensionLifecycleState.ARCHIVED
    assert "hard-cap eviction" in guard._dimensions["dim_00"].archived_reason  # noqa: SLF001
    # 新维度在列
    assert "dim_overflow" in guard.active_dimensions()


def test_gate2_eviction_never_exceeds_cap_under_burst() -> None:
    guard = EvolutionGuard()
    at = T0
    # 连续晋升 40 个：任意时刻活跃数都不得突破 32
    for i in range(40):
        dim_id = f"dim_burst_{i:02d}"
        guard.propose_dimension(dim_id, f"突发#{i}", _valid_anomalies(), at=at)
        guard.begin_trial(dim_id, at=at)
        for p in range(12):
            guard.record_prediction(
                dim_id, f"bp{i}_{p}", at=at + timedelta(days=p % 25 + 1), correct=True
            )
        guard.review_trial(dim_id, at=at + timedelta(days=TRIAL_DAYS))
        assert len(guard.active_dimensions()) <= ACTIVE_DIMENSION_HARD_CAP
        at = at + timedelta(hours=1)
    assert len(guard.active_dimensions()) == ACTIVE_DIMENSION_HARD_CAP


# ======================================================================
# 门禁三：自问自答死循环熔断
# ======================================================================

def test_gate3_reflection_recursion_cut_at_second_layer() -> None:
    guard = EvolutionGuard()
    guard.begin_reflection()  # 第 1 层：允许
    with pytest.raises(ReflectionLoopCutError) as excinfo:
        guard.begin_reflection()  # 第 2 层：物理切断
    assert excinfo.value.depth == 2
    # 切断后套娃栈整体归零（物理切断语义）：可正常开启全新会话
    depth = guard.begin_reflection()
    assert depth == 1
    guard.end_reflection()


def test_gate3_nested_reflection_loop_is_broken_completely() -> None:
    """恶意 Prompt 诱导反思套娃：递归 10 层，第 2 层即被熔断。"""

    def malicious_self_talk(guard: EvolutionGuard, depth: int) -> int:
        try:
            guard.begin_reflection()  # 第 2 层进入时抛出
        except ReflectionLoopCutError:
            return depth + 1         # 物理切断点
        return malicious_self_talk(guard, depth + 1)

    guard = EvolutionGuard()
    guard.begin_reflection()
    cut_at = malicious_self_talk(guard, 1)
    assert cut_at == 2  # 递归在第 2 层被物理切断，永远不会到达第 10 层
    guard.end_reflection()


def test_gate3_reflection_quota_and_loop_breaker_compose() -> None:
    """反思配额（门限三）与递归熔断独立生效：互不抵消。"""
    guard = EvolutionGuard()
    day = T0 + timedelta(days=5)
    guard.daily_reflection_allowance(at=day)
    guard.begin_reflection()
    with pytest.raises(ReflectionLoopCutError):
        guard.begin_reflection()
    with pytest.raises(QuotaExceededBlockError):
        guard.daily_reflection_allowance(at=day)
    guard.end_reflection()
