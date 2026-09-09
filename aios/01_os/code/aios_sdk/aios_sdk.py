# -*- coding: utf-8 -*-
"""AIOS 服务运行时 SDK（M0 · T02）
契约：tasks/contracts.md §4
用法：
    svc = AIOSService("perceptiond", subscribe=["evt.#"])
    svc.on_event = lambda topic, frm, msg: svc.log(f"收到 {topic}")
    svc.log("服务启动")
    svc.run()
心跳由内置线程自动发送；连接失败重试 3 次后 exit(1)，交给 aiosd 重启。
"""
import json
import os
import socket
import threading
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # code/
CONFIG_PATH = os.path.join(ROOT, "aios_config.json")
DEFAULTS = {"bus_host": "127.0.0.1", "bus_port": 7800, "hb_interval_s": 1.0}


def _load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for k in DEFAULTS:
            if k in data:
                cfg[k] = data[k]
    except Exception:
        pass
    return cfg


class AIOSService:
    def __init__(self, name, subscribe=None, on_event=None):
        self.name = name
        self.subscribe = list(subscribe or [])
        self.on_event = on_event          # 运行期可替换（先建实例后挂回调）
        cfg = _load_config()
        self.host = cfg["bus_host"]
        self.port = int(cfg["bus_port"])
        self.hb_interval = float(cfg["hb_interval_s"])
        self.sock = None
        self.rfile = None
        self.connected = False
        self.send_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self._stop = threading.Event()

    # ---------- 基础 ----------
    def _send(self, obj):
        if not self.connected:
            return False
        try:
            with self.send_lock:
                self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            return True
        except Exception:
            self.connected = False
            return False

    def log(self, text):
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {text}"
        try:
            with self.log_lock:
                if getattr(self, "_log_fh", None) is None:
                    path = os.path.join(ROOT, "run", "logs", f"{self.name}.log")
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    self._log_fh = open(path, "a", encoding="utf-8")
                self._log_fh.write(line + "\n")
                self._log_fh.flush()
        except Exception:
            pass
        try:
            print(line, flush=True)   # GBK 控制台下可能编码失败，不能拖垮服务
        except Exception:
            pass

    def publish(self, topic, msg):
        ok = self._send({"t": "pub", "topic": topic, "msg": msg})
        if not ok:
            self.log(f"[丢弃] 总线未连接，publish {topic}")
        return ok
    # ---------- 心跳 ----------
    def _hb_loop(self):
        while not self._stop.wait(self.hb_interval):
            if self.connected:
                self._send({"t": "hb", "pid": os.getpid(), "ts": time.time()})

    # ---------- 收帧 ----------
    def _read_loop(self):
        for line in self.rfile:
            line = line.strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except Exception:
                continue
            if frame.get("t") == "evt":
                try:
                    if self.on_event:
                        self.on_event(frame.get("topic", ""),
                                      frame.get("from", "unknown"),
                                      frame.get("msg", {}))
                except Exception as e:
                    self.log(f"[异常] on_event 回调出错: {e}")
            elif frame.get("t") == "bye":
                return
        # 总线侧关闭 → 正常返回，触发重试

    # ---------- 连接与主循环 ----------
    def _connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # 关 Nagle
        self.sock.settimeout(None)
        self.rfile = self.sock.makefile("r", encoding="utf-8", newline="\n")
        self.connected = True
        self._send({"t": "hello", "service": self.name})
        if self.subscribe:
            self._send({"t": "sub", "topics": self.subscribe})

    def close(self):
        self._stop.set()
        if self.connected:
            self._send({"t": "bye"})
        self.connected = False
        try:
            if getattr(self, "_log_fh", None):
                self._log_fh.close()
                self._log_fh = None
        except Exception:
            pass
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    def run(self):
        self._stop.clear()
        threading.Thread(target=self._hb_loop, daemon=True).start()
        attempts = 0
        while attempts < 3 and not self._stop.is_set():
            try:
                self._connect()
                attempts = 0
                self._read_loop()          # 正常bye/总线关闭都会返回
                if self._stop.is_set():
                    return
                self.connected = False
            except Exception as e:
                self.connected = False
                self.log(f"[连接失败] {e}")
            attempts += 1
            if attempts < 3:
                time.sleep(0.3)
        self.log("[退出] 总线连接持续失败，exit(1) 交由 aiosd 重启")
        self.close()
        os._exit(1)
