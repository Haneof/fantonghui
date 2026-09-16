"""双透镜虚拟索引投影器单元测试（不可变账本 + 单跳隔离，拒绝写死样例）。"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.tools.dual_lens_projector import (
    DualLensVirtualIndexProjector,
    LensConsistencyError,
    LensKind,
)
from aios_core.world.retrospective_annotation import (
    AnnotationRegistry,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

UTC = timezone.utc
T0 = datetime(2023, 5, 1, 9, 0, tzinfo=UTC)


def _built_world(n_facts: int = 80, seed: int = 23):
    rng = random.Random(seed)
    ledger = ImmutableFactLedger()
    registry = AnnotationRegistry()
    facts = []
    for i in range(n_facts):
        facts.append(
            {
                "fact_id": f"fact_{i:03d}",
                "entity_id": f"ent_{i % 7}",
                "occurred_at": T0 + timedelta(days=rng.randrange(0, 700), hours=rng.randrange(24)),
                "kind": "observation",
                "payload": {"value": f"历史事实 #{i} 原始记录", "seed": rng.random()},
            }
        )
    ledger.record_facts(facts)
    return ledger, registry


def test_as_known_lens_hides_todays_annotation_from_past():
    ledger, registry = _built_world()
    t_now = T0 + timedelta(days=900)
    registry.append(
        RetrospectiveAnnotation(
            annotation_id="anno_partner_fraud",
            target_entity_id="fact_003",
            semantic_overlay="经侦定性：历史合作事实重估为诈骗证据链",
            target_time_start=T0 + timedelta(days=40),
            target_time_end=T0 + timedelta(days=40),
            learned_at=t_now,
            source_statement_ref="经侦通报-测试卷",
        )
    )
    projector = DualLensVirtualIndexProjector(ledger, registry)

    past_view = projector.project(LensKind.AS_KNOWN, now=T0 + timedelta(days=500))
    today_view = projector.project(LensKind.ANNOTATED, now=t_now)

    assert past_view.annotation_count == 0  # 历史时刻纯净，后世注解不可见
    assert past_view.is_pure_history is True
    assert today_view.annotation_count == 1
    assert today_view.annotated_fact_ids == ("fact_003",)


def test_projection_never_mutates_history_fingerprint():
    ledger, registry = _built_world(n_facts=120)
    t_now = T0 + timedelta(days=800)
    fingerprint_before = ledger.aggregate_fingerprint()
    hashes_before = dict(ledger.all_hashes())

    projector = DualLensVirtualIndexProjector(ledger, registry)
    for lens in (LensKind.AS_KNOWN, LensKind.ANNOTATED):
        for _ in range(3):  # 反复投影不得有任何副作用
            projector.project(lens, now=t_now)

    registry.append(
        RetrospectiveAnnotation(
            annotation_id="anno_late",
            target_entity_id="fact_050",
            semantic_overlay="迟到两年的重新解释",
            target_time_start=T0 + timedelta(days=100),
            target_time_end=T0 + timedelta(days=100),
            learned_at=t_now,
            source_statement_ref="补充裁定书",
        )
    )
    projector.project(LensKind.ANNOTATED, now=t_now)

    assert ledger.aggregate_fingerprint() == fingerprint_before
    assert ledger.all_hashes() == hashes_before  # 逐事实 SHA-256 一个字节都不许变


def test_lens_consistency_check_and_single_hop_invalidation():
    ledger, registry = _built_world()
    t_now = T0 + timedelta(days=750)
    registry.append(
        RetrospectiveAnnotation(
            annotation_id="anno_origin",
            target_entity_id="fact_010",
            semantic_overlay="关键事实重估",
            target_time_start=T0 + timedelta(days=60),
            target_time_end=T0 + timedelta(days=60),
            learned_at=t_now,
            source_statement_ref="庭审笔录",
        )
    )
    projector = DualLensVirtualIndexProjector(ledger, registry)
    consistency = projector.consistency_check(now=t_now)
    assert consistency["consistent"] is True

    dependencies = {"fact_010": [f"summary_{i}" for i in range(8)]}
    for mid in dependencies["fact_010"]:
        dependencies[mid] = [f"deep_{mid}_{j}" for j in range(5)]
    projector.register_dependency_graph(dependencies)

    report = projector.invalidate_single_hop("fact_010")
    assert report.traversal_depth_reached == 1
    assert len(report.marked_stale) == 8  # 只碰直接下游
    assert report.untouched_downstream == 40  # 二级节点全部完好
    assert report.llm_recompute_triggered == 0

    with pytest.raises(Exception):  # fail-closed：多跳请求零违宪妥协
        projector.isolator.reverse_invalidate("fact_010", max_hops=3)


def test_unknown_projection_lens_rejected():
    ledger, registry = _built_world()
    projector = DualLensVirtualIndexProjector(ledger, registry)
    with pytest.raises(Exception):
        projector.project("hacked_lens", now=T0)  # type: ignore[arg-type]
    # 非法透镜不得留下任何投影痕迹
    assert projector._projections == []
