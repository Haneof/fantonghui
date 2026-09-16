"""M3-001R 动态维度衍生三重硬门限状态机验收测试（宪法铁律 5）。

四大硬门禁：
1. 三重门限准入：跨 >= 2 物理域且持续 >= 3 天 -> CANDIDATE；30 天试用
   期预测准确率 >= 70% 否则 EXPIRED；每日反思配额严格 1 次；
2. 全局活跃维度硬顶 <= 32，超限按活跃度+贡献度淘汰末位至 ARCHIVED；
3. 自问自答死循环在第 2 层递归被物理切断。
"""

from __future__ import annotations

import pytest

from aios_core.dimensions.evolution_guard import (
    MAX_ACTIVE_DIMENSIONS,
    DimensionAdmissionError,
    DimensionEvolutionGuard,
    GuardLifecycle,
    QuotaExceededBlockError,
    ReflectionLoopCircuitError,
)


# ---------------------------------------------------------------------------
# 门限一：物理跨域持续异常准入
# ---------------------------------------------------------------------------


def test_gate1_single_domain_anomaly_is_rejected() -> None:
    guard = DimensionEvolutionGuard()
    with pytest.raises(DimensionAdmissionError):
        guard.submit_candidate(
            "dim-sleep-only", "深夜入睡延迟维度", ("睡眠",), 10, day=1
        )


def test_gate1_cross_domain_but_short_duration_is_rejected() -> None:
    guard = DimensionEvolutionGuard()
    with pytest.raises(DimensionAdmissionError):
        guard.submit_candidate(
            "dim-two-day", "睡眠+血压双域维度", ("睡眠", "血压"), 2, day=1
        )


def test_gate1_cross_domain_persistent_anomaly_admitted_as_candidate() -> None:
    guard = DimensionEvolutionGuard()
    record = guard.submit_candidate(
        "dim-sleep-bp",
        "睡眠异常与血压异常耦合维度",
        ("睡眠", "血压"),
        3,
        day=1,
    )
    assert record.lifecycle is GuardLifecycle.CANDIDATE
    assert record.anomaly_domains == ("睡眠", "血压")
    # 三域长时程异常同样准入。
    record3 = guard.submit_candidate(
        "dim-triple", "睡眠+血压+心率三域维度", ("睡眠", "血压", "心率"), 9, day=1
    )
    assert record3.lifecycle is GuardLifecycle.CANDIDATE


# ---------------------------------------------------------------------------
# 门限二：30 天试用期与预测检验
# ---------------------------------------------------------------------------


def test_gate2_trial_with_70_percent_predictions_becomes_active() -> None:
    guard = DimensionEvolutionGuard()
    guard.submit_candidate("dim-a", "预测力维度A", ("睡眠", "血压"), 4, day=0)
    for correct in (True, True, True, True, True, True, True, False, False, False):
        guard.record_prediction("dim-a", correct=correct)  # 7/10 = 70%
    assert guard.conclude_trial("dim-a", day=29) is GuardLifecycle.ACTIVE


def test_gate2_trial_below_70_percent_expires() -> None:
    guard = DimensionEvolutionGuard()
    guard.submit_candidate("dim-b", "解释力不足维度B", ("睡眠", "心率"), 5, day=0)
    for correct in (True, True, True, True, True, True, False, False, False, False):
        guard.record_prediction("dim-b", correct=correct)  # 6/10 = 60%
    assert guard.conclude_trial("dim-b", day=20) is GuardLifecycle.EXPIRED


def test_gate2_trial_over_30_days_window_expires_even_if_accurate() -> None:
    guard = DimensionEvolutionGuard()
    guard.submit_candidate("dim-c", "迟滞维度C", ("睡眠", "血压"), 3, day=0)
    for _ in range(9):
        guard.record_prediction("dim-c", correct=True)  # 100% 但拖过窗口
    assert guard.conclude_trial("dim-c", day=31) is GuardLifecycle.EXPIRED


def test_gate2_boundary_day_30_still_within_window() -> None:
    guard = DimensionEvolutionGuard()
    guard.submit_candidate("dim-d", "压线维度D", ("睡眠", "血压"), 3, day=0)
    for correct in (True, True, True, False):  # 3/4 = 75%
        guard.record_prediction("dim-d", correct=correct)
    assert guard.conclude_trial("dim-d", day=30) is GuardLifecycle.ACTIVE


