"""阶段六盲测：共生决策推演与主动帮助（证据接地 + 目标撤销）。"""

from __future__ import annotations

from aios_core.simulation.blind_bench_harness import BenchRunResult


def test_advice_is_grounded_in_pinned_evidence(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("advice_kind") == "GroundedAdvice"
    assert stage.fact("advice_evidence_pointers") >= 2
    assert stage.fact("advice_grounding_verified") is True
    assert "observation" in stage.fact("advice_evidence_types")


def test_advice_respects_brevity_and_quality_gate(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("advice_sentence_count") <= 3
    assert stage.fact("advice_chars") <= 120
    conclusion = stage.fact("advice_conclusion")
    for banned in ("保持积极心态", "亲爱的用户", "综上所述", "第一，", "心理疏导"):
        assert banned not in conclusion


def test_advice_text_passes_punctuation_hygiene(bench_run: BenchRunResult) -> None:
    """铁律 1 的可读性硬线：拼接出来的句子必须是干净的人话。"""

    conclusion = bench_run.stage("S6").fact("advice_conclusion")
    assert conclusion
    assert not conclusion.startswith(("；", ";", "，", ",", "。", "！", "？"))
    for smell in ("。。", "！！", "？？", "；；", "，，", "，。", "。，", "；。", "。；"):
        assert smell not in conclusion
    assert conclusion.rstrip() == conclusion
    assert conclusion.endswith(("。", "！", "？"))


def test_engine_withholds_when_evidence_is_absent(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S6")
    assert stage.fact("withheld_kind") == "AdviceWithheld"
    assert stage.fact("withheld_evidence_found") == 0
    assert "证据不足" in stage.fact("withheld_reason")


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
