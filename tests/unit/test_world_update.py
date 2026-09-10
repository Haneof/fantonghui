"""Task 5 —— Event -> World Update -> World State 契约测试。

对应验收:
  案例 A 用户进入办公室      -> location 改变
  案例 B 张总进入            -> 当前人物状态变化
  案例 C 开始合同谈判        -> 当前活动/场景变化
  案例 D 多事件连续发生      -> World State 按时间正确更新
  案例 E 同一 Event 重放     -> 不产生重复 World Update
  案例 F 非法/不完整 Event   -> 不得破坏当前 World State
外加: World Update 数据结构契约、可追溯性、Event 不可篡改、三棵树不混写、
      守恒不变式、重启恢复、以及"Event->World 路径上没有模型/网络"。

时间戳口径: 所有测试事件都带显式完整 ISO 时间(2026-09-09T..+08:00)。
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.world import world_runtime as wr  # noqa: E402
from core.world.world_runtime import (  # noqa: E402
    LEDGER_FIELDS, MODES, STATE_SLOTS, UPDATE_APPLIED, UPDATE_NO_RULE, UPDATE_NO_SLOT_CHANGE,
    UPDATE_REJECTED, UPDATE_REPLAY, UPDATE_STALE, WorldInputError, WorldRuntime,
    WorldUpdateError, make_world_update, validate_world_update,
)
from tests.scenario.helpers import play  # noqa: E402
from tools import forbidden_scan as fs  # noqa: E402

DAY = "2026-09-09"


def ev(eid: str, hhmmss: str, type_: str, *, content: str = "x", source: str = "mic",
       entities=None, location_id=None, confidence: float = 0.9) -> dict:
    """构造一个符合 schemas/event.json 的合法事件(World 的输入合同就是它)。"""
    return {"id": eid, "timestamp": f"{DAY}T{hhmmss}+08:00", "source": source, "type": type_,
            "content": content, "entities": list(entities or []), "location_id": location_id,
            "confidence": confidence, "raw_ref": f"perception://temp/{eid}"}


class Base(unittest.TestCase):
    def setUp(self):
        self.var = Path(tempfile.mkdtemp(prefix="aios-wu-"))
        self.world = WorldRuntime(self.var / "world")

    def tearDown(self):
        shutil.rmtree(self.var, ignore_errors=True)


# ================================ 案例 A/B/C/D ================================

class TestWorldUpdateCases(Base):
    def test_A_arrival_changes_location_and_mode(self):
        before = self.world.current_state()
        self.assertEqual(before["location"], {})
        self.assertEqual(before["mode"], "UNKNOWN")

        chg = self.world.apply_update(ev("evt_A1", "09:00:00", "arrival", location_id="place_004"))
        state = self.world.current_state()
        self.assertEqual(state["location"], {"id": "place_004"}, "进入办公室必须改变 location")
        self.assertEqual(state["mode"], "WORK", "MODE 必须来自宪法 §5.1 的取值")
        self.assertEqual(chg["change_type"], "LOCATION_ARRIVAL")
        self.assertEqual(sorted(chg["before"]), ["location", "mode"])
        self.assertEqual(chg["before"]["mode"], "UNKNOWN", "必须显式记录'从什么变到什么'")

    def test_A_arrival_without_location_evidence_does_not_invent_a_place(self):
        """没有位置证据就不写 location —— 绝不兜底成某个具体场所(那是编造)。"""
        self.world.apply_update(ev("evt_A2", "09:00:00", "arrival", location_id=None))
        self.assertEqual(self.world.current_state()["location"], {})
        self.assertEqual(self.world.current_state()["mode"], "WORK")

    def test_B_person_enter_changes_people(self):
        self.world.apply_update(ev("evt_B1", "09:00:00", "arrival", location_id="place_004"))
        chg = self.world.apply_update(ev("evt_B2", "09:05:00", "person_enter",
                                        content="张总进入", entities=["person_017"]))
        state = self.world.current_state()
        self.assertEqual(state["people"], ["person_017"], "张总进入必须改变当前人物状态")
        self.assertEqual(chg["change_type"], "PARTICIPANT_ENTER")
        self.assertEqual(chg["evidence_events"], ["evt_B2"])
        #: 人物实体必须落到 Entity Store(08 A: 不因 session 结束丢失)
        self.assertIsNotNone(self.world.entities.get("person_017"))
        self.assertEqual(self.world.entities.get("person_017")["type"], "person")

    def test_B_departure_removes_only_the_leaving_person(self):
        self.world.apply_update(ev("evt_B3", "09:00:00", "person_enter", entities=["person_017"]))
        self.world.apply_update(ev("evt_B4", "09:01:00", "person_enter", entities=["person_021"]))
        chg = self.world.apply_update(ev("evt_B5", "09:02:00", "departure", entities=["person_017"]))
        self.assertEqual(self.world.current_state()["people"], ["person_021"])
        self.assertEqual(chg["change_type"], "PARTICIPANT_LEAVE")

    def test_C_contract_negotiation_changes_active_situation(self):
        chg = self.world.apply_update(ev("evt_C1", "09:06:00", "contract_discussion",
                                        content="开始合同谈判", entities=["contract_003"]))
        state = self.world.current_state()
        self.assertEqual(state["active_situations"], ["negotiation"], "活动/场景必须发生变化")
        self.assertEqual(chg["change_type"], "CONTRACT_DISCUSSION")
        self.assertEqual(chg["before"]["active_situations"], [])
        self.assertEqual(chg["after"]["active_situations"], ["negotiation"])

    def test_C_repeated_same_situation_produces_no_duplicate_change(self):
        self.world.apply_update(ev("evt_C2", "09:06:00", "contract_discussion"))
        n = len(self.world.all_changes())
        again = self.world.apply_update(ev("evt_C3", "09:07:00", "contract_discussion"))
        self.assertIsNone(again, "世界已经如此时不得再造一条 World Change(02 §3 只保存变化)")
        self.assertEqual(len(self.world.all_changes()), n)
        self.assertEqual(self.world.dispositions_for("evt_C3"), [UPDATE_NO_SLOT_CHANGE])

    def test_D_seven_events_apply_in_time_order(self):
        events = [ev(f"evt_D{i}", t, ty, entities=en, location_id=loc)
                  for i, (t, ty, en, loc) in enumerate([
                      ("09:00:00", "arrival", ["place_004"], "place_004"),
                      ("09:05:00", "person_enter", ["person_017"], None),
                      ("09:06:00", "contract_discussion", ["contract_003"], None),
                      ("09:08:00", "price_negotiation", ["person_017"], None),
                      ("09:10:00", "silence", [], None),
                      ("09:12:00", "document_open", ["contract_003"], None),
                      ("09:15:00", "price_negotiation", [], None),
                  ])]
        changes = [c for c in (self.world.apply_update(e) for e in events) if c]
        self.assertEqual([c["change_type"] for c in changes], [
            "LOCATION_ARRIVAL", "PARTICIPANT_ENTER", "CONTRACT_DISCUSSION", "PRICE_DISCUSSION",
            "USER_SILENCE", "DOCUMENT_OPEN", "NEGOTIATION_ESCALATION"])
        #: 时间必须单调前进
        stamps = [c["window"]["end"] for c in changes]
        self.assertEqual(stamps, sorted(stamps))
        #: 最终状态必须同时反映所有维度,而不是只记得最后一条
        state = self.world.current_state()
        self.assertEqual(state["timestamp"], f"{DAY}T09:15:00+08:00", "世界时间必须随应用前进")
        self.assertEqual(state["location"], {"id": "place_004"})
        self.assertEqual(state["mode"], "WORK")
        self.assertEqual(state["people"], ["person_017"])
        self.assertEqual(state["active_situations"], ["negotiation"])
        self.assertEqual(state["environment"]["artifact"], "contract_003")
        self.assertEqual(state["user"]["talking"], True)

    def test_D_stale_event_cannot_walk_the_world_backwards(self):
        self.world.apply_update(ev("evt_D9", "10:00:00", "person_enter", entities=["person_021"]))
        before = self.world.current_state()
        out = self.world.apply_update(ev("evt_D8", "09:00:00", "person_enter", entities=["person_017"]))
        self.assertIsNone(out)
        self.assertEqual(self.world.current_state(), before, "过期事件不得把世界改回旧样子")
        self.assertEqual(self.world.stale_skipped, 1)
        self.assertEqual(self.world.dispositions_for("evt_D8"), [UPDATE_STALE])

    def test_goals_and_tasks_use_only_entity_ids(self):
        """目标/任务在已有 schema 支持范围内接通: 值只取 task_*/goal_* 实体 id。"""
        self.world.apply_update(ev("evt_G1", "09:00:00", "goal_set", entities=["goal_007"]))
        self.assertEqual(self.world.current_state()["active_goals"], ["goal_007"])
        self.world.apply_update(ev("evt_G2", "09:01:00", "task_assigned", entities=["task_042"]))
        self.assertEqual(self.world.current_state()["pending_tasks"], ["task_042"])
        self.world.apply_update(ev("evt_G3", "09:02:00", "task_done", entities=["task_042"]))
        self.assertEqual(self.world.current_state()["pending_tasks"], [])
        self.world.apply_update(ev("evt_G4", "09:03:00", "goal_done", entities=["goal_007"]))
        self.assertEqual(self.world.current_state()["active_goals"], [])
        types = [c["change_type"] for c in self.world.all_changes()]
        self.assertEqual(types, ["GOAL_OPENED", "TASK_ASSIGNED", "TASK_CLOSED", "GOAL_CLOSED"])


# ================================ 案例 E: 重放 ================================

class TestReplayIdempotence(Base):
    def test_E_same_event_replayed_does_not_reupdate_world(self):
        first = self.world.apply_update(ev("evt_E1", "09:00:00", "person_enter", entities=["person_017"]))
        self.assertIsNotNone(first)
        n = len(self.world.all_changes())

        again = self.world.apply_update(ev("evt_E1", "09:00:00", "person_enter", entities=["person_017"]))
        self.assertIsNone(again, "同一 Event 重放不得产生第二次 World Update")
        self.assertEqual(len(self.world.all_changes()), n)
        self.assertEqual(self.world.current_state()["people"], ["person_017"])
        self.assertEqual(self.world.replay_skipped, 1)
        self.assertEqual(self.world.dispositions_for("evt_E1"), [UPDATE_APPLIED, UPDATE_REPLAY])

    def test_E_replayed_event_still_leaves_a_ledger_trace(self):
        line = [ln for ln in self.world.update_ledger() if ln["disposition"] == UPDATE_REPLAY]
        self.world.apply_update(ev("evt_E2", "09:00:00", "arrival", location_id="place_004"))
        self.world.apply_update(ev("evt_E2", "09:00:00", "arrival", location_id="place_004"))
        line = [ln for ln in self.world.update_ledger() if ln["disposition"] == UPDATE_REPLAY]
        self.assertEqual(len(line), 1)
        self.assertEqual(line[0]["event_id"], "evt_E2")
        self.assertEqual(line[0]["rule"], "LOCATION_ARRIVAL", "被跳过的重放也要说清它本来想改哪条规则")

    def test_E_whole_timeline_replayed_from_store_is_stable(self):
        r = play(self.var / "pipeline", noise=0)
        events = r["events"]
        w1 = WorldRuntime(self.var / "w1")
        for e in events:
            w1.apply_update(e)
        after_first = (w1.current_state(), [c["change_type"] for c in w1.all_changes()])
        for e in events:  # 整条时间线再来一遍
            w1.apply_update(e)
        self.assertEqual(w1.current_state(), after_first[0], "整条重放不得改写世界")
        self.assertEqual([c["change_type"] for c in w1.all_changes()], after_first[1])
        self.assertEqual(w1.updated, len(after_first[1]))

    def test_E_replay_never_touches_event_store_files(self):
        r = play(self.var / "pipeline", noise=0)
        events = r["events"]
        w = WorldRuntime(self.var / "w2")
        for e in events:
            w.apply_update(e)
        blob = (self.var / "pipeline" / "events" / "events.jsonl").read_bytes()
        for e in events:
            w.apply_update(e)
        self.assertEqual((self.var / "pipeline" / "events" / "events.jsonl").read_bytes(), blob,
                         "World 重放不得回写 Event Runtime 的产物")


# ================================ 案例 F: 非法输入 ================================

class TestInvalidEvents(Base):
    def test_F_incomplete_event_rejected_and_state_untouched(self):
        self.world.apply_update(ev("evt_F0", "09:00:00", "arrival", location_id="place_004"))
        before = self.world.current_state()
        n = len(self.world.all_changes())

        broken = {"id": "evt_F1", "timestamp": f"{DAY}T09:10:00+08:00", "type": "person_enter"}
        out = self.world.apply_update(broken)
        self.assertIsNone(out)
        self.assertEqual(self.world.current_state(), before, "不完整 Event 不得破坏当前 World State")
        self.assertEqual(len(self.world.all_changes()), n)
        self.assertEqual(self.world.rejected, 1)
        self.assertEqual(self.world.rejections, ["SCHEMA_INVALID"])

    def test_F_non_mapping_and_garbage_inputs_are_rejected_not_crashed(self):
        for bad in (None, "evt", 42, ["evt"], {"id": "x"}):
            with self.subTest(bad=repr(bad)):
                self.assertIsNone(self.world.apply_update(bad))
        self.assertEqual(set(self.world.rejections), {"NOT_AN_EVENT", "SCHEMA_INVALID"})
        self.assertEqual(self.world.current_state(), wr.StateRuntime().snapshot())

    def test_F_unparseable_timestamp_rejected(self):
        e = ev("evt_F2", "09:00:00", "arrival", location_id="place_004")
        e["timestamp"] = "昨天下午"
        self.assertIsNone(self.world.apply_update(e))
        self.assertEqual(self.world.rejections, ["UNPARSEABLE_TIMESTAMP"])

    def test_F_empty_id_rejected(self):
        e = ev("evt_F3", "09:00:00", "arrival", location_id="place_004")
        e["id"] = ""
        self.assertIsNone(self.world.apply_update(e))
        self.assertEqual(self.world.rejections, ["MISSING_ID"])

    def test_F_raw_signal_hinted_in_error(self):
        """Raw Signal 直接喂给 World 必须被拒,而且要说清它属于 Perception Runtime。"""
        out = self.world.apply_update({"signal_id": "s1", "modality": "text",
                                       "payload": {"text": "到公司"}})
        self.assertIsNone(out)
        line = [ln for ln in self.world.update_ledger() if ln["disposition"] == UPDATE_REJECTED]
        self.assertEqual(len(line), 1)
        self.assertIn("Perception Runtime", line[0]["note"])

    def test_F_rejects_are_recorded_even_without_an_id(self):
        self.world.apply_update(42)
        line = self.world.update_ledger()[-1]
        self.assertEqual(line["disposition"], UPDATE_REJECTED)
        self.assertIsNone(line["event_id"])
        self.assertIn("NOT_AN_EVENT", line["note"])

    def test_F_state_still_correct_after_rejects(self):
        """被拒之后世界必须还能继续正常更新(拒绝不等于世界报废)。"""
        self.world.apply_update({"not": "an event"})
        chg = self.world.apply_update(ev("evt_F4", "09:00:00", "person_enter", entities=["person_017"]))
        self.assertIsNotNone(chg)
        self.assertEqual(self.world.current_state()["people"], ["person_017"])

    def test_F_strict_mode_raises_loudly(self):
        with self.assertRaises(WorldInputError) as ctx:
            self.world.apply_update({"id": "x"}, strict=True)
        self.assertEqual(ctx.exception.code, "SCHEMA_INVALID")

    def test_F_event_is_never_mutated(self):
        """原 Event 不可篡改: World 只读输入。"""
        e = ev("evt_F5", "09:00:00", "person_enter", entities=["person_017"])
        snapshot = json.dumps(e, sort_keys=True, ensure_ascii=False)
        self.world.apply_update(e)
        self.assertEqual(json.dumps(e, sort_keys=True, ensure_ascii=False), snapshot)
        e["entities"].append("person_HACK")
        self.assertNotIn("person_HACK", self.world.current_state()["people"])


# ==================== World Update 数据结构契约 ====================

class TestWorldUpdateStructure(Base):
    def test_slot_set_equals_schema_slots(self):
        """可写槽位必须由 schemas/world_state.json 决定,不能是代码里的另一套定义。"""
        props = set(json.loads((ROOT / "schemas/world_state.json").read_text(encoding="utf-8"))["properties"])
        self.assertEqual(set(STATE_SLOTS), props - {"timestamp"})

    def test_update_has_exact_fields_and_evidence(self):
        e = ev("evt_U1", "09:00:00", "person_enter", entities=["person_017"])
        u = make_world_update("wup_test", "PARTICIPANT_ENTER", [e], {"people": ["person_017"]})
        self.assertEqual(tuple(u), wr.WORLD_UPDATE_FIELDS)
        self.assertEqual(u["source_events"], ["evt_U1"], "World Update 必须能追溯到 Event")
        self.assertEqual(u["trace"]["raw_refs"], ["perception://temp/evt_U1"])
        self.assertEqual(u["trace"]["event_count"], 1)
        self.assertEqual(u["window"], {"start": e["timestamp"], "end": e["timestamp"]})

    def test_update_without_evidence_is_refused(self):
        u = make_world_update("wup_x", "R", [ev("evt_U2", "09:00:00", "person_enter")], {"people": []})
        u["source_events"] = []
        with self.assertRaises(WorldUpdateError) as ctx:
            validate_world_update(u)
        self.assertEqual(ctx.exception.code, "UPDATE_WITHOUT_EVIDENCE")

    def test_unknown_slot_is_refused(self):
        with self.assertRaises(WorldUpdateError) as ctx:
            make_world_update("wup_y", "R", [ev("evt_U3", "09:00:00", "arrival")], {"weather": "sunny"})
        self.assertEqual(ctx.exception.code, "UPDATE_UNKNOWN_SLOT")

    def test_cognition_memory_growth_cannot_be_written(self):
        """宪法 §4: 事实/认知/成长不得混写 —— 想把它写进 World State 就是越权。"""
        e = ev("evt_U4", "09:00:00", "arrival", location_id="place_004")
        before = self.world.current_state()
        for slot in wr.FORBIDDEN_SLOTS:
            with self.subTest(slot=slot):
                with self.assertRaises(WorldUpdateError) as ctx:
                    make_world_update("wup_z", "R", [e], {slot: "anything"})
                self.assertEqual(ctx.exception.code, "UPDATE_FORBIDDEN_SLOT")
        self.world.apply_update(e)
        self.assertEqual(set(self.world.current_state()), set(before),
                         "World State 的键集合必须永远等于 schema 声明的槽位")

    def test_bad_mode_value_is_refused(self):
        with self.assertRaises(WorldUpdateError) as ctx:
            make_world_update("wup_m", "R", [ev("evt_U5", "09:00:00", "arrival")], {"mode": "谈判中"})
        self.assertEqual(ctx.exception.code, "UPDATE_BAD_MODE")

    def test_mode_always_within_constitution_enum(self):
        r = play(self.var / "pipeline", noise=3)
        self.assertIn(r["world"].current_state()["mode"], MODES)
        for ln in r["world"].update_ledger():
            upd = ln.get("update") or {}
            if upd.get("slots", {}).get("mode"):
                self.assertIn(upd["slots"]["mode"], MODES)

    def test_slot_value_type_checked(self):
        with self.assertRaises(WorldUpdateError) as ctx:
            make_world_update("wup_t", "R", [ev("evt_U6", "09:00:00", "arrival")], {"people": "person_017"})
        self.assertEqual(ctx.exception.code, "UPDATE_SLOT_TYPE")

    def test_window_must_be_ordered(self):
        with self.assertRaises(WorldUpdateError) as ctx:
            make_world_update("wup_w", "R", [ev("evt_U7", "09:00:00", "arrival")],
                             {"mode": "WORK"}, {"start": "2026-09-09T10:00:00+08:00",
                                                "end": "2026-09-09T09:00:00+08:00"})
        self.assertEqual(ctx.exception.code, "UPDATE_WINDOW_ORDER")


# ==================== 守恒 / 台账 / 追溯 ====================

class TestLedgerInvariants(Base):
    def test_every_attempt_lands_in_exactly_one_disposition(self):
        events = [ev("evt_L1", "09:00:00", "arrival", location_id="place_004"),
                  ev("evt_L2", "09:01:00", "person_enter", entities=["person_017"]),
                  {"id": "evt_L3", "type": "bogus"},                       # 非法
                  ev("evt_L4", "09:02:00", "unrecognized"),                # 无模板
                  ev("evt_L1", "09:00:00", "arrival", location_id="place_004")]  # 重放
        for e in events:
            self.world.apply_update(e)
        c = self.world.conservation()
        self.assertEqual(c["attempted"], 5)
        self.assertEqual(c["ledger_lines"], 5)
        self.assertEqual(c["applied"], 2)
        self.assertEqual(c["rejected"], 1)
        self.assertEqual(c["no_rule"], 1)
        self.assertEqual(c["replay_skipped"], 1)
        self.assertTrue(c["balanced"], f"守恒被破坏: {c}")
        self.assertEqual(self.world.verify_conservation(), [])

    def test_no_rule_events_are_visible_not_silently_dropped(self):
        """08 E: 无模板场景不得静默丢弃 —— 世界不变,但必须留下可查的记录。"""
        self.world.apply_update(ev("evt_L5", "09:00:00", "unrecognized", content="用户在阳台浇花"))
        self.assertEqual(self.world.current_state(), wr.StateRuntime().snapshot())
        line = self.world.update_ledger()[-1]
        self.assertEqual(line["disposition"], UPDATE_NO_RULE)
        self.assertEqual(line["event_id"], "evt_L5")
        self.assertEqual(self.world.no_change, 1)

    def test_ledger_lines_have_exact_fields(self):
        self.world.apply_update(ev("evt_L6", "09:00:00", "arrival", location_id="place_004"))
        self.world.apply_update({"bad": True})
        for ln in self.world.update_ledger():
            self.assertEqual(set(ln), set(LEDGER_FIELDS), f"台账行字段漂移: {sorted(ln)}")

    def test_every_change_traces_back_to_a_stored_event(self):
        r = play(self.var / "pipeline", noise=3)
        ids = {e["id"] for e in r["events"]}
        problems = r["world"].verify_traceability(ids)
        self.assertEqual(problems, [], f"世界变化无法追溯到 Event: {problems}")
        for chg in r["changes"]:
            self.assertTrue(set(chg["evidence_events"]) <= ids)

    def test_traceability_detects_forged_evidence(self):
        self.world.apply_update(ev("evt_L7", "09:00:00", "person_enter", entities=["person_017"]))
        real = {c["evidence_events"][0] for c in self.world.all_changes()}
        self.assertEqual(self.world.verify_traceability(real), [], "真实证据 id 必须全部通过核对")
        bad = self.world.verify_traceability({"evt_NOT_IN_STORE"})
        self.assertTrue(bad, "伪造的证据 id 必须被 verify_traceability 抓到")

    def test_ledger_is_reloaded_from_disk(self):
        w1 = WorldRuntime(self.var / "w3")
        w1.apply_update(ev("evt_L8", "09:00:00", "arrival", location_id="place_004"))
        w2 = WorldRuntime(self.var / "w3")
        self.assertEqual(w2.current_state(), w1.current_state(), "重启后世界必须还是同一个世界")
        self.assertEqual(w2.updated, 1)
        self.assertEqual(w2.conservation()["attempted"], 1)
        out = w2.apply_update(ev("evt_L8", "09:00:00", "arrival", location_id="place_004"))
        self.assertIsNone(out, "重启后已吸收过的 Event 仍不得产生重复 World Update")


# ==================== 边界: 没有模型、没有网络、没有越界 ====================

def _trees() -> dict[Path, ast.Module]:
    return {p: ast.parse(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "core/world").rglob("*.py"))}


def world_layer_imports() -> list[str]:
    """core/world 引入了哪些下游层(用于反向断言边界)。"""
    out = []
    for path, tree in _trees().items():
        for node in ast.walk(tree):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for m in mods:
                parts = m.split(".")
                if len(parts) > 1 and parts[0] == "core" and parts[1] in {"ai", "attention", "memory",
                                                                          "event", "perception", "policy"}:
                    out.append(f"{path.name}: import {m}")
    return sorted(out)


def model_api_identifiers() -> list[str]:
    """机械检查(不看注释、只看标识符): World 层里的模型调用痕迹。

    标识符 = 变量名 + 属性/方法名 + 被导入模块名。刻意扫 AST 而不是全文子串,
    因为文档里必须能写"LLM 不在必经路径上"这句话。
    """
    tokens = ("llm", "openai", "gemini", "anthropic", "completion", "chat", "prompt",
              "modelrouter", "model_router", "predict", "inference", "transformers", "ollama")
    hits: list[str] = []
    for path, tree in _trees().items():
        idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        idents |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        idents |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        idents |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        hits += [f"{path.name}: {i}" for i in sorted(idents) if any(tok in i.lower() for tok in tokens)]
    return hits


class TestBoundaryOfWorldPath(Base):
    def test_no_model_or_network_imports_anywhere(self):
        self.assertEqual(fs.check_no_model_or_network(), [])

    def test_world_does_not_import_downstream_layers(self):
        """Event -> World Update 的必经路径上不得出现 AI/注意力/唤醒,也不得回手抓 Perception。"""
        self.assertEqual(world_layer_imports(), [])

    def test_world_calls_no_model_or_llm_apis(self):
        self.assertEqual(model_api_identifiers(), [], "World 层出现模型调用/导入痕迹")

    def test_boundary_scans_are_not_vacuous(self):
        """往 core/world/ 塞一个带模型调用的文件,两个扫描器都必须抓到(证明它们没被调瞎)。"""
        decoy = ROOT / "core/world/_decoy_task5.py"
        decoy.write_text(
            "import openai\n"
            "from core.ai.model_router import ModelRouter\n\n\n"
            "def ask_llm(prompt):\n"
            "    return openai.Completion.create(prompt=prompt)\n", encoding="utf-8")
        try:
            self.assertTrue(world_layer_imports(), "core/world 里 import core.ai 必须被抓到")
            self.assertTrue(model_api_identifiers(), "core/world 里出现 openai/ask_llm 必须被抓到")
            self.assertTrue(fs.check_no_model_or_network(),
                            "tools.forbidden_scan 也必须命中(它扫 core/** 的 import)")
        finally:
            decoy.unlink()
        self.assertEqual(world_layer_imports(), [], "decoy 删掉后必须恢复干净")
        self.assertEqual(model_api_identifiers(), [], "decoy 删掉后必须恢复干净")
        self.assertEqual(fs.check_no_model_or_network(), [])

    def test_dedupe_stays_owned_by_event_runtime(self):
        """Task 4 边界不得被 Task 5 破坏: World 里不能出现第二套判重。"""
        self.assertEqual(fs.check_dedupe_home(), [])
        for p in (ROOT / "core/world").rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            self.assertNotIn(".is_duplicate(", src)
            self.assertNotIn(".dedupe(", src)

    def test_rules_are_a_closed_deterministic_table(self):
        #: 每条规则都必须是 (event, before) -> (change_type, slots) 的纯映射
        e = ev("evt_R1", "09:00:00", "arrival", location_id="place_004")
        blank = wr.StateRuntime().snapshot()
        for name, fn in wr.RULES.items():
            with self.subTest(rule=name):
                out = fn(e, blank)
                self.assertIsInstance(out, tuple)
                self.assertEqual(len(out), 2)
                self.assertIsInstance(out[0], str)
                self.assertIsInstance(out[1], dict)
                self.assertTrue(set(out[1]) <= set(STATE_SLOTS))

    def test_pipeline_counters_reported_by_the_player_are_real(self):
        r = play(self.var / "pipeline", noise=3)
        w = r["world"]
        self.assertEqual(w.updated, r["world_updates"])
        self.assertEqual(w.no_change, r["world_no_change"])
        self.assertEqual(len(r["changes"]), w.updated)
        self.assertEqual(w.conservation()["applied"], w.updated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
