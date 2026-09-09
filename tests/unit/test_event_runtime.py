"""Sprint 1 Task 3-4 —— Event 输入、JSONL 持久化、最小去重(02 §1)。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.simulator.mock_adapter import MockSimulatorAdapter  # noqa: E402
from core.event.event_runtime import EventRuntime  # noqa: E402
from core.perception import perception_runtime as pr  # noqa: E402
from core.perception.perception_runtime import PerceptionRuntime  # noqa: E402

SCENARIO = ROOT / "adapters/simulator/negotiation_timeline.txt"


class Base(unittest.TestCase):
    def setUp(self):
        self.var = Path(tempfile.mkdtemp(prefix="aios-test-"))
        pr.reset_id_space()
        self.p = PerceptionRuntime(date="2026-09-09")
        self.p.register_adapter(MockSimulatorAdapter(SCENARIO))
        self.events = self.p.drain()

    def tearDown(self):
        shutil.rmtree(self.var, ignore_errors=True)

    def runtime(self, **kw):
        return EventRuntime(self.var / "events", **kw)


class TestPersistence(Base):
    def test_ingest_persists_and_reads_back(self):
        rt = self.runtime()
        for ev in self.events:
            self.assertIsNotNone(rt.ingest(ev))
        back = rt.all_events()
        self.assertEqual([e["id"] for e in back], [e["id"] for e in self.events])
        self.assertEqual(json.loads(rt.path.read_text(encoding="utf-8").splitlines()[0])["content"], "到公司")

    def test_reload_from_disk_survives_instance(self):
        rt = self.runtime()
        for ev in self.events:
            rt.ingest(ev)
        again = self.runtime()
        self.assertEqual(len(again.all_events()), 7)


class TestDedupe(Base):
    def test_duplicate_within_window_dropped(self):
        rt = self.runtime(dedupe_window_s=120)
        self.assertIsNotNone(rt.ingest(self.events[0]))
        dup = {**self.events[0], "id": pr.issue_event_id()}
        self.assertIsNone(rt.ingest(dup))
        self.assertEqual(rt.stats()["duplicate_dropped"], 1)
        self.assertEqual(len(rt.all_events()), 1)

    def test_same_content_outside_window_kept(self):
        rt = self.runtime(dedupe_window_s=1.0)
        rt.ingest(self.events[0])
        later = {**self.events[0], "id": pr.issue_event_id(), "timestamp": "2026-09-09T09:30:00+08:00"}
        self.assertIsNotNone(rt.ingest(later))
        self.assertEqual(rt.stats()["duplicate_dropped"], 0)

    def test_content_difference_not_deduped(self):
        rt = self.runtime()
        self.assertIsNotNone(rt.ingest(self.events[3]))
        other = {**self.events[3], "id": pr.issue_event_id(), "content": "张总要求分期付款"}
        self.assertIsNotNone(rt.ingest(other))

    def test_batch_dedupe_helper(self):
        rt = self.runtime()
        dup = {**self.events[0], "id": pr.issue_event_id()}
        kept, dropped = rt.dedupe([*self.events, dup])
        self.assertEqual(dropped, 1)
        self.assertEqual(len(kept), 7)


class TestGuards(Base):
    def test_origin_must_be_perception(self):
        rt = self.runtime()
        with self.assertRaises(ValueError):
            rt.ingest(self.events[0], origin="simulator")

    def test_unminted_id_rejected(self):
        rt = self.runtime()
        hand = {**self.events[0], "id": "evt_handmade"}
        with self.assertRaises(ValueError):
            rt.ingest(hand)

    def test_schema_violation_rejected(self):
        rt = self.runtime()
        bad = {**self.events[0], "id": pr.issue_event_id(), "raw_data": "audio bytes"}
        with self.assertRaises(ValueError):
            rt.ingest(bad)

    def test_order_is_chronological(self):
        shuffled = [self.events[2], self.events[0], self.events[1]]
        self.assertEqual([e["id"] for e in EventRuntime.order(shuffled)],
                         [self.events[0]["id"], self.events[1]["id"], self.events[2]["id"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
