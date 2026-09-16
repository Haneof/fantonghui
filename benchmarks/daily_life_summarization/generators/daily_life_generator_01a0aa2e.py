"""AIOS 3.0 全天生活流出卷官 —— 战队 ``01a0aa2e`` 的高熵 24 小时人生试卷生成器。

设计目标（对应出卷铁律）
----------------------
1. 每道试卷 = 一个人的 24 小时（07:00 ~ 23:30），三通道混合：
   ``mic_slices``（对话切片）/ ``app_notifications``（应用与通知）/ ``sensor_summary``（体征宏观摘要）。
2. 【关键大事】与【海量琐碎日常】按真实配比混编：单题 45~90 个事件，其中只有
   10~18 个承载标答证据，其余为买咖啡、取快递、同事闲聊一类的低信息量噪声。
3. 每道题必有跨维度冲突或转折（工作受挫 + 情感破裂 + 体征异动同时发生）。
4. 标答是【方向性语义标答】：每个维度给出 ``semantic_core`` +
   ``acceptable_synonyms``（方向同义词，命中即算对）+ ``red_line_rejections``
   （绝对偏离红线，命中一票否决）+ ``key_entities`` + ``evidence_ref_ids``。

反泄漏纪律（本战队做题时踩过的坑，出题时全部堵死）
--------------------------------------------------
* 题面内**不得**出现 ``label`` / ``kind`` / ``note`` / ``is_junk`` / ``trap_tag`` /
  ``dimension`` / ``intent`` / ``ground_truth`` / ``anchor`` 之类的答案字段；
* ``generator_meta``（主线剧情 id、副线 id、难度成因）只写入标答文件，不进题面；
* 标答里每一个 ``key_entities`` 必须**逐字**出现在它引用的证据碎片文本中
  （:func:`validate_question` 强校验）——这正是对手题库第一大缺陷（锚点不在题面）；
* ``red_line_rejections`` 里的词**不得**出现在题面任何文本中，否则标答自相矛盾；
* ``acceptable_synonyms`` 与 ``red_line_rejections`` 不得有交集。

确定性：全部随机性来自 ``random.Random(seed)``，同 seed 同输出，可复现。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

GENERATOR_AGENT_ID = "01a0aa2e"
BANK_NAME = f"daily_life_{GENERATOR_AGENT_ID}"

DAY_START_MIN = 7 * 60          # 07:00
DAY_END_MIN = 23 * 60 + 30      # 23:30
DIMENSIONS = ("dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career")

#: 题面中禁止出现的答案字段名（反泄漏）
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "label", "label_zh", "kind", "note", "is_junk", "junk_tag", "trap_tag",
        "ground_truth", "ground_truth_facts", "ground_truth_junk_ids", "directional_ground_truth",
        "semantic_core", "acceptable_synonyms", "red_line", "red_lines", "anchor", "anchors",
        "intent", "semantic_intent", "dimension", "dimension_id", "difficulty_reason",
        "spine_id", "subplot_id", "generator_meta", "answer", "solution",
    }
)

#: 标答里禁止出现的"字句匹配陷阱"：不允许把整句原话当作唯一同义词
MIN_SYNONYMS = 3
MIN_RED_LINES = 2


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def hhmm(minutes: int) -> str:
    """分钟数 → ``HH:MM``。"""
    minutes = max(0, min(24 * 60 - 1, minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def minutes_of(stamp: str) -> int:
    hour, minute = stamp.split(":")
    return int(hour) * 60 + int(minute)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 词库：人名 / 城市 / 职业 / 地点
# ---------------------------------------------------------------------------
SURNAMES = (
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余杜叶程苏魏吕丁任沈"
    "姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛段雷侯龙史陶黎贺顾毛郝龚邵万钱严武戴莫孔汤"
)
GIVEN_CHAR_A = (
    "伟芳娜敏静丽强磊军洋勇艳杰娟涛明超霞平刚桂英华玉萍红鹏斌宇浩凯健俊帆蕾婷雪琳晨阳璐倩薇妍宁嘉"
    "昊然泽瑞楠欣怡梦思雨辰子一鸣"
)
GIVEN_CHAR_B = (
    "华军平刚强磊涛明超杰斌宇浩凯健俊帆婷雪琳晨阳璐倩薇妍宁嘉昊然泽瑞楠欣怡梦思雨辰子翔睿琪菲彤"
    "岚坤成栋梁旭恒毅安澜清婉柔嘉乐康宁"
)
GIVEN_FEMALE_BIAS = set("芳娜敏静丽娟霞萍红蕾婷雪琳璐倩薇妍欣怡梦雨柔婉菲彤岚清婉")

CITIES = (
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "重庆", "苏州", "天津",
    "长沙", "郑州", "青岛", "沈阳", "宁波", "昆明", "合肥", "佛山", "福州", "济南", "大连", "厦门",
    "哈尔滨", "南昌", "贵阳", "石家庄", "南宁", "长春", "太原", "无锡", "温州", "兰州", "海口", "银川",
    "乌鲁木齐", "呼和浩特", "珠海", "常州",
)

OCCUPATIONS: Tuple[Tuple[str, str, str], ...] = (
    # (岗位, 单位类型, 行业)
    ("后端研发工程师", "互联网科技公司", "互联网"),
    ("算法工程师", "人工智能公司", "人工智能"),
    ("产品经理", "互联网科技公司", "互联网"),
    ("测试工程师", "软件外包公司", "软件服务"),
    ("运维工程师", "云计算公司", "云计算"),
    ("数据分析师", "跨境电商公司", "电商"),
    ("UI设计师", "设计工作室", "设计"),
    ("市场专员", "快消品公司", "快消"),
    ("销售经理", "医疗器械公司", "医疗器械"),
    ("客户经理", "股份制银行", "金融"),
    ("风控专员", "消费金融公司", "金融"),
    ("会计", "制造业集团", "制造"),
    ("审计助理", "会计师事务所", "会计服务"),
    ("人力资源专员", "人力资源服务公司", "人力服务"),
    ("法务专员", "律师事务所", "法律服务"),
    ("中学语文老师", "市重点中学", "教育"),
    ("小学班主任", "公办小学", "教育"),
    ("高校辅导员", "省属高校", "教育"),
    ("三甲医院护士长", "三甲医院", "医疗"),
    ("住院医师", "三甲医院", "医疗"),
    ("药剂师", "连锁药房", "医药零售"),
    ("机械工程师", "汽车整车厂", "汽车制造"),
    ("电气工程师", "电力设计院", "电力"),
    ("土建施工员", "建筑工程公司", "建筑"),
    ("造价工程师", "工程咨询公司", "建筑"),
    ("货运司机", "物流运输公司", "物流"),
    ("外卖骑手", "即时配送平台", "即时配送"),
    ("网约车司机", "出行平台", "出行"),
    ("餐厅店长", "连锁餐饮门店", "餐饮"),
    ("便利店店主", "个体便利店", "零售"),
    ("理发师", "连锁美发门店", "美业"),
    ("健身教练", "连锁健身房", "健身"),
    ("摄影师", "婚纱摄影机构", "摄影"),
    ("社区民警", "辖区派出所", "公共安全"),
    ("消防员", "消防救援站", "应急救援"),
    ("公务员科员", "市直机关", "政务"),
    ("事业单位职员", "区文化馆", "文化"),
    ("记者编辑", "都市报社", "传媒"),
    ("新媒体运营", "MCN机构", "传媒"),
    ("主播", "直播电商公司", "直播电商"),
    ("宠物医生", "宠物医院", "宠物医疗"),
    ("月嫂", "家政服务公司", "家政"),
    ("退休返聘技术员", "老厂技术顾问岗", "制造"),
    ("花店老板", "个体花店", "零售"),
    ("研究生", "省属高校", "教育"),
    ("大三学生", "省属高校", "教育"),
    ("创业者", "初创公司", "创业"),
    ("独立开发者", "自由职业", "软件服务"),
    ("保险代理人", "寿险公司", "保险"),
    ("房产中介", "连锁房产中介", "房产"),
)

MEETING_ROOMS = ("三楼会议室", "五层小会议室", "开放区讨论间", "客户接待室", "工位旁走廊")
COMMUTE_MODES = ("地铁", "公交", "电动车", "共享单车", "网约车", "自驾")
COFFEE_SHOPS = ("瑞幸", "星巴克", "库迪", "Manner", "便利店咖啡")
LUNCH_SPOTS = ("楼下麻辣烫", "园区食堂", "沙县小吃", "兰州拉面", "便利店饭团", "外卖", "公司楼下的粤式茶餐厅")
SUPERMARKETS = ("盒马", "永辉", "华润万家", "社区生鲜店", "山姆")
EXPRESS_STATIONS = ("菜鸟驿站", "丰巢柜", "小区门卫", "京东自提点")
WEATHERS = ("晴", "多云", "小雨", "阴", "大风降温", "雷阵雨", "回南天", "雾霾")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class Anchor:
    """一个维度的方向性语义标答。"""

    dim: str                                     # "global" 或 DIMENSIONS 之一
    core: str                                    # 方向性核心（已渲染成最终文本）
    synonyms: Tuple[str, ...]                    # 可接受的方向同义词
    red_lines: Tuple[str, ...]                   # 绝对偏离红线（一票否决）
    tags: Tuple[str, ...]                        # 证据碎片标签
    entities: Tuple[str, ...] = ()               # 关键实体（必须逐字出现在证据中）
    severity: int = 3                            # 3 主线 / 2 副线 / 1 常态，用于合并时选主锚点


@dataclass
class Spine:
    """一条主线剧情（一天的核心冲突）。"""

    spine_id: str
    title: str
    requires: str                                # "" / "partner" / "single" / "child" / "pet"
    age_min: int
    age_max: int
    build: Callable[["Ctx"], List[Anchor]]
    jobs: Tuple[str, ...] = ()                   # 限定适配的职业（空 = 不限）


@dataclass
class Subplot:
    """一条副线（补充某一维度的次级要点）。"""

    subplot_id: str
    requires: str
    build: Callable[["Ctx"], List[Anchor]]


class Ctx:
    """单题构建上下文：持有 RNG、人物设定、三通道事件流与证据索引。"""

    def __init__(self, rng: random.Random, persona: Dict[str, Any]):
        self.rng = rng
        self.persona = persona
        self.p: Dict[str, Any] = dict(persona)
        self.mic_items: List[Dict[str, Any]] = []
        self.app_items: List[Dict[str, Any]] = []
        self.hr_events: List[Dict[str, Any]] = []
        self.imu_events: List[Dict[str, Any]] = []
        self.refs: Dict[str, List[str]] = {}
        self.sensor: Dict[str, Any] = {}
        #: 全天步数在建题之初就定死，主线可下调（久坐日）或上调（体力劳动日），
        #: 标答里凡提到活动量都必须引用这个真实数值，避免"步数偏少"与 2 万步自相矛盾。
        self.steps_total: int = rng.randint(2500, 21000)
        self._mic_n = 0
        self._app_n = 0
        self._hr_n = 0
        self._imu_n = 0

    # -- 事件写入 -----------------------------------------------------------
    def pick_ts(self, window: Tuple[int, int]) -> str:
        return hhmm(self.rng.randint(window[0], window[1]))

    def _link(self, tag: str, ref_id: str) -> None:
        self.refs.setdefault(tag, []).append(ref_id)

    def mic(
        self,
        tag: str,
        window: Tuple[int, int],
        speaker: str,
        location: str,
        text: str,
        noise_db: Optional[int] = None,
        channel: str = "对话",
    ) -> str:
        self._mic_n += 1
        ref_id = f"M{self._mic_n:03d}"
        self.mic_items.append(
            {
                "snippet_id": ref_id,
                "ts": self.pick_ts(window),
                "speaker": speaker,
                "location": location,
                "channel": channel,
                "text": text,
                "ambient_noise_db": noise_db if noise_db is not None else self.rng.randint(42, 74),
            }
        )
        self._link(tag, ref_id)
        return ref_id

    def app(
        self,
        tag: str,
        window: Tuple[int, int],
        app_name: str,
        sender: str,
        content: str,
        direction: str = "接收",
        session: str = "私聊",
    ) -> str:
        self._app_n += 1
        ref_id = f"A{self._app_n:03d}"
        self.app_items.append(
            {
                "msg_id": ref_id,
                "ts": self.pick_ts(window),
                "app": app_name,
                "sender": sender,
                "session": session,
                "direction": direction,
                "content": content,
            }
        )
        self._link(tag, ref_id)
        return ref_id

    def hr(self, tag: str, window: Tuple[int, int], peak: int, window_mean: Optional[int] = None, duration_s: Optional[int] = None) -> str:
        self._hr_n += 1
        ref_id = f"SH{self._hr_n:02d}"
        stamp = self.pick_ts(window)
        self.hr_events.append(
            {
                "event_id": ref_id,
                "ts": stamp,
                # 手环 App 的可读读数，保证"{peak}bpm"这类实体在题面中逐字可见
                "reading": f"{peak}bpm（{stamp} 触发）",
                "peak_bpm": peak,
                "window_mean_bpm": window_mean if window_mean is not None else max(58, peak - self.rng.randint(8, 22)),
                "duration_s": duration_s if duration_s is not None else self.rng.choice((90, 120, 180, 240, 300, 420)),
            }
        )
        self._link(tag, ref_id)
        return ref_id

    def imu(self, tag: str, window: Tuple[int, int], peak_g: float, axis: str = "垂直") -> str:
        self._imu_n += 1
        ref_id = f"SI{self._imu_n:02d}"
        stamp = self.pick_ts(window)
        self.imu_events.append(
            {
                "event_id": ref_id,
                "ts": stamp,
                "reading": f"{peak_g}g（{stamp} {axis}方向冲击）",
                "peak_g": peak_g,
                "axis": axis,
            }
        )
        self._link(tag, ref_id)
        return ref_id

    # -- 随机小工具 ---------------------------------------------------------
    def money(self, low: int, high: int, step: int = 100) -> int:
        return self.rng.randrange(low, high + 1, step)

    def choice(self, seq: Sequence[Any]) -> Any:
        return self.rng.choice(list(seq))


# ---------------------------------------------------------------------------
# 人物设定
# ---------------------------------------------------------------------------
def _given_name(rng: random.Random, gender: str) -> str:
    a = rng.choice(GIVEN_CHAR_A)
    b = rng.choice(GIVEN_CHAR_B)
    if gender == "女" and rng.random() < 0.7 and b not in GIVEN_FEMALE_BIAS:
        b = rng.choice([c for c in GIVEN_CHAR_B if c in GIVEN_FEMALE_BIAS] or list(GIVEN_CHAR_B))
    if rng.random() < 0.22:                     # 约两成是单字名
        return a
    return a + b


def _full_name(rng: random.Random, gender: str) -> str:
    return rng.choice(SURNAMES) + _given_name(rng, gender)


def build_persona(rng: random.Random, index: int) -> Dict[str, Any]:
    gender = "女" if rng.random() < 0.5 else "男"
    name = _full_name(rng, gender)
    job_title, employer_type, industry = rng.choice(OCCUPATIONS)
    age = rng.randint(22, 68)
    relationship = rng.choices(
        ("单身", "恋爱中", "已婚", "异地恋", "离异"),
        weights=(22, 24, 38, 8, 8),
    )[0]
    partner_name = _full_name(rng, "男" if gender == "女" else "女") if relationship in ("恋爱中", "已婚", "异地恋") else ""
    partner_title = {"恋爱中": "恋人", "已婚": "配偶", "异地恋": "异地恋人"}.get(relationship, "")
    has_child = relationship == "已婚" and rng.random() < 0.62
    child_name = _full_name(rng, "女" if rng.random() < 0.5 else "男") if has_child else ""
    child_grade = rng.choice(("幼儿园中班", "小学二年级", "小学五年级", "初一", "初三", "高二")) if has_child else ""
    return {
        "persona_id": f"P_{GENERATOR_AGENT_ID}_{index:05d}",
        "name": name,
        "gender": gender,
        "age": age,
        "city": rng.choice(CITIES),
        "district": rng.choice(("老城区", "高新区", "经开区", "滨江新区", "城郊", "市中心")),
        "occupation": job_title,
        "employer_type": employer_type,
        "industry": industry,
        "company": f"{rng.choice(CITIES)}{rng.choice(('星澜', '中鼎', '恒越', '蓝湾', '拓维', '云图', '华宸', '锐驰'))}{rng.choice(('科技', '智能', '医疗', '智造', '数字', '新材'))}有限公司",
        "team_group": rng.choice(("研发中心大群", "项目组", "运营一组", "华东大区群", "门店管理群", "科室排班群")),
        "boss": _full_name(rng, "男" if rng.random() < 0.6 else "女"),
        "colleague": _full_name(rng, "男" if rng.random() < 0.5 else "女"),
        "best_friend": _full_name(rng, gender),
        "father": _full_name(rng, "男"),
        "mother": _full_name(rng, "女"),
        "relationship_status": relationship,
        "partner_name": partner_name,
        "partner_title": partner_title,
        "has_child": has_child,
        "child_name": child_name,
        "child_grade": child_grade,
        "monthly_income": rng.randrange(5000, 46001, 500),
        "commute_mode": rng.choice(COMMUTE_MODES),
        "commute_minutes": rng.randint(12, 78),
        "living_with": rng.choice(("独居", "与配偶同住", "与父母同住", "合租", "与配偶和孩子同住")),
        "pet": rng.choice(("", "", "", "一只金毛", "一只橘猫", "一只柯基")),
        "health_baseline": rng.choice(("良好", "良好", "亚健康", "轻度脂肪肝", "高血压一期", "甲状腺结节随访中", "轻度贫血")),
        "sleep_baseline_hours": round(rng.uniform(5.6, 8.0), 1),
        "resting_hr_baseline": rng.randint(52, 78),
        "personality": rng.choice(("内敛", "外向", "急躁", "温和", "要强", "随和")),
    }


# ---------------------------------------------------------------------------
# 琐碎日常噪声池（海量低信息量事件，不承载任何标答证据）
# ---------------------------------------------------------------------------
TriviaMic: Tuple[Tuple[str, str, str], ...] = (
    ("同事-{colleague}", "公司茶水间", "中午吃啥？{lunch}排队排到门外了。"),
    ("同事-{colleague}", "工位旁", "打印机又卡纸了，行政说下午来修。"),
    ("便利店店员", "楼下便利店", "袋子要吗？两毛。"),
    ("快递员", "小区门口", "你的件放{station}了，取件码一会儿发你。"),
    ("外卖骑手", "楼下", "您好，您的外卖放前台了，麻烦取一下。"),
    ("咖啡店店员", "{coffee}", "您点的冰美式好了，小心烫手。"),
    ("地铁报站", "地铁站台", "列车即将进站，请先下后上，注意站台间隙。"),
    ("保安", "小区门岗", "麻烦刷一下门禁，快递不能进楼。"),
    ("{colleague}", "电梯里", "今天这天儿，风大得能把人吹跑。"),
    ("食堂阿姨", "园区食堂", "红烧肉还有最后一份，要不要？"),
    ("{best_friend}", "电话", "在忙吗？没事，就问你周末有没有空打球。"),
    ("邻居", "楼道", "你家门口那袋垃圾我顺手带下去了。"),
    ("物业前台", "物业办公室", "停车费这个月涨了五十，扫码交就行。"),
    ("理发师", "理发店", "两边推短一点是吧？好嘞。"),
    ("药店店员", "连锁药房", "维C在第三排，保健品那边现在有买二送一。"),
    ("健身教练", "健身房", "今天练背还是练腿？"),
    ("水果摊老板", "小区门口", "橘子十块三斤，尝一个再买。"),
    ("洗车工", "洗车店", "精洗五十，二十分钟就好。"),
    ("公交报站", "公交车内", "下一站，人民广场，请提前做好准备。"),
    ("{mother}", "电话", "晚饭吃了吗？别老点外卖。"),
    ("同事-{colleague}", "会议室门口", "空调谁调的，冷得发抖。"),
    ("网约车司机", "车内", "前面堵得厉害，走辅路行吗？"),
    ("驿站店员", "{station}", "手机尾号多少？我帮你找找。"),
    ("超市收银员", "{market}", "会员积分抵两块，需要袋子吗？"),
    ("{best_friend}", "语音消息", "哈哈哈这视频笑死我了，你快看。"),
    ("同事-{colleague}", "工位旁", "团建定在下周五，AA一百五。"),
    ("快递员", "电话", "您那个件超重了，得补五块钱。"),
    ("门口保安", "公司大堂", "访客登记一下，身份证给我看看。"),
    ("早餐摊老板", "小区门口", "豆浆油条还是煎饼？"),
    ("药店收银", "连锁药房", "医保卡可以刷，感冒药在右手边。"),
    ("同事-{colleague}", "工位旁", "会议纪要发你了，你补两句。"),
    ("保洁阿姨", "办公楼走廊", "麻烦抬下脚，刚拖的地。"),
    ("{best_friend}", "电话", "我下周搬家，你有空来搭把手不？"),
    ("宠物店店员", "宠物店", "洗护要四十分钟，您可以先逛逛。"),
    ("加油站员工", "加油站", "加满还是两百？"),
    ("银行大堂经理", "银行网点", "取号排队，前面还有七位。"),
    ("快递员", "楼道", "您家没人，我先放门口了啊。"),
    ("修锁师傅", "小区门口", "换锁芯一百八，十分钟搞定。"),
    ("菜市场摊主", "菜市场", "排骨今天二十八一斤，来点？"),
    ("同事-{colleague}", "茶水间", "微波炉里那份是谁的，都凉了。"),
    ("网约车司机", "车内", "您系好安全带，我们出发了。"),
    ("快递柜提示音", "{station}", "请在24小时内取件，超时将收取保管费。"),
)

TriviaApp: Tuple[Tuple[str, str, str], ...] = (
    ("美团外卖", "美团外卖", "您的订单已送达，骑手已放置于{station}。"),
    ("支付宝", "支付宝", "今日消费一笔 {small} 元，商户：便利店。"),
    ("微信", "{colleague}", "那个文档我放共享盘了，你有空看下。"),
    ("微信", "{best_friend}", "【表情包】"),
    ("滴滴出行", "滴滴出行", "行程已结束，本次费用 {fare} 元。"),
    ("淘宝", "淘宝", "您关注的商品降价了，限时直降 {small} 元。"),
    ("京东", "京东", "您的包裹正在派送中，预计今天送达。"),
    ("日历", "系统日历", "提醒：{meeting}。"),
    ("天气", "系统天气", "今日{weather}，{temp_low}-{temp_high}℃，出门注意添衣。"),
    ("微信", "工作群-{team_group}", "@所有人 下班前把周报发到群里。"),
    ("拼多多", "拼多多", "帮我砍一刀！还差 0.08 元就能免费拿。"),
    ("健康", "系统健康", "今日已走 {steps_partial} 步，继续保持。"),
    ("网易云音乐", "网易云音乐", "年度听歌报告已生成。"),
    ("微信", "{mother}", "买了点水果，放冰箱了。"),
    ("饿了么", "饿了么", "红包即将过期，下单立减 {small} 元。"),
    ("共享单车", "共享单车", "本次骑行 {ride} 分钟，扣费 {bike} 元。"),
    ("快递", "菜鸟驿站", "您有一个包裹已到站，取件码 {code}。"),
    ("微信", "{colleague}", "在吗？帮我看下这个数对不对。"),
    ("12306", "12306", "您预订的车票出票成功。"),
    ("银行", "{bank}", "您尾号 {tail} 的账户支出 {small} 元，余额 {balance} 元。"),
    ("微信", "{best_friend}", "周末打球还去吗？场地我订好了。"),
    ("钉钉", "考勤打卡", "您已完成上班打卡，打卡时间正常。"),
    ("高德地图", "高德地图", "前方拥堵 1.2 公里，预计通过时间 12 分钟。"),
    ("微信", "{colleague}", "收到，我下午处理。"),
    ("美团", "美团", "您有一张 {small} 元优惠券即将到期。"),
    ("微信运动", "微信运动", "您今日共走 {steps_partial} 步，排名较昨日上升。"),
    ("国家电网", "网上国网", "本月电费 {small} 元，请及时缴纳。"),
    ("微信", "物业管家", "小区明天上午停水两小时，请提前储水。"),
    ("微博", "微博热搜", "您关注的话题新增 32 万讨论。"),
    ("12306", "12306", "您的候补订单已兑现，请注意查收。"),
    ("微信", "{mother}", "周末回来吃饭吗？给你炖汤。"),
)

BANKS = ("工商银行", "招商银行", "建设银行", "农业银行", "中国银行", "交通银行")
MEETINGS = ("周会", "项目复盘会", "客户需求对齐会", "月度经营分析会", "季度述职", "供应商评审会")


class _Slots(dict):
    """缺失槽位时保留占位符原文，交由出题自查（禁止残留花括号）拦截。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def emit_trivia(ctx: Ctx, count: int) -> None:
    """向三通道撒入 ``count`` 条琐碎日常噪声。"""
    rng = ctx.rng
    p = ctx.p
    slots = _Slots({
        "colleague": p["colleague"], "best_friend": p["best_friend"], "mother": p["mother"],
        "coffee": rng.choice(COFFEE_SHOPS), "station": rng.choice(EXPRESS_STATIONS),
        "market": rng.choice(SUPERMARKETS), "lunch": rng.choice(LUNCH_SPOTS),
        "team_group": p["team_group"], "weather": rng.choice(WEATHERS),
        "temp_low": rng.randint(-4, 22), "temp_high": rng.randint(12, 36),
        "meeting": rng.choice(MEETINGS), "bank": rng.choice(BANKS),
    })
    # 一天之内同一条琐碎台词只出现一次：先打乱池子再按需取用
    deck = [("mic", item) for item in TriviaMic] + [("app", item) for item in TriviaApp]
    rng.shuffle(deck)
    for kind, entry in deck[:count]:
        window = (DAY_START_MIN, DAY_END_MIN - 10)
        if kind == "mic":
            speaker, location, tpl = entry
            ctx.mic(
                "trivia", window, speaker.format(**slots), location.format(**slots), tpl.format(
                    **slots,
                    small=rng.randint(3, 180), fare=rng.randint(9, 68), ride=rng.randint(6, 34),
                    bike=rng.randint(1, 4), steps_partial=rng.randint(1200, 9800),
                    code="".join(str(rng.randint(0, 9)) for _ in range(4)),
                    tail="".join(str(rng.randint(0, 9)) for _ in range(4)),
                    balance=rng.randint(2000, 180000),
                ),
            )
        else:
            app_name, sender, tpl = entry
            ctx.app(
                "trivia", window, app_name, sender.format(**slots), tpl.format(
                    **slots,
                    small=rng.randint(3, 180), fare=rng.randint(9, 68), ride=rng.randint(6, 34),
                    bike=rng.randint(1, 4), steps_partial=rng.randint(1200, 9800),
                    code="".join(str(rng.randint(0, 9)) for _ in range(4)),
                    tail="".join(str(rng.randint(0, 9)) for _ in range(4)),
                    balance=rng.randint(2000, 180000),
                ),
            )
    # 常态维度锚点只引用少量琐碎碎片作为"这一天确实平淡"的佐证，
    # 绝不把全部琐碎碎片都算作证据（否则关键事件会被噪声淹没，题目失去区分度）。
    ctx.refs["trivia_sample"] = list(ctx.refs.get("trivia", []))[:3]


