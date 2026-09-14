from __future__ import annotations

import pytest

from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError
from tests.unit.test_m0_gate_sixth_followup import counts, obs, op


def test_dirty_expected_world_revision_is_normalized_before_fresh_revision_check(tmp_path):
    store = SQLiteWorldStore(tmp_path / "fresh.db")
    request = op("dirty-fresh").model_copy(update={"expected_world_revision": "0"})
    assert request.expected_world_revision == "0"

    result = store.commit([obs("reader")], request)

    assert result.world_revision == 1
    assert result.idempotent_replay is False
    assert store.operation_record(request.operation_id)["expected_world_revision"] == 0


def test_dirty_expected_world_revision_exact_retry_matches_canonical_request(tmp_path):
    path = tmp_path / "retry.db"
    store = SQLiteWorldStore(path)
    canonical = op("dirty-retry")
    first = store.commit([obs("reader")], canonical)
    before = counts(path)

    dirty = canonical.model_copy(update={"expected_world_revision": "0"})
    replay = SQLiteWorldStore(path).commit([obs("reader")], dirty)

    assert first.world_revision == replay.world_revision == 1
    assert replay.idempotent_replay is True
    assert counts(path) == before


def test_dirty_operation_extra_is_invalid_argument_on_fresh_write(tmp_path):
    store = SQLiteWorldStore(tmp_path / "dirty-extra.db")
    request = op("dirty-extra").model_copy(update={"rogue": "must-not-disappear"})
    before = counts(store.db_path)

    with pytest.raises(StoreError) as exc:
        store.commit([obs("reader")], request)

    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert counts(store.db_path) == before


def test_dirty_operation_extra_is_idempotency_conflict_on_retry(tmp_path):
    store = SQLiteWorldStore(tmp_path / "dirty-extra-retry.db")
    request = op("dirty-extra-retry")
    store.commit([obs("reader")], request)
    before = counts(store.db_path)

    dirty = request.model_copy(update={"rogue": "must-not-disappear"})
    with pytest.raises(StoreError) as exc:
        store.commit([obs("reader")], dirty)

    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert counts(store.db_path) == before
