"""M1-018 四大硬门禁 · 独立复核（Gate Audit）。

本件**不重复实现**，也不修改主实现（提交 `829a0a2`）与其补充件
（`fact_immutability_ledger`）。它只做一件事：以工单原文的四条硬门禁为
判据，用**独立构造的场景与断言**去压现有实现，证明门禁是真通过的，
而不是"测试与实现互相自洽"。

场景（工单规约，非低幼化样例）：
    用户两年前与核心技术合伙人签署《Pre-A 轮联合孵化与股权代持对赌协议》。
    730 天内累积 18,000 条客观事实 Observation（技术评审、商业汇款凭证、
    深夜高压谈判的心率变异度与皮质醇体征、重大合同）。第 730 天司法机关
    下达冻结查封裁定书，证实该合伙人自设立之初即利用关联离岸空壳公司
    转移核心知识产权并隐匿巨额对外连带担保。

四门禁：
    G1 历史事实绝对不可变（18,000 条 SHA-256 基线，注记后 100% 一致，禁 UPDATE/DELETE）
    G2 今天只写一条 RetrospectiveAnnotation（learned_at=T_today，valid=[T0,T_today]）
    G3 双时间认知透镜（as_of_cutoff=T0+100d 时 active_annotations 必为空）
    G4 单跳隔离杜绝雪崩（5 层依赖，is_stale 严格 = 10 个 1 级节点，深度严格 = 1）

G4 附带**负向对照**：同一张依赖图上跑朴素递归失效，实测会波及 210+ 个节点，
以此证明"单跳隔离"确实在拦一场真实的雪崩，而不是一句口号。
"""

from __future__ import annotations

import sqlite3
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aios_core.contracts.models import Observation
from aios_core.contracts.time import TemporalExtent
from aios_core.world.fact_immutability_ledger import (
    FactImmutabilityLedger,
    canonical_fact_sha256,
)
from aios_core.world.retrospective_annotation import (
    BiTemporalEpistemicLens,
    DependencyEdge,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationJournal,
    SingleHopCascadeIsolator,
)

# ---------------------------------------------------------------------------
# 场景常量
# ---------------------------------------------------------------------------

T_TODAY = datetime(2026, 9, 16, 9, 0, 0, tzinfo=UTC)
T0 = T_TODAY - timedelta(days=730)
T_PLUS_100D = T0 + timedelta(days=100)

USER_SUBJECT_ID = "subj_founder_user"
PARTNER_ENTITY_ID = "ent_cofounder_zhao"
OBSERVATION_COUNT = 18_000

ANNOTATION_ID = "rta_judicial_freeze_and_fraud_reassessment_day730"
RULING_REF = (
    "judicial-freeze-order://financial-court/2026/"
    "pre-a-ip-seizure-and-concealed-joint-guarantee"
)

# 5 层依赖网络的每层扇出（工单：一级 10、二级 200、三级 1000；此处补足到 5 层）
LAYER_FANOUT: tuple[int, ...] = (10, 20, 5, 2, 2)  # 10 → 200 → 1000 → 2000 → 4000


# ---------------------------------------------------------------------------
# 场景构造
# ---------------------------------------------------------------------------


def _fact_payload(index: int, day_offset: int) -> dict[str, object]:
    """四类高熵客观事实轮转：技术评审 / 汇款凭证 / 谈判体征 / 合同条款。"""
    kind = index % 4
    if kind == 0:
        return {
            "kind": "technical_review",
            "artifact": f"core-ip-review-{index:06d}",
            "verdict": "通过",
            "reviewer": PARTNER_ENTITY_ID,
            "ip_scope": "推理引擎核心专利族",
            "day_offset": day_offset,
        }
    if kind == 1:
        return {
            "kind": "remittance_voucher",
            "voucher_no": f"PAY-2024-{index:06d}",
            "amount_cny": 1_250_000 + index * 137,
            "purpose": "联合孵化研发费用",
            "beneficiary_declared": "孵化主体账户",
            "day_offset": day_offset,
        }
    if kind == 2:
        return {
            "kind": "negotiation_physiology",
            "session": f"late-night-round-{index // 4}",
            "hrv_rmssd_ms": 18 + (index % 23),
            "cortisol_nmoll": 480 + (index % 190),
            "local_time": "02:40",
            "counterparty": PARTNER_ENTITY_ID,
            "day_offset": day_offset,
        }
    return {
        "kind": "material_contract",
        "contract": "《Pre-A 轮联合孵化与股权代持对赌协议》补充协议",
        "clause": f"第 {index % 27 + 1} 条 业绩承诺与回购触发",
        "signatories": ["用户", PARTNER_ENTITY_ID],
        "day_offset": day_offset,
    }


