# -*- coding: utf-8 -*-
"""Agent-10 / M5-AGENT-ARENA 千人千面多维人生战训考场 · 验收测试（arena01 线）

硬门禁：
- 3 种人格 3 年跨度近万条观测流、全 seed 决定性；
- 高智商省 Token 策略 vs 低能耗散策略：同等证据命中率下 Token 差 ≥20 倍；
- 人设分寸感：琐事沉默、红线直言；五大铁律违宪检查
  （P0 调大模型 / 篡改历史 各一票否决）；
- 《共生心智操作全景体检报告》经验库 JSONL 持久化。
"""

import json

import pytest

from aios_core.cognition.self_reflection_arena01 import (
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
)
from aios_core.cognition.symbiotic_advisor_arena01 import MomBirthdayGiftAdvisor
from aios_core.contracts.safety_bypass import WakePriority
from aios_core.query.search_arena01 import (
    ExperiencePool,
    MultidimensionalSearchBus,
    OperationExperienceDistiller,
    PathwayComparisonExecutor,
)
from aios_core.simulation.agent_mind_bench_arena01 import (
    AgentMindArena,
    ArenaDeckItem,
    ArenaReportStore,
    MindPolicy,
    MindResult,
    PersonaTrajectoryGenerator,
)

SEED = 0xA510


class SavvyDistilledPolicy(MindPolicy):
    """高智商省 Token 策略：蒸馏直达 + 拓扑下钻 + 铁律姿态 + 证据化建议。"""

    name = "savvy-distilled"

    def __init__(self) -> None:
        self._decider = HumanlikeResponsePostureDecider()
        self._rapport = DynamicRapportModel().advance(companionship_days=365, survived_events=20)
        self._evidence = {}

    def bind(self, trajectory) -> None:
        self._evidence = trajectory.advisor_evidence

    def search_mind(self, deck, distiller, bus):
        terms = tuple(deck.prompt.split())
        answer = distiller.distilled_search(terms)
        if answer is not None:
            return MindResult(token_cost=answer.token_cost, refs=answer.refs)
        distiller.observe(terms)
        distiller.maybe_distill_gold(terms)
        report = PathwayComparisonExecutor(bus).pathway_c_topology_drill(terms)
        return MindResult(token_cost=report.token_cost, refs=report.refs)

    def decide_posture(self, deck):
        decision = self._decider.decide(
            event_kind=deck.event_kind, urgency=deck.urgency, rapport=self._rapport,
        )
        return MindResult(posture=decision.posture.value)

    def advise_decision(self, deck):
        if deck.advice_kind == "gift":
            advice = MomBirthdayGiftAdvisor().advise(self._evidence["gift"])
            return MindResult(token_cost=advice.token_cost, advice_verdict=advice.verdict)
        return MindResult(advice_verdict="not-applicable")


class WastefulBrutePolicy(MindPolicy):
    """低能耗散策略：暴力全库扫描 + 嗓门错位 + P0 违规调大模型。"""

    name = "wasteful-brute"

    def search_mind(self, deck, distiller, bus):
        report = PathwayComparisonExecutor(bus).pathway_a_brute_scan(tuple(deck.prompt.split()))
        return MindResult(token_cost=report.token_cost, refs=report.refs)

    def decide_posture(self, deck):
        llm = 1 if deck.urgency is WakePriority.P0_CRITICAL_SAFETY else 0  # 红线违规
        posture = "CRITICAL_SPOKEN" if deck.event_kind == "weather_gossip" else "SILENCE"
        return MindResult(posture=posture, llm_calls=llm)

    def advise_decision(self, deck):
        return MindResult(token_cost=5, advice_verdict="随便看看再说")


def _founder_rig(tmp_path):
    trajectory = PersonaTrajectoryGenerator(seed=SEED).build("startup_founder")
    bus = MultidimensionalSearchBus()
    for doc in trajectory.observations:
        bus.add(doc)
    distiller = OperationExperienceDistiller(bus, ExperiencePool(tmp_path / "pool.jsonl"))
    return trajectory, AgentMindArena(bus, distiller)


def test_gate1_personas_span_three_years_near_10k_and_deterministic():
    gen = PersonaTrajectoryGenerator(seed=SEED)
    for persona in ("senior_programmer", "startup_founder", "fulltime_mother"):
        t = gen.build(persona)
        assert (t.end - t.start).days + 1 == 1095  # 3 年跨度
        assert 8_700 <= len(t.observations) <= 10_000  # 近万条观测流
        assert len(t.gold_families) == 4
        assert set(t.advisor_evidence) == {"gift", "fraud", "cardiac"}
    a = gen.build("startup_founder")
    b = gen.build("startup_founder")
    assert [d.object_id for d in a.observations[:50]] == [d.object_id for d in b.observations[:50]]
    assert a.observations[0].text == b.observations[0].text
    c = gen.build("senior_programmer")
    assert a.observations[0].text != c.observations[0].text  # 千人千面


def test_gate2_deck_golden_anchors_are_bus_searchable(tmp_path):
    trajectory, arena = _founder_rig(tmp_path)
    deck = arena.build_deck(trajectory)
    assert len(deck) == 8
    assert sum(1 for d in deck if d.kind == "search") == 4
    assert sum(1 for d in deck if d.kind == "posture") == 3
    assert sum(1 for d in deck if d.kind == "advice") == 1


def test_gate3_savvy_crushes_wasteful_on_token_and_tact(tmp_path):
    trajectory, arena = _founder_rig(tmp_path)
    savvy = arena.run(SavvyDistilledPolicy(), trajectory, warp_iters=4)
    wasteful = arena.run(WastefulBrutePolicy(), trajectory, warp_iters=4)

    # 同等 100% 证据命中率前提下，Token 消耗差 ≥20 倍
    assert savvy.evidence_hit_rate == 1.0
    assert wasteful.evidence_hit_rate == 1.0
    assert wasteful.total_tokens >= savvy.total_tokens * 20
    assert savvy.budget_usage < 0.005
    assert wasteful.budget_usage > 1.0  # 暴力扫描直接击穿月度封套

    # 人设分寸感：savvy 满分；wasteful 全错位
    assert savvy.tact_score == 100.0
    assert wasteful.tact_score < 40.0

    # 五大铁律违宪检查：P0 调大模型一票否决命中 wasteful
    assert savvy.constitution_ok and savvy.llm_calls == 0
    assert not wasteful.constitution_ok
    assert any("P0调用大模型" in r for r in wasteful.veto_reasons)


def test_gate4_constitution_veto_on_history_mutation(tmp_path):
    class TamperPolicy(SavvyDistilledPolicy):
        name = "tamper"

        def search_mind(self, deck, distiller, bus):
            out = super().search_mind(deck, distiller, bus)
            out.history_mutations = 1
            return out

    trajectory, arena = _founder_rig(tmp_path)
    result = arena.run(TamperPolicy(), trajectory, warp_iters=1)
    assert not result.constitution_ok
    assert any("篡改历史" in r for r in result.veto_reasons)


def test_gate5_panorama_report_persists_append_only(tmp_path):
    trajectory, arena = _founder_rig(tmp_path)
    store = ArenaReportStore(tmp_path / "experience" / "arena_reports.jsonl")
    for policy in (SavvyDistilledPolicy(), WastefulBrutePolicy()):
        result = arena.run(policy, trajectory, warp_iters=1)
        store.persist(result)
    lines = store._path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    batch = [json.loads(l) for l in lines]
    assert {b["policy"] for b in batch} == {"savvy-distilled", "wasteful-brute"}
    assert all("共生心智操作全景体检报告" in b["report"] for b in batch)
