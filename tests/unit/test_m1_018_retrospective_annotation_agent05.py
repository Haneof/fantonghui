"""M1-018 高阶实战验收（Agent-05 并行实现 · 独立命名版测试套件）。

与被合入的战友套件 ``test_m1_018_retrospective_annotation.py`` **并存共置、
互不覆盖**：本套件验收独立模块
``aios_core.world.retrospective_annotation_agent05`` 的全套四门禁契约。

场景基座（严禁低幼化）：用户两年前（T0）与核心技术合伙人签署《Pre-A 轮
联合孵化与股权代持对赌协议》。730 天内系统累积落账 18,000 条客观事实
Observation 链：技术评审纪要、商业汇款凭证、深夜高压谈判时的心率变异度
（HRV）与皮质醇体征、重大合同与股权代持文件。第 730 天（T_today），司法
机关下达冻结查封裁定书，证实该合伙人自设立之初即利用关联离岸空壳公司
转移核心知识产权并隐匿巨额对外连带担保。

四大硬门禁：
1. 历史事实绝对不可变 —— 18,000 条记录 SHA-256 物理哈希在新裁定进入后
   100% 保持一致，存储底座零 SQL UPDATE / DELETE；
2. 今天打标签 —— 只写入一条 RetrospectiveAnnotation，learned_at = T_today，
   valid_time_range = [T0, T_today]；
3. 双时间认知透镜 BiTemporalEpistemicLens —— as_of_cutoff = T0+100 天时
   active_annotations 严格为空；as_of_cutoff = None 时历史完整保留并精确
   叠加司法查封/欺诈重估图层；
4. 单跳隔离杜绝雪崩 SingleHopCascadeIsolator —— 5 层深依赖网（1级×10、
   2级×200、3级×1000），is_stale 严格限于 10 个 1 级节点，遍历深度严格
   为 1，彻底掐灭 210+ 次大模型算力雪崩。
"""
from __future__ import annotations

import json
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.retrospective_annotation_agent05 import (
    BiTemporalEpistemicLens,
    EpistemicWorldLens,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationError,
    SingleHopCascadeIsolator,
    canonical_fact_sha256,
)

# ---------------------------------------------------------------------------
# 场景常量：Pre-A 对赌协议全周期时间轴
# ---------------------------------------------------------------------------

PARTNER_ENTITY = "partner-cto-01"  # 核心技术合伙人实体
FOREIGN_SHELL = "offshore-shell-bvi-aurora"  # 关联离岸空壳公司（案涉）

T0 = datetime(2024, 9, 16, 9, 0, tzinfo=timezone.utc)  # 《Pre-A 协议》签署
DAY_SPAN = 730
T_TODAY = T0 + timedelta(days=DAY_SPAN)  # 第 730 天：司法查封裁定下达日
assert T_TODAY == datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)
CUTOFF_EARLY_TRUST = T0 + timedelta(days=100)  # 当时已知视图：T0+100 天

FACT_TOTAL = 18_000

RECORD_TYPES = (
    "技术评审纪要",
    "商业汇款凭证",
    "深夜高压谈判心率变异度",
    "皮质醇体征采样",
    "重大合同与股权代持文件",
)


def fact_time(i: int) -> datetime:
    """第 i 条事实的客观发生时刻（确定性铺满 730 天）。"""
    return T0 + timedelta(days=i % DAY_SPAN, minutes=(i * 37) % 720)


