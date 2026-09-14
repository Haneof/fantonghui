"""M0-012 EventAnchor contract and cognitive lifecycle tests."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import ErrorCode, EventStatus, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import EventAnchor, Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.services import validate_event_transition
from aios_core.storage.sqlite_store import SQLiteWorldStore, StoreError


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def make_op(expected_world_revision: int) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_012_test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-012 test",
        idempotency_key=str(uuid.uuid4()),
    )


def make_event(
    *,
    object_id: str | None = None,
    revision: int = 1,
    status: EventStatus = EventStatus.CANDIDATE,
    title: str = "候选体育活动",
    interpretation: str = "现有资料显示可能存在体育活动",
    learned_at: datetime = BASE,
    confidence: float = 0.45,
    **overrides,
) -> EventAnchor:
    data = dict(
        object_id=object_id or new_object_id(ObjectType.EVENT),
        subject_id="user-1",
        revision=revision,
        occurred=TemporalExtent.unknown_time(),
        learned_at=learned_at,
        recorded_at=learned_at,
        created_by="test",
        title=title,
        interpretation=interpretation,
        event_status=status,
        event_time=TemporalExtent.point(BASE),
        confidence=confidence,
    )
    data.update(overrides)
    return EventAnchor(**data)


def test_ev01_exact_schema_and_object_type_literal():
    hints = get_type_hints(EventAnchor)
    assert get_origin(hints["object_type"]) is Literal
    assert get_args(hints["object_type"]) == (ObjectType.EVENT,)
    assert hints["title"] is str
    assert hints["interpretation"] is str
    assert hints["event_status"] is EventStatus
    assert hints["event_time"] is TemporalExtent
    for field_name in [
        "participant_refs",
        "primary_claim_refs",
        "support_evidence_set_refs",
        "counter_evidence_set_refs",
        "supersedes_refs",
        "split_child_refs",
    ]:
        assert get_origin(hints[field_name]) is list
        assert get_args(hints[field_name]) == (ObjectRef,)
    assert hints["confidence"] is float
    assert set(get_args(hints["merged_into_ref"])) == {ObjectRef, type(None)}
    assert set(get_args(hints["split_from_ref"])) == {ObjectRef, type(None)}
    assert set(get_args(hints["revision_reason"])) == {str, type(None)}


def test_ev02_candidate_confidence_is_not_forced_to_one():
    event = make_event(confidence=0.21)
    assert event.event_status is EventStatus.CANDIDATE
    assert event.confidence == 0.21


def test_ev03_confidence_bounds():
    for value in (0.0, 0.5, 1.0):
        assert make_event(confidence=value).confidence == value
    for value in (-0.01, 1.01):
        with pytest.raises(ValidationError):
            make_event(confidence=value)


def test_ev04_required_lifecycle_transitions():
    validate_event_transition(EventStatus.CANDIDATE, EventStatus.ACTIVE)
    validate_event_transition(EventStatus.CANDIDATE, EventStatus.REJECTED)
    validate_event_transition(EventStatus.ACTIVE, EventStatus.REVISED)
    validate_event_transition(EventStatus.ACTIVE, EventStatus.RESOLVED)


def test_ev05_merged_and_split_are_terminal_in_current_state_machine():
    for terminal in (EventStatus.MERGED, EventStatus.SPLIT):
        for target in EventStatus:
            with pytest.raises(ValueError):
                validate_event_transition(terminal, target)


def test_ev06_invalid_direct_transition_rejected():
    with pytest.raises(ValueError):
        validate_event_transition(EventStatus.CANDIDATE, EventStatus.RESOLVED)


def test_ev07_revised_requires_history_link_and_reason():
    with pytest.raises(ValidationError, match="REVISED EventAnchor requires supersedes_refs"):
        make_event(status=EventStatus.REVISED, revision_reason="新证据修正")

    previous = ObjectRef(object_id=new_object_id(ObjectType.EVENT), revision=1)
    with pytest.raises(ValidationError, match="REVISED EventAnchor requires revision_reason"):
        make_event(status=EventStatus.REVISED, supersedes_refs=[previous])


def test_ev08_merged_and_split_require_traceability_links():
    with pytest.raises(ValidationError, match="MERGED EventAnchor requires merged_into_ref"):
        make_event(status=EventStatus.MERGED, revision_reason="与另一锚点重复")

    with pytest.raises(ValidationError, match="SPLIT EventAnchor requires split_child_refs"):
        make_event(status=EventStatus.SPLIT, revision_reason="实际包含两个独立事件")


def test_ev09_rejected_requires_reason_but_not_confidence_zero():
    with pytest.raises(ValidationError, match="REJECTED EventAnchor requires revision_reason"):
        make_event(status=EventStatus.REJECTED, confidence=0.3)
    rejected = make_event(
        status=EventStatus.REJECTED,
        confidence=0.3,
        revision_reason="后续明确资料否定运动会解释",
    )
    assert rejected.confidence == 0.3


def test_ev10_provenance_refs_must_be_pinned():
    event_id = new_object_id(ObjectType.EVENT)
    cases = [
        ("primary_claim_refs", [ObjectRef(object_id=new_object_id(ObjectType.CLAIM), revision=None)]),
        ("support_evidence_set_refs", [ObjectRef(object_id=new_object_id(ObjectType.EVIDENCE_SET), revision=None)]),
        ("counter_evidence_set_refs", [ObjectRef(object_id=new_object_id(ObjectType.EVIDENCE_SET), revision=None)]),
        ("supersedes_refs", [ObjectRef(object_id=event_id, revision=None)]),
        ("split_child_refs", [ObjectRef(object_id=new_object_id(ObjectType.EVENT), revision=None)]),
    ]
    for field_name, value in cases:
        kwargs = {field_name: value}
        if field_name == "supersedes_refs":
            kwargs.update(status=EventStatus.REVISED, revision_reason="revision")
        elif field_name == "split_child_refs":
            kwargs.update(status=EventStatus.SPLIT, revision_reason="split")
        with pytest.raises(ValidationError, match=f"{field_name} requires pinned"):
            make_event(**kwargs)

    with pytest.raises(ValidationError, match="merged_into_ref requires pinned"):
        make_event(
            status=EventStatus.MERGED,
            merged_into_ref=ObjectRef(object_id=new_object_id(ObjectType.EVENT), revision=None),
            revision_reason="merge",
        )
    with pytest.raises(ValidationError, match="split_from_ref requires pinned"):
        make_event(
            split_from_ref=ObjectRef(object_id=new_object_id(ObjectType.EVENT), revision=None)
        )


def test_ev11_participant_identity_can_follow_stable_entity_id():
    participant = ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=None)
    event = make_event(participant_refs=[participant])
    assert event.participant_refs[0].revision is None


def test_ev12_sports_day_revision_history_is_replayable(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    event_id = new_object_id(ObjectType.EVENT)

    rev1 = make_event(
        object_id=event_id,
        revision=1,
        status=EventStatus.CANDIDATE,
        title="可能是体育活动",
        interpretation="操场位置和跑动信号支持体育活动假设",
        confidence=0.42,
        learned_at=BASE,
    )
    store.commit([rev1], make_op(0))
    validate_event_transition(EventStatus.CANDIDATE, EventStatus.ACTIVE)

    rev2 = make_event(
        object_id=event_id,
        revision=2,
        status=EventStatus.ACTIVE,
        title="学校运动会",
        interpretation="当时综合证据后认为是学校运动会",
        confidence=0.76,
        learned_at=BASE + timedelta(minutes=1),
    )
    store.commit([rev2], make_op(1))
    validate_event_transition(EventStatus.ACTIVE, EventStatus.REVISED)

    rev3 = make_event(
        object_id=event_id,
        revision=3,
        status=EventStatus.REVISED,
        title="校内田径测试",
        interpretation="用户后续明确说明是田径测试，不是运动会",
        confidence=0.94,
        learned_at=BASE + timedelta(minutes=2),
        supersedes_refs=[ObjectRef(object_id=event_id, revision=2)],
        revision_reason="用户明确说明活动性质，修正先前运动会解释",
    )
    store.commit([rev3], make_op(2))

    old_candidate = store.get_payload(event_id, revision=1)
    old_active = store.get_payload(event_id, revision=2)
    revised = store.get_payload(event_id, revision=3)

    assert old_candidate["title"] == "可能是体育活动"
    assert old_active["title"] == "学校运动会"
    assert revised["title"] == "校内田径测试"
    assert revised["supersedes_refs"] == [{"object_id": event_id, "revision": 2}]
    assert revised["revision_reason"] == "用户明确说明活动性质，修正先前运动会解释"
    assert store.get_payload(event_id, as_of_world_revision=1)["revision"] == 1
    assert store.get_payload(event_id, as_of_world_revision=2)["revision"] == 2
    assert store.get_payload(event_id, as_of_world_revision=3)["revision"] == 3


def test_ev13_event_payload_does_not_copy_raw_observation(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    raw = Observation(
        object_id=new_object_id(ObjectType.OBSERVATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.point(BASE),
        learned_at=BASE,
        recorded_at=BASE,
        created_by="test",
        source_kind="simulator",
        modality="text",
        value="原始私有证据文本：操场加油声",
    )
    store.commit([raw], make_op(0))

    event = make_event(title="可能是体育活动")
    store.commit([event], make_op(1))
    payload = store.get_payload(event.object_id)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "原始私有证据文本：操场加油声" not in serialized
    assert "value" not in payload


def test_ev14_post_validation_floating_provenance_mutation_blocked_at_store(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    target = make_event(title="先前事件")
    store.commit([target], make_op(0))

    event = make_event()
    event.supersedes_refs.append(ObjectRef(object_id=target.object_id, revision=None))
    assert event.supersedes_refs[-1].revision is None

    with pytest.raises(StoreError) as excinfo:
        store.commit([event], make_op(1))
    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 1


def test_ev15_merge_and_split_links_are_persistable_with_real_targets(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    left = make_event(title="候选锚点A")
    right = make_event(title="统一后的真实事件")
    child1 = make_event(title="拆分子事件1")
    child2 = make_event(title="拆分子事件2")
    store.commit([left, right, child1, child2], make_op(0))

    merged = make_event(
        object_id=left.object_id,
        revision=2,
        status=EventStatus.MERGED,
        learned_at=BASE + timedelta(minutes=1),
        merged_into_ref=ObjectRef(object_id=right.object_id, revision=1),
        revision_reason="确认两个锚点描述同一现实事件",
    )
    store.commit([merged], make_op(1))
    assert store.get_payload(left.object_id, revision=2)["merged_into_ref"]["revision"] == 1

    parent = make_event(title="原组合事件")
    store.commit([parent], make_op(2))
    split = make_event(
        object_id=parent.object_id,
        revision=2,
        status=EventStatus.SPLIT,
        learned_at=BASE + timedelta(minutes=2),
        split_child_refs=[
            ObjectRef(object_id=child1.object_id, revision=1),
            ObjectRef(object_id=child2.object_id, revision=1),
        ],
        revision_reason="新资料表明原锚点包含两个独立事件",
    )
    store.commit([split], make_op(3))
    assert len(store.get_payload(parent.object_id, revision=2)["split_child_refs"]) == 2
