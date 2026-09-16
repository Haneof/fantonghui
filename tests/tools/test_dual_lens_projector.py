"""双透镜虚拟索引投影器单测"""
from datetime import datetime, timedelta, timezone

from aios_core.tools.dual_lens_projector import DualLensVirtualIndexProjector
from aios_core.world.retrospective_annotation import RetrospectiveAnnotation

UTC = timezone.utc


def test_virtual_projection_zero_copy():
    proj = DualLensVirtualIndexProjector()
    base = datetime(2022, 1, 1, tzinfo=UTC)
    facts = [{"fact_id": f"f{i}", "entity_id": "ent_a", "occurred_at": base + timedelta(days=i), "kind": "chat", "payload": {"text": f"hello {i}"}} for i in range(100)]
    proj.ingest_facts(facts)
    view1 = proj.view_annotated()
    view2 = proj.view_annotated()
    assert view1.is_virtual and view2.is_virtual
    assert proj.stats.switch_count >= 2
    assert proj.stats.p95_switch_ms < 10


def test_immutability_and_old_view_zero_overlay():
    proj = DualLensVirtualIndexProjector()
    base = datetime(2022, 1, 1, tzinfo=UTC)
    today = datetime(2025, 11, 15, tzinfo=UTC)
    facts = [{"fact_id": f"f{i}", "entity_id": "ent_old_wang", "occurred_at": base + timedelta(days=i), "kind": "chat", "payload": {"text": "old"}} for i in range(10)]
    proj.ingest_facts(facts)
    snap = dict(proj.ledger.all_hashes())
    ann = RetrospectiveAnnotation(annotation_id="ann_1", target_entity_id="ent_old_wang", semantic_overlay="诈骗", target_time_start=base, target_time_end=today, learned_at=today, recorded_at=today, source_statement_ref="court")
    proj.mount_annotation(ann)
    ok, cnt = proj.verify_immutability()
    assert ok and cnt == 10
    assert snap == {k: v for k, v in proj.ledger.all_hashes().items() if k in snap}
    old = proj.view_as_known(datetime(2023, 1, 1, tzinfo=UTC))
    new = proj.view_annotated()
    assert old.overlay_count == 0
    assert new.overlay_count == 1
    assert new.fact_count == 10


def test_single_hop_isolation():
    proj = DualLensVirtualIndexProjector()
    rep = proj.single_hop_isolation_report("ent_old_wang")
    assert rep["depth"] == 1
    assert rep["llm_calls"] == 0
    assert rep["prevented_apiavalanche"] == 210


def test_co_search_with_lens():
    proj = DualLensVirtualIndexProjector()
    base = datetime(2022, 1, 1, tzinfo=UTC)
    facts = [
        {"fact_id": "f1", "entity_id": "ent_a", "occurred_at": base, "kind": "chat", "payload": {"text": "老王 借款 50万 合同"}},
        {"fact_id": "f2", "entity_id": "ent_b", "occurred_at": base, "kind": "chat", "payload": {"text": "妈妈 生日 礼物"}},
    ]
    proj.ingest_facts(facts)
    hit = proj.co_search_with_lens(["老王", "借款"], lens="annotated")
    assert hit["hit_count"] >= 1
    assert hit["virtual"] is True


def test_memory_overhead_bounded():
    proj = DualLensVirtualIndexProjector()
    base = datetime(2022, 1, 1, tzinfo=UTC)
    facts = [{"fact_id": f"f{i}", "entity_id": "ent_a", "occurred_at": base, "kind": "chat", "payload": {"text": "x"}} for i in range(1000)]
    proj.ingest_facts(facts)
    before = proj.stats.virtual_memory_overhead_bytes
    ann = RetrospectiveAnnotation(annotation_id="ann_1", target_entity_id="ent_a", semantic_overlay="overlay", target_time_start=base, target_time_end=base + timedelta(days=10), learned_at=base + timedelta(days=20), recorded_at=base + timedelta(days=20), source_statement_ref="src")
    proj.mount_annotation(ann)
    after = proj.stats.virtual_memory_overhead_bytes
    assert after == 256  # single annotation overhead
    assert after < len(facts) * 10
