"""aa30 题库方向性阅卷器（Grader: 01a0aa2c-fantonghui，交叉阅卷）。

目标题库：daily-examiner-01a0aa30《10,000 个人 × 各自完整一天》。
阅卷对象：任意战队提交的六维总结答卷（ans_*.jsonl）。
标答来源：``ground_truth_10000_people.jsonl.xz``（出卷方独立发布）。

判分哲学（遵守出卷方 README 纪律）：
1. **方向优先**：以 ``semantic_intent``（结局意图）驱动方向标记簇判定，
   不要求逐字命中 core_claim 或 acceptable_directions（严禁死板字句匹配）；
2. **红线为命题级**：仅在答卷以肯定性断言表述与证据相反的命题时触发
   （否定语境豁免：''没有复合'' 不触发红线），不用禁词子串匹配；
3. **实体与数值锚点**：required_entities 召回 + structured_anchors 数值正确性
   （分→元、bpm、分钟、步等格式归一）；
4. **自出自做一票否决**：solver_agent == generator_agent 直接 0 分 FAIL。

单维分 = 方向 60 + 实体召回 20 + 数值锚点 20；红线触发则该维 0 分且整卷 FAIL。
总分 = global 25% + 五维各 15%；PASS ≥ 80。
"""

from __future__ import annotations

import argparse
import json
import lzma
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

SOLVER_AGENT = "01a0aa2c-fantonghui"
GENERATOR_AGENT = "daily-examiner-01a0aa30"

WEIGHTS = {
    "global_daily_summary": 0.25,
    "dim:health": 0.15, "dim:social": 0.15, "dim:emotion": 0.15,
    "dim:finance": 0.15, "dim:career": 0.15,
}
SUBKEY = {
    "global_daily_summary": "generated_global_summary",
    "dim:health": "generated_health_summary",
    "dim:social": "generated_social_summary",
    "dim:emotion": "generated_emotion_summary",
    "dim:finance": "generated_finance_summary",
    "dim:career": "generated_career_summary",
}

# ---------------------------------------------------------------------------
# 方向标记簇：intent → (正向方向标记, 反向命题标记)
# 反向标记仅用于红线判定（且需肯定性断言 + 正向方向未命中）
# ---------------------------------------------------------------------------

