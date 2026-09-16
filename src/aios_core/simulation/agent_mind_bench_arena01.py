"""M5-AGENT-ARENA 千人千面多维人生战训考场（arena01 独立命名并存线）。

老大核心指示：让每个 Agent 独立作为 AIOS 里的 AI，面对虚拟人生海量
数据流自行判断、维护、整理，总结出最快、最准、最少 Token 获取知识的机制。

- PersonaTrajectoryGenerator：程序员 / 创业者 / 全职妈妈等高熵人生
  轨迹，3 年跨度、单人 ~9,500 条观测流，全 seed 决定性；
- AgentMindArena：目标 Agent 独立进驻，自主调用 search_mind /
  distill_dimension / decide_posture / advise_decision；
- 自动评分：Token 预算使用率、证据检索命中率、人设分寸感得分、
  五大铁律违宪检查（篡改历史一票否决、P0 调大模型一票否决）；
- 报告：《AIOS 3.0 共生心智操作全景体检报告》持久化到经验库（JSONL 只追加）。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.safety_bypass import WakePriority
from aios_core.query.search_arena01 import (
    MultidimensionalSearchBus,
    OperationExperienceDistiller,
    SearchDocument,
    intent_hash_of,
)

__all__ = [
    "PersonaTrajectory",
    "PersonaTrajectoryGenerator",
    "ArenaDeckItem",
    "MindResult",
    "MindPolicy",
    "ArenaRunResult",
    "AgentMindArena",
    "ArenaReportStore",
    "DEFAULT_PERSONAS",
    "MONTHLY_TOKEN_BUDGET",
]

MONTHLY_TOKEN_BUDGET = 2_554_000
DEFAULT_PERSONAS = ("senior_programmer", "startup_founder", "fulltime_mother")


@dataclass(frozen=True)
class PersonaTrajectory:
    persona: str
    persona_label: str
    start: date
    end: date
    observations: Tuple[SearchDocument, ...]
    gold_families: Dict[str, Tuple[str, ...]]  # intent_family -> gold object_ids
    advisor_evidence: Dict[str, Tuple["AdvisorEvidence", ...]] = field(default_factory=dict)


class PersonaTrajectoryGenerator:
    """千人千面高熵轨迹发生器（3 年 ~9,500 观测，seed 决定性）。"""

    _LABELS = {
        "senior_programmer": "资深程序员",
        "startup_founder": "创业企业法务总监",
        "fulltime_mother": "全职妈妈",
    }
    _DAILY_KINDS = ("heartrate", "chat", "billing", "calendar", "scene")

    def __init__(self, *, seed: int, start: date = date(2023, 9, 16)) -> None:
        self._seed = seed
        self._start = start

    def build(self, persona: str, *, days: int = 1095, per_day: int = 8) -> PersonaTrajectory:
        rng = random.Random(f"{self._seed}:{persona}")
        label = self._LABELS[persona]
        obs: List[SearchDocument] = []
        gold: Dict[str, Tuple[str, ...]] = {}
        seq = 0
        for d in range(days):
            today = self._start + timedelta(days=d)
            for _ in range(per_day):
                seq += 1
                kind = self._DAILY_KINDS[seq % len(self._DAILY_KINDS)]
                oid = f"{persona}-obs-{seq:05d}"
                text = (
                    f"{label}第{d + 1}日{kind}记录："
                    f"负载指标{rng.randint(40, 95):02d}，"
                    f"协作文档{rng.randint(1, 3)}份，纬度{31 + rng.random():0.4f}"
                )
                obs.append(SearchDocument(
                    object_id=oid, kind="Observation",
                    title=f"{label}-{kind}-{today:%Y%m%d}",
                    text=text, dimension_slug=f"stream-{kind}", day_index=d,
                ))
        # ---- 黄金事件锚点（检索 100% 命中的基准事实） ----
        anchor_specs = [
            ("contract-breach", "Entity", "dim-法务违约",
             "老王合同违约：第612日收到违约告知函，老王单方撕毁对赌回购第4.2条并转移专利"),
            ("cardiac-alert", "Claim", "dim-体征早搏",
             "室性早搏预警：第700日动态心电图频报多源室性早搏，医嘱立即停工"),
            ("gift-need-knee", "Claim", "dim-家庭母亲",
             "母亲膝盖受凉：第350日两次提及夜间膝盖受凉酸胀"),
            ("court-judgment", "Annotation", "dim-法务判决",
             "法院判决回溯注记：老王名下民事判决进入恢复执行程序"),
        ]
        for family, kind, slug, text in anchor_specs:
            oid = f"{persona}-gold-{family}"
            obs.append(SearchDocument(object_id=oid, kind=kind,
                                      title=f"{label}黄金锚点-{family}",
                                      text=text, dimension_slug=slug, day_index=0))
            gold[family] = (oid,)
        advisor_evidence = self._build_advisor_evidence(persona)
        # 决策证据同样进入观测流（可检索、可审计）
        for family, items in advisor_evidence.items():
            for item in items:
                obs.append(SearchDocument(
                    object_id=item.ref.object_id, kind="Claim",
                    title=f"{label}决策证据-{family}-{item.ref.object_id}",
                    text=item.text, dimension_slug=f"evidence-{item.domain}", day_index=0,
                ))
        return PersonaTrajectory(
            persona=persona, persona_label=label, start=self._start,
            end=self._start + timedelta(days=days - 1),
            observations=tuple(obs), gold_families=gold,
            advisor_evidence=advisor_evidence,
        )

    @staticmethod
    def _build_advisor_evidence(persona: str) -> Dict[str, Tuple["AdvisorEvidence", ...]]:
        from aios_core.cognition.symbiotic_advisor_arena01 import AdvisorEvidence

        def ref(suffix: str) -> ObjectRef:
            return ObjectRef(object_id=f"{persona}-ev-{suffix}", revision=1)

        gift = (
            AdvisorEvidence(ref("gift-2023"), "gift_history", 2023,
                            "2023 母亲节送出真丝丝巾，已妥收，同品类再送无新意"),
            AdvisorEvidence(ref("gift-2024"), "gift_history", 2024,
                            "2024 足浴盆闲置堆灰：母亲倒水时闪了腰，抱怨占地方"),
            AdvisorEvidence(ref("gift-2025"), "gift_history", 2025,
                            "2025 按摩椅高频使用，连续好评，证实偏好直下热敷体感"),
            AdvisorEvidence(ref("gift-2026"), "gift_history", 2026,
                            "2026 入冬两次提及膝盖夜间受凉酸胀，晨练后加重"),
        )
        fraud = (
            AdvisorEvidence(ref("fraud-wechat"), "chat_wechat", 2024,
                            "两年前微信借条+转账截图：老王借款 6 万元承诺三个月归还，至今零清偿"),
            AdvisorEvidence(ref("fraud-judgment"), "judicial", 2025,
                            "法院民事判决书：老王多笔借款被判限期清偿仍拖延，案件已进执行程序"),
        )
        cardiac = (
            AdvisorEvidence(ref("cardiac-overtime"), "calendar", 2026,
                            "连续三日通宵加班：律所对赌交割 03:40 仍在批注合同"),
            AdvisorEvidence(ref("cardiac-holter"), "health", 2026,
                            "动态心电图频报室性早搏，心内科医嘱立即停工复查"),
        )
        return {"gift": gift, "fraud": fraud, "cardiac": cardiac}


@dataclass(frozen=True)
class ArenaDeckItem:
    item_id: str
    family: str        # 对应 PersonaTrajectory.gold_families 或 trivia/posture/advice 题组
    prompt: str
    kind: str          # search / posture / advice
    urgency: WakePriority = WakePriority.P2_NORMAL_INTERACT
    event_kind: str = "daily_chatter"
    expect_posture: Optional[str] = None
    advice_kind: Optional[str] = None  # gift / fraud / cardiac


@dataclass
class MindResult:
    token_cost: int = 0
    refs: Tuple[ObjectRef, ...] = ()
    posture: Optional[str] = None
    advice_verdict: Optional[str] = None
    llm_calls: int = 0
    history_mutations: int = 0


class MindPolicy:
    """进驻考场的 Agent 策略基类：四大心智动作要实现。"""

    name: str = "abstract"

    def search_mind(self, deck: ArenaDeckItem, distiller: OperationExperienceDistiller,
                    bus: MultidimensionalSearchBus) -> MindResult:  # pragma: no cover
        raise NotImplementedError

    def distill_dimension(self, deck: ArenaDeckItem) -> MindResult:
        return MindResult()

    def decide_posture(self, deck: ArenaDeckItem) -> MindResult:  # pragma: no cover
        raise NotImplementedError

    def advise_decision(self, deck: ArenaDeckItem) -> MindResult:  # pragma: no cover
        raise NotImplementedError


@dataclass
class ArenaRunResult:
    policy_name: str
    persona: str
    total_tokens: int = 0
    budget_usage: float = 0.0
    evidence_hit_rate: float = 0.0
    tact_score: float = 0.0
    llm_calls: int = 0
    history_mutations: int = 0
    constitution_ok: bool = True
    veto_reasons: Tuple[str, ...] = ()
    deck_summary: Tuple[str, ...] = ()


class ArenaReportStore:
    """《共生心智操作全景体检报告》经验库持久化（JSONL 只追加）。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def persist(self, result: ArenaRunResult) -> Path:
        blob = {
            "report": "《AIOS 3.0 共生心智操作全景体检报告》",
            "policy": result.policy_name,
            "persona": result.persona,
            "total_tokens": result.total_tokens,
            "budget_usage": result.budget_usage,
            "evidence_hit_rate": result.evidence_hit_rate,
            "tact_score": result.tact_score,
            "constitution_ok": result.constitution_ok,
            "veto_reasons": list(result.veto_reasons),
            "deck_summary": list(result.deck_summary),
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(blob, ensure_ascii=False) + "\n")
        return self._path


