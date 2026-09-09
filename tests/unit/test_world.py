"""Sprint 1 Task 5-8 —— Entity / World State / Event->World Update / World Change Delta。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.simulator.mock_adapter import MockSimulatorAdapter  # noqa: E402
from core.perception import perception_runtime as pr  # noqa: E402
from core.perception.perception_runtime import PerceptionRuntime  # noqa: E402
from core.world.entity_runtime import EntityRuntime  # noqa: E402
from core.world.state_runtime import StateRuntime, EMPTY_STATE  # noqa: E402
from core.world.world_runtime import WorldRuntime  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402
import json  # noqa: E402

CHG_SCHEMA = json.loads((ROOT / "schemas/world_change.json").read_text(encoding="utf-8"))
SCENARIO = ROOT / "adapters/simulator/negotiation_timeline.txt"


def timeline():
    pr.reset_id_space()
    p = PerceptionRuntime(date="2026-09-09")
    p.register_adapter(MockSimulatorAdapter(SCENARIO))
    return p.drain()


class WorldCase(unittest.TestCase):
    def setUp(self):
        self.var = Path(tempfile.mkdtemp(prefix="aios-world-"))
        self.events = timeline()
        self.world = WorldRuntime(self.var / "world", EntityRuntime(self.var / "world"))

    def tearDown(self):
        shutil.rmtree(self.var, ignore_errors=True)

    def apply_all(self):
        return [c for c in (self.world.apply_update(e) for e in self.events) if c]


class TestWorldUpdate(WorldCase):
    def test_initial_state_is_unknown_mode(self):
        self.assertEqual(self.world.current_state()["mode"], "UNKNOWN")

    def test_arrival_updates_location_and_mode(self):
        chg = self.world.apply_update(self.events[0])
        self.assertEqual(chg["change_type"], "LOCATION_ARRIVAL")
        self.assertEqual(chg["after"]["location"], {"id": "place_004"})
        self.assertEqual(chg["after"]["mode"], "WORK")
        self.assertEqual(self.world.current_state()["location"]["id"], "place_004")

    def test_person_enter_adds_people_and_entity(self):
        self.world.apply_update(self.events[1])
        self.assertEqual(self.world.current_state()["people"], ["person_017"])
        self.assertIsNotNone(self.world.entities.get("person_017"))

    def test_unrecognized_event_changes_nothing_but_is_not_dropped(self):
        ev = PerceptionRuntime().ingest_signal({"at": "09:40", "text": "用户在阳台浇花"})
        before = self.world.current_state()
        self.assertIsNone(self.world.apply_update(ev))
        self.assertEqual(self.world.current_state(), before)
        self.assertEqual(self.world.no_change, 1)

    def test_every_change_conforms_to_schema(self):
        for c in self.apply_all():
            with self.subTest(cid=c["id"]):
                self.assertEqual(validate(c, CHG_SCHEMA), [])

    def test_change_carries_before_after_and_evidence(self):
        chg = self.world.apply_update(self.events[0])
        self.assertEqual(chg["before"]["mode"], "UNKNOWN")
        self.assertEqual(chg["after"]["mode"], "WORK")
        self.assertEqual(chg["evidence_events"], [self.events[0]["id"]])
        self.assertEqual(set(chg["before"]) == set(chg["after"]), True)

    def test_price_then_second_price_escalates(self):
        self.world.apply_update(self.events[0])
        self.assertEqual(self.world.apply_update(self.events[3])["change_type"], "PRICE_DISCUSSION")
        self.world.apply_update(self.events[4])  # 09:10 用户沉默 -> talking=False
        self.assertEqual(self.world.apply_update(self.events[6])["change_type"], "NEGOTIATION_ESCALATION")

    def test_identical_repeat_makes_no_world_change(self):
        """02 §3: 只保存变化。同样的价格讨论再来一次,世界没有变化就不该造 Change。"""
        self.world.apply_update(self.events[3])
        again = {**self.events[3], "id": "evt_dup", "timestamp": "2026-09-09T09:09:00+08:00"}
        self.assertIsNone(self.world.apply_update(again))
        self.assertEqual(self.world.no_change, 1)

    def test_full_timeline_produces_seven_changes(self):
        changes = self.apply_all()
        self.assertEqual([c["change_type"] for c in changes], [
            "LOCATION_ARRIVAL", "PARTICIPANT_ENTER", "CONTRACT_DISCUSSION", "PRICE_DISCUSSION",
            "USER_SILENCE", "DOCUMENT_OPEN", "NEGOTIATION_ESCALATION"])

    def test_silence_flips_talking(self):
        self.apply_all()
        self.assertEqual(self.world.current_state()["user"]["talking"], True)
        self.assertEqual(self.world.current_state()["active_situations"], ["negotiation"])


class TestStateAndEntity(WorldCase):
    def test_diff_reports_only_changed_slots(self):
        a = {**EMPTY_STATE, "mode": "WORK"}
        b = {**EMPTY_STATE, "mode": "SLEEP"}
        self.assertEqual(list(StateRuntime.diff(a, b)), ["mode"])
        self.assertEqual(StateRuntime.diff(a, a), {})

    def test_state_snapshot_is_a_copy(self):
        s = StateRuntime()
        snap = s.snapshot()
        snap["mode"] = "HACKED"
        self.assertEqual(s.snapshot()["mode"], "UNKNOWN")

    def test_relationship_is_first_class_and_referenced_by_ids(self):
        ent = EntityRuntime(self.var / "rel")
        ent.ensure("user", "person")
        ent.ensure("person_017", "person")
        rel = ent.link("user", "person_017", "CLIENT", 0.6, [self.events[1]["id"]])
        self.assertEqual(ent.get("person_017")["relationship_ids"], [rel["id"]])
        self.assertEqual(len(ent.all_relationships()), 1)
        stronger = ent.link("user", "person_017", "CLIENT", 0.8, [self.events[3]["id"]])
        self.assertEqual(stronger["id"], rel["id"], "同一对同类关系必须复用 id,不得堆积")
        self.assertEqual(stronger["strength"], 0.8)
        self.assertEqual(len(stronger["evidence"]), 2)

    def test_entity_rejects_embedded_relationships(self):
        ent = EntityRuntime(self.var / "bad")
        with self.assertRaises(ValueError):
            ent.upsert({"id": "person_017", "type": "person",
                        "identity": {"name": None, "aliases": [], "confidence": 0.0},
                        "relationships": [], "evidence": []})


if __name__ == "__main__":
    unittest.main(verbosity=2)
