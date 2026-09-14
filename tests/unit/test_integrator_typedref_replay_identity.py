from __future__ import annotations

import pytest

from aios_core.contracts import ObjectRef
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError
from tests.unit.test_m0_gate_sixth_followup import counts, obs, op


def test_fresh_typed_missing_ref_is_rejected(tmp_path):
    """Control: the candidate does validate a real typed ref on a fresh request."""
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
    """A typed ref and an opaque lookalike dict have different M0 semantics.

    The opaque dictionary is deliberately not a reference and is allowed to persist.
    Retrying the same idempotency key with an actual ObjectRef is therefore a
    materially different request and must conflict rather than replay the first
    success. In particular, replay identity must not erase the typed-ref semantic
    distinction before M0-019 reference validation can act on it.
    """
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
