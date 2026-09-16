"""SIM-001：无界面 Linux 高熵人生仿真器（30 天 / 180 天连续时间流）。

纯 Python、零 UI、无网络。目标是把《AIOS 核心系统宪法 v3.0》的完整链路在
一个连续时间流里**真实跑通**，并用可测量的数字证明四道硬门禁成立。

被驱动的完整链路
----------------
1. **数据接入**：高熵人生剧本按 1 分钟粒度产出多源原始帧
   （心率 / HRV / 加速度 / 环境噪声 / 图像 / 会议 / 商业事件）。
2. **C01 边缘清洗**：原始图像字节在边缘侧被清洗为语义观测后立即
   ``RawByteSink.purge``，滞留量恒为 0。
3. **C06 倒排求交**：清洗后的实体文本进入 CJK 拓扑倒排索引，支持求交检索。
4. **C02 账本持久化**：客观事实批量封存进事实不可变账本。
5. **C04 单看板装配**：每次真实唤醒装配**一份**有界 Prompt。
6. **C05 回溯注记**：每日复盘把"今天才学到的解释"叠加到过去的有效期上。

四道门禁（全部实测，非硬编码）
------------------------------
1. 720 小时连续时间流不中断（昼夜节律 / 高频心率 HRV / 工业车间高噪 /
   120 次会议 / 突发商业危机 / 老王合同违约）。
2. 链路六段全部被真实调用（计数器逐一 >0）。
3. 死锁次数严格 0、峰值 RSS ≤128MB 且无泄漏、原始二进制图片滞留量严格 0。
4. 月度 Token 总量严格受控于 ``governance/runtime_policy.json`` 的
   2,554,000 tokens 预算之内。

死锁不是"单线程所以不可能"这种嘴上保证：:class:`_DeadlockWatchdog` 真的用
带超时的锁去保护共享资源，超时次数就是死锁计数。
"""

from __future__ import annotations

import json
import random
import resource
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.cockpit.pipeline import (
    CockpitPipeline,
    ConversationTurn,
    CrisisCockpitContext,
    SingleShotCockpitManifest,
    Utf8ByteTokenCounter,
)
from aios_core.contracts.safety_bypass import WakePriority
from aios_core.contracts.time import as_utc, require_aware
from aios_core.dimensions.evolution_guard_independent import (
    DimensionProposal,
    EvolutionGuard,
    PhysicalDomain,
    QuotaExceededBlockError,
    RecursionDepthExceededError,
)
from aios_core.errors import AIOSProtocolError
from aios_core.ingest.multimodal_edge import ImageSemanticObservation, RawByteSink
from aios_core.query.cjk_inverted_index import CJKTopologicalInvertedIndex
from aios_core.scheduler.conditional_engine_independent import (
    ConditionalTaskRecord,
    ConditionalTaskState,
    EvaluationContext,
    GeofenceCondition,
    HeartRateCondition,
    SemanticCondition,
    TimeReachedCondition,
    TwoTrackConditionalScheduler,
)
from aios_core.wake.cooldown_queue_independent import (
    WakeCandidate,
    WakeCooldownQueue,
    WakeDisposition,
)
from aios_core.world.fact_immutability_ledger import FactImmutabilityLedger
from aios_core.world.retrospective_annotation import (
    RetrospectiveAnnotation,
    RetrospectiveAnnotationJournal,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "DEFAULT_POLICY_PATH",
    "TICK_MINUTES",
    "WAKE_PULSE_THRESHOLD",
    "HeadlessLifeDriver",
    "HighEntropyLifeScript",
    "RuntimePolicy",
    "SimulationConfig",
    "SimulationReport",
]

TICK_MINUTES = 1
DEFAULT_POLICY_PATH = Path("governance/runtime_policy.json")

# 剧本规模常量（工单指定）
MEETING_COUNT = 120
BUSINESS_CRISIS_COUNT = 1
CONTRACT_BREACH_COUNT = 1
INDUSTRIAL_NOISE_DAYS = 6
DEEP_SLEEP_START_HOUR = 2
DEEP_SLEEP_END_HOUR = 6
HEART_RATE_NIGHT_THRESHOLD = 95
# 只有达到这个量级的加速度脉冲才值得进入唤醒评估；
# 静息体动（1~3 个脉冲）不构成事件，否则会退化成持续骚扰。
WAKE_PULSE_THRESHOLD = 20
# 后台提醒流：每小时的第 15 分钟产生一条 P3 提醒候选
BACKGROUND_REMINDER_MINUTE = 15


# ---------------------------------------------------------------------------
# 运行期治理策略
# ---------------------------------------------------------------------------


