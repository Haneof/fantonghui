"""M0-002 统一错误码、协议级错误结构与机器可恢复异常契约

CASE E01-E20 + P01-P09 + S01-S03 + 额外回归测试
"""
from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.errors import ErrorResponse
from aios_core.errors import AIOSProtocolError
from aios_core.storage.sqlite_store import StoreError


# CASE E01: 所有10个 ErrorCode 可以构造 ErrorResponse
def test_e01_all_error_codes_constructible():
    for code in ErrorCode:
        resp = ErrorResponse(code=code, message=f"test {code}", context={})
        assert resp.code == code
    assert len(list(ErrorCode)) == 10
    expected = {
        "INVALID_ARGUMENT",
        "NOT_FOUND",
        "VERSION_CONFLICT",
        "INCOMPLETE_DATA",
        "STALE_INDEX",
        "BUDGET_EXHAUSTED",
        "PERMISSION_DENIED",
        "DEPENDENCY_INVALID",
        "OUTCOME_UNKNOWN",
        "IDEMPOTENCY_CONFLICT",
    }
    actual = {c.value for c in ErrorCode}
    assert actual == expected


# CASE E02: ErrorResponse code/message/context 可以 model_dump(mode="json")
def test_e02_error_response_json_dump():
    resp = ErrorResponse(
        code=ErrorCode.NOT_FOUND,
        message="object not found",
        context={"object_id": "obj_123", "revision": 1},
    )
    dumped = resp.model_dump(mode="json")
    assert dumped["code"] == "NOT_FOUND"
    assert dumped["message"] == "object not found"
    assert dumped["context"]["object_id"] == "obj_123"
    json_str = json.dumps(dumped)
    assert "NOT_FOUND" in json_str


# CASE E03: 未知 ErrorCode 被拒绝
def test_e03_unknown_error_code_rejected():
    with pytest.raises(ValidationError):
        ErrorResponse(code="UNKNOWN_CODE", message="x", context={})  # type: ignore
    with pytest.raises(ValidationError):
        ErrorResponse(code="FAKE_ERROR", message="x", context={})  # type: ignore
    with pytest.raises((ValidationError, TypeError)):
        ErrorResponse(code=123, message="x", context={})  # type: ignore


# CASE E04: 空 message 被拒绝 (清理重复)
def test_e04_empty_message_rejected():
    with pytest.raises(ValidationError):
        ErrorResponse(code=ErrorCode.NOT_FOUND, message="", context={})


# CASE E05: 额外字段被拒绝
def test_e05_extra_fields_rejected():
    with pytest.raises(ValidationError):
        ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="x",
            context={},
            extra_field="not allowed",  # type: ignore
        )
    with pytest.raises(ValidationError):
        ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="x",
            context={},
            traceback="should not be allowed",  # type: ignore
        )


# CASE E06: 非JSON context 值被拒绝
def test_e06_non_json_context_rejected():
    with pytest.raises(ValidationError):
        ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="x",
            context={"obj": object()},  # type: ignore
        )
    with pytest.raises(ValidationError):
        ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="x",
            context={"file": open},  # type: ignore
        )
    ok = ErrorResponse(
        code=ErrorCode.NOT_FOUND,
        message="x",
        context={
            "str": "a",
            "int": 1,
            "float": 1.5,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        },
    )
    assert ok.context["str"] == "a"


# CASE E07: AIOSProtocolError .code .message .context 正确
def test_e07_protocol_error_properties():
    err = AIOSProtocolError(
        ErrorCode.VERSION_CONFLICT,
        "version conflict",
        context={"expected_world_revision": 3, "current_world_revision": 4},
    )
    assert err.code == ErrorCode.VERSION_CONFLICT
    assert err.message == "version conflict"
    assert err.context["expected_world_revision"] == 3
    assert err.context["current_world_revision"] == 4
    assert str(err) == "version conflict"


# CASE E08: AIOSProtocolError.to_response() 产生相同协议语义
def test_e08_to_response_same_semantics():
    err = AIOSProtocolError(
        ErrorCode.NOT_FOUND,
        "object not found",
        context={"object_id": "obj_123"},
    )
    resp = err.to_response()
    assert isinstance(resp, ErrorResponse)
    assert resp.code == err.code
    assert resp.message == err.message
    assert resp.context == err.context
    assert resp.model_dump(mode="json")["code"] == "NOT_FOUND"


