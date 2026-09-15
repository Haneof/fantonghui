"""M1-001: source-message ingress, without cognitive interpretation.

Only the existing Core store commits durable data. Source identity lives on the
first Observation revision; the per-call lookup is rebuilt from that world, not
from a second database or a process-local dedupe cache.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.contracts.time import TemporalExtent, as_utc, utc_now
from aios_core.errors import AIOSProtocolError
from aios_core.storage.idempotency import canonical_json_dumps, canonical_json_value
from aios_core.storage.sqlite_store import SQLiteWorldStore


def _utc_point(value: Any) -> datetime:
    if isinstance(value, str):
        if "T" not in value:
            raise ValueError("occurred_at must be an ISO 8601 datetime with timezone")
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError("time must be an aware datetime or ISO 8601 datetime")
    return as_utc(value, "time")


class _Message(BaseModel):
    """Service input only; deliberately not a new durable world contract."""

    model_config = ConfigDict(extra="forbid", strict=True)

    subject_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    modality: Literal["gps", "heart_rate", "imu", "text", "app"]
    occurred_at: datetime
    value: Any
    unit: str | None = None
    data_quality: dict[str, Any] = Field(default_factory=dict)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    raw_locator: str | None = None

    @field_validator("subject_id", "source_id", "source_event_id", "source_kind")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source identity fields must not be blank")
        return value  # Identity is exact, never silently trimmed or case-folded.

    @field_validator("occurred_at", mode="before")
    @classmethod
    def normalize_time(cls, value: Any) -> datetime:
        return _utc_point(value)


class IngestResult(BaseModel):
    """Refs/statuses align with input order; committed_refs contains new rows only.

    world_revision is the snapshot read for a no-op, or the Core commit revision.
    Replayed refs always pin the original ingress revision, even after correction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_refs: list[ObjectRef]
    committed_refs: list[ObjectRef]
    statuses: list[Literal["committed", "replayed", "duplicate_in_batch"]]
    world_revision: int = Field(ge=0)
    operation_id: str | None = None
    idempotent_replay: bool = False


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("measurement must be a finite number, not a boolean or string")
    return float(value)


def _normalize(message: _Message) -> _Message:
    value, unit = message.value, message.unit
    if message.modality == "heart_rate":
        if unit not in ("bpm", "Hz"):
            raise ValueError("heart_rate unit must be bpm or Hz")
        value = _number(value) * (60 if unit == "Hz" else 1)
        if value < 0 or not math.isfinite(value):
            raise ValueError("heart_rate must be finite and nonnegative")
        unit = "bpm"
    elif message.modality == "gps":
        if unit != "deg" or not isinstance(value, dict) or set(value) != {"latitude", "longitude"}:
            raise ValueError("gps requires latitude/longitude in deg")
        value = {key: _number(item) for key, item in value.items()}
        if not (-90 <= value["latitude"] <= 90 and -180 <= value["longitude"] <= 180):
            raise ValueError("gps coordinate out of range")
    elif message.modality == "imu":
        units = {"g": (9.80665, "m/s^2"), "m/s^2": (1, "m/s^2"),
                 "deg/s": (math.pi / 180, "rad/s"), "rad/s": (1, "rad/s")}
        if unit not in units or not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
            raise ValueError("imu requires x/y/z and an acceleration or angular-rate unit")
        factor, unit = units[unit]
        value = {key: _number(item) * factor for key, item in value.items()}
        if not all(math.isfinite(item) for item in value.values()):
            raise ValueError("imu conversion overflow")
    elif message.modality == "text":
        if not isinstance(value, str) or unit is not None:
            raise ValueError("text requires a string and no unit")
    elif message.modality == "app":
        if not isinstance(value, dict) or unit is not None:
            raise ValueError("app requires a structured object and no unit")
    message.value, message.unit = value, unit
    return message


def _identity(message: _Message) -> tuple[str, str, str]:
    return message.subject_id, message.source_id, message.source_event_id


def _content(message: _Message) -> str:
    # This is a conflict check AFTER source identity lookup, never value dedupe.
    return canonical_json_dumps(message.model_dump(mode="python"))


