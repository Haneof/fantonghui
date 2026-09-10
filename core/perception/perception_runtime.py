"""PerceptionRuntime —— 契约来源: 02 §0 Perception / 宪法 6.1 感知系统.

职责边界(02 §0,越界即违反 09 禁止事项 2):
    负责: 输入适配(Raw Signal 合同)、基础语义化、感知置信度、短生命周期 raw_ref。
    不负责: Relevance、Attention、Wake、AI 判断、World 最终状态、Action、建议。

主链: Raw Signal -> ingest_signal -> Semantic Event(schemas/event.json 强校验)。
本模块不 import EventRuntime/WorldRuntime/任何模型或网络库;事件 id 的登记册放在中立
设施 tools/provenance.py,所以 Event Runtime 验证出处时不需要依赖本模块。真实
VAD/ASR/Vision/IMU 适配器接入时只需换 register_adapter 的实现,对外接口(ingest_signal /
emit_semantic_event / drain)不变。

隐私(宪法 12.2): payload 只进 _transient 短生命周期缓冲,事件发出即清除;
事件里只留 raw_ref 指针,且 raw_ref 带上 signal_id 以便回溯来源而不留原文。
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path
from typing import Any, Mapping, Protocol

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.perception.raw_signal import MODALITIES, PerceptionInputError, RawSignal  # noqa: E402
from core.perception.semantics import UNKNOWN_TYPE, classify, resolve_entities  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402
from tools.provenance import EventProvenance, default_provenance  # noqa: E402

# ---------------------------------------------------------------------------
# 事件 id 的铸造权。登记册本身是中立设施(tools/provenance.py),不放在本模块里,
# 因为 Event Runtime 需要验证出处却不得反向依赖 Perception Runtime。
# 下面三个模块级函数只是"进程默认登记册"的兼容外壳:新代码请用
# PerceptionRuntime(provenance=...) 显式注入同一个实例给双方。
# ---------------------------------------------------------------------------


def issue_event_id() -> str:
    """用进程默认登记册铸造一个事件 id(等价于 default_provenance.mint())。"""
    return default_provenance.mint()


def is_minted(eid: str) -> bool:
    return default_provenance.is_minted(eid)


def reset_id_space() -> None:
    """回放/测试用:重置默认登记册,保证同一时间线得到同一批 id(确定性验收 A-2)。"""
    default_provenance.reset()


class PerceptionAdapter(Protocol):
    """适配器合同: 只会"吐出 raw signal",不做语义化、不碰 Event/World。"""

    def read(self) -> list[Any]:
        ...


class PerceptionRuntime:
    """把 raw signal 语义化为标准 Semantic Event(02 §0)。"""

    contract = "02 §0 Perception"
    #: 对外暴露的合法模态集合,方便测试与文档对齐(不是第二套 schema)。
    modalities: tuple[str, ...] = MODALITIES

    def __init__(self, date: str = "2026-09-09", timezone: str = "+08:00",
                 provenance: EventProvenance | None = None) -> None:
        self.date = date
        self.timezone = timezone
        #: 铸造权。装配时应把同一个实例交给 Event Runtime,双方共用一份登记册。
        self.provenance = provenance if provenance is not None else default_provenance
        self.adapters: list[PerceptionAdapter] = []
        self._transient: dict[str, Any] = {}
        self._seen_signals: set[str] = set()
        self.emitted = 0
        self.unknown = 0
        self.rejected = 0
        self.rejections: list[str] = []

    # ---------------------------------------------------------------- 输入适配
    def register_adapter(self, adapter: PerceptionAdapter) -> "PerceptionRuntime":
        """接入 mock 或真实(VAD/ASR/Vision/IMU/Phone)适配器。"""
        self.adapters.append(adapter)
        return self

    def drain(self) -> list[dict]:
        """从已注册适配器拉取全部 raw signal 并语义化。"""
        return [self.ingest_signal(sig) for adapter in self.adapters for sig in adapter.read()]

    def ingest_signal(self, raw: Any) -> dict:
        """标准输入边界:非法输入明确抛错(禁止静默吞错),合法输入产出 Semantic Event。"""
        try:
            signal = RawSignal.from_dict(raw)
        except PerceptionInputError as exc:
            self.rejected += 1
            self.rejections.append(exc.code)
            raise
        if signal.signal_id in self._seen_signals:
            self.rejected += 1
            self.rejections.append("DUPLICATE_SIGNAL_ID")
            raise PerceptionInputError("DUPLICATE_SIGNAL_ID",
                                       f"signal_id {signal.signal_id!r} 已被本实例消费过,不得重复语义化",
                                       "signal_id")
        self._seen_signals.add(signal.signal_id)
        return self.emit_semantic_event(signal)

    # ---------------------------------------------------------------- 语义化
    def emit_semantic_event(self, signal: RawSignal | Mapping[str, Any]) -> dict:
        """单个 Raw Signal -> Semantic Event。未命中规则降为低置信度事件,不丢弃(08 E)。"""
        sig = signal if isinstance(signal, RawSignal) else RawSignal.from_dict(signal)
        text = sig.semantic_text
        etype, conf, channel = classify(sig.modality, text)
        if etype == UNKNOWN_TYPE:
            self.unknown += 1

        entities = resolve_entities(text)
        location = next((e for e in entities if e.startswith("place_")), None)
        eid = self.provenance.mint()
        self._transient[eid] = dict(sig.payload)  # 原始数据只进短生命周期缓冲区
        event = {
            "id": eid,
            "timestamp": self._iso(sig.timestamp),
            "source": channel or sig.source,
            "type": etype,
            "content": text,
            "entities": entities,
            "location_id": location,
            "confidence": conf,
            "raw_ref": f"perception://temp/{eid}?signal_id={sig.signal_id}",
        }
        self._check(event)
        self.purge_raw(eid)  # 事件发出即销毁原始体(宪法 12.2 录音/图像即删)
        self.emitted += 1
        return event

    def _iso(self, stamp: str) -> str:
        """把 HH:MM[:SS] 补成带日期与时区的 ISO-8601;已是 ISO 的原样通过。"""
        if "T" in stamp:
            return stamp
        hh, mm, ss = (*stamp.split(":"), "0", "0")[:3]
        return f"{self.date}T{int(hh):02d}:{int(mm):02d}:{int(ss):02d}{self.timezone}"

    @staticmethod
    def _check(event: dict) -> dict:
        """感知输出必须符合 schemas/event.json,否则宁可不产出(02 §0 + 03 Canonical naming rule)。"""
        errs = validate(event, _EVENT_SCHEMA)
        if errs:
            raise ValueError(f"感知输出不符合 event schema: {errs}")
        return event

    # ---------------------------------------------------------------- 隐私
    def purge_raw(self, eid: str) -> None:
        self._transient.pop(eid, None)

    def raw_still_held(self) -> int:
        """必须恒为 0:任何发出过的事件都不应再持有原始体。"""
        return len(self._transient)

    def stats(self) -> dict:
        """遥测:漏斗计数。注意这里不产生任何判断语义,只是数数。"""
        return {
            "emitted": self.emitted,
            "unknown": self.unknown,
            "rejected": self.rejected,
            "raw_still_held": self.raw_still_held(),
        }


def _load(name: str) -> dict:
    import json

    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


_EVENT_SCHEMA = _load("event.json")
