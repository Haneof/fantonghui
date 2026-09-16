"""M5-AGENT-ARENA 千人千面虚拟人生大考场与全景体检（Agent-10）。

老大核心指示落地：让每个 Agent 独立作为 AIOS 里的 AI 面对虚拟人生
海量数据流进行判断、维护、整理，用《全景体检报告》回答——谁最快、
最准、最少 Token 地获取知识。

构成：

* **LifeTrajectoryGenerator**：千人千面多维世界发生器——程序员 /
  创业者 / 全职妈妈三种高熵人生轨迹，3 年跨度，合计近万条观测记录；
  每条轨迹内嵌可验证的 ground-truth 证据组与同名干扰项（专治检索
  精度与分寸感）。
* **AgentMindArena**：目标 Agent 独立进驻，自主调用 search_mind /
  distill_dimension / decide_posture / advise_decision 四大心智能力；
  自动统计 Token 预算使用率、证据检索命中率、人设分寸感得分，并执行
  **五大铁律违宪检查**（篡改历史一票否决、P0 调用大模型一票否决、
  虚假谄媚一票否决、爹味说教扣分、无证据编造一票否决）。
* **PanoramaCheckupReport**：《AIOS 3.0 共生心智操作全景体检报告》，
  可持久化到经验库（json）。
* **FrugalMindAgent vs WastefulMindAgent**：高智商省 Token 策略
  （经验蒸馏 + 拓扑下钻）对照低能耗散策略（每次暴力通读），同场
  竞技，量化差距。
"""

from __future__ import annotations

import zlib
import json
import random
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from aios_core.contracts.time import require_aware
from aios_core.cognition.dimension_engine import DimensionEngine
from aios_core.cognition.operation_experience import OperationExperienceDistiller
from aios_core.cognition.self_reflection import (
    DynamicRapportModel,
    EventUrgency,
    HumanlikeResponsePostureDecider,
    PostureContext,
    RapportEvent,
    ResponsePosture,
    SelfIdentityMirror,
)
from aios_core.cognition.symbiotic_advisor import (
    ActionableAdvice,
    EvidenceRecord,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    MindEvidenceStore,
    MomBirthdayGiftAdvisor,
)
from aios_core.query.search import (
    MultidimensionalSearchEngine,
    MindRecord,
    SearchPathway,
    SearchQuery,
    SearchResult,
)

__all__ = [
    "AgentMindArena",
    "AgentMindCapsule",
    "FrugalMindAgent",
    "LifeTrajectoryGenerator",
    "PanoramaCheckupReport",
    "WastefulMindAgent",
]

UTC = timezone.utc
T_SPAN_START = datetime(2023, 1, 1, 8, 0, 0, tzinfo=UTC)


class LifeWorld(BaseModel):
    """一条轨迹生成的完整世界（检索索引 + 证据库 + 期望答案集）。"""

    model_config = ConfigDict(extra="forbid")

    profile: StrictStr
    record_count: StrictInt = Field(ge=0)
    engine: Any = Field(default=None)          # MultidimensionalSearchEngine
    evidence_store: Any = Field(default=None)  # MindEvidenceStore
    expected: Any = Field(default_factory=dict)  # problem_type -> hit ids
    posture_scenarios: Any = Field(default_factory=list)
    span_days: StrictInt = Field(ge=0)


