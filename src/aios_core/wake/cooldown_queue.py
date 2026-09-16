"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

工单：``arena/agent-wake-m2-001`` -> ``src/aios_core/wake/cooldown_queue.py``

实战情境
--------------------------------------------------------------------------
手环佩戴者处于两类极端状态：

* **高频运动**：羽毛球赛后心率剧烈波动，加速度传感器 50Hz 持续产出离散脉冲；
* **深度睡眠**：凌晨 02:00~06:00 的 Deep Sleep 阶段，任何打扰都是伤害。

四大硬门禁
--------------------------------------------------------------------------
1. **高频传感器防抖与合并窗口**
   5 秒内涌入的 250 条离散体征脉冲必须聚合成 **1 条批次事件**（并做幂等去重），
   严禁逐条唤醒下游心智流水线。
2. **冷却时间硬防护**
   非致命一般提醒触发后强制进入 **15~30 分钟自适应冷却**（连续触发逐级抬升、
   静默足够久后回落），避免手环变骚扰器。
3. **深度睡眠绝对静默闸（DEEP_SLEEP GATE）**
   判定处于深睡阶段时，除 P0 生命安全事件（心梗/跌倒硬件直穿）外，
   所有一般通知、复盘反思、任务提醒**全部挂起**，物理马达振动次数严格为 **0**。
4. **静默队列无损唤醒延递**
   用户清醒并下床后的**第一个安全窗口**，静默队列自动解冻并**有序聚合呈现**
   （只震一次、按优先级与时间排序、零丢弃）。
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from statistics import fmean
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.safety_bypass import WakePriority
from aios_core.contracts.time import as_utc, require_aware, utc_now
from aios_core.errors import AIOSProtocolError

__all__ = [
    "COOLDOWN_MAX_MINUTES",
    "COOLDOWN_MIN_MINUTES",
    "MERGE_WINDOW_SECONDS",
    "AggregatedMetric",
    "CooldownDecision",
    "CooldownGate",
    "CooldownPolicy",
    "DeepSleepDecision",
    "DeepSleepGate",
    "GateVerdict",
    "MergedBatch",
    "Notification",
    "NotificationKind",
    "PhysiologicalPulse",
    "PhysiologyState",
    "PulseKind",
    "PulseMergeWindow",
    "SilentQueue",
    "UnfreezeReport",
    "WakeCooldownQueue",
]

#: 工单口径：5 秒合并窗口（250 条离散脉冲 -> 1 条批次事件）。
MERGE_WINDOW_SECONDS: Final[float] = 5.0

#: 工单口径：一般提醒冷却 15~30 分钟（自适应）。
COOLDOWN_MIN_MINUTES: Final[float] = 15.0
COOLDOWN_MAX_MINUTES: Final[float] = 30.0


# ---------------------------------------------------------------------------
# 体征脉冲与合并批次
# ---------------------------------------------------------------------------


class PulseKind(StrEnum):
    HEART_RATE = "heart_rate"
    ACCELERATION = "acceleration"
    HRV = "hrv"
    SPO2 = "spo2"
    GYROSCOPE = "gyroscope"


class PhysiologicalPulse(BaseModel):
    """单条离散物理体征脉冲（50Hz 加速度 / 逐拍心率）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pulse_id: str = Field(min_length=1)
    captured_at: datetime
    kind: PulseKind
    value: float
    unit: str = ""
    source: str = "band"
    quality: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.captured_at, "captured_at")
        return self

    @property
    def dedupe_fingerprint(self) -> str:
        """去重指纹：同源、同通道、同量化值的重复上报视为同一物理事实。"""
        return f"{self.source}|{self.kind.value}|{round(self.value, 3)}"


class AggregatedMetric(BaseModel):
    """单个通道在窗口内的聚合统计（不丢极值：min/max 必须保留）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    unit: str = ""
    count: int = Field(ge=1)
    minimum: float
    maximum: float
    mean: float
    last: float


