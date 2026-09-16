"""M2-001 验收测试：高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

工单：``arena/agent-wake-m2-001``
实现：``src/aios_core/wake/cooldown_queue.py``

实战情境
--------------------------------------------------------------------------
手环佩戴者白天打羽毛球，赛后心率剧烈波动、加速度传感器 50Hz 持续产生离散数据；
夜间 02:00~06:00 进入 Deep Sleep 阶段。

四大硬门禁 ↔ 用例
--------------------------------------------------------------------------
1. 5 秒 250 条脉冲 -> 单批次  —— ``test_gate1_*``
2. 15~30 分钟自适应冷却硬防护 —— ``test_gate2_*``
3. 深睡绝对静默（除 P0 外马达 0 次）—— ``test_gate3_*``
4. 静默队列无损解冻与有序聚合 —— ``test_gate4_*``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.safety_bypass import WakePriority
from aios_core.wake.cooldown_queue import (
    COOLDOWN_MAX_MINUTES,
    COOLDOWN_MIN_MINUTES,
    MERGE_WINDOW_SECONDS,
    CooldownGate,
    CooldownPolicy,
    DeepSleepGate,
    GateVerdict,
    Notification,
    NotificationKind,
    PhysiologicalPulse,
    PhysiologyState,
    PulseKind,
    PulseMergeWindow,
    SilentQueue,
    WakeCooldownQueue,
)

# ---------------------------------------------------------------------------
# 基线与场景常量
# ---------------------------------------------------------------------------

T_AFTER_BADMINTON = datetime(2026, 9, 16, 20, 30, tzinfo=timezone.utc)
T_SLEEP_START = datetime(2026, 9, 17, 2, 0, tzinfo=timezone.utc)
T_SLEEP_MIDDLE = T_SLEEP_START + timedelta(hours=2)
T_MORNING = datetime(2026, 9, 17, 6, 40, tzinfo=timezone.utc)

PULSE_TOTAL = 250
DUPLICATED_PULSES = 40
ACCEL_SAMPLES = 200
HEART_BEATS = 50

GENERAL_NOTIFICATIONS = 20
REVIEW_NOTIFICATIONS = 5
TASK_NOTIFICATIONS = 3
SILENCED_TOTAL = GENERAL_NOTIFICATIONS + REVIEW_NOTIFICATIONS + TASK_NOTIFICATIONS


def _badminton_aftermath_pulses() -> tuple[PhysiologicalPulse, ...]:
    """羽毛球赛后的 5 秒现实：50Hz 加速度 + 逐拍心率，且含真实存在的重复上报。

    真实设备在弱信号/补传时会重复上报同一量化值——这正是"去重"要处理的物理事实。
    """
    pulses: list[PhysiologicalPulse] = []
    # 200 条加速度采样：50Hz × 4s，波形连续变化（真实 IMU 不会只有几个离散值），
    # 其中每 5 条有 1 条是"与上一条完全相同的补传重复上报" -> 去重必须命中 40 次。
    previous_value: float | None = None
    for index in range(ACCEL_SAMPLES):
        # 连续爬升的冲击波形（相邻样本差 > 0.001，保证 3 位量化下仍两两不同）
        value = round(0.8 + index * 0.008534, 4)
        if index % 5 == 4 and previous_value is not None:
            value = previous_value  # 完全相同的量化值 -> 判定为同一次物理事件的重复上报
        pulses.append(
            PhysiologicalPulse(
                pulse_id=f"acc_{index:04d}",
                captured_at=T_AFTER_BADMINTON + timedelta(seconds=index * 0.02),
                kind=PulseKind.ACCELERATION,
                value=value,
                unit="g",
                source="band_imu",
            )
        )
        previous_value = value
    # 50 条逐拍心率（1Hz 采样）：运动后心率连续波动
    for index in range(HEART_BEATS):
        pulses.append(
            PhysiologicalPulse(
                pulse_id=f"hr_{index:04d}",
                captured_at=T_AFTER_BADMINTON + timedelta(seconds=index * 0.1),
                kind=PulseKind.HEART_RATE,
                value=round(178.0 - index * 0.21, 2),  # 赛后心率缓降
                unit="bpm",
                source="band_ppg",
            )
        )
    assert len(pulses) == PULSE_TOTAL
    return tuple(pulses)


def _notification(
    index: int,
    kind: NotificationKind,
    *,
    priority: WakePriority = WakePriority.P2_NORMAL_INTERACT,
    digest: str = "g",
) -> Notification:
    return Notification(
        notification_id=f"ntf_{kind.value}_{digest}_{index:03d}",
        kind=kind,
        title=f"{kind.value} 提醒 #{index:03d}",
        priority=priority,
        created_at=T_SLEEP_START + timedelta(minutes=index),
    )


def _p0_cardiac_fall() -> Notification:
    return Notification(
        notification_id="ntf_p0_cardiac_fall_001",
        kind=NotificationKind.SAFETY_P0,
        title="检测到心梗跌倒：硬件直穿紧急求救",
        priority=WakePriority.P0_CRITICAL_SAFETY,
        created_at=T_SLEEP_MIDDLE,
        motor_vibration=False,
    )


def _deep_sleep_state() -> PhysiologyState:
    return PhysiologyState(
        captured_at=T_SLEEP_MIDDLE, deep_sleep=True, asleep=True, in_bed=True
    )


def _morning_state() -> PhysiologyState:
    return PhysiologyState(captured_at=T_MORNING, deep_sleep=False, asleep=False, in_bed=False)


# ===========================================================================
# 硬门禁 1：5 秒 250 条脉冲 -> 单批次（防抖合并 + 去重）
# ===========================================================================


def test_gate1_250_pulses_in_five_seconds_collapse_into_one_batch() -> None:
    window = PulseMergeWindow(window_seconds=MERGE_WINDOW_SECONDS)
    batches = [
        batch
        for batch in (window.ingest(pulse) for pulse in _badminton_aftermath_pulses())
        if batch is not None
    ]
    final = window.flush(T_AFTER_BADMINTON + timedelta(seconds=5))
    assert final is not None
    batches.append(final)

    assert len(batches) == 1, "5 秒窗口内的 250 条脉冲必须合并为 1 条批次事件"
    assert window.downstream_wake_count == 1, "下游心智流水线只允许被唤醒 1 次"
    assert window.total_ingested == PULSE_TOTAL
    batch = batches[0]
    assert batch.deduped_count == DUPLICATED_PULSES
    assert batch.pulse_count == PULSE_TOTAL - DUPLICATED_PULSES


def test_gate1_aggregation_preserves_extremes_and_channels() -> None:
    window = PulseMergeWindow()
    for pulse in _badminton_aftermath_pulses():
        window.ingest(pulse)
    batch = window.flush(T_AFTER_BADMINTON + timedelta(seconds=5))
    assert batch is not None

    assert set(batch.aggregated) == {PulseKind.ACCELERATION.value, PulseKind.HEART_RATE.value}
    accel = batch.aggregated[PulseKind.ACCELERATION.value]
    heart = batch.aggregated[PulseKind.HEART_RATE.value]

    assert accel.count + heart.count == PULSE_TOTAL - DUPLICATED_PULSES
    assert accel.maximum == max(
        p.value for p in _badminton_aftermath_pulses() if p.kind is PulseKind.ACCELERATION
    )
    assert accel.minimum <= accel.mean <= accel.maximum
    assert heart.maximum >= 178.0 and heart.unit == "bpm"
    assert batch.distinct_sources == 2
    assert batch.critical_hint is False, "赛后心率 178bpm 未达极高危阈值 180"


def test_gate1_naive_per_pulse_wakeup_is_288x_more_expensive() -> None:
    window = PulseMergeWindow()
    for pulse in _badminton_aftermath_pulses():
        window.ingest(pulse)
    window.flush(T_AFTER_BADMINTON + timedelta(seconds=5))

    naive_downstream_wakes = PULSE_TOTAL
    assert window.downstream_wake_count == 1
    assert naive_downstream_wakes / window.downstream_wake_count >= 250, (
        "合并收益必须至少 250 倍（逐条唤醒 = 250 次，合并后 = 1 次）"
    )
    assert window.batches_emitted == 1
    assert window.total_deduped == DUPLICATED_PULSES


def test_gate1_window_boundary_opens_a_new_batch() -> None:
    """跨窗口的脉冲必须开新批次，绝不无限堆积（窗口纪律）。"""
    window = PulseMergeWindow(window_seconds=5.0)
    first = window.ingest(
        PhysiologicalPulse(
            pulse_id="p0",
            captured_at=T_AFTER_BADMINTON,
            kind=PulseKind.HEART_RATE,
            value=150.0,
            unit="bpm",
        )
    )
    assert first is None
    boundary = window.ingest(
        PhysiologicalPulse(
            pulse_id="p1",
            captured_at=T_AFTER_BADMINTON + timedelta(seconds=5.001),
            kind=PulseKind.HEART_RATE,
            value=151.0,
            unit="bpm",
        )
    )
    assert boundary is not None, "超过 5 秒必须吐出一批"
    assert boundary.pulse_count == 1 and window.pending_count == 1


def test_gate1_duplicate_pulses_do_not_inflate_the_batch() -> None:
    """同一物理事实重复上报 10 次，批次里只能算 1 条。"""
    window = PulseMergeWindow()
    for repeat in range(10):
        window.ingest(
            PhysiologicalPulse(
                pulse_id=f"dup_{repeat}",
                captured_at=T_AFTER_BADMINTON + timedelta(milliseconds=repeat * 10),
                kind=PulseKind.SPO2,
                value=97.0,
                unit="%",
                source="band_spo2",
            )
        )
    batch = window.flush(T_AFTER_BADMINTON + timedelta(seconds=1))
    assert batch is not None
    assert batch.pulse_count == 1
    assert window.total_deduped == 9
    assert batch.aggregated[PulseKind.SPO2.value].count == 1


# ===========================================================================
# 硬门禁 2：15~30 分钟自适应冷却硬防护
# ===========================================================================


def test_gate2_first_reminder_fires_then_enters_cooldown() -> None:
    gate = CooldownGate()
    first = _notification(0, NotificationKind.GENERAL_REMINDER)

    delivered = gate.check(first, T_AFTER_BADMINTON)
    assert delivered.verdict is GateVerdict.DELIVERED
    assert delivered.motor_vibrations == 1
    assert COOLDOWN_MIN_MINUTES * 60.0 <= delivered.cooldown_seconds <= COOLDOWN_MAX_MINUTES * 60.0

    immediate = gate.check(_notification(1, NotificationKind.GENERAL_REMINDER), T_AFTER_BADMINTON)
    assert immediate.verdict is GateVerdict.SUPPRESSED_BY_COOLDOWN
    assert immediate.motor_vibrations == 0, "冷却期内一律不许再震"
    assert immediate.next_allowed_at == delivered.next_allowed_at

    # 冷却到期后放行
    allowed_again = gate.check(
        _notification(2, NotificationKind.GENERAL_REMINDER),
        delivered.next_allowed_at + timedelta(seconds=1),
    )
    assert allowed_again.verdict is GateVerdict.DELIVERED
    assert gate.delivered_count == 2 and gate.suppressed_count == 1


def test_gate2_cooldown_never_escapes_the_15_to_30_minute_band() -> None:
    gate = CooldownGate()
    now = T_AFTER_BADMINTON
    observed: list[float] = []
    for index in range(12):
        decision = gate.check(_notification(index, NotificationKind.TASK_REMINDER), now)
        if decision.verdict is GateVerdict.DELIVERED:
            observed.append(decision.cooldown_seconds)
            now = deployment = decision.next_allowed_at + timedelta(seconds=1)
        else:
            now = decision.next_allowed_at + timedelta(seconds=1)

    assert observed, "至少要有一次放行"
    assert all(
        COOLDOWN_MIN_MINUTES * 60.0 <= value <= COOLDOWN_MAX_MINUTES * 60.0 for value in observed
    ), f"冷却时长越界: {observed}"
    assert max(observed) == COOLDOWN_MAX_MINUTES * 60.0, "连续触发必须抬升到 30 分钟封顶"
    assert observed[0] == COOLDOWN_MIN_MINUTES * 60.0
    assert len(set(observed)) >= 3, "冷却必须自适应抬升，而不是恒定值"
    print(f"[M2-001 冷却梯度] 阶梯={observed}（秒），封顶 {COOLDOWN_MAX_MINUTES} 分钟")


def test_gate2_cooldown_decays_after_a_quiet_period() -> None:
    policy = CooldownPolicy(quiet_reset_minutes=90.0)
    gate = CooldownGate(policy)
    now = T_AFTER_BADMINTON
    heights: list[float] = []
    for index in range(6):
        decision = gate.check(_notification(index, NotificationKind.GENERAL_REMINDER), now)
        assert decision.verdict is GateVerdict.DELIVERED
        heights.append(decision.cooldown_seconds)
        now = decision.next_allowed_at + timedelta(seconds=1)
    assert heights[-1] == COOLDOWN_MAX_MINUTES * 60.0

    # 长时间不打扰（>= 90 分钟）后，冷却回落到底价 15 分钟
    after_quiet = now + timedelta(minutes=policy.quiet_reset_minutes + 1)
    reset = gate.check(_notification(99, NotificationKind.GENERAL_REMINDER), after_quiet)
    assert reset.verdict is GateVerdict.DELIVERED
    assert reset.cooldown_seconds == COOLDOWN_MIN_MINUTES * 60.0, "静默期后必须回落到 15 分钟"


def test_gate2_cooldown_is_per_channel_so_alerts_do_not_starve_each_other() -> None:
    gate = CooldownGate()
    general = gate.check(_notification(0, NotificationKind.GENERAL_REMINDER), T_AFTER_BADMINTON)
    review = gate.check(_notification(0, NotificationKind.REVIEW_REFLECTION), T_AFTER_BADMINTON)

    assert general.verdict is GateVerdict.DELIVERED
    assert review.verdict is GateVerdict.DELIVERED, "不同通道各自独立冷却（复盘不该被一般提醒压死）"
    assert general.gate_key != review.gate_key
    # 但同一通道的第二次立刻被压制
    again = gate.check(_notification(1, NotificationKind.REVIEW_REFLECTION), T_AFTER_BADMINTON)
    assert again.verdict is GateVerdict.SUPPRESSED_BY_COOLDOWN


def test_gate2_general_reminder_flood_is_throttled_to_a_handful() -> None:
    """30 分钟内连推 30 条一般提醒：最多放行 2 次，其余全部压掉。"""
    gate = CooldownGate()
    start = T_AFTER_BADMINTON
    delivered = 0
    for index in range(30):
        decision = gate.check(
            _notification(index, NotificationKind.GENERAL_REMINDER),
            start + timedelta(seconds=index * 60),
        )
        delivered += 1 if decision.verdict is GateVerdict.DELIVERED else 0
    assert delivered <= 2, f"30 分钟内放行了 {delivered} 次，骚扰防护失效"
    assert gate.suppressed_count >= 28
    assert gate.motor_vibrations == delivered


# ===========================================================================
# 硬门禁 3：深度睡眠绝对静默（除 P0 外马达 0 次）
# ===========================================================================


def test_gate3_deep_sleep_silences_everything_except_p0() -> None:
    gate = DeepSleepGate()
    state = _deep_sleep_state()
    assert state.silence_required is True

    decisions = []
    for index in range(GENERAL_NOTIFICATIONS):
        decisions.append(gate.check(_notification(index, NotificationKind.GENERAL_REMINDER), state))
    for index in range(REVIEW_NOTIFICATIONS):
        decisions.append(gate.check(_notification(index, NotificationKind.REVIEW_REFLECTION), state))
    for index in range(TASK_NOTIFICATIONS):
        decisions.append(gate.check(_notification(index, NotificationKind.TASK_REMINDER), state))

    assert all(d.verdict is GateVerdict.SUPPRESSED_BY_DEEP_SLEEP for d in decisions)
    assert all(d.motor_vibrations == 0 for d in decisions)
    assert gate.motor_vibrations == 0, "深睡期非 P0 通知的物理马达振动必须严格为 0"
    assert gate.suppressed_count == SILENCED_TOTAL
    assert gate.hardware_pulse_count == 0

    p0 = gate.check(_p0_cardiac_fall(), state)
    assert p0.verdict is GateVerdict.DELIVERED, "P0 生命安全必须硬件直穿"
    assert p0.safety_exempt is True and p0.hardware_pulse_issued is True
    assert p0.motor_vibrations == 0, "急救走硬件通道，不占用马达"
    assert gate.hardware_pulse_count == 1
    assert gate.motor_vibrations == 0


def test_gate3_facade_keeps_motor_silent_and_llm_at_zero_during_sleep() -> None:
    queue = WakeCooldownQueue()
    queue.enter_state(_deep_sleep_state())

    for index in range(GENERAL_NOTIFICATIONS):
        queue.notify(_notification(index, NotificationKind.GENERAL_REMINDER), T_SLEEP_MIDDLE)
    for index in range(REVIEW_NOTIFICATIONS):
        queue.notify(_notification(index, NotificationKind.REVIEW_REFLECTION), T_SLEEP_MIDDLE)
    for index in range(TASK_NOTIFICATIONS):
        queue.notify(_notification(index, NotificationKind.TASK_REMINDER), T_SLEEP_MIDDLE)

    audit = queue.audit()
    assert audit["motor_vibrations"] == 0, "深睡期马达振动必须严格为 0"
    assert audit["notifications_delivered"] == 0
    assert audit["queued_now"] == SILENCED_TOTAL
    assert audit["llm_calls"] == 0, "机械静默闸不允许任何大模型参与"
    assert queue.silent_queue.enqueued_total == SILENCED_TOTAL

    # P0 直穿不破坏静默纪律
    p0_outcome = queue.notify(_p0_cardiac_fall(), T_SLEEP_MIDDLE)
    assert p0_outcome.verdict is GateVerdict.DELIVERED
    assert queue.deep_sleep_gate.hardware_pulse_count == 1
    assert queue.motor_vibrations == 0


def test_gate3_outside_sleep_the_same_notifications_are_delivered() -> None:
    """对照组：非深睡状态下同样的一批通知会被正常投递（证明静默是状态驱动，不是全盘哑火）。"""
    queue = WakeCooldownQueue()
    queue.enter_state(PhysiologyState(captured_at=T_AFTER_BADMINTON, in_bed=False, asleep=False))
    outcome = queue.notify(_notification(0, NotificationKind.TASK_REMINDER), T_AFTER_BADMINTON)
    assert outcome.verdict is GateVerdict.DELIVERED
    assert queue.motor_vibrations == 1


# ===========================================================================
# 硬门禁 4：静默队列无损解冻与有序聚合呈现
# ===========================================================================


def test_gate4_queue_stays_frozen_until_the_morning_safe_window() -> None:
    queue = SilentQueue()
    for index in range(SILENCED_TOTAL):
        queue.enqueue(_notification(index, NotificationKind.GENERAL_REMINDER))

    # 仍在深睡
    while_asleep = queue.unfreeze(_deep_sleep_state())
    assert while_asleep.unfrozen is False and while_asleep.still_silent is True
    assert while_asleep.presented == ()
    assert while_asleep.motor_vibrations == 0
    assert while_asleep.queued_remaining == SILENCED_TOTAL, "不解冻就必须原样封存（无损）"

    # 醒了但还赖在床上：仍不是安全窗口
    in_bed_awake = queue.unfreeze(
        PhysiologyState(captured_at=T_MORNING, deep_sleep=False, asleep=False, in_bed=True)
    )
    assert in_bed_awake.unfrozen is False
    assert in_bed_awake.queued_remaining == SILENCED_TOTAL
    assert in_bed_awake.motor_vibrations == 0


def test_gate4_morning_unfreeze_is_ordered_aggregated_and_lossless() -> None:
    queue = SilentQueue(batch_size=5)
    for index in range(GENERAL_NOTIFICATIONS):
        queue.enqueue(_notification(index, NotificationKind.GENERAL_REMINDER))
    for index in range(REVIEW_NOTIFICATIONS):
        queue.enqueue(
            _notification(index, NotificationKind.REVIEW_REFLECTION, priority=WakePriority.P1_URGENT_TASK)
        )
    for index in range(TASK_NOTIFICATIONS):
        queue.enqueue(
            _notification(index, NotificationKind.TASK_REMINDER, priority=WakePriority.P3_BACKGROUND_TICK)
        )

    report = queue.unfreeze(_morning_state())
    assert report.unfrozen is True and report.still_silent is False
    assert len(report.presented) == SILENCED_TOTAL
    assert report.dropped == 0 and report.lossless is True, "静默队列必须无损"
    assert queue.queued_count == 0
    assert queue.presented_total == SILENCED_TOTAL

    # 有序：先按优先级（P1 复盘 -> P2 一般 -> P3 任务），同级按时间
    order = [
        (WakePriority.P1_URGENT_TASK, WakePriority.P2_NORMAL_INTERACT, WakePriority.P3_BACKGROUND_TICK)
        .index(n.priority)
        for n in report.presented
    ]
    assert order == sorted(order), "解冻呈现必须按优先级有序"
    by_priority: dict[WakePriority, list[datetime]] = {}
    for notification in report.presented:
        by_priority.setdefault(notification.priority, []).append(notification.created_at)
    for moments in by_priority.values():
        assert moments == sorted(moments), "同优先级内必须按时间有序"

    # 聚合呈现：马达只震 1 次（不是 28 次）
    assert report.aggregated_batches == 6, "28 条按 5 条一批 = 6 个聚合批次"
    assert report.motor_vibrations == 1, "晨间聚合呈现只允许震一次"
    assert queue.presented_total == SILENCED_TOTAL
    print(
        f"[M2-001 晨间解冻] 挂起={SILENCED_TOTAL} 批次数={report.aggregated_batches} "
        f"马达振动={report.motor_vibrations} 丢弃={report.dropped}"
    )


def test_gate4_facade_end_to_end_sleep_then_morning() -> None:
    queue = WakeCooldownQueue()
    queue.enter_state(_deep_sleep_state())
    for index in range(GENERAL_NOTIFICATIONS):
        queue.notify(_notification(index, NotificationKind.GENERAL_REMINDER), T_SLEEP_MIDDLE)
    for index in range(REVIEW_NOTIFICATIONS):
        queue.notify(_notification(index, NotificationKind.REVIEW_REFLECTION), T_SLEEP_MIDDLE)
    queue.notify(_p0_cardiac_fall(), T_SLEEP_MIDDLE)  # 唯一直穿的那条

    assert queue.audit()["queued_now"] == GENERAL_NOTIFICATIONS + REVIEW_NOTIFICATIONS
    assert queue.audit()["motor_vibrations"] == 0

    report = queue.morning_wake(_morning_state())
    assert report.unfrozen is True
    assert len(report.presented) == GENERAL_NOTIFICATIONS + REVIEW_NOTIFICATIONS
    assert report.motor_vibrations == 1
    assert queue.audit()["queued_now"] == 0
    assert queue.audit()["motor_vibrations"] == 1, "整夜到晨间总共只震 1 次"
    assert queue.audit()["hardware_pulses"] == 1
    assert queue.audit()["llm_calls"] == 0


# ===========================================================================
# 端到端压力：赛后 5 秒 + 整夜
# ===========================================================================


def test_full_night_pipeline_is_quiet_and_lossless() -> None:
    queue = WakeCooldownQueue()

    # 20:30 羽毛球赛后：5 秒 250 条脉冲
    batches = queue.submit_pulses(_badminton_aftermath_pulses())
    queue.submit_pulse(
        PhysiologicalPulse(
            pulse_id="tail",
            captured_at=T_AFTER_BADMINTON + timedelta(seconds=6),
            kind=PulseKind.HEART_RATE,
            value=140.0,
            unit="bpm",
        )
    )
    queue.enter_state(_deep_sleep_state())

    # 02:00~06:00 深睡：一般通知 + 复盘 + 任务提醒全部挂起
    for index in range(GENERAL_NOTIFICATIONS):
        queue.notify(_notification(index, NotificationKind.GENERAL_REMINDER), T_SLEEP_MIDDLE)
    for index in range(TASK_NOTIFICATIONS):
        queue.notify(_notification(index, NotificationKind.TASK_REMINDER), T_SLEEP_MIDDLE)

    sleep_audit = queue.audit()
    assert sleep_audit["motor_vibrations"] == 0
    assert sleep_audit["queued_now"] == GENERAL_NOTIFICATIONS + TASK_NOTIFICATIONS
    assert sleep_audit["downstream_wakes"] <= 2, "赛后脉冲只允许偶发几次下游唤醒"

    # 06:40 起床（走出睡眠状态）
    report = queue.morning_wake(_morning_state())
    assert report.unfrozen is True and report.lossless is True
    assert report.motor_vibrations == 1

    final = queue.audit()
    assert final["motor_vibrations"] == 1
    assert final["notifications_delivered"] == 0
    assert final["llm_calls"] == 0
    print(
        f"[M2-001 全链路] 脉冲={len(_badminton_aftermath_pulses())} 批次数={final['batches_emitted']} "
        f"下游唤醒={final['downstream_wakes']} 深睡挂起={sleep_audit['queued_now']} "
        f"晨间呈现={len(report.presented)} 全夜马达={final['motor_vibrations']}"
    )


def test_merge_contract_rejects_invalid_window() -> None:
    with pytest.raises(Exception) as excinfo:
        PulseMergeWindow(window_seconds=0.0)
    assert getattr(excinfo.value, "context", {}).get("reason") == "invalid_merge_window"


def test_cooldown_policy_bounds_are_validated() -> None:
    with pytest.raises(Exception):
        CooldownPolicy(base_minutes=20.0, max_minutes=10.0)
