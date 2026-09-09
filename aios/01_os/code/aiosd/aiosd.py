# -*- coding: utf-8 -*-
"""AIOS aiosd 总管家（M0 · T03）
契约：tasks/contracts.md §5 §6 §7
- 冻结顺序拉起 bus + 15 服务；看门狗 0.2s 扫描；被杀服务立即复活
- health.json 每 0.5s 落盘（合并 bus_stats.json 的 last_hb）
- Ctrl+C 逆序停止全部子进程
"""
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # code/
RUN_DIR = os.path.join(ROOT, "run")
LOG_DIR = os.path.join(RUN_DIR, "logs")
CONFIG_PATH = os.path.join(ROOT, "aios_config.json")
SERVICES_PATH = os.path.join(ROOT, "services.json")


def log(text):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {text}"
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "aiosd.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    cfg = load_json(CONFIG_PATH, {
        "scan_interval_s": 0.2, "restart_min_interval_s": 0.5,
        "max_restarts_per_min": 10})
    manifest = load_json(SERVICES_PATH, {"bus": {"script": "bus/aios_busd.py"},
                                         "services": []})
    os.makedirs(LOG_DIR, exist_ok=True)

    procs = {}          # name -> dict(proc, script, always_on, order, restarts, last_spawn, state, spawn_ts)
    order = []
    stop = threading.Event()

    def spawn(name, script):
        path = os.path.join(ROOT, script)
        if not os.path.exists(path):
            return None
        # stdout/stderr → DEVNULL：服务日志以 run/logs 文件为准，避免管道 IO 成为吞吐瓶颈
        # PYTHONUTF8=1：强制 UTF-8 模式，杜绝 GBK 控制台编码崩溃（如内容含 ¥ 字符）
        env = dict(os.environ, PYTHONUTF8="1")
        p = subprocess.Popen([sys.executable, script], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        info = procs.setdefault(name, {"restarts": 0, "state": "up",
                                       "spawn_ts": deque(maxlen=64)})
        info.update(proc=p, pid=p.pid, script=script,
                    last_spawn=time.time(), state="up")
        info["spawn_ts"].append(time.time())
        log(f"拉起 {name} (pid={p.pid})")
        return p

    def reap():
        """UNSTABLE 打标：滑动 60s 窗口内重启次数超限。"""
        now = time.time()
        for name, info in procs.items():
            recent = [t for t in info.get("spawn_ts", deque()) if now - t < 60]
            info["spawn_ts"] = deque(recent, maxlen=64)
            if len(recent) > cfg.get("max_restarts_per_min", 10):
                if info["state"] != "unstable":
                    log(f"[警告] {name} 重启过频，标记 UNSTABLE")
                info["state"] = "unstable"
            elif info["state"] == "unstable":
                info["state"] = "up"

    # 1) 总线
    bus_script = manifest.get("bus", {}).get("script", "bus/aios_busd.py")
    bus_proc = spawn("bus", bus_script)
    time.sleep(0.5)

    # 2) 服务（冻结顺序）
    for svc in sorted(manifest.get("services", []), key=lambda s: s.get("order", 99)):
        spawn(svc["name"], svc["script"])

    # 3) 监控循环
    def monitor():
        while not stop.wait(cfg.get("scan_interval_s", 0.2)):
            reap()
            for name, info in list(procs.items()):
                p = info.get("proc")
                if p is None:
                    continue
                code = p.poll()
                if code is not None:
                    log(f"[看门狗] {name} 退出(code={code})，立即重启")
                    spawn(name, info["script"])

    def health():
        while not stop.wait(0.5):
            stats = load_json(os.path.join(RUN_DIR, "bus_stats.json"), {})
            svc_stats = stats.get("services", {})
            out = {"ts": time.time(),
                   "bus": {"pid": bus_proc.pid if bus_proc else None,
                           "state": "up" if (bus_proc and bus_proc.poll() is None) else "down"},
                   "services": {}}
            for name in [s["name"] for s in manifest.get("services", [])]:
                info = procs.get(name, {})
                p = info.get("proc")
                st = info.get("state", "down")
                if p is not None and p.poll() is None:
                    st = "unstable" if st == "unstable" else "up"
                else:
                    st = "down" if st != "unstable" else "unstable"
                out["services"][name] = {
                    "pid": p.pid if p else None, "state": st,
                    "restarts": info.get("restarts", 0),
                    "last_hb": svc_stats.get(name, {}).get("last_hb")}
            try:
                tmp = os.path.join(RUN_DIR, "health.json.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False)
                os.replace(tmp, os.path.join(RUN_DIR, "health.json"))
            except Exception:
                pass

    threading.Thread(target=monitor, daemon=True).start()
    threading.Thread(target=health, daemon=True).start()
    log(f"aiosd 启动完成：bus + {len(manifest.get('services', []))} 服务受管")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("[退出] 收到停止信号，逆序停止全部子进程")
        stop.set()
        for name in reversed([s["name"] for s in manifest.get("services", [])]):
            info = procs.get(name, {})
            p = info.get("proc")
            if p and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        if bus_proc and bus_proc.poll() is None:
            bus_proc.terminate()
        log("[退出] 完成")


if __name__ == "__main__":
    main()
