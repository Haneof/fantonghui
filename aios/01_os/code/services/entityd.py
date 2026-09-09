# -*- coding: utf-8 -*-
"""entityd · 实体系统（Task 5 轻量配合：只补"事件引用了但库里没有"的实体占位）

职责边界（刻意收窄）：
- 只做客观占位：谁被事件引用过、出现了几次、最早/最晚时间戳、按 id 前缀给出粗类。
- 不做身份解析、不做人物绑定推断 —— 那是 Identity/Cognition 的职责（02 §5、宪法 6.2：
  "AI 怎么理解这个实体"属于认知系统，不得写进实体库）。
- 只写自己的库 run/entity_store.db，不跨库写三棵树（schemas/trees.sql.md 隔离铁律 1/2）。
- 02 §5：允许 UNKNOWN 与多候选，不允许无证据强绑定 —— 因此占位行 confidence 恒为 0.0，
  name 恒为 null，等 Identity 实装后再由它按证据改写。

其余空壳行为（接入总线、心跳、限频日志）保持不变。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "run", "entity_store.db")

DDL = """
CREATE TABLE IF NOT EXISTS entities(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT, confidence REAL NOT NULL,
  first_seen REAL NOT NULL, last_seen REAL NOT NULL, refs INTEGER NOT NULL, evidence TEXT NOT NULL);
"""

_KINDS = (("person_", "person"), ("place_", "place"), ("org_", "org"),
          ("contract_", "object"), ("task_", "object"), ("goal_", "object"))


def kind_of(entity_id: str) -> str:
    for prefix, kind in _KINDS:
        if entity_id.startswith(prefix):
            return kind
    return "unknown"


class EntityStore:
    """事件引用到的实体 → 缺位则写 UNKNOWN 占位行（存在即计数，不覆盖已解析出的身份）。"""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript("PRAGMA journal_mode=WAL;PRAGMA synchronous=NORMAL;" + DDL)
        self.stats = {"seen": 0, "created": 0, "skipped_noncanonical": 0}

    def touch_from_event(self, msg) -> list[str]:
        if not isinstance(msg, dict):
            self.stats["skipped_noncanonical"] += 1
            return []
        ids = [str(x) for x in (msg.get("entities") or []) if isinstance(x, (str, int)) and str(x)]
        if not ids:
            return []
        ts = float(msg.get("ts") or time.time())
        event_id = str(msg.get("id") or "")
        created: list[str] = []
        with self._conn:
            for eid in ids:
                row = self._conn.execute("SELECT refs, evidence FROM entities WHERE id=?", (eid,)).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT INTO entities (id,kind,name,confidence,first_seen,last_seen,refs,evidence)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (eid, kind_of(eid), None, 0.0, ts, ts, 1,
                         json.dumps([event_id] if event_id else [])))
                    self.stats["created"] += 1
                    created.append(eid)
                else:
                    evidence = json.loads(row[1] or "[]")
                    if event_id and event_id not in evidence:
                        evidence = (evidence + [event_id])[-20:]      # 只留最近 20 条证据引用
                    self._conn.execute("UPDATE entities SET refs=?, last_seen=?, evidence=? WHERE id=?",
                                       (row[0] + 1, ts, json.dumps(evidence, ensure_ascii=False), eid))
                self.stats["seen"] += 1
        return created

    def get(self, entity_id: str):
        row = self._conn.execute("SELECT id,kind,name,confidence,refs,evidence FROM entities WHERE id=?",
                                 (entity_id,)).fetchone()
        return {"id": row[0], "kind": row[1], "name": row[2], "confidence": row[3],
                "refs": row[4], "evidence": json.loads(row[5] or "[]")} if row else None

    def all_entities(self) -> list[dict]:
        rows = self._conn.execute("SELECT id,kind,name,confidence,refs FROM entities ORDER BY id").fetchall()
        return [{"id": r[0], "kind": r[1], "name": r[2], "confidence": r[3], "refs": r[4]} for r in rows]

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


svc = AIOSService("entityd", subscribe=["evt.#"])
store = EntityStore()
_counter = {"n": 0}


def on_event(topic, from_svc, msg):
    _counter["n"] += 1
    created = store.touch_from_event(msg)
    if created and (_counter["n"] <= 3 or _counter["n"] % 50 == 0):   # 限频日志：防日志拖慢流水线
        svc.log(f"实体占位 {created} 来自 {topic}（kind={[store.get(c)['kind'] for c in created]}，"
                f"confidence=0.0 待 Identity 解析）")


svc.on_event = on_event
svc.log("服务启动（Task5 轻量配合：UNKNOWN 实体占位，不做身份推断）")
svc.run()