MARKERS = {
    # ---- career ----
    "DEADLINE_RESCHEDULED": (["延期", "改到明天", "任务保留", "改期", "不是撤销"], ["永久取消", "已完成核验", "验收通过"]),
    "REVISION_PENDING": (["补充", "整改", "尚未最终", "留到明天", "复核", "未通过"], ["已核对通过", "正式取消"]),
    "SCOPE_REDUCED_CONTINUES": (["缩小", "只保留第一部分", "其余取消", "范围"], ["要求加量", "全面取消"]),
    "TASK_CANCELLED_LIMITED_SCOPE": (["正式取消", "停止投入", "本次任务"], ["全部岗位解除", "继续推进", "验收通过"]),
    "EXTRA_TASK_DECLINED": (["不接额外", "婉拒", "现有任务继续", "不加单"], ["接受了额外任务", "同意加单"]),
    "OFFER_UNDECIDED": (["邀请", "待决", "未签约", "考虑", "明天答复", "口头意向"], ["已正式签约", "已经辞职", "断然拒绝"]),
    "ALLEGATION_CORRECTED": (["指责不成立", "更正", "推翻", "回执"], ["承认漏交", "指责成立"]),
    "REJECTION_REVERSED": (["核对通过", "旧版", "作废", "按新版执行"], ["仍然退回", "未通过"]),
    # ---- social ----
    "BREAKUP_CONFIRMED": (["结束伴侣关系", "分手", "关系结束", "感情破裂", "分开"], ["复合", "和好", "甜蜜互动"]),
    "BREAKUP_WITHDRAWN": (["撤回分手", "继续交往", "和好", "谈开"], ["已经分手", "结束关系", "感情破裂"]),
    "CAREGIVING_PENDING_DIAGNOSIS": (["复诊", "陪", "预约", "尚未", "没有新的诊断"], ["已经手术", "确诊绝症", "已经治愈"]),
    "CARE_RESPONSIBILITY_SHARED": (["分工", "一起承担", "陪诊", "分担"], ["一人独自", "已经确诊"]),
    "COLLEAGUE_CONFLICT_REPAIRED": (["道歉", "指责不成立", "继续", "合作"], ["关系破裂", "继续指责"]),
    "FRIEND_BOUNDARY_ACCEPTED": (["边界", "没有绝交", "接受", "婉拒"], ["绝交", "承诺通宵", "为了证明关系硬撑"]),
    "FRIEND_SUPPORT_CONFIRMED": (["倾听", "支持", "周末见面", "被理解"], ["借钱", "恋爱承诺"]),
    "LEASE_NEGOTIATION_PENDING": (["租金", "租约", "有效", "未谈妥", "再谈"], ["已经搬走", "已被赶出", "租金已生效"]),
    # ---- emotion（与社交结局同源） ----
    "EMOTION_BREAKUP": (["难过", "委屈", "仍能"], ["狂喜", "一天都很开心"]),
    "EMOTION_BREAKUP_WITHDRAWN": (["委屈", "松了口气", "疲惫", "谈开"], ["一天都很开心"]),
    "EMOTION_RECONCILED": (["委屈", "松了口气", "疲惫"], ["一天都很开心"]),
    "EMOTION_FRIEND_BOUNDARY": (["压力", "放松", "松了"], ["全天愉悦"]),
    "EMOTION_PARENT_PENDING": (["担心", "焦虑", "还没诊断"], ["确诊", "狂喜"]),
    "EMOTION_SUPPORT": (["累", "被理解", "没那么孤立"], ["完全孤立", "狂喜"]),
    "EMOTION_CARE_SHARED": (["松了口气", "担心", "不像下午那么慌"], ["完全不担心", "确诊"]),
    "EMOTION_COWORKER_APOLOGY": (["憋屈", "没那么生气", "恢复信任"], ["一直很生气", "关系破裂"]),
    "EMOTION_HOUSING_PENDING": (["不安", "还没确定", "核对预算"], ["已确定安居", "狂喜"]),
    # ---- health ----
    "HEALTH_STABLE": (["平稳", "无明显突升", "静坐"], ["骤升", "生理危象", "心动过速"]),
    "HEALTH_STRESS_RECOVERED": (["升至", "回落", "缓解", "复测"], ["持续偏快", "确诊心脏病"]),
    "HEALTH_STRESS_PERSISTENT": (["持续偏快", "复测仍", "升至"], ["已经回落", "全天平稳", "确诊心脏病"]),
    "HEALTH_SHORT_SLEEP": (["睡眠不足", "睡得短", "疲倦", "仅"], ["睡眠充足", "精力充沛"]),
    "HEALTH_EXERCISE": (["快步运动", "运动负荷"], ["静息异常", "生理危象"]),
    "HEALTH_OFF_WRIST_ARTIFACT": (["摘下", "无效", "伪迹", "接触为假"], ["摔倒", "心脏骤停"]),
    # ---- finance ----
    "FINANCE_INCOMING_SETTLED": (["实际到账", "已实际入账", "不是仅有"], ["仅口头承诺", "尚未到账"]),
    "FINANCE_INCOMING_PROMISED": (["承诺", "明天", "尚未到账", "未收到"], ["已经到账", "实际入账"]),
    "FINANCE_LOAN_TAKEN": (["放款", "负债", "借款本金"], ["工资", "净赚", "收入利润"]),
    "FINANCE_LOAN_DECLINED": (["试算", "未放款", "未签"], ["已放款", "新增负债"]),
    "FINANCE_REFUND_SETTLED": (["退款", "已入账"], ["新工资", "没有到账"]),
    "FINANCE_REFUND_PENDING": (["受理", "审核", "没有入账记录", "未退"], ["退款已到账"]),
    "FINANCE_REPAY_FULL": (["全额", "结清", "归零"], ["新增负债"]),
    "FINANCE_REPAY_PARTIAL": (["部分偿还", "未全部结清", "不能当作全部结清"], ["全额结清", "全部还清"]),
    "FINANCE_REPAIR_PAID": (["维修费", "支付"], ["分期", "借款支付"]),
    "FINANCE_FRAUD_PREVENTED": (["核实", "无此业务", "未转账"], ["已经汇款", "受骗转账"]),
}