class MergedBatch(BaseModel):
    """合并后的事件批次：下游心智流水线只看到这个，不看到 250 条原始脉冲。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: str = Field(min_length=1)
    window_start: datetime
    window_end: datetime
    pulse_count: int = Field(ge=1)
    deduped_count: int = Field(ge=0)
    distinct_sources: int = Field(ge=1)
    aggregated: dict[str, AggregatedMetric] = Field(default_factory=dict)
    critical_hint: bool = False
    fingerprint: str = Field(min_length=1)

    @property
    def compression_ratio(self) -> float:
        return self.pulse_count / max(len(self.aggregated), 1)

    def metric(self, name: str) -> AggregatedMetric | None:
        return self.aggregated.get(name)


class PulseMergeWindow:
    """5 秒滑动合并窗口：去重 + 聚合，绝不逐条唤醒下游。"""

    def __init__(
        self,
        *,
        window_seconds: float = MERGE_WINDOW_SECONDS,
        dedupe: bool = True,
        critical_bpm: float = 180.0,
    ) -> None:
        if window_seconds <= 0:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "window_seconds must be positive",
                context={"reason": "invalid_merge_window"},
            )
        self._window_seconds = window_seconds
        self._dedupe = dedupe
        self._critical_bpm = critical_bpm
        self._lock = threading.RLock()
        self._pending: list[PhysiologicalPulse] = []
        self._seen_fingerprints: set[str] = set()
        self._window_start: datetime | None = None
        self._batches: list[MergedBatch] = []
        self._ingested = 0
        self._deduped = 0
        self._downstream_wakes = 0  # 每次真正交给下游心智流水线的批次数

    # ---- 只读指标 ----

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    @property
    def total_ingested(self) -> int:
        return self._ingested

    @property
    def total_deduped(self) -> int:
        return self._deduped

    @property
    def batches_emitted(self) -> int:
        return len(self._batches)

    @property
    def downstream_wake_count(self) -> int:
        """下游心智流水线被唤醒的次数（必须远小于脉冲条数）。"""
        return self._downstream_wakes

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def batches(self) -> tuple[MergedBatch, ...]:
        return tuple(self._batches)

    # ---- 写路径 ----

    def ingest(self, pulse: PhysiologicalPulse) -> MergedBatch | None:
        """摄入一条脉冲；窗口满则吐出批次，否则返回 ``None``。"""
        with self._lock:
            self._ingested += 1
            if self._window_start is None:
                self._window_start = pulse.captured_at
            else:
                elapsed = (
                    as_utc(pulse.captured_at, "captured_at")
                    - as_utc(self._window_start, "window_start")
                ).total_seconds()
                if elapsed > self._window_seconds:
                    closed = self._close_locked()
                    self._window_start = pulse.captured_at
                    self._accumulate_locked(pulse)
                    return closed
            self._accumulate_locked(pulse)
            return None

    def flush(self, now: datetime | None = None) -> MergedBatch | None:
        """强制关闭当前窗口（会话结束/静默切换时使用）。"""
        with self._lock:
            if not self._pending:
                self._window_start = None
                return None
            batch = self._close_locked()
            self._window_start = None
            _ = now
            return batch

    def _accumulate_locked(self, pulse: PhysiologicalPulse) -> None:
        if self._dedupe:
            fingerprint = pulse.dedupe_fingerprint
            if fingerprint in self._seen_fingerprints:
                self._deduped += 1
                return
            self._seen_fingerprints.add(fingerprint)
        self._pending.append(pulse)

    def _close_locked(self) -> MergedBatch | None:
        if not self._pending:
            return None
        pending = self._pending
        self._pending = []
        self._seen_fingerprints.clear()
        aggregated: dict[str, AggregatedMetric] = {}
        by_kind: dict[str, list[PhysiologicalPulse]] = {}
        for pulse in pending:
            by_kind.setdefault(pulse.kind.value, []).append(pulse)
        for kind, items in by_kind.items():
            values = [item.value for item in items]
            aggregated[kind] = AggregatedMetric(
                metric=kind,
                unit=items[0].unit,
                count=len(items),
                minimum=min(values),
                maximum=max(values),
                mean=fmean(values),
                last=values[-1],
            )
        window_start = min(pulse.captured_at for pulse in pending)
        window_end = max(pulse.captured_at for pulse in pending)
        heart = aggregated.get(PulseKind.HEART_RATE.value)
        batch = MergedBatch(
            batch_id=f"batch_{window_start.isoformat()}_{window_end.isoformat()}",
            window_start=window_start,
            window_end=window_end,
            pulse_count=len(pending),
            deduped_count=self._deduped,
            distinct_sources=len({pulse.source for pulse in pending}),
            aggregated=aggregated,
            critical_hint=bool(heart and heart.maximum >= self._critical_bpm),
            fingerprint=f"{window_start.isoformat()}|{window_end.isoformat()}|{len(pending)}",
        )
        self._batches.append(batch)
        self._downstream_wakes += 1  # 一个窗口 = 一次下游唤醒
        return batch


# ---------------------------------------------------------------------------
# 通知与静默闸
# ---------------------------------------------------------------------------


class NotificationKind(StrEnum):
    SAFETY_P0 = "safety_p0"              # 生命安全：硬件直穿，不在静默范围内
    TASK_REMINDER = "task_reminder"      # 任务提醒
    REVIEW_REFLECTION = "review_reflection"  # 复盘反思
    GENERAL_REMINDER = "general_reminder"    # 一般提醒
    HEALTH_TIP = "health_tip"                # 健康贴士


#: 深睡期允许直穿的通知类型（P0 生命安全）。
SILENCE_EXEMPT_KINDS: Final[frozenset[NotificationKind]] = frozenset(
    {NotificationKind.SAFETY_P0}
)

#: 优先级排序权重（数字越小越先呈现）。
_PRIORITY_ORDER: Final[Mapping[WakePriority, int]] = {
    WakePriority.P0_CRITICAL_SAFETY: 0,
    WakePriority.P1_URGENT_TASK: 1,
    WakePriority.P2_NORMAL_INTERACT: 2,
    WakePriority.P3_BACKGROUND_TICK: 3,
}


class Notification(BaseModel):
    """一条待投递的提醒（一般通知 / 复盘反思 / 任务提醒 / P0 急救）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    notification_id: str = Field(min_length=1)
    kind: NotificationKind
    title: str = Field(min_length=1)
    priority: WakePriority = WakePriority.P2_NORMAL_INTERACT
    created_at: datetime = Field(default_factory=utc_now)
    dedupe_key: str | None = None
    motor_vibration: bool = True

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.created_at, "created_at")
        return self

    @property
    def is_safety_critical(self) -> bool:
        return (
            self.kind in SILENCE_EXEMPT_KINDS
            or self.priority is WakePriority.P0_CRITICAL_SAFETY
        )

    @property
    def gate_key(self) -> str:
        return self.dedupe_key or self.kind.value


