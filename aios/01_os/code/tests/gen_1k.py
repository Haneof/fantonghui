# -*- coding: utf-8 -*-
"""千题基准 · 题库生成器 v2（适配加厚数据集：消息 516 / 支付 232 / 承诺实例）"""
import json
import os
import random
import sqlite3
import time
from collections import defaultdict

random.seed(20260911)
ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
conn = sqlite3.connect("file:run/life_tree.db?mode=ro", uri=True)
PEOPLE = ["小王", "张总", "李经理", "小雅", "小陈"]
Q = []

def add(qid, typ, q, ctx, truth, check):
    Q.append({"qid": qid, "type": typ, "q": q, "ctx": ctx, "truth": truth, "check": check})

def fmt(ts):
    return time.strftime("%m-%d %H:%M", time.localtime(ts))

def day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))

def mon(ts):
    return time.strftime("%Y%m", time.localtime(ts))

def week(ts):
    return time.strftime("%G-W%V", time.localtime(ts))

# ---------- T1a 哪一天吃了/打了X（按商户×月，125）----------
pays = conn.execute("SELECT timestamp_s, content FROM raw_log WHERE type='payment' ORDER BY timestamp_s").fetchall()
vendor_months = defaultdict(list)
for ts, content in pays:
    name = content.split("¥")[0].strip()
    vendor_months[(name, mon(ts))].append((ts, content))
combos = [(k, v) for k, v in vendor_months.items() if len(v) >= 2]
random.shuffle(combos)
n = 0
for (name, month), rows in combos:
    if n >= 125:
        break
    ctx = [f"{fmt(ts)} {content}" for ts, content in rows]
    dates = sorted({time.strftime("%m月%d日", time.localtime(ts)) for ts, _ in rows})
    add(f"T1a-{n:03d}", "T1a", f"{month[4:6]}月林川用过「{name}」吗？是哪几天？",
        ctx, {"dates": dates}, "dates")
    n += 1

# ---------- T1b 某日晨间几点心率到X（125）----------
vitals = conn.execute("SELECT timestamp_s, content FROM raw_log WHERE type='vital' AND content LIKE '心率%' ORDER BY timestamp_s").fetchall()
by_day = defaultdict(list)
for ts, content in vitals:
    by_day[day(ts)].append((ts, content))
