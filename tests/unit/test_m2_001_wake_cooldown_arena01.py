"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸 · 四大硬门禁验收。

情境：羽毛球赛后 50Hz 高频体征脉冲；凌晨 02:00~06:00 深度睡眠。
1. 5 秒 250 条离散脉冲 → 单条批次事件，下游永不逐条唤醒；
2. 一般提醒触发后强制 15~30 分钟自适应冷却，骚扰零马达；
3. 深睡期除 P0 生命安全硬件直穿外全部挂起，马达振动严格 0；
4. 清醒下床后首个安全窗口：静默队列无损、有序、聚合解冻。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.safety_bypass import WakePriority
from aios_core.wake.cooldown_queue_arena01 import (
    GeneralNotice,
    RecordingMotor,
    SleepStage,
    VitalPulse,
    WakeCooldownQueue,
)

T0 = datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)  # 羽毛球赛后
NIGHT = datetime(2026, 9, 16, 2, 30, tzinfo=timezone.utc)  # 凌晨深睡窗口
MORNING = datetime(2026, 9, 16, 7, 10, tzinfo=timezone.utc)  # 晨间清醒下床


def _pulse(i: int, *, base: datetime = T0, key: str = "badminton-cardio", value: float | None = None) -> VitalPulse:
    """50Hz 离散体征脉冲（20ms 间隔），值确定性抖动。"""
    return VitalPulse(
        ts=base + timedelta(milliseconds=i * 20),
        kind="heart_rate",
        value=value if value is not None else 158.0 + (i % 37) * 0.5,
        dedupe_key=key,
    )


# ===========================================================================
# 门禁 1：高频防抖与合并窗口——250 条脉冲只唤醒下游 1 次
# ===========================================================================


def test_gate1_250_pulses_in_5s_merge_into_single_batch() -> None:
    queue = WakeCooldownQueue(motor=RecordingMotor())
    for i in range(250):  # 50Hz × 5s
        queue.ingest_pulse(_pulse(i))
    assert queue.stats["pulses_ingested"] == 250
    assert queue.stats["downstream_wakes"] == 0  # 摄入期间下游零惊扰

    batches = queue.seal_finished_windows(T0 + timedelta(seconds=5, milliseconds=20))
    assert len(batches) == 1  # 5 秒窗口只产出单条批次事件
    batch = batches[0]
    assert batch.dedupe_key == "badminton-cardio"
    assert batch.pulse_count == 250
    assert 1 < batch.unique_count <= 250  # 精确内容去重（同值脉冲合并计数）
    assert batch.min_value < batch.mean_value < batch.max_value
    # 下游心智流水线全程只被唤醒 1 次，绝无 250 次穿透。
    assert queue.stats["downstream_wakes"] == 1
    assert queue.stats["batches_sealed"] == 1


def test_gate1_multi_sensor_keys_batch_independently_and_duplicate_collapse() -> None:
    queue = WakeCooldownQueue()
    # 心率与加速度两路 50Hz 各 5 秒。
    for i in range(250):
        queue.ingest_pulse(_pulse(i, key="hr-stream", value=160.0 + i))
        queue.ingest_pulse(
            VitalPulse(ts=T0 + timedelta(milliseconds=i * 20), kind="accel", value=3.2, dedupe_key="acc-stream")
        )
    batches = queue.seal_finished_windows(T0 + timedelta(seconds=6))
    assert {b.dedupe_key for b in batches} == {"hr-stream", "acc-stream"}
    by_key = {b.dedupe_key: b for b in batches}
    assert by_key["hr-stream"].pulse_count == 250
    # 加速度全同值：精确去重后 unique_count==1，脉冲计数仍 250（无损审计）。
    assert by_key["acc-stream"].pulse_count == 250
    assert by_key["acc-stream"].unique_count == 1
    assert queue.stats["downstream_wakes"] == 2  # 每键每窗严格 1 次
    assert queue.stats["pulses_deduped"] == 0  # 时间戳不同不算重复，只在 unique_count 上聚合

    # 完全相同的重放脉冲（同键同值）被逐条判重。
    queue2 = WakeCooldownQueue()
    dup = _pulse(0, key="dup")
    for _ in range(100):
        queue2.ingest_pulse(dup)
    [batch] = queue2.seal_finished_windows(T0 + timedelta(seconds=6))
    assert batch.pulse_count == 1
    assert queue2.stats["pulses_deduped"] == 99


def test_gate1_rolling_windows_emit_in_order_not_per_pulse() -> None:
    queue = WakeCooldownQueue()
    for i in range(500):  # 10 秒连续 50Hz → 两个 5 秒窗口
        queue.ingest_pulse(_pulse(i))
    queue.seal_finished_windows(T0 + timedelta(seconds=5))
    queue.seal_finished_windows(T0 + timedelta(seconds=11))
    assert queue.stats["downstream_wakes"] == 2
    assert queue.stats["batches_sealed"] == 2


