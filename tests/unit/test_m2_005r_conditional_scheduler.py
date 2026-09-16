"""M2-005R 条件驱动任务调度双轨引擎验收测试。

场景：创业企业法务总监日程挂载 200 项跨周期复杂条件任务（诉讼对方
实控人股权变更提醒、连续 3 天晚间心率超 95bpm 启动心内科预约建档、
回到上海办公室且非深度专注时提示签署对赌回购协议）。

四大硬门禁：
1. DORMANT 任务 Token 严格为 0（物理隐形）；
2. Level-1 机械快轨 0 Token / 0 LLM、1ms 内纯 Python 判定直达 READY；
3. Level-2 机会式捎带：只在用户主动唤醒且场景相关时评估；
4. 状态机非法跃迁 100% 拦截。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

import pytest

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.scheduler.conditional_engine import (
    ConditionalTask,
    ConditionalTaskEngine,
    ConditionalTaskState,
    ConditionKind,
    IllegalStateTransitionError,
)

DAY0 = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
TOTAL_TASKS = 200


def build_legal_director_corpus() -> ConditionalTaskEngine:
    """200 项法务总监条件任务：80 时间 / 40 围栏 / 40 心率 / 40 语义。"""

    engine = ConditionalTaskEngine()
    for i in range(80):
        engine.register_task(
            f"task-time-{i:03d}",
            f"诉讼时效节点复核 T{i:03d}：证据交换期限跟踪",
            ConditionKind.TIME_DUE,
            {"due_at": DAY0 + timedelta(days=i % 30, hours=i % 12)},
        )
    for i in range(40):
        locations = ("上海办公室", "静安法院调解室") if i % 2 == 0 else ("虹桥枢纽",)
        engine.register_task(
            f"task-geo-{i:03d}",
            f"到场即用印 G{i:03d}：对赌回购协议签署提示",
            ConditionKind.GEOFENCE_ENTER,
            {"locations": locations},
        )
    for i in range(40):
        engine.register_task(
            f"task-hr-{i:03d}",
            f"心内科预约建档 H{i:03d}：连续 3 天晚间心率超过 95bpm",
            ConditionKind.HEART_RATE_THRESHOLD,
            {"threshold_bpm": 95.0, "required_consecutive_days": 3},
        )
    for i in range(40):
        scene = "股权变更审查" if i % 2 == 0 else "诉讼策略推演"
        engine.register_task(
            f"task-sem-{i:03d}",
            f"语义值守 S{i:03d}：诉讼对方实控人股权变更异动提醒",
            ConditionKind.SEMANTIC_SCENE,
            {"scene": scene},
        )
    assert len(engine.tasks_in_state(ConditionalTaskState.DORMANT)) == TOTAL_TASKS
    return engine


# ---------------------------------------------------------------------------
# 硬门禁 1：DORMANT 任务 Token 严格为 0
# ---------------------------------------------------------------------------


def test_gate1_all_200_dormant_tasks_are_physically_invisible() -> None:
    engine = build_legal_director_corpus()

    prompt = engine.assemble_session_prompt()
    assert prompt == ""
    assert engine.dormant_token_consumption() == 0
    assert engine.visible_tasks() == ()
    assert estimate_tokens(prompt) == 0


def test_gate1_mature_tasks_never_drag_dormant_tokens() -> None:
    engine = build_legal_director_corpus()

    # 3 项时间任务成熟进入 READY；其余 197 项仍休眠。
    mature = engine.task("task-time-000")
    engine.transition(mature.task_id, ConditionalTaskState.READY)
    engine.transition("task-time-001", ConditionalTaskState.READY)
    engine.transition("task-time-002", ConditionalTaskState.READY)

    prompt = engine.assemble_session_prompt()
    assert estimate_tokens(prompt) > 0
    assert len(engine.visible_tasks()) == 3

    # 全部 197 项休眠任务的标题一个字都不允许出现在 Prompt 中。
    for task in engine.tasks_in_state(ConditionalTaskState.DORMANT):
        assert task.title not in prompt
    assert engine.dormant_token_consumption() == 0


# ---------------------------------------------------------------------------
# 硬门禁 2：Level-1 机械快轨 0 Token 判定（0 LLM、1ms 内）
# ---------------------------------------------------------------------------


def test_gate2_level1_mechanical_fast_track_zero_llm_within_1ms() -> None:
    engine = build_legal_director_corpus()

    # 连续 3 天晚间心率 102bpm（超标），喂养心率连续计数。
    for _ in range(2):
        engine.observe_evening_heart_rate(102.0)

    snapshot = {
        "now": DAY0 + timedelta(days=29, hours=23),
        "location": "上海办公室",
        "heart_rate_bpm": 102.0,  # 第 3 天晚间，命中连续 3 天阈值
    }
    newly_ready = engine.evaluate_level1(snapshot)

    # 大模型调用次数严格为 0。
    assert engine.llm_calls == 0

    # 时间到期（29 天窗口内到期的任务）、上海办公室围栏、心率连续超标全部命中。
    ready = set(newly_ready)
    assert any(t.startswith("task-time-") for t in ready)
    assert {t for t in ready if t.startswith("task-geo-")} == {
        f"task-geo-{i:03d}" for i in range(0, 40, 2)
    }
    assert {t for t in ready if t.startswith("task-hr-")} == {
        f"task-hr-{i:03d}" for i in range(40)
    }
    for task_id in ready:
        assert engine.task(task_id).state is ConditionalTaskState.READY

    # 200 项批量判定在 1ms/项 预算内（机械快轨纯 Python）。
    assert engine.last_level1_latency_ms / max(1, TOTAL_TASKS) <= 1.0
    assert engine.last_level1_latency_ms <= 50.0  # 整批硬上限兜底


def test_gate2_level1_is_idempotent_and_skips_non_dormant() -> None:
    engine = build_legal_director_corpus()
    snapshot = {"now": DAY0 + timedelta(days=40), "location": "静安法院调解室"}
    first = engine.evaluate_level1(snapshot)
    second = engine.evaluate_level1(snapshot)
    assert second == []  # 已 READY 的任务不会重复判定
    assert all(engine.task(t).state is ConditionalTaskState.READY for t in first)


# ---------------------------------------------------------------------------
# 硬门禁 3：Level-2 机会式捎带（绝不自主唤醒大模型）
# ---------------------------------------------------------------------------


def _stub_llm_verdict(tasks: Iterable[ConditionalTask], scene: str) -> dict[str, bool]:
    """确定性 LLM 桩：场景为股权变更审查时裁决全部成熟。"""

    return {t.task_id: scene == "股权变更审查" for t in tasks}


def test_gate3_no_autonomous_llm_wakeup_for_dormant_semantic_tasks() -> None:
    engine = build_legal_director_corpus()

    # 调度器例行心跳（非用户主动）：大模型调用严格为 0，任务纹丝不动。
    for _ in range(10):
        assert engine.piggyback_level2(
            user_initiated=False, scene="股权变更审查", llm_sink=_stub_llm_verdict
        ) == []
    assert engine.llm_calls == 0
    assert len(engine.tasks_in_state(ConditionalTaskState.DORMANT)) == TOTAL_TASKS


def test_gate3_opportunistic_piggyback_only_when_user_wakes_matching_scene() -> None:
    engine = build_legal_director_corpus()

    # 用户主动唤醒但场景无关：顺路看一眼，没有匹配任务，0 次大模型调用。
    assert engine.piggyback_level2(
        user_initiated=True, scene="无关场景", llm_sink=_stub_llm_verdict
    ) == []
    assert engine.llm_calls == 0

    # 用户主动唤醒且命中"股权变更审查"：恰好 1 次捎带调用，20 项语义任务成熟。
    ready = engine.piggyback_level2(
        user_initiated=True, scene="股权变更审查", llm_sink=_stub_llm_verdict
    )
    assert engine.llm_calls == 1
    assert len(ready) == 20
    assert all(engine.task(t).state is ConditionalTaskState.READY for t in ready)

    # 剩余 20 项"诉讼策略推演"语义任务仍休眠、仍零 Token。
    remaining_semantic = [
        t
        for t in engine.tasks_in_state(ConditionalTaskState.DORMANT)
        if t.condition_kind is ConditionKind.SEMANTIC_SCENE
    ]
    assert len(remaining_semantic) == 20
    assert engine.dormant_token_consumption() == 0


# ---------------------------------------------------------------------------
# 硬门禁 4：状态机非法跃迁 100% 拦截
# ---------------------------------------------------------------------------

_ALL_STATES = (
    ConditionalTaskState.DORMANT,
    ConditionalTaskState.READY,
    ConditionalTaskState.RUNNING,
    ConditionalTaskState.COMPLETED,
)
_LEGAL_PAIRS = {
    (ConditionalTaskState.DORMANT, ConditionalTaskState.READY),
    (ConditionalTaskState.READY, ConditionalTaskState.RUNNING),
    (ConditionalTaskState.RUNNING, ConditionalTaskState.COMPLETED),
}


def test_gate4_every_illegal_transition_is_intercepted() -> None:
    for source in _ALL_STATES:
        for target in _ALL_STATES:
            if (source, target) in _LEGAL_PAIRS:
                continue
            engine = ConditionalTaskEngine()
            engine.register_task("t-probe", "探针任务", ConditionKind.TIME_DUE, {"due_at": DAY0})
            # 把探针推到 source 态（沿合法链走）。
            chain = {
                ConditionalTaskState.DORMANT: [],
                ConditionalTaskState.READY: [ConditionalTaskState.READY],
                ConditionalTaskState.RUNNING: [ConditionalTaskState.READY, ConditionalTaskState.RUNNING],
                ConditionalTaskState.COMPLETED: [
                    ConditionalTaskState.READY,
                    ConditionalTaskState.RUNNING,
                    ConditionalTaskState.COMPLETED,
                ],
            }[source]
            for step in chain:
                engine.transition("t-probe", step)

            with pytest.raises(IllegalStateTransitionError):
                engine.transition("t-probe", target)
            assert engine.task("t-probe").state is source  # 状态未被污染


def test_gate4_dormant_task_cannot_be_directly_executed() -> None:
    engine = build_legal_director_corpus()
    with pytest.raises(IllegalStateTransitionError):
        engine.start_task("task-sem-001")  # DORMANT -> RUNNING 直触发执行
    with pytest.raises(IllegalStateTransitionError):
        engine.complete_task("task-sem-001")  # DORMANT -> COMPLETED
    assert engine.task("task-sem-001").state is ConditionalTaskState.DORMANT


def test_gate4_legal_lifecycle_walks_to_completion() -> None:
    engine = build_legal_director_corpus()
    task = engine.task("task-geo-001")
    engine.transition(task.task_id, ConditionalTaskState.READY)
    engine.start_task(task.task_id)
    engine.complete_task(task.task_id)
    assert engine.task("task-geo-001").state is ConditionalTaskState.COMPLETED
    # COMPLETED 是终态。
    with pytest.raises(IllegalStateTransitionError):
        engine.transition("task-geo-001", ConditionalTaskState.READY)