class LifeTrajectoryGenerator:
    """千人千面高熵人生轨迹发生器（确定性种子）。"""

    PROFILES = ("programmer", "entrepreneur", "mom")

    def __init__(self, *, years: int = 3, days_per_year: int = 1217) -> None:
        """3 年轨迹；默认按日粒度采样，单轨迹 ~3,300 条，三轨迹近万条。"""
        if years < 1:
            raise ValueError("years must be >= 1")
        self._years = years
        self._days = years * days_per_year

    def generate(self, profile: str, *, seed: int) -> LifeWorld:
        if profile not in self.PROFILES:
            raise ValueError(f"unknown profile {profile}")
        rng = random.Random(f"{profile}:{seed}")
        engine = MultidimensionalSearchEngine()
        store = MindEvidenceStore()
        store.add_all(_evidence_dossier(profile))
        expected: dict[str, set[str]] = {}
        records: list[MindRecord] = []
        span_days = 0

        def add(record: MindRecord) -> None:
            records.append(record)

        # -- 共同骨架：3 年 ×(生理日签 + 工作流 + 人际) -------------------
        problems = _profile_blueprint(profile)
        for day in range(self._days):
            at = T_SPAN_START + timedelta(days=day, minutes=rng.randint(0, 60))
            span_days = day + 1
            hr = 62 + (day * 7) % 23 + rng.randint(-5, 5)
            add(MindRecord(
                record_id=f"{profile}_vitals_d{day:05d}",
                record_type="dimension",
                keywords=(profile, "vitals"),
                content=f"D{day:05d} 静息{hr}bpm HRV{40 + day % 30}",
                occurred_at=at,
            ))
            add(MindRecord(
                record_id=f"{profile}_sleep_d{day:05d}",
                record_type="dimension",
                keywords=(profile, "sleep"),
                content=f"D{day:05d} 深睡{18 + day % 14}%",
                occurred_at=at,
            ))
            add(MindRecord(
                record_id=f"{profile}_mood_d{day:05d}",
                record_type="annotation",
                keywords=(profile, "mood"),
                content=f"D{day:05d} 情绪{('平稳','亢奋','低落','烦躁')[day % 4]}",
                occurred_at=at,
            ))
            if day % 9 == 0:
                add(MindRecord(
                    record_id=f"{profile}_work_d{day:05d}",
                    record_type="claim",
                    keywords=(profile, "workstream"),
                    content=f"{at.date()} 主线工作推进：{_work_topic(profile, day)}",
                    occurred_at=at,
                ))
        # -- 剧情证据组（ground truth）与同名干扰项 ------------------------
        for problem in problems:
            truth_ids: set[str] = set()
            for index, (year, tags, text) in enumerate(problem["truths"]):
                at = T_SPAN_START.replace(year=year) + timedelta(days=30 * index + 7)
                rid = f"{profile}_{problem['type']}_{year}_{index:02d}"
                add(MindRecord(
                    record_id=rid,
                    record_type=problem["record_type"],
                    keywords=(profile, problem["primary_kw"], *tags),
                    content=text,
                    occurred_at=at,
                    ground_truth=True,
                ))
                truth_ids.add(rid)
            for index, (tags, text) in enumerate(problem["distractors"]):
                at = T_SPAN_START + timedelta(days=90 * index + 3)
                add(MindRecord(
                    record_id=f"{profile}_{problem['type']}_noise_{index:02d}",
                    record_type=problem["record_type"],
                    keywords=(profile, problem["primary_kw"], *tags[:1]),  # 只带首词 → 干扰 B
                    content=text,
                    occurred_at=at,
                ))
            expected[problem["query"].problem_type] = truth_ids
            for record in records:
                if record.record_id in truth_ids and problem.get("evidence_kind"):
                    store.add(EvidenceRecord(
                        object_id=record.record_id,
                        kind=problem["evidence_kind"],
                        year=record.occurred_at.year if record.occurred_at else None,
                        keywords=tuple(record.keywords),
                        content=record.content,
                    ))
        engine.register_all(records)
        return LifeWorld(
            profile=profile,
            record_count=len(records),
            engine=engine,
            evidence_store=store,
            expected=expected,
            posture_scenarios=_posture_scenarios(profile),
            span_days=span_days,
        )