# CASE E09: StoreError 是 AIOSProtocolError 的子类
def test_e09_store_error_subclass():
    assert issubclass(StoreError, AIOSProtocolError)
    err = StoreError(ErrorCode.NOT_FOUND, "not found", context={"object_id": "x"})
    assert isinstance(err, AIOSProtocolError)
    assert isinstance(err, StoreError)


# CASE E10: StoreError 仍可被 except StoreError 捕获
def test_e10_store_error_catchable_as_store_error():
    try:
        raise StoreError(ErrorCode.NOT_FOUND, "not found", context={"object_id": "x"})
    except StoreError as e:
        assert e.code == ErrorCode.NOT_FOUND
    else:
        pytest.fail("should have raised StoreError")


# CASE E11: StoreError 也可被 except AIOSProtocolError 统一捕获
def test_e11_store_error_catchable_as_protocol_error():
    try:
        raise StoreError(ErrorCode.NOT_FOUND, "not found", context={"object_id": "x"})
    except AIOSProtocolError as e:
        assert e.code == ErrorCode.NOT_FOUND
    else:
        pytest.fail("should have been caught as AIOSProtocolError")


# CASE E12: world revision conflict context
def test_e12_world_revision_conflict_context(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    from aios_core.contracts.time import utc_now
    import uuid

    class DummyObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"
        payload: str = "x"

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)
    obj1 = DummyObj(
        object_id="obj1",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        payload="a",
    )
    op1 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obj1], op1)

    obj2 = DummyObj(
        object_id="obj2",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        payload="b",
    )
    op2 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    try:
        store.commit([obj2], op2)
        pytest.fail("should have raised VERSION_CONFLICT")
    except StoreError as e:
        assert e.code == ErrorCode.VERSION_CONFLICT
        assert "expected_world_revision" in e.context
        assert "current_world_revision" in e.context
        assert e.context["expected_world_revision"] == 0
        assert e.context["current_world_revision"] == 1


# CASE E13: object revision conflict context
def test_e13_object_revision_conflict_context(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    from aios_core.contracts.time import utc_now
    import uuid

    class DummyObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"
        payload: str = "x"

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)
    obj1 = DummyObj(
        object_id="obj1",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        payload="a",
    )
    op1 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obj1], op1)

    obj1_dup = DummyObj(
        object_id="obj1",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        payload="b",
    )
    op2 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=1,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    try:
        store.commit([obj1_dup], op2)
        pytest.fail("should have raised VERSION_CONFLICT")
    except StoreError as e:
        assert e.code == ErrorCode.VERSION_CONFLICT
        assert e.context["object_id"] == "obj1"
        assert e.context["expected_revision"] == 2
        assert e.context["actual_revision"] == 1


# CASE E14: NOT_FOUND 读取对象 context 含 object_id
def test_e14_not_found_read_object(tmp_path):
    from aios_core.storage.sqlite_store import SQLiteWorldStore

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)
    try:
        store.get_payload("nonexistent_obj")
        pytest.fail("should have raised NOT_FOUND")
    except StoreError as e:
        assert e.code == ErrorCode.NOT_FOUND
        assert e.context["object_id"] == "nonexistent_obj"


