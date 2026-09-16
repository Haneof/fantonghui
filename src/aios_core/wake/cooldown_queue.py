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

import threading
import time
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