def _ledger_facts(count: int = OBSERVATION_COUNT) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for i in range(count):
        day_offset = (i * 730) // count
        occurred = T0 + timedelta(days=day_offset, minutes=i % 1440)
        facts.append(
            {
                "object_id": f"obs_pre_a_{i:06d}",
                "revision": 1,
                "object_type": "observation",
                "subject_id": PARTNER_ENTITY_ID,
                "occurred_at": occurred,
                "learned_at": occurred,
                "payload": _fact_payload(i, day_offset),
            }
        )
    return facts


def _observations(count: int = OBSERVATION_COUNT) -> list[Observation]:
    total_seconds = int((T_TODAY - T0).total_seconds()) - 1
    denominator = count - 1
    out: list[Observation] = []
    for i in range(count):
        occurred_at = T0 + timedelta(seconds=(i * total_seconds) // denominator)
        out.append(
            Observation(
                object_id=f"obs_pre_a_{i:06d}",
                subject_id=USER_SUBJECT_ID,
                revision=1,
                occurred=TemporalExtent.point(occurred_at),
                learned_at=occurred_at,
                recorded_at=occurred_at,
                created_by="m1-018-independent-gate-audit",
                source_kind="signed-enterprise-evidence-stream",
                modality="fiduciary_contract_execution",
                value=_fact_payload(i, (occurred_at - T0).days),
                data_quality={"evidence_grade": "auditable", "sequence": i},
                metadata={
                    "target_entity_id": PARTNER_ENTITY_ID,
                    "agreement_id": "pre-a-joint-incubation-nominee-equity-v4",
                },
            )
        )
    return out


def _judicial_ruling_annotation() -> RetrospectiveAnnotation:
    return RetrospectiveAnnotation(
        annotation_id=ANNOTATION_ID,
        target_entity_id=PARTNER_ENTITY_ID,
        semantic_overlay=(
            "第 730 日司法冻结查封裁定确认：该核心技术合伙人自联合孵化关系设立之初，"
            "即通过关联离岸空壳公司转移核心知识产权，并隐匿巨额对外连带担保。"
            "此前全部基于信任假设形成的商业认知需按欺诈重估口径重新解读，"
            "但客观事实本身一个字节都不改。"
        ),
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=T_TODAY,
        source_statement_ref=RULING_REF,
    )


def _five_layer_edges() -> list[tuple[str, str]]:
    """root → L1(10) → L2(200) → L3(1000) → L4(2000) → L5(4000)，共 5 层。"""
    edges: list[tuple[str, str]] = []
    previous_layer = ["cog_partner_trust_root"]
    for depth, fanout in enumerate(LAYER_FANOUT, start=1):
        current_layer = [
            f"l{depth}_node_{index:05d}"
            for index in range(len(previous_layer) * fanout)
        ]
        for parent_index, parent in enumerate(previous_layer):
            for child in current_layer[
                parent_index * fanout : (parent_index + 1) * fanout
            ]:
                edges.append((parent, child))
        previous_layer = current_layer
    return edges


def _naive_recursive_invalidation(edges: list[tuple[str, str]], root: str) -> set[str]:
    """负向对照：朴素递归反向失效会波及多少节点（这就是要被掐灭的雪崩）。"""
    reverse: dict[str, list[str]] = {}
    for upstream, dependent in edges:
        reverse.setdefault(upstream, []).append(dependent)

    visited: set[str] = set()
    queue = deque(reverse.get(root, ()))
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(reverse.get(node, ()))
    return visited


# ---------------------------------------------------------------------------
# G1 历史事实绝对不可变
# ---------------------------------------------------------------------------


def test_g1_18000_facts_sha256_baseline_unchanged_after_annotation(
    tmp_path: Path,
) -> None:
    """18,000 条客观事实封存后写入裁定注记，逐条 SHA-256 必须 100% 一致。"""
    conn = sqlite3.connect(":memory:")
    try:
        ledger = FactImmutabilityLedger(conn)
        facts = _ledger_facts()
        assert ledger.seal_many(facts) == OBSERVATION_COUNT

        before = ledger.verify_fact_integrity()
        assert before.checked == OBSERVATION_COUNT
        assert before.intact == OBSERVATION_COUNT
        assert before.all_intact

        # 独立留存一份基线哈希，避免"实现自证自洽"
        baseline = {
            fact["object_id"]: canonical_fact_sha256(fact["payload"])  # type: ignore[arg-type]
            for fact in facts
        }
        assert len(baseline) == OBSERVATION_COUNT

        # 今天写入裁定注记（走 append-only 日志，不触碰事实表）
        journal = RetrospectiveAnnotationJournal(tmp_path / "annotation_journal.db")
        journal.append(_judicial_ruling_annotation())
        assert journal.count() == 1

        after = ledger.verify_fact_integrity()
        assert after.checked == OBSERVATION_COUNT
        assert after.intact == OBSERVATION_COUNT
        assert after.all_intact
        assert after.mismatched_object_ids == ()

        # 逐条与独立基线比对（不是只信 verify 的自洽结论）
        for object_id, expected in baseline.items():
            assert ledger.digest_of(object_id) == expected

    finally:
        conn.close()


def test_g1_database_rejects_update_and_delete() -> None:
    """即使绕过应用层，数据库也必须拒绝 UPDATE / DELETE。"""
    conn = sqlite3.connect(":memory:")
    try:
        ledger = FactImmutabilityLedger(conn)
        ledger.seal_many(_ledger_facts(200))

        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "UPDATE fact_integrity_ledger SET canonical_sha256 = 'deadbeef' "
                "WHERE object_id = 'obs_pre_a_000000'"
            )
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "DELETE FROM fact_integrity_ledger WHERE object_id = 'obs_pre_a_000001'"
            )
        # 拒绝后基线仍然完好
        assert ledger.fact_count() == 200
        assert ledger.verify_fact_integrity().all_intact
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# G2 今天只写一条注记
# ---------------------------------------------------------------------------


