"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。
独立命名并存线（agent-05）：本模块为同工单独立命名交付版本，与共享分支上的规范实现并存，零覆盖；详见批次报告 agent-05-m2m3-sim-batch-20260916。

实战业务情境：手环佩戴者处于高频运动状态（羽毛球赛后心率剧烈波动、
加速度传感器 50Hz 持续产生离散数据）或凌晨 02:00~06:00 深度睡眠阶段。

四大硬门禁（宪法级承诺）：

1. **高频传感器防抖与合并窗口**：5 秒内涌入的 250 条离散物理体征脉冲
   （50Hz 采样 × 5s）由合并队列自动去重并聚合为**单条**批次事件，
   禁止逐条唤醒下游心智流水线（``downstream_wakes`` 是审计口径）；
2. **冷却时间（Cooldown）硬防护**：非致命一般提醒触发后强制进入
   15~30 分钟自适应冷却期（被抑制则 +5min 升级、封顶 30min、
   用户确认回落 15min），防止手环高频骚扰；
3. **深度睡眠绝对静默（DEEP_SLEEP GATE）**：深度睡眠阶段除 P0 生命安全
   事件（心梗跌倒硬件直穿，经 ``wake.dispatcher`` 既有脉冲通道）外，
   所有一般通知/复盘反思/任务提醒全部强制挂起静默，
   一般通知物理马达振动次数严格为 0；
4. **静默队列无损唤醒延递**：晨间清醒下床后的第一个安全窗口，
   静默队列自动解冻并做有序聚合呈现（无损、保序、分组）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from aios_core.contracts.safety_bypass import WakePriority
from . import dispatcher as _dispatcher

#: 合并窗口（门禁 1）：5 秒内离散脉冲聚合成单条批次事件
MERGE_WINDOW = timedelta(seconds=5)
#: 冷却期上下界（门禁 2）：15~30 分钟自适应
COOLDOWN_FLOOR = timedelta(minutes=15)
COOLDOWN_CEILING = timedelta(minutes=30)
#: 每次被抑制后的冷却升级步长
COOLDOWN_ESCALATION_STEP = timedelta(minutes=5)

_PULSE_DISPATCHER = Callable[[str, Dict], bool]


class SleepPhase(str, Enum):
    AWAKE = "awake"
    LIGHT_SLEEP = "light_sleep"
    DEEP_SLEEP = "deep_sleep"


# ----------------------------------------------------------------------
# 物理脉冲与合并批次（门禁 1）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalPulse:
    """单条离散物理体征脉冲（50Hz 加速度/心率/HRV 采样点）。"""

    seq: int
    at: datetime
    channel: str  # "hr" | "hrv" | "accel_x" | "accel_y" | "accel_z" | "noise_db"
    value: float


@dataclass(frozen=True)
class ChannelStats:
    """单通道聚合统计（去重后的审计口径）。"""

    count: int
    unique: int
    min_value: float
    max_value: float
    mean_value: float


@dataclass(frozen=True)
class MergedBatchEvent:
    """5 秒窗口合并后的单条批次事件（下游心智流水线只见到它）。"""

    batch_id: str
    window_start: datetime
    window_end: datetime
    pulse_count: int
    channels: Mapping[str, ChannelStats]
    first_seq: int
    last_seq: int


def _quantize(value: float) -> float:
    """去重量化：0.1 分辨率（传感器离散抖动不构成新数据）。"""
    return round(value * 10.0) / 10.0


# ----------------------------------------------------------------------
# 唤醒通知（门禁 2/3/4）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class WakeNotification:
    """一条非致命唤醒通知（一般提醒/复盘反思/任务提醒）。"""

    notification_id: str
    at: datetime
    category: str  # "task_reminder" | "retrospective" | "general"
    payload: Dict = field(default_factory=dict)
    priority: WakePriority = WakePriority.P2_NORMAL_INTERACT


@dataclass(frozen=True)
class DeliveryResult:
    action: str  # DELIVERED | SUPPRESSED_COOLDOWN | SILENT_SUSPENDED_DEEP_SLEEP | P0_HARDWARE_PASSTHROUGH
    notification_id: str
    vibration_counted: bool
    hardware_pulse_sent: bool
    at: datetime


