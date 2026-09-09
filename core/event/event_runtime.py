"""EventRuntime —— 契约来源: 02 §1 Event / 09 Sprint 1 Task 3(去重最小实现见 Task 4).

主链(本模块只负责中段):
    Semantic Event -> EventRuntime.ingest -> Event Store(JSONL)

负责(02 §1): 接收 Semantic Event、按 schemas/event.json 校验、时间排序、事件生命周期、
JSONL 持久化、raw_ref lineage 保留、窗口去重(Task 4 的最小实现)。

不负责: AI 判断、用户建议、最终唤醒决定(02 §1);不实现 Event -> World Update
(World 由调用方读 all_events() 后自行推进,本模块不 import core.world);
不实现 Event Fusion / 趋势 / Relevance / Attention(core/event/fusion.py 仍是骨架)。

09 禁止事项第 6 条: 去重只能待在这个目录里,tests/unit/test_prohibitions.py 扫仓强制。

Task 4(契约固化,不是重新实现): 全仓只允许本文件这一套去重。这里把 7 件事钉成可断言的契约 ——
窗口参数、指纹组成、窗口内判重定义、窗口外必须保留、dropped.jsonl 留痕、重启后状态恢复、
唯一实现门禁(见 tools/forbidden_scan.py)。窗口值本身(默认 120s)是实现默认值,
docs/02 与 09 都未规定它,是否升为 Contract 由架构师裁决。

Event provenance(09 禁止事项第 5 条): 只接受"合法感知路径铸造登记过"的 event id。
证明的来源是中立登记册 tools/provenance.py,由调用方把同一个实例交给 Perception 和本
Runtime —— 本模块不 import、不调用、也不动态加载任何 Perception 代码;Runtime 之间
零依赖,方向只有 Perception -> 登记册 <- Event Runtime。该边界由
tests/unit/test_event_runtime.py::TestBoundaries 用 AST + 注入隔离测试锁死。
"""
from __future__ import annotations

import datetime as dt
import json
import math
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

# ---------------------------------------------------------------- 去重契约(Task 4 固化)
#: 默认窗口(秒)。0 = 只有时间戳完全相同才算重复;越大越激进。
DEFAULT_DEDUPE_WINDOW_S: float = 120.0
#: 指纹由且仅由这些字段构成 —— 加字段=改语义,必须走架构裁决。
FINGERPRINT_FIELDS: tuple[str, ...] = ("source", "type", "content", "entities")
#: 明确被排除的字段: 身份、时间、原始指针、置信度、地点。同一事实重复到达时它们必然不同,
#: 若参与指纹会让去重永远失效(每条都"不一样")。
FINGERPRINT_EXCLUDED: tuple[str, ...] = ("id", "timestamp", "raw_ref", "confidence", "location_id")
#: 目前唯一的丢弃原因。以后新增原因必须同时进 DROPPED_REASONS,否则留痕契约测试会红。
DROP_DUPLICATE_WITHIN_WINDOW = "DUPLICATE_WITHIN_WINDOW"
DROPPED_REASONS: frozenset[str] = frozenset({DROP_DUPLICATE_WITHIN_WINDOW})
#: dropped.jsonl 每行的固定结构。用 frozenset 而不是 tuple: JSON 对象的契约是"键集合",
#: 而 _append() 以 sort_keys=True 序列化,读回来的顺序必然被规范化 —— 拿顺序当契约是假契约。
DROPPED_RECORD_FIELDS: frozenset[str] = frozenset({"id", "reason", "dropped_at_event", "event"})

#: raw_ref 形式: perception://temp/<event_id>?signal_id=<signal_id>
LINEAGE_RE = re.compile(r"^perception://temp/(?P<eid>[^?]+)(?:\?signal_id=(?P<sid>.+))?$")


