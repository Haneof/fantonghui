"""StateRuntime —— 契约来源: 02 §3 State.

重点(02 §3): 不要只保存值,要保存变化。因此本模块提供 diff(),World Runtime 用它生成
World Change 的 before/after。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.mini_jsonschema import validate  # noqa: E402

EMPTY_STATE = {
    "timestamp": "",
    "user": {},
    "location": {},
    "mode": "UNKNOWN",
    "people": [],
    "environment": {},
    "active_situations": [],
    "active_goals": [],
    "pending_tasks": [],
}


class StateRuntime:
    """当前世界快照 + 状态变化 Delta(02 §3)。"""

    contract = "02 §3 State"

    def __init__(self, schema: dict | None = None) -> None:
        self._state = copy.deepcopy(EMPTY_STATE)
        self._schema = schema or json.loads((_ROOT / "schemas" / "world_state.json").read_text(encoding="utf-8"))

    def snapshot(self) -> dict:
        return copy.deepcopy(self._state)

    def replace(self, state: dict) -> None:
        errs = validate(state, self._schema)
        if errs:
            raise ValueError(f"world state 不符合 schemas/world_state.json: {errs}")
        self._state = copy.deepcopy(state)

    @staticmethod
    def diff(before: dict, after: dict) -> dict:
        """返回 {字段: {"before": …, "after": …}};无变化返回空 dict。"""
        out: dict[str, dict] = {}
        for key in sorted(set(before) | set(after)):
            b, a = before.get(key), after.get(key)
            if b != a:
                out[key] = {"before": copy.deepcopy(b), "after": copy.deepcopy(a)}
        return out

    @staticmethod
    def changed_slots(diff: dict, side: str) -> dict:
        return {k: v[side] for k, v in diff.items()}
