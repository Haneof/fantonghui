from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import aios_core.world.retrospective_annotation as retrospective_module
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.retrospective_annotation import (
    AnnotationConflictError,
    BiTemporalEpistemicLens,
    DependencyEdge,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationJournal,
    SingleHopCascadeIsolator,
)

TODAY = datetime(2026, 9, 16, 9, 30, tzinfo=UTC)
T0 = TODAY - timedelta(days=730)
PARTNER_ENTITY_ID = "entity_pre_a_offshore_ip_custodian"
USER_SUBJECT_ID = "founder_subject_pre_a_incubation"
ANNOTATION_ID = "rta_judicial_freeze_day_730"


def _commercial_observation(index: int, occurred_at: datetime) -> Observation:
    scenario = index % 5
    if scenario == 0:
        modality = "technical_governance_review"
        value = {
            "artifact": f"distributed-runtime-architecture-rfc-{index:05d}",
            "review_vector": "consensus-safety-and-ip-boundary",
            "decision_state": "jointly-ratified-under-pre-a-veto-matrix",
            "counterparty_role": "core-technology-general-partner",
        }
    elif scenario == 1:
        modality = "institutional_funds_evidence"
        value = {
            "bank_instruction_ref": f"cross-border-capital-call-{index:05d}",
            "settlement_currency": "CNY",
            "amount_minor_units": 80_000_000 + index * 137,
            "beneficial_owner_attestation": "nominee-holding-protocol-v4",
        }
    elif scenario == 2:
        modality = "high_pressure_negotiation_biosignal"
        value = {
            "hrv_rmssd_ms": 18.0 + (index % 17) / 10,
            "cortisol_proxy_zscore": 2.1 + (index % 13) / 100,
            "negotiation_phase": "anti-dilution-and-liquidation-preference",
            "sensor_fusion_confidence": 0.94,
        }
    elif scenario == 3:
        modality = "fiduciary_contract_execution"
        value = {
            "instrument": "Pre-A联合孵化与股权代持对赌协议",
            "clause_vector": f"ip-custody-joint-control-{index % 41:02d}",
            "execution_status": "counterparty-performance-recorded",
            "governing_law": "PRC-commercial-and-corporate",
        }
    else:
        modality = "intellectual_property_chain_of_custody"
        value = {
            "repository_attestation": f"core-patent-family-{index:05d}",
            "custody_state": "joint-incubation-trust-assumption",
            "export_control_review": "completed",
            "offshore_transfer_disclosure": "none-known-at-observation-time",
        }

    return Observation(
        object_id=f"obs_pre_a_chain_{index:05d}",
        subject_id=USER_SUBJECT_ID,
        revision=1,
        occurred=TemporalExtent.point(occurred_at),
        learned_at=occurred_at,
        recorded_at=occurred_at,
        created_by="m1-018-commercial-scenario-fixture",
        source_kind="signed-enterprise-evidence-stream",
        modality=modality,
        value=value,
        data_quality={
            "evidence_grade": "auditable",
            "sequence": index,
        },
        metadata={
            "target_entity_id": PARTNER_ENTITY_ID,
            "agreement_id": "pre-a-joint-incubation-nominee-equity-v4",
            "day_ordinal": (occurred_at - T0).days,
        },
    )


