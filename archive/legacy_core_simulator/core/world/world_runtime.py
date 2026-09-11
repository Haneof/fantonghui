"""WorldRuntime —— 契约来源: 02 §2 World(与 02 §3 State 配合产出 World Change)。

Task 5 把 "Event -> World Update -> World State" 钉成三段可见结构:

    Event  --plan-->  World Update  --apply-->  World State
                          |
                          +--> World Change(before / after / evidence_events)

边界纪律(每条都能被 tests/unit/test_world_update.py 反查):

1. World Runtime 只允许"事件类型 -> 世界槽位"的**确定性映射**(01 §6: World Runtime 不负责
   复杂判断)。零模型、零网络、零文本相似度 —— LLM 不在 Event -> World 的必经路径上。
2. Event 不可篡改: 输入一律 deepcopy,World 从不写回事件字段;World Change 只引用 event id,
   要看内容就按 id 回到 Event Runtime 的 events.jsonl。
3. World Update 必须可追溯到 Event: 每个 update 必带非空 source_events(已入库事件 id),
   verify_traceability() 做机械核对。
4. 三棵树不得混写(宪法 §4 绝对规则): World Update 只能改写 schemas/world_state.json 声明的
   槽位,且认知/记忆/成长类键名被显式拒绝。
5. 非法、不完整、过期或重复的事件**不得破坏当前 World State**: 先校验后改写,任何拒绝路径都在
   updates.jsonl 留痕,世界状态一字不动。
6. 02 §1 把 "World Update Request" 列为 Event Runtime 的输出之一,而 02 §2 规定"维护现在世界
   是什么样"属于 World Runtime。为不擅自移动 Runtime 边界,这里把 World Update 定义为**边界对象**:
   由 World Runtime 从已入库 Event 派生,Event Runtime 一字未改。归属歧义已在 DEVLOG 登记待裁决。
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.world.entity_runtime import EntityRuntime  # noqa: E402
from core.world.state_runtime import StateRuntime  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402


def _load(name: str) -> dict:
    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


# ================ Task 5 契约常量(调用方与测试都不得各自硬编码字面量) ================

#: World Update 可改写的槽位 —— 直接取自 schemas/world_state.json,不多不少。
#: 槽位集合由 Schema 决定,所以"给 World State 加槽位"必须走 schema 裁决,不能在代码里塞键。
_STATE_SCHEMA = _load("world_state.json")
STATE_SLOTS: tuple[str, ...] = tuple(k for k in _STATE_SCHEMA["properties"] if k != "timestamp")
LIST_SLOTS: tuple[str, ...] = ("people", "active_situations", "active_goals", "pending_tasks")
DICT_SLOTS: tuple[str, ...] = ("user", "location", "environment")
SCALAR_SLOTS: tuple[str, ...] = ("mode",)

#: 宪法 §5.1 九种 MODE 的规范英文名(UNKNOWN = 还不能确定,不是"没数据就猜")。
#: 是否把 enum 写进 world_state.json 属 Schema 层,已登记待裁决,Runtime 不私自加。
MODES: tuple[str, ...] = ("WORK", "SOCIAL", "DRIVE", "SLEEP", "SPORT", "STUDY",
                          "LEISURE", "EMERGENCY", "UNKNOWN")

#: 宪法 §4"事实 / 认知 / 成长 绝不混写"在 World 侧的可执行形态: 这些键名一旦被当作槽位提交
#: 就立即拒绝(而不是悄悄忽略),因为它说明有人想把推断写成世界事实。
FORBIDDEN_SLOTS: frozenset[str] = frozenset({
    "cognition", "memory", "growth", "belief", "judgment", "lesson",
    "decision", "importance", "tags",
})

#: World Update 结构字段。
WORLD_UPDATE_FIELDS: tuple[str, ...] = ("id", "rule", "source_events", "window", "slots", "trace")
WORLD_UPDATE_TRACE_FIELDS: tuple[str, ...] = ("event_ids", "raw_refs", "event_count")

#: 一次 Event -> World Update 的全部结局(closed set)。每一次尝试必须恰好落进一个,
#: 由 conservation() 机械保证"不吞事件、不重复记账"。
UPDATE_APPLIED = "applied"
UPDATE_NO_RULE = "no_rule"                  # 没有对应模板(08 E: 事件必须保留,但不得改变世界)
UPDATE_NO_SLOT_CHANGE = "no_slot_change"     # 有模板但世界已经如此(02 §3: 只保存变化)
UPDATE_STALE = "stale"                       # 早于当前世界快照 -> 不得把世界往回改
UPDATE_REPLAY = "replay_skipped"             # 同一 Event 已被吸收 -> 不得产生重复 World Update
UPDATE_REJECTED = "rejected"                 # 非法/不完整 Event -> 世界状态一字不动
UPDATE_DISPOSITIONS: frozenset[str] = frozenset({
    UPDATE_APPLIED, UPDATE_NO_RULE, UPDATE_NO_SLOT_CHANGE,
    UPDATE_STALE, UPDATE_REPLAY, UPDATE_REJECTED,
})

#: 台账行结构(比 World Update 更宽:它连"什么都没做"的尝试也要记)。
LEDGER_FIELDS: tuple[str, ...] = ("id", "event_id", "rule", "disposition", "change_id", "update", "note")

#: 进入 World 的东西被拒绝的原因闭集。
REJECT_CODES: frozenset[str] = frozenset({
    "NOT_AN_EVENT", "SCHEMA_INVALID", "UNPARSEABLE_TIMESTAMP", "MISSING_ID",
})


class WorldInputError(ValueError):
    """送进来的东西不是一个可使用的 Event(结构问题,不是语义问题)。"""

    def __init__(self, code: str, detail: str, field: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.field = code, detail, field


class WorldUpdateError(ValueError):
    """World Update 本身不合法(槽位越界 / 没有证据 / 混写三棵树)。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _ts(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp)


