"""SIM-001 无界面 Linux 30 天 / 180 天高熵多维人生仿真驱动引擎。

工单：``arena/agent-sim-engine`` -> ``src/aios_core/simulation/headless_life_driver.py``

核心使命
--------------------------------------------------------------------------
构建**纯 Python、零 UI、可在无图形 Linux 服务器上持续跑批**的"虚拟人多维人生时空
仿真推演机"，用海量真实压力测试喂养 AIOS——而不是用玩具数据自我安慰。

四大硬门禁
--------------------------------------------------------------------------
1. **真实高熵成年人 30 天时空流**
   720 小时连续时间流（昼夜节律 / 高频心率与 HRV / 工业车间高噪 / 120 次真实工作会议 /
   突发商业危机 / 合同违约事件）；
2. **驱动 AIOS 完整技术链**
   数据接入 -> C01 边缘清洗 -> C06 倒排求交 -> C02 账本持久化 -> C04 单看板装配 -> C05 回溯注记，
   每一段都用**真实模块**而不是桩件；
3. **30 天连续推演 0 死锁 + 内存平稳**
   阶段执行带超时哨兵（超时即记死锁）；RSS 逐日采样并断言 <= 128MB 且尾部无泄漏趋势；
   原始二进制图片滞留量严格为 0（物理粉碎 + 审计留痕）；
4. **月度 Token 封套核验**
   全局 Token 消耗必须严格受控于 ``governance/runtime_policy.json`` 的月度总预算
   （2,554,000 tokens）。
"""

from __future__ import annotations