def test_g2_single_annotation_learned_today_spanning_full_history() -> None:
    annotation = _judicial_ruling_annotation()

    assert annotation.learned_at == T_TODAY
    assert annotation.recorded_at == T_TODAY
    assert annotation.valid_time_range.start == T0
    assert annotation.valid_time_range.end == T_TODAY
    assert annotation.target_entity_id == PARTNER_ENTITY_ID


def test_g2_rejects_overlay_extending_beyond_knowledge_time() -> None:
    """valid_time 不得越过 learned_at——否则就是伪造"当时就知道"。"""
    with pytest.raises(ValueError, match="must not extend beyond learned_at"):
        RetrospectiveAnnotation(
            annotation_id="rta_backdated",
            target_entity_id=PARTNER_ENTITY_ID,
            semantic_overlay="试图把今天才知道的欺诈结论写成两年前就成立",
            target_time_start=T0,
            target_time_end=T_TODAY + timedelta(days=1),
            learned_at=T_TODAY,
            source_statement_ref=RULING_REF,
        )


# ---------------------------------------------------------------------------
# G3 双时间认知透镜
# ---------------------------------------------------------------------------


def test_g3_lens_at_day100_shows_no_overlay_and_full_history() -> None:
    """as_of_cutoff = T0+100d：忠实还原两年前用户面对的真实商业信任状态。"""
    observations = _observations(2_000)
    lens = BiTemporalEpistemicLens(
        observations,
        [_judicial_ruling_annotation()],
    )

    historical = lens.query_historical_slice(
        PARTNER_ENTITY_ID,
        target_time=T_PLUS_100D,
        as_of_cutoff=T_PLUS_100D,
    )

    # 两年前用户还不知道裁定，外挂图层必须为空
    assert historical.active_annotations == []
    # 但当时已发生的客观事实一条不少
    assert historical.observation_count > 0
    assert all(
        obs.occurred.start is not None and obs.occurred.start <= T_PLUS_100D
        for obs in historical.historical_observations
    )


