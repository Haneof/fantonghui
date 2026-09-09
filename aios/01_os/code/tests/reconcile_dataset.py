# -*- coding: utf-8 -*-
"""数据集对账：找出哪 1012 条没入库（尾部连续 = 排队被截断；散布 = 随机丢失）"""
import json, sqlite3

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
data = json.load(open(ROOT + r"\simulator\scripts\life_90days.json", encoding="utf-8"))
all_ids = [e["event"]["id"] for e in data]
all_by_id = {e["event"]["id"]: e["event"] for e in data}

conn = sqlite3.connect("file:" + ROOT + r"\run\life_tree.db?mode=ro", uri=True)
db_ids = set(r[0] for r in conn.execute("SELECT id FROM raw_log").fetchall())
conn.close()

missing = [i for i in all_ids if i not in db_ids]
print(f"数据集 {len(all_ids)} | 已入库 {len(db_ids & set(all_ids))} | 缺失 {len(missing)}")

# 缺失事件在原序列中的位置分布
idx_of = {e["event"]["id"]: i for i, e in enumerate(data)}
missing_idx = sorted(idx_of[i] for i in missing)
if missing_idx:
    print(f"缺失位置范围: {missing_idx[0]} ~ {missing_idx[-1]}")
    # 连续段检测
    runs = []
    start = prev = missing_idx[0]
    for x in missing_idx[1:]:
        if x == prev + 1:
            prev = x
        else:
            runs.append((start, prev)); start = prev = x
    runs.append((start, prev))
    print(f"连续段数量: {len(runs)}")
    for a, b in runs[:10]:
        print(f"  段 {a}~{b}（{b-a+1} 条）content 样例: {data[a]['event']['content'][:30]}")
else:
    print("无缺失")
