"""诊断仪与一键运行器单测：探针归因、Token 账单、报告排版、五条铁律判据。"""

from __future__ import annotations

import json
import time

import pytest

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import Observation, TemporalExtent
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import utc_now
import os

from aios_core.simulation.blind_bench_diagnostics import (
    IOAttribution,
    StorageIOProfiler,
    _signature,
    bottleneck_diagnosis,
    iron_rule_assertions,
    render_bottleneck_summary,
    token_ledger,
)
from aios_core.simulation.blind_bench_harness import BenchRunResult, BlindBenchHarness
from aios_core.storage.sqlite_store import SQLiteWorldStore

#: 诊断仪单测的规模：默认 0.2（约 2.5 s），CI 需要更小可用环境变量覆盖。
UNIT_SCALE = float(os.environ.get("AIOS_BLIND_BENCH_UNIT_SCALE", "0.2"))


@pytest.fixture(scope="module")
def bench_run() -> BenchRunResult:
    harness = BlindBenchHarness(scale=UNIT_SCALE, seed=20260916)
    try:
        return harness.run()
    finally:
        harness.close()


def _observation(index: int) -> Observation:
    stamp = utc_now()
    return Observation(
        object_id=f"obs_diag_{index:03d}",
        subject_id="user_1",
        revision=1,
        occurred=TemporalExtent.point(stamp),
        learned_at=stamp,
        recorded_at=stamp,
        created_by="diagnostics-test",
        source_kind="chat",
        modality="text",
        value=f"合伙出资第 {index} 笔，涉及对赌协议",
    )


def _commit(store: SQLiteWorldStore, count: int, key: str) -> None:
    store.commit(
        [_observation(index) for index in range(count)],
        OperationRequest(
            operation_name="world.commit",
            expected_world_revision=0,
            reason="诊断仪单测：真实落盘观察",
            idempotency_key=key,
        ),
    )


def test_profiler_restores_the_driver_when_leaving_the_context() -> None:
    import aios_core.storage.sqlite_store as store_module

    original = store_module.sqlite3.connect
    profiler = StorageIOProfiler()
    with profiler.install():
        assert store_module.sqlite3.connect is not original
    assert store_module.sqlite3.connect is original
    assert profiler.attribute(()).unassigned_statements == 0


def test_profiler_attributes_real_statements_to_a_stage(tmp_path) -> None:
    store = SQLiteWorldStore(str(tmp_path / "diag.db"))
    _commit(store, 40, "diag-commit-1")

    profiler = StorageIOProfiler()
    with profiler.install():
        started = time.perf_counter()
        payloads = store.list_payloads(object_type=ObjectType.OBSERVATION)
        store.current_world_revision()
        ended = time.perf_counter()

    assert len(payloads) == 40
    attribution = profiler.attribute((("SX", started, ended),))
    assert attribution.unassigned_statements == 0
    assert attribution.per_stage["SX"]
    hottest = attribution.hottest()
    assert hottest.rows_scanned >= 40
    assert hottest.statements >= 1
    assert attribution.heaviest_stage()[0] == "SX"
    assert "SX" in attribution.render()


def test_profiler_counts_writes_by_rowcount(tmp_path) -> None:
    store = SQLiteWorldStore(str(tmp_path / "diag_write.db"))
    profiler = StorageIOProfiler()
    with profiler.install():
        started = time.perf_counter()
        _commit(store, 10, "diag-commit-2")
        ended = time.perf_counter()

    attribution = profiler.attribute((("SW", started, ended),))
    inserts = [
        hotspot
        for hotspot in attribution.per_stage["SW"]
        if hotspot.signature.startswith("INSERT")
    ]
    assert inserts
    assert sum(hotspot.rows_scanned for hotspot in inserts) >= 10