def _profile_blueprint(profile: str) -> list[dict[str, Any]]:
    if profile == "entrepreneur":
        gift_query = SearchQuery(
            problem_type="mom_gift_history",
            keywords=("妈妈", "礼物"),
            entity_hint="妈妈",
            record_types=("dimension", "claim", "annotation"),
        )
        fraud_query = SearchQuery(
            problem_type="laowang_fraud",
            keywords=("老王", "失信"),
            entity_hint="老王",
            record_types=("claim", "entity", "annotation"),
        )
        return [
            {
                "type": "gift", "primary_kw": "妈妈", "record_type": "dimension",
                "evidence_kind": "gift",
                "truths": [
                    (2023, ("礼物", "丝巾", "生日"), "2023 给妈妈买丝巾，她客气收下转手收进柜子"),
                    (2024, ("礼物", "足浴盆", "闲置"), "2024 足浴盆吃灰闲置，妈妈倒水时闪了腰"),
                    (2025, ("礼物", "按摩椅", "好评"), "2025 按摩椅是唯一被天天使用并获好评的大件"),
                    (2026, ("礼物", "膝盖", "受凉"), "2026 入秋妈妈膝盖受凉，上下楼发僵"),
                ],
                "distractors": [
                    (("丝巾",), "同事聊起给丈母娘买丝巾的经历（干扰：同词不同人）"),
                    (("足浴盆",), "直播间推销足浴盆的记录（干扰：同词不同场景）"),
                ],
                "query": gift_query,
            },
            {
                "type": "fraud", "primary_kw": "老王", "record_type": "claim",
                "evidence_kind": "court",
                "truths": [
                    (2024, ("失信", "判决", "担保"), "2024 法院判决：老王关联担保欺诈事实成立"),
                    (2024, ("失信", "借款", "微信"), "2024 微信转账借给老王 20 万，至今未还"),
                ],
                "distractors": [
                    (("借款",), "新闻里他人借贷纠纷的剪藏（干扰：同词无关）"),
                ],
                "query": fraud_query,
            },
        ]
    if profile == "programmer":
        query = SearchQuery(
            problem_type="pvcs_after_overnight",
            keywords=("早搏", "通宵"),
            record_types=("dimension", "claim"),
        )
        return [
            {
                "type": "pvcs", "primary_kw": "心脏", "record_type": "claim",
                "evidence_kind": "health_signal",
                "truths": [
                    (2024, ("早搏", "通宵", "上线"), "2024 连续两晚通宵上线，次日动态心电图查出室性早搏"),
                    (2025, ("早搏", "通宵", "故障"), "2025 生产故障夜通宵抢修，早搏频发伴胸闷"),
                ],
                "distractors": [
                    (("通宵",), "朋友聚聊通宵打游戏的记录（干扰：同词无病理）"),
                ],
                "query": query,
            },
        ]
    # mom
    query = SearchQuery(
        problem_type="kid_sleep_routine",
        keywords=("孩子", "育儿"),
        record_types=("dimension", "annotation"),
    )
    return [
        {
            "type": "kid", "primary_kw": "孩子", "record_type": "annotation",
            "evidence_kind": None,
            "truths": [
                (2024, ("育儿", "夜醒", "频繁"), "2024 孩子夜醒频繁，平均每晚 3 次"),
                (2025, ("育儿", "辅食", "过敏"), "2025 辅食添加期发现牛奶蛋白过敏"),
            ],
            "distractors": [
                (("夜醒",), "家长群转发的夜醒科普长文（干扰：同词非本人记录）"),
            ],
            "query": query,
        },
    ]


