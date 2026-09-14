"""Separately frozen additions for the clarified quality-review requirements.
Does not replace or modify test_redteam_b6588bd.py or any of its expectations.
"""
import pytest
from aios_core.contracts import ObjectRef, SourceRef
from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.storage import SQLiteWorldStore
from test_redteam_b6588bd import (
    obs, op, request_at, error_without_writes, replay_without_writes,
)


@pytest.mark.parametrize("ref_type", [ObjectRef, SourceRef])
@pytest.mark.parametrize("place", ["metadata", "value", "selector.filters"])
def test_missing_world_reference_rejected(tmp_path, ref_type, place):
    store = SQLiteWorldStore(tmp_path / "world.db")
    obj, request = request_at(place, ref_type(object_id="missing", revision=1), rev=0)
    error_without_writes(store, [obj], request, ErrorCode.NOT_FOUND)


@pytest.mark.parametrize("claimed_type", [ObjectType.DEPENDENCY, ObjectType.EVIDENCE_SET])
def test_observation_cannot_claim_other_canonical_type(tmp_path, claimed_type):
    store = SQLiteWorldStore(tmp_path / "world.db")
    dirty = obs().model_copy(update={"object_type": claimed_type})
    error_without_writes(store, [dirty], op(), ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize("invalid_type", ["not-a-world-type", None, 123])
def test_dirty_object_type_protocol(tmp_path, invalid_type):
    store = SQLiteWorldStore(tmp_path / "world.db")
    dirty = obs().model_copy(update={"object_type": invalid_type})
    error_without_writes(store, [dirty], op(), ErrorCode.INVALID_ARGUMENT)


def test_equivalent_object_type_string_normalizes(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    dirty = obs().model_copy(update={"object_type": "observation"})
    request = op()
    result = store.commit([dirty], request)
    assert result.world_revision == 1
    replay_without_writes(SQLiteWorldStore(store.db_path), [obs()], request)
