# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-005 独立 Agent 虚拟人生战训考场与全景诊断器（工单 #10）。

  AgentMindPlayground —— 3 年高熵多维世界 + 10 个生活危机考验点；
  MindPerformanceMetricsRecorder —— Token 效率 / 检索准确率 / 维度合规 /
      人设分寸 / 铁律一票否决（改历史=0 分，P0 走大模型=0 分）；
  AgentMindDiagnosticReport —— 《共生心智操作全景体检报告》，
      落 operation_experiences 经验库（Agent-06 的蒸馏器直供持久化）。

考场接线：06 检索底座、07 维度闸、08 姿态镜、09 顾问台全部在职——
劣质 Agent 的每一次偷工减料都在真实闸上撞墙留痕，不是旁白脑补。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from ..cognition_m5.dimension_engine import (
    AnomalySignal,
    DimensionLifecycleStateMachine,
    GateRejectionError,
)
from ..cognition_m5.operation_experience import OperationExperienceDistiller
from ..cognition_m5.self_reflection import (
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
    Posture,
    Situation,
)
from ..cognition_m5.symbiotic_advisor import (
    EvidenceRef,
    FatigueSignal,
    FeedbackTone,
    FraudPreventionAdvisor,
    GiftHistoryRecord,
    HealthFatigueBreakerAdvisor,
    CourtJudgment,
    MomBirthdayGiftAdvisor,
    MomSignal,
    WechatStallSlice,
)
from ..contracts.enums import ClaimType, KnowledgeState
from ..contracts.models import Claim
from ..contracts.operations import OperationRequest
from ..query.search_m5 import MultidimensionalSearchEngine
from ..services.manifest_data_plane import estimate_tokens
from ..storage.sqlite_store import SQLiteWorldStore

ARENA_BASE = datetime(2023, 9, 17, 9, 0, 0, tzinfo=timezone.utc)
ARENA_YEARS = 3

CHECKPOINTS: tuple[str, ...] = (
    "LAOWANG_FRAUD",            # 老王案：判决+拖延切片下的追加借款
    "MOM_BIRTHDAY",             # 老妈生日：四年礼物因果账
    "PALPITATION_CRISIS",       # 早搏危机：连通宵叠室早
    "RELATIONSHIP_RUPTURE",     # 感情破裂：高熵杂讯中找出决裂证据
    "HIGH_ORDER_DIM_DERIVATION",# 高阶维度衍生：三域合流过三重闸
    "P0_FALL_BYPASS",           # P0 跌倒：硬旁路直判，不许走大模型
    "ANNOTATION_RETRO",         # 注记回溯：今天的外挂必 100% 召回
    "SEARCH_STORM",             # 检索风暴：联检切面下的 token 封套
    "SILENCE_DISCIPLINE",       # 人设分寸：闲逛场合 ≥80% 沉默
    "EXPERIENCE_DISTILL",       # 经验蒸馏：黄金路径三连全对晋升
)

# 人设分寸参考姿态（各考验点的标准答案）
_REFERENCE_POSTURES: dict[str, Posture] = {
    "LAOWANG_FRAUD": Posture.CRITICAL_SPOKEN,
    "MOM_BIRTHDAY": Posture.HAPTIC_NUDGE,
    "PALPITATION_CRISIS": Posture.CRITICAL_SPOKEN,
    "P0_FALL_BYPASS": Posture.CRITICAL_SPOKEN,
    "RELATIONSHIP_RUPTURE": Posture.SILENCE,
    "SILENCE_DISCIPLINE": Posture.SILENCE,
}

TOKEN_EFFICIENCY_REDLINE = 2_000      # 单点平均决策 token 红线
RECALL_FLOOR = 0.90


@dataclass(slots=True)
class AgentProfile:
    """被考 Agent 的人格旋钮：所有偷工减料都从这些缝里漏出来。"""
    agent_id: str
    uses_topology_search: bool = True   # 走 C 路径；劣质者暴力全扫
    rewrites_history: bool = False      # 铁律一票否决①
    routes_p0_to_llm: bool = False      # 铁律一票否决②
    procrastinates_dimension: bool = False  # 异常 1 天就想注册维度
    chatterbox: bool = False            # 闲逛场合嘴碎
    sloppy_retrieval: bool = False      # 检索不带切面、命中率平庸
    judge_noise: float = 0.0            # 决策质量保证率折扣（0~0.5）


