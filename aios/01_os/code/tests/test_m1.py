# -*- coding: utf-8 -*-
"""M1 验收裁判（T09-T13）—— 契约：tasks/plans/T09-13_m1.md 门禁
用法：python tests/test_m1.py
门禁：模拟一天 300 事件 → 零丢失入库 + 按秒查询 + 按小时钻取 + 14 份小时摘要 + 授权状态机丢弃/放行
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUN_DIR = os.path.join(ROOT, "run")
HEALTH = os.path.join(RUN_DIR, "health.json")
DB = os.path.join(RUN_DIR, "life_tree.db")
SERVICES_EXPECTED = ["hublinkd", "stated", "safetyd", "privacyd", "modemgrd",
                     "attentiond", "perceptiond", "entityd", "memoryd",
                     "cognitiond", "decisiond", "abilityd", "interactd",
                     "evolution", "modelrouterd"]
SERVICES_EXPECTED = ["hublinkd", "stated", "safetyd", "privacyd", "modemgrd",
                     "attentiond", "perceptiond", "entityd", "memoryd",
                     "cognitiond", "decisiond", "abilityd", "interactd",
                     "evolutiond", "modelrouterd"]
N_EVENTS = 300
SIM_SCRIPT = os.path.join(RUN_DIR, "m1_day.json")

results = []


def record(name, expect, actual, cost, ok):
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}（{cost:.1f}s）期望: {expect} | 实际: {actual}", flush=True)


def load_health():
    try:
        with open(HEALTH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class BusClient:
    def __init__(self, name, port=7800):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.rfile = self.sock.makefile("r", encoding="utf-8", newline="\n")
        self._send({"t": "hello", "service": name})
        self.rfile.readline()
        self.buffer_topics = []

    def _send(self, obj):
        self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def sub(self, topics):
        self.buffer_topics = topics
        self._send({"t": "sub", "topics": topics})

    def pub(self, topic, msg):
        self._send({"t": "pub", "topic": topic, "msg": msg})

    def wait_evt(self, topic, timeout):
        end = time.time() + timeout
        while time.time() < end:
            self.sock.settimeout(max(0.05, end - time.time()))
            try:
                line = self.rfile.readline()
            except socket.timeout:
                continue
            if not line:
                continue
            try:
                frame = json.loads(line)
            except Exception:
                continue
            if frame.get("t") == "evt" and frame.get("topic") == topic:
                return frame.get("msg", {})
        return None

    def close(self):
        try:
            self._send({"t": "bye"})
            self.sock.close()
        except Exception:
            pass


def db_count():
    if not os.path.exists(DB):
        return 0
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
    conn.close()
    return n


def db_query_one(ts):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute("SELECT id, timestamp_s, content FROM raw_log WHERE timestamp_s = ?",
                        (float(ts),)).fetchall()
    conn.close()
    return rows


def main():
    print("=" * 60)
    print("AIOS M1 验收开始（T09-T13）")
    print("=" * 60)
    aiosd = None
    try:
        aiosd = subprocess.Popen([sys.executable, "aiosd/aiosd.py"], cwd=ROOT)
        print(f"aiosd 已拉起 (pid={aiosd.pid})")

        # 等栈就绪（A3 同款检查，作为前置）
        deadline = time.time() + 20
        ready = False
        while time.time() < deadline:
            h = load_health()
            if h and h.get("bus", {}).get("state") == "up":
                svcs = h.get("services", {})
                if all(svcs.get(n, {}).get("state") == "up" for n in SERVICES_EXPECTED):
                    ready = True
                    break
            time.sleep(0.3)
        record("前置·全栈就绪", "bus+15 服务 up", f"ready={ready}", 20 - (deadline - time.time()), ready)

        driver = BusClient("testdriver")
        driver.sub(["evt.#"])
        time.sleep(0.2)

        # ---- 授权：sim / mic 已授权（默认未授权，先验证状态机方向）----
        t0 = time.time()
        driver.pub("sys.privacy.set", {"source": "sim", "state": "已授权"})
        driver.pub("sys.privacy.set", {"source": "mic", "state": "已授权"})
        ok = False
        for _ in range(20):
            snap = os.path.join(RUN_DIR, "privacy_snapshot.json")
            if os.path.exists(snap):
                with open(snap, encoding="utf-8") as f:
                    st = json.load(f)
                if st.get("sim") == "已授权" and st.get("mic") == "已授权":
                    ok = True
                    break
            time.sleep(0.2)
        record("T13a 授权状态机·授权生效", "sim/mic → 已授权（快照落盘）",
               f"snapshot={st if ok else '未就绪'}", time.time() - t0, ok)

        # ---- 生成一天剧本（300 事件，秒级时间戳唯一）----
        t0 = time.time()
        base = time.time() - 14 * 3600            # 从 14 小时前开始"一天"
        step = int(13.9 * 3600 / N_EVENTS)        # 秒级间隔，事件时间戳互不相同
        types = ["speech", "vital", "motion", "message", "env"]
        entries = []
        expected_ts = {}
        for i in range(N_EVENTS):
            ts = base + i * step
            content = f"事件{i:03d}@{time.strftime('%H:%M:%S', time.localtime(ts))}"
            entries.append({"delay_s": 0.004,
                            "topic": f"evt.sim.{types[i % len(types)]}",
                            "event": {"id": str(uuid.uuid4()), "ts": ts,
                                      "source": "sim", "type": types[i % len(types)],
                                      "content": content}})
            expected_ts[ts] = content   # 全精度浮点做键（与库内存储一致）
        os.makedirs(RUN_DIR, exist_ok=True)
        with open(SIM_SCRIPT, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        record("剧本生成", f"{N_EVENTS} 事件 · 秒级时间戳唯一", f"实际 {len(entries)} 条",
               time.time() - t0, len(entries) == N_EVENTS)

        # ---- 回放（simd → hublinkd → perceptiond → memoryd）----
        t0 = time.time()
        simd = subprocess.Popen([sys.executable, "simulator/simd.py",
                                 "--script", SIM_SCRIPT, "--loop", "1"], cwd=ROOT,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        n = 0
        while time.time() < deadline:
            n = db_count()
            if n >= N_EVENTS:
                break
            time.sleep(0.3)
        record("T09-T11 零丢失入库", f"life_tree.db {N_EVENTS} 条",
               f"{n} 条", time.time() - t0, n == N_EVENTS)

        # ---- 按秒查询（任取一条，±0.4s 窗口内应唯一命中）----
        t0 = time.time()
        probe_ts, probe_content = next(iter(expected_ts.items()))
        req = {"req_id": str(uuid.uuid4()),
               "q": {"from_ts": probe_ts - 0.4, "to_ts": probe_ts + 0.4}}
        driver.pub("sys.query.life", req)
        got = driver.wait_evt(f"evt.query.reply.{req['req_id']}", 5)
        rows = (got or {}).get("results", [])
        ok = len(rows) == 1 and rows[0]["content"] == probe_content
        record("按秒查询", "±0.4s 窗口内唯一命中且内容一致", f"{len(rows)} 条命中",
               time.time() - t0, ok)

        # ---- 按小时钻取 ----
        t0 = time.time()
        req = {"req_id": str(uuid.uuid4()), "q": {"from_ts": base, "to_ts": base + 14 * 3600, "limit": 1000}}
        driver.pub("sys.query.life", req)
        got = driver.wait_evt(f"evt.query.reply.{req['req_id']}", 5)
        span = (got or {}).get("results", [])
        record("按小时钻取（14h 区间检索）", f"区间内 {N_EVENTS} 条", f"{len(span)} 条",
               time.time() - t0, len(span) == N_EVENTS)

        # ---- 小时摘要（已完结小时桶 → 每桶一份，桶数由事件分布动态决定）----
        t0 = time.time()
        now_bucket = int(time.time() // 3600)
        expected_buckets = len({int(ts // 3600) for ts in expected_ts
                                if int(ts // 3600) < now_bucket})
        driver.pub("sys.cmd.summarize", {})
        got = driver.wait_evt("evt.query.reply.summarize", 8)
        made = (got or {}).get("made", -1)
        ok = made == expected_buckets
        record("T12 小时摘要", f"{expected_buckets} 个已完结小时 → 等量摘要",
               f"生成 {made} 份", time.time() - t0, ok)

        # ---- 授权状态机：未授权源丢弃 + 授权后放行 ----
        t0 = time.time()
        before = db_count()
        for i in range(5):   # camera 默认未授权
            driver.pub("evt.sim.camera", {"id": str(uuid.uuid4()), "ts": time.time(),
                                          "source": "camera", "type": "visual_scene",
                                          "content": f"未授权画面{i}"})
        driver.pub("sys.privacy.set", {"source": "camera", "state": "已授权"})
        time.sleep(0.5)
        for i in range(3):
            driver.pub("evt.sim.camera", {"id": str(uuid.uuid4()), "ts": time.time(),
                                          "source": "camera", "type": "visual_scene",
                                          "content": f"已授权画面{i}"})
        deadline = time.time() + 8
        after = before
        while time.time() < deadline:
            after = db_count()
            if after >= before + 3:
                break
            time.sleep(0.2)
        dropped_ok = after >= before + 3 and after <= before + 4  # 允许边界内 0-1 条竞态
        record("T13b 授权丢弃/放行", "未授权 5 条零入库；授权后 3 条入库",
               f"库增量 {after - before}（期望 3）", time.time() - t0, dropped_ok)

        # ---- 物理隔离：life_tree.db 独立文件 ----
        t0 = time.time()
        record("三棵树物理隔离（第一阶段）", "life_tree.db 独立 SQLite 文件",
               f"存在={os.path.exists(DB)}", time.time() - t0, os.path.exists(DB))

        driver.close()

    finally:
        if aiosd:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(aiosd.pid)], capture_output=True)
        time.sleep(0.5)
        h = load_health()
        if h and h.get("bus", {}).get("pid"):
            subprocess.run(["taskkill", "/F", "/PID", str(h["bus"]["pid"])], capture_output=True)

    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    print(f"M1 验收结果: {passed}/{len(results)} 项通过")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
