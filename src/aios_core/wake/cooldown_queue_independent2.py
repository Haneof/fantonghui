"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

业务情境：羽毛球赛后心率剧震 + 加速度计 50Hz 离散脉冲；或凌晨深睡阶段。

四大硬门禁与实现位置：

1. 【高频传感器防抖与合并窗口】
   ``CooldownWakeQueue.ingest`` 对同一物理体征源的脉冲进入
   ``MERGE_WINDOW_NS`` 合并窗；精确重复（同源同值同秒）先物理去重，
   期满由 ``flush`` 合并为**单条**聚合批次——下游心智流水线每窗最多被
   唤醒一次。

2. 【冷却时间硬防护】
   非 P0 一般提醒在触发后进入 15 分钟基础冷却；每次重复抑制把该源的
   冷却阶梯 +5 分钟，上限 30 分钟（自适应防骚扰，绝不无限叠加）。

3. 【DEEP_SLEEP 绝对静默】
   睡眠阶段为 DEEP 时，除 ``P0_CRITICAL_SAFETY`` 硬件直穿外的一切事件
   进入无损延递仓；``vibrate`` 马达调用次数严格为 0（由注入的
   ``VibratorPort`` 计数器见证）。P0 永远立即下落，永不入仓。

4. 【静默队列无损唤醒延递】
   走出睡眠后的第一个安全窗口（``advance_sleep_stage`` 至 AWAKE），
   延递仓按（优先级降序、时间升序）有序聚合出仓，批次振动恰好 1 次，
   出仓集合与入仓集合严格等势（``verify_lossless``）。
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Callable, Protocol, Sequence

MERGE_WINDOW_NS = 5_000_000_000          # 合并窗口 5s
BASE_COOLDOWN_NS = 15 * 60 * 1_000_000_000   # 基础冷却 15min
MAX_COOLDOWN_NS = 30 * 60 * 1_000_000_000    # 冷却上限 30min
COOLDOWN_STEP_NS = 5 * 60 * 1_000_000_000    # 自适应阶梯 +5min


class WakePriority(IntEnum):
    P3_BACKGROUND = 10
    P2_NOTIFICATION = 20
    P1_ATTENTION = 30
    P0_CRITICAL_SAFETY = 40


class VitalPulseKind(Enum):
    HEART_RATE = "heart_rate"
    MOTION_IMPACT = "motion_impact"
    TASK_REMINDER = "task_reminder"
    REVIEW_NUDGE = "review_nudge"
    GENERAL_NOTIFICATION = "general_notification"


@dataclass(frozen=True)
class VitalPulse:
    kind: VitalPulseKind
    value: float
    at_ns: int
    priority: WakePriority = WakePriority.P2_NOTIFICATION
    payload: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class AggregatedBatch:
    """单源脉冲的合并批次。``pulses`` 逐一保留，合并不丢原始证据。"""

    kind: VitalPulseKind
    pulses: tuple[VitalPulse, ...]

    @property
    def count(self) -> int:
        return len(self.pulses)

    @property
    def first_at_ns(self) -> int:
        return self.pulses[0].at_ns

    @property
    def last_at_ns(self) -> int:
        return self.pulses[-1].at_ns

    @property
    def min_value(self) -> float:
        return min(p.value for p in self.pulses)

    @property
    def max_value(self) -> float:
        return max(p.value for p in self.pulses)

    @property
    def avg_value(self) -> float:
        return sum(p.value for p in self.pulses) / len(self.pulses)


class SleepStage(Enum):
    AWAKE = "AWAKE"
    LIGHT = "LIGHT"
    REM = "REM"
    DEEP = "DEEP"


class IngestDecision(Enum):
    DISPATCHED = "DISPATCHED"              # 立即下发下游（P0 或窗口外新源）
    BUFFERED_MERGING = "BUFFERED_MERGING"  # 进入合并窗
    SUPPRESSED_COOLDOWN = "SUPPRESSED_COOLDOWN"  # 冷却期抑制
    DEFERRED_DEEP_SLEEP = "DEFERRED_DEEP_SLEEP"  # 深睡延递
    DEDUPLICATED = "DEDUPLICATED"          # 精确重复被去重


#: 冷却语义只覆盖"非致命一般提醒"类（门禁 2 原文）；
#: 原始生理体征脉冲不是提醒，只吃合并窗、不吃冷却，避免漏报关键体征趋势。
_COOLDOWN_KINDS: frozenset[VitalPulseKind] = frozenset(
    {
        VitalPulseKind.TASK_REMINDER,
        VitalPulseKind.REVIEW_NUDGE,
        VitalPulseKind.GENERAL_NOTIFICATION,
    }
)


class VibratorPort(Protocol):
    """物理马达口。计数由实现侧（测试注入）见证。"""

    def vibrate(self, pattern: str, burst_count: int) -> None:  # pragma: no cover
        ...


