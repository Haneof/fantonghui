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
from core.perception.perception_runtime import PerceptionRuntime, issue_event_id  # noqa: E402
from core.event.event_runtime import EventIngestError, EventRuntime  # noqa: E402
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


class TestContractGates(Base):
    """实现要求 一/二/三/九:输入形态、schema、id 规则、错误可断言。"""

    def codes_for(self, *mutators):
        out = []
        for mut in mutators:
            ev = mut(dict(self.events[0]))
            with self.subTest(mut=mut.__name__):
                with self.assertRaises(EventIngestError) as ctx:
                    self.runtime().ingest(ev)
                out.append((ctx.exception.code, ctx.exception.field))
        return out

    def test_legal_event_is_stored_and_returned(self):
        rt = self.runtime()
        got = rt.ingest(self.events[0])
        self.assertEqual(got, self.events[0])
        self.assertEqual(rt.count(), 1)

    def test_raw_signal_is_not_accepted(self):
        """要求 一 + 十(10):Raw Signal 属于 Perception 的输入,Event Store 必须拒收。"""
        from adapters.simulator.mock_adapter import MockSimulatorAdapter  # noqa: PLC0415

        raw = MockSimulatorAdapter(SCENARIO).read()[0]
        rt = self.runtime()
        with self.assertRaises(EventIngestError) as ctx:
            rt.ingest(raw)
        self.assertEqual(ctx.exception.code, "RAW_SIGNAL_REJECTED")
        self.assertEqual(rt.count(), 0)

    def test_error_code_table(self):
        def forge_id(e):
            e["id"] = "evt_forged"
            return e

        def bogus_origin(e):
            return e

        def add_attributes(e):
            e["attributes"] = {"price": 100}   # 03 无此字段,additionalProperties=false 必须拒
            return e

        def break_timestamp(e):
            e["timestamp"] = "昨天下午"
            return e

        def break_entities(e):
            e["entities"] = "person_017"        # 03 要求 array of string
            return e

        self.assertEqual(
            self.codes_for(forge_id, add_attributes, break_timestamp, break_entities),
            [("ID_NOT_MINTED", "id"), ("SCHEMA_INVALID", ""),
             ("UNPARSEABLE_TIMESTAMP", "timestamp"), ("SCHEMA_INVALID", "")])
        with self.assertRaises(EventIngestError) as ctx:
            self.runtime().ingest(bogus_origin(self.events[0]), origin="simulator")
        self.assertEqual((ctx.exception.code, ctx.exception.field), ("ORIGIN_NOT_PERCEPTION", "origin"))
        for bad in (None, "evt_001", 42, ["id"]):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(EventIngestError) as ctx:
                    self.runtime().ingest(bad)
                self.assertEqual(ctx.exception.code, "BAD_EVENT_TYPE")

    def test_rejections_are_counted_not_swallowed(self):
        rt = self.runtime()
        for _ in range(3):
            with self.assertRaises(EventIngestError):
                rt.ingest({**self.events[0], "id": "evt_forged"})
        self.assertEqual((rt.stats()["rejected"], rt.count()), (3, 0))

    def test_no_field_is_autorepaired(self):
        """要求 九:不得把非法事件"修"成另一个事件。非法就是非法,原样拒。"""
        rt = self.runtime()
        for bad in ({**self.events[0], "id": issue_event_id(), "entities": "person_017"},
                    {**self.events[0], "id": issue_event_id(), "confidence": "很高"},
                    {**self.events[0], "id": issue_event_id(), "location_id": 7}):
            with self.assertRaises(EventIngestError):
                rt.ingest(bad)
        self.assertEqual(rt.count(), 0, "Store 不得替调用方改写事实字段")

    def test_confidence_range_is_a_spec_gap_not_our_invention(self):
        """登记事实:schemas/event.json 对 confidence 没有 minimum/maximum,所以 12 会被收下。

        0..1 区间目前只由 Perception 侧保证(test_confidence_is_in_range_for_every_event)。
        Store 自行加区间校验=改契约(禁止项 17),因此这里断言"当前确实不拦",
        把缺口留在测试名里,而不是偷偷修好或假装它不存在。待架构师裁决。
        """
        rt = self.runtime()
        got = rt.ingest({**self.events[1], "id": issue_event_id(), "confidence": 12})
        self.assertIsNotNone(got, "若 03 补了 min/max,本断言应转红,提示我们同步实现")

    def test_error_is_valueerror(self):
        self.assertTrue(issubclass(EventIngestError, ValueError))


