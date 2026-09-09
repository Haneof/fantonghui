# -*- coding: utf-8 -*-
"""AIOS 事件总线 broker（M1 · 队列化版本）
契约：tasks/contracts.md §2 §3
关键：每连接独立发送队列 + 写线程——慢消费者不再阻塞发布者（消除队头阻塞）
- TCP JSON Lines；hello/sub(通配#)/pub(不回环)/hb/bye/err
- 每 1.0s 落盘 run/bus_stats.json
"""
import argparse
import json
import os
import queue
import socket
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # code/
RUN_DIR = os.path.join(ROOT, "run")
CONFIG_PATH = os.path.join(ROOT, "aios_config.json")
MAX_FRAME = 256 * 1024


def load_config():
    cfg = {"bus_host": "127.0.0.1", "bus_port": 7800}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        cfg["bus_host"] = data.get("bus_host", cfg["bus_host"])
        cfg["bus_port"] = int(data.get("bus_port", cfg["bus_port"]))
    except Exception:
        pass
    return cfg


class Client:
    """一条已接入的连接：读线程由 Bus 管理，写线程独立跑发送队列。"""
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.name = None
        self.topics = []
        self.last_hb = None
        self.frames_in = 0
        self.alive = True
        self.out_q = queue.Queue()
        self.rfile = sock.makefile("r", encoding="utf-8", newline="\n")
        self.writer = threading.Thread(target=self._out_loop, daemon=True)
        self.writer.start()

    def enqueue(self, obj):
        if self.alive:
            try:
                self.out_q.put(obj)
            except Exception:
                pass

    def _out_loop(self):
        while True:
            obj = self.out_q.get()
            if obj is None:
                break
            try:
                line = json.dumps(obj, ensure_ascii=False) + "\n"
                self.sock.sendall(line.encode("utf-8"))
            except Exception:
                self.alive = False
                break

    def stop(self):
        self.alive = False
        try:
            self.out_q.put(None)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class Bus:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.lock = threading.RLock()
        self.clients = []
        self.stats_stop = threading.Event()
        self.server_sock = None

    @staticmethod
    def topic_match(subscribed, topic):
        if subscribed.endswith(".#"):
            return topic.startswith(subscribed[:-1])
        return subscribed == topic

    def broadcast(self, sender, frame):
        with self.lock:
            targets = [c for c in self.clients
                       if c.alive and c.name and c is not sender
                       and any(self.topic_match(t, frame["topic"]) for t in c.topics)]
        for c in targets:        # 只入队，写线程负责投递，不阻塞发布者
            c.enqueue(frame)

    def handle_line(self, client, line):
        client.frames_in += 1
        try:
            frame = json.loads(line)
        except Exception:
            client.enqueue({"t": "err", "code": "BAD_JSON", "text": "帧不是合法 JSON"})
            return
        t = frame.get("t")
        if t == "hello":
            name = str(frame.get("service", "")).strip()
            if not name:
                client.enqueue({"t": "err", "code": "BAD_NAME", "text": "hello 缺 service"})
                return
            client.name = name
            with self.lock:
                for c in self.clients:
                    if c is not client and c.name == name and c.alive:
                        c.stop()
            client.enqueue({"t": "welcome", "service": name})
        elif t == "sub":
            topics = frame.get("topics") or []
            with self.lock:
                client.topics = [str(x) for x in topics if isinstance(x, str)]
        elif t == "pub":
            topic = frame.get("topic", "")
            msg = frame.get("msg")
            if not topic or not isinstance(msg, dict):
                client.enqueue({"t": "err", "code": "BAD_PUB", "text": "pub 缺 topic 或 msg"})
                return
            if len(line) > MAX_FRAME:
                client.enqueue({"t": "err", "code": "TOO_BIG", "text": "帧超过 256KB"})
                return
            self.broadcast(client, {"t": "evt", "topic": topic,
                                    "from": client.name or "unknown", "msg": msg})
        elif t == "hb":
            client.last_hb = time.time()
        elif t == "bye":
            client.alive = False
        else:
            client.enqueue({"t": "err", "code": "UNKNOWN_T", "text": f"未知帧类型 {t}"})

    def serve_client(self, client):
        try:
            for line in client.rfile:
                line = line.strip()
                if not line:
                    continue
                if not client.alive:
                    break
                self.handle_line(client, line)
        except Exception:
            pass
        finally:
            client.stop()
            with self.lock:
                if client in self.clients:
                    self.clients.remove(client)

    def stats_loop(self):
        os.makedirs(RUN_DIR, exist_ok=True)
        path = os.path.join(RUN_DIR, "bus_stats.json")
        while not self.stats_stop.wait(1.0):
            with self.lock:
                services = {c.name: {"connected": bool(c.alive and c.name),
                                     "last_hb": c.last_hb,
                                     "frames_in": c.frames_in,
                                     "qsize": c.out_q.qsize()}
                            for c in self.clients if c.name}
            tmp = {"ts": time.time(), "services": services}
            try:
                with open(path + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(tmp, f, ensure_ascii=False)
                os.replace(path + ".tmp", path)
            except Exception:
                pass

    def serve_forever(self):
        os.makedirs(RUN_DIR, exist_ok=True)
        threading.Thread(target=self.stats_loop, daemon=True).start()
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(32)
        print(f"BUS LISTEN {self.host}:{self.port}", flush=True)
        try:
            while True:
                sock, addr = self.server_sock.accept()
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                client = Client(sock, addr)
                with self.lock:
                    self.clients.append(client)
                threading.Thread(target=self.serve_client, args=(client,),
                                 daemon=True).start()
        except KeyboardInterrupt:
            pass
        finally:
            self.stats_stop.set()
            with self.lock:
                for c in list(self.clients):
                    c.stop()
            try:
                self.server_sock.close()
            except Exception:
                pass
            print("BUS SHUTDOWN", flush=True)


if __name__ == "__main__":
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=cfg["bus_host"])
    ap.add_argument("--port", type=int, default=cfg["bus_port"])
    args = ap.parse_args()
    Bus(args.host, args.port).serve_forever()