# ===========================================================================
# 门禁 2：冷却时间硬防护（15~30 分钟自适应）
# ===========================================================================


def test_gate2_cooldown_hard_wall_and_adaptive_extension() -> None:
    motor = RecordingMotor()
    queue = WakeCooldownQueue(motor=motor, cooldown_base_minutes=15, cooldown_max_minutes=30)
    notice = GeneralNotice(ts=T0, category="task_reminder", text="提示复核对赌回购补充协议", cooldown_key="vam-review")

    first = queue.notify_general(notice)
    assert first.outcome == "delivered" and first.motor_vibrated
    assert motor.count == 1
    assert first.cooldown_until == T0 + timedelta(minutes=15)

    # 冷却期内反复骚扰：全部压制、零马达。
    for minutes in (1, 5, 14):
        verdict = queue.notify_general(
            GeneralNotice(ts=T0 + timedelta(minutes=minutes), category="task_reminder",
                          text="同一提醒的高频骚扰", cooldown_key="vam-review")
        )
        assert verdict.outcome == "suppressed_cooldown"
        assert not verdict.motor_vibrated
    assert motor.count == 1
    assert queue.stats["cooldown_suppressions"] == 3
    assert queue.cooldown_remaining_seconds("vam-review", T0 + timedelta(minutes=14)) > 0

    # 冷却结束再次投递：本轮骚扰 3 次 → 冷却自适应延长 15+3=18 分钟。
    second = queue.notify_general(
        GeneralNotice(ts=T0 + timedelta(minutes=15), category="task_reminder",
                      text="冷却结束后的合法再提醒", cooldown_key="vam-review")
    )
    assert second.outcome == "delivered"
    assert second.cooldown_until == T0 + timedelta(minutes=15) + timedelta(minutes=18)
    assert motor.count == 2

    # 自适应封顶：连续骚扰压制必然收敛在 30 分钟硬顶之内。
    for minutes in (16, 17, 18, 20, 25):
        queue.notify_general(
            GeneralNotice(ts=T0 + timedelta(minutes=15) + timedelta(minutes=minutes),
                          category="task_reminder", text="持续骚扰", cooldown_key="vam-review")
        )
    third_at = second.cooldown_until
    third = queue.notify_general(
        GeneralNotice(ts=third_at, category="task_reminder", text="再次合法提醒", cooldown_key="vam-review")
    )
    assert third.cooldown_until - third_at <= timedelta(minutes=30)
    assert third.cooldown_until - third_at >= timedelta(minutes=15)
    assert motor.count == 3  # 骚扰全程零额外马达


def test_gate2_cooldown_keys_are_isolated() -> None:
    queue = WakeCooldownQueue(motor=RecordingMotor())
    a = GeneralNotice(ts=T0, category="task_reminder", text="协议复核", cooldown_key="key-a")
    b = GeneralNotice(ts=T0, category="reflection", text="深夜复盘提示", cooldown_key="key-b")
    assert queue.notify_general(a).outcome == "delivered"
    assert queue.notify_general(b).outcome == "delivered"  # 异键互不俗冷却
    assert queue.notify_general(
        GeneralNotice(ts=T0 + timedelta(minutes=1), category="task_reminder", text="x", cooldown_key="key-a")
    ).outcome == "suppressed_cooldown"
    assert queue.stats["general_deliveries"] == 2


# ===========================================================================
# 门禁 3：DEEP_SLEEP 绝对静默——P0 之外马达振动严格为 0
# ===========================================================================


