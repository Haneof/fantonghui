"""M0-003 稳定对象 ID 生成器正式冻结与验证"""
from __future__ import annotations

import re
import time
import uuid

import pytest

from aios_core.contracts.enums import ObjectType
import aios_core.contracts.ids as ids_module
from aios_core.contracts.ids import new_object_id, new_operation_id, new_execution_id


# 5. ObjectType完整性测试
def test_prefixes_cover_all_object_types():
    assert set(ids_module._PREFIXES.keys()) == set(ObjectType), (
        f"Missing ObjectType in _PREFIXES: {set(ObjectType) - set(ids_module._PREFIXES.keys())}, "
        f"Extra: {set(ids_module._PREFIXES.keys()) - set(ObjectType)}"
    )


def test_prefixes_non_empty_and_unique():
    prefixes = list(ids_module._PREFIXES.values())
    for p in prefixes:
        assert isinstance(p, str) and len(p) > 0, f"Empty prefix found: {p}"
    assert len(prefixes) == len(set(prefixes)), f"Duplicate prefixes found: {prefixes}"


def test_prefixes_frozen_mapping():
    expected = {
        ObjectType.OBSERVATION: "obs",
        ObjectType.ENTITY: "ent",
        ObjectType.RELATION: "rel",
        ObjectType.DIMENSION_DEFINITION: "dim",
        ObjectType.DIMENSION_MEMBERSHIP: "dmem",
        ObjectType.DIMENSION_DERIVATION: "dder",
        ObjectType.CLAIM: "clm",
        ObjectType.EVIDENCE_SET: "evs",
        ObjectType.EVENT: "evt",
        ObjectType.SUMMARY: "sum",
        ObjectType.GOAL: "gol",
        ObjectType.DEPENDENCY: "dep",
        ObjectType.TASK: "tsk",
        ObjectType.WAKE: "wak",
        ObjectType.SESSION: "ses",
        ObjectType.ACTION: "act",
        ObjectType.OUTCOME: "out",
        ObjectType.OPERATION_EXPERIENCE: "exp",
        ObjectType.TOOL_PROPOSAL: "tlp",
        ObjectType.PREDICTION: "prd",
        ObjectType.LIFE_CHAPTER: "lfc",
        ObjectType.REINTERPRETATION: "rip",
        ObjectType.COMMUNICATION_EXPERIENCE: "cxp",
        ObjectType.BUDGET_POLICY: "bgp",
        ObjectType.ASSEMBLY_POLICY: "asp",
        ObjectType.NARRATIVE_SEGMENT: "nsg",
        ObjectType.DIMENSION_CURVE_POINT: "dcp",
    }
    assert ids_module._PREFIXES == expected


# 6. 格式测试
@pytest.mark.parametrize("obj_type", list(ObjectType))
def test_object_id_format(obj_type):
    oid = new_object_id(obj_type)
    prefix = ids_module._PREFIXES[obj_type]
    pattern = rf"^{re.escape(prefix)}_[0-9a-f]{{32}}$"
    assert re.match(pattern, oid), f"ID {oid} does not match pattern {pattern}"
    suffix = oid[len(prefix) + 1 :]
    assert len(suffix) == 32
    assert all(c in "0123456789abcdef" for c in suffix), f"Suffix {suffix} not lowercase hex"
    assert " " not in oid
    assert "/" not in oid
    assert "\n" not in oid


# 7. Operation / Execution ID
def test_operation_id_format():
    oid = new_operation_id()
    pattern = r"^op_[0-9a-f]{32}$"
    assert re.match(pattern, oid), f"Operation ID {oid} does not match {pattern}"


def test_execution_id_format():
    eid = new_execution_id()
    pattern = r"^exec_[0-9a-f]{32}$"
    assert re.match(pattern, eid), f"Execution ID {eid} does not match {pattern}"


def test_operation_execution_uniqueness_1000():
    ops = [new_operation_id() for _ in range(1000)]
    execs = [new_execution_id() for _ in range(1000)]
    assert len(set(ops)) == 1000, "Operation IDs not unique in 1000 batch"
    assert len(set(execs)) == 1000, "Execution IDs not unique in 1000 batch"


