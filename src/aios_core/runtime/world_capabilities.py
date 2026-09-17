"""World/Data + Search/Recall adapters exposed to the AI Cognitive Runtime.

These adapters deliberately return candidates/evidence. They do not decide whether a
memory is important, whether a person is trustworthy, or what the AI should conclude.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from aios_core.contracts.enums import ObjectType
from aios_core.query.search import WorldSearchIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore

from .capabilities import CapabilityKind, CapabilityRegistry, CapabilitySpec

UTC = timezone.utc


def _parse_time(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(UTC)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(UTC)


def _occurred_start(payload: dict[str, Any]) -> datetime | None:
    occurred = payload.get("occurred")
    if not isinstance(occurred, dict) or occurred.get("unknown"):
        return None
    raw = occurred.get("start")
    if not isinstance(raw, str):
        return None
    try:
        return _parse_time(raw)
    except (TypeError, ValueError):
        return None


class WorldCapabilityBus:
    """Register deterministic world-navigation primitives for model use."""

    def __init__(self, store: SQLiteWorldStore, search: WorldSearchIndex | None = None) -> None:
        self.store = store
        self.search = search or WorldSearchIndex(store.db_path, store=store)

    def search_world(
        self,
        query: str,
        *,
        subject_id: str | None = None,
        limit: int = 10,
        view: str = "ANNOTATED",
        as_of: str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        terms = [part for part in query.split() if part]
        if not terms:
            terms = [query]
        page = self.search.co_search(
            terms,
            subject=subject_id,
            limit=max(1, min(int(limit), 100)),
            view=view,
            as_of=_parse_time(as_of),
            include_tombstones=False,
        )
        return [
            {
                "object_id": hit.object_id,
                "revision": hit.revision,
                "object_type": hit.object_type,
                "subject_id": hit.subject_id,
                "score": hit.score,
                "excerpt": hit.excerpt,
                "index_lag": page.lag,
            }
            for hit in page.hits
        ]

    def retrieve_original_observation(
        self,
        object_id: str,
        *,
        revision: int | None = None,
        as_of: str | datetime | None = None,
    ) -> dict[str, Any]:
        payload = self.store.get_payload(
            object_id,
            revision=revision,
            knowledge_cutoff=_parse_time(as_of),
        )
        if payload.get("object_type") != ObjectType.OBSERVATION.value:
            raise ValueError(f"{object_id} is not an Observation")
        return payload

    def focus_entity(
        self,
        entity_id: str,
        *,
        limit: int = 20,
    ) -> dict[str, Any]:
        entity = self.store.get_payload(entity_id)
        if entity.get("object_type") != ObjectType.ENTITY.value:
            raise ValueError(f"{entity_id} is not an Entity")
        page = self.search.search_by_entity(entity_id, limit=max(1, min(int(limit), 100)))
        return {
            "entity": entity,
            "candidate_context": [
                {
                    "object_id": hit.object_id,
                    "revision": hit.revision,
                    "object_type": hit.object_type,
                    "dimension_hint": hit.dimension,
                    "excerpt": hit.excerpt,
                    "score_hint": hit.score,
                }
                for hit in page.hits
            ],
        }

    def inspect_evidence(self, object_id: str, *, revision: int | None = None) -> dict[str, Any]:
        payload = self.store.get_payload(object_id, revision=revision)
        refs: list[dict[str, Any]] = []
        for key in (
            "member_refs",
            "support_evidence_set_refs",
            "counter_evidence_set_refs",
            "evidence_set_refs",
            "source_refs",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                for ref in value:
                    if isinstance(ref, dict) and isinstance(ref.get("object_id"), str):
                        refs.append(ref)
        resolved: list[dict[str, Any]] = []
        for ref in refs:
            try:
                resolved.append(
                    self.store.get_payload(
                        ref["object_id"],
                        revision=ref.get("revision"),
                    )
                )
            except Exception as exc:
                resolved.append(
                    {
                        "object_id": ref.get("object_id"),
                        "revision": ref.get("revision"),
                        "resolution_error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return {"target": payload, "referenced_evidence": resolved}

    def compare_claims(self, refs: Iterable[str]) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        for object_id in refs:
            payload = self.store.get_payload(str(object_id))
            if payload.get("object_type") != ObjectType.CLAIM.value:
                raise ValueError(f"{object_id} is not a Claim")
            claims.append(payload)
        return claims

    def search_timeline(
        self,
        start: str | datetime,
        end: str | datetime,
        *,
        subject_id: str | None = None,
        object_type: str | None = None,
        as_of: str | datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        start_dt = _parse_time(start)
        end_dt = _parse_time(end)
        if start_dt is None or end_dt is None:
            raise ValueError("start/end are required")
        if end_dt < start_dt:
            raise ValueError("end must not be before start")

        type_enum = ObjectType(object_type) if object_type is not None else None
        payloads = self.store.list_payloads(
            object_type=type_enum,
            subject_id=subject_id,
            knowledge_cutoff=_parse_time(as_of),
        )
        selected: list[tuple[datetime, dict[str, Any]]] = []
        for payload in payloads:
            occurred = _occurred_start(payload)
            if occurred is None or not (start_dt <= occurred <= end_dt):
                continue
            selected.append((occurred, payload))
        selected.sort(key=lambda item: item[0])
        return [payload for _, payload in selected[: max(1, min(int(limit), 500))]]

    def register_read_capabilities(self, registry: CapabilityRegistry) -> None:
        registry.register(
            CapabilitySpec(
                name="search_world",
                description="Search the world for candidate memories/evidence. Results are candidates, not conclusions.",
                kind=CapabilityKind.READ,
                input_schema={"query": "string", "subject_id": "string?", "limit": "int?", "view": "ANNOTATED|AS_KNOWN", "as_of": "iso_datetime?"},
            ),
            self.search_world,
        )
        registry.register(
            CapabilitySpec(
                name="retrieve_original_observation",
                description="Retrieve an original Observation by durable reference when a summary is insufficient.",
                kind=CapabilityKind.READ,
                input_schema={"object_id": "string", "revision": "int?", "as_of": "iso_datetime?"},
            ),
            self.retrieve_original_observation,
        )
        registry.register(
            CapabilitySpec(
                name="focus_entity",
                description="Open one entity and candidate context linked to it without deciding relationship meaning.",
                kind=CapabilityKind.READ,
                input_schema={"entity_id": "string", "limit": "int?"},
            ),
            self.focus_entity,
        )
        registry.register(
            CapabilitySpec(
                name="inspect_evidence",
                description="Inspect a durable object and resolve its direct evidence/source references.",
                kind=CapabilityKind.READ,
                input_schema={"object_id": "string", "revision": "int?"},
            ),
            self.inspect_evidence,
        )
        registry.register(
            CapabilitySpec(
                name="compare_claims",
                description="Retrieve multiple Claim objects side-by-side so the AI can compare them.",
                kind=CapabilityKind.READ,
                input_schema={"refs": "string[]"},
            ),
            self.compare_claims,
        )
        registry.register(
            CapabilitySpec(
                name="search_timeline",
                description="Read world objects whose occurred time falls in a requested interval; optional AS_KNOWN cutoff is independent.",
                kind=CapabilityKind.READ,
                input_schema={"start": "iso_datetime", "end": "iso_datetime", "subject_id": "string?", "object_type": "string?", "as_of": "iso_datetime?", "limit": "int?"},
            ),
            self.search_timeline,
        )