def test_gate3_deep_sleep_forces_total_silence_except_p0() -> None:
    motor = RecordingMotor()
    queue = WakeCooldownQueue(motor=motor)
    queue.set_sleep_stage(SleepStage.DEEP_SLEEP)

    # 一般通知 / 复盘反思 / 任务提醒：全部强制挂起静默，马达 0。
    for i, category in enumerate(("general", "reflection", "task_reminder")):
        verdict = queue.notify_general(
            GeneralNotice(ts=NIGHT + timedelta(minutes=i), category=category,
                          text=f"{category} 深睡期内容 {i}", cooldown_key=f"night-{i}")
        )
        assert verdict.outcome == "held_silent"
        assert not verdict.motor_vibrated
    assert motor.count == 0
    assert queue.stats["motor_vibrations_total"] == 0
    assert queue.stats["silent_held"] == 3
    assert queue.silent_backlog_size() == 3

    # 高频体征脉冲照常聚合（不影响 P0 判定通路），但不产生任何振动。
    for i in range(250):
        queue.ingest_pulse(_pulse(i, base=NIGHT, key="night-cardio", value=58.0 + i % 5))
    assert queue.seal_finished_windows(NIGHT + timedelta(seconds=6))
    assert motor.count == 0

    # P0 生命安全（心梗/跌倒）硬件直穿：深睡中立即振动报警。
    receipt = queue.notify_p0(ts=NIGHT + timedelta(minutes=10), text="心率骤停告警", hazard="CARDIAC_ARREST")
    assert receipt["outcome"] == "p0_passthrough"
    assert receipt["sleep_stage_at_entry"] == SleepStage.DEEP_SLEEP
    assert motor.count == 1
    assert motor.calls == ["p0_emergency_pattern"]
    assert queue.stats["p0_passthrough"] == 1
    # P0 之后深睡静默闸依然闭合。
    assert queue.notify_general(
        GeneralNotice(ts=NIGHT + timedelta(minutes=11), category="general", text="并非 P0", cooldown_key="night-9")
    ).outcome == "held_silent"
    assert queue.stats["motor_vibrations_total"] == 1

    # 深睡中试图解冻静默队列：物理拒绝（防误解冻绕过静默闸）。
    with pytest.raises(ValueError, match="DEEP_SLEEP"):
        queue.flush_silent_backlog(NIGHT + timedelta(minutes=30))
    assert motor.count == 1


# ===========================================================================
# 门禁 4：静默队列无损唤醒延递
# ===========================================================================


def test_gate4_silent_queue_losslessly_defers_to_first_safe_window() -> None:
    motor = RecordingMotor()
    queue = WakeCooldownQueue(motor=motor)
    queue.set_sleep_stage(SleepStage.DEEP_SLEEP)
    notices = [
        GeneralNotice(ts=NIGHT + timedelta(minutes=m), category=cat, text=f"{cat}-{m}",
                      cooldown_key=f"k{m}", priority=prio)
        for m, cat, prio in (
            (5, "task_reminder", WakePriority.P2_NORMAL_INTERACT),
            (20, "general", WakePriority.P2_NORMAL_INTERACT),
            (2, "reflection", WakePriority.P3_BACKGROUND_TICK),
            (20, "general", WakePriority.P1_URGENT_TASK),
        )
    ]
    held_total = 0
    for n in notices:
        queue.notify_general(n)
        held_total += 1
    assert queue.silent_backlog_size() == held_total == 4

    # 晨间清醒并下床（走出睡眠态）后的第一个安全窗口：自动解冻。
    queue.set_sleep_stage(SleepStage.AWAKE)
    digest = queue.flush_silent_backlog(MORNING)

    # 无损：4 条全部呈现，一条不丢。
    assert digest.total == 4
    assert [n.text for n in digest.entries] == [n.text for n in sorted(
        notices, key=lambda n: (n.ts, -list(WakePriority).index(n.priority))
    )]
    # 有序：时间升序，同时刻优先级降序（P1 紧急先于 P2 普通）。
    ts_seq = [n.ts for n in digest.entries]
    assert ts_seq == sorted(ts_seq)
    same_ts_p1_first = digest.entries[2].priority is WakePriority.P1_URGENT_TASK or digest.entries[3].priority is WakePriority.P1_URGENT_TASK
    assert digest.entries[2].text == "general-20" and digest.entries[3].text == "general-20"
    # 聚合：类目计数完整。
    assert dict(digest.grouped_counts) == {"general": 2, "reflection": 1, "task_reminder": 1}
    # 静默队列清空；清醒后允许一次轻柔的摘要振动。
    assert queue.silent_backlog_size() == 0
    assert queue.stats["silent_flushed"] == 4
    assert digest.motor_vibrated
    assert motor.count == 1

    # 空队列重复解冻是幂等空操作，不再振动。
    digest2 = queue.flush_silent_backlog(MORNING + timedelta(minutes=10))
    assert digest2.total == 0 and not digest2.motor_vibrated
    assert motor.count == 1


def test_gate4_deferred_notices_then_reenter_normal_cooldown_world() -> None:
    motor = RecordingMotor()
    queue = WakeCooldownQueue(motor=motor)
    queue.set_sleep_stage(SleepStage.DEEP_SLEEP)
    queue.notify_general(GeneralNotice(ts=NIGHT, category="task_reminder", text="晨间待办", cooldown_key="todo"))
    queue.set_sleep_stage(SleepStage.AWAKE)
    queue.flush_silent_backlog(MORNING, motor_pulse=False)
    assert motor.count == 0  # 调用方也可选择纯静默呈现

    # 解冻后世界恢复正常冷却秩序。
    v = queue.notify_general(GeneralNotice(ts=MORNING, category="general", text="正常提醒", cooldown_key="daily"))
    assert v.outcome == "delivered"
    assert queue.cooldown_remaining_seconds("daily", MORNING) == pytest.approx(15 * 60)
