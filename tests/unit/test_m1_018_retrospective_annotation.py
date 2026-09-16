"""M1-018 认知反向传播语义图层契约（老王案）— 万级数据压测验收单测。

高熵商业实战场景（严禁低幼化）：
- 用户 730 天前（T0）与核心技术合伙人签署《Pre-A 轮联合孵化与股权代持对赌协议》；
- 过去 730 天系统累积 18,000 条客观事实 Observation 链：技术评审、商业汇款凭证、
  深夜高压谈判心率变异度(HRV)/皮质醇体征、重大合同、离岸 IP 转移、连带担保、董事会；
- 第 730 天（T_today）司法冻结查封裁定书下达，证实合伙人自设立之初即利用关联
  离岸空壳公司转移核心知识产权并隐匿巨额对外连带担保。

四大硬门禁断言：
1. 历史事实绝对不可变：18,000 条 SHA-256 物理哈希在加注后 100% 一致，
   账本 API 面不存在 UPDATE/DELETE 攻击面；
2. 今天打标签：只写一条 RetrospectiveAnnotation（learned_at = T_today，
   valid_time_range = [T0, T_today]）；
3. 双时间认知透镜：as_of_cutoff = T0+100 天 → active_annotations 必为空
   （忠实还原当时商业信任状态）；as_of_cutoff = None → 18,000 条事实完整保留
   + 外挂重估图层精确叠加；
4. 单跳隔离：5 层万级依赖网络（10/200/1000/3000/6000）反向失效，
   is_stale 严格等于 10 个 1 级节点，遍历深度严格 1，大模型重算 0 次。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.world import (
    AnnotationBudgetExceededError,
    AnnotationConflictError,
    AnnotationRegistry,
    BiTemporalEpistemicLens,
    CascadeIsolationError,
    ImmutableFactLedger,
    LedgerConflictError,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

UTC = timezone.utc

# T0 = 第 0 天：合伙设立；T_TODAY = 第 730 天：司法裁定书下达
T_TODAY = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)
T0 = T_TODAY - timedelta(days=730)
assert (T_TODAY - T0) == timedelta(days=730)

ENTITY = "entity:partner:wang_lao"
ANN_ID = "ann:m1-018:judicial-freeze-fraud-reassessment:2026-09-16"
N_FACTS = 18_000

# 事实类型：高熵商业实战事件（技术评审 / 汇款凭证 / 体征 / 合同 / 离岸转移 / 担保 / 董事会）
_KINDS = (
    "tech_review",
    "tech_review",
    "remittance_voucher",
    "remittance_voucher",
    "biometric_stress",
    "biometric_stress",
    "contract_document",
    "offshore_ip_transfer",
    "guarantee_exposure",
    "board_meeting",
)


def build_18k_observation_chain() -> list[dict]:
    """确定性生成 730 天 × 18,000 条高熵商业事实（前 480 天 25 条/天，其余 24 条/天）。"""
    rng = random.Random(20260916)
    records: list[dict] = []
    for day in range(730):
        per_day = 25 if day < 480 else 24
        for i in range(per_day):
            kind = _KINDS[i % 10]
            base_time = T0 + timedelta(days=day, minutes=6 + i * 5)
            stamp = base_time.strftime("%Y%m%d")
            if kind == "tech_review":
                payload = {
                    "review_id": f"TR-{stamp}-{rng.randint(1000, 9999)}",
                    "module": rng.choice(
                        [
                            "core_recommendation_algorithm_v3",
                            "cross_border_data_pipeline",
                            "equity_holding_ledger_system",
                            "patent_application_docket",
                        ]
                    ),
                    "decision": rng.choice(
                        ["approved_with_risks", "conditional_approval", "deferred_pending_ip_clause"]
                    ),
                    "risk_score": round(rng.uniform(0.35, 0.92), 3),
                    "concern": "核心算法专利权归属条款表述含糊，法务建议补充在先权利确认",
                }
            elif kind == "remittance_voucher":
                payload = {
                    "voucher_id": f"RC-{stamp}-{rng.randint(100000, 999999)}",
                    "amount_cny": rng.randint(100, 5000) * 10000,
                    "currency": "CNY",
                    "beneficiary": rng.choice(
                        ["Nexus Horizon (Cayman) Ltd", "Aurora Trust BVI LLC", "公司主账户"]
                    ),
                    "purpose": "联合孵化运营资金",
                    "swift_ref": "".join(rng.choice("0123456789") for _ in range(12)),
                }
            elif kind == "biometric_stress":
                payload = {
                    "session": "late-night_high_pressure_negotiation",
                    "hour": rng.choice([1, 2, 3, 4, 5]),
                    "hrv_rmssd_ms": round(rng.uniform(14.0, 42.0), 1),
                    "cortisol_ng_ml": round(rng.uniform(12.0, 28.0), 2),
                    "blood_pressure": f"{rng.randint(138, 158)}/{rng.randint(86, 96)}",
                    "context": "合伙人首次提出上调本轮估值并要求当场签署股权代持与对赌条款",
                }
            elif kind == "contract_document":
                payload = {
                    "contract": "Pre-A轮联合孵化与股权代持对赌协议",
                    "clause": rng.choice(
                        [
                            "intellectual_property_ownership_and_transfer",
                            "performance_bet_clauses",
                            "equity_trust_arrangement",
                            "non_compete_and_confidentiality",
                        ]
                    ),
                    "signed_pages": rng.randint(18, 66),
                    "note": "当时用户认为属常规跨境架构安排，未提出异议",
                }
            elif kind == "offshore_ip_transfer":
                payload = {
                    "ip_asset": rng.choice(
                        ["核心推荐算法 v3", "专利申请 PCT-2024-0031", "训练数据资产库"]
                    ),
                    "transfer_to": "Nexus Horizon (Cayman) Ltd",
                    "valuation_cny": rng.randint(2000, 20000) * 10000,
                    "instrument": "intellectual_property_assignment_and_license_contract",
                }
            elif kind == "guarantee_exposure":
                payload = {
                    "guarantee_type": "joint_and_several_liability_guarantee",
                    "principal_cny": rng.randint(5000, 80000) * 10000,
                    "guarantor": "Nexus Horizon (Cayman) Ltd",
                    "lender": rng.choice(["离岸信托", "海外融资租赁公司"]),
                    "disclosed_to_user": False,
                }
            else:  # board_meeting
                payload = {
                    "topic": rng.choice(
                        ["Pre-A 轮交割审查", "知识产权资产清单核对", "离岸架构合规质询"]
                    ),
                    "tension_level": rng.randint(3, 5),
                    "open_issues": rng.randint(2, 9),
                }
            records.append(
                {
                    "fact_id": f"obs:{day:04d}:{i:02d}",
                    "entity_id": ENTITY,
                    "occurred_at": base_time,
                    "kind": kind,
                    "payload": payload,
                }
            )
    assert len(records) == N_FACTS
    return records


def make_annotation(annotation_id: str = ANN_ID) -> RetrospectiveAnnotation:
    """第 730 天司法裁定后的唯一外挂重估图层：今天写、指向过去、不改过去。"""
    return RetrospectiveAnnotation(
        annotation_id=annotation_id,
        target_entity_id=ENTITY,
        semantic_overlay=(
            "司法冻结查封裁定确认：该合伙人自设立之初即利用关联离岸空壳公司转移核心"
            "知识产权，并隐匿巨额对外连带担保（欺诈重估）"
        ),
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=T_TODAY,
        source_statement_ref="doc:judicial_ruling:freeze_seizure:2026-09-16-0001",
    )


ORIGIN = "cognition:partner:wang_lao:core_technology_trustworthy"
_L1, _L2, _L3, _L4, _L5 = 10, 200, 1000, 3000, 6000


def build_dependency_graph():
    """5 层万级依赖网络：10 / 200 / 1000 / 3000 / 6000，共 10,211 节点。"""
    iso = SingleHopCascadeIsolator()
    rng = random.Random(20260916)
    layers: list[list[str]] = []
    parent_of: dict[str, str] = {}
    prev = [ORIGIN]
    for level, size in enumerate((_L1, _L2, _L3, _L4, _L5), start=1):
        current = [f"node:L{level}:{idx:05d}" for idx in range(size)]
        for node in current:
            parent = rng.choice(prev)
            parent_of[node] = parent
            iso.add_dependency(parent, node)
        layers.append(current)
        prev = current
    return iso, layers, parent_of


@pytest.fixture(scope="module")
def ledger_and_records():
    ledger = ImmutableFactLedger()
    records = build_18k_observation_chain()
    ledger.record_facts(records)
    assert ledger.count() == N_FACTS
    return ledger, records


def _lens_with_annotation(ledger) -> BiTemporalEpistemicLens:
    registry = AnnotationRegistry()
    registry.append(make_annotation())
    return BiTemporalEpistemicLens(ledger, registry, clock=lambda: T_TODAY)


# ----------------------------------------------------------------------
# 门禁 1：历史事实绝对不可变（SHA-256 物理哈希 100% 一致，禁止 UPDATE/DELETE）
# ----------------------------------------------------------------------


class TestGate1_HistoricalFactImmutability:
    def test_18k_sha256_hashes_100_percent_unchanged_after_annotation(self, ledger_and_records):
        ledger, _ = ledger_and_records
        before = ledger.all_hashes()
        fingerprint_before = ledger.aggregate_fingerprint()
        assert ledger.count() == N_FACTS
        assert len(before) == N_FACTS
        assert all(len(digest) == 64 for digest in before.values())

        # 新裁定进入：只写一条今天注记 + 双视图查询 —— 历史事实不得受任何触碰
        lens = _lens_with_annotation(ledger)
        lens.query_historical_slice(ENTITY, T0, T_TODAY, as_of_cutoff=None)
        lens.query_historical_slice(
            ENTITY, T0 + timedelta(days=100), as_of_cutoff=T0 + timedelta(days=100)
        )

        after = ledger.all_hashes()
        # 哈希值 100% 保持一致（18,000 / 18,000）
        assert after == before
        assert ledger.aggregate_fingerprint() == fingerprint_before
        # 对封存字节重算哈希：完整性审计全通过
        ok, checked = ledger.verify_integrity()
        assert ok is True and checked == N_FACTS
        # 逐条抽验：视图事实的封存哈希与快照一致
        sample = ledger.facts_for(ENTITY, T0, T_TODAY)
        assert len(sample) == N_FACTS
        for fact in sample[::1000]:
            assert fact.sha256 == before[fact.fact_id]

    def test_ledger_api_surface_has_no_update_delete(self):
        ledger = ImmutableFactLedger()
        forbidden = [
            method
            for method in dir(ledger)
            if not method.startswith("__")
            and any(
                keyword in method.lower()
                for keyword in ("update", "delete", "remove", "erase", "overwrite", "mutate", "replace")
            )
        ]
        # 物理抹掉 SQL UPDATE / DELETE 攻击面
        assert forbidden == []

    def test_duplicate_fact_id_with_different_content_is_rejected(self, ledger_and_records):
        ledger, records = ledger_and_records
        original = records[0]
        with pytest.raises(LedgerConflictError, match="immutable"):
            ledger.record_fact(
                fact_id=original["fact_id"],
                entity_id=ENTITY,
                occurred_at=original["occurred_at"],
                kind=original["kind"],
                payload={"伪造": True},
            )
        assert ledger.count() == N_FACTS  # 拒写后账本原封不动

    def test_identical_reappend_is_idempotent(self, ledger_and_records):
        ledger, records = ledger_and_records
        first = records[0]
        assert ledger.record_fact(**first) == ledger.get_hash(first["fact_id"])
        assert ledger.count() == N_FACTS


# ----------------------------------------------------------------------
# 门禁 2：今天打标签（只写一条 RetrospectiveAnnotation，learned_at = T_today）
# ----------------------------------------------------------------------


class TestGate2_TodayOnlyAnnotation:
    def test_exactly_one_annotation_with_learned_at_t_today(self, ledger_and_records):
        ledger, _ = ledger_and_records
        registry = AnnotationRegistry()
        annotation = registry.append(make_annotation())
        assert registry.count() == 1
        assert annotation.learned_at == T_TODAY  # 只写今天
        assert annotation.target_time_start == T0  # valid_time_range = [T0, T_today]
        assert annotation.target_time_end == T_TODAY
        assert "司法" in annotation.semantic_overlay
        assert "冻结查封" in annotation.semantic_overlay
        assert "欺诈重估" in annotation.semantic_overlay
        # 加注之后历史账本规模不变（标注只加图层，不加事实）
        assert ledger.count() == N_FACTS

    def test_annotation_is_frozen_history_can_not_be_rewritten(self):
        annotation = make_annotation()
        with pytest.raises(ValidationError):
            annotation.learned_at = T0  # 严禁倒写历史
        with pytest.raises(ValidationError):
            annotation.target_time_end = T0 + timedelta(days=1)  # 图层范围不可倒改

    def test_registry_is_append_only(self):
        registry = AnnotationRegistry()
        registry.append(make_annotation())
        with pytest.raises(AnnotationConflictError, match="append-only"):
            registry.append(make_annotation())  # 同一注记不可覆盖/重放为另一版本
        assert registry.count() == 1

    def test_unbounded_annotation_storm_is_rejected_by_budget(self):
        """注记风暴防线：每实体外挂图层带硬预算，超限 fail-closed 拒绝。"""
        registry = AnnotationRegistry(max_per_entity=3)
        for i in range(3):
            registry.append(make_annotation(f"ann:m1-018:reassessment-round-{i}"))
        with pytest.raises(AnnotationBudgetExceededError, match="budget"):
            registry.append(make_annotation("ann:m1-018:reassessment-round-3"))
        assert registry.count() == 3  # 第 4 条被拒，账上恰为 3 条
        # 预算是每实体维度：另一实体的首个注记不受影响
        other_ann = RetrospectiveAnnotation(
            annotation_id="ann:m1-018:other-entity-0",
            target_entity_id="entity:other:counterparty",
            semantic_overlay="独立实体的首次重估",
            target_time_start=T0,
            target_time_end=T_TODAY,
            learned_at=T_TODAY,
            source_statement_ref="doc:judicial_ruling:other:0001",
        )
        registry.append(other_ann)
        assert registry.count() == 4

    def test_registry_stores_independent_immutable_copy(self):
        annotation = make_annotation()
        registry = AnnotationRegistry()
        registry.append(annotation)
        stored = registry.get(ANN_ID)
        assert stored == annotation
        with pytest.raises(ValidationError):
            annotation.semantic_overlay = "篡改"
        assert "篡改" not in registry.get(ANN_ID).semantic_overlay


# ----------------------------------------------------------------------
# 门禁 3：双时间认知透镜（BiTemporalEpistemicLens）
# ----------------------------------------------------------------------


class TestGate3_BiTemporalLens:
    def test_as_of_t0_plus_100d_restores_historical_trust_state(self, ledger_and_records):
        ledger, _ = ledger_and_records
        lens = _lens_with_annotation(ledger)
        cutoff = T0 + timedelta(days=100)
        view = lens.query_historical_slice(ENTITY, cutoff, as_of_cutoff=cutoff)
        assert view.view_kind == "AS_OF"
        # 硬门禁断言：忠实还原历史认知 —— 当时旧王仍是可信合伙人，无任何重估图层
        assert view.active_annotations == ()
        assert view.has_overlay is False
        # 前 100 天事实完整（25 条/天 × 100 天）
        assert view.fact_count == 100 * 25
        assert all(fact.occurred_at <= cutoff for fact in view.facts)
        assert view.facts[0].occurred_at >= T0
        assert view.knowledge_cutoff == cutoff

    def test_current_view_keeps_all_facts_with_precise_overlay(self, ledger_and_records):
        ledger, _ = ledger_and_records
        lens = _lens_with_annotation(ledger)
        view = lens.query_historical_slice(ENTITY, T0, T_TODAY, as_of_cutoff=None)
        assert view.view_kind == "CURRENT"
        # 历史事实完整保留：一条不少
        assert view.fact_count == N_FACTS
        # 外挂重估图层精确叠加：恰好一条，且就是今天的司法裁定注记
        assert len(view.active_annotations) == 1
        assert view.active_annotations[0].annotation_id == ANN_ID
        assert view.active_annotations[0].learned_at == T_TODAY
        assert view.has_overlay is True

    def test_same_slice_seen_through_two_epistemic_moments(self, ledger_and_records):
        """同一历史切片在两个知识时刻：事实完全一致（历史没被改写），只有图层不同。"""
        ledger, _ = ledger_and_records
        lens = _lens_with_annotation(ledger)
        cutoff = T0 + timedelta(days=100)
        as_of_view = lens.query_historical_slice(ENTITY, cutoff, as_of_cutoff=cutoff)
        current_view = lens.query_historical_slice(ENTITY, cutoff, as_of_cutoff=None)
        assert [f.fact_id for f in as_of_view.facts] == [f.fact_id for f in current_view.facts]
        assert as_of_view.active_annotations == ()
        assert len(current_view.active_annotations) == 1

    def test_payload_content_intact_in_current_view(self, ledger_and_records):
        ledger, _ = ledger_and_records
        lens = _lens_with_annotation(ledger)
        view = lens.query_historical_slice(ENTITY, T0, T_TODAY, as_of_cutoff=None)
        kinds = {fact.kind for fact in view.facts}
        # 七类高熵商业事实全部在案
        assert kinds == {"tech_review", "remittance_voucher", "biometric_stress",
                         "contract_document", "offshore_ip_transfer",
                         "guarantee_exposure", "board_meeting"}
        biometric = next(f for f in view.facts if f.kind == "biometric_stress")
        assert "hrv_rmssd_ms" in biometric.payload
        assert "cortisol_ng_ml" in biometric.payload
        voucher = next(f for f in view.facts if f.kind == "remittance_voucher")
        assert voucher.payload["currency"] == "CNY"
        guarantee = next(f for f in view.facts if f.kind == "guarantee_exposure")
        assert guarantee.payload["guarantee_type"] == "joint_and_several_liability_guarantee"

    def test_cutoff_boundary_inclusive_at_exact_learned_at(self, ledger_and_records):
        """知识截止边界语义：cutoff 恰好等于 learned_at 时注记恰在此刻可见；
        早一秒则尚未获知 —— 认知只随时间向前演化，无泄露、无提前。"""
        ledger, _ = ledger_and_records
        lens = _lens_with_annotation(ledger)
        exact = lens.query_historical_slice(ENTITY, T0, T_TODAY, as_of_cutoff=T_TODAY)
        assert len(exact.active_annotations) == 1
        assert exact.active_annotations[0].annotation_id == ANN_ID
        one_second_earlier = lens.query_historical_slice(
            ENTITY, T0, T_TODAY, as_of_cutoff=T_TODAY - timedelta(seconds=1)
        )
        assert one_second_earlier.active_annotations == ()
        assert one_second_earlier.fact_count == N_FACTS  # 事实层不受边界影响

    def test_unknown_entity_returns_empty_view(self, ledger_and_records):
        ledger, _ = ledger_and_records
        lens = _lens_with_annotation(ledger)
        view = lens.query_historical_slice(
            "entity:other:counterparty", T0, T_TODAY, as_of_cutoff=None
        )
        assert view.fact_count == 0
        assert view.active_annotations == ()


# ----------------------------------------------------------------------
# 门禁 4：单跳级联隔离（SingleHopCascadeIsolator，杜绝 210 次 API 雪崩）
# ----------------------------------------------------------------------


class TestGate4_SingleHopIsolation:
    def test_invalidation_marks_exactly_10_first_hop_nodes(self):
        iso, layers, _ = build_dependency_graph()
        assert iso.node_count() == 1 + _L1 + _L2 + _L3 + _L4 + _L5 == 10211

        report = iso.reverse_invalidate(ORIGIN)

        # 硬门禁断言：is_stale=True 的节点严格 = 直接消费该认知的 10 个 1 级节点
        assert len(report.marked_stale) == 10
        assert set(report.marked_stale) == set(layers[0])
        assert iso.stale_nodes() == set(layers[0])
        # 遍历深度严格为 1
        assert report.traversal_depth_reached == 1
        assert report.nodes_visited == 10
        # 大模型重算触发次数严格 0 —— 级联被物理掐灭
        assert report.llm_recompute_triggered == 0
        assert report.cascade_suppressed is True
        assert report.untouched_downstream == _L2 + _L3 + _L4 + _L5 == 10200
        # 逐条验证 2~5 级（10,200 个节点）零污染
        for layer in layers[1:]:
            for node in layer:
                assert not iso.is_stale(node)
        # 旧式无界级联会触发 10 + 200 = 210 次大模型重算 —— 现已全部在抑制范围内
        legacy_avalanche_scope = _L1 + _L2
        assert legacy_avalanche_scope == 210
        assert legacy_avalanche_scope <= report.untouched_downstream

    def test_max_hops_greater_than_one_is_fail_closed(self):
        iso, _, _ = build_dependency_graph()
        with pytest.raises(CascadeIsolationError, match="max_hops must be 1"):
            iso.reverse_invalidate(ORIGIN, max_hops=2)
        with pytest.raises(CascadeIsolationError):
            iso.reverse_invalidate(ORIGIN, max_hops=5)
        # 违宪请求被拒后网络状态零污染
        assert iso.stale_nodes() == frozenset()

    def test_invalidate_leaf_without_consumers_is_safe(self):
        iso, layers, _ = build_dependency_graph()
        leaf = layers[4][0]
        report = iso.reverse_invalidate(leaf)
        assert report.marked_stale == ()
        assert report.traversal_depth_reached == 0
        assert iso.stale_nodes() == frozenset()

    def test_second_hop_stays_clean_until_its_own_single_hop_window(self):
        """2 级节点绝不因 1 跳失效被连带标记；其失效必须等待 1 级节点
        自己的单跳窗口（逐级、可审计、不递归）。"""
        iso, layers, parent_of = build_dependency_graph()
        iso.reverse_invalidate(ORIGIN)
        first_l1 = layers[0][0]
        l2_children = [n for n in layers[1] if parent_of[n] == first_l1]
        assert l2_children  # 200 个 2 级节点分布在 10 个 1 级父节点下，必然非空
        assert all(not iso.is_stale(n) for n in l2_children)  # 2 级零污染

        report = iso.reverse_invalidate(first_l1)  # 1 级节点自己的单跳窗口
        assert set(report.marked_stale) == set(l2_children)
        assert report.traversal_depth_reached == 1
        assert iso.stale_nodes() == set(layers[0]) | set(l2_children)
        # 3 级及以下依然零污染
        for layer in layers[2:]:
            for node in layer:
                assert not iso.is_stale(node)

    def test_unknown_origin_and_self_dependency_are_rejected(self):
        iso, _, _ = build_dependency_graph()
        with pytest.raises(KeyError):
            iso.reverse_invalidate("cognition:unknown:node")
        with pytest.raises(ValueError, match="itself"):
            iso.add_dependency("node:L1:00000", "node:L1:00000")


# ======================================================================
# agent-05 双线收敛增量硬化：learned_at = recorded_at = T_today 对齐
# 与「严禁倒写历史」排序校验（为纯增量断言，不改变队友已合入语义）
# ======================================================================


class TestGate2_R2ContractHardline:
    """工单原文「自身的 learned_at = recorded_at = T_now（今天的时间戳）」
    在本模型上成立；任何倒签到切片终点之前的构造都必须被拒绝。"""

    def test_recorded_at_defaults_align_with_learned_at_today(self):
        annotation = make_annotation()  # 未显式传 recorded_at
        assert annotation.learned_at == T_TODAY
        assert annotation.recorded_at == T_TODAY  # 缺省回填 = learned_at = T_today

    def test_both_timestamps_omitted_share_one_anchor(self):
        annotation = RetrospectiveAnnotation(
            annotation_id="ann:hardline:no-times",
            target_entity_id=ENTITY,
            semantic_overlay="司法查封/欺诈重估",
            target_time_start=T0,
            target_time_end=T0 + timedelta(days=30),  # 已闭合的过去切片
            source_statement_ref="doc:judicial_ruling:freeze:hardline",
        )
        assert annotation.recorded_at == annotation.learned_at
        assert annotation.learned_at >= annotation.target_time_end

    def test_pretending_to_know_before_slice_end_is_rejected(self):
        """假装 T0+100 天就已知晓查封裁定：倒写历史，契约直接拒绝。"""
        with pytest.raises(ValidationError):
            RetrospectiveAnnotation(
                annotation_id="ann:hardline:backdated",
                target_entity_id=ENTITY,
                semantic_overlay="欺诈重估",
                target_time_start=T0,
                target_time_end=T_TODAY,
                learned_at=T0 + timedelta(days=100),
                source_statement_ref="doc:backdated",
            )

    def test_recorded_at_earlier_than_learned_at_is_rejected(self):
        with pytest.raises(ValidationError):
            RetrospectiveAnnotation(
                annotation_id="ann:hardline:recorded-before",
                target_entity_id=ENTITY,
                semantic_overlay="欺诈重估",
                target_time_start=T0,
                target_time_end=T_TODAY,
                learned_at=T_TODAY,
                recorded_at=T_TODAY - timedelta(seconds=1),
                source_statement_ref="doc:recorded-before",
            )

    def test_recorded_at_after_learned_at_ingestion_delay_allowed(self):
        annotation = RetrospectiveAnnotation(
            annotation_id="ann:hardline:ingestion-delay",
            target_entity_id=ENTITY,
            semantic_overlay="司法查封/欺诈重估",
            target_time_start=T0,
            target_time_end=T_TODAY,
            learned_at=T_TODAY,
            recorded_at=T_TODAY + timedelta(hours=2),  # 合法摄入延迟
            source_statement_ref="doc:ingestion-delay",
        )
        assert annotation.recorded_at > annotation.learned_at
