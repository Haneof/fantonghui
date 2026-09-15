"""M1-001 acceptance tests. Expectations frozen before implementation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import sqlite3
import subprocess
import sys
from threading import Barrier
from time import perf_counter

import pytest

from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.errors import AIOSProtocolError
from aios_core.storage.sqlite_store import SQLiteWorldStore


NOW = datetime(2026, 9, 15, 16, tzinfo=timezone.utc)


def service(store):
    from aios_core.world.ingest import ObservationIngestService
    return ObservationIngestService(store, clock=lambda: NOW,
                                    clock_provenance="simulator:m1-001")


def message(event="1", **changes):
    result = dict(subject_id="user-1", source_id="watch-1", source_event_id=event,
                  source_kind="sensor", modality="heart_rate", value=80,
                  unit="bpm", occurred_at="2026-09-15T15:01:00+00:00")
    result.update(changes)
    return result


@pytest.fixture
def store(tmp_path):
    return SQLiteWorldStore(tmp_path / "world.db")


def test_exact_source_replay(store):
    observation = service(store)
    first = observation.ingest([message()])
    again = observation.ingest([message()])
    assert first.world_revision == again.world_revision == 1
    assert first.object_refs == again.object_refs
    assert len(first.committed_refs) == 1 and again.committed_refs == []
    assert first.statuses == ["committed"] and again.statuses == ["replayed"]
    assert again.idempotent_replay
    assert len(store.list_payloads()) == 1


def test_same_value_different_time(store):
    result = service(store).ingest([message(), message("2", occurred_at="2026-09-15T15:02:00Z")])
    assert len(set(ref.object_id for ref in result.object_refs)) == 2
    assert len(store.list_payloads()) == 2
    assert result.world_revision == 1


@pytest.mark.parametrize("changes", [{"source_id": "watch-2"},
                                     {"source_event_id": "2"},
                                     {"subject_id": "user-2"}])
def test_distinct_message_identity_same_payload(store, changes):
    result = service(store).ingest([message(), message(**changes)])
    assert len(result.committed_refs) == 2


MODALITIES = [
    ("gps", {"latitude": 31.2, "longitude": 121.5}, "deg"),
    ("heart_rate", 80, "bpm"),
    ("imu", {"x": 0, "y": 0, "z": 9.80665}, "m/s^2"),
    ("text", "我今天跑步第一名", None),
    ("app", {"question_id": "q1", "answer": "A", "elapsed_ms": 3200}, None),
]


@pytest.mark.parametrize("modality,value,unit", MODALITIES)
def test_modality_batch(store, modality, value, unit):
    batch = [message(str(i), modality=modality, value=value, unit=unit) for i in range(3)]
    result = service(store).ingest(batch)
    assert len(result.committed_refs) == 3
    for payload in store.list_payloads():
        assert payload["modality"] == modality and payload["value"] == value
        assert payload["unit"] == unit and payload["object_type"] == "observation"


def test_mixed_batch_and_no_semantic_inference(store):
    batch = [message(str(i), modality=m, value=v, unit=u) for i, (m, v, u) in enumerate(MODALITIES)]
    result = service(store).ingest(batch)
    assert len(result.committed_refs) == len(store.list_payloads()) == 5
    assert {p["object_type"] for p in store.list_payloads()} == {"observation"}


@pytest.mark.parametrize("kind", [ObjectType.EVENT, ObjectType.CLAIM, ObjectType.WAKE,
    ObjectType.EVIDENCE_SET, ObjectType.ENTITY, ObjectType.RELATION, ObjectType.GOAL, ObjectType.SUMMARY])
def test_ingest_does_not_create_cognition(store, kind):
    service(store).ingest([message(value=180), message("2", modality="text", value="学校运动会", unit=None)])
    assert store.list_payloads(object_type=kind) == []


@pytest.mark.parametrize("time", ["yesterday", "2026-09-15T15:00:00", "2026-02-30T00:00:00Z",
    None, 1234567890, "1234567890", "0001-01-01T00:00:00+14:00"])
def test_invalid_time_is_atomic_protocol_error(store, time):
    with pytest.raises(AIOSProtocolError) as caught:
        service(store).ingest([message(), message("2", occurred_at=time)])
    assert caught.value.code == ErrorCode.INVALID_ARGUMENT
    assert store.current_world_revision() == 0 and store.list_payloads() == []


@pytest.mark.parametrize("changes", [
    {"unit": "kg"}, {"value": "80"}, {"value": True}, {"value": float("nan")},
    {"modality": "gps", "unit": "deg", "value": {"latitude": 91, "longitude": 0}},
    {"modality": "gps", "unit": "deg", "value": {"latitude": 0}},
    {"modality": "imu", "unit": "g", "value": {"x": 1, "y": 2}},
    {"modality": "text", "unit": None, "value": 42},
    {"modality": "app", "unit": None, "value": "json"},
    {"data_quality": []}, {"data_quality": {"x": float("inf")}},
    {"source_event_id": ""}, {"source_id": " "}, {"modality": "event"},
    {"learned_at": "2020-01-01T00:00:00Z"}, {"recorded_at": "2020-01-01T00:00:00Z"},
    {"data_quality": {1: "bad key"}}, {"source_metadata": {"x": "\ud800"}},
])
def test_invalid_format_unit_quality_or_provenance(store, changes):
    with pytest.raises(AIOSProtocolError) as caught:
        service(store).ingest([message(), message("2", **changes)])
    assert caught.value.code == ErrorCode.INVALID_ARGUMENT
    assert store.list_payloads() == [] and store.current_world_revision() == 0


def test_quality_source_metadata_and_clock_queryable(store):
    quality = {"missing_samples": 3, "flags": ["device_reported_noise"], "confidence": 0.4}
    result = service(store).ingest([message(data_quality=quality, source_metadata={"firmware": "v1"}, raw_locator="file:sample")])
    p = store.get_payload(result.object_refs[0].object_id, revision=1)
    assert p["data_quality"] == quality and p["raw_locator"] == "file:sample"
    assert p["metadata"]["source_metadata"] == {"firmware": "v1"}
    assert datetime.fromisoformat(p["learned_at"]) == NOW
    assert datetime.fromisoformat(p["recorded_at"]) == NOW
    assert p["metadata"]["ingress"]["clock_provenance"] == "simulator:m1-001"


def test_unit_and_timezone_normalization(store):
    a = service(store).ingest([message(value=2, unit="Hz", occurred_at="2026-09-15T23:01:00+08:00")])
    b = service(store).ingest([message(value=120, unit="bpm")])
    assert a.object_refs == b.object_refs and b.idempotent_replay
    p = store.get_payload(a.object_refs[0].object_id)
    assert p["value"] == 120 and p["unit"] == "bpm"
    assert datetime.fromisoformat(p["occurred"]["start"]).utcoffset() == timedelta(0)


@pytest.mark.parametrize("unit,value,expected,canonical", [
    ("g", {"x": 0, "y": 0, "z": 1}, 9.80665, "m/s^2"),
    ("deg/s", {"x": 0, "y": 0, "z": 180}, 3.141592653589793, "rad/s"),
])
def test_imu_units(store, unit, value, expected, canonical):
    service(store).ingest([message(modality="imu", unit=unit, value=value)])
    p = store.list_payloads()[0]
    assert p["value"]["z"] == pytest.approx(expected) and p["unit"] == canonical


def test_partial_replay_and_in_batch_duplicate(store):
    observation = service(store)
    first = observation.ingest([message()])
    second = observation.ingest([message("2"), message(), message("2")])
    assert second.statuses == ["committed", "replayed", "duplicate_in_batch"]
    assert len(second.committed_refs) == 1 and second.world_revision == 2
    assert second.object_refs[0] == second.object_refs[2]
    assert second.object_refs[1] == first.object_refs[0]
    assert len(store.list_payloads()) == 2


@pytest.mark.parametrize("changes", [{"value": 81}, {"occurred_at": "2026-09-15T15:02:00Z"},
                                     {"data_quality": {"flag": "changed"}}])
def test_same_identity_changed_content_conflicts(store, changes):
    observation = service(store)
    observation.ingest([message()])
    with pytest.raises(AIOSProtocolError) as caught:
        observation.ingest([message("new"), message(**changes)])
    assert caught.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    assert store.current_world_revision() == 1 and len(store.list_payloads()) == 1


def test_conflicting_same_batch_has_no_write(store):
    with pytest.raises(AIOSProtocolError) as caught:
        service(store).ingest([message(), message(value=81)])
    assert caught.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    assert store.current_world_revision() == 0


def test_reference_validation_not_bypassed(store):
    with pytest.raises(AIOSProtocolError) as caught:
        service(store).ingest([message(), message("2", source_refs=[{"object_id": "missing", "revision": 1}])])
    assert caught.value.code == ErrorCode.NOT_FOUND and store.list_payloads() == []


def test_mid_insert_failure_rolls_back_everything(store):
    # Test-only fault injection: fail second INSERT after first row was written.
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("CREATE TRIGGER fail_second BEFORE INSERT ON object_revisions WHEN (SELECT COUNT(*) FROM object_revisions) >= 1 BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    with pytest.raises(AIOSProtocolError):
        service(store).ingest([message(), message("2"), message("3")])
    assert store.current_world_revision() == 0 and store.list_payloads() == []
    with sqlite3.connect(store.db_path) as conn:
        for table in ["world_commits", "operations", "idempotency_records"]:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        conn.execute("DROP TRIGGER fail_second")
    assert len(service(store).ingest([message(), message("2")]).committed_refs) == 2


def test_restart_in_another_process_preserves_dedupe(store):
    first = service(store).ingest([message()])
    script = '''
import json, sys
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.ingest import ObservationIngestService
result = ObservationIngestService(SQLiteWorldStore(sys.argv[1])).ingest([json.loads(sys.argv[2])])
print(result.model_dump_json())
'''
    env = dict(os.environ, PYTHONPATH="src", PYTHONHASHSEED="937")
    p = subprocess.run([sys.executable, "-c", script, str(store.db_path), json.dumps(message())],
                       capture_output=True, text=True, env=env, check=True)
    result = json.loads(p.stdout)
    assert result["idempotent_replay"] and result["world_revision"] == 1
    assert result["object_refs"][0]["object_id"] == first.object_refs[0].object_id


def test_observation_revision_does_not_erase_ingress_identity(store):
    first = service(store).ingest([message()])
    original = store.get_payload(first.object_refs[0].object_id)
    original.update(revision=2, metadata={}, value=90, subject_id="corrected-subject")
    store.commit([Observation.model_validate(original)], OperationRequest(
        operation_name="test.revise", expected_world_revision=1, reason="test revision",
        idempotency_key="test-revise"))
    replay = service(store).ingest([message()])
    assert replay.object_refs == first.object_refs and replay.idempotent_replay
    assert replay.world_revision == 2 and len(store.list_payloads()) == 1


def test_concurrent_writers_conflict_then_retry_without_duplicate(store):
    barrier = Barrier(2)
    class RacingStore(SQLiteWorldStore):
        def commit(self, objects, operation):
            barrier.wait(timeout=10)
            return super().commit(objects, operation)
    def run():
        try:
            return service(RacingStore(store.db_path)).ingest([message()])
        except AIOSProtocolError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    failures = [r for r in results if isinstance(r, AIOSProtocolError)]
    assert len(failures) == 1 and failures[0].code == ErrorCode.VERSION_CONFLICT
    assert service(store).ingest([message()]).idempotent_replay
    assert len(store.list_payloads()) == 1 and store.current_world_revision() == 1


def test_empty_batch_is_noop(store):
    result = service(store).ingest([])
    assert result.object_refs == [] and result.committed_refs == [] and result.world_revision == 0


def test_10000_heart_rate_baseline(store):
    batch = [message(str(i), occurred_at=(NOW - timedelta(seconds=10000-i)).isoformat(),
                     value=60 + i % 40) for i in range(10000)]
    start = perf_counter()
    result = service(store).ingest(batch)
    write_seconds = perf_counter() - start
    assert len(result.committed_refs) == 10000 and result.world_revision == 1
    assert len(store.list_payloads()) == 10000
    start = perf_counter()
    replay = service(SQLiteWorldStore(store.db_path)).ingest(batch)
    replay_seconds = perf_counter() - start
    assert replay.idempotent_replay and replay.world_revision == 1
    assert replay.object_refs == result.object_refs
    assert store.list_payloads(object_type=ObjectType.WAKE) == []
    print("\nINGEST_10K=" + json.dumps({"count": 10000, "write_seconds": write_seconds,
        "observations_per_second": 10000/write_seconds, "restart_replay_seconds": replay_seconds,
        "database_bytes": os.stat(store.db_path).st_size}))
