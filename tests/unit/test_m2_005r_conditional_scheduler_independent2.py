"""M2-005R 条件驱动任务调度双轨引擎 四大硬门禁验收单测。

门禁对位：
1. DORMANT 未成熟任务看板 Token 严格为 0（物理隐形）；
2. Level-1 机械快轨：200 任务纯 Python 扫一次 <1ms、LLM 调用恒 0、即刻就绪；
3. Level-2 机会式捎带：无唤醒不评估、空场景标签拒绝、场景不相交不动；
4. 状态机非法跃迁 100% 拦截（IllegalStateTransitionError）。
"""

from __future__ import annotations

import time

import pytest

from aios_core.cockpit.pipeline import Utf8ByteTokenCounter
from aios_core.scheduler.conditional_engine_independent2 import (
    AbsoluteTimeTrigger,
    AnyOfTrigger,
    ConditionalTask,
    ConditionalTaskEngine,
    GeofenceTrigger,
    IllegalStateTransitionError,
    SemanticSceneTrigger,
    SensorSnapshot,
    SustainedHeartRateTrigger,
    TaskState,
)

NS = 1_726_400_000_000_000_000
HOUR_NS = 3_600_000_000_000
# 上海办公室坐标（地理围栏用例）
SH_OFFICE = (31.2304, 121.4737)


def _engine_with_200_tasks(now: int = NS) -> ConditionalTaskEngine:
    """200 项跨周期复杂条件任务：190 未到期 + 10 语义捎带。"""
    engine = ConditionalTaskEngine()
    for i in range(190):
        engine.register(
            ConditionalTask(
                task_id=f"legal_monitor_{i:03d}",
                title=f"监控对手方{i}：实控人股权变更提醒",
                trigger=AbsoluteTimeTrigger(due_at_ns=now + (i + 1) * HOUR_NS),
                created_at_ns=now,
            )
        )
    for j in range(10):
        engine.register(
            ConditionalTask(
                task_id=f"semantic_sign_{j:02d}",
                title=f"回上海办公室且非深度专注时提示签署对赌回购协议v{j}",
                trigger=AbsoluteTimeTrigger(due_at_ns=now + 10**18),  # 永不机械到期
                semantic=SemanticSceneTrigger(
                    scene_tags=frozenset({"office_shanghai", "non_deep_focus"})
                ),
                created_at_ns=now,
            )
        )
    return engine


# ---------------------------------------------------------------------------
# 门禁 1：DORMANT 看板 Token 严格为 0
# ---------------------------------------------------------------------------

def test_dormant_tasks_token_cost_strictly_zero() -> None:
    engine = _engine_with_200_tasks()
    view = engine.prompt_view()
    # 200 项全部 DORMANT：看板行数为 0，因此消耗为 0
    assert view == []
    assert Utf8ByteTokenCounter().count("\n".join(view)) == 0
    assert engine.dormant_token_cost() == 0

    # 机械到期 3 项后：看板只出现 READY 的 3 项，197 项 DORMANT 仍缺席
    snap = SensorSnapshot(at_ns=NS + 3 * HOUR_NS + 1)
    promoted = engine.mechanical_sweep(snap)
    assert len(promoted) == 3
    prompt = "\n".join(engine.prompt_view())
    assert prompt.count("【就绪】") == 3
    # 逐项核对：任何 DORMANT 标题都不允许出现在看板字符串中
    for i in range(3, 190):
        assert f"监控对手方{i}" not in prompt
    for j in range(10):
        assert f"对赌回购协议v{j}" not in prompt
    assert engine.dormant_token_cost() == 0


# ---------------------------------------------------------------------------
# 门禁 2：Level-1 机械快轨 0 Token 判定（<1ms、LLM=0、直接 READY）
# ---------------------------------------------------------------------------

def test_level1_mechanical_fast_track_sub_ms_zero_llm() -> None:
    engine = _engine_with_200_tasks()
    # 附加三个真实物理条件：地理围栏 / 连续三日心率 / 时间到期
    engine.register(
        ConditionalTask(
            task_id="geo_office_sign",
            title="回到上海办公室提示签署回购协议",
            trigger=GeofenceTrigger(center_lat=SH_OFFICE[0], center_lng=SH_OFFICE[1], radius_m=200),
        )
    )
    engine.register(
        ConditionalTask(
            task_id="hr_cardio_3d",
            title="连续3天晚间心率>95bpm启动心内科预约建档",
            trigger=SustainedHeartRateTrigger(threshold_bpm=95.0, min_consecutive_days=3),
        )
    )
    engine.register(
        ConditionalTask(
            task_id="abs_due_now",
            title="仲裁答辩状递交截止提醒",
            trigger=AnyOfTrigger(
                triggers=(AbsoluteTimeTrigger(due_at_ns=NS - 1),)
            ),
        )
    )

    snap = SensorSnapshot(
        at_ns=NS,
        heart_rate_bpm=132.0,
        latitude=31.2305, longitude=121.4738,  # 围栏内（约 15 米）
        evening_hr_series=(98.5, 99.1, 101.0),  # 连续 3 天 > 95
    )
    # 200+3 任务整库扫描，取最坏值；先热机一次排除解释器冷启动，
    # 再量 200 次最坏值（稳态应约 30~80µs，门禁阈值 1ms 有 10 倍余量）
    engine.mechanical_sweep(snap)
    worst_s = 0.0
    promoted_once = None
    for _ in range(200):
        t0 = time.perf_counter()
        promoted_once = engine.mechanical_sweep(snap)
        worst_s = max(worst_s, time.perf_counter() - t0)
    assert promoted_once == []          # 首轮已提升，复扫幂等无新增
    assert worst_s < 0.001, f"203 任务机械扫耗时 {worst_s*1000:.3f}ms ≥ 1ms"
    assert engine.llm_invocations == 0  # 0 Token：模型调用恒为 0
    assert engine.get("geo_office_sign").state is TaskState.READY
    assert engine.get("hr_cardio_3d").state is TaskState.READY
    assert engine.get("abs_due_now").state is TaskState.READY
    assert engine.get("geo_office_sign").ready_reason == "L1机械条件命中"

    # 负向：单日尖峰不满足连续阈值；围栏外不命中
    engine2 = ConditionalTaskEngine()
    engine2.register(
        ConditionalTask(
            task_id="hr_spike_only",
            title="连续3天晚间心率>95bpm启动心内科建档(反例)",
            trigger=SustainedHeartRateTrigger(threshold_bpm=95.0, min_consecutive_days=3),
        )
    )
    promoted = engine2.mechanical_sweep(
        SensorSnapshot(at_ns=NS, evening_hr_series=(99.0, 88.0, 102.0))
    )
    assert promoted == []
    assert engine2.get("hr_spike_only").state is TaskState.DORMANT

    engine3 = ConditionalTaskEngine()
    engine3.register(
        ConditionalTask(
            task_id="geo_far",
            title="回到上海办公室才提示(反例)",
            trigger=GeofenceTrigger(center_lat=SH_OFFICE[0], center_lng=SH_OFFICE[1], radius_m=200),
        )
    )
    promoted = engine3.mechanical_sweep(
        SensorSnapshot(at_ns=NS, latitude=30.0, longitude=120.0)  # 约 160km 外
    )
    assert promoted == []
    assert engine3.get("geo_far").state is TaskState.DORMANT


