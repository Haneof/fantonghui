"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

对应 R3-ARCH 蓝图 M2-002/003（机械触发引擎、Wake 去重合并冷却），
宪法依据：V3 §34（Observation 默认只写入世界、不直接唤醒）、
§80-2（情境方便度严格研判、绝对不宜打扰时保持绝对沉默）、
§80-3（后台静默巡检绝对不停转，主动出声可冷却）、§82（重复触发
与情境抑制：合并、冷却、暂缓，安全信号不得被普通冷却屏蔽）。

四道闸（顺序固定）：

1. **合并窗口（5 秒）**：同源高频离散脉冲在窗口内聚合为单条批次
   事件——下游心智流水线只见到 1 次唤醒，绝不见 250 次。
2. **冷却硬防护（15~30 分钟自适应）**：非致命一般提醒触发后进入
   冷却期；近期被忽略/拒绝越多，冷却越长（自适应上限 30 分钟）。
3. **DEEP_SLEEP 绝对静默闸**：深度睡眠阶段，除 P0 生命安全事件外，
   一切通知/反思/提醒强制挂起，物理马达振动次数严格为 0。
4. **静默队列无损延递**：清醒安全窗口（下床事件）自动解冻，静默
   队列按"首触时间 + 严重度"有序聚合为单次呈现，零丢失。

P0 生命安全事件（心梗/跌倒硬件直穿）旁路全部四道闸——宪法 §78-4
最高执行特权，绝不允许被合并、冷却或静默吞没。
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from aios_core.contracts.time import require_aware

__all__ = [
    "BatchedPulseEvent",
    "CooldownPolicy",
    "DeepSleepGate",
    "DispatchDecision",
    "MergeWindow",
    "SilentQueueEntry",
    "WakeDispatchCenter",
    "WakePulse",
    "WakeSeverity",
]

MERGE_WINDOW_SECONDS = 5.0
COOLDOWN_BASE_MINUTES = 15
COOLDOWN_MAX_MINUTES = 30


class WakeSeverity(IntEnum):
    """严重度分层：P0 生命安全拥有最高执行特权（数值最大优先级最高）。"""

    NORMAL = 10
    ELEVATED = 30
    REMINDER = 20
    P0_CRITICAL_SAFETY = 100

    @classmethod
    def order_key(cls, value: "WakeSeverity") -> int:
        return int(value)


class WakePulse(BaseModel):
    """单条离散物理体征/提醒脉冲（进入队列前必须先过合并窗口）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pulse_id: StrictStr = Field(min_length=1)
    source_class: StrictStr = Field(min_length=1)     # hr / imu / reminder / reflective ...
    severity: WakeSeverity = WakeSeverity.NORMAL
    at: datetime
    dedupe_key: StrictStr = Field(min_length=1)
    note: str = ""

    @model_validator(mode="after")
    def _validate(self) -> "WakePulse":
        require_aware(self.at, "at")
        return self


class BatchedPulseEvent(BaseModel):
    """合并窗口产出的单条批次事件（下游唤醒的最小单位）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: StrictStr
    source_class: StrictStr
    severity: WakeSeverity
    pulse_count: StrictInt = Field(ge=1)
    first_at: datetime
    last_at: datetime
    dedupe_key: StrictStr
    representative_note: str = ""


