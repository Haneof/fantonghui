"""M5 retrieval pathway comparison and durable golden experience distillation."""

from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.contracts.time import require_aware
from aios_core.query.search import (
    MindSearchQuery,
    MultidimensionalSearchEngine,
    SearchPathway,
)


class PathwayType(StrEnum):
    BRUTE_FORCE_SCAN = "brute_force_scan"
    KEYWORD_SEARCH = "keyword_search"
    HIERARCHICAL_TOPO = "hierarchical_topo"

    @property
    def search_pathway(self) -> SearchPathway:
        return SearchPathway(self.value)


class QueryExecutionReceipt(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    receipt_id: str = Field(
        default_factory=lambda: f"search_receipt_{uuid4().hex}",
        min_length=1,
        max_length=160,
    )
    query_intent: str = Field(min_length=1, max_length=1_000)
    pathway_type: PathwayType
    token_cost: int = Field(ge=0)
    output_token_count: int = Field(default=0, ge=0, le=500)
    latency_ms: float = Field(ge=0.0)
    recall_accuracy: float = Field(ge=0.0, le=1.0)
    # Legacy callers supplied only recall.  They remain accepted, but measured
    # executors always set this flag from exact answer-set equality.
    exact_result_match: bool = True
    facts_retrieved_count: int = Field(ge=0)
    hit_object_ids: tuple[str, ...] = ()
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str = Field(default="", max_length=4_096)

    @field_validator("executed_at")
    @classmethod
    def executed_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "executed_at")
        return value

    @model_validator(mode="after")
    def result_count_must_match_ids(self) -> QueryExecutionReceipt:
        if self.hit_object_ids and self.facts_retrieved_count != len(
            self.hit_object_ids
        ):
            raise ValueError("facts_retrieved_count must equal supplied hit_object_ids")
        if len(set(self.hit_object_ids)) != len(self.hit_object_ids):
            raise ValueError("hit_object_ids must be unique")
        return self


class PathwayComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_intent: str
    expected_object_ids: frozenset[str]
    receipts: tuple[QueryExecutionReceipt, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def all_three_paths_must_be_present(self) -> PathwayComparison:
        if {receipt.pathway_type for receipt in self.receipts} != set(PathwayType):
            raise ValueError("comparison must contain exactly the three pathways")
        return self


class OptimalRetrievalStrategy(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    query_intent: str = Field(min_length=1, max_length=1_000)
    preferred_pathway: PathwayType
    expected_tokens: int = Field(ge=0, le=500)
    expected_latency_ms: float = Field(ge=0.0)
    expected_accuracy: float = Field(ge=0.0, le=1.0)
    pathway_steps: tuple[str, ...] = Field(min_length=1, max_length=8)
    sample_size: int = Field(ge=0)
    distilled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("distilled_at")
    @classmethod
    def distilled_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "distilled_at")
        return value

    @model_validator(mode="after")
    def golden_strategy_must_be_exact(self) -> OptimalRetrievalStrategy:
        if self.expected_accuracy != 1.0:
            raise ValueError("golden retrieval experience requires 100% accuracy")
        return self


class NoGoldenPathwayError(RuntimeError):
    """No measured pathway satisfies both exactness and the 500-token cap."""


class PathwayComparisonExecutor:
    """Execute all three pathways against one immutable expected answer set."""

    def __init__(self, engine: MultidimensionalSearchEngine) -> None:
        self.engine = engine

    def compare(
        self,
        *,
        query_intent: str,
        query: MindSearchQuery,
        expected_object_ids: Iterable[str],
    ) -> PathwayComparison:
        expected = frozenset(expected_object_ids)
        if not expected:
            raise ValueError("expected_object_ids must not be empty")
        receipts: list[QueryExecutionReceipt] = []
        for pathway_type in PathwayType:
            started = time.perf_counter_ns()
            execution = self.engine.execute_pathway(
                pathway_type.search_pathway,
                query,
            )
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            hit_ids = tuple(hit.object_id for hit in execution.page.hits)
            hit_set = frozenset(hit_ids)
            recall = len(hit_set & expected) / len(expected)
            receipts.append(
                QueryExecutionReceipt(
                    query_intent=query_intent,
                    pathway_type=pathway_type,
                    token_cost=execution.context_token_cost,
                    output_token_count=execution.page.total_estimated_tokens,
                    latency_ms=latency_ms,
                    recall_accuracy=recall,
                    exact_result_match=hit_set == expected,
                    facts_retrieved_count=len(hit_ids),
                    hit_object_ids=hit_ids,
                    notes=(
                        f"inspected={execution.inspected_document_count};"
                        f"physical_output={execution.page.total_estimated_tokens}"
                    ),
                )
            )
        return PathwayComparison(
            query_intent=query_intent,
            expected_object_ids=expected,
            receipts=tuple(receipts),
        )


class OperationExperienceDistiller:
    """Append receipts and persist the cheapest measured exact strategy."""

    PRIOR_STEPS: ClassVar[tuple[str, ...]] = (
        "按维度和实体收窄候选集",
        "沿实体与事件拓扑定位锚点",
        "对关键词 posting 做交集",
        "只物化命中微切片与证据指针",
    )

    def __init__(self, store_or_path: Any) -> None:
        db_path = getattr(store_or_path, "db_path", store_or_path)
        if not isinstance(db_path, (str, Path)):
            raise TypeError("experience store must expose a SQLite db_path")
        self.db_path = str(db_path)
        self._lock = RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS operation_experience_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    intent_key TEXT NOT NULL,
                    pathway_type TEXT NOT NULL,
                    token_cost INTEGER NOT NULL,
                    output_token_count INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    recall_accuracy REAL NOT NULL,
                    exact_result_match INTEGER NOT NULL,
                    facts_retrieved_count INTEGER NOT NULL,
                    hit_object_ids_json TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    notes TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_experience_receipt_intent
                    ON operation_experience_receipts(intent_key, pathway_type);

                CREATE TABLE IF NOT EXISTS operation_experiences (
                    intent_key TEXT PRIMARY KEY,
                    experience_type TEXT NOT NULL DEFAULT 'retrieval_strategy',
                    preferred_pathway TEXT NOT NULL,
                    expected_tokens INTEGER NOT NULL,
                    expected_latency_ms REAL NOT NULL,
                    expected_accuracy REAL NOT NULL,
                    pathway_steps_json TEXT NOT NULL,
                    sample_size INTEGER NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                """
            )
            # Forward-migrate the original M5 table in place.  SQLite's
            # ``CREATE IF NOT EXISTS`` does not add later columns.
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(operation_experiences)"
                )
            }
            if "experience_type" not in columns:
                connection.execute(
                    "ALTER TABLE operation_experiences ADD COLUMN "
                    "experience_type TEXT NOT NULL DEFAULT 'retrieval_strategy'"
                )
            if "payload_json" not in columns:
                connection.execute(
                    "ALTER TABLE operation_experiences ADD COLUMN "
                    "payload_json TEXT NOT NULL DEFAULT '{}'"
                )

    @staticmethod
    def normalize_intent(query_intent: str) -> str:
        if not isinstance(query_intent, str) or not query_intent.strip():
            raise ValueError("query_intent must not be blank")
        return " ".join(query_intent.casefold().split())

    def record_receipt(self, receipt: QueryExecutionReceipt) -> None:
        normalized = QueryExecutionReceipt.model_validate(receipt)
        intent_key = self.normalize_intent(normalized.query_intent)
        values = (
            normalized.receipt_id,
            intent_key,
            normalized.pathway_type.value,
            normalized.token_cost,
            normalized.output_token_count,
            normalized.latency_ms,
            normalized.recall_accuracy,
            int(normalized.exact_result_match),
            normalized.facts_retrieved_count,
            json.dumps(normalized.hit_object_ids, ensure_ascii=False),
            normalized.executed_at.isoformat(),
            normalized.notes,
        )
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO operation_experience_receipts(
                        receipt_id, intent_key, pathway_type, token_cost,
                        output_token_count, latency_ms, recall_accuracy,
                        exact_result_match, facts_retrieved_count,
                        hit_object_ids_json, executed_at, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            except sqlite3.IntegrityError as exc:
                row = connection.execute(
                    "SELECT * FROM operation_experience_receipts WHERE receipt_id = ?",
                    (normalized.receipt_id,),
                ).fetchone()
                if row is None or self._receipt_row_values(row) != values:
                    raise ValueError(
                        f"receipt_id has conflicting immutable content: "
                        f"{normalized.receipt_id}"
                    ) from exc

    def record_comparison(self, comparison: PathwayComparison) -> None:
        normalized = PathwayComparison.model_validate(comparison)
        for receipt in normalized.receipts:
            self.record_receipt(receipt)

    def distill_for_intent(self, query_intent: str) -> OptimalRetrievalStrategy:
        intent_key = self.normalize_intent(query_intent)
        receipts = self._load_receipts(intent_key)
        if not receipts:
            raise NoGoldenPathwayError(
                "no measured pathway receipts exist; refusing to fabricate "
                "token, latency, or accuracy claims"
            )

        grouped: dict[PathwayType, list[QueryExecutionReceipt]] = defaultdict(list)
        for receipt in receipts:
            grouped[receipt.pathway_type].append(receipt)

        qualified: list[tuple[int, float, str, PathwayType, int]] = []
        for pathway, samples in grouped.items():
            all_exact = all(
                sample.exact_result_match and sample.recall_accuracy == 1.0
                for sample in samples
            )
            average_tokens = round(
                sum(sample.token_cost for sample in samples) / len(samples)
            )
            if not all_exact or average_tokens > 500:
                continue
            average_latency = sum(sample.latency_ms for sample in samples) / len(
                samples
            )
            qualified.append(
                (
                    average_tokens,
                    average_latency,
                    pathway.value,
                    pathway,
                    len(samples),
                )
            )
        if not qualified:
            raise NoGoldenPathwayError(
                "no measured pathway has 100% exact recall within 500 tokens"
            )
        tokens, latency, _name, pathway, _path_samples = min(qualified)
        steps = (
            self.PRIOR_STEPS
            if pathway is PathwayType.HIERARCHICAL_TOPO
            else ("执行已验证的精确关键词求交",)
        )
        strategy = OptimalRetrievalStrategy(
            query_intent=query_intent,
            preferred_pathway=pathway,
            expected_tokens=tokens,
            expected_latency_ms=latency,
            expected_accuracy=1.0,
            pathway_steps=steps,
            sample_size=len(receipts),
        )
        self._save_strategy(intent_key, strategy)
        return strategy

    def get_strategy(self, query_intent: str) -> OptimalRetrievalStrategy:
        intent_key = self.normalize_intent(query_intent)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM operation_experiences WHERE intent_key = ? "
                "AND experience_type = 'retrieval_strategy'",
                (intent_key,),
            ).fetchone()
        if row is None:
            return self.distill_for_intent(query_intent)
        return self._strategy_from_row(row, query_intent)

    def save_experience_payload(
        self,
        *,
        experience_key: str,
        experience_type: str,
        payload: Mapping[str, Any],
        expected_tokens: int,
        expected_accuracy: float,
    ) -> None:
        key = self.normalize_intent(experience_key)
        if not experience_type.strip():
            raise ValueError("experience_type must not be blank")
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operation_experiences(
                    intent_key, experience_type, preferred_pathway,
                    expected_tokens, expected_latency_ms, expected_accuracy,
                    pathway_steps_json, sample_size, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, '[]', 1, ?, ?)
                ON CONFLICT(intent_key) DO UPDATE SET
                    experience_type=excluded.experience_type,
                    preferred_pathway=excluded.preferred_pathway,
                    expected_tokens=excluded.expected_tokens,
                    expected_accuracy=excluded.expected_accuracy,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    key,
                    experience_type,
                    PathwayType.HIERARCHICAL_TOPO.value,
                    expected_tokens,
                    expected_accuracy,
                    serialized,
                    now,
                ),
            )

    def load_experience_payload(self, experience_key: str) -> dict[str, Any]:
        key = self.normalize_intent(experience_key)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM operation_experiences WHERE intent_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise KeyError(experience_key)
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            raise TypeError("persisted experience payload is not an object")
        return payload

    def _load_receipts(self, intent_key: str) -> list[QueryExecutionReceipt]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM operation_experience_receipts "
                "WHERE intent_key = ? ORDER BY executed_at, receipt_id",
                (intent_key,),
            ).fetchall()
        return [
            QueryExecutionReceipt(
                receipt_id=row["receipt_id"],
                query_intent=intent_key,
                pathway_type=PathwayType(row["pathway_type"]),
                token_cost=row["token_cost"],
                output_token_count=row["output_token_count"],
                latency_ms=row["latency_ms"],
                recall_accuracy=row["recall_accuracy"],
                exact_result_match=bool(row["exact_result_match"]),
                facts_retrieved_count=row["facts_retrieved_count"],
                hit_object_ids=tuple(json.loads(row["hit_object_ids_json"])),
                executed_at=datetime.fromisoformat(row["executed_at"]),
                notes=row["notes"],
            )
            for row in rows
        ]

    def _save_strategy(
        self,
        intent_key: str,
        strategy: OptimalRetrievalStrategy,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operation_experiences(
                    intent_key, experience_type, preferred_pathway,
                    expected_tokens, expected_latency_ms, expected_accuracy,
                    pathway_steps_json, sample_size, payload_json, updated_at
                ) VALUES (?, 'retrieval_strategy', ?, ?, ?, ?, ?, ?, '{}', ?)
                ON CONFLICT(intent_key) DO UPDATE SET
                    experience_type='retrieval_strategy',
                    preferred_pathway=excluded.preferred_pathway,
                    expected_tokens=excluded.expected_tokens,
                    expected_latency_ms=excluded.expected_latency_ms,
                    expected_accuracy=excluded.expected_accuracy,
                    pathway_steps_json=excluded.pathway_steps_json,
                    sample_size=excluded.sample_size,
                    payload_json='{}',
                    updated_at=excluded.updated_at
                """,
                (
                    intent_key,
                    strategy.preferred_pathway.value,
                    strategy.expected_tokens,
                    strategy.expected_latency_ms,
                    strategy.expected_accuracy,
                    json.dumps(strategy.pathway_steps, ensure_ascii=False),
                    strategy.sample_size,
                    strategy.distilled_at.isoformat(),
                ),
            )

    @staticmethod
    def _strategy_from_row(
        row: sqlite3.Row,
        query_intent: str,
    ) -> OptimalRetrievalStrategy:
        return OptimalRetrievalStrategy(
            query_intent=query_intent,
            preferred_pathway=PathwayType(row["preferred_pathway"]),
            expected_tokens=row["expected_tokens"],
            expected_latency_ms=row["expected_latency_ms"],
            expected_accuracy=row["expected_accuracy"],
            pathway_steps=tuple(json.loads(row["pathway_steps_json"])),
            sample_size=row["sample_size"],
            distilled_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _receipt_row_values(row: sqlite3.Row) -> tuple[Any, ...]:
        return (
            row["receipt_id"],
            row["intent_key"],
            row["pathway_type"],
            row["token_cost"],
            row["output_token_count"],
            row["latency_ms"],
            row["recall_accuracy"],
            row["exact_result_match"],
            row["facts_retrieved_count"],
            row["hit_object_ids_json"],
            row["executed_at"],
            row["notes"],
        )
