"""09 §Sprint 1 禁止事项 1-7 的执行测试(不靠自觉,靠测试)。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import forbidden_scan as fs  # noqa: E402


class TestProhibitions(unittest.TestCase):
    def test_1_constitution_frozen(self):
        """禁止#1: 宪法 V1.2-r1 一字未改。golden 哈希在 tests/constitution_v1.2-r1.sha256。"""
        golden = (ROOT / "tests/constitution_v1.2-r1.sha256").read_text(encoding="utf-8").strip()
        self.assertEqual(fs.constitution_hash(), golden,
                         "宪法被改动了。要改必须先在 docs 层走架构裁决,再重新生成 golden 哈希")

    def test_2_runtime_boundaries_unchanged(self):
        self.assertEqual(fs.check_runtime_boundaries(), [])

    def test_3_no_sprint2_3_4_work(self):
        self.assertEqual(fs.check_skeleton_intact(), [])

    def test_4_no_model_or_network(self):
        self.assertEqual(fs.check_no_model_or_network(), [])

    def test_5_no_bypass_of_perception(self):
        self.assertEqual(fs.check_perception_gate(), [])

    def test_6_dedupe_lives_in_event_runtime(self):
        self.assertEqual(fs.check_dedupe_home(), [])

    def test_7_prohibitions_are_in_repo(self):
        self.assertEqual(fs.check_prohibitions_recorded(), [])

    def test_scan_is_not_vacuous(self):
        """往 Event Runtime 之外塞一个 dedupe 实现,检查器必须报错(证明检查有效)。"""
        decoy = ROOT / "core/attention/_decoy_dedupe.py"
        decoy.write_text("def dedupe(events):\n    return events\n", encoding="utf-8")
        try:
            self.assertTrue(fs.check_dedupe_home(), "越界去重没被抓到,检查器是空转的")
        finally:
            decoy.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
