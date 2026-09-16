# -*- coding: utf-8 -*-
"""AIOS 3.0 全天生活流与多维总结高熵出卷官 —— agent-aa2e 战队。

任务：生成 10,000 个人的「真实人生 24 小时生活流」高熵试卷，每卷含：
  1. cleaned_daily_stream —— 07:00~23:30 已清洗生活流（MIC 对话切片 / APP 通知与
     聊天 / 传感器体征宏观摘要），关键大事与海量琐碎日常混编，含跨维度冲突转折；
  2. directional_ground_truth —— 六维方向性语义标答（全局日总结 + health/social/
     emotion/finance/career），每维给出【可接受方向同义词】与【绝对偏离红线判据】。

出题铁律落实：
  * 标答只锚定语义方向，严禁死板字句匹配 —— acceptable_directions 为方向近义簇，
    forbidden_directions 为一票否决红线（如分手答成甜蜜互动）；
  * 生成完全确定性（SEED 固定），同版本代码重跑逐字节一致，便于仲裁复核。
"""

from __future__ import annotations

import json
import random
from pathlib import Path

GENERATOR_AGENT = "agent-aa2e"
SEED = 0xAA2E
TOTAL = 10_000

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "benchmarks/daily_summary/questions/questions_daily24h_agent_aa2e.jsonl"

# ---------------------------------------------------------------------------
# 一、人物池（姓名 × 职业 × 城市 → 10,000 个不重复人生）
# ---------------------------------------------------------------------------

SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜")
GIVEN = ["志远", "晓彤", "雨桐", "嘉懿", "沐宸", "欣怡", "浩然", "语嫣", "子墨", "思齐",
         "曼妮", "峻纬", "若曦", "铭轩", "婉清", "奕辰", "静姝", "泽楷", "芷晴", "骁睿",
         "佩珊", "承宇", "韵如", "皓轩", "梓萱", "冠廷", "慧娴", "天翊", "缇娜", "秉文"]

OCCUPATIONS = [
    ("互联网产品经理", 26, 38), ("后端程序员", 24, 36), ("三甲医院护士", 23, 40),
    ("中学语文老师", 26, 45), ("外卖骑手", 22, 42), ("银行客户经理", 25, 40),
    ("广告公司文案", 23, 33), ("建筑工程监理", 30, 50), ("宠物店主理人", 25, 38),
    ("会计师事务所审计", 24, 35), ("新媒体运营", 22, 32), ("急诊科住院医师", 27, 40),
    ("房产中介", 24, 40), ("咖啡店店长", 25, 36), ("小学美术老师", 24, 38),
    ("跨境电商运营", 25, 35), ("律所初级律师", 26, 36), ("装修工长", 32, 52),
    ("网约车司机", 28, 50), ("健身教练", 23, 35), ("研究生在读", 22, 28),
    ("HR人事专员", 24, 36), ("市场销售代表", 24, 38), ("幼儿园老师", 22, 34),
]

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京",
          "重庆", "长沙", "苏州", "青岛", "郑州", "厦门", "合肥"]

PARTNER_TITLES_F = ["男友", "老公", "未婚夫"]
PARTNER_TITLES_M = ["女友", "老婆", "未婚妻"]

# ---------------------------------------------------------------------------
# 二、事业弧线池（dim:career 主事件，白天 09:30~17:30 展开）
#     polarity: +1 顺境 / -1 逆境 / 0 压力中性
# ---------------------------------------------------------------------------

