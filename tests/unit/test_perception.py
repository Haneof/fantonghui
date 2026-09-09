"""Sprint 1 Task 2 —— Mock Perception Adapter 的最小合同(02 §0)。

覆盖:正常 Raw Signal -> Semantic Event、多种 modality、confidence 区间、raw_ref 保留、
相同输入的确定性、以及"Perception 不越界"。非法输入的拒收见 test_perception_contract.py。
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.simulator.mock_adapter import MockSimulatorAdapter  # noqa: E402
from core.perception import perception_runtime as pr  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402

EVENT_SCHEMA = json.loads((ROOT / "schemas/event.json").read_text(encoding="utf-8"))
SCENARIO = ROOT / "adapters/simulator/negotiation_timeline.txt"
MULTIMODAL = ROOT / "adapters/simulator/mock_multimodal.jsonl"
PERCEPTION_SRC = (ROOT / "core/perception").glob("*.py")


def fresh(date: str = "2026-09-09", scenario: Path = SCENARIO) -> pr.PerceptionRuntime:
    pr.reset_id_space()
    p = pr.PerceptionRuntime(date=date)
    p.register_adapter(MockSimulatorAdapter(scenario))
    return p


def raw(text: str, at: str = "09:00", **over) -> dict:
    sig = {"signal_id": over.pop("signal_id", f"sig-{at}-{text}"), "timestamp": at,
           "source": "simulator", "modality": "text", "payload": {"text": text}}
    sig.update(over)
    return sig


class TestSemanticEventOutput(unittest.TestCase):
    def test_scenario_events_are_schema_conformant(self):
        events = fresh().drain()
        self.assertEqual(len(events), 7)
        for ev in events:
            with self.subTest(eid=ev["id"]):
                self.assertEqual(validate(ev, EVENT_SCHEMA), [])

    def test_event_carries_the_required_semantic_fields(self):
        """任务要求的 6 项在 docs/03 里的对应:id=event_id, type=event_type,
        content+entities=payload/attributes,另有 timestamp/source/confidence/raw_ref。"""
        ev = fresh().drain()[0]
        self.assertEqual(set(ev), {"id", "timestamp", "source", "type", "content",
                                   "entities", "location_id", "confidence", "raw_ref"})

    def test_ids_are_minted_by_perception_only(self):
        events = fresh().drain()
        self.assertEqual([e["id"] for e in events], [f"evt_{i:03d}" for i in range(1, 8)])
        self.assertTrue(all(pr.is_minted(e["id"]) for e in events))
        self.assertFalse(pr.is_minted("evt_999"))

    def test_confidence_is_in_range_for_every_event(self):
        for ev in fresh(scenario=MULTIMODAL).drain() + fresh().drain():
            with self.subTest(etype=ev["type"]):
                self.assertIsInstance(ev["confidence"], float)
                self.assertGreaterEqual(ev["confidence"], 0.0)
                self.assertLessEqual(ev["confidence"], 1.0)

    def test_three_plus_modalities_produce_events(self):
        events = fresh(scenario=MULTIMODAL).drain()
        self.assertEqual(len(events), 7)
        self.assertEqual([e["type"] for e in events],
                         ["price_negotiation", "person_enter", "person_enter", "silence",
                          "contract_discussion", "departure", "unrecognized"])
        # 命中规则时 source=感知通道;未命中时回落到 raw signal 自己的 source(设计如此)
        self.assertEqual({e["source"] for e in events},
                         {"asr", "sensor", "vision", "calendar", "phone"})

    def test_unknown_signal_is_downgraded_not_dropped(self):
        p = fresh()
        ev = p.ingest_signal(raw("用户在阳台浇花", at="09:20"))
        self.assertEqual(ev["type"], "unrecognized")
        self.assertEqual(ev["confidence"], 0.40)
        self.assertEqual(p.unknown, 1)
        self.assertEqual(p.emitted, 1, "未知场景必须保留成事件,不得丢弃(08 E)")

    def test_same_input_is_deterministic(self):
        a = fresh().drain()
        b = fresh().drain()
        self.assertEqual(a, b, "相同输入必须产出完全相同的 Semantic Event(含 id)")

    def test_payload_is_normalized_per_modality(self):
        p = fresh()
        ev = p.ingest_signal(raw("谈价格", at="09:20"))
        self.assertEqual(ev["content"], "谈价格")
        self.assertEqual(ev["type"], "price_negotiation")
        self.assertEqual(ev["source"], "mic")

    def test_time_is_normalized_with_date(self):
        ev = fresh().ingest_signal(raw("张总进入", at="9:05"))
        self.assertEqual(ev["timestamp"], "2026-09-09T09:05:00+08:00")

    def test_mock_entity_resolution(self):
        ev = fresh().ingest_signal(raw("张总进入", at="09:05"))
        self.assertEqual(ev["entities"], ["person_017"])
        self.assertEqual(ev["location_id"], None)

    def test_raw_ref_keeps_signal_lineage(self):
        p = fresh()
        ev = p.ingest_signal(raw("到公司", at="09:00", signal_id="sig-line-9"))
        self.assertTrue(ev["raw_ref"].startswith("perception://temp/"))
        m = re.search(r"signal_id=(.+)$", ev["raw_ref"])
        self.assertIsNotNone(m, "raw_ref 必须能回溯到 raw signal")
        self.assertEqual(m.group(1), "sig-line-9")

    def test_raw_payload_is_purged_privacy(self):
        p = fresh()
        p.drain()
        self.assertEqual(p.raw_still_held(), 0, "原始感知数据不得留存(宪法 12.2)")

    def test_check_rejects_raw_data_field(self):
        """03 Canonical naming rule:raw_data 不得进入标准 Event,_check 必须拦住。"""
        good = fresh().drain()[0]
        with self.assertRaises(ValueError):
            pr.PerceptionRuntime._check({**good, "raw_data": "整段录音"})

    def test_check_rejects_missing_required_field(self):
        good = fresh().drain()[0]
        with self.assertRaises(ValueError):
            pr.PerceptionRuntime._check({k: v for k, v in good.items() if k != "confidence"})


class TestBoundariesAndQuality(unittest.TestCase):
    """实现要求 四 / 八:边界与代码质量的机械检查,不靠自觉。"""

    files = {p.name: p.read_text(encoding="utf-8") for p in PERCEPTION_SRC}

    def test_no_placeholder_in_core_path(self):
        for name, src in self.files.items():
            for token in ("NotImplementedError", "TODO", "FIXME", "raise NotImplementedError"):
                with self.subTest(file=name, token=token):
                    self.assertNotIn(token, src, f"core/perception/{name} 用占位实现代替了核心逻辑")
            for ln, line in enumerate(src.splitlines(), 1):
                if line.strip() == "pass":
                    self.fail(f"core/perception/{name}:{ln} 用裸 pass 搪塞")

    def test_does_not_reach_into_event_world_or_llm(self):
        """边界用 ast 检查:Perception 不得 import 下游 Runtime、模型库或网络库。"""
        import ast  # noqa: PLC0415

        banned = ("core.event", "core.world", "core.attention", "core.ai", "core.memory", "core.identity",
                  "core.policy", "core.capability", "core.interaction", "core.evolution",
                  "openai", "anthropic", "httpx", "requests", "socket", "urllib", "google")
        for name, src in self.files.items():
            mods = []
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                elif isinstance(node, ast.Import):
                    mods += [a.name for a in node.names]
            with self.subTest(file=name):
                hit = [m for m in mods if m.split(".")[0] in {b.split(".")[0] for b in banned}
                       and any(m == b or m.startswith(b + ".") or m.split(".")[0] == b for b in banned)]
                self.assertEqual(hit, [], f"core/perception/{name} 越界 import: {hit}")

    def test_only_stdlib_and_local_imports(self):
        imports = {m for src in self.files.values()
                   for m in re.findall(r"^[ \t]*(?:from|import)\s+([A-Za-z_][\w.]*)", src, re.M)}
        allowed = {"__future__", "itertools", "re", "sys", "pathlib", "typing", "dataclasses", "json",
                   "core.perception", "core.perception.raw_signal", "core.perception.semantics",
                   "tools.mini_jsonschema"}
        self.assertTrue(imports <= allowed, f"引入了计划外依赖: {sorted(imports - allowed)}")

    def test_adapter_has_no_runtime_calls(self):
        """Simulator 只准吐 raw signal:用 ast 查真实调用,不被注释里的词误伤。"""
        import ast  # noqa: PLC0415

        tree = ast.parse((ROOT / "adapters/simulator/mock_adapter.py").read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {f"{a.module}" for a in ast.walk(tree) if isinstance(a, ast.ImportFrom)}
        forbidden = {"EventRuntime", "WorldRuntime", "PerceptionRuntime", "issue_event_id",
                     "core.event", "core.world"}
        self.assertEqual(sorted(names & forbidden), [], "Simulator 适配器碰了下游 Runtime")

if __name__ == "__main__":
    unittest.main(verbosity=2)
