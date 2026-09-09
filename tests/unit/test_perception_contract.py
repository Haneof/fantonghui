"""Sprint 1 Task 2 —— Raw Signal 输入合同的异常处理(实现要求 五)。

要求: 缺失 signal_id / 缺失 timestamp / 缺失 source / 无效 modality / 非法 payload
必须被明确拒绝,禁止静默吞错。这里把每一条都做成可执行断言。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.perception.perception_runtime import PerceptionRuntime  # noqa: E402
from core.perception.raw_signal import MODALITIES, PerceptionInputError, RawSignal  # noqa: E402


def ok(**over) -> dict:
    base = {"signal_id": "sig-1", "timestamp": "09:00", "source": "simulator",
            "modality": "text", "payload": {"text": "到公司"}}
    base.update(over)
    return base


class TestRejectsBadInput(unittest.TestCase):
    def setUp(self):
        self.p = PerceptionRuntime()

    def assert_rejected(self, raw: dict, code: str, field: str = "") -> None:
        before = self.p.emitted
        with self.assertRaises(PerceptionInputError) as ctx:
            self.p.ingest_signal(raw)
        self.assertEqual(ctx.exception.code, code, f"期望错误码 {code},实得 {ctx.exception.code}")
        if field:
            self.assertEqual(ctx.exception.field, field)
        self.assertEqual(self.p.emitted, before, "被拒输入不得产出任何事件")
        self.assertEqual(self.p.emitted, self.p.stats()["emitted"])

    def test_missing_signal_id(self):
        raw = ok()
        del raw["signal_id"]
        self.assert_rejected(raw, "MISSING_FIELD", "signal_id")

    def test_missing_timestamp(self):
        raw = ok()
        del raw["timestamp"]
        self.assert_rejected(raw, "MISSING_FIELD", "timestamp")

    def test_missing_source(self):
        raw = ok()
        del raw["source"]
        self.assert_rejected(raw, "MISSING_FIELD", "source")

    def test_missing_modality(self):
        raw = ok()
        del raw["modality"]
        self.assert_rejected(raw, "MISSING_FIELD", "modality")

    def test_missing_payload(self):
        raw = ok()
        del raw["payload"]
        self.assert_rejected(raw, "MISSING_FIELD", "payload")

    def test_blank_signal_id(self):
        self.assert_rejected(ok(signal_id="   "), "EMPTY_FIELD", "signal_id")

    def test_none_source(self):
        self.assert_rejected(ok(source=None), "MISSING_FIELD", "source")

    def test_non_string_source(self):
        self.assert_rejected(ok(source=7), "BAD_TYPE", "source")

    def test_invalid_modality(self):
        self.assert_rejected(ok(modality="smell"), "BAD_MODALITY", "modality")

    def test_all_declared_modalities_are_accepted(self):
        for i, m in enumerate(MODALITIES):
            with self.subTest(modality=m):
                payload = {"text": "到公司"} if m == "text" else {
                    "audio_transcript": {"transcript": "谈价格"},
                    "sensor": {"sensor": "entry_sensor", "state": "opened"},
                    "vision": {"objects": ["张总"]},
                    "calendar": {"title": "合同评审会"},
                }[m]
                ev = self.p.ingest_signal(ok(signal_id=f"sig-{i}", modality=m, payload=payload))
                self.assertNotEqual(ev["type"], "unrecognized", f"{m} 应有规则命中")

    def test_bad_timestamp_format(self):
        self.assert_rejected(ok(timestamp="昨天早上"), "BAD_TIMESTAMP", "timestamp")

    def test_raw_is_not_a_mapping(self):
        for bad in ("到公司", ["到公司"], None, 3):
            with self.subTest(raw=repr(bad)):
                self.assert_rejected(bad, "BAD_RAW_TYPE")

    def test_illegal_payload_shape(self):
        self.assert_rejected(ok(payload="到公司"), "BAD_PAYLOAD", "payload")

    def test_payload_missing_required_key(self):
        self.assert_rejected(ok(payload={"say": "到公司"}), "BAD_PAYLOAD", "payload.text")

    def test_payload_empty_text(self):
        self.assert_rejected(ok(payload={"text": "  "}), "BAD_PAYLOAD", "payload.text")

    def test_payload_wrong_type(self):
        self.assert_rejected(ok(modality="audio_transcript",
                                payload={"transcript": "谈价格", "duration_ms": "两秒"}),
                             "BAD_PAYLOAD", "payload.duration_ms")

    def test_payload_bool_is_not_int(self):
        self.assert_rejected(ok(modality="audio_transcript", payload={"transcript": "谈价格", "duration_ms": True}),
                             "BAD_PAYLOAD", "payload.duration_ms")

    def test_payload_unknown_key(self):
        self.assert_rejected(ok(payload={"text": "到公司", "raw_audio": "bytes"}),
                             "UNKNOWN_PAYLOAD_KEY", "payload.raw_audio")

    def test_vision_empty_objects_rejected(self):
        self.assert_rejected(ok(modality="vision", payload={"objects": []}), "BAD_PAYLOAD", "payload.objects")

    def test_duplicate_signal_id_rejected(self):
        self.p.ingest_signal(ok())
        self.assert_rejected(ok(), "DUPLICATE_SIGNAL_ID", "signal_id")

    def test_no_silent_swallow(self):
        """每一条错误都必须进 rejected 计数,否则"拒收"会变成悄悄丢数据。"""
        for bad in (ok(signal_id=""), ok(modality="x"), ok(payload={})):
            with self.assertRaises(PerceptionInputError):
                self.p.ingest_signal(bad)
        st = self.p.stats()
        self.assertEqual(st["rejected"], 3)
        self.assertEqual(st["emitted"], 0)
        self.assertEqual(self.p.raw_still_held(), 0, "被拒输入不得在瞬态里留下原始体")

    def test_error_is_valueerror_for_callers(self):
        self.assertTrue(issubclass(PerceptionInputError, ValueError))

    def test_raw_signal_is_frozen_and_equal_by_value(self):
        sig = RawSignal.from_dict(ok())
        with self.assertRaises(Exception):
            sig.payload = {}  # type: ignore[misc]
        self.assertEqual(sig, RawSignal.from_dict(ok()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
