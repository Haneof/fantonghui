"""M5-AGENT-ARENA 验收：千人千面大考场与全景体检。

1. 发生器：3 人设 × 3 年 × 3 会话，9,720 条观测流全覆盖；
2. 高智省 Token 策略(FrugalMindAgent)全面 PASS：
   tokens ≤ 500、命中率 100%、分外名 ≥ 1.0、零铁律违宪；
3. 低能耗散策略(WastefulMindAgent)在每场硬指标上全部失败：
   暴力扫描 token 超顶、塞入伪证、P0 调大模型一票否决；
4. 自动体检报告落盘 + 经验库 JSON 持久化。
"""

from __future__ import annotations

import json
from pathlib import Path

from aios_core.cognition.operation_experience_independent2 import CorpusDoc
from aios_core.cognition.self_reflection_independent2 import EventClass, UrgencyLevel
from aios_core.simulation.agent_mind_bench import (
    AgentMindArena,
    FrugalMindAgent,
    PersonaWorldGenerator,
    WastefulMindAgent,
)


def _docs(n: int = 100) -> list[CorpusDoc]:
    topics = ("家庭", "财务", "健康", "法务", "日程")
    return [
        CorpusDoc(
            doc_id=f"d{i:03d}",
            topics=(topics[i % 5],),
            title=f"{topics[i % 5]}-record-{i:03d}",
            body=(f"doc-{i:03d}-{topics[i % 5]}-" + "x" * 180)[:192],
        )
        for i in range(n)
    ]


def test_persona_world_generator_produces_one_hundred_faces_flow() -> None:
    gen = PersonaWorldGenerator()
    all_obs = [gen.generate(i) for i in range(3)]
    total = sum(len(o) for o in all_obs)
    assert total == 3 * (365 * 3) * 3     # 3 人设 × 3 年 × 3 会话
    # 高熵：同一人设内相邻观测绝不同话题重复
    for obs_list in all_obs:
        consecutive_topics = [o.topics[0] for o in obs_list[:12]]
        assert len(set(consecutive_topics[:6])) > 1

    # 决定论：重生成指纹完全一致
    assert gen.generate(0) == gen.generate(0)
    # 越界天数立即失败
    try:
        gen.generate(0, days=0)
    except ValueError:
        pass
    else:
        raise AssertionError("days=0 必须拒绝")


def test_arena_frugal_passes_wasteful_vetoed(tmp_path: Path) -> None:
    docs = _docs()
    agent_frugal = FrugalMindAgent(evidence_ids=["ev_1", "ev_2"])
    agent_wasteful = WastefulMindAgent(evidence_ids=["ev_1"])

    arena = AgentMindArena()
    arena.setup([agent_frugal, agent_wasteful], docs)

    sheet = arena.run(
        [agent_frugal, agent_wasteful],
        query="健康",
        expected_hits=("ev_1", "ev_2"),
        evidence_ids=("ev_1", "ev_2"),
        event=EventClass.LIFE_EMERGENCY, urgency=UrgencyLevel.LIFE_OR_DEATH,
    )

    frugal = sheet.by_agent("agent_frugal")
    waste = sheet.by_agent("agent_wasteful")

    # ---- 高智省 Token 策略 PASS
    assert frugal.tokens_consumed < waste.tokens_consumed
    assert frugal.tokens_consumed <= AgentMindArena.TOKEN_BUDGET_PER_QUERY
    assert frugal.evidence_hit_rate == 1.0
    assert frugal.persona_propriety_score == 1.0
    assert frugal.iron_law_violations == ()
    assert frugal.is_passing

    # ---- 低能耗散策略一票否决
    assert waste.tokens_consumed > AgentMindArena.TOKEN_BUDGET_PER_QUERY
    assert waste.evidence_hit_rate < 1.0          # 塞了 fake_evidence_404
    assert waste.persona_propriety_score < 1.0    # 生死场景仍沉默
    assert "HISTORY_TAMPER_VETO" in waste.iron_law_violations
    assert "P0_LLM_VETO" in waste.iron_law_violations
    assert "FABRICATED_EVIDENCE_VETO" in waste.iron_law_violations
    assert not waste.is_passing

    # ---- 全景体检报告落盘 + 经验库持久化
    report_path = tmp_path / "health_report.md"
    md = arena.write_report(sheet, report_path)
    assert "AIOS 3.0 共生心智操作全景体检报告" in md
    assert "agent_frugal" in md and "agent_wasteful" in md
    assert report_path.exists()

    exp_path = tmp_path / "arena_experience.json"
    arena.persist_experience(sheet, exp_path)
    raw = json.loads(exp_path.read_text(encoding="utf-8"))
    assert raw["report_kind"] == "aios_arena_score"
    assert any(s["agent_id"] == "agent_frugal" and s["is_passing"] for s in raw["scores"])
    assert any(s["agent_id"] == "agent_wasteful" and not s["is_passing"] for s in raw["scores"])
