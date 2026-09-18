"""S7: model-owned communication decisions with evidence-linked audit."""

from __future__ import annotations

from aios_core.simulation.blind_bench_harness import BenchRunResult


def test_all_three_model_selected_action_kinds_are_logged(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S7")
    assert stage.fact("actions_logged") == 6
    assert stage.fact("interventions") == 2
    assert stage.fact("silences") == 1
    assert stage.fact("advices") == 3
    assert stage.fact("action_objects_in_store") >= 6


def test_runtime_preserves_model_decisions_without_rule_brain_rewrite(
    bench_run: BenchRunResult,
) -> None:
    stage = bench_run.stage("S7")
    assert stage.fact("program_rewrite_count") == 0
    assert stage.fact("explicit_kind_mismatches") == 0
    assert stage.fact("model_decisions_preserved") is True


def test_communication_history_is_descriptive_not_prescriptive(
    bench_run: BenchRunResult,
) -> None:
    stage = bench_run.stage("S7")
    assert stage.fact("history_samples") >= 4
    assert stage.fact("case_history_samples") >= 2
    assert "recommended_style" not in stage.facts
    assert "avoid_styles" not in stage.facts
    assert "case_predicted_style" not in stage.facts


def test_feedback_is_evidence_linked_and_persisted(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S7")
    assert stage.fact("feedback_evidence_coverage") == 1.0
    assert stage.fact("communication_experiences_in_store") == 7
    assert "explicit_reply" in stage.fact("feedback_sources")


def test_silence_is_explicit_and_auditable(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S7")
    assert stage.fact("silence_has_reason") is True
    assert stage.fact("silence_content_chars") == 0


def test_zero_ui_surface(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S7")
    assert stage.fact("ui_prompts_issued") == 0
