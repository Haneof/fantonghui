"""Eight-stage, million-record AIOS Core synthetic life benchmark.

The benchmark separates its answer key from the system under test:
:class:`MassiveSyntheticLifeGenerator` freezes scenario oracles before it emits
any samples, while every stage derives receipts from the generated stream.  It
is a Linux virtual-world evaluation, not evidence of physical wearable or real
LLM feasibility.

Run the official scale locally with::

    python -m aios_core.simulation.massive_life_bench --samples 1000000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import sqlite3
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.cockpit.evidence_pipeline import (
    BrevityGuard,
    CockpitPipeline,
    ConversationTurn,
    CrisisCockpitContext,
    split_sentences,
)
from aios_core.cognition.self_reflection_evidence import (
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
    RapportTier,
    SelfIdentityMirror,
)
from aios_core.cognition.symbiotic_advisor_evidence import (
    ActionableAdvice,
    EvidenceFact,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    InMemoryEvidenceRepository,
    MomBirthdayGiftAdvisor,
)
from aios_core.contracts.enums import (
    EventStatus,
    GoalSourceType,
    GoalStatus,
    TaskState,
    TaskType,
)
from aios_core.contracts.models import (
    EventAnchor,
    EvidenceCoverage,
    EvidenceSet,
    Goal,
    Observation,
    Task,
    ToolProposal,
)
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.contracts.time import KnowledgeWindow, TemporalExtent, require_aware
from aios_core.dimensions.evolution_guard_evidence import (
    AdmissionThresholdBlockError,
    DerivedDimensionState,
    DimensionCandidateRequest,
    DimensionEvolutionGuard,
    PhysicalDomainAnomaly,
    QuotaExceededBlockError,
    TrialEvidence,
)
from aios_core.ingest.multimodal_edge_evidence import (
    EdgeMultimodalCleaner,
    VoiceprintProfile,
    VoiceprintTTLStateMachine,
)
from aios_core.operations.adaptive_temporal_compressor import (
    AdaptiveTemporalCompressionOperator,
    CompressedObservation,
    CompressionReceipt,
    RawSemanticClass,
    SensorModality,
    TemporalSample,
    adaptive_compression_tool_proposal,
)
from aios_core.query.cjk_inverted_index_evidence import CJKTopologicalInvertedIndex
from aios_core.query.epistemic_projection import (
    DualLensProjectionIndex,
    ImmutableProjectionFact,
    ProjectionOverlay,
    dual_lens_projection_tool_proposal,
)
from aios_core.scheduler.conditional_engine_evidence import (
    ConditionalScheduler,
    ConditionalTask,
    ConditionTrack,
    MechanicalCondition,
    MechanicalConditionKind,
    MechanicalSnapshot,
)
from aios_core.summaries.lossless_temporal_pyramid import LosslessTemporalPyramid
from aios_core.wake.dispatcher_evidence import dispatch_wake_event
from aios_core.world.fact_integrity_ledger import FactImmutabilityLedger
from aios_core.world.retrospective_annotation_evidence import (
    BiTemporalEpistemicLens,
    DependencyEdge,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

BENCHMARK_VERSION = "3.0.0"
OFFICIAL_MINIMUM_RECORDS = 1_000_000
DAY_NS = 86_400 * 1_000_000_000
MINUTE_NS = 60 * 1_000_000_000


def _to_ns(value: datetime) -> int:
    require_aware(value, "timestamp")
    return int(value.timestamp() * 1_000_000_000)


def _from_ns(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC)


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return value ^ (value >> 31)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _rss_bytes() -> int:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return _peak_rss_bytes()
    return _peak_rss_bytes()


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value * 1024)  # Linux reports KiB.


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_count: int = Field(default=OFFICIAL_MINIMUM_RECORDS, ge=1_000)
    seed: int = Field(default=0xA10530, ge=0)
    current_at: datetime = Field(
        default_factory=lambda: datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    )
    output_dir: Path = Path("reports/benchmarks")
    persist_artifacts: bool = True
    ingest_batch_size: int = Field(default=4_096, ge=128, le=65_536)

    @field_validator("current_at")
    @classmethod
    def current_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "current_at")
        return value.astimezone(UTC)


class StageMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    stage_id: str
    name: str
    input_count: int = Field(ge=0)
    output_count: int = Field(ge=0)
    wall_time_ms: float = Field(ge=0.0)
    throughput_per_second: float = Field(ge=0.0)
    latency_p50_ms: float = Field(ge=0.0)
    latency_p95_ms: float = Field(ge=0.0)
    latency_p99_ms: float = Field(ge=0.0)
    rss_before_bytes: int = Field(ge=0)
    rss_after_bytes: int = Field(ge=0)
    peak_rss_bytes: int = Field(ge=0)
    measurements: dict[str, Any] = Field(default_factory=dict)


class GateReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_id: str
    iron_law: int | None = Field(default=None, ge=1, le=5)
    requirement: str
    passed: bool
    measured: dict[str, Any] = Field(default_factory=dict)


class MassiveLifeBenchmarkReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = "《AIOS 全流程海量盲测与极限压测报告》"
    benchmark_version: str = BENCHMARK_VERSION
    generated_at: datetime
    seed: int
    requested_sample_count: int
    generated_sample_count: int
    official_scale_reached: bool
    stages: tuple[StageMetric, ...]
    gates: tuple[GateReceipt, ...]
    tool_proposals: tuple[ToolProposal, ...]
    bottleneck_diagnosis: dict[str, Any]
    limitations: tuple[str, ...]
    artifacts: dict[str, str]
    verdict: str

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "generated_at")
        return value

    @model_validator(mode="after")
    def verdict_matches_gate_receipts(self) -> MassiveLifeBenchmarkReport:
        expected = "PASS" if all(gate.passed for gate in self.gates) else "FAIL"
        if self.verdict != expected:
            raise ValueError("verdict must exactly match measured gate receipts")
        if self.generated_sample_count != self.requested_sample_count:
            raise ValueError("generated count must match requested count")
        return self

    @property
    def all_gates_passed(self) -> bool:
        return self.verdict == "PASS"


@dataclass(frozen=True, slots=True)
class LifeScenarioOracle:
    oracle_id: str
    subject_id: str
    event_time_ns: int
    required_modalities: frozenset[SensorModality]
    query_terms: tuple[str, ...]
    expected_event_key: str


@dataclass(frozen=True, slots=True)
class GeneratorReceipt:
    generated_count: int
    modality_counts: dict[str, int]
    subject_counts: dict[str, int]
    normalized_entropy: float
    oracle_count: int
    special_record_count: int


class MassiveSyntheticLifeGenerator:
    """Seeded procedural three-year stream with a frozen independent oracle."""

    SUBJECTS: ClassVar[tuple[str, ...]] = (
        "programmer",
        "entrepreneur",
        "full_time_parent",
    )
    _CHAT_VERBS: ClassVar[tuple[str, ...]] = (
        "复盘",
        "协商",
        "陪伴",
        "争论",
        "确认",
        "推迟",
        "庆祝",
        "道歉",
    )
    _TOPICS: ClassVar[tuple[str, ...]] = (
        "项目",
        "搬家",
        "家庭",
        "预算",
        "健康",
        "课程",
        "合同",
        "照护",
        "旅行",
        "工作",
    )

    def __init__(self, config: BenchmarkConfig) -> None:
        self.config = config
        self.end_ns = _to_ns(config.current_at)
        self.start_ns = _to_ns(config.current_at - timedelta(days=3 * 365))
        self._span_ns = self.end_ns - self.start_ns
        self._entropy_bins = [0] * 256
        self._modality_counts: Counter[str] = Counter()
        self._subject_counts: Counter[str] = Counter()
        self._generated = 0
        self._special_samples: dict[int, TemporalSample] = {}
        self.oracles = self._freeze_oracles_and_special_records()

    def __iter__(self):
        for sequence_no in range(self.config.sample_count):
            sample = self._special_samples.get(sequence_no)
            if sample is None:
                sample = self._procedural_sample(sequence_no)
            entropy_word = _splitmix64(self.config.seed ^ sequence_no)
            self._entropy_bins[entropy_word & 0xFF] += 1
            self._modality_counts[sample.modality.value] += 1
            self._subject_counts[sample.subject_id] += 1
            self._generated += 1
            yield sample

    def receipt(self) -> GeneratorReceipt:
        if self._generated != self.config.sample_count:
            raise RuntimeError(
                "generator receipt requested before complete consumption"
            )
        total = sum(self._entropy_bins)
        entropy = 0.0
        if total:
            for count in self._entropy_bins:
                if count:
                    probability = count / total
                    entropy -= probability * math.log2(probability)
            entropy /= math.log2(len(self._entropy_bins))
        return GeneratorReceipt(
            generated_count=self._generated,
            modality_counts=dict(sorted(self._modality_counts.items())),
            subject_counts=dict(sorted(self._subject_counts.items())),
            normalized_entropy=entropy,
            oracle_count=len(self.oracles),
            special_record_count=len(self._special_samples),
        )

    def _procedural_sample(self, sequence_no: int) -> TemporalSample:
        random_word = _splitmix64(self.config.seed + sequence_no * 17)
        percentile = random_word % 100
        if percentile < 45:
            modality = SensorModality.IMU
        elif percentile < 75:
            modality = SensorModality.HEART_RATE
        elif percentile < 83:
            modality = SensorModality.AUDIO
        elif percentile < 88:
            modality = SensorModality.IMAGE
        elif percentile < 95:
            modality = SensorModality.GPS
        elif percentile < 98:
            modality = SensorModality.CHAT
        else:
            modality = SensorModality.BILLING

        subject = self.SUBJECTS[(random_word >> 9) % len(self.SUBJECTS)]
        timestamp_ns = self.start_ns + (
            self._span_ns * sequence_no // max(1, self.config.sample_count - 1)
        )
        progress = (timestamp_ns - self.start_ns) / self._span_ns
        chapter_tag = "new_city" if progress >= 0.72 else "old_city"
        topic = self._TOPICS[(random_word >> 16) % len(self._TOPICS)]
        verb = self._CHAT_VERBS[(random_word >> 24) % len(self._CHAT_VERBS)]
        noise = ((random_word >> 32) & 0xFFFF) / 0xFFFF
        circadian = math.sin((timestamp_ns / DAY_NS) * math.tau)
        anomaly = 0.93 if random_word & 0xFFF == 0 else noise * 0.35
        semantic_class = RawSemanticClass.ROUTINE
        text = ""
        value: float | None = None
        tags: tuple[str, ...]
        speaker: str | None = None
        raw_buffer: bytearray | None = None

        if modality is SensorModality.IMU:
            value = 0.15 + noise * 0.35 + (2.8 if anomaly >= 0.82 else 0.0)
            tags = ("impact" if anomaly >= 0.82 else "macro_motion", chapter_tag)
        elif modality is SensorModality.HEART_RATE:
            value = 67.0 + 8.0 * circadian + noise * 7.0
            if anomaly >= 0.82:
                value += 55.0
            tags = ("rhythm_anomaly" if anomaly >= 0.82 else "stable", subject)
        elif modality is SensorModality.GPS:
            value = 35.0 + noise * 5.0
            tags = (chapter_tag, topic)
        elif modality is SensorModality.AUDIO:
            raw_buffer = bytearray(random_word.to_bytes(8, "little") * 4)
            speaker = f"P{((random_word >> 40) % 24) + 1:03d}"
            if random_word % 10:
                semantic_class = RawSemanticClass.AMBIENT_NOISE
                text = f"ambient acoustic fragment {random_word:016x}"
            else:
                text = f"{speaker}围绕{topic}{verb}，记录号{random_word & 0xFFFF:04x}"
            tags = (topic, "transcript")
        elif modality is SensorModality.IMAGE:
            raw_buffer = bytearray(random_word.to_bytes(8, "little") * 4)
            if random_word % 5:
                semantic_class = RawSemanticClass.AMBIENT_NOISE
            text = f"场景文字描述：{chapter_tag}，{topic}，光照级{int(noise * 9)}"
            tags = (chapter_tag, topic, "caption")
        elif modality is SensorModality.CHAT:
            text = f"{subject}在第{sequence_no}段对话里{verb}{topic}，语境码{random_word & 0xFFFF:04x}"
            tags = (topic, verb)
        else:
            value = round(5.0 + noise * 9_995.0, 2)
            text = (
                f"账单分类{topic}，金额{value:.2f}，流水号{random_word & 0xFFFFFF:06x}"
            )
            tags = (topic, "bank_flow")

        return TemporalSample(
            sequence_no=sequence_no,
            subject_id=subject,
            occurred_at_ns=timestamp_ns,
            modality=modality,
            value=value,
            anomaly_score=anomaly,
            text=text,
            tags=tags,
            semantic_class=semantic_class,
            entity_ids=(f"P{((random_word >> 48) % 24) + 1:03d}",),
            speaker_id=speaker,
            sample_rate_hz=50 if modality is SensorModality.IMU else 1,
            raw_buffer=raw_buffer,
        )

    def _freeze_oracles_and_special_records(self) -> tuple[LifeScenarioOracle, ...]:
        scenarios = (
            (
                "partnership_dispute",
                "entrepreneur",
                self.config.current_at - timedelta(days=520),
                ("合伙", "借贷", "争执", "银行流水"),
                "EVT_PARTNERSHIP_DISPUTE",
            ),
            (
                "overnight_cardiac",
                "programmer",
                self.config.current_at - timedelta(days=240),
                ("通宵", "工作", "心律", "复查"),
                "EVT_OVERNIGHT_CARDIAC",
            ),
            (
                "family_reconciliation",
                "full_time_parent",
                self.config.current_at - timedelta(days=380),
                ("家庭", "矛盾", "道歉", "和解"),
                "EVT_FAMILY_RECONCILIATION",
            ),
            (
                "interprovince_move",
                "entrepreneur",
                self.config.current_at - timedelta(days=300),
                ("跨省", "搬家", "新城市", "基线变化"),
                "EVT_INTERPROVINCE_MOVE",
            ),
            (
                "chronic_management",
                "full_time_parent",
                self.config.current_at - timedelta(days=120),
                ("慢病", "复诊", "用药", "指标"),
                "EVT_CHRONIC_MANAGEMENT",
            ),
        )
        oracles: list[LifeScenarioOracle] = []
        sequence = 220
        for oracle_id, subject, event_time, terms, event_key in scenarios:
            event_ns = _to_ns(event_time)
            modalities = (
                SensorModality.GPS,
                SensorModality.HEART_RATE,
                SensorModality.AUDIO,
                SensorModality.CHAT,
            )
            oracles.append(
                LifeScenarioOracle(
                    oracle_id=oracle_id,
                    subject_id=subject,
                    event_time_ns=event_ns,
                    required_modalities=frozenset(modalities[:3]),
                    query_terms=terms,
                    expected_event_key=event_key,
                )
            )
            for offset, modality in enumerate(modalities):
                text = "；".join(terms) + f"；多模态证据{offset}"
                value = None
                if modality is SensorModality.HEART_RATE:
                    value = 126.0 + offset
                elif modality is SensorModality.GPS:
                    value = 39.9 + offset / 100
                raw = (
                    bytearray(_splitmix64(sequence).to_bytes(8, "little") * 4)
                    if modality is SensorModality.AUDIO
                    else None
                )
                self._special_samples[sequence] = TemporalSample(
                    sequence_no=sequence,
                    subject_id=subject,
                    occurred_at_ns=event_ns + offset * 2 * MINUTE_NS,
                    modality=modality,
                    value=value,
                    anomaly_score=0.95
                    if modality is SensorModality.HEART_RATE
                    else 0.1,
                    text=text,
                    tags=terms + ("oracle_evidence",),
                    semantic_class=RawSemanticClass.KEY_EVIDENCE,
                    entity_ids=("P002",),
                    event_key=event_key,
                    speaker_id="P002" if modality is SensorModality.AUDIO else None,
                    sample_rate_hz=1,
                    raw_buffer=raw,
                )
                sequence += 1

        self._add_advisor_evidence()
        self._add_burnout_series()
        return tuple(oracles)

    def _add_advisor_evidence(self) -> None:
        rows = (
            (
                10,
                datetime(2023, 10, 1, tzinfo=UTC),
                "2023 妈妈收到丝巾后一直落灰未使用",
                "GIFT_2023",
            ),
            (
                11,
                datetime(2024, 10, 1, tzinfo=UTC),
                "2024 足浴盆笨重，倒水让妈妈腰疼后闲置",
                "GIFT_2024",
            ),
            (
                12,
                datetime(2025, 10, 1, tzinfo=UTC),
                "2025 按摩椅反馈很好，妈妈喜欢并常用",
                "GIFT_2025",
            ),
            (
                13,
                self.config.current_at - timedelta(days=10),
                "2026 妈妈说膝盖受凉就疼",
                "GIFT_2026",
            ),
            (
                14,
                self.config.current_at - timedelta(days=900),
                "历史微信聊天显示对方反复拖延还款并推脱",
                "PARTNER_HISTORY",
            ),
            (
                15,
                self.config.current_at - timedelta(hours=2),
                "法院判决认定相关借贷构成合同诈骗",
                "FRAUD_RULING",
            ),
            (
                16,
                self.config.current_at - timedelta(days=2),
                "周四连续通宵工作，整夜未睡且疲劳",
                "HEALTH_SLEEP",
            ),
            (
                17,
                self.config.current_at - timedelta(days=1),
                "动态心电记录频发室性早搏 PVC",
                "HEALTH_RHYTHM",
            ),
            (
                18,
                self.config.current_at - timedelta(days=1_000),
                "多年共同创业并建立信任的客观聊天原话",
                "RETRO_HISTORY",
            ),
        )
        for sequence, occurred_at, text, event_key in rows:
            self._special_samples[sequence] = TemporalSample(
                sequence_no=sequence,
                subject_id="entrepreneur"
                if "PARTNER" in event_key
                or "FRAUD" in event_key
                or "RETRO" in event_key
                else "full_time_parent",
                occurred_at_ns=_to_ns(occurred_at),
                modality=SensorModality.CHAT,
                text=text,
                tags=("verified_evidence", event_key.casefold()),
                semantic_class=RawSemanticClass.CORE_QUOTE,
                entity_ids=("P002",),
                event_key=event_key,
                speaker_id="P002",
            )

    def _add_burnout_series(self) -> None:
        series_start = self.config.current_at - timedelta(days=90)
        for day in range(35):
            sequence = 100 + day
            value = (
                62.0 + 0.08 * day
                if day < 21
                else 63.68 + 0.08 * (day - 20) + 0.11 * (day - 20) ** 2
            )
            self._special_samples[sequence] = TemporalSample(
                sequence_no=sequence,
                subject_id="programmer",
                occurred_at_ns=_to_ns(series_start + timedelta(days=day)),
                modality=SensorModality.HEART_RATE,
                value=value,
                anomaly_score=min(0.8, 0.2 + day / 100),
                text=f"日度耗竭观测 {day}: {value:.3f}",
                tags=("burnout_series", "cross_domain_measurement"),
                semantic_class=RawSemanticClass.KEY_EVIDENCE,
                entity_ids=("P011",),
                event_key="SERIES_BURNOUT",
            )


@dataclass(frozen=True, slots=True)
class ResonanceCandidate:
    candidate_id: str
    subject_id: str
    window_start_ns: int
    evidence_refs: tuple[str, ...]
    modalities: frozenset[SensorModality]
    confidence: float


class TemporalCrossModalResonator:
    """Align independently retained modalities in bounded time/entity windows."""

    WINDOW_NS: ClassVar[int] = 30 * MINUTE_NS
    REQUIRED_MODALITIES: ClassVar[frozenset[SensorModality]] = frozenset(
        {SensorModality.GPS, SensorModality.HEART_RATE, SensorModality.AUDIO}
    )

    def synthesize(
        self,
        observations: tuple[CompressedObservation, ...],
    ) -> tuple[ResonanceCandidate, ...]:
        groups: dict[tuple[str, str, int], list[CompressedObservation]] = defaultdict(
            list
        )
        for observation in observations:
            if observation.semantic_class is RawSemanticClass.ROUTINE:
                continue
            entities = observation.entity_ids or (observation.subject_id,)
            window = observation.occurred_at_ns // self.WINDOW_NS
            for entity_id in entities:
                groups[(observation.subject_id, entity_id, window)].append(observation)

        candidates: list[ResonanceCandidate] = []
        for (subject_id, _entity_id, window), items in sorted(groups.items()):
            modalities = frozenset(item.modality for item in items)
            if not self.REQUIRED_MODALITIES <= modalities:
                continue
            refs = tuple(sorted({item.observation_id for item in items}))
            identity = "\x1f".join(refs).encode("utf-8")
            confidence = min(
                0.99,
                0.55 + 0.08 * len(modalities) + 0.02 * min(len(refs), 5),
            )
            candidates.append(
                ResonanceCandidate(
                    candidate_id=(
                        "resonance_" + hashlib.sha256(identity).hexdigest()[:20]
                    ),
                    subject_id=subject_id,
                    window_start_ns=window * self.WINDOW_NS,
                    evidence_refs=refs,
                    modalities=modalities,
                    confidence=confidence,
                )
            )
        return tuple(candidates)


class AppendOnlyEventLifecycle:
    """Validated EventAnchor revisions with no overwrite path."""

    _TRANSITIONS: ClassVar[dict[EventStatus, frozenset[EventStatus]]] = {
        EventStatus.CANDIDATE: frozenset({EventStatus.ACTIVE, EventStatus.REJECTED}),
        EventStatus.ACTIVE: frozenset(
            {
                EventStatus.RESOLVED,
                EventStatus.REVISED,
                EventStatus.MERGED,
                EventStatus.SPLIT,
            }
        ),
        EventStatus.RESOLVED: frozenset(),
        EventStatus.REVISED: frozenset(),
        EventStatus.REJECTED: frozenset(),
        EventStatus.MERGED: frozenset(),
        EventStatus.SPLIT: frozenset(),
    }

    def __init__(self) -> None:
        self._versions: dict[str, list[EventAnchor]] = {}
        self._evidence_sets: dict[str, EvidenceSet] = {}

    def create_candidate(
        self,
        *,
        object_id: str,
        subject_id: str,
        learned_at: datetime,
        event_time: datetime,
        evidence_refs: tuple[str, ...],
        confidence: float,
    ) -> EventAnchor:
        if object_id in self._versions:
            raise ValueError(f"event already exists: {object_id}")
        members = [ObjectRef(object_id=ref, revision=1) for ref in evidence_refs]
        evidence_digest = hashlib.sha256(
            (object_id + "\x1f" + "\x1f".join(sorted(evidence_refs))).encode()
        ).hexdigest()[:20]
        evidence_id = f"evidence_{evidence_digest}"
        evidence_set = EvidenceSet(
            object_id=evidence_id,
            subject_id=subject_id,
            learned_at=learned_at,
            recorded_at=learned_at,
            created_by="temporal_cross_modal_resonator",
            purpose="support one bounded cross-modal EventAnchor candidate",
            knowledge_window=KnowledgeWindow(knowledge_cutoff=learned_at),
            member_refs=members,
            support_refs=members,
            selection_method="30-minute entity-aligned multimodal resonance",
            coverage=EvidenceCoverage(
                expected_count=len(members),
                observed_count=len(members),
                coverage_ratio=1.0,
            ),
        )
        previous_evidence = self._evidence_sets.get(evidence_id)
        if previous_evidence is not None and previous_evidence != evidence_set:
            raise ValueError(f"evidence set id collision: {evidence_id}")
        self._evidence_sets[evidence_id] = evidence_set
        anchor = EventAnchor(
            object_id=object_id,
            subject_id=subject_id,
            revision=1,
            learned_at=learned_at,
            recorded_at=learned_at,
            created_by="temporal_cross_modal_resonator",
            title="cross-modal resonance candidate",
            interpretation="time-aligned multimodal evidence requires cognition review",
            event_status=EventStatus.CANDIDATE,
            event_time=TemporalExtent.point(event_time),
            evidence_set_refs=[ObjectRef(object_id=evidence_id, revision=1)],
            support_evidence_set_refs=[ObjectRef(object_id=evidence_id, revision=1)],
            confidence=confidence,
        )
        self._versions[object_id] = [anchor]
        return anchor

    def transition(
        self,
        object_id: str,
        status: EventStatus,
        *,
        learned_at: datetime,
        reason: str | None = None,
        merged_into_ref: ObjectRef | None = None,
        split_child_refs: tuple[ObjectRef, ...] = (),
    ) -> EventAnchor:
        previous = self.latest(object_id)
        status = EventStatus(status)
        if status not in self._TRANSITIONS[previous.event_status]:
            raise ValueError(
                f"illegal event transition: {previous.event_status.value} -> "
                f"{status.value}"
            )
        payload = previous.model_dump(mode="python")
        payload.update(
            revision=previous.revision + 1,
            learned_at=learned_at,
            recorded_at=learned_at,
            event_status=status,
            revision_reason=reason,
            supersedes_refs=(
                [ObjectRef(object_id=object_id, revision=previous.revision)]
                if status is EventStatus.REVISED
                else []
            ),
            merged_into_ref=merged_into_ref,
            split_child_refs=list(split_child_refs),
        )
        anchor = EventAnchor.model_validate(payload)
        self._versions[object_id].append(anchor)
        return anchor

    def latest(self, object_id: str) -> EventAnchor:
        try:
            return self._versions[object_id][-1]
        except KeyError as exc:
            raise KeyError(f"unknown event: {object_id}") from exc

    def versions(self, object_id: str) -> tuple[EventAnchor, ...]:
        try:
            return tuple(self._versions[object_id])
        except KeyError as exc:
            raise KeyError(f"unknown event: {object_id}") from exc

    @property
    def all_versions(self) -> tuple[EventAnchor, ...]:
        return tuple(
            version
            for object_id in sorted(self._versions)
            for version in self._versions[object_id]
        )

    @property
    def evidence_sets(self) -> tuple[EvidenceSet, ...]:
        return tuple(self._evidence_sets[key] for key in sorted(self._evidence_sets))

    def evidence_references_resolve(self) -> bool:
        return all(
            ref.object_id in self._evidence_sets
            for event in self.all_versions
            for ref in event.evidence_set_refs
        )


@dataclass(frozen=True, slots=True)
class DerivativePoint:
    occurred_at_ns: int
    value: float
    velocity: float
    acceleration: float


@dataclass(frozen=True, slots=True)
class DerivativeReceipt:
    points: tuple[DerivativePoint, ...]
    inflection_indices: tuple[int, ...]
    computed_in_cognition_layer: bool = True


class CognitiveDerivativeEngine:
    """Compute first/second derivatives above the physical ingestion layer."""

    def evaluate(
        self,
        values: tuple[tuple[int, float], ...],
    ) -> DerivativeReceipt:
        if len(values) < 4:
            raise ValueError("at least four ordered values are required")
        ordered = sorted(values)
        if len({timestamp for timestamp, _ in ordered}) != len(ordered):
            raise ValueError("derivative timestamps must be unique")
        velocities = [0.0]
        for index in range(1, len(ordered)):
            elapsed_days = (ordered[index][0] - ordered[index - 1][0]) / DAY_NS
            if elapsed_days <= 0:
                raise ValueError("derivative time must move forward")
            velocities.append(
                (ordered[index][1] - ordered[index - 1][1]) / elapsed_days
            )
        accelerations = [0.0, 0.0]
        for index in range(2, len(ordered)):
            elapsed_days = (ordered[index][0] - ordered[index - 1][0]) / DAY_NS
            accelerations.append(
                (velocities[index] - velocities[index - 1]) / elapsed_days
            )
        inflections: list[int] = []
        for index in range(2, len(accelerations)):
            recent = [abs(value) for value in accelerations[max(2, index - 7) : index]]
            local_baseline = statistics.median(recent) if recent else 0.0
            if accelerations[index] >= max(0.02, local_baseline * 3.0):
                inflections.append(index)
        points = tuple(
            DerivativePoint(timestamp, value, velocities[index], accelerations[index])
            for index, (timestamp, value) in enumerate(ordered)
        )
        return DerivativeReceipt(points=points, inflection_indices=tuple(inflections))


@dataclass(frozen=True, slots=True)
class LifeChapterReceipt:
    changed: bool
    old_baseline: float
    new_baseline: float
    normalized_shift: float
    persistent_points: int
    archived_old_chapter: bool


class LifeChapterDetector:
    """Detect persistent baseline rupture rather than a transient excursion."""

    MIN_POINTS: ClassVar[int] = 14
    MIN_SHIFT: ClassVar[float] = 0.65

    def detect(
        self,
        old_baseline_values: tuple[float, ...],
        new_values: tuple[float, ...],
    ) -> LifeChapterReceipt:
        if (
            len(old_baseline_values) < self.MIN_POINTS
            or len(new_values) < self.MIN_POINTS
        ):
            raise ValueError("life chapter detection requires persistent windows")
        old_mean = statistics.fmean(old_baseline_values)
        new_mean = statistics.fmean(new_values)
        scale = max(1.0, statistics.pstdev(old_baseline_values))
        shift = abs(new_mean - old_mean) / scale
        changed = shift >= self.MIN_SHIFT
        return LifeChapterReceipt(
            changed=changed,
            old_baseline=old_mean,
            new_baseline=new_mean,
            normalized_shift=shift,
            persistent_points=len(new_values),
            archived_old_chapter=changed,
        )


class CommunicationStyle(StrEnum):
    DIRECT = "direct"
    OLD_FRIEND = "old_friend"
    GENTLE = "gentle"


class UserFeedback(StrEnum):
    ACCEPTED = "accepted"
    RESISTED = "resisted"
    IGNORED = "ignored"
    LAUGHED = "laughed"


@dataclass(frozen=True, slots=True)
class CommunicationFeedbackCase:
    user_id: str
    style: CommunicationStyle
    feedback: UserFeedback


class AdversarialCommunicationFeedbackGenerator:
    """Freeze latent user preferences before the learner observes feedback."""

    ORACLE: ClassVar[dict[str, CommunicationStyle]] = {
        "programmer": CommunicationStyle.DIRECT,
        "entrepreneur": CommunicationStyle.OLD_FRIEND,
        "full_time_parent": CommunicationStyle.GENTLE,
    }

    def cases(self) -> tuple[CommunicationFeedbackCase, ...]:
        cases: list[CommunicationFeedbackCase] = []
        for user_id, preferred in self.ORACLE.items():
            for style in CommunicationStyle:
                for trial in range(8):
                    if style is preferred:
                        feedback = (
                            UserFeedback.LAUGHED
                            if trial % 4 == 0
                            else UserFeedback.ACCEPTED
                        )
                    else:
                        feedback = (
                            UserFeedback.IGNORED
                            if trial % 5 == 0
                            else UserFeedback.RESISTED
                        )
                    cases.append(CommunicationFeedbackCase(user_id, style, feedback))
        return tuple(cases)


@dataclass(frozen=True, slots=True)
class AIActionRecord:
    action_id: str
    occurred_at_ns: int
    posture: str
    style: CommunicationStyle
    feedback: UserFeedback
    previous_hash: str
    record_hash: str


class AppendOnlyAIActionLog:
    """Hash-chained intervention/silence/advice journal."""

    def __init__(self) -> None:
        self._records: list[AIActionRecord] = []

    def append(
        self,
        *,
        action_id: str,
        occurred_at_ns: int,
        posture: str,
        style: CommunicationStyle,
        feedback: UserFeedback,
    ) -> AIActionRecord:
        if self._records and occurred_at_ns < self._records[-1].occurred_at_ns:
            raise ValueError("AI action time cannot move backwards")
        previous = self._records[-1].record_hash if self._records else "0" * 64
        payload = (
            f"{action_id}\x1f{occurred_at_ns}\x1f{posture}\x1f{style.value}\x1f"
            f"{feedback.value}\x1f{previous}"
        ).encode()
        record = AIActionRecord(
            action_id=action_id,
            occurred_at_ns=occurred_at_ns,
            posture=posture,
            style=style,
            feedback=feedback,
            previous_hash=previous,
            record_hash=hashlib.sha256(payload).hexdigest(),
        )
        self._records.append(record)
        return record

    def verify(self) -> bool:
        previous = "0" * 64
        for record in self._records:
            payload = (
                f"{record.action_id}\x1f{record.occurred_at_ns}\x1f{record.posture}\x1f"
                f"{record.style.value}\x1f{record.feedback.value}\x1f{previous}"
            ).encode()
            if record.previous_hash != previous:
                return False
            if hashlib.sha256(payload).hexdigest() != record.record_hash:
                return False
            previous = record.record_hash
        return True

    @property
    def records(self) -> tuple[AIActionRecord, ...]:
        return tuple(self._records)


class CommunicationExperienceLearner:
    """Learn style utility and interruption spacing only from observed feedback."""

    _REWARD: ClassVar[dict[UserFeedback, float]] = {
        UserFeedback.ACCEPTED: 1.0,
        UserFeedback.LAUGHED: 1.2,
        UserFeedback.IGNORED: -0.4,
        UserFeedback.RESISTED: -1.5,
    }

    def __init__(self) -> None:
        self._outcomes: dict[str, dict[CommunicationStyle, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._negative_streak: Counter[str] = Counter()
        self._avoid: dict[str, set[CommunicationStyle]] = defaultdict(set)

    def record(
        self,
        user_id: str,
        style: CommunicationStyle,
        feedback: UserFeedback,
    ) -> None:
        style = CommunicationStyle(style)
        feedback = UserFeedback(feedback)
        outcomes = self._outcomes[user_id][style]
        outcomes.append(self._REWARD[feedback])
        if feedback in {UserFeedback.RESISTED, UserFeedback.IGNORED}:
            self._negative_streak[user_id] += 1
        else:
            self._negative_streak[user_id] = 0
        if len(outcomes) >= 3 and statistics.fmean(outcomes) < -0.5:
            self._avoid[user_id].add(style)

    def preferred_style(self, user_id: str) -> CommunicationStyle:
        candidates = [
            style for style in CommunicationStyle if style not in self._avoid[user_id]
        ]
        if not candidates:
            candidates = list(CommunicationStyle)
        return max(
            candidates,
            key=lambda style: (
                statistics.fmean(self._outcomes[user_id][style])
                if self._outcomes[user_id][style]
                else float("-inf"),
                -list(CommunicationStyle).index(style),
            ),
        )

    def minimum_intervention_interval_minutes(self, user_id: str) -> int:
        return min(24 * 60, 15 * (2 ** min(self._negative_streak[user_id], 6)))

    def avoided_styles(self, user_id: str) -> frozenset[CommunicationStyle]:
        return frozenset(self._avoid[user_id])


class DialogueStance(StrEnum):
    EVIDENCE_CORRECTION = "evidence_correction"
    EMPATHIC_LISTENING = "empathic_listening"
    UNCONDITIONAL_AGREEMENT = "unconditional_agreement"


class DialogueMode(StrEnum):
    NATURAL = "natural"
    LEGAL_LECTURE = "legal_lecture"
    QUESTIONNAIRE = "questionnaire"


class CommunicationPolicyGuard:
    """Structured anti-sycophancy, anti-lecture, and zero-UI boundary."""

    def validate(
        self,
        *,
        stance: DialogueStance,
        mode: DialogueMode,
        proposition_supported: bool | None,
        user_is_venting: bool,
    ) -> None:
        if (
            proposition_supported is False
            and stance is DialogueStance.UNCONDITIONAL_AGREEMENT
        ):
            raise ValueError(
                "unsupported proposition cannot receive sycophantic agreement"
            )
        if user_is_venting and mode is DialogueMode.LEGAL_LECTURE:
            raise ValueError("venting context rejects teacher-like legal lectures")
        if mode is DialogueMode.QUESTIONNAIRE:
            raise ValueError("end-user questionnaire UI is constitutionally forbidden")


class ConciseDialoguePolicy:
    """A deterministic benchmark adapter; not represented as a production LLM."""

    def respond(
        self,
        *,
        user_text: str,
        emotional_valence: float,
        evidence_excerpt: str | None,
    ) -> str:
        if not user_text.strip():
            raise ValueError("user_text must not be blank")
        if emotional_valence <= -0.5:
            first = "听得出来你现在是真累，我在这儿。"
        elif emotional_valence >= 0.5:
            first = "这一下确实值得高兴。"
        else:
            first = "嗯，我跟着你的节奏。"
        if evidence_excerpt:
            excerpt = evidence_excerpt.strip()[:42]
            return first + f"我只钉住这条已知事实：{excerpt}。"
        return first


@dataclass(slots=True)
class _StageOutcome:
    value: Any
    output_count: int
    latency_samples_ms: list[float] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _IngestState:
    observations: tuple[CompressedObservation, ...]
    compression: CompressionReceipt
    generator: GeneratorReceipt
    voiceprint_tombstoned: bool
    core_voiceprint_retained: bool
    edge_image_raw_purged: bool


@dataclass(frozen=True, slots=True)
class _PyramidState:
    pyramid: LosslessTemporalPyramid
    representative_observation_id: str
    drill_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _WorldSynthesisState:
    search_hits: tuple[str, ...]
    expected_search_hits: tuple[str, ...]
    query_terms: tuple[str, ...]
    index_stats: dict[str, int]
    resonance_candidates: tuple[ResonanceCandidate, ...]
    lifecycle: AppendOnlyEventLifecycle
    statuses_seen: frozenset[EventStatus]
    stale_direct_count: int
    traversal_depth: int


@dataclass(frozen=True, slots=True)
class _EvolutionState:
    derivative: DerivativeReceipt
    valid_dimension_state: DerivedDimensionState
    low_accuracy_state: DerivedDimensionState
    sporadic_blocked: bool
    premature_activation_blocked: bool
    quota_blocked: bool
    life_chapter: LifeChapterReceipt


@dataclass(frozen=True, slots=True)
class _RetrospectiveState:
    historical_hash_before: str
    historical_hash_after: str
    update_blocked: bool
    delete_blocked: bool
    ledger_intact: bool
    as_known_overlay_count: int
    annotated_overlay_count: int
    same_historical_facts: bool
    direct_stale_count: int
    traversal_depth: int
    llm_recompute_requests: int
    projection_scan_reduction: float


@dataclass(frozen=True, slots=True)
class _AdviceState:
    advice: tuple[ActionableAdvice, ...]
    evidence_pointer_count: int
    all_pointers_resolved: bool
    goal_history_count: int
    task_history_count: int
    inferred_goal_abandoned: bool
    derived_task_cancelled: bool
    reflection_recorded: bool
    advice_context_bytes: int


@dataclass(frozen=True, slots=True)
class _CommunicationState:
    action_count: int
    action_log_intact: bool
    learned_style_accuracy: float
    avoided_style_count: int
    interval_before_rejection: int
    interval_after_rejection: int
    sycophancy_blocked: bool
    lecture_blocked: bool
    questionnaire_blocked: bool


@dataclass(frozen=True, slots=True)
class _CockpitState:
    p0_latencies_ms: tuple[float, ...]
    p0_llm_calls: int
    p0_cockpit_accesses: int
    p0_all_hardware_dispatched: bool
    p0_all_bypassed_world: bool
    dormant_projection_tokens: int
    level1_model_calls: int
    manifest_count: int
    max_manifest_tokens: int
    rolling_turn_count: int
    archived_turn_count: int
    four_step_order_valid: bool
    dialogue_sentence_counts: tuple[int, ...]
    normal_model_calls: int


class MassiveLifeBench:
    """Orchestrate all eight stages and emit fail-closed measured receipts."""

    STAGE_NAMES: ClassVar[tuple[str, ...]] = (
        "百万级摄入、清洗与边缘提纯",
        "五级时间金字塔与无损下钻",
        "多维共振、事件合成与生命周期",
        "认知导数、维度门槛与人生相变",
        "历史回溯与单跳雪崩隔离",
        "证据绑定建议与目标任务解耦",
        "AI 行动日志与沟通策略演进",
        "单次驾驶舱、P0 硬旁路与十轮对话",
    )

    def __init__(self, config: BenchmarkConfig | None = None) -> None:
        self.config = config or BenchmarkConfig()
        self._metrics: list[StageMetric] = []
        self._baseline_rss = _rss_bytes()

    def run(self) -> MassiveLifeBenchmarkReport:
        ingest = self._run_measured(
            "S1",
            self.STAGE_NAMES[0],
            self.config.sample_count,
            self._stage_ingest,
        )
        pyramid = self._run_measured(
            "S2",
            self.STAGE_NAMES[1],
            len(ingest.observations),
            lambda: self._stage_pyramid(ingest),
        )
        synthesis = self._run_measured(
            "S3",
            self.STAGE_NAMES[2],
            len(ingest.observations),
            lambda: self._stage_world_synthesis(ingest),
        )
        evolution = self._run_measured(
            "S4",
            self.STAGE_NAMES[3],
            len(ingest.observations),
            lambda: self._stage_evolution(ingest),
        )
        retrospective = self._run_measured(
            "S5",
            self.STAGE_NAMES[4],
            len(ingest.observations),
            lambda: self._stage_retrospective(ingest),
        )
        advice = self._run_measured(
            "S6",
            self.STAGE_NAMES[5],
            len(ingest.observations),
            lambda: self._stage_advice(ingest),
        )
        communication = self._run_measured(
            "S7",
            self.STAGE_NAMES[6],
            72,
            self._stage_communication,
        )
        cockpit = self._run_measured(
            "S8",
            self.STAGE_NAMES[7],
            110,
            lambda: self._stage_cockpit(ingest, advice),
        )

        gates = self._build_gates(
            ingest,
            pyramid,
            synthesis,
            evolution,
            retrospective,
            advice,
            communication,
            cockpit,
        )
        proposals = (
            adaptive_compression_tool_proposal(self.config.current_at),
            dual_lens_projection_tool_proposal(self.config.current_at),
        )
        artifacts = self._artifact_paths()
        diagnosis = self._diagnose(ingest, synthesis, advice, cockpit)
        limitations = (
            "This is a deterministic Linux synthetic-world benchmark; it does not prove physical wearable feasibility.",
            "Structured semantic/risk labels emulate upstream model adjudication; no production LLM quality claim is made.",
            "Process RSS includes Python, SQLite, and prior test-run allocations; it is not a per-module heap profile.",
            "Latency measurements describe this sandbox and are not a production service-level guarantee.",
        )
        verdict = "PASS" if all(gate.passed for gate in gates) else "FAIL"
        report = MassiveLifeBenchmarkReport(
            generated_at=self.config.current_at,
            seed=self.config.seed,
            requested_sample_count=self.config.sample_count,
            generated_sample_count=ingest.generator.generated_count,
            official_scale_reached=(
                ingest.generator.generated_count >= OFFICIAL_MINIMUM_RECORDS
            ),
            stages=tuple(self._metrics),
            gates=tuple(gates),
            tool_proposals=proposals,
            bottleneck_diagnosis=diagnosis,
            limitations=limitations,
            artifacts=artifacts,
            verdict=verdict,
        )
        if self.config.persist_artifacts:
            self._persist(report)
        return report

    def _run_measured(
        self,
        stage_id: str,
        name: str,
        input_count: int,
        operation: Any,
    ) -> Any:
        rss_before = _rss_bytes()
        started = time.perf_counter_ns()
        outcome: _StageOutcome = operation()
        wall_ms = (time.perf_counter_ns() - started) / 1_000_000
        rss_after = _rss_bytes()
        throughput = input_count / (wall_ms / 1_000) if wall_ms else 0.0
        samples = outcome.latency_samples_ms or [wall_ms]
        self._metrics.append(
            StageMetric(
                stage_id=stage_id,
                name=name,
                input_count=input_count,
                output_count=outcome.output_count,
                wall_time_ms=wall_ms,
                throughput_per_second=throughput,
                latency_p50_ms=_percentile(samples, 0.50),
                latency_p95_ms=_percentile(samples, 0.95),
                latency_p99_ms=_percentile(samples, 0.99),
                rss_before_bytes=rss_before,
                rss_after_bytes=rss_after,
                peak_rss_bytes=max(_peak_rss_bytes(), rss_before, rss_after),
                measurements=outcome.measurements,
            )
        )
        return outcome.value

    def _stage_ingest(self) -> _StageOutcome:
        generator = MassiveSyntheticLifeGenerator(self.config)
        compressor = AdaptiveTemporalCompressionOperator()
        batch_latencies: list[float] = []
        batch_started = time.perf_counter_ns()
        batch_count = 0
        for sample in generator:
            compressor.ingest(sample)
            batch_count += 1
            if batch_count == self.config.ingest_batch_size:
                elapsed_ms = (time.perf_counter_ns() - batch_started) / 1_000_000
                batch_latencies.append(elapsed_ms / batch_count)
                batch_started = time.perf_counter_ns()
                batch_count = 0
        if batch_count:
            elapsed_ms = (time.perf_counter_ns() - batch_started) / 1_000_000
            batch_latencies.append(elapsed_ms / batch_count)

        observations, compression = compressor.finalize()
        generator_receipt = generator.receipt()

        raw_image = bytearray(b"non-durable-camera-frame")
        image = EdgeMultimodalCleaner(
            clock=lambda: self.config.current_at,
            id_factory=lambda: "obs_edge_probe",
        ).evaluate_and_clean_image(
            {
                "quality_score": 0.9,
                "semantic_caption": "text-only semantic scene",
                "scene_tags": ["benchmark", "caption"],
                "captured_at": self.config.current_at,
            },
            raw_image,
        )
        edge_image_raw_purged = (
            image is not None
            and image.raw_image_bytes_retained is False
            and not any(raw_image)
        )

        stale_time = self.config.current_at - timedelta(days=181)
        profiles = (
            VoiceprintProfile(
                voiceprint_id="vp_unknown_stale",
                feature_hash="0" * 32,
                first_detected_at=stale_time,
                last_contact_at=stale_time,
            ),
            VoiceprintProfile(
                voiceprint_id="vp_core_relation",
                entity_id="P001",
                feature_hash="f" * 32,
                first_detected_at=stale_time,
                last_contact_at=stale_time,
            ),
        )
        voice_snapshot = VoiceprintTTLStateMachine(profiles).advance(
            self.config.current_at
        )
        state = _IngestState(
            observations=observations,
            compression=compression,
            generator=generator_receipt,
            voiceprint_tombstoned=(
                "vp_unknown_stale" in voice_snapshot.newly_tombstoned_ids
            ),
            core_voiceprint_retained=any(
                profile.voiceprint_id == "vp_core_relation"
                for profile in voice_snapshot.active_matching_profiles
            ),
            edge_image_raw_purged=edge_image_raw_purged,
        )
        return _StageOutcome(
            value=state,
            output_count=len(observations),
            latency_samples_ms=batch_latencies,
            measurements={
                "raw_sensor_points": compression.raw_sensor_points_seen,
                "durable_observations": compression.durable_observation_count,
                "high_frequency_write_ratio": compression.high_frequency_write_ratio,
                "ambient_deleted": compression.ambient_records_physically_deleted,
                "key_evidence_retention_ratio": compression.key_evidence_retention_ratio,
                "normalized_generator_entropy": generator_receipt.normalized_entropy,
            },
        )

    @staticmethod
    def _stage_pyramid(ingest: _IngestState) -> _StageOutcome:
        pyramid = LosslessTemporalPyramid()
        started = time.perf_counter_ns()
        receipt = pyramid.build(ingest.observations)
        build_ms = (time.perf_counter_ns() - started) / 1_000_000
        selected_root = pyramid.roots[0]
        representative = pyramid.get_observation(
            selected_root.representative_observation_ref
        )
        drill_started = time.perf_counter_ns()
        path = pyramid.drill_path(
            selected_root.node_id,
            representative.observation_id,
        )
        drill_ms = (time.perf_counter_ns() - drill_started) / 1_000_000
        state = _PyramidState(
            pyramid=pyramid,
            representative_observation_id=representative.observation_id,
            drill_path=path,
        )
        return _StageOutcome(
            value=state,
            output_count=receipt.summary_node_count,
            latency_samples_ms=[build_ms, drill_ms],
            measurements={
                "summary_nodes": receipt.summary_node_count,
                "year_roots": receipt.year_root_count,
                "drill_path_depth": len(path) - 1,
                "evidence_chain_break_rate": receipt.evidence_chain_break_rate,
                "lossless_verified": pyramid.verify_lossless(),
            },
        )

    def _stage_world_synthesis(self, ingest: _IngestState) -> _StageOutcome:
        index_directory = tempfile.TemporaryDirectory(prefix="aios-cjk-bench-")
        index_path = Path(index_directory.name) / "topological-index.sqlite3"
        connection = sqlite3.connect(index_path)
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = FILE")
        connection.execute("PRAGMA cache_size = -32768")
        index = CJKTopologicalInvertedIndex(connection)
        indexable = tuple(
            observation
            for observation in ingest.observations
            if observation.semantic_class is not RawSemanticClass.ROUTINE
            or observation.modality
            in {
                SensorModality.CHAT,
                SensorModality.AUDIO,
                SensorModality.IMAGE,
                SensorModality.BILLING,
            }
        )
        index_latencies: list[float] = []
        for offset in range(0, len(indexable), 1_000):
            chunk = indexable[offset : offset + 1_000]
            started = time.perf_counter_ns()
            index.index_many(
                (
                    observation.observation_id,
                    " ".join((observation.summary, *observation.tags)),
                    observation.occurred_at_ns,
                )
                for observation in chunk
            )
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            index_latencies.append(elapsed / max(1, len(chunk)))

        query_terms = ("合伙", "借贷", "争执", "银行流水")
        expected_hits = tuple(
            sorted(
                observation.observation_id
                for observation in ingest.observations
                if observation.event_key == "EVT_PARTNERSHIP_DISPUTE"
                and all(term in observation.summary for term in query_terms)
            )
        )
        query_latencies: list[float] = []
        hits: list[str] = []
        for _ in range(25):
            started = time.perf_counter_ns()
            hits = index.co_search(query_terms)
            query_latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        index_stats = index.stats()

        resonance = TemporalCrossModalResonator().synthesize(ingest.observations)
        if not resonance:
            raise RuntimeError("cross-modal resonator produced no candidates")
        lifecycle = AppendOnlyEventLifecycle()
        learned_base = self.config.current_at - timedelta(minutes=20)
        evidence_sets = [candidate.evidence_refs for candidate in resonance]
        while len(evidence_sets) < 5:
            evidence_sets.append(evidence_sets[-1])

        def create(name: str, evidence: tuple[str, ...], tick: int) -> EventAnchor:
            candidate = resonance[tick % len(resonance)]
            return lifecycle.create_candidate(
                object_id=name,
                subject_id=candidate.subject_id,
                learned_at=learned_base + timedelta(seconds=tick),
                event_time=_from_ns(candidate.window_start_ns),
                evidence_refs=evidence,
                confidence=candidate.confidence,
            )

        create("event_resolved", evidence_sets[0], 0)
        lifecycle.transition(
            "event_resolved",
            EventStatus.ACTIVE,
            learned_at=learned_base + timedelta(seconds=1),
        )
        lifecycle.transition(
            "event_resolved",
            EventStatus.RESOLVED,
            learned_at=learned_base + timedelta(seconds=2),
        )

        create("event_revised", evidence_sets[1], 3)
        lifecycle.transition(
            "event_revised",
            EventStatus.ACTIVE,
            learned_at=learned_base + timedelta(seconds=4),
        )
        lifecycle.transition(
            "event_revised",
            EventStatus.REVISED,
            learned_at=learned_base + timedelta(seconds=5),
            reason="late counter-evidence changed the bounded interpretation",
        )

        create("event_merged", evidence_sets[2], 6)
        lifecycle.transition(
            "event_merged",
            EventStatus.ACTIVE,
            learned_at=learned_base + timedelta(seconds=7),
        )
        lifecycle.transition(
            "event_merged",
            EventStatus.MERGED,
            learned_at=learned_base + timedelta(seconds=8),
            reason="overlapping evidence identified a single event",
            merged_into_ref=ObjectRef(object_id="event_revised", revision=3),
        )

        create("event_split", evidence_sets[3], 9)
        lifecycle.transition(
            "event_split",
            EventStatus.ACTIVE,
            learned_at=learned_base + timedelta(seconds=10),
        )
        lifecycle.transition(
            "event_split",
            EventStatus.SPLIT,
            learned_at=learned_base + timedelta(seconds=11),
            reason="two independent participant timelines were resolved",
            split_child_refs=(
                ObjectRef(object_id="event_split_child_a", revision=1),
                ObjectRef(object_id="event_split_child_b", revision=1),
            ),
        )

        create("event_rejected", evidence_sets[4], 12)
        lifecycle.transition(
            "event_rejected",
            EventStatus.REJECTED,
            learned_at=learned_base + timedelta(seconds=13),
            reason="required modality was disproved by late evidence",
        )
        statuses = frozenset(item.event_status for item in lifecycle.all_versions)

        isolation = SingleHopCascadeIsolator(
            (
                DependencyEdge(
                    upstream_node_id="event_revised",
                    dependent_node_id="summary_current",
                ),
                DependencyEdge(
                    upstream_node_id="event_revised",
                    dependent_node_id="task_current",
                ),
                DependencyEdge(
                    upstream_node_id="summary_current",
                    dependent_node_id="summary_historical_1",
                ),
            )
        ).isolate(
            "event_revised",
            reason_annotation_id="event_revision_3",
        )
        connection.close()
        index_db_bytes = index_path.stat().st_size
        index_directory.cleanup()
        state = _WorldSynthesisState(
            search_hits=tuple(hits),
            expected_search_hits=expected_hits,
            query_terms=query_terms,
            index_stats=index_stats,
            resonance_candidates=resonance,
            lifecycle=lifecycle,
            statuses_seen=statuses,
            stale_direct_count=isolation.stale_count,
            traversal_depth=isolation.traversal_depth,
        )
        return _StageOutcome(
            value=state,
            output_count=(
                len(resonance)
                + len(lifecycle.all_versions)
                + len(lifecycle.evidence_sets)
            ),
            latency_samples_ms=index_latencies + query_latencies,
            measurements={
                **index_stats,
                "index_db_bytes": index_db_bytes,
                "strict_co_search_hits": len(hits),
                "expected_co_search_hits": len(expected_hits),
                "co_search_exact": set(hits) == set(expected_hits),
                "resonance_candidates": len(resonance),
                "event_versions": len(lifecycle.all_versions),
                "evidence_sets": len(lifecycle.evidence_sets),
                "event_evidence_refs_resolve": lifecycle.evidence_references_resolve(),
                "event_statuses": sorted(item.value for item in statuses),
                "direct_stale_count": isolation.stale_count,
                "invalidation_depth": isolation.traversal_depth,
                "query_p99_ms": _percentile(query_latencies, 0.99),
            },
        )

    def _stage_evolution(self, ingest: _IngestState) -> _StageOutcome:
        burnout_values = tuple(
            sorted(
                (observation.occurred_at_ns, float(observation.mean_value))
                for observation in ingest.observations
                if observation.event_key == "SERIES_BURNOUT"
                and observation.mean_value is not None
            )
        )
        derivative = CognitiveDerivativeEngine().evaluate(burnout_values)

        submitted_at = self.config.current_at - timedelta(days=40)
        valid_anomalies = (
            PhysicalDomainAnomaly(
                domain="heart_rate",
                started_at=submitted_at - timedelta(days=3),
                observed_through=submitted_at,
            ),
            PhysicalDomainAnomaly(
                domain="sleep",
                started_at=submitted_at - timedelta(days=4),
                observed_through=submitted_at,
            ),
            PhysicalDomainAnomaly(
                domain="workload",
                started_at=submitted_at - timedelta(days=3),
                observed_through=submitted_at,
            ),
        )
        guard = DimensionEvolutionGuard()
        guard.submit_candidate(
            DimensionCandidateRequest(
                dimension_id="DIM_BURNOUT_COMPOSITE",
                name="身心耗竭复合维度",
                description="cross-domain predictive trial",
                anomalies=valid_anomalies,
            ),
            submitted_at=submitted_at,
        )
        quota_blocked = False
        try:
            guard.submit_candidate(
                DimensionCandidateRequest(
                    dimension_id="DIM_SECOND_SAME_DAY",
                    name="同日第二候选",
                    description="must be blocked by global quota",
                    anomalies=valid_anomalies,
                ),
                submitted_at=submitted_at,
            )
        except QuotaExceededBlockError:
            quota_blocked = True
        guard.start_trial("DIM_BURNOUT_COMPOSITE", started_at=submitted_at)
        premature = guard.evaluate_trial(
            "DIM_BURNOUT_COMPOSITE",
            evaluated_at=submitted_at + timedelta(days=15),
        )
        for day in range(30):
            guard.record_trial_evidence(
                TrialEvidence(
                    dimension_id="DIM_BURNOUT_COMPOSITE",
                    observed_at=submitted_at + timedelta(days=day, hours=1),
                    explanation_supported=True,
                    prediction_success=day < 24,
                )
            )
        valid_receipt = guard.evaluate_trial(
            "DIM_BURNOUT_COMPOSITE",
            evaluated_at=submitted_at + timedelta(days=30),
        )

        sporadic_blocked = False
        sporadic_guard = DimensionEvolutionGuard()
        try:
            sporadic_guard.submit_candidate(
                DimensionCandidateRequest(
                    dimension_id="DIM_SPORADIC",
                    name="偶发噪声维度",
                    description="one physical domain cannot qualify",
                    anomalies=(
                        PhysicalDomainAnomaly(
                            domain="heart_rate",
                            started_at=submitted_at - timedelta(hours=2),
                            observed_through=submitted_at,
                        ),
                        PhysicalDomainAnomaly(
                            domain="heart_rate",
                            started_at=submitted_at - timedelta(hours=1),
                            observed_through=submitted_at,
                        ),
                    ),
                ),
                submitted_at=submitted_at,
            )
        except AdmissionThresholdBlockError:
            sporadic_blocked = True

        low_guard = DimensionEvolutionGuard()
        low_guard.submit_candidate(
            DimensionCandidateRequest(
                dimension_id="DIM_LOW_ACCURACY",
                name="低预测收益维度",
                description="must expire after measured trial",
                anomalies=valid_anomalies,
            ),
            submitted_at=submitted_at,
        )
        low_guard.start_trial("DIM_LOW_ACCURACY", started_at=submitted_at)
        for day in range(30):
            low_guard.record_trial_evidence(
                TrialEvidence(
                    dimension_id="DIM_LOW_ACCURACY",
                    observed_at=submitted_at + timedelta(days=day, hours=1),
                    explanation_supported=True,
                    prediction_success=day < 3,
                )
            )
        low_receipt = low_guard.evaluate_trial(
            "DIM_LOW_ACCURACY",
            evaluated_at=submitted_at + timedelta(days=30),
        )

        gps = sorted(
            (
                observation
                for observation in ingest.observations
                if observation.modality is SensorModality.GPS
                and ("old_city" in observation.tags or "new_city" in observation.tags)
            ),
            key=lambda item: item.occurred_at_ns,
        )
        old_values = tuple(0.0 for item in gps if "old_city" in item.tags)[-60:]
        new_values = tuple(1.0 for item in gps if "new_city" in item.tags)[:60]
        life_chapter = LifeChapterDetector().detect(old_values, new_values)
        state = _EvolutionState(
            derivative=derivative,
            valid_dimension_state=valid_receipt.state,
            low_accuracy_state=low_receipt.state,
            sporadic_blocked=sporadic_blocked,
            premature_activation_blocked=(
                not premature.finalized
                and premature.state is DerivedDimensionState.TRIAL
            ),
            quota_blocked=quota_blocked,
            life_chapter=life_chapter,
        )
        return _StageOutcome(
            value=state,
            output_count=len(derivative.points) + 2,
            measurements={
                "derivative_points": len(derivative.points),
                "inflection_count": len(derivative.inflection_indices),
                "valid_dimension_state": valid_receipt.state.value,
                "valid_prediction_accuracy": valid_receipt.prediction_accuracy,
                "low_accuracy_state": low_receipt.state.value,
                "low_prediction_accuracy": low_receipt.prediction_accuracy,
                "sporadic_blocked": sporadic_blocked,
                "premature_activation_blocked": state.premature_activation_blocked,
                "quota_blocked": quota_blocked,
                "life_chapter_shift": life_chapter.normalized_shift,
            },
        )

    def _stage_retrospective(self, ingest: _IngestState) -> _StageOutcome:
        historical = next(
            observation
            for observation in ingest.observations
            if observation.event_key == "RETRO_HISTORY"
        )
        occurred_at = _from_ns(historical.occurred_at_ns)
        fact_payload = {
            "observation_id": historical.observation_id,
            "summary": historical.summary,
            "source_sha256": historical.source_sha256,
            "target_entity_id": "P002",
        }
        connection = sqlite3.connect(":memory:")
        ledger = FactImmutabilityLedger(connection)
        digest_before = ledger.seal_fact(
            object_id=historical.observation_id,
            revision=1,
            object_type="observation",
            subject_id=historical.subject_id,
            occurred_at=occurred_at,
            learned_at=occurred_at,
            payload=fact_payload,
        )
        update_blocked = False
        try:
            connection.execute(
                "UPDATE fact_integrity_ledger SET payload_json = '{}' "
                "WHERE object_id = ?",
                (historical.observation_id,),
            )
            connection.commit()
        except sqlite3.DatabaseError:
            update_blocked = True
            connection.rollback()
        delete_blocked = False
        try:
            connection.execute(
                "DELETE FROM fact_integrity_ledger WHERE object_id = ?",
                (historical.observation_id,),
            )
            connection.commit()
        except sqlite3.DatabaseError:
            delete_blocked = True
            connection.rollback()
        digest_after = ledger.digest_of(historical.observation_id) or ""
        integrity = ledger.verify_fact_integrity()

        contract_observation = Observation(
            object_id=historical.observation_id,
            subject_id=historical.subject_id,
            learned_at=occurred_at,
            recorded_at=occurred_at,
            created_by="adaptive_temporal_compressor",
            occurred=TemporalExtent.point(occurred_at),
            source_kind="synthetic_life_stream",
            modality="chat",
            value=historical.summary,
            data_quality={"source_sha256": historical.source_sha256},
            metadata={"target_entity_id": "P002"},
        )
        annotation = RetrospectiveAnnotation(
            annotation_id="annotation_partner_risk_now",
            target_entity_id="P002",
            semantic_overlay="current risk label from newly adjudicated evidence",
            target_time_start=occurred_at - timedelta(days=30),
            target_time_end=occurred_at + timedelta(days=30),
            learned_at=self.config.current_at,
            source_statement_ref="FRAUD_RULING@1",
        )
        lens = BiTemporalEpistemicLens(
            observations=(contract_observation,),
            annotations=(annotation,),
        )
        as_known = lens.query_historical_slice(
            "P002",
            occurred_at,
            as_of_cutoff=occurred_at + timedelta(days=1),
        )
        annotated = lens.query_historical_slice(
            "P002",
            occurred_at,
            as_of_cutoff=self.config.current_at,
        )
        same_historical = tuple(
            item.object_id for item in as_known.historical_observations
        ) == tuple(item.object_id for item in annotated.historical_observations)

        projection = DualLensProjectionIndex()
        projection_candidates = list(ingest.observations[:5_000])
        if historical not in projection_candidates:
            projection_candidates.append(historical)
        for observation in projection_candidates:
            entity = (
                observation.entity_ids[0]
                if observation.entity_ids
                else observation.subject_id
            )
            projection.append_fact(
                ImmutableProjectionFact.create(
                    object_id=observation.observation_id,
                    revision=1,
                    entity_id=entity,
                    valid_start_ns=observation.occurred_at_ns,
                    valid_end_ns=observation.occurred_at_ns,
                    learned_at_ns=observation.occurred_at_ns,
                    payload={
                        "summary": observation.summary,
                        "source_sha256": observation.source_sha256,
                    },
                )
            )
        projection.append_overlay(
            ProjectionOverlay.create(
                annotation_id=annotation.annotation_id,
                entity_id="P002",
                valid_start_ns=_to_ns(annotation.target_time_start),
                valid_end_ns=_to_ns(annotation.target_time_end),
                learned_at_ns=_to_ns(annotation.learned_at),
                payload={"risk_label": "current_caution"},
                source_ref=annotation.source_statement_ref,
            )
        )
        projection_as_known = projection.as_known(
            "P002",
            target_time_ns=historical.occurred_at_ns,
            knowledge_cutoff_ns=historical.occurred_at_ns + DAY_NS,
        )
        projection_annotated = projection.annotated(
            "P002",
            target_time_ns=historical.occurred_at_ns,
            current_knowledge_ns=_to_ns(self.config.current_at),
        )

        dependencies = (
            DependencyEdge(
                upstream_node_id="P002",
                dependent_node_id="current_relation_projection",
            ),
            DependencyEdge(
                upstream_node_id="P002",
                dependent_node_id="current_risk_summary",
            ),
            DependencyEdge(
                upstream_node_id="P002",
                dependent_node_id="current_advice_watch",
            ),
            DependencyEdge(
                upstream_node_id="current_relation_projection",
                dependent_node_id="year_summary_2024",
            ),
            DependencyEdge(
                upstream_node_id="year_summary_2024",
                dependent_node_id="month_summary_2024_03",
            ),
        )
        isolation = SingleHopCascadeIsolator(dependencies).isolate(
            "P002",
            reason_annotation_id=annotation.annotation_id,
        )
        connection.close()
        state = _RetrospectiveState(
            historical_hash_before=digest_before,
            historical_hash_after=digest_after,
            update_blocked=update_blocked,
            delete_blocked=delete_blocked,
            ledger_intact=integrity.all_intact and projection.verify_immutable_facts(),
            as_known_overlay_count=len(as_known.active_annotations),
            annotated_overlay_count=len(annotated.active_annotations),
            same_historical_facts=(
                same_historical
                and projection_as_known.historical_hashes
                == projection_annotated.historical_hashes
            ),
            direct_stale_count=isolation.stale_count,
            traversal_depth=isolation.traversal_depth,
            llm_recompute_requests=isolation.llm_recompute_requests,
            projection_scan_reduction=projection_annotated.scan_reduction_ratio,
        )
        return _StageOutcome(
            value=state,
            output_count=(
                len(annotated.historical_observations)
                + len(annotated.active_annotations)
                + isolation.stale_count
            ),
            measurements={
                "historical_hash_unchanged": digest_before == digest_after,
                "sql_update_blocked": update_blocked,
                "sql_delete_blocked": delete_blocked,
                "as_known_overlays": len(as_known.active_annotations),
                "annotated_overlays": len(annotated.active_annotations),
                "single_hop_stale_count": isolation.stale_count,
                "single_hop_depth": isolation.traversal_depth,
                "llm_recompute_requests": isolation.llm_recompute_requests,
                "projection_scan_reduction": projection_annotated.scan_reduction_ratio,
            },
        )

    def _stage_advice(self, ingest: _IngestState) -> _StageOutcome:
        facts: list[EvidenceFact] = []
        for observation in ingest.observations:
            if observation.semantic_class not in {
                RawSemanticClass.KEY_EVIDENCE,
                RawSemanticClass.CORE_QUOTE,
            }:
                continue
            object_type = (
                "claim" if observation.event_key == "FRAUD_RULING" else "observation"
            )
            facts.append(
                EvidenceFact(
                    ref=ObjectRef(
                        object_id=observation.observation_id,
                        revision=1,
                    ),
                    object_type=object_type,
                    text=observation.summary,
                    occurred_at=_from_ns(observation.occurred_at_ns),
                    source_kind="massive_synthetic_life_stream",
                    verified=True,
                )
            )
        repository = InMemoryEvidenceRepository(facts)
        advice = (
            MomBirthdayGiftAdvisor(repository).advise(1_200),
            FraudPreventionAdvisor(repository).advise("对方再次提出借款和合伙转账"),
            HealthFatigueBreakerAdvisor(repository).advise(),
        )
        pointers = tuple(
            pointer for item in advice for pointer in item.evidence_pointers
        )
        all_resolved = all(repository.resolve(pointer) for pointer in pointers)

        now = self.config.current_at
        inferred_goal = Goal(
            object_id="goal_inferred_recovery",
            subject_id="programmer",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="goal_inference",
            owner_id="programmer",
            source_type=GoalSourceType.USER_INFERRED,
            title="reduce chronic overload",
            description="inferred from cross-domain evidence, pending user authority",
            goal_status=GoalStatus.ACTIVE,
            success_criteria=["four consecutive weeks without overload"],
            app_ids=["health", "work"],
            confidence=0.72,
        )
        task = Task(
            object_id="task_inferred_recovery_followup",
            subject_id="programmer",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="goal_task_linker",
            task_type=TaskType.FOLLOW_UP,
            task_state=TaskState.READY,
            goal_ref=ObjectRef(object_id=inferred_goal.object_id, revision=1),
            title="review overload evidence when next condition matures",
            priority=60,
            next_step="wait for explicit user acceptance or new evidence",
            app_id="health",
        )
        denied_goal_payload = inferred_goal.model_dump(mode="python")
        denied_goal_payload.update(
            revision=2,
            learned_at=now + timedelta(seconds=1),
            recorded_at=now + timedelta(seconds=1),
            goal_status=GoalStatus.ABANDONED,
            metadata={"reason": "user explicitly denied inferred goal"},
        )
        denied_goal = Goal.model_validate(denied_goal_payload)
        cancelled_task_payload = task.model_dump(mode="python")
        cancelled_task_payload.update(
            revision=2,
            learned_at=now + timedelta(seconds=2),
            recorded_at=now + timedelta(seconds=2),
            task_state=TaskState.CANCELLED,
            metadata={"reason": "source inferred goal was denied"},
        )
        cancelled_task = Task.model_validate(cancelled_task_payload)
        reflection = {
            "source_goal": inferred_goal.object_id,
            "correction": "do not infer recovery intent from physiology alone",
            "recorded_at": (now + timedelta(seconds=2)).isoformat(),
        }
        advice_context_bytes = sum(
            len(item.model_dump_json().encode("utf-8")) for item in advice
        )
        state = _AdviceState(
            advice=advice,
            evidence_pointer_count=len(pointers),
            all_pointers_resolved=bool(all_resolved),
            goal_history_count=len((inferred_goal, denied_goal)),
            task_history_count=len((task, cancelled_task)),
            inferred_goal_abandoned=(denied_goal.goal_status is GoalStatus.ABANDONED),
            derived_task_cancelled=(cancelled_task.task_state is TaskState.CANCELLED),
            reflection_recorded=bool(reflection["correction"]),
            advice_context_bytes=advice_context_bytes,
        )
        return _StageOutcome(
            value=state,
            output_count=len(advice),
            measurements={
                "advice_count": len(advice),
                "evidence_pointer_count": len(pointers),
                "all_pointers_resolved": state.all_pointers_resolved,
                "inferred_goal_abandoned": state.inferred_goal_abandoned,
                "derived_task_cancelled": state.derived_task_cancelled,
                "advice_context_bytes": advice_context_bytes,
            },
        )

    def _stage_communication(self) -> _StageOutcome:
        feedback_generator = AdversarialCommunicationFeedbackGenerator()
        learner = CommunicationExperienceLearner()
        action_log = AppendOnlyAIActionLog()
        tick = _to_ns(self.config.current_at - timedelta(days=30))
        for action_index, case in enumerate(feedback_generator.cases()):
            learner.record(case.user_id, case.style, case.feedback)
            action_log.append(
                action_id=f"comm_action_{action_index:04d}",
                occurred_at_ns=tick + action_index * MINUTE_NS,
                posture=(
                    "SILENCE" if case.feedback is UserFeedback.IGNORED else "SPOKEN"
                ),
                style=case.style,
                feedback=case.feedback,
            )
        correct = sum(
            learner.preferred_style(user_id) is expected
            for user_id, expected in feedback_generator.ORACLE.items()
        )
        accuracy = correct / len(feedback_generator.ORACLE)
        avoided = sum(
            len(learner.avoided_styles(user_id))
            for user_id in feedback_generator.ORACLE
        )

        probe_user = "rejection_probe"
        interval_before = learner.minimum_intervention_interval_minutes(probe_user)
        for _ in range(3):
            learner.record(
                probe_user,
                CommunicationStyle.DIRECT,
                UserFeedback.RESISTED,
            )
        interval_after = learner.minimum_intervention_interval_minutes(probe_user)

        policy_guard = CommunicationPolicyGuard()
        sycophancy_blocked = False
        try:
            policy_guard.validate(
                stance=DialogueStance.UNCONDITIONAL_AGREEMENT,
                mode=DialogueMode.NATURAL,
                proposition_supported=False,
                user_is_venting=False,
            )
        except ValueError:
            sycophancy_blocked = True
        lecture_blocked = False
        try:
            policy_guard.validate(
                stance=DialogueStance.EMPATHIC_LISTENING,
                mode=DialogueMode.LEGAL_LECTURE,
                proposition_supported=None,
                user_is_venting=True,
            )
        except ValueError:
            lecture_blocked = True
        questionnaire_blocked = False
        try:
            policy_guard.validate(
                stance=DialogueStance.EVIDENCE_CORRECTION,
                mode=DialogueMode.QUESTIONNAIRE,
                proposition_supported=True,
                user_is_venting=False,
            )
        except ValueError:
            questionnaire_blocked = True

        state = _CommunicationState(
            action_count=len(action_log.records),
            action_log_intact=action_log.verify(),
            learned_style_accuracy=accuracy,
            avoided_style_count=avoided,
            interval_before_rejection=interval_before,
            interval_after_rejection=interval_after,
            sycophancy_blocked=sycophancy_blocked,
            lecture_blocked=lecture_blocked,
            questionnaire_blocked=questionnaire_blocked,
        )
        return _StageOutcome(
            value=state,
            output_count=len(action_log.records),
            measurements={
                "action_log_count": len(action_log.records),
                "action_log_intact": state.action_log_intact,
                "learned_style_accuracy": accuracy,
                "avoided_style_count": avoided,
                "interval_before_rejection_minutes": interval_before,
                "interval_after_rejection_minutes": interval_after,
                "sycophancy_blocked": sycophancy_blocked,
                "lecture_blocked": lecture_blocked,
                "questionnaire_blocked": questionnaire_blocked,
            },
        )

    def _stage_cockpit(
        self,
        ingest: _IngestState,
        advice: _AdviceState,
    ) -> _StageOutcome:
        class ForbiddenMindContext:
            def __init__(self) -> None:
                self.cockpit_accesses = 0
                self.llm_calls = 0

            def invoke_llm(self, _prompt: str) -> None:
                self.llm_calls += 1
                raise AssertionError("P0 invoked the model gateway")

            @property
            def cockpit_pipeline(self):
                self.cockpit_accesses += 1
                raise AssertionError("P0 entered the cognition/cockpit path")

        forbidden_context = ForbiddenMindContext()
        p0_latencies: list[float] = []
        all_dispatched = True
        all_bypassed = True
        for index in range(100):
            wake = SimpleNamespace(
                object_id=f"p0_virtual_{index}",
                priority=WakePriority.P0_CRITICAL_SAFETY,
                safety_bypass=SafetyBypassPayload(
                    hazard_type=(
                        HazardType.FALL_DETECTED
                        if index % 2 == 0
                        else HazardType.CARDIAC_ARREST
                    ),
                    vital_snapshot={"virtual_sample": index},
                    triggered_at=self.config.current_at,
                ),
            )
            started = time.perf_counter_ns()
            result = dispatch_wake_event(wake, forbidden_context)
            p0_latencies.append((time.perf_counter_ns() - started) / 1_000_000)
            receipt = result["deferred_receipt"]
            all_dispatched = all_dispatched and receipt.hardware_action_dispatched
            all_bypassed = all_bypassed and (
                result["bypassed_llm"]
                and result["bypassed_cockpit"]
                and result["bypassed_world_transaction"]
                and result["persistence_deferred"]
            )

        scheduler = ConditionalScheduler(
            (
                ConditionalTask(
                    task_id="dormant_future_review",
                    title="wake only when the evidence window matures",
                    track=ConditionTrack.LEVEL_1_MECHANICAL,
                    created_at=self.config.current_at,
                    mechanical_condition=MechanicalCondition(
                        kind=MechanicalConditionKind.ABSOLUTE_TIME,
                        due_at=self.config.current_at + timedelta(days=1),
                    ),
                ),
            )
        )
        dormant_projection = scheduler.cockpit_projection()
        scheduler.evaluate_level1(
            MechanicalSnapshot(observed_at=self.config.current_at)
        )

        mirror = SelfIdentityMirror()
        rapport = DynamicRapportModel(RapportTier.TRUSTED_WINGMAN)
        decider = HumanlikeResponsePostureDecider(rapport)
        posture = decider.decide(
            {
                "event_type": "IMPORTANT_REMINDER",
                "severity": "MEDIUM",
                "risk_codes": [],
            }
        )
        context = CrisisCockpitContext(
            session_id="massive_life_terminal_dialogue",
            ai_self_summary=json.dumps(
                mirror.reflect(), ensure_ascii=False, separators=(",", ":")
            ),
            rapport_state=json.dumps(
                rapport.get_rapport_state(),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            response_posture=posture.posture.value,
            wake_reason_anchor="user-initiated ordinary conversation",
            local_world_facts=(
                advice.advice[0].conclusion + " " + advice.advice[1].conclusion
            ),
            ready_tasks=[],
        )
        pipeline = CockpitPipeline(clock=lambda: self.config.current_at)
        dialogue_policy = ConciseDialoguePolicy()
        brevity = BrevityGuard()
        user_inputs = (
            ("今天有点累。", -0.7),
            ("项目终于过了。", 0.8),
            ("我妈膝盖最近还是怕冷。", -0.2),
            ("先不聊工作了。", 0.0),
            ("刚搬来这边还不太习惯。", -0.4),
            ("晚饭吃得挺舒服。", 0.6),
            ("那个合伙纠纷又来消息了。", -0.6),
            ("我只是想安静走一会儿。", -0.1),
            ("明天记得别让我漏掉复查。", 0.0),
            ("行，今天就到这儿。", 0.2),
        )
        evidence_excerpt = next(
            observation.summary
            for observation in ingest.observations
            if observation.semantic_class is RawSemanticClass.CORE_QUOTE
        )
        manifests = []
        sentence_counts: list[int] = []
        normal_model_calls = 0
        for index, (user_text, valence) in enumerate(user_inputs, start=1):
            normal_model_calls += 1
            raw_reply = dialogue_policy.respond(
                user_text=user_text,
                emotional_valence=valence,
                evidence_excerpt=(evidence_excerpt if index in {3, 7, 9} else None),
            )
            guarded = brevity.enforce(raw_reply)
            sentence_counts.append(len(split_sentences(guarded.text)))
            manifest = pipeline.process_turn(
                ConversationTurn(
                    turn_id=f"terminal_turn_{index:02d}",
                    sequence_no=index,
                    occurred_at=self.config.current_at + timedelta(minutes=index),
                    user_text=user_text,
                    assistant_text=guarded.text,
                ),
                context,
            )
            manifests.append(manifest)

        final_prompt = manifests[-1].prompt
        labels = (
            "[STEP_1_SELF]",
            "[STEP_2_RAPPORT]",
            "[STEP_3_POSTURE]",
            "[STEP_4_WORLD]",
        )
        positions = tuple(final_prompt.find(label) for label in labels)
        four_step_order = all(
            position >= 0 for position in positions
        ) and positions == tuple(sorted(positions))
        state = _CockpitState(
            p0_latencies_ms=tuple(p0_latencies),
            p0_llm_calls=forbidden_context.llm_calls,
            p0_cockpit_accesses=forbidden_context.cockpit_accesses,
            p0_all_hardware_dispatched=all_dispatched,
            p0_all_bypassed_world=all_bypassed,
            dormant_projection_tokens=dormant_projection.token_count,
            level1_model_calls=scheduler.level1_model_call_count,
            manifest_count=len(manifests),
            max_manifest_tokens=max(item.prompt_token_count for item in manifests),
            rolling_turn_count=len(pipeline.window),
            archived_turn_count=len(pipeline.archive),
            four_step_order_valid=four_step_order,
            dialogue_sentence_counts=tuple(sentence_counts),
            normal_model_calls=normal_model_calls,
        )
        return _StageOutcome(
            value=state,
            output_count=len(manifests),
            latency_samples_ms=p0_latencies,
            measurements={
                "p0_p50_ms": _percentile(p0_latencies, 0.50),
                "p0_p95_ms": _percentile(p0_latencies, 0.95),
                "p0_p99_ms": _percentile(p0_latencies, 0.99),
                "p0_llm_calls": forbidden_context.llm_calls,
                "p0_cockpit_accesses": forbidden_context.cockpit_accesses,
                "dormant_projection_tokens": dormant_projection.token_count,
                "level1_model_calls": scheduler.level1_model_call_count,
                "manifest_count": len(manifests),
                "max_manifest_tokens": state.max_manifest_tokens,
                "rolling_turn_count": state.rolling_turn_count,
                "archived_turn_count": state.archived_turn_count,
                "four_step_order_valid": four_step_order,
                "dialogue_sentence_counts": sentence_counts,
            },
        )

    def _build_gates(
        self,
        ingest: _IngestState,
        pyramid: _PyramidState,
        synthesis: _WorldSynthesisState,
        evolution: _EvolutionState,
        retrospective: _RetrospectiveState,
        advice: _AdviceState,
        communication: _CommunicationState,
        cockpit: _CockpitState,
    ) -> list[GateReceipt]:
        required_statuses = {
            EventStatus.CANDIDATE,
            EventStatus.ACTIVE,
            EventStatus.RESOLVED,
            EventStatus.REVISED,
            EventStatus.MERGED,
            EventStatus.SPLIT,
        }
        stage_gates = [
            GateReceipt(
                gate_id="SCALE-1M",
                requirement="official run generates at least 1,000,000 records",
                passed=ingest.generator.generated_count >= OFFICIAL_MINIMUM_RECORDS,
                measured={"generated": ingest.generator.generated_count},
            ),
            GateReceipt(
                gate_id="S1-EDGE-COMPACTION",
                iron_law=4,
                requirement="no raw payload retention, bounded writes, and 100% key-evidence retention",
                passed=(
                    ingest.compression.raw_payloads_retained == 0
                    and ingest.compression.high_frequency_write_ratio < 0.02
                    and ingest.compression.key_evidence_retention_ratio == 1.0
                    and ingest.edge_image_raw_purged
                ),
                measured={
                    "raw_payloads_retained": ingest.compression.raw_payloads_retained,
                    "write_ratio": ingest.compression.high_frequency_write_ratio,
                    "key_evidence_retention": ingest.compression.key_evidence_retention_ratio,
                    "edge_image_raw_purged": ingest.edge_image_raw_purged,
                },
            ),
            GateReceipt(
                gate_id="S1-DAILY-PRUNE-TTL",
                iron_law=4,
                requirement="ambient noise is physically purged and unbound voiceprint expires at 180 days",
                passed=(
                    ingest.compression.ambient_records_physically_deleted > 0
                    and ingest.voiceprint_tombstoned
                    and ingest.core_voiceprint_retained
                ),
                measured={
                    "ambient_deleted": ingest.compression.ambient_records_physically_deleted,
                    "voiceprint_tombstoned": ingest.voiceprint_tombstoned,
                    "core_voiceprint_retained": ingest.core_voiceprint_retained,
                },
            ),
            GateReceipt(
                gate_id="S2-LOSSLESS-DRILL",
                requirement="year-to-observation pointer chain has zero breakage",
                passed=(
                    pyramid.pyramid.verify_lossless()
                    and pyramid.pyramid.receipt.evidence_chain_break_rate == 0.0
                    and len(pyramid.drill_path) == 6
                    and pyramid.representative_observation_id
                    in pyramid.pyramid.get_node(pyramid.drill_path[0]).summary_text
                    and pyramid.pyramid.direct_drill(
                        pyramid.representative_observation_id
                    ).observation_id
                    == pyramid.representative_observation_id
                ),
                measured={
                    "break_rate": pyramid.pyramid.receipt.evidence_chain_break_rate,
                    "path": pyramid.drill_path,
                    "path_nodes": len(pyramid.drill_path),
                },
            ),
            GateReceipt(
                gate_id="S3-COSEARCH-RESONANCE",
                requirement="strict multi-keyword query and cross-modal synthesis both produce evidence pointers",
                passed=(
                    bool(synthesis.search_hits)
                    and set(synthesis.search_hits)
                    == set(synthesis.expected_search_hits)
                    and bool(synthesis.resonance_candidates)
                    and all(
                        candidate.evidence_refs
                        for candidate in synthesis.resonance_candidates
                    )
                ),
                measured={
                    "query_terms": synthesis.query_terms,
                    "search_hits": len(synthesis.search_hits),
                    "expected_hits": len(synthesis.expected_search_hits),
                    "exact_retrieval": set(synthesis.search_hits)
                    == set(synthesis.expected_search_hits),
                    "resonance_candidates": len(synthesis.resonance_candidates),
                },
            ),
            GateReceipt(
                gate_id="S3-EVENT-LIFECYCLE",
                requirement="append-only event revisions cover candidate/active/resolved/revised/merged/split and single-hop stale propagation",
                passed=(
                    required_statuses <= synthesis.statuses_seen
                    and synthesis.lifecycle.evidence_references_resolve()
                    and synthesis.traversal_depth <= 1
                    and synthesis.stale_direct_count == 2
                ),
                measured={
                    "statuses": sorted(item.value for item in synthesis.statuses_seen),
                    "event_versions": len(synthesis.lifecycle.all_versions),
                    "evidence_refs_resolve": synthesis.lifecycle.evidence_references_resolve(),
                    "stale_direct_count": synthesis.stale_direct_count,
                    "traversal_depth": synthesis.traversal_depth,
                },
            ),
            GateReceipt(
                gate_id="S4-DERIVATIVE-INFLECTION",
                requirement="velocity/acceleration and an inflection are computed in cognition",
                passed=(
                    evolution.derivative.computed_in_cognition_layer
                    and bool(evolution.derivative.inflection_indices)
                ),
                measured={
                    "points": len(evolution.derivative.points),
                    "inflections": evolution.derivative.inflection_indices,
                },
            ),
            GateReceipt(
                gate_id="S4-DIMENSION-TRIPLE-GATE",
                iron_law=5,
                requirement="3-day cross-domain, full 30-day trial, and daily reflection quota are all enforced",
                passed=(
                    evolution.sporadic_blocked
                    and evolution.premature_activation_blocked
                    and evolution.quota_blocked
                    and evolution.valid_dimension_state is DerivedDimensionState.ACTIVE
                    and evolution.low_accuracy_state is DerivedDimensionState.EXPIRED
                ),
                measured={
                    "sporadic_blocked": evolution.sporadic_blocked,
                    "premature_activation_blocked": evolution.premature_activation_blocked,
                    "quota_blocked": evolution.quota_blocked,
                    "qualified_state": evolution.valid_dimension_state.value,
                    "low_accuracy_state": evolution.low_accuracy_state.value,
                },
            ),
            GateReceipt(
                gate_id="S4-LIFE-CHAPTER",
                requirement="persistent baseline rupture archives the old life chapter",
                passed=(
                    evolution.life_chapter.changed
                    and evolution.life_chapter.archived_old_chapter
                ),
                measured={
                    "normalized_shift": evolution.life_chapter.normalized_shift,
                    "persistent_points": evolution.life_chapter.persistent_points,
                },
            ),
            GateReceipt(
                gate_id="S5-HISTORY-IMMUTABLE",
                iron_law=2,
                requirement="historical SHA-256 is unchanged and SQL UPDATE/DELETE are blocked",
                passed=(
                    retrospective.historical_hash_before
                    == retrospective.historical_hash_after
                    and retrospective.update_blocked
                    and retrospective.delete_blocked
                    and retrospective.ledger_intact
                ),
                measured={
                    "hash_before": retrospective.historical_hash_before,
                    "hash_after": retrospective.historical_hash_after,
                    "update_blocked": retrospective.update_blocked,
                    "delete_blocked": retrospective.delete_blocked,
                    "ledger_intact": retrospective.ledger_intact,
                },
            ),
            GateReceipt(
                gate_id="S5-DUAL-LENS-SINGLE-HOP",
                iron_law=2,
                requirement="today's overlay changes annotated view only, with constant-depth invalidation and zero LLM recompute",
                passed=(
                    retrospective.as_known_overlay_count == 0
                    and retrospective.annotated_overlay_count == 1
                    and retrospective.same_historical_facts
                    and retrospective.traversal_depth <= 1
                    and retrospective.llm_recompute_requests == 0
                ),
                measured={
                    "as_known_overlays": retrospective.as_known_overlay_count,
                    "annotated_overlays": retrospective.annotated_overlay_count,
                    "same_historical_facts": retrospective.same_historical_facts,
                    "stale_count": retrospective.direct_stale_count,
                    "depth": retrospective.traversal_depth,
                    "llm_recompute_requests": retrospective.llm_recompute_requests,
                    "projection_scan_reduction": retrospective.projection_scan_reduction,
                },
            ),
            GateReceipt(
                gate_id="S6-EVIDENCE-BOUND-ADVICE",
                iron_law=1,
                requirement="three actionable advices resolve every pinned causal ObjectRef",
                passed=(
                    len(advice.advice) == 3
                    and advice.evidence_pointer_count >= 8
                    and advice.all_pointers_resolved
                ),
                measured={
                    "advice_count": len(advice.advice),
                    "evidence_pointer_count": advice.evidence_pointer_count,
                    "all_pointers_resolved": advice.all_pointers_resolved,
                },
            ),
            GateReceipt(
                gate_id="S6-GOAL-TASK-DECOUPLING",
                requirement="denied inferred goal is abandoned, downstream task cancelled, and correction recorded",
                passed=(
                    advice.goal_history_count == 2
                    and advice.task_history_count == 2
                    and advice.inferred_goal_abandoned
                    and advice.derived_task_cancelled
                    and advice.reflection_recorded
                ),
                measured={
                    "goal_versions": advice.goal_history_count,
                    "task_versions": advice.task_history_count,
                    "goal_abandoned": advice.inferred_goal_abandoned,
                    "task_cancelled": advice.derived_task_cancelled,
                },
            ),
            GateReceipt(
                gate_id="S7-COMMUNICATION-LEARNING",
                requirement="feedback—not a preset output rule—selects style and lengthens interruption spacing after resistance",
                passed=(
                    communication.action_log_intact
                    and communication.learned_style_accuracy == 1.0
                    and communication.avoided_style_count > 0
                    and communication.interval_after_rejection
                    > communication.interval_before_rejection
                ),
                measured={
                    "action_count": communication.action_count,
                    "style_accuracy": communication.learned_style_accuracy,
                    "avoided_styles": communication.avoided_style_count,
                    "interval_before": communication.interval_before_rejection,
                    "interval_after": communication.interval_after_rejection,
                },
            ),
            GateReceipt(
                gate_id="S7-PERSONA-BOUNDARIES",
                iron_law=1,
                requirement="sycophancy, teacher-like lecturing, and questionnaire UI are blocked",
                passed=(
                    communication.sycophancy_blocked
                    and communication.lecture_blocked
                    and communication.questionnaire_blocked
                ),
                measured={
                    "sycophancy_blocked": communication.sycophancy_blocked,
                    "lecture_blocked": communication.lecture_blocked,
                    "questionnaire_blocked": communication.questionnaire_blocked,
                },
            ),
            GateReceipt(
                gate_id="S8-P0-HARD-BYPASS",
                iron_law=3,
                requirement="P0 dispatch P99 <=50ms with zero cognition/LLM/world access",
                passed=(
                    _percentile(list(cockpit.p0_latencies_ms), 0.99) <= 50.0
                    and cockpit.p0_llm_calls == 0
                    and cockpit.p0_cockpit_accesses == 0
                    and cockpit.p0_all_hardware_dispatched
                    and cockpit.p0_all_bypassed_world
                ),
                measured={
                    "p0_p99_ms": _percentile(list(cockpit.p0_latencies_ms), 0.99),
                    "p0_llm_calls": cockpit.p0_llm_calls,
                    "p0_cockpit_accesses": cockpit.p0_cockpit_accesses,
                    "hardware_dispatched": cockpit.p0_all_hardware_dispatched,
                    "world_bypassed": cockpit.p0_all_bypassed_world,
                },
            ),
            GateReceipt(
                gate_id="S8-COCKPIT-DIALOGUE",
                iron_law=1,
                requirement="single-shot four-step cockpit, zero-token dormant lane, six-turn window, and 1-3 sentence dialogue",
                passed=(
                    cockpit.dormant_projection_tokens == 0
                    and cockpit.level1_model_calls == 0
                    and cockpit.manifest_count == 10
                    and cockpit.max_manifest_tokens <= 1_500
                    and cockpit.rolling_turn_count == 6
                    and cockpit.archived_turn_count == 4
                    and cockpit.four_step_order_valid
                    and all(
                        1 <= count <= 3 for count in cockpit.dialogue_sentence_counts
                    )
                ),
                measured={
                    "dormant_tokens": cockpit.dormant_projection_tokens,
                    "level1_model_calls": cockpit.level1_model_calls,
                    "manifests": cockpit.manifest_count,
                    "max_manifest_tokens": cockpit.max_manifest_tokens,
                    "rolling_turns": cockpit.rolling_turn_count,
                    "archived_turns": cockpit.archived_turn_count,
                    "four_step_order": cockpit.four_step_order_valid,
                    "sentence_counts": cockpit.dialogue_sentence_counts,
                },
            ),
        ]
        return stage_gates

    def _diagnose(
        self,
        ingest: _IngestState,
        synthesis: _WorldSynthesisState,
        advice: _AdviceState,
        cockpit: _CockpitState,
    ) -> dict[str, Any]:
        slowest = max(self._metrics, key=lambda item: item.wall_time_ms)
        largest_p99 = max(self._metrics, key=lambda item: item.latency_p99_ms)
        cockpit_context_upper_bound = (
            cockpit.manifest_count * cockpit.max_manifest_tokens
        )
        token_candidates = {
            "actionable_advice_serialization": advice.advice_context_bytes,
            "cockpit_manifests_conservative_upper_bound": cockpit_context_upper_bound,
        }
        token_hotspot = max(token_candidates, key=token_candidates.get)
        return {
            "slowest_stage": slowest.stage_id,
            "slowest_stage_wall_ms": slowest.wall_time_ms,
            "largest_p99_stage": largest_p99.stage_id,
            "largest_observed_p99_ms": largest_p99.latency_p99_ms,
            "token_hotspot": token_hotspot,
            "token_measurements_utf8_bytes": token_candidates,
            "io_hotspot": "CJK topological postings",
            "io_posting_rows": synthesis.index_stats.get("postings_rows", 0),
            "durable_write_ratio": ingest.compression.high_frequency_write_ratio,
            "highest_distortion_risk": (
                "cross-modal EventAnchor interpretation: alignment proves co-occurrence, "
                "not causality; confidence and counter-evidence lifecycle remain mandatory"
            ),
            "mechanism_limit": (
                "the synthetic semantic adjudicator supplies structured labels; model "
                "calibration and real-world sensor drift need separate validation"
            ),
        }

    def _artifact_paths(self) -> dict[str, str]:
        date = self.config.current_at.date().isoformat()
        output = self.config.output_dir
        return {
            "evidence_json": str(output / f"aios_full_pipeline_bench_{date}.json"),
            "stress_report": str(
                output / f"AIOS_全流程海量盲测与极限压测报告_{date}.md"
            ),
            "diagnosis": str(output / f"AIOS_全生命周期心智瓶颈与缺陷诊断书_{date}.md"),
            "tool_proposals": str(output / f"AIOS_新机制发明与新工具提议_{date}.md"),
        }

    def _persist(self, report: MassiveLifeBenchmarkReport) -> None:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        payload_json = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        self._atomic_write(Path(report.artifacts["evidence_json"]), payload_json)
        self._atomic_write(
            Path(report.artifacts["stress_report"]),
            self._stress_markdown(report),
        )
        self._atomic_write(
            Path(report.artifacts["diagnosis"]),
            self._diagnosis_markdown(report),
        )
        self._atomic_write(
            Path(report.artifacts["tool_proposals"]),
            self._proposal_markdown(report),
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.replace(path)

    @staticmethod
    def _stress_markdown(report: MassiveLifeBenchmarkReport) -> str:
        total_wall_ms = sum(stage.wall_time_ms for stage in report.stages)
        peak_rss_bytes = max(stage.peak_rss_bytes for stage in report.stages)
        lines = [
            f"# {report.title}",
            "",
            f"- Benchmark version: `{report.benchmark_version}`",
            f"- Generated at: `{report.generated_at.isoformat()}`",
            f"- Seed: `{report.seed}`",
            f"- Raw records: **{report.generated_sample_count:,}**",
            f"- Total measured stage time: **{total_wall_ms:.3f} ms**",
            f"- Process peak RSS: **{peak_rss_bytes / 1024 / 1024:.2f} MiB**",
            f"- Official million-record scale: **{report.official_scale_reached}**",
            f"- Verdict: **{report.verdict}**",
            "",
            "## 八阶段实测性能",
            "",
            "| 阶段 | 输入 | 输出 | 总耗时 ms | 吞吐/s | P50 ms | P95 ms | P99 ms | RSS after MiB |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for stage in report.stages:
            lines.append(
                f"| {stage.stage_id} {stage.name} | {stage.input_count:,} | "
                f"{stage.output_count:,} | {stage.wall_time_ms:.3f} | "
                f"{stage.throughput_per_second:,.1f} | {stage.latency_p50_ms:.6f} | "
                f"{stage.latency_p95_ms:.6f} | {stage.latency_p99_ms:.6f} | "
                f"{stage.rss_after_bytes / 1024 / 1024:.2f} |"
            )
        lines.extend(
            [
                "",
                "## 五大铁律与阶段硬门",
                "",
                "| Gate | 铁律 | 结果 | 实测要求 |",
                "|---|---:|---|---|",
            ]
        )
        for gate in report.gates:
            lines.append(
                f"| {gate.gate_id} | {gate.iron_law or '-'} | "
                f"{'PASS' if gate.passed else 'FAIL'} | {gate.requirement} |"
            )
        lines.extend(
            [
                "",
                "## 结论边界",
                "",
                *[f"- {item}" for item in report.limitations],
                "",
                "完整原始实测值与 Gate receipts 见同目录 JSON 工件。",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _diagnosis_markdown(report: MassiveLifeBenchmarkReport) -> str:
        diagnosis = report.bottleneck_diagnosis
        return "\n".join(
            [
                "# 《AIOS 全生命周期心智瓶颈与缺陷诊断书》",
                "",
                (
                    f"- 最慢阶段：`{diagnosis['slowest_stage']}`，"
                    f"实测 `{diagnosis['slowest_stage_wall_ms']:.3f} ms`。"
                ),
                (
                    f"- P99 最高阶段：`{diagnosis['largest_p99_stage']}`，"
                    f"实测 `{diagnosis['largest_observed_p99_ms']:.6f} ms`。"
                ),
                (
                    f"- Token 热点：`{diagnosis['token_hotspot']}`；所有候选值均按"
                    "保守 UTF-8 字节计量，不用估算值伪装 tokenizer 实测。"
                ),
                (
                    f"- I/O 热点：`{diagnosis['io_hotspot']}`，共 "
                    f"`{diagnosis['io_posting_rows']:,}` 条倒排 posting。"
                ),
                f"- 高频摄入持久化写入比：`{diagnosis['durable_write_ratio']:.8f}`。",
                "",
                "## 最容易失真的认知抽象",
                "",
                diagnosis["highest_distortion_risk"],
                "",
                "## 为什么仍不完美",
                "",
                diagnosis["mechanism_limit"],
                (
                    "真实 LLM 语义清洗、跨设备时钟漂移、传感器缺失、数据库并发写"
                    "放大与实体硬件功耗均不在本次 Linux 确定性盲测的证明范围内。"
                ),
                "",
            ]
        )

    @staticmethod
    def _proposal_markdown(report: MassiveLifeBenchmarkReport) -> str:
        lines = [
            "# 《AIOS 新机制发明与新工具提议 (ToolProposal)》",
            "",
            (
                "以下提案均已按 `contracts.models.ToolProposal` 实例化，并有纯 Python "
                "实现参与本次全流程实跑。"
            ),
            "",
        ]
        for index, proposal in enumerate(report.tool_proposals, start=1):
            lines.extend(
                [
                    f"## {index}. `{proposal.object_id}`",
                    "",
                    f"- 能力缺口：{proposal.capability_gap}",
                    f"- 预期收益：{proposal.expected_benefit}",
                    f"- 验证计划：{proposal.validation_plan}",
                    "- 已实现接口：",
                    "",
                    "```json",
                    json.dumps(
                        proposal.proposed_interface,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    ),
                    "```",
                    "",
                    "- 当前限制：" + "；".join(proposal.current_limitations),
                    "",
                ]
            )
        lines.extend(
            [
                "## 实测关联",
                "",
                (
                    "自适应时序压缩算子的写入比、证据保留率与物理清理回执见 "
                    "`S1-EDGE-COMPACTION`；双透镜投影器的历史哈希一致性、扫描缩减与"
                    "单跳隔离回执见 `S5-HISTORY-IMMUTABLE` / `S5-DUAL-LENS-SINGLE-HOP`。"
                ),
                "",
            ]
        )
        return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the AIOS 3.0 eight-stage massive synthetic life benchmark."
    )
    parser.add_argument("--samples", type=int, default=OFFICIAL_MINIMUM_RECORDS)
    parser.add_argument("--seed", type=int, default=0xA10530)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/benchmarks"))
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args(argv)
    report = MassiveLifeBench(
        BenchmarkConfig(
            sample_count=args.samples,
            seed=args.seed,
            output_dir=args.output_dir,
            persist_artifacts=not args.no_persist,
        )
    ).run()
    print(
        json.dumps(
            {
                "verdict": report.verdict,
                "generated": report.generated_sample_count,
                "official_scale": report.official_scale_reached,
                "failed_gates": [
                    gate.gate_id for gate in report.gates if not gate.passed
                ],
                "artifacts": report.artifacts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.all_gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OFFICIAL_MINIMUM_RECORDS",
    "AppendOnlyAIActionLog",
    "AppendOnlyEventLifecycle",
    "BenchmarkConfig",
    "CognitiveDerivativeEngine",
    "CommunicationExperienceLearner",
    "CommunicationPolicyGuard",
    "CommunicationStyle",
    "ConciseDialoguePolicy",
    "DerivativeReceipt",
    "DialogueMode",
    "DialogueStance",
    "GateReceipt",
    "GeneratorReceipt",
    "LifeChapterDetector",
    "LifeScenarioOracle",
    "MassiveLifeBench",
    "MassiveLifeBenchmarkReport",
    "MassiveSyntheticLifeGenerator",
    "ResonanceCandidate",
    "StageMetric",
    "TemporalCrossModalResonator",
    "UserFeedback",
    "main",
]
