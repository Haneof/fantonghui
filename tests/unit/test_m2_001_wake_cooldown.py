"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸 —— 压测。

实战情境：羽毛球赛后 50Hz 加速度计 + 剧烈心率波动涌入 250 条离散
脉冲；随后进入凌晨 02:00~06:00 深度睡眠；晨间下床后静默队列解冻。

四大硬门禁：
1. 5 秒内 250 条离散脉冲合并为单条批次事件，下游唤醒尝试=1；
2. 非致命提醒触发后强制 15~30 分钟自适应冷却；
3. 深度睡眠期间除 P0 外全部挂起，马达振动次数严格为 0；
4. 清晨下床后静默队列无损解冻、有序聚合呈现。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.wake.cooldown_queue import (
    BatchedPulseEvent,
    CooldownPolicy,
    DeepSleepGate,
    MergeWindow,
    WakeDispatchCenter,
    WakePulse,
    WakeSeverity,
)

UTC = timezone.utc
MATCH_END = datetime(2026, 9, 14, 20, 0, 0, tzinfo=UTC)      # 羽毛球赛结束
DEEP_SLEEP_AT = datetime(2026, 9, 15, 2, 0, 0, tzinfo=UTC)   # 凌晨02:00 入睡
WAKE_AT = datetime(2026, 9, 15, 6, 40, 0, tzinfo=UTC)        # 清晨下床


def _badminton_burst() -> list[WakePulse]:
    """5 秒内 250 条离散脉冲（50Hz IMU × 4s + 剧烈心率波动）。"""
    pulses: list[WakePulse] = []
    for i in range(200):  # 50Hz IMU 离散数据
        pulses.append(
            WakePulse(
                pulse_id=f"imu_{i:03d}",
                source_class="imu",
                severity=WakeSeverity.NORMAL,
                at=MATCH_END + timedelta(milliseconds=i * 20),
                dedupe_key="post_match_imu_burst",
            )
        )
    for i in range(50):  # 剧烈心率波动
        pulses.append(
            WakePulse(
                pulse_id=f"hr_{i:03d}",
                source_class="hr",
                severity=WakeSeverity.ELEVATED,
                at=MATCH_END + timedelta(milliseconds=100 + i * 80),
                dedupe_key="post_match_hr_spike",
            )
        )
    return pulses


# ======================================================================
# 门禁一：250 条脉冲 → 单条批次事件
# ======================================================================

def test_gate1_250_pulses_merge_into_single_batch_per_stream() -> None:
    window = MergeWindow()
    pulses = _badminton_burst()
    for pulse in pulses:
        window.submit(pulse)
    assert window.pending_batches() == 2  # imu 流 + hr 流（同窗内各自聚合）
    events = window.flush(now=MATCH_END + timedelta(seconds=6))
    assert len(events) == 2
    by_key = {e.dedupe_key: e for e in events}
    imu_batch = by_key["post_match_imu_burst"]
    hr_batch = by_key["post_match_hr_spike"]
    assert imu_batch.pulse_count == 200
    assert hr_batch.pulse_count == 50
    # 下游心智流水线只见 2 次批次事件（而非 250 次唤醒尝试）
    assert sum(e.pulse_count for e in events) == 250


def test_gate1_duplicate_pulse_delivery_is_deduped() -> None:
    window = MergeWindow()
    pulse = WakePulse(
        pulse_id="hr_repeat",
        source_class="hr",
        at=MATCH_END,
        dedupe_key="hr_spike",
        severity=WakeSeverity.ELEVATED,
    )
    for _ in range(10):
        window.submit(pulse)
    events = window.flush(now=MATCH_END + timedelta(seconds=6))
    assert len(events) == 1
    assert events[0].pulse_count == 1  # 同脉冲重复投递只计一次


def test_gate1_end_to_end_pipeline_sees_single_wake_attempt() -> None:
    center = WakeDispatchCenter()
    center.accept(_badminton_burst())
    decisions = center.process(now=MATCH_END + timedelta(seconds=6))
    dispatched = [d for d in decisions if d.action == "dispatch_now"]
    assert len(dispatched) == 2  # 两条物理流各一次合并派发
    assert center.motor_vibration_count == 2


