"""PerceptionRuntime —— 契约来源: 02 §0 Perception / 宪法 6.1 感知系统.

Sprint 1 只做"最小合同":把 raw signal 变成符合 schemas/event.json 的 Semantic Event。
真实 VAD/ASR/Vision/IMU 适配器接入时,替换 MOCK_SEMANTICS 与 register_adapter 的适配器即可,
本类的对外接口(ingest_signal / emit_semantic_event)不变。

隐私约束(宪法 12.2):原始数据只存在于 _transient 短生命周期缓冲区,事件发出即清除;
事件里只保留 raw_ref 引用。
"""
from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.mini_jsonschema import validate  # noqa: E402

#: 由感知层铸造的事件 id 登记处。EventRuntime 只接受这里登记过的 id,
#: 用于机械执行 09 禁止事项第 5 条(不得绕过 Perception Runtime)。
_MINTED: set[str] = set()
_seq = itertools.count(1)


def issue_event_id() -> str:
    eid = f"evt_{next(_seq):03d}"
    _MINTED.add(eid)
    return eid


def is_minted(eid: str) -> bool:
    return eid in _MINTED


def reset_id_space() -> None:
    """回放/测试用:重置 id 计数,保证同一时间线得到同一批 id。"""
    global _seq
    _seq = itertools.count(1)
    _MINTED.clear()


#: Sprint 1 的 Mock 语义规则表(确定性规则,不引入任何模型)。
MOCK_SEMANTICS: list[tuple[re.Pattern[str], str, str, float]] = [
    (re.compile(r"到公司|到达|抵达"), "arrival", "gps", 0.98),
    (re.compile(r"进入|到场"), "person_enter", "mic", 0.90),
    (re.compile(r"提出降价|砍价|再次谈价格|谈价格"), "price_negotiation", "mic", 0.93),
    (re.compile(r"沉默|不说话"), "silence", "imu", 0.75),
    (re.compile(r"打开|查看"), "document_open", "screen", 0.95),
    (re.compile(r"合同"), "contract_discussion", "mic", 0.90),
]

#: Mock 实体解析表。真实实现由 Identity Runtime 异步绑定(02 §5),此处仅占位。
MOCK_ENTITIES = {"张总": "person_017", "小王": "person_021", "合同": "contract_003", "公司": "place_004"}

UNKNOWN_SOURCE = "simulator"
UNKNOWN_CONFIDENCE = 0.40


class PerceptionRuntime:
    """把 raw signal 语义化为标准 Semantic Event(02 §0)。"""

    contract = "02 §0 Perception"

    def __init__(self, date: str = "2026-09-09", timezone: str = "+08:00") -> None:
        self.date = date
        self.timezone = timezone
        self.adapters: list[Any] = []
        self._transient: dict[str, Any] = {}
        self.emitted = 0
        self.unknown = 0

    def register_adapter(self, adapter: Any) -> "PerceptionRuntime":
        """接入 mock 或真实(VAD/ASR/Vision/IMU/Phone)适配器。"""
        self.adapters.append(adapter)
        return self

    def _iso(self, hhmm: str) -> str:
        parts = (hhmm or "").strip().split(":")
        hh = parts[0].rjust(2, "0") if parts and parts[0] else "00"
        mm = parts[1].rjust(2, "0") if len(parts) > 1 and parts[1] else "00"
        return f"{self.date}T{hh}:{mm}:00{self.timezone}"

    def _resolve_entities(self, text: str) -> list[str]:
        return [eid for name, eid in MOCK_ENTITIES.items() if name in text]

    def emit_semantic_event(self, raw: dict) -> dict:
        """单个 raw signal -> Semantic Event。未知输入不丢弃,降为低置信度事件(08 E)。"""
        text = str(raw.get("text", "")).strip()
        etype, source, conf = "unrecognized", str(raw.get("channel", UNKNOWN_SOURCE)), UNKNOWN_CONFIDENCE
        for rx, name, src, c in MOCK_SEMANTICS:
            if rx.search(text):
                etype, source, conf = name, str(raw.get("channel", src)), c
                break
        else:
            self.unknown += 1

        entities = list(raw.get("entities") or self._resolve_entities(text))
        location = raw.get("location_id") or next((e for e in entities if e.startswith("place_")), None)
        eid = issue_event_id()
        self._transient[eid] = raw.get("payload", text)  # 原始数据只进短生命周期缓冲区
        event = {
            "id": eid,
            "timestamp": self._iso(str(raw.get("at", ""))),
            "source": source,
            "type": etype,
            "content": text,
            "entities": entities,
            "location_id": location,
            "confidence": conf,
            "raw_ref": f"perception://temp/{eid}",
        }
        self._check(event)
        self.purge_raw(eid)  # 事件发出即销毁原始体(宪法 12.2 录音/图像即删)
        self.emitted += 1
        return event

    @staticmethod
    def _check(event: dict) -> dict:
        """感知输出必须符合 schemas/event.json,否则宁可不产出(02 §0 + 03 Canonical naming rule)。"""
        errs = validate(event, _EVENT_SCHEMA)
        if errs:
            raise ValueError(f"感知输出不符合 event schema: {errs}")
        return event

    def ingest_signal(self, raw: dict) -> dict:
        return self.emit_semantic_event(raw)

    def purge_raw(self, eid: str) -> None:
        self._transient.pop(eid, None)

    def raw_still_held(self) -> int:
        """必须恒为 0:任何发出过的事件都不应再持有原始体。"""
        return len(self._transient)

    def drain(self) -> list[dict]:
        """从已注册适配器拉取全部 raw signal 并语义化。"""
        return [self.emit_semantic_event(sig) for adapter in self.adapters for sig in adapter.read()]


def _load(name: str) -> dict:
    import json

    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


_EVENT_SCHEMA = _load("event.json")