# CASE E15: 不存在引用 context 包含 referenced_object_id 和 referenced_revision
def test_e15_reference_not_found_context(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.contracts.refs import ObjectRef
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    from aios_core.contracts.time import utc_now
    import uuid

    class ObjWithRef(WorldObject):
        object_type: ObjectType = ObjectType.CLAIM
        subject_id: str = "test"
        ref: ObjectRef

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obj = ObjWithRef(
        object_id="obj1",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        ref=ObjectRef(object_id="missing_obj", revision=1),
    )
    op = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    try:
        store.commit([obj], op)
        pytest.fail("should have raised NOT_FOUND for missing reference")
    except StoreError as e:
        assert e.code == ErrorCode.NOT_FOUND
        assert e.context["referenced_object_id"] == "missing_obj"
        assert e.context["referenced_revision"] == 1

    obj2 = ObjWithRef(
        object_id="obj2",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        ref=ObjectRef(object_id="missing_obj2", revision=None),
    )
    op2 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    try:
        store.commit([obj2], op2)
        pytest.fail("should have raised NOT_FOUND")
    except StoreError as e:
        assert e.code == ErrorCode.NOT_FOUND
        assert e.context["referenced_object_id"] == "missing_obj2"
        assert e.context["referenced_revision"] is None


# CASE E16: OUTCOME_UNKNOWN 模拟Action timeout
def test_e16_outcome_unknown_action_timeout():
    try:
        raise TimeoutError("action timed out after 30s")
    except TimeoutError as cause:
        err = AIOSProtocolError(
            ErrorCode.OUTCOME_UNKNOWN,
            "action outcome unknown due to timeout",
            context={
                "action_id": "act_123",
                "cause": "timeout",
            },
        )
        err.__cause__ = cause
        assert err.code == ErrorCode.OUTCOME_UNKNOWN
        resp = err.to_response()
        assert resp.code == ErrorCode.OUTCOME_UNKNOWN
        assert resp.context["action_id"] == "act_123"
        assert resp.context["cause"] == "timeout"


# CASE E17: OUTCOME_UNKNOWN 不被自动改为普通 FAILED
def test_e17_outcome_unknown_not_failed():
    err = AIOSProtocolError(
        ErrorCode.OUTCOME_UNKNOWN,
        "unknown outcome",
        context={"action_id": "act_456"},
    )
    resp = err.to_response()
    assert resp.code == ErrorCode.OUTCOME_UNKNOWN
    assert resp.code != ErrorCode.NOT_FOUND
    assert resp.code.value == "OUTCOME_UNKNOWN"


# CASE E18: NOT_FOUND 与 INCOMPLETE_DATA 是不同 code
def test_e18_not_found_vs_incomplete_data():
    not_found = ErrorResponse(
        code=ErrorCode.NOT_FOUND, message="object not found", context={"object_id": "x"}
    )
    incomplete = ErrorResponse(
        code=ErrorCode.INCOMPLETE_DATA,
        message="incomplete data for judgment",
        context={"object_id": "x", "missing_fields": ["sleep_end"]},
    )
    assert not_found.code != incomplete.code
    assert not_found.code == ErrorCode.NOT_FOUND
    assert incomplete.code == ErrorCode.INCOMPLETE_DATA


# CASE E19: VERSION_CONFLICT 与 IDEMPOTENCY_CONFLICT 是不同 code
def test_e19_version_vs_idempotency_conflict():
    version_err = ErrorResponse(
        code=ErrorCode.VERSION_CONFLICT,
        message="version conflict",
        context={"expected_world_revision": 1, "current_world_revision": 2},
    )
    idempotency_err = ErrorResponse(
        code=ErrorCode.IDEMPOTENCY_CONFLICT,
        message="idempotency conflict",
        context={"idempotency_key": "key123"},
    )
    assert version_err.code != idempotency_err.code
    assert version_err.code == ErrorCode.VERSION_CONFLICT
    assert idempotency_err.code == ErrorCode.IDEMPOTENCY_CONFLICT


# CASE E20: ErrorResponse 不包含 traceback 字段
def test_e20_no_traceback_in_response():
    err = AIOSProtocolError(
        ErrorCode.INVALID_ARGUMENT, "invalid", context={"field": "x"}
    )
    resp = err.to_response()
    dumped = resp.model_dump(mode="json")
    assert "traceback" not in dumped
    assert "traceback" not in dumped.get("context", {})
    assert "traceback" not in json.dumps(dumped).lower()


# 额外：禁止message业务分支的回归测试
def test_message_independence_classify():
    def classify(error: ErrorResponse) -> str:
        if error.code == ErrorCode.VERSION_CONFLICT:
            return "retry_after_refresh"
        elif error.code == ErrorCode.NOT_FOUND:
            return "create_new"
        elif error.code == ErrorCode.OUTCOME_UNKNOWN:
            return "check_manually"
        else:
            return "other"

    err1 = ErrorResponse(
        code=ErrorCode.VERSION_CONFLICT,
        message="文本A",
        context={"expected_world_revision": 1, "current_world_revision": 2},
    )
    err2 = ErrorResponse(
        code=ErrorCode.VERSION_CONFLICT,
        message="完全重写后的文本B",
        context={"expected_world_revision": 1, "current_world_revision": 2},
    )
    assert classify(err1) == classify(err2) == "retry_after_refresh"

    err3 = ErrorResponse(
        code=ErrorCode.NOT_FOUND,
        message="文本A",
        context={"object_id": "x"},
    )
    assert classify(err3) == "create_new"
    assert classify(err3) != classify(err1)


# 协议错误不可泄露内部异常
def test_safe_serialization_no_leak():
    try:
        raise ValueError("internal sensitive diagnostic")
    except ValueError as cause:
        err = AIOSProtocolError(
            ErrorCode.INVALID_ARGUMENT,
            "invalid request",
            context={"field": "x"},
        )
        err.__cause__ = cause

    resp = err.to_response()
    dumped = resp.model_dump(mode="json")
    json_str = json.dumps(dumped)
    assert "internal sensitive diagnostic" not in json_str
    assert "ValueError" not in json_str
    assert "traceback" not in json_str.lower()
    assert err.__cause__ is not None
    assert "internal sensitive diagnostic" in str(err.__cause__)


# STALE_INDEX, BUDGET_EXHAUSTED, PERMISSION_DENIED, DEPENDENCY_INVALID 可构造性
def test_other_error_codes_constructible():
    for code in [
        ErrorCode.STALE_INDEX,
        ErrorCode.BUDGET_EXHAUSTED,
        ErrorCode.PERMISSION_DENIED,
        ErrorCode.DEPENDENCY_INVALID,
    ]:
        resp = ErrorResponse(
            code=code,
            message=f"{code.value} occurred",
            context={"detail": "test"},
        )
        assert resp.code == code
        assert json.dumps(resp.model_dump(mode="json"))


# 测试 operation not found context
def test_operation_not_found_context(tmp_path):
    from aios_core.storage.sqlite_store import SQLiteWorldStore

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)
    try:
        store.operation_record("nonexistent_op")
        pytest.fail("should have raised NOT_FOUND")
    except StoreError as e:
        assert e.code == ErrorCode.NOT_FOUND
        assert e.context["operation_id"] == "nonexistent_op"


