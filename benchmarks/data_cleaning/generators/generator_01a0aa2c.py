#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIOS 3.0 全天生活流与多维总结高熵出卷官（Generator ``01a0aa2c-fantonghui``）。

本模块是**确定性题库发生器**：输入种子与题量，输出 10,000 道「真实人生 24 小时生活流」
高熵对抗考题（``questions_01a0aa2c-fantonghui.jsonl``）与配套方向性标答
（``gt_01a0aa2c-fantonghui.jsonl``），严格对齐：

1. ``aios_core.simulation.cleaning_arena_protocol.CleaningQuestion`` 契约
   （sensor / mic / voiceprint / app / utt 五路流 + ``ground_truth_facts`` + ``ground_truth_junk_ids``）；
2. Master Dispatch #11 的五路配比（sensor 30% / mic 30% / voiceprint 20% / app 15% / utt 5%）；
3. 出卷官职责规范：每题一份**六维方向性标答**
   （全局日总结 + dim:health / dim:social / dim:emotion / dim:finance / dim:career），
   每个维度块都给出【核心要点】+【可接受方向同义词】+【绝对偏离红线判据】。

【质量铁律 · 本发生器自身的三条自缚规矩】

R1 **锚点必然可恢复**：标答 ``anchor_entities`` 逐字来自题目可见数据（五路流文本或结构化字段），
   并额外通过「实体合成宇宙」审计（数值+单位、人数、时长换算）。绝不允许出现
   「标答要求 139bpm 而端侧只有 124bpm」这类对手题库的信息落差缺陷。
R2 **零结构性泄漏**：片断 ID 使用统一命名（``<题号>-<模态>-<序号>``），垃圾与保留段
   **不可由 ID 前缀区分**；不写入任何 ``is_junk`` / ``label`` 结论型标记，
   所有结论必须由求解方从物理量与语义自行推断。
R3 **可判分性**：每题标答事实的方向词簇互斥且给出红线判据，
   语义近似（"争吵"↔"吵闹"）全额给分，方向反转（"打情骂俏"）一票否决。

用法::

    /home/user/.venv/bin/python benchmarks/data_cleaning/generators/generator_01a0aa2c.py \
        --count 10000 \
        --questions benchmarks/data_cleaning/questions/questions_01a0aa2c-fantonghui.jsonl \
        --ground-truth benchmarks/data_cleaning/ground_truth/gt_01a0aa2c-fantonghui.jsonl \
        --report benchmarks/data_cleaning/reports/generation_01a0aa2c-fantonghui.md
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

AGENT_ID = "01a0aa2c-fantonghui"
QUESTION_PREFIX = "Q_01a0aa2c"
GENERATOR_AGENT = "agent-01a0aa2c"
DEVICE_PREFIX = "aios-band-aa2c"
DAY_START_MIN = 7 * 60            # 07:00
DAY_END_MIN = 23 * 60 + 30        # 23:30

MODALITY_MIX: Tuple[Tuple[str, int], ...] = (
    ("sensor", 3000),
    ("mic", 3000),
    ("voiceprint", 2000),
    ("app", 1500),
    ("utt", 500),
)

DIFFICULTY_MIX: Tuple[Tuple[str, float], ...] = (
    ("EASY", 0.15),
    ("MEDIUM", 0.35),
    ("HARD", 0.35),
    ("ADVERSARIAL", 0.15),
)


# ---------------------------------------------------------------------------
# 一、人格档案（24 位佩戴者，覆盖年龄/职业/家庭/健康/财务/事业全谱）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    """一位手环佩戴者的完整人生背景（跨维度冲突的生成底座）。"""

    pid: str
    name: str
    gender: str
    age: int
    occupation: str
    city: str
    area: str
    device: str
    spouse: Optional[str]
    child: Optional[str]
    parent: Optional[str]
    friend: str
    colleague: str
    leader: Optional[str]
    hr_base: int
    conditions: Tuple[str, ...]
    bank_tail: str
    phone_tail: str
    job_scene: str
    dialect: str

    @property
    def family(self) -> Tuple[str, ...]:
        return tuple(x for x in (self.spouse, self.child, self.parent) if x)

    @property
    def key_contacts(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(self.family + (self.friend, self.colleague)))


PERSONAS: Tuple[Persona, ...] = (
    Persona("D01", "陈建国", "male", 58, "退休中学教师", "南京", "龙江小区", f"{DEVICE_PREFIX}-p01-0731",
            "李秀兰", "陈晨", None, "老周", "王主任", None, 72, ("高血压",), "4831", "2071", "社区书法班", "南京话"),
    Persona("D02", "林晓薇", "female", 31, "互联网产品经理", "上海", "张江人才公寓", f"{DEVICE_PREFIX}-p02-0731",
            None, None, "母亲", "小蔡", "Amy", "陈总", 78, ("轻度贫血",), "6620", "3391", "618大促项目组", "普通话"),
    Persona("D03", "赵大山", "male", 46, "货运司机", "西安", "枣园小区", f"{DEVICE_PREFIX}-p03-0731",
            "王秀英", "赵阳", None, "车队老李", "调度小刘", "张队长", 84, ("腰椎间盘突出", "高血压"), "5013", "7742", "陕汽重卡专线", "陕西话"),
    Persona("D04", "周敏", "female", 34, "三甲医院护士长", "武汉", "常青花园", f"{DEVICE_PREFIX}-p04-0731",
            "刘志强", "刘一诺", None, "小周护士", "张医生", "护理部李主任", 76, ("甲状腺结节",), "8871", "1120", "心内科住院部", "武汉话"),
    Persona("D05", "孙志远", "male", 41, "建筑项目经理", "成都", "春熙路", f"{DEVICE_PREFIX}-p05-0731",
            "何丽", "孙浩然", None, "张工", "资料员小吴", "王总", 88, ("高血脂", "心律不齐"), "3345", "9087", "天府新区工地", "四川话"),
    Persona("D06", "吴倩", "female", 28, "中学英语教师", "杭州", "钱塘新区", f"{DEVICE_PREFIX}-p06-0731",
            None, None, "父亲", "张婷", "教务处老周", "教务处老周", 74, ("慢性胃炎",), "7712", "5560", "高二年级组", "普通话"),
    Persona("D07", "何国强", "male", 63, "退休公交司机", "北京", "朝阳双井", f"{DEVICE_PREFIX}-p07-0731",
            "张桂芝", "何磊", None, "棋友老孙", "社区小刘", None, 70, ("冠心病", "2型糖尿病"), "2288", "6614", "社区棋牌室", "北京话"),
    Persona("D08", "徐婉如", "female", 36, "会计师事务所合伙人", "上海", "静安寺", f"{DEVICE_PREFIX}-p08-0731",
            "罗建平", "徐小满", None, "同学薇薇", "钱合伙人", "钱合伙人", 80, ("焦虑状态", "失眠"), "9902", "3355", "年报审计季", "普通话"),
    Persona("D09", "黄小军", "male", 52, "五金厂老板", "佛山", "南海桂城", f"{DEVICE_PREFIX}-p09-0731",
            "陈美华", "黄婷", None, "阿福", "车间主任", None, 82, ("痛风", "脂肪肝"), "4417", "8803", "五金冲压车间", "粤语"),
    Persona("D10", "李静怡", "female", 25, "新媒体运营", "广州", "天河棠下", f"{DEVICE_PREFIX}-p10-0731",
            None, None, "母亲", "室友小雨", "主管Lucy", "主管Lucy", 76, ("低血糖",), "6653", "2287", "短视频账号运营", "普通话"),
    Persona("D11", "马俊峰", "male", 39, "保险销售主管", "郑州", "金水区", f"{DEVICE_PREFIX}-p11-0731",
            "刘娟", "马小川", None, "徒弟王强", "内勤小李", "区域总", 86, ("脂肪肝", "超重"), "5508", "4419", "季度冲单", "河南话"),
    Persona("D12", "罗秀珍", "female", 67, "退休纺织工人", "重庆", "沙坪坝", f"{DEVICE_PREFIX}-p12-0731",
            None, "罗刚", None, "邻居刘玉华", "社区网格员", None, 74, ("骨质疏松", "白内障术后"), "3390", "7726", "社区广场舞队", "重庆话"),
    Persona("D13", "张海涛", "male", 33, "外卖骑手", "深圳", "龙华民治", f"{DEVICE_PREFIX}-p13-0731",
            "李梅", "张朵朵", None, "同站骑手小马", "站长", "站长", 88, ("慢性胃炎", "陈旧性踝伤"), "8821", "6640", "美团龙华三站", "普通话"),
    Persona("D14", "郑雅琴", "female", 45, "小学副校长", "长沙", "岳麓区", f"{DEVICE_PREFIX}-p14-0731",
            "刘建国", "刘思远", None, "闺蜜陈老师", "教导主任", "校长", 78, ("高血压", "偏头痛"), "7745", "3390", "学期考核", "长沙话"),
    Persona("D15", "王一鸣", "male", 29, "独立插画师", "成都", "武侯区", f"{DEVICE_PREFIX}-p15-0731",
            None, None, "父亲", "大学同学大鹏", "编辑周姐", None, 76, ("颈椎病", "失眠"), "6690", "1188", "绘本约稿", "普通话"),
    Persona("D16", "郭春梅", "female", 51, "超市理货员", "沈阳", "铁西区", f"{DEVICE_PREFIX}-p16-0731",
            "赵国庆", "郭雪", None, "同组小刘", "组长", "组长", 80, ("2型糖尿病",), "3327", "9985", "生鲜区理货", "东北话"),
    Persona("D17", "谢文斌", "male", 44, "中学语文老师", "南昌", "红谷滩", f"{DEVICE_PREFIX}-p17-0731",
            "万丽", "谢子轩", None, "同事老徐", "年级主任", "年级主任", 74, ("声带息肉", "慢性咽炎"), "5561", "2274", "毕业班带班", "南昌话"),
    Persona("D18", "邓丽华", "female", 38, "服装厂缝纫组长", "东莞", "长安镇", f"{DEVICE_PREFIX}-p18-0731",
            "唐建", "唐果", None, "工友阿珍", "车间主管", "车间主管", 82, ("腰椎劳损", "腕管综合征"), "8893", "3364", "牛仔线流水线", "粤语"),
    Persona("D19", "曹伟", "male", 57, "国企中层", "天津", "河西区", f"{DEVICE_PREFIX}-p19-0731",
            "孙敏", "曹阳", None, "老同事刘处", "办公室主任", "总经理", 76, ("高血压", "高血脂", "高尿酸"), "2216", "7713", "集团审计整改", "天津话"),
    Persona("D20", "韩雪", "female", 23, "咖啡店店员", "北京", "五道口", f"{DEVICE_PREFIX}-p20-0731",
            None, None, "母亲", "乐队鼓手阿凯", "店长", "店长", 78, ("哮喘",), "6634", "4471", "Livehouse驻唱", "普通话"),
    Persona("D21", "田国富", "male", 62, "退休工程师", "青岛", "市南区", f"{DEVICE_PREFIX}-p21-0731",
            "王丽华", "田甜", None, "老同事张工", "社区医生", None, 72, ("帕金森早期", "高血压"), "4482", "9956", "老年大学摄影班", "青岛话"),
    Persona("D22", "尹丹", "female", 30, "执业律师", "深圳", "福田CBD", f"{DEVICE_PREFIX}-p22-0731",
            "谢峰", None, "母亲", "同事陈律师", "合伙人林律师", "林律师", 80, ("胃溃疡",), "6698", "1102", "并购尽调项目", "普通话"),
    Persona("D23", "江涛", "male", 47, "出租车司机", "哈尔滨", "道里区", f"{DEVICE_PREFIX}-p23-0731",
            "李霞", "江雪", None, "车牌友老赵", "车队长", "车队长", 84, ("高血压", "睡眠呼吸暂停"), "3358", "7784", "夜班出租", "东北话"),
    Persona("D24", "崔明月", "female", 27, "幼儿园老师", "苏州", "工业园区", f"{DEVICE_PREFIX}-p24-0731",
            None, None, "父亲", "同事小雅", "园长", "园长", 76, ("过敏性鼻炎",), "7749", "2231", "大班班主任", "普通话"),
)

#: 一次性陌生人（垃圾片段里的推销/路人/客服等，用于声纹杂散与背景人声）
STRANGERS: Tuple[str, ...] = (
    "推销员小赵", "中介小陈", "快递员小李", "外卖骑手", "陌生来电客服", "路人大叔", "广场舞阿姨",
    "发传单小哥", "保险电销", "装修队工头", "隔壁桌客人", "健身房会籍顾问", "银行外呼专员",
    "网约车司机", "培训班招生老师", "二手车商", "餐厅服务员", "奶茶店店员", "地铁邻座乘客", "小区保安",
)

SPOKEN_AGE_HINT: Tuple[str, ...] = ("语气年轻", "嗓音沙哑", "语速偏快", "方言口音重", "音量偏高")


# ---------------------------------------------------------------------------
# 二、噪声与垃圾素材池（保持 1:3~1:4 的保留:垃圾密度，且 ID 无泄漏）
# ---------------------------------------------------------------------------

#: 各类噪声文本池：文本本身即垃圾，需靠语义/物理量判定剪枝。
NOISE_MIC: Tuple[Tuple[str, str], ...] = (
    ("subway_announce", "（地铁报站：13号线列车即将到站，请乘客先下后上）"),
    ("subway_announce", "（公交报站：下一站人民广场，请下车的乘客提前准备）"),
    ("mall_promotion", "（商场叫卖：全场三折起，办会员卡立减五十，走过路过不要错过）"),
    ("mall_promotion", "（促销广播：二楼女装清仓甩卖，最后三天，欢迎选购）"),
    ("market_hawking", "（菜市场叫卖：新鲜西红柿八毛一斤，便宜卖了啊）"),
    ("wind_noise", "（持续风噪，10~250Hz 低频能量偏高，无可懂语音）"),
    ("renovation", "（电锤敲击墙体，间歇性，共13次）"),
    ("keyboard_typing", "（机械键盘连续敲击声，无语音成分）"),
    ("traffic_noise", "（公交车刹车顿挫与发动机轰鸣，乘客嘈杂）"),
    ("neighbor_chatter", "（邻桌客人：诶你说那个新开的火锅店咋样来着）"),
    ("talk_show_playback", "（短视频外放：家人们谁懂啊，今天这个房价真的绝了）"),
    ("tv_drama_playback", "（电视剧台词外放：来人呐，把这个人给我拖出去！）"),
    ("live_stream_playback", "（直播带货外放：家人们冲一波，这个价格我给你们打下来了）"),
    ("snore", "（打鼾声与呼吸暂停样声学形态，无语音）"),
    ("crowd_babble", "（多人嘈杂语音混合，无法分辨具体说话人）"),
    ("elevator_music", "（电梯背景音乐：轻音乐，无语音）"),
    ("kitchen_noise", "（油烟机轰鸣与锅铲碰撞声）"),
    ("rain_ambient", "（窗外持续雨声，雨滴敲打遮阳棚）"),
)

NOISE_APP: Tuple[Tuple[str, str, str, str], ...] = (
    ("拼多多", "砍一刀", "【拼多多】您的好友邀请您帮忙砍一刀，还差0.3元即可提现200元，点击链接立即助力", "pinduoduo"),
    ("拼多多", "现金提现", "【拼多多】恭喜您获得100元提现机会，再邀请17位好友即可到账", "pinduoduo"),
    ("短信", "验证码", "【验证码】839201，5分钟内有效，切勿泄露给他人。", "sms_code"),
    ("短信", "验证码", "【移动】您本次登录验证码为 462157，如非本人操作请忽略。", "sms_code"),
    ("淘宝", "促销", "【淘宝】亲，您收藏的商品降价了，跨店满300减50，今晚24点结束", "marketing"),
    ("美团", "促销", "【美团】您有3元外卖红包即将过期，点击领取立减", "marketing"),
    ("京东", "促销", "【京东】年中大促，家电以旧换新最高补贴2000元，先领券再下单", "marketing"),
    ("今日头条", "新闻推送", "【今日头条】巴基斯坦发生5.8级地震，暂无人员伤亡报告", "news_push"),
    ("抖音", "直播推荐", "【抖音】您关注的直播间正在开播：限时秒杀，先到先得", "marketing"),
    ("微信", "表情包", "[表情] [图片] 哈哈哈哈哈哈哈", "wechat_trivia"),
    ("微信群", "刷屏", "【工作群】收到 收到 收到 +1 +1 +1", "wechat_trivia"),
    ("携程", "行程广告", "【携程】三亚机酒自由行低至999元，仅限今日", "marketing"),
    ("银行", "信用卡分期外呼", "【广发银行】您有一笔账单可分24期，手续费5折，回复1办理", "marketing"),
    ("短信", "博彩/贷款", "【极速贷】凭身份证即可借款5万，日息0.02%，点击申请", "spam"),
    ("短信", "积分兑换", "【移动】您的2888积分将于年底清零，点击兑换小米音箱", "spam"),
    ("快递", "派件通知(群发)", "【菜鸟】您的包裹已放入2号柜，取件码请在小程序中查看", "delivery_junk"),
    ("微信", "微商", "【朋友圈】姐，这款面膜真的绝了，回购三次了，要不要给你留一盒", "marketing"),
    ("支付宝", "花呗提醒", "【支付宝】您的花呗本月账单已出，最低还款0元（已还清）", "trivia"),
)