CAREER_ARCS = [
    {
        "arc_id": "C_PUBLIC_CRITICISM", "polarity": -1,
        "events": [
            ("10:05", "MIC", "（会议室，领导）{name}，这份季度汇报数据口径全是错的！当着全部门的面我都替你脸红，推倒重做！"),
            ("10:12", "MIC", "（{name}低声）……好的，我下周前重新整理，抱歉。"),
            ("15:40", "APP", "微信-部门群｜总监：季度复盘材料质量参差，个别同学要好好反思，下周一重交。"),
        ],
        "core": "季度汇报被领导当众严厉批评并要求推倒重做，职业信心受挫面临整改压力",
        "acceptable": ["汇报被否决", "当众批评", "工作受挫", "被领导训斥", "复盘材料被打回", "职场挫败", "面临返工整改"],
        "forbidden": ["汇报获得表扬", "晋升加薪", "领导高度认可", "工作顺利无波折"],
    },
    {
        "arc_id": "C_PROMOTION_WIN", "polarity": 1,
        "events": [
            ("11:00", "MIC", "（答辩会）评委：思路很完整，落地路径也清晰。恭喜{name}，晋升答辩全票通过！"),
            ("11:20", "APP", "微信-HR：晋升审批已走完流程，下月起职级与薪资同步调整，恭喜！"),
            ("12:05", "MIC", "（同事）请客请客！{name}老师高升，中午这顿必须安排！"),
        ],
        "core": "晋升答辩全票通过职级薪资双升，事业取得关键突破",
        "acceptable": ["晋升成功", "答辩通过", "升职加薪", "事业高光", "职级提升", "获得认可"],
        "forbidden": ["晋升失败", "被降职", "答辩被否", "被辞退", "职业受挫"],
    },
    {
        "arc_id": "C_LAYOFF_TALK", "polarity": -1,
        "events": [
            ("14:00", "MIC", "（小会议室，HR）{name}，公司业务线调整，你的岗位在优化名单里，N+1 方案你先看看。"),
            ("14:25", "MIC", "（{name}）能不能给我转岗机会？这个项目我跟了两年……"),
            ("16:30", "APP", "微信-前同事：听说你们组被整个端了？别慌，我们这边在招人，简历发我。"),
        ],
        "core": "被约谈裁员进入优化名单，面临失业与N+1补偿抉择，职业生涯突遭重挫",
        "acceptable": ["被裁员约谈", "岗位被优化", "面临失业", "被辞退谈补偿", "职业危机", "丢了工作"],
        "forbidden": ["升职加薪", "获得晋升", "工作稳定顺利", "拿到大项目嘉奖"],
    },
    {
        "arc_id": "C_PROJECT_LAUNCH", "polarity": 1,
        "events": [
            ("09:40", "MIC", "（站会）{name}：灰度数据正常，各指标平稳，今天上午全量上线！"),
            ("11:30", "APP", "钉钉-项目群｜CTO：新版本上线零事故，转化率提升12%，给整个项目组记功！"),
            ("17:10", "MIC", "（领导）干得漂亮，季度评优我提名你，继续保持。"),
        ],
        "core": "负责的项目全量上线零事故且指标大涨，获高层公开表扬并提名评优",
        "acceptable": ["项目上线成功", "获得表扬", "指标大涨", "被提名评优", "工作高光", "上线零事故"],
        "forbidden": ["上线失败", "线上事故", "被追责", "项目烂尾", "被批评"],
    },
    {
        "arc_id": "C_BLAME_SHIFT", "polarity": -1,
        "events": [
            ("10:30", "MIC", "（复盘会，同事）昨晚的故障是{name}改的配置引起的吧？我这边可没动过。"),
            ("10:33", "MIC", "（{name}）变更记录都在系统里，几点几分谁提交的一查就知道，别乱扣帽子！"),
            ("15:00", "APP", "企业微信-主管：故障定责先挂你名下，有异议提交证据链，周五前给结论。"),
        ],
        "core": "线上故障复盘被同事甩锅，定责暂挂己名，被迫整理变更证据链自证清白",
        "acceptable": ["被同事甩锅", "背锅", "故障被定责", "职场推诿冲突", "自证清白", "复盘会被针对"],
        "forbidden": ["获得表彰", "团队和睦无冲突", "同事主动揽责", "升职"],
    },
    {
        "arc_id": "C_CLIENT_SIGN", "polarity": 1,
        "events": [
            ("13:30", "MIC", "（客户）合同条款没问题，今天就盖章，明年的框架单也一起谈了吧。"),
            ("13:50", "APP", "微信-销售群｜经理：恭喜{name}拿下年度最大单，佣金按最高档结算！"),
            ("18:00", "MIC", "（同事）大单之王！晚上庆功宴走起？"),
        ],
        "core": "拿下年度最大客户签约并锁定明年框架合作，业绩创新高佣金按最高档结算",
        "acceptable": ["签下大客户", "拿下大单", "业绩突破", "签约成功", "销售冠军", "佣金丰厚"],
        "forbidden": ["丢单", "客户流失", "签约失败", "业绩垫底", "被客户投诉"],
    },
    {
        "arc_id": "C_DEADLINE_CRUNCH", "polarity": 0,
        "events": [
            ("09:20", "APP", "钉钉-项目群｜产品：客户临时改需求，交付日期不变，今晚辛苦大家。"),
            ("16:00", "MIC", "（{name}）第三版方案又推翻……行吧，我重排今晚全弄完。"),
            ("21:40", "APP", "钉钉-项目群｜{name}：改完自测通过，已提测，明早联调。"),
        ],
        "core": "客户临时变更需求但交付日不变，被迫加班到深夜重做方案并如期提测",
        "acceptable": ["需求突变赶工", "连夜加班", "交付压力大", "熬夜改方案", "高强度赶进度"],
        "forbidden": ["清闲无事", "提前下班休假", "项目取消无压力"],
    },
    {
        "arc_id": "C_DEMO_FAIL", "polarity": -1,
        "events": [
            ("14:30", "MIC", "（演示现场）{name}：稍等……系统怎么突然白屏了，我重启一下服务……"),
            ("14:45", "MIC", "（甲方）你们就这准备水平？下周再约，再翻车这项目就换供应商。"),
            ("17:20", "APP", "企业微信-老板：今天现场什么情况？晚上电话会复盘，把根因给我讲清楚。"),
        ],
        "core": "关键客户演示现场系统崩溃翻车，甲方威胁更换供应商，被老板责令连夜复盘",
        "acceptable": ["演示翻车", "现场事故", "客户不满", "被老板追责", "项目岌岌可危", "演示失败"],
        "forbidden": ["演示大获成功", "当场签约", "获客户盛赞", "被嘉奖"],
    },
    {
        "arc_id": "C_PASS_PROBATION", "polarity": 1,
        "events": [
            ("11:15", "MIC", "（主管）转正述职我打了最高分，答辩委员会也全过了，恭喜正式入职！"),
            ("11:40", "APP", "邮箱-HR：转正审批通过，薪资上调15%，次月生效。"),
        ],
        "core": "转正述职获最高分顺利通过，薪资上调15%，职业阶段性目标达成",
        "acceptable": ["转正通过", "述职高分", "加薪15%", "顺利转正", "获主管认可"],
        "forbidden": ["转正被拒", "延长试用", "被劝退", "述职失败"],
    },
    {
        "arc_id": "C_WAGE_DELAY", "polarity": -1,
        "events": [
            ("10:50", "APP", "邮箱-财务部：因资金回笼延迟，本月工资推迟两周发放，敬请谅解。"),
            ("12:10", "MIC", "（同事）又延发？这都第二回了，我房贷等着扣款呢！"),
            ("12:12", "MIC", "（{name}）我也慌，再这样真得看看外面机会了。"),
        ],
        "core": "公司邮件通知工资延迟两周发放且系年内第二次，动摇军心开始考虑外部机会",
        "acceptable": ["工资延发", "欠薪风波", "公司资金紧张", "考虑跳槽", "薪资拖欠"],
        "forbidden": ["加薪", "发放丰厚奖金", "公司经营大好", "工资提前到账"],
    },
    {
        "arc_id": "C_THESIS_REJECT", "polarity": -1,
        "events": [
            ("09:50", "APP", "邮箱-期刊编辑部：很遗憾，您的论文经外审未达录用标准，建议大修后另投。"),
            ("15:30", "MIC", "（导师）三个审稿人两个拒，说明方法创新不够，实验补齐重写引言，下月再投。"),
            ("15:35", "MIC", "（{name}）……好，我把补充实验列个计划今晚发您。"),
        ],
        "core": "论文被期刊拒稿，导师要求补实验重写后另投，学业进度受挫压力陡增",
        "acceptable": ["论文被拒稿", "科研受挫", "被导师批评", "延毕风险", "实验重做压力"],
        "forbidden": ["论文录用", "获奖学金", "导师盛赞", "顺利毕业"],
    },
    {
        "arc_id": "C_SHOP_INSPECT", "polarity": -1,
        "events": [
            ("11:20", "MIC", "（检查人员）后厨台账不全，消防通道还堆着货，限期三天整改，复查不过就停业。"),
            ("13:00", "MIC", "（{name}）今天下午谁都别休，货全部清走，台账连夜补齐！"),
            ("20:10", "APP", "微信-店员群｜{name}：整改清单我发群里了，明早八点对照逐项过。"),
        ],
        "core": "门店突遭检查被责令三天限期整改否则停业，带全员连夜清货补台账",
        "acceptable": ["门店被检查", "限期整改", "面临停业", "连夜整改", "经营危机"],
        "forbidden": ["检查全优通过", "获评示范门店", "生意火爆扩店"],
    },
    {
        "arc_id": "C_BIG_ORDER", "polarity": 1,
        "events": [
            ("10:40", "MIC", "（客户电话）你们家口碑不错，公司年会两百人的单子交给你，预算五万。"),
            ("10:55", "MIC", "（{name}）您放心，方案明天就给您，绝对办得漂漂亮亮！"),
            ("19:30", "APP", "微信-供货商：定金收到，明早头一车料优先给你送。"),
        ],
        "core": "接到五万元两百人年会大单并收到定金，生意迎来重要突破",
        "acceptable": ["接到大单", "生意突破", "订单火爆", "收入大增", "经营向好"],
        "forbidden": ["订单被取消", "生意惨淡", "亏损关店", "被客户拉黑"],
    },
    {
        "arc_id": "C_OFFER_POACH", "polarity": 0,
        "events": [
            ("12:40", "APP", "微信-猎头Lynn：对方给到涨薪40%加期权，职级平移带团队，本周内要答复。"),
            ("18:40", "MIC", "（{name}自语）40%……可现在项目正到关键期，走还是不走？"),
        ],
        "core": "收到涨薪40%带团队的挖角offer限期答复，在忠诚与机会间纠结抉择",
        "acceptable": ["收到高薪offer", "猎头挖角", "跳槽抉择", "去留纠结", "职业十字路口"],
        "forbidden": ["被裁员", "求职被拒", "毫无职业波动"],
    },
]

