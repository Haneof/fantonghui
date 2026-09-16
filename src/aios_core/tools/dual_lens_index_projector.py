"""双透镜虚拟索引投影器（Dual-Lens Virtual Index Projector，ToolProposal TLP-DLV-002）。

宪法依据
--------
* 第七条 / 第三十一条之一：认知的校准必须能在**不篡改历史**的前提下完成；
* 第二十五条 & 第九十三条：过去的事实字节级不可变，新认知只在今天挂外挂注解；
* 第三十三条之一（R4-01 双时间透镜）：同一份历史必须能同时回答两个问题 ——
  "当年我认知里的世界是什么样"（``AS_KNOWN``）与"今天回看叠加注解的世界是什么
  样"（``ANNOTATED``）。
* 第八十六条之一：算力预算硬约束。

为什么既有实现不够
------------------
仓库既有的双透镜实现（``world.view_lens.view_at`` / ``EpistemicWorldLens``）是
**读面**语义：每次查询都把底层事实全量拉出来、再逐条叠加注解（``O(全部事实数)``）。
在"3 年 18000 条事实 + 今日 1 条注解"的老王案里，这条路径每次查询都要重扫
18000 条并重建对象字典 —— 这正是算力雪崩的读面孪生体，只是藏在查询延迟里。

本投影器把双透镜下沉到**索引层**，用"共享基底 + 注解增量"的虚拟视图替换全量重建：

* 基底倒排索引只建一次（``index_fact``），AS_KNOWN 透镜直接读基底；
* 挂注解时只写**该注解自身词元的增量 posting**（``O(|注解文本|)``），
  并把被致废目标登记进薄薄的 override 集合；
* ANNOTATED 透镜 = 基底 posting ∪ 增量 posting，并按 override 集合贴注解标记 ——
  基底哈希在挂注解前后逐字节不变（历史不可篡改在索引层的体现）；
* 度量 ``naive_projection_postings`` 与 ``overlay_postings_written`` 直接量化
  "全量重建 vs 增量投影" 的 I/O 差，杜绝口号式优化。

零第三方依赖，纯内存结构，可被 C06 检索总线或端侧 ring buffer 直接复用。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.query.cjk_inverted_index import tokenize_cjk_overlapping

__all__ = [
    "ANNOTATED",
    "AS_KNOWN",
    "DualLensVirtualIndexProjector",
    "LensHit",
    "LensQueryResult",
    "ProjectionMetrics",
]

AS_KNOWN = "AS_KNOWN"
ANNOTATED = "ANNOTATED"
_VALID_LENSES = (AS_KNOWN, ANNOTATED)


class LensHit(BaseModel):
    """单条透镜命中：同一 object_id 在两条透镜上的评分口径完全一致。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str
    score: int = Field(ge=0)
    matched_terms: tuple[str, ...] = ()
    annotation_ids: tuple[str, ...] = ()
    invalidated_by: tuple[str, ...] = ()
    learned_us: int


class LensQueryResult(BaseModel):
    """一次透镜查询的完整结果与自证字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lens: str = Field(pattern="^(AS_KNOWN|ANNOTATED)$")
    keywords: tuple[str, ...]
    hits: tuple[LensHit, ...]
    as_of_us: int | None = None
    candidate_postings_touched: int = Field(ge=0)
    overlay_postings_touched: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_lens(self) -> "LensQueryResult":
        if self.lens not in _VALID_LENSES:
            raise ValueError(f"unknown lens: {self.lens!r}")
        return self

    @property
    def object_ids(self) -> tuple[str, ...]:
        return tuple(hit.object_id for hit in self.hits)


class ProjectionMetrics(BaseModel):
    """投影代价度量（用于量化"增量投影 vs 全量重建"的真实 I/O 差异）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    indexed_facts: int = Field(ge=0)
    base_postings: int = Field(ge=0)
    overlay_postings_written: int = Field(ge=0)
    annotations_attached: int = Field(ge=0)
    naive_rebuild_postings: int = Field(ge=0)
    saved_postings: int = Field(ge=0)
    saved_ratio: float = Field(ge=0.0, le=1.0)
    base_index_sha256: str = Field(min_length=64)

    @model_validator(mode="after")
    def validate_arithmetic(self) -> "ProjectionMetrics":
        if self.saved_postings != max(0, self.naive_rebuild_postings - self.overlay_postings_written):
            raise ValueError("saved_postings must equal naive_rebuild - overlay_written")
        if self.saved_ratio > 0.0 and self.naive_rebuild_postings == 0:
            raise ValueError("saved_ratio must be 0 when there is nothing to rebuild")
        return self


@dataclass(slots=True)
class _Fact:
    object_id: str
    learned_us: int
    tokens: frozenset[str]


