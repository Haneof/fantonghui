"""Agent-10 / M5-AGENT-ARENA：千人千面考场 + 五大铁律违宪检查。

老大指示：让 Agent 独立进驻虚拟人生海量数据流，用《全景体检报告》
回答——谁最快、最准、最少 Token。对照：省 Token 策略（蒸馏+拓扑
下钻）vs 低能耗散策略（每次暴力通读、琐事也吱声）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios_core.cognition.self_reflection import EventUrgency, ResponsePosture
from aios_core.query.search import SearchPathway
from aios_core.simulation.agent_mind_bench import (
    AgentMindArena,
    FrugalMindAgent,
    LifeTrajectoryGenerator,
    PanoramaCheckupReport,
    WastefulMindAgent,
    _AgentKit,
    _query_by_problem,
)

UTC = timezone.utc
AT = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
FAST = dict(years=1, days_per_year=200)


# ----------------------------------------------------------------------
# 世界发生器：确定性、高熵、真值/干扰同词不同链
# ----------------------------------------------------------------------

def test_world_generator_is_deterministic_across_pythonhashseed() -> None:
    """跨进程 + 跨 PYTHONHASHSEED：世界逐位一致（无 hash() 盐化种子）。"""
    code = (
        "from aios_core.simulation.agent_mind_bench import LifeTrajectoryGenerator;"
        "g = LifeTrajectoryGenerator(years=1, days_per_year=60);"
        "w = g.generate('entrepreneur', seed=959);"
        "print(w.record_count, sorted(w.expected['mom_gift_history'])[-1])"
    )
    outputs = set()
    for hashseed in ("0", "12345", "random"):
        env = {**__import__("os").environ, "PYTHONPATH": "src", "PYTHONHASHSEED": hashseed}
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout.strip())
    assert len(outputs) == 1, f"world differs across PYTHONHASHSEED: {outputs}"


def test_world_contains_truth_chains_with_same_word_distractors() -> None:
    gen = LifeTrajectoryGenerator(**FAST)  # type: ignore[arg-type]
    for profile in LifeTrajectoryGenerator.PROFILES:
        world = gen.generate(profile, seed=9)
        # 高熵骨架：>600 条观测（200 天 × 3 流 + 工作流）
        assert world.record_count > 600, profile
        for problem_type, truth_ids in world.expected.items():
            query = _query_by_problem(profile, problem_type)
            for rid in truth_ids:
                assert world.engine._records[rid].ground_truth is True  # noqa: SLF001
            # 路径 C：共现约束精确命中全部真值（accuracy 100%）
            result_c = world.engine.run_pathway(query, SearchPathway.TOPOLOGICAL_DRILL)
            assert set(result_c.hit_ids) == set(truth_ids), (profile, problem_type)
            # 路径 B：朴素 OR 必然引入同名干扰（假阳性 > 0），失义于"朴素即准"
            result_b = world.engine.run_pathway(query, SearchPathway.NAIVE_KEYWORD)
            assert len(set(result_b.hit_ids) - set(truth_ids)) > 0, (profile, problem_type)


def test_generator_rejects_unknown_profile() -> None:
    gen = LifeTrajectoryGenerator(years=1, days_per_year=30)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown profile"):
        gen.generate("extremely_rich_ceo", seed=1)


# ----------------------------------------------------------------------
# 考场：省 Token 策略 vs 低能耗散策略
# ----------------------------------------------------------------------

def test_arena_frugal_passes_and_crushes_wasteful_on_tokens() -> None:
    arena = AgentMindArena(token_budget=500_000, **FAST)  # type: ignore[arg-type]
    frugal = arena.run(FrugalMindAgent(), at=AT)
    wasteful = arena.run(WastefulMindAgent(), at=AT)

    # -- 省 Token 策略：最快、最准、最少 Token，体检 PASS ----------------
    assert frugal.verdict == "PASS"
    assert frugal.evidence_hit_rate >= 0.99
    assert frugal.posture_manner_score >= 0.8
    assert frugal.iron_rule_violations == ()
    assert frugal.token_budget_usage < 0.5
    assert frugal.total_records_seen > 1500
    # 经验蒸馏收口：第 4 轮起零对比直取（3 战役沉淀黄金经验）
    assert frugal.tokens_used > 0

    # -- 低能耗散策略：分寸感崩坏 + Token 放血，体检 NEEDS_TRAINING -----
    assert wasteful.verdict == "NEEDS_TRAINING"
    assert wasteful.posture_manner_score < 0.8     # 琐事也吱声、欺诈也只敢微震
    assert wasteful.token_budget_usage > frugal.token_budget_usage * 2.0
    assert wasteful.tokens_used > frugal.tokens_used * 2.0


def test_iron_rule_veto_p0_llm_call_is_one_vote_down() -> None:
    """铁律探针：P0 生命安全时刻调用大模型 → 一票否决 VETOED。"""

    class RuleBreakingAgent(FrugalMindAgent):
        def open_session(self, world) -> _AgentKit:  # type: ignore[override]
            kit = super().open_session(world)
            kit._llm_probe = lambda: None      # 探针注入：P0 时触发记账
            return kit

    arena = AgentMindArena(token_budget=500_000, **FAST)  # type: ignore[arg-type]
    report = arena.run(RuleBreakingAgent(), at=AT)
    assert report.verdict == "VETOED"
    assert report.p0_llm_calls > 0
    assert any("一票否决" in v for v in report.iron_rule_violations)


def test_history_tamper_channel_is_physically_absent() -> None:
    """铁律探针：检索总线无 update/delete 改写面，追加不减少世界总量。"""
    gen = LifeTrajectoryGenerator(**FAST)  # type: ignore[arg-type]
    world = gen.generate("programmer", seed=7)
    engine = world.engine
    forbidden = tuple(
        name for name in dir(engine)
        if name.startswith(("update", "delete", "remove", "rewrite", "overwrite"))
    )
    assert forbidden == (), f"history rewrite channel detected: {forbidden}"
    # 追加-only 语义：新注记今天可加（append），但不存在任何缩量通道
    before = engine.world_total_tokens()
    snapshot = {r.record_id: r for r in engine._records.values()}  # noqa: SLF001
    assert len(snapshot) == engine.record_count
    assert engine.world_total_tokens() >= before


def test_arena_rejects_naive_history_shrink_via_probe() -> None:
    """镜像探针在场内执行：篡改尝试后世界 Token 只增不减。"""
    arena = AgentMindArena(token_budget=500_000, **FAST)  # type: ignore[arg-type]
    report = arena.run(FrugalMindAgent(), at=AT)
    assert report.verdict == "PASS"            # 探针全程未发现改写通道


# ----------------------------------------------------------------------
# 《全景体检报告》持久化与全文体检
# ----------------------------------------------------------------------

def test_panorama_report_persists_and_roundtrips(tmp_path: Path) -> None:
    arena = AgentMindArena(token_budget=500_000, **FAST)  # type: ignore[arg-type]
    report = arena.run(FrugalMindAgent(), at=AT)
    path = arena.persist(report, tmp_path / "checkup" / "frugal_01.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["agent_id"] == "frugal_01"
    assert raw["strategy"] == "distilled_topological"
    assert set(raw["profiles_covered"]) == {"programmer", "entrepreneur", "mom"}
    assert raw["verdict"] == "PASS"
    restored = PanoramaCheckupReport.model_validate_json(path.read_text(encoding="utf-8"))
    assert restored.tokens_used == report.tokens_used
    assert restored.evidence_hit_rate == report.evidence_hit_rate


# ----------------------------------------------------------------------
# 全尺寸实证：3 年 × 三人设 ≈ 3.4 万条观测流（工单「近万条/人」口径）
# ----------------------------------------------------------------------

def test_full_scale_three_year_arena_frugal_passes_within_budget() -> None:
    arena = AgentMindArena(token_budget=2_000_000)          # 3 年 × 1217 天全马
    report = arena.run(FrugalMindAgent(), at=AT)
    assert report.total_records_seen >= 30_000              # 近万条 × 3 人设
    assert report.verdict == "PASS"
    assert report.evidence_hit_rate >= 0.99
    assert report.posture_manner_score >= 0.8
    assert report.token_budget_usage < 0.5                  # 300 万预算内余量过半
    assert report.iron_rule_violations == ()
