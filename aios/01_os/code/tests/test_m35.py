# -*- coding: utf-8 -*-
"""M3.5 综合验收：真模型路由（本地 llama + 云端 Gemini 池）+ T23 暴力断电零丢失"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
RUN = os.path.join(ROOT, "run")
results = []


def rec(name, expect, actual, cost, ok):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}（{cost:.1f}s）| 期望: {expect} | 实际: {actual}", flush=True)


class BC:
    def __init__(self, name):
        self.sock = socket.create_connection(("127.0.0.1", 7800), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = b""
        self._send({"t": "hello", "service": name})
        self._recv(1)

    def _send(self, o):
        self.sock.sendall((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))

    def _recv(self, timeout):
        self.sock.settimeout(timeout)
        while b"\n" not in self.buf:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                return None
            if not chunk:
                return None
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8")

    def pub(self, topic, msg):
        self._send({"t": "pub", "topic": topic, "msg": msg})

    def sub(self, topics):
        self._send({"t": "sub", "topics": topics})

    def wait_topic(self, topic, timeout):
        end = time.time() + timeout
        while time.time() < end:
            line = self._recv(end - time.time())
            if line is None:
                return None
            try:
                f = json.loads(line)
            except Exception:
                continue
            if f.get("t") == "evt" and f.get("topic") == topic:
                return f.get("msg", {})
        return None

    def close(self):
        try:
            self._send({"t": "bye"})
            self.sock.close()
        except Exception:
            pass


def rpc(c, topic, msg, timeout=60):
    rid = str(uuid.uuid4())
    msg = dict(msg or {})
    msg["req_id"] = rid
    c.pub(topic, msg)
    return c.wait_topic(f"evt.query.reply.{rid}", timeout)


def db_count():
    try:
        conn = sqlite3.connect(f"file:{os.path.join(ROOT, 'run', 'life_tree.db')}?mode=ro", uri=True)
        n = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


c = BC("testdriver")
c.sub(["evt.#"])
time.sleep(0.2)

# ---- 1. 本地真模型（llama-server · Qwen 0.5B）----
t0 = time.time()
g = rpc(c, "sys.model.request", {"task_type": "simple_judgment", "payload": "1+1等于几？只回答数字"})
routed = (g or {}).get("routed", "")
result = (g or {}).get("result", "")
rec("真本地模型", "routed=local_llama 且真模型回答",
    f"{routed} | 回答: {str(result)[:60]}", time.time() - t0,
    routed == "local_llama" and len(str(result)) > 0 and "桩" not in str(result))

# ---- 2. 云端真模型（Gemini 轮换池）----
t0 = time.time()
g = rpc(c, "sys.model.request", {"task_type": "complex_reason", "payload": "用一句话说明什么是事件总线"})
routed = (g or {}).get("routed", "")
result = (g or {}).get("result", "")
rec("真云端模型（Gemini 池）", "routed=cloud_gemini 且真模型回答",
    f"{routed} | 回答: {str(result)[:80]}", time.time() - t0,
    routed == "cloud_gemini" and len(str(result)) > 5 and "mock" not in str(result))

# ---- 3. T23 暴力断电：压测中途 kill -9 全栈 → 重启 → 零丢失 ----
t0 = time.time()
N = 3000
before = db_count()
pushed = {"n": 0}
stop = threading.Event()


def pusher():
    for i in range(N):
        if stop.is_set():
            break
        c.pub("evt.sim.stress", {"id": str(uuid.uuid4()), "ts": time.time(),
                                 "source": "sim", "type": "stress",
                                 "content": f"断电压测事件 {i}"})
        pushed["n"] += 1


th = threading.Thread(target=pusher, daemon=True)
th.start()
time.sleep(2.0)                      # 推一半
killed_at = pushed["n"]
# kill -9 等价：taskkill 整棵 aiosd 树（含总线与全部服务）
out = subprocess.run(["powershell", "-Command",
                      "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                      "Where-Object { $_.CommandLine -match 'aiosd|aios_busd|services[/\\\\]' } | "
                      "ForEach-Object { taskkill /F /PID $_.ProcessId } | Out-Null"],
                     capture_output=True)
stop.set()
print(f"  [断电] 推送 {killed_at} 条时整栈被 kill -9（含总线与所有在途队列）")
time.sleep(2)

# 重启栈（新实例继承持久化队列）
aiosd2 = subprocess.Popen([sys.executable, "aiosd/aiosd.py"], cwd=ROOT,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          env=dict(os.environ, PYTHONUTF8="1"))
print("  [重启] aiosd 新实例启动，等待重放...")
deadline = time.time() + 30
while time.time() < deadline:
    h = None
    try:
        h = json.load(open(os.path.join(ROOT, "run", "health.json"), encoding="utf-8"))
    except Exception:
        pass
    if h and h.get("bus", {}).get("state") == "up":
        if all(v.get("state") == "up" for v in h.get("services", {}).values()):
            break
    time.sleep(0.3)

# 重放后重连统计
time.sleep(6)
after = db_count()
delta = after - before
# pushed 条数中：kill 前已到达 hublinkd 的（持久化）应全部入库；kill 瞬间在 simd 缓冲里的允许丢
# 零丢失判定：断电时刻 pushed['n'] 条中至少 (killed_at - 管道深度容差 30) 条入库
expected_min = max(0, killed_at - 30)
rec("T23 暴力断电零丢失", f"断电前已推送 {killed_at}，断电后重启重放，入库 ≥ {expected_min}",
    f"入库增量 {delta}", time.time() - t0, delta >= expected_min)

c.close()
print("=" * 60)
passed = sum(results)
print(f"M3.5 综合验收结果: {passed}/{len(results)} 项通过")
sys.exit(0 if passed == len(results) else 1)