# 8. 100k唯一性测试 - 仅记录观测指标，不设性能Gate
def test_100k_uniqueness():
    start = time.time()
    n = 100_000
    ids = [new_object_id(ObjectType.ENTITY) for _ in range(n)]
    elapsed = time.time() - start
    unique = len(set(ids))
    collisions = n - unique
    print(f"\n100k generation: {n} ids, unique {unique}, collisions {collisions}, elapsed {elapsed:.2f}s")
    print("100k generation elapsed仅作为观测指标，不属于M0-003验收Gate")
    assert len(ids) == 100_000
    assert unique == 100_000, f"Collisions detected: {collisions}"
    assert collisions == 0
    # 不设性能Gate，耗时不决定 PASS/FAIL


# 9. Rename稳定性测试
def test_rename_stability():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import utc_now

    class TestEntity(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test_subject"
        canonical_name: str = "unknown"

    now = utc_now()
    object_id = new_object_id(ObjectType.ENTITY)

    v1 = TestEntity(
        object_id=object_id,
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )
    v2 = TestEntity(
        object_id=object_id,
        revision=2,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="妈妈",
    )

    assert v1.object_id == v2.object_id
    assert v1.canonical_name != v2.canonical_name
    assert v1.object_id == object_id
    assert v2.object_id == object_id


# 10. Revision稳定性测试 (非Entity例子)
def test_revision_stability_event():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import utc_now

    class TestEvent(WorldObject):
        object_type: ObjectType = ObjectType.EVENT
        subject_id: str = "test_event_subject"
        title: str = "event title"

    now = utc_now()
    object_id = new_object_id(ObjectType.EVENT)

    v1 = TestEvent(
        object_id=object_id,
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        title="first version",
    )
    v2 = TestEvent(
        object_id=object_id,
        revision=2,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        title="second version revised",
    )

    assert v1.object_id == v2.object_id
    assert v1.revision == 1
    assert v2.revision == 2


# 11. 名称不进入ID - 补强：真正实例化不同canonical_name的Entity
def test_name_not_in_id():
    import inspect
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import utc_now

    # 验证生成器参数只有 object_type
    sig = inspect.signature(new_object_id)
    params = list(sig.parameters.keys())
    assert params == ["object_type"], f"new_object_id signature should only have object_type, got {params}"

    class TestEntity(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"
        canonical_name: str = "test"

    now = utc_now()

    # 真正执行场景：创建两个带不同canonical_name的Entity
    entity_a = TestEntity(
        object_id=new_object_id(ObjectType.ENTITY),
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="未知人物A",
    )

    entity_b = TestEntity(
        object_id=new_object_id(ObjectType.ENTITY),
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="妈妈",
    )

    # 验证 canonical_name not in object_id
    assert entity_a.canonical_name not in entity_a.object_id, (
        f"canonical_name '{entity_a.canonical_name}' should not be in object_id '{entity_a.object_id}'"
    )
    assert entity_b.canonical_name not in entity_b.object_id, (
        f"canonical_name '{entity_b.canonical_name}' should not be in object_id '{entity_b.object_id}'"
    )

    # 两个Entity是不同身份，object_id应该不同 (随机唯一性，非数学证明)
    assert entity_a.object_id != entity_b.object_id

    # 额外：ID中不包含其他语义
    assert "未知人物A" not in entity_a.object_id
    assert "妈妈" not in entity_b.object_id


# 12. 测试真值泄露
def test_truth_leakage():
    secret_truth = "mother_ground_truth_8848"
    ids = [new_object_id(ObjectType.ENTITY) for _ in range(100)]
    for oid in ids:
        assert secret_truth not in oid
        assert re.match(r"^ent_[0-9a-f]{32}$", oid)

    import inspect

    sig = inspect.signature(new_object_id)
    assert "truth" not in str(sig)
    assert "secret" not in str(sig).lower()
    assert len(sig.parameters) == 1


# 13. UUID版本测试
def test_uuid_version():
    oid = new_object_id(ObjectType.ENTITY)
    prefix = ids_module._PREFIXES[ObjectType.ENTITY]
    suffix = oid[len(prefix) + 1 :]
    parsed = uuid.UUID(hex=suffix)
    assert parsed.version == 4

    op_suffix = new_operation_id()[3:]
    assert uuid.UUID(hex=op_suffix).version == 4

    exec_suffix = new_execution_id()[5:]
    assert uuid.UUID(hex=exec_suffix).version == 4
