"""M2-001：高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

对应《AIOS 核心系统宪法 v3.0》第九十八条之一（柔性全屏手环物理形态与
交互状态机 / FSM 零误触宪章）与第八十六条（零浪费执行法则）。

业务情境：佩戴者打完羽毛球后心率剧烈波动、加速度传感器 50Hz 持续产生离散
数据；或处于凌晨 02:00~06:00 深度睡眠。这两种状态下若逐条唤醒下游心智
流水线，既烧 Token 又骚扰用户。

四道闸门
--------
1. **合并窗口（Merge Window）**：窗口内涌入的离散物理脉冲聚合为**单条批次
   事件**，禁止逐条唤醒下游。250 条 / 5 秒 → 1 次唤醒。
2. **自适应冷却（Cooldown）**：非致命一般提醒触发后强制进入 15~30 分钟
   冷却期，防止手环形成高频骚扰。冷却时长随近期打扰密度自适应上浮。
3. **深度睡眠绝对静默（DEEP_SLEEP GATE）**：除 P0 生命安全事件（心梗、跌倒
   等硬件直穿）外，一般通知 / 复盘反思 / 任务提醒全部强制挂起，
   **物理马达振动次数严格为 0**。
4. **静默队列无损延递**：晨间清醒后的第一个安全窗口，静默队列自动解冻并
   **有序聚合**呈现——挂起不是丢弃。

与 M0 冻结契约的关系
--------------------
优先级复用 ``contracts/safety_bypass.py`` 的 ``WakePriority``
（``P0_CRITICAL_SAFETY`` / ``P1_URGENT_TASK`` / ``P2_NORMAL_INTERACT`` /
``P3_BACKGROUND_TICK``），不新增枚举值。P0 的硬件直穿路径由
``wake/dispatcher.py`` 负责，本模块**不拦截** P0，只负责其余三级的
去重、冷却与静默。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.safety_bypass import WakePriority
from aios_core.contracts.time import as_utc, require_aware

__all__ = [
    "BatchedPulseEvent",
    "CooldownLedger",
    "DeepSleepGate",
    "MergeWindow",
    "SilentQueueThawReport",
    "WakeCandidate",
    "WakeCooldownQueue",
    "WakeDisposition",
]

# 合并窗口：5 秒内的离散脉冲聚合为一条批次事件
DEFAULT_MERGE_WINDOW_SECONDS = 5.0
# 冷却区间：非致命一般提醒 15~30 分钟
COOLDOWN_FLOOR_MINUTES = 15
COOLDOWN_CEILING_MINUTES = 30


class WakeDisposition(StrEnum):
    """一次唤醒候选的最终处置。"""

    DISPATCHED = "dispatched"          # 放行到下游心智流水线
    MERGED = "merged"                  # 被合并窗口吸收，未单独唤醒
    COOLED_DOWN = "cooled_down"        # 处于冷却期，挂起
    SUPPRESSED_DEEP_SLEEP = "suppressed_deep_sleep"  # 深度睡眠静默闸拦截
    P0_BYPASS = "p0_bypass"            # P0 生命安全，硬件直穿，不受任何闸门约束


class WakeCandidate(BaseModel):
    """一次唤醒候选。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    topic_key: str = Field(min_length=1)  # 去重键：同一主题的脉冲归并
    priority: WakePriority
    occurred_at: datetime
    source_modality: str = Field(default="sensor")
    payload_digest: str = Field(default="")
    is_motor_feedback_requested: bool = True

    @model_validator(mode="after")
    def occurred_at_must_be_aware(self) -> WakeCandidate:
        require_aware(self.occurred_at, "occurred_at")
        return self


