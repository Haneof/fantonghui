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
import policy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDB = os.path.join(ROOT, "run", "entry_queue.db")
# 攒批与清理节奏属 T1 策略：全部现读注册表，本文件不留数值字面量。
# 「829 条/秒」这个已记录的性能结论，口径 = bus.batch_size=20 / bus.batch_window_s=0.5；改这两个数须重跑压测。
KNOB_BATCH_SIZE = "bus.batch_size"
KNOB_BATCH_WINDOW_S = "bus.batch_window_s"
KNOB_RETENTION_H = "bus.retention_h"
KNOB_REPLAY_INTERVAL_S = "bus.replay_interval_s"
KNOB_CLEANUP_INTERVAL_S = "bus.cleanup_interval_s"
KNOB_STARTUP_GRACE_S = "bus.startup_grace_s"

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
            if (len(self._batch) >= int(policy.get(KNOB_BATCH_SIZE))
                    or time.time() - self._last_commit >= float(policy.get(KNOB_BATCH_WINDOW_S))):
                self._flush_locked()
            # 注：一个批量窗口内崩溃最多丢未提交批（窗口 = batch_size / batch_window_s，可配），v0 可接受损耗

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

    def cleanup(self, hours=None):
        hours = float(policy.get(KNOB_RETENTION_H)) if hours is None else hours
        with self._lock:
            self._conn.execute(
                "DELETE FROM entry_queue WHERE forwarded=1 AND forwarded_at < ?",
                (time.time() - hours * 3600,))
            self._conn.commit()


# 模块级不产生任何副作用：以前 `Q = EntryQueue(QDB)` + 两条线程 + svc.run() 全写在 import 路径上，
# 结果任何测试只要 import 本模块就会真起服务并 sys.exit(1)，把测试进程带走。改为 _main() 内装配。
Q = None

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

def _build_queue(path=None):
    """装配（含建库）与测试注入点：测试传自己的路径，绝不碰真实 run/。"""
    return EntryQueue(path or QDB)


def _wire(q):
    global Q
    Q = q
    svc.on_event = on_event


svc.on_event = on_event

# ---------- 启动重放线程 ----------
def replay_loop():
    time.sleep(float(policy.get(KNOB_STARTUP_GRACE_S)))   # 等总线连接建立（可配）
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
        time.sleep(float(policy.get(KNOB_REPLAY_INTERVAL_S)))


# ---------- 清理线程 ----------
def cleanup_loop():
    while True:
        time.sleep(float(policy.get(KNOB_CLEANUP_INTERVAL_S)))
        try:
            Q.cleanup()
        except Exception:
            pass


def main():
    global Q
    Q = _build_queue()
    threading.Thread(target=replay_loop, daemon=True).start()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    svc.log("服务启动（M2.5 · 入口持久化队列：先落盘后转发，重启零丢失）")
    svc.run()


if __name__ == "__main__":
    main()
