# -*- coding: utf-8 -*-
"""stated · 状态系统（World State / World Update / World Change）—— Sprint 1 Task 5 实装

契约来源（全部可反查）：
- Canonical 02 §2 World：输入 Event/Entity/State Update，输出 World State + World Change。
- Canonical 02 §3 State：不要只保存值，要保存变化（before/after）。
- Canonical 03：World State 九个槽位、World Change 字段、raw_ref 唯一引用字段。
- Canonical 01 §6：World Runtime 不负责复杂判断 → 本文件只允许"事件类型 → 世界槽位"的
  确定性映射；零模型、零网络、零文本相似度（LLM 不在 Event→World 必经路径上）。
- 宪法 §4：事实(Event)/认知(Cognition)/记忆(Memory)/成长(Growth) 绝不混写 → World 只写
  自己的库 `run/world_state.db`，并且显式拒绝认知/记忆/成长槽位。
- 宪法 §5.1：MODE 九种；docs/OS §S3：MODE 由 modemgrd→stated 提供 → 本服务**消费**
  事件自带的 mode_at_time，不自造 MODE 判定。
- docs/OS §3.2：stated 维护"此刻快照"，持久化=内存 + 快照文件；本实装在其上加 SQLite
  版本链（NEXT_TASK §2 要求快照+版本），快照文件仍常备供毫秒级读取（AI 工作包 B 段）。

运行方式：
1) 常驻（aiosd 拉起，正常路径）：订阅 evt.#，把 canonical Event 应用进世界。
2) 离线回放（确定性验收）：
       python services/stated.py --replay-jsonl <file.jsonl>
   逐行读 canonical Event，应用到一次性数据库，打印最终快照 + state_sha 后退出。

线程模型：SDK 的读循环单线程回调 on_event；引擎内部仍加锁，便于离线模式与测试复用。
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time

CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # code/
SCHEMA_DIR = os.path.join(os.path.dirname(CODE_ROOT), "schemas")             # 01_os/schemas
RUN_DIR = os.path.join(CODE_ROOT, "run")
DB_PATH = os.path.join(RUN_DIR, "world_state.db")
SNAPSHOT_PATH = os.path.join(RUN_DIR, "world_state.json")

# ===================== Canonical 契约常量（槽位集合由 schema 决定，代码不第二套定义） =====================

MODES: tuple[str, ...] = ("WORK", "SOCIAL", "DRIVE", "SLEEP", "SPORT", "STUDY",
                          "LEISURE", "EMERGENCY", "UNKNOWN")

#: 一次 Event → World Update 的全部下落（closed set）：每次尝试必须恰好落进一个。
UPDATE_APPLIED = "applied"
UPDATE_NO_RULE = "no_rule"                    # 无模板：事件保留、世界不变（08 E 不得静默丢弃）
UPDATE_NO_SLOT_CHANGE = "no_slot_change"      # 世界已经如此：不造重复 Change（02 §3）
UPDATE_STALE = "stale"                        # 早于当前快照：不得把世界往回改
UPDATE_REPLAY = "replay_skipped"              # 同一 Event 已吸收：不得产生第二次 World Update
UPDATE_REJECTED = "rejected"                  # 非法/不完整：世界状态一字不动
DISPOSITIONS: frozenset[str] = frozenset({UPDATE_APPLIED, UPDATE_NO_RULE, UPDATE_NO_SLOT_CHANGE,
                                          UPDATE_STALE, UPDATE_REPLAY, UPDATE_REJECTED})

#: World Update 结构字段（与 arena 线已验证的边界对象同名同义，便于两条线对照审查）。
UPDATE_FIELDS: tuple[str, ...] = ("id", "rule", "source_events", "window", "slots", "trace")

#: 宪法 §4 三棵树的键名——一旦被当作世界槽位提交就报错，而不是悄悄忽略。
FORBIDDEN_SLOTS: frozenset[str] = frozenset({"cognition", "memory", "growth", "belief", "judgment",
                                             "lesson", "decision", "importance", "tags"})

#: 拒绝原因闭集。
REJECT_CODES: frozenset[str] = frozenset({"NOT_AN_EVENT", "SCHEMA_INVALID",
                                           "UNPARSEABLE_TIMESTAMP", "MISSING_ID"})

_META_KEYWORDS = {"$schema", "$id", "title", "description"}


class WorldInputError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class WorldUpdateError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# ===================== 最小 schema 校验器（主线只用标准库，故不引外部 jsonschema） =====================

_SUPPORTED = {"type", "properties", "required", "additionalProperties", "items", "oneOf"}


def _check_type(value, want: str) -> bool:
    return {"object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "null": lambda v: v is None}[want](value)


def validate(value, schema: dict, path: str = "") -> list[str]:
    """只实现这三份 canonical schema 用到的关键字；遇到不认识的关键字直接抛错。

    刻意不"静默忽略"未知关键字：那会把契约悄悄放宽成假契约。
    """
    unknown = set(schema) - _SUPPORTED - _META_KEYWORDS
    if unknown:
        raise AssertionError(f"schema 校验器未实现的关键字 {sorted(unknown)} @ {path or '<root>'}")
    errs: list[str] = []
    if "oneOf" in schema:
        subs = schema["oneOf"]
        if not any(not validate(value, s, path) for s in subs):
            return [f"{path or '<root>'} 不匹配 oneOf"]
    if "type" in schema and not _check_type(value, schema["type"]):
        errs.append(f"{path or '<root>'} 类型应为 {schema['type']}，实为 {type(value).__name__}")
        return errs
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errs.append(f"{path or '<root>'} 缺必填字段 {req}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties", True) is False:
            for k in value:
                if k not in props:
                    errs.append(f"{path or '<root>'} 出现未声明字段 {k}")
        for k, sub in props.items():
            if k in value:
                errs += validate(value[k], sub, f"{path}.{k}" if path else k)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errs += validate(item, schema["items"], f"{path}[{i}]")
    return errs


def _load_schema(name: str) -> dict:
    with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as f:
        schema = json.load(f)
    if name == "event.json":                      # 启动自检：schema 必须还是 Canonical 03 那一份
        props = set(schema["properties"])
        expect = {"id", "timestamp", "source", "type", "content", "entities",
                  "location_id", "confidence", "raw_ref"}
        if props != expect:
            raise AssertionError(f"schemas/event.json 字段与 Canonical 03 不一致：{sorted(props)}")
    return schema


EVENT_SCHEMA = _load_schema("event.json")
STATE_SCHEMA = _load_schema("world_state.json")
CHANGE_SCHEMA = _load_schema("world_change.json")
STATE_SLOTS: tuple[str, ...] = tuple(k for k in STATE_SCHEMA["properties"] if k != "timestamp")
EMPTY_STATE: dict = {"timestamp": "", "user": {}, "location": {}, "mode": "UNKNOWN", "people": [],
                     "environment": {}, "active_situations": [], "active_goals": [], "pending_tasks": []}


# ===================== 总线帧 → canonical Event（规范化只在这里做一次） =====================

def iso_from_epoch(seconds: float) -> str:
    """固定 UTC(+00:00)：回放确定性不能依赖机器时区。设备本地时区由事件自带 timestamp 覆盖。"""
    return dt.datetime.fromtimestamp(float(seconds), dt.timezone.utc).isoformat(timespec="seconds")


def _parse_ts(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp)


def normalize_frame(msg: dict, from_svc: str = "", topic: str = "") -> tuple[dict, dict]:
    """总线帧（{id,ts,source,type,content,...}）→ Canonical 03 Event + 主线上下文。

    Canonical 03 只认这 9 个字段（event.json additionalProperties:false），因此
    speaker / mode_at_time / privacy_level 等主线字段一律放进 context，不混进 Event 本体。
    """
    ev = dict(msg or {})
    if not ev.get("timestamp"):
        ts = ev.get("ts")
        ev["timestamp"] = iso_from_epoch(ts if ts else time.time())
    canon = {
        "id": str(ev.get("id") or ""),
        "timestamp": str(ev.get("timestamp") or ""),
        "source": str(ev.get("source") or "unknown"),
        "type": str(ev.get("type") or "unknown"),
        "content": ev.get("content") if isinstance(ev.get("content"), str) else str(ev.get("content", "")),
        "entities": [str(x) for x in (ev.get("entities") or [])],
        # 位置只取事件自带的显式证据：优先 location_id，其次 entities 里的 place_*（不猜）。
        "location_id": ev.get("location_id") or next((e for e in (ev.get("entities") or [])
                                                      if str(e).startswith("place_")), None),
        "confidence": float(ev.get("confidence") or 0.0),
        # raw_ref 是 03 唯一原始引用字段：主线指向 hublinkd 入口队列里的那一行（24h 保留，非长期存储）。
        "raw_ref": ev.get("raw_ref") or (f"aios://entry_queue#{ev.get('id')}" if ev.get("id") else None),
    }
    context = {k: v for k, v in ev.items() if k not in canon}
    context["from_service"], context["topic"] = from_svc, topic
    return canon, context


# ===================== 事件类型 → 世界槽位（确定性规则；与 arena 线已验证表一致） =====================

def _rule_arrival(ev, before, ctx):
    slots: dict = {"mode": "WORK"}
    if ev["location_id"]:
        slots["location"] = {"id": ev["location_id"]}
    return "LOCATION_ARRIVAL", slots


def _rule_person_enter(ev, before, ctx):
    people = sorted(set(before["people"]) | {e for e in ev["entities"] if e.startswith("person_")})
    return "PARTICIPANT_ENTER", {"people": people}


def _rule_departure(ev, before, ctx):
    leaving = {e for e in ev["entities"] if e.startswith("person_")}
    if leaving:
        return "PARTICIPANT_LEAVE", {"people": [p for p in before["people"] if p not in leaving]}
    if ev["location_id"] and before["location"].get("id") == ev["location_id"]:
        return "LOCATION_DEPARTURE", {"location": {}, "mode": "UNKNOWN"}
    return "PARTICIPANT_LEAVE", {"people": list(before["people"])}


def _rule_contract(ev, before, ctx):
    return "CONTRACT_DISCUSSION", {"active_situations": sorted(set(before["active_situations"]) | {"negotiation"})}


def _rule_price(ev, before, ctx):
    base = "PRICE_DISCUSSION"
    if _is_escalating(ctx.get("_recent_price_iso"), ev["timestamp"]):
        base = "NEGOTIATION_ESCALATION"
    return base, {"user": {**before["user"], "talking": True, "topic": "price"}}


def _rule_silence(ev, before, ctx):
    return "USER_SILENCE", {"user": {**before["user"], "talking": False}}


def _rule_doc_open(ev, before, ctx):
    artifact = next((e for e in ev["entities"] if e.startswith("contract_")), None)
    return "DOCUMENT_OPEN", {"environment": {**before["environment"], "artifact": artifact}}


def _slot_set(prefix: str, slot: str, change_type: str, remove: bool = False):
    """任务/目标维度：值只取 entity id（task_*/goal_*），不解析自由文本。"""
    def rule(ev, before, ctx):
        ids = [e for e in ev["entities"] if e.startswith(prefix)]
        if remove:
            drop = set(ids)
            return change_type, {slot: [x for x in before[slot] if x not in drop]}
        return change_type, {slot: sorted(set(before[slot]) | set(ids))}
    return rule


def _is_escalating(last_iso, now_iso: str) -> bool:
    """30 分钟内再次出现价格讨论 → 升级（03 §World Change 示例的 NEGOTIATION_ESCALATION）。"""
    if not last_iso:
        return False
    try:
        return abs((_parse_ts(now_iso) - _parse_ts(last_iso)).total_seconds()) <= 1800
    except ValueError:
        return False


RULES = {
    "arrival": _rule_arrival,
    "person_enter": _rule_person_enter,
    "departure": _rule_departure,
    "contract_discussion": _rule_contract,
    "price_negotiation": _rule_price,
    "silence": _rule_silence,
    "document_open": _rule_doc_open,
    "task_assigned": _slot_set("task_", "pending_tasks", "TASK_ASSIGNED"),
    "task_done": _slot_set("task_", "pending_tasks", "TASK_CLOSED", remove=True),
    "goal_set": _slot_set("goal_", "active_goals", "GOAL_OPENED"),
    "goal_done": _slot_set("goal_", "active_goals", "GOAL_CLOSED", remove=True),
}


def make_world_update(update_id: str, rule: str, events: list[dict], slots: dict) -> dict:
    stamps = [e["timestamp"] for e in events]
    upd = {"id": update_id, "rule": rule, "source_events": [e["id"] for e in events],
           "window": {"start": min(stamps), "end": max(stamps)},
           "slots": copy.deepcopy(slots),
           "trace": {"event_ids": [e["id"] for e in events],
                     "raw_refs": [e.get("raw_ref") for e in events],
                     "event_count": len(events)}}
    validate_world_update(upd)
    return upd


def validate_world_update(upd) -> None:
    """World Update 结构契约。违反即抛，绝不"尽力而为"地应用半个更新。"""
    if not isinstance(upd, dict):
        raise WorldUpdateError("UPDATE_NOT_A_MAPPING", f"应为 dict，收到 {type(upd).__name__}")
    missing = [k for k in UPDATE_FIELDS if k not in upd]
    extra = sorted(set(upd) - set(UPDATE_FIELDS))
    if missing or extra:
        raise WorldUpdateError("UPDATE_FIELDS", f"缺 {missing} 多 {extra}")
    if not upd["source_events"]:
        raise WorldUpdateError("UPDATE_WITHOUT_EVIDENCE", "World Update 必须能追溯到至少一个 Event")
    if any(not isinstance(i, str) or not i for i in upd["source_events"]):
        raise WorldUpdateError("UPDATE_BAD_EVIDENCE", "source_events 必须是非空 event id")
    if upd["trace"]["event_ids"] != list(upd["source_events"]):
        raise WorldUpdateError("UPDATE_TRACE_MISMATCH", "trace.event_ids 与 source_events 不一致")
    win = upd["window"]
    if set(win) != {"start", "end"} or win["start"] > win["end"]:
        raise WorldUpdateError("UPDATE_WINDOW", f"窗口非法：{win}")
    slots = upd["slots"]
    if not isinstance(slots, dict) or not slots:
        raise WorldUpdateError("UPDATE_NO_SLOT", "至少提出一个槽位改写")
    for name, value in slots.items():
        if name in FORBIDDEN_SLOTS:
            raise WorldUpdateError("UPDATE_FORBIDDEN_SLOT",
                                  f"{name!r} 属于认知/记忆/成长层，不得写进 World State（宪法 §4）")
        if name not in STATE_SLOTS:
            raise WorldUpdateError("UPDATE_UNKNOWN_SLOT", f"{name!r} 不是 world_state.json 声明的槽位")
        errs = validate(value, STATE_SCHEMA["properties"][name], name)
        if errs:
            raise WorldUpdateError("UPDATE_SLOT_TYPE", "; ".join(errs))
        if name == "mode" and value not in MODES:
            raise WorldUpdateError("UPDATE_BAD_MODE", f"MODE 必须是宪法 §5.1 取值，收到 {value!r}")


# ===================== 世界本体：SQLite（快照+版本+台账）+ 内存 + 快照文件 =====================

DDL = """
CREATE TABLE IF NOT EXISTS world_state(
  version INTEGER PRIMARY KEY, ts TEXT NOT NULL, ts_s INTEGER NOT NULL,
  state_json TEXT NOT NULL, state_sha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS world_update(
  id TEXT PRIMARY KEY, event_id TEXT, rule TEXT, disposition TEXT NOT NULL,
  change_id TEXT, window_start TEXT, window_end TEXT, slots TEXT, update_json TEXT,
  note TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS world_change(
  id TEXT PRIMARY KEY, window_start TEXT, window_end TEXT, change_type TEXT,
  before_json TEXT, after_json TEXT, entities_json TEXT, evidence_json TEXT,
  confidence REAL, version INTEGER, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS applied_event(
  event_id TEXT PRIMARY KEY, change_id TEXT, applied_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_wu_disp ON world_update(disposition);
CREATE INDEX IF NOT EXISTS idx_wc_ver ON world_change(version);
"""


class WorldStateEngine:
    """与总线解耦的世界状态引擎（publish 可注入，便于单测——沿用 attentiond 的 LeaseEngine 风格）。"""

    def __init__(self, db_path: str = DB_PATH, snapshot_path: str | None = SNAPSHOT_PATH,
                 publish=None) -> None:
        self.db_path = db_path
        self.snapshot_path = snapshot_path
        self.publish = publish or (lambda topic, msg: None)
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript("PRAGMA journal_mode=WAL;PRAGMA synchronous=NORMAL;" + DDL)
        self._lock = threading.Lock()
        self._update_seq = int((self._query_one("SELECT COUNT(*) FROM world_update") or (0,))[0] or 0)
        self._state = self._load_latest_state()
        self._version = self._load_latest_version()
        self._recent_price: str | None = self._load_recent_price()
        self.stats = {"attempted": 0, UPDATE_APPLIED: 0, UPDATE_NO_RULE: 0, UPDATE_NO_SLOT_CHANGE: 0,
                      UPDATE_STALE: 0, UPDATE_REPLAY: 0, UPDATE_REJECTED: 0,
                      "expensive_model_call_count": 0}

    # ---------- 恢复 ----------

    def _query_one(self, sql, args=()):
        try:
            return self._conn.execute(sql, args).fetchone()
        except sqlite3.Error:
            return None

    def _load_latest_state(self) -> dict:
        row = self._query_one("SELECT state_json FROM world_state ORDER BY version DESC LIMIT 1")
        return json.loads(row[0]) if row else copy.deepcopy(EMPTY_STATE)

    def _load_latest_version(self) -> int:
        row = self._query_one("SELECT MAX(version) FROM world_state")
        return int(row[0]) if row and row[0] is not None else 0

    def _load_recent_price(self):
        row = self._query_one("SELECT window_end FROM world_change WHERE change_type IN "
                              "('PRICE_DISCUSSION','NEGOTIATION_ESCALATION') ORDER BY version DESC LIMIT 1")
        return row[0] if row else None

    # ---------- 主流程 ----------

    def on_bus_frame(self, topic: str, from_svc: str, msg: dict) -> dict:
        """总线入口：规范化 + 校验，非法帧在这里被挡（引擎不会看到脏数据）。"""
        if not isinstance(msg, dict):
            return self._reject(msg, "NOT_AN_EVENT", f"msg 必须是 dict，收到 {type(msg).__name__}")
        try:
            canon, ctx = normalize_frame(msg, from_svc, topic)
        except (ValueError, TypeError) as exc:
            return self._reject(msg, "SCHEMA_INVALID", f"规范化失败：{exc}")
        return self.apply_event(canon, ctx=ctx)

    def apply_event(self, event: dict, ctx: dict | None = None) -> dict:
        """输入 canonical Event（03），返回本次下落记录。永远不抛——非法走 rejected。"""
        ctx = dict(ctx or {})
        self.stats["attempted"] += 1
        try:
            ev = self._validate_event(event)
        except (WorldInputError, WorldUpdateError) as exc:
            return self._reject(event, exc.code, exc.detail)

        with self._lock:
            if self._already_applied(ev["id"]):
                return self._ledger(ev, rule=None, disposition=UPDATE_REPLAY, ctx=ctx)
            try:
                upd = self._plan(ev, ctx)
            except WorldUpdateError as exc:
                return self._reject(ev, exc.code, exc.detail)
            if upd is None:
                return self._ledger(ev, rule=None, disposition=UPDATE_NO_RULE, ctx=ctx)
            if self._is_stale(ev):
                return self._ledger(ev, rule=upd["rule"], disposition=UPDATE_STALE, update=upd, ctx=ctx)

            before = copy.deepcopy(self._state)
            after = copy.deepcopy(self._state)
            after.update(copy.deepcopy(upd["slots"]))
            after["timestamp"] = ev["timestamp"]
            diff = {k: {"before": before.get(k), "after": after.get(k)}
                    for k in STATE_SLOTS if before.get(k) != after.get(k)}
            if not diff:
                return self._ledger(ev, rule=upd["rule"], disposition=UPDATE_NO_SLOT_CHANGE,
                                    update=upd, ctx=ctx)

            errs = validate(after, STATE_SCHEMA)
            if errs:
                # 状态不合法 → 一字不落地拒绝，绝不写半个世界
                return self._reject(ev, "SCHEMA_INVALID", f"合并后的 World State 非法：{errs}")

            self._version += 1
            sha = self._sha(after)
            chg = {
                "id": f"chg_{self._version:05d}",
                "window": dict(upd["window"]),
                "change_type": upd["rule"],
                "before": {k: v["before"] for k, v in diff.items()},
                "after": {k: v["after"] for k, v in diff.items()},
                "entities": list(ev["entities"]),
                "evidence_events": list(upd["source_events"]),
                "confidence": ev["confidence"],
            }
            cerrs = validate(chg, CHANGE_SCHEMA)
            if cerrs:
                raise AssertionError(f"World Change 不符合 schemas/world_change.json：{cerrs}")

            now = time.time()
            with self._conn:                                  # 一个事务：状态+变更+台账+幂等标记
                self._conn.execute("INSERT INTO world_state VALUES (?,?,?,?,?)",
                                   (self._version, after["timestamp"], int(_parse_ts(after["timestamp"]).timestamp()),
                                    json.dumps(after, ensure_ascii=False, sort_keys=True), sha))
                self._conn.execute(
                    "INSERT INTO world_change VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (chg["id"], chg["window"]["start"], chg["window"]["end"], chg["change_type"],
                     json.dumps(chg["before"], ensure_ascii=False, sort_keys=True),
                     json.dumps(chg["after"], ensure_ascii=False, sort_keys=True),
                     json.dumps(chg["entities"], ensure_ascii=False),
                     json.dumps(chg["evidence_events"], ensure_ascii=False),
                     chg["confidence"], self._version, now))
                self._conn.execute("INSERT OR IGNORE INTO applied_event VALUES (?,?,?)",
                                   (ev["id"], chg["id"], now))
            self._state = after
            if chg["change_type"] in ("PRICE_DISCUSSION", "NEGOTIATION_ESCALATION"):
                self._recent_price = ev["timestamp"]
            self._write_snapshot()
            line = self._ledger(ev, rule=upd["rule"], disposition=UPDATE_APPLIED,
                                update=upd, change_id=chg["id"], ctx=ctx)
            self.publish("world.state.updated", {"version": self._version, "ts": after["timestamp"],
                                                  "state_sha": sha, "changed_slots": sorted(diff),
                                                  "event_id": ev["id"]})
            self.publish("world.change", chg)
            line["change"] = chg
            return line

    def _plan(self, ev: dict, ctx: dict) -> dict | None:
        """Event → World Update。无模板事件返回 None（但事件本身已在别处落库，不丢）。"""
        before = copy.deepcopy(self._state)
        slots: dict = {}
        rule_name = None
        fn = RULES.get(ev["type"])
        if fn is not None:
            ctx = {**ctx, "_recent_price_iso": self._recent_price}
            rule_name, slots = fn(ev, before, ctx)
        # MODE 由 modemgrd→stated 提供（docs/OS §S3）：外部权威优先于本地规则，unknown 不算。
        ext_mode = ctx.get("mode_at_time")
        if isinstance(ext_mode, str) and ext_mode in MODES and ext_mode != "UNKNOWN":
            if slots.get("mode") != ext_mode:
                slots["mode"] = ext_mode
                rule_name = rule_name or "MODE_CONTEXT"
        if not slots:
            return None
        self._update_seq += 1
        return make_world_update(f"wup_{self._update_seq:06d}", rule_name or "UNMAPPED", [ev], slots)

    def _validate_event(self, event) -> dict:
        if not isinstance(event, dict):
            raise WorldInputError("NOT_AN_EVENT", f"World 只接受 canonical Event dict，收到 {type(event).__name__}")
        ev = copy.deepcopy(event)                     # 只读：任何情况下不改调用方对象
        errs = validate(ev, EVENT_SCHEMA)
        if errs:
            hint = "（Raw Signal 属于 perceptiond 的输入，不得直接进世界）" if "modality" in ev or "payload" in ev else ""
            raise WorldInputError("SCHEMA_INVALID", f"不符合 schemas/event.json{hint}：{errs}")
        if not ev["id"]:
            raise WorldInputError("MISSING_ID", "Event id 为空，世界无法建立可追溯性")
        try:
            _parse_ts(ev["timestamp"])
        except ValueError as exc:
            raise WorldInputError("UNPARSEABLE_TIMESTAMP", f"时间戳无法解析：{exc}") from exc
        return ev

    def _is_stale(self, ev: dict) -> bool:
        cur = self._state.get("timestamp")
        if not cur:
            return False
        try:
            return _parse_ts(ev["timestamp"]) < _parse_ts(cur)
        except ValueError:
            return True

    def _already_applied(self, event_id: str) -> bool:
        return self._query_one("SELECT 1 FROM applied_event WHERE event_id=?", (event_id,)) is not None

    # ---------- 台账与自检 ----------

    def _ledger(self, ev, *, rule, disposition, update=None, change_id=None, ctx=None, note="") -> dict:
        self.stats[disposition] = self.stats.get(disposition, 0) + 1
        eid = ev.get("id") if isinstance(ev, dict) else None
        uid = f"wuplog_{self.stats['attempted']:06d}"
        with self._conn:
            self._conn.execute("INSERT OR REPLACE INTO world_update VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (uid, eid or None, rule, disposition, change_id,
                               (update or {}).get("window", {}).get("start"),
                               (update or {}).get("window", {}).get("end"),
                               json.dumps((update or {}).get("slots", {}), ensure_ascii=False, sort_keys=True),
                               json.dumps(update, ensure_ascii=False, sort_keys=True) if update else None,
                               note, time.time()))
        return {"id": uid, "event_id": eid or None, "rule": rule, "disposition": disposition,
                "change_id": change_id, "update": update, "note": note}

    def _reject(self, event, code: str, detail: str) -> dict:
        note = f"{code}: {detail}"
        line = self._ledger(event, rule=None, disposition=UPDATE_REJECTED, note=note)
        self.publish("world.update.rejected", {"event_id": line["event_id"], "code": code, "detail": detail})
        return line

    @staticmethod
    def _sha(state: dict) -> str:
        return hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _write_snapshot(self) -> None:
        if not self.snapshot_path:
            return
        os.makedirs(os.path.dirname(self.snapshot_path) or ".", exist_ok=True)
        tmp = self.snapshot_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.snapshot_path)              # 原子替换：读者永远看到完整快照

    def snapshot(self) -> dict:
        return copy.deepcopy(self._state)

    def state_sha(self) -> str:
        return self._sha(self._state)

    def version(self) -> int:
        return self._version

    def counts(self) -> dict:
        return copy.deepcopy(self.stats)

    def changes(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute("SELECT id,window_start,window_end,change_type,before_json,"
                                  "after_json,evidence_json,confidence,version FROM world_change "
                                  "ORDER BY version DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "window": {"start": r[1], "end": r[2]}, "change_type": r[3],
                 "before": json.loads(r[4]), "after": json.loads(r[5]),
                 "evidence_events": json.loads(r[6]), "confidence": r[7], "version": r[8]} for r in rows][::-1]

    def ledger(self, limit: int = 1000, disposition: str | None = None) -> list[dict]:
        sql = "SELECT id,event_id,rule,disposition,change_id,slots,note FROM world_update"
        args: tuple = ()
        if disposition:
            sql += " WHERE disposition=?"; args = (disposition,)
        rows = self._conn.execute(sql + " ORDER BY rowid LIMIT ?", (*args, limit)).fetchall()
        return [{"id": r[0], "event_id": r[1], "rule": r[2], "disposition": r[3], "change_id": r[4],
                 "slots": json.loads(r[5] or "{}"), "note": r[6]} for r in rows]

    def verify_conservation(self) -> list[str]:
        total = sum(self.stats[k] for k in DISPOSITIONS)
        bad = []
        if total != self.stats["attempted"]:
            bad.append(f"attempted={self.stats['attempted']} 但各下落合计={total}")
        n = self._conn.execute("SELECT COUNT(*) FROM world_update").fetchone()[0]
        if n != self.stats["attempted"]:
            bad.append(f"台账行数 {n} != attempted {self.stats['attempted']}")
        applied = self._conn.execute("SELECT COUNT(*) FROM world_update WHERE disposition=?",
                                     (UPDATE_APPLIED,)).fetchone()[0]
        changes = self._conn.execute("SELECT COUNT(*) FROM world_change").fetchone()[0]
        if applied != changes:
            bad.append(f"applied 台账 {applied} != World Change {changes}")
        if changes != self._version:
            bad.append(f"World Change {changes} != 快照版本 {self._version}")
        return bad

    def verify_traceability(self) -> list[str]:
        """每个 World Change 都必须回到已吸收的 Event；幂等标记与 change 必须互相咬合。"""
        bad = []
        rows = self._conn.execute("SELECT id,evidence_json FROM world_change").fetchall()
        for cid, ev_json in rows:
            ids = json.loads(ev_json)
            if not ids:
                bad.append(f"{cid} 没有 evidence_events")
                continue
            for eid in ids:
                if self._query_one("SELECT 1 FROM applied_event WHERE event_id=?", (eid,)) is None:
                    bad.append(f"{cid} 的证据 {eid} 不在 applied_event 里（World Change 无法追溯）")
        orphans = self._conn.execute(
            "SELECT event_id FROM applied_event WHERE change_id NOT IN (SELECT id FROM world_change)").fetchall()
        if orphans:
            bad.append(f"幂等标记指向不存在的 Change: {[r[0] for r in orphans]}")
        return bad

    def verify_slot_isolation(self) -> list[str]:
        """三棵树不得混写：World State 的键集合必须永远等于 schema 声明的槽位。"""
        return [] if set(self._state) == set(STATE_SCHEMA["properties"]) else \
            [f"World State 键漂移: {sorted(set(self._state) ^ set(STATE_SCHEMA['properties']))}"]

    def close(self) -> None:
        try:
            self._conn.commit()
            self._conn.close()
        except sqlite3.Error:
            pass


# ===================== 总线服务侧（常驻） =====================

def main_service() -> None:                                  # pragma: no cover - 常驻入口
    sys.path.insert(0, CODE_ROOT)
    from aios_sdk.aios_sdk import AIOSService

    svc = AIOSService("stated", subscribe=["evt.#"])
    eng = WorldStateEngine(publish=svc.publish)
    counter = {"n": 0, "last_log": 0.0}

    def on_event(topic, from_svc, msg):
        counter["n"] += 1
        rec = eng.on_bus_frame(topic, from_svc, msg)
        if rec["disposition"] != UPDATE_APPLIED:
            return
        now = time.time()
        if counter["n"] <= 3 or now - counter["last_log"] > 5.0:      # 限频日志：防日志拖慢流水线
            counter["last_log"] = now
            c = eng.counts()
            svc.log(f"世界更新 #{eng.version()} {rec['rule']} <- {rec['event_id']} "
                    f"slots={sorted(rec['update']['slots'])} "
                    f"[applied={c[UPDATE_APPLIED]} no_rule={c[UPDATE_NO_RULE]} stale={c[UPDATE_STALE]} "
                    f"replay={c[UPDATE_REPLAY]} rejected={c[UPDATE_REJECTED]}]")

    svc.on_event = on_event
    svc.log(f"服务启动（Task5 实装：Event→World Update→World State；恢复版本 {eng.version()}，"
            f"mode={eng.snapshot()['mode']}）")
    svc.run()


def main_replay(path: str) -> int:
    """离线确定性回放：同一份事件流跑两遍必须得到同一个 state_sha。"""
    events = [json.loads(ln) for ln in open(path, encoding="utf-8") if ln.strip()]
    out = {}
    for pass_no in (1, 2):
        db = os.path.join(RUN_DIR, f"_replay_pass{pass_no}.db")
        for junk in (db, db + "-wal", db + "-shm"):
            if os.path.exists(junk):
                os.remove(junk)
        eng = WorldStateEngine(db_path=db, snapshot_path=None)
        for ev in events:
            eng.apply_event(ev)
        out[pass_no] = (eng.version(), eng.state_sha(), eng.counts())
        eng.close()
        for junk in (db, db + "-wal", db + "-shm"):
            if os.path.exists(junk):
                os.remove(junk)
    same = out[1][1] == out[2][1] and out[1][0] == out[2][0]
    print(json.dumps({"events": len(events), "pass1": {"version": out[1][0], "state_sha": out[1][1],
                                                        "counts": out[1][2]},
                      "pass2": {"version": out[2][0], "state_sha": out[2][1]},
                      "replay_identical": same}, ensure_ascii=False, indent=1))
    return 0 if same else 1


if __name__ == "__main__":
    if "--replay-jsonl" in sys.argv:
        raise SystemExit(main_replay(sys.argv[sys.argv.index("--replay-jsonl") + 1]))
    main_service()