class MergeWindow:
    """5 秒滑动合并窗口：同源脉冲去重聚合，绝不开多路唤醒。"""

    def __init__(self, window_seconds: float = MERGE_WINDOW_SECONDS) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._window = window_seconds
        self._lock = threading.RLock()
        self._open: dict[str, dict[str, WakePulse]] = {}   # dedupe_key -> pulses
        self._meta: dict[str, dict[str, Any]] = {}
        self._closed: list[BatchedPulseEvent] = []
        self._seq = 0

    def submit(self, pulse: WakePulse) -> None:
        with self._lock:
            bucket = self._open.setdefault(pulse.dedupe_key, {})
            if pulse.pulse_id in bucket:
                return  # 同脉冲重复投递：去重
            bucket[pulse.pulse_id] = pulse
            meta = self._meta.setdefault(
                pulse.dedupe_key,
                {
                    "source_class": pulse.source_class,
                    "severity": pulse.severity,
                    "first_at": pulse.at,
                    "note": pulse.note,
                },
            )
            if pulse.at < meta["first_at"]:
                meta["first_at"] = pulse.at
            if int(pulse.severity) > int(meta["severity"]):
                meta["severity"] = pulse.severity

    def flush(self, *, now: datetime) -> tuple[BatchedPulseEvent, ...]:
        """关闭所有已过窗口期的批次并返回（按首触时间排序）。"""
        require_aware(now, "now")
        produced: list[BatchedPulseEvent] = []
        with self._lock:
            for dedupe_key in sorted(list(self._open.keys())):
                bucket = self._open[dedupe_key]
                if not bucket:
                    continue
                meta = self._meta[dedupe_key]
                last_at = max(p.at for p in bucket.values())
                first_at = meta["first_at"]
                window_closed = (now - last_at).total_seconds() >= self._window or (
                    now - first_at
                ).total_seconds() >= self._window
                if not window_closed:
                    continue
                self._seq += 1
                event = BatchedPulseEvent(
                    batch_id=f"batch_{dedupe_key}_{self._seq:04d}",
                    source_class=meta["source_class"],
                    severity=meta["severity"],
                    pulse_count=len(bucket),
                    first_at=first_at,
                    last_at=last_at,
                    dedupe_key=dedupe_key,
                    representative_note=meta["note"],
                )
                produced.append(event)
                self._closed.append(event)
                del self._open[dedupe_key]
                del self._meta[dedupe_key]
        return tuple(sorted(produced, key=lambda e: (e.first_at, e.dedupe_key)))

    def pending_batches(self) -> int:
        with self._lock:
            return len(self._open)


class CooldownPolicy:
    """非致命一般提醒的自适应冷却（15~30 分钟硬防护）。"""

    def __init__(
        self,
        *,
        base_minutes: int = COOLDOWN_BASE_MINUTES,
        max_minutes: int = COOLDOWN_MAX_MINUTES,
    ) -> None:
        if not (0 < base_minutes <= max_minutes):
            raise ValueError("require 0 < base_minutes <= max_minutes")
        self._base = base_minutes
        self._max = max_minutes
        self._lock = threading.RLock()
        self._cooldown_until: dict[str, datetime] = {}
        self._dismiss_streak: dict[str, int] = {}

    def cooldown_minutes_for(self, dedupe_key: str) -> int:
        with self._lock:
            streak = self._dismiss_streak.get(dedupe_key, 0)
            return min(self._base + 5 * streak, self._max)

    def is_cooled_down(self, dedupe_key: str, *, now: datetime) -> bool:
        require_aware(now, "now")
        with self._lock:
            until = self._cooldown_until.get(dedupe_key)
            return until is not None and now < until

    def arm_after_dispatch(self, dedupe_key: str, *, now: datetime) -> datetime:
        """触发后强制进入冷却期，返回冷却截止时刻。"""
        require_aware(now, "now")
        with self._lock:
            minutes = self.cooldown_minutes_for(dedupe_key)
            until = now + timedelta(minutes=minutes)
            self._cooldown_until[dedupe_key] = until
            return until

    def record_dismissal(self, dedupe_key: str) -> int:
        """用户忽略/拒绝一次 → 冷却梯度抬升（自适应上限 30 分钟）。"""
        with self._lock:
            self._dismiss_streak[dedupe_key] = (
                self._dismiss_streak.get(dedupe_key, 0) + 1
            )
            return self._dismiss_streak[dedupe_key]


class SilentQueueEntry(BaseModel):
    """静默挂起的唤醒条目（冻结时的完整现场，零丢失）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: StrictStr
    batch: BatchedPulseEvent
    deferred_at: datetime
    reason: Literal["deep_sleep", "cooldown"] = "deep_sleep"


class DeepSleepGate:
    """深度睡眠绝对静默闸（P0 生命安全独享旁路）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._deep_sleep = False
        self._silent: list[SilentQueueEntry] = []
        self._seq = 0

    @property
    def deep_sleep(self) -> bool:
        with self._lock:
            return self._deep_sleep

    def set_sleep_state(self, *, deep_sleep: bool, at: datetime) -> None:
        require_aware(at, "at")
        with self._lock:
            self._deep_sleep = deep_sleep

    def gate(self, event: BatchedPulseEvent, *, at: datetime) -> bool:
        """返回 True=放行（P0 或清醒），False=静默挂起。"""
        require_aware(at, "at")
        with self._lock:
            if event.severity is WakeSeverity.P0_CRITICAL_SAFETY:
                return True
            if not self._deep_sleep:
                return True
            self._seq += 1
            self._silent.append(
                SilentQueueEntry(
                    entry_id=f"silent_{self._seq:04d}",
                    batch=event,
                    deferred_at=at,
                    reason="deep_sleep",
                )
            )
            return False

    def thaw(self) -> tuple[SilentQueueEntry, ...]:
        """清醒安全窗口：静默队列整体解冻并按序呈现（首触时间+严重度）。"""
        with self._lock:
            entries = sorted(
                self._silent,
                key=lambda e: (e.batch.first_at, -int(e.batch.severity)),
            )
            self._silent.clear()
            return tuple(entries)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._silent)


