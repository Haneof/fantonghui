"""M2-005R 验收单测：条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

法务总监实战情境：200 项跨周期条件任务挂载，四大硬门禁逐一断言。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.scheduler.conditional_engine import (
    BiometricThresholdCondition,
    ConditionalSchedulerEngine,
    GeoPresenceCondition,
    IllegalStateTransitionError,
    SchedulerStage,
    SemanticContextCondition,
    TimeArrivalCondition,
)

UTC = timezone.utc
T0 = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)  # 早晨 8 点（UTC+8 视为上海 16:00 前，仅测试口径）


def evening_of(day_offset: int) -> datetime:
    """构造“晚间心率”样本时刻：UTC 21:30，落在引擎晚间窗口 19~23。"""
    return T0 + timedelta(days=day_offset, hours=13, minutes=30)


@pytest.fixture()
def engine() -> ConditionalSchedulerEngine:
    eng = ConditionalSchedulerEngine()
    # —— 情境 1：股权变更提醒（纯语义，只能被捎带）——
    eng.register_task(
        task_id="tsk_equity_watch",
        title="诉讼对方实控人出现股权变更时提醒",
        conditions=[
            SemanticContextCondition(
                description="外部工商信号语义核验",
                required_tags=frozenset({"股权", "工商信号"}),
                needs_physical_gate=False,
            )
        ],
    )
    # —— 情境 2：连续 3 天晚间心率 >95 → 心内科预约建档 ——
    eng.register_task(
        task_id="tsk_cardiology",
        title="连续3天晚间心率超95启动心内科预约建档",
        conditions=[
            BiometricThresholdCondition(
                metric="heart_rate",
                comparator="gt",
                value=95.0,
                consecutive_days=3,
                evening_only=True,
            )
        ],
    )
    # —— 情境 3：回到上海办公室 + 非深度专注 + 语义时机 → 签署对赌回购协议 ——
    eng.register_task(
        task_id="tsk_vam_sign",
        title="在沪且非深度专注时提示签署对赌回购协议",
        conditions=[
            GeoPresenceCondition(place_id="sh_office", exclude_activity="deep_focus"),
            SemanticContextCondition(
                description="协议已送达且双方在场",
                required_tags=frozenset({"对赌", "签约窗口"}),
                needs_physical_gate=True,
            ),
        ],
    )
    return eng


# ---------------------------------------------------------------------------
# 门禁一：未成熟任务 Token 严格为 0（物理隐形）
# ---------------------------------------------------------------------------


def test_dormant_tasks_are_physically_invisible_and_cost_zero_tokens(engine):
    board = engine.board_snapshot(now=T0)
    assert board["items"] == []
    assert board["dormant_count"] == 3
    prompt = engine.render_llm_prompt_context(now=T0)
    assert prompt == ""
    assert engine.prompt_token_total == 0
    for task_id in ("tsk_equity_watch", "tsk_cardiology", "tsk_vam_sign"):
        assert engine.dormant_task_token_cost(task_id) == 0
        assert engine.dormant_token_contributions[task_id] == 0
    # 200 任务压力下的同一断言
    bulk = ConditionalSchedulerEngine()
    for i in range(200):
        bulk.register_task(
            task_id=f"tsk_{i}",
            title=f"未成熟法务任务 {i}（绝不可灌入 Prompt）",
            conditions=[TimeArrivalCondition(due_at=T0 + timedelta(days=365 + i))],
        )
    prompt_bulk = bulk.render_llm_prompt_context(now=T0)
    assert prompt_bulk == ""
    assert bulk.prompt_token_total == 0
    assert all(v == 0 for v in bulk.dormant_token_contributions.values())


def test_promoted_tasks_are_the_only_visible_lines(engine):
    for day in range(3):
        engine.feed_biometric(metric="heart_rate", value=99.0, at=evening_of(day))
    assert engine.stage_of("tsk_cardiology") is SchedulerStage.READY
    prompt = engine.render_llm_prompt_context()
    assert "心内科" in prompt
    assert "股权变更" not in prompt
    assert "对赌回购协议" not in prompt
    board = engine.board_snapshot()
    ids = {item["task_id"] for item in board["items"]}
    assert ids == {"tsk_cardiology"}


# ---------------------------------------------------------------------------
# 门禁二：Level-1 机械快轨 0 Token / 亚毫秒判定 / 自动跃迁 READY
# ---------------------------------------------------------------------------


def test_level1_mechanical_track_uses_zero_llm_and_fires_on_third_evening():
    eng = ConditionalSchedulerEngine()
    eng.register_task(
        task_id="tsk_hr",
        title="心率阈值",
        conditions=[
            BiometricThresholdCondition(
                metric="heart_rate",
                comparator="gt",
                value=95.0,
                consecutive_days=3,
                evening_only=True,
            )
        ],
    )
    fired = eng.feed_biometric(metric="heart_rate", value=99.0, at=evening_of(0))
    assert fired == []
    assert eng.llm_calls == 0
    fired = eng.feed_biometric(metric="heart_rate", value=97.0, at=evening_of(1))
    assert fired == []
    fired = eng.feed_biometric(metric="heart_rate", value=96.0, at=evening_of(2))
    assert fired == ["tsk_hr"]
    assert eng.stage_of("tsk_hr") is SchedulerStage.READY
    record = eng._records["tsk_hr"]
    assert record.promoted_via == "level1_mechanical"
    assert eng.llm_calls == 0  # 全程 0 大模型调用


def test_daytime_samples_do_not_satisfy_evening_only_rule():
    eng = ConditionalSchedulerEngine()
    eng.register_task(
        task_id="tsk_hr",
        title="心率阈值",
        conditions=[
            BiometricThresholdCondition(
                metric="heart_rate", comparator="gt", value=95.0,
                consecutive_days=3, evening_only=True,
            )
        ],
    )
    for day in range(3):
        eng.feed_biometric(metric="heart_rate", value=120.0, at=T0 + timedelta(days=day, hours=2))
    assert eng.stage_of("tsk_hr") is SchedulerStage.DORMANT


def test_level1_tick_is_sub_millisecond_over_two_hundred_tasks():
    eng = ConditionalSchedulerEngine()
    for i in range(200):
        eng.register_task(
            task_id=f"tsk_{i}",
            title=f"任务 {i}",
            conditions=[TimeArrivalCondition(due_at=T0 + timedelta(minutes=i))],
        )
    now = T0 + timedelta(minutes=150)  # 前 151 个任务已到期
    started = time.perf_counter()
    promoted = eng.tick(now)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert len(promoted) == 151
    # 工单口径：底层调度器对全部挂载任务做纯 Python 判定须亚毫秒级完成；
    # 宽松执行余量防 CI 噪声，但均摊必须严格 < 1ms/任务。
    assert elapsed_ms < 50.0
    assert elapsed_ms / max(1, len(eng._records)) < 1.0
    assert eng.llm_calls == 0
    # 无到期命中的空拍必须极廉价
    started = time.perf_counter()
    eng.tick(now + timedelta(microseconds=1))
    assert (time.perf_counter() - started) * 1000.0 < 1.0


def test_geo_fence_level1_transition(engine):
    fired = engine.feed_presence(place_id="sh_office", present=True, activity="meeting", at=T0)
    assert fired == []  # tsk_vam_sign 是复合 Level-2：机械信号不得代答
    engine.register_task(
        task_id="tsk_pure_geo",
        title="纯地理围栏任务",
        conditions=[GeoPresenceCondition(place_id="sh_office")],
    )
    fired = engine.feed_presence(place_id="sh_office", present=True, activity="normal", at=T0 + timedelta(seconds=1))
    assert fired == ["tsk_pure_geo"]
    assert engine.stage_of("tsk_pure_geo") is SchedulerStage.READY
    assert engine.llm_calls == 0


# ---------------------------------------------------------------------------
# 门禁三：Level-2 机会式捎带
# ---------------------------------------------------------------------------


def test_level2_never_wakes_llm_without_user_wake(engine):
    for day in range(3):
        engine.feed_biometric(metric="heart_rate", value=99.0, at=evening_of(day))
    engine.tick(T0 + timedelta(days=9))
    assert engine.llm_calls == 0  # 用户从未唤醒 → 语义任务零打扰
    assert engine.stage_of("tsk_equity_watch") is SchedulerStage.DORMANT


def test_level2_piggyback_evaluates_once_per_wake_and_only_on_tag_match(engine):
    calls: list[str] = []
    approved = {"tsk_equity_watch"}

    def evaluator(record, scene):
        calls.append(record.task_id)
        return record.task_id in approved

    # 场景标签不命中 → 不评估
    engine.on_user_wake(now=T0, scene_tags=["午饭"], semantic_evaluator=evaluator)
    assert calls == []
    assert engine.llm_calls == 0

    # 标签命中 → 恰好每任务 1 次评估
    promoted = engine.on_user_wake(
        now=T0 + timedelta(minutes=1), scene_tags=["股权", "工商信号"], semantic_evaluator=evaluator
    )
    assert promoted == ["tsk_equity_watch"]
    assert calls == ["tsk_equity_watch"]
    assert engine.llm_calls == 1
    assert engine.stage_of("tsk_equity_watch") is SchedulerStage.READY
    assert engine._records["tsk_equity_watch"].promoted_via == "level2_piggyback"

    # 无评估器注入 → 引擎绝不自主调用模型
    engine.on_user_wake(now=T0 + timedelta(minutes=2), scene_tags=["对赌", "签约窗口"], semantic_evaluator=None)
    assert engine.llm_calls == 1

    # 复合任务：物理前提（在场且非深度专注）未满足 → 连评估机会都不给
    calls.clear()
    engine.on_user_wake(now=T0 + timedelta(minutes=3), scene_tags=["对赌", "签约窗口"], semantic_evaluator=evaluator)
    assert calls == []
    engine.feed_presence(place_id="sh_office", present=True, activity="deep_focus", at=T0 + timedelta(minutes=4))
    engine.on_user_wake(now=T0 + timedelta(minutes=5), scene_tags=["对赌", "签约窗口"], semantic_evaluator=evaluator)
    assert calls == []  # 深度专注被排除
    engine.feed_presence(place_id="sh_office", present=True, activity="normal", at=T0 + timedelta(minutes=6))
    approved.add("tsk_vam_sign")
    promoted = engine.on_user_wake(
        now=T0 + timedelta(minutes=7),
        scene_tags=["对赌", "签约窗口"],
        semantic_evaluator=evaluator,
    )
    assert promoted == ["tsk_vam_sign"]
    assert calls == ["tsk_vam_sign"]
    assert engine.llm_calls == 2


def test_same_wake_never_double_evaluates_one_task():
    eng = ConditionalSchedulerEngine()
    eng.register_task(
        task_id="tsk_x",
        title="语义任务",
        conditions=[
            SemanticContextCondition(
                description="d", required_tags=frozenset({"t"}), needs_physical_gate=False
            )
        ],
    )

    seen: list[str] = []

    def evaluator(record, scene):
        seen.append(record.task_id)
        return False  # 否决 → 保持 DORMANT，下次唤醒可再评估

    eng.on_user_wake(now=T0, scene_tags=["t"], semantic_evaluator=evaluator)
    assert seen == ["tsk_x"]
    eng.on_user_wake(now=T0 + timedelta(seconds=1), scene_tags=["t"], semantic_evaluator=evaluator)
    assert seen == ["tsk_x", "tsk_x"]  # 新唤醒重新计票：每次唤醒至多 1 次


# ---------------------------------------------------------------------------
# 门禁四：状态机非法跃迁 100% 拦截
# ---------------------------------------------------------------------------


def test_illegal_transitions_are_100_percent_blocked(engine):
    with pytest.raises(IllegalStateTransitionError, match=r"dormant -> running"):
        engine.start("tsk_equity_watch")  # 未就绪直接触发执行 → 当场拒绝
    with pytest.raises(IllegalStateTransitionError):
        engine.complete("tsk_cardiology")  # DORMANT -> COMPLETED
    assert engine.stats()["stage_dormant"] == 3
    assert engine.illegal_transition_attempts == 2

    # 合法链路畅通
    for day in range(3):
        engine.feed_biometric(metric="heart_rate", value=99.0, at=evening_of(day))
    assert engine.stage_of("tsk_cardiology") is SchedulerStage.READY
    with pytest.raises(IllegalStateTransitionError):
        engine.complete("tsk_cardiology")  # READY 跳过 RUNNING 也不许
    engine.start("tsk_cardiology")
    assert engine.stage_of("tsk_cardiology") is SchedulerStage.RUNNING
    with pytest.raises(IllegalStateTransitionError):
        engine.start("tsk_cardiology")  # RUNNING 重复 start
    engine.complete("tsk_cardiology")
    assert engine.stage_of("tsk_cardiology") is SchedulerStage.COMPLETED
    with pytest.raises(IllegalStateTransitionError):
        engine.start("tsk_cardiology")  # 终态不许复活

    log = engine.transition_log  # (task_id, from, to, at)
    assert [(entry[1], entry[2]) for entry in log] == [
        ("dormant", "ready"),
        ("ready", "running"),
        ("running", "completed"),
    ]
