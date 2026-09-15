from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta
from itertools import combinations

import pytest

from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    RawByteSink,
    VoiceprintAudioSlice,
    VoiceprintLSHEngine,
    VoiceprintProfile,
    VoiceprintTTLStateMachine,
)

START = datetime(2025, 9, 21, 18, 0, tzinfo=UTC)
DAY_360 = START + timedelta(days=360)
CORE_SPEAKERS = (
    "core-00-zh-mandarin",
    "core-01-en-us",
    "core-02-zh-yue-cantonese",
    "core-03-zh-wuu-shanghainese",
    "core-04-zh-cmn-sichuanese",
    "core-05-en-singapore",
    "core-06-zh-nan-hokkien",
    "core-07-zh-hak-hakka",
    "core-08-zh-cmn-northeastern",
)
BACKGROUND_SPEAKERS = (
    "waiter-00-zh-mandarin",
    "waiter-01-en-uk",
    "waiter-02-zh-yue-cantonese",
    "waiter-03-ja-jp",
    "waiter-04-zh-wuu-shanghainese",
    "waiter-05-en-us",
    "waiter-06-zh-cmn-sichuanese",
    "waiter-07-zh-nan-hokkien",
    "passerby-08-zh-mandarin",
    "passerby-09-en-singapore",
    "passerby-10-zh-hak-hakka",
    "passerby-11-ja-jp",
    "passerby-12-zh-yue-cantonese",
    "passerby-13-en-us",
    "passerby-14-zh-cmn-northeastern",
)
CORE_PARTNER_COUNT = len(CORE_SPEAKERS)
BACKGROUND_SPEAKER_COUNT = len(BACKGROUND_SPEAKERS)
ALL_SPEAKERS = CORE_SPEAKERS + BACKGROUND_SPEAKERS
TOTAL_SPEAKERS = len(ALL_SPEAKERS)


def _speaker_vector(speaker_index: int, sample_index: int) -> tuple[float, ...]:
    """Deterministic DSP fixture after 85dB machinery/noise suppression."""

    return tuple(
        math.sin((speaker_index + 1) * (dimension + 1) * 0.019)
        + math.cos((speaker_index + 7) * (dimension + 1) * 0.011)
        + math.sin((sample_index + 1) * (dimension + 3) * 0.003) * 0.015
        for dimension in range(128)
    )


def _industrial_roundtable_slices() -> tuple[
    list[VoiceprintAudioSlice], dict[str, str]
]:
    slices: list[VoiceprintAudioSlice] = []
    enrolled_entity_hashes: dict[str, str] = {}
    for speaker_index, speaker_key in enumerate(ALL_SPEAKERS):
        is_core_partner = speaker_key.startswith("core-")
        if is_core_partner:
            entity_id = f"entity_supply_chain_partner_{speaker_index:02d}"
            enrolled_entity_hashes[entity_id] = VoiceprintLSHEngine.feature_hash(
                _speaker_vector(speaker_index, 0)
            )
            last_contact = DAY_360 - timedelta(hours=2)
        else:
            # At DAY_360 this is exactly 180 days since last contact.
            last_contact = DAY_360 - timedelta(days=180)

        for sample_index, detected_at in enumerate((START, last_contact)):
            slices.append(
                VoiceprintAudioSlice(
                    slice_id=(f"slice-85db-overlap-{speaker_index:02d}-{sample_index}"),
                    speaker_key=speaker_key,
                    feature_vector=_speaker_vector(speaker_index, sample_index),
                    detected_at=detected_at,
                )
            )
    return slices, enrolled_entity_hashes


@pytest.fixture(scope="module")
def roundtable_profiles() -> list[VoiceprintProfile]:
    slices, enrolled_entity_hashes = _industrial_roundtable_slices()
    anonymous_profiles = VoiceprintLSHEngine.build_profiles(slices)
    assert all(profile.entity_id is None for profile in anonymous_profiles)
    return VoiceprintLSHEngine.bind_nearest_entities(
        anonymous_profiles,
        enrolled_entity_hashes=enrolled_entity_hashes,
        max_hamming_distance=16,
    )


def test_500_degraded_images_are_purged_in_five_ms_without_raw_retention() -> None:
    sink = RawByteSink()
    cleaner = EdgeMultimodalCleaner(raw_byte_sink=sink)
    frames = [
        bytearray((frame_index * 31 + offset * 17) % 256 for offset in range(256))
        for frame_index in range(500)
    ]
    scores = [0.05 + (index % 34) / 100 for index in range(500)]
    persisted_observations: list[object] = []

    started = time.perf_counter_ns()
    for index, frame in enumerate(frames):
        result = cleaner.evaluate_and_clean_image(
            {
                "quality_score": scores[index],
                "capture_context": "85dB-heavy-assembly-line-motion-blur",
            },
            frame,
        )
        if result is not None:
            persisted_observations.append(result)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000

    assert elapsed_ms <= 5.0
    assert persisted_observations == []
    assert sink.purged_frame_count == 500
    assert sink.purged_byte_count == 500 * 256
    assert sink.retained_byte_count == 0
    assert all(not any(frame) for frame in frames)


