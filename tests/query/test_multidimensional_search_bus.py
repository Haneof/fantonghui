"""AIOS 3.0 多维心智检索总线原生四大维度测试套件 (Multidimensional Search Bus Test).

严格验证 MultidimensionalSearchEngine 原生支持：
1. 按维度（Dimension）：dim_finance, dim_health, dim_social 等；
2. 按主张（Claim）：通过 claim_id 因果穿透证据链；
3. 按实体（Entity）：通过 entity_id 与别名网络精准关联；
4. 按注记（Annotation）：老王案外挂解释图层联动，作为候选证据而非固定最高解释权；
5. 多维正交联合精准检索：时空窗 + 维度 + 实体 + 注记伴随，Token 极简 (< 150)。
"""

import pytest
from datetime import datetime, timezone
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.contracts.models import (
    Entity, Observation, Claim, EventAnchor, TemporalExtent
)
from aios_core.contracts.enums import ObjectType, ClaimType, KnowledgeState, SourceClass
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.query.search import MultidimensionalSearchEngine
from aios_core.operations.world_operator import WorldOperatorSuite

UTC = timezone.utc


@pytest.fixture
def bus_test_env(tmp_path):
    db_file = tmp_path / "mind_bus_test.db"
    store = SQLiteWorldStore(str(db_file))
    suite = WorldOperatorSuite(store)
    engine = suite.search.index

    t0 = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
    t1 = datetime(2025, 6, 20, 15, 0, tzinfo=UTC)
    t_now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)

    # 1. 写入实体：老王、母亲、自己
    ent_me = Entity(
        object_id="ent_me",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="我",
        aliases=["自己"],
        occurred=TemporalExtent.point(t0),
        learned_at=t0,
        recorded_at=t0,
        created_by="test",
    )
    ent_wang = Entity(
        object_id="ent_wang",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="老王",
        aliases=["王强", "合伙人老王"],
        occurred=TemporalExtent.point(t0),
        learned_at=t0,
        recorded_at=t0,
        created_by="test",
    )
    ent_mom = Entity(
        object_id="ent_mom",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="母亲",
        aliases=["老妈", "妈妈"],
        occurred=TemporalExtent.point(t0),
        learned_at=t0,
        recorded_at=t0,
        created_by="test",
    )

    # 2. 写入观测：
    # 财务：老王借款
    obs_wang_loan = Observation(
        object_id="obs_wang_loan_50w",
        subject_id="user_1",
        revision=1,
        source_kind="transaction",
        modality="text",
        value="微信转账给合伙人老王借款50万元用于周转",
        occurred=TemporalExtent.point(t0),
        learned_at=t0,
        recorded_at=t0,
        created_by="test",
        metadata={"dimension": "dim_finance"},
    )
    # 健康：早搏心电
    obs_cardiac = Observation(
        object_id="obs_cardiac_arrhythmia",
        subject_id="user_1",
        revision=1,
        source_kind="biometrics",
        modality="text",
        value="深夜通宵加班后发生室性早搏与心率飙升",
        occurred=TemporalExtent.point(t1),
        learned_at=t1,
        recorded_at=t1,
        created_by="test",
        metadata={"dimension": "dim_health"},
    )
    # 社交：母亲生日送礼
    obs_mom_gift = Observation(
        object_id="obs_mom_gift_footbath",
        subject_id="user_1",
        revision=1,
        source_kind="chat",
        modality="text",
        value="给老妈买的足浴盆闲置了，倒水太沉腰疼",
        occurred=TemporalExtent.point(t1),
        learned_at=t1,
        recorded_at=t1,
        created_by="test",
        metadata={"dimension": "dim_social"},
    )

    # 3. 写入主张（Claim）：合伙信用主张，支持证据是指向借款
    claim_partner = Claim(
        object_id="claim_partner_trust",
        subject_id="user_1",
        revision=1,
        claimant_id="user_1",
        claim_type=ClaimType.FACT,
        content="老王是值得信赖的合伙人",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.9,
        valid_time=TemporalExtent.point(t0),
        asserted_at=t0,
        occurred=TemporalExtent.point(t0),
        learned_at=t0,
        recorded_at=t0,
        created_by="test",
    )

    op_init = OperationRequest(
        operation_id=new_operation_id(),
        operation_name="init.world",
        expected_world_revision=0,
        reason="Setup test world",
        idempotency_key="init_1",
        source_class=SourceClass.AI_COGNITION,
    )
    store.commit([ent_me, ent_wang, ent_mom, obs_wang_loan, obs_cardiac, obs_mom_gift, claim_partner], op_init)

    # 4. 写入老王案外挂注记（今天打标签，绝对零修改历史）
    anno = suite.cognition.record_realization_today(
        target_object_id="obs_wang_loan_50w",
        target_object_type=ObjectType.OBSERVATION,
        reinterpretation_claim="朝阳法院正式判决老王借款涉嫌合同诈骗，两年前合伙借款实为诈骗套路",
        is_invalidating=True,
        actor="test_judge",
        now=t_now,
    )

    return store, engine, suite, anno


