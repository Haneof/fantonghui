"""阶段二验收：时间金字塔多尺度逐级结晶与无损穿透。

工单要求逐条对应：
- 总结是新观察层，绝非压缩删除原始记录；
- 从年度总结一键无损穿透到具体月份、日期、直至当时那一句原话切片；
- 证据链断裂率 0.0%。
"""

from __future__ import annotations

import datetime as dt
from datetime import date, timedelta

import pytest

from aios_core.contracts.enums import SummaryStatus
from aios_core.summaries.pyramid_aggregator_parallel import (
    TIER_ORDER,
    SummaryTier,
    TimePyramidAggregator,
)

UTC = dt.UTC
BASE = dt.datetime(2023, 1, 1, tzinfo=UTC)

UTTERANCES = (
    "今天和老王谈了合伙分成的事",
    "银行流水显示他挪用了资金",
    "胸口闷，早搏又犯了",
)


@pytest.fixture(scope="module")
def three_year() -> TimePyramidAggregator:
    """三年跨度的对抗生命切片：365*3 天 × 3 条原话 = 3,285 条原始观测。"""
    aggregator = TimePyramidAggregator()
    for day in range(365 * 3):
        for k, text in enumerate(UTTERANCES):
            aggregator.ingest_observation(
                f"obs_{day}_{k}", text, BASE + timedelta(days=day, hours=9 + k)
            )
    return aggregator


# ---------------------------------------------------------------------------
# 结晶：五层齐全，且总结是"新观察层"
# ---------------------------------------------------------------------------


def test_all_five_tiers_crystallize(three_year: TimePyramidAggregator) -> None:
    nodes = three_year.crystallize_all(date(2023, 6, 15))
    assert list(nodes) == list(TIER_ORDER)
    assert [t.value for t in TIER_ORDER] == ["day", "week", "month", "quarter", "year"]


def test_summary_is_a_new_layer_and_never_deletes_raw(
    three_year: TimePyramidAggregator,
) -> None:
    """工单核心原则：结晶之后原始观测一条都不许少。"""
    before = three_year.raw_observation_count
    assert before == 365 * 3 * 3

    three_year.crystallize_all(date(2023, 6, 15))
    three_year.crystallize_all(date(2024, 3, 3))
    three_year.crystallize_all(date(2025, 11, 20))

    assert three_year.raw_observation_count == before
    assert three_year.summary_count > 0


def test_crystallization_is_idempotent(three_year: TimePyramidAggregator) -> None:
    first = three_year.crystallize(SummaryTier.MONTH, date(2024, 5, 9))
    second = three_year.crystallize(SummaryTier.MONTH, date(2024, 5, 22))
    assert first is not None and second is not None
    assert first.node_id == second.node_id
    count = three_year.summary_count
    three_year.crystallize(SummaryTier.MONTH, date(2024, 5, 30))
    assert three_year.summary_count == count


def test_summary_node_aligns_with_frozen_contract(
    three_year: TimePyramidAggregator,
) -> None:
    node = three_year.crystallize(SummaryTier.YEAR, date(2023, 6, 15))
    assert node is not None
    assert node.granularity == "year"  # 对齐 Summary.granularity
    assert node.summary_status is SummaryStatus.CURRENT


def test_empty_period_is_not_crystallized() -> None:
    """空周期不建节点，否则会产生空壳并被误判成断链。"""
    aggregator = TimePyramidAggregator()
    aggregator.ingest_observation("only", "唯一一条", BASE)
    assert aggregator.crystallize(SummaryTier.DAY, date(2023, 1, 1)) is not None
    assert aggregator.crystallize(SummaryTier.DAY, date(2023, 2, 1)) is None
    assert aggregator.summary_count == 1


# ---------------------------------------------------------------------------
# 无损穿透：年 -> 季 -> 月 -> 周 -> 日 -> 原话
# ---------------------------------------------------------------------------


def test_year_summary_drills_down_to_exact_raw_utterances(
    three_year: TimePyramidAggregator,
) -> None:
    year = three_year.crystallize(SummaryTier.YEAR, date(2023, 6, 15))
    assert year is not None
    path = three_year.drill_down(year.node_id)

    assert path.reached_raw is True
    # 2023 年共 365 天 × 3 条 = 1,095 条原话，一条不多一条不少
    assert len(path.leaf_texts) == 365 * 3
    assert path.leaf_texts[0] == UTTERANCES[0]
    # 穿透覆盖了全部五层
    assert set(path.tiers) == set(TIER_ORDER)


def test_day_summary_drills_to_its_three_utterances(
    three_year: TimePyramidAggregator,
) -> None:
    day = three_year.crystallize(SummaryTier.DAY, date(2024, 8, 17))
    assert day is not None
    path = three_year.drill_down(day.node_id)
    assert path.reached_raw is True
    assert path.leaf_texts == UTTERANCES


