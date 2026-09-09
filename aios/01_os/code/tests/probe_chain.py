# -*- coding: utf-8 -*-
"""链路探针：evt.sim.probe → hublinkd → evt.stream → perceptiond → evt.normalized → memoryd 逐段检测"""
import json, socket, time, uuid, sqlite3

s1 = socket.create_connection(("127.0.0.1", 7800), timeout=5)
s1.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
buf1 = b""
def send1(o): s1.sendall((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))
def recv1(timeout):
    global buf1
    s1.settimeout(timeout)
    while b"\n" not in buf1:
        try:
            chunk = s1.recv(65536)
        except socket.timeout:
            return None
        if not chunk: return None
        buf1 += chunk
    line, buf1 = buf1.split(b"\n", 1)
    return line.decode("utf-8")

s2 = socket.create_connection(("127.0.0.1", 7800), timeout=5)
s2.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
buf2 = b""
def send2(o): s2.sendall((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))
def recv2(timeout):
    global buf2
    s2.settimeout(timeout)
    while b"\n" not in buf2:
        try:
            chunk = s2.recv(65536)
        except socket.timeout:
            return None
        if not chunk: return None
        buf2 += chunk
    line, buf2 = buf2.split(b"\n", 1)
    return line.decode("utf-8")

send1({"t": "hello", "service": "probe-a"})
send2({"t": "hello", "service": "probe-b"})
time.sleep(0.3)
send2({"t": "sub", "topics": ["evt.#"]})
time.sleep(0.3)
recv2(0.5)  # 清缓冲

pid = str(uuid.uuid4())
send1({"t": "pub", "topic": "evt.sim.probe", "msg": {"id": pid, "ts": time.time(),
      "source": "sim", "type": "probe", "content": "HUBLINKD-存活探针"}})

# 等 evt.stream（hublinkd 转发的证据）
got_stream = None
end = time.time() + 4
while time.time() < end:
    line = recv2(0.5)
    if not line: continue
    try:
        f = json.loads(line)
    except Exception:
        continue
    if f.get("t") == "evt" and f.get("topic") == "evt.stream" and \
       f.get("msg", {}).get("id") == pid:
        got_stream = f
        break

print("第一跳（simd→hublinkd→evt.stream）:", "存活 ✅" if got_stream else "死亡 ❌")

# 等 evt.normalized（perceptiond 转发的证据）
got_norm = None
end = time.time() + 4
while time.time() < end:
    line = recv2(0.5)
    if not line: continue
    try:
        f = json.loads(line)
    except Exception:
        continue
    if f.get("t") == "evt" and f.get("topic") == "evt.normalized" and \
       f.get("msg", {}).get("id") == pid:
        got_norm = f
        break
print("第二跳（perceptiond→evt.normalized）:", "存活 ✅" if got_norm else "死亡 ❌")

# 等入库（memoryd）
time.sleep(1.5)
conn = sqlite3.connect("file:run/life_tree.db?mode=ro", uri=True)
row = conn.execute("SELECT content FROM raw_log WHERE id=?", (pid,)).fetchone()
n = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
conn.close()
print("第三跳（memoryd 入库）:", ("存活 ✅ " + row[0]) if row else "死亡 ❌", "| 总数:", n)
s1.close(); s2.close()
