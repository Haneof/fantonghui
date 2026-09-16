"""M3-001R 动态维度衍生三重硬门限状态机（铁律 5）验收单测。

1. 三重门限：跨 2 物理域+持续 3 天才准入；30 天试用 >=70% 才转正；
   每日反思配额 == 1，超额 QuotaExceededBlockError。
2. 全局活跃维度 ≤ 32 硬顶，末位（活跃度, 贡献度, 提案日）淘汰归档。
3. 自问自答死循环：第 2 层递归物理切断 ReflectionLoopBreaker。
"""

from __future__ import annotations

import pytest

from aios_core.dimensions.evolution_guard_independent2 import (
    AnomalyEvidence,
    DimensionGateRejection,
    DimensionState,
    EvolutionGuard,
    PhysicalDomain,
    QuotaExceededBlockError,
    ReflectionLoopBreaker,
)

DAY0 = 100


def _evidence(*pairs: tuple[PhysicalDomain, int, int]) -> list[AnomalyEvidence]:
    return [
        AnomalyEvidence(domain=d, first_seen_day=a, last_seen_day=b, description=f"{d.value}-anomaly")
        for d, a, b in pairs
    ]


def _submit_valid(guard: EvolutionGuard, cid: str, *, day: int = DAY0) -> None:
    guard.submit(
        cid,
        name=f"认知维度-{cid}",
        evidence=_evidence(
            (PhysicalDomain.SLEEP, day - 4, day - 1),            # 4 天持续
            (PhysicalDomain.BLOOD_PRESSURE, day - 3, day - 1),   # 3 天持续
        ),
        day=day,
    )


# ---------------------------------------------------------------------------
# 门一：物理跨域持续异常
# ---------------------------------------------------------------------------

def test_gate_one_rejects_insufficient_domain_and_sustain() -> None:
    guard = EvolutionGuard()
    # 单物理域：拒绝（哪怕持续 7 天）
    with pytest.raises(DimensionGateRejection):
        guard.submit(
            "single_domain",
            name="睡眠单域异常",
            evidence=_evidence((PhysicalDomain.SLEEP, DAY0 - 7, DAY0 - 1)),
            day=DAY0,
        )
    # 跨 2 域但最短持续 2 天 < 3 天：拒绝
    with pytest.raises(DimensionGateRejection):
        guard.submit(
            "too_short",
            name="双域但不足三天",
            evidence=_evidence(
                (PhysicalDomain.SLEEP, DAY0 - 2, DAY0 - 1),
                (PhysicalDomain.BLOOD_PRESSURE, DAY0 - 2, DAY0 - 1),
            ),
            day=DAY0,
        )
    assert guard.gate_one_rejections == 2


def test_gate_one_admits_two_domains_three_days() -> None:
    guard = EvolutionGuard()
    _submit_valid(guard, "c_ok")
    assert guard.state_of("c_ok") is DimensionState.CANDIDATE


# ---------------------------------------------------------------------------
# 门二：30 天试用期与预测准确率
# ---------------------------------------------------------------------------

def _run_predictions(guard: EvolutionGuard, cid: str, wins: int, total: int) -> None:
    for i in range(total):
        guard.record_prediction(cid, day=DAY0 + 1 + i % 20, success=i < wins)


def test_gate_two_expires_below_70_and_zero_sample() -> None:
    guard = EvolutionGuard()
    _submit_valid(guard, "c_69")
    _run_predictions(guard, "c_69", wins=69, total=100)  # 69% 不达标
    assert guard.resolve_probation("c_69", day=DAY0 + 30) is DimensionState.EXPIRED

    _submit_valid(guard, "c_none")
    # 零次预测绝不许转正
    assert guard.resolve_probation("c_none", day=DAY0 + 30) is DimensionState.EXPIRED

    # 未转正前不可自省试用被锁——已 EXPIRED 再 resolve 保持终态
    assert guard.resolve_probation("c_69", day=DAY0 + 100) is DimensionState.EXPIRED


def test_gate_two_promotes_at_70_and_under_30_days_protected() -> None:
    guard = EvolutionGuard()
    _submit_valid(guard, "c_70")
    _run_predictions(guard, "c_70", wins=7, total=10)  # 恰 70%
    # 第 29 天：试用未满，不裁决
    assert guard.resolve_probation("c_70", day=DAY0 + 29) is DimensionState.CANDIDATE
    # 第 30 天：转正
    assert guard.resolve_probation("c_70", day=DAY0 + 30) is DimensionState.ACTIVE


