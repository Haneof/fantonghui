# -*- coding: utf-8 -*-
"""M0 验收裁判（T06）—— 契约 §8 A1-A5
用法：python tests/test_m0.py
全绿 exit 0；任何一项失败 exit 1。finally 清理全部子进程。
"""
import json
import os
import socket
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # code/
RUN_DIR = os.path.join(ROOT, "run")
HEALTH = os.path.join(RUN_DIR, "health.json")
SERVICES_EXPECTED = ["hublinkd", "stated", "safetyd", "privacyd", "modemgrd",
                     "attentiond", "perceptiond", "entityd", "memoryd",
                     "cognitiond", "decisiond", "abilityd", "interactd",
                     "evolutiond", "modelrouterd"]

results = []   # (名称, 期望, 实际, 耗时, ok)


def record(name, expect, actual, cost, ok):
    results.append((name, expect, actual, cost, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}（{cost:.1f}s）期望: {expect} | 实际: {actual}", flush=True)


def load_health():
    try:
        with open(HEALTH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class BusClient:
    """以服务身份裸连总线（契约 §2）。"""
    def __init__(self, name, port=7800, host="127.0.0.1"):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.rfile = self.sock.makefile("r", encoding="utf-8", newline="\n")
        self._send({"t": "hello", "service": name})
        # 吃掉 welcome
        self.rfile.readline()

    def _send(self, obj):
        self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def pub(self, topic, msg):
        self._send({"t": "pub", "topic": topic, "msg": msg})

    def sub(self, topics):
        self._send({"t": "sub", "topics": topics})

    def wait_evt(self, topic, timeout):
        end = time.time() + timeout
        while time.time() < end:
            self.sock.settimeout(max(0.1, end - time.time()))
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
                return frame
        return None

    def close(self):
        try:
            self._send({"t": "bye"})
            self.sock.close()
        except Exception:
            pass


def main():
    print("=" * 60)
    print("AIOS M0 验收开始（A1-A5）")
    print("=" * 60)
    aiosd = None
    try:
        # 起栈
        t0 = time.time()
        aiosd = subprocess.Popen([sys.executable, "aiosd/aiosd.py"], cwd=ROOT)
        print(f"aiosd 已拉起 (pid={aiosd.pid})")

        # ---- A3 心跳全绿 ----
        t0 = time.time()
        ok, actual = False, "20s 内 health.json 未达全绿"
        deadline = time.time() + 20
        while time.time() < deadline:
            h = load_health()
            if h and h.get("bus", {}).get("state") == "up":
                svcs = h.get("services", {})
                ups = [n for n in SERVICES_EXPECTED
                       if svcs.get(n, {}).get("state") == "up"]
                fresh = all(
                    svcs.get(n, {}).get("last_hb") and
                    time.time() - svcs[n].get("last_hb", 0) < 3
                    for n in ups) if ups else False
                if len(ups) == len(SERVICES_EXPECTED) and fresh:
                    ok = True
                    actual = f"{len(ups)}/15 服务 up 且心跳新鲜"
                    break
            time.sleep(0.3)
        record("A3 心跳全绿", "bus+15 服务 up 且 last_hb<3s", actual, time.time() - t0, ok)
        if not ok:
            h = load_health()
            print("health.json 快照:", json.dumps(h, ensure_ascii=False, indent=1)[:2000])

        # ---- A1 事件互通（回声链路）----
        t0 = time.time()
        ok, actual = False, "未收到 evt.hub.echo"
        try:
            cli = BusClient("testdriver")
            cli.sub(["evt.#"])
            time.sleep(0.2)
            cli.pub("sys.test.ping", {"id": str(uuid.uuid4()), "ts": time.time(),
                                      "source": "testdriver", "type": "ping",
                                      "content": "m0-echo-test"})
            frame = cli.wait_evt("evt.hub.echo", 5)
            if frame:
                ok = True
                actual = f"收到回声 content={frame['msg'].get('content', '')}"
            cli.close()
        except Exception as e:
            actual = f"异常: {e}"
        record("A1 事件互通", "5s 内收到 evt.hub.echo", actual, time.time() - t0, ok)

        # ---- A2 击杀复活 ----
        t0 = time.time()
        ok, actual = False, "health.json 不可读"
        h = load_health()
        victim = None
        if h:
            cands = [n for n in SERVICES_EXPECTED
                     if h.get("services", {}).get(n, {}).get("pid")]
            # 避免杀掉回声链路的两位，保证后续步骤稳定
            victim = next((n for n in cands if n not in ("hublinkd", "perceptiond")), None)
        if victim:
            old_pid = h["services"][victim]["pid"]
            subprocess.run(["taskkill", "/F", "/PID", str(old_pid)],
                           capture_output=True)
            deadline = time.time() + 1.5
            while time.time() < deadline:
                h2 = load_health()
                if h2:
                    info = h2.get("services", {}).get(victim, {})
                    if info.get("state") == "up" and info.get("pid") not in (None, old_pid):
                        ok = True
                        actual = f"{victim} 已复活 pid {old_pid}->{info['pid']}"
                        break
                time.sleep(0.1)
            if not ok:
                actual = f"{victim} 1.5s 内未复活"
        else:
            actual = "无可选目标服务"
        record("A2 击杀复活", "taskkill /F 后 ≤1.5s 重启", actual, time.time() - t0, ok)

        # ---- A5 日志齐全 ----
        t0 = time.time()
        log_dir = os.path.join(RUN_DIR, "logs")
        count = 0
        if os.path.isdir(log_dir):
            count = sum(1 for f in os.listdir(log_dir)
                        if f.endswith(".log") and
                        os.path.getsize(os.path.join(log_dir, f)) > 0)
        ok = count >= 15
        record("A5 日志齐全", "run/logs 非空日志 ≥15", f"{count} 个", time.time() - t0, ok)

        # ---- A4 契约一致性（代码审查项，这里做静态扫描）----
        t0 = time.time()
        bad = []
        svc_dir = os.path.join(ROOT, "services")
        for fn in os.listdir(svc_dir):
            if fn.endswith(".py"):
                with open(os.path.join(svc_dir, fn), encoding="utf-8") as f:
                    src = f.read()
                if "socket.create_connection" in src or "socket.socket(" in src:
                    bad.append(fn)
        ok = not bad
        record("A4 契约一致性", "服务无自行连总线代码", f"违规: {bad or '无'}",
               time.time() - t0, ok)

    finally:
        # ---- 清理 ----
        if aiosd:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(aiosd.pid)],
                           capture_output=True)
        # 兜底清理残留 python 进程（bus 可能不是 aiosd 子进程树内）
        time.sleep(0.5)
        h = load_health()
        if h and h.get("bus", {}).get("pid"):
            subprocess.run(["taskkill", "/F", "/PID", str(h["bus"]["pid"])],
                           capture_output=True)

    print("=" * 60)
    passed = sum(1 for r in results if r[4])
    print(f"M0 验收结果: {passed}/{len(results)} 项通过")
    for name, _, actual, cost, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name} ({cost:.1f}s) - {actual}")
    print("=" * 60)
    sys.exit(0 if passed == len(results) and len(results) == 5 else 1)


if __name__ == "__main__":
    main()
