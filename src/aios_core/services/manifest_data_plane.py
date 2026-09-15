"""M1-022 · Manifest Data-Plane Builder v0——R4 §3.4 的 L0 确定性切片聚合器。

    宪法锚：§84.1 单次看盘（Single-Shot）＋ §84.2 四步序是「段落排版顺序」不是
    调用顺序（ADJ-001 裁决）＋ §86.2 只暴露 READY 任务 ＋ §86.4 物化留证可回放。

    范围闸（v0 = 数据面，待 C15 / M2-017 接管装配 K1）：
      做   → L0 机械键直查（l0_slice + M1-021 ready_view）、SlotRef 装配、
             确定性 token 估计、canonical 哈希、版本化幂等物化；
      不做 → Step-0 安全机械闸、stance 候选、L1 召回、L2 deferred、预算闸
             （这些不进 v0；缺席必须写 omissions，绝不静默伪造）。

    硬承诺：
      model_calls_per_build == 0  结构性常数（本模块不存在任何可调模型的入口）；
      queries_per_build   == 3    直查两次 + 幂等物化一次，与数据规模无关；
      同世界状态 + 同输入 ⇒ 同 canonical_hash ⇒ 同 manifest_id（重放幂等）。
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..contracts.enums_v3 import ManifestLane
from ..contracts.models_v3 import FourStepsSections, OmissionDetail, SlotRef
from ..contracts.refs import ObjectRef
from ..storage.eligibility_schema import ensure_eligibility_schema
from ..storage.manifest_schema import ensure_manifest_schema
from ..storage.sqlite_store import SQLiteWorldStore

MODEL_CALLS_PER_BUILD = 0          # 零 LLM 承诺：结构性常数，不是告警指标
QUERIES_PER_BUILD = 3              # L0 直查 + READY 直查 + 幂等物化，规模无关
ESTIMATOR_VERSION = "tok-est-v0"   # C15 接管时可换真 tokenizer，版本戳随件走

# L0 切面注册表（writer 侧契约；本平面只读）
SLICE_SELF_STATE = "self_state"                # §84.2 step1：身份切片+上次停留心智状态
SLICE_RAPPORT = "rapport"                      # §84.2 step2：DIM_AI_RAPPORT 当前值
SLICE_NOW_CONTEXT = "now_context"              # §84.3：当前时间/地点/人物/主事件
SLICE_CAPABILITY_REGISTRY = "capability_registry"  # §84.3：工具能力清单
KNOWN_SLICE_KINDS = (
    SLICE_SELF_STATE,
    SLICE_RAPPORT,
    SLICE_NOW_CONTEXT,
    SLICE_CAPABILITY_REGISTRY,
)

# v0 明文缺席声明——C15 接管前绝不伪造这两段（防静默失忆，R4 I2 omissions 铁律）
OMIT_STEP0_REASON = "reserved_for_M2-017:step0_safety_gate_not_assembled_in_v0"
OMIT_STEP3_REASON = "reserved_for_M2-017:step3_stance_candidates_not_assembled_in_v0"


# ---------------------------------------------------------------------------
# 确定性 token 估计器（v0）
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """确定性估计：CJK/全角字符一字符一 token，其余字符 ceil(n/4)。

    公式写死在版本戳 tok-est-v0 名下：同串同值，回放可复算；M2-017 换真
    tokenizer 时改 ESTIMATOR_VERSION，旧 manifest 的 token_total 依旧可解释。
    """
    if not text:
        return 0
    wide = 0
    for ch in text:
        o = ord(ch)
        if (
            0x3000 <= o <= 0x30FF      # 日文假名 + CJK 标点
            or 0x2E80 <= o <= 0x9FFF   # CJK 统一表意及部首
            or 0xAC00 <= o <= 0xD7AF   # 韩文音节
            or 0xF900 <= o <= 0xFAFF   # CJK 兼容表意
            or 0xFF00 <= o <= 0xFFEF   # 全角 ASCII
        ):
            wide += 1
    rest = len(text) - wide
    return wide + math.ceil(rest / 4)


def _canon_json(obj: Any) -> str:
    """装配平面唯一 canonical 形态：同语义 ⇒ 同字节串 ⇒ 同哈希。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 输入 / 报告
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class WakeInput:
    """一次唤醒的装配输入（§85.3 第一层：触发指针层）。"""

    subject_id: str
    wake_object_id: str
    wake_revision: int                 # 钉版：manifest 声称的是该 rev 的 wake
    wake_reason_kind: str
    lane: str                          # notify|investigate|chapter
    scene_refs: tuple[ObjectRef, ...] = ()  # §84.2 step4：wake 自带现场切片（钉版指针）
    now_utc: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.now_utc is None:
            object.__setattr__(self, "now_utc", datetime.now(timezone.utc))
        now = self.now_utc
        object.__setattr__(self, "now_utc", now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now)
        if self.lane not in {lane.value for lane in ManifestLane}:
            raise ValueError(f"lane 非法：{self.lane!r}（ManifestLane 外无车道）")
        if self.wake_revision < 1:
            raise ValueError("wake_revision 必须钉版（>=1）")
        for r in self.scene_refs:
            if r.revision is None:
                raise ValueError(f"scene ref 未钉版：{r.object_id}（L0 拒绝无版本指针）")