# ---------------------------------------------------------------------------
# 三、人际情感弧线池（dim:social 主事件，晚间 19:00~22:40 引爆或全天穿插）
# ---------------------------------------------------------------------------

SOCIAL_ARCS = [
    {
        "arc_id": "S_BREAKUP", "polarity": -1, "shock": True,
        "events": [
            ("13:05", "APP", "微信-{partner}：晚上早点回来吧，有件事想当面说。"),
            ("{shock_t}", "APP", "微信-{partner}：这两年我想了很久，我们性格真的不合适……我们分手吧，东西我周末来取。"),
            ("{shock_t2}", "MIC", "（{name}带哭腔通话）两年了你就发条微信？你出来，当面把话说清楚……"),
        ],
        "core": "晚间遭{partner}微信提出分手，两年感情宣告破裂，情感遭受重创",
        "acceptable": ["恋人提出分手", "感情破裂", "情侣关系终结", "被分手", "协议分开", "恋情告吹"],
        "forbidden": ["甜蜜互动", "求婚订婚", "感情升温", "打情骂俏", "复合成功"],
    },
    {
        "arc_id": "S_PROPOSAL_OK", "polarity": 1, "shock": True,
        "events": [
            ("12:30", "APP", "微信-死党：戒指、气球、灯牌我都布置好了，晚上八点准时开灯，稳住别露馅！"),
            ("{shock_t}", "MIC", "（餐厅，{name}单膝跪地）认识你的第四年，往后每一年都想有你——嫁给我好吗？"),
            ("{shock_t2}", "MIC", "（{partner}哽咽）我愿意！你这家伙藏得也太深了……"),
        ],
        "core": "精心策划晚间求婚成功，{partner}含泪应允，恋情升华为婚约",
        "acceptable": ["求婚成功", "订婚", "感情升华", "步入婚约", "喜结良缘"],
        "forbidden": ["求婚被拒", "分手", "感情破裂", "冷战", "争吵收场"],
    },
    {
        "arc_id": "S_PARENT_ILL", "polarity": -1, "shock": True,
        "events": [
            ("09:10", "APP", "微信-爸：你妈这几天总说胸口不舒服，今天我带她去医院查查，你别分心。"),
            ("{shock_t}", "APP", "微信-爸：CT结果出来了，医生说肺上有个结节得住院进一步检查……你有空回来一趟吗。"),
            ("{shock_t2}", "MIC", "（{name}通话）挂我这周的号！我明天一早的高铁就回去，妈那边先别吓着她。"),
        ],
        "core": "晚间得知母亲查出肺部结节需住院进一步检查，心急如焚连夜订票回乡",
        "acceptable": ["母亲查出结节", "亲人健康告急", "家人住院", "为母病忧心", "紧急回乡探病"],
        "forbidden": ["母亲体检全优", "家人康复出院", "家庭无恙", "旅游团聚"],
    },
    {
        "arc_id": "S_FRIEND_LOAN_CLASH", "polarity": -1, "shock": True,
        "events": [
            ("11:45", "APP", "微信-{friend}：兄弟再宽限一个月，这个月真周转不开。"),
            ("{shock_t}", "MIC", "（电话，{name}）说好三个月还的两万块，都拖半年了！我买房首付就等这笔钱！"),
            ("{shock_t2}", "APP", "微信-{friend}：行，你别把话说这么难听，钱我想办法，朋友做到头了。"),
        ],
        "core": "为拖欠半年的两万元借款与好友{friend}电话摊牌，多年友情濒临破裂",
        "acceptable": ["朋友欠钱翻脸", "催债伤感情", "友情破裂", "借款纠纷摊牌", "为钱绝交"],
        "forbidden": ["朋友如期还款", "友情升温", "结伴出游", "把酒言欢"],
    },
    {
        "arc_id": "S_RECONCILE", "polarity": 1, "shock": True,
        "events": [
            ("10:20", "APP", "微信-{friend}：那件事是我不对，一直没敢跟你开口……今晚有空吗，我请你吃老地方。"),
            ("{shock_t}", "MIC", "（餐馆，{friend}）对不起，拖了半年才说出口。（{name}）行了行了，来，这杯干了这页翻篇。"),
        ],
        "core": "冷战半年的挚友{friend}主动道歉，晚间老地方把酒言和，友情失而复得",
        "acceptable": ["挚友和好", "冰释前嫌", "友情修复", "重归于好", "道歉和解"],
        "forbidden": ["绝交", "争吵升级", "友情破裂", "拉黑删除"],
    },
    {
        "arc_id": "S_BLIND_DATE_GOOD", "polarity": 1, "shock": True,
        "events": [
            ("12:50", "APP", "微信-妈：晚上七点半，对方也是{city}工作的，人家照片我看了很精神，你穿正式点！"),
            ("{shock_t}", "MIC", "（咖啡馆，相亲对象）没想到你也徒步！下个月山线一起？（{name}）一言为定，加个微信。"),
            ("{shock_t2}", "APP", "微信-相亲对象：今天聊得很开心，周末那个展一起去呀？"),
        ],
        "core": "母亲安排的相亲意外投缘，互加微信约定周末再见，桃花萌芽",
        "acceptable": ["相亲聊得投缘", "遇到心动对象", "桃花运来了", "约定二次见面", "感情萌芽"],
        "forbidden": ["相亲翻车", "话不投机", "被放鸽子", "互删好友"],
    },
    {
        "arc_id": "S_DIVORCE_TALK", "polarity": -1, "shock": True,
        "events": [
            ("08:30", "APP", "微信-{partner}：晚上把话谈完吧，房子、孩子怎么分，你考虑好。"),
            ("{shock_t}", "MIC", "（客厅，{partner}）房子归我，孩子抚养权也归我，你只管出抚养费。（{name}）孩子的事没得谈，我们法庭见！"),
        ],
        "core": "与{partner}就离婚条件彻夜谈判，因房产与孩子抚养权分歧巨大谈崩，扬言诉讼",
        "acceptable": ["离婚谈判", "婚姻破裂", "争夺抚养权", "分割财产谈崩", "对簿公堂"],
        "forbidden": ["婚姻甜蜜", "复合", "二人世界度假", "感情升温"],
    },
    {
        "arc_id": "S_KID_AWARD", "polarity": 1, "shock": True,
        "events": [
            ("16:20", "APP", "微信-班主任：恭喜！{kid}的作品拿了全市一等奖，下周五颁奖，请家长出席。"),
            ("{shock_t}", "MIC", "（家里，{kid}）爸妈快看奖状！老师说全市就三个一等奖！（{name}）我们家出小画家啦，走，下馆子庆祝！"),
        ],
        "core": "孩子{kid}斩获全市一等奖，全家晚间下馆子庆祝，家庭氛围其乐融融",
        "acceptable": ["孩子获奖", "家庭喜事", "阖家欢庆", "子女出息", "家庭温馨"],
        "forbidden": ["孩子闯祸被请家长", "家庭争吵", "亲子冲突", "成绩滑坡挨批"],
    },
    {
        "arc_id": "S_ROOMMATE_CONFLICT", "polarity": -1, "shock": True,
        "events": [
            ("08:10", "MIC", "（合租客厅）你外卖盒堆一周了！水电费也拖着不交，这日子没法过了！"),
            ("{shock_t}", "MIC", "（{name}）房租我按时交的，公共区你一次没扫过，要么按规矩来要么换房住！"),
            ("{shock_t2}", "APP", "微信-室友：行，月底我搬走，押金找房东掰扯去。"),
        ],
        "core": "与室友因卫生和水电费彻底闹翻，对方撂话月底搬走，合租关系破裂",
        "acceptable": ["室友闹翻", "合租矛盾爆发", "为水电费争吵", "室友要搬走", "同住关系破裂"],
        "forbidden": ["室友和睦聚餐", "结伴出游", "关系升温", "续约同住"],
    },
    {
        "arc_id": "S_LONG_DIST_COLD", "polarity": -1, "shock": True,
        "events": [
            ("12:20", "APP", "微信-{partner}：@{name} 你昨晚又没回消息。"),
            ("{shock_t}", "APP", "微信-{partner}：视频三次你挂三次，异地这半年就我一个人在撑，你自己想想还谈不谈了。"),
            ("{shock_t2}", "MIC", "（{name}自语）不是不想接……可每次开口就是吵。这段感情还救得回来吗。"),
        ],
        "core": "异地恋冷战升级，{partner}下最后通牒质问关系是否继续，感情岌岌可危",
        "acceptable": ["异地恋冷战", "感情最后通牒", "恋情濒危", "沟通破裂", "感情摇摇欲坠"],
        "forbidden": ["甜蜜视频", "异地奔现团聚", "感情稳定升温", "订婚"],
    },
    {
        "arc_id": "S_FAMILY_REUNION", "polarity": 1, "shock": True,
        "events": [
            ("09:30", "APP", "微信-姐：我和爸妈高铁下午三点到，别订外卖，晚上妈给你做一桌。"),
            ("{shock_t}", "MIC", "（家里）妈：瘦了瘦了，锅里炖着排骨汤。爸：你租这屋采光不错，比视频里强。（{name}）你们能来比啥都强！"),
        ],
        "core": "久别的父母与姐姐来{city}探望，晚间家宴其乐融融，亲情充电",
        "acceptable": ["家人来访团聚", "亲情温暖", "家宴其乐融融", "久别重逢", "家人齐聚"],
        "forbidden": ["家庭争吵", "亲人重病", "独自过节冷清", "与父母决裂"],
    },
    {
        "arc_id": "S_NEIGHBOR_QUARREL", "polarity": -1, "shock": True,
        "events": [
            ("07:20", "MIC", "（楼道）您家装修电钻六点半就响，孩子还在睡觉！麻烦按物业规定九点以后再施工！"),
            ("{shock_t}", "MIC", "（晚间楼道）（邻居）我装修还得看你脸色？（{name}）再违规施工我直接投诉城管，咱们走着瞧！"),
            ("{shock_t2}", "APP", "微信-物业管家：已记录您的投诉，明日将约谈对方业主并转告施工时段规定。"),
        ],
        "core": "因邻居违规清晨施工两度争执并向物业投诉，邻里关系剑拔弩张",
        "acceptable": ["邻里因噪音争执", "投诉邻居施工", "邻里矛盾激化", "与邻居吵架", "楼道冲突"],
        "forbidden": ["邻里互赠美食", "和睦互助", "结伴遛弯", "邻居致歉和解"],
    },
    {
        "arc_id": "S_BESTIE_WEDDING", "polarity": 1, "shock": True,
        "events": [
            ("14:10", "APP", "微信-{friend}：下月18号我结婚！伴娘（郎）必须是你，礼服我都给你留好了！"),
            ("{shock_t}", "MIC", "（电话，{name}）从大学宿舍到你出嫁，十年了……说好的我可以哭但你不许哭！"),
        ],
        "core": "挚友{friend}官宣婚讯并郑重邀请当伴娘（郎），十年友情见证幸福时刻",
        "acceptable": ["挚友结婚邀约", "受邀当伴娘", "喜讯临门", "友情见证幸福", "为好友高兴"],
        "forbidden": ["婚礼取消", "友情破裂", "被移出宾客名单", "闹掰绝交"],
    },
    {
        "arc_id": "S_PET_LOST_FOUND", "polarity": 1, "shock": True,
        "events": [
            ("07:50", "MIC", "（{name}急喊）豆豆？豆豆！门没关严跑出去了……小区群里发寻狗启事，快！"),
            ("12:15", "APP", "微信-小区群｜{name}：棕色柯基走失，尾随必谢，红包答谢！"),
            ("{shock_t}", "APP", "微信-小区群｜3栋阿姨：是不是这只？在快递驿站后面趴着呢！"),
            ("{shock_t2}", "MIC", "（{name}哽咽）豆豆！吓死我了你个小祖宗……阿姨太感谢了，红包您务必收下！"),
        ],
        "core": "爱犬清晨走失全天悬心寻找，晚间经邻居线索寻回，虚惊一场喜极而泣",
        "acceptable": ["宠物走失又寻回", "失而复得", "全城寻狗", "虚惊一场", "邻里相助寻宠"],
        "forbidden": ["宠物丢失未找回", "宠物离世", "平静无事的一天"],
    },
]

