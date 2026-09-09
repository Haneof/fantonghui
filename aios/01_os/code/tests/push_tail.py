# -*- coding: utf-8 -*-
"""重推缺失的尾部 990 条（幂等：INSERT OR REPLACE by id）"""
import json, os, socket, sqlite3, subprocess, sys, threading, time, uuid

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
DB = os.path.join(ROOT, "run", "life_tree.db")
data = json.load(open(r"simulator\scripts\life_90days.json", encoding="utf-8"))
tail = data[30027:31017]
tail_path = os.path.join(ROOT, "run", "tail_990.json")
with open(tail_path, "w", encoding="utf-8") as f:
    json.dump(tail, f, ensure_ascii=False)
print(f"尾部 {len(tail)} 条已写出")

def db_count():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
    conn.close()
    return n

before = db_count()
print("推送前:", before)

# 直连总线发布（不经 simd，控制最精确）
c = socket.create_connection(("127.0.0.1", 7800), timeout=5)
c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
def send(o): c.sendall((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))
send({"t": "hello", "service": "tail-push"})
time.sleep(0.3)
t0 = time.time()
for item in tail:
    ev = dict(item["event"])
    send({"t": "pub", "topic": item["topic"], "msg": ev})
print(f"31,017 中尾部 {len(tail)} 条已全部发送，等待消化...")

deadline = time.time() + 30
while time.time() < deadline:
    time.sleep(1)
    n = db_count()
    print(f"  {time.time()-t0:4.1f}s | 人生树 {n} 条")
    if n >= before + len(tail) - 2:
        break
after = db_count()
print(f"结果: {before} → {after}（+{after-before}）")
c.close()