def test_gate_two_rejects_prediction_outside_probation_state() -> None:
    guard = EvolutionGuard()
    _submit_valid(guard, "c_x")
    guard.resolve_probation("c_x", day=DAY0 + 30)  # 零样本 → EXPIRED
    with pytest.raises(ValueError):
        guard.record_prediction("c_x", day=DAY0 + 31, success=True)


# ---------------------------------------------------------------------------
# 门三：每日反思配额 == 1
# ---------------------------------------------------------------------------

def test_gate_three_daily_reflection_quota_one() -> None:
    guard = EvolutionGuard()
    _submit_valid(guard, "c_q1")
    _submit_valid(guard, "c_q2", day=DAY0 + 1)
    # 第一发放行
    assert guard.reflect("c_q1", day=DAY0).startswith("reflection:")
    # 同自然日第二发：拦截（即便换对象也算第二次——配额按日总量）
    with pytest.raises(QuotaExceededBlockError):
        guard.reflect("c_q2", day=DAY0)
    with pytest.raises(QuotaExceededBlockError):
        guard.reflect("c_q1", day=DAY0)
    assert guard.quota_blocks == 2
    # 新的一天配额复位
    assert guard.reflect("c_q1", day=DAY0 + 1).startswith("reflection:")


# ---------------------------------------------------------------------------
# 全球硬顶 32 与末位淘汰
# ---------------------------------------------------------------------------

def test_global_active_cap_32_with_tail_eviction() -> None:
    guard = EvolutionGuard()
    # 灌入 40 个候选，全部 90% 预测且依次转正
    for i in range(40):
        cid = f"c{i:02d}"
        _submit_valid(guard, cid, day=DAY0 + i)
        guard.record_prediction(cid, day=DAY0 + i + 1, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 2, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 3, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 4, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 5, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 6, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 7, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 8, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 9, success=True)
        guard.record_prediction(cid, day=DAY0 + i + 10, success=False)  # 9/10 ≥ 70%
        # 活跃度/贡献度按编号升序：编号越小越该被淘汰
        guard.set_scores(cid, activity=i / 100.0, contribution=i / 100.0)
        assert guard.resolve_probation(cid, day=DAY0 + i + 30) is DimensionState.ACTIVE
        assert guard.active_count <= EvolutionGuard.MAX_ACTIVE

    assert guard.active_count == 32
    assert guard.archived_count == 8
    # 被淘汰的必须是 (活跃度, 贡献度, 提案日) 三键最低的 8 个
    assert guard.evacuated_to_archive == [f"c{i:02d}" for i in range(8)]
    assert guard.state_of("c00") is DimensionState.ARCHIVED
    assert guard.state_of("c39") is DimensionState.ACTIVE


# ---------------------------------------------------------------------------
# 自问自答死循环熔断
# ---------------------------------------------------------------------------

def test_self_talk_recursion_cut_at_layer_two() -> None:
    guard = EvolutionGuard()
    executed_layers: list[int] = []

    def malicious_reflection(depth: int) -> None:
        with guard.reflection_scope():
            executed_layers.append(depth)
            if depth < 5:  # 恶意套娃：必须永远不会跑进来第二次
                malicious_reflection(depth + 1)

    with pytest.raises(ReflectionLoopBreaker):
        malicious_reflection(1)
    assert executed_layers == [1]           # 只有第 1 层真正执行
    assert guard.self_talk_cut_count == 1   # 恰在试图进入第 2 层时切断

    # 熔断不是永久伤残：独立顶层反思仍可继续（防呆不等于锁死）
    with guard.reflection_scope():
        executed_layers.append(99)
    assert executed_layers[-1] == 99
    # 深度计数已正确回落，再次"嵌套"切入还能触发切断（顺序重入≠递归，不拦）
    with guard.reflection_scope():
        pass
    with guard.reflection_scope():
        pass
    assert guard.self_talk_cut_count == 1

    def nested() -> None:
        with guard.reflection_scope():
            with guard.reflection_scope():
                pass

    with pytest.raises(ReflectionLoopBreaker):
        nested()
    assert guard.self_talk_cut_count == 2


def test_unknown_candidate_and_blank_name_rejected() -> None:
    guard = EvolutionGuard()
    with pytest.raises(KeyError):
        guard.state_of("ghost")
    with pytest.raises(ValueError):
        guard.submit("blank", name="  ", evidence=_evidence(
            (PhysicalDomain.SLEEP, DAY0 - 3, DAY0 - 1),
            (PhysicalDomain.BLOOD_PRESSURE, DAY0 - 3, DAY0 - 1),
        ), day=DAY0)
    with pytest.raises(ValueError):
        _evidence((PhysicalDomain.SLEEP, DAY0, DAY0 - 5))  # 时序翻转非法