# ======================================================================
# 门禁二：15~30 分钟自适应冷却硬防护
# ======================================================================

def test_gate2_cooldown_blocks_immediate_refire() -> None:
    cooldown = CooldownPolicy()
    at = MATCH_END
    cooldown.arm_after_dispatch("hydration_reminder", now=at)
    assert cooldown.is_cooled_down("hydration_reminder", now=at + timedelta(minutes=10))
    assert not cooldown.is_cooled_down("hydration_reminder", now=at + timedelta(minutes=16))


def test_gate2_adaptive_cooldown_escalates_to_30min_cap() -> None:
    cooldown = CooldownPolicy()
    at = MATCH_END
    assert cooldown.cooldown_minutes_for("meeting_prep") == 15  # 基线 15 分钟
    for _ in range(3):
        cooldown.record_dismissal("meeting_prep")
    assert cooldown.cooldown_minutes_for("meeting_prep") == 30  # 3次忽略 → 顶格
    for _ in range(10):
        cooldown.record_dismissal("meeting_prep")
    assert cooldown.cooldown_minutes_for("meeting_prep") == 30  # 自适应上限封顶


def test_gate2_cooldown_never_blocks_p0_safety() -> None:
    center = WakeDispatchCenter()
    center.sleep_gate.set_sleep_state(deep_sleep=True, at=DEEP_SLEEP_AT)
    center.cooldown.arm_after_dispatch("fall_impact", now=DEEP_SLEEP_AT)
    center.accept(
        [
            WakePulse(
                pulse_id="p0_fall_001",
                source_class="hardwave_fall",
                severity=WakeSeverity.P0_CRITICAL_SAFETY,
                at=DEEP_SLEEP_AT + timedelta(minutes=1),
                dedupe_key="fall_impact",
            )
        ]
    )
    decisions = center.process(now=DEEP_SLEEP_AT + timedelta(minutes=1, seconds=6))
    assert decisions[0].action == "p0_bypass"
    assert decisions[0].motor_vibrations == 1  # 冷却/静默均不可吞没 P0


# ======================================================================
# 门禁三：DEEP_SLEEP 绝对静默（马达振动严格为 0）
# ======================================================================

def test_gate3_deep_sleep_suspends_everything_except_p0() -> None:
    center = WakeDispatchCenter(motor=lambda batch_id: None)
    center.sleep_gate.set_sleep_state(deep_sleep=True, at=DEEP_SLEEP_AT)

    night_pulses: list[WakePulse] = []
    # 深睡期涌入的一般通知/复盘反思/任务提醒（非 P0）
    categories = (
        ("hr", "night_hr_drift", WakeSeverity.ELEVATED),
        ("reflective", "night_reflection_batch", WakeSeverity.NORMAL),
        ("reminder", "tomorrow_agenda", WakeSeverity.NORMAL),
        ("reminder", "water_reminder", WakeSeverity.NORMAL),
    )
    seq = 0
    for minute_offset in range(0, 200, 10):  # 02:00~05:10 每10分钟一波
        for source, key, severity in categories:
            seq += 1
            night_pulses.append(
                WakePulse(
                    pulse_id=f"night_{seq:03d}",
                    source_class=source,
                    severity=severity,
                    at=DEEP_SLEEP_AT + timedelta(minutes=minute_offset),
                    dedupe_key=key,
                )
            )
    center.accept(night_pulses)
    # 分波推进派发循环
    for minute_offset in range(0, 220, 10):
        center.process(now=DEEP_SLEEP_AT + timedelta(minutes=minute_offset, seconds=6))

    deferred = [d for d in center.decisions() if d.action == "silent_deferred"]
    assert len(deferred) >= 4
    assert all(d.motor_vibrations == 0 for d in deferred)
    # 整个深睡阶段物理马达振动次数严格为 0
    assert center.motor_vibration_count == 0
    assert center.sleep_gate.pending_count() >= 4  # 静默队列完整持有