class TestOrdering(Base):
    """实现要求 五:同刻、异刻、乱序都必须有序读回,且不得丢事件。"""

    def test_out_of_order_input_reads_back_sorted(self):
        rt = self.runtime()
        for ev in [self.events[3], self.events[0], self.events[2], self.events[1]]:
            rt.ingest(ev)
        back = rt.all_events()
        self.assertEqual(len(back), 4, "排序不得吞事件")
        self.assertEqual([e["id"] for e in back],
                         [self.events[i]["id"] for i in (0, 1, 2, 3)])

    def test_same_timestamp_keeps_arrival_order(self):
        rt = self.runtime()
        ids = [issue_event_id() for _ in range(4)]
        for i, eid in enumerate(ids):
            rt.ingest({**self.events[0], "id": eid, "content": f"第 {i} 次报价",
                       "timestamp": "2026-09-09T09:15:00+08:00"})
        self.assertEqual([e["id"] for e in rt.all_events()], ids, "相同 timestamp 必须按到达顺序稳定")

    def test_events_after_is_incremental_and_sorted(self):
        rt = self.runtime()
        for ev in self.events:
            rt.ingest(ev)
        later = rt.events_after("2026-09-09T09:10:00+08:00")
        self.assertEqual([e["timestamp"][11:16] for e in later], ["09:12", "09:15"])

    def test_dedupe_drops_are_not_silent(self):
        rt = self.runtime()
        rt.ingest(self.events[0])
        self.assertIsNone(rt.ingest({**self.events[0], "id": issue_event_id()}))
        ledger = rt.dropped()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["reason"], "DUPLICATE_WITHIN_WINDOW")
        self.assertNotEqual(ledger[0]["id"], self.events[0]["id"], "留痕必须是被丢弃那条")


class TestPersistence(Base):
    """实现要求 四/十(5,6,15,16):写、读、重启恢复、批量连续写一致。"""

    def test_file_matches_memory(self):
        rt = self.runtime()
        for ev in self.events:
            rt.ingest(ev)
        self.assertEqual(rt.verify_persistence(), [])
        lines = rt.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 7)
        self.assertEqual([json.loads(ln)["id"] for ln in lines], [e["id"] for e in self.events])

    def test_reload_restores_index_window_and_counters(self):
        rt = self.runtime()
        for ev in self.events:
            rt.ingest(ev)
        again = self.runtime()
        self.assertEqual([e["id"] for e in again.all_events()], [e["id"] for e in self.events])
        self.assertEqual(again.stats()["semantic_event_count"], 7)
        # 恢复的不只是数据,还有去重窗口:重启后重放同一条内容必须仍判重复
        self.assertIsNone(again.ingest({**self.events[0], "id": issue_event_id()}))
        self.assertEqual(again.stats()["duplicate_dropped"], 1)

    def test_resume_can_be_disabled(self):
        rt = self.runtime()
        rt.ingest(self.events[0])
        fresh = EventRuntime(self.var / "events", resume=False)
        self.assertEqual(fresh.count(), 0)
        self.assertEqual(len(EventRuntime(self.var / "events").all_events()), 1)

    def test_continuous_bulk_write(self):
        rt = self.runtime(dedupe_window_s=0.0)
        ids, base = [], self.events[0]
        for i in range(50):
            eid = issue_event_id()
            ids.append(eid)
            rt.ingest({**base, "id": eid, "content": f"批量事件 {i:03d}",
                       "timestamp": f"2026-09-09T09:{i // 60:02d}:{i % 60:02d}+08:00"})
        self.assertEqual(rt.count(), 50)
        self.assertEqual(rt.verify_persistence(), [])
        self.assertEqual([e["id"] for e in rt.all_events()], ids)

    def test_get_by_id(self):
        rt = self.runtime()
        rt.ingest(self.events[0])
        self.assertEqual(rt.get(self.events[0]["id"])["content"], "到公司")
        self.assertIsNone(rt.get("evt_missing"))


