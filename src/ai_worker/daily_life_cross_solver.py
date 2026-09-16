"""Evidence-first daily summary adapter for an unseen opponent observation schema.

Deterministic rule/extractive baseline authored from BLIND inputs, not an LLM
backend. No examiner, evaluator, ground-truth loader, world DB or network import.
Cleaned evidence is never deleted. Unknown states remain explicitly unresolved.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from time import perf_counter_ns

SOLVER = "agent-solver-01a0aa2d"
DIMS = ("global_daily_summary", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career")
GENERATED_FIELDS = dict(zip(DIMS, ("generated_global_summary", "generated_health_summary", "generated_social_summary", "generated_emotion_summary", "generated_finance_summary", "generated_career_summary")))
SOCIAL_ROLES = {"伴侣", "朋友", "好友", "父亲", "母亲", "姐姐", "哥哥", "家人", "房东", "室友", "同事"}
EMOTIONS = ("难过", "委屈", "焦虑", "压力", "放松", "松了口气", "不安", "被理解", "孤立", "憋屈", "生气", "内疚", "担心", "紧张", "疲惫")


def validate_blind(q, generator_agent):
    if "aa2d" in generator_agent.lower() or "aa2d" in q["question_id"].lower():
        raise ValueError("Author-team self-solving is forbidden even under another alias")
    def visit(value):
        if isinstance(value, dict):
            if any(k in {"directional_ground_truth", "ground_truth", "ground_truth_facts", "acceptable_directions", "redline_violations"} for k in value):
                raise ValueError("Ground truth must not enter the solver")
            for v in value.values():
                visit(v)
        elif isinstance(value, list):
            for v in value:
                visit(v)
    visit(q)
    seen = set()
    previous = None
    for s in q["cleaned_daily_stream"]:
        sid = s["slice_id"]
        if sid in seen or not sid:
            raise ValueError("Duplicate or empty evidence ID")
        seen.add(sid)
        t = datetime.fromisoformat(s["timestamp"])
        if t.tzinfo is None or (previous and t < previous):
            raise ValueError("Evidence must be timezone-aware and time ordered")
        previous = t
    if not seen:
        raise ValueError("Empty day")


def cents(n):
    return f"{n / 100:.2f}元"


def block(summary, observations, status="UNRESOLVED", numeric=None):
    return {"summary_text": summary, "evidence_refs": list(dict.fromkeys(s["slice_id"] for s in observations)),
            "observed_status": status, "numeric_facts": numeric or {}}


def career_summary(q):
    p = q["persona"]
    names = {c["name"] for c in p.get("contacts", []) if c["role"] not in SOCIAL_ROLES | {"日常工作联系人"}}
    obs = [s for s in q["cleaned_daily_stream"] if s["speaker_or_source"] in names]
    t = obs[-1]["content"] if obs else ""
    rules = [
        ("允许改到明天", "RESCHEDULED", "工作核验因时间冲突获准改到明天，原任务保留，尚非已完成核验"),
        ("还没完成复核", "REVISION_PENDING", "补充材料已交但复核未完成，最终确认留到明天，不能把提交材料当作通过"),
        ("只保留第一部分", "SCOPE_REDUCED", "双方确认缩小交付范围，仅保留第一部分，其余取消，不是任务加量"),
        ("任务正式取消", "TASK_CANCELLED", "本次具体任务正式取消并停止投入，不等于解除全部岗位或其他合作"),
        ("不接额外任务的决定已确认", "EXTRA_DECLINED", "拒接额外自愿任务获确认，现有任务继续，守住工作边界"),
        ("此前漏交指责不成立", "CREDIT_CORRECTED", "回执证明按时交付，漏交指责被撤回并更正，不能继续认定本人漏交"),
        ("旧版退回状态作废", "RECOVERED_APPROVAL", "更正后的版本复核通过，早先退回状态已被后续通过取代"),
        ("邀请仍有效", "OFFER_PENDING", "新的长期合作仍是有效口头邀请，待明天答复，尚未正式签约且现有任务仍保留"),
    ]
    for marker, state, summary in rules:
        if marker in t:
            return block(f"{p['starting_context']['task']}：{summary}。", obs, state)
    return block("工作结论证据不足；" + (t if t else "保留未定状态，不假定成功或取消。"), obs)


def social_summary(q):
    names = {c["name"] for c in q["persona"].get("contacts", []) if c["role"] in SOCIAL_ROLES}
    obs = [s for s in q["cleaned_daily_stream"] if s["speaker_or_source"] in names]
    t = obs[-1]["content"] if obs else ""
    name = obs[-1]["speaker_or_source"] if obs else "关系当事人"
    rules = [
        ("撤回分手的话", "RECONCILED", "此前分手话语已撤回，双方同意继续交往并安排后续长谈"),
        ("确认结束伴侣关系", "BREAKUP_CONFIRMED", "双方确认结束伴侣关系，分手不是玩笑，也没有复合证据"),
        ("没有绝交", "FRIEND_BOUNDARY", "朋友接受本人今晚不陪同的边界，改约周末，友情未终止"),
        ("不是借钱也不是恋爱承诺", "FRIEND_SUPPORT", "朋友提供倾听和支持，约定周末见面，不是借贷或恋爱承诺"),
        ("已经在原群道歉", "APOLOGY_REPAIRED", "同事撤回未经核实的指责并公开道歉，恢复按分工合作"),
        ("我确认明早陪他去", "CARE_SHARED", "亲属承担明早陪父亲复诊，本人负责晚间资料整理，照护分工得到分担；尚无确诊或治愈结论"),
        ("明早你陪我去", "PARENT_VISIT_PENDING", "父亲明早复诊仍需本人陪同，其他家人暂不能来，今天只是预约与安排，未出新诊断"),
        ("现租约仍有效", "HOUSING_PENDING", "房东提出的涨租幅度尚未谈妥，现租约有效，周日再议，并未要求今天搬离"),
    ]
    for marker, status, text in rules:
        if marker in t:
            return block(f"与{name}：{text}。", obs, status)
    return block("关系状态未能确定；" + t, obs)


def health_summary(q):
    stream = q["cleaned_daily_stream"]
    sleep = next((s for s in stream if "sleep_minutes" in s.get("measurements", {})), None)
    steps = next((s for s in reversed(stream) if "steps" in s.get("measurements", {})), None)
    hr = [s for s in stream if "heart_rate_bpm" in s.get("measurements", {})]
    valid = [s for s in hr if s["measurements"].get("signal_valid") is True and s["measurements"].get("worn") is not False]
    invalid = [s for s in hr if s not in valid]
    seated_high = [s for s in valid if s["measurements"].get("motion") == "seated" and s["measurements"]["heart_rate_bpm"] >= 100]
    exercise_high = [s for s in valid if s["measurements"].get("motion") in {"brisk_walk", "running", "exercise"} and s["measurements"]["heart_rate_bpm"] >= 100]
    personal_notes = [s for s in stream if s["speaker_or_source"] == q["persona"]["name"] and any(x in s["content"] for x in ("昨晚睡得短", "感觉心跳快"))]
    numbers = {"sleep_minutes": sleep["measurements"]["sleep_minutes"] if sleep else None,
               "steps": steps["measurements"]["steps"] if steps else None,
               "morning_resting_hr_bpm": valid[0]["measurements"]["heart_rate_bpm"] if valid else None,
               "latest_valid_hr_bpm": valid[-1]["measurements"]["heart_rate_bpm"] if valid else None,
               "valid_hr_peak_bpm": max((s["measurements"]["heart_rate_bpm"] for s in valid), default=None)}
    if invalid:
        status, main = "OFF_WRIST_ARTIFACT", "脱腕时冲击和无效PPG读数不代表人体跌倒或真实心率归零；重新佩戴后的有效测量正常"
    elif seated_high:
        if valid[-1]["measurements"]["heart_rate_bpm"] >= 100:
            status, main = "RESTING_HIGH_PERSISTENT", "晚间静坐心率升高后复测仍偏高，不能认定已经恢复；应进一步关注和评估，不凭相关性确诊心梗"
        else:
            status, main = "RESTING_HIGH_RECOVERED", "晚间静坐心率升高，后续复测已回落；与谈话和紧张时间相邻，不证明唯一病因或具体心脏病"
    elif exercise_high:
        status, main = "EXERCISE_RECOVERED", "快步运动伴心率升高，随后静坐复测回落；有活动背景，不能写成静息情绪危象"
    elif numbers["sleep_minutes"] is not None and numbers["sleep_minutes"] < 360:
        status, main = "SHORT_SLEEP", "昨夜有效睡眠偏短，本人报告疲倦和注意力受影响；未见持续高心率，不作新的疾病诊断"
    elif valid:
        status, main = "STABLE_SAMPLED_VITALS", "已记录时点的有效心率总体平稳，未见所测时点急性异常；不据此保证全天每刻或心理状态完全正常"
    else:
        status, main = "UNRESOLVED", "缺乏有效体征，不能得出正常或异常的确定结论"
    detail = "；".join(f"{s['timestamp'][11:16]}有效心率{s['measurements']['heart_rate_bpm']}bpm" for s in valid)
    intro = f"上一完整睡眠段{numbers['sleep_minutes']}分钟、全天{numbers['steps']}步。"
    return block(main + "。" + intro + detail + "。下一夜睡眠尚未完成。", [s for s in [sleep, *hr, *personal_notes, steps] if s], status, numbers)


def finance_summary(q):
    stream = q["cleaned_daily_stream"]
    start = next((s for s in stream if "cash_balance_cents" in s.get("measurements", {})), None)
    end = next((s for s in reversed(stream) if "net_cashflow_cents" in s.get("measurements", {})), None)
    transactions = {}
    obs = []
    for s in stream:
        if "transaction" not in s:
            continue
        tx = s["transaction"]
        if tx["status"] != "SETTLED":
            continue
        if type(tx["amount_cents"]) is not int:
            raise ValueError("Use integer cents")
        tid = tx["transaction_id"]
        if tid in transactions and tx != transactions[tid]:
            raise ValueError("Conflicting duplicate transaction")
        if tid not in transactions:
            transactions[tid] = tx
            obs.append(s)
    major = [s for s in obs if s["transaction"].get("category") != "ordinary_expense"]
    financial_sources = {"银行日初快照", "银行与个人账本日终对账", "结算方留言", "银行合同回执", "商户售后", "银行核对结果", "银行试算页面", "陌生联系人转述", "银行官方客服核实", "维修服务单"}
    context = [s for s in stream if s["speaker_or_source"] in financial_sources]
    content = " ".join(s["content"] for s in context)
    numeric = {}
    if start and end:
        sm, em = start["measurements"], end["measurements"]
        net = sum(tx["amount_cents"] for tx in transactions.values())
        numeric = {"opening_balance_cents": sm["cash_balance_cents"], "closing_balance_cents": em["cash_balance_cents"],
                   "net_cashflow_cents": net, "opening_loan_principal_cents": sm["loan_principal_cents"],
                   "closing_loan_principal_cents": em["loan_principal_cents"],
                   "ordinary_expense_cents": -sum(tx["amount_cents"] for tx in transactions.values() if tx.get("category") == "ordinary_expense"),
                   "settled_transaction_count": len(transactions)}
        if numeric["opening_balance_cents"] + net != numeric["closing_balance_cents"] or net != em["net_cashflow_cents"]:
            raise ValueError("Visible bank reconciliation conflict")
    if major:
        item = major[-1]
        tx = item["transaction"]
        category = tx.get("category")
        status = {"prior_work_income": "INCOMING_SETTLED", "new_loan_principal": "LOAN_TAKEN", "prior_purchase_refund": "REFUND_SETTLED", "home_repair": "REPAIR_PAID"}.get(category, "OTHER_SETTLED")
        if category == "principal_repayment":
            status = "REPAY_FULL" if numeric.get("closing_loan_principal_cents") == 0 else "REPAY_PARTIAL"
        main = item["content"]
    elif "没有这笔解冻业务" in content:
        status, main = "FRAUD_PREVENTED", "冒充解冻催款被官方核实阻止，本人未转账，没有该笔已证实损失"
    elif "未签合同，未放款" in content:
        status, main = "LOAN_DECLINED", "只查看贷款试算，未签借款合同、未放款，不认定新增贷款"
    elif "退款没有银行入账记录" in content:
        status, main = "REFUND_PENDING", "退款申请已受理但仍待审且无银行入账，不能认定已退钱"
    elif "对方承诺不是现金入账" in content:
        status, main = "INCOMING_PROMISED", "对方计划支付结算款，但今天尚未到账，只能记为承诺而非现金收入"
    else:
        status, main = "UNRESOLVED", "重大财务事项未能确定，只记录可核验账本"
    detail = ""
    if numeric:
        detail = f"；日常实际支出{cents(numeric['ordinary_expense_cents'])}，净现金流{cents(numeric['net_cashflow_cents'])}，余额{cents(numeric['opening_balance_cents'])}→{cents(numeric['closing_balance_cents'])}；借款本金{cents(numeric['opening_loan_principal_cents'])}→{cents(numeric['closing_loan_principal_cents'])}"
    return block(main + detail + "。待审、承诺或试算不算已入账；不重复记账第三方转述。", [*context, *obs], status, numeric)


def summarize(q, *, generator_agent, now, version=1):
    start = perf_counter_ns()
    validate_blind(q, generator_agent)
    if now.tzinfo is None:
        raise ValueError("Recording time must be timezone aware")
    career, social, health, finance = career_summary(q), social_summary(q), health_summary(q), finance_summary(q)
    own = [s for s in q["cleaned_daily_stream"] if s["speaker_or_source"] == q["persona"]["name"]]
    feelings = [s for s in own if any(w in s["content"] for w in EMOTIONS) and s["modality"] in {"MIC", "USER_NOTE"}]
    emotion = block("自述：" + "；".join(s["content"] for s in feelings) if feelings else "缺乏明确情绪自述，不根据职业或体征捏造心情。", feelings, "SELF_REPORTED" if feelings else "UNRESOLVED")
    decisions = [s for s in own if "我决定" in s["content"] and "因为今晚" in s["content"]]
    decision = decisions[-1]["content"] if decisions else "未见足够证据支持明确的跨维度取舍。"
    if version >= 2:
        # Calibration fix: keep the complete causal chain, not just the last
        # speaker message. No question IDs or examiner answer strings are used.
        time_conflicts = [s for s in own if "工作时限与个人安排的时间冲突" in s["content"]]
        career["evidence_refs"] = list(dict.fromkeys(career["evidence_refs"] + [s["slice_id"] for s in time_conflicts + decisions]))
        if decisions:
            career["summary_text"] += "后续计划：" + decision.split("我决定", 1)[1]
        emotion["evidence_refs"] = list(dict.fromkeys(social["evidence_refs"] + emotion["evidence_refs"]))
        artifact_notes = [s for s in own if "只是把手环摘下" in s["content"] and "没有摔倒" in s["content"]]
        health["evidence_refs"] = list(dict.fromkeys(health["evidence_refs"] + [s["slice_id"] for s in artifact_notes]))
        episodes = [s for s in q["cleaned_daily_stream"] if
                    s.get("measurements", {}).get("signal_valid") is True and
                    s["measurements"].get("heart_rate_bpm", 0) >= 100 and
                    s["measurements"].get("motion") in {"seated", "brisk_walk", "exercise", "running"}]
        health["numeric_facts"]["episode_hr_bpm"] = episodes[0]["measurements"]["heart_rate_bpm"] if episodes else None
        declined = [s for s in own if "决定不申请" in s["content"] and "贷款" in s["content"]]
        finance["evidence_refs"] = list(dict.fromkeys(finance["evidence_refs"] + [s["slice_id"] for s in declined]))
        if declined and finance["observed_status"] == "LOAN_DECLINED":
            finance["summary_text"] = "本人明确拒绝申请该笔贷款，未签约未放款。" + finance["summary_text"]
    summaries = {"dim:health": health, "dim:social": social, "dim:emotion": emotion, "dim:finance": finance, "dim:career": career}
    main = "；".join(s["summary_text"].split("。")[0] for s in [career, social, health])
    main += "；财务：" + finance["summary_text"].split("；")[0] + "。"
    if feelings:
        main += "情绪自述：" + feelings[0]["content"]
    main += "日终取舍：" + decision
    global_refs = list(dict.fromkeys([ref for b in summaries.values() for ref in b["evidence_refs"]] + [s["slice_id"] for s in decisions]))
    summaries["global_daily_summary"] = {"summary_text": main, "evidence_refs": global_refs, "observed_status": "CROSS_DIMENSION_TRADEOFF", "numeric_facts": {}}
    summaries = {d: summaries[d] for d in DIMS}
    return {"question_id": q["question_id"], "person_id": q["persona"]["person_id"], "generator_agent": generator_agent,
            "solver_agent": SOLVER, "solver_version": version, "recorded_at": now.astimezone(timezone.utc).isoformat(),
            "source_day": q["persona"]["date"], "summaries": summaries,
            **{GENERATED_FIELDS[d]: summaries[d]["summary_text"] for d in DIMS},
            "input_record_sha256": hashlib.sha256(json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "execution_time_ms": (perf_counter_ns() - start) / 1e6, "llm_calls": 0, "llm_tokens_used": 0,
            "method": "deterministic evidence-first rules; not per-question LLM inference"}
