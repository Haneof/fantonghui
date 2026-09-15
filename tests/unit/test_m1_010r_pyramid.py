"""M1-010R 5D 时空多尺度连续聚合器与时间金字塔物化视图 - 验收单测。

宪法第二十五至二十七条铁律验收断言：
- 高层总结必须携带所有底层证据指针列表（evidence_ids），证据链完整度 100%；
- 下钻时底层事件完好无损（深拷贝、按时间序、内容逐字节一致）；
- 下钻响应 <= 45ms；
- 生成月/年总结后，日记录与原始事件永存于证据保险库，绝不删除、绝不覆盖。
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from aios_core.summaries import (
    CONTINUOUS_ZOOM_SECONDS,
    MAX_SPAN_SECONDS,
    SCALE_ORDER,
    PyramidAggregator,
    PyramidError,
    TimePyramidSummary,
    finer_than,
    scale_for_zoom,
)

UTC = timezone.utc
BASE = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
POLICY_PATH = Path(__file__).resolve().parents[2] / "governance" / "runtime_policy.json"


def make_events(
    *,
    start: datetime = BASE,
    n_days: int,
    per_day: int,
    with_5d: bool = True,
    id_prefix: str = "ev",
) -> list[dict]:
    """确定性事件生成器：按天×分钟散布的原始事件（可含 5D 描述字段）。"""
    events = []
    for day in range(n_days):
        for i in range(per_day):
            event = {
                "id": f"{id_prefix}-{day:03d}-{i:02d}",
                "time": start + timedelta(days=day, minutes=i * 7),
                "text": f"原始事实 {day}-{i}",
            }
            if with_5d:
                event.update(
                    x=round(day * 0.5 + i * 0.01, 4),
                    y=float(i % 5),
                    z=1.5,
                    r=0.8,
                    c=0.9,
                )
            events.append(event)
    return events


# ----------------------------------------------------------------------
# 证据链完整度 100%：高层总结必须携带所有底层证据指针
# ----------------------------------------------------------------------


class TestEvidenceChainIntegrity:
    def test_month_rollup_carries_all_underlying_evidence_ids(self):
        events = make_events(n_days=31, per_day=12)
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("MONTH", "dim_health", events)

        assert summary.evidence_ids
        assert len(summary.evidence_ids) == len(events) == 372
        underlying = {event["id"] for event in events}
        # 证据链完整度 = |总结证据 ∩ 底层事件| / |底层事件| == 100%
        assert len(set(summary.evidence_ids) & underlying) / len(underlying) == 1.0
        assert set(summary.evidence_ids) == underlying
        # 无重复指针、按时间序（生成器本身即时间序）
        assert summary.evidence_ids == [event["id"] for event in events]

    def test_week_rollup_evidence_chain_complete(self):
        events = make_events(n_days=7, per_day=10, id_prefix="wk")
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("WEEK", "dim_work", events)
        assert set(summary.evidence_ids) == {event["id"] for event in events}
        assert len(summary.evidence_ids) == 70

    def test_pyramid_compositional_evidence_union_is_lossless(self):
        """4 周物化 + 1 月物化：各周 evidence_ids 之并集 == 月 evidence_ids。"""
        events = make_events(n_days=28, per_day=10, id_prefix="comp")
        aggregator = PyramidAggregator()
        week_size = 7 * 10  # 一周 = 7 天 × 每天 10 条
        week_summaries = [
            aggregator.generate_materialized_rollup(
                "WEEK", "dim_comp", events[week_size * d : week_size * (d + 1)]
            )
            for d in range(4)
        ]
        month_summary = aggregator.generate_materialized_rollup("MONTH", "dim_comp", events)

        union = set()
        for week in week_summaries:
            union |= set(week.evidence_ids)
        assert union == set(month_summary.evidence_ids)
        assert union == {event["id"] for event in events}

    def test_year_rollup_from_12_month_slices_full_evidence(self):
        """12 个月物化 + 1 年物化：年度总结携带全年全部底层证据指针。"""
        year_start = datetime(2024, 1, 1, tzinfo=UTC)  # 闰年 366 天
        per_day = 3
        events = make_events(start=year_start, n_days=366, per_day=per_day, id_prefix="yr")
        aggregator = PyramidAggregator()

        day = 0
        month_summaries = []
        month_lengths = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        for length in month_lengths:
            slice_events = events[day * per_day : (day + length) * per_day]
            month_summaries.append(
                aggregator.generate_materialized_rollup("MONTH", "dim_year", slice_events)
            )
            day += length
        assert day == 366

        year_summary = aggregator.generate_materialized_rollup("YEAR", "dim_year", events)
        assert set(year_summary.evidence_ids) == {event["id"] for event in events}
        union = set()
        for month in month_summaries:
            union |= set(month.evidence_ids)
        assert union == set(year_summary.evidence_ids)

    def test_scale_metadata_of_rollups(self):
        events = make_events(n_days=31, per_day=6)
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("MONTH", "dim_meta", events)
        assert summary.scale == "MONTH"
        assert summary.dimension_id == "dim_meta"
        # headline 只允许是中性结构标签：机械聚合层不测量任何「演变」，
        # 单事件窗口内也不存在演变。旧文案「阶段性演变概览」预设了结论，
        # 违反 §11 分寸感自涌现 / policy style_constraints.hardcoded_intimacy_rules_prohibited。
        assert summary.headline == "MONTH 阶段汇总"
        assert summary.scale in summary.headline
        assert summary.start_time == events[0]["time"]
        assert summary.end_time == events[-1]["time"]
        assert summary.missingness_ratio == 0.0
        assert "沉淀了 186 项核心事实" in summary.synthesis_text


# ----------------------------------------------------------------------
# 无损下钻：底层事件完好无损
# ----------------------------------------------------------------------


class TestLosslessDrillDown:
    def test_drill_down_to_day_returns_intact_raw_events(self):
        events = make_events(n_days=31, per_day=8)
        snapshot = copy.deepcopy(events)
        aggregator = PyramidAggregator()
        month_summary = aggregator.generate_materialized_rollup("MONTH", "dim_intact", events)

        drilled = aggregator.drill_down(month_summary.summary_id, "DAY")
        assert len(drilled) == len(events) == 248
        drilled_by_id = {event["id"]: event for event in drilled}
        for original in snapshot:
            # 深相等：底层事件完好无损（含嵌套字段与 5D 描述）
            assert drilled_by_id[original["id"]] == original
        # 下钻返回按时间序
        assert [event["time"] for event in drilled] == sorted(
            event["time"] for event in drilled
        )
        # 输入事件列表未被聚合器改动
        assert events == snapshot

    def test_drill_down_to_week_composes_losslessly_and_drills_further(self):
        events = make_events(n_days=28, per_day=6, id_prefix="wd")
        aggregator = PyramidAggregator()
        month_summary = aggregator.generate_materialized_rollup("MONTH", "dim_chain", events)

        weeks = aggregator.drill_down(month_summary.summary_id, "WEEK")
        # 2026-01-01 是周四：1 月 1-4 日属上一 ISO 周，故 28 天窗口横跨 5 个 ISO 周
        # （若起点为周一则为 4 个）—— 数量随起点浮动，无损性才是验收红线
        assert 4 <= len(weeks) <= 5
        assert all(isinstance(week, TimePyramidSummary) for week in weeks)
        assert all(week.scale == "WEEK" for week in weeks)
        # 子层证据两两不相交（划分），且并集 == 父层证据：无损
        parent_evidence = set(month_summary.evidence_ids)
        union = set()
        for week in weeks:
            assert set(week.evidence_ids) <= parent_evidence
            assert union.isdisjoint(week.evidence_ids)
            union |= set(week.evidence_ids)
        assert union == parent_evidence

        # 子总结可继续下钻至 DAY，拼回全部原始事件
        collected = []
        for week in weeks:
            collected.extend(aggregator.drill_down(week.summary_id, "DAY"))
        assert {event["id"]: event for event in collected} == {
            event["id"]: event for event in events
        }

    def test_drill_down_from_year_through_months_to_days(self):
        year_start = datetime(2024, 1, 1, tzinfo=UTC)
        events = make_events(start=year_start, n_days=366, per_day=2, id_prefix="yd")
        aggregator = PyramidAggregator()
        year_summary = aggregator.generate_materialized_rollup("YEAR", "dim_full", events)

        months = aggregator.drill_down(year_summary.summary_id, "MONTH")
        assert len(months) == 12
        collected = []
        for month in months:
            collected.extend(aggregator.drill_down(month.summary_id, "DAY"))
        assert len(collected) == 732
        assert {event["id"]: event for event in collected} == {
            event["id"]: event for event in events
        }


# ----------------------------------------------------------------------
# 宪法红线：总结绝不是压缩删除，原始事实永存
# ----------------------------------------------------------------------


class TestConstitutionalRedLine:
    def test_day_records_persist_after_higher_rollups(self):
        """生成月总结后，日记录绝不可删除：底层事件全部永存 vault。"""
        events = make_events(n_days=28, per_day=5, id_prefix="const")
        aggregator = PyramidAggregator()
        day_summary = aggregator.generate_materialized_rollup(
            "DAY", "dim_const", events[:5]
        )
        # WEEK 只能覆盖一个自然周（<= 7 天）。此处曾把 28 天整段标成 WEEK，
        # 生成出一个「标签说谎」的总结：手环 5D 滑动条按 scale 标签取内容，
        # 于是会把 4 周的内容当成 1 周呈现。现按尺度切片，本测试的**意图不变**
        # （生成更高层总结后，日记录一条都不少），且红线断言更强：
        # DAY/WEEK/MONTH 三层全部生成后，vault 仍须完整保留 140 条原始事件。
        week_size = 7 * 5  # 一周 = 7 天 × 每天 5 条
        week_summary = aggregator.generate_materialized_rollup(
            "WEEK", "dim_const", events[:week_size]
        )
        month_summary = aggregator.generate_materialized_rollup("MONTH", "dim_const", events)

        assert month_summary.scale == "MONTH"
        assert day_summary.scale == "DAY"
        assert week_summary.scale == "WEEK"
        # 月总结生成之后，日记录（底层原始事件）一条都不少
        assert aggregator.vault_size() == len(events) == 140
        for event in events:
            assert aggregator.get_raw_event(event["id"]) == event

    def test_vault_is_isolated_from_caller_mutation(self):
        events = make_events(n_days=7, per_day=3, id_prefix="iso")
        aggregator = PyramidAggregator()
        week_summary = aggregator.generate_materialized_rollup("WEEK", "dim_iso", events)

        # 调用方事后篡改输入事件，不影响保险库原件
        events[0]["text"] = "被篡改"
        events[0]["c"] = 0.0
        assert aggregator.get_raw_event(events[0]["id"])["text"] == "原始事实 0-0"
        assert aggregator.get_raw_event(events[0]["id"])["c"] == 0.9

        # 下钻返回深拷贝：篡改下钻结果也无法污染保险库
        drilled = aggregator.drill_down(week_summary.summary_id, "DAY")
        drilled[0]["text"] = "恶意修改"
        assert aggregator.get_raw_event(events[0]["id"])["text"] == "原始事实 0-0"

    def test_evidence_conflict_is_rejected_never_overwritten(self):
        events = make_events(n_days=1, per_day=2, id_prefix="conflict")
        aggregator = PyramidAggregator()
        aggregator.generate_materialized_rollup("DAY", "dim_conflict", events)

        tampered = copy.deepcopy(events)
        tampered[0]["text"] = "篡改后的历史"
        with pytest.raises(PyramidError, match="evidence conflict"):
            aggregator.generate_materialized_rollup("DAY", "dim_conflict", tampered)
        # 原件未被覆盖
        assert aggregator.get_raw_event(events[0]["id"])["text"] == "原始事实 0-0"

    def test_duplicate_identical_event_is_deduped(self):
        events = make_events(n_days=1, per_day=2, id_prefix="dup")
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup(
            "DAY", "dim_dup", events + events  # 同一证据指针重复投递
        )
        assert summary.evidence_ids == [event["id"] for event in events]
        assert aggregator.vault_size() == 2


# ----------------------------------------------------------------------
# 5D 聚合与缺失度
# ----------------------------------------------------------------------


class TestFiveDAggregation:
    def test_missingness_ratio_counts_incomplete_5d_descriptors(self):
        events = make_events(n_days=1, per_day=6)
        for index in range(4):  # 4 条缺失可信度 c
            events[index].pop("c")
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("DAY", "dim_missing", events)
        assert summary.missingness_ratio == pytest.approx(4 / 6)

    def test_deterministic_5d_weights_and_centroid(self):
        # 两个事件均 c=1, r=1：近因系数 0 与 1，坐标原点 prox=1
        # => 总权重 = 0*1*1*1 + 1*1*1*1 = 1.000，重心 (0, 0, 0)
        events = [
            {"id": "w1", "time": BASE, "x": 0.0, "y": 0.0, "z": 0.0, "r": 1.0, "c": 1.0},
            {
                "id": "w2",
                "time": BASE + timedelta(hours=1),
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "r": 1.0,
                "c": 1.0,
            },
        ]
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("DAY", "dim_w", events)
        assert "总权重 1.000" in summary.synthesis_text
        assert "时空重心 (0.00, 0.00, 0.00)" in summary.synthesis_text
        assert summary.missingness_ratio == 0.0

    def test_invalid_5d_values_are_rejected(self):
        events = [
            {"id": "b1", "time": BASE, "x": 1.0, "y": 0.0, "z": 0.0, "r": 1.0, "c": 1.5},
            {
                "id": "b2",
                "time": BASE + timedelta(minutes=5),
                "x": 1.0,
                "y": 0.0,
                "z": 0.0,
                "r": 1.0,
                "c": 0.5,
            },
        ]
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="within \\[0, 1\\]"):
            aggregator.generate_materialized_rollup("DAY", "dim_bad", events)


# ----------------------------------------------------------------------
# 下钻响应 <= 45ms
# ----------------------------------------------------------------------


class TestDrillDownLatency:
    def test_drill_down_response_within_45_ms(self):
        import time

        year_start = datetime(2024, 1, 1, tzinfo=UTC)
        events = make_events(start=year_start, n_days=366, per_day=24, id_prefix="lat")
        aggregator = PyramidAggregator()
        year_summary = aggregator.generate_materialized_rollup("YEAR", "dim_lat", events)
        assert len(events) == 8784

        started = time.perf_counter()
        months = aggregator.drill_down(year_summary.summary_id, "MONTH")
        month_ms = (time.perf_counter() - started) * 1000
        assert len(months) == 12
        assert month_ms <= 45, f"YEAR->MONTH 下钻耗时 {month_ms:.2f}ms 超过 45ms 红线"

        started = time.perf_counter()
        days = aggregator.drill_down(year_summary.summary_id, "DAY")
        day_ms = (time.perf_counter() - started) * 1000
        assert len(days) == 8784
        assert day_ms <= 45, f"YEAR->DAY 下钻耗时 {day_ms:.2f}ms 超过 45ms 红线"

        started = time.perf_counter()
        month_days = aggregator.drill_down(months[0].summary_id, "DAY")
        chained_ms = (time.perf_counter() - started) * 1000
        assert len(month_days) == 31 * 24
        assert chained_ms <= 45, f"MONTH->DAY 下钻耗时 {chained_ms:.2f}ms 超过 45ms 红线"


# ----------------------------------------------------------------------
# 协议护栏
# ----------------------------------------------------------------------


class TestGuardRails:
    def test_invalid_scale_rejected(self):
        events = make_events(n_days=1, per_day=2)
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="invalid scale"):
            aggregator.generate_materialized_rollup("HOUR", "dim_x", events)
        with pytest.raises(PyramidError, match="invalid scale"):
            aggregator.generate_materialized_rollup("", "dim_x", events)

    def test_empty_events_rejected(self):
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="non-empty"):
            aggregator.generate_materialized_rollup("DAY", "dim_x", [])
        with pytest.raises(PyramidError, match="non-empty"):
            aggregator.generate_materialized_rollup("DAY", "dim_x", None)  # type: ignore[arg-type]

    def test_event_missing_id_or_time_rejected(self):
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="'id'"):
            aggregator.generate_materialized_rollup(
                "DAY", "dim_x", [{"time": BASE}]
            )
        with pytest.raises(PyramidError, match="'time'"):
            aggregator.generate_materialized_rollup(
                "DAY", "dim_x", [{"id": "no-time"}]
            )

    def test_drill_down_to_unknown_summary_raises(self):
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="unknown summary_id"):
            aggregator.drill_down("sum_nonexistent", "DAY")

    def test_drill_down_must_go_finer_only(self):
        events = make_events(n_days=7, per_day=3, id_prefix="up")
        aggregator = PyramidAggregator()
        week_summary = aggregator.generate_materialized_rollup("WEEK", "dim_up", events)
        with pytest.raises(PyramidError, match="strictly finer"):
            aggregator.drill_down(week_summary.summary_id, "MONTH")
        with pytest.raises(PyramidError, match="strictly finer"):
            aggregator.drill_down(week_summary.summary_id, "WEEK")

    def test_day_summary_has_no_finer_scale_to_drill(self):
        events = make_events(n_days=1, per_day=3, id_prefix="day")
        aggregator = PyramidAggregator()
        day_summary = aggregator.generate_materialized_rollup("DAY", "dim_day", events)
        with pytest.raises(PyramidError, match="strictly finer"):
            aggregator.drill_down(day_summary.summary_id, "DAY")

    def test_finer_than_helper_ordering(self):
        assert SCALE_ORDER == ("DAY", "WEEK", "MONTH", "YEAR")
        for fine, coarse in [
            ("DAY", "WEEK"),
            ("DAY", "MONTH"),
            ("DAY", "YEAR"),
            ("WEEK", "MONTH"),
            ("WEEK", "YEAR"),
            ("MONTH", "YEAR"),
        ]:
            assert finer_than(fine, coarse) is True
        for same in SCALE_ORDER:
            assert finer_than(same, same) is False

    def test_model_contract_rejects_invalid_shapes(self):
        with pytest.raises(ValidationError, match="scale must be one of"):
            TimePyramidSummary(
                summary_id="s1",
                scale="HOUR",
                start_time=BASE,
                end_time=BASE + timedelta(days=1),
                dimension_id="d",
                headline="h",
                synthesis_text="t",
                evidence_ids=["e1"],
            )
        with pytest.raises(ValidationError, match="must not be after"):
            TimePyramidSummary(
                summary_id="s2",
                scale="DAY",
                start_time=BASE + timedelta(days=1),
                end_time=BASE,
                dimension_id="d",
                headline="h",
                synthesis_text="t",
                evidence_ids=["e1"],
            )
        with pytest.raises(ValidationError, match="duplicates"):
            TimePyramidSummary(
                summary_id="s3",
                scale="DAY",
                start_time=BASE,
                end_time=BASE,
                dimension_id="d",
                headline="h",
                synthesis_text="t",
                evidence_ids=["e1", "e1"],
            )

    def test_get_summary_and_vault_lookup_errors(self):
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="unknown summary_id"):
            aggregator.get_summary("missing")
        with pytest.raises(PyramidError, match="unknown event_id"):
            aggregator.get_raw_event("missing")


# ----------------------------------------------------------------------
# 合成文本诚实性：机械聚合层只允许陈述它真正测量过的量
# 法律依据：宪法 §11（分寸感自涌现）、R3 §5.1（严禁写死亲密度结论）、
#           governance/runtime_policy.json
#             style_constraints.hardcoded_intimacy_rules_prohibited = true
#             task_readiness.mechanical_trigger_output_is_binary_signal_only = true
#           ADJ-003（机械触发不直接产生语义结论）
# ----------------------------------------------------------------------

#: 机械聚合层禁止出现的「关系结论」措辞。这些词描述的都是**趋势方向**，
#: 而 PyramidAggregator 不测量任何趋势 —— 一旦出现即为凭空断言。
BANNED_SEMANTIC_CONCLUSIONS = (
    "关系稳步加深",
    "关系加深",
    "感情升温",
    "越来越亲密",
    "更加信任",
    "关系恶化",
    "渐行渐远",
    "亲密度提升",
)


def _deteriorating_events(*, n_days: int = 28, per_day: int = 4, id_prefix: str = "dtr"):
    """构造一段**明确恶化**的数据：羁绊权重 r 与可信度 c 单调递减。

    这是合成诚实性的对抗样本：任何声称「关系向好」的文案在此数据上都是假话。
    """
    events = make_events(n_days=n_days, per_day=per_day, id_prefix=id_prefix)
    total = max(len(events) - 1, 1)
    for index, event in enumerate(events):
        decay = 1.0 - (index / total) * 0.9  # 单调递减：1.0 -> 0.1
        event["r"] = round(0.1 + 0.8 * decay, 4)
        event["c"] = round(0.1 + 0.8 * decay, 4)
    return events


class TestSynthesisHonesty:
    def test_policy_basis_for_this_group_still_exists(self):
        """本组测试的法律依据必须真实存在（引用而非复制；被改名/删除即红）。"""
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        assert policy["style_constraints"]["hardcoded_intimacy_rules_prohibited"] is True
        assert (
            policy["task_readiness"]["mechanical_trigger_output_is_binary_signal_only"]
            is True
        )

    def test_no_relationship_conclusion_on_deteriorating_data(self):
        """在 r/c 单调递减的恶化数据上，任何尺度都不得输出关系向好文案。"""
        events = _deteriorating_events()
        aggregator = PyramidAggregator()
        week_size = 7 * 4  # 一周 = 7 天 × 每天 4 条
        summaries = [
            aggregator.generate_materialized_rollup("DAY", "dim_h", events[:4]),
            aggregator.generate_materialized_rollup("WEEK", "dim_h", events[:week_size]),
            aggregator.generate_materialized_rollup("MONTH", "dim_h", events),
            aggregator.generate_materialized_rollup("YEAR", "dim_h", events),
        ]
        assert len(summaries) == 4
        for summary in summaries:
            text = summary.headline + summary.synthesis_text
            for banned in BANNED_SEMANTIC_CONCLUSIONS:
                assert banned not in text, (
                    f"{summary.scale} 层输出了凭空断言 {banned!r}: {text!r}"
                )

    def test_fully_missing_5d_never_yields_a_trend_claim(self):
        """missingness_ratio == 1.0（五项 5D 全缺）时仍不得下关系结论。

        这是对修复前实现最致命的一击：旧代码在此情形下照样输出「关系稳步加深」，
        即在**完全没有 5D 数据**时编造了一个声称基于 5D 的结论。
        """
        events = make_events(n_days=7, per_day=3, with_5d=False, id_prefix="no5d")
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("WEEK", "dim_no5d", events)
        assert summary.missingness_ratio == pytest.approx(1.0)
        for banned in BANNED_SEMANTIC_CONCLUSIONS:
            assert banned not in summary.synthesis_text
        # 缺失必须被披露，不能被沉默吞掉（沉默会把降级伪装成正常）
        assert "21 项 5D 描述不完整" in summary.synthesis_text
        assert "100.0%" in summary.synthesis_text

    def test_synthesis_numeric_claims_are_reproducible_from_input(self):
        """合成文本里的每个数字都必须能由输入复算 —— 不允许装饰性数字。"""
        events = make_events(n_days=31, per_day=6)
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("MONTH", "dim_num", events)
        assert len(summary.evidence_ids) == 186
        assert len(set(summary.evidence_ids)) == 186
        assert f"沉淀了 {len(summary.evidence_ids)} 项核心事实" in summary.synthesis_text
        assert summary.missingness_ratio == 0.0
        # 数据完整时：不得出现缺失披露，也不得谎称重心不可计算
        assert "描述不完整" not in summary.synthesis_text
        assert "不可计算" not in summary.synthesis_text
        assert "时空重心" in summary.synthesis_text

    def test_uncomputable_centroid_is_disclosed_not_silently_omitted(self):
        """权重全为 0（c=0）时重心不可计算 —— 必须说出来，不能沉默省略。

        沉默省略会被上层读成「重心在原点」或「无位置信息」，那是另一种假话。
        """
        events = [
            {"id": "z1", "time": BASE, "x": 3.0, "y": 4.0, "z": 0.0, "r": 1.0, "c": 0.0},
            {
                "id": "z2",
                "time": BASE + timedelta(hours=2),
                "x": 1.0,
                "y": 1.0,
                "z": 1.0,
                "r": 1.0,
                "c": 0.0,
            },
        ]
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("DAY", "dim_zero", events)
        assert "总权重 0.000" in summary.synthesis_text
        assert "时空重心不可计算" in summary.synthesis_text
        assert summary.missingness_ratio == 0.0  # 5D 字段齐全，只是权重为零

    def test_partial_missingness_is_disclosed_with_exact_count(self):
        """部分缺失必须给出确切条数与缺失率，而非只塞进一个 ratio 字段。"""
        events = make_events(n_days=1, per_day=6, id_prefix="part")
        for index in range(4):  # 4 条缺失可信度 c
            events[index].pop("c")
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("DAY", "dim_part", events)
        assert summary.missingness_ratio == pytest.approx(4 / 6)
        assert "4 项 5D 描述不完整" in summary.synthesis_text
        assert "66.7%" in summary.synthesis_text

    def test_headline_is_a_neutral_structural_label(self):
        """headline 不得预设「演变」已经发生：单事件窗口内不存在任何演变。"""
        events = make_events(n_days=1, per_day=1, id_prefix="one")
        aggregator = PyramidAggregator()
        summary = aggregator.generate_materialized_rollup("DAY", "dim_one", events)
        assert summary.headline == "DAY 阶段汇总"
        for word in ("演变", "加深", "升温", "恶化", "变化", "改善"):
            assert word not in summary.headline
        assert summary.scale in summary.headline


# ----------------------------------------------------------------------
# 尺度-跨度守卫：scale 标签必须与内容跨度相符
# （手环 5D 滑动条按 scale 标签取内容，标签说谎 == 给错粒度）
# ----------------------------------------------------------------------


class TestScaleSpanGuard:
    def test_max_span_table_is_exact_and_monotonic(self):
        """上限表必须逐尺度精确且随尺度单调放大。

        范围被悄悄放宽（例如 MONTH 改成 90 天）是纯算术校验看不见的，
        所以这里把法定自然上限**硬编码在测试里**，与实现表双向对锁。
        """
        expected = {
            "DAY": 24 * 3600.0,
            "WEEK": 7 * 24 * 3600.0,
            "MONTH": 31 * 24 * 3600.0,  # 最长自然月
            "YEAR": 366 * 24 * 3600.0,  # 闰年
        }
        assert set(MAX_SPAN_SECONDS) == set(SCALE_ORDER)
        assert MAX_SPAN_SECONDS == expected
        spans = [MAX_SPAN_SECONDS[scale] for scale in SCALE_ORDER]
        assert spans == sorted(spans), "上限必须随尺度单调不减"
        assert len(set(spans)) == len(spans), "上限必须严格递增，不得有并列尺度"

    @pytest.mark.parametrize(
        "scale,n_days",
        [("DAY", 2), ("WEEK", 28), ("MONTH", 45), ("YEAR", 800)],
    )
    def test_overlong_span_for_declared_scale_is_rejected(self, scale, n_days):
        """跨度超过该尺度自然上限 => fail-closed，绝不静默产出错标总结。"""
        events = make_events(n_days=n_days, per_day=2, id_prefix=f"ov{scale}")
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="cannot span"):
            aggregator.generate_materialized_rollup(scale, "dim_span", events)
        # 拒绝必须发生在总结层：金字塔里不得留下这个说谎的总结
        assert all(
            aggregator.get_summary(sid).scale != scale
            or (
                aggregator.get_summary(sid).end_time
                - aggregator.get_summary(sid).start_time
            ).total_seconds()
            <= MAX_SPAN_SECONDS[scale]
            for sid in aggregator.summary_ids()
        )

    def test_longest_natural_window_is_accepted_not_rejected(self):
        """边界必须**接受**：恰好一个最长自然窗口不得被误杀（差一错误守卫）。"""
        aggregator = PyramidAggregator()
        cases = [
            ("DAY", timedelta(days=1) - timedelta(seconds=1)),
            ("WEEK", timedelta(days=7) - timedelta(seconds=1)),
            ("MONTH", timedelta(days=31) - timedelta(seconds=1)),
            ("YEAR", timedelta(days=366) - timedelta(seconds=1)),
        ]
        for index, (scale, span) in enumerate(cases):
            events = [
                {
                    "id": f"bnd{index}-a",
                    "time": BASE,
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "r": 1.0,
                    "c": 1.0,
                },
                {
                    "id": f"bnd{index}-b",
                    "time": BASE + span,
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "r": 1.0,
                    "c": 1.0,
                },
            ]
            summary = aggregator.generate_materialized_rollup(scale, "dim_bound", events)
            assert summary.scale == scale
            assert len(summary.evidence_ids) == 2
            assert (summary.end_time - summary.start_time) == span

    def test_guard_failure_never_becomes_a_deletion_path(self):
        """跨度守卫触发时，已摄入的原始事实必须仍完整永存。

        §25「总结绝不是压缩删除」对**失败路径**同样成立：报错不能顺手把证据带走，
        否则一次调用方参数错误就变成了一条删除历史的路径。
        """
        events = make_events(n_days=28, per_day=2, id_prefix="keep")
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="cannot span"):
            aggregator.generate_materialized_rollup("WEEK", "dim_keep", events)
        assert aggregator.vault_size() == len(events) == 56
        for event in events:
            assert aggregator.get_raw_event(event["id"]) == event

    def test_drill_down_subsummaries_always_satisfy_the_guard(self):
        """守卫不得破坏组合性：逐级下钻的每个子总结都天然落在自己的自然窗口内。"""
        year_start = datetime(2024, 1, 1, tzinfo=UTC)  # 闰年 366 天
        events = make_events(start=year_start, n_days=366, per_day=2, id_prefix="gd")
        aggregator = PyramidAggregator()
        year_summary = aggregator.generate_materialized_rollup("YEAR", "dim_gd", events)

        months = aggregator.drill_down(year_summary.summary_id, "MONTH")
        assert len(months) == 12, "闰年按自然月分组必须是 12 个子总结"
        for month in months:
            assert (month.end_time - month.start_time).total_seconds() <= MAX_SPAN_SECONDS[
                "MONTH"
            ]
            weeks = aggregator.drill_down(month.summary_id, "WEEK")
            assert weeks
            for week in weeks:
                assert (
                    week.end_time - week.start_time
                ).total_seconds() <= MAX_SPAN_SECONDS["WEEK"]


# ----------------------------------------------------------------------
# 下钻幂等性与逐级证据并集（无损性的可重放证明）
# ----------------------------------------------------------------------


class TestDrillDownIdempotencyAndUnion:
    def test_drill_down_is_idempotent_and_does_not_duplicate_layers(self):
        """重复下钻是纯读操作：结果稳定，且不得在金字塔里堆出重复层。"""
        events = make_events(n_days=28, per_day=5, id_prefix="idem")
        aggregator = PyramidAggregator()
        month = aggregator.generate_materialized_rollup("MONTH", "dim_idem", events)

        first = aggregator.drill_down(month.summary_id, "WEEK")
        ids_after_first = sorted(aggregator.summary_ids())
        second = aggregator.drill_down(month.summary_id, "WEEK")
        ids_after_second = sorted(aggregator.summary_ids())

        assert first, "28 天必须下钻出周子总结"
        assert [s.summary_id for s in first] == [s.summary_id for s in second]
        assert [s.evidence_ids for s in first] == [s.evidence_ids for s in second]
        assert [s.synthesis_text for s in first] == [s.synthesis_text for s in second]
        assert [s.start_time for s in first] == [s.start_time for s in second]
        assert ids_after_second == ids_after_first

    def test_drill_down_to_day_is_byte_stable_across_repeats(self):
        """DAY 层下钻可重放且返回深拷贝：污染一次不得影响下一次。"""
        events = make_events(n_days=7, per_day=3, id_prefix="byte")
        aggregator = PyramidAggregator()
        week = aggregator.generate_materialized_rollup("WEEK", "dim_byte", events)

        first = aggregator.drill_down(week.summary_id, "DAY")
        second = aggregator.drill_down(week.summary_id, "DAY")
        assert first == second == events

        first[0]["text"] = "污染尝试"
        assert aggregator.drill_down(week.summary_id, "DAY")[0]["text"] == events[0]["text"]
        assert aggregator.get_raw_event(events[0]["id"])["text"] == events[0]["text"]

    def test_evidence_union_is_lossless_through_all_four_levels(self):
        """端到端无损证明：YEAR -> MONTH -> WEEK -> DAY 逐级并集严格相等。

        既有测试只验证相邻两层；这里把四层串起来，证明任意一层都不曾丢弃证据
        —— 这是「1 秒到 10 年连续缩放」的正确性基础。
        """
        year_start = datetime(2024, 1, 1, tzinfo=UTC)
        events = make_events(start=year_start, n_days=366, per_day=2, id_prefix="u4")
        aggregator = PyramidAggregator()
        all_ids = {event["id"] for event in events}
        assert len(all_ids) == 732

        year = aggregator.generate_materialized_rollup("YEAR", "dim_u4", events)
        assert set(year.evidence_ids) == all_ids

        months = aggregator.drill_down(year.summary_id, "MONTH")
        assert set().union(*[set(m.evidence_ids) for m in months]) == all_ids

        weeks: list = []
        for month in months:
            weeks.extend(aggregator.drill_down(month.summary_id, "WEEK"))
        assert set().union(*[set(w.evidence_ids) for w in weeks]) == all_ids

        day_events: list = []
        for week in weeks:
            day_events.extend(aggregator.drill_down(week.summary_id, "DAY"))
        assert {e["id"] for e in day_events} == all_ids
        # 不仅集合相等，且无重复膨胀：每条原始事件在四层展开中恰好出现一次
        assert len(day_events) == len(all_ids)
        # 底层事实永存：四层展开之后 vault 一条不少
        assert aggregator.vault_size() == len(all_ids)

    def test_repeated_rollup_of_same_window_is_content_idempotent(self):
        """同一窗口、同一 now 重放：内容逐项相同（id 允许因去重后缀不同）。"""
        events = make_events(n_days=7, per_day=3, id_prefix="replay")
        stamp = BASE + timedelta(days=400)
        aggregator = PyramidAggregator()
        first = aggregator.generate_materialized_rollup("WEEK", "dim_rp", events, now=stamp)
        second = aggregator.generate_materialized_rollup("WEEK", "dim_rp", events, now=stamp)
        assert first.summary_id != second.summary_id
        for field_name in (
            "scale",
            "start_time",
            "end_time",
            "dimension_id",
            "headline",
            "synthesis_text",
            "evidence_ids",
            "missingness_ratio",
        ):
            assert getattr(first, field_name) == getattr(second, field_name), field_name
        # 重放不得复制底层事实（vault 按 event_id 去重且永存）
        assert aggregator.vault_size() == len(events)


# ----------------------------------------------------------------------
# 连续缩放范围（1 秒 ~ 10 年）与物化层的对应关系
# ----------------------------------------------------------------------


class TestContinuousZoomContract:
    def test_zoom_range_constant_is_exact(self):
        """1 秒到 10 年是法定滑动条范围，数值必须精确（不许写成近似值）。"""
        assert CONTINUOUS_ZOOM_SECONDS == (1, 10 * 365 * 24 * 3600)
        assert CONTINUOUS_ZOOM_SECONDS[0] < CONTINUOUS_ZOOM_SECONDS[1]

    def test_every_scale_window_fits_inside_the_zoom_range(self):
        """四尺度中任一自然窗口都必须落在滑动条量程之内。"""
        low, high = CONTINUOUS_ZOOM_SECONDS
        for scale in SCALE_ORDER:
            assert low <= MAX_SPAN_SECONDS[scale] <= high, scale

    def test_one_second_end_is_served_by_second_precision_raw_events(self):
        """滑动条 1 秒端必须由原始事件承载：秒级/微秒级时间戳不得被量化成天。"""
        events = [
            {"id": "s0", "time": BASE, "x": 0.0, "y": 0.0, "z": 0.0, "r": 0.9, "c": 0.9},
            {
                "id": "s1",
                "time": BASE + timedelta(seconds=1),
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "r": 0.9,
                "c": 0.9,
            },
            {
                "id": "s2",
                "time": BASE + timedelta(seconds=1, microseconds=500000),
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "r": 0.9,
                "c": 0.9,
            },
        ]
        aggregator = PyramidAggregator()
        week = aggregator.generate_materialized_rollup("WEEK", "dim_zoom", events)
        drilled = aggregator.drill_down(week.summary_id, "DAY")
        assert drilled == events
        # 原始时间戳逐字节保留（含微秒），这才让 1 秒端真正可缩放
        assert drilled[2]["time"] == BASE + timedelta(seconds=1, microseconds=500000)
        assert len({e["time"] for e in drilled}) == 3

    def test_coarsest_materializable_window_is_one_year(self):
        """最粗物化层是 YEAR（<= 366 天）—— 已知设计缺口，此处只固定事实。

        滑动条 1 年 ~ 10 年这一段目前只能由多个 YEAR 总结并列承载，聚合器没有
        DECADE 尺度。新增尺度会改动 SCALE_ORDER 法定序（属一级治理变更），
        故不在此私自扩展；缺口已在 M1-010R 交付报告中上报。
        """
        assert SCALE_ORDER[-1] == "YEAR"
        assert MAX_SPAN_SECONDS["YEAR"] < CONTINUOUS_ZOOM_SECONDS[1]
        events = make_events(start=BASE, n_days=366 * 3, per_day=1, id_prefix="dec")
        aggregator = PyramidAggregator()
        with pytest.raises(PyramidError, match="cannot span"):
            aggregator.generate_materialized_rollup("YEAR", "dim_dec", events)


# ----------------------------------------------------------------------
# 连续缩放全覆盖：1 秒 ~ 10 年量程内不得存在「无层可用」的死区
# 工单 §2：支持手环端侧 5D 滑动条从 1 秒到 10 年连续无损缩放与下钻
# ----------------------------------------------------------------------


def _decade_events(*, first_year: int = 2020, years: int = 10, id_prefix: str = "dec"):
    """按日历日铺满整整十年的原始事件（每天 1 条）。"""
    events = []
    day = datetime(first_year, 1, 1, tzinfo=UTC)
    stop = datetime(first_year + years, 1, 1, tzinfo=UTC)
    index = 0
    while day < stop:
        events.append(
            {
                "id": f"{id_prefix}-{index:05d}",
                "time": day,
                "text": f"原始事实 {day.date().isoformat()}",
                "x": round((index % 50) * 0.1, 4),
                "y": float(index % 7),
                "z": 1.0,
                "r": 0.8,
                "c": 0.9,
            }
        )
        day += timedelta(days=1)
        index += 1
    return events


class TestContinuousZoomCoverage:
    def test_scale_for_zoom_is_total_over_the_entire_range(self):
        """全量程密集采样：每一个滑动条位置都必须落到某个物化层上。

        这是「连续缩放」的实质含义 —— 不是四个离散档位，而是 1 秒到 10 年
        之间**任意**位置都有层可用。若存在死区，滑动条拖到那里就是空白。
        """
        low, high = CONTINUOUS_ZOOM_SECONDS
        samples = 400
        seen = set()
        previous_rank = -1
        for i in range(samples + 1):
            # 对数等距采样：细端与粗端都取到足够密度
            zoom = low * (high / low) ** (i / samples)
            scale = scale_for_zoom(zoom)
            assert scale in SCALE_ORDER, f"zoom={zoom:.3f}s 映射到非法尺度 {scale!r}"
            seen.add(scale)
            # 单调性：视野变大，承载尺度只能变粗或不变，绝不能变细
            rank = SCALE_ORDER.index(scale)
            assert rank >= previous_rank, (
                f"zoom={zoom:.3f}s 处尺度非单调：{SCALE_ORDER[previous_rank]} -> {scale}"
            )
            previous_rank = rank
        # 非退化：四个尺度都必须真的被用到。全部映射成 YEAR 也满足"全射"，
        # 但那是个没用的映射 —— 这一条挡住这种假绿。
        assert seen == set(SCALE_ORDER), f"量程内未被使用的尺度: {set(SCALE_ORDER) - seen}"

    def test_scale_for_zoom_boundaries_are_exact(self):
        """四个档位边界必须精确（上限硬编码在测试里，与实现双向对锁）。"""
        cases = [
            ("DAY", 1.0),                      # 量程下限
            ("DAY", 86400.0),                  # 恰好一天
            ("WEEK", 86400.001),               # 刚过一天
            ("WEEK", 604800.0),                # 恰好一周
            ("MONTH", 604800.001),             # 刚过一周
            ("MONTH", 2678400.0),              # 恰好 31 天
            ("YEAR", 2678400.001),             # 刚过 31 天
            ("YEAR", 31622400.0),              # 恰好 366 天（YEAR 自然窗口上限）
            ("YEAR", 315360000.0),             # 量程上限 10 年：由多个 YEAR 节点平铺
        ]
        for expected, zoom in cases:
            assert scale_for_zoom(zoom) == expected, f"zoom={zoom} 应为 {expected}"

    def test_scale_for_zoom_rejects_out_of_contract_input(self):
        """量程外与非法输入一律 fail-closed，不许悄悄夹到最近档位。"""
        _, high = CONTINUOUS_ZOOM_SECONDS
        for bad in (0, 0.0, -1, -0.5, float("nan"), float("inf"), high + 1, "7", None, True):
            with pytest.raises(PyramidError):
                scale_for_zoom(bad)

    def test_ten_year_band_is_tiled_by_year_nodes_losslessly(self):
        """**1 年 ~ 10 年段的无损证明**：十年视野由 10 个 YEAR 节点平铺，
        其 evidence_ids 之并集 == 全部底层原始事件，一条不少。

        这一段超过 YEAR 的自然窗口（366 天），不可能有单个总结覆盖。
        此前聚合器没有任何按维度+时间范围检索物化节点的入口，
        滑动条拖到十年级将取不到数据 —— 本测试固定该入口的存在与无损性。
        """
        events = _decade_events()
        assert len(events) == 3653  # 2020~2029，含 2020/2024/2028 三个闰年
        all_ids = {event["id"] for event in events}

        aggregator = PyramidAggregator()
        by_year: dict = {}
        for event in events:
            by_year.setdefault(event["time"].year, []).append(event)
        assert sorted(by_year) == list(range(2020, 2030))

        year_nodes = []
        for year in sorted(by_year):
            year_nodes.append(
                aggregator.generate_materialized_rollup("YEAR", "dim_decade", by_year[year])
            )
        assert len(year_nodes) == 10
        for node in year_nodes:
            span = (node.end_time - node.start_time).total_seconds()
            assert span <= MAX_SPAN_SECONDS["YEAR"]

        # 滑动条拖到十年级：center=2025-01-01, zoom=10 年
        view = aggregator.slider_view(
            "dim_decade", datetime(2025, 1, 1, tzinfo=UTC), CONTINUOUS_ZOOM_SECONDS[1]
        )
        assert len(view) == 10, f"十年视野应铺满 10 个 YEAR 节点，实得 {len(view)}"
        assert all(node.scale == "YEAR" for node in view)
        assert [node.start_time for node in view] == sorted(n.start_time for n in view)

        union = set().union(*[set(node.evidence_ids) for node in view])
        assert union == all_ids, "十年视野的证据并集必须等于全部底层事实"

        # 平铺不得重复计数：每个节点互不相交，总数恰好等于底层事件数
        assert sum(len(node.evidence_ids) for node in view) == len(all_ids)

        # 底层事实永存：十年物化 + 全量检索之后 vault 一条不少
        assert aggregator.vault_size() == len(all_ids)
        for node in view:
            drilled = aggregator.drill_down(node.summary_id, "DAY")
            assert {e["id"] for e in drilled} == set(node.evidence_ids)

    def test_one_second_end_is_served_by_raw_events_in_range(self):
        """**1 秒端的数据源**：亚日级视野直接取原始事件，闭区间、含边界。"""
        events = [
            {"id": "t0", "time": BASE, "x": 0.0, "y": 0.0, "z": 0.0, "r": 0.9, "c": 0.9},
            {"id": "t1", "time": BASE + timedelta(milliseconds=500), "x": 0.0, "y": 0.0, "z": 0.0, "r": 0.9, "c": 0.9},
            {"id": "t2", "time": BASE + timedelta(seconds=1), "x": 0.0, "y": 0.0, "z": 0.0, "r": 0.9, "c": 0.9},
            {"id": "t3", "time": BASE + timedelta(seconds=2), "x": 0.0, "y": 0.0, "z": 0.0, "r": 0.9, "c": 0.9},
        ]
        aggregator = PyramidAggregator()
        aggregator.generate_materialized_rollup("DAY", "dim_sec", events)

        window = aggregator.raw_events_in_range(BASE, BASE + timedelta(seconds=1))
        assert [e["id"] for e in window] == ["t0", "t1", "t2"], "闭区间必须含两端"

        sub_second = aggregator.raw_events_in_range(
            BASE, BASE + timedelta(milliseconds=500)
        )
        assert [e["id"] for e in sub_second] == ["t0", "t1"]
        # 1 秒端不塌缩：三个互异时间戳必须各自可辨
        assert len({e["time"] for e in window}) == 3

    def test_raw_events_in_range_returns_deep_copies(self):
        """区间取数返回深拷贝：污染结果不得回灌证据保险库。"""
        events = make_events(n_days=1, per_day=4, id_prefix="rng")
        aggregator = PyramidAggregator()
        aggregator.generate_materialized_rollup("DAY", "dim_rng", events)

        got = aggregator.raw_events_in_range(BASE, BASE + timedelta(days=1))
        assert got == events
        got[0]["text"] = "污染尝试"
        again = aggregator.raw_events_in_range(BASE, BASE + timedelta(days=1))
        assert again[0]["text"] == events[0]["text"]
        assert aggregator.get_raw_event(events[0]["id"])["text"] == events[0]["text"]

    def test_range_queries_on_empty_vault_return_empty_not_error(self):
        """vault 为空时区间查询返回空列表 —— 但必须说清楚这不是"没有事实"。

        聚合器的 vault 只保存**曾经被某次物化摄入过**的事件；它不是原始事实的
        权威存储（那是 storage 层的职责，见交付报告 G1）。空结果与"该区间确实
        没有事实"在语义上不可区分，端侧不得把空列表直接渲染成"这一天什么都没发生"。
        """
        aggregator = PyramidAggregator()
        assert aggregator.raw_events_in_range(BASE, BASE + timedelta(days=1)) == []
        assert (
            aggregator.summaries_in_range("YEAR", "dim_x", BASE, BASE + timedelta(days=1))
            == []
        )
        assert aggregator.slider_view("dim_x", BASE, 3600) == []

    def test_summaries_in_range_uses_intersection_not_containment(self):
        """跨越视野边界的总结必须被返回：它的证据落在视野内。"""
        events = make_events(n_days=28, per_day=4, id_prefix="isect")
        aggregator = PyramidAggregator()
        month = aggregator.generate_materialized_rollup("MONTH", "dim_isect", events)

        # 视野只覆盖该月总结的前 3 天
        partial = aggregator.summaries_in_range(
            "MONTH", "dim_isect", BASE, BASE + timedelta(days=3)
        )
        assert [s.summary_id for s in partial] == [month.summary_id]

        # 视野完全在总结之前 => 空
        before = aggregator.summaries_in_range(
            "MONTH", "dim_isect", BASE - timedelta(days=10), BASE - timedelta(days=5)
        )
        assert before == []

    def test_summaries_in_range_isolates_scale_and_dimension(self):
        """检索必须按尺度与维度双重隔离，不得串台。"""
        events = make_events(n_days=7, per_day=4, id_prefix="iso2")
        aggregator = PyramidAggregator()
        week_a = aggregator.generate_materialized_rollup("WEEK", "dim_a", events)
        aggregator.generate_materialized_rollup("WEEK", "dim_b", events)
        aggregator.generate_materialized_rollup("DAY", "dim_a", events[:4])
        window = (BASE - timedelta(days=1), BASE + timedelta(days=30))

        assert [s.summary_id for s in aggregator.summaries_in_range("WEEK", "dim_a", *window)] == [
            week_a.summary_id
        ]
        assert all(
            s.dimension_id == "dim_b"
            for s in aggregator.summaries_in_range("WEEK", "dim_b", *window)
        )
        assert all(
            s.scale == "DAY" for s in aggregator.summaries_in_range("DAY", "dim_a", *window)
        )
        assert aggregator.summaries_in_range("YEAR", "dim_a", *window) == []
        assert aggregator.summaries_in_range("WEEK", "dim_absent", *window) == []

    def test_range_queries_reject_inverted_window(self):
        """起点晚于终点是调用方错误，必须 fail-closed 而不是静默返回空。"""
        events = make_events(n_days=1, per_day=2, id_prefix="inv")
        aggregator = PyramidAggregator()
        aggregator.generate_materialized_rollup("DAY", "dim_inv", events)
        with pytest.raises(PyramidError, match="empty query window"):
            aggregator.raw_events_in_range(BASE + timedelta(days=1), BASE)
        with pytest.raises(PyramidError, match="empty query window"):
            aggregator.summaries_in_range(
                "DAY", "dim_inv", BASE + timedelta(days=1), BASE
            )
        # slider_view 的负 zoom 由量程校验先拦住（不是窗口校验）
        with pytest.raises(PyramidError, match="positive finite"):
            aggregator.slider_view("dim_inv", BASE, -5)

    def test_time_index_invalidates_when_vault_grows(self):
        """惰性时间索引必须随 vault 增长失效重建，否则新事实会被查询漏掉。"""
        first = make_events(n_days=1, per_day=3, id_prefix="idx1")
        aggregator = PyramidAggregator()
        aggregator.generate_materialized_rollup("DAY", "dim_idx", first)
        assert len(aggregator.raw_events_in_range(BASE, BASE + timedelta(days=1))) == 3

        later = make_events(n_days=1, per_day=3, id_prefix="idx2")
        aggregator.generate_materialized_rollup("DAY", "dim_idx", later)
        window = aggregator.raw_events_in_range(BASE, BASE + timedelta(days=1))
        assert len(window) == 6, "索引未失效 => 后摄入的事实被漏掉"
        assert {e["id"] for e in window} == {e["id"] for e in first + later}

    def test_slider_view_serves_every_zoom_with_the_mapped_scale(self):
        """滑动条在任意档位取回的节点，尺度都必须等于 scale_for_zoom 的结果。"""
        events = _decade_events(first_year=2024, years=2, id_prefix="sv")
        aggregator = PyramidAggregator()
        by_year: dict = {}
        for event in events:
            by_year.setdefault(event["time"].year, []).append(event)
        for year in sorted(by_year):
            aggregator.generate_materialized_rollup("YEAR", "dim_sv", by_year[year])
        # 再物化一层 MONTH，供细档位取数
        by_month: dict = {}
        for event in events:
            by_month.setdefault((event["time"].year, event["time"].month), []).append(event)
        for key in sorted(by_month):
            aggregator.generate_materialized_rollup("MONTH", "dim_sv", by_month[key])

        center = datetime(2025, 1, 1, tzinfo=UTC)
        # (zoom, 应映射到的尺度, 该档位应取到的节点数)
        # 节点数必须逐个写死：all([]) 恒为真，只断言尺度会让空结果蒙混过关。
        expectations = [
            (3600.0, "DAY", 0),        # 本维度未物化 DAY 层 -> 端侧应改取 raw_events_in_range
            (86400.0, "DAY", 0),
            (604800.0, "WEEK", 0),     # 本维度未物化 WEEK 层
            (2678400.0, "MONTH", 2),   # 视野横跨 2024-12 与 2025-01 两个月节点
            (31536000.0, "YEAR", 2),   # 十年视野铺满 2024/2025 两个 YEAR 节点
        ]
        for zoom, expected_scale, expected_count in expectations:
            assert scale_for_zoom(zoom) == expected_scale
            view = aggregator.slider_view("dim_sv", center, zoom)
            assert len(view) == expected_count, (
                f"zoom={zoom} 在 {expected_scale} 层应取到 {expected_count} 个节点，实得 {len(view)}"
            )
            assert all(node.scale == expected_scale for node in view)
        decade = aggregator.slider_view("dim_sv", center, CONTINUOUS_ZOOM_SECONDS[1])
        assert {n.start_time.year for n in decade} == {2024, 2025}
