"""M1-012R 实体拓扑超链接网络穿透检索器（C06 拓扑查询与超链接检索层）。

工单：``governance/dispatches/TASK_DISPATCH_AGENT_4_M1_012R.md``
门禁：黄金底库 ``docs/fusion_dossier/02_*`` —— 10 万节点下深度 4 穿透检索 <= 25ms

设计原则（逐条对齐宪法 V3 与老大五大铁律）
--------------------------------------------------------------------------
1. **废除单表 LIKE '%xxx%' 模糊扫表**：所有边一律来自**结构化引用**
   （``EventAnchor.participant_refs`` / ``*.evidence_set_refs`` / ``EvidenceSet.member_refs``）。
   查询期只做 O(可达子图) 的索引跳转，绝不扫全表、绝不对文本做模糊匹配。
2. **四级因果穿透**：Entity -> EventAnchor -> EvidenceSet -> Observation。
3. **别名归一**：NFKC 归一 + 大小写折叠 + 空白折叠 + 零宽字符剥离；
   一个别名映射到多个实体时**显式抛出冲突**，绝不静默合并
   （宪法第三十六条：文字相同不代表实体相同；第三十五条：身份未知不影响使用）。
4. **只读与历史不可变（老大铁律 #2 / 宪法第九十三条）**：
   本模块**严禁** UPDATE / DELETE / 任何世界写入；只在内存维护**可重建的派生索引**。
   索引属于可重建的查询设施（架构规划 §6.4），不是世界本体；
   世界本体永远只有一个写入者 ``SQLiteWorldStore.commit()``。
5. **预算与不静默丢弃**：单次查询的边展开量有硬上限（``max_link_expansions``），
   查询耗时因此**与全图规模无关**——这是"10 万节点深 4 <= 25ms"的结构性保证；
   锚点层可续页（``continuation``），证据层/观测层有界物化；
   任何一层被预算裁剪时 ``coverage.truncated=True`` 且如实上报
   ``expansion_exhausted`` / ``fanout_capped_nodes`` 与各层 ``*_discovered`` 计数，
   调用方永远知道"还有多少没返回、计数是精确值还是下界"（宪法第六十四条、R1-06）。
6. **知识截止与索引水位**：派生索引必须能声明自己建于哪个世界版本之上；
   相对世界落后时由调用方显式发现（``STALE_INDEX``），不得把旧索引伪装成最新事实
   （架构规划 §6.4、工作台规格 §4 的 ``STALE_INDEX`` 语义）。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.errors import AIOSProtocolError

__all__ = [
    "MAX_DEPTH",
    "AmbiguousAlias",
    "AnchorNode",
    "EntityHyperlinkGraphTraverser",
    "EntityNode",
    "EvidenceSetNode",
    "HyperlinkLevel",
    "HyperlinkTraversalError",
    "HyperlinkTraversalResult",
    "IndexBuildReport",
    "IndexWatermark",
    "ObservationNode",
    "TraversalContinuation",
    "TraversalCoverage",
    "normalize_alias",
]

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 穿透图谱固定四级：Entity -> EventAnchor -> EvidenceSet -> Observation。
MAX_DEPTH: Final[int] = 4

#: 单节点默认扇出上限（超出部分不展开；命中该上限的节点会被计数上报）。
DEFAULT_MAX_FANOUT_PER_NODE: Final[int] = 64
#: 单次查询默认边的展开预算：这是"10 万节点下深度 4 穿透 <= 25ms"的**结构性保证**——
#: 查询成本只与可达子图（受本预算约束）有关，与全图规模无关。
DEFAULT_MAX_LINK_EXPANSIONS: Final[int] = 8192
#: 单页默认返回上限（分层预算，防止一次查询把端侧内存打满）。
DEFAULT_MAX_ANCHORS: Final[int] = 128
DEFAULT_MAX_EVIDENCE_SETS: Final[int] = 192
DEFAULT_MAX_OBSERVATIONS: Final[int] = 384

#: 需要从别名中剥离的零宽/不可见字符（手机端转写文本常见污染）。
_ZERO_WIDTH_RE: Final[re.Pattern[str]] = re.compile("[\u200b\u200c\u200d\ufeff\u2060]")
_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# 别名归一（宪法第三十六条：关键词是世界入口，不是世界最终真相）
# ---------------------------------------------------------------------------


def normalize_alias(raw: str) -> str:
    """把任意书写形态的别名折叠为稳定查询键（幂等）。

    规则：NFKC 归一 -> 剥离零宽字符 -> 折叠空白与首尾 -> 大小写折叠。

    只做**书写层**归一，不做任何语义推测：
    "老王" 与 "王叔" 是否同一人必须由登记时显式声明，绝不由本函数猜。
    """
    if not isinstance(raw, str):
        raise AIOSProtocolError(
            ErrorCode.INVALID_ARGUMENT,
            "alias must be a string",
            context={"reason": "alias_not_string", "value_type": type(raw).__name__},
        )
    folded = unicodedata.normalize("NFKC", raw)
    folded = _ZERO_WIDTH_RE.sub("", folded)
    folded = _WHITESPACE_RE.sub(" ", folded).strip()
    return folded.casefold()


# ---------------------------------------------------------------------------
# 契约：节点
# ---------------------------------------------------------------------------


class HyperlinkLevel(StrEnum):
    ENTITY = "entity"
    EVENT_ANCHOR = "event_anchor"
    EVIDENCE_SET = "evidence_set"
    OBSERVATION = "observation"


class EntityNode(BaseModel):
    """第一级：实体档案（别名归一的落点；身份未知不影响使用，宪法第三十五条）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    canonical_name: str | None = None
    entity_type: str | None = None
    aliases: tuple[str, ...] = ()
    depth: int = Field(default=1, ge=1, le=MAX_DEPTH)


