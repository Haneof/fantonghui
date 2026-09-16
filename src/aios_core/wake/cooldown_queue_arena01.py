"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

实战情境：手环佩戴者处于羽毛球赛后心率剧烈波动（加速度传感器 50Hz 持续
离散脉冲），或处于凌晨 02:00~06:00 深度睡眠阶段。

四大硬门禁的工程落点：

1. **高频防抖与合并窗口**：同一去重键在滚动 ``merge_window_seconds``
   （默认 5s）窗口内的离散脉冲全部聚合为**单条 MergedBatch**——下游心智
   流水线每窗口至多被唤醒 1 次，绝不逐条穿透；
2. **冷却时间硬防护**：非致命一般提醒触发后强制进入 15~30 分钟**自适应**
   冷却期：同键在冷却期内的骚扰被压制（0 马达），压制次数越多冷却越向
   30 分钟自适应延长，手环绝不形成高频骚扰；
3. **DEEP_SLEEP 绝对静默**：判定深睡时，除 ``WakePriority.P0_CRITICAL_SAFETY``
   硬件直穿外，一切一般通知/复盘/任务提醒强制挂入静默队列——**物理马达
   振动次数严格为 0**（本引擎对马达的全部调用带优先级审计计数）；
4. **静默队列无损唤醒延递**：用户清醒并下床（走出睡眠态）的第一个安全
   窗口，静默队列自动解冻，按「时间升序 → 优先级降序」做有序聚合呈现，
   一条不丢、次序不乱。

时钟全部显式注入，与 M0-023/M0-023-V22 的 P0 硬件直穿语义严格同层：
本队列绝不拦截、绝不延迟 P0。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from aios_core.contracts.safety_bypass import WakePriority

__all__ = [
    "SleepStage",
    "VitalPulse",
    "MergedBatch",
    "GeneralNotice",
    "NotifyVerdict",
    "SilentDigest",
    "MotorPort",
    "RecordingMotor",
    "WakeCooldownQueue",
]


class SleepStage:
    """睡眠相位（底层生理判定的最小契约）。"""

    AWAKE = "awake"
    LIGHT_SLEEP = "light_sleep"
    DEEP_SLEEP = "deep_sleep"

    ALL = frozenset({AWAKE, LIGHT_SLEEP, DEEP_SLEEP})


@dataclass(frozen=True)
class VitalPulse:
    """一条离散物理体征脉冲（50Hz 传感器流的最小单元）。"""

    ts: datetime
    kind: str  # heart_rate / hrv / accel / ...
    value: float
    dedupe_key: str
    priority: WakePriority = WakePriority.P3_BACKGROUND_TICK


@dataclass(frozen=True)
class MergedBatch:
    """一个合并窗口密封后的唯一下游唤醒事件。"""

    dedupe_key: str
    window_open: datetime
    window_close: datetime
    pulse_count: int
    unique_count: int  # 精确内容去重后的条数
    min_value: float
    max_value: float
    mean_value: float
    digest: str  # 内容寻址（审计稳定）


@dataclass(frozen=True)
class GeneralNotice:
    """非致命一般提醒（复盘反思 / 任务提醒 / 一般通知）。"""

    ts: datetime
    category: str  # reflection / task_reminder / general
    text: str
    cooldown_key: str  # 同键共享冷却期
    priority: WakePriority = WakePriority.P2_NORMAL_INTERACT


@dataclass(frozen=True)
class NotifyVerdict:
    """一次一般提醒投递裁决（审计可读）。"""

    outcome: str  # delivered / suppressed_cooldown / held_silent
    motor_vibrated: bool
    cooldown_until: Optional[datetime] = None
    silent_backlog: int = 0


@dataclass(frozen=True)
class SilentDigest:
    """静默队列解冻时的有序聚合呈现（门禁 4 的交付形态）。"""

    entries: Tuple[GeneralNotice, ...]  # 时间升序 → 优先级降序
    grouped_counts: Tuple[Tuple[str, int], ...]  # (category, count) 聚合
    total: int
    flushed_at: datetime
    motor_vibrated: bool  # 清醒后允许的一次轻柔提示


class MotorPort(Protocol):
    """物理马达端口（P0 之外的一切振动都被审计计数）。"""

    def vibrate(self, pattern: str) -> None: ...


class RecordingMotor:
    """默认马达实现：只计数不动作（生产替换为真实硬件驱动）。"""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def vibrate(self, pattern: str) -> None:
        self.calls.append(pattern)

    @property
    def count(self) -> int:
        return len(self.calls)


@dataclass
class _WindowAccumulator:
    anchor: datetime
    kind: str
    values: List[Tuple[datetime, float]] = field(default_factory=list)
    seen_digests: set = field(default_factory=set)
    unique_value_reprs: set = field(default_factory=set)


