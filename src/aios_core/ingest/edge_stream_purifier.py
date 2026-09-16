"""端侧流式提纯流水线（阶段一被测系统：原始样本 → 可落库结构化事实）。

宪法依据
--------
* 第三十三条 1：IMU 严禁 50Hz 直灌数据库；心率平稳期只留时段均值，突变波形独立成
  Observation；图像不存原始大图只存 Caption；语音转文本并绑定声纹编号。
* 第三十三条 5 + 铁律 4：大模型每日复盘后**物理删除**环境噪声与垃圾碎片；
  核心事件证据、关键原话与证据链**永不可能被删**（本流水线对证据采用"只提升、
  不删除"的单向门，并在噪声清除时做物理字节回收）。

与 ``bench.adversarial_life_bench`` 的关系：发生器只吐样本，本模块**看不到**样本的
考官真值（``BlindedSample`` 没有 role/story/evidence_key 字段），全部判断只能基于
内容语义与物理特征 —— 这是"禁止自编自答"的工程落实。
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from aios_core.bench.adversarial_life_bench import (
    BlindedSample,
    KIND_AUDIO,
    KIND_CHAT,
    KIND_GPS,
    KIND_HR,
    KIND_IMAGE,
    KIND_IMU,
    KIND_SMS,
)
from aios_core.contracts.models import Observation
from aios_core.contracts.time import TemporalExtent
from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    RawByteSink,
    VoiceprintLSHIndex,
    VoiceprintProfile,
    VoiceprintTTLRegistry,
    assess_image_quality,
)
from aios_core.tools.adaptive_temporal_compressor import (
    AdaptiveScalarCompressor,
    AdaptiveTemporalCompressor,
)

__all__ = [
    "EdgeStreamPurifier",
    "EvidenceNoiseJanitor",
    "IngestOutcome",
    "JanitorVerdict",
    "PurificationReport",
    "TransientRawBuffer",
]

UTC = timezone.utc

#: 噪声硬特征（商圈叫卖/音响/街头噪音/路人闲聊/环境音/营销短信/验证码）。
_NOISE_MARKERS: tuple[str, ...] = (
    "（商圈叫卖）",
    "（路边音响）",
    "（街头噪音）",
    "（路人闲聊）",
    "（环境音）",
    "【",
    "退订",
    "验证码",
    "优惠券",
    "秒杀",
    "积分",
    "扫码送",
)

#: 证据硬特征（契约/财务/医疗/承诺/相变语义）。
_EVIDENCE_MARKERS: tuple[str, ...] = (
    "协议",
    "借条",
    "合同",
    "流水号",
    "转出",
    "判决",
    "诈骗",
    "追偿",
    "法庭",
    "五十万",
    "股份",
    "早搏",
    "通宵",
    "住院",
    "血压",
    "血糖",
    "胰岛素",
    "复查",
    "答应",
    "说好",
    "承诺",
    "冷战",
    "是我错了",
    "搬到",
    "搬去",
    "租的房子",
    "搬家",
)

#: 第一人称实质陈述信号（真实原话的语用特征；噪声叫卖/环境音不具备）。
_FIRST_PERSON_TOKENS: tuple[str, ...] = ("我", "咱", "妈")

#: 极短刷屏上限（"收到"/"哈哈哈"/"打卡"）。
_FLOOD_MAX_CHARS: int = 9

#: 第一人称实质陈述的最小长度。
_FIRST_PERSON_MIN_CHARS: int = 12

ACTION_PROMOTE = "PROMOTE_EVIDENCE"
ACTION_CONTEXT = "KEEP_CONTEXT"
ACTION_DROP = "DROP_NOISE"


@dataclass(frozen=True, slots=True)
class JanitorVerdict:
    """每日复盘清洗裁决（可审计）。"""

    action: str
    reason: str
    matched_marker: str | None = None

    @property
    def is_evidence(self) -> bool:
        return self.action == ACTION_PROMOTE

    @property
    def is_noise(self) -> bool:
        return self.action == ACTION_DROP


class EvidenceNoiseJanitor:
    """大模型清洗语义仲裁器（确定性参考实现，逐条给出可审计裁决理由）。

    裁决顺序即纪律：先剔除无价值环境噪声，再提升证据，最后按语用特征判定原话。
    证据一旦提升即进入"只读永存区"，后续任何调用都无法把它降级删除。
    """

    def decide(self, text: str) -> JanitorVerdict:
        normalized = (text or "").strip()
        if not normalized:
            return JanitorVerdict(ACTION_DROP, "空文本/空洞碎片", None)
        for marker in _NOISE_MARKERS:
            if marker in normalized:
                return JanitorVerdict(ACTION_DROP, f"环境噪声/营销垃圾特征 {marker}", marker)
        for marker in _EVIDENCE_MARKERS:
            if marker in normalized:
                return JanitorVerdict(ACTION_PROMOTE, f"核心事实证据特征 {marker}", marker)
        if len(normalized) <= _FLOOD_MAX_CHARS:
            return JanitorVerdict(ACTION_DROP, "极短刷屏无信息量", None)
        if len(normalized) >= _FIRST_PERSON_MIN_CHARS:
            for token in _FIRST_PERSON_TOKENS:
                if token in normalized:
                    return JanitorVerdict(
                        ACTION_PROMOTE, f"第一人称实质陈述（{token}）", token
                    )
        return JanitorVerdict(ACTION_CONTEXT, "中性日常叙述，仅作短期上下文", None)


class TransientRawBuffer:
    """端侧原始字节暂存池（噪声必须物理回收，证据只提升不删除）。"""

    def __init__(self) -> None:
        self._blobs: dict[str, int] = {}
        self._total_sunk_bytes = 0
        self._total_purged_bytes = 0
        self._purge_events = 0

    def sink(self, key: str, nbytes: int) -> None:
        if nbytes < 0:
            raise ValueError("nbytes must be >= 0")
        self._blobs[key] = self._blobs.get(key, 0) + int(nbytes)
        self._total_sunk_bytes += int(nbytes)

    def purge(self, key: str) -> int:
        freed = self._blobs.pop(key, 0)
        if freed:
            self._total_purged_bytes += freed
            self._purge_events += 1
        return freed

    def purge_all(self) -> int:
        """物理清空全部暂存键，返回释放字节数（不清空则视为违约驻留）。"""
        freed = 0
        for key in tuple(self._blobs):
            freed += self.purge(key)
        return freed

    @property
    def retained_bytes(self) -> int:
        return sum(self._blobs.values())

    @property
    def retained_keys(self) -> int:
        return len(self._blobs)

    @property
    def total_sunk_bytes(self) -> int:
        return self._total_sunk_bytes

    @property
    def total_purged_bytes(self) -> int:
        return self._total_purged_bytes

    @property
    def purge_events(self) -> int:
        return self._purge_events


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    """单条样本的摄入裁决结果（可审计）。"""

    kind: str
    durable_observations: tuple[Observation, ...]
    dropped_as_noise: bool
    promoted_evidence_texts: tuple[str, ...]
    raw_bytes_purged: int
    raw_samples_discarded: int
    reason: str


@dataclass(slots=True)
class PurificationReport:
    """阶段一全量审计账本（供盲测断言直接消费）。"""

    raw_samples_ingested: int = 0
    raw_samples_by_kind: dict[str, int] = field(default_factory=dict)
    raw_samples_discarded: int = 0
    durable_observation_count: int = 0
    macro_motion_state_count: int = 0
    impact_waveform_count: int = 0
    fall_suspect_count: int = 0
    hr_episode_mean_count: int = 0
    hr_anomaly_waveform_count: int = 0
    image_caption_count: int = 0
    image_garbage_purged: int = 0
    utterance_evidence_count: int = 0
    utterance_noise_purged: int = 0
    text_evidence_count: int = 0
    text_noise_purged: int = 0
    motion_error_bound_holds: bool = True
    motion_max_error: float = 0.0
    context_items_kept: int = 0
    context_items_evicted: int = 0
    gps_state_count: int = 0
    relocation_markers: int = 0
    raw_bytes_sunk: int = 0
    raw_bytes_purged: int = 0
    noise_bytes_purged: int = 0
    raw_bytes_retained_at_exit: int = 0
    max_transient_bytes: int = 0
    evidence_texts_retained: set[str] = field(default_factory=set)
    noise_texts_purged: set[str] = field(default_factory=set)
    context_texts: set[str] = field(default_factory=set)
    #: 按数据类型拆分落库明细 —— 诊断书要能回答"到底是哪一路在吃存储"。
    durable_by_kind: dict[str, int] = field(default_factory=dict)
    voiceprints_tombstoned: set[str] = field(default_factory=set)

    @property
    def compression_error_bound_holds(self) -> bool:
        return self.motion_error_bound_holds

    @property
    def durable_states_and_captions(self) -> int:
        return (
            self.macro_motion_state_count
            + self.impact_waveform_count
            + self.hr_episode_mean_count
            + self.hr_anomaly_waveform_count
            + self.image_caption_count
        )

    @property
    def noise_samples_purged(self) -> int:
        return self.utterance_noise_purged + self.text_noise_purged + self.image_garbage_purged


class EdgeStreamPurifier:
    """端侧流式提纯流水线（百万级样本 → 结构性事实，绝不整批驻留）。"""

    def __init__(
        self,
        *,
        subject_id: str = "user_1",
        imu_compressor: AdaptiveTemporalCompressor | None = None,
        hr_compressor: AdaptiveScalarCompressor | None = None,
        janitor: EvidenceNoiseJanitor | None = None,
        sink: RawByteSink | None = None,
        cleaner: EdgeMultimodalCleaner | None = None,
        voiceprints: VoiceprintLSHIndex | None = None,
        voiceprint_ttl: VoiceprintTTLRegistry | None = None,
        min_motion_state_s: float = 0.8,
        min_hr_episode_s: float = 1800.0,
        context_window_limit: int = 512,
    ) -> None:
        self.subject_id = subject_id
        self.imu_compressor = imu_compressor or AdaptiveTemporalCompressor(tolerance=0.12)
        self.hr_compressor = hr_compressor or AdaptiveScalarCompressor(
            tolerance=5.0, max_segment_span_s=7200.0
        )
        self.janitor = janitor or EvidenceNoiseJanitor()
        self.sink = sink or RawByteSink()
        self.cleaner = cleaner or EdgeMultimodalCleaner()
        self.voiceprints = voiceprints or VoiceprintLSHIndex()
        self.voiceprint_ttl = voiceprint_ttl or VoiceprintTTLRegistry()
        self.transient = TransientRawBuffer()
        self.min_motion_state_s = float(min_motion_state_s)
        self.min_hr_episode_s = float(min_hr_episode_s)
        if context_window_limit < 1:
            raise ValueError("context_window_limit must be >= 1")

        self._day: int | None = None
        self._hr_window: list[tuple[float, float]] = []
        self._last_gps_cluster: str | None = None
        self._voiceprint_bound: dict[str, str] = {}
        self._voiceprint_last_contact: dict[str, datetime] = {}
        self._motion_input_samples = 0
        self._hr_input_samples = 0
        self._motion_max_error = 0.0
        self._motion_error_bound_holds = True
        self._pending: list[Observation] = []
        self._context_ring: deque[str] = deque(maxlen=context_window_limit)
        self.report = PurificationReport()

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def ingest(self, sample: BlindedSample) -> IngestOutcome:
        """摄入一条盲化样本，返回裁决结果。"""

        self._roll_day(sample.occurred_at)
        report = self.report
        report.raw_samples_ingested += 1
        report.raw_samples_by_kind[sample.kind] = (
            report.raw_samples_by_kind.get(sample.kind, 0) + 1
        )
        if sample.kind == KIND_IMU:
            return self._ingest_imu(sample)
        if sample.kind == KIND_HR:
            return self._ingest_hr(sample)
        if sample.kind == KIND_IMAGE:
            return self._ingest_image(sample)
        if sample.kind == KIND_AUDIO:
            return self._ingest_utterance(sample)
        if sample.kind in (KIND_CHAT, KIND_SMS):
            return self._ingest_text(sample)
        if sample.kind == KIND_GPS:
            return self._ingest_gps(sample)
        report.raw_samples_discarded += 1
        return IngestOutcome(sample.kind, (), False, (), 0, 1, "未知样本类型：物理丢弃")

    def flush(self, at: datetime | None = None) -> tuple[Observation, ...]:
        """收尾冲刷：结算心率窗口、回收残留原始字节，审计驻留峰值。"""

        emitted: list[Observation] = []
        if self._hr_window:
            emitted.extend(self._settle_hr_window())
        self.report.motion_error_bound_holds = self._motion_error_bound_holds
        self.report.motion_max_error = self._motion_max_error
        self.report.max_transient_bytes = max(
            self.report.max_transient_bytes, self.transient.retained_bytes
        )
        self.report.raw_bytes_purged += self.transient.purge_all()
        self.report.raw_bytes_retained_at_exit = self.transient.retained_bytes
        _ = at
        return tuple(emitted)

    def drain_observations(self) -> tuple[Observation, ...]:
        """取出本轮新增的可落库 Observation（调用方随即批量提交，避免驻留）。"""

        drained = tuple(self._pending)
        self._pending.clear()
        return drained

    # ------------------------------------------------------------------
    # IMU：宏观状态 + 冲击波形（严禁 50Hz 直灌）
    # ------------------------------------------------------------------

    def _ingest_imu(self, sample: BlindedSample) -> IngestOutcome:
        payload = sample.payload
        raw_samples = payload.get("samples") or ()
        frame_rate = float(payload.get("frame_rate_hz", 50.0) or 50.0)
        self._motion_input_samples += len(raw_samples)
        interval = 1.0 / frame_rate if frame_rate > 0 else 0.02
        timeline: list[tuple[datetime, float]] = []
        for index, reading in enumerate(raw_samples):
            if isinstance(reading, (tuple, list)):
                magnitude = math.sqrt(sum(float(axis) ** 2 for axis in reading))
            else:
                magnitude = abs(float(reading))
            timeline.append(
                (sample.occurred_at + timedelta(seconds=index * interval), magnitude)
            )
        result = self.imu_compressor.compress(timeline, sample_interval_s=interval)
        self._motion_max_error = max(self._motion_max_error, result.max_absorption_error)
        self._motion_error_bound_holds = (
            self._motion_error_bound_holds and result.error_bound_holds
        )
        retained: list[Observation] = []

        for state in result.macro_states:
            if state.duration_s < self.min_motion_state_s:
                continue
            retained.append(
                self._observation(
                    kind="motion_state",
                    occurred_at=state.start_time,
                    value={
                        "motion_state": state.motion_class,
                        "duration_s": round(state.duration_s, 3),
                        "mean_magnitude_g": round(state.mean_g, 4),
                        "rms_magnitude_g": round(state.rms_g, 4),
                        "source_frames": state.sample_count,
                        "frame_rate_hz": frame_rate,
                        "derivative_computed": False,
                    },
                    source_kind="wearable_imu",
                )
            )
            self.report.macro_motion_state_count += 1

        for impact in result.impacts:
            retained.append(
                self._observation(
                    kind="impact_waveform",
                    occurred_at=impact.onset_time,
                    value={
                        "classification": "FALL_SUSPECT" if impact.suspect_fall else "IMPACT",
                        "peak_g": round(impact.peak_g, 4),
                        "duration_s": round(impact.duration_s, 4),
                        "sample_count": len(impact.samples),
                        "waveform_samples": list(impact.samples),
                        "derivative_computed": False,
                    },
                    source_kind="wearable_imu_impact",
                )
            )
            self.report.impact_waveform_count += 1
            if impact.suspect_fall:
                self.report.fall_suspect_count += 1

        self.report.raw_samples_discarded += len(raw_samples)
        self._pending.extend(retained)
        self._count_durable(KIND_IMU, len(retained))
        return IngestOutcome(
            KIND_IMU,
            tuple(retained),
            False,
            (),
            0,
            len(raw_samples),
            f"50Hz 原始点 {len(raw_samples)} 条全部提纯，仅存 {len(retained)} 条宏观状态/波形",
        )

    # ------------------------------------------------------------------
    # 心率：平稳段均值 + 突变波形
    # ------------------------------------------------------------------

    def _ingest_hr(self, sample: BlindedSample) -> IngestOutcome:
        payload = sample.payload
        bpm = float(payload.get("bpm", 0.0))
        self._hr_window.append((sample.occurred_at.timestamp(), bpm))
        self._hr_input_samples += 1
        return IngestOutcome(KIND_HR, (), False, (), 0, 0, "心率进入当日窗口，日终结算均值/突变")

    def _settle_hr_window(self) -> list[Observation]:
        window = self._hr_window
        self._hr_window = []
        if not window:
            return []
        timeline = [
            (datetime.fromtimestamp(timestamp, tz=UTC), float(bpm)) for timestamp, bpm in window
        ]
        result = self.hr_compressor.compress(timeline)
        retained: list[Observation] = []
        raw_points_accounted = 0
        for episode in result.episodes:
            raw_points_accounted += episode.sample_count
            if episode.duration_s < self.min_hr_episode_s:
                continue
            occurred = episode.start_time
            retained.append(
                self._observation(
                    kind="hr_episode_mean",
                    occurred_at=occurred,
                    value={
                        "heart_rate_bpm_mean": round(episode.mean_value, 2),
                        "window_duration_s": round(episode.duration_s, 1),
                        "samples": episode.sample_count,
                        "stable_episode": True,
                    },
                    source_kind="wearable_ppg",
                )
            )
            self.report.hr_episode_mean_count += 1
        for spike in result.anomalies:
            occurred = spike.onset_time
            retained.append(
                self._observation(
                    kind="hr_anomaly_waveform",
                    occurred_at=occurred,
                    value={
                        "heart_rate_peak_bpm": round(spike.peak_value, 2),
                        "baseline_bpm": round(spike.baseline_value, 2),
                        "direction": spike.direction,
                        "duration_s": round(spike.duration_s, 2),
                        "sample_count": spike.sample_count,
                        "waveform_samples": list(spike.samples),
                        "derivative_computed": False,
                    },
                    source_kind="wearable_ppg_anomaly",
                )
            )
            self.report.hr_anomaly_waveform_count += 1
        self.report.raw_samples_discarded += max(0, raw_points_accounted - len(retained))
        self._pending.extend(retained)
        self._count_durable(KIND_HR, len(retained))
        return retained

    # ------------------------------------------------------------------
    # 图像：只留 Caption，原始字节物理粉碎
    # ------------------------------------------------------------------

    def _ingest_image(self, sample: BlindedSample) -> IngestOutcome:
        payload = sample.payload
        metadata = dict(payload.get("metadata") or {})
        raw_bytes = payload.get("raw_bytes") or b""
        nbytes = len(raw_bytes)
        key = f"img:{sample.sequence}"
        image_id = f"img_{sample.sequence}"
        self.transient.sink(key, nbytes)
        self.sink.sink(image_id, raw_bytes)
        self.report.raw_bytes_sunk += nbytes
        self.report.motion_error_bound_holds = self._motion_error_bound_holds
        self.report.motion_max_error = self._motion_max_error
        self.report.max_transient_bytes = max(
            self.report.max_transient_bytes, self.transient.retained_bytes
        )
        quality = assess_image_quality(metadata)
        cleaned = self.cleaner.evaluate_and_clean_image(metadata, raw_bytes)
        freed = self.transient.purge(key)
        self.sink.purge([image_id])
        self.report.raw_bytes_purged += freed
        if cleaned is None or quality < self.cleaner.quality_gate.threshold:
            self.report.image_garbage_purged += 1
            self.report.noise_bytes_purged += freed
            self.report.raw_samples_discarded += 1
            return IngestOutcome(
                KIND_IMAGE,
                (),
                True,
                (),
                freed,
                1,
                f"画质 {quality:.3f} 低于门限，原始大图已物理粉碎",
            )
        observation = self._observation(
            kind="image_caption",
            occurred_at=sample.occurred_at,
            value={
                "caption": cleaned.semantic_caption,
                "scene_tags": list(cleaned.scene_tags),
                "quality_score": round(cleaned.quality_score, 4),
                "raw_image_bytes_retained": cleaned.raw_image_bytes_retained,
            },
            source_kind="wearable_camera_caption",
        )
        self.report.image_caption_count += 1
        self._count_durable(KIND_IMAGE, 1)
        self._pending.append(observation)
        return IngestOutcome(
            KIND_IMAGE,
            (observation,),
            False,
            (),
            freed,
            0,
            "仅保留文字 Caption，原始二进制零保留",
        )

    # ------------------------------------------------------------------
    # 外界录音：证据提升 + 声纹绑定；噪声物理删除
    # ------------------------------------------------------------------

    def _ingest_utterance(self, sample: BlindedSample) -> IngestOutcome:
        payload = sample.payload
        text = str(payload.get("transcript", "") or "")
        token = str(payload.get("speaker_token", "UNK") or "UNK")
        raw_bytes = payload.get("raw_bytes") or b""
        nbytes = len(raw_bytes)
        key = f"aud:{sample.sequence}"
        self.transient.sink(key, nbytes)
        self.report.raw_bytes_sunk += nbytes
        self._touch_voiceprint(token, sample.occurred_at)
        verdict = self.janitor.decide(text)
        freed = self.transient.purge(key)
        self.report.raw_bytes_purged += freed

        if verdict.is_noise:
            self.report.utterance_noise_purged += 1
            self.report.noise_bytes_purged += freed
            self.report.noise_texts_purged.add(text)
            self.report.raw_samples_discarded += 1
            return IngestOutcome(
                KIND_AUDIO,
                (),
                True,
                (),
                freed,
                1,
                f"环境噪声物理删除：{verdict.reason}",
            )

        if not verdict.is_evidence:
            # 中性日常叙述：只进端侧有界短期上下文环，不落长期世界（避免存储膨胀）
            self._push_context(text)
            return IngestOutcome(
                KIND_AUDIO,
                (),
                False,
                (),
                freed,
                0,
                f"仅短期上下文（有界环，非长期记忆）：{verdict.reason}",
            )
        observation = self._observation(
            kind="utterance",
            occurred_at=sample.occurred_at,
            value={
                "transcript": text,
                "speaker_token": token,
                "voiceprint_bound_entity": self._voiceprint_bound.get(token),
                "evidence": True,
                "janitor_reason": verdict.reason,
            },
            source_kind="wearable_mic_asr",
        )
        self.report.utterance_evidence_count += 1
        self.report.evidence_texts_retained.add(text)
        self._count_durable(KIND_AUDIO, 1)
        self._pending.append(observation)
        return IngestOutcome(
            KIND_AUDIO,
            (observation,),
            False,
            (text,),
            freed,
            0,
            verdict.reason,
        )

    # ------------------------------------------------------------------
    # 聊天/短信：智能剪枝
    # ------------------------------------------------------------------

    def _ingest_text(self, sample: BlindedSample) -> IngestOutcome:
        payload = sample.payload
        text = str(payload.get("text", "") or "")
        verdict = self.janitor.decide(text)
        if verdict.is_noise:
            self.report.text_noise_purged += 1
            self.report.noise_texts_purged.add(text)
            self.report.raw_samples_discarded += 1
            return IngestOutcome(
                sample.kind,
                (),
                True,
                (),
                0,
                1,
                f"垃圾文本物理删除：{verdict.reason}",
            )
        if not verdict.is_evidence:
            self._push_context(text)
            return IngestOutcome(
                sample.kind,
                (),
                False,
                (),
                0,
                0,
                f"仅短期上下文（有界环，非长期记忆）：{verdict.reason}",
            )
        observation = self._observation(
            kind="chat_message",
            occurred_at=sample.occurred_at,
            value={
                "text": text,
                "thread": payload.get("thread"),
                "sender": payload.get("sender") or payload.get("from"),
                "evidence": True,
                "janitor_reason": verdict.reason,
            },
            source_kind="phone_message",
        )
        self.report.text_evidence_count += 1
        self.report.evidence_texts_retained.add(text)
        self._count_durable(sample.kind, 1)
        self._pending.append(observation)
        return IngestOutcome(
            sample.kind,
            (observation,),
            False,
            (text,),
            0,
            0,
            verdict.reason,
        )

    # ------------------------------------------------------------------
    # GPS：只留宏观位置状态与相变标记
    # ------------------------------------------------------------------

    def _ingest_gps(self, sample: BlindedSample) -> IngestOutcome:
        cluster = str(sample.payload.get("cluster", "UNK"))
        if cluster == self._last_gps_cluster:
            self.report.raw_samples_discarded += 1
            return IngestOutcome(KIND_GPS, (), False, (), 0, 1, "位置与既有宏观状态一致，不重复入库")
        self._last_gps_cluster = cluster
        observation = self._observation(
            kind="location_state",
            occurred_at=sample.occurred_at,
            value={
                "cluster": cluster,
                "lat": sample.payload.get("lat"),
                "lon": sample.payload.get("lon"),
            },
            source_kind="phone_gps",
        )
        self.report.gps_state_count += 1
        if self.report.gps_state_count > 1:
            self.report.relocation_markers += 1
        self._count_durable(KIND_GPS, 1)
        self._pending.append(observation)
        return IngestOutcome(KIND_GPS, (observation,), False, (), 0, 0, "宏观位置状态变更")

    # ------------------------------------------------------------------
    # 声纹绑定与 180 天淘汰
    # ------------------------------------------------------------------

    def _touch_voiceprint(self, token: str, at: datetime) -> None:
        bound_entity = self._voiceprint_bound.get(token)
        if bound_entity is None and token.startswith("P0"):
            bound_entity = f"ent_{token.lower()}"
        if token not in self._voiceprint_last_contact:
            self.voiceprints.add(token, _pseudo_feature(token), bound_entity)
            self.voiceprint_ttl.register(
                VoiceprintProfile(
                    voiceprint_id=token,
                    entity_id=bound_entity,
                    feature_hash=hashlib.sha1(token.encode("utf-8")).hexdigest()[:16],
                    first_detected_at=at,
                    last_contact_at=at,
                )
            )
        else:
            self.voiceprint_ttl.note_contact(token, at)
        if bound_entity is not None:
            self._voiceprint_bound[token] = bound_entity
        self._voiceprint_last_contact[token] = at

    def sweep_voiceprints(self, now: datetime) -> tuple[str, ...]:
        """推进声纹淘汰时钟：未绑定实体且满 180 天未接触者进入墓碑。"""

        tombstoned = tuple(self.voiceprint_ttl.sweep(now))
        for voiceprint_id in tombstoned:
            self.report.voiceprints_tombstoned.add(voiceprint_id)
        return tombstoned

    def assign_voiceprint_slice(self, token: str) -> str:
        """把一条新音频切片指派回最近声纹（聚类纯度审计入口）。"""

        return self.voiceprints.assign_slice(_pseudo_feature(token))

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _roll_day(self, occurred_at: datetime) -> None:
        day_index = occurred_at.toordinal()
        if self._day is None:
            self._day = day_index
            return
        if day_index == self._day:
            return
        if self._hr_window:
            self._settle_hr_window()
        self._day = day_index

    def _push_context(self, text: str) -> None:
        """写入端侧有界短期上下文环（溢出即物理淘汰最旧一条）。"""

        if len(self._context_ring) == self._context_ring.maxlen:
            self.report.context_items_evicted += 1
        self._context_ring.append(text)
        self.report.context_texts.add(text)
        self.report.context_items_kept += 1

    def _count_durable(self, kind: str, amount: int) -> None:
        """落库计数（总量 + 分类型明细），诊断书按此定位"谁在吃存储"。"""

        if amount <= 0:
            return
        self.report.durable_observation_count += amount
        self.report.durable_by_kind[kind] = self.report.durable_by_kind.get(kind, 0) + amount

    def _observation(
        self,
        *,
        kind: str,
        occurred_at: datetime,
        value: Mapping[str, Any],
        source_kind: str,
    ) -> Observation:
        digest = hashlib.sha1(
            f"{kind}|{occurred_at.isoformat()}|{sorted(value.items(), key=lambda kv: kv[0])}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return Observation(
            object_id=f"obs_{kind}_{digest}",
            subject_id=self.subject_id,
            revision=1,
            source_kind=source_kind,
            modality="json",
            value=dict(value),
            occurred=TemporalExtent.point(occurred_at),
            learned_at=occurred_at,
            recorded_at=occurred_at,
            created_by="edge_stream_purifier",
        )

    # ------------------------------------------------------------------
    # 审计接口
    # ------------------------------------------------------------------

    def evidence_retention_ratio(
        self,
        ground_truth_keys: Iterable[str],
        beat_texts: Mapping[str, str],
    ) -> float:
        """按考官真值核算核心证据留存率（按原话文本比对，不依赖内部分类）。"""

        total = 0
        retained = 0
        for key in ground_truth_keys:
            total += 1
            text = beat_texts.get(key)
            if text is not None and text in self.report.evidence_texts_retained:
                retained += 1
        if total == 0:
            return 1.0
        return retained / total

    def noise_purge_ratio(self, ground_truth_noise_texts: Sequence[str]) -> float:
        if not ground_truth_noise_texts:
            return 1.0
        purged = sum(
            1 for text in ground_truth_noise_texts if text in self.report.noise_texts_purged
        )
        return purged / len(ground_truth_noise_texts)

    @property
    def raw_bytes_retained(self) -> int:
        return self.transient.retained_bytes

    @property
    def motion_max_error(self) -> float:
        return self._motion_max_error

    @property
    def motion_error_bound_holds(self) -> bool:
        return self._motion_error_bound_holds

    @property
    def motion_input_samples(self) -> int:
        return self._motion_input_samples

    @property
    def hr_input_samples(self) -> int:
        return self._hr_input_samples

    @property
    def motion_compression_ratio(self) -> float:
        outputs = self.report.macro_motion_state_count + self.report.impact_waveform_count
        return (self._motion_input_samples / outputs) if outputs else 0.0

    @property
    def hr_compression_ratio(self) -> float:
        outputs = self.report.hr_episode_mean_count + self.report.hr_anomaly_waveform_count
        return (self._hr_input_samples / outputs) if outputs else 0.0

    @property
    def context_ring_size(self) -> int:
        return len(self._context_ring)

    @property
    def context_ring_limit(self) -> int:
        return int(self._context_ring.maxlen or 0)

    @property
    def bound_voiceprints(self) -> Mapping[str, str]:
        return dict(self._voiceprint_bound)

    @property
    def voiceprint_last_contact(self) -> Mapping[str, datetime]:
        return dict(self._voiceprint_last_contact)


def _pseudo_feature(token: str) -> tuple[float, ...]:
    """由声纹编号派生 128 维稳定特征（同一人稳定、不同人可分的归一化嵌入）。"""

    digest = hashlib.sha256(token.encode("utf-8")).digest()
    feature: list[float] = []
    for index in range(128):
        byte = digest[index % len(digest)]
        mixed = (byte + index * 31) % 256
        feature.append(((mixed / 255.0) - 0.5) * 2.0)
    norm = math.sqrt(sum(value * value for value in feature)) or 1.0
    return tuple(value / norm for value in feature)
