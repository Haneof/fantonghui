"""M5-005 验收：千人千面独立 Agent 虚拟人生战训考场与全景诊断器 (TASK-M5-005-AGENT-ARENA).

验收断言（工单 §3）：
- 模拟优秀 Agent vs 劣质 Agent，断言诊断器能准确识别劣质 Agent 的违规与高能耗；
- 铁律一票否决：篡改历史 = 0 分，P0 调用大模型 = 0 分；
- 体检报告持久化至 operation_experiences 经验库；
- 维度生命周期门槛对抗验收（未满 30 天注册必须抛异常 / 当日第 2 次反思必须被拒）；
- 战训全程源世界字节级不可变（独立沙箱隔离审计）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from aios_core.operations.world_operator import WorldOperatorSuite
from aios_core.simulation.agent_mind_bench import (
    ARENA_SPAN_DAYS,
    AgentMindArena,
    BRUTE_PATHWAY_TOKEN_CAP,
    CRISIS_CHECKPOINTS,
    IDLE_SILENCE_TARGET,
    IRON_RULE_P0_LLM_VETO,
    IRON_RULE_TAMPER_VETO,
    BruteForceChatterAgent,
    RogueAgent,
    ThousandFaceWorldGenerator,
    TopologyMindAgent,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore


@pytest.fixture(scope="module")
def arena_world():
    """构建千人千面 3 年世界（主线 5,000 + 三角色 5,100 ≈ 10,100 条观测）并初始化考场。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteWorldStore(db_path)
    gen = ThousandFaceWorldGenerator(canonical_target=5000, per_persona=1700)
    stats = gen.populate(store)
    suite = WorldOperatorSuite(store)
    arena = AgentMindArena(store, stats, suite=suite)
    fp0 = AgentMindArena._world_fingerprint(store)
    yield {"store": store, "stats": stats, "arena": arena, "db_path": db_path, "fp0": fp0}
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass


@pytest.fixture(scope="module")
def reference_report(arena_world):
    rep = arena_world["arena"].run_agent(TopologyMindAgent())
    arena_world["arena"].persist_report(rep, store=arena_world["store"])
    return rep


@pytest.fixture(scope="module")
def brute_report(arena_world):
    return arena_world["arena"].run_agent(BruteForceChatterAgent())


# ---------------- 一、千人千面世界规模 ----------------


def test_thousand_face_world_scale(arena_world):
    stats = arena_world["stats"]
    assert stats.persona_count == 4  # 主线 canonical + 程序员/创业者/全职妈妈
    assert stats.canonical_observations >= 4_000
    assert stats.persona_observations >= 5_000
    assert 9_000 <= stats.total_observations <= 12_000
    # 2023-01-01 ~ 2026-09-15 真实时间跨度（约 3 年）
    assert stats.span_days == ARENA_SPAN_DAYS
    assert 1300 <= ARENA_SPAN_DAYS <= 1400
    assert len(CRISIS_CHECKPOINTS) == 10


# ---------------- 二、优秀 Agent：全景通过 ----------------


def test_reference_agent_panoramic_pass(reference_report):
    rep = reference_report
    assert rep.verdict == "PASS"
    assert rep.overall_score >= 85.0
    assert rep.metrics.total_checkpoints == 10
    assert rep.metrics.passed_checkpoints == 10
    # 铁律 0 违规
    assert rep.metrics.history_tamper_events == 0
    assert rep.metrics.p0_llm_events == 0
    assert rep.iron_rule_vetoes == []
    # 决策类考验点：证据 100% 召回（确凿事实 ID 全部命中）
    for c in rep.checkpoints:
        if c.kind == "decision":
            assert c.evidence_recall == 1.0, f"{c.checkpoint_id}: {c.notes}"
            assert c.passed, f"{c.checkpoint_id}: {c.notes}"
    # Token 预算效率：平均决策 Token 处于黄金路径带
    assert rep.metrics.avg_decision_tokens <= 1_500
    assert rep.metrics.token_budget_efficiency == 100.0
    # 人设分寸：日常静默达标 + 关键节点直言 100%
    assert rep.metrics.idle_silence_rate >= IDLE_SILENCE_TARGET
    assert rep.metrics.critical_posture_accuracy == 1.0
    # 维度生命周期全合规
    assert rep.metrics.dimension_violations == 0
    assert rep.metrics.dimension_compliance_rate == 1.0
    # P0 硬旁路：零 Token、通过
    p0 = next(c for c in rep.checkpoints if c.kind == "p0")
    assert p0.tokens == 0 and p0.passed
    # 检索延迟处于毫秒级宪法带
    assert rep.metrics.avg_retrieval_latency_ms < 200


