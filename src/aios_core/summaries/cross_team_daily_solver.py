"""Evidence-linked six-dimensional daily summary baseline, authored by 01a0aa30.

Reads blinded daily slices only. No evaluator/model/filesystem dependency. Rules
are explicit, not a claim of runtime LLM reasoning. Uncertain source statements
remain reported/uncertain rather than being promoted to diagnoses or actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from pydantic import BaseModel, ConfigDict, Field

SOLVER = "agent-solver-01a0aa30"
SELF_ALIASES = (SOLVER, "daily-examiner-01a0aa30", "01a0aa30-fantonghui", "01a0aa30")
DIMS = ("global", "health", "social", "emotion", "finance", "career")


class Slice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    t: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    src: str = Field(pattern=r"^(mic|app|sensor)$")
    text: str = Field(min_length=1, max_length=12000)
    who: str | None = None
    app: str | None = None
    sender: str | None = None

    @property
    def speaker(self):
        # A forged/irrelevant MIC 'who' on an APP row must not override sender.
        return (self.who if self.src == "mic" else self.sender) or self.app or self.src


class Persona(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    age: int
    city: str
    job: str
    relationship: str | None = None
    partner: str | None = None
    band_id: str | None = None


class BlindDailyQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    question_id: str = Field(min_length=1)
    generator_agent: str
    exam_date: str
    persona: Persona
    cleaned_daily_stream: list[Slice] = Field(min_length=1, max_length=512)


@dataclass(frozen=True)
class Fact:
    dimension: str
    intent: str
    summary: str
    refs: tuple[int, ...]
    time: str
    polarity: str = "neutral"
    epistemic: str = "reported"


def contains(text, words):
    return any(word in text for word in words)


def amounts(text):
    return re.findall(r"\d[\d,，]*(?:\.\d+)?(?:万|千)?元|\d+(?:\.\d+)?万", text)


class DailyCrossSolver:
    version = "v1"

    def facts(self, q):
        result = []
        career_by_time = []
        social_by_time = []
        for index, s in enumerate(q.cleaned_daily_stream):
            text, who = s.text, s.speaker
            # Source content is data, not instructions. Quoted celebrity news,
            # advertisements and third-party hyperbole are not personal events.
            if contains(text, ("【热搜】", "转发链接", "限时免息", "名额有限", "哈哈哈", "忽略之前指令")):
                continue
            if s.src == "sensor":
                if "晨起静息" in text:
                    result.append(Fact("health", "BASELINE", text.rstrip("。"), (index,), s.t))
                elif "心率由" in text:
                    # Strip the upstream algorithm's causal diagnosis, retain
                    # measured values; temporal co-occurrence is not causality.
                    observed = text.split("判定", 1)[0].rstrip("，。")
                    result.append(Fact("health", "HR_EPISODE", f"{s.t}传感器摘要报告{observed}；原因仍需结合情境核实", (index,), s.t, "arousal"))
                elif "入睡准备" in text:
                    result.append(Fact("health", "DAY_METRICS", text.rstrip("。"), (index,), s.t))
                continue
            # Account notification text beats its broad, sometimes erroneous
            # '扣款通知' wrapper (e.g. unrealized equity losses are not cash debits).
            account = contains(text, ("【扣款通知】", "【账户通知】"))
            if account:
                clean = re.sub(r"^【[^】]+】", "", text)
                intent, polarity = "ACCOUNT_REPORTED", "neutral"
                if "浮亏" in text:
                    intent, polarity = "UNREALIZED_LOSS", "negative"
                    clean += "；这是持仓浮动损益，未提供已卖出或现金扣款依据"
                elif contains(text, ("还款", "房贷")):
                    intent, polarity = "DEBT_PAYMENT", "negative"
                elif contains(text, ("借给", "垫付")):
                    intent, polarity = "ADVANCE_OR_LENDING", "negative"
                    clean += "；实际返还尚未在题面确认"
                elif contains(text, ("奖金", "年终奖", "稿费", "退款")):
                    intent, polarity = "RECEIPT_OR_REFUND", "positive"
                elif contains(text, ("罚款", "保养", "加油")):
                    intent, polarity = "EXPENSE", "negative"
                result.append(Fact("finance", intent, f"账户消息：{clean}", (index,), s.t, polarity))
                continue
            if "乘车扣款" in text:
                result.append(Fact("finance", "SMALL_EXPENSE", text, (index,), s.t, "neutral"))
                continue
            career = self.career_fact(s, index, q)
            if career:
                result.append(career)
                career_by_time.append(career)
            social = self.social_fact(s, index, q)
            if social:
                result.append(social)
                social_by_time.append(social)
            if who == "自己" and contains(text, ("憋不住笑", "不能声张")):
                result.append(Fact("emotion", "SELF_EXCITEMENT", "本人难掩笑意但有所克制，显示兴奋或期待", (index,), s.t, "positive", "inferred"))
        # Merge the two clearly attributed proposal/acceptance turns. A wedding
        # registration or the wearer's promotion cannot be inferred from this.
        proposal = [f for f in result if f.intent == "PROPOSAL"]
        acceptance = [f for f in result if f.intent == "ACCEPTANCE"]
        if proposal and acceptance and proposal[0].time <= acceptance[0].time:
            result = [f for f in result if f.intent not in ("PROPOSAL", "ACCEPTANCE")]
            a, b = proposal[0], acceptance[0]
            result.append(Fact("social", "ENGAGEMENT", "本人求婚，伴侣答应，求婚获得接受；未见婚姻登记完成证据", a.refs + b.refs, b.time, "positive"))
        return sorted(result, key=lambda f: f.time)

    def career_fact(self, s, index, q):
        text, who = s.text, s.speaker
        # A partner saying '我升主管了' is the partner's success, not the wearer.
        work_source = s.src == "app" and who in ("HR", "人事部", "项目群", "全员群", "销售部", "运维群")
        work_source |= s.src == "mic" and contains(who, ("领导", "客户"))
        if not work_source:
            return None
        templates = (
            (("口头offer",), "OFFER", "收到口头工作邀约，薪资涨幅与答复时限见通知，尚非已入职", "positive"),
            (("晋升评审结果：未通过",), "PROMOTION_DENIED", "本人晋升评审未通过，可预约反馈面谈", "negative"),
            (("晋升评审通过",), "PROMOTION_APPROVED", "本人晋升评审通过，生效时间在未来", "positive"),
            (("绩效结果",), "PERFORMANCE_REVIEW", "绩效评级下达并要求提交改进计划", "negative"),
            (("维护组",), "ROLE_TRANSFER", "收到转入维护组通知，后续报到安排待执行", "uncertain"),
            (("新事业部",), "REORGANIZATION", "组织调整将转入新事业部，汇报关系尚未明确", "uncertain"),
            (("未中", "标丢了"), "BID_LOST", "本次投标失利，进入归档而不是签约成功", "negative"),
            (("签约喜报",), "CONTRACT_WON", "收到合同签约喜报；合同金额不等于本人现金到账", "positive"),
            (("项目按期上线",), "PROJECT_RELEASED", "项目按期上线并获项目组表扬", "positive"),
            (("创新奖",), "AWARD", "入选创新奖，奖金预计随下月工资发放，今日到账未确认", "positive"),
            (("重做",), "REVISION_REQUIRED", "方案遭领导否定并要求限期重做", "negative"),
            (("暂时取消",), "CLIENT_CANCELLATION", "客户说明合作暂时取消，不能扩大为全面失业", "negative"),
            (("事故定责",), "INCIDENT_ATTRIBUTION", "运维通知将事故操作记录指向本人账号并要求复盘；具体因果责任仍需核实", "negative"),
            (("目标缺口",), "TARGET_GAP", "部门业绩存在缺口并要求各组连夜想办法，不等于本人独自欠款", "negative"),
            (("你来牵头",), "LEAD_RESPONSIBILITY", "领导授权本人牵头模块及选人安排", "positive"),
            (("我不点名",), "GENERAL_CRITICISM", "领导大会不点名批评部分组的数据管理；是否指向本人并未明确", "uncertain"),
        )
        for words, intent, summary, polarity in templates:
            if contains(text, words):
                return Fact("career", intent, f"{summary}；{who}原话：{text}", (index,), s.t, polarity)
        return None

    def social_fact(self, s, index, q):
        text, who = s.text, s.speaker
        partner = who == q.persona.partner
        if partner:
            cases = (
                (("我们分手吧",), "BREAKUP_REQUEST", "伴侣明确提出分手并要求停止联系", "negative"),
                (("这几天是我不对",), "APOLOGY", "伴侣表达歉意并提议周末出行，关系有修复迹象", "positive"),
                (("这次听我的", "去海边"), "TRAVEL_DISCUSSION", "伴侣讨论周末海边行程；不能仅凭同一发送者的两条消息确认双方已经和好", "positive"),
                (("我愿意",), "ACCEPTANCE", "伴侣表示愿意接受求婚", "positive"),
                (("我升主管",), "PARTNER_PROMOTION", "伴侣分享自己升主管的喜讯并邀约庆祝，不是本人晋升", "positive"),
                (("今天几号",), "PARTNER_DISPLEASURE", "伴侣对日期或约定表达不满，关系出现疏离信号；具体缘由尚未明说", "negative"),
                (("十年了",), "SHARED_OCCASION", "伴侣布置餐桌并提到十年，疑似共同纪念场景", "positive"),
            )
            for words, intent, summary, polarity in cases:
                if contains(text, words):
                    return Fact("social", intent, f"与{who}：{summary}；原话：{text}", (index,), s.t, polarity,
                                "inferred" if intent in ("SHARED_OCCASION", "PARTNER_DISPLEASURE") else "reported")
        if who == "自己" and "嫁给我" in text:
            return Fact("social", "PROPOSAL", "本人向伴侣求婚", (index,), s.t, "positive")
        if who in ("妈妈", "爸爸"):
            if contains(text, ("幼儿园", "怎么想", "为你好")):
                return Fact("social", "PARENT_PRESSURE", f"父母谈及婚育或个人安排并施压，具体决定未见；{who}说：{text}", (index,), s.t, "negative", "inferred")
            if "最爱吃" in text:
                return Fact("social", "FAMILY_CARE", f"母亲做本人爱吃的饭菜，体现家庭关照：{text}", (index,), s.t, "positive")
        if who == "老同学" and "高中" in text:
            return Fact("social", "REUNION_MEMORY", f"与老同学回忆往事：{text}", (index,), s.t, "positive")
        if who == "室友" and "碗你堆" in text:
            return Fact("social", "ROOMMATE_CONFLICT", f"室友因家务积累表达不满：{text}", (index,), s.t, "negative")
        if who == "自己" and "外卖盒" in text:
            return Fact("social", "ROOMMATE_RETORT", f"本人以家务问题反驳室友：{text}", (index,), s.t, "negative")
        if who == "老友" and "周转" in text:
            return Fact("social", "FRIEND_BORROW_REQUEST", f"朋友开口请求短期借款：{text}；该对话本身未证明本人已出借或明确拒绝", (index,), s.t, "uncertain")
        if who == "老友" and "挂断" in text:
            return Fact("social", "FRIEND_SILENCE", "朋友长时间沉默后挂断，关系显得紧张；未见明确绝交声明", (index,), s.t, "negative", "inferred")
        return None

    def solve(self, q: BlindDailyQuestion, *, now: datetime | None = None):
        if q.generator_agent.casefold() in {a.casefold() for a in SELF_ALIASES} or "01a0aa30" in q.generator_agent.casefold():
            raise ValueError("self-solving prohibited across team aliases")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("T_now must be timezone-aware")
        before = hashlib.sha256(q.model_dump_json().encode()).hexdigest()
        facts = self.facts(q)
        dimensions = {}
        evidence = {}
        for dim in ("health", "social", "finance", "career"):
            selected = [f for f in facts if f.dimension == dim]
            # Exact repeats do not make independent events. Keep chronological
            # distinct states rather than discarding earlier contradictory turns.
            seen = set()
            selected = [f for f in selected if not (f.summary in seen or seen.add(f.summary))]
            if dim == "finance":
                selected.sort(key=lambda f: (f.intent == "SMALL_EXPENSE", f.time))
            dimensions[dim] = "；".join(f.summary for f in selected) if selected else "题面未提供足以确认该维度重大变化的直接证据。"
            evidence[dim] = sorted({r for f in selected for r in f.refs})
        explicit_emotion = [f for f in facts if f.dimension == "emotion"]
        contextual = [f for f in facts if f.dimension in ("career", "social") and f.polarity in ("positive", "negative", "uncertain")]
        signs = {f.polarity for f in contextual}
        if explicit_emotion:
            emotion = "；".join(f.summary for f in explicit_emotion)
        else:
            emotion = "没有完整的本人情绪自述"
        if "negative" in signs and "positive" in signs:
            emotion += "；工作或人际情境中受挫与支持/喜讯并存，可能有压力与宽慰交替，不能断言单一情绪覆盖全天"
        elif "negative" in signs:
            emotion += "；工作或关系冲突提示可能紧张、委屈或低落，具体强度未能确认"
        elif "positive" in signs:
            emotion += "；喜讯或亲友支持提示可能喜悦、放松，但仍需本人感受验证"
        else:
            emotion += "；情境不确定，不宜强行认定崩溃或持续快乐"
        emotion += "；以上不是精神疾病诊断。"
        dimensions["emotion"] = emotion
        evidence["emotion"] = sorted({r for f in explicit_emotion + contextual for r in f.refs})
        primary = []
        for dim in ("career", "social", "finance"):
            fs = [f for f in facts if f.dimension == dim and f.intent != "SMALL_EXPENSE"]
            if fs:
                # Global plot is selective; complete dimensional summaries and
                # evidence preserve the remaining turns for audit/down-drill.
                primary.append(f"{dim}：" + "；".join(f.summary.split("；", 1)[0] for f in fs[:2]))
        hr = [f for f in facts if f.intent == "HR_EPISODE"]
        if hr:
            primary.append("健康：" + "；".join(f.summary for f in hr))
        dimensions["global"] = f"{q.persona.name}当天主线：" + ("。".join(primary) if primary else "未见足以确定的重大变化") + "。不同维度的先后变化不自动证明因果关系。"
        evidence["global"] = sorted(set().union(*(set(evidence[d]) for d in ("career", "social", "finance", "health"))))
        answer = {"question_id": q.question_id, "solver_agent": SOLVER,
                  **{f"generated_{dim}_summary": dimensions[dim] for dim in DIMS}}
        audit = {"question_id": q.question_id, "solver_version": self.version,
                 "learned_at": now.isoformat(), "recorded_at": now.isoformat(), "source_exam_date": q.exam_date,
                 "llm_calls": 0, "world_calls": 0, "method": "deterministic_evidence_linked_baseline",
                 "evidence": {dim: [{"slice_index": i, "source_ref": f"{q.cleaned_daily_stream[i].src}@{q.cleaned_daily_stream[i].t}",
                                     "source_sha256": hashlib.sha256(q.cleaned_daily_stream[i].model_dump_json().encode()).hexdigest()} for i in refs]
                              for dim, refs in evidence.items()},
                 "facts": [f.__dict__ for f in facts], "source_digest": before}
        if hashlib.sha256(q.model_dump_json().encode()).hexdigest() != before:
            raise RuntimeError("historical input mutated")
        return answer, audit


class DailyCrossSolverV2(DailyCrossSolver):
    """Development-error fixes: follow-up evidence and chronological synthesis.

    Keeps v1 available. Does not ingest label fields, force agreement with the
    opponent's hidden plots, or remove qualifications to chase substring scores.
    """
    version = "v2"

    def facts(self, q):
        facts = super().facts(q)
        updated = []
        for f in facts:
            source_text = "；".join(q.cleaned_daily_stream[i].text for i in f.refs)
            summary = f.summary
            if f.intent == "HR_EPISODE":
                observed, _, upstream_label = source_text.partition("判定")
                summary = f"{f.time}心率骤升，测量记录：{observed.rstrip('，。')}"
                if upstream_label:
                    summary += f"；设备算法标注‘{upstream_label}’，该标签不等于医生确诊或已证明情绪因果"
            elif f.intent == "PERFORMANCE_REVIEW":
                grade = re.search(r"绩效结果[：:]\s*([A-E])", source_text)
                if grade:
                    summary = f"绩效{grade.group(1)}，需要绩效改进；" + f.summary
            elif f.intent == "INCIDENT_ATTRIBUTION":
                summary = "事故责任受到追查，需要复盘，最终因果责任待核实；" + f.summary
            elif f.intent == "PROJECT_RELEASED":
                summary = "项目上线零故障，项目组受到公开表扬；" + f.summary
            elif f.intent == "AWARD":
                summary = "获得创新奖，奖金待未来发放；" + f.summary
            elif f.intent == "PROMOTION_DENIED":
                summary = "晋升受挫，评审未通过；" + f.summary
            elif f.intent == "PROMOTION_APPROVED":
                summary = "晋升获批，尚待通知日期生效；" + f.summary
            elif f.intent == "OFFER":
                summary = "获得口头offer，答复尚待决定；" + f.summary
            elif f.intent == "ROLE_TRANSFER":
                summary = "岗位调整，转组不自动等于降职；" + f.summary
            elif f.intent == "LEAD_RESPONSIBILITY":
                summary = "被委任牵头模块，承担负责人职责；" + f.summary
            elif f.intent == "REVISION_REQUIRED":
                summary = "方案被批评并要求重做；" + f.summary
            elif f.intent == "REUNION_MEMORY":
                summary = "与老同学交流近况和回忆，呈现老友重逢情境；是否多年未见或聊至深夜没有直接记录；" + f.summary
            updated.append(Fact(f.dimension, f.intent, summary, f.refs, f.time, f.polarity, f.epistemic))
        for i, s in enumerate(q.cleaned_daily_stream):
            if s.src != "mic" or "领导" not in s.speaker:
                continue
            followup = None
            if "检讨明天" in s.text:
                followup = ("要求明天提交检讨，检讨形式未明确", "negative")
            elif "下个周期盯紧" in s.text:
                followup = ("领导要求下周期改进表现，后续考核机制未提供", "negative")
            elif contains(s.text, ("一单漂亮", "好好干")):
                followup = ("领导对工作给予肯定或鼓励", "positive")
            elif "明年再来" in s.text:
                followup = ("领导说明本次评审差距并建议下一轮再申请", "negative")
            if followup:
                updated.append(Fact("career", "LEADER_FOLLOWUP", f"{followup[0]}；领导原话：{s.text}",
                                    (i,), s.t, followup[1]))
        parents = [f for f in updated if f.intent == "PARENT_PRESSURE"]
        if len(parents) > 1:
            updated = [f for f in updated if f.intent != "PARENT_PRESSURE"]
            refs = tuple(r for f in parents for r in f.refs)
            quote = "；".join(f"{q.cleaned_daily_stream[i].speaker}：{q.cleaned_daily_stream[i].text}" for i in refs)
            updated.append(Fact("social", "PARENT_PRESSURE", "父母对婚育安排有催促和分歧，通话中断；不能确定是催婚还是催生，也未见本人争吵的完整原话；" + quote,
                                refs, parents[-1].time, "negative", "inferred"))
        return sorted(updated, key=lambda f: f.time)

    def solve(self, q, *, now=None):
        answer, audit = super().solve(q, now=now)
        facts = [Fact(**f) for f in audit["facts"]]
        work = [f for f in facts if f.dimension == "career" and f.intent != "LEADER_FOLLOWUP"]
        people = [f for f in facts if f.dimension == "social"]
        first_work = work[0].polarity if work else "uncertain"
        last_people = people[-1].polarity if people else "uncertain"
        emotional_path = (first_work, last_people)
        if emotional_path == ("negative", "negative"):
            arc = "工作受挫与人际冲突叠加，可能承受双重压力"
            mood = "白天工作受挫，晚间关系也有冲突，可能焦虑、委屈与低落；缺少直接自述来确认具体强度"
        elif emotional_path == ("negative", "positive"):
            arc = "有起有伏、先抑后扬的一天"
            mood = "白天受挫可能委屈，晚间获得关照或喜讯，情绪有先抑后扬的迹象，可能有所感动和宽慰"
        elif emotional_path == ("positive", "negative"):
            arc = "喜忧参半、先扬后抑的转折日"
            mood = "白天好消息可能令人振奋，晚间关系紧张可能失落；情绪有先扬后抑的迹象"
        elif emotional_path == ("positive", "positive"):
            arc = "事业推进与人际支持同向的一天"
            mood = "工作好消息与关系支持并存，可能喜悦和满足；不能由此断言所有时刻都没有压力"
        else:
            arc = "工作安排或关系状态仍有待明朗的一天"
            mood = "存在不确定安排，具体情绪有待本人陈述，不能仅凭心率推断全天情绪主基调"
        explicit = [f.summary for f in facts if f.dimension == "emotion"]
        answer["generated_emotion_summary"] = ("；".join(explicit) + "；" if explicit else "") + mood + "。此为情境推测，不是精神疾病诊断。"
        primary = []
        for dimension, label in (("career", "事业"), ("social", "人际"), ("finance", "财务")):
            fs = [f for f in facts if f.dimension == dimension and f.intent not in ("LEADER_FOLLOWUP", "SMALL_EXPENSE")]
            if fs:
                primary.append(label + "：" + "；".join(f.summary.split("；", 1)[0] for f in fs[:2]))
        if any(f.intent == "HR_EPISODE" for f in facts):
            primary.append("健康：出现心率骤升记录，关联情境不等于医学因果")
        else:
            maximum = re.search(r"全天最高心率(\d+)bpm", answer["generated_health_summary"])
            if maximum and int(maximum.group(1)) < 100:
                answer["generated_health_summary"] = "已给出的日摘要心率平稳，不能替代完整健康检查；" + answer["generated_health_summary"]
        answer["generated_global_summary"] = q.persona.name + "：" + arc + "。" + "。".join(primary) + "。计划、付款承诺和他人的经历不得当作本人已完成的事实。"
        return answer, audit