class WakeCooldownQueue:
    """高频唤醒去重合并 + 自适应冷却 + DEEP_SLEEP 静默闸。"""

    def __init__(
        self,
        *,
        motor: Optional[MotorPort] = None,
        merge_window_seconds: int = 5,
        cooldown_base_minutes: int = 15,
        cooldown_max_minutes: int = 30,
        silent_backlog_cap: int = 500,
    ) -> None:
        if not 1 <= merge_window_seconds <= 600:
            raise ValueError("merge_window_seconds must be within 1..600")
        if not 1 <= cooldown_base_minutes <= cooldown_max_minutes:
            raise ValueError("cooldown range must satisfy 1 <= base <= max")
        self._window = merge_window_seconds
        self._cooldown_base = cooldown_base_minutes
        self._cooldown_max = cooldown_max_minutes
        self._backlog_cap = silent_backlog_cap
        self.motor: MotorPort = motor if motor is not None else RecordingMotor()

        self._open_windows: Dict[str, _WindowAccumulator] = {}
        self._cooldown_until: Dict[str, datetime] = {}
        self._suppression_since_delivery: Dict[str, int] = {}
        self._silent_backlog: List[GeneralNotice] = []
        self._sleep_stage = SleepStage.AWAKE
        self._stats: Dict[str, int] = {
            "pulses_ingested": 0,
            "pulses_deduped": 0,
            "batches_sealed": 0,
            "downstream_wakes": 0,
            "general_deliveries": 0,
            "cooldown_suppressions": 0,
            "silent_held": 0,
            "silent_flushed": 0,
            "p0_passthrough": 0,
            "motor_vibrations_total": 0,
        }

    # ------------------------------------------------------------------
    # 门禁 1：高频防抖与合并窗口
    # ------------------------------------------------------------------

    def ingest_pulse(self, pulse: VitalPulse) -> Optional[MergedBatch]:
        """摄入一条离散脉冲：只入窗口，绝不直接唤醒下游。

        返回：若该脉冲越过当前窗口期，旧窗口被立即密封并作为返回值返回
        （去重合并的标准防抖语义：下游每窗严格一次唤醒）。窗口内返回 None。
        """
        if not pulse.dedupe_key.strip() or not pulse.kind.strip():
            raise ValueError("dedupe_key/kind must be non-empty")
        self._stats["pulses_ingested"] += 1
        # 精确重放去重：同键同窗同 (ts, kind, value) 的重复脉冲只算一次。
        content_digest = hashlib.sha1(
            f"{pulse.dedupe_key}|{pulse.ts.isoformat()}|{pulse.kind}|{pulse.value!r}".encode("utf-8")
        ).hexdigest()
        sealed: Optional[MergedBatch] = None
        acc = self._open_windows.get(pulse.dedupe_key)
        if acc is None:
            acc = _WindowAccumulator(anchor=pulse.ts, kind=pulse.kind)
            self._open_windows[pulse.dedupe_key] = acc
        elif pulse.ts >= acc.anchor + timedelta(seconds=self._window):
            # 窗口期已满：先无损密封旧窗口（下游唯一一次唤醒），再开新窗。
            sealed = self._seal_one(pulse.dedupe_key, acc)
            acc = _WindowAccumulator(anchor=pulse.ts, kind=pulse.kind)
            self._open_windows[pulse.dedupe_key] = acc
        if content_digest in acc.seen_digests:
            self._stats["pulses_deduped"] += 1
            return sealed
        acc.seen_digests.add(content_digest)
        acc.unique_value_reprs.add(repr(pulse.value))
        acc.values.append((pulse.ts, pulse.value))
        return sealed

    def seal_finished_windows(self, now: datetime) -> List[MergedBatch]:
        """密封所有已过窗口期的累加器。

        每个密封窗口**只产生一次下游唤醒**（``downstream_wakes += 1``），
        250 条脉冲进来，心智流水线只见 1 条 MergedBatch。
        """
        sealed: List[MergedBatch] = []
        for key in sorted(self._open_windows):
            acc = self._open_windows[key]
            if acc.anchor + timedelta(seconds=self._window) > now:
                continue
            batch = self._seal_one(key, acc)
            sealed.append(batch)
        for batch in sealed:
            del self._open_windows[batch.dedupe_key]
        return sealed

    def _seal_one(self, key: str, acc: _WindowAccumulator) -> MergedBatch:
        if not acc.values:
            raise ValueError("cannot seal an empty window")
        values = [v for _, v in acc.values]
        first_ts = min(t for t, _ in acc.values)
        last_ts = max(t for t, _ in acc.values)
        digest = hashlib.sha256(
            json.dumps(
                {"key": key, "n": len(values), "span": [first_ts.isoformat(), last_ts.isoformat()]},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self._stats["batches_sealed"] += 1
        self._stats["downstream_wakes"] += 1  # 每窗口严格 1 次
        return MergedBatch(
            dedupe_key=key,
            window_open=acc.anchor,
            window_close=acc.anchor + timedelta(seconds=self._window),
            pulse_count=len(acc.values),
            unique_count=len(acc.unique_value_reprs),
            min_value=min(values),
            max_value=max(values),
            mean_value=sum(values) / len(values),
            digest=digest,
        )

    # ------------------------------------------------------------------
    # 门禁 2/3：一般提醒投递（冷却硬防护 + DEEP_SLEEP 静默）
    # ------------------------------------------------------------------

    def set_sleep_stage(self, stage: str) -> None:
        if stage not in SleepStage.ALL:
            raise ValueError(f"unknown sleep stage: {stage!r}")
        self._sleep_stage = stage

    def _vibrate_audited(self, pattern: str) -> None:
        self.motor.vibrate(pattern)
        self._stats["motor_vibrations_total"] += 1

    def notify_general(self, notice: GeneralNotice) -> NotifyVerdict:
        """非致命一般提醒投递裁决。

        优先级：DEEP_SLEEP 静默 > 冷却压制 > 正常投递。
        （P0 生命安全事件请走 :meth:`notify_p0`，绝不进入本方法。）
        """
        if not notice.category.strip() or not notice.cooldown_key.strip():
            raise ValueError("category/cooldown_key must be non-empty")

        if self._sleep_stage == SleepStage.DEEP_SLEEP:
            if len(self._silent_backlog) >= self._backlog_cap:
                raise ValueError("silent backlog cap exceeded: 静默队列有界防线")
            self._silent_backlog.append(notice)
            self._stats["silent_held"] += 1
            return NotifyVerdict(
                outcome="held_silent", motor_vibrated=False, silent_backlog=len(self._silent_backlog)
            )

        cooling = self._cooldown_until.get(notice.cooldown_key)
        if cooling is not None and notice.ts < cooling:
            self._stats["cooldown_suppressions"] += 1
            self._suppression_since_delivery[notice.cooldown_key] = (
                self._suppression_since_delivery.get(notice.cooldown_key, 0) + 1
            )
            return NotifyVerdict(outcome="suppressed_cooldown", motor_vibrated=False, cooldown_until=cooling)

        # 正常投递：马达一次轻柔提示 + 记录自适应冷却。
        self._vibrate_audited("general_soft_pulse")
        suppressed = self._suppression_since_delivery.pop(notice.cooldown_key, 0)
        adaptive_minutes = min(self._cooldown_max, self._cooldown_base + suppressed)
        self._cooldown_until[notice.cooldown_key] = notice.ts + timedelta(minutes=adaptive_minutes)
        self._stats["general_deliveries"] += 1
        return NotifyVerdict(
            outcome="delivered",
            motor_vibrated=True,
            cooldown_until=self._cooldown_until[notice.cooldown_key],
        )

    def notify_p0(self, *, ts: datetime, text: str, hazard: str = "P0") -> Dict[str, Any]:
        """P0 生命安全硬件直穿：深睡/冷却一律让路，立即振动+下行审计。"""
        self._vibrate_audited("p0_emergency_pattern")
        self._stats["p0_passthrough"] += 1
        return {
            "outcome": "p0_passthrough",
            "hazard": hazard,
            "text": text,
            "motor_vibrated": True,
            "sleep_stage_at_entry": self._sleep_stage,
        }

    # ------------------------------------------------------------------
    # 门禁 4：静默队列无损唤醒延递
    # ------------------------------------------------------------------

    def flush_silent_backlog(self, now: datetime, *, motor_pulse: bool = True) -> SilentDigest:
        """清醒下床后的第一个安全窗口：冻结的静默队列有序解冻聚合。

        呈现序：时间升序，同时刻按优先级（P0>P1>P2>P3）降序；类目聚合计数，
        一条不丢。清醒后允许一次性的轻柔马达提示（可选，由调用方决定）。
        """
        if self._sleep_stage == SleepStage.DEEP_SLEEP:
            # 深睡中绝不允许误解冻（物理马达 0 的铁律高于一切）。
            raise ValueError("cannot flush silent backlog during DEEP_SLEEP")

        order = {
            WakePriority.P0_CRITICAL_SAFETY: 0,
            WakePriority.P1_URGENT_TASK: 1,
            WakePriority.P2_NORMAL_INTERACT: 2,
            WakePriority.P3_BACKGROUND_TICK: 3,
        }
        ordered = sorted(self._silent_backlog, key=lambda n: (n.ts, order.get(n.priority, 9)))
        grouped: Dict[str, int] = {}
        for notice in ordered:
            grouped[notice.category] = grouped.get(notice.category, 0) + 1
        flushed = len(ordered)
        self._silent_backlog.clear()
        self._stats["silent_flushed"] += flushed
        vibrated = False
        if motor_pulse and flushed:
            self._vibrate_audited("morning_digest_soft_chime")
            vibrated = True
        return SilentDigest(
            entries=tuple(ordered),
            grouped_counts=tuple(sorted(grouped.items(), key=lambda kv: (-kv[1], kv[0]))),
            total=flushed,
            flushed_at=now,
            motor_vibrated=vibrated,
        )

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    @property
    def sleep_stage(self) -> str:
        return self._sleep_stage

    def silent_backlog_size(self) -> int:
        return len(self._silent_backlog)

    def cooldown_remaining_seconds(self, key: str, now: datetime) -> float:
        until = self._cooldown_until.get(key)
        if until is None or now >= until:
            return 0.0
        return (until - now).total_seconds()
