"""AIOS 3.0 M5 世界装配与证据闭包工具箱 (Life World Kit).

本模块是 M5 里程碑（工单 6~10）共用的**世界装配底座 + 证据拓扑基准器**，服务于：

1. **装配（Build）**：以确定性种子把"四大宪法级剧情线"（老王诈骗案 / 妈妈生日礼物案 /
   熬夜早搏因果共振案 / 三年感情隐性因果案）连同海量高熵日常噪声流一次性灌入真实
   ``SQLiteWorldStore``，供检索、维度、人设、决策、战训各战队共用同一份可复现世界；
2. **基准（Oracle）**：提供**不依赖任何索引**的暴力证据闭包 ``exhaustive_reference_closure``，
   作为检索召回率的"真值裁判"——检索路径必须与它逐一对齐，而不是自己给自己打分；
3. **度量（Meter）**：提供与 ``aios_core.operations.world_operator.estimate_token_count``
   完全一致的 Token 估算口径，保证"省 Token"结论可被独立复算。

设计铁律：
- 工具箱**只读**世界（装配走官方 ``commit`` 通道，其它操作不写库）；
- 闭包与度量口径必须与在线检索索引**同构但不同源**（索引走倒排，闭包走全表扫描），
  两者的差异才能暴露索引漏召回，构成真正的差分测试。
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping, Sequence

from aios_core.simulation.massive_life_bench import (
    MassiveBenchStats,
    populate_massive_world,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

#: 单次 Token 估算口径：与 world_operator.estimate_token_count 保持一致（1 token ≈ 3.2 字符）。
CHARS_PER_TOKEN = 3.2

#: 剧情线归类的显式主键清单（剧情对象本身）。
WANG_FRAUD_CORE: frozenset[str] = frozenset(
    {
        "ent_old_wang",
        "rel_user_wang",
        "obs_wang_loan_contract",
        "obs_wang_delay_msg",
        "obs_wang_fight_call",
        "obs_wang_court_verdict",
        "evset_wang_case",
        "anchor_wang_fraud_timeline",
        "claim_wang_is_fraudster",
    }
)

MOM_GIFT_CORE: frozenset[str] = frozenset(
    {
        "ent_mom",
        "rel_user_mom",
        "obs_mom_gift_2023",
        "obs_mom_gift_2024",
        "obs_mom_gift_2025",
        "obs_mom_health_knee_2026",
        "evset_mom_gifts",
        "anchor_mom_birthday_gifts",
        "claim_mom_gift_preference",
    }
)

HEALTH_RESONANCE_CORE: frozenset[str] = frozenset(
    {
        "obs_work_late_night_0",
        "obs_work_late_night_1",
        "obs_work_late_night_2",
        "obs_bio_arrhythmia_0",
        "obs_bio_arrhythmia_1",
        "obs_bio_arrhythmia_2",
        "evset_health_overtime_resonance",
        "anchor_overtime_arrhythmia_resonance",
        "claim_overtime_arrhythmia_causality",
    }
)

ROMANCE_CORE: frozenset[str] = frozenset(
    {
        "ent_xiao_lin",
        "obs_romance_start",
        "obs_romance_fight",
        "obs_romance_breakup",
        "evset_romance_timeline",
        "anchor_romance_xiao_lin",
        "claim_romance_status",
    }
)

#: 海量日常噪声流前缀（既不进证据集、也不进任何剧情线，用于检验检索的抗噪能力）。
NOISE_PREFIXES: tuple[str, ...] = (
    "obs_bio_stream_",
    "obs_chat_stream_",
    "obs_finance_stream_",
)


def estimate_tokens(text_or_obj: Any) -> int:
    """与在线操作原语完全一致的 Token 估算口径。"""
    if text_or_obj is None:
        return 0
    if isinstance(text_or_obj, str):
        content = text_or_obj
    else:
        try:
            content = json.dumps(text_or_obj, ensure_ascii=False, default=str)
        except Exception:  # pragma: no cover - 兜底防御
            content = str(text_or_obj)
    return max(1, math.ceil(len(content) / CHARS_PER_TOKEN))


def iter_reference_ids(node: Any) -> Iterator[str]:
    """通用引用抽取器。

    与倒排索引 ``aios_core.query.search._iter_ref_ids`` 采用**同一约定**：
    一个 dict 同时带有 ``object_id`` 与 ``revision`` 字段即视为一条引用边
    （这正是 ``ObjectRef`` / ``SourceRef`` 的序列化形状）。
    """
    if isinstance(node, dict):
        object_id = node.get("object_id")
        if isinstance(object_id, str) and "revision" in node:
            yield object_id
        for value in node.values():
            yield from iter_reference_ids(value)
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            yield from iter_reference_ids(item)


def reference_edges(payload: Mapping[str, Any]) -> frozenset[str]:
    """抽取单条载荷的全部出边（去重后的目标 object_id 集合）。"""
    return frozenset(iter_reference_ids(dict(payload)))


@dataclass(frozen=True)
class StoryIndex:
    """剧情线 → 对象 id 归属索引（用于召回率基准、注入校验与取证）。"""

    wang_fraud: frozenset[str] = WANG_FRAUD_CORE
    mom_gifts: frozenset[str] = MOM_GIFT_CORE
    health_resonance: frozenset[str] = HEALTH_RESONANCE_CORE
    romance: frozenset[str] = ROMANCE_CORE

    def core_ids(self) -> frozenset[str]:
        """全部剧情线核心对象 id 的并集。"""
        return self.wang_fraud | self.mom_gifts | self.health_resonance | self.romance

    def story_of(self, object_id: str) -> str | None:
        """返回对象所属剧情线代号（噪声流返回 ``None``）。"""
        if object_id in self.wang_fraud:
            return "wang_fraud"
        if object_id in self.mom_gifts:
            return "mom_gifts"
        if object_id in self.health_resonance:
            return "health_resonance"
        if object_id in self.romance:
            return "romance"
        return None

    def lineage_members(self, kind: str) -> frozenset[str]:
        """按前缀返回该剧情线的**全部**成员（含编号成员，如 ``obs_bio_arrhythmia_*``）。"""
        prefix_map = {
            "wang_fraud": ("obs_wang_", "evset_wang_", "anchor_wang_", "claim_wang_"),
            "mom_gifts": ("obs_mom_", "evset_mom_", "anchor_mom_", "claim_mom_"),
            "health_resonance": (
                "obs_work_late_night_",
                "obs_bio_arrhythmia_",
                "evset_health_",
                "anchor_overtime_",
                "claim_overtime_",
            ),
            "romance": ("obs_romance_", "evset_romance_", "anchor_romance_", "claim_romance_"),
        }
        return frozenset(prefix_map.get(kind, ()))

    @staticmethod
    def is_noise(object_id: str) -> bool:
        """判定是否为海量日常噪声流对象。"""
        return object_id.startswith(NOISE_PREFIXES)


@dataclass
class LifeWorldHandles:
    """装配完成后的世界句柄：实体坐标 + 剧情线索引 + 统计口径。"""

    store: SQLiteWorldStore
    stats: MassiveBenchStats
    entity_ids: dict[str, str]
    stories: StoryIndex = field(default_factory=StoryIndex)
    seeded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    build_ms: float = 0.0
    total_objects: int = 0

    # ---- 基础读接口 -------------------------------------------------------
    def payload(self, object_id: str) -> dict:
        """读取最新可见载荷（不存在时抛 StoreError，交由调用方处理）。"""
        return self.store.get_payload(object_id)

    def payloads(self, object_ids: Iterable[str]) -> list[dict]:
        """批量读取载荷，自动跳过不存在/已裁剪对象，保持输入顺序。"""
        out: list[dict] = []
        for oid in object_ids:
            try:
                out.append(self.store.get_payload(oid))
            except Exception:
                continue
        return out

    def tokens_of(self, object_ids: Iterable[str]) -> int:
        """估算一组对象物化进 Prompt 的 Token 代价。"""
        return sum(estimate_tokens(p) for p in self.payloads(object_ids))

    def entity(self, key: str) -> str:
        """按语义键取实体 id（``user`` / ``old_wang`` / ``mom`` / ``xiao_lin``）。"""
        return self.entity_ids[key]

    # ---- 证据闭包基准 -----------------------------------------------------
    def closure(self, seed_ids: Sequence[str], *, max_depth: int = 3) -> frozenset[str]:
        """以暴力全表扫描计算种子集合的证据拓扑闭包（真值裁判，不依赖任何索引）。"""
        return exhaustive_reference_closure(self.store, seed_ids, max_depth=max_depth)


def build_canonical_life_world(
    store: SQLiteWorldStore,
    *,
    target_count: int = 2400,
    seed: int = 42,
    batch_size: int = 500,
) -> LifeWorldHandles:
    """装配四大剧情线 + 高熵噪声流的可复现世界。

    ``target_count`` 为世界对象总量（剧情对象优先装配，其余配额由噪声流填充），
    因此同一 ``seed`` 下世界的**拓扑骨架恒等**，只有噪声流的数值细节变化。
    """
    t0 = time.perf_counter()
    stats = populate_massive_world(
        store,
        target_count=target_count,
        batch_size=batch_size,
        seed=seed,
    )
    build_ms = (time.perf_counter() - t0) * 1000.0
    payloads = store.list_payloads()
    return LifeWorldHandles(
        store=store,
        stats=stats,
        entity_ids={
            "user": "ent_user_me",
            "old_wang": "ent_old_wang",
            "mom": "ent_mom",
            "xiao_lin": "ent_xiao_lin",
        },
        seeded_at=datetime.now(UTC),
        build_ms=build_ms,
        total_objects=len(payloads),
    )


def _payload_graph(store: SQLiteWorldStore) -> dict[str, frozenset[str]]:
    """一次性全表扫描，构建 object_id → 出边集合 的引用图。"""
    graph: dict[str, frozenset[str]] = {}
    for payload in store.list_payloads():
        oid = payload.get("object_id")
        if not isinstance(oid, str):
            continue
        graph[oid] = reference_edges(payload)
    return graph


def exhaustive_reference_closure(
    store: SQLiteWorldStore,
    seed_ids: Sequence[str],
    *,
    max_depth: int = 3,
) -> frozenset[str]:
    """暴力证据闭包（真值裁判）。

    语义：从 ``seed_ids`` 出发，在**无向**引用图上做深度受限的广度优先扩张——
    既包含种子所引用的对象，也包含引用了种子的对象，因为证据链天生双向可达
    （实体 ← 事件锚点 → 证据集 → 观测微切片）。

    实现刻意**不触碰检索索引**：只调用 ``list_payloads`` 全表扫描 + 自建邻接表，
    从而与"倒排索引 + 超链接跳转"的在线拓扑下钻形成两条独立代码路径，
    二者结果必须逐一对齐（差分校验）。
    """
    graph = _payload_graph(store)
    if not graph:
        return frozenset()

    inbound: dict[str, set[str]] = {}
    for src, targets in graph.items():
        for dst in targets:
            inbound.setdefault(dst, set()).add(src)

    visited: set[str] = set()
    frontier: list[str] = [sid for sid in seed_ids if sid in graph]
    visited.update(frontier)
    depth = 0
    while frontier and depth < max_depth:
        nxt: list[str] = []
        for node in frontier:
            neighbours = set(graph.get(node, frozenset())) | inbound.get(node, set())
            for nb in neighbours:
                if nb not in visited:
                    visited.add(nb)
                    nxt.append(nb)
        frontier = nxt
        depth += 1
    return frozenset(visited)


def minimal_spanning_facts(
    graph: Mapping[str, frozenset[str]],
    target_ids: Iterable[str],
    *,
    limit: int | None = None,
) -> list[str]:
    """在引用图上挑出"最省 Token 的覆盖集"：优先保留出边最多（信息密度最高）的节点。

    用于给拓扑下钻路径给出"该先看哪几片微切片"的静态排序建议；
    ``limit`` 为覆盖上限，``None`` 表示不截断。
    """
    ranked = sorted(
        (oid for oid in target_ids if oid in graph),
        key=lambda oid: (-len(graph[oid]), oid),
    )
    return ranked if limit is None else ranked[:limit]


def noise_ratio(stats: MassiveBenchStats) -> float:
    """噪声流占比（用于校验世界是否真的"高熵"而非剧情自嗨）。"""
    total = max(1, stats.total_observations)
    noise = max(0, stats.total_observations - len(WANG_FRAUD_CORE) - len(MOM_GIFT_CORE) - len(HEALTH_RESONANCE_CORE) - len(ROMANCE_CORE))
    return noise / total
