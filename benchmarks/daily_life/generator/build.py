"""Composable full-day observations with evidence-grounded directional keys.

The same latent event creates its observable record and its answer anchor. No
opponent bank is read, and no solver or answer-scoring model is used here.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from .catalog import (CITIES, FINANCE_CODES, GIVEN_A, GIVEN_B, HEALTH_CODES,
                      PROJECTS, ROLES, SOCIAL, SURNAMES)

TZ = timezone(timedelta(hours=8))
DAY = datetime(2026, 9, 16, tzinfo=TZ)
SEED = 0x1A0AA2D
DIMENSIONS = ("global_daily_summary", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career")


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}元"


def name_at(index, offset=0):
    total = len(SURNAMES) * len(GIVEN_A) * len(GIVEN_B)
    multiplier = 7919
    while math.gcd(multiplier, total) != 1:
        multiplier += 1
    n = (index * multiplier + SEED + offset) % total
    return SURNAMES[n // (len(GIVEN_A) * len(GIVEN_B))] + GIVEN_A[n // len(GIVEN_B) % len(GIVEN_A)] + GIVEN_B[n % len(GIVEN_B)]


def choose_scenarios(index, rng):
    # Permuted Cartesian product: not 10,000 copies distinguished only by names.
    n = ((index - 1) * 7919 + 137) % (24 * 12 * 8 * 12)
    rc, n = n % 24, n // 24
    social_index, n = n % 12, n // 12
    health_index, finance_index = n % 8, n // 8
    role = ROLES[rc // 2]
    soc = SOCIAL[social_index]
    lo, hi = role["age"]
    # Avoid generating hundreds of centenarian parents for retired wearers.
    if lo >= 60 and soc["relation"] in {"父亲", "母亲"}:
        soc = SOCIAL[11]
    age = rng.randint(max(lo, soc["min_age"]), hi)
    return role, role["cases"][rc % 2], soc, HEALTH_CODES[health_index], FINANCE_CODES[finance_index], age


def financial_case(code, amount):
    """All values in integer CNY cents. Requested != contracted != posted."""
    a = money(amount)
    table = {
        "repayment": ("银行提醒本期个人信用卡应还" + a + "，尚未扣款。", "银行确认本人信用卡还款" + a + "已扣账成功。", -amount, 0, "NONE", "信用卡还款已完成", "还款到账|负债偿付|已实际扣账", "这笔还款仍未支付|这笔交易是新增借款"),
        "rent": ("房东发来本期本人租住房屋租金账单" + a + "，请核对金额。", "银行确认向房东支付本人租金" + a + "成功，房东已回复收到。", -amount, 0, "NONE", "本期租金实际支付", "租金支出|房租已付|居住成本扣账", "租金尚未付款|租金被认成收入"),
        "family_support": ("本人打算从个人账户给家庭共用照护金补入" + a + "，此前仅做了预算。", "家庭共用照护金账户已收到本人转入的" + a + "；这是支持家庭，不是出借给朋友。", -amount, 0, "NONE", "向家庭共用照护金实际转入支持款", "家庭支持支出|照护金转入|本人账户支出", "已向朋友发放贷款|本人收到该笔收入"),
        "refund_posted": ("此前本人购买的家电退货已受理，预计退款" + a + "，早上仍在处理中。", "银行入账记录显示该笔家电退款" + a + "已到账，原待退款状态结案。", amount, 0, "NONE", "家电退款由处理中转为实际到账", "退款到账|退货返款|资金回流", "退款仍完全未到账|新增借款形成该收入"),
        "phishing_stopped": ("陌生账号称本人需支付" + a + "解冻账户，并催促立即转账；未经认证。", "本人联系银行官方客服核实，确认陌生催款是冒充；未按要求转账，银行本日无此扣款。", 0, 0, "NONE", "识破冒充催款并停止转账，未产生该笔损失", "识破诈骗|转账被阻止|未实际损失", "已经转出诈骗款|欠陌生账号该笔合法债务"),
        "income_pending": ("兼职结算方说本人有一笔" + a + "报酬在审批中，尚未付款。", "本人查账户并向结算方确认：仍待财务审批，本日没有收到这笔" + a + "。", 0, 0, "INCOME_PENDING", "报酬仍待审批，不能认定已到账", "收入待结算|应收未到账|付款待审批", "报酬已到账|已经确认付款失败且永久不付"),
        "new_loan": ("银行展示本人申请的小额借款" + a + "待签确认页面，早上还没有放款。", "本人确认合同后银行放款" + a + "入本人账户，新借款本金同额成立，后续需按合同偿还。", amount, amount, "NONE", "小额借款签约并实际放款，现金与债务同时增加", "借款落地|放款到账|新增本金债务", "只是无偿收入无需偿还|只申请未放款|本日没有新增债务"),
        "income_posted": ("平台通知本人此前提供服务的报酬" + a + "进入待支付队列，与今天职业任务不是同一笔业务。", "银行确认此前服务报酬" + a + "入账成功；不是借款，无对应新本金债务。", amount, 0, "NONE", "此前服务报酬实际入账，不构成新债务", "报酬到账|服务收入|资金增加", "报酬仍未支付|这笔收入属于借款"),
        "charge_disputed": ("银行扣账记录出现本人不认识的消费" + a + "，已实际扣款，尚不清楚归因。", "本人向银行发起争议，客服回复已受理调查；截至今日未退款，不能认定调查已胜诉。", -amount, 0, "DISPUTE_OPEN", "陌生消费已扣账，争议调查未决且尚未退款", "争议扣款|待调查|已扣未退", "款项已退回|银行已最终认定本人胜诉|肯定是本人故意消费"),
        "contract_not_disbursed": ("本人在正规银行阅读额度" + a + "的借款合同，尚未最终确认。", "本人完成合同电子确认，银行状态为待放款，今日没有资金入账；合同关系成立不等于放款完成。", 0, 0, "SIGNED_AWAITING_DISBURSEMENT", "借款合同已确认但尚未放款，未新增实际放款本金", "签约待放款|合同与到账分离|资金未入账", "放款已经到账|从未签署任何合同|签约即等于已收到现金"),
        "repayment_retry": ("本人信用卡还款" + a + "首次尝试因网络超时未完成，银行确认该次没有扣账。", "本人重新操作后银行确认还款" + a + "成功，仅扣款一次，先前失败状态已被后续成功取代。", -amount, 0, "NONE", "还款首次失败后重试成功，最终仅扣款一次", "重试成功|还款完成|失败后反转", "还款一直失败未完成|还款扣款两次|该笔支出变成收入"),
        "refund_pending": ("平台批准本人退款" + a + "申请，显示原路退回处理中。", "本人查银行未见该笔入账，平台仍显示处理中；批准退款不是钱已经到账。", 0, 0, "REFUND_PENDING", "退款获批准但截至日终尚未到账", "退款待到账|审核通过未入账|返款处理中", "退款已经实际到账|退款申请已被最终拒绝"),
    }
    start, end, delta, debt, pending, summary, accepts, forbidden = table[code]
    return dict(code=code, start=start, end=end, delta=delta, debt=debt, pending=pending,
                summary=summary, accepts=accepts.split("|"), forbidden=forbidden.split("|"), amount=amount)


def health_case(code, baseline, rng):
    peak = rng.randint(121, 136)
    recover = rng.randint(78, 94)
    if code == "stress_recovery":
        return dict(code=code, peak=peak, recover=recover, quality="valid", activity="静坐",
                    start=f"晚间静坐时心率升到{peak}bpm，IMU未见剧烈运动；本人说刚才的谈话让我很紧张，暂未报告胸痛。",
                    end=f"休息和缓慢呼吸后，复测心率{recover}bpm；本人说紧绷感减轻。未形成具体心脏病诊断。",
                    summary="晚间静止时出现心率升高，随后休息回落；与情绪事件时间相邻，不足以证明唯一病因",
                    accepts=["心率骤升后回落", "静止心动过速", "紧张伴心率波动", "身心压力相关但未确诊"],
                    forbidden=["全天心率完全平稳没有波动", "已经确诊心肌梗死", "确定完全由剧烈运动解释"], urgent=False)
    if code == "exercise_recovery":
        peak = rng.randint(132, 152)
        return dict(code=code, peak=peak, recover=recover, quality="valid", activity="爬楼后步行恢复",
                    start=f"本人上楼并快走后心率{peak}bpm，IMU呈有节律的上下楼运动；本人未诉胸痛或晕厥。",
                    end=f"停止运动后复测心率{recover}bpm，活动恢复平稳，没有急救事件记录。",
                    summary="晚间心率上升有明确运动伴随并在停止后回落，不能仅凭数字认定情绪危象",
                    accepts=["运动相关心率升高", "活动后正常回落", "生理负荷变化", "不能误报心脏危象"],
                    forbidden=["静息状态突发心搏骤停", "完全没有运动就剧烈心率上升", "已经确诊心梗"], urgent=False)
    if code == "sleep_debt":
        return dict(code=code, peak=baseline + 10, recover=baseline + 4, quality="valid", activity="静坐",
                    start=f"晚间静坐心率{baseline+10}bpm。本人说昨夜反复醒、今天注意力差，下午多次想打瞌睡。",
                    end=f"复测心率{baseline+4}bpm，没有捕捉到显著心动过速；本人仍感疲惫，准备减少晚间任务。",
                    summary="昨夜睡眠不足且本人持续疲劳，心率没有发生剧烈突升；疲劳不等于心脏骤停",
                    accepts=["睡眠不足", "疲劳累积", "注意力下降", "体征较稳但疲惫"],
                    forbidden=["昨夜睡眠充足且全天精力旺盛", "出现已证实的心搏骤停", "晚间静息心率超过120且持续不降"], urgent=False)
    if code == "off_wrist_artifact":
        return dict(code=code, peak=peak, recover=baseline + 2, quality="invalid_off_wrist", activity="设备脱腕",
                    start=f"手环被摘下放到桌面，IMU瞬时冲击6.1g；屏幕显示{peak}bpm，但接触检测为脱腕、PPG质量不足。本人说我只是放表，没有摔倒。",
                    end=f"重新佩戴后有效心率{baseline+2}bpm，步态稳定；先前脱腕读数不纳入有效体征统计。",
                    summary="脱腕放表产生冲击和无效心率读数，重新佩戴正常；不能认定人体摔倒或真实心率骤升",
                    accepts=["脱腕伪迹", "传感器误报排除", "无效读数", "非人体跌倒"],
                    forbidden=["佩戴者发生严重摔倒", "无效心率值被当作已证实心动过速", "已发生心搏骤停"], urgent=False)
    if code == "steady":
        return dict(code=code, peak=baseline + 7, recover=baseline + 3, quality="valid", activity="静坐",
                    start=f"晚间有效心率{baseline+7}bpm，呼吸与运动宏观摘要无急性异常。本人明确说情绪有起伏，但身体没有明显不舒服。",
                    end=f"复测有效心率{baseline+3}bpm；本段未检出急性异常，不能据此推断心理问题不存在。",
                    summary="全天及晚间有效体征总体稳定，情绪起伏没有伴随已观测到的急性生理危象",
                    accepts=["体征总体平稳", "未见急性生理异常", "情绪与体征区分", "没有心率危象证据"],
                    forbidden=["因为情绪不好所以一定发生心率危象", "本人已确诊心梗", "体征稳定证明毫无情绪压力"], urgent=False)
    if code == "caffeine_uncertain":
        return dict(code=code, peak=peak, recover=recover, quality="valid", activity="静坐",
                    start=f"静坐心率{peak}bpm。本人说上午喝了买的一杯咖啡和茶水间免费的一杯，今晚又心慌，拿不准是咖啡、压力还是别的原因。",
                    end=f"暂停咖啡并休息后复测{recover}bpm；目前没有检查证实单一病因。",
                    summary="静止心慌伴心率升高后回落，咖啡摄入与压力均有线索，病因仍不确定",
                    accepts=["心慌回落", "多因素可能", "咖啡摄入线索", "病因未定"],
                    forbidden=["医生已证实全部由咖啡造成", "已经排除一切其他原因", "本人发生已确诊心梗"], urgent=False)
    if code == "urgent_assessment":
        return dict(code=code, peak=peak, recover=rng.randint(92, 105), quality="valid", activity="静坐胸部不适",
                    start=f"本人静坐时心率{peak}bpm，诉胸口压迫感、冷汗和喘憋，虽说可能休息就好，但症状没有立即消失。",
                    end="家属已陪同到急诊，分诊人员要求继续检查并留观；目前没有明确疾病诊断，也没有宣告所有风险已排除。",
                    summary="静止胸部压迫感、冷汗、喘憋与心率升高构成高危信号，已赴急诊评估，诊断及结局尚未明确",
                    accepts=["高危胸部症状", "及时急诊评估", "身体危象待排查", "不能因口头否认忽略风险"],
                    forbidden=["只是开玩笑无需关注", "已经确诊心肌梗死或心搏骤停", "检查确认绝对健康并已回家睡觉"], urgent=True)
    return dict(code=code, peak=baseline + 12, recover=baseline + 3, quality="valid", activity="起身后坐下",
                start=f"本人久坐起身时短暂眼前发黑，心率{baseline+12}bpm，随后坐下休息；IMU没有跌倒冲击。",
                end=f"本人反馈眩晕已缓解，有效心率{baseline+3}bpm；尚未测到血压数据或得到贫血等具体诊断。",
                summary="起身后短暂眩晕经坐下缓解，未见跌倒；没有血压或化验证据支持具体病因诊断",
                accepts=["体位变化后短暂不适", "眩晕缓解", "未见跌倒", "病因待观察"],
                forbidden=["已经确诊严重贫血", "已经测得低血压数值", "发生了有证据的严重摔倒"], urgent=False)


def routine(rng, minute, role, person, contacts, health, onset, reassess, steps):
    """Low-stakes, cleaned observations, not raw noise or hidden answer tags."""
    home = minute < 480 or minute >= 1110
    location = "家中" if home else role["workspace"]
    if 480 <= minute < 520 or 1060 <= minute < 1110:
        location = "通勤途中"
    if health["urgent"] and minute >= reassess:
        location = "急诊留观区"
    channel = rng.choices(["MIC", "APP", "SENSOR"], weights=[4, 4, 3])[0]
    self_id, peer_id = person["person_id"], contacts[0]["entity_id"]
    if channel == "SENSOR":
        if onset <= minute < reassess:
            fraction = (minute - onset) / (reassess - onset)
            hr = round(health["peak"] + fraction * (health["recover"] - health["peak"]))
            quality = health["quality"]
            activity = health["activity"]
        else:
            base = person["baseline_resting_hr_bpm"] if minute < onset else health["recover"]
            hr = base + rng.randint(-3, 6)
            quality = "valid"
            activity = rng.choice(["坐姿稳定", "缓步", "手部轻活动"])
        return dict(modality=channel, source="手环宏观摘要", participants=[self_id],
                    text=f"{location}时段：{activity}，心率读数{hr}bpm；截至本片段累计步数{steps}。",
                    measurements={"heart_rate_bpm": hr, "measurement_quality": quality,
                                  "on_wrist": quality == "valid", "cumulative_steps": steps, "activity": activity})
    if channel == "APP":
        if not home and location != "急诊留观区":
            obj = rng.choice(role["tasks"])
            text = rng.choice([f"个人工作台：{obj}的草稿已自动保存。", f"协作群：{obj}附件已同步到共享目录。", f"提醒事项：有空核对{obj}的文件命名。", f"个人笔记：已把{obj}加入检索标签。", f"工具通知：{obj}旧版仍保留，只新增一份副本。", f"协作群：{obj}的浏览权限正常，暂不需要操作。", f"日历：{obj}例行整理提醒已看到，未形成新的工作承诺。"])
        else:
            topic = rng.choice(["菜谱收藏", "地铁时刻", "借阅书目", "居家收纳", "公园路线", "语言学习", "相册分类", "天气趋势", "纪录片片单", "便民服务", "运动拉伸", "盆栽养护"])
            text = rng.choice([f"阅读应用：已保存{topic}的阅读位置。", f"个人收藏：{topic}有一条离线笔记。", f"便民信息：今日{topic}栏目已更新。", f"聊天群里分享了{topic}的经验，我只做了收藏。", f"学习应用：{topic}的提醒已延后，不涉及付款。", f"检索记录：查看{topic}的公开信息，未做付费操作。"])
        return dict(modality=channel, source=rng.choice(["个人笔记APP", "微信日常群", "系统提醒"]), participants=[self_id], text=text)
    if location == "急诊留观区":
        text = rng.choice(["我先坐着等叫号，今天别的事情暂时不处理。", "家属帮我把随身物品放在椅边。", "我把手机调低亮度，等下一步检查安排。", "我喝了一小口水，继续等分诊通知。", "现在还没有新的检查结论，我不自己猜病名。"])
        speaker_ids = [self_id]
    elif home:
        obj = rng.choice(["毛巾", "钥匙", "水杯", "窗帘", "书签", "雨伞", "充电线", "收纳盒", "外套", "拖鞋", "纸巾", "台灯", "背包", "水壶", "旧杂志", "靠垫"])
        text = rng.choice([f"我把{obj}放回常用的位置，省得下次到处找。", f"我看了看{obj}，这次先用现有的，不另外下单。", f"我整理了一下{obj}周围的地方。", f"我记下{obj}放在哪里，继续手头的小事。", f"我停了几分钟整理{obj}，没有新计划。", f"我把注意力放回{obj}这件小事，暂时不刷更多消息。"])
        speaker_ids = [self_id]
    elif location == "通勤途中":
        text = rng.choice(["车门这边人少一点，我往里面让了让。", "我看了一眼路线图，今天仍按常用路线走。", "站台提示下一班还有几分钟，我继续等。", "前面的人让出通道，我说了声谢谢。", "我把背包移到身前，没有和人发生争执。", "路口在正常通行，我等绿灯再过去。"])
        speaker_ids = [self_id]
    else:
        obj = rng.choice(role["tasks"])
        text = rng.choice([f"{contacts[0]['name']}问{obj}放哪了，我指了常用目录。", f"我说先看{obj}的这一页，旁边的人点头表示听到了。", f"我把{obj}的位置说清楚，然后继续原来的任务。", f"我说{obj}的命名还沿用旧规则，不必重复整理。", f"{contacts[0]['name']}提到{obj}的一个小细节，我记在便签上。", f"我核对{obj}的顺序，没有就此作出新的重大决定。", f"我和{contacts[0]['name']}聊了两句{obj}的日常处理方式。"])
        speaker_ids = [self_id, peer_id]
    return dict(modality=channel, source="MIC已转写对话", participants=speaker_ids, speaker_ids=speaker_ids, text=text)


def make_question(index, seed=SEED):
    if not 1 <= index <= 10000:
        raise ValueError("index must be between 1 and 10000")
    rng = random.Random(seed * 100003 + index)
    role, car, soc, health_code, finance_code, age = choose_scenarios(index, rng)
    pid, qid = f"P_{index:05d}", f"DAY_01a0aa2d_{index:05d}"
    contact = name_at(index + 20000)
    lead = name_at(index + 40000)
    peer = name_at(index + 60000)
    project = rng.choice(PROJECTS) + f"{rng.randint(2, 38)}号"
    values = dict(contact=contact, lead=lead, project=project)
    contacts = [dict(entity_id=f"{pid}:peer", name=peer, relation=role["colleague"]),
                dict(entity_id=f"{pid}:contact", name=contact, relation=soc["relation"]),
                dict(entity_id=f"{pid}:lead", name=lead, relation="当日任务协调人"),
                dict(entity_id=f"{pid}:neighbor", name=name_at(index + 80000), relation="邻居"),
                dict(entity_id=f"{pid}:family", name=name_at(index + 100000), relation="家人"),
                dict(entity_id=f"{pid}:friend", name=name_at(index + 120000), relation="朋友"),
                dict(entity_id=f"{pid}:stranger", name="快递员（姓名未提供）", relation="陌生人")]
    baseline = rng.randint(60, 78)
    persona = dict(person_id=pid, name=name_at(index), age=age, gender=rng.choice(["女", "男"]),
                   occupation=role["role"], city=rng.choice(CITIES), timezone="Asia/Shanghai",
                   day="2026-09-16", day_window={"start": DAY.isoformat(), "end": (DAY + timedelta(days=1)).isoformat()},
                   baseline_resting_hr_bpm=baseline, shift_description="当日白天开展职业、学习或照护行动，晚间处理私人生活",
                   relationship_at_day_start={"with_entity_id": contacts[1]["entity_id"], "state": soc["initial"]},
                   housing="本人租住房屋" if finance_code == "rent" else ("合租" if soc["relation"] == "室友" else rng.choice(["与家人同住", "独立居住"])),
                   contacts=contacts, fictional=True)
    health = health_case(health_code, baseline, rng)
    amount = rng.choice([600, 800, 1200, 1800, 2400, 3000, 3600, 4800, 5200, 6500]) * 100
    if finance_code in {"phishing_stopped", "new_loan", "contract_not_disbursed"}:
        amount = rng.choice([3000, 5000, 8000, 12000, 16000]) * 100
    finance = financial_case(finance_code, amount)
    coffee = rng.choice([1200, 1500, 1800, 2200, 2600])
    lunch = rng.choice([1800, 2300, 2800, 3200, 3600])
    dinner = rng.choice([1600, 2100, 2700, 3400, 4200])
    small_total = coffee + lunch + dinner
    initial_balance = rng.randint(20000, 95000) * 100
    end_balance = initial_balance + finance["delta"] - small_total
    wake_minute = rng.randint(375, 405)
    sleep_start = DAY - timedelta(minutes=rng.randint(20, 115))
    awake_minutes = rng.randint(90, 155) if health_code == "sleep_debt" else rng.randint(3, 22)
    sleep_minutes = int(((DAY + timedelta(minutes=wake_minute)) - sleep_start).total_seconds() // 60) - awake_minutes
    if health_code != "sleep_debt" and sleep_minutes < 360:
        sleep_start -= timedelta(minutes=30)
        sleep_minutes += 30

    # Record meaningful changes at separate times. Small timing jitter makes the
    # cross-modal correlations observable without requiring exact clock strings.
    times = {"sleep": 420, "family_chat": 432, "peer_chat": 610, "friend_chat": 860, "stranger_chat": 1040, "parcel_picked": 1105, "news": 1160, "coffee": 455, "finance_start": 490 + rng.randint(-7, 7),
             "career_start": 550 + rng.randint(-8, 8), "career_obstacle": 670 + rng.randint(-8, 8),
             "social_midday": 723 + rng.randint(-6, 6), "emotion_midday": 744 + rng.randint(-4, 4),
             "lunch": 760, "other_person": 952 + rng.randint(-4, 4), "career_end": 986 + rng.randint(-8, 8),
             "finance_end": 1090 + rng.randint(-7, 7), "dinner": 1130,
             "social_end": 1232 + rng.randint(-5, 5), "health_start": 1250 + rng.randint(-3, 3),
             "health_end": 1284 + rng.randint(-3, 3), "cross": 1322 + rng.randint(-4, 4),
             "emotion_end": 1362 + rng.randint(-4, 4), "finance_audit": 1390,
             "day_end": 1405}
    if len(set(times.values())) != len(times):
        raise AssertionError("core timestamps must be distinct")
    observations = {}

    def put(key, modality, text, participants=None, measurements=None, **extra):
        observations[times[key]] = dict(key=key, modality=modality,
            source={"MIC": "MIC已转写对话", "APP": "经来源区分的通知记录", "SENSOR": "手环宏观摘要"}[modality],
            participants=participants or [pid], text=text,
            **({"measurements": measurements} if measurements is not None else {}), **extra)

    book = rng.choice(["城市散步随笔", "自然观察笔记", "短篇小说集", "旅行手记", "历史人物小传", "科普读物", "诗歌选集", "地方风物志"])
    put("family_chat", "MIC", f"家人{contacts[4]['name']}说：昨晚晾的衣服已经收好了。我回复知道了，有空把衣架放回常用位置。", [pid, contacts[4]["entity_id"]])
    put("peer_chat", "MIC", f"{role['colleague']}{peer}问一份{rng.choice(role['tasks'])}放在哪里，我告诉对方常用位置，随后各自继续手头任务。", [pid, contacts[0]["entity_id"]])
    put("friend_chat", "MIC", f"朋友{contacts[5]['name']}说看了{book}的开头。我说还没读完，可以慢慢看，不用今天就讨论结局。", [pid, contacts[5]["entity_id"]])
    put("stranger_chat", "MIC", f"快递员说：之前买的包裹放在门卫架{rng.randint(1,32)}号格，不需到付。我说谢谢，稍后去取。", [pid, contacts[6]["entity_id"]])
    put("parcel_picked", "APP", "取件记录：本人领取此前订单的包裹，核对外包装无破损；今天没有另付取件费。")
    other_city = rng.choice([c for c in CITIES if c != persona['city']])
    put("news", "APP", f"新闻摘要：{other_city}的一条公共绿道开放试运行，报道介绍了沿途设施；是外地公共新闻，不是本人的出行记录。")
    put("sleep", "SENSOR", f"昨夜睡眠从{sleep_start.isoformat()}至今晨{(DAY+timedelta(minutes=wake_minute)).isoformat()}，扣除觉醒{awake_minutes}分钟后有效睡眠{sleep_minutes}分钟；晨起静息心率{baseline}bpm。",
        measurements={"sleep_episode_start": sleep_start.isoformat(), "sleep_episode_end": (DAY + timedelta(minutes=wake_minute)).isoformat(),
                      "sleep_minutes": sleep_minutes, "awake_minutes": awake_minutes, "resting_hr_bpm": baseline, "measurement_quality": "valid"})
    put("coffee", "APP", f"本人早餐后购买一杯咖啡，支付{money(coffee)}已完成，没有第二次重复扣款。", transaction={"owner_id": pid, "delta_cents": -coffee, "status": "POSTED", "currency": "CNY"})
    put("lunch", "APP", f"本人午餐付款{money(lunch)}完成，随后收到取餐通知。", transaction={"owner_id": pid, "delta_cents": -lunch, "status": "POSTED", "currency": "CNY"})
    put("dinner", "APP", f"本人晚餐付款{money(dinner)}完成，餐食已取到。", transaction={"owner_id": pid, "delta_cents": -dinner, "status": "POSTED", "currency": "CNY"})
    put("finance_start", "APP", finance["start"], source_account_owner_id=pid)
    put("finance_end", "APP", finance["end"], transaction={"owner_id": pid, "delta_cents": finance["delta"],
        "status": "POSTED" if finance["delta"] else (finance["pending"] if finance["pending"] != "NONE" else "NO_TRANSFER"), "currency": "CNY", "new_disbursed_principal_cents": finance["debt"]})
    for key, content in [("career_start", car["start"]), ("career_obstacle", car["obstacle"]), ("career_end", car["ending"])]:
        put(key, "MIC" if key != "career_end" else "APP", content.format(**values), [pid, contacts[2]["entity_id"]])
    put("social_midday", "APP", soc["midday"].format(**values), [pid, contacts[1]["entity_id"]])
    put("social_end", "MIC", soc["evening"].format(**values), [pid, contacts[1]["entity_id"]])
    put("emotion_midday", "MIC", f"我现在的感受是：{car['emotion']}；私人那边的消息也让我分心。这是我自己的感受，不是医生下的心理诊断。")
    put("other_person", "APP", f"邻居{contacts[3]['name']}在群里说：我今天收到了旧网购订单的退款，准备周末去看一场电影。", [contacts[3]["entity_id"]])
    put("health_start", "SENSOR", health["start"], measurements={"heart_rate_bpm": health["peak"],
        "measurement_quality": health["quality"], "on_wrist": health["quality"] == "valid", "activity": health["activity"]})
    put("health_end", "APP" if health["urgent"] else "SENSOR", health["end"],
        measurements={"heart_rate_bpm": health["recover"], "measurement_quality": "valid", "on_wrist": True})
    if health["urgent"]:
        decision = "今晚暂停处理工作和家务，留在急诊配合检查，其他事项等情况明确再安排"
        emotion_end = f"我对人际那边仍然是{soc['emotion']}；但现在更担心身体，正在等待检查，不代表已经绝望到要自伤。"
    else:
        decision = "今晚不再追加工作任务，先保留休息时间；" + car["followup"]
        emotion_end = f"白天我{car['emotion']}，到晚上{soc['emotion']}。我决定先做能控制的小事，暂不把所有问题都当作已经解决。"
        if health_code == "sleep_debt":
            emotion_end += "睡眠不足让我更疲惫，我想早点结束今天的任务。"
    finance_constraint = ("尚未到账的款项不列入今晚可用的钱" if finance["pending"] != "NONE" else
                          "已有实际收支和预算约束，不再因今天的情绪随意追加付费安排")
    put("cross", "MIC", f"我本来想晚上继续处理白天的任务，又想把私人消息一次谈清，可今天的体力和预算不允许什么都接。{finance_constraint}。所以我决定{decision}。")
    put("emotion_end", "MIC", emotion_end)
    all_debits = small_total + max(0, -finance["delta"])
    all_credits = max(0, finance["delta"])
    put("finance_audit", "APP", f"本人授权汇总的个人账户日结：期初可用余额{money(initial_balance)}，今日已入账收入{money(all_credits)}，已扣账支出{money(all_debits)}（含咖啡、午餐、晚餐合计{money(small_total)}）；当前余额{money(end_balance)}。今日新增实际放款本金{money(finance['debt'])}。未到账或争议状态：{finance['pending']}。未出现其他新增借款或支出记录。",
        account_summary={"owner_id": pid, "opening_balance_cents": initial_balance, "posted_credits_cents": all_credits,
                         "posted_debits_cents": all_debits, "closing_balance_cents": end_balance,
                         "new_disbursed_principal_cents": finance["debt"], "pending_status": finance["pending"], "currency": "CNY"})

    # Partition the ENTIRE 24h window, with many short cleaned daytime slices.
    starts = [420]
    while starts[-1] < 1410:
        starts.append(min(1410, starts[-1] + rng.randint(3, 6)))
    starts = sorted(set([0, wake_minute, 420, 1410, *starts, *times.values()]))
    boundaries = starts + [1440]
    stream, key_ids, steps = [], {}, 0
    for order, (minute, end_minute) in enumerate(zip(boundaries, boundaries[1:])):
        if minute >= wake_minute:
            # Counts are cumulative physical activity, not independent random totals.
            if (480 <= minute < 540) or (1060 <= minute < 1130):
                steps += rng.randint(90, 230)
            elif minute < 1320 and not (health["urgent"] and minute >= times["health_start"]):
                steps += rng.randint(0, 50)
        if minute == 0:
            obs = dict(modality="SENSOR", source="夜间睡眠宏观摘要", participants=[pid], text=f"零点至{(DAY+timedelta(minutes=wake_minute)).strftime('%H:%M')}处于夜间睡眠监测窗，其间累计清醒{awake_minutes}分钟；并非整段无间断熟睡。", measurements={"awake_minutes_in_interval": awake_minutes})
        elif minute == wake_minute:
            obs = dict(modality="MIC", source="MIC已转写自述", participants=[pid], text="我起床洗漱，整理随身物品，准备开始今天的安排。")
        elif minute == 1410:
            obs = dict(modality="SENSOR", source="日界前宏观摘要", participants=[pid], text=("23:30至24:00仍在急诊留观区等候检查，没有新的诊断结果，未入睡。" if health["urgent"] else "23:30后进入睡前休息并监测到入睡片段；截至24:00完整夜间睡眠尚未结束，不能提前给出下一夜总时长。"), measurements={"cumulative_steps": steps, "sleep_episode_complete": False})
        elif minute == times["day_end"]:
            obs = dict(modality="SENSOR", source="全天宏观摘要", participants=[pid], text=f"截至23:25累计步数{steps}；此前报告的{sleep_minutes}分钟是昨夜至今晨睡眠，不是尚未完成的下一夜。", measurements={"cumulative_steps": steps, "last_completed_sleep_minutes": sleep_minutes})
            key_ids["day_end"] = f"s{order:03d}"
        elif minute in observations:
            obs = dict(observations[minute])
            key_ids[obs.pop("key")] = f"s{order:03d}"
            if "measurements" in obs:
                obs["measurements"]["cumulative_steps"] = steps
        else:
            obs = routine(rng, minute, role, persona, contacts, health, times["health_start"], times["health_end"], steps)
        stream.append(dict(slice_id=f"s{order:03d}", timestamp=(DAY + timedelta(minutes=minute)).isoformat(),
                           end_timestamp=(DAY + timedelta(minutes=end_minute)).isoformat(), **obs))

    def evidence(*keys):
        return [key_ids[k] for k in keys]

    def anchor(code, proposition, accepts, refs, entities=(), certainty="observed", weight=1.0):
        return dict(anchor_id=code, proposition=proposition, acceptable_direction_synonyms=accepts,
                    evidence_refs=refs, entity_ids=list(entities) or [pid], certainty=certainty,
                    temporal_scope="2026-09-16；按证据先后区分最终状态与早期状态", weight=weight)

    def block(summary, anchors, forbidden):
        return dict(core_summary=summary, semantic_core_anchors=anchors,
                    acceptable_directional_paraphrases=list(dict.fromkeys(p for a in anchors for p in a["acceptable_direction_synonyms"])),
                    red_line_criteria=[dict(code=f"POLARITY_VETO_{i+1}", rejected_assertion=text, severity="ONE_VOTE_VETO",
                                           applies_only_when="模型把它作为本人今天已发生的肯定事实；引用、否定、风险提示和未定假设不触发红线") for i, text in enumerate(forbidden)],
                    scoring_policy="按语义方向、主体、否定/条件、先后状态和证据评估；不得要求逐字命中同义词表。只说宽泛相关词而遗漏关键状态可给部分分，不自动判完整正确。")

    car_anchor = anchor("career:trajectory", car["summary"], car["acceptable"], evidence("career_start", "career_obstacle", "career_end"), [pid, contacts[2]["entity_id"]])
    soc_anchor = anchor("social:trajectory", soc["summary"], soc["acceptable"], evidence("social_midday", "social_end"), [pid, contacts[1]["entity_id"]])
    health_anchor = anchor("health:change", health["summary"], health["accepts"], evidence("health_start", "health_end"), certainty="observed_signals_not_diagnosis")
    fin_anchor = anchor("finance:state", finance["summary"], finance["accepts"], evidence("finance_start", "finance_end", "finance_audit"))
    emotional_summary = (car["emotion"] + "；晚间" + soc["emotion"] + ("，随后因身体高危信号转为担忧并等待检查" if health["urgent"] else "，尝试通过安排边界减轻负担"))
    emotion_words = ["情绪有先后转折", "混合情绪", "自述感受不等于临床诊断"]
    for cues, synonyms in [
        ("焦虑|担心|紧张|压力|挣扎|怕", ["焦虑", "紧张", "担忧", "心理压力"]),
        ("委屈|受冤枉|失落|受否定|难过", ["委屈", "失落", "难过", "受挫"]),
        ("愤怒|烦躁", ["生气", "烦闷", "恼火"]),
        ("支持|理解", ["被支持", "被理解", "孤立感减轻"]),
        ("缓解|缓和|放松|松一口气|轻松|安心|踏实", ["缓和", "释然", "松口气"]),
        ("期待", ["期待", "希望", "怕落空"]),
        ("内疚", ["愧疚", "过意不去", "坚持边界伴内疚"]),
    ]:
        if any(cue in emotional_summary for cue in cues.split("|")):
            emotion_words.extend(synonyms)
    emotion_forbidden = ["本人明确全天毫无压力和情绪变化", "仅凭这些片段确诊抑郁症或其他精神疾病", "凭空认定本人已经自伤或作出自伤计划"]
    if soc["code"] == "breakup_confirmed":
        emotion_forbidden.append("把明确的分手失落写成毫无难过的甜蜜狂喜")
    if soc["code"] in {"friend_support", "parent_check_relief", "colleague_apology"}:
        emotion_forbidden.append("否认自述中已出现的被理解感或局部缓解，声称从未有任何缓解")
    emo_anchor = anchor("emotion:trajectory", emotional_summary,
                        emotion_words, evidence("emotion_midday", "emotion_end"), certainty="self_report")
    cross_anchor = anchor("global:tradeoff", "工作或行动目标、人际要求与身体/预算约束相互挤占，最终取舍为：" + decision,
                          ["多重压力叠加后重新排序", "责任与个人边界冲突", "身心及预算约束影响行动", "并非琐事流水账"], evidence("career_end", "social_end", "health_start", "finance_end", "cross"), certainty="self_reported_tradeoff", weight=2.0)
    sleep_anchor = anchor("health:sleep", f"上一完整睡眠段有效睡眠{sleep_minutes}分钟，晨起静息心率{baseline}bpm；当天记录最终步数{steps}。",
                          ["昨夜睡眠与今天体征区分", "保留有意义的睡眠和活动量", "不提前编造下一夜睡眠"], evidence("sleep", "day_end"))
    finance_numbers = anchor("finance:ledger", f"重大事项涉及{money(amount)}；咖啡与两餐合计{money(small_total)}。总入账{money(all_credits)}、总扣账{money(all_debits)}，余额由{money(initial_balance)}变为{money(end_balance)}，实际新放款本金{money(finance['debt'])}。",
                             ["到账和待处理分离", "净现金流与债务分离", "日常小额消费不是主线", "按个人账户而非他人消息记账"], evidence("coffee", "lunch", "dinner", "finance_start", "finance_end", "finance_audit"))
    sleep_anchor["numeric_anchors"] = {"sleep_minutes": sleep_minutes, "resting_hr_bpm": baseline, "final_steps": steps}
    health_anchor["numeric_anchors"] = {"displayed_onset_hr_bpm": health["peak"], "onset_measurement_valid": health["quality"] == "valid", "recheck_hr_bpm": health["recover"]}
    finance_numbers["numeric_anchors"] = {"major_item_cents": amount, "daily_small_expenses_cents": small_total,
        "opening_balance_cents": initial_balance, "closing_balance_cents": end_balance,
        "posted_debits_cents": all_debits, "posted_credits_cents": all_credits, "new_disbursed_principal_cents": finance["debt"]}
    career_action = anchor("career:next_action", "日终实际行动取舍：" + decision,
                           ["已完成与待办分开", "不把计划写成已经完成", "按最终沟通更新行动顺序"], evidence("career_end", "cross"))
    global_summary = f"{car['summary']}；{soc['summary']}；{health['summary']}；{finance['summary']}。{emotional_summary}，日终选择{decision}。"
    gt = {
        "global_daily_summary": block(global_summary, [car_anchor, soc_anchor, health_anchor, fin_anchor, emo_anchor, cross_anchor], ["把今天概括为只有吃饭取物且没有核心转折", car["forbidden"][0], soc["forbidden"][0], health["forbidden"][0], finance["forbidden"][0], "把邻居的财务消息当成本人的入账"]),
        "dim:health": block(health["summary"], [sleep_anchor, health_anchor], health["forbidden"] + ["把父母或新闻里的疾病直接认定为佩戴者本人已确诊"]),
        "dim:social": block(soc["summary"], [soc_anchor], soc["forbidden"]),
        "dim:emotion": block(emotional_summary, [emo_anchor, anchor("emotion:coping", "日终自述与取舍：" + decision,
            ["尝试应对而非保证治愈", "保留混合情绪", "行动边界可能带来局部缓解"], evidence("cross", "emotion_end"), certainty="self_report")],
            emotion_forbidden),
        "dim:finance": block(finance["summary"], [fin_anchor, finance_numbers], finance["forbidden"] + ["把邻居或单位业务款项记入本人个人账户", "捏造未出现在个人账户汇总中的新借款"]),
        "dim:career": block(car["summary"], [car_anchor, career_action], car["forbidden"]),
    }
    return {"question_id": qid, "persona": persona, "cleaned_daily_stream": stream, "directional_ground_truth": gt}