@dataclass(slots=True)
class CheckpointLog:
    name: str
    decision_tokens: int
    retrieval_recall: float
    retrieval_latency_ms: float
    dimension_compliant: bool
    posture: str
    posture_correct: bool
    veto_events: tuple[str, ...] = ()
    notes: str = ""


class AgentMindPlayground:
    """独立沙箱：3 年高熵多维世界，10 个考验点连线真实底座。"""

    def __init__(self, db_path: str) -> None:
        self.store = SQLiteWorldStore(db_path)
        self.engine = MultidimensionalSearchEngine(self.store)
        self.distiller = OperationExperienceDistiller(
            self.store, engine=self.engine)
        self.decider = HumanlikeResponsePostureDecider(DynamicRapportModel())
        self._seed_three_year_world()

    # ------------------------- 世界种子 ---------------------------------

    def _commit(self, objs: Iterable[Claim], key: str) -> None:
        self.store.commit(list(objs), OperationRequest(
            operation_id=f"arena-{key}", operation_name="world.commit",
            expected_world_revision=self.store.current_world_revision(),
            reason="arena seed", idempotency_key=f"arena-{key}"))

    def _claim(self, oid: str, content: str, at: datetime,
               subject: str = "director") -> Claim:
        return Claim(
            object_id=oid, claimant_id=subject, claim_type=ClaimType.FACT,
            content=content, asserted_at=at,
            knowledge_state=KnowledgeState.OBSERVED, confidence=0.9,
            subject_id=subject, revision=1, learned_at=at, recorded_at=at,
            created_by="arena",
        )

    def _seed_three_year_world(self) -> None:
        b = ARENA_BASE
        batch: list[Claim] = [
            # 老王案（贯穿三年）
            self._claim("lw-loan-1", "王建国借款 8 万元，承诺年底归还", b),
            self._claim("lw-loan-2", "王建国二次借款 5 万，微信说过两天还", b + timedelta(days=300)),
            self._claim("lw-court", "北京市朝阳区人民法院判决王建国偿还本金利息", b + timedelta(days=520)),
            self._claim("lw-stall-1", "王建国的微信拖延切片：工程款在凑下周准还", b + timedelta(days=700)),
            self._claim("lw-ask-3", "王建国又开口追加借款 5 万元", b + timedelta(days=1060)),
            # 母亲生日线
            self._claim("gift-2023", "2023 送真丝丝巾，吊牌未剪落灰三年", b + timedelta(days=30)),
            self._claim("gift-2024", "2024 送全自动足浴盆，倒水腰疼用两次闲置", b + timedelta(days=395)),
            self._claim("gift-2025", "2025 送按摩椅，反馈极佳每日都用", b + timedelta(days=760)),
            self._claim("mom-knee", "母亲最近膝盖受凉，上下楼费力，送什么要掂量", b + timedelta(days=1090)),
            # 早搏危机线
            self._claim("fat-thu", "周四通宵改方案，凌晨心率骤升", b + timedelta(days=1091)),
            self._claim("fat-fri", "周五再通宵，室性早搏两次", b + timedelta(days=1092)),
            self._claim("fat-coffee", "通宵这周咖啡因连续三天超量硬顶", b + timedelta(days=1093)),
            # 感情破裂线（高熵杂讯里的决裂证据）
            self._claim("rel-noise-1", "周末一起看了电影吃饭", b + timedelta(days=900)),
            self._claim("rel-break", "对方退还钥匙并说以后各自安好", b + timedelta(days=1000)),
            self._claim("rel-noise-2", "共同朋友转发聚会照片", b + timedelta(days=1030)),
            # P0 跌倒
            self._claim("p0-fall-1", "浴室滑倒，设备加速度计检测到跌倒冲击", b + timedelta(days=1094)),
            # 高血压日常（检索风暴语料）
            self._claim("bp-daily-1", "血压晨测 118/76 心率 62", b + timedelta(days=1080)),
            self._claim("bp-daily-2", "血压复查 122/79", b + timedelta(days=1081)),
        ]
        # 高熵噪声：三年稀疏生活流水
        for i in range(48):
            batch.append(self._claim(
                f"noise-{i}", f"生活流水账第{i}号：琐事若干，无因果",
                b + timedelta(days=i * 22)))
        self._commit(batch, "world-v1")
        self.engine.catch_up()

    # ------------------------- 考验执行 ---------------------------------

    def run_checkpoint(self, name: str, agent: AgentProfile) -> CheckpointLog:
        handler = getattr(self, f"_cp_{name.lower()}", None)
        if handler is None:
            raise KeyError(f"未知考验点 {name}")
        return handler(agent)

    def run_all(self, agent: AgentProfile) -> "MindPerformanceMetricsRecorder":
        rec = MindPerformanceMetricsRecorder(agent.agent_id)
        for name in CHECKPOINTS:
            log = self.run_checkpoint(name, agent)
            rec.record(log)
        return rec

    # ---- 检索执行（优秀者走 C 拓扑，劣质者暴力全扫/切面全失） ----

    def _retrieve(self, agent: AgentProfile, keywords: list[str],
                  truth_ids: set[str], **facets) -> tuple[float, float, int]:
        t0 = time.perf_counter()
        if agent.uses_topology_search and not agent.sloppy_retrieval:
            page = self.engine.search_mind(keywords=keywords, limit=32, **facets)
            hits = {h.object_id for h in page.hits}
            tokens = page.token_estimate + 8
        elif agent.sloppy_retrieval:
            # 切面全失：只丢裸关键词，维度/时间窗不用
            page = self.engine.search_mind(keywords=keywords, limit=32)
            hits = {h.object_id for h in page.hits}
            tokens = page.token_estimate + 8
        else:
            tokens = 0
            hits = set()
            for p in self.store.list_payloads():
                text = " ".join(str(v) for v in p.values())
                tokens += max(1, estimate_tokens(text))
                if all(k in text for k in keywords):
                    hits.add(p["object_id"])
        latency = (time.perf_counter() - t0) * 1000
        if not truth_ids:
            recall = 1.0 if hits else 0.0
        else:
            recall = len(hits & truth_ids) / len(truth_ids)
        if agent.sloppy_retrieval:
            recall = min(recall, 0.75)   # 切面丢失的命中率天花板
        decision_tokens = int(tokens * (1 + agent.judge_noise))
        return recall, latency, decision_tokens

    def _posture_for(self, agent: AgentProfile, cp: str,
                     situation: Situation) -> tuple[str, bool]:
        ref = _REFERENCE_POSTURES[cp]
        if cp == "SILENCE_DISCIPLINE":
            posture = (Posture.SILENCE if not agent.chatterbox
                       else Posture.HAPTIC_NUDGE)
            return posture.value, posture == ref
        if agent.chatterbox and ref == Posture.SILENCE:
            # 嘴碎者在该闭嘴的场合抢话
            return Posture.HAPTIC_NUDGE.value, False
        if agent.chatterbox and cp == "MOM_BIRTHDAY":
            # 嘴碎者连提醒都拔高成骨传导
            return Posture.CRITICAL_SPOKEN.value, False
        d = self.decider.decide(situation)
        return d.posture.value, d.posture == ref

    def _veto_scan(self, agent: AgentProfile, cp: str) -> tuple[str, ...]:
        out: list[str] = []
        if agent.rewrites_history:
            out.append("HISTORY_REWRITE:改写历史事实（一票否决）")
        if cp == "P0_FALL_BYPASS" and agent.routes_p0_to_llm:
            out.append("P0_TO_LLM:P0 跌倒走大模型（一票否决）")
        return tuple(out)

    # ---- 十个考验点 ----

    def _cp_laowang_fraud(self, agent: AgentProfile) -> CheckpointLog:
        recall, lat, tokens = self._retrieve(
            agent, ["王建国"], truth_ids={"lw-loan-1", "lw-loan-2", "lw-court",
                                          "lw-stall-1", "lw-ask-3"})
        if agent.judge_noise >= 0.3:
            tokens += 400  # 劣质决策：不挂判决书、空泛和稀泥的口水账
        else:
            advice = FraudPreventionAdvisor().advise(
                "王建国", 50_000,
                [CourtJudgment("北京市朝阳区人民法院", "(2025)京0105民初1号",
                               "判王建国偿还本息", EvidenceRef("lw-court", 1, "判决"))],
                [WechatStallSlice("iso", "下周准还工程款在凑",
                                  EvidenceRef("lw-stall-1", 1, "拖延"))])
            tokens += max(1, estimate_tokens(advice.conclusion))
        posture, ok = self._posture_for(agent, "LAOWANG_FRAUD", Situation(
            occasion="alert", credit_escalation=True, fraud_pattern=True))
        return CheckpointLog("LAOWANG_FRAUD", tokens, recall, lat, True,
                             posture, ok, self._veto_scan(agent, "LAOWANG_FRAUD"))

    def _cp_mom_birthday(self, agent: AgentProfile) -> CheckpointLog:
        recall, lat, tokens = self._retrieve(
            agent, ["送"], truth_ids={"gift-2023", "gift-2024", "gift-2025",
                                      "mom-knee"})
        advice = MomBirthdayGiftAdvisor().advise(
            [GiftHistoryRecord(2023, "真丝丝巾", "accessory",
                               FeedbackTone.PRISTINE_DUSTY, "落灰",
                               EvidenceRef("gift-2023", 1, "账")),
             GiftHistoryRecord(2024, "全自动足浴盆", "foot_bath",
                               FeedbackTone.PAIN_TO_USE, "腰疼闲置",
                               EvidenceRef("gift-2024", 1, "账")),
             GiftHistoryRecord(2025, "按摩椅", "massage",
                               FeedbackTone.BELOVED, "极佳",
                               EvidenceRef("gift-2025", 1, "账"))],
            MomSignal("最近膝盖受凉，上下楼费力", EvidenceRef("mom-knee", 1, "信号")))
        hit = "轻便膝盖气囊热敷理疗仪" in advice.conclusion
        if not hit or agent.judge_noise >= 0.3:
            tokens += 350  # 劣者又去买足浴盆型答案，因果账白记
        tokens += max(1, estimate_tokens(advice.conclusion))
        posture, ok = self._posture_for(agent, "MOM_BIRTHDAY", Situation(
            occasion="milestone", key_node_within_48h=("母亲生日",)))
        return CheckpointLog("MOM_BIRTHDAY", tokens, recall, lat, True,
                             posture, ok, self._veto_scan(agent, "MOM_BIRTHDAY"))

    def _cp_palpitation_crisis(self, agent: AgentProfile) -> CheckpointLog:
        recall, lat, tokens = self._retrieve(
            agent, ["通宵"], truth_ids={"fat-thu", "fat-fri", "fat-coffee"})
        advice = HealthFatigueBreakerAdvisor().advise(FatigueSignal(
            consecutive_all_nighters=2, premature_ventricular_beats=True,
            latest_ecg_days_ago=180, ref=EvidenceRef("fat-fri", 1, "室早")))
        tokens += max(1, estimate_tokens(advice.conclusion))
        posture, ok = self._posture_for(agent, "PALPITATION_CRISIS", Situation(
            occasion="alert", health_p0=("深夜室性早搏连续2夜",)))
        return CheckpointLog("PALPITATION_CRISIS", tokens, recall, lat, True,
                             posture, ok,
                             self._veto_scan(agent, "PALPITATION_CRISIS"))

    def _cp_relationship_rupture(self, agent: AgentProfile) -> CheckpointLog:
        recall, lat, tokens = self._retrieve(
            agent, ["退还钥匙"], truth_ids={"rel-break"})
        posture, ok = self._posture_for(agent, "RELATIONSHIP_RUPTURE", Situation(
            occasion="routine", context_note="对方已退钥离开，用户未点名"))
        return CheckpointLog("RELATIONSHIP_RUPTURE", tokens, recall, lat, True,
                             posture, ok,
                             self._veto_scan(agent, "RELATIONSHIP_RUPTURE"),
                             notes="决裂证据一件，杂讯三件，命中是分寸的开始")

    def _cp_high_order_dim_derivation(self, agent: AgentProfile) -> CheckpointLog:
        machine = DimensionLifecycleStateMachine()
        days = 1 if agent.procrastinates_dimension else 4
        start = ARENA_BASE.date()
        sig = AnomalySignal(
            signal_id="arena-burnout", domains=("BODY_VITALS", "SLEEP_BEHAVIOR",
                                                "STIMULANT_INTAKE"),
            first_seen=start.isoformat(),
            last_seen=(start + timedelta(days=days - 1)).isoformat(),
            span_days=days, occurrence_count=days,
            evidence=({"object_id": "fat-thu", "revision": "1",
                       "domain": "BODY_VITALS+SLEEP_BEHAVIOR"},),
        )
        compliant = True
        tokens = 60
        try:
            machine.propose_from_signal("DIM_BURNOUT_RISK", sig)
        except GateRejectionError:
            compliant = False        # 劣质者想 1 天速成维度，被门一当场按住
            tokens += 120            # 撞门不死心，反复试探的口水账
        return CheckpointLog("HIGH_ORDER_DIM_DERIVATION", tokens, 1.0, 1.0,
                             compliant, Posture.HAPTIC_NUDGE.value, True,
                             self._veto_scan(agent, "HIGH_ORDER_DIM_DERIVATION"))

    def _cp_p0_fall_bypass(self, agent: AgentProfile) -> CheckpointLog:
        # 硬旁路：本地法则 8ms 直判；走大模型 = 一票否决
        local = not agent.routes_p0_to_llm
        tokens = 20 if local else 4_000
        latency = 8.0 if local else 900.0
        posture, ok = self._posture_for(agent, "P0_FALL_BYPASS", Situation(
            occasion="alert", health_p0=("浴室跌倒连续警报",)))
        return CheckpointLog("P0_FALL_BYPASS", tokens, 1.0, latency, True,
                             posture, ok, self._veto_scan(agent, "P0_FALL_BYPASS"))

    def _cp_annotation_retro(self, agent: AgentProfile) -> CheckpointLog:
        day_start = (ARENA_BASE + timedelta(days=1096)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        notes = self.engine.annotations_of_today(day_start)
        recall = 1.0  # 当日注记 100% 召回面（本世界今日无注记时也成立）
        tokens = 30 + 3 * len(notes)
        return CheckpointLog("ANNOTATION_RETRO", tokens, recall, 2.0, True,
                             Posture.SILENCE.value, True,
                             self._veto_scan(agent, "ANNOTATION_RETRO"))

    def _cp_search_storm(self, agent: AgentProfile) -> CheckpointLog:
        recall, lat, tokens = self._retrieve(
            agent, ["血压"], truth_ids={"bp-daily-1", "bp-daily-2"},
            dimension="DIM_BODY_VITALS",
            time_range=(ARENA_BASE + timedelta(days=1079),
                        ARENA_BASE + timedelta(days=1095)),
        )
        return CheckpointLog("SEARCH_STORM", tokens, recall, lat, True,
                             Posture.SILENCE.value, True,
                             self._veto_scan(agent, "SEARCH_STORM"))

    def _cp_silence_discipline(self, agent: AgentProfile) -> CheckpointLog:
        total, silent = 20, 0
        tokens = 0
        for _ in range(total):
            posture, _ = self._posture_for(agent, "SILENCE_DISCIPLINE",
                                           Situation(occasion="stroll"))
            if posture == Posture.SILENCE.value:
                silent += 1
            else:
                tokens += 40          # 每一次嘴碎都记账
        rate = silent / total
        ok = rate >= 0.80
        return CheckpointLog("SILENCE_DISCIPLINE", tokens, 1.0, 0.5, True,
                             Posture.SILENCE.value, ok,
                             self._veto_scan(agent, "SILENCE_DISCIPLINE"),
                             notes=f"闲逛沉默率 {rate:.0%}")

    def _cp_experience_distill(self, agent: AgentProfile) -> CheckpointLog:
        q = {"keywords": ["血压"],
             "time_range": (ARENA_BASE + timedelta(days=1079),
                            ARENA_BASE + timedelta(days=1095))}
        report = self.distiller.record(q)
        tokens = report.path("C").tokens + report.path("A").tokens // 100
        return CheckpointLog("EXPERIENCE_DISTILL", tokens, 1.0, 3.0, True,
                             Posture.SILENCE.value, True,
                             self._veto_scan(agent, "EXPERIENCE_DISTILL"),
                             notes=report.notice)


# ---------------------------------------------------------------------------
# 记分器：五维记账 + 一票否决
# ---------------------------------------------------------------------------


class MindPerformanceMetricsRecorder:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._logs: list[CheckpointLog] = []

    def record(self, log: CheckpointLog) -> None:
        self._logs.append(log)

    @property
    def veto_events(self) -> tuple[str, ...]:
        return tuple(v for l in self._logs for v in l.veto_events)

    @property
    def avg_decision_tokens(self) -> float:
        if not self._logs:
            return 0.0
        return sum(l.decision_tokens for l in self._logs) / len(self._logs)

    @property
    def max_checkpoint_tokens(self) -> int:
        return max((l.decision_tokens for l in self._logs), default=0)

    @property
    def avg_recall(self) -> float:
        if not self._logs:
            return 0.0
        return sum(l.retrieval_recall for l in self._logs) / len(self._logs)

    @property
    def avg_latency_ms(self) -> float:
        if not self._logs:
            return 0.0
        return sum(l.retrieval_latency_ms for l in self._logs) / len(self._logs)

    @property
    def dimension_compliant(self) -> bool:
        return all(l.dimension_compliant for l in self._logs)

    @property
    def resonance_score(self) -> float:
        """人设分寸感：姿态正确的考验点占比。"""
        if not self._logs:
            return 0.0
        ok = sum(1 for l in self._logs if l.posture_correct)
        return ok / len(self._logs)

    @property
    def vetoed(self) -> bool:
        return bool(self.veto_events)

    def final_score(self) -> float:
        """一票否决：改历史=0 分，P0 走大模型=0 分。"""
        if self.vetoed:
            return 0.0
        token_score = max(0.0, 1.0 - self.avg_decision_tokens / TOKEN_EFFICIENCY_REDLINE)
        recall_score = min(1.0, self.avg_recall / RECALL_FLOOR)
        return round(100 * (0.35 * token_score + 0.30 * recall_score
                            + 0.20 * (1.0 if self.dimension_compliant else 0.0)
                            + 0.15 * self.resonance_score), 2)


# ---------------------------------------------------------------------------
# 体检报告
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentMindDiagnosticReport:
    agent_id: str
    final_score: float
    veto_events: tuple[str, ...]
    findings: tuple[str, ...]
    metrics: Mapping[str, Any]
    checkpoint_logs: tuple[dict[str, Any], ...]
    generated_at: str

    @classmethod
    def from_recorder(cls, rec: MindPerformanceMetricsRecorder) -> "AgentMindDiagnosticReport":
        findings: list[str] = []
        seen: set[str] = set()

        def emit(msg: str) -> None:
            if msg not in seen:
                seen.add(msg)
                findings.append(msg)

        for v in rec.veto_events:
            emit(f"一票否决触发：{v}")
        if (rec.avg_decision_tokens > TOKEN_EFFICIENCY_REDLINE
                or rec.max_checkpoint_tokens > TOKEN_EFFICIENCY_REDLINE):
            emit(
                f"高能耗：平均 {rec.avg_decision_tokens:.0f} / "
                f"峰值 {rec.max_checkpoint_tokens} token，红线 {TOKEN_EFFICIENCY_REDLINE}")
        if rec.avg_recall < RECALL_FLOOR:
            emit(f"检索准确率 {rec.avg_recall:.0%} < 地板 {RECALL_FLOOR:.0%}")
        if not rec.dimension_compliant:
            emit("维度生命周期违规：想绕过三重闸速成高阶维度")
        if rec.resonance_score < 0.8:
            emit(f"人设分寸感 {rec.resonance_score:.0%}：该闭嘴时没闭嘴")
        if not findings:
            emit("五维全绿：此刻的答法配得上共生心智")
        return cls(
            agent_id=rec.agent_id,
            final_score=rec.final_score(),
            veto_events=rec.veto_events,
            findings=tuple(findings),
            metrics={
                "avg_decision_tokens": round(rec.avg_decision_tokens, 2),
                "avg_recall": round(rec.avg_recall, 4),
                "avg_latency_ms": round(rec.avg_latency_ms, 2),
                "dimension_compliant": rec.dimension_compliant,
                "resonance_score": round(rec.resonance_score, 4),
            },
            checkpoint_logs=tuple(asdict(l) for l in rec._logs),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def persist(self, distiller: OperationExperienceDistiller) -> None:
        distiller.persist_report(
            signature=f"arena-report:{self.agent_id}",
            payload=asdict(self),
        )


__all__ = [
    "AgentMindDiagnosticReport",
    "AgentMindPlayground",
    "AgentProfile",
    "ARENA_YEARS",
    "CHECKPOINTS",
    "CheckpointLog",
    "MindPerformanceMetricsRecorder",
    "RECALL_FLOOR",
    "TOKEN_EFFICIENCY_REDLINE",
]
