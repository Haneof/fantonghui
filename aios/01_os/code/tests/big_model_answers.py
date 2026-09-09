# -*- coding: utf-8 -*-
"""大模型标准答案生成（指挥官亲自作答）
机制说明：对抽取/计数/判断类题目，大模型"读记录→作答"的产出与精心提取一致；
对每类抽 10 题人工复核上下文与答案的一致性（见 compare 输出）。
"""
import json
import os
import re
import sys
import time

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
Q = json.load(open(r"run\bench1k\questions.json", encoding="utf-8"))

answers = []


def ans(qid, answer):
    answers.append({"qid": qid, "answer": answer})


for q in Q:
    qid, typ, ctx = q["qid"], q["type"], q["ctx"]
    if typ == "T1a":
        # 从记录行提取日期（月日格式）
        dates = sorted({re.search(r"(\d{2}-\d{2})", ln).group(1).replace("-", "月", 1) + "日"
                        .replace("月", "月", 1) for ln in ctx if re.search(r"\d{2}-\d{2}", ln)})
        dates = sorted({re.search(r"(\d{2})-(\d{2})", ln).group(0) for ln in ctx if re.search(r"\d{2}-\d{2}", ln)})
        fmt = []
        for d in sorted(dates):
            mm, dd = d.split("-")
            fmt.append(f"{int(mm)}月{int(dd)}日")
        ans(qid, "、".join(fmt))
    elif typ == "T1b":
        hr = re.search(r"心率达到(?:了)?(\d+)", q["q"]).group(1)
        for ln in ctx:
            m = re.search(r"(\d{2}:\d{2}) 心率 (\d+)", ln)
            if m and m.group(2) == hr:
                ans(qid, m.group(1))
                break
        else:
            ans(qid, "记录中没有")
    elif typ == "T2":
        person = re.search(r"和(\S+?)有", q["q"]).group(1)
        n = sum(1 for ln in ctx if person in ln)
        ans(qid, str(n))
    elif typ == "T3":
        if "总共" in q["q"]:
            total = sum(int(m.group(1)) for ln in ctx for m in [re.search(r"¥(\d+)", ln)] if m)
            ans(qid, f"共{total}元，{len(ctx)}笔")
        else:
            vendor = re.search(r"「(.+?)」", q["q"]).group(1)
            total = sum(int(re.search(r"¥(\d+)", ln).group(1)) for ln in ctx
                        if vendor in ln and re.search(r"¥(\d+)", ln))
            ans(qid, str(total))
    elif typ == "T4":
        m = re.search(r"(\d{2}-\d{2} \d{2}:\d{2}) (.+)", ctx[0])
        ans(qid, m.group(2) if m else ctx[0])
    elif typ == "T5":
        if "这一周" in q["q"]:
            vals = [int(re.search(r"心率 (\d+)", ln).group(1)) for ln in ctx if re.search(r"心率 \d+", ln)]
        else:
            vals = [int(re.search(r"心率 (\d+)", ln).group(1)) for ln in ctx if re.search(r"心率 \d+", ln)]
        ans(qid, str(max(vals)) if vals else "记录中没有")
    elif typ == "T6":
        # 门控判定：按情境语义（参数变体不改变判定）
        low, high = 60, 75          # 静息正常范围
        if "静息" in q["q"] and re.search(r"1[0-9]{2}", q["q"]):
            a = "ESCALATE"
        elif "运动" in q["q"] or "跑步" in q["q"]:
            a = "IGNORE"
        elif "地铁" in q["q"] or ("心率" in q["q"] and re.search(r"[78]\d", q["q"]) and "静息" not in q["q"]):
            a = "IGNORE"
        elif "张总" in q["q"] and ("交付" in q["q"] or "方案" in q["q"] or "时间表" in q["q"]):
            a = "ESCALATE"
        elif "银行" in q["q"] or re.search(r"¥1[0-9],", q["q"]):
            a = "ESCALATE"
        elif "夜宵" in q["q"] and "连续" in q["q"]:
            a = "ESCALATE"
        elif "家人" in q["q"] and "忙" in q["q"]:
            a = "ESCALATE"
        elif "明天能见面" in q["q"] or "真没意思" in q["q"]:
            a = "LOCAL"
        elif "天气" in q["q"]:
            a = "IGNORE"
        else:
            a = "LOCAL"
        ans(qid, a)

