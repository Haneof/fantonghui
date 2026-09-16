"""双透镜虚拟索引投影器 (DualLensVirtualIndexProjector) —— ToolProposal TLP-C02 纯代码实现。

宪法出处：第 84~86 条（单次看盘 1500 Token、禁止盲目灌入全量长上下文）、
第 90 条（图谱拓扑穿透）、第 96 条（关键词是入口不是真相）。

解决的问题（能力缺口）：

    驾驶舱每次组装都要回答同一个问题——"过去这几年，和这家伙发生过什么"。现有实现
    必须从 C02 账本 / 倒排投影里把原始对象逐条取出、逐条渲染，才能拼进看板。当对象
    数达到百万级时，这会带来两笔无法摊销的固定开销：

    1) I/O 层重复物化：同一条 Observation 在"看板组装"与"检索复核"里被各取一次，
       带动对象表随机读放大；
    2) 双时间视图割裂：AS_KNOWN（还原当时认知）与 ANNOTATED（叠加今日图层）各自走
       一遍完整物化路径，而两者的事实基础字节完全一致——属重复劳动。

机制：

    * **一次解析、双透镜复用**：事实入账时只解析一次规范 JSON 并计算 SHA-256；之后
      AS_KNOWN 与 ANNOTATED 两种投影共享同一份事实字节；
    * **先指针、后物化**：投影第一跳只产出 ``(object_id, revision, sha256)`` 三元组
      （虚拟索引），长载荷只在被显式请求时才物化——不物化的对象保持指针形态，看板
      不随检索半径线性膨胀；
    * **双时间一致性锚定**：注解挂载与 AS_OF 视图直接委托
      :class:`aios_core.world.epistemic_world_lens.EpistemicWorldLens`，由生产引擎
      强制"历史不可变 + 单跳隔离 + 认知只前向"；本投影器绝不触碰事实字节。

纯确定性、零大模型调用；投影层只读。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Iterable, Sequence

from aios_core.contracts.time import as_utc
from aios_core.world.epistemic_world_lens import (
    EpistemicWorldLens,
    RetrospectiveAnnotation,
    coerce_world_object,
    encode_fact_payload,
)

__all__ = [
    "DualLensVirtualIndexProjector",
    "LensProjection",
    "MaterializedFact",
    "PointerForm",
]

#: 指针形态输出上限（object_id + @revision + 短摘要），防止长载荷混入虚拟索引。
_POINTER_MAX_LEN: Final[int] = 96


@dataclass(frozen=True)
class PointerForm:
    """虚拟索引形态：不携带任何长载荷，只够定位与按需物化。"""

    object_id: str
    revision: int
    sha256: str

    @property
    def size_chars(self) -> int:
        return len(self.object_id) + len(self.sha256) + 8

    def as_dict(self) -> dict[str, Any]:
        return {"object_id": self.object_id, "revision": self.revision, "sha256": self.sha256}


@dataclass(frozen=True)
class MaterializedFact:
    """被显式物化的完整事实（长载荷只在被点名时出现）。"""

    reference: PointerForm
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"reference": self.reference.as_dict(), "payload": self.payload}


@dataclass(frozen=True)
class LensProjection:
    """一次投影的结果：指针集 + 物化集 + 双时间注解视图。

    ``naive_chars``（全部物化所需字符）与 ``pointer_chars``（虚拟索引所需字符）之比
    即"指针化收益"；``materialized`` 只含被点名物化的对象。
    """

    entity_id: str
    target_time: datetime
    as_of_cutoff: datetime | None
    view_mode: str
    fact_pointers: tuple[PointerForm, ...]
    materialized: tuple[MaterializedFact, ...]
    overlay_labels: tuple[str, ...]
    naive_chars: int
    pointer_chars: int

    @property
    def virtualization_ratio(self) -> float:
        """指针化后字符占用 / 全量物化字符占用（越小越省）。"""
        return self.pointer_chars / max(1, self.naive_chars)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "target_time": self.target_time.isoformat(),
            "as_of_cutoff": self.as_of_cutoff.isoformat() if self.as_of_cutoff else None,
            "view_mode": self.view_mode,
            "pointer_count": len(self.fact_pointers),
            "materialized_count": len(self.materialized),
            "overlay_labels": list(self.overlay_labels),
            "virtualization_ratio": round(self.virtualization_ratio, 4),
        }


class DualLensVirtualIndexProjector:
    """双时间透镜虚拟索引投影器：一次解析、双透镜复用、字节级只读、零大模型调用。"""

    def __init__(
        self,
        *,
        budget_tokens: int = 1500,
        charset: bytes | None = None,
    ) -> None:
        self._budget_tokens = budget_tokens
        self._lens = EpistemicWorldLens(require_anchored_target=True)
        # (object_id, revision) -> (注册时刻的规范事实字节, MaterializedFact)
        self._facts: dict[tuple[str, int], MaterializedFact] = {}
        self._llm_calls = 0
        self._materializations = 0
        self._projections = 0

    # -- 审计只读 ------------------------------------------------------

    @property
    def llm_calls(self) -> int:
        return self._llm_calls

    @property
    def facts_registered(self) -> int:
        return len(self._facts)

    @property
    def materializations(self) -> int:
        return self._materializations

    @property
    def budget_tokens(self) -> int:
        return self._budget_tokens

    @property
    def lens(self) -> EpistemicWorldLens:
        return self._lens

    # -- 入账 ----------------------------------------------------------

    def register_fact(self, fact: Any, *, entity_ids: str | Iterable[str] | None = None) -> str:
        """登记一条历史事实：解析一次、算 SHA-256、登记双时间透镜锚点。返回 SHA-256。"""
        obj = coerce_world_object(fact)
        payload, _encoded, digest = encode_fact_payload(obj)
        self._lens.register_fact(obj, entity_ids=entity_ids)
        key = (obj.object_id, obj.revision)
        pointer = PointerForm(object_id=obj.object_id, revision=obj.revision, sha256=digest)
        self._facts[key] = MaterializedFact(reference=pointer, payload=payload)
        return digest

    def attach_overlay(
        self,
        annotation: RetrospectiveAnnotation,
    ) -> str:
        """挂载今日注解（委托生产引擎：只追加、单跳、历史字节不可变）。返回注解 SHA-256。"""
        receipt = self._lens.attach_annotation(annotation)
        return receipt.annotation_sha256

    def materialize(self, object_id: str, *, revision: int | None = None) -> dict[str, Any] | None:
        """按点名的 (object_id, revision) 物化长载荷；未登记返回 None（指针形态不残废）。"""
        keys = [
            key for key in self._facts
            if key[0] == object_id and (revision is None or key[1] == revision)
        ]
        if not keys:
            return None
        key = keys[-1]
        fact = self._facts[key]
        self._materializations += 1
        return fact.payload

    # -- 投影 ----------------------------------------------------------

    def project(
        self,
        *,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: datetime | None = None,
        materialize_refs: Sequence[str] = (),
        slice_mode: str = "cumulative",
    ) -> LensProjection:
        """构建一次双透镜投影：先指针、后按需物化，永不改写事实字节。

        ``slice_mode`` 默认 ``cumulative``——驾驶舱"过去几年与这位伙伴发生过什么"
        的语义是"截至此刻的一生事实"，故委托生产引擎按 start-before-target 选取；
        需要"那一刻正在发生什么"时传 ``instant``。
        """
        target = as_utc(target_time, "target_time")
        cutoff = as_utc(as_of_cutoff, "as_of_cutoff") if as_of_cutoff is not None else None

        # 双时间事实选择委托生产引擎（保证 AS_KNOWN 语义与企业基线一致）。
        typed_view = self._lens.query_slice_view(
            entity_id, target, cutoff, slice_mode=slice_mode
        )
        visible_facts: dict[tuple[str, int], MaterializedFact] = {}
        for fact_view in typed_view.facts:
            key = (fact_view.object_id, fact_view.revision)
            registered = self._facts.get(key)
            if registered is not None:
                visible_facts[key] = registered

        requested = set(materialize_refs)
        pointers: list[PointerForm] = []
        materialized: list[MaterializedFact] = []
        naive_chars = 0
        for fact in visible_facts.values():
            ref = fact.reference
            pointers.append(ref)
            payload_json = json.dumps(fact.payload, ensure_ascii=False, sort_keys=True)
            naive_chars += len(payload_json)
            if ref.object_id in requested:
                materialized.append(fact)
                self._materializations += 1

        pointer_chars = sum(p.size_chars for p in pointers) + sum(
            len(json.dumps(f.payload, ensure_ascii=False, sort_keys=True)) for f in materialized
        )
        view_mode = typed_view.view_mode
        overlay_labels = typed_view.overlay_labels
        self._projections += 1
        return LensProjection(
            entity_id=entity_id,
            target_time=target,
            as_of_cutoff=cutoff,
            view_mode=view_mode,
            fact_pointers=tuple(pointers),
            materialized=tuple(materialized),
            overlay_labels=overlay_labels,
            naive_chars=naive_chars,
            pointer_chars=pointer_chars,
        )

    @property
    def projections(self) -> int:
        return self._projections