# ---------------------------------------------------------------------------
# 主线剧情：每一条都必须构成跨维度冲突或转折
# ---------------------------------------------------------------------------
def _a(dim: str, core: str, syn: Sequence[str], red: Sequence[str], tags: Sequence[str],
       ent: Sequence[str] = (), sev: int = 3) -> Anchor:
    """构造锚点。字符串入参一律归一化为单元素元组，避免 ``("x")`` 被拆成字符。"""
    def _one(value: Any) -> Tuple[Any, ...]:
        return (value,) if isinstance(value, str) else tuple(value)

    return Anchor(dim, core, _one(syn), _one(red), _one(tags), _one(ent), sev)


def _s_criticism_breakup(c: Ctx) -> List[Anchor]:
    p = c.p
    peak = c.rng.randint(118, 132)
    c.mic("crit", (9 * 60, 10 * 60), f"直属领导-{p['boss']}", c.choice(MEETING_ROOMS),
          f"{p['boss']}在{p['company']}当着整组人把方案拍在桌上：这版季度汇报重做，客户面前丢的是我的脸。", noise_db=58)
    c.app("crit_msg", (10 * 60, 10 * 60 + 40), "微信", f"工作群-{p['team_group']}",
          f"{p['boss']}：@{p['name']} 材料今晚十点前重出一版，明早客户会直接用。", session="群聊")
    c.mic("self_talk", (12 * 60 + 20, 13 * 60), f"佩戴者-{p['name']}", "楼梯间",
          f"{p['name']}自言自语：重做就重做，凭什么当众下我的面子。", channel="自语")
    c.app("cover", (14 * 60, 15 * 60), "微信", f"同事-{p['colleague']}",
          f"{p['colleague']}：别往心里去，{p['boss']}今天被大老板批了，火气冲着我们撒。")
    c.app("breakup_msg", (20 * 60 + 30, 21 * 60), "微信", f"{p['partner_title']}-{p['partner_name']}",
          f"{p['partner_name']}：我们分手吧，我想了很久，不是一时冲动。")
    c.mic("breakup_call", (21 * 60, 21 * 60 + 25), f"{p['partner_title']}-{p['partner_name']}", "出租屋楼下",
          f"{p['partner_name']}在电话里说：东西我明天来拿，别再联系我了。", noise_db=52)
    c.hr("hr_spike", (21 * 60 + 20, 21 * 60 + 45), peak)
    c.app("late_reply", (22 * 60, 23 * 60), "微信", f"直属领导-{p['boss']}",
          f"{p['boss']}：新版收到，比上一版像样，明早八点前发我邮箱。")
    c.mic("night", (23 * 60, 23 * 60 + 25), f"佩戴者-{p['name']}", "卧室",
          f"{p['name']}半夜翻来覆去：工作爱情一起塌，撑不下去了。", channel="自语")
    return [
        _a("global",
           f"{p['name']}上午在{p['company']}被{p['boss']}当众否定季度汇报，晚间遭{p['partner_name']}提出分手，事业与感情同日双重重挫，身心处于极度高压危机",
           ("工作受挫又遭遇分手", "职场打击叠加情感重创", "一天之内事业感情双双重挫", "被领导批评后又被恋人分手"),
           ("甜蜜约会", "晋升加薪", "升职庆祝", "一切顺利", "感情升温", "心情舒畅"),
           ("crit", "crit_msg", "breakup_msg", "breakup_call", "hr_spike"),
           (p["boss"], p["partner_name"], p["company"])),
        _a("dim:health",
           f"晨起静息心率平稳，晚间{hhmm(c.refs.get('hr_spike') and 0 or 0) or ''}21时前后心率骤升至{peak}bpm并持续数分钟，夜间入睡困难、睡眠时长明显缩短",
           ("晚间突发情绪性心动过速", "夜里心率飙高", "心率异常升高伴失眠", "应激性心率骤升"),
           ("全天心率平稳无波动", "体能状态极佳", "睡眠质量很好", "静息心率下降"),
           ("hr_spike", "night"), (f"{peak}bpm",)),
        _a("dim:social",
           f"与{p['partner_name']}的亲密关系当日破裂走向分手，同时与直属领导{p['boss']}出现公开的职业冲突，仅同事{p['colleague']}给予安慰",
           ("恋人关系破裂提出分手", "与领导公开冲突", "亲密关系终结", "情侣闹掰"),
           ("与恋人关系升温", "与领导关系融洽", "获得提拔赏识", "打情骂俏"),
           ("breakup_msg", "breakup_call", "crit", "cover"), (p["partner_name"], p["boss"], p["colleague"])),
        _a("dim:emotion",
           "情绪主基调为委屈与屈辱，白天压抑忍耐，晚间转为崩溃与绝望，深夜自我怀疑",
           ("委屈崩溃", "绝望压抑", "情绪跌到谷底", "委屈到撑不住"),
           ("心情愉悦", "兴奋激动", "平静无波", "得意洋洋", "轻松自在"),
           ("self_talk", "breakup_call", "night"), ()),
        _a("dim:finance",
           "当日仅有餐饮通勤一类日常小额支出，无工资外收入，也无新增大额债务",
           ("仅日常小额消费", "财务状况无重大变化", "无新增大额负债"),
           ("大额进账", "中彩票", "获得巨额奖金", "新增大额贷款", "资产大幅增值"),
           ("trivia_sample",), ()),
        _a("dim:career",
           f"季度汇报被{p['boss']}当众否决并要求当晚重做，工作目标受阻，面临客户会前的整改压力，深夜返工后勉强通过",
           ("季度汇报被否需重做", "工作成果被否决面临整改", "汇报材料返工", "被客户会议倒逼加班"),
           ("汇报顺利通过", "获得客户表扬", "项目提前交付", "得到晋升通知"),
           ("crit", "crit_msg", "late_reply"), (p["boss"],)),
    ]


def _s_quarterly_rejected_debt(c: Ctx) -> List[Anchor]:
    p = c.p
    c.steps_total = c.rng.randint(1200, 3600)          # 全天耗在会议室，步数必然很低
    repay = c.money(2000, 6000, 100)
    c.app("reject", (10 * 60, 11 * 60), "邮件", f"{p['boss']}",
          f"{p['boss']}：季度经营汇报未通过评审，数据口径混乱，三天内整改重报。")
    c.mic("crit", (11 * 60, 11 * 60 + 40), f"直属领导-{p['boss']}", c.choice(MEETING_ROOMS),
          f"{p['boss']}：口径都对不上，你让我怎么在会上替你说话？", noise_db=55)
    c.app("repay", (12 * 60 + 30, 13 * 60 + 30), "银行", c.choice(BANKS),
          f"信用卡本期应还{repay}元，还款日为今日24时前，逾期将影响征信。")
    c.app("repaid", (13 * 60, 14 * 60), "银行", c.choice(BANKS),
          f"您已成功还款{repay}元，本期账单结清，未产生逾期记录。")
    c.mic("father_call", (18 * 60, 19 * 60), f"父亲-{p['father']}", "电话",
          f"{p['father']}在电话里说：我今天在医院查出来要住院，你先别跟你妈说。", noise_db=48)
    c.hr("hr_up", (18 * 60 + 30, 19 * 60 + 30), c.rng.randint(102, 116))
    c.app("hospital", (19 * 60 + 30, 20 * 60 + 30), "微信", f"母亲-{p['mother']}",
          f"{p['mother']}：你爸住进{p['city']}市二院呼吸科了，医生说要观察三天。")
    c.mic("rework", (21 * 60, 22 * 60 + 30), f"同事-{p['colleague']}", "办公室",
          f"{p['colleague']}：数据我帮你重新拉一版，你先忙家里的事。")
    return [
        _a("global",
           f"{p['name']}季度汇报被{p['boss']}否决要求三日整改，同日按期偿还信用卡{repay}元，傍晚得知父亲{p['father']}住院，工作与家庭压力叠加",
           ("汇报被否又逢父亲住院", "职场受阻叠加家人住院", "工作整改与家庭变故同日发生"),
           ("全家出游", "升职加薪", "喜获大奖", "一切顺心", "家人身体健康"),
           ("reject", "crit", "repay", "father_call", "hospital"),
           (p["boss"], p["father"], f"{repay}元")),
        _a("dim:health",
           f"傍晚接到父亲住院消息后心率升至100bpm以上，全天仅{c.steps_total}步以室内久坐为主，夜间睡眠时长缩短至{c.persona['sleep_baseline_hours']}小时以下",
           ("傍晚心率明显升高", "应激性心率上升", "心率快伴睡眠变差", "久坐少动"),
           ("全天心率平稳", "运动量充足", "睡眠充足精神好", "步数创新高"),
           ("hr_up", "father_call", "sensor"), (f"{c.steps_total}步",)),
        _a("dim:social",
           f"与领导{p['boss']}因汇报质量产生职业矛盾，与父亲{p['father']}、母亲{p['mother']}的亲情牵挂加深，同事{p['colleague']}主动分担工作",
           ("与领导关系紧张", "家人患病牵挂加深", "同事伸出援手"),
           ("家庭关系破裂", "与同事翻脸", "被同事排挤"),
           ("crit", "father_call", "hospital", "rework"), (p["boss"], p["father"], p["mother"], p["colleague"])),
        _a("dim:emotion",
           "情绪以焦虑与自责为主，白天为工作挫败憋闷，傍晚因父亲病情转为担忧与愧疚",
           ("焦虑自责", "担忧愧疚", "压力大到喘不过气", "心力交瘁"),
           ("轻松愉快", "无忧无虑", "兴奋喜悦", "毫无压力"),
           ("crit", "father_call"), ()),
        _a("dim:finance",
           f"按期偿还信用卡{repay}元，账单结清未逾期，同时开始为父亲住院准备一笔医疗备用金",
           ("按时还清信用卡", "偿还信用卡账单未逾期", "为家人住院预备医疗费"),
           ("信用卡逾期", "新增大额负债", "资产大幅增值", "获得巨额收入"),
           ("repay", "repaid", "hospital"), (f"{repay}元",)),
        _a("dim:career",
           f"季度经营汇报未通过评审，被要求三天内整改重报，工作推进受阻并需连夜返工",
           ("汇报未通过需整改", "工作成果被打回", "限期重报材料"),
           ("汇报顺利通过", "获得表彰", "项目验收成功", "提前完成季度目标"),
           ("reject", "crit", "rework"), (p["boss"],)),
    ]


def _s_layoff_rumor_mortgage(c: Ctx) -> List[Anchor]:
    p = c.p
    c.steps_total = c.rng.randint(900, 3200)           # 一整天钉在工位上打听消息
    amount = c.money(6000, 15000, 500)
    borrow = c.money(10000, 50000, 5000)
    c.app("rumor", (9 * 60, 10 * 60), "微信", f"同事-{p['colleague']}",
          f"{p['colleague']}：听说这轮优化名单里有咱们组，你自己心里有个数。")
    c.mic("whisper", (10 * 60 + 20, 11 * 60), f"同事-{p['colleague']}", "茶水间",
          f"{p['colleague']}压低声音：HR昨天约谈了三个人，你别声张。", noise_db=60)
    c.app("mortgage_fail", (11 * 60, 12 * 60), "银行", c.choice(BANKS),
          f"您的住房贷款本期扣款{amount}元失败，原因：账户余额不足，请当日补足避免逾期上征信。")
    c.app("mortgage_ok", (12 * 60 + 30, 14 * 60), "银行", c.choice(BANKS),
          f"您已补足账户余额，住房贷款{amount}元扣款成功。")
    c.mic("friend_borrow", (21 * 60, 22 * 60), f"好友-{p['best_friend']}", "电话",
          f"{p['best_friend']}在电话里开口：能不能借我{borrow}周转两个月，我下月发奖金就还。", noise_db=50)
    c.hr("hr_up", (22 * 60, 23 * 60), c.rng.randint(96, 112))
    c.app("resume", (22 * 60 + 30, 23 * 60 + 20), "微信", f"{p['best_friend']}",
          f"{p['name']}：钱我这月真拿不出，房贷刚扣完。简历我先更新着。", direction="发送")
    return [
        _a("global",
           f"{p['name']}听闻所在组进入裁员优化名单，同日房贷{amount}元因余额不足首次扣款失败后补足，深夜又被好友{p['best_friend']}开口借{borrow}元，财务与职业安全感同时告急",
           ("裁员风声叠加房贷扣款失败", "职业危机与资金链紧张同日爆发", "被优化传闻加上朋友借钱"),
           ("获得晋升", "财务宽松", "升职加薪", "喜讯连连", "全款买房"),
           ("rumor", "whisper", "mortgage_fail", "friend_borrow"),
           (f"{amount}元", p["best_friend"], f"{borrow}")),
        _a("dim:health",
           f"夜间入睡困难，深夜心率持续偏高，全天久坐仅{c.steps_total}步，活动量明显不足",
           ("夜间心率偏高", "睡眠变差", "焦虑导致心率上升", "久坐少动"),
           ("睡眠质量极佳", "体能充沛", "全天心率平稳", "运动量充足"),
           ("hr_up", "resume", "sensor"), (f"{c.steps_total}步",)),
        _a("dim:social",
           f"与同事{p['colleague']}形成互通消息的同盟关系，与好友{p['best_friend']}因借钱请求出现微妙尴尬，关系未破裂但产生距离",
           ("同事互通裁员消息", "朋友借钱带来关系尴尬", "拒绝借款后关系微妙"),
           ("朋友慷慨相助", "关系更加亲密", "同事落井下石", "被朋友绝交"),
           ("whisper", "friend_borrow", "resume"), (p["colleague"], p["best_friend"])),
        _a("dim:emotion",
           "全天笼罩在不安全感与焦虑中，深夜转为对未来的恐慌与自我怀疑",
           ("焦虑不安", "恐慌自我怀疑", "心神不宁", "如坐针毡"),
           ("踏实安心", "志得意满", "轻松愉悦", "满怀信心"),
           ("whisper", "mortgage_fail", "friend_borrow"), ()),
        _a("dim:finance",
           f"住房贷款{amount}元首次扣款失败后当日补足，未产生逾期；同时婉拒好友{borrow}元借款请求，当月现金流极度紧张",
           ("房贷扣款失败后补足", "现金流紧张", "拒绝大额借款请求", "险些逾期"),
           ("房贷逾期上征信", "获得大额进账", "资金宽裕", "资产大幅增值"),
           ("mortgage_fail", "mortgage_ok", "friend_borrow", "resume"),
           (f"{amount}元", f"{borrow}")),
        _a("dim:career",
           "所在团队进入裁员优化传闻范围，职业稳定性受威胁，当晚开始更新简历准备后路",
           ("面临裁员风险", "岗位不保的危机感", "开始准备退路更新简历"),
           ("获得晋升机会", "被委以重任", "岗位稳固受重用", "涨薪通知"),
           ("rumor", "whisper", "resume"), ()),
    ]


def _s_launch_promotion_pressure(c: Ctx) -> List[Anchor]:
    p = c.p
    c.app("launch", (10 * 60, 11 * 60), "微信", f"工作群-{p['team_group']}",
          f"系统通知：版本已成功发布上线，监控无异常，恭喜各位。", session="群聊")
    c.mic("cheer", (11 * 60, 11 * 60 + 30), f"同事-{p['colleague']}", "工区",
          f"{p['colleague']}：终于上线了，这两个月的通宵没白熬。", noise_db=62)
    c.mic("promotion_talk", (15 * 60, 16 * 60), f"直属领导-{p['boss']}", c.choice(MEETING_ROOMS),
          f"{p['boss']}：晋升名额只有一个，你和另一个组在竞争，述职材料下周交。", noise_db=50)
    c.mic("mother_pressure", (19 * 60 + 30, 20 * 60 + 30), f"母亲-{p['mother']}", "家中客厅",
          f"{p['mother']}：你都{p['age']}了，相亲见一见怎么了？隔壁孩子都会打酱油了。", noise_db=48)
    c.mic("argue", (20 * 60 + 30, 21 * 60 + 20), f"佩戴者-{p['name']}", "家中客厅",
          f"{p['name']}提高声音：我今天刚上线一个大版本，你们只关心我结没结婚。", channel="自语")
    c.hr("hr_up", (20 * 60 + 40, 21 * 60 + 30), c.rng.randint(98, 114))
    c.app("makeup", (22 * 60, 23 * 60), "微信", f"母亲-{p['mother']}",
          f"{p['mother']}：妈不是逼你，就是怕你一个人。早点睡。")
    return [
        _a("global",
           f"{p['name']}主导的版本成功上线获得肯定，同日被{p['boss']}告知晋升名额需竞争述职，晚间又因催婚问题与母亲{p['mother']}争执，喜忧参半且情绪被拉扯",
           ("上线成功但晋升要竞争又被催婚", "事业小成同时家庭催婚冲突", "工作喜忧参半叠加亲子争执"),
           ("毫无波折的一天", "全家其乐融融", "直接升职无需竞争", "彻底失败"),
           ("launch", "promotion_talk", "mother_pressure", "argue"),
           (p["boss"], p["mother"])),
        _a("dim:health",
           "连续加班后疲劳度偏高，晚间争执时心率上升，夜间睡眠时长偏短",
           ("疲劳度高", "晚间心率上升", "睡眠不足"),
           ("精力充沛", "身体状态极佳", "睡眠质量优秀"),
           ("hr_up", "cheer", "argue"), ()),
        _a("dim:social",
           f"与团队因上线成功关系升温，与领导{p['boss']}进入晋升竞争关系，与母亲{p['mother']}因催婚发生争执但当晚和解",
           ("团队关系升温", "与母亲因催婚争执", "亲子冲突后和解", "与领导形成竞争关系"),
           ("与母亲关系彻底破裂", "被团队孤立", "断绝亲子关系"),
           ("cheer", "promotion_talk", "mother_pressure", "argue", "makeup"),
           (p["boss"], p["mother"], p["colleague"])),
        _a("dim:emotion",
           "白天因上线成功感到成就与兴奋，晚间因催婚转为烦躁委屈，深夜在和解中平复",
           ("先喜后烦", "成就感与委屈交织", "烦躁委屈", "情绪起伏大"),
           ("全程低落绝望", "毫无情绪波动", "极度愤怒失控"),
           ("cheer", "argue", "makeup"), ()),
        _a("dim:finance",
           "当日为庆祝上线产生一笔团队聚餐支出，晋升结果未定因此暂无涨薪落地",
           ("仅有聚餐一类支出", "收入暂无变化", "晋升未定薪资未变"),
           ("工资大幅上涨", "获得巨额奖金", "新增大额负债", "资产大幅增值"),
           ("trivia_sample", "launch"), ()),
        _a("dim:career",
           f"版本成功上线是重要正向进展，但晋升名额需与另一组竞争述职，工作目标推进一半并带来新的压力",
           ("版本上线成功", "晋升需要竞争述职", "职业发展出现机会与压力并存"),
           ("直接晋升成功", "项目失败被追责", "被裁撤", "工作毫无进展"),
           ("launch", "promotion_talk"), (p["boss"],)),
    ]


