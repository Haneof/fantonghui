"""Append-only dual-lens projection index for retrospective cognition.

The index never rewrites historical fact payloads.  It joins immutable facts
with overlays at read time and applies both valid-time and knowledge-time
cutoffs, yielding an ``as_known`` historical view or a current annotated view
from the same bytes.
"""

from __future__ import annotations

import bisect
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import require_aware


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ImmutableProjectionFact:
    object_id: str
    revision: int
    entity_id: str
    valid_start_ns: int
    valid_end_ns: int
    learned_at_ns: int
    payload_json: str
    payload_sha256: str

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @classmethod
    def create(
        cls,
        *,
        object_id: str,
        revision: int,
        entity_id: str,
        valid_start_ns: int,
        valid_end_ns: int,
        learned_at_ns: int,
        payload: dict[str, Any],
    ) -> ImmutableProjectionFact:
        if not object_id.strip() or not entity_id.strip():
            raise ValueError("fact identities must not be blank")
        if revision < 1:
            raise ValueError("fact revision must be positive")
        if not 0 <= valid_start_ns <= valid_end_ns <= learned_at_ns:
            raise ValueError("fact bitemporal bounds are invalid")
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            object_id=object_id,
            revision=revision,
            entity_id=entity_id,
            valid_start_ns=valid_start_ns,
            valid_end_ns=valid_end_ns,
            learned_at_ns=learned_at_ns,
            payload_json=payload_json,
            payload_sha256=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class ProjectionOverlay:
    annotation_id: str
    entity_id: str
    valid_start_ns: int
    valid_end_ns: int
    learned_at_ns: int
    payload_json: str
    source_ref: str

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @classmethod
    def create(
        cls,
        *,
        annotation_id: str,
        entity_id: str,
        valid_start_ns: int,
        valid_end_ns: int,
        learned_at_ns: int,
        payload: dict[str, Any],
        source_ref: str,
    ) -> ProjectionOverlay:
        if not annotation_id.strip() or not entity_id.strip() or not source_ref.strip():
            raise ValueError("overlay identities and source_ref must not be blank")
        if not 0 <= valid_start_ns <= valid_end_ns <= learned_at_ns:
            raise ValueError("overlay bitemporal bounds are invalid")
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            annotation_id=annotation_id,
            entity_id=entity_id,
            valid_start_ns=valid_start_ns,
            valid_end_ns=valid_end_ns,
            learned_at_ns=learned_at_ns,
            payload_json=payload_json,
            source_ref=source_ref,
        )


@dataclass(frozen=True, slots=True)
class EpistemicProjection:
    entity_id: str
    target_time_ns: int
    knowledge_cutoff_ns: int
    facts: tuple[ImmutableProjectionFact, ...]
    overlays: tuple[ProjectionOverlay, ...]
    candidate_rows_examined: int
    total_index_rows: int

    @property
    def historical_hashes(self) -> tuple[str, ...]:
        return tuple(fact.payload_sha256 for fact in self.facts)

    @property
    def scan_reduction_ratio(self) -> float:
        if self.total_index_rows == 0:
            return 0.0
        return 1.0 - self.candidate_rows_examined / self.total_index_rows


