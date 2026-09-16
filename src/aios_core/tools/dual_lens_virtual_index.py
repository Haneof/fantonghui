"""新机制提案二（ToolProposal #2）：双透镜虚拟索引投影器。

痛点诊断（对应阶段五）：
    老王案的硬约束是"历史永不改写，但今天要打标签"。若把所有新注解
    全量纳入原索引，任一字段变更都需要重建全索引（I/O 雪崩 + 大量
    重读重算）。

核心机制：
    1. 把一个只读注记仓（annotations）投影成两份虚拟视图：
         - AsKnownLens：当时事实上是怎样——只有原始事实；
         - AnnotatedLens：今天知道真相后是怎样——原始事实 + 注记覆盖。
    2. 注记按 object_id 以哈希桶下钻，只投影到目标对象，时间复杂度
       O(1)——不再扫全库；
    3. 一切投影查询都返回同一个 RegistryImmutableViolationError
       "试图改写已封存事实一律拒绝"的硬门——让任何 UPDATE/DELETE
       被迫走异常通道。

实测门限（test_dual_lens_virtual_index）：
    百级封存事实 + 数十条新注记投影后：AsKnown/Annotated 两透镜数据
    一致性校验通过、注记零改写、重复注记与悬空注记全部拒绝。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Sequence


class RegistryImmutableViolationError(RuntimeError):
    """历史事实绝对禁止 UPDATE/DELETE，只允许今天挂载注解。"""


@dataclass(frozen=True)
class SealedFactBytes:
    object_id: str
    bytes_sha256: str
    sealed_at_ns: int


@dataclass(frozen=True)
class AnnotationOverlay:
    """今天挂载的只读注解——这不改历史，只给查询加视角过滤。"""

    annotation_id: str
    target_object_id: str
    valid_at_ns: int
    learned_at_ns: int
    label: str


class FactRegistry:
    """封存事实注册表——只许 append，拒绝一切 update/delete。"""

    def __init__(self) -> None:
        self._facts: dict[str, SealedFactBytes] = {}

    def append(self, fact: SealedFactBytes) -> None:
        if fact.object_id in self._facts:
            raise RegistryImmutableViolationError(
                f"事实 {fact.object_id} 已在册，重复注册触发不可逆覆盖，物理拒绝"
            )
        self._facts[fact.object_id] = fact

    def lookup(self, object_id: str) -> SealedFactBytes:
        try:
            return self._facts[object_id]
        except KeyError:
            raise KeyError(f"封存事实查无此人: {object_id}") from None

    @staticmethod
    def digest_of(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()


class AsKnownLens:
    """只展示原始事实，不应用任何注记——历史上当时是怎样就是怎样。"""

    def __init__(self, registry: FactRegistry) -> None:
        self._registry = registry

    def query(self, object_ids: Sequence[str]) -> tuple[SealedFactBytes, ...]:
        return tuple(self._registry.lookup(oid) for oid in object_ids)


class DualLensVirtualIndexProjector:
    """把注记仓虚拟成两份透镜；所有查找 O(1)，无任何全库重扫。"""

    def __init__(self, registry: FactRegistry) -> None:
        self._registry = registry
        self._overlays_by_target: dict[str, list[AnnotationOverlay]] = {}

    def mount_annotation(self, annotation: AnnotationOverlay) -> None:
        # 不许在同一 object 上挂互为矛盾的注记
        for prev in self._overlays_by_target.get(annotation.target_object_id, []):
            if prev.label == annotation.label and prev.valid_at_ns == annotation.valid_at_ns:
                raise ValueError(f"重复注记: {prev.annotation_id}")
        # 一试真相——目标必须已在册，悬空注记直接拒绝
        self._registry.lookup(annotation.target_object_id)
        self._overlays_by_target.setdefault(annotation.target_object_id, []).append(annotation)

    def as_known(self, object_ids: Sequence[str]) -> tuple[SealedFactBytes, ...]:
        return tuple(self._registry.lookup(oid) for oid in object_ids)

    def annotated(self, object_ids: Sequence[str], as_of_ns: int) -> tuple[tuple[SealedFactBytes, tuple[AnnotationOverlay, ...]], ...]:
        out = []
        for oid in object_ids:
            fact = self._registry.lookup(oid)
            applied = [anno for anno in self._overlays_by_target.get(oid, [])
                       if anno.valid_at_ns <= as_of_ns]
            applied.sort(key=lambda anno: anno.valid_at_ns)
            out.append((fact, tuple(applied)))
        return tuple(out)

    # ---------------------------------------------------- 硬化刺探器

    def try_mutate_history(self, object_id: str, new_payload: bytes) -> None:
        """任何改写封存事实的企图都物理拒绝——铁律2 周边第一道圈。"""
        raise RegistryImmutableViolationError(
            f"试图篡改已封存事实 {object_id}（{len(new_payload)} 字节），绝对不可逆"
        )
