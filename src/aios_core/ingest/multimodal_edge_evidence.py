"""M1-001R edge multimodal cleanup and voiceprint lifecycle policy.

The module deliberately exposes no raw-image field on its durable output.  A
camera adapter may pass a short-lived frame buffer to
:meth:`EdgeMultimodalCleaner.evaluate_and_clean_image`, but the cleaner only
returns bounded text metadata.  Mutable input buffers are zeroed before the
method returns; immutable ``bytes`` remain owned by the caller and are never
retained by this component.  The ADV surface also exposes deterministic
128-bit voice LSH matching and an inclusive 180-day hot-to-archive state
machine without changing the legacy manager's strict ``> 180 days`` contract.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from functools import lru_cache
from math import isfinite
from threading import RLock
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.contracts.time import as_utc, require_aware, utc_now


class ImageSemanticObservation(BaseModel):
    """Text-only result of edge image filtering and semantic extraction."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
        validate_default=True,
    )

    observation_id: str = Field(min_length=1, max_length=128)
    quality_score: float = Field(ge=0.0, le=1.0)
    semantic_caption: str = Field(min_length=1, max_length=4096)
    scene_tags: list[str] = Field(default_factory=list, max_length=32)
    raw_image_bytes_retained: Literal[False] = False
    captured_at: datetime = Field(default_factory=utc_now)

    @field_validator("raw_image_bytes_retained", mode="before")
    @classmethod
    def raw_bytes_can_never_be_retained(cls, value: object) -> object:
        if value is not False:
            raise ValueError("raw image bytes must never be retained")
        return value

    @field_validator("scene_tags")
    @classmethod
    def normalize_scene_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            tag = value.strip()
            if not tag:
                raise ValueError("scene tags must not be blank")
            if len(tag) > 128:
                raise ValueError("scene tags must be at most 128 characters")
            if tag not in seen:
                normalized.append(tag)
                seen.add(tag)
        return normalized

    @field_validator("captured_at")
    @classmethod
    def captured_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "captured_at")
        return value


