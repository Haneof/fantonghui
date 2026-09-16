"""M5 multidimensional mind search and three-path execution substrate.

The engine joins Dimension, Claim, Entity, Observation, and Annotation records
behind one bounded result contract.  It deliberately exposes three execution
paths so operation experience can compare measured cost without pretending
that a cheap low-recall query is intelligent.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from itertools import pairwise
from math import ceil
from pathlib import Path
from threading import RLock
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.contracts.time import as_utc, require_aware

_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


class SearchPathway(StrEnum):
    BRUTE_FORCE_SCAN = "brute_force_scan"
    KEYWORD_SEARCH = "keyword_search"
    HIERARCHICAL_TOPO = "hierarchical_topo"


class MindObjectType(StrEnum):
    DIMENSION = "dimension"
    CLAIM = "claim"
    ENTITY = "entity"
    OBSERVATION = "observation"
    ANNOTATION = "annotation"
    EVENT = "event"
    RELATION = "relation"


class ConservativeTokenMeter:
    """Dependency-free output envelope using UTF-8 bytes as strict units."""

    @staticmethod
    def count(text: str) -> int:
        return len(text.encode("utf-8"))

    @staticmethod
    def truncate(text: str, limit: int) -> str:
        if limit < 0:
            raise ValueError("token limit must be non-negative")
        return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")

    @staticmethod
    def estimate_context_tokens(text: str) -> int:
        """Comparable BPE estimate for pathway input-cost receipts only."""

        return max(1, ceil(len(text.encode("utf-8")) / 4))


def _tokens(text: str) -> frozenset[str]:
    lowered = text.casefold()
    result = set(_WORD_RE.findall(lowered))
    for run in _CJK_RE.findall(lowered):
        if len(run) == 1:
            result.add(run)
        result.update(left + right for left, right in pairwise(run))
    return frozenset(result)


def tokens_for(text: str) -> set[str]:
    """Backward-compatible public tokenizer (ASCII words + CJK bigrams)."""

    return set(_tokens(text))


def normalize_alias(text: str) -> str:
    return " ".join(text.casefold().split())


def _iter_ref_ids(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        object_id = node.get("object_id")
        if isinstance(object_id, str) and "revision" in node:
            yield object_id
        for value in node.values():
            yield from _iter_ref_ids(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_ref_ids(item)


def derive_dimension(payload: dict[str, Any], object_type: str) -> str:
    """Derive a stable dimension without copying arbitrary payload fields."""

    explicit = payload.get("dimension")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().casefold()
    dimensions = payload.get("dimensions")
    if isinstance(dimensions, list):
        for item in dimensions:
            if isinstance(item, str) and item.strip():
                return item.strip().casefold()

    source = str(payload.get("source_kind", "")).casefold()
    source_dimensions = {
        "biometrics": "dim_health",
        "heart_rate": "dim_health",
        "sleep": "dim_health",
        "transaction": "dim_finance",
        "bank": "dim_finance",
        "loan": "dim_finance",
        "contract": "dim_finance",
        "chat": "dim_social",
        "message": "dim_social",
        "meeting": "dim_work",
        "work_log": "dim_work",
    }
    if source in source_dimensions:
        return source_dimensions[source]

    text = " ".join(
        value
        for key in ("content", "value", "title", "description", "semantic_overlay")
        if isinstance((value := payload.get(key)), str)
    ).casefold()
    if any(term in text for term in ("心率", "早搏", "膝盖", "睡眠", "血压")):
        return "dim_health"
    if any(term in text for term in ("借款", "诈骗", "判决", "合同", "转账")):
        return "dim_finance"
    if any(term in text for term in ("母亲", "朋友", "聊天", "生日")):
        return "dim_social"
    if any(term in text for term in ("会议", "加班", "代码", "工作")):
        return "dim_work"
    if object_type.casefold() == MindObjectType.DIMENSION.value:
        return str(payload.get("name", "dim_general")).strip().casefold()
    return "dim_general"


class MindDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    object_id: str = Field(min_length=1, max_length=240)
    revision: int = Field(default=1, ge=1)
    object_type: MindObjectType
    dimension: str = Field(min_length=1, max_length=160)
    entity_id: str | None = Field(default=None, min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=100_000)
    occurred_at: datetime
    aliases: frozenset[str] = Field(default_factory=frozenset)
    related_entity_ids: frozenset[str] = Field(default_factory=frozenset)
    related_object_ids: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "occurred_at")
        return value

    @field_validator("dimension")
    @classmethod
    def normalize_dimension(cls, value: str) -> str:
        return value.casefold()


class MindSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    keywords: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    dimension: str | None = Field(default=None, min_length=1, max_length=160)
    entity_id: str | None = Field(default=None, min_length=1, max_length=240)
    linked_object_id: str | None = Field(default=None, min_length=1, max_length=240)
    object_types: tuple[MindObjectType, ...] = Field(default_factory=tuple)
    time_start: datetime | None = None
    time_end: datetime | None = None
    include_annotations: bool = False
    limit: int = Field(default=4, ge=1, le=50)

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(value.strip().casefold() for value in values))
        if any(not value for value in normalized):
            raise ValueError("keywords must not contain blanks")
        return normalized

    @field_validator("dimension")
    @classmethod
    def normalize_optional_dimension(cls, value: str | None) -> str | None:
        return value.casefold() if value is not None else None

    @field_validator("time_start", "time_end")
    @classmethod
    def query_times_must_be_aware(
        cls, value: datetime | None, info: Any
    ) -> datetime | None:
        require_aware(value, info.field_name)
        return value

    @model_validator(mode="after")
    def time_range_must_be_ordered(self) -> MindSearchQuery:
        if (
            self.time_start is not None
            and self.time_end is not None
            and as_utc(self.time_end) < as_utc(self.time_start)
        ):
            raise ValueError("time_end cannot precede time_start")
        if (
            not self.keywords
            and self.dimension is None
            and self.entity_id is None
            and self.linked_object_id is None
        ):
            raise ValueError(
                "search requires keywords, dimension, entity_id, or linked_object_id"
            )
        return self


class MindSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str
    revision: int = Field(ge=1)
    object_type: MindObjectType
    entity_id: str | None = None
    dimension: str
    excerpt: str
    score: int = Field(ge=0)
    is_annotation: bool = False
    related_entity_ids: tuple[str, ...] = ()
    estimated_tokens: int = Field(ge=1, le=150)

    @property
    def subject_id(self) -> str:
        """Compatibility name used by the original co_search result contract."""

        return self.entity_id or "user_1"

    @model_validator(mode="after")
    def hit_receipt_matches_excerpt(self) -> MindSearchHit:
        physical = ConservativeTokenMeter.count(self.excerpt)
        if self.estimated_tokens != physical:
            raise ValueError("estimated_tokens must match physical UTF-8 excerpt")
        return self


class MindSearchPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = "ok"
    pathway: SearchPathway = SearchPathway.HIERARCHICAL_TOPO
    hits: tuple[MindSearchHit, ...] = Field(default_factory=tuple, max_length=50)
    total_estimated_tokens: int = Field(default=0, ge=0, le=500)
    query_intent: str = ""
    ambiguous_keywords: dict[str, list[str]] = Field(default_factory=dict)
    lag: int = Field(default=0, ge=0)
    world_revision: int = Field(default=0, ge=0)
    index_watermark: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def page_receipt_matches_hits(self) -> MindSearchPage:
        expected = sum(hit.estimated_tokens for hit in self.hits)
        if self.total_estimated_tokens != expected:
            raise ValueError("page token receipt must equal hit envelopes")
        return self


class PathwaySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page: MindSearchPage
    inspected_document_count: int = Field(ge=0)
    context_token_cost: int = Field(ge=0)


class MultidimensionalSearchEngine:
    """In-memory projection with optional SQLiteWorldStore catch-up."""

    MAX_SINGLE_HIT_TOKENS: ClassVar[int] = 150
    MAX_PAGE_TOKENS: ClassVar[int] = 500

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        store: Any | None = None,
        documents: Iterable[MindDocument] = (),
    ) -> None:
        self.db_path = str(db_path) if db_path is not None else None
        self._store = store
        self._documents: dict[tuple[str, int], MindDocument] = {}
        self._tokens_by_key: dict[tuple[str, int], frozenset[str]] = {}
        self._postings: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self._dimensions: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self._entities: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self._object_links: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self._annotations_by_target: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self._aliases: dict[str, set[str]] = defaultdict(set)
        self._entity_aliases: dict[str, set[str]] = defaultdict(set)
        self._types: dict[MindObjectType, set[tuple[str, int]]] = defaultdict(set)
        self._lock = RLock()
        self._watermark = 0
        for document in documents:
            self.add_document(document)

    def add_document(self, document: MindDocument) -> None:
        normalized = MindDocument.model_validate(document)
        key = (normalized.object_id, normalized.revision)
        with self._lock:
            previous = self._documents.get(key)
            if previous is not None:
                if previous != normalized:
                    raise ValueError(
                        f"document revision already indexed with different content: {key}"
                    )
                return
            self._documents[key] = normalized
            document_tokens = _tokens(normalized.text)
            self._tokens_by_key[key] = document_tokens
            for token in document_tokens:
                self._postings[token].add(key)
            self._dimensions[normalized.dimension].add(key)
            self._types[normalized.object_type].add(key)
            self._object_links[normalized.object_id].add(key)
            for object_id in normalized.related_object_ids:
                self._object_links[object_id].add(key)
                if normalized.object_type is MindObjectType.ANNOTATION:
                    self._annotations_by_target[object_id].add(key)
            if normalized.entity_id is not None:
                self._entities[normalized.entity_id].add(key)
            for entity_id in normalized.related_entity_ids:
                self._entities[entity_id].add(key)
            if normalized.object_type is MindObjectType.ENTITY:
                entity_id = normalized.object_id
                names = {normalized.text, *normalized.aliases}
                for name in names:
                    alias = normalize_alias(name)
                    if alias:
                        self._aliases[alias].add(entity_id)
                        self._entity_aliases[entity_id].add(alias)

    def watermark(self) -> int:
        return self._watermark

    def lag(self) -> int:
        if self._store is None:
            return 0
        try:
            return max(0, int(self._store.current_world_revision()) - self._watermark)
        except (AttributeError, TypeError, ValueError):
            return 0

    def drop_projection(self) -> None:
        """Drop only the rebuildable in-memory projection, never world truth."""

        with self._lock:
            self._documents.clear()
            self._tokens_by_key.clear()
            self._postings.clear()
            self._dimensions.clear()
            self._entities.clear()
            self._object_links.clear()
            self._annotations_by_target.clear()
            self._aliases.clear()
            self._entity_aliases.clear()
            self._types.clear()
            self._watermark = 0

    def rebuild(self) -> int:
        self.drop_projection()
        return self.catch_up()

    def catch_up(self) -> int:
        """Project supported durable objects and either annotation schema."""

        if self._store is None:
            return 0
        current_revision = self._current_world_revision()
        if self._watermark >= current_revision:
            return 0
        added_before = len(self._documents)
        type_map = {
            "dimension_definition": MindObjectType.DIMENSION,
            "claim": MindObjectType.CLAIM,
            "entity": MindObjectType.ENTITY,
            "observation": MindObjectType.OBSERVATION,
            "event": MindObjectType.EVENT,
            "relation": MindObjectType.RELATION,
        }
        for durable_type, mind_type in type_map.items():
            try:
                payloads = self._store.list_payloads(object_type=durable_type)
            except (AttributeError, TypeError, ValueError):
                try:
                    from aios_core.contracts.enums import ObjectType

                    payloads = self._store.list_payloads(
                        object_type=ObjectType(durable_type)
                    )
                except (AttributeError, TypeError, ValueError):
                    continue
            for payload in payloads:
                document = self._payload_document(payload, mind_type)
                if document is not None:
                    self.add_document(document)
        self._catch_up_annotations()
        try:
            self._watermark = int(self._store.current_world_revision())
        except (AttributeError, TypeError, ValueError):
            pass
        return len(self._documents) - added_before

    def search_mind(
        self,
        keywords: Sequence[str] = (),
        *,
        dimension: str | None = None,
        claim_id: str | None = None,
        entity_id: str | None = None,
        annotation_id: str | None = None,
        object_types: Sequence[MindObjectType | str] | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        include_annotations: bool = True,
        limit: int = 20,
        pathway: SearchPathway = SearchPathway.HIERARCHICAL_TOPO,
    ) -> MindSearchPage:
        if claim_id is not None and annotation_id is not None:
            raise ValueError("claim_id and annotation_id cannot be combined")
        query = MindSearchQuery(
            keywords=tuple(keywords),
            dimension=dimension,
            entity_id=entity_id,
            linked_object_id=annotation_id or claim_id,
            object_types=tuple(MindObjectType(item) for item in (object_types or ())),
            time_start=time_range[0] if time_range is not None else None,
            time_end=time_range[1] if time_range is not None else None,
            include_annotations=include_annotations,
            limit=limit,
        )
        return self.execute_pathway(pathway, query).page

    def execute_pathway(
        self,
        pathway: SearchPathway,
        query: MindSearchQuery,
    ) -> PathwaySearchResult:
        normalized_pathway = SearchPathway(pathway)
        normalized_query = MindSearchQuery.model_validate(query)
        if self._store is not None and self.lag() > 0:
            self.catch_up()
        with self._lock:
            if normalized_pathway is SearchPathway.BRUTE_FORCE_SCAN:
                candidate_keys = set(self._documents)
                inspected_keys = set(self._documents)
                matched = self._filter_exact(candidate_keys, normalized_query)
            elif normalized_pathway is SearchPathway.KEYWORD_SEARCH:
                candidate_keys = self._naive_keyword_candidates(normalized_query)
                inspected_keys = set(candidate_keys)
                matched = self._filter_structured(candidate_keys, normalized_query)
            else:
                candidate_keys = self._topological_candidates(normalized_query)
                inspected_keys = set(candidate_keys)
                matched = self._filter_exact(candidate_keys, normalized_query)

            if normalized_query.include_annotations and matched:
                target_ids = {self._documents[key].object_id for key in matched}
                for target_id in target_ids:
                    matched.update(self._annotations_by_target.get(target_id, ()))

            ranked = sorted(
                (self._documents[key] for key in matched),
                key=lambda document: self._rank_key(document, normalized_query),
            )[: normalized_query.limit]
            page = self._bounded_page(
                ranked,
                normalized_query,
                normalized_pathway,
            )
            if normalized_pathway is SearchPathway.HIERARCHICAL_TOPO:
                context_cost = page.total_estimated_tokens
            else:
                context_cost = sum(
                    ConservativeTokenMeter.estimate_context_tokens(
                        self._documents[key].text
                    )
                    for key in inspected_keys
                )
            return PathwaySearchResult(
                page=page,
                inspected_document_count=len(inspected_keys),
                context_token_cost=context_cost,
            )

    def search_by_dimension(
        self,
        dimension: str,
        keywords: Sequence[str] = (),
        limit: int = 20,
    ) -> MindSearchPage:
        return self.search_mind(keywords, dimension=dimension, limit=limit)

    def search_by_claim(
        self,
        claim_id: str,
        keywords: Sequence[str] = (),
        limit: int = 20,
    ) -> MindSearchPage:
        return self.search_mind(keywords, claim_id=claim_id, limit=limit)

    def search_by_entity(
        self,
        entity_id: str,
        keywords: Sequence[str] = (),
        limit: int = 20,
    ) -> MindSearchPage:
        return self.search_mind(keywords, entity_id=entity_id, limit=limit)

    def search_by_annotation(
        self,
        annotation_id: str,
        limit: int = 20,
    ) -> MindSearchPage:
        return self.search_mind(annotation_id=annotation_id, limit=limit)

    def co_search(
        self,
        keywords: Sequence[str],
        *,
        subject: str | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        limit: int = 50,
        strict_freshness: bool = False,
        view: str = "ANNOTATED",
        as_of: datetime | None = None,
        include_tombstones: bool = True,
    ) -> MindSearchPage:
        """Backward-compatible co-occurrence intersection over bounded hits."""

        del view, as_of, include_tombstones
        if not keywords or any(not keyword.strip() for keyword in keywords):
            raise ValueError("co_search requires non-blank keywords")
        if strict_freshness and self.lag() > 0:
            return MindSearchPage(
                status="stale_index",
                lag=self.lag(),
                world_revision=self._current_world_revision(),
                index_watermark=self._watermark,
            )
        if self._store is not None and self.lag() > 0:
            self.catch_up()
        query = MindSearchQuery(
            keywords=tuple(keywords),
            entity_id=subject,
            time_start=time_range[0] if time_range is not None else None,
            time_end=time_range[1] if time_range is not None else None,
            include_annotations=False,
            limit=limit,
        )
        with self._lock:
            groups: list[set[tuple[str, int]]] = []
            ambiguous: dict[str, list[str]] = {}
            for keyword in query.keywords:
                keyword_tokens = _tokens(keyword)
                resolved = self._aliases.get(normalize_alias(keyword), set())
                if len(resolved) > 1:
                    ambiguous[keyword] = sorted(resolved)
                expanded_tokens = set(keyword_tokens)
                for entity_id in resolved:
                    for alias in self._entity_aliases.get(entity_id, ()):
                        expanded_tokens.update(_tokens(alias))
                candidates: set[tuple[str, int]] = set()
                for token in expanded_tokens:
                    candidates.update(self._postings.get(token, ()))
                for entity_id in resolved:
                    candidates.update(self._entities.get(entity_id, ()))
                candidates = {
                    key
                    for key in candidates
                    if self._keyword_matches_document(keyword, resolved, key)
                }
                if not candidates:
                    return MindSearchPage(
                        lag=self.lag(),
                        world_revision=self._current_world_revision(),
                        index_watermark=self._watermark,
                        ambiguous_keywords=ambiguous,
                        query_intent=" ".join(query.keywords),
                    )
                groups.append(candidates)
            matched = set.intersection(*groups)
            matched = self._filter_structured(matched, query)
            ranked = sorted(
                (self._documents[key] for key in matched),
                key=lambda document: self._rank_key(document, query),
            )[:limit]
            page = self._bounded_page(
                ranked,
                query,
                SearchPathway.HIERARCHICAL_TOPO,
            )
            return page.model_copy(update={"ambiguous_keywords": ambiguous})

    def _current_world_revision(self) -> int:
        if self._store is None:
            return self._watermark
        try:
            return int(self._store.current_world_revision())
        except (AttributeError, TypeError, ValueError):
            return self._watermark

    def _keyword_matches_document(
        self,
        keyword: str,
        resolved_entity_ids: set[str],
        key: tuple[str, int],
    ) -> bool:
        document = self._documents[key]
        if keyword.casefold() in document.text.casefold():
            return True
        if _tokens(keyword) <= self._tokens_by_key[key]:
            return True
        for entity_id in resolved_entity_ids:
            if any(
                _tokens(alias) <= self._tokens_by_key[key]
                for alias in self._entity_aliases.get(entity_id, ())
            ):
                return True
        linked_entities = {
            document.entity_id,
            *document.related_entity_ids,
        }
        return bool(resolved_entity_ids & linked_entities)

    def _naive_keyword_candidates(self, query: MindSearchQuery) -> set[tuple[str, int]]:
        query_tokens = self._query_tokens(query)
        if not query_tokens:
            return set(self._documents)
        candidates: set[tuple[str, int]] = set()
        for token in query_tokens:
            candidates.update(self._postings.get(token, ()))
        return candidates

    def _topological_candidates(self, query: MindSearchQuery) -> set[tuple[str, int]]:
        candidates = set(self._documents)
        if query.dimension is not None:
            candidates &= self._dimensions.get(query.dimension, set())
        if query.entity_id is not None:
            candidates &= self._entities.get(query.entity_id, set())
        if query.linked_object_id is not None:
            candidates &= self._object_links.get(query.linked_object_id, set())
        if query.object_types:
            allowed: set[tuple[str, int]] = set()
            for object_type in query.object_types:
                allowed.update(self._types.get(object_type, ()))
            candidates &= allowed
        for keyword in query.keywords:
            candidates &= self._candidate_keys_for_keyword(keyword)
        return candidates

    def _filter_exact(
        self,
        keys: set[tuple[str, int]],
        query: MindSearchQuery,
    ) -> set[tuple[str, int]]:
        return {
            key
            for key in self._filter_structured(keys, query)
            if all(
                self._keyword_matches_document(
                    keyword,
                    self._aliases.get(normalize_alias(keyword), set()),
                    key,
                )
                for keyword in query.keywords
            )
        }

    def _candidate_keys_for_keyword(self, keyword: str) -> set[tuple[str, int]]:
        resolved = self._aliases.get(normalize_alias(keyword), set())
        variants = {normalize_alias(keyword)}
        for entity_id in resolved:
            variants.update(self._entity_aliases.get(entity_id, ()))
        candidates: set[tuple[str, int]] = set()
        for variant in variants:
            variant_candidates = set(self._documents)
            for token in _tokens(variant):
                variant_candidates &= self._postings.get(token, set())
            candidates.update(variant_candidates)
        for entity_id in resolved:
            candidates.update(self._entities.get(entity_id, ()))
        return {
            key
            for key in candidates
            if self._keyword_matches_document(keyword, resolved, key)
        }

    def _filter_structured(
        self,
        keys: set[tuple[str, int]],
        query: MindSearchQuery,
    ) -> set[tuple[str, int]]:
        return {
            key for key in keys if self._matches_structured(self._documents[key], query)
        }

    @staticmethod
    def _matches_structured(document: MindDocument, query: MindSearchQuery) -> bool:
        if query.dimension is not None and document.dimension != query.dimension:
            return False
        if query.entity_id is not None and query.entity_id not in {
            document.entity_id,
            *document.related_entity_ids,
        }:
            return False
        if query.linked_object_id is not None and query.linked_object_id not in {
            document.object_id,
            *document.related_object_ids,
        }:
            return False
        if query.object_types and document.object_type not in query.object_types:
            return False
        occurred = as_utc(document.occurred_at)
        if query.time_start is not None and occurred < as_utc(query.time_start):
            return False
        return not (query.time_end is not None and occurred > as_utc(query.time_end))

    def _bounded_page(
        self,
        documents: list[MindDocument],
        query: MindSearchQuery,
        pathway: SearchPathway,
    ) -> MindSearchPage:
        remaining = self.MAX_PAGE_TOKENS
        hits: list[MindSearchHit] = []
        query_tokens = self._query_tokens(query)
        for index, document in enumerate(documents):
            documents_left = len(documents) - index
            budget = min(
                self.MAX_SINGLE_HIT_TOKENS,
                max(1, remaining // max(1, documents_left)),
            )
            excerpt = ConservativeTokenMeter.truncate(document.text, budget)
            physical_count = ConservativeTokenMeter.count(excerpt)
            if physical_count == 0:
                continue
            remaining -= physical_count
            hits.append(
                MindSearchHit(
                    object_id=document.object_id,
                    revision=document.revision,
                    object_type=document.object_type,
                    entity_id=document.entity_id,
                    dimension=document.dimension,
                    excerpt=excerpt,
                    score=(
                        len(
                            query_tokens
                            & self._tokens_by_key[
                                (document.object_id, document.revision)
                            ]
                        )
                        + (
                            10
                            if document.object_type is MindObjectType.ANNOTATION
                            else 0
                        )
                    ),
                    is_annotation=document.object_type is MindObjectType.ANNOTATION,
                    related_entity_ids=tuple(sorted(document.related_entity_ids)),
                    estimated_tokens=physical_count,
                )
            )
        intent_parts = list(query.keywords)
        if query.dimension is not None:
            intent_parts.append(f"dim:{query.dimension}")
        if query.entity_id is not None:
            intent_parts.append(f"entity:{query.entity_id}")
        if query.linked_object_id is not None:
            intent_parts.append(f"object:{query.linked_object_id}")
        return MindSearchPage(
            pathway=pathway,
            hits=tuple(hits),
            total_estimated_tokens=sum(hit.estimated_tokens for hit in hits),
            query_intent=" ".join(intent_parts),
            lag=self.lag(),
            world_revision=self._current_world_revision(),
            index_watermark=self._watermark,
        )

    def _rank_key(
        self,
        document: MindDocument,
        query: MindSearchQuery,
    ) -> tuple[int, int, float, str]:
        token_matches = len(
            self._query_tokens(query)
            & self._tokens_by_key[(document.object_id, document.revision)]
        )
        return (
            -int(document.object_type is MindObjectType.ANNOTATION),
            -token_matches,
            -as_utc(document.occurred_at).timestamp(),
            document.object_id,
        )

    @staticmethod
    def _query_tokens(query: MindSearchQuery) -> frozenset[str]:
        tokens: set[str] = set()
        for keyword in query.keywords:
            tokens.update(_tokens(keyword))
        return frozenset(tokens)

    @staticmethod
    def _payload_document(
        payload: dict[str, Any],
        object_type: MindObjectType,
    ) -> MindDocument | None:
        text_parts: list[str] = []
        for field_name in (
            "name",
            "description",
            "content",
            "canonical_name",
            "aliases",
            "value",
            "title",
            "interpretation",
        ):
            value = payload.get(field_name)
            if isinstance(value, str):
                text_parts.append(value)
            elif isinstance(value, list):
                text_parts.extend(str(item) for item in value if isinstance(item, str))
            elif field_name == "value" and value is not None:
                text_parts.append(
                    json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                )
        if not text_parts:
            return None
        occurred = payload.get("occurred")
        occurred_value = occurred.get("start") if isinstance(occurred, dict) else None
        timestamp_raw = occurred_value or payload.get("learned_at")
        try:
            timestamp = (
                datetime.fromisoformat(timestamp_raw)
                if isinstance(timestamp_raw, str)
                else datetime.now(UTC)
            )
            require_aware(timestamp, "document timestamp")
        except ValueError:
            return None
        subject = payload.get("subject_id")
        entity_id = (
            str(payload.get("object_id"))
            if object_type is MindObjectType.ENTITY
            else str(subject)
            if isinstance(subject, str)
            else None
        )
        related_object_ids = frozenset(_iter_ref_ids(payload))
        related_entity_ids = frozenset(
            object_id
            for object_id in related_object_ids
            if object_id.startswith(("ent_", "entity_"))
        )
        aliases = payload.get("aliases", ())
        return MindDocument(
            object_id=str(payload["object_id"]),
            revision=int(payload.get("revision", 1)),
            object_type=object_type,
            dimension=derive_dimension(payload, object_type.value),
            entity_id=entity_id,
            text="；".join(text_parts),
            occurred_at=timestamp,
            aliases=frozenset(
                alias for alias in aliases if isinstance(alias, str) and alias.strip()
            )
            if isinstance(aliases, list)
            else frozenset(),
            related_entity_ids=related_entity_ids,
            related_object_ids=related_object_ids,
        )

    def _catch_up_annotations(self) -> None:
        if self.db_path is None or not Path(self.db_path).is_file():
            return
        try:
            with sqlite3.connect(self.db_path) as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(retrospective_annotations)"
                    )
                }
                if not columns:
                    return
                if {"annotation_id", "target_entity_id", "semantic_overlay"} <= columns:
                    rows = connection.execute(
                        "SELECT annotation_id, target_entity_id, semantic_overlay, "
                        "target_time_start, learned_at FROM retrospective_annotations"
                    ).fetchall()
                    for annotation_id, entity_id, text, occurred, learned in rows:
                        timestamp = datetime.fromisoformat(occurred or learned)
                        self.add_document(
                            MindDocument(
                                object_id=annotation_id,
                                object_type=MindObjectType.ANNOTATION,
                                dimension=derive_dimension(
                                    {"semantic_overlay": text}, "annotation"
                                ),
                                entity_id=entity_id,
                                text=text,
                                occurred_at=timestamp,
                                related_entity_ids=frozenset({entity_id}),
                            )
                        )
                elif {
                    "annotation_id",
                    "target_object_id",
                    "reinterpretation_claim",
                } <= columns:
                    rows = connection.execute(
                        "SELECT annotation_id, target_object_id, "
                        "reinterpretation_claim, created_at FROM retrospective_annotations"
                    ).fetchall()
                    for annotation_id, target_id, text, created_at in rows:
                        self.add_document(
                            MindDocument(
                                object_id=annotation_id,
                                object_type=MindObjectType.ANNOTATION,
                                dimension=derive_dimension(
                                    {"semantic_overlay": text}, "annotation"
                                ),
                                text=text,
                                occurred_at=datetime.fromisoformat(created_at),
                                related_object_ids=frozenset({target_id}),
                            )
                        )
        except (sqlite3.DatabaseError, OSError, TypeError, ValueError):
            return


# Compatibility exports retained for M1-017 callers.
SearchHit = MindSearchHit
SearchPage = MindSearchPage
WorldSearchIndex = MultidimensionalSearchEngine
