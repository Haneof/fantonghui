"""Task 4 —— Event Deduplication Contract Hardening(契约固化,不是重新实现)。

本文件一行去重逻辑都不写:唯一实现是 core/event/event_runtime.py。
这里只做 7 件事:
  1 窗口参数契约  2 指纹组成  3 同窗口重复的定义  4 窗口外必须保留
  5 dropped.jsonl 留痕  6 重启后状态恢复  7 全仓只此一套实现(含禁止语义相似度判重)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.event import event_runtime as er  # noqa: E402
from core.event.event_runtime import (  # noqa: E402
    DROPPED_RECORD_FIELDS,
    DROP_DUPLICATE_WITHIN_WINDOW,
    EventConfigError,
    EventRuntime,
    FINGERPRINT_EXCLUDED,
    FINGERPRINT_FIELDS,
    fingerprint,
)
from core.perception import perception_runtime as pr  # noqa: E402
from tools import forbidden_scan as fs  # noqa: E402

W = "2026-09-09T09:{m:02d}:00+08:00"


def ev(**over) -> dict:
    """按 schemas/event.json 造一条合法事件(唯一必须字段用默认值,其余由用例覆盖)。"""
    base = {"id": pr.issue_event_id(), "timestamp": W.format(m=0), "source": "mic", "type": "speech",
            "content": "张总提出降价", "entities": ["person_017"], "location_id": None,
            "confidence": 0.93, "raw_ref": "perception://temp/x"}
    base.update(over)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        self.var = Path(tempfile.mkdtemp(prefix="aios-d4-"))

    def tearDown(self):
        shutil.rmtree(self.var, ignore_errors=True)

    def store(self, **kw):
        return EventRuntime(self.var / "ev", **kw)


class Test1WindowParam(Base):
    """1. dedupe_window 参数契约:具名常量 + 类型与取值域。"""

    def test_default_is_named_constant(self):
        self.assertEqual(EventRuntime.DEFAULT_WINDOW_S, er.DEFAULT_DEDUPE_WINDOW_S)
        self.assertEqual(EventRuntime.DEFAULT_WINDOW_S, 120.0)
        self.assertEqual(self.store().dedupe_window_s, EventRuntime.DEFAULT_WINDOW_S)

    def test_window_domain(self):
        for good in (0, 0.5, 1, 120.0, 86400):
            with self.subTest(window=good):
                self.assertEqual(self.store(dedupe_window_s=good).dedupe_window_s, float(good))

    def test_window_rejects_garbage(self):
        for bad in (True, False, None, "120", [120], -1, -0.001, float("inf"), float("nan")):
            with self.subTest(window=repr(bad)):
                with self.assertRaises(EventConfigError):
                    self.store(dedupe_window_s=bad)

    def test_window_zero_means_same_timestamp_only(self):
        rt = self.store(dedupe_window_s=0)
        self.assertIsNotNone(rt.ingest(ev()))
        self.assertIsNone(rt.ingest(ev(timestamp=W.format(m=0))), "同刻同内容必须判重")
        self.assertIsNotNone(rt.ingest(ev(timestamp=W.format(m=1))), "差 1 分钟就不算重复")


class Test2Fingerprint(Base):
    """2. 指纹组成:说什么由谁说的,不是它被编号成几号、几点到的、置信度多少。"""

    def test_declared_fields_participate(self):
        for field in FINGERPRINT_FIELDS:
            with self.subTest(field=field):
                alt = {**ev(), field: (["person_017", "contract_003"] if field == "entities" else "CHANGED")}
                self.assertNotEqual(fingerprint(ev()), fingerprint(alt))

    def test_excluded_fields_do_not(self):
        for field in FINGERPRINT_EXCLUDED:
            with self.subTest(field=field):
                self.assertEqual(fingerprint(ev()), fingerprint({**ev(), field: "OTHER"}))

    def test_excluded_plus_declared_covers_whole_schema(self):
        """指纹字段 ∪ 排除字段 必须正好等于 event.json 的全部属性:不多不少、无遗漏。"""
        props = set(json.loads((ROOT / "schemas/event.json").read_text(encoding="utf-8"))["properties"])
        self.assertEqual(set(FINGERPRINT_FIELDS) | set(FINGERPRINT_EXCLUDED), props)

    def test_entities_are_a_multiset_not_a_sequence(self):
        self.assertEqual(fingerprint(ev(entities=["b", "a"])), fingerprint(ev(entities=["a", "b"])))
        self.assertNotEqual(fingerprint(ev(entities=["a", "a"])), fingerprint(ev(entities=["a"])))

    def test_runtime_exposes_the_same_fingerprint(self):
        """EventRuntime.fingerprint 必须就是模块级函数,不得存在第二个实现。"""
        self.assertIs(EventRuntime.fingerprint, fingerprint)
        # py3.10+ 的 staticmethod 直接就是原函数;相等即证明没有第二份实现


class Test3SameWindowDefinition(Base):
    """3. "同窗口重复"的定义,含边界闭区间。"""

    def test_boundary_is_inclusive(self):
        rt = self.store(dedupe_window_s=120)
        rt.ingest(ev(timestamp=W.format(m=0)))
        later = "2026-09-09T09:02:00+08:00"  # 恰好 120 秒
        self.assertIsNone(rt.ingest(ev(timestamp=later)), "delta == window 必须算重复(定义: <=)")

    def test_just_outside_is_not_duplicate(self):
        rt = self.store(dedupe_window_s=120)
        rt.ingest(ev(timestamp=W.format(m=0)))
        self.assertIsNotNone(rt.ingest(ev(timestamp="2026-09-09T09:02:01+08:00")))

    def test_identity_is_content_not_id(self):
        rt = self.store()
        first = ev()
        rt.ingest(first)
        for patch in ({"content": "另一句话"}, {"type": "silence"}, {"source": "asr"},
                      {"entities": ["contract_003"]}):
            with self.subTest(**patch):
                self.assertIsNotNone(rt.ingest({**first, "id": pr.issue_event_id(), **patch}),
                                     "换了任一指纹字段就是另一条事实,不得吞掉")


class Test4OutsideWindowKept(Base):
    """4. 窗口外的相同事件必须保留,且判重只与"最近一条被保留的"比较。"""

    def test_steady_repetition_alternates_keep_drop(self):
        """每 100 秒重复一次、窗口 120 秒 => 保 1 扔 1。

        这是"只与被保留者比较"的直接后果(被丢弃的不刷新窗口)。刻意写成显式契约:
        以后谁改成"被丢弃也刷新窗口",这条会红,逼他说明理由。
        """
        rt = self.store(dedupe_window_s=120)
        stamps = ["2026-09-09T09:00:00+08:00", "2026-09-09T09:01:40+08:00",
                  "2026-09-09T09:03:20+08:00", "2026-09-09T09:05:00+08:00"]
        outcomes = [rt.ingest(ev(timestamp=s)) is not None for s in stamps]
        self.assertEqual(outcomes, [True, False, True, False])
        self.assertEqual([e["timestamp"][11:19] for e in rt.all_events()], ["09:00:00", "09:03:20"])

    def test_distant_duplicates_are_all_stored(self):
        rt = self.store(dedupe_window_s=60)
        for m in (0, 5, 10, 15):
            self.assertIsNotNone(rt.ingest(ev(timestamp=W.format(m=m))))
        self.assertEqual(rt.count(), 4)
        self.assertEqual(rt.stats()["duplicate_dropped"], 0)


class Test5Ledger(Base):
    """5. dropped.jsonl 留痕:丢掉的每一条都必须可复核。"""

    def test_every_drop_is_recorded(self):
        rt = self.store()
        rt.ingest(ev())
        for _ in range(3):
            rt.ingest(ev())
        ledger = rt.dropped()
        self.assertEqual(len(ledger), 3)
        self.assertEqual(rt.verify_dedupe_ledger(), [])
        self.assertEqual({rec["reason"] for rec in ledger}, {DROP_DUPLICATE_WITHIN_WINDOW})
        self.assertEqual(frozenset(ledger[0]), DROPPED_RECORD_FIELDS)
        self.assertEqual(ledger[0]["event"]["id"], ledger[0]["id"], "留痕必须能指回被丢弃的原始事件")

    def test_reasons_are_a_closed_set(self):
        """以后要新增丢弃原因,必须同时改 DROPPED_REASONS —— 否则这里先红,不让人偷偷加。"""
        self.assertEqual(set(EventRuntime.DROPPED_REASONS), {DROP_DUPLICATE_WITHIN_WINDOW})
        rt = self.store()
        with self.assertRaises(EventConfigError):
            rt._record_drop(ev(), "BECAUSE_I_SAID_SO")

    def test_conservation_invariant(self):
        """每一次尝试都要有归属:入库 + 留痕丢弃 + 被拒 == 尝试数。丢数据必须看得见。"""
        rt = self.store()
        attempts = 0
        for i, m in enumerate((0, 0, 1, 1, 1)):
            attempts += 1
            rt.ingest(ev(timestamp=W.format(m=m)))
        with self.assertRaises(er.EventIngestError):
            attempts += 1
            rt.ingest({**ev(), "id": "evt_forged"})
        c = rt.conservation()
        self.assertTrue(c["balanced"], f"账不平: {c}")
        self.assertEqual(c["attempted"], attempts)
        self.assertEqual(c["stored"] + c["dropped_counter"] + c["rejected"], c["attempted"])

    def test_ledger_is_jsonl_and_flushed_per_line(self):
        rt = self.store()
        rt.ingest(ev())
        rt.ingest(ev())
        lines = rt.dropped_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["reason"], DROP_DUPLICATE_WITHIN_WINDOW)


class Test6Restart(Base):
    """6. 重启后 dedupe 状态必须恢复(只恢复数据不恢复窗口=重放会二次入库)。"""

    def test_window_state_restored(self):
        rt = self.store()
        rt.ingest(ev())
        again = self.store()
        self.assertIsNone(again.ingest(ev()), "重启后仍在窗口内的同内容必须继续判重")
        self.assertEqual(again.count(), 1)

    def test_ledger_count_restored(self):
        """同刻连投 3 条相同事实 => 1 入库 2 丢弃;重启后这两个数都必须复原。"""
        rt = self.store()
        for _ in range(3):
            rt.ingest(ev())
        self.assertEqual((rt.count(), rt.dropped_duplicate), (1, 2))
        again = self.store()
        self.assertEqual(again.dropped_duplicate, 2)
        self.assertEqual(len(again.dropped()), 2)
        self.assertTrue(again.conservation()["balanced"])

    def test_window_param_is_not_persisted_by_design(self):
        """窗口是运行参数,不落盘:重启换一个窗口值就用新值。写成断言防止误以为有持久化。"""
        self.store(dedupe_window_s=120).ingest(ev())
        self.assertEqual(self.store(dedupe_window_s=0).dedupe_window_s, 0.0)


class Test7SingleImplementation(Base):
    """7. 全仓只此一套去重;并禁止语义相似度/模糊匹配判重。"""

    def test_gate_currently_clean(self):
        self.assertEqual(fs.check_dedupe_home(), [])

    def test_gate_catches_second_implementation(self):
        cases = {
            "core/world/_dup2.py": "def dedupe(events):\n    return events\n",
            "core/world/_dup3.py": "class X:\n    def run(self, s):\n        return s.dedupe([])\n",
            "core/memory/_dup4.py": 'PATH = "dropped.jsonl"\n',
            "core/event/_dup5.py": "import difflib\n\n\ndef similar(a, b):\n"
                                  "    return difflib.SequenceMatcher(None, a, b).ratio()\n",
        }
        for rel, body in cases.items():
            decoy = ROOT / rel
            decoy.write_text(body, encoding="utf-8")
            try:
                with self.subTest(decoy=rel):
                    self.assertTrue(fs.check_dedupe_home(),
                                    f"往 {rel} 塞第二套去重/相似度判重没被抓到,门禁是空转的")
            finally:
                decoy.unlink()

    def test_no_similarity_dedupe_in_our_runtime(self):
        src = (ROOT / "core/event/event_runtime.py").read_text(encoding="utf-8")
        for tok in fs.SIMILARITY_TOKENS:
            self.assertNotIn(tok.lower(), src.lower(), f"出现了 {tok}:Task 4 明确禁止语义相似度判重")


if __name__ == "__main__":
    unittest.main(verbosity=2)
