# -*- coding: utf-8 -*-
"""M3 验收裁判（T17-T19）—— 契约 tasks/contracts_m3.md 门禁
用法：python tests/test_m3.py
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
GROWTH_DB = os.path.join(RUN_DIR, "growth_tree.db")
DEGRADE = os.path.join(RUN_DIR, "model_degrade.json")
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
        self._recv_line(5)

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
    print("AIOS M3 验收开始（T17-T19）")
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

        # ---- T17 五级介入通道 ----
        t0 = time.time()
        def channel_for(risk_class, priority=None):
            rid = str(uuid.uuid4())
            c.pub("sys.interact.request", {"req_id": rid, "risk_class": risk_class, "priority": priority})
            g = c.wait_reply(rid, 5)
            return (g or {}).get("channel")
        ch_social = channel_for("SOCIAL")
        ch_social_high = channel_for("SOCIAL", "high")
        ch_safety = channel_for("SAFETY")
        ch_fin = channel_for("FINANCIAL")
        ok = (ch_social == "VISUAL" and ch_social_high == "BONE_CONDUCTION"
              and ch_safety == "HAPTIC" and ch_fin == "HAPTIC")
        rec("T17 五级介入通道", "SOCIAL→VISUAL / SOCIAL+high→BONE / SAFETY→HAPTIC / FIN→HAPTIC",
            f"{ch_social}/{ch_social_high}/{ch_safety}/{ch_fin}", time.time() - t0, ok)

        # ---- T18 Intervention Regret 对账闭环 ----
        t0 = time.time()
        c.pub("sys.interact.request", {"req_id": str(uuid.uuid4()), "risk_class": "SOCIAL", "priority": None})
        time.sleep(0.2)
        int_evt = c.wait_topic("evt.intervention", 3)
        iid = (int_evt or {}).get("intervention_id")
        ok_int = bool(iid)
        # rejected → SOCIAL 阈值上调
        rid = str(uuid.uuid4())
        c.pub("sys.interact.feedback", {"req_id": rid, "intervention_id": iid, "feedback": "rejected"})
        g = c.wait_reply(rid, 5)
        th_after_reject = (g or {}).get("threshold")
        # accepted → 阈值下调（先用一次 rejected 把阈值抬高，再 accepted 验证方向）
        rid2 = str(uuid.uuid4())
        c.pub("sys.interact.feedback", {"req_id": rid2, "intervention_id": iid, "feedback": "accepted"})
        g2 = c.wait_reply(rid2, 5)
        th_after_accept = (g2 or {}).get("threshold")
        ok_dir = (th_after_reject is not None and th_after_accept is not None
                  and th_after_reject > th_after_accept)
        rec("T18a 反馈驱动阈值", "rejected 上调 > accepted 下调",
            f"{th_after_reject} > {th_after_accept}", time.time() - t0,
            ok_int and ok_dir)

        t0 = time.time()
        rid3 = str(uuid.uuid4())
        c.pub("sys.evolve.rollback", {"req_id": rid3, "strategy_key": "SOCIAL"})
        g3 = c.wait_reply(rid3, 5)
        rb = bool(g3 and g3.get("rolled_back"))
        db_ok = os.path.exists(GROWTH_DB)
        conn = None
        sv_ok = False
        if db_ok:
            conn = sqlite3.connect(f"file:{GROWTH_DB}?mode=ro", uri=True)
            sv_ok = conn.execute("SELECT COUNT(*) FROM strategy_versions").fetchone()[0] >= 1
            conn.close()
        rec("T18b 回退 + 成长树落库", "rollback 成功 + strategy_versions≥1",
            f"rollback={rb} db={db_ok} versions={sv_ok}", time.time() - t0, rb and db_ok and sv_ok)

        # ---- T19 模型路由 + 降级 ----
        t0 = time.time()
        def model_call(task_type):
            rid = str(uuid.uuid4())
            c.pub("sys.model.request", {"req_id": rid, "task_type": task_type, "payload": "x"})
            g = c.wait_reply(rid, 5)
            return (g or {}).get("routed")
        r_simple = model_call("simple_judgment")
        r_complex = model_call("complex_reason")
        ok_route = (r_simple == "local_stub" and r_complex == "cloud_mock")
        # 断网降级
        rid4 = str(uuid.uuid4())
        c.pub("sys.model.set_offline", {"offline": True})
        time.sleep(0.2)
        r_complex_off = model_call("complex_reason")
        deg_ok = False
        if os.path.exists(DEGRADE):
            with open(DEGRADE, encoding="utf-8") as f:
                deg_ok = len(json.load(f)) >= 1
        # 恢复在线
        c.pub("sys.model.set_offline", {"offline": False})
        ok_degrade = (r_complex_off == "degraded_queued" and deg_ok)
        rec("T19 路由+降级", "simple→local / complex→cloud / 离线→degraded_queued+队列",
            f"{r_simple}/{r_complex}/{r_complex_off}/queue={deg_ok}",
            time.time() - t0, ok_route and ok_degrade)

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
    print(f"M3 验收结果: {passed}/{len(results)} 项通过")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
