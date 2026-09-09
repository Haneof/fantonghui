# -*- coding: utf-8 -*-
"""M1.5 数据集压测最终报告"""
import sqlite3

conn = sqlite3.connect("file:run/life_tree.db?mode=ro", uri=True)
n = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
s = conn.execute("SELECT COUNT(*) FROM summary").fetchone()[0]
by = conn.execute("SELECT type, COUNT(*) FROM raw_log GROUP BY type ORDER BY 2 DESC").fetchall()
span = conn.execute("SELECT MIN(timestamp_s), MAX(timestamp_s) FROM raw_log").fetchone()
sample = conn.execute("SELECT content FROM raw_log WHERE type='payment' LIMIT 1").fetchone()
conn.close()
print("人生树最终入库:", n, "条")
print("小时摘要:", s, "份")
print("类型分布:", by)
print("时间跨度: %.1f 天" % ((span[1] - span[0]) / 86400))
print("抽查支付事件:", sample[0])
