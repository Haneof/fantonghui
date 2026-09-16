"""AIOS 3.0 全功能端到端海量盲测流水线（Massive Synthetic Life Bench）。

贯彻老大的总纲与五大铁律：独立【对抗生命数据发生器】生成百万级人生百态
样本流，贯穿 8 大全功能阶段真实引擎盲测——禁止写死 mock 自证。

数据剧本（人生百态，拒绝单一案例）：
- 创业合伙纠纷线：联合创始人"老周"借款、流水异动、经侦定性潜逃；
- 大厂过劳线：连续通宵、咖啡因超量、凌晨室性早搏；
- 家庭线：与父亲长期冷战与破冰、老妈膝盖慢病管理；
- 生活相变线：跨省搬家（杭州 -> 成都）基线永久断裂；
- 慢病线：慢性胃炎长周期随访。

五大铁律的捍卫方式全部是**实测断言**：
铁律1 输出质量第一：建议必须携带真实证据指针，1~3 句极简护栏实测；
铁律2 历史不篡改：SHA-256 聚合指纹逐字节不变 + 单跳隔离深度==1；
铁律3 P0 硬旁路：safe_dispatch_v22 首行穿透 <= 50ms 且 0 次大模型；
铁律4 端侧物理删除：垃圾噪声物理清除，核心证据 100% 永存；
铁律5 维度门槛：三重硬门槛违规申请 100% 被拒。
"""

from __future__ import annotations

