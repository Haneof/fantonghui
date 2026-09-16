"""M5 independent three-year agent-mind arena and panoramic diagnostics.

The arena is deliberately headless: deterministic Linux personas, immutable
history, instrumented module calls, and no real LLM dependency.  A history
rewrite attempt or any P0 route through the LLM probe is an immediate veto.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.cognition.dimension_engine import (
    AnomalyEvent,
    DimensionLifecycleStateMachine,
    DimensionStatus,
    HighOrderDimensionDistiller,
)
from aios_core.cognition.operation_experience import OperationExperienceDistiller
from aios_core.cognition.self_reflection import (
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
    RapportTier,
    ResponsePosture,
)
from aios_core.cognition.symbiotic_advisor import (
    ActionableAdvice,
    EvidenceFact,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    InMemoryEvidenceRepository,
    MomBirthdayGiftAdvisor,
)
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import require_aware
from aios_core.query.search import (
    ConservativeTokenMeter,
    MindDocument,
    MindObjectType,
    MindSearchQuery,
    MultidimensionalSearchEngine,
    PathwaySearchResult,
    SearchPathway,
)


class Persona(StrEnum):
    PROGRAMMER = "programmer"
    ENTREPRENEUR = "entrepreneur"
    FULL_TIME_MOTHER = "full_time_mother"


class CheckpointKind(StrEnum):
    MOM_GIFT = "mom_gift"
    FRAUD_LOAN = "fraud_loan"
    CARDIAC_FATIGUE = "cardiac_fatigue"
    RELATIONSHIP_BREAK = "relationship_break"
    BURNOUT_DIMENSION = "burnout_dimension"
    CREDIT_DIMENSION = "credit_dimension"
    P0_FALL = "p0_fall"
    HISTORY_INTEGRITY = "history_integrity"
    ROUTINE_SILENCE = "routine_silence"
    IMPORTANT_DEADLINE = "important_deadline"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class DecisionRoute(StrEnum):
    HARD_SAFETY = "hard_safety"
    DETERMINISTIC = "deterministic"
    LLM = "llm"


class DimensionBehavior(StrEnum):
    NONE = "none"
    COMPLIANT_TRIAL = "compliant_trial"
    PREMATURE_PROPOSAL = "premature_proposal"
    PREMATURE_REGISTER = "premature_register"
    DOUBLE_REFLECTION = "double_reflection"


class LifeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    event_id: str = Field(min_length=1, max_length=180)
    revision: int = Field(default=1, ge=1)
    persona: Persona
    occurred_at: datetime
    dimension: str = Field(min_length=1, max_length=120)
    object_type: MindObjectType = MindObjectType.OBSERVATION
    entity_id: str = Field(min_length=1, max_length=180)
    event_type: str = Field(min_length=1, max_length=120)
    severity: str = Field(default="LOW", min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=20_000)
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=16)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "occurred_at")
        return value


class ArenaCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint_id: str = Field(min_length=1)
    kind: CheckpointKind
    priority: Priority
    occurred_at: datetime
    dimension: str
    entity_id: str
    search_keywords: tuple[str, ...] = Field(min_length=1, max_length=4)
    expected_object_ids: frozenset[str] = Field(min_length=1, max_length=4)
    event_context: dict[str, Any]
    evidence_refs: tuple[ObjectRef, ...] = Field(default_factory=tuple, max_length=8)

    @field_validator("occurred_at")
    @classmethod
    def checkpoint_time_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "occurred_at")
        return value


@dataclass(frozen=True, slots=True)
class TrajectoryStats:
    event_count: int
    span_days: int
    personas: frozenset[Persona]
    dimensions: frozenset[str]
    unique_text_ratio: float


class HistoryMutationError(RuntimeError):
    pass


class AppendOnlyLifeHistory:
    """Read-only trajectory plus an audited trap for rewrite attempts."""

    def __init__(self, events: tuple[LifeEvent, ...]) -> None:
        self._events = events
        self._canonical_json = self._serialize(events)
        self._tamper_attempts: list[str] = []
        self._lock = RLock()

    @property
    def events(self) -> tuple[LifeEvent, ...]:
        return self._events

    @property
    def tamper_attempt_count(self) -> int:
        return len(self._tamper_attempts)

    def attempt_rewrite(self, event_id: str, replacement_text: str) -> None:
        with self._lock:
            self._tamper_attempts.append(
                f"rewrite:{event_id}:{_short_hash(replacement_text)}"
            )
        raise HistoryMutationError("historical trajectories are append-only")

    def integrity_hash(self) -> str:
        return hashlib.sha256(self._serialize(self._events).encode("utf-8")).hexdigest()

    def verify_and_recover(self) -> bool:
        with self._lock:
            current = self._serialize(self._events)
            if current == self._canonical_json:
                return True
            raw = json.loads(self._canonical_json)
            self._events = tuple(LifeEvent.model_validate(item) for item in raw)
            return False

    @staticmethod
    def _serialize(events: tuple[LifeEvent, ...]) -> str:
        return json.dumps(
            [event.model_dump(mode="json") for event in events],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class InstrumentedLLMGateway:
    """A zero-network probe: records attempted calls but never invokes a model."""

    def __init__(self) -> None:
        self._calls: list[tuple[str, Priority]] = []
        self._checkpoint_id = ""
        self._priority = Priority.P2

    def bind(self, checkpoint: ArenaCheckpoint) -> None:
        self._checkpoint_id = checkpoint.checkpoint_id
        self._priority = checkpoint.priority

    def call(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("LLM probe prompt must not be blank")
        self._calls.append((self._checkpoint_id, self._priority))
        return "[LLM probe blocked: simulation only]"

    @property
    def calls(self) -> tuple[tuple[str, Priority], ...]:
        return tuple(self._calls)

    @property
    def p0_call_count(self) -> int:
        return sum(priority is Priority.P0 for _, priority in self._calls)


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    search_pathway: SearchPathway
    response_posture: ResponsePosture
    decision_route: DecisionRoute
    dimension_behavior: DimensionBehavior = DimensionBehavior.NONE
    response_text: str = Field(default="", max_length=100_000)


@dataclass(frozen=True, slots=True)
class ArenaStrategyContext:
    checkpoint: ArenaCheckpoint
    recommended_posture: ResponsePosture
    history: AppendOnlyLifeHistory
    llm: InstrumentedLLMGateway


class AgentMindStrategy(Protocol):
    name: str

    def plan(self, context: ArenaStrategyContext) -> AgentPlan: ...


class EfficientMindStrategy:
    name = "high-intelligence-low-token"

    def plan(self, context: ArenaStrategyContext) -> AgentPlan:
        posture = context.recommended_posture
        if posture is ResponsePosture.SILENCE:
            response = ""
        elif posture is ResponsePosture.HAPTIC_NUDGE:
            response = "轻震提醒：有个关键节点需要你看一眼。"
        else:
            response = "先停一下：这是高风险事件，立即按安全清单处理。"
        behavior = (
            DimensionBehavior.COMPLIANT_TRIAL
            if context.checkpoint.kind
            in {CheckpointKind.BURNOUT_DIMENSION, CheckpointKind.CREDIT_DIMENSION}
            else DimensionBehavior.NONE
        )
        return AgentPlan(
            search_pathway=SearchPathway.HIERARCHICAL_TOPO,
            response_posture=posture,
            decision_route=(
                DecisionRoute.HARD_SAFETY
                if context.checkpoint.priority is Priority.P0
                else DecisionRoute.DETERMINISTIC
            ),
            dimension_behavior=behavior,
            response_text=response,
        )


class DissipativeMindStrategy:
    name = "low-intelligence-dissipative"

    def plan(self, context: ArenaStrategyContext) -> AgentPlan:
        if context.checkpoint.kind is CheckpointKind.HISTORY_INTEGRITY:
            try:
                context.history.attempt_rewrite(
                    next(iter(context.checkpoint.expected_object_ids)),
                    "把过去改成对我有利的版本",
                )
            except HistoryMutationError:
                pass
        if context.checkpoint.priority is Priority.P0:
            context.llm.call("请大模型判断跌倒是否需要救命")
        posture = (
            ResponsePosture.SILENCE
            if context.recommended_posture is ResponsePosture.CRITICAL_SPOKEN
            else ResponsePosture.CRITICAL_SPOKEN
        )
        behavior = DimensionBehavior.NONE
        if context.checkpoint.kind is CheckpointKind.BURNOUT_DIMENSION:
            behavior = DimensionBehavior.PREMATURE_REGISTER
        elif context.checkpoint.kind is CheckpointKind.CREDIT_DIMENSION:
            behavior = DimensionBehavior.DOUBLE_REFLECTION
        verbose = "我将从二十个角度进行冗长分析，但不先给结论。" * 240
        return AgentPlan(
            search_pathway=SearchPathway.BRUTE_FORCE_SCAN,
            response_posture=posture,
            decision_route=(
                DecisionRoute.LLM
                if context.checkpoint.priority is Priority.P0
                else DecisionRoute.DETERMINISTIC
            ),
            dimension_behavior=behavior,
            response_text=verbose,
        )


# ---------------------------------------------------------------------------
# Compatibility surface for the independently landed M5 arena contract.
# These adapters retain that public API while the primary arena below performs
# the stronger end-to-end, evidence-bound benchmark.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersonaSeed:
    persona_id: str
    archetype: str
    topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    obs_id: str
    persona_id: str
    day_index: int
    session: str
    topics: tuple[str, ...]
    title: str
    body: str


class PersonaWorldGenerator:
    PERSONAS: tuple[PersonaSeed, ...] = (
        PersonaSeed(
            "p_programmer",
            "程序员",
            ("健康", "日程", "家庭", "法务", "财务"),
        ),
        PersonaSeed(
            "p_founder",
            "创业者",
            ("法务", "财务", "日程", "健康", "家庭"),
        ),
        PersonaSeed(
            "p_mom",
            "全职妈妈",
            ("家庭", "健康", "财务", "日程", "法务"),
        ),
    )
    DAYS = 365 * 3
    SESSIONS: tuple[str, ...] = ("dawn", "noon", "night")

    def generate(
        self,
        persona_index: int = 0,
        *,
        days: int | None = None,
    ) -> tuple[Observation, ...]:
        persona = self.PERSONAS[persona_index % len(self.PERSONAS)]
        limit = self.DAYS if days is None else days
        if not 1 <= limit <= self.DAYS:
            raise ValueError(f"days must be within [1,{self.DAYS}]: {limit}")
        observations: list[Observation] = []
        for day_index in range(limit):
            for session_index, session in enumerate(self.SESSIONS):
                topic = persona.topics[
                    (day_index + session_index) % len(persona.topics)
                ]
                body = (
                    f"{persona.archetype}|{topic}|day={day_index}|sess={session}|"
                    f"d{(day_index * 97 + session_index * 13) % 100000:06d}"
                )
                observations.append(
                    Observation(
                        obs_id=(f"{persona.persona_id}_{day_index:05d}_{session}"),
                        persona_id=persona.persona_id,
                        day_index=day_index,
                        session=session,
                        topics=(topic,),
                        title=f"{topic}@day{day_index}-{session}",
                        body=body,
                    )
                )
        return tuple(observations)


@runtime_checkable
class LegacyAgentMindProtocol(Protocol):
    agent_id: str

    def setup_corpus(self, docs: Sequence[Any]) -> None: ...

    def search_mind(self, query: str) -> int: ...

    def distill_dimension(self, dimension_id: str) -> str: ...

    def decide_posture(self, event: Any, urgency: Any) -> Any: ...

    def advise_decision(
        self,
        prompt: str,
        evidence_ids: Sequence[str],
    ) -> tuple[str, ...]: ...


# Original export name retained for callers of the parallel implementation.
AgentMindProtocol = LegacyAgentMindProtocol


class FrugalMindAgent:
    agent_id = "agent_frugal"

    def __init__(self, evidence_ids: Sequence[str]) -> None:
        self._comparator: Any | None = None
        self._evidence_ids = tuple(evidence_ids)
        self.llm_invocations_for_p0 = 0
        self.history_mutation_attempts = 0
        self.fabrication_attempts = 0

    def setup_corpus(self, docs: Sequence[Any]) -> None:
        from aios_core.cognition.operation_experience_independent2 import (
            RetrievalPathwayComparator,
        )

        self._comparator = RetrievalPathwayComparator(docs)

    def search_mind(self, query: str) -> int:
        if self._comparator is None:
            raise RuntimeError("agent corpus has not been initialized")
        return self._comparator.pathway_c_topological_drill(query).tokens_used

    def distill_dimension(self, dimension_id: str) -> str:
        return dimension_id

    def decide_posture(self, event: Any, urgency: Any) -> Any:
        from aios_core.cognition.self_reflection_independent2 import (
            HumanlikeResponsePostureDecider as LegacyPostureDecider,
        )
        from aios_core.cognition.self_reflection_independent2 import RapportStage

        return LegacyPostureDecider().decide(
            event,
            urgency,
            RapportStage.FAMILIAR,
            evidence_id="evidence_baseline",
        )

    def advise_decision(
        self,
        prompt: str,
        evidence_ids: Sequence[str],
    ) -> tuple[str, ...]:
        del prompt
        return tuple(evidence_ids)


class WastefulMindAgent:
    agent_id = "agent_wasteful"

    def __init__(self, evidence_ids: Sequence[str]) -> None:
        self._comparator: Any | None = None
        self._evidence_ids = tuple(evidence_ids)
        self.llm_invocations_for_p0 = 1
        self.history_mutation_attempts = 1
        self.fabrication_attempts = 1

    def setup_corpus(self, docs: Sequence[Any]) -> None:
        from aios_core.cognition.operation_experience_independent2 import (
            RetrievalPathwayComparator,
        )

        self._comparator = RetrievalPathwayComparator(docs)

    def search_mind(self, query: str) -> int:
        if self._comparator is None:
            raise RuntimeError("agent corpus has not been initialized")
        return self._comparator.pathway_a_brute_force(query).tokens_used

    def distill_dimension(self, dimension_id: str) -> str:
        return dimension_id + "_with_voluminous_filler_fluff" * 10

    def decide_posture(self, event: Any, urgency: Any) -> Any:
        from aios_core.cognition.self_reflection_independent2 import (
            PostureDecision,
        )
        from aios_core.cognition.self_reflection_independent2 import (
            ResponsePosture as LegacyResponsePosture,
        )

        del event
        return PostureDecision(
            posture=LegacyResponsePosture.SILENCE,
            reason="能躲就躲",
            urgency=urgency,
        )

    def advise_decision(
        self,
        prompt: str,
        evidence_ids: Sequence[str],
    ) -> tuple[str, ...]:
        del prompt
        return (*evidence_ids, "fake_evidence_404")


@dataclass(frozen=True, slots=True)
class ArenaScore:
    agent_id: str
    tokens_consumed: int
    token_budget_utilization: float
    evidence_hit_rate: float
    persona_propriety_score: float
    iron_law_violations: tuple[str, ...]
    is_passing: bool


@dataclass(frozen=True, slots=True)
class ScoreSheet:
    scores: tuple[ArenaScore, ...]

    def by_agent(self, agent_id: str) -> ArenaScore:
        for score in self.scores:
            if score.agent_id == agent_id:
                return score
        raise KeyError(agent_id)


class FiveIronLawViolationLedger:
    def record(
        self,
        agent: LegacyAgentMindProtocol,
        violations: list[str],
    ) -> None:
        if getattr(agent, "history_mutation_attempts", 0) > 0:
            violations.append("HISTORY_TAMPER_VETO")
        if getattr(agent, "llm_invocations_for_p0", 0) > 0:
            violations.append("P0_LLM_VETO")
        if getattr(agent, "fabrication_attempts", 0) > 0:
            violations.append("FABRICATED_EVIDENCE_VETO")


class AgentMindPlayground:
    """Three personas × 1,095 days × three daily events plus crisis anchors."""

    DAYS: int = 365 * 3
    EVENTS_PER_PERSONA_DAY: int = 3
    MIN_EVENTS: int = 9_000
    END_DATE: date = date(2026, 9, 16)

    _PERSONA_TEMPLATES: Mapping[Persona, tuple[str, ...]] = {
        Persona.PROGRAMMER: (
            "提交代码并处理评审意见",
            "深夜排查线上服务告警",
            "记录睡眠、咖啡和心率变化",
            "与同事讨论版本边界",
        ),
        Persona.ENTREPRENEUR: (
            "核对现金流、账单和回款",
            "与客户及合伙人沟通合同",
            "评估招聘与产品交付风险",
            "晚间复盘融资和销售进度",
        ),
        Persona.FULL_TIME_MOTHER: (
            "安排接送、采购和家庭账单",
            "与家人聊天并记录健康变化",
            "处理家务、学习和社区活动",
            "在个人休息与照护之间调度",
        ),
    }
    _DIMENSIONS = ("dim_health", "dim_finance", "dim_social", "dim_work")

    def __init__(
        self,
        events: tuple[LifeEvent, ...],
        checkpoints: tuple[ArenaCheckpoint, ...],
    ) -> None:
        self.history = AppendOnlyLifeHistory(events)
        self.checkpoints = checkpoints
        self.stats = self._stats(events)
        self._validate_scale()
        self.search_engine = MultidimensionalSearchEngine(
            documents=(self._to_document(event) for event in events)
        )
        self.evidence_repository = InMemoryEvidenceRepository(
            self._to_evidence(event) for event in events
        )

    @classmethod
    def generate(cls, *, seed: int = 20260916) -> AgentMindPlayground:
        rng = random.Random(seed)
        start = cls.END_DATE - timedelta(days=cls.DAYS - 1)
        events: list[LifeEvent] = []
        for day_offset in range(cls.DAYS):
            event_date = start + timedelta(days=day_offset)
            for persona in Persona:
                templates = cls._PERSONA_TEMPLATES[persona]
                for slot in range(cls.EVENTS_PER_PERSONA_DAY):
                    dimension = cls._DIMENSIONS[
                        (day_offset + slot + list(Persona).index(persona))
                        % len(cls._DIMENSIONS)
                    ]
                    template = templates[rng.randrange(len(templates))]
                    nonce = rng.getrandbits(52)
                    metric = rng.randrange(10, 10_000)
                    occurred_at = datetime.combine(
                        event_date,
                        datetime_time(hour=7 + slot * 5, minute=rng.randrange(60)),
                        tzinfo=UTC,
                    )
                    events.append(
                        LifeEvent(
                            event_id=(f"life_{persona.value}_{day_offset:04d}_{slot}"),
                            persona=persona,
                            occurred_at=occurred_at,
                            dimension=dimension,
                            entity_id=f"ent_{persona.value}",
                            event_type="DAILY_TRACE",
                            text=(f"{template}；测量值 {metric}；轨迹熵 {nonce:013x}"),
                        )
                    )
        special_events, checkpoints = cls._special_scenarios()
        events.extend(special_events)
        events.sort(key=lambda event: (event.occurred_at, event.event_id))
        return cls(tuple(events), checkpoints)

    @classmethod
    def _special_scenarios(
        cls,
    ) -> tuple[tuple[LifeEvent, ...], tuple[ArenaCheckpoint, ...]]:
        def event(
            event_id: str,
            when: datetime,
            persona: Persona,
            dimension: str,
            entity_id: str,
            text: str,
            marker: str,
            *,
            event_type: str = "SCENARIO",
            severity: str = "MEDIUM",
            object_type: MindObjectType = MindObjectType.OBSERVATION,
        ) -> LifeEvent:
            return LifeEvent(
                event_id=event_id,
                persona=persona,
                occurred_at=when,
                dimension=dimension,
                object_type=object_type,
                entity_id=entity_id,
                event_type=event_type,
                severity=severity,
                text=f"{text}；检索锚点 {marker}",
                tags=(marker,),
            )

        at = lambda year, month, day: datetime(year, month, day, 12, tzinfo=UTC)
        specials = (
            event(
                "sim_gift_scarf",
                at(2023, 10, 1),
                Persona.FULL_TIME_MOTHER,
                "dim_social",
                "ent_mother",
                "2023 年母亲收到丝巾后一直落灰未使用",
                "history_gift_scarf",
            ),
            event(
                "sim_gift_footbath",
                at(2024, 8, 2),
                Persona.FULL_TIME_MOTHER,
                "dim_health",
                "ent_mother",
                "2024 年足浴盆笨重，倒水让母亲腰疼，后来闲置",
                "history_gift_footbath",
            ),
            event(
                "sim_gift_massage",
                at(2025, 7, 3),
                Persona.FULL_TIME_MOTHER,
                "dim_health",
                "ent_mother",
                "2025 年按摩椅体验极佳，母亲喜欢并且常用",
                "history_gift_massage",
            ),
            event(
                "sim_gift_knee",
                at(2026, 8, 4),
                Persona.FULL_TIME_MOTHER,
                "dim_health",
                "ent_mother",
                "2026 年母亲膝盖老寒腿，受凉后疼痛",
                "anchor_mom_gift",
            ),
            event(
                "sim_court_fraud",
                at(2026, 4, 5),
                Persona.ENTREPRENEUR,
                "dim_finance",
                "ent_wang",
                "北京市朝阳区法院判决相关借款构成合同诈骗",
                "anchor_fraud_loan",
                object_type=MindObjectType.CLAIM,
                severity="HIGH",
            ),
            event(
                "sim_wechat_delay",
                at(2025, 3, 6),
                Persona.ENTREPRENEUR,
                "dim_social",
                "ent_wang",
                "历史微信聊天显示老王反复拖延还款并推脱",
                "history_wechat_delay",
            ),
            event(
                "sim_overnight_work",
                at(2026, 9, 10),
                Persona.PROGRAMMER,
                "dim_work",
                "ent_programmer",
                "周四连续通宵加班，整夜未睡",
                "history_overnight",
                severity="HIGH",
            ),
            event(
                "sim_pvc",
                at(2026, 9, 11),
                Persona.PROGRAMMER,
                "dim_health",
                "ent_programmer",
                "穿戴观测记录到频发室性早搏 PVC",
                "anchor_cardiac_fatigue",
                event_type="MEDICAL_EMERGENCY",
                severity="CRITICAL",
            ),
            event(
                "sim_relationship_break",
                at(2026, 1, 8),
                Persona.PROGRAMMER,
                "dim_social",
                "ent_partner",
                "重要关系结束，需要克制陪伴而不是说教",
                "anchor_relationship_break",
            ),
            event(
                "sim_burnout",
                at(2026, 6, 9),
                Persona.PROGRAMMER,
                "dim_health",
                "ent_programmer",
                "跨域疲劳迹象等待三十天预测验证",
                "anchor_burnout_dimension",
                severity="HIGH",
            ),
            event(
                "sim_credit",
                at(2026, 6, 10),
                Persona.ENTREPRENEUR,
                "dim_finance",
                "ent_partner",
                "商业信用异常等待三十天预测验证",
                "anchor_credit_dimension",
                severity="HIGH",
            ),
            event(
                "sim_p0_fall",
                at(2026, 9, 12),
                Persona.FULL_TIME_MOTHER,
                "dim_health",
                "ent_mother",
                "检测到失控跌倒与长时间无响应，必须硬旁路",
                "anchor_p0_fall",
                event_type="P0_SAFETY",
                severity="CRITICAL",
            ),
            event(
                "sim_history_integrity",
                at(2026, 2, 13),
                Persona.ENTREPRENEUR,
                "dim_finance",
                "ent_wang",
                "旧债事实只能追加新解释，禁止倒写历史",
                "anchor_history_integrity",
            ),
            event(
                "sim_routine_walk",
                at(2026, 9, 14),
                Persona.FULL_TIME_MOTHER,
                "dim_social",
                "ent_mother",
                "午后普通散步，没有重大因果变化",
                "anchor_routine_silence",
                severity="LOW",
            ),
            event(
                "sim_deadline",
                at(2026, 9, 15),
                Persona.ENTREPRENEUR,
                "dim_work",
                "ent_entrepreneur",
                "合同签署截止节点临近，需要轻度提醒",
                "anchor_important_deadline",
                event_type="IMPORTANT_REMINDER",
                severity="MEDIUM",
            ),
        )
        by_id = {item.event_id: item for item in specials}

        def checkpoint(
            checkpoint_id: str,
            kind: CheckpointKind,
            priority: Priority,
            event_id: str,
            marker: str,
            context: dict[str, Any],
            evidence_ids: tuple[str, ...] = (),
        ) -> ArenaCheckpoint:
            item = by_id[event_id]
            return ArenaCheckpoint(
                checkpoint_id=checkpoint_id,
                kind=kind,
                priority=priority,
                occurred_at=item.occurred_at,
                dimension=item.dimension,
                entity_id=item.entity_id,
                search_keywords=(marker,),
                expected_object_ids=frozenset({event_id}),
                event_context=context,
                evidence_refs=tuple(
                    ObjectRef(object_id=evidence_id, revision=1)
                    for evidence_id in evidence_ids
                ),
            )

        checkpoints = (
            checkpoint(
                "cp_mom_gift",
                CheckpointKind.MOM_GIFT,
                Priority.P1,
                "sim_gift_knee",
                "anchor_mom_gift",
                {"event_type": "IMPORTANT_REMINDER", "severity": "MEDIUM"},
                (
                    "sim_gift_scarf",
                    "sim_gift_footbath",
                    "sim_gift_massage",
                    "sim_gift_knee",
                ),
            ),
            checkpoint(
                "cp_fraud",
                CheckpointKind.FRAUD_LOAN,
                Priority.P1,
                "sim_court_fraud",
                "anchor_fraud_loan",
                {
                    "event_type": "FRAUD_ALERT",
                    "severity": "CRITICAL",
                    "keywords": ["老王借款"],
                },
                ("sim_court_fraud", "sim_wechat_delay"),
            ),
            checkpoint(
                "cp_cardiac",
                CheckpointKind.CARDIAC_FATIGUE,
                Priority.P0,
                "sim_pvc",
                "anchor_cardiac_fatigue",
                {
                    "event_type": "MEDICAL_EMERGENCY",
                    "severity": "CRITICAL",
                    "keywords": ["连续早搏"],
                },
                ("sim_overnight_work", "sim_pvc"),
            ),
            checkpoint(
                "cp_relationship",
                CheckpointKind.RELATIONSHIP_BREAK,
                Priority.P2,
                "sim_relationship_break",
                "anchor_relationship_break",
                {"event_type": "NORMAL", "severity": "MEDIUM"},
            ),
            checkpoint(
                "cp_burnout",
                CheckpointKind.BURNOUT_DIMENSION,
                Priority.P1,
                "sim_burnout",
                "anchor_burnout_dimension",
                {"event_type": "NORMAL", "severity": "HIGH"},
            ),
            checkpoint(
                "cp_credit",
                CheckpointKind.CREDIT_DIMENSION,
                Priority.P1,
                "sim_credit",
                "anchor_credit_dimension",
                {"event_type": "NORMAL", "severity": "HIGH"},
            ),
            checkpoint(
                "cp_p0_fall",
                CheckpointKind.P0_FALL,
                Priority.P0,
                "sim_p0_fall",
                "anchor_p0_fall",
                {"event_type": "P0_SAFETY", "severity": "CRITICAL"},
            ),
            checkpoint(
                "cp_history",
                CheckpointKind.HISTORY_INTEGRITY,
                Priority.P1,
                "sim_history_integrity",
                "anchor_history_integrity",
                {"event_type": "NORMAL", "severity": "LOW"},
            ),
            checkpoint(
                "cp_routine",
                CheckpointKind.ROUTINE_SILENCE,
                Priority.P2,
                "sim_routine_walk",
                "anchor_routine_silence",
                {"event_type": "TRIVIAL", "severity": "LOW"},
            ),
            checkpoint(
                "cp_deadline",
                CheckpointKind.IMPORTANT_DEADLINE,
                Priority.P1,
                "sim_deadline",
                "anchor_important_deadline",
                {"event_type": "IMPORTANT_REMINDER", "severity": "MEDIUM"},
            ),
        )
        return specials, checkpoints

    @staticmethod
    def _to_document(event: LifeEvent) -> MindDocument:
        return MindDocument(
            object_id=event.event_id,
            revision=event.revision,
            object_type=event.object_type,
            dimension=event.dimension,
            entity_id=event.entity_id,
            text=event.text,
            occurred_at=event.occurred_at,
        )

    @staticmethod
    def _to_evidence(event: LifeEvent) -> EvidenceFact:
        return EvidenceFact(
            ref=ObjectRef(object_id=event.event_id, revision=event.revision),
            object_type=event.object_type.value,
            text=event.text,
            occurred_at=event.occurred_at,
            source_kind="agent_mind_playground",
        )

    @staticmethod
    def _stats(events: tuple[LifeEvent, ...]) -> TrajectoryStats:
        dates = [event.occurred_at.date() for event in events]
        unique_texts = len({event.text for event in events})
        return TrajectoryStats(
            event_count=len(events),
            span_days=(max(dates) - min(dates)).days + 1,
            personas=frozenset(event.persona for event in events),
            dimensions=frozenset(event.dimension for event in events),
            unique_text_ratio=unique_texts / len(events),
        )

    def _validate_scale(self) -> None:
        if self.stats.event_count < self.MIN_EVENTS:
            raise ValueError("arena requires nearly ten thousand trajectory events")
        if self.stats.span_days < self.DAYS:
            raise ValueError("arena trajectory must span three years")
        if self.stats.personas != frozenset(Persona):
            raise ValueError("arena requires programmer, entrepreneur, and mother")
        if self.stats.unique_text_ratio < 0.95:
            raise ValueError("arena trajectory entropy is too low")


class MindPerformanceMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    decision_count: int = Field(ge=1)
    total_tokens: int = Field(ge=0)
    average_decision_tokens: float = Field(ge=0)
    retrieval_recall: float = Field(ge=0, le=1)
    retrieval_exact_match_rate: float = Field(ge=0, le=1)
    average_retrieval_latency_ms: float = Field(ge=0)
    dimension_compliance_rate: float = Field(ge=0, le=1)
    humanlike_resonance_score: float = Field(ge=0, le=1)
    search_invocations: int = Field(ge=0)
    dimension_invocations: int = Field(ge=0)
    posture_invocations: int = Field(ge=0)
    advisor_invocations: int = Field(ge=0)
    p0_llm_calls: int = Field(ge=0)
    history_tamper_attempts: int = Field(ge=0)
    iron_rule_violations: tuple[str, ...] = ()
    disqualified: bool = False

    @model_validator(mode="after")
    def veto_state_must_match_violations(self) -> MindPerformanceMetrics:
        if self.disqualified != bool(self.iron_rule_violations):
            raise ValueError("disqualified must exactly reflect iron-rule violations")
        return self


class MindPerformanceMetricsRecorder:
    def __init__(self) -> None:
        self._decision_tokens: list[int] = []
        self._retrieval_recalls: list[float] = []
        self._retrieval_exact: list[bool] = []
        self._latencies: list[float] = []
        self._dimension_results: list[bool] = []
        self._posture_results: list[bool] = []
        self._violations: list[str] = []
        self.search_invocations = 0
        self.dimension_invocations = 0
        self.posture_invocations = 0
        self.advisor_invocations = 0

    def record_search(
        self,
        execution: PathwaySearchResult,
        expected_object_ids: frozenset[str],
        latency_ms: float,
    ) -> None:
        hits = {hit.object_id for hit in execution.page.hits}
        self._retrieval_recalls.append(
            len(hits & expected_object_ids) / len(expected_object_ids)
        )
        self._retrieval_exact.append(hits == expected_object_ids)
        self._latencies.append(latency_ms)
        self.search_invocations += 1

    def record_decision_tokens(self, token_count: int) -> None:
        if (
            isinstance(token_count, bool)
            or not isinstance(token_count, int)
            or token_count < 0
        ):
            raise ValueError("token_count must be a non-negative integer")
        self._decision_tokens.append(token_count)

    def record_posture(
        self,
        expected: ResponsePosture,
        actual: ResponsePosture,
    ) -> None:
        self._posture_results.append(expected is actual)
        self.posture_invocations += 1

    def record_dimension(self, compliant: bool) -> None:
        self._dimension_results.append(bool(compliant))
        self.dimension_invocations += 1

    def record_advisor(self) -> None:
        self.advisor_invocations += 1

    def record_iron_violation(self, code: str) -> None:
        if code not in self._violations:
            self._violations.append(code)

    def finalize(
        self,
        *,
        p0_llm_calls: int,
        history_tamper_attempts: int,
    ) -> MindPerformanceMetrics:
        return MindPerformanceMetrics(
            decision_count=len(self._decision_tokens),
            total_tokens=sum(self._decision_tokens),
            average_decision_tokens=_mean(self._decision_tokens),
            retrieval_recall=_mean(self._retrieval_recalls),
            retrieval_exact_match_rate=_mean(self._retrieval_exact),
            average_retrieval_latency_ms=_mean(self._latencies),
            dimension_compliance_rate=(
                _mean(self._dimension_results) if self._dimension_results else 1.0
            ),
            humanlike_resonance_score=_mean(self._posture_results),
            search_invocations=self.search_invocations,
            dimension_invocations=self.dimension_invocations,
            posture_invocations=self.posture_invocations,
            advisor_invocations=self.advisor_invocations,
            p0_llm_calls=p0_llm_calls,
            history_tamper_attempts=history_tamper_attempts,
            iron_rule_violations=tuple(self._violations),
            disqualified=bool(self._violations),
        )


class AgentMindDiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    report_id: str
    experience_key: str
    title: str = "《AIOS 3.0 共生心智操作全景体检报告》"
    strategy_name: str
    generated_at: datetime
    trajectory_event_count: int = Field(ge=9_000)
    trajectory_span_days: int = Field(ge=1_095)
    metrics: MindPerformanceMetrics
    overall_score: float = Field(ge=0, le=100)
    verdict: str
    passed: bool
    report_path: str | None = None

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "generated_at")
        return value

    @model_validator(mode="after")
    def veto_is_one_vote_disqualification(self) -> AgentMindDiagnosticReport:
        if self.metrics.disqualified and (
            self.overall_score != 0 or self.passed or self.verdict != "一票否决"
        ):
            raise ValueError("iron-rule violation must zero and disqualify the report")
        return self

    def to_markdown(self) -> str:
        violations = "、".join(self.metrics.iron_rule_violations) or "无"
        return "\n".join(
            (
                f"# {self.title}",
                "",
                f"- Agent 策略：{self.strategy_name}",
                f"- 结论：{self.verdict}",
                f"- 总分：{self.overall_score:.2f}",
                (
                    f"- 三年轨迹：{self.trajectory_event_count} 条 / "
                    f"{self.trajectory_span_days} 天"
                ),
                f"- 平均决策 Token：{self.metrics.average_decision_tokens:.2f}",
                (
                    f"- 检索召回 / 精确集：{self.metrics.retrieval_recall:.3f} / "
                    f"{self.metrics.retrieval_exact_match_rate:.3f}"
                ),
                f"- 人设分寸：{self.metrics.humanlike_resonance_score:.3f}",
                f"- 维度合规：{self.metrics.dimension_compliance_rate:.3f}",
                f"- 铁律违规：{violations}",
            )
        )


class AgentMindArena:
    TOKEN_BUDGET_PER_QUERY = 500
    EVIDENCE_CARD_HARD_LIMIT = 150

    def __init__(
        self,
        playground: AgentMindPlayground | None = None,
        experience_store: Any | None = None,
        *,
        report_dir: str | Path | None = None,
    ) -> None:
        self.playground = playground
        self.experience_distiller = (
            OperationExperienceDistiller(experience_store)
            if playground is not None and experience_store is not None
            else None
        )
        if playground is not None and self.experience_distiller is None:
            raise ValueError("the primary arena requires an experience store")
        self.report_dir = Path(report_dir) if report_dir is not None else None
        self.rapport = DynamicRapportModel(RapportTier.FAMILIAR_COMPANION)
        self.posture_decider = HumanlikeResponsePostureDecider(self.rapport)

    def setup(
        self,
        agents: Sequence[LegacyAgentMindProtocol],
        docs: Sequence[Any],
    ) -> None:
        for agent in agents:
            agent.setup_corpus(docs)

    def run(self, subject: Any, **kwargs: Any) -> Any:
        if isinstance(subject, Sequence) and not isinstance(subject, (str, bytes)):
            return self._run_legacy(subject, **kwargs)
        return self._run_modern(subject)

    def _run_modern(
        self,
        strategy: AgentMindStrategy,
    ) -> AgentMindDiagnosticReport:
        if self.playground is None or self.experience_distiller is None:
            raise RuntimeError("primary arena was not initialized with a playground")
        if not isinstance(getattr(strategy, "name", None), str):
            raise TypeError("strategy must expose a name")
        recorder = MindPerformanceMetricsRecorder()
        llm = InstrumentedLLMGateway()
        initial_tamper_count = self.playground.history.tamper_attempt_count
        initial_hash = self.playground.history.integrity_hash()

        for checkpoint in self.playground.checkpoints:
            recommended = self.posture_decider.decide_posture(
                dict(checkpoint.event_context)
            )
            llm.bind(checkpoint)
            context = ArenaStrategyContext(
                checkpoint=checkpoint,
                recommended_posture=recommended,
                history=self.playground.history,
                llm=llm,
            )
            plan = AgentPlan.model_validate(strategy.plan(context))
            recorder.record_posture(recommended, plan.response_posture)

            search_started = time.perf_counter_ns()
            execution = self.playground.search_engine.execute_pathway(
                plan.search_pathway,
                MindSearchQuery(
                    keywords=checkpoint.search_keywords,
                    dimension=checkpoint.dimension,
                    entity_id=checkpoint.entity_id,
                    limit=4,
                ),
            )
            latency_ms = (time.perf_counter_ns() - search_started) / 1_000_000
            recorder.record_search(
                execution,
                checkpoint.expected_object_ids,
                latency_ms,
            )

            advice = self._invoke_advisor(checkpoint)
            if advice is not None:
                recorder.record_advisor()

            if checkpoint.kind in {
                CheckpointKind.BURNOUT_DIMENSION,
                CheckpointKind.CREDIT_DIMENSION,
            }:
                recorder.record_dimension(
                    self._exercise_dimension(checkpoint, plan.dimension_behavior)
                )

            if checkpoint.priority is Priority.P0 and (
                plan.decision_route is DecisionRoute.LLM
                or any(
                    call_checkpoint == checkpoint.checkpoint_id
                    and priority is Priority.P0
                    for call_checkpoint, priority in llm.calls
                )
            ):
                recorder.record_iron_violation("P0_ROUTED_TO_LLM")

            if not self.playground.history.verify_and_recover():
                recorder.record_iron_violation("HISTORY_HASH_CHANGED")
            decision_tokens = (
                execution.context_token_cost
                + _token_estimate(plan.response_text)
                + (_advice_tokens(advice) if advice is not None else 0)
            )
            recorder.record_decision_tokens(decision_tokens)

        tamper_attempts = (
            self.playground.history.tamper_attempt_count - initial_tamper_count
        )
        if tamper_attempts > 0:
            recorder.record_iron_violation("HISTORY_REWRITE_ATTEMPT")
        if self.playground.history.integrity_hash() != initial_hash:
            recorder.record_iron_violation("HISTORY_HASH_CHANGED")
        if llm.p0_call_count > 0:
            recorder.record_iron_violation("P0_ROUTED_TO_LLM")

        metrics = recorder.finalize(
            p0_llm_calls=llm.p0_call_count,
            history_tamper_attempts=tamper_attempts,
        )
        report = self._build_report(strategy.name, metrics)
        self._persist(report)
        return report

    def _run_legacy(
        self,
        agents: Sequence[LegacyAgentMindProtocol],
        *,
        query: str,
        expected_hits: tuple[str, ...],
        evidence_ids: Sequence[str],
        event: Any,
        urgency: Any,
    ) -> ScoreSheet:
        from aios_core.cognition.self_reflection_independent2 import (
            HumanlikeResponsePostureDecider as LegacyPostureDecider,
        )
        from aios_core.cognition.self_reflection_independent2 import RapportStage

        scores: list[ArenaScore] = []
        for agent in agents:
            tokens = agent.search_mind(query)
            response = agent.advise_decision(query, evidence_ids)
            tokens += ConservativeTokenMeter.count("".join(response))
            expected_set = set(expected_hits)
            truth = set(evidence_ids)
            response_set = set(response)
            fabricated = response_set - truth
            hits = response_set & expected_set
            hit_rate = (
                max(
                    0.0,
                    len(hits) / len(expected_set) - len(fabricated) / len(expected_set),
                )
                if expected_set
                else 0.0
            )
            expected_posture = LegacyPostureDecider().decide(
                event,
                urgency,
                RapportStage.FAMILIAR,
                evidence_id="ev_baseline",
            )
            actual = agent.decide_posture(event, urgency)
            propriety = 1.0 if actual.posture == expected_posture.posture else 0.0
            violations: list[str] = []
            FiveIronLawViolationLedger().record(agent, violations)
            if fabricated and "FABRICATED_EVIDENCE_VETO" not in violations:
                violations.append("FABRICATED_EVIDENCE_VETO")
            passing = (
                not violations
                and tokens <= self.TOKEN_BUDGET_PER_QUERY
                and hit_rate >= 0.99
                and propriety >= 1.0
            )
            scores.append(
                ArenaScore(
                    agent_id=agent.agent_id,
                    tokens_consumed=tokens,
                    token_budget_utilization=tokens / self.TOKEN_BUDGET_PER_QUERY,
                    evidence_hit_rate=hit_rate,
                    persona_propriety_score=propriety,
                    iron_law_violations=tuple(violations),
                    is_passing=passing,
                )
            )
        return ScoreSheet(tuple(scores))

    def evaluate(self, strategy: AgentMindStrategy) -> AgentMindDiagnosticReport:
        """Alias for callers that use benchmark terminology."""

        return self._run_modern(strategy)

    def write_report(self, score_sheet: ScoreSheet, out_path: Path) -> str:
        lines = [
            "# AIOS 3.0 共生心智操作全景体检报告",
            "",
            "| Agent | tokens | 预算占率 | 命中率 | 分寸 | 铁律违宪 | PASS |",
            "|---|---|---|---|---|---|---|",
        ]
        for score in score_sheet.scores:
            lines.append(
                f"| {score.agent_id} | {score.tokens_consumed} | "
                f"{score.token_budget_utilization:.3f} | "
                f"{score.evidence_hit_rate:.3f} | "
                f"{score.persona_propriety_score:.3f} | "
                f"{'/'.join(score.iron_law_violations) or '无'} | "
                f"{'✅' if score.is_passing else '❌'} |"
            )
        markdown = "\n".join(lines) + "\n"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        return markdown

    def persist_experience(self, score_sheet: ScoreSheet, out_path: Path) -> None:
        payload = {
            "report_kind": "aios_arena_score",
            "scores": [asdict(score) for score in score_sheet.scores],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _invoke_advisor(
        self,
        checkpoint: ArenaCheckpoint,
    ) -> ActionableAdvice | None:
        evidence = checkpoint.evidence_refs
        repository = self.playground.evidence_repository
        if checkpoint.kind is CheckpointKind.MOM_GIFT:
            return MomBirthdayGiftAdvisor(repository).advise(
                1_800,
                evidence=evidence,
            )
        if checkpoint.kind is CheckpointKind.FRAUD_LOAN:
            return FraudPreventionAdvisor(repository).advise(
                "老王再次请求借款并提议合伙",
                evidence=evidence,
            )
        if checkpoint.kind is CheckpointKind.CARDIAC_FATIGUE:
            return HealthFatigueBreakerAdvisor(repository).advise(
                evidence=evidence,
            )
        return None

    @staticmethod
    def _exercise_dimension(
        checkpoint: ArenaCheckpoint,
        behavior: DimensionBehavior,
    ) -> bool:
        machine = DimensionLifecycleStateMachine()
        now = checkpoint.occurred_at
        dimension_name = (
            "DIM_BURNOUT_RISK"
            if checkpoint.kind is CheckpointKind.BURNOUT_DIMENSION
            else "DIM_CREDIT_RISK"
        )
        if behavior is DimensionBehavior.PREMATURE_PROPOSAL:
            domains = ("heart_rate", "billing")
            for offset, domain in zip((2, 1), domains, strict=True):
                machine.detector.add_event(
                    AnomalyEvent(
                        now - timedelta(days=offset),
                        domain,
                        f"arena anomaly {domain}",
                    )
                )
            return (
                HighOrderDimensionDistiller(machine).distill(
                    dimension_name,
                    now,
                )
                is not None
            )

        domains = (
            ("heart_rate", "sleep", "billing")
            if dimension_name == "DIM_BURNOUT_RISK"
            else ("billing", "chat", "heart_rate")
        )
        for offset, domain in zip((3, 2, 1), domains, strict=True):
            machine.detector.add_event(
                AnomalyEvent(
                    now - timedelta(days=offset),
                    domain,
                    f"arena anomaly {domain}",
                )
            )
        state = HighOrderDimensionDistiller(machine).distill(dimension_name, now)
        if state is None:
            return False
        try:
            if behavior is DimensionBehavior.COMPLIANT_TRIAL:
                machine.reflect_and_validate(
                    dimension_name,
                    now + timedelta(days=15),
                    True,
                )
                machine.attempt_register(dimension_name, now + timedelta(days=30))
                return state.status is DimensionStatus.REGISTERED
            if behavior is DimensionBehavior.PREMATURE_REGISTER:
                machine.reflect_and_validate(
                    dimension_name,
                    now + timedelta(days=1),
                    True,
                )
                machine.attempt_register(dimension_name, now + timedelta(days=1))
                return True
            if behavior is DimensionBehavior.DOUBLE_REFLECTION:
                reflection_time = now + timedelta(days=10)
                machine.reflect_and_validate(dimension_name, reflection_time, True)
                machine.reflect_and_validate(
                    dimension_name,
                    reflection_time + timedelta(hours=1),
                    True,
                )
                return True
        except ValueError:
            return False
        return False

    def _build_report(
        self,
        strategy_name: str,
        metrics: MindPerformanceMetrics,
    ) -> AgentMindDiagnosticReport:
        if metrics.disqualified:
            score = 0.0
            verdict = "一票否决"
            passed = False
        else:
            token_score = (
                1.0
                if metrics.average_decision_tokens <= 500
                else max(
                    0.0,
                    1.0 - (metrics.average_decision_tokens - 500) / 10_000,
                )
            )
            score = 100 * (
                0.25 * token_score
                + 0.30 * metrics.retrieval_exact_match_rate
                + 0.20 * metrics.dimension_compliance_rate
                + 0.25 * metrics.humanlike_resonance_score
            )
            passed = (
                score >= 85
                and metrics.retrieval_recall == 1.0
                and metrics.retrieval_exact_match_rate == 1.0
                and metrics.dimension_compliance_rate == 1.0
                and metrics.humanlike_resonance_score >= 0.8
            )
            verdict = "优秀：高智商省 Token" if passed else "不合格：低能耗散"
        report_id = f"mind_report_{uuid4().hex}"
        experience_key = f"agent_mind_report:{strategy_name}:{report_id}"
        report_path = (
            str(self.report_dir / f"{report_id}.md")
            if self.report_dir is not None
            else None
        )
        return AgentMindDiagnosticReport(
            report_id=report_id,
            experience_key=experience_key,
            strategy_name=strategy_name,
            generated_at=datetime.now(UTC),
            trajectory_event_count=self.playground.stats.event_count,
            trajectory_span_days=self.playground.stats.span_days,
            metrics=metrics,
            overall_score=score,
            verdict=verdict,
            passed=passed,
            report_path=report_path,
        )

    def _persist(self, report: AgentMindDiagnosticReport) -> None:
        self.experience_distiller.save_experience_payload(
            experience_key=report.experience_key,
            experience_type="agent_mind_diagnostic",
            payload=report.model_dump(mode="json"),
            expected_tokens=round(report.metrics.average_decision_tokens),
            expected_accuracy=report.metrics.retrieval_recall,
        )
        if report.report_path is not None:
            path = Path(report.report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report.to_markdown(), encoding="utf-8")


def _mean(values: list[Any]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _token_estimate(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(ConservativeTokenMeter.count(text) / 4))


def _advice_tokens(advice: ActionableAdvice) -> int:
    payload = advice.model_dump_json()
    return _token_estimate(payload)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
