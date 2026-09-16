"""AIOS 3.0 全天生活流与多维总结高熵出卷生成器（出卷战队 01a0aa2c-fantonghui）。

每道试卷 = 一个人的一整天（24 小时已清洗生活流），标准四键：
``question_id`` / ``persona`` / ``cleaned_daily_stream`` / ``directional_ground_truth``
（另附 ``generator_agent``/``date``/``difficulty`` 元信息）。

标答为六维方向性语义锚点（全局日总结 + dim:health/social/emotion/finance/career），
每维包含 core_anchor / accepted_synonyms（可接受方向同义词簇）/
redline_criteria（绝对偏离红线判据，一票否决）/ anchor_entities / evidence_event_ids。

出题铁律的工程落实：
1. **可观测性自检**：每个锚点实体必须出现在流文本中——第一轮竞技场发现的
   "标答引用盲卷不存在信息"缺陷，本次从我方出题侧结构性杜绝；
2. **方向性判卷**：同义词簇 + 红线判据，严禁死板字句匹配；
3. **高熵交织**：核心大事（跨维度冲突/转折）与海量琐碎日常、语义陷阱
   （玩笑/吹牛/惊悚新闻/砍一刀/他人生活）在时间轴上交错；
4. **确定性**：seed 化随机，同种子逐字节可复现；
5. **时间轴**：事件全部落在 07:00~23:30，睡眠窗口由传感器宏观摘要承载。

用法::

    python benchmarks/daily_summary/generators/daily_life_generator_01a0aa2c.py \
        --count 10000 --out benchmarks/daily_summary/questions/questions_daily_life_01a0aa2c.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_life_pools_01a0aa2c import (  # noqa: E402
    ARCHETYPES,
    ARCHETYPE_FINANCE,
    BOSS_TITLES,
    CAREER_STATES,
    CITIES,
    COLLEAGUES,
    COMPANIES,
    DEFAULT_FINANCE_POOL,
    EMOTION_STATES,
    FINANCE_EVENTS,
    FRIENDS,
    FEMALE_NAMES,
    FULL_NAMES,
    HEALTH_STATES,
    HOSPITALS,
    INTENSITY_HR,
    MALE_NAMES,
    OCCUPATIONS,
    PERSONALITIES,
    RELATIONSHIPS,
    SOCIAL_STATES,
    TRAP_EVENTS,
    TRIVIAL_EVENTS,
)

GENERATOR_AGENT = "01a0aa2c-fantonghui"
BASE_SEED = 0x01A0AA2C
DAY_START_MIN = 7 * 60
DAY_END_MIN = 23 * 60 + 30

#: 全局主线证据需纳入财务事件的原型（spine 本身含财务要素）
GLOBAL_FIN_ARCHETYPES = {"OVERDUE_ANXIETY", "BONUS_REPAY_DAY", "INVESTMENT_CRASH", "FRIEND_LOAN_REQUEST"}

#: 必选琐碎事件（传感器宏观量的可观测载体：静息心率/睡眠/步数/夜间心率）
MANDATORY_TRIVIAL_TIMES = ("07:35", "07:45", "13:15", "17:30", "22:40")

#: 各原型核心事件表：(时间, 来源, x1, x2, 文本)；evidence 为核心事件索引 → 维度映射
CORE_SPECS = {
    "BREAKUP_AFTER_CRITICISM": {
        "events": [
            ("10:02", "mic", "{boss}", "季度晨会", "这季度数据这么难看？方案打回重做，按整改意见明天上午给我新版"),
            ("10:06", "mic", "{colleague}", "低声安慰", "别往心里去，他今天火气大，当众批评谁都难堪"),
            ("21:05", "app", "微信", "女友{gf}", "我们分手吧，这样下去太累了，别再找我了"),
            ("21:08", "mic", "女友{gf}", "通话", "我说的认真的，就到这里吧，保重"),
        ],
        "anomaly": ("21:09", "hr_spike"),
        "evidence": {"global": [0, 2, 3], "dim:social": [2, 3], "dim:career": [0], "dim:emotion": [0, 2]},
    },
    "LONGDIST_FIGHT": {
        "events": [
            ("21:30", "mic", "女友{gf}", "视频通话", "又爆发争吵：你到底什么时候能搬过来？我等了整整一年了"),
            ("21:55", "app", "微信", "女友{gf}", "先这样吧，都冷静几天，别打电话了"),
            ("23:00", "mic", "本人", "睡前自语", "异地这么久，这次争吵怕是过不去了……睡吧"),
        ],
        "anomaly": ("21:32", "hr_spike"),
        "evidence": {"global": [0, 1, 2], "dim:social": [0, 1], "dim:emotion": [0, 2]},
    },
    "DIVORCE_TALK": {
        "events": [
            ("20:40", "mic", "{spouse}", "客厅谈话", "我想清楚了，我们离婚吧，房子车子都好商量"),
            ("21:10", "mic", "{spouse}", "客厅谈话", "财产分割下周找时间列个清单，孩子的事慢慢谈"),
            ("23:15", "mic", "本人", "失眠自语", "走到离婚这一步……真是没想到"),
            ("21:30", "app", "微信", "{spouse}", "离婚协议的草稿我先发你了，条款你先看，有意见标出来"),
        ],
        "anomaly": ("20:42", "hr_spike"),
        "evidence": {"global": [0, 1, 3], "dim:social": [0, 1, 3], "dim:emotion": [0, 2]},
    },
    "PARTNER_COLDWAR": {
        "events": [
            ("19:55", "mic", "本人", "发现异常", "这位是谁？半夜还在给你发这种暧昧消息……你解释一下这些聊天记录"),
            ("20:10", "mic", "{spouse}", "冷战开始", "没什么好解释的，你爱怎么想怎么想"),
            ("23:20", "mic", "本人", "睡前自语", "就这么冷战下去吗……算了，睡了"),
            ("23:25", "app", "微信", "{spouse}", "今晚你睡书房吧，我需要静一静"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 3], "dim:social": [0, 1, 3], "dim:emotion": [0]},
    },
    "RECONCILE_DEEPTALK": {
        "events": [
            ("20:30", "mic", "女友{gf}", "深夜长谈", "这段时间是我不好，冷落了你，你别往心里去"),
            ("21:40", "mic", "本人", "长谈回应", "我也有错。我们和好，以后有话当天说开，不攒着"),
            ("22:30", "app", "微信", "女友{gf}", "晚安，明天一起吃你最爱的那家火锅呀"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:social": [0, 1, 2], "dim:emotion": [0, 1]},
    },
    "PROPOSAL_SUCCESS_DAY": {
        "events": [
            ("17:50", "app", "支付宝", "官方", "您预订的餐厅今晚18:30已确认，祝用餐愉快"),
            ("19:40", "mic", "本人", "求婚现场", "……嫁给我吧。戒指递出去那一刻我手都在抖"),
            ("20:05", "mic", "女友{gf}", "求婚现场", "我答应了！哭得妆都花了，傻子"),
            ("21:30", "app", "微信", "女友{gf}", "跟爸妈报喜啦，他们说下周就来提亲，求婚成功！"),
        ],
        "anomaly": ("19:41", "hr_spike"),
        "evidence": {"global": [1, 2, 3], "dim:social": [1, 2, 3], "dim:emotion": [1, 2]},
    },
    "FAMILY_ILLNESS_CALL": {
        "events": [
            ("14:20", "app", "微信", "{kin}{kinname}", "检查结果出来了，医生让马上住院，你别慌"),
            ("14:25", "mic", "本人", "回电", "妈你先在诊室等着，我现在请假买票过去"),
            ("15:00", "app", "钉钉", "{boss}", "已批你的事假，工作先交接给{colleague}，家里要紧"),
            ("21:50", "mic", "本人", "医院走廊", "住院手续办完了，今晚我陪护守着，你先睡"),
            ("22:10", "sensor", "", "", "连日奔波疲劳度显著，需警惕体力透支"),
        ],
        "anomaly": ("14:22", "hr_spike"),
        "evidence": {"global": [0, 2, 3], "dim:social": [0, 3], "dim:career": [2], "dim:emotion": [0, 1], "dim:health": [4]},
    },
    "NEIGHBOR_DISPUTE_DAY": {
        "events": [
            ("19:30", "mic", "邻居", "门口对峙", "说了多少次了，{dispute}必须给个说法，今天说不清楚谁也别走"),
            ("19:45", "mic", "邻居", "门口对峙", "行了行了，物业来了让他们评评理"),
            ("21:00", "app", "微信-业主群", "物业管家", "收到您的{dispute}投诉，明天上门核实调解"),
        ],
        "anomaly": ("19:32", "hr_spike"),
        "evidence": {"global": [0, 1, 2], "dim:social": [0, 1, 2], "dim:emotion": [0]},
    },
    "FRIEND_LOAN_REQUEST": {
        "events": [
            ("12:50", "mic", "{friend}", "午餐来电", "兄弟，想借{amount}万周转半年，利息按银行算，你看行不"),
            ("13:20", "mic", "本人", "犹豫回应", "金额太大了，我回家跟家里人商量一下，这两天回你"),
            ("22:50", "mic", "本人", "睡前自语", "{amount}万不是小数……借还是不借，愁人"),
            ("13:05", "app", "微信", "{friend}", "兄弟，商量得怎么样？{amount}万我月底急用，实在为难就算了"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 3, 2], "dim:social": [0, 3], "dim:emotion": [1, 2], "dim:finance": [0, 3]},
    },
    "LAB_CRITICAL_NOTICE": {
        "events": [
            ("09:15", "app", "短信", "{hospital}", "【{hospital}】危急值通知：您昨日体检{lab}结果{labval}，已达危急值，请尽快复诊"),
            ("09:20", "mic", "本人", "门诊回电", "好，我挂下周一心内科的号……这个危急值严不严重？"),
            ("21:40", "app", "微信", "文件传输助手", "复诊材料清单：体检报告+医保卡+既往病史，周日提前整理"),
        ],
        "anomaly": ("09:16", "hr_spike"),
        "evidence": {"global": [0, 1, 2], "dim:health": [0, 1], "dim:emotion": [0, 1]},
    },
    "NIGHT_CHEST_ER": {
        "events": [
            ("22:35", "mic", "本人", "突发不适", "胸口……闷得慌，出冷汗，扶我一下"),
            ("22:50", "app", "微信", "{colleague}", "我可能要去趟{hospital}急诊，明早帮我跟{boss}请假"),
            ("23:15", "sensor", "", "", "急诊途中：心率{bpm}bpm，胸闷胸痛症状持续"),
        ],
        "anomaly": ("22:36", "hr_spike"),
        "evidence": {"global": [0, 1, 2], "dim:health": [0, 2], "dim:career": [1], "dim:emotion": [0]},
    },
    "CHRONIC_WORSE_DAY": {
        "events": [
            ("09:30", "app", "短信", "{hospital}", "【{hospital}】您的{chronic}复查结果较上次恶化，请严格控制饮食作息并按时服药"),
            ("10:00", "mic", "本人", "工位自语", "指标又升了……应酬推掉，晚饭也吃得清淡点吧"),
            ("19:30", "mic", "{colleague}", "应酬邀约", "晚上聚餐你可必须来啊，就缺你了"),
            ("19:35", "mic", "本人", "婉拒", "真去不了，{chronic}刚恶化，医嘱忌口，下次我请"),
            ("21:50", "app", "钉钉", "{boss2}", "明晚的版本评审提前到九点，今晚再对一轮，辛苦加班"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 3, 4], "dim:health": [0, 1, 3], "dim:emotion": [1], "dim:career": [4]},
    },
    "INVESTMENT_CRASH": {
        "events": [
            ("10:25", "mic", "本人", "工位自语", "又跌{pct}%……到底止损还是补仓，一整天心神不宁"),
            ("21:35", "app", "微信-基金群", "群友", "这波回撤太狠了，都在讨论要不要割肉"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1], "dim:emotion": [0, 1]},
    },
    "OVERDUE_ANXIETY": {
        "events": [
            ("12:30", "mic", "本人", "午间自语", "早上银行提示余额不足……下午先找{colleague}周转一点，千万别上征信"),
            ("18:05", "app", "{bank}", "{bank}", "【{bank}】您的信用卡还款{amt}元扣款失败，请今日24点前补足，逾期将影响征信"),
            ("21:40", "app", "钉钉", "{boss2}", "今晚的对账数据再核一轮才能下班，加班处理，明早给我结果"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1], "dim:finance": [1], "dim:emotion": [0], "dim:career": [2]},
    },
    "BONUS_REPAY_DAY": {
        "events": [
            ("16:30", "app", "企业微信", "{boss}", "与{client}的合同正式盖章了，这单你牵头功不可没，签约成功！"),
            ("14:10", "app", "{bank}", "{bank}", "您申请的提前归还部分房贷已受理，月供将相应下调"),
            ("17:30", "mic", "本人", "下班自语", "奖金到账了，先还掉一部分房贷，轻松一点是一点"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:career": [0], "dim:finance": [1], "dim:emotion": [2]},
    },
    "PROMOTION_FAMILY_ILL": {
        "events": [
            ("11:30", "app", "钉钉", "{boss}", "恭喜！晋升答辩全票通过，下月起你正式担任{position}"),
            ("15:40", "app", "微信", "{kin}{kinname}", "复查结果出来了，医生确诊要住院，你别慌，先听安排"),
            ("16:10", "mic", "本人", "走廊自语", "上午还在高兴晋升{position}，下午就……这叫什么事"),
            ("21:30", "app", "钉钉", "{boss}", "家里情况了解了，下周交接会我替你安排，先陪家人"),
            ("22:10", "sensor", "", "", "全天疲劳度偏高，下午情绪震荡后精力透支"),
        ],
        "anomaly": ("15:42", "hr_spike"),
        "evidence": {"global": [0, 1, 2], "dim:career": [0], "dim:social": [1], "dim:emotion": [2], "dim:health": [4]},
    },
    "EXAM_PASS_SICK": {
        "events": [
            ("15:20", "app", "微信", "{friend}", "查分了吗？你过了！{exam}通过了！"),
            ("15:25", "mic", "本人", "欣喜自语", "过了过了！这一年没白熬"),
            ("21:00", "sensor", "", "", "晚间低烧37.8℃，咳嗽乏力，体力下降"),
            ("21:10", "app", "美团买药", "骑手", "布洛芬+止咳糖浆已送达，请按时用药"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:career": [0, 1], "dim:health": [2, 3], "dim:emotion": [1]},
    },
    "OLDFRIEND_REUNION": {
        "events": [
            ("18:40", "mic", "{friend}", "重逢寒暄", "十来年没见了！你还是老样子，走走走，今晚不醉不归"),
            ("21:20", "mic", "{friend}", "酒过三巡", "对了，我现在做理财，有个年化12%的项目，兄弟带你一个"),
            ("21:25", "mic", "本人", "婉拒", "理财就算了，我只买存款。来，喝茶喝茶"),
            ("22:45", "mic", "本人", "回家路上", "今天重逢聊得真尽兴，就是这一身酒气……"),
            ("17:55", "app", "微信", "{friend}", "到老地方了！你到哪了？我先点菜"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 3, 4], "dim:social": [0, 4], "dim:emotion": [3]},
    },
    "PROMOTION_LOST_DAY": {
        "events": [
            ("16:00", "app", "钉钉", "人事", "本次{position}竞聘结果公示：很遗憾您未入选，感谢参与"),
            ("16:20", "mic", "本人", "工位自语", "竞聘还是败了……这两年白拼了"),
            ("18:30", "mic", "猎头顾问", "来电", "看到您在圈内的口碑，有个{position}机会薪资上浮40%，考虑吗"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:career": [0, 1, 2], "dim:emotion": [1]},
    },
    "LAID_OFF_DAY": {
        "events": [
            ("11:10", "app", "钉钉", "{boss}", "因业务收缩启动裁员，你的岗位在列，{days}天内完成交接"),
            ("11:15", "mic", "本人", "工位自语", "被裁了……房贷每个月一万二，这可怎么办"),
            ("14:30", "app", "{bank}", "{bank}", "【{bank}】提醒：您的房贷本月应还12000元，还款日为下月1日"),
        ],
        "anomaly": ("11:12", "hr_spike"),
        "evidence": {"global": [0, 1, 2], "dim:career": [0], "dim:finance": [2], "dim:emotion": [1]},
    },
    "ACCIDENT_BLAMED_DAY": {
        "events": [
            ("09:50", "app", "钉钉-全员", "行政", "通报批评：昨日{sysname}线上事故造成资损，责任人{me}记过一次"),
            ("10:05", "mic", "{boss}", "点名问责", "当着大家的面批评你，{sysname}这事必须给公司一个交代，检讨明天交我"),
            ("22:00", "mic", "本人", "加班自语", "如坐针毡一整天……检讨还差一半，继续写吧"),
        ],
        "anomaly": ("09:52", "hr_spike"),
        "evidence": {"global": [0, 1, 2], "dim:career": [0, 1], "dim:social": [1], "dim:emotion": [2]},
    },
    "CONTRACT_MISSED_ANNIVERSARY": {
        "events": [
            ("16:30", "app", "企业微信", "{boss}", "与{client}正式签约完成！庆功宴今晚6点半，主角缺席不合适吧"),
            ("20:15", "app", "微信", "女友{gf}", "今天是我们的纪念日。我订的餐厅，一个人坐到了打烊"),
            ("20:16", "app", "微信", "女友{gf}", "你总是这样。有些失望攒多了就散了，你自己想想吧"),
            ("22:40", "mic", "本人", "回家路上", "单子签下来了，纪念日却搞砸了……她不接电话了"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 3], "dim:career": [0], "dim:social": [1, 2], "dim:emotion": [3]},
    },
    "OFFER_NEWJOB_DAY": {
        "events": [
            ("10:50", "app", "邮件", "{company}HR", "恭喜您通过全部面试，正式发放offer，薪资上浮35%，一周内答复"),
            ("11:00", "mic", "本人", "工位自语", "{company}的offer来了……走还是留，真难抉择"),
            ("21:20", "mic", "本人", "睡前权衡", "涨幅是心动，但还没想好怎么跟{boss}提离职的事"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:career": [0, 1, 2], "dim:emotion": [1, 2]},
    },
    "RESIGN_SUBMITTED_DAY": {
        "events": [
            ("09:40", "app", "钉钉", "本人-离职申请", "辞职申请已提交：个人职业规划原因，望批准"),
            ("10:10", "mic", "{boss}", "离职面谈", "想清楚了？公司培养你不容易……好，我签字，交接按两周排"),
            ("10:30", "mic", "本人", "面谈后自语", "字签了，辞职这事终于说出口了，轻松又忐忑"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:career": [0, 1], "dim:emotion": [2]},
    },
    "QUIET_WEEKEND": {
        "events": [
            ("10:30", "sensor", "", "", "周末补觉后自然醒，精神恢复良好"),
            ("15:40", "app", "顺丰速运", "官方", "您抢购的心仪好物已送达驿站，凭码{code}取件"),
            ("16:00", "mic", "本人", "取件自语", "蹲了半个月终于抢到了，小确幸！"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:emotion": [2]},
    },
    "REMOTE_QUIET_DAY": {
        "events": [
            ("09:30", "app", "钉钉", "视频例会", "远程例会10分钟结束，今日交付物照常推进"),
            ("18:40", "app", "美团外卖", "官方", f"很抱歉您的订单超时30分钟，已赔付{{payout}}元红包"),
            ("18:45", "mic", "本人", "晚餐自语", "超是超了点，好歹赔了红包，凑合吧"),
        ],
        "anomaly": None,
        "evidence": {"global": [0, 1, 2], "dim:emotion": [2]},
    },
}


# ---------------------------------------------------------------------------
# 槽位抽取
# ---------------------------------------------------------------------------


def make_slots(rng: random.Random, arch_id: str, fin_key: str) -> dict:
    """为一天抽取全部槽位值（人名/金额/体征基线等）。"""
    spouse_sex = rng.choice(("妻", "夫"))
    spouse_name = rng.choice(FEMALE_NAMES) if spouse_sex == "妻" else rng.choice(MALE_NAMES)
    kin, kinname = rng.choice(
        (("母亲", rng.choice(FEMALE_NAMES)), ("父亲", rng.choice(MALE_NAMES)))
    )
    slots = {
        "gf": rng.choice(FEMALE_NAMES),
        "spouse": (f"妻子{spouse_name}" if spouse_sex == "妻" else f"丈夫{spouse_name}"),
        "boss": rng.choice(BOSS_TITLES),
        "boss2": rng.choice(BOSS_TITLES),
        "colleague": rng.choice(COLLEAGUES),
        "friend": rng.choice(FRIENDS),
        "hospital": rng.choice(HOSPITALS),
        "chronic": rng.choice(("2型糖尿病", "高血压", "高尿酸血症")),
        "dispute": rng.choice(("装修噪音扰民", "楼道堆物占道", "漏水泡了地板")),
        "position": rng.choice(("高级经理", "技术总监", "部门负责人", "项目总监")),
        "days": rng.choice(("7", "14", "30")),
        "sysname": rng.choice(("订单系统", "支付网关", "库存中台")),
        "client": rng.choice(COMPANIES),
        "company": rng.choice(COMPANIES),
        "exam": rng.choice(
            ("注册会计师综合阶段考试", "一级建造师考试", "法律职业资格考试", "高级工程师评审")
        ),
        "amount": str(rng.choice((3, 5, 8, 10, 12, 15, 20, 30))),
        "pct": f"{rng.uniform(2.8, 9.6):.1f}",
        "bank": rng.choice(("招商银行", "工商银行", "建设银行", "浦发银行", "民生银行")),
        "tail": f"{rng.randrange(1000, 10000)}",
        "kin": kin,
        "kinname": kinname,
        "me": rng.choice(FULL_NAMES),
        "rest": str(rng.randrange(58, 77)),
        "steps": str(rng.randrange(2800, 13500, 37) // 10 * 10),
        "temp": str(rng.randrange(3, 10)),
        "tiny": str(rng.randrange(12, 260)),
        "payout": str(rng.randrange(8, 40)),
        "code": f"{rng.randrange(100, 10000)}",
        "m": str(rng.randrange(1, 13)),
    }
    lab_pairs = (
        ("肌钙蛋白I", "0.61ng/mL"), ("空腹血糖", "11.8mmol/L"),
        ("D-二聚体", "5.2mg/L"), ("血钾", "6.1mmol/L"),
    )
    slots["lab"], slots["labval"] = rng.choice(lab_pairs)

    # 财务金额语义（按事件类型）：FUND_LOSS 用亏损额，BONUS 用奖金额，其余用账单额
    if fin_key == "FUND_LOSS":
        if arch_id == "INVESTMENT_CRASH":
            loss_wan = round(rng.uniform(1.2, 8.5), 1)
            slots["amt"] = str(int(loss_wan * 10000))
            slots["loss_wan"] = f"{loss_wan:.1f}"
        else:
            slots["amt"] = str(rng.randrange(800, 9800, 50))
            slots["loss_wan"] = f"{int(slots['amt']) / 10000:.2f}"
    elif fin_key == "BONUS_IN":
        slots["amt"] = str(rng.randrange(80, 460) * 100)
    elif fin_key == "SALARY_IN":
        slots["amt"] = str(rng.randrange(80, 260) * 100)
    else:
        slots["amt"] = str(rng.randrange(120, 680, 4) * 10)

    # 睡眠/体征按剧情调制
    arch = ARCHETYPES[arch_id]
    if arch["health"] == "CAREGIVER_STRAIN":
        slots["sleep"] = f"{rng.uniform(3.4, 4.9):.1f}"
    elif arch["health"] == "EMOTIONAL_TACHY":
        slots["sleep"] = f"{rng.uniform(4.4, 6.1):.1f}"
    else:
        slots["sleep"] = f"{rng.uniform(5.6, 8.4):.1f}"
    slots["deep"] = f"{float(slots['sleep']) * rng.uniform(0.18, 0.28):.1f}"
    slots["hr2"] = str(int(slots["rest"]) + rng.randrange(8, 21))
    lo, hi = INTENSITY_HR[arch["intensity"]]
    slots["bpm"] = str(rng.randrange(lo, hi + 1))
    slots["dur"] = str(rng.choice((4, 5, 6, 8, 10)))
    return slots


def _to_min(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def _fmt_time(t: int) -> str:
    return f"{t // 60:02d}:{t % 60:02d}"


def _jitter(hhmm: str, rng: random.Random, max_off: int = 6) -> int:
    t = _to_min(hhmm) + rng.randrange(-max_off, max_off + 1)
    return max(DAY_START_MIN, min(DAY_END_MIN, t))


def _fill(template: str, slots: dict) -> str:
    return template.format(**slots)


# ---------------------------------------------------------------------------
# 单题构造
# ---------------------------------------------------------------------------


def build_question(idx: int) -> dict:
    rng = random.Random(BASE_SEED + idx * 7919)

    # 1) 剧情原型（加权）与财务事件（先定，金额槽位依赖它）
    arch_ids = list(ARCHETYPES)
    weights = [ARCHETYPES[a]["weight"] for a in arch_ids]
    arch_id = rng.choices(arch_ids, weights=weights, k=1)[0]
    arch = ARCHETYPES[arch_id]
    fin_key = rng.choice(ARCHETYPE_FINANCE.get(arch_id, DEFAULT_FINANCE_POOL))
    slots = make_slots(rng, arch_id, fin_key)

    # 2) 人设
    persona = {
        "persona_id": f"P{idx:05d}",
        "age": rng.randrange(24, 52),
        "occupation": rng.choice(OCCUPATIONS),
        "city": rng.choice(CITIES),
        "relationship": rng.choice(RELATIONSHIPS),
        "personality": rng.choice(PERSONALITIES),
        "name": rng.choice(FULL_NAMES),
    }

    # 3) 日期（QUIET_WEEKEND 强制周末）
    if arch_id == "QUIET_WEEKEND":
        d = date(2026, 1, 3) + timedelta(days=rng.randrange(0, 44) * 7 + rng.randrange(0, 2))
    else:
        d = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 360))
    day_date = d.isoformat()

    def mk_event(t: str, src: str, x1: str, x2: str, text: str, jitter: int = 5) -> dict:
        return {
            "_min": _jitter(t, rng, jitter),
            "src": src,
            "x1": _fill(x1, slots) if "{" in x1 else x1,
            "x2": _fill(x2, slots) if "{" in x2 else x2,
            "text": _fill(text, slots),
        }

    # 4) 核心事件 + 心率异常事件
    spec = CORE_SPECS[arch_id]
    core_events = [mk_event(*e) for e in spec["events"]]
    anomalies = []
    anomaly_event = None
    if spec["anomaly"]:
        at, kind = spec["anomaly"]
        detail = f"心率骤升至{slots['bpm']}bpm（持续{slots['dur']}分钟）"
        anomaly_event = mk_event(at, "sensor", "", "", detail, jitter=2)
        anomalies.append({"t": _fmt_time(anomaly_event["_min"]), "kind": kind, "detail": detail})

    # 5) 琐碎日常（传感器宏观量事件必选）+ 语义陷阱
    mandatory = [e for e in TRIVIAL_EVENTS if e[0] in MANDATORY_TRIVIAL_TIMES]
    trivial_pool = [e for e in TRIVIAL_EVENTS if e[0] not in MANDATORY_TRIVIAL_TIMES]
    chosen_trivial = mandatory + rng.sample(trivial_pool, rng.randrange(8, 13))
    trivial_events = [mk_event(*e) for e in chosen_trivial]
    n_traps = rng.choices((0, 1, 2, 3), weights=(3, 4, 2, 1), k=1)[0]
    trap_events = [mk_event(*e, jitter=8) for e in rng.sample(list(TRAP_EVENTS), n_traps)]

    # 6) 财务事件（与核心事件解耦滚动）
    fin_event = None
    if fin_key not in ("NONE", "LOAN_PENDING"):
        _src, _app, _sender, _text = FINANCE_EVENTS[fin_key]["event"]
        ftimes = ("08:05", "08:30", "10:05") if arch_id in ("BONUS_REPAY_DAY", "INVESTMENT_CRASH") else ("08:05", "08:30", "11:05", "13:40", "16:55")
        fin_event = mk_event(rng.choice(ftimes), _src, _app, _sender, _text, jitter=4)

    # 7) 合成时间轴：排序、同分钟去重、编号
    all_events = core_events + trivial_events + trap_events
    if anomaly_event is not None:
        all_events.append(anomaly_event)
    if fin_event is not None:
        all_events.append(fin_event)
    all_events.sort(key=lambda e: (e["_min"], e["src"] != "mic", e["text"]))
    used = set()
    for e in all_events:
        while e["_min"] in used and e["_min"] < DAY_END_MIN:
            e["_min"] += 1
        used.add(e["_min"])
    core_id_map = {}
    events_out = []
    for i, ev in enumerate(sorted(all_events, key=lambda e: e["_min"])):
        ev_id = f"e{i + 1:02d}"
        t = _fmt_time(ev["_min"])
        if ev in core_events:
            core_id_map[core_events.index(ev)] = ev_id
        item = {"id": ev_id, "t": t, "src": ev["src"]}
        if ev["src"] == "mic":
            item["from"] = ev["x1"]
            item["scene"] = ev["x2"]
        elif ev["src"] == "app":
            item["app"] = ev["x1"]
            item["from"] = ev["x2"]
        item["text"] = ev["text"]
        events_out.append(item)
    fin_event_id = None
    if fin_event is not None:
        fin_event_id = next(e["id"] for e in events_out if e["text"] == fin_event["text"])
    anomaly_id = None
    if anomaly_event is not None:
        anomaly_id = next(e["id"] for e in events_out if e["text"] == anomaly_event["text"])

    # 8) 传感器宏观摘要
    sensor_summary = {
        "morning_rest_hr": int(slots["rest"]),
        "total_steps": int(slots["steps"]),
        "sleep_hours": float(slots["sleep"]),
        "sleep_window": f"{_fmt_time(rng.randrange(23 * 60 + 33, 23 * 60 + 56))}-{_fmt_time(rng.randrange(6 * 60 + 38, 7 * 60 + 18))}",
        "anomalies": anomalies,
    }

    # 9) 六维方向性标答
    gt = build_ground_truth(arch_id, slots, spec, core_id_map, fin_event_id, fin_key,
                            anomaly_id, events_out)

    # 10) 难度（陷阱密度 + 冲突隐蔽度）
    if n_traps >= 2:
        difficulty = "ADVERSARIAL"
    elif n_traps == 1:
        difficulty = "HARD"
    elif arch["intensity"] == "HIGH":
        difficulty = "EASY"
    else:
        difficulty = "MEDIUM"

    return {
        "question_id": f"QDAY_{GENERATOR_AGENT}_{idx:05d}",
        "generator_agent": GENERATOR_AGENT,
        "timestamp_utc": f"{day_date}T12:00:00Z",
        "date": day_date,
        "difficulty": difficulty,
        "persona": persona,
        "cleaned_daily_stream": {
            "date": day_date,
            "sensor_summary": sensor_summary,
            "events": events_out,
        },
        "directional_ground_truth": gt,
    }


def build_ground_truth(arch_id: str, slots: dict, spec: dict, core_id_map: dict,
                       fin_event_id: str | None, fin_key: str, anomaly_id: str | None,
                       events_out: list) -> dict:
    arch = ARCHETYPES[arch_id]
    state_slots = dict(slots)
    if anomaly_id is not None:
        state_slots["t"] = next(e["t"] for e in events_out if e["id"] == anomaly_id)
    else:
        state_slots["t"] = "21:00"

    def ev_ids(dim: str) -> list:
        ids = [core_id_map[i] for i in spec["evidence"].get(dim, [])]
        if dim == "dim:health" and anomaly_id:
            ids.append(anomaly_id)
        if dim == "dim:finance" and fin_event_id:
            ids.insert(0, fin_event_id)
        if dim == "global" and fin_event_id and arch_id in GLOBAL_FIN_ARCHETYPES:
            ids.append(fin_event_id)
        return ids

    def dim_block(dim_id: str, state_pool: dict, state_key: str) -> dict:
        st = state_pool[state_key]
        return {
            "dimension_id": dim_id,
            "core_anchor": _fill(st.get("core") or st["gt_core"], state_slots),
            "accepted_synonyms": [_fill(s, state_slots) for s in st["syns"]],
            "redline_criteria": [_fill(s, state_slots) for s in st["reds"]],
            "anchor_entities": [_fill(e, state_slots) for e in st.get("ents", ()) if e],
            "evidence_event_ids": ev_ids(dim_id),
        }

    dims = [
        dim_block("dim:health", HEALTH_STATES, arch["health"]),
        dim_block("dim:social", SOCIAL_STATES, arch["social"]),
        dim_block("dim:emotion", EMOTION_STATES, arch["emotion"]),
        dim_block("dim:finance", FINANCE_EVENTS, fin_key),
        dim_block("dim:career", CAREER_STATES, arch["career"]),
    ]

    # 全局主线（spine + 关键人物/事件实体；仅保留当日语料中真实可观测者）
    corpus = " ".join(
        e.get("text", "") + " " + e.get("from", "") + " " + e.get("app", "")
        + " " + e.get("scene", "") for e in events_out
    )
    global_entities = []
    for label in (
        f"女友{slots['gf']}", slots["spouse"], slots["boss"], slots["friend"],
    ):
        if label in corpus and label not in global_entities:
            global_entities.append(label)
    if arch["social"] == "FAMILY_ILLNESS" and f"{slots['kin']}{slots['kinname']}" in corpus:
        global_entities.append(f"{slots['kin']}{slots['kinname']}")
    for w in {
        "GIRLFRIEND_BREAKUP": ("分手",), "SPOUSE_DIVORCE": ("离婚",), "LONGDIST_FIGHT": ("争吵",),
        "PARTNER_COLDWAR": ("冷战",), "PROPOSAL_SUCCESS": ("求婚",), "FRIEND_REUNION": ("重逢",),
        "FRIEND_LOAN_TENSION": (f"{slots['amount']}万",), "ANNIVERSARY_MISSED": ("纪念日",),
    }.get(arch["social"], ()):
        if w not in global_entities:
            global_entities.append(w)
    for w in {
        "CRITICIZED_REDO": ("整改",), "CONTRACT_WON": ("签约",), "PROMOTION_WON": ("晋升",),
        "LAID_OFF_NOTICE": ("裁员",), "ACCIDENT_BLAMED": ("通报批评",), "EXAM_PASS": ("通过",),
    }.get(arch["career"], ()):
        if w not in global_entities:
            global_entities.append(w)

    return {
        "global_daily_summary": {
            "dimension_id": "global",
            "core_anchor": _fill(arch["spine"], state_slots),
            "accepted_synonyms": list(arch["spine_syns"]),
            "redline_criteria": list(arch["spine_reds"]),
            "anchor_entities": global_entities[:6],
            "evidence_event_ids": ev_ids("global"),
            "plot_family": arch["family"],
            "intensity": arch["intensity"],
        },
        "dimensions": dims,
    }


# ---------------------------------------------------------------------------
# 质检：可观测性与结构自检
# ---------------------------------------------------------------------------


def verify_question(q: dict) -> list:
    issues = []
    stream = q["cleaned_daily_stream"]
    events = stream["events"]
    corpus = " ".join(
        e.get("text", "") + " " + e.get("from", "") + " " + e.get("app", "")
        + " " + e.get("scene", "") for e in events
    )
    ss = stream["sensor_summary"]
    for a in ss["anomalies"]:
        corpus += " " + a["detail"]
    corpus += f" {ss['morning_rest_hr']}bpm {ss['total_steps']}步 {ss['sleep_hours']}小时"

    ids = [e["id"] for e in events]
    if len(ids) != len(set(ids)):
        issues.append("event id 重复")
    times = [_to_min(e["t"]) for e in events]
    if times != sorted(times):
        issues.append("事件未按时间排序")
    if any(t < DAY_START_MIN or t > DAY_END_MIN for t in times):
        issues.append("事件越界（须在07:00~23:30）")
    if len(events) < 15:
        issues.append(f"事件过少：{len(events)}")

    gt = q["directional_ground_truth"]
    blocks = [gt["global_daily_summary"]] + gt["dimensions"]
    if len(gt["dimensions"]) != 5:
        issues.append("维度数不为5")
    dim_ids = [b["dimension_id"] for b in gt["dimensions"]]
    if dim_ids != ["dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"]:
        issues.append(f"维度顺序异常：{dim_ids}")
    for b in blocks:
        dim = b["dimension_id"]
        if set(b["accepted_synonyms"]) & set(b["redline_criteria"]):
            issues.append(f"{dim}: 同义词簇与红线重叠")
        if not b["core_anchor"] or not b["accepted_synonyms"] or not b["redline_criteria"]:
            issues.append(f"{dim}: 标答字段缺失")
        for ent in b["anchor_entities"]:
            if ent and ent not in corpus:
                issues.append(f"{dim}: 锚点实体不可观测: {ent!r}")
        for ev_id in b["evidence_event_ids"]:
            if ev_id not in ids:
                issues.append(f"{dim}: 证据事件不存在: {ev_id}")
    # 铁律③：每题必须含跨维度冲突或转折（全局 evidence ≥3 且非单一来源）
    if len(gt["global_daily_summary"]["evidence_event_ids"]) < 3:
        issues.append("全局证据事件不足3条")
    return issues


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def generate(count: int, out_path: Path, verify: bool = True) -> dict:
    questions = []
    seen_ids = set()
    arch_counter = Counter()
    diff_counter = Counter()
    n_events_total = 0
    for idx in range(1, count + 1):
        q = build_question(idx)
        if q["question_id"] in seen_ids:
            raise SystemExit("question_id 冲突")
        seen_ids.add(q["question_id"])
        arch_counter[q["directional_ground_truth"]["global_daily_summary"]["plot_family"]] += 1
        diff_counter[q["difficulty"]] += 1
        n_events_total += len(q["cleaned_daily_stream"]["events"])
        if verify:
            issues = verify_question(q)
            if issues:
                raise SystemExit(f"自检失败 {q['question_id']}: {issues}")
        questions.append(q)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for q in questions:
            fh.write(json.dumps(q, ensure_ascii=False, separators=(",", ":")) + "\n")

    stats = {
        "generator_agent": GENERATOR_AGENT,
        "generator_version": "v1",
        "seed": hex(BASE_SEED),
        "total_questions": count,
        "file": str(out_path),
        "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "size_mb": round(out_path.stat().st_size / 1e6, 2),
        "avg_events_per_day": round(n_events_total / max(count, 1), 2),
        "plot_family_distribution": dict(arch_counter.most_common()),
        "difficulty_distribution": dict(diff_counter.most_common()),
        "dimension_schema": ["global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"],
        "observability_check": "passed" if verify else "skipped",
        "grading_rule": (
            "判卷以方向为准：命中 core_anchor 或任一 accepted_synonyms 方向即得分；"
            "命中任一 redline_criteria 即该维一票否决（0 分）；"
            "严禁字句级死板匹配。"
        ),
        "note": (
            "每道试卷=一人一整天（07:00~23:30 事件流+传感器宏观摘要）；"
            "盲做时请剥离 directional_ground_truth 字段。"
        ),
    }
    manifest_path = out_path.parent / f"manifest_{out_path.stem.replace('questions_', '')}.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="AIOS 3.0 全天生活流出卷生成器")
    ap.add_argument("--count", type=int, default=10000)
    ap.add_argument(
        "--out", type=Path,
        default=Path("benchmarks/daily_summary/questions/questions_daily_life_01a0aa2c.jsonl"),
    )
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    stats = generate(args.count, args.out, verify=not args.no_verify)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
