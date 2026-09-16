"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

场景：手环佩戴者处于高频运动状态（羽毛球赛后心率剧烈波动、50Hz
加速度计离散数据洪流）或凌晨 02:00~06:00 深度睡眠阶段。四道硬门禁：

1. 5 秒合并窗口：窗口内涌入的同签名离散脉冲自动去重聚合为单条批次
   事件，禁止逐条唤醒下游心智流水线；
2. 冷却硬防护：非致命一般提醒触发后强制进入 15~30 分钟自适应冷却；
3. DEEP_SLEEP 绝对静默：除 P0 生命安全事件硬件直穿外，一般通知 /
   复盘反思 / 任务提醒全部挂起，物理马达振动次数严格为 0；
4. 无损延递：晨间清醒后的第一个安全窗口，静默队列自动解冻、有序聚合。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aios_core.contracts.safety_bypass import WakePriority

__all__ = [
    "COALESCE_WINDOW_SECONDS",
    "MAX_COOLDOWN_SECONDS",
    "MIN_COOLDOWN_SECONDS",
    "BatchedWakeEvent",
    "DeepSleepGate",
    "SleepStage",
    "WakeCooldownQueue",
    "WakeKind",
    "WakePulse",
]

COALESCE_WINDOW_SECONDS = 5.0
MIN_COOLDOWN_SECONDS = 15 * 60
MAX_COOLDOWN_SECONDS = 30 * 60
_COOLDOWN_STEP_SECONDS = 5 * 60


class SleepStage(StrEnum):
    AWAKE = "awake"
    LIGHT_SLEEP = "light_sleep"
    DEEP_SLEEP = "deep_sleep"


class WakeKind(StrEnum):
    SENSOR_BATCH = "sensor_batch"
    GENERAL_REMINDER = "general_reminder"
    RETROSPECTIVE = "retrospective"
    TASK_REMINDER = "task_reminder"
    P0_SAFETY = "p0_safety"


@dataclass(frozen=True)
class WakePulse:
    """一条离散唤醒脉冲（传感器洪流的原始个体）。"""

    pulse_id: str
    kind: WakeKind
    signature: str
    occurred_at: float
    priority: WakePriority = WakePriority.P2_NORMAL_INTERACT
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchedWakeEvent:
    """合并窗口输出的单条批次事件（N 条脉冲 -> 1 条）。"""

    signature: str
    kind: WakeKind
    count: int
    first_at: float
    last_at: float
    priority: WakePriority
    pulse_ids: tuple[str, ...]


class DeepSleepGate:
    """深度睡眠绝对静默闸：P0 硬件直穿豁免，其余全挂起、马达零振动。"""

    def __init__(self) -> None:
        self._stage: SleepStage = SleepStage.AWAKE
        self._silent_queue: deque[WakePulse | BatchedWakeEvent] = deque()
        self.motor_vibrations = 0
        self.p0_passes = 0
        self.suspended_count = 0

    @property
    def stage(self) -> SleepStage:
        return self._stage

    @property
    def silent_queue_size(self) -> int:
        return len(self._silent_queue)

    def set_stage(self, stage: SleepStage) -> None:
        self._stage = stage

    def admit(
        self, event: WakePulse | BatchedWakeEvent, *, is_p0: bool
    ) -> str:
        """裁决一条事件：``deliver`` / ``suspend``。"""

        if is_p0:
            # P0 生命安全事件任何阶段硬件直穿，绝不静默。
            self.p0_passes += 1
            return "deliver"
        if self._stage is SleepStage.DEEP_SLEEP:
            self._silent_queue.append(event)
            self.suspended_count += 1
            return "suspend"
        return "deliver"

    def vibrate(self, times: int = 1) -> None:
        """物理马达振动记账：深睡静默期间严禁对挂起事件调用。"""

        self.motor_vibrations += times

    def release_on_wake(self) -> tuple[WakePulse | BatchedWakeEvent, ...]:
        """清醒安全窗口：静默队列无损解冻，按原始时间戳有序聚合。"""

        pending = sorted(self._silent_queue, key=_event_sort_key)
        self._silent_queue.clear()
        return tuple(pending)


def _event_sort_key(event: WakePulse | BatchedWakeEvent) -> float:
    if isinstance(event, BatchedWakeEvent):
        return event.first_at
    return event.occurred_at


