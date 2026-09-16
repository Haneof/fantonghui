"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸验收测试。

场景：羽毛球赛后心率剧烈波动 + 50Hz 加速度计离散洪流；凌晨 02:00~06:00
深度睡眠阶段。

四大硬门禁：
1. 5 秒内 250 条离散脉冲去重聚合为单条批次事件；
2. 非致命提醒触发后强制 15~30 分钟自适应冷却；
3. 深度睡眠：除 P0 生命安全事件外全部挂起，马达振动严格为 0；
4. 晨间清醒后静默队列无损解冻、有序聚合呈现。
"""

from __future__ import annotations

import pytest

from aios_core.contracts.safety_bypass import WakePriority
from aios_core.wake.cooldown_queue import (
    COALESCE_WINDOW_SECONDS,
    MAX_COOLDOWN_SECONDS,
    MIN_COOLDOWN_SECONDS,
    BatchedWakeEvent,
    SleepStage,
    WakeCooldownQueue,
    WakeKind,
    WakePulse,
)

T0 = 1000.0  # 秒级单调时钟基准


def _pulse(i: int, *, signature: str, at: float, kind: WakeKind = WakeKind.SENSOR_BATCH,
           priority: WakePriority = WakePriority.P2_NORMAL_INTERACT) -> WakePulse:
    return WakePulse(
        pulse_id=f"pulse-{signature}-{i:04d}",
        kind=kind,
        signature=signature,
        occurred_at=at,
        priority=priority,
        payload={"seq": i},
    )


# ---------------------------------------------------------------------------
# 硬门禁 1：5 秒合并窗口（250 条 -> 1 条批次事件）
# ---------------------------------------------------------------------------


def test_gate1_250_pulses_in_5s_coalesce_into_single_batch() -> None:
    queue = WakeCooldownQueue()
    assert COALESCE_WINDOW_SECONDS == 5.0

    # 5 秒内涌入 250 条心率剧烈波动脉冲（赛后 50Hz 采样洪流）。
    for i in range(250):
        queue.enqueue(_pulse(i, signature="hr-turbulence", at=T0 + i * 0.02))
    # 同一时间窗内另一签名 30 条加速度冲击脉冲。
    for i in range(30):
        queue.enqueue(_pulse(i, signature="accel-smash", at=T0 + i * 0.1))

    batches = queue.flush_window(now=T0 + COALESCE_WINDOW_SECONDS)

    assert len(batches) == 2  # 每个签名一条批次事件
    by_sig = {b.signature: b for b in batches}
    hr = by_sig["hr-turbulence"]
    assert isinstance(hr, BatchedWakeEvent)
    assert hr.count == 250
    assert len(hr.pulse_ids) == 250
    assert hr.first_at == pytest.approx(T0)
    assert hr.last_at <= T0 + COALESCE_WINDOW_SECONDS
    assert by_sig["accel-smash"].count == 30

    # 禁止逐条唤醒下游：批次路由各只产生 1 次下游唤醒。
    before = queue.downstream_wake_calls
    for batch in batches:
        queue.route_batch(batch, now=T0 + COALESCE_WINDOW_SECONDS)
    assert queue.downstream_wake_calls - before == 2  # 而不是 280


def test_gate1_duplicate_pulse_ids_are_deduplicated() -> None:
    queue = WakeCooldownQueue()
    for _ in range(3):  # 重复上报同一脉冲（传感器重发）
        queue.enqueue(_pulse(0, signature="dup", at=T0))
    queue.enqueue(_pulse(1, signature="dup", at=T0 + 1.0))
    (batch,) = queue.flush_window(now=T0 + 5.0)
    assert batch.count == 2  # 3 条重复去重为 1 条


# ---------------------------------------------------------------------------
# 硬门禁 2：15~30 分钟自适应冷却硬防护
# ---------------------------------------------------------------------------


def test_gate2_cooldown_forces_15_to_30_minutes_quiet_period() -> None:
    queue = WakeCooldownQueue()
    reminder = _pulse(0, signature="standup-reminder", at=T0, kind=WakeKind.GENERAL_REMINDER)

    assert queue.route_pulse(reminder, now=T0) == "delivered"
    cooldown = queue.cooldown_seconds("standup-reminder")
    assert MIN_COOLDOWN_SECONDS == 15 * 60
    assert MAX_COOLDOWN_SECONDS == 30 * 60
    assert MIN_COOLDOWN_SECONDS <= cooldown <= MAX_COOLDOWN_SECONDS

    # 冷却期内重复提醒：一律抑制，绝不骚扰。
    for t in (T0 + 60, T0 + 5 * 60, T0 + cooldown - 1):
        assert queue.route_pulse(reminder, now=t) == "cooldown_suppressed"
    assert queue.suppressed_by_cooldown == 3

    # 冷却期满：恢复送达。
    assert queue.route_pulse(reminder, now=T0 + cooldown + 1) == "delivered"


def test_gate2_cooldown_adapts_upward_within_15_30_bounds() -> None:
    queue = WakeCooldownQueue()
    sig = "noisy-nag"
    first = queue.route_pulse(_pulse(0, signature=sig, at=T0, kind=WakeKind.TASK_REMINDER), now=T0)
    assert first == "delivered"
    base = queue.cooldown_seconds(sig)

    # 连续骚扰 -> 冷却自适应拉长，但严格封顶 30 分钟。
    t = T0
    for i in range(1, 8):
        t = t + queue.cooldown_seconds(sig) + 1
        queue.route_pulse(_pulse(i, signature=sig, at=t, kind=WakeKind.TASK_REMINDER), now=t)
        queue.route_pulse(_pulse(100 + i, signature=sig, at=t + 10, kind=WakeKind.TASK_REMINDER), now=t + 10)
        span = queue.cooldown_seconds(sig)
        assert MIN_COOLDOWN_SECONDS <= span <= MAX_COOLDOWN_SECONDS
    assert queue.cooldown_seconds(sig) >= base
    assert queue.cooldown_seconds(sig) <= MAX_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# 硬门禁 3：DEEP_SLEEP 绝对静默闸
# ---------------------------------------------------------------------------


def test_gate3_deep_sleep_suspends_everything_except_p0_with_zero_vibration() -> None:
    queue = WakeCooldownQueue()
    queue.gate.set_stage(SleepStage.DEEP_SLEEP)

    # 凌晨 03:12 心梗跌倒：P0 生命安全事件硬件直穿。
    cardiac = WakePulse(
        pulse_id="p0-cardiac-fall",
        kind=WakeKind.P0_SAFETY,
        signature="p0-cardiac-fall",
        occurred_at=T0,
        priority=WakePriority.P0_CRITICAL_SAFETY,
        payload={"heart_rate_bpm": 165, "g_force": 5.2},
    )
    assert queue.route_pulse(cardiac, now=T0) == "delivered"
    assert queue.gate.p0_passes == 1

    # 50 条一般通知 / 复盘反思 / 任务提醒：全部强制挂起。
    kinds = (WakeKind.GENERAL_REMINDER, WakeKind.RETROSPECTIVE, WakeKind.TASK_REMINDER)
    for i in range(50):
        pulse = _pulse(i, signature=f"noise-{i % 7}", at=T0 + 60 + i, kind=kinds[i % 3])
        assert queue.route_pulse(pulse, now=T0 + 60 + i) == "suspended"

    assert queue.gate.suspended_count == 50
    assert queue.gate.silent_queue_size == 50
    # 物理马达振动次数严格为 0（P0 走硬件直穿通道，不经马达提醒）。
    assert queue.gate.motor_vibrations == 0
    # 深睡期间下游心智流水线零唤醒（P0 硬件直穿不计入常规下游）。
    assert queue.delivered_signatures == ["p0-cardiac-fall"]


# ---------------------------------------------------------------------------
# 硬门禁 4：静默队列无损唤醒延递
# ---------------------------------------------------------------------------


def test_gate4_silent_queue_releases_losslessly_on_first_wake_window() -> None:
    queue = WakeCooldownQueue()
    queue.gate.set_stage(SleepStage.DEEP_SLEEP)

    suspended_ids: list[str] = []
    kinds = (WakeKind.GENERAL_REMINDER, WakeKind.RETROSPECTIVE, WakeKind.TASK_REMINDER)
    for i in range(50):
        pulse = _pulse(i, signature=f"morning-{i % 5}", at=T0 + i * 30, kind=kinds[i % 3])
        assert queue.route_pulse(pulse, now=T0 + i * 30) == "suspended"
        suspended_ids.append(pulse.pulse_id)

    # 06:42 用户清醒下床：第一个安全窗口解冻。
    queue.gate.set_stage(SleepStage.AWAKE)
    released = queue.wake_up_window()

    # 无损：50 条一条不少，ID 全量对账。
    assert len(released) == 50
    assert [p.pulse_id for p in released] == suspended_ids
    # 有序：按原始时间戳聚合呈现。
    timestamps = [p.occurred_at for p in released]
    assert timestamps == sorted(timestamps)
    assert queue.gate.silent_queue_size == 0


def test_gate4_batched_events_also_release_in_order() -> None:
    queue = WakeCooldownQueue()
    queue.gate.set_stage(SleepStage.DEEP_SLEEP)
    for i in range(20):
        queue.enqueue(_pulse(i, signature="night-hr", at=T0 + i * 0.2))
    (batch,) = queue.flush_window(now=T0 + 5)
    assert queue.route_batch(batch, now=T0 + 5) == "suspended"

    queue.gate.set_stage(SleepStage.AWAKE)
    released = queue.wake_up_window()
    assert len(released) == 1
    assert isinstance(released[0], BatchedWakeEvent)
    assert released[0].count == 20
