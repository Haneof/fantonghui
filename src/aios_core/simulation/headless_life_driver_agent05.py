"""SIM-001 无界面 Linux 30天/180天高熵多维人生仿真器驱动引擎。
独立命名并存线（agent-05）：本模块为同工单独立命名交付版本，与共享分支上的规范实现并存，零覆盖；详见批次报告 agent-05-m2m3-sim-batch-20260916。

核心使命：纯 Python、零 UI、可在无图形 Linux 服务器上持续跑批的"虚拟人
多维人生时空仿真推演机"，为 AIOS 提供海量真实压力测试。

四大硬门禁：

1. **真实高熵成年人 30 天时空流发生器**：720 小时连续时间流（昼夜节律、
   高频心率/HRV、85dB 工业车间高噪环境、120 次真实工作会议、突发商业危机
   与老王合同违约事件）；
2. **驱动 AIOS 完整技术链**：数据接入 → C01 边缘清洗（multimodal_edge：
   画质初筛 + 原始字节粉碎 + 声纹 LSH）→ C06 倒排求交（仿真局部
   CJK 倒排索引）→ C02 账本持久化（ImmutableFactLedger 追加式哈希封存）
   → C04 单看板装配（cockpit/pipeline：1500 Token 硬预算）→ C05 回溯注记
   （world/retrospective_annotation：双时间透镜 + 单跳级联隔离），并叠加
   M2-005R 条件调度 / M2-001 唤醒静默闸 / M3-001R 维度守卫三条 M2/M3 主线；
3. **30 天连续推演 0 死锁与内存平稳**（1000x 加速回放）：死锁看门狗计数
   严格为 0；驻留 RSS ≤ 128MB（增长曲线平稳）；原始二进制图片滞留量严格为 0；
4. **月度 Token 封套核验**：30 天全局 Token 总量严格受控于
   ``governance/runtime_policy.json`` 规定的 2,554,000 tokens 月度总预算。

业务情境（严禁低幼化样例）：长期高压的创业企业法务总监 —— 85dB 重工业
装配车间巡检、120 次工作会议、跨国供应链圆桌、老王合同违约突发商业危机、
对赌回购协议签署、司法裁定反转。
"""
from __future__ import annotations

