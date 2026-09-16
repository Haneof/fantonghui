"""端侧原始流提纯引擎（Edge Stream Purifier，阶段一核心算子）。

宪法依据
--------
* 第三十三条第 1 款：IMU 严禁 50Hz 高频时序直写数据库；心率平稳期只留时段均值，
  重大异常波动独立成 Observation；
* 第三十三条第 2/3 款：图像只留文本 Caption，原始大图绝不落库；语音转文本并绑定
  声纹编号，未绑定声纹满 180 天淘汰；
* 第三十三条第 5 款 + 第十五条第 14 款（铁律 4）：大模型在每日复盘中自主研判，
  **物理删除**商圈叫卖、垃圾短信等环境噪声，但核心合同承诺、关键争议原话与事件
  证据链 **100% 永存**。

设计要点
--------
1. 本模块是"原始世界 → 世界模型"之间的**唯一提纯闸门**：上游是百万级原始采样流
   （IMU / 心率 / 视觉 / 音频 / 文本），下游是数量级收敛的宏观 Observation。
2. 高频压缩复用 :class:`AdaptiveTemporalCompressor`（误差有界、冲击保真），
   本模块只负责"把压缩段翻译成宪法语义的宏观观察"。
3. 淘汰决策由 :class:`RetentionAdjudicator` 承担：它是**大模型清洗权的可复现代理**
   —— 打分规则公开、可审计、可被测试独立复核；且**证据链保护优先于一切打分**：
   任何被 EventAnchor / EvidenceSet / Claim 引用的观察，无论文本多像噪声，永不可删。
4. 删除动作本身也留痕：:class:`PurgeLedger` 记录哈希链，删除可审计、可追责，
   而"删"只走 storage 层既有的 append-only tombstone 通道（宪法 33.5：世界对象
   没有物理 DELETE，只有 tombstone 修订 + 冷档归档；对端侧而言等于噪声原话
   从活跃世界物理消失，历史真相表的不可变性同时得到保全）。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.cognition.model_call_meter import ModelCallMeter
from aios_core.contracts.enums import ObjectType, SourceClass
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import Claim, Entity, EventAnchor, EvidenceSet, Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    RawByteSink,
    VoiceprintLSHIndex,
    VoiceprintProfile,
    VoiceprintTTLRegistry,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.tools.adaptive_temporal_compressor import (
    AdaptiveTemporalCompressor,
    CompressionResult,
)

UTC = timezone.utc

__all__ = [
    "DailyReviewReport",
    "EdgePurifierPolicy",
    "EdgePurifyReport",
    "EdgeStreamPurifier",
    "PurgeLedger",
    "PurgeLedgerEntry",
    "RawAudioSlice",
    "RawEnvironmentText",
    "RawHeartSample",
    "RawImuSample",
    "RawVisionFrame",
    "RetentionAdjudicator",
    "RetentionDecision",
    "RetentionVerdict",
]


def _us(ts: datetime) -> int:
    return int(ts.timestamp() * 1_000_000)


def _dt(us: int) -> datetime:
    return datetime.fromtimestamp(us / 1_000_000, tz=UTC)


# ---------------------------------------------------------------------------
# 原始样本契约（百万级流的搬运单位，均为不可变值对象）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawImuSample:
    """50Hz IMU 原始采样（宪法明令禁止直写数据库）。"""

    t_us: int
    ax: float
    ay: float
    az: float
    gyro_mag: float = 0.0

    @property
    def magnitude(self) -> float:
        return math.sqrt(self.ax * self.ax + self.ay * self.ay + self.az * self.az)


@dataclass(frozen=True, slots=True)
class RawHeartSample:
    """心率/HRV 原始采样（1Hz 级别）。"""

    t_us: int
    bpm: float
    hrv_ms: float = 0.0
    pvc_count: int = 0


@dataclass(frozen=True, slots=True)
class RawVisionFrame:
    """手环抓拍帧（原始字节只允许在端侧内存暂存，随即粉碎）。"""

    frame_id: str
    t_us: int
    caption: str
    tags: tuple[str, ...] = ()
    raw_bytes: bytes = b""
    mean_luma: float = 128.0
    high_freq_energy: float = 0.6
    motion_magnitude: float = 0.1


@dataclass(frozen=True, slots=True)
class RawAudioSlice:
    """外界录音切片（转写文本 + 128 维声纹特征 + 声纹槽位）。"""

    slice_id: str
    t_us: int
    transcript: str
    speaker_slot: str = "P000"
    voiceprint_feature: tuple[float, ...] = ()
    ambient_db: float = 45.0
    duration_ms: int = 3000
    bound_entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class RawEnvironmentText:
    """文本环境流（聊天、合同、短信、叫卖等）。"""

    event_id: str
    t_us: int
    channel: str
    text: str


# ---------------------------------------------------------------------------
# 淘汰裁决（大模型每日复盘清洗权的可复现代理）
# ---------------------------------------------------------------------------


class RetentionVerdict(StrEnum):
    KEEP = "keep"
    NOISE = "noise"
    UNSURE = "unsure"


class RetentionDecision(BaseModel):
    """单条文本的淘汰裁决（含打分理由，可被审计独立复核）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: RetentionVerdict
    score: float
    reasons: tuple[str, ...]
    protected_by: str | None = None
    evidence_hits: tuple[str, ...] = ()
    noise_hits: tuple[str, ...] = ()


#: 证据性标记：命中即视为"核心事实 / 关键原话 / 承诺"的强信号。
EVIDENCE_MARKERS: tuple[str, ...] = (
    "合同", "协议", "备忘录", "借据", "欠条", "承诺", "约定", "判决", "裁定",
    "起诉", "律师", "账目", "流水", "转账", "股权", "合伙", "对赌", "验收",
    "诊断", "医嘱", "处方", "复查", "体检", "住院", "手术", "化验", "报告",
    "吵架", "争吵", "争执", "翻脸", "分手", "道歉", "和解", "破冰", "决裂",
    "辞职", "离职", "入职", "面试", "offer", "调岗", "降薪", "裁员", "赔偿",
    "搬家", "迁居", "落户", "社保", "违约金", "分期", "利息", "本金",
    "愿望", "梦想", "答应", "发誓", "绝不", "务必",
    # 关键原话与在场对话（"谁在什么场合说了什么"本身就是证据）
    "原话", "说的话", "说道", "电话里", "发来的信息", "发来", "当面对", "会议上",
    "对话", "转述", "翻旧账", "酒后", "家里",
    # 身心信号（客观生理事件，不是情绪形容词）
    "心率", "早搏", "心律", "胸闷", "胸口", "失眠", "血糖", "血压", "漏服",
    "复诊", "随访", "症状", "医嘱", "药", "化验", "体检", "住院",
    # 生活相变与长期安排
    "通宵", "加班", "辞职", "离职", "入职", "新家", "房东", "租约", "迁入",
    "每周", "每月", "每天", "约定", "计划", "陪", "回家",
)