def _s_headhunter_noncompete(c: Ctx) -> List[Anchor]:
    p = c.p
    offer = c.money(25, 60, 1)
    c.mic("headhunter", (10 * 60 + 30, 11 * 60 + 30), "猎头顾问", "电话",
          f"猎头顾问：对方给到年薪{offer}万，比你现在高四成，就是竞业协议得先看清楚。", noise_db=54)
    c.app("jd", (11 * 60, 12 * 60), "微信", "猎头顾问",
          f"猎头顾问：岗位说明我发你了，下周安排一次电话面，先别告诉现单位。")
    c.mic("boss_probe", (15 * 60, 16 * 60), f"直属领导-{p['boss']}", "走廊",
          f"{p['boss']}：最近有人找你聊跳槽？咱们组明年有个新项目，我正想让你牵头。", noise_db=58)
    c.app("contract", (16 * 60 + 30, 17 * 60 + 30), "邮件", "人力资源部",
          f"您签署的竞业限制协议约定：离职后12个月内不得入职直接竞争对手，违约金为离职前年薪的两倍。")
    c.hr("hr_up", (16 * 60 + 30, 17 * 60), c.rng.randint(94, 108))
    c.mic("friend_advice", (21 * 60, 22 * 60), f"好友-{p['best_friend']}", "烧烤摊",
          f"{p['best_friend']}：竞业违约金两年年薪，你敢赌吗？我劝你先谈补偿。", noise_db=72)
    return [
        _a("global",
           f"{p['name']}接到猎头年薪{offer}万的挖角邀约，但受制于12个月竞业限制条款，同时被领导{p['boss']}试探性挽留并许诺新项目，去留两难",
           ("挖角机会与竞业限制冲突", "被挖角又面临竞业约束", "跳槽机会遭遇合同束缚"),
           ("毫无职业机会", "顺利跳槽无任何阻碍", "被公司开除", "安心躺平"),
           ("headhunter", "contract", "boss_probe"), (f"{offer}万", p["boss"])),
        _a("dim:health",
           "午后得知竞业条款时心率上升，全天用脑强度高，夜间思虑过多入睡偏晚",
           ("午间心率上升", "精神紧张", "入睡偏晚"),
           ("全天心率平稳", "身心放松", "睡眠极佳"),
           ("hr_up", "contract"), ()),
        _a("dim:social",
           f"与猎头建立新的职业联系，与领导{p['boss']}之间产生试探与不信任，与好友{p['best_friend']}就风险进行深谈",
           ("与领导互相试探", "获得外部职业人脉", "与好友深谈决策"),
           ("与领导坦诚相待", "关系彻底破裂", "被同事举报"),
           ("boss_probe", "friend_advice", "headhunter"), (p["boss"], p["best_friend"])),
        _a("dim:emotion",
           "情绪在兴奋与犹豫之间反复，既渴望更高薪酬又担忧违约风险，整体处于纠结拉扯状态",
           ("纠结拉扯", "兴奋又担忧", "犹豫不决", "内心矛盾"),
           ("毫无波澜", "果断决绝", "极度恐惧", "心如死灰"),
           ("headhunter", "contract", "friend_advice"), ()),
        _a("dim:finance",
           f"潜在年薪{offer}万的增收机会尚未落地，竞业违约金为离职前年薪两倍构成重大或有负债，当日实际收支无变化",
           ("潜在涨薪未落地", "面临竞业违约金的或有负债", "当日收支无实际变化"),
           ("已获得大额涨薪", "已支付巨额违约金", "新增大额负债", "资产大幅缩水"),
           ("headhunter", "contract"), (f"{offer}万",)),
        _a("dim:career",
           "外部挖角带来明显向上的职业机会，但受竞业限制与领导挽留双重牵制，职业路径进入关键抉择期",
           ("获得外部挖角机会", "职业发展面临抉择", "被领导挽留许诺新项目"),
           ("已被裁员", "职业毫无起色", "已正式离职", "晋升已确定"),
           ("headhunter", "boss_probe", "contract"), (p["boss"],)),
    ]


def _s_customer_complaint(c: Ctx) -> List[Anchor]:
    p = c.p
    claim = c.money(3, 30, 1)
    c.mic("complaint", (9 * 60 + 30, 10 * 60 + 30), "客户方负责人", "电话",
          f"客户方负责人：这批交付有质量事故，我们要索赔{claim}万，今天必须给说法。", noise_db=56)
    c.app("complaint_mail", (10 * 60, 11 * 60), "邮件", "客户方采购部",
          f"关于交付质量问题的正式函件：保留索赔{claim}万元的权利，请贵司24小时内书面回复。")
    c.mic("boss_blame", (11 * 60, 12 * 60), f"直属领导-{p['boss']}", c.choice(MEETING_ROOMS),
          f"{p['boss']}：这事你先顶着，把责任链梳理清楚再说。", noise_db=55)
    c.mic("overtime", (21 * 60, 23 * 60), f"同事-{p['colleague']}", "办公室",
          f"{p['colleague']}：报告初稿写完了，你先回去睡，明早我改。", noise_db=50)
    c.imu("commute_bump", (23 * 60, 23 * 60 + 25), round(c.rng.uniform(1.4, 2.2), 2))
    c.hr("hr_up", (10 * 60, 11 * 60), c.rng.randint(104, 118))
    c.app("taxi", (23 * 60 + 10, 23 * 60 + 29), "网约车", "网约车平台",
          f"行程已结束，本次费用{c.money(28, 76, 2)}元，感谢您深夜乘车。")
    return [
        _a("global",
           f"{p['name']}上午遭遇客户方就交付质量事故提出{claim}万元索赔，被领导{p['boss']}要求独自顶住责任，加班至深夜23点后才打车回家，全天处于高压救火状态",
           ("客户索赔引发全天救火", "质量事故索赔叠加加班", "被客户追责又被迫顶锅"),
           ("客户关系融洽", "顺利结项", "轻松的一天", "获得客户表扬"),
           ("complaint", "complaint_mail", "boss_blame", "overtime"),
           (f"{claim}万", p["boss"])),
        _a("dim:health",
           f"上午接到索赔电话时心率升至100bpm以上，全天连续工作超过12小时，深夜才结束，疲劳度极高",
           ("长时间加班极度疲劳", "心率升高", "工作时间过长"),
           ("作息规律", "精力充沛", "睡眠质量好"),
           ("hr_up", "overtime", "taxi"), ()),
        _a("dim:social",
           f"与客户方关系因质量事故转为对立，与领导{p['boss']}之间存在责任推诿的紧张，同事{p['colleague']}深夜并肩支持",
           ("客户关系转差", "与领导关系紧张", "同事并肩作战"),
           ("客户关系升温", "获得领导力挺", "被同事背叛"),
           ("complaint", "boss_blame", "overtime"), (p["boss"], p["colleague"])),
        _a("dim:emotion",
           "情绪以紧张、焦灼与委屈为主，被迫独自承担压力，深夜出现明显的疲惫与无力感",
           ("焦灼紧张", "委屈无力", "压力巨大", "心力交瘁"),
           ("轻松愉快", "得意满足", "毫无压力", "兴奋激动"),
           ("boss_blame", "overtime"), ()),
        _a("dim:finance",
           f"公司面临{claim}万元索赔的或有损失，个人当日仅有深夜打车一类支出，尚无个人债务变动",
           ("面临客户索赔的或有损失", "个人当日仅小额支出", "个人债务无变化"),
           ("个人获得大额进账", "个人新增大额负债", "索赔已完成赔付", "资产大幅增值"),
           ("complaint_mail", "taxi"), (f"{claim}万",)),
        _a("dim:career",
           "交付质量事故导致工作目标严重受阻，需在24小时内出具书面回复并梳理责任链，职业声誉与考核同时承压",
           ("质量事故导致工作受阻", "限期书面回复客户", "面临责任追责风险"),
           ("项目顺利交付", "获得客户续约", "工作进展顺利", "获得表彰"),
           ("complaint", "complaint_mail", "boss_blame"), (p["boss"],)),
    ]


# ---------------------------------------------------------------------------
# 常态维度锚点（当天该维度无重大变化时使用，仍必须给方向标答）
# ---------------------------------------------------------------------------
def _health_routine(c: Ctx, note: str = "") -> Anchor:
    p = c.p
    core = (f"全天体征基本平稳，晨起静息心率与平日相当，{note}" if note
            else f"全天体征基本平稳，晨起静息心率{p['resting_hr_baseline']}bpm与平日相当，无明显异常波动")
    return _a("dim:health", core,
              ("体征平稳无异常", "心率与平日相当", "身体状态与平时差不多"),
              ("突发心率骤升", "疑似心脏事件", "严重身体不适", "体征显著恶化"),
              ("trivia_sample",), (f"{p['resting_hr_baseline']}bpm",) if not note else (), sev=1)


def _social_routine(c: Ctx, note: str = "") -> Anchor:
    p = c.p
    core = note or f"人际关系无重大变化，与同事{p['colleague']}维持正常协作，家人联系如常"
    return _a("dim:social", core,
              ("人际关系平稳", "社交状态与平日一致", "无重大人际变化"),
              ("关系彻底破裂", "发生激烈冲突", "断绝往来", "社交全面崩塌"),
              ("trivia_sample",), (), sev=1)


def _emotion_routine(c: Ctx, note: str = "") -> Anchor:
    core = note or "情绪主基调平稳，偶有琐事带来的轻微烦躁，整体可控"
    return _a("dim:emotion", core,
              ("情绪平稳", "心情总体平和", "情绪波动不大"),
              ("崩溃绝望", "极度愤怒失控", "情绪剧烈震荡", "彻底绝望"),
              ("trivia_sample",), (), sev=1)


def _finance_routine(c: Ctx, note: str = "") -> Anchor:
    core = note or "当日仅有餐饮通勤等日常小额支出，无新增收入，也无新增大额债务"
    return _a("dim:finance", core,
              ("仅日常小额消费", "财务无重大变化", "无新增大额负债"),
              ("大额进账", "新增巨额负债", "资产大幅增值", "发生巨额赔付"),
              ("trivia_sample",), (), sev=1)


def _career_routine(c: Ctx, note: str = "") -> Anchor:
    p = c.p
    core = note or f"按既定节奏推进{p['occupation']}的日常工作，无重大进展也无明显受阻"
    return _a("dim:career", core,
              ("工作按部就班", "无重大进展也无受阻", "常规推进本职工作"),
              ("获得重大晋升", "被辞退", "项目彻底失败", "工作全面停滞"),
              ("trivia_sample",), (), sev=1)


# ---------------------------------------------------------------------------
# 主线剧情（续）
# ---------------------------------------------------------------------------
def _s_intern_blame(c: Ctx) -> List[Anchor]:
    p = c.p
    c.mic("blame", (10 * 60, 11 * 60), f"直属领导-{p['boss']}", c.choice(MEETING_ROOMS),
          f"{p['boss']}：这个锅你别急着背，是谁改的线上配置查日志。", noise_db=55)
    c.app("intern_cry", (11 * 60 + 30, 12 * 60 + 30), "微信", "实习生-小周",
          f"实习生-小周：哥对不起，是我把测试配置推到线上了，你帮我跟{p['boss']}说一声。")
    c.mic("team_conflict", (14 * 60, 15 * 60), f"同事-{p['colleague']}", "工区",
          f"{p['colleague']}：流程摆在那儿，谁签字谁负责，你不能什么都护着。", noise_db=64)
    c.hr("hr_up", (14 * 60, 15 * 60), c.rng.randint(92, 106))
    c.app("apology", (22 * 60, 23 * 60), "微信", "实习生-小周",
          f"实习生-小周：我写了份复盘发你邮箱了，明天我在会上自己说。")
    c.mic("apology_call", (22 * 60 + 20, 23 * 60 + 10), f"佩戴者-{p['name']}", "家中",
          f"{p['name']}在电话里说：责任我担一半，你别一个人扛。", channel="自语")
    return [
        _a("global",
           f"线上配置事故爆发，实习生小周误操作，{p['name']}在领导{p['boss']}与同事{p['colleague']}之间承受追责压力，深夜与实习生沟通共同担责，团队内部出现分歧",
           ("线上事故追责引发团队分歧", "实习生闯祸导致内部矛盾", "事故复盘中的责任拉锯"),
           ("毫无事故的一天", "团队一团和气", "获得集体表彰", "顺利上线无任何问题"),
           ("blame", "intern_cry", "team_conflict", "apology"),
           (p["boss"], p["colleague"])),
        _a("dim:health",
           "午后争执时心率上升，全天精神紧绷，夜间因复盘材料推迟入睡",
           ("午后心率上升", "精神紧绷", "入睡推迟"),
           ("全天心率平稳", "身心放松", "作息规律"),
           ("hr_up", "team_conflict"), ()),
        _a("dim:social",
           f"与同事{p['colleague']}因责任归属产生明显分歧，与实习生小周形成保护与被保护的关系，与领导{p['boss']}维持克制沟通",
           ("与同事产生分歧", "维护实习生", "团队内部矛盾"),
           ("团队高度团结", "与同事关系升温", "把实习生推出去背锅"),
           ("team_conflict", "intern_cry", "apology", "apology_call"), (p["colleague"], p["boss"])),
        _a("dim:emotion",
           "情绪以压抑、为难与自责为主，既要保护新人又要面对同事指责，内心矛盾",
           ("为难压抑", "自责矛盾", "憋屈"),
           ("轻松愉快", "理直气壮", "毫无压力", "兴奋得意"),
           ("team_conflict", "apology_call"), ()),
        _finance_routine(c, "当日仅日常支出，事故赔付由公司承担，个人无债务变动"),
        _a("dim:career",
           "线上事故导致当日排期全部让位于复盘与整改，需在会上说明责任链，个人考核面临扣分风险",
           ("事故导致排期受阻", "需承担复盘与整改", "考核面临扣分风险"),
           ("项目顺利推进", "获得表彰", "排期提前完成", "被提拔重用"),
           ("blame", "team_conflict", "apology"), (p["boss"],)),
    ]


def _s_trip_delay_leak(c: Ctx) -> List[Anchor]:
    p = c.p
    cost = c.money(300, 2600, 50)
    c.app("delay", (7 * 60 + 30, 8 * 60 + 30), "12306", "12306",
          f"您乘坐的G{c.rng.randint(100, 8999)}次列车因设备故障晚点约{c.rng.randint(40, 150)}分钟。")
    c.mic("station", (8 * 60, 9 * 60), "候车厅广播", "高铁站候车厅",
          f"广播：因线路设备故障，部分列车晚点，请旅客留意显示屏信息。", noise_db=76)
    c.app("leak", (13 * 60, 14 * 60), "微信", "物业管家",
          f"物业管家：您家卫生间水管爆裂，已经渗到楼下，麻烦尽快回来处理，初步维修费约{cost}元。")
    c.mic("leak_call", (13 * 60 + 20, 14 * 60 + 20), "楼下邻居", "电话",
          f"楼下邻居：你家水把我天花板泡了，你得负责。", noise_db=52)
    c.hr("hr_up", (13 * 60 + 20, 14 * 60 + 30), c.rng.randint(100, 116))
    c.app("repair", (19 * 60, 20 * 60), "微信", "维修师傅",
          f"维修师傅：管子换了，材料加人工一共{cost}元，楼下那边你自己谈。")
    c.mic("client_angry", (20 * 60 + 30, 21 * 60 + 30), "客户方对接人", "电话",
          f"客户方对接人：你人没到现场，会怎么开？这项目我们很被动。", noise_db=54)
    return [
        _a("global",
           f"{p['name']}出差途中遭遇高铁大面积晚点，同日家中水管爆裂渗漏到楼下需赔付维修{cost}元，客户方又因缺席现场会议表达不满，行程、家庭与工作三线同时失守",
           ("出差受阻叠加家中漏水", "行程延误与家庭突发事故叠加", "三线同时出问题的一天"),
           ("行程顺利", "家中一切安好", "客户高度满意", "轻松出差"),
           ("delay", "leak", "leak_call", "client_angry"), (f"{cost}元",)),
        _a("dim:health",
           "长途奔波加突发事故导致疲劳度偏高，午间心率上升，夜间睡眠质量下降",
           ("疲劳度偏高", "午间心率上升", "睡眠变差"),
           ("精力充沛", "作息规律", "身体状态极佳"),
           ("hr_up", "station"), ()),
        _a("dim:social",
           "与楼下邻居因渗漏产生赔偿纠纷，与物业保持协调关系，与客户方对接人关系因缺席而紧张",
           ("与邻里产生纠纷", "与客户关系紧张", "需协调物业处理"),
           ("邻里关系融洽", "客户高度认可", "人际全面和谐"),
           ("leak_call", "leak", "client_angry"), ()),
        _a("dim:emotion",
           "情绪以焦躁与无力为主，行程延误与家庭事故接连打击，出现明显的心烦意乱",
           ("焦躁无力", "心烦意乱", "接连打击下的烦躁"),
           ("从容淡定", "心情愉悦", "毫无波澜"),
           ("station", "leak_call", "client_angry"), ()),
        _a("dim:finance",
           f"因家中水管爆裂产生维修与赔付支出约{cost}元，高铁改签带来额外交通费用，属计划外的突发性支出",
           ("突发维修赔付支出", "计划外支出增加", "承担邻里赔偿"),
           ("大额进账", "资产大幅增值", "无任何额外支出", "获得赔偿收入"),
           ("leak", "repair", "delay"), (f"{cost}元",)),
        _a("dim:career",
           "因列车晚点未能按时抵达客户现场，会议缺席导致项目推进被动，职业可靠度受到质疑",
           ("因延误缺席客户会议", "项目推进被动", "职业可靠度受质疑"),
           ("客户会议顺利完成", "项目进展顺利", "获得客户表扬"),
           ("delay", "client_angry"), ()),
    ]


def _s_checkup_nodule(c: Ctx) -> List[Anchor]:
    p = c.p
    size = round(c.rng.uniform(0.6, 1.8), 1)
    c.app("report", (9 * 60, 10 * 60), "医院公众号", f"{p['city']}市第一人民医院",
          f"体检报告已出：甲状腺左叶结节{size}cm，TI-RADS 3类，建议3个月后复查超声。")
    c.mic("doctor", (10 * 60 + 30, 11 * 60 + 30), "体检科医生", "诊室",
          f"体检科医生：3类基本是良性，别自己吓自己，按时复查就行。", noise_db=50)
    c.app("search", (12 * 60, 13 * 60), "浏览器", "搜索引擎",
          f"搜索记录：甲状腺结节3类会不会癌变 / 结节{size}cm需要手术吗")
    c.hr("hr_up", (12 * 60, 13 * 60), c.rng.randint(96, 110))
    c.mic("mother_worry", (19 * 60, 20 * 60), f"母亲-{p['mother']}", "电话",
          f"{p['mother']}：结节听着吓人，你赶紧去大医院再看一次，别拖。", noise_db=48)
    c.app("booking", (20 * 60 + 30, 21 * 60 + 30), "医院公众号", "省肿瘤医院",
          f"预约成功：甲状腺外科专家门诊，就诊时间三日后上午。")
    c.mic("work_push", (15 * 60, 16 * 60), f"同事-{p['colleague']}", "工区",
          f"{p['colleague']}：这周上线窗口就三天，你那块得盯紧点。", noise_db=62)
    return [
        _a("global",
           f"{p['name']}体检发现甲状腺左叶{size}cm结节被建议三个月后复查，自行搜索后陷入健康焦虑，母亲{p['mother']}催促进一步就诊，同时工作上线窗口逼近，健康担忧与工作压力并行",
           ("体检查出结节引发健康焦虑", "体检异常叠加工作压力", "健康警报与工作冲刺同日"),
           ("体检完全正常", "身体健康无任何问题", "毫无压力的一天", "确诊重症"),
           ("report", "search", "mother_worry", "work_push"), (f"{size}cm", p["mother"])),
        _a("dim:health",
           f"体检发现甲状腺左叶{size}cm结节（TI-RADS 3类），需三个月后复查，当日因担忧出现心率上升与食欲下降",
           ("体检查出甲状腺结节需复查", "发现结节需定期随访", "健康指标出现异常需观察"),
           ("体检各项完全正常", "确诊恶性肿瘤", "身体机能显著增强", "无需任何复查"),
           ("report", "doctor", "booking"), (f"{size}cm",)),
        _a("dim:social",
           f"母亲{p['mother']}因担忧而反复叮嘱并催促就诊，家人关切加深，同事{p['colleague']}并不知情仍照常催进度",
           ("家人关切加深", "母亲催促就诊", "工作圈不知情"),
           ("家人漠不关心", "家庭关系破裂", "同事集体排挤"),
           ("mother_worry", "work_push"), (p["mother"], p["colleague"])),
        _a("dim:emotion",
           "因体检结果产生明显健康焦虑，反复搜索加重担忧，情绪由平静转为不安，夜间难以放松",
           ("健康焦虑", "担忧不安", "反复查证加重焦虑"),
           ("心情愉悦", "毫无担忧", "兴奋激动", "彻底绝望"),
           ("search", "mother_worry", "report"), ()),
        _finance_routine(c, "当日产生一笔体检与专家门诊挂号支出，金额不大，无新增大额债务"),
        _a("dim:career",
           f"工作上线窗口仅剩三天，{p['name']}需在健康担忧中继续盯紧关键模块，工作推进未受阻但心理负担加重",
           ("上线窗口紧张需盯进度", "工作照常推进但负担加重", "关键节点压力"),
           ("项目提前完成", "获得晋升", "工作全面停滞", "被调离关键岗位"),
           ("work_push",), ()),
    ]


def _s_nocturnal_palpitation(c: Ctx) -> List[Anchor]:
    p = c.p
    peak = c.rng.randint(126, 148)
    c.hr("hr_night", (22 * 60, 23 * 60 + 20), peak)
    c.app("watch_alert", (22 * 60 + 10, 23 * 60 + 25), "健康", "手环",
          f"心率异常提醒：静息状态下心率达{peak}bpm，持续超过10分钟，建议关注。")
    c.mic("alone", (22 * 60 + 30, 23 * 60 + 20), f"佩戴者-{p['name']}", "卧室",
          f"{p['name']}喘着气说：心跳得厉害，屋里就我一个人，要不要打电话。", channel="自语")
    c.mic("friend_call", (23 * 60, 23 * 60 + 28), f"好友-{p['best_friend']}", "电话",
          f"{p['best_friend']}：你别睡，我陪你说话，实在不行现在就打120。", noise_db=44)
    c.app("coffee_late", (16 * 60, 17 * 60), "美团外卖", "咖啡店",
          f"您下单一杯超大杯冰美式（加浓），已于16时送达。")
    c.mic("overtime", (18 * 60, 20 * 60), f"同事-{p['colleague']}", "办公室",
          f"{p['colleague']}：再撑一小时就发版了，咖啡我帮你点了。", noise_db=58)
    return [
        _a("global",
           f"{p['name']}连续加班并下午摄入加浓咖啡，深夜独居时静息心率骤升至{peak}bpm并收到手环报警，仅能靠好友{p['best_friend']}电话陪伴，独居健康风险凸显",
           ("独居深夜心悸发作", "夜间心率骤升无人照护", "加班加咖啡后夜间心脏不适"),
           ("全天身体无恙", "家人在旁照料", "睡眠安稳", "毫无异常"),
           ("hr_night", "watch_alert", "alone", "friend_call"), (f"{peak}bpm", p["best_friend"])),
        _a("dim:health",
           f"深夜静息状态心率骤升至{peak}bpm并持续十分钟以上，手环发出异常提醒，疑似与过量咖啡因及熬夜相关的阵发性心悸",
           (f"夜间静息心率骤升至{peak}bpm", "深夜心悸发作", "心率异常伴手环报警", "疑似阵发性心动过速"),
           ("全天心率平稳", "体能状态极佳", "睡眠质量优秀", "心率偏低"),
           ("hr_night", "watch_alert", "coffee_late"), (f"{peak}bpm",)),
        _a("dim:social",
           f"独居状态下缺少同住照护，紧急时刻仅依赖好友{p['best_friend']}电话陪伴，暴露独居支持网络薄弱",
           ("独居缺少照护", "依赖好友远程陪伴", "社会支持薄弱"),
           ("家人全程陪伴", "支持网络充足", "多人现场照护"),
           ("alone", "friend_call"), (p["best_friend"],)),
        _a("dim:emotion",
           "深夜突发心悸时产生强烈恐惧与孤独感，担心独自出事无人知晓，情绪接近恐慌",
           ("恐惧孤独", "担心独自出事", "接近恐慌", "惊慌无助"),
           ("平静安详", "心情愉悦", "毫无担忧", "兴奋激动"),
           ("alone", "friend_call"), ()),
        _finance_routine(c, "当日仅有咖啡外卖一类小额支出，未发生就医费用"),
        _a("dim:career",
           f"为赶发版窗口连续加班至晚间，工作强度过高是当日身体异常的重要诱因，项目本身按期发版",
           ("为发版连续加班", "工作强度过高", "项目按期发版但代价大"),
           ("工作轻松无压力", "项目延期失败", "获得休假", "被裁撤"),
           ("overtime", "coffee_late"), ()),
    ]


