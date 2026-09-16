"""M2-001 高频唤醒去重合并队列与 DEEP_SLEEP 绝对静默闸。

宪法锚：§11 分寸感 / 老大五铁律 3（P0 硬旁路 ±50ms、世界模型让路）。

四大硬门禁的结构性落实：

1. 【防抖合并窗】同一样式 kind 在 MERGE_WINDOW_SECONDS 内涌入的离散脉冲
   一律聚合成单条 BatchEmission——下游心智流水线每窗至多被唤一次；
   逐条唤醒的路径在本类不存在。
2. 【冷却硬防护】kind 交付后进入自适应冷却 [15min, 30min]：基线 15min，
   冷却期内每被压下一批 +5min，封顶 30min（确定性阶梯，可复放）。
3. 【DEEP_SLEEP 绝对静默】深睡相内除 P0 外的事件全部无损挂起：
   马达计数结构性为 0——非 P0 事件根本到不了 vibrate() 的调用点；
   P0 生命安全事件无视睡眠相直穿（硬件通路语义：马达+即时发射）。
4. 【无损唤醒延递】脱离睡眠相的第一个安全窗（on_user_wake）一次性
   有序聚合呈现：严格按 occurred_at 排序、一条不丢、一次唤一次达。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

MERGE_WINDOW_SECONDS = 5
COOLDOWN_BASE_SECONDS = 900        # 15 min 基线
COOLDOWN_STEP_SECONDS = 300        # 每压一批 +5 min
COOLDOWN_MAX_SECONDS = 1800        # 30 min 封顶


class WakePriority(str, Enum):
    P0_CRITICAL_SAFETY = "P0_CRITICAL_SAFETY"  # 心梗/跌倒/SOS：硬件直穿
    NORMAL = "NORMAL"


class SleepPhase(str, Enum):
    AWAKE = "AWAKE"
    LIGHT_SLEEP = "LIGHT_SLEEP"
    DEEP_SLEEP = "DEEP_SLEEP"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass(slots=True, frozen=True)
class WakeEvent:
    event_id: str
    kind: str                    # 合并键：同源同型事件一个 family
    priority: WakePriority
    payload: tuple = ()
    occurred_at: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.occurred_at is None:
            raise ValueError("occurred_at 必填（唤醒纪律以发生时刻为准，不以到达时刻）")
        object.__setattr__(self, "occurred_at", _aware(self.occurred_at))
        if not self.event_id or not self.kind:
            raise ValueError("event_id/kind 不得为空")


@dataclass(slots=True, frozen=True)
class BatchEmission:
    """一次下游唤醒：单批次、单马达语义（merged_count 记被合并的脉冲数）。"""

    kind: str
    merged_count: int
    first_occurred_at: datetime
    last_occurred_at: datetime
    event_ids: tuple[str, ...]
    deferred: bool = False        # 晨间延递聚合件标记
    kinds: tuple[str, ...] = ()   # 延递聚合时覆盖的全部 kind


class CountingMotorPort:
    """物理马达口（sim 形态）：唯一职责是被调用即计数——0 就是 0。"""

    def __init__(self) -> None:
        self.vibrations = 0

    def vibrate(self) -> None:
        self.vibrations += 1


class WakeCooldownQueue:
    """高频唤醒的防抖、冷却、深睡静默与晨间延递队列。

    交付通道：``drain_emissions``（下游只在这里取件）；马达通道：motor 端口。
    在本类的全部代码路径里，NORMAL 事件永远不会调用 motor.vibrate()——
    振动语义当前仅属于 P0 直穿件（与老大铁律 3 的硬件通路对位）。
    """

    def __init__(self, *, motor: CountingMotorPort | None = None) -> None:
        self.motor = motor or CountingMotorPort()
        self._sleep_phase = SleepPhase.AWAKE
        self._merge_buffer: dict[str, list[WakeEvent]] = {}
        self._window_open_at: dict[str, datetime] = {}
        self._suspended: list[WakeEvent] = []
        self._seen_ids: set[str] = set()
        self._emissions: list[BatchEmission] = []
        self._cooling: dict[str, list[WakeEvent]] = {}
        self._last_delivered: dict[str, datetime] = {}
        self._cooldown_seconds: dict[str, float] = {}
        self._suppressed_batches = 0

    # ------------------------------ 输入 --------------------------------

    def set_sleep_phase(self, phase: SleepPhase) -> None:
        self._sleep_phase = phase

    def ingest(self, event: WakeEvent, now: datetime) -> None:
        if event.event_id in self._seen_ids:      # 幂等：重复投递不产生第二条
            return
        self._seen_ids.add(event.event_id)
        now = _aware(now)
        occurred = _aware(event.occurred_at)

        # P0 生命安全：无视睡眠相/冷却期，硬件直穿（马达 + 即时发射）
        if event.priority is WakePriority.P0_CRITICAL_SAFETY:
            self.motor.vibrate()
            self._emissions.append(BatchEmission(
                kind=event.kind, merged_count=1,
                first_occurred_at=occurred, last_occurred_at=occurred,
                event_ids=(event.event_id,),
            ))
            return

        # DEEP_SLEEP 绝对静默：无损挂起，马达计数结构性不动
        if self._sleep_phase is SleepPhase.DEEP_SLEEP:
            self._suspended.append(event)
            return

        buf = self._merge_buffer.setdefault(event.kind, [])
        if not buf:
            self._window_open_at[event.kind] = now
        buf.append(event)

    # ------------------------------ 交付 --------------------------------

    def flush(self, now: datetime) -> None:
        """闭窗批次过冷却闸：否决不丢件，事件退入冷却缓冲与下一窗合流交付。"""
        now = _aware(now)
        for kind in sorted(self._merge_buffer):
            opened = self._window_open_at[kind]
            if (now - opened).total_seconds() < MERGE_WINDOW_SECONDS:
                continue  # 窗未闭
            events = self._merge_buffer.pop(kind)
            self._window_open_at.pop(kind, None)
            self._cooling.setdefault(kind, []).extend(events)
        for kind in sorted(self._cooling):
            if not self._cooling[kind]:
                continue
            if not self._cooldown_allows(kind, now):
                self._suppressed_batches += 1
                self._bump_cooldown(kind)
                continue  # 否决不丢：事件留在冷却缓冲，等下一个允许窗
            self._deliver(kind, self._cooling.pop(kind), now)

    def _deliver(self, kind: str, events: list[WakeEvent], now: datetime) -> None:
        ordered = sorted(events, key=lambda e: (e.occurred_at, e.event_id))
        self._emissions.append(BatchEmission(
            kind=kind, merged_count=len(ordered),
            first_occurred_at=ordered[0].occurred_at,
            last_occurred_at=ordered[-1].occurred_at,
            event_ids=tuple(e.event_id for e in ordered),
        ))
        self._last_delivered[kind] = now
        self._cooldown_seconds[kind] = COOLDOWN_BASE_SECONDS

    def _cooldown_allows(self, kind: str, now: datetime) -> bool:
        last = self._last_delivered.get(kind)
        if last is None:
            return True
        cd = self._cooldown_seconds.get(kind, COOLDOWN_BASE_SECONDS)
        return (_aware(now) - last).total_seconds() >= cd

    def _bump_cooldown(self, kind: str) -> None:
        cd = self._cooldown_seconds.get(kind, COOLDOWN_BASE_SECONDS)
        self._cooldown_seconds[kind] = min(cd + COOLDOWN_STEP_SECONDS, COOLDOWN_MAX_SECONDS)

    # ------------------------------ 晨间延递 -----------------------------

    def on_user_wake(self, now: datetime) -> None:
        """第一安全窗：静默队列 + 合并/冷却未发件，一次性有序聚合呈现（无损）。"""
        now = _aware(now)
        self._sleep_phase = SleepPhase.AWAKE
        pending = list(self._suspended)
        self._suspended = []
        for kind in sorted(self._merge_buffer):
            pending.extend(self._merge_buffer.pop(kind))
        self._window_open_at.clear()
        for kind in sorted(self._cooling):
            pending.extend(self._cooling.pop(kind))
        if not pending:
            return
        ordered = sorted(pending, key=lambda e: (e.occurred_at, e.event_id))
        kinds = tuple(sorted({e.kind for e in ordered}))
        self._emissions.append(BatchEmission(
            kind="__morning_aggregate__", merged_count=len(ordered),
            first_occurred_at=ordered[0].occurred_at,
            last_occurred_at=ordered[-1].occurred_at,
            event_ids=tuple(e.event_id for e in ordered),
            deferred=True, kinds=kinds,
        ))
        for kind in kinds:
            self._last_delivered[kind] = now
            self._cooldown_seconds[kind] = COOLDOWN_BASE_SECONDS

    # ------------------------------ 观测面 -------------------------------

    def drain_emissions(self) -> list[BatchEmission]:
        out, self._emissions = self._emissions, []
        return out

    @property
    def suppressed_batches(self) -> int:
        return self._suppressed_batches

    @property
    def suspended_count(self) -> int:
        return len(self._suspended)

    def cooldown_of(self, kind: str) -> float:
        return self._cooldown_seconds.get(kind, COOLDOWN_BASE_SECONDS)


__all__ = [
    "BatchEmission",
    "COOLDOWN_BASE_SECONDS",
    "COOLDOWN_MAX_SECONDS",
    "COOLDOWN_STEP_SECONDS",
    "CountingMotorPort",
    "MERGE_WINDOW_SECONDS",
    "SleepPhase",
    "WakeCooldownQueue",
    "WakeEvent",
    "WakePriority",
]
