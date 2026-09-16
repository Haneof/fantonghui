"""AIOS 3.0 全天生活流与多维总结出卷素材库（出卷战队 01a0aa2c-fantonghui）。

本模块是《Master Dispatch #11 路线图·第二步：全维度多尺度时间日志总结大考》的
出题素材库：人设池、五维方向性状态机（社交/情绪/健康/事业/财务）、琐碎日常事件池、
语义陷阱池与 22 个跨维度剧情原型。

设计铁律（吸取第一轮清洗竞技场的教训）：
1. **可观测性**：所有标答锚点实体（人名/金额/指标）必须出现在流文本中——
   出题方内部只允许引用自己写进流里的事实；
2. **方向性标答**：每维给出 core_anchor + accepted_synonyms（可接受同义词簇）
   + redline_criteria（绝对偏离红线），严禁死板字句匹配；
3. **高熵编织**：核心大事必须与海量琐碎日常、语义陷阱（玩笑/吹牛/惊悚新闻）
   交错，考验总结模型的信号提纯与反误报能力；
4. **确定性**：全部素材为纯数据 + 模板槽位，配合种子化随机可精确复现。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 基础槽位池（人设与人物名）
# ---------------------------------------------------------------------------

CITIES = ("北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "重庆", "苏州", "长沙")

OCCUPATIONS = (
    "后端工程师", "产品经理", "UI设计师", "会计", "行政专员", "销售顾问", "中学教师",
    "护士", "外卖骑手", "网约车司机", "门店店长", "基层公务员", "律师助理", "新媒体运营",
    "数据分析师", "测试工程师", "机械工程师", "药剂师", "银行柜员", "建筑设计师",
)

RELATIONSHIPS = ("恋爱2年", "恋爱5年", "异地恋1年", "新婚半年", "已婚未育", "已婚一孩", "单身", "离异独居")

PERSONALITIES = ("内敛隐忍", "外向健谈", "敏感细腻", "理性冷静", "急躁直率", "乐观豁达", "焦虑易压力")

FEMALE_NAMES = ("小雨", "梓琳", "晓萌", "诗涵", "梦瑶", "欣怡", "婉清", "若彤", "佳颖", "思远", "乐瑶", "清妍")
MALE_NAMES = ("陈默", "志豪", "子航", "一鸣", "泽宇", "俊杰", "立群", "浩然", "嘉树", "明轩")
FULL_NAMES = ("陈立", "林芳", "王倩", "李哲", "赵蕾", "周涛", "吴敏", "郑凯", "孙悦", "冯雪", "韩磊", "许静")

BOSS_TITLES = ("周总", "王总监", "李总", "张总", "刘总", "陈总", "赵总", "孙总", "吴总", "郑总", "林总", "何总")
COLLEAGUES = ("老赵", "小李", "阿坤", "大刘", "小周", "老徐", "小吴", "阿杰", "小郑", "老马", "小杨", "阿岚")
FRIENDS = ("发小大刘", "大学室友阿斌", "老同学周成", "发小石头", "挚友老高", "发小建国")
COMPANIES = ("星澜科技", "恒宇建材", "青禾生物", "拓远物流", "锐驰软件", "蓝湾食品", "中鼎装饰")
HOSPITALS = ("市第一人民医院", "中山医院", "华西医院", "仁济医院", "省人民医院", "协和医院")
PLATFORMS_APPS = ("微信", "企业微信", "钉钉", "美团", "京东", "支付宝", "招商银行", "抖音", "微博", "网易新闻")

#: 全天时间轴锚点（事件必须落在 07:00~23:30）
DAY_START_MIN = 7 * 60
DAY_END_MIN = 23 * 60 + 30

# ---------------------------------------------------------------------------
# 五维方向性状态机
# 每个状态: core(核心方向模板) / syns(可接受同义词簇) / reds(绝对红线) / ents(锚点实体模板)
# ---------------------------------------------------------------------------

SOCIAL_STATES = {
    "GIRLFRIEND_BREAKUP": {
        "core": "与女友{gf}关系破裂走向分手：晚间{gf}明确提出分手，恋情终结",
        "syns": ("分手", "感情破裂", "被提出分手", "恋人关系结束", "情侣分手", "关系破裂"),
        "reds": ("甜蜜互动", "求婚成功", "和好如初", "打情骂俏", "离婚"),
        "ents": ("女友{gf}", "分手"),
    },
    "SPOUSE_DIVORCE": {
        "core": "配偶{spouse}提出离婚并启动协商，婚姻关系濒临解体",
        "syns": ("离婚", "婚姻破裂", "提出离婚", "闹离婚", "婚姻危机", "协议离婚"),
        "reds": ("恩爱和睦", "婚姻升温", "备孕喜讯", "周年庆祝"),
        "ents": ("{spouse}", "离婚"),
    },
    "PARTNER_COLDWAR": {
        "core": "因发现{spouse}与异性暧昧聊天记录发生质问，关系陷入冷战",
        "syns": ("冷战", "争吵", "信任危机", "感情裂痕", "质问对峙", "关系恶化"),
        "reds": ("和好如初", "甜蜜互动", "信任加深"),
        "ents": ("{spouse}", "冷战"),
    },
    "LONGDIST_FIGHT": {
        "core": "与异地恋{gf}因聚少离多激烈争吵，和解未成，关系僵持",
        "syns": ("异地恋争吵", "情侣吵架", "闹矛盾", "关系紧张", "争吵冷战"),
        "reds": ("团聚见面", "感情升温", "和好如初"),
        "ents": ("女友{gf}", "争吵"),
    },
    "RECONCILE": {
        "core": "与{gf}的矛盾经深谈化解，关系和好修复",
        "syns": ("和好", "和解", "矛盾化解", "关系修复", "重归于好"),
        "reds": ("分手", "感情破裂", "冷战加剧"),
        "ents": ("{gf}", "和好"),
    },
    "PROPOSAL_SUCCESS": {
        "core": "向{gf}求婚成功，双方进入谈婚论嫁阶段",
        "syns": ("求婚成功", "答应求婚", "订婚", "步入婚姻"),
        "reds": ("求婚被拒", "分手", "争吵"),
        "ents": ("{gf}", "求婚"),
    },
    "FAMILY_ILLNESS": {
        "core": "{kin}{kinname}确诊重病住院，家庭进入陪护状态",
        "syns": ("家人重病", "家人住院", "确诊重病", "病重陪护", "住院通知"),
        "reds": ("家人康复出院", "体检一切正常", "全家健康"),
        "ents": ("{kin}{kinname}", "住院"),
    },
    "NEIGHBOR_DISPUTE": {
        "core": "与邻居因{dispute}发生纠纷冲突，关系对立",
        "syns": ("邻里纠纷", "与邻居冲突", "邻里矛盾", "对峙争吵"),
        "reds": ("邻里和睦", "互助友好"),
        "ents": ("邻居", "{dispute}"),
    },
    "FRIEND_LOAN_TENSION": {
        "core": "老友{friend}提出大额借款{amount}万请求，犹豫未决未应允",
        "syns": ("朋友借钱", "被请求借款", "借款请求", "友谊金钱考验"),
        "reds": ("已转账借出", "朋友还款", "合伙投资"),
        "ents": ("{friend}", "{amount}万"),
    },
    "BOSS_CONFLICT": {
        "core": "与领导{boss}因工作分歧产生冲突，被当众批评",
        "syns": ("与领导冲突", "被领导批评", "当众被批", "上司不满", "被指责"),
        "reds": ("受到表扬", "领导赞赏", "升职认可"),
        "ents": ("{boss}", "批评"),
    },
    "ANNIVERSARY_MISSED": {
        "core": "因工作错过与{gf}的纪念日，伴侣不满，关系需弥补",
        "syns": ("错过纪念日", "伴侣不满", "忽略伴侣", "纪念日爽约"),
        "reds": ("共度纪念日", "伴侣赞许", "惊喜庆祝"),
        "ents": ("{gf}", "纪念日"),
    },
    "FRIEND_REUNION": {
        "core": "与老友{friend}多年后重逢叙旧，社交联结恢复，席间婉拒其理财推销",
        "syns": ("老友重逢", "故友相聚", "多年好友再聚", "叙旧", "重逢尽兴"),
        "reds": ("与友人反目", "借钱撕破脸", "被拉去投资", "错失见面"),
        "ents": ("{friend}", "重逢"),
    },
    "SOCIAL_STABLE": {
        "core": "社交关系平稳，无重大人际冲突或转折",
        "syns": ("社交平稳", "人际关系正常", "无重大人际事件", "日常互动"),
        "reds": ("关系破裂", "重大冲突", "分手离婚"),
        "ents": (),
    },
}

EMOTION_STATES = {
    "CRUSH_DESPAIR": {
        "core": "情绪高压重创：白天委屈压抑，晚间遭遇打击后崩溃绝望",
        "syns": ("崩溃", "绝望", "情感重创", "心理高压", "情绪崩溃", "痛苦低落"),
        "reds": ("心情愉快", "平静喜悦", "情绪稳定"),
    },
    "ANXIOUS_WORRY": {
        "core": "全天焦虑不安，对重大不确定性事件持续担忧",
        "syns": ("焦虑", "担忧", "不安", "忧心忡忡", "紧张忐忑"),
        "reds": ("放松平静", "喜悦", "心安"),
    },
    "IRRITABLE_LOW": {
        "core": "情绪烦躁低落，易怒且提不起劲",
        "syns": ("烦躁", "低落", "易怒", "郁闷", "提不起精神"),
        "reds": ("兴奋", "愉悦", "平和"),
    },
    "BITTERSWEET": {
        "core": "喜忧参半：成就感与现实打击交织，情绪复杂纠结",
        "syns": ("喜忧参半", "百感交集", "复杂纠结", "又喜又忧"),
        "reds": ("纯粹狂喜", "纯粹绝望", "平静无波"),
    },
    "ELATED": {
        "core": "情绪高涨愉悦，充满成就感与幸福感",
        "syns": ("开心", "喜悦", "幸福", "成就感", "兴奋雀跃"),
        "reds": ("崩溃绝望", "悲伤低落", "焦虑抑郁"),
    },
    "CALM_STABLE": {
        "core": "情绪基调平稳，日常琐碎无大起大落",
        "syns": ("平稳", "平静", "情绪稳定", "心态平和"),
        "reds": ("崩溃", "狂喜", "剧烈波动"),
    },
    "TENSE_RELIEF": {
        "core": "先紧张后释然：白天高压，晚间负面压力解除后如释重负",
        "syns": ("如释重负", "先紧后松", "释然", "松了口气"),
        "reds": ("持续崩溃", "打击加重", "愈发紧张"),
    },
}

HEALTH_STATES = {
    "STABLE": {
        "core": "体征平稳：晨起静息心率{rest}bpm，全天步数{steps}步，睡眠{sleep}小时",
        "syns": ("体征平稳", "心率正常", "健康无异常", "指标正常"),
        "reds": ("心动过速", "危急值", "胸痛晕厥", "急症发作"),
    },
    "EMOTIONAL_TACHY": {
        "core": "晨起心率{rest}bpm平稳，晚间{t}情绪剧烈波动致心率骤升至{bpm}bpm，睡眠{sleep}小时偏短",
        "syns": ("情绪性心动过速", "心率骤升", "心率飙升", "心动过速", "心率异常升高"),
        "reds": ("全天心率平稳", "心率过低", "心脏骤停"),
        "ents": ("{bpm}bpm", "心率骤升"),
    },
    "NIGHT_EMERGENCY": {
        "core": "晚间{t}突发胸痛胸闷伴冷汗，心率{bpm}bpm，赴急诊检查",
        "syns": ("胸痛急诊", "夜间心脏不适", "突发胸痛", "胸闷急诊", "夜间就医"),
        "reds": ("体征平稳", "轻微感冒", "肌肉劳损", "无健康事件"),
        "ents": ("胸痛", "{hospital}"),
    },
    "LAB_CRITICAL": {
        "core": "收到体检危急值通知（{lab}{labval}），已有相关躯体不适，待复诊",
        "syns": ("检验危急值", "指标严重异常", "体检危急值", "危急值通知", "指标超标"),
        "reds": ("指标正常", "体检通过", "一切正常"),
        "ents": ("{lab}", "危急值"),
    },
    "CHRONIC_WORSE": {
        "core": "慢性病{chronic}控制不佳，指标持续恶化，饮食作息失控",
        "syns": ("慢性病恶化", "指标失控", "慢性病加重", "控制不佳"),
        "reds": ("指标改善", "痊愈", "体征平稳"),
        "ents": ("{chronic}",),
    },
    "CAREGIVER_STRAIN": {
        "core": "为陪护家人连日奔波，睡眠仅{sleep}小时，疲劳度飙升",
        "syns": ("疲劳累积", "睡眠不足", "体力透支", "过度疲劳", "疲于奔命"),
        "reds": ("精力充沛", "休息良好", "睡眠充足"),
        "ents": ("{sleep}小时", "疲劳"),
    },
    "MILD_ILL": {
        "core": "晚间出现低烧咳嗽等轻微症状，体力下降",
        "syns": ("感冒发烧", "轻微不适", "低烧", "着凉生病"),
        "reds": ("重症急症", "危急值", "急诊手术"),
    },
}

CAREER_STATES = {
    "CRITICIZED_REDO": {
        "core": "季度汇报被{boss}当众否决，方案返工整改，面临整改压力",
        "syns": ("汇报被否", "方案被否决", "当众批评", "打回重做", "整改压力"),
        "reds": ("汇报通过", "受到表彰", "方案获批", "领导赞赏"),
        "ents": ("{boss}", "整改"),
    },
    "LAID_OFF_NOTICE": {
        "core": "收到部门优化裁员通知，{days}天内需完成交接，职业前景骤然不明",
        "syns": ("被裁员", "裁员通知", "被优化", "失业风险", "部门裁撤"),
        "reds": ("升职加薪", "续签合同", "岗位稳固", "被表彰"),
        "ents": ("裁员", "{days}天"),
    },
    "ACCIDENT_BLAMED": {
        "core": "负责的{sysname}线上事故被通报批评，承担责任",
        "syns": ("事故背锅", "被通报批评", "承担事故责任", "被追责", "事故问责"),
        "reds": ("事故立功", "免责表扬", "受到嘉奖"),
        "ents": ("{sysname}", "通报批评"),
    },
    "PROMOTION_LOST": {
        "core": "竞聘{position}失败晋升落选，开始考虑外部机会",
        "syns": ("竞聘失败", "晋升落选", "升职失败", "竞聘失利"),
        "reds": ("竞聘成功", "顺利晋升", "获得提拔", "已递交辞呈"),
        "ents": ("竞聘", "{position}"),
    },
    "PROMOTION_WON": {
        "core": "晋升答辩通过，升任{position}，职业迈上新台阶",
        "syns": ("升职", "晋升成功", "职业晋升", "升任新职", "获得提拔"),
        "reds": ("降职", "竞聘失败", "被辞退"),
        "ents": ("晋升", "{position}"),
    },
    "CONTRACT_WON": {
        "core": "主导与{client}的大单正式签约，业绩重大突破",
        "syns": ("签约成功", "拿下大单", "业绩突破", "合同签订", "合作达成"),
        "reds": ("丢单", "项目失败", "合作终止", "谈判破裂"),
        "ents": ("{client}", "签约"),
    },
    "OFFER_NEW": {
        "core": "收到{company}的offer，跳槽意向萌生，尚未正式提离职",
        "syns": ("拿到offer", "新工作机会", "跳槽意向", "收到录用"),
        "reds": ("被开除", "降职处分", "失业"),
        "ents": ("offer", "{company}"),
    },
    "RESIGN_SUBMITTED": {
        "core": "正式递交辞职信进入交接期，职业方向主动转折",
        "syns": ("提出辞职", "递交辞呈", "离职决定", "辞职交接"),
        "reds": ("续约留任", "被辞退", "被迫失业"),
        "ents": ("辞职",),
    },
    "LEAVE_CONFLICT": {
        "core": "为家人病重请假交接，工作安排受到冲击",
        "syns": ("事假陪护", "请假照护家人", "工作为家庭让路", "请假交接"),
        "reds": ("全勤无休", "工作如常推进", "出差远行"),
        "ents": ("请假",),

    },
    "EXAM_PASS": {
        "core": "重要{exam}顺利通过，职业资格取得突破",
        "syns": ("考试通过", "答辩通过", "顺利过关", "资格取得"),
        "reds": ("考试失利", "答辩被毙", "未通过"),
        "ents": ("{exam}", "通过"),
    },
    "NORMAL_PROGRESS": {
        "core": "日常工作正常推进，无重大职业事件",
        "syns": ("工作正常", "日常事务", "平稳推进", "无重大职业变动"),
        "reds": ("被批评", "升职", "被裁", "重大事故"),
    },
    "OVERTIME_PRESSURE": {
        "core": "连续加班赶工，交付压力沉重",
        "syns": ("加班高压", "赶工期", "交付压力", "连轴转"),
        "reds": ("轻松悠闲", "带薪休假", "工作清闲"),
        "ents": ("加班",),
    },
    "OFFDAY": {
        "core": "非工作日，无职业事务，休整为主",
        "syns": ("休息日", "无职业事件", "休假休整"),
        "reds": ("加班危机", "升职变动", "被批评"),
    },
}

FINANCE_EVENTS = {
    "CC_REPAY": {
        "gt_core": "例行信用卡还款{amt}元，无新增大额债务",
        "syns": ("信用卡还款", "还款{amt}元", "例行还款", "按时还款"),
        "reds": ("新增大额负债", "收入暴增", "投资巨亏", "逾期"),
        "event": ("app", "{bank}", "{bank}", "【{bank}】您尾号{tail}的信用卡本月还款{amt}元已自动扣款"),
        "ents": ("{amt}元",),
    },
    "SALARY_IN": {
        "gt_core": "例行工资到账{amt}元，财务面平稳",
        "syns": ("工资到账", "发薪{amt}元", "收入到账"),
        "reds": ("大额亏损", "新增负债", "奖金巨额", "逾期"),
        "event": ("app", "{bank}", "{bank}", "【{bank}】您账户{m}月工资{amt}元已入账"),
        "ents": ("{amt}元",),
    },
    "FUND_LOSS": {
        "gt_core": "持仓基金单日回撤{pct}%（约{amt}元），投资受损",
        "syns": ("基金亏损", "投资回撤", "理财浮亏", "持仓下跌"),
        "reds": ("投资大赚", "收益创新高", "财务无忧"),
        "event": ("app", "支付宝", "基金公司", "您的持仓基金今日净值下跌{pct}%，约亏{amt}元"),
        "ents": ("{pct}%", "{amt}元"),
    },
    "BONUS_IN": {
        "gt_core": "项目奖金{amt}元到账，计划提前偿还部分房贷，月供压力将减轻",
        "syns": ("奖金到账", "绩效奖励", "项目奖金"),
        "reds": ("罚款扣款", "工资拖欠", "投资亏损"),
        "event": ("app", "{bank}", "{bank}", "【{bank}】您账户入账项目奖金{amt}元"),
        "ents": ("{amt}元",),
    },
    "OVERDUE_RISK": {
        "gt_core": "信用卡最后还款日临近而余额不足，面临逾期与征信风险",
        "syns": ("逾期风险", "征信焦虑", "还款压力", "账单压力"),
        "reds": ("财务宽裕", "无债务", "大额入账"),
        "event": ("app", "{bank}", "{bank}", "【{bank}】您的信用卡今日为最后还款日，应还{amt}元，当前余额不足，请及时补足"),
        "ents": ("{amt}元",),
    },
    "LOAN_PENDING": {
        "gt_core": "老友提出借款{amount}万元请求未获应允，当日资产负债无实际变动",
        "syns": ("借款请求未决", "被请求借钱但未转账", "资产负债未变", "借钱请求悬而未决"),
        "reds": ("已放款转账", "新增负债", "收到还款", "大额入账"),
        "event": None,
        "ents": ("{amount}万",),
    },
    "NONE": {
        "gt_core": "财务平稳，无重大资产与债务变动（仅日常小额消费）",
        "syns": ("无财务变动", "财务平稳", "日常小额消费"),
        "reds": ("大额入账", "大额亏损", "新增负债", "逾期"),
        "event": None,
        "ents": (),
    },
}

# ---------------------------------------------------------------------------
# 琐碎日常事件池（时间窗, 来源, 发送方/应用, 文本模板）——高熵噪声主体
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 琐碎日常事件池（高熵噪声主体）
# 统一五元组 (时间, 来源, x1, x2, 文本)：
#   mic    → x1=说话人, x2=场景
#   app    → x1=应用,   x2=发送方
#   sensor → x1="",     x2=""
# ---------------------------------------------------------------------------

TRIVIAL_EVENTS = (
    ("07:20", "mic", "母亲", "晨间电话", "记得吃早饭，别空腹喝咖啡"),
    ("07:35", "sensor", "", "", "晨起静息心率{rest}bpm"),
    ("07:45", "sensor", "", "", "昨夜睡眠{sleep}小时，深睡{deep}小时"),
    ("07:55", "mic", "地铁广播", "通勤", "开往科技园方向的列车即将进站"),
    ("08:40", "app", "瑞幸咖啡", "官方", "您的订单已出餐，取餐码A{code}"),
    ("09:10", "app", "微信-工作群", "{colleague}", "@所有人 十点例会改到十点半，会议室3F"),
    ("09:45", "mic", "{colleague}", "茶水间闲聊", "昨晚那球看了没？最后三分钟绝了"),
    ("10:30", "app", "菜鸟驿站", "官方", "您有包裹已到驿站{code}柜，下班记得取"),
    ("11:20", "app", "钉钉", "{boss2}", "下午两点评审会，材料提前发我"),
    ("12:10", "app", "美团外卖", "商家", "您的订单已送达，祝您用餐愉快"),
    ("12:40", "mic", "{colleague}", "午餐闲聊", "这家酸菜鱼一般，还不如楼下那家"),
    ("13:15", "sensor", "", "", "午休后心率{hr2}bpm，步数{steps}步"),
    ("14:50", "app", "微信-拼单群", "{colleague}", "下午茶拼单，奶茶三杯起送，来的接龙"),
    ("15:30", "mic", "{colleague}", "工位请教", "这需求文档我看了，有个逻辑对不上，你来瞅瞅"),
    ("16:40", "app", "京东", "官方", "您购买的商品已发货，预计明日送达"),
    ("17:30", "sensor", "", "", "傍晚步数{steps}步，久坐提醒：该起身活动了"),
    ("18:20", "mic", "超市店员", "买菜", "会员积分吗？袋子需要吗"),
    ("19:10", "app", "微信-家人群", "母亲", "转发：换季少吃这三种食物（养生文章）"),
    ("19:40", "mic", "父亲", "晚间来电", "家里都好，你忙你的，别惦记"),
    ("20:15", "app", "网易新闻", "推送", "本周冷空气来袭，局地降温{temp}度"),
    ("20:50", "app", "抖音", "官方", "您关注的主播开播啦"),
    ("21:30", "app", "支付宝", "基金公司", "基金净值更新：今日持仓收益-{tiny}元"),
    ("22:10", "mic", "{colleague}", "微信语音", "明早拼车吗？我开车顺路带你"),
    ("22:40", "sensor", "", "", "夜间心率{hr2}bpm，准备就寝"),
    ("23:10", "app", "手机系统", "系统", "屏幕使用时间6小时42分，较昨日增加{temp}分钟"),
)

#: 语义陷阱池——语义上像大事，实为玩笑/他人事/惊悚标题/残留噪声，严禁总结成本人核心事实
TRAP_EVENTS = (
    ("10:15", "mic", "{colleague}", "工位玩笑", "再让我改这版方案，我就把工位搬到老板办公室去哈哈"),
    ("11:05", "app", "微信-同学群", "老同学", "下个月我必收购腾讯，谁拦我跟谁急（吹牛）"),
    ("15:50", "app", "网易新闻", "推送", "研究称90后体检异常率飙升，网友热议"),
    ("20:35", "mic", "{colleague}", "电话吐槽", "烦死了，真想明天就辞职去大理开客栈（口头禅）"),
    ("21:15", "app", "微博", "热搜", "某明星官宣离婚，评论区已炸"),
    ("21:45", "app", "微信-家人群", "三姨", "帮忙点一下砍一刀，就差0.9%啦"),
    ("22:20", "app", "手机系统", "系统", "验证码{code}，请勿泄露给任何人（残留噪声）"),
    ("20:05", "app", "朋友圈", "老同学", "晒图配文：人生赢家，环游世界ing（他人生活）"),
)


# ---------------------------------------------------------------------------
# 跨维度剧情原型库（24 个）
# 每个原型: family / weight / intensity / spine(全局主线模板) /
#           五维状态(social/emotion/health/career) + 主线同义词簇与红线
# ---------------------------------------------------------------------------

ARCHETYPES = {
    "BREAKUP_AFTER_CRITICISM": {
        "family": "职场危机×情感断裂",
        "weight": 9,
        "intensity": "HIGH",
        "spine": "白天工作被{boss}当众批评受挫，晚间女友{gf}明确提出分手，情感重创叠加职场压力，身心极度高压",
        "social": "GIRLFRIEND_BREAKUP", "emotion": "CRUSH_DESPAIR",
        "health": "EMOTIONAL_TACHY", "career": "CRITICIZED_REDO",
        "spine_syns": ("工作受挫叠加分手打击", "被批后遭分手情感重创", "职场情感双线崩塌高压", "白天挨批晚上分手"),
        "spine_reds": ("升职庆祝", "甜蜜求婚", "工作受表扬", "和好如初", "离婚"),
    },
    "LONGDIST_FIGHT": {
        "family": "情感转折",
        "weight": 5,
        "intensity": "MEDIUM",
        "spine": "与异地恋女友{gf}因长期聚少离多爆发激烈争吵，和解未成，关系陷入僵局",
        "social": "LONGDIST_FIGHT", "emotion": "IRRITABLE_LOW",
        "health": "EMOTIONAL_TACHY", "career": "NORMAL_PROGRESS",
        "spine_syns": ("异地恋争吵关系僵持", "情侣矛盾爆发", "远距离感情危机"),
        "spine_reds": ("团聚见家长", "感情升温", "和好订婚"),
    },
    "DIVORCE_TALK": {
        "family": "情感断裂",
        "weight": 5,
        "intensity": "HIGH",
        "spine": "配偶{spouse}晚间正式提出离婚并谈及财产分割，婚姻濒临解体，情绪剧烈震荡",
        "social": "SPOUSE_DIVORCE", "emotion": "CRUSH_DESPAIR",
        "health": "EMOTIONAL_TACHY", "career": "NORMAL_PROGRESS",
        "spine_syns": ("被提出离婚婚姻危机", "婚变冲击", "离婚协商启动"),
        "spine_reds": ("恩爱和睦", "备孕喜讯", "纪念庆祝"),
    },
    "PARTNER_COLDWAR": {
        "family": "情感转折",
        "weight": 5,
        "intensity": "MEDIUM",
        "spine": "偶然发现伴侣{spouse}与异性的暧昧聊天记录，质问后陷入冷战，信任动摇",
        "social": "PARTNER_COLDWAR", "emotion": "IRRITABLE_LOW",
        "health": "STABLE", "career": "NORMAL_PROGRESS",
        "spine_syns": ("发现暧昧记录后冷战", "信任危机爆发", "伴侣关系恶化"),
        "spine_reds": ("信任加深", "甜蜜互动", "和好如初"),
    },
    "RECONCILE_DEEPTALK": {
        "family": "情感修复",
        "weight": 4,
        "intensity": "MEDIUM",
        "spine": "与女友{gf}的积怨经深夜长谈彻底化解，关系和好修复，如释重负",
        "social": "RECONCILE", "emotion": "TENSE_RELIEF",
        "health": "STABLE", "career": "NORMAL_PROGRESS",
        "spine_syns": ("矛盾化解和好", "深谈修复关系", "和解如释重负"),
        "spine_reds": ("分手决裂", "冷战加剧", "争吵升级"),
    },
    "PROPOSAL_SUCCESS_DAY": {
        "family": "正向突破",
        "weight": 4,
        "intensity": "HIGH",
        "spine": "精心筹备后向女友{gf}求婚成功，双方进入谈婚论嫁阶段，全天幸福高涨",
        "social": "PROPOSAL_SUCCESS", "emotion": "ELATED",
        "health": "STABLE", "career": "NORMAL_PROGRESS",
        "spine_syns": ("求婚成功喜事", "答应求婚步入婚姻", "订婚喜悦"),
        "spine_reds": ("求婚被拒", "分手争吵", "感情破裂"),
    },
    "FAMILY_ILLNESS_CALL": {
        "family": "健康危机×家庭",
        "weight": 6,
        "intensity": "HIGH",
        "spine": "{kin}{kinname}确诊重病住院的通知打破日常，连夜赶赴医院陪护，家庭进入应急状态",
        "social": "FAMILY_ILLNESS", "emotion": "ANXIOUS_WORRY",
        "health": "CAREGIVER_STRAIN", "career": "LEAVE_CONFLICT",
        "spine_syns": ("家人重病打乱生活", "确诊住院陪护应急", "家庭健康危机"),
        "spine_reds": ("家人康复喜讯", "全家平安无事", "体检正常"),
    },
    "NEIGHBOR_DISPUTE_DAY": {
        "family": "人际冲突",
        "weight": 4,
        "intensity": "MEDIUM",
        "spine": "与邻居因{dispute}爆发激烈纠纷，投诉沟通未果，关系对立，心率随之波动",
        "social": "NEIGHBOR_DISPUTE", "emotion": "IRRITABLE_LOW",
        "health": "EMOTIONAL_TACHY", "career": "NORMAL_PROGRESS",
        "spine_syns": ("邻里纠纷对立", "与邻居冲突激化", "邻里矛盾爆发"),
        "spine_reds": ("邻里和睦互助", "握手言和", "友好协商解决"),
    },
    "FRIEND_LOAN_REQUEST": {
        "family": "财务契约×人际",
        "weight": 5,
        "intensity": "MEDIUM",
        "spine": "老友{friend}突然提出借款{amount}万元周转，金额远超预期，犹豫再三未应允，友谊面临金钱考验",
        "social": "FRIEND_LOAN_TENSION", "emotion": "ANXIOUS_WORRY",
        "health": "STABLE", "career": "NORMAL_PROGRESS",
        "spine_syns": ("老友大额借钱请求未决", "借款请求引发犹豫", "友谊金钱考验"),
        "spine_reds": ("慷慨转账解围", "朋友如约还款", "合伙投资共赢"),
    },
    "LAB_CRITICAL_NOTICE": {
        "family": "健康危机",
        "weight": 6,
        "intensity": "HIGH",
        "spine": "收到{hospital}体检危急值通知（{lab}{labval}），全天焦虑笼罩，连夜预约复诊",
        "social": "SOCIAL_STABLE", "emotion": "ANXIOUS_WORRY",
        "health": "LAB_CRITICAL", "career": "NORMAL_PROGRESS",
        "spine_syns": ("体检危急值引发焦虑", "指标异常待复诊", "健康警报响起"),
        "spine_reds": ("体检一切正常", "指标好转", "虚惊一场无异常"),
    },
    "NIGHT_CHEST_ER": {
        "family": "健康危机",
        "weight": 4,
        "intensity": "HIGH",
        "spine": "晚间突发胸痛胸闷伴冷汗，深夜赴{hospital}急诊检查，次日需请假休养",
        "social": "SOCIAL_STABLE", "emotion": "ANXIOUS_WORRY",
        "health": "NIGHT_EMERGENCY", "career": "LEAVE_CONFLICT",
        "spine_syns": ("深夜胸痛急诊", "突发心脏不适就医", "夜间健康急症"),
        "spine_reds": ("体征平稳无事", "轻微肌肉劳损", "整夜安睡"),
    },
    "CHRONIC_WORSE_DAY": {
        "family": "健康危机",
        "weight": 4,
        "intensity": "MEDIUM",
        "spine": "慢性病{chronic}复查指标恶化，医嘱严格控制饮食作息，但工作应酬让执行难上加难",
        "social": "SOCIAL_STABLE", "emotion": "IRRITABLE_LOW",
        "health": "CHRONIC_WORSE", "career": "OVERTIME_PRESSURE",
        "spine_syns": ("慢性病指标失控", "病情控制不佳", "健康管理与工作冲突"),
        "spine_reds": ("指标显著改善", "痊愈", "体征平稳无恙"),
    },
    "INVESTMENT_CRASH": {
        "family": "财务契约",
        "weight": 6,
        "intensity": "MEDIUM",
        "spine": "持仓基金单日大跌{pct}%，账面回撤约{loss_wan}万元，止损与补仓反复纠结，全天心神不宁",
        "social": "SOCIAL_STABLE", "emotion": "ANXIOUS_WORRY",
        "health": "STABLE", "career": "NORMAL_PROGRESS",
        "spine_syns": ("基金大跌心神不宁", "投资回撤纠结止损", "理财亏损焦虑"),
        "spine_reds": ("投资大赚", "收益创新高", "财务无忧"),
    },
    "OVERDUE_ANXIETY": {
        "family": "财务契约",
        "weight": 4,
        "intensity": "MEDIUM",
        "spine": "信用卡今日最后还款日而余额不足，四处周转凑款，征信逾期风险压顶",
        "social": "SOCIAL_STABLE", "emotion": "ANXIOUS_WORRY",
        "health": "STABLE", "career": "OVERTIME_PRESSURE",
        "spine_syns": ("还款日资金告急", "逾期征信风险", "账单压力压顶"),
        "spine_reds": ("财务宽裕轻松", "大额入账", "无债一身轻"),
    },
    "BONUS_REPAY_DAY": {
        "family": "财务契约×正向",
        "weight": 4,
        "intensity": "MEDIUM",
        "spine": "项目奖金{amt}元到账，决定提前偿还部分房贷减轻月供，财务规划迈出一步",
        "social": "SOCIAL_STABLE", "emotion": "ELATED",
        "health": "STABLE", "career": "CONTRACT_WON",
        "spine_syns": ("奖金到账提前还贷", "收入改善财务优化", "绩效兑现减负"),
        "spine_reds": ("罚款扣钱", "工资拖欠", "投资亏损"),
    },
    "PROMOTION_FAMILY_ILL": {
        "family": "复合转折（喜忧参半）",
        "weight": 5,
        "intensity": "HIGH",
        "spine": "晋升答辩通过升任{position}的同日，{kin}{kinname}确诊重病住院，喜事与噩耗交织，悲喜交加",
        "social": "FAMILY_ILLNESS", "emotion": "BITTERSWEET",
        "health": "CAREGIVER_STRAIN", "career": "PROMOTION_WON",
        "spine_syns": ("升职同日家人病重", "喜忧参半的一天", "晋升与噩耗交织"),
        "spine_reds": ("纯粹双喜临门", "纯粹灾祸", "平淡无奇"),
    },
    "EXAM_PASS_SICK": {
        "family": "复合转折（喜忧参半）",
        "weight": 4,
        "intensity": "MEDIUM",
        "spine": "{exam}顺利通过的当晚突发低烧咳嗽，喜事被病痛打了折扣",
        "social": "SOCIAL_STABLE", "emotion": "BITTERSWEET",
        "health": "MILD_ILL", "career": "EXAM_PASS",
        "spine_syns": ("考试通过但病倒", "通过后染病", "喜中带忧"),
        "spine_reds": ("考试失利", "全程健康", "双重打击崩溃"),
    },
    "OLDFRIEND_REUNION": {
        "family": "人际转折",
        "weight": 4,
        "intensity": "LOW",
        "spine": "与{friend}多年后重逢畅聊至深夜，叙旧尽兴，席间对方推销理财被我婉拒",
        "social": "FRIEND_REUNION", "emotion": "TENSE_RELIEF",
        "health": "STABLE", "career": "NORMAL_PROGRESS",
        "spine_syns": ("老友重逢叙旧", "多年好友再聚", "重逢尽兴而归"),
        "spine_reds": ("老友反目", "借钱撕破脸", "被拉去投资入坑"),
    },
    "PROMOTION_LOST_DAY": {
        "family": "职场危机",
        "weight": 5,
        "intensity": "MEDIUM",
        "spine": "竞聘{position}失败晋升落选，情绪低落之际猎头主动来电，开始认真考虑外部机会",
        "social": "SOCIAL_STABLE", "emotion": "IRRITABLE_LOW",
        "health": "STABLE", "career": "PROMOTION_LOST",
        "spine_syns": ("竞聘失利萌生去意", "晋升失败考虑跳槽", "落选后另寻出路"),
        "spine_reds": ("竞聘成功晋升", "获得提拔重用", "安心留任表彰"),
    },
    "LAID_OFF_DAY": {
        "family": "职场危机×财务",
        "weight": 5,
        "intensity": "HIGH",
        "spine": "收到部门优化裁员通知，{days}天内需完成交接，房贷月供压力瞬间放大，前景骤暗",
        "social": "SOCIAL_STABLE", "emotion": "CRUSH_DESPAIR",
        "health": "EMOTIONAL_TACHY", "career": "LAID_OFF_NOTICE",
        "spine_syns": ("被裁叠加房贷焦虑", "裁员通知前景骤暗", "失业危机高压"),
        "spine_reds": ("升职加薪", "续约稳固", "被表彰嘉奖"),
    },
    "ACCIDENT_BLAMED_DAY": {
        "family": "职场危机",
        "weight": 5,
        "intensity": "HIGH",
        "spine": "负责的{sysname}线上事故被通报批评，被{boss}点名担责，全天如坐针毡",
        "social": "BOSS_CONFLICT", "emotion": "IRRITABLE_LOW",
        "health": "EMOTIONAL_TACHY", "career": "ACCIDENT_BLAMED",
        "spine_syns": ("事故背锅被通报", "被点名担责如坐针毡", "问责压力笼罩"),
        "spine_reds": ("事故立功受奖", "免责表扬", "责任撇清无事"),
    },
    "CONTRACT_MISSED_ANNIVERSARY": {
        "family": "复合转折（顾此失彼）",
        "weight": 5,
        "intensity": "MEDIUM",
        "spine": "主导与{client}的大单签约庆功，却因此错过与女友{gf}的纪念日，她深夜发来长文表达不满",
        "social": "ANNIVERSARY_MISSED", "emotion": "BITTERSWEET",
        "health": "STABLE", "career": "CONTRACT_WON",
        "spine_syns": ("签约庆功却爽约纪念日", "事业得意情感失分", "顾此失彼的一天"),
        "spine_reds": ("事业爱情双丰收", "共度纪念日", "女友理解赞赏"),
    },
    "OFFER_NEWJOB_DAY": {
        "family": "职场转折",
        "weight": 4,
        "intensity": "MEDIUM",
        "spine": "收到{company}的offer，薪酬涨幅可观，跳槽意向萌生但尚未正式向{boss}提离职，内心拉扯",
        "social": "SOCIAL_STABLE", "emotion": "BITTERSWEET",
        "health": "STABLE", "career": "OFFER_NEW",
        "spine_syns": ("拿到offer去留拉扯", "新机会与现状抉择", "跳槽意向萌生"),
        "spine_reds": ("被开除", "降职处分", "断然拒绝一切机会"),
    },
    "RESIGN_SUBMITTED_DAY": {
        "family": "职场转折",
        "weight": 4,
        "intensity": "HIGH",
        "spine": "经过长期纠结正式递交辞职信，与{boss}坦诚沟通后进入交接期，如释重负又前路未知",
        "social": "SOCIAL_STABLE", "emotion": "TENSE_RELIEF",
        "health": "STABLE", "career": "RESIGN_SUBMITTED",
        "spine_syns": ("递交辞呈进入交接", "正式提离职", "主动转折如释重负"),
        "spine_reds": ("续约留任", "被辞退", "被迫失业"),
    },
    "QUIET_WEEKEND": {
        "family": "平静基线（小确幸）",
        "weight": 6,
        "intensity": "LOW",
        "spine": "休息日居家休整：补觉、打扫、追剧，唯一波澜是网购的心仪好物到货，平淡中的小确幸",
        "social": "SOCIAL_STABLE", "emotion": "CALM_STABLE",
        "health": "STABLE", "career": "OFFDAY",
        "spine_syns": ("平稳休整日", "平淡小确幸", "休息日无事"),
        "spine_reds": ("重大危机", "情感破裂", "健康急症", "职业变动"),
    },
    "REMOTE_QUIET_DAY": {
        "family": "平静基线（远程办公）",
        "weight": 4,
        "intensity": "LOW",
        "spine": "远程办公日节奏平缓，例会与交付照旧推进，傍晚外卖超时获平台赔付，小有不快但总体平稳",
        "social": "SOCIAL_STABLE", "emotion": "CALM_STABLE",
        "health": "STABLE", "career": "NORMAL_PROGRESS",
        "spine_syns": ("远程办公平稳日", "例行推进小波折", "平淡工作日"),
        "spine_reds": ("重大冲突", "健康急症", "被批评裁员"),
    },
}

#: 各原型可搭配的财务事件（未列出者走默认滚动池）
ARCHETYPE_FINANCE = {
    "BREAKUP_AFTER_CRITICISM": ("CC_REPAY", "NONE", "FUND_LOSS"),
    "FRIEND_LOAN_REQUEST": ("LOAN_PENDING",),
    "INVESTMENT_CRASH": ("FUND_LOSS",),
    "OVERDUE_ANXIETY": ("OVERDUE_RISK",),
    "BONUS_REPAY_DAY": ("BONUS_IN",),
    "LAID_OFF_DAY": ("OVERDUE_RISK", "CC_REPAY"),
    "PROPOSAL_SUCCESS_DAY": ("SALARY_IN", "NONE", "CC_REPAY"),
    "LAB_CRITICAL_NOTICE": ("CC_REPAY", "NONE", "SALARY_IN"),
    "FAMILY_ILLNESS_CALL": ("NONE", "CC_REPAY"),
    "PROMOTION_FAMILY_ILL": ("SALARY_IN", "NONE"),
    "QUIET_WEEKEND": ("NONE", "CC_REPAY"),
}

#: 财务事件默认滚动池
DEFAULT_FINANCE_POOL = ("CC_REPAY", "NONE", "NONE", "SALARY_IN", "FUND_LOSS", "NONE", "CC_REPAY")

#: 剧情强度 → 晚间心率异常幅度（bpm）
INTENSITY_HR = {"HIGH": (118, 132), "MEDIUM": (104, 115), "LOW": (96, 103)}