# ---------------------------------------------------------------------------
# 四、财务事件池（dim:finance）
# ---------------------------------------------------------------------------

FINANCE_EVENTS = [
    {
        "fin_id": "F_CREDIT_REPAY",
        "events": [("08:45", "APP", "银行APP：您尾号{card}的信用卡本期账单{amt}元已自动还款成功。")],
        "core": "信用卡自动还款{amt}元成功，无新增大额负债",
        "acceptable": ["信用卡还款{amt}元", "按期还清账单", "偿还信用卡", "无新增负债"],
        "forbidden": ["信用卡逾期", "新增大额借贷", "收到巨额进账", "债务违约"],
        "amt_range": (1800, 9800),
    },
    {
        "fin_id": "F_MORTGAGE",
        "events": [("09:05", "APP", "银行APP：您的住房贷款本月月供{amt}元已扣款成功，剩余期数{n}期。")],
        "core": "房贷月供{amt}元如期扣款，家庭负债结构稳定无异常",
        "acceptable": ["房贷扣款{amt}元", "月供正常缴纳", "按揭如期还款", "负债平稳"],
        "forbidden": ["断供逾期", "提前还清全部房贷", "新增购房", "被银行催收"],
        "amt_range": (3200, 12800),
    },
    {
        "fin_id": "F_SALARY_IN",
        "events": [("10:15", "APP", "银行APP：您的账户入账工资{amt}元。"),
                   ("10:16", "APP", "记账APP提醒：本月储蓄目标完成 60%，继续加油。")],
        "core": "工资{amt}元到账，现金流为正，储蓄计划推进正常",
        "acceptable": ["工资到账{amt}元", "月薪入账", "收入进账", "现金流健康"],
        "forbidden": ["工资被拖欠", "收入断流", "账户被冻结", "大额亏损"],
        "amt_range": (6500, 32000),
    },
    {
        "fin_id": "F_FUND_LOSS",
        "events": [("15:05", "APP", "基金APP：您持有的组合今日估值下跌 2.8%，浮亏约{amt}元。"),
                   ("15:08", "APP", "微信-基金讨论群：别慌，定投照常，跌了就当打折加仓。")],
        "core": "基金单日浮亏约{amt}元，账面缩水但未割肉离场，坚持定投策略",
        "acceptable": ["基金浮亏{amt}元", "投资账面缩水", "理财下跌", "持仓亏损但未卖出"],
        "forbidden": ["投资大赚", "清仓获利了结", "中奖暴富", "毫无投资波动"],
        "amt_range": (600, 8600),
    },
    {
        "fin_id": "F_TRANSFER_PARENT",
        "events": [("19:05", "APP", "微信支付：您向「妈妈」转账{amt}元。备注：天冷买件厚外套，别省。")],
        "core": "向母亲转账{amt}元贴补家用，尽孝支出，无其他大额变动",
        "acceptable": ["给母亲转账{amt}元", "孝亲支出", "贴补父母家用", "家庭转账"],
        "forbidden": ["向父母借钱", "家庭财务纠纷", "拒绝赡养"],
        "amt_range": (1000, 5000),
    },
    {
        "fin_id": "F_REFUND_IN",
        "events": [("13:40", "APP", "购物APP：您退回的商品验收通过，退款{amt}元已原路退回。")],
        "core": "网购退货成功退款{amt}元到账，当日仅剩咖啡外卖等小额消费",
        "acceptable": ["收到退款{amt}元", "退货回款", "小额资金回流", "无大额支出"],
        "forbidden": ["退款被拒", "遭遇购物诈骗", "大额透支消费"],
        "amt_range": (89, 2400),
    },
    {
        "fin_id": "F_PRESALE_PAY",
        "events": [("20:35", "APP", "购物APP：您已支付预售定金{amt}元，尾款支付时间为下周一 20:00。"),
                   ("20:37", "APP", "记账APP：本月「购物」预算已使用 82%，请注意控制。")],
        "core": "支付大促预售定金{amt}元，购物预算逼近上限被记账APP预警",
        "acceptable": ["付预售定金{amt}元", "购物预算吃紧", "剁手消费", "大促下单"],
        "forbidden": ["全额免单", "毫无消费", "退出购物车省钱成功"],
        "amt_range": (300, 3200),
    },
    {
        "fin_id": "F_NO_BIG_CHANGE",
        "events": [("12:35", "APP", "支付APP：午餐消费{amt}元。"),
                   ("21:30", "APP", "记账APP日报：今日总支出{amt2}元，均为餐饮与交通小额消费。")],
        "core": "当日仅餐饮交通小额支出共约{amt2}元，无任何大额资产负债变动",
        "acceptable": ["仅小额日常消费", "财务无大变动", "收支平稳", "无新增债务"],
        "forbidden": ["大额进账", "大额借贷", "投资爆仓", "financial windfall 暴富"],
        "amt_range": (18, 45),
    },
]

