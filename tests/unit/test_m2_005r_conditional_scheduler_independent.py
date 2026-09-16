"""M2-005R 条件驱动任务调度双轨引擎单测。

业务情境：法务总监挂载 200 项跨周期复杂条件任务。
四大硬门禁逐条断言，另附 200 项任务下的 Level-1 判定延迟基准。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from aios_core.contracts.enums import ErrorCode, TaskState
from aios_core.scheduler.conditional_engine_independent import (
    ConditionalTaskRecord,
    ConditionalTaskState,
    EvaluationContext,
    EvaluationLevel,
    GeofenceCondition,
    HeartRateCondition,
    IllegalStateTransitionError,
    SemanticCondition,
    TimeReachedCondition,
    TwoTrackConditionalScheduler,
    to_frozen_task_state,
)

NOW = datetime(2026, 9, 16, 9, 0, 0, tzinfo=UTC)
SHANGHAI_OFFICE_LAT = 31.2304
SHANGHAI_OFFICE_LON = 121.4737


def _ctx(**overrides: object) -> EvaluationContext:
    base: dict[str, object] = {"now": NOW}
    base.update(overrides)
    return EvaluationContext(**base)  # type: ignore[arg-type]


def _time_task(task_id: str = "task_sign_buyback", due: datetime = NOW) -> ConditionalTaskRecord:
    return ConditionalTaskRecord(
        task_id=task_id,
        title="签署对赌回购协议",
        conditions=(TimeReachedCondition(due_at=due),),
    )


# ---------------------------------------------------------------------------
# 门禁 1：未成熟任务 Token 严格为 0
# ---------------------------------------------------------------------------


def test_gate1_dormant_tasks_are_physically_absent_from_manifest() -> None:
    """DORMANT 不是"渲染成空串"，是根本不进列表。"""
    scheduler = TwoTrackConditionalScheduler(
        [
            _time_task("t_due", due=NOW - timedelta(hours=1)),
            _time_task("t_not_due", due=NOW + timedelta(days=30)),
        ]
    )

    # 尚未 advance：两项都是 DORMANT
    assert scheduler.dormant_count == 2
    assert scheduler.assemble_ready_manifest() == ()
    assert scheduler.dormant_manifest_tokens() == 0
    assert scheduler.ready_manifest_tokens() == 0

    # 只有到期的那项进入看板
    scheduler.advance_level1(_ctx())
    manifest = scheduler.assemble_ready_manifest()
    assert [t.task_id for t in manifest] == ["t_due"]
    assert scheduler.dormant_manifest_tokens() == 0
    assert scheduler.ready_manifest_tokens() == 120


def test_gate1_200_tasks_only_ready_ones_cost_tokens() -> None:
    """200 项任务中只有 1 项就绪时，看板 token 只按那 1 项计。"""
    tasks = [_time_task(f"t_{i:03d}", due=NOW + timedelta(days=i + 1)) for i in range(200)]
    scheduler = TwoTrackConditionalScheduler(tasks)
    scheduler.transition("t_000", ConditionalTaskState.READY)

    assert scheduler.dormant_count == 199
    assert len(scheduler.assemble_ready_manifest()) == 1
    # 199 项休眠任务的 token 贡献严格为 0
    assert scheduler.dormant_manifest_tokens() == 0
    assert scheduler.ready_manifest_tokens() == 120
    # 对照：若违宪把全部任务灌进 Prompt，将是 24,000 token
    assert 200 * 120 == 24_000


def test_gate1_dormant_task_ids_never_appear_in_manifest_payload() -> None:
    """序列化后的看板载荷里不得出现任何休眠任务标识。"""
    scheduler = TwoTrackConditionalScheduler(
        [
            _time_task("t_ready", due=NOW - timedelta(hours=1)),
            _time_task("t_sleeping", due=NOW + timedelta(days=30)),
        ]
    )
    scheduler.advance_level1(_ctx())

    payload = "\n".join(t.title + t.task_id for t in scheduler.assemble_ready_manifest())
    assert "t_sleeping" not in payload
    assert "t_ready" in payload


# ---------------------------------------------------------------------------
# 门禁 2：Level-1 机械快轨 0 Token 判定
# ---------------------------------------------------------------------------


def test_gate2_time_geofence_heartrate_all_zero_llm_calls() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_geo",
                title="回到上海办公室且非深度专注时提示签署回购协议",
                conditions=(
                    GeofenceCondition(
                        fence_id="shanghai_office",
                        center_lat=SHANGHAI_OFFICE_LAT,
                        center_lon=SHANGHAI_OFFICE_LON,
                        radius_m=150.0,
                        require_dwell_seconds=60,
                    ),
                ),
            ),
            ConditionalTaskRecord(
                task_id="t_hr",
                title="连续 3 天夜间心率超 95bpm 启动心内科预约建档",
                conditions=(
                    HeartRateCondition(
                        threshold_bpm=95,
                        window="night",
                        consecutive_days_required=3,
                    ),
                ),
            ),
        ]
    )

    promoted = scheduler.advance_level1(
        _ctx(
            lat=SHANGHAI_OFFICE_LAT + 0.0002,
            lon=SHANGHAI_OFFICE_LON + 0.0002,
            dwelled_seconds=120,
            heart_rate_bpm=101,
            heart_rate_window="night",
            consecutive_night_breach_days=3,
        )
    )

    assert set(promoted) == {"t_geo", "t_hr"}
    assert scheduler.state_of("t_geo") is ConditionalTaskState.READY
    assert scheduler.state_of("t_hr") is ConditionalTaskState.READY

    # 逐项核对：每个机械判定的 llm_calls 都是 0
    for task_id in ("t_geo", "t_hr"):
        task = scheduler._tasks[task_id]
        outcomes = scheduler.evaluate_level1(task, _ctx(heart_rate_bpm=101))
        assert all(o.llm_calls == 0 for o in outcomes)
        assert all(o.level == EvaluationLevel.LEVEL1_MECHANICAL for o in outcomes)


def test_gate2_level1_never_promotes_semantic_task() -> None:
    """语义条件不得被机械快轨误判为就绪。"""
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_semantic",
                title="当诉讼对方实控人出现股权变更时提醒",
                conditions=(
                    SemanticCondition(
                        predicate="诉讼对方实控人发生股权变更",
                        relevance_keywords=("股权变更", "实控人"),
                        estimated_llm_tokens=400,
                    ),
                ),
            )
        ]
    )

    assert scheduler.advance_level1(_ctx()) == ()
    assert scheduler.state_of("t_semantic") is ConditionalTaskState.DORMANT


def test_gate2_level1_sub_millisecond_for_200_tasks() -> None:
    """工单要求 1ms 内纯 Python 判定。200 项混合条件实测应在亚毫秒~毫秒级。"""
    tasks: list[ConditionalTaskRecord] = []
    for i in range(200):
        if i % 3 == 0:
            cond: object = TimeReachedCondition(due_at=NOW - timedelta(minutes=i))
        elif i % 3 == 1:
            cond = HeartRateCondition(threshold_bpm=95, window="night", consecutive_days_required=3)
        else:
            cond = GeofenceCondition(
                fence_id=f"fence_{i}",
                center_lat=SHANGHAI_OFFICE_LAT,
                center_lon=SHANGHAI_OFFICE_LON,
                radius_m=150.0,
            )
        tasks.append(
            ConditionalTaskRecord(task_id=f"t_{i:03d}", title=f"条件任务 {i}", conditions=(cond,))  # type: ignore[arg-type]
        )

    scheduler = TwoTrackConditionalScheduler(tasks)
    context = _ctx(
        lat=SHANGHAI_OFFICE_LAT,
        lon=SHANGHAI_OFFICE_LON,
        heart_rate_bpm=101,
        heart_rate_window="night",
        consecutive_night_breach_days=3,
    )

    scheduler.advance_level1(context)  # 预热
    started = time.perf_counter()
    promoted = scheduler.advance_level1(context)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert len(promoted) == 0  # 第二轮无新增
    assert elapsed_ms <= 1.0, f"200 项 Level-1 判定耗时 {elapsed_ms:.3f}ms，超过 1ms"


def test_gate2_heart_rate_needs_three_consecutive_days() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_hr",
                title="连续 3 天夜间心率超阈启动建档",
                conditions=(
                    HeartRateCondition(
                        threshold_bpm=95, window="night", consecutive_days_required=3
                    ),
                ),
            )
        ]
    )

    for days in (1, 2):
        assert scheduler.advance_level1(
            _ctx(
                heart_rate_bpm=101,
                heart_rate_window="night",
                consecutive_night_breach_days=days,
            )
        ) == ()
    assert scheduler.advance_level1(
        _ctx(heart_rate_bpm=101, heart_rate_window="night", consecutive_night_breach_days=3)
    ) == ("t_hr",)


def test_gate2_geofence_rejects_far_and_short_dwell() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_geo",
                title="回到上海办公室时提示",
                conditions=(
                    GeofenceCondition(
                        fence_id="shanghai_office",
                        center_lat=SHANGHAI_OFFICE_LAT,
                        center_lon=SHANGHAI_OFFICE_LON,
                        radius_m=150.0,
                        require_dwell_seconds=60,
                    ),
                ),
            )
        ]
    )
    # 在北京
    assert scheduler.advance_level1(_ctx(lat=39.9042, lon=116.4074, dwelled_seconds=600)) == ()
    # 在围栏内但停留不足
    assert (
        scheduler.advance_level1(
            _ctx(lat=SHANGHAI_OFFICE_LAT, lon=SHANGHAI_OFFICE_LON, dwelled_seconds=10)
        )
        == ()
    )
    # 无定位
    assert scheduler.advance_level1(_ctx(dwelled_seconds=600)) == ()


# ---------------------------------------------------------------------------
# 门禁 3：Level-2 机会式捎带
# ---------------------------------------------------------------------------


def test_gate3_no_evaluation_without_user_initiated_wake() -> None:
    """用户没主动唤醒时，绝不为了评估休眠任务而调用模型。"""
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_semantic",
                title="当诉讼对方实控人出现股权变更时提醒",
                conditions=(
                    SemanticCondition(
                        predicate="诉讼对方实控人发生股权变更",
                        relevance_keywords=("股权变更",),
                        estimated_llm_tokens=400,
                    ),
                ),
            )
        ]
    )

    report = scheduler.evaluate_level2_piggyback(
        _ctx(active_scene_keywords=("股权变更",), user_initiated=False),
        semantic_judge=lambda predicate, kw: True,
    )

    assert report.llm_calls == 0
    assert report.llm_tokens == 0
    assert report.autonomous_wakes_for_evaluation == 0
    assert scheduler.state_of("t_semantic") is ConditionalTaskState.DORMANT


def test_gate3_piggyback_promotes_only_when_scene_relevant() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_equity_change",
                title="当诉讼对方实控人出现股权变更时提醒",
                conditions=(
                    SemanticCondition(
                        predicate="诉讼对方实控人发生股权变更",
                        relevance_keywords=("股权变更", "实控人"),
                        estimated_llm_tokens=400,
                    ),
                ),
            ),
            ConditionalTaskRecord(
                task_id="t_unrelated",
                title="与当前场景无关的语义任务",
                conditions=(
                    SemanticCondition(
                        predicate="某个完全无关的语义判断",
                        relevance_keywords=("无关关键词",),
                        estimated_llm_tokens=400,
                    ),
                ),
            ),
        ]
    )

    report = scheduler.evaluate_level2_piggyback(
        _ctx(active_scene_keywords=("股权变更", "工商变更公告"), user_initiated=True),
        semantic_judge=lambda predicate, kw: True,
    )

    assert report.evaluated_task_ids == ("t_equity_change",)
    assert "t_unrelated" in report.skipped_task_ids
    # 只对相关的 1 项付出模型开销
    assert report.llm_calls == 1
    assert report.llm_tokens == 400
    assert report.autonomous_wakes_for_evaluation == 0


def test_gate3_judge_returning_false_keeps_task_dormant() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_semantic",
                title="股权变更提醒",
                conditions=(
                    SemanticCondition(
                        predicate="诉讼对方实控人发生股权变更",
                        relevance_keywords=("股权变更",),
                        estimated_llm_tokens=400,
                    ),
                ),
            )
        ]
    )

    report = scheduler.evaluate_level2_piggyback(
        _ctx(active_scene_keywords=("股权变更",), user_initiated=True),
        semantic_judge=lambda predicate, kw: False,
    )

    assert report.llm_calls == 1  # 确实顺路问了一次
    assert scheduler.state_of("t_semantic") is ConditionalTaskState.DORMANT
    assert report.autonomous_wakes_for_evaluation == 0


def test_gate3_mixed_task_needs_both_mechanical_and_semantic() -> None:
    """and 组合：语义满足但机械条件未满足时不得就绪。"""
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_mixed",
                title="回到办公室且处于非深度专注状态时提示签署回购协议",
                conditions=(
                    GeofenceCondition(
                        fence_id="shanghai_office",
                        center_lat=SHANGHAI_OFFICE_LAT,
                        center_lon=SHANGHAI_OFFICE_LON,
                        radius_m=150.0,
                    ),
                    SemanticCondition(
                        predicate="当前处于非深度专注状态",
                        relevance_keywords=("专注",),
                        estimated_llm_tokens=300,
                    ),
                ),
                combine="and",
            )
        ]
    )

    # 不在办公室
    away = scheduler.evaluate_level2_piggyback(
        _ctx(lat=39.9042, lon=116.4074, active_scene_keywords=("专注",), user_initiated=True),
        semantic_judge=lambda predicate, kw: True,
    )
    assert away.evaluated_task_ids == ()
    assert scheduler.state_of("t_mixed") is ConditionalTaskState.DORMANT

    # 在办公室
    office = scheduler.evaluate_level2_piggyback(
        _ctx(
            lat=SHANGHAI_OFFICE_LAT,
            lon=SHANGHAI_OFFICE_LON,
            active_scene_keywords=("专注",),
            user_initiated=True,
        ),
        semantic_judge=lambda predicate, kw: True,
    )
    assert office.evaluated_task_ids == ("t_mixed",)
    assert scheduler.state_of("t_mixed") is ConditionalTaskState.READY


def test_gate3_no_relevant_scene_costs_zero() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_semantic",
                title="股权变更提醒",
                conditions=(
                    SemanticCondition(
                        predicate="x", relevance_keywords=("股权变更",), estimated_llm_tokens=400
                    ),
                ),
            )
        ]
    )
    report = scheduler.evaluate_level2_piggyback(
        _ctx(active_scene_keywords=("午餐",), user_initiated=True),
        semantic_judge=lambda predicate, kw: True,
    )
    assert report.llm_calls == 0
    assert report.evaluated_task_ids == ()


# ---------------------------------------------------------------------------
# 门禁 4：状态机非法跃迁 100% 拦截
# ---------------------------------------------------------------------------


def test_gate4_dormant_cannot_jump_straight_to_running() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [_time_task("t_sleeping", due=NOW + timedelta(days=30))]
    )

    with pytest.raises(IllegalStateTransitionError) as excinfo:
        scheduler.start("t_sleeping")

    err = excinfo.value
    assert err.code is ErrorCode.INVALID_ARGUMENT
    assert err.context["from_state"] == "dormant"
    assert err.context["to_state"] == "running"
    assert err.context["task_id"] == "t_sleeping"
    assert scheduler.state_of("t_sleeping") is ConditionalTaskState.DORMANT


def test_gate4_happy_path_dormant_ready_running_completed() -> None:
    scheduler = TwoTrackConditionalScheduler([_time_task("t_ok", due=NOW)])
    scheduler.advance_level1(_ctx())

    assert scheduler.state_of("t_ok") is ConditionalTaskState.READY
    scheduler.start("t_ok")
    assert scheduler.state_of("t_ok") is ConditionalTaskState.RUNNING
    scheduler.complete("t_ok")
    assert scheduler.state_of("t_ok") is ConditionalTaskState.COMPLETED


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        (ConditionalTaskState.DORMANT, ConditionalTaskState.RUNNING),
        (ConditionalTaskState.DORMANT, ConditionalTaskState.COMPLETED),
        (ConditionalTaskState.COMPLETED, ConditionalTaskState.RUNNING),
        (ConditionalTaskState.COMPLETED, ConditionalTaskState.READY),
        (ConditionalTaskState.EXPIRED, ConditionalTaskState.READY),
        (ConditionalTaskState.CANCELLED, ConditionalTaskState.RUNNING),
        (ConditionalTaskState.READY, ConditionalTaskState.COMPLETED),
    ],
)
def test_gate4_illegal_transitions_all_raise(
    from_state: ConditionalTaskState, to_state: ConditionalTaskState
) -> None:
    scheduler = TwoTrackConditionalScheduler([_time_task("t", due=NOW)])
    # 构造起始状态（经由合法路径或注册默认）
    if from_state is ConditionalTaskState.READY:
        scheduler.transition("t", ConditionalTaskState.READY)
    elif from_state is ConditionalTaskState.COMPLETED:
        scheduler.transition("t", ConditionalTaskState.READY)
        scheduler.transition("t", ConditionalTaskState.RUNNING)
        scheduler.transition("t", ConditionalTaskState.COMPLETED)
    elif from_state is ConditionalTaskState.EXPIRED:
        scheduler.transition("t", ConditionalTaskState.EXPIRED)
    elif from_state is ConditionalTaskState.CANCELLED:
        scheduler.transition("t", ConditionalTaskState.CANCELLED)

    with pytest.raises(IllegalStateTransitionError):
        scheduler.transition("t", to_state)


def test_gate4_expired_task_is_not_promotable() -> None:
    scheduler = TwoTrackConditionalScheduler(
        [
            ConditionalTaskRecord(
                task_id="t_expired",
                title="已过期的条件任务",
                conditions=(TimeReachedCondition(due_at=NOW - timedelta(days=1)),),
                expires_at=NOW - timedelta(hours=1),
            )
        ]
    )
    scheduler.advance_level1(_ctx())

    assert scheduler.state_of("t_expired") is ConditionalTaskState.EXPIRED
    assert scheduler.assemble_ready_manifest() == ()


def test_gate4_unknown_task_raises_keyerror() -> None:
    scheduler = TwoTrackConditionalScheduler()
    with pytest.raises(KeyError):
        scheduler.state_of("nope")


# ---------------------------------------------------------------------------
# 冻结契约兼容
# ---------------------------------------------------------------------------


def test_dormant_maps_onto_frozen_task_state_without_new_enum_value() -> None:
    """DORMANT 是调度器本地视图，持久化时投影到冻结 TaskState.WAITING_TIME。"""
    assert to_frozen_task_state(ConditionalTaskState.DORMANT) is TaskState.WAITING_TIME
    assert to_frozen_task_state(ConditionalTaskState.READY) is TaskState.READY
    assert to_frozen_task_state(ConditionalTaskState.RUNNING) is TaskState.RUNNING
    assert to_frozen_task_state(ConditionalTaskState.COMPLETED) is TaskState.COMPLETED
    # 冻结枚举本身没有被改动
    assert "dormant" not in {s.value for s in TaskState}


def test_duplicate_task_id_rejected() -> None:
    scheduler = TwoTrackConditionalScheduler([_time_task("dup", due=NOW)])
    with pytest.raises(ValueError, match="duplicate task_id"):
        scheduler.register(_time_task("dup", due=NOW))
