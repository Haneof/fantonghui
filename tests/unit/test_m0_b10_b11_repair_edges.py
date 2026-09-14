"""B10/B11 independent boundary probes, written before the repair."""

from enum import Enum, IntEnum, StrEnum
import sqlite3

import pytest

from aios_core.contracts import ObjectType
from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.registry import CANONICAL_WORLD_OBJECT_MODELS
from aios_core.storage import SQLiteWorldStore, StoreError
from aios_core.storage.idempotency import request_fingerprint
from tests.unit.test_m0_gate_fifth_followup import obs, op


@pytest.mark.parametrize("declared", ["unknown-type", None, ["dependency"]])
@pytest.mark.parametrize("retry", [False, True])
def test_b10_unknown_dirty_type_is_protocol_rejection(tmp_path, declared, retry):
    store = SQLiteWorldStore(tmp_path / "world.db")
    request = op(0, "dirty")
    obj = obs("obj", "ok")
    if retry:
        store.commit([obj], request)
    dirty = obj.model_copy(update={"object_type": declared})
    with pytest.raises(StoreError) as exc:
        store.commit([dirty], request)
    assert exc.value.code is (
        ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT
    )
    assert store.current_world_revision() == int(retry)
    with sqlite3.connect(store.db_path) as conn:
        for table in (
            "world_commits",
            "object_revisions",
            "operations",
            "idempotency_records",
        ):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == int(
                retry
            )


def test_b10_registry_cannot_be_mutated_to_authorize_base_model():
    from aios_core.contracts import WorldObject

    original = CANONICAL_WORLD_OBJECT_MODELS[ObjectType.DEPENDENCY]
    try:
        with pytest.raises(TypeError):
            CANONICAL_WORLD_OBJECT_MODELS[ObjectType.DEPENDENCY] = WorldObject
    finally:
        # Restore only on the pre-fix mutable registry, avoiding test pollution.
        if isinstance(CANONICAL_WORLD_OBJECT_MODELS, dict):
            CANONICAL_WORLD_OBJECT_MODELS[ObjectType.DEPENDENCY] = original


@pytest.mark.parametrize("declared", [ObjectType.DEPENDENCY, ObjectType.EVIDENCE_SET])
def test_b10_runtime_class_mismatch_is_rejected(tmp_path, declared):
    store = SQLiteWorldStore(tmp_path / "world.db")
    dirty = obs("obj", "ok").model_copy(update={"object_type": declared})
    with pytest.raises(StoreError) as exc:
        store.commit([dirty], op(0, "mismatch"))
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert store.current_world_revision() == 0


class TextKey(StrEnum):
    KEY = "key"


class NumberKey(IntEnum):
    KEY = 1


class OpaqueKey(Enum):
    KEY = "key"


@pytest.mark.parametrize(
    "key", [1, None, True, (1, "a"), NumberKey.KEY, OpaqueKey.KEY, b"key"]
)
@pytest.mark.parametrize("slot", ["object", "arguments"])
def test_b11_nested_nonstring_key_domain(tmp_path, key, slot):
    store = SQLiteWorldStore(tmp_path / "world.db")
    # Python itself equates True and 1 as dict keys; we test the remaining key,
    # not a fictional two-entry mapping that Python has already collapsed.
    value = {"nested": {key: "nonstring", str(key): "string"}}
    obj = obs("obj", value if slot == "object" else "ok")
    request = op(0, "key-domain")
    if slot == "arguments":
        request.arguments = value
    with pytest.raises(StoreError) as exc:
        store.commit([obj], request)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert store.current_world_revision() == 0


def test_b11_string_enum_order_and_distinct_identity(tmp_path):
    request = op(0, "ordered")
    a = obs("obj", {"nested": {"a": 1, TextKey.KEY: "v"}, "z": 2})
    b = obs("obj", {"z": 2, "nested": {"key": "v", "a": 1}})
    c = obs("obj", {"z": 2, "nested": {"key": "different", "a": 1}})
    assert request_fingerprint(request, [a]) == request_fingerprint(request, [b])
    assert request_fingerprint(request, [a]) != request_fingerprint(request, [c])
    store = SQLiteWorldStore(tmp_path / "world.db")
    store.commit([a], request)
    assert SQLiteWorldStore(store.db_path).commit([b], request).idempotent_replay
    assert store.get_payload("obj")["value"] == b.value
    with pytest.raises(StoreError) as exc:
        store.commit([c], request)
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