def _build_observation_chain(count: int = 18_000) -> list[Observation]:
    total_seconds = int((TODAY - T0).total_seconds()) - 1
    denominator = count - 1
    return [
        _commercial_observation(
            index,
            T0 + timedelta(seconds=(index * total_seconds) // denominator),
        )
        for index in range(count)
    ]


def _physical_observation_hashes(
    db_path: Path,
    *,
    connect: object = sqlite3.connect,
) -> dict[tuple[str, int], str]:
    connection = connect(db_path)  # type: ignore[operator]
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT object_id, revision, object_type, subject_id,
                   world_revision, learned_at, recorded_at, payload_json
            FROM object_revisions
            ORDER BY object_id, revision
            """
        ).fetchall()
    finally:
        connection.close()

    result: dict[tuple[str, int], str] = {}
    for row in rows:
        physical_record = json.dumps(
            {key: row[key] for key in row.keys()},  # noqa: SIM118
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        result[(row["object_id"], row["revision"])] = hashlib.sha256(
            physical_record
        ).hexdigest()
    return result


def _judicial_annotation() -> RetrospectiveAnnotation:
    return RetrospectiveAnnotation(
        annotation_id=ANNOTATION_ID,
        target_entity_id=PARTNER_ENTITY_ID,
        semantic_overlay=(
            "第730日司法冻结查封裁定确认：该核心技术合伙人自联合孵化关系设立之初，"
            "即通过关联离岸空壳公司转移核心知识产权，并隐匿巨额对外连带担保；"
            "据此对历史商业信任作欺诈风险重估，但不得改写任一历史客观事实。"
        ),
        target_time_start=T0,
        target_time_end=TODAY,
        learned_at=TODAY,
        source_statement_ref=(
            "judicial-freeze-order://financial-court/2026/pre-a-ip-seizure-730"
        ),
    )


def test_18k_observations_remain_byte_identical_after_today_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """18,000-row hard gate: append one overlay without touching historical rows."""

    db_path = tmp_path / "pre_a_retrospective_world.sqlite3"
    world_store = SQLiteWorldStore(db_path)
    journal = RetrospectiveAnnotationJournal(db_path)
    observations = _build_observation_chain()
    commit = world_store.commit(
        observations,
        OperationRequest(
            operation_id="op_seed_pre_a_18000_observations",
            session_id="session_pre_a_forensic_reconstruction",
            operation_name="world.commit.pre_a_evidence_chain",
            arguments={"observation_count": 18_000, "period_days": 730},
            expected_world_revision=0,
            reason="seed immutable high-entropy Pre-A evidence chain",
            idempotency_key="idem_seed_pre_a_18000_observations",
        ),
    )
    assert commit.world_revision == 1
    assert len(commit.object_refs) == 18_000

    real_connect = sqlite3.connect
    before = _physical_observation_hashes(db_path, connect=real_connect)
    assert len(before) == 18_000
    assert all(len(digest) == 64 for digest in before.values())

    traced_statements: list[str] = []
    forbidden_mutations: list[tuple[int, str | None, str | None]] = []

    def audited_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(traced_statements.append)

        def authorizer(
            action: int,
            arg1: str | None,
            arg2: str | None,
            _database: str | None,
            _trigger: str | None,
        ) -> int:
            if action in {sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}:
                forbidden_mutations.append((action, arg1, arg2))
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorizer)
        return connection

    monkeypatch.setattr(retrospective_module.sqlite3, "connect", audited_connect)

    annotation = _judicial_annotation()
    appended = journal.append(annotation)
    assert appended == annotation
    assert annotation.learned_at == TODAY
    assert annotation.recorded_at == TODAY
    assert annotation.valid_time_range.start == T0
    assert annotation.valid_time_range.end == TODAY
    assert "司法冻结查封裁定" in annotation.semantic_overlay
    assert "关联离岸空壳公司" in annotation.semantic_overlay

    historical_target = T0 + timedelta(days=100)
    lens = BiTemporalEpistemicLens(observations, journal=journal)
    historical_view = lens.query_historical_slice(
        PARTNER_ENTITY_ID,
        historical_target,
        as_of_cutoff=historical_target,
    )
    current_view = lens.query_historical_slice(
        PARTNER_ENTITY_ID,
        historical_target,
        as_of_cutoff=None,
    )

    assert historical_view.active_annotations == []
    assert current_view.active_annotations == [annotation]
    assert historical_view.observation_count > 0
    assert [item.object_id for item in historical_view.historical_observations] == [
        item.object_id for item in current_view.historical_observations
    ]

    after = _physical_observation_hashes(db_path, connect=real_connect)
    assert after == before
    assert len(after) == 18_000
    assert journal.count() == 1
    assert len(journal.visible_annotations(PARTNER_ENTITY_ID, historical_target)) == 1

    assert forbidden_mutations == []
    normalized_trace = [
        " ".join(statement.upper().split()) for statement in traced_statements
    ]
    assert not any(
        statement.startswith(("UPDATE ", "DELETE ")) for statement in normalized_trace
    )
    annotation_inserts = [
        statement
        for statement in normalized_trace
        if statement.startswith("INSERT INTO RETROSPECTIVE_ANNOTATIONS")
    ]
    assert len(annotation_inserts) == 1
    assert not any(
        "OBJECT_REVISIONS" in statement
        and statement.startswith(("INSERT ", "UPDATE ", "DELETE "))
        for statement in normalized_trace
    )


def _five_level_dependency_network() -> tuple[list[DependencyEdge], set[str]]:
    root = PARTNER_ENTITY_ID
    edges: list[DependencyEdge] = []

    level_1 = {f"l1_direct_consumer_{index:02d}" for index in range(10)}
    for node in sorted(level_1):
        edges.append(
            DependencyEdge(
                upstream_node_id=root,
                dependent_node_id=node,
            )
        )

    level_2: list[str] = []
    for parent_index, parent in enumerate(sorted(level_1)):
        for child_index in range(20):
            child = f"l2_risk_model_{parent_index:02d}_{child_index:02d}"
            level_2.append(child)
            edges.append(
                DependencyEdge(
                    upstream_node_id=parent,
                    dependent_node_id=child,
                )
            )

    level_3: list[str] = []
    for parent_index, parent in enumerate(level_2):
        for child_index in range(5):
            child = f"l3_decision_projection_{parent_index:03d}_{child_index}"
            level_3.append(child)
            edges.append(
                DependencyEdge(
                    upstream_node_id=parent,
                    dependent_node_id=child,
                )
            )

    level_4: list[str] = []
    for parent_index, parent in enumerate(level_3):
        for child_index in range(5):
            child = f"l4_portfolio_projection_{parent_index:04d}_{child_index}"
            level_4.append(child)
            edges.append(
                DependencyEdge(
                    upstream_node_id=parent,
                    dependent_node_id=child,
                )
            )

    for parent_index, parent in enumerate(level_4):
        edges.append(
            DependencyEdge(
                upstream_node_id=parent,
                dependent_node_id=f"l5_long_horizon_simulation_{parent_index:04d}",
            )
        )

    # 10 + 200 + 1,000 + 5,000 + 5,000 = 11,210 dependency edges.
    assert len(edges) == 11_210
    assert len(level_2) == 200
    assert len(level_3) == 1_000
    assert len(level_4) == 5_000
    return edges, level_1


def test_single_hop_isolator_marks_exactly_ten_of_11210_edges_stale() -> None:
    dependencies, expected_direct_consumers = _five_level_dependency_network()
    isolator = SingleHopCascadeIsolator(dependencies)

    result = isolator.invalidate_direct_consumers(
        PARTNER_ENTITY_ID,
        reason_annotation_id=ANNOTATION_ID,
    )

    assert result.stale_count == 10
    assert {item.node_id for item in result.stale_nodes} == expected_direct_consumers
    assert all(item.is_stale is True for item in result.stale_nodes)
    assert all(
        item.reason_annotation_id == ANNOTATION_ID for item in result.stale_nodes
    )
    assert result.traversal_depth == 1
    assert result.visited_edge_count == 10
    assert result.llm_recompute_requests == 0
    assert not any(item.node_id.startswith("l2_") for item in result.stale_nodes)
    assert not any(item.node_id.startswith("l3_") for item in result.stale_nodes)
    assert not any(item.node_id.startswith("l4_") for item in result.stale_nodes)
    assert not any(item.node_id.startswith("l5_") for item in result.stale_nodes)


def test_annotation_journal_is_idempotent_but_rejects_id_reuse(tmp_path: Path) -> None:
    journal = RetrospectiveAnnotationJournal(
        tmp_path / "annotation_idempotency.sqlite3"
    )
    annotation = _judicial_annotation()

    assert journal.append(annotation) == annotation
    assert journal.append(annotation) == annotation
    assert journal.count() == 1

    conflicting = annotation.model_copy(
        update={"semantic_overlay": "司法裁定内容被恶意替换"}
    )
    with pytest.raises(AnnotationConflictError, match="different content"):
        journal.append(conflicting)
    assert journal.count() == 1
    assert journal.get(ANNOTATION_ID) == annotation


def test_annotation_rejects_backdating_and_naive_time() -> None:
    with pytest.raises(ValidationError, match="must not extend beyond learned_at"):
        RetrospectiveAnnotation(
            annotation_id="rta_backdated",
            target_entity_id=PARTNER_ENTITY_ID,
            semantic_overlay="司法事实尚未获知时不得倒写解释图层",
            target_time_start=T0,
            target_time_end=TODAY,
            learned_at=TODAY - timedelta(seconds=1),
            source_statement_ref="judicial-order://not-yet-learned",
        )

    with pytest.raises(ValidationError, match="must be timezone-aware"):
        RetrospectiveAnnotation(
            annotation_id="rta_naive",
            target_entity_id=PARTNER_ENTITY_ID,
            semantic_overlay="无时区时间不得进入双时间账本",
            target_time_start=datetime(2024, 9, 17),  # noqa: DTZ001
            target_time_end=TODAY,
            learned_at=TODAY,
            source_statement_ref="judicial-order://timezone-invalid",
        )


def test_lens_excludes_overlay_outside_entity_or_valid_time() -> None:
    annotation = _judicial_annotation()
    lens = BiTemporalEpistemicLens(annotations=[annotation])

    before_valid_period = lens.query_historical_slice(
        PARTNER_ENTITY_ID,
        T0 - timedelta(seconds=1),
    )
    unrelated_entity = lens.query_historical_slice(
        "entity_unrelated_institutional_counterparty",
        T0 + timedelta(days=100),
    )

    assert before_valid_period.active_annotations == []
    assert unrelated_entity.active_annotations == []
