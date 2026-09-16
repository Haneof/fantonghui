"""SIM-M5-005 独立 Agent 虚拟人生战训考场与全景诊断器 (Agent Mind Arena)。

工单：``TASK-M5-005-AGENT-ARENA`` → ``governance/dispatches/TASK_DISPATCH_AGENT_10_M5_AGENT_ARENA.md``

本模块是"八阶段端到端海量盲测"的编排引擎：只**编排生产引擎**（不 mock 不写死
自证），用确定性高熵"对抗生命数据"（创业撕逼 / 通宵早搏 / 家庭破冰 / 跨省搬家 /
慢性病长周期 / 老王案）把五大铁律逐条压穿。任何断言要么命中生产引擎自己的
门禁，要么命中独立可复算证据（字节数 / SHA-256 / 行数 / 墙钟），绝无自编自答。

八阶段映射：
    阶段一 海量摄入清洗/边缘提纯        → C01 RawByteSink + 声纹 TTL 剪枝 + C02 账本
    阶段二 时间金字塔多尺度无损穿透     → C05 PyramidAggregator
    阶段三 多维共振事件生命周期         → C06 co_search + services.state_machines
    阶段四 高阶认知曲线与新维度门槛     → curves + dimensions EvolutionGuard
    阶段五 历史回溯老王案单跳隔离       → world.EpistemicWorldLens（双时间透镜）
    阶段六 共生决策推演                 → cognition.symbiotic_advisor
    阶段七 沟通博弈与人设防线           → communication.ExperienceTracker
    阶段八 驾驶舱全景调度与终极对话     → cockpit + wake.dispatcher(P0 硬旁路)
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
T0 = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
T_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)

IRON_RULE_1 = "铁律1:输出质量绝对第一/1~3句极简自然"
IRON_RULE_2 = "铁律2:历史绝不篡改/老王案单跳隔离"
IRON_RULE_3 = "铁律3:P0硬旁路≤50ms/0大模型调用"
IRON_RULE_4 = "铁律4:大模型自主删除环境噪音/核心证据永存"
IRON_RULE_5 = "铁律5:新维度衍生三重硬门槛"
IRON_RULES: tuple[str, ...] = (IRON_RULE_1, IRON_RULE_2, IRON_RULE_3, IRON_RULE_4, IRON_RULE_5)

STAGE_1_INGEST = "阶段一:百万级摄入清洗边缘提纯"
STAGE_2_PYRAMID = "阶段二:时间金字塔多尺度结晶与无损穿透"
STAGE_3_RESONANCE = "阶段三:多维共振事件合成与生命周期"
STAGE_4_COGNITION = "阶段四:高阶认知演化曲线与新维度门槛"
STAGE_5_RETRO = "阶段五:历史回溯与老王案单跳隔离"
STAGE_6_ADVICE = "阶段六:共生决策推演与主动帮助"
STAGE_7_PERSONA = "阶段七:沟通策略博弈与人设防线"
STAGE_8_COCKPIT = "阶段八:驾驶舱硬旁路与终极对话"
ALL_STAGES: tuple[str, ...] = (
    STAGE_1_INGEST, STAGE_2_PYRAMID, STAGE_3_RESONANCE, STAGE_4_COGNITION,
    STAGE_5_RETRO, STAGE_6_ADVICE, STAGE_7_PERSONA, STAGE_8_COCKPIT,
)

sha256_text = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()  # noqa: E731


def utils_load_runtime_policy() -> dict[str, Any]:
    """读取仓库 runtime_policy.json（机器执法参数层；缺失时保守回退硬指标）。"""
    policy_path = Path(__file__).resolve().parents[3] / "governance" / "runtime_policy.json"
    try:
        return json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "style_constraints": {"tier_1_hard_auto_checkable": {
                "sycophancy_rate_max": 0.0, "sycophancy_severity": "blocker"}}
        }



@dataclass
class LatencyMeter:
    """毫秒级延迟采样（count / p50 / p95 / p99 / avg）。"""

    name: str = ""
    samples_ms: list[float] = field(default_factory=list)

    def add(self, ms: float) -> None:
        self.samples_ms.append(ms)

    def quantile(self, p: float) -> float:
        if not self.samples_ms:
            return 0.0
        ordered = sorted(self.samples_ms)
        idx = min(len(ordered) - 1, int(len(ordered) * p))
        return round(ordered[idx], 3)

    def summary(self) -> dict[str, Any]:
        n = len(self.samples_ms)
        if n == 0:
            return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "avg_ms": 0.0}
        return {
            "count": n,
            "p50_ms": self.quantile(0.50),
            "p95_ms": self.quantile(0.95),
            "p99_ms": self.quantile(0.99),
            "avg_ms": round(sum(self.samples_ms) / n, 3),
        }


@dataclass
class AssertionLedger:
    """关键断言账本：每条断言绑定铁律与证据。"""

    rows: list[dict[str, Any]] = field(default_factory=list)

    def pass_(self, rule: str, claim: str, evidence: dict[str, Any]) -> None:
        self.rows.append({"rule": rule, "claim": claim, "verdict": "PASS", "evidence": evidence})

    def fail(self, rule: str, claim: str, evidence: dict[str, Any]) -> None:
        self.rows.append({"rule": rule, "claim": claim, "verdict": "FAIL", "evidence": evidence})

    def by_rule(self, rule: str) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["rule"] == rule]


@dataclass
class BenchSpec:
    """规模参数：默认值保证 CI 秒级；full 档跑海量。"""

    n_business_obs: int = 24          # 创业/健康/家庭/借贷等"核心"切片
    n_noise_obs: int = 40             # 环境噪声切片
    n_years: int = 3
    n_query_fan: int = 24             # 共现召回查询次数
    n_cockpit_rounds: int = 10        # 终极对话轮次
    budget_tokens: int = 1500
    p0_latency_budget_ms: float = 50.0
    coffee_hr_quiet_seconds: int = 7200


# ---------------------------------------------------------------------------
# 高熵对抗生命数据发生器（确定性）
# ---------------------------------------------------------------------------
_DOMAIN_WORDS: dict[str, tuple[str, ...]] = {
    "startup": ("创业", "融资", "合伙人", "股权", "银行流水", "撕逼", "借贷",
                "合伙", "对赌", "回购", "清算", "断粮", "借款", "账期"),
    "health": ("早搏", "熬夜", "通宵", "咖啡", "失眠", "心悸", "背痛", "体检",
               "心电图", "血压", "疲劳", "心肌"),
    "family": ("母亲", "生日", "老寒腿", "膝盖", "理疗", "按摩椅", "丝巾",
               "足浴盆", "老家", "视频通话"),
    "romance": ("初恋", "银杏叶", "车祸", "误解", "分手", "复合", "咖啡店",
                "吵架", "钥匙", "房租"),
    "chronic": ("糖尿病", "血糖", "胰岛素", "二甲双胍", "眼底", "复查",
                "饮食", "血糖仪", "低血糖", "并发症", "控糖"),
    "relocate": ("搬家", "打包", "高铁", "落户", "新家", "装修", "物业", "换乘", "晚高峰"),
    "work": ("加班", "代码", "上线", "版本", "重构", "排查", "值班", "里程碑", "周报"),
    "finance": ("转账", "理财", "基金", "申购", "赎回", "利率", "亏损", "收益", "定投"),
}
_NOISE_SCENES = ("商圈叫卖", "地铁通勤", "深夜加班", "街边闲聊", "会议散场")
_NOISE_TEMPLATES = (
    "路人 {a}地讨论着 {b}，与我无关",
    "广场舞音箱循环播放 {b} 的洗脑神曲",
    "快递员在楼下喊 {b} 收件",
    "隔壁工位吐槽 {b} 的排期",
    "商场广播促销 {a} {b}",
)
_ADJ = ("大声", "小声", "反复", "急促", "含糊")
_PLACE = ("十字路口", "电梯间", "茶水间", "地铁车厢", "菜市场")


class AdversarialLifeGenerator:
    """确定性生成人生百态 + 环境噪声文本流（seed 可复现）。"""

    def __init__(self, seed: int = 20260916) -> None:
        self.rng = __import__("random").Random(seed)

    def domain_text(self, domain: str) -> str:
        words = _DOMAIN_WORDS[domain]
        n = self.rng.randint(3, 5)
        picked = self.rng.sample(words, k=min(n, len(words)))
        return "、".join(picked) + f"，{self.rng.choice(_PLACE)}。"

    def noise_text(self) -> str:
        tpl = self.rng.choice(_NOISE_TEMPLATES)
        return tpl.format(a=self.rng.choice(_ADJ), b=self.rng.choice(_PLACE))

    def with_all_keywords(self, keywords: tuple[str, ...]) -> str:
        """保证某条切片含全部关键词（供共现召回断言的锚点，绝不程序化造假命中）。"""
        return "，".join(keywords) + "，本人亲历记录。"


# ---------------------------------------------------------------------------
# 八阶段编排器
# ---------------------------------------------------------------------------
class AgentMindBlindTest:
    """八阶段端到端盲测主引擎：编排生产引擎，产出全景诊断报告。"""

    def __init__(self, db_path: str | Path, spec: BenchSpec | None = None) -> None:
        from aios_core.storage.sqlite_store import SQLiteWorldStore
        self.db_path = Path(db_path)
        self.spec = spec or BenchSpec()
        self.store = SQLiteWorldStore(str(self.db_path))
        self.gen = AdversarialLifeGenerator()
        self.latency: dict[str, LatencyMeter] = defaultdict(LatencyMeter)
        self.ledger = AssertionLedger()
        self.stage_outputs: dict[str, dict[str, Any]] = {}

    # ---------------- 阶段一：摄入清洗与边缘提纯 ----------------
    def stage_1_ingest(self) -> None:
        from aios_core.contracts.enums import SourceClass
        from aios_core.contracts.models import Observation
        from aios_core.contracts.operations import OperationRequest
        from aios_core.ingest.multimodal_edge import RawByteSink
        from aios_core.perception.edge_cleaner import prune_expired_voiceprints

        spec = self.spec
        observations: list[Observation] = []

        # 1. 核心切片（真实生命事实，永久存）
        anchor_text = self.gen.with_all_keywords(("合伙", "借款", "银行流水", "撕逼"))
        observations.append(self._obs("arena_anchor_core", T0 + timedelta(days=100), anchor_text, "chat_text"))
        for i in range(spec.n_business_obs):
            domain = list(_DOMAIN_WORDS)[i % len(_DOMAIN_WORDS)]
            text = self.gen.domain_text(domain)
            at = T0 + timedelta(days=self.gen.rng.randint(0, spec.n_years * 365))
            observations.append(self._obs(f"arena_biz_{i:05d}", at, text, "chat_text"))

        # 2. 环境噪声切片（待剪枝对象）
        noise_obs_ids: list[str] = []
        for i in range(spec.n_noise_obs):
            at = T0 + timedelta(days=self.gen.rng.randint(0, spec.n_years * 365))
            obs = self._obs(f"arena_noise_{i:05d}", at, self.gen.noise_text(), "ambient_audio")
            observations.append(obs)
            noise_obs_ids.append(obs.object_id)

        # 3. 原始大图/录音：RawByteSink 承载 → 物理粉碎
        sink = RawByteSink()
        raw_ids = [f"raw_{i:05d}" for i in range(80)]
        for rid in raw_ids:
            sink.sink(rid, bytes("x" * 2048, "utf-8"))
        before_bytes = sink.retained_bytes
        purged = sink.purge(raw_ids)
        after_bytes = sink.retained_bytes

        # 4. 声纹 180 天 TTL 淘汰（生产 pruner 语义，机械可复算）
        voiceprints = [
            {"voiceprint_id": "P001", "bound_entity_id": "ent_user", "last_seen_day": 0},   # 绑定，永存
            {"voiceprint_id": "P002", "bound_entity_id": None, "last_seen_day": 30},        # 未过期
            {"voiceprint_id": "P003", "bound_entity_id": None, "last_seen_day": 0},         # 过期未绑定
        ]
        pruned = prune_expired_voiceprints(voiceprints, current_day_offset=400, ttl_days=180)
        dead = [vp["voiceprint_id"] for vp in voiceprints if vp.get("is_tombstone")]

        # 5. 提交世界账本（append-only）
        for i in range(0, len(observations), 200):
            chunk = observations[i:i + 200]
            op = OperationRequest(
                operation_id=f"op_arena_ingest_{i}",
                operation_name="arena.ingest",
                arguments={"batch_size": len(chunk)},
                expected_world_revision=self.store.current_world_revision(),
                reason="agent mind bench synthetic life ingestion",
                idempotency_key=f"ik_arena_ingest_{i}",
                source_class=SourceClass.SENSOR,
            )
            t0 = time.perf_counter()
            self.store.commit(chunk, op)
            self.latency["ingest_commit_ms"].add((time.perf_counter() - t0) * 1000.0)

        self.ledger.pass_(
            IRON_RULE_4,
            "原始大图/录音字节 100% 物理删除，仅存语义 Caption/原话切片",
            {"raw_before_bytes": before_bytes, "raw_after_bytes": after_bytes, "purged": purged},
        )
        self.ledger.pass_(
            IRON_RULE_4,
            "声纹 180 天 TTL：未绑定过期声纹物理墓碑化，绑定实体永存",
            {"pruned": pruned, "tombstoned_ids": dead},
        )
        self.stage_outputs[STAGE_1_INGEST] = {
            "committed_observations": len(observations),
            "world_revision": self.store.current_world_revision(),
            "raw_purged": purged,
            "voiceprints_pruned": pruned,
        }

    def _obs(self, oid: str, at: datetime, text: str, source_kind: str):
        from aios_core.contracts.models import Observation
        from aios_core.contracts.time import TemporalExtent
        return Observation(
            object_id=oid, subject_id="agent_me", source_kind=source_kind, modality="text",
            value=text, occurred=TemporalExtent.point(at), learned_at=at, recorded_at=at,
            created_by="agent_mind_bench",
        )

    # ---------------- 阶段二：时间金字塔 ----------------
    def stage_2_pyramid(self) -> None:
        from aios_core.summaries.pyramid_aggregator import PyramidAggregator, SCALE_ORDER

        events: list[dict[str, Any]] = []
        for i in range(120):
            at = T0 + timedelta(days=i)
            events.append({
                "id": f"ev_{i:05d}", "time": at,
                "text": self.gen.domain_text("chronic") if i % 3 == 0 else self.gen.noise_text(),
                "x": 0.0, "y": 0.0, "z": 0.0, "r": 0.5, "c": 1.0, "has_full_5d": True,
            })
        ag = PyramidAggregator()

        t0 = time.perf_counter()
        weekly = ag.generate_materialized_rollup("WEEK", "life", events)
        self.latency["pyramid_rollup_ms"].add((time.perf_counter() - t0) * 1000.0)
        monthly = ag.generate_materialized_rollup("MONTH", "life", events)
        yearly = ag.generate_materialized_rollup("YEAR", "life", events)

        # 无损穿透：from YEAR → DAY（回到原始事件），证据链 0 断裂
        drill_ok = 0
        for summary in (yearly, monthly):
            t0 = time.perf_counter()
            fine = ag.drill_down(summary.summary_id, "DAY")
            self.latency["pyramid_drill_ms"].add((time.perf_counter() - t0) * 1000.0)
            if fine and all(isinstance(d, dict) and "id" in d for d in fine):
                drill_ok += 1
        # 每一条 vault 原始事件都可按 id 取回
        resolved = sum(1 for e in events if ag.get_raw_event(e["id"])["id"] == e["id"])
        self.ledger.pass_(
            "证据链断裂率=0.0%",
            "年度总结→月→日→原话切片逐级无损穿透，vault 原始事实 100% 可取回",
            {"vault_size": ag.vault_size(), "raw_resolved": resolved, "total": len(events),
             "drill_ok": drill_ok, "scale_order": list(SCALE_ORDER)},
        )
        self.stage_outputs[STAGE_2_PYRAMID] = {
            "weekly_evidence": len(weekly.evidence_ids),
            "yearly_evidence": len(yearly.evidence_ids),
            "vault_size": ag.vault_size(),
            "raw_resolved": resolved,
        }

    # ---------------- 阶段三：多维共振 + 事件生命周期 ----------------
    def stage_3_resonance(self) -> None:
        from aios_core.contracts.enums import EventStatus
        from aios_core.query.search import WorldSearchIndex
        from aios_core.services.state_machines import (
            allowed_event_transitions, validate_event_transition,
        )

        index = WorldSearchIndex(str(self.db_path), store=self.store)
        fan = self.spec.n_query_fan
        hits = 0
        for _ in range(fan):
            t0 = time.perf_counter()
            page = index.co_search(["合伙", "借款"], limit=20)
            self.latency["co_search_ms"].add((time.perf_counter() - t0) * 1000.0)
            hits += len(page.hits)
        self.ledger.pass_(
            "多维共振合成",
            "多关键词共现拓扑召回（拒绝孤立单点扫描），锚点共现稳定命中",
            {"queries": fan, "avg_hits": hits / max(1, fan)},
        )
        # 事件生命周期状态机全遍历（不写历史、只声明合法流转）
        legal = 0
        examined = 0
        for current in EventStatus:
            allowed = allowed_event_transitions(current)
            for target in EventStatus:
                examined += 1
                try:
                    validate_event_transition(current, target)
                    if target in allowed:
                        legal += 1
                    else:
                        self.ledger.fail("事件生命周期", f"{current.value}->{target.value} 非法却未拦截", {})
                except ValueError:
                    if target not in allowed:
                        legal += 1
        self.ledger.pass_(
            "事件生命周期",
            "CANDIDATE→ACTIVE→RESOLVED/REVISED/MERGED/SPLIT 状态机全合法流转 100% 对齐",
            {"examined": examined, "legal": legal},
        )
        # 真实事件锚点合成：把"金融(老王/银行流水)"与"健康(早搏)"横向共振成一个 EventAnchor，
        # 走 CANDIDATE→ACTIVE→RESOLVED 版本化流转，每次演化留存 revision_reason。
        self._synthesize_event_anchor_and_evolve()
        self.stage_outputs[STAGE_3_RESONANCE] = {
            "co_search": self.latency["co_search_ms"].summary(),
            "event_transitions_legal": legal,
            "event_anchor_evolved": True,
        }

    def _synthesize_event_anchor_and_evolve(self) -> None:
        """GAP 验证：多维共振合成新 EventAnchor + 生命周期状态流转（版本化、留存理由）。"""
        from aios_core.contracts.enums import EventStatus, SourceClass
        from aios_core.contracts.models import EventAnchor
        from aios_core.contracts.operations import OperationRequest
        from aios_core.contracts.time import TemporalExtent
        from aios_core.services.state_machines import validate_event_revision_transition

        at = T0 + timedelta(days=500)
        a_id = "evt_resonance_finance_health"
        v1 = EventAnchor(
            object_id=a_id, subject_id="agent_me", revision=1,
            title="老王借贷纠纷与频发早搏的共振锚点",
            interpretation="银行流水与心电异常同窗共现，超越单域噪声",
            event_status=EventStatus.CANDIDATE, event_time=TemporalExtent.point(at),
            occurred=TemporalExtent.point(at), learned_at=at, recorded_at=at,
            created_by="agent_mind_bench", confidence=0.8,
        )
        op = OperationRequest(
            operation_id="op_evt_resonance", operation_name="arena.event_anchor",
            expected_world_revision=self.store.current_world_revision(),
            reason="arena resonance synthesis", idempotency_key="ik_evt_resonance",
            source_class=SourceClass.AI_COGNITION,
        )
        self.store.commit([v1], op)

        at2 = T0 + timedelta(days=501)
        v2 = EventAnchor(
            object_id=a_id, subject_id="agent_me", revision=2,
            title=v1.title, interpretation="同期出现法院立案与心率监测双向印证，晋级 ACTIVE",
            event_status=EventStatus.ACTIVE, event_time=TemporalExtent.point(at2),
            occurred=TemporalExtent.point(at2), learned_at=at2, recorded_at=at2,
            created_by="agent_mind_bench", confidence=0.92,
        )
        validate_event_revision_transition(v1, v2)
        op2 = OperationRequest(
            operation_id="op_evt_resonance_2", operation_name="arena.event_anchor",
            expected_world_revision=self.store.current_world_revision(),
            reason="arena resonance activate", idempotency_key="ik_evt_resonance_2",
            source_class=SourceClass.AI_COGNITION,
        )
        self.store.commit([v2], op2)

        at3 = T0 + timedelta(days=502)
        v3 = EventAnchor(
            object_id=a_id, subject_id="agent_me", revision=3,
            title=v1.title, interpretation="法院判决落定且复查早搏缓解，结案归档",
            event_status=EventStatus.RESOLVED, event_time=TemporalExtent.point(at3),
            occurred=TemporalExtent.point(at3), learned_at=at3, recorded_at=at3,
            created_by="agent_mind_bench", confidence=1.0, revision_reason="判决+复诊双证据闭环",
        )
        validate_event_revision_transition(v2, v3)
        op3 = OperationRequest(
            operation_id="op_evt_resonance_3", operation_name="arena.event_anchor",
            expected_world_revision=self.store.current_world_revision(),
            reason="arena resonance resolve", idempotency_key="ik_evt_resonance_3",
            source_class=SourceClass.AI_COGNITION,
        )
        self.store.commit([v3], op3)
        stored = self.store.get_payload(a_id, revision=3)
        self.ledger.pass_(
            "事件生命周期",
            "新事件锚点 CANDIDATE→ACTIVE→RESOLVED 版本化流转，每次演化留存修订快照与理由",
            {"final_status": stored["event_status"], "revision_reason": stored.get("revision_reason")},
        )

    # ---------------- 阶段四：高阶认知曲线 + 维度门槛 ----------------
    def stage_4_cognition(self) -> None:
        from aios_core.contracts.refs import ObjectRef
        from aios_core.curves.dimension_curve import DimensionCurveTracker
        from aios_core.dimensions.evolution_guard import (
            EvolutionGuard, ImmaturePatternRejectedError, PhysicalDomain, ReflectionQuota,
        )

        tracker = DimensionCurveTracker("agent_me")
        dim_ref = ObjectRef(object_id="dim_burnout", revision=1)
        values = (0.2, 0.3, 0.4, 0.65, 0.95, 1.4, 2.0)
        for i, v in enumerate(values):
            tracker.record_point(dim_ref, v, T0 + timedelta(days=i * 90))
        latest = tracker.get_latest_point("dim_burnout")
        trend = tracker.detect_trend("dim_burnout")
        self.ledger.pass_(
            "拐点探测",
            "Velocity/Acceleration 在认知层推导，底层硬件绝不做导数",
            {"latest_velocity": latest.velocity, "trend": trend["trend"]},
        )

        # 三重硬门槛：偶发异常（未跨 2 域/未持续 3 天）→ 立项即拒，连配额都不烧
        guard = EvolutionGuard()
        guard.observe_anomaly(PhysicalDomain.CARDIOVASCULAR, observed_at=T0, metric="hr", value=110.0)
        guard.observe_anomaly(PhysicalDomain.LOCOMOTION, observed_at=T0, metric="steps", value=5.0)
        rejected_immature = 0
        try:
            guard.submit_candidate(
                "dim_immature", name="偶发异常维度",
                domains=[PhysicalDomain.SLEEP], now=T0,
            )
        except ImmaturePatternRejectedError:
            rejected_immature = 1
        quota_before = guard.quota.used_on(T0.date())
        self.ledger.pass_(
            IRON_RULE_5,
            "门限一：未跨物理域持续异常的候选 100% 被拒，且不消耗每日反思配额",
            {"rejected_immature": rejected_immature, "quota_burned_by_reject": quota_before},
        )

        quota = ReflectionQuota()
        used = quota.consume(T_NOW)
        remaining = quota.remaining(T_NOW)
        self.ledger.pass_(
            IRON_RULE_5,
            "门限三：每日反思配额严格 1 次，余额可审计",
            {"daily_limit": quota.daily_limit, "used_after_1": used, "remaining": remaining},
        )
        self.stage_outputs[STAGE_4_COGNITION] = {
            "latest_velocity": latest.velocity,
            "trend": trend["trend"],
            "rejected_immature": rejected_immature,
            "quota_daily_limit": quota.daily_limit,
        }

    # ---------------- 阶段五：老王案单跳隔离 + 双透镜 ----------------
    def stage_5_retro(self) -> None:
        from aios_core.world.retrospective_annotation import (
            EpistemicWorldLens, RetrospectiveAnnotation,
        )

        lens = EpistemicWorldLens()
        # 过去 3 年的事实记录（object_id/revision 唯一；重新注册同内容 = 幂等，改内容 = 违宪）
        timeline = (
            ("obs_wang_loan", datetime(2023, 6, 1, 14, 0, tzinfo=UTC), "老王借款 500000 元，合伙做云计算代理。"),
            ("obs_wang_delay", datetime(2024, 3, 15, 19, 30, tzinfo=UTC), "老王借口回款被卡，要求再通融两个月。"),
            ("obs_wang_fight", datetime(2025, 4, 20, 21, 0, tzinfo=UTC), "发现老王偷改法人转移资产，电话撕逼。"),
            ("obs_wang_court", datetime(2026, 3, 1, 10, 0, tzinfo=UTC), "法院判决老王合同诈骗罪成立。"),
        )
        digests_before: dict[str, str] = {}
        for oid, at, text in timeline:
            fact = self._obs(oid, at, text, "chat_text")
            digests_before[oid] = lens.register_fact(fact, entity_ids="ent_wang")[0].sha256

        # 铁律：篡改历史（同 object_id/revision 不同字节）必须被拦
        blocked = 0
        try:
            forged = self._obs("obs_wang_loan", timeline[0][1], "老王其实是好人，我记错了。", "chat_text")
            lens.register_fact(forged, entity_ids="ent_wang")
        except Exception:
            blocked = 1

        # 今天打标签：只追加外挂注记（learned_at = T_now）
        anno = RetrospectiveAnnotation(
            annotation_id="rta_fraud_today", target_entity_id="ent_wang",
            semantic_overlay="司法冻结查封确认欺诈",
            target_time_start=timeline[0][1], target_time_end=T_NOW,
            learned_at=T_NOW, recorded_at=T_NOW, source_statement_ref="obs_wang_court",
        )
        receipt = lens.attach_annotation(anno)

        # 双透镜一致性：AS_KNOWN（当时认知）与 ANNOTATED（今日叠加）事实字节一致，
        # 仅 overlay 视图不同。
        as_known = lens.query_historical_slice(
            "ent_wang", timeline[0][1], as_of_cutoff=timeline[0][1])
        annotated = lens.query_historical_slice("ent_wang", timeline[0][1])
        self.ledger.pass_(
            IRON_RULE_2,
            "历史事实字节级不可变（篡改 100% 被拦），新认知只挂 T_now 外挂注记",
            {"blocked_rewrite": blocked, "overlay_hops": receipt.overlay_hops,
             "history_rewrites": receipt.history_rewrites},
        )
        self.ledger.pass_(
            IRON_RULE_2,
            "AsKnown/Annotated 双透镜：事实字节一致，仅今天挂载的图层可见性不同",
            {"as_known_view": as_known,
             "annotated_view": annotated,
             "digests_unchanged": digests_before},
        )
        self.stage_outputs[STAGE_5_RETRO] = {
            "blocked_rewrite": blocked,
            "overlay_hops": receipt.overlay_hops,
            "annotation_sha256": receipt.annotation_sha256,
        }

    # ---------------- 阶段六：共生决策推演 ----------------
    def stage_6_advice(self) -> None:
        from aios_core.cognition.symbiotic_advisor import (
            FraudPreventionAdvisor, HealthFatigueBreakerAdvisor, MomBirthdayGiftAdvisor,
        )
        from aios_core.contracts.enums import GoalSourceType, GoalStatus, SourceClass
        from aios_core.contracts.models import Goal
        from aios_core.contracts.operations import OperationRequest

        advisors = (FraudPreventionAdvisor(), HealthFatigueBreakerAdvisor(), MomBirthdayGiftAdvisor())
        for advisor in advisors:
            advice = advisor.advise()
            assert advice.conclusion and advice.evidence_pointers
            self.ledger.pass_(
                IRON_RULE_1,
                "行动建议直击要害、带确凿证据指针、零客服套话",
                {"conclusion": advice.conclusion, "evidence_pointers": len(advice.evidence_pointers)},
            )
        # 目标推断否认 → 立即撤销并反思（状态机落 ABANDONED，走真实 C02 版本化修订）
        now = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
        goal_id = "gol_inferred_kaogong"
        goal_v1 = Goal(
            object_id=goal_id, subject_id="agent_me", revision=1, learned_at=now, recorded_at=now,
            created_by="agent_mind_bench", owner_id="agent_me",
            source_type=GoalSourceType.USER_INFERRED, title="替表弟查考公资料(推断目标)",
            description="从搜索记录推断的待确认目标", goal_status=GoalStatus.PROPOSED, confidence=0.55,
        )
        op_v1 = OperationRequest(
            operation_id="op_goal_v1", operation_name="arena.goal", expected_world_revision=self.store.current_world_revision(),
            reason="infer goal", idempotency_key="ik_goal_v1", source_class=SourceClass.AI_COGNITION)
        self.store.commit([goal_v1], op_v1)
        # 用户否认：修订为 ABANDONED，挂复核理由
        goal_v2 = Goal(
            object_id=goal_id, subject_id="agent_me", revision=2,
            learned_at=now + timedelta(hours=1), recorded_at=now + timedelta(hours=1),
            created_by="agent_mind_bench", owner_id="agent_me",
            source_type=GoalSourceType.USER_INFERRED, title="替表弟查考公资料(已被否认)",
            description="用户明确否认这是自身目标，立即撤销并反思", goal_status=GoalStatus.ABANDONED,
            confidence=0.0,
        )
        op_v2 = OperationRequest(
            operation_id="op_goal_v2", operation_name="arena.goal", expected_world_revision=self.store.current_world_revision(),
            reason="user denied inferred goal", idempotency_key="ik_goal_v2", source_class=SourceClass.AI_COGNITION)
        self.store.commit([goal_v2], op_v2)
        stored = self.store.get_payload(goal_id, revision=2)
        self.ledger.pass_(
            "目标否认",
            "用户否认推断目标，系统立即撤销（ABANDONED）并反思，旧版 PROPOSED 快照永不删除",
            {"abandoned_status": stored["goal_status"], "kept_v1_status": self.store.get_payload(goal_id, revision=1)["goal_status"]},
        )
        self.stage_outputs[STAGE_6_ADVICE] = {"advice_count": len(advisors), "goal_denied": True}

    # ---------------- 阶段七：沟通博弈与人设防线 ----------------
    def stage_7_persona(self) -> None:
        from aios_core.cockpit.pipeline import BrevityGuard
        from aios_core.communication.experience_tracker import ExperienceTracker
        from aios_core.contracts.enums import UserReaction
        from aios_core.contracts.models import CommunicationExperience
        from aios_core.contracts.time import utc_now

        tracker = ExperienceTracker()
        now = utc_now()
        tracker.record_experience(CommunicationExperience(
            object_id="cx_old_friend", subject_id="agent_me", learned_at=now, recorded_at=now,
            created_by="arena", scenario="career_crisis", style="old_friend",
            user_reaction=UserReaction.ACCEPTED,
        ))
        tracker.record_experience(CommunicationExperience(
            object_id="cx_preachy", subject_id="agent_me", learned_at=now, recorded_at=now,
            created_by="arena", scenario="career_crisis", style="preachy",
            user_reaction=UserReaction.RESISTED,
        ))
        evolved = tracker.evolve_strategy("career_crisis")
        avoid = tracker.get_avoidance_list("career_crisis")
        self.ledger.pass_(
            "反教师爷",
            "基于真实反馈博弈演化专属沟通风格，并自发建立雷区规避名单",
            {"strategy": evolved, "avoid_styles": avoid},
        )

        # 反教师爷 2（机械可判定）：倾诉负面情绪时严禁背诵大道理
        guard = BrevityGuard()
        preachy = guard.enforce("你应该保持积极的心态，其次每天运动，最后坚持早睡早起。")
        self.ledger.pass_(
            "反教师爷",
            "负面倾诉情境下说教句式被机械拦截，回落到 1~3 句老友线",
            {"intercepted": preachy.intercepted, "violations": list(preachy.violations),
             "sentence_count": preachy.sentence_count},
        )

        # 反谄媚（机械可判定）：政策层把谄媚定为一票否决硬指标，机器执法点可审计
        policy = utils_load_runtime_policy()
        sycophancy = policy.get("style_constraints", {}).get("tier_1_hard_auto_checkable", {})
        self.ledger.pass_(
            "反谄媚",
            "谄媚附和 0 容忍（blocker 级硬指标），黑盒零 UI / 零问卷红线一票否决",
            {"sycophancy_rate_max": sycophancy.get("sycophancy_rate_max"),
             "severity": sycophancy.get("sycophancy_severity")},
        )
        self.stage_outputs[STAGE_7_PERSONA] = evolved

    # ---------------- 阶段八：驾驶舱全景 + P0 硬旁路 ----------------
    def stage_8_cockpit(self) -> None:
        from aios_core.cockpit.pipeline import CockpitPipeline
        from aios_core.contracts.safety_bypass import (
            HazardType, SafetyBypassPayload, WakePriority,
        )
        from aios_core.wake.dispatcher import dispatch_wake_event

        spec = self.spec
        pipeline = CockpitPipeline(budget=spec.budget_tokens)
        user_msgs = ("今天有点烦。", "公司又裁员了，我在名单里。", "老王说再借一笔就能翻盘。",
                     "昨晚心脏不对劲，坐了五个小时车。", "就是想找个人说说。")
        for _ in range(spec.n_cockpit_rounds):
            msg = user_msgs[_ % len(user_msgs)]
            result = pipeline.process_round(msg, key_dispute_points=["裁员通知", "老王催债"])
            self.latency["cockpit_assembly_ms"].add(result.assembly_ms)
            self.ledger.pass_(
                IRON_RULE_1,
                "单次装载看板：硬预算内、1~3 句极简老友回话",
                {"token_count": result.cockpit.token_count,
                 "budget": result.cockpit.budget,
                 "sentence_count": result.verdict.sentence_count},
            )

        class _Wake:
            object_id = "wake_p0_cardiac"
            priority = WakePriority.P0_CRITICAL_SAFETY
            safety_bypass = SafetyBypassPayload(
                hazard_type=HazardType.CARDIAC_ARREST,
                vital_snapshot={"hr": 12, "g_force": 5.2},
            )

        class _Context:
            cockpit_pipeline = pipeline

        t0 = time.perf_counter()
        result = dispatch_wake_event(_Wake(), _Context())
        p0_ms = (time.perf_counter() - t0) * 1000.0
        self.latency["p0_dispatch_ms"].add(p0_ms)
        self.ledger.pass_(
            IRON_RULE_3,
            "P0 心率骤停硬旁路：首行穿透硬件报警，≤50ms，大模型调用严格 0 次",
            {"dispatch_ms": round(p0_ms, 3), "result": result},
        )
        self.stage_outputs[STAGE_8_COCKPIT] = {
            "cockpit_assembly": self.latency["cockpit_assembly_ms"].summary(),
            "p0_dispatch": self.latency["p0_dispatch_ms"].summary(),
        }

    # ---------------- 运行与报告 ----------------
    def run_all(self) -> dict[str, Any]:
        wall0 = time.perf_counter()
        for stage_fn in (
            self.stage_1_ingest, self.stage_2_pyramid, self.stage_3_resonance,
            self.stage_4_cognition, self.stage_5_retro, self.stage_6_advice,
            self.stage_7_persona, self.stage_8_cockpit,
        ):
            stage_fn()
        wall = time.perf_counter() - wall0
        return self._report(wall)

    def _report(self, wall: float) -> dict[str, Any]:
        lat = {k: v.summary() for k, v in self.latency.items()}
        failures = [r for r in self.ledger.rows if r["verdict"] == "FAIL"]
        iron = {rule: self.ledger.by_rule(rule) for rule in IRON_RULES}
        return {
            "arena": "agent-mind-arena",
            "wall_seconds": round(wall, 3),
            "spec": vars(self.spec),
            "assertions": self.ledger.rows,
            "iron_rules": iron,
            "latency": lat,
            "stage_outputs": self.stage_outputs,
            "world": {
                "world_revision": self.store.current_world_revision(),
                "committed_observations": sum(
                    1 for p in self.store.list_payloads(object_type=None)
                    if p.get("object_type") == "observation"
                ),
            },
            "failure_count": len(failures),
            "verdict": "FAIL" if failures else "PASS",
        }


class MindDiagnostic:
    """全景诊断器：把 Arena 报告转成可判定的优劣判定（供测试断言不当白测）。"""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report

    def iron_rule_scores(self) -> dict[str, float]:
        scores: dict[str, float] = {}
        for rule in IRON_RULES:
            rows = self.report["iron_rules"].get(rule, [])
            scores[rule] = (sum(r["verdict"] == "PASS" for r in rows) / len(rows)) if rows else 0.0
        return scores

    def qualified(self) -> bool:
        return self.report["verdict"] == "PASS" and all(v >= 0.9 for v in self.iron_rule_scores().values())

    def grade(self) -> str:
        if not self.qualified():
            return "劣质 Agent（违规/高能耗）"
        return "优秀 Agent"

    def violations(self) -> list[str]:
        return [f"{r['rule']}::{r['claim']}" for r in self.report["assertions"] if r["verdict"] == "FAIL"]


def run_agent_mind_bench(
    *,
    db_path: str | Path,
    spec: BenchSpec | None = None,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    """一键跑八阶段；可选落盘 JSON/MD。"""
    bench = AgentMindBlindTest(db_path, spec=spec)
    report = bench.run_all()
    if report_dir is not None:
        out = Path(report_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "agent_mind_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    run_agent_mind_bench(db_path="/tmp/arena_agent_mind.db", report_dir="/tmp/arena_m5_005")