def test_profiler_leaves_out_of_window_statements_unassigned(tmp_path) -> None:
    store = SQLiteWorldStore(str(tmp_path / "diag_gap.db"))
    profiler = StorageIOProfiler()
    with profiler.install():
        store.current_world_revision()
    attribution = profiler.attribute((("SX", time.perf_counter() + 60.0, time.perf_counter() + 61.0),))
    assert attribution.unassigned_statements >= 1
    assert attribution.per_stage.get("SX", ()) == ()


def test_sql_signature_groups_by_verb_and_table() -> None:
    assert _signature("SELECT payload_json FROM object_revisions WHERE object_id = ?") == (
        "SELECT object_revisions"
    )
    assert _signature("insert into search_postings (a,b) values (?,?)") == (
        "INSERT search_postings"
    )
    assert _signature("SELECT a FROM world_commits JOIN operations ON 1=1") == (
        "SELECT operations,world_commits"
    )


def test_token_ledger_marks_mechanical_stages_as_zero(bench_run) -> None:
    ledger = {row.stage_id: row for row in token_ledger(bench_run)}
    assert ledger["S1"].tokens == 0
    assert ledger["S4"].tokens == 0
    assert ledger["S5"].tokens == 0
    assert ledger["S8"].tokens > 0
    assert all(row.sources or row.tokens == 0 for row in ledger.values())


def test_diagnosis_and_iron_rules_from_a_real_bench_run(bench_run) -> None:
    empty = IOAttribution(per_stage={}, overall=(), unassigned_statements=0)
    diagnosis = bottleneck_diagnosis(bench_run, empty)
    assert diagnosis["token_total"] > 0
    assert diagnosis["token_hotspot"].stage_id == "S8"
    assert diagnosis["io_hotspot"] is None
    assert diagnosis["io_hot_stage"] == ("(none)", 0)
    assert len(diagnosis["abstraction_fidelity"]) == 4
    assert diagnosis["worst_abstraction"]["distortion"] >= 0.0
    assert diagnosis["defects"]
    summary = render_bottleneck_summary(diagnosis)
    assert "Token 热点" in summary
    assertions = iron_rule_assertions(bench_run)
    assert len(assertions) == 5
    assert all(assertion.passed for assertion in assertions)
    assert all(assertion.checks for assertion in assertions)
    assert all("要求" in assertion.render() for assertion in assertions)


def test_runner_payload_is_self_consistent(tmp_path) -> None:
    """一键运行器：小规模真跑一次，产物必须自洽、可序列化、可排版。"""

    from scripts.run_blind_bench import main, render_summary, run_bench

    payload = run_bench(scale=0.2, seed=20260916, imu_samples=5_000)
    assert payload["extras"]["quota"]["total"] == payload["stages"][0]["facts"][
        "raw_samples_generated"
    ]
    for assertion in payload["extras"]["iron_rule_assertions"]:
        assert assertion["passed"] is True, assertion["rule"]
    diagnosis = payload["extras"]["diagnosis"]
    assert diagnosis["token_hotspot"]["stage_id"] == "S8"
    assert len(diagnosis["abstraction_fidelity"]) == 4
    assert diagnosis["io_attribution"]["overall"]
    assert [stage["stage_id"] for stage in payload["stages"]] == [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8",
    ]

    summary = render_summary(payload)
    for section in ("Token 账单", "I/O 归因", "认知抽象失真度", "五条铁律判据"):
        assert section in summary
    assert "1,131,330" not in summary  # 小规模运行不得混入满规模数字

    out_dir = tmp_path / "blind"
    exit_code = main(
        ["--scale", "0.2", "--imu-samples", "5_000", "--out", str(out_dir), "--stage", "S1"]
    )
    assert exit_code == 0
    dumped = json.loads((out_dir / "bench_run.json").read_text(encoding="utf-8"))
    assert [stage["stage_id"] for stage in dumped["stages"]] == ["S1"]
    assert (out_dir / "bench_summary.md").exists()


def test_runner_fails_loudly_on_unknown_stage() -> None:
    from scripts.run_blind_bench import run_bench

    with pytest.raises(AttributeError):
        run_bench(scale=0.05, stages=["S99"], imu_samples=1_000)
