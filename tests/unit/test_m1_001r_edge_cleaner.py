from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    ImageSemanticObservation,
    VoiceprintLifecycleManager,
    VoiceprintProfile,
)

NOW = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


def _profile(
    voiceprint_id: str,
    *,
    age_days: float,
    entity_id: str | None = None,
    is_tombstone: bool = False,
) -> VoiceprintProfile:
    last_contact = NOW - timedelta(days=age_days)
    return VoiceprintProfile(
        voiceprint_id=voiceprint_id,
        entity_id=entity_id,
        feature_hash=f"hash-{voiceprint_id}",
        first_detected_at=last_contact - timedelta(days=10),
        last_contact_at=last_contact,
        is_tombstone=is_tombstone,
    )


def test_edge_cleaner_discards_quality_below_point_four() -> None:
    cleaner = EdgeMultimodalCleaner()

    result = cleaner.evaluate_and_clean_image(
        {"quality_score": 0.399999},
        b"low-quality-frame",
    )

    assert result is None


def test_edge_cleaner_accepts_exact_threshold_and_never_retains_raw_bytes() -> None:
    cleaner = EdgeMultimodalCleaner(
        clock=lambda: NOW,
        id_factory=lambda: "obs_img_boundary",
    )
    raw = b"unique-binary-image-payload"

    result = cleaner.evaluate_and_clean_image(
        {
            "quality_score": 0.4,
            "caption": "散步",
            "tags": ["outdoor", "walking"],
        },
        raw,
    )

    assert result is not None
    assert result.observation_id == "obs_img_boundary"
    assert result.semantic_caption == "散步"
    assert result.scene_tags == ["outdoor", "walking"]
    assert result.raw_image_bytes_retained is False
    assert "raw_bytes" not in type(result).model_fields
    assert raw not in result.model_dump_json().encode()


def test_image_contract_cannot_be_constructed_with_retention_enabled() -> None:
    with pytest.raises(ValidationError, match="must never be retained"):
        ImageSemanticObservation(
            observation_id="obs_img_forbidden",
            quality_score=0.9,
            semantic_caption="书房阅读",
            raw_image_bytes_retained=True,
            captured_at=NOW,
        )


@pytest.mark.parametrize(
    "invalid_score",
    [float("nan"), float("inf"), float("-inf"), -0.01, 1.01, True, "bad"],
)
def test_edge_cleaner_rejects_invalid_quality_scores(invalid_score: object) -> None:
    cleaner = EdgeMultimodalCleaner()

    with pytest.raises(ValueError, match="quality_score"):
        cleaner.evaluate_and_clean_image(
            {"quality_score": invalid_score},
            b"frame",
        )


def test_edge_cleaner_generates_collision_resistant_ids() -> None:
    cleaner = EdgeMultimodalCleaner(clock=lambda: NOW)

    ids = {
        cleaner.evaluate_and_clean_image(
            {"quality_score": 0.8, "caption": "日常片段"},
            b"frame",
        ).observation_id
        for _ in range(100)
    }

    assert len(ids) == 100
    assert all(value.startswith("obs_img_") for value in ids)


def test_edge_cleaner_normalizes_tags_and_uses_aware_capture_time() -> None:
    cleaner = EdgeMultimodalCleaner(clock=lambda: NOW)

    result = cleaner.evaluate_and_clean_image(
        {
            "quality_score": "0.85",
            "semantic_caption": "  用户在书房阅读  ",
            "scene_tags": [" reading ", "indoors", "reading"],
        },
        b"frame",
    )

    assert result is not None
    assert result.semantic_caption == "用户在书房阅读"
    assert result.scene_tags == ["reading", "indoors"]
    assert result.captured_at == NOW
    assert result.captured_at.utcoffset() is not None


def test_edge_cleaner_zeroes_mutable_buffer_on_success() -> None:
    cleaner = EdgeMultimodalCleaner(clock=lambda: NOW)
    raw = bytearray(b"sensitive-camera-frame")

    result = cleaner.evaluate_and_clean_image(
        {"quality_score": 0.8, "caption": "室内"},
        raw,
    )

    assert result is not None
    assert raw == bytearray(len(raw))


