# -*- coding: utf-8 -*-
"""M2 验收裁判（T14-T16）—— 契约 tasks/contracts_m2.md 门禁
用法：python tests/test_m2.py
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
COG_DB = os.path.join(RUN_DIR, "cognitive_tree.db")
LEASE_STATS = os.path.join(RUN_DIR, "lease_stats.json")
SERVICES = ["hublinkd", "stated", "safetyd", "privacyd", "modemgrd", "attentiond",
            "perceptiond", "entityd", "memoryd", "cognitiond", "decisiond",
            "abilityd", "interactd", "evolutiond", "modelrouterd"]
results = []


def rec(name, expect, actual, cost, ok):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}（{cost:.1f}s）期望: {expect} | 实际: {actual}", flush=True)


class BusClient:
    def __init__(self, name, port=7800):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = b""
        self._send({"t": "hello", "service": name})
        self._recv_line(5)   # 吃掉 welcome

    def _send(self, obj):
        self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def _recv_line(self, timeout):
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

    def wait_reply(self, req_id, timeout):
        end = time.time() + timeout
        while time.time() < end:
            line = self._recv_line(end - time.time())
            if line is None:
                return None
            try:
                frame = json.loads(line)
            except Exception:
                continue
            if frame.get("t") == "evt" and frame.get("topic") == f"evt.query.reply.{req_id}":
                return frame.get("msg", {})
        return None

    def wait_topic(self, topic, timeout):
        end = time.time() + timeout
        while time.time() < end:
            line = self._recv_line(end - time.time())
            if line is None:
                return None
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


def load_health():
    try:
        with open(HEALTH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    print("=" * 60)
    print("AIOS M2 验收开始（T14-T16）")
    print("=" * 60)
    aiosd = None
    try:
        aiosd = subprocess.Popen([sys.executable, "aiosd/aiosd.py"], cwd=ROOT,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 20
        ready = False
        while time.time() < deadline:
            h = load_health()
            if h and h.get("bus", {}).get("state") == "up":
                sv = h.get("services", {})
                if all(sv.get(n, {}).get("state") == "up" for n in SERVICES):
                    ready = True
                    break
            time.sleep(0.3)
        rec("前置·全栈就绪", "bus+15 服务 up", f"ready={ready}", 20 - (deadline - time.time()), ready)

        c = BusClient("testdriver")
        c.sub(["evt.#"])
        time.sleep(0.2)

        # ---- T14a 认知树物理隔离 + assert 两条 ----
        t0 = time.time()
        r1 = str(uuid.uuid4())
        c.pub("sys.cognition.assert", {"req_id": r1, "kind": "BELIEF",
                                       "conclusion": "张总更在意交付而非价格",
                                       "confidence": 0.72, "evidence": ["raw:1", "raw:2"],
                                       "epistemic": "INFERRED"})
        g1 = c.wait_reply(r1, 5)
        ok1 = bool(g1 and g1.get("status") == "stored" and g1.get("epistemic") == "INFERRED")
        id_inferred = g1.get("id") if g1 else None

        r2 = str(uuid.uuid4())
        c.pub("sys.cognition.assert", {"req_id": r2, "kind": "BELIEF",
                                       "conclusion": "张总是我们的客户",
                                       "confidence": 1.0, "evidence": ["raw:0"],
                                       "epistemic": "KNOWN"})
        g2 = c.wait_reply(r2, 5)
        ok2 = bool(g2 and g2.get("status") == "stored" and g2.get("epistemic") == "KNOWN")
        id_known = g2.get("id") if g2 else None
        rec("T14 认知落库（INFERRED+KNOWN）", "两条 stored 且 epistemic 正确",
            f"INFERRED={ok1} KNOWN={ok2}", time.time() - t0, ok1 and ok2 and os.path.exists(COG_DB))

        # ---- T14b 查询认知 ----
        t0 = time.time()
        r3 = str(uuid.uuid4())
        c.pub("sys.query.cognition", {"req_id": r3, "q": {}})
        g3 = c.wait_reply(r3, 5)
        rows = (g3 or {}).get("results", [])
        rec("T14 认知查询", "≥2 条且字段含 confidence/evidence/epistemic",
            f"{len(rows)} 条", time.time() - t0,
            len(rows) >= 2 and all({"confidence", "evidence", "epistemic"} <= set(x) for x in rows))

        # ---- T16a INFERRED 当 KNOWN 被拒 ----
        t0 = time.time()
        r4 = str(uuid.uuid4())
        c.pub("sys.decision.request", {"req_id": r4, "cites": [id_inferred],
                                       "risk_class": "SOCIAL", "action": "advise"})
        g4 = c.wait_reply(r4, 5)
        rec("T16 INFERRED≠KNOWN 校验", "REJECT(INFERRED_AS_KNOWN)",
            f"{(g4 or {}).get('verdict')}", time.time() - t0,
            bool(g4 and g4.get("verdict") == "REJECT" and g4.get("reason") == "INFERRED_AS_KNOWN"))

        # ---- T16b KNOWN → ACCEPT ----
        t0 = time.time()
        r5 = str(uuid.uuid4())
        c.pub("sys.decision.request", {"req_id": r5, "cites": [id_known],
                                       "risk_class": "SOCIAL", "action": "advise"})
        g5 = c.wait_reply(r5, 5)
        rec("T16 KNOWN → ACCEPT", "ACCEPT", f"{(g5 or {}).get('verdict')}",
            time.time() - t0, bool(g5 and g5.get("verdict") == "ACCEPT"))

        # ---- T16c 金融高风险 → REQUIRE_CONFIRM ----
        t0 = time.time()
        r6 = str(uuid.uuid4())
        c.pub("sys.decision.request", {"req_id": r6, "cites": [id_known],
                                       "risk_class": "FINANCIAL", "action": "pay"})
        g6 = c.wait_reply(r6, 5)
        rec("T16 FINANCIAL 二次确认", "REQUIRE_CONFIRM", f"{(g6 or {}).get('verdict')}",
            time.time() - t0, bool(g6 and g6.get("verdict") == "REQUIRE_CONFIRM"))

        # ---- T16d SAFETY → ACCEPT ----
        t0 = time.time()
        r7 = str(uuid.uuid4())
        c.pub("sys.decision.request", {"req_id": r7, "cites": [id_known],
                                       "risk_class": "SAFETY", "action": "alert"})
        g7 = c.wait_reply(r7, 5)
        rec("T16 SAFETY → ACCEPT", "ACCEPT", f"{(g7 or {}).get('verdict')}",
            time.time() - t0, bool(g7 and g7.get("verdict") == "ACCEPT"))

        # ---- T15 租约超时回收 ----
        t0 = time.time()
        r8 = str(uuid.uuid4())
        c.pub("sys.lease.request", {"req_id": r8, "event_id": "evt-x", "budget_ms": 300})
        g8 = c.wait_reply(r8, 5)
        got_lease = bool(g8 and g8.get("lease_id"))
        expired_evt = c.wait_topic("evt.lease.expired", 3) if got_lease else None
        stats = {}
        if os.path.exists(LEASE_STATS):
            with open(LEASE_STATS, encoding="utf-8") as f:
                stats = json.load(f)
        ok = got_lease and expired_evt is not None and stats.get("expired", 0) >= 1
        rec("T15 租约超时回收", "300ms 租约不释放 → expired 事件 + 计数",
            f"lease={got_lease} expired_evt={expired_evt is not None} count={stats.get('expired')}",
            time.time() - t0, ok)

        c.close()
    finally:
        if aiosd:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(aiosd.pid)], capture_output=True)
        time.sleep(0.5)
        h = load_health()
        if h and h.get("bus", {}).get("pid"):
            subprocess.run(["taskkill", "/F", "/PID", str(h["bus"]["pid"])], capture_output=True)

    print("=" * 60)
    passed = sum(results)
    print(f"M2 验收结果: {passed}/{len(results)} 项通过")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