# ---------------------------------------------------------------------------
# 五、琐碎日常填充池（海量低熵日常，与关键大事混编）
# ---------------------------------------------------------------------------

FILLERS = [
    ("07:35", "MIC", "（早餐摊）老板，一套煎饼加蛋，不要香菜。——好嘞，四块五。"),
    ("07:52", "APP", "天气APP：今日多云转晴，18~26℃，空气质量良。"),
    ("08:20", "MIC", "（地铁广播）本次列车开往市中心方向，下一站换乘二号线。"),
    ("08:26", "APP", "新闻APP推送：本市新增三条夜间公交线路，覆盖软件园片区。"),
    ("09:15", "MIC", "（茶水间）新来的咖啡机豆子不错。——是吧，比楼下三十块的强。"),
    ("12:25", "APP", "外卖APP：您的订单已由骑手取货，预计 20 分钟后送达。"),
    ("12:48", "MIC", "（同事）下午三点那个会挪到明天了。——收到，正好把材料再顺一遍。"),
    ("13:15", "APP", "快递APP：您的包裹已放至驿站 3 号货架，取件码 8-1024。"),
    ("15:20", "MIC", "（咖啡店）冰美式做好了，请拿好。——谢谢。"),
    ("16:05", "APP", "音乐APP：根据你的口味生成了今日歌单「傍晚的风」。"),
    ("17:45", "MIC", "（驿站）取件码多少？——8-1024。——好，最里面那排。"),
    ("18:20", "MIC", "（超市）西红柿今天特价，三块九一斤。——来两斤，再拿盒鸡蛋。"),
    ("18:55", "APP", "运动APP：今日步数已达标，击败了 76% 的好友。"),
    ("19:40", "MIC", "（楼下遛弯）您家狗真乖。——嗨，就是见谁都摇尾巴。"),
    ("21:05", "APP", "视频APP：您追的剧更新了 2 集。"),
    ("22:10", "APP", "水电缴费提醒：本月电费 87.4 元将于三日后自动代扣。"),
    ("12:58", "MIC", "（食堂）今天糖醋排骨不错。——早说啊，我都打完饭了。"),
    ("16:40", "APP", "网盘APP：您的照片已自动备份 36 张。"),
    ("20:15", "MIC", "（电话-快递员）您在家吗？有个到付件。——放门口就行，谢谢。"),
    ("08:05", "APP", "共享单车APP：本次骑行 1.8 公里，费用 1.5 元。"),
]

