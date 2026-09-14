"""M0-011 persistence proof: one world object may have multiple memberships."""
import uuid
from datetime import datetime, timezone

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import DimensionDefinition, DimensionMembership, Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def op(expected: int) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_011_membership_persistence",
        arguments={},
        expected_world_revision=expected,
        reason="prove one object may have multiple dimension memberships",
        idempotency_key=str(uuid.uuid4()),
    )


def test_one_object_persists_under_multiple_dimensions(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")

    member = Observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.point(BASE),
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        source_kind="simulator",
        modality="text",
        value="同一对象可同时属于多个维度",
    )
    experience = DimensionDefinition(
        object_id=new_object_id(ObjectType.DIMENSION_DEFINITION),
        subject_id="user-1",
        revision=1,
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        name="事件经历",
        description="事件经历维度",
        data_shape="event_set",
    )
    sports = DimensionDefinition(
        object_id=new_object_id(ObjectType.DIMENSION_DEFINITION),
        subject_id="user-1",
        revision=1,
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        name="运动经历",
        description="运动经历维度",
        data_shape="event_set",
    )
    store.commit([member, experience, sports], op(0))

    first = DimensionMembership(
        object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
        subject_id="user-1",
        revision=1,
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        dimension_ref=ObjectRef(object_id=experience.object_id, revision=1),
        member_ref=ObjectRef(object_id=member.object_id, revision=1),
    )
    second = DimensionMembership(
        object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
        subject_id="user-1",
        revision=1,
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        dimension_ref=ObjectRef(object_id=sports.object_id, revision=1),
        member_ref=ObjectRef(object_id=member.object_id, revision=1),
    )
    result = store.commit([first, second], op(1))

    assert result.world_revision == 2
    payloads = store.list_payloads(object_type=ObjectType.DIMENSION_MEMBERSHIP)
    assert len(payloads) == 2
    assert {p["dimension_ref"]["object_id"] for p in payloads} == {
        experience.object_id,
        sports.object_id,
    }
    assert {p["member_ref"]["object_id"] for p in payloads} == {member.object_id}
