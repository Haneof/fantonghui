"""Evidence retrieval and grounding integrity for the AI cognitive runtime.

R5/R6 boundary
--------------
This module is infrastructure, not an advisor brain. It may:
- retrieve evidence candidates from the world;
- pin exact object revisions;
- verify that selected references resolve;
- preserve the model's decision and text exactly;
- report descriptive token/evidence metadata.

It must not:
- decide how much evidence is "enough";
- decide whether the AI should speak or stay silent;
- choose an action for the AI;
- classify tone/style with regex or keyword lists;
- truncate, rewrite, rank, or substitute natural-language output;
- assign cognitive confidence from mechanical hit counts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.registry import canonical_model_for_object_type
from aios_core.contracts.time import as_utc
from aios_core.query.search import WorldSearchIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

__all__ = [
    "AdviceDecisionKind",
    "EvidenceGroundingService",
    "EvidencePacket",
    "EvidenceQuery",
    "ModelAdviceDecision",
    "estimate_tokens",
]


def estimate_tokens(text: str) -> int:
    """Descriptive token estimate; never a semantic quality gate."""

    tokens = 0
    run = False
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            if run:
                tokens += 1
                run = False
            tokens += 1
        elif ch.isascii() and ch.isalnum():
            run = True
        else:
            if run:
                tokens += 1
                run = False
    return tokens + (1 if run else 0)


class EvidenceQuery(BaseModel):
    """Model/runtime-selected retrieval intent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(min_length=1)
    keywords: tuple[str, ...] = Field(min_length=1)
    entity_id: str | None = None
    dimension: str | None = None


class EvidencePacket(BaseModel):
    """Candidate evidence returned to the cognitive runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: EvidenceQuery
    evidence_pointers: tuple[ObjectRef, ...] = ()
    evidence_chain: tuple[str, ...] = ()
    retrieved_at: datetime

    @property
    def hit_count(self) -> int:
        return len(self.evidence_pointers)

    @model_validator(mode="after")
    def validate_pins(self) -> "EvidencePacket":
        for ref in self.evidence_pointers:
            if ref.revision is None:
                raise ValueError("retrieved evidence must pin an exact revision")
        return self


class AdviceDecisionKind(StrEnum):
    RESPOND = "respond"
    SILENCE = "silence"


class ModelAdviceDecision(BaseModel):
    """An already-made cognitive decision, preserved without semantic rewriting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: AdviceDecisionKind
    intent: str = Field(min_length=1)
    conclusion: str = ""
    action: str | None = None
    rationale: str = Field(min_length=1)
    evidence_pointers: tuple[ObjectRef, ...] = ()
    produced_at: datetime
    token_estimate: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_shape(self) -> "ModelAdviceDecision":
        if self.decision is AdviceDecisionKind.RESPOND and not self.conclusion:
            raise ValueError("respond decision requires model-supplied conclusion")
        if self.decision is AdviceDecisionKind.SILENCE and self.conclusion:
            raise ValueError("silence decision must not carry user-visible conclusion")
        for ref in self.evidence_pointers:
            if ref.revision is None:
                raise ValueError("selected evidence must pin an exact revision")
        return self


