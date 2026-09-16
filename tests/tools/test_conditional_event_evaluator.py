"""轻量条件事件求值器（TLP-LCE-003）：宽相位建索引 + 窄相位只碰命中桶。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aios_core.scheduler.conditional_engine import Condition, ConditionKind
from aios_core.tools.conditional_event_evaluator import (
    EvaluatorSignals,
    LightweightConditionalEventEvaluator,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)


def _evaluator(count: int = 300) -> LightweightConditionalEventEvaluator:
    evaluator = LightweightConditionalEventEvaluator()
    for index in range(count):
        if index % 3 == 0:
            condition = Condition(
                kind=ConditionKind.ABSOLUTE_TIME,
                summary=f"时间 {index}",
                deadline=NOW + timedelta(days=100 + index),
            )
        elif index % 3 == 1:
            condition = Condition(
                kind=ConditionKind.GEO_FENCE,
                summary=f"围栏 {index}",
                place_key=f"place_{index % 10}",
            )
        else:
            condition = Condition(
                kind=ConditionKind.VITAL_THRESHOLD,
                summary=f"指标 {index}",
                metric=f"metric_{index % 5}",
                comparator=">",
                threshold=110.0,
                consecutive_days=1,
            )
        evaluator.register(f"task_{index}", title=f"任务 {index}", conditions=(condition,))
    return evaluator


def test_silent_tick_touches_nothing() -> None:
    evaluator = _evaluator()
    report = evaluator.tick(EvaluatorSignals(now=NOW))
    assert report.tasks_evaluated == 0
    assert report.tasks_registered == 300
    assert report.elapsed_ms < 1.0
    assert report.llm_calls == 0


def test_signal_tick_only_touches_matching_buckets() -> None:
    evaluator = _evaluator()
    report = evaluator.tick(
        EvaluatorSignals(now=NOW, present_places=("place_4",), vitals={"metric_0": (120.0,)})
    )
    assert report.tasks_evaluated > 0
    assert report.tasks_evaluated < 300 // 4
    assert report.touched_ratio < 0.25
    assert report.llm_calls == 0
    assert report.fired_task_ids


def test_absolute_time_deadline_pops_from_heap() -> None:
    evaluator = LightweightConditionalEventEvaluator()
    evaluator.register(
        "task_due",
        title="到期的任务",
        conditions=(
            Condition(
                kind=ConditionKind.ABSOLUTE_TIME,
                summary="到期",
                deadline=NOW - timedelta(seconds=1),
            ),
        ),
    )
    report = evaluator.tick(EvaluatorSignals(now=NOW))
    assert "task_due" in report.fired_task_ids
    assert report.time_heap_popped >= 1
    assert evaluator.earliest_pending_us() is None


def test_semantic_conditions_are_blocked_not_evaluated() -> None:
    evaluator = LightweightConditionalEventEvaluator()
    evaluator.register(
        "task_semantic",
        title="机械前提 + 语义确认",
        conditions=(
            Condition(
                kind=ConditionKind.GEO_FENCE,
                summary="到达公司围栏",
                place_key="place_office",
            ),
            Condition(
                kind=ConditionKind.SEMANTIC_SCENE,
                summary="语义场景命中：深夜仍在改需求",
                scene_tags=("深夜", "改需求"),
            ),
        ),
    )
    # 没有新信号时：连一次机械比较都不做（窄相位只碰变化的桶）
    quiet = evaluator.tick(EvaluatorSignals(now=NOW))
    assert quiet.tasks_evaluated == 0
    assert quiet.fired_task_ids == ()
    # 机械前提满足之后：仍需语义确认 → 挂起（不消耗任何大模型调用）
    arrived = evaluator.tick(EvaluatorSignals(now=NOW, present_places=("place_office",)))
    assert "task_semantic" in arrived.blocked_by_semantics
    assert arrived.fired_task_ids == ()
    assert evaluator.llm_calls == 0


def test_index_sizes_report_buckets() -> None:
    evaluator = _evaluator(90)
    sizes = evaluator.index_sizes()
    assert sizes["time_heap"] >= 1
    assert sizes["geo_places"] >= 1
    assert sizes["vital_metrics"] >= 1
