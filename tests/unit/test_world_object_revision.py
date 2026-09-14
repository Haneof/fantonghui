"""M0-005 WorldObject 公共字段与 Append-Only Revision 规则正式冻结"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import utc_now
from aios_core.storage.sqlite_store import SQLiteWorldStore, StoreError


# Helper Entity for M0-005 tests
class DummyEntity(WorldObject):
    object_type: ObjectType = ObjectType.ENTITY
    entity_kind: str = "person"
    canonical_name: str | None = None


def make_op(expected_world_revision: int = 0) -> OperationRequest:
    import uuid

    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-005 test",
        idempotency_key=str(uuid.uuid4()),
    )


# W01 公共字段集合
def test_w01_worldobject_common_fields():
    fields = set(WorldObject.model_fields.keys())
    required = {
        "object_id",
        "object_type",
        "subject_id",
        "revision",
        "occurred",
        "learned_at",
        "recorded_at",
        "source_refs",
        "created_by",
        "status",
        "metadata",
    }
    missing = required - fields
    assert not missing, f"WorldObject missing fields: {missing}"
    for f in required:
        assert f in fields


# W02 所有持久模型继承WorldObject
def test_w02_all_durable_models_inherit_worldobject():
    import aios_core.contracts.models as models_module
    import inspect

    durable = []
    for name, obj in inspect.getmembers(models_module, inspect.isclass):
        if obj.__module__ != models_module.__name__:
            continue
        if issubclass(obj, WorldObject) and obj is not WorldObject:
            durable.append(obj)

    expected_names = {
        "Observation",
        "Entity",
        "Relation",
        "DimensionDefinition",
        "DimensionMembership",
        "DimensionDerivation",
        "Claim",
        "EvidenceSet",
        "EventAnchor",
        "Summary",
        "Goal",
        "Dependency",
        "Task",
        "Wake",
        "Session",
        "Action",
        "Outcome",
        "OperationExperience",
        "ToolProposal",
    }

    found_names = {c.__name__ for c in durable}
    missing = expected_names - found_names
    assert not missing, f"Durable models missing WorldObject inheritance: {missing}"

    for cls in durable:
        for field in ["object_id", "object_type", "subject_id", "revision", "occurred", "learned_at", "recorded_at", "source_refs", "created_by", "status", "metadata"]:
            assert field in cls.model_fields, f"{cls.__name__} missing {field}"

    assert len(durable) >= 19, f"Expected at least 19 durable models, got {len(durable)}: {found_names}"


# W03 revision模型下限
def test_w03_revision_lower_bound():
    now = utc_now()

    with pytest.raises(Exception):
        DummyEntity(
            object_id="test_obj",
            subject_id="test",
            revision=0,
            learned_at=now,
            recorded_at=now,
            created_by="test",
        )

    with pytest.raises(Exception):
        DummyEntity(
            object_id="test_obj",
            subject_id="test",
            revision=-1,
            learned_at=now,
            recorded_at=now,
            created_by="test",
        )

    obj = DummyEntity(
        object_id="test_obj",
        subject_id="test",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
    )
    assert obj.revision == 1


# W04 新对象不能从rev2开始
def test_w04_new_object_cannot_start_from_rev2(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="should_fail",
    )

    op = make_op(expected_world_revision=0)

    with pytest.raises(StoreError) as excinfo:
        store.commit([obj], op)

    err = excinfo.value
    assert err.code == ErrorCode.VERSION_CONFLICT
    assert err.context["expected_revision"] == 1
    assert err.context["actual_revision"] == 2
    assert err.context["object_id"] == obj_id

    assert store.current_world_revision() == 0


# W05 写入rev1
def test_w05_write_rev1(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )

    op = make_op(expected_world_revision=0)
    result = store.commit([obj], op)

    assert result.world_revision == 1
    assert store.current_world_revision() == 1

    payload = store.get_payload(obj_id)
    assert payload["canonical_name"] == "未知人物A"
    assert payload["revision"] == 1


# W06 写入rev2
def test_w06_write_rev2(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )
    store.commit([obj1], make_op(0))

    now2 = utc_now()
    obj2 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=now2,
        recorded_at=now2,
        created_by="test",
        canonical_name="妈妈",
    )
    result = store.commit([obj2], make_op(1))

    assert result.world_revision == 2
    assert store.current_world_revision() == 2

    payload = store.get_payload(obj_id)
    assert payload["canonical_name"] == "妈妈"
    assert payload["revision"] == 2


# W07 rev1仍可精确读取
def test_w07_rev1_still_readable_after_rev2(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )
    store.commit([obj1], make_op(0))

    now2 = utc_now()
    obj2 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=now2,
        recorded_at=now2,
        created_by="test",
        canonical_name="妈妈",
    )
    store.commit([obj2], make_op(1))

    payload1 = store.get_payload(obj_id, revision=1)
    assert payload1["canonical_name"] == "未知人物A"
    assert payload1["revision"] == 1

    payload2 = store.get_payload(obj_id, revision=2)
    assert payload2["canonical_name"] == "妈妈"
    assert payload2["revision"] == 2

    latest = store.get_payload(obj_id)
    assert latest["canonical_name"] == "妈妈"
    assert latest["revision"] == 2


# W08 直接跳rev4必须失败
def test_w08_skip_rev4_must_fail(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )
    store.commit([obj1], make_op(0))

    obj2 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="妈妈",
    )
    store.commit([obj2], make_op(1))

    obj4 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=4,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="跳过",
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([obj4], make_op(2))

    err = excinfo.value
    assert err.code == ErrorCode.VERSION_CONFLICT
    assert err.context["expected_revision"] == 3
    assert err.context["actual_revision"] == 4
    assert err.context["object_id"] == obj_id


# W09 Revision失败事务必须原子回滚
def test_w09_failed_transaction_rollback(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )
    store.commit([obj1], make_op(0))

    obj2 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="妈妈",
    )
    store.commit([obj2], make_op(1))

    obj4 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=4,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="fail",
    )
    try:
        store.commit([obj4], make_op(2))
        pytest.fail("Should have raised VERSION_CONFLICT")
    except StoreError:
        pass

    assert store.current_world_revision() == 2

    latest = store.get_payload(obj_id)
    assert latest["revision"] == 2
    assert latest["canonical_name"] == "妈妈"

    with pytest.raises(StoreError) as excinfo:
        store.get_payload(obj_id, revision=4)
    assert excinfo.value.code == ErrorCode.NOT_FOUND

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT revision FROM object_revisions WHERE object_id=? ORDER BY revision",
        (obj_id,),
    ).fetchall()
    conn.close()
    revs = [r["revision"] for r in rows]
    assert revs == [1, 2]


# W10 失败以后rev3仍可正常写入
def test_w10_rev3_after_failed_rev4(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )
    store.commit([obj1], make_op(0))

    obj2 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="妈妈",
    )
    store.commit([obj2], make_op(1))

    obj4 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=4,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="fail",
    )
    with pytest.raises(StoreError):
        store.commit([obj4], make_op(2))

    obj3 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=3,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="rev3_ok",
    )
    result = store.commit([obj3], make_op(2))

    assert result.world_revision == 3
    assert store.current_world_revision() == 3

    latest = store.get_payload(obj_id)
    assert latest["revision"] == 3
    assert latest["canonical_name"] == "rev3_ok"


# W11 直接验证append-only数据库行
def test_w11_append_only_db_rows(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )
    store.commit([obj1], make_op(0))

    obj2 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="妈妈",
    )
    store.commit([obj2], make_op(1))

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT object_id, revision, payload_json FROM object_revisions WHERE object_id=? ORDER BY revision",
        (obj_id,),
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0]["revision"] == 1
    assert rows[1]["revision"] == 2

    payload1 = json.loads(rows[0]["payload_json"])
    payload2 = json.loads(rows[1]["payload_json"])

    assert "未知人物A" in json.dumps(payload1, ensure_ascii=False)
    assert payload1["canonical_name"] == "未知人物A"

    assert "妈妈" in json.dumps(payload2, ensure_ascii=False)
    assert payload2["canonical_name"] == "妈妈"


# W12 World Revision与Object Revision分离
def test_w12_world_revision_vs_object_revision_multi(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id_a = new_object_id(ObjectType.ENTITY)
    obj_id_b = new_object_id(ObjectType.ENTITY)

    obj_a1 = DummyEntity(
        object_id=obj_id_a,
        subject_id="subject_a",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="A1",
    )
    obj_b1 = DummyEntity(
        object_id=obj_id_b,
        subject_id="subject_b",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="B1",
    )

    result = store.commit([obj_a1, obj_b1], make_op(0))

    assert result.world_revision == 1
    assert store.current_world_revision() == 1

    payload_a = store.get_payload(obj_id_a)
    payload_b = store.get_payload(obj_id_b)
    assert payload_a["revision"] == 1
    assert payload_b["revision"] == 1

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT object_id, revision, world_revision FROM object_revisions ORDER BY object_id"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    for r in rows:
        assert r["world_revision"] == 1


# W13 下一次修改单个对象
def test_w13_world_revision_vs_object_revision_single(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id_a = new_object_id(ObjectType.ENTITY)
    obj_id_b = new_object_id(ObjectType.ENTITY)

    obj_a1 = DummyEntity(
        object_id=obj_id_a,
        subject_id="subject_a",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="A1",
    )
    obj_b1 = DummyEntity(
        object_id=obj_id_b,
        subject_id="subject_b",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="B1",
    )
    store.commit([obj_a1, obj_b1], make_op(0))

    obj_a2 = DummyEntity(
        object_id=obj_id_a,
        subject_id="subject_a",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="A2",
    )
    result2 = store.commit([obj_a2], make_op(1))

    assert result2.world_revision == 2
    assert store.current_world_revision() == 2

    payload_a = store.get_payload(obj_id_a)
    payload_b = store.get_payload(obj_id_b)

    assert payload_a["revision"] == 2
    assert payload_b["revision"] == 1


# W14 Append-only源码证据
def test_w14_no_update_replace_in_store_source():
    import pathlib

    store_path = pathlib.Path("src/aios_core/storage/sqlite_store.py")
    content = store_path.read_text()

    forbidden_patterns = [
        "UPDATE object_revisions",
        "REPLACE INTO object_revisions",
        "INSERT OR REPLACE INTO object_revisions",
    ]

    for pat in forbidden_patterns:
        assert pat not in content, f"Found forbidden pattern in store: {pat}"

    import re

    matches = re.findall(
        r"UPDATE\s+object_revisions|REPLACE\s+INTO\s+object_revisions|INSERT\s+OR\s+REPLACE\s+INTO\s+object_revisions",
        content,
        flags=re.IGNORECASE,
    )
    assert not matches, f"Found forbidden SQL patterns: {matches}"

# DummyClaim for object_type continuity test
class DummyClaim(WorldObject):
    object_type: ObjectType = ObjectType.CLAIM
    content: str = "test"


# W15 object_type不能跨revision变化
def test_w15_object_type_cannot_change_across_revisions(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj_entity = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="entity1",
    )
    result = store.commit([obj_entity], make_op(0))
    assert result.world_revision == 1

    # Try to change to CLAIM with same object_id rev2
    obj_claim = DummyClaim(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        content="should_fail",
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([obj_claim], make_op(1))

    err = excinfo.value
    assert err.code == ErrorCode.VERSION_CONFLICT
    assert err.context["object_id"] == obj_id
    assert err.context["expected_object_type"] == ObjectType.ENTITY.value
    assert err.context["actual_object_type"] == ObjectType.CLAIM.value


# W16 类型冲突必须完整原子回滚 (multi-object)
def test_w16_type_conflict_atomic_rollback_multi(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    # First commit ENTITY rev1
    obj_entity1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="entity1",
    )
    store.commit([obj_entity1], make_op(0))
    assert store.current_world_revision() == 1

    # Prepare a commit with both illegal CLAIM rev2 and a new legal ENTITY
    obj_id_new = new_object_id(ObjectType.ENTITY)
    obj_illegal_claim = DummyClaim(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        content="illegal",
    )
    obj_new_entity = DummyEntity(
        object_id=obj_id_new,
        subject_id="new_subject",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="new_entity",
    )

    with pytest.raises(StoreError) as excinfo:
        store.commit([obj_illegal_claim, obj_new_entity], make_op(1))

    err = excinfo.value
    assert err.code == ErrorCode.VERSION_CONFLICT

    # current_world_revision must still be 1
    assert store.current_world_revision() == 1

    # Original object latest still rev1 ENTITY
    payload_orig = store.get_payload(obj_id)
    assert payload_orig["revision"] == 1
    assert payload_orig["object_type"] == ObjectType.ENTITY.value

    # Illegal CLAIM rev2 does not exist
    with pytest.raises(StoreError) as excinfo2:
        store.get_payload(obj_id, revision=2)
    assert excinfo2.value.code == ErrorCode.NOT_FOUND

    # New ENTITY object also does not exist (entire transaction atomic)
    with pytest.raises(StoreError) as excinfo3:
        store.get_payload(obj_id_new)
    assert excinfo3.value.code == ErrorCode.NOT_FOUND

    # world_commits should not have new revision
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT world_revision FROM world_commits ORDER BY world_revision").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["world_revision"] == 1


# W17 类型冲突失败后合法rev2可恢复
def test_w17_type_conflict_recovery_legal_rev2(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    now = utc_now()
    obj_id = new_object_id(ObjectType.ENTITY)

    obj_entity1 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="entity1",
    )
    store.commit([obj_entity1], make_op(0))

    # Fail with illegal type
    obj_illegal = DummyClaim(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        content="illegal",
    )
    with pytest.raises(StoreError):
        store.commit([obj_illegal], make_op(1))

    # Now legal rev2 ENTITY should succeed
    obj_entity2 = DummyEntity(
        object_id=obj_id,
        subject_id="test_subject",
        revision=2,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        canonical_name="entity2",
    )
    result = store.commit([obj_entity2], make_op(1))

    assert result.world_revision == 2
    assert store.current_world_revision() == 2

    latest = store.get_payload(obj_id)
    assert latest["revision"] == 2
    assert latest["object_type"] == ObjectType.ENTITY.value
    assert latest["canonical_name"] == "entity2"

    # Check DB history: rev1 ENTITY, rev2 ENTITY, no CLAIM
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT revision, object_type FROM object_revisions WHERE object_id=? ORDER BY revision",
        (obj_id,),
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0]["revision"] == 1
    assert rows[0]["object_type"] == ObjectType.ENTITY.value
    assert rows[1]["revision"] == 2
    assert rows[1]["object_type"] == ObjectType.ENTITY.value