class BatchedPulseEvent(BaseModel):
    """合并窗口产出的单条批次事件。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_key: str
    window_start: datetime
    window_end: datetime
    absorbed_count: int = Field(ge=0)
    member_candidate_ids: tuple[str, ...] = ()
    # 批次里只要有一条成员请求过马达反馈，整批才允许震动一次。
    # 后台调度类候选（任务提醒 / 复盘提示）不请求马达反馈，
    # 于是它们永远走"静默呈现"，不会把手环变成骚扰源。
    motor_feedback_requested: bool = False
    aggregated_payload: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def window_must_be_ordered(self) -> BatchedPulseEvent:
        start = as_utc(self.window_start, "window_start")
        end = as_utc(self.window_end, "window_end")
        if end < start:
            raise ValueError("window_end must not precede window_start")
        if len(self.member_candidate_ids) != self.absorbed_count:
            raise ValueError("absorbed_count must match member_candidate_ids length")
        return self


class MergeWindow:
    """高频脉冲防抖：窗口内同主题脉冲聚合，窗口外或主题变更时冲刷。"""

    def __init__(self, window_seconds: float = DEFAULT_MERGE_WINDOW_SECONDS) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._window_seconds = window_seconds
        self._buffers: dict[str, list[WakeCandidate]] = {}
        self.absorbed_total = 0
        self.emitted_batches = 0

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    def offer(self, candidate: WakeCandidate) -> BatchedPulseEvent | None:
        """投喂一条候选。

        返回 ``None`` 表示被吸收进当前窗口（不唤醒下游）；
        返回 :class:`BatchedPulseEvent` 表示窗口关闭并冲刷出一条批次事件。
        """
        bucket = self._buffers.setdefault(candidate.topic_key, [])
        flushed: BatchedPulseEvent | None = None

        if bucket:
            window_start = as_utc(bucket[0].occurred_at, "occurred_at")
            now = as_utc(candidate.occurred_at, "occurred_at")
            if (now - window_start).total_seconds() > self._window_seconds:
                flushed = self._flush(candidate.topic_key, window_end=now)

        self._buffers.setdefault(candidate.topic_key, []).append(candidate)
        return flushed

    def flush_all(self, now: datetime) -> tuple[BatchedPulseEvent, ...]:
        """强制冲刷所有缓冲（例如进入深度睡眠前、或晨间解冻时）。"""
        require_aware(now, "now")
        out: list[BatchedPulseEvent] = []
        for topic_key in list(self._buffers):
            if self._buffers[topic_key]:
                out.append(self._flush(topic_key, window_end=as_utc(now, "now")))
        return tuple(out)

    def pending_count(self) -> int:
        return sum(len(bucket) for bucket in self._buffers.values())

    def _flush(self, topic_key: str, *, window_end: datetime) -> BatchedPulseEvent:
        members = self._buffers.pop(topic_key, [])
        self._buffers[topic_key] = []
        batch = BatchedPulseEvent(
            topic_key=topic_key,
            window_start=members[0].occurred_at,
            window_end=window_end,
            absorbed_count=len(members),
            member_candidate_ids=tuple(m.candidate_id for m in members),
            motor_feedback_requested=any(
                m.is_motor_feedback_requested for m in members
            ),
            aggregated_payload={
                "modality": members[0].source_modality,
                "priority": members[0].priority.value,
                "sample_count": len(members),
            },
        )
        self.absorbed_total += len(members)
        self.emitted_batches += 1
        return batch


class CooldownLedger:
    """非致命提醒的自适应冷却台账。

    冷却时长在 15~30 分钟区间内自适应：近期打扰越密集，冷却越长。
    P0 生命安全事件**从不**进入冷却（由 DeepSleepGate 之前的 P0 分支放行）。
    """

    def __init__(
        self,
        *,
        floor_minutes: int = COOLDOWN_FLOOR_MINUTES,
        ceiling_minutes: int = COOLDOWN_CEILING_MINUTES,
    ) -> None:
        if floor_minutes < 1 or ceiling_minutes < floor_minutes:
            raise ValueError("require 1 <= floor_minutes <= ceiling_minutes")
        self._floor = floor_minutes
        self._ceiling = ceiling_minutes
        self._last_dispatch: dict[str, datetime] = {}
        self._recent_dispatches: deque[datetime] = deque(maxlen=20)

    @property
    def floor_minutes(self) -> int:
        return self._floor

    @property
    def ceiling_minutes(self) -> int:
        return self._ceiling

    def cooldown_seconds_for(self, topic_key: str, now: datetime) -> float:
        """按近期打扰密度给出该主题的冷却秒数。"""
        require_aware(now, "now")
        now_utc = as_utc(now, "now")
        recent = sum(
            1
            for stamp in self._recent_dispatches
            if (now_utc - stamp).total_seconds() <= 3600
        )
        # 0 次 -> floor；>= 10 次/小时 -> ceiling；线性插值
        ratio = min(recent / 10.0, 1.0)
        minutes = self._floor + (self._ceiling - self._floor) * ratio
        return minutes * 60.0

    def is_cooling(self, topic_key: str, now: datetime) -> bool:
        last = self._last_dispatch.get(topic_key)
        if last is None:
            return False
        elapsed = (as_utc(now, "now") - as_utc(last, "last_dispatch")).total_seconds()
        return elapsed < self.cooldown_seconds_for(topic_key, now)

    def remaining_seconds(self, topic_key: str, now: datetime) -> float:
        last = self._last_dispatch.get(topic_key)
        if last is None:
            return 0.0
        elapsed = (as_utc(now, "now") - as_utc(last, "last_dispatch")).total_seconds()
        return max(0.0, self.cooldown_seconds_for(topic_key, now) - elapsed)

    def record_dispatch(self, topic_key: str, now: datetime) -> None:
        require_aware(now, "now")
        stamp = as_utc(now, "now")
        self._last_dispatch[topic_key] = stamp
        self._recent_dispatches.append(stamp)

    def within_bounds(self, topic_key: str, now: datetime) -> bool:
        """冷却时长必须落在 15~30 分钟区间内。"""
        seconds = self.cooldown_seconds_for(topic_key, now)
        return self._floor * 60 <= seconds <= self._ceiling * 60


class DeepSleepGate:
    """深度睡眠绝对静默闸。

    除 ``P0_CRITICAL_SAFETY`` 外一律拦截，且**马达振动次数严格为 0**：
    被拦截的候选既不震动、也不出声、也不上屏，只进静默队列。
    """

    def __init__(self) -> None:
        self._deep_sleep = False
        self._motor_vibrations = 0
        self._suppressed_total = 0

    @property
    def is_deep_sleep(self) -> bool:
        return self._deep_sleep

    def enter_deep_sleep(self) -> None:
        self._deep_sleep = True

    def exit_deep_sleep(self) -> None:
        self._deep_sleep = False

    @property
    def motor_vibration_count(self) -> int:
        """物理马达振动次数。深度睡眠期间被拦截的事件不得贡献任何一次。"""
        return self._motor_vibrations

    def record_vibration(self, count: int = 1) -> None:
        if self._deep_sleep:
            raise RuntimeError(
                "motor vibration is physically forbidden during DEEP_SLEEP"
            )
        self._motor_vibrations += count

    def admit(self, candidate: WakeCandidate) -> bool:
        """返回 True 表示放行；False 表示静默拦截（由队列负责挂起，不在此留存）。"""
        if candidate.priority == WakePriority.P0_CRITICAL_SAFETY:
            return True
        if not self._deep_sleep:
            return True
        self._suppressed_total += 1
        return False

    @property
    def suppressed_total(self) -> int:
        """深度睡眠期间被静默拦截的累计条数（只计数，不留副本）。"""
        return self._suppressed_total


class SilentQueueThawReport(BaseModel):
    """晨间解冻的聚合呈现结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    thawed_at: datetime
    topic_groups: tuple[str, ...] = ()
    total_candidates: int = Field(default=0, ge=0)
    lost_candidates: int = Field(default=0, ge=0)
    motor_vibrations_used: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def thawed_at_must_be_aware(self) -> SilentQueueThawReport:
        require_aware(self.thawed_at, "thawed_at")
        return self