class EventIngestError(ValueError):
    """事件被拒。带 code/field,让"拒绝"本身可断言,而不是只有一句人话。"""

    def __init__(self, code: str, detail: str, field: str = "") -> None:
        self.code = code
        self.field = field
        self.detail = detail
        super().__init__(f"[{code}] {field and field + ': ' or ''}{detail}")


class EventConfigError(ValueError):
    """EventRuntime 构造参数不合法。窗口是语义参数,不能靠运行时兜底。"""


def _load(name: str) -> dict:
    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _ts(event: Mapping[str, Any]) -> dt.datetime:
    return dt.datetime.fromisoformat(event["timestamp"])


def fingerprint(event: Mapping[str, Any]) -> tuple:
    """去重指纹 —— Task 4 定义的"同一条重复"的唯一判据。

    组成固定为 FINGERPRINT_FIELDS: source、type、content,加上排序后的 entities
    (顺序无关,但重复次数有关: ["a","a"] 与 ["a"] 判为不同事实)。
    不使用 id/timestamp/raw_ref/confidence/location_id(FINGERPRINT_EXCLUDED),
    否则重复到达永远无法识别。不做语义归一:那是 LLM 的活,Sprint 1 明确禁止。
    """
    src, etype, content, entities = (event["source"], event["type"], event["content"], event["entities"])
    return (src, etype, content, tuple(sorted(entities)))


def _key(event: Mapping[str, Any]) -> tuple:
    """内部别名,指向同一个 fingerprint()。刻意不复制逻辑:防止出现第二套判据。"""
    return fingerprint(event)


