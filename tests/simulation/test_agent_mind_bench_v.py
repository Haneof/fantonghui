# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-005 Agent 战训考场验收（工单 #10 §3）：

  * 3 年高熵多维世界 + 10 个危机考验点齐备；
  * 优秀 Agent vs 劣质 Agent：诊断器必识别劣质者的违规与高能耗；
  * 铁律一票否决双条款：改历史 = 0 分，P0 走大模型 = 0 分；
  * 体检报告持久化至 operation_experiences 经验库。
"""

from __future__ import annotations

import pytest

from aios_core.cognition_m5.operation_experience import OperationExperienceDistiller  # noqa: F401
from aios_core.simulation.agent_mind_bench_m5 import (
    ARENA_BASE,
    CHECKPOINTS,
    RECALL_FLOOR,
    AgentMindDiagnosticReport,
    AgentMindPlayground,
    AgentProfile,
    TOKEN_EFFICIENCY_REDLINE,
)


@pytest.fixture(scope="module")
def arena(tmp_path_factory):
    arena_dir = tmp_path_factory.mktemp("arena")
    return AgentMindPlayground(str(arena_dir / "world.db"))


GOOD = AgentProfile(agent_id="agent.exemplar")
BAD = AgentProfile(
    agent_id="agent.slob",
    uses_topology_search=False,      # 暴力全扫
    rewrites_history=True,           # 一票否决①
    routes_p0_to_llm=True,           # 一票否决②
    procrastinates_dimension=True,   # 想一天速成维度
    chatterbox=True,                 # 闲逛嘴碎
    sloppy_retrieval=True,           # 切面全丢
    judge_noise=0.4,
)
MID = AgentProfile(agent_id="agent.lazy", judge_noise=0.4,
                   procrastinates_dimension=True, chatterbox=True)


# ---------------------------------------------------------------------------
# 考场本体：3 年 × 10 点
# ---------------------------------------------------------------------------


def test_playground_has_ten_checkpoints_and_three_year_world(arena):
    assert len(CHECKPOINTS) == 10
    payloads = arena.store.list_payloads()
    assert len(payloads) >= 60, "高熵世界语料量不足"
    days = set()
    for p in payloads:
        occ = p.get("asserted_at") or p.get("occurred_at")
        if occ:
            days.add(str(occ)[:10])
    span = (max(days), min(days))
    assert span[0] >= "2026-09" and span[1] <= "2023-10", "三年纵深必须实锤"


# ---------------------------------------------------------------------------
# 优秀 Agent：五维全绿
# ---------------------------------------------------------------------------


def test_exemplar_agent_scores_and_stays_compliant(arena):
    rec = arena.run_all(GOOD)
    assert rec.veto_events == ()
    assert rec.final_score() > 60, f"优秀者得分 {rec.final_score()} 不应落魄"
    assert rec.avg_decision_tokens < TOKEN_EFFICIENCY_REDLINE
    assert rec.avg_recall >= RECALL_FLOOR, f"检索准确率 {rec.avg_recall:.0%}"
    assert rec.dimension_compliant
    assert rec.resonance_score >= 0.9

    report = AgentMindDiagnosticReport.from_recorder(rec)
    assert report.final_score == rec.final_score()
    assert report.findings == ("五维全绿：此刻的答法配得上共生心智",)
    tokens = report.metrics["avg_decision_tokens"]
    assert tokens < TOKEN_EFFICIENCY_REDLINE


# ---------------------------------------------------------------------------
# 劣质 Agent：双一票否决 + 高能耗 + 低召回全落网
# ---------------------------------------------------------------------------


def test_slob_agent_is_diagnosed_zero_and_flagged(arena):
    rec = arena.run_all(BAD)
    # 双一票否决各自应验、合取归零
    assert rec.vetoed
    veto_kinds = " ".join(rec.veto_events)
    assert "HISTORY_REWRITE" in veto_kinds, "改历史必被点名"
    assert "P0_TO_LLM" in veto_kinds, "P0 走大模型必被点名"
    assert rec.final_score() == 0.0, "一票否决：得分硬归零"

    # 高能耗实测：暴力全扫 vs 拓扑检索，能量落差必被量化
    exemplar_avg = arena.run_all(GOOD).avg_decision_tokens
    assert rec.avg_decision_tokens > exemplar_avg * 5, \
        "暴力全扫的能耗必须是拓扑检索的数倍级"

    # 低召回与维度违规、嘴碎全数落网
    assert rec.avg_recall < RECALL_FLOOR
    assert not rec.dimension_compliant
    assert rec.resonance_score < 0.8

    report = AgentMindDiagnosticReport.from_recorder(rec)
    text = "；".join(report.findings)
    for flag in ("一票否决触发", "高能耗", "检索准确率", "维度生命周期违规",
                 "人设分寸感"):
        assert flag in text, f"诊断漏报：{flag}"


def test_zero_score_holds_under_single_veto(arena):
    only_history = AgentProfile(agent_id="agent.hist", rewrites_history=True)
    only_p0 = AgentProfile(agent_id="agent.p0", routes_p0_to_llm=True)
    assert arena.run_all(only_history).final_score() == 0.0
    assert arena.run_all(only_p0).final_score() == 0.0


def test_lazy_mid_agent_outscored_by_exemplar(arena):
    good = arena.run_all(GOOD).final_score()
    mid = arena.run_all(MID).final_score()
    assert good > mid >= 0, "三无铁律违规但五维松垮者：不干零，但要排名垫底"


# ---------------------------------------------------------------------------
# 报告持久化至经验库
# ---------------------------------------------------------------------------


def test_report_persists_into_operation_experiences(arena):
    rec = arena.run_all(AgentProfile(agent_id="agent.persisted"))
    report = AgentMindDiagnosticReport.from_recorder(rec)
    report.persist(arena.distiller)

    rows = arena.distiller.list_observations()
    arena_rows = [r for r in rows if r["kind"] == "arena_report"]
    assert arena_rows, "报告必须落 operation_experiences 经验库"
    latest = arena_rows[-1]
    assert latest["payload"]["agent_id"] == "agent.persisted"
    assert latest["payload"]["final_score"] == report.final_score
    assert len(latest["payload"]["checkpoint_logs"]) == 10
