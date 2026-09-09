"""Sprint 1 Task 2 —— Mock Perception Adapter 的最小合同(02 §0)。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.simulator.mock_adapter import MockSimulatorAdapter  # noqa: E402
from core.perception import perception_runtime as pr  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402

import json  # noqa: E402

EVENT_SCHEMA = json.loads((ROOT / "schemas/event.json").read_text(encoding="utf-8"))
SCENARIO = ROOT / "adapters/simulator/negotiation_timeline.txt"


def fresh(date="2026-09-09"):
    pr.reset_id_space()
    p = pr.PerceptionRuntime(date=date)
    p.register_adapter(MockSimulatorAdapter(SCENARIO))
    return p


class TestPerception(unittest.TestCase):
    def test_scenario_events_are_schema_conformant(self):
        events = fresh().drain()
        self.assertEqual(len(events), 7)
        for ev in events:
            with self.subTest(eid=ev["id"]):
                self.assertEqual(validate(ev, EVENT_SCHEMA), [])

    def test_ids_are_minted_by_perception_only(self):
        events = fresh().drain()
        self.assertEqual([e["id"] for e in events], [f"evt_{i:03d}" for i in range(1, 8)])
        self.assertTrue(all(pr.is_minted(e["id"]) for e in events))
        self.assertFalse(pr.is_minted("evt_999"))

    def test_unknown_signal_is_downgraded_not_dropped(self):
        p = fresh()
        ev = p.ingest_signal({"at": "09:20", "text": "用户在阳台浇花"})
        self.assertEqual(ev["type"], "unrecognized")
        self.assertEqual(ev["confidence"], 0.40)
        self.assertEqual(p.unknown, 1)

    def test_raw_payload_is_purged_privacy(self):
        p = fresh()
        ev = p.drain()[0]
        self.assertTrue(ev["raw_ref"].startswith("perception://temp/"))
        self.assertEqual(p.raw_still_held(), 0, "原始感知数据不得留存(宪法 12.2)")

    def test_time_is_normalized_with_date(self):
        ev = fresh().ingest_signal({"at": "9:05", "text": "张总进入"})
        self.assertEqual(ev["timestamp"], "2026-09-09T09:05:00+08:00")

    def test_mock_entity_resolution(self):
        ev = fresh().ingest_signal({"at": "09:05", "text": "张总进入"})
        self.assertEqual(ev["entities"], ["person_017"])

    def test_check_rejects_raw_data_field(self):
        """03 Canonical naming rule:raw_data 不得进入标准 Event,_check 必须拦住。"""
        good = fresh().drain()[0]
        with self.assertRaises(ValueError):
            pr.PerceptionRuntime._check({**good, "raw_data": "整段录音"})

    def test_check_rejects_missing_required_field(self):
        good = fresh().drain()[0]
        with self.assertRaises(ValueError):
            pr.PerceptionRuntime._check({k: v for k, v in good.items() if k != "confidence"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