#: 噪声标记：命中即视为"环境噪声 / 垃圾碎片"的强信号（仅在无证据保护时才生效）。
#:
#: 覆盖三类日常环境噪声：公共空间广播、商业推销、群聊刷屏。证据标记与证据链
#: 保护永远优先 —— 若同一句话既含噪声又含证据，命中会被驳回（score 归零 → UNSURE）。
NOISE_MARKERS: tuple[str, ...] = (
    "叫卖", "促销", "打折", "清仓", "甩卖", "扫码", "关注公众号",
    "验证码", "营销短信", "退订", "贷你", "中奖", "免费领取", "限时秒杀",
    "群聊刷屏", "斗图", "广告", "陌生来电推销", "路人甲", "背景噪声",
    "车厢广播", "商场广播", "广场舞音乐", "循环播放",
    # 公共空间广播与报站
    "广播", "报站", "请乘客", "终点站", "大厅广播",
    # 商业推销与环境叫卖
    "特价", "优惠券", "秒杀", "办卡", "推销", "保健品", "扫码进群",
    "买房送", "推荐购房", "满一万减", "试纸买十送三",
    # 群聊刷屏与营销转发
    "刷屏", "转发这条", "领红包", "群广告", "微商", "代取快递", "外卖骑手",
    # 物理环境噪声
    "电钻", "装修", "背景音乐", "嘈杂", "嗡嗡", "邻桌", "路人",
)


class RetentionAdjudicator:
    """可复现的清洗裁决器（大模型每日复盘清洗权的机制化落地）。

    打分口径（公开、可被测方独立复算）：

    * 命中 ``EVIDENCE_MARKERS``：每条 +0.35；
    * 命中 ``NOISE_MARKERS``：每条 -0.35；
    * 文本含阿拉伯数字金额/日期/编号：+0.10（"有据可查"的弱信号）；
    * ``score <= noise_threshold`` 且**无证据链保护** → :data:`RetentionVerdict.NOISE`；
    * ``score >= keep_threshold`` 或**存在证据链保护** → :data:`RetentionVerdict.KEEP`；
    * 其余 → :data:`RetentionVerdict.UNSURE`（先入库，等每日复盘再裁决）。
    """

    def __init__(
        self,
        *,
        noise_threshold: float = -0.35,
        keep_threshold: float = 0.35,
        evidence_weight: float = 0.35,
        noise_weight: float = 0.35,
    ) -> None:
        if keep_threshold <= noise_threshold:
            raise ValueError("keep_threshold must be greater than noise_threshold")
        self.noise_threshold = noise_threshold
        self.keep_threshold = keep_threshold
        self.evidence_weight = evidence_weight
        self.noise_weight = noise_weight

    def score(self, text: str) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
        evidence_hits = tuple(marker for marker in EVIDENCE_MARKERS if marker in text)
        noise_hits = tuple(marker for marker in NOISE_MARKERS if marker in text)
        score = self.evidence_weight * len(evidence_hits) - self.noise_weight * len(noise_hits)
        if any(ch.isdigit() for ch in text):
            score += 0.10
        return (round(score, 4), evidence_hits, noise_hits)

    def adjudicate(self, text: str, *, protected_by: str | None = None) -> RetentionDecision:
        score, evidence_hits, noise_hits = self.score(text)
        reasons: list[str] = []
        if evidence_hits:
            reasons.append(f"命中证据标记 {len(evidence_hits)} 项：{','.join(evidence_hits[:4])}")
        if noise_hits:
            reasons.append(f"命中噪声标记 {len(noise_hits)} 项：{','.join(noise_hits[:4])}")
        if protected_by is not None:
            reasons.append(f"证据链保护：{protected_by}")
            return RetentionDecision(
                verdict=RetentionVerdict.KEEP,
                score=score,
                reasons=tuple(reasons),
                protected_by=protected_by,
                evidence_hits=evidence_hits,
                noise_hits=noise_hits,
            )
        if score <= self.noise_threshold:
            verdict = RetentionVerdict.NOISE
        elif score >= self.keep_threshold:
            verdict = RetentionVerdict.KEEP
        else:
            verdict = RetentionVerdict.UNSURE
        reasons.append(f"裁决依据：score={score} 阈值=[{self.noise_threshold},{self.keep_threshold}]")
        return RetentionDecision(
            verdict=verdict,
            score=score,
            reasons=tuple(reasons),
            evidence_hits=evidence_hits,
            noise_hits=noise_hits,
        )


# ---------------------------------------------------------------------------
# 删除审计账本（哈希链，删除可追责）
# ---------------------------------------------------------------------------