def test_gate3_sleep_state_toggle_is_explicit() -> None:
    gate = DeepSleepGate()
    assert gate.deep_sleep is False
    gate.set_sleep_state(deep_sleep=True, at=DEEP_SLEEP_AT)
    assert gate.deep_sleep is True
    event = BatchedPulseEvent(
        batch_id="b1",
        source_class="hr",
        severity=WakeSeverity.NORMAL,
        pulse_count=1,
        first_at=DEEP_SLEEP_AT,
        last_at=DEEP_SLEEP_AT,
        dedupe_key="night_hr",
    )
    assert gate.gate(event, at=DEEP_SLEEP_AT + timedelta(minutes=3)) is False


# ======================================================================
# 门禁四：静默队列无损唤醒延递（晨间有序聚合）
# ======================================================================

def test_gate4_morning_thaw_drains_ordered_and_lossless() -> None:
    center = WakeDispatchCenter(motor=lambda batch_id: None)
    center.sleep_gate.set_sleep_state(deep_sleep=True, at=DEEP_SLEEP_AT)

    # 深睡期三波非 P0 事件
    for i, (key, first_minute, severity) in enumerate(
        (
            ("night_hr", 0, WakeSeverity.ELEVATED),
            ("night_reflection", 40, WakeSeverity.NORMAL),
            ("tomorrow_agenda", 120, WakeSeverity.NORMAL),
        )
    ):
        for k in range(3):  # 每波 3 条脉冲
            center.accept(
                [
                    WakePulse(
                        pulse_id=f"n{i}_{k}",
                        source_class="mixed",
                        severity=severity,
                        at=DEEP_SLEEP_AT + timedelta(minutes=first_minute + k),
                        dedupe_key=key,
                    )
                ]
            )
        center.process(
            now=DEEP_SLEEP_AT + timedelta(minutes=first_minute + 5, seconds=6)
        )

    assert center.sleep_gate.pending_count() == 3
    assert center.motor_vibration_count == 0

    # 清晨下床：第一个安全窗口解冻
    center.sleep_gate.set_sleep_state(deep_sleep=False, at=WAKE_AT)
    entries = center.thaw_silent_queue()

    assert len(entries) == 3  # 无损：三波全部解冻
    # 有序：按首触时间排列（夜内 HR 最先，议程最后）
    assert [e.batch.dedupe_key for e in entries] == (
        ["night_hr", "night_reflection", "tomorrow_agenda"]
    )
    # 完整性：脉冲计数与现场时间戳原样保留
    assert sum(e.batch.pulse_count for e in entries) == 9
    assert entries[0].batch.first_at == DEEP_SLEEP_AT
    assert entries[-1].batch.first_at == DEEP_SLEEP_AT + timedelta(minutes=120)
    # 聚合呈现只产生一次马达振动（不是 3 次连环轰炸）
    assert center.motor_vibration_count == 1
    assert center.sleep_gate.pending_count() == 0  # 队列清空，绝无二次残留


def test_gate4_thaw_order_prefers_severity_within_same_first_touch() -> None:
    gate = DeepSleepGate()
    gate.set_sleep_state(deep_sleep=True, at=DEEP_SLEEP_AT)
    same_time = DEEP_SLEEP_AT + timedelta(minutes=30)

    def make_event(batch_id: str, severity: WakeSeverity) -> BatchedPulseEvent:
        return BatchedPulseEvent(
            batch_id=batch_id,
            source_class="hr",
            severity=severity,
            pulse_count=1,
            first_at=same_time,
            last_at=same_time,
            dedupe_key=batch_id,
        )

    gate.gate(make_event("evt_low", WakeSeverity.NORMAL), at=same_time)
    gate.gate(make_event("evt_high", WakeSeverity.ELEVATED), at=same_time)
    entries = gate.thaw()
    assert [e.batch.batch_id for e in entries] == ["evt_high", "evt_low"]
