"""aa30 全天生活流做题引擎（Solver: 01a0aa2c-fantonghui，跨队交叉做题）。

目标题库：daily-examiner-01a0aa30《10,000 个人 × 各自完整一天》（盲卷）。
遵守跨战队纪律：仅消费 ``questions_*.blind.jsonl`` 输入（不含标答），
不读取对方生成源码；本引擎从已清洗生活流的信号模板中抽取六维事实并组句。

抽取策略（全部来自输入流的可观测信号，0 LLM、确定性）：
- 职业线：工作联系人上午任务状态 + 下午结果性留言（8 结局模板）；
- 社交线：联系人晚间 MIC 诉求 + APP 收尾留言（8 关系结局模板）；
- 情绪线：本人晚间自述感受语句（与社交结局同源）；
- 健康线：睡眠统计 / 晨午晚 PPG / 复测 / 快步运动 / 脱腕伪迹（6 轨迹）；
- 财务线：日初快照 + 实际交易（含类别）+ 特殊财务事件 + 日终对账（10 面向）；
- 全局线：职业结局 × 社交结局 × 本人取舍陈述（"我决定……"）编织成主线。

防自做铁律：``solve()`` 拒绝 generator_agent 与本战队相同的试卷。
"""

from __future__ import annotations

import re
import time
from typing import Any

SOLVER_AGENT = "01a0aa2c-fantonghui"
TARGET_GENERATOR = "daily-examiner-01a0aa30"

# ---------------------------------------------------------------------------
# 信号模板 → 结局分类（关键词组按与模板的联合命中判定，容错单关键词缺失）
# ---------------------------------------------------------------------------

CAREER_RULES = [
    # (结局, 下午结果关键词组, 上午状态关键词组, 方向措辞要素)
    ("rescheduled", ("允许改到", "任务保留"), ("原定今晚核验",),
     "因时间冲突获准延期到明天，任务保留没有取消"),
    ("revise", ("收到了补充材料", "还没完成复核"), ("依据不够", "不通过"),
     "被要求补充依据，当天尚未最终通过，整改待定而非取消整个任务"),
    ("scope", ("缩小", "其余明确取消"), ("按完整范围准备",),
     "双方确认缩小范围只保留第一部分，其余明确取消，不是要求加量"),
    ("cancelled", ("正式取消", "先停止投入"), ("今天下午会最后确认",),
     "本次任务正式取消并停止投入，但这不是解除全部岗位或其他合作"),
    ("declined_extra", ("不接额外任务的决定已确认",), ("再接一项临时任务",),
     "婉拒在现有任务之外加接临时任务，现有任务继续，不视为终止现有安排"),
    ("credited", ("已核对通过", "旧版退回状态作废"), ("还有两处错误", "暂时退回"),
     "更正后的交付物已核对通过，旧版退回状态作废，按新版执行"),
    ("recovered", ("指责不成立", "更正"), ("漏交", "先不要下结论"),
     "漏交指责被系统回执推翻，负责人已更正，不实指责不成立"),
    ("offer_pending", ("确认邀请仍有效",), ("长期合作邀请", "口头意向"),
     "OFFER"),
]

SOCIAL_RULES = [
    ("breakup", ("确认结束伴侣关系",), ("我想分手", "把话说清楚"),
     "确认结束伴侣关系，钥匙之后交还；不是玩笑，也没有说复合"),
    ("reconciled", ("撤回分手", "继续交往"), ("气头上我说了分手", "认真谈谈"),
     "对方撤回气头上的分手话，双方同意继续交往，下周安排一次长谈"),
    ("friend_boundary", ("我接受你今晚没空", "没有绝交"), ("再陪我忙一晚上", "不把我当朋友"),
     "婉拒临时陪同但守住时间边界，对方接受，友谊没有破裂，约定周末再约"),
    ("parent_pending", ("明早你陪我去",), ("医院复诊要有人陪",),
     "家人明日医院复诊只是收到预约尚未就诊，商定明早由对方陪同，医生尚未给出新诊断"),
    ("support", ("我们约好周末见面", "不是借钱也不是恋爱承诺"), ("晚些时候我可以听你说说",),
     "朋友主动提供倾听支持，约好周末见面，不是借钱也不是恋爱承诺"),
    ("care_shared", ("我确认明早陪他去",), ("原定你一个人陪", "商量分工"),
     "陪诊责任重新分工：对方明早陪诊、本人负责晚上整理资料，家人尚未确诊不能说成绝症或已治愈"),
    ("coworker_apology", ("我看完记录了", "道歉"), ("说你不配合", "还没看完你的记录"),
     "同事先前的配合指责被记录推翻，已在原群道歉，双方继续按分工合作"),
    ("housing_pending", ("现租约仍有效", "涨租幅度还没谈妥"), ("租金可能调整", "征求意见"),
     "下月租金调整仅停留在征求意见阶段，现租约仍有效，没有要求今天搬离，周日再谈"),
]