def _minutes(a: str, b: str) -> float:
    return abs((_ts(b) - _ts(a)).total_seconds()) / 60.0


# ============ 事件类型 -> 世界槽位(确定性规则表,零模型、零相似度) ============

def _rule_arrival(ev: dict, before: dict) -> tuple[str, dict]:
    #: 只认 Event 自带的 location_id,绝不兜底成某个具体场所 —— 没有位置证据就不写位置。
    slots: dict[str, Any] = {"mode": "WORK"}
    loc = ev.get("location_id")
    if loc:
        slots["location"] = {"id": loc}
    return "LOCATION_ARRIVAL", slots


def _rule_person_enter(ev: dict, before: dict) -> tuple[str, dict]:
    people = sorted(set(before["people"]) | {e for e in ev["entities"] if e.startswith("person_")})
    return "PARTICIPANT_ENTER", {"people": people}


def _rule_departure(ev: dict, before: dict) -> tuple[str, dict]:
    leaving = {e for e in ev["entities"] if e.startswith("person_")}
    if leaving:
        return "PARTICIPANT_LEAVE", {"people": [p for p in before["people"] if p not in leaving]}
    loc = ev.get("location_id")
    if loc and before["location"].get("id") == loc:
        return "LOCATION_DEPARTURE", {"location": {}, "mode": "UNKNOWN"}
    return "PARTICIPANT_LEAVE", {"people": list(before["people"])}


def _rule_contract(ev: dict, before: dict) -> tuple[str, dict]:
    situations = sorted(set(before["active_situations"]) | {"negotiation"})
    return "CONTRACT_DISCUSSION", {"active_situations": situations}


def _rule_price(ev: dict, before: dict) -> tuple[str, dict]:
    return "PRICE_DISCUSSION", {"user": {**before["user"], "talking": True, "topic": "price"}}


def _rule_silence(ev: dict, before: dict) -> tuple[str, dict]:
    return "USER_SILENCE", {"user": {**before["user"], "talking": False}}


