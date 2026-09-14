"""M0-011 DimensionDefinition / Membership / Derivation contract freeze."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import DimensionLifecycle, ErrorCode, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import (
    DimensionDefinition,
    DimensionDerivation,
    DimensionMembership,
    Observation,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore, StoreError


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def make_op(expected_world_revision: int) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_011_test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-011 test",
        idempotency_key=str(uuid.uuid4()),
    )


def make_dimension(*, name: str, data_shape: str = "scalar") -> DimensionDefinition:
    return DimensionDefinition(
        object_id=new_object_id(ObjectType.DIMENSION_DEFINITION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        name=name,
        description=f"{name} dimension",
        data_shape=data_shape,
        lifecycle=DimensionLifecycle.CANDIDATE,
        update_method="evidence_driven",
    )


def make_observation(value: str = "raw-private-value") -> Observation:
    return Observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.point(BASE),
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        source_kind="simulator",
        modality="text",
        value=value,
    )


def test_d01_exact_three_layer_schema():
    definition_hints = get_type_hints(DimensionDefinition)
    assert get_origin(definition_hints["object_type"]) is Literal
    assert get_args(definition_hints["object_type"]) == (ObjectType.DIMENSION_DEFINITION,)
    assert definition_hints["name"] is str
    assert definition_hints["description"] is str
    assert definition_hints["data_shape"] is str
    assert definition_hints["lifecycle"] is DimensionLifecycle
    assert set(get_args(definition_hints["update_method"])) == {str, type(None)}
    assert set(get_args(definition_hints["expected_value"])) == {str, type(None)}
    assert get_origin(definition_hints["maintenance_policy"]) is dict
    assert get_args(definition_hints["maintenance_policy"]) == (str, Any)

    membership_hints = get_type_hints(DimensionMembership)
    assert get_origin(membership_hints["object_type"]) is Literal
    assert get_args(membership_hints["object_type"]) == (ObjectType.DIMENSION_MEMBERSHIP,)
    assert membership_hints["dimension_ref"] is ObjectRef
    assert membership_hints["member_ref"] is ObjectRef
    assert membership_hints["applicable_time"] is TemporalExtent
    assert get_origin(membership_hints["basis_refs"]) is list
    assert get_args(membership_hints["basis_refs"]) == (ObjectRef,)

    derivation_hints = get_type_hints(DimensionDerivation)
    assert get_origin(derivation_hints["object_type"]) is Literal
    assert get_args(derivation_hints["object_type"]) == (ObjectType.DIMENSION_DERIVATION,)
    assert derivation_hints["output_dimension_ref"] is ObjectRef
    assert get_origin(derivation_hints["input_refs"]) is list
    assert get_args(derivation_hints["input_refs"]) == (ObjectRef,)
    assert derivation_hints["derivation_description"] is str
    assert get_origin(derivation_hints["applicable_scope"]) is dict
    assert get_args(derivation_hints["applicable_scope"]) == (str, Any)
    assert derivation_hints["applicable_time"] is TemporalExtent
    assert get_origin(derivation_hints["evidence_set_refs"]) is list
    assert get_args(derivation_hints["evidence_set_refs"]) == (ObjectRef,)
    assert derivation_hints["confidence"] is float
    assert get_origin(derivation_hints["counterexample_refs"]) is list
    assert get_args(derivation_hints["counterexample_refs"]) == (ObjectRef,)


def test_d02_data_shape_is_not_forced_to_curve():
    shapes = [
        "scalar",
        "time_series",
        "discrete_state",
        "event_set",
        "entity_relation_graph",
        "text_hypothesis",
        "multidimensional_structure",
    ]
    for shape in shapes:
        dim = make_dimension(name=f"dim-{shape}", data_shape=shape)
        assert dim.data_shape == shape


def test_d03_same_member_can_have_multiple_dimension_memberships():
    dim_event = make_dimension(name="事件经历", data_shape="event_set")
    dim_sport = make_dimension(name="运动经历", data_shape="event_set")
    member_id = new_object_id(ObjectType.EVENT)

    m1 = DimensionMembership(
        object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        dimension_ref=ObjectRef(object_id=dim_event.object_id, revision=1),
        member_ref=ObjectRef(object_id=member_id, revision=1),
        basis_refs=[],
    )
    m2 = DimensionMembership(
        object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        dimension_ref=ObjectRef(object_id=dim_sport.object_id, revision=1),
        member_ref=ObjectRef(object_id=member_id, revision=1),
        basis_refs=[],
    )

    assert m1.member_ref.object_id == m2.member_ref.object_id
    assert m1.dimension_ref.object_id != m2.dimension_ref.object_id


def test_d04_membership_provenance_refs_are_pinned():
    dim_id = new_object_id(ObjectType.DIMENSION_DEFINITION)
    member_id = new_object_id(ObjectType.OBSERVATION)

    with pytest.raises(ValidationError, match="dimension_ref requires pinned"):
        DimensionMembership(
            object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
            subject_id="user-1",
            learned_at=BASE,
            recorded_at=BASE,
            created_by="test",
            dimension_ref=ObjectRef(object_id=dim_id, revision=None),
            member_ref=ObjectRef(object_id=member_id, revision=1),
        )

    with pytest.raises(ValidationError, match="member_ref requires pinned"):
        DimensionMembership(
            object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
            subject_id="user-1",
            learned_at=BASE,
            recorded_at=BASE,
            created_by="test",
            dimension_ref=ObjectRef(object_id=dim_id, revision=1),
            member_ref=ObjectRef(object_id=member_id, revision=None),
        )

    with pytest.raises(ValidationError, match="basis_refs requires pinned"):
        DimensionMembership(
            object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
            subject_id="user-1",
            learned_at=BASE,
            recorded_at=BASE,
            created_by="test",
            dimension_ref=ObjectRef(object_id=dim_id, revision=1),
            member_ref=ObjectRef(object_id=member_id, revision=1),
            basis_refs=[ObjectRef(object_id=member_id, revision=None)],
        )


def test_d05_derivation_requires_input():
    output = make_dimension(name="学习能力")
    with pytest.raises(ValidationError):
        DimensionDerivation(
            object_id=new_object_id(ObjectType.DIMENSION_DERIVATION),
            subject_id="user-1",
            learned_at=BASE,
            recorded_at=BASE,
            created_by="test",
            output_dimension_ref=ObjectRef(object_id=output.object_id, revision=1),
            input_refs=[],
            derivation_description="数学+英语+编程形成学习能力假设",
            confidence=0.7,
        )


def test_d06_learning_ability_drills_down_to_math_english_programming():
    math = make_dimension(name="数学能力")
    english = make_dimension(name="英语能力")
    coding = make_dimension(name="编程能力")
    learning = make_dimension(name="学习能力", data_shape="cognitive_hypothesis")

    derivation = DimensionDerivation(
        object_id=new_object_id(ObjectType.DIMENSION_DERIVATION),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        output_dimension_ref=ObjectRef(object_id=learning.object_id, revision=1),
        input_refs=[
            ObjectRef(object_id=math.object_id, revision=1),
            ObjectRef(object_id=english.object_id, revision=1),
            ObjectRef(object_id=coding.object_id, revision=1),
        ],
        derivation_description="数学、英语、编程表现共同支持学习能力这一高层认知假设",
        applicable_scope={"subject": "user-1"},
        confidence=0.72,
    )

    assert derivation.output_dimension_ref.object_id == learning.object_id
    assert [ref.object_id for ref in derivation.input_refs] == [
        math.object_id,
        english.object_id,
        coding.object_id,
    ]


def test_d07_derivation_input_contract_is_objectref_not_numeric_vector():
    hints = get_type_hints(DimensionDerivation)
    assert get_origin(hints["input_refs"]) is list
    assert get_args(hints["input_refs"]) == (ObjectRef,)

    output = make_dimension(name="高层维度")
    heterogeneous_ids = [
        new_object_id(ObjectType.DIMENSION_DEFINITION),
        new_object_id(ObjectType.EVENT),
        new_object_id(ObjectType.CLAIM),
        new_object_id(ObjectType.SUMMARY),
        new_object_id(ObjectType.EVIDENCE_SET),
    ]
    derivation = DimensionDerivation(
        object_id=new_object_id(ObjectType.DIMENSION_DERIVATION),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        output_dimension_ref=ObjectRef(object_id=output.object_id, revision=1),
        input_refs=[ObjectRef(object_id=oid, revision=1) for oid in heterogeneous_ids],
        derivation_description="heterogeneous inputs",
        confidence=0.5,
    )
    assert [ref.object_id for ref in derivation.input_refs] == heterogeneous_ids


def test_d08_derivation_provenance_refs_are_pinned():
    output_id = new_object_id(ObjectType.DIMENSION_DEFINITION)
    input_id = new_object_id(ObjectType.CLAIM)
    evidence_id = new_object_id(ObjectType.EVIDENCE_SET)

    cases = [
        (
            {"output_dimension_ref": ObjectRef(object_id=output_id, revision=None),
             "input_refs": [ObjectRef(object_id=input_id, revision=1)]},
            "output_dimension_ref requires pinned",
        ),
        (
            {"output_dimension_ref": ObjectRef(object_id=output_id, revision=1),
             "input_refs": [ObjectRef(object_id=input_id, revision=None)]},
            "input_refs requires pinned",
        ),
        (
            {"output_dimension_ref": ObjectRef(object_id=output_id, revision=1),
             "input_refs": [ObjectRef(object_id=input_id, revision=1)],
             "evidence_set_refs": [ObjectRef(object_id=evidence_id, revision=None)]},
            "evidence_set_refs requires pinned",
        ),
        (
            {"output_dimension_ref": ObjectRef(object_id=output_id, revision=1),
             "input_refs": [ObjectRef(object_id=input_id, revision=1)],
             "counterexample_refs": [ObjectRef(object_id=input_id, revision=None)]},
            "counterexample_refs requires pinned",
        ),
    ]

    for overrides, message in cases:
        with pytest.raises(ValidationError, match=message):
            DimensionDerivation(
                object_id=new_object_id(ObjectType.DIMENSION_DERIVATION),
                subject_id="user-1",
                learned_at=BASE,
                recorded_at=BASE,
                created_by="test",
                derivation_description="test",
                confidence=0.5,
                **overrides,
            )


def test_d09_raw_observation_is_referenced_not_copied(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    observation = make_observation("原始证据只应存在Observation")
    dimension = make_dimension(name="运动经历", data_shape="event_set")
    store.commit([observation, dimension], make_op(0))

    membership = DimensionMembership(
        object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        dimension_ref=ObjectRef(object_id=dimension.object_id, revision=1),
        member_ref=ObjectRef(object_id=observation.object_id, revision=1),
        basis_refs=[ObjectRef(object_id=observation.object_id, revision=1)],
    )
    store.commit([membership], make_op(1))

    payload = store.get_payload(membership.object_id)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["member_ref"]["object_id"] == observation.object_id
    assert payload["basis_refs"][0]["object_id"] == observation.object_id
    assert "原始证据只应存在Observation" not in serialized
    assert "value" not in payload


def test_d10_dimension_objects_round_trip_in_store(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    low = make_dimension(name="数学能力", data_shape="mixed")
    high = make_dimension(name="学习能力", data_shape="cognitive_hypothesis")
    store.commit([low, high], make_op(0))

    membership = DimensionMembership(
        object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        dimension_ref=ObjectRef(object_id=low.object_id, revision=1),
        member_ref=ObjectRef(object_id=high.object_id, revision=1),
    )
    derivation = DimensionDerivation(
        object_id=new_object_id(ObjectType.DIMENSION_DERIVATION),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        output_dimension_ref=ObjectRef(object_id=high.object_id, revision=1),
        input_refs=[ObjectRef(object_id=low.object_id, revision=1)],
        derivation_description="low to high",
        confidence=0.6,
    )
    result = store.commit([membership, derivation], make_op(1))
    assert result.world_revision == 2
    assert store.get_payload(membership.object_id)["object_type"] == ObjectType.DIMENSION_MEMBERSHIP.value
    assert store.get_payload(derivation.object_id)["input_refs"][0]["revision"] == 1


def test_d11_membership_post_validation_mutation_blocked_at_store(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    observation = make_observation()
    dimension = make_dimension(name="运动经历")
    store.commit([observation, dimension], make_op(0))

    membership = DimensionMembership(
        object_id=new_object_id(ObjectType.DIMENSION_MEMBERSHIP),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        dimension_ref=ObjectRef(object_id=dimension.object_id, revision=1),
        member_ref=ObjectRef(object_id=observation.object_id, revision=1),
        basis_refs=[ObjectRef(object_id=observation.object_id, revision=1)],
    )
    membership.basis_refs.append(ObjectRef(object_id=observation.object_id, revision=None))
    assert membership.basis_refs[-1].revision is None

    with pytest.raises(StoreError) as excinfo:
        store.commit([membership], make_op(1))
    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 1


def test_d12_derivation_post_validation_mutation_blocked_at_store(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    low = make_dimension(name="数学能力")
    high = make_dimension(name="学习能力")
    store.commit([low, high], make_op(0))

    derivation = DimensionDerivation(
        object_id=new_object_id(ObjectType.DIMENSION_DERIVATION),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        output_dimension_ref=ObjectRef(object_id=high.object_id, revision=1),
        input_refs=[ObjectRef(object_id=low.object_id, revision=1)],
        derivation_description="test",
        confidence=0.5,
    )
    derivation.input_refs.append(ObjectRef(object_id=low.object_id, revision=None))
    assert derivation.input_refs[-1].revision is None

    with pytest.raises(StoreError) as excinfo:
        store.commit([derivation], make_op(1))
    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 1


def test_d13_confidence_bounds():
    output = make_dimension(name="output")
    input_dim = make_dimension(name="input")
    common = dict(
        object_id=new_object_id(ObjectType.DIMENSION_DERIVATION),
        subject_id="user-1",
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        output_dimension_ref=ObjectRef(object_id=output.object_id, revision=1),
        input_refs=[ObjectRef(object_id=input_dim.object_id, revision=1)],
        derivation_description="bounds",
    )
    for value in (0.0, 0.5, 1.0):
        assert DimensionDerivation(**common, confidence=value).confidence == value
    for value in (-0.01, 1.01):
        with pytest.raises(ValidationError):
            DimensionDerivation(**common, confidence=value)