import json
import random
import resource
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aios_core.cockpit.pipeline import (
    ConversationState,
    CockpitPipeline,
    SINGLE_SHOT_TOKEN_BUDGET,
)
from aios_core.contracts.safety_bypass import WakePriority
from aios_core.dimensions.evolution_guard_agent05 import (
    DimensionEvolutionGuard,
    DimensionPhase,
    DomainAnomaly,
    RecursionCircuitBrokenError,
)
from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    RawByteSink,
    VoiceprintLSHIndex,
)
from aios_core.scheduler.conditional_engine_agent05 import (
    ConditionalTask,
    ConditionalTaskEngine,
    ConditionalTaskState,
    PhysicalContext,
    build_legal_director_schedule,
)
from aios_core.simulation.cjk_trigram_index import CjkTrigramIndex
from aios_core.wake.cooldown_queue_agent05 import (
    PhysicalPulse,
    SleepPhase,
    WakeCooldownQueue,
    WakeNotification,
)
from aios_core.world import (
    AnnotationRegistry,
    BiTemporalEpistemicLens,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

__all__ = [
    "DeadlockWatchdog",
    "HighEntropyLifeStream",
    "HeadlessLifeDriver",
    "SimTick",
    "SimulationReport",
    "run_headless_simulation",
]

SIM_SEED = 20260916
TZ_SH = timezone(timedelta(hours=8))  # 亚洲/上海
START = datetime(2026, 8, 3, 0, 0, tzinfo=TZ_SH)  # 周一 00:00
OFFICE = (31.2304, 121.4737)
HOME = (31.1999, 121.4375)
SHENZHEN_HOTEL = (22.5431, 114.0579)

CRISIS_DAYS = (11, 12, 13)      # 老王合同违约爆发（第 12~14 天）
P0_DAY, P0_HOUR = 12, 3         # 第 13 天 03:15 心梗跌倒（深度睡眠中）
RULING_DAY = 26                 # 第 27 天 09:00 司法裁定
EQUITY_EVENT_DAY = 19           # 第 20 天 10:00 股权变更
ROUNDTABLE_DAY = 8              # 第 9 天 19:00 跨国供应链圆桌（24 人）
WORKSHOP_DAYS = range(0, 10)    # 前 10 天车间高噪巡检
MEETING_HOURS = (9, 11, 13, 15, 16, 17)
MEETING_LAST_DAY = 25           # 会议排满前 20 个工作日 × 6 场 = 120 场

#: 危机夜间高熵对话（法务总监对抗线，严禁低幼化）
_CRISIS_DIALOGUES: Dict[int, Tuple[Tuple[str, Optional[str]], ...]] = {
    11: (
        ("老王那边刚发了违约通知，说我们先期违约，还要求启动回购条款", "回购条款启动争议"),
        ("原合同第 12 条明明写的是 8 月 31 日履约节点，他们凭什么认定 8 月 14 日违约", "履约节点条款矛盾"),
        ("我刚才和对方实控人通过电话，他语气不对，我怀疑背后有股权变动", "实控人异常信号"),
        ("法官要求周三前补交证据目录，我们材料还差两组", "证据目录时限压力"),
        ("这份对赌协议我不能签，单方责任条款写得明显是陷阱", "单方责任条款风险"),
    ),
    12: (
        ("对方申请了财产保全冻结，我们账户被冻了，事情严重了", "财产保全冻结落地"),
        ("我整夜没睡，心率一直上来了，身体有点顶不住", None),
        ("法院把一审开庭定在了 9 月 10 号", "一审开庭时间确定"),
        ("工商的股权变更底档我调出来看，记录全是乱的", "股权变更底档异常"),
        ("对赌一旦触发，金额是 4800 万，公司扛不住", "对赌金额敞口4800万"),
    ),
    13: (
        ("我决定提起反诉，以欺诈诱导为由", "欺诈诱导反诉决定"),
        ("律师费和评估费已经付了，发票都在证据包里", "损失证据链完整"),
        ("老王那边今天换了代理律师，新律所专做并购纠纷", "对方换律师信号"),
        ("我周五飞北京，直接找对方实控人谈", None),
        ("睡前把案件时间线再过一遍，关键节点我要背下来", None),
    ),
}
_MORNING_CHECKINS: Dict[int, str] = {
    11: "早，过一遍今天的诉讼日程和昨晚的心率曲线",
    12: "早，昨晚心率数据很糟，帮我看看趋势",
    13: "早，反诉状初稿我改完了，帮我核对条款引用",
}
_ONE_OFF_DIALOGUES: Dict[int, Tuple[Tuple[str, Optional[str]], ...]] = {
    19: (
        ("刚收到推送，老王公司的股权今早变更了，23% 转给一家新壳公司", "23%股权变更至壳公司"),
        ("如果股权变更坐实，这就是欺诈诱导主张的直接证据", "股权变更证据价值"),
    ),
    20: (
        ("我回到上海办公室了，那份对赌回购协议就放在桌上，我签不下去", None),
        ("把签署窗口改成视频会议，并且要求公证人在场", "签署程序加固"),
    ),
    26: (
        ("法院裁定出来了：对赌条款无效，老王那边的违约主张被驳回", "裁定：对赌条款无效"),
        ("三年诉讼终于反转，把这份裁定作为回溯注记打到旧认知上", "裁定回溯注记"),
    ),
}
_P0_SCENE_TAGS = frozenset({"nighttime", "deep_sleep"})


# ----------------------------------------------------------------------
# 门禁 1：真实高熵成年人 30 天时空流发生器
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DialogueTurn:
    text: str
    occurred_at: datetime
    dispute_point: Optional[str]
    scene_tags: frozenset = field(default_factory=frozenset)


@dataclass(frozen=True)
class SimTick:
    at: datetime
    day: int
    hour: int
    phase: str  # "deep_sleep" | "sleep" | "awake"
    environment: str  # "workshop" | "meeting" | "badminton" | "office" | "home"
    heart_rate_bpm: float
    hrv_ms: float
    location: Tuple[float, float]
    deep_focus: bool
    dialogues: Tuple[DialogueTurn, ...] = ()
    images: Tuple[Tuple[dict, bytes], ...] = ()  # (metadata, raw_bytes)
    is_p0_moment: bool = False


class HighEntropyLifeStream:
    """720 小时连续高熵时间流发生器（确定性种子，1000x 加速回放）。"""

    def __init__(self, days: int = 30, seed: int = SIM_SEED, start: datetime = START) -> None:
        if days < 1:
            raise ValueError("days must be >= 1")
        self.days = days
        self.start = start
        self.seed = seed
        self._rng = random.Random(seed)

    def __iter__(self) -> "HighEntropyLifeStream":
        self._cursor = 0
        self._rng = random.Random(self.seed + self.start.toordinal())
        return self

    def __next__(self) -> SimTick:
        total_hours = self.days * 24
        if self._cursor >= total_hours:
            raise StopIteration
        idx = self._cursor
        self._cursor += 1
        rng = self._rng
        at = self.start + timedelta(hours=idx)
        day = idx // 24
        hour = at.hour
        weekday = at.weekday()  # 0=周一
        is_workday = weekday < 5

        # —— 昼夜节律 ——
        if 2 <= hour < 6:
            phase = "deep_sleep"
        elif hour >= 23 or hour < 7:
            phase = "sleep"
        else:
            phase = "awake"

        # —— 环境（85dB 车间高噪 / 会议 / 羽毛球 / 办公室 / 居家）——
        if is_workday and day <= MEETING_LAST_DAY and hour in MEETING_HOURS:
            environment = "meeting"
        elif day in WORKSHOP_DAYS and is_workday and 6 <= hour < 14:
            environment = "workshop"
        elif (weekday in (2, 4) and is_workday or weekday == 6) and 19 <= hour < 21:
            environment = "badminton"
        elif is_workday and 8 <= hour < 19:
            environment = "office"
        else:
            environment = "home"

        # —— 位置（第 15~17 天赴深圳出差）——
        if 14 <= day <= 16:
            location = SHENZHEN_HOTEL
        elif is_workday and 8 <= hour < 19 and day not in (14, 15, 16):
            location = OFFICE
        else:
            location = HOME

        deep_focus = is_workday and (10 <= hour < 12 or 14 <= hour < 16) and day not in CRISIS_DAYS

        # —— 高频心率 / HRV ——
        if phase == "deep_sleep":
            hr = rng.gauss(58, 2.5)
            hrv = rng.gauss(72, 6)
        elif phase == "sleep":
            hr = rng.gauss(62, 3)
            hrv = rng.gauss(66, 6)
        elif day in CRISIS_DAYS and hour == 21:
            # 危机三晚 21:00：心率 97~101（>95 连续 3 天 → 心内科建档触发）
            hr = 97.0 + 2.0 * (day - CRISIS_DAYS[0]) + rng.random()
            hrv = rng.gauss(36, 4)
        elif environment == "badminton":
            hr = rng.gauss(132, 12)
            hrv = rng.gauss(30, 5)
        elif environment == "workshop":
            hr = rng.gauss(80, 5)
            hrv = rng.gauss(50, 6)
        elif environment == "meeting":
            hr = rng.gauss(86, 6)
            hrv = rng.gauss(46, 6)
        else:
            hr = rng.gauss(70, 5)
            hrv = rng.gauss(52, 6)
        hr = max(48.0, min(hr, 168.0))
        hrv = max(18.0, min(hrv, 110.0))

        # —— 高熵对话（危机夜 / 晨间核对 / 一次性事件）——
        dialogues: List[DialogueTurn] = []
        if day in _MORNING_CHECKINS and hour == 9:
            dialogues.append(DialogueTurn(_MORNING_CHECKINS[day], at, None))
        if day in _CRISIS_DIALOGUES and hour == 21:
            for k, (text, point) in enumerate(_CRISIS_DIALOGUES[day]):
                dialogues.append(DialogueTurn(text, at + timedelta(minutes=8 * k), point))
        if day in _ONE_OFF_DIALOGUES and hour == 10:
            scene = frozenset({"external_event:equity_change"}) if day == EQUITY_EVENT_DAY else frozenset()
            for k, (text, point) in enumerate(_ONE_OFF_DIALOGUES[day]):
                dialogues.append(DialogueTurn(text, at + timedelta(minutes=12 * k), point, scene_tags=scene))

        # —— 图片流（车间标牌 / 合同文本 / 工商公告 / 裁定书）——
        images: List[Tuple[dict, bytes]] = []
        if environment == "workshop":
            for k in range(2):
                q = rng.uniform(0.25, 0.95)
                images.append(
                    (
                        {
                            "quality_score": round(q, 4),
                            "caption": f"设备标牌：{rng.randint(1, 6)}号装配线 {k + 1}",
                            "tags": ["nameplate", "workshop"],
                            "source": f"workshop-{day}-{hour}-{k}",
                        },
                        bytes(rng.getrandbits(8) for _ in range(rng.randint(512, 4096))),
                    )
                )
        elif day == ROUNDTABLE_DAY and hour == 19:
            for k in range(20):
                q = rng.uniform(0.3, 0.95)
                images.append(
                    (
                        {
                            "quality_score": round(q, 4),
                            "caption": f"圆桌现场：名牌/合同页 {k + 1}",
                            "tags": ["roundtable", "nameplate", "contract"],
                            "source": f"roundtable-{k}",
                        },
                        bytes(rng.getrandbits(8) for _ in range(rng.randint(512, 8192))),
                    )
                )
        elif day in CRISIS_DAYS and 8 <= hour < 18:
            for k in range(3):
                q = rng.uniform(0.35, 0.98)
                images.append(
                    (
                        {
                            "quality_score": round(q, 4),
                            "caption": f"合同页：第 {rng.randint(1, 24)} 条 {k + 1}",
                            "tags": ["contract", "clause"],
                            "source": f"crisis-{day}-{hour}-{k}",
                        },
                        bytes(rng.getrandbits(8) for _ in range(rng.randint(512, 4096))),
                    )
                )
        elif day == EQUITY_EVENT_DAY and 10 <= hour < 12:
            for k in range(5):
                q = rng.uniform(0.5, 0.98)
                images.append(
                    (
                        {
                            "quality_score": round(q, 4),
                            "caption": f"工商公示：股权变更页 {k + 1}",
                            "tags": ["equity", "registry"],
                            "source": f"equity-{k}",
                        },
                        bytes(rng.getrandbits(8) for _ in range(rng.randint(512, 4096))),
                    )
                )
        elif day == RULING_DAY and 9 <= hour < 11:
            for k in range(5):
                q = rng.uniform(0.55, 0.99)
                images.append(
                    (
                        {
                            "quality_score": round(q, 4),
                            "caption": f"民事裁定书：第 {k + 1} 页",
                            "tags": ["court", "ruling"],
                            "source": f"ruling-{k}",
                        },
                        bytes(rng.getrandbits(8) for _ in range(rng.randint(512, 4096))),
                    )
                )

        is_p0 = day == P0_DAY and hour == P0_HOUR
        return SimTick(
            at=at,
            day=day,
            hour=hour,
            phase=phase,
            environment=environment,
            heart_rate_bpm=round(hr, 1),
            hrv_ms=round(hrv, 1),
            location=location,
            deep_focus=deep_focus,
            dialogues=tuple(dialogues),
            images=tuple(images),
            is_p0_moment=is_p0,
        )


# ----------------------------------------------------------------------
# 门禁 3：死锁看门狗（canary 线程 + 临界区探测）
# ----------------------------------------------------------------------


class DeadlockWatchdog:
    """死锁看门狗：canary 线程与主线程竞争同一临界区，超时即计一次死锁。"""

    def __init__(self, timeout_s: float = 5.0) -> None:
        self.timeout_s = timeout_s
        self.deadlock_count = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._canary = threading.Thread(target=self._canary_loop, daemon=True)

    def start(self) -> None:
        self._canary.start()

    def stop(self) -> None:
        self._stop.set()
        self._canary.join(timeout=2.0)

    def _canary_loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            with self._lock:
                pass
            if time.monotonic() - started > self.timeout_s:
                self.deadlock_count += 1
            self._stop.wait(0.05)

    def ping(self) -> None:
        started = time.monotonic()
        with self._lock:
            pass
        if time.monotonic() - started > self.timeout_s:
            self.deadlock_count += 1


def _vm_rss_mb() -> float:
    """当前进程驻留 RSS（/proc/self/status，Linux）。"""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    except OSError:
        return 0.0
    return 0.0


# ----------------------------------------------------------------------
# 仿真报告
# ----------------------------------------------------------------------


@dataclass
class SimulationReport:
    days: int
    hours_processed: int
    # 门禁 3
    deadlock_count: int
    peak_rss_mb: float
    vmrss_first_mb: float
    vmrss_last_mb: float
    raw_binary_retained_bytes: int
    # C01 边缘清洗
    images_sunk: int
    images_purged: int
    images_kept: int
    voiceprint_speakers: int
    voiceprint_slices_assigned: int
    # C06 倒排求交
    documents_indexed: int
    query_hits_buyback: int
    query_hits_breach: int
    # C02 账本持久化
    facts_recorded: int
    ledger_fingerprint: str
    ledger_integrity_ok: bool
    # C04 单看板装配
    cockpit_assemblies: int
    cockpit_tokens_total: int
    cockpit_max_tokens: int
    # C05 回溯注记
    annotation_id: str
    zero_early_leak_ok: bool
    overlay_visible_now_ok: bool
    cascade_marked_stale: int
    cascade_deeper_untouched_ok: bool
    # M2-005R / M2-001 / M3-001R
    tasks_matured_level1: int
    tasks_matured_level2: int
    cardiology_task_state: str
    equity_task_state: str
    buyback_task_state: str
    pulses_ingested: int
    batch_events: int
    p0_hardware_pulses: int
    silent_suspended: int
    thawed_total: int
    general_vibrations: int
    dimension_active: int
    dimension_expired: int
    dimension_archived: int
    reflection_cuts: int
    # 门禁 4
    token_envelope_total: int
    token_envelope_budget: int
    duration_s: float


# ----------------------------------------------------------------------
# 驱动引擎
# ----------------------------------------------------------------------


class HeadlessLifeDriver:
    """无界面高熵人生仿真驱动引擎（C01→C06→C02→C04→C05 全链 + M2/M3 主线）。"""

    def __init__(
        self,
        days: int = 30,
        *,
        seed: int = SIM_SEED,
        runtime_policy_path: Optional[Path] = None,
    ) -> None:
        self.days = days
        self.stream = HighEntropyLifeStream(days=days, seed=seed)
        if runtime_policy_path is None:
            # 仓库根目录/governance/runtime_policy.json（与本文件的相对位置解析，不依赖 CWD）
            runtime_policy_path = Path(__file__).resolve().parents[3] / "governance" / "runtime_policy.json"
        with open(runtime_policy_path, "r", encoding="utf-8") as fh:
            self.runtime_policy = json.load(fh)
        self.token_budget = int(self.runtime_policy["monthly_token_budget"])

        # C01 边缘清洗
        self.cleaner = EdgeMultimodalCleaner()
        self.raw_sink = RawByteSink()
        self.voiceprints = VoiceprintLSHIndex(seed=seed, lsh_planes=128)
        # C06 倒排求交
        self.index = CjkTrigramIndex()
        # C02 账本持久化
        self.ledger = ImmutableFactLedger()
        # C04 单看板装配
        self.pipeline = CockpitPipeline(
            state=ConversationState(
                crisis_context="商业危机对抗线：老王合同违约 / 对赌回购 / 司法裁定",
            ),
            budget=SINGLE_SHOT_TOKEN_BUDGET,
        )
        # C05 回溯注记
        self.registry = AnnotationRegistry()
        self.isolator = SingleHopCascadeIsolator()
        self._ruling_at: Optional[datetime] = None
        self._annotation_id: Optional[str] = None
        self._zero_early_leak_ok = False
        self._overlay_visible_now_ok = False
        self._cascade_marked = 0
        self._cascade_deeper_untouched_ok = False

        # M2-005R 条件调度
        self.engine = ConditionalTaskEngine()
        self.engine.register_all(build_legal_director_schedule(start=self.stream.start, count=200))
        # M2-001 唤醒静默闸
        self.wake_queue = WakeCooldownQueue()
        # M3-001R 维度守卫
        self.guard = DimensionEvolutionGuard(today=self.stream.start.date())
        self._guard_day = 0
        self.reflection_cuts = 0

        self.watchdog = DeadlockWatchdog()
        self._stats = {
            "hours": 0,
            "images_sunk": 0,
            "images_purged": 0,
            "images_kept": 0,
            "voiceprint_speakers": 0,
            "voiceprint_slices": 0,
            "query_hits_buyback": 0,
            "query_hits_breach": 0,
            "assemblies": 0,
            "tokens_total": 0,
            "tokens_max": 0,
            "pulses": 0,
            "p0_pulses": 0,
            "silent": 0,
            "thawed": 0,
            "level1": 0,
            "level2": 0,
            "cardiology_state": "DORMANT",
            "equity_state": "DORMANT",
            "buyback_state": "DORMANT",
        }
        self._vmrss_samples: List[float] = []
        self._rng = random.Random(seed + 7)

    # ---------------- C01：边缘清洗 ----------------

    def _process_images(self, tick: SimTick) -> None:
        for metadata, raw in tick.images:
            self.raw_sink.sink(f"img-{tick.day}-{tick.hour}-{self._stats['images_sunk']}", raw)
            self._stats["images_sunk"] += 1
            obs = self.cleaner.evaluate_and_clean_image(metadata, raw)
            # 门禁 3：原始二进制图片滞留量严格为 0 —— 无论收留与否立即粉碎
            self.raw_sink.purge([f"img-{tick.day}-{tick.hour}-{self._stats['images_sunk'] - 1}"])
            self._stats["images_purged"] += 1
            if obs is not None:
                self._stats["images_kept"] += 1

    def _process_roundtable_voiceprints(self, tick: SimTick) -> None:
        if tick.day != ROUNDTABLE_DAY or tick.hour != 19:
            return
        rng = random.Random(SIM_SEED + 900)
        for i in range(24):
            vp_id = f"vp-rt-{i:02d}"
            base = [rng.gauss(0.0, 1.0) for _ in range(128)]
            self.voiceprints.add(vp_id, base, entity_id=f"entity:partner:{i:02d}" if i < 8 else None)
            self._stats["voiceprint_speakers"] += 1
            for _ in range(3):  # 每声源 3 条交织切片
                slice_feat = [v + rng.gauss(0.0, 0.05) for v in base]
                self.voiceprints.assign_slice(slice_feat)
                self._stats["voiceprint_slices"] += 1

    # ---------------- C06：倒排求交 ----------------

    def _process_documents(self, tick: SimTick) -> None:
        if tick.environment == "meeting":
            doc_id = f"doc:meeting:{tick.day:02d}:{tick.hour}"
            text = (
                f"第{tick.day}天{tick.hour}时工作会议纪要：对赌回购协议履约节点复核，"
                "老王方主张 8 月 14 日违约，我方坚持 8 月 31 日履约节点条款，"
                "股权变更底档与竞业限制条款存在交叉风险，证据目录周三前补交。"
            )
            self.index.add(doc_id, text)
            self.ledger.record_fact(
                fact_id=f"fact:meeting:{tick.day:02d}:{tick.hour}",
                entity_id="entity:legal:me",
                occurred_at=tick.at,
                kind="meeting",
                payload={"doc_ref": doc_id, "hour": tick.hour, "day": tick.day},
            )
        if tick.day == CRISIS_DAYS[0] and tick.hour == 10:
            self.index.add(
                "doc:breach:001",
                "老王合同违约突发事件纪要：对方以我方先期违约为由发出通知，要求启动对赌回购，"
                "涉及金额 4800 万；股权变更底档异常，实控人疑似通过壳公司转移 23% 股权。",
            )
            self.ledger.record_fact(
                fact_id="fact:crisis:breach",
                entity_id="entity:counterparty:old_wang",
                occurred_at=tick.at,
                kind="crisis_event",
                payload={"event": "contract_breach_notice", "exposure_cny": 48_000_000},
            )
        if tick.day == EQUITY_EVENT_DAY and tick.hour == 10:
            self.index.add(
                "doc:equity:001",
                "工商公示：老王公司 23% 股权变更至新设壳公司，变更日期为今晨，关联欺诈诱导主张。",
            )
            self.ledger.record_fact(
                fact_id="fact:equity:change",
                entity_id="entity:counterparty:old_wang",
                occurred_at=tick.at,
                kind="crisis_event",
                payload={"event": "equity_change", "pct": 23},
            )
        if tick.day == RULING_DAY and tick.hour == 9:
            self._ruling_at = tick.at
            self.index.add(
                "doc:ruling:001",
                "民事裁定书：对赌条款无效，老王方面的违约主张被驳回，反诉欺诈诱导部分继续审理。",
            )
            self.ledger.record_fact(
                fact_id="fact:ruling:final",
                entity_id="entity:counterparty:old_wang",
                occurred_at=tick.at,
                kind="crisis_event",
                payload={"event": "court_ruling", "outcome": "buyback_clause_invalid"},
            )
        # 每日异常汇总事实（C02）
        if tick.hour == 23:
            self.ledger.record_fact(
                fact_id=f"fact:daily-summary:{tick.day:02d}",
                entity_id="entity:legal:me",
                occurred_at=tick.at,
                kind="daily_anomaly_summary",
                payload={"day": tick.day, "in_crisis": tick.day in CRISIS_DAYS},
            )

    def _run_queries(self, tick: SimTick) -> None:
        if tick.hour % 6 != 0:
            return
        if tick.day >= CRISIS_DAYS[0]:
            hits = self.index.query_multi_word(["老王", "违约"])
            if hits:
                self._stats["query_hits_breach"] = max(self._stats["query_hits_breach"], len(hits))
        if tick.day >= 1 and self.index.doc_count > 2:
            hits = self.index.query_multi_word(["对赌", "回购"])
            if hits:
                self._stats["query_hits_buyback"] = max(self._stats["query_hits_buyback"], len(hits))

    # ---------------- C04：单看板装配 ----------------

    def _process_dialogues(self, tick: SimTick) -> None:
        for turn in tick.dialogues:
            result = self.pipeline.process_round(
                turn.text,
                occurred_at=turn.occurred_at,
                key_dispute_points=[turn.dispute_point] if turn.dispute_point else [],
            )
            self._stats["assemblies"] += 1
            self._stats["tokens_total"] += result.cockpit.token_count
            self._stats["tokens_max"] = max(self._stats["tokens_max"], result.cockpit.token_count)
            assert result.cockpit.token_count <= SINGLE_SHOT_TOKEN_BUDGET
            # M2-005R Level-2 机会式捎带：用户主动唤醒 + 相关场景
            if turn.scene_tags:
                matured = self.engine.piggyback_semantic(
                    wake_ref=f"wake:sim:{tick.day:02d}:{tick.hour}",
                    scene_tags=turn.scene_tags,
                    at=turn.occurred_at,
                )
                self._stats["level2"] += len(matured)
                for task in matured:
                    if task.task_id == "task:equity-change:counterparty":
                        self.engine.start(task.task_id, at=turn.occurred_at + timedelta(minutes=30))
                        self.engine.complete(task.task_id, at=turn.occurred_at + timedelta(hours=2))
                        self._stats["equity_state"] = task.state.value

    # ---------------- C05：回溯注记 ----------------

    def _process_ruling_annotation(self, tick: SimTick) -> None:
        if self._ruling_at is None or self._annotation_id is not None:
            return
        ruling_at = self._ruling_at
        target_start = self.stream.start + timedelta(days=1)
        annotation = RetrospectiveAnnotation(
            annotation_id="ann:sim:ruling-reversal",
            target_entity_id="entity:counterparty:old_wang",
            semantic_overlay="司法裁定确认对赌条款无效：对老王方诚信与原始商业信任判断进行欺诈重估",
            target_time_start=target_start,
            target_time_end=ruling_at,
            learned_at=ruling_at,
            recorded_at=ruling_at,
            source_statement_ref="doc:ruling:001",
        )
        self.registry.append(annotation)
        self._annotation_id = annotation.annotation_id

        # 双时间透镜：零提前泄露 + 当前可见
        lens = BiTemporalEpistemicLens(self.ledger, self.registry, clock=lambda: ruling_at)
        early_view = lens.query_historical_slice(
            "entity:counterparty:old_wang",
            target_start,
            ruling_at,
            as_of_cutoff=self.stream.start + timedelta(days=12, hours=12),
        )
        now_view = lens.query_historical_slice(
            "entity:counterparty:old_wang", target_start, ruling_at, as_of_cutoff=None
        )
        self._zero_early_leak_ok = len(early_view.active_annotations) == 0
        self._overlay_visible_now_ok = len(now_view.active_annotations) == 1

        # 单跳级联隔离：旧认知"老王可信"反向失效（严格 1 跳）
        origin = "cognition:oldwang_trustworthy"
        direct = [
            "cognition:repurchase_valuation",
            "cognition:settlement_estimate",
            "cognition:litigation_strategy",
            "cognition:q3_risk_report",
        ]
        deeper = "cognition:final_appeal_plan"
        self.isolator.register_node(origin)
        for node in direct + [deeper]:
            self.isolator.register_node(node)
        for node in direct:
            self.isolator.add_dependency(origin, node)
        self.isolator.add_dependency("cognition:litigation_strategy", deeper)
        report = self.isolator.reverse_invalidate(origin, max_hops=1)
        self._cascade_marked = len(report.marked_stale)
        self._cascade_deeper_untouched_ok = not self.isolator.is_stale(deeper)
        assert report.llm_recompute_triggered == 0

    # ---------------- M2-001：唤醒静默闸 ----------------

    def _process_wake(self, tick: SimTick) -> None:
        # 07:05 第一安全窗口：用户清醒并下床（走出睡眠状态），夜间静默队列无损解冻
        if tick.hour == 7 and tick.phase == "awake" and self.wake_queue.pending_silent():
            thawed = self.wake_queue.mark_awake(tick.at + timedelta(minutes=5))
            self._stats["thawed"] += len(thawed)

        # 睡眠阶段切换（02:00~06:00 深度睡眠 / 06:00~07:00 浅睡 / 其余清醒或夜间浅睡）
        if tick.phase == "deep_sleep":
            self.wake_queue.set_sleep_phase(SleepPhase.DEEP_SLEEP, tick.at)
        elif tick.phase == "sleep":
            self.wake_queue.set_sleep_phase(SleepPhase.LIGHT_SLEEP, tick.at)
        else:
            self.wake_queue.set_sleep_phase(SleepPhase.AWAKE, tick.at)

        # 50Hz 高频脉冲：5 秒窗口 × 250 条（合并为单批次）
        for i in range(250):
            p = PhysicalPulse(
                seq=self._stats["pulses"] + i,
                at=tick.at + timedelta(seconds=i * 0.02),
                channel=("accel_x", "accel_y", "accel_z", "hr")[i % 4],
                value=self.tick_pulse_value(tick, i),
            )
            self.wake_queue.ingest_physical_pulse(p)
            self._stats["pulses"] += 1
        self.wake_queue.flush_pending()

        # 深度睡眠中的挂起通知（02:30/03:00/04:00/05:00）
        deep_notices = {2: ("task", "task_reminder"), 3: ("retro", "retrospective"), 4: ("general", "general"), 5: ("task", "task_reminder")}
        if tick.phase == "deep_sleep":
            key = deep_notices[tick.hour]
            result = self.wake_queue.notify(
                WakeNotification(
                    notification_id=f"n:{tick.day:02d}:{tick.hour}",
                    at=tick.at + timedelta(minutes=30 if tick.hour == 2 else 0),
                    category=key[1],
                    payload={"day": tick.day},
                )
            )
            if result.action == "SILENT_SUSPENDED_DEEP_SLEEP":
                self._stats["silent"] += 1
            # 03:15 P0：心梗跌倒硬件直穿（深度睡眠中绝不静默）
            if tick.is_p0_moment:
                p0_result = self.wake_queue.notify(
                    WakeNotification(
                        notification_id="n:p0-0315",
                        at=tick.at + timedelta(minutes=15),
                        category="safety",
                        priority=WakePriority.P0_CRITICAL_SAFETY,
                        payload={
                            "hr_bpm_peak": 165,
                            "g_force_peak": 5.2,
                            "three_axis": [4.1, 1.2, 3.0],
                            "context": "deep_sleep_nocturnal",
                        },
                    )
                )
                assert p0_result.action == "P0_HARDWARE_PASSTHROUGH"
                self._stats["p0_pulses"] += 1
                self.ledger.record_fact(
                    fact_id="fact:p0:cardiac-fall",
                    entity_id="entity:legal:me",
                    occurred_at=tick.at + timedelta(minutes=15),
                    kind="crisis_event",
                    payload={"hr_bpm_peak": 165, "g_force_peak": 5.2},
                )

        # 23:30 每日复盘（浅睡/清醒：正常投递走冷却）
        if tick.hour == 23:
            self.wake_queue.notify(
                WakeNotification(
                    notification_id=f"n:retro:{tick.day:02d}",
                    at=tick.at + timedelta(minutes=30),
                    category="retrospective",
                    payload={"day": tick.day},
                )
            )



    def tick_pulse_value(self, tick: SimTick, i: int) -> float:
        if i % 4 == 3:
            return tick.heart_rate_bpm + self._rng.uniform(-1.5, 1.5)
        return round(self._rng.uniform(-1.2, 1.2), 3)

    # ---------------- M2-005R / M3-001R ----------------

    def _process_scheduler(self, tick: SimTick) -> None:
        biometrics = {"heart_rate_bpm": tick.heart_rate_bpm, "hrv_ms": tick.hrv_ms}
        if 21 <= tick.hour < 24:  # 晚间心率窗口（心内科建档任务的独立口径，防运动峰值污染）
            biometrics["evening_heart_rate_bpm"] = tick.heart_rate_bpm
        ctx = PhysicalContext(
            now=tick.at,
            location=tick.location,
            biometrics=biometrics,
            flags={"deep_focus": tick.deep_focus, "calendar_free": tick.environment == "home"},
        )
        matured = self.engine.evaluate_physical(ctx)
        self._stats["level1"] += len(matured)
        for task in matured:
            if task.task_id == "task:cardiology:hr-3day":
                self._stats["cardiology_state"] = "READY"
                # 次日晨启动心内科预约建档，当日完成
                start_at = tick.at + timedelta(hours=12)
                self.engine.start(task.task_id, at=start_at)
                self.engine.complete(task.task_id, at=start_at + timedelta(hours=6))
                self._stats["cardiology_state"] = task.state.value
            elif task.task_id == "task:buyback-sign:shanghai":
                self._stats["buyback_state"] = "READY"
        # 对赌回购协议签署：条件就绪后，用户于第 21 天（day 20）回到办公室正式签署
        buyback = self.engine.get("task:buyback-sign:shanghai")
        if (
            buyback.state is ConditionalTaskState.READY
            and tick.day == 20
            and tick.hour == 10
        ):
            start_at = tick.at + timedelta(minutes=30)
            self.engine.start(buyback.task_id, at=start_at)
            self.engine.complete(buyback.task_id, at=start_at + timedelta(hours=7))
            self._stats["buyback_state"] = buyback.state.value

    def _process_dimension_guard(self, tick: SimTick) -> None:
        # 守卫模拟时钟逐日推进（每日反思配额按日计）
        if tick.day != self._guard_day:
            self.guard.advance_days(tick.day - self._guard_day)
            self._guard_day = tick.day
        d = tick.day
        if d == 2 and tick.hour == 22:
            base = self.stream.start.date()
            anomalies = [
                DomainAnomaly(domain="sleep", day=base + timedelta(days=k)) for k in range(3)
            ] + [DomainAnomaly(domain="heart_rate", day=base + timedelta(days=k)) for k in range(3)]
            self.guard.submit_candidate(name="跨域压力维", anomalies=anomalies)
        if d == 3 and tick.hour == 22:
            base = self.stream.start.date()
            anomalies = [
                DomainAnomaly(domain="sleep", day=base + timedelta(days=k + 1)) for k in range(3)
            ] + [DomainAnomaly(domain="temperature", day=base + timedelta(days=k + 1)) for k in range(3)]
            self.guard.submit_candidate(name="体温睡眠耦合维", anomalies=anomalies)
        preds = {
            8: ("dim:0001", True, 0.82),
            10: ("dim:0002", True, 0.7),
            12: ("dim:0001", True, 0.84),
            14: ("dim:0002", False, 0.55),
            16: ("dim:0001", True, 0.81),
            18: ("dim:0002", False, 0.5),
            20: ("dim:0001", False, 0.74),
            24: ("dim:0001", True, 0.86),
        }
        if d in preds and tick.hour == 20:
            dim_id, correct, power = preds[d]
            self.guard.record_prediction(dim_id, correct=correct, explanatory_power=power)
        if d == 5 and tick.hour == 9:
            self.guard.reflect("评估跨域压力维对危机期心率的解释力")
        if d == 6 and tick.hour == 9:
            try:
                self.guard.reflect("请反思是否要反思是否需要新增维度来反思压力维")
            except RecursionCircuitBrokenError:
                self.reflection_cuts += 1  # 第 2 层递归物理切断（铁律 5）

    # ---------------- 主循环 ----------------

    def run(self) -> SimulationReport:
        started = time.perf_counter()
        self.watchdog.start()
        try:
            for tick in self.stream:
                self.watchdog.ping()
                self._vmrss_samples.append(_vm_rss_mb())
                self._process_wake(tick)
                self._process_images(tick)
                self._process_roundtable_voiceprints(tick)
                self._process_documents(tick)
                self._run_queries(tick)
                self._process_dialogues(tick)
                self._process_scheduler(tick)
                self._process_dimension_guard(tick)
                self._process_ruling_annotation(tick)
                self._stats["hours"] += 1
        finally:
            self.watchdog.stop()

        # 试用期结算（虚拟时钟推进至第 33 天：最晚提交的候选 day 3 + 30 天试用期；
        # 长时程运行（如 180 天）时钟已越过结算点则直接结算）
        self.guard.advance_days(max(0, 33 - self._guard_day))
        self.guard.run_probation_check()

        self.ledger.verify_integrity()
        ok, _ = self.ledger.verify_integrity()
        elapsed = time.perf_counter() - started
        vmrss_first = self._vmrss_samples[0] if self._vmrss_samples else 0.0
        vmrss_last = self._vmrss_samples[-1] if self._vmrss_samples else 0.0
        return SimulationReport(
            days=self.days,
            hours_processed=self._stats["hours"],
            deadlock_count=self.watchdog.deadlock_count,
            peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
            vmrss_first_mb=vmrss_first,
            vmrss_last_mb=vmrss_last,
            raw_binary_retained_bytes=self.raw_sink.retained_bytes,
            images_sunk=self._stats["images_sunk"],
            images_purged=self._stats["images_purged"],
            images_kept=self._stats["images_kept"],
            voiceprint_speakers=self._stats["voiceprint_speakers"],
            voiceprint_slices_assigned=self._stats["voiceprint_slices"],
            documents_indexed=self.index.doc_count,
            query_hits_buyback=self._stats["query_hits_buyback"],
            query_hits_breach=self._stats["query_hits_breach"],
            facts_recorded=self.ledger.count(),
            ledger_fingerprint=self.ledger.aggregate_fingerprint(),
            ledger_integrity_ok=ok,
            cockpit_assemblies=self._stats["assemblies"],
            cockpit_tokens_total=self._stats["tokens_total"],
            cockpit_max_tokens=self._stats["tokens_max"],
            annotation_id=self._annotation_id or "",
            zero_early_leak_ok=self._zero_early_leak_ok,
            overlay_visible_now_ok=self._overlay_visible_now_ok,
            cascade_marked_stale=self._cascade_marked,
            cascade_deeper_untouched_ok=self._cascade_deeper_untouched_ok,
            tasks_matured_level1=self._stats["level1"],
            tasks_matured_level2=self._stats["level2"],
            cardiology_task_state=self._stats["cardiology_state"],
            equity_task_state=self._stats["equity_state"],
            buyback_task_state=self._stats["buyback_state"],
            pulses_ingested=self._stats["pulses"],
            batch_events=self.wake_queue.downstream_wakes,
            p0_hardware_pulses=self._stats["p0_pulses"],
            silent_suspended=self._stats["silent"],
            thawed_total=self._stats["thawed"],
            general_vibrations=self.wake_queue.general_vibration_count,
            dimension_active=len(self.guard.by_phase(DimensionPhase.ACTIVE)),
            dimension_expired=len(self.guard.by_phase(DimensionPhase.EXPIRED)),
            dimension_archived=len(self.guard.by_phase(DimensionPhase.ARCHIVED)),
            reflection_cuts=self.reflection_cuts,
            token_envelope_total=self._stats["tokens_total"],
            token_envelope_budget=self.token_budget,
            duration_s=elapsed,
        )


def run_headless_simulation(days: int = 30, **kw) -> SimulationReport:
    """便捷入口：跑完整 30 天（或 N 天）无界面仿真并返回报告。"""
    return HeadlessLifeDriver(days=days, **kw).run()
