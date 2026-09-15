"""M1-012R 实体拓扑超链接四级网络穿透检索器。

废除旧系统在单表中执行 ``LIKE '%xxx%'`` 的低效模糊遍历：本模块把
``Entity -> EventAnchor -> EvidenceSet -> Observation`` 四级因果链
预先索引为超链接图谱，检索全程只走哈希命中，不再对任何文本列做模糊扫描。

核心能力：

1. 别名自动归一（Alias Normalization）
   任意别名（如 "老王" / "王叔" / "隔壁老王"）经 ``register_entity_link``
   登记后进入归一索引，检索时以 O(1) 哈希命中主实体档案（root entity），
   保证 100% 归一到同一个 ``entity_id``。

2. 四级因果穿透（Depth-Budgeted BFS）
   一跳 = 一条超链接，深度预算 ``depth`` 控制穿透的跳数：

   =====  ============================================================
   hop    可达节点
   =====  ============================================================
   0      根实体（别名归一后的主实体档案）
   1      实体参与的事件锚点（EventAnchor）
   2      锚点挂载的证据组（EvidenceSet）＋共享锚点的对等实体（网络横向穿透）
   3      证据组内的原始观察（Observation）＋对等实体自身的锚点
   4      对等实体锚点的证据组 ＋ 二度对等实体
   =====  ============================================================

   因此 ``depth=4`` 既完整覆盖四级因果链
   ``Entity -> EventAnchor -> EvidenceSet -> Observation``（hop 1-3），
   又完成一轮超链接网络横向穿透（对等实体的锚点与证据组）；
   ``depth > 4`` 时 BFS 继续沿超链接交替展开，直至预算耗尽。
   已访问节点全局去重，环与共享节点不会导致重复或死循环。
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AliasConflictError",
    "EntityHyperlinkGraphTraverser",
    "HyperlinkTraversalResult",
    "HyperlinkTraversalError",
    "UnknownEntityError",
]


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------


class HyperlinkTraversalError(ValueError):
    """超链接图谱登记 / 检索错误的基类。"""


class UnknownEntityError(HyperlinkTraversalError, LookupError):
    """检索入口既不是已登记的实体 ID，也不是任何已登记别名。"""


class AliasConflictError(HyperlinkTraversalError):
    """同一别名被登记到两个不同的主实体档案，拒绝跨实体别名冲突。"""


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


class HyperlinkTraversalResult(BaseModel):
    """一次超链接穿透检索的完整拓扑结果。

    字段覆盖四级因果链（Entity -> EventAnchor -> EvidenceSet ->
    Observation）外加网络横向穿透发现的对等实体。所有列表保持
    确定性的 BFS 发现顺序。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_entity_id: str = Field(min_length=1)
    matched_aliases: list[str] = Field(default_factory=list)
    anchors: list[dict[str, Any]] = Field(default_factory=list)
    evidence_sets: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    linked_entity_ids: list[str] = Field(default_factory=list)
    traversal_depth: int = Field(ge=0)
    traversal_ms: float = Field(ge=0.0)


# ---------------------------------------------------------------------------
# 内部图记录（预索引节点，全部哈希访问）
# ---------------------------------------------------------------------------


class _EntityRecord:
    __slots__ = ("entity_id", "aliases", "_alias_keys", "anchor_ids")

    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        # 主实体档案的完整归一别名集：首元素恒为规范 entity_id。
        self.aliases: list[str] = [entity_id]
        self._alias_keys: set[str] = {entity_id.casefold()}
        self.anchor_ids: list[str] = []


class _AnchorRecord:
    __slots__ = ("anchor_id", "title", "evidence_set_ids", "participant_entity_ids")

    def __init__(self, anchor_id: str, title: str) -> None:
        self.anchor_id = anchor_id
        self.title = title
        self.evidence_set_ids: list[str] = []
        self.participant_entity_ids: list[str] = []


class _EvidenceSetRecord:
    __slots__ = ("evidence_set_id", "purpose", "observation_ids")

    def __init__(self, evidence_set_id: str, purpose: str) -> None:
        self.evidence_set_id = evidence_set_id
        self.purpose = purpose
        self.observation_ids: list[str] = []


class _ObservationRecord:
    __slots__ = ("observation_id", "payload")

    def __init__(self, observation_id: str, payload: dict[str, Any]) -> None:
        self.observation_id = observation_id
        self.payload = payload


def _require_id(value: Any, field: str) -> str:
    """校验并归一化一个超链接 ID / 名称：去首尾空白，拒绝空白与非字符串。"""

    if not isinstance(value, str):
        raise TypeError(f"{field} must be str, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} must not be blank")
    return stripped


def _alias_key(name: str) -> str:
    """别名归一键：去首尾空白 + casefold，保证 '老王'/'王叔' 类别名精确命中。"""

    return name.casefold()


# ---------------------------------------------------------------------------
# 核心遍历器
# ---------------------------------------------------------------------------