def test_g3_lens_at_now_keeps_facts_and_adds_overlay() -> None:
    """as_of_cutoff = None：历史事实完整保留，同时精确叠加外挂重估图层。"""
    observations = _observations(2_000)
    lens = BiTemporalEpistemicLens(observations, [_judicial_ruling_annotation()])

    current = lens.query_historical_slice(
        PARTNER_ENTITY_ID,
        target_time=T_TODAY,
        as_of_cutoff=None,
    )

    assert len(current.active_annotations) == 1
    assert current.active_annotations[0].annotation_id == ANNOTATION_ID
    assert current.observation_count == 2_000

    # 关键不变量：加不加图层，历史事实集合必须逐条一致（同一 target_time、
    # 同一 as_of_cutoff）。图层的唯一作用是"外挂解读"，不得触碰事实。
    bare = BiTemporalEpistemicLens(observations)
    bare_slice = bare.query_historical_slice(
        PARTNER_ENTITY_ID,
        target_time=T_TODAY,
        as_of_cutoff=None,
    )
    assert [o.object_id for o in bare_slice.historical_observations] == [
        o.object_id for o in current.historical_observations
    ]
    assert bare_slice.active_annotations == []
    assert len(current.active_annotations) == 1


def test_g3_knowledge_time_filters_observations_not_just_overlays() -> None:
    """as_of_cutoff 同时约束**知识时间**，不只是图层——这是"忠实还原"的实质。

    T0+100d 时用户根本还没观测到后面 630 天的事实，因此该视图可见的
    Observation 必须显著少于当前视图；否则"还原两年前认知"只是把图层藏起来，
    却把两年后才知道的事实偷偷塞了进去。
    """
    observations = _observations(2_000)
    lens = BiTemporalEpistemicLens(observations, [_judicial_ruling_annotation()])

    past = lens.query_historical_slice(
        PARTNER_ENTITY_ID, target_time=T_TODAY, as_of_cutoff=T_PLUS_100D
    )
    now = lens.query_historical_slice(
        PARTNER_ENTITY_ID, target_time=T_TODAY, as_of_cutoff=None
    )

    assert past.observation_count < now.observation_count
    assert now.observation_count == 2_000
    # 100 天 / 730 天 ≈ 13.7%，允许采样误差
    assert past.observation_count < 2_000 * 0.20
    assert all(obs.learned_at <= T_PLUS_100D for obs in past.historical_observations)


def test_g3_overlay_never_leaks_into_earlier_as_of_view() -> None:
    """注记 learned_at=T_today，任何早于它的 as_of 视图都不得看见它。"""
    lens = BiTemporalEpistemicLens(_observations(200), [_judicial_ruling_annotation()])

    for days in (1, 100, 365, 729):
        cutoff = T0 + timedelta(days=days)
        slice_ = lens.query_historical_slice(
            PARTNER_ENTITY_ID, target_time=cutoff, as_of_cutoff=cutoff
        )
        assert slice_.active_annotations == [], f"T0+{days}d 视图泄漏了未来注记"


# ---------------------------------------------------------------------------
# G4 单跳隔离杜绝雪崩
# ---------------------------------------------------------------------------


def test_g4_five_layer_network_marks_exactly_ten_stale_at_depth_one() -> None:
    edges = _five_layer_edges()
    root = "cog_partner_trust_root"

    # 先确认拓扑确实是工单描述的规模
    layer_sizes = [10, 200, 1000, 2000, 4000]
    assert sum(layer_sizes) == 7210
    assert len(edges) == 7210

    isolator = SingleHopCascadeIsolator(
        DependencyEdge(upstream_node_id=u, dependent_node_id=d) for u, d in edges
    )

    result = isolator.isolate(root, reason_annotation_id=ANNOTATION_ID)

    stale_ids = {node.node_id for node in result.stale_nodes}

    # 严格等于 10 个一级节点
    assert len(stale_ids) == 10
    assert stale_ids == {f"l1_node_{i:05d}" for i in range(10)}
    # 遍历深度严格为 1
    assert result.traversal_depth == 1
    # 不得产生任何大模型重算请求
    assert result.llm_recompute_requests == 0
    # 二级及以后一个都不许被标记
    assert not any(
        node_id.startswith(("l2_", "l3_", "l4_", "l5_")) for node_id in stale_ids
    )
    # 每个 stale 节点都必须带上归因注记
    assert all(
        node.reason_annotation_id == ANNOTATION_ID for node in result.stale_nodes
    )