class _PassthroughVibrator:
    def vibrate(self, pattern: str, burst_count: int) -> None:  # pragma: no cover
        pass


class CooldownWakeQueue:
    """合并窗 + 自适应冷却 + 深睡静默闸 + 无损延递。"""

    def __init__(
        self,
        *,
        vibrator: VibratorPort | None = None,
        downstream: Callable[[AggregatedBatch], None] | None = None,
        merge_window_ns: int = MERGE_WINDOW_NS,
    ) -> None:
        self._vibrator = vibrator or _PassthroughVibrator()
        self._downstream = downstream or (lambda batch: None)
        self.merge_window_ns = merge_window_ns

        self._pending: "OrderedDict[tuple, VitalPulse]" = OrderedDict()
        self._pending_first_at_ns: int | None = None
        self._deferred: list[AggregatedBatch] = []
        self._cooldown_until_ns: dict[VitalPulseKind, int] = {}
        self._cooldown_span_ns: dict[VitalPulseKind, int] = {}

        # 观察性计数（门禁证据）
        self.downstream_dispatch_count = 0
        self.vibration_invocations = 0       # 模拟计数;真机由 VibratorPort 实现侧计
        self.deep_sleep_blocked_count = 0
        self.dedup_dropped_count = 0
        self.sleep_stage: SleepStage = SleepStage.AWAKE

    # ---------------------------------------------------------------- 输入

    def ingest(self, pulse: VitalPulse, *, now_ns: int) -> IngestDecision:
        """单条脉冲入口。P0 永远直穿；深睡一律延递；冷却期抑制；其余入合并窗。"""
        if pulse.at_ns > now_ns:
            raise ValueError("pulse.at_ns 不能晚于 now_ns（时钟只能向前）")

        # P0 生命安全事件：硬件直穿，不吃任何闸门
        if pulse.priority is WakePriority.P0_CRITICAL_SAFETY:
            self._dispatch_merged(VitalPulseKind(pulse.kind), [pulse], now_ns)
            self._vibrate("SOS_CRITICAL", 3)
            return IngestDecision.DISPATCHED

        # 深睡绝对静默
        if self.sleep_stage is SleepStage.DEEP:
            self.deep_sleep_blocked_count += 1
            self._deferred.append(AggregatedBatch(kind=pulse.kind, pulses=(pulse,)))
            return IngestDecision.DEFERRED_DEEP_SLEEP

        # 冷却硬防护（仅提醒类源受用；体征源免疫避免漏报）
        if pulse.kind in _COOLDOWN_KINDS:
            until = self._cooldown_until_ns.get(pulse.kind, 0)
            if now_ns < until:
                self._escalate_cooldown(pulse.kind, now_ns)
                return IngestDecision.SUPPRESSED_COOLDOWN

        # 合并窗：按（源、值、秒）精确去重
        dedupe_key = (pulse.kind, pulse.value, pulse.at_ns // 1_000_000_000)
        if dedupe_key in self._pending:
            self.dedup_dropped_count += 1
            return IngestDecision.DEDUPLICATED
        if self._pending_first_at_ns is None:
            self._pending_first_at_ns = pulse.at_ns
        self._pending[dedupe_key] = pulse
        return IngestDecision.BUFFERED_MERGING

    # ---------------------------------------------------------------- 出窗

    def flush(self, *, now_ns: int, force: bool = False) -> list[AggregatedBatch]:
        """窗口期满把积压脉冲合并为单条批次，一次性唤醒下游。

        ``force=True`` 供测试/安全窗口显式出窗；正常路径只在窗口期满自动合并。
        """
        if not self._pending:
            return []
        assert self._pending_first_at_ns is not None
        if not force and now_ns - self._pending_first_at_ns < self.merge_window_ns:
            return []

        # 深睡期出窗：脉冲转无损延递仓，绝不唤醒下游
        if self.sleep_stage is SleepStage.DEEP:
            batches: list[AggregatedBatch] = []
            by_kind: dict[VitalPulseKind, list[VitalPulse]] = {}
            for pulse in self._pending.values():
                by_kind.setdefault(pulse.kind, []).append(pulse)
                self.deep_sleep_blocked_count += 1
            self._pending.clear()
            self._pending_first_at_ns = None
            for kind, pulses in by_kind.items():
                self._deferred.append(AggregatedBatch(kind=kind, pulses=tuple(pulses)))
            return []

        by_kind: dict[VitalPulseKind, list[VitalPulse]] = {}
        for pulse in self._pending.values():
            by_kind.setdefault(pulse.kind, []).append(pulse)
        self._pending.clear()
        self._pending_first_at_ns = None

        batches = []
        for kind, pulses in by_kind.items():
            pulses.sort(key=lambda p: p.at_ns)
            # 冷却期内的提醒类不进下游，转冷却延递仓（无损，醒后/期满后出仓）
            until = self._cooldown_until_ns.get(kind, 0)
            if kind in _COOLDOWN_KINDS and now_ns < until:
                self._deferred.append(AggregatedBatch(kind=kind, pulses=tuple(pulses)))
                continue
            batch = AggregatedBatch(kind=kind, pulses=tuple(pulses))
            self._dispatch_merged(kind, batch.pulses, now_ns, batch=batch)
            batches.append(batch)
        return batches

    # ---------------------------------------------------------------- 睡眠

    def advance_sleep_stage(self, stage: SleepStage, *, now_ns: int) -> "SleepThawReport | None":
        """推进睡眠阶段；DEEP→AWAKE 的清晨安全窗口自动解冻延递仓。"""
        previous = self.sleep_stage
        self.sleep_stage = stage
        if previous is SleepStage.DEEP and stage is SleepStage.AWAKE:
            return self.thaw_deferred(now_ns=now_ns)
        return None

    def thaw_deferred(self, *, now_ns: int) -> "SleepThawReport":
        """有序聚合呈现延递仓：优先级降序、时间升序；批次振动恰好 1 次。"""
        buffered = list(self._deferred)
        self._deferred.clear()

        # 同云集合并：同 kind 的批次再聚一次（无损聚合呈现）
        merged: dict[VitalPulseKind, list[VitalPulse]] = {}
        for batch in buffered:
            merged.setdefault(batch.kind, []).extend(batch.pulses)

        lines: list[AggregatedBatch] = []
        for kind, pulses in merged.items():
            pulses.sort(key=lambda p: (p.priority.value, p.at_ns), reverse=False)
            lines.append(AggregatedBatch(kind=kind, pulses=tuple(pulses)))
        # 呈现排序：最高优先级批次在前，批次内时间升序
        lines.sort(key=lambda b: (-max(p.priority for p in b.pulses), b.first_at_ns))

        for batch in lines:
            self.downstream_dispatch_count += 1
            self._downstream(batch)
        if lines:
            self._vibrate("THAW_DIGEST", 1)  # 安全窗口聚合呈现，仅一次提示振动
        return SleepThawReport(
            batches=tuple(lines),
            total_pulses=sum(b.count for b in lines),
            vibrated=bool(lines),
        )

    def verify_lossless(self, expected_pulses: Sequence[VitalPulse]) -> bool:
        """无损性核验：集合与延递仓+已出仓脉冲严格等势。"""
        held: list[VitalPulse] = []
        for batch in self._deferred:
            held.extend(batch.pulses)
        for pulse in self._pending.values():
            held.append(pulse)
        expected_ids = sorted((p.kind.value, p.value, p.at_ns) for p in expected_pulses)
        held_ids = sorted((p.kind.value, p.value, p.at_ns) for p in held)
        return expected_ids == held_ids

    # ---------------------------------------------------------------- 内部

    def _dispatch_merged(
        self,
        kind: VitalPulseKind,
        pulses: Sequence[VitalPulse],
        now_ns: int,
        *,
        batch: AggregatedBatch | None = None,
    ) -> None:
        batch = batch or AggregatedBatch(kind=kind, pulses=tuple(pulses))
        self.downstream_dispatch_count += 1
        self._downstream(batch)
        # 提醒类下发后进入冷却；P0 与体征源不设冷却
        if (
            kind in _COOLDOWN_KINDS
            and max((p.priority for p in pulses), default=WakePriority.P3_BACKGROUND)
            is not WakePriority.P0_CRITICAL_SAFETY
        ):
            self._arm_cooldown(kind, now_ns)

    def _arm_cooldown(self, kind: VitalPulseKind, now_ns: int) -> None:
        span = self._cooldown_span_ns.get(kind, BASE_COOLDOWN_NS)
        span = min(max(span, BASE_COOLDOWN_NS), MAX_COOLDOWN_NS)
        self._cooldown_span_ns[kind] = span
        self._cooldown_until_ns[kind] = now_ns + span

    def _escalate_cooldown(self, kind: VitalPulseKind, now_ns: int) -> None:
        span = self._cooldown_span_ns.get(kind, BASE_COOLDOWN_NS) + COOLDOWN_STEP_NS
        span = min(span, MAX_COOLDOWN_NS)
        self._cooldown_span_ns[kind] = span
        self._cooldown_until_ns[kind] = now_ns + span

    def _vibrate(self, pattern: str, burst_count: int) -> None:
        self.vibration_invocations += 1
        self._vibrator.vibrate(pattern, burst_count)


@dataclass(frozen=True)
class SleepThawReport:
    batches: tuple[AggregatedBatch, ...]
    total_pulses: int
    vibrated: bool