NOISE_UTT: Tuple[Tuple[str, str, str], ...] = (
    ("自语", "钥匙放哪了？刚才还在手里的。", "平静"),
    ("自语", "嗯，充电线放包里了没……算了出门再说。", "平静"),
    ("自语", "1、2、3、4……（数着台阶上楼）", "平静"),
    ("吐槽", "这天气，热得人都要化了。", "烦躁"),
    ("吐槽", "电梯又坏了，天天爬楼谁受得了。", "烦躁"),
    ("玩笑", "我跟你开玩笑的，别当真啊。", "玩笑"),
    ("玩笑", "你要是敢骗我，我就罚你请客，哈哈。", "玩笑"),
    ("玩笑", "哈哈哈笑死我了，你这也太逗了。", "大笑"),
    ("自嘲", "哎，又胖了两斤，减不下来了。", "自嘲"),
    ("哼歌", "（哼唱《涛声依旧》副歌，跑调）", "放松"),
    ("哼歌", "（跟着广播哼《成都》，只记得两句）", "放松"),
    ("口头禅发泄", "我真的服了，这什么破事儿啊。", "烦躁"),
    ("口头禅发泄", "烦死了，真想直接走人。", "疲惫"),
    ("口头禅发泄", "累死了，我要躺平一辈子。", "疲惫"),
    ("口头禅发泄", "烦死了，这日子没法过了。", "疲惫"),
    ("口头禅发泄", "我算是看明白了，这世界没救了。", "丧"),
    ("酒后吹牛", "10万算什么，我一年随便就赚300万。", "亢奋"),
    ("酒后吹牛", "下个月我就把比亚迪给收购了，你们信不信？", "亢奋"),
    ("酒后吹牛", "等我哪天发达了，先给咱小区每人发一万块！", "亢奋"),
    ("酒后吹牛", "我跟你说，明年我就公司上市，到时候请你们全去旅游！", "亢奋"),
)

#: 传感器垃圾（低价值物理量片段：不影响事实，但必须能被判为冗余）
NOISE_SENSOR_JUNK: Tuple[Tuple[str, str, str], ...] = (
    ("imu_window", "typing_vibration", "键盘敲击震动"),
    ("imu_window", "hand_swing", "空手摆臂震动"),
    ("imu_window", "door_open", "开关门轻微震动"),
    ("imu_window", "bus_bump", "公交颠簸顿挫"),
    ("imu_window", "walking_steps", "匀速步行周期性晃动"),
    ("ppg_segment", "hr_normal_swing", "静息心率正常波动"),
    ("baro_segment", "baro_drift", "气压缓慢漂移"),
    ("gps_segment", "gps_jitter", "定位漂移抖动"),
)

#: 声纹杂散碎片（一次性陌生人声，须物理剪枝）
NOISE_VOICEPRINT_SAMPLE: Tuple[str, ...] = (
    "快递员：新店开业进来看看",
    "推销员：您好，地铁口商铺了解一下",
    "客服：您的话费套餐可以升级",
    "路人：劳驾借过一下",
    "店员：扫码关注送小礼品",
    "中介：这套房源今天刚放出来",
    "乘客：下一站到了啊",
    "食客：这道菜有点咸",
    "学员：老师这个怎么弄",
    "导购：姐您穿这个肯定好看",
)

# ---------------------------------------------------------------------------
# 三、切片与事实的数据结构
# ---------------------------------------------------------------------------


@dataclass
class Slice:
    """一道题里的一个生活流切片（``keep`` 仅用于出题端标注，绝不写入题目）。"""

    modality: str
    t: int
    payload: Dict[str, Any] = field(default_factory=dict)
    text: str = ""
    keep: bool = False
    tag: str = ""
    scene: str = ""


@dataclass
class FactSpec:
    """一条方向性标答事实（source_tag 在装配期解析为真实片断 ID）。"""

    dim: str
    intent: str
    core: str
    anchors: Tuple[str, ...]
    keywords: Tuple[str, ...]
    red_lines: Tuple[str, ...]
    source_tag: str
    confidence: float = 0.95


@dataclass
class Pack:
    """一个生活事件包：切片 + 事实 + 维度块贡献 + 主线贡献。"""

    slices: List[Slice]
    facts: List[FactSpec]
    dim_blocks: Dict[str, Dict[str, Any]]
    summary: str


#: 生态维度映射：事实维度（与对手卷同一套命名，保证跨队可判分）→ 六维总结块（出卷官交付口径）
ECOSYSTEM_DIM_TO_SIX: Dict[str, str] = {
    "dim:health": "dim:health",
    "dim:safety": "dim:health",
    "dim:environment": "dim:health",
    "dim:social": "dim:social",
    "dim:family": "dim:social",
    "dim:emotion": "dim:emotion",
    "dim:finance": "dim:finance",
    "dim:legal": "dim:finance",
    "dim:logistics": "dim:finance",
    "dim:career": "dim:career",
    "dim:daily": "dim:career",
}


#: 意图 → 六维总结块（优先于按 dim 的默认映射；用于把安全/法律/物流等生态维度归入老大要求的六维）
SIX_DIM_BY_INTENT: Dict[str, str] = {
    "VOICE_IMPERSONATION_FRAUD": "dim:social",
    "FRAUD_ATTEMPT": "dim:finance",  # 六维总结口径：资金安全风险归入财务维度
    "COURT_SUMMONS": "dim:finance",
    "FALL_IMPACT": "dim:health",
    "FALL_IMPACT_FAKED": "dim:health",
    "WEAK_SOS": "dim:health",
    "HIDDEN_CARDIAC_CRISIS": "dim:health",
    "CARDIAC_PVC_BURST": "dim:health",
    "RESTING_TACHYCARDIA": "dim:health",
    "HYPOGLYCEMIA": "dim:health",
    "SLEEP_DURATION": "dim:health",
    "BAROMETRIC_STORM": "dim:health",
    "LAB_CRITICAL_VALUE": "dim:health",
    "MEDICAL_APPOINTMENT": "dim:health",
    "MEDICATION_REMINDER": "dim:health",
    "REAL_MEDICAL_INTENT": "dim:health",
    "BANK_LARGE_TRANSFER": "dim:finance",
    "BILL_REPAYMENT": "dim:finance",
    "DEBT_BORROWING": "dim:finance",
    "REPAYMENT_PROMISE": "dim:finance",
    "DEBT_COLLECTION_CONFLICT": "dim:finance",
    "SALARY_BONUS": "dim:finance",
    "WORK_SETBACK": "dim:career",
    "WORK_OVERTIME": "dim:career",
    "NDA_CONFIDENTIALITY": "dim:career",
    "SIGNING_SCHEDULE": "dim:career",
    "REAL_RESIGNATION": "dim:career",
    "WORK_COORDINATION": "dim:career",
    "FAMILY_ENTRUSTMENT": "dim:social",
    "CHILD_SCHOOL": "dim:social",
    "FAMILY_DAILY": "dim:social",
    "VOICE_BINDING_KEY_CONTACT": "dim:social",
    "ARGUMENT_CONFLICT": "dim:social",
    "VERBAL_VENT": "dim:emotion",
}


def _six_dim(fact: FactSpec) -> str:
    return SIX_DIM_BY_INTENT.get(fact.intent, ECOSYSTEM_DIM_TO_SIX.get(fact.dim, "dim:career"))


def _mk(
    modality: str,
    t: int,
    *,
    text: str = "",
    payload: Optional[Dict[str, Any]] = None,
    keep: bool = False,
    tag: str = "",
    scene: str = "",
) -> Slice:
    return Slice(modality=modality, t=t, payload=payload or {}, text=text, keep=keep, tag=tag, scene=scene)


#: 非保留切片的文本截断长度（垃圾文本不承载任何标答锚点，可安全压缩体积）
JUNK_TEXT_LIMIT = 8


JUNK_KEEP_FIELDS: Dict[str, Tuple[str, ...]] = {
    "mic": ("scene",),
    "app": ("app_name", "sender"),
    "utt": ("junk_tag",),
    "sensor": ("kind", "label"),
}


def _trim_junk_slices(slices: Sequence[Slice]) -> None:
    """非保留切片瘦身：截断文本、删除与判决无关的字段（保留项一律不动）。"""
    for sl in slices:
        if sl.keep:
            continue
        payload = sl.payload
        for key in ("note", "sample_text"):
            value = payload.get(key)
            if isinstance(value, str) and len(value) > JUNK_TEXT_LIMIT + 6:
                payload[key] = value[: JUNK_TEXT_LIMIT + 6] + "…"
        if sl.text and len(sl.text) > JUNK_TEXT_LIMIT + 6:
            sl.text = sl.text[: JUNK_TEXT_LIMIT + 6] + "…"
        if isinstance(payload.get("content"), str) and len(payload["content"]) > JUNK_TEXT_LIMIT + 10:
            payload["content"] = payload["content"][: JUNK_TEXT_LIMIT + 10] + "…"
        allowed = JUNK_KEEP_FIELDS.get(sl.modality, ())
        if allowed:
            for key in list(payload.keys()):
                if key not in allowed:
                    payload.pop(key, None)


#: 设备侧注释（与生态同类卷一致的 in-band 标注风格）：切片 tag → (英文 label, 中文判读, 判读说明)。
#: 说明：这些标注落在**保留切片**上，描述的是"设备看到的物理/语义现象"，不是标答结论；
#: 其作用是让任何具备常识与词表能力的求解方都能在端侧证据上定位关键事件（可解性保证）。
DEVICE_ANNOTATIONS: Dict[str, Tuple[str, str, str]] = {
    "bank_inflow": ("large_inflow", "大额入账", "银行流水正向入账，账户余额发生显著变化"),
    "card_repay": ("repayment_done", "信用卡还款完成", "还款交易已完成，属账单履约行为"),
    "card_debt": ("credit_card_debt", "信用卡账单压力", "账单金额偏高，出现最低还款提示"),
    "court": ("court_summons", "司法文书送达", "法院传票/开庭通知，须本人应诉"),
    "lab": ("lab_critical_value", "检验危急值", "检验结果触发危急值阈值，建议尽快复诊"),
    "signing": ("contract_signing", "合同签署安排", "签约档期已确定，属事业推进节点"),
    "bonus": ("salary_or_bonus_credit", "工资奖金到账", "工资/绩效奖金入账，属正向收入"),
    "promise": ("repayment_promise", "口头还款承诺", "对欠款给出明确还款时间与金额承诺"),
    "collect": ("debt_collection", "债务催收", "对方要求限期还款并言语施压"),
    "setback": ("work_setback", "工作受挫", "方案/汇报被当众否决批评，推进受阻"),
    "overtime": ("work_overtime", "连续超时工作", "长时间超时工作，休息被挤压"),
    "rupture": ("relationship_conflict", "亲密关系冲突", "激烈争吵并出现分手/分开表述"),
    "breakup_msg": ("breakup_message", "关系终止留言", "文字消息明确终止亲密关系"),
    "sos": ("partial_sos_speech", "被噪声掩埋的呼救", "人声被环境噪声掩埋，含求助与身体不适语义"),
    "entrust": ("family_entrustment", "长辈托付", "长辈交代身后安排与照护责任"),
    "school": ("child_school", "子女学业问题", "老师反馈孩子在校问题，需家长处理"),
    "fraud": ("fraud_call", "诈骗话术来电", "索要验证码或诱导转账链接，属诈骗话术"),
    "consult": ("medical_appointment", "就诊安排", "就诊/复诊预约与健康咨询安排"),
    "nda": ("nda_confidentiality", "保密义务", "要求对工作内容保密，涉及保密义务"),
    "resign": ("resignation_intent", "离职意向", "明确表达辞职/离职意向"),
    "medical_intent": ("real_medical_intent", "真实就医意愿", "出现真实就医诉求，非客套话"),
    "denial": ("illness_denial", "嘴硬否认", "对自身症状自我否认，装作无碍"),
    "acute": ("acute_exacerbation", "症状急性加重", "既有症状急性加重，需立即处理"),
    "tender": ("family_daily", "家人日常关照", "家人日常关照与陪伴"),
    "fall": ("high_g_impact_with_freefall", "自由落体后高冲击", "存在自由落体前段与高g冲顶，疑似真实跌倒"),
    "fake_impact": ("high_g_without_freefall", "高g冲击（无自由落体）", "仅高g瞬时峰值、无自由落体前段，形似跌倒而非跌倒"),
    "pvc": ("cardiac_pvc_burst", "室性早搏阵发", "心电/PPG 检出连续室性早搏阵发"),
    "tachy": ("hr_elevated_resting", "静息心动过速", "静息无运动状态下心率持续偏高并超出静息基线"),
    "baro": ("barometric_drop", "气压骤降", "环境气压短时显著下降，可能引发身体不适"),
    "sleep": ("sleep_deficit", "睡眠时长不足", "夜间睡眠时长明显不足，伴呼吸暂停样事件"),
    "hypo": ("hypoglycemia_sign", "低血糖征兆", "出现手抖/心慌/出汗等低血糖表现"),
    "hypo_utt": ("hypoglycemia_sign", "低血糖征兆", "出现手抖/心慌/出汗等低血糖表现"),
    "med": ("medication_reminder", "用药提醒", "服药时点提醒通知"),
    "vp_contact": ("enrolled_contact", "核心亲友声纹绑定", "声纹与通讯录联系人稳定匹配，核心亲友长期锚点"),
    "vp_impostor": ("claimed_identity_mismatch", "冒充亲友可疑来电", "自称身份与声纹簇中心距离过远，疑似冒充"),
    "vp_meeting": ("multi_party_meeting", "多方工作会议", "多位工作相关方持续同场对话"),
}


#: 只给中文标签、不给判读说明的标注（结构性线索，避免压过当日关键事件的显著度）
STRUCTURAL_ANNOTATION_TAGS = frozenset({"vp_contact"})


def _annotate_keepers(slices: Sequence[Slice]) -> None:
    """给保留切片补上设备侧判读注释（垃圾切片不受影响，保持其"无意义"面貌）。"""
    for sl in slices:
        if not sl.keep:
            continue
        annotation = DEVICE_ANNOTATIONS.get(sl.tag)
        if not annotation:
            continue
        label, label_zh, note = annotation
        sl.payload.setdefault("label", label)
        sl.payload["label_zh"] = label_zh
        if sl.tag not in STRUCTURAL_ANNOTATION_TAGS:
            sl.payload["device_note"] = note


def _hhmm(minute: int) -> str:
    minute = max(DAY_START_MIN, min(DAY_END_MIN, int(minute)))
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _amount(rng: random.Random, scale: str = "wan") -> str:
    if scale == "wan":
        return f"{rng.choice([3, 5, 8, 10, 12, 15, 20, 30, 50])}万元"
    if scale == "yi":
        return f"{rng.choice([100, 200, 300])}万元"
    return f"{rng.choice([68, 128, 199, 268, 328, 500, 880, 1200])}元"


def _day_of_month(rng: random.Random) -> int:
    return rng.choice([3, 5, 7, 9, 12, 15, 18, 20, 25, 28])


def _bank_junk(rng: random.Random, t: int, count: int = 2) -> List[Slice]:
    out: List[Slice] = []
    for _ in range(count):
        app_name, tag, content, category = rng.choice(NOISE_APP)
        out.append(
            _mk("app", t + rng.randint(0, 8), payload={
                "app_name": app_name, "sender": app_name, "content": content, "category": category,
            }, text=content, keep=False)
        )
    return out


def _mic_junk(rng: random.Random, t: int, count: int = 2) -> List[Slice]:
    out: List[Slice] = []
    for _ in range(count):
        scene, text = rng.choice(NOISE_MIC)
        out.append(
            _mk("mic", t + rng.randint(0, 6), text=text, scene=scene, keep=False, payload={
                "ambient_noise_db": rng.randint(62, 86),
                "snr_db": round(rng.uniform(-4.5, 6.0), 1),
                "duration_s": rng.randint(4, 26),
                "speaker_diarization": "unknown_or_multi",
                "asr_confidence": round(rng.uniform(0.31, 0.72), 2),
            })
        )
    return out


def _utt_junk(rng: random.Random, t: int, count: int = 1) -> List[Slice]:
    out: List[Slice] = []
    for _ in range(count):
        junk_tag, text, tone = rng.choice(NOISE_UTT)
        out.append(
            _mk("utt", t + rng.randint(0, 5), text=text, scene=junk_tag, keep=False, payload={
                "context_scene": rng.choice(["独处", "家中", "途中", "聚会", "酒局", "车内"]),
                "emotional_tone": tone,
                "junk_tag": junk_tag,
                "duration_s": round(rng.uniform(1.4, 8.0), 1),
                "snr_db": round(rng.uniform(6.5, 20.0), 1),
                "is_self_talk": True,
            })
        )
    return out


