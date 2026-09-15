"""M1-012R 实体拓扑超链接四级网络穿透检索器。

架构定位（R3-ARCH C15「世界检索与导航」）：

1. **可重建的查询侧索引设施**，不是事实源。世界对象与版本只存在于
   ``aios_core.storage``；本模块只维护稳定 ID 的指针邻接表，可随时由
   上游按 world_revision 水位重建。
2. **只存指针，绝不复制载荷**（V3 宪法 §18 反冗余拷贝）。索引中的每个
   值都是稳定全局 ID；内容本体必须经 Core 读取服务按需加载。
3. **O(1) 哈希精确归一，彻底废除单表模糊扫描**。别名经 Unicode 归一后
   进入哈希倒排索引，检索成本与库体积无关；查询层禁止直接 SQL（本包
   级约束），也不引入任何 ``sqlite3`` 依赖。
4. **四级因果穿透链**：``Entity -> EventAnchor -> EvidenceSet ->
   Observation``。depth 参数按节点层级计数（1=实体档案, 2=+事件锚点,
   3=+证据集合, 4=+原始观测），depth=4 即全链穿透。
5. **同名不等于同实体**（V3 宪法 §36）。同一别名映射到多个实体时记为
   歧义冲突（ambiguity），解析必须显式失败并给出全部候选，绝不允许静默
   合并或静默改绑。
6. 本层不做任何语义判断（V3 §77：触发/查询只负责定位，不产生认知结论）。

并发约定：读写在同一把可重入锁内串行；遍历是纯读快照语义，注册与遍历
可安全并发，单次遍历不会被并发注册撕裂。
"""

from __future__ import annotations

import threading
import time
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from aios_core.contracts.enums import ErrorCode

__all__ = [
    "AliasAmbiguousError",
    "EntityNotRegisteredError",
    "EntityHyperlinkGraphTraverser",
    "HyperlinkQueryError",
    "HyperlinkTraversalResult",
    "InvalidTraversalDepthError",
    "MalformedIdentifierError",
    "MAX_TRAVERSAL_DEPTH",
    "normalize_alias",
]

#: 因果穿透链的层级数（Entity/EventAnchor/EvidenceSet/Observation）。
MAX_TRAVERSAL_DEPTH = 4

_LEVEL_NAMES: tuple[str, ...] = (
    "entity",
    "event_anchor",
    "evidence_set",
    "observation",
)


def normalize_alias(value: str) -> str:
    """别名归一化：NFKC 折叠 + 去首尾空白 + 内部空白压缩 + casefold。

    归一化是"拓扑归一"的全部语义：它只做字符层面的等价折叠，不做任何
    语义联想（同义词、尊称推理属于大模型的实体解析服务，不在本层）。
    归一后为空串的输入视为非法别名。
    """
    if not isinstance(value, str):
        raise MalformedIdentifierError("alias must be a string", field="alias")
    folded = unicodedata.normalize("NFKC", value).strip()
    folded = " ".join(folded.split()).casefold()
    if not folded:
        raise MalformedIdentifierError(
            "alias is empty after normalization", field="alias"
        )
    return folded


def _require_identifier(value: str, field: str) -> str:
    """稳定 ID 校验：非空字符串、无首尾空白、不含控制空白。

    注意：本层不强制 ID 前缀策略（``ent_``/``evt_``/``evs_``/``obs_``
    等前缀属于 contracts.ids 与存储层的管辖），以避免查询索引发明新的
    事实标准。字符串本身的合法性必须在此把守。
    """
    if not isinstance(value, str) or not value.strip():
        raise MalformedIdentifierError(
            f"{field} must be a non-empty string", field=field
        )
    if value != value.strip() or any(ch.isspace() for ch in value):
        raise MalformedIdentifierError(
            f"{field} must not contain whitespace", field=field
        )
    return value


class HyperlinkQueryError(Exception):
    """携带协议级错误码的查询异常（机器可分支，行为对齐 ErrorResponse）。"""

    code: ErrorCode = ErrorCode.INVALID_ARGUMENT

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, object] = context


class MalformedIdentifierError(HyperlinkQueryError):
    code = ErrorCode.INVALID_ARGUMENT


class InvalidTraversalDepthError(HyperlinkQueryError):
    code = ErrorCode.INVALID_ARGUMENT