def test_24_overlapping_speakers_produce_distinct_128_bit_lsh_profiles(
    roundtable_profiles: list[VoiceprintProfile],
) -> None:
    profiles = roundtable_profiles

    assert len(profiles) == TOTAL_SPEAKERS
    assert len({profile.voiceprint_id for profile in profiles}) == TOTAL_SPEAKERS
    assert len({profile.feature_hash for profile in profiles}) == TOTAL_SPEAKERS
    assert all(len(profile.feature_hash) == 32 for profile in profiles)
    assert all(
        len(f"{int(profile.feature_hash, 16):0128b}") == 128 for profile in profiles
    )

    core_partners = [profile for profile in profiles if profile.entity_id is not None]
    background_people = [profile for profile in profiles if profile.entity_id is None]
    assert len(core_partners) == CORE_PARTNER_COUNT
    assert len(background_people) == BACKGROUND_SPEAKER_COUNT
    assert all(
        profile.entity_id.startswith("entity_supply_chain_partner_")
        for profile in core_partners
        if profile.entity_id is not None
    )
    assert all(
        set(profile.model_dump())
        == {
            "voiceprint_id",
            "entity_id",
            "feature_hash",
            "first_detected_at",
            "last_contact_at",
            "is_tombstone",
        }
        for profile in profiles
    )

    distances = [
        VoiceprintLSHEngine.hamming_distance(left.feature_hash, right.feature_hash)
        for left, right in combinations(profiles, 2)
    ]
    assert min(distances) > 0
    assert max(distances) <= 128


def test_15_unbound_background_voiceprints_move_out_of_hot_table_at_day_180(
    roundtable_profiles: list[VoiceprintProfile],
) -> None:
    state_machine = VoiceprintTTLStateMachine(roundtable_profiles)

    just_before = state_machine.advance(DAY_360 - timedelta(microseconds=1))
    assert len(just_before.active_matching_profiles) == TOTAL_SPEAKERS
    assert just_before.archived_profiles == []
    assert just_before.newly_tombstoned_ids == []

    exact_boundary = state_machine.advance(DAY_360)
    assert len(exact_boundary.newly_tombstoned_ids) == BACKGROUND_SPEAKER_COUNT
    assert len(exact_boundary.archived_profiles) == BACKGROUND_SPEAKER_COUNT
    assert len(exact_boundary.active_matching_profiles) == CORE_PARTNER_COUNT
    assert all(
        profile.is_tombstone is True and profile.entity_id is None
        for profile in exact_boundary.archived_profiles
    )
    assert all(
        profile.is_tombstone is False and profile.entity_id is not None
        for profile in exact_boundary.active_matching_profiles
    )

    stable = state_machine.advance(DAY_360 + timedelta(days=180))
    assert stable.newly_tombstoned_ids == []
    assert len(stable.archived_profiles) == BACKGROUND_SPEAKER_COUNT
    assert len(stable.active_matching_profiles) == CORE_PARTNER_COUNT
    with pytest.raises(ValueError, match="cannot move backwards"):
        state_machine.advance(DAY_360)


def test_lifecycle_rejects_conflicting_rows_for_one_voiceprint_id(
    roundtable_profiles: list[VoiceprintProfile],
) -> None:
    original = roundtable_profiles[0]
    conflicting = original.model_copy(
        update={"last_contact_at": original.last_contact_at - timedelta(seconds=1)}
    )

    with pytest.raises(ValueError, match="conflicting profiles"):
        VoiceprintTTLStateMachine([original, conflicting])


def test_lsh_engine_rejects_wrong_dimension_and_non_finite_features() -> None:
    with pytest.raises(ValueError, match="exactly 128"):
        VoiceprintLSHEngine.feature_hash([0.0] * 127)
    with pytest.raises(ValueError, match="finite"):
        VoiceprintLSHEngine.feature_hash([0.0] * 127 + [float("nan")])


def test_lsh_hamming_distance_rejects_malformed_hashes() -> None:
    with pytest.raises(ValueError, match="exactly 128 bits"):
        VoiceprintLSHEngine.hamming_distance("abc", "0" * 32)
    with pytest.raises(ValueError, match="hexadecimal"):
        VoiceprintLSHEngine.hamming_distance("z" * 32, "0" * 32)


def test_ambiguous_lsh_enrollment_fails_closed_as_unbound(
    roundtable_profiles: list[VoiceprintProfile],
) -> None:
    unknown = roundtable_profiles[-1].model_copy(update={"entity_id": None})
    ambiguous = VoiceprintLSHEngine.bind_nearest_entities(
        [unknown],
        enrolled_entity_hashes={
            "entity_candidate_a": unknown.feature_hash,
            "entity_candidate_b": unknown.feature_hash,
        },
        max_hamming_distance=0,
    )

    assert ambiguous[0].entity_id is None