class DualLensProjectionIndex:
    """A read-time overlay projection with append-only insertion semantics."""

    def __init__(self) -> None:
        self._facts_by_id: dict[tuple[str, int], ImmutableProjectionFact] = {}
        self._overlays_by_id: dict[str, ProjectionOverlay] = {}
        self._facts_by_entity: dict[str, list[ImmutableProjectionFact]] = defaultdict(
            list
        )
        self._fact_starts: dict[str, list[int]] = defaultdict(list)
        self._overlays_by_entity: dict[str, list[ProjectionOverlay]] = defaultdict(list)
        self._overlay_starts: dict[str, list[int]] = defaultdict(list)

    def append_fact(self, fact: ImmutableProjectionFact) -> None:
        key = (fact.object_id, fact.revision)
        previous = self._facts_by_id.get(key)
        if previous is not None:
            if previous != fact:
                raise ValueError(f"fact identity already has different bytes: {key}")
            return
        if _payload_hash(fact.payload) != fact.payload_sha256:
            raise ValueError("fact payload does not match its immutable digest")
        self._facts_by_id[key] = fact
        self._insert_sorted(
            self._facts_by_entity[fact.entity_id],
            self._fact_starts[fact.entity_id],
            fact.valid_start_ns,
            fact,
        )

    def append_overlay(self, overlay: ProjectionOverlay) -> None:
        previous = self._overlays_by_id.get(overlay.annotation_id)
        if previous is not None:
            if previous != overlay:
                raise ValueError(
                    "annotation_id already has different append-only content: "
                    f"{overlay.annotation_id}"
                )
            return
        self._overlays_by_id[overlay.annotation_id] = overlay
        self._insert_sorted(
            self._overlays_by_entity[overlay.entity_id],
            self._overlay_starts[overlay.entity_id],
            overlay.valid_start_ns,
            overlay,
        )

    def as_known(
        self,
        entity_id: str,
        *,
        target_time_ns: int,
        knowledge_cutoff_ns: int,
    ) -> EpistemicProjection:
        return self._project(entity_id, target_time_ns, knowledge_cutoff_ns)

    def annotated(
        self,
        entity_id: str,
        *,
        target_time_ns: int,
        current_knowledge_ns: int,
    ) -> EpistemicProjection:
        return self._project(entity_id, target_time_ns, current_knowledge_ns)

    def verify_immutable_facts(self) -> bool:
        return all(
            _payload_hash(fact.payload) == fact.payload_sha256
            for fact in self._facts_by_id.values()
        )

    @property
    def fact_count(self) -> int:
        return len(self._facts_by_id)

    @property
    def overlay_count(self) -> int:
        return len(self._overlays_by_id)

    def _project(
        self,
        entity_id: str,
        target_time_ns: int,
        cutoff_ns: int,
    ) -> EpistemicProjection:
        if not entity_id.strip():
            raise ValueError("entity_id must not be blank")
        if target_time_ns < 0 or cutoff_ns < 0:
            raise ValueError("projection times must be non-negative")
        fact_rows = self._facts_by_entity.get(entity_id, [])
        fact_end = bisect.bisect_right(
            self._fact_starts.get(entity_id, []),
            target_time_ns,
        )
        candidates = fact_rows[:fact_end]
        facts = tuple(
            fact
            for fact in candidates
            if fact.valid_end_ns >= target_time_ns and fact.learned_at_ns <= cutoff_ns
        )

        overlay_rows = self._overlays_by_entity.get(entity_id, [])
        overlay_end = bisect.bisect_right(
            self._overlay_starts.get(entity_id, []),
            target_time_ns,
        )
        overlay_candidates = overlay_rows[:overlay_end]
        overlays = tuple(
            overlay
            for overlay in overlay_candidates
            if overlay.valid_end_ns >= target_time_ns
            and overlay.learned_at_ns <= cutoff_ns
        )
        return EpistemicProjection(
            entity_id=entity_id,
            target_time_ns=target_time_ns,
            knowledge_cutoff_ns=cutoff_ns,
            facts=facts,
            overlays=overlays,
            candidate_rows_examined=len(candidates) + len(overlay_candidates),
            total_index_rows=self.fact_count + self.overlay_count,
        )

    @staticmethod
    def _insert_sorted(
        rows: list[Any],
        starts: list[int],
        start_ns: int,
        value: Any,
    ) -> None:
        position = bisect.bisect_right(starts, start_ns)
        starts.insert(position, start_ns)
        rows.insert(position, value)


def dual_lens_projection_tool_proposal(now: datetime) -> ToolProposal:
    require_aware(now, "now")
    return ToolProposal(
        object_id="tool_proposal_dual_lens_projection_v1",
        subject_id="aios_core",
        learned_at=now,
        recorded_at=now,
        created_by="massive_life_bench",
        capability_gap=(
            "Retrospective discoveries need a current annotated view without "
            "rewriting or recursively recomputing historical facts."
        ),
        use_cases=[
            "AsKnown historical truth at an earlier knowledge cutoff",
            "current annotated interpretation over identical fact hashes",
            "entity/time bounded virtual projection without history duplication",
        ],
        current_limitations=[
            "in-memory implementation is process-local",
            "very dense per-entity history may need an interval tree",
        ],
        proposed_interface={
            "append_fact": "ImmutableProjectionFact -> None",
            "append_overlay": "ProjectionOverlay -> None",
            "as_known": "(entity, valid_time, cutoff) -> EpistemicProjection",
            "annotated": "(entity, valid_time, now) -> EpistemicProjection",
        },
        expected_benefit=(
            "Preserve byte-identical history while reducing reads to the selected "
            "entity/time projection and making knowledge-time semantics explicit."
        ),
        validation_plan=(
            "Seal historical hashes, append a present-day overlay, compare both "
            "lenses, and prove only direct consumers are invalidated."
        ),
    )


__all__ = [
    "DualLensProjectionIndex",
    "EpistemicProjection",
    "ImmutableProjectionFact",
    "ProjectionOverlay",
    "dual_lens_projection_tool_proposal",
]
