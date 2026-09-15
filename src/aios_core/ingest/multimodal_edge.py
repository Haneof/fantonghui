"""M1-001R edge multimodal cleanup and voiceprint lifecycle policy.

The module deliberately exposes no raw-image field on its durable output.  A
camera adapter may pass a short-lived frame buffer to
:meth:`EdgeMultimodalCleaner.evaluate_and_clean_image`, but the cleaner only
returns bounded text metadata.  Mutable input buffers are zeroed before the
method returns; immutable ``bytes`` remain owned by the caller and are never
retained by this component.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from math import isfinite
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


class EdgeMultimodalCleaner:
    """Apply the fixed edge quality gate and emit text-only observations.

    The supplied metadata contains the lightweight edge model's quality score,
    caption and tags.  This class does not call a remote model and never stores
    or returns the frame bytes.
    """

    QUALITY_THRESHOLD: ClassVar[float] = 0.4
    DEFAULT_CAPTION: ClassVar[str] = "日常活动场景"
    DEFAULT_TAGS: ClassVar[tuple[str, ...]] = ("routine",)

    __slots__ = ("_clock", "_id_factory")

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory or (lambda: f"obs_img_{uuid4().hex}")

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
            self._zero_mutable_buffer(raw_bytes)

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