class VoiceprintProfile(BaseModel):
    """Minimal non-audio voiceprint identity and lifecycle state."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    voiceprint_id: str = Field(min_length=1, max_length=128)
    entity_id: str | None = Field(default=None, min_length=1, max_length=128)
    feature_hash: str = Field(min_length=1, max_length=1024)
    first_detected_at: datetime
    last_contact_at: datetime
    is_tombstone: bool = False

    @field_validator("first_detected_at", "last_contact_at")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime, info: Any) -> datetime:
        require_aware(value, info.field_name)
        return value

    @field_validator("is_tombstone", mode="before")
    @classmethod
    def tombstone_must_be_boolean(cls, value: object) -> object:
        if not isinstance(value, bool):
            # Pydantic v2 intentionally propagates TypeError from validators;
            # ValueError keeps this a model ValidationError for callers.
            raise ValueError("is_tombstone must be a boolean")  # noqa: TRY004
        return value

    @model_validator(mode="after")
    def contact_cannot_precede_detection(self) -> VoiceprintProfile:
        if as_utc(self.last_contact_at, "last_contact_at") < as_utc(
            self.first_detected_at,
            "first_detected_at",
        ):
            raise ValueError("last_contact_at must not precede first_detected_at")
        return self


class RawByteSink:
    """Zero caller-owned writable frames and retain no raw payload reference.

    Two different things happen to a frame, and conflating them would make the
    privacy accounting lie:

    * **zeroed** — the buffer was writable (``bytearray`` / writable
      ``memoryview``), so its storage was actually overwritten with zeros
      before the reference was dropped.  This is what red line 2 asks for.
    * **released** — the buffer was immutable (``bytes`` / read-only
      ``memoryview``).  Python cannot erase an immutable allocation from
      inside this process, so all we did was drop our reference and leave
      destruction to the caller/GC.  Counting that as "purged bytes" would
      report destruction that never happened.

    ``purged_*`` remains the total (kept for backwards compatibility);
    ``zeroed_*`` and ``released_*`` split it honestly.  ``retained_byte_count``
    is always 0 either way: this component never keeps a reference.
    """

    __slots__ = (
        "_lock",
        "_purged_bytes",
        "_purged_frames",
        "_released_bytes",
        "_released_frames",
        "_zeroed_bytes",
        "_zeroed_frames",
    )

    def __init__(self) -> None:
        self._lock = RLock()
        self._purged_frames = 0
        self._purged_bytes = 0
        self._zeroed_frames = 0
        self._zeroed_bytes = 0
        self._released_frames = 0
        self._released_bytes = 0

    @staticmethod
    def _is_erasure_capable(raw_bytes: bytes | bytearray | memoryview) -> bool:
        """Writable storage is the only kind this process can actually erase."""
        if isinstance(raw_bytes, bytearray):
            return True
        return isinstance(raw_bytes, memoryview) and not raw_bytes.readonly

    def purge(self, raw_bytes: bytes | bytearray | memoryview) -> None:
        if not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
            raise TypeError("raw_bytes must be bytes-like")
        byte_count = (
            raw_bytes.nbytes if isinstance(raw_bytes, memoryview) else len(raw_bytes)
        )
        erasable = self._is_erasure_capable(raw_bytes)
        EdgeMultimodalCleaner._zero_mutable_buffer(raw_bytes)
        with self._lock:
            self._purged_frames += 1
            self._purged_bytes += byte_count
            if erasable:
                self._zeroed_frames += 1
                self._zeroed_bytes += byte_count
            else:
                self._released_frames += 1
                self._released_bytes += byte_count

    @property
    def purged_frame_count(self) -> int:
        with self._lock:
            return self._purged_frames

    @property
    def purged_byte_count(self) -> int:
        with self._lock:
            return self._purged_bytes

    @property
    def zeroed_frame_count(self) -> int:
        """Frames whose storage was actually overwritten with zeros."""
        with self._lock:
            return self._zeroed_frames

    @property
    def zeroed_byte_count(self) -> int:
        with self._lock:
            return self._zeroed_bytes

    @property
    def released_frame_count(self) -> int:
        """Immutable frames: reference dropped, storage **not** erased here.

        A non-zero value means the device adapter handed us ``bytes``.  Edge
        capture paths should hand over ``bytearray``/``memoryview`` so that
        red line 2's "physical deletion" is actually achievable; this counter
        is what makes the gap observable instead of hidden inside a total.
        """
        with self._lock:
            return self._released_frames

    @property
    def released_byte_count(self) -> int:
        with self._lock:
            return self._released_bytes

    @property
    def retained_byte_count(self) -> Literal[0]:
        return 0


class VoiceprintAudioSlice(BaseModel):
    """Audio-free 128-dimensional feature slice emitted by upstream DSP."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    slice_id: str = Field(min_length=1, max_length=160)
    speaker_key: str = Field(min_length=1, max_length=160)
    feature_vector: tuple[float, ...] = Field(min_length=128, max_length=128)
    detected_at: datetime

    @field_validator("detected_at")
    @classmethod
    def detected_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "detected_at")
        return value


