"""双透镜虚拟索引投影器（TLP-DLV-002）：基底哈希、增量投影、集合一致。"""

from __future__ import annotations

import pytest

from aios_core.tools.dual_lens_index_projector import (
    ANNOTATED,
    AS_KNOWN,
    DualLensVirtualIndexProjector,
)


def _projector(facts: int = 400) -> DualLensVirtualIndexProjector:
    projector = DualLensVirtualIndexProjector()
    for index in range(facts):
        projector.index_fact(
            f"obs_{index:04d}",
            f"合伙出资与银行流水第 {index} 笔，涉及对赌协议与借款",
            learned_us=1_700_000_000_000_000 + index,
        )
    return projector


def test_indexing_is_idempotent_and_content_locked() -> None:
    projector = _projector(10)
    assert projector.index_fact("obs_0001", "合伙出资与银行流水第 1 笔，涉及对赌协议与借款", learned_us=1) == 0
    with pytest.raises(ValueError):
        projector.index_fact("obs_0001", "被改写过的内容", learned_us=1)


def test_annotation_only_writes_incremental_postings() -> None:
    projector = _projector()
    frozen = projector.freeze_base()
    written = projector.attach_annotation(
        "anno_1",
        target_object_id="obs_0007",
        statement="事后证实该笔资金涉嫌合同诈骗",
        slot="meaning",
        annotated_us=1_800_000_000_000_000,
    )
    metrics = projector.metrics()
    assert written > 0
    assert metrics.overlay_postings_written == written
    assert metrics.saved_ratio > 0.9
    assert projector.base_index_sha256 == frozen
    assert projector.base_compatible_with_frozen() is True


def test_annotation_replay_is_idempotent_and_conflict_refused() -> None:
    projector = _projector(20)
    projector.attach_annotation(
        "anno_1", target_object_id="obs_0003", statement="诈骗款", slot="meaning", annotated_us=9
    )
    assert (
        projector.attach_annotation(
            "anno_1", target_object_id="obs_0003", statement="诈骗款", slot="meaning", annotated_us=9
        )
        == 0
    )
    with pytest.raises(ValueError):
        projector.attach_annotation(
            "anno_1",
            target_object_id="obs_0004",
            statement="另一段话",
            slot="meaning",
            annotated_us=9,
        )


def test_two_lenses_return_the_same_fact_set() -> None:
    projector = _projector()
    projector.freeze_base()
    projector.attach_annotation(
        "anno_1",
        target_object_id="obs_0007",
        statement="事后证实该笔资金涉嫌合同诈骗，需要按诈骗口径重估",
        slot="meaning",
        annotated_us=1_800_000_000_000_000,
    )
    keywords = ["合伙", "出资"]
    as_known = projector.query(keywords, lens=AS_KNOWN, limit=100)
    annotated = projector.query(keywords, lens=ANNOTATED, limit=100)
    # 两条透镜的**事实集合**必须一致（注解只加语义权重，不增删历史事实）
    assert set(as_known.object_ids) == set(annotated.object_ids)
    assert projector.assert_lens_consistency(keywords, limit=100) is True
    marked = [hit for hit in annotated.hits if hit.annotation_ids]
    assert marked and marked[0].object_id == "obs_0007"
    assert marked[0].invalidated_by == ("anno_1",)


def test_as_of_cutoff_hides_later_facts() -> None:
    projector = _projector(50)
    projector.freeze_base()
    cutoff = 1_700_000_000_000_010
    page = projector.query(["合伙"], lens=AS_KNOWN, as_of_us=cutoff, limit=100)
    assert page.hits
    assert all(hit.learned_us <= cutoff for hit in page.hits)


def test_metrics_arithmetic() -> None:
    projector = _projector(30)
    projector.attach_annotation(
        "anno_1", target_object_id="obs_0002", statement="诈骗款重估", slot="meaning", annotated_us=5
    )
    metrics = projector.metrics()
    assert metrics.saved_postings == metrics.naive_rebuild_postings - metrics.overlay_postings_written
    assert 0.0 <= metrics.saved_ratio <= 1.0
    assert len(metrics.base_index_sha256) == 64
