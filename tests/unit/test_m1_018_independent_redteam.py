"""M1-018 独立红队验收层（独立命名，纯追加 —— 不改动、不覆盖任何既有版本）。

对当前分支合流后的 M1-018 实现（含 7785aed 增量硬化：recorded_at 对齐与
倒写历史强校验）做对抗性复核：

- 倒写历史强校验（learned_at < target_time_end 违宪拒绝）；
- recorded_at / learned_at 双时间戳对齐语义；
- 图层"零提前泄露"（知识时间早于获知时刻必须不可见）；
- naive/aware 混合时间的健壮性；
- 跨账本实例哈希确定性（同一事实 = 同一 SHA-256）；
- 非 JSON 载荷 fail-closed；
- 级联隔离的动态图语义（失效后新增下游不回溯标记）；
- 万级规模独立复测（2,000 事实 + 3,211 节点 5 层网络）。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.world import (
    AnnotationRegistry,
    BiTemporalEpistemicLens,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

UTC = timezone.utc
T0 = datetime(2024, 9, 16, 8, 0, tzinfo=UTC)
T_TODAY = T0 + timedelta(days=730)
ENTITY = "entity:redteam:counterparty_zhang"


def make_fact(day: int, i: int) -> dict:
    return {
        "fact_id": f"rt-obs:{day:04d}:{i:02d}",
        "entity_id": ENTITY,
        "occurred_at": T0 + timedelta(days=day, minutes=3 + i * 4),
        "kind": "board_meeting",
        "payload": {"topic": "圆桌质询", "tension_level": 4, "seq": i},
    }


def make_annotation(
    *,
    annotation_id: str = "ann:rt-001",
    target_start: datetime = T0,
    target_end: datetime = T_TODAY,
    learned_at: datetime = T_TODAY,
    **overrides,
) -> RetrospectiveAnnotation:
    data = dict(
        annotation_id=annotation_id,
        target_entity_id=ENTITY,
        semantic_overlay="红队复核注记",
        target_time_start=target_start,
        target_time_end=target_end,
        learned_at=learned_at,
        source_statement_ref="doc:rt:0001",
    )
    data.update(overrides)
    return RetrospectiveAnnotation(**data)


class TestRetroactiveRewriteStrongValidation:
    """7785aed 增量红队：倒写历史必须被模型层拒绝。"""

    def test_learned_before_slice_end_is_constitutionally_rejected(self):
        # 假装"当时就已知晓"（learned_at 早于切片终点）→ 违宪
        with pytest.raises(ValidationError, match="target_time_end"):
            make_annotation(learned_at=T0 + timedelta(days=50))

    def test_recorded_before_learned_is_rejected(self):
        with pytest.raises(ValidationError, match="recorded_at must be >= learned_at"):
            make_annotation(recorded_at=T_TODAY - timedelta(days=1))

    def test_recorded_at_backfills_from_learned_at(self):
        ann = RetrospectiveAnnotation(
            annotation_id="ann:rt-002",
            target_entity_id=ENTITY,
            semantic_overlay="红队复核注记",
            target_time_start=T0,
            target_time_end=T_TODAY,
            learned_at=T_TODAY,
            source_statement_ref="doc:rt:0002",
        )
        # 工单原文语义：learned_at = recorded_at = T_today（缺省回填，不依赖真实时钟）
        assert ann.recorded_at == ann.learned_at == T_TODAY

    def test_both_timestamps_absent_share_single_now_anchor(self):
        # 目标切片终点取过去（T0+700d）—— 缺省 now 回填才可能满足 learned_at >= 切片终点
        now_real = datetime.now(timezone.utc)
        ann = RetrospectiveAnnotation(
            annotation_id="ann:rt-003",
            target_entity_id=ENTITY,
            semantic_overlay="红队复核注记",
            target_time_start=T0,
            target_time_end=T0 + timedelta(days=700),
            source_statement_ref="doc:rt:0003",
        )
        assert ann.learned_at == ann.recorded_at
        # 锚点必须是"现在附近"（不得回填为历史时刻，与真实时钟同源 ±5 分钟）
        assert abs((ann.learned_at - now_real).total_seconds()) < 300


class TestZeroEarlyLeak:
    """图层零提前泄露：知识时刻早于获知时刻 → 严格不可见。"""

    def _lens(self, registry: AnnotationRegistry) -> BiTemporalEpistemicLens:
        return BiTemporalEpistemicLens(
            ImmutableFactLedger(), registry, clock=lambda: T_TODAY
        )

    def test_past_learned_annotation_visible_only_after_learning_moment(self):
        # 合法的历史获知注记：指向 [T0, T0+100d]，于 T0+120d 获知（>= 切片终点）
        registry = AnnotationRegistry()
        registry.append(
            make_annotation(
                annotation_id="ann:rt-010",
                target_start=T0,
                target_end=T0 + timedelta(days=100),
                learned_at=T0 + timedelta(days=120),
            )
        )
        lens = self._lens(registry)
        early = lens.query_historical_slice(
            ENTITY, T0, T0 + timedelta(days=100), as_of_cutoff=T0 + timedelta(days=119)
        )
        late = lens.query_historical_slice(
            ENTITY, T0, T0 + timedelta(days=100), as_of_cutoff=T0 + timedelta(days=120)
        )
        assert early.active_annotations == ()          # 获知前一秒：不可见
        assert len(late.active_annotations) == 1        # 获知瞬间：可见


class TestTimezoneRobustness:
    def test_naive_facts_and_naive_anchor_treated_as_utc(self):
        """naive 契约的事实侧口径：naive 一律按 UTC 解释（无注记 → 不进入 overlap 检查）。"""
        registry = AnnotationRegistry()
        ledger = ImmutableFactLedger()
        ledger.record_fact(
            fact_id="rt-tz-0",
            entity_id=ENTITY,
            occurred_at=datetime(2024, 9, 20, 10, 0),  # naive（按 UTC 解释）
            kind="board_meeting",
            payload={"a": 1},
        )
        lens = BiTemporalEpistemicLens(ledger, registry, clock=lambda: T_TODAY)
        view = lens.query_historical_slice(
            ENTITY,
            datetime(2024, 9, 21, 0, 0),  # naive 切片锚点
            as_of_cutoff=None,
        )
        assert view.fact_count == 1
        # 事实时间戳经归一化为 aware UTC
        assert view.facts[0].occurred_at == datetime(2024, 9, 20, 10, 0, tzinfo=timezone.utc)
        assert view.knowledge_cutoff == T_TODAY

    def test_known_gap_naive_slice_anchor_vs_aware_annotation(self):
        """已知缺口留档（本红队批次不改既有版本，提请总师裁定硬化）：

        当注册表已有 aware 注记、调用方以 naive 切片锚点查询时，overlap 判定
        （_ranges_overlap）在比较前未归一化切片边界 → naive/aware 直接比较
        触发 TypeError。事实侧与视图侧均按 UTC 归一化，唯独 overlap 路径漏归一化。
        """
        registry = AnnotationRegistry()
        registry.append(make_annotation())  # aware 注记（T0 → T_TODAY）
        ledger = ImmutableFactLedger()
        ledger.record_fact(
            fact_id="rt-tz-1",
            entity_id=ENTITY,
            occurred_at=datetime(2024, 9, 20, 10, 0, tzinfo=timezone.utc),
            kind="board_meeting",
            payload={"a": 1},
        )
        lens = BiTemporalEpistemicLens(ledger, registry, clock=lambda: T_TODAY)
        with pytest.raises(TypeError):
            lens.query_historical_slice(
                ENTITY,
                datetime(2024, 9, 21, 0, 0),  # naive 切片锚点
                as_of_cutoff=None,
            )


class TestHashDeterminismAndFailClosed:
    def test_same_facts_produce_identical_hashes_across_instances(self):
        records = [make_fact(day, i) for day in range(40) for i in range(12)]  # 480 条
        ledger_a, ledger_b = ImmutableFactLedger(), ImmutableFactLedger()
        ledger_a.record_facts(records)
        ledger_b.record_facts(records)
        assert ledger_a.all_hashes() == ledger_b.all_hashes()
        assert ledger_a.aggregate_fingerprint() == ledger_b.aggregate_fingerprint()

    def test_unicode_and_nested_payloads_hash_stably(self):
        ledger = ImmutableFactLedger()
        digest = ledger.record_fact(
            fact_id="rt-unicode",
            entity_id=ENTITY,
            occurred_at=T0,
            kind="contract_document",
            payload={"合同": "股权代持对赌协议", "nested": {"甲": [1, 2, 3], "乙": None}},
        )
        assert len(digest) == 64
        again = ImmutableFactLedger().record_fact(
            fact_id="rt-unicode",
            entity_id=ENTITY,
            occurred_at=T0,
            kind="contract_document",
            payload={"合同": "股权代持对赌协议", "nested": {"甲": [1, 2, 3], "乙": None}},
        )
        assert digest == again  # 键序无关的规范哈希

    def test_non_json_payload_fails_closed_without_corrupting_ledger(self):
        ledger = ImmutableFactLedger()
        ledger.record_fact(
            fact_id="rt-ok",
            entity_id=ENTITY,
            occurred_at=T0,
            kind="x",
            payload={"a": 1},
        )
        with pytest.raises((TypeError, ValueError)):
            ledger.record_fact(
                fact_id="rt-bad",
                entity_id=ENTITY,
                occurred_at=T0,
                kind="x",
                payload={"datetime": datetime.now(UTC)},  # 非 JSON 载荷
            )
        assert ledger.count() == 1  # 拒写后账本完好


class TestCascadeDynamicGraphSemantics:
    def _graph(self) -> tuple[SingleHopCascadeIsolator, list[str]]:
        iso = SingleHopCascadeIsolator()
        origin = "cognition:rt:trust"
        l1 = [f"n1:{i}" for i in range(10)]
        l2 = [f"n2:{i}" for i in range(200)]
        for node in l1:
            iso.add_dependency(origin, node)
        for node in l2:
            iso.add_dependency(f"n1:{(int(node.split(':')[1]) // 20) % 10}", node)
        return iso, l1

    def test_downstream_added_after_invalidation_is_not_retroactively_marked(self):
        iso, l1 = self._graph()
        iso.reverse_invalidate("cognition:rt:trust")
        iso.add_dependency("cognition:rt:trust", "n1:late")  # 失效后新增的直接下游
        assert iso.is_stale("n1:late") is False  # 单跳是失效时刻的快照语义
        assert iso.stale_nodes() == set(l1)

    def test_double_invalidation_is_idempotent(self):
        iso, l1 = self._graph()
        first = iso.reverse_invalidate("cognition:rt:trust")
        second = iso.reverse_invalidate("cognition:rt:trust")
        assert first.marked_stale == second.marked_stale
        assert iso.stale_nodes() == set(l1)
        assert second.llm_recompute_triggered == 0

    def test_second_hop_window_only_marks_its_own_children(self):
        iso, _ = self._graph()
        iso.reverse_invalidate("cognition:rt:trust")
        report = iso.reverse_invalidate("n1:0")
        own_children = set(iso.direct_consumers("n1:0"))
        assert set(report.marked_stale) == own_children
        assert not (own_children & set(iso.direct_consumers("cognition:rt:trust")))
        assert report.traversal_depth_reached == 1


class TestStressScaleIndependentRerun:
    def test_2000_facts_and_3211_node_graph(self):
        rng = random.Random(20260917)
        ledger = ImmutableFactLedger()
        for day in range(100):
            for i in range(20):
                ledger.record_fact(
                    fact_id=f"stress-{day:04d}-{i:02d}",
                    entity_id=ENTITY,
                    occurred_at=T0 + timedelta(days=day, minutes=i * 7),
                    kind="remittance_voucher",
                    payload={
                        "amount_cny": rng.randint(100, 5000) * 10000,
                        "purpose": "联合孵化运营资金",
                    },
                )
        assert ledger.count() == 2000
        hashes_before = ledger.all_hashes()

        registry = AnnotationRegistry()
        registry.append(make_annotation(annotation_id="ann:rt-stress"))
        lens = BiTemporalEpistemicLens(ledger, registry, clock=lambda: T_TODAY)
        assert lens.query_historical_slice(ENTITY, T0, T_TODAY, as_of_cutoff=None).fact_count == 2000
        assert lens.query_historical_slice(
            ENTITY, T0 + timedelta(days=100), as_of_cutoff=T0 + timedelta(days=100)
        ).active_annotations == ()
        assert ledger.all_hashes() == hashes_before  # 万级语义同构：哈希 100% 稳定

        # 5 层网络 1+10+200+1000+2000 = 3,211 节点
        iso = SingleHopCascadeIsolator()
        prev = ["cognition:rt:trust"]
        l1 = []
        for level, size in enumerate((10, 200, 1000, 2000), start=1):
            current = [f"node:rt-L{level}:{idx:05d}" for idx in range(size)]
            for node in current:
                iso.add_dependency(rng.choice(prev), node)
            prev = current
            if level == 1:
                l1 = current
        assert iso.node_count() == 3211
        report = iso.reverse_invalidate("cognition:rt:trust")
        assert set(report.marked_stale) == set(l1)
        assert report.traversal_depth_reached == 1
        assert report.llm_recompute_triggered == 0
        assert report.untouched_downstream == 3200