@dataclass
class BuildReport:
    manifest_id: str
    reused_existing: bool              # True=内容寻址幂等命中（重放未产生新行）
    sections_filled: list[str]
    ready_exposed: int
    waiting_exposed: int = 0           # G2 铁律：恒 0，非 0 即代码 bug
    capabilities_exposed: int = 0
    slices_hit: int = 0
    omissions_count: int = 0
    rows_examined_ready: int = 0       # ≤1.05×ready 的分子（索引直查返回行数）
    queries_executed: int = 0          # 结构性常数 QUERIES_PER_BUILD
    token_total: int = 0
    build_ms: float = 0.0
    world_rev: int = 0
    canonical_hash: str = ""
    model_calls_in_build: int = MODEL_CALLS_PER_BUILD


# ---------------------------------------------------------------------------
# L0 切片存储（writer 侧机械面；reader 是 builder 的两次直查之一）
# ---------------------------------------------------------------------------


class L0SliceStore:
    """（主体, 种类）→ 最新载荷。latest-per-kind 是装配平面的供给契约：

    历史在 world store，本表只承诺「按主键一次索引读拿到全部 L0 输入」。
    载荷写入侧 canonical 化，保证 token 估计与 canonical 哈希跨进程稳定。
    """

    def __init__(self, store: SQLiteWorldStore) -> None:
        self._store = store

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(self._store.db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        ensure_manifest_schema(conn)
        return conn

    def upsert(
        self,
        subject_id: str,
        slice_kind: str,
        payload: Mapping[str, Any],
        *,
        source_object_id: str,
        source_revision: int,
        freshness_at: datetime,
        slice_rev: int,
    ) -> None:
        if slice_kind not in KNOWN_SLICE_KINDS:
            raise ValueError(f"未知 L0 切片种类：{slice_kind!r}（注册表外不供给装配）")
        if source_revision < 1:
            raise ValueError("source_revision 必须钉版（>=1）")
        freshness_at = (
            freshness_at.replace(tzinfo=timezone.utc)
            if freshness_at.tzinfo is None else freshness_at
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO l0_slice VALUES (?,?,?,?,?,?,?)",
                (
                    subject_id,
                    slice_kind,
                    _canon_json(dict(payload)),
                    source_object_id,
                    source_revision,
                    freshness_at.isoformat(),
                    slice_rev,
                ),
            )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _aware(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _slot(ref: ObjectRef, *, freshness: datetime, cost: int, reason: str) -> SlotRef:
    return SlotRef(
        ref=ref,
        source="l0_slice",
        freshness_at=freshness,
        token_cost=cost,
        reason=reason,
    )


class ManifestDataPlaneBuilderV0:
    """L0 确定性切片聚合器：机械键直查 → SlotRef 段落 → 版本化幂等物化。

    只读消费面：l0_slice（本件）+ ready_view/task_proxy（M1-021，只读 JOIN，
    绝不在其 schema 上回填字段）。绝不写认知、绝不排序裁决、绝不调模型。
    """

    def __init__(self, store: SQLiteWorldStore) -> None:
        self._store = store

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(self._store.db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        ensure_eligibility_schema(conn)  # 消费 M1-021 面（只读），幂等确保在
        ensure_manifest_schema(conn)
        return conn

    def build(self, wake: WakeInput) -> BuildReport:
        t0 = time.perf_counter()
        queries = 0
        now = wake.now_utc

        with self._connect() as conn:
            # Q1：L0 切片一次 IN 直查（主键索引，规模无关）
            slice_rows = conn.execute(
                "SELECT slice_kind, payload_json, source_object_id, source_revision,"
                " freshness_at FROM l0_slice"
                " WHERE subject_id=? AND slice_kind IN (?,?,?,?)",
                (wake.subject_id, *KNOWN_SLICE_KINDS),
            ).fetchall()
            queries += 1

            # Q2：M1-021 就绪集索引 JOIN 直查；state='READY' 硬过滤是
            #     G2 waiting_tasks_exposed_to_model=0 的物理臂（连陈旧 ready_view
            #     行都穿不过这层）
            ready_rows = conn.execute(
                "SELECT tp.task_id AS task_id, rv.ready_since AS ready_since,"
                " rv.world_rev AS world_rev, rv.reason_json AS reason_json"
                "   FROM ready_view rv"
                "   JOIN task_proxy tp ON tp.task_id = rv.task_id"
                "  WHERE tp.subject_id=? AND tp.state='READY'"
                "  ORDER BY rv.ready_since, tp.task_id",
                (wake.subject_id,),
            ).fetchall()
            queries += 1

        slices = {r["slice_kind"]: r for r in slice_rows}
        omissions: list[OmissionDetail] = [
            OmissionDetail(source="l0_slice", reason=OMIT_STEP0_REASON, projected_token_cost=0),
            OmissionDetail(source="l0_slice", reason=OMIT_STEP3_REASON, projected_token_cost=0),
        ]
        for kind in KNOWN_SLICE_KINDS:
            if kind not in slices:
                omissions.append(OmissionDetail(
                    source="l0_slice",
                    reason=f"l0_slice_absent:{kind}",
                    projected_token_cost=0,
                ))

        def slice_slot(kind: str, reason: str) -> SlotRef | None:
            row = slices.get(kind)
            if row is None:
                return None
            return _slot(
                ObjectRef(object_id=row["source_object_id"], revision=row["source_revision"]),
                freshness=_aware(row["freshness_at"]),
                cost=estimate_tokens(row["payload_json"]),
                reason=reason,
            )

        # §84.2 段落排版顺序（ADJ-001：layout 规格，不是调用顺序）
        s1 = slice_slot(SLICE_SELF_STATE, "l0:self_state #84.2-step1")
        s2 = slice_slot(SLICE_RAPPORT, "l0:rapport #84.2-step2")
        s4_now = slice_slot(SLICE_NOW_CONTEXT, "l0:now_context #84.3")
        scene_slots = [
            _slot(
                r,
                freshness=now,
                cost=estimate_tokens(f"{r.object_id}@{r.revision}"),
                reason="l0:wake_scene #84.2-step4",
            )
            for r in wake.scene_refs
        ]
        sections = FourStepsSections(
            step1_self=[s1] if s1 is not None else [],
            step2_rapport=[s2] if s2 is not None else [],
            step3_stance=[],  # v0 明文不装配（omissions 已声明）
            step4_world=([s4_now] if s4_now is not None else []) + scene_slots,
        )

        ready_tasks = [
            _slot(
                ObjectRef(object_id=r["task_id"], revision=r["world_rev"]),
                freshness=_aware(r["ready_since"]),
                cost=estimate_tokens(r["task_id"] + r["reason_json"]),
                reason="l0:ready_task #86.2",
            )
            for r in ready_rows
        ]

        cap_row = slices.get(SLICE_CAPABILITY_REGISTRY)
        capabilities: list[SlotRef] = []
        if cap_row is not None:
            for item in json.loads(cap_row["payload_json"]).get("capabilities", []):
                capabilities.append(_slot(
                    ObjectRef(object_id=item["object_id"], revision=int(item["revision"])),
                    freshness=_aware(cap_row["freshness_at"]),
                    cost=estimate_tokens(item["object_id"]),
                    reason="l0:capability #84.3",
                ))

        token_total = sum(
            slot.token_cost
            for group in (sections.step1_self, sections.step2_rapport,
                          sections.step3_stance, sections.step4_world,
                          ready_tasks, capabilities)
            for slot in group
        )

        body = {
            "manifest_version": 0,
            "subject_id": wake.subject_id,
            "wake": {"object_id": wake.wake_object_id, "revision": wake.wake_revision,
                     "reason_kind": wake.wake_reason_kind, "lane": wake.lane},
            "built_at": now.isoformat(),
            "sections": sections.model_dump(mode="json"),
            "ready_tasks": [s.model_dump(mode="json") for s in ready_tasks],
            "capabilities": [s.model_dump(mode="json") for s in capabilities],
            "omissions": [o.model_dump(mode="json") for o in omissions],
            "world_rev": self._store.current_world_revision(),
            "estimator_version": ESTIMATOR_VERSION,
        }
        canonical = _canon_json(body)
        canonical_hash = hashlib.sha256(canonical.encode()).hexdigest()
        manifest_id = f"mani0-{canonical_hash[:16]}"
        build_ms = (time.perf_counter() - t0) * 1000.0

        with self._connect() as conn:  # Q3：内容寻址幂等物化（重放不产生第二行）
            cur = conn.execute(
                "INSERT OR IGNORE INTO manifest_instance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    manifest_id, 0, wake.subject_id, wake.wake_object_id, wake.wake_revision,
                    wake.wake_reason_kind, wake.lane, canonical,
                    _canon_json([o.model_dump(mode="json") for o in omissions]),
                    len(ready_tasks), token_total, build_ms, QUERIES_PER_BUILD,
                    body["world_rev"], ESTIMATOR_VERSION, canonical_hash, now.isoformat(),
                ),
            )
            queries += 1
            reused = cur.rowcount == 0

        return BuildReport(
            manifest_id=manifest_id,
            reused_existing=reused,
            sections_filled=[
                name for name, group in (
                    ("step1_self", sections.step1_self),
                    ("step2_rapport", sections.step2_rapport),
                    ("step3_stance", sections.step3_stance),
                    ("step4_world", sections.step4_world),
                ) if group
            ],
            ready_exposed=len(ready_tasks),
            waiting_exposed=0,
            capabilities_exposed=len(capabilities),
            slices_hit=len(slices),
            omissions_count=len(omissions),
            rows_examined_ready=len(ready_rows),
            queries_executed=queries,
            token_total=token_total,
            build_ms=build_ms,
            world_rev=body["world_rev"],
            canonical_hash=canonical_hash,
        )

    def read_manifest_body(self, manifest_id: str) -> dict[str, Any] | None:
        """只读取回（M2-016/M2-017 的消费位）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT body_json FROM manifest_instance WHERE manifest_id=?",
                (manifest_id,),
            ).fetchone()
        return None if row is None else json.loads(row["body_json"])


__all__ = [
    "ESTIMATOR_VERSION",
    "KNOWN_SLICE_KINDS",
    "MODEL_CALLS_PER_BUILD",
    "QUERIES_PER_BUILD",
    "BuildReport",
    "L0SliceStore",
    "ManifestDataPlaneBuilderV0",
    "SLICE_CAPABILITY_REGISTRY",
    "SLICE_NOW_CONTEXT",
    "SLICE_RAPPORT",
    "SLICE_SELF_STATE",
    "WakeInput",
    "estimate_tokens",
]