def fact_payload(i: int) -> dict:
    """第 i 条 Observation 的高熵业务载荷（确定性）。"""
    record_type = RECORD_TYPES[i % len(RECORD_TYPES)]
    base = {"record_type": record_type, "seq": i, "counterparty": PARTNER_ENTITY}
    if record_type == "技术评审纪要":
        base |= {"review_board": f"TRB-{i:05d}", "milestone": f"孵化里程碑{(i % 8) + 1}/8"}
    elif record_type == "商业汇款凭证":
        base |= {
            "voucher_no": f"REM-20240916-{i:06d}",
            "amount_cny": 200_000 + (i % 37) * 1_000,
            "clause": "依据《Pre-A轮联合孵化与股权代持对赌协议》第4.2条如期拨付",
        }
    elif record_type == "深夜高压谈判心率变异度":
        base |= {"hrv_rmssd_ms": 22 + (i % 19), "captured_at": "02:00-04:00 高压谈判窗口"}
    elif record_type == "皮质醇体征采样":
        base |= {"cortisol_nmol_l": 380 + (i % 41), "sample": "saliva"}
    else:
        base |= {"contract_no": f"CTR-PREA-{i:05d}", "subject": "股权代持与知识产权归属条款"}
    return base


def fact_oid(i: int) -> str:
    return f"obs-prea-{i:05d}"


def make_observation(i: int) -> Observation:
    occurred = fact_time(i)
    payload = fact_payload(i)
    return Observation(
        object_id=fact_oid(i),
        subject_id="founder-01",
        revision=1,
        occurred=TemporalExtent.point(occurred),
        learned_at=occurred,
        recorded_at=occurred,
        created_by="m1-018-pre-a",
        source_kind=payload["record_type"],
        modality="json",
        value=payload,
    )


def judicial_annotation() -> RetrospectiveAnnotation:
    """第 730 天唯一允许写入的认知：司法查封 + 欺诈重估注记。"""
    return RetrospectiveAnnotation(
        annotation_id="anno-2026-09-16-judicial-freeze-prea-730d",
        target_entity_id=PARTNER_ENTITY,
        semantic_overlay=(
            "司法冻结查封裁定已生效：合伙人自设立之初借关联离岸空壳公司转移核心知识产权"
            "并隐匿巨额对外连带担保——欺诈重估 / 最高人际警惕"
        ),
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=T_TODAY,
        recorded_at=T_TODAY,
        source_statement_ref="stmt://judiciary/2026-09-16/冻结查封裁定书-[2026]京04执保0916号",
    )


class SealedWorld(NamedTuple):
    lens: BiTemporalEpistemicLens
    snapshot: dict[str, str]  # fact_id -> sha256（挂载注记前的哈希基准）
    times: list[datetime]


@pytest.fixture(scope="module")
def sealed_world() -> SealedWorld:
    """18,000 条事实底账 + 第 730 天唯一一条司法查封注记（模块级只读）。"""
    lens = BiTemporalEpistemicLens()
    for i in range(FACT_TOTAL):
        lens.attach_fact(
            entity_id=PARTNER_ENTITY,
            valid_time_start=fact_time(i),
            payload=fact_payload(i),
            fact_id=fact_oid(i),
        )
    before = lens.hash_snapshot(PARTNER_ENTITY)
    assert len(before) == FACT_TOTAL
    lens.attach_annotation(judicial_annotation())
    # 挂载当刻即断言：底账哈希零漂移。
    assert lens.hash_snapshot(PARTNER_ENTITY) == before
    return SealedWorld(lens=lens, snapshot=before, times=[fact_time(i) for i in range(FACT_TOTAL)])


class SealedStore(NamedTuple):
    store: SQLiteWorldStore
    db_path: str
    snapshot: dict[str, str]