class PurgeLedgerEntry(BaseModel):
    """一次淘汰动作的审计条目。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str
    action: str = Field(pattern="^(dropped_at_edge|tombstoned|retained)$")
    verdict: str = Field(pattern="^(keep|noise|unsure)$")
    score: float
    reasons: tuple[str, ...]
    ledger_hash: str = Field(min_length=64)


@dataclass
class PurgeLedger:
    """哈希链审计账本：任何一条淘汰记录被静默篡改都会破坏链。"""

    entries: list[PurgeLedgerEntry] = field(default_factory=list)
    _prev: str = field(default="0" * 64, repr=False)

    def append(
        self,
        *,
        object_id: str,
        action: str,
        verdict: str,
        score: float,
        reasons: Sequence[str],
    ) -> PurgeLedgerEntry:
        chain_hash = self._digest(
            self._prev,
            object_id=object_id,
            action=action,
            verdict=verdict,
            score=score,
            reasons=tuple(reasons),
        )
        entry = PurgeLedgerEntry(
            object_id=object_id,
            action=action,
            verdict=verdict,
            score=score,
            reasons=tuple(reasons),
            ledger_hash=chain_hash,
        )
        self.entries.append(entry)
        self._prev = chain_hash
        return entry

    def head(self) -> str:
        return self._prev

    def count(self, action: str) -> int:
        return sum(1 for entry in self.entries if entry.action == action)

    def verify_chain(self) -> bool:
        """独立复算整条哈希链（防篡改自检）。"""

        prev = "0" * 64
        for entry in self.entries:
            recomputed = self._digest(
                prev,
                object_id=entry.object_id,
                action=entry.action,
                verdict=entry.verdict,
                score=entry.score,
                reasons=entry.reasons,
            )
            if recomputed != entry.ledger_hash:
                return False
            # 链条绑定**复算值**而不是存储值：任何一条被改写都会让其后的所有
            # 链接失效（篡改无法靠同时改写单条哈希掩盖）。
            prev = recomputed
        return True

    @staticmethod
    def _digest(
        prev: str,
        *,
        object_id: str,
        action: str,
        verdict: str,
        score: float,
        reasons: tuple[str, ...],
    ) -> str:
        """条目指纹：前序哈希 + 全部可审计字段（含裁决与理由，缺一不可）。"""

        digest = hashlib.sha256()
        digest.update(prev.encode("ascii"))
        digest.update(b"|")
        digest.update(object_id.encode("utf-8"))
        digest.update(b"|")
        digest.update(action.encode("ascii"))
        digest.update(b"|")
        digest.update(verdict.encode("ascii"))
        digest.update(b"|")
        digest.update(f"{score:.6f}".encode("ascii"))
        digest.update(b"|")
        for reason in reasons:
            digest.update(reason.encode("utf-8"))
            digest.update(b"\x1f")
        return digest.hexdigest()


# ---------------------------------------------------------------------------
# 策略与报告
# ---------------------------------------------------------------------------


class EdgePurifierPolicy(BaseModel):
    """端侧提纯策略（数字全部外置，代码路径不因场景分叉）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    imu_epsilon: float = 0.4
    imu_curvature_budget: float = 1.0
    imu_impact_magnitude: float = 4.0
    imu_min_window: int = 50
    imu_max_window: int = 4096
    #: 宏观运动状态的最小驻留时长（微秒）：短于它的状态抖动被吸收进相邻状态，
    #: 避免"静止/走动"阈值附近的高频翻转把时间轴刷成碎片（宪法第 33 条精神：
    #: 只记宏观状态，不记采样抖动）。
    motion_min_dwell_us: int = 10_000_000

    #: 心率误差界（bpm）：窗口内任一采样与"时段均值"的偏差硬约束在此界内，
    #: 这是"平稳期只留一个时段均值点"可被证明不失真的前提。
    heart_epsilon: float = 4.0
    heart_curvature_budget: float = 10.0
    heart_jump_threshold: float = 15.0
    heart_min_window: int = 30
    #: 1Hz 采样下 7200 点 = 2 小时：即宪法第 33 条"持续 2 小时无剧烈波动
    #: 仅压缩记录一个时段平均值点"在算子参数上的直接落地。
    heart_max_window: int = 7200

    image_quality_threshold: float = 0.4
    voiceprint_ttl_days: int = 180
    noise_threshold: float = -0.35
    keep_threshold: float = 0.35

    @model_validator(mode="after")
    def validate_thresholds(self) -> "EdgePurifierPolicy":
        if self.imu_epsilon <= 0 or self.heart_epsilon <= 0:
            raise ValueError("compression epsilon must be positive")
        if self.image_quality_threshold <= 0.0 or self.image_quality_threshold > 1.0:
            raise ValueError("image_quality_threshold must be within (0, 1]")
        if self.motion_min_dwell_us <= 0:
            raise ValueError("motion_min_dwell_us must be positive")
        if self.noise_threshold >= self.keep_threshold:
            raise ValueError("noise_threshold must be strictly below keep_threshold")
        return self


class EdgePurifyReport(BaseModel):
    """端侧提纯总账（百万级流入 → 宏观观察流出的可审计凭证）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_samples_ingested: int = Field(ge=0)
    imu_raw_samples: int = Field(ge=0)
    heart_raw_samples: int = Field(ge=0)
    vision_frames: int = Field(ge=0)
    audio_slices: int = Field(ge=0)
    text_events: int = Field(ge=0)

    macro_observations: int = Field(ge=0)
    imu_segments: int = Field(ge=0)
    imu_macro_observations: int = Field(ge=0)
    imu_impact_observations: int = Field(ge=0)
    heart_summary_observations: int = Field(ge=0)
    heart_anomaly_observations: int = Field(ge=0)
    caption_observations: int = Field(ge=0)
    transcript_observations: int = Field(ge=0)
    environment_text_observations: int = Field(ge=0)

    low_quality_frames_purged: int = Field(ge=0)
    raw_image_bytes_sunk: int = Field(ge=0)
    raw_image_bytes_retained: int = Field(ge=0)
    noise_dropped_at_edge: int = Field(ge=0)
    unsure_admitted: int = Field(ge=0)
    voiceprints_registered: int = Field(ge=0)
    voiceprints_tombstoned: int = Field(ge=0)

    imu_max_reconstruction_error: float = Field(ge=0.0)
    heart_max_reconstruction_error: float = Field(ge=0.0)
    compression_ratio: float = Field(ge=0.0, le=1.0)
    ingest_seconds: float = Field(ge=0.0)
    model_calls: int = Field(ge=0)

    @property
    def persisted_observations(self) -> int:
        return self.macro_observations


class DailyReviewReport(BaseModel):
    """每日复盘清洗回执（铁律 4 的量化证据）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewed_observations: int = Field(ge=0)
    tombstoned_noise: int = Field(ge=0)
    retained_core: int = Field(ge=0)
    protected_by_evidence: int = Field(ge=0)
    noise_object_ids: tuple[str, ...] = ()
    ledger_head: str = Field(min_length=64)
    ledger_ok: bool
    model_calls_charged: int = Field(ge=0)


# ---------------------------------------------------------------------------
# 提纯引擎
# ---------------------------------------------------------------------------

