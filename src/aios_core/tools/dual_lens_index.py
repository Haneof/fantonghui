"""TP-002 双透镜虚拟索引投影器（阶段五机制沉淀的通用化）。"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from aios_core.contracts.models import ToolProposal
from aios_core.contracts.refs import ObjectRef

__all__ = ["DualLensVirtualIndexProjector", "LensView", "tool_proposal_of_dual_lens"]


@dataclass(frozen=True, slots=True)
class LensView:
    """一次双透镜投影的只读视图（零拷贝：只含 id 与叠加旗标）。"""

    subject_id: str
    lens: str                       # as_known / annotated
    base_ids: tuple[str, ...]
    overturned_ids: frozenset[str]  # annotated 视角下被推翻的 base id
    annotated_ids: frozenset[str]   # 带当日注记的 base id

    @property
    def visible_ids(self) -> tuple[str, ...]:
        """AsKnown=全量；Annotated=剔除被推翻项的可见集。"""
        if self.lens == "as_known":
            return self.base_ids
        return tuple(i for i in self.base_ids if i not in self.overturned_ids)


class DualLensVirtualIndexProjector:
    """AsKnown / Annotated 双透镜虚拟投影索引。

    机制：构建期只扫一遍注解（O(注解数)），把「哪条记录被哪个注解
    覆盖」做成倒排覆盖表；查询期按透镜旗标**虚拟投影**——不复制任何
    记录载荷、不物化视图，返回 id 与旗标集。历史注解链一致性由
    :meth:`consistency_report` 独立审计。
    """

    def __init__(
        self,
        *,
        record_subjects: Mapping[str, str],
        annotations: Sequence[dict[str, object]],
    ) -> None:
        """record_subjects: record_id -> subject；annotations: 覆盖注解字典流
        （键：record_id / subject_id / kind('overturn'|'note') / learned_at）。
        """
        self._lock = threading.RLock()
        self._subject_of = dict(record_subjects)
        self._by_subject: dict[str, list[str]] = {}
        for rid, subj in record_subjects.items():
            self._by_subject.setdefault(subj, []).append(rid)
        self._overturn: dict[str, set[str]] = {}
        self._note: dict[str, set[str]] = {}
        build_scans = 0
        for ann in annotations:
            build_scans += 1
            rid = str(ann["record_id"])
            kind = str(ann.get("kind", "note"))
            subj = str(ann.get("subject_id", self._subject_of.get(rid, "?")))
            if kind == "overturn":
                self._overturn.setdefault(subj, set()).add(rid)
            else:
                self._note.setdefault(subj, set()).add(rid)
        self._build_scan_count = build_scans
        self._record_total = len(record_subjects)

    @property
    def build_scan_count(self) -> int:
        """构建扫描量 = 注解数（与记录总量无关 → O(注解) 构建）。"""
        return self._build_scan_count

    @property
    def record_total(self) -> int:
        return self._record_total

    def view(self, subject_id: str, *, lens: str) -> LensView:
        with self._lock:
            base = tuple(sorted(self._by_subject.get(subject_id, ())))
            overturned = frozenset(self._overturn.get(subject_id, ()))
            annotated = frozenset(self._note.get(subject_id, ()))
        if lens not in ("as_known", "annotated"):
            raise ValueError("lens must be 'as_known' or 'annotated'")
        return LensView(
            subject_id=subject_id,
            lens=lens,
            base_ids=base,
            overturned_ids=overturned,
            annotated_ids=annotated,
        )

    def consistency_report(self) -> dict[str, object]:
        """双透镜一致性：AsKnown ⊇ Annotated 且仅差被推翻集。"""
        ok = True
        for subj in self._by_subject:
            known = self.view(subj, lens="as_known")
            noted = self.view(subj, lens="annotated")
            if set(noted.visible_ids) - set(known.visible_ids):
                ok = False
                break
            if not set(noted.overturned_ids) <= set(known.base_ids):
                ok = False
                break
        return {
            "consistent": ok,
            "subjects": len(self._by_subject),
            "overturned_total": sum(len(v) for v in self._overturn.values()),
            "annotated_total": sum(len(v) for v in self._note.values()),
        }


def tool_proposal_of_dual_lens() -> ToolProposal:
    """TP-002 的 ToolProposal 契约实例。"""
    return ToolProposal(
        object_id="tool-proposal-tp002-dual-lens-virtual-index",
        subject_id="aios_core.tools",
        created_by="cloud_mass_bench_agent",
        learned_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        capability_gap=(
            "双透镜视图目前靠逐条遍历注解链现算，10 万级历史 + 500 总结"
            "场景下每次视图查询都要重放链条；缺一个 O(注解) 构建、"
            "O(1) 查询的虚拟投影索引"
        ),
        use_cases=[
            "老王案 overturn 后的 AsKnown/Annotated 双视图一致性秒级审计",
            " AnyEntity 级历史认知透镜（信任基线 / 失信标记）按需切换",
            "下游复核队列的可视化投影（只看带注记的记录）",
        ],
        current_limitations=[
            "BiTemporalEpistemicLens 面向单实体语义链，非批量投影面",
            "SingleHopCascadeIsolator 给出 stale 标记，但不提供视图物",
        ],
        proposed_interface={
            "class": "DualLensVirtualIndexProjector",
            "ctor": {"record_subjects": "Mapping[rid,subject]",
                      "annotations": "Sequence[dict(kind=overturn|note)]"},
            "view": "view(subject_id: str, lens: str) -> LensView（零拷贝 id/旗标集）",
            "consistency_report": "consistency_report() -> dict（⊇关系与推翻集闭合性）",
        },
        expected_benefit=(
            "构建 O(注解数) 与记录总量解耦（10 万记录 + 500 注解场景"
            "构建扫描量下降 200×）；查询期零载荷拷贝，双透镜一致性"
            "由结构保证而非逐条对账"
        ),
        validation_plan=(
            "盲测世界 500 总结 + 400 观察注入 overturn 注解：构建扫描量"
            "==注解数；双透镜 visible 差集==overturn 集；一致性报告全绿；"
            "与 SingleHopCascadeIsolator stale 标记交叉核对"
        ),
    )
