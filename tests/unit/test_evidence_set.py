"""M0-009 EvidenceSet（一等证据集合）契约冻结 + R1 durable boundary"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import get_args, get_origin, get_type_hints, Any

import pytest
from pydantic import ValidationError

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import (
    EvidenceCoverage,
    EvidenceSelector,
    EvidenceSet,
    Observation,
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
        reason="M0-009 test",
        idempotency_key=str(uuid.uuid4()),
    )


def make_observation(
    *,
    object_id: str | None = None,
    value: Any = "obs",
    learned_at: datetime | None = None,
    recorded_at: datetime | None = None,
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
        source_kind="device_sensor",
        modality="text",
        value=value,
    )


def make_knowledge_window(
    *,
    knowledge_cutoff: datetime | None = None,
    world_revision: int | None = None,
):
    cutoff = knowledge_cutoff or utc_now()
    return KnowledgeWindow(
        knowledge_cutoff=cutoff,
        world_revision=world_revision,
    )


def make_evidence_set(
    *,
    object_id: str | None = None,
    revision: int = 1,
    purpose: str = "test purpose",
    knowledge_window: KnowledgeWindow | None = None,
    member_refs: list[ObjectRef] | None = None,
    support_refs: list[ObjectRef] | None = None,
    counter_refs: list[ObjectRef] | None = None,
    context_refs: list[ObjectRef] | None = None,
    selector: EvidenceSelector | None = None,
    selection_method: str = "manual",
    aggregation_method: str | None = None,
    aggregation_version: str | None = None,
    coverage: EvidenceCoverage | None = None,
    stale: bool = False,
    learned_at: datetime | None = None,
    recorded_at: datetime | None = None,
):
    now = utc_now()
    learned = learned_at or now
    recorded = recorded_at if recorded_at is not None else learned
    if knowledge_window is None:
        knowledge_window = make_knowledge_window(knowledge_cutoff=learned)

    oid = object_id or new_object_id(ObjectType.EVIDENCE_SET)
    return EvidenceSet(
        object_id=oid,
        subject_id="user-1",
        revision=revision,
        occurred=TemporalExtent.unknown_time(),
        learned_at=learned,
        recorded_at=recorded,
        created_by="test",
        purpose=purpose,
        knowledge_window=knowledge_window,
        member_refs=member_refs if member_refs is not None else [],
        support_refs=support_refs if support_refs is not None else [],
        counter_refs=counter_refs if counter_refs is not None else [],
        context_refs=context_refs if context_refs is not None else [],
        selector=selector,
        selection_method=selection_method,
        aggregation_method=aggregation_method,
        aggregation_version=aggregation_version,
        coverage=coverage or EvidenceCoverage(),
        stale=stale,
    )


def make_selector(
    *,
    selector_type: str = "dimension_interval",
    subject_id: str = "user-1",
    time_range: TemporalExtent | None = None,
    dimension_refs: list[ObjectRef] | None = None,
    filters: dict[str, Any] | None = None,
    algorithm_version: str = "v1",
):
    tr = time_range or TemporalExtent(
        start=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc),
    )
    return EvidenceSelector(
        selector_type=selector_type,
        subject_id=subject_id,
        time_range=tr,
        dimension_refs=dimension_refs or [],
        filters=filters or {},
        algorithm_version=algorithm_version,
    )


# E01 schema exact types - hardened R1
def test_e01_schema_exact_types():
    assert issubclass(EvidenceSet, WorldObject)

    hints = get_type_hints(EvidenceSet)
    assert hints["purpose"] is str
    assert hints["knowledge_window"] is KnowledgeWindow
    assert get_origin(hints["member_refs"]) is list
    assert get_args(hints["member_refs"]) == (ObjectRef,)
    assert get_origin(hints["support_refs"]) is list
    assert get_args(hints["support_refs"]) == (ObjectRef,)
    assert get_origin(hints["counter_refs"]) is list
    assert get_args(hints["counter_refs"]) == (ObjectRef,)
    assert get_origin(hints["context_refs"]) is list
    assert get_args(hints["context_refs"]) == (ObjectRef,)

    # selector exact set {EvidenceSelector, None}
    sel_ann = hints["selector"]
    assert set(get_args(sel_ann)) == {EvidenceSelector, type(None)}, f"selector must be exactly EvidenceSelector | None, got {get_args(sel_ann)}"

    assert hints["selection_method"] is str
    assert set(get_args(hints["aggregation_method"])) == {str, type(None)}, f"aggregation_method must be exactly str | None"
    assert set(get_args(hints["aggregation_version"])) == {str, type(None)}, f"aggregation_version must be exactly str | None"

    assert hints["coverage"] is EvidenceCoverage
    assert hints["stale"] is bool

    sel_hints = get_type_hints(EvidenceSelector)
    assert sel_hints["time_range"] is TemporalExtent
    assert get_origin(sel_hints["dimension_refs"]) is list
    assert get_args(sel_hints["dimension_refs"]) == (ObjectRef,)
    assert get_origin(sel_hints["filters"]) is dict
    assert get_args(sel_hints["filters"]) == (str, Any), f"filters must be dict[str, Any], got {get_args(sel_hints['filters'])}"
    assert sel_hints["algorithm_version"] is str

    cov_hints = get_type_hints(EvidenceCoverage)
    assert set(get_args(cov_hints["expected_count"])) == {int, type(None)}
    assert set(get_args(cov_hints["observed_count"])) == {int, type(None)}
    assert set(get_args(cov_hints["coverage_ratio"])) == {float, type(None)}
    assert get_origin(cov_hints["missing_description"]) is list
    assert get_args(cov_hints["missing_description"]) == (str,)


# E02 empty EvidenceSet拒绝
def test_e02_empty_reject():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base)
    with pytest.raises(ValidationError):
        make_evidence_set(
            member_refs=[],
            selector=None,
            purpose="综合多个维度判断",
            selection_method="AI认为如此",
            knowledge_window=kw,
            learned_at=base,
            recorded_at=base,
        )


# E03 explicit members
def test_e03_explicit_members(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs_a = make_observation(value="A", learned_at=base, recorded_at=base)
    obs_b = make_observation(value="B", learned_at=base, recorded_at=base)

    store.commit([obs_a, obs_b], make_op(0))

    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)
    es = make_evidence_set(
        member_refs=[
            ObjectRef(object_id=obs_a.object_id, revision=1),
            ObjectRef(object_id=obs_b.object_id, revision=1),
        ],
        selector=None,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )

    result = store.commit([es], make_op(1))
    assert result.world_revision == 2

    payload = store.get_payload(es.object_id)
    assert len(payload["member_refs"]) == 2
    assert payload["member_refs"][0]["revision"] == 1


# E04 member floating拒绝
def test_e04_member_floating_reject():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base)
    obs_id = new_object_id(ObjectType.OBSERVATION)

    with pytest.raises(ValidationError) as excinfo:
        make_evidence_set(
            member_refs=[ObjectRef(object_id=obs_id, revision=None)],
            selector=None,
            knowledge_window=kw,
            learned_at=base,
            recorded_at=base,
        )
    assert "member_refs requires pinned ObjectRef revisions" in str(excinfo.value)


# E05 support/counter/context floating拒绝
def test_e05_support_counter_context_floating_reject():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base)
    obs_id = new_object_id(ObjectType.OBSERVATION)
    pinned = ObjectRef(object_id=new_object_id(ObjectType.OBSERVATION), revision=1)

    with pytest.raises(ValidationError) as excinfo:
        make_evidence_set(
            member_refs=[pinned],
            support_refs=[ObjectRef(object_id=obs_id, revision=None)],
            knowledge_window=kw,
            learned_at=base,
            recorded_at=base,
        )
    assert "support_refs requires pinned ObjectRef revisions" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        make_evidence_set(
            member_refs=[pinned],
            counter_refs=[ObjectRef(object_id=obs_id, revision=None)],
            knowledge_window=kw,
            learned_at=base,
            recorded_at=base,
        )
    assert "counter_refs requires pinned ObjectRef revisions" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        make_evidence_set(
            member_refs=[pinned],
            context_refs=[ObjectRef(object_id=obs_id, revision=None)],
            knowledge_window=kw,
            learned_at=base,
            recorded_at=base,
        )
    assert "context_refs requires pinned ObjectRef revisions" in str(excinfo.value)


# E06 selector dimension floating拒绝
def test_e06_selector_dimension_floating_reject():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base)
    dim_id = new_object_id(ObjectType.DIMENSION_DEFINITION)

    selector_floating = make_selector(
        dimension_refs=[ObjectRef(object_id=dim_id, revision=None)]
    )

    with pytest.raises(ValidationError) as excinfo:
        make_evidence_set(
            member_refs=[],
            selector=selector_floating,
            knowledge_window=kw,
            learned_at=base,
            recorded_at=base,
        )
    assert "selector.dimension_refs requires pinned ObjectRef revisions" in str(excinfo.value)

    selector_pinned = make_selector(
        dimension_refs=[ObjectRef(object_id=dim_id, revision=1)]
    )
    es = make_evidence_set(
        member_refs=[],
        selector=selector_pinned,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )
    assert es.selector.dimension_refs[0].revision == 1


# E07 selector-only合法
def test_e07_selector_only_legal():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base)

    selector = make_selector(
        selector_type="dimension_interval",
        subject_id="user-1",
        time_range=TemporalExtent(
            start=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc),
        ),
        dimension_refs=[],
        filters={},
        algorithm_version="v1",
    )

    es = make_evidence_set(
        member_refs=[],
        selector=selector,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )
    assert es.selector is not None
    assert es.member_refs == []


# E08 selector materialization contract
def test_e08_selector_materialization(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs_a = make_observation(value="A", learned_at=base, recorded_at=base)
    obs_b = make_observation(value="B", learned_at=base, recorded_at=base)
    store.commit([obs_a, obs_b], make_op(0))

    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)
    selector = make_selector()

    es_id = new_object_id(ObjectType.EVIDENCE_SET)
    es_rev1 = make_evidence_set(
        object_id=es_id,
        revision=1,
        member_refs=[],
        selector=selector,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )
    store.commit([es_rev1], make_op(1))

    es_rev2 = make_evidence_set(
        object_id=es_id,
        revision=2,
        member_refs=[
            ObjectRef(object_id=obs_a.object_id, revision=1),
            ObjectRef(object_id=obs_b.object_id, revision=1),
        ],
        selector=selector,
        knowledge_window=kw,
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
    )
    store.commit([es_rev2], make_op(2))

    rev1_payload = store.get_payload(es_id, revision=1)
    assert rev1_payload["member_refs"] == []

    rev2_payload = store.get_payload(es_id, revision=2)
    assert len(rev2_payload["member_refs"]) == 2


# E09 fixed interval one week later - hardened exact
def test_e09_fixed_interval(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    expected_start = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    expected_end = datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc)
    expected_cutoff = datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc)

    time_range = TemporalExtent(
        start=expected_start,
        end=expected_end,
    )
    kw = make_knowledge_window(knowledge_cutoff=expected_cutoff, world_revision=1)

    selector = make_selector(time_range=time_range)

    learned = expected_cutoff
    es = make_evidence_set(
        member_refs=[],
        selector=selector,
        knowledge_window=kw,
        learned_at=learned,
        recorded_at=learned,
    )
    store.commit([es], make_op(0))

    later = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
    obs_new = make_observation(value="new", learned_at=later, recorded_at=later)
    store.commit([obs_new], make_op(1))

    old_payload = store.get_payload(es.object_id, revision=1)

    stored_extent = TemporalExtent.model_validate(
        old_payload["selector"]["time_range"]
    )
    stored_window = KnowledgeWindow.model_validate(
        old_payload["knowledge_window"]
    )

    assert as_utc(stored_extent.start, "start") == as_utc(expected_start, "expected_start")
    assert as_utc(stored_extent.end, "end") == as_utc(expected_end, "expected_end")
    assert as_utc(stored_window.knowledge_cutoff, "knowledge_cutoff") == as_utc(expected_cutoff, "expected_cutoff")
    assert stored_window.world_revision == 1
    assert old_payload["member_refs"] == []
    assert obs_new.object_id not in [ref["object_id"] for ref in old_payload["member_refs"]]


# E10 dynamic time替代拒绝
def test_e10_dynamic_time_reject():
    with pytest.raises(ValidationError):
        EvidenceSelector(
            selector_type="dimension_interval",
            subject_id="user-1",
            time_range="now-14d",  # type: ignore
            dimension_refs=[],
            filters={},
            algorithm_version="v1",
        )

    with pytest.raises(ValidationError):
        EvidenceSelector(
            selector_type="dimension_interval",
            subject_id="user-1",
            time_range=TemporalExtent(
                start=datetime(2026, 9, 1, tzinfo=timezone.utc),
                end=datetime(2026, 9, 14, tzinfo=timezone.utc),
            ),
            dimension_refs=[],
            filters={},
            algorithm_version="v1",
            relative_time="last_2_weeks",  # type: ignore
        )


# E11 support/counter/context separation
def test_e11_separation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs_s = make_observation(value="support", learned_at=base, recorded_at=base)
    obs_c = make_observation(value="counter", learned_at=base, recorded_at=base)
    obs_x = make_observation(value="context", learned_at=base, recorded_at=base)
    store.commit([obs_s, obs_c, obs_x], make_op(0))

    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)

    es = make_evidence_set(
        member_refs=[ObjectRef(object_id=obs_s.object_id, revision=1)],
        support_refs=[ObjectRef(object_id=obs_s.object_id, revision=1)],
        counter_refs=[ObjectRef(object_id=obs_c.object_id, revision=1)],
        context_refs=[ObjectRef(object_id=obs_x.object_id, revision=1)],
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )
    store.commit([es], make_op(1))

    payload = store.get_payload(es.object_id)
    assert payload["support_refs"][0]["object_id"] == obs_s.object_id
    assert payload["counter_refs"][0]["object_id"] == obs_c.object_id
    assert payload["context_refs"][0]["object_id"] == obs_x.object_id


# E12 coverage/missingness visible
def test_e12_coverage(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base)

    coverage = EvidenceCoverage(
        expected_count=10,
        observed_count=7,
        coverage_ratio=0.7,
        missing_description=["09:30-09:45 心率缺失", "没有比赛名称"],
    )

    obs = make_observation(learned_at=base, recorded_at=base)
    store.commit([obs], make_op(0))

    es2 = make_evidence_set(
        member_refs=[ObjectRef(object_id=obs.object_id, revision=1)],
        coverage=coverage,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )
    store.commit([es2], make_op(1))

    payload = store.get_payload(es2.object_id)
    assert payload["coverage"]["expected_count"] == 10
    assert payload["coverage"]["observed_count"] == 7
    assert payload["coverage"]["coverage_ratio"] == 0.7
    assert payload["coverage"]["missing_description"] == [
        "09:30-09:45 心率缺失",
        "没有比赛名称",
    ]


# E13 KnowledgeWindow cutoff不能未来 - strict
def test_e13_cutoff_future_reject():
    learned = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    cutoff_future = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    kw_future = make_knowledge_window(knowledge_cutoff=cutoff_future)

    with pytest.raises(ValidationError) as excinfo:
        make_evidence_set(
            member_refs=[ObjectRef(object_id=new_object_id(ObjectType.OBSERVATION), revision=1)],
            knowledge_window=kw_future,
            learned_at=learned,
            recorded_at=learned,
        )
    assert "knowledge_window.knowledge_cutoff must not be after learned_at" in str(excinfo.value)

    kw_equal = make_knowledge_window(knowledge_cutoff=learned)
    es_equal = make_evidence_set(
        member_refs=[ObjectRef(object_id=new_object_id(ObjectType.OBSERVATION), revision=1)],
        knowledge_window=kw_equal,
        learned_at=learned,
        recorded_at=learned,
    )
    assert es_equal.knowledge_window.knowledge_cutoff == learned

    cutoff_past = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
    kw_past = make_knowledge_window(knowledge_cutoff=cutoff_past)
    es_past = make_evidence_set(
        member_refs=[ObjectRef(object_id=new_object_id(ObjectType.OBSERVATION), revision=1)],
        knowledge_window=kw_past,
        learned_at=learned,
        recorded_at=learned,
    )
    assert es_past.knowledge_window.knowledge_cutoff == cutoff_past


# E14 KnowledgeWindow world_revision round-trip
def test_e14_world_revision_round_trip(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(
        knowledge_cutoff=base,
        world_revision=7,
    )

    obs = make_observation(learned_at=base, recorded_at=base)
    store.commit([obs], make_op(0))

    es2 = make_evidence_set(
        member_refs=[ObjectRef(object_id=obs.object_id, revision=1)],
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )
    store.commit([es2], make_op(1))

    payload = store.get_payload(es2.object_id)
    assert payload["knowledge_window"]["world_revision"] == 7


# E15 pinned history不漂移
def test_e15_pinned_history(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    target_id = new_object_id(ObjectType.OBSERVATION)
    target_rev1 = Observation(
        object_id=target_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.point(base),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        source_kind="device_sensor",
        modality="text",
        value="old",
    )
    store.commit([target_rev1], make_op(0))

    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)
    es = make_evidence_set(
        member_refs=[ObjectRef(object_id=target_id, revision=1)],
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )
    store.commit([es], make_op(1))

    target_rev2 = Observation(
        object_id=target_id,
        subject_id="user-1",
        revision=2,
        occurred=TemporalExtent.point(base + timedelta(seconds=1)),
        learned_at=base + timedelta(seconds=1),
        recorded_at=base + timedelta(seconds=1),
        created_by="test",
        source_kind="device_sensor",
        modality="text",
        value="new",
    )
    store.commit([target_rev2], make_op(2))

    es_payload = store.get_payload(es.object_id)
    assert es_payload["member_refs"][0]["revision"] == 1

    member_ref = es_payload["member_refs"][0]
    target_via_ref = store.get_payload(
        member_ref["object_id"], revision=member_ref["revision"]
    )
    assert target_via_ref["value"] == "old"


# E16 stale/rebuild revision capability
def test_e16_stale_rebuild(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs_a = make_observation(value="A", learned_at=base, recorded_at=base)
    store.commit([obs_a], make_op(0))

    kw1 = make_knowledge_window(knowledge_cutoff=base, world_revision=1)
    es_id = new_object_id(ObjectType.EVIDENCE_SET)

    es_rev1 = make_evidence_set(
        object_id=es_id,
        revision=1,
        member_refs=[ObjectRef(object_id=obs_a.object_id, revision=1)],
        knowledge_window=kw1,
        stale=False,
        learned_at=base,
        recorded_at=base,
    )
    store.commit([es_rev1], make_op(1))

    later = base + timedelta(hours=1)
    obs_b = make_observation(value="B", learned_at=later, recorded_at=later)
    store.commit([obs_b], make_op(2))

    es_rev2 = make_evidence_set(
        object_id=es_id,
        revision=2,
        member_refs=[ObjectRef(object_id=obs_a.object_id, revision=1)],
        knowledge_window=kw1,
        stale=True,
        learned_at=later,
        recorded_at=later,
    )
    store.commit([es_rev2], make_op(3))

    kw3 = make_knowledge_window(knowledge_cutoff=later, world_revision=4)
    es_rev3 = make_evidence_set(
        object_id=es_id,
        revision=3,
        member_refs=[
            ObjectRef(object_id=obs_a.object_id, revision=1),
            ObjectRef(object_id=obs_b.object_id, revision=1),
        ],
        knowledge_window=kw3,
        stale=False,
        learned_at=later,
        recorded_at=later,
    )
    store.commit([es_rev3], make_op(4))

    rev1_payload = store.get_payload(es_id, revision=1)
    assert rev1_payload["stale"] is False
    assert len(rev1_payload["member_refs"]) == 1

    rev2_payload = store.get_payload(es_id, revision=2)
    assert rev2_payload["stale"] is True

    rev3_payload = store.get_payload(es_id, revision=3)
    assert rev3_payload["stale"] is False
    assert len(rev3_payload["member_refs"]) == 2


# E17 coverage bounds
def test_e17_coverage_bounds():
    for ratio in [0.0, 0.5, 1.0]:
        cov = EvidenceCoverage(coverage_ratio=ratio)
        assert cov.coverage_ratio == ratio

    for ratio in [-0.01, 1.01]:
        with pytest.raises(ValidationError):
            EvidenceCoverage(coverage_ratio=ratio)

    for count in [-1]:
        with pytest.raises(ValidationError):
            EvidenceCoverage(expected_count=count)
        with pytest.raises(ValidationError):
            EvidenceCoverage(observed_count=count)

    cov = EvidenceCoverage(expected_count=5, observed_count=10)
    assert cov.observed_count == 10


# E18 object_type固定
def test_e18_object_type_fixed():
    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base)
    with pytest.raises(ValidationError):
        EvidenceSet(
            object_id=new_object_id(ObjectType.EVIDENCE_SET),
            object_type=ObjectType.EVENT,  # type: ignore
            subject_id="user-1",
            revision=1,
            occurred=TemporalExtent.unknown_time(),
            learned_at=base,
            recorded_at=base,
            created_by="test",
            purpose="test",
            knowledge_window=kw,
            member_refs=[ObjectRef(object_id=new_object_id(ObjectType.OBSERVATION), revision=1)],
            selection_method="manual",
        )


# E19 Evidence ref pin exact annotation
def test_e19_ref_pin_exact_annotation():
    hints = get_type_hints(EvidenceSet)
    for field in ["member_refs", "support_refs", "counter_refs", "context_refs"]:
        ann = hints[field]
        assert get_origin(ann) is list
        assert get_args(ann) == (ObjectRef,)


# E20 member_refs原地mutation攻击 - persistence revalidation
def test_e20_member_mutation_persistence(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    target = make_observation(value="target", learned_at=base, recorded_at=base)
    store.commit([target], make_op(0))
    assert store.current_world_revision() == 1

    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)
    es = make_evidence_set(
        member_refs=[ObjectRef(object_id=target.object_id, revision=1)],
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )

    es.member_refs.append(
        ObjectRef(object_id=target.object_id, revision=None)
    )

    assert es.member_refs[-1].revision is None

    from aios_core.storage.sqlite_store import StoreError
    from aios_core.contracts.enums import ErrorCode

    with pytest.raises(StoreError) as excinfo:
        store.commit([es], make_op(1))

    err = excinfo.value
    assert err.code == ErrorCode.INVALID_ARGUMENT
    assert err.context["reason"] == "persistence_revalidation_failed"
    assert err.context["object_id"] == es.object_id
    assert err.context["object_type"] == ObjectType.EVIDENCE_SET.value
    assert err.context["revision"] == 1

    assert store.current_world_revision() == 1
    with pytest.raises(StoreError):
        store.get_payload(es.object_id)


# E21 selector.dimension_refs嵌套mutation攻击
def test_e21_selector_dimension_mutation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    from aios_core.contracts.models import DimensionDefinition
    dim_id = new_object_id(ObjectType.DIMENSION_DEFINITION)
    dim = DimensionDefinition(
        object_id=dim_id,
        subject_id="user-1",
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=base,
        recorded_at=base,
        created_by="test",
        name="test_dim",
        description="test",
        data_shape="scalar",
    )
    store.commit([dim], make_op(0))
    assert store.current_world_revision() == 1

    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)
    selector = make_selector(
        dimension_refs=[ObjectRef(object_id=dim_id, revision=1)]
    )

    es = make_evidence_set(
        member_refs=[],
        selector=selector,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )

    es.selector.dimension_refs.append(
        ObjectRef(object_id=dim_id, revision=None)
    )

    assert es.selector.dimension_refs[-1].revision is None

    from aios_core.storage.sqlite_store import StoreError
    from aios_core.contracts.enums import ErrorCode

    with pytest.raises(StoreError) as excinfo:
        store.commit([es], make_op(1))

    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 1
    with pytest.raises(StoreError):
        store.get_payload(es.object_id)


# E22 nested EvidenceCoverage mutation攻击
def test_e22_coverage_mutation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    obs_a = make_observation(value="A", learned_at=base, recorded_at=base)
    store.commit([obs_a], make_op(0))
    assert store.current_world_revision() == 1

    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)
    coverage = EvidenceCoverage(
        expected_count=10,
        observed_count=7,
        coverage_ratio=0.7,
    )

    es = make_evidence_set(
        member_refs=[ObjectRef(object_id=obs_a.object_id, revision=1)],
        coverage=coverage,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )

    es.coverage.coverage_ratio = 1.5  # type: ignore

    assert es.coverage.coverage_ratio == 1.5

    from aios_core.storage.sqlite_store import StoreError
    from aios_core.contracts.enums import ErrorCode

    with pytest.raises(StoreError) as excinfo:
        store.commit([es], make_op(1))

    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 1
    with pytest.raises(StoreError):
        store.get_payload(es.object_id)


# E23 selector.time_range mutation攻击
def test_e23_time_range_mutation(tmp_path):
    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    base = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    kw = make_knowledge_window(knowledge_cutoff=base, world_revision=1)

    time_range = TemporalExtent(
        start=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc),
    )
    selector = make_selector(time_range=time_range)

    es = make_evidence_set(
        member_refs=[],
        selector=selector,
        knowledge_window=kw,
        learned_at=base,
        recorded_at=base,
    )

    es.selector.time_range = "now-14d"  # type: ignore

    from aios_core.storage.sqlite_store import StoreError
    from aios_core.contracts.enums import ErrorCode

    with pytest.raises(StoreError) as excinfo:
        store.commit([es], make_op(0))

    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 0
    with pytest.raises(StoreError):
        store.get_payload(es.object_id)