@dataclass(slots=True)
class _Annotation:
    annotation_id: str
    target_object_id: str
    statement: str
    slot: str
    invalidating: bool
    annotated_us: int
    tokens: frozenset[str] = field(default_factory=frozenset)


class DualLensVirtualIndexProjector:
    """双透镜虚拟索引投影器：基底共享 + 注解增量，读面零全量重建。"""

    def __init__(
        self,
        *,
        tokenizer: Callable[[str], set[str]] | None = None,
    ) -> None:
        self._tokenize = tokenizer or tokenize_cjk_overlapping
        self._facts: dict[str, _Fact] = {}
        self._base_postings: dict[str, set[str]] = {}
        self._overlay_postings: dict[str, set[str]] = {}
        self._annotations: dict[str, _Annotation] = {}
        self._annotations_by_target: dict[str, list[str]] = {}
        self._invalidating_by_target: dict[str, set[str]] = {}
        self._overlay_postings_written = 0
        self._base_frozen_sha256: str | None = None
        self._base_snapshot: dict[str, frozenset[str]] | None = None

    # ------------------------------------------------------------------
    # 基底索引
    # ------------------------------------------------------------------

    def index_fact(
        self,
        object_id: str,
        text: str,
        *,
        learned_us: int,
    ) -> int:
        """索引一条历史事实，返回其新增基底 posting 数（幂等：重复登记同文返回 0）。"""

        if not object_id:
            raise ValueError("object_id must be non-empty")
        tokens = frozenset(self._tokenize(text))
        existing = self._facts.get(object_id)
        if existing is not None:
            if existing.tokens != tokens:
                raise ValueError(
                    f"fact {object_id!r} already indexed with different content: "
                    "历史事实在索引层同样不可改写"
                )
            return 0
        self._facts[object_id] = _Fact(
            object_id=object_id,
            learned_us=int(learned_us),
            tokens=tokens,
        )
        for token in tokens:
            bucket = self._base_postings.get(token)
            if bucket is None:
                self._base_postings[token] = {object_id}
            else:
                bucket.add(object_id)
        return len(tokens)

    def freeze_base(self) -> str:
        """冻结基底索引并返回其 SHA-256（历史不可篡改的索引层锚点）。"""

        digest = hashlib.sha256()
        for token in sorted(self._base_postings):
            digest.update(token.encode("utf-8"))
            digest.update(b"\x00")
            for object_id in sorted(self._base_postings[token]):
                digest.update(object_id.encode("utf-8"))
                digest.update(b"\x1f")
            digest.update(b"\x1e")
        self._base_frozen_sha256 = digest.hexdigest()
        self._base_snapshot = {
            token: frozenset(objects) for token, objects in self._base_postings.items()
        }
        return self._base_frozen_sha256

    @property
    def base_index_sha256(self) -> str:
        if self._base_frozen_sha256 is None:
            return self.freeze_base()
        return self._base_frozen_sha256

    def base_compatible_with_frozen(self) -> bool:
        """基底是否与冻结快照逐字节一致（挂注解绝不允许污染基底）。"""

        if self._base_snapshot is None:
            return True
        if set(self._base_snapshot) != set(self._base_postings):
            return False
        for token, objects in self._base_snapshot.items():
            if frozenset(self._base_postings[token]) != objects:
                return False
        return True

    # ------------------------------------------------------------------
    # 注解增量
    # ------------------------------------------------------------------

    def attach_annotation(
        self,
        annotation_id: str,
        *,
        target_object_id: str,
        statement: str,
        slot: str,
        annotated_us: int,
        invalidating: bool = True,
    ) -> int:
        """挂载外挂注解：只写增量 posting，返回本次新增增量 posting 数。"""

        if annotation_id in self._annotations:
            existing = self._annotations[annotation_id]
            if (
                existing.target_object_id != target_object_id
                or existing.statement != statement
            ):
                raise ValueError(
                    f"annotation {annotation_id!r} replay conflicts with the ledger"
                )
            return 0
        if target_object_id not in self._facts:
            raise KeyError(f"unknown target fact: {target_object_id!r}")

        tokens = frozenset(self._tokenize(statement))
        annotation = _Annotation(
            annotation_id=annotation_id,
            target_object_id=target_object_id,
            statement=statement,
            slot=slot,
            invalidating=invalidating,
            annotated_us=int(annotated_us),
            tokens=tokens,
        )
        self._annotations[annotation_id] = annotation
        self._annotations_by_target.setdefault(target_object_id, []).append(annotation_id)
        if invalidating:
            self._invalidating_by_target.setdefault(target_object_id, set()).add(annotation_id)

        written = 0
        for token in tokens:
            bucket = self._overlay_postings.get(token)
            if bucket is None:
                self._overlay_postings[token] = {target_object_id}
                written += 1
            elif target_object_id not in bucket:
                bucket.add(target_object_id)
                written += 1
        self._overlay_postings_written += written
        return written

    def attach_annotations(self, annotations: Iterable[dict[str, object]]) -> int:
        total = 0
        for item in annotations:
            total += self.attach_annotation(
                str(item["annotation_id"]),
                target_object_id=str(item["target_object_id"]),
                statement=str(item["statement"]),
                slot=str(item["slot"]),
                annotated_us=int(item["annotated_us"]),
                invalidating=bool(item.get("invalidating", True)),
            )
        return total

    # ------------------------------------------------------------------
    # 双透镜查询
    # ------------------------------------------------------------------

    def query(
        self,
        keywords: Sequence[str],
        *,
        lens: str = AS_KNOWN,
        as_of_us: int | None = None,
        limit: int = 20,
    ) -> LensQueryResult:
        """按透镜检索：两条透镜返回**同一组候选事实**，ANNOTATED 额外贴注解标记。"""

        if lens not in _VALID_LENSES:
            raise ValueError(f"unknown lens: {lens!r}")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if as_of_us is not None and as_of_us < 0:
            raise ValueError("as_of_us must be >= 0")

        query_tokens: set[str] = set()
        for keyword in keywords:
            query_tokens |= self._tokenize(keyword)

        scores: dict[str, int] = {}
        matched: dict[str, set[str]] = {}
        touched = 0
        overlay_touched = 0
        for token in query_tokens:
            base_bucket = self._base_postings.get(token)
            if base_bucket:
                touched += len(base_bucket)
                for object_id in base_bucket:
                    fact = self._facts[object_id]
                    if as_of_us is not None and fact.learned_us > as_of_us:
                        continue
                    scores[object_id] = scores.get(object_id, 0) + 1
                    matched.setdefault(object_id, set()).add(token)
            if lens == ANNOTATED:
                overlay_bucket = self._overlay_postings.get(token)
                if overlay_bucket:
                    overlay_touched += len(overlay_bucket)
                    for object_id in overlay_bucket:
                        fact = self._facts[object_id]
                        if as_of_us is not None and fact.learned_us > as_of_us:
                            continue
                        scores[object_id] = scores.get(object_id, 0) + 1
                        matched.setdefault(object_id, set()).add(token)

        hits: list[LensHit] = []
        for object_id, score in scores.items():
            annotation_ids: tuple[str, ...] = ()
            invalidated_by: tuple[str, ...] = ()
            if lens == ANNOTATED:
                annotation_ids = tuple(self._annotations_by_target.get(object_id, ()))
                invalidated_by = tuple(
                    sorted(self._invalidating_by_target.get(object_id, ()))
                )
            hits.append(
                LensHit(
                    object_id=object_id,
                    score=score,
                    matched_terms=tuple(sorted(matched[object_id])),
                    annotation_ids=annotation_ids,
                    invalidated_by=invalidated_by,
                    learned_us=self._facts[object_id].learned_us,
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.learned_us, hit.object_id))
        return LensQueryResult(
            lens=lens,
            keywords=tuple(keywords),
            hits=tuple(hits[:limit]),
            as_of_us=as_of_us,
            candidate_postings_touched=touched,
            overlay_postings_touched=overlay_touched,
        )

    def assert_lens_consistency(self, keywords: Sequence[str], *, limit: int = 50) -> bool:
        """断言两条透镜的**事实集合**完全一致（注解只加语义，绝不增删历史事实）。"""

        as_known = set(self.query(keywords, lens=AS_KNOWN, limit=limit).object_ids)
        annotated = set(self.query(keywords, lens=ANNOTATED, limit=limit).object_ids)
        return as_known == annotated

    # ------------------------------------------------------------------
    # 只读视图与度量
    # ------------------------------------------------------------------

    def annotations(self) -> tuple[_Annotation, ...]:
        return tuple(self._annotations.values())

    def fact_count(self) -> int:
        return len(self._facts)

    def metrics(self) -> ProjectionMetrics:
        naive = sum(len(bucket) for bucket in self._base_postings.values())
        saved = max(0, naive - self._overlay_postings_written)
        ratio = (saved / naive) if naive else 0.0
        return ProjectionMetrics(
            indexed_facts=len(self._facts),
            base_postings=len(self._base_postings),
            overlay_postings_written=self._overlay_postings_written,
            annotations_attached=len(self._annotations),
            naive_rebuild_postings=naive,
            saved_postings=saved,
            saved_ratio=max(0.0, min(1.0, ratio)),
            base_index_sha256=self.base_index_sha256,
        )