# ---------------------------------------------------------------------------
# 门限三：每日反思配额严格 1 次
# ---------------------------------------------------------------------------


def test_gate3_daily_reflection_quota_is_exactly_one() -> None:
    guard = DimensionEvolutionGuard()
    guard.begin_reflection(day=7)  # 当日唯一配额
    with pytest.raises(QuotaExceededBlockError):
        guard.begin_reflection(day=7)  # 超额直接熔断
    guard.begin_reflection(day=8)  # 次日配额重置


# ---------------------------------------------------------------------------
# 全局活跃维度硬顶 <= 32 与末位淘汰
# ---------------------------------------------------------------------------


def _seed_active(guard: DimensionEvolutionGuard, count: int, start_day: int = 0) -> list[str]:
    ids = []
    for i in range(count):
        dim_id = f"dim-cap-{i:02d}"
        guard.submit_candidate(dim_id, f"容量维度{i}", ("睡眠", "血压"), 3, day=start_day)
        guard.record_prediction(dim_id, correct=True)
        guard.record_prediction(dim_id, correct=True)
        guard.record_prediction(dim_id, correct=False)  # 2/3 ≈ 66.7% < 70% -> 用 force_admit
        guard.force_admit_active(dim_id, day=start_day + 1)
        guard.note_scores(dim_id, activity_delta=float(i), contribution_delta=float(i))
        ids.append(dim_id)
    return ids


def test_cap_active_dimensions_hard_limited_to_32_with_eviction() -> None:
    assert MAX_ACTIVE_DIMENSIONS == 32
    guard = DimensionEvolutionGuard()
    ids = _seed_active(guard, 32)
    assert len(guard.active_dimensions()) == 32

    # dim-cap-00 的活跃度+贡献度最低（0+0），引入第 33 枚时它被末位归档。
    guard.submit_candidate("dim-new", "新晋维度", ("睡眠", "心率"), 4, day=10)
    evicted = guard.force_admit_active("dim-new", day=11)

    assert evicted == ["dim-cap-00"]
    assert guard.dimension("dim-cap-00").lifecycle is GuardLifecycle.ARCHIVED
    assert guard.dimension("dim-cap-00").archived_day == 11
    assert len(guard.active_dimensions()) == 32
    assert guard.dimension("dim-new").lifecycle is GuardLifecycle.ACTIVE

    # 连续引入 3 枚：每轮都严格淘汰当时的末位，硬顶恒为 32。
    for i in range(3):
        guard.submit_candidate(f"dim-x{i}", f"增援维度{i}", ("睡眠", "血压"), 3, day=20)
        guard.note_scores(f"dim-x{i}", activity_delta=100.0)
        guard.force_admit_active(f"dim-x{i}", day=20)
        assert len(guard.active_dimensions()) == 32


# ---------------------------------------------------------------------------
# 自问自答死循环熔断（第 2 层递归物理切断）
# ---------------------------------------------------------------------------


def test_recursion_circuit_breaks_at_second_reflection_layer() -> None:
    guard = DimensionEvolutionGuard()

    # 第 1 层反思：允许进入。
    depth = guard.enter_reflection_scope("我为什么创建了这枚维度？")
    assert depth == 1
    assert guard.reflection_depth == 1

    # 恶意 Prompt 诱导的反思套娃：第 2 层递归直接被物理切断。
    with pytest.raises(ReflectionLoopCircuitError):
        guard.enter_reflection_scope("我为什么要问'我为什么创建了这枚维度'？")
    assert guard.reflection_depth == 1  # 切断不污染已合法进入的作用域

    guard.exit_reflection_scope()
    assert guard.reflection_depth == 0


def test_malicious_self_answer_loop_is_simulated_and_cut() -> None:
    """模拟恶意注入：AI 在反思中再次触发反思（自问自答套娃）。"""

    guard = DimensionEvolutionGuard()

    def recursive_self_reflection(layer: int) -> int:
        guard.enter_reflection_scope(f"套娃反思 layer={layer}")
        try:
            return recursive_self_reflection(layer + 1)  # 恶意递归
        finally:
            if guard.reflection_depth > 0:
                guard.exit_reflection_scope()

    with pytest.raises(ReflectionLoopCircuitError):
        recursive_self_reflection(1)

    with pytest.raises(ReflectionLoopCircuitError):
        guard.exit_reflection_scope()  # 无活动作用域时退出同样熔断
