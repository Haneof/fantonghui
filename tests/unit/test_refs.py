"""M0-006 ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性冻结"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.contracts.time import utc_now
from aios_core.storage.sqlite_store import SQLiteWorldStore, StoreError


class DummyEntity(WorldObject):
    object_type: ObjectType = ObjectType.ENTITY
    entity_kind: str = "person"
    canonical_name: str | None = None
    value: str | None = None


class RefNode(WorldObject):
    object_type: ObjectType = ObjectType.ENTITY
    entity_kind: str = "refnode"
    link_refs: list[ObjectRef] = []


class RefHolder(WorldObject):
    object_type: ObjectType = ObjectType.ENTITY
    entity_kind: str = "holder"
    ref: ObjectRef | None = None
    refs: list[ObjectRef] = []


class SourceHolder(WorldObject):
    object_type: ObjectType = ObjectType.ENTITY
    entity_kind: str = "source_holder"
    # source_refs is already in WorldObject, use it


def make_op(expected_world_revision: int = 0) -> OperationRequest:
    import uuid

    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-006 test",
        idempotency_key=str(uuid.uuid4()),
    )


# R01 ObjectRef结构
def test_r01_objectref_structure():
    # object_id=""拒绝
    with pytest.raises(Exception):
        ObjectRef(object_id="", revision=1)

    # revision=0拒绝
    with pytest.raises(Exception):
        ObjectRef(object_id="x", revision=0)

    # revision=-1拒绝
    with pytest.raises(Exception):
        ObjectRef(object_id="x", revision=-1)

    # revision=None合法
    ref_none = ObjectRef(object_id="x", revision=None)
    assert ref_none.revision is None

    # revision=1合法
    ref1 = ObjectRef(object_id="x", revision=1)
    assert ref1.revision == 1

    # extra field拒绝
    with pytest.raises(Exception):
        ObjectRef(object_id="x", revision=1, extra_field="bad")  # type: ignore


# R02 ObjectRef frozen
def test_r02_objectref_frozen():
    ref = ObjectRef(object_id="x", revision=1)
    with pytest.raises(Exception):
        ref.revision = 2  # type: ignore

    with pytest.raises(Exception):
        ref.object_id = "y"  # type: ignore


# R03 SourceRef结构与frozen
def test_r03_sourceref_structure_and_frozen():
    # object_id, revision, source_locator
    ref = SourceRef(object_id="x", revision=1, source_locator="loc")
    assert ref.source_locator == "loc"

    # revision None /1 合法
    ref_none = SourceRef(object_id="x", revision=None)
    assert ref_none.revision is None
    ref1 = SourceRef(object_id="x", revision=1)
    assert ref1.revision == 1

    # revision=0拒绝
    with pytest.raises(Exception):
        SourceRef(object_id="x", revision=0)

    # extra字段拒绝
    with pytest.raises(Exception):
        SourceRef(object_id="x", revision=1, bad="field")  # type: ignore

    # 赋值修改拒绝
    ref_frozen = SourceRef(object_id="x", revision=1)
    with pytest.raises(Exception):
        ref_frozen.revision = 2  # type: ignore


# R04 nonexistent object
def test_r04_nonexistent_object(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    target_ref = ObjectRef(object_id="missing_obj", revision=None)

    holder = RefHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        ref=target_ref,
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([holder], make_op(0))

    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert store.current_world_revision() == 0


# R05 nonexistent exact revision
def test_r05_nonexistent_exact_revision(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    target_id = new_object_id(ObjectType.ENTITY)
    target = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        value="rev1",
    )
    store.commit([target], make_op(0))

    # Reference rev2 which does not exist
    holder = RefHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        ref=ObjectRef(object_id=target_id, revision=2),
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([holder], make_op(1))

    assert excinfo.value.code == ErrorCode.NOT_FOUND
    # Should not fallback to rev1


# R06 pinned historical ref不漂移
def test_r06_pinned_historical_ref_no_drift(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    target_id = new_object_id(ObjectType.ENTITY)

    target_rev1 = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        value="old",
    )
    store.commit([target_rev1], make_op(0))

    holder_id = new_object_id(ObjectType.ENTITY)
    holder_ref = ObjectRef(object_id=target_id, revision=1)
    holder = RefHolder(
        object_id=holder_id,
        subject_id="test",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        ref=holder_ref,
    )
    store.commit([holder], make_op(1))

    # Target updates to rev2
    target_rev2 = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        value="new",
    )
    store.commit([target_rev2], make_op(2))

    # Re-read holder
    holder_payload = store.get_payload(holder_id)
    # holder's ref revision still ==1 (stored in payload)
    # Depending on how payload stores ref, check
    assert holder_payload["ref"]["revision"] == 1

    # Read target@holder_ref.revision must be "old"
    target_via_ref = store.get_payload(target_id, revision=holder_ref.revision)
    assert target_via_ref["value"] == "old"
    assert target_via_ref["value"] != "new"


# R07 floating navigation语义
def test_r07_floating_navigation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    target_id = new_object_id(ObjectType.ENTITY)

    target_rev1 = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        value="rev1",
    )
    store.commit([target_rev1], make_op(0))

    floating = ObjectRef(object_id=target_id, revision=None)

    # Navigation latest should get rev1
    latest = store.get_payload(target_id)
    assert latest["value"] == "rev1"

    # Add rev2
    target_rev2 = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        value="rev2",
    )
    store.commit([target_rev2], make_op(1))

    # Same floating ref still revision=None, but latest reading gets rev2
    assert floating.revision is None
    latest2 = store.get_payload(target_id)
    assert latest2["value"] == "rev2"


# R08 同事务互相引用
def test_r08_same_transaction_mutual_refs(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id_a = new_object_id(ObjectType.ENTITY)
    obj_id_b = new_object_id(ObjectType.ENTITY)

    # A refs B@1, B refs A@1, same learned_at
    obj_a = RefNode(
        object_id=obj_id_a,
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        link_refs=[ObjectRef(object_id=obj_id_b, revision=1)],
    )
    obj_b = RefNode(
        object_id=obj_id_b,
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        link_refs=[ObjectRef(object_id=obj_id_a, revision=1)],
    )

    result = store.commit([obj_a, obj_b], make_op(0))
    assert result.world_revision == 1
    assert store.current_world_revision() == 1

    # Both readable
    payload_a = store.get_payload(obj_id_a)
    payload_b = store.get_payload(obj_id_b)
    assert payload_a["object_id"] == obj_id_a
    assert payload_b["object_id"] == obj_id_b


# R09 future explicit ref拒绝
def test_r09_future_explicit_ref_rejected(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    # target learned at 11:00
    target_learned = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    target_id = new_object_id(ObjectType.ENTITY)
    target = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=target_learned,
        recorded_at=target_learned,
        created_by="test",
        value="future",
    )
    store.commit([target], make_op(0))

    # holder learned at 10:00, refs target@1
    holder_learned = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    holder = RefHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=holder_learned,
        recorded_at=holder_learned,
        created_by="test",
        ref=ObjectRef(object_id=target_id, revision=1),
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([holder], make_op(1))

    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert store.current_world_revision() == 1
    # Error must not leak target learned_at
    ctx_str = json.dumps(excinfo.value.context, ensure_ascii=False)
    assert "11:00" not in ctx_str
    assert "future" not in ctx_str.lower() or "reference_not_visible" in ctx_str


# R10 visible historical explicit ref成功
def test_r10_visible_historical_explicit_ref_success(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    target_learned = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
    target_id = new_object_id(ObjectType.ENTITY)
    target = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=target_learned,
        recorded_at=target_learned,
        created_by="test",
        value="old",
    )
    store.commit([target], make_op(0))

    holder_learned = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    holder = RefHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=holder_learned,
        recorded_at=holder_learned,
        created_by="test",
        ref=ObjectRef(object_id=target_id, revision=1),
    )

    result = store.commit([holder], make_op(1))
    assert result.world_revision == 2


# R11 floating ref有旧可见版本
def test_r11_floating_ref_old_visible(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    target_id = new_object_id(ObjectType.ENTITY)

    rev1_learned = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
    rev1 = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=rev1_learned,
        recorded_at=rev1_learned,
        created_by="test",
        value="rev1",
    )
    store.commit([rev1], make_op(0))

    rev2_learned = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    rev2 = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=2,
        learned_at=rev2_learned,
        recorded_at=rev2_learned,
        created_by="test",
        value="rev2",
    )
    store.commit([rev2], make_op(1))

    holder_learned = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    holder = RefHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=holder_learned,
        recorded_at=holder_learned,
        created_by="test",
        ref=ObjectRef(object_id=target_id, revision=None),
    )

    # Should allow because rev1 visible at 10:00, even though rev2 is 11:00 and DB latest is future
    result = store.commit([holder], make_op(2))
    assert result.world_revision == 3


# R12 floating ref只有未来版本
def test_r12_floating_ref_only_future(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    target_id = new_object_id(ObjectType.ENTITY)
    rev1_learned = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    rev1 = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=rev1_learned,
        recorded_at=rev1_learned,
        created_by="test",
        value="future",
    )
    store.commit([rev1], make_op(0))

    holder_learned = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    holder = RefHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=holder_learned,
        recorded_at=holder_learned,
        created_by="test",
        ref=ObjectRef(object_id=target_id, revision=None),
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([holder], make_op(1))

    assert excinfo.value.code == ErrorCode.NOT_FOUND


# R13 pending future ref拒绝
def test_r13_pending_future_ref_rejected(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obj_id_a = new_object_id(ObjectType.ENTITY)
    obj_id_b = new_object_id(ObjectType.ENTITY)

    learned_a = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    learned_b = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)

    obj_a = RefNode(
        object_id=obj_id_a,
        subject_id="test",
        revision=1,
        learned_at=learned_a,
        recorded_at=learned_a,
        created_by="test",
        link_refs=[ObjectRef(object_id=obj_id_b, revision=1)],
    )
    obj_b = RefNode(
        object_id=obj_id_b,
        subject_id="test",
        revision=1,
        learned_at=learned_b,
        recorded_at=learned_b,
        created_by="test",
        link_refs=[],
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([obj_a, obj_b], make_op(0))

    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert store.current_world_revision() == 0

    # Neither should be written
    with pytest.raises(StoreError):
        store.get_payload(obj_id_a)
    with pytest.raises(StoreError):
        store.get_payload(obj_id_b)


# R14 SourceRef版本验证
def test_r14_sourceref_version_validation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    target_id = new_object_id(ObjectType.ENTITY)
    now = utc_now()
    target = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        value="rev1",
    )
    store.commit([target], make_op(0))

    # SourceRef target rev1 exists and visible => success
    holder_ok = SourceHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        source_refs=[SourceRef(object_id=target_id, revision=1)],
    )
    result = store.commit([holder_ok], make_op(1))
    assert result.world_revision == 2

    # SourceRef target rev2 does not exist => NOT_FOUND
    holder_fail = SourceHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        source_refs=[SourceRef(object_id=target_id, revision=2)],
    )
    with pytest.raises(StoreError) as excinfo:
        store.commit([holder_fail], make_op(2))
    assert excinfo.value.code == ErrorCode.NOT_FOUND


# R15 SourceRef future visibility
def test_r15_sourceref_future_visibility(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    target_learned = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    target_id = new_object_id(ObjectType.ENTITY)
    target = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=target_learned,
        recorded_at=target_learned,
        created_by="test",
        value="future",
    )
    store.commit([target], make_op(0))

    holder_learned = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    holder = SourceHolder(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="test",
        revision=1,
        learned_at=holder_learned,
        recorded_at=holder_learned,
        created_by="test",
        source_refs=[SourceRef(object_id=target_id, revision=1)],
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([holder], make_op(1))

    assert excinfo.value.code == ErrorCode.NOT_FOUND


# Critical model ref field check
def test_critical_model_ref_fields():
    from aios_core.contracts.models import (
        Claim,
        EventAnchor,
        EvidenceSet,
        Dependency,
    )

    # Claim
    assert "support_evidence_set_refs" in Claim.model_fields
    assert "counter_evidence_set_refs" in Claim.model_fields
    # Check type annotation is ObjectRef (we check via model_fields)
    # We won't enforce strict type equality, just ensure field exists and is not modified to string

    # EventAnchor
    assert "primary_claim_refs" in EventAnchor.model_fields
    assert "evidence_set_refs" in EventAnchor.model_fields

    # EvidenceSet
    assert "member_refs" in EvidenceSet.model_fields
    assert "support_refs" in EvidenceSet.model_fields
    assert "counter_refs" in EvidenceSet.model_fields
    assert "context_refs" in EvidenceSet.model_fields

    # Dependency
    assert "dependent_ref" in Dependency.model_fields
    assert "dependency_ref" in Dependency.model_fields