class EntityHyperlinkGraphTraverser:
    """实体超链接图谱的登记与穿透检索器。

    所有登记在写入时即完成索引构建（别名归一索引 + 四级邻接表），
    ``traverse_entity_network`` 只执行纯哈希 BFS，从而在深度 4 的穿透
    检索中稳定满足 25ms 预算，与语料总规模无关。
    """

    def __init__(self) -> None:
        self._entities: dict[str, _EntityRecord] = {}
        self._anchors: dict[str, _AnchorRecord] = {}
        self._evidence_sets: dict[str, _EvidenceSetRecord] = {}
        self._observations: dict[str, _ObservationRecord] = {}
        # 归一索引：alias_key -> 主实体 entity_id（含实体 ID 自身）。
        self._alias_index: dict[str, str] = {}

    # -- 登记 API -----------------------------------------------------------

    def register_entity_link(
        self,
        entity_id: str,
        aliases: Sequence[str] = (),
        anchor_ids: Sequence[str] = (),
    ) -> str:
        """登记实体主档案、归一别名与参与的事件锚点超链接。

        重复登记同一主实体会幂等合并别名与锚点链接；若任一别名已被
        另一个主实体档案占用，则抛出 :class:`AliasConflictError`，
        保证别名 100% 归一到唯一主实体。

        返回归一后的主实体 ``entity_id``。
        """

        eid = _require_id(entity_id, "entity_id")
        alias_names = [_require_id(name, "aliases item") for name in aliases]
        anchor_links = [_require_id(aid, "anchor_ids item") for aid in anchor_ids]

        eid_key = _alias_key(eid)
        owner = self._alias_index.get(eid_key)
        if owner is not None and owner != eid:
            raise AliasConflictError(
                f"entity_id {eid!r} is already registered as an alias of "
                f"entity {owner!r}; refusing to create a second primary profile"
            )

        for name in alias_names:
            key = _alias_key(name)
            existing = self._alias_index.get(key)
            if existing is not None and existing != eid:
                raise AliasConflictError(
                    f"alias {name!r} is already linked to entity {existing!r}; "
                    f"refusing cross-entity alias collision with {eid!r}"
                )

        record = self._entities.get(eid)
        if record is None:
            record = _EntityRecord(eid)
            self._entities[eid] = record

        self._alias_index[eid_key] = eid
        for name in alias_names:
            key = _alias_key(name)
            if key not in record._alias_keys:
                record._alias_keys.add(key)
                record.aliases.append(name)
            self._alias_index[key] = eid

        for aid in anchor_links:
            if aid not in record.anchor_ids:
                record.anchor_ids.append(aid)

        return eid

    def register_anchor(
        self,
        anchor_id: str,
        *,
        title: str = "",
        evidence_set_ids: Sequence[str] = (),
        participant_entity_ids: Sequence[str] = (),
    ) -> None:
        """登记事件锚点（EventAnchor 层）及其证据组 / 参与实体超链接。"""

        aid = _require_id(anchor_id, "anchor_id")
        record = self._anchors.get(aid)
        if record is None:
            record = _AnchorRecord(aid, title.strip())
            self._anchors[aid] = record
        elif title.strip():
            record.title = title.strip()

        for esid in evidence_set_ids:
            esid = _require_id(esid, "evidence_set_ids item")
            if esid not in record.evidence_set_ids:
                record.evidence_set_ids.append(esid)
        for pid in participant_entity_ids:
            pid = _require_id(pid, "participant_entity_ids item")
            if pid not in record.participant_entity_ids:
                record.participant_entity_ids.append(pid)

    def register_evidence_set(
        self,
        evidence_set_id: str,
        *,
        purpose: str = "",
        observation_ids: Sequence[str] = (),
    ) -> None:
        """登记证据组（EvidenceSet 层）及其原始观察超链接。"""

        esid = _require_id(evidence_set_id, "evidence_set_id")
        record = self._evidence_sets.get(esid)
        if record is None:
            record = _EvidenceSetRecord(esid, purpose.strip())
            self._evidence_sets[esid] = record
        elif purpose.strip():
            record.purpose = purpose.strip()

        for oid in observation_ids:
            oid = _require_id(oid, "observation_ids item")
            if oid not in record.observation_ids:
                record.observation_ids.append(oid)

    def register_observation(
        self,
        observation_id: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """登记原始观察（Observation 层），``payload`` 承载原始言论等事实。"""

        oid = _require_id(observation_id, "observation_id")
        record = self._observations.get(oid)
        if record is None:
            self._observations[oid] = _ObservationRecord(oid, dict(payload or {}))
        elif payload is not None:
            record.payload.update(payload)

    # -- 检索 API -----------------------------------------------------------

    def traverse_entity_network(
        self,
        entity_id: str,
        depth: int = 4,
    ) -> HyperlinkTraversalResult:
        """从实体（或其任意别名）出发执行深度预算内的超链接穿透检索。

        ``depth`` 为超链接跳数预算：1=锚点层，2=+证据组+对等实体，
        3=+原始观察+对等实体的锚点，4=完整四级因果链+对等实体的证据组
        +二度对等实体（详见模块文档的 hop 表）。
        """

        if isinstance(depth, bool) or not isinstance(depth, int):
            raise TypeError(f"depth must be int, got {type(depth).__name__}")
        if depth < 0:
            raise ValueError("depth must be >= 0")

        started_at = time.perf_counter()

        root_id = self._resolve_entity_id(entity_id)
        root_record = self._entities[root_id]

        anchors_out: list[dict[str, Any]] = []
        evidence_out: list[dict[str, Any]] = []
        observations_out: list[dict[str, Any]] = []
        linked_entities: list[str] = []

        seen_entities: set[str] = {root_id}
        seen_anchors: set[str] = set()
        seen_evidence_sets: set[str] = set()
        seen_observations: set[str] = set()

        # BFS 队列元素：(节点类型, 节点ID, 已用跳数, 父节点ID)。
        queue: deque[tuple[str, str, int, str | None]] = deque()
        queue.append(("entity", root_id, 0, None))

        while queue:
            kind, node_id, hop, parent_id = queue.popleft()
            if hop >= depth:
                continue
            next_hop = hop + 1

            if kind == "entity":
                record = self._entities[node_id]
                for aid in record.anchor_ids:
                    if aid in seen_anchors:
                        continue
                    anchor = self._anchors.get(aid)
                    if anchor is None:
                        continue
                    seen_anchors.add(aid)
                    anchors_out.append(
                        {
                            "anchor_id": aid,
                            "title": anchor.title,
                            "depth": next_hop,
                            "via_entity_id": node_id,
                            "evidence_set_ids": list(anchor.evidence_set_ids),
                            "participant_entity_ids": list(
                                anchor.participant_entity_ids
                            ),
                        }
                    )
                    queue.append(("anchor", aid, next_hop, node_id))

            elif kind == "anchor":
                record = self._anchors[node_id]
                for esid in record.evidence_set_ids:
                    if esid in seen_evidence_sets:
                        continue
                    evidence_set = self._evidence_sets.get(esid)
                    if evidence_set is None:
                        continue
                    seen_evidence_sets.add(esid)
                    evidence_out.append(
                        {
                            "evidence_set_id": esid,
                            "purpose": evidence_set.purpose,
                            "depth": next_hop,
                            "anchor_id": node_id,
                            "observation_ids": list(evidence_set.observation_ids),
                        }
                    )
                    queue.append(("evidence_set", esid, next_hop, node_id))
                for pid in record.participant_entity_ids:
                    if pid in seen_entities or pid not in self._entities:
                        continue
                    seen_entities.add(pid)
                    linked_entities.append(pid)
                    if next_hop < depth:
                        queue.append(("entity", pid, next_hop, node_id))

            elif kind == "evidence_set":
                record = self._evidence_sets[node_id]
                for oid in record.observation_ids:
                    if oid in seen_observations:
                        continue
                    observation = self._observations.get(oid)
                    if observation is None:
                        continue
                    seen_observations.add(oid)
                    observations_out.append(
                        {
                            "observation_id": oid,
                            "depth": next_hop,
                            "evidence_set_id": node_id,
                            "anchor_id": parent_id,
                            "payload": dict(observation.payload),
                        }
                    )

        traversal_ms = (time.perf_counter() - started_at) * 1000.0

        return HyperlinkTraversalResult(
            root_entity_id=root_id,
            matched_aliases=list(root_record.aliases),
            anchors=anchors_out,
            evidence_sets=evidence_out,
            observations=observations_out,
            linked_entity_ids=linked_entities,
            traversal_depth=depth,
            traversal_ms=traversal_ms,
        )

    # -- 辅助 ---------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """返回图谱各层节点数量，用于审计与容量观测。"""

        return {
            "entities": len(self._entities),
            "anchors": len(self._anchors),
            "evidence_sets": len(self._evidence_sets),
            "observations": len(self._observations),
            "alias_index_entries": len(self._alias_index),
        }

    def _resolve_entity_id(self, entity_id: str) -> str:
        """把实体 ID 或任意别名经归一索引解析为主实体档案 ID（O(1)）。"""

        if not isinstance(entity_id, str):
            raise TypeError(
                f"entity_id must be str, got {type(entity_id).__name__}"
            )
        key = _alias_key(entity_id.strip())
        if not key:
            raise ValueError("entity_id must not be blank")
        resolved = self._alias_index.get(key)
        if resolved is None:
            raise UnknownEntityError(
                f"entity {entity_id!r} is not registered in the hyperlink "
                "graph: neither a known entity_id nor a registered alias"
            )
        return resolved