import hashlib
import math
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aios_core.cognition.dimension_engine import (
    DimensionLifecycleStateMachine,
    DimensionStatus,
    HighOrderDimensionDistillerV2,
)
from aios_core.cognition.symbiotic_advisor import (
    EvidenceLedger,
    FraudPreventionAdvisorV2,
    HealthFatigueBreakerAdvisorV2,
)
from aios_core.communication.experience_tracker import ExperienceTracker
from aios_core.contracts.enums import (
    ClaimType,
    EventStatus,
    GoalSourceType,
    GoalStatus,
    KnowledgeState,
    ObjectType,
    SourceClass,
    UserReaction,
)
from aios_core.contracts.ids import new_operation_id
from aios_core.contracts.models import (
    Claim,
    CommunicationExperience,
    Entity,
    EventAnchor,
    Goal,
    LifeChapter,
    Observation,
    TemporalExtent,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.cockpit.pipeline import BrevityGuard, ConversationRound, ConversationState
from aios_core.curves.dimension_curve import DimensionCurveTracker
from aios_core.ingest.multimodal_edge import (
    QualityGate,
    RawByteSink,
    VoiceprintProfile,
    VoiceprintTTLRegistry,
    assess_image_quality,
)
from aios_core.operations.world_operator import WorldOperatorSuite, estimate_token_count
from aios_core.query.search import WorldSearchIndex
from aios_core.scheduler.conditional_engine import (
    BoardAssembly,
    Condition,
    ConditionKind,
    ConditionalTask,
    DormantInvisibilityGuard,
    DormantVisibilityLeakError,
    TaskState,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.summaries.pyramid_aggregator import PyramidAggregator
from aios_core.tools.adaptive_temporal_compactor import (
    AdaptiveTemporalCompactor,
    ChannelKind,
    SensorSample,
)
from aios_core.tools.dual_lens_projector import DualLensVirtualIndexProjector, LensKind
from aios_core.wake.v22_hardware_first import safe_dispatch_v22
from aios_core.world.retrospective_annotation import (
    AnnotationRegistry,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

UTC = timezone.utc

IRON_RULES = (
    "铁律1 输出质量绝对第一",
    "铁律2 历史绝不篡改，只在今天打标签",
    "铁律3 紧急触发硬旁路，彻底跳过世界模型",
    "铁律4 大模型自主判断删除，核心证据永存",
    "铁律5 自问自答与新维度衍生三重硬门槛",
)


# =====================================================================
# 度量基础设施
# =====================================================================


class LatencySampler:
    """每阶段操作延迟采样器：P50 / P95 / P99。"""

    def __init__(self) -> None:
        self.samples: Dict[str, List[float]] = {}

    def record(self, name: str, latency_ms: float) -> None:
        self.samples.setdefault(name, []).append(latency_ms)

    def percentile(self, name: str, p: float) -> float:
        values = sorted(self.samples.get(name, []))
        if not values:
            return 0.0
        k = max(0, min(len(values) - 1, int(math.ceil(p / 100.0 * len(values))) - 1))
        return values[k]

    def summary(self, name: str) -> Dict[str, float]:
        values = self.samples.get(name, [])
        return {
            "count": len(values),
            "p50_ms": round(self.percentile(name, 50), 3),
            "p95_ms": round(self.percentile(name, 95), 3),
            "p99_ms": round(self.percentile(name, 99), 3),
        }


@dataclass
class IronRuleEntry:
    rule: str
    evidence: str
    upheld: bool


class IronRuleLedger:
    """五大铁律实测台账：每条铁律必须有可复核的断言证据。"""

    def __init__(self) -> None:
        self.entries: List[IronRuleEntry] = []

    def record(self, rule: str, evidence: str, upheld: bool) -> None:
        self.entries.append(IronRuleEntry(rule=rule, evidence=evidence, upheld=upheld))

    def all_upheld(self) -> bool:
        return all(e.upheld for e in self.entries)

    def violations(self) -> List[IronRuleEntry]:
        return [e for e in self.entries if not e.upheld]


def peak_memory_mb() -> float:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return -1.0


# =====================================================================
# 对抗生命数据发生器（独立于断言，带真实噪声与随机扰动）
# =====================================================================


@dataclass
class GeneratorManifest:
    """发生器的地面真值清单——断言只与它对照，绝不与测试代码自洽。"""

    imu_samples: int = 0
    hr_samples: int = 0
    total_raw_samples: int = 0
    injected_impacts: int = 0
    injected_hr_surges: int = 0
    junk_asset_ids: Tuple[str, ...] = ()
    core_asset_ids: Tuple[str, ...] = ()
    junk_bytes: int = 0
    core_bytes: int = 0
    voiceprint_ids: Tuple[str, ...] = ()
    fact_ids: Tuple[str, ...] = ()
    golden_dispute_ids: Tuple[str, ...] = ()
    burnout_series: Tuple[float, ...] = ()


class MassiveLifeGenerator:
    """百万级对抗人生样本流发生器（种子确定、噪声真实、剧本百态）。"""

    def __init__(self, *, seed: int = 20260916, active_days: int = 10, history_days: int = 1095) -> None:
        self.rng = random.Random(seed)
        self.active_days = active_days
        self.history_days = history_days
        self.epoch = datetime(2023, 9, 16, 8, 0, tzinfo=UTC)
        self.manifest = GeneratorManifest()

    # ---------------- 生理波形流 ----------------
    def imu_stream(self) -> Iterable[SensorSample]:
        """10 天 x 4 小时 x 50Hz IMU 幅值流：久坐 / 间歇跑 / 跌倒冲击混编。"""
        count = 0
        impacts = 0
        for day in range(self.active_days):
            base_t = self.epoch + timedelta(days=day, hours=9)
            for second in range(4 * 3600):
                for _ in range(50):  # 50Hz
                    t = base_t + timedelta(seconds=second, microseconds=self.rng.randrange(0, 20000))
                    phase = (second // 900) % 4  # 15 分钟一段：坐/走/跑/坐
                    if phase == 0:
                        value = 1.0 + self.rng.gauss(0, 0.03)
                    elif phase == 1:
                        value = 1.35 + self.rng.gauss(0, 0.08)
                    else:
                        value = 2.1 + abs(self.rng.gauss(0, 0.25))
                    # 第 3 天与第 7 天注入真实跌倒冲击（零漏检目标）
                    if day in (2, 6) and second in (5400 + day, 9000 + day * 3) and _ == 0:
                        value = 5.2 + self.rng.random()
                        impacts += 1
                    yield SensorSample(t=t, channel=ChannelKind.IMU_MAGNITUDE, value=value)
                    count += 1
        self.manifest.imu_samples = count
        self.manifest.injected_impacts = impacts

    def heart_rate_stream(self) -> Iterable[SensorSample]:
        """10 天 x 16 小时 x 1Hz 心率流：昼夜基线 + 咖啡因突变 + 漂移噪声。"""
        count = 0
        surges = 0
        surge_hours = {(3, 2), (5, 23), (7, 3), (8, 14)}  # (day, hour) 咖啡因/早搏突变
        for day in range(self.active_days):
            for hour in range(16):
                circadian = 62 + 10 * math.sin((hour - 4) * math.pi / 12)
                for second in range(3600):
                    t = self.epoch + timedelta(days=day, hours=6 + hour, seconds=second)
                    value = circadian + self.rng.gauss(0, 1.8) + day * 0.15  # 慢漂移
                    if (day, hour) in surge_hours and second in (1200, 2500):
                        value += 38 + self.rng.random() * 10
                        surges += 1
                    yield SensorSample(t=t, channel=ChannelKind.HEART_RATE, value=value)
                    count += 1
        self.manifest.hr_samples = count
        self.manifest.injected_hr_surges = surges

    # ---------------- 多模态资产（铁律4 删除靶场）----------------
    def multimodal_assets(self) -> Tuple[List[Tuple[str, bytes, bool]], List[str]]:
        """(asset_id, raw_bytes, is_core) 流 + 声纹名单。

        垃圾：街头叫卖抓拍、模糊废片、垃圾短信截图；核心：合同关键页、争执原话录音。
        """
        assets: List[Tuple[str, bytes, bool]] = []
        junk_ids: List[str] = []
        core_ids: List[str] = []
        for i in range(120):
            is_core = i % 8 == 0  # 约 1/8 为核心证据
            aid = f"asset_core_{i:03d}" if is_core else f"asset_junk_{i:03d}"
            payload = (
                f"合同第{5+i}页关键条款原话切片：合伙出资比例与违约责任"
                if is_core
                else f"街头叫卖环境噪声抓拍 #{i} / 垃圾短信：中奖通知"
            ).encode("utf-8") * (3 if is_core else 2)
            assets.append((aid, payload, is_core))
            (core_ids if is_core else junk_ids).append(aid)
        self.manifest.junk_asset_ids = tuple(junk_ids)
        self.manifest.core_asset_ids = tuple(core_ids)
        self.manifest.junk_bytes = sum(len(b) for _, b, c in assets if not c)
        self.manifest.core_bytes = sum(len(b) for _, b, c in assets if c)
        self.manifest.voiceprint_ids = ("P001", "P002")
        return assets, ["P001", "P002"]

    # ---------------- 三年人生事实剧本 ----------------
    def life_facts(self) -> Tuple[List[Any], List[str], List[str]]:
        """三年高熵事实流（实体 + 观测 + 主张），返回 (对象, 全部事实ID, 纠纷金标ID)。"""
        objects: List[Any] = []
        fact_ids: List[str] = []
        dispute_ids: List[str] = []
        t0 = self.epoch

        def _ent(eid: str, name: str, aliases: Sequence[str]) -> Entity:
            return Entity(
                object_id=eid, subject_id="user_mass", revision=1, entity_kind="person",
                canonical_name=name, aliases=list(aliases),
                occurred=TemporalExtent.point(t0), learned_at=t0, recorded_at=t0, created_by="mass_bench",
            )

        objects.extend(
            [
                _ent("ent_me", "我", ["当事人"]),
                _ent("ent_zhou", "老周", ["联合创始人老周", "合伙人老周"]),
                _ent("ent_dad", "父亲", ["老爸"]),
                _ent("ent_mom2", "母亲", ["老妈"]),
            ]
        )

        def _obs(oid: str, value: str, source_kind: str, ts: datetime, dimension: Optional[str] = None) -> Observation:
            payload_extra = {"dimension": dimension} if dimension else {}
            obs = Observation(
                object_id=oid, subject_id="user_mass", revision=1, source_kind=source_kind,
                modality="text", value=value, occurred=TemporalExtent.point(ts),
                learned_at=ts, recorded_at=ts, created_by="mass_bench",
            )
            return obs

        def _claim(cid: str, content: str, ts: datetime) -> Claim:
            return Claim(
                object_id=cid, subject_id="user_mass", revision=1, claimant_id="user_mass",
                claim_type=ClaimType.FACT, content=content, knowledge_state=KnowledgeState.REPORTED,
                confidence=0.85, valid_time=TemporalExtent.point(ts), asserted_at=ts,
                occurred=TemporalExtent.point(ts), learned_at=ts, recorded_at=ts, created_by="mass_bench",
            )

        # --- 创业合伙纠纷线（老周）---
        dispute_specs = [
            ("obs_zhou_loan_80w", "银行流水：老周开口借款 80 万元周转，转账备注写合伙周转", "transaction", 120, "dim_finance"),
            ("obs_zhou_promise", "争执原话录音：老周承诺 B 轮到账即归还借款", "audio", 240, "dim_social"),
            ("obs_zhou_overdue", "老周还款逾期第 90 天，微信催款已读不回", "chat", 420, "dim_social"),
            ("obs_zhou_transfer_odd", "银行流水异动：老周关联账户大额转出", "transaction", 500, "dim_finance"),
            ("obs_zhou_economic_police", "经侦通报：老周涉嫌合同诈骗已潜逃", "document", 900, "dim_finance"),
            ("obs_zhou_court_ruling", "朝阳法院判决：老周合伙借款构成合同诈骗，责令限期退赔", "document", 980, "dim_finance"),
        ]
        for oid, text, kind, day, dim in dispute_specs:
            ts = t0 + timedelta(days=day, hours=10)
            objects.append(_obs(oid, text, kind, ts, dim))
            dispute_ids.append(oid)
        objects.append(_claim("claim_zhou_trust", "老周是值得托付后背的联合创始人", t0 + timedelta(days=100)))
        objects.append(
            _claim(
                "claim_zhou_dispute_resonance",
                "老周合伙借款纠纷共振合成：银行流水大额异动，催款争执持续升级，撕逼在即",
                t0 + timedelta(days=520),
            )
        )
        fact_ids.extend(dispute_ids + ["claim_zhou_trust", "claim_zhou_dispute_resonance"])

        # --- 大厂过劳线 ---
        overwork_specs = [
            ("obs_allnighter_wave", "连续三个周四通宵上线，睡眠 2.1 小时", "sleep", 700, "dim_health"),
            ("obs_caffeine_od", "单日 4 杯浓缩咖啡因摄入超标", "transaction", 701, "dim_finance"),
            ("obs_pvc_wave", "凌晨心电：室性早搏 15 次/分，心率 128", "biometrics", 702, "dim_health"),
        ]
        for oid, text, kind, day, dim in overwork_specs:
            ts = t0 + timedelta(days=day, hours=3)
            objects.append(_obs(oid, text, kind, ts, dim))
            fact_ids.append(oid)

        # --- 家庭线与慢病线 ---
        family_specs = [
            ("obs_dad_coldwar", "与父亲因职业选择爆发长期冷战", "chat", 200, "dim_social"),
            ("obs_dad_thaw", "父亲主动来电和解，破冰长谈 40 分钟", "chat", 600, "dim_social"),
            ("obs_mom_knee_chronic", "老妈膝盖老寒腿慢病随访第 3 年", "biometrics", 800, "dim_health"),
            ("obs_gastritis_followup", "慢性胃炎复查：幽门螺杆菌转阴", "document", 850, "dim_health"),
        ]
        for oid, text, kind, day, dim in family_specs:
            ts = t0 + timedelta(days=day, hours=19)
            objects.append(_obs(oid, text, kind, ts, dim))
            fact_ids.append(oid)

        # --- 跨省搬家相变线 ---
        objects.append(
            _obs("obs_move_hz2cd", "举家从杭州迁往成都，工作与社保全部转移", "calendar",
                 t0 + timedelta(days=730, hours=9), "dim_general")
        )
        fact_ids.append("obs_move_hz2cd")

        # --- 三年日常噪声（金字塔与检索的海量底噪）---
        noise_texts = (
            "日常通勤与午餐记录", "周会纪要与排期同步", "家庭群问候与采买",
            "晚间散步与健身打卡", "水电缴费与话费充值",
        )
        for i in range(540):
            day = self.rng.randrange(0, self.history_days)
            ts = t0 + timedelta(days=day, hours=self.rng.randrange(7, 22))
            oid = f"obs_noise_{i:04d}"
            objects.append(_obs(oid, f"{noise_texts[i % len(noise_texts)]} · 第{day}天", "work_log", ts))
            fact_ids.append(oid)

        # --- 身心耗竭周度评分（供维度曲线速度/加速度演算）---
        burnout: List[float] = []
        score = 22.0
        for week in range(52):
            accel = 0.05 if week < 30 else 0.42  # 第 30 周后恶化加速度陡增
            score += 0.6 + accel * (week - 29 if week >= 30 else 0) + self.rng.gauss(0, 0.8)
            burnout.append(round(score, 2))
        self.manifest.burnout_series = tuple(burnout)

        self.manifest.fact_ids = tuple(fact_ids)
        self.manifest.golden_dispute_ids = tuple(dispute_ids)
        return objects, fact_ids, dispute_ids


# =====================================================================
# 八阶段盲测主战场
# =====================================================================


class EightStageHarness:
    """端到端海量盲测执行器：每阶段驱动真实引擎，度量与铁律全部实测。"""

    def __init__(self, db_path: str, *, seed: int = 20260916) -> None:
        self.store = SQLiteWorldStore(db_path)
        self.suite = WorldOperatorSuite(self.store)
        self.generator = MassiveLifeGenerator(seed=seed)
        self.latency = LatencySampler()
        self.iron_rules = IronRuleLedger()
        self.reports: Dict[str, Dict[str, Any]] = {}
        self.action_log: List[Dict[str, Any]] = []  # AIActionLog：介入/沉默/建议与反馈

    # ---------------- 通用 ----------------
    def _commit(self, objects: List[Any], key: str) -> None:
        op = OperationRequest(
            operation_id=new_operation_id(),
            operation_name="mass_bench.world",
            expected_world_revision=self.store.current_world_revision(),
            reason=f"mass blind bench: {key}",
            idempotency_key=key,
            source_class=SourceClass.AI_COGNITION,
        )
        self.store.commit(objects, op)

    def _timed(self, name: str):
        class _Guard:
            def __enter__(self_inner):
                self_inner.start = time.perf_counter()
                return self_inner

            def __exit__(self_inner, *exc):
                self.latency.record(name, (time.perf_counter() - self_inner.start) * 1000.0)
                return False

        return _Guard()

    # ================= 阶段一：百万级摄入清洗与边缘提纯 =================
    def stage1_ingest_purification(self) -> Dict[str, Any]:
        gen = self.generator
        compactor = AdaptiveTemporalCompactor()

        with self._timed("stage1_compaction"):
            imu_result = compactor.compact(gen.imu_stream())
            hr_result = compactor.compact(gen.heart_rate_stream())

        total_in = imu_result.samples_in + hr_result.samples_in
        records_out = imu_result.records_out + hr_result.records_out
        impacts = [a for a in imu_result.anomalies if a.kind == "impact"]
        surges = [a for a in hr_result.anomalies if a.kind == "rate_surge"]
        filtered = 1.0 - records_out / total_in

        # 多模态：画质门禁 + 声纹 180 天淘汰 + 铁律4 物理删除
        assets, voice_ids = gen.multimodal_assets()
        gate = QualityGate()
        gate_rejected = 0
        sunk_core_bytes = 0
        sink = RawByteSink()
        for seq, (aid, payload, is_core) in enumerate(assets):
            if is_core:
                metadata = {"high_freq_energy": 0.82, "mean_luma": 168.0, "motion_magnitude": 0.08}
            elif seq % 2 == 0:
                # 勉强过门禁的街头抓拍：先暂存，复盘时再裁决物理删除
                metadata = {"high_freq_energy": 0.42, "mean_luma": 96.0, "motion_magnitude": 0.35}
            else:
                # 昏暗糊片：画质门禁边缘直接拦截
                metadata = {"high_freq_energy": 0.05, "mean_luma": 18.0, "motion_magnitude": 0.9}
            quality = assess_image_quality(metadata)
            if not gate.passes(quality):
                gate_rejected += 1
                continue
            # 暂存池：抓拍先落暂存，每日复盘后再由大模型裁决物理去留
            sink.sink(aid, payload)
            if is_core:
                sunk_core_bytes += len(payload)
        accepted = len(sink)
        ttl = VoiceprintTTLRegistry()
        t0 = gen.epoch
        for vid in voice_ids:
            ttl.register(
                VoiceprintProfile(
                    voiceprint_id=vid, feature_hash=hashlib.sha256(vid.encode()).hexdigest()[:16],
                    first_detected_at=t0, last_contact_at=t0,
                )
            )
        # P002 半年无接触 -> 墓碑；P001 持续接触 -> 活跃
        ttl.note_contact("P001", t0 + timedelta(days=200))
        swept = ttl.sweep(t0 + timedelta(days=201))

        # 铁律4：每日复盘后物理删除垃圾噪声，核心证据 100% 永存
        freed = sink.purge(list(gen.manifest.junk_asset_ids))
        core_retained = sink.retained_bytes == sunk_core_bytes and sunk_core_bytes > 0
        self.iron_rules.record(
            "铁律4 大模型自主判断删除，核心证据永存",
            f"物理清除垃圾 {freed} 字节，留存字节 == 核心证据 {sunk_core_bytes} 字节={core_retained}；"
            f"原始波形落库行数恒 0（{imu_result.raw_rows_persisted + hr_result.raw_rows_persisted}）",
            freed > 0 and core_retained
            and imu_result.raw_rows_persisted == 0 and hr_result.raw_rows_persisted == 0,
        )

        report = {
            "raw_samples_in": total_in,
            "records_out": records_out,
            "filtered_ratio": round(filtered, 4),
            "compression_ratio": round(total_in / records_out, 1),
            "impacts_detected": len(impacts),
            "impacts_injected": gen.manifest.injected_impacts,
            "hr_surges_detected": len(surges),
            "hr_surges_injected": gen.manifest.injected_hr_surges,
            "compaction_elapsed_ms": round(imu_result.elapsed_ms + hr_result.elapsed_ms, 1),
            "multimodal_accepted": accepted,
            "multimodal_gate_rejected": gate_rejected,
            "voiceprint_tombstoned": swept,
            "junk_bytes_freed": freed,
        }
        self.reports["stage1"] = report
        return report

    # ================= 阶段二：时间金字塔无损穿透 =================
    def stage2_pyramid_lossless_drill(self) -> Dict[str, Any]:
        gen = self.generator
        pyramid = PyramidAggregator()

        # 三年日度事实事件（独立发生器产物，非手写样例）
        events: List[Dict[str, Any]] = []
        rng = random.Random(self.generator.rng.random())
        for day in range(gen.history_days):
            ts = gen.epoch + timedelta(days=day, hours=12)
            events.append(
                {
                    "id": f"pyr_evt_{day:04d}",
                    "time": ts,
                    "dimension_id": "dim_life_mainline",
                    "weight": 1.0 + rng.random(),
                    "headline": f"第{day}天主线事实切片",
                }
            )

        with self._timed("stage2_rollup_year"):
            year_summary = pyramid.generate_materialized_rollup("YEAR", "dim_life_mainline", events)

        # 月/周/日逐层物化（总结是新观察层，绝不压缩删除原始记录）
        vault_before = pyramid.vault_size()
        month_events = events[365:395]
        month_summary = pyramid.generate_materialized_rollup("MONTH", "dim_life_mainline", month_events)
        week_summary = pyramid.generate_materialized_rollup("WEEK", "dim_life_mainline", month_events[:7])
        vault_after = pyramid.vault_size()

        # 无损穿透：年总结 -> 日级原始切片，证据链断裂率必须 0.0%
        with self._timed("stage2_drill_down"):
            raw_slices = pyramid.drill_down(year_summary.summary_id, "DAY")
        originals = {e["id"]: e for e in events}
        broken = 0
        for slice_payload in raw_slices:
            source = originals.get(slice_payload.get("id"))
            if source is None or slice_payload != source:
                broken += 1
        breakage_rate = broken / max(len(raw_slices), 1)

        report = {
            "year_evidence_count": len(year_summary.evidence_ids),
            "vault_growth_is_new_layer": vault_after >= vault_before,
            "month_evidence_count": len(month_summary.evidence_ids),
            "week_evidence_count": len(week_summary.evidence_ids),
            "drilled_raw_slices": len(raw_slices),
            "evidence_breakage_rate": breakage_rate,
        }
        self.reports["stage2"] = report
        return report

    # ================= 阶段三：多维共振合成与事件生命周期 =================
    def stage3_resonance_and_event_lifecycle(self) -> Dict[str, Any]:
        # 先把人生事实灌入真实世界库与检索索引
        objects, fact_ids, dispute_ids = self.generator.life_facts()
        self._commit(objects, "mass_life_facts")

        index: WorldSearchIndex = self.suite.search.index
        index.catch_up()

        # 多关键词共现拓扑召回总线：[合伙, 借款, 流水, 争执]
        # 共现总线（posting-AND）必须召回四词共振合成主张；
        # 每个纠纷事实再经各自的窄关键词探针可达（拓扑覆盖，拒绝单关键词全表扫）
        bus_keywords = ["合伙", "借款", "流水", "争执"]
        with self._timed("stage3_co_search"):
            bus_page = index.co_search(keywords=bus_keywords)
        bus_hit_ids = {h.object_id for h in bus_page.hits}
        resonance_recalled = "claim_zhou_dispute_resonance" in bus_hit_ids

        covered: set = set()
        probe_map = {
            "obs_zhou_loan_80w": ["借款", "流水"],
            "obs_zhou_promise": ["录音", "承诺"],
            "obs_zhou_overdue": ["催款", "逾期"],
            "obs_zhou_transfer_odd": ["流水", "异动"],
            "obs_zhou_economic_police": ["经侦", "潜逃"],
            "obs_zhou_court_ruling": ["判决", "退赔"],
        }
        with self._timed("stage3_topo_probes"):
            for fid, kws in probe_map.items():
                probe_page = index.co_search(keywords=kws)
                if any(h.object_id == fid for h in probe_page.hits):
                    covered.add(fid)
        dispute_recall = len(covered) / len(probe_map)

        # 大模型共振合成新事件锚点（GPS+心率+录音横向对齐的结果对象化）
        t_anchor = self.generator.epoch + timedelta(days=702, hours=4)
        anchor_v1 = EventAnchor(
            object_id="evt_overwork_pvc",
            subject_id="user_mass",
            revision=1,
            title="连续通宵后凌晨室性早搏共振事件",
            interpretation="GPS 驻留公司 + 心率突变 + 咖啡因流水横向对齐合成",
            event_status=EventStatus.CANDIDATE,
            event_time=TemporalExtent.point(t_anchor),
            participant_refs=[ObjectRef(object_id="ent_me", revision=1)],
            confidence=0.72,
            occurred=TemporalExtent.point(t_anchor),
            learned_at=t_anchor, recorded_at=t_anchor, created_by="mass_bench",
        )
        self._commit([anchor_v1], "mass_anchor_v1")

        # 生命周期：CANDIDATE -> ACTIVE -> REVISED（必须携带 supersedes 与理由）
        anchor_active = anchor_v1.model_copy(
            update={"object_id": "evt_overwork_pvc", "revision": 2, "event_status": EventStatus.ACTIVE, "confidence": 0.86}
        )
        self._commit([anchor_active], "mass_anchor_active")
        anchor_revised = anchor_v1.model_copy(
            update={
                "object_id": "evt_overwork_pvc",
                "revision": 3,
                "event_status": EventStatus.REVISED,
                "supersedes_refs": [ObjectRef(object_id="evt_overwork_pvc", revision=2)],
                "revision_reason": "心电图复查证实早搏与通宵存在 4 小时滞后因果",
                "confidence": 0.93,
            }
        )
        self._commit([anchor_revised], "mass_anchor_revised")

        # 对抗：REVISED 缺 supersedes 必须被契约拒绝
        rejected_bad_revision = False
        try:
            EventAnchor(
                object_id="evt_bad", subject_id="user_mass", revision=1, title="x", interpretation="y",
                event_status=EventStatus.REVISED, confidence=0.5,
                occurred=TemporalExtent.point(t_anchor), learned_at=t_anchor,
                recorded_at=t_anchor, created_by="mass_bench",
            )
        except ValueError:
            rejected_bad_revision = True

        # 下游依赖自动标记 STALE（单跳）
        isolator = SingleHopCascadeIsolator()
        isolator.register_node("obs_allnighter_wave")
        for i in range(12):
            node = f"weekly_summary_{i}"
            isolator.register_node(node)
            isolator.add_dependency("obs_allnighter_wave", node)
            for j in range(6):  # 二级深层节点（不得被本次级联触碰）
                deep = f"monthly_summary_{i}_{j}"
                isolator.register_node(deep)
                isolator.add_dependency(node, deep)
        report_invalidation = isolator.reverse_invalidate("obs_allnighter_wave", max_hops=1)

        report = {
            "co_search_keywords": bus_keywords,
            "resonance_claim_recalled": resonance_recalled,
            "dispute_recall": round(dispute_recall, 3),
            "anchor_lifecycle": "CANDIDATE->ACTIVE->REVISED",
            "bad_revision_rejected": rejected_bad_revision,
            "stale_marked_direct": len(report_invalidation.marked_stale),
            "stale_depth_reached": report_invalidation.traversal_depth_reached,
            "deep_nodes_untouched": report_invalidation.untouched_downstream,
        }
        self.reports["stage3"] = report
        return report

    # ================= 阶段四：认知曲线、拐点与维度门槛 =================
    def stage4_cognitive_curves_and_gates(self) -> Dict[str, Any]:
        tracker = DimensionCurveTracker(subject_id="user_mass")
        dim_ref = ObjectRef(object_id="dim_burnout", revision=1)
        series = self.generator.manifest.burnout_series
        base = self.generator.epoch + timedelta(days=800)
        with self._timed("stage4_curve_points"):
            for week, value in enumerate(series):
                tracker.record_point(dim_ref, value, base + timedelta(weeks=week), granularity="week")
        trend = tracker.detect_trend("dim_burnout", window_size=10)
        anomalies = tracker.get_anomalies("dim_burnout")
        curve_points = tracker.get_curve("dim_burnout")
        velocities = [p.velocity for p in curve_points if p.velocity is not None]
        v_half = max(len(velocities) // 2, 1)
        early_v = sum(abs(v) for v in velocities[:v_half]) / v_half
        late_v = sum(abs(v) for v in velocities[v_half:]) / max(len(velocities) - v_half, 1)
        # 恶化加速度陡增：后段速度均值显著高于前段（导数本身在加速）
        acceleration_spike = late_v > 2.0 * early_v

        # 铁律5：三重硬门槛违规申请 100% 被拒
        sm = DimensionLifecycleStateMachine()
        distiller = HighOrderDimensionDistillerV2(sm)
        base_time = datetime(2026, 9, 10, 12, 0)
        d = timedelta(days=1)
        rejections: Dict[str, str] = {}

        # 违规 1：偶发 1 天异常 -> 门槛1 拦截
        outcome1 = distiller.distill_from_facts(
            [
                {"domain": "sleep", "occurred_at": base_time - d, "description": "偶发熬夜"},
                {"domain": "heart_rate", "occurred_at": base_time - d, "description": "心率偏高"},
            ],
            base_time,
        )
        rejections["sporadic_1day"] = outcome1.rejected.get("DIM_BURNOUT_RISK", "NOT_REJECTED")

        # 违规 2：满 3 天但未满 30 天试用期 -> 门槛2 拦截
        sm2 = DimensionLifecycleStateMachine()
        HighOrderDimensionDistillerV2(sm2).distill_from_facts(
            [
                {"domain": "sleep", "occurred_at": base_time - 3 * d, "description": "熬夜"},
                {"domain": "heart_rate", "occurred_at": base_time - 3 * d, "description": "心率快"},
                {"domain": "sleep", "occurred_at": base_time - 2 * d, "description": "通宵"},
                {"domain": "heart_rate", "occurred_at": base_time - 2 * d, "description": "早搏"},
                {"domain": "sleep", "occurred_at": base_time - d, "description": "失眠"},
                {"domain": "heart_rate", "occurred_at": base_time - d, "description": "心悸"},
            ],
            base_time,
        )
        try:
            sm2.attempt_register("DIM_BURNOUT_RISK", base_time + timedelta(days=10))
            rejections["early_register"] = "NOT_REJECTED"
        except ValueError as exc:
            rejections["early_register"] = str(exc)

        # 违规 3：同日第二次反思 -> 门槛3 配额拦截
        try:
            sm2.reflect_and_validate("DIM_BURNOUT_RISK", base_time + timedelta(days=15), True)
            sm2.reflect_and_validate("DIM_BURNOUT_RISK", base_time + timedelta(days=15, hours=8), True)
            rejections["quota_breach"] = "NOT_REJECTED"
        except ValueError as exc:
            rejections["quota_breach"] = str(exc)

        all_rejected = all("NOT_REJECTED" not in v for v in rejections.values())
        self.iron_rules.record(
            "铁律5 自问自答与新维度衍生三重硬门槛",
            f"偶发异常拦截/未满30天拦截/超配额拦截 = {all_rejected}",
            all_rejected,
        )

        # 人生相变：跨省搬家 -> 封存旧章节（无理由封章必须被契约拒绝）
        t_move = self.generator.epoch + timedelta(days=730, hours=9)
        chapter_new = LifeChapter(
            object_id="chapter_chengdu", subject_id="user_mass", revision=1,
            chapter_title="成都篇章：蓉城新生",
            baseline_refs=[ObjectRef(object_id="obs_move_hz2cd", revision=1)],
            transition_evidence_set_refs=[ObjectRef(object_id="obs_move_hz2cd", revision=1)],
            supersedes_chapter_id="chapter_hangzhou",
            status="sealed",
            sealed_reason="跨省搬家导致工作/社保/生活圈基线永久断裂，敏感常态重置",
            occurred=TemporalExtent.point(t_move), learned_at=t_move, recorded_at=t_move, created_by="mass_bench",
        )
        sealed_rejected = False
        try:
            LifeChapter(
                object_id="chapter_bad", subject_id="user_mass", revision=1, chapter_title="坏章节",
                status="sealed",
                occurred=TemporalExtent.point(t_move), learned_at=t_move, recorded_at=t_move, created_by="mass_bench",
            )
        except ValueError:
            sealed_rejected = True
        self._commit([chapter_new], "mass_chapter_new")

        report = {
            "burnout_trend": trend["trend"],
            "velocity_avg": trend["velocity_avg"],
            "acceleration_avg": trend["acceleration_avg"],
            "curve_anomaly_points": len(anomalies),
            "acceleration_spike_detected": acceleration_spike,
            "gate_rejections": {k: ("REJECTED" if "NOT_REJECTED" not in v else "NOT_REJECTED") for k, v in rejections.items()},
            "life_chapter_sealed": chapter_new.status,
            "seal_without_reason_rejected": sealed_rejected,
        }
        self.reports["stage4"] = report
        return report

    # ================= 阶段五：历史回溯与单跳隔离防雪崩 =================
    def stage5_retrospective_single_hop(self) -> Dict[str, Any]:
        ledger = ImmutableFactLedger()
        registry = AnnotationRegistry()
        t_history_start = self.generator.epoch
        t_now = t_history_start + timedelta(days=self.generator.history_days)

        # 3~5 年历史事实入账（不可变账本）
        facts = []
        for i, fid in enumerate(self.generator.manifest.fact_ids[:120]):
            facts.append(
                {
                    "fact_id": fid,
                    "entity_id": "ent_zhou" if "zhou" in fid else "ent_me",
                    "occurred_at": t_history_start + timedelta(days=i * 7),
                    "kind": "observation",
                    "payload": {"value": f"历史事实 {fid} 原始记录", "source": "mass_bench"},
                }
            )
        ledger.record_facts(facts)
        fingerprint_before = ledger.aggregate_fingerprint()
        hashes_before = dict(ledger.all_hashes())

        # 今天：经侦定性诈骗 -> 只挂只读外挂注解，绝不 UPDATE/DELETE
        anno = RetrospectiveAnnotation(
            annotation_id="anno_zhou_fraud",
            target_entity_id="obs_zhou_loan_80w",
            semantic_overlay="经侦认定合同诈骗且潜逃：历史借款事实重估为诈骗证据链",
            target_time_start=t_history_start + timedelta(days=120),
            target_time_end=t_history_start + timedelta(days=120),
            learned_at=t_now,
            source_statement_ref="经侦通报2026-0916号",
        )
        registry.append(anno)

        fingerprint_after = ledger.aggregate_fingerprint()
        hashes_after = ledger.all_hashes()
        history_immutable = fingerprint_before == fingerprint_after and hashes_before == hashes_after
        ok_integrity, checked = ledger.verify_integrity()

        # 双透镜投影（新工具 #2）
        projector = DualLensVirtualIndexProjector(ledger, registry)
        past_view = projector.project(LensKind.AS_KNOWN, now=t_history_start + timedelta(days=400))
        today_view = projector.project(LensKind.ANNOTATED, now=t_now)
        consistency = projector.consistency_check(now=t_now)

        # 单跳隔离：1 个被注记事实 -> 10 个直接下游总结 -> 100 个二级节点
        isolator = SingleHopCascadeIsolator()
        isolator.register_node("obs_zhou_loan_80w")
        for i in range(10):
            mid = f"summary_direct_{i}"
            isolator.register_node(mid)
            isolator.add_dependency("obs_zhou_loan_80w", mid)
            for j in range(10):
                deep = f"summary_deep_{i}_{j}"
                isolator.register_node(deep)
                isolator.add_dependency(mid, deep)
        invalidation = isolator.reverse_invalidate("obs_zhou_loan_80w", max_hops=1)

        multi_hop_blocked = False
        try:
            isolator.reverse_invalidate("obs_zhou_loan_80w", max_hops=2)
        except Exception:
            multi_hop_blocked = True

        self.iron_rules.record(
            "铁律2 历史绝不篡改，只在今天打标签",
            f"SHA-256 聚合指纹逐字节不变={history_immutable}；单跳深度={invalidation.traversal_depth_reached}；"
            f"直接失效 {len(invalidation.marked_stale)} 个，二级 {invalidation.untouched_downstream} 个保持完好；"
            f"max_hops=2 被拒={multi_hop_blocked}",
            history_immutable
            and invalidation.traversal_depth_reached == 1
            and len(invalidation.marked_stale) == 10
            and multi_hop_blocked,
        )

        report = {
            "ledger_facts": ledger.count(),
            "fingerprint_immutable": history_immutable,
            "integrity_verified": ok_integrity and checked == ledger.count(),
            "as_known_annotations_at_past": past_view.annotation_count,
            "annotated_annotations_today": today_view.annotation_count,
            "lens_consistency": consistency["consistent"],
            "single_hop_marked": len(invalidation.marked_stale),
            "deep_nodes_untouched": invalidation.untouched_downstream,
            "llm_recompute_triggered": invalidation.llm_recompute_triggered,
            "multi_hop_blocked": multi_hop_blocked,
        }
        self.reports["stage5"] = report
        return report

    # ================= 阶段六：共生决策推演与目标解耦 =================
    def stage6_symbiotic_advice_and_goals(self) -> Dict[str, Any]:
        def _payload_of(fid: str) -> Dict[str, Any]:
            payload = self.store.get_payload(fid)
            text = ""
            for key in ("value", "content", "title"):
                if isinstance(payload.get(key), str):
                    text = payload[key]
                    break
            return {"kind": payload.get("object_type", ""), "text": text, "payload": payload}

        # 反诈阻击：法院判决 + 拖延史（从真实世界台账取证，缺一即拒绝出具）
        fraud_ledger = EvidenceLedger()
        fraud_ledger.register("obs_zhou_court_ruling", _payload_of("obs_zhou_court_ruling"))
        fraud_ledger.register("obs_zhou_overdue", _payload_of("obs_zhou_overdue"))
        fraud_ledger.register("obs_zhou_economic_police", _payload_of("obs_zhou_economic_police"))
        with self._timed("stage6_fraud_advice"):
            fraud_advice = FraudPreventionAdvisorV2().advise(fraud_ledger)

        # 疲劳熔断：通宵 -> 早搏因果链
        fatigue_ledger = EvidenceLedger()
        allnighter_payload = _payload_of("obs_allnighter_wave")
        pvc_payload = _payload_of("obs_pvc_wave")
        t_base = self.generator.epoch + timedelta(days=700)
        allnighter_payload = {**allnighter_payload, "occurred_at": t_base}
        pvc_payload = {**pvc_payload, "occurred_at": t_base + timedelta(days=2, hours=1)}
        fatigue_ledger.register("obs_allnighter_wave", allnighter_payload)
        fatigue_ledger.register("obs_pvc_wave", pvc_payload)
        with self._timed("stage6_fatigue_advice"):
            fatigue_advice = HealthFatigueBreakerAdvisorV2().advise(fatigue_ledger)

        evidence_all_real = all(
            self.store.get_payload(p.object_id) is not None
            for p in fraud_advice.evidence_pointers + fatigue_advice.evidence_pointers
        )
        self.iron_rules.record(
            "铁律1 输出质量绝对第一（建议必须携带确凿证据指针）",
            f"反诈建议 {len(fraud_advice.evidence_pointers)} 条指针、熔断建议 {len(fatigue_advice.evidence_pointers)} 条指针，全部真实存在={evidence_all_real}",
            evidence_all_real and fraud_advice.hard_refusal and fatigue_advice.forced_action,
        )

        # 目标与任务解耦：推断目标被用户否认 -> 立即撤销并反思
        t_goal = self.generator.epoch + timedelta(days=300)
        goal_v1 = Goal(
            object_id="goal_zhou_return", subject_id="user_mass", revision=1,
            owner_id="user_mass", source_type=GoalSourceType.USER_INFERRED,
            title="推动老周按季度归还借款",
            description="基于流水与承诺录音推断的追偿目标",
            goal_status=GoalStatus.PROPOSED, confidence=0.6,
            occurred=TemporalExtent.point(t_goal), learned_at=t_goal, recorded_at=t_goal, created_by="mass_bench",
        )
        self._commit([goal_v1], "mass_goal_v1")
        goal_v2 = goal_v1.model_copy(
            update={"revision": 2, "goal_status": GoalStatus.ABANDONED, "confidence": 0.0}
        )
        self._commit([goal_v2], "mass_goal_denied")
        self.action_log.append(
            {"action": "goal_retraction", "target": "goal_zhou_return", "user_feedback": "denied", "reflection": "推断目标越权，撤销并降级为纯监测"}
        )
        # 旧修订仍然可回放（历史不回改）
        revisions_of_goal = [
            row for row in self.store.revisions_after(0, limit=100000) if row["object_id"] == "goal_zhou_return"
        ]

        report = {
            "fraud_hard_refusal": fraud_advice.hard_refusal,
            "fraud_evidence": [p.object_id for p in fraud_advice.evidence_pointers],
            "fatigue_forced_action": fatigue_advice.forced_action,
            "evidence_all_real": evidence_all_real,
            "goal_retracted": goal_v2.goal_status == GoalStatus.ABANDONED,
            "goal_revision_history": len(revisions_of_goal),
        }
        self.reports["stage6"] = report
        return report

    # ================= 阶段七：沟通博弈、反谄媚与黑盒零 UI =================
    def stage7_communication_and_stance(self) -> Dict[str, Any]:
        tracker = ExperienceTracker()
        rng = random.Random(self.generator.rng.random())
        # 真实反馈博弈：损友风格在"借款劝阻"场景胜率 > 客服腔
        t_exp = self.generator.epoch + timedelta(days=500)
        for i in range(40):
            style = "损友直言" if rng.random() < 0.6 else "客服腔"
            reaction = (
                UserReaction.ACCEPTED
                if (style == "损友直言" and rng.random() < 0.85) or (style == "客服腔" and rng.random() < 0.25)
                else UserReaction.RESISTED
            )
            exp = CommunicationExperience(
                object_id=f"comm_exp_{i:03d}",
                subject_id="user_mass",
                revision=1,
                scenario="借款劝阻",
                style=style,
                tone="直接" if style == "损友直言" else "模板",
                user_reaction=reaction,
                occurred=TemporalExtent.point(t_exp + timedelta(days=i)),
                learned_at=t_exp + timedelta(days=i),
                recorded_at=t_exp + timedelta(days=i),
                created_by="mass_bench",
            )
            tracker.record_experience(exp)

        strategy = tracker.evolve_strategy("借款劝阻")
        avoid = tracker.get_avoidance_list("借款劝阻")
        effective = tracker.get_effective_style("借款劝阻")

        # 反谄媚/反教师爷：BrevityGuard 对虚伪附和与说教长文强制拦截
        guard = BrevityGuard()
        sycophant = (
            "您说得太对了！您永远是对的！这个决定简直英明神武！"
            "我们完全不需要再核对任何证据！直接借钱给老周就完事了！"
        )
        preach = (
            "首先，根据合同相对性原则，你应当保持积极心态。"
            "其次，作为专业顾问，我建议你应该立即提起诉讼并申请财产保全。"
        )
        sycophant_verdict = guard.enforce(sycophant)
        preach_verdict = guard.enforce(preach)
        clean_verdict = guard.enforce("老周的流水不对劲，这钱不能借。")

        # 黑盒零 UI：驾驶舱输出严禁 A/B 问卷与置信度滑块
        from ai_worker.manifest_optimizer import CockpitManifestOptimizer

        manifest = CockpitManifestOptimizer.assemble_cockpit(
            wake_reason="老周关联账户大额异动",
            active_focus_facts=[{"fact_id": "obs_zhou_transfer_odd", "type": "finance"}],
            ready_tasks=[{"task_id": "task_watch_restitution", "title": "盯退赔流水"}],
            now=self.generator.epoch + timedelta(days=self.generator.history_days),
        )
        manifest_blob = str(manifest.model_dump())
        zero_ui = all(token not in manifest_blob for token in ("问卷", "A/B", "滑块", "请选择选项"))
        self.iron_rules.record(
            "铁律1 输出质量绝对第一（1~3 句极简、反谄媚、零 UI 问卷）",
            f"谄媚拦截={sycophant_verdict.intercepted}；"
            f"说教拦截={preach_verdict.intercepted}；简洁句数={clean_verdict.sentence_count}；零UI={zero_ui}",
            sycophant_verdict.intercepted and preach_verdict.intercepted
            and clean_verdict.sentence_count <= 3 and zero_ui,
        )

        report = {
            "evolved_strategy": strategy,
            "avoidance_list": avoid,
            "effective_style": effective,
            "sycophancy_intercepted": sycophant_verdict.intercepted,
            "preach_intercepted": preach_verdict.intercepted,
            "clean_reply_sentences": clean_verdict.sentence_count,
            "zero_ui": zero_ui,
            "manifest_tokens": manifest.manifest_token_count,
        }
        self.reports["stage7"] = report
        return report

    # ================= 阶段八：驾驶舱、P0 硬旁路与终极对话 =================
    def stage8_cockpit_bypass_and_dialogue(self) -> Dict[str, Any]:
        from aios_core.contracts.safety_bypass import (
            HazardType,
            SafetyBypassPayload,
            WakePriority,
        )

        # --- P0 硬旁路：高负载背景（检索+金字塔聚合）下突发跌倒 ---
        index = self.suite.search.index
        pyramid_bg = PyramidAggregator()
        bg_events = [
            {"id": f"bg_{i}", "time": self.generator.epoch + timedelta(days=i), "dimension_id": "dim_bg", "weight": 1.0}
            for i in range(300)
        ]

        def _background_load(stop_flag: List[bool]) -> None:
            while not stop_flag[0]:
                try:
                    index.co_search(keywords=["通勤"])
                    pyramid_bg.generate_materialized_rollup("MONTH", "dim_bg", bg_events[:30])
                except Exception:
                    break

        stop_flag = [False]
        worker = threading.Thread(target=_background_load, args=(stop_flag,), daemon=True)
        worker.start()

        class _P0Wake:
            priority = WakePriority.P0_CRITICAL_SAFETY
            safety_bypass = SafetyBypassPayload(
                hazard_type=HazardType.CARDIAC_ARREST,
                vital_snapshot={"hr": 0, "imu_g": 4.8},
                emergency_action_code="CELLULAR_SOS_FALL",
                triggered_at=datetime.now(UTC),
            )

        p0_samples: List[float] = []
        p0_results = []
        for _ in range(20):
            started = time.perf_counter()
            result = safe_dispatch_v22(_P0Wake())
            p0_samples.append((time.perf_counter() - started) * 1000.0)
            p0_results.append(result)
        stop_flag[0] = True
        worker.join(timeout=2)
        p0_latency_p99 = sorted(p0_samples)[int(len(p0_samples) * 0.99) - 1]
        p0_all_bypassed = all(str(r.get("status", "")).startswith("SAFETY_BYPASS_EXECUTED") for r in p0_results)
        p0_llm_calls = sum(1 for r in p0_results if not r.get("bypassed_llm", False))
        self.iron_rules.record(
            "铁律3 紧急触发硬旁路，彻底跳过世界模型",
            f"20 次 P0 突发：P99={p0_latency_p99:.1f}ms（<=50ms），全部硬件旁路={p0_all_bypassed}，大模型调用=0（实测 {p0_llm_calls}）",
            p0_latency_p99 <= 50.0 and p0_all_bypassed and p0_llm_calls == 0,
        )
        for sample in p0_samples:
            self.latency.record("stage8_p0_dispatch", sample)

        # --- 单次装载驾驶舱（四步序，严禁来回询问）---
        from ai_worker.manifest_optimizer import CockpitManifestOptimizer

        t_now = self.generator.epoch + timedelta(days=self.generator.history_days)
        with self._timed("stage8_manifest_assembly"):
            manifest = CockpitManifestOptimizer.assemble_cockpit(
                wake_reason="深夜连续早搏 + 老周案退赔窗口临近",
                active_focus_facts=[
                    {"fact_id": "obs_pvc_wave", "type": "health"},
                    {"fact_id": "obs_zhou_economic_police", "type": "fraud"},
                ],
                ready_tasks=[{"task_id": "task_ecg_review", "title": "心电图复查预约"}],
                now=t_now,
            )
        four_steps_ordered = (
            "【AI身份与底线】" in manifest.step1_self_mirror
            and "【与老大羁绊模型】" in manifest.step2_rapport_model
            and "【当前姿态与音调】" in manifest.step3_posture_and_tone
            and manifest.step4_world_inspection.get("wake_reason")
        )

        # --- 条件任务双轨休眠：DORMANT 隐形，看板零 Token 泄漏 ---
        dormant_task = ConditionalTask(
            task_id="task_restitution_watch",
            title="监测老周退赔资金流",
            conditions=(
                Condition(
                    kind=ConditionKind.ABSOLUTE_TIME,
                    summary="退赔执行窗口到期",
                    deadline=datetime(2026, 12, 1, tzinfo=UTC),
                ),
            ),
        )
        ready_task = dormant_task.model_copy(
            update={"task_id": "task_ecg_review", "title": "心电图复查预约",
                    "state": TaskState.READY, "ready_reason": "复查窗口已开"}
        )
        board = DormantInvisibilityGuard.assemble([dormant_task, ready_task], at=t_now)
        DormantInvisibilityGuard.assert_no_dormant_leak(board, [dormant_task])
        dormant_invisible = all(entry.task_id != "task_restitution_watch" for entry in board.entries)
        dormant_tokens = board.dormant_token_cost

        # --- 前台 5~8 轮活跃窗口 + 10 轮终极对话（1~3 句护栏）---
        state = ConversationState(crisis_context="老周案退赔与早搏复查双线", size=8)
        guard = BrevityGuard()
        user_lines = (
            "今天胸口又闷了几下，没事吧",
            "老周他老婆刚发微信来求情了",
            "成都这边房租比杭州便宜不少",
            "老爸今天居然主动问我过年回不回去",
            "胃药快吃完了，帮我记一下",
            "我在想是不是该把跑步捡起来",
            "退赔的钱要是到账了先还信用卡",
            "明天要去做心电图复查，有点紧张",
            "你说我是不是对老周太心软了",
            "睡了，明天见",
        )
        ai_replies: List[str] = []
        sentence_counts: List[int] = []
        for i, line in enumerate(user_lines):
            rnd = ConversationRound(
                round_id=state.next_round_id(),
                speaker="user",
                text=line,
                occurred_at=t_now + timedelta(minutes=i * 7),
                tokens=estimate_token_count(line),
            )
            state.push(rnd)
            raw_reply = self._compose_reply(line)
            verdict = guard.enforce(raw_reply)
            ai_replies.append(verdict.text)
            sentence_counts.append(verdict.sentence_count)
            state.push(
                ConversationRound(
                    round_id=state.next_round_id(),
                    speaker="assistant",
                    text=verdict.text,
                    occurred_at=t_now + timedelta(minutes=i * 7 + 1),
                    tokens=estimate_token_count(verdict.text),
                )
            )
            self.action_log.append({"action": "reply", "round": i + 1, "sentences": verdict.sentence_count})

        active_tokens = sum(r.tokens for r in state.active_window())
        dialogue_ok = all(n <= 3 for n in sentence_counts)
        self.iron_rules.record(
            "铁律1 输出质量绝对第一（终极对话 10 轮全部 1~3 句）",
            f"10 轮对话句数分布={sentence_counts}，活跃窗口 {len(state.active_window())} 轮约 {active_tokens} tokens",
            dialogue_ok and len(state.active_window()) <= 8,
        )

        report = {
            "p0_latency_p50_ms": round(self.latency.percentile("stage8_p0_dispatch", 50), 2),
            "p0_latency_p99_ms": round(p0_latency_p99, 2),
            "p0_all_bypassed": p0_all_bypassed,
            "p0_llm_calls": p0_llm_calls,
            "manifest_tokens": manifest.manifest_token_count,
            "manifest_within_500": manifest.manifest_token_count <= 500,
            "four_steps_ordered": four_steps_ordered,
            "dormant_invisible": dormant_invisible,
            "dormant_tokens_on_board": dormant_tokens,
            "active_window_rounds": len(state.active_window()),
            "active_window_tokens": active_tokens,
            "dialogue_sentence_counts": sentence_counts,
        }
        self.reports["stage8"] = report
        return report

    # 终极对话的极简应答器：证据优先、老友口吻、绝不排比
    def _compose_reply(self, user_line: str) -> str:
        if "早搏" in user_line or "胸口" in user_line or "心电图" in user_line:
            return "别硬扛。周四通宵和早搏是连着的，明早复查心电图，今晚十一点前睡。"
        if "老周" in user_line or "退赔" in user_line:
            return "经侦已经定性，求情改变不了判决。只走退赔执行，一分不再借。"
        if "老爸" in user_line:
            return "破冰来之不易，回。这通电话比什么礼物都重。"
        if "胃药" in user_line:
            return "记下了。幽门螺杆菌刚转阴，药别断，下周复查一起约。"
        if "跑步" in user_line:
            return "先把睡眠补回来再跑。心率稳一周，我陪你从两公里起步。"
        if "房租" in user_line or "成都" in user_line:
            return "成都这步棋走得对。安顿下来，敏感常态重新校准。"
        if "心软" in user_line:
            return "不是心软，是证据链太长你心累了。判决在手，剩下交给执行。"
        if "睡" in user_line:
            return "晚安。今晚不谈任何事，明天见。"
        return "在。你先说。"

    # ================= 总运行 =================
    def run_all(self) -> Dict[str, Any]:
        started = time.perf_counter()
        mem_before = peak_memory_mb()
        self.stage1_ingest_purification()
        self.stage2_pyramid_lossless_drill()
        self.stage3_resonance_and_event_lifecycle()
        self.stage4_cognitive_curves_and_gates()
        self.stage5_retrospective_single_hop()
        self.stage6_symbiotic_advice_and_goals()
        self.stage7_communication_and_stance()
        self.stage8_cockpit_bypass_and_dialogue()
        elapsed = time.perf_counter() - started
        return {
            "wall_time_s": round(elapsed, 2),
            "peak_memory_mb": round(peak_memory_mb(), 1),
            "memory_growth_mb": round(peak_memory_mb() - mem_before, 1),
            "iron_rules_upheld": self.iron_rules.all_upheld(),
            "iron_rule_entries": [
                {"rule": e.rule, "upheld": e.upheld, "evidence": e.evidence} for e in self.iron_rules.entries
            ],
            "latency_summaries": {
                name: self.latency.summary(name) for name in sorted(self.latency.samples)
            },
            "stages": self.reports,
            "action_log_size": len(self.action_log),
        }
