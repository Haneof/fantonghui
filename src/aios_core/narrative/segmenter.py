"""叙事分段管线：切割、标注、合并、归档。

宪法第八章：将用户生命线按主题切割为有意义的段落，
支持跨维度叙事主线追踪，为人生相变(LifeChapter)提供底层数据。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aios_core.contracts.enums import NarrativeSegmentStatus, ObjectType
from aios_core.contracts.models import NarrativeSegment
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent, utc_now


class NarrativeSegmenter:
    """叙事分段器：负责切割、合并、归档叙事段落。"""

    def __init__(self, subject_id: str):
        self._subject_id = subject_id
        self._segments: dict[str, NarrativeSegment] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"ns-{self._subject_id}-{self._counter:06d}"

    @property
    def segments(self) -> dict[str, NarrativeSegment]:
        return dict(self._segments)

    def open_segment(
        self,
        title: str,
        *,
        description: str = "",
        dimension_refs: list[ObjectRef] | None = None,
        theme_tags: list[str] | None = None,
        segment_time: TemporalExtent | None = None,
        now: datetime | None = None,
    ) -> NarrativeSegment:
        """开启一个新的叙事分段。"""
        ts = now or utc_now()
        seg_id = self._next_id()
        seg = NarrativeSegment(
            object_id=seg_id,
            subject_id=self._subject_id,
            learned_at=ts,
            recorded_at=ts,
            created_by="narrative_segmenter",
            title=title,
            description=description,
            dimension_refs=dimension_refs or [],
            theme_tags=theme_tags or [],
            segment_time=segment_time or TemporalExtent.unknown_time(),
            segment_status=NarrativeSegmentStatus.OPEN,
        )
        self._segments[seg_id] = seg
        return seg

    def attach_event(
        self, segment_id: str, event_ref: ObjectRef
    ) -> NarrativeSegment:
        """向叙事分段挂载关键事件。"""
        seg = self._segments[segment_id]
        if seg.segment_status != NarrativeSegmentStatus.OPEN:
            raise ValueError(f"只能向 OPEN 状态的分段挂载事件，当前状态: {seg.segment_status}")
        updated_refs = list(seg.key_event_refs) + [event_ref]
        new_seg = seg.model_copy(update={"key_event_refs": updated_refs, "revision": seg.revision + 1})
        self._segments[segment_id] = new_seg
        return new_seg

    def attach_claim(
        self, segment_id: str, claim_ref: ObjectRef
    ) -> NarrativeSegment:
        """向叙事分段挂载关键主张。"""
        seg = self._segments[segment_id]
        if seg.segment_status != NarrativeSegmentStatus.OPEN:
            raise ValueError(f"只能向 OPEN 状态的分段挂载主张，当前状态: {seg.segment_status}")
        updated_refs = list(seg.key_claim_refs) + [claim_ref]
        new_seg = seg.model_copy(update={"key_claim_refs": updated_refs, "revision": seg.revision + 1})
        self._segments[segment_id] = new_seg
        return new_seg

    def seal_segment(
        self, segment_id: str, *, reason: str = "自然结束"
    ) -> NarrativeSegment:
        """封存归档叙事分段。"""
        seg = self._segments[segment_id]
        if seg.segment_status != NarrativeSegmentStatus.OPEN:
            raise ValueError(f"只能封存 OPEN 状态的分段，当前状态: {seg.segment_status}")
        if not seg.title.strip():
            raise ValueError("封存的叙事分段必须有明确标题")
        new_seg = seg.model_copy(update={
            "segment_status": NarrativeSegmentStatus.SEALED,
            "revision": seg.revision + 1,
            "metadata": {**seg.metadata, "seal_reason": reason},
        })
        new_seg.validate_narrative_segment()
        self._segments[segment_id] = new_seg
        return new_seg

    def merge_segments(
        self, source_ids: list[str], target_title: str, *, now: datetime | None = None
    ) -> NarrativeSegment:
        """合并多个分段为一个新分段。"""
        if len(source_ids) < 2:
            raise ValueError("合并至少需要2个分段")
        ts = now or utc_now()
        sources = [self._segments[sid] for sid in source_ids]
        
        # 收集所有子段的引用
        all_event_refs = []
        all_claim_refs = []
        all_dim_refs = []
        all_participant_refs = []
        all_tags = set()
        for s in sources:
            all_event_refs.extend(s.key_event_refs)
            all_claim_refs.extend(s.key_claim_refs)
            all_dim_refs.extend(s.dimension_refs)
            all_participant_refs.extend(s.participant_refs)
            all_tags.update(s.theme_tags)

        merged = self.open_segment(
            title=target_title,
            dimension_refs=all_dim_refs,
            theme_tags=sorted(all_tags),
            now=ts,
        )
        # 更新合并后的引用
        merged = merged.model_copy(update={
            "key_event_refs": all_event_refs,
            "key_claim_refs": all_claim_refs,
            "participant_refs": all_participant_refs,
        })
        self._segments[merged.object_id] = merged

        # 标记源分段为 MERGED
        merged_ref = ObjectRef(object_id=merged.object_id, revision=merged.revision)
        for sid in source_ids:
            s = self._segments[sid]
            self._segments[sid] = s.model_copy(update={
                "segment_status": NarrativeSegmentStatus.MERGED,
                "merged_into_ref": merged_ref,
                "revision": s.revision + 1,
            })

        return merged

    def get_open_segments(self) -> list[NarrativeSegment]:
        """获取所有处于 OPEN 状态的分段。"""
        return [
            seg for seg in self._segments.values()
            if seg.segment_status == NarrativeSegmentStatus.OPEN
        ]

    def get_segments_by_dimension(self, dimension_id: str) -> list[NarrativeSegment]:
        """按维度查询相关的叙事分段。"""
        return [
            seg for seg in self._segments.values()
            if any(ref.object_id == dimension_id for ref in seg.dimension_refs)
        ]

    def get_segments_by_theme(self, theme: str) -> list[NarrativeSegment]:
        """按主题标签查询叙事分段。"""
        return [
            seg for seg in self._segments.values()
            if theme in seg.theme_tags
        ]
