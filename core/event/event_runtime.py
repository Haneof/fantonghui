"""EventRuntime —— 契约来源: 02 §1 Event / 09 Sprint 1 Task 3-4.

负责: 接收 Semantic Event、按 event schema 校验、去重(最小实现)、时间排序、JSONL 持久化。
不负责: AI 判断、用户建议、最终唤醒决定(02 §1)。

09 禁止事项第 6 条: 去重只能待在这个目录里。tests/unit/test_prohibitions.py 会扫仓强制这一点。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Iterable

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.perception.perception_runtime import is_minted  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402


def _load(name: str) -> dict:
    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _ts(event: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(event["timestamp"])


def _key(event: dict) -> tuple:
    return (event["source"], event["type"], event["content"], tuple(sorted(event["entities"])))


class EventRuntime:
    """Event 输入、去重与持久化(02 §1)。"""

    contract = "02 §1 Event"

    def __init__(self, var_dir: str | Path, dedupe_window_s: float = 120.0, schema: dict | None = None) -> None:
        self.dir = Path(var_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.jsonl"
        self.dedupe_window_s = dedupe_window_s
        self._schema = schema or _load("event.json")
        self._recent: list[tuple[dt.datetime, tuple]] = []
        self.ingested = 0
        self.dropped_duplicate = 0

    # ---------- 输入 ----------

    def ingest(self, event: dict, *, origin: str = "perception") -> dict | None:
        """唯一入口。origin 必须是 perception 且 id 由感知层铸造,否则拒绝(09 禁止事项 5)。"""
        if origin != "perception":
            raise ValueError(f"EventRuntime 只接受来自 Perception Runtime 的事件,收到 origin={origin!r}")
        if not is_minted(event.get("id", "")):
            raise ValueError(f"事件 {event.get('id')!r} 不是 Perception Runtime 铸造的,拒绝入库(09 禁止事项 5)")
        errs = validate(event, self._schema)
        if errs:
            raise ValueError(f"事件不符合 schemas/event.json: {errs}")
        if self.is_duplicate(event):
            self.dropped_duplicate += 1
            return None
        self._recent.append((_ts(event), _key(event)))
        self.ingested += 1
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event

    # ---------- 去重(最小实现, Sprint 3 Task 1 再做策略调优 + Fusion 联动) ----------

    def is_duplicate(self, event: dict) -> bool:
        """最小实现: 同 source+type+content+entities 落在去重窗口内即视为重复。"""
        now = _ts(event)
        self._recent = [(t, k) for t, k in self._recent if (now - t).total_seconds() <= self.dedupe_window_s]
        return any(k == _key(event) for _, k in self._recent)

    def dedupe(self, events: Iterable[dict]) -> tuple[list[dict], int]:
        """批量入口: 返回 (保留下来的事件, 被丢弃数量)。"""
        kept: list[dict] = []
        dropped = 0
        window: list[tuple[dt.datetime, tuple]] = []
        for ev in sorted(events, key=_ts):
            now = _ts(ev)
            window = [(t, k) for t, k in window if (now - t).total_seconds() <= self.dedupe_window_s]
            if any(k == _key(ev) for _, k in window):
                dropped += 1
                continue
            window.append((now, _key(ev)))
            kept.append(ev)
        return kept, dropped

    # ---------- 生命周期 ----------

    @staticmethod
    def order(events: Iterable[dict]) -> list[dict]:
        """时间排序(02 §1)。"""
        return sorted(events, key=_ts)

    def all_events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return self.order(json.loads(ln) for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip())

    def stats(self) -> dict:
        return {
            "semantic_event_count": self.ingested,
            "duplicate_dropped": self.dropped_duplicate,
            "stored": len(self.all_events()),
            "dedupe_window_s": self.dedupe_window_s,
        }