class WakeCooldownQueue:
    """高频唤醒去重合并队列 + 冷却硬防护 + DEEP_SLEEP 绝对静默闸。

    - 传感器侧：``ingest_physical_pulse`` / ``flush_pending``（合并窗口去重聚合）；
    - 通知侧：``notify``（P0 直穿 / 静默挂起 / 冷却抑制 / 正常投递）；
    - 睡眠侧：``set_sleep_phase`` / ``mark_awake``（第一安全窗口无损解冻）。
    """

    def __init__(
        self,
        *,
        merge_window: timedelta = MERGE_WINDOW,
        cooldown_floor: timedelta = COOLDOWN_FLOOR,
        cooldown_ceiling: timedelta = COOLDOWN_CEILING,
        escalation_step: timedelta = COOLDOWN_ESCALATION_STEP,
        pulse_dispatcher: Optional[_PULSE_DISPATCHER] = None,
    ) -> None:
        if not (timedelta(0) < cooldown_floor <= cooldown_ceiling):
            raise ValueError("require 0 < cooldown_floor <= cooldown_ceiling")
        self.merge_window = merge_window
        self.cooldown_floor = cooldown_floor
        self.cooldown_ceiling = cooldown_ceiling
        self.escalation_step = escalation_step
        # P0 硬件脉冲缺省经 dispatcher 模块命名空间**调用时解析**
        # （与 V1 主链同一调用点，升级/spy 同时生效）
        self._pulse_dispatcher = pulse_dispatcher

        # ---- 门禁 1：合并缓冲区 ----
        self._buffer: List[PhysicalPulse] = []
        self._batch_seq = 0
        self.downstream_wakes = 0  # 交给下游心智流水线的批次事件数（审计口径）

        # ---- 门禁 2：冷却状态 ----
        self._last_delivered_at: Optional[datetime] = None
        self._suppression_streak = 0
        self._cooldown = cooldown_floor
        self.suppressed_count = 0
        self.general_vibration_count = 0

        # ---- 门禁 3/4：睡眠静默 ----
        self._sleep_phase = SleepPhase.AWAKE
        self._silent_queue: List[WakeNotification] = []
        self.p0_hardware_pulse_count = 0
        self.thawed_notifications: List[WakeNotification] = []

    # ==================================================================
    # 门禁 1：高频传感器防抖与合并窗口
    # ==================================================================

    def ingest_physical_pulse(self, pulse: PhysicalPulse) -> Optional[MergedBatchEvent]:
        """接收单条离散脉冲；窗口（5s）关闭时自动产出**单条**批次事件。"""
        if not self._buffer:
            self._buffer.append(pulse)
            return None
        if pulse.at - self._buffer[0].at >= self.merge_window:
            batch = self._close_batch()
            self._buffer = [pulse]
            return batch
        self._buffer.append(pulse)
        return None

    def flush_pending(self) -> Optional[MergedBatchEvent]:
        """流结束时冲刷未闭窗的残余脉冲（仍聚合为单条批次）。"""
        if not self._buffer:
            return None
        return self._close_batch()

    def _close_batch(self) -> MergedBatchEvent:
        pulses = self._buffer
        self._buffer = []
        self._batch_seq += 1
        per_channel: Dict[str, list] = {}
        for pulse in pulses:
            per_channel.setdefault(pulse.channel, []).append(pulse)
        channels: Dict[str, ChannelStats] = {}
        for channel, items in per_channel.items():
            values = [p.value for p in items]
            unique = len({_quantize(v) for v in values})
            channels[channel] = ChannelStats(
                count=len(items),
                unique=unique,
                min_value=min(values),
                max_value=max(values),
                mean_value=sum(values) / len(values),
            )
        batch = MergedBatchEvent(
            batch_id=f"batch:{self._batch_seq:06d}",
            window_start=pulses[0].at,
            window_end=pulses[-1].at,
            pulse_count=len(pulses),
            channels=channels,
            first_seq=pulses[0].seq,
            last_seq=pulses[-1].seq,
        )
        # 一条批次事件 = 一次下游唤醒（严禁 250 条逐条唤醒）
        self.downstream_wakes += 1
        return batch

    # ==================================================================
    # 门禁 2：冷却时间硬防护（15~30 分钟自适应）
    # ==================================================================

    @property
    def current_cooldown(self) -> timedelta:
        return self._cooldown

    @property
    def in_cooldown(self) -> bool:
        return self._last_delivered_at is not None

    def _cooldown_active_at(self, at: datetime) -> bool:
        return self._last_delivered_at is not None and at - self._last_delivered_at < self._cooldown

    def acknowledge(self) -> None:
        """用户已处理：冷却期回落至下限（自适应回落）。"""
        self._suppression_streak = 0
        self._cooldown = self.cooldown_floor

    # ==================================================================
    # 门禁 3 + 统一投递入口
    # ==================================================================

    def set_sleep_phase(self, phase: SleepPhase, at: datetime) -> None:
        self._sleep_phase = phase

    @property
    def sleep_phase(self) -> SleepPhase:
        return self._sleep_phase

    def notify(self, notification: WakeNotification) -> DeliveryResult:
        """统一投递入口：P0 直穿 → DEEP_SLEEP 静默挂起 → 冷却抑制 → 正常投递。"""
        at = notification.at
        # —— P0 生命安全事件：任何状态下硬件直穿（心梗跌倒），绝不静默 ——
        if notification.priority is WakePriority.P0_CRITICAL_SAFETY:
            pulse_fn = self._pulse_dispatcher or _dispatcher.dispatch_emergency_hardware_pulse
            pulse_fn("EMERGENCY_BROADCAST_AND_SOS", dict(notification.payload))
            self.p0_hardware_pulse_count += 1
            return DeliveryResult(
                action="P0_HARDWARE_PASSTHROUGH",
                notification_id=notification.notification_id,
                vibration_counted=False,
                hardware_pulse_sent=True,
                at=at,
            )

        # —— DEEP_SLEEP 绝对静默闸：一般通知/复盘/任务提醒全部挂起 ——
        if self._sleep_phase is SleepPhase.DEEP_SLEEP:
            self._silent_queue.append(notification)
            return DeliveryResult(
                action="SILENT_SUSPENDED_DEEP_SLEEP",
                notification_id=notification.notification_id,
                vibration_counted=False,
                hardware_pulse_sent=False,
                at=at,
            )

        # —— 冷却硬防护（15~30 分钟自适应）——
        if self._cooldown_active_at(at):
            self.suppressed_count += 1
            self._suppression_streak += 1
            self._cooldown = min(
                self.cooldown_ceiling,
                self.cooldown_floor + self.escalation_step * self._suppression_streak,
            )
            return DeliveryResult(
                action="SUPPRESSED_COOLDOWN",
                notification_id=notification.notification_id,
                vibration_counted=False,
                hardware_pulse_sent=False,
                at=at,
            )

        self.general_vibration_count += 1
        self._last_delivered_at = at
        self._suppression_streak = 0
        self._cooldown = self.cooldown_floor
        return DeliveryResult(
            action="DELIVERED",
            notification_id=notification.notification_id,
            vibration_counted=True,
            hardware_pulse_sent=False,
            at=at,
        )

    # ==================================================================
    # 门禁 4：静默队列无损唤醒延递（第一安全窗口解冻）
    # ==================================================================

    def pending_silent(self) -> Tuple[WakeNotification, ...]:
        """当前静默挂起的通知（只读视图，无损可审计）。"""
        return tuple(self._silent_queue)

    def mark_awake(self, at: datetime) -> Tuple[WakeNotification, ...]:
        """晨间清醒并下床（走出睡眠状态）后的第一个安全窗口：解冻静默队列。

        - 无损：所有挂起通知全部延递，一条不丢；
        - 有序：按原始到达顺序聚合呈现；
        - 解冻投递计入一般振动（此时已清醒，不再受静默闸约束）；
        - 解冻后冷却窗口从最后一条延递开始计算。

        守卫：静默队列为空且不在 DEEP_SLEEP 状态时为空操作；
        静默队列非空时允许解冻（调用方保证"已走出睡眠状态"的安全窗口语义，
        覆盖"浅睡残留 + 静默挂起"的边界情形）。
        """
        if not self._silent_queue and self._sleep_phase is not SleepPhase.DEEP_SLEEP:
            return ()
        self._sleep_phase = SleepPhase.AWAKE
        ordered = list(self._silent_queue)
        self._silent_queue = []
        for notification in ordered:
            self.general_vibration_count += 1
            self._last_delivered_at = notification.at
        if ordered:
            self.thawed_notifications.extend(ordered)
        self._suppression_streak = 0
        self._cooldown = self.cooldown_floor
        return tuple(ordered)

    def aggregated_thaw_view(self, thawed: Sequence[WakeNotification]) -> Dict[str, Tuple[str, ...]]:
        """解冻后的分组聚合呈现（按类别，组内保持原始顺序）。"""
        groups: Dict[str, List[str]] = {}
        for notification in thawed:
            groups.setdefault(notification.category, []).append(notification.notification_id)
        return {category: tuple(ids) for category, ids in groups.items()}
