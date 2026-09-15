"""M1-018 认知反向传播语义图层契约与回溯标注引擎（老王案 / 宪法第 93 条）。

宪法第九十三条「错误允许存在，认知随时间向前演化（严禁篡改历史）」在本模块
落为三条结构性工程铁律：

1. **历史不可篡改**：两年前的客观事实（聊天记录、心率、合伙事件等
   ``Observation``）字节级冻结，本引擎在结构上只有「追加」，没有任何
   UPDATE / DELETE 通道；挂载标注后，原始事实的 SHA-256 内容哈希
   必须 100% 保持不变。
2. **新认知只写在当前时间戳（T_now）**：今天学到「老王是骗子」，不回去改写
   任何历史对话，只生成一条 ``RetrospectiveAnnotation``——其自身
   ``learned_at = recorded_at = T_now``，并以
   ``target_time_start / target_time_end`` 指针指向过去的老王时空切片，
   充当外挂「解释图层」（Overlay）。
3. **拒绝全盘级联雪崩与历史重算**：透镜（``EpistemicWorldLens``）只做
   **单跳**按点查询——命中「直接挂在该切片上」的图层即渲染，绝不递归穿透、
   绝不下探重算历史周/月总结；渲染按需懒加载（Lazy Evaluation），
   并带每实体图层预算硬上限，从结构上杜绝算力雪崩。

双时间透镜（Bitemporal Lens）：

- ``as_of_cutoff=两年前``：当时已知视图——完整重现「那时信任老王」的
  历史真实人生原貌，今天才学到的注记严格不可见（零认知泄露）；
- ``as_of_cutoff=None``：当前认知视图——历史切片原貌之上，动态渲染
  「后来发现是骗子」的警示标记；历史曲线本身分毫不动。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import as_utc, canonical_utc_iso, require_aware, utc_now
from aios_core.contracts.enums import ErrorCode
from aios_core.errors import AIOSProtocolError

__all__ = [
    "RetrospectiveAnnotation",
    "EpistemicWorldLens",
    "RetrospectiveAnnotationError",
    "canonical_fact_sha256",
]


class RetrospectiveAnnotationError(AIOSProtocolError):
    """M1-018 图层引擎向协议边界传播的已知失败。"""


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

    这是「历史不可篡改」断言的度量尺：挂载/查询标注前后，同一事实对象的
    该哈希值必须严格逐比特一致。
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
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    semantic_overlay: str = Field(min_length=1, description="挂载的解释图层，如'疑似欺诈'")
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
# 双时间视图查询透镜
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


class EpistemicWorldLens:
    """认知世界双时间透镜（M1-018 老王案）。

    - ``attach_annotation`` 只追加解释图层，永不触碰底层事实；
    - ``query_historical_slice`` 按点单跳渲染：历史事实字节级原样返回，
      图层可见性严格服从 ``learned_at <= as_of_cutoff`` 的知识截止律；
    - 渲染全部懒加载于查询时刻，不持久化任何派生结果，不产生历史重算。
    """

    DEFAULT_MAX_ANNOTATIONS_PER_ENTITY = 10_000

    def __init__(self, *, max_annotations_per_entity: int = DEFAULT_MAX_ANNOTATIONS_PER_ENTITY) -> None:
        if not isinstance(max_annotations_per_entity, int) or max_annotations_per_entity < 1:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "max_annotations_per_entity must be a positive int (级联雪崩预算硬上限)",
            )
        self._max_annotations_per_entity = max_annotations_per_entity
        # Append-only 底账：只进不出。
        self._facts: List[_FrozenFact] = []
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
        self._facts.append(
            _FrozenFact(
                fact_id=resolved_fact_id,
                entity_id=entity_id,
                valid_start=start,
                valid_end=end,
                payload_json=payload_json,
                sha256=digest,
            )
        )
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

    def query_historical_slice(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """查询 ``entity_id`` 在 ``target_time`` 切片的双时间视图。

        - ``as_of_cutoff is None``：当前认知视图，全部已挂载图层动态渲染为
          警示标记；
        - ``as_of_cutoff`` 给定：当时已知视图，仅渲染 ``learned_at <= cutoff``
          的图层——今天才学到的认知对该视图**严格不可见**，历史原貌完整重现。

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

        fact_hits = [
            f for f in self._facts if f.entity_id == entity_id and f.valid_start <= t <= f.valid_end
        ]

        self._stats["queries"] += 1
        self._stats["fact_hits_total"] += len(fact_hits)
        self._stats["overlay_hits_total"] += len(visible)

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
            "overlays": [
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
            ],
            "overlay_count": len(visible),
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
    def stats(self) -> Dict[str, int]:
        """懒加载/单跳工作量的只读计数（用于断言无级联重算）。"""
        return dict(self._stats)
