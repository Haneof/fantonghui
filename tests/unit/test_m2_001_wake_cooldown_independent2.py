"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸 四大硬门禁验收。

1. 5 秒 250 脉冲去重合并且只唤醒下游一次；
2. 提醒类冷却 15~30 分钟自适应阶梯硬防护；
3. DEEP_SLEEP：除 P0 外物理马达振动 0 次，全部无损延递；
4. 晨间安全窗口有序聚合出仓，集合严格无损。
"""

from __future__ import annotations

import pytest

from aios_core.wake.cooldown_queue_independent2 import (
    AggregatedBatch,
    CooldownWakeQueue,
    IngestDecision,
    SleepStage,
    VitalPulse,
    VitalPulseKind,
    WakePriority,
    BASE_COOLDOWN_NS,
    MAX_COOLDOWN_NS,
    COOLDOWN_STEP_NS,
    MERGE_WINDOW_NS,
)

T0 = 1_726_480_000_000_000_000
MIN_NS = 60 * 1_000_000_000


class _Recorder:
    """下游收批 + 马达计数的测试替身。"""

    def __init__(self) -> None:
        self.batches: list[AggregatedBatch] = []
        self.vibrations: list[tuple[str, int]] = []

    def downstream(self, batch: AggregatedBatch) -> None:
        self.batches.append(batch)

    def vibrate(self, pattern: str, burst_count: int) -> None:
        self.vibrations.append((pattern, burst_count))


# ---------------------------------------------------------------------------
# 门禁 1：高频传感器防抖与合并窗口（250 脉冲 / 5s -> 单批单唤醒）
# ---------------------------------------------------------------------------

def test_high_frequency_pulses_merge_to_single_batch() -> None:
    rec = _Recorder()
    queue = CooldownWakeQueue(vibrator=rec, downstream=rec.downstream)

    total, duplicates = 250, 23
    for i in range(total):
        value = 150.0 + (i % 17) * 2.4  # 赛后心率剧震 150~188bpm
        # 精确重复注入：同源同值同秒
        at_ns = T0 + (i // 50) * 1_000_000_000 + (i % 50) * 19_000_000
        if i and i % 10 == 0:
            at_ns = T0 + ((i - 5) // 50) * 1_000_000_000 + ((i - 5) % 50) * 19_000_000
            value = 150.0 + ((i - 5) % 17) * 2.4
        decision = queue.ingest(
            VitalPulse(kind=VitalPulseKind.HEART_RATE, value=value, at_ns=at_ns),
            now_ns=at_ns,
        )
        assert decision in {IngestDecision.BUFFERED_MERGING, IngestDecision.DEDUPLICATED}

    # 窗口未期满：下游 0 次
    rec_pre = len(rec.batches)
    assert rec_pre == 0

    batches = queue.flush(now_ns=T0 + MERGE_WINDOW_NS + 1)
    assert len(batches) == 1                       # 合并为单条批次
    batch = batches[0]
    assert len(rec.batches) == 1                   # 下游心智流水线只被唤醒一次
    assert queue.downstream_dispatch_count == 1
    assert batch.min_value < batch.max_value
    assert 1 <= batch.count <= total
    assert queue.dedup_dropped_count >= 1          # 精确重复已被物理去重
    assert batch.count + queue.dedup_dropped_count == total  # 账目闭合
    assert queue.vibration_invocations == 0        # 体征合并不震动（仅提醒类震）


# ---------------------------------------------------------------------------
# 门禁 2：提醒类冷却 15~30 分钟自适应硬防护
# ---------------------------------------------------------------------------

def test_cooldown_adaptive_hard_guard_15_to_30_min() -> None:
    rec = _Recorder()
    queue = CooldownWakeQueue(vibrator=rec, downstream=rec.downstream)

    def remind(at_ns: int, value: float) -> IngestDecision:
        d = queue.ingest(
            VitalPulse(kind=VitalPulseKind.TASK_REMINDER, value=value, at_ns=at_ns),
            now_ns=at_ns,
        )
        # 直接显式出窗以完成"触发"（非紧急提醒也走合并窗管线）
        queue.flush(now_ns=at_ns, force=True)
        return d

    # 首次触发：正常下发，随后进入 15 分钟基础冷却
    remind(T0, 1.0)
    assert queue.downstream_dispatch_count == 1

    # +10 分钟重触发：冷却抑制，冷却阶梯升级至 20 分钟
    at1 = T0 + 10 * MIN_NS
    assert remind(at1, 1.0) == IngestDecision.SUPPRESSED_COOLDOWN
    assert queue.downstream_dispatch_count == 1   # 没有新增下发

    # T0+21m 重触发：处于升级后的 20 分钟冷却内（自 at1 起算，滚动窗）
    at2 = T0 + 21 * MIN_NS
    assert remind(at2, 1.0) == IngestDecision.SUPPRESSED_COOLDOWN  # 阶梯 → 25min

    # T0+26m 重触发：阶梯封顶 30 分钟，窗口滚至 at3+30m
    at3 = T0 + 26 * MIN_NS
    assert remind(at3, 1.0) == IngestDecision.SUPPRESSED_COOLDOWN

    # 滚动冷却语义：每次骚扰都把窗口从当刻续满当前阶梯（防高频骚扰的核心机制）
    # 差 1ns 未满 30 分钟也拒绝，并再次续窗 —— 用户必须获得"静默满阶梯"的真正安静
    at4 = T0 + 26 * MIN_NS + MAX_COOLDOWN_NS - 1
    assert remind(at4, 1.0) == IngestDecision.SUPPRESSED_COOLDOWN
    at5 = at4 + MAX_COOLDOWN_NS
    assert remind(at5, 1.0) == IngestDecision.BUFFERED_MERGING     # 静默满 30min 才放行
    assert queue.downstream_dispatch_count == 2

    # 体征源免疫：冷却中的提醒不影响心率批次
    d = queue.ingest(
        VitalPulse(kind=VitalPulseKind.HEART_RATE, value=99.0, at_ns=at5 + 1),
        now_ns=at5 + 1,
    )
    assert d is IngestDecision.BUFFERED_MERGING


# ---------------------------------------------------------------------------
# 门禁 3：DEEP_SLEEP 绝对静默（除 P0 外振动严格为 0）
# ---------------------------------------------------------------------------

def test_deep_sleep_absolute_silence_except_p0() -> None:
    rec = _Recorder()
    queue = CooldownWakeQueue(vibrator=rec, downstream=rec.downstream)
    queue.advance_sleep_stage(SleepStage.DEEP, now_ns=T0)

    # 100 条各类一般事件：通知 / 复盘反思 / 任务提醒 / 体征
    kinds = [
        VitalPulseKind.GENERAL_NOTIFICATION,
        VitalPulseKind.REVIEW_NUDGE,
        VitalPulseKind.TASK_REMINDER,
        VitalPulseKind.HEART_RATE,
    ]
    for i in range(100):
        kind = kinds[i % 4]
        d = queue.ingest(
            VitalPulse(kind=kind, value=60.0 + i, at_ns=T0 + i * 5_000_000),
            now_ns=T0 + i * 5_000_000,
        )
        assert d is IngestDecision.DEFERRED_DEEP_SLEEP

    assert len(rec.batches) == 0                   # 下游零打扰
    assert rec.vibrations == []                    # 物理马达振动严格为 0
    assert queue.vibration_invocations == 0
    assert queue.deep_sleep_blocked_count == 100

    # P0 生命安全事件：硬件直穿，绝不被静默
    d = queue.ingest(
        VitalPulse(
            kind=VitalPulseKind.HEART_RATE,
            value=165.0,
            at_ns=T0 + 2_000_000_000,
            priority=WakePriority.P0_CRITICAL_SAFETY,
            payload={"fall_g": 5.2, "pvc_burst": 6},
        ),
        now_ns=T0 + 2_000_000_000,
    )
    assert d is IngestDecision.DISPATCHED
    assert len(rec.batches) == 1
    assert rec.vibrations == [("SOS_CRITICAL", 3)]


# ---------------------------------------------------------------------------
# 门禁 4：静默队列无损唤醒延递（晨间安全窗口有序聚合）
# ---------------------------------------------------------------------------

def test_deferred_queue_lossless_ordered_thaw() -> None:
    rec = _Recorder()
    queue = CooldownWakeQueue(vibrator=rec, downstream=rec.downstream)
    queue.advance_sleep_stage(SleepStage.DEEP, now_ns=T0)

    ingested: list[VitalPulse] = []
    # 混合优先级在深睡期入仓
    plan = [
        (VitalPulseKind.GENERAL_NOTIFICATION, WakePriority.P3_BACKGROUND, 10),
        (VitalPulseKind.TASK_REMINDER, WakePriority.P2_NOTIFICATION, 5),
        (VitalPulseKind.REVIEW_NUDGE, WakePriority.P1_ATTENTION, 3),
        (VitalPulseKind.HEART_RATE, WakePriority.P2_NOTIFICATION, 12),
    ]
    for kind, prio, n in plan:
        for i in range(n):
            p = VitalPulse(kind=kind, value=50.0 + i, at_ns=T0 + i * 3_000_000, priority=prio)
            ingested.append(p)
            assert queue.ingest(p, now_ns=p.at_ns) is IngestDecision.DEFERRED_DEEP_SLEEP

    assert queue.verify_lossless(ingested)

    # 晨间清醒下床：DEEP → AWAKE 安全窗口自动解冻
    morning = T0 + 7 * 3600 * 1_000_000_000
    report = queue.advance_sleep_stage(SleepStage.AWAKE, now_ns=morning)
    assert report is not None
    assert report.total_pulses == 30               # 30 条延递全部出仓（无损）
    assert sum(b.count for b in report.batches) == 30
    assert rec.vibrations == [("THAW_DIGEST", 1)]  # 聚合呈现恰振动 1 次

    # 呈现有序：最高优先级批次在前
    assert report.batches[0].kind is VitalPulseKind.REVIEW_NUDGE
    assert max(p.priority for p in report.batches[0].pulses) is WakePriority.P1_ATTENTION
    # 批次内每源时间升序
    for batch in report.batches:
        times = [p.at_ns for p in batch.pulses]
        assert times == sorted(times)

    # 解冻后队列清空；再次出窗为空
    assert queue._deferred == []
    assert queue.flush(now_ns=morning, force=True) == []