class DispatchDecision(BaseModel):
    """单条批次事件的最终路由决定（可审计）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: StrictStr
    action: Literal["dispatch_now", "cooled_down", "silent_deferred", "p0_bypass"]
    motor_vibrations: StrictInt = Field(ge=0)
    detail: str = ""


class WakeDispatchCenter:
    """唤醒总闸：合并窗口 → 深睡闸 → 冷却闸 → 派发（P0 全程旁路）。"""

    def __init__(
        self,
        *,
        merge_window: MergeWindow | None = None,
        cooldown: CooldownPolicy | None = None,
        sleep_gate: DeepSleepGate | None = None,
        motor: Callable[[str], None] | None = None,
    ) -> None:
        self.merge_window = merge_window or MergeWindow()
        self.cooldown = cooldown or CooldownPolicy()
        self.sleep_gate = sleep_gate or DeepSleepGate()
        self._motor = motor
        self._motor_vibrations = 0
        self._decisions: list[DispatchDecision] = []
        self._lock = threading.RLock()

    # -- 入口 ---------------------------------------------------------

    def accept(self, pulses: Sequence[WakePulse]) -> None:
        for pulse in pulses:
            self.merge_window.submit(pulse)

    def process(self, *, now: datetime) -> tuple[DispatchDecision, ...]:
        """推进一次派发循环（合并→静默→冷却→执行）。"""
        require_aware(now, "now")
        events = self.merge_window.flush(now=now)
        decisions: list[DispatchDecision] = []
        for event in events:
            if event.severity is WakeSeverity.P0_CRITICAL_SAFETY:
                vibrations = self._fire(event.batch_id)
                decision = DispatchDecision(
                    batch_id=event.batch_id,
                    action="p0_bypass",
                    motor_vibrations=vibrations,
                    detail="P0 生命安全：旁路全部闸门直穿硬件报警",
                )
            elif not self.sleep_gate.gate(event, at=now):
                decision = DispatchDecision(
                    batch_id=event.batch_id,
                    action="silent_deferred",
                    motor_vibrations=0,
                    detail="DEEP_SLEEP 绝对静默：挂起至清醒安全窗口",
                )
            elif self.cooldown.is_cooled_down(event.dedupe_key, now=now):
                decision = DispatchDecision(
                    batch_id=event.batch_id,
                    action="cooled_down",
                    motor_vibrations=0,
                    detail="冷却防护期内：合并丢弃（窗口内证据已留存）",
                )
            else:
                vibrations = self._fire(event.batch_id)
                self.cooldown.arm_after_dispatch(event.dedupe_key, now=now)
                decision = DispatchDecision(
                    batch_id=event.batch_id,
                    action="dispatch_now",
                    motor_vibrations=vibrations,
                    detail=f"正常派发，进入 {self.cooldown.cooldown_minutes_for(event.dedupe_key)} 分钟冷却",
                )
            with self._lock:
                self._decisions.append(decision)
            decisions.append(decision)
        return tuple(decisions)

    def thaw_silent_queue(self) -> tuple[SilentQueueEntry, ...]:
        """晨间下床安全窗口：解冻静默队列，聚合呈现一次（单次马达振动）。"""
        entries = self.sleep_gate.thaw()
        if entries:
            self._fire("thaw_aggregate_presentation")
        return entries

    # -- 观测 ---------------------------------------------------------

    @property
    def motor_vibration_count(self) -> int:
        with self._lock:
            return self._motor_vibrations

    def decisions(self) -> tuple[DispatchDecision, ...]:
        with self._lock:
            return tuple(self._decisions)

    def _fire(self, batch_id: str) -> int:
        with self._lock:
            self._motor_vibrations += 1
        if self._motor is not None:
            self._motor(batch_id)
        return 1