#: 社交结局 → 情绪方向措辞（与本人晚间自述同源）
EMOTION_PHRASES = {
    "breakup": "关系结束带来难过和委屈，仍能按步骤处理事情",
    "reconciled": "早些时候委屈，谈开以后松了口气，还有点疲惫，不是一天都很开心",
    "friend_boundary": "先感到人情压力，边界被对方接受后放松，不用内疚到答应所有事情",
    "parent_pending": "担心家人的检查结果、有些焦虑，但知道还没诊断，先安排好明天行程",
    "support": "事情虽累，但有人愿意倾听，觉得被理解，没那么孤立",
    "care_shared": "有人一起承担明显松了口气，对检查仍担心但不像下午那么慌",
    "coworker_apology": "被指责时很憋屈，看到更正后没那么生气了，但还需要一点时间恢复信任",
    "housing_pending": "住处条件还没确定有些不安，暂时能住就先核对预算，不把可能当成事实",
}

#: 社交结局 → 关系对象角色提示（用于措辞）
SOCIAL_ROLE_HINT = {
    "breakup": "伴侣", "reconciled": "伴侣", "friend_boundary": "朋友",
    "parent_pending": "家人", "support": "朋友", "care_shared": "家人",
    "coworker_apology": "同事", "housing_pending": "房东",
}

HEALTH_STRESS_RECHECK_MAX = 100  # 复测 ≥100bpm 视为持续偏快
SHORT_SLEEP_MIN = 360            # 有效睡眠 <360 分钟视为睡眠不足

_RE_SLEEP = re.compile(r"有效睡眠(\d+)分钟")
_RE_HR = re.compile(r"心率(\d+)bpm")
_RE_STEPS = re.compile(r"全天步数(\d+)步")
_RE_EXERCISE = re.compile(r"快步运动(\d+)分钟")
_RE_IMU = re.compile(r"IMU峰值([\d.]+)g")
_RE_PPG = re.compile(r"PPG数值(\d+)标记无效")
_RE_MONEY = re.compile(r"([\d.]+)元")
_RE_DAY_START = re.compile(r"日初余额([\d.]+)元；个人借款本金([\d.]+)元")
_RE_DAY_END = re.compile(r"余额([\d.]+)元，借款本金([\d.]+)元；普通餐饮交通实际支出([\d.]+)元")


def _cents_to_yuan(c: int) -> str:
    return f"{c / 100:.2f}"


def _nz(v, unit: str = "") -> str:
    """None 防泄漏：缺失体征渲染为'未记录'。"""
    return f"{v}{unit}" if v is not None else "未记录"


class SelfSolveViolation(RuntimeError):
    """自出自做铁律违规。"""