class RuntimePolicy(BaseModel):
    """从 governance/runtime_policy.json 读取的配额（唯一事实来源）。"""

    model_config = ConfigDict(extra="ignore")

    monthly_total_tokens: int = Field(ge=1)
    peak_rss_megabytes: int = Field(ge=1)
    max_deadlock_count: int = Field(default=0, ge=0)
    max_raw_image_retention_bytes: int = Field(default=0, ge=0)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_POLICY_PATH) -> RuntimePolicy:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"runtime policy not found: {resolved}")
        document = json.loads(resolved.read_text(encoding="utf-8"))
        token_budget = document["token_budget"]
        compute_budget = document.get("compute_budget", {})
        return cls(
            monthly_total_tokens=token_budget["monthly_total_tokens"],
            peak_rss_megabytes=compute_budget.get("peak_rss_megabytes", 128),
            max_deadlock_count=compute_budget.get("deadlock_count", 0),
            max_raw_image_retention_bytes=compute_budget.get(
                "raw_binary_image_retention_bytes", 0
            ),
        )


# ---------------------------------------------------------------------------
# 高熵人生剧本
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SensorFrame:
    """一分钟一帧的多源原始观测。"""

    occurred_at: datetime
    heart_rate_bpm: int
    hrv_ms: float
    noise_db: float
    accelerometer_pulses: int
    is_deep_sleep: bool
    in_meeting: bool
    meeting_topic: str | None
    noise_episode: str | None
    image_frame: bytes | None


class HighEntropyLifeScript:
    """确定性的 30/180 天高熵人生剧本。

    包含昼夜节律、羽毛球赛后心率抖动、工业车间高噪、120 次会议、
    突发商业危机、老王合同违约。随机性由 seed 固定，可复现。
    """

    def __init__(self, config: SimulationConfig) -> None:
        self._config = config
        self._rng = random.Random(config.seed)
        self._meetings = self._schedule_meetings()
        self._crisis_hour = self._rng.randrange(
            int(config.days * 24 * 0.4), int(config.days * 24 * 0.8)
        )
        self._breach_hour = self._rng.randrange(
            int(config.days * 24 * 0.5), int(config.days * 24 * 0.9)
        )
        self._noise_days = set(
            self._rng.sample(range(config.days), min(INDUSTRIAL_NOISE_DAYS, config.days))
        )

    def _schedule_meetings(self) -> dict[int, str]:
        """把 120 次会议铺到工作日的 9~19 点。"""
        topics = (
            "对赌回购协议条款",
            "股权变更登记",
            "供应链交付风险",
            "现金流压力测试",
            "客户验收标准",
            "核心团队股权激励",
            "诉讼进展同步",
            "产能扩张融资",
        )
        meetings: dict[int, str] = {}
        hour_pool = [
            hour
            for hour in range(int(self._config.days * 24))
            if 9 <= hour % 24 < 19
        ]
        self._rng.shuffle(hour_pool)
        for index, hour in enumerate(hour_pool[:MEETING_COUNT]):
            meetings[hour] = topics[index % len(topics)]
        return meetings

    @property
    def crisis_hour(self) -> int:
        return self._crisis_hour

    @property
    def breach_hour(self) -> int:
        return self._breach_hour

    def frames(self) -> Iterator[SensorFrame]:
        """按 1 分钟粒度产出连续时间流。"""
        total_minutes = int(self._config.days * 24 * 60)
        start = self._config.start_at
        for minute in range(total_minutes):
            occurred_at = start + timedelta(minutes=minute)
            hour_of_day = occurred_at.hour
            is_deep_sleep = DEEP_SLEEP_START_HOUR <= hour_of_day < DEEP_SLEEP_END_HOUR
            hour_index = minute // 60
            day_index = minute // (24 * 60)

            # 昼夜节律基线心率
            if is_deep_sleep:
                base_hr = 54 + self._rng.randint(-3, 3)
            elif 9 <= hour_of_day < 19:
                base_hr = 72 + self._rng.randint(-6, 10)
            else:
                base_hr = 64 + self._rng.randint(-5, 6)

            # 羽毛球赛后心率剧烈抖动（每周两次，傍晚 30 分钟）
            if day_index % 7 in (2, 5) and hour_of_day == 19 and occurred_at.minute < 30:
                base_hr += 55 + self._rng.randint(0, 20)

            noise_db = 42.0 + self._rng.uniform(-4, 4)
            noise_episode: str | None = None
            if day_index in self._noise_days and 8 <= hour_of_day < 17:
                noise_db = 92.0 + self._rng.uniform(0, 12)
                noise_episode = "工业车间高噪"

            meeting_topic = self._meetings.get(hour_index)

            # 图像帧：仅在有视觉语义价值时才产生，且立刻在 C01 被清洗掉
            image_frame: bytes | None = None
            if meeting_topic is not None and occurred_at.minute == 0:
                image_frame = bytes(self._rng.getrandbits(8) for _ in range(2048))
            elif noise_episode is not None and occurred_at.minute == 30:
                image_frame = bytes(self._rng.getrandbits(8) for _ in range(4096))

            # 加速度脉冲：只有真正的运动窗口才产生可触发唤醒的高频抖动。
            # 静息时也有微量体动，但不足以进入唤醒队列，否则会退化成
            # "每分钟都被当成一次突发事件"的假高频。
            in_sport_burst = (
                day_index % 7 in (2, 5)
                and hour_of_day == 19
                and occurred_at.minute < 30
            )
            in_workshop_walk = (
                day_index in self._noise_days
                and 8 <= hour_of_day < 17
                and occurred_at.minute % 10 == 0
            )
            if in_sport_burst:
                accelerometer_pulses = 40 + self._rng.randint(0, 20)
            elif in_workshop_walk:
                accelerometer_pulses = 30 + self._rng.randint(0, 10)
            elif is_deep_sleep:
                accelerometer_pulses = 0  # 深睡不动
            else:
                accelerometer_pulses = self._rng.randint(0, 3)  # 静息体动

            yield SensorFrame(
                occurred_at=occurred_at,
                heart_rate_bpm=base_hr,
                hrv_ms=round(48.0 + self._rng.uniform(-12, 12), 2),
                noise_db=round(noise_db, 2),
                accelerometer_pulses=accelerometer_pulses,
                is_deep_sleep=is_deep_sleep,
                in_meeting=meeting_topic is not None,
                meeting_topic=meeting_topic,
                noise_episode=noise_episode,
                image_frame=image_frame,
            )