class ObservationIngestService:
    """Unified ``observation.ingest(batch)`` service.

    batch is a list of input dictionaries. One source_event_id represents one
    sample within (subject_id, source_id), across all modalities. An adapter for
    source sequences can map its stable stream/epoch/sequence identity to this
    field. Missing identities are rejected, never synthesized from values.

    The composition root owns clock/clock_provenance, not incoming messages.
    Optimistic VERSION_CONFLICT is returned intact: retry the whole batch.
    """

    def __init__(self, store: SQLiteWorldStore, *, clock: Callable[[], datetime] | None = None,
                 clock_provenance: str | None = None):
        if clock is not None and (not isinstance(clock_provenance, str) or not clock_provenance.strip()):
            raise ValueError("a controlled clock requires clock_provenance")
        self._store = store
        self._clock = clock or utc_now
        self._clock_provenance = clock_provenance if clock is not None else "core:utc_now"

    def _existing(self, snapshot: int) -> dict[tuple[str, str, str], tuple[str, ObjectRef]]:
        existing = {}
        for payload in self._store.list_payloads(object_type=ObjectType.OBSERVATION,
                                                 as_of_world_revision=snapshot):
            # Latest metadata/subject/value may have been corrected through Core.
            # The immutable first revision remains the receipt for original input.
            if payload["revision"] != 1:
                payload = self._store.get_payload(payload["object_id"], revision=1,
                                                  as_of_world_revision=snapshot)
            marker = payload.get("metadata", {}).get("ingress")
            if not isinstance(marker, dict) or marker.get("service") != "observation.ingest":
                continue  # Legacy Observation has no source-message receipt.
            try:
                if marker["version"] != 1:
                    raise ValueError("unsupported ingress receipt version")
                source = _Message.model_validate(dict(
                    subject_id=payload["subject_id"], source_id=marker["source_id"],
                    source_event_id=marker["source_event_id"], source_kind=payload["source_kind"],
                    modality=payload["modality"], occurred_at=payload["occurred"]["start"],
                    value=payload["value"], unit=payload["unit"], data_quality=payload["data_quality"],
                    source_metadata=payload["metadata"]["source_metadata"],
                    source_refs=payload["source_refs"], raw_locator=payload["raw_locator"]))
                key = _identity(source)
                receipt = (_content(source), ObjectRef(object_id=payload["object_id"], revision=1))
                if key in existing:
                    raise ValueError("multiple original receipts for one source message")
                existing[key] = receipt
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                raise AIOSProtocolError(ErrorCode.STORAGE_FAILURE, "invalid ingress receipt",
                                        context={"reason": "invalid_ingress_receipt"}) from exc
        return existing

    def ingest(self, batch: list[dict[str, Any]]) -> IngestResult:
        try:
            if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
                raise ValueError("batch must be a list of message dictionaries")
            # Reuse frozen durable normalization (cycles, UTF-8, keys, depth).
            # Explicit source_refs are subsequently reconstructed as typed refs.
            messages = [_normalize(_Message.model_validate(canonical_json_value(item))) for item in batch]
            contents = [_content(message) for message in messages]
            now = _utc_point(self._clock())
        except (ValueError, TypeError, OverflowError, RecursionError) as exc:
            raise AIOSProtocolError(ErrorCode.INVALID_ARGUMENT, "invalid observation batch",
                                    context={"reason": "invalid_ingress_input"}) from exc

        snapshot = self._store.current_world_revision()
        if not messages:
            return IngestResult(object_refs=[], committed_refs=[], statuses=[], world_revision=snapshot)
        existing = self._existing(snapshot)
        pending: dict[tuple[str, str, str], tuple[str, ObjectRef]] = {}
        objects = []
        refs, statuses = [], []
        for message, content in zip(messages, contents):
            key = _identity(message)
            receipt = pending.get(key) or existing.get(key)
            if receipt is not None:
                if receipt[0] != content:
                    raise AIOSProtocolError(ErrorCode.IDEMPOTENCY_CONFLICT,
                                            "source message identity reused with different content",
                                            context={"reason": "source_message_conflict"})
                refs.append(receipt[1])
                statuses.append("duplicate_in_batch" if key in pending else "replayed")
                continue
            obj = Observation(
                object_id=new_object_id(ObjectType.OBSERVATION), subject_id=message.subject_id,
                occurred=TemporalExtent.point(message.occurred_at), learned_at=now, recorded_at=now,
                created_by="observation.ingest", source_kind=message.source_kind, modality=message.modality,
                value=message.value, unit=message.unit, data_quality=message.data_quality,
                raw_locator=message.raw_locator, source_refs=message.source_refs,
                metadata={"source_metadata": message.source_metadata, "ingress": {
                    "service": "observation.ingest", "version": 1, "source_id": message.source_id,
                    "source_event_id": message.source_event_id, "clock_provenance": self._clock_provenance}},
            )
            ref = ObjectRef(object_id=obj.object_id, revision=1)
            pending[key] = content, ref
            objects.append(obj)
            refs.append(ref)
            statuses.append("committed")
        if not objects:
            return IngestResult(object_refs=refs, committed_refs=[], statuses=statuses,
                                world_revision=snapshot, idempotent_replay=True)

        operation_id = new_operation_id()
        operation = OperationRequest(
            operation_id=operation_id, operation_name="observation.ingest",
            expected_world_revision=snapshot, reason="ingest source observations",
            idempotency_key=f"observation.ingest:{operation_id}",
            arguments={"source_messages": [list(key) for key in pending]},
        )
        # All validation, reference checks, inserts, audit and revision advancement
        # remain inside the frozen Core transaction. No per-row commits or SQL here.
        committed = self._store.commit(objects, operation)
        return IngestResult(object_refs=refs,
                            committed_refs=[ObjectRef(object_id=oid, revision=rev) for oid, rev in committed.object_refs],
                            statuses=statuses, world_revision=committed.world_revision,
                            operation_id=committed.operation_id)