class VoiceprintLSHEngine:
    """Build deterministic 128-bit random-hyperplane locality-sensitive hashes."""

    LSH_DIMENSIONS: ClassVar[Literal[128]] = 128

    @classmethod
    def feature_hash(cls, vector: Sequence[float]) -> str:
        if len(vector) != cls.LSH_DIMENSIONS:
            raise ValueError("voice feature vector must contain exactly 128 values")
        normalized: list[float] = []
        for value in vector:
            number = float(value)
            if not isfinite(number):
                raise ValueError("voice feature vector must contain finite values")
            normalized.append(number)

        bit_field = 0
        for row in cls._projection_rows():
            projection = sum(
                value * sign for value, sign in zip(normalized, row, strict=True)
            )
            bit_field = (bit_field << 1) | int(projection >= 0.0)
        return f"{bit_field:032x}"

    @classmethod
    def build_profiles(
        cls,
        slices: Sequence[VoiceprintAudioSlice],
        *,
        entity_bindings: Mapping[str, str] | None = None,
    ) -> list[VoiceprintProfile]:
        bindings = entity_bindings or {}
        grouped: dict[str, list[VoiceprintAudioSlice]] = defaultdict(list)
        for item in slices:
            audio_slice = VoiceprintAudioSlice.model_validate(item)
            grouped[audio_slice.speaker_key].append(audio_slice)

        profiles: list[VoiceprintProfile] = []
        for speaker_key in sorted(grouped):
            speaker_slices = grouped[speaker_key]
            accumulator = [0.0] * cls.LSH_DIMENSIONS
            for audio_slice in speaker_slices:
                for index, value in enumerate(audio_slice.feature_vector):
                    accumulator[index] += value
            averaged = [value / len(speaker_slices) for value in accumulator]
            entity_id = bindings.get(speaker_key)
            if entity_id is not None and (
                not isinstance(entity_id, str) or not entity_id.strip()
            ):
                raise ValueError("entity binding must be a non-blank string")
            detected_times = [item.detected_at for item in speaker_slices]
            profiles.append(
                VoiceprintProfile(
                    voiceprint_id=(
                        "vp_lsh_"
                        + hashlib.sha256(speaker_key.encode("utf-8")).hexdigest()[:24]
                    ),
                    entity_id=entity_id,
                    feature_hash=cls.feature_hash(averaged),
                    first_detected_at=min(detected_times),
                    last_contact_at=max(detected_times),
                    is_tombstone=False,
                )
            )
        return profiles

    @classmethod
    def bind_nearest_entities(
        cls,
        profiles: Sequence[VoiceprintProfile],
        *,
        enrolled_entity_hashes: Mapping[str, str],
        max_hamming_distance: int = 16,
    ) -> list[VoiceprintProfile]:
        """Bind only an unambiguous nearby enrollment; ties remain unbound."""

        if isinstance(max_hamming_distance, bool) or not isinstance(
            max_hamming_distance, int
        ):
            raise TypeError("max_hamming_distance must be an integer")
        if not 0 <= max_hamming_distance <= cls.LSH_DIMENSIONS:
            raise ValueError("max_hamming_distance must be between 0 and 128")

        enrollments: list[tuple[str, int]] = []
        for entity_id, feature_hash in enrolled_entity_hashes.items():
            if not isinstance(entity_id, str) or not entity_id.strip():
                raise ValueError("enrolled entity_id must be a non-blank string")
            # Parse once per enrollment. The previous shape re-parsed both
            # 32-char hex strings on **every** comparison, i.e. O(profiles x
            # enrollments) `int()` calls for values that never change inside
            # the loop (measured: 1M comparisons = 748.6 ms; see the as-built
            # probe's E9 gate). Validation semantics are unchanged: a malformed
            # enrollment hash still raises here, before any profile is touched.
            enrollments.append((entity_id, cls._parse_hash(feature_hash)))

        bound: list[VoiceprintProfile] = []
        for item in profiles:
            profile = VoiceprintProfile.model_validate(item)
            # Parsed before the early-exit checks so that a malformed hash on an
            # already-bound/tombstoned profile still fails closed, as before.
            profile_bits = cls._parse_hash(profile.feature_hash)
            if profile.entity_id is not None or profile.is_tombstone or not enrollments:
                bound.append(profile)
                continue
            ranked = sorted(
                (
                    # .bit_count() 不可省：省了就变成"按 XOR 数值大小排序"，
                    # 与海明距离毫无关系（本轮真的犯过这个错，靠下面的 parity 测试抓住）
                    ((profile_bits ^ enrollment_bits).bit_count(), entity_id)
                    for entity_id, enrollment_bits in enrollments
                )
            )
            nearest_distance, nearest_entity_id = ranked[0]
            nearest_is_unique = len(ranked) == 1 or ranked[1][0] != nearest_distance
            if nearest_distance <= max_hamming_distance and nearest_is_unique:
                profile = profile.model_copy(update={"entity_id": nearest_entity_id})
            bound.append(profile)
        return bound

    @staticmethod
    def _parse_hash(value: str) -> int:
        """Validate a 32-hex (128-bit) LSH hash and return its integer form.

        Hoisting the parse out of comparison loops is what makes
        :meth:`bind_nearest_entities` linear in ``P x E`` integer XORs instead
        of ``P x E`` string parses.  Error messages are byte-identical to the
        previous ``hamming_distance`` validation so callers see no change.
        """
        if len(value) != 32:
            raise ValueError("LSH hash must encode exactly 128 bits")
        try:
            return int(value, 16)
        except ValueError as exc:
            raise ValueError("LSH hash must be hexadecimal") from exc

    @staticmethod
    def hamming_distance(left_hash: str, right_hash: str) -> int:
        engine = VoiceprintLSHEngine
        left = engine._parse_hash(left_hash)
        right = engine._parse_hash(right_hash)
        return (left ^ right).bit_count()

    @staticmethod
    @lru_cache(maxsize=1)
    def _projection_rows() -> tuple[tuple[int, ...], ...]:
        rows: list[tuple[int, ...]] = []
        for projection_index in range(128):
            random_bytes = hashlib.shake_256(
                f"AIOS-M1-001R-LSH-{projection_index}".encode()
            ).digest(128)
            rows.append(tuple(1 if value & 1 else -1 for value in random_bytes))
        return tuple(rows)


class VoiceprintLifecycleSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluated_at: datetime
    active_matching_profiles: list[VoiceprintProfile] = Field(default_factory=list)
    archived_profiles: list[VoiceprintProfile] = Field(default_factory=list)
    newly_tombstoned_ids: list[str] = Field(default_factory=list)

    @field_validator("evaluated_at")
    @classmethod
    def evaluated_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "evaluated_at")
        return value


class VoiceprintTTLStateMachine:
    """Inclusive 180-day ADV lifecycle: active hot table -> tombstone archive."""

    TOMBSTONE_AT: ClassVar[timedelta] = timedelta(days=180)

    def __init__(self, profiles: Sequence[VoiceprintProfile] = ()) -> None:
        self._lock = RLock()
        self._active: dict[str, VoiceprintProfile] = {}
        self._archived: dict[str, VoiceprintProfile] = {}
        self._last_advanced_at: datetime | None = None
        seen: dict[str, VoiceprintProfile] = {}
        for item in profiles:
            profile = VoiceprintProfile.model_validate(item)
            if profile.voiceprint_id in seen:
                if seen[profile.voiceprint_id] != profile:
                    raise ValueError(
                        "voiceprint_id has conflicting profiles: "
                        f"{profile.voiceprint_id}"
                    )
                continue
            seen[profile.voiceprint_id] = profile
            destination = self._archived if profile.is_tombstone else self._active
            destination[profile.voiceprint_id] = profile

    def advance(self, current_time: datetime) -> VoiceprintLifecycleSnapshot:
        require_aware(current_time, "current_time")
        now = as_utc(current_time, "current_time")
        newly_tombstoned: list[str] = []
        with self._lock:
            if self._last_advanced_at is not None and now < self._last_advanced_at:
                raise ValueError("current_time cannot move backwards")
            for voiceprint_id, profile in list(self._active.items()):
                should_archive = (
                    profile.entity_id is None
                    and now - as_utc(profile.last_contact_at, "last_contact_at")
                    >= self.TOMBSTONE_AT
                )
                if not should_archive:
                    continue
                tombstoned = profile.model_copy(update={"is_tombstone": True})
                self._archived[voiceprint_id] = tombstoned
                del self._active[voiceprint_id]
                newly_tombstoned.append(voiceprint_id)
            self._last_advanced_at = now
            return self._snapshot(current_time, newly_tombstoned)

    def snapshot(self, current_time: datetime) -> VoiceprintLifecycleSnapshot:
        require_aware(current_time, "current_time")
        with self._lock:
            return self._snapshot(current_time, [])

    def _snapshot(
        self,
        evaluated_at: datetime,
        newly_tombstoned_ids: list[str],
    ) -> VoiceprintLifecycleSnapshot:
        return VoiceprintLifecycleSnapshot(
            evaluated_at=evaluated_at,
            active_matching_profiles=[
                self._active[key] for key in sorted(self._active)
            ],
            archived_profiles=[self._archived[key] for key in sorted(self._archived)],
            newly_tombstoned_ids=sorted(newly_tombstoned_ids),
        )


