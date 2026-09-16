"""Lossless five-level temporal summary pointer pyramid.

Summary nodes are an additional observation layer: they contain pointers and
content hashes, never replacements for source observations.  The hierarchy is
``year -> quarter -> month -> week-of-month -> day -> observation`` so every
leaf has exactly one deterministic drill-down path.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from aios_core.operations.adaptive_temporal_compressor import (
    CompressedObservation,
    RawSemanticClass,
)


class TemporalGranularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


@dataclass(frozen=True, slots=True)
class TemporalSummaryNode:
    node_id: str
    granularity: TemporalGranularity
    period_key: str
    start_ns: int
    end_ns: int
    child_node_ids: tuple[str, ...]
    observation_refs: tuple[str, ...]
    source_sha256: str
    source_count: int
    representative_observation_ref: str
    summary_text: str


@dataclass(frozen=True, slots=True)
class PyramidBuildReceipt:
    source_observation_count: int
    unique_leaf_count: int
    summary_node_count: int
    year_root_count: int
    duplicate_leaf_refs: int
    broken_pointer_count: int
    evidence_chain_break_rate: float


class LosslessTemporalPyramid:
    """Build and navigate a deterministic pointer-only temporal hierarchy."""

    def __init__(self) -> None:
        self._observations: dict[str, CompressedObservation] = {}
        self._nodes: dict[str, TemporalSummaryNode] = {}
        self._parent_by_node: dict[str, str] = {}
        self._day_by_observation: dict[str, str] = {}
        self._roots: tuple[str, ...] = ()
        self._receipt: PyramidBuildReceipt | None = None

    def build(
        self,
        observations: tuple[CompressedObservation, ...],
    ) -> PyramidBuildReceipt:
        if self._receipt is not None:
            raise RuntimeError("pyramid instances are single-build")
        duplicates = 0
        for observation in observations:
            previous = self._observations.get(observation.observation_id)
            if previous is not None:
                if previous != observation:
                    raise ValueError(
                        "observation id has conflicting immutable content: "
                        f"{observation.observation_id}"
                    )
                duplicates += 1
                continue
            self._observations[observation.observation_id] = observation

        leaves_by_day: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        for observation in self._observations.values():
            dt = datetime.fromtimestamp(
                observation.occurred_at_ns / 1_000_000_000,
                tz=UTC,
            )
            leaves_by_day[(dt.year, dt.month, dt.day)].append(
                observation.observation_id
            )

        child_groups: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        for day_key in sorted(leaves_by_day):
            year, month, day = day_key
            observation_ids = tuple(sorted(leaves_by_day[day_key]))
            node = self._make_leaf_node(day_key, observation_ids)
            self._nodes[node.node_id] = node
            for observation_id in observation_ids:
                self._day_by_observation[observation_id] = node.node_id
            child_groups[(year, month, (day - 1) // 7 + 1)].append(node.node_id)

        weeks_by_month: dict[tuple[int, int], list[str]] = defaultdict(list)
        for week_key in sorted(child_groups):
            year, month, week = week_key
            node = self._make_parent_node(
                TemporalGranularity.WEEK,
                f"{year:04d}-{month:02d}-W{week}",
                tuple(child_groups[week_key]),
            )
            self._register_parent(node)
            weeks_by_month[(year, month)].append(node.node_id)

        months_by_quarter: dict[tuple[int, int], list[str]] = defaultdict(list)
        for month_key in sorted(weeks_by_month):
            year, month = month_key
            node = self._make_parent_node(
                TemporalGranularity.MONTH,
                f"{year:04d}-{month:02d}",
                tuple(weeks_by_month[month_key]),
            )
            self._register_parent(node)
            months_by_quarter[(year, (month - 1) // 3 + 1)].append(node.node_id)

        quarters_by_year: dict[int, list[str]] = defaultdict(list)
        for quarter_key in sorted(months_by_quarter):
            year, quarter = quarter_key
            node = self._make_parent_node(
                TemporalGranularity.QUARTER,
                f"{year:04d}-Q{quarter}",
                tuple(months_by_quarter[quarter_key]),
            )
            self._register_parent(node)
            quarters_by_year[year].append(node.node_id)

        roots: list[str] = []
        for year in sorted(quarters_by_year):
            node = self._make_parent_node(
                TemporalGranularity.YEAR,
                str(year),
                tuple(quarters_by_year[year]),
            )
            self._register_parent(node)
            roots.append(node.node_id)
        self._roots = tuple(roots)

        broken = self._count_broken_pointers()
        unique_leaf_count = len(self._observations)
        break_rate = broken / unique_leaf_count if unique_leaf_count else 0.0
        self._receipt = PyramidBuildReceipt(
            source_observation_count=len(observations),
            unique_leaf_count=unique_leaf_count,
            summary_node_count=len(self._nodes),
            year_root_count=len(self._roots),
            duplicate_leaf_refs=duplicates,
            broken_pointer_count=broken,
            evidence_chain_break_rate=break_rate,
        )
        return self._receipt

    @property
    def roots(self) -> tuple[TemporalSummaryNode, ...]:
        return tuple(self._nodes[node_id] for node_id in self._roots)

    @property
    def receipt(self) -> PyramidBuildReceipt:
        if self._receipt is None:
            raise RuntimeError("pyramid has not been built")
        return self._receipt

    def get_node(self, node_id: str) -> TemporalSummaryNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown summary node: {node_id}") from exc

    def get_observation(self, observation_id: str) -> CompressedObservation:
        try:
            return self._observations[observation_id]
        except KeyError as exc:
            raise KeyError(f"unknown observation: {observation_id}") from exc

    def expand(self, node_id: str) -> tuple[str, ...]:
        """Return every source observation under a node without copying payloads."""

        root = self.get_node(node_id)
        pending = [root]
        leaves: list[str] = []
        while pending:
            node = pending.pop()
            leaves.extend(node.observation_refs)
            pending.extend(
                self.get_node(child_id) for child_id in reversed(node.child_node_ids)
            )
        return tuple(leaves)

    def drill_path(
        self,
        root_node_id: str,
        observation_id: str,
    ) -> tuple[str, ...]:
        """Return year-to-leaf pointer path ending in the observation id."""

        self.get_node(root_node_id)
        self.get_observation(observation_id)
        try:
            current = self._day_by_observation[observation_id]
        except KeyError as exc:  # pragma: no cover - guarded by build invariants
            raise RuntimeError("observation is not attached to a day node") from exc
        reverse_path = [current]
        while current in self._parent_by_node:
            current = self._parent_by_node[current]
            reverse_path.append(current)
        path = tuple(reversed(reverse_path)) + (observation_id,)
        if path[0] != root_node_id:
            raise ValueError(
                f"observation {observation_id} is not below root {root_node_id}"
            )
        return path

    def direct_drill(self, observation_id: str) -> CompressedObservation:
        """Constitutional fast path: callers may bypass every summary layer."""

        return self.get_observation(observation_id)

    def verify_lossless(self) -> bool:
        if self._receipt is None or self._count_broken_pointers() != 0:
            return False
        expanded: list[str] = []
        for root in self._roots:
            expanded.extend(self.expand(root))
        return (
            len(expanded) == len(set(expanded))
            and set(expanded) == set(self._observations)
            and all(
                root.representative_observation_ref in self.expand(root.node_id)
                for root in self.roots
            )
            and all(self._verify_node_hash(node) for node in self._nodes.values())
        )

    def _make_leaf_node(
        self,
        day_key: tuple[int, int, int],
        observation_ids: tuple[str, ...],
    ) -> TemporalSummaryNode:
        year, month, day = day_key
        observations = [self._observations[item] for item in observation_ids]
        digest = self._hash_parts(
            *(observation.source_sha256 for observation in observations)
        )
        period = f"{year:04d}-{month:02d}-{day:02d}"
        representative = next(
            (
                item
                for item in observations
                if item.semantic_class
                in {RawSemanticClass.CORE_QUOTE, RawSemanticClass.KEY_EVIDENCE}
            ),
            observations[0],
        )
        return TemporalSummaryNode(
            node_id=f"summary_day_{period}_{digest[:12]}",
            granularity=TemporalGranularity.DAY,
            period_key=period,
            start_ns=min(item.occurred_at_ns for item in observations),
            end_ns=max(item.occurred_at_ns for item in observations),
            child_node_ids=(),
            observation_refs=observation_ids,
            source_sha256=digest,
            source_count=len(observation_ids),
            representative_observation_ref=representative.observation_id,
            summary_text=(
                f"{period}: {len(observation_ids)} retained observations; "
                f"representative evidence: {representative.summary[:96]}"
            ),
        )

    def _make_parent_node(
        self,
        granularity: TemporalGranularity,
        period_key: str,
        child_ids: tuple[str, ...],
    ) -> TemporalSummaryNode:
        children = [self._nodes[item] for item in child_ids]
        digest = self._hash_parts(*(child.source_sha256 for child in children))
        source_count = sum(child.source_count for child in children)
        representative_ref = next(
            (
                child.representative_observation_ref
                for child in children
                if self._observations[
                    child.representative_observation_ref
                ].semantic_class
                in {RawSemanticClass.CORE_QUOTE, RawSemanticClass.KEY_EVIDENCE}
            ),
            children[0].representative_observation_ref,
        )
        return TemporalSummaryNode(
            node_id=f"summary_{granularity.value}_{period_key}_{digest[:12]}",
            granularity=granularity,
            period_key=period_key,
            start_ns=min(child.start_ns for child in children),
            end_ns=max(child.end_ns for child in children),
            child_node_ids=child_ids,
            observation_refs=(),
            source_sha256=digest,
            source_count=source_count,
            representative_observation_ref=representative_ref,
            summary_text=(
                f"{period_key}: {source_count} source observations via "
                f"{len(child_ids)} {children[0].granularity.value} nodes; "
                "macro thread remains pinned to representative evidence "
                f"{representative_ref}"
            ),
        )

    def _register_parent(self, node: TemporalSummaryNode) -> None:
        self._nodes[node.node_id] = node
        for child_id in node.child_node_ids:
            if child_id in self._parent_by_node:
                raise ValueError(f"summary node has multiple parents: {child_id}")
            self._parent_by_node[child_id] = node.node_id

    def _count_broken_pointers(self) -> int:
        broken = 0
        for node in self._nodes.values():
            broken += sum(child not in self._nodes for child in node.child_node_ids)
            broken += sum(
                observation not in self._observations
                for observation in node.observation_refs
            )
        return broken

    def _verify_node_hash(self, node: TemporalSummaryNode) -> bool:
        if node.observation_refs:
            expected = self._hash_parts(
                *(
                    self._observations[item].source_sha256
                    for item in node.observation_refs
                )
            )
        else:
            expected = self._hash_parts(
                *(self._nodes[item].source_sha256 for item in node.child_node_ids)
            )
        return expected == node.source_sha256

    @staticmethod
    def _hash_parts(*parts: str) -> str:
        hasher = hashlib.sha256()
        for part in parts:
            hasher.update(part.encode("ascii"))
            hasher.update(b"\x00")
        return hasher.hexdigest()


__all__ = [
    "LosslessTemporalPyramid",
    "PyramidBuildReceipt",
    "TemporalGranularity",
    "TemporalSummaryNode",
]
