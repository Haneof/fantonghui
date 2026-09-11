"""Sprint 1 Task 2 最小闭环集成测试:Mock Raw Signal -> Perception Runtime -> Semantic Event。

按任务要求"只验证到 Semantic Event 为止":这里不接 Event Runtime、不接 World,
只用它们的存在性做反向断言(证明 Perception 没把链路偷跑到下一段)。
"""
from __future__ import annotations

import json
import socket
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.simulator.mock_adapter import MockSimulatorAdapter  # noqa: E402
from core.perception import perception_runtime as pr  # noqa: E402
from core.perception.raw_signal import PerceptionInputError  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402

EVENT_SCHEMA = json.loads((ROOT / "schemas/event.json").read_text(encoding="utf-8"))
SCENARIOS = [ROOT / "adapters/simulator/negotiation_timeline.txt",
             ROOT / "adapters/simulator/mock_multimodal.jsonl"]


class NoNetwork:
    """运行时闸门:任何 socket / HTTP 调用直接炸,证明没有外部服务。"""

    def __enter__(self) -> "NoNetwork":
        self._sock, self._urlopen = socket.socket, urllib.request.urlopen
        socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Perception 不得联网"))
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Perception 不得发 HTTP"))
        return self

    def __exit__(self, *exc) -> None:
        socket.socket, urllib.request.urlopen = self._sock, self._urlopen


class TestClosedLoop(unittest.TestCase):
    def test_end_to_end_raw_to_semantic_event(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.name), NoNetwork():
                pr.reset_id_space()
                p = pr.PerceptionRuntime(date="2026-09-09")
                adapter = MockSimulatorAdapter(scenario)
                p.register_adapter(adapter)
                by_ref = {s["signal_id"]: s["source"] for s in adapter.read()}
                events = p.drain()
                self.assertTrue(events)
                self.assertEqual(p.raw_still_held(), 0)
                self.assertEqual(p.stats()["rejected"], 0, "合法场景不得被拒收")
                for ev in events:
                    self.assertEqual(validate(ev, EVENT_SCHEMA), [], f"{ev['id']} 不符合 event schema")
                    if ev["type"] == "unrecognized":
                        # 设计:未命中规则时 source 回落到 raw signal 自带的来源,不做任何猜测
                        self.assertEqual(ev["source"], by_ref[ev["raw_ref"].rsplit("=", 1)[1]])
                    else:
                        self.assertIn(ev["source"], {"gps", "mic", "imu", "screen", "asr",
                                                     "sensor", "vision", "calendar"})
                    # raw_ref 指向的瞬态槽位必须已被销毁
                    self.assertNotIn(ev["id"], p._transient)

    def test_modality_coverage(self):
        pr.reset_id_space()
        p = pr.PerceptionRuntime()
        p.register_adapter(MockSimulatorAdapter(SCENARIOS[0]))
        p.register_adapter(MockSimulatorAdapter(SCENARIOS[1]))
        events = p.drain()
        self.assertGreaterEqual(len({e["source"] for e in events}), 5, "至少 3 种 modality 的用例要真跑起来")
        self.assertGreaterEqual(len({e["type"] for e in events}), 8)

    def test_bad_signal_stops_at_the_boundary(self):
        """非法输入在边界就被拒,不会产生事件,也不会污染后续(此处无 store 可污染)。"""
        p = pr.PerceptionRuntime()
        with self.assertRaises(PerceptionInputError):
            p.ingest_signal({"timestamp": "09:00", "modality": "text", "payload": {"text": "到公司"}})
        self.assertEqual(p.emitted, 0)
        self.assertEqual(p.raw_still_held(), 0)

    def test_perception_writes_no_files(self):
        """Perception 是瞬态层:整条 drain 不该落任何盘(持久化属于 Event Runtime)。"""
        def snapshot() -> set[str]:
            var = ROOT / "var"
            return {f.relative_to(ROOT).as_posix() for f in var.rglob("*")} if var.exists() else set()

        before = snapshot()
        p = pr.PerceptionRuntime()
        p.register_adapter(MockSimulatorAdapter(SCENARIOS[1]))
        p.drain()
        self.assertEqual(before, snapshot(), "Perception 阶段不应产生持久化文件")


if __name__ == "__main__":
    unittest.main(verbosity=2)
