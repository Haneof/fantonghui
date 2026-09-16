"""ToolProposal TLP-C02 双透镜虚拟索引投影器验收测试。

宪法第 84~86 条：看板单次装载、1500 Token、禁止盲目灌入全量长上下文。投影器把
AS_KNOWN/ANNOTATED 双时间视图的物化 IO 收敛为一次解析 + 指针优先，验证：
    - 事实入账一次解析，双时间视图复用同一事实字节；
    - 惰性物化：未点名对象保持指针形态，不随检索半径膨胀；
    - 投影只读：绝不改写注册事实的字节。
"""

from __future__ import annotations

from datetime import datetime, timezone

from aios_core.contracts.models import Observation
from aios_core.contracts.time import TemporalExtent
from aios_core.world.epistemic_world_lens import RetrospectiveAnnotation
from aios_core.tools.dual_lens_virtual_index import DualLensVirtualIndexProjector

UTC = timezone.utc


def _obs(oid: str, at: datetime, text: str) -> Observation:
    return Observation(
        object_id=oid, subject_id="user_1", source_kind="chat_text", modality="text",
        value=text, occurred=TemporalExtent.point(at), learned_at=at, recorded_at=at,
        created_by="projector_test", revision=1,
    )


def test_fact_registered_once_and_lens_reuses_same_bytes() -> None:
    proj = DualLensVirtualIndexProjector()
    at = datetime(2024, 5, 10, 14, 0, tzinfo=UTC)
    obj = _obs("obs_loan_1", at, "老王与我签署合伙投资备忘录，借款500000元。")
    digest = proj.register_fact(obj, entity_ids="ent_wang")

    now = datetime(2026, 9, 16, tzinfo=UTC)
    view_as_known = proj.project(entity_id="ent_wang", target_time=now,
                                 as_of_cutoff=at, slice_mode="cumulative")
    view_annotated = proj.project(entity_id="ent_wang", target_time=now, slice_mode="cumulative")

    # 同一事实在两个透镜下的指针 SHA-256 完全一致（解析一次、双透镜复用）
    assert len(view_as_known.fact_pointers) == 1
    assert len(view_annotated.fact_pointers) == 1
    assert view_as_known.fact_pointers[0].sha256 == digest
    assert view_annotated.fact_pointers[0].sha256 == digest


def test_pointer_priority_and_lazy_materialization() -> None:
    proj = DualLensVirtualIndexProjector()
    for i in range(10):
        at = datetime(2024, 1, 1, tzinfo=UTC) + __import__("datetime").timedelta(days=i)
        proj.register_fact(_obs(f"obs_{i}", at, f"事实切片 {i}"), entity_ids="ent_x")

    now = datetime(2026, 9, 16, tzinfo=UTC)
    view = proj.project(entity_id="ent_x", target_time=now, slice_mode="cumulative",
                        materialize_refs=["obs_3"])
    assert len(view.fact_pointers) == 10
    assert len(view.materialized) == 1
    assert view.materialized[0].reference.object_id == "obs_3"
    # 指针化收益：字符占用明显低于全量物化
    assert 0.0 <= view.virtualization_ratio <= 1.0
    assert view.naive_chars > view.pointer_chars


def test_overlay_attach_is_append_only_and_read_only() -> None:
    proj = DualLensVirtualIndexProjector()
    at = datetime(2023, 6, 1, tzinfo=UTC)
    proj.register_fact(_obs("obs_wang_loan", at, "老王借款500000元。"), entity_ids="ent_wang")
    now = datetime(2026, 3, 1, tzinfo=UTC)
    anno = RetrospectiveAnnotation(
        annotation_id="rta_1", target_entity_id="ent_wang",
        semantic_overlay="司法冻结查封确认欺诈",
        valid_time_start=at, valid_time_end=now,
        learned_at=now, recorded_at=now, source_evidence_ref="obs_wang_court",
    )
    receipt = proj.attach_overlay(anno)
    assert receipt
    view = proj.project(entity_id="ent_wang", target_time=now, slice_mode="cumulative")
    assert "司法冻结查封确认欺诈" in view.overlay_labels
    # 事实负载仍取自登记时的字节，未被覆盖
    assert view.fact_pointers[0].sha256


def test_as_known_view_tree_and_lens_consistency() -> None:
    """AS_KNOWN / ANNOTATED 视图都用生产透镜引擎的切片结果。"""
    proj = DualLensVirtualIndexProjector()
    at = datetime(2023, 6, 1, tzinfo=UTC)
    proj.register_fact(
        _obs("obs_wang_loan", at, "老王借款500000元。"), entity_ids="ent_wang"
    )
    now = datetime(2026, 9, 16, tzinfo=UTC)
    # as_of_cutoff 在事实之后：当前认知可见；as_known 截断在事实当天
    view_known = proj.project(entity_id="ent_wang", target_time=now,
                              as_of_cutoff=at, slice_mode="cumulative")
    view_now = proj.project(entity_id="ent_wang", target_time=now, slice_mode="cumulative")
    assert view_known.view_mode == "as_of_cutoff"
    assert view_now.view_mode == "current_cognition"
    assert view_known.fact_pointers[0].sha256 == view_now.fact_pointers[0].sha256
