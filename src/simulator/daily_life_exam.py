"""Reproducible 10,000-person, one-day directional-summary exam publisher.

Standard-library only. Generates exam evidence and examiner labels together,
then validates structural, temporal, provenance and accounting invariants.
It never calls a solver or grades its own questions. Full and blinded JSONL
archives are streamed with deterministic XZ compression, not held in memory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
import lzma
import hashlib
import io
import json
from pathlib import Path
import random
import re

from simulator.daily_life_catalog import (
    BOOKS, CAREER, CITIES, GIVEN_FIRST, GIVEN_LAST, HOBBIES, ITEMS, JOBS,
    ROUTINES, SOCIAL, SURNAMES, TOPICS, WEATHER,
)

AUTHOR = "daily-examiner-01a0aa30"
VERSION = "1.0.0"
DEFAULT_SEED = 2026091603
DIMENSIONS = ("global_daily_summary", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career")
FINANCE_TYPES = ("repay_full", "repay_partial", "incoming_settled", "incoming_promised",
                 "refund_settled", "refund_pending", "repair_paid", "loan_declined", "loan_taken", "fraud_prevented")
HEALTH_TYPES = ("stress_recovered", "stress_persistent", "exercise", "stable", "off_wrist_artifact", "short_sleep")
TZ = timezone(timedelta(hours=8))
GUIDANCE = (
    "按事实方向、状态、主体、先后关系与证据判断，不要求逐字命中参考摘要或同义词。",
    "红线只在模型肯定了与证据矛盾的命题时触发；引用、否定、假设中的相同词语不构成违规。",
    "可以省略普通日常，不能将转述新闻当作本人经历，也不能把计划、申请或承诺改写为完成。",
)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}元"


def person_name(index):
    index %= len(SURNAMES) * len(GIVEN_FIRST) * len(GIVEN_LAST)
    surname, remainder = divmod(index, len(GIVEN_FIRST) * len(GIVEN_LAST))
    first, last = divmod(remainder, len(GIVEN_LAST))
    return SURNAMES[surname] + GIVEN_FIRST[first] + GIVEN_LAST[last]


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


@contextmanager
def compressed_writer(path):
    """Exclusive create + deterministic XZ; never overwrite a prior exam."""
    with Path(path).open("xb") as raw:
        with lzma.LZMAFile(raw, mode="wb", format=lzma.FORMAT_XZ, preset=6) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="\n") as out:
                yield out


class Day:
    def __init__(self, index, seed):
        self.index = index
        self.rng = random.Random(int.from_bytes(hashlib.sha256(f"{seed}:{index}".encode()).digest()[:8], "big"))
        self.qid = f"DAY_{AUTHOR}_{index + 1:05d}"
        self.day = date(2026, 7, 1) + timedelta(days=self.rng.randrange(77))
        self.start = datetime.combine(self.day, time(), TZ)
        self.name = person_name(index)
        self.lead = person_name(index + 1237)
        self.contact = person_name(index + 6199)
        self.colleague = person_name(index + 9333)
        self.job = JOBS[self.rng.randrange(len(JOBS))]
        self.career = dict(CAREER[self.rng.randrange(len(CAREER))])
        self.social = SOCIAL[self.rng.randrange(len(SOCIAL))]
        if self.career["key"] == "rescheduled" and self.social["key"] == "parent_pending":
            self.career["action"] = "保留已获准的明早核验，再申请改到下午以避开陪诊；第二次改期尚未获批"
        self.health = HEALTH_TYPES[self.rng.randrange(len(HEALTH_TYPES))]
        self.finance = FINANCE_TYPES[self.rng.randrange(len(FINANCE_TYPES))]
        self.events = []
        self.id_pool = self.rng.sample(range(1000, 10000), 240)
        self.ledger = []
        self.start_cash = self.rng.randrange(20000, 65001) * 100
        self.initial_debt = self.rng.randrange(30, 121) * 10000 if self.finance.startswith("repay") else 0
        self.end_debt = self.initial_debt
        self.refs = {}
        self.persona = {
            "person_id": f"PERSON_{index + 1:05d}", "name": self.name, "synthetic": True,
            "age": self.rng.randint(22, 58) if self.job[0] != "研究生" else self.rng.randint(22, 33),
            "gender": self.rng.choice(("女", "男", "未指定")), "occupation": self.job[0],
            "city": self.rng.choice(CITIES), "timezone": "Asia/Shanghai", "date": self.day.isoformat(),
            "day_start": self.start.isoformat(), "day_end_exclusive": (self.start + timedelta(days=1)).isoformat(),
            "day_type": "本人的排班或任务日，不以自然周末推断休假",
            "household_context": self.rng.choice(("独居，家人异地", "与家人同城分住", "与家人同住，个人独立记账", "合租，保留独立个人空间")),
            "interest": self.rng.choice(HOBBIES),
            "contacts": [{"name": self.lead, "role": self.job[3]},
                         {"name": self.contact, "role": self.social["role"]},
                         {"name": self.colleague, "role": "日常工作联系人"}],
            "accounting_scope": "本题给出的人民币活期账户与个人借款本金，账本完整；不推断其他资产或第三人账户",
            "starting_context": {"task": self.job[1], "deliverable": self.job[2],
                                 "cash_balance_cents": self.start_cash, "loan_principal_cents": self.initial_debt},
        }

    def stamp(self, minute):
        return (self.start + timedelta(minutes=minute)).isoformat()

    def render(self, text):
        return text.format(lead=self.lead, work=self.job[2], person=self.contact, task=self.job[1])

    def add(self, minute, modality, text, *, speaker=None, end=None, measurements=None, transaction=None, location=None):
        # Opaque IDs conceal the order in which pivotal/routine events were built.
        ref = f"SL_{self.index + 1:05d}_{self.id_pool[len(self.events)]}"
        event = {"slice_id": ref, "timestamp": self.stamp(minute),
                 "end_timestamp": self.stamp(end if end is not None else minute + 1),
                 "modality": modality, "speaker_or_source": speaker or self.name,
                 "location": location or self.location(minute), "content": text}
        if measurements is not None:
            event["measurements"] = measurements
        if transaction is not None:
            event["transaction"] = transaction
            self.ledger.append({"source_slice_id": ref, **transaction})
        self.events.append(event)
        return ref

    def location(self, minute):
        if minute < 480 or minute >= 1140:
            return "家中"
        if 480 <= minute < 540 or 1080 <= minute < 1140:
            return "通勤路线"
        if 720 <= minute < 780:
            return "午间休息区"
        return self.job[4]

    def transfer(self, minute, signed_cents, category, text):
        return self.add(minute, "APP", text, speaker="个人账户银行已入账回执",
                        transaction={"transaction_id": f"TX_{self.index + 1:05d}_{len(self.ledger) + 1:02d}",
                                     "amount_cents": signed_cents, "currency": "CNY", "status": "SETTLED", "category": category})

    def block(self, intent, claim, words, refs, redline, *, entities=None, slots=None):
        return {
            "semantic_core_anchors": [{"anchor_id": "AN_" + hashlib.sha256(f"{self.qid}:{intent}:{claim}".encode()).hexdigest()[:16],
                "semantic_intent": intent, "core_claim": claim, "acceptable_directions": words,
                "required_entities": entities or [self.name], "evidence_slice_ids": list(dict.fromkeys(refs)),
                "structured_anchors": slots or []}],
            "redline_criteria": [{"contradicted_claim": redline, "severity": "VETO",
                "application_rule": "仅肯定性断言与最终证据相反时触发；不得用禁词或子串匹配",
                "evidence_slice_ids": list(dict.fromkeys(refs))}],
            "grading_notes": list(GUIDANCE),
        }

    @staticmethod
    def slot(field, value, ref):
        return {"field": field, "value": value, "source_slice_id": ref}

    def build_sleep_and_routine(self):
        sleep_minutes = self.rng.randint(270, 325) if self.health == "short_sleep" else self.rng.randint(365, 480)
        awake_minutes = self.rng.randint(10, 35)
        onset = self.start + timedelta(minutes=420 - sleep_minutes - awake_minutes)
        sleep = self.add(0, "SENSOR", f"夜间睡眠监测到晨起结束：有效睡眠{sleep_minutes}分钟，清醒{awake_minutes}分钟；统计窗含前夜入睡部分。",
            speaker="手环睡眠摘要", end=420, location="家中",
            measurements={"sleep_minutes": sleep_minutes, "awake_minutes": awake_minutes,
                          "measurement_start": onset.isoformat(), "measurement_end": self.stamp(420)})
        base = self.rng.randint(58, 79)
        self.refs["sleep"] = sleep
        self.refs["morning_hr"] = self.add(425, "SENSOR", f"晨起静坐心率{base}bpm，测量接触有效，没有运动。",
            speaker="手环PPG摘要", measurements={"heart_rate_bpm": base, "motion": "seated", "signal_valid": True})
        self.refs["day_hr"] = self.add(730 + self.rng.randrange(8), "SENSOR", f"午间静坐片段心率{base + 5}bpm，不能据此声称全天所有时刻均平稳。",
            speaker="手环PPG摘要", measurements={"heart_rate_bpm": base + 5, "motion": "seated", "signal_valid": True})
        self.refs["opening_balance"] = self.add(432, "APP", f"本题账户日初余额{money(self.start_cash)}；个人借款本金{money(self.initial_debt)}。",
            speaker="银行日初快照", measurements={"cash_balance_cents": self.start_cash, "loan_principal_cents": self.initial_debt})
        amounts = [self.rng.choice((800, 1200, 1500, 1800)), self.rng.randrange(18, 46) * 100,
                   self.rng.choice((400, 600, 800, 1200)), self.rng.randrange(16, 43) * 100]
        self.routine_refs = []
        for minute, amount, category in zip((475, 721, 1125, 1152), amounts, ("早餐", "午餐", "交通", "晚餐")):
            self.routine_refs.append(self.transfer(minute, -amount, "ordinary_expense", f"{category}支付成功，扣款{money(amount)}，此条为实际交易而非优惠宣传。"))
        self.routine_cost = sum(amounts)
        self.add(1100, "APP", "包裹已放入自提柜，是上周已付款的订单，今天没有再次扣款。", speaker="快递柜通知")
        self.add(1190, "MIC", "我已取回上周付款的包裹，里面是日用品，不是今天的新购物订单。")
        self.add(780, "APP", "新闻转述：影视剧里的主角被裁员又失恋。此消息不是关于你或你所在单位的通知。", speaker="新闻订阅摘要")
        return base

    def build_finance(self):
        kind = self.finance
        amount = self.rng.randrange(8, 66) * 10000
        related = []
        if kind == "repay_full":
            amount = self.initial_debt
            paid = self.transfer(800, -amount, "principal_repayment", f"个人借款本金全额偿还{money(amount)}，交易成功，未收额外费用。")
            self.end_debt = 0
            claim = f"偿还全部借款本金{money(amount)}，该笔本金余额归零"
            words = ["借款全额结清", "本金已全部归还", "债务本金清零而非新借款"]
            redline = "说还款未完成或本金仍全额未还，或把还款当作收入"
            related = [paid]
        elif kind == "repay_partial":
            amount = self.initial_debt // 2
            paid = self.transfer(800, -amount, "principal_repayment", f"个人借款本金部分偿还{money(amount)}，未收额外费用，不能当作全部结清。")
            self.end_debt = self.initial_debt - amount
            claim = f"实际部分还本{money(amount)}，仍欠本金{money(self.end_debt)}"
            words = ["部分还款仍有余额", "减轻债务但未结清", "本金下降而不是全部归零"]
            redline = "把部分还款说成全额结清，或把本金还款算作借入现金"
            related = [paid]
        elif kind == "incoming_settled":
            related.append(self.add(790, "APP", f"上月另一项已完成事务的结算款{money(amount)}今天安排汇出，与今天的任务不是同一笔。", speaker="结算方留言"))
            related.append(self.transfer(982, amount, "prior_work_income", f"上月独立结算款{money(amount)}已实际入账，不是仅有付款承诺。"))
            claim = f"上月独立结算款{money(amount)}实际到账，不能据此认定今天工作已验收"
            words = ["往期结算款实际到账", "已收到款项而非只有承诺", "收入确认但不代表今日任务完成"]
            redline = "说只是口头承诺尚未到账，或由旧款到账推断今日任务全部验收"
        elif kind == "incoming_promised":
            related.append(self.add(790, "APP", f"上月独立结算款{money(amount)}计划明天转出，今天没有转账回单。", speaker="结算方留言"))
            related.append(self.add(983, "APP", f"已核对银行：今天尚未收到上述{money(amount)}结算款；对方承诺不是现金入账。", speaker="银行核对结果"))
            claim = f"结算方仅承诺明日支付{money(amount)}，今天尚未到账"
            words = ["预期收入未兑现", "付款承诺不能当作入账", "现金流仍等待结算"]
            redline = "把明日承诺金额计为今日实际收入"
        elif kind == "refund_settled":
            related.append(self.add(790, "APP", f"上周订单退款{money(amount)}获批，是否到账以银行为准。", speaker="商户售后"))
            related.append(self.transfer(982, amount, "prior_purchase_refund", f"上周订单退款{money(amount)}已入账，这是退款而非新工资。"))
            claim = f"上周订单退款{money(amount)}已到账，性质为退款而非工资"
            words = ["退货款已回到账户", "退款落地不是新薪酬", "银行确认收回旧支出"]
            redline = "把已到账退款说成尚未申请，或改写成工作奖金"
        elif kind == "refund_pending":
            related.append(self.add(790, "APP", f"上周订单退款申请{money(amount)}已受理，仍在审核；受理不表示已经退钱。", speaker="商户售后"))
            related.append(self.add(982, "APP", f"截至查询时，{money(amount)}退款没有银行入账记录。", speaker="银行核对结果"))
            claim = f"退款{money(amount)}仅受理待审，今天未到账"
            words = ["退款申请未变成现金", "等待审核和到账", "受理状态不能当作完成"]
            redline = "说退款已经到账或已确定为可支配现金"
        elif kind == "repair_paid":
            amount = self.rng.randrange(3, 17) * 10000
            related.append(self.add(790, "APP", f"家用设备维修报价{money(amount)}，你确认后才扣款。", speaker="维修服务单"))
            related.append(self.transfer(982, -amount, "home_repair", f"已确认并支付家用设备维修费{money(amount)}，没有分期或借款。"))
            claim = f"实际支付家用设备维修费{money(amount)}，未因此新增借贷"
            words = ["维修费用已支出", "一次性支出而非贷款", "支付已经完成不是只询价"]
            redline = "把支出当作收入，或凭空增加一笔分期债务"
        elif kind == "loan_declined":
            related.append(self.add(790, "APP", f"贷款试算额度{money(amount)}仅供参考，未签合同，未放款。", speaker="银行试算页面"))
            related.append(self.add(982, "MIC", f"我决定不申请这笔{money(amount)}贷款，试算页面已退出，没有签字。"))
            claim = f"仅试算{money(amount)}后放弃申请，未新增借款或资金到账"
            words = ["没有实际举债", "试算后拒绝贷款", "意向退出而非获得贷款"]
            redline = "把试算额度写成已经新增的借款或资产"
        elif kind == "loan_taken":
            related.append(self.add(790, "APP", f"借款合同已签，本金{money(amount)}；今天无手续费扣款，利息自次日起按合同计提。", speaker="银行合同回执"))
            related.append(self.transfer(982, amount, "new_loan_principal", f"借款本金{money(amount)}已放款到账；这是负债融资，不能算工资或净赚。"))
            self.end_debt = amount
            claim = f"签约并收到借款本金{money(amount)}，现金和负债同步增加，不是收入利润"
            words = ["贷款到账伴随新增负债", "借入资金不是工资收入", "资产现金与债务同时上升"]
            redline = "把贷款算作净赚收入，或称未签约未放款"
        else:
            related.append(self.add(790, "APP", f"陌生人声称要解冻一笔款项，要求先向私人账户汇{money(amount)}；该说法尚未验证。", speaker="陌生联系人转述"))
            related.append(self.add(982, "APP", "银行官方核实：没有这笔解冻业务，不要汇款；本人确认未转账，账户也无相关扣款。", speaker="银行官方客服核实"))
            claim = f"识别要求先汇{money(amount)}的虚假解冻说法并停止操作，没有实际损失或新增贷款"
            words = ["诈骗要求被识别且未转账", "未发生的支出不能入账", "风险被阻断而非资金已被骗走"]
            redline = "把陌生人的声称当作银行事实，或宣称已经损失该笔资金"
        self.refs["finance_story"] = related
        return claim, words, redline, amount

    def build_health(self, base):
        mode = self.health
        peak = self.rng.randint(112, 136)
        if mode in ("stress_recovered", "stress_persistent"):
            episode = self.add(1265, "SENSOR", f"晚间静坐12分钟，心率{peak}bpm，接触信号有效，IMU未见运动；只有关联体征，不能自动诊断心梗。",
                speaker="手环PPG与IMU摘要", end=1277,
                measurements={"heart_rate_bpm": peak, "motion": "seated", "signal_valid": True, "duration_minutes": 12})
            spoken = self.add(1267, "MIC", "谈完今晚的事情我感觉心跳快，觉得紧张；这是我的感受，不是医生诊断。")
            final = base + self.rng.randint(3, 10) if mode == "stress_recovered" else peak - self.rng.randint(1, 5)
            recovery = self.add(1288, "SENSOR", f"再次静坐测得心率{final}bpm，接触有效。", speaker="手环复测",
                measurements={"heart_rate_bpm": final, "motion": "seated", "signal_valid": True})
            if mode == "stress_recovered":
                claim = f"晚间静坐心率升至{peak}bpm，与自述紧张同现；复测回落至{final}bpm，不等于确诊心脏病"
                words = ["晚间短暂静息心率升高后缓解", "紧张与心率波动同现但不能确诊", "异常片段后复测回落"]
                redline = "宣称全天没有心率波动、复测仍维持峰值，或据此确诊心肌梗死"
            else:
                claim = f"晚间静坐心率{peak}bpm，后续仍为{final}bpm，持续偏快但没有医学诊断"
                words = ["静息心率升高未明显恢复", "晚间体征仍需关注", "紧张同现的持续心率偏快而非确诊疾病"]
                redline = "宣称复测已完全正常，或直接诊断为心梗或抑郁症"
            refs = [self.refs["sleep"], self.refs["morning_hr"], self.refs["day_hr"], episode, spoken, recovery]
        elif mode == "exercise":
            peak = self.rng.randint(118, 143)
            episode = self.add(1090, "SENSOR", f"返程前快步运动8分钟，心率{peak}bpm，步频明显增加；不是静坐时的心率变化。",
                speaker="手环PPG与IMU摘要", end=1098,
                measurements={"heart_rate_bpm": peak, "motion": "brisk_walk", "signal_valid": True})
            recovery = self.add(1265, "SENSOR", f"晚间静坐心率{base + 4}bpm，信号有效。", speaker="手环复测",
                measurements={"heart_rate_bpm": base + 4, "motion": "seated", "signal_valid": True})
            claim = f"运动时心率{peak}bpm，晚间静坐回到{base + 4}bpm，不能把运动负荷写成情绪性静息危象"
            words = ["运动性心率升高而非静息异常", "活动后恢复平稳", "生理负荷与情绪诊断必须分开"]
            redline = "把运动中的高心率当作晚间静息心搏骤停或已确诊心脏病"
            refs = [self.refs["sleep"], self.refs["morning_hr"], episode, recovery]
        elif mode == "off_wrist_artifact":
            episode = self.add(1265, "SENSOR", "手环摘下放桌面时IMU峰值6.2g，佩戴接触为假，PPG数值0标记无效；没有有效人体心率为0的证据。",
                speaker="手环脱腕质量日志", measurements={"imu_peak_g": 6.2, "worn": False, "heart_rate_bpm": 0, "signal_valid": False})
            spoken = self.add(1266, "MIC", "我刚刚只是把手环摘下放桌上，没有摔倒，正在正常说话。")
            recovery = self.add(1288, "SENSOR", f"重新佩戴后有效心率{base + 3}bpm。", speaker="手环复测",
                measurements={"heart_rate_bpm": base + 3, "worn": True, "signal_valid": True})
            claim = f"脱腕冲击和无效PPG零值是设备伪迹，重戴后心率{base + 3}bpm，不能判为人体跌倒或心搏骤停"
            words = ["脱腕伪迹被复测澄清", "无效零值不等于心脏停跳", "设备冲击而非已确认人体跌倒"]
            redline = "把脱腕日志当成人体真实跌倒、心搏骤停或已死亡"
            refs = [self.refs["sleep"], self.refs["morning_hr"], episode, spoken, recovery]
            peak = None
        else:
            episode = self.add(1265, "SENSOR", f"晚间静坐测得心率{base + 6}bpm，接触有效；该片段没有明显心率激增。",
                speaker="手环PPG摘要", measurements={"heart_rate_bpm": base + 6, "motion": "seated", "signal_valid": True})
            refs = [self.refs["sleep"], self.refs["morning_hr"], self.refs["day_hr"], episode]
            if mode == "short_sleep":
                refs.append(self.add(1268, "MIC", "昨晚睡得短，今天明显疲倦，注意力容易飘；我没有因此得到任何新的疾病诊断。"))
                claim = "前夜有效睡眠偏短并自述疲倦，已记录的静坐心率片段平稳，不应凭情绪推断严重心律事件"
                words = ["短睡眠后的疲劳", "疲惫并不等于已确诊疾病", "疲劳明显但心率片段未突升"]
            else:
                claim = "晨午晚已记录的静坐心率片段无明显突升，不能仅因关系或工作压力推断生理危象"
                words = ["有心理压力但已测心率相对平稳", "情绪与已测体征不混同", "未见明显异常不等于全天绝对无风险"]
            redline = "凭生活压力捏造125bpm静息峰值、确诊心梗，或把有限片段概括为所有时刻绝对安全"
            peak = None
        sleep_value = next(e["measurements"]["sleep_minutes"] for e in self.events if e["slice_id"] == self.refs["sleep"])
        claim = f"前夜有效睡眠{sleep_value}分钟；" + claim
        slots = [self.slot("morning_heart_rate_bpm", base, self.refs["morning_hr"]),
                 self.slot("sleep_minutes", sleep_value, self.refs["sleep"])]
        if peak is not None:
            slots.append(self.slot("episode_heart_rate_bpm", peak, episode))
        self.refs["health"] = refs
        return self.block("HEALTH_" + mode.upper(), claim, words, refs, redline, slots=slots)

    def fill_routines(self):
        # Sample without replacement: strictly distinct starts and many ordinary
        # observations without 07:00-23:30 holes or hidden importance labels.
        forbidden = set()
        for e in self.events:
            minute = int((datetime.fromisoformat(e["timestamp"]) - self.start).total_seconds() // 60)
            forbidden.update(range(minute - 2, minute + 3))
        available = [minute for minute in range(435, 1410, 4) if minute not in forbidden]
        count = self.rng.randint(128, min(176, len(available)))
        # One observation in each half-hour band bounds gaps even for the
        # sparsest random draw; additional observations supply high density.
        selected = []
        for band in range(435, 1410, 30):
            candidates = [m for m in available if band <= m < band + 30]
            if candidates:
                selected.append(self.rng.choice(candidates))
        remaining = [m for m in available if m not in selected]
        selected += self.rng.sample(remaining, count - len(selected))
        for minute in sorted(selected):
            phase = "morning" if minute < 540 else "lunch" if 720 <= minute < 780 else "commute" if 1080 <= minute < 1140 else "evening" if minute >= 1140 else "work"
            text = self.rng.choice(ROUTINES[phase]).format(
                item=self.rng.choice(ITEMS), book=self.rng.choice(BOOKS), topic=self.rng.choice(TOPICS),
                weather=self.weather, work=self.job[2], task=self.job[1])
            modality = self.rng.choice(("MIC", "APP", "MIC", "APP", "USER_NOTE"))
            speaker = self.name if modality != "APP" else self.rng.choice(("日常消息摘要", "个人备忘录", "已清洗通知摘要"))
            self.add(minute, modality, text, speaker=speaker)

    def build(self):
        self.weather = self.rng.choice(WEATHER)
        base = self.build_sleep_and_routine()
        morning = self.add(610 + self.rng.randrange(30), "MIC", self.render(self.career["morning"]), speaker=self.lead)
        # All personas confront a time/attention conflict, even on a positive day.
        request = self.add(850 + self.rng.randrange(20), "APP", "我今天有工作时限与个人安排的时间冲突，希望明确哪些必须做、哪些可以改期，不想把所有事都拖着。", speaker=self.name)
        afternoon = self.add(930 + self.rng.randrange(30), "APP", self.render(self.career["afternoon"]), speaker=self.lead)
        first_social = self.add(1185, "MIC", self.render(self.social["first"]), speaker=self.contact)
        last_social = self.add(1230 + self.rng.randrange(15), "APP", self.render(self.social["last"]), speaker=self.contact)
        emotion = self.add(1255, "MIC", self.social["emotion"], speaker=self.name)
        finance_claim, finance_words, finance_redline, amount = self.build_finance()
        health_truth = self.build_health(base)
        choice = self.add(1320 + self.rng.randrange(12), "MIC",
            f"因为今晚需要{self.social['constraint']}，而工作也不能没有交代，我决定{self.career['action']}；这是接下来的安排，不是说所有待办已经完成。")
        # Actual daily totals are known from the complete scoped ledger, never
        # from a promise, credit limit, unverified chat or nominal loan profit.
        final_cash = self.start_cash + sum(t["amount_cents"] for t in self.ledger)
        net_cashflow = final_cash - self.start_cash
        close = self.add(1405, "APP",
            f"日终核对本题完整账户：余额{money(final_cash)}，借款本金{money(self.end_debt)}；普通餐饮交通实际支出{money(self.routine_cost)}。所有实际交易已列出，待审、承诺、试算金额均未入账，23:25至日界无额外交易。",
            speaker="银行与个人账本日终对账", end=1440,
            measurements={"cash_balance_cents": final_cash, "loan_principal_cents": self.end_debt,
                          "ordinary_expense_cents": self.routine_cost, "net_cashflow_cents": net_cashflow,
                          "reconciled_through": self.stamp(1440)})
        steps = self.rng.randint(2600, 11900)
        step_ref = self.add(1408, "SENSOR", f"全天步数{steps}步；之后到日界未新增计步。步数不能独立证明做过特定运动或发生了跌倒。",
            speaker="手环日界宏观摘要", end=1440, measurements={"steps": steps, "coverage_start": self.stamp(0), "coverage_end": self.stamp(1440)})
        self.add(1410, "SENSOR", "23:30上床准备休息；到24:00没有新增可辨识语音、消息或交易。仅记录安静休息，尚不能判断下一夜睡眠总时长。",
            speaker="手环日界摘要", end=1440, location="家中", measurements={"motion": "resting", "next_night_sleep_minutes": None})
        pivotal_count = len(self.events)
        self.fill_routines()
        ordinary_count = len(self.events) - pivotal_count
        self.events.sort(key=lambda e: (e["timestamp"], e["slice_id"]))
        career_claim = self.render(self.career["claim"])
        social_claim = self.render(self.social["claim"])
        social_truth = self.block(self.social["intent"], social_claim, self.social["directions"],
            [first_social, last_social], self.social["redline"], entities=[self.name, self.contact])
        career_truth = self.block(self.career["intent"], career_claim + "；最终个人安排为" + self.career["action"],
            self.career["directions"], [morning, request, afternoon, choice], self.career["redline"], entities=[self.name, self.lead])
        emotion_truth = self.block("EMOTION_" + self.social["key"].upper(), self.social["emotion_claim"],
            self.social["emotion_words"], [first_social, last_social, emotion],
            "把有时间变化的自述情绪写成全天完全相反的情绪，或从这些语句直接确诊精神疾病")
        finance_refs = [self.refs["opening_balance"], *self.refs["finance_story"], *self.routine_refs, close]
        finance_truth = self.block("FINANCE_" + self.finance.upper(),
            finance_claim + f"；普通消费{money(self.routine_cost)}，日终余额{money(final_cash)}，本金负债{money(self.end_debt)}",
            finance_words, finance_refs, finance_redline,
            slots=[self.slot("day_end_cash_balance_cents", final_cash, close),
                   self.slot("day_end_loan_principal_cents", self.end_debt, close),
                   self.slot("ordinary_expense_cents", self.routine_cost, close)])
        health_truth["semantic_core_anchors"][0]["evidence_slice_ids"].append(step_ref)
        health_truth["semantic_core_anchors"][0]["structured_anchors"].append(self.slot("steps", steps, step_ref))
        main = (f"白天{career_claim}；晚间{social_claim}。在工作时限与个人关系或照护安排之间，"
                f"本人明确选择{self.career['action']}，以便{self.social['constraint']}。"
                f"情绪表现为{self.social['emotion_claim']}；{health_truth['semantic_core_anchors'][0]['core_claim']}。"
                f"财务主变化为{finance_claim}。")
        global_truth = self.block("CROSS_DIMENSION_DAILY_ARC", main,
            [f"同时抓住‘{career_claim}’与‘{social_claim}’并说明时间取舍",
             f"围绕工作最终状态、人际转折和‘{self.career['action']}’组织主线",
             "可先讲人际或健康，再回溯工作，但必须保留最终状态、现金事实和明确的行动取舍"],
            [morning, afternoon, first_social, last_social, emotion, *self.refs["health"], *self.refs["finance_story"], close, choice],
            "将关键事项的最终状态翻转、将别人的新闻当作本人经历，或把待办全部改写为已经完成",
            entities=[self.name, self.lead, self.contact])
        global_truth["causal_constraints"] = [
            {"relation": "EXPLICIT_SELF_ATTRIBUTION", "claim": f"本人说明为了{self.social['constraint']}而选择{self.career['action']}",
             "cause_evidence_slice_ids": [last_social], "effect_evidence_slice_ids": [choice]},
            {"relation": "TEMPORAL_ASSOCIATION_NOT_DIAGNOSIS", "claim": "关系变化、自述情绪和体征各有来源，不得把同日先后强行升级成医学因果或确诊",
             "cause_evidence_slice_ids": [emotion], "effect_evidence_slice_ids": self.refs["health"]},
        ]
        truth = dict(zip(DIMENSIONS, (global_truth, health_truth, social_truth, emotion_truth, finance_truth, career_truth)))
        record = {"question_id": self.qid, "persona": self.persona, "cleaned_daily_stream": self.events,
                  "directional_ground_truth": truth}
        audit = {"career": self.career["key"], "social": self.social["key"], "health": self.health, "finance": self.finance,
                 "ordinary_slices": ordinary_count, "signature": "|".join((self.career["key"], self.social["key"], self.health, self.finance)),
                 "intended_finance_amount_cents": amount}
        return record, audit


def generate_question(index, seed=DEFAULT_SEED):
    require(0 <= index < 10000, "person index must be in [0, 10000)")
    return Day(index, seed).build()


def validate_question(q):
    """Fail-closed publication invariants, not an answer-generating solver."""
    require(set(q) == {"question_id", "persona", "cleaned_daily_stream", "directional_ground_truth"}, "four required top-level fields")
    p, stream, truth = q["persona"], q["cleaned_daily_stream"], q["directional_ground_truth"]
    require(p["synthetic"] is True, "synthetic disclosure required")
    require(set(truth) == set(DIMENSIONS), "six complete dimensions required")
    start, end = datetime.fromisoformat(p["day_start"]), datetime.fromisoformat(p["day_end_exclusive"])
    require(end - start == timedelta(hours=24), "24h coverage required")
    require(start.tzinfo is not None and start.hour == start.minute == 0, "aware midnight start")
    require(p["date"] == start.date().isoformat(), "persona date mismatch")
    require(140 <= len(stream) <= 230, "daily density out of bounds")
    by_id = {e["slice_id"]: e for e in stream}
    require(len(by_id) == len(stream), "duplicate slice ID")
    require({"MIC", "APP", "SENSOR"} <= {e["modality"] for e in stream}, "required modalities missing")
    require([e["timestamp"] for e in stream] == sorted(e["timestamp"] for e in stream), "timestamps must be sorted")
    for e in stream:
        at, until = datetime.fromisoformat(e["timestamp"]), datetime.fromisoformat(e["end_timestamp"])
        require(start <= at < until <= end, "out-of-day or nonpositive slice")
        require(e["modality"] in ("MIC", "APP", "SENSOR", "USER_NOTE"), "unknown modality")
        require(bool(e["content"]) and bool(e["speaker_or_source"]), "empty evidence")
        require(not ({"importance", "scenario_id", "semantic_intent", "ground_truth", "is_core"} & set(e)), "answer leakage in stream")
    require(stream[0]["timestamp"] == p["day_start"], "missing midnight prefix")
    require(stream[0]["end_timestamp"] == (start + timedelta(hours=7)).isoformat(), "missing overnight summary")
    require(stream[-1]["timestamp"] == (start + timedelta(hours=23, minutes=30)).isoformat(), "missing 23:30 endpoint")
    require(stream[-1]["end_timestamp"] == p["day_end_exclusive"], "missing day tail")
    slots = [int((datetime.fromisoformat(e["timestamp"]) - start).total_seconds() // 60) for e in stream if datetime.fromisoformat(e["timestamp"]).hour >= 7]
    require(max(b - a for a, b in zip(slots, slots[1:])) <= 65, "unexplained daytime gap exceeds 65 minutes")
    anchor_ids = set()
    for dim, block in truth.items():
        require(bool(block["semantic_core_anchors"]) and bool(block["redline_criteria"]), "empty labels")
        for anchor in block["semantic_core_anchors"]:
            require(anchor["anchor_id"] not in anchor_ids, "duplicate anchor ID")
            anchor_ids.add(anchor["anchor_id"])
            require(bool(anchor["core_claim"]) and len(set(anchor["acceptable_directions"])) >= 3, "missing directional alternatives")
            refs = anchor["evidence_slice_ids"]
            require(bool(refs) and set(refs) <= by_id.keys(), "unresolvable anchor evidence")
            entity_corpus = encode(p) + "".join(encode(by_id[r]) for r in refs)
            require(all(entity in entity_corpus for entity in anchor["required_entities"]), "entity absent from input evidence")
            for value in anchor["structured_anchors"]:
                require(value["source_slice_id"] in refs, "structured slot lacks anchor evidence")
                source = by_id[value["source_slice_id"]]
                require(value["value"] in source.get("measurements", {}).values(), "structured anchor fabricated or not directly evidenced")
        for red in block["redline_criteria"]:
            require(red["severity"] == "VETO" and red["contradicted_claim"], "invalid redline")
            require(set(red["evidence_slice_ids"]) <= by_id.keys(), "redline evidence missing")
            require("否定" in "".join(block["grading_notes"]), "semantic polarity instruction missing")
    for link in truth["global_daily_summary"]["causal_constraints"]:
        require(set(link["cause_evidence_slice_ids"] + link["effect_evidence_slice_ids"]) <= by_id.keys(), "causal link evidence missing")
        if link["relation"] == "EXPLICIT_SELF_ATTRIBUTION":
            cause_last = max(by_id[r]["timestamp"] for r in link["cause_evidence_slice_ids"])
            effect_first = min(by_id[r]["timestamp"] for r in link["effect_evidence_slice_ids"])
            require(cause_last < effect_first, "causal arrow points backward in time")
    tx = [e["transaction"] for e in stream if "transaction" in e]
    require(len({t["transaction_id"] for t in tx}) == len(tx), "duplicate transaction")
    require(all(t["status"] == "SETTLED" and t["currency"] == "CNY" and isinstance(t["amount_cents"], int) for t in tx), "nonfinal or invalid cash entry")
    closing = next(e["measurements"] for e in stream if "reconciled_through" in e.get("measurements", {}))
    require(p["starting_context"]["cash_balance_cents"] + sum(t["amount_cents"] for t in tx) == closing["cash_balance_cents"], "cash ledger does not reconcile")
    debt = p["starting_context"]["loan_principal_cents"] + sum(t["amount_cents"] for t in tx if t["category"] in ("principal_repayment", "new_loan_principal"))
    require(debt == closing["loan_principal_cents"] and debt >= 0, "loan principal does not reconcile")
    require(-sum(t["amount_cents"] for t in tx if t["category"] == "ordinary_expense") == closing["ordinary_expense_cents"], "routine expenses mismatch")
    require(sum(t["amount_cents"] for t in tx) == closing["net_cashflow_cents"], "cashflow mismatch")
    return {"slices": len(stream), "transactions": len(tx), "anchors": len(anchor_ids)}


def publish(output, count=10000, seed=DEFAULT_SEED):
    require(1 <= count <= 10000, "count must be 1..10000")
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    totals = Counter()
    facets = {k: Counter() for k in ("career", "social", "health", "finance", "occupation", "city", "modalities")}
    signatures, names, ids, content_hashes, masked_hashes = set(), set(), set(), set(), set()
    minimum, maximum = 10**9, 0
    full_path = out / "exams_10000_people.jsonl.xz"
    blind_path = out / "questions_10000_people.blind.jsonl.xz"
    truth_path = out / "ground_truth_10000_people.jsonl.xz"
    with compressed_writer(full_path) as full, compressed_writer(blind_path) as blind, compressed_writer(truth_path) as labels:
        for index in range(count):
            q, audit = generate_question(index, seed)
            result = validate_question(q)
            require(q["persona"]["name"] not in names and q["question_id"] not in ids, "duplicate person/question")
            names.add(q["persona"]["name"])
            ids.add(q["question_id"])
            # Content uniqueness is checked without slice IDs or timestamps.
            content_hashes.add(hashlib.sha256(encode([e["content"] for e in q["cleaned_daily_stream"]]).encode()).hexdigest())
            masked_text = encode([e["content"] for e in q["cleaned_daily_stream"]])
            for name in [q["persona"]["name"]] + [c["name"] for c in q["persona"]["contacts"]]:
                masked_text = masked_text.replace(name, "人物")
            masked_text = re.sub(r"\d+(?:\.\d+)?", "数值", masked_text)
            masked_hashes.add(hashlib.sha256(masked_text.encode()).hexdigest())
            full.write(encode(q) + "\n")
            blind.write(encode({k: v for k, v in q.items() if k != "directional_ground_truth"}) + "\n")
            labels.write(encode({"question_id": q["question_id"], "directional_ground_truth": q["directional_ground_truth"]}) + "\n")
            totals.update(result)
            totals["ordinary_slices"] += audit["ordinary_slices"]
            minimum, maximum = min(minimum, result["slices"]), max(maximum, result["slices"])
            for key in ("career", "social", "health", "finance"):
                facets[key][audit[key]] += 1
            facets["occupation"][q["persona"]["occupation"]] += 1
            facets["city"][q["persona"]["city"]] += 1
            facets["modalities"].update(e["modality"] for e in q["cleaned_daily_stream"])
            signatures.add(audit["signature"])
            if index == 0:
                (out / "example_person_00001.json").write_text(json.dumps(q, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    require(len(content_hashes) == count, "content duplicates after removing IDs and time")
    require(len(masked_hashes) == count, "duplicate streams after masking names and numbers")
    code_files = [Path(__file__), Path(__file__).with_name("daily_life_catalog.py")]
    manifest = {"schema_version": VERSION, "generator_agent": AUTHOR, "synthetic": True, "seed": seed,
        "person_count": count, "question_count": count, "unique_names": len(names), "unique_content_streams": len(content_hashes),
        "unique_streams_after_masking_names_and_numbers": len(masked_hashes),
        "distinct_outcome_combinations": len(signatures), "outcome_combination_space": len(CAREER) * len(SOCIAL) * len(HEALTH_TYPES) * len(FINANCE_TYPES),
        "totals": dict(totals), "minimum_slices": minimum, "maximum_slices": maximum,
        "coverage": "24h per person; overnight 00:00–07:00, dense daytime, tail 23:30–24:00",
        "dimensions": list(DIMENSIONS), "facets": {k: dict(v) for k, v in facets.items()},
        "format": "UTF-8 JSON Lines compressed with XZ; each full line is one standard JSON object with the four requested fields",
        "validation": "structural/time/provenance/accounting invariants only; no solver or self-scoring",
        "generation_limits": "Template-composed fictional lives, not collected real people and not 10,000 independent hand-written plots. Numeric, persona, temporal, dialogue and outcome combinations vary.",
        "code_sha256": {p.name: sha_file(p) for p in code_files},
        "artifacts": {p.name: {"sha256": sha_file(p), "bytes": p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate_archive(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, artifact in manifest["artifacts"].items():
        require(Path(name).name == name, "unsafe artifact path")
        require(sha_file(directory / name) == artifact["sha256"], "artifact hash mismatch")
    totals, person_ids, names, qids = Counter(), set(), set(), set()
    with lzma.open(directory / "exams_10000_people.jsonl.xz", "rt", encoding="utf-8") as full, \
         lzma.open(directory / "questions_10000_people.blind.jsonl.xz", "rt", encoding="utf-8") as blind, \
         lzma.open(directory / "ground_truth_10000_people.jsonl.xz", "rt", encoding="utf-8") as labels:
        for line in full:
            q = json.loads(line)
            totals.update(validate_question(q))
            require(q["question_id"] not in qids and q["persona"]["person_id"] not in person_ids and q["persona"]["name"] not in names, "duplicate person")
            qids.add(q["question_id"])
            person_ids.add(q["persona"]["person_id"])
            names.add(q["persona"]["name"])
            bline, gline = blind.readline(), labels.readline()
            require(bool(bline) and bool(gline), "truncated sidecar")
            b, g = json.loads(bline), json.loads(gline)
            require(b == {k: v for k, v in q.items() if k != "directional_ground_truth"}, "blind stream differs or contains answer leakage")
            require(g == {"question_id": q["question_id"], "directional_ground_truth": q["directional_ground_truth"]}, "ground truth differs")
        require(not blind.readline() and not labels.readline(), "extra sidecar rows")
    require(len(qids) == manifest["question_count"] == manifest["person_count"], "count mismatch")
    require(all(manifest["totals"][key] == value for key, value in totals.items()), "aggregate mismatch")
    return {"verdict": "PASS", "questions": len(qids), "distinct_people": len(person_ids), "totals": dict(totals),
            "checked": ["XZ integrity", "SHA-256", "exact blind/answer separation", "six dimensions", "evidence references", "24h timestamps", "cash and debt reconciliation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("generate")
    generate.add_argument("--output", required=True)
    generate.add_argument("--count", type=int, default=10000)
    generate.add_argument("--seed", type=int, default=DEFAULT_SEED)
    validate = sub.add_parser("validate")
    validate.add_argument("directory")
    args = parser.parse_args()
    result = publish(args.output, args.count, args.seed) if args.command == "generate" else validate_archive(args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