def test_g4_negative_control_naive_recursion_would_avalanche_210_plus() -> None:
    """负向对照：证明被掐灭的雪崩是真实存在的，而不是假想敌。

    同一张 5 层依赖图上跑朴素递归反向失效，会波及全部 7,210 个下游节点；
    仅前两级就已是工单所说的 10 + 200 = 210 次大模型重算。
    """
    edges = _five_layer_edges()
    root = "cog_partner_trust_root"

    avalanched = _naive_recursive_invalidation(edges, root)
    assert len(avalanched) == 7210
    # 工单口径的 210：一级 + 二级
    first_two_layers = {n for n in avalanched if n.startswith(("l1_", "l2_"))}
    assert len(first_two_layers) == 210

    # 而单跳隔离只碰 10 个
    isolator = SingleHopCascadeIsolator(
        DependencyEdge(upstream_node_id=u, dependent_node_id=d) for u, d in edges
    )
    result = isolator.isolate(root, reason_annotation_id=ANNOTATION_ID)
    assert len(result.stale_nodes) == 10
    assert result.llm_recompute_requests == 0
    # 雪崩规模是单跳的 721 倍
    assert len(avalanched) == len(result.stale_nodes) * 721


def test_g4_isolator_rejects_blank_inputs() -> None:
    isolator = SingleHopCascadeIsolator(
        [DependencyEdge(upstream_node_id="a", dependent_node_id="b")]
    )
    with pytest.raises(ValueError, match="changed_node_id"):
        isolator.isolate("  ", reason_annotation_id=ANNOTATION_ID)
    with pytest.raises(ValueError, match="reason_annotation_id"):
        isolator.isolate("a", reason_annotation_id="")


def test_g4_dependency_edge_rejects_self_loop() -> None:
    with pytest.raises(ValueError):
        DependencyEdge(upstream_node_id="same", dependent_node_id="same")


# ---------------------------------------------------------------------------
# 10000 级压测
# ---------------------------------------------------------------------------


def test_stress_18000_seal_and_verify_within_budget() -> None:
    """18,000 条封存 + 全量复核必须在预算内完成（否则门禁在真实量级不可用）。"""
    conn = sqlite3.connect(":memory:")
    try:
        ledger = FactImmutabilityLedger(conn)

        started = time.perf_counter()
        sealed = ledger.seal_many(_ledger_facts())
        seal_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        report = ledger.verify_fact_integrity()
        verify_ms = (time.perf_counter() - started) * 1000

        assert sealed == OBSERVATION_COUNT
        assert report.all_intact and report.checked == OBSERVATION_COUNT
        # 预算给得宽松（CI 机器差异大），重点是锁住量级：秒级，不是分钟级
        assert seal_ms < 20_000, f"封存 {seal_ms:.0f}ms 超预算"
        assert verify_ms < 20_000, f"复核 {verify_ms:.0f}ms 超预算"
    finally:
        conn.close()


def test_stress_lens_over_18000_observations_both_cutoffs() -> None:
    """18,000 条 Observation 上跑两种 as_of 视图，且历史事实集合完全一致。"""
    observations = _observations()
    lens = BiTemporalEpistemicLens(observations, [_judicial_ruling_annotation()])

    started = time.perf_counter()
    past = lens.query_historical_slice(
        PARTNER_ENTITY_ID, target_time=T_PLUS_100D, as_of_cutoff=T_PLUS_100D
    )
    now = lens.query_historical_slice(
        PARTNER_ENTITY_ID, target_time=T_TODAY, as_of_cutoff=None
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert past.active_annotations == []
    assert len(now.active_annotations) == 1
    assert now.observation_count == OBSERVATION_COUNT
    assert past.observation_count < now.observation_count
    assert elapsed_ms < 60_000, f"双视图查询 {elapsed_ms:.0f}ms 超预算"
