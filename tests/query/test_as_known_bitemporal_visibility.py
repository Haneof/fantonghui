"""AS_KNOWN 必须按 learned_at 限制知识可见性，不能发生时间穿越。"""

from datetime import datetime, timezone

from aios_core.contracts.enums import SourceClass
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.query.search import WorldSearchIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc


def test_as_known_hides_past_event_that_was_learned_later(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")

    occurred = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    learned = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    recorded = datetime(2026, 1, 1, 12, 1, tzinfo=UTC)

    obs = Observation(
        object_id="obs_late_learned_contract",
        subject_id="user_1",
        revision=1,
        source_kind="user_chat",
        modality="text",
        value="用户今天才告诉 AI：2024 年和老王签过一份合同。",
        occurred=TemporalExtent.point(occurred),
        learned_at=learned,
        recorded_at=recorded,
        created_by="test",
    )
    store.commit(
        [obs],
        OperationRequest(
            operation_id="op_late_learned_contract",
            operation_name="test.ingest",
            expected_world_revision=0,
            reason="freeze bitemporal AS_KNOWN contract",
            idempotency_key="idem_late_learned_contract",
            source_class=SourceClass.USER,
        ),
    )

    index = WorldSearchIndex(tmp_path / "world.db", store=store)

    before_learning = index.co_search(
        ["合同"],
        view="AS_KNOWN",
        as_of=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert [hit.object_id for hit in before_learning.hits] == []

    after_learning = index.co_search(
        ["合同"],
        view="AS_KNOWN",
        as_of=datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
    )
    assert [hit.object_id for hit in after_learning.hits] == ["obs_late_learned_contract"]

    # ANNOTATED/current view still returns the historical event normally.
    current = index.co_search(["合同"], view="ANNOTATED")
    assert [hit.object_id for hit in current.hits] == ["obs_late_learned_contract"]
