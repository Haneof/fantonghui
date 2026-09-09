"""EventRuntime —— 契约来源: 02 §1 Event / 09 Sprint 1 Task 3(去重最小实现见 Task 4).

主链(本模块只负责中段):
    Semantic Event -> EventRuntime.ingest -> Event Store(JSONL)

负责(02 §1): 接收 Semantic Event、按 schemas/event.json 校验、时间排序、事件生命周期、
JSONL 持久化、raw_ref lineage 保留、窗口去重(Task 4 的最小实现)。

不负责: AI 判断、用户建议、最终唤醒决定(02 §1);不实现 Event -> World Update
(World 由调用方读 all_events() 后自行推进,本模块不 import core.world);
不实现 Event Fusion / 趋势 / Relevance / Attention(core/event/fusion.py 仍是骨架)。

09 禁止事项第 6 条: 去重只能待在这个目录里,tests/unit/test_prohibitions.py 扫仓强制。

Event provenance(09 禁止事项第 5 条): 只接受"合法感知路径铸造登记过"的 event id。
证明的来源是中立登记册 tools/provenance.py,由调用方把同一个实例交给 Perception 和本
Runtime —— 本模块不 import、不调用、也不动态加载任何 Perception 代码;Runtime 之间
零依赖,方向只有 Perception -> 登记册 <- Event Runtime。该边界由
tests/unit/test_event_runtime.py::TestBoundaries 用 AST + 注入隔离测试锁死。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.mini_jsonschema import validate  # noqa: E402
from tools.provenance import EventProvenance, default_provenance  # noqa: E402

#: Raw Signal 的特征字段。出现任何一个就说明调用方把感知层输入直接喂给了 Event Store。
RAW_MARKERS = ("signal_id", "modality", "payload")

#: raw_ref 形式: perception://temp/<event_id>?signal_id=<signal_id>
LINEAGE_RE = re.compile(r"^perception://temp/(?P<eid>[^?]+)(?:\?signal_id=(?P<sid>.+))?$")


class EventIngestError(ValueError):
    """事件被拒。带 code/field,让"拒绝"本身可断言,而不是只有一句人话。"""

    def __init__(self, code: str, detail: str, field: str = "") -> None:
        self.code = code
        self.field = field
        self.detail = detail
        super().__init__(f"[{code}] {field and field + ': ' or ''}{detail}")


def _load(name: str) -> dict:
    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _ts(event: Mapping[str, Any]) -> dt.datetime:
    return dt.datetime.fromisoformat(event["timestamp"])


def _key(event: Mapping[str, Any]) -> tuple:
    """去重指纹: 同一来源、同一语义、同一内容、同一实体集合才算重复。不含 id/timestamp/raw_ref。"""
    return (event["source"], event["type"], event["content"], tuple(sorted(event["entities"])))


class EventRuntime:
    """Event 输入、校验、排序、持久化与最小去重(02 §1)。"""

    contract = "02 §1 Event"

    def __init__(self, var_dir: str | Path, dedupe_window_s: float = 120.0,
                 schema: dict | None = None, resume: bool = True,
                 provenance: EventProvenance | None = None) -> None:
        self.dir = Path(var_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.jsonl"
        self.dropped_path = self.dir / "dropped.jsonl"
        self.dedupe_window_s = dedupe_window_s
        #: 出处证明。默认用进程级登记册;装配层应显式注入与感知层同一实例。
        self.provenance = provenance if provenance is not None else default_provenance
        self._schema = schema or _load("event.json")
        self._events: list[dict] = []
        self._recent: list[tuple[dt.datetime, tuple]] = []
        self.ingested = 0
        self.dropped_duplicate = 0
        self.rejected = 0
        self.rejections: list[str] = []
        if resume:
            self.resume()

    # ------------------------------------------------------------------ 输入
    def ingest(self, event: Mapping[str, Any], *, origin: str = "perception") -> dict | None:
        """唯一入口。校验通过才落盘;非法事件明确抛 EventIngestError,绝不修数据、绝不静默吞。

        返回入库后的事件副本;命中去重窗口时返回 None(并在 dropped.jsonl 留痕)。
        """
        self._gate(event, origin)
        stored = dict(event)
        if self.is_duplicate(stored):
            self._record_drop(stored, "DUPLICATE_WITHIN_WINDOW")
            return None
        self._events.append(stored)
        self._recent.append((_ts(stored), _key(stored)))
        self.ingested += 1
        self._append(self.path, stored)
        return stored

    def _gate(self, event: Any, origin: str) -> None:
        """四道闸门。顺序即优先级:先拒"喂错东西",再拒"伪造来源",再拒"伪造 id",最后拒"结构不合法"。"""
        if not isinstance(event, Mapping):
            self._reject("BAD_EVENT_TYPE", f"Semantic Event 必须是 dict,收到 {type(event).__name__}")
        if next((k for k in RAW_MARKERS if k in event), None) is not None:
            self._reject("RAW_SIGNAL_REJECTED",
                         "Event Runtime 只接受 Semantic Event;Raw Signal 属于 Perception Runtime 的输入(02 §0)",
                         "modality")
        if origin != "perception":
            self._reject("ORIGIN_NOT_PERCEPTION",
                         f"只接受来自 Perception Runtime 的事件,收到 origin={origin!r}(09 禁止事项 5)", "origin")
        eid = event.get("id")
        if not self.provenance.is_minted(eid):
            self._reject("ID_NOT_MINTED",
                         f"事件 id {eid!r} 未在 provenance 登记册中(不是合法感知路径铸造),"
                         f"拒绝入库(09 禁止事项 5)", "id")
        errs = validate(dict(event), self._schema)
        if errs:
            self._reject("SCHEMA_INVALID", f"不符合 schemas/event.json: {errs}")
        try:
            _ts(event)
        except (KeyError, ValueError) as exc:
            self._reject("UNPARSEABLE_TIMESTAMP", f"时间戳无法解析,无法保证排序: {exc}", "timestamp")

    def _reject(self, code: str, detail: str, field: str = "") -> None:
        self.rejected += 1
        self.rejections.append(code)
        raise EventIngestError(code, detail, field)

    # -------------------------------------------------------------- 去重(最小)
    def is_duplicate(self, event: Mapping[str, Any]) -> bool:
        """Task 4 的最小实现: 同 source+type+content+entities 落在去重窗口内即为重复。

        刻意不做语义近似、不做融合:Sprint 3 Task 1 才做策略调优 + Event Fusion 联动。
        """
        now = _ts(event)
        self._recent = [(t, k) for t, k in self._recent if (now - t).total_seconds() <= self.dedupe_window_s]
        return any(k == _key(event) for _, k in self._recent)

    def dedupe(self, events: Iterable[Mapping[str, Any]]) -> tuple[list[dict], int]:
        """批量入口: 返回 (保留下来的事件, 被丢弃数量)。按时间扫描,稳定可复现。"""
        kept: list[dict] = []
        dropped = 0
        window: list[tuple[dt.datetime, tuple]] = []
        for ev in self.order(events):
            now = _ts(ev)
            window = [(t, k) for t, k in window if (now - t).total_seconds() <= self.dedupe_window_s]
            if any(k == _key(ev) for _, k in window):
                dropped += 1
                continue
            window.append((now, _key(ev)))
            kept.append(dict(ev))
        return kept, dropped

    def _record_drop(self, event: dict, reason: str) -> None:
        """重复不是"丢了就完了":必须留痕,否则去重会退化成静默丢数据。"""
        self.dropped_duplicate += 1
        self._append(self.dropped_path, {"id": event.get("id"), "reason": reason,
                                         "dropped_at_event": event["timestamp"],
                                         "event": event})

    # ------------------------------------------------------------ 顺序与读取
    @staticmethod
    def order(events: Iterable[Mapping[str, Any]]) -> list[dict]:
        """按 timestamp 稳定排序(02 §1 时间排序)。

        相同 timestamp 保持入队顺序(python sorted 稳定 + 入队顺序=到达顺序),
        不得用 id 二次排序:那会把"谁先到"这一事实抹掉,回放结果就不可复现了。
        """
        return [dict(e) for e in sorted(events, key=_ts)]

    def all_events(self) -> list[dict]:
        """时间有序的全部入库事件(有序 + 同刻按到达序)。"""
        return self.order(self._events)

    def get(self, event_id: str) -> dict | None:
        return next((e for e in self._events if e["id"] == event_id), None)

    def events_after(self, timestamp: str) -> list[dict]:
        """增量读取(回放/续跑用):严格晚于给定时刻的事件。"""
        cut = dt.datetime.fromisoformat(timestamp)
        return self.order(e for e in self._events if _ts(e) > cut)

    def count(self) -> int:
        return len(self._events)

    # ---------------------------------------------------------------- lineage
    @staticmethod
    def lineage_of(event: Mapping[str, Any]) -> dict:
        """把 raw_ref 解成可追溯结构:事件仍能追到 Perception 的那一条 Raw Signal。"""
        ref = event.get("raw_ref")
        out = {"event_id": event.get("id"), "raw_ref": ref, "target_event_id": None, "signal_id": None}
        if isinstance(ref, str):
            m = LINEAGE_RE.match(ref)
            if m:
                out["target_event_id"] = m.group("eid")
                out["signal_id"] = m.group("sid")
            else:
                out["signal_id"] = "<unparsable>"
        return out

    def lineage(self, event_id: str) -> dict | None:
        ev = self.get(event_id)
        return None if ev is None else self.lineage_of(ev)

    # ------------------------------------------------------------ 生命周期
    def dropped(self) -> list[dict]:
        if not self.dropped_path.exists():
            return []
        return [json.loads(ln) for ln in self.dropped_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def resume(self) -> "EventRuntime":
        """重新加载后恢复:内存索引、去重窗口、计数器全部从磁盘重建(02 §1 事件生命周期)。"""
        self._events = [json.loads(ln) for ln in self._read_lines(self.path)]
        self._recent = [(_ts(e), _key(e)) for e in self._events]
        self.ingested = len(self._events)
        self.dropped_duplicate = len(self.dropped())
        return self

    def verify_persistence(self) -> list[str]:
        """内存与磁盘必须逐行一致。返回不一致项(空列表 = 一致),供测试直接断言。"""
        on_disk = [json.loads(ln) for ln in self._read_lines(self.path)]
        problems: list[str] = []
        if len(on_disk) != len(self._events):
            problems.append(f"条数不一致: 磁盘 {len(on_disk)} vs 内存 {len(self._events)}")
        for idx, (disk, mem) in enumerate(zip(on_disk, self._events)):
            if disk != mem:
                problems.append(f"第 {idx} 条不一致: {disk.get('id')} vs {mem.get('id')}")
        for line in self._read_lines(self.path):
            if "\n" in line or "\r" in line:
                problems.append("JSONL 出现断裂行")
                break
        return problems

    def stats(self) -> dict:
        """遥测:semantic_event_count 是 04 §11 / 08 B 的验收分母,口径不得在此改写。"""
        return {
            "semantic_event_count": self.ingested,
            "duplicate_dropped": self.dropped_duplicate,
            "stored": self.count(),
            "rejected": self.rejected,
            "dedupe_window_s": self.dedupe_window_s,
        }

    # ---------------------------------------------------------------- 存储原语
    @staticmethod
    def _read_lines(path: Path) -> list[str]:
        if not path.exists():
            return []
        return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    @staticmethod
    def _append(path: Path, obj: Mapping[str, Any]) -> None:
        """一行一条 JSON,写完即关闭(逐条落盘,不依赖事务)。禁止引入数据库服务。"""
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