class EvidenceGroundingService:
    """World retrieval + reference integrity boundary for model-owned advice."""

    def __init__(
        self,
        store: SQLiteWorldStore,
        *,
        index: WorldSearchIndex | None = None,
    ) -> None:
        self.store = store
        self.index = index or WorldSearchIndex(store.db_path, store=store)
        self._build_index()

    def _build_index(self) -> int:
        """Catch the projection index up to the current world revision."""

        applied = 0
        for _ in range(64):
            if self.index.lag() <= 0:
                break
            applied += self.index.catch_up(max_rows=2_000)
        if self.index.lag() > 0:
            applied += self.index.catch_up(max_rows=100_000)
        return applied

    def retrieve(
        self,
        query: EvidenceQuery,
        *,
        extra_keywords: Sequence[str] = (),
        limit: int = 8,
        time_range: tuple[datetime, datetime] | None = None,
        now: datetime | None = None,
    ) -> EvidencePacket:
        """Return evidence candidates; zero hits is data, not a forced decision."""

        if limit < 1:
            raise ValueError("limit must be >= 1")
        stamp = as_utc(now or datetime.now(UTC), "now")
        keywords = tuple(dict.fromkeys((*query.keywords, *extra_keywords)))

        seen: set[str] = set()
        hits: list[object] = []
        for keyword in keywords:
            page = self.index.search_mind(
                keywords=[keyword],
                dimension=query.dimension,
                entity_id=query.entity_id,
                time_range=time_range,
                limit=limit,
            )
            for hit in page.hits:
                if hit.object_id in seen:
                    continue
                seen.add(hit.object_id)
                hits.append(hit)
        hits = hits[:limit]

        pointers: list[ObjectRef] = []
        chain: list[str] = []
        seen_excerpt: set[str] = set()
        for hit in hits:
            revision = getattr(hit, "revision", None)
            if revision is None or int(revision) < 1:
                raise ValueError(
                    "search projection returned an unpinned hit; "
                    "evidence candidates must pin revisions"
                )
            pointers.append(
                ObjectRef(object_id=str(getattr(hit, "object_id")), revision=int(revision))
            )
            excerpt = str(getattr(hit, "excerpt", "") or "").strip()
            if excerpt and excerpt not in seen_excerpt:
                seen_excerpt.add(excerpt)
                chain.append(excerpt)

        return EvidencePacket(
            query=query,
            evidence_pointers=tuple(pointers),
            evidence_chain=tuple(chain),
            retrieved_at=stamp,
        )

    def record_model_decision(
        self,
        packet: EvidencePacket,
        *,
        decision: AdviceDecisionKind,
        conclusion: str = "",
        action: str | None = None,
        rationale: str,
        evidence_pointers: Sequence[ObjectRef] = (),
        now: datetime | None = None,
    ) -> ModelAdviceDecision:
        """Validate references and preserve the cognitive decision exactly."""

        stamp = as_utc(now or datetime.now(UTC), "now")
        selected = tuple(evidence_pointers)
        available = {
            (ref.object_id, ref.revision)
            for ref in packet.evidence_pointers
        }
        for ref in selected:
            if ref.revision is None:
                raise ValueError("selected evidence must pin an exact revision")
            if (ref.object_id, ref.revision) not in available:
                raise ValueError(
                    "selected evidence must come from the supplied EvidencePacket"
                )
            payload = self.store.get_payload(ref.object_id, revision=ref.revision)
            if not payload:
                raise ValueError(
                    f"selected evidence does not resolve: {ref.object_id}@{ref.revision}"
                )

        return ModelAdviceDecision(
            decision=decision,
            intent=packet.query.intent,
            conclusion=conclusion,
            action=action,
            rationale=rationale,
            evidence_pointers=selected,
            produced_at=stamp,
            token_estimate=estimate_tokens(conclusion),
        )

    def verify_grounding(self, decision: ModelAdviceDecision) -> bool:
        """Verify selected evidence references only; never judge semantic sufficiency."""

        if not decision.evidence_pointers:
            return False
        for ref in decision.evidence_pointers:
            try:
                payload = self.store.get_payload(ref.object_id, revision=ref.revision)
            except Exception:
                return False
            if not payload:
                return False
        return True

    def evidence_objects(
        self, refs: Sequence[ObjectRef] | ModelAdviceDecision
    ) -> tuple[dict, ...]:
        selected = refs.evidence_pointers if isinstance(refs, ModelAdviceDecision) else tuple(refs)
        payloads: list[dict] = []
        for ref in selected:
            payloads.append(self.store.get_payload(ref.object_id, revision=ref.revision))
        return tuple(payloads)

    def evidence_object_types(
        self, refs: Sequence[ObjectRef] | ModelAdviceDecision
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    str(payload.get("object_type"))
                    for payload in self.evidence_objects(refs)
                }
            )
        )

    @staticmethod
    def canonical_models(object_types: Iterable[str]) -> tuple[str, ...]:
        names: list[str] = []
        for value in object_types:
            model = canonical_model_for_object_type(ObjectType(value))
            names.append(model.__name__)
        return tuple(names)