class WakeCooldownQueue:
    """把合并窗口、冷却台账、深度睡眠闸串成一条唤醒准入流水线。"""

    def __init__(
        self,
        *,
        merge_window_seconds: float = DEFAULT_MERGE_WINDOW_SECONDS,
        cooldown_floor_minutes: int = COOLDOWN_FLOOR_MINUTES,
        cooldown_ceiling_minutes: int = COOLDOWN_CEILING_MINUTES,
    ) -> None:
        self.merge_window = MergeWindow(merge_window_seconds)
        self.cooldown = CooldownLedger(
            floor_minutes=cooldown_floor_minutes,
            ceiling_minutes=cooldown_ceiling_minutes,
        )
        self.deep_sleep_gate = DeepSleepGate()
        self._silent_queue: deque[WakeCandidate] = deque()
        self.dispatched_total = 0
        self.p0_bypass_total = 0
        self.cooled_down_total = 0
        self.last_dispatched_batch: BatchedPulseEvent | None = None

    # ------------------------------------------------------------- 准入

    def submit(self, candidate: WakeCandidate) -> WakeDisposition:
        """提交一次唤醒候选，返回其处置。

        顺序：**P0 直穿 → 深度睡眠闸 → 合并窗口 → 冷却**。
        P0 永远第一，因为它是硬件直穿路径，不能被任何闸门延迟。
        """
        # 1. P0 生命安全：绕过一切闸门
        if candidate.priority == WakePriority.P0_CRITICAL_SAFETY:
            self.p0_bypass_total += 1
            self.dispatched_total += 1
            return WakeDisposition.P0_BYPASS

        # 2. 深度睡眠绝对静默
        if not self.deep_sleep_gate.admit(candidate):
            self._silent_queue.append(candidate)
            return WakeDisposition.SUPPRESSED_DEEP_SLEEP

        # 3. 合并窗口：窗口未关闭时只吸收，绝不单独唤醒下游
        batch = self.merge_window.offer(candidate)
        if batch is None:
            return WakeDisposition.MERGED

        # 4. 窗口已关闭 → 这一整簇脉冲合并为一次投递，再过冷却闸
        return self._dispatch_batch(batch, candidate.occurred_at)

    def _dispatch_batch(
        self, batch: BatchedPulseEvent, now: datetime
    ) -> WakeDisposition:
        now_utc = as_utc(now, "now")
        if self.deep_sleep_gate.is_deep_sleep:
            return WakeDisposition.SUPPRESSED_DEEP_SLEEP
        if self.cooldown.is_cooling(batch.topic_key, now_utc):
            self.cooled_down_total += 1
            return WakeDisposition.COOLED_DOWN
        self.cooldown.record_dispatch(batch.topic_key, now_utc)
        self.dispatched_total += 1
        self.last_dispatched_batch = batch
        if batch.motor_feedback_requested:
            self.deep_sleep_gate.record_vibration()
        return WakeDisposition.DISPATCHED

    def submit_batch(self, candidates: Iterable[WakeCandidate]) -> list[WakeDisposition]:
        return [self.submit(c) for c in candidates]

    def flush_and_dispatch(self, now: datetime) -> tuple[BatchedPulseEvent, ...]:
        """关闭所有合并窗口，把批次事件真正投递下游（受冷却与静默闸约束）。

        250 条脉冲在窗口内被吸收 → 这里只产出 **1 条**批次事件、
        只唤醒下游 **1 次**。这是"禁止逐条唤醒"的正向断言点。
        """
        require_aware(now, "now")
        now_utc = as_utc(now, "now")
        batches = self.merge_window.flush_all(now_utc)

        dispatched: list[BatchedPulseEvent] = []
        for batch in batches:
            if self.deep_sleep_gate.is_deep_sleep:
                continue  # 深度睡眠：批次也不放行，等晨间解冻
            if self.cooldown.is_cooling(batch.topic_key, now_utc):
                continue
            self.cooldown.record_dispatch(batch.topic_key, now_utc)
            self.dispatched_total += 1
            if batch.motor_feedback_requested:
                self.deep_sleep_gate.record_vibration()
            dispatched.append(batch)
        return tuple(dispatched)

    # ------------------------------------------------------- 晨间解冻

    def thaw_silent_queue(self, now: datetime) -> SilentQueueThawReport:
        """晨间清醒后的第一个安全窗口：解冻静默队列并有序聚合呈现。

        **无损**：进入静默队列的候选一条都不许丢；按主题分组、按时间排序后
        一次性聚合呈现，马达振动按"组"计而不是按条计。
        """
        require_aware(now, "now")
        now_utc = as_utc(now, "now")

        if self.deep_sleep_gate.is_deep_sleep:
            raise RuntimeError(
                "cannot thaw while still in DEEP_SLEEP; exit deep sleep first"
            )

        drained = list(self._silent_queue)
        before = len(drained)
        self._silent_queue.clear()

        groups: dict[str, list[WakeCandidate]] = {}
        for candidate in drained:
            groups.setdefault(candidate.topic_key, []).append(candidate)

        ordered_topics = tuple(
            sorted(
                groups,
                key=lambda k: min(
                    as_utc(c.occurred_at, "occurred_at") for c in groups[k]
                ),
            )
        )

        # 每个主题一次聚合呈现，一次马达反馈
        for topic in ordered_topics:
            self.cooldown.record_dispatch(topic, now_utc)
        self.deep_sleep_gate.record_vibration(max(len(ordered_topics), 0))

        return SilentQueueThawReport(
            thawed_at=now_utc,
            topic_groups=ordered_topics,
            total_candidates=before,
            lost_candidates=0,
            motor_vibrations_used=len(ordered_topics),
        )

    # --------------------------------------------------------- 可观测性

    @property
    def silent_queue_size(self) -> int:
        """当前挂起在静默队列中的候选数（等待晨间解冻）。"""
        return len(self._silent_queue)

    def stats(self) -> dict[str, int]:
        return {
            "dispatched_total": self.dispatched_total,
            "p0_bypass_total": self.p0_bypass_total,
            "cooled_down_total": self.cooled_down_total,
            "absorbed_by_merge_window": self.merge_window.absorbed_total,
            "emitted_batches": self.merge_window.emitted_batches,
            "pending_in_window": self.merge_window.pending_count(),
            "silent_queue_size": self.silent_queue_size,
            "suppressed_by_deep_sleep": self.deep_sleep_gate.suppressed_total,
            "motor_vibrations": self.deep_sleep_gate.motor_vibration_count,
        }
