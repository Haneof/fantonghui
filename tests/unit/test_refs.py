"""M0-006 ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性冻结 + R1强化"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import get_args, get_origin, get_type_hints
from zoneinfo import ZoneInfo

import pytest

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.contracts.time import as_utc, utc_now
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
    with pytest.raises(Exception):
        ObjectRef(object_id="", revision=1)
    with pytest.raises(Exception):
        ObjectRef(object_id="x", revision=0)
    with pytest.raises(Exception):
        ObjectRef(object_id="x", revision=-1)
    ref_none = ObjectRef(object_id="x", revision=None)
    assert ref_none.revision is None
    ref1 = ObjectRef(object_id="x", revision=1)
    assert ref1.revision == 1
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
    ref = SourceRef(object_id="x", revision=1, source_locator="loc")
    assert ref.source_locator == "loc"
    ref_none = SourceRef(object_id="x", revision=None)
    assert ref_none.revision is None
    ref1 = SourceRef(object_id="x", revision=1)
    assert ref1.revision == 1
    with pytest.raises(Exception):
        SourceRef(object_id="x", revision=0)
    with pytest.raises(Exception):
        SourceRef(object_id="x", revision=1, bad="field")  # type: ignore
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
    holder_payload = store.get_payload(holder_id)
    assert holder_payload["ref"]["revision"] == 1
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
    latest = store.get_payload(target_id)
    assert latest["value"] == "rev1"
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
    payload_a = store.get_payload(obj_id_a)
    payload_b = store.get_payload(obj_id_b)
    assert payload_a["object_id"] == obj_id_a
    assert payload_b["object_id"] == obj_id_b


# R09 future explicit ref拒绝 - 强化canary
def test_r09_future_explicit_ref_rejected(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    canary = "FUTURE_SECRET_8848"
    target_learned = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    target_id = new_object_id(ObjectType.ENTITY)
    target = DummyEntity(
        object_id=target_id,
        subject_id="test",
        revision=1,
        learned_at=target_learned,
        recorded_at=target_learned,
        created_by="test",
        value=canary,
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

    with pytest.raises(StoreError) as excinfo:
        store.commit([holder], make_op(1))

    err = excinfo.value
    assert err.code == ErrorCode.NOT_FOUND
    assert store.current_world_revision() == 1

    # 必须验证context不泄露未来
    assert err.context["referenced_object_id"] == target_id
    assert err.context["referenced_revision"] == 1
    assert err.context["reason"] == "reference_not_visible_or_missing"

    serialized_error = str(err) + json.dumps(err.context, ensure_ascii=False)
    # 严格不可逃逸检查
    assert canary not in serialized_error, f"Leaked canary {canary} in error: {serialized_error}"
    assert "11:00" not in serialized_error
    assert "learned_at" not in serialized_error
    assert "payload" not in serialized_error


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


# R16 pending DST false-accept防护
def test_r16_pending_dst_false_accept_rejected(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    ny = ZoneInfo("America/New_York")

    # referencing A learned 01:45 fold=0 = 05:45 UTC
    learned_a = datetime(2026, 11, 1, 1, 45, tzinfo=ny, fold=0)
    # pending target B learned 01:30 fold=1 = 06:30 UTC (future vs A)
    learned_b = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=1)

    # Explicit UTC instant check
    assert as_utc(learned_b, "B") > as_utc(learned_a, "A"), f"{as_utc(learned_b,'B')} should > {as_utc(learned_a,'A')}"

    # Wall clock looks B <= A (01:30 <= 01:45) but real instant B > A, should be rejected
    obj_id_a = new_object_id(ObjectType.ENTITY)
    obj_id_b = new_object_id(ObjectType.ENTITY)

    obj_b = DummyEntity(
        object_id=obj_id_b,
        subject_id="test",
        revision=1,
        learned_at=learned_b,
        recorded_at=learned_b,
        created_by="test",
        value="B_future",
    )
    obj_a = RefNode(
        object_id=obj_id_a,
        subject_id="test",
        revision=1,
        learned_at=learned_a,
        recorded_at=learned_a,
        created_by="test",
        link_refs=[ObjectRef(object_id=obj_id_b, revision=1)],
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([obj_a, obj_b], make_op(0))

    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert store.current_world_revision() == 0
    with pytest.raises(StoreError):
        store.get_payload(obj_id_a)
    with pytest.raises(StoreError):
        store.get_payload(obj_id_b)


# R17 pending DST false-reject防护
def test_r17_pending_dst_false_reject_allowed(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    ny = ZoneInfo("America/New_York")

    # target B 01:30 fold=0 = 05:30 UTC
    learned_b = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=0)
    # referencing A 01:15 fold=1 = 06:15 UTC
    learned_a = datetime(2026, 11, 1, 1, 15, tzinfo=ny, fold=1)

    assert as_utc(learned_b, "B") < as_utc(learned_a, "A")

    # Wall clock 01:30 > 01:15 would be considered future if direct comparison, but real instant B < A, should allow
    obj_id_a = new_object_id(ObjectType.ENTITY)
    obj_id_b = new_object_id(ObjectType.ENTITY)

    obj_b = DummyEntity(
        object_id=obj_id_b,
        subject_id="test",
        revision=1,
        learned_at=learned_b,
        recorded_at=learned_b,
        created_by="test",
        value="B_old",
    )
    obj_a = RefNode(
        object_id=obj_id_a,
        subject_id="test",
        revision=1,
        learned_at=learned_a,
        recorded_at=learned_a,
        created_by="test",
        link_refs=[ObjectRef(object_id=obj_id_b, revision=1)],
    )

    result = store.commit([obj_a, obj_b], make_op(0))
    assert result.world_revision == 1
    assert store.current_world_revision() == 1

    payload_a = store.get_payload(obj_id_a)
    payload_b = store.get_payload(obj_id_b)
    assert payload_a["object_id"] == obj_id_a
    assert payload_b["object_id"] == obj_id_b


# Critical model ref field check - 强化 annotation + R2 exact ObjectRef
def test_critical_model_ref_fields_annotation():
    from aios_core.contracts.models import Claim, EventAnchor, EvidenceSet, Dependency

    def assert_list_of_object_ref(model, field_name):
        hints = get_type_hints(model)
        assert field_name in hints, f"{model.__name__}.{field_name} missing in type_hints"
        annotation = hints[field_name]
        origin = get_origin(annotation)
        args = get_args(annotation)
        # Should be list[ObjectRef]
        assert origin is list, f"{model.__name__}.{field_name} should be list, got {origin} annotation {annotation}"
        assert args == (ObjectRef,), f"{model.__name__}.{field_name} should be list[ObjectRef], got {args}"

    def assert_exact_object_ref(model, field_name):
        hints = get_type_hints(model)
        assert field_name in hints, f"{model.__name__}.{field_name} missing"
        annotation = hints[field_name]
        assert annotation is ObjectRef, (
            f"{model.__name__}.{field_name} must be exactly ObjectRef, got {annotation}"
        )

    # Claim
    assert_list_of_object_ref(Claim, "support_evidence_set_refs")
    assert_list_of_object_ref(Claim, "counter_evidence_set_refs")

    # EventAnchor
    assert_list_of_object_ref(EventAnchor, "primary_claim_refs")
    assert_list_of_object_ref(EventAnchor, "evidence_set_refs")

    # EvidenceSet
    assert_list_of_object_ref(EvidenceSet, "member_refs")
    assert_list_of_object_ref(EvidenceSet, "support_refs")
    assert_list_of_object_ref(EvidenceSet, "counter_refs")
    assert_list_of_object_ref(EvidenceSet, "context_refs")

    # Dependency - 必须exactly ObjectRef，不能是 Optional
    assert_exact_object_ref(Dependency, "dependent_ref")
    assert_exact_object_ref(Dependency, "dependency_ref")