_MOTION_STILL = "静止"
_MOTION_WALK = "平缓走动"
_MOTION_RUN = "剧烈跑动"


class EdgeStreamPurifier:
    """端侧原始流提纯引擎：唯一允许把原始流翻译成世界观察的闸门。"""

    def __init__(
        self,
        store: SQLiteWorldStore,
        *,
        policy: EdgePurifierPolicy | None = None,
        meter: ModelCallMeter | None = None,
        subject_id: str = "user_1",
        batch_size: int = 500,
    ) -> None:
        self.store = store
        self.policy = policy or EdgePurifierPolicy()
        self.meter = meter or ModelCallMeter(name="edge-purifier")
        self.subject_id = subject_id
        self.batch_size = batch_size

        self.ledger = PurgeLedger()
        self.adjudicator = RetentionAdjudicator(
            noise_threshold=self.policy.noise_threshold,
            keep_threshold=self.policy.keep_threshold,
        )
        self._image_cleaner = EdgeMultimodalCleaner()
        self._image_sink = RawByteSink()
        self._voiceprint_index = VoiceprintLSHIndex()
        self._voiceprint_registry = VoiceprintTTLRegistry(
            ttl_days=self.policy.voiceprint_ttl_days
        )

        self._pending: list[Observation] = []
        self._committed: list[Observation] = []
        self._committed_total = 0
        self._committed_sample_cap = 64
        self._stream_batch_size = 20_000
        self._imu_buffer: list[RawImuSample] = []
        self._heart_buffer: list[RawHeartSample] = []
        self._imu_epoch_us: int | None = None
        self._heart_epoch_us: int | None = None

        # ---- 统计口径 ----
        self._raw_samples = 0
        self._imu_raw = 0
        self._heart_raw = 0
        self._vision_frames = 0
        self._audio_slices = 0
        self._text_events = 0
        self._imu_segments = 0
        self._imu_macro = 0
        self._imu_impacts = 0
        self._heart_summary = 0
        self._heart_anomaly = 0
        self._captions = 0
        self._transcripts = 0
        self._text_kept = 0
        self._low_quality_purged = 0
        self._sunk_bytes = 0
        self._noise_dropped = 0
        self._unsure_admitted = 0
        self._voiceprints_tombstoned = 0
        self._imu_error = 0.0
        self._heart_error = 0.0
        self._ingest_seconds = 0.0
        self._unbound_voiceprints: list[str] = []

    # ------------------------------------------------------------------
    # 通用入口
    # ------------------------------------------------------------------

    def ingest_raw_stream(self, raw: Iterable[Any]) -> EdgePurifyReport:
        """按样本类型分派摄入：支持百万级生成器流，不物化整个流。"""

        import time

        started = time.perf_counter()
        for sample in raw:
            if isinstance(sample, RawImuSample):
                self._push_imu(sample)
            elif isinstance(sample, RawHeartSample):
                self._push_heart(sample)
            elif isinstance(sample, RawVisionFrame):
                self.ingest_vision_frame(sample)
            elif isinstance(sample, RawAudioSlice):
                self.ingest_audio_slice(sample)
            elif isinstance(sample, RawEnvironmentText):
                self.ingest_text_event(sample)
            else:
                raise TypeError(f"unsupported raw sample type: {type(sample).__name__}")
        self._flush_imu_buffer()
        self._flush_heart_buffer()
        self.flush()
        self._ingest_seconds += time.perf_counter() - started
        return self.report()

    # ---- 缓冲与"时间纪元"边界 ------------------------------------------
    #
    # 单条时间轴上只允许时间单调不减。一旦出现时间回退，说明流切换到了另一段
    # 独立生命线/设备会话：此时必须先封掉当前缓冲，否则跨纪元样本会被错误地
    # 压进同一个自适应窗口（把两段人生平均成一个均值），这是不可接受的失真。

    def _push_imu(self, sample: RawImuSample) -> None:
        if self._imu_epoch_us is not None and sample.t_us < self._imu_epoch_us:
            self._flush_imu_buffer()
        self._imu_epoch_us = sample.t_us
        self._imu_buffer.append(sample)
        if len(self._imu_buffer) >= self._stream_batch_size:
            self._flush_imu_buffer()

    def _flush_imu_buffer(self) -> None:
        if self._imu_buffer:
            batch = self._imu_buffer
            self._imu_buffer = []
            self._ingest_imu_batch(batch)

    def _push_heart(self, sample: RawHeartSample) -> None:
        if self._heart_epoch_us is not None and sample.t_us < self._heart_epoch_us:
            self._flush_heart_buffer()
        self._heart_epoch_us = sample.t_us
        self._heart_buffer.append(sample)
        if len(self._heart_buffer) >= self._stream_batch_size:
            self._flush_heart_buffer()

    def _flush_heart_buffer(self) -> None:
        if self._heart_buffer:
            batch = self._heart_buffer
            self._heart_buffer = []
            self._ingest_heart_batch(batch)

    def ingest_imu_stream(
        self, stream: Iterable[RawImuSample], *, batch_size: int | None = None
    ) -> int:
        previous = self._stream_batch_size
        if batch_size is not None:
            self._stream_batch_size = batch_size
        try:
            for sample in stream:
                self._push_imu(sample)
            self._flush_imu_buffer()
        finally:
            self._stream_batch_size = previous
        return self._imu_raw

    def ingest_heart_stream(
        self, stream: Iterable[RawHeartSample], *, batch_size: int | None = None
    ) -> int:
        previous = self._stream_batch_size
        if batch_size is not None:
            self._stream_batch_size = batch_size
        try:
            for sample in stream:
                self._push_heart(sample)
            self._flush_heart_buffer()
        finally:
            self._stream_batch_size = previous
        return self._heart_raw

    # ------------------------------------------------------------------
    # IMU：50Hz 禁直写 → 宏观运动状态 + 独立冲击 Observation
    # ------------------------------------------------------------------

    def _ingest_imu_batch(self, batch: Sequence[RawImuSample]) -> None:
        compressor = AdaptiveTemporalCompressor(
            epsilon=self.policy.imu_epsilon,
            curvature_budget=self.policy.imu_curvature_budget,
            impact_magnitude=self.policy.imu_impact_magnitude,
            impact_jump=None,
            min_window=self.policy.imu_min_window,
            max_window=self.policy.imu_max_window,
        )
        result: CompressionResult = compressor.compress(
            (sample.t_us, sample.magnitude) for sample in batch
        )
        self._imu_raw += result.input_count
        self._raw_samples += result.input_count
        self._imu_segments += result.output_count
        self._imu_error = max(self._imu_error, result.max_abs_error)

        dwell_us = self.policy.motion_min_dwell_us
        committed_state: str | None = None
        committed_start = 0
        committed_end = 0
        committed_samples = 0
        committed_weighted = 0.0

        pend_state: str | None = None
        pend_start = 0
        pend_end = 0
        pend_samples = 0
        pend_weighted = 0.0

        for segment in result.segments:
            if segment.segment_kind == "impact":
                if committed_state is not None:
                    self._emit_motion_observation(
                        committed_state,
                        committed_start,
                        committed_end,
                        committed_samples,
                        committed_weighted,
                    )
                    committed_state = None
                pend_state = None
                pend_samples = 0
                pend_weighted = 0.0
                self._imu_impacts += 1
                self._buffer(
                    Observation(
                        object_id=new_object_id(ObjectType.OBSERVATION),
                        subject_id=self.subject_id,
                        revision=1,
                        source_kind="imu_impact",
                        modality="json",
                        value=json.dumps(
                            {
                                "impact_kind": "fall_suspected"
                                if segment.value >= 4.5
                                else "sharp_impact",
                                "peak_magnitude_g": round(segment.value, 3),
                                "impact_at": _dt(segment.start_us).isoformat(),
                                "raw_high_frequency_persisted": False,
                            },
                            ensure_ascii=False,
                        ),
                        occurred=TemporalExtent.point(_dt(segment.start_us)),
                        learned_at=_dt(segment.start_us),
                        created_by="edge_stream_purifier",
                        metadata={"channel": "imu", "sample_count": 1},
                    )
                )
                continue

            state = self._classify_motion(segment.value)
            if state != pend_state:
                # 上一个候选状态结束：只有驻留够久才允许改写宏观状态
                if pend_state is not None:
                    if committed_state is None:
                        committed_state = pend_state
                        committed_start = pend_start
                        committed_end = pend_end
                        committed_samples = pend_samples
                        committed_weighted = pend_weighted
                    elif pend_end - pend_start >= dwell_us and pend_state != committed_state:
                        self._emit_motion_observation(
                            committed_state,
                            committed_start,
                            committed_end,
                            committed_samples,
                            committed_weighted,
                        )
                        committed_state = pend_state
                        committed_start = pend_start
                        committed_end = pend_end
                        committed_samples = pend_samples
                        committed_weighted = pend_weighted
                    else:
                        # 抖动被吸收：并入当前宏观状态，不产生新的时间轴碎片
                        committed_end = pend_end
                        committed_samples += pend_samples
                        committed_weighted += pend_weighted
                pend_state = state
                pend_start = segment.start_us
                pend_samples = 0
                pend_weighted = 0.0
            pend_end = segment.end_us
            pend_samples += segment.n_samples
            pend_weighted += segment.value * segment.n_samples

        if pend_state is not None:
            if committed_state is None:
                committed_state = pend_state
                committed_start = pend_start
                committed_end = pend_end
                committed_samples = pend_samples
                committed_weighted = pend_weighted
            elif pend_end - pend_start >= dwell_us and pend_state != committed_state:
                self._emit_motion_observation(
                    committed_state,
                    committed_start,
                    committed_end,
                    committed_samples,
                    committed_weighted,
                )
                committed_state = pend_state
                committed_start = pend_start
                committed_end = pend_end
                committed_samples = pend_samples
                committed_weighted = pend_weighted
            else:
                committed_end = pend_end
                committed_samples += pend_samples
                committed_weighted += pend_weighted

        if committed_state is not None:
            self._emit_motion_observation(
                committed_state,
                committed_start,
                committed_end,
                committed_samples,
                committed_weighted,
            )

    @staticmethod
    def _classify_motion(magnitude: float) -> str:
        if magnitude < 1.25:
            return _MOTION_STILL
        if magnitude < 2.2:
            return _MOTION_WALK
        return _MOTION_RUN

    def _emit_motion_observation(
        self,
        state: str,
        start_us: int,
        end_us: int,
        samples: int,
        weighted: float,
    ) -> None:
        """落一条宏观运动状态观察（宪法第 33 条第 1 款的落库形态）。"""

        if samples == 0:
            return
        self._imu_macro += 1
        mean = weighted / samples
        self._buffer(
            Observation(
                object_id=new_object_id(ObjectType.OBSERVATION),
                subject_id=self.subject_id,
                revision=1,
                source_kind="imu_macro_state",
                modality="state",
                value=json.dumps(
                    {
                        "motion_state": state,
                        "mean_magnitude_g": round(mean, 4),
                        "compressed_sample_count": samples,
                        "window_start": _dt(start_us).isoformat(),
                        "window_end": _dt(end_us).isoformat(),
                    },
                    ensure_ascii=False,
                ),
                occurred=TemporalExtent(start=_dt(start_us), end=_dt(end_us)),
                learned_at=_dt(end_us),
                created_by="edge_stream_purifier",
                metadata={"channel": "imu", "sample_count": samples},
            )
        )

    # ------------------------------------------------------------------
    # 心率：平稳期只留时段均值，突变波形独立成 Observation
    # ------------------------------------------------------------------

    def _ingest_heart_batch(self, batch: Sequence[RawHeartSample]) -> None:
        compressor = AdaptiveTemporalCompressor(
            epsilon=self.policy.heart_epsilon,
            curvature_budget=self.policy.heart_curvature_budget,
            impact_jump=self.policy.heart_jump_threshold,
            impact_magnitude=None,
            min_window=self.policy.heart_min_window,
            max_window=self.policy.heart_max_window,
        )
        result = compressor.compress((sample.t_us, sample.bpm) for sample in batch)
        self._heart_raw += result.input_count
        self._raw_samples += result.input_count
        self._heart_error = max(self._heart_error, result.max_abs_error)

        for segment in result.segments:
            night = 0 <= _dt(segment.start_us).hour < 6
            if segment.segment_kind == "impact":
                self._heart_anomaly += 1
                self._buffer(
                    Observation(
                        object_id=new_object_id(ObjectType.OBSERVATION),
                        subject_id=self.subject_id,
                        revision=1,
                        source_kind="heart_rate_anomaly",
                        modality="json",
                        value=json.dumps(
                            {
                                "anomaly_kind": "acute_bpm_shift",
                                "peak_bpm": round(segment.value, 1),
                                "detected_at": _dt(segment.start_us).isoformat(),
                                "nighttime": night,
                                "waveform_preserved": True,
                            },
                            ensure_ascii=False,
                        ),
                        occurred=TemporalExtent.point(_dt(segment.start_us)),
                        learned_at=_dt(segment.start_us),
                        created_by="edge_stream_purifier",
                        metadata={"channel": "heart_rate", "sample_count": 1},
                    )
                )
                continue
            if segment.n_samples < self.policy.heart_min_window:
                # 短段不构成"平稳时段"，静默丢弃，绝不污染时间轴
                continue
            self._heart_summary += 1
            self._buffer(
                Observation(
                    object_id=new_object_id(ObjectType.OBSERVATION),
                    subject_id=self.subject_id,
                    revision=1,
                    source_kind="heart_rate_summary",
                    modality="json",
                    value=json.dumps(
                        {
                            "period_mean_bpm": round(segment.value, 2),
                            "window_start": _dt(segment.start_us).isoformat(),
                            "window_end": _dt(segment.end_us).isoformat(),
                            "compressed_sample_count": segment.n_samples,
                            "max_abs_error_bpm": round(segment.max_abs_error, 3),
                        },
                        ensure_ascii=False,
                    ),
                    occurred=TemporalExtent(start=_dt(segment.start_us), end=_dt(segment.end_us)),
                    learned_at=_dt(segment.end_us),
                    created_by="edge_stream_purifier",
                    metadata={"channel": "heart_rate", "sample_count": segment.n_samples},
                )
            )

    # ------------------------------------------------------------------
    # 视觉：只留 Caption，原始字节必粉碎
    # ------------------------------------------------------------------

    def ingest_vision_frame(self, frame: RawVisionFrame) -> str | None:
        self._vision_frames += 1
        self._raw_samples += 1
        self._image_sink.sink(frame.frame_id, frame.raw_bytes)
        self._sunk_bytes += len(frame.raw_bytes)
        cleaned = self._image_cleaner.evaluate_and_clean_image(
            {
                "mean_luma": frame.mean_luma,
                "high_freq_energy": frame.high_freq_energy,
                "motion_magnitude": frame.motion_magnitude,
                "caption": frame.caption,
                "tags": list(frame.tags),
                "source": frame.frame_id,
            },
            frame.raw_bytes,
        )
        self._image_sink.purge([frame.frame_id])
        if cleaned is None:
            self._low_quality_purged += 1
            return None
        if cleaned.raw_image_bytes_retained:
            raise AssertionError("宪法第 33 条：达标图像同样不得保留原始二进制")
        self._captions += 1
        self._buffer(
            Observation(
                object_id=new_object_id(ObjectType.OBSERVATION),
                subject_id=self.subject_id,
                revision=1,
                source_kind="vision_caption",
                modality="text",
                value=cleaned.semantic_caption,
                occurred=TemporalExtent.point(_dt(frame.t_us)),
                learned_at=_dt(frame.t_us),
                created_by="edge_stream_purifier",
                metadata={
                    "channel": "vision",
                    "quality_score": cleaned.quality_score,
                    "scene_tags": list(cleaned.scene_tags),
                    "raw_image_bytes_retained": False,
                },
            )
        )
        return cleaned.semantic_caption

    # ------------------------------------------------------------------
    # 音频：转文本 + 声纹绑定 + 180 天淘汰
    # ------------------------------------------------------------------

    def ingest_audio_slice(self, slice_: RawAudioSlice) -> str | None:
        self._audio_slices += 1
        self._raw_samples += 1
        voiceprint_id = slice_.speaker_slot
        feature = tuple(slice_.voiceprint_feature)
        if voiceprint_id not in self._voiceprint_registry.active_hot and len(feature) == 128:
            if voiceprint_id not in self._registered_voiceprint_ids():
                self._voiceprint_index.add(voiceprint_id, feature, slice_.bound_entity_id)
                self._voiceprint_registry.register(
                    VoiceprintProfile(
                        voiceprint_id=voiceprint_id,
                        entity_id=slice_.bound_entity_id,
                        feature_hash=hashlib.sha1(
                            ",".join(f"{v:.3f}" for v in feature).encode("utf-8")
                        ).hexdigest(),
                        first_detected_at=_dt(slice_.t_us),
                        last_contact_at=_dt(slice_.t_us),
                    )
                )
                if slice_.bound_entity_id is None:
                    self._unbound_voiceprints.append(voiceprint_id)
        elif voiceprint_id in self._registered_voiceprint_ids():
            self._voiceprint_registry.note_contact(voiceprint_id, _dt(slice_.t_us))

        decision = self.adjudicator.adjudicate(slice_.transcript)
        if decision.verdict is RetentionVerdict.NOISE:
            self._noise_dropped += 1
            self.ledger.append(
                object_id=f"raw_audio:{slice_.slice_id}",
                action="dropped_at_edge",
                verdict=decision.verdict.value,
                score=decision.score,
                reasons=decision.reasons,
            )
            return None

        self._transcripts += 1
        self._buffer(
            Observation(
                object_id=new_object_id(ObjectType.OBSERVATION),
                subject_id=self.subject_id,
                revision=1,
                source_kind="voice_transcript",
                modality="text",
                value=slice_.transcript,
                occurred=TemporalExtent.point(_dt(slice_.t_us)),
                learned_at=_dt(slice_.t_us),
                created_by="edge_stream_purifier",
                metadata={
                    "channel": "audio",
                    "voiceprint_id": voiceprint_id,
                    "bound_entity_id": slice_.bound_entity_id,
                    "ambient_db": slice_.ambient_db,
                    "duration_ms": slice_.duration_ms,
                    "retention_verdict": decision.verdict.value,
                },
            )
        )
        return slice_.transcript

    def _registered_voiceprint_ids(self) -> set[str]:
        return {
            profile.voiceprint_id
            for profile in (self._voiceprint_registry.active_hot + self._voiceprint_registry.archived)
        }

    def sweep_voiceprints(self, now: datetime) -> tuple[str, ...]:
        """推进声纹 TTL：满 180 天未接触且未绑定身份的声纹自动墓碑。"""

        tombstoned = tuple(self._voiceprint_registry.sweep(now))
        self._voiceprints_tombstoned += len(tombstoned)
        return tombstoned

    # ------------------------------------------------------------------
    # 文本环境流：大模型裁决 + 边缘物理剪枝
    # ------------------------------------------------------------------

    def ingest_text_event(self, event: RawEnvironmentText) -> str | None:
        self._text_events += 1
        self._raw_samples += 1
        decision = self.adjudicator.adjudicate(event.text)
        if decision.verdict is RetentionVerdict.NOISE:
            self._noise_dropped += 1
            self.ledger.append(
                object_id=event.event_id,
                action="dropped_at_edge",
                verdict=decision.verdict.value,
                score=decision.score,
                reasons=decision.reasons,
            )
            return None
        if decision.verdict is RetentionVerdict.UNSURE:
            self._unsure_admitted += 1
        self._text_kept += 1
        self._buffer(
            Observation(
                object_id=event.event_id,
                subject_id=self.subject_id,
                revision=1,
                source_kind=event.channel,
                modality="text",
                value=event.text,
                occurred=TemporalExtent.point(_dt(event.t_us)),
                learned_at=_dt(event.t_us),
                created_by="edge_stream_purifier",
                metadata={
                    "channel": event.channel,
                    "retention_verdict": decision.verdict.value,
                    "retention_score": decision.score,
                },
            )
        )
        return event.text

    # ------------------------------------------------------------------
    # 缓冲与落库
    # ------------------------------------------------------------------

    def _buffer(self, observation: Observation) -> None:
        self._pending.append(observation)
        if len(self._pending) >= self.batch_size:
            self.flush()

    def flush(self) -> int:
        """把缓冲的宏观观察批量提交（唯一落库通道，天然杜绝原始流直写）。"""

        if not self._pending:
            return 0
        chunk = self._pending
        self._pending = []
        operation = OperationRequest(
            operation_id=new_operation_id(),
            operation_name="edge.purify.commit",
            expected_world_revision=self.store.current_world_revision(),
            reason=f"Edge purifier commit {len(chunk)} macro observations",
            idempotency_key=new_operation_id(),
            source_class=SourceClass.SENSOR,
        )
        self.store.commit(chunk, operation)
        self._committed_total += len(chunk)
        remaining = self._committed_sample_cap - len(self._committed)
        if remaining > 0:
            self._committed.extend(chunk[:remaining])
        return len(chunk)

    # ------------------------------------------------------------------
    # 每日复盘清洗（铁律 4）
    # ------------------------------------------------------------------

    def scan_evidence_protection(self) -> dict[str, str]:
        """扫描世界里已有的证据链条，返回 ``{被引用对象 id: 保护来源}``。"""

        protection: dict[str, str] = {}
        for payload in self.store.list_payloads(object_type=ObjectType.EVENT):
            anchor = EventAnchor.model_validate(payload)
            for ref in (
                list(anchor.evidence_set_refs)
                + list(anchor.support_evidence_set_refs)
                + list(anchor.primary_claim_refs)
            ):
                protection.setdefault(ref.object_id, f"EventAnchor:{anchor.object_id}")
        for payload in self.store.list_payloads(object_type=ObjectType.EVIDENCE_SET):
            evidence_set = EvidenceSet.model_validate(payload)
            for ref in (
                list(evidence_set.member_refs)
                + list(evidence_set.support_refs)
                + list(evidence_set.counter_refs)
                + list(evidence_set.context_refs)
            ):
                protection.setdefault(ref.object_id, f"EvidenceSet:{evidence_set.object_id}")
        for payload in self.store.list_payloads(object_type=ObjectType.CLAIM):
            claim = Claim.model_validate(payload)
            for ref in list(claim.support_evidence_set_refs) + list(
                claim.counter_evidence_set_refs
            ):
                protection.setdefault(ref.object_id, f"Claim:{claim.object_id}")
        return protection

    def daily_review(self, *, now: datetime | None = None) -> DailyReviewReport:
        """每日复盘：大模型自主研判后，**物理淘汰**无证据保护的噪声观察。"""

        review_time = now or datetime.now(UTC)
        self.flush()
        protection = self.scan_evidence_protection()

        reviewed = 0
        tombstoned = 0
        retained_core = 0
        protected = 0
        noise_ids: list[str] = []

        for payload in self.store.list_payloads(object_type=ObjectType.OBSERVATION):
            if payload.get("pruned"):
                continue
            if str(payload.get("modality", "")) != "text":
                # 结构化传感器观察（IMU 宏观态 / 心率时段均值 / 异常波形）不是
                # "环境文本碎片"：它们是该生理时段**唯一**的客观记录，绝不进入
                # 文本淘汰裁决（铁律 4 只清理原始噪声与垃圾文本）。
                continue
            reviewed += 1
            object_id = str(payload["object_id"])
            text = str(payload.get("value", ""))
            guard = protection.get(object_id)
            decision = self.adjudicator.adjudicate(text, protected_by=guard)
            if guard is not None:
                protected += 1
                retained_core += 1
                continue
            # 每日复盘是全世界观下的大模型裁决点：边缘为保守起见先收下的
            # UNSURE 文本，在这里按同一把尺子做终审 —— 无证据保护的一律物理淘汰
            # （铁律 4：手环存储宝贵，环境噪声与垃圾碎片不得长期驻留）。
            if decision.verdict is not RetentionVerdict.KEEP:
                self.store.prune(
                    object_id,
                    authz_ref="daily_review:llm_adjudication",
                    reason=(
                        "铁律4 每日复盘智能清洗：环境噪声/垃圾碎片无证据保护，"
                        f"verdict={decision.verdict.value} score={decision.score}"
                    ),
                )
                tombstoned += 1
                noise_ids.append(object_id)
                self.ledger.append(
                    object_id=object_id,
                    action="tombstoned",
                    verdict=decision.verdict.value,
                    score=decision.score,
                    reasons=decision.reasons,
                )
            else:
                retained_core += 1

        # 每日复盘是大模型唯一被允许消耗算力的清洗点：这里记一次账（每轮一次）。
        self.meter.charge("daily_review_adjudication", detail=f"reviewed={reviewed}")

        return DailyReviewReport(
            reviewed_observations=reviewed,
            tombstoned_noise=tombstoned,
            retained_core=retained_core,
            protected_by_evidence=protected,
            noise_object_ids=tuple(noise_ids),
            ledger_head=self.ledger.head(),
            ledger_ok=self.ledger.verify_chain(),
            model_calls_charged=1,
        )

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def report(self) -> EdgePurifyReport:
        macro = (
            self._imu_macro
            + self._imu_impacts
            + self._heart_summary
            + self._heart_anomaly
            + self._captions
            + self._transcripts
            + self._text_kept
        )
        ratio = 0.0
        if self._raw_samples:
            ratio = max(0.0, 1.0 - (macro / self._raw_samples))
        return EdgePurifyReport(
            raw_samples_ingested=self._raw_samples,
            imu_raw_samples=self._imu_raw,
            heart_raw_samples=self._heart_raw,
            vision_frames=self._vision_frames,
            audio_slices=self._audio_slices,
            text_events=self._text_events,
            macro_observations=macro,
            imu_segments=self._imu_segments,
            imu_macro_observations=self._imu_macro,
            imu_impact_observations=self._imu_impacts,
            heart_summary_observations=self._heart_summary,
            heart_anomaly_observations=self._heart_anomaly,
            caption_observations=self._captions,
            transcript_observations=self._transcripts,
            environment_text_observations=self._text_kept,
            low_quality_frames_purged=self._low_quality_purged,
            raw_image_bytes_sunk=self._sunk_bytes,
            raw_image_bytes_retained=self._image_sink.retained_bytes,
            noise_dropped_at_edge=self._noise_dropped,
            unsure_admitted=self._unsure_admitted,
            voiceprints_registered=len(self._voiceprint_index),
            voiceprints_tombstoned=self._voiceprints_tombstoned,
            imu_max_reconstruction_error=self._imu_error,
            heart_max_reconstruction_error=self._heart_error,
            compression_ratio=ratio,
            ingest_seconds=self._ingest_seconds,
            model_calls=self.meter.total,
        )

    # ------------------------------------------------------------------
    # 只读探针（供测试 / 审计独立复核，不暴露内部可变状态）
    # ------------------------------------------------------------------

    def committed_observations(self) -> tuple[Observation, ...]:
        """返回前若干条已落库观察（有界样本，百万级压测时不驻留全量对象）。"""

        return tuple(self._committed)

    def committed_count(self) -> int:
        return self._committed_total

    def voiceprint_bindings(self) -> Mapping[str, str | None]:
        return {
            profile.voiceprint_id: profile.entity_id
            for profile in (
                self._voiceprint_registry.active_hot + self._voiceprint_registry.archived
            )
        }

    def voiceprint_tombstones(self) -> tuple[str, ...]:
        return tuple(profile.voiceprint_id for profile in self._voiceprint_registry.archived)

    def voiceprint_index_size(self) -> int:
        return len(self._voiceprint_index)

    def voiceprint_hot_size(self) -> int:
        return len(self._voiceprint_registry.active_hot)

    def sink_retained_bytes(self) -> int:
        return self._image_sink.retained_bytes