class WakeCooldownQueue:
    """唤醒总闸：合并窗口 + 自适应冷却 + 深睡静默 + 无损延递。"""

    def __init__(self) -> None:
        self._window_start: float | None = None
        self._pending: dict[str, list[WakePulse]] = {}
        self._cooldown_until: dict[str, float] = {}
        self._cooldown_span: dict[str, int] = {}
        self.gate = DeepSleepGate()
        self.downstream_wake_calls = 0
        self.suppressed_by_cooldown = 0
        self.delivered_signatures: list[str] = []

    # -- 门禁 1：5 秒合并窗口 ---------------------------------------------------

    def enqueue(self, pulse: WakePulse) -> None:
        if self._window_start is None:
            self._window_start = pulse.occurred_at
        self._pending.setdefault(pulse.signature, []).append(pulse)

    def flush_window(self, now: float) -> tuple[BatchedWakeEvent, ...]:
        """窗口到期：同签名脉冲去重聚合为单条批次事件。"""

        batches: list[BatchedWakeEvent] = []
        for signature, pulses in self._pending.items():
            in_window = [
                p
                for p in pulses
                if self._window_start is not None
                and p.occurred_at - self._window_start <= COALESCE_WINDOW_SECONDS
            ]
            if not in_window:
                continue
            unique: dict[str, WakePulse] = {}
            for pulse in in_window:
                unique.setdefault(pulse.pulse_id, pulse)
            deduped = sorted(unique.values(), key=lambda p: p.occurred_at)
            priority = WakePriority.P0_CRITICAL_SAFETY if any(
                p.priority is WakePriority.P0_CRITICAL_SAFETY for p in deduped
            ) else deduped[0].priority
            batches.append(
                BatchedWakeEvent(
                    signature=signature,
                    kind=deduped[0].kind,
                    count=len(deduped),
                    first_at=deduped[0].occurred_at,
                    last_at=deduped[-1].occurred_at,
                    priority=priority,
                    pulse_ids=tuple(p.pulse_id for p in deduped),
                )
            )
        self._pending.clear()
        self._window_start = None
        batches.sort(key=lambda b: b.first_at)
        return tuple(batches)

    # -- 门禁 2/3：冷却硬防护 + 深睡静默联合路由 ----------------------------------

    def route_batch(self, event: BatchedWakeEvent, now: float) -> str:
        """批次事件路由：P0 直穿 / 深睡挂起 / 冷却抑制 / 正常送达。"""

        is_p0 = event.priority is WakePriority.P0_CRITICAL_SAFETY
        verdict = self.gate.admit(event, is_p0=is_p0)
        if verdict == "suspend":
            return "suspended"
        if not is_p0 and self._in_cooldown(event.signature, now):
            self.suppressed_by_cooldown += 1
            self._escalate_cooldown(event.signature)
            return "cooldown_suppressed"
        self._deliver(event, now, vibrate=not is_p0)
        return "delivered"

    def route_pulse(self, pulse: WakePulse, now: float) -> str:
        """单条脉冲路由（提醒/复盘类事件，无合并窗口路径）。"""

        is_p0 = pulse.priority is WakePriority.P0_CRITICAL_SAFETY
        verdict = self.gate.admit(pulse, is_p0=is_p0)
        if verdict == "suspend":
            return "suspended"
        if not is_p0 and self._in_cooldown(pulse.signature, now):
            self.suppressed_by_cooldown += 1
            self._escalate_cooldown(pulse.signature)
            return "cooldown_suppressed"
        self._deliver(pulse, now, vibrate=not is_p0)
        return "delivered"

    def _deliver(self, event: WakePulse | BatchedWakeEvent, now: float, *, vibrate: bool) -> None:
        self.downstream_wake_calls += 1
        signature = event.signature
        self.delivered_signatures.append(signature)
        if not isinstance(event, WakePulse) or event.priority is not WakePriority.P0_CRITICAL_SAFETY:
            self._arm_cooldown(signature, now)
        if vibrate:
            self.gate.vibrate(1)

    def _in_cooldown(self, signature: str, now: float) -> bool:
        until = self._cooldown_until.get(signature)
        return until is not None and now < until

    def _arm_cooldown(self, signature: str, now: float) -> None:
        span = self._cooldown_span.get(signature, 0)
        cooldown = min(
            MIN_COOLDOWN_SECONDS + span * _COOLDOWN_STEP_SECONDS,
            MAX_COOLDOWN_SECONDS,
        )
        self._cooldown_until[signature] = now + cooldown

    def _escalate_cooldown(self, signature: str) -> None:
        self._cooldown_span[signature] = self._cooldown_span.get(signature, 0) + 1

    def cooldown_seconds(self, signature: str) -> float:
        span = self._cooldown_span.get(signature, 0)
        return float(
            min(MIN_COOLDOWN_SECONDS + span * _COOLDOWN_STEP_SECONDS, MAX_COOLDOWN_SECONDS)
        )

    # -- 门禁 4：静默队列无损唤醒延递 -------------------------------------------

    def wake_up_window(self) -> tuple[WakePulse | BatchedWakeEvent, ...]:
        """晨间清醒第一个安全窗口：解冻静默队列，有序聚合呈现。"""

        released = self.gate.release_on_wake()
        for event in released:
            self.downstream_wake_calls += 1
            self.delivered_signatures.append(event.signature)
        if released:
            self.gate.vibrate(1)  # 清醒窗口一次性聚合提示
        return released