@pytest.fixture(scope="module")
def sealed_store(tmp_path_factory) -> SealedStore:
    """SQLite 存储底座中的 18,000 条 Observation（模块级只读）。"""
    db_path = str(tmp_path_factory.mktemp("prea_store_a05") / "world.db")
    store = SQLiteWorldStore(db_path)
    for chunk in range(FACT_TOTAL // 3_000):
        objects = [make_observation(i) for i in range(chunk * 3_000, (chunk + 1) * 3_000)]
        op = OperationRequest(
            operation_id=str(uuid.uuid4()),
            operation_name="world.commit",
            arguments={},
            expected_world_revision=chunk,
            reason="M1-018 Pre-A 730 天事实链播种（agent-05 独立版）",
            idempotency_key=str(uuid.uuid4()),
        )
        store.commit(objects, op)

    snapshot = {
        p["object_id"]: canonical_fact_sha256(p)
        for p in store.list_payloads(object_type=ObjectType.OBSERVATION)
    }
    assert len(snapshot) == FACT_TOTAL
    return SealedStore(store=store, db_path=db_path, snapshot=snapshot)


def _raw_revision_rows(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM object_revisions").fetchone()[0]
    finally:
        conn.close()


# ===========================================================================
# 硬门禁 1：历史事实绝对不可变（18,000 条 SHA-256 物理哈希 100% 一致）
# ===========================================================================


def test_gate1_18000_observation_sha256_hashes_strictly_invariant(sealed_store) -> None:
    store, db_path, snapshot_before = sealed_store.store, sealed_store.db_path, sealed_store.snapshot
    world_revision_before = store.current_world_revision()
    rows_before = _raw_revision_rows(db_path)

    # 新裁定进入：在透镜侧完成挂载与大量查询（含当前视图渲染）。
    lens = BiTemporalEpistemicLens()
    for i in range(FACT_TOTAL):
        lens.attach_fact(
            entity_id=PARTNER_ENTITY,
            valid_time_start=fact_time(i),
            payload=fact_payload(i),
            fact_id=fact_oid(i),
        )
    lens_hashes_before = lens.hash_snapshot(PARTNER_ENTITY)
    lens.attach_annotation(judicial_annotation())
    for probe in range(0, FACT_TOTAL, 997):
        lens.query_historical_slice(PARTNER_ENTITY, fact_time(probe))
        lens.query_historical_slice(PARTNER_ENTITY, fact_time(probe), as_of_cutoff=CUTOFF_EARLY_TRUST)

    # 门禁：18,000 条物理哈希 100% 一致——存储底座与透镜底账双侧。
    snapshot_after = {
        p["object_id"]: canonical_fact_sha256(p)
        for p in store.list_payloads(object_type=ObjectType.OBSERVATION)
    }
    assert snapshot_after == snapshot_before
    assert lens.hash_snapshot(PARTNER_ENTITY) == lens_hashes_before

    # 存储底座零写入：world_revision 不变、object_revisions 行数不变（无 UPDATE/DELETE/补偿提交）。
    assert store.current_world_revision() == world_revision_before
    assert _raw_revision_rows(db_path) == rows_before == FACT_TOTAL


def test_gate1_hash_invariance_under_repeated_overlay_rendering(sealed_world) -> None:
    lens, snapshot = sealed_world.lens, sealed_world.snapshot
    # 反复渲染当前视图（叠加司法图层）不得扰动任何底层字节。
    for probe in range(0, FACT_TOTAL, 499):
        view = lens.query_historical_slice(PARTNER_ENTITY, fact_time(probe))
        assert view["overlay_count"] == 1
        for f in view["facts"]:
            assert snapshot[f["fact_id"]] == f["sha256"]
    assert lens.hash_snapshot(PARTNER_ENTITY) == snapshot


# ===========================================================================
# 硬门禁 2：今天只写入一条回溯注记，时间戳与指针合法
# ===========================================================================


def test_gate2_exactly_one_annotation_written_today(sealed_world) -> None:
    lens = sealed_world.lens
    annotations = lens.annotations_for(PARTNER_ENTITY)
    assert len(annotations) == 1, "第 730 天只允许存在一条回溯注记"
    assert lens.stats["annotations_attached"] == 1

    annot = annotations[0]
    # learned_at = recorded_at = T_today
    assert annot.learned_at == T_TODAY
    assert annot.recorded_at == T_TODAY
    # valid_time_range = [T0, T_today]，覆盖 730 天对赌全周期
    assert annot.target_time_start == T0
    assert annot.target_time_end == T_TODAY
    # 认知单向向前：730 天前的任何一天都绝不可能知道今天的裁定。
    assert annot.learned_at > T0 + timedelta(days=729)
    assert "离岸空壳" in annot.semantic_overlay
    assert "欺诈重估" in annot.semantic_overlay
    assert "冻结查封裁定书" in annot.source_statement_ref
    # 全部 18,000 个历史时刻都落在注记指针覆盖范围内。
    assert all(annot.covers(t) for t in sealed_world.times)


def test_gate2_pretending_to_know_earlier_is_unconstitutional() -> None:
    """假装在 T0+100 天就已知道查封裁定：契约直接拒绝（严禁倒写历史）。"""
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(
            annotation_id="anno-backdated",
            target_entity_id=PARTNER_ENTITY,
            semantic_overlay="欺诈重估",
            target_time_start=T0,
            target_time_end=T_TODAY,
            learned_at=CUTOFF_EARLY_TRUST,  # learned_at < target_time_end
            source_statement_ref="stmt://x",
        )


# ===========================================================================
# 硬门禁 3：双时间认知透镜 BiTemporalEpistemicLens
# ===========================================================================


def _first_index(record_type: str, lo_day: int, hi_day: int) -> int:
    for i in range(FACT_TOTAL):
        if i % len(RECORD_TYPES) == RECORD_TYPES.index(record_type) and lo_day <= i % DAY_SPAN <= hi_day:
            return i
    raise AssertionError("scenario builder changed; index not found")


def test_gate3_as_of_cutoff_reproduces_business_trust_state(sealed_world) -> None:
    """as_of_cutoff = T0+100 天：精准还原当时的商业信任状态，图层严格为空。"""
    lens, times = sealed_world.lens, sealed_world.times
    voucher_idx = _first_index("商业汇款凭证", 20, 40)
    contract_idx = _first_index("重大合同与股权代持文件", 20, 40)

    for idx in (voucher_idx, contract_idx):
        view = lens.query_historical_slice(
            PARTNER_ENTITY, times[idx], as_of_cutoff=CUTOFF_EARLY_TRUST
        )
        assert view["view_mode"] == "as_of_historical"
        assert view["as_of_cutoff"] is not None
        # 硬断言：当时已知的认知里，司法查封/欺诈重估严格不可见。
        assert view["active_annotations"] == []
        assert view["overlay_count"] == 0
        # 历史信任状态完整重现：当初的汇款凭证/代持合同原样在场。
        assert view["fact_count"] >= 1
        payload_blob = json.dumps([f["payload"] for f in view["facts"]], ensure_ascii=False)
        assert view["facts"][0]["sha256"] == sealed_world.snapshot[view["facts"][0]["fact_id"]]
        assert "PREA" in payload_blob or "REM-" in payload_blob

    # 730 天内全时域扫描：任何早于 T_today 的 cutoff 都零泄露。
    rng = random.Random(730)
    for _ in range(300):
        t = times[rng.randrange(FACT_TOTAL)]
        cutoff = T0 + timedelta(days=rng.randrange(DAY_SPAN))  # 历史内任意一天
        view = lens.query_historical_slice(PARTNER_ENTITY, t, as_of_cutoff=cutoff)
        assert view["active_annotations"] == []


def test_gate3_current_view_precisely_overlays_judicial_layer(sealed_world) -> None:
    """as_of_cutoff = None：历史完整保留 + 精确叠加司法查封/欺诈重估图层。"""
    lens, times, snapshot = sealed_world.lens, sealed_world.times, sealed_world.snapshot
    voucher_idx = _first_index("商业汇款凭证", 20, 40)
    hrv_idx = _first_index("深夜高压谈判心率变异度", 500, 560)

    for idx in (voucher_idx, hrv_idx):
        as_of = lens.query_historical_slice(
            PARTNER_ENTITY, times[idx], as_of_cutoff=CUTOFF_EARLY_TRUST
        )
        current = lens.query_historical_slice(PARTNER_ENTITY, times[idx])
        assert current["view_mode"] == "current_overlay"
        assert current["overlay_count"] == 1

        overlay = current["active_annotations"][0]
        assert overlay["annotation_id"] == "anno-2026-09-16-judicial-freeze-prea-730d"
        assert overlay["rendered_as"] == "warning_marker"
        assert "冻结查封" in overlay["semantic_overlay"] or "欺诈重估" in overlay["semantic_overlay"]
        # 图层时间戳属于今天；指针指向 [T0, T_today] 全周期。
        assert overlay["learned_at"].startswith("2026-09-16")
        assert overlay["target_time_start"].startswith("2024-09-16")
        assert overlay["source_statement_ref"].endswith("0916号")

        # 叠加图层后，同一切片的历史事实与 as-of 视图逐比特一致。
        assert [f["sha256"] for f in current["facts"]] == [f["sha256"] for f in as_of["facts"]]
        assert [f["payload"] for f in current["facts"]] == [f["payload"] for f in as_of["facts"]]
        for f in current["facts"]:
            assert snapshot[f["fact_id"]] == f["sha256"]

        # overlays 为一号工单字段别名，内容与 active_annotations 完全一致。
        assert current["overlays"] == current["active_annotations"]


def test_gate3_cutoff_boundary_inclusive_at_exact_ruling_time(sealed_world) -> None:
    lens, times = sealed_world.lens, sealed_world.times
    t = times[0]
    at_exact = lens.query_historical_slice(PARTNER_ENTITY, t, as_of_cutoff=T_TODAY)
    assert at_exact["overlay_count"] == 1  # learned_at == cutoff：当刻已知
    just_before = lens.query_historical_slice(
        PARTNER_ENTITY, t, as_of_cutoff=T_TODAY - timedelta(microseconds=1)
    )
    assert just_before["active_annotations"] == []


# ===========================================================================
# 硬门禁 4：SingleHopCascadeIsolator 单跳隔离杜绝雪崩
# ---------------------------------------------------------------------------
# 依赖网络：5 层深度。1 级直接消费者 10 个；2 级 200；3 级 1,000；
# 4 级 2,000；5 级 7,000。全网 10,211 个节点，10,210 条有向边。
# 朴素递归失效会卷入 L1+L2 共 210 个重算节点（全网闭合 10,210 个）——
# 大模型算力雪崩。隔离器必须把 is_stale 严格限制在 10 个 1 级节点。
# ===========================================================================

SOURCE_NODE = "cognition:partner-cto-01:integrity-profile"
L1 = [f"derive.partnership-month-summary.l1-{k:02d}" for k in range(10)]
L2 = [f"aggregate.quarterly-derisk-review.l2-{k:03d}" for k in range(200)]
L3 = [f"evidence-chain.deep-reputation-derivation.l3-{k:04d}" for k in range(1000)]
L4 = [f"dimension-sample.trust-baseline.l4-{k:04d}" for k in range(2000)]
L5 = [f"narrative.long-horizon-founder-report.l5-{k:04d}" for k in range(7000)]


def _build_dependency_web() -> SingleHopCascadeIsolator:
    iso = SingleHopCascadeIsolator()
    iso.add_dependencies((c, SOURCE_NODE) for c in L1)
    iso.add_dependencies((L2[k], L1[k % 10]) for k in range(200))
    iso.add_dependencies((L3[k], L2[k % 200]) for k in range(1000))
    iso.add_dependencies((L4[k], L3[k % 1000]) for k in range(2000))
    iso.add_dependencies((L5[k], L4[k % 2000]) for k in range(7000))
    return iso


def _naive_full_cascade_closure(iso: SingleHopCascadeIsolator, source: str) -> set[str]:
    """测试侧独立 BFS：量化朴素递归失效会卷入的全部节点（雪崩规模取证）。"""
    seen: set[str] = set()
    frontier = [source]
    while frontier:
        nxt: list[str] = []
        for node in frontier:
            for consumer in iso.direct_consumers_of(node):
                if consumer not in seen:
                    seen.add(consumer)
                    nxt.append(consumer)
        frontier = nxt
    return seen


def test_gate4_reverse_invalidation_marks_exactly_ten_l1_nodes() -> None:
    iso = _build_dependency_web()
    assert iso.stats["edges"] == 10 + 200 + 1000 + 2000 + 7000

    report = iso.invalidate(SOURCE_NODE)

    # 硬断言 1：is_stale=True 的节点严格等于 10 个一级直接消费者。
    assert report.stale_count == 10
    assert report.stale_node_ids == tuple(sorted(L1))
    assert iso.stale_nodes() == tuple(sorted(L1))
    for node in L1:
        assert iso.is_stale(node)
    # 2..5 级任何节点绝不被级联污染。
    for node in (*L2, *L3, *L4, *L5):
        assert not iso.is_stale(node)

    # 硬断言 2：遍历深度严格为 1，触达节点 11（源 + 10），LLM 重算作业恒 0。
    assert report.max_traversal_depth == 1
    assert report.nodes_touched == 11
    assert report.llm_recompute_jobs_executed == 0

    # 雪崩取证：朴素递归会卷入 10,210 个节点（含工单量化的 L1+L2=210 个
    # 重算节点）；隔离器将其全部挡在门外——被拯救的重算规模 10,200 个，
    # 远超工单量化的 210 次。
    closure = _naive_full_cascade_closure(iso, SOURCE_NODE)
    assert len(closure) == 10 + 200 + 1000 + 2000 + 7000 == 10_210
    assert len(L1) + len(L2) == 210  # 工单量化的雪崩阶数
    rescued = len(closure) - report.stale_count
    assert rescued == 10_200 >= 210


def test_gate4_lazy_rerender_and_resolve_flow() -> None:
    """stale 节点不立即重算：未来被真实需要时各自懒加载重写并摘牌。"""
    iso = _build_dependency_web()
    report = iso.invalidate(SOURCE_NODE)
    assert report.llm_recompute_jobs_executed == 0

    target = L1[0]
    assert iso.is_stale(target)
    iso.mark_resolved(target)  # 模拟该 1 级节点按需懒重写完成
    assert not iso.is_stale(target)
    assert len(iso.stale_nodes()) == 9
    # 摘牌不影响 2 级及以下：它们从未被标记过。
    assert not any(iso.is_stale(n) for n in (*L2, *L3, *L4, *L5))


def test_gate4_invalidation_budget_rejects_marking_storm() -> None:
    iso = _build_dependency_web()
    capped = SingleHopCascadeIsolator(max_marks_per_invalidation=5)
    capped.add_dependencies((c, SOURCE_NODE) for c in L1)
    with pytest.raises(RetrospectiveAnnotationError) as excinfo:
        capped.invalidate(SOURCE_NODE)
    assert excinfo.value.code == ErrorCode.BUDGET_EXHAUSTED
    assert capped.stale_nodes() == ()  # 拒绝是原子的：半个节点都不许被标记

    # 未设预算的隔离器对未知源为合法空操作。
    empty_report = iso.invalidate("cognition:unknown")
    assert empty_report.stale_count == 0
    assert empty_report.max_traversal_depth == 0
    assert empty_report.nodes_touched == 1


def test_gate4_isolator_input_validation() -> None:
    iso = SingleHopCascadeIsolator()
    with pytest.raises(RetrospectiveAnnotationError):
        iso.add_dependency("node-a", "node-a")  # 自环
    with pytest.raises(RetrospectiveAnnotationError):
        iso.add_dependency(" ", SOURCE_NODE)
    with pytest.raises(RetrospectiveAnnotationError):
        iso.invalidate("")
    with pytest.raises(RetrospectiveAnnotationError):
        SingleHopCascadeIsolator(max_marks_per_invalidation=0)


# ===========================================================================
# 10,000 级数据压测：万级查询下哈希稳定、计数有界、渲染确定
# ===========================================================================


def test_stress_10000_queries_hashes_and_counters_stay_exact(sealed_world) -> None:
    lens, times, snapshot = sealed_world.lens, sealed_world.times, sealed_world.snapshot
    stats_before = lens.stats

    rng = random.Random(2026_0916)
    query_total = 10_000
    expected_overlay_hits = 0
    expected_fact_hits = 0
    for _ in range(query_total):
        t = times[rng.randrange(FACT_TOTAL)]
        r = rng.random()
        if r < 0.4:
            cutoff = None
        elif r < 0.6:
            cutoff = CUTOFF_EARLY_TRUST
        elif r < 0.8:
            cutoff = T0 + timedelta(days=rng.randrange(DAY_SPAN))
        else:
            cutoff = T_TODAY - timedelta(seconds=1)
        view = lens.query_historical_slice(PARTNER_ENTITY, t, as_of_cutoff=cutoff)
        expected_overlay_hits += view["overlay_count"]
        expected_fact_hits += view["fact_count"]
        # 当前视图恒恰 1 层；任何历史 cutoff 恒 0 层（learned_at = T_today）。
        assert view["overlay_count"] == (1 if cutoff is None else 0)
        for f in view["facts"]:
            assert snapshot[f["fact_id"]] == f["sha256"]

    stats_after = lens.stats
    assert stats_after["queries"] - stats_before["queries"] == query_total
    assert stats_after["overlay_hits_total"] - stats_before["overlay_hits_total"] == expected_overlay_hits
    assert stats_after["fact_hits_total"] - stats_before["fact_hits_total"] == expected_fact_hits
    # 万级查询压测后：底账与注记账零漂移（无级联落账、无隐藏重算）。
    assert stats_after["annotations_attached"] == 1
    assert stats_after["facts_attached"] == FACT_TOTAL
    assert lens.hash_snapshot(PARTNER_ENTITY) == snapshot


def test_stress_10000_node_web_invalidation_stays_single_hop() -> None:
    """万级依赖网上重复失效：每次报告均深度 1、触达 11、作业 0，且幂等。"""
    iso = _build_dependency_web()  # 10,211 节点
    for _ in range(200):
        report = iso.invalidate(SOURCE_NODE)
        assert report.stale_count == 10
        assert report.max_traversal_depth == 1
        assert report.nodes_touched == 11
        assert report.llm_recompute_jobs_executed == 0
    assert iso.stale_nodes() == tuple(sorted(L1))
    assert iso.stats["invalidations"] == 200


# ===========================================================================
# 通用契约防线（沿用并强化 R1 工单断言集）
# ===========================================================================


def test_contract_time_and_shape_validation() -> None:
    base = dict(
        annotation_id="anno-x",
        target_entity_id=PARTNER_ENTITY,
        semantic_overlay="司法查封/欺诈重估",
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=T_TODAY,
        recorded_at=T_TODAY,
        source_statement_ref="stmt://judiciary/x",
    )
    with pytest.raises(ValidationError):  # 无时区
        RetrospectiveAnnotation(**{**base, "target_time_start": T0.replace(tzinfo=None)})
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "learned_at": T_TODAY.replace(tzinfo=None)})
    with pytest.raises(ValidationError):  # 终点早于起点
        RetrospectiveAnnotation(**{**base, "target_time_end": T0 - timedelta(days=1)})
    with pytest.raises(ValidationError):  # recorded_at 早于 learned_at
        RetrospectiveAnnotation(**{**base, "recorded_at": T_TODAY - timedelta(seconds=1)})
    with pytest.raises(ValidationError):  # 空白图层
        RetrospectiveAnnotation(**{**base, "semantic_overlay": "   "})
    with pytest.raises(ValidationError):  # 未知字段（如倒写历史开关）
        RetrospectiveAnnotation(**{**base, "rewrite_history": True})