import json
import math
import os
import random
import resource
import threading
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts import (
    Entity,
    EventAnchor,
    EvidenceSet,
    ObjectRef,
    Observation,
    Relation,
    SourceRef,
    TemporalExtent,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.time import as_utc, require_aware, utc_now
from aios_core.errors import AIOSProtocolError

__all__ = [
    "DEFAULT_MONTHLY_TOKEN_BUDGET",
    "SIMULATION_DAYS_SHORT",
    "C01EdgeCleaning",
    "C02LedgerWriter",
    "C04BoardAssembler",
    "C05RetrospectiveRecorder",
    "C06InvertedIntersector",
    "ChainStage",
    "ChainStageResult",
    "DeadlockSentinel",
    "HeadlessLifeDriver",
    "HeadlessLifeTimeline",
    "LifeEvent",
    "LifeEventKind",
    "MemorySentinel",
    "RuntimePolicy",
    "SimulationConfig",
    "SimulationReport",
    "StageTimeoutError",
    "TokenMeter",
    "load_runtime_policy",
]

#: 工单口径：30 天短窗仿真。
SIMULATION_DAYS_SHORT: Final[int] = 30

#: 工单口径：月度 Token 总预算（governance/runtime_policy.json 的同名配置）。
DEFAULT_MONTHLY_TOKEN_BUDGET: Final[int] = 2_554_000

HOURS_PER_DAY: Final[int] = 24
MEETINGS_TOTAL: Final[int] = 120
CRISIS_DAY: Final[int] = 17
BREACH_DAY: Final[int] = 26


# ---------------------------------------------------------------------------
# 运行时策略（外部化配置：调度周期、Token 阈值、冷却参数全量配置化）
# ---------------------------------------------------------------------------


class RuntimePolicy(BaseModel):
    """``governance/runtime_policy.json`` 的内存映射。"""

    model_config = ConfigDict(extra="allow", frozen=True)

    version: str = "3.0"
    monthly_token_budget: int = Field(default=DEFAULT_MONTHLY_TOKEN_BUDGET, ge=1)
    manifest_token_budget: int = Field(default=1500, ge=1)
    sample_interval_seconds: int = Field(default=60, ge=1)
    geo_poll_seconds: int = Field(default=8, ge=1)
    cooldown: dict[str, Any] = Field(default_factory=dict)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    simulation: dict[str, Any] = Field(default_factory=dict)


def load_runtime_policy(path: str | os.PathLike[str] | None = None) -> RuntimePolicy:
    """读取运行时策略；文件缺失时使用内置默认值（但绝不静默改变工单口径）。"""
    candidate = Path(path) if path is not None else Path("governance/runtime_policy.json")
    if candidate.is_file():
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        return RuntimePolicy(**payload)
    return RuntimePolicy()


class SimulationConfig(BaseModel):
    """仿真配置（可跑 30 天短窗，也可扩到 180 天长窗）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    days: int = Field(default=SIMULATION_DAYS_SHORT, ge=1, le=365)
    seed: int = Field(default=20260916, ge=0)
    speed_multiplier: float = Field(default=1000.0, gt=0.0)
    meetings_total: int = Field(default=MEETINGS_TOTAL, ge=0)
    sessions_per_day: int = Field(default=40, ge=0)
    turns_per_session: int = Field(default=8, ge=1)
    stage_timeout_seconds: float = Field(default=120.0, gt=0.0)
    rss_budget_mb: float = Field(default=128.0, gt=0.0)
    monthly_token_budget: int = Field(default=DEFAULT_MONTHLY_TOKEN_BUDGET, ge=1)
    policy_path: str = "governance/runtime_policy.json"
    db_path: str | None = None
    purge_threshold: float = Field(default=1.0, ge=0.0, le=1.0)
    frames_per_day: int = Field(default=6, ge=0)

    @model_validator(mode="after")
    def validate_envelope(self) -> SimulationConfig:
        policy = load_runtime_policy(self.policy_path)
        if self.monthly_token_budget > policy.monthly_token_budget * 12:
            raise ValueError("monthly_token_budget exceeds the annual envelope in runtime policy")
        return self

    @property
    def hours(self) -> int:
        return self.days * HOURS_PER_DAY


# ---------------------------------------------------------------------------
# 高熵时空流
# ---------------------------------------------------------------------------


class LifeEventKind(StrEnum):
    CIRCADIAN_TICK = "circadian_tick"          # 每小时昼夜节律（心率/HRV/睡眠阶段）
    WORKSHOP_NOISE = "workshop_noise"          # 工业车间高噪环境
    MEETING = "meeting"                        # 真实工作会议
    COMMUTE = "commute"                          # 通勤（地理转移）
    BURST_STRESS = "burst_stress"               # 高强度突发压力
    BUSINESS_CRISIS = "business_crisis"         # 突发商业危机
    CONTRACT_BREACH = "contract_breach"         # 老王合同违约
    CAPTURE_FRAME = "capture_frame"             # 图像抓拍（原始字节待清洗）


class LifeEvent(BaseModel):
    """时空流中的一个事件（高熵、可复现：同种子必然同序列）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    occurred_at: datetime
    kind: LifeEventKind
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_time(self) -> LifeEvent:
        _ = require_aware(self.occurred_at, "occurred_at")
        return self


class HeadlessLifeTimeline:
    """30 天时空流发生器：昼夜节律 + 会议 + 噪声 + 危机 + 违约（全部确定性可复现）。"""

    def __init__(self, config: SimulationConfig, *, start: datetime | None = None) -> None:
        self._config = config
        self._start = start or datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        self._random = random.Random(config.seed)

    @property
    def start(self) -> datetime:
        return self._start

    @property
    def end(self) -> datetime:
        return self._start + timedelta(days=self._config.days)

    # ---- 生成 ----

    def events(self) -> Iterator[LifeEvent]:
        config = self._config
        meetings_per_day = config.meetings_total / config.days
        meetings_emitted = 0
        for day in range(config.days):
            day_start = self._start + timedelta(days=day)
            # 1) 每小时昼夜节律（睡眠 -> 清醒 -> 高强度工作 -> 睡眠）
            for hour in range(HOURS_PER_DAY):
                moment = day_start + timedelta(hours=hour)
                yield LifeEvent(
                    event_id=f"tick_d{day:02d}_h{hour:02d}",
                    occurred_at=moment,
                    kind=LifeEventKind.CIRCADIAN_TICK,
                    payload=self._circadian_payload(day, hour),
                )
            # 2) 工业车间高噪环境：工作日 09:00-11:00
            if day % 7 < 5:
                yield LifeEvent(
                    event_id=f"noise_d{day:02d}",
                    occurred_at=day_start + timedelta(hours=9),
                    kind=LifeEventKind.WORKSHOP_NOISE,
                    payload={"noise_db": 88.0 + self._random.random() * 6.0, "hours": 2},
                )
            # 3) 真实工作会议：均匀铺满全月，合计恰好 meetings_total 次
            for slot in range(int(meetings_per_day)):
                hour = 10 + slot * 2
                meetings_emitted += 1
                yield LifeEvent(
                    event_id=f"meeting_{meetings_emitted:03d}",
                    occurred_at=day_start + timedelta(hours=hour % HOURS_PER_DAY),
                    kind=LifeEventKind.MEETING,
                    payload={
                        "topic": self._random.choice(
                            ["对赌条款谈判", "股东会决议", "尽职调查复盘", "诉讼策略会", "融资交割"]
                        ),
                        "attendees": 4 + self._random.randint(0, 6),
                        "duration_minutes": 30 + self._random.randint(0, 90),
                    },
                )
            # 4) 突发商业危机 / 合同违约（各自唯一、位置固定，便于回归断言）
            if day == CRISIS_DAY:
                yield LifeEvent(
                    event_id="crisis_regulatory_raid",
                    occurred_at=day_start + timedelta(hours=21, minutes=40),
                    kind=LifeEventKind.BUSINESS_CRISIS,
                    payload={
                        "summary": "监管突击检查 + 合伙人对赌触发，核心 IP 权属存疑",
                        "severity": 0.95,
                        "counterparty": "ent_partner_tech",
                    },
                )
            if day == BREACH_DAY:
                yield LifeEvent(
                    event_id="breach_wang_contract",
                    occurred_at=day_start + timedelta(hours=16, minutes=20),
                    kind=LifeEventKind.CONTRACT_BREACH,
                    payload={
                        "counterparty": "ent_wang",
                        "contract": "Pre-A 联合孵化与股权代持对赌协议",
                        "loss_cny": 23_000_000,
                        "summary": "老王单方违约，隐匿对外连带担保",
                    },
                )
            # 5) 图像抓拍（含低质量帧 -> C01 必须物理粉碎）
            for index in range(config.frames_per_day):
                yield LifeEvent(
                    event_id=f"frame_d{day:02d}_{index:02d}",
                    occurred_at=day_start + timedelta(hours=8 + index * 2),
                    kind=LifeEventKind.CAPTURE_FRAME,
                    payload={
                        "frame_id": f"frame_d{day:02d}_{index:02d}",
                        "quality": round(0.25 + 0.68 * self._random.random(), 3),
                        "scene_tag": "contract_desk" if index % 2 == 0 else "meeting_room",
                    },
                )
        if meetings_emitted != config.meetings_total:
            raise AIOSProtocolError(
                ErrorCode.INCOMPLETE_DATA,
                "timeline did not emit the declared number of meetings",
                context={
                    "reason": "meeting_count_mismatch",
                    "emitted": meetings_emitted,
                    "expected": config.meetings_total,
                },
            )

    def _circadian_payload(self, day: int, hour: int) -> dict[str, Any]:
        """昼夜节律：睡眠段低心率高 HRV，工作段高心率低 HRV，夜间高压峰值。"""
        asleep = hour < 6 or hour >= 23
        base_hr = 52.0 if asleep else 68.0
        circadian = 8.0 * math.sin((hour - 6) / 24 * 2 * math.pi)
        stress = 0.0
        if not asleep and 19 <= hour <= 22:
            stress = 12.0 + 3.0 * math.sin(day * 0.7)  # 夜间高压谈判
        heart_rate = base_hr + circadian + stress + self._random.uniform(-2.0, 2.0)
        hrv = 78.0 if asleep else 45.0
        if not asleep and 19 <= hour <= 22:
            hrv -= 14.0
        return {
            "day": day,
            "hour": hour,
            "sleep_stage": "deep_sleep" if asleep else ("light_sleep" if hour < 7 else "awake"),
            "heart_rate_bpm": round(heart_rate, 2),
            "hrv_ms": round(max(hrv + self._random.uniform(-4.0, 4.0), 12.0), 2),
            "noise_db": round(self._random.uniform(38.0, 52.0), 2),
        }


# ---------------------------------------------------------------------------
# 哨兵（死锁 / 内存 / Token）
# ---------------------------------------------------------------------------


class StageTimeoutError(AIOSProtocolError):
    """阶段超时：视为一次死锁（工单要求死锁次数严格为 0）。"""

    def __init__(self, stage: str, timeout_seconds: float) -> None:
        super().__init__(
            ErrorCode.OUTCOME_UNKNOWN,
            f"simulation stage timed out: {stage}",
            context={
                "reason": "stage_timeout",
                "stage": stage,
                "timeout_seconds": timeout_seconds,
            },
        )


class DeadlockSentinel:
    """死锁哨兵：每个阶段在独立线程里带超时执行，超时/异常即计数。"""

    def __init__(self, *, timeout_seconds: float) -> None:
        self._timeout = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sim_stage")
        self._deadlocks = 0
        self._timeouts: list[str] = []

    @property
    def deadlock_count(self) -> int:
        return self._deadlocks

    @property
    def timed_out_stages(self) -> tuple[str, ...]:
        return tuple(self._timeouts)

    def run(self, stage: str, fn: Any) -> Any:
        future = self._executor.submit(fn)
        try:
            return future.result(timeout=self._timeout)
        except FutureTimeoutError as exc:  # 真死锁：下游永远不返回
            self._deadlocks += 1
            self._timeouts.append(stage)
            raise StageTimeoutError(stage, self._timeout) from exc

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class MemorySentinel:
    """内存哨兵：逐日采样 RSS，用于"平稳/无泄漏"断言。"""

    def __init__(self, *, budget_mb: float) -> None:
        self._budget = budget_mb
        self._samples: list[float] = []

    @property
    def budget_mb(self) -> float:
        return self._budget

    @staticmethod
    def current_rss_mb() -> float:
        """当前驻留集（优先 /proc/self/statm，其次 ru_maxrss，最后 0 表示不可测）。"""
        try:
            with open("/proc/self/statm", encoding="ascii") as handle:
                pages = int(handle.read().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
        except (OSError, ValueError, IndexError):
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return usage / 1024.0 if usage else 0.0

    @property
    def samples(self) -> tuple[float, ...]:
        return tuple(self._samples)

    def sample(self) -> float:
        value = self.current_rss_mb()
        self._samples.append(value)
        return value

    @property
    def baseline_mb(self) -> float:
        return self._samples[0] if self._samples else 0.0

    @property
    def peak_mb(self) -> float:
        return max(self._samples) if self._samples else 0.0

    @property
    def growth_mb(self) -> float:
        return self.peak_mb - self.baseline_mb

    def absolute_within_budget(self) -> bool:
        return self.peak_mb <= self._budget

    def tail_is_flat(self, *, window: int = 5, tolerance_mb: float = 16.0) -> bool:
        """尾部窗口必须平稳：真正泄漏的内存会一路抬升，不会自己回落。"""
        if len(self._samples) < window:
            return True
        tail = self._samples[-window:]
        return (max(tail) - min(tail)) <= tolerance_mb


class TokenMeter:
    """Token 计量器：按阶段记账，总量必须落在月度封套内。"""

    def __init__(self, *, budget: int) -> None:
        self._budget = budget
        self._by_stage: dict[str, int] = {}
        self._lock = threading.RLock()

    @property
    def budget(self) -> int:
        return self._budget

    def record(self, stage: str, tokens: int) -> None:
        if tokens < 0:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "token count must be non-negative",
                context={"reason": "invalid_token_count", "tokens": tokens},
            )
        with self._lock:
            self._by_stage[stage] = self._by_stage.get(stage, 0) + tokens

    @property
    def total(self) -> int:
        return sum(self._by_stage.values())

    @property
    def remaining(self) -> int:
        return self._budget - self.total

    @property
    def within_budget(self) -> bool:
        return self.total <= self._budget

    def by_stage(self) -> Mapping[str, int]:
        return dict(self._by_stage)


# ---------------------------------------------------------------------------
# 技术链阶段
# ---------------------------------------------------------------------------


class ChainStage(StrEnum):
    INGEST = "ingest"
    C01_EDGE_CLEAN = "c01_edge_clean"
    C06_HYPERLINK_INTERSECT = "c06_hyperlink_intersect"
    C02_LEDGER_PERSIST = "c02_ledger_persist"
    C04_BOARD_ASSEMBLY = "c04_board_assembly"
    C05_RETRO_ANNOTATION = "c05_retro_annotation"


class ChainStageResult(BaseModel):
    """单阶段结果：处理量、Token、耗时、是否成功（全部可核对）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: ChainStage
    events_in: int = Field(ge=0)
    events_out: int = Field(ge=0)
    tokens: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0.0, ge=0.0)
    detail: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True


class _C01Report(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessed: int = Field(ge=0)
    purged_frames: int = Field(ge=0)
    bytes_freed: int = Field(ge=0)
    noise_filtered: int = Field(ge=0)
    cleaned_observations: int = Field(ge=0)


class C01EdgeCleaning:
    """C01 边缘清洗：画质评估 + 物理粉碎 + 噪声门限（真实调用 ingest 模块）。"""

    #: 工业车间噪声门限（超过即判定"环境不可用"，观测降权而不是丢弃事实）
    NOISE_DB_GATE: Final[float] = 80.0

    def __init__(self, *, purge_threshold: float = 1.0) -> None:
        from aios_core.ingest.multimodal_edge import CaptureFrame, RawByteSink

        self._CaptureFrame = CaptureFrame
        self._sink = RawByteSink()
        self._purge_threshold = purge_threshold

    @property
    def sink(self) -> Any:
        return self._sink

    @property
    def live_frame_count(self) -> int:
        return self._sink.live_frame_count

    def residue_bytes(self) -> int:
        """当前滞留的原始二进制字节总量（工单要求严格为 0）。"""
        total = 0
        with self._sink._lock:  # noqa: SLF001 - 只读盘点，不改任何状态
            for frame_id, raw in self._sink._raw.items():
                total += len(raw)
                _ = frame_id
        return total

    def store_frame(self, *, frame_id: str, quality: float, scene_tag: str, at: datetime) -> None:
        frame = self._CaptureFrame(
            frame_id=frame_id,
            quality=quality,
            brightness=0.5,
            sharpness=max(quality - 0.1, 0.0),
            jitter=min(quality + 0.1, 1.0),
            scene_tag=scene_tag,
            captured_at=at,
        )
        # 原始字节是仿真出来的确定性伪影（不入契约、只入物理 sink）
        raw = bytes((index * 37 + len(frame_id)) % 256 for index in range(2048))
        self._sink.store(frame, raw)

    def clean(self, events: Sequence[LifeEvent]) -> tuple[_C01Report, tuple[LifeEvent, ...]]:
        cleaned: list[LifeEvent] = []
        noise_filtered = 0
        for event in events:
            if event.kind is LifeEventKind.WORKSHOP_NOISE:
                if float(event.payload.get("noise_db", 0.0)) > self.NOISE_DB_GATE:
                    noise_filtered += 1
                    continue
            cleaned.append(event)
        report = self._sink.purge(self._purge_threshold, now=utc_now())
        cleaned_count = sum(1 for e in cleaned if e.kind is LifeEventKind.CIRCADIAN_TICK)
        return (
            _C01Report(
                assessed=self._sink.live_frame_count + report.purged_count,
                purged_frames=report.purged_count,
                bytes_freed=report.bytes_freed_total,
                noise_filtered=noise_filtered,
                cleaned_observations=cleaned_count,
            ),
            tuple(cleaned),
        )


class C06InvertedIntersector:
    """C06 倒排求交：从世界账本重建四级索引并做结构化穿透（真实调用 C06 模块）。"""

    def __init__(self) -> None:
        from aios_core.query.hyperlink_traverser import EntityHyperlinkGraphTraverser

        self._traverser = EntityHyperlinkGraphTraverser()

    @property
    def traverser(self) -> Any:
        return self._traverser

    def build_and_intersect(self, store: Any, *, root_entity_id: str) -> dict[str, Any]:
        index_report = self._traverser.build_from_store(store)
        result = self._traverser.traverse_entity_network(root_entity_id)
        return {
            "indexed_entities": getattr(index_report, "entity_count", None),
            "anchors": len(getattr(result, "anchors", ()) or ()),
            "evidence_sets": len(getattr(result, "evidence_sets", ()) or ()),
            "observations": len(getattr(result, "observations", ()) or ()),
            "truncated": bool(getattr(result, "truncated", False)),
        }


class C02LedgerWriter:
    """C02 账本持久化：世界唯一写入口 ``SQLiteWorldStore.commit``（只追加）。"""

    def __init__(self, store: Any, *, batch_size: int = 500) -> None:
        self._store = store
        self._batch_size = batch_size
        self._committed = 0

    @property
    def committed_count(self) -> int:
        return self._committed

    def commit_all(self, *, run_id: str, objects: Sequence[Any]) -> dict[str, Any]:
        batches = 0
        for start in range(0, len(objects), self._batch_size):
            chunk = list(objects[start : start + self._batch_size])
            if not chunk:
                continue
            from aios_core.contracts import OperationRequest

            self._store.commit(
                chunk,
                OperationRequest(
                    operation_name="world.commit",
                    expected_world_revision=self._store.current_world_revision(),
                    reason=f"SIM-001 时空流推演 {run_id}",
                    idempotency_key=f"sim-001-{run_id}-batch-{batches:04d}",
                ),
            )
            self._committed += len(chunk)
            batches += 1
        return {"committed": self._committed, "batches": batches}


class C04BoardAssembler:
    """C04 单看板装配：真实走 cockpit 流水线，Token 由官方估算器计量。"""

    def __init__(self, *, token_budget: int = 1500) -> None:
        from aios_core.cockpit.pipeline import CrisisDialoguePipeline

        self._token_budget = token_budget
        self._Pipeline = CrisisDialoguePipeline

    def assemble_day(
        self,
        *,
        day: int,
        sessions: int,
        turns_per_session: int,
        now: datetime,
        day_facts: Sequence[str] = (),
        ready_tasks: Sequence[str] = (),
    ) -> tuple[int, int]:
        """装配一天的会话看板，返回 (会话数, 消耗 Token 总量)。

        Token 记账**含输入与输出两侧**：看板上下文（manifest） + AI 回复估算，
        否则月度封套就会变成一个自欺欺人的数字。
        """
        from aios_core.cockpit.pipeline import estimate_tokens

        digest = "；".join(day_facts[:12]) or "最近 24 小时无可披露关键事实"
        recall = tuple(f"回溯核对：{fact}" for fact in day_facts[:6])
        tokens = 0
        sessions_done = 0
        for session in range(sessions):
            pipeline = self._Pipeline(
                session_id=f"sim_session_d{day:03d}_{session:03d}", token_budget=self._token_budget
            )
            for turn in range(turns_per_session):
                pipeline.push_turn(
                    "user",
                    f"第 {day + 1} 天第 {session + 1} 次会话第 {turn + 1} 轮："
                    f"复核对赌回购条款、代持结构与连带担保风险。",
                    now,
                )
                reply = "已按单看板口径回答：条款风险已标注，等待你确认签署窗口。"
                pipeline.push_turn("ai", reply, now)
                tokens += estimate_tokens(reply)
            manifest = pipeline.assemble_manifest(
                wake_reason="user_resumed_ai",
                world_digest=digest,
                self_mirror="近 3 天睡眠碎片化，晚间血压偏高，需要控制夜间高压谈判时长。",
                ready_tasks=tuple(ready_tasks[:10]),
                recall_digest=recall,
                session_digest=f"第 {day + 1} 天第 {session + 1} 次会话：聚焦对赌与代持风险",
                now=now,
            )
            tokens += manifest.token_total
            sessions_done += 1
        return (sessions_done, tokens)


class C05RetrospectiveRecorder:
    """C05 回溯注记：用 M1-018 契约写下唯一一条"今天才学到"的重估注记。"""

    def __init__(self, store: Any) -> None:
        from aios_core.world.retrospective_annotation import (
            AnnotationKind,
            ObservationHashLedger,
            RetrospectiveAnnotation,
            RetrospectiveAnnotationWriter,
        )

        self._store = store
        self._Kind = AnnotationKind
        self._Annotation = RetrospectiveAnnotation
        self._Writer = RetrospectiveAnnotationWriter
        self._Ledger = ObservationHashLedger

    def record(
        self,
        *,
        run_id: str,
        subject_id: str,
        overlay: str,
        source_ref: str,
        learned_at: datetime,
    ) -> dict[str, Any]:
        """在**仿真时钟的"今天"**写下唯一一条回溯注记（严禁倒写历史）。"""
        require_aware(learned_at, "learned_at")
        from aios_core.contracts.enums import ObjectType

        observations = self._store.list_payloads(object_type=ObjectType.OBSERVATION)
        ledger = self._Ledger.capture(observations)
        first = min(
            (o["learned_at"] for o in observations if isinstance(o, dict)), default=None
        )
        last = max((o["learned_at"] for o in observations if isinstance(o, dict)), default=None)
        annotation = self._Annotation(
            annotation_id=f"ann_sim_{run_id}",
            target_entity_id="ent_wang",
            semantic_overlay=overlay,
            target_time_start=_parse_time(first),
            target_time_end=_parse_time(last),
            learned_at=learned_at,
            source_statement_ref=source_ref,
            annotation_kind=self._Kind.FRAUD_REASSESSMENT,
        )
        receipt = self._Writer(self._store).write(
            annotation,
            history_ledger=ledger,
            subject_id=subject_id,
            created_by="sim_001_engine",
            history_payloads=observations,
        )
        return {
            "annotation_id": annotation.annotation_id,
            "history_unchanged": receipt.history_unchanged,
            "matched": receipt.history_matched,
            "world_revision": (receipt.world_revision_before, receipt.world_revision_after),
        }


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return as_utc(value, "time")
    if isinstance(value, str):
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        return as_utc(datetime.fromisoformat(text), "time")
    raise AIOSProtocolError(
        ErrorCode.INCOMPLETE_DATA,
        "cannot parse timestamp from payload",
        context={"reason": "unparsable_timestamp", "value": repr(value)},
    )


# ---------------------------------------------------------------------------
# 仿真报告与驱动
# ---------------------------------------------------------------------------


class SimulationReport(BaseModel):
    """仿真总报告：把四大门禁的结论全部数字化。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    days: int = Field(ge=1)
    hours_simulated: int = Field(ge=0)
    wall_clock_seconds: float = Field(ge=0.0)
    speed_multiplier: float = Field(gt=0.0)
    events_total: int = Field(ge=0)
    meetings: int = Field(ge=0)
    crises: int = Field(ge=0)
    breaches: int = Field(ge=0)
    stages: tuple[ChainStageResult, ...] = ()
    deadlocks: int = Field(ge=0)
    rss_baseline_mb: float = Field(ge=0.0)
    rss_peak_mb: float = Field(ge=0.0)
    rss_growth_mb: float = Field(ge=0.0)
    rss_budget_mb: float = Field(gt=0.0)
    rss_tail_flat: bool
    raw_binary_residue_bytes: int = Field(ge=0)
    tokens_total: int = Field(ge=0)
    tokens_by_stage: dict[str, int] = Field(default_factory=dict)
    token_budget: int = Field(ge=1)

    @property
    def deadlock_free(self) -> bool:
        return self.deadlocks == 0

    @property
    def memory_within_budget(self) -> bool:
        return self.rss_peak_mb <= self.rss_budget_mb

    @property
    def no_binary_residue(self) -> bool:
        return self.raw_binary_residue_bytes == 0

    @property
    def tokens_within_budget(self) -> bool:
        return self.tokens_total <= self.token_budget

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "days": self.days,
            "hours": self.hours_simulated,
            "events": self.events_total,
            "meetings": self.meetings,
            "crises": self.crises,
            "breaches": self.breaches,
            "deadlocks": self.deadlocks,
            "rss_peak_mb": round(self.rss_peak_mb, 2),
            "rss_growth_mb": round(self.rss_growth_mb, 2),
            "raw_binary_residue_bytes": self.raw_binary_residue_bytes,
            "tokens_total": self.tokens_total,
            "token_budget": self.token_budget,
            "token_utilisation": round(self.tokens_total / self.token_budget, 4),
        }


