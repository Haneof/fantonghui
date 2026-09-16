from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from aios_core.simulation.headless_life_driver import (
    HeadlessLifeDriver,
    HighEntropyLifeStream,
    RuntimePolicyError,
    RuntimeTokenPolicy,
    TokenBudgetExceededError,
)

START = datetime(2026, 8, 17, 0, 0, tzinfo=UTC)
MONTHLY_BUDGET = 2_554_000
RSS_LIMIT = 128 * 1024 * 1024


def _write_policy(tmp_path, budget: int = MONTHLY_BUDGET):
    policy = tmp_path / "governance" / "runtime_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        json.dumps(
            {
                "policy_version": "3.0",
                "token_budget": {"monthly_total_tokens": budget},
            }
        ),
        encoding="utf-8",
    )
    return policy


def test_high_entropy_stream_covers_720_hours_and_120_adult_work_meetings() -> None:
    stream = HighEntropyLifeStream(start_at=START, days=30)
    hours = 0
    meetings = 0
    crises = 0
    breaches = 0
    deep_sleep_hours = 0
    industrial_hours = 0
    physiological_samples = 0
    first_at = None
    last_at = None

    for event in stream:
        first_at = event.occurred_at if first_at is None else first_at
        last_at = event.occurred_at
        assert event.hour_index == hours
        assert len(event.heart_rate_samples) == 300
        assert len(event.hrv_samples_ms) == 300
        hours += 1
        meetings += int(event.meeting_title is not None)
        crises += int(event.commercial_crisis is not None)
        breaches += int(event.lao_wang_contract_breach)
        deep_sleep_hours += int(event.circadian_state == "DEEP_SLEEP")
        industrial_hours += int(event.industrial_noise_db >= 85)
        physiological_samples += len(event.heart_rate_samples)

    assert hours == 720
    assert first_at == START
    assert last_at is not None
    assert last_at + timedelta(hours=1) == START + timedelta(days=30)
    assert meetings == 120
    assert crises == 4
    assert breaches == 1
    assert deep_sleep_hours == 30 * 6
    assert industrial_hours == 30 * 11
    assert physiological_samples == 720 * 300


def test_30day_headless_driver_runs_full_chain_with_zero_raw_images(tmp_path) -> None:
    policy_path = _write_policy(tmp_path)
    work_dir = tmp_path / "sim-runtime"
    driver = HeadlessLifeDriver(
        work_dir=work_dir,
        runtime_policy_path=policy_path,
        start_at=START,
        days=30,
    )
    try:
        report = driver.run()
    finally:
        driver.close()

    assert report.days == 30
    assert report.generated_hours == 720
    assert report.physiological_sample_count == 216_000
    assert report.meeting_count == 120
    assert report.commercial_crisis_count == 4
    assert report.lao_wang_breach_count == 1

    assert report.c01_image_frames_processed == 720
    assert report.c01_semantic_observations > 0
    assert report.c01_semantic_observations < 720
    assert report.c01_raw_bytes_retained == 0
    assert driver.raw_sink.retained_byte_count == 0

    assert report.c06_indexed_entities == 720
    assert report.c06_breach_query_hits >= 1
    assert report.c02_persisted_observations == 720
    assert report.c02_world_revision == 30
    with sqlite3.connect(work_dir / "world.db") as connection:
        persisted = connection.execute(
            "SELECT COUNT(*) FROM object_revisions WHERE object_type = ?",
            ("observation",),
        ).fetchone()[0]
    assert persisted == 720

    assert report.c04_cockpit_assemblies >= 120
    assert report.c05_retrospective_annotations == 1
    assert report.c05_historical_overlay_count == 0
    assert report.c05_current_overlay_count == 1
    assert report.completed_chain == (
        "C01_EDGE_CLEAN",
        "C06_INVERTED_INTERSECTION",
        "C02_LEDGER_PERSIST",
        "C04_SINGLE_COCKPIT",
        "C05_RETROSPECTIVE_ANNOTATION",
    )


def test_30day_run_has_zero_deadlocks_stable_rss_and_1000x_replay(tmp_path) -> None:
    driver = HeadlessLifeDriver(
        work_dir=tmp_path / "bounded-runtime",
        runtime_policy_path=_write_policy(tmp_path),
        start_at=START,
        days=30,
    )
    try:
        report = driver.run()
    finally:
        driver.close()

    assert report.deadlock_count == 0
    assert len(report.daily_rss_bytes) == 31
    assert report.peak_rss_bytes <= RSS_LIMIT
    assert max(report.daily_rss_bytes) <= RSS_LIMIT
    assert report.final_rss_bytes - report.initial_rss_bytes <= 32 * 1024 * 1024
    assert max(report.daily_rss_bytes) - min(report.daily_rss_bytes) <= 32 * 1024 * 1024
    assert report.acceleration_factor >= 1_000


def test_monthly_token_envelope_is_loaded_and_never_exceeded(tmp_path) -> None:
    policy_path = _write_policy(tmp_path)
    policy = RuntimeTokenPolicy.load(policy_path)
    assert policy.monthly_token_budget == MONTHLY_BUDGET
    assert policy.source_path.endswith("governance/runtime_policy.json")

    driver = HeadlessLifeDriver(
        work_dir=tmp_path / "token-runtime",
        runtime_policy_path=policy_path,
        start_at=START,
        days=30,
    )
    try:
        report = driver.run()
    finally:
        driver.close()

    assert 0 < report.consumed_tokens <= MONTHLY_BUDGET
    assert report.monthly_token_budget == MONTHLY_BUDGET
    assert report.token_budget_remaining == MONTHLY_BUDGET - report.consumed_tokens


def test_tiny_policy_fails_closed_before_cockpit_can_overspend(tmp_path) -> None:
    driver = HeadlessLifeDriver(
        work_dir=tmp_path / "tiny-budget-runtime",
        runtime_policy_path=_write_policy(tmp_path, budget=100),
        start_at=START,
        days=30,
    )
    try:
        with pytest.raises(TokenBudgetExceededError, match="would exceed 100"):
            driver.run()
    finally:
        driver.close()


def test_policy_cannot_relax_constitutional_monthly_ceiling(tmp_path) -> None:
    relaxed = _write_policy(tmp_path, budget=MONTHLY_BUDGET + 1)
    with pytest.raises(RuntimePolicyError, match="cannot relax"):
        RuntimeTokenPolicy.load(relaxed)
