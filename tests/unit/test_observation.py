"""M0-007 Observation（基础观测）契约正式冻结"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent, utc_now
from aios_core.storage.sqlite_store import SQLiteWorldStore


def make_op(expected_world_revision: int = 0) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-007 test",
        idempotency_key=str(uuid.uuid4()),
    )


def make_observation(
    *,
    object_id: str | None = None,
    subject_id: str = "user-1",
    occurred: TemporalExtent | None = None,
    learned_at: datetime | None = None,
    recorded_at: datetime | None = None,
    source_kind: str = "device_sensor",
    modality: str = "heart_rate",
    value=None,
    unit: str | None = None,
    data_quality: dict | None = None,
    raw_locator: str | None = None,
    **extra,
):
    now = utc_now()
    learned = learned_at or now
    recorded = (
        recorded_at
        if recorded_at is not None
        else learned
    )
    oid = object_id or new_object_id(ObjectType.OBSERVATION)
    base_kwargs = dict(
        object_id=oid,
        subject_id=subject_id,
        revision=1,
        occurred=occurred or TemporalExtent.point(learned),
        learned_at=learned,
        recorded_at=recorded,
        created_by="test",
        source_kind=source_kind,
        modality=modality,
        value=value,
        unit=unit,
        data_quality=data_quality or {},
        raw_locator=raw_locator,
    )
    base_kwargs.update(extra)
    return Observation(**base_kwargs)


# O01 Schema contract
def test_o01_schema_contract():
    # Observation is WorldObject subclass
    assert issubclass(Observation, WorldObject)

    # model_fields至少包含公共11字段 + Observation字段
    fields = Observation.model_fields
    public_11 = [
        "object_id",
        "object_type",
        "subject_id",
        "revision",
        "occurred",
        "learned_at",
        "recorded_at",
        "source_refs",
        "created_by",
        "status",
        "metadata",
    ]
    obs_fields = [
        "source_kind",
        "modality",
        "value",
        "unit",
        "data_quality",
        "raw_locator",
    ]
    for f in public_11:
        assert f in fields, f"missing public field {f}"
    for f in obs_fields:
        assert f in fields, f"missing obs field {f}"

    # object_type默认 OBSERVATION
    obs = make_observation()
    assert obs.object_type == ObjectType.OBSERVATION

    # 构造合法
    assert obs.source_kind == "device_sensor"
    assert obs.modality == "heart_rate"


# O02 Heart-rate observation
def test_o02_heart_rate_observation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    occurred = TemporalExtent.point(datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc))
    learned_at = datetime(2026, 9, 14, 8, 5, tzinfo=timezone.utc)

    obs = make_observation(
        occurred=occurred,
        learned_at=learned_at,
        recorded_at=learned_at,
        source_kind="device_sensor",
        modality="heart_rate",
        value=82,
        unit="bpm",
        data_quality={"signal_quality": "good"},
    )

    # 创建成功验证
    assert obs.value == 82
    assert obs.unit == "bpm"
    assert obs.data_quality["signal_quality"] == "good"

    # 不得生成任何语义结论 - 确保没有高层字段
    assert not hasattr(obs, "event_type")
    assert not hasattr(obs, "emotion")
    assert not hasattr(obs, "claim_type")

    result = store.commit([obs], make_op(0))
    assert result.world_revision == 1

    payload = store.get_payload(obs.object_id)
    assert payload["value"] == 82
    assert payload["unit"] == "bpm"
    assert payload["source_kind"] == "device_sensor"
    assert payload["modality"] == "heart_rate"


# O03 GPS observation
def test_o03_gps_observation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    gps_value = {
        "lat": 31.2304,
        "lon": 121.4737,
        "accuracy_m": 8.0,
    }

    obs = make_observation(
        source_kind="device_sensor",
        modality="gps",
        value=gps_value,
        unit=None,
    )

    result = store.commit([obs], make_op(0))
    assert result.world_revision == 1

    payload = store.get_payload(obs.object_id)
    assert payload["value"]["lat"] == 31.2304
    assert payload["value"]["lon"] == 121.4737
    assert payload["value"]["accuracy_m"] == 8.0
    assert payload["unit"] is None

    # 不得自动产生地点事件等
    assert "event_type" not in payload
    assert "emotion" not in payload
    assert "relationship_state" not in payload


# O04 Conversation text observation
def test_o04_conversation_text_observation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obs = make_observation(
        source_kind="chat",
        modality="text",
        value="我今天有点累",
        raw_locator="conversation://test/session-1/message-1",
    )

    result = store.commit([obs], make_op(0))
    assert result.world_revision == 1

    payload = store.get_payload(obs.object_id)
    assert payload["value"] == "我今天有点累"
    assert payload["raw_locator"] == "conversation://test/session-1/message-1"

    # 不要额外产生 emotion/event_type
    assert "emotion" not in payload
    assert "event_type" not in payload


# O05 App answer observation
def test_o05_app_answer_observation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    ans = {
        "question_id": "math_q1",
        "answer": "B",
        "correct": True,
    }

    obs = make_observation(
        source_kind="app",
        modality="quiz_answer",
        value=ans,
    )

    result = store.commit([obs], make_op(0))
    assert result.world_revision == 1

    payload = store.get_payload(obs.object_id)
    assert payload["value"]["question_id"] == "math_q1"
    assert payload["value"]["answer"] == "B"
    assert payload["value"]["correct"] is True

    # 不要自动推断 ability等，严格无confidence
    assert "ability" not in payload
    assert "learning_problem" not in payload
    assert "confidence" not in payload


# O06 禁止event_type高层语义字段
def test_o06_forbid_event_type_extra():
    with pytest.raises(ValidationError):
        make_observation(
            source_kind="chat",
            modality="text",
            value="我们分手了",
            event_type="breakup",  # type: ignore
        )


# O07 Semantic extra fields
def test_o07_semantic_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        make_observation(
            source_kind="chat",
            modality="text",
            value="我有点焦虑",
            emotion="anxious",  # type: ignore
        )

    with pytest.raises(ValidationError):
        make_observation(
            source_kind="chat",
            modality="text",
            value="今天天气好",
            claim_type="FACT",  # type: ignore
        )

    with pytest.raises(ValidationError):
        make_observation(
            source_kind="chat",
            modality="text",
            value="吵架了",
            relationship_state="conflict",  # type: ignore
        )


# O08 Object type不可伪装
def test_o08_object_type_immutable():
    # Attempt to create Observation with EVENT type must fail
    with pytest.raises(ValidationError):
        Observation(
            object_id=new_object_id(ObjectType.OBSERVATION),
            object_type=ObjectType.EVENT,  # type: ignore
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=utc_now(),
            recorded_at=utc_now(),
            created_by="test",
            source_kind="chat",
            modality="text",
            value="test",
        )


# O09 多来源同一时间轴
def test_o09_unified_timeline_multi_source(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base_time = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)

    obs_hr = make_observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        source_kind="device_sensor",
        modality="heart_rate",
        value=82,
        unit="bpm",
        data_quality={"signal_quality": "good"},
        learned_at=base_time,
        recorded_at=base_time,
        occurred=TemporalExtent.point(base_time),
    )
    obs_gps = make_observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        source_kind="device_sensor",
        modality="gps",
        value={"lat": 31.2304, "lon": 121.4737, "accuracy_m": 8.0},
        learned_at=base_time + timedelta(minutes=1),
        recorded_at=base_time + timedelta(minutes=1),
        occurred=TemporalExtent.point(base_time + timedelta(minutes=1)),
    )
    obs_chat = make_observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        source_kind="chat",
        modality="text",
        value="我今天有点累",
        raw_locator="conversation://test/session-1/message-1",
        learned_at=base_time + timedelta(minutes=2),
        recorded_at=base_time + timedelta(minutes=2),
        occurred=TemporalExtent.point(base_time + timedelta(minutes=2)),
    )
    obs_app = make_observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        source_kind="app",
        modality="quiz_answer",
        value={"question_id": "math_q1", "answer": "B", "correct": True},
        learned_at=base_time + timedelta(minutes=3),
        recorded_at=base_time + timedelta(minutes=3),
        occurred=TemporalExtent.point(base_time + timedelta(minutes=3)),
    )

    # Commit in one or multiple transactions
    store.commit([obs_hr, obs_gps], make_op(0))
    store.commit([obs_chat, obs_app], make_op(1))

    all_obs = store.list_payloads(object_type=ObjectType.OBSERVATION)
    assert len(all_obs) == 4

    for payload in all_obs:
        assert payload["object_type"] == ObjectType.OBSERVATION.value
        assert "occurred" in payload
        assert "learned_at" in payload
        assert "recorded_at" in payload

    # Verify different source_kind share same object_type
    source_kinds = {p["source_kind"] for p in all_obs}
    assert "device_sensor" in source_kinds
    assert "chat" in source_kinds
    assert "app" in source_kinds


# O10 Observation默认不Wake
def test_o10_observation_does_not_wake(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obs = make_observation(
        source_kind="device_sensor",
        modality="heart_rate",
        value=82,
        unit="bpm",
    )

    store.commit([obs], make_op(0))

    wakes = store.list_payloads(object_type=ObjectType.WAKE)
    assert wakes == []
    assert len(wakes) == 0


# O11 raw_locator round-trip
def test_o11_raw_locator_round_trip(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obs = make_observation(
        source_kind="device",
        modality="audio_metadata",
        value={"format": "wav", "duration_seconds": 12},
        raw_locator="file:///raw/audio/session-1.wav",
    )

    store.commit([obs], make_op(0))

    payload = store.get_payload(obs.object_id)
    assert payload["raw_locator"] == "file:///raw/audio/session-1.wav"
    assert payload["value"]["format"] == "wav"
    assert payload["value"]["duration_seconds"] == 12

    # Ensure we did not put bytes into value (task forbids)
    assert not isinstance(payload["value"], (bytes, bytearray, memoryview))


# O12 底层观测不产生衍生世界对象
def test_o12_no_derived_world_objects(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    obs = make_observation(
        source_kind="chat",
        modality="text",
        value="我们分手了",
    )

    result = store.commit([obs], make_op(0))

    # object_refs only contains that Observation
    assert len(result.object_refs) == 1
    assert result.object_refs[0][0] == obs.object_id
    assert result.object_refs[0][1] == 1

    # No Claim, Event, Goal, Wake
    claims = store.list_payloads(object_type=ObjectType.CLAIM)
    events = store.list_payloads(object_type=ObjectType.EVENT)
    goals = store.list_payloads(object_type=ObjectType.GOAL)
    wakes = store.list_payloads(object_type=ObjectType.WAKE)

    assert claims == []
    assert events == []
    assert goals == []
    assert wakes == []


# O13 helper不得掩盖非法公共时间
def test_o13_helper_must_not_mask_illegal_time():
    learned = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    recorded = datetime(2026, 9, 14, 9, 59, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        make_observation(
            learned_at=learned,
            recorded_at=recorded,
            source_kind="device_sensor",
            modality="heart_rate",
            value=82,
            unit="bpm",
        )
