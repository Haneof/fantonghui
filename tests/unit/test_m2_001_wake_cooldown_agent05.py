"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸 —— 四大硬门禁验收。
独立命名并存线（agent-05）：本文件为 agent-05 共存线交付版本的独立验收测试，与规范实现的验收测试并存，零覆盖、互不依赖。

实战业务情境：羽毛球赛后 50Hz 传感器高频脉冲 + 凌晨 02:00~06:00 深度睡眠。
- 门禁 1：5 秒内 250 条离散脉冲合并为单条批次事件（禁止逐条唤醒下游）；
- 门禁 2：非致命提醒 15~30 分钟自适应冷却硬防护；
- 门禁 3：DEEP_SLEEP 阶段除 P0 硬件直穿外全部静默，一般振动严格为 0；
- 门禁 4：晨间第一安全窗口静默队列无损解冻、有序聚合呈现。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.safety_bypass import WakePriority
from aios_core.wake import dispatcher
from aios_core.wake.cooldown_queue_agent05 import (
    COOLDOWN_CEILING,
    COOLDOWN_FLOOR,
    MERGE_WINDOW,
    PhysicalPulse,
    SleepPhase,
    WakeCooldownQueue,
    WakeNotification,
)

UTC = timezone.utc
NIGHT = datetime(2026, 8, 12, 2, 0, tzinfo=UTC)  # 02:00 进入深度睡眠


def pulse(seq: int, at: datetime, channel: str = "accel_x", value: float = 1.0) -> PhysicalPulse:
    return PhysicalPulse(seq=seq, at=at, channel=channel, value=value)


def note(nid: str, at: datetime, category: str = "task_reminder", **kw) -> WakeNotification:
    return WakeNotification(notification_id=nid, at=at, category=category, **kw)


# ----------------------------------------------------------------------
# 门禁 1：高频传感器防抖与合并窗口
# ----------------------------------------------------------------------


class TestHighFrequencyMergeWindow:
    def test_250_pulses_in_5s_merge_into_single_batch(self):
        queue = WakeCooldownQueue()
        t0 = datetime(2026, 8, 12, 20, 30, tzinfo=UTC)  # 羽毛球赛后
        batches = []
        for i in range(250):  # 50Hz × 5s = 250 条离散脉冲
            p = pulse(i, t0 + timedelta(seconds=i * 0.02), channel="accel_x", value=round(0.5 + 0.3 * (i % 7) / 6, 3))
            batch = queue.ingest_physical_pulse(p)
            if batch is not None:
                batches.append(batch)
        # 250 条跨度 4.98s < 5s：缓冲内不关窗，flush 后仅 1 条批次
        assert batches == []
        batch = queue.flush_pending()
        assert batch is not None
        assert batch.pulse_count == 250
        assert batch.first_seq == 0
        assert batch.last_seq == 249
        assert batch.window_end - batch.window_start < MERGE_WINDOW
        # 下游心智流水线只被唤醒 1 次（严禁 250 次逐条唤醒）
        assert queue.downstream_wakes == 1

    def test_two_waves_produce_two_batches_not_500_wakes(self):
        queue = WakeCooldownQueue()
        t0 = datetime(2026, 8, 12, 20, 30, tzinfo=UTC)
        for wave in range(2):
            for i in range(250):
                p = pulse(wave * 250 + i, t0 + timedelta(seconds=wave * 5 + i * 0.02))
                queue.ingest_physical_pulse(p)
        queue.flush_pending()
        assert queue.downstream_wakes == 2  # 两条批次，不是 500 次

    def test_window_boundary_splits_batches(self):
        queue = WakeCooldownQueue()
        t0 = datetime(2026, 8, 12, 20, 30, tzinfo=UTC)
        emitted = []
        # 第 251 条落在 >= 5s 处：自动关闭第一窗
        for i in range(251):
            batch = queue.ingest_physical_pulse(pulse(i, t0 + timedelta(seconds=i * 0.02)))
            if batch is not None:
                emitted.append(batch)
        assert len(emitted) == 1
        assert emitted[0].pulse_count == 250
        tail = queue.flush_pending()
        assert tail is not None and tail.pulse_count == 1
        assert queue.downstream_wakes == 2

    def test_dedup_statistics_within_batch(self):
        queue = WakeCooldownQueue()
        t0 = datetime(2026, 8, 12, 20, 30, tzinfo=UTC)
        # 100 条重复值 + 100 条重复值（另一通道）+ 50 条抖动值
        for i in range(100):
            queue.ingest_physical_pulse(pulse(i, t0 + timedelta(milliseconds=i), channel="hr", value=165.0))
        for i in range(100):
            queue.ingest_physical_pulse(pulse(100 + i, t0 + timedelta(milliseconds=i), channel="accel_z", value=5.2))
        for i in range(50):
            queue.ingest_physical_pulse(pulse(200 + i, t0 + timedelta(milliseconds=i), channel="hrv", value=30.0 + i * 0.5))
        batch = queue.flush_pending()
        assert batch is not None
        assert batch.channels["hr"].count == 100 and batch.channels["hr"].unique == 1
        assert batch.channels["accel_z"].count == 100 and batch.channels["accel_z"].unique == 1
        assert batch.channels["hrv"].count == 50 and batch.channels["hrv"].unique == 50
        assert batch.channels["hr"].mean_value == 165.0


