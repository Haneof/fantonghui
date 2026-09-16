"""Streaming edge compaction without durable high-frequency raw payloads.

The operator is intentionally model-agnostic.  An upstream edge classifier
supplies structured semantic and anomaly labels; this component enforces what
may cross the durable-storage boundary.  Stable physical samples are reduced
online into bounded time buckets, while anomalous features and adjudicated
key evidence remain individually addressable.

No ``TemporalSample.raw_buffer`` object is retained.  Mutable buffers are
zeroed before :meth:`ingest` returns, including on validation failures.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import require_aware


class SensorModality(StrEnum):
    IMU = "imu"
    HEART_RATE = "heart_rate"
    IMAGE = "image"
    AUDIO = "audio"
    GPS = "gps"
    CHAT = "chat"
    BILLING = "billing"


class RawSemanticClass(StrEnum):
    """Structured verdict emitted by the edge/daily-review classifier."""

    ROUTINE = "routine"
    AMBIENT_NOISE = "ambient_noise"
    KEY_EVIDENCE = "key_evidence"
    CORE_QUOTE = "core_quote"


@dataclass(slots=True)
class TemporalSample:
    """One ephemeral edge sample.

    ``occurred_at_ns`` is UTC epoch nanoseconds.  Integer time avoids allocating
    one million ``datetime`` objects in a stress stream.  ``text`` is already a
    caption/transcript for image/audio modalities; raw media belongs only in
    the mutable ``raw_buffer`` and is never copied into durable output.
    """

    sequence_no: int
    subject_id: str
    occurred_at_ns: int
    modality: SensorModality
    value: float | None = None
    anomaly_score: float = 0.0
    text: str = ""
    tags: tuple[str, ...] = ()
    semantic_class: RawSemanticClass = RawSemanticClass.ROUTINE
    entity_ids: tuple[str, ...] = ()
    event_key: str | None = None
    speaker_id: str | None = None
    sample_rate_hz: int = 1
    raw_buffer: bytearray | memoryview | None = None


@dataclass(frozen=True, slots=True)
class CompressedObservation:
    observation_id: str
    subject_id: str
    occurred_at_ns: int
    modality: SensorModality
    summary: str
    tags: tuple[str, ...]
    entity_ids: tuple[str, ...]
    semantic_class: RawSemanticClass
    event_key: str | None
    source_sha256: str
    sample_count: int = 1
    mean_value: float | None = None
    minimum_value: float | None = None
    maximum_value: float | None = None
    speaker_id: str | None = None
    raw_payload_retained: bool = False


@dataclass(frozen=True, slots=True)
class CompressionReceipt:
    raw_records_seen: int
    raw_sensor_points_seen: int
    durable_observation_count: int
    durable_sensor_observation_count: int
    stable_bucket_count: int
    anomaly_observation_count: int
    semantic_observation_count: int
    ambient_records_physically_deleted: int
    raw_buffers_purged: int
    raw_bytes_purged: int
    key_evidence_expected: int
    key_evidence_retained: int
    raw_payloads_retained: int

    @property
    def key_evidence_retention_ratio(self) -> float:
        if self.key_evidence_expected == 0:
            return 1.0
        return self.key_evidence_retained / self.key_evidence_expected

    @property
    def high_frequency_write_ratio(self) -> float:
        if self.raw_sensor_points_seen == 0:
            return 0.0
        return self.durable_sensor_observation_count / self.raw_sensor_points_seen


@dataclass(slots=True)
class _OnlineBucket:
    subject_id: str
    modality: SensorModality
    bucket_start_ns: int
    sample_count: int = 0
    total: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf
    states: Counter[str] = field(default_factory=Counter)

    def add(self, value: float, tags: tuple[str, ...]) -> None:
        self.sample_count += 1
        self.total += value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.states.update(tags)


class AdaptiveTemporalCompressionOperator:
    """Online temporal reducer and raw-media retention firewall.

    This class is a reusable implementation of one benchmark-derived
    :class:`~aios_core.contracts.models.ToolProposal`.  It keeps O(number of
    active time buckets) state rather than O(number of raw samples) state.
    """

    HEART_BUCKET_NS: ClassVar[int] = 2 * 60 * 60 * 1_000_000_000
    IMU_BUCKET_NS: ClassVar[int] = 24 * 60 * 60 * 1_000_000_000
    GPS_BUCKET_NS: ClassVar[int] = 6 * 60 * 60 * 1_000_000_000
    ANOMALY_THRESHOLD: ClassVar[float] = 0.82
    MAX_TEXT_CHARS: ClassVar[int] = 1_024

    _BUCKET_WIDTH: ClassVar[dict[SensorModality, int]] = {
        SensorModality.HEART_RATE: HEART_BUCKET_NS,
        SensorModality.IMU: IMU_BUCKET_NS,
        SensorModality.GPS: GPS_BUCKET_NS,
    }

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, SensorModality, int], _OnlineBucket] = {}
        self._observations: list[CompressedObservation] = []
        self._raw_records_seen = 0
        self._raw_sensor_points_seen = 0
        self._stable_bucket_count = 0
        self._durable_sensor_count = 0
        self._anomaly_count = 0
        self._semantic_count = 0
        self._ambient_deleted = 0
        self._raw_buffers_purged = 0
        self._raw_bytes_purged = 0
        self._key_expected = 0
        self._key_retained = 0
        self._closed = False

    def ingest(self, sample: TemporalSample) -> CompressedObservation | None:
        """Consume one ephemeral sample and return an immediate durable feature.

        Stable numerical samples return ``None`` until :meth:`finalize` flushes
        their aggregate bucket.  This is the mechanical proof that high-rate
        points are not written one-for-one.
        """

        try:
            self._validate(sample)
            if self._closed:
                raise RuntimeError("compressor is already finalized")
            self._raw_records_seen += 1
            if sample.modality in self._BUCKET_WIDTH:
                self._raw_sensor_points_seen += sample.sample_rate_hz
            if sample.semantic_class in {
                RawSemanticClass.KEY_EVIDENCE,
                RawSemanticClass.CORE_QUOTE,
            }:
                self._key_expected += 1

            if sample.semantic_class is RawSemanticClass.AMBIENT_NOISE:
                self._ambient_deleted += 1
                return None

            if sample.modality in self._BUCKET_WIDTH and (
                sample.anomaly_score < self.ANOMALY_THRESHOLD
                and sample.semantic_class is RawSemanticClass.ROUTINE
            ):
                self._add_to_bucket(sample)
                return None

            observation = self._individual_observation(sample)
            self._observations.append(observation)
            self._durable_sensor_count += int(sample.modality in self._BUCKET_WIDTH)
            self._semantic_count += int(sample.modality not in self._BUCKET_WIDTH)
            self._anomaly_count += int(
                sample.modality in self._BUCKET_WIDTH
                and sample.anomaly_score >= self.ANOMALY_THRESHOLD
            )
            if sample.semantic_class in {
                RawSemanticClass.KEY_EVIDENCE,
                RawSemanticClass.CORE_QUOTE,
            }:
                self._key_retained += 1
            return observation
        finally:
            self._purge_raw_buffer(sample.raw_buffer)
            sample.raw_buffer = None

    def ingest_many(self, samples: Iterable[TemporalSample]) -> None:
        for sample in samples:
            self.ingest(sample)

    def finalize(self) -> tuple[tuple[CompressedObservation, ...], CompressionReceipt]:
        if not self._closed:
            for key in sorted(
                self._buckets, key=lambda item: (item[2], item[0], item[1])
            ):
                self._observations.append(self._bucket_observation(self._buckets[key]))
                self._stable_bucket_count += 1
                self._durable_sensor_count += 1
            self._buckets.clear()
            self._closed = True
        receipt = CompressionReceipt(
            raw_records_seen=self._raw_records_seen,
            raw_sensor_points_seen=self._raw_sensor_points_seen,
            durable_observation_count=len(self._observations),
            durable_sensor_observation_count=self._durable_sensor_count,
            stable_bucket_count=self._stable_bucket_count,
            anomaly_observation_count=self._anomaly_count,
            semantic_observation_count=self._semantic_count,
            ambient_records_physically_deleted=self._ambient_deleted,
            raw_buffers_purged=self._raw_buffers_purged,
            raw_bytes_purged=self._raw_bytes_purged,
            key_evidence_expected=self._key_expected,
            key_evidence_retained=self._key_retained,
            raw_payloads_retained=sum(
                observation.raw_payload_retained for observation in self._observations
            ),
        )
        return tuple(self._observations), receipt

    def _add_to_bucket(self, sample: TemporalSample) -> None:
        width = self._BUCKET_WIDTH[sample.modality]
        bucket_start = sample.occurred_at_ns - sample.occurred_at_ns % width
        key = (sample.subject_id, sample.modality, bucket_start)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _OnlineBucket(sample.subject_id, sample.modality, bucket_start)
            self._buckets[key] = bucket
        assert sample.value is not None
        bucket.add(sample.value, sample.tags)

    def _individual_observation(
        self,
        sample: TemporalSample,
    ) -> CompressedObservation:
        text = sample.text.strip()[: self.MAX_TEXT_CHARS]
        if not text:
            text = self._feature_summary(sample)
        digest = self._source_digest(
            sample.sequence_no,
            sample.subject_id,
            sample.occurred_at_ns,
            sample.modality.value,
            sample.value,
            sample.anomaly_score,
            text,
            sample.tags,
        )
        return CompressedObservation(
            observation_id=f"obs_{digest[:24]}",
            subject_id=sample.subject_id,
            occurred_at_ns=sample.occurred_at_ns,
            modality=sample.modality,
            summary=text,
            tags=tuple(dict.fromkeys(sample.tags)),
            entity_ids=tuple(dict.fromkeys(sample.entity_ids)),
            semantic_class=sample.semantic_class,
            event_key=sample.event_key,
            source_sha256=digest,
            mean_value=sample.value,
            minimum_value=sample.value,
            maximum_value=sample.value,
            speaker_id=sample.speaker_id,
            raw_payload_retained=False,
        )

    def _bucket_observation(self, bucket: _OnlineBucket) -> CompressedObservation:
        mean = bucket.total / bucket.sample_count
        dominant_state = (
            bucket.states.most_common(1)[0][0] if bucket.states else "stable"
        )
        summary = (
            f"{bucket.modality.value} stable aggregate: mean={mean:.3f}, "
            f"range={bucket.minimum:.3f}..{bucket.maximum:.3f}, "
            f"state={dominant_state}, n={bucket.sample_count}"
        )
        digest = self._source_digest(
            bucket.subject_id,
            bucket.modality.value,
            bucket.bucket_start_ns,
            bucket.sample_count,
            round(mean, 9),
            round(bucket.minimum, 9),
            round(bucket.maximum, 9),
            dominant_state,
        )
        return CompressedObservation(
            observation_id=f"obs_bucket_{digest[:20]}",
            subject_id=bucket.subject_id,
            occurred_at_ns=bucket.bucket_start_ns,
            modality=bucket.modality,
            summary=summary,
            tags=("stable_aggregate", dominant_state),
            entity_ids=(),
            semantic_class=RawSemanticClass.ROUTINE,
            event_key=None,
            source_sha256=digest,
            sample_count=bucket.sample_count,
            mean_value=mean,
            minimum_value=bucket.minimum,
            maximum_value=bucket.maximum,
            raw_payload_retained=False,
        )

    @staticmethod
    def _feature_summary(sample: TemporalSample) -> str:
        value = "unknown" if sample.value is None else f"{sample.value:.3f}"
        tags = ",".join(sample.tags) or "unclassified"
        return (
            f"{sample.modality.value} extracted feature: value={value}, "
            f"anomaly={sample.anomaly_score:.3f}, tags={tags}"
        )

    @staticmethod
    def _source_digest(*parts: object) -> str:
        payload = "\x1f".join(repr(part) for part in parts).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _purge_raw_buffer(self, raw_buffer: bytearray | memoryview | None) -> None:
        if raw_buffer is None:
            return
        try:
            view = (
                memoryview(raw_buffer)
                if isinstance(raw_buffer, bytearray)
                else raw_buffer
            )
            if view.readonly:
                raise ValueError("raw_buffer must be mutable so it can be purged")
            byte_view = view.cast("B")
            size = len(byte_view)
            chunk = b"\x00" * min(size, 4_096)
            for start in range(0, size, len(chunk) or 1):
                end = min(size, start + len(chunk))
                byte_view[start:end] = chunk[: end - start]
            self._raw_buffers_purged += 1
            self._raw_bytes_purged += size
        finally:
            if isinstance(raw_buffer, bytearray):
                view.release()

    @classmethod
    def _validate(cls, sample: TemporalSample) -> None:
        if (
            isinstance(sample.sequence_no, bool)
            or not isinstance(sample.sequence_no, int)
            or sample.sequence_no < 0
        ):
            raise ValueError("sequence_no must be a non-negative integer")
        if not sample.subject_id.strip():
            raise ValueError("subject_id must not be blank")
        if (
            isinstance(sample.occurred_at_ns, bool)
            or not isinstance(sample.occurred_at_ns, int)
            or sample.occurred_at_ns < 0
        ):
            raise ValueError("occurred_at_ns must be a non-negative integer")
        sample.modality = SensorModality(sample.modality)
        sample.semantic_class = RawSemanticClass(sample.semantic_class)
        if sample.value is not None and not math.isfinite(sample.value):
            raise ValueError("sample value must be finite")
        if not 0.0 <= sample.anomaly_score <= 1.0:
            raise ValueError("anomaly_score must be within [0, 1]")
        if (
            isinstance(sample.sample_rate_hz, bool)
            or not isinstance(sample.sample_rate_hz, int)
            or sample.sample_rate_hz < 1
        ):
            raise ValueError("sample_rate_hz must be a positive integer")
        if sample.modality in cls._BUCKET_WIDTH and sample.value is None:
            raise ValueError("numerical sensor modality requires value")


def adaptive_compression_tool_proposal(now: datetime) -> ToolProposal:
    """Return the durable proposal implemented by this module."""

    require_aware(now, "now")
    return ToolProposal(
        object_id="tool_proposal_adaptive_temporal_compressor_v1",
        subject_id="aios_core",
        learned_at=now,
        recorded_at=now,
        created_by="massive_life_bench",
        capability_gap=(
            "High-rate physical and multimodal streams need bounded online "
            "compaction without losing anomalous or causally linked evidence."
        ),
        use_cases=[
            "50Hz IMU macro-state extraction without point-wise database writes",
            "two-hour stable heart-rate aggregation with anomaly feature retention",
            "caption/transcript-only media persistence and raw-buffer zeroization",
        ],
        current_limitations=[
            "fixed time buckets over-read stable periods",
            "media adjudication labels are supplied by an upstream classifier",
        ],
        proposed_interface={
            "ingest": "TemporalSample -> CompressedObservation | None",
            "finalize": "() -> (observations, CompressionReceipt)",
            "space_complexity": "O(active buckets + retained evidence)",
        },
        expected_benefit=(
            "Reduce durable sensor writes by orders of magnitude while preserving "
            "100% of classifier-marked key evidence and zero raw media payloads."
        ),
        validation_plan=(
            "Stream at least 1,000,000 adversarial records; assert no one-for-one "
            "50Hz writes, raw-buffer purge, anomaly retention, and evidence recall."
        ),
    )


__all__ = [
    "AdaptiveTemporalCompressionOperator",
    "CompressedObservation",
    "CompressionReceipt",
    "RawSemanticClass",
    "SensorModality",
    "TemporalSample",
    "adaptive_compression_tool_proposal",
]