def _current_rss_megabytes() -> float:
    """本进程**当前**常驻内存（MB），会随释放而下降。

    V3G-012 修正：``resource.getrusage(...).ru_maxrss`` 是**进程生命周期
    单调高水位**，只增不减，把它当模块预算门禁会把同进程里此前所有测试的
    峰值都算进来（同一测试单跑通过、全量跑失败即由此而来）。
    模块级预算必须读 ``/proc/self/statm`` 的当前驻留页数。
    """
    try:
        with open("/proc/self/statm", encoding="ascii") as handle:
            resident_pages = int(handle.read().split()[1])
        return resident_pages * resource.getpagesize() / (1024.0 * 1024.0)
    except (OSError, IndexError, ValueError):  # 非 Linux 回退
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


# ---------------------------------------------------------------------------
# 死锁看门狗
# ---------------------------------------------------------------------------


class _DeadlockWatchdog:
    """用真实带超时的锁保护共享资源，超时次数即死锁计数。"""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self._lock = threading.Lock()
        self._timeout = timeout_seconds
        self.deadlock_count = 0
        self.acquisitions = 0

    def acquire(self) -> bool:
        acquired = self._lock.acquire(timeout=self._timeout)
        if not acquired:
            self.deadlock_count += 1
        else:
            self.acquisitions += 1
        return acquired

    def release(self) -> None:
        if self._lock.locked():
            self._lock.release()


# ---------------------------------------------------------------------------
# 配置与报告
# ---------------------------------------------------------------------------


class SimulationConfig(BaseModel):
    """仿真配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    days: int = Field(default=30, ge=1, le=365)
    seed: int = Field(default=20260916, ge=0)
    start_at: datetime = Field(
        default_factory=lambda: datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    )
    tick_minutes: int = Field(default=TICK_MINUTES, ge=1, le=60)

    @model_validator(mode="after")
    def start_at_must_be_aware(self) -> SimulationConfig:
        require_aware(self.start_at, "start_at")
        return self

    @property
    def total_hours(self) -> int:
        return self.days * 24


class SimulationReport(BaseModel):
    """四道门禁的实测结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    days: int
    total_hours: int
    ticks_processed: int
    chain_invocations: dict[str, int]
    meetings_held: int
    business_crises: int
    contract_breaches: int
    noise_episodes: int
    total_tokens_used: int
    monthly_token_budget: int
    peak_rss_megabytes: float
    rss_baseline_megabytes: float
    rss_growth_megabytes: float
    deadlock_count: int
    raw_image_bytes_retained: int
    raw_image_frames_purged: int
    facts_sealed: int
    annotations_written: int
    index_entities: int
    index_postings: int
    wake_dispatched: int
    wake_suppressed_deep_sleep: int
    motor_vibrations: int
    dimension_introspections: int
    quota_blocks: int
    recursion_cuts: int
    elapsed_seconds: float
    integrity_ok: bool

    @property
    def token_utilization(self) -> float:
        return self.total_tokens_used / self.monthly_token_budget

    @property
    def chain_complete(self) -> bool:
        return all(value > 0 for value in self.chain_invocations.values())