# ========== R1 新增 P01-P09 ==========

# P01 AIOSProtocolError构造阶段拒绝 object()
def test_p01_protocol_error_rejects_object_at_construction():
    with pytest.raises(ValidationError):
        AIOSProtocolError(
            ErrorCode.INVALID_ARGUMENT,
            "bad request",
            context={"bad": object()},  # type: ignore
        )


# P02 AIOSProtocolError构造阶段拒绝 open
def test_p02_protocol_error_rejects_non_json_at_construction():
    with pytest.raises(ValidationError):
        AIOSProtocolError(
            ErrorCode.INVALID_ARGUMENT,
            "bad request",
            context={"bad": open},  # type: ignore
        )


# P03 ErrorResponse拒绝 NaN
def test_p03_error_response_rejects_nan():
    with pytest.raises(ValidationError):
        ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="x",
            context={"v": float("nan")},
        )


# P04 ErrorResponse拒绝 Infinity
@pytest.mark.parametrize("inf_val", [float("inf"), float("-inf")])
def test_p04_error_response_rejects_infinity(inf_val):
    with pytest.raises(ValidationError):
        ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="x",
            context={"v": inf_val},
        )


# P05 AIOSProtocolError同样拒绝 NaN/Infinity
@pytest.mark.parametrize("bad_val", [float("nan"), float("inf"), float("-inf")])
def test_p05_protocol_error_rejects_nan_inf(bad_val):
    with pytest.raises(ValidationError):
        AIOSProtocolError(
            ErrorCode.NOT_FOUND,
            "x",
            context={"v": bad_val},
        )


