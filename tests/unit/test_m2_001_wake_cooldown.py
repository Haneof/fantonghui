"""M2-001 唤醒冷却队列——四大硬门禁的机械证。

  1. 防抖合并：5 秒涌入 250 条同型脉冲 → 下游恰好 1 次唤醒，单批 merged_count=250
  2. 冷却硬防护：交付后 15min 基线冷却，压批自适应 +5min 封顶 30min；否决不丢件
  3. DEEP_SLEEP 绝对静默：非 P0 全挂起、马达结构性恒 0；P0 无视睡眠相直穿
  4. 无损晨间延递：离眠第一安全窗一次性有序聚合呈现，一条不丢、一次唤一次达
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.wake.cooldown_queue import (
    COOLDOWN_BASE_SECONDS,
    COOLDOWN_MAX_SECONDS,
    COOLDOWN_STEP_SECONDS,
    MERGE_WINDOW_SECONDS,
    CountingMotorPort,
    SleepPhase,
    WakeCooldownQueue,
    WakeEvent,
    WakePriority,
)

T0 = datetime(2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc)


def _pulse(i: int, *, kind: str = "hr_spike", at: datetime = T0,
           priority: WakePriority = WakePriority.NORMAL) -> WakeEvent:
    return WakeEvent(event_id=f"{kind}-{i:04d}", kind=kind, priority=priority,
                     payload=(f"bpm={120 + i % 15}",), occurred_at=at)


# ---------------------------------------------------------------------------
# 门禁 1：5 秒 250 脉冲 → 一次唤醒
# ---------------------------------------------------------------------------


def test_250_pulses_in_5s_merge_to_single_batch():
    motor = CountingMotorPort()
    q = WakeCooldownQueue(motor=motor)
    for i in range(250):
        q.ingest(_pulse(i, at=T0 + timedelta(milliseconds=i * 20)), T0 + timedelta(milliseconds=i * 20))
    q.flush(T0 + timedelta(seconds=MERGE_WINDOW_SECONDS))
    emissions = q.drain_emissions()
    assert len(emissions) == 1, "下游心智流水线每窗至多被唤一次"
    batch = emissions[0]
    assert batch.merged_count == 250 and batch.kind == "hr_spike"
    assert motor.vibrations == 0, "NORMAL 事件永不触碰马达"
    assert len(batch.event_ids) == 250


def test_two_kinds_emit_two_batches_no_cross_merge():
    q = WakeCooldownQueue()
    for i in range(10):
        q.ingest(_pulse(i, kind="hr_spike"), T0)
        q.ingest(_pulse(i + 100, kind="accel_burst"), T0)
    q.flush(T0 + timedelta(seconds=MERGE_WINDOW_SECONDS))
    kinds = sorted(e.kind for e in q.drain_emissions())
    assert kinds == ["accel_burst", "hr_spike"]


def test_duplicate_event_id_is_idempotent():
    q = WakeCooldownQueue()
    e = _pulse(0)
    q.ingest(e, T0)
    q.ingest(e, T0 + timedelta(seconds=1))
    q.flush(T0 + timedelta(seconds=MERGE_WINDOW_SECONDS))
    assert q.drain_emissions()[0].merged_count == 1


# ---------------------------------------------------------------------------
# 门禁 2：冷却硬防护 + 自适应阶梯 + 否决不丢件
# ---------------------------------------------------------------------------


def test_cooldown_suppresses_then_delivers_after_base():
    q = WakeCooldownQueue()
    q.ingest(_pulse(0), T0)
    q.flush(T0 + timedelta(seconds=MERGE_WINDOW_SECONDS))
    assert len(q.drain_emissions()) == 1

    # 5 分钟后再来一批：冷却内否决，且件不丢
    q.ingest(_pulse(1), T0 + timedelta(minutes=5))
    q.flush(T0 + timedelta(minutes=5, seconds=MERGE_WINDOW_SECONDS))
    assert q.drain_emissions() == []
    assert q.suppressed_batches == 1
    assert q.cooldown_of("hr_spike") == COOLDOWN_BASE_SECONDS + COOLDOWN_STEP_SECONDS

    # 15+5 分钟冷却过后：与缓冲合流交付（无损）
    q.flush(T0 + timedelta(minutes=21))
    later = q.drain_emissions()
    assert len(later) == 1 and later[0].merged_count == 1


def test_adaptive_cooldown_ladder_bounded_15_to_30_minutes():
    q = WakeCooldownQueue()
    q.ingest(_pulse(0), T0)
    q.flush(T0 + timedelta(seconds=MERGE_WINDOW_SECONDS))
    q.drain_emissions()
    assert q.cooldown_of("hr_spike") == COOLDOWN_BASE_SECONDS

    # 连续压批：阶梯上行直到封顶
    for step in range(1, 12):
        q.ingest(_pulse(step), T0 + timedelta(minutes=step))
        q.flush(T0 + timedelta(minutes=step, seconds=MERGE_WINDOW_SECONDS))
    q.drain_emissions()
    cd = q.cooldown_of("hr_spike")
    assert cd == COOLDOWN_MAX_SECONDS
    assert COOLDOWN_BASE_SECONDS == 900 <= cd <= 1800 == COOLDOWN_MAX_SECONDS
    assert q.suppressed_batches == 11


# ---------------------------------------------------------------------------
# 门禁 3：DEEP_SLEEP 绝对静默 vs P0 硬件直穿
# ---------------------------------------------------------------------------


def test_deep_sleep_suspends_everything_but_p0():
    motor = CountingMotorPort()
    q = WakeCooldownQueue(motor=motor)
    q.set_sleep_phase(SleepPhase.DEEP_SLEEP)
    for i in range(10):
        q.ingest(_pulse(i, at=T0 + timedelta(minutes=i)), T0 + timedelta(minutes=i))
    q.flush(T0 + timedelta(minutes=10))
    assert q.drain_emissions() == []
    assert motor.vibrations == 0, "深睡期物理马达振动次数严格为 0"
    assert q.suspended_count == 10, "静默无损：全部挂起在队"

    sos = WakeEvent(event_id="sos-1", kind="fall_detect",
                    priority=WakePriority.P0_CRITICAL_SAFETY,
                    payload=("impact=9.8g",), occurred_at=T0 + timedelta(minutes=11))
    q.ingest(sos, T0 + timedelta(minutes=11))
    emissions = q.drain_emissions()
    assert len(emissions) == 1 and emissions[0].event_ids == ("sos-1",)
    assert motor.vibrations == 1, "P0 无视睡眠相直穿（生命安全高于一切）"
    assert q.suspended_count == 10, "P0 不泄洪：挂起件原样保留"


def test_p0_bypasses_cooldown_too():
    q = WakeCooldownQueue()
    q.ingest(_pulse(0), T0)
    q.flush(T0 + timedelta(seconds=MERGE_WINDOW_SECONDS))
    q.drain_emissions()  # 进入 15min 冷却

    sos = WakeEvent(event_id="sos-2", kind="heart_stall",
                    priority=WakePriority.P0_CRITICAL_SAFETY,
                    occurred_at=T0 + timedelta(minutes=3))
    q.ingest(sos, T0 + timedelta(minutes=3))
    emissions = q.drain_emissions()
    assert len(emissions) == 1, "P0 连冷却也直穿"


# ---------------------------------------------------------------------------
# 门禁 4：晨间无损唤醒延递
# ---------------------------------------------------------------------------


def test_morning_defrost_single_ordered_aggregate_lossless():
    q = WakeCooldownQueue()
    q.set_sleep_phase(SleepPhase.DEEP_SLEEP)
    suspended_events = [_pulse(i, kind="hr_spike", at=T0 + timedelta(minutes=i * 7)) for i in range(6)]
    suspended_events += [_pulse(100 + i, kind="task_remind", at=T0 + timedelta(minutes=3 + i * 5)) for i in range(4)]
    for e in suspended_events:
        q.ingest(e, e.occurred_at)
    assert q.drain_emissions() == []

    q.on_user_wake(T0 + timedelta(hours=8))
    emissions = q.drain_emissions()
    assert len(emissions) == 1, "晨间一次性聚合呈现，仅唤一次"
    agg = emissions[0]
    assert agg.deferred is True
    assert agg.merged_count == 10
    assert set(agg.kinds) == {"hr_spike", "task_remind"}
    ids = [e.event_id for e in sorted(suspended_events, key=lambda e: (e.occurred_at, e.event_id))]
    assert list(agg.event_ids) == ids, "严格按发生时刻有序呈现，一条不丢"
    assert q.suspended_count == 0


def test_morning_aggregate_resets_cooldown_and_recovers_normal_flow():
    q = WakeCooldownQueue()
    q.set_sleep_phase(SleepPhase.DEEP_SLEEP)
    q.ingest(_pulse(0, kind="hr_spike", at=T0), T0)
    q.on_user_wake(T0 + timedelta(hours=7))
    assert len(q.drain_emissions()) == 1

    # 恢复常规流：新事件走合并窗正常交付
    q.ingest(_pulse(1, kind="hr_spike"), T0 + timedelta(hours=8))
    q.flush(T0 + timedelta(hours=8, seconds=MERGE_WINDOW_SECONDS))
    out = q.drain_emissions()
    assert len(out) == 1 and out[0].deferred is False


def test_event_requires_occurred_at_and_nonempty_ids():
    with pytest.raises(ValueError, match="occurred_at"):
        WakeEvent(event_id="e1", kind="k", priority=WakePriority.NORMAL)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="不得为空"):
        WakeEvent(event_id="", kind="k", priority=WakePriority.NORMAL, occurred_at=T0)