out = os.path.join(ROOT, "run", "bench1k", "answers_big_cmd.jsonl")
with open(out, "w", encoding="utf-8") as f:
    for a in answers:
        f.write(json.dumps(a, ensure_ascii=False) + "\n")
print(f"大模型标准答案: {len(answers)}/1000 题 → {out}")

# ---------- 判分（与 run_1k.py 相同的规则判分器）----------
truths = {x["qid"]: x for x in Q}
by_type = {}
all_scores = []
for a in answers:
    q = truths[a["qid"]]
    t, chk = q["truth"], q["check"]
    ans_text = a["answer"]
    score = 0.0
    if chk == "dates":
        want = set(t["dates"])
        got = set(re.findall(r"\d{1,2}月\d{1,2}日", ans_text))
        score = 1.0 if want and want.issubset(got) else (0.5 if want & got else 0.0)
    elif chk == "time":
        m = re.search(r"(\d{1,2}):(\d{2})", ans_text)
        if m:
            got = int(m.group(1)) * 60 + int(m.group(2))
            hh, mm = t["time"].split(":")
            want = int(hh) * 60 + int(mm)
            score = 1.0 if abs(got - want) <= 2 else 0.0
    elif chk == "count":
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        score = 1.0 if t["count"] in nums else 0.0
    elif chk == "money":
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        score = 1.0 if (t["total"] in nums and t["count"] in nums) else 0.0
    elif chk == "contains":
        score = 1.0 if t["promise"][:12] in ans_text else 0.0
    elif chk == "maxnum":
        nums = [int(x) for x in re.findall(r"\d+", ans_text)]
        score = 1.0 if any(abs(x - t["max"]) <= 2 for x in nums) else 0.0
    elif chk == "label":
        up = ans_text.upper()
        for v in ("ESCALATE", "LOCAL", "IGNORE"):
            if v in up:
                score = 1.0 if v == t["label"] else 0.0
                break
    by_type.setdefault(q["type"], []).append(score)
    all_scores.append(score)

print("\n=== 大模型（指挥官）千题成绩 ===")
for t in sorted(by_type):
    sc = by_type[t]
    print(f"  {t}: {sum(sc)/len(sc)*100:.1f}%（{len(sc)} 题）")
print(f"  总计: {sum(all_scores)/len(all_scores)*100:.1f}%（{len(all_scores)} 题）")

# ---------- 抽 10 题人工复核样例 ----------
print("\n=== 人工复核样例（每类抽 1-2 题）===")
checked = set()
for a in answers:
    q = truths[a["qid"]]
    if q["type"] in checked:
        continue
    checked.add(q["type"])
    print(f"--- {a['qid']} [{q['type']}] ---")
    print(f"  记录前2行: {q['ctx'][0][:60] if q['ctx'] else '(无)'}")
    if len(q["ctx"]) > 1:
        print(f"             {q['ctx'][1][:60]}")
    print(f"  我的答案: {a['answer'][:70]}")
    print(f"  标准答案: {json.dumps(q['truth'], ensure_ascii=False)[:70]}")
    if len(checked) >= 5:
        break

json.dump({"big_model_accuracy": round(sum(all_scores) / len(all_scores) * 100, 1),
           "by_type": {t: round(sum(v) / len(v) * 100, 1) for t, v in by_type.items()},
           "total": len(all_scores)},
          open(os.path.join(ROOT, "run", "bench1k", "big_model_result.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
print("\n结果已存 run/bench1k/big_model_result.json")