def _s_bp_recheck_drinking(c: Ctx) -> List[Anchor]:
    p = c.p
    sys_bp, dia_bp = c.rng.randint(138, 158), c.rng.randint(88, 99)
    c.app("bp", (8 * 60, 9 * 60), "健康", "血压计",
          f"今日晨起血压{sys_bp}/{dia_bp}mmHg，高于您近30天均值，建议复测。")
    c.mic("doctor", (10 * 60, 11 * 60), "社区医生", "社区卫生服务中心",
          f"社区医生：低压快到100了，酒必须停，盐减半，两周后回来复测。", noise_db=52)
    c.mic("dinner_drink", (18 * 60 + 30, 20 * 60), "客户方负责人", "饭店包间",
          f"客户方负责人：这杯不喝就是不给我面子，合同的事好说。", noise_db=78)
    c.mic("refuse", (19 * 60, 20 * 60), f"佩戴者-{p['name']}", "饭店包间",
          f"{p['name']}：真不行，医生让我停酒，我以茶代酒敬您。", channel="自语")
    c.hr("hr_up", (19 * 60, 20 * 60), c.rng.randint(96, 110))
    c.app("wife", (21 * 60, 22 * 60), "微信", f"{p['partner_title']}-{p['partner_name']}",
          f"{p['partner_name']}：又应酬？血压那样了还去，你自己看着办。") if p["partner_name"] else c.app("wife", (21 * 60, 22 * 60), "微信", f"母亲-{p['mother']}", f"{p['mother']}：别喝酒了，命重要。")
    return [
        _a("global",
           f"{p['name']}晨起血压升至{sys_bp}/{dia_bp}mmHg并被社区医生要求停酒限盐，晚间却不得不出席客户应酬以茶代酒，健康管理与人情应酬直接冲突",
           ("血压升高却被劝酒", "健康警示与应酬冲突", "医嘱与饭局正面相撞"),
           ("身体完全健康", "饮酒尽兴", "毫无冲突的一天", "确诊重症住院"),
           ("bp", "doctor", "dinner_drink", "refuse"), (f"{sys_bp}/{dia_bp}mmHg",)),
        _a("dim:health",
           f"晨起血压{sys_bp}/{dia_bp}mmHg明显高于近30天均值，医生要求停酒限盐并两周后复测，属需要干预的血压升高",
           ("血压偏高需干预", "血压高于平时需复查", "需停酒限盐控制血压"),
           ("血压完全正常", "血压偏低", "无需任何干预", "血压指标改善"),
           ("bp", "doctor"), (f"{sys_bp}/{dia_bp}mmHg",)),
        _a("dim:social",
           f"与客户方维持需要应酬的人情关系，因拒酒略感尴尬但未失礼，家人{p['partner_name'] or p['mother']}对饮酒行为明确不满",
           ("应酬人情压力", "因拒酒略显尴尬", "家人不满饮酒"),
           ("家人支持饮酒", "客户关系破裂", "社交全面和谐无压力"),
           ("dinner_drink", "refuse", "wife"), (p["partner_name"] or p["mother"],)),
        _a("dim:emotion",
           "情绪以无奈与自我克制为主，既担心身体又怕得罪客户，席间压抑，回家后感到疲惫",
           ("无奈压抑", "自我克制", "两难疲惫"),
           ("尽兴愉悦", "毫无压力", "兴奋激动", "彻底放松"),
           ("refuse", "dinner_drink", "wife"), ()),
        _finance_routine(c, "当日晚宴为公司招待支出，个人仅通勤一类小额消费，无债务变动"),
        _a("dim:career",
           f"为维系客户关系出席应酬并保住合同机会，职业关系维护有进展，但以牺牲健康管理为代价",
           ("以应酬维系客户关系", "为业务牺牲健康", "合同机会有进展"),
           ("客户流失", "项目终止", "工作毫无进展", "获得晋升"),
           ("dinner_drink", "refuse"), ()),
    ]


def _s_parent_fall_leave(c: Ctx) -> List[Anchor]:
    p = c.p
    c.mic("fall_call", (10 * 60 + 30, 11 * 60 + 30), f"母亲-{p['mother']}", "电话",
          f"{p['mother']}在电话里哭：你爸在卫生间摔了，爬不起来，我扶不动他。", noise_db=46)
    c.app("hospital", (12 * 60, 13 * 60), "微信", f"母亲-{p['mother']}",
          f"{p['mother']}：拍片说髋部有裂纹，医生说要先卧床，得有人看着。")
    c.imu("rush", (11 * 60 + 30, 12 * 60 + 30), round(c.rng.uniform(1.6, 2.4), 2))
    c.hr("hr_up", (11 * 60, 12 * 60), c.rng.randint(108, 124))
    c.mic("boss_refuse", (14 * 60, 15 * 60), f"直属领导-{p['boss']}", "电话",
          f"{p['boss']}：这周上线走不开，你先请半天，剩下的周末补。", noise_db=54)
    c.app("leave", (14 * 60 + 30, 15 * 60 + 30), "OA系统", "人力资源部",
          f"您的请假申请（事假1天）已被驳回，理由：项目关键期人力紧张。")
    c.mic("night_care", (21 * 60, 22 * 60 + 30), f"父亲-{p['father']}", "医院病房",
          f"{p['father']}：我没事，你回去上班，别耽误正事。", noise_db=48)
    return [
        _a("global",
           f"{p['name']}上午接到母亲{p['mother']}电话得知父亲{p['father']}在卫生间跌倒致髋部裂纹，请假陪护却被领导{p['boss']}以项目关键期驳回，只能白天上班夜里陪护，家庭责任与工作义务正面冲突",
           ("父亲跌倒请假被拒", "家人受伤与工作冲突", "孝亲陪护与项目关键期相撞"),
           ("家人身体健康", "请假顺利获批", "工作与家庭兼顾无压力", "毫无波折"),
           ("fall_call", "hospital", "boss_refuse", "leave", "night_care"),
           (p["father"], p["mother"], p["boss"])),
        _a("dim:health",
           f"父亲{p['father']}跌倒致髋部裂纹需卧床照护；本人因奔走与焦虑心率升至110bpm以上，夜间陪护导致睡眠严重不足",
           ("家人跌倒受伤需卧床", "本人心率升高", "夜间陪护睡眠不足"),
           ("全家身体健康", "睡眠充足", "心率平稳"),
           ("fall_call", "hospital", "hr_up", "night_care"), (p["father"],)),
        _a("dim:social",
           f"与父母之间的照护责任骤然加重，与领导{p['boss']}因请假被拒产生明显不满，家庭与工作两侧关系同时紧张",
           ("照护责任加重", "与领导因请假产生矛盾", "家庭与工作关系同时紧张"),
           ("领导体谅批准", "家庭关系轻松", "毫无矛盾"),
           ("boss_refuse", "leave", "night_care", "fall_call"), (p["boss"], p["father"], p["mother"])),
        _a("dim:emotion",
           "情绪在惊慌、愧疚与愤怒之间交替，对父亲心疼、对请假被拒愤怒、对无法兼顾深感愧疚",
           ("惊慌愧疚", "愤怒委屈", "无法兼顾的内疚", "心力交瘁"),
           ("平静从容", "心情愉悦", "毫无压力", "兴奋激动"),
           ("fall_call", "boss_refuse", "night_care"), ()),
        _finance_routine(c, "当日产生父亲拍片与药品费用支出，属计划外医疗开支，尚未构成大额负债"),
        _a("dim:career",
           f"项目处于关键期，请假申请被驳回，只能在完成上线任务的同时夜间陪护，工作推进未停但个人承受双线负荷",
           ("请假被拒需硬扛", "项目关键期无法脱身", "工作与照护双线作战"),
           ("顺利获批长假", "项目暂停", "获得领导体谅", "工作全面停滞"),
           ("boss_refuse", "leave"), (p["boss"],)),
    ]


def _s_pregnancy_handover(c: Ctx) -> List[Anchor]:
    p = c.p
    weeks = c.rng.randint(12, 34)
    c.app("checkup", (9 * 60, 10 * 60), "医院公众号", "妇幼保健院",
          f"产检提醒：孕{weeks}周常规检查已完成，各项指标正常，下次产检两周后。")
    c.mic("doctor", (10 * 60, 11 * 60), "产科医生", "诊室",
          f"产科医生：指标都正常，就是别再熬夜，工作能交接就交接。", noise_db=52)
    c.mic("handover", (14 * 60, 15 * 60 + 30), f"同事-{p['colleague']}", "工区",
          f"{p['colleague']}：你手上的活我接一部分，剩下的写个文档给我。", noise_db=60)
    c.app("partner_trip", (17 * 60, 18 * 60), "微信", f"{p['partner_title']}-{p['partner_name']}",
          f"{p['partner_name']}：临时要我出差四天，产检你自己去行吗？对不起。") if p["partner_name"] else c.app(
        "partner_trip", (17 * 60, 18 * 60), "微信", f"母亲-{p['mother']}", f"{p['mother']}：产检我陪你去，别一个人。")
    c.hr("hr_up", (20 * 60, 21 * 60), c.rng.randint(92, 104))
    c.mic("tired", (22 * 60, 23 * 60), f"佩戴者-{p['name']}", "卧室",
          f"{p['name']}：腰疼得厉害，还得把交接文档写完。", channel="自语")
    return [
        _a("global",
           f"{p['name']}孕{weeks}周产检指标正常但被医嘱减少熬夜，同日开始向同事{p['colleague']}交接工作，配偶{p['partner_name'] or '家人'}却临时出差四天，孕期照护出现空档",
           ("产检正常但交接与配偶出差叠加", "孕期照护空档", "产检顺利却面临独自承担"),
           ("全家陪同产检", "毫无压力", "身体异常需住院", "配偶全程陪护"),
           ("checkup", "doctor", "handover", "partner_trip"), (f"{weeks}周",)),
        _a("dim:health",
           f"孕{weeks}周产检各项指标正常，但存在腰部不适与疲劳，医嘱要求停止熬夜，需两周后复查",
           ("孕期检查指标正常", "孕周产检无异常", "有疲劳腰疼需休养"),
           ("产检发现严重异常", "需立即住院", "身体完全无变化", "妊娠终止"),
           ("checkup", "doctor", "tired"), (f"{weeks}周",)),
        _a("dim:social",
           f"与同事{p['colleague']}形成工作承接关系，与配偶{p['partner_name'] or '家人'}因出差缺席产检产生轻微失落与体谅并存的微妙情绪",
           ("同事承接工作", "配偶缺席产检", "家人补位陪伴", "关系微妙但互相体谅"),
           ("配偶全程陪伴", "夫妻激烈冲突", "同事拒绝帮忙", "关系破裂"),
           ("handover", "partner_trip"), (p["colleague"], p["partner_name"] or p["mother"])),
        _a("dim:emotion",
           "情绪总体平稳偏疲惫，因配偶缺席略有委屈与不安，但产检结果正常带来安心",
           ("疲惫中带委屈", "略有不安但安心", "平稳偏累"),
           ("极度焦虑崩溃", "兴奋狂喜", "毫无情绪波动", "绝望"),
           ("partner_trip", "checkup", "tired"), ()),
        _finance_routine(c, "当日产生产检挂号与检查费用，属常规医疗支出，无新增大额债务"),
        _a("dim:career",
           f"因孕期需要减少负荷，主动启动工作交接并整理文档，职责范围阶段性收缩但交接有序推进",
           ("启动工作交接", "职责阶段性收缩", "为孕期调整工作安排"),
           ("获得晋升", "承担更多职责", "被辞退", "工作全面停滞"),
           ("handover", "doctor"), ()),
    ]


def _s_blind_date_fender(c: Ctx) -> List[Anchor]:
    p = c.p
    loss = c.money(1200, 8000, 100)
    match = _full_name(c.rng, "男" if p["gender"] == "女" else "女")
    c.app("date", (14 * 60, 15 * 60), "微信", "介绍人-王姨",
          f"介绍人-王姨：今天下午三点，人民公园东门，对方叫{match}，人挺实在的。")
    c.mic("date_talk", (15 * 60, 17 * 60), f"相亲对象-{match}", "咖啡馆",
          f"{match}：我也不绕弯子，觉得合适就处，不合适也不耽误彼此。", noise_db=58)
    c.mic("fender", (17 * 60 + 30, 18 * 60 + 30), "对方车主", "路口",
          f"对方车主：你追尾了，走保险吧，定损大概{loss}块。", noise_db=70)
    c.imu("impact", (17 * 60 + 25, 17 * 60 + 40), round(c.rng.uniform(2.2, 3.4), 2))
    c.app("insurance", (18 * 60 + 30, 19 * 60 + 30), "保险公司", "车险客服",
          f"报案已受理，定损金额{loss}元，交强险范围内赔付，无需自付。")
    c.app("date_msg", (21 * 60, 22 * 60), "微信", f"相亲对象-{match}",
          f"{match}：今天聊得挺舒服，车的事别放心上，下次我请。")
    return [
        _a("global",
           f"{p['name']}下午相亲与{match}相谈甚洽，返程途中发生追尾事故定损{loss}元但由保险全额赔付，傍晚对方主动发来继续接触的信号，是意外与好消息交织的一天",
           ("相亲顺利却遇上追尾", "好消息与小意外同日", "感情有进展同时发生车祸"),
           ("相亲失败", "发生严重事故受伤", "保险拒赔", "毫无进展的一天"),
           ("date_talk", "fender", "insurance", "date_msg"), (match, f"{loss}元")),
        _a("dim:health",
           f"追尾瞬间IMU记录到{c.rng.choice(('2', '3'))}g左右冲击，本人未受伤，事后心率短时升高后恢复",
           ("受到轻微冲击但未受伤", "身体无大碍", "事故后短时心率升高"),
           ("重伤住院", "身体完全无异常", "全天心率无任何波动"),
           ("impact", "fender"), ()),
        _a("dim:social",
           f"与相亲对象{match}建立良好第一印象并有继续接触意向，与事故对方车主按流程处理无纠纷，介绍人王姨牵线成功",
           ("相亲关系有进展", "与对方车主和平处理", "获得继续交往意向"),
           ("相亲彻底失败", "与对方车主激烈冲突", "被拉黑断联"),
           ("date_talk", "date_msg", "fender"), (match,)),
        _a("dim:emotion",
           "情绪整体上扬，相亲顺利带来期待与愉悦，事故带来短暂惊慌后迅速平复",
           ("愉悦中带期待", "先惊后喜", "心情不错"),
           ("崩溃绝望", "极度愤怒", "情绪低落", "心如死灰"),
           ("date_talk", "fender", "date_msg"), ()),
        _a("dim:finance",
           f"车辆追尾定损{loss}元，交强险范围内全额赔付，个人无需自付，当日另有相亲咖啡一类小额支出",
           (f"定损{loss}元由保险赔付", "事故损失由保险覆盖", "个人未承担赔付"),
           ("个人自付巨额维修费", "保险拒赔", "新增大额负债", "获得大额赔偿收入"),
           ("insurance", "fender"), (f"{loss}元",)),
        _career_routine(c, "当日为休息日，无工作任务推进，职业状态无变化"),
    ]


def _s_cold_war_reconcile(c: Ctx) -> List[Anchor]:
    p = c.p
    rent = c.money(2000, 7500, 100)
    c.app("cold", (8 * 60, 9 * 60), "微信", f"{p['partner_title']}-{p['partner_name']}",
          f"{p['partner_name']}：（三天未回复的最后一条消息）你自己想想吧。") if p["partner_name"] else c.app(
        "cold", (8 * 60, 9 * 60), "微信", f"好友-{p['best_friend']}", f"{p['best_friend']}：你俩冷战三天了？")
    c.app("rent", (10 * 60, 11 * 60), "微信", "房东",
          f"房东：下季度房租{rent}元，这个月底前转我，要涨两百。")
    c.mic("raise_talk", (15 * 60, 16 * 60), f"直属领导-{p['boss']}", c.choice(MEETING_ROOMS),
          f"{p['boss']}：调薪窗口下月开，我给你报，但你得把上季度那个尾巴收掉。", noise_db=52)
    c.mic("reconcile", (20 * 60, 21 * 60 + 30), f"{p['partner_title']}-{p['partner_name']}", "楼下小公园",
          f"{p['partner_name']}：那天是我话说重了，我们别这样了。", noise_db=50) if p["partner_name"] else c.mic(
        "reconcile", (20 * 60, 21 * 60 + 30), f"好友-{p['best_friend']}", "烧烤摊",
        f"{p['best_friend']}：说开了就好，别憋着。", noise_db=72)
    c.app("paid", (21 * 60 + 30, 22 * 60 + 30), "银行", c.choice(BANKS),
          f"您已向房东转账{rent}元，交易成功。")
    return [
        _a("global",
           f"{p['name']}与{p['partner_name'] or p['best_friend']}冷战三天后于晚间和解，同日收到房租涨至{rent}元的催缴通知，并获领导{p['boss']}口头承诺下月申报调薪，情感、居住与收入三线同日出现转机",
           ("冷战和解叠加房租上涨与调薪希望", "情感修复同时财务压力上升", "三线同日出现转机"),
           ("关系彻底破裂", "被房东驱逐", "调薪被拒", "全线崩塌"),
           ("cold", "reconcile", "rent", "raise_talk"), (f"{rent}元", p["boss"])),
        _a("dim:health",
           "冷战期间睡眠欠佳，和解后情绪放松、入睡改善，全天体征无异常波动",
           ("和解后睡眠改善", "体征无异常", "情绪放松身体状态回升"),
           ("心率骤升", "身体出现急症", "全天极度不适"),
           ("reconcile", "trivia_sample"), ()),
        _a("dim:social",
           f"与{p['partner_name'] or p['best_friend']}由冷战转为和解，关系修复并明确沟通方式，与领导{p['boss']}因调薪沟通而关系缓和",
           ("冷战后关系修复", "沟通方式改善", "与领导关系缓和"),
           ("关系彻底破裂", "冲突升级", "被冷暴力持续", "断绝往来"),
           ("cold", "reconcile", "raise_talk"), (p["partner_name"] or p["best_friend"], p["boss"])),
        _a("dim:emotion",
           "情绪由前几日的压抑委屈转为释然与轻松，晚间出现明显的安心感，整体基调回暖",
           ("由压抑转释然", "情绪回暖", "安心轻松"),
           ("持续崩溃", "愤怒失控", "绝望到底", "毫无变化"),
           ("reconcile", "cold"), ()),
        _a("dim:finance",
           f"下季度房租涨至{rent}元并已按期转账，居住成本上升；同时获得下月调薪申报的口头承诺，收入有向好预期但尚未落地",
           (f"房租涨至{rent}元并已支付", "居住成本上升", "调薪有望但未落地"),
           ("房租下降", "获得大额一次性收入", "新增巨额负债", "调薪已到账"),
           ("rent", "paid", "raise_talk"), (f"{rent}元",)),
        _a("dim:career",
           f"领导{p['boss']}承诺在下月调薪窗口申报，但前提是先收尾上季度遗留工作，职业发展有正向预期且任务明确",
           ("获得调薪申报机会", "需先收尾遗留工作", "职业发展有正向预期"),
           ("被明确拒绝调薪", "工作毫无进展", "被辞退", "已晋升到位"),
           ("raise_talk",), (p["boss"],)),
    ]


def _s_friend_loan_fallout(c: Ctx) -> List[Anchor]:
    p = c.p
    owed = c.money(10000, 60000, 5000)
    loss = c.money(8000, 40000, 2000)
    c.app("demand", (11 * 60, 12 * 60), "微信", f"好友-{p['best_friend']}",
          f"{p['best_friend']}：那{owed}元你到底什么时候还？我这月信用卡都刷爆了。")
    c.mic("shout", (12 * 60, 13 * 60), f"好友-{p['best_friend']}", "电话",
          f"{p['best_friend']}提高声音：当初说好三个月，你拖了一年，还算不算朋友？", noise_db=58)
    c.app("invest", (14 * 60, 15 * 60), "微信", "投资群-老同学合伙",
          f"合伙人-老陈：那个项目彻底黄了，{loss}打水漂，谁也别怪谁。", session="群聊")
    c.hr("hr_up", (12 * 60, 13 * 60), c.rng.randint(100, 116))
    c.mic("family_dinner", (19 * 60, 20 * 60 + 30), f"母亲-{p['mother']}", "家中餐桌",
          f"{p['mother']}：钱的事慢慢还，别把朋友处没了。", noise_db=56)
    c.app("promise", (22 * 60, 23 * 60), "微信", f"好友-{p['best_friend']}",
          f"{p['name']}：这个月先发你三千，剩下的分六个月，我写个字据。", direction="发送")
    return [
        _a("global",
           f"{p['name']}被好友{p['best_friend']}当面催讨拖欠一年的{owed}元借款并遭质问，同日得知与老同学合伙的项目亏损{loss}元，晚间在家人劝解下给出分期还款字据，友情与财务双重受创",
           ("被好友催债同时合伙投资亏损", "友情与财务同日双杀", "债务纠纷叠加投资失败"),
           ("朋友慷慨免债", "投资大幅获利", "毫无纠纷的一天", "关系更进一步"),
           ("demand", "shout", "invest", "promise"), (p["best_friend"], f"{owed}", f"{loss}")),
        _a("dim:health",
           "争执时心率升至100bpm以上，晚间情绪低落影响食欲与睡眠",
           ("争执时心率升高", "情绪影响食欲睡眠", "应激反应明显"),
           ("全天心率平稳", "食欲睡眠良好", "身体状态极佳"),
           ("hr_up", "shout"), ()),
        _a("dim:social",
           f"与好友{p['best_friend']}因拖欠借款发生正面冲突，多年友情出现裂痕但未断绝，家人{p['mother']}居中劝解",
           ("与好友因债务冲突", "友情出现裂痕", "关系未断但已生隙", "家人居中劝解"),
           ("关系彻底决裂", "友情更加牢固", "毫无矛盾", "被朋友起诉"),
           ("demand", "shout", "family_dinner", "promise"), (p["best_friend"], p["mother"])),
        _a("dim:emotion",
           "情绪以羞愧、懊恼与压力为主，被当面质问时难堪，晚间在家人安慰下略有缓解",
           ("羞愧懊恼", "难堪压力", "自责压抑"),
           ("理直气壮", "心情愉悦", "毫无压力", "兴奋得意"),
           ("shout", "family_dinner", "promise"), ()),
        _a("dim:finance",
           f"拖欠好友{owed}元借款被催讨并承诺分期偿还，同日合伙项目确认亏损{loss}元，个人资产负债状况明显恶化",
           (f"拖欠{owed}元需分期偿还", f"合伙投资亏损{loss}元", "债务与亏损同时发生", "财务状况恶化"),
           ("债务全部清偿", "投资获利退出", "资产大幅增值", "获得大额收入"),
           ("demand", "invest", "promise"), (f"{owed}", f"{loss}")),
        _career_routine(c, "当日工作按常规推进，债务与投资问题尚未波及职业表现"),
    ]