# ---------------------------------------------------------------------------
# 六、体征模板（dim:health —— 与情感冲击时刻联动的宏观摘要）
# ---------------------------------------------------------------------------

def build_health(rng: random.Random, social_arc: dict, career_pol: int, shock_t: str):
    resting = rng.randint(56, 72)
    steps = rng.randint(4200, 15800)
    sleep_h = round(rng.uniform(5.1, 7.9), 1)
    pol = social_arc["polarity"]
    if pol < 0:
        spike = rng.randint(112, 136)
        sleep_h = round(rng.uniform(4.2, 6.0), 1)
        spike_desc = f"{shock_t} 情绪冲击时刻心率骤升至 {spike}bpm 并持续约 {rng.randint(18, 45)} 分钟"
        core = (f"晨起静息心率 {resting}bpm 日间平稳，{spike_desc}，属情绪应激性心动过速非器质性病变；"
                f"全天步数 {steps} 步，夜间入睡困难仅睡 {sleep_h} 小时，疲劳度偏高")
        acceptable = ["晚间情绪性心率骤升", "应激性心动过速", "心率因情绪冲击飙升", "睡眠不足疲劳", "身心高压"]
        forbidden = ["全天体征毫无波动", "心脏器质性病变确诊", "深睡充足精力充沛", "剧烈运动导致心率上升"]
    elif pol > 0:
        spike = rng.randint(98, 118)
        spike_desc = f"{shock_t} 兴奋时刻心率短暂升至 {spike}bpm 随后自行回落"
        core = (f"晨起静息心率 {resting}bpm，日间整体平稳，{spike_desc}，属喜悦兴奋性生理波动；"
                f"全天步数 {steps} 步，睡眠 {sleep_h} 小时，整体状态良好")
        acceptable = ["晚间兴奋性心率上升", "喜悦引起的生理波动", "体征整体平稳健康", "状态良好"]
        forbidden = ["恶性心律失常", "情绪崩溃引发心悸", "疾病性心动过速", "健康告急"]
    else:
        core = (f"晨起静息心率 {resting}bpm，全天心率平稳无异常波动；步数 {steps} 步，"
                f"睡眠 {sleep_h} 小时，仅久坐与轻度疲劳提醒")
        acceptable = ["全天体征平稳", "心率无异常", "轻度疲劳", "健康无警报"]
        forbidden = ["心率骤升告警", "突发疾病", "跌倒事故", "急救送医"]
    if career_pol < 0:
        core += "；日间工作高压时段伴短时心率上浮与压力升高提示"
    sensor_events = [
        ("07:02", "SENSOR", f"晨起体征摘要：静息心率 {resting}bpm，血氧 {rng.randint(96, 99)}%，昨夜睡眠 {sleep_h} 小时。"),
        (shock_t if pol != 0 else "14:50", "SENSOR",
         (f"心率告警：{spike}bpm（静息状态，无运动特征），已记录情绪应激事件。" if pol < 0 else
          f"心率提示：{spike}bpm，情绪兴奋波动，无风险。" if pol > 0 else
          "久坐提醒：您已连续静坐 2 小时，建议起身活动。")),
        ("23:30", "SENSOR", f"全天汇总：总步数 {steps} 步，活动消耗 {rng.randint(220, 640)} 千卡，压力指数{'偏高' if pol < 0 or career_pol < 0 else '正常'}。"),
    ]
    return {"core_content": core, "acceptable_directions": acceptable,
            "forbidden_directions": forbidden,
            "anchor_entities": ["佩戴者", f"{resting}bpm", f"{steps}步", f"{sleep_h}小时"]}, sensor_events


