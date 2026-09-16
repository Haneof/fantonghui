"""M1-018 认知反向传播语义图层契约与回溯标注引擎（Agent-05 并行实现 · 独立命名版）。

> **并行开发并存说明**：本文件是 arena/01a0a700 会话（agent-05）对同一工单
> 的独立全量实现，按交付方要求以独立模块名保存，与同路径已合入的战友实现
> ``retrospective_annotation.py`` **并存共置、互不覆盖**。两者的技术分歧点
> （错误分类法 / naive 时区策略 / 视图返回形态 / 注记注册组件形态）已留档
> ``governance/agent_reports/agent-05-m1-018/LATEST.md`` 待首席仲裁。
> 本模块不经过 ``aios_core.world.__init__`` 导出，以全路径显式引用。

## 高阶实战场景（本模块的验收叙事基座）

用户两年前与核心技术合伙人签署《Pre-A 轮联合孵化与股权代持对赌协议》。
过去 730 天，系统累积落账 18,000 条客观事实 ``Observation`` 链：技术评审
纪要、商业汇款凭证、深夜高压谈判时的心率变异度与皮质醇体征、重大合同。

第 730 天，司法机关下达冻结查封裁定书，证实该合伙人自设立之初即利用
关联离岸空壳公司转移核心知识产权并隐匿巨额对外连带担保。

系统唯一合法的认知响应是：**今天只追加一条 ``RetrospectiveAnnotation``**
（``learned_at = T_today``，``valid_time_range = [T0, T_today]``），挂载
司法查封与欺诈重估注记。过去 730 天的 18,000 条原始记录的 SHA-256 物理
哈希必须 100% 保持不变，结构上不存在 SQL UPDATE / DELETE 通道。

## 四大硬门禁的工程落点

1. **历史事实绝对不可变**：底账仅存规范化 JSON + 内容寻址 SHA-256；
   本引擎对存储底座零写入，任何挂载/查询都不引发新 world_commit。
2. **今天打标签**：注记契约强制 ``learned_at = recorded_at = T_today``
   且 ``learned_at >= target_time_end``——假装当时就知道即违宪。
3. **双时间认知透镜** ``BiTemporalEpistemicLens``：
   ``as_of_cutoff = T0 + 100 天`` 时 ``active_annotations`` 严格为空，
   精准还原当时的商业信任状态；``as_of_cutoff = None`` 时历史事实完整
   保留并精确叠加外挂重估图层。
4. **单跳隔离杜绝雪崩** ``SingleHopCascadeIsolator``：反向失效只把
   「直接消费该合伙人认知」的 1 级节点标为 ``is_stale=True``（严格
   10 个），遍历深度严格为 1，立刻执行的 LLM 重算作业严格为 0——
   兜底掐灭 210+ 次大模型算力雪崩，下游仅按需懒加载。

宪法第九十三条铁律在此全部结构化为代码：时间单向向前，历史不可篡改。
"""

from __future__ import annotations

import bisect
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.time import as_utc, canonical_utc_iso, require_aware, utc_now
from aios_core.errors import AIOSProtocolError

__all__ = [
    "RetrospectiveAnnotation",
    "BiTemporalEpistemicLens",
    "EpistemicWorldLens",
    "SingleHopCascadeIsolator",
    "CascadeIsolationReport",
    "RetrospectiveAnnotationError",
    "canonical_fact_sha256",
]


class RetrospectiveAnnotationError(AIOSProtocolError):
    """M1-018 图层引擎向协议边界传播的已知失败（与 C02 存储底座同族错误分类法）。"""


# ---------------------------------------------------------------------------
# 规范化与内容寻址哈希（字节级不可篡改断言的唯一事实来源）
# ---------------------------------------------------------------------------


def _canonicalize(value: Any) -> Any:
    """将任意 JSON 可用值规范化为确定性结构（供稳定哈希）。

    - Mapping: 键排序递归规范化；
    - set / frozenset: 排序为列表（无序集合的跨进程稳定，M0-B8 既定语义）；
    - tuple: 转为 list；
    - BaseModel: ``model_dump(mode="json")`` 后递归；
    - datetime: UTC ISO 字符串。
    """
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (set, frozenset)):
        canon_items = [_canonicalize(v) for v in value]
        return sorted(canon_items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, datetime):
        return canonical_utc_iso(value)
    return value


