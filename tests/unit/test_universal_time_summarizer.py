"""全维度多尺度时间总结引擎单元测试。

验证老大的核心指示：
1. 时间总结是所有维度的通用机制（健康、情绪、社交、财富、学业、职业、生活、全维度宏观）；
2. 覆盖完整 9 档跨度（日、周、月、季、半年、年、3年、5年、10年），绝无夹缝；
3. 逐级下钻证据并集 100% 守恒，SHA-256 指纹机械可查；
4. 导出为符合 AIOS 核心契约的 Summary 世界对象。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from aios_core.summaries.universal_time_summarizer import (
    SYNOPTIC_ALL,
    UniversalTimePyramidEngine,
    UniversalTimeScale,
    calculate_window_bounds,
    scale_finer_than,
)
from aios_core.contracts.models import Summary


UTC = timezone.utc
BASE_TIME = datetime(2020, 1, 1, 0, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> UniversalTimePyramidEngine:
    eng = UniversalTimePyramidEngine()

    # 注入跨越 10 年（2020~2029）、跨越 5 个不同维度的丰富测试事实
    dimensions = ["dim:health", "dim:emotion", "dim:finance", "dim:career", "dim:cognition"]
    
    for year_offset in range(10):  # 2020 ~ 2029
        for month_offset in (1, 4, 7, 10):  # 四个季度各采一个点
            moment = datetime(2020 + year_offset, month_offset, 15, 10, 0, tzinfo=UTC)
            for dim in dimensions:
                event_id = f"fact_{dim.replace(':', '_')}_{2020 + year_offset}_{month_offset}"
                if dim == "dim:health":
                    payload = {"id": event_id, "time": moment, "text": "早晨晨跑 5 公里，心率平稳", "bpm": 72 + year_offset}
                elif dim == "dim:emotion":
                    payload = {"id": event_id, "time": moment, "text": "专注完成代码重构，成就感满满", "stress_score": 0.3}
                elif dim == "dim:finance":
                    payload = {"id": event_id, "time": moment, "text": "季度理财结算与大额定投", "amount": 5000.0}
                elif dim == "dim:career":
                    payload = {"id": event_id, "time": moment, "text": "达成重要项目节点 Milestone", "score": 95}
                else:  # dim:cognition
                    payload = {"id": event_id, "time": moment, "text": "深度研读认知架构新论文", "score": 88}
                eng.ingest_event(payload, dimension_id=dim)
    return eng


def test_scale_ordering_and_comparison() -> None:
    # 验证偏序合法性：DAY < WEEK < MONTH < QUARTER < HALF_YEAR < YEAR < 3Y < 5Y < DECADE
    assert scale_finer_than(UniversalTimeScale.DAY, UniversalTimeScale.WEEK)
    assert scale_finer_than(UniversalTimeScale.WEEK, UniversalTimeScale.MONTH)
    assert scale_finer_than(UniversalTimeScale.MONTH, UniversalTimeScale.QUARTER)
    assert scale_finer_than(UniversalTimeScale.QUARTER, UniversalTimeScale.HALF_YEAR)
    assert scale_finer_than(UniversalTimeScale.HALF_YEAR, UniversalTimeScale.YEAR)
    assert scale_finer_than(UniversalTimeScale.YEAR, UniversalTimeScale.MULTI_YEAR_3Y)
    assert scale_finer_than(UniversalTimeScale.MULTI_YEAR_3Y, UniversalTimeScale.MULTI_YEAR_5Y)
    assert scale_finer_than(UniversalTimeScale.MULTI_YEAR_5Y, UniversalTimeScale.DECADE)


def test_all_dimensions_have_time_summaries(engine: UniversalTimePyramidEngine) -> None:
    # 验证核心原则：“时间维度的总结是所有维度都要有的机制，不是单独某个维度的专属！”
    moment = datetime(2023, 5, 20, 12, 0, tzinfo=UTC)
    all_dims_summaries = engine.summarize_all_dimensions_at_scale(UniversalTimeScale.YEAR, moment)

    # 涵盖健康、情绪、财务、事业、认知，以及全维度 SYNOPTIC_ALL
    assert "dim:health" in all_dims_summaries
    assert "dim:emotion" in all_dims_summaries
    assert "dim:finance" in all_dims_summaries
    assert "dim:career" in all_dims_summaries
    assert "dim:cognition" in all_dims_summaries
    assert SYNOPTIC_ALL in all_dims_summaries

    # 每个维度的总结都是独立有价值的
    health_sum = all_dims_summaries["dim:health"]
    assert health_sum.source_event_count == 4  # 4个季度各1条
    assert "avg_bpm" in health_sum.dimension_metrics
    assert health_sum.fingerprint_sha256 != ""

    # 全维度跨域总结包含了所有 5 个维度的 20 条事实并集
    synoptic_sum = all_dims_summaries[SYNOPTIC_ALL]
    assert synoptic_sum.source_event_count == 20
    assert len(synoptic_sum.evidence_ids) == 20


def test_quarterly_and_half_year_summaries(engine: UniversalTimePyramidEngine) -> None:
    # 验证重点：季度（QUARTER）与半年（HALF_YEAR）不再存在夹缝
    moment_q2 = datetime(2023, 4, 20, 10, 0, tzinfo=UTC)  # 属于 Q2 (4~6月)
    q2_summary = engine.summarize_window("dim:finance", UniversalTimeScale.QUARTER, moment_q2)

    assert q2_summary.scale == UniversalTimeScale.QUARTER
    assert q2_summary.start_time == datetime(2023, 4, 1, 0, 0, tzinfo=UTC)
    assert q2_summary.source_event_count >= 1
    assert "avg_amount" in q2_summary.dimension_metrics

    # 半年总结 (H1: 1~6月)
    h1_summary = engine.summarize_window("dim:health", UniversalTimeScale.HALF_YEAR, moment_q2)
    assert h1_summary.scale == UniversalTimeScale.HALF_YEAR
    assert h1_summary.start_time == datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
    # H1 包含 1月和4月两条事实
    assert h1_summary.source_event_count == 2


def test_multi_year_and_decade_summaries(engine: UniversalTimePyramidEngine) -> None:
    # 验证 3年、5年、10年宏观大跨度
    anchor = datetime(2025, 6, 1, tzinfo=UTC)
    
    # 3年跨度 (2025~2027)
    sum_3y = engine.summarize_window("dim:career", UniversalTimeScale.MULTI_YEAR_3Y, anchor)
    assert sum_3y.scale == UniversalTimeScale.MULTI_YEAR_3Y
    assert sum_3y.start_time == datetime(2025, 1, 1, tzinfo=UTC)
    assert sum_3y.source_event_count == 12  # 3年 × 4季度

    # 5年跨度 (2025~2029)
    sum_5y = engine.summarize_window("dim:career", UniversalTimeScale.MULTI_YEAR_5Y, anchor)
    assert sum_5y.scale == UniversalTimeScale.MULTI_YEAR_5Y
    assert sum_5y.start_time == datetime(2025, 1, 1, tzinfo=UTC)
    assert sum_5y.source_event_count == 20  # 5年 × 4季度

    # 10年跨度 (2020~2029)
    sum_10y = engine.summarize_window("dim:career", UniversalTimeScale.DECADE, anchor)
    assert sum_10y.scale == UniversalTimeScale.DECADE
    assert sum_10y.start_time == datetime(2020, 1, 1, tzinfo=UTC)
    assert sum_10y.source_event_count == 40  # 10年 × 4季度


def test_lossless_multi_level_drill_down_evidence_conservation(engine: UniversalTimePyramidEngine) -> None:
    # 从 10 年最高层依次下钻到 5年 -> 年 -> 季度 -> 原始事实，验证并集绝对守恒！
    anchor = datetime(2025, 1, 1, tzinfo=UTC)
    decade_node = engine.summarize_window("dim:health", UniversalTimeScale.DECADE, anchor)
    assert decade_node.source_event_count == 40

    # 1. 10年下钻到 5年
    five_year_nodes = engine.drill_down(decade_node.summary_id, UniversalTimeScale.MULTI_YEAR_5Y)
    assert len(five_year_nodes) == 2  # 2020~2024, 2025~2029
    combined_5y_ev = set()
    for node in five_year_nodes:
        combined_5y_ev.update(node.evidence_ids)
    assert combined_5y_ev == set(decade_node.evidence_ids)

    # 2. 5年下钻到 年
    first_5y = five_year_nodes[0]
    year_nodes = engine.drill_down(first_5y.summary_id, UniversalTimeScale.YEAR)
    assert len(year_nodes) == 5
    combined_year_ev = set()
    for y in year_nodes:
        combined_year_ev.update(y.evidence_ids)
    assert combined_year_ev == set(first_5y.evidence_ids)

    # 3. 年下钻到 季度
    first_year = year_nodes[0]
    quarter_nodes = engine.drill_down(first_year.summary_id, UniversalTimeScale.QUARTER)
    assert len(quarter_nodes) == 4
    combined_quarter_ev = set()
    for q in quarter_nodes:
        combined_quarter_ev.update(q.evidence_ids)
    assert combined_quarter_ev == set(first_year.evidence_ids)

    # 4. 季度直接下钻到底层原始事实 Observation
    first_quarter = quarter_nodes[0]
    raw_facts = engine.drill_down(first_quarter.summary_id, UniversalTimeScale.DAY)
    assert len(raw_facts) == 1
    assert raw_facts[0]["id"] in first_quarter.evidence_ids
    assert "bpm" in raw_facts[0]


def test_export_to_aios_summary_contract(engine: UniversalTimePyramidEngine) -> None:
    anchor = datetime(2023, 7, 1, tzinfo=UTC)
    node = engine.summarize_window("dim:finance", UniversalTimeScale.QUARTER, anchor)

    contract_obj = node.to_contract_summary(source_world_revision=42)
    assert isinstance(contract_obj, Summary)
    assert contract_obj.granularity == "QUARTER"
    assert contract_obj.dimension_ref is not None
    assert contract_obj.dimension_ref.object_id == "dim:finance"
    assert contract_obj.source_world_revision == 42
    assert contract_obj.coverage["event_count"] >= 1
    assert contract_obj.coverage["fingerprint"] == node.fingerprint_sha256