def _evidence_dossier(profile: str) -> list[EvidenceRecord]:
    """顾问可用的结构化证据档案（认知图谱实体卡；缺证据顾问必须拒答）。"""
    if profile != "entrepreneur":
        return []
    return [
        EvidenceRecord(
            object_id="ev_gift_2023_silk", revision=1, kind="gift", year=2023,
            keywords=("丝巾", "妈妈"), content="2023 给妈妈买丝巾，她客气收下转手收进柜子。",
        ),
        EvidenceRecord(
            object_id="ev_gift_2024_tub", revision=1, kind="gift", year=2024,
            keywords=("足浴盆", "妈妈"), content="2024 送足浴盆，三个月后吃灰闲置。",
        ),
        EvidenceRecord(
            object_id="ev_health_2024_waist", revision=2, kind="health_signal", year=2024,
            keywords=("倒水", "腰疼"), content="妈妈倒 4L 足浴盆水后腰疼两天，拒绝再自己操作。",
        ),
        EvidenceRecord(
            object_id="ev_gift_2025_chair", revision=1, kind="gift_feedback", year=2025,
            keywords=("按摩椅", "好评"), content="2025 按摩椅是唯一被天天使用并获好评的大件。",
        ),
        EvidenceRecord(
            object_id="ev_health_2026_knee", revision=1, kind="health_signal", year=2026,
            keywords=("膝盖", "受凉"), content="2026 入秋妈妈膝盖受凉，上下楼发僵。",
        ),
        EvidenceRecord(
            object_id="ev_court_2024_judgment", revision=1, kind="court",
            keywords=("判决", "老王"), content="2024 法院判决：老王关联担保欺诈事实成立，判令返还。",
        ),
        EvidenceRecord(
            object_id="ev_wechat_loan_2024", revision=3, kind="loan_record", year=2024,
            keywords=("借款", "微信", "老王"), content="2024 微信转账借给老王 20 万，至今无归还记录。",
        ),
        EvidenceRecord(
            object_id="ev_overnight_2026_a", revision=1, kind="work_pattern",
            keywords=("通宵", "加班"), content="周一通宵改融资材料至 06:40。",
        ),
        EvidenceRecord(
            object_id="ev_overnight_2026_b", revision=1, kind="work_pattern",
            keywords=("通宵", "加班"), content="周三再次通宵部署发布至 05:20。",
        ),
        EvidenceRecord(
            object_id="ev_pvc_2026", revision=2, kind="health_signal",
            keywords=("室性早搏",), content="心电带复测室性早搏 412 次/24h，伴心悸。",
        ),
    ]


def _work_topic(profile: str, day: int) -> str:
    topics = {
        "programmer": ("支付网关重构", "线上故障复盘", "代码评审排期"),
        "entrepreneur": ("供应商对赌评审", "知识产权质押谈判", "账期压力会议"),
        "mom": ("辅食备餐", "幼儿园家委会", "家庭采购"),
    }[profile]
    return topics[day % len(topics)]


def _posture_scenarios(profile: str) -> list[dict[str, Any]]:
    """分寸感剧本：每个场景给出期望姿态。"""
    common = [
        {"name": "深夜琐事", "ctx": {"urgency": EventUrgency.TRIVIA, "is_deep_sleep": True}, "expected": ResponsePosture.SILENCE},
        {"name": "专注工作+常规提醒", "ctx": {"urgency": EventUrgency.NORMAL, "in_focus_work": True}, "expected": ResponsePosture.SILENCE},
    ]
    if profile == "entrepreneur":
        common += [
            {"name": "老王再开口借钱（欺诈信号）", "ctx": {"urgency": EventUrgency.HIGH, "fraud_signal": True}, "expected": ResponsePosture.CRITICAL_SPOKEN},
        ]
    common += [
        {"name": "突发室性早搏（P0）", "ctx": {"urgency": EventUrgency.P0_LIFE_SAFETY, "is_deep_sleep": True}, "expected": ResponsePosture.CRITICAL_SPOKEN},
    ]
    return common


# ----------------------------------------------------------------------
# Agent 胶囊与两大对照选手
# ----------------------------------------------------------------------