def _s_wedding_gift_pressure(c: Ctx) -> List[Anchor]:
    p = c.p
    gift = c.money(800, 3000, 100)
    c.app("invite", (9 * 60, 10 * 60), "微信", "老同学-班长",
          f"老同学-班长：这周六我婚礼，随礼统一{gift}元，大家都这样，别单独少。", session="群聊")
    c.mic("reunion", (18 * 60, 20 * 60), "老同学", "饭店包间",
          f"老同学：听说你年薪百万了？我看你朋友圈还在挤地铁。", noise_db=80)
    c.app("balance", (20 * 60 + 30, 21 * 60 + 30), "银行", c.choice(BANKS),
          f"您的账户可用余额{c.money(1500, 9000, 100)}元，本月已支出占比偏高。")
    c.hr("hr_up", (19 * 60, 20 * 60), c.rng.randint(90, 104))
    c.app("noodles", (21 * 60 + 30, 22 * 60 + 30), "美团外卖", "面馆",
          f"您下单一碗牛肉面，实付{c.money(12, 28, 2)}元。")
    c.mic("self", (22 * 60 + 30, 23 * 60 + 20), f"佩戴者-{p['name']}", "出租屋",
          f"{p['name']}：月底了，随礼一交，这周只能吃面。", channel="自语")
    return [
        _a("global",
           f"{p['name']}被要求按{gift}元的统一标准随同学婚礼礼金，同学会上又遭攀比讥讽，账户余额吃紧到月底只能吃面，人情消费与自尊感受同时受压",
           ("随礼压力叠加同学攀比", "人情开销压垮月底预算", "同学会攀比带来的窘迫"),
           ("财务宽裕无压力", "同学会气氛融洽", "获得大额进账", "毫无波澜"),
           ("invite", "reunion", "balance", "self"), (f"{gift}元",)),
        _a("dim:health",
           "同学会席间情绪紧张心率略升，全天饮食简单，体征无异常",
           ("情绪紧张心率略升", "体征无异常", "饮食偏简单"),
           ("心率骤升", "身体出现急症", "全天极度不适"),
           ("hr_up", "reunion"), ()),
        _a("dim:social",
           "与老同学群体维持表面热络实则攀比的关系，被讥讽后社交自尊受挫，未发生正面冲突但内心疏离",
           ("同学关系表面热络", "攀比带来社交压力", "内心疏离未冲突"),
           ("同学真诚相待", "关系彻底破裂", "发生激烈争吵", "获得群体认可"),
           ("reunion", "invite"), ()),
        _a("dim:emotion",
           "情绪以窘迫、委屈与自我怀疑为主，被当众攀比后感到难堪，深夜以自嘲方式消化",
           ("窘迫委屈", "难堪自嘲", "自我怀疑"),
           ("自信满满", "心情愉悦", "毫无压力", "得意洋洋"),
           ("reunion", "self"), ()),
        _a("dim:finance",
           f"需按统一标准支出{gift}元婚礼随礼，账户可用余额偏低，月底现金流紧张只能压缩日常饮食开支",
           (f"随礼支出{gift}元", "现金流紧张", "压缩日常开支", "人情消费压力大"),
           ("财务宽裕", "获得大额收入", "资产大幅增值", "毫无额外支出"),
           ("invite", "balance", "noodles", "self"), (f"{gift}元",)),
        _career_routine(c, "当日工作按常规推进，个人收入未变，职业状态无重大变化"),
    ]


def _s_parent_teacher_meeting(c: Ctx) -> List[Anchor]:
    p = c.p
    mortgage = c.money(4000, 12000, 500)
    c.app("notice", (16 * 60, 17 * 60), "微信", f"班主任-{p['child_name']}班",
          f"班主任：{p['child_name']}最近上课走神，作业连续三次没交，明天家长来一趟。", session="群聊")
    c.mic("teacher", (17 * 60 + 30, 18 * 60 + 30), "班主任", "教室办公室",
          f"班主任：孩子不是笨，是没人盯，你们家长得配合。", noise_db=58)
    c.mic("couple_blame", (20 * 60, 21 * 60), f"{p['partner_title']}-{p['partner_name']}", "家中客厅",
          f"{p['partner_name']}：天天加班，孩子你管过一天吗？", noise_db=54) if p["partner_name"] else c.mic(
        "couple_blame", (20 * 60, 21 * 60), f"母亲-{p['mother']}", "家中客厅",
        f"{p['mother']}：孩子的事你别都推给我，我也老了。", noise_db=54)
    c.app("mortgage", (21 * 60 + 30, 22 * 60 + 30), "银行", c.choice(BANKS),
          f"您的住房贷款{mortgage}元已扣款成功，剩余期数{c.rng.randint(80, 260)}期。")
    c.hr("hr_up", (20 * 60, 21 * 60), c.rng.randint(94, 108))
    c.mic("kid", (22 * 60, 23 * 60), f"孩子-{p['child_name']}", "儿童房",
          f"{p['child_name']}：我不是不想写，是看不懂，你们又不在家。", noise_db=46)
    return [
        _a("global",
           f"{p['name']}因孩子{p['child_name']}连续欠作业被班主任约谈，回家后与{p['partner_name'] or p['mother']}因育儿分工互相埋怨，同日房贷{mortgage}元照常扣款，育儿、婚姻与经济三重压力同日挤压",
           ("孩子被约谈引发夫妻埋怨", "育儿与经济压力同日叠加", "家长会批评引发家庭冲突"),
           ("孩子表现优秀", "家庭其乐融融", "毫无压力", "房贷减免"),
           ("notice", "teacher", "couple_blame", "mortgage", "kid"),
           (p["child_name"], f"{mortgage}元")),
        _a("dim:health",
           "晚间争执时心率上升，全天奔波于学校与工作之间，睡眠时长偏短",
           ("晚间心率上升", "睡眠偏短", "奔波疲劳"),
           ("全天心率平稳", "睡眠充足", "精力充沛"),
           ("hr_up", "couple_blame"), ()),
        _a("dim:social",
           f"与班主任因孩子教育问题形成压力性沟通，与{p['partner_name'] or p['mother']}因育儿分工爆发互相埋怨，与孩子{p['child_name']}之间存在被忽视的沟通缺口",
           ("与配偶因育儿互相埋怨", "与老师形成压力沟通", "亲子沟通缺口暴露"),
           ("家庭关系融洽", "夫妻互相支持", "与老师关系轻松", "亲子亲密无间"),
           ("teacher", "couple_blame", "kid"), (p["child_name"], p["partner_name"] or p["mother"])),
        _a("dim:emotion",
           "情绪以愧疚、烦躁与无力为主，既对孩子愧疚又对伴侣埋怨感到委屈，深夜自责",
           ("愧疚烦躁", "委屈无力", "自责压抑"),
           ("轻松愉悦", "理直气壮", "毫无压力", "兴奋得意"),
           ("couple_blame", "kid"), ()),
        _a("dim:finance",
           f"住房贷款{mortgage}元按期扣款成功，家庭固定负债压力持续，当日另有课外辅导一类计划外支出",
           (f"房贷{mortgage}元按期扣款", "固定负债压力持续", "无逾期"),
           ("房贷逾期", "获得大额收入", "负债全部清偿", "资产大幅增值"),
           ("mortgage",), (f"{mortgage}元",)),
        _a("dim:career",
           f"为参加家长会临时离岗，工作进度受影响，职业与家庭的资源分配矛盾凸显",
           ("为家长会离岗影响进度", "工作与家庭资源冲突", "进度受影响"),
           ("工作毫无影响", "获得晋升", "项目提前完成", "被辞退"),
           ("notice", "teacher"), ()),
    ]


def _s_fund_loss_cut(c: Ctx) -> List[Anchor]:
    p = c.p
    loss_pct = c.rng.randint(12, 34)
    principal = c.money(20000, 200000, 10000)
    c.app("fund", (9 * 60 + 30, 10 * 60 + 30), "基金", "基金平台",
          f"您持有的沪深300指数基金今日再跌{c.rng.randint(2, 5)}%，累计浮亏{loss_pct}%，市值{int(principal * (100 - loss_pct) / 100)}元。")
    c.app("rate", (11 * 60, 12 * 60), "银行", c.choice(BANKS),
          f"您的住房贷款利率已按LPR重定价，月供减少{c.money(60, 400, 10)}元，下期生效。")
    c.mic("cut", (14 * 60, 15 * 60), f"佩戴者-{p['name']}", "工位",
          f"{p['name']}：割了，亏{loss_pct}%认了，再拿下去睡不着。", channel="自语")
    c.app("cut_done", (14 * 60 + 10, 15 * 60 + 10), "基金", "基金平台",
          f"您已提交全部赎回申请，本金{principal}元，确认亏损{int(principal * loss_pct / 100)}元。")
    c.mic("comfort", (20 * 60, 21 * 60), f"{p['partner_title'] or '好友'}-{p['partner_name'] or p['best_friend']}", "家中",
          f"{p['partner_name'] or p['best_friend']}：亏了就亏了，人没事比什么都强。", noise_db=50)
    c.hr("hr_up", (14 * 60, 15 * 60), c.rng.randint(92, 106))
    return [
        _a("global",
           f"{p['name']}持有的指数基金累计浮亏{loss_pct}%后果断全部割肉离场，确认亏损{int(principal * loss_pct / 100)}元，同日房贷利率下调使月供减少，投资受挫与生活成本改善同日发生",
           ("割肉离场同时房贷月供下降", "投资亏损与减负同日", "认赔止损加上利率下调"),
           ("投资大幅获利", "基金翻倍", "房贷利率上调", "毫无财务波动"),
           ("fund", "cut", "cut_done", "rate"), (f"{loss_pct}%", f"{principal}元")),
        _a("dim:health",
           "长期盯盘导致睡眠浅，赎回当日心率上升后放松，全天无急性身体异常",
           ("盯盘导致睡眠变浅", "赎回时心率上升", "无急性异常"),
           ("心率骤升", "突发急症", "身体状态显著改善"),
           ("hr_up", "cut"), ()),
        _a("dim:social",
           f"配偶/好友{p['partner_name'] or p['best_friend']}在亏损后给予情绪支持，家庭内部未因投资失利产生指责，关系稳定",
           ("家人给予情绪支持", "未因亏损互相指责", "关系稳定"),
           ("因亏损爆发家庭冲突", "关系破裂", "被家人责骂"),
           ("comfort",), (p["partner_name"] or p["best_friend"],)),
        _a("dim:emotion",
           "情绪由焦虑不甘转为割肉后的解脱与失落并存，晚间在家人安慰下逐步平复",
           ("焦虑转解脱", "失落与释然并存", "情绪逐步平复"),
           ("狂喜", "彻底崩溃", "毫无情绪波动", "愤怒失控"),
           ("cut", "comfort"), ()),
        _a("dim:finance",
           f"全部赎回本金{principal}元的基金，确认亏损{loss_pct}%约{int(principal * loss_pct / 100)}元；同时住房贷款利率下调，月供减少，长期负债成本下降",
           (f"基金割肉确认亏损{loss_pct}%", f"赎回本金{principal}元", "房贷利率下调月供减少", "投资资产缩水"),
           ("投资获利离场", "资产大幅增值", "房贷月供上升", "获得大额进账"),
           ("fund", "cut_done", "rate"), (f"{loss_pct}%", f"{principal}元")),
        _career_routine(c, "当日工作按常规推进，投资亏损未影响职业表现"),
    ]


def _s_payday_side_income(c: Ctx) -> List[Anchor]:
    p = c.p
    salary = c.money(8000, 32000, 500)
    side = c.money(800, 6000, 100)
    c.app("salary", (10 * 60, 11 * 60), "银行", c.choice(BANKS),
          f"您尾号账户入账{salary}元，摘要：工资。")
    c.app("side", (12 * 60, 13 * 60), "微信", "私单客户",
          f"私单客户：设计稿收到，尾款{side}元已转你，下次还找你。")
    c.app("plan", (20 * 60, 21 * 60), "携程", "携程旅行",
          f"您收藏的{c.choice(('三亚', '成都', '西安', '厦门', '大理'))}往返机票已降价，最低{c.money(600, 2400, 50)}元起。")
    c.mic("talk", (21 * 60, 22 * 60), f"{p['partner_title'] or '好友'}-{p['partner_name'] or p['best_friend']}", "家中",
          f"{p['partner_name'] or p['best_friend']}：工资加私单，这个月能出去玩一趟了。", noise_db=48)
    c.app("boss_praise", (16 * 60, 17 * 60), "微信", f"直属领导-{p['boss']}",
          f"{p['boss']}：这版方案客户很满意，下季度让你带新人。")
    return [
        _a("global",
           f"{p['name']}当日工资{salary}元到账，副业私单尾款{side}元同步入账，工作上获领导{p['boss']}肯定并被安排带新人，晚间开始规划出行，是收入与认可双双落地的顺遂一天",
           ("工资与副业同时到账", "收入落地叠加工作被肯定", "顺遂有收获的一天"),
           ("被降薪", "副业失败", "被辞退", "毫无进展", "陷入债务危机"),
           ("salary", "side", "boss_praise", "plan"), (f"{salary}元", f"{side}元", p["boss"])),
        _a("dim:health",
           "作息规律，晨起静息心率与平日相当，全天体征平稳，心情愉悦带动睡眠质量良好",
           ("体征平稳作息规律", "睡眠质量良好", "身体状态与平日一致"),
           ("心率骤升", "身体急症", "严重失眠", "体征显著恶化"),
           ("trivia_sample", "talk"), ()),
        _a("dim:social",
           f"与领导{p['boss']}因方案获认可而关系升温，与私单客户建立复购关系，与{p['partner_name'] or p['best_friend']}共同规划出行，社交关系全面正向",
           ("与领导关系升温", "获得客户复购", "与伴侣共同规划", "关系全面正向"),
           ("关系破裂", "被同事排挤", "客户投诉", "家庭冲突"),
           ("boss_praise", "side", "talk"), (p["boss"], p["partner_name"] or p["best_friend"])),
        _a("dim:emotion",
           "情绪主基调为满足与期待，收入到账带来安全感，被认可带来成就感，晚间转为对出行的兴奋",
           ("满足与期待", "成就感与安全感", "心情愉悦"),
           ("崩溃绝望", "焦虑不安", "愤怒失控", "情绪低落"),
           ("salary", "boss_praise", "plan"), ()),
        _a("dim:finance",
           f"工资{salary}元与副业尾款{side}元同日入账，收入渠道多元化，开始规划一笔旅行支出，现金流明显改善且无新增负债",
           (f"工资{salary}元到账", f"副业收入{side}元", "现金流改善", "收入多元化"),
           ("收入下降", "新增大额负债", "资产大幅缩水", "遭遇诈骗损失"),
           ("salary", "side", "plan"), (f"{salary}元", f"{side}元")),
        _a("dim:career",
           f"方案获客户满意并被领导{p['boss']}安排下季度带新人，职责范围扩大，职业发展进入正向通道",
           ("方案获客户认可", "被安排带新人", "职责扩大职业向好"),
           ("被批评否决", "被边缘化", "工作毫无进展", "被辞退"),
           ("boss_praise",), (p["boss"],)),
    ]


def _s_refund_scam(c: Ctx) -> List[Anchor]:
    p = c.p
    amount = c.money(1200, 20000, 200)
    c.app("scam_call", (14 * 60, 15 * 60), "电话", "自称客服",
          f"自称客服：您的订单质量有问题要双倍退款，请提供短信验证码并开启屏幕共享。")
    c.app("code", (14 * 60 + 5, 14 * 60 + 30), "短信", "运营商",
          f"【安全提醒】您正在办理转账业务，验证码{c.rng.randint(100000, 999999)}，任何人索要均为诈骗。")
    c.app("riskcontrol", (14 * 60 + 20, 15 * 60 + 20), "银行", c.choice(BANKS),
          f"您向陌生账户转账{amount}元的交易已被风控拦截，请核实对方身份。")
    c.mic("police", (16 * 60, 17 * 60), "反诈民警", "派出所",
          f"反诈民警：这是典型冒充客服诈骗，你运气好被拦了，签个笔录。", noise_db=60)
    c.hr("hr_up", (14 * 60, 15 * 60), c.rng.randint(104, 122))
    c.app("family", (20 * 60, 21 * 60), "微信", f"母亲-{p['mother']}",
          f"{p['mother']}：派出所给我打电话了，你没被骗吧？吓死我了。")
    return [
        _a("global",
           f"{p['name']}遭遇冒充客服的退款诈骗，被诱导提供验证码并向陌生账户转账{amount}元，所幸银行风控拦截、警方介入未造成损失，全天经历惊魂与后怕",
           ("遭遇冒充客服诈骗被风控拦下", "险些被骗后报警", "诈骗未遂的惊魂一天"),
           ("被骗走大额资金", "毫无异常的一天", "获得意外之财", "轻松顺利"),
           ("scam_call", "code", "riskcontrol", "police"), (f"{amount}元",)),
        _a("dim:health",
           f"诈骗过程中心率骤升至110bpm以上，事后长时间后怕，夜间睡眠受扰",
           ("应激性心率骤升", "事后后怕失眠", "急性应激反应"),
           ("全天心率平稳", "睡眠良好", "身体状态极佳"),
           ("hr_up", "scam_call"), ()),
        _a("dim:social",
           "与反诈民警形成求助与配合关系，家人因警方通知而知情并表达担忧，社交圈无冲突",
           ("向警方求助配合", "家人知情并担忧", "获得反诈指导"),
           ("与家人激烈冲突", "被朋友指责", "关系破裂", "拒绝警方协助"),
           ("police", "family"), (p["mother"],)),
        _a("dim:emotion",
           "情绪经历紧张恐慌到后怕再到庆幸的剧烈起伏，深夜仍反复回想细节，警惕心明显提高",
           ("紧张恐慌", "后怕庆幸", "惊魂未定", "警惕心提高"),
           ("心情愉悦", "毫无波澜", "兴奋激动", "彻底绝望"),
           ("scam_call", "police", "family"), ()),
        _a("dim:finance",
           f"向陌生账户转账{amount}元的交易被银行风控拦截，资金未实际损失，账户随后被临时保护，无新增债务",
           (f"转账{amount}元被风控拦截", "资金未损失", "账户受保护", "诈骗未遂"),
           (f"损失{amount}元", "资金被盗刷", "新增大额负债", "获得大额退款"),
           ("riskcontrol", "scam_call", "police"), (f"{amount}元",)),
        _career_routine(c, "当日工作因处理诈骗事件被打断，但职责与进度无实质变化"),
    ]


def _s_insurance_claim_denied(c: Ctx) -> List[Anchor]:
    p = c.p
    claim = c.money(3000, 30000, 500)
    premium = c.money(2000, 9000, 100)
    c.app("denied", (10 * 60, 11 * 60), "保险公司", "理赔部",
          f"您提交的住院医疗费用理赔申请{claim}元不予赔付，理由：属免责条款第7条既往症。")
    c.mic("argue_call", (11 * 60, 12 * 60), "保险客服", "电话",
          f"保险客服：条款写得很清楚，您投保前没告知，我们只能拒赔。", noise_db=54)
    c.app("complaint", (14 * 60, 15 * 60), "12378", "银行保险消费者投诉热线",
          f"您的投诉已受理，工单号{c.rng.randint(100000, 999999)}，将在15个工作日内答复。")
    c.app("renew", (19 * 60, 20 * 60), "保险公司", "续保提醒",
          f"您的医疗险将于月底到期，续保保费{premium}元，是否继续投保？")
    c.hr("hr_up", (11 * 60, 12 * 60), c.rng.randint(96, 112))
    c.mic("family", (21 * 60, 22 * 60), f"{p['partner_title'] or '母亲'}-{p['partner_name'] or p['mother']}", "家中",
          f"{p['partner_name'] or p['mother']}：不续了吧，白交钱。可万一真出事呢。", noise_db=50)
    return [
        _a("global",
           f"{p['name']}的{claim}元住院理赔被保险公司以既往症免责条款拒赔，投诉至12378后仍未有结果，同时面临月底{premium}元续保的两难抉择，保障信任与经济压力同时受挫",
           ("理赔被拒后投诉无果", "拒赔叠加续保两难", "保险纠纷的一天"),
           ("理赔顺利到账", "保险全额赔付", "毫无纠纷", "获得额外赔付"),
           ("denied", "argue_call", "complaint", "renew"), (f"{claim}元", f"{premium}元")),
        _a("dim:health",
           "本人当日体征平稳，但此前住院治疗的既往病症仍在随访，情绪激动时心率上升",
           ("体征平稳但既往病随访中", "情绪激动心率上升", "健康状况需持续关注"),
           ("身体完全康复无任何隐患", "突发急症", "全天心率毫无波动"),
           ("hr_up", "denied"), ()),
        _a("dim:social",
           "与保险公司形成对立维权关系，家人对是否续保意见分歧，未达成一致但保持沟通",
           ("与保险公司对立", "家人意见分歧", "维权沟通中"),
           ("与保险公司关系融洽", "家人完全一致", "关系破裂"),
           ("argue_call", "family", "complaint"), ()),
        _a("dim:emotion",
           "情绪以愤怒与被辜负感为主，对条款不公感到委屈，深夜陷入对保障缺失的不安",
           ("愤怒被辜负", "委屈不安", "对保障缺失担忧"),
           ("心情愉悦", "毫无波澜", "兴奋激动", "彻底放松"),
           ("argue_call", "family"), ()),
        _a("dim:finance",
           f"{claim}元理赔被拒需自费承担，同时月底面临{premium}元续保支出，医疗与保障双重成本压力上升",
           (f"理赔{claim}元被拒需自费", f"面临{premium}元续保支出", "医疗保障成本上升"),
           ("理赔款到账", "保费大幅下降", "获得大额赔付", "无任何额外支出"),
           ("denied", "renew"), (f"{claim}元", f"{premium}元")),
        _career_routine(c, "当日工作按常规推进，保险纠纷未影响职业进度"),
    ]