def test_every_node_reaches_raw_with_zero_breakage(
    three_year: TimePyramidAggregator,
) -> None:
    """工单硬指标：证据链断裂率 0.0%。"""
    for anchor in (date(2023, 6, 15), date(2024, 3, 3), date(2025, 11, 20)):
        three_year.crystallize_all(anchor)

    report = three_year.verify_chain_integrity()
    assert report.nodes_checked > 400
    assert report.dangling_child_refs == 0
    assert report.dangling_leaf_refs == 0
    assert report.broken_paths == 0
    assert report.breakage_rate == 0.0


def test_dangling_leaf_reference_is_detected_as_breakage() -> None:
    """反向验证：真把原始观测抽掉，断裂率必须立刻不为 0。"""
    aggregator = TimePyramidAggregator()
    aggregator.ingest_observation("a", "原话一", BASE)
    aggregator.ingest_observation("b", "原话二", BASE + timedelta(hours=1))
    day = aggregator.crystallize(SummaryTier.DAY, date(2023, 1, 1))
    assert day is not None
    assert aggregator.verify_chain_integrity().breakage_rate == 0.0

    # 模拟历史被物理删除（铁律二禁止的行为）
    aggregator._observations.pop("b")
    report = aggregator.verify_chain_integrity()
    assert report.dangling_leaf_refs == 1
    assert report.breakage_rate == 1.0


# ---------------------------------------------------------------------------
# 追加式：摄入不得覆盖或删除
# ---------------------------------------------------------------------------


def test_ingest_rejects_duplicate_and_blank() -> None:
    aggregator = TimePyramidAggregator()
    aggregator.ingest_observation("x", "第一条", BASE)
    with pytest.raises(ValueError, match="duplicate"):
        aggregator.ingest_observation("x", "重复", BASE)
    with pytest.raises(ValueError, match="blank"):
        aggregator.ingest_observation("y", "   ", BASE)
    with pytest.raises(ValueError, match="blank"):
        aggregator.ingest_observation("  ", "内容", BASE)


def test_ingest_rejects_naive_datetime() -> None:
    aggregator = TimePyramidAggregator()
    with pytest.raises(Exception, match="timezone|aware"):
        aggregator.ingest_observation("n", "无时区", dt.datetime(2023, 1, 1))  # noqa: DTZ001


def test_ingest_many_counts(three_year: TimePyramidAggregator) -> None:
    aggregator = TimePyramidAggregator()
    n = aggregator.ingest_many(
        [("o1", "一", BASE), ("o2", "二", BASE + timedelta(hours=1))]
    )
    assert n == 2
    assert aggregator.raw_observation_count == 2


# ---------------------------------------------------------------------------
# 周期边界
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "anchor", "expected_start", "expected_end"),
    [
        (SummaryTier.DAY, date(2024, 5, 9), date(2024, 5, 9), date(2024, 5, 9)),
        (SummaryTier.WEEK, date(2024, 5, 9), date(2024, 5, 6), date(2024, 5, 12)),
        (SummaryTier.MONTH, date(2024, 5, 9), date(2024, 5, 1), date(2024, 5, 31)),
        (SummaryTier.QUARTER, date(2024, 5, 9), date(2024, 4, 1), date(2024, 6, 30)),
        (SummaryTier.YEAR, date(2024, 5, 9), date(2024, 1, 1), date(2024, 12, 31)),
    ],
)
def test_period_boundaries(tier, anchor, expected_start, expected_end) -> None:
    start, end = TimePyramidAggregator.period_for(tier, anchor)
    assert (start, end) == (expected_start, expected_end)


def test_quarter_boundaries_at_year_edges() -> None:
    assert TimePyramidAggregator.period_for(SummaryTier.QUARTER, date(2024, 1, 1)) == (
        date(2024, 1, 1),
        date(2024, 3, 31),
    )
    assert TimePyramidAggregator.period_for(SummaryTier.QUARTER, date(2024, 12, 31)) == (
        date(2024, 10, 1),
        date(2024, 12, 31),
    )


def test_week_straddle_is_documented_not_a_defect(three_year: TimePyramidAggregator) -> None:
    """周周期会跨月，故一个周节点可被相邻两个月共享。

    这不是断链：drill_down 已按节点与原话双重去重。年度穿透仍精确等于
    365*3，说明去重生效；本用例把这一性质钉死，防止日后被误改成重复计数。
    """
    year = three_year.crystallize(SummaryTier.YEAR, date(2023, 6, 15))
    assert year is not None
    assert len(three_year.drill_down(year.node_id).leaf_texts) == 365 * 3


def test_unknown_node_raises(three_year: TimePyramidAggregator) -> None:
    with pytest.raises(KeyError):
        three_year.node("sum_nope")