class TestLineage(Base):
    """实现要求 六:Semantic Event -> raw_ref 必须一路可追。"""

    def test_raw_ref_survives_persistence(self):
        rt = self.runtime()
        rt.ingest(self.events[0])
        reloaded = self.runtime()
        self.assertEqual(reloaded.all_events()[0]["raw_ref"], self.events[0]["raw_ref"])
        lin = reloaded.lineage(self.events[0]["id"])
        self.assertEqual(lin["signal_id"], "sim-negotiation_timeline-001")
        self.assertEqual(lin["target_event_id"], self.events[0]["id"])
        self.assertFalse(lin["signal_id"].endswith("_"), "lineage 不得指向已销毁的原始体,只留指针")

    def test_null_raw_ref_is_tolerated(self):
        """03 的 Event 示例允许 raw_ref=null;不得因此拒绝入库。"""
        rt = self.runtime()
        ev = {**self.events[1], "id": issue_event_id(), "raw_ref": None}
        self.assertIsNotNone(rt.ingest(ev))
        self.assertEqual(rt.lineage(ev["id"])["raw_ref"], None)

    def test_unknown_lineage_is_reported_not_crashing(self):
        rt = self.runtime()
        ev = {**self.events[1], "id": issue_event_id(), "raw_ref": "file:///tmp/tape.wav"}
        rt.ingest(ev)
        self.assertEqual(rt.lineage(ev["id"])["signal_id"], "<unparsable>")
        self.assertIsNone(rt.lineage("evt_absent"))


class TestBoundaries(Base):
    """实现要求 七/十二:用 AST 与 monkeypatch 双重锁死边界,不另写第二套检查器。"""

    SRC = (ROOT / "core/event/event_runtime.py").read_text(encoding="utf-8")

    def test_event_runtime_imports_no_downstream_runtime(self):
        import ast  # noqa: PLC0415

        banned = {"core.world", "core.attention", "core.ai", "core.memory", "core.identity",
                  "core.policy", "core.capability", "core.interaction", "core.evolution"}
        mods = []
        for node in ast.walk(ast.parse(self.SRC)):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
        self.assertEqual(sorted(set(mods) & banned), [], f"Event Runtime 越界 import: {sorted(set(mods) & banned)}")

    def test_no_runtime_import_of_perception(self):
        """FIX-01: Event Runtime 对 core.* 必须零依赖,provenance 走中立登记册。"""
        import ast  # noqa: PLC0415

        mods = []
        for node in ast.walk(ast.parse(self.SRC)):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
        self.assertEqual([m for m in mods if m.startswith("core.")], [],
                         f"Event Runtime 依赖了 Runtime 模块: {[m for m in mods if m.startswith('core.')]}")
        self.assertEqual([m for m in mods if "perception" in m], [], "仍有 perception 引用")
        self.assertIn("tools.provenance", mods, "出处验证必须来自中立登记册,不是别的 Runtime")

    def test_no_dynamic_import_escape(self):
        """禁止用 sys.path / importlib / __import__ / exec 变相加载 Perception。"""
        for token in ("importlib", "__import__", "import_module", "exec(", "eval("):
            self.assertNotIn(token, self.SRC, f"出现 {token}:属于绕过静态边界检查")
        for ln, line in enumerate(self.SRC.splitlines(), 1):
            if "sys.path" in line:
                self.assertNotIn("perception", line, f"event_runtime.py:{ln} 用 sys.path 指向感知层")
        self.assertNotIn("core.perception", self.SRC, "注释里也不留点路径,防止被当成依赖 grep 不出真相")

    def test_ingest_works_with_perception_pipeline_disabled(self):
        """把感知的四个入口全打断,Event Store 仍能写读 —— 证明它没在调用 Perception。"""
        def boom(*a, **k):
            raise AssertionError("Event Runtime 不得调用 Perception 流水线")

        saved = (PerceptionRuntime.register_adapter, PerceptionRuntime.drain,
                 PerceptionRuntime.ingest_signal, PerceptionRuntime.emit_semantic_event)
        events = self.events  # 先把合法事件准备好(这一步才允许用感知)
        PerceptionRuntime.register_adapter = PerceptionRuntime.drain = boom
        PerceptionRuntime.ingest_signal = PerceptionRuntime.emit_semantic_event = boom
        try:
            rt = self.runtime()
            for ev in events:
                self.assertIsNotNone(rt.ingest(ev))
            self.assertEqual(rt.count(), 7)
            self.assertEqual(rt.verify_persistence(), [])
        finally:
            (PerceptionRuntime.register_adapter, PerceptionRuntime.drain,
             PerceptionRuntime.ingest_signal, PerceptionRuntime.emit_semantic_event) = saved

    def test_no_network_during_ingest_and_read(self):
        import socket  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        sock, up = socket.socket, urllib.request.urlopen
        socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Event Runtime 不得联网"))
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Event Runtime 不得发 HTTP"))
        try:
            rt = self.runtime()
            for ev in self.events:
                rt.ingest(ev)
            rt.resume().all_events()
        finally:
            socket.socket, urllib.request.urlopen = sock, up

    def test_existing_forbidden_scan_still_covers_this_runtime(self):
        """要求 十二:复用项目已有检查器,不另写一套。"""
        from tools import forbidden_scan as fs  # noqa: PLC0415

        self.assertEqual(fs.check_no_model_or_network(), [])
        self.assertEqual(fs.check_dedupe_home(), [])
        self.assertEqual(fs.check_perception_gate(), [])

    def test_fusion_and_patterns_stay_skeleton(self):
        """要求 八:本任务不得把 Event Runtime 扩成 Fusion 系统。"""
        for ref in (("core.event.fusion", "EventFusion"), ("core.event.patterns", "Patterns")):
            import importlib  # noqa: PLC0415

            with self.assertRaises(NotImplementedError):
                getattr(importlib.import_module(ref[0]), ref[1])()