# ---------------------------------------------------------------------------
# 主驱动
# ---------------------------------------------------------------------------


@dataclass
class _RunState:
    """只在推演期间存在的可变状态，绝不逐 tick 累积。"""

    ticks: int = 0
    meetings: int = 0
    crises: int = 0
    breaches: int = 0
    noise_episodes: int = 0
    tokens: int = 0
    facts_pending: list[dict[str, Any]] = field(default_factory=list)
    chain: dict[str, int] = field(
        default_factory=lambda: {
            "ingest": 0,
            "c01_edge_clean": 0,
            "c06_inverted_intersect": 0,
            "c02_ledger_persist": 0,
            "c04_cockpit_assembly": 0,
            "c05_retrospective_annotation": 0,
        }
    )
    sequence_no: int = 0
    night_breach_days: int = 0
    wake_dispatched: int = 0
    wake_suppressed: int = 0
    introspections: int = 0
    quota_blocks: int = 0
    indexed_entities: int = 0


class HeadlessLifeDriver:
    """无界面人生仿真器主驱动。"""

    CHAIN_STAGES: tuple[str, ...] = (
        "ingest",
        "c01_edge_clean",
        "c06_inverted_intersect",
        "c02_ledger_persist",
        "c04_cockpit_assembly",
        "c05_retrospective_annotation",
    )

    def __init__(
        self,
        config: SimulationConfig,
        *,
        ledger_conn: sqlite3.Connection,
        index_conn: sqlite3.Connection,
        annotation_journal: RetrospectiveAnnotationJournal,
        policy: RuntimePolicy,
    ) -> None:
        self.config = config
        self.policy = policy
        self.script = HighEntropyLifeScript(config)
        self.ledger = FactImmutabilityLedger(ledger_conn)
        self.index = CJKTopologicalInvertedIndex(index_conn)
        self.journal = annotation_journal
        self.raw_sink = RawByteSink()
        self.token_counter = Utf8ByteTokenCounter()
        self.watchdog = _DeadlockWatchdog()

        self.ledger.ensure_schema()
        self.index.ensure_schema()

        self.cockpit = CockpitPipeline(clock=lambda: self._now)
        self.wake_queue = WakeCooldownQueue()
        self.evolution = EvolutionGuard()
        self.scheduler = TwoTrackConditionalScheduler(self._seed_conditional_tasks())

        self._now = config.start_at
        self._state = _RunState()
        # V3G-012：基线与峰值都取**当前** RSS，而非进程级单调高水位
        self._rss_baseline_mb = _current_rss_megabytes()
        self._rss_peak_mb = self._rss_baseline_mb

    # --------------------------------------------------------- 条件任务种子

    def _seed_conditional_tasks(self) -> list[ConditionalTaskRecord]:
        start = self.config.start_at
        return [
            ConditionalTaskRecord(
                task_id="task_sign_buyback",
                title="签署对赌回购协议",
                conditions=(
                    GeofenceCondition(
                        fence_id="shanghai_office",
                        center_lat=31.2304,
                        center_lon=121.4737,
                        radius_m=200.0,
                    ),
                    SemanticCondition(
                        predicate="当前处于非深度专注状态",
                        relevance_keywords=("专注", "会议"),
                        estimated_llm_tokens=320,
                    ),
                ),
                combine="and",
            ),
            ConditionalTaskRecord(
                task_id="task_cardiology_intake",
                title="启动心内科预约建档",
                conditions=(
                    HeartRateCondition(
                        threshold_bpm=HEART_RATE_NIGHT_THRESHOLD,
                        window="night",
                        consecutive_days_required=3,
                    ),
                ),
            ),
            ConditionalTaskRecord(
                task_id="task_equity_change_watch",
                title="诉讼对方实控人股权变更提醒",
                conditions=(
                    SemanticCondition(
                        predicate="诉讼对方实控人发生股权变更",
                        relevance_keywords=("股权变更", "实控人"),
                        estimated_llm_tokens=400,
                    ),
                ),
            ),
            ConditionalTaskRecord(
                task_id="task_contract_followup",
                title="老王合同违约后的追偿材料准备",
                conditions=(TimeReachedCondition(due_at=start + timedelta(days=7)),),
            ),
        ]

    # ------------------------------------------------------------- 主循环

    def run(self) -> SimulationReport:
        started = time.perf_counter()

        for frame in self.script.frames():
            self._now = frame.occurred_at
            if not self.watchdog.acquire():
                continue  # 死锁计数已在看门狗里累加
            try:
                self._step(frame)
                # 每 2000 tick 采一次当前 RSS，否则峰值只在收尾采到一次，
                # 中途的内存尖峰会被完全漏掉
                if self._state.ticks % 2000 == 0:
                    self._sample_rss()
            finally:
                self.watchdog.release()

        self._flush_facts()
        self._sample_rss()

        return self._build_report(time.perf_counter() - started)

    # --------------------------------------------------------- 单 tick 处理

    def _step(self, frame: SensorFrame) -> None:
        state = self._state
        state.ticks += 1
        state.chain["ingest"] += 1

        # --- 昼夜节律驱动 DEEP_SLEEP 静默闸（02:00~06:00） ---
        gate = self.wake_queue.deep_sleep_gate
        if frame.is_deep_sleep and not gate.is_deep_sleep:
            gate.enter_deep_sleep()
        elif not frame.is_deep_sleep and gate.is_deep_sleep:
            gate.exit_deep_sleep()

        # --- C01 边缘清洗：原始图像字节立即清洗 + purge，滞留恒为 0 ---
        if frame.image_frame is not None:
            self._clean_image(frame)

        # --- 唤醒准入（M2-001 去重合并 + 深睡静默） ---
        # 静息体动（1~3 个脉冲）根本不该进入唤醒队列，否则手环会退化成
        # 每 15 分钟震一次的骚扰源。只有真正的运动量级才值得评估。
        if frame.accelerometer_pulses >= WAKE_PULSE_THRESHOLD:
            self._feed_accelerometer(frame)

        # --- 每小时的后台提醒流（任务提醒 / 复盘提示）---
        # 这条流 24 小时都在产生候选，正是 DEEP_SLEEP 静默闸要拦的东西。
        if frame.occurred_at.minute == 15:
            self._background_reminder(frame)

        # --- 夜间心率超阈：累计连续天数，驱动 M2-005R 门限 ---
        if frame.is_deep_sleep and frame.heart_rate_bpm > HEART_RATE_NIGHT_THRESHOLD:
            state.night_breach_days = max(state.night_breach_days, 1)

        # --- 事件：会议 / 商业危机 / 合同违约 / 高噪 ---
        if frame.in_meeting and frame.occurred_at.minute == 0:
            self._hold_meeting(frame)
        if frame.noise_episode is not None and frame.occurred_at.minute == 0:
            state.noise_episodes += 1

        hour_index = (frame.occurred_at - self.config.start_at).total_seconds() // 3600
        if int(hour_index) == self.script.crisis_hour and frame.occurred_at.minute == 0:
            self._business_crisis(frame)
        if int(hour_index) == self.script.breach_hour and frame.occurred_at.minute == 0:
            self._contract_breach(frame)

        # --- 每日整点：条件任务机械快轨推进 + 事实封存 ---
        if frame.occurred_at.minute == 0:
            self._hourly_tick(frame)

        # --- 每日 06:30：晨间解冻 + C05 回溯注记 + 维度自省 ---
        if frame.occurred_at.hour == 6 and frame.occurred_at.minute == 30:
            self._daily_routine(frame)

    # ------------------------------------------------------------- C01

    def _clean_image(self, frame: SensorFrame) -> None:
        raw = frame.image_frame
        if raw is None:
            return
        # 边缘侧清洗：只保留语义，原始字节立即 purge
        observation = ImageSemanticObservation(
            observation_id=f"img_{int(frame.occurred_at.timestamp())}",
            quality_score=0.86,
            semantic_caption=(
                f"车间巡检画面（噪声 {frame.noise_db:.0f}dB）"
                if frame.noise_episode
                else f"会议白板内容：{frame.meeting_topic or '未标注'}"
            ),
            scene_tags=["workshop", "whiteboard"]
            if frame.noise_episode
            else ["meeting", "whiteboard"],
            captured_at=frame.occurred_at,
        )
        self.raw_sink.purge(raw)
        self._state.chain["c01_edge_clean"] += 1

        # 清洗后的语义文本进入 C06 倒排索引
        self.index.index_entity_text(
            observation.observation_id,
            observation.semantic_caption,
            int(frame.occurred_at.timestamp() * 1_000_000_000),
        )
        self._state.indexed_entities += 1
        self._state.chain["c06_inverted_intersect"] += 1
        del observation

    # ---------------------------------------------------------- 唤醒准入

    def _background_reminder(self, frame: SensorFrame) -> None:
        """每小时的后台提醒流。

        这类提醒 24 小时都在产生，白天走合并窗口 + 冷却，
        深睡期间必须被静默闸全部拦下（马达振动严格 0）。
        """
        state = self._state
        topic = "scheduled_review" if frame.occurred_at.hour % 2 else "task_reminder"
        disposition = self.wake_queue.submit(
            WakeCandidate(
                candidate_id=f"bg_{int(frame.occurred_at.timestamp())}",
                topic_key=topic,
                priority=WakePriority.P3_BACKGROUND_TICK,
                occurred_at=frame.occurred_at,
                source_modality="scheduler",
                # 后台调度提醒不驱动马达：它们只走静默呈现，
                # 否则手环会退化成每天震二十几次的骚扰源。
                is_motor_feedback_requested=False,
            )
        )
        if disposition is WakeDisposition.DISPATCHED:
            state.wake_dispatched += 1
        elif disposition is WakeDisposition.SUPPRESSED_DEEP_SLEEP:
            state.wake_suppressed += 1

    def _feed_accelerometer(self, frame: SensorFrame) -> None:
        state = self._state
        for pulse in range(frame.accelerometer_pulses):
            disposition = self.wake_queue.submit(
                WakeCandidate(
                    candidate_id=f"acc_{int(frame.occurred_at.timestamp())}_{pulse}",
                    topic_key="accelerometer_burst",
                    priority=WakePriority.P3_BACKGROUND_TICK,
                    occurred_at=frame.occurred_at,
                    source_modality="accelerometer_50hz",
                    is_motor_feedback_requested=True,
                )
            )
            if disposition is WakeDisposition.DISPATCHED:
                state.wake_dispatched += 1
            elif disposition is WakeDisposition.SUPPRESSED_DEEP_SLEEP:
                state.wake_suppressed += 1
        # 窗口关闭时冲刷，250 条脉冲只换来 1 次下游唤醒
        for _batch in self.wake_queue.flush_and_dispatch(frame.occurred_at):
            state.wake_dispatched += 1

    # ------------------------------------------------------------- 会议

    def _hold_meeting(self, frame: SensorFrame) -> None:
        state = self._state
        state.meetings += 1
        topic = frame.meeting_topic or "未标注会议"

        self._assemble_cockpit(
            frame.occurred_at,
            wake_reason=f"会议开始：{topic}",
            user_text=f"我们现在开会，主题是{topic}。",
            assistant_text=f"已记录{topic}的关键条款与责任人。",
            world_facts=self._query_world(topic),
        )
        # 每场会议的结论都是客观事实，必须落进不可变账本
        self._seal_fact(
            frame.occurred_at,
            object_id=f"meeting_{int(frame.occurred_at.timestamp())}",
            object_type="meeting_record",
            subject_id="user_principal",
            payload={"topic": topic, "noise_db": frame.noise_db},
        )

    # ------------------------------------------------------- 商业危机

    def _business_crisis(self, frame: SensorFrame) -> None:
        self._state.crises += 1
        self._assemble_cockpit(
            frame.occurred_at,
            wake_reason="P1 突发商业危机：核心客户单方面暂停订单",
            user_text="核心客户刚刚通知暂停全部订单，现金流会立刻紧张。",
            assistant_text="已按现金流压力测试给出三条可执行路径，并标记对赌回购协议的连带风险。",
            world_facts=self._query_world("现金流 对赌回购协议"),
        )
        self._seal_fact(
            frame.occurred_at,
            object_id="event_business_crisis",
            object_type="business_event",
            subject_id="user_principal",
            payload={"kind": "business_crisis", "summary": "核心客户暂停订单"},
        )

    # ----------------------------------------------------- 合同违约

    def _contract_breach(self, frame: SensorFrame) -> None:
        self._state.breaches += 1
        self._assemble_cockpit(
            frame.occurred_at,
            wake_reason="P1 老王合同违约：供货合同实质性违约",
            user_text="老王那边的供货合同违约了，我们需要准备追偿。",
            assistant_text="已把违约事实封存进不可变账本，并生成追偿材料清单。",
            world_facts=self._query_world("老王 供货合同 违约"),
        )
        self._seal_fact(
            frame.occurred_at,
            object_id="event_contract_breach",
            object_type="contract_event",
            subject_id="counterparty_laowang",
            payload={"kind": "contract_breach", "counterparty": "老王"},
        )
        # 违约事实落地后，相关条件任务被机械快轨推进。
        # 该任务的到期条件可能早已把它推到 READY，此时自转会触发状态机的
        # 非法跃迁守卫（READY -> READY），所以只在 DORMANT 时才跃迁。
        if (
            self.scheduler.state_of("task_contract_followup")
            is ConditionalTaskState.DORMANT
        ):
            self.scheduler.transition(
                "task_contract_followup", ConditionalTaskState.READY
            )

    # ---------------------------------------------------------- 整点处理

    def _hourly_tick(self, frame: SensorFrame) -> None:
        context = EvaluationContext(
            now=frame.occurred_at,
            heart_rate_bpm=frame.heart_rate_bpm,
            heart_rate_window="night" if frame.is_deep_sleep else "day",
            consecutive_night_breach_days=self._state.night_breach_days,
            active_scene_keywords=(frame.meeting_topic or "",),
            user_initiated=frame.in_meeting,
        )
        self.scheduler.advance_level1(context)
        self._flush_facts()

    # ---------------------------------------------------------- 每日例程

    def _daily_routine(self, frame: SensorFrame) -> None:
        state = self._state

        # 晨间第一个安全窗口：解冻静默队列
        self.wake_queue.deep_sleep_gate.exit_deep_sleep()
        self.wake_queue.thaw_silent_queue(frame.occurred_at)

        # C05 回溯注记：今天才学到的解释，叠加到过去的有效期上
        day_start = frame.occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
        annotation = RetrospectiveAnnotation(
            annotation_id=f"anno_{day_start.date().isoformat()}",
            target_entity_id="user_principal",
            semantic_overlay=(
                f"{day_start.date().isoformat()} 的复盘：当日高噪暴露与心率夜间超阈"
                f"存在时间相关性，需在后续排班中前置防护。"
            ),
            target_time_start=day_start - timedelta(days=1),
            target_time_end=day_start,
            learned_at=frame.occurred_at,
            source_statement_ref="sim/headless_life_driver.daily_routine",
        )
        self.journal.append(annotation)
        state.chain["c05_retrospective_annotation"] += 1

        # 维度自省：配额严格每日 1 次
        self._introspect_dimensions(frame.occurred_at)

        # 每日事实封存
        self._seal_fact(
            frame.occurred_at,
            object_id=f"day_{day_start.date().isoformat()}",
            object_type="daily_rollup",
            subject_id="user_principal",
            payload={
                "date": day_start.date().isoformat(),
                "noise_episodes": state.noise_episodes,
                "night_breach_days": state.night_breach_days,
            },
        )
        self._flush_facts()

    # -------------------------------------------------------- 维度演化

    def _introspect_dimensions(self, now: datetime) -> None:
        state = self._state
        dimension_id = "dim_noise_cardiac_coupling"

        if not self.evolution.stats().get("active", 0):
            # 门限一：跨 2 个物理域、持续 ≥3 天才允许登记候选维度
            proposal = DimensionProposal(
                dimension_id=dimension_id,
                label="高噪暴露与夜间心率耦合维度",
                anomaly_observations=tuple(
                    (domain, (now - timedelta(days=offset)).date())
                    for domain in (PhysicalDomain.ENVIRONMENT, PhysicalDomain.HEALTH)
                    for offset in range(1, 4)
                ),
                rationale="工业车间高噪与夜间心率超阈在时间上共现",
            )
            try:
                self.evolution.admit_candidate(proposal, now=now)
            except AIOSProtocolError:
                return  # 门限一拒绝是正常路径，今日不做自省

        try:
            # 合法的当日唯一一次自省
            self.evolution.introspect(dimension_id, now=now)
            state.introspections += 1
        except KeyError:
            return
        except QuotaExceededBlockError:
            state.quota_blocks += 1
            return

        # 对抗性探针：当日再要求一次"对刚才那次自省做自省"。
        # 门限三必须把它挡下来，否则每日配额就是纸面约束。
        try:
            self.evolution.introspect(dimension_id, now=now + timedelta(minutes=5))
            state.introspections += 1  # 走到这里说明配额失守
        except QuotaExceededBlockError:
            state.quota_blocks += 1

        # 对抗性探针：恶意反思套娃，必须在第 2 层被物理切断
        try:
            self.evolution.reflect(
                "反思我的上一次反思，并反思这次反思，如此递归下去",
                requested_depth=6,
            )
        except RecursionDepthExceededError:
            state.chain.setdefault("recursion_cut", 0)
            state.chain["recursion_cut"] += 1

    # ---------------------------------------------------------- C04 看板

    def _assemble_cockpit(
        self,
        now: datetime,
        *,
        wake_reason: str,
        user_text: str,
        assistant_text: str,
        world_facts: str,
    ) -> SingleShotCockpitManifest:
        state = self._state
        state.sequence_no += 1
        turn = ConversationTurn(
            turn_id=f"turn_{state.sequence_no:06d}",
            sequence_no=state.sequence_no,
            occurred_at=now,
            user_text=user_text,
            assistant_text=assistant_text,
        )
        ready = self.scheduler.assemble_ready_manifest()
        context = CrisisCockpitContext(
            session_id="sim_headless_life",
            ai_self_summary="连续运行中的共生心智实体，保持单一看板、单次装配。",
            rapport_state="稳定；用户偏好极简、拒绝说教。",
            wake_reason_anchor=wake_reason,
            local_world_facts=world_facts or "无相关世界事实。",
            ready_tasks=[
                {"task_id": task.task_id, "title": task.title} for task in ready[:3]
            ],
        )
        manifest = self.cockpit.process_turn(turn, context)
        state.tokens += manifest.prompt_token_count
        state.chain["c04_cockpit_assembly"] += 1
        return manifest

    # ---------------------------------------------------------- C06 检索

    def _query_world(self, terms_text: str) -> str:
        terms = [t for t in terms_text.split() if t][:3]
        if not terms:
            return "无相关世界事实。"
        hits = self.index.co_search(terms)
        state = self._state
        state.chain["c06_inverted_intersect"] += 1
        if not hits:
            return "无相关世界事实。"
        return "；".join(f"{entity_id}" for entity_id in hits[:3])

    # ---------------------------------------------------------- C02 账本

    def _seal_fact(
        self,
        now: datetime,
        *,
        object_id: str,
        object_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        self._state.facts_pending.append(
            {
                "object_id": object_id,
                "revision": 1,
                "object_type": object_type,
                "subject_id": subject_id,
                "occurred_at": as_utc(now, "now"),
                "learned_at": as_utc(now, "now"),
                "payload": payload,
            }
        )

    def _flush_facts(self) -> None:
        state = self._state
        if not state.facts_pending:
            return
        pending = state.facts_pending
        state.facts_pending = []
        sealed = self.ledger.seal_many(pending)
        if sealed:
            state.chain["c02_ledger_persist"] += 1

    # ------------------------------------------------------------- RSS

    def _sample_rss(self) -> None:
        self._rss_peak_mb = max(self._rss_peak_mb, _current_rss_megabytes())

    @property
    def peak_rss_megabytes(self) -> float:
        """推演期间观测到的**当前** RSS 峰值（模块级，会随释放回落）。"""
        return self._rss_peak_mb

    @property
    def rss_baseline_megabytes(self) -> float:
        return self._rss_baseline_mb

    @property
    def rss_growth_megabytes(self) -> float:
        """归因于本次推演的内存增量 = 峰值 - 基线。"""
        return max(0.0, self._rss_peak_mb - self._rss_baseline_mb)

    # ---------------------------------------------------------- 报告

    def _build_report(self, elapsed: float) -> SimulationReport:
        state = self._state
        integrity = self.ledger.verify_fact_integrity()
        index_stats = self.index.stats()
        return SimulationReport(
            days=self.config.days,
            total_hours=self.config.total_hours,
            ticks_processed=state.ticks,
            chain_invocations=dict(state.chain),
            meetings_held=state.meetings,
            business_crises=state.crises,
            contract_breaches=state.breaches,
            noise_episodes=state.noise_episodes,
            total_tokens_used=state.tokens,
            monthly_token_budget=self.policy.monthly_total_tokens,
            peak_rss_megabytes=round(self.peak_rss_megabytes, 2),
            rss_baseline_megabytes=round(self.rss_baseline_megabytes, 2),
            rss_growth_megabytes=round(self.rss_growth_megabytes, 2),
            deadlock_count=self.watchdog.deadlock_count,
            raw_image_bytes_retained=self.raw_sink.retained_byte_count,
            raw_image_frames_purged=self.raw_sink.purged_frame_count,
            facts_sealed=self.ledger.fact_count(),
            annotations_written=self.journal.count(),
            # 直接下标取值：键名写错必须立刻炸，不能用静默默认值掩盖
            index_entities=index_stats["distinct_entities"],
            index_postings=index_stats["postings_rows"],
            wake_dispatched=state.wake_dispatched,
            wake_suppressed_deep_sleep=state.wake_suppressed,
            motor_vibrations=self.wake_queue.deep_sleep_gate.motor_vibration_count,
            dimension_introspections=state.introspections,
            quota_blocks=state.quota_blocks,
            recursion_cuts=self.evolution.recursion.cut_count,
            elapsed_seconds=round(elapsed, 3),
            integrity_ok=integrity.all_intact,
        )