def test_idempotent_replay_and_conflict_rejected(sealed_world) -> None:
    lens = sealed_world.lens
    annot = judicial_annotation()
    # 与 fixture 中完全相同内容的重复挂载：幂等无操作。
    assert lens.attach_annotation(annot) == annot.annotation_id
    assert len(lens.annotations_for(PARTNER_ENTITY)) == 1

    conflicting = RetrospectiveAnnotation(
        annotation_id=annot.annotation_id,
        target_entity_id=PARTNER_ENTITY,
        semantic_overlay="被篡改的图层：试图淡化担保风险",
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=T_TODAY,
        recorded_at=T_TODAY,
        source_statement_ref="stmt://x",
    )
    with pytest.raises(RetrospectiveAnnotationError) as excinfo:
        lens.attach_annotation(conflicting)
    assert excinfo.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    assert len(lens.annotations_for(PARTNER_ENTITY)) == 1

    with pytest.raises(TypeError):
        lens.attach_annotation("不是注记")  # type: ignore[arg-type]


def test_single_hop_no_bleed_into_shell_company_or_other_entities(sealed_world) -> None:
    lens = sealed_world.lens
    # 离岸空壳与其他实体不被级联重标：单跳只命中指针直接指向的实体切片。
    for entity in (FOREIGN_SHELL, "co-founder-02", "lead-investor-03"):
        view = lens.query_historical_slice(entity, T0 + timedelta(days=365))
        assert view["active_annotations"] == []
        assert view["facts"] == []
    # 指针区间之外的历史时刻（签署协议前夜）：不渲染任何图层。
    before_signing = lens.query_historical_slice(PARTNER_ENTITY, T0 - timedelta(hours=1))
    assert before_signing["active_annotations"] == []