# ----------------------------------------------------------------------
# 门禁 2：冷却时间硬防护（15~30 分钟自适应）
# ----------------------------------------------------------------------


class TestCooldownHardProtection:
    def test_cooldown_suppresses_then_adapts_within_15_30(self):
        queue = WakeCooldownQueue()
        t0 = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
        seen = []
        # t0+0：投递（首次）
        seen.append(queue.notify(note("n0", t0)).action)
        # t0+10min：冷却中（<15min）→ 抑制，冷却升级 15→20
        seen.append(queue.notify(note("n1", t0 + timedelta(minutes=10))).action)
        assert queue.current_cooldown == timedelta(minutes=20)
        # t0+20min：恰好 20min（不 < 20）→ 投递，冷却回落 15
        seen.append(queue.notify(note("n2", t0 + timedelta(minutes=20))).action)
        assert queue.current_cooldown == COOLDOWN_FLOOR
        # t0+30min：距上次投递 10min < 15 → 抑制，冷却 15→20
        seen.append(queue.notify(note("n3", t0 + timedelta(minutes=30))).action)
        assert queue.current_cooldown == timedelta(minutes=20)
        # t0+50min：距上次投递 20min（不 < 20）→ 投递
        seen.append(queue.notify(note("n4", t0 + timedelta(minutes=50))).action)
        assert seen == ["DELIVERED", "SUPPRESSED_COOLDOWN", "DELIVERED", "SUPPRESSED_COOLDOWN", "DELIVERED"]
        assert queue.general_vibration_count == 3
        assert queue.suppressed_count == 2
        # 冷却期恒在 [15, 30] 区间
        assert COOLDOWN_FLOOR <= queue.current_cooldown <= COOLDOWN_CEILING

    def test_cooldown_escalates_to_ceiling_30(self):
        queue = WakeCooldownQueue()
        t0 = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
        queue.notify(note("n0", t0))
        # 连续 4 次冷却中打扰：15→20→25→30→30（封顶）
        for i, expected in enumerate([timedelta(minutes=20), timedelta(minutes=25), timedelta(minutes=30), timedelta(minutes=30)]):
            queue.notify(note(f"n{i + 1}", t0 + timedelta(minutes=5 * (i + 1))))
            assert queue.current_cooldown == expected
        assert queue.current_cooldown == COOLDOWN_CEILING

    def test_acknowledge_resets_cooldown_to_floor(self):
        queue = WakeCooldownQueue()
        t0 = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
        queue.notify(note("n0", t0))
        queue.notify(note("n1", t0 + timedelta(minutes=10)))  # 抑制 → 20min
        assert queue.current_cooldown == timedelta(minutes=20)
        queue.acknowledge()
        assert queue.current_cooldown == COOLDOWN_FLOOR

    def test_p0_bypasses_cooldown_entirely(self):
        pulses = []
        queue = WakeCooldownQueue(pulse_dispatcher=lambda action_code, payload: pulses.append((action_code, payload)) or True)
        t0 = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
        queue.notify(note("n0", t0))
        # 冷却中的 P0：直接硬件直穿，不受冷却约束
        result = queue.notify(note("p0", t0 + timedelta(minutes=1), priority=WakePriority.P0_CRITICAL_SAFETY, payload={"hr_bpm": 165}))
        assert result.action == "P0_HARDWARE_PASSTHROUGH"
        assert len(pulses) == 1
        assert pulses[0][0] == "EMERGENCY_BROADCAST_AND_SOS"