class EventRuntime:
    """Event 输入、校验、排序、持久化与最小去重(02 §1)。"""

    contract = "02 §1 Event"

    # ---- Task 4 契约常量:从 Runtime 本身可发现,调用方与测试不得各自硬编码字面量 ----
    DEFAULT_WINDOW_S: float = DEFAULT_DEDUPE_WINDOW_S
    FINGERPRINT_FIELDS: tuple[str, ...] = FINGERPRINT_FIELDS
    FINGERPRINT_EXCLUDED: tuple[str, ...] = FINGERPRINT_EXCLUDED
    DROPPED_REASONS: frozenset[str] = DROPPED_REASONS
    DROPPED_RECORD_FIELDS: tuple[str, ...] = DROPPED_RECORD_FIELDS
    fingerprint = staticmethod(fingerprint)

    def __init__(self, var_dir: str | Path, dedupe_window_s: float = DEFAULT_DEDUPE_WINDOW_S,
                 schema: dict | None = None, resume: bool = True,
                 provenance: EventProvenance | None = None) -> None:
        self.dir = Path(var_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.jsonl"
        self.dropped_path = self.dir / "dropped.jsonl"
        self.dedupe_window_s = self._check_window(dedupe_window_s)
        #: 出处证明。默认用进程级登记册;装配层应显式注入与感知层同一实例。
        self.provenance = provenance if provenance is not None else default_provenance
        self._schema = schema or _load("event.json")
        self._events: list[dict] = []
        self._recent: list[tuple[dt.datetime, tuple]] = []
        self.ingested = 0
        self.dropped_duplicate = 0
        self.attempted = 0
        self.rejected = 0
        self.rejections: list[str] = []
        if resume:
            self.resume()

    @staticmethod
    def _check_window(window: Any) -> float:
        """窗口契约: 必须是有限的非负 int/float。bool 不算数(它是 bool),inf/nan 会让
        "窗口内"退化成"永远重复"或"永不重复",这类配置错误必须在构造时就拒绝。"""
        if isinstance(window, bool) or not isinstance(window, (int, float)):
            raise EventConfigError(f"dedupe_window_s 必须是数字,收到 {type(window).__name__}")
        if not math.isfinite(float(window)) or window < 0:
            raise EventConfigError(f"dedupe_window_s 必须是有限非负秒数,收到 {window!r}"
                                   f"(0 = 只有同时间戳才算重复)")
        return float(window)

    # ------------------------------------------------------------------ 输入
    def ingest(self, event: Mapping[str, Any], *, origin: str = "perception") -> dict | None:
        """唯一入口。校验通过才落盘;非法事件明确抛 EventIngestError,绝不修数据、绝不静默吞。

        返回入库后的事件副本;命中去重窗口时返回 None(并在 dropped.jsonl 留痕)。
        """
        self.attempted += 1
        self._gate(event, origin)
        stored = dict(event)
        if self.is_duplicate(stored):
            self._record_drop(stored)
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

    def _record_drop(self, event: dict, reason: str = DROP_DUPLICATE_WITHIN_WINDOW) -> None:
        """重复不是"丢了就完了":必须留痕,否则去重会退化成静默丢数据。

        记录结构固定为 DROPPED_RECORD_FIELDS;reason 必须来自 DROPPED_REASONS,
        这样"丢弃了什么、为什么丢"永远可以被人或测试复核。
        """
        if reason not in DROPPED_REASONS:
            raise EventConfigError(f"未知的丢弃原因 {reason!r},允许 {sorted(DROPPED_REASONS)}")
        record = {"id": event.get("id"), "reason": reason,
                  "dropped_at_event": event["timestamp"], "event": event}
        if frozenset(record) != DROPPED_RECORD_FIELDS:
            raise EventConfigError(f"留痕记录字段漂移: {sorted(record)} != {sorted(DROPPED_RECORD_FIELDS)}")
        self.dropped_duplicate += 1
        self._append(self.dropped_path, record)

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
        """重新加载后恢复:事件索引、**去重窗口**、计数器全部从磁盘重建(02 §1 事件生命周期)。

        去重窗口必须一起恢复:否则重启后同一批事件会被二次入库(Task 4 第 6 项)。
        attempted 在重启后是保守下界 —— 历史上被拒(非法)的尝试没有落盘,无从复原。
        """
        self._events = [json.loads(ln) for ln in self._read_lines(self.path)]
        self._recent = [(_ts(e), fingerprint(e)) for e in self._events]
        self.ingested = len(self._events)
        self.dropped_duplicate = len(self.dropped())
        self.attempted = self.ingested + self.dropped_duplicate
        return self

    def conservation(self) -> dict:
        """不变式: 每一次 ingest 尝试都要有归属 —— 入库、留痕丢弃、或被拒。"""
        ledger = self.dropped()
        return {
            "attempted": self.attempted,
            "stored": self.ingested,
            "dropped_recorded": len(ledger),
            "dropped_counter": self.dropped_duplicate,
            "rejected": self.rejected,
            "balanced": (self.attempted == self.ingested + self.dropped_duplicate + self.rejected
                         and len(ledger) == self.dropped_duplicate),
        }

    def verify_dedupe_ledger(self) -> list[str]:
        """留痕契约自检: 字段齐全、原因合法、账实相符、每条都能指回被丢弃的原始事件。"""
        problems: list[str] = []
        for idx, rec in enumerate(self.dropped()):
            if frozenset(rec) != DROPPED_RECORD_FIELDS:
                problems.append(f"第 {idx} 行字段漂移: {sorted(rec)}")
                continue
            if rec["reason"] not in DROPPED_REASONS:
                problems.append(f"第 {idx} 行非法原因: {rec['reason']!r}")
            inner = rec["event"]
            if inner.get("id") != rec["id"] or inner.get("timestamp") != rec["dropped_at_event"]:
                problems.append(f"第 {idx} 行留痕与原始事件不一致")
            missing = [k for k in FINGERPRINT_FIELDS if k not in inner]
            if missing:
                problems.append(f"第 {idx} 行 event 缺少指纹字段 {missing},无法复现判重")
        if len(self.dropped()) != self.dropped_duplicate:
            problems.append(f"留痕条数 {len(self.dropped())} != 计数 {self.dropped_duplicate}")
        return problems

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
            "attempted": self.attempted,
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
