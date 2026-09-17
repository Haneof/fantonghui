"""Model-facing world capability adapters must preserve World/Search truth semantics."""

from datetime import datetime, timezone

from aios_core.contracts.enums import SourceClass
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.runtime.capabilities import CapabilityCall, CapabilityRegistry
from aios_core.runtime.world_capabilities import WorldCapabilityBus
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc


def _world(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    occurred = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    learned = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    obs = Observation(
        object_id="obs_contract_memory",
        subject_id="user_1",
        revision=1,
        source_kind="user_chat",
        modality="text",
        value="用户今天才告诉 AI：2024 年和老王签过一份合同。",
        occurred=TemporalExtent.point(occurred),
        learned_at=learned,
        recorded_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
        created_by="test",
    )
    store.commit(
        [obs],
        OperationRequest(
            operation_id="op_runtime_world",
            operation_name="test.ingest",
            expected_world_revision=0,
            reason="runtime world capability fixture",
            idempotency_key="idem_runtime_world",
            source_class=SourceClass.USER,
        ),
    )
    return store


def test_search_world_keeps_knowledge_time_separate_from_event_time(tmp_path):
    bus = WorldCapabilityBus(_world(tmp_path))

    before = bus.search_world(
        "合同",
        view="AS_KNOWN",
        as_of="2025-01-01T00:00:00+00:00",
    )
    assert before == []

    after = bus.search_world(
        "合同",
        view="AS_KNOWN",
        as_of="2026-02-01T00:00:00+00:00",
    )
    assert [row["object_id"] for row in after] == ["obs_contract_memory"]


def test_timeline_filters_occurrence_but_as_of_filters_knowledge(tmp_path):
    bus = WorldCapabilityBus(_world(tmp_path))

    hidden = bus.search_timeline(
        "2023-12-01T00:00:00+00:00",
        "2024-12-31T23:59:59+00:00",
        subject_id="user_1",
        as_of="2025-12-31T23:59:59+00:00",
    )
    assert hidden == []

    visible = bus.search_timeline(
        "2023-12-01T00:00:00+00:00",
        "2024-12-31T23:59:59+00:00",
        subject_id="user_1",
        as_of="2026-02-01T00:00:00+00:00",
    )
    assert [row["object_id"] for row in visible] == ["obs_contract_memory"]


def test_registry_exposes_read_capabilities_as_tools(tmp_path):
    bus = WorldCapabilityBus(_world(tmp_path))
    registry = CapabilityRegistry()
    bus.register_read_capabilities(registry)

    names = {item["name"] for item in registry.catalog()}
    assert {
        "search_world",
        "search_timeline",
        "focus_entity",
        "retrieve_original_observation",
        "inspect_evidence",
        "compare_claims",
    }.issubset(names)

    result = registry.invoke(
        CapabilityCall(
            name="retrieve_original_observation",
            arguments={"object_id": "obs_contract_memory"},
        )
    )
    assert result.ok is True
    assert result.data["value"].endswith("签过一份合同。")