days = [d for d in sorted(by_day) if len([1 for ts, _ in by_day[d] if 5 <= time.localtime(ts).tm_hour <= 11]) >= 6]
random.shuffle(days)
n = 0
for d in days:
    if n >= 125:
        break
    morning_raw = [(ts, content) for ts, content in by_day[d] if 5 <= time.localtime(ts).tm_hour <= 11]
    morning = [f"{time.strftime('%H:%M', time.localtime(ts))} {content}" for ts, content in morning_raw]
    target_ts, target_content = random.choice(morning_raw[:len(morning_raw) // 2])
    hr_val = target_content.split("心率 ")[1].split("，")[0].split("（")[0]
    tm = time.strftime("%H:%M", time.localtime(target_ts))
    add(f"T1b-{n:03d}", "T1b", f"林川在{d}上午几点心率达到了{hr_val}？（±2分钟内算对）",
        morning, {"time": tm, "hr": hr_val}, "time")
    n += 1

# ---------- T2 人物互动统计（人物×周/月，200）----------
inter = conn.execute("SELECT timestamp_s, type, content FROM raw_log "
                     "WHERE type IN ('message','speech') ORDER BY timestamp_s").fetchall()
combos = []
for person in PEOPLE:
    for wk in sorted({week(ts) for ts, _, _ in inter}):
        rows = [(ts, typ, c) for ts, typ, c in inter
                if person in c and week(ts) == wk]
        if len(rows) >= 2:
            combos.append(("WEEK", person, wk, rows))
    for m in sorted({mon(ts) for ts, _, _ in inter}):
        rows = [(ts, typ, c) for ts, typ, c in inter
                if person in c and mon(ts) == m]
        if len(rows) >= 3:
            combos.append(("MONTH", person, m, rows))
random.shuffle(combos)
n = 0
for scope, person, period, rows in combos:
    if n >= 200:
        break
    if scope == "WEEK":
        ctx = [f"{fmt(ts)} [{typ}] {content}" for ts, typ, content in rows]
        add(f"T2-{n:03d}", "T2", f"{period} 这一周林川和{person}有多少次互动？只回答数字。",
            ctx, {"count": len(rows), "person": person}, "count")
    else:
        ctx = [f"{fmt(ts)} [{typ}] {content}" for ts, typ, content in rows[::2]]
        add(f"T2-{n:03d}", "T2", f"{period[4:6]}月林川和{person}有多少次互动？只回答数字。",
            ctx, {"count": len(rows), "person": person}, "count")
    n += 1

# ---------- T3 消费统计（月总/月分商户/周总，100）----------
count = 0
import re
month_rows = defaultdict(list)
for ts, content in pays:
    month_rows[mon(ts)].append((ts, content))
for m in sorted(month_rows):
    rows = month_rows[m]
    total = sum(int(re.search(r"¥(\d+)", c).group(1)) for _, c in rows if re.search(r"¥(\d+)", c))
    ctx = [f"{fmt(ts)} {content}" for ts, content in rows]
    add(f"T3-{count:03d}", "T3", f"{m[4:6]}月林川消费总共花了多少钱？共几笔？格式：共X元，Y笔。",
        ctx, {"total": total, "count": len(rows)}, "money")
    count += 1
vendor_wk = defaultdict(list)
for ts, content in pays:
    name = content.split("¥")[0].strip()
    vendor_wk[(name, week(ts))].append((ts, content))
combos = [(k, v) for k, v in vendor_wk.items() if len(v) >= 2]
random.shuffle(combos)
for (name, wk), rows in combos:
    if count >= 100:
        break
    total = sum(int(re.search(r"¥(\d+)", c).group(1)) for _, c in rows if re.search(r"¥(\d+)", c))
    ctx = [f"{fmt(ts)} {content}" for ts, content in rows]
    add(f"T3-{count:03d}", "T3", f"{wk} 这周「{name}」上花了多少钱？只回答数字。",
        ctx, {"total": total, "count": len(rows)}, "money")
    count += 1

# ---------- T4 承诺（30）----------
promises = conn.execute("SELECT timestamp_s, content FROM raw_log WHERE type='speech' AND "
                        "(content LIKE '%答应%' OR content LIKE '%保证%' OR content LIKE '%承诺%' "
                        "OR content LIKE '%月底交付%' OR content LIKE '%明天给你%') "
                        "ORDER BY timestamp_s").fetchall()
for i, (ts, content) in enumerate(promises[:30]):
    d = time.strftime("%m月%d日", time.localtime(ts))
    add(f"T4-{i:03d}", "T4", f"林川在{d}前后许下了什么承诺？原话是什么？",
        [f"{fmt(ts)} {content}"], {"promise": content}, "contains")

# ---------- T5 运动心率峰值（周峰值 13 + 单次峰值 45）----------
wk_vitals = conn.execute("SELECT timestamp_s, content FROM raw_log WHERE type='vital' AND content LIKE '%跑步中心率%' ORDER BY timestamp_s").fetchall()
wk_by = defaultdict(list)
single = []
for ts, content in wk_vitals:
    val = int(content.split("心率 ")[1])
    wk_by[week(ts)].append((ts, val))
    single.append((ts, val))
n = 0
for wk in sorted(wk_by):
    if n >= 13:
        break
    items = wk_by[wk]
    if len(items) < 5:
        continue
    truth_max = max(v for _, v in items)
    ctx = [f"{fmt(ts)} 心率 {v}" for ts, v in items[::2]]
    add(f"T5-{n:03d}", "T5", f"{wk} 这一周林川运动时心率最高到过多少？（±2内算对）只回答数字。",
        ctx, {"max": truth_max}, "maxnum")
    n += 1
singles = [(ts, v) for ts, v in single if v >= 140]
random.shuffle(singles)
for ts, val in singles[:45]:
    ctx = [f"{fmt(ts2)} 心率 {v}" for ts2, v in single if abs(ts2 - ts) < 1800]
    add(f"T5-{n:03d}", "T5", f"林川在{fmt(ts)}这次运动中心率峰值是多少？（±2内算对）只回答数字。",
        ctx, {"max": val}, "maxnum")
    n += 1

# ---------- T6 门控（补足至 1000）----------
base_cases = [
    ("心率 72，用户在工位坐着", "IGNORE"),
    ("静息状态下心率 110 持续 5 分钟", "ESCALATE"),
    ("小王发来消息：明天能见面吗？", "LOCAL"),
    ("张总发来消息：交付时间表发我，今天要", "ESCALATE"),
    ("用户在地铁上，心率 88", "IGNORE"),
    ("用户深夜 23:40 支付夜宵外卖 ¥45（连续第 4 天）", "ESCALATE"),
    ("用户连续第 3 天对家人说'我在忙'（实际在刷手机）", "ESCALATE"),
    ("电梯里听到同事谈论天气", "IGNORE"),
    ("用户对张总说：这个版本明天给你方案（今天已是周四）", "ESCALATE"),
    ("运动中瞬时心率 142", "IGNORE"),
    ("银行短信：账户支出 ¥15,000", "ESCALATE"),
    ("用户说：今天真没意思", "LOCAL"),
]
variants = {"小王": ["小王", "小雅", "小陈"], "¥45": ["¥38", "¥52", "¥45"],
            "心率 72": ["心率 68", "心率 74", "心率 71"], "¥15,000": ["¥12,000", "¥15,000", "¥18,000"],
            "142": ["138", "142", "145"]}
count = len(Q)
i = 0
while count < 1000:
    text, expect = base_cases[i % len(base_cases)]
    t = text
    for orig, opts in variants.items():
        if orig in t:
            t = t.replace(orig, opts[(i // 4) % len(opts)])
    add(f"T6-{count:04d}", "T6",
        f"判断这条事件应该 IGNORE（忽略只留档）/ LOCAL（本地小处理）/ ESCALATE（叫云端大模型）中的哪一种？只回答三个词之一。\n事件：{t}",
        [], {"label": expect}, "label")
    count += 1
    i += 1

conn.close()
print(f"题库总数: {len(Q)}")
from collections import Counter
print(Counter(x["type"] for x in Q))
out = os.path.join(ROOT, "run", "bench1k", "questions.json")
os.makedirs(out, exist_ok=True) if False else os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(Q, f, ensure_ascii=False)
print("题库已保存:", out)
