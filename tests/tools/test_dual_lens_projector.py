"""双透镜虚拟索引投影器全量单测"""
from datetime import datetime, timedelta, timezone
import pytest

from aios_core.contracts.enums import ProposalStatus
from aios_core.tools.dual_lens_projector import (
    DualLensVirtualIndexProjector,
    LensMode,
    create_dual_lens_projector_tool_proposal,
)
from aios_core.tools.proposal_pipeline import ToolProposalPipeline
from aios_core.world.retrospective_annotation import (
    ImmutableFactLedger,
    RetrospectiveAnnotation,
)

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


def test_dual_lens_query_isolation():
    ledger = ImmutableFactLedger()
    t_loan = datetime(2024, 5, 10, 10, 0, tzinfo=UTC)
    t_chat = datetime(2024, 11, 15, 14, 0, tzinfo=UTC)
    t_verdict = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)

    # 1. 写入两年前的合伙借款与聊天事实
    ledger.record_fact(
        fact_id="fact_loan",
        entity_id="ent_wang",
        occurred_at=t_loan,
        kind="contract",
        payload={"text": "老王签署合伙协议，转账借款50万"},
    )
    ledger.record_fact(
        fact_id="fact_chat",
        entity_id="ent_wang",
        occurred_at=t_chat,
        kind="chat",
        payload={"text": "老王发微信承诺下季度连本带息偿还"},
    )

    # 2. 挂载今天学到的刑事判决重估注记
    anno = RetrospectiveAnnotation(
        annotation_id="anno_fraud_2026",
        target_entity_id="ent_wang",
        semantic_overlay="【司法定性】：已被法院以合同诈骗罪定罪判刑，系失信欺诈行为",
        target_time_start=datetime(2024, 1, 1, tzinfo=UTC),
        target_time_end=datetime(2026, 9, 16, 8, 59, tzinfo=UTC),
        learned_at=t_verdict,
        recorded_at=t_verdict,
        source_statement_ref="朝阳法院刑事判决书",
    )

    projector = DualLensVirtualIndexProjector(ledger, [anno])

    # 3. 透镜测试 A：当时已知透镜 (AS_KNOWN，回溯至 2024 年底)
    t_cutoff_2024 = datetime(2024, 12, 31, 23, 59, tzinfo=UTC)
    res_past = projector.query_with_lens(
        search_terms=["老王", "借款"],
        lens_mode=LensMode.AS_KNOWN,
        as_of_cutoff=t_cutoff_2024,
    )
    assert len(res_past.matched_facts) == 1
    assert res_past.matched_facts[0].fact_id == "fact_loan"
    assert res_past.matched_facts[0].active_overlay is None
    assert res_past.matched_facts[0].is_invalidated is False
    assert res_past.overlays_suppressed_count >= 1

    # 4. 透镜测试 B：当前认知透镜 (ANNOTATED，今日认知)
    res_today = projector.query_with_lens(
        search_terms=["老王", "借款"],
        lens_mode=LensMode.ANNOTATED,
    )
    assert len(res_today.matched_facts) == 1
    assert res_today.matched_facts[0].fact_id == "fact_loan"
    assert res_today.matched_facts[0].payload["text"] == "老王签署合伙协议，转账借款50万"
    assert res_today.matched_facts[0].active_overlay is not None
    assert "合同诈骗罪" in res_today.matched_facts[0].active_overlay
    assert res_today.matched_facts[0].is_invalidated is True
    assert res_today.overlays_applied_count >= 1
    assert res_today.query_latency_ms <= 10.0


def test_dual_lens_proposal_lifecycle():
    pipeline = ToolProposalPipeline()
    proposal = create_dual_lens_projector_tool_proposal(subject_id="user_admin")
    pipeline.submit_proposal(proposal)
    pipeline.review_proposal(proposal.object_id, "approve")
    executed = pipeline.execute_proposal(proposal.object_id)
    assert executed.status == ProposalStatus.EXECUTED
