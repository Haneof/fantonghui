# -*- coding: utf-8 -*-
"""金字塔重建 + 逐层下钻验证（v2：修正列索引与父子标签）"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
DB = "run/life_tree.db"

# 停栈 → DROP summary（raw_log 保留）→ 起栈
subprocess.run(["powershell", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -match 'aiosd|aios_busd|services' } | "
                "ForEach-Object { taskkill /T /F /PID $_.ProcessId } | Out-Null"],
               capture_output=True)
time.sleep(1.5)
conn = sqlite3.connect(DB)
conn.execute("DROP TABLE IF EXISTS summary")
conn.commit()
n_raw = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
conn.close()
print(f"summary 已重建（raw_log 保留 {n_raw} 条）")

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

c = socket.create_connection(("127.0.0.1", 7800), timeout=5)
c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
def send(o): c.sendall((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))
send({"t": "hello", "service": "pyramid-cli"})
time.sleep(0.3)
send({"t": "pub", "topic": "sys.cmd.rebuild_pyramid", "msg": {"req_id": "rb2"}})
print("金字塔重建中（分钟→小时→日→周‖月→季）...")
time.sleep(12)

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
print("\n=== 金字塔各层 ===")
levels = {}
for r in conn.execute("SELECT level, COUNT(*) FROM summary GROUP BY level ORDER BY 2 DESC"):
    levels[r[0]] = r[1]
    print(f"  {r[0]}: {r[1]} 份")
print(f"  RAW: {conn.execute('SELECT COUNT(*) FROM raw_log').fetchone()[0]} 条")

print("\n=== 下钻验证：月总结的输入=日总结（用户裁定核对）===")
m = conn.execute("SELECT id, period_key, content, children FROM summary WHERE level='MONTHLY' LIMIT 1").fetchone()
if m:
    kids = json.loads(m[3])
    kid_levels = [conn.execute("SELECT level FROM summary WHERE id=?", (k,)).fetchone()[0] for k in kids[:6]]
    print(f"  月[{m[1]}] 子节点层级: {kid_levels} （应全为 DAILY）")
    print(f"  月[{m[1]}] 内容: {m[2][:70]}…")
print("\n=== 下钻验证：周总结的输入=日总结 ===")
w = conn.execute("SELECT id, period_key, content, children FROM summary WHERE level='WEEKLY' LIMIT 1").fetchone()
if w:
    kids = json.loads(w[3])
    kid_levels = [conn.execute("SELECT level FROM summary WHERE id=?", (k,)).fetchone()[0] for k in kids[:6]]
    print(f"  周[{w[1]}] 子节点层级: {kid_levels} （应全为 DAILY）")

print("\n=== 全链路下钻：季→月→日→时→分→原始 ===")
q = conn.execute("SELECT id, period_key, content, children FROM summary WHERE level='QUARTERLY'").fetchone()
if q:
    print(f"  季[{q[1]}]: 子节点 {len(json.loads(q[3]))} 个月总结")
    mid = json.loads(q[3])[0]
    m = conn.execute("SELECT period_key, content, children FROM summary WHERE id=?", (mid,)).fetchone()
    print(f"    月[{m[0]}]: 子节点 {len(json.loads(m[2]))} 份日总结")
    did = json.loads(m[2])[0]
    d = conn.execute("SELECT period_key, content, children FROM summary WHERE id=?", (did,)).fetchone()
    print(f"      日[{d[0]}]: 子节点 {len(json.loads(d[2]))} 份小时总结")
    hid = json.loads(d[2])[0]
    h = conn.execute("SELECT period_key, content, children FROM summary WHERE id=?", (hid,)).fetchone()
    print(f"        时[{h[0]}]: 子节点 {len(json.loads(h[2]))} 份分钟总结")
    minid = json.loads(h[2])[0]
    mi = conn.execute("SELECT period_key, content, children FROM summary WHERE id=?", (minid,)).fetchone()
    print(f"          分[{mi[0]}]: 子节点 {len(json.loads(mi[2]))} 条原始事件")
    rid = json.loads(mi[2])[0]
    r = conn.execute("SELECT content FROM raw_log WHERE id=?", (rid,)).fetchone()
    print(f"            原始事件: {r[0][:56]}")
conn.close()
print("\n金字塔验证完成")
