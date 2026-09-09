# -*- coding: utf-8 -*-
"""门控 v2 · 对比机制规则引擎 —— 在千题基准 T6（636 题）上实测
规则只看事件文本，做阈值/模式对比，不让任何模型"思考"。
"""
import json
import re
import sys

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
sys.path.insert(0, ROOT)

Q = json.load(open(ROOT + r"\run\bench1k\questions.json", encoding="utf-8"))
T6 = [q for q in Q if q["type"] == "T6"]


def rule_gate(text):
    """对比机制门控：返回 IGNORE / LOCAL / ESCALATE
    设计原则（用户裁定 2026-09-09）：本地只做数据整理+阈值触发，不做理解；
    误报可由 Regret 环收紧阈值，漏报由非对称阈值兜底（宁可多叫醒）。
    """
    t = text
    # ---------- 1) 身体数据：心率 ----------
    m = re.search(r"心率\s*(\d+)", t)
    if m:
        hr = int(m.group(1))
        if re.search(r"运动|跑步|骑行|健身|锻炼", t):
            return "IGNORE"                      # 运动语境豁免：高低都正常
        if re.search(r"地铁|公交|通勤|走路|电梯|车", t):
            return "IGNORE" if 55 <= hr <= 105 else "ESCALATE"
        # 静息/工位/睡眠/无语境：正常带 60-100（上线后换个人基线）
        return "IGNORE" if 60 <= hr <= 100 else "ESCALATE"
    # ---------- 2) 消费数据：金额 ----------
    m = re.search(r"[¥￥]\s*([\d,]+)", t)
    if m:
        amt = int(m.group(1).replace(",", ""))
        if re.search(r"银行|账户|转账|贷款|还款", t):
            return "ESCALATE" if amt >= 5000 else "LOCAL"   # 大额资金变动
        if re.search(r"夜宵|外卖|深夜|23:\d\d|0[0-2]:\d\d", t) and re.search(r"连续", t):
            return "ESCALATE"                    # 行为模式：连续深夜消费
        return "LOCAL"                           # 普通消费：留档，日结走 SQL
    # ---------- 3) 消息/话语：模式规则 ----------
    if re.search(r"[\u4e00-\u9fa5]总|老板|领导|上司|甲方", t):
        if re.search(r"发来消息|要求|催|问", t) and re.search(r"交付|时间表|方案|评审|今天要|尽快|加班", t):
            return "ESCALATE"                    # 上级施压类
        if re.search(r"说[：:]", t) and re.search(r"明天|今天|晚上|下周|给你|发你|交", t):
            return "ESCALATE"                    # 对上级做了承诺 → 需追踪
    if re.search(r"银行|账户支出|转账|盗刷|验证码", t):
        return "ESCALATE"
    if re.search(r"家人|老婆|爸妈|孩子|家里", t) and re.search(r"连续", t):
        return "ESCALATE"                        # 关系模式：连续敷衍家人
    if re.search(r"天气|电梯|闲聊|八卦|广告", t):
        return "IGNORE"                          # 明确无信息量
    if re.search(r"见面|没意思|无聊|吃了吗|周末|改天|有空", t):
        return "LOCAL"                           # 朋友闲聊/日常情绪：本地处理
    if re.search(r"夜宵|外卖", t) and re.search(r"连续", t):
        return "ESCALATE"
    return "LOCAL"                               # 默认：留档不吵（漏报由复核环兜底）


# ---- 跑 636 题 ----
by_case = {}
all_sc = []
misses = []
for q in T6:
    m = re.search(r"事件：(.+)", q["q"], re.S)
    ev = m.group(1).strip() if m else (q["ctx"][0] if q["ctx"] else q["q"])
    pred = rule_gate(ev)
    want = q["truth"]["label"]
    sc = 1.0 if pred == want else 0.0
    all_sc.append(sc)
    # 归类到基准情境（用模式前缀）
    norm = re.sub(r"\d+", "N", ev)[:14]
    by_case.setdefault(norm, []).append((pred, want))
    if pred != want and len(misses) < 12:
        misses.append((q["qid"], ev[:60], pred, want))

print(f"=== 对比机制规则引擎 · T6 门控 636 题实测 ===")
print(f"准确率: {sum(all_sc)/len(all_sc)*100:.1f}%（小模型 1.5B: 31.9% / 2B: 28.6% / 大模型: 91.7%）")
print(f"\n判错样例（最多 12 条）:")
for qid, ev, pred, want in misses:
    print(f"  {qid} | {ev} | 规则={pred} 标准={want}")

# 混淆分析
from collections import Counter
conf = Counter()
for q in T6:
    m = re.search(r"事件：(.+)", q["q"], re.S)
    ev = m.group(1).strip() if m else ""
    pred, want = rule_gate(ev), q["truth"]["label"]
    if pred != want:
        conf[(re.sub(r'\d+', 'N', ev)[:16], want, pred)] += 1
print("\n错误集中点（情境 → 标准 vs 规则）:")
for (ev, want, pred), n in conf.most_common(8):
    print(f"  {n:3d} 题 | {ev} | 标准={want} 规则={pred}")

# 存结果
json.dump({"gate_rules_accuracy": round(sum(all_sc) / len(all_sc) * 100, 1),
           "n": len(all_sc),
           "confusion": [{"case": k, "want": w, "pred": p, "n": n} for (k, w, p), n in conf.most_common()]},
          open(ROOT + r"\run\bench1k\gate_rules_result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n已存 gate_rules_result.json")