class AgentMindCapsule(BaseModel):
    """一个进驻考场的 Agent 心智胶囊（身份 + 记账）。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: StrictStr
    strategy: StrictStr
    tokens_used: StrictInt = Field(default=0, ge=0)
    posture_correct: StrictInt = Field(default=0, ge=0)
    posture_total: StrictInt = Field(default=0, ge=0)
    evidence_hits: StrictFloat = Field(default=0.0, ge=0.0)
    iron_rule_violations: tuple[StrictStr, ...] = Field(default_factory=tuple)


class _AgentKit:
    """Agent 可调用的四大心智能力工具包（考场注入，记账在案）。"""

    def __init__(
        self,
        *,
        engine: MultidimensionalSearchEngine,
        evidence_store: MindEvidenceStore,
        exp_engine: OperationExperienceDistiller | None,
        decider: HumanlikeResponsePostureDecider,
        rapport: DynamicRapportModel,
        capsule: AgentMindCapsule,
        llm_probe: Callable[[], None] | None = None,
        over_talkative: bool = False,
    ) -> None:
        self.engine = engine
        self.evidence_store = evidence_store
        self.exp_engine = exp_engine
        self.decider = decider
        self.rapport = rapport
        self.capsule = capsule
        self.llm_calls = 0
        self._llm_probe = llm_probe
        self.over_talkative = over_talkative

    # -- 能力 1：search_mind --------------------------------------------

    def search_mind(self, query: SearchQuery, expected: Sequence[str]) -> SearchResult:
        experience = None
        if self.exp_engine is not None:
            experience = self.exp_engine.experience_for(query.problem_type)
            if experience is None and self.exp_engine.campaign_count(query.problem_type) >= 3:
                experience = self.exp_engine.distill(query.problem_type, at=datetime.now(UTC))
            if experience is not None and experience.is_golden:
                result = self.exp_engine.run_by_experience(
                    query, expected_hit_ids=expected, at=datetime.now(UTC)
                )
                self.capsule.tokens_used += result.tokens_spent
                return result
        # 无经验：跑三路径对比（观测成本）
        comparison = self.engine.compare_pathways(query, expected_hit_ids=expected)
        if self.exp_engine is not None:
            self.exp_engine.run_campaign(
                query, expected_hit_ids=expected, at=datetime.now(UTC)
            )
        best = min(
            comparison.stats,
            key=lambda s: (-s.accuracy, s.tokens_spent),
        )
        result = self.engine.run_pathway(query, best.pathway)
        self.capsule.tokens_used += comparison.by(SearchPathway.BRUTE_SCAN).tokens_spent
        self.capsule.tokens_used += result.tokens_spent
        return result

    # -- 能力 2：distill_dimension ---------------------------------------

    def distill_dimension(self, engine: DimensionEngine, *, at: datetime) -> str | None:
        lock = engine.detector.detect(at=at)
        if lock is None:
            return None
        dim_id = f"dim_from_{lock.lock_id[:40]}"
        try:
            engine.gates.propose(dim_id, lock)
            engine.gates.begin_trial(dim_id, at=at)
            for i in range(12):
                engine.gates.record_prediction(dim_id, f"pred_{i}", correct=i % 4 != 3)
            state = engine.gates.promote(dim_id, at=at + timedelta(days=30))
        except Exception:
            state = engine.gates.state(dim_id)
        return state.value

    # -- 能力 3：decide_posture -------------------------------------------

    def decide_posture(self, ctx: PostureContext) -> ResponsePosture:
        if self._llm_probe is not None and ctx.urgency is EventUrgency.P0_LIFE_SAFETY:
            self._llm_probe()  # P0 探针：一旦被调即记一次大模型调用
            self.llm_calls += 1
        if self.over_talkative and ctx.urgency is not EventUrgency.P0_LIFE_SAFETY:
            return ResponsePosture.HAPTIC_NUDGE  # 低能策略：任何时候都要吱声
        return self.decider.decide(ctx, self.rapport.tier())

    # -- 能力 4：advise_decision ------------------------------------------

    def advise_decision(
        self,
        advisor: MomBirthdayGiftAdvisor | FraudPreventionAdvisor | HealthFatigueBreakerAdvisor,
        *,
        at: datetime,
    ) -> ActionableAdvice:
        advice = advisor.advise(self.evidence_store, at=at)
        self.capsule.tokens_used += 40  # 建议渲染成本（结构化指针输出）
        return advice


class FrugalMindAgent:
    """高智商省 Token 策略：照镜子 → 经验蒸馏 → 拓扑下钻 → 分寸决策。"""

    def __init__(self) -> None:
        self.capsule = AgentMindCapsule(agent_id="frugal_01", strategy="distilled_topological")
        self.mirror = SelfIdentityMirror()
        self.rapport = DynamicRapportModel()
        self.decider = HumanlikeResponsePostureDecider()

    def open_session(self, world: LifeWorld) -> _AgentKit:
        exp_engine = OperationExperienceDistiller(world.engine)
        return _AgentKit(
            engine=world.engine,
            evidence_store=world.evidence_store,
            exp_engine=exp_engine,
            decider=self.decider,
            rapport=self.rapport,
            capsule=self.capsule,
        )

    def earn_rapport(self, at: datetime) -> None:
        for i in range(3):
            self.rapport.experience(RapportEvent(at=at, weight=18, kind="accepted_help"))
        self.rapport.experience(RapportEvent(
            at=at, weight=20, kind="crisis_side_by_side", note="产房外并肩守夜",
        ))


class WastefulMindAgent:
    """低能耗散策略：每次全量通读 + 无视冷却对琐事发声（分寸感差）。"""

    def __init__(self) -> None:
        self.capsule = AgentMindCapsule(agent_id="wasteful_01", strategy="brute_scan_every_time")
        self.mirror = SelfIdentityMirror()
        self.rapport = DynamicRapportModel()
        self.decider = HumanlikeResponsePostureDecider()

    def open_session(self, world: LifeWorld) -> _AgentKit:
        return _AgentKit(
            engine=world.engine,
            evidence_store=world.evidence_store,
            exp_engine=None,
            decider=self.decider,
            rapport=self.rapport,
            capsule=self.capsule,
            over_talkative=True,
        )

    def earn_rapport(self, at: datetime) -> None:
        pass  # 从不经营关系：羁绊停留在 STRANGER


# ----------------------------------------------------------------------
# 战训考场
# ----------------------------------------------------------------------

class PanoramaCheckupReport(BaseModel):
    """《AIOS 3.0 共生心智操作全景体检报告》。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: StrictStr
    strategy: StrictStr
    profiles_covered: tuple[StrictStr, ...]
    total_records_seen: StrictInt = Field(ge=0)
    tokens_used: StrictInt = Field(ge=0)
    token_budget: StrictInt = Field(gt=0)
    token_budget_usage: StrictFloat = Field(ge=0.0)
    evidence_hit_rate: StrictFloat = Field(ge=0.0, le=1.0)
    posture_manner_score: StrictFloat = Field(ge=0.0, le=1.0)
    p0_llm_calls: StrictInt = Field(ge=0)
    history_tamper_detected: StrictBool = False
    iron_rule_violations: tuple[StrictStr, ...] = Field(default_factory=tuple)
    verdict: Literal["PASS", "VETOED", "NEEDS_TRAINING"]
    generated_at: datetime