# ----------------------------------------------------------------------
# 门禁 3：深度睡眠绝对静默闸（DEEP_SLEEP GATE）
# ----------------------------------------------------------------------


class TestDeepSleepAbsoluteSilence:
    def _night_queue(self, pulse_spy: list):
        return WakeCooldownQueue(pulse_dispatcher=lambda action_code, payload: pulse_spy.append((action_code, payload)) or True)

    def test_all_general_notifications_silent_with_zero_vibration(self):
        pulses = []
        queue = self._night_queue(pulses)
        queue.set_sleep_phase(SleepPhase.DEEP_SLEEP, NIGHT)
        # 02:00~06:00 深度睡眠：任务提醒/复盘反思/一般通知全部挂起
        results = [
            queue.notify(note("task:sign", NIGHT + timedelta(minutes=30), category="task_reminder")),
            queue.notify(note("retro:day", NIGHT + timedelta(minutes=60), category="retrospective")),
            queue.notify(note("general:news", NIGHT + timedelta(minutes=90), category="general")),
            queue.notify(note("task:review", NIGHT + timedelta(minutes=120), category="task_reminder")),
        ]
        assert all(r.action == "SILENT_SUSPENDED_DEEP_SLEEP" for r in results)
        assert all(not r.vibration_counted for r in results)
        # 物理马达振动次数严格为 0
        assert queue.general_vibration_count == 0
        assert pulses == []  # 未触发任何硬件脉冲
        # 静默队列无损暂存 4 条
        assert [n.notification_id for n in queue.pending_silent()] == ["task:sign", "retro:day", "general:news", "task:review"]

    def test_p0_cardiac_fall_punches_through_deep_sleep(self):
        pulses = []
        queue = self._night_queue(pulses)
        queue.set_sleep_phase(SleepPhase.DEEP_SLEEP, NIGHT)
        # 03:15 心梗跌倒：P0 硬件直穿（宪法：生命安全高于一切）
        result = queue.notify(
            note(
                "p0:0315",
                NIGHT + timedelta(hours=1, minutes=15),
                priority=WakePriority.P0_CRITICAL_SAFETY,
                payload={"hr_bpm_peak": 165, "g_force_peak": 5.2, "context": "deep_sleep_nocturnal"},
            )
        )
        assert result.action == "P0_HARDWARE_PASSTHROUGH"
        assert result.hardware_pulse_sent is True
        assert queue.p0_hardware_pulse_count == 1
        assert pulses[0][1]["hr_bpm_peak"] == 165
        # P0 直穿不污染一般振动计数
        assert queue.general_vibration_count == 0

    def test_light_sleep_is_not_deep_sleep_gate(self):
        queue = self._night_queue([])
        queue.set_sleep_phase(SleepPhase.LIGHT_SLEEP, NIGHT)
        result = queue.notify(note("n:light", NIGHT + timedelta(minutes=10)))
        assert result.action == "DELIVERED"  # 浅睡不触发绝对静默闸（仅 DEEP_SLEEP）

    def test_default_pulse_dispatcher_uses_v1_channel(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dispatcher, "dispatch_emergency_hardware_pulse", lambda action_code, payload: calls.append(action_code) or True)
        queue = WakeCooldownQueue()  # 缺省 pulse_dispatcher → dispatcher 模块命名空间
        queue.set_sleep_phase(SleepPhase.DEEP_SLEEP, NIGHT)
        queue.notify(note("p0:default", NIGHT, priority=WakePriority.P0_CRITICAL_SAFETY, payload={}))
        assert calls == ["EMERGENCY_BROADCAST_AND_SOS"]


# ----------------------------------------------------------------------
# 门禁 4：静默队列无损唤醒延递（第一安全窗口）
# ----------------------------------------------------------------------