class AnchorNode(BaseModel):
    """第二级：事件锚点（事件本身是锚点，引用而非复制，宪法第四十七条）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor_id: str = Field(min_length=1)
    title: str | None = None
    summary_text: str | None = None
    event_status: str | None = None
    occurred_at: datetime | None = None
    evidence_set_ids: tuple[str, ...] = ()
    depth: int = Field(default=2, ge=2, le=MAX_DEPTH)


class EvidenceSetNode(BaseModel):
    """第三级：证据集合（一等对象，必须可复核，宪法第四十二条）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_set_id: str = Field(min_length=1)
    purpose: str | None = None
    knowledge_cutoff: datetime | None = None
    stale: bool = False
    member_count: int = Field(default=0, ge=0)
    depth: int = Field(default=3, ge=2, le=MAX_DEPTH)


class ObservationNode(BaseModel):
    """第四级：原始观测（世界原始输入，宪法第三十三条）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str = Field(min_length=1)
    content: str = ""
    source_kind: str | None = None
    modality: str | None = None
    dimension_id: str | None = None
    occurred_at: datetime | None = None
    learned_at: datetime | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    via_evidence_set_id: str | None = None
    depth: int = Field(default=4, ge=2, le=MAX_DEPTH)


# ---------------------------------------------------------------------------
# 契约：覆盖度、冲突、续页、水位
# ---------------------------------------------------------------------------


class TraversalCoverage(BaseModel):
    """覆盖度如实上报：既报告"拿到什么"，也报告"还剩下什么"。

    计数口径（必须精确，绝不模糊）：
    - ``expansion_exhausted=False`` 时，``*_discovered`` 相对**实际展开的父层**是精确值：
      ``anchors_discovered`` 相对实体精确；``evidence_sets_discovered`` 相对本次返回的锚点精确；
      ``observations_discovered`` 相对本次返回的证据集合精确；
    - ``expansion_exhausted=True`` 时枚举被预算提前中止，``*_discovered`` 退化为**下界**，
      调用方必须据此判断"证据尚未穷尽"，绝不可当作全量结论。
    - ``fanout_capped_nodes > 0`` 表示有节点出边被扇出上限截断，此时 ``truncated``
      必定为真——宁可多报截断，不可漏报不完整。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_depth: int = Field(ge=1, le=MAX_DEPTH)
    reached_depth: int = Field(ge=1, le=MAX_DEPTH)
    anchors_discovered: int = Field(ge=0)
    anchors_returned: int = Field(ge=0)
    evidence_sets_discovered: int = Field(ge=0)
    evidence_sets_returned: int = Field(ge=0)
    observations_discovered: int = Field(ge=0)
    observations_returned: int = Field(ge=0)
    dangling_refs: int = Field(ge=0)
    truncated: bool
    expansion_exhausted: bool
    fanout_capped_nodes: int = Field(ge=0)
    index_node_total: int = Field(ge=0)
    visited_edges: int = Field(ge=0)


class AmbiguousAlias(BaseModel):
    """同一别名指向多个实体：必须显式暴露，绝不合并（宪法第三十六条）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alias: str = Field(min_length=1)
    entity_ids: tuple[str, ...] = Field(min_length=1)


class TraversalContinuation(BaseModel):
    """续页游标：**仅对锚点层分页**，且分页并集严格等于全量锚点集合。

    证据层与观测层的裁剪由每节点扇出上限与单页预算界定，属于**已声明的边界**，
    不伪装成可续取的游标（宁可少承诺，不可给一个会漏证据的假游标）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor_offset: int = Field(ge=0)
    depth: int = Field(ge=1, le=MAX_DEPTH)


class IndexWatermark(BaseModel):
    """派生索引自述：我建立在哪个世界版本之上、装了多少节点与边。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world_revision: int | None = Field(default=None, ge=0)
    built_at: datetime
    entities: int = Field(ge=0)
    anchors: int = Field(ge=0)
    evidence_sets: int = Field(ge=0)
    observations: int = Field(ge=0)
    edges: int = Field(ge=0)

    @property
    def node_total(self) -> int:
        return self.entities + self.anchors + self.evidence_sets + self.observations


class IndexBuildReport(BaseModel):
    """``build_from_store`` 的结果：如实报告跳过与悬垂，不掩盖数据质量问题。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entities_loaded: int = Field(ge=0)
    anchors_loaded: int = Field(ge=0)
    evidence_sets_loaded: int = Field(ge=0)
    observations_loaded: int = Field(ge=0)
    payloads_skipped: int = Field(ge=0)
    dangling_refs: int = Field(ge=0)
    world_revision: int = Field(ge=0)
    build_ms: float = Field(ge=0.0)


# ---------------------------------------------------------------------------
# 契约：穿透结果
# 工单强制字段 root_entity_id / matched_aliases / anchors / observations /
# traversal_depth / traversal_ms 全部保留原名与语义。
# ---------------------------------------------------------------------------


class HyperlinkTraversalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root_entity_id: str = Field(min_length=1)
    matched_aliases: list[str] = Field(default_factory=list)
    anchors: list[AnchorNode] = Field(default_factory=list)
    observations: list[ObservationNode] = Field(default_factory=list)
    traversal_depth: int = Field(ge=1, le=MAX_DEPTH)
    traversal_ms: float = Field(ge=0.0)

    # —— 生产级补充（工单契约的严格超集，便于门禁核账与调试器回放）——
    root_entity: EntityNode
    evidence_sets: list[EvidenceSetNode] = Field(default_factory=list)
    coverage: TraversalCoverage
    resolved_via: str = Field(default="entity_id", min_length=1)
    resolved_via_alias: str | None = None
    ambiguous_aliases: list[AmbiguousAlias] = Field(default_factory=list)
    index_world_revision: int | None = Field(default=None, ge=0)
    continuation: TraversalContinuation | None = None
    result_fingerprint: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# 异常（沿用 M0 统一协议错误协议）
# ---------------------------------------------------------------------------


class HyperlinkTraversalError(AIOSProtocolError):
    """本模块协议错误基类。"""


class UnknownEntityError(HyperlinkTraversalError):
    def __init__(self, key: str) -> None:
        super().__init__(
            ErrorCode.NOT_FOUND,
            "entity is unknown to the hyperlink index",
            context={"reason": "unknown_entity", "key": key},
        )


class AmbiguousEntityAliasError(HyperlinkTraversalError):
    def __init__(self, alias: str, entity_ids: Sequence[str]) -> None:
        super().__init__(
            ErrorCode.INVALID_ARGUMENT,
            "alias resolves to multiple entities; caller must disambiguate",
            context={
                "reason": "ambiguous_alias",
                "alias": alias,
                "candidate_entity_ids": sorted(entity_ids),
            },
        )


