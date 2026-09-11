"""08 A 世界连续性 + 可回放(Time/Space) —— 集成测试。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.event.event_runtime import EventRuntime  # noqa: E402
from tests.scenario.helpers import play  # noqa: E402


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.var = Path(tempfile.mkdtemp(prefix="aios-replay-"))

    def tearDown(self):
        shutil.rmtree(self.var, ignore_errors=True)

    def test_state_rebuilt_from_events_only(self):
        r = play(self.var, noise=3)
        store = EventRuntime(self.var / "events")
        replayed = r["world"].replay(store.all_events(), self.var / "re")
        self.assertEqual(replayed.current_state(), r["world"].current_state())

    def test_entities_survive_new_instance(self):
        r = play(self.var, noise=0)
        from core.world.entity_runtime import EntityRuntime  # noqa: PLC0415

        reloaded = EntityRuntime(self.var / "world")
        self.assertEqual(sorted(e["id"] for e in reloaded.all_entities()),
                         sorted(e["id"] for e in r["world"].entities.all_entities()))
        self.assertIn("person_017", [e["id"] for e in reloaded.all_entities()])

    def test_timeline_is_monotonic_and_time_space_replayable(self):
        r = play(self.var, noise=0)
        stamps = [e["timestamp"] for e in r["events"]]
        self.assertEqual(stamps, sorted(stamps), "事件必须按时间有序落库")
        self.assertEqual(len({e["timestamp"][11:16] for e in r["events"]}), 7)

    def test_changes_evidence_points_at_stored_events(self):
        r = play(self.var, noise=0)
        ids = {e["id"] for e in r["events"]}
        for chg in r["changes"]:
            self.assertTrue(set(chg["evidence_events"]) <= ids, f"{chg['id']} 的证据事件不在库内")


if __name__ == "__main__":
    unittest.main(verbosity=2)
