"""Unit tests for AIOS 3.0 World Operator Suite (aios_core.operations)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.enums import ClaimType, KnowledgeState, ObjectType, SourceClass
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import (
    Claim,
    Entity,
    EventAnchor,
    EvidenceSet,
    Observation,
    Relation,
    TemporalExtent,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import KnowledgeWindow
from aios_core.operations.world_operator import (
    CognitionOperator,
    ConditionalTaskOperator,
    DimensionLensOperator,
    EvidenceDrillDownOperator,
    ScaleLevel,
    TimeLensOperator,
    WorldNavigator,
    WorldOperatorSuite,
    estimate_token_count,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc
T0 = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def clean_store(tmp_path) -> SQLiteWorldStore:
    db_path = str(tmp_path / "test_world_ops.db")
    return SQLiteWorldStore(db_path)


@pytest.fixture
def populated_suite(clean_store: SQLiteWorldStore) -> WorldOperatorSuite:
    store = clean_store
    t1 = T0
    t2 = T0 + timedelta(days=5)

    # 1. 创建实体
    ent_user = Entity(
        object_id="ent_me",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="测试用户",
        occurred=TemporalExtent.point(t1),
        learned_at=t1,
        recorded_at=t1,
        created_by="test",
    )
    ent_wang = Entity(
        object_id="ent_wang",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="老王",
        aliases=["合伙人老王"],
        occurred=TemporalExtent.point(t1),
        learned_at=t1,
        recorded_at=t1,
        created_by="test",
    )

    # 2. 关系
    rel = Relation(
        object_id="rel_user_wang",
        subject_id="user_1",
        revision=1,
        relation_type="partner",
        left=ObjectRef(object_id="ent_me", revision=1),
        right=ObjectRef(object_id="ent_wang", revision=1),
        confidence=1.0,
        valid_time=TemporalExtent.point(t1),
        occurred=TemporalExtent.point(t1),
        learned_at=t1,
        recorded_at=t1,
        created_by="test",
    )

    # 3. 观测
    obs1 = Observation(
        object_id="obs_wang_loan",
        subject_id="user_1",
        revision=1,
        source_kind="transaction",
        modality="text",
        value="借给老王50万元用于合伙项目",
        occurred=TemporalExtent.point(t1),
        learned_at=t1,
        recorded_at=t1,
        created_by="test",
    )
    obs2 = Observation(
        object_id="obs_heart_spike",
        subject_id="user_1",
        revision=1,
        source_kind="biometrics",
        modality="json",
        value=json.dumps({"hr": 125, "arrhythmia": True}),
        occurred=TemporalExtent.point(t2),
        learned_at=t2,
        recorded_at=t2,
        created_by="test",
    )
    obs3 = Observation(
        object_id="obs_chat_dispute",
        subject_id="user_1",
        revision=1,
        source_kind="chat",
        modality="text",
        value="和老王电话激烈争吵，对方拒绝还钱",
        occurred=TemporalExtent.point(t2),
        learned_at=t2,
        recorded_at=t2,
        created_by="test",
    )

    # 4. 证据集与锚点
    evset = EvidenceSet(
        object_id="evset_wang_loan",
        subject_id="user_1",
        revision=1,
        purpose="老王借款凭证",
        knowledge_window=KnowledgeWindow(
            knowledge_cutoff=t2,
        ),
        member_refs=[
            ObjectRef(object_id="obs_wang_loan", revision=1),
            ObjectRef(object_id="obs_chat_dispute", revision=1),
        ],
        selection_method="curated",
        occurred=TemporalExtent(start=t1, end=t2),
        learned_at=t2,
        recorded_at=t2,
        created_by="test",
    )
    anchor = EventAnchor(
        object_id="anchor_wang_dispute",
        subject_id="user_1",
        revision=1,
        title="老王借款争执",
        interpretation="老王借款50万后发生严重纠纷",
        confidence=0.9,
        participant_refs=[
            ObjectRef(object_id="ent_wang", revision=1),
            ObjectRef(object_id="ent_me", revision=1),
        ],
        evidence_set_refs=[
            ObjectRef(object_id="evset_wang_loan", revision=1),
        ],
        event_time=TemporalExtent(start=t1, end=t2),
        occurred=TemporalExtent(start=t1, end=t2),
        learned_at=t2,
        recorded_at=t2,
        created_by="test",
    )
    claim = Claim(
        object_id="claim_wang_dispute",
        subject_id="ent_wang",
        revision=1,
        claimant_id="user_1",
        claim_type=ClaimType.BELIEF,
        content="老王存在严重违约还款风险",
        confidence=0.95,
        valid_time=TemporalExtent.point(t2),
        asserted_at=t2,
        knowledge_state=KnowledgeState.INFERRED,
        support_evidence_set_refs=[
            ObjectRef(object_id="evset_wang_loan", revision=1),
        ],
        occurred=TemporalExtent.point(t2),
        learned_at=t2,
        recorded_at=t2,
        created_by="test",
    )

    op = OperationRequest(
        operation_id=new_operation_id(),
        operation_name="test.init",
        expected_world_revision=store.current_world_revision(),
        reason="Init test entities",
        idempotency_key="init_key_001",
        source_class=SourceClass.AI_COGNITION,
    )
    store.commit([ent_user, ent_wang, rel, obs1, obs2, obs3, evset, anchor, claim], op)
    return WorldOperatorSuite(store)


def test_time_lens_operator_zoom_and_slice(populated_suite: WorldOperatorSuite):
    lens = populated_suite.time_lens

    # 1. 缩放尺度
    scale = lens.zoom(ScaleLevel.SCALE_1M)
    assert scale == ScaleLevel.SCALE_1M
    assert lens.current_scale == ScaleLevel.SCALE_1M

    # 2. 截取时空窗
    t_start = T0 - timedelta(days=1)
    t_end = T0 + timedelta(days=10)
    slice_res = lens.slice_window(t_start, t_end)
    assert len(slice_res) >= 3

    obs_ids = [item["object_id"] for item in slice_res]
    assert "obs_wang_loan" in obs_ids
    assert "obs_heart_spike" in obs_ids


def test_dimension_lens_operator_focus_and_align(populated_suite: WorldOperatorSuite):
    dim_op = populated_suite.dim_lens

    # 1. 聚焦维度
    focused = dim_op.focus_dimensions(["dim_health", "dim_social"])
    assert "dim_health" in focused
    assert "dim_social" in focused

    # 2. 时空基准横向对齐 (T0 + 5天 发生的心率突变与对话争吵)
    t_window = (T0 + timedelta(days=4), T0 + timedelta(days=6))
    aligned = dim_op.align_cross_dimensions(t_window, ["dim_health", "dim_social"])

    assert len(aligned["dim_health"]) == 1
    assert aligned["dim_health"][0]["object_id"] == "obs_heart_spike"

    assert len(aligned["dim_social"]) == 1
    assert aligned["dim_social"][0]["object_id"] == "obs_chat_dispute"


def test_world_navigator_hop_and_event_chain(populated_suite: WorldOperatorSuite):
    nav = populated_suite.navigator

    # 1. 实体拓扑跳转
    hop_res = nav.hop_entity("ent_wang")
    assert hop_res["root_entity_id"] == "ent_wang"
    assert hop_res["entity"]["canonical_name"] == "老王"
    assert len(hop_res["related_anchors"]) == 1
    assert hop_res["related_anchors"][0]["anchor_id"] == "anchor_wang_dispute"
    assert len(hop_res["related_claims"]) == 1
    assert hop_res["related_claims"][0]["claim_id"] == "claim_wang_dispute"
    assert len(hop_res["related_relations"]) == 1

    # 2. 事件链排序
    chain = nav.get_event_chain(["anchor_wang_dispute"])
    assert len(chain) == 1
    assert chain[0]["anchor_id"] == "anchor_wang_dispute"


def test_evidence_drill_down_lazy_unrolling_and_token_cost(populated_suite: WorldOperatorSuite):
    drill = populated_suite.evidence_drill

    # Level 1: peek_claim (仅查看核心主张元数据)
    claim_summary = drill.peek_claim("claim_wang_dispute")
    assert claim_summary["claim_id"] == "claim_wang_dispute"
    assert claim_summary["statement"] == "老王存在严重违约还款风险"
    tok1 = claim_summary["estimated_tokens"]
    assert tok1 < 60  # 极省 Token

    # Level 2: get_evidence_pointers (仅获取证据集指针，不加载原始大图或长文)
    pointers = drill.get_evidence_pointers("claim_wang_dispute")
    assert len(pointers) == 1
    assert pointers[0]["evidence_set_id"] == "evset_wang_loan"
    assert "obs_wang_loan" in pointers[0]["member_observation_ids"]

    # Level 3: drill_observation_slice (按需精确展开单条微观测切片)
    slice_obs = drill.drill_observation_slice("obs_wang_loan", max_chars=50)
    assert slice_obs["observation_id"] == "obs_wang_loan"
    assert "借给老王50万元" in slice_obs["value_slice"]
    tok3 = slice_obs["estimated_tokens"]
    assert tok3 < 100


def test_cognition_operator_immutable_history_and_today_label(populated_suite: WorldOperatorSuite):
    cog = populated_suite.cognition
    store = populated_suite.store

    # 验证底层事实不可篡改（老王案铁律）：原 obs_wang_loan 保持不变
    orig_wang = store.get_payload("obs_wang_loan")

    t_today = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    # 在今天打标签：老王被定罪为骗子
    anno = cog.record_realization_today(
        target_object_id="obs_wang_loan",
        target_object_type=ObjectType.OBSERVATION,
        reinterpretation_claim="老王已被朝阳法院刑事判决诈骗罪定罪，此笔借款实为合同诈骗款！",
        is_invalidating=True,
        now=t_today,
    )
    assert anno.target_object_id == "obs_wang_loan"
    assert anno.is_invalidating is True

    # 历史记录字节级不变
    wang_after = store.get_payload("obs_wang_loan")
    assert wang_after["value"] == orig_wang["value"]
    assert wang_after["occurred"] == orig_wang["occurred"]

    # 通过时间滑动条查询 ANNOTATED 视图，能够读取到今天的外挂注记
    slice_items = populated_suite.time_lens.slice_window(
        T0 - timedelta(days=1), T0 + timedelta(days=1)
    )
    loan_item = next(it for it in slice_items if it["object_id"] == "obs_wang_loan")
    assert "annotations" in loan_item
    assert loan_item["annotations"][0]["is_invalidating"] is True


def test_conditional_task_operator_anti_waste(populated_suite: WorldOperatorSuite):
    task_op = populated_suite.task_operator

    # 1. 未声明显式触发条件，违宪拦截报错
    with pytest.raises(ValueError, match="违宪拦截"):
        task_op.schedule_conditional_task("无脑轮询任务", {})

    with pytest.raises(ValueError, match="无效的触发条件类型"):
        task_op.schedule_conditional_task("假条件任务", {"type": "unknown_trigger"})

    # 2. 合法条件任务调度成功
    task = task_op.schedule_conditional_task(
        "监测老王退赔到账",
        trigger_condition={
            "type": "event_occurred",
            "event_type": "bank_deposit_received",
            "amount_min": 100000,
        },
    )
    assert task.title == "监测老王退赔到账"
    assert task.task_state == "draft"
    assert task.completion_condition["type"] == "event_occurred"
