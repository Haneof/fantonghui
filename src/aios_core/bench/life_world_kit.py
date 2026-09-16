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
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Iterator, Mapping, Sequence, Tuple

from aios_core.contracts.ids import new_operation_id
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.contracts.enums import SourceClass
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


# ===========================================================================
# 跨域异常窗口装配器（供维度演化 / 人设姿态 / 战训考场共用）
# ===========================================================================
@dataclass(frozen=True)
class AnomalyWindow:
    """一条"连续 N 天 × 多物理域"的真实异常窗口。"""

    profile: str
    days: Tuple[datetime, ...]
    per_day: Mapping[str, Mapping[str, Tuple[str, ...]]]
    observation_ids: Tuple[str, ...]
    evidence_refs: Tuple[ObjectRef, ...]

    def day_count(self) -> int:
        """窗口天数。"""
        return len(self.days)

    def domains(self) -> frozenset[str]:
        """窗口内点亮过的物理域集合。"""
        out: set[str] = set()
        for domains in self.per_day.values():
            out.update(domains)
        return frozenset(out)

    def payloads(self, store: SQLiteWorldStore) -> list[dict]:
        """取回窗口内全部观测载荷（按对象 id 顺序）。"""
        return [store.get_payload(oid) for oid in self.observation_ids]


#: 窗口配方：profile → 每日 (物理域 → 观测模板) 与主题人物
_WINDOW_RECIPES: Mapping[str, Mapping[str, Any]] = {
    "burnout": {
        "subject_id": "ent_user_me",
        "domains": {
            "health": (
                "biometrics",
                "json",
                '{{"resting_hr": {hr}, "hrv": {hrv}, "note": "凌晨 02:10 静息心率骤升，HRV 显著塌陷"}}',
            ),
            "work": (
                "work_log",
                "text",
                "连续第 {day_index} 天在工位加班至凌晨 02:30 提交版本，全天会议 4 场，未离开写字楼。",
            ),
            "finance": (
                "transaction",
                "text",
                "凌晨 01:40 咖啡与外卖异常消费 {amount} 元（远高于日常均值 32 元）。",
            ),
        },
    },
    "credit": {
        "subject_id": "ent_old_wang",
        "domains": {
            "finance": (
                "transaction",
                "text",
                "老王的项目方大额资金转出 {amount} 元，同日又有 2 笔小额过账回流，账户流水异常。",
            ),
            "social": (
                "chat",
                "text",
                "老王微信：'再宽限我{day_index}天，下周三连本带息打过去'（与此前 3 次承诺措辞几乎一致）。",
            ),
            "behavior": (
                "location",
                "text",
                "老王临时变更常驻办公地点并多次拒接视频核验，行为轨迹与承诺不符。",
            ),
        },
    },
    "parent_health": {
        "subject_id": "ent_mom",
        "domains": {
            "health": (
                "medical",
                "text",
                "母亲膝关节受凉疼痛复发，晨起上下楼困难，自述膝盖像被冷风灌透，热敷后略有缓解。",
            ),
            "social": (
                "chat",
                "text",
                "妈妈微信语音：'今天膝盖又疼了第 {day_index} 天，别买那些又要灌水又要搬的东西'。",
            ),
            "behavior": (
                "location",
                "text",
                "母亲连续减少外出散步时长（{day_index} 天来最低），居家活动为主。",
            ),
        },
    },
}


def build_anomaly_window(
    store: SQLiteWorldStore,
    *,
    profile: str = "burnout",
    start: datetime = datetime(2026, 9, 10, 2, 0, tzinfo=UTC),
    days: int = 3,
    seed: int = 7,
) -> AnomalyWindow:
    """装配一条连续 ``days`` 天、每天多物理域的异常观测窗口并真实入库。

    这是维度层"门槛一"的证据来源：窗口内每个物理域都有真实 ``Observation`` 对象，
    提炼出的高阶维度因而携带可回指的物证指针（而不是测试里的字符串常量）。
    """
    recipe = _WINDOW_RECIPES[profile]
    subject_id = str(recipe["subject_id"])
    domains: Mapping[str, Any] = recipe["domains"]
    rng = random.Random(seed)
    start = start if start.tzinfo else start.replace(tzinfo=UTC)

    objects: list[Any] = []
    per_day: dict[str, dict[str, tuple[str, ...]]] = {}
    all_ids: list[str] = []

    day_starts: list[datetime] = []
    for day_offset in range(days):
        day_anchor = start + timedelta(days=day_offset)
        day_starts.append(day_anchor)
        key = day_anchor.date().isoformat()
        per_day[key] = {}
        for domain_index, (domain, template) in enumerate(domains.items()):
            source_kind, modality, text_template = template
            ts = day_anchor + timedelta(hours=domain_index) + timedelta(minutes=rng.randint(0, 45))
            value = text_template.format(
                day_index=day_offset + 1,
                hr=rng.randint(96, 118),
                hrv=rng.randint(14, 22),
                amount=rng.choice([138, 156, 189, 213]),
            )
            # id 内嵌自然日，保证同一世界内多条窗口（主组/控制组）互不覆盖
            object_id = f"obs_window_{profile}_{domain}_{ts.date().isoformat()}"
            objects.append(
                Observation(
                    object_id=object_id,
                    subject_id=subject_id,
                    revision=1,
                    source_kind=source_kind,
                    modality=modality,
                    value=value,
                    occurred=TemporalExtent.point(ts),
                    learned_at=ts,
                    recorded_at=ts,
                    created_by="m5_anomaly_window",
                )
            )
            per_day[key][domain] = (object_id,)
            all_ids.append(object_id)

    operation = OperationRequest(
        operation_id=new_operation_id(),
        operation_name="sim.m5.anomaly_window",
        expected_world_revision=store.current_world_revision(),
        reason=f"装配跨域异常窗口 profile={profile} days={days}",
        idempotency_key=f"m5_window_{profile}_{days}_{seed}_{start.date().isoformat()}",
        source_class=SourceClass.AI_COGNITION,
    )
    store.commit(objects, operation)

    return AnomalyWindow(
        profile=profile,
        days=tuple(day_starts),
        per_day=per_day,
        observation_ids=tuple(all_ids),
        evidence_refs=tuple(ObjectRef(object_id=oid, revision=1) for oid in all_ids),
    )


def build_anomaly_windows(
    store: SQLiteWorldStore,
    *,
    start: datetime = datetime(2026, 9, 10, 2, 0, tzinfo=UTC),
    days: int = 3,
    seed: int = 7,
) -> dict[str, AnomalyWindow]:
    """一次性装配三类跨域异常窗口：过劳 / 信用 / 亲人健康。"""
    return {
        profile: build_anomaly_window(store, profile=profile, start=start, days=days, seed=seed)
        for profile in _WINDOW_RECIPES
    }
