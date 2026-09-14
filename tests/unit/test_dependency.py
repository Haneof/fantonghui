"""M0-015 Dependency contract, cycle guard, and reverse-query tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import (
    ClaimType,
    ErrorCode,
    KnowledgeState,
    ObjectType,
    TaskType,
)
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import (
    Claim,
    Dependency,
    Entity,
    EvidenceSet,
    EventAnchor,
    Observation,
    Relation,
    Summary,
    Task,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import KnowledgeWindow, TemporalExtent
from aios_core.dependency import (
    collect_impacted_dependents,
    find_dependency_cycle,
    validate_dependency_graph_acyclic,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore, StoreError


BASE = datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc)


def common(object_type: ObjectType, *, object_id: str | None = None) -> dict:
    return {
        "object_id": object_id or new_object_id(object_type),
        "subject_id": "user-1",
        "occurred": TemporalExtent.unknown_time(),
        "learned_at": BASE,
        "recorded_at": BASE,
        "created_by": "test",
    }


def make_op(expected_world_revision: int) -> OperationRequest:
    return OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="m0_015_test_commit",
        arguments={},
        expected_world_revision=expected_world_revision,
        reason="M0-015 test",
        idempotency_key=str(uuid.uuid4()),
    )


def ref(object_id: str, revision: int = 1) -> ObjectRef:
    return ObjectRef(object_id=object_id, revision=revision)


def make_dependency(
    dependent: ObjectRef,
    dependency: ObjectRef,
    dependency_type: str = "evidence_basis",
) -> Dependency:
    return Dependency(
        **common(ObjectType.DEPENDENCY),
        dependent_ref=dependent,
        dependency_ref=dependency,
        dependency_type=dependency_type,
    )


def make_real_chain():
    observation = Observation(
        **common(ObjectType.OBSERVATION),
        source_kind="chat",
        modality="text",
        value="原始资料",
    )
    evidence = EvidenceSet(
        **common(ObjectType.EVIDENCE_SET),
        purpose="support claim",
        knowledge_window=KnowledgeWindow(
            knowledge_cutoff=BASE,
            world_revision=0,
        ),
        member_refs=[ref(observation.object_id)],
        support_refs=[ref(observation.object_id)],
        selection_method="explicit",
    )
    claim = Claim(
        **common(ObjectType.CLAIM),
        claimant_id="user-1",
        claim_type=ClaimType.FACT,
        content="一个需要证据支持的主张",
        asserted_at=BASE,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.7,
        support_evidence_set_refs=[ref(evidence.object_id)],
    )
    summary = Summary(
        **common(ObjectType.SUMMARY),
        summary_time=TemporalExtent.unknown_time(),
        granularity="day",
        source_world_revision=0,
        claim_refs=[ref(claim.object_id)],
    )
    event = EventAnchor(
        **common(ObjectType.EVENT),
        title="测试事件",
        interpretation="供 Task 依赖测试",
        confidence=0.6,
    )
    task = Task(
        **common(ObjectType.TASK),
        task_type=TaskType.FOLLOW_UP,
        title="后续复核事件",
    )
    dependencies = [
        make_dependency(ref(claim.object_id), ref(evidence.object_id), "claim_evidence"),
        make_dependency(ref(evidence.object_id), ref(observation.object_id), "evidence_member"),
        make_dependency(ref(summary.object_id), ref(claim.object_id), "summary_claim"),
        make_dependency(ref(task.object_id), ref(event.object_id), "task_event"),
    ]
    return observation, evidence, claim, summary, event, task, dependencies


def test_d01_exact_dependency_schema_and_literal_object_type():
    hints = get_type_hints(Dependency)
    assert get_origin(hints["object_type"]) is Literal
    assert get_args(hints["object_type"]) == (ObjectType.DEPENDENCY,)
    assert hints["dependent_ref"] is ObjectRef
    assert hints["dependency_ref"] is ObjectRef
    assert hints["dependency_type"] is str


def test_d02_dependency_requires_exact_pinned_versions():
    with pytest.raises(ValidationError):
        make_dependency(
            ObjectRef(object_id="claim-a", revision=None),
            ref("evidence-a"),
        )
    with pytest.raises(ValidationError):
        make_dependency(
            ref("claim-a"),
            ObjectRef(object_id="evidence-a", revision=None),
        )

    dependency = make_dependency(ref("claim-a", 2), ref("evidence-a", 3))
    assert dependency.dependent_ref.revision == 2
    assert dependency.dependency_ref.revision == 3


def test_d03_dependency_type_is_open_but_must_be_nonblank():
    dependency = make_dependency(
        ref("summary-a"),
        ref("claim-a"),
        "future_domain_specific_basis",
    )
    assert dependency.dependency_type == "future_domain_specific_basis"

    for invalid in ["", "   "]:
        with pytest.raises(ValidationError):
            make_dependency(ref("summary-a"), ref("claim-a"), invalid)


def test_d04_direct_self_dependency_is_rejected_even_across_revisions():
    with pytest.raises(ValidationError):
        make_dependency(ref("claim-a", 1), ref("claim-a", 1))
    with pytest.raises(ValidationError):
        make_dependency(ref("claim-a", 2), ref("claim-a", 1))


def test_d05_required_claim_evidence_observation_chain_is_explicit():
    observation, evidence, claim, _summary, _event, _task, dependencies = make_real_chain()
    claim_to_evidence, evidence_to_observation = dependencies[:2]

    assert claim_to_evidence.dependent_ref == ref(claim.object_id)
    assert claim_to_evidence.dependency_ref == ref(evidence.object_id)
    assert evidence_to_observation.dependent_ref == ref(evidence.object_id)
    assert evidence_to_observation.dependency_ref == ref(observation.object_id)
    assert find_dependency_cycle(dependencies[:2]) is None


def test_d06_required_summary_claim_and_task_event_edges_are_explicit():
    _observation, _evidence, claim, summary, event, task, dependencies = make_real_chain()
    summary_to_claim = dependencies[2]
    task_to_event = dependencies[3]

    assert summary_to_claim.dependent_ref == ref(summary.object_id)
    assert summary_to_claim.dependency_ref == ref(claim.object_id)
    assert task_to_event.dependent_ref == ref(task.object_id)
    assert task_to_event.dependency_ref == ref(event.object_id)


def test_d07_multi_edge_proof_cycle_is_rejected():
    a = ref("claim-a")
    b = ref("evidence-b")
    c = ref("claim-c")
    dependencies = [
        make_dependency(a, b),
        make_dependency(b, c),
        make_dependency(c, a),
    ]

    cycle = find_dependency_cycle(dependencies)
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    with pytest.raises(ValueError, match="dependency graph contains cycle"):
        validate_dependency_graph_acyclic(dependencies)


def test_d08_acyclic_dependency_chain_passes_cycle_guard():
    dependencies = [
        make_dependency(ref("summary-a"), ref("claim-b")),
        make_dependency(ref("claim-b"), ref("evidence-c")),
        make_dependency(ref("evidence-c"), ref("observation-d")),
    ]
    validate_dependency_graph_acyclic(dependencies)
    assert find_dependency_cycle(dependencies) is None


def test_d09_reverse_lookup_finds_transitive_impacts_from_bottom_object():
    observation, evidence, claim, summary, _event, _task, dependencies = make_real_chain()

    impacted = collect_impacted_dependents(
        dependencies,
        ref(observation.object_id),
    )
    assert impacted == (
        ref(evidence.object_id),
        ref(claim.object_id),
        ref(summary.object_id),
    )

    direct_only = collect_impacted_dependents(
        dependencies,
        ref(observation.object_id),
        transitive=False,
    )
    assert direct_only == (ref(evidence.object_id),)


def test_d10_reverse_lookup_is_revision_sensitive():
    dependencies = [
        make_dependency(ref("claim-a", 1), ref("observation-x", 1)),
    ]
    assert collect_impacted_dependents(
        dependencies,
        ref("observation-x", 1),
    ) == (ref("claim-a", 1),)
    assert collect_impacted_dependents(
        dependencies,
        ref("observation-x", 2),
    ) == ()


def test_d11_relation_graph_may_cycle_without_becoming_dependency_graph():
    entity_a = Entity(**common(ObjectType.ENTITY), entity_kind="person")
    entity_b = Entity(**common(ObjectType.ENTITY), entity_kind="person")
    relation_ab = Relation(
        **common(ObjectType.RELATION),
        left=ref(entity_a.object_id),
        relation_type="knows",
        right=ref(entity_b.object_id),
        confidence=0.5,
    )
    relation_ba = Relation(
        **common(ObjectType.RELATION),
        left=ref(entity_b.object_id),
        relation_type="knows",
        right=ref(entity_a.object_id),
        confidence=0.5,
    )

    assert relation_ab.left.object_id == relation_ba.right.object_id
    assert relation_ba.left.object_id == relation_ab.right.object_id
    assert find_dependency_cycle([]) is None


def test_d12_dependencies_persist_and_can_be_rebuilt_for_reverse_query(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    observation, evidence, claim, summary, event, task, dependencies = make_real_chain()

    store.commit(
        [
            observation,
            evidence,
            claim,
            summary,
            event,
            task,
            *dependencies,
        ],
        make_op(0),
    )

    payloads = store.list_payloads(object_type=ObjectType.DEPENDENCY)
    rebuilt = [Dependency.model_validate(payload) for payload in payloads]
    assert len(rebuilt) == 4

    impacted = collect_impacted_dependents(
        rebuilt,
        ref(observation.object_id),
    )
    assert ref(evidence.object_id) in impacted
    assert ref(claim.object_id) in impacted
    assert ref(summary.object_id) in impacted
    assert ref(task.object_id) not in impacted


def test_d13_post_validation_mutation_cannot_persist_floating_dependency_ref(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    observation = Observation(
        **common(ObjectType.OBSERVATION),
        source_kind="test",
        modality="text",
        value="raw",
    )
    claim_stub = Observation(
        **common(ObjectType.OBSERVATION),
        source_kind="test",
        modality="text",
        value="dependent stub",
    )
    store.commit([observation, claim_stub], make_op(0))

    dependency = make_dependency(
        ref(claim_stub.object_id),
        ref(observation.object_id),
    )
    object.__setattr__(
        dependency,
        "dependency_ref",
        ObjectRef(object_id=observation.object_id, revision=None),
    )

    with pytest.raises(StoreError) as exc_info:
        store.commit([dependency], make_op(1))
    assert exc_info.value.code is ErrorCode.INVALID_ARGUMENT
    assert exc_info.value.context["reason"] == "persistence_revalidation_failed"
    assert store.current_world_revision() == 1
    assert store.list_payloads(object_type=ObjectType.DEPENDENCY) == []


def test_d14_graph_helper_is_contract_only_not_automatic_m3_propagation():
    dependencies = [
        make_dependency(ref("summary-a"), ref("claim-b")),
    ]
    impacted = collect_impacted_dependents(dependencies, ref("claim-b"))
    assert impacted == (ref("summary-a"),)
    assert not hasattr(Dependency, "auto_revise")
    assert not hasattr(Dependency, "propagate_correction")