# P06 合法协议 json.dumps allow_nan=False 成功
def test_p06_legal_json_dumps_strict():
    resp = ErrorResponse(
        code=ErrorCode.NOT_FOUND,
        message="x",
        context={"a": 1, "b": None, "c": [1, 2], "d": {"nested": "ok"}},
    )
    dumped = resp.model_dump(mode="json")
    # 必须能够 json.dumps with allow_nan=False
    json_str = json.dumps(dumped, allow_nan=False)
    assert "NOT_FOUND" in json_str
    # 验证标准 JSON
    parsed = json.loads(json_str)
    assert parsed["code"] == "NOT_FOUND"


# P07 原始context隔离
def test_p07_original_context_isolation():
    ctx = {"value": 1, "nested": {"a": 1}}
    err = AIOSProtocolError(
        ErrorCode.INVALID_ARGUMENT,
        "x",
        context=ctx,
    )
    # 修改原始 dict
    ctx["value"] = 2
    ctx["nested"]["a"] = 999
    ctx["new_key"] = "polluted"
    # 必须仍然是原值
    assert err.context["value"] == 1
    assert err.context["nested"]["a"] == 1
    assert "new_key" not in err.context


# P08 context getter隔离
def test_p08_context_getter_isolation():
    err = AIOSProtocolError(
        ErrorCode.INVALID_ARGUMENT,
        "x",
        context={"value": 1},
    )
    returned = err.context
    returned["value"] = 999
    returned["new"] = "polluted"
    # 再次获取必须仍是原值
    assert err.context["value"] == 1
    assert "new" not in err.context


# P09 to_response稳定
def test_p09_to_response_stable():
    ctx = {"value": 1}
    err = AIOSProtocolError(
        ErrorCode.INVALID_ARGUMENT,
        "x",
        context=ctx,
    )
    resp1 = err.to_response()
    # 执行外部修改
    ctx["value"] = 2
    returned = err.context
    returned["value"] = 999
    # to_response 仍应得到原始合法内容
    resp2 = err.to_response()
    assert resp1.context["value"] == 1
    assert resp2.context["value"] == 1
    assert resp1.model_dump(mode="json")["context"]["value"] == 1


# ========== R1 新增 S01-S03 ==========

# S01 空commit context
def test_s01_empty_commit_context(tmp_path):
    from aios_core.contracts.operations import OperationRequest
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    import uuid

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)
    op = OperationRequest(
        operation_id="op_empty",
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    try:
        store.commit([], op)
        pytest.fail("should have raised INVALID_ARGUMENT")
    except StoreError as e:
        assert e.code == ErrorCode.INVALID_ARGUMENT
        assert e.context["operation_id"] == "op_empty"
        assert e.context["reason"] == "empty_commit"


# S02 duplicate revision context
def test_s02_duplicate_revision_context(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    from aios_core.contracts.time import utc_now
    import uuid

    class DummyObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"
        payload: str = "x"

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obj1 = DummyObj(
        object_id="dup_obj",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        payload="a",
    )
    obj2 = DummyObj(
        object_id="dup_obj",
        revision=1,  # duplicate
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        payload="b",
    )
    op = OperationRequest(
        operation_id="op_dup",
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    try:
        store.commit([obj1, obj2], op)
        pytest.fail("should have raised INVALID_ARGUMENT for duplicate")
    except StoreError as e:
        assert e.code == ErrorCode.INVALID_ARGUMENT
        assert e.context["operation_id"] == "op_dup"
        assert e.context["reason"] == "duplicate_revision"


# S03 当前对象引用自己的当前revision context
def test_s03_self_current_reference_context(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.contracts.refs import ObjectRef
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    from aios_core.contracts.time import utc_now
    import uuid

    class ObjSelfRef(WorldObject):
        object_type: ObjectType = ObjectType.CLAIM
        subject_id: str = "test"
        ref: ObjectRef

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obj = ObjSelfRef(
        object_id="self_obj",
        revision=1,
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        ref=ObjectRef(object_id="self_obj", revision=1),  # self current
    )
    op = OperationRequest(
        operation_id="op_self",
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    try:
        store.commit([obj], op)
        pytest.fail("should have raised DEPENDENCY_INVALID")
    except StoreError as e:
        assert e.code == ErrorCode.DEPENDENCY_INVALID
        assert e.context["object_id"] == "self_obj"
        assert e.context["revision"] == 1
