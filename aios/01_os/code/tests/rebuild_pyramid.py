# -*- coding: utf-8 -*-
"""清理测试污染 + 重建递归摘要金字塔 + 链路完整性验证"""
import json
import os
import sqlite3
import socket
import time
import uuid

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
DB = os.path.join(ROOT, "run", "life_tree.db")

# ---- 1. 清理测试污染（保留 90 天数据集与冒烟数据）----
conn = sqlite3.connect(DB)
n0 = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
conn.execute("DELETE FROM raw_log WHERE type='stress' OR type='probe'")
conn.execute("DELETE FROM summary")
conn.commit()
n1 = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
print(f"清理: {n0} → {n1}（移除测试污染 {n0-n1} 条，保留 90 天数据集）")
conn.close()

# 清空入口队列（其中的 stress 测试行不再需要）
q = sqlite3.connect(os.path.join(ROOT, "run", "entry_queue.db"))
q.execute("DELETE FROM entry_queue")
q.commit()
q.close()
print("入口队列已清空")

# ---- 2. 触发金字塔重建 ----
s = socket.create_connection(("127.0.0.1", 7800), timeout=5)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
def send(o): s.sendall((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))
send({"t": "hello", "service": "pyramid-cli"})
time.sleep(0.3)
send({"t": "pub", "topic": "sys.cmd.rebuild_pyramid", "msg": {"req_id": str(uuid.uuid4())}})
print("金字塔重建已触发（分钟→小时→日→周→月→季 逐层）")
time.sleep(12)

# ---- 3. 链路验证 ----
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
print("\n=== 金字塔各层 ===")
levels = {}
for r in conn.execute("SELECT level, COUNT(*) FROM summary GROUP BY level"):
    levels[r[0]] = r[1]
    print(f"  {r[0]}: {r[1]} 份")
raw = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
print(f"  RAW(原始事件): {raw} 条")

# 链路完整性：从 QUARTERLY 逐层下钻
print("\n=== 链路下钻验证（季→月→周→日→小时→分钟→原始）===")
q = conn.execute("SELECT id, period_key, content, children FROM summary WHERE level='QUARTERLY'").fetchone()
if q:
    qid, qkey, qcontent, qchildren = q
    kids = json.loads(qchildren)
    print(f"  季度[{qkey}]: {qcontent[:60]}... | 子节点 {len(kids)} 个月总结")
    for mid in kids[:3]:
        m = conn.execute("SELECT period_key, content, children FROM summary WHERE id=?", (mid,)).fetchone()
        if m:
            mkids = json.loads(m[2])
            print(f"    月[{m[0]}]: {m[1][:50]}... | 子节点 {len(mkids)} 份日总结")
    # 抽一条日总结下钻两层
    d = conn.execute("SELECT id, period_key, content, children FROM summary WHERE level='DAILY' LIMIT 1").fetchone()
    if d:
        dkids = json.loads(d[2])
        print(f"    日[{d[1]}]: {d[2][:50]}... | 子节点 {len(dkids)} 份小时总结")
        if dkids:
            h = conn.execute("SELECT id, period_key, content, children FROM summary WHERE id=?", (dkids[0],)).fetchone()
            if h:
                hkids = json.loads(h[2])
                print(f"      小时[{h[1]}]: {h[2][:50]}... | 子节点 {len(hkids)} 份分钟总结")
                if hkids:
                    mi = conn.execute("SELECT id, period_key, content, children FROM summary WHERE id=?", (hkids[0],)).fetchone()
                    if mi:
                        mikids = json.loads(mi[2])
                        print(f"        分钟[{mi[1]}]: {mi[2][:60]}... | 子节点 {len(mikids)} 条原始事件")
                        raw_sample = conn.execute("SELECT content FROM raw_log WHERE id=?", (mikids[0],)).fetchone()
                        if raw_sample:
                            print(f"          原始事件: {raw_sample[0][:50]}")
conn.close()
print("\n金字塔验证完成")
