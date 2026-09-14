from __future__ import annotations

import pytest

from aios_core.contracts import ObjectRef
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError
from tests.unit.test_m0_gate_sixth_followup import counts, obs, op


def test_fresh_typed_missing_ref_is_rejected(tmp_path):
    """Control: a real typed ref is validated on a fresh request."""
    store = SQLiteWorldStore(tmp_path / "control.db")
    typed = obs(
        "reader",
        metadata={"payload": {"ref": ObjectRef(object_id="missing", revision=1)}},
    )

    with pytest.raises(StoreError) as exc:
        store.commit([typed], op("fresh-typed"))

    assert exc.value.code is ErrorCode.NOT_FOUND
    assert counts(store.db_path) == (0, 0, 0, 0, 0)


def test_typed_ref_and_opaque_dict_cannot_alias_idempotent_replay(tmp_path):
    """Opaque lookalike input and an actual ObjectRef are different requests."""
    store = SQLiteWorldStore(tmp_path / "world.db")
    request = op("typed-vs-opaque")

    opaque = obs(
        "reader",
        metadata={"payload": {"ref": {"object_id": "missing", "revision": 1}}},
    )
    first = store.commit([opaque], request)
    assert first.world_revision == 1
    assert first.idempotent_replay is False
    before = counts(store.db_path)

    typed = obs(
        "reader",
        metadata={"payload": {"ref": ObjectRef(object_id="missing", revision=1)}},
    )
    with pytest.raises(StoreError) as exc:
        store.commit([typed], request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(store.db_path) == before


def test_exact_typed_ref_retry_survives_restart_and_stale_expected_revision(tmp_path):
    """The semantic marker must preserve safe exact replay, not merely force conflict."""
    path = tmp_path / "typed-retry.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))

    request = op("typed-reader", rev=1)
    reader = obs(
        "reader",
        metadata={"payload": {"ref": ObjectRef(object_id="target", revision=1)}},
    )
    first = store.commit([reader], request)
    assert first.world_revision == 2
    assert first.idempotent_replay is False
    before = counts(path)

    replay = SQLiteWorldStore(path).commit([reader], request)
    assert replay.world_revision == 2
    assert replay.idempotent_replay is True
    assert counts(path) == before


def test_typed_first_then_opaque_retry_is_conflict(tmp_path):
    """The semantic separation is symmetric in the opposite replay direction."""
    path = tmp_path / "typed-first.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))

    request = op("typed-first", rev=1)
    typed = obs(
        "reader",
        metadata={"payload": {"ref": ObjectRef(object_id="target", revision=1)}},
    )
    store.commit([typed], request)
    before = counts(path)

    opaque = obs(
        "reader",
        metadata={"payload": {"ref": {"object_id": "target", "revision": 1}}},
    )
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([opaque], request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(path) == before


def test_exact_opaque_retry_still_replays_after_restart(tmp_path):
    """Opaque JSON data remains ordinary accepted data with stable replay identity."""
    path = tmp_path / "opaque-retry.db"
    store = SQLiteWorldStore(path)
    request = op("opaque-exact")
    opaque = obs(
        "reader",
        metadata={"payload": {"ref": {"object_id": "missing", "revision": 1}}},
    )
    first = store.commit([opaque], request)
    assert first.world_revision == 1
    before = counts(path)

    replay = SQLiteWorldStore(path).commit([opaque], request)
    assert replay.idempotent_replay is True
    assert replay.world_revision == 1
    assert counts(path) == before


def test_opaque_marker_shaped_sequence_cannot_spoof_typed_ref_identity(tmp_path):
    """A caller-created JSON sequence cannot collide with the internal ref tag."""
    path = tmp_path / "marker-spoof.db"
    store = SQLiteWorldStore(path)
    request = op("marker-spoof")
    opaque = obs(
        "reader",
        metadata={"payload": {"ref": ["$aios-ref", "object", "missing", 1]}},
    )
    store.commit([opaque], request)
    before = counts(path)

    typed = obs(
        "reader",
        metadata={"payload": {"ref": ObjectRef(object_id="missing", revision=1)}},
    )
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit([typed], request)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(path) == before
