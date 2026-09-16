"""阶段三盲测：多维时空共振 / 新事件合成 / 生命周期。"""

from __future__ import annotations

import pytest

from aios_core.contracts.enums import EventStatus
from aios_core.services.state_machines import validate_event_transition
from aios_core.simulation.blind_bench_harness import BenchRunResult


def test_cross_dimension_resonance_precedes_synthesis(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S3")
    assert stage.fact("resonant_dimension_count") >= 3
    assert stage.fact("aligned_samples") >= 3
    assert stage.fact("streams_registered") >= 4


def test_event_lifecycle_snapshots_and_revisions(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S3")
    assert stage.fact("synthesized_event_status") == "candidate"
    assert stage.fact("lifecycle_snapshots") == "candidate,active,revised,resolved"
    assert stage.fact("synthesized_event_revision") == 4
    assert stage.fact("revision_chain_validated") is True


def test_illegal_lifecycle_transition_is_refused(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S3")
    assert stage.fact("illegal_transition_rejected") is True
    # 独立复核状态机：终态事件不得回退到候选态
    with pytest.raises(ValueError):
        validate_event_transition(EventStatus.RESOLVED, EventStatus.CANDIDATE)
    with pytest.raises(ValueError):
        validate_event_transition(EventStatus.MERGED, EventStatus.ACTIVE)


def test_downstream_is_marked_stale_not_recomputed(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S3")
    stale = stage.fact("stale_downstream_after_activation")
    assert "summary_week_resonance" in stale
    assert "advice_card_resonance" in stale


def test_multi_keyword_cooccurrence_bus(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S3")
    assert stage.fact("cooccurrence_hits") >= 1
    assert stage.fact("cooccurrence_is_subset") is True
    assert stage.fact("claim_evidence_refs") >= 2