def test_edge_cleaner_zeroes_mutable_buffer_on_discard_and_validation_error() -> None:
    cleaner = EdgeMultimodalCleaner()
    discarded = bytearray(b"discarded")
    invalid = bytearray(b"invalid")

    assert (
        cleaner.evaluate_and_clean_image(
            {"quality_score": 0.1},
            discarded,
        )
        is None
    )
    with pytest.raises(ValueError, match="quality_score"):
        cleaner.evaluate_and_clean_image(
            {"quality_score": "not-a-number"},
            invalid,
        )

    assert discarded == bytearray(len(discarded))
    assert invalid == bytearray(len(invalid))


def test_edge_cleaner_rejects_naive_capture_time() -> None:
    cleaner = EdgeMultimodalCleaner()

    with pytest.raises(ValidationError, match="captured_at must be timezone-aware"):
        cleaner.evaluate_and_clean_image(
            {
                "quality_score": 0.9,
                "caption": "场景",
                "captured_at": datetime(2026, 9, 16),  # noqa: DTZ001
            },
            b"frame",
        )


def test_voiceprint_sweep_tombstones_every_stale_unbound_profile() -> None:
    manager = VoiceprintLifecycleManager()
    profiles = [
        _profile(f"vp_{index:03d}", age_days=181 + index) for index in range(100)
    ]

    result = manager.sweep_stale_voiceprints(profiles, NOW)

    assert len(result) == 100
    assert all(profile.is_tombstone is True for profile in result)
    assert all(profile.is_tombstone is False for profile in profiles)


def test_voiceprint_sweep_uses_strict_over_180_day_boundary() -> None:
    manager = VoiceprintLifecycleManager()
    exact_boundary = _profile("vp_exact", age_days=180)
    just_over_boundary = _profile(
        "vp_over",
        age_days=180 + (1 / 86_400),
    )

    exact_result, over_result = manager.sweep_stale_voiceprints(
        [exact_boundary, just_over_boundary],
        NOW,
    )

    assert exact_result.is_tombstone is False
    assert over_result.is_tombstone is True


def test_voiceprint_sweep_never_tombstones_entity_bound_profile() -> None:
    manager = VoiceprintLifecycleManager()
    bound = _profile(
        "vp_known",
        age_days=1_000,
        entity_id="entity_alice",
    )

    result = manager.sweep_stale_voiceprints([bound], NOW)

    assert result == [bound]
    assert result[0].is_tombstone is False


def test_voiceprint_sweep_preserves_active_and_existing_tombstone_states() -> None:
    manager = VoiceprintLifecycleManager()
    active = _profile("vp_active", age_days=179)
    tombstoned = _profile(
        "vp_tombstoned",
        age_days=400,
        is_tombstone=True,
    )

    result = manager.sweep_stale_voiceprints(
        [active, tombstoned],
        NOW,
    )

    assert result[0].is_tombstone is False
    assert result[1].is_tombstone is True


def test_voiceprint_sweep_requires_timezone_aware_current_time() -> None:
    manager = VoiceprintLifecycleManager()

    with pytest.raises(ValueError, match="current_time must be timezone-aware"):
        manager.sweep_stale_voiceprints(
            [_profile("vp_one", age_days=181)],
            datetime(2026, 9, 16),  # noqa: DTZ001
        )


def test_voiceprint_profile_rejects_invalid_temporal_order() -> None:
    with pytest.raises(
        ValidationError,
        match="last_contact_at must not precede first_detected_at",
    ):
        VoiceprintProfile(
            voiceprint_id="vp_invalid",
            feature_hash="hash",
            first_detected_at=NOW,
            last_contact_at=NOW - timedelta(seconds=1),
        )


def test_voiceprint_profile_rejects_non_boolean_tombstone() -> None:
    with pytest.raises(ValidationError, match="is_tombstone must be a boolean"):
        VoiceprintProfile(
            voiceprint_id="vp_invalid_bool",
            feature_hash="hash",
            first_detected_at=NOW - timedelta(days=1),
            last_contact_at=NOW,
            is_tombstone="false",  # type: ignore[arg-type]
        )
