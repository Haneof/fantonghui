"""M1-010R 5D 时空多尺度连续聚合器与时间金字塔物化视图 - 验收单测。

宪法第二十五至二十七条铁律验收断言：
- 高层总结必须携带所有底层证据指针列表（evidence_ids），证据链完整度 100%；
- 下钻时底层事件完好无损（深拷贝、按时间序、内容逐字节一致）；
- 下钻响应 <= 45ms；
- 生成月/年总结后，日记录与原始事件永存于证据保险库，绝不删除、绝不覆盖。
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.summaries import (
    SCALE_ORDER,
    PyramidAggregator,
    PyramidError,
    TimePyramidSummary,
    finer_than,
)

UTC = timezone.utc
BASE = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


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
        assert summary.headline == "MONTH 阶段性演变概览"
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
        week_summary = aggregator.generate_materialized_rollup("WEEK", "dim_const", events)
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
# 保险库隔离补强（Agent-03 复核批：tuple 携带可变元素 + 注册表共享对象）
# 宪法第 25-27 条推论——"vault 只读"若可经元组内层污染，铁律即为纸面。
# ----------------------------------------------------------------------


class TestIsolationHardening:
    def test_mutable_inside_tuple_cannot_pollute_vault(self):
        inner = {"k": 1}
        events = [
            {
                "id": "tup-1",
                "time": BASE,
                "text": "原始事实",
                "payload": (inner,),
                "plain_scalars": (1, 2, 3),
            }
        ]
        agg = PyramidAggregator()
        summary = agg.generate_materialized_rollup("WEEK", "dim_iso", events)
        drilled = agg.drill_down(summary.summary_id, "DAY")
        assert drilled[0]["payload"][0] is not inner, "含可变元素的 tuple 必须物建"
        drilled[0]["payload"][0]["k"] = 999
        drilled[0]["plain_scalars"] is not None
        assert agg.get_raw_event("tup-1")["payload"][0]["k"] == 1, "tuple 内层污染了保险库原件"

    def test_scalar_only_tuple_shares_original_fast_path(self):
        events = [{"id": "tup-2", "time": BASE, "text": "x", "coords": (1.5, -2.0, 3)}]
        agg = PyramidAggregator()
        summary = agg.generate_materialized_rollup("DAY", "dim_iso", events)
        assert summary.evidence_ids == ["tup-2"]
        raw = agg.get_raw_event("tup-2")
        assert raw["coords"] == (1.5, -2.0, 3)  # 值等价即可；纯标量元组允许共享原件省开销

    def test_mutating_returned_summary_cannot_pollute_registry(self):
        events = make_events(n_days=2, per_day=2, id_prefix="reg")
        agg = PyramidAggregator()
        summary = agg.generate_materialized_rollup("WEEK", "dim_reg", events)
        summary.evidence_ids.append("evil")
        summary.headline = "被篡改的标题"
        registry_copy = agg.get_summary(summary.summary_id)
        assert "evil" not in registry_copy.evidence_ids, "注册表被共享对象就地篡改污染"
        assert registry_copy.headline != "被篡改的标题"
        further = agg.drill_down(summary.summary_id, "DAY")  # 下钻仍须基于干净 record
        assert len(further) == 4


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
