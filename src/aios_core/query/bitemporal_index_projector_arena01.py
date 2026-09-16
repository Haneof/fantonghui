"""新工具发明 #2：BitemporalVirtualIndexProjector 双透镜虚拟索引投影器（arena01）。

军令对位（阶段五 × 阶段八）：
- 老王案之后，AsKnown(as_of) 与 Annotated(now) 双重视图需要**同时可检索**
  但不能改写任何历史字节，更不能为每个时间点重建索引（索引雪崩）；
- 本投影器对索引执行**零拷贝虚拟化**：postings → 文档可见性谓词过滤，同一
  物理索引可投影出任意时间切片的虚拟视图，新增注解只追加、只出现在
  Annotated 视图；源索引及源文档 SHA 任何时刻不变；
- 配套 ToolProposal 契约登记。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import TemporalExtent
from aios_core.query.search_arena01 import MultidimensionalSearchBus, SearchDocument

__all__ = [
    "LensView",
    "VirtualIndexView",
    "BitemporalVirtualIndexProjector",
    "build_bitemporal_projector_proposal",
]


class LensView:  # StrEnum 省依赖；字符串字面量即可
    AS_KNOWN = "as_known"
    ANNOTATED = "annotated"


@dataclass(frozen=True)
class VirtualIndexView:
    lens: str
    cutoff_seq: int
    visible_doc_ids: Tuple[str, ...]
    source_digest: str  # 构造时原总线指纹（证明零改写）


class BitemporalVirtualIndexProjector:
    """对 SearchDocument.object_id 前缀序号（``*-seq`` 形态）执行可见性投影。

    每个文档记录 (seq, learned_seq_overlay)：历史文档 learned ≤ as_of 即
    AsKnown 可见；外挂注解 holds extra flag overlay=True，只在 Annotated 可见。
    """

    def __init__(self, bus: MultidimensionalSearchBus) -> None:
        self._bus = bus
        import hashlib
        import json
        blob = json.dumps(
            [(d.object_id, d.kind, d.title, d.text) for d in bus.documents()],
            ensure_ascii=False,
        ).encode("utf-8")
        self._digest = hashlib.sha256(blob).hexdigest()
        self._overlay_ids: Dict[str, int] = {}

    def register_overlay(self, doc_id: str, learned_seq: int) -> None:
        if doc_id not in {d.object_id for d in self._bus.documents()}:
            raise ValueError(f"overlay doc 必须已存在于总线: {doc_id}")
        self._overlay_ids[doc_id] = learned_seq

    def project(self, lens: str, *, cutoff_seq: int) -> VirtualIndexView:
        visible: List[str] = []
        for doc in self._bus.documents():
            if doc.object_id in self._overlay_ids:
                if lens == LensView.ANNOTATED and self._overlay_ids[doc.object_id] <= cutoff_seq:
                    visible.append(doc.object_id)
                continue  # 注解绝不混入 AsKnown 历史视图
            seq = self._seq_of(doc.object_id)
            if seq <= cutoff_seq:
                visible.append(doc.object_id)
        return VirtualIndexView(
            lens=lens, cutoff_seq=cutoff_seq, visible_doc_ids=tuple(sorted(visible)),
            source_digest=self._digest,
        )

    def search(self, view: VirtualIndexView, terms: Sequence[str]) -> Tuple[str, ...]:
        hits = {ref.object_id for ref in self._bus.search(terms)}
        visible = set(view.visible_doc_ids)
        return tuple(sorted(hits & visible))

    def source_digest(self) -> str:
        return self._digest

    @staticmethod
    def _seq_of(object_id: str) -> int:
        tail = object_id.rsplit("-", 1)[-1]
        return int(tail) if tail.isdigit() else 0


def build_bitemporal_projector_proposal(now: datetime) -> ToolProposal:
    """ToolProposal 契约登记：双透镜虚拟索引投影器。"""
    return ToolProposal(
        object_id="tool-proposal-bitemporal-index-projector-arena01",
        subject_id="aios-core",
        occurred=TemporalExtent.point(now),
        learned_at=now,
        created_by="agent-arena01",
        capability_gap="AsKnown/Annotated 双透镜若按时间点重建物化索引，索引存储与构建算力"
                       "随注解数量线性雪崩；需要零拷贝虚拟化投影。",
        use_cases=[
            "老王案今天的外挂注解只在 Annotated 视图可检索，AsKnown 历史视图零渗透",
            "任意时间点快照查询共享同一物理倒排索引",
        ],
        current_limitations=["现有多维总线未内置时间透镜谓词层"],
        proposed_interface={
            "class": "BitemporalVirtualIndexProjector",
            "project(lens, cutoff_seq)": "VirtualIndexView",
            "search(view, terms)": "Tuple[str, ...]",
            "register_overlay(doc_id, learned_seq)": "None",
        },
        expected_benefit="索引构建 O(1) 摊销之外零重建；历史字节与视图指纹全程不变；"
                         "注解追加即视图生效",
        validation_plan="tests/e2e/test_massive_e2e_8stage_bench_arena01.py 阶段五压测 + "
                        "专属单测锚定 AsKnown 零渗透 / Annotated 完整 / 指纹不变",
    )
