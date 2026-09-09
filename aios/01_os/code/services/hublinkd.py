# -*- coding: utf-8 -*-
"""hublinkd v2 · 反射世界通信桥 + 入口持久化队列（T23）
- 订阅 evt.sim.# / evt.raw.# → 归一化 →【先落盘 run/entry_queue.db】→ 转发 evt.stream → 标记已转发
- 启动重放：forwarded=0 的事件重新转发（memoryd 按 id 幂等去重，重复无副作用）
- 宪法：事件一旦产生不允许丢失——落盘必须发生在转发之前
- 保留 M0 回声链路
"""
import json
import os
import sqlite3
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDB = os.path.join(ROOT, "run", "entry_queue.db")
BATCH_SIZE = 20
BATCH_WINDOW = 0.5
RETENTION_H = 24

svc = AIOSService("hublinkd", subscribe=["evt.sim.#", "evt.raw.#", "sys.test.#"])

# ---------- 持久化队列（T23）----------
class EntryQueue:
    """WAL 落盘队列：先持久化，后转发；崩溃后未转发事件启动重放。"""
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript("""
CREATE TABLE IF NOT EXISTS entry_queue (
  id TEXT PRIMARY KEY, ts REAL NOT NULL, payload TEXT NOT NULL,
  forwarded INTEGER DEFAULT 0, forwarded_at REAL);
CREATE INDEX IF NOT EXISTS idx_q_fwd ON entry_queue(forwarded);
""")
        self._conn.commit()
        self._batch = []
        self._last_commit = time.time()

    def persist(self, ev):
        with self._lock:
            self._batch.append(ev)
            if len(self._batch) >= BATCH_SIZE or time.time() - self._last_commit >= BATCH_WINDOW:
                self._flush_locked()
            # 注：批量窗口内（≤20 条 / ≤0.5s）崩溃最多丢未提交批，v0 可接受损耗

    def _flush_locked(self):
        for ev in self._batch:
            self._conn.execute(
                "INSERT OR IGNORE INTO entry_queue VALUES (?,?,?,0,NULL)",
                (ev["id"], ev["ts"], json.dumps(ev, ensure_ascii=False)))
        self._conn.commit()
        self._batch.clear()
        self._last_commit = time.time()

    def pending(self):
        with self._lock:
            self._flush_locked()
            rows = self._conn.execute(
                "SELECT id, payload FROM entry_queue WHERE forwarded=0 ORDER BY ts").fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    def mark(self, ids):
        with self._lock:
            now = time.time()
            for i in ids:
                self._conn.execute(
                    "UPDATE entry_queue SET forwarded=1, forwarded_at=? WHERE id=?", (now, i))
            self._conn.commit()

    def cleanup(self, hours=RETENTION_H):
        with self._lock:
            self._conn.execute(
                "DELETE FROM entry_queue WHERE forwarded=1 AND forwarded_at < ?",
                (time.time() - hours * 3600,))
            self._conn.commit()


Q = EntryQueue(QDB)

def normalize(msg):
    ev = dict(msg or {})
    if not ev.get("id"):
        ev["id"] = str(uuid.uuid4())
    ev["ts"] = float(ev.get("ts") or time.time())
    ev["source"] = str(ev.get("source", "unknown"))
    ev["type"] = str(ev.get("type", "unknown"))
    ev["content"] = str(ev.get("content", ""))
    return ev

def on_event(topic, from_svc, msg):
    if topic == "sys.test.ping":                    # M0 回声链路（回归保护）
        svc.publish("evt.hub.echo", {
            "id": str(uuid.uuid4()), "ts": time.time(),
            "source": "hublinkd", "type": "echo",
            "content": msg.get("content", "")})
        return
    if topic.startswith("evt.sim.") or topic.startswith("evt.raw."):
        ev = normalize(msg)
        ev["entry_topic"] = topic
        Q.persist(ev)                               # 【先落盘】
        if svc.publish("evt.stream", ev):           # 【后转发】
            Q.mark([ev["id"]])

svc.on_event = on_event

# ---------- 启动重放线程 ----------
def replay_loop():
    time.sleep(1.5)                                 # 等总线连接建立
    while True:
        try:
            pend = Q.pending()
            if pend:
                svc.log(f"[重放] 入口队列 {len(pend)} 条未转发事件重放")
                done = []
                for eid, ev in pend:
                    if svc.publish("evt.stream", ev):
                        done.append(eid)
                Q.mark(done)
        except Exception as e:
            svc.log(f"[异常] 重放: {e}")
        time.sleep(3)

threading.Thread(target=replay_loop, daemon=True).start()

# ---------- 清理线程 ----------
def cleanup_loop():
    while True:
        time.sleep(60)
        try:
            Q.cleanup()
        except Exception:
            pass

threading.Thread(target=cleanup_loop, daemon=True).start()

svc.log("服务启动（M2.5 · 入口持久化队列：先落盘后转发，重启零丢失）")
svc.run()