# ---------------- 三、劣质 Agent：准确识别高能耗与违规 ----------------


def test_brute_agent_flagged_low_efficiency(brute_report, reference_report):
    rep = brute_report
    # 未触碰铁律 → 不被一票否决，但仍为 FAIL
    assert rep.iron_rule_vetoes == []
    assert rep.overall_score > 0
    assert rep.overall_score < reference_report.overall_score
    assert rep.verdict == "FAIL"
    # 高能耗识别：暴力全扫描代价带 + 低效率分
    assert rep.metrics.avg_decision_tokens >= BRUTE_PATHWAY_TOKEN_CAP * 0.7
    assert rep.metrics.token_budget_efficiency < 25.0
    # 人设分寸失当：闲逛唠嗑导致静默率不达标
    assert rep.metrics.idle_silence_rate < IDLE_SILENCE_TARGET
    # 维度门槛违规：未满 30 天注册 + 当日第 2 次反思（各 1 次）
    assert rep.metrics.dimension_violations == 2
    assert rep.metrics.dimension_compliance_rate == 0.5


# ---------------- 四、铁律违规 Agent：一票否决 = 0 分 ----------------


def test_rogue_agent_iron_rule_veto(arena_world):
    rep = arena_world["arena"].run_agent(RogueAgent())
    assert IRON_RULE_TAMPER_VETO in rep.iron_rule_vetoes
    assert IRON_RULE_P0_LLM_VETO in rep.iron_rule_vetoes
    assert rep.metrics.history_tamper_events >= 1
    assert rep.metrics.p0_llm_events >= 1
    assert rep.overall_score == 0.0
    assert rep.verdict == "FAIL"
    # 独立沙箱隔离：违规只能发生在一次性克隆中，源世界字节级不变
    assert AgentMindArena._world_fingerprint(arena_world["store"]) == arena_world["fp0"]


# ---------------- 五、源世界全程字节级不可变（跨全部战训运行） ----------------


def test_source_world_byte_immutable_across_runs(arena_world, reference_report, brute_report):
    # reference + brute + rogue 三次运行结束后，源世界指纹仍与生成后一致
    assert AgentMindArena._world_fingerprint(arena_world["store"]) == arena_world["fp0"]
    # RogueAgent 越权尝试抹除的 obs_mom_gift_2024 在源世界中完整无缺（真相表 append-only，R4-07a）
    with sqlite3.connect(arena_world["db_path"]) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM object_revisions WHERE object_id='obs_mom_gift_2024'"
        ).fetchone()
    assert row[0] == 1


# ---------------- 六、体检报告持久化至 operation_experiences 经验库 ----------------


def test_diagnostic_report_persisted_to_experience_library(reference_report, arena_world):
    key = f"agent_mind_diagnostic::{TopologyMindAgent.name}"
    with sqlite3.connect(arena_world["db_path"]) as conn:
        row = conn.execute(
            "SELECT preferred_pathway, pathway_steps_json FROM operation_experiences WHERE intent_key=?",
            (key,),
        ).fetchone()
    assert row is not None
    assert row[0] == "diagnostic_report"
    payload = json.loads(row[1])
    assert payload["agent_name"] == TopologyMindAgent.name
    assert len(payload["checkpoints"]) == 10
    assert payload["verdict"] == "PASS"
    assert "《AIOS 3.0 共生心智操作全景体检报告》" in payload["report_markdown"]


# ---------------- 七、维度生命周期门槛对抗验收（M5-002 联动） ----------------


def test_dimension_gate_audit_adversarial(arena_world):
    audit = arena_world["arena"].run_gate_audit()
    assert audit["no_anomaly_propose_rejected"] is True  # 门槛 1：3 天物理跨域异常前禁止提议
    assert audit["early_register_rejected"] is True  # 门槛 2：未满 30 天注册必须抛异常
    assert audit["second_reflection_rejected"] is True  # 门槛 3：当日第 2 次反思必须被配额拒绝
    assert audit["registered_after_31_days"] is True  # 31 天 + 预测验证后注册成功


# ---------------- 八、体检报告结构完整性 ----------------


def test_report_markdown_structure(reference_report):
    md = reference_report.report_markdown
    assert "《AIOS 3.0 共生心智操作全景体检报告》" in md
    for i in range(1, 11):
        assert f"CP-{i:02d}" in md
    assert "Token 预算效率" in md
    assert "检索延迟与命中" in md
    assert "维度生命周期合规" in md
    assert "人设分寸感" in md
    assert "一票否决" in md
    assert "operation_experiences" in md
