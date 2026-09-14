"""M0-010 Entity + Relation（实体与关系）契约正式冻结 + R1 harden"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import get_args, get_origin, get_type_hints, Literal

import pytest
from pydantic import ValidationError

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ClaimType, KnowledgeState, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import (
    Claim,
    Entity,
    EvidenceSet,
    Observation,
    Relation,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import KnowledgeWindow, TemporalExtent, as_utc, utc_now
from aios_core.storage.sqlite_store import SQLiteWorldStore


def make_op(expected_world_revision: int = 0) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-010 test",
        idempotency_key=str(uuid.uuid4()),
    )


def make_observation(
    *,
    object_id: str | None = None,
    value: str = "obs",
    learned_at: datetime | None = None,
):
    now = utc_now()
    learned = learned_at or now
    oid = object_id or new_object_id(ObjectType.OBSERVATION)
    return Observation(
        object_id=oid,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.point(learned),
        learned_at=learned,
        recorded_at=learned,
        created_by="test",
        source_kind="device_sensor",
        modality="text",
        value=value,
    )


def make_claim_for_entity(
    *,
    object_id: str | None = None,
    subject_id: str,
    content: str = "identity claim",
    learned_at: datetime | None = None,
):
    base = learned_at or utc_now()
    oid = object_id or new_object_id(ObjectType.CLAIM)
    return Claim(
        object_id=oid,
        subject_id=subject_id,
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        claimant_id="user-1",
        claim_type=ClaimType.FACT,
        content=content,
        valid_time=TemporalExtent.unknown_time(),
        asserted_at=base,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.9,
    )


# ER01 exact schema - hardened R1 no false-green
def test_er01_exact_schema():
    assert issubclass(Entity, WorldObject)
    assert issubclass(Relation, WorldObject)

    e_hints = get_type_hints(Entity)
    assert e_hints["entity_kind"] is str
    can_ann = e_hints["canonical_name"]
    assert set(get_args(can_ann)) == {str, type(None)}
    assert get_origin(e_hints["aliases"]) is list
    assert get_args(e_hints["aliases"]) == (str,)
    assert get_origin(e_hints["identity_claim_refs"]) is list
    assert get_args(e_hints["identity_claim_refs"]) == (ObjectRef,)

    # exact Literal for Entity object_type
    entity_object_type_ann = e_hints["object_type"]
    assert get_origin(entity_object_type_ann) is Literal
    assert get_args(entity_object_type_ann) == (ObjectType.ENTITY,)

    ent = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        entity_kind="person",
    )
    assert ent.object_type == ObjectType.ENTITY

    r_hints = get_type_hints(Relation)
    assert r_hints["left"] is ObjectRef
    assert r_hints["relation_type"] is str
    assert r_hints["right"] is ObjectRef
    assert r_hints["valid_time"] is TemporalExtent
    assert get_origin(r_hints["evidence_set_refs"]) is list
    assert get_args(r_hints["evidence_set_refs"]) == (ObjectRef,)
    assert r_hints["confidence"] is float

    relation_object_type_ann = r_hints["object_type"]
    assert get_origin(relation_object_type_ann) is Literal
    assert get_args(relation_object_type_ann) == (ObjectType.RELATION,)

    rel = Relation(
        object_id=new_object_id(ObjectType.RELATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        left=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
        confidence=0.8,
    )
    assert rel.object_type == ObjectType.RELATION


# ER02 unknown entity合法
def test_er02_unknown_entity_legal(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    ent = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=utc_now(),
        recorded_at=utc_now(),
        created_by="test",
        entity_kind="person",
        canonical_name=None,
        aliases=["P001"],
        identity_claim_refs=[],
    )

    result = store.commit([ent], make_op(0))
    assert result.world_revision == 1

    payload = store.get_payload(ent.object_id)
    assert payload["canonical_name"] is None
    assert "P001" in payload["aliases"]


# ER03 unknown P001 -> 妈妈
def test_er03_unknown_to_mother(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    entity_id = new_object_id(ObjectType.ENTITY)

    rev1 = Entity(
        object_id=entity_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name=None,
        aliases=["P001"],
        identity_claim_refs=[],
    )
    store.commit([rev1], make_op(0))

    claim = make_claim_for_entity(
        subject_id=entity_id,
        content="P001对应用户的妈妈",
        learned_at=base + timedelta(seconds=1),
    )
    store.commit([claim], make_op(1))

    rev2 = Entity(
        object_id=entity_id,
        revision=2,
        subject_id="user-1",
        occurred=TemporalExtent.unknown_time(),
        learned_at=base + timedelta(seconds=2),
        recorded_at=base + timedelta(seconds=2),
        created_by="test",
        entity_kind="person",
        canonical_name="妈妈",
        aliases=["P001", "妈妈"],
        identity_claim_refs=[ObjectRef(object_id=claim.object_id, revision=1)],
    )
    store.commit([rev2], make_op(2))

    rev1_payload = store.get_payload(entity_id, revision=1)
    rev2_payload = store.get_payload(entity_id, revision=2)

    assert rev1_payload["object_id"] == rev2_payload["object_id"]
    assert rev1_payload["canonical_name"] is None
    assert rev2_payload["canonical_name"] == "妈妈"
    assert rev2_payload["identity_claim_refs"][0]["revision"] == 1


# ER04 floating identity claim拒绝
def test_er04_floating_identity_reject():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    claim_id = new_object_id(ObjectType.CLAIM)

    with pytest.raises(ValidationError) as excinfo:
        Entity(
            object_id=new_object_id(ObjectType.ENTITY),
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            entity_kind="person",
            canonical_name="test",
            identity_claim_refs=[ObjectRef(object_id=claim_id, revision=None)],
        )
    assert "identity_claim_refs requires pinned ObjectRef revisions" in str(excinfo.value)

    ent = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        identity_claim_refs=[ObjectRef(object_id=claim_id, revision=1)],
    )
    assert ent.identity_claim_refs[0].revision == 1


# ER05 同名两个小王不能自动合并
def test_er05_same_name_two_entities(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="小王",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="小王",
    )

    assert ent_a.object_id != ent_b.object_id

    store.commit([ent_a, ent_b], make_op(0))

    all_entities = store.list_payloads(object_type=ObjectType.ENTITY)
    assert len(all_entities) == 2
    ids = {e["object_id"] for e in all_entities}
    assert ent_a.object_id in ids
    assert ent_b.object_id in ids


# ER06 canonical_name不是ID
def test_er06_canonical_name_not_id(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="小王",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="小王",
    )

    assert ent_a.object_id != ent_b.object_id

    store.commit([ent_a, ent_b], make_op(0))

    rev2 = Entity(
        object_id=ent_a.object_id,
        subject_id="user-1",
        revision=2,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
        created_by="test",
        entity_kind="person",
        canonical_name="王某",
    )
    store.commit([rev2], make_op(1))

    latest = store.get_payload(ent_a.object_id)
    assert latest["canonical_name"] == "王某"
    assert latest["object_id"] == ent_a.object_id


# ER07 Relation schema / confidence
def test_er07_relation_confidence():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    left_id = new_object_id(ObjectType.ENTITY)
    right_id = new_object_id(ObjectType.ENTITY)

    rel = Relation(
        object_id=new_object_id(ObjectType.RELATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=left_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=right_id, revision=1),
        valid_time=TemporalExtent(
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 8, 31, tzinfo=timezone.utc),
        ),
        confidence=0.8,
    )
    assert rel.confidence == 0.8

    for conf in [0.0, 0.5, 1.0]:
        r = Relation(
            object_id=new_object_id(ObjectType.RELATION),
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            left=ObjectRef(object_id=left_id, revision=1),
            relation_type="colleague",
            right=ObjectRef(object_id=right_id, revision=1),
            confidence=conf,
        )
        assert r.confidence == conf

    for conf in [-0.01, 1.01]:
        with pytest.raises(ValidationError):
            Relation(
                object_id=new_object_id(ObjectType.RELATION),
                subject_id="user-1",
                revision=1,
                occurred=TemporalExtent.unknown_time(),
                learned_at=base,
                recorded_at=base,
                created_by="test",
                left=ObjectRef(object_id=left_id, revision=1),
                relation_type="colleague",
                right=ObjectRef(object_id=right_id, revision=1),
                confidence=conf,
            )


# ER08 evidence_set_refs pinned
def test_er08_evidence_pinned():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    ev_id = new_object_id(ObjectType.EVIDENCE_SET)

    with pytest.raises(ValidationError) as excinfo:
        Relation(
            object_id=new_object_id(ObjectType.RELATION),
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            left=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
            relation_type="colleague",
            right=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
            evidence_set_refs=[ObjectRef(object_id=ev_id, revision=None)],
            confidence=0.8,
        )
    assert "evidence_set_refs requires pinned ObjectRef revisions" in str(excinfo.value)

    rel = Relation(
        object_id=new_object_id(ObjectType.RELATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
        evidence_set_refs=[ObjectRef(object_id=ev_id, revision=1)],
        confidence=0.8,
    )
    assert rel.evidence_set_refs[0].revision == 1


# ER09 同名实体关系必须按ID绑定
def test_er09_relation_by_id(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="小王",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="小王",
    )
    user_ent = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="用户",
    )

    store.commit([ent_a, ent_b, user_ent], make_op(0))

    rel = Relation(
        object_id=new_object_id(ObjectType.RELATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=user_ent.object_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        confidence=0.8,
    )
    store.commit([rel], make_op(1))

    payload = store.get_payload(rel.object_id)
    assert payload["right"]["object_id"] == ent_b.object_id
    assert payload["right"]["object_id"] != ent_a.object_id


# ER10 colleague关系rev1
def test_er10_colleague_rev1(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="A",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="B",
    )
    obs = make_observation(value="与小王在同一公司工作", learned_at=base)

    store.commit([ent_a, ent_b, obs], make_op(0))

    kw = KnowledgeWindow(knowledge_cutoff=base, world_revision=1)
    es = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        purpose="colleague evidence",
        knowledge_window=kw,
        member_refs=[ObjectRef(object_id=obs.object_id, revision=1)],
        support_refs=[ObjectRef(object_id=obs.object_id, revision=1)],
        selection_method="manual",
    )
    store.commit([es], make_op(1))

    rel_id = new_object_id(ObjectType.RELATION)
    valid = TemporalExtent(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )

    rel_rev1 = Relation(
        object_id=rel_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        valid_time=valid,
        evidence_set_refs=[ObjectRef(object_id=es.object_id, revision=1)],
        confidence=0.8,
    )
    store.commit([rel_rev1], make_op(2))

    payload = store.get_payload(rel_id)
    assert payload["relation_type"] == "colleague"


# ER11 colleague -> former_colleague
def test_er11_colleague_to_former(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="A",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="B",
    )
    obs1 = make_observation(value="与小王在同一公司工作", learned_at=base)
    store.commit([ent_a, ent_b, obs1], make_op(0))

    kw1 = KnowledgeWindow(knowledge_cutoff=base, world_revision=1)
    es1 = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        purpose="colleague evidence",
        knowledge_window=kw1,
        member_refs=[ObjectRef(object_id=obs1.object_id, revision=1)],
        selection_method="manual",
    )
    store.commit([es1], make_op(1))

    rel_id = new_object_id(ObjectType.RELATION)
    valid1 = TemporalExtent(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    rel_rev1 = Relation(
        object_id=rel_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        valid_time=valid1,
        evidence_set_refs=[ObjectRef(object_id=es1.object_id, revision=1)],
        confidence=0.8,
    )
    store.commit([rel_rev1], make_op(2))

    later = base + timedelta(days=1)
    obs2 = make_observation(value="小王离职", learned_at=later)
    store.commit([obs2], make_op(3))

    kw2 = KnowledgeWindow(knowledge_cutoff=later, world_revision=4)
    es2 = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=later,
        recorded_at=later,
        created_by="test",
        purpose="former colleague evidence",
        knowledge_window=kw2,
        member_refs=[ObjectRef(object_id=obs2.object_id, revision=1)],
        selection_method="manual",
    )
    store.commit([es2], make_op(4))

    valid2 = TemporalExtent(
        start=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    rel_rev2 = Relation(
        object_id=rel_id,
        subject_id="user-1",
        revision=2,
        occurred=TemporalExtent.unknown_time(),
        learned_at=later,
        recorded_at=later,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="former_colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        valid_time=valid2,
        evidence_set_refs=[ObjectRef(object_id=es2.object_id, revision=1)],
        confidence=0.9,
    )
    store.commit([rel_rev2], make_op(5))

    latest = store.get_payload(rel_id)
    assert latest["relation_type"] == "former_colleague"
    rev1 = store.get_payload(rel_id, revision=1)
    assert rev1["relation_type"] == "colleague"


# ER12 historical world revision replay
def test_er12_historical_replay(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="A",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="B",
    )
    obs1 = make_observation(value="colleague obs", learned_at=base)
    store.commit([ent_a, ent_b, obs1], make_op(0))

    kw1 = KnowledgeWindow(knowledge_cutoff=base, world_revision=1)
    es1 = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        purpose="evidence",
        knowledge_window=kw1,
        member_refs=[ObjectRef(object_id=obs1.object_id, revision=1)],
        selection_method="manual",
    )
    store.commit([es1], make_op(1))

    rel_id = new_object_id(ObjectType.RELATION)
    rel_rev1 = Relation(
        object_id=rel_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        valid_time=TemporalExtent(
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 8, 31, tzinfo=timezone.utc),
        ),
        evidence_set_refs=[ObjectRef(object_id=es1.object_id, revision=1)],
        confidence=0.8,
    )
    res1 = store.commit([rel_rev1], make_op(2))
    world_after_rev1 = res1.world_revision

    later = base + timedelta(days=1)
    obs2 = make_observation(value="former", learned_at=later)
    store.commit([obs2], make_op(3))

    kw2 = KnowledgeWindow(knowledge_cutoff=later, world_revision=4)
    es2 = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=later,
        recorded_at=later,
        created_by="test",
        purpose="evidence2",
        knowledge_window=kw2,
        member_refs=[ObjectRef(object_id=obs2.object_id, revision=1)],
        selection_method="manual",
    )
    store.commit([es2], make_op(4))

    rel_rev2 = Relation(
        object_id=rel_id,
        subject_id="user-1",
        revision=2,
        occurred=TemporalExtent.unknown_time(),
        learned_at=later,
        recorded_at=later,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="former_colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        valid_time=TemporalExtent(
            start=datetime(2026, 9, 1, tzinfo=timezone.utc),
            end=datetime(2026, 12, 31, tzinfo=timezone.utc),
        ),
        evidence_set_refs=[ObjectRef(object_id=es2.object_id, revision=1)],
        confidence=0.9,
    )
    store.commit([rel_rev2], make_op(5))

    historical = store.list_payloads(
        object_type=ObjectType.RELATION,
        as_of_world_revision=world_after_rev1,
    )
    assert len(historical) == 1
    assert historical[0]["relation_type"] == "colleague"

    latest = store.list_payloads(object_type=ObjectType.RELATION)
    assert latest[0]["relation_type"] == "former_colleague"


# ER13 valid_time exact round-trip
def test_er13_valid_time_round_trip(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
    )
    store.commit([ent_a, ent_b], make_op(0))

    valid1 = TemporalExtent(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    rel_id = new_object_id(ObjectType.RELATION)
    rel_rev1 = Relation(
        object_id=rel_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        valid_time=valid1,
        confidence=0.8,
    )
    store.commit([rel_rev1], make_op(1))

    payload1 = store.get_payload(rel_id, revision=1)
    stored_valid1 = TemporalExtent.model_validate(payload1["valid_time"])
    assert as_utc(stored_valid1.start, "start") == as_utc(valid1.start, "expected")
    assert as_utc(stored_valid1.end, "end") == as_utc(valid1.end, "expected")

    valid2 = TemporalExtent(
        start=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    rel_rev2 = Relation(
        object_id=rel_id,
        subject_id="user-1",
        revision=2,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base + timedelta(days=1),
        recorded_at=base + timedelta(days=1),
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="former_colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        valid_time=valid2,
        confidence=0.9,
    )
    store.commit([rel_rev2], make_op(2))

    payload2 = store.get_payload(rel_id, revision=2)
    stored_valid2 = TemporalExtent.model_validate(payload2["valid_time"])
    assert as_utc(stored_valid2.start, "start") == as_utc(valid2.start, "expected")
    assert as_utc(stored_valid2.end, "end") == as_utc(valid2.end, "expected")


# ER14 Entity历史revision可回放
def test_er14_entity_history(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    entity_id = new_object_id(ObjectType.ENTITY)

    rev1 = Entity(
        object_id=entity_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name=None,
        aliases=["P001"],
        identity_claim_refs=[],
    )
    store.commit([rev1], make_op(0))

    claim = make_claim_for_entity(
        subject_id=entity_id,
        content="P001是妈妈",
        learned_at=base + timedelta(seconds=1),
    )
    store.commit([claim], make_op(1))

    rev2 = Entity(
        object_id=entity_id,
        subject_id="user-1",
        revision=2,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base + timedelta(seconds=2),
        recorded_at=base + timedelta(seconds=2),
        created_by="test",
        entity_kind="person",
        canonical_name="妈妈",
        aliases=["P001", "妈妈"],
        identity_claim_refs=[ObjectRef(object_id=claim.object_id, revision=1)],
    )
    store.commit([rev2], make_op(2))

    p1 = store.get_payload(entity_id, revision=1)
    assert p1["canonical_name"] is None
    assert "P001" in p1["aliases"]

    p2 = store.get_payload(entity_id, revision=2)
    assert p2["canonical_name"] == "妈妈"


# ER15 Relation不内嵌Entity
def test_er15_relation_not_embedded(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="A",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="B",
    )
    store.commit([ent_a, ent_b], make_op(0))

    ent_a_payload_before = store.get_payload(ent_a.object_id)
    assert "relations" not in ent_a_payload_before

    rel = Relation(
        object_id=new_object_id(ObjectType.RELATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        confidence=0.8,
    )
    store.commit([rel], make_op(1))

    ent_a_payload_after = store.get_payload(ent_a.object_id)
    assert ent_a_payload_after["canonical_name"] == "A"
    assert "relations" not in ent_a_payload_after


# ER16 object_type固定
def test_er16_object_type_fixed():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        Entity(
            object_id=new_object_id(ObjectType.ENTITY),
            object_type=ObjectType.RELATION,  # type: ignore
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            entity_kind="person",
        )

    with pytest.raises(ValidationError):
        Relation(
            object_id=new_object_id(ObjectType.RELATION),
            object_type=ObjectType.ENTITY,  # type: ignore
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            left=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
            relation_type="colleague",
            right=ObjectRef(object_id=new_object_id(ObjectType.ENTITY), revision=1),
            confidence=0.8,
        )


# ER17 identity_claim post-validation mutation
def test_er17_identity_mutation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    claim = make_claim_for_entity(
        subject_id="entity-1",
        content="identity",
        learned_at=base,
    )
    store.commit([claim], make_op(0))

    ent = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="test",
        identity_claim_refs=[ObjectRef(object_id=claim.object_id, revision=1)],
    )

    ent.identity_claim_refs.append(
        ObjectRef(object_id=claim.object_id, revision=None)
    )

    assert ent.identity_claim_refs[-1].revision is None

    from aios_core.storage.sqlite_store import StoreError
    from aios_core.contracts.enums import ErrorCode

    with pytest.raises(StoreError) as excinfo:
        store.commit([ent], make_op(1))

    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 1


# ER18 relation evidence post-validation mutation - fixed real endpoints
def test_er18_relation_evidence_mutation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    ent_a = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="A",
    )
    ent_b = Entity(
        object_id=new_object_id(ObjectType.ENTITY),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        entity_kind="person",
        canonical_name="B",
    )
    obs = make_observation(learned_at=base)
    store.commit([ent_a, ent_b, obs], make_op(0))

    kw = KnowledgeWindow(knowledge_cutoff=base, world_revision=1)
    es = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        purpose="test",
        knowledge_window=kw,
        member_refs=[ObjectRef(object_id=obs.object_id, revision=1)],
        selection_method="manual",
    )
    store.commit([es], make_op(1))

    rel = Relation(
        object_id=new_object_id(ObjectType.RELATION),
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        left=ObjectRef(object_id=ent_a.object_id, revision=1),
        relation_type="colleague",
        right=ObjectRef(object_id=ent_b.object_id, revision=1),
        evidence_set_refs=[ObjectRef(object_id=es.object_id, revision=1)],
        confidence=0.8,
    )

    rel.evidence_set_refs.append(
        ObjectRef(object_id=es.object_id, revision=None)
    )

    assert rel.evidence_set_refs[-1].revision is None

    from aios_core.storage.sqlite_store import StoreError
    from aios_core.contracts.enums import ErrorCode

    with pytest.raises(StoreError) as excinfo:
        store.commit([rel], make_op(2))

    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 2
    with pytest.raises(StoreError):
        store.get_payload(rel.object_id)


# ER19 exact Literal mutation guard
def test_er19_object_type_annotations_exact():
    e_hints = get_type_hints(Entity)
    entity_object_type_ann = e_hints["object_type"]
    assert get_origin(entity_object_type_ann) is Literal
    assert get_args(entity_object_type_ann) == (ObjectType.ENTITY,)

    r_hints = get_type_hints(Relation)
    relation_object_type_ann = r_hints["object_type"]
    assert get_origin(relation_object_type_ann) is Literal
    assert get_args(relation_object_type_ann) == (ObjectType.RELATION,)
