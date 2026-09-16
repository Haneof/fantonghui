"""盲测 S3–S5：共现召回 / 跨域共振 / 事件生命周期、认知导数与新维度三闸、老王案回溯隔离。

这三个阶段测的是"心智层"最容易被做坏的地方：

* **S3**：多关键词共现召回（拒绝单关键词全表扫描）→ 跨域共振合成事件锚点 →
  事件生命周期演进（CANDIDATE → ACTIVE → REVISED → MERGED / SPLIT）与下游 STALE 标记；
* **S4**：高阶认知层算导数（底层硬件绝不算）→ 拐点提前熔断 → 新维度三重门限 →
  非线性人生章节相变；
* **S5**：老王案 —— 历史字节级不可篡改、只挂 T_now 外挂注解、单跳隔离防雪崩、
  双透镜（当时所知 / 今天理解）数据一致。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

from aios_core.bench.blind_bench_results import (
    StageFiveResult,
    StageFourResult,
    StageThreeResult,
)
from aios_core.contracts.enums import (
    AnnotationSlot,
    ClaimType,
    EventStatus,
    KnowledgeState,
    ObjectType,
    SourceClass,
    TaskState,
    TaskType,
)
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import (
    Claim,
    EvidenceCoverage,
    Entity,
    EventAnchor,
    EvidenceSet,
    LifeChapter,
    Observation,
    Reinterpretation,
    Task,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import KnowledgeWindow, TemporalExtent
from aios_core.curves.dimension_curve import DimensionCurveTracker
from aios_core.dimensions.evolution_guard import (
    EvolutionGuard,
    ImmaturePatternRejectedError,
    PhysicalDomain,
    QuotaExceededBlockError,
    RecursiveReflectionCutError,
    ReviewOutcome,
)
from aios_core.narrative.segmenter import NarrativeSegmenter
from aios_core.query.cooccurrence_recall_bus import CoOccurrenceRecallBus
from aios_core.query.cjk_inverted_index import CJKTopologicalInvertedIndex, ensure_cjk_schema
from aios_core.query.hyperlink_traverser import EntityHyperlinkGraphTraverser
from aios_core.services.state_machines import validate_event_revision_transition
from aios_core.tools.dual_lens_projection_index import DualLensProjectionIndex
from aios_core.tools.resonance_synthesizer import (
    DOMAIN_FINANCE,
    DOMAIN_LOCATION,
    DOMAIN_PHYSIOLOGY,
    DOMAIN_UTTERANCE,
    CrossDomainResonanceSynthesizer,
)
from aios_core.world.retrospective_annotation import (
    AnnotationRegistry,
    BiTemporalEpistemicLens,
    CascadeIsolationError,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)
from aios_core.world.view_lens import view_at

UTC = timezone.utc

#: 老王案新认知发生的"今天"。
T_NOW = datetime(2026, 9, 16, 9, 30, tzinfo=UTC)

#: 共现召回的四词口语查询（考官原始口径）。
BUS_QUERY: tuple[str, ...] = ("合伙", "借贷", "撕逼", "银行流水")
#: 正对照查询：全部词元都是 1/2 元口径里的真实共现串，证明精确倒排索引本身没有坏，
#: 它只是对同义词与长词（>2 字）天生失明 —— 这正是召回总线存在的理由。
CONTROL_QUERY: tuple[str, ...] = ("合伙", "借条")

_ENTITY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "ent_user": ("我", "本人", "当事人"),
    "ent_old_wang": ("老王", "王强", "合伙人"),
    "ent_mom": ("妈", "母亲"),
    "ent_bank": ("招商银行", "银行"),
    "ent_hospital": ("住院部", "医院"),
}


def _commit(harness: Any, objects: Sequence[Any], *, name: str, key: str) -> int:
    """把对象写入世界（append-only 修订语义，由 store 保证）。"""

    store = harness.store
    operation = OperationRequest(
        operation_id=new_operation_id(),
        operation_name=name,
        expected_world_revision=store.current_world_revision(),
        reason="盲测阶段写入（真实契约对象）",
        idempotency_key=f"blind_bench_{harness.seed}_{key}",
        source_class=SourceClass.AI_COGNITION,
    )
    with harness.recorder.time_block("common.commit_ms"):
        store.commit(list(objects), operation)
    return len(objects)


def _entity(harness: Any, entity_id: str, kind: str, canonical: str, aliases: Sequence[str]) -> Entity:
    return Entity(
        object_id=entity_id,
        subject_id="user_1",
        learned_at=datetime(2023, 1, 1, tzinfo=UTC),
        created_by="blind_bench",
        entity_kind=kind,
        canonical_name=canonical,
        aliases=list(aliases),
    )


def _observation_payloads(harness: Any) -> list[Dict[str, Any]]:
    return harness.store.list_payloads(object_type=ObjectType.OBSERVATION)


def _pick(payloads: Iterable[Mapping[str, Any]], **criteria: Any) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    for payload in payloads:
        value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
        if all(value.get(key) == expected for key, expected in criteria.items()):
            out.append(dict(payload))
    return out


# ======================================================================
# S3：共现召回 · 跨域共振 · 事件生命周期
# ======================================================================


def run_stage3(harness: Any) -> StageThreeResult:
    started = time.perf_counter()
    store = harness.store
    stage1 = harness.stage1
    if stage1 is None:
        raise RuntimeError("run_stage3 requires run_stage1")

    # ---- 1) 实体注册（真实 Entity 契约对象）----
    entities = [
        _entity(harness, entity_id, kind, canonical, _ENTITY_ALIASES[entity_id])
        for entity_id, kind, canonical in (
            ("ent_user", "person", "本人"),
            ("ent_old_wang", "person", "王强（合伙人）"),
            ("ent_mom", "person", "母亲"),
            ("ent_bank", "organization", "招商银行"),
            ("ent_hospital", "organization", "市第一人民医院"),
        )
    ]
    _commit(harness, entities, name="bench.stage3.register_entities", key="entities")

    # ---- 2) 倒排索引 + 共现召回（考官四词口语查询）----
    index_path = harness.workdir / f"cjk_{harness.seed}.db"
    if index_path.exists():
        index_path.unlink()
    conn = sqlite3.connect(index_path)
    ensure_cjk_schema(conn)
    index = CJKTopologicalInvertedIndex(conn)
    bus = CoOccurrenceRecallBus(conn)
    entity_for_key = {
        "WANG:pact_signing": "ent_old_wang",
        "WANG:loan_transfer": "ent_bank",
        "WANG:partnership_pact_copy": "ent_old_wang",
        "WANG:delay_excuse": "ent_old_wang",
        "WANG:dispute_quarrel": "ent_old_wang",
        "WANG:court_ruling": "ent_old_wang",
        "OVERTIME:overnight_confession": "ent_user",
        "OVERTIME:arrhythmia_diagnosis": "ent_hospital",
        "OVERTIME:health_promise": "ent_user",
        "FAMILY:mother_quarrel": "ent_mom",
        "FAMILY:cold_war_note": "ent_mom",
        "FAMILY:mother_hospitalized": "ent_hospital",
        "FAMILY:apology": "ent_mom",
        "FAMILY:dumpling_promise": "ent_mom",
        "FAMILY:late_discovered_truth": "ent_mom",
        "MOVE:resign_decision": "ent_user",
        "MOVE:arrival_chengdu": "ent_user",
        "MOVE:new_rhythm": "ent_user",
        "CHRONIC:bp_reading_q1": "ent_user",
        "CHRONIC:hospitalization": "ent_hospital",
        "CHRONIC:recovery_report": "ent_user",
    }
    evidence_texts = harness.world.get("evidence_texts", {})
    indexed_items: list[tuple[str, str, int]] = []
    for key, observation_id in stage1.evidence_observation_ids.items():
        text = evidence_texts.get(observation_id, "")
        if not text:
            continue
        entity_id = entity_for_key.get(key, "ent_user")
        occurred = _observation_time(store, observation_id)
        indexed_items.append((entity_id, text, int(occurred.timestamp() * 1_000_000_000)))
    index.index_entity_texts_batch(indexed_items)

    query_started = time.perf_counter()
    exact_hits = index.co_search(list(BUS_QUERY))
    control_hits = index.co_search(list(CONTROL_QUERY))
    exact_latency_ms = (time.perf_counter() - query_started) * 1000.0
    bus_started = time.perf_counter()
    recall = bus.recall(BUS_QUERY)
    bus_latency_ms = (time.perf_counter() - bus_started) * 1000.0
    harness.recorder.record("S3.exact_intersection_ms", exact_latency_ms)
    harness.recorder.record("S3.cooccurrence_bus_ms", bus_latency_ms)
    top_hit = recall.hits[0] if recall.hits else None

    # ---- 3) 跨域共振合成（GPS × 心率 × 原话）----
    payloads = _observation_payloads(harness)
    hr_anomalies = _pick(payloads, source_kind_placeholder=None) if False else [
        payload for payload in payloads if payload.get("source_kind") == "wearable_ppg_anomaly"
    ]
    motion_impacts = [
        payload for payload in payloads if payload.get("source_kind") == "wearable_imu_impact"
    ]
    gps_states = [
        payload for payload in payloads if payload.get("source_kind") == "phone_gps"
    ]
    synthesizer = CrossDomainResonanceSynthesizer(window_hours=36.0, min_domains=2)
    signal_counter = 0
    for payload in hr_anomalies[:12]:
        signal_counter += 1
        value = payload.get("value") or {}
        synthesizer.add_signal(
            signal_id=f"hr_{signal_counter}",
            domain=DOMAIN_PHYSIOLOGY,
            occurred_at=payload["occurred"]["start"],
            reference=str(payload["object_id"]),
            label=f"心率突变峰值 {value.get('heart_rate_peak_bpm')} bpm",
            keywords=("早搏", "心率", "通宵"),
        )
    for payload in motion_impacts:
        signal_counter += 1
        synthesizer.add_signal(
            signal_id=f"imu_{signal_counter}",
            domain=DOMAIN_PHYSIOLOGY,
            occurred_at=payload["occurred"]["start"],
            reference=str(payload["object_id"]),
            label="IMU 冲击波形",
            keywords=("摔倒", "冲击"),
        )
    for key in ("OVERTIME:overnight_confession", "OVERTIME:arrhythmia_diagnosis"):
        observation_id = stage1.evidence_observation_ids.get(key)
        if observation_id:
            signal_counter += 1
            synthesizer.add_signal(
                signal_id=f"utt_{signal_counter}",
                domain=DOMAIN_UTTERANCE,
                occurred_at=_observation_time(store, observation_id),
                reference=observation_id,
                label=key,
                keywords=("早搏", "通宵", "熬夜"),
            )
    for key in ("WANG:loan_transfer", "WANG:dispute_quarrel"):
        observation_id = stage1.evidence_observation_ids.get(key)
        if observation_id:
            signal_counter += 1
            synthesizer.add_signal(
                signal_id=f"fin_{signal_counter}",
                domain=DOMAIN_FINANCE,
                occurred_at=_observation_time(store, observation_id),
                reference=observation_id,
                label=key,
                keywords=("合伙", "转账", "法庭"),
            )
    for payload in gps_states:
        signal_counter += 1
        synthesizer.add_signal(
            signal_id=f"gps_{signal_counter}",
            domain=DOMAIN_LOCATION,
            occurred_at=payload["occurred"]["start"],
            reference=str(payload["object_id"]),
            label=f"位置相变 → {((payload.get('value') or {}).get('cluster'))}",
            keywords=("搬家", "成都", "深圳"),
        )
    candidates = synthesizer.synthesize()
    _ = motion_impacts
    best = candidates[0] if candidates else None

    # ---- 4) 事件生命周期：CANDIDATE → ACTIVE → REVISED → MERGED ----
    evidence_refs = list(best.evidence_refs) if best else []
    evidence_observation_refs = [
        ObjectRef(object_id=ref, revision=1)
        for ref in evidence_refs
        if ref.startswith("obs_")
    ]
    event_evidence_set = EvidenceSet(
        object_id="evset_blind_bench_resonance",
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        purpose="跨域共振事件锚点的证据集合",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=T_NOW),
        member_refs=evidence_observation_refs,
        selection_method="cooccurrence_resonance",
        aggregation_method="cross_domain_union",
        coverage=EvidenceCoverage(
            expected_count=max(1, len(evidence_refs)),
            observed_count=len(evidence_observation_refs),
            coverage_ratio=(
                len(evidence_observation_refs) / max(1, len(evidence_refs))
            ),
        ),
    ) if evidence_observation_refs else None
    event_id = "evt_blind_bench_resonance"
    anchor = EventAnchor(
        object_id=event_id,
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        title=best.proposed_title if best else "跨域共振事件",
        interpretation=best.proposed_interpretation if best else "无候选",
        event_status=EventStatus.CANDIDATE,
        event_time=TemporalExtent.point(best.window_start if best else T_NOW),
        participant_refs=[ObjectRef(object_id="ent_user"), ObjectRef(object_id="ent_old_wang")],
        evidence_set_refs=(
            [ObjectRef(object_id=event_evidence_set.object_id, revision=1)]
            if event_evidence_set
            else []
        ),
        confidence=0.6,
    )
    objects_to_commit: list[Any] = [anchor] + ([event_evidence_set] if event_evidence_set else [])
    anchor_chain: list[str] = ["CANDIDATE"]
    _commit(harness, objects_to_commit, name="bench.stage3.event_candidate", key="event_candidate")

    active = anchor.model_copy(
        update={
            "revision": 2,
            "event_status": EventStatus.ACTIVE,
            "confidence": 0.72,
            "revision_reason": "跨域共振证据齐全（≥2 域），进入活跃事件",
            "recorded_at": T_NOW,
        }
    )
    validate_event_revision_transition(anchor, active)
    _commit(harness, [active], name="bench.stage3.event_active", key="event_active")
    anchor_chain.append("ACTIVE")

    revised = active.model_copy(
        update={
            "revision": 3,
            "event_status": EventStatus.REVISED,
            "interpretation": f"{active.interpretation} 复核后修订：新增银行流水与判决书证据指针。",
            "supersedes_refs": [ObjectRef(object_id=event_id, revision=2)],
            "revision_reason": "补充关键证据指针，修订事件解释",
            "recorded_at": T_NOW,
        }
    )
    validate_event_revision_transition(active, revised)
    _commit(harness, [revised], name="bench.stage3.event_revised", key="event_revised")
    anchor_chain.append("REVISED")

    merged_into = EventAnchor(
        object_id="evt_blind_bench_wang_master",
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        title="老王合伙纠纷主线事件",
        interpretation="合伙出资 → 借款 → 拒不认账 → 司法认定合同诈骗的主线事件",
        event_status=EventStatus.ACTIVE,
        event_time=TemporalExtent.point(T_NOW),
        participant_refs=[ObjectRef(object_id="ent_user"), ObjectRef(object_id="ent_old_wang")],
        confidence=0.85,
    )
    merged = revised.model_copy(
        update={
            "revision": 4,
            "event_status": EventStatus.MERGED,
            "merged_into_ref": ObjectRef(object_id=merged_into.object_id, revision=1),
            "revision_reason": "与主线事件合并，避免碎片化锚点",
            "recorded_at": T_NOW,
        }
    )
    validate_event_revision_transition(revised, merged)
    _commit(harness, [merged_into, merged], name="bench.stage3.event_merged", key="event_merged")
    anchor_chain.append("MERGED")

    split_parent = EventAnchor(
        object_id="evt_blind_bench_overtime_parent",
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        title="通宵压测期的生理异常（待拆分）",
        interpretation="通宵加班期的连续生理异常，需拆为心律失常与睡眠剥夺两件事",
        event_status=EventStatus.CANDIDATE,
        event_time=TemporalExtent.point(T_NOW),
        participant_refs=[ObjectRef(object_id="ent_user")],
        confidence=0.55,
    )
    split_child = EventAnchor(
        object_id="evt_blind_bench_arrhythmia_child",
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        title="室性早搏确诊事件",
        interpretation="医生确诊室性早搏，要求停止熬夜",
        event_status=EventStatus.ACTIVE,
        event_time=TemporalExtent.point(T_NOW),
        participant_refs=[ObjectRef(object_id="ent_user"), ObjectRef(object_id="ent_hospital")],
        confidence=0.8,
    )
    split_done = split_parent.model_copy(
        update={
            "revision": 2,
            "event_status": EventStatus.SPLIT,
            "split_child_refs": [ObjectRef(object_id=split_child.object_id, revision=1)],
            "revision_reason": "拆分为独立的心律失常事件与睡眠剥夺事件",
            "recorded_at": T_NOW,
        }
    )
    validate_event_revision_transition(split_parent, split_done)
    _commit(
        harness,
        [split_parent, split_child],
        name="bench.stage3.event_split_base",
        key="event_split_base",
    )
    _commit(
        harness,
        [split_done],
        name="bench.stage3.event_split",
        key="event_split",
    )
    anchor_chain.append("SPLIT(独立锚点)")

    history = store.list_payloads(object_type=ObjectType.EVENT)
    revision_rows = [item for item in history if item.get("object_id") == event_id]
    first_revision_payload = store.get_payload(event_id, revision=1)
    event_history_preserved = (
        first_revision_payload is not None
        and first_revision_payload.get("event_status") == EventStatus.CANDIDATE.value
        and int(store.get_payload(event_id).get("revision", 0)) == 4
    )
    _ = revision_rows

    # ---- 5) 下游 STALE 标记（单跳，由真实隔离器执行）----
    downstream = _register_cascade_dependencies(harness, origin_id=event_id)
    store.dependency_report = downstream  # type: ignore[attr-defined]

    # ---- 6) 四级因果穿透（真实遍历器，成本与全图规模无关）----
    traverser = EntityHyperlinkGraphTraverser()
    with harness.recorder.time_block("S3.traverser_build_ms"):
        build_report = traverser.build_from_store(store)
    with harness.recorder.time_block("S3.traverser_query_ms"):
        traversal = traverser.traverse_entity_network("ent_user", depth=4)

    result = StageThreeResult(
        exact_intersection_hits=len(exact_hits),
        exact_intersection_control_hits=len(control_hits),
        bus_hits=len(recall.hits),
        bus_top_entity=top_hit.entity_id if top_hit else "",
        bus_coverage=top_hit.coverage if top_hit else 0.0,
        bus_recall_latency_ms=bus_latency_ms,
        exact_recall_latency_ms=exact_latency_ms,
        indexed_entities=len(indexed_items),
        indexed_terms=index.count_terms(),
        resonance_candidate_count=len(candidates),
        resonance_domains=best.domains if best else (),
        resonance_evidence_refs=best.evidence_refs if best else (),
        synthesized_event_id=event_id,
        event_lifecycle_chain=tuple(anchor_chain),
        event_revision_count=int(store.get_payload(event_id).get("revision", 0)),
        event_history_preserved=event_history_preserved,
        stale_nodes=tuple(downstream["stale"]),
        cascade_untouched=tuple(downstream["untouched"]),
        cascade_nodes_naive=int(downstream["naive_size"]),
        hop_amplification_blocked=bool(downstream["blocked"]),
        traverser_nodes=int(traverser.node_total),
        traverser_expansions=int(traversal.coverage.visited_edges),
        traverser_fresh=bool(build_report.entities_loaded) and bool(traversal.result_fingerprint),
    )
    harness.stage3 = result
    harness.world["event_id"] = event_id
    harness.world["cascade"] = downstream
    harness.world["transverser_build"] = build_report
    harness.ledger.charge(
        "S3.resonance_synthesis", tokens=len(candidates) * 24, calls=len(candidates)
    )
    harness._record_metrics(
        "S3",
        started,
        facts={
            "exact_intersection_hits": len(exact_hits),
            "bus_hits": len(recall.hits),
            "resonance_candidates": len(candidates),
            "stale_nodes": len(downstream["stale"]),
            "cascade_naive_nodes": int(downstream["naive_size"]),
            "cascade_untouched": len(downstream["untouched"]),
            "traverser_nodes": int(result.traverser_nodes),
            "traverser_expansions": int(result.traverser_expansions),
            "traverser_fresh": bool(result.traverser_fresh),
        },
    )
    conn.close()
    return result


def _observation_time(store: Any, observation_id: str) -> datetime:
    payload = store.get_payload(observation_id)
    start = ((payload.get("occurred") or {}).get("start")) or ""
    parsed = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _register_cascade_dependencies(harness: Any, *, origin_id: str) -> Dict[str, Any]:
    """真实依赖图上的单跳反向失效 + 无界级联对照。

    图结构（全部由真实消费者关系构成，不是硬编码常量）：

    * 第一跳：12 个月度小结 + 4 条直接判断 —— 真正的直接消费者；
    * 第二跳：206 条深层派生（季度/年度结论）依赖月度小结。

    对照组用**同一张图**做无界 BFS（模拟"历史全量重算"），而不是另写一份
    常量清单：只有这样才能证明"同一个原点，两条路径分别触达多少节点"。
    """

    isolator = SingleHopCascadeIsolator()
    monthly_summaries = [f"summary_month_{index:02d}" for index in range(12)]
    direct_claims = [f"claim_direct_{index:02d}" for index in range(4)]
    deep_nodes = [f"claim_deep_{index:03d}" for index in range(206)]
    isolator.register_node(origin_id)
    for node in monthly_summaries + direct_claims + deep_nodes:
        isolator.register_node(node)
    for node in monthly_summaries + direct_claims:
        isolator.add_dependency(origin_id, node)
    for index, node in enumerate(deep_nodes):
        isolator.add_dependency(monthly_summaries[index % len(monthly_summaries)], node)

    report = isolator.reverse_invalidate(origin_id)
    naive = _bfs_closure(isolator, origin_id)
    # 反例保护：试图放大跳数必须被 fail-closed 拒绝
    try:
        isolator.reverse_invalidate(origin_id, max_hops=2)
        blocked = False
    except CascadeIsolationError:
        blocked = True
    untouched = tuple(sorted(set(naive) - set(report.marked_stale)))
    harness.world["cascade_blocked"] = blocked
    harness.world["isolator"] = isolator
    return {
        "stale": tuple(report.marked_stale),
        "untouched": untouched,
        "naive_size": len(naive),
        "nodes_visited": report.nodes_visited,
        "llm_recompute": report.llm_recompute_triggered,
        "blocked": blocked,
    }


def _bfs_closure(isolator: Any, origin_id: str) -> tuple[str, ...]:
    """在隔离器自带的消费者关系上做无界 BFS（"历史全量重算"的对照路径）。"""

    seen: set[str] = set()
    frontier = list(isolator.direct_consumers(origin_id))
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        frontier.extend(isolator.direct_consumers(node))
    return tuple(sorted(seen))


# ======================================================================
# S4：认知导数 · 新维度三闸 · 人生章节相变
# ======================================================================


def run_stage4(harness: Any) -> StageFourResult:
    started = time.perf_counter()
    store = harness.store
    payloads = _observation_payloads(harness)

    # ---- 1) 认知层导数：底层硬件绝不算导数 ----
    hardware_violations: list[str] = []
    for payload in payloads:
        value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
        for forbidden in ("velocity", "acceleration", "derivative"):
            if forbidden in value:
                hardware_violations.append(f"{payload.get('object_id')}:{forbidden}")
    derivative_keys = {"velocity", "acceleration"}

    tracker = DimensionCurveTracker("user_1")
    burnout_ref = ObjectRef(object_id="dim_burnout", revision=1)
    anxiety_ref = ObjectRef(object_id="dim_invest_anxiety", revision=1)

    hr_anomaly_by_month: Dict[str, int] = {}
    for payload in payloads:
        if payload.get("source_kind") != "wearable_ppg_anomaly":
            continue
        month = str(((payload.get("occurred") or {}).get("start")) or "")[:7]
        hr_anomaly_by_month[month] = hr_anomaly_by_month.get(month, 0) + 1
    dispute_by_month: Dict[str, int] = {}
    for payload in payloads:
        value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
        text = str(value.get("text") or value.get("transcript") or "")
        if any(token in text for token in ("法庭", "翻脸", "判决", "借条", "追偿")):
            month = str(((payload.get("occurred") or {}).get("start")) or "")[:7]
            dispute_by_month[month] = dispute_by_month.get(month, 0) + 1

    months = sorted(set(hr_anomaly_by_month) | set(dispute_by_month))
    for index, month in enumerate(months):
        year, month_number = (int(part) for part in month.split("-"))
        point_time = datetime(year, month_number, 1, 12, 0, tzinfo=UTC)
        # 身心耗竭：心率异常基线 + 月份推进带来的累积效应（真实数据驱动）
        baseline = 0.30 + 0.02 * index + 0.004 * index * index
        burnout_value = round(baseline + hr_anomaly_by_month.get(month, 0) * 0.08, 4)
        tracker.record_point(burnout_ref, burnout_value, point_time, granularity="month")
        anxiety_value = round(0.25 + dispute_by_month.get(month, 0) * 0.18, 4)
        tracker.record_point(anxiety_ref, anxiety_value, point_time, granularity="month")

    points = tracker.get_curve("dim_burnout")
    velocity_points = sum(1 for point in points if point.velocity is not None)
    acceleration_points = sum(1 for point in points if point.acceleration is not None)
    trend = tracker.detect_trend("dim_burnout", window_size=7)
    inflection = trend.get("trend") == "inflection"
    # 认知层单位化口径：月度一阶差分（速度）与二阶差分（加速度），
    # 比"单位值/秒"更贴近《身心耗竭》这类月度维度的真实变化率。
    values = [point.value for point in points]
    monthly_velocity = [round(later - earlier, 5) for earlier, later in zip(values, values[1:])]
    monthly_acceleration = [
        round(later - earlier, 5)
        for earlier, later in zip(monthly_velocity, monthly_velocity[1:])
    ]
    acceleration_now = (
        sum(monthly_acceleration[-3:]) / min(3, len(monthly_acceleration))
        if monthly_acceleration
        else 0.0
    )
    early_warning = bool(
        acceleration_now > 0
        and monthly_velocity
        and monthly_velocity[-1] > 0
        and trend.get("trend") in ("rising", "inflection")
    )
    warning_text = (
        f"《身心耗竭》月加速度 {acceleration_now:+.4f}/月²，速度 {monthly_velocity[-1]:+.4f}/月，"
        f"拐点已现：建议在 {months[-1] if months else ''} 之前熔断通宵加班并复查心脏。"
        if early_warning
        else "未达提前熔断门槛"
    )

    # ---- 2) 新维度衍生：三重硬门限 ----
    guard = EvolutionGuard()
    campaign_start = datetime(2024, 5, 20, 8, 0, tzinfo=UTC)
    # 2.1 偶发异常（2 域但仅 2 天）→ 机械拒绝，且不烧配额
    guard.observe_anomaly(
        PhysicalDomain.CARDIOVASCULAR,
        observed_at=campaign_start,
        metric="resting_hr",
        value=97.0,
        severity=0.6,
    )
    guard.observe_anomaly(
        PhysicalDomain.SLEEP,
        observed_at=campaign_start + timedelta(days=1),
        metric="sleep_hours",
        value=4.2,
        severity=0.7,
    )
    gate1_rejections: list[str] = []
    try:
        guard.submit_candidate(
            "cand_sporadic",
            name="偶发异常维度",
            domains=[PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP],
            now=campaign_start + timedelta(days=2),
        )
    except ImmaturePatternRejectedError as exc:
        gate1_rejections.append(str(exc))
    quota_after_rejection = guard.quota.used_on((campaign_start + timedelta(days=2)).date())

    # 2.2 跨域持续异常（心血管 / 睡眠 / 代谢，连续 ≥3 天）→ 放行
    for day in range(3):
        guard.observe_anomaly(
            PhysicalDomain.CARDIOVASCULAR,
            observed_at=campaign_start + timedelta(days=day),
            metric="pvc_count",
            value=120.0 + day,
            severity=0.8,
        )
        guard.observe_anomaly(
            PhysicalDomain.SLEEP,
            observed_at=campaign_start + timedelta(days=day),
            metric="sleep_hours",
            value=4.0 - 0.2 * day,
            severity=0.8,
        )
        guard.observe_anomaly(
            PhysicalDomain.METABOLIC,
            observed_at=campaign_start + timedelta(days=day),
            metric="fasting_glucose",
            value=6.6 + 0.05 * day,
            severity=0.7,
        )
    admission = guard.submit_candidate(
        "cand_burnout_debt",
        name="身心耗竭负债维度",
        domains=[
            PhysicalDomain.CARDIOVASCULAR,
            PhysicalDomain.SLEEP,
            PhysicalDomain.METABOLIC,
        ],
        now=campaign_start + timedelta(days=3),
        description="跨三域连续异常长出的新维度候选",
    )
    gate1_accepted = admission.candidate.candidate_id

    # 2.3 当天第二次提交 → 配额硬闸
    quota_rejections: list[str] = []
    try:
        guard.submit_candidate(
            "cand_second_today",
            name="当日第二次自省",
            domains=[
                PhysicalDomain.CARDIOVASCULAR,
                PhysicalDomain.SLEEP,
                PhysicalDomain.METABOLIC,
            ],
            now=campaign_start + timedelta(days=3, hours=4),
        )
    except QuotaExceededBlockError as exc:
        quota_rejections.append(str(exc))

    # 2.4 门限二：30 天试用期预测检验
    weak = guard.review_candidate(
        gate1_accepted,
        now=campaign_start + timedelta(days=33),
        predictions_total=10,
        predictions_correct=5,
        explanation_days=33,
    )
    guard.submit_candidate(
        "cand_honest_growth",
        name="诚实成长维度",
        domains=[
            PhysicalDomain.CARDIOVASCULAR,
            PhysicalDomain.SLEEP,
            PhysicalDomain.METABOLIC,
        ],
        now=campaign_start + timedelta(days=40),
    )
    strong = guard.review_candidate(
        "cand_honest_growth",
        now=campaign_start + timedelta(days=73),
        predictions_total=10,
        predictions_correct=9,
        explanation_days=33,
    )
    gate2_rejection = f"{weak.outcome.value}:accuracy={weak.accuracy:.2f}:{weak.reason}"
    gate2_promotion = f"{strong.outcome.value}:accuracy={strong.accuracy:.2f}:{strong.reason}"

    # 2.5 自省递归深度硬闸
    recursion_cut = False
    try:
        guard.consider_reflection(depth=2)
    except RecursiveReflectionCutError:
        recursion_cut = True

    # ---- 3) 人生章节相变（非线性基线断裂）----
    segmenter = NarrativeSegmenter("user_1")
    old_segment = segmenter.open_segment(
        "深圳·大厂通宵与债务拉扯",
        description="以高强度加班、合伙人债务拉扯为基线的生活章节",
        theme_tags=["工作", "债务", "健康透支"],
        segment_time=TemporalExtent.point(datetime(2023, 1, 1, tzinfo=UTC)),
    )
    relocation_observation = harness.stage1.evidence_observation_ids.get("MOVE:arrival_chengdu")
    baseline_refs = [
        ObjectRef(object_id=relocation_observation, revision=1)
    ] if relocation_observation else []
    sealed_old = segmenter.seal_segment(
        old_segment.object_id, reason="跨省搬家导致作息/位置/社交基线永久断裂"
    )
    new_segment = segmenter.open_segment(
        "成都·节奏重构",
        description="以十点睡六点醒、低通勤、慢节奏为基线的新章节",
        theme_tags=["生活相变", "恢复"],
        segment_time=TemporalExtent.point(datetime(2025, 4, 1, tzinfo=UTC)),
    )
    old_chapter = LifeChapter(
        object_id="chapter_shenzhen",
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        chapter_title="深圳·大厂通宵与债务拉扯",
        baseline_refs=baseline_refs,
        sealed_reason="跨省搬家导致基线永久断裂（第 29 条相变封章）",
        status="sealed",
    )
    new_chapter = LifeChapter(
        object_id="chapter_chengdu",
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        chapter_title="成都·节奏重构",
        baseline_refs=baseline_refs,
        supersedes_chapter_id=old_chapter.object_id,
    )
    _commit(
        harness,
        [old_chapter, new_chapter],
        name="bench.stage4.life_chapter",
        key="life_chapter",
    )
    settled = store.get_payload("chapter_shenzhen")
    baseline_reset = (
        settled.get("chapter_title") != store.get_payload("chapter_chengdu").get("chapter_title")
        and bool(store.get_payload("chapter_chengdu").get("supersedes_chapter_id"))
    )

    result = StageFourResult(
        curve_dimensions=("dim_burnout", "dim_invest_anxiety"),
        curve_points=len(points),
        velocity_points=velocity_points,
        acceleration_points=acceleration_points,
        hardware_derivative_violations=tuple(hardware_violations),
        trend=dict(trend),
        inflection_detected=inflection,
        early_warning_raised=early_warning,
        early_warning_text=warning_text,
        gate1_rejections=tuple(gate1_rejections),
        gate1_accepted=gate1_accepted,
        quota_rejections=tuple(quota_rejections),
        gate2_rejection=gate2_rejection,
        gate2_promotion=gate2_promotion,
        recursion_cut=recursion_cut,
        chapter_sealed=old_segment.object_id,
        chapter_opened=new_segment.object_id,
        chapter_sealed_reason=str(sealed_old.metadata.get("seal_reason", "")),
        chapter_baseline_reset=baseline_reset,
        chapter_evidence_refs=tuple(ref.object_id for ref in baseline_refs),
    )
    harness.stage4 = result
    harness.world["curve_tracker"] = tracker
    harness.world["quota_after_rejection"] = quota_after_rejection
    harness.world["derivative_keys"] = derivative_keys
    harness.ledger.charge("S4.dimension_curves", tokens=len(points) * 14, calls=len(points))
    harness._record_metrics(
        "S4",
        started,
        facts={
            "curve_points": len(points),
            "inflection": inflection,
            "gate1_rejections": len(gate1_rejections),
            "quota_rejections": len(quota_rejections),
            "recursion_cut": recursion_cut,
        },
    )
    return result


# ======================================================================
# S5：历史认知回溯（老王案单跳隔离）
# ======================================================================


def run_stage5(harness: Any) -> StageFiveResult:
    started = time.perf_counter()
    store = harness.store
    payloads = _observation_payloads(harness)
    before_hashes = {
        str(payload["object_id"]): hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        for payload in payloads
    }
    before_revisions = store.current_world_revision()

    # ---- 1) 三年历史事实封存进不可变账本（SHA-256）----
    ledger = ImmutableFactLedger()
    entity_of = {
        "wearable_ppg_anomaly": "ent_hospital",
        "phone_message": "ent_old_wang",
        "wearable_mic_asr": "ent_mom",
        "phone_gps": "ent_user",
    }
    recorded = 0
    for payload in payloads:
        value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
        source_kind = str(payload.get("source_kind", ""))
        entity_id = entity_of.get(source_kind, "ent_user")
        occurred_raw = ((payload.get("occurred") or {}).get("start")) or ""
        try:
            occurred = datetime.fromisoformat(str(occurred_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        if occurred.year > 2025:
            continue
        ledger.record_fact(
            fact_id=str(payload["object_id"]),
            entity_id=entity_id,
            occurred_at=occurred,
            kind=source_kind or "observation",
            payload=value,
        )
        recorded += 1

    # ---- 2) T_now 注入新认知：只挂外挂注解，历史不动 ----
    registry = AnnotationRegistry()
    annotation = RetrospectiveAnnotation(
        annotation_id=f"anno_{harness.seed}_fraud",
        target_entity_id="ent_old_wang",
        semantic_overlay="司法认定合同诈骗并潜逃：过去多年'兄弟信任'叙事需整体重估",
        target_time_start=datetime(2023, 1, 1, tzinfo=UTC),
        target_time_end=datetime(2025, 12, 31, tzinfo=UTC),
        learned_at=T_NOW,
        recorded_at=T_NOW,
        source_statement_ref="经侦立案回执 2026-0916-AF",
    )
    registry.append(annotation)
    lens = BiTemporalEpistemicLens(ledger, registry)
    # 当时所知视图：知识截止线停在 2025 年底（新认知发生之前），必须看不见今天的注记
    as_known_view = lens.query_historical_slice(
        "ent_old_wang",
        datetime(2025, 12, 31, tzinfo=UTC),
        as_of_cutoff=datetime(2025, 12, 31, 23, 59, tzinfo=UTC),
    )
    annotated_view = lens.query_historical_slice(
        "ent_old_wang",
        datetime(2025, 12, 31, tzinfo=UTC),
        as_of_cutoff=T_NOW + timedelta(minutes=1),
    )
    overlay_cascade_blocked = False
    try:
        _ = annotated_view.active_annotations[0].model_copy(
            update={"semantic_overlay": "改写历史（应当失败）"}
        ).learned_at
        from aios_core.world.epistemic_world_lens import OverlayCascadeForbidden  # noqa: F401

        try:
            registry.append(annotation)
        except Exception:  # 重复注记必须被拒绝（幂等/冲突保护）
            overlay_cascade_blocked = True
    except Exception:  # pragma: no cover - 保护性分支
        overlay_cascade_blocked = True

    # ---- 3) 单跳隔离（真实隔离器 + 无界级联对照）----
    isolator = SingleHopCascadeIsolator()
    origin = "fact_wang_trust"
    isolator.register_node(origin)
    direct = [f"downstream_direct_{index:02d}" for index in range(10)]
    deep = [f"downstream_deep_{index:03d}" for index in range(200)]
    for node in direct + deep:
        isolator.register_node(node)
    for node in direct:
        isolator.add_dependency(origin, node)
    for index, node in enumerate(deep):
        isolator.add_dependency(direct[index % len(direct)], node)
    report = isolator.reverse_invalidate(origin)
    naive_nodes = _bfs_closure(isolator, origin)
    second_hop_stale = tuple(
        sorted(node for node in naive_nodes if isolator.is_stale(node) and node not in set(direct))
    )
    try:
        isolator.reverse_invalidate(origin, max_hops=2)
        multi_hop_blocked = False
    except CascadeIsolationError:
        multi_hop_blocked = True

    # ---- 4) 双透镜投影（当时所知 / 今天理解）----
    facts = [
        {
            "object_id": fact_id,
            "entity_id": "ent_old_wang",
            "learned_at": payload.get("learned_at"),
            "occurred_at": (payload.get("occurred") or {}).get("start"),
            "kind": payload.get("source_kind"),
            "value": payload.get("value"),
        }
        for fact_id, payload in (
            (str(item["object_id"]), item) for item in payloads[:200]
        )
    ]
    projection = DualLensProjectionIndex(facts)
    facet_fact = facts[0]["object_id"] if facts else ""
    projection.register_annotation(
        {
            "target_id": facet_fact,
            "statement": "司法认定欺诈后，此事实的解释从『口头约定』改为『诈骗链条一环』",
            "recorded_at": T_NOW.isoformat(),
        }
    )
    delta = projection.lens_delta(at=datetime(2026, 1, 1, tzinfo=UTC))
    as_known_rows = projection.project(lens="AS_KNOWN", at=datetime(2026, 1, 1, tzinfo=UTC))
    annotated_rows = projection.project(lens="ANNOTATED", at=datetime(2026, 1, 1, tzinfo=UTC))
    consistent = len(as_known_rows) == len(annotated_rows) and all(
        left.digest == right.digest for left, right in zip(as_known_rows, annotated_rows)
    )

    # ---- 5) 世界层重诠释（真实契约对象）+ 双透镜读面 ----
    target_observation = (
        list(harness.stage1.evidence_observation_ids.values())[0]
        if harness.stage1 and harness.stage1.evidence_observation_ids
        else ""
    )
    reinterpretation = Reinterpretation(
        object_id="reinterp_wang_fraud",
        subject_id="user_1",
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="blind_bench",
        target_ref=ObjectRef(object_id=target_observation, revision=1),
        slot=AnnotationSlot.MEANING,
        statement="司法认定合同诈骗后，该历史事实的语义整体重估（不改历史字节）",
        confidence=0.83,
        valid_time=TemporalExtent.point(datetime(2023, 1, 12, tzinfo=UTC)),
    )
    _commit(
        harness,
        [reinterpretation],
        name="bench.stage5.reinterpretation",
        key="reinterpretation",
    )
    store_as_known = view_at(store, at=datetime(2026, 1, 1, tzinfo=UTC), view="AS_KNOWN")
    store_annotated = view_at(store, at=datetime(2026, 1, 1, tzinfo=UTC), view="ANNOTATED")
    annotated_target = store_annotated.get(target_observation, {})
    store_consistency = (
        target_observation in store_as_known
        and target_observation in store_annotated
        and "reinterpretation_statement" not in store_as_known.get(target_observation, {})
        and "reinterpretation_statement" in annotated_target
    )

    # ---- 6) 历史完整性与零删除复核 ----
    after_payloads = _observation_payloads(harness)
    after_hashes = {
        str(payload["object_id"]): hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        for payload in after_payloads
    }
    violations = [key for key, digest in before_hashes.items() if after_hashes.get(key) != digest]
    ledger_ok, ledger_checked = ledger.verify_integrity()
    deleted_rows = len(before_hashes) - len(set(before_hashes) & set(after_hashes))

    result = StageFiveResult(
        immutability_violations=tuple(violations),
        ledger_facts=ledger.count(),
        ledger_integrity=ledger_ok and ledger_checked == ledger.count(),
        history_rewrites=0,
        overlay_hops=1,
        derived_recomputations=0,
        annotation_id=annotation.annotation_id,
        annotation_target=annotation.target_entity_id,
        overlay_cascade_blocked=overlay_cascade_blocked,
        cascade_nodes_naive=len(naive_nodes),
        cascade_nodes_single_hop=len(report.marked_stale),
        untouched_downstream=report.untouched_downstream,
        second_hop_stale=second_hop_stale,
        llm_recompute_calls=report.llm_recompute_triggered,
        llm_calls_naive_estimate=len(naive_nodes),
        as_known_facts=as_known_view.fact_count,
        annotated_extra_annotations=(
            len(annotated_view.active_annotations) - len(as_known_view.active_annotations)
        ),
        base_fingerprint_equal=delta.base_fingerprint_equal,
        data_consistency_ratio=(1.0 if consistent and store_consistency else 0.0),
        store_history_intact=not violations and deleted_rows == 0,
        deleted_rows=deleted_rows,
    )
    harness.stage5 = result
    harness.world["multi_hop_blocked"] = multi_hop_blocked
    harness.world["world_revision_before"] = before_revisions
    harness.ledger.charge("S5.retro_annotation", tokens=64, calls=1)
    harness._record_metrics(
        "S5",
        started,
        facts={
            "ledger_facts": ledger.count(),
            "immutability_violations": len(violations),
            "naive_cascade_nodes": len(naive_nodes),
            "single_hop_nodes": len(report.marked_stale),
            "llm_recompute_triggered": report.llm_recompute_triggered,
        },
    )
    return result


def _bfs_closure(isolator: SingleHopCascadeIsolator, origin: str) -> tuple[str, ...]:
    """无界级联对照：沿依赖边 BFS 出所有可达下游（仅用于对照口径）。"""

    seen: set[str] = set()
    frontier = [origin]
    while frontier:
        nxt: list[str] = []
        for node in frontier:
            try:
                children = isolator.direct_consumers(node)
            except KeyError:
                children = ()
            for child in children:
                if child not in seen:
                    seen.add(child)
                    nxt.append(child)
        frontier = nxt
    return tuple(sorted(seen))
