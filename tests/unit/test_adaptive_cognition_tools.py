"""Red-team tests for the two benchmark-derived ToolProposal implementations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from aios_core.contracts.models import ToolProposal
from aios_core.operations.adaptive_temporal_compressor import (
    AdaptiveTemporalCompressionOperator,
    CompressedObservation,
    RawSemanticClass,
    SensorModality,
    TemporalSample,
    adaptive_compression_tool_proposal,
)
from aios_core.query.epistemic_projection import (
    DualLensProjectionIndex,
    ImmutableProjectionFact,
    ProjectionOverlay,
    dual_lens_projection_tool_proposal,
)
from aios_core.summaries.pyramid_aggregator import LosslessTemporalPyramid

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
NOW_NS = int(NOW.timestamp() * 1_000_000_000)
DAY_NS = 86_400 * 1_000_000_000


def test_adaptive_compressor_never_persists_raw_frames_or_pointwise_imu():
    operator = AdaptiveTemporalCompressionOperator()
    for sequence in range(1_000):
        operator.ingest(
            TemporalSample(
                sequence_no=sequence,
                subject_id="virtual-user",
                occurred_at_ns=NOW_NS + sequence * 20_000_000,
                modality=SensorModality.IMU,
                value=0.2 + sequence % 5 / 100,
                tags=("walking",),
                sample_rate_hz=50,
            )
        )

    anomaly = operator.ingest(
        TemporalSample(
            sequence_no=1_001,
            subject_id="virtual-user",
            occurred_at_ns=NOW_NS + 30_000_000_000,
            modality=SensorModality.IMU,
            value=3.8,
            anomaly_score=0.98,
            tags=("impact",),
            sample_rate_hz=50,
        )
    )
    key_raw = bytearray(b"contract promise audio")
    key = TemporalSample(
        sequence_no=1_002,
        subject_id="virtual-user",
        occurred_at_ns=NOW_NS + 31_000_000_000,
        modality=SensorModality.AUDIO,
        text="P001 promised to preserve the signed agreement",
        semantic_class=RawSemanticClass.CORE_QUOTE,
        speaker_id="P001",
        raw_buffer=key_raw,
    )
    key_observation = operator.ingest(key)
    noise_raw = bytearray(b"street noise")
    assert (
        operator.ingest(
            TemporalSample(
                sequence_no=1_003,
                subject_id="virtual-user",
                occurred_at_ns=NOW_NS + 32_000_000_000,
                modality=SensorModality.AUDIO,
                text="ambient fragment",
                semantic_class=RawSemanticClass.AMBIENT_NOISE,
                raw_buffer=noise_raw,
            )
        )
        is None
    )

    observations, receipt = operator.finalize()
    assert anomaly is not None
    assert key_observation is not None
    assert key.raw_buffer is None
    assert not any(key_raw)
    assert not any(noise_raw)
    assert receipt.raw_records_seen == 1_003
    assert receipt.raw_sensor_points_seen == 1_001 * 50
    assert receipt.durable_sensor_observation_count == 2
    assert receipt.high_frequency_write_ratio < 0.001
    assert receipt.key_evidence_retention_ratio == 1.0
    assert receipt.raw_payloads_retained == 0
    assert all(item.raw_payload_retained is False for item in observations)


def test_compressor_rejects_invalid_sensor_data_but_still_zeroizes_buffer():
    raw = bytearray(b"must be zero even when invalid")
    sample = TemporalSample(
        sequence_no=0,
        subject_id="virtual-user",
        occurred_at_ns=NOW_NS,
        modality=SensorModality.HEART_RATE,
        value=float("nan"),
        raw_buffer=raw,
    )
    with pytest.raises(ValueError, match="finite"):
        AdaptiveTemporalCompressionOperator().ingest(sample)
    assert sample.raw_buffer is None
    assert not any(raw)


def test_dual_lens_projection_cannot_mutate_fact_bytes_or_leak_future_overlay():
    source_payload = {"statement": "trusted partner at that historical time"}
    fact = ImmutableProjectionFact.create(
        object_id="obs-history",
        revision=1,
        entity_id="P002",
        valid_start_ns=NOW_NS - 10 * DAY_NS,
        valid_end_ns=NOW_NS - 10 * DAY_NS,
        learned_at_ns=NOW_NS - 10 * DAY_NS,
        payload=source_payload,
    )
    source_payload["statement"] = "caller mutation"
    projected_copy = fact.payload
    projected_copy["statement"] = "read-result mutation"
    assert fact.payload["statement"] == "trusted partner at that historical time"

    index = DualLensProjectionIndex()
    index.append_fact(fact)
    index.append_overlay(
        ProjectionOverlay.create(
            annotation_id="ann-risk-now",
            entity_id="P002",
            valid_start_ns=NOW_NS - 20 * DAY_NS,
            valid_end_ns=NOW_NS - DAY_NS,
            learned_at_ns=NOW_NS,
            payload={"current_label": "risk"},
            source_ref="claim-today@1",
        )
    )
    historical = index.as_known(
        "P002",
        target_time_ns=NOW_NS - 10 * DAY_NS,
        knowledge_cutoff_ns=NOW_NS - 9 * DAY_NS,
    )
    current = index.annotated(
        "P002",
        target_time_ns=NOW_NS - 10 * DAY_NS,
        current_knowledge_ns=NOW_NS,
    )
    assert historical.overlays == ()
    assert len(current.overlays) == 1
    assert historical.historical_hashes == current.historical_hashes
    assert index.verify_immutable_facts()

    conflicting = ImmutableProjectionFact.create(
        object_id="obs-history",
        revision=1,
        entity_id="P002",
        valid_start_ns=NOW_NS - 10 * DAY_NS,
        valid_end_ns=NOW_NS - 10 * DAY_NS,
        learned_at_ns=NOW_NS - 10 * DAY_NS,
        payload={"statement": "rewritten history"},
    )
    with pytest.raises(ValueError, match="different bytes"):
        index.append_fact(conflicting)


def test_lossless_pyramid_has_one_year_to_quote_path_and_direct_fast_path():
    observations = []
    for day in range(370):
        digest = hashlib.sha256(f"source-{day}".encode()).hexdigest()
        observations.append(
            CompressedObservation(
                observation_id=f"obs-{day}",
                subject_id="virtual-user",
                occurred_at_ns=NOW_NS - (369 - day) * DAY_NS,
                modality=SensorModality.CHAT,
                summary=f"original quote {day}",
                tags=("quote",),
                entity_ids=("P001",),
                semantic_class=RawSemanticClass.CORE_QUOTE,
                event_key=None,
                source_sha256=digest,
            )
        )
    pyramid = LosslessTemporalPyramid()
    receipt = pyramid.build(tuple(observations))
    target = observations[42]
    root = next(
        item
        for item in pyramid.roots
        if item.start_ns <= target.occurred_at_ns <= item.end_ns
    )
    path = pyramid.drill_path(root.node_id, target.observation_id)
    assert len(path) == 6
    assert path[-1] == target.observation_id
    assert pyramid.direct_drill(target.observation_id).summary == "original quote 42"
    assert receipt.evidence_chain_break_rate == 0.0
    assert pyramid.verify_lossless()


def test_both_implemented_tools_emit_valid_durable_tool_proposals():
    proposals = (
        adaptive_compression_tool_proposal(NOW),
        dual_lens_projection_tool_proposal(NOW),
    )
    assert all(isinstance(item, ToolProposal) for item in proposals)
    assert len({item.object_id for item in proposals}) == 2
    assert all(item.validation_plan and item.proposed_interface for item in proposals)