class EntityNotRegisteredError(HyperlinkQueryError):
    code = ErrorCode.NOT_FOUND


class AliasAmbiguousError(HyperlinkQueryError):
    """别名歧义：同一别名声称属于多个实体（V3 §36 禁止静默合并）。"""

    code = ErrorCode.INVALID_ARGUMENT


class HyperlinkTraversalResult(BaseModel):
    """四级穿透检索结果（只含指针与计量，不含任何载荷内容）。

    ``evidence_sets`` 是任务书必填字段之外的补充层级：四级因果链的第三级
    必须可见，否则上层无法继续下钻到 Observation（V3 §90 双向可穿透）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_entity_id: StrictStr
    matched_aliases: tuple[StrictStr, ...] = Field(default=())
    anchors: tuple[StrictStr, ...] = Field(default=())
    evidence_sets: tuple[StrictStr, ...] = Field(default=())
    observations: tuple[StrictStr, ...] = Field(default=())
    traversal_depth: StrictInt = Field(ge=1, le=MAX_TRAVERSAL_DEPTH)
    traversal_ms: float = Field(ge=0.0)
    matched_level: Literal["entity_id", "alias"] = "entity_id"


class EntityHyperlinkGraphTraverser:
    """实体拓扑超链接图：O(1) 别名归一 + 分层指针邻接表 + 逐级 BFS。

    索引与库规模无关的三个保证：
    - 别名解析是哈希精确命中，不是扫描；
    - 逐级展开只做 ``set`` 并集（C 速度），每条边至多被触碰一次；
    - 输出恒为排序后的元组，天然满足幂等重放（同输入同输出）。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # L0: 实体档案层 —— 别名倒排 + 实体正排
        self._alias_to_entity: dict[str, str] = {}
        self._entity_aliases: dict[str, set[str]] = {}
        self._alias_conflicts: dict[str, set[str]] = {}
        # L1..L3: 分层指针邻接表
        self._entity_anchors: dict[str, set[str]] = {}
        self._anchor_evidence: dict[str, set[str]] = {}
        self._evidence_observations: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # 索引注册（additive & 幂等：重复注册 = 集合并集，绝不产生重复边）
    # ------------------------------------------------------------------

    def register_entity_link(
        self,
        entity_id: str,
        aliases: Sequence[str],
        anchor_ids: Sequence[str],
    ) -> None:
        """登记实体档案：别名集合（自动归一）与其直接参与的事件锚点。"""
        _require_identifier(entity_id, "entity_id")
        normalized = sorted({normalize_alias(a) for a in aliases})
        anchors = [
            _require_identifier(a, f"anchor_ids[{i}]")
            for i, a in enumerate(anchor_ids)
        ]
        with self._lock:
            self._entity_aliases.setdefault(entity_id, set()).update(normalized)
            for alias in normalized:
                owner = self._alias_to_entity.get(alias)
                if owner is None:
                    self._alias_to_entity[alias] = entity_id
                elif owner != entity_id:
                    # 同名不同实体：只记冲突，绝不静默改绑或合并（V3 §36）。
                    self._alias_conflicts.setdefault(alias, {owner}).add(entity_id)
            self._entity_anchors.setdefault(entity_id, set()).update(anchors)

    def register_anchor_links(
        self, anchor_id: str, evidence_set_ids: Sequence[str]
    ) -> None:
        """登记事件锚点 → 证据集合的指针边（L1→L2）。"""
        _require_identifier(anchor_id, "anchor_id")
        evidence = [
            _require_identifier(e, f"evidence_set_ids[{i}]")
            for i, e in enumerate(evidence_set_ids)
        ]
        with self._lock:
            self._anchor_evidence.setdefault(anchor_id, set()).update(evidence)

    def register_evidence_links(
        self, evidence_set_id: str, observation_ids: Sequence[str]
    ) -> None:
        """登记证据集合 → 原始观测的指针边（L2→L3）。"""
        _require_identifier(evidence_set_id, "evidence_set_id")
        observations = [
            _require_identifier(o, f"observation_ids[{i}]")
            for i, o in enumerate(observation_ids)
        ]
        with self._lock:
            self._evidence_observations.setdefault(
                evidence_set_id, set()
            ).update(observations)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def resolve_alias(self, alias: str) -> str:
        """别名 → 主实体档案。歧义与未注册都必须显式失败。"""
        key = normalize_alias(alias)
        with self._lock:
            if key in self._alias_conflicts:
                candidates = sorted(self._alias_conflicts[key])
                raise AliasAmbiguousError(
                    "alias maps to multiple entities; explicit disambiguation"
                    " is required (V3 constitution §36)",
                    alias=key,
                    candidate_entity_ids=candidates,
                )
            entity_id = self._alias_to_entity.get(key)
        if entity_id is None:
            raise EntityNotRegisteredError(
                "alias is not linked to any entity", alias=key
            )
        return entity_id

    def traverse_entity_network(
        self, entity_id: str, depth: int = MAX_TRAVERSAL_DEPTH
    ) -> HyperlinkTraversalResult:
        """从实体档案出发，沿因果链向上逐级穿透。

        ``entity_id`` 接受稳定实体 ID，或已归一链接到该实体的任意别名
        （命中别名时 ``matched_level="alias"``）。``depth`` 按节点层级计数：
        1=实体档案；2=+事件锚点；3=+证据集合；4=+原始观测（全链）。
        """
        started = time.perf_counter()
        if isinstance(depth, bool) or not isinstance(depth, int):
            raise InvalidTraversalDepthError(
                "depth must be an integer", depth=repr(depth)
            )
        if not 1 <= depth <= MAX_TRAVERSAL_DEPTH:
            raise InvalidTraversalDepthError(
                f"depth must be within 1..{MAX_TRAVERSAL_DEPTH}", depth=depth
            )
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise MalformedIdentifierError(
                "entity_id must be a non-empty string", field="entity_id"
            )

        root = entity_id
        matched_level: Literal["entity_id", "alias"] = "entity_id"
        with self._lock:
            if entity_id in self._entity_aliases:
                # 直达路径：稳定 ID 精确命中（O(1)）。
                root = entity_id
            elif self._is_alias(entity_id):
                # 别名归一路径：NFKC/casefold/空白折叠后哈希命中（O(1)）。
                root = self.resolve_alias(entity_id)
                matched_level = "alias"
            else:
                raise EntityNotRegisteredError(
                    "entity id is not registered in the hyperlink index",
                    entity_id=entity_id,
                )
            aliases = sorted(self._entity_aliases.get(root, set()))
            anchors: tuple[str, ...] = ()
            evidence: tuple[str, ...] = ()
            observations: tuple[str, ...] = ()
            if depth >= 2:
                anchors = self._frozenset_union(
                    self._entity_anchors, root
                )
            if depth >= 3:
                evidence = self._union_over(
                    anchors, self._anchor_evidence
                )
            if depth >= MAX_TRAVERSAL_DEPTH:
                observations = self._union_over(
                    evidence, self._evidence_observations
                )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return HyperlinkTraversalResult(
            root_entity_id=root,
            matched_aliases=tuple(aliases),
            anchors=anchors,
            evidence_sets=evidence,
            observations=observations,
            traversal_depth=depth,
            traversal_ms=round(elapsed_ms, 6),
            matched_level=matched_level,
        )

    # ------------------------------------------------------------------
    # 运维观测
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """索引规模概览（供运维面板与水位重建决策，非语义判断）。"""
        with self._lock:
            return {
                "entities": len(self._entity_aliases),
                "aliases": len(self._alias_to_entity),
                "alias_conflicts": len(self._alias_conflicts),
                "entity_anchor_edges": sum(
                    len(v) for v in self._entity_anchors.values()
                ),
                "anchor_evidence_edges": sum(
                    len(v) for v in self._anchor_evidence.values()
                ),
                "evidence_observation_edges": sum(
                    len(v) for v in self._evidence_observations.values()
                ),
            }

    # ------------------------------------------------------------------

    def _is_alias(self, value: str) -> bool:
        key = normalize_alias(value)
        return key in self._alias_to_entity or key in self._alias_conflicts

    @staticmethod
    def _frozenset_union(
        table: dict[str, set[str]], key: str
    ) -> tuple[str, ...]:
        return tuple(sorted(table.get(key, ())))

    @staticmethod
    def _union_over(
        level_ids: Iterable[str], next_table: dict[str, set[str]]
    ) -> tuple[str, ...]:
        if not level_ids:
            return ()
        merged: set[str] = set()
        for level_id in level_ids:
            merged.update(next_table.get(level_id, ()))
        return tuple(sorted(merged))
