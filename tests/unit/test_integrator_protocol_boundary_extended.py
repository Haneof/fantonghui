from __future__ import annotations

import pytest

from aios_core.contracts import ObjectRef, SourceRef
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError
from tests.unit.test_m0_gate_sixth_followup import counts, obs, op


def _bad_values():
    cycle: list[object] = []
    cycle.append(cycle)
    deep: object = "leaf"
    for _ in range(1500):
        deep = [deep]
    return ["\ud800", cycle, deep, 10**5000]


@pytest.mark.parametrize("bad", _bad_values(), ids=["surrogate", "cycle", "deep", "huge-int"])
def test_bad_operation_arguments_are_invalid_argument_without_writes(tmp_path, bad):
    store = SQLiteWorldStore(tmp_path / "fresh.db")
    request = op("bad-args", arguments={"bad": bad})
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([obs("reader")], request)

    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(store.db_path) == before


@pytest.mark.parametrize("bad", _bad_values(), ids=["surrogate", "cycle", "deep", "huge-int"])
def test_bad_operation_arguments_retry_is_conflict_without_writes(tmp_path, bad):
    path = tmp_path / "retry.db"
    store = SQLiteWorldStore(path)
    request = op("bad-args-retry", arguments={"bad": "safe"})
    store.commit([obs("reader")], request)
    before = counts(path)

    dirty = request.model_copy(update={"arguments": {"bad": bad}})
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([obs("reader")], dirty)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(path) == before


def test_unbindable_dirty_idempotency_key_is_invalid_argument_not_storage_failure(tmp_path):
    store = SQLiteWorldStore(tmp_path / "bad-key.db")
    request = op("valid-key").model_copy(update={"idempotency_key": ["not", "a", "key"]})
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([obs("reader")], request)

    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(store.db_path) == before


def test_coercible_dirty_idempotency_key_can_find_exact_replay(tmp_path):
    path = tmp_path / "coercible-key.db"
    store = SQLiteWorldStore(path)
    request = op("coercible-key")
    store.commit([obs("reader")], request)
    before = counts(path)

    dirty = request.model_copy(update={"idempotency_key": b"coercible-key"})
    replay = SQLiteWorldStore(path).commit([obs("reader")], dirty)

    assert replay.idempotent_replay is True
    assert replay.world_revision == 1
    assert counts(path) == before


def test_sourceref_and_opaque_dict_do_not_alias_replay(tmp_path):
    path = tmp_path / "source-ref.db"
    store = SQLiteWorldStore(path)
    request = op("source-ref-alias")
    opaque = obs(
        "reader",
        metadata={"ref": {"object_id": "missing", "revision": 1, "source_locator": "x"}},
    )
    store.commit([opaque], request)
    before = counts(path)

    typed = obs(
        "reader",
        metadata={"ref": SourceRef(object_id="missing", revision=1, source_locator="x")},
    )
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([typed], request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(path) == before


def test_typed_ref_in_operation_arguments_is_semantically_distinct_from_opaque_dict(tmp_path):
    path = tmp_path / "op-ref.db"
    store = SQLiteWorldStore(path)
    request = op(
        "op-ref-alias",
        arguments={"ref": {"object_id": "missing", "revision": 1}},
    )
    store.commit([obs("reader")], request)
    before = counts(path)

    typed = request.model_copy(
        update={"arguments": {"ref": ObjectRef(object_id="missing", revision=1)}}
    )
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([obs("reader")], typed)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(path) == before


def test_dirty_sourceref_revision_is_revalidated_and_exact_retry_replays(tmp_path):
    path = tmp_path / "dirty-source-ref.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))

    canonical_ref = SourceRef(object_id="target", revision=1, source_locator="loc")
    dirty_ref = canonical_ref.model_copy(update={"revision": "1"})
    request = op("dirty-source-reader", rev=1)
    reader = obs("reader", metadata={"ref": dirty_ref})
    store.commit([reader], request)
    payload = store.get_payload("reader")
    assert payload["metadata"]["ref"]["revision"] == 1
    before = counts(path)

    canonical_reader = obs("reader", metadata={"ref": canonical_ref})
    replay = SQLiteWorldStore(path).commit([canonical_reader], request)
    assert replay.idempotent_replay is True
    assert counts(path) == before


def test_dirty_sourceref_unknown_extra_is_rejected(tmp_path):
    store = SQLiteWorldStore(tmp_path / "dirty-source-extra.db")
    dirty_ref = SourceRef(object_id="target", revision=1).model_copy(
        update={"rogue": "must-not-disappear"}
    )
    reader = obs("reader", metadata={"ref": dirty_ref})
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([reader], op("dirty-source-extra"))

    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(store.db_path) == before
