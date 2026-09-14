from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from aios_core.contracts import ObjectRef
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError
from tests.unit.test_m0_gate_sixth_followup import counts, obs, op


class ExtraBox(BaseModel):
    model_config = ConfigDict(extra="allow")
    value: str


def _deep_list(depth: int) -> list[object]:
    root: list[object] = []
    cursor = root
    for _ in range(depth):
        child: list[object] = []
        cursor.append(child)
        cursor = child
    return root


def _cyclic_list() -> list[object]:
    value: list[object] = []
    value.append(value)
    return value


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param("\ud800", id="surrogate"),
        pytest.param(_cyclic_list(), id="cycle"),
        pytest.param(_deep_list(1500), id="deep"),
        pytest.param(10**5000, id="huge-int"),
    ],
)
def test_x2_fresh_unrepresentable_values_map_to_invalid_argument(tmp_path, bad_value):
    store = SQLiteWorldStore(tmp_path / "fresh.db")
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([obs(value=bad_value)], op("fresh-x2"))

    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(store.db_path) == before


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param("\ud800", id="surrogate"),
        pytest.param(_cyclic_list(), id="cycle"),
        pytest.param(_deep_list(1500), id="deep"),
        pytest.param(10**5000, id="huge-int"),
    ],
)
def test_x2_retry_unrepresentable_values_map_to_idempotency_conflict(tmp_path, bad_value):
    store = SQLiteWorldStore(tmp_path / "retry.db")
    request = op("retry-x2")
    original = obs(value="safe")
    store.commit([original], request)
    before = counts(store.db_path)

    changed = obs(value=bad_value)
    with pytest.raises(StoreError) as exc:
        store.commit([changed], request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(store.db_path) == before


def test_x3_nested_pydantic_extra_is_preserved_durably(tmp_path):
    store = SQLiteWorldStore(tmp_path / "nested-extra.db")
    obj = obs(value=ExtraBox(value="ok", hidden="secret"))

    store.commit([obj], op("nested-extra"))
    payload = store.get_payload(obj.object_id)

    assert payload["value"] == {"value": "ok", "hidden": "secret"}


def test_x3_nested_pydantic_extra_changes_replay_identity(tmp_path):
    store = SQLiteWorldStore(tmp_path / "nested-extra-replay.db")
    request = op("nested-extra-replay")
    first = obs(value=ExtraBox(value="ok", hidden="one"))
    second = obs(value=ExtraBox(value="ok", hidden="two"))

    store.commit([first], request)
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([second], request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(store.db_path) == before


def test_x3_dirty_top_level_extra_is_rejected_not_silently_dropped(tmp_path):
    store = SQLiteWorldStore(tmp_path / "dirty-extra.db")
    dirty = obs().model_copy(update={"rogue": "must-not-disappear"})
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([dirty], op("dirty-extra"))

    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(store.db_path) == before


def test_x4_dirty_frozen_ref_is_revalidated_and_normalized(tmp_path):
    store = SQLiteWorldStore(tmp_path / "dirty-ref.db")
    target = obs("target")
    store.commit([target], op("target"))

    request = op("dirty-ref", rev=1)
    dirty_ref = ObjectRef(object_id="target", revision=1).model_copy(
        update={"revision": "1"}
    )
    assert dirty_ref.revision == "1"

    reader = obs("reader", metadata={"ref": dirty_ref})
    first = store.commit([reader], request)
    assert first.world_revision == 2
    payload = store.get_payload("reader")
    assert payload["metadata"]["ref"]["revision"] == 1
    assert isinstance(payload["metadata"]["ref"]["revision"], int)

    canonical_reader = obs(
        "reader",
        metadata={"ref": ObjectRef(object_id="target", revision=1)},
    )
    replay = store.commit([canonical_reader], request)
    assert replay.idempotent_replay is True
    assert replay.world_revision == 2


def test_x4_dirty_frozen_ref_unknown_field_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "dirty-ref-extra.db")
    target = obs("target")
    store.commit([target], op("target"))

    dirty_ref = ObjectRef(object_id="target", revision=1).model_copy(
        update={"rogue": "must-not-disappear"}
    )
    reader = obs("reader", metadata={"ref": dirty_ref})
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([reader], op("dirty-ref-extra", rev=1))

    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(store.db_path) == before
