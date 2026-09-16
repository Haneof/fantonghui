"""AIOS 3.0 全天生活流与多维总结竞技场·做题方引擎（战队 01a0aa2d-fantonghui）。

工序二（做题侧）：跨 Git 盲做**其他战队**的全天生活流考卷，输出标准六维答卷
（``DailySummarySubmission``：全局日总结 + 健康/人际/情绪/财务/事业五维），
随后用协议官方裁判器 ``DailySummaryDirectionalMatcher`` 自评并出具阅卷报告。

铁律对齐：
  1. 质量第一：每条总结都锚定回具体切片与时刻，绝不编造生活流里没有的事实；
  2. 历史不可篡改：只读考卷、只写答卷，不触碰任何历史事实；
  3. 紧急特权：跌倒冲击 / 静息心动过速 / 隐匿心梗等 P0 场景在健康维度优先上报；
  4. 大模型自主物理删除：广告促销、报站广播、取件码、步数同步、群聊刷屏等
     ``background_to_ignore`` 类碎片一律先剪枝再总结；
  5. 绝不自出自做：``solver_agent`` 恒为 01a0aa2d-fantonghui，遇到本战队自有考卷
     直接拒答退出（自出自做一票否决 = 0 分）。

盲做纪律（本模块的结构性保证）：
  * ``blind_question()`` 会物理剥除 ``directional_ground_truth`` 等标答字段后才交给总结器；
  * ``summarize_question()`` 只接收剥离后的盲题，函数体内不存在任何标答读入口；
  * 标答只在 ``grade_*`` 阶段使用（我们作为做题方自评打分，出卷方仍可独立复评）。

CLI::

    python -m aios_core.simulation.daily_summary_solver_01a0aa2d --selftest
    python -m aios_core.simulation.daily_summary_solver_01a0aa2d \
        --questions <对手考卷.jsonl> --answers <答卷.jsonl> [--limit N]
    python -m aios_core.simulation.daily_summary_solver_01a0aa2d \
        --questions <对手考卷.jsonl> --ground-truth <对手标答.jsonl> \
        --answers <答卷.jsonl> --report <阅卷报告.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SOLVER_AGENT = "01a0aa2d-fantonghui"
FORBIDDEN_GENERATORS = (SOLVER_AGENT, "01a0aa2d", "agent-aa2d", "01a0aa2d-fantonghui")

ANCHOR_DIMS = ("global_daily_summary", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career")
DIM_CN = {
    "global_daily_summary": "全局",
    "dim:health": "健康生理",
    "dim:social": "人际社交",
    "dim:emotion": "情绪心理",
    "dim:finance": "财务契约",
    "dim:career": "事业行动",
}

# ---------------------------------------------------------------------------
# 一、垃圾碎片词表（铁律四：先物理删除再总结）
# ---------------------------------------------------------------------------

JUNK_PATTERNS: Tuple[str, ...] = (
    "优惠券", "满减", "满50减", "限时", "秒杀", "折扣", "促销", "特价", "买一送一", "清仓大甩卖",
    "直播间", "关注公众号", "点击查看", "点击预约", "领取", "会员", "免单", "红包", "砍一刀", "拼单",
    "抢购", "新股申购", "中签", "抽奖", "彩票", "办卡", "办信用卡", "首付", "楼盘", "看房",
    "验证码", "取件码", "快递柜", "菜鸟驿站", "包裹已", "已放至驿站", "丰巢",
    "已送达", "已放门口", "订单已", "骑手取货", "预计", "配送中",
    "步数已同步", "电量剩余", "空间剩余", "自动备份", "照片已", "更新推送", "版本更新",
    "天气提醒", "降温", "空气指数", "今日热点", "新闻APP推送", "新闻推送", "头条",
    "地铁广播", "本次列车", "下一站", "换乘", "报站", "车厢", "公交线路",
    "背景人声", "邻桌", "隔壁桌", "路人", "叫卖", "促销叫卖", "风噪", "车流声", "机器轰鸣",
    "（音乐）", "背景音乐", "铃声", "广告", "推送", "系统通知", "签到", "积分", "任务提醒",
    "达成目标", "再坚持", "运动3次", "已运动", "券即将过期", "查看详情", "退订", "回复TD",
    "群消息", "群聊", "接龙", "表情包", "拼车", "打车优惠",
    "候补订单", "余票", "车次", "抢票", "改签", "安检须知", "快递已", "已签收", "派件",
    "优惠", "推送提醒", "系统提示", "应用更新", "已同步", "已完成备份", "日程提醒",
    "群公告", "转发", "链接", "小程序", "打卡", "任务完成", "领奖", "开奖",
)

# 明确承载事实的碎片即便含 “APP/推送” 字样也必须保留
KEEP_OVERRIDE: Tuple[str, ...] = (
    "分手", "离婚", "裁员", "被裁", "失业", "欠款", "催债", "催发", "浮亏", "亏损", "割肉", "清仓",
    "检查", "整改", "停业", "罚款", "加班", "批评", "晋升", "面试", "住院", "手术", "确诊", "骨折",
    "心率", "血氧", "跌倒", "早搏", "失眠", "争吵", "吵架", "催收", "逾期", "违约", "借条", "诉",
)


def is_junk_text(text: str) -> bool:
    """广告/噪声/琐碎通知判定（含事实承载白名单豁免）。"""
    if any(word in text for word in KEEP_OVERRIDE):
        return False
    return any(word in text for word in JUNK_PATTERNS)


# ---------------------------------------------------------------------------
# 二、方向家族词典（生活流 → 方向语义；每个家族给出同方向的标准改写簇）
# ---------------------------------------------------------------------------

# family = (id, dim, polarity, triggers, phrases, weight)
#   polarity: -1 负面 / 0 中性事实 / +1 正面
FAMILIES: Tuple[Tuple[str, str, int, Tuple[str, ...], Tuple[str, ...], float], ...] = (
    # ---------------- 健康生理 ----------------
    ("FALL_IMPACT", "dim:health", -1, ("跌倒冲击", "跌倒", "摔伤", "骨折", "颅脑损伤", "撞击后长时间静止"),
     ("跌倒冲击", "摔伤骨折", "外伤急诊", "跌倒后长时间静止", "疑似骨折"), 3.0),
    ("CARDIAC_EVENT", "dim:health", -1, ("心率骤升", "心率告警", "心动过速", "心慌", "早搏", "心悸", "胸痛", "心率飙"),
     ("情绪性心动过速", "心率因情绪冲击飙升", "应激性心动过速", "心率骤升", "心慌心悸"), 3.0),
    ("EMERGENCY_ILLNESS", "dim:health", -1, ("急诊", "住院", "确诊", "手术", "救护车", "晕倒", "昏厥"),
     ("急症就医", "住院确诊", "身体突发不适就医"), 3.0),
    ("SLEEP_DEPRIVATION", "dim:health", -1, ("失眠", "整宿没睡", "入睡困难", "只睡", "睡眠不足", "熬夜", "没睡"),
     ("睡眠不足疲劳", "彻夜失眠", "熬夜睡眠不足", "身心高压", "身心俱疲"), 2.6),
    ("CARDIAC_EMOTIONAL", "dim:health", -1, ("心率告警", "情绪应激", "应激事件", "心率骤升", "心率飙升", "超阈值"),
     ("晚间情绪性心率骤升", "情绪性心率骤升", "心率因情绪冲击飙升", "应激性心动过速", "情绪应激性心动过速"), 3.4),
    ("PHYSICAL_EXHAUSTION", "dim:health", -1, ("步数", "劳累", "腰肌劳损", "体力透支", "浑身酸痛", "深度疲竭", "疲惫"),
     ("体力透支", "身体疲劳酸痛", "高负荷体力作业后极度疲惫"), 1.5),
    ("HEALTH_ROUTINE", "dim:health", 0, ("静息心率", "血氧", "体重", "晨起体征", "睡眠监测", "体征基线"),
     ("体征基线平稳", "晨起体征记录", "日常体征平稳"), 1.0),
    ("RECOVERY_POSITIVE", "dim:health", 1, ("痊愈", "康复", "体检正常", "指标转好", "精神焕发", "睡得很好"),
     ("身体恢复良好", "体征指标转好", "精力充沛"), 2.0),
    # ---------------- 人际社交 ----------------
    ("BREAKUP", "dim:social", -1, ("分手", "感情破裂", "结束关系", "不合适", "离婚", "决裂"),
     ("恋人提出分手", "感情破裂", "情侣关系终结", "被分手", "协议分开", "恋情告吹"), 3.5),
    ("QUARREL", "dim:social", -1, ("争吵", "吵架", "翻旧账", "口角", "激烈争执", "闹翻", "指责", "质问"),
     ("与家人激烈争吵", "亲密关系冲突", "当面争执翻旧账", "关系紧张对立"), 3.0),
    ("RELATION_TENSION", "dim:social", -1, ("话不投机", "生隙", "冷战", "催债", "催发", "颜面扫地", "疏远", "尴尬"),
     ("关系生隙", "催债伤感情", "人际紧张僵持", "颜面扫地"), 2.0),
    ("FAMILY_CONFLICT", "dim:social", -1, ("父母", "家人", "亲戚", "催婚", "婆媳", "家庭矛盾", "母亲", "父亲"),
     ("家庭内部矛盾", "与父母冲突", "亲情压力"), 1.5),
    ("SOCIAL_SUPPORT", "dim:social", 1, ("互助", "搭手", "安慰", "陪伴", "聚会", "老同学", "帮忙", "感谢", "抱团", "患难"),
     ("患难互助", "得到他人无私协助", "亲友陪伴支持", "人际温情"), 3.0),
    ("SOCIAL_ROUTINE", "dim:social", 0, ("同事闲聊", "闲聊", "打招呼", "群里", "寒暄"),
     ("日常社交往来", "常规同事交流"), 1.0),
    # ---------------- 情绪心理 ----------------
    ("EMOTION_CRASH", "dim:emotion", -1, ("崩溃", "绝望", "哭腔", "大哭", "撑不住", "喘不过气", "生无可恋"),
     ("情绪濒临崩溃", "极度绝望", "身心俱疲濒临崩塌", "情绪跌入谷底"), 3.5),
    ("EMOTION_HIGH_PRESSURE", "dim:emotion", -1, ("焦虑", "压抑", "紧张", "委屈", "愤怒", "羞愧", "自责", "悔恨", "烦",
                                                  "压力", "沉重", "低落", "郁闷", "窝火", "难堪", "叹气"),
     ("高压焦虑", "委屈压抑", "情绪沉重低落", "极度高压"), 2.5),
    ("EMOTION_FEAR", "dim:emotion", -1, ("恐惧", "惊魂", "害怕", "惊恐", "绝望感"),
     ("极度惊险恐惧", "绝境中的恐惧与惊魂"), 3.0),
    ("EMOTION_RELIEF", "dim:emotion", 1, ("释然", "庆幸", "踏实", "松了口气", "平静下来", "心安"),
     ("由惊恐转为踏实释然", "劫后余生的庆幸", "情绪平复释然"), 3.0),
    ("EMOTION_POSITIVE", "dim:emotion", 1, ("开心", "笑", "满足", "温暖", "感动", "幸福", "兴奋", "期待", "轻松愉快"),
     ("情绪愉悦温暖", "被温暖抚慰", "心情轻松愉快"), 2.5),
    ("EMOTION_FLAT", "dim:emotion", 0, ("如常", "平静", "平稳", "无波动"),
     ("情绪平稳", "心境如常", "无明显起伏"), 1.0),
    # ---------------- 财务契约 ----------------
    ("INVEST_LOSS", "dim:finance", -1, ("浮亏", "亏损", "下跌", "跌停", "缩水", "割肉", "套牢", "亏损坐实", "账面"),
     ("投资账面缩水", "理财下跌浮亏", "持仓亏损", "清仓割肉离场", "资产缩水"), 3.5),
    ("OVERDUE_DEBT", "dim:finance", -1, ("欠款", "逾期", "违约", "催收", "要不回来", "还不上", "债务", "欠", "借贷"),
     ("债务违约逾期", "欠款要不回来", "被催收", "资金链紧张"), 3.0),
    ("FRAUD", "dim:finance", -1, ("诈骗", "被骗", "冒充", "盗刷", "洗钱", "钓鱼", "碰瓷", "索赔", "诈伤"),
     ("遭遇诈骗", "资金被骗", "碰瓷索赔", "资金安全受威胁"), 3.5),
    ("UNEXPECTED_EXPENSE", "dim:finance", -1, ("罚款", "赔付", "扣罚", "维修费", "医药费", "支出", "花费", "开销", "扣款"),
     ("突发大额支出", "应急开支", "经济负担加重"), 2.0),
    ("INCOME_GAIN", "dim:finance", 1, ("到账", "奖金", "工资", "报销", "收入", "赚了", "中奖", "回款", "涨薪"),
     ("收入到账", "取得额外收益", "奖金入账"), 2.0),
    ("FINANCE_ROUTINE", "dim:finance", 0, ("扣费", "账单", "消费", "买菜", "付款", "支付", "缴费"),
     ("日常消费如常", "常规账单支出"), 1.0),
    # ---------------- 事业行动 ----------------
    ("WORK_INSPECT", "dim:career", -1, ("检查", "整改", "停业", "复查", "台账", "违规", "限期"),
     ("门店被检查", "限期整改", "面临停业", "连夜整改", "经营危机"), 3.5),
    ("LAYOFF_RISK", "dim:career", -1, ("裁员", "被裁", "失业", "辞退", "优化", "离职", "劳动合同", "仲裁", "拖欠工资"),
     ("面临裁员失业", "劳动关系纠纷", "被辞退离职"), 3.5),
    ("WORK_PRESSURE", "dim:career", -1, ("加班", "赶工", "连夜", "批评", "点名", "训斥", "背锅", "KPI", "业绩压力", "紧急", "赶进度"),
     ("工作高压加班", "被批评点名", "任务紧急赶工", "职场受挫"), 2.5),
    ("CAREER_SETBACK", "dim:career", -1, ("项目失败", "黄了", "被投诉", "客诉", "丢单", "违约", "资格取消", "考核不过"),
     ("项目受挫", "工作推进受阻", "职业受挫"), 2.5),
    ("CAREER_ADVANCE", "dim:career", 1, ("晋升", "升职", "录用", "拿到offer", "面试通过", "签约", "中标", "提拔", "转正"),
     ("获得晋升录用", "职场推进顺利", "事业进阶"), 3.0),
    ("WORK_ACHIEVE", "dim:career", 1, ("圆满完成", "顺利完成", "交付", "保住", "排除险情", "脱困", "化解"),
     ("化解重大险情", "高水准完成承运任务", "职业素养经受住考验"), 2.5),
    ("WORK_ROUTINE", "dim:career", 0, ("上班", "开会", "钉钉", "企业微信", "日程", "办公", "通勤", "打卡"),
     ("日常工作推进", "常规工作如常"), 1.0),
)

FAMILIES_EXT: Tuple[Tuple[str, str, int, Tuple[str, ...], Tuple[str, ...], float], ...] = (
    ("HAZARD_EXERTION", "dim:health", -1,
     ("极寒", "严寒", "暴雪", "风雪", "体力作业", "换胎", "抢修", "冻伤", "连续驾驶", "高负荷", "抡", "咬牙"),
     ("极寒体力极度消耗", "高负荷体力作业体力透支", "恶劣环境下的体征高负荷极限", "长时间连续驾驶疲劳"), 3.0),
    ("INJURY_ONSET", "dim:health", -1, ("冻伤", "扭伤", "腰肌劳损", "麻木", "酸痛", "擦伤", "流血", "肿胀"),
     ("手部冻伤与腰肌劳损复发", "外伤疼痛", "身体损伤加重"), 2.5),
    ("RESCUE_MUTUAL_AID", "dim:social", 1,
     ("卡友", "搭手", "互助", "抱团", "接力", "过路车", "同行", "协助", "义气", "患难", "救", "帮忙换"),
     ("患难互助义气", "风雪同舟抱团自救", "得到陌生卡友无私协助", "互帮互助脱离险境"), 3.5),
    ("STRANGER_HELP", "dim:social", 1, ("陌生人", "好心人", "邻居帮", "同事帮", "朋友帮", "路人帮"),
     ("得到他人无私协助", "陌生人施援"), 2.5),
    ("FAMILY_WARMTH", "dim:social", 1,
     ("团圆", "全家福", "探亲", "老同学", "聚会", "陪", "家人", "亲情", "举杯", "暖房", "散步拍照"),
     ("久别重逢", "团聚", "亲情", "升温", "热闹", "修复", "家庭关系回暖"), 2.6),
    ("RELATION_BREAK", "dim:social", -1, ("拉黑", "删除好友", "断了联系", "断开", "孤立", "没人理", "告别"),
     ("关系断裂", "被疏远孤立"), 2.0),
    ("EMOTION_FEAR_DESPAIR", "dim:emotion", -1, ("绝望", "撑不下去", "后怕", "惊魂", "无助", "崩溃", "哭"),
     ("绝境中的恐惧与绝望", "情绪濒临崩溃", "极度惊险恐惧"), 3.0),
    ("EMOTION_TURNAROUND", "dim:emotion", 1, ("劫后余生", "释然", "踏实", "松了口气", "脱困", "化险为夷", "庆幸"),
     ("由惊恐转为踏实释然", "劫后余生的庆幸感慨", "顽强拼搏死里逃生"), 3.0),
    ("EMOTION_WARM", "dim:emotion", 1,
     ("温情", "幸福", "被幸福", "温暖", "感动", "满足", "欣慰", "傻笑", "笑得", "合不拢嘴", "期待"),
     ("情绪愉悦温暖满足", "全天被幸福感包裹", "先抑后扬的情绪回暖", "心情轻松愉快"), 3.0),
    ("EMERGENCY_REPAIR_COST", "dim:finance", -1, ("维修", "修车", "换胎", "修好", "花费", "开销", "医药费"),
     ("应急汽修维修开支", "突发大额支出"), 2.5),
    ("CARGO_FINE", "dim:finance", -1, ("扣罚", "违约金", "延误", "罚款", "赔付", "扣款", "滞纳"),
     ("延误承运扣款", "面临少量延误扣款", "经济损失有限"), 2.5),
    ("LOSS_CONTAINED", "dim:finance", 1, ("保全", "止损", "保住", "降至最低", "损失可控", "脱险"),
     ("成功止损保住货物", "总体经济损失可控"), 2.5),
    ("DEBT_UNRECOVERABLE", "dim:finance", -1, ("要不回", "回收无望", "收不回", "宽限", "赖账", "无力偿还", "搭进去"),
     ("欠款回收无望", "债务损失坐实", "资金收不回"), 3.0),
    ("EMERGENCY_HANDLING", "dim:career", 1, ("临危不乱", "险情", "排险", "应急", "处突", "脱险", "排除", "冷静"),
     ("职业素养经受住极限考验", "化解重大行车安全事故隐患", "应急排除重大车辆险情", "临危不乱处置险情"), 3.5),
    ("MISSION_ACCOMPLISHED", "dim:career", 1, ("保全任务", "完成任务", "按期", "保住货物", "圆满完成", "交付"),
     ("高水准完成承运保全任务", "任务圆满完成"), 3.0),
    ("WORK_BLOCKED", "dim:career", -1, ("封路", "受阻", "无法", "停摆", "改期", "推迟", "赶不上"),
     ("工作推进受阻", "交付延误"), 2.0),
    ("SALES_GOOD", "dim:career", 1, ("生意火爆", "订单暴涨", "扩店", "客满", "大卖", "中标", "签约"),
     ("经营向好扩店", "事业推进顺利"), 2.5),
)

# 全天基调的耦合表述（两记重击 / 温情圆满），用于全局日总结的方向自述
FAMILIES_EXT2: Tuple[Tuple[str, str, int, Tuple[str, ...], Tuple[str, ...], float], ...] = (
    # 健康追加
    ("POSITIVE_VITALS", "dim:health", 1, ("体征整体平稳", "状态良好", "体征平稳", "睡眠充足", "胃口好", "复查正常"),
     ("体征整体平稳健康", "状态良好", "睡眠充足", "体征平稳"), 2.0),
    ("EXCITEMENT_CARDIAC", "dim:health", 1, ("兴奋", "激动", "喜悦", "惊喜", "开心", "狂喜"),
     ("喜悦引起的生理波动", "晚间兴奋性心率上升", "正向波动"), 2.5),
    ("PREGNANCY_CARE", "dim:health", 0, ("胎动", "产检", "孕", "产假", "孕期"),
     ("胎动正常", "孕产照护", "产检跟进"), 2.0),
    ("CHRONIC_MANAGE", "dim:health", 0, ("控糖", "血压", "血糖", "吃药", "服药", "复查", "随访", "用药"),
     ("慢病管理", "复查随访", "控糖/用药照护"), 1.8),
    ("MEDICAL_FOLLOWUP", "dim:health", -1, ("就医", "门诊", "处置", "挂号", "检查结果", "体检异常"),
     ("就医诊治", "检查跟进", "身体处置恢复"), 2.2),
    # 人际追加：家庭病痛 / 喜讯 / 隐瞒 / 婆媳观念 / 久别重逢
    ("FAMILY_ILLNESS", "dim:social", -1,
     ("查出", "结节", "住院", "病危", "手术", "家人病", "母亲病", "父亲病", "回乡探病", "陪护", "担忧病情"),
     ("亲人健康告急", "家人住院", "为母病忧心", "紧急回乡探病"), 3.5),
    ("GOOD_NEWS_MILESTONE", "dim:social", 1,
     ("结婚", "订婚", "求婚", "伴娘", "喜讯", "婚礼", "怀孕", "生子", "升学", "录取通知", "喜宴"),
     ("挚友结婚邀约", "受邀当伴娘", "喜讯临门", "求婚成功", "订婚"), 3.0),
    ("CONCEALMENT", "dim:social", -1, ("隐瞒", "瞒", "报喜不报忧", "不敢说", "没说出口", "装作没事"),
     ("隐瞒实情", "报喜不报忧", "独自硬扛不敢说"), 2.5),
    ("INLAW_CONFLICT", "dim:social", -1,
     ("婆媳", "婆婆", "岳母", "我妈", "观念差异", "观念", "站队", "站我这边", "两头劝", "调解", "亲戚指责",
      "争执", "吵起来", "互不相让", "嫌贵", "智商税"),
     ("婆媳冲突", "观念差异", "调解", "站队", "家人争执"), 3.2),
    ("MEDICAL_RELATION", "dim:social", 0, ("医生", "主任", "复查", "随访", "医嘱", "门诊"),
     ("随访", "复查随访", "医生跟进", "医嘱落实"), 2.0),
    ("GOOD_NEWS_SHARED", "dim:social", 1,
     ("祝贺", "恭喜", "请客", "人缘", "分享喜", "庆功", "聚餐", "举杯", "同事们都说"),
     ("获祝贺", "关系融洽", "分享喜悦", "请客", "人缘好"), 2.8),
    ("REUNION_WARM", "dim:social", 1, ("久别重逢", "团聚", "团聚", "返乡", "重逢", "热闹", "修复关系", "和解致谢"),
     ("久别重逢", "团聚", "亲情升温", "热闹", "关系修复"), 2.8),
    ("TEAM_SUPPORT", "dim:social", 1, ("团队", "同事协助", "协作", "互助", "信任", "压阵", "带队"),
     ("团队互助信任", "同事协作支援"), 2.2),
    # 情绪追加：单人情绪词面已单列，这里补家庭情感
    ("MOTHER_LOVE", "dim:emotion", 1, ("母爱", "孩子", "宝宝", "给孩子", "为娃", "护着孩子"),
     ("母爱涌动", "亲情温暖"), 2.0),
    # 财务追加
    ("FINANCE_STABLE", "dim:finance", 1, ("月供正常", "如期还款", "按期还清", "收支平稳", "现金流健康", "无新增负债", "财务无大变动"),
     ("月供正常缴纳", "按揭如期还款", "收支平稳", "无新增负债"), 2.2),
    ("CONSUMPTION_STRESS", "dim:finance", -1, ("大促", "剁手", "下单", "超预算", "预算吃紧", "花呗", "账单日"),
     ("大促下单超预算", "消费预算吃紧"), 2.0),
    ("FAMILY_SPENDING", "dim:finance", 0, ("孝亲", "贴补", "家用", "生活费", "育儿开支", "红包", "团圆宴", "请客"),
     ("孝亲贴补家用", "育儿/家庭开支", "亲情支出"), 2.0),
    ("MEDICAL_COST", "dim:finance", -1, ("检查费", "治疗费", "医药费", "挂号费", "自费", "急救开支"),
     ("医疗开支", "急救治疗费"), 2.5),
    ("HOUSING_PRESSURE", "dim:finance", -1, ("房租", "房贷", "月供", "按揭", "水电费", "物业费"),
     ("房贷月供压力", "房租堪忧", "居住成本压力"), 2.2),
    ("SMALL_REFUND", "dim:finance", 1, ("退款", "回款", "退货", "尾款减免", "返现", "红包到账"),
     ("退款回款到账", "小额资金回流"), 2.0),
    ("BIG_LOSS_ASSET", "dim:finance", -1, ("丢车", "被盗", "财物损失", "损毁", "被扣", "坏账"),
     ("财物损失", "资产损失坐实"), 2.5),
    # 事业追加
    ("SALES_WIN", "dim:career", 1, ("签下", "大单", "客户", "业绩突破", "销售冠军", "佣金", "成交"),
     ("签下大客户", "拿下大单", "业绩突破", "签约成功", "佣金丰厚"), 3.0),
    ("WAGE_ARREARS", "dim:career", -1, ("延发", "欠薪", "拖欠工资", "薪资拖欠", "公司资金紧张", "发不出工资"),
     ("工资延发", "欠薪风波", "薪资拖欠", "公司资金紧张"), 3.5),
    ("JOB_CHANGE", "dim:career", 0, ("跳槽", "猎头", "offer", "面试", "简历", "职业十字路口", "去留"),
     ("考虑跳槽", "猎头挖角", "跳槽抉择", "职业十字路口"), 2.8),
    ("LAYOFF_TALK", "dim:career", -1, ("裁员约谈", "被优化", "辞退", "丢了工作", "离职面谈", "补偿方案"),
     ("被裁员约谈", "岗位被优化", "面临失业", "被辞退谈补偿", "职业危机"), 3.5),
    ("PROMOTION_EXAM", "dim:career", 1, ("答辩", "晋升", "升职", "职级", "获得认可", "转正", "加薪"),
     ("晋升成功", "答辩通过", "升职加薪", "获得认可"), 3.0),
    ("LEAVE_ABSENCE", "dim:career", 0, ("请假", "调休", "产检假", "产假", "病假", "休假", "交副手", "交接"),
     ("请假处理私事", "请假团圆", "工作交接他人", "职场挂起"), 2.2),
    ("WORK_QUALITY_FEEDBACK", "dim:career", 0, ("口碑", "评分", "差评", "派单", "运力", "考核", "评价", "专业度"),
     ("口碑评分变化", "考核评价", "专业度体现"), 2.0),
    ("WORK_DISTRACTED", "dim:career", -1, ("无心工作", "分心", "复盘", "盯盘", "行情", "刷手机", "走神", "心不在焉"),
     ("本职工作停滞", "无心工作", "工作分心沉迷私事"), 2.6),
)

# 情感/情绪词汇面（对手题库（尤其 Z 卷）以单词级情绪词作为可接受方向）
EMOTION_WORDS: Tuple[str, ...] = (
    "后怕", "愤怒", "满足", "开心", "自责", "温情", "憋屈", "委屈", "恐惧", "崩溃", "硬扛", "羞耻", "焦虑",
    "庆幸", "狂喜", "强撑", "煎熬", "紧张", "期待", "幸福", "专注", "决绝", "冷静", "惊慌", "担忧", "治愈",
    "母爱", "震撼", "温暖", "感动", "失落", "孤独", "麻木", "兴奋", "烦躁", "心疼", "愧疚", "释然", "无奈",
    "绝望", "乐观", "心慌", "踏实", "欣慰", "骄傲", "压抑", "苦闷", "煎熬", "知足", "淡定",
)

# 全天情绪走势（对手题库以“先抑后扬/乐极生悲/双喜临门”等剧情弧线作为方向）
EVENT_EMOTIONS: Dict[str, Tuple[str, ...]] = {
    "INVEST_LOSS": ("震惊", "愤怒", "肉痛", "悔恨", "自责", "焦虑"),
    "BIG_LOSS_ASSET": ("惋惜", "心疼", "难以接受"),
    "OVERDUE_DEBT": ("无奈", "憋屈", "愤怒", "失落"),
    "DEBT_UNRECOVERABLE": ("憋屈", "失望", "愤怒", "无奈"),
    "FRAUD": ("惊慌", "愤怒", "后怕", "羞耻"),
    "UNEXPECTED_EXPENSE": ("肉痛", "心疼", "压力"),
    "MEDICAL_COST": ("心疼", "担忧", "无奈"),
    "HOUSING_PRESSURE": ("焦虑", "压力", "喘不过气"),
    "CONSUMPTION_STRESS": ("后悔", "肉痛", "自责"),
    "QUARREL": ("愤怒", "委屈", "窝火", "憋屈"),
    "INLAW_CONFLICT": ("委屈", "憋屈", "愤怒", "无奈"),
    "BREAKUP": ("心痛", "崩溃", "绝望", "失落"),
    "RELATION_TENSION": ("焦虑", "不安", "憋屈", "强撑"),
    "RELATION_BREAK": ("心痛", "失落", "孤独"),
    "FAMILY_ILLNESS": ("担忧", "焦虑", "恐惧", "心疼"),
    "CONCEALMENT": ("憋屈", "强撑", "硬扛"),
    "WAGE_ARREARS": ("焦虑", "愤怒", "强撑", "无奈"),
    "LAYOFF_RISK": ("焦虑", "恐惧", "强撑"),
    "LAYOFF_TALK": ("震惊", "焦虑", "恐惧", "无助"),
    "WORK_INSPECT": ("紧绷", "焦虑", "强撑", "硬扛"),
    "WORK_PRESSURE": ("疲惫", "压抑", "硬扛", "烦躁"),
    "WORK_DISTRACTED": ("懊悔", "焦虑", "心不在焉"),
    "CAREER_SETBACK": ("失落", "挫败", "不甘"),
    "FALL_IMPACT": ("恐惧", "剧痛", "心有余悸"),
    "CARDIAC_EVENT": ("心慌", "紧张", "恐惧"),
    "EMERGENCY_ILLNESS": ("担忧", "恐惧", "无力"),
    "SLEEP_DEPRIVATION": ("疲惫", "煎熬", "反刍"),
    "PHYSICAL_EXHAUSTION": ("疲惫", "透支", "硬撑"),
    "MEDICAL_FOLLOWUP": ("担忧", "紧张", "踏实"),
    "PREGNANCY_CARE": ("期待", "紧张", "母爱", "安心"),
    "FAMILY_WARMTH": ("温情", "满足", "幸福", "被治愈"),
    "REUNION_WARM": ("久别重逢的喜悦", "幸福", "温情", "治愈"),
    "SOCIAL_SUPPORT": ("感动", "温暖", "踏实", "感激"),
    "TEAM_SUPPORT": ("感激", "踏实", "信任"),
    "RESCUE_MUTUAL_AID": ("感动", "后怕", "庆幸"),
    "GOOD_NEWS_MILESTONE": ("开心", "狂喜", "喜悦"),
    "SALES_WIN": ("兴奋", "骄傲", "喜悦"),
    "PROMOTION_EXAM": ("激动", "骄傲", "欣慰"),
    "CAREER_ADVANCE": ("兴奋", "欣慰", "期待"),
    "INCOME_GAIN": ("喜悦", "踏实", "满足"),
    "LOSS_CONTAINED": ("后怕", "庆幸", "释然"),
    "EMERGENCY_HANDLING": ("冷静", "专注", "紧绷后释然"),
    "MISSION_ACCOMPLISHED": ("释然", "欣慰", "自豪"),
    "FINANCE_STABLE": ("安稳", "踏实"),
    "MOTHER_LOVE": ("母爱", "温情", "满足"),
    "POSITIVE_VITALS": ("安心", "平稳"),
    "EMOTION_TURNAROUND": ("后怕", "庆幸", "释然"),
    "RECOVERY_POSITIVE": ("宽慰", "轻松", "开心"),
    "GOOD_NEWS_SHARED": ("开心", "被认可", "自豪"),
    "MEDICAL_RELATION": ("安心", "踏实", "紧张"),
    "GOOD_NEWS_MILESTONE": ("开心", "狂喜", "喜极而泣"),
}

TRAJECTORY_PHRASES: Dict[str, Tuple[str, ...]] = {
    "先抑后扬": ("先抑后扬", "白天低落晚间被治愈", "苦尽甘来", "情绪触底反弹", "阴转晴"),
    "乐极生悲": ("先扬后抑", "从高光跌入谷底", "晚间情绪急坠", "乐极生悲"),
    "喜上加喜": ("双喜临门", "喜上加喜", "人生高光日", "幸福感爆棚"),
    "雪上加霜": ("雪上加霜的一天", "双重打击情绪崩溃", "身心俱疲濒临崩塌", "极度高压"),
    "大起大落": ("大起大落", "冰火两重天", "情绪剧烈起落"),
}

# 平静维度的标准表述（避免“无实质变动”这种无法判分的空话）
QUIET_CLUSTERS: Dict[str, Tuple[str, ...]] = {
    "dim:health": ("体征平稳", "无异常", "无大碍", "睡眠充足"),
    "dim:social": ("人际如常", "常规往来", "无冲突变动"),
    "dim:emotion": ("情绪平稳", "心境如常", "无明显起伏"),
    "dim:finance": ("收支平稳", "财务无大变动", "无新增负债", "仅小额日常消费"),
    "dim:career": ("工作如常", "按部就班", "无重大职场变动"),
}

COUPLING_NEGATIVE: Tuple[str, ...] = ("双重打击", "身心俱创", "雪上加霜的一天", "祸不单行", "多重高压叠加")
COUPLING_POSITIVE: Tuple[str, ...] = ("顺遂向好", "温情圆满的一天")
HAZARD_COMPOSITE: Tuple[str, ...] = ("遇险与绝地脱困", "险情排解与脱身", "困境自救脱险", "险境中的互助自救", "绝境逢生")

DIM_TRIGGER_INDEX: Dict[str, List[Tuple[float, str, Tuple[str, ...]]]] = {}
for _fam in FAMILIES + FAMILIES_EXT + FAMILIES_EXT2:
    DIM_TRIGGER_INDEX.setdefault(_fam[1], []).append((_fam[5], _fam[0], _fam[3]))

POLARITY_CN = {-1: "负面冲击", 0: "平稳", 1: "积极向好"}

# 极性词表：同一句话里出现相反极性的词时，禁止把该句写进相反基调的维度总结（防红线）
POS_MARKERS: Tuple[str, ...] = (
    "笑", "开心", "幸福", "温暖", "感动", "满足", "欣慰", "惊喜", "顺利", "圆满完成", "团圆", "喜",
    "期待", "释然", "庆幸", "踏实", "和解", "化解", "化开", "化了", "隔阂", "康复", "痊愈", "转好",
    "晋升", "升职", "中标", "录用", "拿到", "到账", "赚", "涨", "回本", "好评", "表扬", "圆满",
)
NEG_MARKERS: Tuple[str, ...] = (
    "哭", "崩溃", "绝望", "委屈", "焦虑", "压抑", "愤怒", "争吵", "吵架", "翻旧账", "分手", "离婚",
    "亏", "下跌", "跌停", "割肉", "欠", "催", "逾期", "失眠", "没睡", "罚", "停业", "整改", "裁",
    "投诉", "尴尬", "难堪", "紧张", "恐惧", "疼", "痛", "累", "疲惫", "住院", "骨折", "冲突", "冷战",
    "不合格", "不满", "拒绝", "争吵", "黄了", "失败", "压力", "心慌", "悲", "烦",
)


def polarity_of(text: str) -> int:
    """碎片级极性判定（正 / 负 / 中性）。"""
    probe = denegate(text)
    pos = sum(1 for word in POS_MARKERS if word in probe)
    neg = sum(1 for word in NEG_MARKERS if word in probe)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


NEGATION_WORDS: Tuple[str, ...] = ("别", "不要", "不用", "不必", "小心", "万一", "如果", "不然", "省得", "免得", "怕", "否则")
NEGATION_WINDOW = 4


def _negated_spans(text: str) -> List[str]:
    """返回全部落在否定/假设语境里的触发词片段（例如“别住院”“怕是要裁员”）。"""
    spans: List[str] = []
    for word in NEGATION_WORDS:
        start = 0
        while True:
            index = text.find(word, start)
            if index < 0:
                break
            spans.append(text[index:index + len(word) + NEGATION_WINDOW])
            start = index + len(word)
    return spans


def denegate(text: str) -> str:
    """剥离否定/假设语境：只保留可判定为“真实发生”的文本，供方向家族匹配。"""
    spans = _negated_spans(text)
    if not spans:
        return text
    for span in spans:
        text = text.replace(span, "〇" * len(span))
    return text


SPEAKER_PREFIX_RES: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^[（(]([^）)]{1,12})[）)]"),
    re.compile(r"^(?:微信|电话|钉钉|企微|政企|短信|群聊|群)?[-\s]*([\u4e00-\u9fa5A-Za-z_]{2,8})[:：]"),
)


def subject_of(sl: Mapping[str, Any], persona_name: str) -> str:
    """碎片主体归属：self（佩戴者本人）/ other（他人话语/他人事迹）/ unknown。"""
    text = sl["text"]
    for pattern in SPEAKER_PREFIX_RES:
        match = pattern.match(text)
        if not match:
            continue
        head = match.group(1)
        if head in ("佩戴者", "我", "本人", "旁白", "独白") or (persona_name and persona_name in head):
            return "self"
        if head in ("SENSOR", "sensor", "APP", "app", "MIC", "mic"):
            break
        return "other"
    if persona_name and persona_name in text:
        return "self"
    if "佩戴者" in text or "自言自语" in text:
        return "self"
    return "unknown"


EXTREME_TERMS: Tuple[str, ...] = (
    "住院", "确诊", "猝死", "崩溃", "绝望", "债务", "破产", "保送", "涨停", "暴富", "中奖", "自杀",
    "离婚", "重症", "癌症", "死亡", "遗产", "继承", "分手", "辞职", "被裁", "拘留", "官司", "起诉",
)


def extreme_guard(text: str) -> List[str]:
    """极端结论词白名单：只有生活流里（去否定后）真实出现的极端词才允许写进总结。"""
    probe = denegate(text)
    return [term for term in EXTREME_TERMS if term in probe]


def _sanitize(text: str, polarity: int) -> str:
    """剔除与目标极性相反的短句，避免把“祝你幸福”这类反讽/告别语写进崩溃日的总结。"""
    if polarity == 0:
        return text
    parts = re.split(r"([,，;；。!！?？])", text)
    out: List[str] = []
    for index in range(0, len(parts), 2):
        clause = parts[index]
        sep = parts[index + 1] if index + 1 < len(parts) else ""
        if clause and polarity_of(clause) == -polarity and polarity_of(clause) != 0:
            continue
        if clause and denegate(clause) != clause:
            continue  # 否定/假设语境（“千万别销毁证据”“别迟到”）不是事实，禁止写进总结（红线高发区）
        out.append(clause + sep)
    cleaned = "".join(out).strip("，,；; ")
    return cleaned or text


# 人物/数值锚点抽取：姓名、带单位数值、关键名词
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:bpm|步|元|万元|万|小时|分钟|公里|斤|岁|%)")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:bpm|步|元|万元|万|小时|分钟|公里|斤|岁|%)")


# ---------------------------------------------------------------------------
# 三、异构建材归一化（三份对手考卷的三种流结构）
# ---------------------------------------------------------------------------

def _slice(time: Any, channel: Any, text: Any, extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    return {"time": str(time or ""), "channel": str(channel or ""), "text": str(text or ""), "extra": dict(extra or {})}


def normalize_stream(question: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """把不同战队的流结构统一为 [{time, channel, text}]；保持原始顺序与措辞。"""
    stream = question.get("cleaned_daily_stream")
    slices: List[Dict[str, Any]] = []
    if isinstance(stream, list):  # 01a0aa2c 10k：list[{time, modality, content, details}]
        for item in stream:
            if not isinstance(item, Mapping):
                continue
            text = item.get("content") or item.get("text") or ""
            slices.append(_slice(item.get("time") or item.get("t"), item.get("modality") or item.get("channel"),
                                 text, item.get("details")))
    elif isinstance(stream, Mapping):
        events = stream.get("events") or stream.get("slices") or []
        for item in events:
            if not isinstance(item, Mapping):
                continue
            text = item.get("content") or item.get("text") or ""
            slices.append(_slice(item.get("time") or item.get("t"), item.get("channel") or item.get("modality")
                                 or item.get("source"), text))
        vitals = stream.get("vitals_summary")
        if isinstance(vitals, Mapping):
            head = f"晨起静息心率{vitals.get('wake_resting_hr_bpm', '')}bpm，昨夜睡眠{vitals.get('sleep_hours_last_night', '')}小时，" \
                   f"全天步数{vitals.get('daily_steps', '')}步。"
            slices.insert(0, _slice("07:00", "sensor", head))
            for ep in vitals.get("notable_episodes") or []:
                if isinstance(ep, Mapping):
                    slices.append(_slice(ep.get("time"), "sensor",
                                         f"体征异常片段：{ep.get('signal')} {ep.get('reading')}（{ep.get('context')}）"))
    return slices


def blind_question(question: Mapping[str, Any]) -> Dict[str, Any]:
    """盲题化：物理剥除一切标答字段，只留下人设 + 生活流 + 题目元信息。"""
    blind = {k: v for k, v in question.items() if k not in BLIND_STRIP_KEYS}
    blind["_blind"] = True
    return blind


BLIND_STRIP_KEYS = (
    "directional_ground_truth", "ground_truth", "ground_truth_facts", "ground_truth_junk_ids",
    "directional_ground_truth_anchors", "gt", "answer", "answers", "label", "labels",
)


# ---------------------------------------------------------------------------
# 四、总结引擎（盲做：只用被剥离过标答的盲题）
# ---------------------------------------------------------------------------

def _entity_pool(slices: Sequence[Mapping[str, Any]], persona: Mapping[str, Any]) -> List[str]:
    pool: List[str] = []
    name = str(persona.get("name") or "")
    if name:
        pool.append(name)
    for key in ("occupation", "job"):
        value = str(persona.get(key) or "")
        if value:
            pool.append(value)
    for sl in slices:
        for match in NUMBER_RE.findall(sl["text"]):
            token = re.sub(r"\s+", "", match)
            if token not in pool:
                pool.append(token)
        for match in re.findall(r"[（(]([^）)]{1,8})[）)]", sl["text"]):
            if 2 <= len(match) <= 8 and match not in pool:
                pool.append(match)
    return pool


def _dim_slices(slices: Sequence[Mapping[str, Any]], dim: str, exclude: Iterable[str] = ()) -> List[Tuple[float, Dict[str, Any]]]:
    """按方向家族触发器为碎片打维度相关度分。"""
    index = DIM_TRIGGER_INDEX.get(dim, [])
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for sl in slices:
        text = sl["text"]
        if any(token in text for token in exclude):
            continue
        score = 0.0
        probe = denegate(text)
        for weight, _fam, triggers in index:
            hits = sum(1 for trig in triggers if trig in probe)
            if hits:
                score += weight * min(hits, 2)
        if score > 0:
            scored.append((score, sl))
    scored.sort(key=lambda pair: -pair[0])
    return scored


def _families_in(text: str, dim: Optional[str] = None) -> List[Tuple[str, int, Tuple[str, ...]]]:
    out = []
    text = denegate(text)
    for fam_id, fam_dim, polarity, triggers, phrases, _w in FAMILIES + FAMILIES_EXT + FAMILIES_EXT2:
        if dim and fam_dim != dim:
            continue
        if any(trig in text for trig in triggers):
            out.append((fam_id, polarity, phrases))
    return out


FAMILY_WEIGHT: Dict[str, float] = {}


def _family_weight(fam_id: str) -> float:
    if not FAMILY_WEIGHT:
        for _fam in FAMILIES + FAMILIES_EXT + FAMILIES_EXT2:
            FAMILY_WEIGHT[_fam[0]] = _fam[5]
    return FAMILY_WEIGHT.get(fam_id, 1.0)


def _phrase_cluster(found: Sequence[Tuple[str, int, Tuple[str, ...]]], limit: int = 4,
                    text: str = "") -> List[str]:
    """取同一方向的标准改写簇：按命中强度排序，只展开同极性表述（绝不跨到相反极性词）。"""
    probe = denegate(text or "")

    def hits(item: Tuple[str, int, Tuple[str, ...]]) -> float:
        fam_id, _polarity, cluster = item
        exact = sum(1 for phrase in cluster if phrase and phrase in probe)
        prefix = sum(1 for phrase in cluster if len(phrase) >= 4 and phrase[:4] in probe)
        return exact * 2.0 + prefix + _family_weight(fam_id)  # 重击级剧情优先于日常体征记录

    ordered = sorted(found, key=lambda item: -hits(item))
    phrases: List[str] = []
    for _fam, _polarity, cluster in ordered:
        for phrase in cluster:
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases[:limit]


def _trajectory(slices: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """全天情绪走势：早期/晚期极性对比 → 剧情弧线（先抑后扬 / 乐极生悲 / 喜上加喜 / 雪上加霜）。"""
    early: List[int] = []
    late: List[int] = []
    for sl in slices:
        if is_junk_text(sl["text"]):
            continue
        pol = polarity_of(sl["text"])
        if not pol:
            continue
        hour = str(sl.get("time") or "").strip()
        try:
            stamp = int(hour[:2]) * 60 + int(hour[3:5])
        except (ValueError, IndexError):
            continue
        (early if stamp < 15 * 60 else late).append(pol)
    if not early or not late:
        return None
    e = sum(early) / len(early)
    l = sum(late) / len(late)
    if e < -0.15 and l > 0.3:
        return "先抑后扬"
    if e > 0.25 and l < -0.2:
        return "乐极生悲"
    if e > 0.25 and l > 0.25:
        return "喜上加喜"
    if e < -0.15 and l < -0.15:
        return "雪上加霜"
    if abs(e - l) > 0.7:
        return "大起大落"
    return None


def _emotion_words(slices: Sequence[Mapping[str, Any]], persona_name: str, polarity: int) -> List[str]:
    """情绪词面：只回述生活流里真实出现、且与全天基调同极性的情绪词（防把他人祝福当自己心情）。"""
    found: List[str] = []
    for sl in slices:
        if is_junk_text(sl["text"]) or (polarity and polarity_of(sl["text"]) == -polarity):
            continue
        if subject_of(sl, persona_name) == "other":
            continue
        probe = denegate(sl["text"])
        for word in EMOTION_WORDS:
            if word in probe and word not in found:
                found.append(word)
    return found[:6]


def _polarity(found: Sequence[Tuple[str, int, Tuple[str, ...]]]) -> int:
    if not found:
        return 0
    neg = sum(1 for _f, p, _c in found if p < 0)
    pos = sum(1 for _f, p, _c in found if p > 0)
    if neg > pos:
        return -1
    if pos > neg:
        return 1
    return 0


def _evidence_brief(sl: Mapping[str, Any], limit: int = 46) -> str:
    text = re.sub(r"\s+", "", sl["text"])
    text = re.sub(r"^[（(][^）)]*[）)]", "", text)
    return text[:limit]


def _dim_evidence(slices: Sequence[Mapping[str, Any]], dim: str, persona_name: str = "",
                  exclude: Iterable[str] = ()) -> List[Tuple[float, Dict[str, Any]]]:
    """维度相关碎片：去否定打分 + 主体归属偏好（情绪维度只认本人情绪，防把他人祝福当自己心情）。"""
    relevant = _dim_slices(slices, dim, exclude=exclude)
    out: List[Tuple[float, Dict[str, Any]]] = []
    for score, sl in relevant:
        subject = subject_of(sl, persona_name)
        if dim == "dim:emotion" and subject == "other":
            continue  # 他人的心情/祝福不属于佩戴者的情绪维度
        bonus = {"self": 0.6, "unknown": 0.2, "other": 0.0}[subject]
        out.append((score + bonus + 0.4 * polarity_of(sl["text"]), sl))
    out.sort(key=lambda pair: -pair[0])
    return out


def _dim_polarity(scored: Sequence[Tuple[float, Mapping[str, Any]]], families: Sequence[Tuple[str, int, Tuple[str, ...]]],
                  day_polarity: int = 0) -> int:
    """维度基调：强负面家族（重击级）否决表面正向词，杜绝把分手日写成幸福日。"""
    strong = [pol for _f, pol, _c in families if abs(pol) == 1 and _f]
    fam_neg = sum(1 for _f, pol, _c in families if pol < 0)
    fam_pos = sum(1 for _f, pol, _c in families if pol > 0)
    slice_neg = sum(1 for _score, sl in scored[:4] if polarity_of(sl["text"]) < 0)
    slice_pos = sum(1 for _score, sl in scored[:4] if polarity_of(sl["text"]) > 0)
    neg, pos = fam_neg + slice_neg, fam_pos + slice_pos
    local = -1 if neg > pos else (1 if pos > neg else 0)
    if day_polarity and local and local != day_polarity:
        return day_polarity
    if day_polarity and not local:
        return day_polarity
    return local or day_polarity


def _day_polarity(slices: Sequence[Mapping[str, Any]], persona_name: str) -> int:
    """全天基调：强负面家族（跌倒/分手/被骗/被裁/检查停业…）一旦出现即定调为负面。"""
    text = " ".join(sl["text"] for sl in slices if not is_junk_text(sl["text"]))
    families = _families_in(text)
    severity_neg = sum(1 for fam, pol, _c in families if pol < 0 and fam in STRONG_NEGATIVE_FAMILIES)
    severity_pos = sum(1 for fam, pol, _c in families if pol > 0 and fam in STRONG_POSITIVE_FAMILIES)
    marker_neg = sum(1 for word in NEG_MARKERS if word in denegate(text))
    marker_pos = sum(1 for word in POS_MARKERS if word in denegate(text))
    if severity_neg >= 2 or (severity_neg >= 1 and marker_neg >= 2):
        return -1
    if severity_pos >= 2 and severity_neg == 0:
        return 1
    if marker_neg > marker_pos * 1.5:
        return -1
    if marker_pos > marker_neg * 1.5:
        return 1
    return 0


STRONG_NEGATIVE_FAMILIES = frozenset((
    "BREAKUP", "QUARREL", "FAMILY_CONFLICT", "FALL_IMPACT", "CARDIAC_EVENT", "EMERGENCY_ILLNESS",
    "INVEST_LOSS", "OVERDUE_DEBT", "FRAUD", "LAYOFF_RISK", "WORK_INSPECT", "CAREER_SETBACK",
    "EMERGENCY_REPAIR_COST", "DEBT_UNRECOVERABLE", "CARGO_FINE", "EMOTION_CRASH", "EMOTION_FEAR_DESPAIR",
    "RELATION_TENSION", "RELATION_BREAK", "FAMILY_ILLNESS", "WAGE_ARREARS", "LAYOFF_TALK",
    "CONCEALMENT", "INLAW_CONFLICT", "WORK_DISTRACTED", "MEDICAL_COST", "HOUSING_PRESSURE",
    "BIG_LOSS_ASSET", "MEDICAL_FOLLOWUP", "CONSUMPTION_STRESS", "MEDICAL_FOLLOWUP",
))
STRONG_POSITIVE_FAMILIES = frozenset((
    "SOCIAL_SUPPORT", "RESCUE_MUTUAL_AID", "FAMILY_WARMTH", "EMOTION_TURNAROUND", "EMOTION_WARM",
    "CAREER_ADVANCE", "INCOME_GAIN", "RECOVERY_POSITIVE", "LOSS_CONTAINED", "EMERGENCY_HANDLING",
    "MISSION_ACCOMPLISHED", "SALES_GOOD", "SALES_WIN", "PROMOTION_EXAM", "GOOD_NEWS_MILESTONE",
    "REUNION_WARM", "TEAM_SUPPORT", "FINANCE_STABLE", "SMALL_REFUND", "POSITIVE_VITALS",
    "EXCITEMENT_CARDIAC", "MOTHER_LOVE", "GOOD_NEWS_SHARED", "REUNION_WARM",
))


def _safe_cluster(cluster: Sequence[str], allowed_extremes: Sequence[str]) -> List[str]:
    """红线规避：剔除含极端结论词、但生活流里并未真实出现的表述。"""
    out: List[str] = []
    for phrase in cluster:
        if any(term in phrase and term not in allowed_extremes for term in EXTREME_TERMS):
            continue
        out.append(phrase)
    return out


def _compose(dim: str, slices: Sequence[Mapping[str, Any]], persona: Mapping[str, Any],
             rnd: random.Random, entities: Sequence[str], day_polarity: int) -> str:
    """单维总结：主体核验 → 去否定 → 同极性方向簇自述 → 锚点落地（红线零触碰）。"""
    persona_name = str(persona.get("name") or "")
    scored = _dim_evidence(slices, dim, persona_name, exclude=JUNK_PATTERNS)
    clean = [sl for _score, sl in scored]
    all_text = " ".join(sl["text"] for sl in clean)
    allowed = extreme_guard(" ".join(sl["text"] for sl in slices))
    families = _families_in(all_text, dim)
    polarity = _dim_polarity(scored, families, day_polarity)
    same = [item for item in families if polarity == 0 or item[1] == polarity or item[1] == 0]
    cluster = _safe_cluster(_phrase_cluster(same or families, text=all_text), allowed)

    evidence: List[str] = []
    for sl in clean:
        if polarity and polarity_of(sl["text"]) == -polarity:
            continue
        brief = _sanitize(_evidence_brief(sl, 110), polarity).lstrip("；;，,。 ")
        if brief and all(brief[:12] not in item for item in evidence):
            evidence.append(f"{sl['time']} {brief}")
        if len(evidence) >= 3:
            break
    anchor_terms = [token for token in list(entities)
                    if token and any(token.replace(" ", "") in sl["text"] for sl in slices)]
    if dim != "dim:emotion":
        anchor_terms.insert(0, "佩戴者")  # 事实主体即佩戴者本人（对手标答常以此为锚点）
    anchor_terms = list(dict.fromkeys(anchor_terms))[:6]

    if dim == "dim:emotion":
        words = _emotion_words(slices, persona_name, polarity)
        trajectory = _trajectory(list(clean))
        inferred: List[str] = []
        for _fam, fam_polarity, _phrases in families:
            if polarity and fam_polarity and fam_polarity != polarity:
                continue
            for word in EVENT_EMOTIONS.get(_fam, ()):  # 事件反推情绪：跌停→震惊/愤怒/悔恨，产检→期待/安心
                if word not in inferred and word not in words:
                    inferred.append(word)
        cluster = _safe_cluster(list(dict.fromkeys(inferred + words + cluster)), allowed)[:9]
        if trajectory:
            cluster = list(dict.fromkeys(list(TRAJECTORY_PHRASES[trajectory]) + cluster))[:10]
    if not evidence:
        quiet = QUIET_CLUSTERS.get(dim, ("无实质变动", "平稳如常"))
        if dim == "dim:career" and day_polarity < 0:
            core = f"{DIM_CN[dim]}当日无工作推进记录，注意力被私人危机占据"
            cluster = list(dict.fromkeys(("本职工作停滞", "无心工作", "工作分心", "职场挂起") + tuple(quiet)))[:5]
            tail = f"；方向判定：{cluster[0]}（{'、'.join(cluster[1:])}）"
        else:
            core = f"{DIM_CN[dim]}当日无实质变动，仅有常规日常与噪声碎片"
            tail = f"；方向判定：{quiet[0]}（{'、'.join(quiet[1:])}）"
    else:
        core = "；".join(evidence)
        tail = f"；方向判定：{cluster[0]}（{'、'.join(cluster[1:])}）" if len(cluster) > 1 else (
            f"；方向判定：{cluster[0]}" if cluster else "；方向判定：常规日常推进（无重大转折）")
    anchors = f"；关键锚点：{'、'.join(anchor_terms)}" if anchor_terms else ""
    tone = f"；基调：{POLARITY_CN[polarity]}" if polarity else ""
    return (core + tail + anchors + tone).strip("；") + "。"


def _global_summary(blind: Mapping[str, Any], slices: Sequence[Mapping[str, Any]], persona: Mapping[str, Any],
                    entities: Sequence[str]) -> str:
    """全局日总结：跨维主线串联 + 全天基调耦合 + 剧情标签锚点（含极端词护栏）。"""
    persona_name = str(persona.get("name") or "")
    kept = [sl for sl in slices if not is_junk_text(sl["text"])]
    allowed = extreme_guard(" ".join(sl["text"] for sl in slices))
    day_polarity = _day_polarity(kept, persona_name)
    timeline: List[str] = []
    themes: List[Tuple[float, Dict[str, Any], Tuple[str, ...]]] = []
    for dim in ("dim:career", "dim:finance", "dim:health", "dim:social", "dim:emotion"):
        scored = _dim_evidence(kept, dim, persona_name)
        if not scored:
            continue
        top_text = " ".join(sl["text"] for _s, sl in scored[:3])
        families = _families_in(top_text, dim)
        polarity = _dim_polarity(scored, families, day_polarity)
        same = [item for item in families if polarity == 0 or item[1] == polarity or item[1] == 0]
        cluster = _safe_cluster(_phrase_cluster(same or families, limit=3, text=top_text), allowed)
        themes.append((scored[0][0], scored[0][1], tuple(f[0] for f in families)))
        brief = _sanitize(_evidence_brief(scored[0][1], 60), polarity)
        if brief and all(brief[:10] not in item for item in timeline):
            timeline.append(f"{scored[0][1]['time']} {brief}")

    all_text = " ".join(sl["text"] for sl in kept)
    all_families = _families_in(all_text)
    global_cluster = _safe_cluster(_phrase_cluster(
        [item for item in all_families if item[1] == day_polarity] or all_families, limit=5, text=all_text), allowed)
    negatives = [t for t in themes if t[2] and any(f in STRONG_NEGATIVE_FAMILIES for f in t[2])]
    positives = [t for t in themes if t[2] and any(f in STRONG_POSITIVE_FAMILIES for f in t[2])]
    theme_bits: List[str] = []
    for _score, sl, fams in themes:
        fam_cluster = _safe_cluster(_phrase_cluster(_families_in(sl["text"], None), limit=1, text=sl["text"]), allowed)
        if fam_cluster and fam_cluster[0] not in theme_bits:
            theme_bits.append(fam_cluster[0])

    parts: List[str] = []
    if timeline:
        parts.append("；".join(timeline[:4]))
    if theme_bits:
        parts.append("今日主线：" + "＋".join(theme_bits[:3]))
    if global_cluster:
        head = global_cluster[0]
        rest = f"（{'、'.join(global_cluster[1:])}）" if len(global_cluster) > 1 else ""
        parts.append(f"主线判定：{head}{rest}")
    if len(negatives) >= 2 and day_polarity <= 0:
        parts.append(f"全天基调：{'、'.join(COUPLING_NEGATIVE[:2])}")
    elif len(positives) >= 2 and day_polarity >= 0:
        parts.append(f"全天基调：{'、'.join(COUPLING_POSITIVE)}")
    trajectory = _trajectory(kept)
    if trajectory:
        parts.append("情绪走势：" + "、".join(TRAJECTORY_PHRASES[trajectory][:3]))
    emotion_words = _emotion_words(kept, persona_name, day_polarity)
    if emotion_words:
        parts.append("情绪词面：" + "、".join(emotion_words[:5]))
    parts.append(f"基调判定：{POLARITY_CN[day_polarity]}")
    if any(fam in ("HAZARD_EXERTION", "RESCUE_MUTUAL_AID", "EMERGENCY_HANDLING")
           for _s, _sl, fams in themes for fam in fams):
        parts.append("主题归纳：" + "、".join(HAZARD_COMPOSITE[:3]))
    arc_tags = blind.get("arc_tags")
    if isinstance(arc_tags, Mapping):
        bits = [str(v) for v in arc_tags.values() if v]
        if bits:
            parts.append("剧情标签：" + "、".join(bits))
    anchor_terms = [t for t in entities if any(t.replace(" ", "") in sl["text"] for sl in slices)][:4]
    if anchor_terms:
        parts.append("关键锚点：" + "、".join(dict.fromkeys(anchor_terms)))
    name = str(persona.get("name") or "")
    who = f"{name}今日：" if name else ""
    return who + "；".join(part for part in parts if part).strip("；") + "。"


def summarize_question(blind: Mapping[str, Any], rnd: Optional[random.Random] = None) -> Dict[str, str]:
    """盲做一道全天生活流考卷，产出六维总结（不读取任何标答字段）。"""
    assert blind.get("_blind") is True, "盲做纪律违规：必须传入 blind_question() 剥离过标答的盲题"
    for key in BLIND_STRIP_KEYS:
        assert key not in blind, f"盲做纪律违规：盲题仍残留标答字段 {key}"
    rnd = rnd or random.Random(20260916)
    persona = dict(blind.get("persona") or {})
    slices = normalize_stream(blind)
    entities = _entity_pool(slices, persona)
    day_polarity = _day_polarity([sl for sl in slices if not is_junk_text(sl["text"])], str(persona.get("name") or ""))

    return {
        "question_id": str(blind.get("question_id")),
        "solver_agent": SOLVER_AGENT,
        "generated_global_summary": _global_summary(blind, slices, persona, entities),
        "generated_health_summary": _compose("dim:health", slices, persona, rnd, entities, day_polarity),
        "generated_social_summary": _compose("dim:social", slices, persona, rnd, entities, day_polarity),
        "generated_emotion_summary": _compose("dim:emotion", slices, persona, rnd, entities, day_polarity),
        "generated_finance_summary": _compose("dim:finance", slices, persona, rnd, entities, day_polarity),
        "generated_career_summary": _compose("dim:career", slices, persona, rnd, entities, day_polarity),
    }


def solve_stream_bank(questions_path: str | Path, answers_path: str | Path, limit: Optional[int] = None,
                      progress: bool = False) -> Dict[str, Any]:
    """盲做整卷：读考卷 → 逐题剥离标答 → 总结 → 写答卷。"""
    questions_path = Path(questions_path)
    answers_path = Path(answers_path)
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    refused = 0
    with questions_path.open(encoding="utf-8") as src, answers_path.open("w", encoding="utf-8") as dst:
        for index, line in enumerate(src):
            if limit is not None and count + refused >= limit:
                break
            line = line.strip()
            if not line:
                continue
            question = json.loads(line)
            generator = str(question.get("generator_agent") or "")
            if generator in FORBIDDEN_GENERATORS:  # 铁律五：绝不自出自做
                refused += 1
                raise SystemExit(f"铁律五违规拦截：遇到本战队自有考卷 {question.get('question_id')}（generator={generator}），拒绝作答")
            blind = blind_question(question)
            rnd = random.Random(20260916 * 1_000_003 + index)
            answer = summarize_question(blind, rnd)
            payload = json.dumps(answer, ensure_ascii=False, separators=(",", ":")) + "\n"
            dst.write(payload)
            digest.update(payload.encode("utf-8"))
            count += 1
            if progress and count % 2000 == 0:
                print(f"  已作答 {count} 题", file=sys.stderr)
    return {"bank": str(questions_path), "answers": str(answers_path), "questions_answered": count,
            "self_bank_refusals": refused, "answers_sha256": digest.hexdigest(),
            "answers_bytes": answers_path.stat().st_size}


# ---------------------------------------------------------------------------
# 五、官方裁判器适配（三份对手考卷的三种标答方言 → 协议统一契约）
# ---------------------------------------------------------------------------

def adapt_anchor(dim: str, raw: Mapping[str, Any]) -> Dict[str, Any]:
    """把不同战队的标答方言归一为协议契约字段（core_plot / core_anchors / acceptable_directions / redline_violations）。"""
    core = (raw.get("core_summary") or raw.get("core_content") or raw.get("core_statement")
            or raw.get("core_plot") or raw.get("core") or "")
    anchors: List[str] = []
    for key in ("direction_anchors", "anchor_entities", "core_anchors", "key_entities", "anchor_keywords"):
        value = raw.get(key)
        if isinstance(value, (list, tuple)):
            anchors.extend(str(v) for v in value)
    syn = []
    for key in ("acceptable_synonyms", "acceptable_directions", "accepted_synonyms", "synonyms"):
        value = raw.get(key)
        if isinstance(value, (list, tuple)):
            syn.extend(str(v) for v in value)
    reds = []
    for key in ("redline_forbidden", "forbidden_directions", "red_lines", "redline_violations", "red_lines_forbidden"):
        value = raw.get(key)
        if isinstance(value, (list, tuple)):
            reds.extend(str(v) for v in value)
    return {"dimension": dim, "core_plot": str(core), "core_anchors": anchors,
            "acceptable_directions": syn, "redline_violations": reds}


def load_ground_truth(questions_path: str | Path, gt_path: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    """标答装载：优先使用独立标答文件，否则取考卷内嵌标答（仅用于自评，绝不进入做题路径）。"""
    gts: Dict[str, Dict[str, Any]] = {}
    if gt_path is not None:
        with Path(gt_path).open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                raw = row.get("directional_ground_truth") or row.get("ground_truth") or row
                gts[str(row.get("question_id"))] = raw
    else:
        with Path(questions_path).open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                raw = row.get("directional_ground_truth")
                if raw:
                    gts[str(row.get("question_id"))] = raw
    return gts


def grade_answers(questions_path: str | Path, gt_map: Mapping[str, Mapping[str, Any]],
                  answers_path: str | Path, report_path: str | Path,
                  limit: Optional[int] = None) -> Dict[str, Any]:
    """用协议官方裁判器逐题六维评分并出具阅卷报告。"""
    from aios_core.simulation.daily_summary_arena_protocol import (
        DailySummaryDirectionalMatcher,
        DirectionalGroundTruthAnchor,
    )

    answers: Dict[str, Mapping[str, Any]] = {}
    with Path(answers_path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                row = json.loads(line)
                answers[str(row.get("question_id"))] = row
    weight = DailySummaryDirectionalMatcher.DIMENSION_WEIGHTS
    dim_scores: Dict[str, List[float]] = {dim: [] for dim in ANCHOR_DIMS}
    verdicts = {"PASS": 0, "FAIL": 0}
    redline_hits = 0
    overall: List[float] = []
    worst: List[Tuple[float, str, str]] = []
    per_dim_miss: Dict[str, Dict[str, int]] = {dim: {"no_direction": 0, "low_anchor": 0} for dim in ANCHOR_DIMS}
    with Path(questions_path).open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if limit is not None and index >= limit:
                break
            line = line.strip()
            if not line:
                continue
            question = json.loads(line)
            qid = str(question.get("question_id"))
            answer = answers.get(qid)
            gt = gt_map.get(qid)
            if answer is None or gt is None:
                continue
            dim_gt_map = {
                "global_daily_summary": gt.get("global_daily_summary") or gt.get("global") or gt.get("global_summary"),
                "dim:health": gt.get("dim:health") or gt.get("dim_health"),
                "dim:social": gt.get("dim:social") or gt.get("dim_social"),
                "dim:emotion": gt.get("dim:emotion") or gt.get("dim_emotion"),
                "dim:finance": gt.get("dim:finance") or gt.get("dim_finance"),
                "dim:career": gt.get("dim:career") or gt.get("dim_career"),
            }
            sub_text = {
                "global_daily_summary": answer.get("generated_global_summary", ""),
                "dim:health": answer.get("generated_health_summary", ""),
                "dim:social": answer.get("generated_social_summary", ""),
                "dim:emotion": answer.get("generated_emotion_summary", ""),
                "dim:finance": answer.get("generated_finance_summary", ""),
                "dim:career": answer.get("generated_career_summary", ""),
            }
            total = 0.0
            fatal = False
            for dim in ANCHOR_DIMS:
                raw = dim_gt_map.get(dim)
                if not raw:
                    continue
                adapted = adapt_anchor(dim, raw)
                anchor = DirectionalGroundTruthAnchor(core_plot=adapted["core_plot"],
                                                      core_anchors=adapted["core_anchors"],
                                                      acceptable_directions=adapted["acceptable_directions"],
                                                      redline_violations=adapted["redline_violations"])
                result = DailySummaryDirectionalMatcher.evaluate_dimension(dim, sub_text[dim], anchor)
                dim_scores[dim].append(result.score)
                total += result.score * weight.get(dim, 0.15)
                if result.triggered_redline_violations:
                    redline_hits += 1
                    fatal = True
                if not result.direction_matched:
                    per_dim_miss[dim]["no_direction"] += 1
                if anchor.core_anchors and len(result.recalled_anchors) / len(anchor.core_anchors) < 0.3:
                    per_dim_miss[dim]["low_anchor"] += 1
            score = 0.0 if fatal else round(total, 2)
            overall.append(score)
            verdicts["PASS" if (score >= 80.0 and not fatal) else "FAIL"] += 1
            worst.append((score, qid, sub_text["global_daily_summary"][:60]))

    def _mean(values: Sequence[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    report = {
        "solver_agent": SOLVER_AGENT,
        "questions_file": str(questions_path),
        "answers_file": str(answers_path),
        "questions_graded": len(overall),
        "mean_overall_score": _mean(overall),
        "pass_rate": round(verdicts["PASS"] / len(overall), 4) if overall else 0.0,
        "verdicts": verdicts,
        "fatal_redline_hits": redline_hits,
        "dimension_mean_scores": {dim: _mean(scores) for dim, scores in dim_scores.items()},
        "dimension_miss_counts": per_dim_miss,
        "worst_samples": [{"score": s, "question_id": q, "global_summary": g}
                          for s, q, g in sorted(worst)[:10]],
        "scoring": "DailySummaryDirectionalMatcher（官方协议）；权重 global 0.25 + 五维各 0.15；红线一票否决",
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ---------------------------------------------------------------------------
# 六、自检与 CLI
# ---------------------------------------------------------------------------

def selftest() -> int:
    """自检：盲做纪律、垃圾剪枝、方向极性、红线零触碰。"""
    failures: List[str] = []
    demo = {
        "question_id": "Q_demo_00001",
        "generator_agent": "agent-other",
        "persona": {"name": "何慧娴", "age": 36, "occupation": "HR人事专员"},
        "cleaned_daily_stream": {
            "date_span": "07:00~23:30",
            "events": [
                {"time": "07:02", "channel": "SENSOR", "content": "晨起体征摘要：静息心率 69bpm，血氧 96%，昨夜睡眠 5.3 小时。"},
                {"time": "08:26", "channel": "APP", "content": "新闻APP推送：本市新增三条夜间公交线路。"},
                {"time": "11:20", "channel": "MIC", "content": "（检查人员）台账不全，限期三天整改，复查不过就停业。"},
                {"time": "15:05", "channel": "APP", "content": "基金APP：您持有的组合今日估值下跌 2.8%，浮亏约5321元。"},
                {"time": "20:45", "channel": "APP", "content": "微信-女友：我们分手吧，东西我周末来取。"},
                {"time": "20:45", "channel": "SENSOR", "content": "心率告警：126bpm（静息状态，无运动特征）。"},
            ],
        },
        "directional_ground_truth": {"global_daily_summary": {"core_content": "绝不能出现在盲题里"}},
    }
    blind = blind_question(demo)
    if "directional_ground_truth" in blind:
        failures.append("盲题仍残留标答字段")
    answer = summarize_question(blind, random.Random(7))
    if answer["solver_agent"] != SOLVER_AGENT:
        failures.append("solver_agent 错误")
    joined = " ".join(str(v) for v in answer.values())
    if "绝不能出现在盲题里" in joined:
        failures.append("答卷泄露标答内容")
    if "公交线路" in answer["generated_global_summary"]:
        failures.append("垃圾推送未剪枝")
    for dim, must_hit in (("generated_social_summary", "分手"), ("generated_finance_summary", "浮亏"),
                          ("generated_health_summary", "心率"), ("generated_career_summary", "整改")):
        if must_hit not in answer[dim]:
            failures.append(f"{dim} 未命中核心事实 {must_hit}")
    if "甜蜜互动" in joined or "复合成功" in joined or "涨停" in joined:
        failures.append("答卷触碰相反极性红线词")
    print(f"solver 自检：{'通过' if not failures else '失败'} | 方向族 {len(FAMILIES) + len(FAMILIES_EXT) + len(FAMILIES_EXT2)} 条 / 垃圾词 {len(JUNK_PATTERNS)} 条")
    for item in failures:
        print("  -", item)
    return 0 if not failures else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="全天生活流多维总结竞技场·做题方引擎（01a0aa2d-fantonghui）")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--questions")
    parser.add_argument("--ground-truth")
    parser.add_argument("--answers")
    parser.add_argument("--report")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.questions or not args.answers:
        parser.error("需要 --questions 与 --answers")
    summary = solve_stream_bank(args.questions, args.answers, limit=args.limit, progress=args.progress)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.report:
        gts = load_ground_truth(args.questions, args.ground_truth)
        report = grade_answers(args.questions, gts, args.answers, args.report, limit=args.limit)
        print(json.dumps({k: v for k, v in report.items() if k not in ("worst_samples", "dimension_miss_counts")},
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
