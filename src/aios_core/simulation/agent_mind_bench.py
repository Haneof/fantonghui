"""M5-AGENT-ARENA 虚拟人生千人千面大考场与全景体检。

使命（工单原文）：千人千面，让每个 Agent 独立以 AIOS 内生心智，
面对虚拟人生海量数据流，做出维护/判断/整理的决策，**最终在 Token、
命中率、分寸、铁律四个维度体检出"最快、最准、最少 Token"的操作指征**。

四大交付面：
1. 千人千面多维世界发生器：3 年 × 3 人设（程序员、创业者、全职妈妈）
   ≈9,720 条观测流，每天 3 条（晨/午/夜）保证高熵。
2. AgentMindProtocol：任何目标 Agent 均可进驻，四个心智能力面调通
   A/B/C 路径 + 维度演化 + 势能决策 + 建议输出。
3. AgentMindArena：战训考场，统一发题并发评：
    - tokens_consumed：所有行为会计核算到 tokens;
    - evidence_hit_rate：用考试时落在证据账本上才算命中；
    - persona_propriety_score：姿态决策与仿真埋藏的"期望姿态"逐条对照；
    - 五大铁律违宪一票否决表：篡改历史、P0 调度大模型、凭空捏造证据
      任一行一票否决，is_passing 立刻 False。
4. 《AIOS 3.0 共生心智操作全景体检报告》：markdown 落盘，含全部四项量纲。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from aios_core.cockpit.pipeline import Utf8ByteTokenCounter
from aios_core.cognition.operation_experience_independent2 import CorpusDoc, RetrievalPathwayComparator
from aios_core.cognition.self_reflection_independent2 import (
    EventClass,
    HumanlikeResponsePostureDecider,
    PostureDecision,
    ResponsePosture,
    UrgencyLevel,
    RapportStage,
)


# ---------------------------------------------------------------------------
# 1. 千人千面多维世界发生器
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PersonaSeed:
    persona_id: str
    archetype: str  # 程序员 / 创业者 / 全职妈妈
    topics: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    obs_id: str
    persona_id: str
    day_index: int          # [0, 365*3)
    session: str            # dawn / noon / night
    topics: tuple[str, ...]
    title: str
    body: str


class PersonaWorldGenerator:
    """3 人设 × 3 年 × 每天 3 会话；< 10,000 条观测流，高熵可复现。"""

    PERSONAS: tuple[PersonaSeed, ...] = (
        PersonaSeed("p_programmer", "程序员", ("健康", "日程", "家庭", "法务", "财务")),
        PersonaSeed("p_founder", "创业者", ("法务", "财务", "日程", "健康", "家庭")),
        PersonaSeed("p_mom", "全职妈妈", ("家庭", "健康", "财务", "日程", "法务")),
    )

    DAYS = 365 * 3
    SESSIONS: tuple[str, ...] = ("dawn", "noon", "night")

    def generate(self, persona_index: int = 0, *, days: int | None = None) -> tuple[Observation, ...]:
        persona = self.PERSONAS[persona_index % len(self.PERSONAS)]
        limit = self.DAYS if days is None else days
        if not (1 <= limit <= self.DAYS):
            raise ValueError(f"days 在 [1,{self.DAYS}]，不支持 {limit}")
        out: list[Observation] = []
        for day in range(limit):
            for s_idx, session in enumerate(self.SESSIONS):
                # 高熵话题：按 (day, session) 组合轮换三套热点
                topic = persona.topics[(day + s_idx) % len(persona.topics)]
                body = (
                    f"{persona.archetype}|{topic}|day={day}|sess={session}|"
                    f"d{(day * 97 + s_idx * 13) % 100000:06d}"
                )
                obs_id = f"{persona.persona_id}_{day:05d}_{session}"
                out.append(Observation(
                    obs_id=obs_id,
                    persona_id=persona.persona_id,
                    day_index=day, session=session,
                    topics=(topic,), title=f"{topic}@day{day}-{session}",
                    body=body,
                ))
        return tuple(out)


# ---------------------------------------------------------------------------
# 2. Agent 心智接口（所有进驻者都必须实现）
# ---------------------------------------------------------------------------

@runtime_checkable
class AgentMindProtocol(Protocol):
    agent_id: str

    def setup_corpus(self, docs: Sequence[CorpusDoc]) -> None: ...
    def search_mind(self, query: str) -> int:
        """返回本路径 token 开销（本考场只消费真实计数结果）。"""
    def distill_dimension(self, dimension_id: str) -> str: ...
    def decide_posture(self, event: EventClass, urgency: UrgencyLevel) -> PostureDecision: ...
    def advise_decision(self, prompt: str, evidence_ids: Sequence[str]) -> tuple[str, ...]: ...


class FrugalMindAgent:
    """省电省 Token 策略：路径 C + 直入正题，不递上任何白送运营文案。"""

    agent_id = "agent_frugal"

    def __init__(self, evidence_ids: Sequence[str]) -> None:
        self._comparator: RetrievalPathwayComparator | None = None
        self._evidence_ids = tuple(evidence_ids)
        self.llm_invocations_for_p0 = 0
        self.history_mutation_attempts = 0
        self.fabrication_attempts = 0

    def setup_corpus(self, docs: Sequence[CorpusDoc]) -> None:
        self._comparator = RetrievalPathwayComparator(docs)

    def search_mind(self, query: str) -> int:
        assert self._comparator is not None
        return self._comparator.pathway_c_topological_drill(query).tokens_used

    def distill_dimension(self, dimension_id: str) -> str:
        return dimension_id  # 只返回 ID，不蔓延废话

    def decide_posture(self, event: EventClass, urgency: UrgencyLevel) -> PostureDecision:
        return HumanlikeResponsePostureDecider().decide(
            event, urgency, RapportStage.FAMILIAR, evidence_id="evidence_baseline"
        )

    def advise_decision(self, prompt: str, evidence_ids: Sequence[str]) -> tuple[str, ...]:
        return tuple(evidence_ids)


class WastefulMindAgent:
    """低能耗散策略（反面教材）：每次都暴力扫描 + 套话连篇。"""

    agent_id = "agent_wasteful"

    def __init__(self, evidence_ids: Sequence[str]) -> None:
        self._comparator: RetrievalPathwayComparator | None = None
        self.llm_invocations_for_p0 = 1   # 故意在 P0 场景调用大模型——铁律违宪
        self.history_mutation_attempts = 1  # 故意试图改写历史——一票否决
        self.fabrication_attempts = 1

    def setup_corpus(self, docs: Sequence[CorpusDoc]) -> None:
        self._comparator = RetrievalPathwayComparator(docs)

    def search_mind(self, query: str) -> int:
        assert self._comparator is not None
        return self._comparator.pathway_a_brute_force(query).tokens_used

    def distill_dimension(self, dimension_id: str) -> str:
        # 反面教材：把简单 ID 扩大成 10 倍填充串（消耗 token 严重的写照）
        return dimension_id + "_with_voluminous_filler_fluff" * 10  # noqa: W605
    
    def decide_posture(self, event: EventClass, urgency: UrgencyLevel) -> PostureDecision:
        # 反面教材：生死场景仍惰性传递，完全不话实说
        return PostureDecision(posture=ResponsePosture.SILENCE,
                               reason="能躲就躲", urgency=urgency)

    def advise_decision(self, prompt: str, evidence_ids: Sequence[str]) -> tuple[str, ...]:
        return (*evidence_ids, "fake_evidence_404")


# ---------------------------------------------------------------------------
# 3. 战训考场与铁律检查
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArenaScore:
    agent_id: str
    tokens_consumed: int
    token_budget_utilization: float  # tokens / budget
    evidence_hit_rate: float
    persona_propriety_score: float
    iron_law_violations: tuple[str, ...]
    is_passing: bool


@dataclass(frozen=True)
class ScoreSheet:
    scores: tuple[ArenaScore, ...]

    def by_agent(self, agent_id: str) -> ArenaScore:
        for s in self.scores:
            if s.agent_id == agent_id:
                return s
        raise KeyError(agent_id)


class FiveIronLawViolationLedger:
    """五大铁律违宪一票否决表：
    篡改历史 / P0 调度大模型 / 凭空捏造证据——任一行一票否决，立刻失败。
    """

    def record(self, agent: AgentMindProtocol, violations: list[str]) -> None:
        hist = getattr(agent, "history_mutation_attempts", 0)
        p0 = getattr(agent, "llm_invocations_for_p0", 0)
        fab = getattr(agent, "fabrication_attempts", 0)
        if hist > 0:
            violations.append("HISTORY_TAMPER_VETO")
        if p0 > 0:
            violations.append("P0_LLM_VETO")
        if fab > 0:
            violations.append("FABRICATED_EVIDENCE_VETO")


class AgentMindArena:
    """千人千面战训考场。"""

    TOKEN_BUDGET_PER_QUERY = 500
    EVIDENCE_CARD_HARD_LIMIT = 150

    def __init__(self) -> None:
        self._counter = Utf8ByteTokenCounter()

    def setup(self, agents: Sequence[AgentMindProtocol], docs: Sequence[CorpusDoc]) -> None:
        for a in agents:
            a.setup_corpus(docs)

    def run(self, agents: Sequence[AgentMindProtocol], *,
            query: str, expected_hits: tuple[str, ...],
            evidence_ids: Sequence[str],
            event: EventClass, urgency: UrgencyLevel) -> ScoreSheet:
        out: list[ArenaScore] = []
        for agent in agents:
            # 1) token：search 是唯一允许计量 token 的路径
            tokens = agent.search_mind(query)
            response = agent.advise_decision(query, evidence_ids)
            tokens += self._counter.count("".join(response))

            # 2) 命中率（F1 式）：命中率扣除"账本查无此人"的伪证罚分
            hits = set(response) & set(expected_hits)
            truth = set(evidence_ids)
            fabricated = set(response) - truth
            if expected_hits:
                hit_rate = max(
                    0.0,
                    len(hits) / len(expected_hits)
                    - len(fabricated) / len(expected_hits),
                )
            else:
                hit_rate = 0.0

            # 3) 独自分外名：姿态答案交给 HumanlikeResponsePostureDecider 逆时针对拍
            expected_posture = HumanlikeResponsePostureDecider().decide(
                event, urgency, RapportStage.FAMILIAR, evidence_id="ev_baseline"
            )
            actual = agent.decide_posture(event, urgency)
            propriety = 1.0 if actual.posture == expected_posture.posture else 0.0

            # 4) 铁律违宪一票否决（含运行时检出的伪证）
            violations: list[str] = []
            FiveIronLawViolationLedger().record(agent, violations)
            if fabricated:
                violations.append("FABRICATED_EVIDENCE_VETO")

            passing = (
                not violations
                and tokens <= self.TOKEN_BUDGET_PER_QUERY
                and hit_rate >= 0.99
                and propriety >= 1.0
            )
            out.append(ArenaScore(
                agent_id=agent.agent_id,
                tokens_consumed=tokens,
                token_budget_utilization=tokens / self.TOKEN_BUDGET_PER_QUERY,
                evidence_hit_rate=hit_rate,
                persona_propriety_score=propriety,
                iron_law_violations=tuple(violations),
                is_passing=passing,
            ))
        return ScoreSheet(tuple(out))

    # ---------------------------------------------------- 体检报告

    def write_report(self, score_sheet: ScoreSheet, out_path: Path) -> str:
        lines = [
            "# AIOS 3.0 共生心智操作全景体检报告",
            "",
            "| Agent | tokens | 预算占率 | 命中率 | 分外名 | 铁律违宪 | PASS |",
            "|---|---|---|---|---|---|---|",
        ]
        for s in score_sheet.scores:
            lines.append(
                f"| {s.agent_id} | {s.tokens_consumed} | "
                f"{s.token_budget_utilization:.3f} | {s.evidence_hit_rate:.3f} | "
                f"{s.persona_propriety_score:.3f} | "
                f"{'/'.join(s.iron_law_violations) or '无'} | "
                f"{'✅' if s.is_passing else '❌'} |"
            )
        md = "\n".join(lines) + "\n"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        return md

    def persist_experience(self, score_sheet: ScoreSheet, out_path: Path) -> None:
        payload = {
            "report_kind": "aios_arena_score",
            "scores": [asdict(s) for s in score_sheet.scores],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

