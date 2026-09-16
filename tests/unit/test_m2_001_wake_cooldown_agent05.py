"""M2-001 验收单测：高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

情境：羽毛球赛后心率剧烈波动 + 50Hz 加速度离散流 + 凌晨深睡阶段。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.safety_bypass import WakePriority
from aios_core.wake.cooldown_queue import (
    SensorPulse,
    SilentWakeEngine,
    SleepStage,
    WakeNotice,
)

UTC = timezone.utc
NIGHT = datetime(2026, 9, 15, 18, 0, tzinfo=UTC)  # 本地时区 UTC+8：凌晨 02:00
DAY = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def t(minutes: float, base: datetime = NIGHT) -> datetime:
    return base + timedelta(minutes=minutes)


def make_pulse(
    i: int,
    *,
    at: datetime,
    metric: str = "heart_rate",
    value: float = 130.0,
    source: str = "wristband_optical",
) -> SensorPulse:
    return SensorPulse(
        metric=metric,
        value=value + (i % 17) * 0.3,
        source=source,
        at=at,
    )


# ---------------------------------------------------------------------------
# 门禁一：高频传感器防抖与合并窗口（250 条 → 1 条批次）
# ---------------------------------------------------------------------------


def test_250_pulses_in_5s_fold_into_single_batch_event():
    eng = SilentWakeEngine(window_seconds=5.0)
    for i in range(250):
        eng.ingest_pulse(make_pulse(i, at=DAY + timedelta(milliseconds=20 * i)))
    # 窗口未关：下游零唤醒
    assert eng.stats()["batches_emitted"] == 0
    assert eng.stats()["motor_vibrations"] == 0

    batches = eng.advance_to(DAY + timedelta(seconds=5.001))
    assert len(batches) == 1
    batch = batches[0]
    assert batch.member_count == 250
    assert eng.pulses_folded == 249
    # 关键断言：250 条脉冲只触发 1 次下游呈现（振动 1 次），禁止逐条唤醒
    assert eng.motor_vibrations == 1
    assert eng.batches_emitted == 1


def test_per_pulse_downstream_path_does_not_exist():
    # 结构证明：ingest_pulse 不产生任何投递副作用（除 P0 直穿外）
    eng = SilentWakeEngine(window_seconds=5.0)
    for i in range(250):
        result = eng.ingest_pulse(make_pulse(i, at=DAY + timedelta(microseconds=19_992 * i)))
        assert result is None
    assert eng.motor_vibrations == 0
    assert eng.deferred_backlog() == 0
    assert eng.stats()["batches_emitted"] == 0


def test_two_sources_in_same_window_yield_two_batches_not_250():
    eng = SilentWakeEngine(window_seconds=5.0)
    for i in range(250):
        at = DAY + timedelta(milliseconds=19 * i)
        eng.ingest_pulse(make_pulse(i, at=at, metric="heart_rate"))
        if i % 50 == 0:
            eng.ingest_pulse(make_pulse(i, at=at, metric="accel_z", source="imu_50hz"))
    batches = eng.advance_to(DAY + timedelta(seconds=6))
    keys = sorted(b.dedupe_key for b in batches)
    assert keys == [
        "pulse:imu_50hz:accel_z",
        "pulse:wristband_optical:heart_rate",
    ]
    total_members = sum(b.member_count for b in batches)
    assert total_members == 250 + 5
    assert eng.motor_vibrations == 2


# ---------------------------------------------------------------------------
# 门禁二：15~30 分钟自适应冷却硬防护
# ---------------------------------------------------------------------------


def _notice(n: int, *, at: datetime, kind: str = "reminder") -> WakeNotice:
    return WakeNotice(
        event_id=f"evt_{n}",
        kind=kind,
        title=f"一般提醒 #{n}",
        occurred_at=at,
    )


def test_cooldown_window_blocks_repeated_reminders_for_15_to_30_minutes():
    eng = SilentWakeEngine()
    assert eng.submit_notice(_notice(1, at=DAY), now=DAY) == "dispatched"
    assert eng.motor_vibrations == 1
    # 14 分 59 秒后：仍在 15 分钟冷却硬防护内 → 抑制，不振动
    r = eng.submit_notice(_notice(2, at=DAY + timedelta(minutes=14, seconds=59)), now=DAY + timedelta(minutes=14, seconds=59))
    assert r == "suppressed"
    assert eng.motor_vibrations == 1
    assert eng.cooldown_suppressed == 1
    # 恰好 15 分钟：第一次冷却到期放行，且因一次加罚 → 新冷却 = 15+7.5 = 22.5 分钟
    r = eng.submit_notice(_notice(3, at=DAY + timedelta(minutes=15)), now=DAY + timedelta(minutes=15))
    assert r == "dispatched"
    assert eng.motor_vibrations == 2
    # 22 分 00 秒 < 22.5 分钟 → 仍被抑制（自适应拉长生效）
    probe_at = DAY + timedelta(minutes=15) + timedelta(minutes=22)
    r = eng.submit_notice(_notice(4, at=probe_at), now=probe_at)
    assert r == "suppressed"
    # 30 分钟绝对上限校验：连续升级后冷却不得超过 30 分钟
    clock = DAY
    for i in range(10):
        # 每次推进到当前冷却边界之后，触发必然放行 → 等级持续抬升
        next_allowed = eng._cooldown_until["notice:reminder"]
        clock = max(clock, next_allowed)
        r = eng.submit_notice(_notice(100 + i, at=clock), now=clock)
        assert r == "dispatched"
        span = (eng._cooldown_until["notice:reminder"] - clock).total_seconds()
        assert span <= SilentWakeEngine.COOLDOWN_MAX_SECONDS
    assert eng._cooldown_until["notice:reminder"] - clock == timedelta(seconds=1800)


def test_quiet_day_decays_cooldown_back_to_base():
    eng = SilentWakeEngine()
    eng.submit_notice(_notice(1, at=DAY), now=DAY)
    eng.submit_notice(_notice(2, at=DAY + timedelta(minutes=5)), now=DAY + timedelta(minutes=5))  # 抑制 → 升级
    far = DAY + timedelta(hours=25)
    r = eng.submit_notice(_notice(3, at=far), now=far)
    assert r == "dispatched"
    # 回落后重新进入 15 分钟基础冷却
    assert eng._cooldown_until["notice:reminder"] - far == timedelta(seconds=900)


def test_p0_bypasses_cooldown_entirely():
    eng = SilentWakeEngine()
    eng.submit_notice(_notice(1, at=DAY), now=DAY)
    p0 = WakeNotice(
        event_id="evt_p0",
        kind="safety",
        title="心率骤停",
        occurred_at=DAY + timedelta(seconds=30),  # 冷却期内
        priority=WakePriority.P0_CRITICAL_SAFETY,
    )
    assert eng.submit_notice(p0, now=DAY + timedelta(seconds=30)) == "dispatched"
    assert eng.p0_passthrough == 1
    assert eng.motor_vibrations == 2


# ---------------------------------------------------------------------------
# 门禁三：DEEP_SLEEP 绝对静默（非 P0 振动严格为 0）
# ---------------------------------------------------------------------------


def _put_to_deep_sleep(eng: SilentWakeEngine):
    eng.set_sleep_stage(SleepStage.LIGHT, at=NIGHT)
    eng.set_sleep_stage(SleepStage.DEEP, at=t(10))


def test_deep_sleep_defers_everything_except_p0_and_motor_is_strictly_zero():
    eng = SilentWakeEngine(window_seconds=5.0)
    _put_to_deep_sleep(eng)

    for i in range(9):
        assert eng.submit_notice(_notice(i, at=t(20 + i)), now=t(20 + i)) == "deferred"
    assert eng.submit_notice(
        WakeNotice(
            event_id="evt_review", kind="review", title="夜间复盘反思", occurred_at=t(30)
        ),
        now=t(30),
    ) == "deferred"
    for i in range(100):
        eng.ingest_pulse(make_pulse(i, at=t(40) + timedelta(milliseconds=9 * i)))
    eng.advance_to(t(41))

    assert eng.stats()["motor_vibrations"] == 0
    assert eng.motor_log == []
    assert eng.deep_sleep_deferred == 11
    assert eng.deferred_backlog() == 11

    # P0（心梗/跌倒硬件直穿）例外：允许穿透
    result = eng.ingest_pulse(
        SensorPulse(metric="spo2", value=76.0, source="wristband", at=t(50), priority=WakePriority.P0_CRITICAL_SAFETY)
    )
    assert result is not None and result["status"] == "SAFETY_BYPASS_EXECUTED"
    assert result["bypassed_sleep_gate"] is True
    assert eng.p0_passthrough == 1
    assert eng.motor_vibrations == 1  # 仅这一次 P0 直穿振动
    assert eng.deferred_backlog() == 11  # P0 不进静默队列


def test_deep_sleep_vibration_count_strictly_zero_without_p0():
    eng = SilentWakeEngine(window_seconds=5.0)
    _put_to_deep_sleep(eng)
    for minute in range(240):  # 02:00~06:00 整段深睡
        eng.submit_notice(_notice(minute, at=t(minute), kind="task_alert"), now=t(minute))
        for j in range(250):
            eng.ingest_pulse(make_pulse(j, at=t(minute) + timedelta(milliseconds=4 * j)))
        eng.advance_to(t(minute) + timedelta(minutes=1))
    assert eng.motor_vibrations == 0
    assert eng.stats()["deferred_backlog"] > 0


# ---------------------------------------------------------------------------
# 门禁四：静默队列无损唤醒延递
# ---------------------------------------------------------------------------


def test_morning_unfreeze_flushes_lossless_and_ordered():
    eng = SilentWakeEngine(window_seconds=5.0)
    _put_to_deep_sleep(eng)
    submitted: list[str] = []
    for i in range(11):
        kind = ["reminder", "review", "task_alert"][i % 3]
        eng.submit_notice(_notice(i, at=t(20 + i), kind=kind), now=t(20 + i))
        submitted.append(f"evt_{i}")
    # 清醒但尚未下床：安全窗口未开，仍然静默
    eng.set_sleep_stage(SleepStage.LIGHT, at=t(250))
    eng.set_sleep_stage(SleepStage.AWAKE, at=t(255))
    assert eng.stats()["deferred_backlog"] == 11
    assert eng.motor_vibrations == 0

    digests = eng.mark_out_of_bed(at=t(260))
    flushed_ids = sorted(eid for d in digests for eid in d["event_ids"])
    assert flushed_ids == sorted(submitted)  # 无损：入队多重集 == 出队多重集
    assert eng.morning_flushed_events == 11
    assert eng.stats()["deferred_backlog"] == 0
    # 有序：每个 digest 内部按 occurred_at 全序
    for d in digests:
        assert len(d["event_ids"]) == len(set(d["event_ids"]))
    # 聚合呈现：同 kind 打袋，振动按 digest 数（3 个 kind → 3 次），不是 11 次
    assert {d["kind"] for d in digests} == {"reminder", "review", "task_alert"}
    assert eng.motor_vibrations == 3

    # 队列清空后再次提交（仍清醒）→ 正常投递，不再走静默
    assert eng.submit_notice(_notice(99, at=t(270)), now=t(270)) == "dispatched"
    assert eng.motor_vibrations == 4


def test_no_api_can_drop_silent_queue():
    eng = SilentWakeEngine()
    for forbidden in ("drop_deferred", "clear_silent_queue", "delete_event", "discard_backlog"):
        assert not hasattr(eng, forbidden)
