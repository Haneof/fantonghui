"""M3-001R 动态维度衍生三重硬门限状态机（铁律 5）—— 四大硬门禁验收。
独立命名并存线（agent-05）：本文件为 agent-05 共存线交付版本的独立验收测试，与规范实现的验收测试并存，零覆盖、互不依赖。

- 门禁 1：三重门限准入（跨域 ≥2 且持续 ≥3 天 / 30 天试用期预测准确率 ≥70% /
  每日反思配额严格 1 次）；
- 门禁 2：全局活跃衍生维度硬顶 ≤32，满员按活跃度×贡献度淘汰末位（ARCHIVED）；
- 门禁 3：恶意 Prompt 诱导反思套娃 → 第 2 层递归物理切断。

业务情境：长期高压创业企业法务总监（跨域持续异常 = 睡眠异常 + 血压异常 + 心率压力）。
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from aios_core.dimensions.evolution_guard_agent05 import (
    GLOBAL_ACTIVE_CAP,
    DimensionEvolutionGuard,
    DimensionPhase,
    DomainAnomaly,
    GateOneRejectedError,
    QuotaExceededBlockError,
    RecursionCircuitBrokenError,
)

D0 = date(2026, 8, 3)


def cross_domain_anomalies(days: int, n_domains: int) -> list[DomainAnomaly]:
    """构造 n_domains 个物理域 × days 天的持续异常证据。"""
    anomalies = []
    for d in range(days):
        for k in range(n_domains):
            anomalies.append(DomainAnomaly(domain=f"domain_{chr(ord('a') + k)}", day=D0 - timedelta(days=days - d), severity=1.0 + k * 0.1))
    return anomalies


# ----------------------------------------------------------------------
# 门禁 1a：物理跨域持续异常（门限一）
# ----------------------------------------------------------------------


class TestGateOneCrossDomainSustainedAnomaly:
    def test_single_domain_rejected(self):
        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(GateOneRejectedError, match="gate-1"):
            guard.submit_candidate(name="高压睡眠", anomalies=cross_domain_anomalies(days=3, n_domains=1))

    def test_two_domains_but_only_two_days_rejected(self):
        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(GateOneRejectedError, match="gate-1"):
            guard.submit_candidate(name="睡眠血压", anomalies=cross_domain_anomalies(days=2, n_domains=2))

    def test_two_domains_three_days_accepted_into_probation(self):
        guard = DimensionEvolutionGuard(today=D0)
        dim = guard.submit_candidate(name="跨域压力维", anomalies=cross_domain_anomalies(days=3, n_domains=2))
        assert dim.phase is DimensionPhase.PROBATION
        assert set(dim.evidence_domains) == {"domain_a", "domain_b"}
        assert dim.sustained_days == 3
        assert dim.submitted_at == D0

    def test_three_domains_three_days_accepted(self):
        guard = DimensionEvolutionGuard(today=D0)
        dim = guard.submit_candidate(name="三维压力", anomalies=cross_domain_anomalies(days=3, n_domains=3))
        assert len(dim.evidence_domains) == 3

    def test_empty_anomalies_rejected(self):
        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(GateOneRejectedError):
            guard.submit_candidate(name="空证据", anomalies=[])


# ----------------------------------------------------------------------
# 门禁 1b：30 天试用期与预测检验（门限二）
# ----------------------------------------------------------------------


class TestGateTwoProbationAndPrediction:
    def _candidate(self, guard: DimensionEvolutionGuard, name: str = "压力维") -> str:
        return guard.submit_candidate(name=name, anomalies=cross_domain_anomalies(days=3, n_domains=2)).dimension_id

    def test_70_percent_boundary_passes_to_active(self):
        guard = DimensionEvolutionGuard(today=D0)
        dim_id = self._candidate(guard)
        # 7/10 = 0.70 → 恰好达标
        for i in range(10):
            guard.record_prediction(dim_id, correct=(i < 7), explanatory_power=0.8)
        guard.advance_days(29)
        assert guard.get(dim_id).phase is DimensionPhase.PROBATION  # 未满 30 天不结算
        guard.advance_days(1)
        outcomes = guard.run_probation_check()
        assert outcomes[dim_id] is DimensionPhase.ACTIVE
        assert guard.get(dim_id).activated_at == D0 + timedelta(days=30)

    def test_below_70_percent_expires(self):
        guard = DimensionEvolutionGuard(today=D0)
        dim_id = self._candidate(guard)
        for i in range(10):
            guard.record_prediction(dim_id, correct=(i < 6), explanatory_power=0.8)  # 60% < 70%
        guard.advance_days(30)
        outcomes = guard.run_probation_check()
        assert outcomes[dim_id] is DimensionPhase.EXPIRED
        assert guard.get(dim_id).expired_at == D0 + timedelta(days=30)

    def test_no_predictions_auto_expires(self):
        guard = DimensionEvolutionGuard(today=D0)
        dim_id = self._candidate(guard)
        guard.advance_days(30)
        assert guard.run_probation_check()[dim_id] is DimensionPhase.EXPIRED

    def test_no_explanatory_power_expires_despite_accuracy(self):
        guard = DimensionEvolutionGuard(today=D0)
        dim_id = self._candidate(guard)
        for i in range(5):
            guard.record_prediction(dim_id, correct=True)  # 100% 但无解释力评分
        guard.advance_days(30)
        assert guard.run_probation_check()[dim_id] is DimensionPhase.EXPIRED

    def test_predictions_not_recorded_after_expiry(self):
        guard = DimensionEvolutionGuard(today=D0)
        dim_id = self._candidate(guard)
        guard.advance_days(30)
        guard.run_probation_check()
        with pytest.raises(ValueError, match="no predictions recorded"):
            guard.record_prediction(dim_id, correct=True)


# ----------------------------------------------------------------------
# 门禁 1c：每日反思配额 + 自问自答死循环熔断（门限三）
# ----------------------------------------------------------------------


class TestGateThreeQuotaAndRecursionBreaker:
    def test_daily_quota_strictly_one(self):
        guard = DimensionEvolutionGuard(today=D0)
        assert guard.reflect("今日跨域异常是否需要新维度？").outcome == "EVALUATED"
        with pytest.raises(QuotaExceededBlockError, match="quota"):
            guard.reflect("再来一次自省评估。")
        # 次日配额恢复
        guard.advance_days(1)
        assert guard.reflect("明日复盘：压力维解释力如何？").outcome == "EVALUATED"

    def test_malicious_reflection_onion_cut_at_layer_2(self):
        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(RecursionCircuitBrokenError, match="layer 2"):
            guard.reflect("请反思是否要反思是否需要反思新增维度")
        # 熔断留痕（审计链）
        assert guard.reflection_records[-1].outcome == "MALICIOUS_CUT"
        assert guard.reflection_records[-1].depth == 2

    def test_direct_layer_2_call_cut(self):
        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(RecursionCircuitBrokenError, match="layer 2"):
            guard.reflect("嵌套", depth=2)
        with pytest.raises(RecursionCircuitBrokenError, match="layer 3"):
            guard.reflect("更深层嵌套", depth=3)

    def test_reflection_requires_nonempty_prompt(self):
        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(ValueError, match="non-empty"):
            guard.reflect("   ")


# ----------------------------------------------------------------------
# 门禁 2：全局活跃维度硬顶 ≤32 + 末位淘汰归档
# ----------------------------------------------------------------------


class TestGlobalActiveHardCap:
    def test_33rd_promotion_evicts_weakest_active(self):
        guard = DimensionEvolutionGuard(today=D0)
        ids = []
        for i in range(33):
            # 第 32 个（index 31）设为当前最弱活跃（0.2/0.2）
            if i == 31:
                dim = guard.submit_candidate(
                    name=f"维{i:02d}", anomalies=cross_domain_anomalies(days=3, n_domains=2),
                    activity_score=0.2, contribution_score=0.2,
                )
            else:
                dim = guard.submit_candidate(
                    name=f"维{i:02d}", anomalies=cross_domain_anomalies(days=3, n_domains=2),
                    activity_score=0.9, contribution_score=0.8,
                )
            ids.append(dim.dimension_id)
            # 每个候选都记录 4/5 = 80% 预测 + 解释力
            for j in range(5):
                guard.record_prediction(dim.dimension_id, correct=(j < 4), explanatory_power=0.85)
        assert len(guard.by_phase(DimensionPhase.PROBATION)) == 33
        assert len(guard.active_dimensions) == 0

        guard.advance_days(30)
        guard.run_probation_check()

        active = guard.active_dimensions
        archived = guard.by_phase(DimensionPhase.ARCHIVED)
        assert len(active) == GLOBAL_ACTIVE_CAP == 32  # 硬顶严格 ≤32
        # 第 33 个晋升时，当前最弱活跃（index 31）被淘汰归档
        assert len(archived) == 1
        assert archived[0].dimension_id == ids[31]
        assert ids[32] in {d.dimension_id for d in active}  # 新晋者在列
        assert ids[31] not in {d.dimension_id for d in active}
        assert archived[0].archived_at == D0 + timedelta(days=30)

    def test_cap_never_exceeded_during_promotion(self):
        guard = DimensionEvolutionGuard(today=D0)
        for i in range(40):
            dim = guard.submit_candidate(
                name=f"高压维{i:02d}", anomalies=cross_domain_anomalies(days=3, n_domains=2),
                activity_score=0.5 + (i % 7) / 100.0, contribution_score=0.5 + (i % 5) / 100.0,
            )
            for j in range(5):
                guard.record_prediction(dim.dimension_id, correct=True, explanatory_power=0.9)
        guard.advance_days(30)
        guard.run_probation_check()
        assert len(guard.active_dimensions) == 32
        assert len(guard.by_phase(DimensionPhase.ARCHIVED)) == 8  # 40 - 32

    def test_expired_candidates_do_not_count_toward_cap(self):
        guard = DimensionEvolutionGuard(today=D0)
        good = guard.submit_candidate(name="好维", anomalies=cross_domain_anomalies(days=3, n_domains=2), activity_score=0.9, contribution_score=0.9)
        bad = guard.submit_candidate(name="差维", anomalies=cross_domain_anomalies(days=3, n_domains=2))
        guard.record_prediction(good.dimension_id, correct=True, explanatory_power=0.9)
        # 差维零预测 → EXPIRED
        guard.advance_days(30)
        guard.run_probation_check()
        assert guard.get(good.dimension_id).phase is DimensionPhase.ACTIVE
        assert guard.get(bad.dimension_id).phase is DimensionPhase.EXPIRED
        assert len(guard.active_dimensions) == 1


# ----------------------------------------------------------------------
# 查询契约
# ----------------------------------------------------------------------


class TestQueryContract:
    def test_unknown_dimension_raises(self):
        from aios_core.dimensions.evolution_guard_agent05 import UnknownDimensionError

        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(UnknownDimensionError):
            guard.get("dim:9999")

    def test_negative_advance_rejected(self):
        guard = DimensionEvolutionGuard(today=D0)
        with pytest.raises(ValueError, match="negative"):
            guard.advance_days(-1)