class PhysiologyState(BaseModel):
    """生理状态快照：深睡判定来自体动+心率特征，不在本模块内做推测。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    captured_at: datetime
    deep_sleep: bool = False
    asleep: bool = False
    in_bed: bool = True

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.captured_at, "captured_at")
        return self

    @property
    def silence_required(self) -> bool:
        return self.deep_sleep

    @property
    def safe_wake_window(self) -> bool:
        """晨间安全窗口：已醒、已下床、且不再处于深睡。"""
        return not self.deep_sleep and not self.asleep and not self.in_bed


class GateVerdict(StrEnum):
    DELIVERED = "delivered"
    SUPPRESSED_BY_DEEP_SLEEP = "suppressed_by_deep_sleep"
    SUPPRESSED_BY_COOLDOWN = "suppressed_by_cooldown"
    QUEUED_FOR_WAKE_WINDOW = "queued_for_wake_window"


class DeepSleepDecision(BaseModel):
    """深睡闸裁决：把"震了几次"变成可核对数字。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: GateVerdict
    notification_id: str
    silence_active: bool
    safety_exempt: bool
    hardware_pulse_issued: bool
    motor_vibrations: int = Field(ge=0)
    reason: str = Field(min_length=1)


class CooldownDecision(BaseModel):
    """冷却闸裁决：非致命提醒必须落进 15~30 分钟自适应冷却。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: GateVerdict
    notification_id: str
    gate_key: str
    escalation_level: int = Field(ge=0)
    cooldown_seconds: float = Field(ge=0.0)
    next_allowed_at: datetime | None = None
    motor_vibrations: int = Field(ge=0)
    reason: str = Field(min_length=1)


class CooldownPolicy(BaseModel):
    """自适应冷却策略：基础 15 分钟，连续触发逐级抬升，封顶 30 分钟。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_minutes: float = Field(default=COOLDOWN_MIN_MINUTES, ge=0.0)
    max_minutes: float = Field(default=COOLDOWN_MAX_MINUTES, ge=0.0)
    escalation_minutes: float = Field(default=5.0, ge=0.0)
    quiet_reset_minutes: float = Field(default=90.0, gt=0.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.max_minutes < self.base_minutes:
            raise ValueError("max_minutes must be >= base_minutes")
        return self

    def cooldown_for(self, escalation_level: int) -> timedelta:
        minutes = min(
            self.max_minutes, self.base_minutes + escalation_level * self.escalation_minutes
        )
        return timedelta(minutes=minutes)


class _GateState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: int = 0
    last_fired_at: datetime | None = None
    until: datetime | None = None


class CooldownGate:
    """冷却闸：非致命一般提醒触发后强制进入自适应冷却期。"""

    def __init__(self, policy: CooldownPolicy | None = None) -> None:
        self._policy = policy or CooldownPolicy()
        self._states: dict[str, _GateState] = {}
        self._lock = threading.RLock()
        self._delivered = 0
        self._suppressed = 0
        self._vibrations = 0

    @property
    def policy(self) -> CooldownPolicy:
        return self._policy

    @property
    def delivered_count(self) -> int:
        return self._delivered

    @property
    def suppressed_count(self) -> int:
        return self._suppressed

    @property
    def motor_vibrations(self) -> int:
        return self._vibrations

    def check(self, notification: Notification, now: datetime) -> CooldownDecision:
        """判定是否放行；放行则占用一次振动并抬升冷却。"""
        moment = as_utc(now, "now")
        with self._lock:
            state = self._states.setdefault(notification.gate_key, _GateState())
            if state.until is not None and moment < as_utc(state.until, "until"):
                self._suppressed += 1
                return CooldownDecision(
                    verdict=GateVerdict.SUPPRESSED_BY_COOLDOWN,
                    notification_id=notification.notification_id,
                    gate_key=notification.gate_key,
                    escalation_level=state.level,
                    cooldown_seconds=self._policy.cooldown_for(state.level).total_seconds(),
                    next_allowed_at=state.until,
                    motor_vibrations=0,
                    reason=(
                        f"冷却期内（等级 {state.level}，"
                        f"至 {state.until.isoformat()} 前不再打扰）"
                    ),
                )

            # 静默足够久 -> 冷却等级回落（避免"一次误触永久抬价"）
            if state.last_fired_at is not None:
                quiet = moment - as_utc(state.last_fired_at, "last_fired_at")
                if quiet >= timedelta(minutes=self._policy.quiet_reset_minutes):
                    state.level = 0
            cooldown = self._policy.cooldown_for(state.level)
            state.last_fired_at = moment
            state.until = moment + cooldown
            state.level = min(state.level + 1, self._max_level())
            self._delivered += 1
            vibrations = 1 if notification.motor_vibration else 0
            self._vibrations += vibrations
            return CooldownDecision(
                verdict=GateVerdict.DELIVERED,
                notification_id=notification.notification_id,
                gate_key=notification.gate_key,
                escalation_level=max(state.level - 1, 0),
                cooldown_seconds=cooldown.total_seconds(),
                next_allowed_at=state.until,
                motor_vibrations=vibrations,
                reason=f"冷却 {cooldown.total_seconds() / 60:.0f} 分钟后才允许再次提醒",
            )

    def _max_level(self) -> int:
        step = self._policy.escalation_minutes
        if step <= 0:
            return 0
        return int((self._policy.max_minutes - self._policy.base_minutes) / step)

    def cooldown_bounds_seconds(self) -> tuple[float, float]:
        """策略允许的冷却区间（工单要求 15~30 分钟）。"""
        return (
            self._policy.base_minutes * 60.0,
            self._policy.max_minutes * 60.0,
        )


class DeepSleepGate:
    """深睡绝对静默闸：除 P0 生命安全外，一律挂起且零马达振动。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._hardware_pulses = 0
        self._vibrations = 0
        self._suppressed = 0

    @property
    def hardware_pulse_count(self) -> int:
        return self._hardware_pulses

    @property
    def motor_vibrations(self) -> int:
        return self._vibrations

    @property
    def suppressed_count(self) -> int:
        return self._suppressed

    def check(self, notification: Notification, state: PhysiologyState) -> DeepSleepDecision:
        with self._lock:
            if not state.silence_required:
                # 放行不等于投递：真正的振动由下游冷却闸（或 P0 硬件通道）记账，
                # 静默闸绝不允许重复计数，否则"整夜震了几次"会被算成两倍。
                return DeepSleepDecision(
                    verdict=GateVerdict.DELIVERED,
                    notification_id=notification.notification_id,
                    silence_active=False,
                    safety_exempt=notification.is_safety_critical,
                    hardware_pulse_issued=notification.is_safety_critical,
                    motor_vibrations=0 if not notification.motor_vibration else 0,
                    reason="非静默期：放行至冷却闸投递",
                )
            if notification.is_safety_critical:
                # P0 生命安全：硬件直穿，不震马达（走的是急救硬件通道）
                self._hardware_pulses += 1
                return DeepSleepDecision(
                    verdict=GateVerdict.DELIVERED,
                    notification_id=notification.notification_id,
                    silence_active=True,
                    safety_exempt=True,
                    hardware_pulse_issued=True,
                    motor_vibrations=0,
                    reason="P0 生命安全硬件直穿（不占用马达振动通道）",
                )
            self._suppressed += 1
            return DeepSleepDecision(
                verdict=GateVerdict.SUPPRESSED_BY_DEEP_SLEEP,
                notification_id=notification.notification_id,
                silence_active=True,
                safety_exempt=False,
                hardware_pulse_issued=False,
                motor_vibrations=0,
                reason="深度睡眠绝对静默：挂起至晨间安全窗口",
            )


# ---------------------------------------------------------------------------
# 静默队列（无损延递）
# ---------------------------------------------------------------------------


class UnfreezeReport(BaseModel):
    """解冻报告：有序聚合呈现的证据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unfrozen: bool
    still_silent: bool
    presented: tuple[Notification, ...] = ()
    aggregated_batches: int = Field(ge=0)
    motor_vibrations: int = Field(ge=0)
    dropped: int = Field(default=0, ge=0)
    queued_remaining: int = Field(default=0, ge=0)
    reason: str = Field(min_length=1)

    @property
    def lossless(self) -> bool:
        return self.dropped == 0 and self.queued_remaining == 0


class SilentQueue:
    """静默队列：深睡期挂起、晨间安全窗口无损解冻并有序聚合呈现。"""

    def __init__(self, *, batch_size: int = 5) -> None:
        self._queue: list[Notification] = []
        self._lock = threading.RLock()
        self._batch_size = max(batch_size, 1)
        self._enqueued = 0
        self._presented = 0
        self._dropped = 0

    @property
    def queued_count(self) -> int:
        return len(self._queue)

    @property
    def enqueued_total(self) -> int:
        return self._enqueued

    @property
    def presented_total(self) -> int:
        return self._presented

    @property
    def dropped_total(self) -> int:
        return self._dropped

    def pending(self) -> tuple[Notification, ...]:
        return tuple(self._queue)

    def enqueue(self, notification: Notification) -> int:
        with self._lock:
            self._enqueued += 1
            self._queue.append(notification)
            return len(self._queue)

    def dequeue_all(self) -> tuple[Notification, ...]:
        with self._lock:
            items = tuple(self._queue)
            self._queue = []
            return items

    def unfreeze(self, state: PhysiologyState) -> UnfreezeReport:
        """只在晨间安全窗口解冻；其余时刻队列原样保留（无损）。"""
        with self._lock:
            if state.silence_required or not state.safe_wake_window:
                return UnfreezeReport(
                    unfrozen=False,
                    still_silent=True,
                    presented=(),
                    aggregated_batches=0,
                    motor_vibrations=0,
                    queued_remaining=len(self._queue),
                    reason="尚未进入晨间安全窗口：静默队列继续封存（零打扰）",
                )
            ordered = sorted(
                self._queue,
                key=lambda n: (_PRIORITY_ORDER.get(n.priority, 9), n.created_at, n.notification_id),
            )
            self._queue = []
            self._presented += len(ordered)
            batches = self._aggregate(ordered)
            return UnfreezeReport(
                unfrozen=True,
                still_silent=False,
                presented=tuple(ordered),
                aggregated_batches=batches,
                motor_vibrations=1 if ordered else 0,  # 聚合呈现：只震一次
                dropped=self._dropped,
                queued_remaining=0,
                reason=(
                    f"晨间安全窗口解冻：{len(ordered)} 条挂起提醒聚合为 {batches} 批呈现"
                    f"（马达振动 1 次）"
                ),
            )

    def _aggregate(self, ordered: Sequence[Notification]) -> int:
        if not ordered:
            return 0
        return (len(ordered) + self._batch_size - 1) // self._batch_size


# ---------------------------------------------------------------------------
# 门面：去重合并 + 冷却 + 静默 + 解冻
# ---------------------------------------------------------------------------


class WakeCooldownQueue:
    """四道闸的门面：脉冲合并进、提醒判定出、静默挂起、晨间延递。"""

    def __init__(
        self,
        *,
        merge_window_seconds: float = MERGE_WINDOW_SECONDS,
        cooldown_policy: CooldownPolicy | None = None,
    ) -> None:
        self._merge = PulseMergeWindow(window_seconds=merge_window_seconds)
        self._cooldown = CooldownGate(cooldown_policy)
        self._deep_sleep = DeepSleepGate()
        self._silent = SilentQueue()
        self._lock = threading.RLock()
        self._llm_calls = 0
        self._queue_hits = 0
        self._presentation_vibrations = 0
        self._state = PhysiologyState(captured_at=utc_now(), deep_sleep=False, asleep=False, in_bed=False)

    # ---- 只读 ----

    @property
    def merge_window(self) -> PulseMergeWindow:
        return self._merge

    @property
    def cooldown(self) -> CooldownGate:
        return self._cooldown

    @property
    def deep_sleep_gate(self) -> DeepSleepGate:
        return self._deep_sleep

    @property
    def silent_queue(self) -> SilentQueue:
        return self._silent

    @property
    def physiology(self) -> PhysiologyState:
        return self._state

    @property
    def llm_calls(self) -> int:
        """本队列自身发起的大模型调用（机械闸门恒为 0）。"""
        return self._llm_calls

    @property
    def motor_vibrations(self) -> int:
        """全链路马达振动总账：冷却闸投递 + 晨间解冻聚合呈现（静默闸恒为 0）。"""
        return (
            self._cooldown.motor_vibrations
            + self._deep_sleep.motor_vibrations
            + self._presentation_vibrations
        )

    def enter_state(self, state: PhysiologyState) -> None:
        with self._lock:
            self._state = state

    # ---- 脉冲摄入（门禁 1）----

    def submit_pulse(self, pulse: PhysiologicalPulse) -> MergedBatch | None:
        return self._merge.ingest(pulse)

    def submit_pulses(
        self, pulses: Iterable[PhysiologicalPulse]
    ) -> tuple[MergedBatch, ...]:
        batches: list[MergedBatch] = []
        for pulse in pulses:
            batch = self._merge.ingest(pulse)
            if batch is not None:
                batches.append(batch)
        return tuple(batches)

    # ---- 通知裁决（门禁 2 & 3）----

    def notify(self, notification: Notification, now: datetime) -> DeepSleepDecision | CooldownDecision:
        """统一投递入口：先过深睡闸，再过冷却闸；被挂起则进静默队列（无损）。"""
        with self._lock:
            sleep_decision = self._deep_sleep.check(notification, self._state)
            if sleep_decision.verdict is GateVerdict.SUPPRESSED_BY_DEEP_SLEEP:
                self._silent.enqueue(notification)
                self._queue_hits += 1
                return sleep_decision
            if notification.is_safety_critical:
                return sleep_decision
            decision = self._cooldown.check(notification, now)
            if decision.verdict is GateVerdict.SUPPRESSED_BY_COOLDOWN:
                self._silent.enqueue(notification)
                self._queue_hits += 1
            return decision

    # ---- 晨间解冻（门禁 4）----

    def morning_wake(self, state: PhysiologyState) -> UnfreezeReport:
        with self._lock:
            self._state = state
            report = self._silent.unfreeze(state)
            self._presentation_vibrations += report.motor_vibrations
            return report

    # ---- 审计 ----

    def audit(self) -> dict[str, int | float]:
        return {
            "pulses_ingested": self._merge.total_ingested,
            "pulses_deduped": self._merge.total_deduped,
            "batches_emitted": self._merge.batches_emitted,
            "downstream_wakes": self._merge.downstream_wake_count,
            "notifications_delivered": self._cooldown.delivered_count,
            "notifications_suppressed": self._cooldown.suppressed_count
            + self._deep_sleep.suppressed_count,
            "queued_for_wake_window": self._queue_hits,
            "queued_now": self._silent.queued_count,
            "motor_vibrations": self.motor_vibrations,
            "hardware_pulses": self._deep_sleep.hardware_pulse_count,
            "llm_calls": self._llm_calls,
        }

    def compression_ratio(self) -> float:
        """250 条脉冲压成几条批次（越大越省下游算力）。"""
        batches = max(self._merge.batches_emitted, 1)
        return self._merge.total_ingested / batches


# ===========================================================================
# agent-05 compatibility wake engine
# ===========================================================================

_P0 = WakePriority.P0_CRITICAL_SAFETY


class SleepStage(StrEnum):
    AWAKE = "awake"
    LIGHT = "light"
    DEEP = "deep"
    REM = "rem"


class _TimeAware(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _aware(self) -> "_TimeAware":
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, datetime):
                require_aware(value, name)
        return self


class SensorPulse(_TimeAware):
    """来自 50Hz 加速度计 / 光学心率等原始物理体征脉冲。"""

    metric: str = Field(min_length=1)
    value: float
    source: str = Field(min_length=1)
    at: datetime
    priority: WakePriority = WakePriority.P2_NORMAL_INTERACT

    @property
    def dedupe_key(self) -> str:
        return f"pulse:{self.source}:{self.metric}"


class WakeNotice(_TimeAware):
    """逻辑唤醒请求：一般提醒 / 复盘反思 / 任务提醒等（非传感器原始流）。"""

    event_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)  # reminder / review / task_alert ...
    title: str = Field(min_length=1)
    occurred_at: datetime
    priority: WakePriority = WakePriority.P2_NORMAL_INTERACT
    payload: dict = Field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        return f"notice:{self.kind}"


