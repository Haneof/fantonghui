"""M2-005R 条件驱动任务调度双轨引擎 —— 200 项跨周期条件任务压测。

实战情境：创业企业法务总监的 200 项复杂条件任务（诉讼对方股权变更
监控、连续晚间心率超标启动心内科建档、回到上海办公室非专注时提示
签署对赌回购协议等）。

四大硬门禁：
1. DORMANT 任务在看板装配路径上物理隐形，Token 贡献严格为 0；
2. Level-1 机械快轨纯 Python 判定，200 项扫描毫秒级，大模型调用为 0；
3. Level-2 机会式捎带：仅在有显式用户会话场景时评估，绝无自主唤醒；
4. 状态机非法跃迁 100% 抛 IllegalStateTransitionError。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.scheduler.conditional_engine import (
    ConditionalSchedulerEngine,
    ConditionalTask,
    GeoFenceCondition,
    HeartRateThresholdCondition,
    IllegalStateTransitionError,
    SemanticCondition,
    TaskState,
    TimeDueCondition,
)

UTC = timezone.utc
T_BASE = datetime(2026, 9, 1, 8, 0, 0, tzinfo=UTC)


def _build_200_tasks() -> list[ConditionalTask]:
    """200 项跨周期条件任务：100 机械（时间/围栏/心率）+ 100 语义。"""
    tasks: list[ConditionalTask] = []
    for i in range(40):
        tasks.append(
            ConditionalTask(
                task_id=f"tsk_due_{i:03d}",
                title=f"到期任务#{i}：合同/备案/续约节点",
                condition=TimeDueCondition(due_at=T_BASE + timedelta(days=i % 30, hours=i)),
                brief=f"机械|到期任务#{i}",
                priority=(i % 100),
            )
        )
    for i in range(30):
        tasks.append(
            ConditionalTask(
                task_id=f"tsk_geo_{i:03d}",
                title=f"围栏任务#{i}：上海办公室节点提醒",
                condition=GeoFenceCondition(region_key="office_shanghai_pudong"),
                brief=f"机械|围栏任务#{i}",
            )
        )
    for i in range(30):
        tasks.append(
            ConditionalTask(
                task_id=f"tsk_hr_{i:03d}",
                title=f"生理任务#{i}：晚间心率连续超标建档",
                condition=HeartRateThresholdCondition(
                    bpm_greater_than=95, consecutive_windows=3
                ),
                brief=f"机械|生理任务#{i}",
            )
        )
    semantic_titles = (
        ("对方实控人股权变更追踪", ("litigation", "equity_change", "counterparty")),
        ("对赌回购协议签署提示", ("office_shanghai", "idle_focus", "contract_review")),
        ("仲裁证据链补强建议", ("litigation", "evidence_review")),
        ("竞业协议风险面谈准备", ("hr_negotiation", "contract_review")),
        ("应收账款账期盘点", ("finance_review", "idle_focus")),
    )
    for i in range(100):
        title, tags = semantic_titles[i % len(semantic_titles)]
        tasks.append(
            ConditionalTask(
                task_id=f"tsk_sem_{i:03d}",
                title=f"语义任务#{i}：{title}",
                condition=SemanticCondition(required_scene_tags=tags),
                brief=f"语义|{title}#{i}",
            )
        )
    return tasks


# ======================================================================
# 门禁一：DORMANT 物理隐形，Token 严格为 0
# ======================================================================

def test_gate1_dormant_tasks_are_physically_invisible_in_kanban() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register_many(_build_200_tasks())
    # 什么条件都没满足：看板必须是空结构
    kanban = engine.assemble_kanban()
    assert kanban == ()
    # 200 个标题全部不存在于装配路径（任何字符串拼接都不产生）
    for task in engine._tasks.values():
        if task.state is TaskState.DORMANT:
            assert all(task.title not in entry["brief"] for entry in kanban)
            assert all(task.task_id != e["task_id"] for e in kanban)
    # 未成熟任务的 Token 贡献严格为 0（空看板 = 0 token）
    from aios_core.cockpit.pipeline import estimate_tokens

    assert sum(estimate_tokens(e["brief"]) for e in kanban) == 0


def test_gate1_only_ready_tasks_enter_kanban_after_promotion() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register_many(_build_200_tasks())
    engine.mechanical_sweep(
        {"now": T_BASE + timedelta(days=40), "current_region": "", "hr_bpm": 70}
    )
    kanban = engine.assemble_kanban()
    assert 0 < len(kanban) <= 40  # 只有到期任务跃迁；语义任务绝不出现
    assert all(entry["task_id"].startswith("tsk_due_") for entry in kanban)
    assert all(not e["task_id"].startswith("tsk_sem_") for e in kanban)


# ======================================================================
# 门禁二：Level-1 机械快轨 0 Token / 0 LLM / 毫秒级
# ======================================================================

def test_gate2_mechanical_fast_track_zero_llm_and_sub_millisecond() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register_many(_build_200_tasks())
    # 引擎本体无任何大模型代码路径：llm_calls 是唯一可信计数器
    ctx = {
        "now": T_BASE + timedelta(days=40),
        "current_region": "office_shanghai_pudong",
        "hr_bpm": 101,
        "hr_over_threshold_streak": 3,
    }
    promoted = engine.mechanical_sweep(ctx)
    stats = engine.stats()

    assert len(promoted) == 100  # 40 到期(≤40天) + 30 围栏 + 30 心率
    assert stats["llm_calls"] == 0  # 机械快轨从未触碰任何大模型
    # 200 项量级纯 Python 判定必须毫秒级（工单 1ms 预算）
    assert stats["last_mechanical_sweep_ms"] <= 1.0, (
        f"200-task mechanical sweep took {stats['last_mechanical_sweep_ms']:.3f}ms"
    )
    assert stats["mechanical_evaluations"] == 100


def test_gate2_hr_condition_requires_consecutive_streak() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register(
        ConditionalTask(
            task_id="tsk_hr_single",
            title="连续3天晚间心率>95启动心内科预约建档",
            condition=HeartRateThresholdCondition(bpm_greater_than=95, consecutive_windows=3),
            brief="机械|心内科建档",
        )
    )
    assert engine.mechanical_sweep(
        {"now": T_BASE, "hr_bpm": 101, "hr_over_threshold_streak": 2}
    ) == ()
    assert engine.mechanical_sweep(
        {"now": T_BASE, "hr_bpm": 101, "hr_over_threshold_streak": 3}
    ) == ("tsk_hr_single",)
    assert engine.task_state("tsk_hr_single") is TaskState.READY


# ======================================================================
# 门禁三：Level-2 机会式捎带，绝无自主唤醒
# ======================================================================

def test_gate3_semantic_tasks_only_via_piggyback_session() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register_many(_build_200_tasks())
    # 用户从未唤醒：语义任务必须全部保持 DORMANT
    engine.mechanical_sweep(
        {"now": T_BASE + timedelta(days=40), "current_region": "x", "hr_bpm": 60}
    )
    assert all(
        t.state is TaskState.DORMANT
        for t in engine._tasks.values()
        if isinstance(t.condition, SemanticCondition)
    )
    # 用户主动唤醒且场景相关：仅命中场景的任务被顺路评估
    evaluations: list[str] = []
    promoted = engine.piggyback_evaluate(
        session_id="sess_user_initiated_001",
        scene_tags=("litigation", "equity_change", "contract_review"),
        llm_evaluator=lambda task, ctx: evaluations.append(task.task_id) or True,
        session_ctx={"user_message": "对方律师又在搞小动作"},
    )
    assert len(evaluations) == len(promoted)  # 只评估了场景匹配的语义任务
    assert all(tid.startswith("tsk_sem_") for tid in promoted)
    stats = engine.stats()
    assert stats["piggyback_sessions"] == 1
    assert stats["llm_calls"] == len(evaluations)  # 评估次数 = LLM 调用次数
    # 场景不匹配的语义任务仍在休眠
    assert engine.task_state("tsk_sem_002") is TaskState.DORMANT  # 需要 evidence_review


def test_gate3_engine_never_self_wakes_without_session() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register(
        ConditionalTask(
            task_id="tsk_sem_lonely",
            title="独立语义任务",
            condition=SemanticCondition(required_scene_tags=("anything",)),
            brief="语义|独立",
        )
    )
    with pytest.raises(ValueError, match="explicit user session"):
        engine.piggyback_evaluate(
            session_id="",
            scene_tags=("anything",),
            llm_evaluator=lambda *a: True,
            session_ctx={},
        )
    assert engine.task_state("tsk_sem_lonely") is TaskState.DORMANT


# ======================================================================
# 门禁四：状态机非法跃迁 100% 拦截
# ======================================================================

def test_gate4_legal_lifecycle_walks_clean() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register(
        ConditionalTask(
            task_id="tsk_flow",
            title="全周期任务",
            condition=GeoFenceCondition(region_key="office_shanghai_pudong"),
            brief="机械|全周期",
        )
    )
    engine.mechanical_sweep({"now": T_BASE, "current_region": "office_shanghai_pudong"})
    engine.start("tsk_flow")
    assert engine.task_state("tsk_flow") is TaskState.RUNNING
    engine.complete("tsk_flow")
    assert engine.task_state("tsk_flow") is TaskState.COMPLETED


def test_gate4_every_illegal_transition_is_blocked() -> None:
    engine = ConditionalSchedulerEngine()
    engine.register(
        ConditionalTask(
            task_id="tsk_state",
            title="状态机任务",
            condition=GeoFenceCondition(region_key="office_shanghai_pudong"),
            brief="机械|状态机",
        )
    )
    # DORMANT 直接执行/完成：拦截
    with pytest.raises(IllegalStateTransitionError):
        engine.start("tsk_state")
    with pytest.raises(IllegalStateTransitionError):
        engine.complete("tsk_state")
    # READY 直接完成：拦截（必须先 RUNNING）
    engine.mechanical_sweep({"now": T_BASE, "current_region": "office_shanghai_pudong"})
    with pytest.raises(IllegalStateTransitionError):
        engine.complete("tsk_state")
    # RUNNING 直接重新开始：拦截
    engine.start("tsk_state")
    with pytest.raises(IllegalStateTransitionError):
        engine.start("tsk_state")
    # COMPLETED 之后的一切：拦截
    engine.complete("tsk_state")
    for operation in (engine.start, engine.complete):
        with pytest.raises(IllegalStateTransitionError):
            operation("tsk_state")
    assert engine.task_state("tsk_state") is TaskState.COMPLETED