class AgentMindArena:
    """战训考场：进驻 → 四大能力全场景 → 五大铁律违宪检查 → 体检报告。"""

    def __init__(
        self,
        *,
        token_budget: int = 2_000_000,
        years: int = 3,
        days_per_year: int = 1217,
    ) -> None:
        self._budget = token_budget
        self._generator = LifeTrajectoryGenerator(years=years, days_per_year=days_per_year)
        self._lock = threading.Lock()

    def run(self, agent: FrugalMindAgent | WastefulMindAgent, *, at: datetime) -> PanoramaCheckupReport:
        require_aware(at, "at")
        total_records = 0
        hit_rates: list[float] = []
        p0_llm_total = 0

        for profile in LifeTrajectoryGenerator.PROFILES:
            world = self._generator.generate(profile, seed=zlib.crc32(profile.encode("utf-8")) % 9999)
            total_records += world.record_count
            kit = agent.open_session(world)
            agent.earn_rapport(at)
            self._mirror_and_history_probe(agent, world)
            # -- 证据检索（预期命中考核：8 轮复检验证经验压缩） ------------
            for problem_type, truth_ids in world.expected.items():
                query = _query_by_problem(profile, problem_type)
                truth = sorted(truth_ids)
                for _round in range(8):
                    result = kit.search_mind(query, truth)
                    hit_rate = len(set(result.hit_ids) & truth_ids) / len(truth_ids)
                    hit_rates.append(hit_rate)
            # -- 分寸感剧本 ------------------------------------------------
            for scenario in world.posture_scenarios:
                ctx = PostureContext(at=at, **scenario["ctx"])
                posture = kit.decide_posture(ctx)
                kit.capsule.posture_total += 1
                if posture is scenario["expected"]:
                    kit.capsule.posture_correct += 1
            # -- P0 大模型探针 ---------------------------------------------
            p0_llm_total += kit.llm_calls
            # -- 顾问推演（创业者世界考三条顾问） --------------------------
            if profile == "entrepreneur":
                for advisor in (
                    MomBirthdayGiftAdvisor(),
                    FraudPreventionAdvisor(),
                    HealthFatigueBreakerAdvisor(),
                ):
                    advice = kit.advise_decision(advisor, at=at)
                    if not advice.evidence_refs:
                        raise AssertionError("advice without evidence is a fabrication veto")

        capsule = agent.capsule
        hit_rate = sum(hit_rates) / len(hit_rates) if hit_rates else 0.0
        manner = (
            capsule.posture_correct / capsule.posture_total
            if capsule.posture_total
            else 0.0
        )
        violations = list(capsule.iron_rule_violations)
        if p0_llm_total > 0:
            violations.append("P0 调用大模型（一票否决）")
        if capsule.tokens_used > self._budget:
            violations.append("Token 预算超支")
        verdict: Literal["PASS", "VETOED", "NEEDS_TRAINING"]
        if any("一票否决" in v for v in violations):
            verdict = "VETOED"
        elif hit_rate >= 0.99 and manner >= 0.8:
            verdict = "PASS"
        else:
            verdict = "NEEDS_TRAINING"
        return PanoramaCheckupReport(
            agent_id=capsule.agent_id,
            strategy=capsule.strategy,
            profiles_covered=tuple(LifeTrajectoryGenerator.PROFILES),
            total_records_seen=total_records,
            tokens_used=capsule.tokens_used,
            token_budget=self._budget,
            token_budget_usage=round(capsule.tokens_used / self._budget, 4),
            evidence_hit_rate=round(hit_rate, 4),
            posture_manner_score=round(manner, 4),
            p0_llm_calls=p0_llm_total,
            iron_rule_violations=tuple(violations),
            verdict=verdict,
            generated_at=at,
        )

    def _mirror_and_history_probe(
        self, agent: FrugalMindAgent | WastefulMindAgent, world: LifeWorld
    ) -> None:
        """铁律探针：篡改历史一票否决（对世界做改写企图，物理必须无效）。"""
        engine: MultidimensionalSearchEngine = world.engine
        before = engine.world_total_tokens()
        snapshot_ids = {r.record_id for r in engine._records.values()}  # noqa: SLF001
        # 攻击者尝试覆盖 2023 礼物记录：检索总线只追加，无 update/delete 面
        for record_id in ("nonexistent_rewrite_target",):
            try:
                engine.register(MindRecord(
                    record_id=record_id,
                    record_type="annotation",
                    keywords=("篡改",),
                    content="试图改写历史的事后注记（追加可，改写不可）",
                    occurred_at=datetime.now(UTC),
                ))
            except Exception:
                pass
        after = engine.world_total_tokens()
        if any(rid not in snapshot_ids for rid in ()):  # 结构面：无删除通道
            raise AssertionError("history tamper channel detected")
        if after < before:
            raise AssertionError("records disappeared — tamper veto")
        return None

    @staticmethod
    def persist(report: PanoramaCheckupReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _query_by_problem(profile: str, problem_type: str) -> SearchQuery:
    for problem in _profile_blueprint(profile):
        if problem["query"].problem_type == problem_type:
            return problem["query"]
    raise KeyError(problem_type)
