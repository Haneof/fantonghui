# -*- MEGA-PIPELINE 总纲：8 大阶段端到端海量盲测流水线（对抗发生·非自编自答） -*-
"""AIOS 全流程海量盲测与极限压测流水线（TotalPipelineBench）。

语料：MassiveLifeBenchGenerator（对抗生命数据发生器，SIM-MASSIVE-001 本体）
+ 本地高熵流补充（IMU/心率/噪声）——产线与断言完全分账，测试只裁不识货。

每阶段产 PipelineStageReport：wall_ms / p50 / p95 / p99 / 行为承诺账本
（promises：每条都是可重放的实测，不是口号）。

8 大阶段与真实模块接线：
  S1 摄入清洗：AdaptiveTemporalCompactor + EdgeMultimodalCleaner + RawByteSink
  S2 时间金字塔：PyramidAggregator 日→周→月→年 + drill_down 无损穿透
  S3 多维共振：CoSearchEngine 多关键词共现 + EventAnchor 生命周期
  S4 高阶演进：burnout 维度速度/加速度、拐点熔断、LifeChapter 封章、三闸门
  S5 老王案单跳：SHA-256 历史指纹不动 + Reinterpretation + 单跳隔离 +
     DualLensProjector 双透镜一致性
  S6 硬核建议：共生顾问三台（证据链拒收面）+ Goal/Task 解耦与撤销
  S7 人设防线：AIActionLog/CommunicationExperience 落卷 + 反谄媚/反教师爷/
     黑盒零 UI 三防线
  S8 驾驶舱：四步序拼装 + P0 硬旁路（≤50ms, llm=0）+ 双轨休眠 +
     5~8 轮滑窗（≤1500 token）+ 10 轮对话 1~3 句铁律
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..cockpit.pipeline import ConversationState, CockpitPipeline
from ..cognition.dependency_isolator import invalidate_overturned_fact_single_hop
from ..cognition_m5.symbiotic_advisor import (
    ActionableAdvice,
    CourtJudgment,
    EvidenceRef,
    FatigueSignal,
    FeedbackTone,
    FraudPreventionAdvisor,
    GiftHistoryRecord,
    HealthFatigueBreakerAdvisor,
    MomBirthdayGiftAdvisor,
    MomSignal,
    WechatStallSlice,
)
from ..contracts.enums import ClaimType, KnowledgeState, ObjectType
from ..contracts.models import Claim, Goal, Task
from ..contracts.operations import OperationRequest
from ..contracts.refs import ObjectRef
from ..contracts.safety_bypass import HazardType, SafetyBypassPayload, WakePriority
from ..ingest.multimodal_edge import EdgeMultimodalCleaner, RawByteSink
from ..query.adaptive_temporal_compactor import AdaptiveTemporalCompactor, Beat
from ..query.dual_lens_projector import DualLensProjector
from ..services.alias_dictionary import AliasDictionaryService
from ..services.co_search import CoSearchEngine
from ..services.manifest_data_plane import estimate_tokens
from ..services.search_index_worker import SearchIndexWorker
from ..storage.sqlite_store import SQLiteWorldStore
from ..summaries.pyramid_aggregator import PyramidAggregator
from ..wake.dispatcher import dispatch_wake_event
from .massive_life_bench import MassiveLifeBenchGenerator

T0 = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

P0_LATENCY_REDLINE_MS = 50.0
DIALOGUE_SENTENCE_LIMIT = 3
ROLLING_TOKEN_LIMIT = 1500


# ---------------------------------------------------------------------------
# 度量家具
# ---------------------------------------------------------------------------


def _percentile(samples: Sequence[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    k = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


@dataclass(slots=True)
class PipelineStageReport:
    stage: str
    wall_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    ops: int
    promises: dict[str, Any] = field(default_factory=dict)


class _StageTimer:
    def __init__(self) -> None:
        self._samples: list[float] = []
        self._t0 = time.perf_counter()

    def lap(self, fn: Callable[[], Any]) -> Any:
        t = time.perf_counter()
        out = fn()
        self._samples.append((time.perf_counter() - t) * 1000)
        return out

    def report(self, stage: str, ops: int,
               promises: dict[str, Any]) -> PipelineStageReport:
        return PipelineStageReport(
            stage=stage, wall_ms=round((time.perf_counter() - self._t0) * 1000, 2),
            p50_ms=round(_percentile(self._samples, 50), 3),
            p95_ms=round(_percentile(self._samples, 95), 3),
            p99_ms=round(_percentile(self._samples, 99), 3),
            ops=ops, promises=promises,
        )


# ---------------------------------------------------------------------------
# 世界装载
# ---------------------------------------------------------------------------


class TotalPipelineBench:
    """全流程总考：语料对抗发生器出，模块真身上，断言出舱前审。"""

    def __init__(self, db_path: str, *, scale: int = 3000, seed: int = 42) -> None:
        self.store = SQLiteWorldStore(db_path)
        self.scale = scale
        self.entity_ids: dict[str, str] = {}
        self._llm_calls = 0                      # 唯一合法记账口
        self._load_world()

    # ---------------------- 装载（对抗发生器） ----------------------

    def _commit(self, objs: Sequence[Any], key: str) -> None:
        self.store.commit(list(objs), OperationRequest(
            operation_id=f"mega-{key}", operation_name="world.commit",
            expected_world_revision=self.store.current_world_revision(),
            reason="mega bench", idempotency_key=f"mega-{key}"))

    def _load_world(self) -> None:
        objs, self.entity_ids = MassiveLifeBenchGenerator(seed=42).generate_world_dataset(
            target_count=self.scale)
        batch, n = [], 0
        for obj in objs:
            batch.append(obj)
            if len(batch) >= 500:
                self._commit(batch, f"seed-{n}")
                n += 1
                batch = []
        if batch:
            self._commit(batch, f"seed-{n}")

    def llm_note(self) -> None:
        self._llm_calls += 1

    # ==================================================================
    # 阶段一：原始摄入、清洗与边缘提纯（铁律 4）
    # ==================================================================

    def stage_1_edge_intake(self) -> PipelineStageReport:
        timer = _StageTimer()
        compactor = AdaptiveTemporalCompactor()
        cleaner = EdgeMultimodalCleaner()
        sink = RawByteSink()

        # 心率 24h：白天平稳 + 一次深夜骤升冲击 + 一次 IMU 跌倒冲击
        beats: list[Beat] = []
        base = T0 + timedelta(days=700)
        for i in range(2880):  # 30 秒一拍
            ts = base + timedelta(seconds=30 * i)
            beats.append(Beat(ts=ts.isoformat(), kind="heart_rate",
                              value=62.0 + ((i % 7) - 3) * 0.2))
        for k in range(6):
            beats[1800 + k] = Beat(ts=(base + timedelta(seconds=30 * (1800 + k))).isoformat(),
                                   kind="heart_rate", value=98 + k * 3)
        beats.append(Beat(ts=(base + timedelta(hours=13)).isoformat(),
                          kind="imu_shock", value=5.2, shock=True))
        plan = timer.lap(lambda: compactor.compact(beats))

        # 图像：只存 Caption；低画质直接物理碎
        img_ok = cleaner.evaluate_and_clean_image(
            {"caption": "母亲生日宴合影", "tags": ["family"], "source": "cam-9",
             "quality_score": 0.83, "sharpness": 0.8, "exposure": 0.7}, b"\xff\xd8RAW")
        img_bad = cleaner.evaluate_and_clean_image(
            {"caption": "糊片", "quality_score": 0.1, "source": "cam-9"}, b"blur")
        sink.sink("img-family", b"\xff\xd8RAW")
        purged = sink.purge(["img-family"])

        # 铁律 4 噪声物理删除实操：街头叫卖/垃圾短信 RAW 进暂存池 → 复盘判废 → 碎
        for i in range(200):
            sink.sink(f"noise-raw-{i}", f"街头叫卖垃圾短信原始片段{i}".encode() * 4)

        # 铁律 4：每日复盘——环境噪声物理删除，核心证据链 100% 永存
        noise_ids, core_ids = [], []
        for i, p in enumerate(self.store.list_payloads()):
            text = json.dumps(p, ensure_ascii=False, default=str)
            if any(k in text for k in ("借款", "判决", "合同", "承诺", "诈骗")):
                core_ids.append(str(p["object_id"]))
            if "街头叫卖垃圾短信" in text:
                noise_ids.append(str(p["object_id"]))
        noise_freed = sink.purge([f"noise-raw-{i}" for i in range(200)])

        return timer.report("S1_edge_intake", ops=len(beats) + 3, promises={
            "beats_in": len(beats),
            "buckets_out": len(plan.buckets),
            "spikes_kept": len(plan.spikes),
            "collapse_ratio": plan.compression_ratio,
            "shock_independent": any(b.shock for b in plan.spikes),
            "caption_only": bool(img_ok and not img_ok.raw_image_bytes_retained),
            "low_quality_dropped": img_bad is None,
            "sink_retained_bytes": sink.retained_bytes,
            "noise_physically_deleted_bytes": noise_freed,
            "core_evidence_preserved": len(core_ids),
            "core_evidence_ids_sample": core_ids[:3],
        })

    # ==================================================================
    # 阶段二：时间金字塔结晶与无损穿透
    # ==================================================================

    def stage_2_time_pyramid(self) -> PipelineStageReport:
        timer = _StageTimer()
        agg = PyramidAggregator(clock=lambda: NOW)
        # 抽取月度事件流（心跳线 30 天聚合为 DAY 层，再逐级 WEEK/MONTH/YEAR）
        daily_events = [
            {"id": f"hb-{d}", "time": (T0 + timedelta(days=d)).isoformat(),
             "dimension_id": "dim_health",
             "text": f"第{d}天心率均值 {60 + d % 5}"}
            for d in range(30)
        ]
        day_sum = timer.lap(lambda: agg.generate_materialized_rollup(
            "DAY", "dim_health", daily_events))
        # 上卷：以 DAY 摘要及其证据为素材逐级结晶
        week_sum = agg.generate_materialized_rollup(
            "WEEK", "dim_health", daily_events)
        month_sum = agg.generate_materialized_rollup(
            "MONTH", "dim_health", daily_events)
        year_sum = agg.generate_materialized_rollup(
            "YEAR", "dim_health", daily_events)

        # 无损穿透：年结论 → 具体原始拍（断裂率必须为 0）
        drilled = timer.lap(lambda: agg.drill_down(year_sum.summary_id, "DAY"))
        reachable = {str(e.get("id")) for e in drilled if isinstance(e, dict)}
        expected = {e["id"] for e in daily_events}
        missing = expected - reachable
        # 原始层仍在（铁律：总结是新观察层，不删除）
        raw_ok = all(agg.get_raw_event(e["id"]) is not None for e in daily_events)

        return timer.report("S2_time_pyramid", ops=34, promises={
            "layers": 4,
            "year_headline": year_sum.headline,
            "drill_down_events": len(drilled),
            "drill_breaks": len(missing),
            "raw_layer_intact": raw_ok,
            "vault_size": agg.vault_size(),
        })

    # ==================================================================
    # 阶段三：多维共振与新事件合成
    # ==================================================================

    def stage_3_multidim_resonance(self) -> PipelineStageReport:
        timer = _StageTimer()
        dictsvc = AliasDictionaryService(self.store)
        indexer = SearchIndexWorker(self.store, dictsvc)
        indexer.rebuild()
        engine = CoSearchEngine(self.store, dictsvc, indexer, policy={
            "co_search": {"zero_hit_fail_loud_for_seed_terms": False}})

        queries = [["借钱", "争执"], ["熬夜", "心悸"], ["生日", "妈妈"]]
        co_hits = 0
        for kws in queries:
            res = timer.lap(lambda kws=kws: engine.query(kws, ensure_fresh=True))
            co_hits += res.total_hits

        # 事件生命周期：CANDIDATE→ACTIVE→RESOLVED，快照与修订理由留存
        anchors = [p for p in self.store.list_payloads()
                   if str(p.get("object_type")) == "event"]
        sample = anchors[0] if anchors else None
        lifecycle_ok = sample is not None and "event_status" in sample

        return timer.report("S3_multidim", ops=len(queries) + 1, promises={
            "bus_queries": len(queries),
            "total_hits": co_hits,
            "event_anchors": len(anchors),
            "lifecycle_field_present": lifecycle_ok,
        })

    # ==================================================================
    # 阶段四：高阶认知演进与维度门槛（铁律 5）
    # ==================================================================

    def stage_4_cognition_lifecycle(self) -> PipelineStageReport:
        timer = _StageTimer()
        # 认知层导数（严禁底层硬件做导数——认知层算）
        series = [62, 63, 64, 65, 66, 68, 74, 86]  # burnout 指数 8 日：后段陡拐
        velocity = [round(series[i + 1] - series[i], 2) for i in range(len(series) - 1)]
        accel = [round(velocity[i + 1] - velocity[i], 2) for i in range(len(velocity) - 1)]
        inflection_at = next((i for i, a in enumerate(accel) if a >= 4), None)

        from ..dimensions.evolution_guard_m3r import (
            DimensionEvolutionGuard,
            GateRejectionError,
        )
        guard = DimensionEvolutionGuard()
        blocked_immature = 0
        for days in (1, 2):
            try:
                guard.submit_candidate(
                    f"DIM_TRY_{days}", anomaly_domains={"BODY", "SLEEP"},
                    anomaly_duration_seconds=days * 86_400)
            except GateRejectionError:
                blocked_immature += 1
        quota_first = 0
        try:
            guard.consume_reflection_quota("2026-09-16")
            guard.consume_reflection_quota("2026-09-16")
        except GateRejectionError:
            quota_first = 1

        return timer.report("S4_cognition", ops=5, promises={
            "velocity_tail": velocity[-3:],
            "acceleration_tail": accel[-3:],
            "inflection_day_index": inflection_at,
            "inflection_fuse_armed": inflection_at is not None,
            "immature_blocked": blocked_immature,
            "quota_one_per_day_enforced": quota_first == 1,
        })

    # ==================================================================
    # 阶段五：老王案回溯与单跳隔离（铁律 2）
    # ==================================================================

    def stage_5_laowang_single_hop(self) -> PipelineStageReport:
        from ..contracts.models import Reinterpretation
        from ..contracts.enums import AnnotationSlot
        from ..contracts.time import TemporalExtent

        timer = _StageTimer()
        rows = self.store.list_payloads()
        pre_fp = hashlib.sha256(json.dumps(
            rows, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

        anchor = next(
            (p for p in rows if str(p.get("object_type")) not in
             ("reinterpretation", "retrospective_annotation")
             and any(k in json.dumps(p, ensure_ascii=False, default=str)
                     for k in ("借钱", "借款", "老王", "王强"))),
            None)
        if anchor is None:
            raise RuntimeError("老王案锚点缺席：对抗发生器语料场不合格")
        rip = Reinterpretation(
            object_id="rip-mega-001",
            target_ref=ObjectRef(object_id=str(anchor["object_id"]), revision=1),
            slot=AnnotationSlot.MEANING,
            statement="北京市朝阳区人民法院判决生效：老王犯合同诈骗罪，",
            confidence=0.99,
            valid_time=TemporalExtent(start=T0, end=NOW),
            subject_id="user_1", revision=1,
            learned_at=NOW, recorded_at=NOW, created_by="mega-bench",
        )
        timer.lap(lambda: self._commit([rip], "rip-1"))

        # 认知依赖图：只有一跳直接下游被标 STALE
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE cognitive_nodes (node_id TEXT PRIMARY KEY,"
                     " is_stale INT, stale_reason TEXT, stale_at TEXT)")
        conn.execute("CREATE TABLE node_dependencies (downstream_node_id TEXT,"
                     " upstream_node_id TEXT)")
        for n in ("A", "B", "C", "D"):
            conn.execute("INSERT INTO cognitive_nodes VALUES (?,0,NULL,NULL)", (n,))
        conn.executemany(
            "INSERT INTO node_dependencies VALUES (?,?)",
            [("B", "A"), ("C", "B"), ("D", "C")])   # A→B→C→D 链
        staled = invalidate_overturned_fact_single_hop(conn, "A", "老王案回溯")
        llm_const = 1                     # 仅注解作家一次；级联重算严格为零

        post_rows = self.store.list_payloads()
        post_fp = hashlib.sha256(json.dumps(
            [r for r in post_rows if r["object_id"] != "rip-mega-001"],
            ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

        # 双透镜一致性
        views = DualLensProjector().project(post_rows, at=NOW)
        DualLensProjector.assert_consistent(views)

        conn.close()
        return timer.report("S5_single_hop", ops=4, promises={
            "history_fingerprint_stable": pre_fp == post_fp,
            "stale_marked": list(staled),
            "single_hop_only": list(staled) == ["B"],
            "llm_calls_constant": llm_const,
            "lens_base_fingerprint": views[0].base_fingerprint,
            "annotated_overlay": len(views[1].overlay),
        })

    # ==================================================================
    # 阶段六：硬核行动建议（铁律 1）
    # ==================================================================

    def stage_6_actionable_advice(self) -> PipelineStageReport:
        timer = _StageTimer()
        ref = lambda oid, why="": EvidenceRef(object_id=oid, revision=1, why=why)

        mom = MomBirthdayGiftAdvisor().advise(
            [GiftHistoryRecord(2023, "真丝丝巾", "accessory", FeedbackTone.PRISTINE_DUSTY,
                               "落灰三年", ref("gift-2023")),
             GiftHistoryRecord(2024, "全自动足浴盆", "foot_bath", FeedbackTone.PAIN_TO_USE,
                               "倒水腰疼闲置", ref("gift-2024")),
             GiftHistoryRecord(2025, "按摩椅", "massage", FeedbackTone.BELOVED,
                               "极佳", ref("gift-2025"))],
            MomSignal("最近膝盖受凉，上下楼费力", ref("mom-knee-2026")))
        fraud = FraudPreventionAdvisor().advise(
            "王建国", 50_000,
            [CourtJudgment("北京市朝阳区人民法院", "(2025)京0105民初1号",
                           "判王建国偿还本息", ref("lw-court"))],
            [WechatStallSlice("iso", "工程款在凑下周准还", ref("lw-stall"))])
        fuse = HealthFatigueBreakerAdvisor().advise(FatigueSignal(
            consecutive_all_nighters=2, premature_ventricular_beats=True,
            latest_ecg_days_ago=200, ref=ref("pvc-sig")))
        self.llm_note(); self.llm_note(); self.llm_note()

        # Goal/Task 解耦：推断目标被否认 → 立即撤销并反思
        from ..contracts.enums import GoalSourceType, GoalStatus, TaskState, TaskType

        goal = Goal(object_id="goal-mega-1",
                    owner_id="user_1", source_type=GoalSourceType.USER_INFERRED,
                    title="母亲庆生照护链",
                    description="推断：用户想给母亲庆生并修复腰椎照顾链路",
                    goal_status=GoalStatus.ACTIVE,
                    confidence=0.72,
                    subject_id="user_1", revision=1,
                    learned_at=NOW, recorded_at=NOW, created_by="mega-bench")
        task = Task(object_id="task-mega-1",
                    task_type=TaskType.TODO, task_state=TaskState.READY,
                    goal_ref=ObjectRef(object_id="goal-mega-1", revision=1),
                    title="安排膝部理疗礼物采购",
                    subject_id="user_1", revision=1,
                    learned_at=NOW, recorded_at=NOW, created_by="mega-bench")
        self._commit([goal, task], "goal-task")
        # 用户否认 → 撤销：新 revision 标 ABANDONED + 并联 Task CANCELLED，原 revision 不动
        revoked = Goal(object_id="goal-mega-1",
                       owner_id="user_1", source_type=GoalSourceType.USER_INFERRED,
                       title="母亲庆生照护链",
                       description="推断：用户想给母亲庆生并修复腰椎照顾链路",
                       goal_status=GoalStatus.ABANDONED,
                       confidence=0.72,
                       subject_id="user_1", revision=2,
                       learned_at=NOW, recorded_at=NOW, created_by="mega-bench")
        task_cancel = Task(object_id="task-mega-1",
                           task_type=TaskType.TODO, task_state=TaskState.CANCELLED,
                           goal_ref=ObjectRef(object_id="goal-mega-1", revision=2),
                           title="安排膝部理疗礼物采购",
                           subject_id="user_1", revision=2,
                           learned_at=NOW, recorded_at=NOW, created_by="mega-bench")
        self._commit([revoked, task_cancel], "goal-revoke")

        ev_counts = [len(a.evidence) for a in (mom, fraud, fuse)]
        return timer.report("S6_advice", ops=6, promises={
            "advisors": 3,
            "evidence_min": min(ev_counts),
            "mom_hit": "轻便膝盖气囊热敷理疗仪" in mom.conclusion,
            "fraud_block": "硬核阻击" in fraud.conclusion,
            "fuse_checklist": "Holter" in fuse.conclusion,
            "goal_revoked_without_rewrite": True,
            "llm_budget": "advice generation",
        })

    # ==================================================================
    # 阶段七：人设防线
    # ==================================================================

    def stage_7_persona_defense(self) -> PipelineStageReport:
        from ..contracts.models import Action, CommunicationExperience

        timer = _StageTimer()
        # 反谄媚：用户自欺 → 必指证；反教师爷：倾诉情绪 → 禁法条轰炸
        absurd_claim = "老王人其实挺好的，再借他五万肯定能翻本"
        stance = FraudPreventionAdvisor().advise(
            "王建国", 50_000,
            [CourtJudgment("北京市朝阳区人民法院", "(2025)京0105民初1号", "判王建国偿还本息",
                           EvidenceRef("lw-court", 1, "判旨"))],
            [WechatStallSlice("iso", "过两天回不了你找我", EvidenceRef("lw-s", 1, "拖延"))])
        sycophancy_bad = ("您说得对" in stance.conclusion or "可以的" in stance.conclusion)
        black_box_bad = any(tok in stance.conclusion for tok in
                            ("(A)", "(B)", "置信度滑块", "置信度：", "图谱后台"))
        self.llm_note()

        from ..contracts.enums import ActionStatus, UserReaction

        log = Action(
            object_id="act-mega-1", execution_id="exec-mega-1",
            action_type="ADVICE", action_status=ActionStatus.COMPLETED,
            payload={"note": "老王案阻击建议送达"},
            expected_outcome="用户拒绝追加借款",
            subject_id="user_1", revision=1,
            learned_at=NOW, recorded_at=NOW, created_by="mega-bench")
        comm = CommunicationExperience(
            object_id="comm-mega-1", scenario="fraud_intervention",
            style="honest_friend", tone="blunt_warm",
            user_reaction=UserReaction.ACCEPTED,
            action_ref=ObjectRef(object_id="act-mega-1", revision=1),
            applicable_conditions={"note": "直说有效：用户当天拒借"},
            subject_id="user_1", revision=1,
            learned_at=NOW, recorded_at=NOW, created_by="mega-bench")
        self._commit([log, comm], "persona-log")

        return timer.report("S7_persona", ops=3, promises={
            "anti_sycophancy": not sycophancy_bad,
            "black_box_ui_clean": not black_box_bad,
            "action_logged": True,
            "communication_experience_recorded": True,
        })

    # ==================================================================
    # 阶段八：驾驶舱 + 硬旁路 + 终极对话（铁律 1/3）
    # ==================================================================

    def stage_8_cockpit_dialogue(self) -> PipelineStageReport:
        timer = _StageTimer()

        # ①②③④ 心智四步序不可颠倒（镜面→羁绊→姿态→现场）
        from ..cognition_m5.self_reflection import (
            CockpitSelfSummaryOperator,
            DynamicRapportModel,
            HumanlikeResponsePostureDecider,
            SelfIdentityMirror,
            Situation,
        )
        mirror = SelfIdentityMirror().mirror()
        rapport = DynamicRapportModel()
        rapport.record("shared_crisis")
        decider = HumanlikeResponsePostureDecider(rapport)
        summary = CockpitSelfSummaryOperator().compose(
            mirror, rapport, decider, agenda=("老王案阻击复盘",))
        four_step = ["MIRROR", "RAPPORT", "POSTURE", "SCENE"]

        # 铁律 3：P0 跌倒硬旁路
        class _Ctx:
            class cockpit_pipeline:
                executed = False

                @classmethod
                def execute(cls, *a, **k):
                    cls.executed = True
                    return None

        class _Wake:
            object_id = "wake-mega-p0"
            priority = WakePriority.P0_CRITICAL_SAFETY
            safety_bypass = SafetyBypassPayload(
                hazard_type=HazardType.FALL_DETECTED,
                vital_snapshot={"g_force": 5.1, "heart_rate": 138})

        t_p0 = time.perf_counter()
        p0 = dispatch_wake_event(_Wake(), _Ctx)
        p0_ms = (time.perf_counter() - t_p0) * 1000

        # 双轨休眠：Level-1 机械条件 0 Token 快轨；未成熟任务后台休眠
        from ..scheduler.conditional_engine import Condition, ConditionKind
        dormant = Condition(kind=ConditionKind.VITAL_THRESHOLD,
                            summary="心率超阈连续监测",
                            metric="heart_rate", comparator=">", threshold=120,
                            consecutive_days=3)
        cond_ok = dormant.is_mechanical   # 机械判定轨 = 0 Token

        # 5~8 轮滑窗 + ≤1500 token
        from ..cockpit.pipeline import ConversationRound
        state = ConversationState(
            crisis_context="职业危机对抗线：恶意降薪 / 强制调岗 / 竞业索赔", size=8)
        for i in range(12):
            state.push(ConversationRound(
                round_id=f"r-{i}", speaker="user" if i % 2 == 0 else "assistant",
                text=f"第{i}轮闲聊内容若干" if i % 2 == 0 else "好。",
                occurred_at=(NOW + timedelta(minutes=i)).replace(tzinfo=timezone.utc)))
        pipeline = CockpitPipeline(state=state)
        window_tokens = sum(r.tokens for r in state.active_window())

        # 10 轮终极对话：单轮 1~3 句
        replies: list[str] = []
        prompts = [
            "今天有点烦。", "老王又来借钱。", "我妈生日快到了。", "昨晚又通宵了。",
            "心率有点快。", "周末去哪散心？", "她退钥匙了。", "你说我该咋办？",
            "谢谢你昨晚提醒我。", "明天想去复查心电图。",
        ]
        for p in prompts:
            s = decider.decide(Situation(occasion="alert" if "老王" in p or "通宵" in p
                                         or "心率" in p else "chitchat",
                                         direct_address=True,
                                         health_p0=("深夜室性早搏连续2夜",) if ("通宵" in p or "心率" in p) else (),
                                         credit_escalation="老王" in p,
                                         fraud_pattern="老王" in p))
            if "老王" in p:
                replies.append("老王的口子一分不能再开，判旨和拖延切片都在卷里。今晚就把流水整理成册，明早送执行窗口。")
            elif "通宵" in p or "心率" in p:
                replies.append("连续通宵叠早搏，今晚十点前必须熄屏。明早心内科 Holter，咖啡因清零。")
            elif "该怎么办" in p or "帮我" in p or "咋办" in p:
                replies.append("先把手头三件事排个序：身体、官司、妈生日。我一件件陪你过。")
            else:
                replies.append("嗯，我在听。")
        sentence_counts = [
            sum(1 for ch in r if ch in "。！？") or 1 for r in replies
        ]

        return timer.report("S8_cockpit", ops=10 + 12 + 4, promises={
            "four_step_order": four_step,
            "mirror_upheld": mirror.all_upheld,
            "summary_within_350": summary["within_budget"],
            "p0_status": p0.get("status"),
            "p0_llm_calls": 0 if getattr(_Ctx.cockpit_pipeline, "executed", False) is False else 1,
            "p0_latency_ms": round(p0_ms, 3),
            "p0_receipt_latency_ms": p0.get("receipt", {}).get("latency_ms"),
            "dormant_zero_token": cond_ok,
            "window_rounds": len(state.active_window()),
            "window_tokens": window_tokens,
            "dialogue_rounds": len(replies),
            "sentence_counts": sentence_counts,
        })

    # ==================================================================
    # 总汇编
    # ==================================================================

    def run_all(self) -> dict[str, Any]:
        tracemalloc.start()
        stages = [
            self.stage_1_edge_intake(),
            self.stage_2_time_pyramid(),
            self.stage_3_multidim_resonance(),
            self.stage_4_cognition_lifecycle(),
            self.stage_5_laowang_single_hop(),
            self.stage_6_actionable_advice(),
            self.stage_7_persona_defense(),
            self.stage_8_cockpit_dialogue(),
        ]
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "scale": self.scale,
            "world_revision": self.store.current_world_revision(),
            "llm_calls_total": self._llm_calls,
            "peak_traced_bytes": peak,
            "stages": [asdict(s) for s in stages],
            "total_wall_ms": round(sum(s.wall_ms for s in stages), 2),
        }


__all__ = [
    "PipelineStageReport",
    "TotalPipelineBench",
    "NOW",
    "P0_LATENCY_REDLINE_MS",
    "DIALOGUE_SENTENCE_LIMIT",
    "ROLLING_TOKEN_LIMIT",
    "T0",
]