def _s_pet_death(c: Ctx) -> List[Anchor]:
    p = c.p
    years = c.rng.randint(6, 15)
    c.mic("vet", (9 * 60, 10 * 60 + 30), "宠物医生", "宠物医院",
          f"宠物医生：{p['pet']}各项器官都衰竭了，救回来的意义不大，你们考虑一下。", noise_db=52)
    c.app("pass", (11 * 60, 12 * 60), "微信", "宠物医院",
          f"宠物医院：{p['pet']}于{hhmm(c.rng.randint(10 * 60 + 40, 11 * 60 + 40))}平静离世，遗体暂存于本院。")
    c.app("leave", (13 * 60, 14 * 60), "OA系统", "人力资源部",
          f"您的请假申请（事假半天）已批准。")
    c.mic("colleague", (15 * 60, 16 * 60), f"同事-{p['colleague']}", "电话",
          f"{p['colleague']}：活儿我先顶着，你别急着回来。", noise_db=54)
    c.mic("cry", (21 * 60, 22 * 60 + 30), f"佩戴者-{p['name']}", "家中",
          f"{p['name']}哽咽：它陪了我{years}年，回家开门再没人扑过来了。", channel="自语")
    c.hr("hr_up", (21 * 60, 22 * 60), c.rng.randint(94, 108))
    return [
        _a("global",
           f"{p['name']}陪伴{years}年的{p['pet']}因器官衰竭在宠物医院离世，请假半天处理后事，同事{p['colleague']}主动分担工作，全天沉浸在丧失的悲痛中",
           ("宠物离世带来的丧失之痛", "陪伴多年的宠物走了", "宠物病亡请假处理"),
           ("宠物康复", "毫无变故的一天", "宠物走失后找回", "喜气洋洋"),
           ("vet", "pass", "leave", "cry"), (p["pet"], f"{years}年")),
        _a("dim:health",
           "哭泣导致心率上升与眼部不适，全天进食极少，夜间几乎无法入睡",
           ("悲伤导致心率上升", "食欲与睡眠严重下降", "应激性躯体反应"),
           ("身体状态极佳", "作息规律", "全天心率平稳"),
           ("hr_up", "cry"), ()),
        _a("dim:social",
           f"同事{p['colleague']}主动分担工作体现支持，请假获批准，社交圈给予体谅，无冲突发生",
           ("获得同事体谅与支持", "请假获批", "社交支持到位"),
           ("被同事指责", "请假被拒", "关系破裂", "被冷嘲热讽"),
           ("colleague", "leave"), (p["colleague"],)),
        _a("dim:emotion",
           "情绪主基调为深度悲伤与失落，反复回忆与宠物相处的细节，出现明显的哀伤反应",
           ("深度悲伤失落", "哀伤难抑", "沉浸在丧失感中"),
           ("心情愉悦", "毫无波澜", "兴奋激动", "轻松自在"),
           ("cry", "pass"), ()),
        _finance_routine(c, f"当日产生宠物临终治疗与遗体处理费用支出，属突发医疗支出，无新增大额债务"),
        _a("dim:career",
           "请假半天处理后事，当日工作由同事代管，进度小幅延后但已妥善安排",
           ("请假导致进度小幅延后", "工作由同事代管", "已妥善交接"),
           ("工作全面停滞", "被追责", "获得晋升", "项目提前完成"),
           ("leave", "colleague"), ()),
    ]


def _s_exam_result_fail(c: Ctx) -> List[Anchor]:
    p = c.p
    score = c.rng.randint(96, 132)
    c.app("score", (9 * 60, 10 * 60), "人事考试网", "成绩查询系统",
          f"您本次{c.choice(('公务员', '事业编', '研究生'))}入学考试成绩为{score}分，未达到入围分数线。")
    c.mic("parent_call", (12 * 60, 13 * 60), f"父亲-{p['father']}", "电话",
          f"{p['father']}：考不上就回来吧，家里给你找了个稳定的活儿。", noise_db=50)
    c.mic("run", (21 * 60 + 30, 22 * 60 + 30), f"佩戴者-{p['name']}", "江边步道",
          f"{p['name']}边跑边说：再来一年，我不信考不上。", channel="自语")
    c.hr("hr_run", (21 * 60 + 30, 22 * 60 + 30), c.rng.randint(138, 162))
    c.app("plan", (22 * 60 + 30, 23 * 60 + 20), "淘宝", "图书专营店",
          f"您下单：明年最新版权威教材与真题卷一套，实付{c.money(180, 680, 10)}元。")
    return [
        _a("global",
           f"{p['name']}查到{c.choice(('公务员', '事业编', '研究生'))}考试成绩{score}分未过线，父亲{p['father']}劝其回家接受稳定工作，本人拒绝并在夜间跑步后决定再战一年，落榜与坚持正面碰撞",
           ("考试落榜后决定再战一年", "落榜与家庭期望冲突", "成绩未过线的挫败与坚持"),
           ("考试顺利通过", "被录取", "放弃备考回家", "毫无波澜"),
           ("score", "parent_call", "run", "plan"), (f"{score}分", p["father"])),
        _a("dim:health",
           f"白天情绪低落活动量低，晚间以{c.rng.randint(6, 12)}公里夜跑释放压力，运动时心率达150bpm以上，身体机能被主动调动",
           ("夜间高强度跑步", "运动时心率显著升高", "以运动调节情绪"),
           ("全天久坐无运动", "心率毫无波动", "身体极度疲惫无活动"),
           ("hr_run", "run"), ()),
        _a("dim:social",
           f"与父亲{p['father']}在人生路径选择上产生分歧，父亲希望其回家就业，本人坚持继续备考，家庭期望出现张力",
           ("与父亲在规划上分歧", "家庭期望形成压力", "坚持己见未妥协"),
           ("家人全力支持", "父子关系破裂", "立刻妥协回家", "毫无分歧"),
           ("parent_call", "run"), (p["father"],)),
        _a("dim:emotion",
           "情绪由得知成绩时的失落自我怀疑，经夜跑后转为不甘与坚定，深夜确立再战决心",
           ("失落转坚定", "自我怀疑后重燃斗志", "不甘与决心"),
           ("狂喜", "彻底放弃", "毫无情绪波动", "绝望到底"),
           ("score", "run", "plan"), ()),
        _finance_routine(c, "当日购入一套备考教材支出数百元，无其他大额收支变动"),
        _a("dim:career",
           f"体制内或升学路径本次受阻，职业入场时间推迟一年，本人重新制定备考计划并投入资金",
           ("升学/入编路径受阻", "职业入场推迟", "重新规划备考"),
           ("顺利上岸", "获得录用通知", "职业路径畅通", "已被录取"),
           ("score", "plan"), ()),
    ]


def _s_ticket_scam(c: Ctx) -> List[Anchor]:
    p = c.p
    price = c.money(800, 4000, 100)
    c.app("scalper", (13 * 60, 14 * 60), "微信", "黄牛-票王",
          f"黄牛-票王：内场两张{price}元，先转账后发电子票，手慢没有。")
    c.app("paid", (13 * 60 + 20, 14 * 60 + 20), "支付宝", "支付宝",
          f"您向个人账户转账{price}元，交易成功。")
    c.app("blocked", (15 * 60, 16 * 60), "微信", "黄牛-票王",
          f"你已开启了朋友验证，你还不是他（她）的朋友。")
    c.mic("argue", (16 * 60 + 30, 17 * 60 + 30), f"好友-{p['best_friend']}", "电话",
          f"{p['best_friend']}：我早说了别信黄牛，你非不听，这钱基本追不回来了。", noise_db=56)
    c.hr("hr_up", (15 * 60, 16 * 60), c.rng.randint(98, 114))
    c.app("report", (18 * 60, 19 * 60), "微信", "腾讯卫士",
          f"您提交的欺诈举报已受理，涉案账号已被限制收款功能。")
    return [
        _a("global",
           f"{p['name']}向黄牛转账{price}元购买演唱会内场票后被拉黑，钱票两空，与好友{p['best_friend']}因先前劝阻发生争执，随后提交欺诈举报，是一次典型的高价票务受骗",
           ("买黄牛票被拉黑钱票两空", "高价购票受骗", "转账后被拉黑"),
           ("顺利买到门票", "获得退款", "毫无损失", "演唱会顺利参加"),
           ("scalper", "paid", "blocked", "argue", "report"), (f"{price}元", p["best_friend"])),
        _a("dim:health",
           "发现被拉黑后心率上升，全天情绪起伏影响进食，夜间难以入睡",
           ("心率上升", "进食受影响", "失眠"),
           ("全天心率平稳", "睡眠良好", "身体状态极佳"),
           ("hr_up", "blocked"), ()),
        _a("dim:social",
           f"与好友{p['best_friend']}因先前劝阻未被采纳而产生争执与埋怨，关系未破裂但气氛尴尬，同时与黄牛账号彻底断联",
           ("与好友因受骗争执", "关系尴尬未破裂", "与骗子断联"),
           ("好友全力支持", "关系彻底破裂", "成功追回资金", "与骗子协商成功"),
           ("argue", "blocked", "report"), (p["best_friend"],)),
        _a("dim:emotion",
           "情绪经历期待、错愕、愤怒到懊悔的连续下跌，对被劝阻未听感到自责",
           ("错愕愤怒", "懊悔自责", "情绪连续下跌"),
           ("心情愉悦", "毫无波澜", "兴奋期待", "彻底平静"),
           ("blocked", "argue"), ()),
        _a("dim:finance",
           f"向个人账户转账{price}元购票后遭拉黑，资金基本无法追回，构成当日实际财产损失，举报后仅冻结对方收款",
           (f"损失{price}元无法追回", "实际财产损失", "举报仅冻结对方账户"),
           ("资金全额追回", "无任何损失", "获得赔偿", "资产增值"),
           ("paid", "blocked", "report"), (f"{price}元",)),
        _career_routine(c, "当日工作按常规推进，票务受骗未影响职业表现"),
    ]


def _s_forgotten_birthday(c: Ctx) -> List[Anchor]:
    p = c.p
    c.app("no_wish", (8 * 60, 9 * 60), "系统日历", "系统日历",
          f"今天没有日程安排。")
    c.app("coupon", (10 * 60, 11 * 60), "美团", "美团",
          f"生日快乐！送您一张{c.money(15, 60, 5)}元生日券，今日有效。")
    c.mic("colleague", (12 * 60, 13 * 60), f"同事-{p['colleague']}", "园区食堂",
          f"{p['colleague']}：今天你生日啊？没人跟你说吗，走，加个鸡腿。", noise_db=68)
    c.app("mother_late", (21 * 60 + 30, 22 * 60 + 30), "微信", f"母亲-{p['mother']}",
          f"{p['mother']}：哎呀妈忙忘了，生日快乐，周末回家吃饭。")
    c.mic("self", (22 * 60 + 30, 23 * 60 + 20), f"佩戴者-{p['name']}", "出租屋",
          f"{p['name']}对着小蛋糕说：又一个人过，也挺好的。", channel="自语")
    c.hr("hr_flat", (22 * 60, 23 * 60), c.rng.randint(70, 84))
    return [
        _a("global",
           f"{p['name']}生日当天家人与伴侣均无祝福，仅平台生日券与同事{p['colleague']}的加餐提醒了这一天，深夜母亲{p['mother']}补上迟到的问候，独居的孤独感与自我和解同时发生",
           ("生日被家人遗忘的孤独", "独居生日无人记得", "迟到的祝福与自我和解"),
           ("盛大的生日惊喜", "家人全程陪伴", "热闹的聚会", "被众人簇拥"),
           ("no_wish", "coupon", "colleague", "mother_late", "self"), (p["colleague"], p["mother"])),
        _a("dim:health",
           "全天体征平稳，夜间心率处于较低水平，饮食简单，无明显身体不适",
           ("体征平稳", "夜间心率偏低", "身体无不适"),
           ("心率骤升", "突发急症", "身体极度不适"),
           ("hr_flat", "self"), ()),
        _a("dim:social",
           f"家人未记起生日暴露情感联结的疏离，同事{p['colleague']}的临时关怀成为当日唯一社交暖意，母亲{p['mother']}深夜补偿性问候",
           ("家人疏忽暴露疏离", "同事给予临时关怀", "母亲迟到补偿问候"),
           ("家人精心准备惊喜", "朋友集体庆祝", "关系亲密无间", "社交热烈"),
           ("no_wish", "colleague", "mother_late"), (p["colleague"], p["mother"])),
        _a("dim:emotion",
           "情绪主基调为孤独与失落，夹杂自我宽慰，深夜以自嘲方式完成情绪的自我消化",
           ("孤独失落", "自我宽慰", "自嘲消化情绪"),
           ("喜悦满足", "兴奋激动", "毫无波澜", "狂喜"),
           ("self", "no_wish", "mother_late"), ()),
        _finance_routine(c, "当日仅收到平台生日券并有小额餐饮支出，无其他财务变动"),
        _career_routine(c, "当日按常规出勤工作，职业状态无变化"),
    ]


def _s_retired_rehire(c: Ctx) -> List[Anchor]:
    p = c.p
    fee = c.money(3000, 9000, 500)
    c.mic("rehire", (9 * 60, 10 * 60), "老厂厂长", "老厂办公室",
          f"老厂厂长：新来的技术员搞不定这批老设备，还得你回来带三个月，顾问费{fee}元。", noise_db=64)
    c.app("followup", (11 * 60, 12 * 60), "医院公众号", "社区卫生服务中心",
          f"慢病随访提醒：您本月血压记录{c.rng.randint(128, 148)}/{c.rng.randint(78, 92)}mmHg，请继续按时服药。")
    c.mic("square_dance", (19 * 60, 20 * 60), "舞伴-刘阿姨", "小区广场",
          f"舞伴-刘阿姨：你又要去上班啊？我们这队少个领舞的。", noise_db=82)
    c.hr("hr_walk", (19 * 60, 20 * 60), c.rng.randint(96, 112))
    c.app("family_worry", (21 * 60, 22 * 60), "微信", f"孩子-{p['child_name'] or p['best_friend']}",
          f"{p['child_name'] or p['best_friend']}：爸你别太累，血压还没稳。") if p["child_name"] else c.app(
        "family_worry", (21 * 60, 22 * 60), "微信", f"母亲-{p['mother']}", f"{p['mother']}：别太累。")
    return [
        _a("global",
           f"{p['name']}退休后获老厂返聘担任三个月技术顾问，顾问费{fee}元，但慢病随访显示血压仍需服药控制，家人与舞伴都劝其量力而行，价值感与健康约束形成拉扯",
           ("退休返聘与健康约束拉扯", "重返岗位但血压需控制", "返聘机会与慢病管理冲突"),
           ("彻底清闲无压力", "身体完全康复停药", "被拒绝返聘", "健康急剧恶化"),
           ("rehire", "followup", "family_worry"), (f"{fee}元",)),
        _a("dim:health",
           "慢病随访显示血压仍偏高需继续服药，广场舞等日常活动使心率维持在合理区间，整体状况稳定但需持续管理",
           ("血压偏高需继续服药", "慢病需持续管理", "日常活动心率合理"),
           ("血压完全正常可停药", "身体机能显著恶化", "突发心脑血管事件"),
           ("followup", "hr_walk"), ()),
        _a("dim:social",
           "与老厂恢复职业联结获得尊重，与广场舞同伴维持稳定社交，家人出于健康考虑表达担忧，三方关系均正向",
           ("恢复职业联结", "社区社交稳定", "家人表达关切"),
           ("被社会边缘化", "社交孤立", "家庭冲突", "被拒绝返聘"),
           ("rehire", "square_dance", "family_worry"), ()),
        _a("dim:emotion",
           "情绪主基调为被需要的满足感，夹杂对健康的隐忧，整体积极而克制",
           ("被需要的满足感", "积极而克制", "隐忧中带欣慰"),
           ("绝望消极", "极度焦虑", "毫无情绪", "愤怒失控"),
           ("rehire", "family_worry"), ()),
        _a("dim:finance",
           f"退休返聘带来{fee}元顾问费收入，是养老金之外的增量收入，当日无大额支出",
           (f"返聘顾问费{fee}元", "养老金外增量收入", "收入结构改善"),
           ("收入下降", "新增大额负债", "资产大幅缩水", "无任何收入变化"),
           ("rehire",), (f"{fee}元",)),
        _a("dim:career",
           "以技术顾问身份重返岗位带教新人，职业价值重新获得确认，工作强度受健康条件限制而需控制",
           ("返聘带教新人", "职业价值重新确认", "强度受健康限制"),
           ("完全退出职场", "工作毫无价值", "被辞退", "健康不允许任何工作"),
           ("rehire",), ()),
    ]


def _s_thesis_reject(c: Ctx) -> List[Anchor]:
    p = c.p
    c.app("reject", (10 * 60, 11 * 60), "邮件", "期刊编辑部",
          f"您的稿件经评审后决定：退修后重投，主要问题为方法学部分论证不足。")
    c.app("interview", (14 * 60, 15 * 60), "微信", "HR-校招",
          f"HR-校招：明天下午两点实习面试，请准备十分钟自我介绍与项目讲解。")
    c.mic("advisor", (16 * 60, 17 * 60), "导师", "实验室",
          f"导师：退修不是拒稿，方法学重写一遍，别灰心。", noise_db=56)
    c.mic("date", (20 * 60, 21 * 60), f"{p['partner_title']}-{p['partner_name']}", "校园湖边",
          f"{p['partner_name']}：面试加油，我明天陪你一起去。", noise_db=48) if p["partner_name"] else c.mic(
        "date", (20 * 60, 21 * 60), f"好友-{p['best_friend']}", "食堂",
        f"{p['best_friend']}：面试加油，我明天陪你去。", noise_db=70)
    c.hr("hr_up", (14 * 60, 15 * 60), c.rng.randint(92, 106))
    c.app("rewrite", (22 * 60, 23 * 60 + 20), "微信", "导师",
          f"{p['name']}：方法学我今晚重写一版，明天面试完就发您。", direction="发送")
    return [
        _a("global",
           f"{p['name']}论文被期刊要求退修重投，同日收到次日的实习面试通知，在导师鼓励与{p['partner_name'] or p['best_friend']}陪同下连夜重写方法学，学业挫折与就业机会同时到来",
           ("论文退修叠加实习面试", "学业受挫同时迎来面试", "连夜改稿备战面试"),
           ("论文直接录用", "面试被取消", "毫无进展", "彻底放弃学业"),
           ("reject", "interview", "advisor", "rewrite"), ()),
        _a("dim:health",
           "面试通知带来紧张使心率略升，熬夜改稿导致睡眠时长明显不足",
           ("睡眠严重不足", "紧张使心率略升", "熬夜透支"),
           ("作息规律睡眠充足", "精力充沛", "全天心率毫无波动"),
           ("hr_up", "rewrite"), ()),
        _a("dim:social",
           f"导师给予明确鼓励与指导，{p['partner_name'] or p['best_friend']}承诺陪同面试，支持系统有效运转，无冲突发生",
           ("导师鼓励指导", "伴侣或好友陪同支持", "支持系统有效"),
           ("导师严厉斥责", "被孤立无援", "关系破裂", "遭人冷嘲"),
           ("advisor", "date"), (p["partner_name"] or p["best_friend"],)),
        _a("dim:emotion",
           "情绪由退修带来的挫败迅速被面试机会拉回，紧张与期待并存，深夜转为专注与决心",
           ("挫败转期待", "紧张与期待并存", "专注与决心"),
           ("彻底绝望", "狂喜失控", "毫无情绪波动", "愤怒爆发"),
           ("reject", "interview", "rewrite"), ()),
        _finance_routine(c, "当日仅校园餐饮一类小额支出，无收入与债务变动"),
        _a("dim:career",
           "论文需退修重投使学术产出推迟，同时获得实习面试机会，职业入口出现新的可能性，需在两条路径上并行投入",
           ("论文退修学术产出推迟", "获得实习面试机会", "职业入口出现新可能"),
           ("论文直接录用", "面试机会取消", "毫无进展", "已被正式录用"),
           ("reject", "interview", "rewrite"), ()),
    ]


def _s_rider_bad_review(c: Ctx) -> List[Anchor]:
    p = c.p
    c.steps_total = c.rng.randint(16000, 28000)        # 全天骑行配送，活动量极高
    fine = c.money(50, 300, 10)
    orders = c.rng.randint(22, 46)
    c.app("fine", (11 * 60, 12 * 60), "骑手端", "配送平台",
          f"您因超时被系统扣款{fine}元，本月累计超时{c.rng.randint(2, 7)}次。")
    c.app("bad_review", (12 * 60 + 30, 13 * 60 + 30), "骑手端", "配送平台",
          f"您收到一条差评：送得太慢，汤都洒了。申诉窗口24小时。")
    c.mic("rain", (17 * 60, 18 * 60), "环境声", "路口",
          f"暴雨中路面积水过踝，电动车打滑，餐箱差点飞出去。", noise_db=84)
    c.imu("slip", (17 * 60 + 10, 17 * 60 + 30), round(c.rng.uniform(2.4, 4.2), 2))
    c.mic("customer", (18 * 60, 19 * 60), "顾客", "小区门口",
          f"顾客：超时半小时，汤全洒了，你说怎么办？", noise_db=66)
    c.mic("family_call", (21 * 60, 22 * 60), f"母亲-{p['mother']}", "电话",
          f"{p['mother']}：下雨就别跑了，钱少挣点不要紧。", noise_db=52)
    c.app("income", (22 * 60 + 30, 23 * 60 + 20), "骑手端", "配送平台",
          f"今日完成{orders}单，收入{c.money(180, 520, 10)}元，已扣除罚款{fine}元。")
    c.hr("hr_up", (17 * 60, 19 * 60), c.rng.randint(112, 132))
    return [
        _a("global",
           f"{p['name']}作为骑手在暴雨中完成{orders}单，却因超时被扣款{fine}元并收到差评，途中电动车打滑险些摔倒，晚间母亲{p['mother']}劝其雨天歇工，高强度劳动与低容错考核形成强烈反差",
           ("暴雨送单遭遇差评罚款", "高强度配送与差评罚款叠加", "骑手的一天在暴雨与差评中收场"),
           ("零差评高收入", "天气晴好顺利", "获得平台奖励", "轻松的一天"),
           ("fine", "bad_review", "rain", "income", "family_call"),
           (f"{orders}单", f"{fine}元", p["mother"])),
        _a("dim:health",
           f"暴雨中长时间骑行导致体力透支，心率长时间维持在120bpm以上，途中车辆打滑存在外伤风险，晚间腰背酸痛",
           ("体力严重透支", "心率长时间偏高", "存在摔伤风险", "腰背酸痛"),
           ("身体轻松无疲劳", "全天心率平稳", "毫无风险", "精力充沛"),
           ("rain", "slip", "hr_up", "income"), ()),
        _a("dim:social",
           f"与顾客因超时和洒汤发生争执但未升级，与平台之间是被考核与被扣款的单向关系，母亲{p['mother']}表达心疼与劝阻",
           ("与顾客争执未升级", "被平台考核扣款", "母亲心疼劝阻"),
           ("顾客体谅致谢", "平台给予奖励", "关系全面和谐", "与家人冲突"),
           ("customer", "bad_review", "family_call"), (p["mother"],)),
        _a("dim:emotion",
           "情绪以委屈、憋闷与隐忍为主，面对差评和罚款无力申诉，深夜在家人安慰下略感温暖",
           ("委屈憋闷", "隐忍无力", "深夜略感温暖"),
           ("心情愉悦", "愤怒爆发", "毫无情绪", "得意满足"),
           ("bad_review", "customer", "family_call"), ()),
        _a("dim:finance",
           f"当日完成{orders}单配送收入被扣除超时罚款{fine}元，恶劣天气补贴不足以覆盖罚款，净收入明显低于预期",
           (f"当日{orders}单收入被扣罚{fine}元", "净收入低于预期", "罚款侵蚀收入"),
           ("收入大幅超预期", "获得平台奖励", "无任何扣款", "获得额外补贴"),
           ("fine", "income"), (f"{orders}单", f"{fine}元")),
        _a("dim:career",
           f"超时次数累积影响骑手评级与派单权重，职业发展受平台算法考核制约，恶劣天气下的劳动强度不可持续",
           ("超时累积影响评级", "受平台算法考核制约", "劳动强度不可持续"),
           ("评级晋升", "获得平台表彰", "工作强度轻松", "转为管理岗"),
           ("fine", "bad_review", "income"), ()),
    ]