def test_search_by_dimension(bus_test_env):
    """测试原生按维度（Dimension）正交过滤。"""
    store, engine, suite, _ = bus_test_env
    # 检索 dim_finance
    finance_page = engine.search_by_dimension("dim_finance")
    assert finance_page.status == "ok"
    f_ids = [h.object_id for h in finance_page.hits]
    assert "obs_wang_loan_50w" in f_ids
    assert "obs_cardiac_arrhythmia" not in f_ids

    # 检索 dim_health
    health_page = engine.search_by_dimension("dim_health")
    h_ids = [h.object_id for h in health_page.hits]
    assert "obs_cardiac_arrhythmia" in h_ids
    assert "obs_wang_loan_50w" not in h_ids


def test_dimension_projection_requires_explicit_world_metadata(tmp_path):
    db_file = tmp_path / "dimension_explicit.db"
    store = SQLiteWorldStore(str(db_file))
    engine = MultidimensionalSearchEngine(str(db_file), store=store)
    t0 = datetime(2026, 9, 18, tzinfo=UTC)
    ambiguous = Observation(
        object_id="obs_ambiguous_dimension",
        subject_id="user_1",
        revision=1,
        source_kind="transaction",
        modality="text",
        value="今天转账后又聊到心率、妈妈和代码，文本故意跨多个旧关键词规则。",
        occurred=TemporalExtent.point(t0),
        learned_at=t0,
        recorded_at=t0,
        created_by="test",
    )
    store.commit(
        [ambiguous],
        OperationRequest(
            operation_id=new_operation_id(),
            operation_name="dimension.explicit.test",
            expected_world_revision=0,
            reason="prove search does not infer semantic dimension from keywords",
            idempotency_key="dimension_explicit_1",
            source_class=SourceClass.AI_COGNITION,
        ),
    )
    engine.catch_up()
    page = engine.search_mind(keywords=["心率"])
    hit = next(h for h in page.hits if h.object_id == ambiguous.object_id)
    assert hit.dimension == "dim_unclassified"

def test_search_by_entity(bus_test_env):
    """测试原生按实体（Entity）精准关联检索（支持别名展开）。"""
    store, engine, suite, _ = bus_test_env
    # 按实体 ID 检索老王
    wang_page = engine.search_by_entity("ent_wang")
    w_ids = [h.object_id for h in wang_page.hits]
    assert "ent_wang" in w_ids or "obs_wang_loan_50w" in w_ids

    # 按别名检索 "老妈"
    mom_page = suite.search.query(keywords=["老妈"])
    m_ids = [h["object_id"] for h in mom_page]
    assert "obs_mom_gift_footbath" in m_ids or "ent_mom" in m_ids


def test_search_by_claim(bus_test_env):
    """测试原生按主张（Claim）穿透检索。"""
    store, engine, suite, _ = bus_test_env
    claim_page = engine.search_by_claim("claim_partner_trust")
    assert claim_page.status == "ok"
    assert any(h.object_id == "claim_partner_trust" for h in claim_page.hits)


def test_search_by_annotation_and_companion_attachment(bus_test_env):
    """注记可直接/伴随召回，但 Search 不授予固定最高解释权。"""
    store, engine, suite, anno = bus_test_env
    anno_page = engine.search_by_annotation(anno.annotation_id)
    assert anno_page.status == "ok"
    assert any(h.object_id == anno.annotation_id for h in anno_page.hits)

    loan_page = engine.search_mind(keywords=["老王", "借款"], include_annotations=True)
    hit_ids = [h.object_id for h in loan_page.hits]
    assert "obs_wang_loan_50w" in hit_ids
    assert anno.annotation_id in hit_ids
    anno_hits = [h for h in loan_page.hits if h.object_id == anno.annotation_id]
    assert len(anno_hits) == 1
    assert "合同诈骗" in anno_hits[0].excerpt

def test_multidimensional_joint_search_and_token_efficiency(bus_test_env):
    """测试维度 + 实体 + 关键词 + 注记四维联合正交检索与极简 Token (< 150)。"""
    store, engine, suite, anno = bus_test_env
    page = suite.search.search_mind(
        keywords=["借款"],
        dimension="dim_finance",
        entity_id="ent_wang",
        include_annotations=True,
        limit=5,
    )
    assert page.status == "ok"
    assert len(page.hits) >= 1
    # 验证极简 Token 预算（总 Token 不超过 150）
    assert page.total_estimated_tokens <= 150
    # 验证驾驶舱 query 输出
    summary_slices = suite.search.query(
        keywords=["借款"],
        dimension="dim_finance",
        entity_id="ent_wang",
    )
    assert len(summary_slices) >= 1
    assert all("estimated_tokens" in s for s in summary_slices)