class TestSilentQueueLosslessDeferral:
    def test_morning_thaw_lossless_ordered_grouped(self):
        pulses = []
        queue = WakeCooldownQueue(pulse_dispatcher=lambda a, p: pulses.append(a) or True)
        queue.set_sleep_phase(SleepPhase.DEEP_SLEEP, NIGHT)
        queue.notify(note("task:sign", NIGHT + timedelta(minutes=30), category="task_reminder"))
        queue.notify(note("retro:day", NIGHT + timedelta(minutes=60), category="retrospective"))
        queue.notify(note("general:news", NIGHT + timedelta(minutes=90), category="general"))
        queue.notify(note("task:review", NIGHT + timedelta(minutes=120), category="task_reminder"))
        # 05:58 仍在深睡：无投递、静默队列无损暂存（mark_awake 仅在用户清醒时调用）
        assert queue.general_vibration_count == 0
        assert len(queue.pending_silent()) == 4

        # 06:05 清醒下床：第一安全窗口
        morning = NIGHT + timedelta(hours=4, minutes=5)
        thawed = queue.mark_awake(morning)
        # 无损：4 条全部延递；有序：按原始到达顺序
        assert [n.notification_id for n in thawed] == ["task:sign", "retro:day", "general:news", "task:review"]
        assert [n.at for n in thawed] == sorted(n.at for n in thawed)
        # 静默队列已清空
        assert queue.pending_silent() == ()
        assert queue.sleep_phase is SleepPhase.AWAKE
        # 解冻呈现分组（组内保持原始顺序）
        view = queue.aggregated_thaw_view(thawed)
        assert view == {
            "task_reminder": ("task:sign", "task:review"),
            "retrospective": ("retro:day",),
            "general": ("general:news",),
        }
        # 解冻投递计入一般振动（已清醒）
        assert queue.general_vibration_count == 4

    def test_thaw_only_in_first_safe_window(self):
        queue = WakeCooldownQueue(pulse_dispatcher=lambda a, p: True)
        queue.set_sleep_phase(SleepPhase.DEEP_SLEEP, NIGHT)
        queue.notify(note("n:1", NIGHT + timedelta(minutes=30)))
        # 第一安全窗口：解冻 1 条
        first = queue.mark_awake(NIGHT + timedelta(hours=4, minutes=5))
        assert [n.notification_id for n in first] == ["n:1"]
        # 已清醒后的普通通知正常投递；再次 mark_awake：无事发生
        queue.notify(note("n:2", NIGHT + timedelta(hours=5)))
        assert queue.mark_awake(NIGHT + timedelta(hours=6)) == ()
        assert queue.general_vibration_count == 2

    def test_p0_between_suspensions_not_lost_in_thaw(self):
        pulses = []
        queue = WakeCooldownQueue(pulse_dispatcher=lambda a, p: pulses.append(a) or True)
        queue.set_sleep_phase(SleepPhase.DEEP_SLEEP, NIGHT)
        queue.notify(note("n:1", NIGHT + timedelta(minutes=30)))
        queue.notify(note("p0", NIGHT + timedelta(minutes=45), priority=WakePriority.P0_CRITICAL_SAFETY, payload={"g": 5.2}))
        queue.notify(note("n:2", NIGHT + timedelta(minutes=60)))
        assert queue.p0_hardware_pulse_count == 1
        assert pulses == ["EMERGENCY_BROADCAST_AND_SOS"]
        # P0 不入静默队列（已即时直穿）：解冻只延递 2 条一般通知
        thawed = queue.mark_awake(NIGHT + timedelta(hours=4, minutes=5))
        assert [n.notification_id for n in thawed] == ["n:1", "n:2"]


# ----------------------------------------------------------------------
# 构造契约
# ----------------------------------------------------------------------


class TestConstructionContract:
    def test_invalid_cooldown_bounds_rejected(self):
        with pytest.raises(ValueError, match="cooldown"):
            WakeCooldownQueue(cooldown_floor=timedelta(minutes=35), cooldown_ceiling=timedelta(minutes=30))
        with pytest.raises(ValueError, match="cooldown"):
            WakeCooldownQueue(cooldown_floor=timedelta(0), cooldown_ceiling=timedelta(minutes=30))

    def test_empty_flush_is_none(self):
        queue = WakeCooldownQueue()
        assert queue.flush_pending() is None
