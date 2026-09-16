import pytest
from datetime import datetime, timezone
from aios_core.contracts.enums import NarrativeSegmentStatus
from aios_core.contracts.models import NarrativeSegment
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent, utc_now
from aios_core.narrative.segmenter import NarrativeSegmenter


@pytest.fixture
def segmenter():
    return NarrativeSegmenter(subject_id="u123")


def test_open_segment(segmenter):
    seg = segmenter.open_segment(title="Initial Segment")
    assert seg.title == "Initial Segment"
    assert seg.segment_status == NarrativeSegmentStatus.OPEN
    assert seg.subject_id == "u123"
    assert seg.object_id.startswith("ns-u123-")
    assert len(segmenter.segments) == 1
    assert segmenter.segments[seg.object_id] == seg


def test_attach_event_and_claim(segmenter):
    seg = segmenter.open_segment(title="My Segment")
    event_ref = ObjectRef(object_id="ev-1", revision=1)
    claim_ref = ObjectRef(object_id="cl-1", revision=1)

    seg2 = segmenter.attach_event(seg.object_id, event_ref)
    assert len(seg2.key_event_refs) == 1
    assert seg2.key_event_refs[0].object_id == "ev-1"
    assert seg2.revision == seg.revision + 1

    seg3 = segmenter.attach_claim(seg.object_id, claim_ref)
    assert len(seg3.key_claim_refs) == 1
    assert seg3.key_claim_refs[0].object_id == "cl-1"
    assert seg3.revision == seg2.revision + 1


def test_seal_segment(segmenter):
    seg = segmenter.open_segment(title="To be sealed")
    sealed_seg = segmenter.seal_segment(seg.object_id, reason="finished")
    assert sealed_seg.segment_status == NarrativeSegmentStatus.SEALED
    assert sealed_seg.metadata["seal_reason"] == "finished"

    with pytest.raises(ValueError, match="只能封存 OPEN 状态的分段"):
        segmenter.seal_segment(seg.object_id)


def test_seal_segment_validation(segmenter):
    seg = segmenter.open_segment(title=" ")
    with pytest.raises(ValueError, match="封存的叙事分段必须有明确标题"):
        segmenter.seal_segment(seg.object_id)


def test_merge_segments(segmenter):
    s1 = segmenter.open_segment(title="s1", theme_tags=["tag1"])
    s2 = segmenter.open_segment(title="s2", theme_tags=["tag2"])
    
    event_ref = ObjectRef(object_id="ev-1", revision=1)
    s1 = segmenter.attach_event(s1.object_id, event_ref)
    
    merged = segmenter.merge_segments([s1.object_id, s2.object_id], target_title="merged")
    
    assert merged.title == "merged"
    assert merged.segment_status == NarrativeSegmentStatus.OPEN
    assert "tag1" in merged.theme_tags
    assert "tag2" in merged.theme_tags
    assert len(merged.key_event_refs) == 1
    
    s1_updated = segmenter.segments[s1.object_id]
    assert s1_updated.segment_status == NarrativeSegmentStatus.MERGED
    assert s1_updated.merged_into_ref is not None
    assert s1_updated.merged_into_ref.object_id == merged.object_id
    assert s1_updated.merged_into_ref.revision == merged.revision


def test_merge_segments_requires_two(segmenter):
    s1 = segmenter.open_segment(title="s1")
    with pytest.raises(ValueError, match="合并至少需要2个分段"):
        segmenter.merge_segments([s1.object_id], "merged")


def test_get_open_segments(segmenter):
    s1 = segmenter.open_segment(title="s1")
    s2 = segmenter.open_segment(title="s2")
    segmenter.seal_segment(s1.object_id)
    
    open_segs = segmenter.get_open_segments()
    assert len(open_segs) == 1
    assert open_segs[0].object_id == s2.object_id


def test_get_segments_by_dimension(segmenter):
    dim_ref = ObjectRef(object_id="dim-1", revision=1)
    s1 = segmenter.open_segment(title="s1", dimension_refs=[dim_ref])
    s2 = segmenter.open_segment(title="s2")
    
    dim_segs = segmenter.get_segments_by_dimension("dim-1")
    assert len(dim_segs) == 1
    assert dim_segs[0].object_id == s1.object_id


def test_get_segments_by_theme(segmenter):
    s1 = segmenter.open_segment(title="s1", theme_tags=["work", "life"])
    s2 = segmenter.open_segment(title="s2", theme_tags=["life"])
    s3 = segmenter.open_segment(title="s3", theme_tags=["study"])
    
    life_segs = segmenter.get_segments_by_theme("life")
    assert len(life_segs) == 2
    
    study_segs = segmenter.get_segments_by_theme("study")
    assert len(study_segs) == 1