# ---------------------------------------------------------------------------
# 七、情绪矩阵（dim:emotion —— 事业极性 × 情感极性）
# ---------------------------------------------------------------------------

EMOTION_MATRIX = {
    (-1, -1): {
        "core": "白天职场受挫委屈压抑，晚间再遭情感/家庭重击，情绪跌入谷底濒临崩溃，全天主基调为高压、焦虑与绝望",
        "acceptable": ["双重打击情绪崩溃", "焦虑绝望", "身心俱疲濒临崩塌", "极度高压", "雪上加霜的一天"],
        "forbidden": ["轻松愉悦", "平静祥和", "幸福满溢", "毫无情绪波动"],
    },
    (-1, 0): {
        "core": "职场受挫带来的委屈与焦虑贯穿全天，晚间靠日常琐事勉强平复，主基调为压抑低落",
        "acceptable": ["压抑低落", "职场挫败感", "焦虑烦闷", "情绪down到谷底"],
        "forbidden": ["兴高采烈", "志得意满", "全天愉快"],
    },
    (-1, 1): {
        "core": "白天职场受挫情绪低落，晚间被亲友喜事治愈，先抑后扬苦尽甘来，主基调由阴转晴",
        "acceptable": ["先抑后扬", "白天低落晚间被治愈", "苦尽甘来", "情绪触底反弹", "阴转晴"],
        "forbidden": ["全天绝望崩溃", "全天平淡无波", "喜事导致情绪崩塌"],
    },
    (0, -1): {
        "core": "日间工作平常有序，晚间突遭情感/家庭变故情绪急坠，主基调为夜间的震惊、心痛与难眠",
        "acceptable": ["晚间情绪急坠", "震惊心痛", "深夜崩溃难眠", "情感重创"],
        "forbidden": ["全天甜蜜幸福", "平静喜悦收尾", "毫无波澜"],
    },
    (0, 0): {
        "core": "全天节奏平常，压力与琐事并存但无剧烈波动，主基调为平稳中略带疲惫",
        "acceptable": ["平稳略疲惫", "波澜不惊", "普通的一天", "轻微压力"],
        "forbidden": ["情绪崩溃", "狂喜暴怒", "重大情感转折"],
    },
    (0, 1): {
        "core": "日间平常运转，晚间喜事降临情绪升温，主基调为惊喜、温暖与幸福",
        "acceptable": ["晚间惊喜幸福", "温暖治愈", "喜事临门心情大好"],
        "forbidden": ["悲伤崩溃", "焦虑绝望", "冷漠麻木"],
    },
    (1, -1): {
        "core": "白天事业高光志得意满，晚间骤遭情感/家庭打击从云端跌落，大起大落冰火两重天",
        "acceptable": ["先扬后抑", "大起大落", "从高光跌入谷底", "冰火两重天", "乐极生悲"],
        "forbidden": ["全天幸福圆满", "全天低迷", "平静无波"],
    },
    (1, 0): {
        "core": "事业捷报带来的振奋贯穿全天，晚间平静收尾，主基调为自信与踏实",
        "acceptable": ["振奋自信", "成就感满满", "心情大好"],
        "forbidden": ["沮丧失落", "崩溃大哭", "焦虑失眠"],
    },
    (1, 1): {
        "core": "事业与情感双喜临门，全天情绪高涨幸福感爆棚，主基调为狂喜与感恩",
        "acceptable": ["双喜临门", "幸福感爆棚", "人生高光日", "喜上加喜"],
        "forbidden": ["悲伤绝望", "情绪崩溃", "焦虑主导", "平淡如水"],
    },
}


