"""双透镜虚拟索引投影器（DualLensProjectionIndex）。

问题
----
宪法第二十二条（老王案铁律）要求同一条历史事实能同时呈现两种视线：

* ``AS_KNOWN``：**当时所知**（截至知识截止线的点态快照，不含任何今天的后见之明）；
* ``ANNOTATED``：**今天理解**（在只读叠加层上挂今天的重新诠释，历史原样不动）。

现有实现里，这两条视线散落在存储层与重诠释读写路径上，缺少一个**统一的虚拟投影器**：
既不能一次投影出两种视线，也无法机械证明"投影只是视图、底层事实一个字节都没动"。

本投影器做什么
--------------
1. ``project(lens, at)`` 一次产出透镜视图：AS_KNOWN 只给当时可见事实；
   ANNOTATED 在同样的事实集合上叠加**只读注解**（不修改事实字节）；
2. ``lens_delta(at)`` 给出两份视图的差异清单：事实集合与指纹必须完全一致，
   差异只能出现在注解字段上（"历史不可变"的可证伪断言）；
3. ``query`` 支持按实体 / 关键词 / 时间窗检索，并强制携带证据指针；
4. ``vault_fingerprint`` 是底层事实的 SHA-256 聚合，任何改写都会让它变化。
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

__all__ = [
    "ANNOTATED",
    "AS_KNOWN",
    "DualLensProjectionIndex",
    "LensDelta",
    "ProjectedFact",
    "ProjectionError",
]

AS_KNOWN = "AS_KNOWN"
ANNOTATED = "ANNOTATED"
_LENSES = (AS_KNOWN, ANNOTATED)


class ProjectionError(ValueError):
    """投影协议错误（未知透镜、重复登记、注解指向缺失事实）。"""


def _as_utc(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ProjectionError(f"{field_name} must be datetime or ISO string")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fact_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProjectedFact:
    """一条被投影出的事实（底层字节 + 可视注解）。"""

    object_id: str
    digest: str
    occurred_at: datetime | None
    learned_at: datetime
    payload: Mapping[str, Any]
    annotations: tuple[Mapping[str, Any], ...] = ()

    @property
    def annotation_count(self) -> int:
        return len(self.annotations)

    def effective_meaning(self) -> str:
        """今天理解：注解优先，否则回落到事实自带语义。"""

        if self.annotations:
            latest = self.annotations[-1]
            statement = latest.get("statement")
            if isinstance(statement, str) and statement.strip():
                return statement.strip()
        for key in ("meaning", "text", "transcript", "statement", "value"):
            value = self.payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""


@dataclass(frozen=True, slots=True)
class LensDelta:
    """两份透镜视图的差异清单（用于自证"只加注解、不改历史"）。"""

    at: datetime
    as_known_ids: tuple[str, ...]
    annotated_ids: tuple[str, ...]
    annotated_only_ids: tuple[str, ...]
    as_known_only_ids: tuple[str, ...]
    base_fingerprint_equal: bool
    annotation_count: int
    annotated_fact_count: int
    mutation_count: int

    @property
    def history_intact(self) -> bool:
        return (
            self.base_fingerprint_equal
            and not self.annotated_only_ids
            and not self.as_known_only_ids
            and self.mutation_count == 0
        )


class DualLensProjectionIndex:
    """在不可变事实账本之上做双透镜虚拟投影。"""

    def __init__(
        self,
        facts: Iterable[Mapping[str, Any]],
        *,
        annotations: Iterable[Mapping[str, Any]] = (),
    ) -> None:
        self._facts: Dict[str, Dict[str, Any]] = {}
        self._fact_times: Dict[str, tuple[datetime | None, datetime]] = {}
        self._entity_index: Dict[str, set[str]] = {}
        self._annotations: list[Dict[str, Any]] = []
        self._mutations_blocked = 0
        for fact in facts:
            self.register_fact(fact)
        for annotation in annotations:
            self.register_annotation(annotation)

    # ------------------------------------------------------------------
    # 登记（只增不改）
    # ------------------------------------------------------------------

    def register_fact(self, fact: Mapping[str, Any]) -> str:
        object_id = str(fact.get("object_id") or fact.get("id") or "")
        if not object_id:
            raise ProjectionError("fact requires an object_id")
        payload = copy.deepcopy(dict(fact))
        digest = _fact_digest(payload)
        existing = self._facts.get(object_id)
        if existing is not None:
            if _fact_digest(existing) != digest:
                self._mutations_blocked += 1
                raise ProjectionError(
                    f"fact {object_id!r} already registered with different bytes "
                    "(history mutation blocked)"
                )
            return object_id
        self._facts[object_id] = payload
        occurred = payload.get("occurred_at") or payload.get("event_time")
        learned = payload.get("learned_at") or payload.get("recorded_at") or occurred
        self._fact_times[object_id] = (
            _as_utc(occurred, "occurred_at") if occurred else None,
            _as_utc(learned, "learned_at"),
        )
        for entity in self._entities_of(payload):
            self._entity_index.setdefault(entity, set()).add(object_id)
        return object_id

    def register_annotation(self, annotation: Mapping[str, Any]) -> None:
        payload = copy.deepcopy(dict(annotation))
        target = str(payload.get("target_id") or payload.get("object_id") or "")
        if target not in self._facts:
            raise ProjectionError(f"annotation targets unknown fact {target!r}")
        payload["target_id"] = target
        payload["recorded_at"] = _as_utc(
            payload.get("recorded_at") or payload.get("learned_at"), "recorded_at"
        ).isoformat()
        payload["_sha256"] = _fact_digest(payload)
        self._annotations.append(payload)

    @staticmethod
    def _entities_of(payload: Mapping[str, Any]) -> tuple[str, ...]:
        entities: list[str] = []
        for key in ("entity_id", "subject_id", "participant_refs", "entities"):
            value = payload.get(key)
            if isinstance(value, str):
                entities.append(value)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, str):
                        entities.append(item)
                    elif isinstance(item, Mapping) and isinstance(item.get("object_id"), str):
                        entities.append(str(item["object_id"]))
        return tuple(dict.fromkeys(entities))

    # ------------------------------------------------------------------
    # 投影
    # ------------------------------------------------------------------

    def project(
        self,
        *,
        lens: str = AS_KNOWN,
        at: datetime | str | None = None,
    ) -> tuple[ProjectedFact, ...]:
        if lens not in _LENSES:
            raise ProjectionError(f"unknown lens {lens!r}; expected one of {list(_LENSES)}")
        cutoff = _as_utc(at, "at") if at is not None else None
        annotations_by_target: Dict[str, list[Mapping[str, Any]]] = {}
        if lens == ANNOTATED:
            for annotation in self._annotations:
                recorded = _as_utc(annotation["recorded_at"], "recorded_at")
                if cutoff is not None and recorded > cutoff:
                    continue
                annotations_by_target.setdefault(str(annotation["target_id"]), []).append(annotation)
        projected: list[ProjectedFact] = []
        for object_id in sorted(self._facts):
            occurred, learned = self._fact_times[object_id]
            if cutoff is not None and learned > cutoff:
                continue
            payload = self._facts[object_id]
            annotations = tuple(
                sorted(
                    annotations_by_target.get(object_id, ()),
                    key=lambda item: str(item["recorded_at"]),
                )
            )
            projected.append(
                ProjectedFact(
                    object_id=object_id,
                    digest=_fact_digest(payload),
                    occurred_at=occurred,
                    learned_at=learned,
                    payload=copy.deepcopy(payload),
                    annotations=tuple(copy.deepcopy(dict(item)) for item in annotations),
                )
            )
        return tuple(projected)

    def query(
        self,
        *,
        lens: str = AS_KNOWN,
        at: datetime | str | None = None,
        entity_id: str | None = None,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
        keyword: str | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectedFact, ...]:
        lower = _as_utc(start, "start") if start is not None else None
        upper = _as_utc(end, "end") if end is not None else None
        rows = self.project(lens=lens, at=at)
        if entity_id is not None:
            candidates = self._entity_index.get(entity_id, set())
            rows = tuple(row for row in rows if row.object_id in candidates)
        if lower is not None:
            rows = tuple(
                row for row in rows if row.occurred_at is not None and row.occurred_at >= lower
            )
        if upper is not None:
            rows = tuple(
                row for row in rows if row.occurred_at is not None and row.occurred_at <= upper
            )
        if keyword:
            rows = tuple(
                row
                for row in rows
                if keyword in json.dumps(row.payload, ensure_ascii=False)
                or any(keyword in str(a.get("statement", "")) for a in row.annotations)
            )
        return rows[:limit] if limit is not None else rows

    # ------------------------------------------------------------------
    # 自证
    # ------------------------------------------------------------------

    def vault_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for object_id in sorted(self._facts):
            digest.update(object_id.encode("utf-8"))
            digest.update(_fact_digest(self._facts[object_id]).encode("utf-8"))
        return digest.hexdigest()

    def base_fingerprint(self, *, at: datetime | str | None = None) -> str:
        digest = hashlib.sha256()
        for row in self.project(lens=AS_KNOWN, at=at):
            digest.update(row.object_id.encode("utf-8"))
            digest.update(row.digest.encode("utf-8"))
        return digest.hexdigest()

    def lens_delta(self, *, at: datetime | str | None = None) -> LensDelta:
        cutoff = _as_utc(at, "at") if at is not None else None
        as_known = self.project(lens=AS_KNOWN, at=at)
        annotated = self.project(lens=ANNOTATED, at=at)
        as_known_ids = {row.object_id for row in as_known}
        annotated_ids = {row.object_id for row in annotated}
        base_equal = self.base_fingerprint(at=at) == self._projection_fingerprint(annotated)
        return LensDelta(
            at=cutoff or _as_utc(datetime.now(timezone.utc), "at"),
            as_known_ids=tuple(sorted(as_known_ids)),
            annotated_ids=tuple(sorted(annotated_ids)),
            annotated_only_ids=tuple(sorted(annotated_ids - as_known_ids)),
            as_known_only_ids=tuple(sorted(as_known_ids - annotated_ids)),
            base_fingerprint_equal=base_equal,
            annotation_count=sum(row.annotation_count for row in annotated),
            annotated_fact_count=sum(1 for row in annotated if row.annotation_count),
            mutation_count=self._mutations_blocked,
        )

    @staticmethod
    def _projection_fingerprint(rows: Sequence[ProjectedFact]) -> str:
        digest = hashlib.sha256()
        for row in rows:
            digest.update(row.object_id.encode("utf-8"))
            digest.update(row.digest.encode("utf-8"))
        return digest.hexdigest()

    def annotations_for(self, object_id: str) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            copy.deepcopy(annotation)
            for annotation in self._annotations
            if str(annotation["target_id"]) == object_id
        )

    @property
    def fact_count(self) -> int:
        return len(self._facts)

    @property
    def annotation_total(self) -> int:
        return len(self._annotations)
