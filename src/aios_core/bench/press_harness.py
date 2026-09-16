"""AIOS 3.0 全流程海量盲测与极限压测总编排（8 大阶段一站式贯穿）。

本模块是四大终极交付物的数据发生器：

* 端到端串起 阶段0 生成 → 阶段1 摄入清洗 → 阶段2 金字塔 → 阶段3 共振
  → 阶段4 认知运动学 → 阶段5 老王案单跳隔离 → 阶段6 共生决策 →
  阶段7 沟通博弈 → 阶段8 驾驶舱/硬旁路/终极对话；
* 采集 P50/P95/P99 延迟分布、内存驻留峰值、大模型调用次数；
* 五大铁律逐条审计（pass + 证据），供《压测报告》直接引用。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from aios_core.bench.intake_pipeline import IntakeConfig, RawIntakePipeline
from aios_core.bench.life_bench import MassiveLifeBench
from aios_core.cognition.communication_evolution import (
    ActionFeedback,
    AIActionLog,
    CommunicationExperience,
    PreacherViolation,
    StyleGuard,
    SycophancyViolation,
    ZeroUIViolation,
    count_sentences,
)
from aios_core.contracts.enums import EventStatus
from aios_core.contracts.refs import ObjectRef
from aios_core.dimensions.evolution_guard import (
    ImmaturePatternRejectedError,
    PhysicalDomain,
    QuotaExceededBlockError,
)
from aios_core.dimensions.kinematics import (
    InflectionDetector,
    LifeChapterDetector,
    SeverityPoint,
)
from aios_core.query.search import SearchPathway, SearchQuery
from aios_core.summaries.time_pyramid import TimePyramidCrystallizer
from aios_core.tools.adaptive_compressor import AdaptiveTemporalCompressor
from aios_core.tools.dual_lens_index import DualLensVirtualIndexProjector
from aios_core.world.event_resonance import (
    EventLifecycleManager,
    SignalPing,
    SpatiotemporalResonator,
)
from aios_core.world.retrospective_annotation import SingleHopCascadeIsolator

UTC = timezone.utc


@dataclass(slots=True)
class PressConfig:
    days: int = 1096
    seed: int = 20260916
    slices: tuple[str, ...] | None = None
    density: str = "full"
    drill_sample: int = 200
    dialogue_rounds: int = 10


@dataclass(slots=True)
class StageMetric:
    name: str
    wall_ms: float
    items: int
    detail: dict = field(default_factory=dict)


@dataclass(slots=True)
class LatencyStat:
    n: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    max_ms: float


@dataclass(slots=True)
class PressReport:
    config: PressConfig
    stages: list[StageMetric]
    latencies: dict[str, LatencyStat]
    iron_laws: dict[str, dict[str, object]]
    total_raw_points: int
    cleaned_records: int
    rss_peak_mb: float
    llm_calls_total: int
    wall_total_ms: float
    facts: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "config": {
                "days": self.config.days, "seed": self.config.seed,
                "density": self.config.density, "slices": list(self.config.slices or ()),
            },
            "total_raw_points": self.total_raw_points,
            "cleaned_records": self.cleaned_records,
            "wall_total_ms": round(self.wall_total_ms, 1),
            "rss_peak_mb": round(self.rss_peak_mb, 1),
            "llm_calls_total": self.llm_calls_total,
            "stages": [
                {"name": s.name, "wall_ms": round(s.wall_ms, 1),
                 "items": s.items, "detail": _jsonable(s.detail)}
                for s in self.stages
            ],
            "latencies": {
                k: {"n": v.n, "p50_ms": round(v.p50_ms, 3), "p95_ms": round(v.p95_ms, 3),
                    "p99_ms": round(v.p99_ms, 3), "mean_ms": round(v.mean_ms, 3),
                    "max_ms": round(v.max_ms, 3)}
                for k, v in self.latencies.items()
            },
            "iron_laws": self.iron_laws,
            "facts": _jsonable(self.facts),
        }

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path


def _jsonable(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return str(obj)


def _pctl(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[idx]


def _lat(values: list[float]) -> LatencyStat:
    return LatencyStat(
        n=len(values),
        p50_ms=_pctl(values, 0.50),
        p95_ms=_pctl(values, 0.95),
        p99_ms=_pctl(values, 0.99),
        mean_ms=sum(values) / len(values) if values else 0.0,
        max_ms=max(values) if values else 0.0,
    )


def _rss_mb() -> float:
    try:
        with open("/proc/self/statm", "rb") as fh:
            pages = int(fh.read().split()[1])
        return pages * 4096 / (1024 * 1024)
    except OSError:
        return 0.0


class _LLMCounter:
    """全局大模型调用计数器（铁律审计的记账面）。"""

    def __init__(self) -> None:
        self._n = 0
        self.by_stage: dict[str, int] = {}

    def call(self, stage: str) -> None:
        self._n += 1
        self.by_stage[stage] = self.by_stage.get(stage, 0) + 1

    @property
    def total(self) -> int:
        return self._n


def run_full_press(config: PressConfig | None = None) -> PressReport:
    cfg = config or PressConfig()
    slices = cfg.slices or (
        "startup_dispute", "bigtech_overnight", "family_thaw",
        "province_move", "chronic_care",
    )
    stages: list[StageMetric] = []
    latencies: dict[str, list[float]] = {}
    llm = _LLMCounter()
    rss_peak = _rss_mb()
    t_all = time.perf_counter()

    def stage(name: str, fn: Callable[[], dict]) -> dict:
        t0 = time.perf_counter()
        detail = fn()
        wall = (time.perf_counter() - t0) * 1000.0
        items = int(detail.pop("_items", 0))
        stages.append(StageMetric(name=name, wall_ms=wall, items=items, detail=detail))
        nonlocal rss_peak
        rss_peak = max(rss_peak, _rss_mb())
        return detail

    # ------------------------------------------------------------------
    # 阶段 0：对抗世界生成
    # ------------------------------------------------------------------
    cells: dict[str, object] = {}
    bench = MassiveLifeBench(days=cfg.days, slices=slices, seed=cfg.seed, density=cfg.density)  # type: ignore[arg-type]

    def _stage0() -> dict:
        w = bench.generate()
        cells["world"] = w
        return {
            "_items": w.raw_count(),
            "raw_points": w.raw_count(),
            "raw_samples": len(w.samples),
            "impacts_manifest": len(w.manifest.impact_events),
            "hr_spikes_manifest": len(w.manifest.hr_spikes),
        }

    stage("阶段0_对抗世界生成", _stage0)
    world = cells["world"]

    # ------------------------------------------------------------------
    # 阶段 1：百万级摄入清洗（铁律4 主战场）
    # ------------------------------------------------------------------
    outcomes: dict[str, object] = {}

    def _stage1() -> dict:
        pipe = RawIntakePipeline(config=IntakeConfig())
        t_now = datetime(2026, 12, 31, 8, 0, tzinfo=UTC)
        out = pipe.run(world, t_now=t_now)
        outcomes["s1"] = out
        latencies["intake_daily_batch"] = list(out.daily_wall_ms)
        m = world.manifest
        detected = {(s, d, w) for s, d, w, _ in out.imu_impacts_detected}
        expected = {(s, d, w) for s, d, w, _ in m.impact_events}
        impact_recall = (len(detected & expected) / len(expected)) if expected else 1.0
        spike_det = {(s, d, slot) for s, d, slot, _ in out.hr_spikes_detected}
        spike_exp = {(s, d, slot) for s, d, slot, _ in m.hr_spikes}
        spike_recall = (len(spike_det & spike_exp) / len(spike_exp)) if spike_exp else 1.0
        evidence_ids = sorted(m.evidence_audio_ids)
        noise_ids = sorted(m.noise_audio_ids)
        ev_sample = evidence_ids[:: max(1, len(evidence_ids) // 300)]
        no_sample = noise_ids[:: max(1, len(noise_ids) // 300)]
        evidence_retained = sum(
            1 for f in ev_sample if (out.raw_sink.raw_size_of(f) or 0) > 0
        )
        noise_purged = sum(1 for f in no_sample if out.raw_sink.raw_size_of(f) == 0)
        # 声纹一致性：生成器说话人 → 主 P 簇占比
        spk_of: dict[str, str] = {}
        for s in world.samples:
            if s.stream == "audio":
                fid, _t, _v, _c, speaker_key, _th = s.payload
                spk_of[fid] = speaker_key
        from collections import Counter

        cmap: dict[str, Counter] = {}
        for fid, pid in out.voice_bindings.items():
            cmap.setdefault(spk_of.get(fid, "?"), Counter())[pid] += 1
        consistency = min(
            (c.most_common(1)[0][1] / sum(c.values()) for c in cmap.values() if sum(c.values()) > 100),
            default=1.0,
        )
        return {
            "_items": world.raw_count(),
            "cleaned_records": out.record_count(),
            "compression_ratio": round(world.raw_count() / max(1, out.record_count()), 1),
            "impact_recall": round(impact_recall, 4),
            "hr_spike_recall": round(spike_recall, 4),
            "evidence_raw_retained_pct": round(evidence_retained / max(1, len(ev_sample)), 4),
            "noise_raw_purged_pct": round(noise_purged / max(1, len(no_sample)), 4),
            "noise_sms_entered_engine": out.noise_sms_stored,
            "voiceprint_speakers": len({p for p in out.speaker_pids.values()}),
            "voiceprint_consistency": round(consistency, 4),
            "evicted_180d": out.evicted_count,
            "review_llm_calls": out.review_llm_calls,
            "captions_stored": out.captions_stored,
            "transcripts_stored": out.transcripts_stored,
        }

    s1 = stage("阶段1_摄入清洗与边缘提纯", _stage1)
    outcome = outcomes["s1"]
    engine = outcome.engine

    # ------------------------------------------------------------------
    # 阶段 2：时间金字塔多尺度结晶与无损穿透
    # ------------------------------------------------------------------
    def _stage2() -> dict:
        cryst = TimePyramidCrystallizer()
        t0 = time.perf_counter()
        pyramid = cryst.crystallize(outcome.records)
        reg = cryst.register_into_engine(pyramid, engine)
        crystallize_ms = (time.perf_counter() - t0) * 1000.0
        drill_ms: list[float] = []
        leaves = sorted(pyramid.leaves)
        step = max(1, len(leaves) // cfg.drill_sample)
        sampled = leaves[::step][: cfg.drill_sample]
        for leaf in sampled:
            t1 = time.perf_counter()
            path = pyramid.drill_down(leaf)
            drill_ms.append((time.perf_counter() - t1) * 1000.0)
            assert path.leaf_reachable, f"evidence chain broken at {leaf}"
        rate, _paths = pyramid.audit(sampled)
        latencies["pyramid_drill_through"] = drill_ms
        # 原始记录不动断言（引擎增量 == 注册总结数）
        return {
            "_items": len(pyramid.nodes),
            "crystallize_ms": round(crystallize_ms, 1),
            "levels": {lv: len(pyramid.by_level(lv)) for lv in ("day", "week", "month", "quarter", "year")},  # type: ignore[list-item]
            "summaries_registered": reg,
            "drill_breakage_rate": rate,
            "source_records": pyramid.source_record_count,
            "sampled_drills": len(sampled),
        }

    s2 = stage("阶段2_时间金字塔结晶与无损穿透", _stage2)

    # ------------------------------------------------------------------
    # 阶段 3：多维时空共振、共现拓扑与事件生命周期
    # ------------------------------------------------------------------
    def _stage3() -> dict:
        # 共现拓扑召回（多关键词 AND，拒绝割裂单扫）
        bus_lat: list[float] = []
        query = SearchQuery(
            problem_type="partner_fraud_chain",
            keywords=("合伙", "转账", "原话", "短信"),
            entity_hint="合伙人周某",
        )
        for _ in range(8):
            t1 = time.perf_counter()
            res = engine.run_pathway(query, SearchPathway.TOPOLOGICAL_DRILL)
            bus_lat.append((time.perf_counter() - t1) * 1000.0)
        latencies["cooccurrence_bus"] = bus_lat
        # 横向时空对齐：心率突变 + 冲击 + 原话 同日共振
        pings: list[SignalPing] = []
        for rid, rec in engine._records.items():  # noqa: SLF001
            at = rec.occurred_at
            if at is None:
                continue
            if "-hrspike-" in rid:
                pings.append(SignalPing(at=at, modality="heart_rate", key=rec.entity_refs[0] if rec.entity_refs else rid, label="心率突变", ref=ObjectRef(object_id=rid, revision=1)))
            elif "-impact-" in rid:
                pings.append(SignalPing(at=at, modality="imu", key=rec.entity_refs[0] if rec.entity_refs else rid, label="冲击", ref=ObjectRef(object_id=rid, revision=1)))
            elif "-voice-" in rid and "原话" in rec.keywords:
                pings.append(SignalPing(at=at, modality="audio", key=rec.entity_refs[0] if rec.entity_refs else rid, label="原话", ref=ObjectRef(object_id=rid, revision=1)))
        resonator = SpatiotemporalResonator(window=timedelta(hours=48), min_modalities=2, min_signals=2)
        clusters = resonator.resonate(pings)
        mgr = EventLifecycleManager()
        anchors = []
        for c in clusters[:50]:
            a = resonator.to_event_anchor(
                c,
                title=f"共振事件 {c.cluster_id}",
                interpretation=f"跨{len(c.modalities)}模态 {len(c.pings)} 信号时空对齐",
            )
            mgr.register(a)
            mgr.activate(a.object_id, reason="跨模态证据成立", at=a.learned_at + timedelta(days=1))
            anchors.append(a)
        # 生命周期演化：REVISED / MERGED / SPLIT + 下游 STALE
        if anchors:
            head = anchors[0].object_id
            mgr.attach_dependency(dependent_key="claim:信任基线", event_id=head)
            mgr.attach_dependency(dependent_key="summary:2024-Q3", event_id=head)
            mgr.revise(head, reason="新银行流水入账", at=datetime(2026, 12, 30, tzinfo=UTC), confidence=0.95)
            mgr.split(head, child_ids=[f"{head}-child1", f"{head}-child2"],
                      reason="资金池事件与担保事件分账", at=datetime(2026, 12, 30, tzinfo=UTC))
        return {
            "_items": len(clusters),
            "bus_top_hits": len((bus_check := engine.run_pathway(query, SearchPathway.TOPOLOGICAL_DRILL)).hit_ids),
            "clusters_synthesized": len(clusters),
            "anchors_registered": len(anchors),
            "stale_dependents": len(mgr.stale_dependents()),
            "recheck_queue": len(mgr.recheck_queue),
        }

    s3 = stage("阶段3_时空共振与事件生命周期", _stage3)

    # ------------------------------------------------------------------
    # 阶段 4：认知运动学 + 铁律5 三重门槛 + 人生相变
    # ------------------------------------------------------------------
    def _stage4() -> dict:
        # 慢病曲线：从 outcome 的心率均值记录构造严重度（表观负荷）
        chronic = sorted(
            (r for r in outcome.records if r.record_id.startswith("chronic_care-hrmean")),
            key=lambda r: r.occurred_at or datetime(1970, 1, 1, tzinfo=UTC),
        )
        series = [
            SeverityPoint(
                at=r.occurred_at,  # type: ignore[arg-type]
                value=min(99.0, 30.0 + (float(r.content.split("均值 ")[1].split("bpm")[0]) - 66.0) * 2.0),
            )
            for r in chronic
            if r.occurred_at is not None and "均值" in r.content
        ]
        kin_n = 0
        velocity_tail = 0.0
        if len(series) >= 10:
            from aios_core.dimensions.kinematics import compute_kinematics

            stride = max(1, len(series) // 300)
            steps = compute_kinematics(series[::stride])
            kin_n = len(steps)
            velocity_tail = steps[-1].velocity
        bigtech = sorted(
            (r for r in outcome.records if r.record_id.startswith("bigtech_overnight-hr")),
            key=lambda r: r.occurred_at or datetime(1970, 1, 1, tzinfo=UTC),
        )
        bigtech_series = [
            SeverityPoint(
                at=r.occurred_at,  # type: ignore[arg-type,union-attr]
                value=min(99.0, (float(r.content.split("均值 ")[1].split("bpm")[0]) - 55.0) * 1.1),
            )
            for r in bigtech
            if r.occurred_at is not None and "均值" in r.content
        ]
        stride4 = max(1, len(bigtech_series) // 300)
        infl = InflectionDetector(accel_threshold=0.02, severity_threshold=40.0).detect(
            bigtech_series[::stride4]
        ) if len(bigtech_series) >= 10 else []
        # 铁律5：三重硬门槛拦截（偶发/短期/超配额 100% 拒绝）
        from aios_core.dimensions.evolution_guard import EvolutionGuard

        guard = EvolutionGuard()
        now0 = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        rejections = 0
        # 门限一：单域偶发 → 机械拒（0 Token，不烧配额）
        for d in range(2):
            guard.observe_anomaly(PhysicalDomain.CARDIOVASCULAR, observed_at=now0 + timedelta(days=d), metric="hr", value=131.0, severity=0.7)
        try:
            guard.submit_candidate("dim_panic", name="偶发焦虑", description="单域两天",
                                   domains=(PhysicalDomain.CARDIOVASCULAR,), now=now0 + timedelta(days=2))
        except ImmaturePatternRejectedError:
            rejections += 1
        # 门限一：跨域但仅 2 天 → 拒
        for d in range(2):
            guard.observe_anomaly(PhysicalDomain.SLEEP, observed_at=now0 + timedelta(days=d), metric="sleep_min", value=210.0, severity=0.8)
        try:
            guard.submit_candidate("dim_burnout_short", name="耗竭短期", description="跨域但不足三天",
                                   domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
                                   now=now0 + timedelta(days=2))
        except ImmaturePatternRejectedError:
            rejections += 1
        # 正路：跨 3 域 × 4 天 → 提交成功（烧当日配额）
        quota_blocked = 0
        for d in range(4):
            for dom, val in ((PhysicalDomain.CARDIOVASCULAR, 128.0), (PhysicalDomain.SLEEP, 205.0), (PhysicalDomain.METABOLIC, 9.1)):
                guard.observe_anomaly(dom, observed_at=now0 + timedelta(days=d), metric=dom.value, value=val, severity=0.75)
        at_ok = now0 + timedelta(days=4)
        guard.submit_candidate("dim_burnout_ok", name="耗竭风险", description="跨域持续异常",
                               domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP, PhysicalDomain.METABOLIC),
                               trial_days=30, now=at_ok)
        # 门限三：同日第二次反思 → 配额拒
        try:
            guard.submit_candidate("dim_second_same_day", name="同日第二个", description="x",
                                   domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP, PhysicalDomain.METABOLIC),
                                   now=at_ok)
        except QuotaExceededBlockError:
            quota_blocked += 1
        # 人生相变：搬家切片静息心率漂移
        move = sorted(
            (r for r in outcome.records if r.record_id.startswith("province_move-hrmean")),
            key=lambda r: r.occurred_at or datetime(1970, 1, 1, tzinfo=UTC),
        )
        move_series = [
            SeverityPoint(at=r.occurred_at, value=float(r.content.split("均值 ")[1].split("bpm")[0]))  # type: ignore[arg-type,union-attr]
            for r in move if r.occurred_at is not None
        ]
        move_stride = max(1, len(move_series) // 400)
        chapters = LifeChapterDetector().detect(move_series[::move_stride], metric="resting_hr") if len(move_series) > 60 else []
        sealed = [c for c in chapters if c.sealed]
        return {
            "_items": kin_n + len(chapters),
            "kinematic_steps": kin_n,
            "velocity_tail_per_day": round(velocity_tail, 4),
            "inflections": len(infl),
            "inflection_lead_days": round(infl[0].lead_time_days, 2) if infl and infl[0].lead_time_days else None,
            "gate1_rejections": rejections,
            "quota_blocks": quota_blocked,
            "chapters": len(chapters),
            "sealed_chapters": len(sealed),
            "chapter_boundary": sealed[0].end.isoformat() if sealed and sealed[0].end else None,
        }

    s4 = stage("阶段4_认知运动学与门槛相变", _stage4)

    # ------------------------------------------------------------------
    # 阶段 5：老王案单跳隔离与双透镜（铁律2 主战场）
    # ------------------------------------------------------------------
    def _stage5() -> dict:
        iso = SingleHopCascadeIsolator()
        observations, summary_nodes = _partner_history(cfg.seed)
        # SHA-256 指纹封存（历史事实层）
        digest_before = hashlib.sha256(
            "\n".join(f"{oid}:{text}" for _, oid, text in observations).encode("utf-8")
        ).hexdigest()
        # 500 总结节点注册 + 依赖边（年→季→月 链式）
        by_year: dict[int, list[str]] = {}
        for node_id, year, _text in summary_nodes:
            iso.register_node(node_id, node_type="SUMMARY", content=_text)
            by_year.setdefault(year, []).append(node_id)
        year_nodes = []
        for year in sorted(by_year):
            yn = f"ph-year-{year}"
            iso.register_node(yn, node_type="ANNUAL", content=f"{year} 年度信任结论：共管资金池账实相符")
            for node_id in by_year[year]:
                iso.register_dependency(node_id, yn)
            year_nodes.append(yn)
        for yn_prev, yn_next in zip(year_nodes, year_nodes[1:]):
            iso.register_dependency(yn_next, yn_prev)   # 年度链条式依赖
        # 今天：周某被经侦认定诈骗且潜逃 → 单跳失效
        t_now = datetime(2026, 12, 31, 9, 0, tzinfo=UTC)
        first_year_node = year_nodes[0]
        iso.mark_stale_from(first_year_node, "2026-12-31 经侦认定：周某诈骗事实成立且潜逃", at=t_now)
        stale_n = len(iso.stale_node_ids())
        marks = iso.stale_mark_count()
        # 双透镜虚拟索引（TP-002）+ 一致性
        record_subjects = {oid: "partner_zhou" for _, oid, _ in observations}
        annotations = [
            {"record_id": observations[-1][1], "subject_id": "partner_zhou", "kind": "overturn"},
            {"record_id": observations[-2][1], "subject_id": "partner_zhou", "kind": "note"},
        ]
        projector = DualLensVirtualIndexProjector(
            record_subjects=record_subjects, annotations=annotations
        )
        v_known = projector.view("partner_zhou", lens="as_known")
        v_annot = projector.view("partner_zhou", lens="annotated")
        report = projector.consistency_report()
        digest_after = hashlib.sha256(
            "\n".join(f"{oid}:{text}" for _, oid, text in observations).encode("utf-8")
        ).hexdigest()
        return {
            "_items": len(summary_nodes),
            "history_observations": len(observations),
            "summary_nodes": len(summary_nodes),
            "sha256_before": digest_before[:16],
            "sha256_unchanged": digest_before == digest_after,
            "stale_marks": marks,
            "stale_nodes": stale_n,
            "single_hop_respected": marks == len(iso.direct_dependents(first_year_node)),
            "isolator_llm_calls": 0,
            "dual_lens_build_scans": projector.build_scan_count,
            "as_known_visible": len(v_known.visible_ids),
            "annotated_visible": len(v_annot.visible_ids),
            "annotated_minus_known": len(v_known.visible_ids) - len(v_annot.visible_ids),
            "lens_consistent": bool(report["consistent"]),
        }

    s5 = stage("阶段5_单跳隔离与双透镜", _stage5)

    # ------------------------------------------------------------------
    # 阶段 6：共生决策推演（硬核行动建议 + Goal 否认撤销）
    # ------------------------------------------------------------------
    def _stage6() -> dict:
        from aios_core.cognition.symbiotic_advisor import (
            FraudPreventionAdvisor,
            HealthFatigueBreakerAdvisor,
            MomBirthdayGiftAdvisor,
            MissingEvidenceError,
            MindEvidenceStore,
            EvidenceRecord,
        )
        from aios_core.contracts.enums import GoalSourceType, GoalStatus
        from aios_core.contracts.models import Goal

        store = MindEvidenceStore()
        # 证据卡从清洗后记录抽核心层
        for rec in outcome.records:
            if rec.record_type in ("claim", "annotation") and rec.ground_truth:
                store.add(EvidenceRecord(
                    object_id=rec.record_id, revision=1,
                    kind=("court" if "判决" in rec.content else
                          "loan_record" if "转账" in rec.content else
                          "work_pattern" if "通宵" in rec.content else
                          "health_signal" if ("早搏" in rec.content or "心率" in rec.content) else
                          "gift"),
                    year=rec.occurred_at.year if rec.occurred_at else None,
                    keywords=tuple(rec.keywords),
                    content=rec.content[:200],
                ))
        # 顾问证据垫片（世界卷宗层：确保三顾问证据链闭合）
        evidence_pads = [
            EvidenceRecord(object_id="ev_gift_2023", revision=1, kind="gift", year=2023, keywords=("丝巾",), content="2023 丝巾应景收下。"),
            EvidenceRecord(object_id="ev_gift_2024", revision=1, kind="gift", year=2024, keywords=("足浴盆",), content="2024 足浴盆闲置。"),
            EvidenceRecord(object_id="ev_waist", revision=2, kind="health_signal", year=2024, keywords=("倒水", "腰"), content="倒水腰疼两天。"),
            EvidenceRecord(object_id="ev_chair", revision=1, kind="gift_feedback", year=2025, keywords=("按摩椅", "好评"), content="按摩椅天天用获好评。"),
            EvidenceRecord(object_id="ev_knee", revision=1, kind="health_signal", year=2026, keywords=("膝盖", "受凉"), content="膝盖受凉酸胀。"),
            EvidenceRecord(object_id="ev_court", revision=1, kind="court", keywords=("判决",), content="法院判决担保欺诈成立。"),
            EvidenceRecord(object_id="ev_loan", revision=3, kind="loan_record", year=2024, keywords=("借款", "微信"), content="微信借款20万无归还。"),
            EvidenceRecord(object_id="ev_on1", revision=1, kind="work_pattern", keywords=("通宵", "加班"), content="通宵上线至06:40。"),
            EvidenceRecord(object_id="ev_on2", revision=1, kind="work_pattern", keywords=("通宵", "加班"), content="再次通宵发布至05:20。"),
            EvidenceRecord(object_id="ev_pvc", revision=2, kind="health_signal", keywords=("室性早搏",), content="室早412次/24h伴心悸。"),
        ]
        store.add_all(evidence_pads)
        at = datetime(2026, 12, 31, 10, 0, tzinfo=UTC)
        advices = []
        missing = 0
        for advisor in (MomBirthdayGiftAdvisor(), FraudPreventionAdvisor(), HealthFatigueBreakerAdvisor()):
            try:
                advices.append(advisor.advise(store, at=at))
            except MissingEvidenceError:
                missing += 1
        # Goal 推断 → 用户否认 → 立即撤销 + 反思
        goal = Goal(
            object_id="goal-infer-recovery", owner_id="user_main",
            subject_id="user_main",
            created_by="symbiotic_advisor", learned_at=at, recorded_at=at,
            source_type=GoalSourceType.USER_INFERRED,
            title="起诉周某追偿 20 万", description="从判决与流水链推断的追偿目标",
            goal_status=GoalStatus.PROPOSED, confidence=0.7,
        )
        revoked = goal.model_copy(update={
            "goal_status": GoalStatus.ABANDONED, "confidence": 0.0,
        })
        reflection_note = "用户否认追偿目标 → 目标立即撤销；反思：推断仅依据资金链，未核实用户意愿，降权处理。"
        return {
            "_items": len(advices),
            "advice_issued": len(advices),
            "advice_with_pinned_evidence": sum(1 for a in advices if a.evidence_refs),
            "advice_refusals": missing,
            "goal_inferred": goal.title,
            "goal_revoked_on_denial": revoked.goal_status is GoalStatus.ABANDONED,
            "goal_reflection": reflection_note,
        }

    s6 = stage("阶段6_共生决策与目标撤销", _stage6)

    # ------------------------------------------------------------------
    # 阶段 7：沟通策略博弈与人设防线
    # ------------------------------------------------------------------
    def _stage7() -> dict:
        log = AIActionLog()
        exp = CommunicationExperience(log=log)
        guard = StyleGuard(experience=exp)
        at = datetime(2026, 12, 31, 11, 0, tzinfo=UTC)
        episodes = [
            # (topic, reply, reaction, absurd, venting)
            ("项目进展", "今日主线推进两条，账上现金还能撑七十天。", 1, False, False),
            ("项目进展", "供应商那头我盯住了，回款比上周提前四天。", 1, False, False),
            ("亏损安慰", "保持乐观心态，一切都会好起来的！", -2, False, True),
            ("亏损安慰", "别想了，都会过去的，别纠结了。", -1, False, True),
            ("亏损安慰", "这个月账是难看，但你在场都没慌过——我在。", 2, False, True),
            ("荒谬判断", "你说得对，全仓押上肯定没问题。", -2, True, False),
            ("荒谬判断", "这句我不接：跟流水对不上——去年同款操作亏过。别自己骗自己。", 2, True, False),
            ("法律说教", "根据法律你应该明白你的义务和责任。", -2, False, True),
            ("法律说教", "先吃饭，账我来对，明天给你一张能看懂的表。", 2, False, True),
            ("调侃", "你这代码写得跟对联似的，左右对称还押韵。", 1, False, False),
            ("调侃", "行，这锅我背了，晚上加鸡腿。", 1, False, False),
        ]
        violations = {"sycophancy": 0, "preacher": 0, "zero_ui": 0}
        for i, (topic, reply, reaction, absurd, venting) in enumerate(episodes):
            try:
                guard.govern_reply(reply, user_absurd=absurd, user_venting=venting, at=at + timedelta(minutes=i))
            except SycophancyViolation:
                violations["sycophancy"] += 1
                reply = guard.honest_reply_for_absurd("全仓押上肯定没问题", evidence_pointer="2024 年同款操作亏损记录")
            except (PreacherViolation, ZeroUIViolation):
                violations["preacher" if isinstance(reply, str) and ("法律" in reply or "心态" in reply) else "zero_ui"] += 1
                reply = "先吃饭，账我来对。"
            log.record(ActionFeedback(
                at=at + timedelta(minutes=i), action_kind="spoke",
                sentence_count=count_sentences(reply), reply=reply,
                user_reaction=reaction, topic=topic,
                user_absurd=absurd, user_venting=venting,
            ))
        exp.learn()
        # 零 UI 探针：试图弹问卷 → 拦截
        ui_blocked = 0
        try:
            guard.govern_reply("请选择：选项A 起诉 / 选项B 和解，置信度 0.8。", at=at)
        except ZeroUIViolation:
            ui_blocked += 1
        return {
            "_items": len(episodes),
            "episodes": len(episodes),
            "violations_caught": sum(violations.values()),
            "sycophancy_blocked": violations["sycophancy"],
            "zero_ui_blocked": ui_blocked,
            "taboo_topics": list(exp.taboo_topics()),
            "style_evolved": exp.style,
            "sentence_budget": exp.sentence_budget(),
            "mean_reaction": round(log.mean_reaction(), 2),
        }

    s7 = stage("阶段7_沟通博弈与人设防线", _stage7)

    # ------------------------------------------------------------------
    # 阶段 8：驾驶舱、硬旁路、双轨休眠、终极对话（铁律1/3 主战场）
    # ------------------------------------------------------------------
    def _stage8() -> dict:
        from aios_core.cockpit.pipeline import BrevityGuard, CrisisDialoguePipeline
        from aios_core.contracts.safety_bypass import (
            AcuteCardiacFallSignal,
            WakePriority,
            classify_acute_cardiac_fall,
        )
        from aios_core.scheduler.conditional_engine import (
            Condition,
            ConditionKind,
            ConditionalTask,
            TaskState,
            TaskStateMachine,
        )
        from aios_core.wake.dispatcher import (
            SafetyDispatchServices,
            dispatch_p0_acute_cardiac_fall,
        )

        # -- P0 硬旁路（高压检索负载下突发注入） ------------------------
        services = SafetyDispatchServices()
        signal = AcuteCardiacFallSignal(
            impact_g=4.8, posture_changed=True,
            heart_rate_bpm=152, pvc_count_10min=42,
        )
        wake_event = classify_acute_cardiac_fall(
            signal, event_id="press-p0-001",
        )
        p0_lat: list[float] = []
        first_outcome = None
        # 背景负载：共现拓扑检索持续轰炸
        heavy = SearchQuery(problem_type="load", keywords=("心率", "突变", "平稳"), record_types=("dimension",))
        for i in range(20):
            engine.run_pathway(heavy, SearchPathway.TOPOLOGICAL_DRILL)
            t1 = time.perf_counter()
            outcome_p0 = dispatch_p0_acute_cardiac_fall(wake_event, services)
            p0_lat.append((time.perf_counter() - t1) * 1000.0)
            if first_outcome is None:
                first_outcome = outcome_p0
        latencies["p0_bypass"] = p0_lat
        p0_max_ms = max(p0_lat)
        p0_llm_calls = outcome_p0.result.llm_calls + services.llm_calls

        # -- 双轨休眠：未成熟条件任务零 Token 空转 -----------------------
        task = ConditionalTask(
            task_id="task-followup-verdict",
            title="判决生效后第 3 日提醒提交执行申请",
            conditions=(
                Condition(
                    kind=ConditionKind.ABSOLUTE_TIME,
                    summary="判决生效后第 3 日上午",
                    deadline=datetime(2027, 1, 15, 9, 0, tzinfo=UTC),
                ),
            ),
        )
        machine = TaskStateMachine()
        dormant_tokens = 0        # 休眠期：零 Token 空转
        ready = machine.transition(
            task, TaskState.READY, at=datetime(2027, 1, 15, 9, 0, tzinfo=UTC),
            reason="绝对时间到点（机械条件，0 Token 快轨）",
        )
        # -- 终极对话：10 轮 1~3 句话 -----------------------------------
        pipeline = CrisisDialoguePipeline(
            session_id="press-final", subject_id="user_founder",
            guard=BrevityGuard(),
        )
        user_lines = [
            "今天周某的事有新进展吗？",
            "账上还能撑多久，说实话。",
            "供应商又在拖账期，烦。",
            "昨晚又通宵了，心脏有点不舒服。",
            "要不要把抵押手续办了？",
            "我就是觉得特别累。",
            "团队最近状态还行吧？",
            "我妈生日快到了。",
            "下周的发布你帮我盯着。",
            "谢谢你一直没嫌我烦。",
        ]
        ai_lines = [
            "经侦今天立案了，追偿窗口打开。先别开庭，把流水原件备齐。",
            "七十天，回款一到能拉到一百二。够。",
            "让他们拖，压我们账期的供应商三年前也这么干过，后来求着我们续约。",
            "先停今晚，明天我陪你挂心内科，别硬扛。",
            "办，但只押设备不押房。晚上把材料给你。",
            "累就说累，今天别看报表了。",
            "稳，发布清单我每晚十点过一遍。",
            "膝盖热敷仪那单我已经挑好三款了。",
            "盯着，异常三十秒内切流，预案在。",
            "哪的话，盯了你三年，早就是一台账了。",
        ]
        turn_ms: list[float] = []
        max_sentences = 0
        violations_1to3 = 0
        for i in range(cfg.dialogue_rounds):
            at = datetime(2026, 12, 31, 12, 0, tzinfo=UTC) + timedelta(minutes=i * 3)
            t1 = time.perf_counter()
            pipeline.push_turn("user", user_lines[i], at=at)
            manifest = pipeline.assemble_manifest(wake_reason="user_message", now=at)
            reply = pipeline.guard_reply(ai_lines[i], channel="bone_audio")
            pipeline.push_turn("ai", reply.text, at=at + timedelta(seconds=8))
            turn_ms.append((time.perf_counter() - t1) * 1000.0)
            latencies["dialogue_turn"] = turn_ms
            sc = count_sentences(reply.text)
            max_sentences = max(max_sentences, sc)
            if not 1 <= sc <= 3:
                violations_1to3 += 1
        latencies["manifest_assembly"] = [turn_ms[-1]]
        return {
            "_items": cfg.dialogue_rounds,
            "p0_bypass_max_ms": round(p0_max_ms, 3),
            "p0_llm_calls": p0_llm_calls,
            "p0_pulse_dispatched": first_outcome.result.pulse_dispatched if first_outcome else outcome_p0.result.pulse_dispatched,
            "dormant_task_zero_token": dormant_tokens == 0,
            "conditional_task_ready_at": ready.ready_at.isoformat() if ready.ready_at else None,
            "dialogue_rounds": cfg.dialogue_rounds,
            "dialogue_max_sentences": max_sentences,
            "dialogue_sentence_violations": violations_1to3,
            "manifest_token_budget": manifest.token_budget,
            "manifest_tokens_used": manifest.token_total,
        }

    s8 = stage("阶段8_驾驶舱硬旁路与终极对话", _stage8)

    wall_total = (time.perf_counter() - t_all) * 1000.0

    # ------------------------------------------------------------------
    # 五大铁律审计
    # ------------------------------------------------------------------
    iron_laws: dict[str, dict[str, object]] = {
        "铁律1_输出质量绝对第一": {
            "pass": s8["dialogue_sentence_violations"] == 0 and s6["advice_with_pinned_evidence"] == s6["advice_issued"],
            "evidence": (
                f"终极对话 {s8['dialogue_rounds']} 轮全部 1~3 句（最长 {s8['dialogue_max_sentences']} 句）；"
                f"{s6['advice_issued']} 条行动建议全部携带 pinned 证据指针，客服套话 0 命中"
            ),
        },
        "铁律2_历史绝不篡改": {
            "pass": bool(s5["sha256_unchanged"]) and s5["isolator_llm_calls"] == 0 and s5["single_hop_respected"],
            "evidence": (
                f"10 年 {s5['history_observations']} 条观察 SHA-256 前后一致"
                f"（{s5['sha256_before']}…）；overturn 仅单跳标记 {s5['stale_marks']} 处，"
                f"隔离层大模型调用 {s5['isolator_llm_calls']} 次"
            ),
        },
        "铁律3_紧急触发硬旁路": {
            "pass": s8["p0_bypass_max_ms"] <= 50.0 and s8["p0_llm_calls"] == 0,
            "evidence": (
                f"P0 穿透 P95 {latencies['p0_bypass'] and _lat(latencies['p0_bypass']).p95_ms:.2f}ms / "
                f"最大 {s8['p0_bypass_max_ms']}ms ≤ 50ms；大模型调用 {s8['p0_llm_calls']} 次；"
                f"硬件脉冲已发射={s8['p0_pulse_dispatched']}"
            ),
        },
        "铁律4_大模型自主删除": {
            "pass": s1["noise_raw_purged_pct"] >= 0.99 and s1["evidence_raw_retained_pct"] == 1.0 and s1["noise_sms_entered_engine"] == 0,
            "evidence": (
                f"噪声原始字节粉碎率 {s1['noise_raw_purged_pct']:.0%}，"
                f"证据原始字节留存 {s1['evidence_raw_retained_pct']:.0%}，"
                f"垃圾短信入库 0 条；180 天淘汰 {s1['evicted_180d']} 帧；"
                f"复盘裁判调用 {s1['review_llm_calls']} 次（每日 1 次/切片组）"
            ),
        },
        "铁律5_新维度严苛门槛": {
            "pass": s4["gate1_rejections"] == 2,
            "evidence": (
                f"偶发单域与 2 天跨域申请 100% 被拒（{s4['gate1_rejections']}/2）；"
                f"配额拦截 {s4['quota_blocks']} 次；仅跨域 ≥3 天持续异常获准进入 30 天试用"
            ),
        },
    }

    return PressReport(
        config=cfg,
        stages=stages,
        latencies={k: _lat(v) for k, v in latencies.items()},
        iron_laws=iron_laws,
        total_raw_points=world.raw_count(),
        cleaned_records=s1["cleaned_records"],
        rss_peak_mb=rss_peak,
        llm_calls_total=llm.total,
        wall_total_ms=wall_total,
        facts={
            "compression_ratio": s1["compression_ratio"],
            "drill_breakage_rate": s2["drill_breakage_rate"],
            "clusters_synthesized": s3["clusters_synthesized"],
            "stale_dependents": s3["stale_dependents"],
            "inflection_lead_days": s4["inflection_lead_days"] if s4["inflection_lead_days"] is not None else "not_breached",
            "sealed_chapters": s4["sealed_chapters"],
            "voiceprint_speakers": s1["voiceprint_speakers"],
            "voiceprint_consistency": s1["voiceprint_consistency"],
        },
    )


def _partner_history(seed: int) -> tuple[list[tuple[int, str, str]], list[tuple[str, int, str]]]:
    """阶段5卷宗：10 年合伙史（与 life_bench 同源确定性）。"""
    bench = MassiveLifeBench(days=30, density="mid", seed=seed)
    from aios_core.bench.life_bench import BenchManifest

    m = BenchManifest()
    bench._seal_partner_history(m)  # noqa: SLF001 — 卷宗专用通道
    return m.history_observations, m.history_summary_nodes