class HeadlessLifeDriver:
    """无界面 30 天人生推演驱动引擎（纯 Python、零 UI、可在无图形 Linux 跑批）。"""

    def __init__(
        self,
        config: SimulationConfig | None = None,
        *,
        start: datetime | None = None,
    ) -> None:
        self._config = config or SimulationConfig()
        self._timeline = HeadlessLifeTimeline(self._config, start=start)
        self._deadlock = DeadlockSentinel(timeout_seconds=self._config.stage_timeout_seconds)
        self._memory = MemorySentinel(budget_mb=self._config.rss_budget_mb)
        self._policy = load_runtime_policy(self._config.policy_path)
        budget = min(
            self._config.monthly_token_budget,
            self._policy.monthly_token_budget,
        )
        self._tokens = TokenMeter(budget=budget)

    @property
    def config(self) -> SimulationConfig:
        return self._config

    @property
    def memory(self) -> MemorySentinel:
        return self._memory

    @property
    def tokens(self) -> TokenMeter:
        return self._tokens

    @property
    def policy(self) -> RuntimePolicy:
        return self._policy

    # ---- 主循环 ----

    def _timed(self, stage: str, fn: Any) -> tuple[Any, float]:
        """在死锁哨兵里执行阶段，并返回 (结果, 耗时毫秒)。"""
        started = time.perf_counter()
        value = self._deadlock.run(stage, fn)
        return (value, (time.perf_counter() - started) * 1000.0)

    def run(self, *, run_id: str | None = None) -> SimulationReport:
        started = time.perf_counter()
        config = self._config
        run = run_id or f"sim001-{utc_now().strftime('%Y%m%dT%H%M%S')}"
        stages: list[ChainStageResult] = []

        # 世界账本（C02 的落点）：临时库，跑批结束即弃
        from aios_core.storage import SQLiteWorldStore

        db_path = config.db_path or os.path.join(
            os.environ.get("TMPDIR", "/tmp"), f"{run}_world.db"
        )
        store = SQLiteWorldStore(db_path)

        # ---------- 阶段 1：数据接入 ----------
        timeline_events, ingest_ms = self._timed(
            ChainStage.INGEST.value, lambda: list(self._timeline.events())
        )
        events_total = len(timeline_events)
        meetings = sum(1 for e in timeline_events if e.kind is LifeEventKind.MEETING)
        crises = sum(1 for e in timeline_events if e.kind is LifeEventKind.BUSINESS_CRISIS)
        breaches = sum(1 for e in timeline_events if e.kind is LifeEventKind.CONTRACT_BREACH)
        stages.append(
            ChainStageResult(
                stage=ChainStage.INGEST,
                events_in=events_total,
                events_out=events_total,
                elapsed_ms=ingest_ms,
                detail={"hours": config.hours, "meetings": meetings, "crises": crises, "breaches": breaches},
            )
        )

        # ---------- 阶段 2：C01 边缘清洗（含图片物理粉碎）----------
        cleaning = C01EdgeCleaning(purge_threshold=config.purge_threshold)
        frames = [e for e in timeline_events if e.kind is LifeEventKind.CAPTURE_FRAME]
        for event in frames:
            cleaning.store_frame(
                frame_id=str(event.payload["frame_id"]),
                quality=float(event.payload["quality"]),
                scene_tag=str(event.payload["scene_tag"]),
                at=event.occurred_at,
            )
        (c01_report, cleaned_events), c01_ms = self._timed(
            ChainStage.C01_EDGE_CLEAN.value, lambda: cleaning.clean(timeline_events)
        )
        stages.append(
            ChainStageResult(
                stage=ChainStage.C01_EDGE_CLEAN,
                events_in=events_total,
                events_out=len(cleaned_events),
                elapsed_ms=c01_ms,
                detail={
                    "frames_assessed": c01_report.assessed,
                    "purged_frames": c01_report.purged_frames,
                    "bytes_freed": c01_report.bytes_freed,
                    "noise_filtered": c01_report.noise_filtered,
                    "cleaned_observation_seeds": c01_report.cleaned_observations,
                    "live_frames_after_purge": cleaning.live_frame_count,
                },
            )
        )

        # ---------- 阶段 3：构造世界对象 ----------
        world_objects, annotation_source = self._materialize_world(cleaned_events, run=run)

        # ---------- 阶段 4：C02 账本持久化 ----------
        ledger_writer = C02LedgerWriter(store)
        c02_detail, c02_ms = self._timed(
            ChainStage.C02_LEDGER_PERSIST.value,
            lambda: ledger_writer.commit_all(run_id=run, objects=world_objects),
        )
        stages.append(
            ChainStageResult(
                stage=ChainStage.C02_LEDGER_PERSIST,
                events_in=len(world_objects),
                events_out=ledger_writer.committed_count,
                elapsed_ms=c02_ms,
                detail={**c02_detail, "world_revision": store.current_world_revision()},
            )
        )

        # ---------- 阶段 5：C06 倒排求交 ----------
        intersection, c06_ms = self._timed(
            ChainStage.C06_HYPERLINK_INTERSECT.value,
            lambda: C06InvertedIntersector().build_and_intersect(store, root_entity_id="ent_wang"),
        )
        stages.append(
            ChainStageResult(
                stage=ChainStage.C06_HYPERLINK_INTERSECT,
                events_in=ledger_writer.committed_count,
                events_out=int(intersection.get("observations") or 0),
                elapsed_ms=c06_ms,
                detail=intersection,
            )
        )

        # ---------- 阶段 6：C04 单看板装配（Token 主战场，逐日采样 RSS）----------
        assembler = C04BoardAssembler(token_budget=self._policy.manifest_token_budget)
        board_tokens = 0
        sessions_total = 0
        board_started = time.perf_counter()
        self._memory.sample()  # 基线
        for day in range(config.days):
            day_moment = self._timeline.start + timedelta(days=day, hours=9)
            day_facts = self._day_facts(cleaned_events, day)
            (sessions, tokens), _ = self._timed(
                f"{ChainStage.C04_BOARD_ASSEMBLY.value}:day{day:02d}",
                lambda day=day, moment=day_moment, facts=day_facts: assembler.assemble_day(
                    day=day,
                    sessions=config.sessions_per_day,
                    turns_per_session=config.turns_per_session,
                    now=moment,
                    day_facts=facts,
                    ready_tasks=tuple(
                        f"第 {day + 1} 天成熟条件任务 {i}：交易文件签署窗口核对" for i in range(6)
                    ),
                ),
            )
            sessions_total += sessions
            board_tokens += tokens
            self._memory.sample()  # 逐日 RSS 采样（30 个样本）
        self._tokens.record(ChainStage.C04_BOARD_ASSEMBLY.value, board_tokens)
        stages.append(
            ChainStageResult(
                stage=ChainStage.C04_BOARD_ASSEMBLY,
                events_in=config.days,
                events_out=sessions_total,
                tokens=board_tokens,
                elapsed_ms=(time.perf_counter() - board_started) * 1000.0,
                detail={
                    "sessions": sessions_total,
                    "turns": sessions_total * config.turns_per_session * 2,
                    "manifest_token_budget": self._policy.manifest_token_budget,
                },
            )
        )

        # ---------- 阶段 7：C05 回溯注记 ----------
        c05_detail, c05_ms = self._timed(
            ChainStage.C05_RETRO_ANNOTATION.value,
            lambda: C05RetrospectiveRecorder(store).record(
                run_id=run,
                subject_id="user_founder",
                overlay="合同违约与隐匿连带担保：老王自设立之初即存在欺诈性转移",
                source_ref=annotation_source,
                learned_at=self._timeline.end + timedelta(minutes=1),
            ),
        )
        stages.append(
            ChainStageResult(
                stage=ChainStage.C05_RETRO_ANNOTATION,
                events_in=1,
                events_out=1,
                elapsed_ms=c05_ms,
                detail=c05_detail,
            )
        )

        self._deadlock.shutdown()
        wall_clock = time.perf_counter() - started
        residue = cleaning.residue_bytes()
        self._memory.sample()

        return SimulationReport(
            run_id=run,
            days=config.days,
            hours_simulated=config.hours,
            wall_clock_seconds=wall_clock,
            speed_multiplier=config.speed_multiplier,
            events_total=events_total,
            meetings=meetings,
            crises=crises,
            breaches=breaches,
            stages=tuple(stages),
            deadlocks=self._deadlock.deadlock_count,
            rss_baseline_mb=self._memory.baseline_mb,
            rss_peak_mb=self._memory.peak_mb,
            rss_growth_mb=self._memory.growth_mb,
            rss_budget_mb=self._memory.budget_mb,
            rss_tail_flat=self._memory.tail_is_flat(),
            raw_binary_residue_bytes=residue,
            tokens_total=self._tokens.total,
            tokens_by_stage=dict(self._tokens.by_stage()),
            token_budget=self._tokens.budget,
        )

    def _day_facts(self, events: Sequence[LifeEvent], day: int) -> tuple[str, ...]:
        """把某一天的事件压成可读事实摘要（驱动 C04 世界摘要层的真实内容）。"""
        facts: list[str] = []
        for event in events:
            if (event.occurred_at - self._timeline.start).days != day:
                continue
            if event.kind is LifeEventKind.CIRCADIAN_TICK:
                payload = event.payload
                facts.append(
                    f"{event.occurred_at:%H:%M} 心率 {payload['heart_rate_bpm']}bpm / "
                    f"HRV {payload['hrv_ms']}ms / {payload['sleep_stage']}"
                )
            elif event.kind is LifeEventKind.MEETING:
                facts.append(f"{event.occurred_at:%H:%M} 会议：{event.payload['topic']}")
            elif event.kind is LifeEventKind.WORKSHOP_NOISE:
                facts.append(f"{event.occurred_at:%H:%M} 车间噪声 {event.payload['noise_db']}dB")
            elif event.kind in (LifeEventKind.BUSINESS_CRISIS, LifeEventKind.CONTRACT_BREACH):
                facts.append(f"{event.occurred_at:%H:%M} 重大事件：{event.payload['summary']}")
        return tuple(facts)

    # ---- 世界对象物化 ----

    def _materialize_world(
        self, events: Sequence[LifeEvent], *, run: str
    ) -> tuple[list[Any], str]:
        """把清洗后的时空流物化成冻结契约对象（引用先行，保证外键可解析）。"""
        start = self._timeline.start
        end = start + timedelta(days=self._config.days)  # 证据集/锚点在推演收尾时成卷
        entities = [
            Entity(
                object_id="ent_wang",
                subject_id="ent_wang",
                learned_at=start,
                recorded_at=start,
                created_by="sim_001_engine",
                entity_kind="person",
                canonical_name="老王（技术合伙人）",
                aliases=["老王", "Wang", "技术合伙人"],
            ),
            Entity(
                object_id="ent_partner_tech",
                subject_id="ent_partner_tech",
                learned_at=start,
                recorded_at=start,
                created_by="sim_001_engine",
                entity_kind="organization",
                canonical_name="联合孵化主体",
                aliases=["联合孵化", "对赌主体"],
            ),
            Entity(
                object_id="ent_user",
                subject_id="ent_user",
                learned_at=start,
                recorded_at=start,
                created_by="sim_001_engine",
                entity_kind="person",
                canonical_name="本人（法务总监）",
                aliases=["我", "法务总监"],
            ),
        ]
        relations = [
            Relation(
                object_id="rel_wang_controls_partner_tech",
                subject_id="ent_wang",
                learned_at=start,
                recorded_at=start,
                created_by="sim_001_engine",
                left=ObjectRef(object_id="ent_wang", revision=1),
                relation_type="controls",
                right=ObjectRef(object_id="ent_partner_tech", revision=1),
                confidence=0.9,
            )
        ]

        observations: list[Observation] = []
        for event in events:
            if event.kind is LifeEventKind.CIRCADIAN_TICK:
                payload = event.payload
                observations.append(
                    Observation(
                        object_id=f"obs_{event.event_id}",
                        subject_id="ent_user",
                        occurred=TemporalExtent.point(event.occurred_at),
                        learned_at=event.occurred_at,
                        recorded_at=event.occurred_at,
                        created_by="sim_001_engine",
                        source_kind="wearable_band",
                        modality="vitals",
                        value=f"hr={payload['heart_rate_bpm']} hrv={payload['hrv_ms']}",
                        unit="bpm",
                        metadata={"sleep_stage": payload["sleep_stage"], "noise_db": payload["noise_db"]},
                    )
                )
            elif event.kind is LifeEventKind.MEETING:
                observations.append(
                    Observation(
                        object_id=f"obs_{event.event_id}",
                        subject_id="ent_user",
                        occurred=TemporalExtent.point(event.occurred_at),
                        learned_at=event.occurred_at,
                        recorded_at=event.occurred_at,
                        created_by="sim_001_engine",
                        source_kind="meeting_note",
                        modality="text",
                        value=f"{event.payload['topic']}（{event.payload['attendees']} 人）",
                    )
                )
            elif event.kind in (
                LifeEventKind.BUSINESS_CRISIS,
                LifeEventKind.CONTRACT_BREACH,
            ):
                observations.append(
                    Observation(
                        object_id=f"obs_{event.event_id}",
                        subject_id="ent_wang",
                        occurred=TemporalExtent.point(event.occurred_at),
                        learned_at=event.occurred_at,
                        recorded_at=event.occurred_at,
                        created_by="sim_001_engine",
                        source_kind=(
                            "regulatory_notice"
                            if event.kind is LifeEventKind.BUSINESS_CRISIS
                            else "contract_document"
                        ),
                        modality="document",
                        value=str(event.payload["summary"]),
                        metadata=dict(event.payload),
                    )
                )
        breach_ids = [
            f"obs_{event.event_id}"
            for event in events
            if event.kind is LifeEventKind.CONTRACT_BREACH
        ]
        if not breach_ids:
            # 短于违约日的窗口不构成一"人生推演"：宁可显式报错，也不生成退化世界。
            raise AIOSProtocolError(
                ErrorCode.INCOMPLETE_DATA,
                "simulation window does not contain the contract-breach event",
                context={
                    "reason": "breach_event_missing",
                    "days": self._config.days,
                    "required_min_days": BREACH_DAY + 1,
                },
            )
        breach_observation_id = breach_ids[0]
        evidence_sets = [
            EvidenceSet(
                object_id="es_sim_wang_chain",
                subject_id="ent_wang",
                learned_at=end,
                recorded_at=end,
                created_by="sim_001_engine",
                purpose="support",
                knowledge_window=self._knowledge_window(),
                selection_method="structured_reference_walk",
                member_refs=[
                    ObjectRef(object_id=breach_observation_id, revision=1),
                    *[
                        ObjectRef(object_id=o.object_id, revision=1)
                        for o in observations
                        if o.subject_id == "ent_wang" and o.object_id != breach_observation_id
                    ],
                ],
            )
        ]
        anchors = [
            EventAnchor(
                object_id="anchor_sim_breach",
                subject_id="ent_wang",
                learned_at=end,
                recorded_at=end,
                created_by="sim_001_engine",
                title="老王合同违约事件",
                interpretation="对赌协议项下核心义务未履行，且存在隐匿连带担保",
                confidence=0.92,
                event_time=TemporalExtent.point(
                    start + timedelta(days=BREACH_DAY, hours=16, minutes=20)
                ),
                participant_refs=[
                    ObjectRef(object_id="ent_wang", revision=1),
                    ObjectRef(object_id="ent_partner_tech", revision=1),
                ],
                evidence_set_refs=[ObjectRef(object_id="es_sim_wang_chain", revision=1)],
            )
        ]
        objects: list[Any] = [*entities, *relations, *observations, *evidence_sets, *anchors]
        return (objects, breach_observation_id)

    def _knowledge_window(self) -> Any:
        """证据集的知识窗口：以推演收尾时刻为认知截止（当时全部事实已知）。"""
        from aios_core.contracts.time import KnowledgeWindow

        return KnowledgeWindow(
            knowledge_cutoff=self._timeline.start + timedelta(days=self._config.days)
        )


def purge_audit_rows(cleaning: C01EdgeCleaning) -> Iterable[Mapping[str, Any]]:
    """只读导出粉碎审计（便于跑批后人工抽查，绝不修改世界状态）。"""
    return tuple(
        {
            "frame_id": record.frame_id,
            "quality": record.quality,
            "bytes_freed": record.bytes_freed,
        }
        for record in cleaning.sink.audit_trail
    )
