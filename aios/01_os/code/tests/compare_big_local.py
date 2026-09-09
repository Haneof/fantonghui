# -*- coding: utf-8 -*-
"""大模型（我）vs 本地 1.5B · 同题对比（4 题样本）"""
import json
import os
import sqlite3
import time

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
truths = {x["qid"]: x for x in json.load(open(r"run\bench1k\questions.json", encoding="utf-8"))}
local_ans = {}
for line in open(r"run\bench1k\results.jsonl", encoding="utf-8"):
    try:
        r = json.loads(line)
        if r["condition"] == "local-n0":
            local_ans[r["qid"]] = (r["answer"][:70], r["score"])
    except Exception:
        pass

my_answers = {}

# T1a-000：07月楼下快餐是哪几天（可见记录 4 条）
my_answers["T1a-000"] = "07月10日、07月13日、07月16日、07月30日"

# T1b-000：2026-08-10 上午几点心率达到 87（检索工具拉全量晨间记录）
conn = sqlite3.connect("file:run/life_tree.db?mode=ro", uri=True)
t0 = time.mktime(time.strptime("2026-08-10 05:00:00", "%Y-%m-%d %H:%M:%S"))
t1 = time.mktime(time.strptime("2026-08-10 11:00:00", "%Y-%m-%d %H:%M:%S"))
rows = conn.execute(
    "SELECT timestamp_s, content FROM raw_log WHERE type='vital' AND content LIKE '心率%' "
    "AND timestamp_s >= ? AND timestamp_s <= ? ORDER BY timestamp_s", (t0, t1)).fetchall()
hits = []
for ts, c in rows:
    try:
        val = int(c.split("心率 ")[1].split("，")[0].split("（")[0])
    except Exception:
        continue
    if val == 87:
        hits.append((time.strftime("%H:%M", time.localtime(ts)), c))
my_answers["T1b-000"] = hits[0][0] + "（" + hits[0][1] + "）" if hits else "上午未见心率87"
t1b_truth_check = hits

# T2-000：W33 周与小陈互动次数（可见记录 5 条均含小陈）
my_answers["T2-000"] = "5"

# T3-000：6 月消费总额与笔数（检索工具拉全量 6 月支付）
t0 = time.mktime(time.strptime("2026-06-01 00:00:00", "%Y-%m-%d %H:%M:%S"))
t1 = time.mktime(time.strptime("2026-07-01 00:00:00", "%Y-%m-%d %H:%M:%S"))
rows = conn.execute(
    "SELECT content FROM raw_log WHERE type='payment' AND timestamp_s >= ? AND timestamp_s < ?",
    (t0, t1)).fetchall()
import re
total = sum(int(re.search(r"¥(\d+)", r[0]).group(1)) for r in rows if re.search(r"¥(\d+)", r[0]))
my_answers["T3-000"] = f"共{total}元，{len(rows)}笔"
conn.close()

print("=== 大模型（指挥官/DeepSeek 同级）vs 本地 1.5B · 4 题样本 ===\n")
for qid in ["T1a-000", "T1b-000", "T2-000", "T3-000"]:
    truth = truths[qid]["truth"]
    la, lsc = local_ans.get(qid, ("（无记录）", -1))
    print(f"--- {qid} ---")
    print(f"  标准答案 : {json.dumps(truth, ensure_ascii=False)[:90]}")
    print(f"  大模型(我): {my_answers[qid][:90]}")
    print(f"  本地1.5B : {la} | 判分 {lsc}")
    print()

# 1.5B 千题总成绩引用
allsc = []
by_type = {}
for line in open(r"run\bench1k\results.jsonl", encoding="utf-8"):
    try:
        r = json.loads(line)
        if r["condition"] == "local-n0":
            allsc.append(r["score"])
            by_type.setdefault(r["type"], []).append(r["score"])
    except Exception:
        pass
print("本地 1.5B 千题总览:", f"{sum(allsc)/len(allsc)*100:.1f}%（{len(allsc)} 题）")
for t in sorted(by_type):
    sc = by_type[t]
    print(f"  {t}: {sum(sc)/len(sc)*100:.1f}%（{len(sc)} 题）")
