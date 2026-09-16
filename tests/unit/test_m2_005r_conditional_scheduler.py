"""M2-005R 验收测试：条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

工单：``arena/agent-dispatch-m2-005r``
实现：``src/aios_core/scheduler/conditional_engine.py``

实战情境（严禁低幼化样例）
--------------------------------------------------------------------------
用户是长期高压的**创业企业法务总监**，日程挂载 **200 项跨周期条件任务**：

* 「当诉讼对方实控人出现股权变更时提醒」（语义条件）
* 「当连续 3 天晚间心率超过 95bpm 时启动心内科预约建档」（生理阈值条件）
* 「在回到上海办公室且处于非深度专注状态时提示签署对赌回购协议」（地理围栏 + 语义条件）
* 各类诉讼送达、举证期限、工商变更公示等**绝对时间**到期任务

四大硬门禁 ↔ 用例
--------------------------------------------------------------------------
1. DORMANT 物理隐形、Token 严格为 0 —— ``test_gate1_*``（含守卫"长牙"负向对照）
2. Level-1 机械快轨 0 Token / ≤1ms —— ``test_gate2_*``
3. Level-2 机会式捎带（绝不自主唤醒）—— ``test_gate3_*``
4. 状态机非法跃迁 100% 拦截 —— ``test_gate4_*``（含非法跃迁矩阵全覆盖）
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from aios_core.scheduler.conditional_engine import (
    LEVEL1_MECHANICAL_BUDGET_MS,
    BoardAssembly,
    Condition,
    ConditionKind,
    ConditionalTask,
    ConditionalTaskScheduler,
    DormantInvisibilityGuard,
    DormantVisibilityLeakError,
    IllegalStateTransitionError,
    Level1FastTrack,
    MechanicalSignal,
    GeoPosition,
    OpportunisticPiggyback,
    TaskState,
    TaskStateMachine,
    VitalSnapshot,
    WakeContext,
)

# ---------------------------------------------------------------------------
# 时间基线与场景常量
# ---------------------------------------------------------------------------

T_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
T_TODAY_START = T_NOW - timedelta(hours=12)
TASK_TOTAL = 200

#: 任务池构成（合计 200）：时间 60 / 地理 40 / 生理 40 / 语义 30 / 混合（地理+语义）30
TIME_TASKS = 60
GEO_TASKS = 40
VITAL_TASKS = 40
SEMANTIC_TASKS = 30
MIXED_TASKS = 30

SHANGHAI_OFFICE = "shanghai_office"
LITIGATION_SCENE = "litigation_counterparty_equity_change"
CONTRACT_SIGNING_SCENE = "contract_signing"
CARDIAC_TRIAGE_SCENE = "cardiac_triage"

VITAL_METRIC = "evening_heart_rate_bpm"
VITAL_THRESHOLD = 95.0        # 心内科预约建档阈值（工单口径）
ESCALATION_THRESHOLD = 105.0  # 急诊绿色通道阈值（更高一档，同样需要连续 3 天）
VITAL_DAYS = 3
VITAL_HIGH = 103.0            # 近期实测晚间心率（>95 但不 >105）
VITAL_LOW = 83.0


def _time_task(index: int, *, expired: bool) -> ConditionalTask:
    """绝对时间任务：诉讼送达 / 举证期限 / 工商公示到期。"""
    offset = timedelta(hours=2 if expired else 72)
    deadline = T_NOW - offset if expired else T_NOW + offset
    return ConditionalTask(
        task_id=f"task_time_{index:03d}",
        title=f"举证期限届满提醒 #{index:03d}（诉讼送达回证归档）",
        priority=1 if expired else 2,
        conditions=(
            Condition(
                kind=ConditionKind.ABSOLUTE_TIME,
                summary=f"举证期限 {deadline.isoformat()} 到期",
                deadline=deadline,
            ),
        ),
    )


def _geo_task(index: int, *, inside: bool) -> ConditionalTask:
    return ConditionalTask(
        task_id=f"task_geo_{index:03d}",
        title=f"到达上海办公室时提取纸质卷宗 #{index:03d}",
        priority=3,
        conditions=(
            Condition(
                kind=ConditionKind.GEO_FENCE,
                summary="位于上海办公室围栏内",
                place_key=SHANGHAI_OFFICE if inside else "shenzhen_hq",
            ),
        ),
    )


def _vital_task(index: int, *, satisfied: bool) -> ConditionalTask:
    """生理阈值任务：一档是心内科预约建档（>95），另一档是急诊绿色通道（>105）。

    同一份实测心率序列（近 3 天 103bpm）只会命中较低那一档——这正是"阈值分档"
    在真实医疗场景里的意义，也保证 40 条里只有 10 条会真正成熟。
    """
    threshold = VITAL_THRESHOLD if satisfied else ESCALATION_THRESHOLD
    label = "心内科预约建档" if satisfied else "急诊绿色通道评估"
    return ConditionalTask(
        task_id=f"task_vital_{index:03d}",
        title=f"连续 {VITAL_DAYS} 天晚间心率超 {threshold:.0f}bpm 则启动{label} #{index:03d}",
        priority=1,
        conditions=(
            Condition(
                kind=ConditionKind.VITAL_THRESHOLD,
                summary="晚间心率连续超标",
                metric=VITAL_METRIC,
                comparator=">",
                threshold=threshold,
                consecutive_days=VITAL_DAYS,
            ),
        ),
    )


def _semantic_task(index: int) -> ConditionalTask:
    return ConditionalTask(
        task_id=f"task_semantic_{index:03d}",
        title=f"诉讼对方实控人股权变更时提醒（对手方主体 #{index:03d}）",
        priority=2,
        conditions=(
            Condition(
                kind=ConditionKind.SEMANTIC_SCENE,
                summary="对手方实控人出现股权变更语义信号",
                scene_tags=(LITIGATION_SCENE,),
            ),
        ),
    )


def _mixed_task(index: int) -> ConditionalTask:
    """地理围栏 + 语义场景双条件：回到上海办公室且非深度专注才提示签署对赌回购协议。"""
    return ConditionalTask(
        task_id=f"task_mixed_{index:03d}",
        title=f"签署对赌回购协议的窗口提示 #{index:03d}",
        priority=1,
        conditions=(
            Condition(
                kind=ConditionKind.GEO_FENCE,
                summary="位于上海办公室围栏内",
                place_key=SHANGHAI_OFFICE,
            ),
            Condition(
                kind=ConditionKind.SEMANTIC_SCENE,
                summary="处于合同签署场景且非深度专注",
                scene_tags=(CONTRACT_SIGNING_SCENE,),
                requires_focus_free=True,
            ),
        ),
    )


def _build_200_tasks() -> tuple[ConditionalTask, ...]:
    """200 项跨周期条件任务：60 时间（30 已到期）+ 40 地理（12 命中）+ 40 生理（10 命中）
    + 30 语义 + 30 混合。"""
    tasks: list[ConditionalTask] = []
    for index in range(TIME_TASKS):
        tasks.append(_time_task(index, expired=index < 30))
    for index in range(GEO_TASKS):
        tasks.append(_geo_task(index, inside=index < 12))
    for index in range(VITAL_TASKS):
        tasks.append(_vital_task(index, satisfied=index < 10))
    for index in range(SEMANTIC_TASKS):
        tasks.append(_semantic_task(index))
    for index in range(MIXED_TASKS):
        tasks.append(_mixed_task(index))
    assert len(tasks) == TASK_TOTAL, f"任务池必须恰好 {TASK_TOTAL} 项"
    return tuple(tasks)


def _vital_snapshot(*, satisfied_evenings: int, deep_focus: bool = False) -> VitalSnapshot:
    """构造晚间心率历史：前 satisfied_evenings 天超标，其余正常。"""
    window = 7
    history = tuple(
        VITAL_HIGH if i >= window - satisfied_evenings else VITAL_LOW for i in range(window)
    )
    return VitalSnapshot(
        captured_at=T_NOW,
        heart_rate_bpm=history[-1],
        hrv_ms=42.0,
        deep_focus=deep_focus,
        metric_history={VITAL_METRIC: history},
    )


def _mechanical_signal() -> MechanicalSignal:
    return MechanicalSignal(
        now=T_NOW,
        position=GeoPosition(
            place_key=SHANGHAI_OFFICE, inside_fence=True, captured_at=T_NOW
        ),
        vitals=_vital_snapshot(satisfied_evenings=VITAL_DAYS + 2),
    )


@pytest.fixture
def scheduler() -> ConditionalTaskScheduler:
    """装载 200 项真实条件任务的调度引擎。"""
    engine = ConditionalTaskScheduler()
    assert engine.register_tasks(_build_200_tasks()) == TASK_TOTAL
    assert engine.dormant_count == TASK_TOTAL, "初始态：全部任务休眠，不看板、不消耗 Token"
    return engine


@pytest.fixture
def machine() -> TaskStateMachine:
    return TaskStateMachine()


# ===========================================================================
# 硬门禁 1：DORMANT 物理隐形 + Token 严格为 0
# ===========================================================================


def test_gate1_all_200_tasks_start_dormant_and_are_frozen_out(
    scheduler: ConditionalTaskScheduler,
) -> None:
    board = scheduler.assemble_board(at=T_NOW)

    assert scheduler.dormant_count == TASK_TOTAL
    assert board.entry_count == 0, "没有任务成熟时，看板装配结果必须为空"
    assert board.frozen_out == TASK_TOTAL
    assert board.dormant_token_cost == 0
    assert board.prompt_text == ""
    assert board.prompt_tokens == 0


def test_gate1_dormant_tasks_contribute_exactly_zero_tokens(
    scheduler: ConditionalTaskScheduler,
) -> None:
    audit = scheduler.dormant_prompt_token_audit()

    assert audit["dormant_tokens_in_board"] == 0, "休眠任务在看板中的 Token 贡献必须为 0"
    # 反事实对照：若把这些休眠任务粗暴灌进 Prompt，会烧掉可观的 Token——
    # 这正是本引擎要避免的浪费（证明"0"不是因为没有内容，而是因为隐形机制）。
    assert audit["dormant_tokens_if_naively_prompted"] > 500
    assert audit["dormant_frozen_out"] == TASK_TOTAL


def test_gate1_dormant_titles_never_leak_into_any_prompt(
    scheduler: ConditionalTaskScheduler,
) -> None:
    fast_track_report = scheduler.tick(_mechanical_signal())
    assert fast_track_report.ready_task_ids, "场景前提：快轨必须点亮部分任务"

    board = scheduler.assemble_board(at=T_NOW)
    dormant = scheduler.tasks_in_state(TaskState.DORMANT)
    assert dormant, "场景前提：仍有任务休眠"

    # 组装后机械核对：休眠任务的标题一个都不许出现在 Prompt 里。
    DormantInvisibilityGuard.assert_no_dormant_leak(board, dormant)
    for task in dormant:
        assert task.title not in board.prompt_text
    for entry in board.entries:
        assert entry.state in (TaskState.READY, TaskState.RUNNING)
        assert scheduler.task(entry.task_id).state is not TaskState.DORMANT

    # 常规会话入口（full_board_prompt）与看板同源，同样不含休眠痕迹。
    conversation_prompt = scheduler.full_board_prompt(at=T_NOW)
    assert conversation_prompt == board.prompt_text
    assert all(task.title not in conversation_prompt for task in dormant)


def test_gate1_invisibility_guard_has_teeth_negative_control(
    scheduler: ConditionalTaskScheduler,
) -> None:
    """守卫必须真的能抓漏：人为把休眠标题塞进 Prompt，必须立刻报错。"""
    dormant = scheduler.tasks_in_state(TaskState.DORMANT)
    leaked = BoardAssembly(
        entries=(),
        frozen_out=len(dormant),
        dormant_token_cost=17,
        dormant_titles_included=(dormant[0].task_id,),
        prompt_text=f"[DORMANT] {dormant[0].title}",
        prompt_tokens=17,
        assembled_at=T_NOW,
    )
    with pytest.raises(DormantVisibilityLeakError) as excinfo:
        DormantInvisibilityGuard.assert_no_dormant_leak(leaked, dormant)
    assert excinfo.value.context["phase"] == "board_assembly"
    assert excinfo.value.context["leaked_count"] >= 1


def test_gate1_board_only_carries_mature_tasks_in_priority_order(
    scheduler: ConditionalTaskScheduler,
) -> None:
    scheduler.tick(_mechanical_signal())
    board = scheduler.assemble_board(at=T_NOW)

    assert board.entry_count == len(scheduler.tasks_in_state(TaskState.READY))
    assert board.entry_count + board.frozen_out == TASK_TOTAL
    priorities = [entry.priority for entry in board.entries]
    assert priorities == sorted(priorities, reverse=True), "看板必须按优先级降序（高优先级先呈现）"
    assert board.prompt_tokens > 0, "有成熟任务时看板 Prompt 才有内容（休眠任务不贡献）"
    assert board.dormant_token_cost == 0


# ===========================================================================
# 硬门禁 2：Level-1 机械快轨 —— 0 Token、1ms 内纯 Python 判定
# ===========================================================================


def test_gate2_mechanical_fast_track_costs_zero_tokens_and_zero_llm_calls(
    scheduler: ConditionalTaskScheduler,
) -> None:
    report = scheduler.tick(_mechanical_signal())

    assert report.llm_calls == 0, "机械快轨严禁触发大模型"
    assert report.prompt_tokens == 0, "机械快轨严禁组装 Prompt"
    assert report.autonomous_wakes == 0
    assert scheduler.llm_calls == 0 and scheduler.autonomous_wakes == 0
    assert report.evaluated == TIME_TASKS + GEO_TASKS + VITAL_TASKS + MIXED_TASKS


def test_gate2_every_judgement_finishes_inside_the_1ms_budget(
    scheduler: ConditionalTaskScheduler,
) -> None:
    report = scheduler.tick(_mechanical_signal())

    assert report.judgement_times_ms, "必须留下逐条判定耗时证据"
    assert report.p95_judgement_ms <= LEVEL1_MECHANICAL_BUDGET_MS, (
        f"机械判定 p95={report.p95_judgement_ms:.4f}ms 超出 1ms 预算"
    )
    assert report.max_judgement_ms <= LEVEL1_MECHANICAL_BUDGET_MS, (
        f"机械判定最坏 {report.max_judgement_ms:.4f}ms 超出 1ms 预算"
    )
    assert report.within_mechanical_budget is True

    # 单独压一遍纯判定热路径（不含状态跃迁开销），确保 1ms 预算有巨大余量。
    fast_track = Level1FastTrack()
    signal = _mechanical_signal()
    tasks = _build_200_tasks()
    started = time.perf_counter()
    for _ in range(20):
        for task in tasks:
            for condition in task.mechanical_conditions:
                fast_track.condition_satisfied(condition, signal)
    per_task_ms = (time.perf_counter() - started) * 1000.0 / (20 * len(tasks))
    print(
        f"[M2-005R 机械快轨] p95={report.p95_judgement_ms * 1000:.2f}µs "
        f"最坏={report.max_judgement_ms * 1000:.2f}µs 单任务均值={per_task_ms * 1000:.2f}µs "
        f"（预算 {LEVEL1_MECHANICAL_BUDGET_MS}ms）"
    )
    assert per_task_ms < LEVEL1_MECHANICAL_BUDGET_MS


def test_gate2_mechanical_conditions_jump_straight_to_ready(
    scheduler: ConditionalTaskScheduler,
) -> None:
    report = scheduler.tick(_mechanical_signal())

    # 绝对时间：30 条已到期 -> READY；另 30 条未到期 -> 继续休眠
    expired = [t for t in report.ready_task_ids if t.startswith("task_time_")]
    assert len(expired) == 30
    # 地理围栏：12 条命中
    assert len([t for t in report.ready_task_ids if t.startswith("task_geo_")]) == 12
    # 生理阈值：10 条连续 3 天超标命中
    assert len([t for t in report.ready_task_ids if t.startswith("task_vital_")]) == 10
    # 混合任务：机械前提满足但仍需语义确认 -> 保持休眠（不给 LLM 白送 Token）
    assert len(report.blocked_by_semantics) == MIXED_TASKS
    assert scheduler.dormant_count == TASK_TOTAL - len(report.ready_task_ids)

    for task_id in report.ready_task_ids:
        task = scheduler.task(task_id)
        assert task is not None
        assert task.state is TaskState.READY, "机械快轨必须直接跃迁至 READY"
        assert task.ready_reason
        assert task.started_at is None, "READY 不等于 RUNNING：不得越权直接开跑"

    # 未命中的任务一条都不能被点亮
    unmet_ids = {line.split(":")[0] for line in report.unmet_mechanical}
    assert "task_time_030" in unmet_ids  # 未到期的绝对时间任务
    assert "task_geo_012" in unmet_ids  # 围栏不匹配
    assert "task_vital_010" in unmet_ids  # 阈值更高一档：连续命中 0/3 天


def test_gate2_vital_threshold_requires_consecutive_days(
    scheduler: ConditionalTaskScheduler,
) -> None:
    """连续 3 天是硬条件：只有 2 天超标必须继续休眠。"""
    only_two_days = MechanicalSignal(
        now=T_NOW,
        position=None,
        vitals=_vital_snapshot(satisfied_evenings=VITAL_DAYS - 1),
    )
    engine = ConditionalTaskScheduler()
    engine.register_task(_vital_task(0, satisfied=True))
    report = engine.tick(only_two_days)

    assert report.ready_task_ids == ()
    assert engine.task("task_vital_000").state is TaskState.DORMANT
    assert "连续命中 2/3 天" in report.unmet_mechanical[0]


def test_gate2_evaluation_before_deadline_is_a_pure_python_decision(
    scheduler: ConditionalTaskScheduler,
) -> None:
    """把时钟拨到所有截止时间之前：全部继续休眠，且依旧 0 Token。"""
    early = MechanicalSignal(
        now=T_NOW - timedelta(days=30),
        position=None,  # 无定位快照：地理围栏一律不命中（不猜位置）
        vitals=_vital_snapshot(satisfied_evenings=0),
    )
    report = scheduler.tick(early)

    assert report.ready_task_ids == ()
    assert report.llm_calls == 0 and report.prompt_tokens == 0
    assert scheduler.dormant_count == TASK_TOTAL


# ===========================================================================
# 硬门禁 3：Level-2 机会式捎带（绝不自主唤醒）
# ===========================================================================


def test_gate3_no_evaluation_without_an_explicit_user_wake(
    scheduler: ConditionalTaskScheduler,
) -> None:
    report = scheduler.piggyback(WakeContext(captured_at=T_NOW, user_resumed_ai=False))

    assert report.triggered_by_user is False
    assert report.evaluated_task_ids == ()
    assert report.llm_calls == 0, "没有用户主动唤醒时，一次大模型调用都不许发生"
    assert scheduler.llm_calls == 0
    assert scheduler.autonomous_wakes == 0
    assert scheduler.dormant_count == TASK_TOTAL


def test_gate3_user_wake_without_matching_scene_costs_nothing(
    scheduler: ConditionalTaskScheduler,
) -> None:
    """用户唤醒了，但聊的是别的事（无关场景）：依然 0 调用、0 评估。"""
    context = WakeContext(
        captured_at=T_NOW,
        user_resumed_ai=True,
        scene_tags=("unrelated_ops_review",),
        position=GeoPosition(place_key=SHANGHAI_OFFICE, inside_fence=True, captured_at=T_NOW),
        vitals=_vital_snapshot(satisfied_evenings=0),
    )
    report = scheduler.piggyback(context)

    assert report.triggered_by_user is True
    assert report.evaluated_task_ids == ()
    assert report.llm_calls == 0
    assert scheduler.dormant_count == TASK_TOTAL


def test_gate3_matching_scene_batches_many_tasks_into_one_single_call(
    scheduler: ConditionalTaskScheduler,
) -> None:
    """30 条语义任务命中同一场景：整批只花 1 次大模型调用（不是每条一次）。"""
    context = WakeContext(
        captured_at=T_NOW,
        user_resumed_ai=True,
        scene_tags=(LITIGATION_SCENE,),
        session_id="session_0916_afternoon",
        position=GeoPosition(place_key=SHANGHAI_OFFICE, inside_fence=True, captured_at=T_NOW),
        vitals=_vital_snapshot(satisfied_evenings=0),
    )
    report = scheduler.piggyback(context)

    assert report.triggered_by_user is True
    assert len(report.evaluated_task_ids) == SEMANTIC_TASKS
    assert report.llm_calls == 1, "机会式捎带必须批量共享单次调用"
    assert scheduler.llm_calls == 1
    assert scheduler.autonomous_wakes == 0, "绝不为休眠任务自主唤醒大模型"
    for task_id in report.ready_task_ids:
        task = scheduler.task(task_id)
        assert task is not None and task.state is TaskState.READY
        assert "语义场景捎带命中" in (task.ready_reason or "")


def test_gate3_piggyback_respects_mechanical_preconditions_of_mixed_tasks(
    scheduler: ConditionalTaskScheduler,
) -> None:
    """混合任务（地理+语义）在捎带时也必须两条腿都站住。"""
    # 场景命中但人不在上海办公室 -> 不得点亮
    away = WakeContext(
        captured_at=T_NOW,
        user_resumed_ai=True,
        scene_tags=(CONTRACT_SIGNING_SCENE,),
        position=GeoPosition(place_key="shenzhen_hq", inside_fence=True, captured_at=T_NOW),
        vitals=_vital_snapshot(satisfied_evenings=0, deep_focus=False),
    )
    report_away = scheduler.piggyback(away)
    assert report_away.evaluated_task_ids == ()
    assert scheduler.tasks_in_state(TaskState.READY) == ()

    # 人在上海办公室但处于深度专注 -> 依然不得打扰
    focused = WakeContext(
        captured_at=T_NOW,
        user_resumed_ai=True,
        scene_tags=(CONTRACT_SIGNING_SCENE,),
        position=GeoPosition(place_key=SHANGHAI_OFFICE, inside_fence=True, captured_at=T_NOW),
        vitals=_vital_snapshot(satisfied_evenings=0, deep_focus=True),
    )
    report_focused = scheduler.piggyback(focused)
    assert report_focused.evaluated_task_ids == ()

    # 回到上海办公室 + 非深度专注 + 签署场景 -> 全部 30 条混合任务一次捎带点亮
    ready_context = WakeContext(
        captured_at=T_NOW,
        user_resumed_ai=True,
        scene_tags=(CONTRACT_SIGNING_SCENE,),
        position=GeoPosition(place_key=SHANGHAI_OFFICE, inside_fence=True, captured_at=T_NOW),
        vitals=_vital_snapshot(satisfied_evenings=0, deep_focus=False),
    )
    report_ready = scheduler.piggyback(ready_context)
    assert len(report_ready.evaluated_task_ids) == MIXED_TASKS
    assert report_ready.llm_calls == 1, "两次导航场景合并评估，仍只花 1 次调用"


def test_gate3_piggyback_reports_are_auditable(
    scheduler: ConditionalTaskScheduler,
) -> None:
    calls: list[tuple[str, ...]] = []
    engine = ConditionalTaskScheduler(
        piggyback=OpportunisticPiggyback(llm_invoker=lambda ids, scene: calls.append(tuple(ids)))
    )
    engine.register_tasks(_build_200_tasks())
    context = WakeContext(
        captured_at=T_NOW,
        user_resumed_ai=True,
        scene_tags=(LITIGATION_SCENE, CARDIAC_TRIAGE_SCENE),
        position=GeoPosition(place_key=SHANGHAI_OFFICE, inside_fence=True, captured_at=T_NOW),
        vitals=_vital_snapshot(satisfied_evenings=0),
    )
    report = engine.piggyback(context)

    assert len(calls) == 1, "批量语义判定只允许一次真实调用"
    assert calls[0] == report.evaluated_task_ids
    assert report.autonomous_wakes == 0
    assert report.elapsed_ms >= 0.0
    print(
        f"[M2-005R 机会式捎带] 批量任务={len(report.evaluated_task_ids)} "
        f"大模型调用={report.llm_calls} 自主唤醒={report.autonomous_wakes}"
    )


# ===========================================================================
# 硬门禁 4：状态机非法跃迁 100% 拦截
# ===========================================================================


def _task_in_state(state: TaskState) -> ConditionalTask:
    task = ConditionalTask(
        task_id="task_probe",
        title="状态机探针任务",
        conditions=(
            Condition(
                kind=ConditionKind.ABSOLUTE_TIME,
                summary="探针到期",
                deadline=T_NOW - timedelta(minutes=1),
            ),
        ),
        state=state,
    )
    return task


def test_gate4_dormant_task_cannot_be_started_directly(
    machine: TaskStateMachine, scheduler: ConditionalTaskScheduler
) -> None:
    dormant = _task_in_state(TaskState.DORMANT)
    with pytest.raises(IllegalStateTransitionError) as excinfo:
        machine.start(dormant, at=T_NOW)
    context = excinfo.value.context
    assert (context["from_state"], context["to_state"]) == ("DORMANT", "RUNNING")
    assert context["allowed_from_state"] == ["READY"]

    # 引擎层同样拦截（休眠任务未就绪，不许执行）
    task = scheduler.task("task_semantic_000")
    assert task is not None and task.state is TaskState.DORMANT
    with pytest.raises(IllegalStateTransitionError):
        scheduler.start(task.task_id, at=T_NOW)
    with pytest.raises(IllegalStateTransitionError):
        scheduler.complete(task.task_id, at=T_NOW)


def test_gate4_running_cannot_be_reached_by_skipping_ready(
    machine: TaskStateMachine,
) -> None:
    dormant = _task_in_state(TaskState.DORMANT)
    with pytest.raises(IllegalStateTransitionError):
        machine.transition(dormant, TaskState.RUNNING, at=T_NOW)

    ready = _task_in_state(TaskState.READY)
    with pytest.raises(IllegalStateTransitionError) as excinfo:
        machine.complete(ready, at=T_NOW)  # READY -> COMPLETED 跳级
    assert excinfo.value.context["from_state"] == "READY"
    assert excinfo.value.context["to_state"] == "COMPLETED"


def test_gate4_state_machine_never_allows_rollback_or_resurrection(
    machine: TaskStateMachine,
) -> None:
    ready = _task_in_state(TaskState.READY)
    with pytest.raises(IllegalStateTransitionError):
        machine.transition(ready, TaskState.DORMANT, at=T_NOW)  # 回退到休眠

    completed = _task_in_state(TaskState.COMPLETED)
    for target in (TaskState.DORMANT, TaskState.READY, TaskState.RUNNING):
        with pytest.raises(IllegalStateTransitionError):
            machine.transition(completed, target, at=T_NOW)


def test_gate4_entire_transition_matrix_is_intercepted(machine: TaskStateMachine) -> None:
    """穷举 4x4 全矩阵：合法 3 条放行，其余 13 条 100% 抛错。"""
    legal = {
        (TaskState.DORMANT, TaskState.READY),
        (TaskState.READY, TaskState.RUNNING),
        (TaskState.RUNNING, TaskState.COMPLETED),
    }
    intercepted: list[tuple[str, str]] = []
    allowed: list[tuple[str, str]] = []
    for source in TaskState:
        for target in TaskState:
            task = _task_in_state(source)
            if (source, target) in legal:
                updated = machine.transition(task, target, at=T_NOW)
                allowed.append((source.value, target.value))
                assert updated.state is target
            else:
                with pytest.raises(IllegalStateTransitionError) as excinfo:
                    machine.transition(task, target, at=T_NOW)
                assert excinfo.value.context["reason"] == "illegal_state_transition"
                intercepted.append((source.value, target.value))

    assert len(allowed) == 3
    assert len(intercepted) == 13, "16 种跃迁里必须只有 3 种合法"
    print(f"[M2-005R 状态机] 合法={allowed} 拦截={len(intercepted)}/13")


def test_gate4_legal_path_runs_end_to_end(
    scheduler: ConditionalTaskScheduler,
) -> None:
    report = scheduler.tick(_mechanical_signal())
    task_id = report.ready_task_ids[0]

    running = scheduler.start(task_id, at=T_NOW)
    assert running.state is TaskState.RUNNING and running.started_at == T_NOW
    completed = scheduler.complete(task_id, at=T_NOW + timedelta(minutes=5))
    assert completed.state is TaskState.COMPLETED
    assert completed.completed_at == T_NOW + timedelta(minutes=5)

    # 完成后不得复活 / 重跑
    with pytest.raises(IllegalStateTransitionError):
        scheduler.start(task_id, at=T_NOW)
    assert scheduler.task(task_id) == completed
    assert all(
        entry.state is not TaskState.DORMANT for entry in scheduler.assemble_board(at=T_NOW).entries
    )


# ===========================================================================
# 端到端：200 项任务的一天
# ===========================================================================


def test_two_hundred_task_day_end_to_end(scheduler: ConditionalTaskScheduler) -> None:
    """完整一天：机械快轨点亮 -> 看板只装成熟任务 -> 机会式捎带补语义 -> 执行闭环。"""
    fast = scheduler.tick(_mechanical_signal())
    board_after_fast = scheduler.assemble_board(at=T_NOW)

    assert fast.llm_calls == 0
    assert board_after_fast.dormant_token_cost == 0
    assert board_after_fast.entry_count == len(fast.ready_task_ids)

    context = WakeContext(
        captured_at=T_NOW + timedelta(minutes=1),
        user_resumed_ai=True,
        scene_tags=(LITIGATION_SCENE, CONTRACT_SIGNING_SCENE),
        position=GeoPosition(place_key=SHANGHAI_OFFICE, inside_fence=True, captured_at=T_NOW),
        vitals=_vital_snapshot(satisfied_evenings=VITAL_DAYS, deep_focus=False),
    )
    piggy = scheduler.piggyback(context)
    assert piggy.llm_calls == 1

    board_final = scheduler.assemble_board(at=T_NOW)
    assert board_final.entry_count == len(fast.ready_task_ids) + len(piggy.ready_task_ids)
    assert board_final.entry_count + board_final.frozen_out == TASK_TOTAL
    assert board_final.dormant_token_cost == 0
    assert scheduler.llm_calls == 1, "全天只允许 1 次机会式捎带调用"

    # 未成熟任务继续休眠，等待真正成熟的时刻
    assert scheduler.dormant_count == TASK_TOTAL - board_final.entry_count
    print(
        f"[M2-005R 端到端] 任务总数={TASK_TOTAL} 快轨点亮={len(fast.ready_task_ids)} "
        f"捎带点亮={len(piggy.ready_task_ids)} 仍休眠={scheduler.dormant_count} "
        f"休眠 Token={board_final.dormant_token_cost} 全天大模型调用={scheduler.llm_calls}"
    )


def test_engine_rejects_duplicate_and_unknown_tasks(
    scheduler: ConditionalTaskScheduler,
) -> None:
    duplicate = _semantic_task(0)
    with pytest.raises(Exception) as excinfo:
        scheduler.register_task(duplicate)
    assert getattr(excinfo.value, "context", {}).get("reason") == "duplicate_task"

    assert scheduler.task("task_does_not_exist") is None
    with pytest.raises(Exception) as excinfo:
        scheduler.start("task_does_not_exist", at=T_NOW)
    assert getattr(excinfo.value, "context", {}).get("reason") == "unknown_task"


def test_condition_contract_rejects_incomplete_specs() -> None:
    """条件契约不猜、不兜底：缺字段直接拒绝。"""
    with pytest.raises(Exception):
        Condition(kind=ConditionKind.ABSOLUTE_TIME, summary="缺 deadline")
    with pytest.raises(Exception):
        Condition(kind=ConditionKind.GEO_FENCE, summary="缺 place_key")
    with pytest.raises(Exception):
        Condition(
            kind=ConditionKind.VITAL_THRESHOLD,
            summary="缺 threshold",
            metric=VITAL_METRIC,
            comparator=">",
            consecutive_days=3,
        )
    with pytest.raises(Exception):
        Condition(kind=ConditionKind.SEMANTIC_SCENE, summary="既无标签也无专注要求")


def test_semantic_condition_cannot_be_judged_on_the_mechanical_track() -> None:
    """语义条件绝不许混进机械快轨（那意味着偷偷花 Token）。"""
    fast_track = Level1FastTrack()
    semantic = Condition(
        kind=ConditionKind.SEMANTIC_SCENE,
        summary="语义条件",
        scene_tags=(LITIGATION_SCENE,),
    )
    with pytest.raises(Exception) as excinfo:
        fast_track.condition_satisfied(semantic, _mechanical_signal())
    assert getattr(excinfo.value, "context", {}).get("reason") == "semantic_condition_on_fast_track"
