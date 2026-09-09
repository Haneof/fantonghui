"""WorldRuntime —— 契约来源: 02 §2 World (与 §3 State 配合产出 World Change).

输入: Event / Entity / State Update。输出: World State、World Change(02 §2)。
World Runtime 不负责复杂判断(01 §6),因此这里只允许"事件类型 -> 世界槽位"的确定性映射。
未知事件不改变世界,但事件本身已经落库(04 §6 / 08 E: 不得因为无模板而丢弃)。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.world.entity_runtime import EntityRuntime  # noqa: E402
from core.world.state_runtime import StateRuntime  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402


def _load(name: str) -> dict:
    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _rule_arrival(ev, before):
    return "LOCATION_ARRIVAL", {"location": {"id": ev.get("location_id") or "place_004"}, "mode": "WORK"}


def _rule_person_enter(ev, before):
    people = sorted(set(before["people"]) | {e for e in ev["entities"] if e.startswith("person_")})
    return "PARTICIPANT_ENTER", {"people": people}


def _rule_contract(ev, before):
    return "CONTRACT_DISCUSSION", {"active_situations": sorted(set(before["active_situations"]) | {"negotiation"})}


def _rule_price(ev, before):
    return "PRICE_DISCUSSION", {"user": {**before["user"], "talking": True, "topic": "price"}}


def _rule_silence(ev, before):
    return "USER_SILENCE", {"user": {**before["user"], "talking": False}}


def _rule_doc_open(ev, before):
    artifact = next((e for e in ev["entities"] if e.startswith("contract_")), None)
    return "DOCUMENT_OPEN", {"environment": {**before["environment"], "artifact": artifact}}


#: 事件类型 -> 世界槽位映射(Sprint 1 的确定性规则,不引入模型)
RULES = {
    "arrival": _rule_arrival,
    "person_enter": _rule_person_enter,
    "contract_discussion": _rule_contract,
    "price_negotiation": _rule_price,
    "silence": _rule_silence,
    "document_open": _rule_doc_open,
}


def _minutes(a: str, b: str) -> float:
    import datetime as dt

    return abs((dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds()) / 60.0


class WorldRuntime:
    """维护"现在世界是什么样",并把每次变化显式写成 World Change(02 §2/§3)。"""

    contract = "02 §2 World"

    def __init__(self, var_dir, entities: EntityRuntime | None = None) -> None:
        self.dir = Path(var_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.entities = entities if entities is not None else EntityRuntime(var_dir)
        self.state = StateRuntime()
        self._change_schema = _load("world_change.json")
        self._state_schema = _load("world_state.json")
        self._changes_path = self.dir / "changes.jsonl"
        self._state_path = self.dir / "world_state.jsonl"
        self._changes: list[dict] = [json.loads(ln) for ln in
                                    (self._changes_path.read_text(encoding="utf-8").splitlines() if self._changes_path.exists() else [])]
        self._seq = len(self._changes)
        self.updated = 0
        self.no_change = 0

    # ---------- 主流程: Event -> World Update -> World Change ----------

    def apply_update(self, event: dict) -> dict | None:
        rule = RULES.get(event["type"])
        before = self.state.snapshot()
        if rule is None:
            self.no_change += 1
            return None
        change_type, patches = rule(event, before)
        if change_type == "PRICE_DISCUSSION" and self._escalating(before["timestamp"], event["timestamp"]):
            change_type = "NEGOTIATION_ESCALATION"

        after = self._merge(before, patches, event["timestamp"])
        if after == before:
            self.no_change += 1
            return None
        self.state.replace(after)

        diff = {k: v for k, v in StateRuntime.diff(before, after).items() if k != "timestamp"}
        if not diff:
            self.no_change += 1
            return None
        self._seq += 1
        self.updated += 1
        change = {
            "id": f"chg_{self._seq:03d}",
            "window": {"start": event["timestamp"], "end": event["timestamp"]},
            "change_type": change_type,
            "before": StateRuntime.changed_slots(diff, "before"),
            "after": StateRuntime.changed_slots(diff, "after"),
            "entities": list(event["entities"]),
            "evidence_events": [event["id"]],
            "confidence": event["confidence"],
        }
        errs = validate(change, self._change_schema)
        if errs:
            raise ValueError(f"World Change 不符合 schemas/world_change.json: {errs}")
        self._changes.append(change)
        self._append(self._changes_path, change)
        self._append(self._state_path, self.state.snapshot())
        self._sync_entities(event)
        return change

    @staticmethod
    def _append(path: Path, obj: dict) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def _sync_entities(self, event: dict) -> None:
        """事件里出现的实体必须进入 Entity Store(08 A: Entity 不因 session 结束而丢失)。"""
        for eid in event["entities"]:
            kind = "person" if eid.startswith("person_") else "place" if eid.startswith("place_") else "object"
            self.entities.ensure(eid, kind)

    @staticmethod
    def _merge(before: dict, patches: dict, timestamp: str) -> dict:
        after = copy.deepcopy(before)
        after.update(copy.deepcopy(patches))
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

    # ---------- 快照与回放 ----------

    def current_state(self) -> dict:
        return self.state.snapshot()

    def all_changes(self) -> list[dict]:
        return copy.deepcopy(self._changes)

    def replay(self, events: list[dict], target_dir=None) -> "WorldRuntime":
        """从事件流重建世界(08 A: Time/Space 可回放)。"""
        tgt = Path(target_dir) if target_dir else self.dir.parent / f"{self.dir.name}_replay"
        fresh = WorldRuntime(tgt, EntityRuntime(tgt))
        for ev in events:
            fresh.apply_update(ev)
        return fresh