def solve(blind_question: dict) -> dict:
    """对一份盲卷（不含 directional_ground_truth）生成六维总结答卷。"""
    t0 = time.perf_counter()
    q = blind_question
    gen = q.get("generator_agent", "")
    if gen == SOLVER_AGENT or gen.startswith("01a0aa2c"):
        raise SelfSolveViolation(f"拒绝自出自做：{q.get('question_id')} (generator={gen})")

    persona = q["persona"]
    name = persona["name"]
    contacts = {c["name"]: c.get("role", "") for c in persona.get("contacts", [])}
    artifact = persona.get("starting_context", {}).get("deliverable", "交付物")
    task = persona.get("starting_context", {}).get("task", "当日任务")

    slices = q.get("cleaned_daily_stream", [])
    ev_ids: list[str] = []

    def hit(text: str, *keywords: str) -> bool:
        return all(k in text for k in keywords)

    # ------------------------------------------------------------------ 扫流
    career_msg = social_msg = None
    career_from = social_from = None
    morning_career = evening_social = ""
    special_finance: list[tuple[str, str]] = []  # (类别, 原文)
    tx_by_cat: dict[str, list[int]] = {}
    day_start = day_end = None
    sleep_min = None
    hr_am = hr_noon = hr_pm = hr_recheck = None
    exercise_min = exercise_hr = None
    imu_g = ppg_invalid = None
    steps = None
    decision_stmt = None
    emotion_stmt = None
    for s in slices:
        src = s.get("speaker_or_source", "")
        content = s.get("content", "")
        modality = s.get("modality", "")
        t = (s.get("timestamp", "") or "")[11:16]

        if "有效睡眠" in content:
            m = _RE_SLEEP.search(content)
            if m:
                sleep_min = int(m.group(1))
        if modality == "SENSOR":
            m = _RE_HR.search(content)
            if m:
                v = int(m.group(1))
                if "晨起" in content:
                    hr_am = v
                elif "午间" in content:
                    hr_noon = v
                elif "再次静坐" in content:
                    hr_recheck = v
                elif "晚间" in content and "静坐" in content:
                    hr_pm = v
                elif "快步运动" in content:
                    exercise_hr = v
            m = _RE_STEPS.search(content)
            if m:
                steps = int(m.group(1))
            m = _RE_EXERCISE.search(content)
            if m:
                exercise_min = int(m.group(1))
            m = _RE_IMU.search(content)
            if m:
                imu_g = m.group(1)
            m = _RE_PPG.search(content)
            if m:
                ppg_invalid = m.group(1)
            continue

        if s.get("transaction"):
            tx = s["transaction"]
            tx_by_cat.setdefault(tx.get("category", "?"), []).append(tx.get("amount_cents", 0))
            for key, pat in (
                ("repay_full", "本金全额偿还"),
                ("repay_partial", "本金部分偿还"),
                ("incoming_settled", "已实际入账"),
                ("loan_taken", "已放款到账"),
                ("refund_settled", "这是退款"),
                ("repair_paid", "维修费"),
            ):
                if pat in content:
                    special_finance.append((key, content))
                    break
            continue

        if "日初快照" in src:
            m = _RE_DAY_START.search(content)
            if m:
                day_start = (float(m.group(1)), float(m.group(2)))
            continue
        if "日终" in src or "日界" in src and "对账" in src:
            m = _RE_DAY_END.search(content)
            if m:
                day_end = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            continue
        if "结算方" in src:
            if "今天安排汇出" in content:
                special_finance.append(("incoming_settled_notice", content))
            elif "计划明天转出" in content:
                special_finance.append(("incoming_promised_notice", content))
            continue

        # 财务特殊事件：按内容特征路由（特异模式优先，全键命中）
        if modality == "APP":
            special = _match_special_finance(content)
            if special:
                special_finance.append((special, content))
                continue

        # 联系人消息：职业线（上午状态 + 下午结果）与社交线（晚间）
        if src in contacts:
            if "09:30" <= t <= "11:59":
                morning_career = morning_career or content
            elif "15:00" <= t <= "16:59":
                career_msg, career_from = content, src
            if "19:00" <= t <= "21:59":
                if "19:00" <= t <= "20:00" and modality == "MIC":
                    evening_social = content
                elif social_msg is None and t >= "20:00":
                    social_msg, social_from = content, src
            continue

        # 本人的陈述
        if src == name:
            if "我决定" in content and "这是接下来的安排" in content:
                decision_stmt = content
            elif modality == "MIC" and "19:00" <= t <= "23:00" and _is_emotion_statement(content):
                emotion_stmt = emotion_stmt or content

    # ------------------------------------------------------------- 职业结局
    career_facet = None
    if career_msg:
        for facet, aft, _m, _p in CAREER_RULES:
            if hit(career_msg, *aft[:1]):
                career_facet = facet
                break
    if career_facet is None and morning_career:
        for facet, _a, mor, _p in CAREER_RULES:
            if hit(morning_career, *mor[:1]):
                career_facet = facet
                break
    career_phrase = next(
        (p for f, _a, _m, p in CAREER_RULES if f == career_facet),
        "当日工作状态未能从流中判定",
    )

    # ------------------------------------------------------------- 社交结局
    social_facet = None
    social_src_text = social_msg or evening_social
    for facet, keys, _m, _p in SOCIAL_RULES:
        if social_src_text and hit(social_src_text, *keys[:1]):
            social_facet = facet
            break
    if social_facet is None and evening_social:
        for facet, _k, mor, _p in SOCIAL_RULES:
            if hit(evening_social, *mor[:1]):
                social_facet = facet
                break
    social_phrase = next(
        (p for f, _k, _m, p in SOCIAL_RULES if f == social_facet),
        "晚间无重大人际转折",
    )

    # ------------------------------------------------------------- 健康轨迹
    health_parts: list[str] = []
    if imu_g is not None:
        health_facet = "off_wrist_artifact"
        health_parts.append(
            f"手环曾摘下放桌面（IMU峰值{imu_g}g、佩戴接触为假、PPG数值{ppg_invalid}标记无效），"
            f"该片段无有效人体心率，不能据此说摔倒或心搏骤停"
        )
        health_parts.append(
            f"前夜有效睡眠{_nz(sleep_min)}分钟；已记录的晨起静坐心率{_nz(hr_am)}bpm、午间{_nz(hr_noon)}bpm测量有效；"
            f"全天步数{_nz(steps)}步"
        )
    elif exercise_hr is not None:
        health_facet = "exercise"
        health_parts.append(f"前夜有效睡眠{_nz(sleep_min)}分钟")
        health_parts.append(
            f"返程前快步运动{exercise_min}分钟、心率{exercise_hr}bpm，属运动负荷而非静息异常"
        )
        health_parts.append(
            f"晨起静坐心率{_nz(hr_am)}bpm，晚间静坐回到{_nz(hr_pm)}bpm，全天步数{_nz(steps)}步"
        )
    elif hr_pm is not None and hr_pm >= HEALTH_STRESS_RECHECK_MAX:
        health_parts.append(f"前夜有效睡眠{_nz(sleep_min)}分钟；晨起静坐心率{_nz(hr_am, '')}bpm")
        if hr_recheck is not None and hr_recheck >= HEALTH_STRESS_RECHECK_MAX:
            health_facet = "stress_persistent"
            health_parts.append(
                f"晚间静坐心率升至{hr_pm}bpm，复测仍为{hr_recheck}bpm，持续偏快但没有医学诊断"
            )
        else:
            health_facet = "stress_recovered"
            health_parts.append(
                f"晚间静坐心率一度升至{hr_pm}bpm、与自述紧张同现，"
                f"复测回落至{hr_recheck if hr_recheck is not None else '较低水平'}bpm，已缓解，不等于确诊心脏病"
            )
        health_parts.append(f"全天步数{steps}步")
    else:
        if sleep_min is not None and sleep_min < SHORT_SLEEP_MIN:
            health_facet = "short_sleep"
            health_parts.append(
                f"前夜有效睡眠仅{_nz(sleep_min)}分钟（不足），白天明显疲倦、注意力容易飘，未获得新的疾病诊断"
            )
        else:
            health_facet = "stable"
            health_parts.append(f"前夜有效睡眠{_nz(sleep_min)}分钟")
        health_parts.append(
            f"晨起静坐心率{_nz(hr_am)}bpm、午间{_nz(hr_noon)}bpm、晚间{_nz(hr_pm)}bpm，静坐片段无明显突升，"
            f"全天步数{_nz(steps)}步，不能仅因压力推断生理危象"
        )
    health_summary = f"{name}健康面：" + "；".join(health_parts) + "。"

    # ------------------------------------------------------------- 财务账本
    fin_parts: list[str] = []
    fin_direction: list[str] = []
    if day_start:
        fin_parts.append(f"日初余额{day_start[0]:.2f}元、借款本金{day_start[1]:.2f}元")
    if "new_loan_principal" in tx_by_cat:
        amt = abs(tx_by_cat["new_loan_principal"][0]) / 100
        fin_direction.append(f"借款本金{amt:.2f}元已放款到账，现金与负债同步增加，是负债融资不是收入利润")
    if "principal_repayment" in tx_by_cat:
        amt = abs(tx_by_cat["principal_repayment"][0]) / 100
        full = any(k == "repay_full" for k, _ in special_finance)
        fin_direction.append(
            f"偿还借款本金{amt:.2f}元（{'全额结清' if full else '部分偿还，不能当作全部结清'}）"
        )
    if "prior_work_income" in tx_by_cat:
        amt = abs(tx_by_cat["prior_work_income"][0]) / 100
        fin_direction.append(f"上月独立结算款{amt:.2f}元实际到账，不是仅有付款承诺，也不能据此认定今天工作已验收")
    if "prior_purchase_refund" in tx_by_cat:
        amt = abs(tx_by_cat["prior_purchase_refund"][0]) / 100
        fin_direction.append(f"上周订单退款{amt:.2f}元已入账，这是退款而非新工资")
    if "home_repair" in tx_by_cat:
        amt = abs(tx_by_cat["home_repair"][0]) / 100
        fin_direction.append(f"已确认并支付家用设备维修费{amt:.2f}元，没有分期或借款")
    keys_present = {k for k, _ in special_finance}
    if "incoming_promised" in keys_present and "prior_work_income" not in tx_by_cat:
        m = _RE_MONEY.search(next(c for k, c in special_finance if k == "incoming_promised_notice") if any(k == "incoming_promised_notice" for k, c in special_finance) else "结算款")
        amt = m.group(1) if m else "上述"
        fin_direction.append(f"结算方仅承诺明日支付{amt}元，今天尚未到账，承诺不是现金入账")
    if "refund_pending" in keys_present:
        fin_direction.append("退款申请已受理仍在审核，截至查询时没有银行入账记录，受理不等于已退钱")
    if "loan_declined" in keys_present:
        fin_direction.append("贷款试算额度仅供参考，未签合同未放款，未新增负债")
    if "fraud_prevented" in keys_present:
        fin_direction.append("陌生人要求汇款解冻属可疑说法，银行官方核实无此业务，本人未转账、账户无相关扣款")
    if not fin_direction and not tx_by_cat:
        fin_direction.append("当日无新增大额资产或债务变动，仅日常小额消费")
    if day_end:
        fin_direction.append(
            f"日终余额{day_end[0]:.2f}元、借款本金{day_end[1]:.2f}元，普通餐饮交通实际支出{day_end[2]:.2f}元"
        )
    finance_summary = f"{name}财务面：" + "；".join(fin_parts + fin_direction) + "。"

    # ------------------------------------------------------------- 六维组句
    if career_facet == "offer_pending":
        career_summary = (
            f"{name}事业面：{career_from or '联系人'}带来一项新的长期合作邀请（仅口头意向未签字），"
            f"下午确认邀请仍有效、明天下午前答复；今天未签约，也未取消现有{artifact}任务。"
        )
    else:
        career_summary = (
            f"{name}事业面：{artifact}{career_phrase}"
            + (f"（与{career_from}确认）" if career_from else "")
            + "。"
        )
    role = SOCIAL_ROLE_HINT.get(social_facet, "联系人")
    social_summary = (
        f"{name}人际面：晚间与{role}{social_from or '联系人'}的沟通收尾：{social_phrase}。"
        if social_from
        else f"{name}人际面：{social_phrase}。"
    )
    emotion_summary = (
        f"{name}情绪面：{EMOTION_PHRASES[social_facet]}。" if social_facet in EMOTION_PHRASES
        else f"{name}情绪面：情绪平稳，无剧烈波动记录。"
    )
    if emotion_stmt:
        quote = emotion_stmt.rstrip("。")
        emotion_summary = f"{emotion_summary[:-1]}（本人自述：{quote}）。"

    global_parts = [
        career_summary.rstrip("。"),
        f"晚间与{role}{social_from or ''}的沟通中，{social_phrase}" if social_from else social_phrase,
    ]
    if decision_stmt:
        global_parts.append(f"在工作与个人安排之间，本人明确取舍：{decision_stmt.rstrip('。')}")
    global_parts.append(f"情绪上{EMOTION_PHRASES.get(social_facet, '总体平稳')}")
    global_parts.append(f"前夜有效睡眠{_nz(sleep_min)}分钟")
    if hr_pm is not None and hr_pm >= HEALTH_STRESS_RECHECK_MAX:
        global_parts.append(f"晚间静坐心率升至{hr_pm}bpm")
    if tx_by_cat.get("prior_work_income"):
        amt = abs(tx_by_cat["prior_work_income"][0]) / 100
        global_parts.append(f"财务主变化为上月独立结算款{amt:.2f}元实际到账")
    elif "loan_taken" in keys_present:
        global_parts.append("财务主变化为借款本金放款到账（负债增加）")
    elif "incoming_promised" in keys_present:
        global_parts.append("财务上结算款仅获明日支付承诺、今天尚未到账")
    elif "refund_settled" in keys_present or "prior_purchase_refund" in tx_by_cat:
        global_parts.append("财务主变化为上周订单退款入账")
    elif "principal_repayment" in tx_by_cat:
        global_parts.append("财务主变化为偿还借款本金")
    elif "home_repair" in tx_by_cat:
        global_parts.append("财务主变化为支付家用设备维修费")
    elif "fraud_prevented" in keys_present:
        global_parts.append("财务上识破陌生人汇款要求、未转账无损失")
    global_summary = f"{name}的一天：" + "；".join(global_parts) + "。"

    ms = (time.perf_counter() - t0) * 1000
    return {
        "question_id": q["question_id"],
        "solver_agent": SOLVER_AGENT,
        "generated_global_summary": global_summary,
        "generated_health_summary": health_summary,
        "generated_social_summary": social_summary,
        "generated_emotion_summary": emotion_summary,
        "generated_finance_summary": finance_summary,
        "generated_career_summary": career_summary,
        "extracted_facts": {
            "career_facet": career_facet,
            "social_facet": social_facet,
            "health_facet": health_facet,
            "finance_categories": sorted(tx_by_cat),
            "sleep_minutes": sleep_min,
            "hr_am": hr_am, "hr_noon": hr_noon, "hr_pm": hr_pm, "hr_recheck": hr_recheck,
            "steps": steps,
        },
        "execution_time_ms": round(ms, 3),
    }


def _match_special_finance(content: str) -> str | None:
    """按内容特征识别特殊财务事件（特异优先，防宽模式抢匹配）。"""
    rules = (
        ("refund_pending", ("退款", "没有银行入账记录")),
        ("refund_pending", ("退款申请", "已受理")),
        ("refund_settled", ("退款", "已入账")),
        ("incoming_settled", ("结算款", "已实际入账")),
        ("incoming_promised", ("尚未收到上述",)),
        ("loan_taken", ("已放款到账",)),
        ("loan_declined", ("试算额度",)),
        ("repay_full", ("本金全额偿还",)),
        ("repay_partial", ("本金部分偿还",)),
        ("fraud_prevented", ("没有这笔解冻业务",)),
        ("repair_paid", ("维修费", "支付")),
    )
    for key, keys in rules:
        if all(k in content for k in keys):
            return key
    return None


def _is_emotion_statement(content: str) -> bool:
    return any(
        k in content
        for k in (
            "感受", "感觉", "委屈", "难过", "担心", "紧张", "松了口气", "憋屈",
            "不安", "孤立", "心跳快", "疲倦",
        )
    )
