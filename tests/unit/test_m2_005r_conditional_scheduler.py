"""M2-005R 条件驱动调度双轨引擎——四大硬门禁的机械证。

  1. DORMANT 物理隐形：200 任务混合注册，board_view 键集绝无 DORMANT，token 恒 0
  2. Level-1 机械快轨：时间/围栏/心率纯 Python 判定，model_calls 结构零，p99 ≤1ms
  3. Level-2 机会式捎带：语义任务熬过一切 tick 保持 DORMANT，只在用户唤醒+场景
     相关时被捎到 READY；引擎无自唤醒 API（self_wakes_issued 结构零）
  4. 非法跃迁 100% 拦截：4×4 全矩阵减去三条主链边 = 13 项全抛 IllegalStateTransitionError
"""

from __future__ import annotations

import statistics
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from aios_core.scheduler.conditional_engine import (
    MODEL_CALLS_LEVEL1,
    SELF_WAKES_STRUCTURAL,
    ConditionalSchedulingEngine,
    ConditionalTask,
    GeoFenceCondition,
    HeartRateCondition,
    IllegalStateTransitionError,
    SemanticSceneCondition,
    TaskState,
    TimeExpiryCondition,
)

NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
SHANGHAI_OFFICE = (31.2304, 121.4737)


def _night_series(days: int, breach: bool, *, gap_after: int = 0) -> list[tuple[datetime, float]]:
    """连续 days 个夜间窗读数；breach=True 每窗含一次 >95bpm。gap_after 空窗天数。"""
    out: list[tuple[datetime, float]] = []
    base_night = date(2026, 9, 10)
    for d in range(days):
        night = datetime(base_night.year, base_night.month, base_night.day, 23, 0, tzinfo=timezone.utc) + timedelta(days=d + gap_after)
        out.append((night, 72.0))
        out.append((night + timedelta(hours=1, minutes=30), 99.0 if breach else 80.0))
    return out


# ---------------------------------------------------------------------------
# 门禁 1：DORMANT 物理隐形（Token 严格为 0）
# ---------------------------------------------------------------------------


def test_200_tasks_dormant_invisible_from_board():
    engine = ConditionalSchedulingEngine()
    for i in range(150):
        engine.register(ConditionalTask(
            task_id=f"mech-{i}", subject_id="director",
            condition=TimeExpiryCondition(at=NOW + timedelta(days=30)),
        ))
    for i in range(50):
        engine.register(ConditionalTask(
            task_id=f"sem-{i}", subject_id="director",
            condition=SemanticSceneCondition(scene_tags=frozenset({f"scene-{i}"})),
        ))
    view = engine.board_view()
    assert view == {}, "200 项未成熟连一个键都不许进看板"
    assert engine.dormant_tokens_exposed == 0
    # 只有 5 项 READY 后：看板恰好 5 键，其余 195 依旧隐形
    for i in range(5):
        engine.transition(f"mech-{i}", TaskState.READY)
    view = engine.board_view()
    assert len(view) == 5 and all(v == "READY" for v in view.values())
    assert all(f"sem-{i}" not in view for i in range(50))
    assert engine.dormant_tokens_exposed == 0


# ---------------------------------------------------------------------------
# 门禁 2：Level-1 机械快轨 0 Token
# ---------------------------------------------------------------------------


def test_time_expiry_fast_track_auto_ready_zero_llm():
    engine = ConditionalSchedulingEngine()
    engine.register(ConditionalTask(
        task_id="t1", subject_id="director", condition=TimeExpiryCondition(at=NOW - timedelta(minutes=1)),
    ))
    report = engine.mechanical_tick(NOW)
    assert report.newly_ready == ["t1"]
    assert engine.state_of("t1") is TaskState.READY
    assert report.model_calls == MODEL_CALLS_LEVEL1 == 0


def test_time_expiry_edge_inclusive_and_future_stays_dormant():
    engine = ConditionalSchedulingEngine()
    engine.register(ConditionalTask("equal", "u", TimeExpiryCondition(at=NOW)))
    engine.register(ConditionalTask("future", "u", TimeExpiryCondition(at=NOW + timedelta(seconds=1))))
    report = engine.mechanical_tick(NOW)
    assert set(report.newly_ready) == {"equal"}, "到点即含（>=），未来一秒都不算"


def test_geofence_inside_outside_boundary():
    engine = ConditionalSchedulingEngine()
    engine.register(ConditionalTask(
        "geo-sign", "director", GeoFenceCondition(*SHANGHAI_OFFICE, radius_m=200.0),
    ))
    inside = {"director": (31.2305, 121.4738)}
    outside = {"director": (31.3000, 121.5000)}  # ≈8km 外
    r1 = engine.mechanical_tick(NOW, geo_positions=outside)
    assert r1.newly_ready == []
    r2 = engine.mechanical_tick(NOW, geo_positions=inside)
    assert r2.newly_ready == ["geo-sign"]
    assert r2.model_calls == 0


def test_heart_rate_three_consecutive_nights_required():
    engine = ConditionalSchedulingEngine()
    cond = HeartRateCondition(threshold_bpm=95.0, min_consecutive_windows=3)
    engine.register(ConditionalTask("hr-cardio", "director", cond))

    ok2 = engine.mechanical_tick(NOW, hr_series={"director": _night_series(2, True)})
    assert ok2.newly_ready == [], "连续 2 窗不构成 3 窗硬条件"

    ok3 = engine.mechanical_tick(NOW, hr_series={"director": _night_series(3, True)})
    assert ok3.newly_ready == ["hr-cardio"]