class StaleHyperlinkIndexError(HyperlinkTraversalError):
    def __init__(self, index_revision: int | None, world_revision: int) -> None:
        super().__init__(
            ErrorCode.STALE_INDEX,
            "hyperlink index is behind the current world revision",
            context={
                "reason": "stale_hyperlink_index",
                "index_world_revision": index_revision,
                "current_world_revision": world_revision,
            },
        )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _coerce_text(value: Any) -> str:
    """把 Observation.value 收敛成文本 Caption（拒存原始二进制大图，宪法第三十三条）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # 黄金底库以纳秒整数存储时间，这里做单位自适应。
        seconds = float(value)
        if seconds > 1e14:
            seconds /= 1_000_000_000.0
        elif seconds > 1e11:
            seconds /= 1_000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _extent_start(extent: Any) -> datetime | None:
    """从冻结契约的 TemporalExtent 取发生时间；未知则 None，绝不编造精确值。"""
    if not isinstance(extent, Mapping):
        return None
    if extent.get("unknown") is True:
        return None
    return _parse_time(extent.get("start"))


def _ref_ids(values: Any) -> tuple[str, ...]:
    """提取 ObjectRef 列表中的 object_id（保持给定顺序）。"""
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, Mapping)):
        return ()
    out: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            object_id = item.get("object_id")
        else:
            object_id = getattr(item, "object_id", None)
        if isinstance(object_id, str) and object_id:
            out.append(object_id)
    return tuple(out)


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({v for v in values if isinstance(v, str) and v}))


def _fingerprint(
    root_id: str,
    anchors: Sequence[AnchorNode],
    evidence_sets: Sequence[EvidenceSetNode],
    observations: Sequence[ObservationNode],
) -> str:
    """结果语义指纹（不含耗时）：用于"同一实体经不同别名进入得到同一子图"的强断言。"""
    payload = {
        "root": root_id,
        "anchors": sorted(a.anchor_id for a in anchors),
        "evidence_sets": sorted(e.evidence_set_id for e in evidence_sets),
        "observations": sorted(o.observation_id for o in observations),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 主体：实体拓扑超链接图穿透器
# ---------------------------------------------------------------------------


class EntityHyperlinkGraphTraverser:
    """内存派生索引 + 有界四级穿透。

    生命周期：``register_*`` / ``build_from_store`` 建索引 -> ``traverse_entity_network`` 只读查询。

    并发模型：写侧单写者（与 Core 的"唯一世界写入者"原则一致），读侧无锁只读；
    查询路径不修改任何索引状态，只读普通 dict/tuple 与排序缓存。
    """

    def __init__(
        self,
        *,
        max_fanout_per_node: int = DEFAULT_MAX_FANOUT_PER_NODE,
        max_link_expansions: int = DEFAULT_MAX_LINK_EXPANSIONS,
        max_anchors: int = DEFAULT_MAX_ANCHORS,
        max_evidence_sets: int = DEFAULT_MAX_EVIDENCE_SETS,
        max_observations: int = DEFAULT_MAX_OBSERVATIONS,
    ) -> None:
        for name, value in (
            ("max_fanout_per_node", max_fanout_per_node),
            ("max_link_expansions", max_link_expansions),
            ("max_anchors", max_anchors),
            ("max_evidence_sets", max_evidence_sets),
            ("max_observations", max_observations),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise AIOSProtocolError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{name} must be a positive integer",
                    context={"reason": "invalid_traversal_budget", "field": name},
                )
        self._max_fanout = max_fanout_per_node
        self._max_expansions = max_link_expansions
        self._max_anchors = max_anchors
        self._max_evidence_sets = max_evidence_sets
        self._max_observations = max_observations

        # —— 四级邻接（全部来自结构化引用，绝无 LIKE 模糊匹配）——
        self._entity_aliases: dict[str, tuple[str, ...]] = {}
        self._alias_index: dict[str, set[str]] = {}
        self._entity_anchors: dict[str, set[str]] = {}
        self._anchor_evidence: dict[str, set[str]] = {}
        self._evidence_observations: dict[str, set[str]] = {}

        # —— 节点元数据 ——
        self._entity_meta: dict[str, dict[str, Any]] = {}
        self._anchor_meta: dict[str, dict[str, Any]] = {}
        self._evidence_meta: dict[str, dict[str, Any]] = {}
        self._observation_meta: dict[str, dict[str, Any]] = {}
        self._known_ids: dict[str, HyperlinkLevel] = {}

        # —— 排序缓存（版本号失效，保证查询期不重复排序）——
        self._version = 0
        self._cache_version = -1
        self._sorted_cache: dict[tuple[str, str], tuple[str, ...]] = {}

        self._lock = threading.RLock()
        self._world_revision: int | None = None
        self._built_at = datetime.now(timezone.utc)
        self._dangling = 0

    # ------------------------------------------------------------------
    # 注册（写侧：仅内存派生索引，绝不触碰世界）
    # ------------------------------------------------------------------

    def register_entity_link(
        self,
        entity_id: str,
        aliases: Sequence[str],
        anchor_ids: Sequence[str],
        *,
        canonical_name: str | None = None,
        entity_type: str | None = None,
    ) -> None:
        """登记一个实体的别名集与其参与的事件锚点（工单强制接口）。

        幂等：同一 ``entity_id`` 重复登记采取**并集**语义，支持增量摄入流式补边。
        """
        self._require_id(entity_id, "entity_id")
        with self._lock:
            forms: list[str] = []
            if canonical_name is not None:
                forms.append(canonical_name)
            forms.extend(aliases)

            seen: set[str] = set()
            deduped: list[str] = []
            for form in forms:
                key = normalize_alias(form)
                if not key or key in seen:
                    continue
                seen.add(key)
                deduped.append(form.strip())
            if not deduped:
                raise AIOSProtocolError(
                    ErrorCode.INVALID_ARGUMENT,
                    "entity must declare at least one non-empty alias",
                    context={"reason": "empty_alias_set", "entity_id": entity_id},
                )

            self._entity_aliases[entity_id] = tuple(deduped)
            for form in deduped:
                self._alias_index.setdefault(normalize_alias(form), set()).add(entity_id)
            self._known_ids[entity_id] = HyperlinkLevel.ENTITY

            meta = self._entity_meta.setdefault(entity_id, {})
            if canonical_name is not None:
                meta["canonical_name"] = canonical_name
            if entity_type is not None:
                meta["entity_type"] = entity_type

            bucket = self._entity_anchors.setdefault(entity_id, set())
            for anchor_id in anchor_ids:
                self._require_id(anchor_id, "anchor_id")
                bucket.add(anchor_id)
                self._known_ids.setdefault(anchor_id, HyperlinkLevel.EVENT_ANCHOR)
            self._touch()

    def register_anchor_link(
        self,
        anchor_id: str,
        evidence_set_ids: Sequence[str],
        *,
        title: str | None = None,
        summary_text: str | None = None,
        occurred_at: datetime | None = None,
        event_status: str | None = None,
    ) -> None:
        """登记事件锚点 -> 证据集合的边（并集语义）。"""
        self._require_id(anchor_id, "anchor_id")
        with self._lock:
            meta = self._anchor_meta.setdefault(anchor_id, {})
            if title is not None:
                meta["title"] = title
            if summary_text is not None:
                meta["summary_text"] = summary_text
            if event_status is not None:
                meta["event_status"] = event_status
            parsed = occurred_at if isinstance(occurred_at, datetime) else _parse_time(occurred_at)
            if parsed is not None:
                meta["occurred_at"] = parsed
            self._known_ids.setdefault(anchor_id, HyperlinkLevel.EVENT_ANCHOR)
            bucket = self._anchor_evidence.setdefault(anchor_id, set())
            for evidence_id in evidence_set_ids:
                self._require_id(evidence_id, "evidence_set_id")
                bucket.add(evidence_id)
                self._known_ids.setdefault(evidence_id, HyperlinkLevel.EVIDENCE_SET)
            self._touch()

    def register_evidence_link(
        self,
        evidence_set_id: str,
        observation_ids: Sequence[str],
        *,
        purpose: str | None = None,
        knowledge_cutoff: datetime | None = None,
        stale: bool | None = None,
    ) -> None:
        """登记证据集合 -> 原始观测的边（并集语义）。"""
        self._require_id(evidence_set_id, "evidence_set_id")
        with self._lock:
            meta = self._evidence_meta.setdefault(evidence_set_id, {})
            if purpose is not None:
                meta["purpose"] = purpose
            cutoff = (
                knowledge_cutoff
                if isinstance(knowledge_cutoff, datetime)
                else _parse_time(knowledge_cutoff)
            )
            if cutoff is not None:
                meta["knowledge_cutoff"] = cutoff
            if stale is not None:
                meta["stale"] = bool(stale)
            self._known_ids.setdefault(evidence_set_id, HyperlinkLevel.EVIDENCE_SET)
            bucket = self._evidence_observations.setdefault(evidence_set_id, set())
            for observation_id in observation_ids:
                self._require_id(observation_id, "observation_id")
                bucket.add(observation_id)
                self._known_ids.setdefault(observation_id, HyperlinkLevel.OBSERVATION)
            self._touch()

    def register_observation(
        self,
        observation_id: str,
        *,
        content: str | None = None,
        occurred_at: datetime | None = None,
        learned_at: datetime | None = None,
        source_kind: str | None = None,
        modality: str | None = None,
        dimension_id: str | None = None,
        confidence: float | None = None,
    ) -> None:
        """登记观测元数据（可选；未登记时穿透仍返回 id 层节点）。"""
        self._require_id(observation_id, "observation_id")
        with self._lock:
            meta = self._observation_meta.setdefault(observation_id, {})
            if content is not None:
                meta["content"] = content
            for field_name, value in (("occurred_at", occurred_at), ("learned_at", learned_at)):
                parsed = value if isinstance(value, datetime) else _parse_time(value)
                if parsed is not None:
                    meta[field_name] = parsed
            if source_kind is not None:
                meta["source_kind"] = source_kind
            if modality is not None:
                meta["modality"] = modality
            if dimension_id is not None:
                meta["dimension_id"] = dimension_id
            if confidence is not None:
                meta["confidence"] = float(confidence)
            self._known_ids.setdefault(observation_id, HyperlinkLevel.OBSERVATION)
            self._touch()

    # ------------------------------------------------------------------
    # 从既有世界重建索引（只读；绝不写世界）
    # ------------------------------------------------------------------

    def build_from_store(self, store: Any) -> IndexBuildReport:
        """用 Core 公共只读接口重建四级索引。

        仅调用 ``list_payloads`` / ``current_world_revision``：
        **不 import sqlite3、不执行任何 SQL、不做任何写入**（铁律 #2）。
        边一律取自冻结契约里的结构化引用字段。
        """
        started = time.perf_counter()
        skipped = 0

        entity_payloads = list(store.list_payloads(object_type=ObjectType.ENTITY))
        anchor_payloads = list(store.list_payloads(object_type=ObjectType.EVENT))
        evidence_payloads = list(store.list_payloads(object_type=ObjectType.EVIDENCE_SET))
        observation_payloads = list(store.list_payloads(object_type=ObjectType.OBSERVATION))

        # 1) 实体 + 别名
        entity_ids: set[str] = set()
        for payload in entity_payloads:
            if not isinstance(payload, Mapping):
                skipped += 1
                continue
            entity_id = payload.get("object_id")
            if not isinstance(entity_id, str) or not entity_id:
                skipped += 1
                continue
            aliases_raw = payload.get("aliases")
            aliases = (
                [a for a in aliases_raw if isinstance(a, str)] if isinstance(aliases_raw, list) else []
            )
            canonical = payload.get("canonical_name")
            kind = payload.get("entity_kind")
            try:
                self.register_entity_link(
                    entity_id,
                    aliases,
                    (),
                    canonical_name=canonical if isinstance(canonical, str) else None,
                    entity_type=kind if isinstance(kind, str) else None,
                )
            except AIOSProtocolError:
                skipped += 1
                continue
            entity_ids.add(entity_id)

        # 2) 事件锚点：participant_refs 是 entity -> anchor 的真实结构化边
        anchor_ids: set[str] = set()
        for payload in anchor_payloads:
            if not isinstance(payload, Mapping):
                skipped += 1
                continue
            anchor_id = payload.get("object_id")
            if not isinstance(anchor_id, str) or not anchor_id:
                skipped += 1
                continue
            evidence_refs = _sorted_unique(
                (
                    *_ref_ids(payload.get("evidence_set_refs")),
                    *_ref_ids(payload.get("support_evidence_set_refs")),
                    *_ref_ids(payload.get("counter_evidence_set_refs")),
                )
            )
            self.register_anchor_link(
                anchor_id,
                evidence_refs,
                title=payload.get("title") if isinstance(payload.get("title"), str) else None,
                summary_text=(
                    payload.get("interpretation")
                    if isinstance(payload.get("interpretation"), str)
                    else None
                ),
                occurred_at=_extent_start(payload.get("event_time")),
                event_status=(
                    payload.get("event_status")
                    if isinstance(payload.get("event_status"), str)
                    else None
                ),
            )
            anchor_ids.add(anchor_id)

            for participant_id in _sorted_unique(_ref_ids(payload.get("participant_refs"))):
                if participant_id in entity_ids:
                    with self._lock:
                        self._entity_anchors.setdefault(participant_id, set()).add(anchor_id)
                        self._touch()
                else:
                    # 参与者不在本索引实体集合内：如实计入悬垂，绝不虚构边。
                    self._dangling += 1

        # 3) 证据集合 -> 观测
        evidence_ids: set[str] = set()
        for payload in evidence_payloads:
            if not isinstance(payload, Mapping):
                skipped += 1
                continue
            evidence_id = payload.get("object_id")
            if not isinstance(evidence_id, str) or not evidence_id:
                skipped += 1
                continue
            cutoff = None
            window = payload.get("knowledge_window")
            if isinstance(window, Mapping):
                cutoff = _parse_time(window.get("knowledge_cutoff"))
            stale_raw = payload.get("stale")
            self.register_evidence_link(
                evidence_id,
                _ref_ids(payload.get("member_refs")),
                purpose=payload.get("purpose") if isinstance(payload.get("purpose"), str) else None,
                knowledge_cutoff=cutoff,
                stale=bool(stale_raw) if stale_raw is not None else None,
            )
            evidence_ids.add(evidence_id)

        # 4) 观测元数据
        observation_ids: set[str] = set()
        for payload in observation_payloads:
            if not isinstance(payload, Mapping):
                skipped += 1
                continue
            observation_id = payload.get("object_id")
            if not isinstance(observation_id, str) or not observation_id:
                skipped += 1
                continue
            self.register_observation(
                observation_id,
                content=_coerce_text(payload.get("value")),
                occurred_at=_extent_start(payload.get("occurred")),
                learned_at=_parse_time(payload.get("learned_at")),
                source_kind=(
                    payload.get("source_kind")
                    if isinstance(payload.get("source_kind"), str)
                    else None
                ),
                modality=payload.get("modality") if isinstance(payload.get("modality"), str) else None,
            )
            observation_ids.add(observation_id)

        world_revision = int(store.current_world_revision())
        with self._lock:
            self._world_revision = world_revision
            self._built_at = datetime.now(timezone.utc)

        return IndexBuildReport(
            entities_loaded=len(entity_ids),
            anchors_loaded=len(anchor_ids),
            evidence_sets_loaded=len(evidence_ids),
            observations_loaded=len(observation_ids),
            payloads_skipped=skipped,
            dangling_refs=self._dangling,
            world_revision=world_revision,
            build_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------
    # 别名解析（宪法第三十六条：冲突必须显式暴露）
    # ------------------------------------------------------------------

    def resolve_entity(self, key: str) -> str:
        """把实体 id **或**别名解析为唯一实体 id；冲突抛 ``AmbiguousEntityAliasError``。"""
        self._require_id(key, "entity_id_or_alias")
        if key in self._entity_aliases:
            return key
        candidates = self._alias_index.get(normalize_alias(key), set())
        if not candidates:
            raise UnknownEntityError(key)
        if len(candidates) > 1:
            raise AmbiguousEntityAliasError(key, sorted(candidates))
        return next(iter(candidates))

    def aliases_for(self, entity_id: str) -> tuple[str, ...]:
        """返回该实体归一后的全部别名形态（含 canonical_name），稳定有序。"""
        return self._entity_aliases.get(entity_id, ())

    def ambiguous_alias_map(self) -> dict[str, tuple[str, ...]]:
        """全量冲突别名清单（供工作台/调试器巡检用），绝不参与自动合并。

        注意：本方法是 O(全部别名) 的巡检接口，**不在查询热路径上**；
        单次穿透只上报与本次根实体相关的冲突（见 ``_ambiguous_aliases_of``）。
        """
        return {
            alias: tuple(sorted(entity_ids))
            for alias, entity_ids in sorted(self._alias_index.items())
            if len(entity_ids) > 1
        }

    # ------------------------------------------------------------------
    # 穿透主入口
    # ------------------------------------------------------------------

    def traverse_entity_network(
        self,
        entity_id: str,
        depth: int = MAX_DEPTH,
        *,
        continuation: TraversalContinuation | None = None,
        require_fresh_store: Any | None = None,
    ) -> HyperlinkTraversalResult:
        """四级穿透：Entity -> EventAnchor -> EvidenceSet -> Observation。

        ``depth`` 语义为**访问层级数**（1..4）：
        1=仅实体档案；2=+事件锚点；3=+证据集合；4=+原始观测。
        返回的 ``traversal_depth`` 是本次**实际到达**的深度。

        ---- 检索契约（读侧 SLA 可证的事实）----
        * 顺序：各层一律**最近优先**（``occurred_at`` / ``knowledge_cutoff`` 降序，其次 id 升序），
          确定性可复现；同一实体经不同别名进入必然得到同一 ``result_fingerprint``。
        * 成本：单次查询的边展开量被 ``max_link_expansions`` 硬性约束，
          因此**耗时与全图规模无关**（10 万节点与 1 万节点同量级），
          这正是废除旧系统单表 LIKE 模糊扫表的核心收益。
        * 计数：``expansion_exhausted=False`` 时各层 ``*_discovered`` 相对**实际展开的父层**
          为精确值；为 True 时是**下界**，调用方必须知道证据尚未穷尽。
        * 续页：锚点层提供 ``continuation`` 游标，多页并集严格等于全量锚点集合（不跳号、不重不漏）。
        """
        started = time.perf_counter()

        if require_fresh_store is not None:
            self._assert_fresh(require_fresh_store)

        if not isinstance(depth, int) or isinstance(depth, bool) or not (1 <= depth <= MAX_DEPTH):
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                f"depth must be an integer within [1, {MAX_DEPTH}]",
                context={"reason": "invalid_depth", "depth": depth, "max_depth": MAX_DEPTH},
            )

        effective_depth = min(depth, continuation.depth) if continuation else depth
        offset_anchor = continuation.anchor_offset if continuation else 0
        root_id, resolved_via, used_alias = self._resolve_root(entity_id)

        anchors: list[AnchorNode] = []
        evidence_sets: list[EvidenceSetNode] = []
        observations: list[ObservationNode] = []

        anchors_discovered = 0
        evidence_discovered = 0
        observations_discovered = 0
        visited_edges = 0
        truncated = False
        reached_depth = 1

        # —— 展开预算：查询成本的结构性上限（与全图规模无关的根本原因）——
        budget_left = self._max_expansions
        expansion_exhausted = False
        fanout_capped_nodes = 0

        def _bounded_edges(node_id: str, container: str) -> tuple[str, ...]:
            """取某节点的出边：先按扇出上限封顶，再从展开预算中领取额度。"""
            nonlocal budget_left, expansion_exhausted, fanout_capped_nodes
            full = self._sorted(container, node_id)
            if len(full) > self._max_fanout:
                full = full[: self._max_fanout]
                fanout_capped_nodes += 1
            if not full:
                return ()
            if budget_left <= 0:
                expansion_exhausted = True
                return ()
            granted = len(full) if len(full) <= budget_left else budget_left
            budget_left -= granted
            if granted < len(full):
                expansion_exhausted = True
            return full[:granted]

        # —— 第二级：事件锚点（可续页）——
        if effective_depth >= 2:
            anchor_ids = self._sorted("entity_anchors", root_id)
            anchors_discovered = len(anchor_ids)
            if anchors_discovered:
                reached_depth = 2
            window = anchor_ids[offset_anchor : offset_anchor + self._max_anchors]
            if len(window) < anchors_discovered - offset_anchor:
                truncated = True
            for anchor_id in window:
                expanded = _bounded_edges(anchor_id, "anchor_evidence")
                if not expanded and expansion_exhausted:
                    # 预算耗尽：本页到此为止。游标从"已返回锚点数"续取，绝不跳号。
                    truncated = True
                    break
                visited_edges += 1 + len(expanded)
                anchors.append(
                    AnchorNode(
                        anchor_id=anchor_id,
                        title=self._anchor_meta.get(anchor_id, {}).get("title"),
                        summary_text=self._anchor_meta.get(anchor_id, {}).get("summary_text"),
                        event_status=self._anchor_meta.get(anchor_id, {}).get("event_status"),
                        occurred_at=self._anchor_meta.get(anchor_id, {}).get("occurred_at"),
                        evidence_set_ids=expanded,
                    )
                )

        # —— 第三级：证据集合 ——
        collected_evidence: dict[str, None] = {}
        if effective_depth >= 3 and anchors:
            for anchor in anchors:
                for evidence_id in anchor.evidence_set_ids:
                    collected_evidence.setdefault(evidence_id, None)
            all_evidence = sorted(
                collected_evidence,
                key=lambda i: (self._time_key(self._evidence_meta.get(i, {})), i),
            )
            evidence_discovered = len(all_evidence)
            if evidence_discovered:
                reached_depth = 3
            materialized = all_evidence[: self._max_evidence_sets]
            if len(materialized) < evidence_discovered:
                truncated = True
            for evidence_id in materialized:
                meta = self._evidence_meta.get(evidence_id, {})
                members = self._sorted("evidence_observations", evidence_id)
                # 证据集合的成员数是只读统计，不消耗展开预算（O(1) 取 len），
                # 但"成员是否被完整展开"受扇出上限约束，需如实上报。
                if len(members) > self._max_fanout:
                    fanout_capped_nodes += 1
                evidence_sets.append(
                    EvidenceSetNode(
                        evidence_set_id=evidence_id,
                        purpose=meta.get("purpose"),
                        knowledge_cutoff=meta.get("knowledge_cutoff"),
                        stale=bool(meta.get("stale", False)),
                        member_count=len(members),
                    )
                )

        # —— 第四级：原始观测 ——
        if effective_depth >= MAX_DEPTH and evidence_sets:
            seen_observations: dict[str, str] = {}
            for node in evidence_sets:
                expanded = _bounded_edges(node.evidence_set_id, "evidence_observations")
                for observation_id in expanded:
                    seen_observations.setdefault(observation_id, node.evidence_set_id)
                visited_edges += 1 + len(expanded)
            ordered = sorted(
                seen_observations,
                key=lambda i: (self._time_key(self._observation_meta.get(i, {})), i),
            )
            observations_discovered = len(ordered)
            if observations_discovered:
                reached_depth = MAX_DEPTH
            materialized_observations = ordered[: self._max_observations]
            if len(materialized_observations) < observations_discovered:
                truncated = True
            for observation_id in materialized_observations:
                meta = self._observation_meta.get(observation_id, {})
                observations.append(
                    ObservationNode(
                        observation_id=observation_id,
                        content=meta.get("content", ""),
                        source_kind=meta.get("source_kind"),
                        modality=meta.get("modality"),
                        dimension_id=meta.get("dimension_id"),
                        occurred_at=meta.get("occurred_at"),
                        learned_at=meta.get("learned_at"),
                        confidence=meta.get("confidence"),
                        via_evidence_set_id=seen_observations[observation_id],
                    )
                )

        # 扇出截断同样意味着"可达子图不完整"，必须计入截断（宁可多报，不可漏报）。
        if fanout_capped_nodes:
            truncated = True

        # —— 续页游标（仅锚点层）——
        next_anchor_offset = offset_anchor + len(anchors)
        continuation_out: TraversalContinuation | None = None
        if effective_depth >= 2 and next_anchor_offset < anchors_discovered:
            continuation_out = TraversalContinuation(
                anchor_offset=next_anchor_offset, depth=effective_depth
            )

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        entity_meta = self._entity_meta.get(root_id, {})
        coverage = TraversalCoverage(
            requested_depth=depth,
            reached_depth=reached_depth,
            anchors_discovered=anchors_discovered,
            anchors_returned=len(anchors),
            evidence_sets_discovered=evidence_discovered,
            evidence_sets_returned=len(evidence_sets),
            observations_discovered=observations_discovered,
            observations_returned=len(observations),
            dangling_refs=self._dangling,
            truncated=truncated,
            expansion_exhausted=expansion_exhausted,
            fanout_capped_nodes=fanout_capped_nodes,
            index_node_total=self.node_total,
            visited_edges=visited_edges,
        )
        return HyperlinkTraversalResult(
            root_entity_id=root_id,
            matched_aliases=list(self._entity_aliases.get(root_id, ())),
            anchors=anchors,
            observations=observations,
            traversal_depth=reached_depth,
            traversal_ms=elapsed_ms,
            root_entity=EntityNode(
                entity_id=root_id,
                canonical_name=entity_meta.get("canonical_name"),
                entity_type=entity_meta.get("entity_type"),
                aliases=tuple(self._entity_aliases.get(root_id, ())),
            ),
            evidence_sets=evidence_sets,
            coverage=coverage,
            resolved_via=resolved_via,
            resolved_via_alias=used_alias,
            ambiguous_aliases=self._ambiguous_aliases_of(root_id),
            index_world_revision=self._world_revision,
            continuation=continuation_out,
            result_fingerprint=_fingerprint(root_id, anchors, evidence_sets, observations),
        )

    # ------------------------------------------------------------------
    # 水位与自述
    # ------------------------------------------------------------------

    def index_watermark(self) -> IndexWatermark:
        counts = {
            HyperlinkLevel.ENTITY: 0,
            HyperlinkLevel.EVENT_ANCHOR: 0,
            HyperlinkLevel.EVIDENCE_SET: 0,
            HyperlinkLevel.OBSERVATION: 0,
        }
        for level in self._known_ids.values():
            counts[level] += 1
        return IndexWatermark(
            world_revision=self._world_revision,
            built_at=self._built_at,
            entities=counts[HyperlinkLevel.ENTITY],
            anchors=counts[HyperlinkLevel.EVENT_ANCHOR],
            evidence_sets=counts[HyperlinkLevel.EVIDENCE_SET],
            observations=counts[HyperlinkLevel.OBSERVATION],
            edges=(
                sum(len(v) for v in self._entity_anchors.values())
                + sum(len(v) for v in self._anchor_evidence.values())
                + sum(len(v) for v in self._evidence_observations.values())
            ),
        )

    @property
    def node_total(self) -> int:
        return len(self._known_ids)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _ambiguous_aliases_of(self, entity_id: str) -> list[AmbiguousAlias]:
        """只检查该实体自身的别名冲突（O(本实体别名数)），不排序全局别名索引。"""
        result: list[AmbiguousAlias] = []
        for form in self._entity_aliases.get(entity_id, ()):
            candidates = self._alias_index.get(normalize_alias(form))
            if candidates and len(candidates) > 1:
                result.append(
                    AmbiguousAlias(alias=normalize_alias(form), entity_ids=tuple(sorted(candidates)))
                )
        return result

    def _resolve_root(self, key: str) -> tuple[str, str, str | None]:
        if key in self._entity_aliases:
            return key, "entity_id", None
        return self.resolve_entity(key), "alias", key.strip()

    def _assert_fresh(self, store: Any) -> None:
        world_revision = int(store.current_world_revision())
        if self._world_revision is None or self._world_revision != world_revision:
            raise StaleHyperlinkIndexError(self._world_revision, world_revision)

    def _touch(self) -> None:
        self._version += 1

    def _sorted(self, container: str, node_id: str) -> tuple[str, ...]:
        """返回确定序邻接表；同一次注册版本内只排序一次（查询期零重复排序）。"""
        if self._cache_version != self._version:
            self._sorted_cache.clear()
            self._cache_version = self._version
        cache_key = (container, node_id)
        cached = self._sorted_cache.get(cache_key)
        if cached is not None:
            return cached

        if container == "entity_anchors":
            raw = self._entity_anchors.get(node_id, ())
            ordered = tuple(
                sorted(raw, key=lambda i: (self._time_key(self._anchor_meta.get(i, {})), i))
            )
        elif container == "anchor_evidence":
            ordered = tuple(sorted(self._anchor_evidence.get(node_id, ())))
        elif container == "evidence_observations":
            raw = self._evidence_observations.get(node_id, ())
            ordered = tuple(
                sorted(raw, key=lambda i: (self._time_key(self._observation_meta.get(i, {})), i))
            )
        else:  # pragma: no cover - 防御性分支
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "unknown adjacency container",
                context={"reason": "unknown_container", "container": container},
            )
        self._sorted_cache[cache_key] = ordered
        return ordered

    @staticmethod
    def _time_key(meta: Mapping[str, Any]) -> tuple[int, float]:
        """排序键：-(最近发生时间)。时间未知的节点排在已知之后，绝不编造精确值。"""
        for field_name in ("occurred_at", "knowledge_cutoff", "learned_at"):
            moment = meta.get(field_name)
            if isinstance(moment, datetime):
                return (0, -moment.timestamp())
        return (1, 0.0)

    @staticmethod
    def _require_id(value: Any, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                f"{field_name} must be a non-empty string",
                context={"reason": "invalid_identifier", "field": field_name},
            )