# ---------------------------------------------------------------------------
# 八、单卷装配
# ---------------------------------------------------------------------------

def _t(rng: random.Random, h1: int, h2: int) -> str:
    return f"{rng.randint(h1, h2):02d}:{rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]):02d}"


def _plus(tstr: str, minutes: int) -> str:
    h, m = map(int, tstr.split(":"))
    total = min(h * 60 + m + minutes, 23 * 60 + 30)
    return f"{total // 60:02d}:{total % 60:02d}"


def build_question(idx: int) -> dict:
    rng = random.Random(f"{SEED}-{idx}")
    name = rng.choice(SURNAMES) + rng.choice(GIVEN)
    occ, a1, a2 = rng.choice(OCCUPATIONS)
    age = rng.randint(a1, a2)
    gender = rng.choice(["男", "女"])
    city = rng.choice(CITIES)
    partner = rng.choice(PARTNER_TITLES_M if gender == "男" else PARTNER_TITLES_F)
    friend = rng.choice(SURNAMES) + rng.choice(["斌", "琳", "凯", "洁", "涛", "薇"])
    kid = rng.choice(["朵朵", "牛牛", "糖糖", "壮壮", "妞妞"])

    career = rng.choice(CAREER_ARCS)
    social = rng.choice(SOCIAL_ARCS)
    fin = rng.choice(FINANCE_EVENTS)

    shock_t = _t(rng, 19, 22)
    shock_t2 = _plus(shock_t, rng.randint(6, 25))
    amt = rng.randint(*fin["amt_range"])
    amt2 = amt + rng.randint(10, 30)
    ctx = {"name": name, "partner": partner, "friend": friend, "kid": kid, "city": city,
           "shock_t": shock_t, "shock_t2": shock_t2, "amt": amt, "amt2": amt2,
           "card": rng.randint(1000, 9999), "n": rng.randint(36, 300)}

    def fmt(s: str) -> str:
        for k, v in ctx.items():
            s = s.replace("{" + k + "}", str(v))
        return s

    events = []
    for t, ch, txt in career["events"]:
        events.append({"time": fmt(t), "channel": ch, "content": fmt(txt)})
    for t, ch, txt in social["events"]:
        events.append({"time": fmt(t), "channel": ch, "content": fmt(txt)})
    for t, ch, txt in fin["events"]:
        events.append({"time": fmt(t), "channel": ch, "content": fmt(txt)})

    health_gt, sensor_events = build_health(rng, social, career["polarity"], shock_t)
    for t, ch, txt in sensor_events:
        events.append({"time": t, "channel": ch, "content": txt})

    for t, ch, txt in rng.sample(FILLERS, rng.randint(8, 12)):
        events.append({"time": t, "channel": ch, "content": txt})

    events.sort(key=lambda e: e["time"])

    emo = EMOTION_MATRIX[(career["polarity"], social["polarity"])]
    pol_word = {(-1, -1): "双重打击身心俱创的高压危机日",
                (1, 1): "事业情感双丰收的人生高光日",
                (1, -1): "白天高光晚间坠落的冰火两重天",
                (-1, 1): "白天受挫晚间被治愈的先抑后扬日"}
    global_core = (f"{fmt(career['core'])}；{fmt(social['core'])}。"
                   f"核心剧情主线：{pol_word.get((career['polarity'], social['polarity']), '大事与日常交织的普通高压日')}")

    gt = {
        "global_daily_summary": {
            "core_content": global_core,
            "acceptable_directions": [fmt(x) for x in career["acceptable"][:3] + social["acceptable"][:3]],
            "forbidden_directions": [fmt(x) for x in career["forbidden"][:2] + social["forbidden"][:3]],
            "anchor_entities": [name, fmt(career["arc_id"]), fmt(social["arc_id"])],
        },
        "dim:health": health_gt,
        "dim:social": {
            "core_content": fmt(social["core"]),
            "acceptable_directions": [fmt(x) for x in social["acceptable"]],
            "forbidden_directions": [fmt(x) for x in social["forbidden"]],
            "anchor_entities": [name] + ([fmt("{partner}")] if "{partner}" in json.dumps(social["events"], ensure_ascii=False) else [])
                               + ([friend] if "{friend}" in json.dumps(social["events"], ensure_ascii=False) else []),
        },
        "dim:emotion": {
            "core_content": emo["core"],
            "acceptable_directions": emo["acceptable"],
            "forbidden_directions": emo["forbidden"],
            "anchor_entities": [name],
        },
        "dim:finance": {
            "core_content": fmt(fin["core"]),
            "acceptable_directions": [fmt(x) for x in fin["acceptable"]],
            "forbidden_directions": [fmt(x) for x in fin["forbidden"]],
            "anchor_entities": [name, f"{amt}元"],
        },
        "dim:career": {
            "core_content": fmt(career["core"]),
            "acceptable_directions": [fmt(x) for x in career["acceptable"]],
            "forbidden_directions": [fmt(x) for x in career["forbidden"]],
            "anchor_entities": [name, occ],
        },
    }

    return {
        "question_id": f"QD_{GENERATOR_AGENT}_{idx:05d}",
        "generator_agent": GENERATOR_AGENT,
        "persona": {"name": name, "gender": gender, "age": age,
                    "occupation": occ, "city": city},
        "arc_tags": {"career": career["arc_id"], "social": social["arc_id"],
                     "finance": fin["fin_id"],
                     "polarity": [career["polarity"], social["polarity"]]},
        "cleaned_daily_stream": {
            "date_span": "07:00~23:30",
            "events": events,
        },
        "directional_ground_truth": gt,
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for i in range(1, TOTAL + 1):
            f.write(json.dumps(build_question(i), ensure_ascii=False) + "\n")
    print(f"generated {TOTAL} -> {OUT}")


if __name__ == "__main__":
    main()