class WakeBatch(_TimeAware):
    """一个合并窗口内同一去重键聚合出的单条批次事件。"""

    batch_id: str
    dedupe_key: str
    member_count: int = Field(ge=1)
    first_at: datetime
    last_at: datetime
    peak_value: float
    mean_value: float


class _SilentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    kind: str
    title: str
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _aware(self) -> "_SilentEntry":
        require_aware(self.occurred_at, "occurred_at")
        return self


class SilentWakeEngine:
    """去重合并 + 自适应冷却 + 深睡静默 + 晨间无损延递 的统一路由器。"""

    COOLDOWN_BASE_SECONDS = 15 * 60
    COOLDOWN_MAX_SECONDS = 30 * 60
    COOLDOWN_ESCALATION_SECONDS = 7 * 60 + 30  # 每级加罚 7.5 分钟
    QUIET_DECAY_SECONDS = 24 * 3600

    def __init__(self, *, window_seconds: float = 5.0) -> None:
        if not (window_seconds > 0) or math.isnan(window_seconds):
            raise ValueError("window_seconds must be a positive finite number")
        self._window_seconds = float(window_seconds)
        # 合并窗口桶：(dedupe_key, window_index) -> pulse 列表
        self._buckets: dict[tuple[str, int], list[SensorPulse]] = defaultdict(list)
        self._open_window_floor: set[tuple[str, int]] = set()
        self._sleep_stage = SleepStage.AWAKE
        self._sleep_stage_at: datetime | None = None
        self._pending_morning_unfreeze = False
        self._silent_queue: list[_SilentEntry] = []
        self._silent_event_ids: list[str] = []
        self._cooldown_until: dict[str, datetime] = {}
        self._cooldown_escalation: dict[str, int] = {}
        self._last_dispatch_at: dict[str, datetime] = {}
        # —— 计量器 ——
        self.pulses_ingested = 0
        self.batches_emitted = 0
        self.pulses_folded = 0
        self.cooldown_suppressed = 0
        self.deep_sleep_deferred = 0
        self.motor_vibrations = 0
        self.p0_passthrough = 0
        self.morning_flushed_events = 0
        self.morning_flush_digests: list[dict] = []
        self.motor_log: list[tuple[datetime, str]] = []
        self._batch_seq = 0

    # ------------------------------------------------------------------
    # 睡眠分期（hypnogram）
    # ------------------------------------------------------------------

    def set_sleep_stage(self, stage: SleepStage, *, at: datetime) -> None:
        stage = SleepStage(stage)
        at = as_utc(at, "at")
        if stage is not SleepStage.AWAKE and self._sleep_stage is SleepStage.AWAKE:
            self._pending_morning_unfreeze = False
        self._sleep_stage = stage
        self._sleep_stage_at = at

    @property
    def sleep_stage(self) -> SleepStage:
        return self._sleep_stage

    def mark_out_of_bed(self, *, at: datetime) -> list[dict]:
        """晨间用户清醒并下床：第一个安全窗口触发静默队列解冻。"""
        at = as_utc(at, "at")
        if self._sleep_stage is not SleepStage.AWAKE:
            return []  # 尚未清醒：安全窗口未到，继续静默
        self._pending_morning_unfreeze = True
        return self._flush_silent_queue(now=at)

    def _flush_silent_queue(self, *, now: datetime) -> list[dict]:
        if not self._pending_morning_unfreeze or not self._silent_queue:
            return []
        # 全序（occurred_at, event_id）→ 按 kind 聚合，不打乱、不丢弃
        ordered = sorted(self._silent_queue, key=lambda e: (as_utc(e.occurred_at), e.event_id))
        grouped: dict[str, list[_SilentEntry]] = defaultdict(list)
        for entry in ordered:
            grouped[entry.kind].append(entry)
        digests: list[dict] = []
        for kind, entries in sorted(grouped.items()):
            digest = {
                "digest_id": f"dgst_{kind}_{len(digests) + now.microsecond}",
                "kind": kind,
                "count": len(entries),
                "event_ids": [e.event_id for e in entries],
                "titles": [e.title for e in entries],
                "rendered_at": now.isoformat(),
            }
            digests.append(digest)
            # 聚合呈现本身即一次通知投递：唤醒一次马达（晨间，非深睡）
            self._vibrate(now, f"morning_digest:{kind}")
        self.morning_flushed_events += len(ordered)
        self.morning_flush_digests.extend(digests)
        self._silent_queue.clear()
        self._pending_morning_unfreeze = False
        return digests

    # ------------------------------------------------------------------
    # 高频传感器入口：合并窗口
    # ------------------------------------------------------------------

    def ingest_pulse(self, pulse: SensorPulse) -> dict | None:
        """原始脉冲唯一入口。

        P0 生命安全脉冲不进窗口桶，立即硬件直穿（深睡与冷却均豁免）；
        其余脉冲只进桶——下游唯一的出口是窗口关闭时聚合出的批次事件。
        """
        self.pulses_ingested += 1
        if pulse.priority is _P0:
            return self._dispatch_p0(
                _SilentEntry(
                    event_id=f"p0_{as_utc(pulse.at).timestamp()}_{pulse.metric}",
                    kind="safety",
                    title=f"P0 生命安全: {pulse.metric} 突变",
                    occurred_at=pulse.at,
                    payload={"value": pulse.value, "source": pulse.source},
                )
            )
        window_index = int(as_utc(pulse.at).timestamp() // self._window_seconds)
        key = (pulse.dedupe_key, window_index)
        self._buckets[key].append(pulse)
        self._open_window_floor.add(key)
        return None

    def advance_to(self, now: datetime) -> list[WakeBatch]:
        """推进时钟：关闭所有 end <= now 的合并窗口，每个关闭桶只产一条批次。"""
        now_dt = as_utc(now, "now")
        closed_keys = [
            key for key in sorted(self._open_window_floor)
            if (key[1] + 1) * self._window_seconds <= now_dt.timestamp()
        ]
        batches: list[WakeBatch] = []
        for key in closed_keys:
            pulses = self._buckets.pop(key)
            self._open_window_floor.discard(key)
            if not pulses:
                continue
            self._batch_seq += 1
            times = [as_utc(p.at) for p in pulses]
            batch = WakeBatch(
                batch_id=f"wb_{self._batch_seq}",
                dedupe_key=key[0],
                member_count=len(pulses),
                first_at=min(times),
                last_at=max(times),
                peak_value=max(p.value for p in pulses),
                mean_value=sum(p.value for p in pulses) / len(pulses),
            )
            self.batches_emitted += 1
            self.pulses_folded += len(pulses) - 1
            batches.append(batch)
            self._route_batch(batch, now=now_dt)
        return batches

    # ------------------------------------------------------------------
    # 逻辑唤醒请求入口
    # ------------------------------------------------------------------

    def submit_notice(self, notice: WakeNotice, *, now: datetime | None = None) -> str:
        """一般提醒/复盘/任务提醒的唯一提交口。返回 dispatched|deferred|suppressed。"""
        now_dt = as_utc(now) if now is not None else utc_now()
        if notice.priority is _P0:
            self._dispatch_p0(
                _SilentEntry(
                    event_id=notice.event_id,
                    kind=notice.kind,
                    title=notice.title,
                    occurred_at=notice.occurred_at,
                    payload=dict(notice.payload),
                ),
                now=now_dt,
            )
            return "dispatched"
        if self._sleep_stage is not SleepStage.AWAKE:
            self._silent_queue.append(
                _SilentEntry(
                    event_id=notice.event_id,
                    kind=notice.kind,
                    title=notice.title,
                    occurred_at=notice.occurred_at,
                    payload=dict(notice.payload),
                )
            )
            self._silent_event_ids.append(notice.event_id)
            self.deep_sleep_deferred += 1
            return "deferred"
        if self._in_cooldown(notice.dedupe_key, now_dt):
            self.cooldown_suppressed += 1
            self._cooldown_escalation[notice.dedupe_key] = (
                self._cooldown_escalation.get(notice.dedupe_key, 0) + 1
            )
            return "suppressed"
        self._deliver(
            _SilentEntry(
                event_id=notice.event_id,
                kind=notice.kind,
                title=notice.title,
                occurred_at=notice.occurred_at,
                payload=dict(notice.payload),
            ),
            dedupe_key=notice.dedupe_key,
            now=now_dt,
        )
        return "dispatched"

    # ------------------------------------------------------------------
    # 冷却 / 投递原语
    # ------------------------------------------------------------------

    def _current_cooldown(self, dedupe_key: str, now: datetime) -> float:
        last = self._last_dispatch_at.get(dedupe_key)
        level = self._cooldown_escalation.get(dedupe_key, 0)
        if last is not None and (now - last).total_seconds() > self.QUIET_DECAY_SECONDS:
            level = 0  # 长期安静 → 自适应回落
        self._cooldown_escalation[dedupe_key] = level
        return min(
            self.COOLDOWN_MAX_SECONDS,
            self.COOLDOWN_BASE_SECONDS + level * self.COOLDOWN_ESCALATION_SECONDS,
        )

    def _in_cooldown(self, dedupe_key: str, now: datetime) -> bool:
        until = self._cooldown_until.get(dedupe_key)
        return until is not None and now < until

    def _deliver(self, entry: _SilentEntry, *, dedupe_key: str, now: datetime) -> None:
        self._vibrate(now, f"{dedupe_key}:{entry.kind}")
        cooldown = self._current_cooldown(dedupe_key, now)
        self._cooldown_until[dedupe_key] = now + timedelta(seconds=cooldown)
        self._last_dispatch_at[dedupe_key] = now

    def _route_batch(self, batch: WakeBatch, *, now: datetime) -> None:
        if self._sleep_stage is not SleepStage.AWAKE:
            self._silent_queue.append(
                _SilentEntry(
                    event_id=batch.batch_id,
                    kind="sensor_batch",
                    title=(
                        f"{batch.dedupe_key} ×{batch.member_count} "
                        f"peak={batch.peak_value:.1f} mean={batch.mean_value:.1f}"
                    ),
                    occurred_at=batch.last_at,
                    payload={
                        "member_count": batch.member_count,
                        "peak_value": batch.peak_value,
                        "mean_value": batch.mean_value,
                    },
                )
            )
            self._silent_event_ids.append(batch.batch_id)
            self.deep_sleep_deferred += 1
            return
        if self._in_cooldown(batch.dedupe_key, now):
            self.cooldown_suppressed += 1
            self._cooldown_escalation[batch.dedupe_key] = (
                self._cooldown_escalation.get(batch.dedupe_key, 0) + 1
            )
            return
        self._deliver(
            _SilentEntry(
                event_id=batch.batch_id,
                kind="sensor_batch",
                title=f"{batch.dedupe_key} ×{batch.member_count}",
                occurred_at=batch.last_at,
            ),
            dedupe_key=batch.dedupe_key,
            now=now,
        )

    def _dispatch_p0(self, entry: _SilentEntry, *, now: datetime | None = None) -> dict:
        """P0 生命安全直穿：深睡闸与冷却闸全部豁免（心梗跌倒硬件直穿）。"""
        at = as_utc(now) if now is not None else utc_now()
        self.p0_passthrough += 1
        self._vibrate(at, f"P0:{entry.kind}")
        return {
            "status": "SAFETY_BYPASS_EXECUTED",
            "event_id": entry.event_id,
            "bypassed_sleep_gate": True,
            "bypassed_cooldown": True,
        }

    def _vibrate(self, at: datetime, reason: str) -> None:
        # 马达振动指令的唯一发射口：任何路径要振动必须经过这里。
        self.motor_vibrations += 1
        self.motor_log.append((as_utc(at, "at"), reason))

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    def deferred_backlog(self) -> int:
        return len(self._silent_queue)

    def deferred_event_ids(self) -> list[str]:
        return list(self._silent_event_ids)

    def all_deferred_ids_seen(self) -> list[str]:
        """入过静默队列的全部 id（含已延递的），供无损性多重集比对。"""
        return list(self._silent_event_ids)

    def stats(self) -> dict[str, int]:
        return {
            "pulses_ingested": self.pulses_ingested,
            "batches_emitted": self.batches_emitted,
            "pulses_folded": self.pulses_folded,
            "cooldown_suppressed": self.cooldown_suppressed,
            "deep_sleep_deferred": self.deep_sleep_deferred,
            "motor_vibrations": self.motor_vibrations,
            "p0_passthrough": self.p0_passthrough,
            "morning_flushed_events": self.morning_flushed_events,
            "deferred_backlog": len(self._silent_queue),
        }