def ensure_entity(
    store: SQLiteWorldStore,
    *,
    entity_id: str,
    canonical_name: str,
    aliases: Sequence[str],
    subject_id: str = "user_1",
    created_at: datetime | None = None,
) -> Entity:
    """幂等登记实体（阶段一/三都用得上的最小写入原语）。"""

    ts = created_at or datetime.now(UTC)
    try:
        store.get_payload(entity_id)
        existing = store.get_payload(entity_id)
        return Entity.model_validate(existing)
    except Exception:
        pass
    entity = Entity(
        object_id=entity_id,
        subject_id=subject_id,
        revision=1,
        entity_kind="person",
        canonical_name=canonical_name,
        aliases=list(aliases),
        occurred=TemporalExtent.point(ts),
        learned_at=ts,
        created_by="campaign",
    )
    store.commit(
        [entity],
        OperationRequest(
            operation_id=new_operation_id(),
            operation_name="campaign.entity.ensure",
            expected_world_revision=store.current_world_revision(),
            reason=f"Ensure entity {canonical_name}",
            idempotency_key=f"ensure_{entity_id}",
            source_class=SourceClass.AI_COGNITION,
        ),
    )
    return entity


def link_evidence(
    store: SQLiteWorldStore,
    *,
    member_refs: Sequence[ObjectRef],
    purpose: str,
    learned_at: datetime,
    evidence_set_id: str,
    subject_id: str = "user_1",
    occurred: TemporalExtent | None = None,
) -> EvidenceSet:
    """建立证据集合（把散落的观察钉成证据链，是"永存"判定的锚）。"""

    evidence_set = EvidenceSet(
        object_id=evidence_set_id,
        subject_id=subject_id,
        revision=1,
        purpose=purpose,
        knowledge_window=_knowledge_window(learned_at),
        member_refs=list(member_refs),
        selection_method="campaign_curated",
        occurred=occurred or TemporalExtent.point(learned_at),
        learned_at=learned_at,
        created_by="campaign",
    )
    store.commit(
        [evidence_set],
        OperationRequest(
            operation_id=new_operation_id(),
            operation_name="campaign.evidence.link",
            expected_world_revision=store.current_world_revision(),
            reason=f"Link evidence set {evidence_set_id}",
            idempotency_key=f"evset_{evidence_set_id}",
            source_class=SourceClass.AI_COGNITION,
        ),
    )
    return evidence_set


def _knowledge_window(learned_at: datetime):
    from aios_core.contracts.time import KnowledgeWindow

    return KnowledgeWindow(knowledge_cutoff=learned_at)


def utc_from_us(t_us: int) -> datetime:
    """微秒时间戳 → UTC datetime（供调用方复用，不重复实现）。"""

    return _dt(t_us)


def elapsed_days(start: datetime, end: datetime) -> float:
    return (end - start) / timedelta(days=1)