class AgentMindArena:
    """千人千面战训考场。"""

    def __init__(self, bus: MultidimensionalSearchBus,
                 distiller: OperationExperienceDistiller) -> None:
        self._bus = bus
        self._distiller = distiller

    # ------------------------------------------------------------------
    def build_deck(self, trajectory: PersonaTrajectory) -> Tuple[ArenaDeckItem, ...]:
        deck: List[ArenaDeckItem] = []
        for family in trajectory.gold_families:
            prompt_map = {
                "contract-breach": "老王 违约 对赌 回购",
                "cardiac-alert": "室性早搏 停工 医嘱",
                "gift-need-knee": "母亲 膝盖 受凉",
                "court-judgment": "判决 执行 老王",
            }
            deck.append(ArenaDeckItem(
                item_id=f"{trajectory.persona}-{family}", family=family,
                prompt=prompt_map[family], kind="search",
            ))
        deck.extend([
            ArenaDeckItem(f"{trajectory.persona}-trivia-weather", "trivia",
                          "天气八卦", "posture", WakePriority.P2_NORMAL_INTERACT,
                          "weather_gossip", "SILENCE"),
            ArenaDeckItem(f"{trajectory.persona}-fraud-loan", "fraud",
                          "老王再次开口借钱", "posture", WakePriority.P2_NORMAL_INTERACT,
                          "fraud_loan_alert", "CRITICAL_SPOKEN", "fraud"),
            ArenaDeckItem(f"{trajectory.persona}-cardiac-p0", "p0-cardiac",
                          "动态心电图捕获室性早搏", "posture", WakePriority.P0_CRITICAL_SAFETY,
                          "cardiac_arrhythmia", "CRITICAL_SPOKEN", "cardiac"),
            ArenaDeckItem(f"{trajectory.persona}-mom-gift", "gift",
                          "母亲生日送礼", "advice", WakePriority.P2_NORMAL_INTERACT,
                          "decision", None, "gift"),
        ])
        return tuple(deck)

    # ------------------------------------------------------------------
    def run(self, policy: MindPolicy, trajectory: PersonaTrajectory,
            *, warp_iters: int = 3) -> ArenaRunResult:
        binder = getattr(policy, "bind", None)
        if callable(binder):
            binder(trajectory)
        deck = self.build_deck(trajectory)
        total_tokens = 0
        llm_calls = 0
        mutations = 0
        hits = 0
        searches = 0
        tact_ok = 0
        tact_total = 0
        p0_llm_calls = 0
        summary: List[str] = []
        for _ in range(warp_iters):  # 同题多刷，供经验蒸馏成立
            for item in deck:
                if item.kind == "search":
                    out = policy.search_mind(item, self._distiller, self._bus)
                    total_tokens += out.token_cost
                    llm_calls += out.llm_calls
                    mutations += out.history_mutations
                    searches += 1
                    gold = set(trajectory.gold_families[item.family])
                    got = {r.object_id for r in out.refs}
                    if gold and gold.issubset(got):
                        hits += 1
                    summary.append(f"{item.family}:{'HIT' if gold.issubset(got) else 'MISS'}"
                                   f"/{out.token_cost}tok")
                elif item.kind == "posture":
                    out = policy.decide_posture(item)
                    total_tokens += out.token_cost
                    llm_calls += out.llm_calls
                    mutations += out.history_mutations
                    tact_total += 1
                    if item.urgency is WakePriority.P0_CRITICAL_SAFETY and out.llm_calls:
                        p0_llm_calls += out.llm_calls
                    if out.posture == item.expect_posture:
                        tact_ok += 1
                    summary.append(f"{item.family}:{out.posture}")
                elif item.kind == "advice":
                    out = policy.advise_decision(item)
                    total_tokens += out.token_cost
                    llm_calls += out.llm_calls
                    mutations += out.history_mutations
                    summary.append(f"{item.family}:{out.advice_verdict and '1' or '0'}")
        veto: List[str] = []
        if mutations > 0:
            veto.append("篡改历史一票否决：发生 history mutation")
        if p0_llm_calls > 0:
            veto.append("P0调用大模型一票否决：生死红线禁止 LLM 延迟")
        result = ArenaRunResult(
            policy_name=policy.name, persona=trajectory.persona,
            total_tokens=total_tokens,
            budget_usage=total_tokens / MONTHLY_TOKEN_BUDGET,
            evidence_hit_rate=(hits / searches) if searches else 0.0,
            tact_score=(tact_ok / tact_total * 100.0) if tact_total else 0.0,
            llm_calls=llm_calls, history_mutations=mutations,
            constitution_ok=not veto, veto_reasons=tuple(veto),
            deck_summary=tuple(summary),
        )
        return result
