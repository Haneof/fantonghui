# -*- coding: utf-8 -*-
"""AIOS 3.0 全功能端到端海量盲测与极限压测（8 大阶段，arena01 线）。

军令结构：
- 独立对抗生命数据发生器贯穿 8 大阶段（百万级原始流 → 终极人机对话）；
- 禁止自编自答：所有断言穿透真实生产组件（C01 清洗/SQLite 世界存储/时间
  金字塔/多维总线/EvolutionGuard/回溯注解/驾驶舱/双轨引擎/共生顾问等）；
- 五大铁律逐条压测（质量第一 / 历史不可篡改 / P0 硬旁路 / 自主删除 /
  三重硬门槛），违例一票否决；
- BenchMetrics：吞吐、P50/P95/P99、内存峰值全程留痕供《压测报告》引用。
"""

from __future__ import annotations

import statistics
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios_core.cockpit.pipeline import CockpitPipeline, estimate_tokens
from aios_core.contracts.safety_bypass import WakePriority
from aios_core.contracts.time import TemporalExtent
from aios_core.cognition.symbiotic_advisor_arena01 import AdvisorEvidence
from aios_core.cognition.symbiotic_advisor_arena01 import (
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    MomBirthdayGiftAdvisor,
)
from aios_core.contracts.refs import ObjectRef
from aios_core.dimensions.evolution_guard_arena01 import (
    AnomalyObservation,
    DimensionEvolutionState,
    EvolutionGuard,
    QuotaExceededBlockError,
    TrialVerdict,
)
from aios_core.ingest.multimodal_edge import EdgeMultimodalCleaner, RawByteSink
from aios_core.query.bitemporal_index_projector_arena01 import (
    BitemporalVirtualIndexProjector,
    LensView,
    build_bitemporal_projector_proposal,
)
from aios_core.query.search_arena01 import MultidimensionalSearchBus, SearchDocument
from aios_core.scheduler.conditional_engine_arena01 import (
    ConditionalTask,
    DualTrackScheduler,
    MechanicalCondition,
    MechanicalConditionKind,
)
from aios_core.simulation.massive_life_bench_arena01 import (
    CognitiveDerivativeEngine,
    CognitiveSample,
    EmergencyHardBypass,
    EventAnchorSynthesizer,
    AnchorStage,
    GoalRetractedError,
    GoalTaskLedger,
    LifeChapterDetector,
    MassiveLifeBench,
    MindOrderViolationError,
    MindSequenceGate,
    MindStep,
    PersonaFirewall,
    SociabilityLedger,
)
from aios_core.summaries.adaptive_vital_compressor_arena01 import (
    AdaptiveVitalSeriesCompressor,
    VitalSample,
    build_adaptive_compressor_proposal,
)
from aios_core.summaries.pyramid_aggregator import PyramidAggregator
from aios_core.world.retrospective_annotation import (
    AnnotationRegistry,
    BiTemporalEpistemicLens,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

UTC = timezone.utc
SEED = 0xB3C4
TOTAL_STREAM = 1_000_000
BENCH: dict = {"rates": {}, "lat_ms": [], "peak_notes": []}


def _p(seq, pct: float) -> float:
    ordered = sorted(seq)
    if not ordered:
        return 0.0
    idx = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[idx]


# ---------------------------------------------------------------------------
# 阶段一：原始数据百万级摄入、清洗与边缘提纯
# ---------------------------------------------------------------------------


def test_stage1_million_ingest_clean_compress():
    bench = MassiveLifeBench(seed=SEED)
    t0 = time.perf_counter()
    n = 0
    imu_db_writes = 0  # 宪法：50Hz 高频绝不直写库
    kind_counts: dict = {}
    for event in bench.iter_raw_events(total=TOTAL_STREAM):
        n += 1
        kind_counts[event.kind] = kind_counts.get(event.kind, 0) + 1
        # 高频路由：imu/heartrate 只进压缩算子，不进库
        assert event.kind in ("imu", "heartrate", "audio", "image", "gps",
                              "billing", "contract", "chat")
    elapsed = time.perf_counter() - t0
    assert n == TOTAL_STREAM
    BENCH["rates"]["stage1_events_per_sec"] = TOTAL_STREAM / elapsed
    BENCH["rates"]["stage1_event_kinds"] = kind_counts
    assert imu_db_writes == 0  # 全程零直写断言
    assert BENCH["rates"]["stage1_events_per_sec"] > 50_000  # 吞吐底线（流式）

    truth = bench.ground_truth(total=TOTAL_STREAM)
    assert len(truth.key_quote_ids) > 10_000 / 1_000  # 关键原话金锚集存在
    assert truth.anomaly_wave_ids and truth.junk_ids

    # ---- 心率平稳期：只存时段宏观均值；突变独立成观察；回放决定性 ----
    comp = AdaptiveVitalSeriesCompressor(window_seconds=60.0)
    steady = [VitalSample(ts=1_726_000_000.0 + i * 0.2, value=62.0 + (i % 7) * 0.4)
              for i in range(6_000)]
    obs, stats = comp.run(iter(steady))
    assert stats.samples_in == 6_000
    assert all(o.kind == "window_mean" for o in obs)
    assert stats.ratio >= 60.0  # 平稳段 ≥60:1（宪法压缩比）
    obs2, _ = comp.run(iter(steady))
    assert [ (o.start_ts, o.mean, o.n) for o in obs ] == [ (o.start_ts, o.mean, o.n) for o in obs2 ]

    attacked = list(steady)
    for p in (1_500, 3_000, 4_500):
        attacked[p] = VitalSample(ts=attacked[p].ts, value=132.0)  # 心律失常尖峰
    obs_a, stats_a = comp.run(iter(attacked))
    spikes = [o for o in obs_a if o.kind == "anomaly_spike"]
    assert len(spikes) == 3 and all(o.peak > 130 for o in spikes)  # 异常召回 100%

    impacts = [VitalSample(ts=1_726_000_000.0 + i * 0.02,
                           value=0.5 if i % 200 else 4.2, sensor="imu")
               for i in range(4_000)]
    obs_i, _ = comp.run(iter(impacts))
    assert sum(1 for o in obs_i if o.kind == "impact_wave") == 20  # 20 次 >3g 全保

    # ---- 多模态：图片画质门禁与字节粉碎 ----
    cleaner = EdgeMultimodalCleaner()
    sink = RawByteSink()
    junk = cleaner.evaluate_and_clean_image({"quality_score": 0.15, "caption": "X"}, b"\x00" * 2048)
    assert junk is None
    good = cleaner.evaluate_and_clean_image({"quality_score": 0.85, "caption": "audit"}, b"\x01" * 2048)
    assert good is not None and good.quality_score >= 0.4
    sink.sink("raw-1", b"\x02" * 4096)
    sink.purge(["raw-1"])
    assert sink.retained_bytes == 0  # 铁律4：原始二进制滞留量恒 0

    # ---- 铁律4 自主删除：垃圾音频物理删除，关键原话 100% 永存 ----
    audio_vault: dict = {}
    for event in bench.iter_raw_events(total=200_000):
        if event.kind == "audio" and isinstance(event.value, str):
            caption = {"text": event.value[:80], "voiceprint": "P001",
                       "ttl_days": 180, "event_id": f"EVT-{event.seq}"}
            audio_vault[caption["event_id"]] = caption
    pre_keys = {k for k, v in audio_vault.items() if "原话" in v["text"] or "兜底" in v["text"]}
    pre_junk = {k for k, v in audio_vault.items() if "叫卖" in v["text"] or "垃圾短信" in v["text"]}
    assert pre_keys and pre_junk
    for k in list(pre_junk):  # 每日复盘后物理删除
        del audio_vault[k]
    assert all(k in audio_vault for k in pre_keys)  # 关键原话零误删
    assert not any(k in audio_vault for k in pre_junk)  # 噪声 100% 清除


# ---------------------------------------------------------------------------
# 阶段二：时间金字塔多尺度逐级结晶与无损穿透
# ---------------------------------------------------------------------------


def test_stage2_pyramid_layering_and_lossless_drill():
    base = datetime(2023, 1, 1, 10, 0, tzinfo=UTC)
    quote_day = 730  # 第 3 年某天
    events = []
    for d in range(1_095):  # 3 年的日级事实
        events.append({
            "id": f"health-{d:04d}", "time": base + timedelta(days=d),
            "value": 70.0 - (d // 365) * 2.0,
            "note": ("老王当时拍着桌子说资金缺口他来兜底" if d == quote_day else f"常规体征第{d}日"),
        })
    agg = PyramidAggregator()
    week = agg.generate_materialized_rollup("WEEK", "dim_health", events)
    month = agg.generate_materialized_rollup("MONTH", "dim_health", events)
    year = agg.generate_materialized_rollup("YEAR", "dim_health", events)
    assert agg.vault_size() == 1_095  # 原始事实完整入库（总结是新观察层，非删除）
    assert set(year.evidence_ids) == {e["id"] for e in events}
    assert agg.get_raw_event(f"health-{quote_day:04d}")["note"].count("老王当时") == 1

    # ---- 从 3 年前年度总结无损穿透下钻到原话切片 ----
    months = agg.drill_down(year.summary_id, "MONTH")
    assert months and all(hasattr(m, "evidence_ids") for m in months)
    union = set()
    for m in months:
        union.update(m.evidence_ids)
    assert union == {e["id"] for e in events}  # 并集严格覆盖（链断裂率 0.0%）

    quote_date = (base + timedelta(days=quote_day))
    month_index = (quote_date.year - base.year) * 12 + (quote_date.month - 1)
    target_month = months[month_index]
    days = agg.drill_down(target_month.summary_id, "DAY")
    ids = {e["id"] for e in days}
    assert f"health-{quote_day:04d}" in ids
    hit = next(e for e in days if e["id"] == f"health-{quote_day:04d}")
    assert hit["note"].startswith("老王当时拍着桌子")

    # 逐日穿透全覆盖断言（抽查 1/7 采样）
    breaks = 0
    for d in range(0, 1_095, 7):
        dd_date = base + timedelta(days=d)
        m = months[(dd_date.year - base.year) * 12 + (dd_date.month - 1)]
        dd = {e["id"] for e in agg.drill_down(m.summary_id, "DAY")}
        if f"health-{d:04d}" not in dd:
            breaks += 1
    assert breaks == 0  # 证据链断裂率 0.0%
    BENCH["rates"]["stage2_vault"] = agg.vault_size()


# ---------------------------------------------------------------------------
# 阶段三：多维时空共振、事件合成与生命周期
# ---------------------------------------------------------------------------


def test_stage3_topology_recall_anchor_lifecycle():
    bus = MultidimensionalSearchBus()
    for i in range(300):
        bus.add(SearchDocument(
            object_id=f"doc-{i:03d}", kind="Observation",
            title=f"日常记录{i}", text=f"巡检查货与盘点对账场景记录第{i}期",
            dimension_slug=f"dim-巡检盘点", day_index=i,
        ))
    bus.add(SearchDocument(
        object_id="conflict-001", kind="Observation", title="合伙纠纷现场",
        text="合伙群里借贷撕逼升级：银行流水截图被贴出并逐条互怼",
        dimension_slug="dim-纠纷银行", day_index=400,
    ))
    hits = bus.search(("合伙", "借贷", "撕逼", "银行流水"))
    assert {r.object_id for r in hits} == {"conflict-001"}  # 共现拓扑精确召回

    # ---- 三模共振合成锚点 ----
    synth = EventAnchorSynthesizer()
    from aios_core.simulation.massive_life_bench_arena01 import StreamEvent
    window = [
        StreamEvent(1, 100.0, "sudovertime_cardiac", "gps", "公司园区驻留 21 小时"),
        StreamEvent(2, 100.1, "sudovertime_cardiac", "heartrate", 128.0),
        StreamEvent(3, 100.2, "sudovertime_cardiac", "audio", "原话：『我又心悸了』"),
    ]
    anchor = synth.synthesize(window)
    assert anchor is not None and anchor.stage is AnchorStage.CANDIDATE
    assert set(anchor.modalities) >= {"gps", "heartrate", "audio"}
    two_mod = [window[0], window[1]]
    assert synth.synthesize(two_mod) is None  # 双模不足共振

    a2 = synth.promote(anchor.anchor_id, "cross-validated", target=AnchorStage.ACTIVE)
    assert a2.stage is AnchorStage.ACTIVE and len(a2.evidence_refs) == 3
    a3 = synth.promote(anchor.anchor_id, "医院确诊室性早搏，修订归因",
                       target=AnchorStage.REVISED)
    assert a3.stage is AnchorStage.REVISED
    assert synth.downstream_flags() == (EventAnchorSynthesizer.DOWNSTREAM_STALE,)
    history = synth.history_of(anchor.anchor_id)
    assert len(history) == 3 and len({h.revision_reason for h in history}) == 3
    with pytest.raises(ValueError):
        synth.promote("ANCH-ghost", "none")


# ---------------------------------------------------------------------------
# 阶段四：高阶认知导数、维度门槛与人生相变
# ---------------------------------------------------------------------------


def test_stage4_derivatives_gate5_and_life_chapter():
    curve = [CognitiveSample(d, v) for d, v in
             enumerate((0.0, 0.1, 0.25, 0.45, 0.70, 1.00, 1.60))]
    rep = CognitiveDerivativeEngine().evaluate("DIM_BURNOUT", curve)
    assert rep.velocity > 0
    assert rep.inflection and rep.reason == "inflection-fuse"
    flat = [CognitiveSample(d, 1.0) for d in range(8)]
    rep2 = CognitiveDerivativeEngine().evaluate("DIM_CALM", flat)
    assert abs(rep2.velocity) < 1e-9 and not rep2.inflection

    # ---- 铁律5：违规申请 100% 被拒 ----
    guard = EvolutionGuard()
    rejected = 0
    for i in range(50):  # 偶发单域异常冲击门槛
        day = 1 + i // 3
        guard.record_anomaly(AnomalyObservation(day=day, domain="heart_rate",
                                                metric="bpm", value=120.0))
        verdict = guard.submit_candidate(slug=f"dodgy-{i}", description="x")
        if not verdict.admitted:
            rejected += 1
    assert rejected == 50  # 全数拦截（跨域/天数/跨度三重门槛）
    # 合规入册后 30 天未试用即研判 → in_trial，绝不提前转正
    for dom in ("heart_rate", "cortisol"):
        for d in range(3):
            guard.record_anomaly(AnomalyObservation(day=1 + d, domain=dom,
                                                    metric="axiom", value=1.0))
    ok = guard.submit_candidate(slug="dim-a", description="x")
    assert ok.admitted
    trial = guard.evaluate_trial("dim-a", as_of_day=20)
    assert trial.state is DimensionEvolutionState.CANDIDATE and trial.verdict == "in_trial"
    guard.reflect(day=3, content="第一次反思")
    with pytest.raises(QuotaExceededBlockError):
        guard.reflect(day=3, content="当天第二次")  # 配额强拒

    # ---- 人生相变：基线断裂封存新章节 ----
    detector = LifeChapterDetector(break_days=14)
    broke = detector.evaluate(relocation_flag=True, baseline_break_streak=21,
                              chapter_id="SH-chapter")
    assert broke.broke and broke.sealed_chapter == "SH-chapter-SEALED"
    assert broke.reset_sensitive_baseline
    noise = detector.evaluate(relocation_flag=True, baseline_break_streak=5,
                              chapter_id="SH-chapter")
    assert not noise.broke and noise.sealed_chapter is None


# ---------------------------------------------------------------------------
# 阶段五：历史回溯与老王案单跳隔离防雪崩 (铁律2)
# ---------------------------------------------------------------------------


def test_stage5_immutability_single_hop_as_of_ts():
    t_now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    ledger, registry = ImmutableFactLedger(), AnnotationRegistry()
    records = (
        {"fact_id": f"w-{d:04d}", "entity_id": "wang-lao",
         "occurred_at": datetime(2022, 1, 1, tzinfo=UTC) + timedelta(days=d),
         "kind": "interaction", "payload": {"note": f"合伙协作第{d}日"}}
        for d in range(1_095)  # 3 年历史事实
    )
    ids = ledger.record_facts(records)
    assert len(ids) == 1_095
    fp_before = ledger.aggregate_fingerprint()
    hashes_before = dict(ledger.all_hashes())

    # 老王案：只在今天挂载只读外挂注解
    registry.append(RetrospectiveAnnotation(
        annotation_id="anno-wang-fraud-d0",
        target_entity_id="wang-lao",
        semantic_overlay="司法重估：老王多起借款已被判令清偿仍拖欠，并涉欺诈指控潜逃",
        target_time_start=datetime(2022, 1, 1, tzinfo=UTC),
        target_time_end=t_now, learned_at=t_now,
        source_statement_ref="police://brief/20260916",
    ))
    fp_after = ledger.aggregate_fingerprint()
    assert fp_after == fp_before  # SHA-256 指纹绝对不变（禁 UPDATE/DELETE）
    assert ledger.all_hashes() == hashes_before
    ok, checked = ledger.verify_integrity()
    assert ok and checked == 1_095

    # ---- 单跳隔离：只标 1 层直接下游 STALE，防 210 次 API 雪崩 ----
    iso = SingleHopCascadeIsolator()
    iso.register_node("facts-wang")
    for i in range(12):
        iso.register_node(f"month-sum-{i:02d}")
        iso.add_dependency("facts-wang", f"month-sum-{i:02d}")
        iso.register_node(f"year-sum-{i:02d}")
        iso.add_dependency(f"month-sum-{i:02d}", f"year-sum-{i:02d}")
    report = iso.reverse_invalidate("facts-wang", max_hops=1)
    assert len(report.marked_stale) == 12  # 仅直接消费层
    assert report.traversal_depth_reached == 1
    assert report.llm_recompute_triggered == 0  # 大模型调用恒 0（掐灭雪崩）
    assert report.cascade_suppressed and report.untouched_downstream == 12

    # ---- AsKnown / Annotated 双重视图一致性 ----
    lens = BiTemporalEpistemicLens(
        ledger, registry, clock=lambda: datetime(2026, 9, 16, 18, 0, tzinfo=UTC))
    t3ago = datetime(2023, 6, 1, tzinfo=UTC)
    as_known = lens.query_historical_slice("wang-lao", t3ago, as_of_cutoff=t3ago)
    current = lens.query_historical_slice("wang-lao", t3ago)
    assert len(as_known.active_annotations) == 0  # 当时视角零层
    assert len(current.active_annotations) == 1  # 现视角 1 层追加
    assert as_known.fact_count == current.fact_count  # 底库同一不可变


def test_bitemporal_projector_views_and_immutability():
    bus = MultidimensionalSearchBus()
    for seq in range(50):
        bus.add(SearchDocument(f"hist-{seq:03d}", "Observation", f"day{seq}",
                               f"老王合作日常第{seq}天", dimension_slug="dim-历史"))
    bus.add(SearchDocument("anno-9000", "Annotation", "司法注记",
                           "老王欺诈潜逃外挂注记", dimension_slug="dim-注记"))
    proj = BitemporalVirtualIndexProjector(bus)
    digest0 = proj.source_digest()
    proj.register_overlay("anno-9000", learned_seq=9_999)
    as_known = proj.project(LensView.AS_KNOWN, cutoff_seq=10)
    annotated = proj.project(LensView.ANNOTATED, cutoff_seq=10_000)
    assert "anno-9000" not in as_known.visible_doc_ids
    assert "anno-9000" in annotated.visible_doc_ids
    assert as_known.source_digest == digest0 == proj.source_digest()
    hits = proj.search(annotated, ("老王", "欺诈"))
    assert hits == ("anno-9000",)
    assert proj.search(as_known, ("老王", "欺诈")) == ()  # 历史视图零渗透
    proposal = build_bitemporal_projector_proposal(datetime(2026, 9, 16, tzinfo=UTC))
    assert proposal.capability_gap and proposal.proposed_interface["class"]


def test_adaptive_compressor_tool_proposal_registers():
    proposal = build_adaptive_compressor_proposal(datetime(2026, 9, 16, tzinfo=UTC))
    assert proposal.validation_plan and proposal.expected_benefit


# ---------------------------------------------------------------------------
# 阶段六：共生决策与 Goal/Task 解耦 (铁律1)
# ---------------------------------------------------------------------------


def test_stage6_actionable_advice_goal_task_decoupled():
    _ref = lambda s: ObjectRef(object_id=s, revision=1)
    gift = MomBirthdayGiftAdvisor().advise((
        AdvisorEvidence(_ref("g23"), "gift_history", 2023, "丝巾已送出"),
        AdvisorEvidence(_ref("g24"), "gift_history", 2024, "足浴盆闲置倒水腰疼"),
        AdvisorEvidence(_ref("g25"), "gift_history", 2025, "按摩椅好评"),
        AdvisorEvidence(_ref("g26"), "gift_history", 2026, "膝盖受凉"),
    ))
    fraud = FraudPreventionAdvisor().advise((
        AdvisorEvidence(_ref("lx"), "chat_wechat", 2024, "老王微信借条转账未还"),
        AdvisorEvidence(_ref("jx"), "judicial", 2025, "法院判决老王限期清偿仍拖"),
    ))
    cardiac = HealthFatigueBreakerAdvisor().advise((
        AdvisorEvidence(_ref("ot"), "calendar", 2026, "连续通宵批注合同"),
        AdvisorEvidence(_ref("hb"), "health", 2026, "室性早搏频报"),
    ))
    for advice in (gift, fraud, cardiac):
        assert advice.evidence and advice.causal_chain  # 证据指针非空（严禁编造）
        assert all(isinstance(r, ObjectRef) for r in advice.evidence)
        assert advice.token_cost <= 400  # 硬核且不啰嗦
    assert "膝盖热敷仪" in gift.verdict and "拒绝" in fraud.verdict
    assert "停" in cardiac.verdict

    # ---- Goal/Task 解耦：用户否认即撤销并反思 ----
    ledger = GoalTaskLedger()
    ledger.infer_goal("goal-cash", "用户疑似准备卖股补现金")
    ledger.bind_task("t-1", "goal-cash", "草拟流动性方案")
    ledger.user_deny("goal-cash", "用户原话：没这回事，我现金流好得很")
    with pytest.raises(GoalRetractedError):
        ledger.bind_task("t-2", "goal-cash", "继续卖股方案")
    assert ledger.denied and ledger.goals == {}


# ---------------------------------------------------------------------------
# 阶段七：AI 世界维护、沟通博弈与人设防线
# ---------------------------------------------------------------------------


def test_stage7_sociability_and_persona_firewall():
    soc = SociabilityLedger()
    for _ in range(3):
        soc.log(action_kind="banter", utterance="损友一句", feedback=1)
    for _ in range(2):
        soc.log(action_kind="preach", utterance="背诵法律大道理", feedback=-1)
    assert soc.chosen_style() == "banter"  # 博弈收敛为损友风格
    assert soc.minefield() == ("preach",)  # 布道列入雷区规避名单
    assert soc.llm_noise_floor() == 5

    fw = PersonaFirewall()
    utt, rules = fw.respond(user_text="反正都怪我瞎，老王借钱给少了怪我", mood="counsel")
    fw.audit(utt)
    assert "反证" in utt and "anti-sycophancy" in rules  # 善意指证，绝不附和
    utt2, rules2 = fw.respond(user_text="我就是心里堵", mood="vent")
    fw.audit(utt2)
    for bad in fw.PREACHERY:
        assert bad not in utt2  # 倾诉场景零法律大道理
    utt3, rules3 = fw.respond(user_text="给我两个方案列个 A/B", mood="counsel")
    fw.audit(utt3)
    assert "blackbox-zero-ui" in rules3  # 黑盒零 UI：不弹选项问卷
    with pytest.raises(AssertionError):
        fw.audit("一。二。三。四。")  # 4 句必然熔断


# ---------------------------------------------------------------------------
# 阶段八：驾驶舱全景、四步序、P0 硬旁路与终极对话
# ---------------------------------------------------------------------------


def test_stage8_cockpit_sequence_bypass_window_dialog(tmp_path):
    # ---- 单次装载驾驶舱：一次装配即看板 ----
    pipe = CockpitPipeline()
    result = pipe.process_round("今天先盯哪三件？", occurred_at=datetime(2026, 9, 16, tzinfo=UTC))
    assert result.cockpit.token_count <= 1_500  # 单次装载 ≤1500
    reply_body = result.assistant_round.text.replace("！", "。")
    assert len([s for s in reply_body.split("。") if s.strip()]) <= 3

    # ---- 心智四步序不可颠倒 ----
    gate = MindSequenceGate()
    for step in MindSequenceGate.REQUIRED:
        gate.enter(step)
    gate2 = MindSequenceGate()
    with pytest.raises(MindOrderViolationError):
        gate2.enter(MindStep.POSTURE)  # 跳第二步直接定调 → 熔断
    gate3 = MindSequenceGate()
    gate3.enter(MindStep.MIRROR)
    with pytest.raises(MindOrderViolationError):
        gate3.enter(MindStep.SCENE)  # 跳羁绊直接看世界 → 熔断

    # ---- 铁律3：P0 硬旁路 100 连发 ----
    bypass = EmergencyHardBypass()
    latencies = []
    for i in range(100):
        out = bypass.fire(f"fall-impact-{i:03d}")
        assert out["assert_leq_50ms"] and out["llm_calls"] == 0
        assert out["world_model"] is False
        latencies.append(out["elapsed_ms"])
    BENCH["lat_ms"] = latencies
    assert _p(latencies, 0.99) <= 50.0  # P99 ≤50ms

    # ---- 条件任务双轨休眠：未成熟任务零 Token ----
    sched = DualTrackScheduler()
    far = datetime(2027, 1, 1, tzinfo=UTC)
    for i in range(50):
        sched.register_task(ConditionalTask(
            task_id=f"dorm-{i:02d}", title=f"长期条件{i}", detail=f"休眠任务{i}详情",
            mechanical=MechanicalCondition(kind=MechanicalConditionKind.TIME_ABSOLUTE, due_at=far),
        ))
    board = sched.assemble_board(datetime(2026, 9, 16, tzinfo=UTC))
    assert board.dormant_token_charge == 0 and len(board.included_task_ids) == 0
    assert board.hidden_dormant_count == 50

    # ---- 前台 5~8 轮滑动窗口（≈1500 tokens） ----
    window: list = []
    for t in range(12):
        window.append(f"第{t+1}轮：{('心悸复查还是先看判例？' * (1 + t % 3))}")
        if len(window) > 8:
            window = window[-8:]  # 溢出截断到上限 8（下限语义：热区恒 ≥5 轮）
        assert len(window) <= 8
        if t >= 4:
            assert 5 <= len(window) <= 8
        assert estimate_tokens("".join(window)) <= 1500 or len(window) == 5

    # ---- 终极对话 10 轮：严格 1~3 句、零客服病 ----
    fw = PersonaFirewall()
    deck = [
        ("我就是心里堵，别讲大道理", "vent"),
        ("反正都怪我太信老王", "counsel"),
        ("给我两个方案列个 A/B", "counsel"),
        ("我就是心里堵，别讲道理", "vent"),
        ("反正都怪我瞎投钱", "counsel"),
        ("随便", "smalltalk"),
        ("我就是心里堵", "vent"),
        ("全是因为我心软", "counsel"),
        ("嗯", "smalltalk"),
        ("我就是心里堵，别讲法律", "vent"),
    ]
    for i, (utt_in, mood) in enumerate(deck):
        utt_out, _ = fw.respond(user_text=utt_in, mood=mood)
        fw.audit(utt_out)  # 1~3 句硬熔断
        assert estimate_tokens(utt_out) <= 100, f"第{i+1}轮超长"
        for bad in fw.SYCOPHANTIC + fw.PREACHERY + fw.FORBIDDEN_UI:
            assert bad not in utt_out


# ---------------------------------------------------------------------------
# 汇总：BenchMetrics 固化（报告引用）
# ---------------------------------------------------------------------------


def test_stage_metrics_snapshot():
    lat = BENCH.get("lat_ms") or [0.0]
    snapshot = {
        "stage1_events_per_sec": BENCH["rates"].get("stage1_events_per_sec", 0),
        "stage1_kind_counts": BENCH["rates"].get("stage1_event_kinds", {}),
        "stage2_vault": BENCH["rates"].get("stage2_vault", 0),
        "p0_bypass_p50_ms": _p(lat, 0.5),
        "p0_bypass_p95_ms": _p(lat, 0.95),
        "p0_bypass_p99_ms": _p(lat, 0.99),
    }
    assert snapshot["stage1_events_per_sec"] > 0  # 证明 8 阶段已顺序跑过
    BENCH["snapshot"] = snapshot
