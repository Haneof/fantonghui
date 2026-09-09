# -*- coding: utf-8 -*-
"""2B/4B 结果判分（修正判分器 + qid 去重）"""
import json
import os
import re
import sys

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
Q = {x["qid"]: x for x in json.load(open(r"run\bench1k\questions.json", encoding="utf-8"))}


def norm_date(d):
    m = re.match(r"0?(\d{1,2})月0?(\d{1,2})日", d)
    return f"{int(m.group(1))}月{int(m.group(2))}日" if m else d


def grade(qid, ans_text):
    q = Q[qid]
    t, chk, qtext = q["truth"], q["check"], q["q"]
    if chk == "dates":
        want = {norm_date(d) for d in t["dates"]}
        got = {norm_date(x) for x in re.findall(r"\d{1,2}月\d{1,2}日", ans_text)}
        return 1.0 if want and want.issubset(got) else (0.5 if want & got else 0.0)
    if chk == "time":
        m = re.search(r"(\d{1,2}):(\d{2})", ans_text)
        if not m:
            return 0.0
        got = int(m.group(1)) * 60 + int(m.group(2))
        hh, mm = t["time"].split(":")
        return 1.0 if abs(got - (int(hh) * 60 + int(mm))) <= 2 else 0.0
    if chk == "count":
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        return 1.0 if t["count"] in nums else 0.0
    if chk == "money":
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        if "共几笔" in qtext:
            return 1.0 if (t["total"] in nums and t["count"] in nums) else 0.0
        return 1.0 if t["total"] in nums else 0.0
    if chk == "contains":
        return 1.0 if t["promise"][:12] in ans_text else 0.0
    if chk == "maxnum":
        ctx_vals = [int(m.group(1)) for ln in q["ctx"]
                    for m in [re.search(r"心率 (\d+)", ln)] if m]
        if not ctx_vals:
            return 1.0 if "没有" in ans_text else 0.0
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        return 1.0 if any(abs(x - max(ctx_vals)) <= 2 for x in nums) else 0.0
    if chk == "label":
        up = ans_text.upper()
        for v in ("ESCALATE", "LOCAL", "IGNORE"):
            if v in up:
                return 1.0 if v == t["label"] else 0.0
        return 0.0
    return 0.0


def report(tag, path):
    by_type = {}
    all_sc = []
    latest = {}
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
            latest[r["qid"]] = r["answer"]      # 后写覆盖（去重）
        except Exception:
            pass
    for qid, ans_text in latest.items():
        if qid not in Q:
            continue
        sc = grade(qid, ans_text)
        by_type.setdefault(Q[qid]["type"], []).append(sc)
        all_sc.append(sc)
    print(f"\n=== {tag}（修正判分 · {len(latest)} 题去重后）===")
    for t in sorted(by_type):
        v = by_type[t]
        print(f"  {t}: {sum(v)/len(v)*100:.1f}%（{len(v)} 题）")
    print(f"  总计: {sum(all_sc)/len(all_sc)*100:.1f}%")
    return {t: round(sum(v) / len(v) * 100, 1) for t, v in by_type.items()}, round(sum(all_sc) / len(all_sc) * 100, 1)


r2b = report("本地 Qwen3.5-2B", r"run\bench1k\results_2b.jsonl")
if os.path.exists(r"run\bench1k\results_4b.jsonl"):
    r4b = report("本地 Qwen3.5-4B", r"run\bench1k\results_4b.jsonl")
else:
    r4b = None

# 大模型对照（已有）
big = {"T1a": 100.0, "T1b": 74.7, "T2": 75.6, "T3": 100.0, "T4": 100.0, "T5": 100.0, "T6": 91.7}
loc15 = {"T1a": 12.8, "T1b": 20.7, "T2": 10.3, "T3": 63.9, "T4": 33.3, "T5": 77.6, "T6": 31.9}

print("\n=== 五档能力对照（修正判分器）===")
print(f"{'类型':<8} {'大模型':>8} {'3.5-4B':>8} {'3.5-2B':>8} {'2.5-1.5B':>8}")
for t in sorted(set(big) | set(r2b)):
    b = big.get(t, "-")
    four = r4b.get(t, "-") if r4b else "进行中"
    two = r2b.get(t, "-")
    l15 = loc15.get(t, "-")
    print(f"{t:<8} {b:>8} {str(four):>8} {str(two):>8} {str(l15):>8}")
print(f"{'总计':<8} {'90.6':>8} {str(r4b.get('total') if r4b else '进行中'):>8} {str(r2b.get('total')):>8} {'33.5':>8}")

json.dump({"qwen35_2b": r2b, "qwen35_4b": r4b if r4b else "进行中"},
          open(r"run\bench1k\model_comparison.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("已存 model_comparison.json")
