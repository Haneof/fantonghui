# -*- coding: utf-8 -*-
"""summary 表重建（修复 schema）+ 金字塔重建 + 完整验证"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)

# 1) 停栈
subprocess.run(["powershell", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -match 'aiosd|aios_busd|services' } | "
                "ForEach-Object { taskkill /T /F /PID $_.ProcessId } | Out-Null"],
               capture_output=True)
time.sleep(1.5)

# 2) 修复 summary 表：DROP（raw_log 保留！）
conn = sqlite3.connect("run/life_tree.db")
conn.execute("DROP TABLE IF EXISTS summary")
conn.commit()
n_raw = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
conn.close()
print(f"旧 summary 表已删除（raw_log 保留 {n_raw} 条）")

# 3) 起栈（新 memoryd 建新表）
aiosd = subprocess.Popen([sys.executable, "aiosd/aiosd.py"], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=dict(os.environ, PYTHONUTF8="1"))
deadline = time.time() + 20
ready = False
while time.time() < deadline:
    try:
        h = json.load(open("run/health.json", encoding="utf-8"))
        if h["bus"]["state"] == "up" and all(v["state"] == "up" for v in h["services"].values()):
            ready = True
            break
    except Exception:
        pass
    time.sleep(0.3)
print(f"全栈就绪: {ready}")

# 4) 触发金字塔重建
c = socket.create_connection(("127.0.0.1", 7800), timeout=5)
c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
def send(o): c.sendall((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))
send({"t": "hello", "service": "pyramid-cli"})
time.sleep(0.3)
print("金字塔重建中（分钟→小时→日→周→月→季）...")
send({"t": "pub", "topic": "sys.cmd.rebuild_pyramid", "msg": {"req_id": "rb1"}})
time.sleep(10)

# 5) 验证
conn = sqlite3.connect(f"file:{DB}?mode=ro".replace("{DB}", "run/life_tree.db"), uri=True) if False else sqlite3.connect("file:run/life_tree.db?mode=ro", uri=True)
print("\n=== 金字塔各层 ===")
levels = {}
for r in conn.execute("SELECT level, COUNT(*) FROM summary GROUP BY level ORDER BY 2 DESC"):
    levels[r[0]] = r[1]
    print(f"  {r[0]}: {r[1]} 份")
raw = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
print(f"  RAW: {raw} 条")

print("\n=== 链路下钻（季→月→周→日→时→分→原始）===")
q = conn.execute("SELECT id, period_key, content, children FROM summary WHERE level='QUARTERLY'").fetchone()
if q:
    print(f"  季[{q[1]}]: {q[2][:56]}… | 子节点 {len(json.loads(q[3]))} 个月总结")
    for mid in json.loads(q[3])[:2]:
        m = conn.execute("SELECT period_key, content, children FROM summary WHERE id=?", (mid,)).fetchone()
        if m:
            print(f"    月[{m[0]}]: {m[1][:48]}… | 子节点 {len(json.loads(m[2]))} 份日总结")
d = conn.execute("SELECT id, period_key, content, children FROM summary WHERE level='DAILY' LIMIT 1").fetchone()
if d:
    print(f"  日[{d[1]}] 样例: {d[2][:56]}… | 子节点 {len(json.loads(d[3]))} 份小时总结")
    h = conn.execute("SELECT id, period_key, content, children FROM summary WHERE id=?",
                     (json.loads(d[3])[0],)).fetchone()
    if h:
        hk = json.loads(h[2])
        print(f"    时[{h[1]}] 样例: {h[2][:56]}… | 子节点 {len(hk)} 份分钟总结")
        mi = conn.execute("SELECT id, period_key, content, children FROM summary WHERE id=?", (hk[0],)).fetchone()
        if mi:
            mk = json.loads(mi[2])
            print(f"      分[{mi[1]}]: {mi[2][:60]}… | 子节点 {len(mk)} 条原始事件")
            r0 = conn.execute("SELECT content FROM raw_log WHERE id=?", (mk[0],)).fetchone()
            if r0:
                print(f"        原始: {r0[0][:56]}")
conn.close()
print("\n金字塔重建验证完成")