def canonical_fact_sha256(payload: Any) -> str:
    """计算底层事实载荷的规范化 SHA-256（hex）。

    这是「历史不可篡改」断言的度量尺：司法裁定注记挂载/查询前后，同一
    事实对象的该哈希值必须严格逐比特一致。
    """
    canon = _canonicalize(payload)
    blob = json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# 数据契约（云端工单 TASK-M1-018 冻结字段）
# ---------------------------------------------------------------------------


class RetrospectiveAnnotation(BaseModel):
    """回溯注记：今天学到的认知，外挂挂载在过去时空切片上的解释图层。

    本对象本身是不可变的追加事实（frozen）；它不携带任何指向其他注记的
    字段，从结构上保证「单跳」——不存在注记之注记的递归链。

    高阶场景实例：``learned_at = T_today``（司法查封裁定下达当日），
    ``[target_time_start, target_time_end] = [T0, T_today]``（覆盖
    730 天的合伙孵化全周期），``semantic_overlay`` 挂载「司法冻结查封 /
    欺诈重估」。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    semantic_overlay: str = Field(min_length=1, description="挂载的解释图层，如'司法冻结查封/欺诈重估'")
    target_time_start: datetime
    target_time_end: datetime
    learned_at: datetime = Field(default_factory=utc_now)
    recorded_at: datetime = Field(default_factory=utc_now)
    source_statement_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_retrospective_contract(self) -> "RetrospectiveAnnotation":
        for field_name in ("annotation_id", "target_entity_id", "semantic_overlay", "source_statement_ref"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")

        require_aware(self.target_time_start, "target_time_start")
        require_aware(self.target_time_end, "target_time_end")
        require_aware(self.learned_at, "learned_at")
        require_aware(self.recorded_at, "recorded_at")

        if as_utc(self.target_time_end, "target_time_end") < as_utc(self.target_time_start, "target_time_start"):
            raise ValueError("target_time_end must not be before target_time_start")

        if as_utc(self.recorded_at, "recorded_at") < as_utc(self.learned_at, "learned_at"):
            raise ValueError("recorded_at must be >= learned_at")

        # 回溯铁律：认知只追加在当下——本次学习必须不早于目标切片终点。
        # 结构上封死「假装当时就什么都知道」的倒写历史通道。
        if as_utc(self.learned_at, "learned_at") < as_utc(self.target_time_end, "target_time_end"):
            raise ValueError(
                "learned_at must be >= target_time_end: 回溯注记必须在切片之后学到，严禁倒写历史"
            )
        return self

    def covers(self, target_time: datetime) -> bool:
        """目标时间点是否落在本注记指针指向的过去切片内（UTC 归一比较）。"""
        t = as_utc(target_time, "target_time")
        return as_utc(self.target_time_start, "target_time_start") <= t <= as_utc(
            self.target_time_end, "target_time_end"
        )


# ---------------------------------------------------------------------------
# 双时间认知透镜（BiTemporal Epistemic Lens）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _FrozenFact:
    """内部冻结事实切片：只存规范化 JSON 串与内容哈希，二进制上不可回写。"""

    fact_id: str
    entity_id: str
    valid_start: datetime  # UTC 归一
    valid_end: datetime  # UTC 归一
    payload_json: str
    sha256: str

    @property
    def is_point(self) -> bool:
        return self.valid_start == self.valid_end


class BiTemporalEpistemicLens:
    """认知世界双时间透镜（M1-018 · 双时间认知透镜 BiTemporalEpistemicLens）。

    - ``attach_annotation`` 只追加解释图层，永不触碰底层事实；
    - ``query_historical_slice`` 按点单跳渲染：历史事实字节级原样返回，
      ``active_annotations`` 的可见性严格服从 ``learned_at <= as_of_cutoff``
      的知识截止律；
    - 渲染全部懒加载于查询时刻，不持久化任何派生结果，不产生历史重算；
    - 事实底账按实体分桶 + 时间有序索引：万级事实下查询成本与命中规模
      同阶，与全库规模解耦（压测级要求的结构性保障）。
    """

    DEFAULT_MAX_ANNOTATIONS_PER_ENTITY = 10_000

    def __init__(self, *, max_annotations_per_entity: int = DEFAULT_MAX_ANNOTATIONS_PER_ENTITY) -> None:
        if not isinstance(max_annotations_per_entity, int) or max_annotations_per_entity < 1:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "max_annotations_per_entity must be a positive int (级联雪崩预算硬上限)",
            )
        self._max_annotations_per_entity = max_annotations_per_entity
        # Append-only 底账：只进不出。按实体分桶；点事实走时间有序索引，
        # 区间事实独立小表扫描（区间在实务中极少）。
        self._fact_points: Dict[str, List[Tuple[datetime, int, _FrozenFact]]] = {}
        self._fact_spans: Dict[str, List[_FrozenFact]] = {}
        self._fact_seq = 0
        self._fact_count = 0
        self._annotations: Dict[str, List[RetrospectiveAnnotation]] = {}
        self._annotation_fingerprints: Dict[str, str] = {}
        self._stats: Dict[str, int] = {
            "facts_attached": 0,
            "annotations_attached": 0,
            "queries": 0,
            "fact_hits_total": 0,
            "overlay_hits_total": 0,
        }

    # ------------------------------------------------------------------
    # 事实底账登记（只追加：为查询透镜提供历史切片，便于测试引擎与演示装配）
    # ------------------------------------------------------------------

    def attach_fact(
        self,
        *,
        entity_id: str,
        valid_time_start: datetime,
        payload: Any,
        valid_time_end: Optional[datetime] = None,
        fact_id: Optional[str] = None,
    ) -> str:
        """登记一条不可变历史事实切片，返回其内容事实 ``fact_id``。

        载荷立即规范化并仅存其 JSON 串与 SHA-256；调用方事后篡改原对象
        不影响透镜内冻结副本（结构式防倒写）。
        """
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "entity_id must be a non-empty string",
            )
        require_aware(valid_time_start, "valid_time_start")
        require_aware(valid_time_end, "valid_time_end")
        start = as_utc(valid_time_start, "valid_time_start")
        end = as_utc(valid_time_end if valid_time_end is not None else valid_time_start, "valid_time_end")
        if end < start:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "valid_time_end must not be before valid_time_start",
            )

        try:
            canon = _canonicalize(payload)
            payload_json = json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "payload must be JSON-serializable (含 Mapping / BaseModel)",
            ) from exc

        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        resolved_fact_id = fact_id or f"fact-{digest[:16]}"
        fact = _FrozenFact(
            fact_id=resolved_fact_id,
            entity_id=entity_id,
            valid_start=start,
            valid_end=end,
            payload_json=payload_json,
            sha256=digest,
        )
        if fact.is_point:
            bucket = self._fact_points.setdefault(entity_id, [])
            bisect.insort(bucket, (start, self._fact_seq, fact))
        else:
            self._fact_spans.setdefault(entity_id, []).append(fact)
        self._fact_seq += 1
        self._fact_count += 1
        self._stats["facts_attached"] += 1
        return resolved_fact_id

    # ------------------------------------------------------------------
    # 云端工单契约方法 1：挂载回溯注记（唯一写入口；绝不触碰事实底账）
    # ------------------------------------------------------------------

    def attach_annotation(self, annotation: RetrospectiveAnnotation) -> str:
        """挂载一条 ``RetrospectiveAnnotation`` 解释图层。

        - 幂等：同一 ``annotation_id`` 以完全相同的内容重复挂载为无操作；
          同 ID 不同内容视为冲突（IDEMPOTENCY_CONFLICT），拒绝静默覆盖；
        - 预算：单实体图层数超过硬上限即 BUDGET_EXHAUSTED，
          从结构上拒绝无界级联追加（宪法 93 条第 3 款）。
        """
        if not isinstance(annotation, RetrospectiveAnnotation):
            raise TypeError(
                f"annotation must be a RetrospectiveAnnotation, got {type(annotation).__name__}"
            )

        fingerprint = canonical_fact_sha256(annotation.model_dump(mode="json"))
        prior = self._annotation_fingerprints.get(annotation.annotation_id)
        if prior is not None:
            if prior == fingerprint:
                return annotation.annotation_id  # 幂等重放：无操作
            raise RetrospectiveAnnotationError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                f"annotation_id '{annotation.annotation_id}' already attached with different content",
                context={"annotation_id": annotation.annotation_id},
            )

        bucket = self._annotations.setdefault(annotation.target_entity_id, [])
        if len(bucket) >= self._max_annotations_per_entity:
            raise RetrospectiveAnnotationError(
                ErrorCode.BUDGET_EXHAUSTED,
                "annotation budget exhausted for entity: 拒绝无界级联图层雪崩",
                context={
                    "target_entity_id": annotation.target_entity_id,
                    "max_annotations_per_entity": self._max_annotations_per_entity,
                },
            )

        bucket.append(annotation)
        self._annotation_fingerprints[annotation.annotation_id] = fingerprint
        self._stats["annotations_attached"] += 1
        return annotation.annotation_id

    # ------------------------------------------------------------------
    # 云端工单契约方法 2：双时间视图查询（懒渲染、单跳、零倒写）
    # ------------------------------------------------------------------

    def _fact_hits_at(self, entity_id: str, t: datetime) -> List[_FrozenFact]:
        """按点命中事实：点时间有序索引 + 极少量区间事实扫描。"""
        hits: List[_FrozenFact] = []
        points = self._fact_points.get(entity_id)
        if points:
            lo = bisect.bisect_left(points, (t, -1))
            hi = bisect.bisect_right(points, (t, 1 << 62))
            hits.extend(entry[2] for entry in points[lo:hi])
        spans = self._fact_spans.get(entity_id)
        if spans:
            hits.extend(f for f in spans if f.valid_start <= t <= f.valid_end)
        return hits

    def query_historical_slice(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """查询 ``entity_id`` 在 ``target_time`` 切片的双时间视图。

        - ``as_of_cutoff is None``：当前认知视图，全部已挂载图层精确叠加
          到 ``active_annotations``；
        - ``as_of_cutoff`` 给定（如 T0+100 天）：当时已知视图，仅渲染
          ``learned_at <= cutoff`` 的图层——司法查封裁定属于未来认知，
          对当时视图**严格不可见**，``active_annotations`` 为空，历史
          商业信任状态完整重现。

        本方法为纯读：不改写事实、不回写派生结果、不触发任何级联重算。
        """
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "entity_id must be a non-empty string",
            )
        require_aware(target_time, "target_time")
        require_aware(as_of_cutoff, "as_of_cutoff")
        t = as_utc(target_time, "target_time")
        cutoff = as_utc(as_of_cutoff, "as_of_cutoff") if as_of_cutoff is not None else None

        # 单跳按点命中：只取「直接指向该实体该切片」的图层，无递归展开。
        direct_hits = [
            a for a in self._annotations.get(entity_id, []) if a.covers(t)
        ]
        if cutoff is None:
            visible = direct_hits
        else:
            visible = [a for a in direct_hits if as_utc(a.learned_at, "learned_at") <= cutoff]

        fact_hits = self._fact_hits_at(entity_id, t)

        self._stats["queries"] += 1
        self._stats["fact_hits_total"] += len(fact_hits)
        self._stats["overlay_hits_total"] += len(visible)

        active_annotations = [
            {
                "annotation_id": a.annotation_id,
                "semantic_overlay": a.semantic_overlay,
                "rendered_as": "warning_marker",
                "target_time_start": canonical_utc_iso(a.target_time_start, "target_time_start"),
                "target_time_end": canonical_utc_iso(a.target_time_end, "target_time_end"),
                "learned_at": canonical_utc_iso(a.learned_at, "learned_at"),
                "recorded_at": canonical_utc_iso(a.recorded_at, "recorded_at"),
                "source_statement_ref": a.source_statement_ref,
            }
            for a in visible
        ]

        return {
            "entity_id": entity_id,
            "target_time": canonical_utc_iso(t),
            "as_of_cutoff": canonical_utc_iso(cutoff) if cutoff is not None else None,
            "view_mode": "current_overlay" if cutoff is None else "as_of_historical",
            "facts": [
                {
                    "fact_id": f.fact_id,
                    "sha256": f.sha256,
                    "valid_time_start": canonical_utc_iso(f.valid_start),
                    "valid_time_end": canonical_utc_iso(f.valid_end),
                    # 每次查询重建的全新副本：调用方篡改返回值不会污染冻结底账。
                    "payload": json.loads(f.payload_json),
                }
                for f in fact_hits
            ],
            "fact_count": len(fact_hits),
            # 双时间透镜的核心渲染结果。
            "active_annotations": active_annotations,
            "overlay_count": len(active_annotations),
            # 一号工单字段别名（同一内容）。
            "overlays": active_annotations,
            "integrity": {
                # 宪法第 93 条结构性铁律标记：该透镜在结构上永远成立。
                "history_rewritten": False,
                "cascade_recompute": False,
                "lazy_evaluation": True,
                "single_hop": True,
            },
        }

    # ------------------------------------------------------------------
    # 只读审计辅助
    # ------------------------------------------------------------------

    def annotations_for(self, entity_id: str) -> List[RetrospectiveAnnotation]:
        """返回实体当前挂载的全部图层（append 顺序的只读拷贝）。"""
        return list(self._annotations.get(entity_id, []))

    @property
    def fact_count(self) -> int:
        """底账冻结事实总数（只读）。"""
        return self._fact_count

    @property
    def stats(self) -> Dict[str, int]:
        """懒加载/单跳工作量的只读计数（用于断言无级联重算）。"""
        return dict(self._stats)

    def hash_snapshot(self, entity_id: str) -> Dict[str, str]:
        """实体全部冻结事实的 ``fact_id -> sha256`` 快照（审计/压测断言用）。"""
        snapshot: Dict[str, str] = {}
        for entry in self._fact_points.get(entity_id, []):
            fact = entry[2]
            snapshot[fact.fact_id] = fact.sha256
        for fact in self._fact_spans.get(entity_id, []):
            snapshot[fact.fact_id] = fact.sha256
        return snapshot


# 一号工单（TASK-M1-018 R1）冻结的类别名：保持向后兼容。
EpistemicWorldLens = BiTemporalEpistemicLens


# ---------------------------------------------------------------------------
# 单跳级联隔离器（宪法 93 条第 3 款：拒绝全盘级联雪崩与历史重算）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CascadeIsolationReport:
    """一次反向失效隔离执行的不可变审计报告。

    不变量：
    - ``max_traversal_depth`` 恒为 1（有直接消费者）或 0（无消费者）；
    - ``llm_recompute_jobs_executed`` 恒为 0：失效当刻零重算，被标记的
      1 级节点只在未来被真实需要时才各自懒加载重写；
    - ``stale_node_ids`` 严格等于 source 的直接消费者集合。
    """

    source_id: str
    stale_node_ids: Tuple[str, ...]
    max_traversal_depth: int
    nodes_touched: int
    llm_recompute_jobs_executed: int

    @property
    def stale_count(self) -> int:
        return len(self.stale_node_ids)


class SingleHopCascadeIsolator:
    """反向失效单跳隔离器：把失效传播严格掐死在 1 级直接消费者。

    依赖网络可以任意深（如 5 层、上万节点）：一级下游 10 个、二级 200
    个、三级 1000 个……朴素递归失效会把全部下游卷入大模型重算（算力
    雪崩）。本隔离器在结构上只遍历 source 的邻接表一次：

    - 标记 ``is_stale=True`` 的节点 = 直接消费该认知的 1 级节点，一个不
      多、一个不少；
    - 深度 >= 2 的节点绝不被主动触碰，更不会被级联重算；
    - 被标 stale 的节点不立即重算（LLM 作业 = 0），未来按需懒加载重写，
      重写完成经 ``mark_resolved`` 摘牌。
    """

    def __init__(self, *, max_marks_per_invalidation: Optional[int] = None) -> None:
        if max_marks_per_invalidation is not None and (
            not isinstance(max_marks_per_invalidation, int) or max_marks_per_invalidation < 1
        ):
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "max_marks_per_invalidation must be a positive int or None",
            )
        self._max_marks = max_marks_per_invalidation
        # 邻接表：source_id -> 直接消费者集合（consumer 主动依赖 source）。
        self._dependents_of: Dict[str, set[str]] = {}
        self._dependencies_of: Dict[str, set[str]] = {}
        self._stale: set[str] = set()
        self._stats: Dict[str, int] = {
            "edges": 0,
            "invalidations": 0,
            "nodes_marked_total": 0,
        }

    # ------------------------------------------------------------------
    # 依赖建网（只追加）
    # ------------------------------------------------------------------

    def add_dependency(self, consumer_node_id: str, source_node_id: str) -> None:
        """登记一条有向依赖边：``consumer`` 直接消费 ``source`` 的认知。"""
        for field_name, value in (("consumer_node_id", consumer_node_id), ("source_node_id", source_node_id)):
            if not isinstance(value, str) or not value.strip():
                raise RetrospectiveAnnotationError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{field_name} must be a non-empty string",
                )
        if consumer_node_id == source_node_id:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "dependency cannot be a self loop",
            )
        bucket = self._dependents_of.setdefault(source_node_id, set())
        if consumer_node_id not in bucket:
            bucket.add(consumer_node_id)
            self._dependencies_of.setdefault(consumer_node_id, set()).add(source_node_id)
            self._stats["edges"] += 1

    def add_dependencies(self, edges: Iterable[Tuple[str, str]]) -> None:
        """批量建网：``edges`` 为 ``(consumer, source)`` 序列。"""
        for consumer, source in edges:
            self.add_dependency(consumer, source)

    # ------------------------------------------------------------------
    # 反向失效：单跳标记，绝不递归
    # ------------------------------------------------------------------

    def invalidate(self, source_node_id: str) -> CascadeIsolationReport:
        """对 ``source`` 执行反向失效隔离，返回审计报告。

        实现即证明：只读一次邻接表，``max_traversal_depth`` 结构上不可能
        超过 1；不下探任何二级消费者，零 LLM 重算作业。
        """
        if not isinstance(source_node_id, str) or not source_node_id.strip():
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "source_node_id must be a non-empty string",
            )

        # 单跳：唯一的一次邻接读取。其后绝不再沿 consumer 下探。
        direct_consumers = sorted(self._dependents_of.get(source_node_id, ()))

        if self._max_marks is not None and len(direct_consumers) > self._max_marks:
            raise RetrospectiveAnnotationError(
                ErrorCode.BUDGET_EXHAUSTED,
                "invalidation marks exceed budget: 拒绝级联标记雪崩",
                context={
                    "source_node_id": source_node_id,
                    "direct_consumers": len(direct_consumers),
                    "max_marks_per_invalidation": self._max_marks,
                },
            )

        for node_id in direct_consumers:
            self._stale.add(node_id)

        self._stats["invalidations"] += 1
        self._stats["nodes_marked_total"] += len(direct_consumers)

        return CascadeIsolationReport(
            source_id=source_node_id,
            stale_node_ids=tuple(direct_consumers),
            max_traversal_depth=1 if direct_consumers else 0,
            nodes_touched=1 + len(direct_consumers),
            llm_recompute_jobs_executed=0,
        )

    # ------------------------------------------------------------------
    # 只读/摘牌接口
    # ------------------------------------------------------------------

    def is_stale(self, node_id: str) -> bool:
        return node_id in self._stale

    def stale_nodes(self) -> Tuple[str, ...]:
        """当前仍在污点名单上的全部节点（排序快照）。"""
        return tuple(sorted(self._stale))

    def direct_consumers_of(self, source_node_id: str) -> Tuple[str, ...]:
        return tuple(sorted(self._dependents_of.get(source_node_id, ())))

    def direct_dependencies_of(self, consumer_node_id: str) -> Tuple[str, ...]:
        return tuple(sorted(self._dependencies_of.get(consumer_node_id, ())))

    def mark_resolved(self, node_id: str) -> None:
        """节点经懒加载按需重写后摘牌（is_stale=False）。"""
        self._stale.discard(node_id)

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)