#: 全局：需同时覆盖职业结局方向 + 社交结局方向 + 取舍陈述
GLOBAL_NEG = ["双喜临门", "全部待办已完成", "任务全部验收"]

_NEGATION_PREFIX = re.compile(r"(?:没有|未|不是|并非|不|无|而非|没有说|不要先说成)[^。；，,]{0,6}$")


def _polarity_ok(text: str, idx: int) -> bool:
    """检查标记在 idx 处是否为肯定性断言（否定语境豁免）。"""
    prefix = text[max(0, idx - 8):idx]
    return not _NEGATION_PREFIX.search(prefix)


def _fmt_structured(field: str, value) -> str:
    if field.endswith("_cents"):
        return f"{value / 100:.2f}"
    if "heart_rate" in field:
        return f"{value}bpm"
    if "minutes" in field:
        return f"{value}分钟"
    if "steps" in field:
        return f"{value}步"
    return str(value)


def evaluate_dimension(dim: str, answer_text: str, gt_block: dict,
                       intents_of_paper: dict) -> dict:
    """单维评定：方向 60 + 实体 20 + 数值 20；命题级红线一票否决。"""
    sub = re.sub(r"\s+", "", answer_text)
    anchors = gt_block.get("semantic_core_anchors", [])
    intents = [a.get("semantic_intent", "") for a in anchors]

    # 1) 红线：肯定性反向命题（仅当正向方向未命中时才可能触发）
    direction_hit = False
    pos_hit = neg_polarity_hit = None
    for it in intents:
        pos_marks, neg_marks = MARKERS.get(it, ((), ()))
        if any(m in sub for m in pos_marks):
            direction_hit = True
            pos_hit = it
            break
    for it in intents:
        pos_marks, neg_marks = MARKERS.get(it, ((), ()))
        for m in neg_marks:
            idx = sub.find(m)
            if idx >= 0 and _polarity_ok(sub, idx):
                neg_polarity_hit = (it, m)
                break
        if neg_polarity_hit:
            break
    if neg_polarity_hit and not direction_hit:
        return {"score": 0.0, "direction": 0.0, "veto": True,
                "reason": f"红线：肯定性反向命题 {neg_polarity_hit[1]}"}

    # 全局维度：需覆盖职业+社交双方向与取舍
    if dim == "global_daily_summary":
        need = []
        for key in ("career", "social"):
            it = intents_of_paper.get(key, "")
            if it in MARKERS:
                need.append(it)
        covered = sum(
            1 for it in need if any(m in sub for m in MARKERS[it][0])
        )
        direction_ratio = covered / len(need) if need else 1.0
        tradeoff = 1.0 if any(k in sub for k in ("决定", "取舍", "边界", "安排")) else 0.0
        direction_score = direction_ratio * (0.75 + 0.25 * tradeoff)
    else:
        direction_score = 1.0 if direction_hit else 0.0

    # 2) 实体召回
    ents = []
    for a in anchors:
        ents.extend(a.get("required_entities", []))
    ent_ratio = (
        sum(1 for e in ents if e and e in sub) / len(ents) if ents else 1.0
    )

    # 3) 数值锚点
    nums = []
    for a in anchors:
        for sa in a.get("structured_anchors", []):
            nums.append((sa.get("field", ""), sa.get("value")))
    num_ok = sum(
        1 for f, v in nums if _fmt_structured(f, v) in sub
    )
    num_ratio = num_ok / len(nums) if nums else 1.0

    score = round(60.0 * direction_score + 20.0 * ent_ratio + 20.0 * num_ratio, 2)
    return {
        "score": score,
        "direction": round(direction_score, 2),
        "entity": round(ent_ratio, 2),
        "number": round(num_ratio, 2),
        "veto": False,
        "reason": f"dir={direction_score} ent={ent_ratio:.2f} num={num_ratio:.2f}"
        + (f" [pos:{pos_hit}]" if pos_hit else ""),
    }


