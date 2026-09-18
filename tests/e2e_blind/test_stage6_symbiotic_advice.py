"""S6 blind bench: evidence infrastructure with model-owned advice."""

from __future__ import annotations

from aios_core.simulation.blind_bench_harness import BenchRunResult


def test_retrieval_returns_pinned_evidence_without_deciding_response(
    bench_run: BenchRunResult,
) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("evidence_packet_kind") == "EvidencePacket"
    assert stage.fact("evidence_packet_hits") >= 1
    assert stage.fact("advice_evidence_pointers") >= 1
    assert stage.fact("advice_grounding_verified") is True
    assert "observation" in stage.fact("advice_evidence_types")


def test_model_owned_advice_is_preserved_without_semantic_gate(
    bench_run: BenchRunResult,
) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("advice_kind") == "ModelAdviceDecision"
    assert stage.fact("advice_decision") == "respond"
    assert stage.fact("model_output_preserved") is True
    assert stage.fact("program_semantic_gate_applied") is False
    assert stage.fact("advice_sentence_count") >= 4
    conclusion = stage.fact("advice_conclusion")
    assert "亲爱的用户" in conclusion
    assert "首先" in conclusion
    assert "保持积极心态" in conclusion
    assert "第五句" in conclusion


def test_empty_retrieval_is_data_not_program_forced_silence(
    bench_run: BenchRunResult,
) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("empty_packet_kind") == "EvidencePacket"
    assert stage.fact("empty_packet_hits") == 0
    assert stage.fact("empty_packet_is_data_not_decision") is True


def test_denied_inferred_goal_is_silently_revoked(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("goal_status_after_retraction") == "abandoned"
    assert stage.fact("task_status_after_retraction") == "cancelled"
    assert stage.fact("retraction_cancelled_tasks") >= 1
    assert stage.fact("retraction_asked_user") is False
    assert stage.fact("abandoned_inferred_goals") == 1


def test_goals_and_tasks_are_decoupled(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("independent_task_status") == "draft"
    assert stage.fact("tasks_without_goals") >= 1