def test_view_is_fresh_copy_and_ledger_tamper_isolated() -> None:
    caller_payload = {"contract_no": "CTR-PREA-00001", "clause": "知识产权归属创始团队"}
    lens = BiTemporalEpistemicLens()
    fid = lens.attach_fact(
        entity_id=PARTNER_ENTITY, valid_time_start=T0, payload=caller_payload, fact_id="fact-contract-1"
    )
    caller_payload["clause"] = "被倒写：知识产权归空壳公司"

    view = lens.query_historical_slice(PARTNER_ENTITY, T0)
    assert view["facts"][0]["payload"]["clause"] == "知识产权归属创始团队"
    assert view["facts"][0]["sha256"] == canonical_fact_sha256(
        {"contract_no": "CTR-PREA-00001", "clause": "知识产权归属创始团队"}
    )
    assert view["facts"][0]["fact_id"] == fid

    view["facts"][0]["payload"]["clause"] = "二次倒写"
    again = lens.query_historical_slice(PARTNER_ENTITY, T0)
    assert again["facts"][0]["payload"]["clause"] == "知识产权归属创始团队"


def test_rendering_deterministic_and_r1_alias_intact(sealed_world) -> None:
    # 一号工单冻结类别名继续可用（向后兼容）。
    assert EpistemicWorldLens is BiTemporalEpistemicLens
    lens, times = sealed_world.lens, sealed_world.times
    v1 = lens.query_historical_slice(PARTNER_ENTITY, times[123])
    v2 = lens.query_historical_slice(PARTNER_ENTITY, times[123])
    assert json.dumps(v1, sort_keys=True, ensure_ascii=False) == json.dumps(
        v2, sort_keys=True, ensure_ascii=False
    )


def test_query_argument_validation(sealed_world) -> None:
    lens, times = sealed_world.lens, sealed_world.times
    with pytest.raises(RetrospectiveAnnotationError) as e1:
        lens.query_historical_slice("  ", times[0])
    assert e1.value.code == ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ValueError):
        lens.query_historical_slice(PARTNER_ENTITY, times[0].replace(tzinfo=None))
    with pytest.raises(ValueError):
        lens.query_historical_slice(PARTNER_ENTITY, times[0], as_of_cutoff=T_TODAY.replace(tzinfo=None))