def test_heart_rate_broken_streak_and_clean_nights_rejected():
    engine = ConditionalSchedulingEngine()
    cond = HeartRateCondition(threshold_bpm=95.0, min_consecutive_windows=3)
    engine.register(ConditionalTask("hr-a", "director", cond))
    # 两窗越标 + 中间断一天 + 一窗越标：断链不算
    series = _night_series(2, True) + _night_series(1, True, gap_after=3)
    # 无越标的三连窗：干净不触发
    engine.register(ConditionalTask("hr-b", "director",
                                    HeartRateCondition(95.0, 3, subject_key="other")))
    r = engine.mechanical_tick(
        NOW,
        hr_series={"director": series, "other": _night_series(3, False)},
    )
    assert "hr-a" not in r.newly_ready and "hr-b" not in r.newly_ready


def test_mechanical_eval_p99_within_1ms_at_200_tasks():
    samples = []
    for k in range(7):
        engine = ConditionalSchedulingEngine()  # 每轮全新引擎：考察量恒定 200
        for i in range(200):
            engine.register(ConditionalTask(f"m-{i}", "director",
                                            TimeExpiryCondition(at=NOW + timedelta(hours=i + 1))))
        report = engine.mechanical_tick(NOW)
        samples.append(report.worst_eval_ms)
        assert report.examined == 200 and report.model_calls == 0
    p99 = statistics.quantiles(samples, n=100)[98] if len(samples) > 1 else samples[0]
    assert p99 <= 1.0, f"单条件机械判定 p99={p99:.3f}ms 越 1ms 红线"


# ---------------------------------------------------------------------------
# 门禁 3：Level-2 机会式捎带
# ---------------------------------------------------------------------------


def test_semantic_tasks_survive_ticks_until_piggybacked():
    engine = ConditionalSchedulingEngine()
    engine.register(ConditionalTask(
        "sem-context", "director",
        SemanticSceneCondition(scene_tags=frozenset({"negotiation", "office"})),
    ))
    for k in range(5):
        r = engine.mechanical_tick(NOW + timedelta(minutes=k))
        assert engine.state_of("sem-context") is TaskState.DORMANT
        assert r.semantic_skipped == 1 and r.examined == 0

    miss = engine.piggyback_on_user_wake({"gym", "running"})
    assert miss.newly_ready == [], "场景不相关：捎到也不评 READY"
    assert engine.state_of("sem-context") is TaskState.DORMANT

    hit = engine.piggyback_on_user_wake({"office", "negotiation"})
    assert hit.newly_ready == ["sem-context"]
    assert engine.state_of("sem-context") is TaskState.READY
    assert hit.self_wakes_issued == SELF_WAKES_STRUCTURAL == 0
    assert hit.model_calls == 0


def test_piggyback_evaluation_counter_runs_only_on_user_wake():
    engine = ConditionalSchedulingEngine()
    engine.register(ConditionalTask("s1", "u", SemanticSceneCondition(scene_tags=frozenset({"x"}))))
    assert engine.piggyback_on_user_wake(set()).piggyback_evaluations == 1
    assert engine.piggyback_on_user_wake(set()).piggyback_evaluations == 2
    engine.mechanical_tick(NOW)  # tick 绝不动计数器
    assert engine.piggyback_on_user_wake(set()).piggyback_evaluations == 3


# ---------------------------------------------------------------------------
# 门禁 4：状态机非法跃迁 100% 拦截（全矩阵）
# ---------------------------------------------------------------------------


def test_illegal_transitions_full_matrix_intercepted():
    legal = {
        (TaskState.DORMANT, TaskState.READY),
        (TaskState.READY, TaskState.RUNNING),
        (TaskState.RUNNING, TaskState.COMPLETED),
    }
    states = list(TaskState)
    intercepted = 0
    for src in states:
        for dst in states:
            engine = ConditionalSchedulingEngine()
            engine.register(ConditionalTask("t", "u", TimeExpiryCondition(at=NOW)))
            # 走到源态
            path = {
                TaskState.DORMANT: [],
                TaskState.READY: [TaskState.READY],
                TaskState.RUNNING: [TaskState.READY, TaskState.RUNNING],
                TaskState.COMPLETED: [TaskState.READY, TaskState.RUNNING, TaskState.COMPLETED],
            }[src]
            for step in path:
                engine.transition("t", step)
            if (src, dst) in legal:
                engine.transition("t", dst)  # 合法不过
            else:
                with pytest.raises(IllegalStateTransitionError):
                    engine.transition("t", dst)
                intercepted += 1
    assert intercepted == len(states) ** 2 - len(legal) == 13


def test_happy_path_full_chain_and_completed_is_terminal():
    engine = ConditionalSchedulingEngine()
    engine.register(ConditionalTask("deal", "director", TimeExpiryCondition(at=NOW)))
    engine.mechanical_tick(NOW + timedelta(seconds=1))
    engine.transition("deal", TaskState.RUNNING)
    engine.transition("deal", TaskState.COMPLETED)
    with pytest.raises(IllegalStateTransitionError):
        engine.transition("deal", TaskState.RUNNING)
    assert engine.board_view() == {}


def test_unknown_condition_species_rejected_at_registration():
    engine = ConditionalSchedulingEngine()
    with pytest.raises(TypeError, match="条件物种"):
        engine.register(ConditionalTask("x", "u", condition=object()))


def test_semantic_condition_never_enters_level1_channel():
    """双轨机械分界：语义条件的 evaluate 在 Level-1 语境被调用 = 立刻炸。"""
    cond = SemanticSceneCondition(scene_tags=frozenset({"office"}))
    with pytest.raises(RuntimeError, match="禁止进入"):
        cond.evaluate(object())