def _rule_doc_open(ev: dict, before: dict) -> tuple[str, dict]:
    artifact = next((e for e in ev["entities"] if e.startswith("contract_")), None)
    return "DOCUMENT_OPEN", {"environment": {**before["environment"], "artifact": artifact}}


def _slot_add(prefix: str, slot: str, change_type: str):
    """任务/目标类规则: 值只取 entity id(task_*/goal_*),不解析自由文本。"""
    def rule(ev: dict, before: dict) -> tuple[str, dict]:
        ids = [e for e in ev["entities"] if e.startswith(prefix)]
        return change_type, {slot: sorted(set(before[slot]) | set(ids))}
    return rule


def _slot_remove(prefix: str, slot: str, change_type: str):
    def rule(ev: dict, before: dict) -> tuple[str, dict]:
        ids = {e for e in ev["entities"] if e.startswith(prefix)}
        return change_type, {slot: [x for x in before[slot] if x not in ids]}
    return rule


#: 事件类型 -> 规则。09 的 Sprint 1 只要求"现在世界是什么样",因此这里刻意不放任何需要
#: 语言理解的能力(如"张总提出降价"要不要升级为谈判紧张) —— 那属于 Relevance/Attention(Sprint 3)。
RULES: dict[str, Any] = {
    "arrival": _rule_arrival,
    "person_enter": _rule_person_enter,
    "departure": _rule_departure,
    "contract_discussion": _rule_contract,
    "price_negotiation": _rule_price,
    "silence": _rule_silence,
    "document_open": _rule_doc_open,
    "task_assigned": _slot_add("task_", "pending_tasks", "TASK_ASSIGNED"),
    "task_done": _slot_remove("task_", "pending_tasks", "TASK_CLOSED"),
    "goal_set": _slot_add("goal_", "active_goals", "GOAL_OPENED"),
    "goal_done": _slot_remove("goal_", "active_goals", "GOAL_CLOSED"),
}


# ============================ World Update 结构 ============================

def make_world_update(update_id: str, rule: str, events: Sequence[Mapping[str, Any]],
                      slots: Mapping[str, Any], window: Mapping[str, str] | None = None) -> dict:
    """把"这些事件建议这样改写世界"打包成显式对象。

    slots 是**建议的目标值**(不是 delta):delta 由 StateRuntime.diff 算出并写进 World Change,
    这正是 02 §3"不要只保存值,要保存变化"的落点。
    """
    evs = [dict(e) for e in events]
    stamps = [e["timestamp"] for e in evs]
    update = {
        "id": update_id,
        "rule": rule,
        "source_events": [e["id"] for e in evs],
        "window": dict(window) if window else {"start": min(stamps), "end": max(stamps)},
        "slots": copy.deepcopy(dict(slots)),
        "trace": {"event_ids": [e["id"] for e in evs],
                  "raw_refs": [e.get("raw_ref") for e in evs],
                  "event_count": len(evs)},
    }
    validate_world_update(update)
    return update