def load_gt(path: Path) -> dict:
    gt = {}
    opener = lzma.open if str(path).endswith(".xz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            g = json.loads(line)
            gt[g["question_id"]] = g["directional_ground_truth"]
    return gt


def main() -> int:
    ap = argparse.ArgumentParser(description="aa30 题库方向性阅卷")
    ap.add_argument("--answers", type=Path, default=Path(
        "benchmarks/daily_summary/answers/ans_01a0aa2c-fantonghui_on_daily-examiner-01a0aa30.jsonl"))
    ap.add_argument("--gt", type=Path, default=Path("/tmp/aa30/ground_truth_10000_people.jsonl.xz"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print("loading ground truth ...", file=sys.stderr)
    gt = load_gt(args.gt)

    answers = {}
    with open(args.answers, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            answers[a["question_id"]] = a

    scores, vetoes = [], 0
    verdicts = Counter()
    dim_scores = {d: [] for d in WEIGHTS}
    dim_dir = {d: [] for d in WEIGHTS}
    worst = []
    n = 0
    for qid, g in gt.items():
        if qid not in answers:
            continue
        sub = answers[qid]
        if sub.get("solver_agent") == GENERATOR_AGENT:
            scores.append(0.0)
            verdicts["FAIL(SELF)"] += 1
            continue
        intents_of_paper = {}
        for key, dim in (("career", "dim:career"), ("social", "dim:social")):
            block = g.get(dim, {})
            if block.get("semantic_core_anchors"):
                intents_of_paper[key] = block["semantic_core_anchors"][0].get("semantic_intent", "")
        total, fatal = 0.0, False
        notes = []
        for dim, w in WEIGHTS.items():
            r = evaluate_dimension(dim, sub.get(SUBKEY[dim], ""), g.get(dim, {}), intents_of_paper)
            dim_scores[dim].append(r["score"])
            dim_dir[dim].append(r["direction"])
            total += r["score"] * w
            if r["veto"]:
                fatal = True
                notes.append(f"{dim}:VETO")
        if fatal:
            total = 0.0
            vetoes += 1
        total = round(total, 2)
        scores.append(total)
        verdicts["PASS" if total >= 80.0 else "FAIL"] += 1
        if (total < 80.0 or fatal) and len(worst) < 60:
            worst.append((total, qid, "; ".join(notes[:3]) or "low"))
        n += 1
        if args.limit and n >= args.limit:
            break

    def avg(x):
        return round(statistics.mean(x), 4) if x else 0.0

    report = {
        "solver_agent": SOLVER_AGENT,
        "generator_tag": "daily-examiner-01a0aa30",
        "count": n,
        "avg_overall": avg(scores),
        "pass_rate": round(verdicts.get("PASS", 0) / max(n, 1), 4),
        "verdicts": dict(verdicts),
        "redline_veto_papers": vetoes,
        "per_dim_avg": {d: avg(v) for d, v in dim_scores.items()},
        "per_dim_direction": {d: avg(v) for d, v in dim_dir.items()},
        "worst_cases": worst[:20],
    }
    out = Path("benchmarks/daily_summary/reports/report_01a0aa2c-fantonghui_on_daily-examiner-01a0aa30.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
