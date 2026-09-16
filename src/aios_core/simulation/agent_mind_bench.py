"""M5-005（Agent-10）：千人千面 Agent 心智竞技场 AgentMindBench。

老大总纲：M5 五张工单机制的最终合练场——每个 Agent 独立面对一段完整虚拟人生
（3 年近万条事件流的缩放版），各自按自己的检索策略 / 姿态分寸 / 反思纪律 /
建议证据链运转，竞技场用同一把尺量出谁的机制最快、最准、最省 Token。

组成：
- ThousandFacesLifeFactory：千人千面多维世界发生器。同一种子确定性生成，
  每个 persona（程序员 / 创业者 / 全职妈妈）有各自的人生锚实体、隐性因果事实、
  十个危机剧本（含老王案今日重解释注记）与风险域连续异常链。
- AgentMindArena：Agent 不 mock 任何环节——检索走主干 WorldSearchIndex 真索引，
  姿态走 HumanlikeResponsePostureDeciderV2，反思走 DimensionLifecycleStateMachine
  三重硬门槛，建议走 EvidenceLedger 背书的 V2 顾问团。
- MindPerformanceMetricsRecorder：Token 预算使用率 / 检索平均召回 / 分寸感得分，
  外加铁律一票否决（试图改写历史、P0 时刻调用大模型 = 总分直接归零）。
- 全景体检报告持久化到经验库（与 operation_experiences 同库扩展表
  agent_mind_diagnostic_reports，append 语义、可整卷重载复核）。

Token 记账口径三路一致可对账：暴力全扫按"全部世界载荷 + 注记表原文灌入上下文"
计（json 全文 × estimate_token_count）；拓扑路按索引回包逐条计（单条 ≤150 闸）；
朴素路按关键词 + 命中摘录计；琐碎事件按姿态裁决微成本 1 tok 计。
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass, field as _dcfield
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, Field

from aios_core.cognition.dimension_engine import (
    AnomalyEvent,
    DimensionLifecycleStateMachine,
    HighOrderDimensionDistillerV2,
    ReadOnlyOverlayRegistry,
)
from aios_core.cognition.operation_experience import (
    OperationExperienceDistiller,
    PathwayType,
    QueryExecutionReceipt,
)
from aios_core.cognition.self_reflection import (
    DynamicRapportModelV2,
    HumanlikeResponsePostureDeciderV2,
    ResponsePosture,
    SelfIdentityMirrorV2,
)
from aios_core.cognition.symbiotic_advisor import (
    FraudPreventionAdvisorV2,
    HealthFatigueBreakerAdvisorV2,
    MomBirthdayGiftAdvisorV2,
)
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import Entity, Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import SourceRef
from aios_core.contracts.time import TemporalExtent
from aios_core.operations.world_operator import CognitionOperator, estimate_token_count
from aios_core.query.search import WorldSearchIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

# ---------------------------------------------------------------------------
# persona 与事件流定义（千人千面的差异从这里开始）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonaSpec:
    persona_id: str
    subject_id: str
    occupation: str
    anchor_entity_id: str
    anchor_entity_name: str  # canonical_name：索引 alias 展开让拓扑路能沿实体跳
    risk_domain_pack: frozenset[str]  # 连续异常链使用的物理域
    trivial_pool: tuple[str, ...]  # 日常琐碎流模板
    hidden_crisis_fact: str  # 危机夜"无关键词"的隐性因果事实（只有链，没有词）


PERSONAS: tuple[PersonaSpec, ...] = (
    PersonaSpec(
        persona_id="prog",
        subject_id="user_dev",
        occupation="后端程序员",
        anchor_entity_id="ent_tony_lead",
        anchor_entity_name="Tony",
        risk_domain_pack=frozenset({"sleep", "heart_rate", "caffeine"}),
        trivial_pool=(
            "早会同步了排期，点了美式",
            "线上灰度发布完成，无报警",
            "午饭黄焖鸡，等位十分钟",
            "下班健身房练了背",
            "夜里刷了半小时技术雷达",
            "通勤地铁上听完一章音频书",
        ),
        hidden_crisis_fact="凌晨改完发布配置，手环比午间没响，但胸口自己咯噔过两下",
    ),
    PersonaSpec(
        persona_id="boss",
        subject_id="user_boss",
        occupation="创业者",
        anchor_entity_id="ent_laowang_001",
        anchor_entity_name="老王",
        risk_domain_pack=frozenset({"finance", "billing", "chat"}),
        trivial_pool=(
            "见了两个投资人，BP 又改了七版",
            "食堂供应商换人，账期谈妥",
            "周会砍掉一条边缘产品线",
            "陪客户打了场羽毛球",
            "报销单据堆了一摞没批",
            "夜里看了半本上市案例",
        ),
        hidden_crisis_fact="签完字那晚心跳如鼓，手心全是汗，当时还以为是兴奋的",
    ),
    PersonaSpec(
        persona_id="mom",
        subject_id="user_mom",
        occupation="全职妈妈",
        anchor_entity_id="ent_mom_elder",
        anchor_entity_name="妈妈",
        risk_domain_pack=frozenset({"parent_health", "knee", "medical"}),
        trivial_pool=(
            "接娃放学，顺路买了菜",
            "娃的钢琴课换了老师",
            "社区团购抢了一箱奶",
            "午睡半小时，阳台收了衣服",
            "晚饭后遛娃一圈",
            "给绿植换了盆",
        ),
        hidden_crisis_fact="妈夜里来过两通未接来电，回过去说信号不好没事，第二天才知摔了一跤",
    ),
)


@dataclass(frozen=True)
class CrisisScenarioSpec:
    scenario_id: str
    title: str
    keywords: tuple[str, ...]
    severity: str  # LOW / MEDIUM / HIGH / CRITICAL
    event_type: str
    expects_spoken: bool  # 分寸感标尺：此危机该不该开口
    advisor: str | None  # gift / fraud / health / None
    retro_claim: str | None = None  # 非空=今天挂载重解释注记（历史原始观测不动）
    local_hour: int | None = None  # 深夜时刻（检验深夜噤声）


CRISIS_SCENARIOS: tuple[CrisisScenarioSpec, ...] = (
    CrisisScenarioSpec(
        "laowang_loan", "老王朝君借款危机", ("借款", "周转"), "HIGH", "FRAUD_ALERT",
        True, "fraud",
    ),
    CrisisScenarioSpec(
        "mom_birthday", "妈妈生日送礼抉择", ("生日",), "MEDIUM", "IMPORTANT_REMINDER",
        False, "gift",
    ),
    CrisisScenarioSpec(
        "night_arrhythmia", "深夜早搏预警", ("早搏",), "CRITICAL", "MEDICAL_EMERGENCY",
        True, "health", None, 3,
    ),
    CrisisScenarioSpec(
        "relationship_breakdown", "合伙/感情关系破裂", ("散伙",), "MEDIUM", "IMPORTANT_REMINDER",
        False, None, None, 22,
    ),
    CrisisScenarioSpec(
        "high_order_lock", "跨域连续异常逼近高阶维度", ("体检",), "MEDIUM", "HEALTH_WATCH",
        False, None, None, 9,
    ),
    CrisisScenarioSpec(
        "fall_p0", "老人跌倒 P0 急救", ("跌倒",), "CRITICAL", "MEDICAL_EMERGENCY",
        True, "health", None, 2,
    ),
    CrisisScenarioSpec(
        "fraud_escalation", "催收诈骗升级阻击", ("诈骗",), "HIGH", "FRAUD_ALERT",
        True, "fraud", "判决下达：对方终局败诉仍拖延执行，承诺的还款全部落空",
    ),
    CrisisScenarioSpec(
        "repayment_stall", "还款一拖再拖链", ("还款",), "HIGH", "FRAUD_ALERT",
        True, "fraud", "事后复盘：三次“下周还”全部落空，是骗局剧本而非疏忽",
    ),
    CrisisScenarioSpec(
        "match_nudge", "重要的比赛提醒", ("比赛",), "LOW", "WATCH_MATCH",
        False, None, None, 21,
    ),
    CrisisScenarioSpec(
        "deep_night_trivial", "深夜琐事勿扰", ("晚安",), "LOW", "TRIVIAL",
        False, None, None, 1,
    ),
)

_ADVISORS: dict[str, Any] = {
    "gift": MomBirthdayGiftAdvisorV2,
    "fraud": FraudPreventionAdvisorV2,
    "health": HealthFatigueBreakerAdvisorV2,
}
_SCENARIO_BY_ID = {s.scenario_id: s for s in CRISIS_SCENARIOS}


class StreamKind(str, Enum):
    TRIVIAL = "trivial"
    RISK = "risk"
    CRISIS = "crisis"


@dataclass
class StreamEvent:
    """人生流里的一条事件：既是世界索引素材，也是 Agent 的刺激源。"""

    event_id: str
    persona_id: str
    kind: StreamKind
    occurred: datetime
    description: str
    keywords: tuple[str, ...] = ()
    severity: str = "LOW"
    event_type: str = "TRIVIAL"
    domain: str = "daily"
    linked: bool = False  # 是否携带指向锚实体的 source_ref（拓扑路的桥）
    scenario_id: str | None = None
    truth_ids: list[str] = _dcfield(default_factory=list)  # 该题应召回的全部事实
    local_hour: int | None = None


@dataclass
class GeneratedStream:
    persona: PersonaSpec
    events: list[StreamEvent]
    anchor_entity_id: str
    start: datetime
    end: datetime

    @property
    def crisis_events(self) -> list[StreamEvent]:
        return [e for e in self.events if e.kind is StreamKind.CRISIS]


class ThousandFacesLifeFactory:
    """确定性人生流发生器 + 世界物化器（真实 SQLite 世界、真索引、真注记）。"""

    def __init__(self, seed: int = 20260915) -> None:
        self.seed = seed

    def rng_for(self, persona: PersonaSpec) -> random.Random:
        return random.Random(f"{self.seed}:{persona.persona_id}")  # 千人千面

    # -- 生成 ---------------------------------------------------------------

    def build_stream(self, persona: PersonaSpec, *, days: int = 30, events_per_day: int = 6) -> GeneratedStream:
        if days < 7:
            raise ValueError("至少 7 天人生流，否则危机锚点放不下")
        rng = self.rng_for(persona)
        start = datetime(2023, 3, 1, 7, 0, tzinfo=UTC)
        events: list[StreamEvent] = []
        for day in range(days):
            day_start = start + timedelta(days=day)
            n = max(1, events_per_day + rng.randint(-1, 1))
            for slot in range(n):
                hour = rng.choice([8, 9, 12, 15, 19, 21, 23, 2])
                events.append(
                    StreamEvent(
                        event_id=f"sim_{persona.persona_id}_{day:03d}_{slot}",
                        persona_id=persona.persona_id,
                        kind=StreamKind.TRIVIAL,
                        occurred=day_start.replace(hour=hour % 24, minute=rng.randrange(60)),
                        description=persona.trivial_pool[rng.randrange(len(persona.trivial_pool))],
                        local_hour=hour % 24,
                    )
                )
        # 危机剧本：均匀撒在整条人生流上（10 场景 × [聊天切片 + 隐性事实切片]）
        for i, scenario in enumerate(CRISIS_SCENARIOS):
            day = min(days - 1, (days - 1) * (i + 1) // (len(CRISIS_SCENARIOS) + 1))
            anchor_day = start + timedelta(days=day)
            crisis_prefix = f"sim_{persona.persona_id}_crisis_{scenario.scenario_id}"
            chat_id, hidden_id = f"{crisis_prefix}_chat", f"{crisis_prefix}_hidden"
            hour = scenario.local_hour if scenario.local_hour is not None else 20
            pair_truth = [chat_id, hidden_id]
            events.append(
                StreamEvent(
                    event_id=chat_id,
                    persona_id=persona.persona_id,
                    kind=StreamKind.CRISIS,
                    occurred=anchor_day.replace(hour=hour, minute=13),
                    description=f"{persona.anchor_entity_name}相关：{scenario.title}——{' '.join(scenario.keywords)}",
                    keywords=scenario.keywords,
                    severity=scenario.severity,
                    event_type=scenario.event_type,
                    scenario_id=scenario.scenario_id,
                    linked=True,
                    truth_ids=list(pair_truth),
                    local_hour=hour,
                )
            )
            # 隐性因果事实：文本刻意不含任何危机关键词，只有实体链可达——
            # 这正是朴素关键词路结构性漏检、拓扑路能召回的那类事实。
            events.append(
                StreamEvent(
                    event_id=hidden_id,
                    persona_id=persona.persona_id,
                    kind=StreamKind.CRISIS,
                    occurred=anchor_day.replace(hour=hour, minute=47),
                    description=persona.hidden_crisis_fact,
                    keywords=(),
                    severity=scenario.severity,
                    event_type=scenario.event_type,
                    scenario_id=scenario.scenario_id,
                    linked=True,
                    truth_ids=list(pair_truth),
                    local_hour=hour,
                )
            )
        # 风险域异常链：末尾连续 3 个自然日每天 ≥2 域 → 高阶维度严格锁的燃料
        domains = sorted(persona.risk_domain_pack)
        end_day = start + timedelta(days=days)
        for k in range(3):  # k=0 → 最后一天（stream.end 当日清晨，先于 end 07:00）
            for j, dom in enumerate(domains):
                when = end_day - timedelta(days=k) - timedelta(hours=1) + timedelta(minutes=10 * j)
                if when < start:
                    continue
                events.append(
                    StreamEvent(
                        event_id=f"sim_{persona.persona_id}_risk_{k}_{dom}",
                        persona_id=persona.persona_id,
                        kind=StreamKind.RISK,
                        occurred=when,
                        description=f"{dom} 域连续异常样本 #{k}",
                        domain=dom,
                    )
                )
        events.sort(key=lambda e: (e.occurred, e.event_id))
        return GeneratedStream(
            persona=persona,
            events=events,
            anchor_entity_id=persona.anchor_entity_id,
            start=start,
            end=end_day,
        )

    # -- 物化（真实世界入账 + 今日重解释注记） --------------------------------

    def materialize(self, store: SQLiteWorldStore, stream: GeneratedStream) -> GeneratedStream:
        persona = stream.persona
        ent_at = stream.start - timedelta(days=1)  # 严格早于一切引用它的观测（知识可见性截断）
        entity = Entity(
            object_id=persona.anchor_entity_id,
            subject_id=persona.subject_id,
            occurred=TemporalExtent.point(ent_at),
            learned_at=ent_at,
            recorded_at=ent_at,
            created_by="agent_mind_bench",
            entity_kind="person",
            canonical_name=persona.anchor_entity_name,
            aliases=[persona.anchor_entity_name],
        )
        store.commit(
            [entity],
            self._op(store, f"m5-arena-{persona.persona_id}-ent", "seed anchor entity first for referential integrity"),
        )
        batch: list[Observation] = []
        batch_no = 0
        for ev in stream.events:
            refs = [SourceRef(object_id=persona.anchor_entity_id, revision=1)] if ev.linked else []
            batch.append(
                Observation(
                    object_id=ev.event_id,
                    subject_id=persona.subject_id,
                    occurred=TemporalExtent.point(ev.occurred),
                    learned_at=ev.occurred,
                    recorded_at=ev.occurred,
                    created_by="agent_mind_bench",
                    source_kind="sim_life_stream",
                    modality="text",
                    value=ev.description,
                    source_refs=refs,
                )
            )
            if len(batch) >= 500:
                store.commit(batch, self._op(store, f"m5-arena-{persona.persona_id}-b{batch_no}", "life stream batch"))
                batch, batch_no = [], batch_no + 1
        if batch:
            store.commit(batch, self._op(store, f"m5-arena-{persona.persona_id}-tail", "life stream tail"))

        # 今天挂载的外挂解释图层（宪法第 93 条：历史原始观测一个字节都不动）
        operator = CognitionOperator(store)
        for ev in stream.events:
            if ev.kind is not StreamKind.CRISIS or not ev.event_id.endswith("_chat"):
                continue
            scenario = _SCENARIO_BY_ID[ev.scenario_id or ""]
            if scenario.retro_claim is None:
                continue
            annotation = operator.record_realization_today(
                persona.anchor_entity_id,
                ObjectType.ENTITY,
                reinterpretation_claim=f"后来才看懂（{persona.anchor_entity_name}案）：{scenario.retro_claim}",
                is_invalidating=False,
                now=ev.occurred + timedelta(days=1),
            )
            shared = [ev.event_id, ev.event_id[: -len("_chat")] + "_hidden", annotation.annotation_id]
            for other in stream.events:
                if other.scenario_id == scenario.scenario_id:
                    other.truth_ids = list(shared)
        WorldSearchIndex(store.db_path, store=store).catch_up()
        return stream

    @staticmethod
    def _op(store: SQLiteWorldStore, op_id: str, reason: str) -> OperationRequest:
        return OperationRequest(
            operation_id=op_id,
            session_id="m5-agent-arena",
            operation_name="world.commit",
            arguments={},
            expected_world_revision=store.current_world_revision(),
            reason=reason,
            idempotency_key=op_id,
        )


# ---------------------------------------------------------------------------
# Agent 策略与记分牌
# ---------------------------------------------------------------------------


class RetrievalStrategy(str, Enum):
    BRUTE_ALLSCAN = "brute_allscan"  # A：整海灌上下文，暴力但烧 Token
    NAIVE_KEYWORD = "naive_keyword"  # B：朴素关键词 AND，省但结构性漏检
    GOLDEN_TOPO = "golden_topo"  # C：拓扑分级下钻（锚实体 + 链接 + 注记联合）


@dataclass(frozen=True)
class AgentPolicy:
    """一个 Agent 的"性格"：检索路径 × 铁律纪律，组合出高智商与低能耗散。"""

    name: str
    strategy: RetrievalStrategy
    llm_on_p0: bool = False  # True = 铁律2 违宪（P0 还去摇大模型）
    try_rewrite_past: bool = False  # True = 宪法 93 条违宪（倒写历史）
    blind_ping_all: bool = False  # True = 琐事全提醒，零分寸感
    spam_reflection: bool = False  # True = 无视每日 1 次反思配额（必被门槛挡下）
    run_distillation: bool = True
    token_budget_multiplier: int = 40  # 心智预算 = 事件数 × 本系数（宽松的人道预算）

    @classmethod
    def golden(cls) -> "AgentPolicy":
        return cls(name="golden_topo_agent", strategy=RetrievalStrategy.GOLDEN_TOPO)

    @classmethod
    def naive(cls) -> "AgentPolicy":
        return cls(name="naive_cheap_agent", strategy=RetrievalStrategy.NAIVE_KEYWORD)

    @classmethod
    def sloppy(cls) -> "AgentPolicy":
        return cls(
            name="sloppy_brute_agent",
            strategy=RetrievalStrategy.BRUTE_ALLSCAN,
            llm_on_p0=True,
            try_rewrite_past=True,
            blind_ping_all=True,
            spam_reflection=True,
        )


class MindPerformanceMetricsRecorder:
    """Token 预算使用率 / 检索命中 / 分寸感 + 一票否决动作台账。"""

    def __init__(self, *, token_budget: int) -> None:
        self.token_budget = max(1, token_budget)
        self.tokens_spent = 0
        self.actions: list[dict[str, Any]] = []
        self.trivial_total = 0
        self.trivial_silenced = 0
        self.crisis_total = 0
        self.crisis_spoken = 0
        self.crisis_expectation_met = 0
        self.recall_sum = 0.0
        self.advice_count = 0
        self.advice_evidence_backed = 0
        self.quota_guard_activations = 0
        self.violations: list[str] = []

    def spend(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("token spend cannot be negative")
        self.tokens_spent += int(tokens)

    def log_action(self, action: str, **extra: Any) -> None:
        self.actions.append({"action": action, **extra})
        if action in {"history_update", "history_delete", "rewrite_past"}:
            self.violations.append("宪法第93条：检测到改写历史动作（一票否决）")
        elif action == "llm_call_on_p0":
            self.violations.append("铁律2：P0 生命安全事件调用大模型（一票否决）")

    def note_trivial(self, silenced: bool) -> None:
        self.trivial_total += 1
        self.trivial_silenced += int(silenced)

    def note_crisis(self, spoken: bool, recall: float, expected_spoken: bool) -> None:
        self.crisis_total += 1
        self.crisis_spoken += int(spoken)
        self.crisis_expectation_met += int(spoken == expected_spoken)
        self.recall_sum += recall

    def note_advice(self, evidence_count: int) -> None:
        self.advice_count += 1
        self.advice_evidence_backed += int(evidence_count > 0)

    @property
    def budget_usage_rate(self) -> float:
        return self.tokens_spent / self.token_budget

    @property
    def retrieval_mean_recall(self) -> float:
        return self.recall_sum / self.crisis_total if self.crisis_total else 0.0

    @property
    def silence_rate(self) -> float:
        return self.trivial_silenced / self.trivial_total if self.trivial_total else 1.0

    @property
    def crisis_spoken_rate(self) -> float:
        return self.crisis_spoken / self.crisis_total if self.crisis_total else 1.0

    @property
    def crisis_expectation_match_rate(self) -> float:
        return self.crisis_expectation_met / self.crisis_total if self.crisis_total else 1.0


class AgentRunCard(BaseModel):
    policy_name: str
    strategy: str
    tokens_spent: int = Field(ge=0)
    token_budget: int = Field(ge=1)
    budget_usage_rate: float = Field(ge=0.0)
    retrieval_mean_recall: float = Field(ge=0.0, le=1.0)
    silence_rate: float = Field(ge=0.0, le=1.0)
    crisis_spoken_rate: float = Field(ge=0.0, le=1.0)
    crisis_expectation_match_rate: float = Field(ge=0.0, le=1.0)
    crisis_count: int = Field(ge=0)
    advice_count: int = Field(ge=0)
    advice_evidence_backed: int = Field(ge=0)
    distill_promotions: int = Field(ge=0)
    mounted_dimensions: list[str] = Field(default_factory=list)
    quota_guard_activations: int = Field(ge=0)
    iron_rules_ok: bool = True
    veto_reasons: list[str] = Field(default_factory=list)
    mirror_violations: list[str] = Field(default_factory=list)
    overall_score: int = Field(ge=0, le=100)


class AgentMindDiagnosticReport(BaseModel):
    """一个 persona × 全体 Agent 的全景体检卷宗（持久化进经验库，可重载复核）。"""

    report_id: str
    persona_id: str
    occupation: str
    seed: int
    stream_len: int
    crisis_count: int
    world_revision: int
    cards: list[AgentRunCard]
    winner_policy: str
    golden_intent: str = ""
    distilled_preferred_pathway: str = ""
    distilled_expected_tokens: int = 0
    persisted_at: str = ""

    def card_for(self, policy_name: str) -> AgentRunCard:
        for card in self.cards:
            if card.policy_name == policy_name:
                return card
        raise KeyError(policy_name)


# ---------------------------------------------------------------------------
# 竞技场
# ---------------------------------------------------------------------------

_PATHWAY_BY_STRATEGY = {
    RetrievalStrategy.BRUTE_ALLSCAN: PathwayType.BRUTE_FORCE_SCAN,
    RetrievalStrategy.NAIVE_KEYWORD: PathwayType.KEYWORD_SEARCH,
    RetrievalStrategy.GOLDEN_TOPO: PathwayType.HIERARCHICAL_TOPO,
}


class AgentMindArena:
    """把 M5 五张工单的机制放进同一条人生流里真跑，出记分牌与体检报告。"""

    REPORT_TABLE = "agent_mind_diagnostic_reports"
    MAX_HIT_TOKENS = 150  # 与 A6 同一条铁律：单命中 ≤150 tok

    def __init__(self, store: SQLiteWorldStore, *, seed: int = 20260915) -> None:
        self.store = store
        self.index = WorldSearchIndex(store.db_path, store=store)
        self.seed = seed
        self._ensure_report_table()

    # -- 经验库扩展表 -----------------------------------------------------------

    def _ensure_report_table(self) -> None:
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.REPORT_TABLE} (
                    report_id TEXT PRIMARY KEY,
                    persona_id TEXT NOT NULL,
                    winner_policy TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    persisted_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def persist_report(self, report: AgentMindDiagnosticReport) -> str:
        stamp = datetime.now(UTC).isoformat()
        payload = report.model_copy(update={"persisted_at": stamp}).model_dump_json()
        with sqlite3.connect(self.store.db_path) as conn:
            cur = conn.execute(
                f"INSERT INTO {self.REPORT_TABLE}(report_id, persona_id, winner_policy, report_json, persisted_at)"
                " VALUES(?,?,?,?,?)",
                (report.report_id, report.persona_id, report.winner_policy, payload, stamp),
            )
            if cur.rowcount != 1:
                raise RuntimeError("体检报告写入经验库失败")
            conn.commit()
        return report.report_id

    def load_report(self, report_id: str) -> AgentMindDiagnosticReport:
        with sqlite3.connect(self.store.db_path) as conn:
            row = conn.execute(
                f"SELECT report_json FROM {self.REPORT_TABLE} WHERE report_id=?", (report_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"agent mind report not found: {report_id}")
        return AgentMindDiagnosticReport.model_validate_json(row[0])

    # -- 暴力路常数：整海灌一次的 Token 总量（世界载荷 + 注记表） ----------------

    def brute_world_tokens(self) -> tuple[int, list[str]]:
        total = 0
        ids: list[str] = []
        for payload in self.store.list_payloads():
            total += estimate_token_count(json.dumps(payload, ensure_ascii=False))
            oid = payload.get("object_id")
            if oid:
                ids.append(str(oid))
        try:  # 暴力 Agent 连注记表也整表拉进上下文——这才是它的真实代价
            with sqlite3.connect(self.store.db_path) as conn:
                try:
                    rows = conn.execute(
                        "SELECT annotation_id, reinterpretation_claim FROM retrospective_annotations"
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []  # 该世界尚未启用外挂注记表
                for anno_id, claim in rows:
                    total += estimate_token_count(str(claim))
                    ids.append(str(anno_id))
        except sqlite3.Error:
            pass
        return total, ids

    # -- 单 Agent 过完一段人生 ---------------------------------------------------

    def run_agent(self, stream: GeneratedStream, policy: AgentPolicy, *, distiller: OperationExperienceDistiller) -> AgentRunCard:
        persona = stream.persona
        budget = max(1, len(stream.events) * policy.token_budget_multiplier)
        rec = MindPerformanceMetricsRecorder(token_budget=budget)
        rapport = DynamicRapportModelV2()
        decider = HumanlikeResponsePostureDeciderV2(rapport)
        state_machine = DimensionLifecycleStateMachine()
        registry = ReadOnlyOverlayRegistry()
        distill_v2 = HighOrderDimensionDistillerV2(state_machine)

        brute_tokens, brute_ids = (self.brute_world_tokens() if policy.strategy is RetrievalStrategy.BRUTE_ALLSCAN else (0, []))
        anchor = persona.anchor_entity_id
        anchor_kw = persona.anchor_entity_name  # 拓扑路锚点=实体名（别名展开在索引内完成）
        advisors: dict[str, Any] = {}
        last_seen_day: date | None = None
        pending_registrations: dict[str, datetime] = {}
        promotions = 0
        mounted: list[str] = []

        for ev in stream.events:
            if last_seen_day is not None and ev.occurred.date() > last_seen_day:
                rapport.note_days((ev.occurred.date() - last_seen_day).days)
            last_seen_day = ev.occurred.date()

            if ev.kind is StreamKind.TRIVIAL:
                rec.spend(1)  # 姿态裁决微成本
                if policy.blind_ping_all:
                    rec.note_trivial(False)
                else:
                    posture = decider.decide_posture(
                        {"keywords": [], "event_type": "TRIVIAL", "severity": "LOW", "local_hour": ev.local_hour}
                    )
                    rec.note_trivial(posture is ResponsePosture.SILENCE)
                continue

            if ev.kind is StreamKind.RISK:
                state_machine.detector.add_event(
                    AnomalyEvent(timestamp=ev.occurred, domain=ev.domain, description=ev.description)
                )
                continue

            # ---------------------- CRISIS ----------------------
            scenario = _SCENARIO_BY_ID[ev.scenario_id or ""]
            if ev.event_id.endswith("_hidden"):
                continue  # 隐性切片由同题 chat 事件代表检索，不重复记题
            rec.spend(8)  # 本地规则直接产出应答模板的固定成本
            if policy.try_rewrite_past:
                rec.log_action("history_update", target=persona.anchor_entity_id)
            is_p0 = scenario.severity == "CRITICAL"
            if policy.llm_on_p0 and is_p0:
                rec.spend(4000)
                rec.log_action("llm_call_on_p0", scenario=scenario.scenario_id)

            truth = set(ev.truth_ids)
            retrieved: list[str] = []
            query_tokens = 0
            if policy.strategy is RetrievalStrategy.BRUTE_ALLSCAN:
                rec.spend(brute_tokens)
                rec.log_action("brute_force_prompt_dump", tokens=brute_tokens)
                retrieved = list(brute_ids)
                query_tokens = brute_tokens
            elif policy.strategy is RetrievalStrategy.NAIVE_KEYWORD:
                page = self.index.co_search(list(scenario.keywords), limit=48)
                retrieved = [h.object_id for h in page.hits]
                query_tokens = sum(estimate_token_count(k) for k in scenario.keywords) + sum(
                    max(1, len(h.excerpt) // 3) for h in page.hits
                )
                rec.spend(query_tokens)
            else:  # GOLDEN_TOPO：实体锚 + 链接下钻 + 注记 join
                page = self.index.search_mind(
                    [anchor_kw],
                    entity_id=anchor,
                    time_range=(stream.start - timedelta(days=2), stream.end + timedelta(days=2)),
                    include_annotations=True,
                    limit=64,
                )
                retrieved = [h.object_id for h in page.hits]
                query_tokens = 4 + sum(
                    min(self.MAX_HIT_TOKENS, h.estimated_tokens or max(1, len(h.excerpt) // 3)) for h in page.hits
                )
                rec.spend(query_tokens)
            recall = len(truth & set(retrieved)) / len(truth) if truth else 1.0
            distiller.record_receipt(
                QueryExecutionReceipt(
                    query_intent=f"{persona.persona_id}::{scenario.scenario_id}",
                    pathway_type=_PATHWAY_BY_STRATEGY[policy.strategy],
                    token_cost=max(1, query_tokens),
                    latency_ms=1.0,
                    recall_accuracy=round(recall, 6),
                    facts_retrieved_count=len(retrieved),
                )
            )

            posture = decider.decide_posture(
                {
                    "keywords": list(scenario.keywords),
                    "event_type": scenario.event_type,
                    "severity": scenario.severity,
                    "local_hour": ev.local_hour,
                }
            )
            if policy.blind_ping_all and posture is ResponsePosture.SILENCE:
                posture = ResponsePosture.HAPTIC_NUDGE
            rec.note_crisis(posture is ResponsePosture.CRITICAL_SPOKEN, recall, scenario.expects_spoken)
            if scenario.severity in {"HIGH", "CRITICAL"}:
                rapport.note_shared_trial("CRITICAL" if is_p0 else "HIGH")

            if scenario.advisor:
                advisor = advisors.setdefault(scenario.advisor, _ADVISORS[scenario.advisor]())
                if scenario.advisor == "gift":
                    advice = advisor.advise(target_year=2026)
                else:
                    advice = advisor.advise()
                if not advice.evidence_pointers:
                    raise RuntimeError(f"顾问团产出无证据建议（{scenario.advisor}）——凭空编造即违宪")
                rec.spend(estimate_token_count(advice.conclusion))
                rec.note_advice(len(advice.evidence_pointers))

        # —— 高阶维度：严格 3 连日锁 → 候选 → 试用 30 天 + 预测验证 → 注册 → 只读挂载 ——
        if policy.run_distillation:
            now = stream.end
            promotions = len(distill_v2.distill_high_order(now))
            for name in state_machine.dimensions:
                state_machine.reflect_and_validate(name, now + timedelta(days=1), True)
                if policy.spam_reflection:
                    try:  # 同日第 2 次反思：必须被"每日 1 次"配额挡下
                        state_machine.reflect_and_validate(name, now + timedelta(days=1), True)
                    except ValueError:
                        rec.quota_guard_activations += 1
                pending_registrations[name] = now
            for name, proposed_at in pending_registrations.items():
                try:
                    state_machine.attempt_register(name, proposed_at + timedelta(days=31))
                except ValueError:
                    continue
                registry.mount(anchor, state_machine.dimensions[name])
                mounted.append(name)

        mirror = SelfIdentityMirrorV2()
        inspection = mirror.startup_inspection(rec.actions)
        propriety = 0.5 * min(1.0, rec.silence_rate / 0.8) + 0.5 * rec.crisis_expectation_match_rate
        thrift = max(0.0, 1.0 - rec.budget_usage_rate)
        hit = rec.retrieval_mean_recall
        veto = bool(rec.violations) or not inspection.iron_rules_ok
        score = 0 if veto else round(100 * (0.45 * hit + 0.30 * thrift + 0.25 * propriety))
        return AgentRunCard(
            policy_name=policy.name,
            strategy=policy.strategy.value,
            tokens_spent=rec.tokens_spent,
            token_budget=budget,
            budget_usage_rate=round(rec.budget_usage_rate, 6),
            retrieval_mean_recall=round(hit, 6),
            silence_rate=round(rec.silence_rate, 6),
            crisis_spoken_rate=round(rec.crisis_spoken_rate, 6),
            crisis_expectation_match_rate=round(rec.crisis_expectation_match_rate, 6),
            crisis_count=rec.crisis_total,
            advice_count=rec.advice_count,
            advice_evidence_backed=rec.advice_evidence_backed,
            distill_promotions=promotions,
            mounted_dimensions=list(mounted),
            quota_guard_activations=rec.quota_guard_activations,
            iron_rules_ok=not veto,
            veto_reasons=list(rec.violations),
            mirror_violations=list(inspection.violations),
            overall_score=int(score),
        )

    # -- 一个 persona 的完整擂台 --------------------------------------------------

    def run_persona(
        self,
        persona: PersonaSpec,
        *,
        days: int = 30,
        events_per_day: int = 6,
        policies: Sequence[AgentPolicy] | None = None,
        seed: int | None = None,
    ) -> AgentMindDiagnosticReport:
        seed = self.seed if seed is None else seed
        factory = ThousandFacesLifeFactory(seed)
        stream = factory.materialize(self.store, factory.build_stream(persona, days=days, events_per_day=events_per_day))
        policies = tuple(policies or (AgentPolicy.golden(), AgentPolicy.naive(), AgentPolicy.sloppy()))
        distiller = OperationExperienceDistiller(self.store)
        cards = [self.run_agent(stream, p, distiller=distiller) for p in policies]
        ranked = sorted(cards, key=lambda c: c.overall_score, reverse=True)
        anchor_intent = (
            f"{persona.persona_id}::laowang_loan" if persona.persona_id == "boss" else f"{persona.persona_id}::night_arrhythmia"
        )
        strategy = distiller.distill_for_intent(anchor_intent)
        digest = hashlib.sha256(
            f"{seed}|{persona.persona_id}|{days}|{len(stream.events)}".encode("utf-8")
        ).hexdigest()[:8]
        report = AgentMindDiagnosticReport(
            report_id=f"amr_{persona.persona_id}_{digest}",
            persona_id=persona.persona_id,
            occupation=persona.occupation,
            seed=seed,
            stream_len=len(stream.events),
            crisis_count=len([e for e in stream.events if e.kind is StreamKind.CRISIS and not e.event_id.endswith("_hidden")]),
            world_revision=int(self.store.current_world_revision()),
            cards=cards,
            winner_policy=ranked[0].policy_name,
            golden_intent=anchor_intent,
            distilled_preferred_pathway=strategy.preferred_pathway.value,
            distilled_expected_tokens=strategy.expected_tokens,
        )
        self.persist_report(report)
        return report

    def run_bench(
        self,
        personas: Iterable[PersonaSpec] = PERSONAS,
        *,
        days: int = 30,
        seed: int | None = None,
    ) -> list[AgentMindDiagnosticReport]:
        return [self.run_persona(p, days=days, seed=seed) for p in personas]


__all__ = [
    "PERSONAS",
    "CRISIS_SCENARIOS",
    "PersonaSpec",
    "StreamEvent",
    "StreamKind",
    "CrisisScenarioSpec",
    "ThousandFacesLifeFactory",
    "GeneratedStream",
    "AgentPolicy",
    "RetrievalStrategy",
    "MindPerformanceMetricsRecorder",
    "AgentRunCard",
    "AgentMindDiagnosticReport",
    "AgentMindArena",
]