def _s_shop_rent_hike(c: Ctx) -> List[Anchor]:
    p = c.p
    hike = c.money(800, 4000, 100)
    loan = c.money(30000, 200000, 10000)
    c.mic("landlord", (10 * 60, 11 * 60), "房东", "店内",
          f"房东：下个月起租金涨{hike}元，这条街都涨了，你不租有的是人。", noise_db=66)
    c.app("sales", (14 * 60, 15 * 60), "微信", "老顾客",
          f"老顾客：你们还开着啊？我以后多来，隔壁那家搬走了。")
    c.app("bank", (16 * 60, 17 * 60), "银行", "小微企业信贷",
          f"您的经营贷预审额度{loan}元，年化利率{round(c.rng.uniform(3.6, 6.8), 2)}%，需补充近半年流水。")
    c.hr("hr_up", (10 * 60, 11 * 60), c.rng.randint(94, 108))
    c.mic("family", (21 * 60, 22 * 60), f"{p['partner_title'] or '母亲'}-{p['partner_name'] or p['mother']}", "店内",
          f"{p['partner_name'] or p['mother']}：实在不行就换个偏点的位置，别硬撑。", noise_db=58)
    return [
        _a("global",
           f"{p['name']}经营的门店被房东通知涨租{hike}元，客流因周边搬迁有所流失，正考虑申请{loan}元经营贷维持周转，家人建议降低选址成本，小微经营者的生存压力集中爆发",
           ("门店涨租挤压经营", "涨租叠加客流流失", "小微经营者生存压力"),
           ("生意火爆", "租金下调", "获得大额补贴", "毫无压力"),
           ("landlord", "sales", "bank", "family"), (f"{hike}元", f"{loan}元")),
        _a("dim:health",
           "全天站立经营体力消耗大，得知涨租后心率上升，长期作息不规律",
           ("体力消耗大", "心率上升", "作息不规律"),
           ("全天轻松无消耗", "作息规律", "身体状态极佳"),
           ("hr_up", "landlord"), ()),
        _a("dim:social",
           f"与房东处于涨租博弈的对立位置，老顾客表达支持形成正向关系，家人建议收缩经营，三方立场不一",
           ("与房东博弈对立", "老顾客支持", "家人建议收缩", "立场不一"),
           ("房东体谅不涨租", "顾客集体流失", "家人强力支持扩张", "关系全面和谐"),
           ("landlord", "sales", "family"), ()),
        _a("dim:emotion",
           "情绪以焦虑与不甘为主，既舍不得经营多年的门店又担忧亏损扩大，深夜陷入两难",
           ("焦虑不甘", "两难纠结", "担忧亏损"),
           ("心情愉悦", "毫无压力", "兴奋激动", "彻底绝望"),
           ("landlord", "family"), ()),
        _a("dim:finance",
           f"门店月租金上涨{hike}元使固定成本上升，正评估{loan}元经营贷补充周转，负债可能增加，现金流承压",
           (f"月租上涨{hike}元", f"评估{loan}元经营贷", "固定成本上升", "现金流承压"),
           ("租金下降", "获得大额补贴", "现金流充裕", "负债全部清偿"),
           ("landlord", "bank"), (f"{hike}元", f"{loan}元")),
        _a("dim:career",
           "自营事业面临成本上升与客流波动的双重考验，需在续约、迁址与融资之间做出经营决策",
           ("自营事业面临成本考验", "需做经营决策", "客流波动带来不确定性"),
           ("生意扩张开分店", "经营毫无压力", "已关闭门店", "获得投资"),
           ("landlord", "sales", "bank"), ()),
    ]


def _s_newborn_night_feed(c: Ctx) -> List[Anchor]:
    p = c.p
    times = c.rng.randint(3, 6)
    c.mic("night_feed", (22 * 60 + 45, 23 * 60 + 20), f"婴儿-{p['child_name'] or '宝宝'}", "卧室",
          f"婴儿持续啼哭，{p['name']}起身冲奶并拍嗝。", noise_db=62)
    c.app("tracker", (7 * 60, 8 * 60), "育儿App", "育儿记录",
          f"昨夜夜奶{times}次，累计清醒{times * 45}分钟，母亲睡眠中断{times}次。")
    c.mic("mil", (10 * 60, 11 * 60), "社区医生", "社区卫生服务中心",
          f"社区医生：产后情绪筛查得分偏高，注意休息，必要时来做个评估。", noise_db=52)
    c.mic("mil_conflict", (19 * 60, 20 * 60), "婆婆", "家中客厅",
          f"婆婆：孩子哭就是没吃饱，你奶水不够得加奶粉。", noise_db=58)
    c.mic("husband", (21 * 60, 22 * 60), f"{p['partner_title']}-{p['partner_name']}", "卧室",
          f"{p['partner_name']}：夜里我起来两次，你多睡会儿。", noise_db=46) if p["partner_name"] else c.mic(
        "husband", (21 * 60, 22 * 60), f"母亲-{p['mother']}", "卧室",
        f"{p['mother']}：夜里我帮你带，你睡。", noise_db=46)
    c.hr("hr_low", (6 * 60, 7 * 60), c.rng.randint(58, 72))
    return [
        _a("global",
           f"{p['name']}夜间被夜奶{times}次打断睡眠，产后情绪筛查得分偏高被建议评估，又因喂养方式与婆婆产生分歧，配偶{p['partner_name'] or p['mother']}夜间分担照护，育儿辛劳与家庭观念冲突交织",
           ("夜奶频繁叠加产后情绪预警", "育儿辛劳与喂养观念冲突", "新手家长的疲惫一天"),
           ("婴儿整夜安睡", "产后状态极佳", "家庭毫无分歧", "轻松育儿"),
           ("night_feed", "tracker", "mil", "mil_conflict"), (f"{times}次",)),
        _a("dim:health",
           f"夜间因夜奶{times}次严重睡眠剥夺，晨起静息心率偏低显示疲劳，产后情绪筛查得分偏高需进一步评估",
           ("严重睡眠剥夺", "产后情绪筛查偏高", "疲劳导致静息心率偏低"),
           ("睡眠充足", "产后恢复良好", "精力充沛", "身体状态极佳"),
           ("night_feed", "tracker", "mil", "hr_low"), (f"{times}次",)),
        _a("dim:social",
           f"与婆婆在喂养方式上产生观念冲突，与配偶{p['partner_name'] or p['mother']}因夜间分担而形成有效协作，社区医生给予专业支持",
           ("与婆婆喂养观念冲突", "配偶夜间分担协作", "获得社区医生支持"),
           ("婆媳关系融洽", "配偶完全缺席", "家庭全面支持", "关系破裂"),
           ("mil_conflict", "husband", "mil"), (p["partner_name"] or p["mother"],)),
        _a("dim:emotion",
           "情绪主基调为疲惫与情绪低落，产后情绪筛查提示风险，被质疑奶水时感到委屈，夜间获得分担后略有缓解",
           ("疲惫低落", "产后情绪风险", "被质疑时委屈"),
           ("心情愉悦", "情绪稳定积极", "毫无压力", "兴奋激动"),
           ("mil", "mil_conflict", "husband"), ()),
        _finance_routine(c, "当日产生奶粉与尿布一类母婴用品支出，属常规育儿开销，无新增大额债务"),
        _a("dim:career",
           "处于产假或哺乳期内，工作职责暂停由同事代管，职业中断带来的返岗压力隐约存在",
           ("产假期间职责暂停", "职业中断待返岗", "工作由他人代管"),
           ("正常工作推进", "获得晋升", "被辞退", "职业发展加速"),
           ("trivia_sample", "mil"), ()),
    ]


def _s_night_nurse_rescue(c: Ctx) -> List[Anchor]:
    p = c.p
    c.mic("rescue", (22 * 60 + 40, 23 * 60 + 15), "值班医生", "急诊抢救室",
          f"值班医生：肾上腺素再推一支，准备除颤，家属先出去。", noise_db=78)
    c.app("record", (23 * 60 + 10, 23 * 60 + 25), "HIS系统", "护理记录",
          f"抢救记录已提交：患者自主心律恢复，转入ICU继续观察。")
    c.mic("family_argue", (23 * 60 + 15, 23 * 60 + 28), "患者家属", "急诊走廊",
          f"患者家属：为什么等了这么久才抢救？你们得给个说法。", noise_db=74)
    c.mic("charge", (23 * 60 + 20, 23 * 60 + 29), "护士长", "护士站",
          f"护士长：沟通我来做，你先把记录补齐，别自己扛。", noise_db=64)
    c.app("schedule", (14 * 60, 15 * 60), "微信", "科室排班群",
          f"护士长：本月夜班调整为{c.rng.randint(6, 10)}个，你连上三天，注意身体。", session="群聊")
    c.hr("hr_night", (22 * 60 + 40, 23 * 60 + 20), c.rng.randint(104, 124))
    c.mic("self", (21 * 60, 22 * 60), f"佩戴者-{p['name']}", "值班室",
          f"{p['name']}：今晚这个班不好上，先把交接班做完。", channel="自语")
    return [
        _a("global",
           f"{p['name']}夜班参与急诊抢救使患者恢复自主心律，随后遭患者家属质疑抢救时机，护士长出面沟通并调整排班至连续三天夜班，职业成就感与医患紧张、体力透支同时存在",
           ("抢救成功却遭家属质疑", "夜班抢救与医患冲突", "救回病人后被责难"),
           ("毫无紧张的夜班", "家属致谢送锦旗", "排班轻松", "患者抢救无效"),
           ("rescue", "record", "family_argue", "charge", "schedule"), ()),
        _a("dim:health",
           "连续夜班导致昼夜节律紊乱，抢救期间心率维持在110bpm以上，下班后极度疲劳",
           ("昼夜节律紊乱", "抢救时心率偏高", "极度疲劳"),
           ("作息规律", "精力充沛", "全天心率平稳"),
           ("hr_night", "schedule", "self"), ()),
        _a("dim:social",
           f"与患者家属因抢救时机产生对立，护士长主动承担沟通形成保护性支持，科室团队内部协作紧密",
           ("与家属对立", "护士长承担沟通", "团队内部协作紧密"),
           ("家属高度感激", "被团队孤立", "同事推卸责任", "关系全面和谐"),
           ("family_argue", "charge", "rescue"), ()),
        _a("dim:emotion",
           "情绪由抢救时的高度紧张转为成功后的欣慰，被家属质疑时感到委屈，深夜以自我说服方式消化",
           ("紧张转欣慰", "被质疑的委屈", "自我说服消化情绪"),
           ("毫无波澜", "极度愤怒爆发", "狂喜", "彻底崩溃"),
           ("family_argue", "self", "record"), ()),
        _finance_routine(c, "当日仅有夜班餐补与通勤一类小额支出，收入与债务无变动"),
        _a("dim:career",
           "成功完成急诊抢救体现专业能力，但排班被调整为连续三天夜班，职业负荷持续加重，医患沟通风险成为职业压力来源",
           ("抢救成功体现专业能力", "排班负荷加重", "医患沟通成为压力源"),
           ("获得表彰晋升", "工作轻松无压力", "被追责处分", "转为行政岗"),
           ("rescue", "schedule", "charge"), ()),
    ]


# ---------------------------------------------------------------------------
# 副线池：为某一天补充次级要点（每条 1 个维度锚点 + 2~4 个事件）
# ---------------------------------------------------------------------------
def _p_express_dispute(c: Ctx) -> List[Anchor]:
    fee = c.money(8, 40, 2)
    c.app("overdue", (17 * 60, 18 * 60), "微信", c.choice(EXPRESS_STATIONS),
          f"{c.choice(EXPRESS_STATIONS)}：您的包裹已超时{c.rng.randint(2, 5)}天，将收取保管费{fee}元。")
    c.mic("argue_station", (18 * 60, 18 * 60 + 40), "驿站店员", c.choice(EXPRESS_STATIONS),
          f"驿站店员：规矩就是这样，我这边也没办法。", noise_db=68)
    return [_a("dim:emotion",
               f"因包裹超时被收取{fee}元保管费与驿站店员发生口角，产生短暂的烦躁与不被理解感",
               ("因小事烦躁", "口角带来的不快", "被规则为难的不适"),
               ("彻底崩溃", "极度愤怒失控", "毫无情绪波动", "心情愉悦"),
               ("overdue", "argue_station"), (f"{fee}元",), sev=2)]


def _p_gym_renewal(c: Ctx) -> List[Anchor]:
    price = c.money(1200, 4800, 100)
    c.mic("gym_sell", (19 * 60, 20 * 60), "健身会籍顾问", "健身房前台",
          f"健身会籍顾问：年卡现在续只要{price}元，明天就恢复原价了。", noise_db=74)
    return [_a("dim:finance",
               f"健身房年卡续费推销报价{price}元，当日未决定，属待议的非必要消费",
               ("面临续费推销", "非必要消费待议", "被推销年卡"),
               ("已支付巨额消费", "获得大额退款", "资产大幅增值", "新增大额负债"),
               ("gym_sell",), (f"{price}元",), sev=2)]


def _p_secondhand_sale(c: Ctx) -> List[Anchor]:
    gain = c.money(200, 2600, 50)
    c.app("sold", (20 * 60, 21 * 60), "闲鱼", "买家",
          f"买家已拍下您发布的闲置{c.choice(('旧手机', '显示器', '婴儿车', '山地车', '相机镜头'))}，成交{gain}元。")
    return [_a("dim:finance",
               f"通过二手平台出售闲置物品回笼资金{gain}元，属小额资产变现",
               ("二手变现回笼资金", "出售闲置获得收入", "小额资产变现"),
               ("大额资产增值", "遭遇诈骗损失", "新增大额负债", "无任何收入"),
               ("sold",), (f"{gain}元",), sev=2)]


def _p_medical_insurance(c: Ctx) -> List[Anchor]:
    total, back = c.money(300, 2600, 50), c.money(80, 900, 10)
    c.app("clinic", (15 * 60, 16 * 60), "医院公众号", "门诊结算",
          f"本次门诊总费用{total}元，医保统筹报销{back}元，个人自付{total - back}元。")
    return [_a("dim:finance",
               f"门诊就医总费用{total}元，医保统筹报销{back}元，个人自付{total - back}元",
               ("门诊费用经医保报销", "自付部分医疗费用", "医保分担就医成本"),
               ("全额自费无报销", "获得大额理赔", "无任何医疗支出", "资产大幅增值"),
               ("clinic",), (f"{total}元", f"{back}元"), sev=2)]


def _p_family_supplement(c: Ctx) -> List[Anchor]:
    price = c.money(300, 3000, 100)
    c.mic("supplement", (19 * 60 + 30, 20 * 60 + 30), f"母亲-{p_name(c)}", "家中客厅",
          f"{p_name(c, 'mother')}：这个{c.choice(('氨糖', '鱼油', '蛋白粉', '辅酶Q10'))}花了{price}元，人家说对关节好。",
          noise_db=52)
    return [_a("dim:health",
               f"家人自行购买{price}元保健品，本人对其功效持保留态度，家庭健康观念存在分歧",
               ("家人购买保健品", "健康观念存在分歧", "对保健品功效存疑"),
               ("医生建议的规范治疗", "身体指标显著改善", "确诊重症", "完全无视健康"),
               ("supplement",), (f"{price}元",), sev=2)]


def _p_commute_late(c: Ctx) -> List[Anchor]:
    p = c.p
    c.app("metro_fault", (8 * 60, 9 * 60), "地铁官方", "地铁运营",
          f"因信号设备故障，{c.rng.randint(2, 9)}号线部分区段限速运行，预计延误15分钟以上。")
    c.app("kaoqin", (9 * 60 + 30, 10 * 60 + 30), "OA系统", "考勤系统",
          f"您今日打卡时间超过规定时间，已记为迟到1次。")
    return [_a("dim:career",
               "因地铁信号故障导致通勤延误并被考勤系统记为迟到，工作出勤记录受影响",
              ("地铁故障导致迟到", "出勤记录受影响", "通勤延误被记迟到"),
              ("获得表彰", "晋升通知", "工作毫无影响", "被辞退"),
              ("metro_fault", "kaoqin"), (), sev=2)]


def _p_team_building(c: Ctx) -> List[Anchor]:
    p = c.p
    fee = c.money(80, 300, 10)
    c.app("aa", (18 * 60, 19 * 60), "微信", f"同事-{p['colleague']}",
          f"{p['colleague']}：团建AA{fee}元，转账给行政就行，周六爬山。", session="群聊")
    return [_a("dim:social",
               f"团队组织周末爬山团建并按AA{fee}元收费，同事间维持常规协作与社交往来",
              ("团队团建活动", "同事常规社交", "AA制集体活动"),
              ("团队彻底分裂", "被同事排挤", "关系破裂", "发生激烈冲突"),
              ("aa",), (f"{fee}元",), sev=2)]


def _p_parking_fee(c: Ctx) -> List[Anchor]:
    fee = c.money(200, 900, 50)
    c.app("parking", (12 * 60, 13 * 60), "微信", "物业管家",
          f"物业管家：本季度停车费{fee}元，月底前缴纳，逾期按日加收。")
    return [_a("dim:finance",
               f"需缴纳本季度停车费{fee}元，属固定居住类支出",
              ("缴纳停车费", "固定居住支出", "物业费用到期"),
              ("获得大额收入", "费用减免", "新增大额负债", "资产大幅增值"),
              ("parking",), (f"{fee}元",), sev=2)]


def _p_side_gig(c: Ctx) -> List[Anchor]:
    p = c.p
    gain = c.money(300, 3000, 50)
    c.app("gig", (21 * 60, 22 * 60), "微信", "私单客户",
          f"私单客户：这次的活儿做得不错，{gain}元已转，下周还有一个。")
    return [_a("dim:finance",
               f"承接私单副业交付获得{gain}元报酬，形成工资之外的第二收入来源",
              ("副业收入到账", "第二收入来源", "私单交付获得报酬"),
              ("副业失败亏损", "收入下降", "新增大额负债", "获得巨额奖金"),
              ("gig",), (f"{gain}元",), sev=2),
            _a("dim:career",
               "利用业余时间承接私单，职业技能获得市场化验证，但精力被本职之外的任务分散",
              ("副业验证技能", "精力被分散", "市场化能力获认可"),
              ("工作全面停滞", "被公司处分", "获得晋升", "职业发展受阻"),
              ("gig",), (), sev=2)]


def _p_appliance_repair(c: Ctx) -> List[Anchor]:
    cost = c.money(150, 1800, 50)
    c.mic("repair", (20 * 60, 21 * 60), "维修师傅", "家中",
          f"维修师傅：压缩机坏了，修{cost}元，换新还不如修。", noise_db=58)
    return [_a("dim:finance",
               f"家电故障产生{cost}元维修支出，属计划外的家庭开支",
              ("家电维修支出", "计划外家庭开支", "维修费用支出"),
              ("获得大额收入", "无任何额外支出", "资产大幅增值", "新增大额负债"),
              ("repair",), (f"{cost}元",), sev=2)]


def _p_child_class_fee(c: Ctx) -> List[Anchor]:
    p = c.p
    fee = c.money(1200, 9800, 100)
    c.app("class_fee", (16 * 60, 17 * 60), "微信", "培训机构老师",
          f"培训机构老师：{p['child_name']}下季度课时费{fee}元，今天报名送一节课。")
    return [_a("dim:finance",
               f"为孩子{p['child_name']}缴纳课外培训课时费{fee}元，家庭教育支出占家庭现金流比重较高",
              (f"缴纳培训费{fee}元", "家庭教育支出", "育儿成本上升"),
              ("教育支出大幅下降", "获得大额补贴", "无任何额外支出", "资产大幅增值"),
              ("class_fee",), (p["child_name"], f"{fee}元"), sev=2)]


def _p_pet_vaccine(c: Ctx) -> List[Anchor]:
    p = c.p
    fee = c.money(120, 800, 20)
    c.app("vaccine", (17 * 60, 18 * 60), "宠物医院", "宠物医院",
          f"{p['pet']}本年度疫苗已完成接种，费用{fee}元，下次接种一年后。")
    return [_a("dim:health",
               f"为{p['pet']}完成年度疫苗接种支出{fee}元，家庭成员（含宠物）的健康管理按计划推进",
              ("宠物疫苗接种", "家庭健康管理推进", "按计划完成接种"),
              ("宠物重病", "家人突发急症", "健康严重恶化", "完全忽视健康"),
              ("vaccine",), (p["pet"], f"{fee}元"), sev=2)]


def _p_blind_date_arranged(c: Ctx) -> List[Anchor]:
    p = c.p
    c.app("arrange", (19 * 60, 20 * 60), "微信", f"母亲-{p['mother']}",
          f"{p['mother']}：周日相亲我给你约好了，人家条件不错，你必须去。")
    c.mic("resist", (20 * 60, 21 * 60), f"佩戴者-{p['name']}", "家中",
          f"{p['name']}：我自己的事我自己有数，别老替我安排。", channel="自语")
    return [_a("dim:social",
               f"母亲{p['mother']}单方面安排周日相亲，本人表达抗拒，代际之间在婚恋自主权上存在张力",
              ("父母安排相亲", "代际婚恋观念张力", "本人抗拒被安排"),
              ("家庭关系彻底破裂", "本人欣然接受", "毫无分歧", "断绝亲子关系"),
              ("arrange", "resist"), (p["mother"],), sev=2)]


def _p_body_fat(c: Ctx) -> List[Anchor]:
    fat = round(c.rng.uniform(21.0, 33.0), 1)
    c.app("bodyfat", (21 * 60, 22 * 60), "健康", "体脂秤",
          f"本次体脂率{fat}%，较上月上升{round(c.rng.uniform(0.3, 2.4), 1)}个百分点。")
    return [_a("dim:health",
               f"体脂率测得{fat}%且较上月上升，提示近期运动量不足与饮食结构失衡",
              ("体脂率上升", "运动量不足", "饮食结构失衡"),
              ("体脂显著下降", "身体指标全面改善", "健康状况极佳", "突发急症"),
              ("bodyfat",), (f"{fat}%",), sev=2)]


def p_name(c: Ctx, key: str = "name") -> str:
    return str(c.p[key])


SUBPLOTS: Tuple[Subplot, ...] = (
    Subplot("EXPRESS_DISPUTE", "", _p_express_dispute),
    Subplot("GYM_RENEWAL", "", _p_gym_renewal),
    Subplot("SECONDHAND_SALE", "", _p_secondhand_sale),
    Subplot("MEDICAL_INSURANCE", "", _p_medical_insurance),
    Subplot("FAMILY_SUPPLEMENT", "parent", _p_family_supplement),
    Subplot("COMMUTE_LATE", "", _p_commute_late),
    Subplot("TEAM_BUILDING", "", _p_team_building),
    Subplot("PARKING_FEE", "", _p_parking_fee),
    Subplot("SIDE_GIG", "", _p_side_gig),
    Subplot("APPLIANCE_REPAIR", "", _p_appliance_repair),
    Subplot("CHILD_CLASS_FEE", "child", _p_child_class_fee),
    Subplot("PET_VACCINE", "pet", _p_pet_vaccine),
    Subplot("BLIND_DATE_ARRANGED", "single", _p_blind_date_arranged),
    Subplot("BODY_FAT_RISE", "", _p_body_fat),
)


