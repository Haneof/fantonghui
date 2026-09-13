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
    # 所有prefix非空
    for p in prefixes:
        assert isinstance(p, str) and len(p) > 0, f"Empty prefix found: {p}"
    # 唯一性
    assert len(prefixes) == len(set(prefixes)), f"Duplicate prefixes found: {prefixes}"


def test_prefixes_frozen_mapping():
    # 正式冻结映射
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
    }
    assert ids_module._PREFIXES == expected


# 6. 格式测试
@pytest.mark.parametrize("obj_type", list(ObjectType))
def test_object_id_format(obj_type):
    oid = new_object_id(obj_type)
    prefix = ids_module._PREFIXES[obj_type]
    # 格式 <prefix>_[0-9a-f]{32}
    pattern = rf"^{re.escape(prefix)}_[0-9a-f]{{32}}$"
    assert re.match(pattern, oid), f"ID {oid} does not match pattern {pattern}"
    # 验证 suffix 只有32位小写十六进制
    suffix = oid.split("_", 1)[1] if "_" in oid else ""
    # 对于 dmem, dder 等前缀含下划线? 实际上 prefix不含下划线，但 split 需处理
    # 更准确：取 prefix 长度 +1 后的部分
    suffix = oid[len(prefix) + 1 :]
    assert len(suffix) == 32
    assert all(c in "0123456789abcdef" for c in suffix), f"Suffix {suffix} not lowercase hex"
    # 不能包含名字、日期、空格、斜杠等
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


# 8. 100k唯一性测试
def test_100k_uniqueness():
    start = time.time()
    n = 100_000
    ids = [new_object_id(ObjectType.ENTITY) for _ in range(n)]
    elapsed = time.time() - start
    unique = len(set(ids))
    collisions = n - unique
    print(f"\n100k generation: {n} ids, unique {unique}, collisions {collisions}, elapsed {elapsed:.2f}s")
    # 记录耗时，不设性能Gate，但报告
    assert len(ids) == 100_000
    assert unique == 100_000, f"Collisions detected: {collisions}"
    assert collisions == 0
    # 耗时报告，仅记录
    assert elapsed < 60, f"100k generation too slow: {elapsed}s"  # 宽松上限


# 9. Rename稳定性测试
def test_rename_stability():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import utc_now
    from datetime import datetime, timezone

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
        object_id=object_id,  # 同一个 object_id
        revision=2,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        canonical_name="妈妈",
    )

    assert v1.object_id == v2.object_id, "object_id must remain same across rename"
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
    # revision不是identity，object_id复用


# 11. 名称不进入ID
def test_name_not_in_id():
    # new_object_id 签名只有 object_type
    import inspect

    sig = inspect.signature(new_object_id)
    params = list(sig.parameters.keys())
    assert params == ["object_type"], f"new_object_id signature should only have object_type, got {params}"
    # 没有 name, canonical_name, label, title, timestamp, subject truth

    # 两个不同名字的 Entity，ID中不包含 canonical_name
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import utc_now

    class TestEntity(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"
        canonical_name: str = "test"

    now = utc_now()
    id1 = new_object_id(ObjectType.ENTITY)
    id2 = new_object_id(ObjectType.ENTITY)

    # 确认ID字符串中不包含 "妈妈"
    assert "妈妈" not in id1
    assert "妈妈" not in id2
    # 也不包含其他语义
    assert "未知人物A" not in id1


# 12. 测试真值泄露
def test_truth_leakage():
    secret_truth = "mother_ground_truth_8848"
    # 生成多个Entity ID
    ids = [new_object_id(ObjectType.ENTITY) for _ in range(100)]
    for oid in ids:
        assert secret_truth not in oid
        assert "mother" not in oid.lower() or "mother" in "mother_ground_truth_8848"  # 实际ID不应包含业务token
        # 更严格：ID只含 prefix + _ + hex
        assert re.match(r"^ent_[0-9a-f]{32}$", oid)

    # 验证ID函数根本不接收truth参数
    import inspect

    sig = inspect.signature(new_object_id)
    assert "truth" not in str(sig)
    assert "secret" not in str(sig).lower()

    # 真正安全保证来自：ID函数签名只有 object_type
    assert len(sig.parameters) == 1


# 13. UUID版本测试
def test_uuid_version():
    oid = new_object_id(ObjectType.ENTITY)
    prefix = ids_module._PREFIXES[ObjectType.ENTITY]
    suffix = oid[len(prefix) + 1 :]
    parsed = uuid.UUID(hex=suffix)
    assert parsed.version == 4, f"Expected UUID4, got version {parsed.version}"

    # 同样测试 operation 和 execution
    op_suffix = new_operation_id()[3:]  # op_ -> len 3
    assert uuid.UUID(hex=op_suffix).version == 4

    exec_suffix = new_execution_id()[5:]  # exec_ -> len 5
    assert uuid.UUID(hex=exec_suffix).version == 4