class TestProvenanceIsolation(Base):
    """FIX-01 的核心安全性质: 登记册是唯一证明,换一份登记册就必须全部拒。"""

    def test_shared_injected_registry_accepts(self):
        from tools.provenance import EventProvenance  # noqa: PLC0415

        reg = EventProvenance(prefix="inj")
        p = PerceptionRuntime(date="2026-09-09", provenance=reg)
        p.register_adapter(MockSimulatorAdapter(SCENARIO))
        events = p.drain()
        rt = EventRuntime(self.var / "shared", provenance=reg)
        self.assertEqual(sum(rt.ingest(e) is not None for e in events), 7)
        self.assertEqual(rt.verify_persistence(), [])
        self.assertEqual(events[0]["id"], "inj_001", "id 必须由注入的登记册铸造")

    def test_foreign_registry_is_rejected(self):
        from tools.provenance import EventProvenance  # noqa: PLC0415

        other = EventProvenance(prefix="oth")
        rt = self.runtime()
        rejected = []
        for ev in self.events:
            with self.assertRaises(EventIngestError) as ctx:
                rt.ingest({**ev, "id": other.mint() if ev is self.events[0] else "oth_forged"})
            rejected.append(ctx.exception.code)
        self.assertEqual(set(rejected), {"ID_NOT_MINTED"})
        self.assertEqual(rt.count(), 0, "别人的登记册不能成为本 Store 的入库理由")

    def test_registry_has_no_public_backdoor(self):
        """登记册的公开面只有 mint/is_minted/reset/snapshot,没有"补登记任意 id"的入口。

        如实说明威胁模型: Python 没有真封装,`reg._minted.add(...)` 这种私有写入是拦不住的
        (下面第三段断言就是在记录这个事实,而不是假装它能被拦)。本机制防的是
        "绕过感知流水线顺手编 id"这类结构性越界,不是防同进程内的恶意代码。
        要真正做到不可伪造,需要签名/HMAC 之类外部信任根 —— 那属于架构裁决,不在 FIX-01。
        """
        from tools.provenance import EventProvenance  # noqa: PLC0415

        public = {n for n in dir(EventProvenance) if not n.startswith("_")}
        self.assertEqual(public, {"is_minted", "mint", "reset", "snapshot"})
        reg = EventProvenance(prefix="nb")
        for name in ("register", "add", "trust", "mark", "verify", "allow"):
            self.assertFalse(hasattr(reg, name), f"出现了 {name}() 就等于给伪造留了门")
        self.assertEqual(reg.snapshot(), ())
        reg.mint()
        self.assertEqual(reg.snapshot(), ("nb_001",), "登记只能通过 mint 发生")
