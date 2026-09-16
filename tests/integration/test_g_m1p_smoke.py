"""G-M1P 套件降规模冒烟：Gate 前唯一合法运行形态（保脚本常热，不宣称 Gate 通过）。

正式 50 万修订点位在 M1 Gate 后跑目标硬件：
`PYTHONPATH=src python -m aios_core.bench.g_m1p --db <path> --revisions 500000`
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios_core.bench.g_m1p import (
    Budget,
    consistency_ok,
    generate_world,
    plan_checks,
    run_bench,
)

CI_BUDGET = Budget(search_p95_ms=400.0, drill_p95_ms=400.0,
                   catchup_ms_per_revision=50.0, strict_stale_max_ms=200.0)


@pytest.fixture(scope="module")
def bench_db(tmp_path_factory) -> Path:
    db = tmp_path_factory.mktemp("g_m1p") / "world.db"
    stats = generate_world(db, 1200, seed=101)
    assert stats["objects"] > 500 and stats["revisions"] == 1200
    return db


def test_smoke_bench_all_points_green(bench_db):
    report = run_bench(bench_db, queries=40, seed=101, budget=CI_BUDGET,
                       revisions_target=1200, late_revisions=300)
    assert report["verdict"] == "pass", report["failures"]
    pts = report["points"]
    assert pts["search"]["n"] == 40 and pts["search"]["p95"] <= CI_BUDGET.search_p95_ms
    assert pts["late_data"]["strict"]["status"] == "stale_index"  # 红线：绝不装新
    assert pts["late_data"]["adaptive"]["status"] == "ok" and pts["late_data"]["lag_before"] >= 300
    assert pts["rebuild"]["indexed_docs"] >= 1000
    assert pts["hot_cards"]["status"] == "not_implemented"  # M1-020 落地后本断言升级
    assert report["consistency"]["verdict"] == "pending_followup"  # M4a/M7 点位未跑
    json.dumps(report, ensure_ascii=False)  # 报告必须可归档


def test_plan_checks_locked_to_kernel_shape(bench_db):
    plan = plan_checks(bench_db)
    assert plan["verdict"] is True
    assert plan["kernel_finalize_shape_locked"], "finalize SQL 形态与内核源码对锁失败——基准在测假查询"


def test_consistency_tolerance_semantics():
    assert consistency_ok({"G-M1P": 50.0, "M4a": None, "M7-002": None})["verdict"] == "pending_followup"
    assert consistency_ok({"a": 50.0, "b": 55.0, "c": 60.0})["verdict"] == "ok"     # +20% 内
    assert consistency_ok({"a": 50.0, "b": 61.0})["verdict"] == "drift"             # 超容忍
    assert consistency_ok({"a": 0.0, "b": 1.0})["verdict"] == "drift"               # 零基线不放行
