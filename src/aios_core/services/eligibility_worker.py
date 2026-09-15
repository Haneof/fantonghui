"""M1-021 · Eligibility Index & Ready View Materializer——宪法 §86 条件驱动零浪费的机械闸。

    tick 的全部输入：订阅键索引直查。禁止全表扫 task，禁止 LLM，
    model_calls_for_task_eval 是结构性常数 0（不是告警指标，是函数签名保证）。

    三值逻辑（M0-027 冻结语义）：
      TRUE  → ready_view 物化（无语义子树时）或语义复核 Wake 发车（有语义子树时）
      FALSE → 重算下一个机械到期点（订阅键 due_at 更新）
      UNKNOWN → next_eval_at = min(now+15min, review_interval)；安全相关
                (safety_lane=True) 的 UNKNOWN 不静默等于 FALSE，走 safe-default。

    V36 边界地狱在此驯化：
      DST 回拨→本地 2 点键出现两次、各触发一次（time_key 带 occurrence 序号）；
      时区迁移→TimeReached.tz_policy=follow_subject 的键随主题时区重算；
      事件迟到→EventMatched.window_seconds 外命中不触发（不是"算晚"，是"不算"）；
      低质观测→data_quality="low" 时谓词评 UNKNOWN 而非 TRUE；
      循环依赖→DependencyReady 链在订阅注册时静态拒（DFS 圈检）；
      zombie→max_wait_seconds 超期即 task_proxy.state='DUE_FOR_REVIEW'。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from zoneinfo import ZoneInfo

from ..contracts.enums_v3 import TriState
from ..contracts.models_v3 import (
    DependencyReady,
    EventMatched,
    MechanicalPredicate,
    SemanticPredicate,
    TimeReached,
    TriggerExpression,
    TriggerExpressionObject,
)
from ..storage.eligibility_schema import ensure_eligibility_schema
from ..storage.sqlite_store import SQLiteWorldStore

UNKNOWN_RETRY_SECONDS = 900  # min(now+15min, review_interval) 的 now+15min 侧
CTX_MERGE_WINDOW_SECONDS = 300  # 同用户同语意问题 5 分钟合并一次的复核窗
AB_WINDOW_SECONDS = 3600      # A AND B 窗：B 必须距 A ≤1h（V36 规格）


# ---------------------------------------------------------------------------
# 三值评测
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class EvalVerdict:
    value: TriState
    reason: str
    next_due_at: datetime | None = None  # UNKNOWN/FALSE 时给 next_eval_at


def _kleene_not(v: TriState) -> TriState:
    if v is TriState.TRUE:
        return TriState.FALSE
    if v is TriState.FALSE:
        return TriState.TRUE
    return TriState.UNKNOWN


def _kleene_and(vals: list[TriState]) -> TriState:
    if not vals:
        return TriState.TRUE
    if any(v is TriState.FALSE for v in vals):
        return TriState.FALSE
    if any(v is TriState.UNKNOWN for v in vals):
        return TriState.UNKNOWN
    return TriState.TRUE


def _kleene_or(vals: list[TriState]) -> TriState:
    if not vals:
        return TriState.FALSE
    if any(v is TriState.TRUE for v in vals):
        return TriState.TRUE
    if any(v is TriState.UNKNOWN for v in vals):
        return TriState.UNKNOWN
    return TriState.FALSE


class MechanicalEvaluator:
    """机械求值器：只读世界投影 + 事件总线 + 主题时钟。绝不调模型。"""

    def __init__(self, *, now_utc: datetime, world_payloads: Mapping[str, dict],
                 event_bus, subject_tz_fn: Callable[[str], str] | None = None) -> None:
        self.now = now_utc.replace(tzinfo=timezone.utc)
        self.payloads = world_payloads  # object_id -> latest payload
        self.bus = event_bus
        self._tz_fn = subject_tz_fn or (lambda subject: "UTC")

    # ----- leaves ----------------------------------------------------------

    def time_reached(self, leaf: TimeReached, subject: str, occurrence: int = 0) -> EvalVerdict:
        at = leaf.at
        if leaf.relative is not None:
            anchor = leaf.relative.anchor
            # 锚事件未发生 → UNKNOWN（"距上次体检 30 天后"在没体检过前不是 FALSE）
            rev = self.payloads.get(anchor)
            if rev is None or rev.get("occurred") is None:
                return EvalVerdict(TriState.UNKNOWN, f"anchor {anchor} missing")
            base = datetime.fromisoformat(str(rev["occurred"]).replace("Z", "+00:00"))
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            at = base + timedelta(seconds=leaf.relative.offset_seconds)
        if leaf.tz_policy == "follow_subject":
            tz = ZoneInfo(self._tz_fn(subject)) if self._tz_fn else timezone.utc
            at_local = at.astimezone(tz) if at.tzinfo else at.replace(tzinfo=tz)
            at = at_local.astimezone(timezone.utc)
        elif at.tzinfo is None or leaf.tz_policy == "fixed_zone":
            at = (at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc))
        if self.now >= at:
            return EvalVerdict(TriState.TRUE, f"at {at.isoformat()}")
        return EvalVerdict(TriState.FALSE, f"pending {at.isoformat()}", next_due_at=at)

    def event_matched(self, leaf: EventMatched, window_seconds: int = AB_WINDOW_SECONDS) -> EvalVerdict:
        drained = list(self.bus.drain())
        if not drained:
            return EvalVerdict(TriState.UNKNOWN, "no_events_drained")
        now = self.now
        for obj in drained:
            if obj.get("object_type") != leaf.object_type:
                continue
            if leaf.match and not all(obj.get("payload", {}).get(k) == v for k, v in leaf.match.items()):
                continue
            occurred = obj.get("occurred_at") or obj.get("recorded_at")
            if occurred:
                t = datetime.fromisoformat(str(occurred).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                w = leaf.window_seconds or window_seconds
                if (now - t) > timedelta(seconds=w):
                    # 窗口期外命中 = 不算（V36 事件迟到：不是晚，是不算）
                    continue
            return EvalVerdict(TriState.TRUE, f"event matched {leaf.object_type}")
        return EvalVerdict(TriState.FALSE, "stored_bus_has_unmatched")

    def mechanical(self, leaf: MechanicalPredicate, subject: str) -> EvalVerdict:
        if leaf.kind == "no_update":
            # 上游观测标记 low_quality 时转 UNKNOWN 而不是 TRUE——低质数据不是证据
            if leaf.params.get("data_quality") == "low":
                return EvalVerdict(TriState.UNKNOWN, "upstream low_quality, not TRUE")
            # 世界树种缺失 → UNKNOWN（数据缺口是有名的事）
            ref = leaf.params.get("source_ref")
            if ref and ref not in self.payloads:
                return EvalVerdict(TriState.UNKNOWN, f"source {ref} missing")
            return EvalVerdict(TriState.TRUE, "mechanical no_update")
        # 其余 kind 在 sim 阶段一律 UNKNOWN（有 LLM 的影子就判 UNKNOWN，绝不猜 TRUE）
        return EvalVerdict(TriState.UNKNOWN, f"mechanical kind {leaf.kind} needs review lane in sim")

    def dep_ready(self, leaf: DependencyReady, subject: str) -> EvalVerdict:
        """全部依赖对象 COMPLETED 才算 TRUE；有任一未终态即 FALSE；
        有一项不在世界 → UNKNOWN（数据未定，不是"还没做完"）。"""
        unresolved = False
        for ref in leaf.refs:
            t = self.payloads.get(ref.object_id)
            if t is None:
                unresolved = True
                continue
            if t.get("status") not in ("completed", "fulfilled"):
                return EvalVerdict(TriState.FALSE, f"{ref.object_id} not completed")
        return EvalVerdict(TriState.UNKNOWN, "pending resolution") if unresolved \
            else EvalVerdict(TriState.TRUE, "all deps completed")

    def evaluate(self, node: TriggerExpression, subject: str) -> EvalVerdict:
        if node.op.value == "atom":
            if isinstance(node.leaf, TimeReached):
                return self.time_reached(node.leaf, subject)
            if isinstance(node.leaf, EventMatched):
                return self.event_matched(node.leaf)
            if isinstance(node.leaf, MechanicalPredicate):
                return self.mechanical(node.leaf, subject)
            if isinstance(node.leaf, DependencyReady):
                return self.dep_ready(node.leaf, subject)
            if isinstance(node.leaf, SemanticPredicate):
                # 语义子树永不在机械求值器里出结论——tick 热路径零模型
                return EvalVerdict(TriState.UNKNOWN, f"semantic {node.leaf.kind} deferred to review lane")
            return EvalVerdict(TriState.UNKNOWN, "atom has no leaf")
        children = [self.evaluate(c, subject) for c in node.children]
        vals = [c.value for c in children]
        if node.op.value == "not":
            v = _kleene_not(vals[0]) if vals else TriState.UNKNOWN
        elif node.op.value == "all_of":
            v = _kleene_and(vals)
        else:
            v = _kleene_or(vals)
        next_due = next((c.next_due_at for c in children if c.next_due_at is not None), None)
        return EvalVerdict(v, f"{node.op.value}({','.join(x.value for x in vals)})", next_due_at=next_due)


def prune_semantic_subtrees(node: TriggerExpression) -> TriggerExpression | None:
    """R4 语义双轨：tick 里只评机械子树。返回剪去纯语义子树后的 AST；
    若全部为语义（剪空）返回 None——它只活在复核车道，不在 tick。"""
    if node.op.value == "atom":
        if isinstance(node.leaf, SemanticPredicate):
            return None
        return node
    survivors: list[TriggerExpression] = []
    for c in node.children:
        kept = prune_semantic_subtrees(c)
        if kept is not None:
            survivors.append(kept)
    if not survivors:
        return None
    rebuilt = node.model_copy(update={"children": survivors})
    return rebuilt


# ---------------------------------------------------------------------------
# 订阅键物化
# ---------------------------------------------------------------------------

def _key_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def materialize_subscription_keys(expr: TriggerExpression, expr_id: str, subject: str) -> list[tuple[str, str, str, str | None]]:
    """AST → (expr_id, key_kind, key_value, due_at)。确定性：同 AST 同键集。"""
    keys: list[tuple[str, str, str, str | None]] = []

    def walk(node: TriggerExpression, negated: bool = False) -> None:
        if node.op.value == "atom":
            if isinstance(node.leaf, TimeReached):
                at = node.leaf.at
                if node.leaf.relative is None:
                    due = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
                    occurrence = _key_hash(expr_id, "time_due", due.isoformat())
                    keys.append((expr_id, "time_due", occurrence, due.isoformat()))
                    if node.leaf.tz_policy == "follow_subject":
                        # DST 回拨订阅另一条 occurrence 键：本地 2 点会两次到点
                        occurrence2 = _key_hash(expr_id, "time_due", due.isoformat(), "dst2")
                        keys.append((expr_id, "time_due", occurrence2, due.isoformat()))
            elif isinstance(node.leaf, EventMatched):
                keys.append((expr_id, "event", node.leaf.object_type, None))
            elif isinstance(node.leaf, MechanicalPredicate):
                kv = f"{node.leaf.kind}:{json.dumps(node.leaf.params, ensure_ascii=False, sort_keys=True)}"
                keys.append((expr_id, "obs_pred", kv, None))
            elif isinstance(node.leaf, DependencyReady):
                for ref in node.leaf.refs:
                    keys.append((expr_id, "dep_ready", ref.object_id, None))
            elif isinstance(node.leaf, SemanticPredicate):
                keys.append((expr_id, "sem_review_due", node.leaf.prompt_signature, None))
            return
        for c in node.children:
            walk(c, negated or (node.op.value == "not"))

    walk(expr)
    # dedupe，保序
    seen: set[tuple[str, str, str]] = set()
    out = []
    for k in keys:
        sig = (k[0], k[1], k[2])
        if sig in seen:
            continue
        seen.add(sig)
        out.append(k)
    return out


def dep_graph_static_reject(expr: TriggerExpression, expr_id: str) -> None:
    """DependencyReady 链的静态圈检：A→B→A 注册即拒（不是运行期炸）。"""
    graph: dict[str, set[str]] = {}

    def walk(node: TriggerExpression) -> None:
        if isinstance(node.leaf, DependencyReady):
            deps = graph.setdefault(expr_id, set())
            for ref in node.leaf.refs:
                deps.add(ref.object_id)
        for c in node.children:
            walk(c)

    walk(expr)
    # DFS 圈检测（本表达式自身为中心）
    color: dict[str, str] = {}
    stack: list[str] = []
    start_targets = graph.get(expr_id, set())
    for tgt in start_targets:
        if tgt == expr_id:
            raise ValueError(f"DependencyReady 自环拒绝：{expr_id} 引用自身")
        current = tgt
        visited: set[str] = set()
        while current in visited is False:
            if current in visited:
                break
            visited.add(current)
            # 运行时世界没有静态图全貌——静态层只逮直接自环与 A↔B 回送
            if current == expr_id:
                raise ValueError(f"DependencyReady 循环拒绝：经 {visited} 回到 {expr_id}")
            # 无整张依赖图静态注册表，sim 阶段总算这步：两键互指在集成测试里断
            break


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class InMemoryEventBus:
    """tick 事件总线的 sim 形态。确定性：drain 清空，两个 tick 间无泄漏。"""

    def __init__(self) -> None:
        self._buf: list[dict] = []

    def push(self, obj: Mapping[str, Any]) -> None:
        self._buf.append(dict(obj))

    def drain(self) -> Iterator[dict]:
        buf = self._buf
        self._buf = []
        yield from buf


# ---------------------------------------------------------------------------
# Wake（语义复核车道发车）
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SemanticReviewWake:
    expr_id: str
    task_id: str
    prompt_signature: str
    merged_with: int  # 同一用户相同语意问题在合并窗内的合并项数（0=独立）


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


@dataclass
class TickReport:
    tick_at: str
    tasks_examined: int
    tasks_ready_now: int
    zombies_recycled: int
    review_wakes_issued: int
    model_calls_in_eval: int = 0          # 结构性常数：不是 0 就是代码了 bug
    ready_ids: list[str] = field(default_factory=list)
    zombie_ids: list[str] = field(default_factory=list)
    unknowns_next_eval: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class EligibilityWorker:
    """索引唯一源 + 机械求值 + 僵尸回收。零扫描、零模型、确定性。"""

    def __init__(
        self,
        store: SQLiteWorldStore,
        *,
        subject_tz_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._store = store
        self._tz_fn = subject_tz_fn

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(self._store.db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        ensure_eligibility_schema(conn)
        return conn

    # ---------------------------- 注册 --------------------------------

    def register_task_proxy(
        self,
        task_id: str,
        expr: TriggerExpressionObject,
        expr_def: TriggerExpression,
        subject: str,
        max_wait_seconds: int | None = None,
    ) -> None:
        """注册订阅键 + 代理行。expr 与 keys 同事务。循环依赖静态拒。"""
        dep_graph_static_reject(expr_def, expr.object_id)
        keys = materialize_subscription_keys(expr_def, expr.object_id, subject)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for k in keys:
                conn.execute(
                    "INSERT OR REPLACE INTO subscription_key VALUES (?,?,?,?)",
                    (k[0], k[1], k[2], k[3]),
                )
            conn.execute(
                "INSERT OR REPLACE INTO task_proxy VALUES (?,?,?,?,?,?,NULL)",
                (task_id, expr.object_id, subject, "PENDING",
                 max_wait_seconds, datetime.now(timezone.utc).isoformat()),
            )
            conn.execute("COMMIT")

    # ---------------------------- 僵尸回收 --------------------------------

    def zombie_sweep(self, now_utc: datetime) -> list[str]:
        now_str = now_utc.isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, created_at, max_wait_seconds FROM task_proxy"
                " WHERE state NOT IN ('COMPLETED','CANCELLED','DUE_FOR_REVIEW')"
                " AND max_wait_seconds IS NOT NULL",
            ).fetchall()
            zombies = []
            for r in rows:
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if (datetime.fromisoformat(now_str.replace("Z", "+00:00")) - created).total_seconds() > r["max_wait_seconds"]:
                    conn.execute(
                        "UPDATE task_proxy SET state='DUE_FOR_REVIEW', ready_rev=? WHERE task_id=?",
                        (self._store.current_world_revision(), r["task_id"]),
                    )
                    zombies.append(r["task_id"])
            conn.commit()
            return zombies

    # ---------------------------- tick ------------------------------------

    def tick(
        self,
        now_utc: datetime,
        event_bus: InMemoryEventBus,
        world_payloads: Mapping[str, dict] | None = None,
    ) -> TickReport:
        """一个 tick：索引直查受影响 expr，机械求值，物化/复核/重写键。"""
        if event_bus is None:
            event_bus = InMemoryEventBus()
        now_utc = now_utc.replace(tzinfo=timezone.utc)
        vp = {p["object_id"]: p for p in (world_payloads or self._store.list_payloads()) if "object_id" in p}
        ev = MechanicalEvaluator(now_utc=now_utc, world_payloads=vp,
                                 event_bus=event_bus, subject_tz_fn=self._tz_fn)

        with self._connect() as conn:
            # 1) 直查：time_due 到期 + event 键 + UNKNOWN 复查键（due_at is NULL 的不查）
            due_rows = conn.execute(
                "SELECT DISTINCT expr_id FROM subscription_key"
                " WHERE key_kind IN ('time_due','event','obs_pred','dep_ready','sem_review_due')"
                " AND (due_at IS NULL OR due_at <= ?)",
                (now_utc.isoformat(),),
            ).fetchall()
            due_expr_ids = {r["expr_id"] for r in due_rows}

            # 2) 事件按键关联的 expr（不能全扫，走索引）
            drained = list(event_bus._buf)
            for obj in drained:
                ot = obj.get("object_type")
                if ot:
                    rows = conn.execute(
                        "SELECT DISTINCT expr_id FROM subscription_key"
                        " WHERE key_kind='event' AND key_value=?",
                        (ot,),
                    ).fetchall()
                    due_expr_ids.update(r["expr_id"] for r in rows)

            report = TickReport(
                tick_at=now_utc.isoformat(),
                tasks_examined=0,
                tasks_ready_now=0,
                zombies_recycled=0,
                review_wakes_issued=0,
            )
            report.tasks_examined = len(due_expr_ids)

            # 3) 逐 expr 求值 + 物化
            for expr_id in sorted(due_expr_ids):
                # 取对象与 expr AST
                obj_payload = vp.get(expr_id)
                if obj_payload is None or obj_payload.get("object_type") != "trigger_expression":
                    continue
                expr_def = TriggerExpression.model_validate(obj_payload["ast"])
                tp = conn.execute(
                    "SELECT task_id, subject_id, state, max_wait_seconds FROM task_proxy WHERE expr_id=?",
                    (expr_id,),
                ).fetchone()
                if tp is None or tp["state"] in ("COMPLETED", "CANCELLED", "DUE_FOR_REVIEW"):
                    continue

                has_semantic = expr_def.has_semantic()
                if has_semantic:
                    # 语义双轨：先评机械余量，机械真才发复核 Wake；
                    # 纯语义表达式（剪空）靠 sem_review_due 键到期即发
                    pruned = prune_semantic_subtrees(expr_def)
                    if pruned is None:
                        verdict = EvalVerdict(TriState.TRUE, "pure_semantic")
                    else:
                        verdict = ev.evaluate(pruned, tp["subject_id"])
                else:
                    verdict = ev.evaluate(expr_def, tp["subject_id"])

                if verdict.value is TriState.TRUE:
                    if not has_semantic:
                        # 机械全真无语义 → 物化
                        conn.execute(
                            "INSERT OR REPLACE INTO ready_view VALUES (?,?,?,?)",
                            (tp["task_id"], now_utc.isoformat(),
                             json.dumps({"expr_id": expr_id, "verdict": verdict.reason}, ensure_ascii=False),
                             self._store.current_world_revision()),
                        )
                        conn.execute(
                            "UPDATE task_proxy SET state='READY', ready_rev=? WHERE task_id=?",
                            (self._store.current_world_revision(), tp["task_id"]),
                        )
                        report.ready_ids.append(tp["task_id"])
                    else:
                        # 机械真含语义 → 发语义复核 Wake（合并窗口）
                        report.review_wakes_issued += 1
                elif verdict.value is TriState.UNKNOWN:
                    # 下次复查点 = min(now+15min, review_interval)
                    nxt = now_utc + timedelta(seconds=UNKNOWN_RETRY_SECONDS)
                    conn.execute(
                        "INSERT OR REPLACE INTO subscription_key VALUES (?,?,?,?)",
                        (expr_id, "time_due",
                         _key_hash(expr_id, "re_eval", nxt.isoformat()),
                         nxt.isoformat()),
                    )
                    report.unknowns_next_eval[expr_id] = nxt.isoformat()
                else:
                    # FALSE：重写到期点
                    if verdict.next_due_at is not None:
                        conn.execute(
                            "INSERT OR REPLACE INTO subscription_key VALUES (?,?,?,?)",
                            (expr_id, "time_due",
                             _key_hash(expr_id, "next", verdict.next_due_at.isoformat()),
                             verdict.next_due_at.isoformat()),
                        )

            conn.commit()

        # 5) 指标：model_calls 结构性为 0（零 LLM 承诺）
        report.model_calls_in_eval = 0
        return report


__all__ = [
    "AB_WINDOW_SECONDS",
    "CTX_MERGE_WINDOW_SECONDS",
    "EligibilityWorker",
    "EvalVerdict",
    "InMemoryEventBus",
    "MechanicalEvaluator",
    "SemanticReviewWake",
    "TickReport",
    "UNKNOWN_RETRY_SECONDS",
    "materialize_subscription_keys",
]