SPINES: Tuple[Spine, ...] = (
    Spine("CRITICISM_AND_BREAKUP", "当众批评叠加晚间分手", "partner", 22, 45, _s_criticism_breakup),
    Spine("QUARTERLY_REJECTED_PARENT_HOSPITAL", "汇报被否决叠加父亲住院", "parent", 24, 55, _s_quarterly_rejected_debt),
    Spine("LAYOFF_RUMOR_MORTGAGE_FAIL", "裁员传闻叠加房贷扣款失败", "", 25, 50, _s_layoff_rumor_mortgage),
    Spine("LAUNCH_PROMOTION_MARRIAGE_PRESSURE", "上线成功叠加催婚争执", "", 25, 40, _s_launch_promotion_pressure),
    Spine("HEADHUNTER_NONCOMPETE", "挖角机会与竞业限制冲突", "", 26, 48, _s_headhunter_noncompete),
    Spine("CUSTOMER_COMPLAINT_CLAIM", "客户索赔引发全天救火", "", 24, 55, _s_customer_complaint),
    Spine("INTERN_BLAME_TEAM_CONFLICT", "线上事故追责与团队分歧", "", 25, 45, _s_intern_blame),
    Spine("TRIP_DELAY_HOME_LEAK", "出差延误叠加家中漏水", "", 25, 55, _s_trip_delay_leak),
    Spine("CHECKUP_THYROID_NODULE", "体检查出结节引发健康焦虑", "", 24, 62, _s_checkup_nodule),
    Spine("NOCTURNAL_PALPITATION_ALONE", "独居深夜心悸发作", "single", 23, 45, _s_nocturnal_palpitation),
    Spine("BP_RECHECK_DRINKING_CONFLICT", "血压升高与应酬劝酒冲突", "", 30, 60, _s_bp_recheck_drinking),
    Spine("PARENT_FALL_LEAVE_DENIED", "父亲跌倒与请假被拒", "parent", 26, 55, _s_parent_fall_leave),
    Spine("PREGNANCY_CHECK_HANDOVER", "产检与工作交接叠加配偶出差", "partner", 24, 40, _s_pregnancy_handover),
    Spine("BLIND_DATE_FENDER_BENDER", "相亲顺利叠加追尾事故", "", 24, 45, _s_blind_date_fender),
    Spine("COLD_WAR_RECONCILE_RENT_HIKE", "冷战和解叠加房租上涨", "", 23, 42, _s_cold_war_reconcile),
    Spine("FRIEND_LOAN_FALLOUT_INVEST_LOSS", "好友催债叠加合伙亏损", "", 25, 50, _s_friend_loan_fallout),
    Spine("WEDDING_GIFT_PEER_PRESSURE", "随礼压力叠加同学攀比", "", 24, 42, _s_wedding_gift_pressure),
    Spine("PARENT_TEACHER_MEETING_CONFLICT", "孩子被约谈引发家庭冲突", "child", 28, 50, _s_parent_teacher_meeting),
    Spine("FUND_LOSS_CUT_RATE_CUT", "基金割肉叠加房贷利率下调", "", 26, 55, _s_fund_loss_cut),
    Spine("PAYDAY_SIDE_INCOME_PRAISE", "工资与副业到账叠加工作被肯定", "", 23, 48, _s_payday_side_income),
    Spine("REFUND_SCAM_RISK_CONTROLLED", "冒充客服诈骗被风控拦截", "", 22, 65, _s_refund_scam),
    Spine("INSURANCE_CLAIM_DENIED", "理赔被拒与续保两难", "", 28, 62, _s_insurance_claim_denied),
    Spine("PET_DEATH_LEAVE", "陪伴多年的宠物离世", "pet", 22, 55, _s_pet_death),
    Spine("EXAM_RESULT_FAIL_RETRY", "考试落榜后决定再战一年", "", 22, 34, _s_exam_result_fail),
    Spine("TICKET_SCAM_FRIEND_ARGUE", "黄牛票受骗与好友争执", "", 20, 36, _s_ticket_scam),
    Spine("FORGOTTEN_BIRTHDAY_ALONE", "独居生日被家人遗忘", "", 24, 45, _s_forgotten_birthday),
    Spine("RETIRED_REHIRE_CHRONIC_CARE", "退休返聘与慢病管理拉扯", "", 55, 68, _s_retired_rehire,
          jobs=("退休返聘技术员", "机械工程师", "电气工程师", "公务员科员")),
    Spine("THESIS_REJECT_INTERVIEW", "论文退修叠加实习面试", "", 22, 28, _s_thesis_reject,
          jobs=("研究生", "大三学生")),
    Spine("RIDER_BAD_REVIEW_STORM", "暴雨送单遭遇差评罚款", "", 20, 52, _s_rider_bad_review,
          jobs=("外卖骑手",)),
    Spine("SHOP_RENT_HIKE_SURVIVAL", "门店涨租挤压小微经营", "", 26, 60, _s_shop_rent_hike,
          jobs=("便利店店主", "花店老板", "餐厅店长", "创业者")),
    Spine("NEWBORN_NIGHT_FEED_CONFLICT", "夜奶频繁与喂养观念冲突", "child", 24, 42, _s_newborn_night_feed),
    Spine("NIGHT_NURSE_RESCUE_CONFLICT", "夜班抢救成功却遭家属质疑", "", 23, 55, _s_night_nurse_rescue,
          jobs=("三甲医院护士长", "住院医师", "药剂师")),
)


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------
def _eligible(spine: Spine, persona: Mapping[str, Any]) -> bool:
    if not (spine.age_min <= int(persona["age"]) <= spine.age_max):
        return False
    if spine.jobs and persona["occupation"] not in spine.jobs:
        return False
    req = spine.requires
    if req == "partner" and not persona["partner_name"]:
        return False
    if req == "single" and persona["partner_name"]:
        return False
    if req == "child" and not persona["has_child"]:
        return False
    if req == "pet" and not persona["pet"]:
        return False
    return True


def _pick_spine(rng: random.Random, persona: Mapping[str, Any], avoid: str, index: int = 0) -> Spine:
    """选主线。

    用 ``index % len(SPINES)`` 做轮转首选，保证 32 条主线在全库上分布均衡；
    首选主线与人物设定不匹配（职业/年龄/婚育/宠物条件）时才随机回退，
    因此单题只依赖自己的 index 与种子，仍然完全可复现。
    """
    preferred = SPINES[index % len(SPINES)]
    if preferred.spine_id != avoid and _eligible(preferred, persona):
        return preferred
    pool = [s for s in SPINES if _eligible(s, persona) and s.spine_id != avoid]
    if not pool:
        pool = [s for s in SPINES if s.spine_id != avoid and not s.jobs and not s.requires]
    return rng.choice(pool)


def _pick_subplots(rng: random.Random, persona: Mapping[str, Any], count: int) -> List[Subplot]:
    pool = [sp for sp in SUBPLOTS if _eligible(Spine("", "", sp.requires, 0, 200, lambda c: []), persona)]
    rng.shuffle(pool)
    return pool[:count]


def _blood_pressure(rng: random.Random) -> str:
    """生成生理自洽的血压读数（脉压差 30~60mmHg）。"""
    systolic = rng.randint(106, 152)
    diastolic = min(96, max(62, systolic - rng.randint(34, 58)))
    return f"{systolic}/{diastolic}"


def _build_sensor(ctx: Ctx, persona: Mapping[str, Any]) -> Dict[str, Any]:
    rng = ctx.rng
    night = [e for e in ctx.hr_events + ctx.imu_events if minutes_of(e["ts"]) >= 21 * 60 or minutes_of(e["ts"]) <= 6 * 60]
    base_sleep = float(persona["sleep_baseline_hours"])
    sleep_hours = round(max(2.5, base_sleep - (rng.uniform(1.0, 2.6) if night else rng.uniform(0.0, 1.0))), 1)
    quality = "差" if sleep_hours < 5.5 else ("一般" if sleep_hours < 7 else "良好")
    periods = ("上午", "下午", "晚间")

    def period_of(stamp: str) -> str:
        m = minutes_of(stamp)
        return "上午" if m < 12 * 60 else ("下午" if m < 18 * 60 else "晚间")

    counts = {k: 0 for k in periods}
    for event in ctx.hr_events:
        counts[period_of(event["ts"])] += 1
    ctx.refs["sensor"] = ["S0"]
    return {
        "sensor_id": "S0",
        "device": "智能手环（全天佩戴）",
        "sleep_hours": sleep_hours,
        "sleep_quality": quality,
        "morning_resting_hr_bpm": int(persona["resting_hr_baseline"]) + (rng.randint(2, 9) if night else rng.randint(-2, 3)),
        "steps_total": ctx.steps_total,
        "steps_reading": f"{ctx.steps_total}步",
        "sleep_reading": f"{sleep_hours}小时",
        "calories_kcal": rng.randint(1500, 3400),
        "hrv_rmsd_ms": rng.randint(18, 78),
        "blood_pressure": _blood_pressure(rng),
        "hr_events": sorted(ctx.hr_events, key=lambda e: e["ts"]),
        "imu_events": sorted(ctx.imu_events, key=lambda e: e["ts"]),
        "stress_index_by_period": [
            {"period": name, "index": min(98, 42 + counts[name] * 14 + rng.randint(-6, 10))} for name in periods
        ],
        "health_baseline": persona["health_baseline"],
    }


def _visible_tokens(core: str, evidence_text: str, limit: int = 4) -> List[str]:
    """从标答核心里抽取"确实在证据文本中出现过"的方向词，保证机器阅卷可判。"""
    found: List[str] = []
    seen = set()
    for size in (6, 5, 4, 3, 2):
        for start in range(0, max(0, len(core) - size + 1)):
            token = core[start:start + size]
            if not all("\u4e00" <= ch <= "\u9fff" or ch.isdigit() for ch in token):
                continue
            if token in evidence_text and not any(token in s for s in seen):
                seen.add(token)
                found.append(token)
        if len(found) >= limit:
            break
    return found[:limit]


def _anchor_payload(anchor: Anchor, ctx: Ctx, ref_index: Mapping[str, str]) -> Dict[str, Any]:
    """把一个锚点渲染成标答 JSON。

    ``directional_keywords`` 只从**该锚点自己引用的证据碎片**里抽取，
    保证机器阅卷用到的方向词一定能在题面被引用的碎片中找到。
    """
    refs = [ref for tag in anchor.tags for ref in ctx.refs.get(tag, [])]
    evidence_text = "\n".join(ref_index.get(ref, "") for ref in refs)
    return {
        "semantic_core": anchor.core,
        "acceptable_synonyms": list(anchor.synonyms),
        "red_line_rejections": list(anchor.red_lines),
        "directional_keywords": _visible_tokens(anchor.core, evidence_text),
        "key_entities": list(anchor.entities),
        "evidence_ref_ids": refs,
        "severity": anchor.severity,
    }


def _persona_for(rng: random.Random, index: int, spine: Spine, attempts: int = 2000) -> Optional[Dict[str, Any]]:
    """反复生成人物设定，直到满足指定主线的职业/年龄/婚育/宠物条件。"""
    for _ in range(attempts):
        persona = build_persona(rng, index)
        if _eligible(spine, persona):
            return persona
    return None


def build_question(rng: random.Random, index: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """构建一道题（题面 + 标答），返回 ``(question, ground_truth)``。"""
    # 先按 index 轮转选定主线，再反向生成与之匹配的人物设定，
    # 这样 32 条主线在全库上分布均衡（各约 1/32），且人设与剧情始终自洽。
    spine = SPINES[index % len(SPINES)]
    persona = _persona_for(rng, index, spine)
    if persona is None:
        persona = build_persona(rng, index)
        spine = _pick_spine(rng, persona, avoid="", index=index)
    ctx = Ctx(rng, persona)
    anchors: List[Anchor] = list(spine.build(ctx))
    subplot_ids = []
    for subplot in _pick_subplots(rng, persona, rng.randint(1, 3)):
        anchors.extend(subplot.build(ctx))
        subplot_ids.append(subplot.subplot_id)
    emit_trivia(ctx, rng.randint(38, min(48, len(TriviaMic) + len(TriviaApp))))

    mic = sorted(ctx.mic_items, key=lambda item: (minutes_of(item["ts"]), item["snippet_id"]))
    app = sorted(ctx.app_items, key=lambda item: (minutes_of(item["ts"]), item["msg_id"]))
    sensor = _build_sensor(ctx, persona)
    stream = {
        "date": f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        "timezone": "Asia/Shanghai",
        "coverage_window": "07:00-23:30",
        "mic_slices": mic,
        "app_notifications": app,
        "sensor_summary": sensor,
    }
    question = {
        "question_id": f"Q_daily_{GENERATOR_AGENT_ID}_{index:05d}",
        "persona": persona,
        "cleaned_daily_stream": stream,
    }

    # ---- 按维度合并：主线锚点为主，副线锚点作为次级要点 ----
    grouped: Dict[str, List[Anchor]] = {}
    for anchor in anchors:
        grouped.setdefault(anchor.dim, []).append(anchor)
    ref_index = _ref_text_index(question)
    dims_payload: Dict[str, Any] = {}
    for dim in ("global",) + DIMENSIONS:
        bucket = sorted(grouped.get(dim, []), key=lambda a: -a.severity)
        if not bucket:
            bucket = [_baseline_for(dim, ctx)]
        primary = bucket[0]
        payload = _anchor_payload(primary, ctx, ref_index)
        payload["secondary_points"] = [_anchor_payload(a, ctx, ref_index) for a in bucket[1:]]
        if dim == "global":
            global_payload = payload
        else:
            dims_payload[dim] = payload
    ground_truth = {
        "question_id": question["question_id"],
        "persona": persona,
        "cleaned_daily_stream": stream,
        "directional_ground_truth": {
            "global_daily_summary": global_payload,
            "dimensions": dims_payload,
        },
        "generator_meta": {
            "generator_agent": GENERATOR_AGENT_ID,
            "spine_id": spine.spine_id,
            "spine_title": spine.title,
            "subplot_ids": subplot_ids,
            "event_count": len(mic) + len(app),
            "seed": rng.getstate()[1][0],
            "generated_at_utc": utc_now(),
        },
    }
    validate_question(question, ground_truth)
    return question, ground_truth


def _baseline_for(dim: str, ctx: Ctx) -> Anchor:
    if dim == "global":
        p = ctx.p
        return _a("global",
                  f"{p['name']}度过了以{p['occupation']}日常为主的一天，无重大突发事件，生活节奏平稳",
                  ("平淡规律的一天", "无重大变故", "日常节奏平稳"),
                  ("遭遇重大变故", "人生剧烈转折", "极度危机", "喜事连连"),
                  ("trivia_sample",), (), sev=1)
    return {"dim:health": _health_routine, "dim:social": _social_routine, "dim:emotion": _emotion_routine,
            "dim:finance": _finance_routine, "dim:career": _career_routine}[dim](ctx)


def _payload_text(payload: Any) -> str:
    """把题面所有可见文本拼成一个大字符串，用于实体/红线校验。"""
    chunks: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in ("snippet_id", "msg_id", "event_id", "sensor_id"):
                    chunks.append(str(value))
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            chunks.append(node)

    walk(payload)
    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# 出题自查：宁可生成失败，也不放一道有缺陷的题进题库
# ---------------------------------------------------------------------------
class BankDefect(RuntimeError):
    """题库缺陷（出题方自查未通过）。"""


def _ref_text_index(question: Mapping[str, Any]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    stream = question["cleaned_daily_stream"]
    for item in stream["mic_slices"]:
        index[item["snippet_id"]] = f"{item['speaker']} {item['location']} {item['text']}"
    for item in stream["app_notifications"]:
        index[item["msg_id"]] = f"{item['app']} {item['sender']} {item['content']}"
    sensor = stream["sensor_summary"]
    for event in sensor["hr_events"] + sensor["imu_events"]:
        index[event["event_id"]] = json.dumps(event, ensure_ascii=False)
    index[sensor["sensor_id"]] = json.dumps(sensor, ensure_ascii=False)
    return index


def _iter_anchors(gt: Mapping[str, Any]) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    truth = gt["directional_ground_truth"]
    yield "global", truth["global_daily_summary"]
    for dim, payload in truth["dimensions"].items():
        yield dim, payload
        for secondary in payload.get("secondary_points", []):
            yield dim, secondary


def _string_values(node: Any) -> Iterable[str]:
    """遍历题面中的所有字符串取值。"""
    if isinstance(node, Mapping):
        for value in node.values():
            yield from _string_values(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _string_values(item)
    elif isinstance(node, str):
        yield node


def validate_question(question: Mapping[str, Any], gt: Mapping[str, Any]) -> None:
    """对单题做出题方自查，任何一条不过就抛 :class:`BankDefect`。"""
    qid = question["question_id"]
    dumped = json.dumps(question, ensure_ascii=False)

    def _keys(node: Any) -> Iterable[str]:
        if isinstance(node, Mapping):
            for key, value in node.items():
                yield key
                yield from _keys(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                yield from _keys(item)

    leftovers = [chunk for chunk in _string_values(question) if "{" in chunk or "}" in chunk]
    if leftovers:
        raise BankDefect(f"{qid} 题面残留未填充的占位符：{leftovers[0][:60]}")
    leaked = sorted({k for k in _keys(question) if k in FORBIDDEN_PAYLOAD_KEYS})
    if leaked:
        raise BankDefect(f"{qid} 题面泄漏答案字段：{leaked}")
    if "ground_truth" in dumped or "directional_ground_truth" in dumped:
        raise BankDefect(f"{qid} 题面中出现标答字段名")

    truth = gt["directional_ground_truth"]
    missing = [d for d in DIMENSIONS if d not in truth["dimensions"]]
    if missing:
        raise BankDefect(f"{qid} 缺少维度标答：{missing}")
    if "global_daily_summary" not in truth:
        raise BankDefect(f"{qid} 缺少全局日总结标答")

    index = _ref_text_index(question)
    payload_text = _payload_text(question)
    for dim, anchor in _iter_anchors(gt):
        if len(anchor["acceptable_synonyms"]) < MIN_SYNONYMS:
            raise BankDefect(f"{qid}/{dim} 方向同义词少于 {MIN_SYNONYMS} 个")
        if len(anchor["red_line_rejections"]) < MIN_RED_LINES:
            raise BankDefect(f"{qid}/{dim} 红线判据少于 {MIN_RED_LINES} 个")
        overlap = set(anchor["acceptable_synonyms"]) & set(anchor["red_line_rejections"])
        if overlap:
            raise BankDefect(f"{qid}/{dim} 同义词与红线冲突：{sorted(overlap)}")
        if not anchor["evidence_ref_ids"]:
            raise BankDefect(f"{qid}/{dim} 标答没有可追溯的证据碎片")
        unknown = [r for r in anchor["evidence_ref_ids"] if r not in index]
        if unknown:
            raise BankDefect(f"{qid}/{dim} 证据碎片不存在：{unknown}")
        evidence_text = "\n".join(index[r] for r in anchor["evidence_ref_ids"])
        for entity in anchor["key_entities"]:
            if entity and entity not in evidence_text:
                raise BankDefect(f"{qid}/{dim} 关键实体未逐字出现在证据中：{entity!r}")
        for red in anchor["red_line_rejections"]:
            if red and red in payload_text:
                raise BankDefect(f"{qid}/{dim} 红线词出现在题面中（标答自相矛盾）：{red!r}")

    streams = ("mic_slices", "app_notifications")
    stamps: List[int] = []
    for name in streams:
        per_stream = [minutes_of(i["ts"]) for i in question["cleaned_daily_stream"][name]]
        if per_stream != sorted(per_stream):
            raise BankDefect(f"{qid}/{name} 时间戳未按升序排列")
        stamps += per_stream
    if not stamps:
        raise BankDefect(f"{qid} 没有任何事件")
    if min(stamps) < DAY_START_MIN or max(stamps) > DAY_END_MIN:
        raise BankDefect(f"{qid} 事件时间超出 07:00~23:30 窗口")
    if len(stamps) < 40:
        raise BankDefect(f"{qid} 事件数 {len(stamps)} 低于 40，琐碎日常不足")


# ---------------------------------------------------------------------------
# 出题方自查指标（对外公开，供做题方判断题库是否公平）
# ---------------------------------------------------------------------------
def coherence_metrics(pairs: Sequence[Tuple[Mapping[str, Any], Mapping[str, Any]]]) -> Dict[str, Any]:
    anchors = 0
    no_keyword = 0
    entity_visible = 0
    keyword_visible = 0
    red_clean = 0
    evidence_ok = 0
    events = 0
    for question, gt in pairs:
        index = _ref_text_index(question)
        payload_text = _payload_text(question)
        events += len(question["cleaned_daily_stream"]["mic_slices"]) + len(
            question["cleaned_daily_stream"]["app_notifications"])
        for _dim, anchor in _iter_anchors(gt):
            anchors += 1
            evidence_text = "\n".join(index[r] for r in anchor["evidence_ref_ids"] if r in index)
            if all(e in evidence_text for e in anchor["key_entities"] if e):
                entity_visible += 1
            if not anchor["directional_keywords"]:
                no_keyword += 1
            if not anchor["directional_keywords"] or all(k in evidence_text for k in anchor["directional_keywords"]):
                keyword_visible += 1
            if not any(r in payload_text for r in anchor["red_line_rejections"] if r):
                red_clean += 1
            if anchor["evidence_ref_ids"]:
                evidence_ok += 1
    total = max(1, anchors)
    return {
        "questions": len(pairs),
        "anchors": anchors,
        "mean_events_per_question": round(events / max(1, len(pairs)), 1),
        "mean_anchors_per_question": round(anchors / max(1, len(pairs)), 2),
        "key_entity_visible_in_evidence_ratio": round(entity_visible / total, 4),
        "directional_keyword_visible_in_evidence_ratio": round(keyword_visible / total, 4),
        "red_line_absent_from_payload_ratio": round(red_clean / total, 4),
        "anchor_has_traceable_evidence_ratio": round(evidence_ok / total, 4),
        "anchor_without_visible_keyword_ratio": round(no_keyword / total, 4),
        "note": ("出题方自查：关键实体与方向词必须能在被引用的证据碎片中找到，红线词必须不出现在题面中。"
                 "注意 acceptable_synonyms 是方向性同义词，按设计**不要求**逐字出现在题面（严禁死板字句匹配）。"),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def generate(count: int, seed: int) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
    for index in range(1, count + 1):
        rng = random.Random(seed * 1_000_003 + index)
        yield build_question(rng, index)


def _write_gz(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 全天生活流出卷官（战队 01a0aa2e）")
    parser.add_argument("--count", type=int, default=10000, help="出多少道题（默认 1 万个人的一天）")
    parser.add_argument("--seed", type=int, default=20260916, help="随机种子（同种子可完全复现）")
    parser.add_argument("--out-dir", default="benchmarks/daily_life_summarization", help="产物根目录")
    parser.add_argument("--sample", type=int, default=0, help="仅用于自查的抽样条数（0 = 全量参与自查）")
    parser.add_argument("--dry-run", action="store_true", help="只生成不落盘（用于单测/自检）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    out_dir = Path(args.out_dir).resolve()
    questions_path = out_dir / "questions" / f"questions_{GENERATOR_AGENT_ID}.jsonl.gz"
    gt_path = out_dir / "ground_truth" / f"gt_{GENERATOR_AGENT_ID}.jsonl.gz"
    metrics_path = out_dir / "reports" / f"coherence_{GENERATOR_AGENT_ID}.json"

    pairs = list(generate(args.count, args.seed))
    sample = pairs if not args.sample else pairs[:args.sample]
    metrics = coherence_metrics(sample)
    spine_counter: Dict[str, int] = {}
    for _question, gt in pairs:
        spine_counter[gt["generator_meta"]["spine_id"]] = spine_counter.get(gt["generator_meta"]["spine_id"], 0) + 1
    metrics["spine_distribution"] = dict(sorted(spine_counter.items(), key=lambda kv: -kv[1]))
    metrics["count"] = args.count
    metrics["seed"] = args.seed
    metrics["generated_at_utc"] = utc_now()

    if not args.dry_run:
        _write_gz(questions_path, (q for q, _ in pairs))
        _write_gz(gt_path, (g for _, g in pairs))
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"questions": args.count, "answers_file": str(questions_path),
                          "ground_truth_file": str(gt_path), "metrics_file": str(metrics_path)}, ensure_ascii=False))
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