def validate_world_update(update: Any) -> None:
    """World Update 的结构契约。违反即抛错 —— 绝不"尽力而为"地应用半个更新。"""
    if not isinstance(update, Mapping):
        raise WorldUpdateError("UPDATE_NOT_A_MAPPING",
                               f"World Update 必须是 dict,收到 {type(update).__name__}")
    missing = [k for k in WORLD_UPDATE_FIELDS if k not in update]
    extra = sorted(set(update) - set(WORLD_UPDATE_FIELDS))
    if missing or extra:
        raise WorldUpdateError("UPDATE_FIELDS",
                               f"字段不符: 缺 {missing} 多 {extra}(应为 {list(WORLD_UPDATE_FIELDS)})")
    if set(update["trace"]) != set(WORLD_UPDATE_TRACE_FIELDS):
        raise WorldUpdateError("UPDATE_TRACE_FIELDS",
                               f"trace 字段应为 {list(WORLD_UPDATE_TRACE_FIELDS)}")
    if not update["source_events"]:
        raise WorldUpdateError("UPDATE_WITHOUT_EVIDENCE",
                              "World Update 必须能追溯到至少一个 Event,否则它只是猜测")
    bad = [i for i in update["source_events"] if not isinstance(i, str) or not i]
    if bad:
        raise WorldUpdateError("UPDATE_BAD_EVIDENCE", f"source_events 必须是非空 event id: {bad}")
    if list(update["trace"]["event_ids"]) != list(update["source_events"]):
        raise WorldUpdateError("UPDATE_TRACE_MISMATCH", "trace.event_ids 必须与 source_events 一致")
    if update["trace"]["event_count"] != len(update["source_events"]):
        raise WorldUpdateError("UPDATE_TRACE_COUNT", "trace.event_count 与 source_events 条数不符")
    win = update["window"]
    if set(win) != {"start", "end"}:
        raise WorldUpdateError("UPDATE_WINDOW", f"window 必须是 {{start,end}},收到 {dict(win)}")
    if win["start"] > win["end"]:
        raise WorldUpdateError("UPDATE_WINDOW_ORDER", f"窗口起点晚于终点: {dict(win)}")

    slots = update["slots"]
    if not isinstance(slots, Mapping) or not slots:
        raise WorldUpdateError("UPDATE_NO_SLOT", "World Update 必须至少提出一个槽位改写")
    for name, value in slots.items():
        if name in FORBIDDEN_SLOTS:
            raise WorldUpdateError("UPDATE_FORBIDDEN_SLOT",
                                  f"{name!r} 属于认知/记忆/成长层,不得写进 World State(宪法 §4)")
        if name not in STATE_SLOTS:
            raise WorldUpdateError("UPDATE_UNKNOWN_SLOT",
                                  f"{name!r} 不是 schemas/world_state.json 声明的槽位")
        errs = validate(value, _STATE_SCHEMA["properties"][name])
        if errs:
            raise WorldUpdateError("UPDATE_SLOT_TYPE", f"槽位 {name!r} 不合 schema: {errs}")
        if name == "mode" and value not in MODES:
            raise WorldUpdateError("UPDATE_BAD_MODE",
                                   f"MODE 必须是宪法 §5.1 的取值,收到 {value!r}(允许 {list(MODES)})")


# ================================ Runtime ================================