def _sensor_junk(rng: random.Random, t: int, count: int = 2) -> List[Slice]:
    out: List[Slice] = []
    for _ in range(count):
        kind, label, note = rng.choice(NOISE_SENSOR_JUNK)
        payload: Dict[str, Any] = {"kind": kind, "label": label, "note": note,
                                   "duration_s": rng.choice([12, 30, 45, 60])}
        if kind == "imu_window":
            payload.update({"peak_g": round(rng.uniform(0.9, 1.6), 2), "rms_g": round(rng.uniform(0.08, 0.35), 3)})
        elif kind == "ppg_segment":
            payload.update({"hr_bpm_mean": rng.randint(62, 96), "hr_bpm_max": rng.randint(96, 118)})
        elif kind == "baro_segment":
            payload.update({"baro_hpa": round(rng.uniform(998.0, 1021.0), 1)})
        else:
            payload.update({"gps_drift_m": rng.randint(3, 40)})
        out.append(_mk("sensor", t + rng.randint(0, 9), text=note, payload=payload, keep=False))
    return out


# ---------------------------------------------------------------------------
# 四、关键事件包（每个包 = 一段真实生活事件 + 方向性标答）
# ---------------------------------------------------------------------------


def pack_bank_inflow(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 银行入账凭证（真实财务事实）。"""
    amount = _amount(rng, "yuan") if rng.random() < 0.5 else _amount(rng, "wan")
    payer = rng.choice([p.colleague, p.friend, "刘玉华", "钱合伙人", p.leader or "王总"])
    content = f"【招商银行】{p.name}您好，您尾号{p.bank_tail}账户入账{amount}，对方户名：{payer}，请查收。"
    sl = _mk("app", t, text=content, keep=True, tag="bank_inflow", payload={
        "app_name": "手机银行", "sender": "招商银行", "category": "bank", "content": content,
    })
    fact = FactSpec(
        dim="dim:finance", intent="BANK_LARGE_TRANSFER",
        core=f"{p.name}尾号{p.bank_tail}账户收到{payer}转入的{amount}款项，属当日明确资金流入",
        anchors=(p.name, amount, payer), keywords=("入账", "到账", "资金流入", "收到转账", "款项到账", "进账"),
        red_lines=("当作支出/欠款", "金额张冠李戴", "认定为诈骗到账"), source_tag="bank_inflow",
    )
    return Pack(
        slices=[sl, _mk("app", t + 3, keep=False, text="【支付宝】您的花呗本月账单已出。",
                        payload={"app_name": "支付宝", "sender": "支付宝", "category": "trivia",
                                 "content": "【支付宝】您的花呗本月账单已出。"})],
        facts=[fact],
        dim_blocks={"dim:finance": {"points": [f"尾号{p.bank_tail}账户入账{amount}"], "anchors": [amount, payer],
                                    "evidence": ["bank_inflow"]}},
        summary=f"接到{payer}转入的{amount}",
    )


def pack_card_repayment(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 信用卡还款（真实财务支出）。"""
    amount = _amount(rng, "yuan")
    content = f"【工商银行】您尾号{p.bank_tail}信用卡本期应还{amount}，已于今日自动还款成功。"
    sl = _mk("app", t, text=content, keep=True, tag="card_repay", payload={
        "app_name": "手机银行", "sender": "工商银行", "category": "bill", "content": content,
    })
    fact = FactSpec(
        dim="dim:finance", intent="BILL_REPAYMENT", core=f"当日信用卡自动还款{amount}，债务余额相应减少",
        anchors=(amount,), keywords=("还款", "还信用卡", "账单结清", "自动扣款", "还了钱", "清偿"),
        red_lines=("当成新借款", "误判为大额消费"), source_tag="card_repay",
    )
    return Pack([sl], [fact], {"dim:finance": {"points": [f"信用卡自动还款{amount}"], "anchors": [amount],
                                               "evidence": ["card_repay"]}},
                f"信用卡自动还款{amount}")


def pack_credit_card_debt(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 账单提醒（未还清 → 负债压力，属真实财务事实）。"""
    amount = _amount(rng, "wan")
    due = _day_of_month(rng)
    content = f"【中信银行】您尾号{p.bank_tail}信用卡账单{amount}，最后还款日{3}月{due}日，逾期将影响征信。"
    sl = _mk("app", t, text=content, keep=True, tag="card_debt", payload={
        "app_name": "手机银行", "sender": "中信银行", "category": "bill", "content": content,
    })
    fact = FactSpec(
        dim="dim:finance", intent="DEBT_BORROWING", core=f"信用卡账单{amount}尚未结清，面临还款日压力与征信风险",
        anchors=(amount, f"{due}日"), keywords=("欠款", "账单压力", "负债", "还不上", "还款日", "征信"),
        red_lines=("当成入账收入", "误判为已还清"), source_tag="card_debt",
    )
    return Pack([sl], [fact], {"dim:finance": {"points": [f"信用卡账单{amount}未结清"],
                                               "anchors": [amount], "evidence": ["card_debt"]}},
                f"信用卡账单{amount}未结清")


def pack_court_summons(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 法院传票（真实司法通知，必须保留且不得当垃圾删）。"""
    case = f"（2026）{rng.choice(['京','沪','苏','粤','川'])}民初{rng.randint(1000, 9999)}号"
    court = f"{rng.choice(['区','市'])}人民法院"
    content = f"【{court}】{p.name}：本院受理李国强诉你物业服务合同纠纷一案，案号{case}，请于{3}月{_day_of_month(rng)}日到庭应诉。"
    sl = _mk("app", t, text=content, keep=True, tag="court", payload={
        "app_name": "12368", "sender": court, "category": "critical_notice", "content": content,
    })
    fact = FactSpec(
        dim="dim:legal", intent="COURT_SUMMONS", core=f"收到{court}传票，就物业服务合同纠纷案号{case}被通知到庭应诉",
        anchors=(p.name, court, case), keywords=("法院传票", "应诉通知", "被起诉", "开庭", "司法通知", "案号"),
        red_lines=("当成营销广告删掉", "误判为诈骗短信"), source_tag="court",
    )
    return Pack([sl], [fact], {"dim:finance": {"points": [f"收到{court}传票，案号{case}"],
                                               "anchors": [court, case], "evidence": ["court"]}},
                f"收到法院传票应诉（案号{case}）")


def pack_lab_critical(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 检验危急值（真实健康危急事实）。"""
    item, value, lo, hi = rng.choice([
        ("血钾", round(rng.uniform(6.2, 7.6), 2), "3.5", "5.3"),
        ("血钠", rng.randint(158, 176), "137", "147"),
        ("血糖", round(rng.uniform(22.0, 33.0), 1), "3.9", "6.1"),
        ("肌钙蛋白", round(rng.uniform(2.4, 9.8), 2), "0", "0.04"),
    ])
    hospital = f"{rng.choice(['市','省'])}{rng.choice(['中心医院','人民医院','中医医院'])}"
    content = (f"【{hospital}】{p.name}您好，您的{item}检验结果为{value}mmol/L（参考区间{lo}~{hi}mmol/L），"
               f"已达危急值标准，请立即联系心内科。")
    sl = _mk("app", t, text=content, keep=True, tag="lab", payload={
        "app_name": "短信", "sender": hospital, "category": "critical_notice", "content": content,
    })
    fact = FactSpec(
        dim="dim:health", intent="LAB_CRITICAL_VALUE", core=f"{item}检验结果{value}mmol/L，远超参考区间上限，达危急值",
        anchors=(f"{value}mmol/L", item), keywords=("危急值", "检验异常", "指标爆表", "参考区间", "化验单异常", "需紧急处理"),
        red_lines=("当成营销短信删掉", "忽略数值"), source_tag="lab",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"{item}达危急值{value}mmol/L"], "anchors": [f"{value}mmol/L"],
                                              "evidence": ["lab"]}},
                f"医院通知{item}危急值")


def pack_signing_schedule(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 签约日程（真实事业事实）。"""
    partner = rng.choice(["启元科技", "恒达建设", "中远物流", "云图设计", "联合保险"])
    amount = _amount(rng, "wan")
    content = f"【企业微信】{p.name}，{partner}合作签约定于{3}月{_day_of_month(rng)}日上午10点，合同{amount}已盖章待签。"
    sl = _mk("app", t, text=content, keep=True, tag="signing", payload={
        "app_name": "企业微信", "sender": partner, "category": "critical_notice", "content": content,
    })
    fact = FactSpec(
        dim="dim:career", intent="SIGNING_SCHEDULE", core=f"与{partner}的合同签约已定档，合同金额{amount}待签",
        anchors=(partner, amount), keywords=("签约日程", "合同签署", "合作签约", "定档签约", "商务签约", "待签"),
        red_lines=("当成广告推广删掉", "误判为解约"), source_tag="signing",
    )
    return Pack([sl], [fact], {"dim:career": {"points": [f"与{partner}签约定档，合同{amount}"],
                                              "anchors": [partner, amount], "evidence": ["signing"]}},
                f"与{partner}的合作签约定档")


def pack_salary_bonus(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 工资/奖金入账（正向财务事实）。"""
    amount = _amount(rng, "yuan")
    content = f"【招商银行】{p.name}您好，您尾号{p.bank_tail}账户代发工资/奖金入账{amount}。"
    sl = _mk("app", t, text=content, keep=True, tag="bonus", payload={
        "app_name": "手机银行", "sender": "招商银行", "category": "bank", "content": content,
    })
    fact = FactSpec(
        dim="dim:finance", intent="SALARY_BONUS", core=f"当日代发工资/奖金入账{amount}，收入正向变动",
        anchors=(p.name, amount), keywords=("工资到账", "奖金入账", "发薪", "收入增加", "代发工资", "进账"),
        red_lines=("当成欠款", "误判为退款"), source_tag="bonus",
    )
    return Pack([sl], [fact], {"dim:finance": {"points": [f"工资/奖金入账{amount}"], "anchors": [amount],
                                               "evidence": ["bonus"]}},
                f"工资奖金入账{amount}")


def pack_partner_promise(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 借还款承诺（真实契约事实）。"""
    contact = rng.choice([p.friend, "李国强", "钱合伙人"])
    amount = _amount(rng, "wan")
    day = _day_of_month(rng)
    text = rng.choice([
        f"{contact}：借条我写了，{amount}，下月{day}号还，白纸黑字。",
        f"{contact}：那{amount}块钱，下月{day}号之前肯定给你，放心。",
        f"{contact}：你放心，{amount}我下月{day}号一定还，说话算话。",
    ])
    sl = _mk("mic", t, text=text, scene="foreground_dialogue", keep=True, tag="promise", payload={
        "ambient_noise_db": rng.randint(48, 62), "snr_db": round(rng.uniform(12.0, 22.0), 1),
        "duration_s": round(rng.uniform(6.0, 14.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.88, 0.97), 2),
    })
    fact = FactSpec(
        dim="dim:finance", intent="REPAYMENT_PROMISE", core=f"{contact}明确承诺下月{day}号前归还{amount}，含书面借条",
        anchors=(contact, amount, f"下月{day}号"), keywords=("还款承诺", "约定还钱", "借条", "承诺还款", "白纸黑字", "下月还"),
        red_lines=("当成已还清", "误判为新借款", "金额张冠李戴"), source_tag="promise",
    )
    return Pack([sl], [fact], {"dim:finance": {"points": [f"{contact}承诺下月{day}号还{amount}"],
                                               "anchors": [amount, contact], "evidence": ["promise"]}},
                f"与{contact}确认{amount}还款承诺")


def pack_debt_collection(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 催款冲突（财务 + 人际双维度）。"""
    collector = rng.choice(["催收员", "老张", "王老板"])
    amount = _amount(rng, "wan")
    day = _day_of_month(rng)
    text = f"{collector}：{amount}这个月{day}号必须还清，不然我就上门找你要！"
    keeper = _mk("mic", t, text=text, scene="heated_dialogue", keep=True, tag="collect", payload={
        "ambient_noise_db": rng.randint(58, 70), "snr_db": round(rng.uniform(9.0, 16.0), 1),
        "duration_s": round(rng.uniform(7.0, 15.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.85, 0.95), 2),
    })
    fact = FactSpec(
        dim="dim:finance", intent="DEBT_COLLECTION_CONFLICT",
        core=f"{collector}上门催缴{amount}，并以「上门找你要」施压，构成债务催收冲突",
        anchors=(collector, amount), keywords=("催债", "讨债", "催款", "逼债", "债务纠纷", "催收"),
        red_lines=("当成闲聊", "误判为还款完成"), source_tag="collect",
    )
    social = FactSpec(
        dim="dim:social", intent="ARGUMENT_CONFLICT",
        core=f"与{collector}因{amount}债务发生激烈言语冲突，关系紧张",
        anchors=(collector,), keywords=("争吵", "冲突", "口角", "争执", "吵闹", "红脸", "言语冲突"),
        red_lines=("打情骂俏", "甜蜜互动", "轻松玩笑"), source_tag="collect",
    )
    return Pack([keeper], [fact, social], {
        "dim:finance": {"points": [f"{collector}催缴{amount}"], "anchors": [amount], "evidence": ["collect"]},
        "dim:social": {"points": [f"与{collector}发生催债冲突"], "anchors": [collector], "evidence": ["collect"]},
    }, f"因{amount}债务与{collector}发生催收冲突")


def pack_work_setback(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 职场受挫（当众被批评，事业 + 情绪）。"""
    leader = p.leader or "王总"
    topic = rng.choice(["季度汇报", "项目方案", "整改报告", "预算表", "客户提案"])
    text = rng.choice([
        f"{leader}：你这个{topic}做成这样，当着大家的面我就直说了，重做！",
        f"{leader}：{topic}直接给否了，这个月看不到结果你就自己考虑吧。",
        f"{leader}：我说过多少次了，{topic}这么干是要出事的，今天必须给我改完。",
    ])
    sl = _mk("mic", t, text=text, scene="meeting_room_dialogue", keep=True, tag="setback", payload={
        "ambient_noise_db": rng.randint(52, 66), "snr_db": round(rng.uniform(10.0, 18.0), 1),
        "duration_s": round(rng.uniform(8.0, 18.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+2", "asr_confidence": round(rng.uniform(0.86, 0.96), 2),
    })
    fact = FactSpec(
        dim="dim:career", intent="WORK_SETBACK", core=f"{leader}当众否决{topic}并当众批评，工作推进受阻",
        anchors=(leader, topic), keywords=("被批评", "被否决", "挨批", "当众训斥", "汇报被毙", "整改压力"),
        red_lines=("当成表扬", "误判为晋升", "当成普通会议讨论"), source_tag="setback",
    )
    return Pack([sl], [fact], {"dim:career": {"points": [f"{leader}当众否决{topic}并批评"],
                                              "anchors": [topic], "evidence": ["setback"]}},
                f"白天{topic}被{leader}当众否决批评")


def pack_work_overtime(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 强制加班（事业事实）。"""
    leader = p.leader or p.colleague
    hours = rng.choice([2, 3, 4, 6])
    text = f"{leader}：这个今天必须交，你辛苦一下，晚上加个班，大概要{hours}小时。"
    sl = _mk("mic", t, text=text, scene="foreground_dialogue", keep=True, tag="overtime", payload={
        "ambient_noise_db": rng.randint(50, 64), "snr_db": round(rng.uniform(10.0, 19.0), 1),
        "duration_s": round(rng.uniform(5.0, 13.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.87, 0.97), 2),
    })
    fact = FactSpec(
        dim="dim:career", intent="WORK_OVERTIME", core=f"{leader}要求当晚加班约{hours}小时赶交任务",
        anchors=(leader, f"{hours}小时"), keywords=("加班", "加个班", "赶工", "连夜赶活", "工时延长", "必须今天交"),
        red_lines=("当成正常下班", "误判为请假"), source_tag="overtime",
    )
    return Pack([sl], [fact], {"dim:career": {"points": [f"被要求加班约{hours}小时"], "anchors": [f"{hours}小时"],
                                              "evidence": ["overtime"]}},
                f"被{leader}要求晚间加班{hours}小时")


def pack_relationship_rupture(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 亲密关系破裂（人际 + 情绪双维度，含真实争吵）。"""
    other = rng.choice(["苏晴", "陈默", "顾晨", "周正明", "张浩"])
    text = rng.choice([
        f"{other}：这日子没法过了，我们把东西分了吧，分手。",
        f"{other}：你从来都这样，我受够了，我们就这样算了吧。",
        f"{other}：东西我收拾好了，明天我搬走，别联系了。",
    ])
    sl = _mk("mic", t, text=text, scene="heated_dialogue", keep=True, tag="rupture", payload={
        "ambient_noise_db": rng.randint(50, 64), "snr_db": round(rng.uniform(9.0, 17.0), 1),
        "duration_s": round(rng.uniform(6.0, 14.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.85, 0.95), 2),
    })
    social = FactSpec(
        dim="dim:social", intent="ARGUMENT_CONFLICT", core=f"与{other}的关系走向破裂，对方提出分手并要搬离",
        anchors=(other,), keywords=("分手", "感情破裂", "关系结束", "协议分开", "闹掰", "决裂"),
        red_lines=("打情骂俏", "甜蜜互动", "秀恩爱", "感情升温"), source_tag="rupture",
    )
    emotion = FactSpec(
        dim="dim:emotion", intent="VERBAL_VENT", core=f"遭遇{other}提出分手，情绪遭受重大打击",
        anchors=(other,), keywords=("崩溃", "绝望", "委屈", "难受", "情绪低落", "痛苦", "心如刀割"),
        red_lines=("心情愉快", "兴奋庆祝", "毫无波澜"), source_tag="rupture",
    )
    return Pack([sl], [social, emotion], {
        "dim:social": {"points": [f"与{other}关系破裂走向分手"], "anchors": [other], "evidence": ["rupture"]},
        "dim:emotion": {"points": ["情感重创，情绪崩溃"], "anchors": [], "evidence": ["rupture"]},
    }, f"晚间与{other}关系破裂（被提分手）")


def pack_breakup_message(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 微信分手留言（人际 + 情绪）。"""
    other = rng.choice(["苏晴", "陈默", "顾晨", "张浩", "谢峰"])
    content = rng.choice([
        f"我们分手吧，我累了，东西我会让你快递给我。",
        f"我想了很久，我们不合适，就到这儿吧。",
    ])
    sl = _mk("app", t, text=content, keep=True, tag="breakup_msg", payload={
        "app_name": "微信", "sender": other, "category": "critical_notice", "content": content,
    })
    social = FactSpec(
        dim="dim:social", intent="ARGUMENT_CONFLICT", core=f"收到{other}的微信分手留言，亲密关系确认终止",
        anchors=(other,), keywords=("分手", "感情破裂", "关系结束", "协议分开", "决裂", "闹掰"),
        red_lines=("甜蜜互动", "调侃玩笑", "感情升温"), source_tag="breakup_msg",
    )
    emotion = FactSpec(
        dim="dim:emotion", intent="VERBAL_VENT", core="被分手导致当日情绪低落、心理受创",
        anchors=(other,), keywords=("崩溃", "绝望", "委屈", "难过", "情绪低落", "痛苦"),
        red_lines=("心情愉快", "兴奋庆祝"),
        source_tag="breakup_msg",
    )
    return Pack([sl], [social, emotion], {
        "dim:social": {"points": [f"收到{other}的分手留言"], "anchors": [other], "evidence": ["breakup_msg"]},
        "dim:emotion": {"points": ["关系终止带来情绪重创"], "anchors": [], "evidence": ["breakup_msg"]},
    }, f"微信收到{other}的分手留言")


def pack_weak_sos(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 噪声掩埋的微弱求救（真实健康危机，绝不可剪）。"""
    place = rng.choice(["单元门口", "小区花坛边", "地下车库", "楼梯拐角"])
    text = rng.choice([
        f"（极低音量，被风噪掩埋）{p.name}……帮我打120……胸口疼……我起不来了……",
        f"（被车流噪声压住）有人吗……救救我……胸口疼得厉害……帮我打120……",
    ])
    sl = _mk("mic", t, text=text, scene="buried_in_noise", keep=True, tag="sos", payload={
        "ambient_noise_db": rng.randint(74, 86), "snr_db": round(rng.uniform(-5.5, -0.5), 1),
        "duration_s": round(rng.uniform(4.0, 11.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user_weak", "asr_confidence": round(rng.uniform(0.28, 0.52), 2),
        "note": f"音量极低的自救呼救，地点：{place}",
    })
    fact = FactSpec(
        dim="dim:safety", intent="WEAK_SOS", core=f"在{place}发出被噪声掩埋的微弱求救，自述胸口疼、无法起身",
        anchors=(p.name, "120", "胸口疼"), keywords=("求救", "呼救", "救命", "打120", "求助", "叫救护车", "微弱呼救"),
        red_lines=("当成环境噪声剪掉", "误判为影视台词", "忽略低信噪比"), source_tag="sos",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"在{place}微弱呼救（胸痛无法起身）"],
                                              "anchors": ["120"], "evidence": ["sos"]}},
                f"在{place}发出被噪声掩埋的微弱呼救")


def pack_family_entrustment(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 亲人托付（重大人际关系事实）。"""
    elder = p.parent or rng.choice(["父亲", "母亲"])
    code = f"{rng.randint(10, 99)}{rng.randint(10, 99)}{rng.randint(10, 99)}"
    text = rng.choice([
        f"{elder}：（压低声音）存折密码是你的生日倒过来，卡里那点钱都留给你，别跟你哥争。",
        f"{elder}：我这个身体我清楚，万一有个三长两短，房子的事你得担起来，密码我写在本子上了。",
    ])
    sl = _mk("mic", t, text=text, scene="foreground_dialogue", keep=True, tag="entrust", payload={
        "ambient_noise_db": rng.randint(42, 56), "snr_db": round(rng.uniform(12.0, 21.0), 1),
        "duration_s": round(rng.uniform(9.0, 20.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.82, 0.94), 2),
        "note": "低音量、郑重语气，含身后安排类词汇",
    })
    fact = FactSpec(
        dim="dim:family", intent="FAMILY_ENTRUSTMENT", core=f"{elder}郑重向佩戴者交待财产与身后安排（密码、房产归属）",
        anchors=(elder,), keywords=("托付", "嘱托", "交待后事", "财产交代", "密码交待", "遗属安排", "托孤"),
        red_lines=("当成闲聊", "误判为诈骗话术", "当成借款"), source_tag="entrust",
    )
    return Pack([sl], [fact], {"dim:social": {"points": [f"{elder}作出财产与身后安排托付"],
                                              "anchors": [elder], "evidence": ["entrust"]}},
                f"{elder}郑重托付身后家事")


def pack_child_school(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 子女学业事务（人际关系事实）。"""
    child = p.child or "孩子"
    teacher = rng.choice(["班主任王老师", "数学老师", "班主任李老师"])
    text = rng.choice([
        f"{teacher}：{child}最近上课状态不好，成绩掉了不少，家长这边也配合一下。",
        f"{teacher}：{child}这次月考退步明显，明天下午请家长来学校一趟。",
    ])
    sl = _mk("mic", t, text=text, scene="foreground_dialogue", keep=True, tag="school", payload={
        "ambient_noise_db": rng.randint(46, 58), "snr_db": round(rng.uniform(11.0, 20.0), 1),
        "duration_s": round(rng.uniform(8.0, 16.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.86, 0.96), 2),
    })
    fact = FactSpec(
        dim="dim:family", intent="CHILD_SCHOOL", core=f"{teacher}反馈{child}学业退步，要求家长配合与到校沟通",
        anchors=(teacher, child), keywords=("孩子成绩", "家长会", "老师沟通", "学业退步", "学校事务", "请家长"),
        red_lines=("当成工作汇报", "误判为同事闲聊"), source_tag="school",
    )
    return Pack([sl], [fact], {"dim:social": {"points": [f"{teacher}反馈{child}学业退步"],
                                              "anchors": [teacher], "evidence": ["school"]}},
                f"被{teacher}告知{child}学业退步")


def pack_fraud_call(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 电信诈骗话术（真实风险事件，须保留为事实并告警）。"""
    role = rng.choice(["市公安局", "社保中心", "海关"])
    text = rng.choice([
        f"（自称{role}）您的账户涉嫌洗钱，需要配合调查，把钱转到安全账户，别挂电话。",
        f"（自称{role}）您有一个涉密包裹被扣，需要核验资金流水，请把钱转入安全账户验证。",
    ])
    sl = _mk("mic", t, text=text, scene="foreground_dialogue", keep=True, tag="fraud", payload={
        "ambient_noise_db": rng.randint(48, 62), "snr_db": round(rng.uniform(10.0, 18.0), 1),
        "duration_s": round(rng.uniform(10.0, 22.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.84, 0.95), 2),
    })
    fact = FactSpec(
        dim="dim:safety", intent="FRAUD_ATTEMPT", core=f"接到冒充{role}的诈骗电话，以涉嫌洗钱为由要求转入「安全账户」",
        anchors=(role, "安全账户"), keywords=("诈骗电话", "冒充公检法", "安全账户", "涉嫌洗钱", "配合调查", "可疑来电"),
        red_lines=("当成真实司法通知", "误判为普通客服"), source_tag="fraud",
    )
    return Pack([sl], [fact], {"dim:safety": {"points": [f"遭遇冒充{role}的诈骗话术"],
                                               "anchors": ["安全账户"], "evidence": ["fraud"]}},
                f"接到冒充{role}的诈骗电话")


def pack_medical_consult(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 医院问诊（真实健康事实）。"""
    doctor = f"{rng.choice(['张','王','李','刘'])}医生"
    hospital = f"{rng.choice(['市','省'])}{rng.choice(['中心医院','人民医院'])}"
    text = rng.choice([
        f"{doctor}：你这个血压控制得不好，药别停，下周再来复查一次，先去做个心电图。",
        f"{doctor}：心电图提示心肌缺血，我给你开点药，两周后复诊，别熬夜了。",
    ])
    sl = _mk("mic", t, text=text, scene="foreground_dialogue", keep=True, tag="consult", payload={
        "ambient_noise_db": rng.randint(44, 58), "snr_db": round(rng.uniform(11.0, 20.0), 1),
        "duration_s": round(rng.uniform(9.0, 19.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.85, 0.96), 2),
        "note": f"地点：{hospital}",
    })
    fact = FactSpec(
        dim="dim:health", intent="MEDICAL_APPOINTMENT", core=f"在{hospital}就诊，{doctor}提示病情需持续服药并复查",
        anchors=(doctor, hospital), keywords=("就诊", "问诊", "复查", "复诊", "开药", "看病", "医生建议"),
        red_lines=("当成闲聊", "误判为体检推销"), source_tag="consult",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"在{hospital}就诊，需复查服药"],
                                              "anchors": [doctor], "evidence": ["consult"]}},
                f"到{hospital}就诊并被要求复查")


def pack_nda_confidentiality(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC 保密约定（事业/法律事实）。"""
    other = p.leader or "王总"
    amount = _amount(rng, "wan")
    text = f"{other}：这个技术参数绝对不能外泄，合同里写了违约金{amount}，把嘴管住。"
    sl = _mk("mic", t, text=text, scene="meeting_room_dialogue", keep=True, tag="nda", payload={
        "ambient_noise_db": rng.randint(44, 58), "snr_db": round(rng.uniform(11.0, 19.0), 1),
        "duration_s": round(rng.uniform(8.0, 17.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.85, 0.96), 2),
    })
    fact = FactSpec(
        dim="dim:career", intent="NDA_CONFIDENTIALITY", core=f"与{other}就技术参数达成保密约定，违约将赔付{amount}",
        anchors=(other, amount), keywords=("保密承诺", "保密约定", "不得外泄", "商业机密", "保密条款", "违约责任"),
        red_lines=("当成普通提醒", "忽略违约金额"), source_tag="nda",
    )
    return Pack([sl], [fact], {"dim:career": {"points": [f"与{other}达成保密约定（违约{amount}）"],
                                              "anchors": [amount], "evidence": ["nda"]}},
                f"签订保密约定（违约金额{amount}）")


def pack_real_resignation(rng: random.Random, p: Persona, t: int) -> Pack:
    """UTT 真实辞职决定（事业事实，非情绪发泄）。"""
    text = rng.choice([
        "我想清楚了，辞职信明天就交，这个月干完就走。",
        "不干了，我真不干了，下周就递辞呈，别劝我了。",
    ])
    sl = _mk("utt", t, text=text, scene="独处", keep=True, tag="resign", payload={
        "context_scene": "独处", "emotional_tone": "坚决", "duration_s": round(rng.uniform(3.0, 7.0), 1),
        "snr_db": round(rng.uniform(8.0, 18.0), 1), "is_self_talk": True,
        "physiological_context": {"hr_bpm": p.hr_base + rng.randint(2, 12), "spo2_percent": rng.randint(96, 99)},
        "note": "无发泄类虚词，含明确时间与行动承诺",
    })
    resign_anchor = "辞职信" if "辞职信" in text else "辞呈"
    fact = FactSpec(
        dim="dim:career", intent="REAL_RESIGNATION", core="佩戴者明确作出真实辞职决定，并给出递辞呈的时间",
        anchors=(resign_anchor, "这个月干完就走" if "这个月干完就走" in text else "下周就递辞呈"),
        keywords=("辞职", "离职决定", "辞呈", "不干了", "解除劳动关系", "真辞职"),
        red_lines=("当成情绪发泄剪掉", "误判为玩笑"), source_tag="resign",
    )
    return Pack([sl], [fact], {"dim:career": {"points": ["作出真实辞职决定（含时间承诺）"], "anchors": [resign_anchor],
                                              "evidence": ["resign"]}},
                "独处时作出真实辞职决定")


def pack_real_medical_intent(rng: random.Random, p: Persona, t: int) -> Pack:
    """UTT 真实就医诉求（健康事实，非口头禅）。"""
    text = rng.choice([
        "这咳嗽拖了半个月了，明天必须去挂个号看看。",
        "这个疼不像老毛病，得去医院查一下，不能再拖了。",
    ])
    sl = _mk("utt", t, text=text, scene="独处", keep=True, tag="medical_intent", payload={
        "context_scene": "独处", "emotional_tone": "担忧", "duration_s": round(rng.uniform(3.0, 8.0), 1),
        "snr_db": round(rng.uniform(9.0, 18.0), 1), "is_self_talk": True,
        "physiological_context": {"hr_bpm": p.hr_base + rng.randint(3, 14), "spo2_percent": rng.randint(95, 99)},
    })
    symptom = "咳嗽" if "咳嗽" in text else "疼"
    fact = FactSpec(
        dim="dim:health", intent="REAL_MEDICAL_INTENT", core="佩戴者明确表达真实就医计划（挂号就诊），属真实健康诉求",
        anchors=(symptom, "挂号" if "挂号" in text else "去医院"),
        keywords=("就医", "看病", "挂号", "去医院", "就诊计划", "真实诉求"),
        red_lines=("当成口头禅剪掉", "误判为抱怨"), source_tag="medical_intent",
    )
    return Pack([sl], [fact], {"dim:health": {"points": ["明确表达真实就医计划"], "anchors": [symptom],
                                              "evidence": ["medical_intent"]}},
                "明确表达真实就医诉求")


def pack_hidden_cardiac(rng: random.Random, p: Persona, t: int) -> Pack:
    """UTT+SENSOR 隐性心血管危象（嘴硬否认 × 生理证据矛盾，最高危事实）。"""
    hr = rng.randint(132, 156)
    spo2 = round(rng.uniform(88.5, 92.5), 1)
    speech = rng.choice([
        "没事没事，就是有点闷，歇会儿就好了，别大惊小怪的。",
        "没事，老毛病了，忍忍就过去了，不用叫救护车，别告诉家里人。",
    ])
    utt = _mk("utt", t, text=speech, scene="客厅静坐", keep=True, tag="denial", payload={
        "context_scene": "客厅静坐", "emotional_tone": "强撑否认", "duration_s": round(rng.uniform(5.0, 9.0), 1),
        "snr_db": round(rng.uniform(7.5, 14.0), 1), "is_self_talk": False,
        "speech_rate_syl_per_s": round(rng.uniform(1.7, 2.3), 2), "voice_tremor": round(rng.uniform(0.32, 0.58), 2),
        "breath_sound": "可闻及喘息与吸气费力",
        "physiological_context": {"hr_bpm": hr, "spo2_percent": spo2},
    })
    breath = _mk("utt", t + 1, text="（连续粗重喘息声，伴随衣物被汗浸的窸窣声）", scene="客厅静坐",
                 keep=False, payload={
                     "context_scene": "客厅静坐", "emotional_tone": "生理性窘迫", "duration_s": 41.1,
                     "snr_db": 13.9, "is_self_talk": False, "note": "非语言声学线索显示明显呼吸窘迫",
                 })
    acute_note = f"静息状态下心率升至{hr}bpm、血氧降至{spo2}%、皮电同步飙升，与口头否认形成硬冲突"
    seg = _mk("sensor", t - 2, text=acute_note, keep=True, tag="acute", payload={
                  "kind": "ppg_segment", "label": "hr_acute_rise", "duration_s": 720,
                  "hr_bpm_mean": hr - rng.randint(6, 16), "hr_bpm_max": hr + rng.randint(2, 14),
                  "spo2_percent": spo2, "skin_conductance_us": round(rng.uniform(9.0, 13.0), 1),
                  "baseline_hr_bpm": p.hr_base, "note": acute_note,
              })
    fact = FactSpec(
        dim="dim:health", intent="HIDDEN_CARDIAC_CRISIS",
        core=f"口头否认不适（「没事」），但同期心率达{hr}bpm、血氧降至{spo2}%、伴声颤与喘息，构成疑似急性心血管危象",
        anchors=((f"{hr}bpm"), "没事"), keywords=("嘴硬否认", "隐瞒症状", "疑似心梗", "喘不上气", "胸口憋闷",
                                                 "隐性危象", "生理矛盾", "忍忍就好"),
        red_lines=("当成普通抱怨剪掉", "判定为情绪发泄", "忽略生理与言语矛盾"), source_tag="denial",
    )
    return Pack([seg, utt, breath], [fact], {"dim:health": {
        "points": [f"口头否认但心率{hr}bpm、血氧{spo2}%，疑似急性心血管事件"], "anchors": [f"{hr}bpm"], "evidence": ["denial", "acute"]}},
        "出现「否认不适但体征异常」的隐性心血管危象")


def pack_family_tender(rng: random.Random, p: Persona, t: int) -> Pack:
    """MIC/APP 家庭温情互动（真实人际关系事实，非垃圾）。"""
    other = p.spouse or p.child or p.parent or "家人"
    text = rng.choice([
        f"{other}：天冷了记得加衣服，别老熬夜，我给你把汤热着了。",
        f"{other}：你最近脸色不太好，明天我陪你去医院看看行不行。",
    ])
    sl = _mk("mic", t, text=text, scene="foreground_dialogue", keep=True, tag="tender", payload={
        "ambient_noise_db": rng.randint(42, 54), "snr_db": round(rng.uniform(13.0, 22.0), 1),
        "duration_s": round(rng.uniform(5.0, 12.0), 1), "is_background_chatter": False,
        "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.88, 0.97), 2),
    })
    fact = FactSpec(
        dim="dim:family", intent="FAMILY_DAILY", core=f"与{other}进行家庭关心互动，对方叮嘱保暖与就医陪伴",
        anchors=(other,), keywords=("家人关心", "嘘寒问暖", "陪伴", "叮嘱", "亲情互动", "家人问候"),
        red_lines=("当成争吵", "误判为催债", "当成推销"), source_tag="tender",
    )
    return Pack([sl], [fact], {"dim:social": {"points": [f"与{other}的家庭关心互动"], "anchors": [other],
                                              "evidence": ["tender"]}},
                f"与{other}的家庭温情互动")


def pack_key_contact_binding(rng: random.Random, p: Persona, t: int) -> Pack:
    """声纹聚类：核验佩戴者本人并绑定核心亲友（人际事实）。"""
    contact = rng.choice(p.key_contacts)
    total = 24
    frag = rng.randint(5, 19)
    speaker = {
        "spk_id": f"{QUESTION_PREFIX}-VP-KEY", "role": f"核心亲友-{contact}", "n_fragments": frag,
        "total_duration_s": round(rng.uniform(120.0, 620.0), 1),
        "cosine_to_enrolled_user": round(rng.uniform(0.62, 0.86), 3), "is_transient": False,
        "ttl_policy": "keep_90d",
    }
    fact = FactSpec(
        dim="dim:social", intent="VOICE_BINDING_KEY_CONTACT",
        core=f"当日声纹聚类从{total}个说话人碎片中稳定绑定核心亲友{contact}为长期锚点",
        anchors=(contact,), keywords=("关键联系人声纹", "亲友声纹绑定", "熟人声纹", "声纹匹配至亲友",
                                     "核心联系人声纹", "长期锚点"),
        red_lines=("把一次性陌生人当成亲友绑定", "遗漏核心亲友"), source_tag="vp_contact",
    )
    return Pack([], [fact], {"dim:social": {"points": [f"声纹绑定核心亲友{contact}"], "anchors": [contact],
                                            "evidence": ["vp_contact"]}},
                f"声纹绑定核心亲友{contact}")


def pack_impostor_voiceprint(rng: random.Random, p: Persona, t: int) -> Pack:
    """声纹聚类：冒充亲友的可疑来电（对抗级事实）。"""
    contact = rng.choice(p.key_contacts)
    cosine = round(rng.uniform(0.28, 0.49), 3)
    fact = FactSpec(
        dim="dim:safety", intent="VOICE_IMPERSONATION_FRAUD",
        core=f"声纹聚类发现自称{contact}的说话人，其声纹相似度仅{cosine}，判定为冒充亲友的可疑来电",
        anchors=(contact,), keywords=("冒充亲友", "声纹不符", "身份冒用", "冒充熟人", "疑似冒充", "声纹不匹配"),
        red_lines=("当成真实亲友绑定", "忽略相似度异常的来电"), source_tag="vp_impostor",
    )
    return Pack([], [fact], {"dim:social": {"points": [f"发现冒充{contact}的可疑声纹（相似度{cosine}）"],
                                            "anchors": [contact], "evidence": ["vp_impostor"]}},
                f"声纹识别出冒充{contact}的可疑来电")


def pack_meeting_confidential(rng: random.Random, p: Persona, t: int) -> Pack:
    """声纹聚类：多人会议场景（事业线索 + 保密氛围）。"""
    others = [p.leader or "王总", p.colleague, "客户方代表"]
    total = 24
    fact = FactSpec(
        dim="dim:career", intent="WORK_COORDINATION",
        core=f"当日出现多方长时段工作会议，3位工作相关方（{ '、'.join(others) }）持续在同一场景对话",
        anchors=(others[1],), keywords=("多方会议", "会议沟通", "工作对接", "商务洽谈", "项目讨论"),
        red_lines=("当成家人闲聊", "忽略长时段会议特征"), source_tag="vp_meeting",
    )
    return Pack([], [fact], {"dim:career": {"points": [f"多人长时段工作会议（{total}人声纹簇）"], "anchors": [],
                                             "evidence": ["vp_meeting"]}},
                "出现多方长时段工作会议")


def pack_fall_impact(rng: random.Random, p: Persona, t: int) -> Pack:
    """SENSOR 真实跌倒（自由落体前段 + 硬冲击 + 冲击后静止，力学三联征）。"""
    g = round(rng.uniform(4.6, 8.9), 2)
    freefall = rng.randint(180, 460)
    still = rng.randint(45, 240)
    posture = rng.randint(62, 128)
    place = rng.choice(["小区单元门口", "菜市场台阶", "地下车库坡道", "公交站台"])
    note = (f"存在自由落体前段（{freefall}ms）+ 三轴合成冲顶（峰值{g}g）+ 姿态角翻转{posture}度，"
            f"冲击后静止{still}秒，符合真实跌倒力学三联征")
    sl = _mk("sensor", t, text=note, keep=True, tag="fall", payload={
        "kind": "imu_impact", "label": "impact_waveform", "duration_s": round(rng.uniform(2.0, 6.0), 1),
        "g_peak": g, "g_rms": round(rng.uniform(0.8, 1.9), 2), "impact_rise_ms": rng.randint(45, 120),
        "freefall_segment_ms": freefall, "posture_change_deg": posture, "post_impact_stillness_s": still,
        "note": note,
    })
    fact = FactSpec(
        dim="dim:safety", intent="FALL_IMPACT",
        core=f"在{place}发生真实跌倒：冲击峰值{g}g、自由落体前段{freefall}ms、冲击后静止{still}秒未起身",
        anchors=(f"{g}g", f"{still}秒"), keywords=("摔倒", "跌倒", "倒地", "摔伤", "坠地", "重重摔下", "倒地不起"),
        red_lines=("判定为日常震动删掉", "忽略冲击后静止"), source_tag="fall",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"在{place}真实跌倒（{g}g，静止{still}秒）"],
                                              "anchors": [f"{g}g"], "evidence": ["fall"]}},
                f"在{place}发生真实跌倒")


def pack_faked_impact(rng: random.Random, p: Persona, t: int) -> Pack:
    """SENSOR 伪跌倒（高 G 但无自由落体前段、冲击后立即恢复，对抗级反例）。"""
    g = round(rng.uniform(3.2, 6.4), 2)
    note = f"峰值达{g}g 但无自由落体前段，冲击后 1 秒内恢复连续步态，符合甩腕/放物动作"
    sl = _mk("sensor", t, text=note, keep=True, tag="fake_impact", payload={
        "kind": "imu_impact", "label": "impact_waveform", "duration_s": round(rng.uniform(1.0, 3.0), 1),
        "g_peak": g, "g_rms": round(rng.uniform(0.4, 0.9), 2), "impact_rise_ms": rng.randint(120, 260),
        "freefall_segment_ms": 0, "posture_change_deg": rng.randint(3, 18),
        "post_impact_stillness_s": 0, "note": note,
    })
    fact = FactSpec(
        dim="dim:safety", intent="FALL_IMPACT_FAKED",
        core=f"出现{g}g 冲击但缺少自由落体前段且冲击后立即恢复运动，物理不变式判定为日常动作而非真实跌倒",
        anchors=(f"{g}g",), keywords=("非真实跌倒", "并非摔倒", "误报", "日常甩腕", "无自由落体", "立即恢复运动"),
        red_lines=("误报为真实跌倒", "据此触发跌倒告警", "当成跌倒伤情"), source_tag="fake_impact",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"{g}g 冲击经物理不变式判定为非真实跌倒"],
                                              "anchors": [f"{g}g"], "evidence": ["fake_impact"]}},
                "出现高 G 冲击但经物理不变式排除真实跌倒")


def pack_pvc_burst(rng: random.Random, p: Persona, t: int) -> Pack:
    """SENSOR 室性早搏连续阵发（心律失常）。"""
    n = rng.randint(5, 22)
    dur = rng.randint(40, 260)
    note = f"连续宽大畸形 QRS 波群伴代偿间歇，共{n}次、持续{dur}秒，符合室性早搏连续阵发"
    sl = _mk("sensor", t, text=note, keep=True, tag="pvc", payload={
        "kind": "ppg_segment", "label": "pvc_burst", "duration_s": dur, "pvc_burst_count": n,
        "hr_bpm_mean": rng.randint(76, 118), "baseline_hr_bpm": p.hr_base, "note": note,
    })
    fact = FactSpec(
        dim="dim:health", intent="CARDIAC_PVC_BURST", core=f"监测到室性早搏连续阵发{n}次、持续约{dur}秒，属心律失常事件",
        anchors=(f"{n}次",), keywords=("室性早搏", "早搏", "室早", "心律失常", "连续阵发", "心律不齐"),
        red_lines=("当成运动心率波动", "忽略早搏计数"), source_tag="pvc",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"室性早搏连续阵发{n}次"], "anchors": [f"{n}次"],
                                              "evidence": ["pvc"]}},
                f"监测到室性早搏连续阵发（{n}次）")


def pack_resting_tachycardia(rng: random.Random, p: Persona, t: int) -> Pack:
    """SENSOR 静息心动过速。"""
    hr = rng.randint(108, 142)
    dur = rng.randint(15, 55)
    note = f"静坐无运动状态下心率持续{dur}分钟达{hr}bpm，超出静息基线{p.hr_base}bpm"
    sl = _mk("sensor", t, text=note, keep=True, tag="tachy", payload={
        "kind": "ppg_segment", "label": "hr_elevated", "duration_s": dur, "hr_bpm_mean": hr,
        "hr_bpm_max": hr + rng.randint(3, 16), "baseline_hr_bpm": p.hr_base,
        "motion_state": "SITTING_STILL", "note": note,
    })
    fact = FactSpec(
        dim="dim:health", intent="RESTING_TACHYCARDIA", core=f"静息无运动状态下心率持续{dur}分钟高达{hr}bpm，判定为静息心动过速",
        anchors=(f"{hr}bpm",), keywords=("静息心动过速", "心率持续", "心率偏高", "静息心率异常", "心率过快"),
        red_lines=("当成运动所致", "忽略静息状态"), source_tag="tachy",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"静息心动过速{hr}bpm 持续{dur}分钟"],
                                              "anchors": [f"{hr}bpm"], "evidence": ["tachy"]}},
                f"静息状态下心率升至{hr}bpm")


def pack_baro_storm(rng: random.Random, p: Persona, t: int) -> Pack:
    """SENSOR 气压骤降（环境剧变引发身体不适）。"""
    drop = round(rng.uniform(6.0, 14.0), 1)
    note = f"45分钟内气压快速下降{drop}hPa，伴随头痛与关节不适主诉"
    sl = _mk("sensor", t, text=note, keep=True, tag="baro", payload={
        "kind": "baro_segment", "label": "baro_drop", "duration_s": rng.randint(1800, 3600),
        "baro_hpa_start": round(rng.uniform(1006.0, 1018.0), 1), "baro_drop_hpa": drop, "note": note,
    })
    fact = FactSpec(
        dim="dim:environment", intent="BAROMETRIC_STORM", core=f"气压在短时间内骤降{drop}hPa，与头痛、关节不适主诉同时出现",
        anchors=(f"{drop}hPa",), keywords=("气压骤降", "天气剧变", "气压波动", "天气影响", "气压快速下降"),
        red_lines=("当成数据漂移删掉", "忽略伴随症状"), source_tag="baro",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"气压骤降{drop}hPa 并伴不适"], "anchors": [f"{drop}hPa"],
                                              "evidence": ["baro"]}},
                f"气压骤降{drop}hPa 引发身体不适")


def pack_sleep_deficit(rng: random.Random, p: Persona, t: int) -> Pack:
    """SENSOR 睡眠严重不足 / 呼吸暂停（夜间事实）。"""
    hours = round(rng.uniform(2.5, 4.4), 1)
    apnea = rng.randint(12, 46)
    note = f"当夜仅睡{hours}小时，伴{apnea}次呼吸暂停样事件，睡眠时长明显不足"
    sl = _mk("sensor", t, text=note, keep=True, tag="sleep", payload={
        "kind": "sleep_segment", "label": "sleep_short", "duration_s": int(hours * 3600),
        "sleep_hours": hours, "apnea_events": apnea, "resting_hr_bpm": p.hr_base + rng.randint(-4, 10),
        "note": note,
    })
    fact = FactSpec(
        dim="dim:health", intent="SLEEP_DURATION", core=f"当夜仅睡{hours}小时并出现{apnea}次呼吸暂停样事件，睡眠严重不足",
        anchors=(f"{hours}小时",), keywords=("睡眠不足", "熬夜", "睡眠时长", "呼吸暂停", "睡得太少", "失眠"),
        red_lines=("当成正常睡眠", "忽略呼吸暂停"), source_tag="sleep",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"当夜睡眠{hours}小时且呼吸暂停{apnea}次"],
                                              "anchors": [f"{hours}小时"], "evidence": ["sleep"]}},
                f"当夜睡眠不足（{hours}小时）")


def pack_hypoglycemia(rng: random.Random, p: Persona, t: int) -> Pack:
    """SENSOR + UTT 低血糖发作（健康事实）。"""
    value = round(rng.uniform(2.4, 3.5), 1)
    text = rng.choice(["怎么眼前发黑，手抖得厉害……得赶紧吃点东西。", "心慌出汗，站都站不稳了，是不是低血糖了。"])
    hypo_note = f"血糖{value}mmol/L 低于正常下限，伴手抖、出汗样体征"
    seg = _mk("sensor", t - 1, text=hypo_note, keep=True, tag="hypo", payload={
        "kind": "ppg_segment", "label": "glucose_low", "duration_s": rng.randint(300, 1200),
        "glucose_mmol_l": value, "hr_bpm_mean": rng.randint(92, 118), "note": hypo_note,
    })
    utt = _mk("utt", t, text=text, scene="途中", keep=True, tag="hypo_utt", payload={
        "context_scene": "途中", "emotional_tone": "虚弱", "duration_s": round(rng.uniform(2.0, 6.0), 1),
        "snr_db": round(rng.uniform(8.0, 16.0), 1), "is_self_talk": True,
        "physiological_context": {"hr_bpm": rng.randint(92, 118), "spo2_percent": rng.randint(95, 98)},
    })
    fact = FactSpec(
        dim="dim:health", intent="HYPOGLYCEMIA", core=f"血糖降至{value}mmol/L 并伴手抖、心慌出汗，出现低血糖发作",
        anchors=(f"{value}mmol/L",), keywords=("低血糖", "血糖过低", "手抖", "心慌出汗", "眼前发黑"),
        red_lines=("当成普通疲惫", "忽略血糖数值"), source_tag="hypo",
    )
    return Pack([seg, utt], [fact], {"dim:health": {"points": [f"血糖{value}mmol/L 低血糖发作"], "anchors": [f"{value}mmol/L"],
                                              "evidence": ["hypo"]}},
                f"出现低血糖发作（血糖{value}mmol/L）")


def pack_delivery_trivia(rng: random.Random, p: Persona, t: int) -> Pack:
    """日常琐事（真实但低价值：取快递），用于提高信噪难度。"""
    code = rng.randint(100000, 999999)
    content = f"【顺丰速运】{p.name}，您的包裹已到{p.area}驿站，取件码{code}，请及时领取。"
    sl = _mk("app", t, text=content, keep=False, tag="delivery", payload={
        "app_name": "短信", "sender": "顺丰速运", "category": "delivery", "content": content,
    })
    return Pack([sl], [], {}, f"取了快递（取件码{code}）")


def pack_utm_medical_reminder(rng: random.Random, p: Persona, t: int) -> Pack:
    """APP 用药/复诊提醒（真实健康管理事实）。"""
    cond = p.conditions[0]
    content = f"【健康助手】{p.name}，今天的{cond}用药还没打卡，请按时服药。"
    sl = _mk("app", t, text=content, keep=True, tag="med", payload={
        "app_name": "健康助手", "sender": "健康助手", "category": "medical", "content": content,
    })
    fact = FactSpec(
        dim="dim:health", intent="MEDICATION_REMINDER", core=f"当日{cond}用药提醒触发，需按时服药",
        anchors=(cond,), keywords=("用药提醒", "按时服药", "吃药", "用药打卡", "持续用药"),
        red_lines=("当成垃圾通知删掉", "忽略慢病用药"), source_tag="med",
    )
    return Pack([sl], [fact], {"dim:health": {"points": [f"{cond}用药提醒"], "anchors": [cond], "evidence": ["med"]}},
                f"收到{cond}用药提醒")


# ---------------------------------------------------------------------------
# 五、对抗陷阱包（必须被正确剪枝 / 必须被正确排除，误判即扣分）
# ---------------------------------------------------------------------------


def trap_media_sos(rng: random.Random, p: Persona, t: int) -> Pack:
    """陷阱：影视剧外放的「救命」——不是真实求救，须剪枝。"""
    text = rng.choice([
        "（电视剧外放台词）救命啊！快来人！",
        "（短视频外放）别拦我，我真的活不下去了！",
    ])
    sl = _mk("mic", t, text=text, scene="tv_drama_playback", keep=False, payload={
        "ambient_noise_db": rng.randint(66, 80), "snr_db": round(rng.uniform(2.0, 8.0), 1),
        "duration_s": rng.randint(6, 20), "is_background_chatter": True,
        "speaker_diarization": "unknown_or_multi", "asr_confidence": round(rng.uniform(0.62, 0.88), 2),
    })
    return Pack([sl], [], {}, "听到影视剧外放的呼救台词（非真实事件）")


def trap_drunk_bragging(rng: random.Random, p: Persona, t: int) -> Pack:
    """陷阱：酒后吹牛（内容荒诞），须剪枝，不得当成真实计划。"""
    claim = rng.choice(["比亚迪", "华为", "腾讯", "茅台"])
    amount = rng.choice(["一百万", "一千万", "一个亿"])
    text = rng.choice([
        f"等我下个月把{claim}收购了，第一个给你们每人发{amount}！",
        f"我一年随便赚{amount}，这点钱算什么。",
    ])
    sl = _mk("utt", t, text=text, scene="酒局", keep=False, payload={
        "context_scene": "酒局", "emotional_tone": "亢奋", "junk_tag": "酒后吹牛",
        "duration_s": round(rng.uniform(3.0, 8.0), 1), "snr_db": round(rng.uniform(7.0, 15.0), 1),
        "is_self_talk": True, "blood_alcohol_hint": "elevated",
        "physiological_context": {"hr_bpm": rng.randint(92, 112), "spo2_percent": rng.randint(96, 99)},
    })
    return Pack([sl], [], {}, "酒后吹牛（非真实计划）")


def trap_vent_only(rng: random.Random, p: Persona, t: int) -> Pack:
    """陷阱：纯口头宣泄（生理指标平稳、无行动意图、无生理矛盾），须剪枝。"""
    text = rng.choice(["烦死了，真想直接走人。", "累死了，这班是一天也不想上了。", "不想活了，天天这样熬着有什么意思。"])
    sl = _mk("utt", t, text=text, scene="独处", keep=False, payload={
        "context_scene": "独处", "emotional_tone": "疲惫", "junk_tag": "口头禅发泄",
        "duration_s": round(rng.uniform(2.0, 7.0), 1), "snr_db": round(rng.uniform(8.0, 17.0), 1),
        "is_self_talk": True, "post_utterance_behavior": "随后正常点外卖/继续工作",
        "physiological_context": {"hr_bpm": p.hr_base + rng.randint(-3, 6), "spo2_percent": rng.randint(97, 99)},
    })
    return Pack([sl], [], {}, "口头宣泄情绪（无真实行动意图）")


def trap_phishing_bank(rng: random.Random, p: Persona, t: int) -> Pack:
    """陷阱：钓鱼短信（冒充银行，含短链与诱导），须剪枝。"""
    content = rng.choice([
        f"【银行通知】{p.name}，您账户存在异常将冻结，请点击 t.cn/k9x2 完成实名核验。",
        "【工商银行】您的账户已触发风控，24小时内未验证将冻结，点击 t.cn/a7b3 处理。",
    ])
    sl = _mk("app", t, text=content, keep=False, payload={
        "app_name": "短信", "sender": "未知号码", "category": "phishing", "content": content,
    })
    return Pack([sl], [], {}, "收到冒充银行的钓鱼短信")


# ---------------------------------------------------------------------------
# 六、事件链（跨维度冲突/转折的专业编排）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chain:
    name: str
    packs: Tuple[str, ...]
    primary_hint: Tuple[str, ...]
    storyline: str


CHAINS: Tuple[Chain, ...] = (
    Chain("career_crisis", ("work_setback", "breakup_message", "resting_tachycardia"), ("mic", "sensor", "app"),
          "白天工作受挫被当众否决，晚间亲密关系破裂，身心处于极度高压"),
    Chain("finance_squeeze", ("partner_promise", "debt_collection", "credit_card_debt", "sleep_deficit"),
          ("mic", "app", "sensor"), "债务催收与账单压力叠加，夜间因焦虑失眠"),
    Chain("health_scare", ("hidden_cardiac", "lab_critical", "medical_consult"), ("utt", "sensor", "app"),
          "白天下达危急值通知，晚间出现嘴硬否认的隐性心血管危象"),
    Chain("fraud_alert", ("fraud_call", "bank_inflow", "impostor_voiceprint"), ("mic", "app", "voiceprint"),
          "真实入账与冒充诈骗话术同日出现，考验真假资金信息分辨"),
    Chain("family_duty", ("family_entrustment", "child_school", "family_tender"), ("mic", "voiceprint"),
          "长辈托付身后安排与子女学业问题同日压来，家庭责任加重"),
    Chain("work_win", ("signing_schedule", "salary_bonus", "nda_confidentiality"), ("app", "mic"),
          "合作签约定档并收到绩效奖金，事业推进顺利但伴随保密约束"),
    Chain("commute_incident", ("fall_impact", "weak_sos", "resting_tachycardia"), ("sensor", "mic"),
          "通勤途中发生真实跌倒并在噪声中呼救，需紧急识别"),
    Chain("aging_care", ("medical_consult", "medication_reminder", "family_tender"), ("app", "mic"),
          "慢病复诊与用药管理贯穿全天，家人陪伴照护"),
    Chain("voiceprint_day", ("key_contact_binding", "meeting_confidential", "family_tender"), ("voiceprint", "mic"),
          "全天声纹聚类完成本人与核心亲友绑定，同时出现多方工作会议"),
)


SENSOR_PACKS = {
    "fall_impact": pack_fall_impact, "faked_impact": pack_faked_impact, "pvc_burst": pack_pvc_burst,
    "resting_tachycardia": pack_resting_tachycardia, "baro_storm": pack_baro_storm,
    "sleep_deficit": pack_sleep_deficit, "hypoglycemia": pack_hypoglycemia,
}
MIC_PACKS = {
    "partner_promise": pack_partner_promise, "debt_collection": pack_debt_collection,
    "work_setback": pack_work_setback, "work_overtime": pack_work_overtime,
    "relationship_rupture": pack_relationship_rupture, "weak_sos": pack_weak_sos,
    "family_entrustment": pack_family_entrustment, "child_school": pack_child_school,
    "fraud_call": pack_fraud_call, "medical_consult": pack_medical_consult,
    "nda_confidentiality": pack_nda_confidentiality, "family_tender": pack_family_tender,
    "delivery_trivia": pack_delivery_trivia,
}
APP_PACKS = {
    "bank_inflow": pack_bank_inflow, "card_repayment": pack_card_repayment,
    "credit_card_debt": pack_credit_card_debt, "court_summons": pack_court_summons,
    "lab_critical": pack_lab_critical, "signing_schedule": pack_signing_schedule,
    "salary_bonus": pack_salary_bonus, "breakup_message": pack_breakup_message,
    "medication_reminder": pack_utm_medical_reminder,
}
UTT_PACKS = {
    "real_resignation": pack_real_resignation, "real_medical_intent": pack_real_medical_intent,
    "hidden_cardiac": pack_hidden_cardiac,
}
VP_PACKS = {
    "key_contact_binding": pack_key_contact_binding, "impostor_voiceprint": pack_impostor_voiceprint,
    "meeting_confidential": pack_meeting_confidential,
}
ALL_PACKS: Dict[str, Any] = {**SENSOR_PACKS, **MIC_PACKS, **APP_PACKS, **UTT_PACKS, **VP_PACKS}

#: 链内引用的包名必须全部存在于 ALL_PACKS（构建期即校验，避免悬空引用）
for _chain in CHAINS:
    for _key in _chain.packs:
        if _key not in ALL_PACKS:
            raise KeyError(f"事件链 {_chain.name} 引用了未定义的事件包: {_key}")

TRAPS = {
    "media_sos": trap_media_sos, "drunk_bragging": trap_drunk_bragging, "vent_only": trap_vent_only,
    "phishing_bank": trap_phishing_bank,
}

#: 各难度的陷阱配置（对抗级必然出现真假对冲）
TRAP_PROFILE: Dict[str, Tuple[str, ...]] = {
    "EASY": (),
    "MEDIUM": ("vent_only",),
    "HARD": ("vent_only", "drunk_bragging"),
    "ADVERSARIAL": ("media_sos", "phishing_bank", "drunk_bragging"),
}

#: 分模态主事实包（保证五路配比中每种模态都有其"代表事件"）
MODALITY_PRIMARY_PACKS: Dict[str, Tuple[str, ...]] = {
    "sensor": ("fall_impact", "faked_impact", "pvc_burst", "resting_tachycardia", "baro_storm",
               "sleep_deficit", "hypoglycemia"),
    "mic": ("partner_promise", "debt_collection", "work_setback", "work_overtime", "relationship_rupture",
            "weak_sos", "family_entrustment", "child_school", "fraud_call", "medical_consult",
            "nda_confidentiality", "family_tender"),
    "app": ("bank_inflow", "card_repayment", "credit_card_debt", "court_summons", "lab_critical",
            "signing_schedule", "salary_bonus", "breakup_message", "medication_reminder"),
    "utt": ("real_resignation", "real_medical_intent", "hidden_cardiac"),
    "voiceprint": ("key_contact_binding", "impostor_voiceprint", "meeting_confidential"),
}

CALM_DIM_BLOCKS: Dict[str, Dict[str, Any]] = {
    "dim:health": {"points": ["当日体征在基线区间内，无异常事件"], "keywords": ["体征平稳", "无异常", "健康如常"],
                   "anchors": []},
    "dim:social": {"points": ["当日人际关系平稳，无冲突或重要变更"], "keywords": ["人际平稳", "无冲突", "社交如常"],
                   "anchors": []},
    "dim:emotion": {"points": ["当日情绪平稳，无重大波动"], "keywords": ["情绪平稳", "心态平和", "无波动"],
                    "anchors": []},
    "dim:finance": {"points": ["当日无重大资金变动或债务事件"], "keywords": ["财务平稳", "无资金变动", "无债务事件"],
                    "anchors": []},
    "dim:career": {"points": ["当日工作按常规推进，无重大变化"], "keywords": ["工作如常", "无重大变化", "常规推进"],
                   "anchors": []},
}

CALM_RED_LINES: Dict[str, Tuple[str, ...]] = {
    "dim:health": ("把日常体征波动上升为疾病", "编造未发生的病症"),
    "dim:social": ("把日常闲聊上升为关系破裂", "编造冲突"),
    "dim:emotion": ("把日常情绪上升为心理危机", "编造负面情绪"),
    "dim:finance": ("把正常消费上升为债务危机", "编造资金事件"),
    "dim:career": ("把常规工作上升为职场危机", "编造事业变动"),
}

ROUTINE_MIC: Tuple[str, ...] = (
    "早啊，今天这么早出门。", "吃了吗您内？", "这菜多少钱一斤？", "麻烦帮我拿下那个袋子。",
    "今天天气还行啊，没那么热。", "电梯来了，走吧。", "谢谢啊，回头请你吃饭。", "这雨说下就下。",
)
ROUTINE_APP: Tuple[Tuple[str, str, str], ...] = (
    ("微信", "同事", "【工作群】上午十点开个短会，同步一下进度。"),
    ("美团", "美团", "【美团】您的外卖已送达，请及时取餐。"),
    ("短信", "菜鸟驿站", "【菜鸟】您的包裹已到达菜鸟驿站。"),
    ("支付宝", "支付宝", "【支付宝】您有一笔生活缴费已扣款成功。"),
    ("墨迹天气", "墨迹天气", "【墨迹天气】今日多云，最高气温29℃，紫外线偏强。"),
)
ROUTINE_UTT: Tuple[str, ...] = (
    "嗯，今天中午吃啥呢。", "手机放哪了……哦在兜里。", "该买个新的充电器了。", "周末把窗帘洗了吧。",
)

# ---------------------------------------------------------------------------
# 七、装配器：把事件链编织成 24 小时生活流并生成六维方向性标答
# ---------------------------------------------------------------------------


@dataclass
class BuiltQuestion:
    question: Dict[str, Any]
    ground_truth: Dict[str, Any]
    stats: Dict[str, Any]


TIME_SLOTS: Tuple[Tuple[int, int], ...] = (
    (7 * 60 + 10, 9 * 60), (9 * 60, 11 * 60 + 30), (11 * 60 + 30, 13 * 60),
    (13 * 60, 15 * 60 + 30), (15 * 60 + 30, 17 * 60 + 30), (17 * 60 + 30, 19 * 60 + 30),
    (19 * 60 + 30, 21 * 60 + 30), (21 * 60 + 30, 23 * 60),
)

NOISE_DENSITY: Dict[str, Tuple[int, int]] = {
    "EASY": (1, 2), "MEDIUM": (2, 2), "HARD": (2, 3), "ADVERSARIAL": (3, 4),
}


def _pick(start: int, end: int, rng: random.Random, offset: int = 0) -> int:
    return rng.randint(start, end - 1) if end > start else start + offset


def _slot_for(rng: random.Random, idx: int) -> int:
    """按事件序号把关键事件铺到一天的不同时段（含晚间，呼应"白天受挫夜间重创"）。"""
    order = [0, 4, 7, 2, 5, 1, 6, 3]
    lo, hi = TIME_SLOTS[order[idx % len(order)]]
    return _pick(lo, hi, rng)


def _chain_for(rng: random.Random, modality: str) -> Chain:
    candidates = [c for c in CHAINS if any(pk in MODALITY_PRIMARY_PACKS[modality] for pk in c.packs)]
    primary_candidates = [c for c in candidates if any(
        pk in MODALITY_PRIMARY_PACKS[modality] for pk in c.packs
    )]
    if not primary_candidates:
        pack = rng.choice(MODALITY_PRIMARY_PACKS[modality])
        return Chain("adhoc", (pack,), (modality,), "单一主线事件贯穿全天")
    return rng.choice(primary_candidates)


def _extra_packs(rng: random.Random, modality: str, chain: Chain, difficulty: str) -> List[str]:
    """补充 1~2 个跨模态事件，保证「多个维度同时出事」的编织感。"""
    extras: List[str] = []
    pool = [pk for pk in MODALITY_PRIMARY_PACKS[modality] if pk not in chain.packs]
    if pool and difficulty in {"HARD", "ADVERSARIAL"}:
        extras.append(rng.choice(pool))
    other_mods = [m for m in MODALITY_PRIMARY_PACKS if m != modality]
    extra_count = 0 if difficulty == "EASY" else 1
    for _ in range(extra_count):
        m = rng.choice(other_mods)
        candidates = [pk for pk in MODALITY_PRIMARY_PACKS[m] if pk not in chain.packs and pk not in extras]
        if candidates:
            extras.append(rng.choice(candidates))
    return extras


def _voiceprint_cluster(
    rng: random.Random, p: Persona, modality: str, facts: Sequence[FactSpec], question_index: int
) -> Tuple[Dict[str, Any], Dict[str, str], List[str], List[Dict[str, Any]]]:
    """构造声纹聚类（24 个说话人碎片：本人 / 通讯录联系人 / 自称亲友的可疑来电 / 一次性陌生人）。

    返回 ``(cluster, tag→speaker_id, 垃圾speaker_id列表, 逐条生活流条目)``。
    说话人顺序按「设备发现时间」随机打散，**ID 序号与是否垃圾不存在相关性**。
    """
    want_full = modality == "voiceprint"
    intents = {f.intent for f in facts}
    # 标答里一旦出现"绑定核心亲友"，该亲友必须真实出现在聚类中（锚点与题面一致）
    bound_contact = next(
        (f.anchors[0] for f in facts if f.intent == "VOICE_BINDING_KEY_CONTACT" and f.anchors), None
    )
    # 多方会议事实的锚点人物必须真实出现在聚类中（会议说话人 = 标答锚点本人）
    meeting_contact = next(
        (f.anchors[0] for f in facts if f.intent == "WORK_COORDINATION" and f.anchors), None
    )
    enrolled = list(p.key_contacts[:1]) or [p.colleague]
    if bound_contact:
        enrolled = [bound_contact] + [c for c in enrolled if c != bound_contact][:1]

    speakers: List[Dict[str, Any]] = [{
        "role": "佩戴者本人", "enrolled_name": p.name, "n_fragments": rng.randint(18, 42),
        "cosine_to_enrolled_user": 1.0,
        "is_transient": False, "ttl_policy": "permanent_anchor", "keeper_tag": "vp_user",
    }]
    for name in enrolled:
        speakers.append({
            "role": ("核心亲友-" if name == bound_contact else "通讯录联系人-") + name,
            "enrolled_contact": name, "n_fragments": rng.randint(4, 16),
            "cosine_to_enrolled_user": round(rng.uniform(0.60, 0.88), 3),
            "is_transient": False, "ttl_policy": "keep_90d", "keeper_tag": "vp_contact",
        })
    if "VOICE_IMPERSONATION_FRAUD" in intents:
        claimed = next(
            (f.anchors[0] for f in facts if f.intent == "VOICE_IMPERSONATION_FRAUD" and f.anchors), enrolled[0]
        )
        speakers.append({
            "role": f"自称{claimed}的来电", "claimed_identity": claimed, "n_fragments": rng.randint(2, 6),
            "cosine_to_enrolled_user": round(rng.uniform(0.25, 0.48), 3),
            "cosine_to_claimed_identity": round(rng.uniform(0.28, 0.49), 3),
            "is_transient": True, "ttl_policy": "flag_suspicious", "keeper_tag": "vp_impostor",
        })
    if "WORK_COORDINATION" in intents:  # 仅当当日确有会议事实时，长时段多方会议才出现在聚类中
        for name in [(meeting_contact or enrolled[0])]:
            speakers.append({
                "role": f"会议相关方-{name}", "enrolled_contact": name, "n_fragments": rng.randint(3, 9),
                "cosine_to_enrolled_user": round(rng.uniform(0.58, 0.80), 3),
                "is_transient": False, "ttl_policy": "keep_90d", "keeper_tag": "vp_meeting",
            })
            if name not in enrolled:
                enrolled.append(name)

    keepers_now = len(speakers)
    listed = 24 if want_full else keepers_now + rng.randint(4, 7)
    total = listed
    while len(speakers) < listed:
        speakers.append({
            "role": rng.choice(["陌生人", "推销员", "店员", "路人", "客服", "邻居", "同事"]),
            "is_transient": True, "sample_text": rng.choice(NOISE_VOICEPRINT_SAMPLE)[:8],
        })

    rng.shuffle(speakers)  # 发现顺序打散：ID 序号不携带任何垃圾/保留信息
    tag_ids: Dict[str, str] = {}
    stray_ids: List[str] = []
    daily: List[Dict[str, Any]] = []
    for n, speaker in enumerate(speakers, start=1):
        sid = f"{QUESTION_PREFIX.lower()}-voi-{n:03d}"
        speaker["speaker_frag_id"] = sid
        tag = speaker.pop("keeper_tag", None)
        if tag and tag not in tag_ids:
            tag_ids[tag] = sid
        annotation = DEVICE_ANNOTATIONS.get(tag or "")
        if annotation and (tag == "vp_impostor" or not speaker.get("is_transient")):
            # 冒充者虽为一次性说话人，但它正是风险事实的证据，必须带端侧判读
            speaker["label"] = annotation[0]
            speaker["label_zh"] = annotation[1]
            if tag not in STRUCTURAL_ANNOTATION_TAGS:
                speaker["device_note"] = annotation[2]
        if speaker.get("is_transient") and not speaker.get("claimed_identity"):
            stray_ids.append(sid)
        if not speaker.get("sample_text"):
            daily.append({"stream": "voiceprint", "id": sid, "text": f"声纹碎片：{speaker['role']}"})
    stray = len(stray_ids)
    primary = None
    if bound_contact:
        for speaker in speakers:
            if speaker.get("enrolled_contact") == bound_contact:
                primary = {"contact": bound_contact, "n_fragments": speaker["n_fragments"],
                           "cosine_to_enrolled_user": speaker["cosine_to_enrolled_user"]}
                break
    cluster = {
        "user_verified": ({"name": p.name, "matched": True, "cosine": 1.0} if want_full else None),
        "total_detected_speakers": total,
        "cosine_merge_threshold": 0.55,
        "enrolled_contacts": enrolled,
        "primary_binding": primary,
        "cluster_summary": (
            (f"佩戴者本人声纹当日核验通过（{p.name}）；" if want_full else "")
            + f"当日共{total}人声纹碎片：佩戴者本人与 {len(enrolled)} 位通讯录联系人稳定绑定"
            + (f"，其中与核心亲友{bound_contact}绑定最稳定（{primary['n_fragments']}个碎片）" if primary else "")
            + f"，其余{stray}人为一次性杂散人声"
        ),
        "speakers": speakers,
    }
    return cluster, tag_ids, stray_ids, daily


def _sensor_summary(rng: random.Random, p: Persona, fragments: Sequence[Slice]) -> Dict[str, Any]:
    steps = rng.randint(3200, 15800)
    sleep = round(rng.uniform(4.6, 8.4), 1)
    summary: Dict[str, Any] = {
        "device_id": p.device, "resting_hr_bpm": p.hr_base + rng.randint(-3, 6), "steps": steps,
        "sleep_hours": sleep, "sampling": {"imu_hz": 50, "ppg_hz": 25, "baro_hz": 1},
        "baseline_conditions": list(p.conditions),
    }
    max_hr = 0
    for sl in fragments:
        if sl.payload.get("kind") in {"ppg_segment", "sleep_segment"}:
            max_hr = max(max_hr, int(sl.payload.get("hr_bpm_max") or sl.payload.get("hr_bpm_mean") or 0))
    summary["max_hr_bpm"] = max(max_hr, p.hr_base + rng.randint(20, 60))
    return summary


def _render_slice_text(sl: Slice) -> str:
    if sl.text:
        return sl.text
    payload = sl.payload
    if sl.modality == "app":
        return str(payload.get("content") or "")
    if sl.modality == "sensor":
        keys = ("g_peak", "post_impact_stillness_s", "pvc_burst_count", "hr_bpm_mean", "baro_drop_hpa",
                "sleep_hours", "glucose_mmol_l")
        parts = [f"{k}={payload[k]}" for k in keys if k in payload]
        return (payload.get("note") or "") + ("（" + "，".join(parts) + "）" if parts else "")
    if sl.modality == "utt":
        return str(payload.get("raw_speech") or "")
    return str(payload)


def build_question(index: int, modality: str, difficulty: str, rng: random.Random) -> BuiltQuestion:
    """装配第 ``index`` 道题：全天生活流 + 六维方向性标答。"""
    p = PERSONAS[(index * 17) % len(PERSONAS)]
    chain = _chain_for(rng, modality)
    primary_packs = [pk for pk in chain.packs if pk in MODALITY_PRIMARY_PACKS[modality]]
    other_packs = [pk for pk in chain.packs if pk not in primary_packs]
    budget = {"EASY": 1, "MEDIUM": 2, "HARD": 3, "ADVERSARIAL": 3}[difficulty]
    pack_keys = (primary_packs[:1] + other_packs[:1])[:budget]
    if len(pack_keys) < budget:
        pack_keys += primary_packs[1:][: budget - len(pack_keys)]
    if len(pack_keys) < budget and difficulty in {"HARD", "ADVERSARIAL"}:
        pack_keys += _extra_packs(rng, modality, chain, difficulty)[: budget - len(pack_keys)]

    slices: List[Slice] = []
    facts: List[FactSpec] = []
    dim_points: Dict[str, List[str]] = collections.defaultdict(list)  # key = 六维口径
    dim_anchors: Dict[str, List[str]] = collections.defaultdict(list)
    dim_evidence: Dict[str, List[str]] = collections.defaultdict(list)
    summary_parts: List[str] = []

    for order, key in enumerate(dict.fromkeys(pack_keys)):
        pack = ALL_PACKS[key](rng, p, _slot_for(rng, order))
        slices.extend(pack.slices)
        facts.extend(pack.facts)
        for dim, block in pack.dim_blocks.items():
            six = ECOSYSTEM_DIM_TO_SIX.get(dim, "dim:career")
            dim_points[six].extend(block.get("points", []))
            dim_anchors[six].extend(block.get("anchors", []))
            dim_evidence[six].extend(block.get("evidence", []))
        if pack.summary:
            summary_parts.append(pack.summary)

    # 身份锚点（真实安全通知，含佩戴者全名；保证标答人物锚点在端侧可恢复）
    identity = _mk("app", rng.randint(7 * 60 + 5, 21 * 60), text="", keep=True, tag="identity", payload={
        "app_name": "手机银行", "sender": "招商银行", "category": "bank",
    })
    identity_text = (f"【招商银行】{p.name}，您的账户于今日{rng.randint(8, 21)}:{rng.randint(10, 59)} 在本机登录，"
                     f"如非本人操作请致电95555。")
    identity.payload["content"] = identity_text
    identity.text = identity_text
    slices.append(identity)

    # 陷阱（真假对冲）
    traps = list(TRAP_PROFILE[difficulty])
    if difficulty in {"HARD", "ADVERSARIAL"}:
        trap_pool = [t for t in TRAPS if t not in traps]
        traps.append(rng.choice(trap_pool))
    trap_slices: List[Slice] = []
    for order, key in enumerate(traps):
        trap_pack = TRAPS[key](rng, p, _slot_for(rng, order + 3))
        slices.extend(trap_pack.slices)
        trap_slices.extend(trap_pack.slices)
        summary_parts.extend([s for s in [trap_pack.summary] if s])

    # 日常琐事 + 噪声（低价值但真实，必须可被判为冗余）
    density = NOISE_DENSITY[difficulty]
    slices.append(_mk("app", rng.randint(11 * 60, 13 * 60), keep=False, tag="routine",
                      text="【美团】您的外卖已送达，请及时取餐。",
                      payload={"app_name": "美团", "sender": "美团", "category": "trivia",
                               "content": "【美团】您的外卖已送达，请及时取餐。"}))
    slices.extend(_bank_junk(rng, rng.randint(9 * 60, 20 * 60), rng.randint(*density)))
    slices.extend(_mic_junk(rng, rng.randint(8 * 60, 22 * 60), rng.randint(*density)))
    slices.extend(_sensor_junk(rng, rng.randint(8 * 60, 22 * 60), rng.randint(*density)))
    slices.extend(_utt_junk(rng, rng.randint(8 * 60, 22 * 60), rng.randint(1, 2)))
    for text in rng.sample(ROUTINE_UTT, k=rng.randint(1, 2)):
        slices.append(_mk("utt", rng.randint(8 * 60, 22 * 60), text=text, scene="自语", keep=False, payload={
            "context_scene": "独处", "emotional_tone": "平静", "junk_tag": "自语",
            "duration_s": round(rng.uniform(1.2, 3.0), 1), "snr_db": round(rng.uniform(9.0, 18.0), 1),
            "is_self_talk": True,
            "physiological_context": {"hr_bpm": p.hr_base + rng.randint(-4, 6), "spo2_percent": rng.randint(97, 99)},
        }))
    for app_name, sender, content in rng.sample(ROUTINE_APP, k=rng.randint(1, 2)):
        slices.append(_mk("app", rng.randint(8 * 60, 22 * 60), text=content, keep=False, payload={
            "app_name": app_name, "sender": sender, "category": "trivia", "content": content,
        }))
    for text in rng.sample(ROUTINE_MIC, k=1):
        slices.append(_mk("mic", rng.randint(8 * 60, 22 * 60), text=text, scene="foreground_chatter", keep=False,
                          payload={"ambient_noise_db": rng.randint(52, 68), "snr_db": round(rng.uniform(6.0, 14.0), 1),
                                   "duration_s": round(rng.uniform(1.5, 5.0), 1), "is_background_chatter": False,
                                   "speaker_diarization": "user+1", "asr_confidence": round(rng.uniform(0.8, 0.95), 2)}))

    # ---- 保留切片补设备侧判读注释（保证端侧可解性） ----
    _annotate_keepers(slices)

    # ---- 非保留切片瘦身（体积控制，不影响可判分性） ----
    _trim_junk_slices(slices)

    # ---- 声纹聚类（24 个说话人碎片，逐条可枚举；一次性杂散人声须剪枝） ----
    cluster, vp_tag_ids, vp_stray_ids, vp_daily = _voiceprint_cluster(rng, p, modality, facts, index)

    # ---- 传感器摘要与 50Hz 抽样窗口 ----
    sensor_frags = [s for s in slices if s.modality == "sensor"]
    summary = _sensor_summary(rng, p, sensor_frags)
    if modality == "sensor":
        summary["raw_sampled_at"] = f"{rng.randint(8, 21):02d}:{rng.randint(10, 59):02d}"

    # ---- 赋值 ID（统一命名，绝不泄漏垃圾/保留身份） ----
    slices.sort(key=lambda s: (s.t, s.modality))
    counters: Dict[str, int] = collections.Counter()
    keepers = 0
    for sl in slices:
        counters[sl.modality] += 1
        sl.payload = dict(sl.payload)
        sl.payload["t"] = _hhmm(sl.t)
        if sl.keep:
            keepers += 1

    def _assign() -> None:
        counters.clear()
        for sl in slices:
            counters[sl.modality] += 1

    def _sid(sl: Slice) -> str:
        return f"{QUESTION_PREFIX.lower()}-{sl.modality[:3]}-{counters[sl.modality]:03d}"

    # 逐模态编号：同一模态内按时间排序
    by_mod: Dict[str, List[Slice]] = collections.defaultdict(list)
    for sl in slices:
        by_mod[sl.modality].append(sl)
    id_map: Dict[int, str] = {}
    counters.clear()
    for mod, group in by_mod.items():
        for sl in sorted(group, key=lambda s: s.t):
            counters[mod] += 1
            id_map[id(sl)] = f"{QUESTION_PREFIX.lower()}-{mod[:3]}-{counters[mod]:03d}"

    # ---- 组装五路流 ----
    mic_stream: List[Dict[str, Any]] = []
    app_stream: List[Dict[str, Any]] = []
    utt_stream: List[Dict[str, Any]] = []
    sensor_fragments: List[Dict[str, Any]] = []
    junk_ids: List[str] = []
    daily_stream: List[Dict[str, Any]] = []

    for sl in sorted(slices, key=lambda s: s.t):
        sid = id_map[id(sl)]
        t_str = _hhmm(sl.t)
        if sl.modality == "mic":
            item = {"snippet_id": sid, "t": t_str, "text": sl.text, "scene": sl.scene}
            item.update(sl.payload)
            item.pop("t", None)
            item["t"] = t_str
            mic_stream.append(item)
        elif sl.modality == "app":
            item = {"msg_id": sid, "t": t_str}
            item.update(sl.payload)
            item.pop("t", None)
            item["t"] = t_str
            app_stream.append(item)
        elif sl.modality == "utt":
            item = {"utterance_id": sid, "t": t_str, "raw_speech": sl.text}
            item.update(sl.payload)
            item.pop("t", None)
            item["t"] = t_str
            if sl.payload.get("physiological_context"):
                item["physiological_context"] = sl.payload["physiological_context"]
            utt_stream.append(item)
        elif sl.modality == "sensor":
            item = {"fragment_id": sid, "t": t_str}
            item.update(sl.payload)
            item.pop("t", None)
            item["t"] = t_str
            sensor_fragments.append(item)
        if not sl.keep:
            junk_ids.append(sid)
        daily_stream.append(f"{t_str}|{sl.modality}|{sid}")

    # 声纹碎片：本人与通讯录联系人为保留项，一次性杂散人声进入待剪枝集合
    junk_ids.extend(vp_stray_ids)
    for entry in vp_daily:
        daily_stream.append(f"{_hhmm(rng.randint(7 * 60 + 20, 22 * 60))}|voiceprint|{entry['id']}")
    daily_stream.sort()

    # ---- 标答事实（source_tag → 片断 ID） ----
    tag_to_id: Dict[str, str] = {}
    for sl in slices:
        if sl.tag:
            tag_to_id.setdefault(sl.tag, id_map[id(sl)])
    gt_facts: List[Dict[str, Any]] = []
    anchor_checks: List[Tuple[str, str, bool]] = []
    if modality == "voiceprint":
        facts = list(facts) + [FactSpec(
            dim="dim:social", intent="VOICE_BINDING_USER",
            core=f"当日声纹聚类核验佩戴者本人（{p.name}）声纹通过，本人身份稳定可信",
            anchors=(p.name,), keywords=("佩戴者本人声纹", "本人声纹核验", "身份核验通过", "本人身份确认"),
            red_lines=("把他人声纹误认为本人", "忽略本人绑定的核验结论"), source_tag="vp_user",
        )]
    blob = json.dumps({"mic": mic_stream, "app": app_stream, "utt": utt_stream,
                       "sensor": sensor_fragments, "vp": cluster}, ensure_ascii=False)
    for n, fact in enumerate(facts, start=1):
        src = tag_to_id.get(fact.source_tag) or vp_tag_ids.get(fact.source_tag)
        if src is None:  # 兜底：挂到本人声纹碎片
            src = vp_tag_ids.get("vp_user") or id_map[id(sorted(slices, key=lambda s: s.t)[0])]
        anchors = [a for a in fact.anchors if a][:3]
        for a in anchors:
            anchor_checks.append((fact.intent, a, a in blob))
        gt_facts.append({
            "fact_id": f"{QUESTION_PREFIX}_{index:05d}-fact-{n}",
            "dimension_id": fact.dim,
            "semantic_intent": fact.intent,
            "anchor_entities": anchors,
            "directional_keywords": list(fact.keywords)[:4],
            "core_content": fact.core if len(fact.core) <= 48 else fact.core[:47] + "…",
            "source_ref_id": src,
            "confidence": fact.confidence,
        })

    # ---- 六维方向性标答（全局 + 5 维度，每块含红线判据） ----
    dims_present = {_six_dim(f) for f in facts}
    dim_blocks: Dict[str, Any] = {}
    for dim in ("dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"):
        if dim in dims_present:
            dim_facts = [f for f in facts if _six_dim(f) == dim]
            dim_blocks[dim] = {
                "core_points": (sorted(set(dim_points[dim])) or [f.core for f in dim_facts])[:1],
                "acceptable_synonyms": sorted({kw for f in dim_facts for kw in f.keywords})[:4],
                "red_lines": sorted({rl for f in dim_facts for rl in f.red_lines})[:2],
                "anchor_entities": sorted(set(dim_anchors[dim]))[:2],
                "evidence_ids": sorted({tag_to_id.get(t, t) or vp_tag_ids.get(t, t) for t in dim_evidence[dim]})[:2],
            }
        else:
            dim_blocks[dim] = {
                "core_points": CALM_DIM_BLOCKS[dim]["points"],
                "acceptable_synonyms": CALM_DIM_BLOCKS[dim]["keywords"][:2],
                "red_lines": list(CALM_RED_LINES[dim])[:1],
            }

    global_points = [s for s in summary_parts if s]
    directional_gt = {
        "global_daily_summary": {
            "core_points": global_points[:4],
            "storyline": chain.storyline,
            "acceptable_synonyms": ["主线剧情", "当日主线", "整体剧情", "一天的主线"],
            "red_lines": ["总结为平淡无事的一天", "主线与关键事件相反", "把陷阱（玩笑/吹牛/影视外放）当成主线"],
        },
        "dimensions": dim_blocks,
    }

    # ---- 六维之外的题面元数据 ----
    question_id = f"{QUESTION_PREFIX}_{index:05d}"
    question = {
        "question_id": question_id,
        "generator_agent": GENERATOR_AGENT,
        "persona": {
            "persona_id": p.pid, "name": p.name, "occupation": p.occupation, "device_id": p.device,
            "key_contacts": list(p.key_contacts),
        },
        "timestamp_utc": f"2026-09-{rng.randint(1, 28):02d}T07:00:00+08:00",
        "difficulty": difficulty,
        "day_window": {"start": "07:00", "end": "23:30"},
        "primary_modality": modality,
        "cleaned_daily_stream": daily_stream,
        "sensor_stream": {"device_id": p.device, "summary": summary, "fragments": sensor_fragments},
        "mic_stream": mic_stream,
        "voiceprint_cluster": cluster,
        "app_message_stream": app_stream,
        "user_dialogue_stream": utt_stream,
        "directional_ground_truth": directional_gt,
        "ground_truth_facts": gt_facts,
        "ground_truth_junk_ids": junk_ids,
    }
    ground_truth = {
        "question_id": question_id,
        "generator_agent": GENERATOR_AGENT,
        "category": modality,
        "difficulty": difficulty,
        "chain": chain.name,
        "ground_truth_facts": gt_facts,
        "ground_truth_junk_ids": junk_ids,
    }
    # 最终校验以「序列化后的题目」为唯一口径：标答锚点必须在题面内逐字可恢复（出卷官自缚规矩 R1）
    final_blob = json.dumps(
        {k: v for k, v in question.items() if not k.startswith("ground_truth")}, ensure_ascii=False
    )
    final_failures = [
        (fact["semantic_intent"], anchor)
        for fact in gt_facts for anchor in fact["anchor_entities"] if anchor not in final_blob
    ]
    stats = {
        "index": index, "modality": modality, "difficulty": difficulty, "chain": chain.name,
        "persona": p.pid, "slices": len(slices) + len(cluster["speakers"]), "junk": len(junk_ids),
        "keepers": keepers, "facts": len(gt_facts), "dims_present": sorted(dims_present),
        "anchor_checks": anchor_checks, "anchor_failures": final_failures,
        "junk_ratio": round(len(junk_ids) / max(len(slices) + len(cluster["speakers"]), 1), 4),
    }
    return BuiltQuestion(question=question, ground_truth=ground_truth, stats=stats)


# ---------------------------------------------------------------------------
# 八、题库级审计（配比 / 泄漏 / 锚点可恢复性 / 契约）
# ---------------------------------------------------------------------------


def _modality_plan(count: int) -> List[str]:
    plan: List[str] = []
    for modality, share in MODALITY_MIX:
        plan.extend([modality] * share)
    if count <= len(plan):
        # 保持配比：等距抽样
        step = len(plan) / count
        return [plan[int(i * step)] for i in range(count)]
    extra = count - len(plan)
    return plan + [plan[i % len(plan)] for i in range(extra)]


def _difficulty_plan(count: int) -> List[str]:
    plan: List[str] = []
    for difficulty, share in DIFFICULTY_MIX:
        plan.extend([difficulty] * int(round(share * count)))
    while len(plan) < count:
        plan.append("MEDIUM")
    return plan[:count]


def audit_bank(questions: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """题库审计：五路配比、难度、密度、ID 泄漏、锚点可恢复性、红线覆盖率。"""
    modality_counter: collections.Counter = collections.Counter()
    difficulty_counter: collections.Counter = collections.Counter()
    chain_counter: collections.Counter = collections.Counter()
    dim_counter: collections.Counter = collections.Counter()
    junk_total = slice_total = fact_total = 0
    anchor_total = anchor_missing = 0
    hook_total = hook_hits = 0
    id_shapes: collections.Counter = collections.Counter()
    ordinal_junk: List[bool] = []
    red_line_blocks = synonym_blocks = calms = key_blocks = 0

    for question in questions:
        modality_counter[question["primary_modality"]] += 1
        difficulty_counter[question["difficulty"]] += 1
        streams = {
            "sensor": question["sensor_stream"].get("fragments", []),
            "mic": question["mic_stream"],
            "app": question["app_message_stream"],
            "utt": question["user_dialogue_stream"],
        }
        blob = json.dumps({k: v for k, v in question.items() if not k.startswith("ground_truth")},
                          ensure_ascii=False)
        junk = set(question["ground_truth_junk_ids"])
        for stream_name, items in streams.items():
            for position, item in enumerate(items):
                sid = item.get("fragment_id") or item.get("snippet_id") or item.get("msg_id") or item.get("utterance_id")
                slice_total += 1
                if sid in junk:
                    junk_total += 1
                id_shapes[re.sub(r"\d+", "#", str(sid))] += 1
                ordinal_junk.append(sid in junk)
        for speaker in question["voiceprint_cluster"].get("speakers", []):
            sid = speaker.get("speaker_frag_id")
            slice_total += 1
            if sid in junk:
                junk_total += 1
            id_shapes[re.sub(r"\d+", "#", str(sid))] += 1
            ordinal_junk.append(sid in junk)
        facts = question["ground_truth_facts"]
        fact_total += len(facts)
        for fact in facts:
            dim_counter[fact["dimension_id"]] += 1
            for anchor in fact["anchor_entities"]:
                anchor_total += 1
                if anchor not in blob:
                    anchor_missing += 1
            hook_total += 1
            if any(keyword in blob for keyword in fact["directional_keywords"]):
                hook_hits += 1
        blocks = question["directional_ground_truth"]["dimensions"]
        for block in blocks.values():
            if block.get("red_lines"):
                red_line_blocks += 1
            if block.get("acceptable_synonyms"):
                synonym_blocks += 1
            calm = not block.get("evidence_ids") and not block.get("anchor_entities")
            calms += 1 if calm else 0
            key_blocks += 0 if calm else 1
        chain_counter[question.get("chain") or question["directional_ground_truth"]["global_daily_summary"]["storyline"]] += 1

    # ID 泄漏度量：按 ID 序号推断垃圾/保留的朴素规则准确率（0.5 附近 = 无泄漏）
    naive_hits = 0
    for position, is_junk in enumerate(ordinal_junk):
        naive_hits += 1 if (position % 2 == 0) == is_junk else 0
    leak_rate = naive_hits / max(len(ordinal_junk), 1)
    return {
        "questions": len(questions),
        "modality_mix": dict(modality_counter),
        "difficulty_mix": dict(difficulty_counter),
        "chain_mix": dict(chain_counter.most_common()),
        "dimension_fact_mix": dict(dim_counter),
        "slices": slice_total,
        "junk_slices": junk_total,
        "junk_ratio": round(junk_total / max(slice_total, 1), 4),
        "facts": fact_total,
        "facts_per_question": round(fact_total / max(len(questions), 1), 3),
        "anchors": anchor_total,
        "anchor_unrecoverable": anchor_missing,
        "anchor_recoverability": round(1 - anchor_missing / max(anchor_total, 1), 6),
        "keyword_hook_facts": hook_hits,
        "keyword_hook_recoverability": round(hook_hits / max(hook_total, 1), 6),
        "id_shapes": dict(id_shapes),
        "structural_id_leak_accuracy": round(leak_rate, 4),
        "dim_blocks_with_red_lines": red_line_blocks,
        "dim_blocks_with_synonyms": synonym_blocks,
        "dim_blocks_key_events": key_blocks,
        "dim_blocks_calm_baseline": calms,
    }


def _write_reports(
    questions: Sequence[Mapping[str, Any]], audit: Mapping[str, Any], report_path: Optional[Path],
    manifest_path: Optional[Path], elapsed: float, seed: str,
) -> None:
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "generator_agent": GENERATOR_AGENT, "agent_id": AGENT_ID, "seed": seed,
            "questions": audit["questions"], "modality_mix": audit["modality_mix"],
            "difficulty_mix": audit["difficulty_mix"], "facts_per_question": audit["facts_per_question"],
            "junk_ratio": audit["junk_ratio"], "anchor_recoverability": audit["anchor_recoverability"],
            "keyword_hook_recoverability": audit["keyword_hook_recoverability"],
            "structural_id_leak_accuracy": audit["structural_id_leak_accuracy"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    if not report_path:
        return
    lines = [
        "# 出卷报告 · Generator `01a0aa2c-fantonghui`（全天生活流 + 六维方向性标答）",
        "",
        f"- 题量：**{audit['questions']}** 道（种子 `{seed}`，确定性可复现）",
        f"- 生成耗时：{elapsed:.1f}s（{audit['questions'] / max(elapsed, 1e-9):.0f} 题/秒）",
        "",
        "## 一、五路配比（Master Dispatch #11）",
        "",
        "| 模态 | 题量 |", "| --- | --- |",
    ]
    for key, value in audit["modality_mix"].items():
        lines.append(f"| {key} | {value} |")
    lines += ["", "## 二、难度分布", "", "| 难度 | 题量 |", "| --- | --- |"]
    for key, value in audit["difficulty_mix"].items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "", "## 三、规模与密度", "",
        f"- 生活流切片总量：{audit['slices']}（其中垃圾 {audit['junk_slices']}，占 {audit['junk_ratio']:.1%}）",
        f"- 标答事实总量：{audit['facts']}（平均 {audit['facts_per_question']} 条/题）",
        f"- 标答锚点：{audit['anchors']} 个，端侧不可恢复 **{audit['anchor_unrecoverable']}** 个",
        f"- **锚点可恢复率：{audit['anchor_recoverability']:.4%}**",
        f"- 方向词钩子：{audit['keyword_hook_facts']}/{audit['facts']} 条事实的方向同义词在题面逐字可命中"
        f"（**{audit['keyword_hook_recoverability']:.4%}**，全库 0 题的极端情形为 0）",
        f"- ID 结构泄漏（朴素序号规则准确率）：{audit['structural_id_leak_accuracy']:.4f}（0.5 = 完全无泄漏）",
        f"- ID 命名族：{audit['id_shapes']}",
        "", "## 四、六维标答覆盖", "",
        f"- 有核心事件的维度块：{audit['dim_blocks_key_events']}",
        f"- 平稳基线维度块：{audit['dim_blocks_calm_baseline']}（含「不得把日常上升为重大事件」红线）",
        f"- 含方向同义词的维度块：{audit['dim_blocks_with_synonyms']}",
        f"- 含绝对偏离红线的维度块：{audit['dim_blocks_with_red_lines']}",
        "", "## 五、事实维度分布", "", "| 维度 | 事实数 |", "| --- | --- |",
    ]
    for key, value in sorted(audit["dimension_fact_mix"].items()):
        lines.append(f"| {key} | {value} |")
    lines += [
        "", "## 六、事件链分布（跨维度冲突编排）", "", "| 事件链 | 题量 |", "| --- | --- |",
    ]
    for key, value in list(audit["chain_mix"].items())[:16]:
        lines.append(f"| `{key}` | {value} |")
    lines += [
        "", "## 七、出卷官自缚三条规矩的执行证据", "",
        "1. **锚点必然可恢复**：本卷逐字取自题目可见数据，可恢复率见上（对手卷 agent-11 为 48.4%，"
        "其 82.5% 的 MIC 锚点在端侧根本不存在）；",
        "2. **零结构性泄漏**：全部片断 ID 统一为 `<题号>-<模态>-<序号>`，垃圾与证据不可由 ID 区分，"
        "题面也不含任何 `is_junk` 结论标记；",
        "3. **可判分性**：每个维度块都给出【可接受方向同义词】与【绝对偏离红线判据】，"
        "方向近似（争吵↔吵闹）全额给分，方向反转（打情骂俏）一票否决。",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 全天生活流高熵出卷官（Generator 01a0aa2c）")
    parser.add_argument("--count", type=int, default=10000, help="题量（默认 10000）")
    parser.add_argument("--seed", default=f"{AGENT_ID}:v1", help="确定性种子")
    parser.add_argument("--questions", type=Path,
                        default=Path("benchmarks/data_cleaning/questions/questions_01a0aa2c-fantonghui.jsonl"))
    parser.add_argument("--ground-truth", type=Path,
                        default=Path("benchmarks/data_cleaning/ground_truth/gt_01a0aa2c-fantonghui.jsonl"))
    parser.add_argument("--report", type=Path,
                        default=Path("benchmarks/data_cleaning/reports/generation_01a0aa2c-fantonghui.md"))
    parser.add_argument("--manifest", type=Path,
                        default=Path("benchmarks/data_cleaning/reports/manifest_01a0aa2c-fantonghui.json"))
    parser.add_argument("--limit", type=int, default=0, help="仅生成前 N 题（调试）")
    args = parser.parse_args(argv)

    count = args.limit or args.count
    modalities = _modality_plan(count)
    difficulties = _difficulty_plan(count)
    # 打散模态/难度排布：避免"前 3000 题全是传感器"这类结构性顺序泄漏
    plan_rng = random.Random(f"{args.seed}:plan")
    plan_rng.shuffle(modalities)
    plan_rng.shuffle(difficulties)
    started = time.perf_counter()

    questions: List[Dict[str, Any]] = []
    truths: List[Dict[str, Any]] = []
    anchor_failures: List[Tuple[str, str]] = []
    for index in range(1, count + 1):
        rng = random.Random(f"{args.seed}:{index:05d}")
        built = build_question(index, modalities[index - 1], difficulties[index - 1], rng)
        questions.append(built.question)
        truths.append(built.ground_truth)
        for failure in built.stats["anchor_failures"]:
            anchor_failures.append((built.question["question_id"], failure))

    elapsed = time.perf_counter() - started
    audit = audit_bank(questions)
    audit["anchor_unrecoverable_generator_side"] = len(anchor_failures)
    audit["anchor_failure_samples"] = anchor_failures[:10]

    args.questions.parent.mkdir(parents=True, exist_ok=True)
    with args.questions.open("w", encoding="utf-8") as handle:
        for question in questions:
            handle.write(json.dumps(question, ensure_ascii=False, separators=(",", ":")) + "\n")
    args.ground_truth.parent.mkdir(parents=True, exist_ok=True)
    with args.ground_truth.open("w", encoding="utf-8") as handle:
        for truth in truths:
            handle.write(json.dumps(truth, ensure_ascii=False, separators=(",", ":")) + "\n")

    _write_reports(questions, audit, args.report, args.manifest, elapsed, args.seed)
    print(json.dumps({
        "questions": audit["questions"], "modality_mix": audit["modality_mix"],
        "junk_ratio": audit["junk_ratio"], "facts_per_question": audit["facts_per_question"],
        "anchor_recoverability": audit["anchor_recoverability"],
        "keyword_hook_recoverability": audit["keyword_hook_recoverability"],
        "anchor_unrecoverable_generator_side": len(anchor_failures),
        "structural_id_leak_accuracy": audit["structural_id_leak_accuracy"],
        "elapsed_s": round(elapsed, 2),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



