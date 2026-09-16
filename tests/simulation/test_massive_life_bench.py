"""Official-scale end-to-end acceptance for the eight-stage life benchmark."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aios_core.contracts.enums import EventStatus
from aios_core.simulation.massive_life_bench_receipt import (
    BENCHMARK_VERSION,
    OFFICIAL_MINIMUM_RECORDS,
    AppendOnlyEventLifecycle,
    BenchmarkConfig,
    CommunicationPolicyGuard,
    DialogueMode,
    DialogueStance,
    MassiveLifeBenchmarkReport,
    MassiveSyntheticLifeGenerator,
)


@pytest.fixture(scope="module")
def official_report(
    tmp_path_factory: pytest.TempPathFactory,
) -> MassiveLifeBenchmarkReport:
    """Run scale isolation in a child so its peak RSS cannot poison later tests."""

    output_dir = tmp_path_factory.mktemp("million-life-bench")
    repository_root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(repository_root / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "aios_core.simulation.massive_life_bench_receipt",
            "--samples",
            str(OFFICIAL_MINIMUM_RECORDS),
            "--output-dir",
            str(output_dir),
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    evidence_path = output_dir / "aios_full_pipeline_bench_2026-09-16.json"
    return MassiveLifeBenchmarkReport.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )


def test_generator_freezes_oracles_before_stream_and_is_high_entropy():
    config = BenchmarkConfig(sample_count=10_000, persist_artifacts=False)
    generator = MassiveSyntheticLifeGenerator(config)
    frozen_oracles = generator.oracles
    samples = list(generator)
    receipt = generator.receipt()

    assert len(samples) == config.sample_count
    assert generator.oracles == frozen_oracles
    assert len(frozen_oracles) >= 5
    assert all(item.required_modalities for item in frozen_oracles)
    assert all(item.query_terms for item in frozen_oracles)
    assert set(receipt.subject_counts) == {
        "programmer",
        "entrepreneur",
        "full_time_parent",
    }
    assert len(receipt.modality_counts) == 7
    assert receipt.normalized_entropy > 0.99


def test_official_million_record_pipeline_passes_every_measured_gate(
    official_report: MassiveLifeBenchmarkReport,
):
    report = official_report
    assert report.benchmark_version == BENCHMARK_VERSION
    assert report.generated_sample_count == 1_000_000
    assert report.official_scale_reached is True
    assert report.verdict == "PASS"
    assert report.all_gates_passed
    assert len(report.stages) == 8
    assert all(stage.wall_time_ms > 0 for stage in report.stages)
    assert all(stage.peak_rss_bytes >= stage.rss_after_bytes for stage in report.stages)
    assert all(gate.passed for gate in report.gates)
    assert {gate.iron_law for gate in report.gates if gate.iron_law} == {1, 2, 3, 4, 5}


def test_official_receipts_prove_key_red_lines_instead_of_declaring_them(
    official_report: MassiveLifeBenchmarkReport,
):
    gates = {gate.gate_id: gate for gate in official_report.gates}
    edge = gates["S1-EDGE-COMPACTION"].measured
    assert edge["raw_payloads_retained"] == 0
    assert edge["write_ratio"] < 0.02
    assert edge["key_evidence_retention"] == 1.0

    history = gates["S5-HISTORY-IMMUTABLE"].measured
    assert history["hash_before"] == history["hash_after"]
    assert history["update_blocked"] and history["delete_blocked"]

    bypass = gates["S8-P0-HARD-BYPASS"].measured
    assert bypass["p0_p99_ms"] <= 50.0
    assert bypass["p0_llm_calls"] == 0
    assert bypass["p0_cockpit_accesses"] == 0

    dimension = gates["S4-DIMENSION-TRIPLE-GATE"].measured
    assert dimension["sporadic_blocked"]
    assert dimension["premature_activation_blocked"]
    assert dimension["quota_blocked"]
    assert dimension["low_accuracy_state"] == "EXPIRED"


def test_all_four_requested_artifacts_are_truthful_and_persisted(
    official_report: MassiveLifeBenchmarkReport,
):
    paths = {name: Path(path) for name, path in official_report.artifacts.items()}
    assert set(paths) == {
        "evidence_json",
        "stress_report",
        "diagnosis",
        "tool_proposals",
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths.values())

    payload = json.loads(paths["evidence_json"].read_text(encoding="utf-8"))
    assert payload["generated_sample_count"] == 1_000_000
    assert payload["verdict"] == "PASS"
    assert len(payload["stages"]) == 8
    assert all(item["wall_time_ms"] > 0 for item in payload["stages"])

    stress = paths["stress_report"].read_text(encoding="utf-8")
    diagnosis = paths["diagnosis"].read_text(encoding="utf-8")
    proposals = paths["tool_proposals"].read_text(encoding="utf-8")
    assert "1,000,000" in stress
    assert "P50" in stress and "P95" in stress and "P99" in stress
    assert "为什么仍不完美" in diagnosis
    assert "ToolProposal" in proposals
    assert len(official_report.tool_proposals) == 2


def test_event_lifecycle_uses_resolvable_evidence_sets_and_rejects_overwrite():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    lifecycle = AppendOnlyEventLifecycle()
    lifecycle.create_candidate(
        object_id="event-red-team",
        subject_id="virtual-user",
        learned_at=now,
        event_time=now - timedelta(minutes=5),
        evidence_refs=("obs-gps", "obs-heart", "obs-quote"),
        confidence=0.84,
    )
    active = lifecycle.transition(
        "event-red-team",
        EventStatus.ACTIVE,
        learned_at=now + timedelta(seconds=1),
    )
    assert active.revision == 2
    assert lifecycle.evidence_references_resolve()
    assert len(lifecycle.evidence_sets) == 1
    assert {ref.object_id for ref in lifecycle.evidence_sets[0].member_refs} == {
        "obs-gps",
        "obs-heart",
        "obs-quote",
    }
    with pytest.raises(ValueError, match="already exists"):
        lifecycle.create_candidate(
            object_id="event-red-team",
            subject_id="virtual-user",
            learned_at=now,
            event_time=now,
            evidence_refs=("rewritten-observation",),
            confidence=0.99,
        )
    with pytest.raises(ValueError, match="illegal event transition"):
        lifecycle.transition(
            "event-red-team",
            EventStatus.CANDIDATE,
            learned_at=now + timedelta(seconds=2),
        )


def test_structured_persona_guard_cannot_be_bypassed_by_bad_free_text():
    guard = CommunicationPolicyGuard()
    with pytest.raises(ValueError, match="sycophantic"):
        guard.validate(
            stance=DialogueStance.UNCONDITIONAL_AGREEMENT,
            mode=DialogueMode.NATURAL,
            proposition_supported=False,
            user_is_venting=False,
        )
    with pytest.raises(ValueError, match="teacher-like"):
        guard.validate(
            stance=DialogueStance.EMPATHIC_LISTENING,
            mode=DialogueMode.LEGAL_LECTURE,
            proposition_supported=None,
            user_is_venting=True,
        )
    with pytest.raises(ValueError, match="questionnaire"):
        guard.validate(
            stance=DialogueStance.EVIDENCE_CORRECTION,
            mode=DialogueMode.QUESTIONNAIRE,
            proposition_supported=True,
            user_is_venting=False,
        )