# ---------------------------------------------------------------------------
# 门禁 3：Level-2 机会式捎带
# ---------------------------------------------------------------------------

def test_level2_opportunistic_piggyback_only_on_real_wake() -> None:
    engine = _engine_with_200_tasks()
    # 语义任务永不机械到期；不被扫描的捎带侧无任何主动评估
    engine.mechanical_sweep(SensorSnapshot(at_ns=NS))
    assert engine.get("semantic_sign_00").state is TaskState.DORMANT

    # 空场景标签 = 调用方缺陷：拒绝（绝不"为了评估而唤醒"）
    with pytest.raises(ValueError):
        engine.piggyback_on_wake([])
    assert engine.wake_piggyback_count == 0

    # 真实唤醒但场景不相交：保持 DORMANT
    assert engine.piggyback_on_wake({"gym_badminton", "sweat"}) == []
    assert engine.get("semantic_sign_00").state is TaskState.DORMANT
    assert engine.llm_invocations == 0

    # 真实唤醒且场景相交：10 项语义任务顺路就绪
    promoted = engine.piggyback_on_wake({"office_shanghai", "meeting_break"})
    assert len(promoted) == 10
    assert engine.get("semantic_sign_00").state is TaskState.READY
    assert engine.get("semantic_sign_00").ready_reason == "L2唤醒捎带命中"
    assert engine.llm_invocations == 0          # 捎带不发起新的模型调用
    assert engine.wake_piggyback_count == 2     # 只有两次真实唤醒


# ---------------------------------------------------------------------------
# 门禁 4：状态机非法跃迁 100% 拦截
# ---------------------------------------------------------------------------

def test_illegal_state_transitions_100_percent_blocked() -> None:
    engine = _engine_with_200_tasks()
    task = ConditionalTask(task_id="t1", title="样例", trigger=AbsoluteTimeTrigger(due_at_ns=NS))
    engine.register(task)

    # DORMANT 直跳 RUNNING / COMPLETED —— 拦截
    with pytest.raises(IllegalStateTransitionError):
        task.start_execution()
    with pytest.raises(IllegalStateTransitionError):
        task.complete()
    with pytest.raises(IllegalStateTransitionError):
        task.transition_to(TaskState.DORMANT)  # 原地不动也非法
    assert task.state is TaskState.DORMANT

    # 合法：DORMANT→READY→RUNNING→COMPLETED
    task.transition_to(TaskState.READY)
    task.start_execution()
    assert task.state is TaskState.RUNNING
    with pytest.raises(IllegalStateTransitionError):
        task.transition_to(TaskState.READY)     # 回退非法
    with pytest.raises(IllegalStateTransitionError):
        task.transition_to(TaskState.DORMANT)   # 回退非法
    task.complete()
    assert task.state is TaskState.COMPLETED

    # 终态不可再迁移：重复完成 / 重启 全部拦截
    for target in (TaskState.COMPLETED, TaskState.RUNNING, TaskState.READY, TaskState.DORMANT):
        with pytest.raises(IllegalStateTransitionError):
            task.transition_to(target)

    # 引擎机械扫也不会把已终态任务再推入流水线
    promoted = engine.mechanical_sweep(SensorSnapshot(at_ns=NS + 10 * HOUR_NS))
    assert "t1" not in promoted
    assert engine.get("t1").state is TaskState.COMPLETED


def test_execution_through_pipeline_semantics() -> None:
    """完整合法流水线：200 任务中逐项推进，终态集合精确。"""
    engine = _engine_with_200_tasks()
    engine.mechanical_sweep(SensorSnapshot(at_ns=NS + 5 * HOUR_NS))
    ready = [tid for tid in engine._tasks if engine._tasks[tid].state is TaskState.READY]
    assert len(ready) == 5  # 5 小时 = 5 项到期
    for tid in ready[:3]:
        engine.get(tid).start_execution()
        engine.get(tid).complete()
    counts = engine.state_counts()
    assert counts == {"DORMANT": 195, "READY": 2, "RUNNING": 0, "COMPLETED": 3}
