"""M5 three-year Agent Mind Arena integration and veto acceptance tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios_core.simulation.agent_mind_bench import (
    AgentMindArena,
    AgentMindPlayground,
    ArenaStrategyContext,
    CheckpointKind,
    DissipativeMindStrategy,
    EfficientMindStrategy,
    Persona,
)


@pytest.fixture(scope="module")
def playground() -> AgentMindPlayground:
    return AgentMindPlayground.generate(seed=42)


def test_playground_contains_three_years_near_10k_high_entropy_multi_persona_data(
    playground: AgentMindPlayground,
):
    stats = playground.stats
    assert 9_000 <= stats.event_count <= 10_000
    assert stats.span_days >= 365 * 3
    assert stats.personas == frozenset(
        {
            Persona.PROGRAMMER,
            Persona.ENTREPRENEUR,
            Persona.FULL_TIME_MOTHER,
        }
    )
    assert stats.dimensions == {
        "dim_health",
        "dim_finance",
        "dim_social",
        "dim_work",
    }
    assert stats.unique_text_ratio >= 0.95
    assert len(playground.checkpoints) == 10
    assert {checkpoint.kind for checkpoint in playground.checkpoints} == set(
        CheckpointKind
    )


def test_arena_distinguishes_high_intelligence_from_dissipative_agent_and_persists(
    playground: AgentMindPlayground,
    tmp_path: Path,
):
    database = tmp_path / "arena-experience.db"
    report_dir = tmp_path / "reports"
    arena = AgentMindArena(playground, database, report_dir=report_dir)

    history_hash = playground.history.integrity_hash()
    excellent = arena.run(EfficientMindStrategy())
    poor = arena.run(DissipativeMindStrategy())

    assert excellent.passed is True
    assert excellent.verdict == "优秀：高智商省 Token"
    assert excellent.overall_score >= 95
    assert excellent.metrics.average_decision_tokens <= 500
    assert excellent.metrics.retrieval_recall == 1.0
    assert excellent.metrics.retrieval_exact_match_rate == 1.0
    assert excellent.metrics.dimension_compliance_rate == 1.0
    assert excellent.metrics.humanlike_resonance_score == 1.0
    assert excellent.metrics.iron_rule_violations == ()

    # All four M5 capabilities were actually called, not represented by a stub.
    assert excellent.metrics.search_invocations == 10
    assert excellent.metrics.dimension_invocations == 2
    assert excellent.metrics.posture_invocations == 10
    assert excellent.metrics.advisor_invocations == 3

    assert poor.passed is False
    assert poor.verdict == "一票否决"
    assert poor.overall_score == 0
    assert poor.metrics.disqualified is True
    assert poor.metrics.average_decision_tokens > (
        excellent.metrics.average_decision_tokens * 100
    )
    assert poor.metrics.dimension_compliance_rate == 0.0
    assert poor.metrics.humanlike_resonance_score == 0.0
    assert poor.metrics.p0_llm_calls == 2
    assert poor.metrics.history_tamper_attempts == 1
    assert set(poor.metrics.iron_rule_violations) == {
        "P0_ROUTED_TO_LLM",
        "HISTORY_REWRITE_ATTEMPT",
    }
    assert playground.history.integrity_hash() == history_hash

    for report in (excellent, poor):
        assert report.title == "《AIOS 3.0 共生心智操作全景体检报告》"
        assert report.report_path is not None
        report_path = Path(report.report_path)
        assert report_path.is_file()
        assert report.title in report_path.read_text(encoding="utf-8")
        payload = arena.experience_distiller.load_experience_payload(
            report.experience_key
        )
        assert payload["report_id"] == report.report_id
        assert payload["metrics"]["retrieval_recall"] == 1.0

    with sqlite3.connect(database) as connection:
        stored_types = {
            row[0]
            for row in connection.execute(
                "SELECT experience_type FROM operation_experiences"
            )
        }
    assert stored_types == {"agent_mind_diagnostic"}


def test_direct_history_hash_change_is_detected_recovered_and_vetoed(
    playground: AgentMindPlayground,
    tmp_path: Path,
):
    class DirectTamperStrategy:
        name = "direct-memory-tamper-red-team"

        def __init__(self) -> None:
            self.delegate = EfficientMindStrategy()

        def plan(self, context: ArenaStrategyContext):
            if context.checkpoint.kind is CheckpointKind.HISTORY_INTEGRITY:
                # Deliberately bypass normal frozen-model assignment to emulate
                # hostile in-process code; the ledger hash must still catch it.
                object.__setattr__(
                    context.history.events[0],
                    "text",
                    "forged historical content",
                )
            return self.delegate.plan(context)

    original_hash = playground.history.integrity_hash()
    report = AgentMindArena(
        playground,
        tmp_path / "tamper.db",
    ).run(DirectTamperStrategy())

    assert report.metrics.disqualified is True
    assert report.metrics.iron_rule_violations == ("HISTORY_HASH_CHANGED",)
    assert report.overall_score == 0
    assert report.verdict == "一票否决"
    assert playground.history.integrity_hash() == original_hash
