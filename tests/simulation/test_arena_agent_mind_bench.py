"""TASK-M5-005-AGENT-ARENA 验收测试：八阶段端到端盲测 + 全景诊断器。

独立 Agent 战训考场：不 mock、不自编自答——直接驱动生产引擎（C01/C02/C05/C06/C07/C04）
跑完全程，断言五大铁律在对抗生命数据下逐条被捍卫。

验收标准（工单原文）：
    - 模拟优秀 Agent vs 劣质 Agent，断言诊断器能准确识别劣质 Agent 的违规与高能耗；
    - 八阶段全部执行、五铁律全绿。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios_core.simulation.arena_agent_mind_bench import (
    IRON_RULE_1,
    IRON_RULE_2,
    IRON_RULE_3,
    IRON_RULE_4,
    IRON_RULE_5,
    IRON_RULES,
    BenchSpec,
    MindDiagnostic,
    run_agent_mind_bench,
)


@pytest.fixture()
def bench_spec() -> BenchSpec:
    return BenchSpec(
        n_business_obs=16,
        n_noise_obs=20,
        n_query_fan=4,
        n_cockpit_rounds=5,
    )


@pytest.fixture()
def arena_report(tmp_path: Path, bench_spec: BenchSpec) -> dict:
    db = tmp_path / "arena.db"
    report = run_agent_mind_bench(db_path=db, spec=bench_spec)
    return report


def test_eight_stages_all_executed(arena_report: dict) -> None:
    stages = arena_report["stage_outputs"]
    assert set(stages) == {
        "阶段一:百万级摄入清洗边缘提纯",
        "阶段二:时间金字塔多尺度结晶与无损穿透",
        "阶段三:多维共振事件合成与生命周期",
        "阶段四:高阶认知演化曲线与新维度门槛",
        "阶段五:历史回溯与老王案单跳隔离",
        "阶段六:共生决策推演与主动帮助",
        "阶段七:沟通策略博弈与人设防线",
        "阶段八:驾驶舱硬旁路与终极对话",
    }


def test_five_iron_rules_all_defended(arena_report: dict) -> None:
    for rule in IRON_RULES:
        rows = arena_report["iron_rules"][rule]
        assert rows, f"{rule} 缺少断言"
        assert all(r["verdict"] == "PASS" for r in rows), f"{rule} 存在未通过断言"


def test_final_verdict_pass(arena_report: dict) -> None:
    assert arena_report["verdict"] == "PASS"
    assert arena_report["failure_count"] == 0


def test_iron_rule_3_p0_hard_bypass_within_50ms(arena_report: dict) -> None:
    rows = arena_report["iron_rules"][IRON_RULE_3]
    evidence = rows[0]["evidence"]
    assert evidence["dispatch_ms"] <= 50.0
    assert evidence["result"]["llm_calls"] == 0
    assert evidence["result"]["status"] == "SAFETY_BYPASS_EXECUTED"


def test_iron_rule_4_uses_raw_byte_sink_evidence(arena_report: dict) -> None:
    """物理删除断言必须基于真实字节审计，而非口头承诺。"""
    rows = arena_report["iron_rules"][IRON_RULE_4]
    purge_evidence = next(r["evidence"] for r in rows if "raw_before_bytes" in r["evidence"])
    assert purge_evidence["raw_before_bytes"] > 0
    assert purge_evidence["raw_after_bytes"] == 0
    assert purge_evidence["purged"] == purge_evidence["raw_before_bytes"]


def test_iron_rule_2_includes_dual_lens_evidence(arena_report: dict) -> None:
    rows = arena_report["iron_rules"][IRON_RULE_2]
    lens_evidence = next(r["evidence"] for r in rows if "as_known_view" in r["evidence"])
    assert "as_known_view" in lens_evidence and "annotated_view" in lens_evidence


def test_iron_rule_5_quota_evidence(arena_report: dict) -> None:
    rows = arena_report["iron_rules"][IRON_RULE_5]
    quota_evidence = next(r["evidence"] for r in rows if "daily_limit" in r["evidence"])
    assert quota_evidence["daily_limit"] == 1
    assert quota_evidence["remaining"] == 0  # 已用 1 次


def test_iron_rule_1_brevity_bounded(arena_report: dict) -> None:
    rows = arena_report["iron_rules"][IRON_RULE_1]
    cockpit_rows = [r for r in rows if "token_count" in r["evidence"]]
    assert cockpit_rows, "驾驶舱极简看板断言缺失"
    for r in cockpit_rows:
        assert 0 <= r["evidence"]["sentence_count"] <= 3


def test_diagnostic_identifies_good_agent(arena_report: dict) -> None:
    diag = MindDiagnostic(arena_report)
    assert diag.qualified()
    assert diag.grade() == "优秀 Agent"
    assert diag.violations() == []


def test_diagnostic_identifies_bad_agent_on_rule_failure(arena_report: dict) -> None:
    """劣质 Agent：篡改铁律 3（P0 大模型调用 > 0）→ 诊断器必须识别违规。"""
    tampered = {
        "verdict": "PASS",
        "iron_rules": {rule: [] for rule in IRON_RULES},
        "assertions": [],
    }
    # 只保留铁律 1 通过，其余铁律缺断言 → 判定不达标
    tampered["iron_rules"][IRON_RULE_1] = [
        {"rule": IRON_RULE_1, "claim": "x", "verdict": "PASS", "evidence": {}}
    ]
    diag = MindDiagnostic(tampered)
    assert not diag.qualified()
    assert diag.grade() == "劣质 Agent（违规/高能耗）"
    scores = diag.iron_rule_scores()
    assert scores[IRON_RULE_1] == 1.0
    assert scores[IRON_RULE_2] == 0.0
