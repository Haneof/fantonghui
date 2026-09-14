"""M0-008 Claim（主张）语义模型正式冻结"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ClaimType, KnowledgeState, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import Claim, Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.contracts.time import TemporalExtent, as_utc, utc_now
from aios_core.storage.sqlite_store import SQLiteWorldStore


def make_op(expected_world_revision: int = 0) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-008 test",
        idempotency_key=str(uuid.uuid4()),
    )


def make_observation(
    *,
    object_id: str | None = None,
    value: str = "test observation",
    learned_at: datetime | None = None,
    recorded_at: datetime | None = None,
    source_kind: str = "chat",
    modality: str = "text",
):
    now = utc_now()
    learned = learned_at or now
    recorded = recorded_at if recorded_at is not None else learned
    oid = object_id or new_object_id(ObjectType.OBSERVATION)
    return Observation(
        object_id=oid,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.point(learned),
        learned_at=learned,
        recorded_at=recorded,
        created_by="test",
        source_kind=source_kind,
        modality=modality,
        value=value,
    )


def make_claim(
    *,
    object_id: str | None = None,
    subject_id: str = "user-1",
    revision: int = 1,
    claimant_id: str = "user-1",
    claim_type: ClaimType = ClaimType.FACT,
    content: str = "test claim",
    valid_time: TemporalExtent | None = None,
    asserted_at: datetime | None = None,
    knowledge_state: KnowledgeState = KnowledgeState.REPORTED,
    confidence: float = 0.7,
    learned_at: datetime | None = None,
    recorded_at: datetime | None = None,
    source_refs: list[SourceRef] | None = None,
    support_evidence_set_refs: list[ObjectRef] | None = None,
    counter_evidence_set_refs: list[ObjectRef] | None = None,
    unknown_items: list[str] | None = None,
    **extra,
):
    now = utc_now()
    learned = learned_at or now
    recorded = recorded_at if recorded_at is not None else learned
    asserted = asserted_at or learned
    oid = object_id or new_object_id(ObjectType.CLAIM)
    kwargs = dict(
        object_id=oid,
        subject_id=subject_id,
        revision=revision,
        occurred=TemporalExtent.unknown_time(),
        learned_at=learned,
        recorded_at=recorded,
        created_by="test",
        claimant_id=claimant_id,
        claim_type=claim_type,
        content=content,
        valid_time=valid_time or TemporalExtent.unknown_time(),
        asserted_at=asserted,
        knowledge_state=knowledge_state,
        confidence=confidence,
        support_evidence_set_refs=support_evidence_set_refs or [],
        counter_evidence_set_refs=counter_evidence_set_refs or [],
        unknown_items=unknown_items or [],
        source_refs=source_refs or [],
    )
    kwargs.update(extra)
    return Claim(**kwargs)


# C01 Claim schema
def test_c01_claim_schema():
    assert issubclass(Claim, WorldObject)

    fields = Claim.model_fields
    required_claim_fields = [
        "claimant_id",
        "claim_type",
        "content",
        "valid_time",
        "asserted_at",
        "knowledge_state",
        "confidence",
        "support_evidence_set_refs",
        "counter_evidence_set_refs",
        "unknown_items",
    ]
    public_fields = [
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
    for f in required_claim_fields:
        assert f in fields, f"missing Claim field {f}"
    for f in public_fields:
        assert f in fields, f"missing public field {f}"

    claim = make_claim()
    assert claim.object_type == ObjectType.CLAIM


# C02 ClaimType required set
def test_c02_claimtype_required_set():
    required = {
        ClaimType.FACT,
        ClaimType.OPINION,
        ClaimType.BELIEF,
        ClaimType.DESIRE,
        ClaimType.INTENTION,
        ClaimType.PLAN,
        ClaimType.PREDICTION,
        ClaimType.PROMISE,
        ClaimType.PREFERENCE,
        ClaimType.INFERENCE,
        ClaimType.HYPOTHESIS,
    }
    all_types = set(ClaimType)
    assert required.issubset(all_types), f"required {required} not subset of {all_types}"


# C03 confidence bounds
def test_c03_confidence_bounds():
    # legal
    for conf in [0.0, 0.37, 1.0]:
        c = make_claim(confidence=conf)
        assert c.confidence == conf

    # illegal
    for conf in [-0.01, 1.01]:
        with pytest.raises(ValidationError):
            make_claim(confidence=conf)

    # FACT confidence 0.37 must stay 0.37 not become 1.0
    c = make_claim(claim_type=ClaimType.FACT, confidence=0.37)
    assert c.confidence == 0.37
    assert c.confidence != 1.0


# C04 asserted_at aware
def test_c04_asserted_at_aware():
    aware = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    c = make_claim(asserted_at=aware)
    assert c.asserted_at == aware

    naive = datetime(2026, 9, 14, 10, 0)  # no tz
    with pytest.raises(ValidationError):
        make_claim(asserted_at=naive)


# C05 “明天生日”
def test_c05_tomorrow_birthday():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    tomorrow = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    valid = TemporalExtent.point(tomorrow)

    claim = make_claim(
        claimant_id="user-1",
        subject_id="user-1",
        claim_type=ClaimType.FACT,
        content="2026-09-15是用户生日",
        asserted_at=base,
        valid_time=valid,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.70,
        learned_at=base,
        recorded_at=base,
    )

    assert claim.claim_type == ClaimType.FACT
    assert claim.knowledge_state == KnowledgeState.REPORTED
    assert claim.confidence == 0.70
    # valid_time in future vs asserted_at - use UTC instant per M0-004
    assert claim.valid_time.start is not None
    assert (
        as_utc(
            claim.valid_time.start,
            "valid_time.start",
        )
        >
        as_utc(
            claim.asserted_at,
            "asserted_at",
        )
    )


# C06 “一定考上”多Claim拆分
def test_c06_certain_admission_multi_claim(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs = make_observation(
        value="我明天一定能考上某校",
        learned_at=base,
        recorded_at=base,
        source_kind="chat",
        modality="text",
    )
    store.commit([obs], make_op(0))

    # Claim A speech_fact
    claim_a = make_claim(
        object_id=new_object_id(ObjectType.CLAIM),
        claimant_id="aios-observer",
        subject_id="user-1",
        claim_type=ClaimType.FACT,
        content="用户说出了‘我明天一定能考上某校’",
        knowledge_state=KnowledgeState.OBSERVED,
        confidence=0.99,
        asserted_at=base,
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
        source_refs=[SourceRef(object_id=obs.object_id, revision=1)],
    )

    # Claim B prediction
    claim_b = make_claim(
        object_id=new_object_id(ObjectType.CLAIM),
        claimant_id="user-1",
        subject_id="user-1",
        claim_type=ClaimType.PREDICTION,
        content="用户将考上某校",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.35,
        asserted_at=base,
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
        source_refs=[SourceRef(object_id=obs.object_id, revision=1)],
    )

    # Optional Claim C belief
    claim_c = make_claim(
        object_id=new_object_id(ObjectType.CLAIM),
        claimant_id="user-1",
        subject_id="user-1",
        claim_type=ClaimType.BELIEF,
        content="用户相信自己将考上某校",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.90,
        asserted_at=base,
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
        source_refs=[SourceRef(object_id=obs.object_id, revision=1)],
    )

    store.commit([claim_a, claim_b, claim_c], make_op(1))

    assert claim_a.object_id != claim_b.object_id
    assert claim_a.object_type == ObjectType.CLAIM
    assert claim_b.object_type == ObjectType.CLAIM
    assert claim_a.source_refs[0].object_id == obs.object_id
    assert claim_a.source_refs[0].revision == 1
    assert claim_b.source_refs[0].object_id == obs.object_id
    assert claim_a.confidence == 0.99
    assert claim_b.confidence == 0.35
    assert claim_b.confidence != claim_a.confidence
    # prediction confidence should not auto become 1 because user said "一定"
    assert claim_b.confidence != 1.0


# C07 “我觉得妈妈生气了”
def test_c07_mother_angry_belief():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs = make_observation(
        value="我觉得妈妈生气了",
        learned_at=base,
        recorded_at=base,
    )

    claim = make_claim(
        claimant_id="user-1",
        subject_id="mother-subject",
        claim_type=ClaimType.BELIEF,
        content="用户认为妈妈正在生气",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.80,
        asserted_at=base,
        learned_at=base,
        recorded_at=base,
        source_refs=[SourceRef(object_id=obs.object_id, revision=1)],
    )

    assert claim.claim_type == ClaimType.BELIEF
    assert claim.claim_type != ClaimType.FACT
    assert claim.knowledge_state == KnowledgeState.REPORTED
    assert claim.subject_id == "mother-subject"
    assert claim.claimant_id == "user-1"
    # Must not auto create event etc, just claim
    assert claim.object_type == ObjectType.CLAIM


# C08 claim_type和knowledge_state独立组合
def test_c08_independent_combinations():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    combos = [
        (ClaimType.FACT, KnowledgeState.REPORTED),
        (ClaimType.BELIEF, KnowledgeState.REPORTED),
        (ClaimType.PREDICTION, KnowledgeState.REPORTED),
        (ClaimType.INFERENCE, KnowledgeState.INFERRED),
        (ClaimType.HYPOTHESIS, KnowledgeState.HYPOTHESIS),
    ]
    for ct, ks in combos:
        c = make_claim(
            claim_type=ct,
            knowledge_state=ks,
            asserted_at=base,
            learned_at=base,
            recorded_at=base,
        )
        assert c.claim_type == ct
        assert c.knowledge_state == ks


# C09 同一句话多个Claim可独立Revision
def test_c09_independent_revision(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs = make_observation(
        value="我明天一定能考上某校",
        learned_at=base,
        recorded_at=base,
    )
    store.commit([obs], make_op(0))

    speech_id = new_object_id(ObjectType.CLAIM)
    pred_id = new_object_id(ObjectType.CLAIM)

    speech_fact = make_claim(
        object_id=speech_id,
        revision=1,
        claimant_id="aios-observer",
        subject_id="user-1",
        claim_type=ClaimType.FACT,
        content="用户说出了‘我明天一定能考上某校’",
        knowledge_state=KnowledgeState.OBSERVED,
        confidence=0.99,
        asserted_at=base,
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
        source_refs=[SourceRef(object_id=obs.object_id, revision=1)],
    )

    prediction = make_claim(
        object_id=pred_id,
        revision=1,
        claimant_id="user-1",
        subject_id="user-1",
        claim_type=ClaimType.PREDICTION,
        content="用户将考上某校",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.35,
        asserted_at=base,
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
        source_refs=[SourceRef(object_id=obs.object_id, revision=1)],
    )

    # Same world commit
    store.commit([speech_fact, prediction], make_op(1))

    # Revise only prediction
    pred_rev2 = make_claim(
        object_id=pred_id,
        revision=2,
        claimant_id="user-1",
        subject_id="user-1",
        claim_type=ClaimType.PREDICTION,
        content="用户将考上某校（修正置信度）",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.20,
        asserted_at=base,
        learned_at=base + timedelta(seconds=2),
        recorded_at=base + timedelta(seconds=2),
        source_refs=[SourceRef(object_id=obs.object_id, revision=1)],
    )

    store.commit([pred_rev2], make_op(2))

    # Verify
    pred_latest = store.get_payload(pred_id)
    assert pred_latest["revision"] == 2
    assert pred_latest["confidence"] == 0.20

    pred_rev1 = store.get_payload(pred_id, revision=1)
    assert pred_rev1["confidence"] == 0.35

    speech_latest = store.get_payload(speech_id)
    assert speech_latest["revision"] == 1
    assert speech_latest["confidence"] == 0.99

    assert store.current_world_revision() == 3


# C10 Revision允许认知修正
def test_c10_revision_cognitive_correction(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    claim_id = new_object_id(ObjectType.CLAIM)

    rev1 = make_claim(
        object_id=claim_id,
        revision=1,
        claim_type=ClaimType.HYPOTHESIS,
        knowledge_state=KnowledgeState.HYPOTHESIS,
        confidence=0.55,
        content="假设用户生日是明天",
        asserted_at=base,
        learned_at=base,
        recorded_at=base,
    )
    store.commit([rev1], make_op(0))

    rev2 = make_claim(
        object_id=claim_id,
        revision=2,
        claim_type=ClaimType.FACT,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.95,
        content="2026-09-15是用户生日（确认）",
        asserted_at=base,
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
    )
    store.commit([rev2], make_op(1))

    latest = store.get_payload(claim_id)
    assert latest["claim_type"] == ClaimType.FACT.value
    assert latest["knowledge_state"] == KnowledgeState.REPORTED.value
    assert latest["confidence"] == 0.95
    assert latest["revision"] == 2

    old = store.get_payload(claim_id, revision=1)
    assert old["claim_type"] == ClaimType.HYPOTHESIS.value
    assert old["confidence"] == 0.55


# C11 unknown_items
def test_c11_unknown_items(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    claim = make_claim(
        unknown_items=["具体学校", "录取结果确认来源"],
        content="用户将考上某校",
    )

    # model dump
    assert claim.unknown_items == ["具体学校", "录取结果确认来源"]

    # SQLite round-trip
    store.commit([claim], make_op(0))
    payload = store.get_payload(claim.object_id)
    assert payload["unknown_items"] == ["具体学校", "录取结果确认来源"]


# C12 support/counter字段存在
def test_c12_evidence_ref_fields():
    fields = Claim.model_fields
    assert "support_evidence_set_refs" in fields
    assert "counter_evidence_set_refs" in fields

    ev_id = new_object_id(ObjectType.EVIDENCE_SET)
    ref = ObjectRef(object_id=ev_id, revision=1)

    claim = make_claim(
        support_evidence_set_refs=[ref],
        counter_evidence_set_refs=[],
    )
    assert claim.support_evidence_set_refs[0].object_id == ev_id
    assert claim.support_evidence_set_refs[0].revision == 1

    # model-level only, don't commit fake ref to avoid M0-006 NOT_FOUND


# C13 禁止 content + confidence 简化
def test_c13_forbid_content_confidence_only():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    # Missing claimant_id, claim_type, asserted_at, knowledge_state
    with pytest.raises(ValidationError):
        Claim(
            object_id=new_object_id(ObjectType.CLAIM),
            object_type=ObjectType.CLAIM,
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            content="only content and confidence",
            confidence=0.8,
        )


# C14 object_type固定
def test_c14_object_type_fixed():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        Claim(
            object_id=new_object_id(ObjectType.CLAIM),
            object_type=ObjectType.EVENT,  # type: ignore
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            claimant_id="user-1",
            claim_type=ClaimType.FACT,
            content="test",
            valid_time=TemporalExtent.unknown_time(),
            asserted_at=base,
            knowledge_state=KnowledgeState.REPORTED,
            confidence=0.7,
        )


# C15 Core不自动产生现实真相
def test_c15_no_semantic_side_effects(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    belief = make_claim(
        claimant_id="user-1",
        subject_id="mother-subject",
        claim_type=ClaimType.BELIEF,
        content="用户认为妈妈正在生气",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.80,
        asserted_at=base,
        learned_at=base,
        recorded_at=base,
    )

    store.commit([belief], make_op(0))

    events = store.list_payloads(object_type=ObjectType.EVENT)
    goals = store.list_payloads(object_type=ObjectType.GOAL)
    assert events == []
    assert goals == []

    # Ensure no auto FACT "妈妈真的生气了"
    claims = store.list_payloads(object_type=ObjectType.CLAIM)
    assert len(claims) == 1
    assert claims[0]["content"] == "用户认为妈妈正在生气"
    assert claims[0]["claim_type"] == ClaimType.BELIEF.value


# C16 claimant vs subject independent - strict, no tautology
def test_c16_claimant_vs_subject_independent():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    claim = make_claim(
        claimant_id="user-1",
        subject_id="mother-subject",
        claim_type=ClaimType.BELIEF,
        content="用户认为妈妈生气",
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.8,
        asserted_at=base,
        learned_at=base,
        recorded_at=base,
    )
    assert claim.claimant_id == "user-1"
    assert claim.subject_id == "mother-subject"
    assert claim.claimant_id != claim.subject_id

# C17 Claim schema精确类型冻结
def test_c17_claim_schema_exact_types():
    from typing import get_args, get_origin, get_type_hints
    from datetime import datetime as dt_datetime

    hints = get_type_hints(Claim)

    assert hints["claimant_id"] is str, f"claimant_id must be exactly str, got {hints['claimant_id']}"
    assert hints["claim_type"] is ClaimType, f"claim_type must be exactly ClaimType, got {hints['claim_type']}"
    assert hints["content"] is str, f"content must be exactly str, got {hints['content']}"
    assert hints["valid_time"] is TemporalExtent, f"valid_time must be exactly TemporalExtent, got {hints['valid_time']}"
    assert hints["asserted_at"] is dt_datetime, f"asserted_at must be exactly datetime, got {hints['asserted_at']}"
    assert hints["knowledge_state"] is KnowledgeState, f"knowledge_state must be exactly KnowledgeState, got {hints['knowledge_state']}"
    assert hints["confidence"] is float, f"confidence must be exactly float, got {hints['confidence']}"

    # unknown_items: list[str]
    ann = hints["unknown_items"]
    assert get_origin(ann) is list, f"unknown_items origin must be list, got {get_origin(ann)} {ann}"
    assert get_args(ann) == (str,), f"unknown_items args must be (str,), got {get_args(ann)}"

    # support_evidence_set_refs: list[ObjectRef]
    ann = hints["support_evidence_set_refs"]
    assert get_origin(ann) is list, f"support_evidence_set_refs origin must be list, got {get_origin(ann)}"
    assert get_args(ann) == (ObjectRef,), f"support_evidence_set_refs args must be (ObjectRef,), got {get_args(ann)}"

    # counter_evidence_set_refs: list[ObjectRef]
    ann = hints["counter_evidence_set_refs"]
    assert get_origin(ann) is list, f"counter_evidence_set_refs origin must be list, got {get_origin(ann)}"
    assert get_args(ann) == (ObjectRef,), f"counter_evidence_set_refs args must be (ObjectRef,), got {get_args(ann)}"

