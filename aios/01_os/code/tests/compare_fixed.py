# -*- coding: utf-8 -*-
"""修正判分器 + 大模型 vs 1.5B 诚实对比
修正：T1a 日期前导零归一化 / T3 按题面要求判 / T5 真相从考生可见 ctx 重算
"""
import json
import os
import re

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
Q = {x["qid"]: x for x in json.load(open(r"run\bench1k\questions.json", encoding="utf-8"))}

# 1.5B 答案（local-n0）
local = {}
for line in open(r"run\bench1k\results.jsonl", encoding="utf-8"):
    try:
        r = json.loads(line)
        if r["condition"] == "local-n0":
            local[r["qid"]] = r["answer"]
    except Exception:
        pass
# 大模型答案
big = {}
for line in open(r"run\bench1k\answers_big_cmd.jsonl", encoding="utf-8"):
    r = json.loads(line)
    big[r["qid"]] = r["answer"]


def norm_date(d):
    """07月10日 → 7月10日（前导零归一）"""
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
        want = int(hh) * 60 + int(mm)
        return 1.0 if abs(got - want) <= 2 else 0.0
    if chk == "count":
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        return 1.0 if t["count"] in nums else 0.0
    if chk == "money":
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        if "共几笔" in qtext:     # 月题要求金额+笔数
            return 1.0 if (t["total"] in nums and t["count"] in nums) else 0.0
        return 1.0 if t["total"] in nums else 0.0   # 周题只要求金额
    if chk == "contains":
        return 1.0 if t["promise"][:12] in ans_text else 0.0
    if chk == "maxnum":
        # 真相从考生可见的 ctx 重算（修复生成器真相不可得 bug）
        ctx_vals = [int(m.group(1)) for ln in q["ctx"]
                    for m in [re.search(r"心率 (\d+)", ln)] if m]
        if not ctx_vals:
            return 1.0 if "没有" in ans_text else 0.0
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        want = max(ctx_vals)
        return 1.0 if any(abs(x - want) <= 2 for x in nums) else 0.0
    if chk == "label":
        up = ans_text.upper()
        for v in ("ESCALATE", "LOCAL", "IGNORE"):
            if v in up:
                return 1.0 if v == t["label"] else 0.0
        return 0.0
    return 0.0


def report(tag, answers):
    by_type = {}
    all_sc = []
    missing = []
    for qid in Q:
        if qid not in answers:
            missing.append(qid)
            continue
        sc = grade(qid, answers[qid])
        by_type.setdefault(Q[qid]["type"], []).append(sc)
        all_sc.append(sc)
    print(f"\n=== {tag}（修正判分器）===")
    for t in sorted(by_type):
        v = by_type[t]
        print(f"  {t}: {sum(v)/len(v)*100:.1f}%（{len(v)} 题）")
    if all_sc:
        print(f"  总计: {sum(all_sc)/len(all_sc)*100:.1f}%（{len(all_sc)} 题）")
    if missing:
        print(f"  缺答案: {len(missing)} 题")
    return all_sc


big_sc = report("大模型（指挥官）", big)
local_sc = report("本地 1.5B", local)