class WorldRuntime:
    """把 Event 变成"现在世界是什么样"的显式改写,并把每次变化写成 World Change(02 §2/§3)。"""

    contract = "02 §2 World"

    # ---- Task 5 契约常量:从 Runtime 本身可发现 ----
    STATE_SLOTS = STATE_SLOTS
    LIST_SLOTS = LIST_SLOTS
    DICT_SLOTS = DICT_SLOTS
    SCALAR_SLOTS = SCALAR_SLOTS
    MODES = MODES
    FORBIDDEN_SLOTS = FORBIDDEN_SLOTS
    WORLD_UPDATE_FIELDS = WORLD_UPDATE_FIELDS
    UPDATE_DISPOSITIONS = UPDATE_DISPOSITIONS
    REJECT_CODES = REJECT_CODES
    RULES = RULES

    def __init__(self, var_dir, entities: EntityRuntime | None = None, *, resume: bool = True) -> None:
        self.dir = Path(var_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.entities = entities if entities is not None else EntityRuntime(var_dir)
        self.state = StateRuntime()
        self._change_schema = _load("world_change.json")
        self._event_schema = _load("event.json")
        self._changes_path = self.dir / "changes.jsonl"
        self._state_path = self.dir / "world_state.jsonl"
        self._updates_path = self.dir / "updates.jsonl"
        self._changes: list[dict] = self._read(self._changes_path)
        self._ledger: list[dict] = self._read(self._updates_path)
        self._seq = len(self._changes)
        #: World Update 的 id 只与"曾经建过多少个 update"有关,和被拒的尝试无关。
        self._update_seq = sum(1 for ln in self._ledger if ln.get("update"))
        #: 已吸收账本: 世界对同一个 Event 只改写一次(重复投喂不得造出重复变化)。
        self._applied: set[str] = {e for c in self._changes for e in c["evidence_events"]}
        self.attempted = 0
        self.updated = 0
        self.no_change = 0
        self.stale_skipped = 0
        self.replay_skipped = 0
        self.rejected = 0
        self.rejections: list[str] = []
        if resume:
            self.resume()

    # ---------------- Event -> World Update -> World State ----------------

    def apply_update(self, event: Mapping[str, Any], *, strict: bool = False) -> dict | None:
        """Task 5 主入口。返回本次产生的 World Change;没有改变世界时返回 None(但仍留痕)。

        strict=True 时非法输入抛 WorldInputError(World Update 不合法一律抛,不受开关影响)。
        """
        self.attempted += 1
        try:
            ev = self._check_event(event)
            update = self._plan(ev)
        except (WorldInputError, WorldUpdateError) as exc:
            code = getattr(exc, "code", "WORLD_ERROR")
            self.rejections.append(code)
            self._record(event, rule=None, disposition=UPDATE_REJECTED, update=None,
                         note=f"{code}: {getattr(exc, 'detail', str(exc))}")
            if strict or isinstance(exc, WorldUpdateError):
                raise
            return None

        if update is None:
            self.no_change += 1
            self._record(ev, rule=None, disposition=UPDATE_NO_RULE, update=None)
            return None

        provenance = set(update["source_events"])
        if provenance <= self._applied:
            self.replay_skipped += 1
            self._record(ev, rule=update["rule"], disposition=UPDATE_REPLAY, update=update)
            return None

        before = self.state.snapshot()
        if before["timestamp"] and _ts(ev["timestamp"]) < _ts(before["timestamp"]):
            self.stale_skipped += 1
            self._record(ev, rule=update["rule"], disposition=UPDATE_STALE, update=update)
            return None

        after = self._merge(before, update["slots"], ev["timestamp"])
        diff = {k: v for k, v in StateRuntime.diff(before, after).items() if k != "timestamp"}
        if not diff:
            self.no_change += 1
            self._record(ev, rule=update["rule"], disposition=UPDATE_NO_SLOT_CHANGE, update=update)
            return None

        self.state.replace(after)
        self._seq += 1
        self.updated += 1
        change = {
            "id": f"chg_{self._seq:03d}",
            "window": dict(update["window"]),
            "change_type": update["rule"],
            "before": StateRuntime.changed_slots(diff, "before"),
            "after": StateRuntime.changed_slots(diff, "after"),
            "entities": list(ev["entities"]),
            "evidence_events": list(update["source_events"]),
            "confidence": ev["confidence"],
        }
        errs = validate(change, self._change_schema)
        if errs:
            raise ValueError(f"World Change 不符合 schemas/world_change.json: {errs}")
        self._changes.append(change)
        self._applied |= provenance
        self._append(self._changes_path, change)
        self._append(self._state_path, self.state.snapshot())
        self._record(ev, rule=update["rule"], disposition=UPDATE_APPLIED, update=update,
                     change_id=change["id"])
        self._sync_entities(ev)
        return change

    # ---------------- 校验 / 规划 / 落盘 ----------------

    def _check_event(self, event: Any) -> dict:
        """Event 必须完整合法,而且**只读**:任何情况下都不改调用方的对象。"""
        if not isinstance(event, Mapping):
            raise WorldInputError("NOT_AN_EVENT",
                                  f"World 只接受标准 Event dict,收到 {type(event).__name__}")
        ev = copy.deepcopy(dict(event))
        errs = validate(ev, self._event_schema)
        if errs:
            hint = "(Raw Signal 属于 Perception Runtime 的输入,不得直接进 World)" if "modality" in ev else ""
            raise WorldInputError("SCHEMA_INVALID", f"不符合 schemas/event.json{hint}: {errs}")
        if not ev["id"]:
            raise WorldInputError("MISSING_ID", "Event id 为空,无法建立可追溯的世界")
        try:
            _ts(ev["timestamp"])
        except (KeyError, ValueError) as exc:
            raise WorldInputError("UNPARSEABLE_TIMESTAMP",
                                  f"时间戳无法解析,世界无法保证按时间更新: {exc}", "timestamp") from exc
        return ev

    def _plan(self, ev: dict) -> dict | None:
        """Event -> World Update。没有模板的事件保持"可见但不改变世界"(08 E)。"""
        rule = RULES.get(ev["type"])
        if rule is None:
            return None
        before = self.state.snapshot()
        change_type, slots = rule(ev, before)
        if change_type == "PRICE_DISCUSSION" and self._escalating(before["timestamp"], ev["timestamp"]):
            change_type = "NEGOTIATION_ESCALATION"
        self._update_seq += 1
        return make_world_update(f"wup_{self._update_seq:03d}", change_type, [ev], slots)

    @staticmethod
    def _merge(before: dict, patches: Mapping[str, Any], timestamp: str) -> dict:
        """槽位改写 + 时间前进。

        timestamp 只在**真的应用了**的时候前进(02 §3: 只保存变化):无模板/无变化/被拒的
        事件不得把世界时间拖走 —— 那会让"世界现在几点"变成噪声的函数。
        """
        after = copy.deepcopy(before)
        after.update(copy.deepcopy(dict(patches)))
        after["timestamp"] = timestamp
        return after

    def _escalating(self, last_ts: str, now_ts: str) -> bool:
        """30 分钟内再次出现价格讨论 -> 升级为 NEGOTIATION_ESCALATION(03 §World Change 示例)。"""
        for chg in reversed(self._changes[-8:]):
            if chg["change_type"] not in ("PRICE_DISCUSSION", "NEGOTIATION_ESCALATION"):
                continue
            if not last_ts:
                return True
            return _minutes(chg["window"]["end"], now_ts) <= 30.0
        return False

    def _record(self, event: Any, *, rule: str | None, disposition: str, update: dict | None,
                 change_id: str | None = None, note: str = "") -> None:
        """每一次尝试都必须在 updates.jsonl 留痕 —— 包括被拒与"世界没变"。

        非法 Event 连 id 都没有,这一行仍要落盘,否则"被拒"就成了无痕操作。
        """
        if disposition not in UPDATE_DISPOSITIONS:
            raise AssertionError(f"未知 disposition(违反 Task5 闭集): {disposition!r}")
        eid = event.get("id") if isinstance(event, Mapping) else None
        line = {
            "id": f"wuplog_{len(self._ledger) + 1:04d}",
            "event_id": eid if isinstance(eid, str) and eid else None,
            "rule": rule,
            "disposition": disposition,
            "change_id": change_id,
            "update": update,
            "note": note,
        }
        self._ledger.append(line)
        self._append(self._updates_path, line)
        if disposition == UPDATE_REJECTED:
            self.rejected += 1

    # ---------------- 恢复 / 自检 ----------------

    def resume(self) -> "WorldRuntime":
        """重启后世界必须还是同一个世界: 快照、已吸收账本、计数都从产物里重建。"""
        snaps = self._read(self._state_path)
        if snaps:
            self.state.replace(snaps[-1])
        counts = {d: 0 for d in UPDATE_DISPOSITIONS}
        for line in self._ledger:
            counts[line["disposition"]] = counts.get(line["disposition"], 0) + 1
        if self._ledger:
            self.updated = counts[UPDATE_APPLIED]
            self.no_change = counts[UPDATE_NO_RULE] + counts[UPDATE_NO_SLOT_CHANGE]
            self.stale_skipped = counts[UPDATE_STALE]
            self.replay_skipped = counts[UPDATE_REPLAY]
            self.rejected = counts[UPDATE_REJECTED]
            self.attempted = len(self._ledger)
        elif self._changes:
            #: 老目录(本仓库 Task 5 之前落的 var/)没有 updates.jsonl: 已吸收判定仍由 changes.jsonl
            #: 提供,计数从 changes 条数保守恢复,不假装知道被拒了多少。
            self.updated = len(self._changes)
        return self

    def conservation(self) -> dict:
        """Event -> World Update 的守恒:每一次尝试都要有下落。"""
        counts = {d: 0 for d in UPDATE_DISPOSITIONS}
        for line in self._ledger:
            counts[line["disposition"]] = counts.get(line["disposition"], 0) + 1
        out = {"attempted": self.attempted, "ledger_lines": len(self._ledger),
               "changes": len(self._changes), **counts}
        out["sum"] = sum(counts.values())
        out["balanced"] = (out["sum"] == self.attempted == len(self._ledger))
        return out

    def verify_conservation(self) -> list[str]:
        c = self.conservation()
        bad = []
        if not c["balanced"]:
            bad.append(f"尝试数与台账不守恒: {c}")
        if c["applied"] != c["changes"]:
            bad.append(f"applied 台账条数({c['applied']}) != World Change 条数({c['changes']})")
        if c["applied"] != self.updated:
            bad.append(f"applied 台账条数({c['applied']}) != updated 计数({self.updated})")
        return bad

    def verify_traceability(self, known_event_ids: set[str] | None = None) -> list[str]:
        """每个 World Change 必须能回到 Event;每个 applied 台账必须指向真实 change。"""
        bad: list[str] = []
        for chg in self._changes:
            ev = chg["evidence_events"]
            if not ev:
                bad.append(f"{chg['id']} 没有 evidence_events")
                continue
            if known_event_ids is not None:
                unknown = [e for e in ev if e not in known_event_ids]
                if unknown:
                    bad.append(f"{chg['id']} 的证据事件不在 Event Runtime 库内: {unknown}")
        applied = {ln["change_id"] for ln in self._ledger if ln["disposition"] == UPDATE_APPLIED}
        missing = applied - {c["id"] for c in self._changes}
        if missing:
            bad.append(f"台账声称已应用但找不到 World Change: {sorted(missing)}")
        return bad

    def verify_ledger(self) -> list[str]:
        bad: list[str] = []
        for ln in self._ledger:
            if set(ln) - set(LEDGER_FIELDS):
                bad.append(f"台账行字段越界: {sorted(set(ln))}")
            if ln["disposition"] not in UPDATE_DISPOSITIONS:
                bad.append(f"台账行 {ln['id']} 的 disposition 不在闭集内: {ln['disposition']}")
            upd = ln.get("update")
            if upd and "note" not in upd:
                try:
                    validate_world_update(upd)
                except WorldUpdateError as exc:
                    bad.append(f"台账里的 World Update 不合法({ln['id']}): {exc}")
        return bad

    # ---------------- 查询 / 回放 ----------------

    def current_state(self) -> dict:
        return self.state.snapshot()

    def all_changes(self) -> list[dict]:
        return copy.deepcopy(self._changes)

    def update_ledger(self) -> list[dict]:
        return copy.deepcopy(self._ledger)

    def dispositions_for(self, event_id: str) -> list[str]:
        return [ln["disposition"] for ln in self._ledger if ln["event_id"] == event_id]

    @staticmethod
    def _read(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    @staticmethod
    def _append(path: Path, obj: dict) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def _sync_entities(self, event: dict) -> None:
        """事件里出现的实体必须进入 Entity Store(08 A: Entity 不因 session 结束而丢失)。"""
        for eid in event["entities"]:
            kind = ("person" if eid.startswith("person_") else "place" if eid.startswith("place_")
                    else "person" if eid == "user" else "object")
            self.entities.ensure(eid, kind)

    def replay(self, events: list[dict], target_dir=None) -> "WorldRuntime":
        """从事件流重建世界(08 A: Time/Space 可回放)。

        resume=False: 回放是"从零重放",不得受目标目录里的历史产物影响。
        """
        tgt = Path(target_dir) if target_dir else self.dir.parent / f"{self.dir.name}_replay"
        fresh = WorldRuntime(tgt, EntityRuntime(tgt), resume=False)
        for ev in events:
            fresh.apply_update(ev)
        return fresh
