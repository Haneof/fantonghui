"""M2-005R 条件驱动任务调度双轨引擎 · 四大硬门禁验收。

实战情境：创业企业法务总监挂载 200 项跨周期条件任务。门禁：
1. DORMANT 任务看板组装 Token 严格为 0（物理隐形，严禁灌入 LLM Prompt）；
2. Level-1 机械快轨：<1ms 纯 Python 判定，LLM 调用严格 0，直接跃迁 READY；
3. Level-2 机会式捎带：只在用户主动唤醒且场景相交时顺路评估，绝不主动唤醒；
4. 非法跃迁 100% 抛出 IllegalStateTransitionError。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.scheduler.conditional_engine_arena01 import (
    BoardAssembly,
    ConditionalTask,
    ConditionalTaskState,
    DualTrackScheduler,
    IllegalStateTransitionError,
    MechanicalCondition,
    MechanicalConditionKind,
    SensorSnapshot,
    SemanticRequirement,
    UserWakeEvent,
)

NOW = datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)
SHANGHAI_OFFICE = (31.2304, 121.4737)  # 上海办公室地理围栏圆心


def _task_time(task_id: str, days: int, hours: int = 0) -> ConditionalTask:
    return ConditionalTask(
        task_id=task_id,
        title=f"[{task_id}] 《对赌回购协议》第 {days} 号补充条款复核截止",
        detail=f"法务高频事项：{task_id} 的机械时间锚点绝对到期必须自动就绪",
        mechanical=MechanicalCondition(
            kind=MechanicalConditionKind.TIME_ABSOLUTE,
            due_at=NOW + timedelta(days=days, hours=hours),
        ),
        priority=60,
    )


def _task_geo(task_id: str) -> ConditionalTask:
    return ConditionalTask(
        task_id=task_id,
        title="回到上海办公室且非深度专注时提示签署对赌回购协议",
        detail="地理围栏触发后由办公室交互窗口承接",
        mechanical=MechanicalCondition(
            kind=MechanicalConditionKind.GEO_FENCE_ENTER,
            center_lat=SHANGHAI_OFFICE[0],
            center_lon=SHANGHAI_OFFICE[1],
            radius_m=300.0,
        ),
        priority=80,
    )


def _task_hr(task_id: str, threshold: float = 95.0) -> ConditionalTask:
    return ConditionalTask(
        task_id=task_id,
        title="晚间心率超阈值即启动心内科预约建档",
        detail=f"心率 >= {threshold}bpm 的客观阈值条件",
        mechanical=MechanicalCondition(
            kind=MechanicalConditionKind.HEART_RATE_THRESHOLD,
            metric="heart_rate",
            threshold=threshold,
            comparator=">=",
        ),
        priority=90,
    )


def _task_semantic(task_id: str, tags: tuple[str, ...]) -> ConditionalTask:
    return ConditionalTask(
        task_id=task_id,
        title="当诉讼对方实控人出现股权变更时提醒",
        detail=f"依赖语义环境的重估条件（场景标签 {tags}）",
        semantic=SemanticRequirement(
            scene_tags=tags,
            prompt_template=f"结合当前对话语境评估 {task_id} 是否已实质发生",
        ),
        priority=70,
    )


def build_legal_director_world() -> tuple[DualTrackScheduler, dict[str, list[str]]]:
    """200 项跨周期条件任务：100 时间 / 40 地理 / 30 心率 / 30 语义。"""
    scheduler = DualTrackScheduler(semantic_evaluator=lambda task, wake: "股权变更" in wake.text)
    ids = {"time": [], "geo": [], "hr": [], "semantic": []}
    for i in range(100):
        tid = f"time-clause-{i:03d}"
        scheduler.register_task(_task_time(tid, days=i % 30, hours=i % 24))
        ids["time"].append(tid)
    for i in range(40):
        tid = f"geo-office-{i:03d}"
        scheduler.register_task(_task_geo(tid))
        ids["geo"].append(tid)
    for i in range(30):
        tid = f"hr-cardio-{i:03d}"
        scheduler.register_task(_task_hr(tid, threshold=95.0 + i % 5))
        ids["hr"].append(tid)
    for i in range(30):
        tid = f"sem-litigation-{i:03d}"
        scheduler.register_task(_task_semantic(tid, ("诉讼", "股权", f"案件-{i % 6}")))
        ids["semantic"].append(tid)
    return scheduler, ids


# ===========================================================================
# 门禁 1：DORMANT 任务 Token 严格为 0（看板绝对物理隐形）
# ===========================================================================


def test_gate1_dormant_tasks_are_physically_invisible_with_zero_tokens() -> None:
    scheduler, ids = build_legal_director_world()
    board = scheduler.assemble_board(NOW)

    # 200 项任务全在休眠：看板应当只剩骨架，任何休眠任务文本严格缺席。
    assert board.hidden_dormant_count == 200
    assert board.included_task_ids == ()
    assert board.dormant_token_charge == 0
    for group in ids.values():
        for tid in group:
            assert tid not in board.prompt_text
    assert "对赌回购" not in board.prompt_text
    assert "心内科" not in board.prompt_text
    # 骨架行（时间戳行）之外零内容：Token 消耗与任务规模彻底解耦。
    assert board.prompt_text.count("\n") == 0

    # 部分任务就绪后再组装：隐形依然逐字成立。
    scheduler.force_state(ids["time"][0], ConditionalTaskState.READY, at=NOW)
    scheduler.force_state(ids["hr"][0], ConditionalTaskState.READY, at=NOW)
    board2 = scheduler.assemble_board(NOW)
    assert board2.hidden_dormant_count == 198
    assert board2.dormant_token_charge == 0
    assert set(board2.included_task_ids) == {ids["time"][0], ids["hr"][0]}
    for tid in ids["time"][1:] + ids["geo"] + ids["hr"][1:] + ids["semantic"]:
        assert tid not in board2.prompt_text
    assert ids["time"][0] in board2.prompt_text or "对赌回购" in board2.prompt_text


def test_gate1_assembly_tokens_scale_only_with_visible_tasks() -> None:
    scheduler, ids = build_legal_director_world()
    empty = scheduler.assemble_board(NOW)
    for k in range(10):
        scheduler.force_state(ids["time"][k], ConditionalTaskState.READY, at=NOW)
    board = scheduler.assemble_board(NOW, max_items=8)
    # max_items 截断：看板只装 8 项，Token 不随就绪总数无界膨胀。
    assert len(board.included_task_ids) == 8
    assert board.hidden_dormant_count == 190
    # 10 项就绪仅 8 项入看板：第 9、10 项文本同样不可见。
    assert ids["time"][8] not in board.prompt_text
    assert ids["time"][9] not in board.prompt_text
    assert board.estimated_prompt_tokens > 0
    assert empty.estimated_prompt_tokens >= 0


# ===========================================================================
# 门禁 2：Level-1 机械快轨 <1ms 纯 Python，LLM 调用严格 0
# ===========================================================================


def test_gate2_mechanical_fast_track_zero_llm_and_auto_ready() -> None:
    scheduler, ids = build_legal_director_world()
    stats_before = scheduler.stats

    # 轴前：所有任务休眠。
    assert scheduler.tick(NOW - timedelta(days=1)) == []

    # 纯时间绝对到期：第 0 批（days=0 且 hours 已过的 subset）直接就绪。
    early_fired = scheduler.tick(NOW + timedelta(hours=23))
    assert early_fired == sorted(early_fired)
    assert early_fired  # days=0 的若干项已到期
    for tid in early_fired:
        assert scheduler.state_of(tid) is ConditionalTaskState.READY

    # 地理围栏进入上海办公室 300m。
    geo_fired = scheduler.tick(
        NOW, SensorSnapshot(lat=31.2307, lon=121.4738)
    )
    assert set(ids["geo"]) <= set(geo_fired + [t for t in ids["geo"] if scheduler.state_of(t) is ConditionalTaskState.READY])
    for tid in ids["geo"]:
        assert scheduler.state_of(tid) is ConditionalTaskState.READY
    # 人在外高桥保税区（>10km 外）：新引擎复查不触发。
    far = DualTrackScheduler()
    far.register_task(_task_geo("geo-far-check"))
    assert far.tick(NOW, SensorSnapshot(lat=31.34, lon=121.59)) == []
    # 心率 96bpm 超标。
    hr_fired = scheduler.tick(NOW, SensorSnapshot(metrics={"heart_rate": 96.0}))
    hr_ready = [t for t in ids["hr"] if scheduler.state_of(t) is ConditionalTaskState.READY]
    assert hr_ready  # 阈值 <= 96 的全部就绪
    for tid in hr_fired:
        assert tid in ids["hr"]

    stats_after = scheduler.stats
    # 机械快轨全程：大模型调用严格 0、捎带评估严格 0。
    assert stats_after["llm_calls"] == 0
    assert stats_after["piggyback_evals"] == 0
    assert stats_after["mechanical_evals"] > stats_before["mechanical_evals"]
    assert stats_after["mechanical_hits"] >= len(set(early_fired + geo_fired + hr_fired))


def test_gate2_mechanical_eval_under_1ms_wall_budget() -> None:
    scheduler, _ = build_legal_director_world()
    avg_ms = scheduler.measure_mechanical_eval_ms(samples=20)
    # 单次客观条件评估硬预算：严格小于 1ms（实际为微秒级）。
    assert avg_ms < 1.0, f"mechanical eval {avg_ms:.4f}ms exceeds 1ms budget"

    # 200 任务整轮 tick 的墙钟上界同样收敛（宽松阈值防 CI 抖动）。
    started = time.perf_counter()
    scheduler.tick(NOW + timedelta(days=31), SensorSnapshot(lat=31.23, lon=121.47, metrics={"heart_rate": 97.0}))
    assert (time.perf_counter() - started) < 0.5
    assert scheduler.stats["llm_calls"] == 0


# ===========================================================================
# 门禁 3：Level-2 机会式捎带——绝不主动唤醒大模型
# ===========================================================================


def test_gate3_semantic_tasks_never_self_wake_llm() -> None:
    evaluator_calls: list[str] = []

    def evaluator(task: ConditionalTask, wake: UserWakeEvent) -> bool:
        evaluator_calls.append(task.task_id)
        return "股权变更" in wake.text

    scheduler = DualTrackScheduler(semantic_evaluator=evaluator)
    for i in range(30):
        scheduler.register_task(_task_semantic(f"sem-{i:02d}", ("诉讼", f"案件-{i % 5}")))

    # 无人唤醒的 30 天：机械 tick 狂奔 10,000 次，语义任务依旧全部休眠。
    for day in range(30):
        for hour in range(24):
            scheduler.tick(NOW + timedelta(days=day, hours=hour))
    assert len(evaluator_calls) == 0
    assert scheduler.tasks_in(ConditionalTaskState.DORMANT) == tuple(f"sem-{i:02d}" for i in range(30))
    assert scheduler.stats["llm_calls"] == 0
    assert scheduler.stats["piggyback_evals"] == 0

    # 用户主动唤醒但场景不相交（聊午饭吃什么）：依然零评估。
    scheduler.piggyback_on_user_wake(
        UserWakeEvent(occurred_at=NOW, scene_tags=("餐饮", "闲聊"), text="中午吃什么")
    )
    assert len(evaluator_calls) == 0
    assert scheduler.stats["piggyback_evals"] == 0

    # 用户主动唤醒且任务要求场景被完整覆盖：仅该子集被捎带评估。
    fired = scheduler.piggyback_on_user_wake(
        UserWakeEvent(occurred_at=NOW, scene_tags=("诉讼", "案件-2"), text="对方实控人刚完成股权变更，注意"),
    )
    assert len(fired) == 6  # 恰为请求标签被覆盖的 案件-2 案件组（i%5==2）
    assert len(evaluator_calls) == 6  # 场景预筛：绝不全量评估
    assert len(evaluator_calls) == scheduler.stats["llm_calls"] > 0
    for tid in fired:
        assert scheduler.state_of(tid) is ConditionalTaskState.READY

    # 捎带后看板可见且休眠计数下降。
    board = scheduler.assemble_board(NOW)
    assert board.hidden_dormant_count == 30 - len(fired)


def test_gate3_no_evaluator_is_fail_closed() -> None:
    scheduler = DualTrackScheduler()  # 未注入语义评估器
    scheduler.register_task(_task_semantic("sem-x", ("诉讼",)))
    fired = scheduler.piggyback_on_user_wake(
        UserWakeEvent(occurred_at=NOW, scene_tags=("诉讼",), text="股权变更已发生")
    )
    # 语义预筛命中但无评估器：保持休眠，绝不臆断就绪、绝不消耗 LLM。
    assert fired == []
    assert scheduler.state_of("sem-x") is ConditionalTaskState.DORMANT
    assert scheduler.stats["llm_calls"] == 0
    assert scheduler.stats["piggyback_evals"] == 1  # 预筛通过但评估被安全跳过


# ===========================================================================
# 门禁 4：非法跃迁 100% 拦截
# ===========================================================================


def test_gate4_illegal_transitions_100_percent_blocked() -> None:
    scheduler, ids = build_legal_director_world()
    tid = ids["time"][0]

    # DORMANT 直接执行/收官/跳 RUNNING/COMPLETED：一律物理拦截。
    for attempt in (
        lambda: scheduler.execute(tid),
        lambda: scheduler.complete(tid),
        lambda: scheduler.force_state(tid, ConditionalTaskState.COMPLETED),
        lambda: scheduler.force_state(tid, ConditionalTaskState.RUNNING),
    ):
        with pytest.raises(IllegalStateTransitionError):
            attempt()
        assert scheduler.state_of(tid) is ConditionalTaskState.DORMANT

    blocked_before = scheduler.stats["illegal_transition_blocked"]
    # 法定路径：DORMANT→READY→RUNNING→COMPLETED 畅通。
    scheduler.force_state(tid, ConditionalTaskState.READY)
    scheduler.execute(tid)
    assert scheduler.state_of(tid) is ConditionalTaskState.RUNNING
    scheduler.complete(tid)
    assert scheduler.state_of(tid) is ConditionalTaskState.COMPLETED
    assert scheduler.stats["illegal_transition_blocked"] == blocked_before

    # 终态之后任何流转、READY 回退 DORMANT、跨级回退均拦截。
    with pytest.raises(IllegalStateTransitionError):
        scheduler.complete(tid)
    tid2 = ids["time"][1]
    scheduler.force_state(tid2, ConditionalTaskState.READY)
    with pytest.raises(IllegalStateTransitionError):
        scheduler.force_state(tid2, ConditionalTaskState.DORMANT)  # READY→DORMANT 回退非法
    with pytest.raises(IllegalStateTransitionError):
        scheduler.force_state(tid2, ConditionalTaskState.COMPLETED)  # READY→COMPLETED 跨级非法
    assert scheduler.state_of(tid2) is ConditionalTaskState.READY


def test_gate4_execute_requires_ready_cannot_fire_from_dormant() -> None:
    """业务直读：DORMANT 的签署提醒绝不能绕过快轨直接触发执行。"""
    scheduler = DualTrackScheduler()
    scheduler.register_task(_task_geo("sign-vam-repurchase"))
    with pytest.raises(IllegalStateTransitionError, match="illegal transition"):
        scheduler.execute("sign-vam-repurchase")
    # 快轨自然命中后即可执行。
    scheduler.tick(NOW, SensorSnapshot(lat=SHANGHAI_OFFICE[0], lon=SHANGHAI_OFFICE[1]))
    scheduler.execute("sign-vam-repurchase", at=NOW)
    scheduler.complete("sign-vam-repurchase", at=NOW)
    assert scheduler.state_of("sign-vam-repurchase") is ConditionalTaskState.COMPLETED


# ===========================================================================
# 综合：200 任务全生命周期 + 审计不变量
# ===========================================================================


def test_full_lifecycle_200_tasks_stats_invariants() -> None:
    scheduler, ids = build_legal_director_world()
    # 第 40 天：全部时间任务到期；地理/心率由快照命中。
    for day in range(40):
        scheduler.tick(NOW + timedelta(days=day), SensorSnapshot(
            lat=SHANGHAI_OFFICE[0] if day == 20 else None,
            lon=SHANGHAI_OFFICE[1] if day == 20 else None,
            metrics={"heart_rate": 100.0} if day == 21 else {},
        ))
    board = scheduler.assemble_board(NOW + timedelta(days=40))
    stats = scheduler.stats
    assert stats["registered"] == 200
    assert stats["llm_calls"] == 0
    assert stats["dormant_token_charge_total"] == 0
    assert board.hidden_dormant_count == 30  # 只剩 30 项语义任务仍休眠
    assert len(scheduler.tasks_in(ConditionalTaskState.READY)) == 170
    # 就绪任务执行一半后，看板包含 RUNNING 与 READY 双态。
    for tid in scheduler.tasks_in(ConditionalTaskState.READY)[:40]:
        scheduler.execute(tid)
    board2 = scheduler.assemble_board(NOW + timedelta(days=40))
    assert "▶" in board2.prompt_text and "◆" in board2.prompt_text
    assert board2.dormant_token_charge == 0
