# -*- coding: utf-8 -*-
"""AIOS 3.0 全天生活流与多维总结高熵出卷官 —— 战队 01a0aa2d-fantonghui。

Master Dispatch #11 第二步（全维度多尺度时间日志总结大考）出卷侧：
生成 10,000 个人的一整天（07:00~23:30）已清洗生活流考卷，并给出六维
【方向性语义标答】（Directional Ground Truth）：

  - dim:global   全局日总结（核心剧情主线）
  - dim:health   健康生理（体征核心变化）
  - dim:social   人际社交（关系状态翻转）
  - dim:emotion  情绪心理（主基调与转折）
  - dim:finance  财务契约（资产债务变动）
  - dim:career   事业行动（推进与受阻）

出卷铁律落实：
  1. 每张卷 = 一个真实人生 24h：关键大事（跨维度冲突/转折）+ 海量琐碎日常；
  2. 标答只给【方向】：acceptable_directions 为可接受方向同义词簇，
     redline_violations 为绝对偏离红线判据（一票否决），严禁死板字句匹配；
  3. 高熵保障：事件模板 × 人设 × 金额/时间/心率参数 × 陷阱（口嗨/转发/广告）
     组合空间 > 10^12，全天事件签名近乎逐人不同；
  4. 因果一致：心率骤升时刻 = 负面事件时刻；情绪走向 = 白天/晚间事件符号组合；
  5. 确定性可复现：固定随机种子 20260916。

输出（题目自含标答，符合出题规范单 JSON 四键）：
  benchmarks/daily_summary/questions/questions_01a0aa2d-fantonghui.jsonl

用法：python3 scripts/generate_daily_summary_01a0aa2d.py [--n 10000] [--seed 20260916]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN_ID = "01a0aa2d-fantonghui"

# ---------------------------------------------------------------------------
# 人设池
# ---------------------------------------------------------------------------

SUR = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向")
G1 = list("梦雨思梓欣怡泽宇轩晨曦悦然博文静佳俊杰妮涛鹏雪莉娟敏磊芳丽军洋艳丹薇露楠杉澄澈岚熙瑶彤麟麒麒昊天佑辰逸")
G2 = list("华强伟明军平辉志刚勇毅峰涛婷颖洁梅琳晶云莉兰薇霞凤春香雅静淑惠美翠莲雪芳晴朗曦阳星辰海阔天空城")

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "重庆",
          "苏州", "天津", "长沙", "郑州", "青岛", "合肥", "福州", "厦门"]
JOBS = ["后端工程师", "前端工程师", "产品经理", "运营专员", "中学教师", "小学班主任", "护士",
        "销售代表", "平面设计师", "货车司机", "厨师", "公务员", "律师助理", "会计", "快递站长",
        "健身教练", "房产中介", "咖啡师", "电商运营", "测试工程师", "数据分析师", "行政专员",
        "机械工程师", "电气工程师", "药剂师", "银行柜员", "保险顾问", "外贸专员", "翻译",
        "新媒体编辑", "插画师", "视频剪辑师", "物业管家", "仓储主管", "美容顾问", "兽医助理"]

TRIVIA_MORNING = [
    ("mic", "同事", "早，昨晚看球了吗？最后那个球绝了。"),
    ("app", "企业微信|人事部", "今日站会改到10:00，请准时参加。"),
    ("mic", "咖啡店店员", "中杯美式少冰是吧？好嘞。"),
    ("app", "菜鸟驿站", "您的包裹已到驿站，凭取件码领取。"),
    ("mic", "楼下保安", "您有个快递放岗亭了啊。"),
    ("app", "支付宝|公交码", "乘车扣款2元成功。"),
]
TRIVIA_NOON = [
    ("mic", "同事", "中午拼单不？我点麻辣烫。"),
    ("app", "美团外卖", "骑手已取餐，预计12:05送达。"),
    ("mic", "同事", "下午帮你带杯奶茶，老规矩三分糖？"),
    ("sensor", None, "步数已达4,120步，久坐提醒已推送。"),
    ("mic", "前台", "有您一个挂号信，下来拿一下。"),
]
TRIVIA_AFTERNOON = [
    ("mic", "同事", "周末爬山去不去？天气预报说晴天。"),
    ("app", "微信|工作群", "@所有人 周报今晚八点前提交。"),
    ("mic", "电梯里邻居", "今天风大，多穿点。"),
    ("app", "钉钉|项目群", "文档V2.3已更新，有空看一眼。"),
    ("mic", "同事", "会议室投影又坏了，你那边能投屏吗？"),
    ("sensor", None, "连续静坐112分钟，颈椎放松提醒。"),
]
TRIVIA_EVENING = [
    ("app", "美团外卖", "今晚的晚餐订单已送达。"),
    ("mic", "便利店店员", "关东煮刚加汤，要来一份吗？"),
    ("mic", "室友", "帮我带瓶酱油呗，谢谢啦。"),
    ("app", "微信|跑步群", "今晚8点江边约跑，接龙+1。"),
    ("sensor", None, "步数突破9,000步，今日活动量达标。"),
]
TRIVIA_NIGHT = [
    ("mic", "家人", "明天早饭想吃啥？我早点起来做。"),
    ("app", "微信|老友", "晚安，周末见！"),
    ("mic", "室友", "热水器我修好了，你晚点洗澡没问题。"),
    ("app", "网易云", "《通勤充电站》歌单本周播放时长榜首。"),
]

# ---------------------------------------------------------------------------
# 事件模板（sign: -1 挫折/压力, +1 突破/升温, 0 平稳）
# 每条: (id, sign, core模板, anchors, acceptable, redlines, slices)
# slices: (t_offset_min, src, who_app, text)
# ---------------------------------------------------------------------------

CAREER_NEG = [
    ("CN1", "季度方案汇报被领导当众否决，被批抓不住重点，限期重做",
     ["汇报被否", "当众批评", "限期重做"],
     ["方案被否", "汇报没通过", "被领导批评", "被打回重做", "当众下不来台"],
     ["晋升通过", "方案获好评", "项目大捷", "被表扬"],
     [(0, "mic", "领导", "这个方案完全没抓到重点，重做，下周一给我。"),
      (18, "mic", "邻座同事", "（低声）别往心里去，他今天对谁都这样。"),
      (95, "app", "企业微信|李总监", "方案打回，周五下班前重新提交，附整改说明。")]),
    ("CN2", "线上事故责任被算到头上，被要求写书面检讨并做全组复盘",
     ["背锅", "书面检讨", "全组复盘"],
     ["背锅", "被追责", "写检讨", "替罪", "责任划分不公"],
     ["立功受奖", "事故与己无关且被澄清", "升职"],
     [(5, "app", "企业微信|运维群", "P2事故定责：操作记录指向你账号，明早十点复盘会。"),
      (40, "mic", "领导", "检讨明天给我，该是谁的问题就是谁的问题。")]),
    ("CN3", "半年度绩效结果公布为C，进入改进观察名单",
     ["绩效C", "观察名单"],
     ["绩效差", "考核垫底", "被约谈", "绩效不达标"],
     ["绩效优秀", "涨薪", "评优"],
     [(0, "app", "企业微信|HR", "半年度绩效结果：C。本周五前提交改进计划。"),
      (30, "mic", "领导", "下个周期盯紧点，别再踩线了。")]),
    ("CN4", "跟进三个月的客户临时毁约，订单归零，团队士气受挫",
     ["客户毁约", "订单归零"],
     ["客户跑了", "单子黄了", "毁约", "白忙三个月"],
     ["签约成功", "大单落定", "客户续约"],
     [(0, "mic", "客户", "抱歉，上面换了供应商，合作暂时取消了。"),
      (25, "app", "企业微信|销售部", "本月目标缺口{gap}万，各组连夜想办法。")]),
    ("CN5", "晋升答辩未通过，提名被评审委员会驳回",
     ["晋升驳回", "答辩未过"],
     ["晋升失败", "没评上", "答辩挂了", "提名被拒"],
     ["晋升通过", "升职加薪", "答辩优秀"],
     [(0, "app", "企业微信|HR", "本轮晋升评审结果：未通过。可预约反馈面谈。"),
      (20, "mic", "领导", "差距主要在项目影响力，明年再来。")]),
    ("CN6", "被调岗至边缘业务线做收尾维护，新方向未明",
     ["调岗", "边缘业务"],
     ["被调岗", "发配边缘", "岗位调整", "不受重用"],
     ["调任核心岗", "升职", "方向明确"],
     [(0, "app", "企业微信|HR", "岗位调整通知：转入维护组，下周一报到。"),
      (35, "mic", "同事", "那摊子活……你多保重。")]),
    ("CN7", "项目竞标输给对手公司，三个月准备心血白费",
     ["竞标失利", "心血白费"],
     ["投标失败", "输了竞标", "被截胡", "白准备了"],
     ["中标", "竞标成功", "拿下合同"],
     [(0, "mic", "领导", "标丢了，对手低了八个百分点，没办法。"),
      (15, "app", "企业微信|项目群", "本次投标未中，材料归档，散会。")]),
    ("CN8", "全员大会上被点名批评（实为流程问题），当众难堪",
     ["大会点名", "当众批评"],
     ["被点名", "公开挨批", "大会上挨训", "当众难堪"],
     ["大会表扬", "公开表彰", "澄清免责"],
     [(0, "mic", "领导（大会）", "有些组的数据管理一塌糊涂，我不点名，自己心里有数！"),
      (12, "mic", "邻座同事", "这明明是流程的锅……唉。")]),
]

CAREER_POS = [
    ("CP1", "晋升答辩通过，下周起升任高级工程师",
     ["晋升通过", "升任高级"],
     ["升职了", "答辩通过", "晋升成功", "提干"],
     ["晋升失败", "被降职", "答辩挂了"],
     [(0, "app", "企业微信|HR", "恭喜！晋升评审通过，下周一生效。"),
      (22, "mic", "领导", "好好干，团队以后一块扛。")]),
    ("CP2", "跟进半年的大客户正式签约，合同金额{amount}万",
     ["大单签约", "{amount}万合同"],
     ["签约成功", "拿下大单", "合同落定", "业绩兑现"],
     ["客户毁约", "投标失败", "单子黄了"],
     [(0, "app", "企业微信|销售部", "签约喜报：合同金额{amount}万，恭喜！"),
      (18, "mic", "领导", "这一单漂亮！晚上加个鸡腿。")]),
    ("CP3", "负责项目按期上线零故障，大群被老板点名表扬",
     ["上线零故障", "老板表扬"],
     ["项目成功", "上线顺利", "被点名表扬", "零事故"],
     ["项目失败", "上线事故", "被批评"],
     [(0, "app", "企业微信|全员群", "项目按期上线，运行零故障，特别表扬项目组！"),
      (15, "mic", "同事", "牛啊，全组跟你沾光。")]),
    ("CP4", "拿到心仪公司offer，涨薪35%，准备提离职流程",
     ["新offer", "涨薪35%"],
     ["拿到offer", "跳槽成功", "涨薪", "新机会确定"],
     ["面试被拒", "offer取消", "跳槽失败"],
     [(0, "app", "电话|HR", "口头offer确认：薪资上浮35%，下周五前回复。"),
      (20, "mic", "自己", "（走廊上憋不住笑，又不能声张）")]),
    ("CP5", "获季度创新奖，奖金10,000元",
     ["创新奖", "奖金1万元"],
     ["获奖", "拿奖金", "季度表彰", "被嘉奖"],
     ["被处罚", "绩效不合格", "通报批评"],
     [(0, "app", "企业微信|HR", "季度创新奖名单公示：恭喜！奖金随下月工资发放。")]),
]

CAREER_NEU = [
    ("CZ1", "收到岗位调整通知，转入新事业部，具体方向待定",
     ["岗位调整", "方向待定"],
     ["调岗", "换部门", "岗位变动", "新事业部"],
     ["被开除", "晋升", "重大变故"],
     [(0, "app", "企业微信|HR", "组织调整通知：你将转入新事业部，汇报关系另行通知。")]),
    ("CZ2", "新项目立项会上被任命为核心模块负责人",
     ["立项", "模块负责人"],
     ["接新项目", "被委以重任", "立项启动", "当负责人"],
     ["项目解散", "被撤职", "重大挫折"],
     [(0, "mic", "领导", "这个模块你来牵头，人你挑，事你定。")]),
]

SOCIAL_NEG = [
    ("SN1", True, "晚间{st}收到{partner}发来的“我们分手吧”，一段感情走到尽头",
     ["分手", "{partner}", "我们分手吧"],
     ["分手", "被提分手", "感情破裂", "失恋", "结束恋情"],
     ["甜蜜互动", "求婚成功", "感情升温", "复合"],
     [(0, "app", "微信|{partner}", "我们分手吧。就这样，别联系了。"),
      (6, "app", "微信|{partner}", "）消息发出去就再没回复，对话框停在{st}。")]),
    ("SN2", False, "结婚纪念日忘了，晚间{partner}冷战，婚姻亮起黄灯",
     ["纪念日忘了", "{partner}冷战"],
     ["纪念日忘了", "配偶冷战", "婚姻亮红灯", "家庭矛盾"],
     ["纪念日惊喜", "恩爱如初", "家庭和睦升温"],
     [(0, "mic", "{partner}", "今天几号你自己看。饭我自己吃过了。")]),
    ("SN3", False, "晚上父母催婚电话演变成激烈争吵，不欢而挂",
     ["催婚", "争吵", "不欢而挂"],
     ["催婚冲突", "和父母吵架", "电话争吵", "催婚压力"],
     ["家庭和睦", "父母支持", "聊天愉快"],
     [(0, "mic", "妈妈", "隔壁小张孩子都上幼儿园了！你到底怎么想的？"),
      (4, "mic", "爸爸", "我们还不是为你好——（电话挂断忙音）")]),
    ("SN4", False, "好友开口借5万被婉拒，多年友谊出现裂痕",
     ["借钱5万", "拒绝", "友谊裂痕"],
     ["朋友借钱被拒", "友谊出裂痕", "借钱纠纷", "人情翻脸"],
     ["友谊升温", "慷慨解囊", "两肋插刀"],
     [(0, "mic", "老友", "5万，就周转两个月，咱俩什么交情……"),
      (5, "mic", "老友", "（沉默十几秒）行，我知道了，先这样吧。（挂断）")]),
    ("SN5", True, "异地恋对象{partner}临时取消周末来访，只回了两个字“累了”",
     ["取消来访", "{partner}", "累了"],
     ["异地恋降温", "被放鸽子", "感情变淡", "对方疏远"],
     ["感情升温", "甜蜜见面", "如胶似漆"],
     [(0, "app", "微信|{partner}", "周末不去了。累了。")]),
    ("SN6", False, "因卫生与噪音问题与合租室友爆发激烈争吵",
     ["室友", "激烈争吵"],
     ["室友吵架", "合租矛盾", "激烈争执", "相处不和"],
     ["室友和睦", "相处愉快", "互帮互助"],
     [(0, "mic", "室友", "洗碗池的碗你堆三天了！说了多少遍？"),
      (3, "mic", "自己", "你自己上周还不是外卖盒堆到发臭！")]),
]

SOCIAL_POS = [
    ("SP1", True, "晚间在江边餐厅求婚成功，{partner}红着眼答应了",
     ["求婚成功", "{partner}"],
     ["求婚成功", "答应求婚", "订婚", "感情大圆满"],
     ["分手", "被拒绝", "感情破裂"],
     [(0, "mic", "自己", "（单膝跪地）嫁给我好吗？"),
      (8, "mic", "{partner}", "……我愿意。（邻桌掌声响起）")]),
    ("SP2", False, "结婚纪念日收到{partner}准备的惊喜晚餐，感动到红了眼",
     ["纪念日惊喜", "{partner}"],
     ["纪念日惊喜", "恩爱", "家庭温暖", "被感动"],
     ["冷战", "吵架", "婚姻危机"],
     [(0, "mic", "{partner}", "进门换鞋——看餐桌！十年了，笨蛋。")]),
    ("SP3", False, "与多年未见的老同学聚会到深夜，近况聊到动情处",
     ["老同学", "聚会"],
     ["同学聚会", "老友重逢", "聊到深夜", "友情保温"],
     ["不欢而散", "翻脸", "聚崩了"],
     [(0, "mic", "老同学", "还记得咱高中天台吗……一晃十年了啊。")]),
    ("SP4", False, "父母来城市看我，做了一桌家乡菜，其乐融融",
     ["父母来访", "家乡菜"],
     ["父母来看我", "家庭团聚", "家乡味道", "其乐融融"],
     ["家庭争吵", "冷锅冷灶", "孤身一人"],
     [(0, "mic", "妈妈", "快趁热吃，你最爱吃的糖醋排骨。")]),
    ("SP5", True, "{partner}升职加薪，两人在江边散步庆祝到很晚",
     ["{partner}升职", "庆祝"],
     ["恋人升职", "一起庆祝", "双喜", "感情甜蜜"],
     ["争吵", "分手", "冷战"],
     [(0, "mic", "{partner}", "我升主管了！走，江边走走，我请宵夜！")]),
    ("SP6", True, "前几日与{partner}闹了别扭，晚间主动服软道歉，两人和好并约定周末短途旅行",
     ["道歉和好", "{partner}"],
     ["和好", "重归于好", "互相理解", "约定旅行"],
     ["继续冷战", "分手", "关系恶化"],
     [(0, "app", "微信|{partner}", "这几天是我不对，别生气了。周末去周边走走？我来订民宿。"),
      (7, "app", "微信|{partner}", "……好呀。这次听我的，去海边。")]),
]

FINANCE = [
    ("F1", -1, "信用卡自动还款{amt}元扣款成功，本月现金流偏紧",
     ["信用卡还款", "{amt}元"], ["还款", "扣款", "账单结清", "信用卡扣款"], ["大额进账", "意外之财", "无资金变动"]),
    ("F2", -1, "房贷月供{amt}元自动扣款，刚性支出照旧",
     ["房贷月供", "{amt}元"], ["房贷扣款", "月供", "还贷压力"], ["提前还清", "无负债", "大额进账"]),
    ("F3", 1, "年终奖{amt}元到账，账户明显回血",
     ["年终奖", "{amt}元"], ["奖金到账", "大额进账", "年终奖发放"], ["大额亏损", "负债增加", "被扣款"]),
    ("F4", -1, "转账借给好友{amt}元应急，约定月底归还",
     ["借出", "{amt}元"], ["借钱给朋友", "资金拆借", "应急借款"], ["借款到账", "收利息", "无资金往来"]),
    ("F5", -1, "违章罚款加保险续费共{amt}元，计划外支出",
     ["罚款", "保险续费", "{amt}元"], ["计划外支出", "罚款缴纳", "续费扣款"], ["退款到账", "无支出"]),
    ("F6", 1, "网购退货退款{amt}元原路退回",
     ["退款", "{amt}元"], ["退款到账", "退货成功"], ["被扣款", "消费升级"]),
    ("F7", -1, "股票账户今日浮亏{amt}元，心情跟着K线走",
     ["浮亏", "{amt}元"], ["投资亏损", "股票浮亏", "账户缩水"], ["涨停回本", "大额盈利"]),
    ("F8", 1, "兼职稿费{amt}元到账，副业开了个头",
     ["稿费", "{amt}元"], ["副业收入", "稿费到账", "外快"], ["副业翻车", "被扣款"]),
    ("F9", -1, "陪家人看病垫付检查费{amt}元",
     ["垫付", "检查费", "{amt}元"], ["医疗支出", "垫付医药费", "家人看病"], ["医保全额报销", "无医疗支出"]),
    ("F10", 0, "汽车保养加油共花{amt}元，养车日常",
     ["保养", "{amt}元"], ["养车支出", "常规消费"], ["卖车套现", "巨额支出"]),
]

TRAPS = [
    ("T1", "app", "微信|大学同学群", "【热搜】知名男星官宣分手，八年长跑告吹……（转发链接）",
     "群转发明星分手新闻（非本人感情事件）", "social",
     ["群转发新闻非本人感情变故"]),
    ("T2", "mic", "同事", "再这么加班下去，老子明天就辞职去大理躺平了，哈哈哈！",
     "同事口嗨辞职玩笑（非本人决定）", "career",
     ["玩笑口嗨非本人辞职决定"]),
    ("T3", "app", "朋友圈广告|平台", "限时免息分期，0首付提新车，名额有限>",
     "平台分期广告（非本人消费/借贷）", "finance",
     ["平台广告非本人消费借贷"]),
]

# 情绪映射: (career_sign, social_sign) -> (主基调, 晚间基调, anchors, acceptable, redlines)
EMOTION_MAP = {
    (-1, -1): ("焦虑压抑", "崩溃绝望", ["焦虑", "委屈", "崩溃"],
               ["焦虑不安", "情绪低落", "崩溃", "绝望", "压力过大", "双重打击", "身心俱疲"],
               ["开心", "兴奋", "平静如常", "如释重负"]),
    (-1, 0): ("焦虑沮丧", "低落收场", ["焦虑", "沮丧"],
              ["焦虑", "沮丧", "情绪低落", "压力山大"], ["兴高采烈", "平静如常", "心花怒放"]),
    (-1, 1): ("先抑后扬", "被温暖抚平", ["委屈", "感动"],
              ["委屈", "先苦后甜", "被治愈", "悲喜交加"], ["全程崩溃", "毫无波澜", "暴怒"]),
    (0, -1): ("失落难过", "委屈孤单", ["失落", "难过"],
              ["失落", "难过", "心里不是滋味", "孤单"], ["欣喜若狂", "平静无波", "亢奋"]),
    (1, -1): ("先扬后抑", "晚间失落", ["振奋", "失落"],
              ["先喜后悲", "心情坐过山车", "高兴不起来"], ["全天亢奋", "毫无起伏", "暴怒"]),
    (1, 1): ("振奋欣喜", "幸福满溢", ["振奋", "幸福"],
             ["双喜临门", "干劲十足", "幸福感爆棚", "亢奋"], ["崩溃", "绝望", "郁郁寡欢"]),
    (0, 1): ("温暖愉快", "踏实幸福", ["温暖", "愉快"],
             ["心情不错", "被治愈", "满足"], ["崩溃", "暴怒", "惶惶不安"]),
    (0, 0): ("平稳偏疲", "略显疲惫", ["疲惫"],
             ["平淡", "有点累", "波澜不惊"], ["狂喜", "崩溃", "暴怒"]),
}

FIN_T_CHOICES = ["08:12", "09:47", "12:47", "15:38", "20:22"]


def _name(rng, used):
    while True:
        nm = rng.choice(SUR) + (rng.choice(G1) if rng.random() < 0.3 else rng.choice(G1) + rng.choice(G2))
        if nm not in used and len(nm) >= 2:
            used.add(nm)
            return nm


def _fmt(tpl, ctx):
    out = tpl
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _sl(t, src, text, who=None, app=None):
    d = {"t": t, "src": src, "text": text}
    if who:
        d["who"] = who
    if app:
        d["app"] = app
    return d


def _src_label(e):
    if e[2] is None:
        return None
    return e[2].split("|")[0], (e[2].split("|", 1)[1] if "|" in e[2] else None)


def _add_event(slices, event, base_t, ctx, day_off=0):
    """把事件切片加入（base_t 为 "HH:MM"，offset 为分钟）。"""
    hh, mm = map(int, base_t.split(":"))
    ev_slices, ev_times = [], []
    for off, src, wa, text in event[-1][:2]:  # 每事件至多2切片，控制卷面体积
        t = (hh * 60 + mm + off + day_off)
        label, sender = (wa.split("|")[0], wa.split("|", 1)[1]) if wa and "|" in wa else (wa, None)
        s = {"t": f"{t//60:02d}:{t%60:02d}", "src": src, "text": _fmt(text, ctx)}
        if src == "mic":
            s["who"] = _fmt(label or "", ctx) or None
        else:
            s["app"] = _fmt(label or "APP", ctx)
            if sender:
                s["sender"] = _fmt(sender, ctx)
        slices.append(s)
        ev_times.append(f"{s['src']}@{s['t']}")
    return ev_times


def _clip(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("；", "，", "、", "："):
        p = cut.rfind(sep)
        if p >= limit // 2:
            return cut[:p]
    return cut


def _truth(dim, core, anchors, acc, red, refs):
    return {
        "core_plot": _clip(core, 48),
        "core_anchors": list(dict.fromkeys(anchors))[:3],
        "acceptable_directions": list(dict.fromkeys(acc))[:3],
        "redline_violations": list(dict.fromkeys(red))[:3],
        "key_evidence_refs": list(dict.fromkeys(refs))[:2],
    }


def generate_person(i, rng, used_names):
    name = _name(rng, used_names)
    age = rng.randint(22, 55)
    city = rng.choice(CITIES)
    job = rng.choice(JOBS)
    rel_r = rng.random()
    relationship = "恋爱中" if rel_r < 0.30 else ("已婚" if rel_r < 0.60 else ("异地恋" if rel_r < 0.75 else "单身"))
    partner = None
    if relationship != "单身":
        partner = _name(rng, used_names)
    ctx = {
        "name": name, "partner": partner or "朋友", "st": "21:05", "ft": "12:47",
        "amt": "3,200", "amount": "480", "gap": "320", "hr0": "76", "hr1": "128",
        "dur": "11", "rhr": "68", "sh": "7", "sm": "12", "steps": "9,860", "maxhr": "128",
    }

    slices = []
    # ---- 晨起体征 ----
    rhr = rng.randint(58, 84)
    sh, sm = rng.randint(5, 8), rng.choice([0, 8, 16, 24, 33, 41, 52])
    wake_t = f"07:{rng.randint(0, 25):02d}"
    slices.append(_sl(wake_t, "sensor",
                      f"晨起静息心率{rhr}bpm；昨夜睡眠{sh}小时{sm}分，深睡占比{rng.randint(14, 31)}%"))
    ctx["rhr"] = str(rhr)
    ctx["sh"], ctx["sm"] = str(sh), f"{sm:02d}"

    # ---- 事业事件 ----
    _cat = rng.choices(("NEG", "POS", "NEU"), weights=(45, 30, 25))[0]
    career = rng.choice({"NEG": CAREER_NEG, "POS": CAREER_POS, "NEU": CAREER_NEU}[_cat])
    c_sign = -1 if career in CAREER_NEG else (1 if career in CAREER_POS else 0)
    ct = f"{rng.randint(10, 16):02d}:{rng.choice(['05', '20', '40', '55'])}"
    if career[0].startswith("CP"):
        ct = f"{rng.randint(15, 17):02d}:{rng.choice(['10', '30', '50'])}"
    career_refs = _add_event(slices, career, ct, ctx)
    ctx_career_core = _fmt(career[1], ctx)

    # ---- 财务事件 ----
    fin = rng.choice(FINANCE)
    f_sign = fin[1]
    _amt_pool = {
        "F1": [2300, 3200, 3850], "F2": [6800, 8600, 9800], "F3": [28000, 36000, 42000],
        "F4": [10000, 20000, 50000], "F5": [1780, 2300, 3850], "F6": [899, 1299, 1999],
        "F7": [2300, 4600, 6000], "F8": [899, 1200, 1500], "F9": [899, 1500, 2300],
        "F10": [1280, 1780, 2200],
    }[fin[0]]
    ctx["amt"] = f"{rng.choice(_amt_pool):,}"
    ft = rng.choice(FIN_T_CHOICES)
    fin_app = rng.choice(["支付宝", "银行APP", "微信支付", "云闪付"])
    fin_text = _fmt(fin[2], ctx)
    slices.append(_sl(ft, "app", ("【账户通知】" if f_sign >= 0 else "【扣款通知】") + fin_text,
                      app=f"{fin_app}|系统通知"))
    fin_refs = [ft]
    ctx_fin_core = fin_text

    # ---- 社交事件 ----
    social_pool = [e for e in (SOCIAL_NEG + SOCIAL_POS)
                   if not (e[1] and relationship == "单身")
                   and not (e[0] == "SN5" and relationship != "异地恋")
                   and not (e[0] == "SN2" and relationship != "已婚")
                   and not (e[0] == "SP2" and relationship != "已婚")]
    social = rng.choice(social_pool)
    s_sign = -1 if social in SOCIAL_NEG else 1
    st = f"{rng.randint(19, 21):02d}:{rng.choice(['05', '25', '40', '55'])}"
    ctx["st"] = st
    social_refs = _add_event(slices, social, st, ctx)
    ctx_social_core = _fmt(social[2], ctx)

    # ---- 健康事件（因果联动）----
    if c_sign < 0 or s_sign < 0:
        hr0, hr1 = rng.randint(68, 86), rng.randint(115, 138)
        dur = rng.randint(6, 18)
        spike_t = st if s_sign < 0 else ct
        th, tm = map(int, spike_t.split(":"))
        tm2 = tm + 2
        spike_t2 = f"{th + (tm2 // 60):02d}:{tm2 % 60:02d}"
        slices.append(_sl(spike_t2, "sensor",
                          f"心率由{hr0}bpm骤升至{hr1}bpm，持续约{dur}分钟，血氧98%，判定情绪性心动过速"))
        ctx["hr0"], ctx["hr1"], ctx["dur"] = str(hr0), str(hr1), str(dur)
        health_core = _fmt("晚间{t}心率由{hr0}骤升至{hr1}bpm（情绪性心动过速），持续约{dur}分钟；晨脉{rhr}bpm，昨夜睡眠{sh}小时{sm}分", {**ctx, "t": spike_t2})
        health_refs = [f"sensor@{spike_t2}", f"sensor@{wake_t}"]
        health_truth = _truth("dim:health", health_core,
                              ["心率骤升", f"{hr1}bpm", "情绪性心动过速"],
                              ["心动过速", "心率飙升", "情绪性心率异常", "应激反应"],
                              ["全天心率平稳无波动", "体检全优", "运动达人状态"], health_refs)
    elif rng.random() < 0.55:
        km = rng.choice([2, 3, 3, 5, 5.5, 6])
        slices.append(_sl("19:48", "sensor", f"慢跑{km}公里配速6'10\"，心率区间有氧，全程无不适"))
        health_core = f"全天体征平稳：晨脉{rhr}bpm，傍晚慢跑{km}公里，昨夜睡眠{sh}小时{sm}分，状态在线"
        health_refs = ["sensor@19:48", f"sensor@{wake_t}"]
        health_truth = _truth("dim:health", health_core,
                              ["体征平稳", f"慢跑{km}公里", f"晨脉{rhr}bpm"],
                              ["健康平稳", "运动达标", "状态良好"], ["心率骤升", "猝倒", "高热"], health_refs)
    else:
        health_core = f"昨夜仅睡{sh}小时{sm}分，全天倦怠，午后靠咖啡续命，静息心率偏高({rhr}bpm)"
        health_refs = [f"sensor@{wake_t}"]
        health_truth = _truth("dim:health", health_core,
                              ["睡眠不足", f"{sh}小时{sm}分", "倦怠"],
                              ["睡眠不足", "疲劳度高", "休息不够"], ["精力充沛", "睡眠充足"], health_refs)

    # ---- 陷阱（15%）----
    trap = None
    if rng.random() < 0.15:
        trap = rng.choice(TRAPS)
        _add_event(slices, (trap[0], 0, "", [], [(0, trap[1], trap[2], trap[3])]), rng.choice(["12:52", "16:15", "20:41"]), ctx)

    # ---- 琐碎日常编织 ----
    def spread(pool, n, t_lo, t_hi):
        for k in range(n):
            src, wa, text = rng.choice(pool)
            t = f"{rng.randint(*t_lo):02d}:{rng.randint(*t_hi):02d}"
            label, sender = (wa.split("|")[0], wa.split("|", 1)[1]) if wa and "|" in wa else (wa, None)
            s = {"t": t, "src": src, "text": text}
            if src == "mic":
                s["who"] = label
            else:
                s["app"] = label
                if sender:
                    s["sender"] = sender
            slices.append(s)

    spread(TRIVIA_MORNING, rng.randint(1, 2), (7, 9), (30, 59))
    spread(TRIVIA_NOON, 1, (12, 12), (0, 55))
    spread(TRIVIA_AFTERNOON, rng.randint(1, 2), (14, 17), (0, 50))
    spread(TRIVIA_EVENING, 1, (18, 19), (0, 35))
    spread(TRIVIA_NIGHT, 1, (22, 23), (10, 25))

    # ---- 收尾体征 ----
    steps = rng.randint(3800, 15400)
    maxhr = max(int(ctx["hr1"]) if "hr1" in ctx and (c_sign < 0 or s_sign < 0) else 0, rng.randint(96, 118))
    slices.append(_sl(f"23:{rng.randint(10, 25):02d}", "sensor",
                      f"入睡准备：今日步数{steps:,}步，全天最高心率{maxhr}bpm，久坐{rng.randint(6, 10)}小时"))
    ctx["steps"] = f"{steps:,}"

    slices.sort(key=lambda x: x["t"])

    # ---- 六维方向性标答 ----
    em = EMOTION_MAP[(c_sign, s_sign)]
    day_part = {(-1): "白天工作受挫带来压力", 0: "白天工作平稳推进", 1: "白天事业好消息提振"}[c_sign]
    emotion_truth = _truth("dim:emotion",
                           f"情绪主基调「{em[0]}」：{day_part}，晚间{em[1]}",
                           em[2], em[3], em[4],
                           social_refs[:1])
    career_truth = _truth("dim:career", ctx_career_core, [_fmt(a, ctx) for a in career[2]],
                          [_fmt(a, ctx) for a in career[3]], [_fmt(a, ctx) for a in career[4]],
                          career_refs[:2])
    social_truth = _truth("dim:social", ctx_social_core, [_fmt(a, ctx) for a in social[3]],
                          [_fmt(a, ctx) for a in social[4]], [_fmt(a, ctx) for a in social[5]],
                          social_refs[:2])
    fin_truth = _truth("dim:finance", ctx_fin_core, [_fmt(a, ctx) for a in fin[3]],
                       [_fmt(a, ctx) for a in fin[4]], [_fmt(a, ctx) for a in fin[5]],
                       [f"app@{ft}"])
    fin_short = {1: "有资金进账", -1: "有刚性支出/资金压力", 0: "常规养车支出"}[f_sign]
    if c_sign < 0 and s_sign < 0:
        g_summary = f"双重受挫高压日：白天{ctx_career_core.split('，')[0]}，晚间{ctx_social_core.split('，')[0]}；{fin_short}；情绪由焦虑走向崩溃边缘"
        g_anchors = ["工作受挫", "人际冲突", "高压", "崩溃"]
        g_acc = ["工作人际双打击", "身心高压危机", "至暗一日", "祸不单行", "压力叠加"]
        g_red = ["顺风顺水", "双喜临门", "平静无奇"]
    elif c_sign > 0 and s_sign > 0:
        g_summary = f"双喜临门日：白天{ctx_career_core.split('，')[0]}，晚间{ctx_social_core.split('，')[0]}；{fin_short}；情绪振奋幸福"
        g_anchors = ["事业突破", "感情升温", "双喜临门"]
        g_acc = ["事业感情双丰收", "高光一日", "喜事成双"]
        g_red = ["双重打击", "至暗时刻", "祸不单行"]
    else:
        g_summary = f"转折起伏日：白天{ctx_career_core.split('，')[0]}，晚间{ctx_social_core.split('，')[0]}；{fin_short}；情绪「{em[0]}」转「{em[1]}」"
        g_anchors = [g_summary.split("：")[1].split("，")[0], "转折", "情绪起伏"]
        g_acc = ["喜忧参半", "有起有伏", "跌宕一日", "先抑后扬" if c_sign < 0 else "先扬后抑"]
        g_red = ["平淡无波", "毫无波澜"]
    global_truth = _truth("dim:global", g_summary, g_anchors, g_acc, g_red,
                          [career_refs[0], social_refs[0] if social_refs else career_refs[0]])

    truth = {
        "global_daily_summary": global_truth,
        "dim:health": health_truth,
        "dim:social": social_truth,
        "dim:emotion": emotion_truth,
        "dim:finance": fin_truth,
        "dim:career": career_truth,
    }

    if trap:
        tdim = {"social": "dim:social", "career": "dim:career", "finance": "dim:finance"}[trap[5]]
        truth[tdim]["redline_violations"] = list(dict.fromkeys(
            truth[tdim]["redline_violations"] + trap[6]))

    active = sum(1 for s in (c_sign, s_sign, f_sign) if s != 0) + (1 if (c_sign < 0 or s_sign < 0) else 0)
    difficulty = "ADVERSARIAL" if trap else ("HARD" if active >= 3 else "MEDIUM")
    archetype = f"career{'+' if c_sign > 0 else ('-' if c_sign < 0 else '0')}_social{'+' if s_sign > 0 else ('-' if s_sign < 0 else '0')}_fin{'+' if f_sign > 0 else ('-' if f_sign < 0 else '0')}"

    return {
        "question_id": f"Q_{GEN_ID}_{i + 1:05d}",
        "day_signature": f"{career[0]}|{social[0]}|{fin[0]}|{trap[0] if trap else '-'}",
        "generator_agent": GEN_ID,
        "exam_date": f"2026-{rng.choice(['07', '08', '09'])}-{rng.randint(1, 28):02d}",
        "difficulty": difficulty,
        "archetype": archetype,
        "trap": trap[4] if trap else None,
        "persona": {
            "name": name, "age": age, "city": city, "job": job,
            "relationship": relationship, "partner": partner,
            "band_id": f"aios-band-{rng.randint(1, 40):02d}-{rng.randint(100, 999):03d}",
        },
        "cleaned_daily_stream": slices,
        "directional_ground_truth": truth,
    }


def validate(people):
    errs = []
    ids, names, sigs = set(), set(), set()
    for p in people:
        if p["question_id"] in ids:
            errs.append("dup id " + p["question_id"])
        ids.add(p["question_id"])
        nm = p["persona"]["name"]
        if nm in names:
            errs.append("dup name " + nm)
        names.add(nm)
        ts = [s["t"] for s in p["cleaned_daily_stream"]]
        if ts != sorted(ts):
            errs.append("unsorted " + p["question_id"])
        if ts[0] < "07:00" or ts[-1] > "23:30":
            errs.append("time window " + p["question_id"])
        gt = p["directional_ground_truth"]
        if set(gt.keys()) != {"global_daily_summary", "dim:health", "dim:social",
                              "dim:emotion", "dim:finance", "dim:career"}:
            errs.append("dims " + p["question_id"])
        for d, t in gt.items():
            if not t["acceptable_directions"] or not t["redline_violations"] or not t["core_anchors"]:
                errs.append(f"empty truth {p['question_id']}:{d}")
        sigs.add(p["day_signature"])
    return errs, len(ids), len(names), len(sigs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260916)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    used_names: set = set()
    people = [generate_person(i, rng, used_names) for i in range(args.n)]

    errs, n_ids, n_names, n_sigs = validate(people)
    out_dir = ROOT / "benchmarks/daily_summary/questions"
    out_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / "benchmarks/daily_summary/ground_truth").mkdir(parents=True, exist_ok=True)
    (ROOT / "benchmarks/daily_summary/reports").mkdir(parents=True, exist_ok=True)
    out = out_dir / f"questions_{GEN_ID}.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for p in people:
            fh.write(json.dumps(p, ensure_ascii=False, separators=(",", ":")) + "\n")

    from collections import Counter
    diff = Counter(p["difficulty"] for p in people)
    arch = Counter(p["archetype"] for p in people)
    traps = sum(1 for p in people if p["trap"])
    manifest = {
        "generator_agent": GEN_ID,
        "generator_script": "scripts/generate_daily_summary_01a0aa2d.py",
        "seed": args.seed,
        "n_questions": len(people),
        "unique_ids": n_ids, "unique_names": n_names, "unique_day_signatures": n_sigs,
        "difficulty_dist": dict(diff),
        "archetype_top10": arch.most_common(10),
        "trap_questions": traps,
        "truth_dimensions": ["dim:global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"],
        "format": "单题四键：question_id / persona / cleaned_daily_stream(07:00~23:30时间轴切片) / directional_ground_truth(六维方向性标答: core_plot+core_anchors+acceptable_directions+redline_violations+key_evidence_refs)",
        "validation_errors": errs[:20],
        "validation_error_count": len(errs),
    }
    with open(ROOT / "benchmarks/daily_summary/manifest_01a0aa2d-fantonghui.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)

    print(f"generated {len(people)} persons -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    print(f"unique ids={n_ids} names={n_names} day_signatures={n_sigs} traps={traps} errors={len(errs)}")
    print("difficulty:", dict(diff))
    print("top archetypes:", arch.most_common(6))


if __name__ == "__main__":
    main()
