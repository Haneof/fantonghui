"""M5 golden retrieval experience acceptance and adversarial tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from aios_core.cognition.operation_experience import (
    NoGoldenPathwayError,
    OperationExperienceDistiller,
    PathwayComparisonExecutor,
    PathwayType,
    QueryExecutionReceipt,
)
from aios_core.query.search import (
    ConservativeTokenMeter,
    MindDocument,
    MindObjectType,
    MindSearchQuery,
    MultidimensionalSearchEngine,
    SearchPathway,
)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
INTENT = "老王借款纠纷因果回溯"


def _large_world() -> MultidimensionalSearchEngine:
    documents: list[MindDocument] = []
    # 150 unrelated records make a true full scan cost 15k--50k tokens.
    for index in range(150):
        documents.append(
            MindDocument(
                object_id=f"noise_{index:03d}",
                object_type=MindObjectType.OBSERVATION,
                dimension="dim_general",
                entity_id=f"ent_noise_{index:03d}",
                text=f"无关环境记录 {index} " + ("x" * 390),
                occurred_at=NOW - timedelta(minutes=index),
            )
        )
    # Keyword OR retrieves these plausible but wrong records.  Topological AND
    # excludes them, which is the exactness difference between pathways B/C.
    for index in range(15):
        documents.append(
            MindDocument(
                object_id=f"wang_only_{index:02d}",
                object_type=MindObjectType.OBSERVATION,
                dimension="dim_finance",
                entity_id="ent_wang",
                text="老王 旧日普通往来 " + ("w" * 390),
                occurred_at=NOW - timedelta(days=20 + index),
            )
        )
        documents.append(
            MindDocument(
                object_id=f"loan_only_{index:02d}",
                object_type=MindObjectType.OBSERVATION,
                dimension="dim_finance",
                entity_id=f"ent_other_{index:02d}",
                text="借款 普通账单记录 " + ("l" * 390),
                occurred_at=NOW - timedelta(days=40 + index),
            )
        )
    for index in range(3):
        documents.append(
            MindDocument(
                object_id=f"evidence_{index}",
                object_type=(
                    MindObjectType.ANNOTATION if index == 0 else MindObjectType.CLAIM
                ),
                dimension="dim_finance",
                entity_id="ent_wang",
                text=(
                    f"老王 借款 证据锚点 {index}：合同、流水和法院结论相互印证。"
                    + ("e" * 100)
                ),
                occurred_at=NOW + timedelta(seconds=index),
            )
        )
    return MultidimensionalSearchEngine(documents=documents)


def _query() -> MindSearchQuery:
    return MindSearchQuery(
        keywords=("老王", "借款"),
        dimension="dim_finance",
        entity_id="ent_wang",
        limit=4,
    )


def test_three_measured_pathways_distill_and_persist_exact_golden_path(tmp_path):
    engine = _large_world()
    executor = PathwayComparisonExecutor(engine)
    expected = {"evidence_0", "evidence_1", "evidence_2"}
    comparisons = [
        executor.compare(
            query_intent=INTENT,
            query=_query(),
            expected_object_ids=expected,
        )
        for _ in range(3)
    ]

    first = {receipt.pathway_type: receipt for receipt in comparisons[0].receipts}
    brute = first[PathwayType.BRUTE_FORCE_SCAN]
    keyword = first[PathwayType.KEYWORD_SEARCH]
    topo = first[PathwayType.HIERARCHICAL_TOPO]

    assert 15_000 <= brute.token_cost <= 50_000
    assert brute.exact_result_match is True
    assert keyword.recall_accuracy == 1.0
    assert keyword.exact_result_match is False  # 100% recall alone is insufficient.
    assert topo.exact_result_match is True
    assert set(topo.hit_object_ids) == expected
    assert topo.token_cost <= 500
    assert topo.token_cost * 30 < brute.token_cost
    assert all(
        hit.estimated_tokens <= 150 and ConservativeTokenMeter.count(hit.excerpt) <= 150
        for hit in engine.execute_pathway(
            SearchPathway.HIERARCHICAL_TOPO,
            _query(),
        ).page.hits
    )

    database = tmp_path / "experience.db"
    distiller = OperationExperienceDistiller(database)
    for comparison in comparisons:
        distiller.record_comparison(comparison)
    learned = distiller.distill_for_intent(INTENT)

    assert learned.preferred_pathway is PathwayType.HIERARCHICAL_TOPO
    assert learned.expected_accuracy == 1.0
    assert learned.expected_tokens <= 500
    assert learned.sample_size == 9
    assert len(learned.pathway_steps) >= 4

    reloaded = OperationExperienceDistiller(database).get_strategy(INTENT)
    assert reloaded == learned


def test_accuracy_is_a_hard_gate_not_a_weighted_preference(tmp_path):
    distiller = OperationExperienceDistiller(tmp_path / "hard-gate.db")
    samples = (
        QueryExecutionReceipt(
            query_intent="对抗查询",
            pathway_type=PathwayType.BRUTE_FORCE_SCAN,
            token_cost=15_000,
            latency_ms=500,
            recall_accuracy=1.0,
            exact_result_match=True,
            facts_retrieved_count=1,
            hit_object_ids=("fact",),
        ),
        QueryExecutionReceipt(
            query_intent="对抗查询",
            pathway_type=PathwayType.KEYWORD_SEARCH,
            token_cost=1,
            latency_ms=0.01,
            recall_accuracy=0.999,
            exact_result_match=False,
            facts_retrieved_count=1,
            hit_object_ids=("wrong",),
        ),
        QueryExecutionReceipt(
            query_intent="对抗查询",
            pathway_type=PathwayType.HIERARCHICAL_TOPO,
            token_cost=120,
            latency_ms=1,
            recall_accuracy=1.0,
            exact_result_match=False,
            facts_retrieved_count=2,
            hit_object_ids=("fact", "false-positive"),
        ),
    )
    for sample in samples:
        distiller.record_receipt(sample)

    with pytest.raises(NoGoldenPathwayError, match="100% exact recall"):
        distiller.distill_for_intent("对抗查询")


def test_prior_legacy_receipts_and_old_table_are_forward_compatible(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE operation_experiences (
                intent_key TEXT PRIMARY KEY,
                preferred_pathway TEXT NOT NULL,
                expected_tokens INTEGER NOT NULL,
                expected_latency_ms REAL NOT NULL,
                expected_accuracy REAL NOT NULL,
                pathway_steps_json TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    distiller = OperationExperienceDistiller(database)
    prior = distiller.distill_for_intent("从未执行的意图")
    assert prior.preferred_pathway is PathwayType.HIERARCHICAL_TOPO
    assert prior.expected_accuracy == 1.0
    assert prior.expected_tokens <= 500
    assert prior.sample_size == 1

    # The original public constructor did not expose exact IDs/output tokens.
    legacy = QueryExecutionReceipt(
        query_intent="兼容意图",
        pathway_type=PathwayType.HIERARCHICAL_TOPO,
        token_cost=360,
        latency_ms=22.5,
        recall_accuracy=1.0,
        facts_retrieved_count=3,
    )
    distiller.record_receipt(legacy)
    learned = distiller.distill_for_intent("兼容意图")
    assert learned.expected_tokens == 360
    assert learned.expected_accuracy == 1.0


def test_durable_combined_index_and_backward_co_search_contract(tmp_path):
    database = tmp_path / "world.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE retrospective_annotations (
                annotation_id TEXT PRIMARY KEY,
                target_object_id TEXT NOT NULL,
                target_object_type TEXT NOT NULL,
                reinterpretation_claim TEXT NOT NULL,
                is_invalidating INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                dimension TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO retrospective_annotations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "anno_fraud",
                "obs_loan",
                "observation",
                "法院确认老王借款属于合同诈骗",
                1,
                NOW.isoformat(),
                "judge",
                "dim_finance",
            ),
        )

    payloads = {
        "dimension_definition": [
            {
                "object_id": "dim_finance",
                "revision": 1,
                "name": "dim_finance",
                "description": "财务事实",
                "learned_at": NOW.isoformat(),
            }
        ],
        "claim": [
            {
                "object_id": "claim_loan",
                "revision": 1,
                "subject_id": "ent_wang",
                "content": "老王承诺偿还借款",
                "learned_at": NOW.isoformat(),
                "dimension": "dim_finance",
            }
        ],
        "entity": [
            {
                "object_id": "ent_wang",
                "revision": 1,
                "canonical_name": "老王",
                "aliases": ["王建国"],
                "learned_at": NOW.isoformat(),
            }
        ],
        "observation": [
            {
                "object_id": "obs_loan",
                "revision": 1,
                "subject_id": "ent_wang",
                "source_kind": "transaction",
                "value": "老王借款五十万元银行流水",
                "learned_at": NOW.isoformat(),
            }
        ],
    }

    class Store:
        db_path = database

        @staticmethod
        def current_world_revision() -> int:
            return 1

        @staticmethod
        def list_payloads(*, object_type):
            key = object_type.value
            return payloads.get(key, [])

    engine = MultidimensionalSearchEngine(database, store=Store())
    assert engine.rebuild() == 5  # four durable kinds plus one annotation

    page = engine.search_mind(
        ("王建国", "借款"),
        dimension="dim_finance",
        entity_id="ent_wang",
        include_annotations=True,
    )
    assert {hit.object_id for hit in page.hits} >= {
        "obs_loan",
        "anno_fraud",
    }
    assert page.hits[0].is_annotation is True
    assert page.total_estimated_tokens <= 500

    legacy_page = engine.co_search(["王建国", "借款"])
    assert legacy_page.status == "ok"
    assert legacy_page.hits
    assert legacy_page.total_estimated_tokens <= 500


def test_utf8_physical_envelope_never_exceeds_single_or_page_budget():
    engine = MultidimensionalSearchEngine(
        documents=(
            MindDocument(
                object_id=f"cn_{index}",
                object_type=MindObjectType.OBSERVATION,
                dimension="dim_health",
                text="早搏 " + ("非常长的中文观测" * 100),
                occurred_at=NOW + timedelta(seconds=index),
            )
            for index in range(4)
        )
    )
    page = engine.search_mind(
        keywords=("早搏",),
        dimension="dim_health",
        limit=4,
    )
    assert len(page.hits) == 4
    assert page.total_estimated_tokens <= 500
    assert sum(hit.estimated_tokens for hit in page.hits) <= 500
    assert all(hit.estimated_tokens <= 150 for hit in page.hits)