class EdgeMultimodalCleaner:
    """Apply the fixed edge quality gate and emit text-only observations.

    The supplied metadata contains the lightweight edge model's quality score,
    caption and tags.  This class does not call a remote model and never stores
    or returns the frame bytes.
    """

    QUALITY_THRESHOLD: ClassVar[float] = 0.4
    DEFAULT_CAPTION: ClassVar[str] = "日常活动场景"
    DEFAULT_TAGS: ClassVar[tuple[str, ...]] = ("routine",)

    __slots__ = ("_clock", "_id_factory", "raw_byte_sink")

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], str] | None = None,
        raw_byte_sink: RawByteSink | None = None,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory or (lambda: f"obs_img_{uuid4().hex}")
        self.raw_byte_sink = (
            raw_byte_sink if raw_byte_sink is not None else RawByteSink()
        )

    def evaluate_and_clean_image(
        self,
        image_metadata: Mapping[str, Any],
        raw_bytes: bytes | bytearray | memoryview,
    ) -> ImageSemanticObservation | None:
        """Discard low-quality frames and return only bounded text semantics.

        ``quality_score < 0.4`` is a deterministic discard.  Invalid scores
        are rejected rather than silently treated as low-quality input.  The
        mutable-buffer zeroization in ``finally`` runs for accepted, discarded
        and invalid frames alike.
        """

        try:
            if not isinstance(image_metadata, Mapping):
                raise TypeError("image_metadata must be a mapping")
            if not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
                raise TypeError("raw_bytes must be bytes-like")

            score = self._read_quality_score(image_metadata)
            if score < self.QUALITY_THRESHOLD:
                return None

            caption_value = image_metadata.get(
                "semantic_caption",
                image_metadata.get("caption", self.DEFAULT_CAPTION),
            )
            if caption_value is None:
                caption_value = self.DEFAULT_CAPTION

            tags_value = image_metadata.get(
                "scene_tags",
                image_metadata.get("tags", self.DEFAULT_TAGS),
            )
            if tags_value is None:
                tags_value = self.DEFAULT_TAGS

            captured_at = image_metadata.get("captured_at")
            if captured_at is None:
                captured_at = self._clock()

            return ImageSemanticObservation(
                observation_id=self._id_factory(),
                quality_score=score,
                semantic_caption=caption_value,
                scene_tags=tags_value,
                raw_image_bytes_retained=False,
                captured_at=captured_at,
            )
        finally:
            self.raw_byte_sink.purge(raw_bytes)

    @staticmethod
    def _read_quality_score(image_metadata: Mapping[str, Any]) -> float:
        value = image_metadata.get("quality_score", 0.5)
        if isinstance(value, bool):
            raise ValueError(  # noqa: TRY004
                "quality_score must be a finite number"
            )
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("quality_score must be a finite number") from exc
        if not isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("quality_score must be between 0.0 and 1.0")
        return score

    @staticmethod
    def _zero_mutable_buffer(raw_bytes: object) -> None:
        """Best-effort zeroization for caller-provided writable buffers.

        Python ``bytes`` are immutable, so ownership of destroying an
        immutable capture allocation stays with the device adapter.  For a
        writable bytearray or memoryview, overwrite the accessible storage in
        bounded chunks without retaining a copy.
        """

        if isinstance(raw_bytes, bytearray):
            view = memoryview(raw_bytes)
        elif isinstance(raw_bytes, memoryview) and not raw_bytes.readonly:
            view = raw_bytes
        else:
            return

        try:
            byte_view = view.cast("B")
            zero_chunk = b"\x00" * min(len(byte_view), 64 * 1024)
            for start in range(0, len(byte_view), len(zero_chunk) or 1):
                end = min(start + len(zero_chunk), len(byte_view))
                byte_view[start:end] = zero_chunk[: end - start]
        except (TypeError, ValueError):
            # Non-contiguous or non-byte-format memoryviews cannot be safely
            # rewritten through this generic API.  No reference is retained.
            return
        finally:
            if isinstance(raw_bytes, bytearray):
                view.release()


class VoiceprintLifecycleManager:
    """Deterministically tombstone stale, unbound voiceprint profiles."""

    STALE_AFTER: ClassVar[timedelta] = timedelta(days=180)

    def sweep_stale_voiceprints(
        self,
        profiles: Sequence[VoiceprintProfile],
        current_time: datetime,
    ) -> list[VoiceprintProfile]:
        """Return an order-preserving lifecycle projection without mutation.

        A profile is stale only when it has no entity binding and its inactivity
        is *strictly greater* than 180 days.  Existing tombstones are never
        automatically revived.
        """

        require_aware(current_time, "current_time")
        current_utc = as_utc(current_time, "current_time")
        updated: list[VoiceprintProfile] = []

        for item in profiles:
            profile = (
                item
                if isinstance(item, VoiceprintProfile)
                else VoiceprintProfile.model_validate(item)
            )
            stale = (
                profile.entity_id is None
                and current_utc - as_utc(profile.last_contact_at, "last_contact_at")
                > self.STALE_AFTER
            )
            if stale and not profile.is_tombstone:
                profile = profile.model_copy(update={"is_tombstone": True})
            updated.append(profile)

        return updated
