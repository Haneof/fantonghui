"""AIOS 3.0 全人生谱系高熵出卷官 —— 战队 ``01a0aa2c-fantonghui`` 的确定性题库发生器。

法定身份与使命（Master Dispatch #11 · 角色一 · 七维随机因子拓扑组合引擎）：

    为全网云端大模型战队生成 10,000 道**高熵、全谱系、极度随机且包含真假对抗**的
    全天生活流清洗大考试卷，并给出**方向性语义标答**（近义词簇 + 绝对偏离红线）。

七维因子（每题必由以下七维笛卡尔积交织衍生，严禁换名刷题）：

    1. 佩戴者身份与人生阶段（15 类 Demographic Persona，D01~D15）
    2. 五大认知域极限事件谱系（生理健康 / 财产债务 / 亲情人际 / 事业法律 / 生活契约）
    3. 外部物理传感器高熵波形（S01~S06：真跌倒、恶性心律、停搏、气压骤降、运动基线、伪冲击）
    4. 声学真实环境拓扑与极端噪声源（A01~A07：地铁、市场、车间、急诊台、长途车、婚宴、暴风雨）
    5. 语言修辞、方言黑话与人际伪装（六大方言 + 吹牛/反讽/病危嘴硬/暗语/自毁隐喻）
    6. 声纹聚类与混杂说话人拓扑（3~24 个声纹碎片，一次性杂散人声必须剪枝）
    7. 真假对抗与事实反转陷阱（T01 假借条对冲 / T02 先承认后反悔 / T03 撤回销毁证据 / T04 假摔诈伤）

出卷纪律（本模块的硬约束，全部在生成时自动校验）：

    * **公平可解**：每条标答事实的 ``anchor_entities`` 必须能逐字溯源到题面证据片段
      （``佩戴者`` 除外——由设备侧身份确定）；``directional_keywords`` 至少 2 个逐字出现在证据片段里；
    * **零标签泄漏**：题面数据流里绝不出现 ``is_junk`` / ``junk_tag`` / ``severity`` / ``category``
      之类"分类器答案"字段，垃圾与事实只由标答文件区分；
    * **垃圾纯净**：任何标答垃圾片段都不得包含标答事实的锚点实体，避免"剪枝即丢证据"的伪冲突；
    * **零空占位符**：每道题的五个数据流必须真实生成，绝不留 ``TODO`` / ``""`` 占位；
    * **抗模板化**：同一（事件模板 × 佩戴者）组合占比受限，全部标答事实描述两两不同；
    * **交付分离**：questions 文件只含观测数据（无标答），标答单独落 ``gt_*.jsonl``（防抄答）。

用法::

    PYTHONPATH=src python3 scripts/generate_cleaning_arena_bank_01a0aa2c.py --count 10000
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Iterator, List, Mapping, Sequence, Tuple

# ---------------------------------------------------------------------------
# 零、常量
# ---------------------------------------------------------------------------

GENERATOR_AGENT = "01a0aa2c-fantonghui"
GENERATOR_BRANCH = "arena/01a0aa2c-fantonghui"
DEFAULT_SEED = 20260916

DIM_HEALTH = "dim:health"
DIM_FINANCE = "dim:finance"
DIM_SOCIAL = "dim:social"
DIM_CAREER = "dim:career"
DIM_LIFE = "dim:life"
DIM_EMOTION = "dim:emotion"

DOMAINS: Tuple[str, ...] = ("health", "finance", "social", "career", "life")
DOMAIN_DIMENSION: Mapping[str, str] = {
    "health": DIM_HEALTH,
    "finance": DIM_FINANCE,
    "social": DIM_SOCIAL,
    "career": DIM_CAREER,
    "life": DIM_LIFE,
}

CH_MIC = "mic"
CH_APP = "app"
CH_UT = "utterance"
CH_SENSOR = "sensor"
CH_VOICEPRINT = "voiceprint"

#: 题面绝不允许出现的"分类器答案"字段（防泄漏铁律）。
FORBIDDEN_QUESTION_KEYS: Tuple[str, ...] = (
    "is_junk", "junk_tag", "junk", "label", "category", "severity", "priority",
    "is_background_chatter", "is_critical", "is_real", "ground_truth", "tone",
)

#: 安全旁路相关的极端波形（真跌倒 / 恶性心律失常 / 停搏 / 血氧骤降）。
P0_WAVEFORMS: Tuple[str, ...] = ("S01", "S03", "S04")

WEARER = "佩戴者"

# ---------------------------------------------------------------------------
# 一、地理与人名语料池（决定方言、机构名、地标与生活质感）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Region:
    key: str
    city: str
    dialect: str
    districts: Tuple[str, ...]
    landmarks: Tuple[str, ...]
    orgs: Tuple[str, ...]
    market: Tuple[str, ...]
    surnames: Tuple[str, ...] = ()


REGIONS: Tuple[Region, ...] = (
    Region(
        "gz", "广州", "粤语",
        ("天河区", "越秀区", "海珠区", "白云区", "番禺区"),
        ("棠下城中村", "珠江新城", "体育西路", "员村地铁口", "车陂路口", "猎德大桥", "天河客运站"),
        ("中山三院", "广东省人民医院", "广州市中院", "天河区劳动仲裁委", "广发银行广州分行", "越秀区住建局"),
        ("华辉拉肠", "山泉公馆", "炳胜品味", "沙县小吃", "潮汕牛肉火锅"),
        ("陈", "梁", "黄", "何", "吴", "李", "周", "林", "罗", "苏"),
    ),
    Region(
        "cd", "成都", "四川话",
        ("武侯区", "锦江区", "成华区", "高新区", "青羊区"),
        ("宽窄巷子", "春熙路", "火车南站", "府南河边", "玉林路口", "华西坝地铁口"),
        ("华西医院", "四川省人民医院", "成都中院", "高新区劳动仲裁委", "建行成都分行", "武侯区房管局"),
        ("甘记肥肠粉", "明婷饭店", "小龙坎火锅", "老妈蹄花", "钟水饺"),
        ("王", "李", "张", "刘", "陈", "杨", "何", "罗", "唐", "蒋"),
    ),
    Region(
        "sy", "沈阳", "东北话",
        ("和平区", "铁西区", "沈河区", "大东区", "浑南区"),
        ("铁西广场", "中街路口", "沈阳北站", "太原街地铁口", "五爱市场", "浑河桥"),
        ("中国医大一院", "盛京医院", "沈阳市中院", "铁西区劳动仲裁委", "盛京银行", "沈阳海关"),
        ("老边饺子", "李连贵熏肉大饼", "满宝馄饨", "西塔冷面", "铁西烧烤"),
        ("赵", "孙", "周", "吴", "郑", "王", "冯", "陈", "褚", "卫"),
    ),
    Region(
        "xa", "西安", "陕西方言",
        ("雁塔区", "碑林区", "未央区", "莲湖区", "长安区"),
        ("小寨十字", "回民街", "钟楼地下通道", "大雁塔北广场", "纺织城", "曲江路口"),
        ("西京医院", "交大一附院", "西安市中院", "雁塔区劳动仲裁委", "长安银行", "西安市住建局"),
        ("老碗面", "秦豫肉夹馍", "魏家凉皮", "贾三灌汤包", "粉巷葫芦头"),
        ("马", "刘", "张", "李", "杨", "高", "白", "惠", "党", "蒙"),
    ),
    Region(
        "sh", "上海", "上海话",
        ("浦东新区", "静安区", "徐汇区", "普陀区", "闵行区"),
        ("陆家嘴环路", "南京西路", "五角场", "漕河泾开发区", "中山公园地铁口", "张江高科"),
        ("瑞金医院", "华山医院", "上海市一中院", "浦东新区劳动仲裁委", "浦发银行", "静安区房管局"),
        ("小杨生煎", "老盛昌", "阿娘黄鱼面", "麦当劳", "沈大成"),
        ("沈", "顾", "陆", "金", "钱", "徐", "朱", "倪", "施", "严"),
    ),
    Region(
        "bj", "北京", "普通话",
        ("朝阳区", "海淀区", "丰台区", "西城区", "通州区"),
        ("中关村地铁口", "国贸桥", "望京SOHO", "五道口", "宋家庄", "双井路口"),
        ("协和医院", "北医三院", "北京市三中院", "朝阳区劳动仲裁委", "北京银行", "海淀区住建局"),
        ("庆丰包子铺", "紫光园", "南城香", "西少爷", "眉州东坡"),
        ("李", "张", "王", "刘", "杨", "赵", "陈", "郭", "贾", "郝"),
    ),
    Region(
        "wh", "武汉", "普通话",
        ("武昌区", "洪山区", "江汉区", "硚口区", "汉阳区"),
        ("光谷广场", "户部巷路口", "钟家村", "街道口地铁口", "汉口火车站", "长江大桥"),
        ("同济医院", "中南医院", "武汉市中院", "洪山区劳动仲裁委", "汉口银行", "武汉市税务局"),
        ("热干面大王", "靓靓蒸虾", "蔡林记", "周黑鸭", "排骨藕汤馆"),
        ("何", "徐", "程", "彭", "余", "梅", "鲁", "钟", "闵", "夏"),
    ),
    Region(
        "cq", "重庆", "四川话",
        ("渝中区", "江北区", "南岸区", "沙坪坝区", "九龙坡区"),
        ("解放碑地铁口", "观音桥", "磁器口", "谢家湾", "红旗河沟", "南坪路口"),
        ("重医附一院", "大坪医院", "重庆市五中院", "渝中区劳动仲裁委", "重庆银行", "江北区住建局"),
        ("花市豌杂面", "山城羊肉馆", "周师兄火锅", "胡记蹄花", "陈麻花"),
        ("罗", "谭", "邓", "蒋", "唐", "曾", "毛", "雷", "冉", "牟"),
    ),
    Region(
        "hz", "杭州", "普通话",
        ("西湖区", "拱墅区", "滨江区", "余杭区", "上城区"),
        ("龙井路口", "钱江新城", "武林门地铁口", "未来科技城", "湖滨银泰", "滨江网易园区"),
        ("浙大一院", "邵逸夫医院", "杭州市中院", "滨江区劳动仲裁委", "杭州银行", "余杭区住建局"),
        ("外婆家", "楼外楼", "新白鹿", "弄堂里", "知味观"),
        ("陈", "叶", "范", "傅", "方", "俞", "潘", "章", "洪", "翁"),
    ),
    Region(
        "zz", "郑州", "普通话",
        ("金水区", "二七区", "中原区", "郑东新区", "管城区"),
        ("二七广场", "郑东新区CBD", "郑州东站", "紫荆山地铁口", "德化步行街", "北环路口"),
        ("郑大一附院", "河南省人民医院", "郑州市中院", "金水区劳动仲裁委", "中原银行", "郑州市房管局"),
        ("方中山胡辣汤", "合记烩面", "萧记三鲜烩面", "蔡记蒸饺", "德化街烧饼"),
        ("郭", "常", "孟", "尚", "樊", "段", "雷", "石", "樊", "乔"),
    ),
)

GIVEN_NAMES: Tuple[str, ...] = (
    "建国", "秀兰", "志强", "桂英", "海燕", "文博", "雅静", "俊杰", "晓梅", "国栋",
    "丽娟", "永强", "凤霞", "振华", "淑芬", "立勇", "小燕", "金华", "雪莲", "广志",
    "春梅", "伟东", "红梅", "建军", "玉兰", "守义", "秀英", "大山", "雅琴", "天乐",
    "梦琪", "浩然", "子涵", "雨欣", "梓涵", "嘉怡", "思远", "若曦", "皓轩", "欣怡",
)
NICK_PREFIX: Tuple[str, ...] = ("老", "小", "大", "阿")

ROLE_CONTACTS: Tuple[str, ...] = (
    "父亲", "母亲", "妻子", "丈夫", "儿子", "女儿", "哥哥", "姐姐", "弟弟", "妹妹",
    "岳父", "婆婆", "二姨", "表哥", "小舅子", "舅舅", "姑姑", "堂哥", "外甥", "孙女",
)
WORK_CONTACTS: Tuple[str, ...] = (
    "主管", "车间主任", "项目经理", "工头", "组长", "班长", "店长", "站长", "分管副经理",
    "调度员", "会计", "出纳", "司机班长", "教研组长", "科主任", "护士长", "车间安全员",
)
STRANGER_ROLES: Tuple[str, ...] = (
    "地铁乘客", "商场导购", "外卖骑手", "小区遛狗邻居", "发传单促销员", "共享单车调度员",
    "菜场摊主", "快递派件员", "路边摊主", "出租车司机", "排队路人", "公交安全员",
    "直播带货主播", "社区广场舞领队", "售楼处业务员", "保健品推销员", "茶楼服务员",
)

# ---------------------------------------------------------------------------
# 二、佩戴者身份与人生阶段（维度 1：15 类 Demographic Persona）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Persona:
    pid: str
    label: str
    age: int
    job: str
    regions: Tuple[str, ...]
    concerns: Tuple[str, ...]
    contacts: Tuple[str, ...]
    habits: Tuple[str, ...]

    @property
    def tag(self) -> str:
        return f"{self.pid}_{self.label}_{self.age}岁"


PERSONAS: Tuple[Persona, ...] = (
    Persona("D01", "高三复读生", 17, "复读学校住校生", ("zz", "xa", "cd"),
            ("重度失眠", "焦虑躯体化", "父母高压陪读", "文具借还"),
            ("母亲", "父亲", "班主任", "同宿舍同学"), ("凌晨刷题", "课间趴桌", "夜跑释放")),
    Persona("D02", "大厂外包运维", 24, "互联网公司外包运维", ("bj", "hz", "sh"),
            ("连续通宵排查故障", "被主管甩锅", "隔断间漏水", "合租纠纷"),
            ("主管", "合租室友", "女朋友", "项目经理"), ("凌晨值班", "地铁通勤", "外卖夜宵")),
    Persona("D03", "孕晚期准妈妈", 28, "国企行政", ("sh", "hz", "gz"),
            ("妊娠期高血糖", "胎动记录", "婆媳关于月嫂争执", "产检危机"),
            ("婆婆", "丈夫", "产科医生", "月嫂"), ("数胎动", "清淡控糖餐", "孕妇瑜伽")),
    Persona("D04", "长途重卡司机", 32, "冷链长途货运", ("zz", "cq", "xa"),
            ("疲劳驾驶", "高原反应", "路怒别车", "油卡盗刷", "高速堵车"),
            ("调度员", "妻子", "跟车副驾", "卡友"), ("服务区泡面", "收费站排队", "车上过夜")),
    Persona("D05", "失业离异二房东", 36, "短租转租个体", ("gz", "wh", "cq"),
            ("被原房东起诉", "租客拖欠房租", "孩子抚养费催缴", "胃溃疡急性出血"),
            ("前妻", "儿子", "租客", "律师"), ("盯群收租", "跑不动产登记", "夜里清点空房")),
    Persona("D06", "急诊科住院总医师", 42, "三甲医院急诊科", ("gz", "wh", "bj"),
            ("连轴转24小时", "医疗纠纷推搡", "高暴露感染风险", "家属下跪托付"),
            ("护士长", "科主任", "患者家属", "120调度员"), ("查房", "写病历", "手术室连台")),
    Persona("D07", "钢筋班包工头", 48, "建筑工地钢筋班", ("cq", "zz", "cd"),
            ("工人高空坠落险情", "农民工讨薪围堵", "发包方阴阳合同", "痛风急性发作"),
            ("工头老张", "发包方经理", "工人代表", "老婆"), ("工地盯进度", "结算对账", "喝白酒谈事")),
    Persona("D08", "民企财务总监", 53, "制造业民企", ("sh", "hz", "sy"),
            ("大额假发票对账", "税务稽查突击", "失眠盗汗", "女儿出嫁礼金纠纷"),
            ("老板", "税务稽查员", "女儿", "出纳"), ("对账到深夜", "养生茶", "晨练太极")),
    Persona("D09", "退休教师", 65, "初老退休中学教师", ("bj", "xa", "hz"),
            ("轻度脑萎缩前兆", "候鸟式养老买房被套", "保健品传销洗脑", "老伴白内障手术"),
            ("老伴", "儿子", "老同学", "保健品推销员"), ("晨练", "写书法", "社区合唱团")),
    Persona("D10", "独居空巢老人", 78, "独居退休工人", ("sy", "zz", "wh"),
            ("骨质疏松髋关节脆弱", "阿尔茨海默走失风险", "煤气忘关", "邻里漏水争执"),
            ("女儿", "邻居", "社区网格员", "上门医生"), ("楼下遛弯", "听收音机", "手写记账")),
    Persona("D11", "户外越野攀岩者", 30, "户外俱乐部教练", ("cd", "cq", "xa"),
            ("失足滑坠悬挂", "失温脱水", "卫星电话盲区", "骨折自救"),
            ("搭档", "俱乐部领队", "救援队", "妻子"), ("凌晨出发", "攀岩训练", "露营过夜")),
    Persona("D12", "乡村外卖骑手", 22, "平台众包骑手", ("cd", "cq", "wh"),
            ("暴雨超时罚款", "电瓶车被盗", "出餐口角", "膝盖滑囊炎"),
            ("站点站长", "商家老板", "同城骑手", "母亲"), ("抢单", "午晚高峰", "夜里洗车")),
    Persona("D13", "连锁餐饮店主", 45, "中式快餐连锁", ("gz", "cd", "wh"),
            ("食品安全抽检", "厨师集体罢工", "供应商催款", "油烟烫伤"),
            ("店长", "厨师长", "供应商", "房东"), ("凌晨进货", "巡店", "算日流水")),
    Persona("D14", "远洋轮机长", 38, "远洋货轮轮机部", ("sh", "gz", "sy"),
            ("连续航行40天", "卫星断网", "船舱高分贝噪声耳鸣", "幽闭恐惧"),
            ("大副", "妻子", "机工", "船舶代理"), ("值夜班", "机舱巡检", "甲板透气")),
    Persona("D15", "独立插画师", 26, "自由职业插画", ("hz", "sh", "bj"),
            ("颈椎压迫手麻", "甲方无底线改图毁约", "版权侵权维权", "猫咪重症"),
            ("甲方", "母亲", "版权代理", "兽医"), ("熬夜赶稿", "咖啡续命", "逛展采风")),
)

# ---------------------------------------------------------------------------
# 三、垃圾噪声语料池（维度 4：声学环境；铁律四的第一剪枝对象）
# ---------------------------------------------------------------------------

#: 声学拓扑（A01~A07）：每种环境给出真实噪声底噪区间与典型垃圾切片。
ACOUSTIC_TOPOLOGIES: Mapping[str, Mapping[str, Any]] = {
    "A01": {
        "label": "早晚高峰地铁换乘通道",
        "db": (80.0, 86.5),
        "lines": (
            "乘客请注意，本次列车开往{stop}方向，请先下后上",
            "换乘{line}号线的乘客请从右侧通道通行，注意脚下安全",
            "车门即将关闭，请勿抢上抢下",
            "扫码乘车优惠活动，新用户首单立减两元",
            "站台内请勿倚靠屏蔽门，谢谢配合",
            "列车因故晚点，预计等待三分钟，敬请谅解",
            "小推车卖水卖纸巾了啊，两块钱一瓶，矿泉水三块",
            "请注意保管好随身物品，谨防扒窃",
        ),
    },
    "A02": {
        "label": "露天农贸海鲜市场",
        "db": (74.0, 82.0),
        "lines": (
            "新鲜排骨今天特价二十八一斤，先到先得啊",
            "老板这个能不能再便宜两块，我天天在你这买",
            "本地小白菜三块五一斤，刚摘的还带露水",
            "让一让让一让，推车的过一下",
            "收摊处理了，这几把菠菜两块全拿走",
            "称重称重，扫码还是现金，微信支付宝都行",
            "鲈鱼活的，三十九一斤，要哪条自己挑",
        ),
    },
    "A03": {
        "label": "冲压车间与机加工厂房",
        "db": (86.0, 92.0),
        "lines": (
            "三号冲床气阀排气异常，等会儿停机点检",
            "老王那边的料筐满了，叉车过来拉一趟",
            "图纸改过一版，孔距按新的来做，别搞错了",
            "切削液没多少了，领料单打好没有",
            "安全帽戴好，行车下面不要站人",
            "这批件毛刺有点大，去毛刺多加一道工序",
        ),
    },
    "A04": {
        "label": "三甲医院急诊分诊台",
        "db": (62.0, 70.0),
        "lines": (
            "请{code}号患者到三诊室就诊",
            "护士护士，我妈这个片子要去哪里取啊",
            "陪护家属请到外面等，里面留一个家属就行",
            "抢救车推过来了，前面让一下路",
            "输液室在左手边，先交费再过去排号",
            "救护车马上到，急诊门口清一下车",
        ),
    },
    "A05": {
        "label": "深夜长途大巴车厢",
        "db": (46.0, 55.0),
        "lines": (
            "下一站服务区休息二十分钟，上厕所的抓紧时间",
            "手机声音小一点，人家都睡了",
            "安全带系好，前面拐弯了",
            "师傅还有多久到县城啊",
            "晕车的往前面坐，后面太颠了",
        ),
    },
    "A06": {
        "label": "婚庆宴席大厅",
        "db": (76.0, 84.0),
        "lines": (
            "来，新郎新娘给各位长辈敬酒，大家干杯",
            "司仪你声音小点，话筒啸叫了",
            "快，孩子别跑，菜汤洒身上了",
            "这桌再来两瓶啤酒，冰的",
            "红包放到签到处，别直接塞手上",
            "合影了合影了，两家人都过来站好",
        ),
    },
    "A07": {
        "label": "暴风雨夜户外露营地",
        "db": (68.0, 78.0),
        "lines": (
            "风绳再拉紧一点，帐篷要被掀翻了",
            "雨太大了，把地钉重新打一遍",
            "远处闷雷一阵接一阵，估计要下整晚",
            "手电还有电吗，先把引火的东西收进来",
            "睡袋都湿了，今晚没法睡了",
        ),
    },
}

#: 微型垃圾池（验证码/系统通知，单条体积小但必须物理剪枝 —— 铁律四点名对象）。
MICRO_JUNK_POOL: Tuple[str, ...] = (
    "【{brand}】验证码{code6}，请勿泄露",
    "【{brand}】尾号{n4}登录动态码{code6}",
    "【{brand}】支付验证码{code6}（5分钟内有效）",
    "【快递】包裹已放{landmark}驿站，取件码{code6}",
    "【{app}】今日步数{steps}，已同步",
    "【{app}】天气提醒：{city}今日{weather}",
    "【{app}】您有1条服务通知待查看",
    "【{shop}】会员日积分即将清零，请及时使用",
)

#: 通用营销/系统噪声池（APP 与短信流）。
APP_JUNK_POOLS: Mapping[str, Tuple[str, ...]] = {
    "promo": (
        "【{shop}】限时充100送30，到店核销，今天最后一天",
        "【{brand}旗舰店】大牌闪购今日直降200，点击进入会场",
        "【{brand}客服】亲爱的会员，您有1张满199减50优惠券即将过期",
        "【{shop}】新客首单立减15元，轻食套餐9.9元起",
        "【{brand}直播】今晚八点清仓直播，前100名下单加赠礼品",
    ),
    "bargain": (
        "【帮我砍一刀】我只差0.01元就能提现100元现金，帮我点一下谢谢",
        "【助力提现】还差2个人头，点一下就能白拿40元，老铁帮帮忙",
        "【拼团邀请】{n3}邀请你参与9.9元拼单，仅剩2个名额",
        "【摇一摇红包】还差一次机会，帮我助力一把",
    ),
    "verify": (
        "【{brand}】验证码{code6}，5分钟内有效，请勿泄露给任何人",
        "【{brand}】您的登录验证码是{code6}，本次为设备登录",
        "【{brand}】短信验证码{code6}（用于账户安全校验）",
        "【{brand}】您正在修改支付密码，验证码{code6}，非本人操作请忽略",
    ),
    "spam_group": (
        "【{group}群】{n3}: 早上好，今天也是元气满满的一天[太阳]",
        "【{group}群】{n4}: 谁有闲置的行李箱出，便宜点",
        "【{group}群】{n3}: [图片]",
        "【{group}群】{n4}: 转发一条：据说转发这个到三个群能转运",
        "【{group}群】{n3}: 有没有人知道附近哪里能修电风扇",
        "【{group}群】{n4}: 打卡打卡，今天第38天",
    ),
    "system": (
        "【{app}】您的步数已达标，去领取今日活力勋章",
        "【{app}】本周运动报告已生成：日均{steps}步，比上周提升8%",
        "【{app}】外卖订单已送达，请给骑手一个五星好评",
        "【{app}】您关注的{shop}上新了，第二件半价",
        "【{app}】快递已到{landmark}菜鸟驿站，凭取件码{code6}领取",
        "【{app}】天气提醒：{city}今日{weather}，出门记得带伞",
    ),
    "news": (
        "【热点推送】本地新闻：{district}新开三条公交线路，明起试运行",
        "【赛事推送】今晚球赛直播，主队首发名单公布",
        "【理财推送】{bank}理财新品七日年化3.1%，风险等级R2",
    ),
}

#: 佩戴者原话噪声池（吹牛/口头禅/玩笑，必须剪枝 —— 同时是对抗"假报警"的考点）。
UTTERANCE_JUNK_POOLS: Mapping[str, Tuple[str, ...]] = {
    "boast": (
        "下个月我把隔壁那条街整栋楼都盘下来，给弟兄们一人分一层",
        "等我这单成了，直接提辆大奔，到时候带你兜风",
        "我在外面认识的人多着呢，一句话的事，没有办不成的",
        "这点钱算什么，我一天流水就这个数",
        "明年这时候我就是{title}了，你信不信",
    ),
    "catchphrase": (
        "烦死了，真想把手机摔了",
        "哎哟累死了，这一天天的没个头",
        "算了算了，睁一只眼闭一只眼吧",
        "这日子过得，凑合呗",
        "别催了别催了，我这就去办",
    ),
    "joke": (
        "你再这样我可从楼上跳下去了啊，逗你的",
        "我要是能中彩票，第一时间就不理你们了，开玩笑的",
        "今晚要是敢加班我就原地辞职，哈哈",
        "谁惹我我就把谁的微信删了，说到做到，开玩笑啦",
    ),
    "smalltalk": (
        "早啊，今天有点起风了，你加件衣服",
        "先吃口饭吧，凉了不好吃",
        "钥匙我放门口鞋柜上了，别忘了拿",
        "路上慢点，到了给我发个消息",
    ),
}

AMBIENT_DESCRIPTORS: Tuple[str, ...] = (
    "（持续风噪，无有效人声，{db:.0f}dB）",
    "（远处机器低频轰鸣，语音不可辨识，{db:.0f}dB）",
    "（雨点密集敲击外壁与风绳拉扯声，{db:.0f}dB）",
    "（餐具碰撞与油烟机嗡鸣，无人声语义，{db:.0f}dB）",
    "（电梯运行与楼道回响，语音模糊不可用，{db:.0f}dB）",
    "（广场舞音响外放与人群嘈杂，无法分辨说话人，{db:.0f}dB）",
    "（车流胎噪与鸣笛混合，持续性低频噪声，{db:.0f}dB）",
)

# ---------------------------------------------------------------------------
# 四、语言修辞、方言黑话（维度 5）
# ---------------------------------------------------------------------------

#: 方言颗粒：包裹在标准汉语核心句之外的语气词，**绝不改写核心句**（保证锚点/关键词可溯源）。
DIALECT_FLAVOR: Mapping[str, Mapping[str, Tuple[str, ...]]] = {
    "四川话": {
        "head": ("硬是背时，", "我跟你说嘛，", "你要晓得哈，", "莫得法子，"),
        "tail": ("，晓得不", "，巴适得板", "，莫得问题", "，硬是恼火得很"),
    },
    "东北话": {
        "head": ("我跟你说啊，", "你听我讲，", "别整那些虚的，", "这事儿老鼻子了，"),
        "tail": ("，妥妥的", "，整明白了没", "，就这么定了", "，别跟我扯犊子"),
    },
    "粤语": {
        "head": ("我同你讲啦，", "你听住先，", "唔好意思啊，", "真系咁嘅，"),
        "tail": ("，你话係咪", "，唔该晒", "，真系冇得顶", "，记得啦"),
    },
    "陕西方言": {
        "head": ("我跟你说咧，", "你听额说，", "甭装糊涂，", "这事嘛，"),
        "tail": ("，你甭急", "，额给你说清楚", "，就这话", "，记住咧"),
    },
    "上海话": {
        "head": ("我搭侬讲，", "侬听我讲，", "勿要急呀，", "其实是搿能样子呃，"),
        "tail": ("，侬讲是伐", "，麻烦侬了", "，就搿能样子", "，记牢哦"),
    },
    "普通话": {"head": ("",), "tail": ("",)},
}

#: 修辞陷阱（维度 5 第二类）：真伪意图辨析。
RHETORIC_TRAPS: Mapping[str, str] = {
    "R01": "反讽与正话反说（表面夸赞实为控诉违约）",
    "R02": "病危假装坚强（客观体征与自述背离，必须一票否决乐观说辞）",
    "R03": "酒后狂悖吹牛（无效酒精发泄，属垃圾噪声）",
    "R04": "暗语行话隐匿（高保密或灰色交易约定）",
    "R05": "自毁隐喻（攒药/告别式措辞，极度危重心理危机）",
}

# ---------------------------------------------------------------------------
# 五、传感器高熵波形库（维度 3）
# ---------------------------------------------------------------------------

SENSOR_WAVEFORMS: Mapping[str, Mapping[str, Any]] = {
    "S01": {"label": "高G值剧烈冲击后长时间静止", "kind": "impact", "evidence": True},
    "S02": {"label": "虚假冲击对冲（磕碰/扣杀类单峰）", "kind": "spurious_impact", "evidence": False},
    "S03": {"label": "静止状态恶性心动过速伴室性早搏阵发", "kind": "arrhythmia", "evidence": True},
    "S04": {"label": "缓慢性窦性停搏与失衡下沉", "kind": "asystole", "evidence": True},
    "S05": {"label": "气压骤降与温湿度突变（暴雨将至）", "kind": "baro_drop", "evidence": True},
    "S06": {"label": "运动基线规律偏移（配速摆动）", "kind": "exercise", "evidence": False},
}

MOTION_STATES: Tuple[str, ...] = (
    "RESTING_SEATED", "WALKING_STEADY", "STAIRS_UP", "TYPING_DESK",
    "VEHICLE_RIDE", "STANDING_TALK", "HOUSEHOLD_CHORES", "SLEEP_STILL",
)

WEATHER_POOL: Tuple[str, ...] = ("多云转阴", "中到大雨", "大风降温", "晴间多云", "雷阵雨", "高温闷热")


# ---------------------------------------------------------------------------
# 六、小工具
# ---------------------------------------------------------------------------


def _hash_int(*parts: Any) -> int:
    """稳定哈希（跨进程/跨平台一致，用于确定性伪随机）。"""
    payload = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _fmt(template: str, slots: Mapping[str, Any]) -> str:
    """安全格式化：未提供的槽位原样保留，绝不抛 KeyError。"""
    class _Safe(dict):
        def __missing__(self, key: str) -> str:  # pragma: no cover - 兜底
            return "{" + key + "}"

    return template.format_map(_Safe(slots))


#: 全天生活流时间窗（06:30 起床 ~ 23:40 入睡前，1030 分钟）。
DAY_START_MIN = 6 * 60 + 30
DAY_SPAN_MIN = 1030
DAY_WINDOW = "06:30~23:40"


def _clock(c: "GenCtx", lo: int | None = None, hi: int | None = None) -> str:
    """生成当天时间戳（HH:MM，本地时区）：落在该佩戴者当天的清醒时段内。

    每道题自带"起床/入睡"边界（``GenCtx.day_lo`` / ``day_hi``），因此全天生活流
    必然横跨清晨到深夜（≥15 小时），而非随机落在半天的窄窗口里。
    """
    start = c.day_lo if lo is None else DAY_START_MIN + lo
    end = c.day_hi if hi is None else DAY_START_MIN + hi
    total = c.rng.randrange(start, end)
    return f"{total // 60:02d}:{total % 60:02d}"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rand_ts(rng: random.Random) -> datetime:
    """随机某日 06:40~23:40 之间的一个时刻（佩戴者的清醒时段）。"""
    base = datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(days=rng.randrange(0, 110))
    minutes = rng.randrange(6 * 60 + 40, 23 * 60 + 40)
    return base.replace(hour=0, minute=0) + timedelta(minutes=minutes)


# ---------------------------------------------------------------------------
# 七、生成上下文与证据片段模型
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GenCtx:
    """单题生成上下文（伪随机 + 地域 + 佩戴者 + 已抽取人名池）。"""

    rng: random.Random
    region: Region
    persona: Persona
    names: List[str] = field(default_factory=list)
    t: datetime = field(default_factory=lambda: datetime(2026, 6, 1, tzinfo=timezone.utc))
    used: set[str] = field(default_factory=set)
    day_lo: int = DAY_START_MIN                    # 当天起床时刻（分钟）
    day_hi: int = DAY_START_MIN + DAY_SPAN_MIN     # 当天入睡时刻（分钟）

    # -- 抽样工具 ---------------------------------------------------------
    def pick(self, seq: Sequence[Any]) -> Any:
        return self.rng.choice(tuple(seq))

    def name(self, index: int = 0) -> str:
        """取一个人名（首次调用时批量生成，保证同题内人名天然不同）。"""
        if not self.names:
            pool: List[str] = []
            for _ in range(6):
                pool.append(self._fresh_name())
            self.names.extend(pool)
        return self.names[index % len(self.names)]

    def _fresh_name(self) -> str:
        for _ in range(50):
            if self.rng.random() < 0.42:
                cand = self.pick(NICK_PREFIX) + self.pick("刘王李张陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤")
            else:
                cand = self.pick(self.region.surnames) + self.pick(GIVEN_NAMES)
            if cand not in self.used:
                self.used.add(cand)
                return cand
        return self.pick("刘王李张陈杨黄赵吴周徐孙马朱胡郭何高林罗郑") + self.pick(GIVEN_NAMES)

    def nick(self, index: int = 0) -> str:
        return self.name(index)

    # -- 金额 / 数量 ------------------------------------------------------
    def money_amount(self, lo: float = 1.5, hi: float = 30.0) -> float:
        """随机金额（万元），保留一位小数。"""
        return round(self.rng.uniform(lo, hi), 1)

    @staticmethod
    def fmt_money(value: float) -> str:
        return f"{value:.1f}万元"

    def money(self, scale: str = "mid") -> str:
        if scale == "small":
            return f"{self.rng.randrange(3, 90) * 100}元"
        if scale == "mid":
            return f"{self.rng.randrange(10, 96) / 10:.1f}万元"
        return f"{self.rng.randrange(60, 460)}万元"

    def place(self) -> str:
        return self.pick(self.region.landmarks)

    def org(self) -> str:
        return self.pick(self.region.orgs)

    def shop(self) -> str:
        return self.pick(self.region.market)

    def flavor(self, text: str) -> str:
        """给核心句包一层方言语气（核心句逐字不改，保证锚点/关键词可溯源）。

        若正文以"人名/角色："开头，则只给冒号后的内容加方言颗粒，绝不污染说话人标签。
        """
        fl = DIALECT_FLAVOR.get(self.region.dialect, DIALECT_FLAVOR["普通话"])
        head = self.pick(fl["head"])
        tail = self.pick(fl["tail"])
        if not text:
            return text
        label = ""
        body = text
        m = re.match(r"^([^：:\s]{1,10}[：:])(.*)$", text)
        if m:
            label, body = m.group(1), m.group(2)
        return f"{label}{head}{body}{tail}" if body else text


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    """一条核心事实：证据片段正文 + 方向性标答字段。"""

    channel: str
    text: str
    intent: str
    dimension: str
    keywords: Tuple[str, ...]
    anchors: Tuple[str, ...]
    core: str
    source: str = "template"


#: 模板变体返回值：(channel, 正文, 候选锚点)
VariantResult = Tuple[str, str, Tuple[str, ...]]


def _mk_template(
    key: str,
    domain: str,
    intent: str,
    keywords: Tuple[str, ...],
    channels: Tuple[str, ...],
    variants: Tuple[Any, ...],
) -> Dict[str, Any]:
    return {
        "key": key,
        "domain": domain,
        "intent": intent,
        "keywords": keywords,
        "channels": channels,
        "variants": variants,
    }


def _v_ws(ctx: GenCtx) -> VariantResult:
    who = ctx.nick(0)
    who, sec = who, ctx.nick(1)
    return (CH_MIC, f"{who}：身体第一位，体检报告出来了吗；{sec}：结果拿到了，回头再说", (who, sec))


# ===========================================================================
# 八、事件模板库（维度 2：五大认知域极限事件谱系；每个模板 3~4 个真实变体）
# ===========================================================================

EVENT_TEMPLATES: Tuple[Mapping[str, Any], ...] = (
    # ---------------- 生理健康域 ----------------
    _mk_template(
        "GOUT_ACUTE_ATTACK", "health", "GOUT_ACUTE_ATTACK",
        ("痛风", "痛风急性发作", "火烧样疼痛", "关节红肿", "无法着地", "疼得站不住"),
        (CH_UT, CH_MIC),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"嘶……脚趾头红肿得跟馒头一样，火烧样疼痛，我一落地就疼得站不住，得找盒{c.pick(('双氯芬酸钠缓释胶囊', '秋水仙碱片', '非布司他片'))}撑着"),
                ("脚趾头红肿", "火烧样疼痛", "疼得站不住"),
            ),
            lambda c: (
                CH_UT,
                f"{c.nick(0)}：哥你走路怎么一瘸一拐；我：痛风又来了，{c.pick(('大脚趾', '脚踝'))}关节红肿，火烧样疼痛，连鞋都穿不上",
                ("痛风", "关节红肿", "火烧样疼痛"),
            ),
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(1)}：你那脚怎么了；{c.nick(0)}：痛风急性发作，红肿的这块碰一下都火烧样疼痛，今天没法上楼收料了"),
                ("痛风急性发作", "火烧样疼痛", "红肿"),
            ),
        ),
    ),
    _mk_template(
        "CARDIAC_VENTRICULAR_BURST", "health", "CARDIAC_VENTRICULAR_BURST",
        ("室性早搏", "早搏阵发", "恶性心律失常", "心动过速", "心律不齐", "心电异常"),
        (CH_SENSOR,),
        (
            lambda c: (
                CH_SENSOR,
                f"静息状态下心率自{c.rng.randrange(52, 62)}bpm骤升至{c.rng.randrange(170, 199)}bpm，室性早搏连续阵发{c.rng.randrange(6, 18)}次，伴短阵心动过速，波形宽大畸形",
                ("室性早搏", "连续阵发", "骤升"),
            ),
            lambda c: (
                CH_SENSOR,
                f"夜间睡眠期出现室性早搏阵发，{c.rng.randrange(20, 60)}分钟内早搏{c.rng.randrange(300, 1200)}次，伴短阵心动过速，RR间期不规则",
                ("室性早搏阵发", "心动过速", "不规则"),
            ),
        ),
    ),
    _mk_template(
        "FALL_HIGH_G_IMPACT", "health", "FALL_HIGH_G_IMPACT",
        ("跌落", "冲击", "静止不动", "跌倒", "坠落", "长时间静止"),
        (CH_SENSOR,),
        (
            lambda c: (
                CH_SENSOR,
                f"检测到自约{c.pick(('1.2', '1.6', '2.1'))}米高处跌落，冲击峰值{c.rng.randrange(150, 340) / 10:.1f}g，落地后静止不动{c.rng.randrange(30, 180)}秒",
                ("跌落", "冲击峰值", "静止不动"),
            ),
            lambda c: (
                CH_SENSOR,
                f"{c.pick(('楼梯', '脚手架', '梯子'))}上坠落，连续两次冲击，第二次峰值{c.rng.randrange(180, 320) / 10:.1f}g，随后姿态保持水平静止不动{c.rng.randrange(40, 150)}秒",
                ("坠落", "冲击", "静止不动"),
            ),
        ),
    ),
    _mk_template(
        "ASYSITOLE_SYNC_FAINT", "health", "ASYSITOLE_SYNC_FAINT",
        ("窦性停搏", "心率骤降", "眼前一黑", "站不稳", "缓慢心率", "晕厥"),
        (CH_SENSOR, CH_UT),
        (
            lambda c: (
                CH_SENSOR,
                f"心电记录窦性停搏{c.rng.randrange(32, 58) / 10:.1f}秒，心率骤降至{c.rng.randrange(26, 38)}bpm，随后出现体动下沉信号",
                ("窦性停搏", "心率骤降", "体动下沉"),
            ),
            lambda c: (
                CH_UT,
                f"（扶墙缓了半分钟）眼前一黑差点摔倒，站不稳，缓过来一身冷汗",
                ("眼前一黑", "站不稳"),
            ),
        ),
    ),
    _mk_template(
        "MED_ALLERGY_ANAPHYLAXIS", "health", "MED_ALLERGY_ANAPHYLAXIS",
        ("过敏", "皮疹", "喘不上气", "喉头水肿", "风团", "药物过敏"),
        (CH_UT, CH_MIC),
        (
            lambda c: (
                CH_UT,
                f"输了液之后浑身起风团样皮疹，喉咙发紧喘不上气，手背都肿了，赶紧叫护士",
                ("起风团样皮疹", "喘不上气", "喉咙发紧"),
            ),
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：我吃了{c.pick(('阿莫西林', '头孢', '青霉素V钾片'))}之后身上起红疹，喘不上气，是不是药物的过敏反应"),
                ("起红疹", "喘不上气", "过敏反应"),
            ),
        ),
    ),
    _mk_template(
        "RHABDOMYOLYSIS_DARK_URINE", "health", "RHABDOMYOLYSIS_DARK_URINE",
        ("横纹肌溶解", "浓茶色尿", "肌肉酸痛", "酱油色", "尿色加深", "剧烈运动后"),
        (CH_UT, CH_MIC),
        (
            lambda c: (
                CH_UT,
                f"前天连续跑了{c.rng.randrange(15, 42)}公里，现在大腿肌肉酸痛得下不了床，尿是浓茶色，估计是横纹肌溶解",
                ("肌肉酸痛", "浓茶色", "横纹肌溶解"),
            ),
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：你那个尿颜色不对劲，像酱油色；我：连着两天高强度训练，腿疼得厉害，怕是横纹肌溶解",
                ("酱油色", "横纹肌溶解", "高强度训练"),
            ),
        ),
    ),
    _mk_template(
        "DRUG_INDUCED_HYPOGLYCEMIA", "health", "DRUG_INDUCED_HYPOGLYCEMIA",
        ("低血糖", "心慌出汗", "血糖", "手抖", "冒冷汗", "眼前发花"),
        (CH_UT, CH_APP),
        (
            lambda c: (
                CH_UT,
                f"半夜心慌出汗手抖，血糖仪测出来{2 + c.rng.randrange(0, 9) / 10:.1f}mmol/L，赶紧含了块糖",
                ("心慌出汗", "手抖", "血糖仪"),
            ),
            lambda c: (
                CH_APP,
                f"【血糖记录】{c.t.strftime('%H:%M')} 指尖血糖{2 + c.rng.randrange(0, 9) / 10:.1f}mmol/L，标注：低血糖，伴心慌出汗",
                ("低血糖", "心慌出汗", "mmol/L"),
            ),
        ),
    ),
    _mk_template(
        "STROKE_ONSET_DENIAL", "health", "STROKE_ONSET_DENIAL",
        ("中风", "脑卒中", "口角歪斜", "说话不利索", "一侧无力", "舌头发麻"),
        (CH_UT, CH_MIC),
        (
            lambda c: (
                CH_UT,
                f"我没事别大惊小怪，就是眼前有点发花，舌头发麻说话不利索，左手拿杯子有点没力气",
                ("没事", "舌头发麻", "说话不利索", "没力气"),
            ),
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：你嘴角怎么歪的；我：哪有事，就是说话不利索，一侧无力，歇会儿就好"),
                ("嘴角", "说话不利索", "一侧无力"),
            ),
        ),
    ),
    # ---------------- 财产债务与民商法域 ----------------
    _mk_template(
        "DEBT_COLLECTION_OVERDUE", "finance", "DEBT_COLLECTION_OVERDUE",
        ("欠款", "还钱", "拖了", "催款", "赖账", "本金", "逾期"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：说好上个月底的{c.money('mid')}今天还，电话也不接，这笔欠款拖了{c.rng.randrange(2, 9)}个月了，我今天就上门"),
                ("欠款", "拖了", "今天还"),
            ),
            lambda c: (
                CH_APP,
                (lambda principal, total: f"【{c.pick(('微信', '短信'))}】{c.nick(0)}：{c.fmt_money(principal)}的本金加利息一共{c.fmt_money(total)}，欠款拖了{c.rng.randrange(2, 11)}个月，还钱的日子一推再推，别怪我不讲情面")(
                    c.money_amount(2.0, 20.0), 0.0) if False else
                (lambda p: f"【{c.pick(('微信', '短信'))}】{c.nick(0)}：{c.fmt_money(p)}的本金加利息一共{c.fmt_money(round(p * c.rng.uniform(1.08, 1.45), 1))}，欠款拖了{c.rng.randrange(2, 11)}个月，还钱的日子一推再推，别怪我不讲情面")(c.money_amount(2.0, 20.0)),
                ("欠款", "拖了", "还钱"),
            ),
        ),
    ),
    _mk_template(
        "BANK_LOAN_OVERDUE_NOTICE", "finance", "BANK_LOAN_OVERDUE_NOTICE",
        ("逾期", "还款", "征信", "贷款", "扣款失败", "催收"),
        (CH_APP,),
        (
            lambda c: (
                CH_APP,
                f"【{c.org()}】尊敬的客户，您尾号{c.rng.randrange(1000, 9999)}的账户贷款本期应还{c.money('small')}已逾期{c.rng.randrange(1, 15)}天，请尽快还款以免影响征信",
                ("逾期", "还款", "征信"),
            ),
            lambda c: (
                CH_APP,
                f"【{c.pick(('招商银行', '建设银行', '邮储银行', '交通银行'))}】您的分期还款代扣失败，本期应还{c.money('small')}，请于今日内在App主动还款，逾期将上报征信",
                ("还款", "逾期", "征信"),
            ),
        ),
    ),
    _mk_template(
        "CRYPTO_PONZI_COLLAPSE", "finance", "CRYPTO_PONZI_COLLAPSE",
        ("跑路", "提现失败", "盘子", "资金盘", "崩盘", "血本无归"),
        (CH_APP, CH_MIC),
        (
            lambda c: (
                CH_APP,
                f"【{c.pick(('链上财富群', '币圈交流群', '稳赚俱乐部'))}】{c.nick(0)}：平台提现失败了，客服电话空号，群主跑路，我投的{c.money('mid')}怕是要血本无归",
                ("提现失败", "跑路", "血本无归"),
            ),
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：那个所谓年化60%的盘子今天崩盘了，{c.money('mid')}提现失败，人早跑路了"),
                ("崩盘", "提现失败", "跑路"),
            ),
        ),
    ),
    _mk_template(
        "INHERITANCE_FAMILY_DISPUTE", "finance", "INHERITANCE_FAMILY_DISPUTE",
        ("遗产", "分配", "房产", "继承", "分家", "公证"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：老爷子的房子和存款一共{c.money('big')}，遗产分配你一个人说了算？妹妹那份不能少，要去公证处说清楚"),
                ("遗产分配", "房子和存款", "公证处"),
            ),
            lambda c: (
                CH_APP,
                f"【{c.pick(('家人群', '亲属群'))}】{c.nick(1)}：父母的房产按遗嘱继承，存款{c.money('mid')}的分配必须三家坐下来谈，谁也别想独占",
                ("房产", "继承", "分配"),
            ),
        ),
    ),
    _mk_template(
        "TAX_INSPECTION_FALSE_INVOICE", "finance", "TAX_INSPECTION_FALSE_INVOICE",
        ("发票", "税务稽查", "对账", "进项", "补税", "虚开"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：税务稽查查到我们去年一批进项发票的业务合同对不上，涉及金额{c.money('big')}，要我们限期说明情况",
                ("发票", "对账", "税务稽查"),
            ),
            lambda c: (
                CH_APP,
                f"【{c.org()}】关于你单位{c.money('big')}进项发票的核实通知：请提供合同、出入库单及银行流水，否则按虚开处理",
                ("进项发票", "合同", "流水"),
            ),
        ),
    ),
    _mk_template(
        "REFUND_SCAM_COMPENSATION", "finance", "REFUND_SCAM_COMPENSATION",
        ("退款", "理赔", "手续费", "转账", "客服", "诈骗"),
        (CH_APP, CH_MIC),
        (
            lambda c: (
                CH_APP,
                f"【客服】您购买的{ctx_shop(c)}有质量问题，我们可以给您三倍理赔，请先向安全账户转入{c.money('small')}的手续费完成核验",
                ("理赔", "手续费", "安全账户"),
            ),
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：自称是平台客服，说给我理赔退款，让我先转账{c.money('small')}的手续费，这套路不对劲吧",
                ("理赔", "退款", "手续费"),
            ),
        ),
    ),
    _mk_template(
        "FUTURES_MARGIN_CALL", "finance", "FUTURES_MARGIN_CALL",
        ("保证金", "浮亏", "强平", "追加", "爆仓", "期货"),
        (CH_APP, CH_UT),
        (
            lambda c: (
                CH_APP,
                f"【期货公司】您的账户风险度已达{c.rng.randrange(96, 130)}%，浮亏{c.money('mid')}，请于今日收盘前追加保证金，否则将强行平仓",
                ("浮亏", "追加保证金", "强行平仓"),
            ),
            lambda c: (
                CH_UT,
                f"这下麻烦了，浮亏已经{c.money('mid')}，再不追加保证金就要被强平，这把是彻底看错了",
                ("浮亏", "追加保证金", "强平"),
            ),
        ),
    ),
    # ---------------- 亲情人际与情感博弈域 ----------------
    _mk_template(
        "ARGUMENT_CONFLICT", "social", "ARGUMENT_CONFLICT",
        ("吵", "吵架", "争执", "争吵", "红脸", "口角"),
        (CH_MIC, CH_UT),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：为{c.pick(('交房', '押金', '工钱', '孩子上学'))}的事你跟我吵架吵了大半天，两个人争来争去有什么用，能不能坐下好好说"),
                ("吵了", "争来争去", "好好说"),
            ),
            lambda c: (
                CH_UT,
                f"（两个人越说越激动）行了别吵了，这么点小事值得起争执吗，脸红脖子粗的给谁看",
                ("别吵", "争执", "脸红脖子粗"),
            ),
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(1)}：你什么态度；{c.nick(0)}：我什么态度？刚才在{c.place()}你当着那么多人跟我吵，这个口角我记下了"),
                ("吵", "口角", "态度"),
            ),
        ),
    ),
    _mk_template(
        "FAMILY_ENTRUSTMENT", "social", "FAMILY_ENTRUSTMENT",
        ("托付", "嘱托", "交代", "叮嘱", "拜托", "万一"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.pick(ROLE_CONTACTS)}：存折密码是你生日倒过来。万一我有个三长两短，你妈就托付给你了，这家里的事你要担起来"),
                ("托付", "万一", "存折密码"),
            ),
            lambda c: (
                CH_APP,
                f"【微信】{c.pick(('父亲', '母亲', '二姨', '岳父'))}：孩子，家里的老屋和地契都放在衣柜铁盒里，我交代你一句，往后家里的事就拜托你多操心，照顾好你{c.pick(('妈', '爸', '妹妹'))}",
                ("交代", "拜托", "照顾好"),
            ),
        ),
    ),
    _mk_template(
        "MARRIAGE_CRISIS_RUPTURE", "social", "MARRIAGE_CRISIS_RUPTURE",
        ("分开", "分手", "过不下去", "离婚", "感情破裂", "撕破脸"),
        (CH_APP, CH_MIC),
        (
            lambda c: (
                CH_APP,
                "【微信】我们分开吧，这日子真的过不下去了。东西我已经收拾好了，明天我回娘家住。别再来找我。",
                ("分开", "过不下去", "别再来找我"),
            ),
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：你冷静一下，是不是真要离婚；{c.nick(1)}：我考虑很久了，感情已经破裂，这日子过不下去，明天去民政局把手续办了",
                ("分开", "感情", "民政局"),
            ),
        ),
    ),
    _mk_template(
        "WORKPLACE_HARASSMENT_RECORDING", "social", "WORKPLACE_HARASSMENT_RECORDING",
        ("骚扰", "录音取证", "单独", "越界", "投诉", "不当言语"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：{c.pick(WORK_CONTACTS)}总在加班后单独把我叫进办公室，说些越界的言语，我已经录音取证了，准备去投诉"),
                ("单独", "录音取证", "投诉"),
            ),
            lambda c: (
                CH_APP,
                f"【微信】{c.nick(1)}：别自己扛着，他那些不当言语就是骚扰，你先把录音取证的材料整理好，我陪你去找{c.pick(('人力资源部', '工会', '律师'))}",
                ("骚扰", "录音取证", "不当言语"),
            ),
        ),
    ),
    _mk_template(
        "NEIGHBOR_FLOOD_DISPUTE", "social", "NEIGHBOR_FLOOD_DISPUTE",
        ("漏水", "泡了", "赔偿", "物业", "楼上", "维修"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：楼上水管爆了，我家天花板全泡了，物业也不管，这个赔偿总得有个说法吧"),
                ("泡了", "物业", "赔偿"),
            ),
            lambda c: (
                CH_APP,
                f"【{c.pick(('业主群', '邻居群'))}】{c.nick(1)}：{c.rng.randrange(3, 16)}楼漏水把我家卧室泡了，木地板全废，维修报价{c.money('small')}，请物业今天上门定责",
                ("漏水", "泡了", "维修"),
            ),
        ),
    ),
    _mk_template(
        "PARENT_CANCER_CONCEALED", "social", "PARENT_CANCER_CONCEALED",
        ("瞒着", "癌症", "报告", "别告诉", "晚期", "片子"),
        (CH_MIC, CH_UT),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：妈的病理报告出来了，是{c.pick(('肺癌', '胃癌', '肠癌', '食管癌'))}中晚期。先瞒着爸，别说漏了，就说是普通炎症"),
                ("中晚期", "瞒着", "别说漏了"),
            ),
            lambda c: (
                CH_UT,
                f"片子我先收起来，谁都别告诉，特别是老人那边，知道了受不了。医生说要尽快手术，我自己扛着就行",
                ("收起来", "别告诉", "手术"),
            ),
        ),
    ),
    _mk_template(
        "CUSTODY_CHILD_CONFLICT", "social", "CUSTODY_CHILD_CONFLICT",
        ("抚养权", "抢孩子", "探视", "学校门口", "争夺", "法院"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：下午三点在{c.pick(('小学', '幼儿园'))}门口，他们家来了四个人要抢孩子，我已经报警了，抚养权的事必须法院判",
                ("抢孩子", "抚养权", "法院"),
            ),
            lambda c: (
                CH_APP,
                f"【微信】{c.nick(1)}：探视时间写得清清楚楚，你们昨天把人接走就不送回，抚养权还没判下来，别以为抢到孩子就赢了",
                ("探视", "抚养权", "抢到孩子"),
            ),
        ),
    ),
    # ---------------- 事业学业与重大转折域 ----------------
    _mk_template(
        "PAYROLL_WAGE_ARREARS", "career", "PAYROLL_WAGE_ARREARS",
        ("工资", "拖欠", "劳动仲裁", "讨薪", "结算", "血汗钱"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：{c.rng.randrange(20, 60)}个工人的{c.money('mid')}工资拖了两个月，老板一直推；再不给就去{c.org()}申请劳动仲裁"),
                ("工资", "拖了", "劳动仲裁"),
            ),
            lambda c: (
                CH_APP,
                f"【工友群】{c.nick(1)}：包工头说月底结算，结果人没影了。我们的血汗钱{c.money('mid')}到现在一分没发，明天一起去讨薪，把考勤和合同都带上",
                ("血汗钱", "结算", "讨薪"),
            ),
        ),
    ),
    _mk_template(
        "RESIGNATION_DECISION", "career", "RESIGNATION_DECISION",
        ("辞职", "离职", "不干了", "交接", "决定", "递交"),
        (CH_UT, CH_APP),
        (
            lambda c: (
                CH_UT,
                f"我想清楚了，这个月工资一发就辞职。干得再多也升不上去，明天把离职申请递上去，手头的活交接给{c.nick(0)}",
                ("辞职", "离职申请", "交接"),
            ),
            lambda c: (
                CH_APP,
                f"【微信】{c.nick(1)}：我已经决定离职了，合同条款看过没有影响，下个月{c.rng.randrange(8, 26)}号走人，你那边早点物色接手的",
                ("离职", "决定", "走人"),
            ),
        ),
    ),
    _mk_template(
        "THESIS_BLIND_REVIEW", "career", "THESIS_BLIND_REVIEW",
        ("盲审", "大修", "论文", "评审意见", "答辩", "导师"),
        (CH_APP, CH_MIC),
        (
            lambda c: (
                CH_APP,
                "【研究生院】您的学位论文盲审结果已出：两位专家均给出修改后答辩意见，其中一位要求补充实验数据并重写第三章，属大修。",
                ("盲审", "大修", "修改后答辩"),
            ),
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：论文盲审被打了大修，专家说创新性不足、要补实验；我跟导师说了，导师让我{c.rng.randrange(5, 20)}天内改完重新提交",
                ("盲审", "大修", "补实验"),
            ),
        ),
    ),
    _mk_template(
        "JOB_INTERVIEW_RESULT", "career", "JOB_INTERVIEW_RESULT",
        ("面试", "录用", "试用期", "入职", "offer", "报到"),
        (CH_APP, CH_UT),
        (
            lambda c: (
                CH_APP,
                f"【{c.pick(('人事部', 'HR'))}】恭喜您通过面试，我们决定录用。试用期{c.rng.randrange(1, 4)}个月，月薪{c.money('small')}，请于下周一上午九点来报到并带齐材料。",
                ("面试", "录用", "试用期"),
            ),
            lambda c: (
                CH_UT,
                f"面试过了，对方给的试用期{c.rng.randrange(1, 4)}个月，转正后{c.money('small')}，让我下周一入职报到。总算落定了，明天先去医院把体检做了",
                ("面试", "试用期", "入职"),
            ),
        ),
    ),
    _mk_template(
        "PROJECT_FAILURE_REVIEW", "career", "PROJECT_FAILURE_REVIEW",
        ("汇报被否", "整改", "限期", "评审", "返工", "追责"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：季度汇报被领导当场否了，说方案脱离实际，限期{c.rng.randrange(3, 15)}天内整改，否则项目组要追责"),
                ("汇报被否", "整改", "追责"),
            ),
            lambda c: (
                CH_APP,
                f"【工作群】{c.nick(1)}：评审结论下来了，我们的方案评定为需返工，限期整改报告本周五前提交，责任人自己认领。",
                ("评审", "返工", "整改"),
            ),
        ),
    ),
    _mk_template(
        "SAFETY_HAZARD_ON_SITE", "career", "SAFETY_HAZARD_ON_SITE",
        ("安全", "隐患", "整改", "停工", "违规作业", "罚款"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：{c.rng.randrange(3, 9)}楼临边防护缺了一段，钢筋班两个工人没系安全带，安全员下了整改单，不整改就停工罚款"),
                ("安全带", "整改单", "停工"),
            ),
            lambda c: (
                CH_APP,
                f"【项目管理群】安全巡查通报：发现重大隐患{c.rng.randrange(2, 6)}处，涉及高空作业无防护，开出整改单并处罚款{c.money('small')}，限期今日清零。",
                ("隐患", "高空作业", "整改单"),
            ),
        ),
    ),
    _mk_template(
        "PARTNER_SHELL_COMPANY_THEFT", "career", "PARTNER_SHELL_COMPANY_THEFT",
        ("合伙人", "壳公司", "客户名单", "转移", "背叛", "查账"),
        (CH_MIC, CH_UT),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：查账才发现合伙人注册了一家壳公司，把{c.rng.randrange(5, 30)}个老客户的名单和订单都挪过去了，这是明摆着掏空公司"),
                ("合伙人", "壳公司", "客户", "查账"),
            ),
            lambda c: (
                CH_UT,
                f"这件事没法善了。合伙人偷偷注册壳公司，把供应商资源和客户名单转移到他自己的公司，账上还挂着{c.money('mid')}的应收，明天直接找律师查账",
                ("客户名单", "转移", "律师"),
            ),
        ),
    ),
    # ---------------- 生活契约与日常意外域 ----------------
    _mk_template(
        "PIPE_BACKFLOW_COMPENSATION", "life", "PIPE_BACKFLOW_COMPENSATION",
        ("倒灌", "浸泡", "索赔", "下水", "物业", "损失"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：厨房下水倒灌，橱柜和地板全泡了，损失大概{c.money('small')}，我得找物业索赔"),
                ("倒灌", "泡了", "索赔"),
            ),
            lambda c: (
                CH_APP,
                f"【{c.pick(('房东', '物业管家'))}】你家卫生间下水倒灌把楼下浸泡了，对方要求赔偿{c.money('small')}，明天上午一起过去协商。",
                ("倒灌", "浸泡", "赔偿"),
            ),
        ),
    ),
    _mk_template(
        "RENTAL_DEPOSIT_DISPUTE", "life", "RENTAL_DEPOSIT_DISPUTE",
        ("押金", "不退", "清洁费", "退租", "扣款", "合同"),
        (CH_APP, CH_MIC),
        (
            lambda c: (
                CH_APP,
                f"【{c.pick(('房东', '中介'))}】退租可以，但押金{c.money('small')}要扣掉清洁费和家具磨损{c.rng.randrange(200, 1200)}元，剩下的下个月再说。",
                ("押金", "扣掉", "清洁费"),
            ),
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：合同上写着退租验收无误就退押金，现在房东一句清洁费就扣我{c.money('small')}，这押金还能不能要回来"),
                ("押金", "清洁费", "合同"),
            ),
        ),
    ),
    _mk_template(
        "DECORATION_RUNAWAY_FRAUD", "life", "DECORATION_RUNAWAY_FRAUD",
        ("装修", "跑路", "首付款", "失联", "施工", "合同"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：装修队收了{c.money('small')}首付款就失联了，墙砸了一半人跑了，合同上的公司地址是个空店面",
                ("首付款", "失联", "合同"),
            ),
            lambda c: (
                CH_APP,
                f"【维权群】{c.nick(1)}：同款遭遇，装修队卷款跑路，我交的{c.money('small')}一分没退，施工进度停在贴砖，大家联合起来起诉。",
                ("跑路", "施工", "起诉"),
            ),
        ),
    ),
    _mk_template(
        "USED_CAR_FLOODED_DISPUTE", "life", "USED_CAR_FLOODED_DISPUTE",
        ("泡水车", "退车", "检测报告", "暗病", "维权", "车况"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：第三方检测出这台车是泡水车，座椅滑轨全是锈，我要退车，卖家一口咬定车况没问题"),
                ("泡水车", "退车", "车况"),
            ),
            lambda c: (
                CH_APP,
                f"【检测机构】车辆检测报告已出：判定为事故泡水车，涉及车价{c.money('mid')}。建议凭报告向卖方主张退车并要求赔偿。",
                ("泡水车", "退车", "检测报告"),
            ),
        ),
    ),
    _mk_template(
        "DOG_KNOCK_CHILD_DISPUTE", "life", "DOG_KNOCK_CHILD_DISPUTE",
        ("狗", "扑倒", "孩子", "派出所", "调解", "赔偿"),
        (CH_MIC, CH_APP),
        (
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：你家狗没拴绳把孩子扑倒了，膝盖都破了，现在在医院拍片。这事必须给个说法，不然我们派出所见",
                ("扑倒", "医院", "说法"),
            ),
            lambda c: (
                CH_APP,
                f"【社区群】提醒：{c.place()}附近有大型犬未拴绳扑倒幼童，家长已报警，双方在派出所调解，涉事方需承担医疗和赔偿。",
                ("扑倒", "报警", "调解"),
            ),
        ),
    ),
    _mk_template(
        "FOOD_DELIVERY_LOST_REFUND", "life", "FOOD_DELIVERY_LOST_REFUND",
        ("外卖", "丢失", "退款", "赔付", "商家", "投诉"),
        (CH_APP, CH_MIC),
        (
            lambda c: (
                CH_APP,
                f"【平台客服】您反馈的订单显示已送达但取餐柜为空，我们已为您发起退款{c.money('small')}，并对骑手作出赔付扣分处理。",
                ("退款", "已送达", "赔付"),
            ),
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：我那份外卖放在楼下被偷了，商家说不管，让我自己找平台投诉，只能申请退款了",
                ("外卖", "退款", "投诉"),
            ),
        ),
    ),
    _mk_template(
        "OVERSEAS_DRIVING_ACCIDENT", "life", "OVERSEAS_DRIVING_ACCIDENT",
        ("车祸", "境外", "语言不通", "报警", "伤者", "救援"),
        (CH_UT, CH_MIC),
        (
            lambda c: (
                CH_UT,
                f"在境外自驾出车祸了，车头撞在护栏上，副驾的人额头流血，语言不通，报警电话打了两遍说不明白，求救援",
                ("车祸", "语言不通", "救援"),
            ),
            lambda c: (
                CH_MIC,
                f"{c.nick(0)}：在境外自驾出车祸了，我在{c.pick(('海外高速', '山区公路', '环形匝道'))}追尾，安全气囊弹了，当地警方到了但语言不通，需要翻译和拖车救援",
                ("追尾", "语言不通", "警方"),
            ),
        ),
    ),
    _mk_template(
        "FRAUD_PHONE_POLICE_IMPERSONATION", "life", "FRAUD_PHONE_POLICE_IMPERSONATION",
        ("诈骗", "冒充公检法", "安全账户", "洗钱", "通缉", "转账"),
        (CH_APP, CH_MIC),
        (
            lambda c: (
                CH_APP,
                f"【来电留言】我是{c.pick(('市公安局', '检察院'))}的，你的身份信息涉嫌洗钱，需要配合核查，请将资金转入安全账户，否则发布通缉。",
                ("涉嫌洗钱", "安全账户", "通缉"),
            ),
            lambda c: (
                CH_MIC,
                c.flavor(f"{c.nick(0)}：电话里自称公检法，说我的银行卡涉嫌洗钱，让我把{c.money('mid')}转到所谓安全账户核验，这明显是诈骗"),
                ("涉嫌洗钱", "安全账户", "诈骗"),
            ),
        ),
    ),
)


def ctx_shop(c: GenCtx) -> str:
    """占位辅助（供模板内联调用，避免闭包捕获顺序问题）。"""
    return c.shop()


# ---------------------------------------------------------------------------
# 九、真假对抗与事实反转陷阱（维度 7：T01~T04）
# ---------------------------------------------------------------------------

TRAP_LABELS: Mapping[str, str] = {
    "T01": "假借条对冲（伪造转账截图 vs 银行到账失败）",
    "T02": "先承认后反悔（口头答应 vs 短信翻脸）",
    "T03": "撤回与销毁证据（违规承诺后撤回并私聊改口）",
    "T04": "假摔诈伤碰瓷（无碰撞波峰 vs 大声呼痛索赔）",
}


def _trap_T01(c: GenCtx, sid: str) -> Tuple[List[Tuple[str, str, str, Mapping[str, Any]]], List[EvidenceFact]]:
    """假借条对冲：伪截图是垃圾，银行到账失败才是事实。"""
    amount = c.money("mid")
    who = c.nick(0)
    junk = [(
        CH_APP,
        "对方发来一张转账截图，截图显示“转账成功”字样与对方姓名，无银行流水单号",
        "aT01",
        {"app": "WeChat", "sender": who, "timestamp": _iso(c.t)},
    )]
    fact = EvidenceFact(
        channel=CH_APP,
        text=f"【{c.pick(('工商银行', '建设银行'))}】您尾号{c.rng.randrange(1000, 9999)}账户的转入{amount}交易失败，对方账户状态异常，资金已原路退回。",
        intent="TRANSFER_FAILED_COUNTERPARTY",
        dimension=DIM_FINANCE,
        keywords=("交易失败", "原路退回", "账户状态异常", "到账", "转账失败"),
        anchors=(amount, "交易失败", "原路退回"),
        core=f"对手方展示转账成功截图，但银行流水显示{amount}转入失败、对方账户异常并原路退回，属假借条对冲",
        source="trap:T01",
    )
    return junk, [fact]


def _trap_T02(c: GenCtx, sid: str) -> Tuple[List[Tuple[str, str, str, Mapping[str, Any]]], List[EvidenceFact]]:
    """先承认后反悔：口头承诺离婚协议，随后短信翻脸。"""
    who = c.nick(1)
    junk: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    fact = EvidenceFact(
        channel=CH_APP,
        text=f"【微信】{who}：想离门都没有，耗死你。昨天电话里答应明早九点去民政局的话不算数了，我反悔了。",
        intent="PROMISE_REVERSAL_CONFLICT",
        dimension=DIM_SOCIAL,
        keywords=("反悔", "不算数", "翻脸", "改口", "承诺作废"),
        anchors=(who, "反悔", "不算数"),
        core="对方在电话中承诺次日上午九点去民政局办理协议离婚，两小时后改口反悔并放话耗着，属先承认后反悔",
        source="trap:T02",
    )
    return junk, [fact]


def _trap_T03(c: GenCtx, sid: str) -> Tuple[List[Tuple[str, str, str, Mapping[str, Any]]], List[EvidenceFact]]:
    """撤回与销毁证据：群聊违规承诺后撤回，私聊改口。"""
    who = c.nick(2)
    back = c.nick(3)
    junk: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    fact = EvidenceFact(
        channel=CH_APP,
        text=f"【微信】{who} 私聊 {back}：刚才群里那段说的是让你把{c.money('mid')}的返点走私人账户，我已经撤回了，你就当没看见，手滑发错了。",
        intent="EVIDENCE_WITHDRAWAL_DENIAL",
        dimension=DIM_CAREER,
        keywords=("撤回", "手滑", "当没看见", "违规承诺", "返点"),
        anchors=("撤回了", "手滑", "返点"),
        core=f"{who}在群内发出让{back}把{c.money('mid')}返点走私人账户的违规承诺后两分钟内撤回，并私聊改口称手滑发错，属撤回与销毁证据",
        source="trap:T03",
    )
    return junk, [fact]


def _trap_T04(c: GenCtx, sid: str) -> Tuple[List[Tuple[str, str, str, Mapping[str, Any]]], List[EvidenceFact]]:
    """假摔诈伤碰瓷：无碰撞波峰的顺势躺倒 vs 大声呼痛索赔。"""
    amount = c.money("mid")
    who = c.nick(4)
    junk: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    facts = [
        EvidenceFact(
            channel=CH_SENSOR,
            text=f"体动序列显示佩戴者缓慢下蹲后顺势躺倒，全程无碰撞波峰，峰值仅{c.rng.randrange(100, 130) / 100:.2f}g，随后{ c.rng.randrange(2, 6)}秒内起身，姿态时序不符合真实跌落",
            intent="STAGED_FALL_CLAIM",
            dimension=DIM_LIFE,
            keywords=("无碰撞波峰", "顺势躺倒", "不符合真实跌落", "诈伤", "假摔"),
            anchors=("无碰撞波峰", "顺势躺倒", "起身"),
            core="体动序列为缓慢下蹲顺势躺倒、全程无碰撞波峰且数秒内起身，与真实跌落不符，随后对方大声呼痛并索赔",
            source="trap:T04",
        ),
        EvidenceFact(
            channel=CH_MIC,
            text=f"{who}：哎哟我的腰啊，你撞人了！赔{c.money('mid')}私了，不赔我就躺这儿不起来！",
            intent="STAGED_FALL_COMPENSATION",
            dimension=DIM_SOCIAL,
            keywords=("呼痛", "索赔", "私了", "躺这儿", "撞人"),
            anchors=(who, "私了", "躺这儿"),
            core=f"{who}呼痛要求{c.rng.randrange(2, 10)}万元私了并声称被撞，与设备侧无碰撞波峰的体动序列矛盾，属假摔诈伤碰瓷",
            source="trap:T04",
        ),
    ]
    return junk, facts


TRAPS: Mapping[str, Any] = {"T01": _trap_T01, "T02": _trap_T02, "T03": _trap_T03, "T04": _trap_T04}


# ---------------------------------------------------------------------------
# 十、片段构造（垃圾噪声 + 事实证据 + 传感器波形 + 声纹拓扑）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BankItem:
    """一道题及其标答（生成后即分离，questions 文件不含 ground_truth_*）。"""

    question: Dict[str, Any]
    gt: Dict[str, Any]


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    return bool(text) and any(n and n in text for n in needles)


def _junk_mic(c: GenCtx, sid: str, topo: Mapping[str, Any], n: int, start: int,
              avoid: Sequence[str] = ()) -> List[Tuple[str, str, str, Mapping[str, Any]]]:
    out: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    k = 0
    guard = 0
    while len(out) < n and guard < n * 10:
        guard += 1
        line = _fmt(c.pick(topo["lines"]), {
            "stop": c.pick(("体育西路", "太平桥", "钟楼", "春熙路", "解放碑")),
            "line": c.rng.randrange(2, 12),
            "code": f"{c.rng.randrange(100, 999)}",
        })
        db = round(c.rng.uniform(*topo["db"]), 1)
        label = c.pick(STRANGER_ROLES)
        if _contains_any(line, avoid) or _contains_any(label, avoid):
            continue
        out.append((
            CH_MIC,
            line,
            f"m{start + k:02d}",
            {"speaker_id": f"spk_s{k + 1:02d}", "speaker_label": label,
             "ambient_noise_db": db, "duration_s": round(c.rng.uniform(1.5, 19.0), 1)},
        ))
        k += 1
    return out


def _ambient_mic(c: GenCtx, sid: str, n: int, start: int) -> List[Tuple[str, str, str, Mapping[str, Any]]]:
    out: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    for k in range(n):
        db = round(c.rng.uniform(62.0, 88.0), 1)
        out.append((
            CH_MIC,
            _fmt(c.pick(AMBIENT_DESCRIPTORS), {"db": db}),
            f"m{start + k:02d}",
            {"speaker_id": "spk_amb", "speaker_label": "环境声", "ambient_noise_db": db,
             "duration_s": round(c.rng.uniform(2.0, 30.0), 1)},
        ))
    return out


def _junk_app(c: GenCtx, sid: str, n: int, start: int,
              avoid: Sequence[str] = ()) -> List[Tuple[str, str, str, Mapping[str, Any]]]:
    pools = ("promo", "bargain", "verify", "spam_group", "system", "news")
    apps = ("微信", "短信", "淘宝", "支付宝", "美团", "同花顺", "国家医保服务平台", "小红书")
    groups = ("业主群", "小区团购群", "老同学群", "工作通知群", "骑行群", "炒股交流群")
    shops = ("蜜雪冰城", "瑞幸咖啡", "屈臣氏", "永辉超市", "钱大妈", "良品铺子")
    out: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    k = 0
    guard = 0
    while len(out) < n and guard < n * 8:
        guard += 1
        pool = c.pick(pools)
        brand = c.pick(("中金财富", "京东", "美团", "国家电网", "平安产险", "顺丰速运"))
        app = c.pick(apps)
        slots = {
            "shop": c.pick(shops), "brand": brand, "app": app,
            "n3": c.nick(3), "n4": c.rng.randrange(3, 60),
            "code6": f"{c.rng.randrange(100000, 999999)}",
            "group": c.pick(groups), "steps": c.rng.randrange(4000, 18000),
            "landmark": c.place(), "city": c.region.city, "weather": c.pick(WEATHER_POOL),
            "district": c.pick(c.region.districts), "bank": c.pick(("招商银行", "浦发银行", "杭州银行")),
        }
        content = _fmt(c.pick(APP_JUNK_POOLS[pool]), slots)
        if any(content == prev[1] for prev in out):  # 同题内绝不重复同一条噪声
            continue
        if _contains_any(content, avoid):
            continue
        out.append((
            CH_APP,
            content,
            f"a{start + k:02d}",
            {"app": app, "sender": c.pick(("系统通知", "官方客服", "营销号", brand, c.pick(groups))),
             "timestamp": _iso(c.t + timedelta(minutes=k * c.rng.randrange(3, 40)))},
        ))
        k += 1
    return out


def _micro_junk(c: GenCtx, sid: str, n: int, start: int,
                avoid: Sequence[str] = ()) -> List[Tuple[str, str, str, Mapping[str, Any]]]:
    """验证码/系统通知类微型垃圾（体积小、必剪，铁律四点名的垃圾类型）。"""
    out: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    apps = ("短信", "京东", "美团", "顺丰速运", "国家电网", "支付宝", "微信")
    k = 0
    guard = 0
    while len(out) < n and guard < n * 10:
        guard += 1
        brand = c.pick(("中金财富", "京东", "美团", "国家电网", "平安产险", "顺丰速运", "中国移动"))
        slots = {"brand": brand, "app": c.pick(apps), "code6": f"{c.rng.randrange(100000, 999999)}",
                 "n4": c.rng.randrange(1000, 9999), "landmark": c.place(), "city": c.region.city,
                 "weather": c.pick(WEATHER_POOL), "steps": c.rng.randrange(4000, 18000),
                 "shop": c.pick(("蜜雪冰城", "瑞幸咖啡", "永辉超市", "钱大妈"))}
        content = _fmt(c.pick(MICRO_JUNK_POOL), slots)
        if _contains_any(content, avoid) or any(content == prev[1] for prev in out):
            continue
        out.append((CH_APP, content, f"a{start + k:02d}",
                    {"app": slots["app"], "t": _clock(c)}))
        k += 1
    return out


def _junk_utterance(c: GenCtx, sid: str, n: int, start: int,
                    avoid: Sequence[str] = ()) -> List[Tuple[str, str, str, Mapping[str, Any]]]:
    pools = ("boast", "catchphrase", "joke", "smalltalk")
    scenes = ("自言自语", "走廊独行", "电梯里", "阳台抽烟", "厨房做饭", "车里等人")
    out: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    k = 0
    guard = 0
    while len(out) < n and guard < n * 10:
        guard += 1
        pool = c.pick(pools)
        text = _fmt(c.pick(UTTERANCE_JUNK_POOLS[pool]), {"title": c.pick(("组长", "包工头", "店长", "总监"))})
        if _contains_any(text, avoid) or any(text == prev[1] for prev in out):
            continue
        out.append((
            CH_UT,
            text,
            f"u{start + k:02d}",
            {"context_scene": c.pick(scenes), "duration_s": round(c.rng.uniform(1.5, 9.0), 1)},
        ))
        k += 1
    return out


#: 传感器垃圾窗（50Hz 碎步晃动 / 打字震动 / 地铁颠簸 / 心率正常波动）。
SENSOR_JUNK_KINDS: Tuple[str, ...] = (
    "imu_micro_shake", "typing_vibration", "vehicle_bump", "hr_normal_fluctuation",
    "stairs_walk", "household_chores", "sleep_still", "door_knock_tap",
)


def _junk_sensor(c: GenCtx, sid: str, n: int, start: int) -> List[Tuple[str, str, str, Mapping[str, Any]]]:
    out: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    motion_by_kind = {
        "imu_micro_shake": "TYPING_DESK",
        "typing_vibration": "TYPING_DESK",
        "vehicle_bump": "VEHICLE_RIDE",
        "hr_normal_fluctuation": "RESTING_SEATED",
        "stairs_walk": "STAIRS_UP",
        "household_chores": "HOUSEHOLD_CHORES",
        "sleep_still": "SLEEP_STILL",
        "door_knock_tap": "STANDING_TALK",
    }
    for k in range(n):
        kind = c.pick(SENSOR_JUNK_KINDS)
        hr = c.rng.randrange(58, 104)
        frag: Dict[str, Any] = {
            "kind": kind,
            "motion_state": motion_by_kind[kind],
            "hr_mean": hr,
            "g_peak": round(c.rng.uniform(1.05, 2.6), 2),
        }
        if kind == "vehicle_bump":
            frag.update({"g_peak": round(c.rng.uniform(2.0, 2.9), 2), "road_type": c.pick(("城市主干道", "地铁区间", "高速路面"))})
        if c.rng.random() < 0.25:
            frag["baro_hpa"] = round(c.rng.uniform(995.0, 1022.0), 1)
        out.append((CH_SENSOR, "", f"s{start + k:02d}", frag))
    return out


def _junk_voiceprint(c: GenCtx, sid: str, n: int, start: int,
                     avoid: Sequence[str] = ()) -> List[Tuple[str, str, str, Mapping[str, Any]]]:
    out: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    k = 0
    guard = 0
    while len(out) < n and guard < n * 10:
        guard += 1
        role = c.pick(STRANGER_ROLES)
        if _contains_any(role, avoid):
            continue
        out.append((
            CH_VOICEPRINT,
            "",
            f"v{start + k:02d}",
            {
                "speaker_id": f"spk_stranger_{k + 1:02d}",
                "role": role,
                "cosine_to_user": round(c.rng.uniform(0.11, 0.46), 3),
                "recurrence_days_30d": c.rng.randrange(1, 3),
            },
        ))
        k += 1
    return out


# ---------------------------------------------------------------------------
# 十一、题库构建主流程
# ---------------------------------------------------------------------------

#: 可被垃圾片段"回声"提及的方向词（制造"剪枝即丢词"的高难陷阱；只允许中性名词）。
ECHOABLE_KEYWORDS: Tuple[str, ...] = (
    "欠款", "工资", "押金", "漏水", "离职", "退款", "赔偿", "逾期", "遗产", "发票",
    "装修", "外卖", "体检", "血压", "血糖", "骨折", "咳嗽", "面试", "汇报", "合同",
)


def _pick_templates(domain: str, rng: random.Random) -> List[Mapping[str, Any]]:
    pool = [t for t in EVENT_TEMPLATES if t["domain"] == domain]
    return pool


#: 主模态 → 事实证据通道偏好（保证"传感器专精卷"里的事实确实来自传感器流）。
MODALITY_CHANNEL: Mapping[str, str] = {
    "sensor": CH_SENSOR,
    "mic": CH_MIC,
    "voiceprint": CH_MIC,
    "app": CH_APP,
    "utterance": CH_UT,
}


def _fact_from_template(
    tpl: Mapping[str, Any],
    c: GenCtx,
    fact_index: int,
    qid: str,
    prefer: str | None = None,
) -> Tuple[EvidenceFact, str, int]:
    """按模板变体生成一条事实（优先选择与主模态匹配的变体通道）。"""
    variants = list(tpl["variants"])
    if prefer:
        want = MODALITY_CHANNEL.get(prefer)
        matched = [v for v in variants if v(c)[0] == want]
        if matched:
            variant = c.pick(matched)
        else:
            variant = c.pick(variants)
    else:
        variant = c.pick(variants)
    channel, text, anchors = variant(c)
    if channel != CH_SENSOR:
        text = text
    kw = tuple(tpl["keywords"])
    anchor_list = [a for a in anchors if a and a in text]
    # 锚点增强：优先补"当事人 / 金额 / 药品与医疗器械 / 机构"这类硬实体（全部逐字出现在证据文本中）
    anchor_list = _enrich_anchors(text, anchor_list, c)
    if not any(n in anchor_list for n in c.names) and c.names:
        for n in c.names:
            if n in text:
                anchor_list.insert(0, n)
                break
    if WEARER not in anchor_list:
        anchor_list.append(WEARER)
    core = _core_sentence(tpl, text, anchor_list, c)
    fact = EvidenceFact(
        channel=channel,
        text=text,
        intent=str(tpl["intent"]),
        dimension=DOMAIN_DIMENSION[str(tpl["domain"])],
        keywords=kw,
        anchors=tuple(dict.fromkeys(anchor_list))[:4],
        core=core,
    )
    return fact, f"{qid}", 0


#: 药品与医疗器械（标答锚点的硬实体来源，逐字取自证据文本）。
MED_ANCHORS: Tuple[str, ...] = (
    "双氯芬酸钠缓释胶囊", "秋水仙碱片", "非布司他片", "阿莫西林", "头孢", "青霉素V钾片",
    "阿托伐他汀", "瑞舒伐他汀", "美托洛尔", "氨氯地平", "二甲双胍", "胰岛素",
)


def _enrich_anchors(text: str, base: Sequence[str], c: GenCtx) -> List[str]:
    """把"当事人 / 金额 / 药品 / 机构"等硬实体补进锚点（只保留逐字出现在证据文本里的）。"""
    out: List[str] = list(base)
    for med in MED_ANCHORS:
        if med in text and med not in out:
            out.insert(0, med)
    m = re.search(r"(\d+(?:\.\d+)?(?:万元|元))", text)
    if m:
        out.insert(0, m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?mmol/L)", text)
    if m:
        out.insert(0, m.group(1))
    for org in list(c.region.orgs) + list(c.region.market) + list(c.region.landmarks):
        if org in text and org not in out:
            out.insert(0, org)
            break
    dedup: List[str] = []
    for a in out:
        if a and a not in dedup:
            dedup.append(a)
    return dedup[:4]


DOMAIN_CORE_HEAD: Mapping[str, str] = {
    "health": "佩戴者出现健康异常",
    "finance": "发生财务/债务与资金变动",
    "social": "人际关系出现冲突或重大转折",
    "career": "事业与学业遭遇关键变动",
    "life": "生活契约与日常意外发生纠纷",
}


def _clean_for_core(text: str, c: GenCtx) -> str:
    """把证据原句清洗为标答核心事实描述（去方言颗粒与括号噪声，保留事实语义）。"""
    body = text.strip()
    fl = DIALECT_FLAVOR.get(c.region.dialect, DIALECT_FLAVOR["普通话"])
    for filler in list(fl["head"]) + list(fl["tail"]):
        if filler:
            body = body.replace(filler, "")
    body = re.sub(r"（[^）]{0,40}）", "", body).strip("，,。 ")
    return body[:120]


def _core_sentence(tpl: Mapping[str, Any], text: str, anchors: Sequence[str], c: GenCtx) -> str:
    """生成标答核心事实描述：领域定性 + 意图方向 + 证据原句（保证可读且唯一）。"""
    head = DOMAIN_CORE_HEAD[str(tpl["domain"])]
    body = _clean_for_core(text, c)
    keys = "、".join(a for a in anchors if a != WEARER) or WEARER
    stamp = c.t.strftime("%m-%d %H:%M")
    return f"{head}（意图方向 {tpl['intent']}）：{body}（关键要素：{keys}；记录于 {stamp} · {c.place()}）"


def _render_facts(
    c: GenCtx,
    qid: str,
    sid: str,
    facts: Sequence[EvidenceFact],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把事实渲染为（标答事实列表, 证据片段四元组列表）。"""
    gt_facts: List[Dict[str, Any]] = []
    frags: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    for i, fact in enumerate(facts, start=1):
        clock = _clock(c)  # 证据发生时刻（标答 core 尾缀与题面片段共用，绝不出现两个时间）
        core = re.sub(
            r"记录于 \d\d-\d\d \d\d:\d\d",
            f"记录于 {c.t.strftime('%m-%d')} {clock}",
            fact.core,
        )
        if fact.channel == CH_SENSOR:
            fid = f"sF{i:02d}"
            payload = _sensor_payload(fact, c)
            payload["t"] = clock
            frags.append((CH_SENSOR, fact.text, fid, payload))
        elif fact.channel == CH_APP:
            fid = f"aF{i:02d}"
            app_name, sender = _infer_app_channel(fact.text, fact.intent)
            frags.append((CH_APP, fact.text, fid, {
                "app": app_name, "sender": sender, "t": clock,
            }))
        elif fact.channel == CH_UT:
            fid = f"uF{i:02d}"
            frags.append((CH_UT, fact.text, fid, {
                "context_scene": c.pick(("独处", "电话中", "客厅", "车内", "工地角落", "病房走廊")),
                "duration_s": round(c.rng.uniform(3.0, 20.0), 1),
                "t": clock,
            }))
        else:
            fid = f"mF{i:02d}"
            role = c.pick(("关键联系人", "家人", "同事", "对方当事人"))
            frags.append((CH_MIC, fact.text, fid, {
                "speaker_id": f"spk_c{i:02d}", "speaker_label": role,
                "ambient_noise_db": round(c.rng.uniform(58.0, 74.0), 1),
                "duration_s": round(c.rng.uniform(3.0, 26.0), 1),
                "t": clock,
            }))
        gt_facts.append({
            "fact_id": f"{qid}-fact-{i}",
            "dimension_id": fact.dimension,
            "semantic_intent": fact.intent,
            "anchor_entities": list(fact.anchors),
            "directional_keywords": list(fact.keywords),
            "core_content": core,
            "source_ref_id": fid,
            "confidence": 1.0,
        })
    return gt_facts, frags


#: 证据 APP 消息的「应用」按发送方标签判定（保证"工地通报不会出现在医院 App"这类生活逻辑）。
SENDER_TAG_APP_RULES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("银行", "信用社", "银联", "农信", "建行", "工行", "招行"), "银行App"),
    (("法院", "仲裁委", "检察", "公安", "交警", "税务", "司法", "人社", "市场监管", "住建局"), "政务App"),
    (("医院", "卫生院", "诊所", "疾控", "体检", "药房", "急诊"), "医院App"),
    (("快递", "物流", "顺丰", "驿站", "邮政", "菜鸟"), "短信"),
    (("美团", "饿了么", "京东", "淘宝", "拼多多", "携程", "滴滴", "商家", "客服", "店铺"), "平台App"),
    (("群", "小区通知", "物业", "房东", "中介", "租客", "学校", "学院", "教务", "导师",
      "班主任", "老师", "家人", "亲友"), "微信"),
    (("微信",), "微信"),
    (("短信", "号码", "移动", "联通", "电信", "10086"), "短信"),
)

#: 无发送方标签时的内容特征兜底（顺序即优先级）。
CONTENT_APP_RULES: Tuple[Tuple[Tuple[str, ...], str, str], ...] = (
    (("转账", "扣款", "余额", "征信", "贷款", "应还", "到账", "流水"), "银行App", "银行"),
    (("传票", "立案", "开庭", "仲裁", "判决"), "政务App", "法院/仲裁委"),
    (("化验", "报告单", "挂号", "门诊", "复诊"), "医院App", "医院"),
    (("驿站", "取件", "派件", "签收", "包裹"), "短信", "快递公司"),
    (("订单", "骑手", "配送", "退款进度"), "平台App", "平台客服"),
    (("考勤", "班组", "结算单", "整改单"), "微信", "工作群"),
)


def _infer_app_channel(text: str, intent: str = "") -> Tuple[str, str]:
    """按【发送方/群名】标签推断 APP 与发送方；无标签时退回内容特征。"""
    match = re.match(r"【([^】]{1,14})】", text.strip())
    tag = match.group(1) if match else ""
    if tag:
        for markers, app_name in SENDER_TAG_APP_RULES:
            if any(m in tag for m in markers):
                return app_name, tag
    for markers, app_name, sender in CONTENT_APP_RULES:
        if any(m in text for m in markers):
            return app_name, sender
    if intent.startswith(("FRAUD", "CRYPTO", "REFUND", "DECORATION")):
        return "短信", "陌生号码"
    return "微信", (tag or "联系人")


def _sensor_payload(fact: EvidenceFact, c: GenCtx) -> Dict[str, Any]:
    """把传感器类事实渲染为物理字段 + 设备侧事件描述（双方均可读）。"""
    text = fact.text
    payload: Dict[str, Any] = {
        "kind": {
            "CARDIAC_VENTRICULAR_BURST": "arrhythmia_burst",
            "FALL_HIGH_G_IMPACT": "high_g_impact",
            "ASYSITOLE_SYNC_FAINT": "sinus_arrest",
            "STAGED_FALL_CLAIM": "staged_motion",
            "STAGED_FALL_COMPENSATION": "interpersonal_claim",
        }.get(fact.intent, "abnormal_event"),
        "motion_state": "RESTING_SEATED" if "静息" in text else "WALKING_STEADY",
        "summary": text,
        "sampling_hz": 50,
    }
    m = re.search(r"峰值(\d+(?:\.\d+)?)g", text)
    if m:
        payload["g_peak"] = float(m.group(1))
        payload["freefall_segment_ms"] = c.rng.randrange(60, 260)
    m = re.search(r"静止不动(\d+)秒", text)
    if m:
        payload["post_impact_stillness_s"] = float(m.group(1))
    m = re.search(r"自(\d+(?:\.\d+)?)米", text)
    if m:
        payload["fall_height_m"] = float(m.group(1))
    m = re.search(r"心率自(\d+)bpm骤升至(\d+)bpm", text)
    if m:
        payload["hr_min"], payload["hr_max"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"早搏连续阵发(\d+)次", text)
    if m:
        payload["pvc_burst_count"] = int(m.group(1))
    m = re.search(r"窦性停搏(\d+(?:\.\d+)?)秒", text)
    if m:
        payload["asystole_s"] = float(m.group(1))
    m = re.search(r"心率骤降至(\d+)bpm", text)
    if m:
        payload["hr_min"] = float(m.group(1))
    payload.setdefault("baro_hpa", round(c.rng.uniform(996.0, 1024.0), 1))
    return payload


def _assemble_streams(
    c: GenCtx,
    sid: str,
    evidence: Sequence[Tuple[str, str, str, Mapping[str, Any]]],
    junk: Sequence[Tuple[str, str, str, Mapping[str, Any]]],
) -> Tuple[Dict[str, Any], List[str]]:
    """把证据与垃圾合并为五大数据流，并返回真正被标记为垃圾的 id 集合。"""
    slices = list(evidence) + list(junk)
    mic: List[Dict[str, Any]] = []
    app: List[Dict[str, Any]] = []
    utt: List[Dict[str, Any]] = []
    sensor: List[Dict[str, Any]] = []
    speakers: List[Dict[str, Any]] = []
    junk_ids: List[str] = []
    junk_set = {fid for _, _, fid, _ in junk}

    # 佩戴者自身声纹永远保留（设备侧身份锚定，属"事实"不是垃圾）
    speakers.append({
        "speaker_frag_id": "vU",
        "speaker_id": "spk_user",
        "role": WEARER,
        "cosine_to_user": 1.0,
        "recurrence_days_30d": 30,
        "fragment_count": c.rng.randrange(120, 900),
        "first_seen_utc": _iso(c.t - timedelta(days=400)),
        "t": _clock(c),
    })

    for channel, text, fid, payload in slices:
        if channel == CH_MIC or channel == CH_VOICEPRINT:
            if channel == CH_MIC:
                item = {"snippet_id": fid, "text": text, "duration_s": payload.get("duration_s", 5.0),
                        "ambient_noise_db": payload.get("ambient_noise_db", 60.0),
                        "speaker_id": payload.get("speaker_id", "spk_unknown"),
                        "speaker_label": payload.get("speaker_label", "未知"),
                        "t": payload.get("t") or _clock(c)}
                mic.append(item)
            else:
                entry = dict(payload)
                entry["speaker_frag_id"] = fid
                speakers.append(entry)
        elif channel == CH_APP:
            entry = {"msg_id": fid, "content": text, "app": payload.get("app", "微信"),
                     "t": payload.get("t") or _clock(c)}
            if payload.get("sender"):
                entry["sender"] = payload["sender"]
            app.append(entry)
        elif channel == CH_UT:
            utt.append({"utterance_id": fid, "raw_speech": text,
                        "context_scene": payload.get("context_scene", "独处"),
                        "duration_s": payload.get("duration_s", 6.0),
                        "t": payload.get("t") or _clock(c)})
        else:  # sensor
            frag = dict(payload)
            frag["fragment_id"] = fid
            frag["t"] = payload.get("t") or _clock(c)
            sensor.append(frag)
        if fid in junk_set:
            junk_ids.append(fid)

    mic.sort(key=lambda x: x["t"])
    app.sort(key=lambda x: x["t"])
    utt.sort(key=lambda x: x["t"])
    sensor.sort(key=lambda x: x["t"])
    stream = {
        "sensor_stream": {
            "sampling_hz": 50,
            "device_id": f"aios-band-{c.region.key}-{c.rng.randrange(1000, 9999)}",
            "day_window": DAY_WINDOW,
            "window_start_utc": _iso(c.t),
            "window_end_utc": _iso(c.t + timedelta(minutes=DAY_SPAN_MIN)),
            "fragments": sensor,
        },
        "mic_stream": mic,
        "voiceprint_cluster": {
            "user_speaker_id": "spk_user",
            "detected_speakers": [s["speaker_id"] for s in speakers],
            "total_detected_speakers": len(speakers),
            "speakers": speakers,
        },
        "app_message_stream": app,
        "user_dialogue_stream": utt,
    }
    return stream, junk_ids


def _stretch_day_span(
    c: GenCtx,
    stream: Dict[str, Any],
    gt_facts: Sequence[Dict[str, Any]] = (),
) -> None:
    """把最早/最晚片段拉到当天边界附近，保证"一个人的一整天"完整覆盖 06:30~23:40。"""
    buckets: List[List[Dict[str, Any]]] = [
        stream.get("mic_stream", []),
        stream.get("app_message_stream", []),
        stream.get("user_dialogue_stream", []),
        stream.get("sensor_stream", {}).get("fragments", []),
        [s for s in stream.get("voiceprint_cluster", {}).get("speakers", []) if "t" in s],
    ]
    entries = [item for bucket in buckets for item in bucket if item.get("t")]
    if not entries:
        return

    def to_min(text: str) -> int:
        return int(text[:2]) * 60 + int(text[3:])

    by_source = {str(f["source_ref_id"]): f for f in gt_facts}

    def set_min(item: Dict[str, Any], minutes: int) -> None:
        item["t"] = f"{minutes // 60:02d}:{minutes % 60:02d}"
        key = str(item.get("fragment_id") or item.get("snippet_id") or item.get("msg_id")
                  or item.get("utterance_id") or item.get("speaker_frag_id") or "")
        fact = by_source.get(key)
        if fact is not None:  # 标答 core 与证据片段时间必须始终一致
            fact["core_content"] = re.sub(
                r"记录于 \d\d-\d\d \d\d:\d\d",
                f"记录于 {c.t.strftime('%m-%d')} {item['t']}",
                str(fact["core_content"]),
            )

    earliest = min(entries, key=lambda x: to_min(x["t"]))
    if to_min(earliest["t"]) > c.day_lo + 20:
        set_min(earliest, c.day_lo + c.rng.randrange(0, 20))
    latest = max(entries, key=lambda x: to_min(x["t"]))
    if to_min(latest["t"]) < c.day_hi - 20:
        set_min(latest, c.day_hi - c.rng.randrange(0, 20))
    for bucket in buckets:
        bucket.sort(key=lambda x: x["t"])


def _daily_stream_index(
    c: GenCtx,
    stream: Mapping[str, Any],
) -> Dict[str, Any]:
    """全天清洗后生活流索引：五流片段按 HH:MM 归并成"一个人的一天"（06:30~23:40）。"""
    stamps: List[str] = []
    for key in ("mic_stream", "app_message_stream", "user_dialogue_stream"):
        stamps += [str(item.get("t")) for item in stream.get(key, []) if item.get("t")]
    stamps += [str(f.get("t")) for f in stream.get("sensor_stream", {}).get("fragments", []) if f.get("t")]
    stamps += [str(s.get("t")) for s in stream.get("voiceprint_cluster", {}).get("speakers", []) if s.get("t")]
    stamps.sort()
    counts = {
        "mic": len(stream.get("mic_stream", [])),
        "app": len(stream.get("app_message_stream", [])),
        "utterance": len(stream.get("user_dialogue_stream", [])),
        "sensor": len(stream.get("sensor_stream", {}).get("fragments", [])),
        "voiceprint": len(stream.get("voiceprint_cluster", {}).get("speakers", [])),
    }
    return {
        "time_span": f"{stamps[0]}~{stamps[-1]}" if stamps else DAY_WINDOW,
        "slices_total": sum(counts.values()),
        "by_channel": counts,
        "ordered_by": "t",
    }


def _inject_echo_trap(
    c: GenCtx,
    sid: str,
    facts: Sequence[EvidenceFact],
    junk: List[Tuple[str, str, str, Mapping[str, Any]]],
) -> None:
    """高难陷阱：让一条**垃圾**片段提到方向关键词（剪枝者需保证事实自身证据仍在）。"""
    anchors = {a for fact in facts for a in fact.anchors}
    candidates: List[str] = []
    for fact in facts:
        for kw in fact.keywords:
            if kw in ECHOABLE_KEYWORDS and kw not in anchors:
                candidates.append(kw)
    if not candidates or not junk:
        return
    kw = c.pick(candidates)
    idx = c.rng.randrange(len(junk))
    channel, text, fid, payload = junk[idx]
    if channel == CH_MIC:
        text = f"（邻桌闲聊）诶你听说没，他那个{kw}的事后来到底怎么样了"
    elif channel == CH_APP:
        text = f"【同事闲聊群】{c.nick(5)}：你们说的那个{kw}的事情是真的吗，我也听说了"
    elif channel == CH_UT:
        text = f"（自言自语）那个{kw}的事儿，回头得找个人问问"
    else:
        return
    junk[idx] = (channel, text, fid, payload)


def build_item(
    seed: int,
    index: int,
    *,
    modality: str = "mic",
    domain: str,
    difficulty: str,
    trap: str | None,
    echo_trap: bool,
    region_key: str,
    persona_id: str,
    primary_key: str,
    secondary: Tuple[str, str] | None,
    sensor_key: str,
    acoustic_key: str,
) -> BankItem:
    """构建第 ``index`` 道题（确定性：同 seed/index 必然同题）。"""
    rng = random.Random(_hash_int(seed, index, "cleaning-arena-01a0aa2c"))
    region = next(r for r in REGIONS if r.key == region_key)
    persona = next(p for p in PERSONAS if p.pid == persona_id)
    qid = f"Q_01a0aa2c_{index + 1:05d}"
    sid = f"{index + 1:05d}"  # 片段 ID 前缀（全局唯一且紧凑）
    t = _rand_ts(rng)
    c = GenCtx(rng=rng, region=region, persona=persona, t=t)
    c.day_lo = DAY_START_MIN + rng.randrange(0, 60)                        # 起床 06:30~07:30
    c.day_hi = DAY_START_MIN + DAY_SPAN_MIN - rng.randrange(0, 70)         # 入睡 22:30~23:39

    # --- 维度 2：主事件（1 条事实）+ 跨域次事件（第 2 条事实，制造跨维度冲突）----
    facts: List[EvidenceFact] = []
    primary_tpl = next(t for t in _pick_templates(domain, rng) if t["key"] == primary_key)
    fact, _, _ = _fact_from_template(primary_tpl, c, 1, qid, prefer=modality)
    facts.append(fact)
    if secondary is not None and trap is None:
        secondary_domain, secondary_key = secondary
        second_tpl = next(t for t in _pick_templates(secondary_domain, rng) if t["key"] == secondary_key)
        second, _, _ = _fact_from_template(second_tpl, c, 2, qid, prefer=modality)
        facts.append(second)

    # --- 维度 7：真假对抗陷阱 --------------------------------------------
    trap_junk: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    trap_facts: List[EvidenceFact] = []
    if trap:
        extra_junk, extra_facts = TRAPS[trap](c, sid)
        trap_junk.extend(extra_junk)
        trap_facts.extend(extra_facts)
    # 事实按「主事实 → 陷阱事实 → 跨域次事实」排序，并按维度去重（保证跨维度冲突）
    ordered: List[EvidenceFact] = trap_facts + facts
    dedup: List[EvidenceFact] = []
    seen_dims: set[str] = set()
    for fact in ordered:
        if fact.dimension in seen_dims:
            continue
        seen_dims.add(fact.dimension)
        dedup.append(fact)
    facts = dedup

    # --- 维度 4/6：垃圾噪声（铁律四的第一剪枝对象） ------------------------
    topo = ACOUSTIC_TOPOLOGIES[acoustic_key]
    boost = MODALITY_BOOST.get(modality, {})
    n_mic_junk = max(1, rng.randrange(3, 5) + boost.get("mic", 0))
    n_amb = rng.randrange(1, 2)
    n_app = max(1, rng.randrange(3, 6) + boost.get("app", 0))
    n_micro = max(2, rng.randrange(10, 14) + boost.get("micro", 0))
    n_ut = max(1, rng.randrange(1, 3) + boost.get("ut", 0))
    n_sensor = max(1, rng.randrange(5, 8) + boost.get("sensor", 0))
    n_spk = max(1, rng.randrange(3, 6) + boost.get("spk", 0))
    avoid = tuple(
        a for fact in facts for a in fact.anchors if a != WEARER and len(a) >= 2
    )
    junk: List[Tuple[str, str, str, Mapping[str, Any]]] = []
    junk += _junk_mic(c, sid, topo, n_mic_junk, start=1, avoid=avoid)
    junk += _ambient_mic(c, sid, n_amb, start=1 + n_mic_junk)
    junk += _junk_app(c, sid, n_app, start=1, avoid=avoid)
    junk += _micro_junk(c, sid, n_micro, start=1 + n_app, avoid=avoid)
    junk += _junk_utterance(c, sid, n_ut, start=1, avoid=avoid)
    junk += _junk_sensor(c, sid, n_sensor, start=1)
    junk += _junk_voiceprint(c, sid, n_spk, start=1, avoid=avoid)
    junk += trap_junk

    # --- 铁律四兜底：垃圾占比不足 0.91 时继续补足真实噪声窗 ------------------
    kept = len(facts) + 1  # 1 = 佩戴者自身声纹（保留，不属垃圾）
    extra_seed = 0
    while junk and (len(junk) / (len(junk) + kept)) < 0.905 and extra_seed < 40:
        extra_seed += 1
        junk += _ambient_mic(c, sid, 1, start=900 + extra_seed)
        junk += _junk_sensor(c, sid, 1, start=900 + extra_seed)
        junk += _junk_voiceprint(c, sid, 1, start=900 + extra_seed, avoid=avoid)

    if echo_trap:
        _inject_echo_trap(c, sid, facts, junk)

    # --- 证据渲染 + 五流装配 ---------------------------------------------
    gt_facts, evidence = _render_facts(c, qid, sid, facts)
    stream, junk_ids = _assemble_streams(c, sid, evidence, junk)

    # --- 角色契约 V3：全天生活流索引 + 六维方向性标答 ----------------------
    _stretch_day_span(c, stream, gt_facts)
    stream["cleaned_daily_stream"] = _daily_stream_index(c, stream)
    persona_block = {
        "name": c.names[0] if c.names else f"{c.region.city}佩戴者",
        "age": persona.age,
        "city": c.region.city,
        "occupation": persona.job,
        "life_stage": persona.label,
        "key_relations": list(persona.contacts[:3]),
        "traits": list(persona.habits[:2]),
    }
    directional_gt = _directional_ground_truth(c, persona, gt_facts, has_trap=bool(trap))

    # --- 跨域冲突：主事实与次事实必须来自不同维度 --------------------------
    question: Dict[str, Any] = {
        "question_id": qid,
        "generator_agent": GENERATOR_AGENT,
        "timestamp_utc": _iso(t),
        "difficulty": difficulty,
        "day_span": DAY_WINDOW,
        "persona_tag": persona.tag,
        "persona": persona_block,
        "modality_tag": modality,
        **stream,
    }
    gt: Dict[str, Any] = {
        "question_id": qid,
        "generator_agent": GENERATOR_AGENT,
        "timestamp_utc": _iso(t),
        "difficulty": difficulty,
        "day_span": DAY_WINDOW,
        "ground_truth_facts": gt_facts,
        "ground_truth_junk_ids": junk_ids,
        "directional_ground_truth": directional_gt,
    }
    return BankItem(question=question, gt=gt)


# ---------------------------------------------------------------------------
# 十二、整卷编排（五大认知域配比、难度分布、陷阱分布、抗模板化）
# ---------------------------------------------------------------------------

TRAP_KEYS: Tuple[str, ...] = ("T01", "T02", "T03", "T04")
ACOUSTIC_KEYS: Tuple[str, ...] = tuple(ACOUSTIC_TOPOLOGIES)
SENSOR_KEYS: Tuple[str, ...] = tuple(SENSOR_WAVEFORMS)


#: 派工单规定的数据流占比：传感器 30% / MIC 30% / 声纹 20% / APP 15% / 用户原话 5%。
MODALITY_WEIGHTS: Tuple[Tuple[str, int], ...] = (
    ("sensor", 30), ("mic", 30), ("voiceprint", 20), ("app", 15), ("utterance", 5),
)
def _build_modality_slots() -> Tuple[str, ...]:
    """按目标配比生成"任意前缀都逼近配比"的模态轮转序列（Webster 除子法思路）。

    简单分块会让前 30 题全是传感器专精卷（前缀严重偏斜）；这里每一步都挑选
    "当前实际占比 − 目标占比"最小的模态，从而 100 题整周期严格等于 30/30/20/15/5，
    任意前 n 题也最多偏离 1 题。
    """

    counts = {modality: 0 for modality, _ in MODALITY_WEIGHTS}
    targets = {modality: weight / 100.0 for modality, weight in MODALITY_WEIGHTS}
    order = [modality for modality, _ in MODALITY_WEIGHTS]
    slots: List[str] = []
    for step in range(100):
        scale = step + 1
        pick = min(order, key=lambda m: (counts[m] - targets[m] * scale, order.index(m)))
        slots.append(pick)
        counts[pick] += 1
    return tuple(slots)


MODALITY_SLOTS: Tuple[str, ...] = _build_modality_slots()

#: 各主模态下的"噪声放大"倍率（该模态的垃圾切片显著加厚，形成模态专精考题）。
MODALITY_BOOST: Mapping[str, Mapping[str, int]] = {
    "sensor": {"mic": 0, "app": -2, "micro": -5, "ut": -1, "sensor": 8, "spk": -1},
    "mic": {"mic": 6, "app": -2, "micro": -4, "ut": 0, "sensor": -2, "spk": 0},
    "voiceprint": {"mic": 0, "app": -2, "micro": -4, "ut": -1, "sensor": -2, "spk": 8},
    "app": {"mic": -1, "app": 4, "micro": 7, "ut": 0, "sensor": -2, "spk": -1},
    "utterance": {"mic": 1, "app": -2, "micro": -5, "ut": 6, "sensor": -2, "spk": -1},
}


def plan_item(index: int, seed: int) -> Dict[str, Any]:
    """整卷级编排计划（决定该题的域/难度/陷阱/地域/佩戴者/模板/波形）。"""
    rng = random.Random(_hash_int(seed, index, "plan"))
    domain = DOMAINS[index % len(DOMAINS)]           # 五大域严格轮转 → 每域 20%
    persona = PERSONAS[(index * 7 + rng.randrange(0, 3)) % len(PERSONAS)]
    region = next(r for r in REGIONS if r.key == persona.regions[index % len(persona.regions)])
    trap = TRAP_KEYS[(index // 23) % len(TRAP_KEYS)] if index % 23 == 0 else None
    difficulty = ("ADVERSARIAL" if trap else
                  "EASY" if index % 13 == 0 else
                  "HARD" if index % 7 == 0 else "MEDIUM")
    secondary_domain = DOMAINS[(index + 2) % len(DOMAINS)]
    # 40% 双事实（跨维度冲突）；**每个主域等量抽取**，保证事实级五大域配比均衡
    use_secondary = (index // len(DOMAINS)) % len(DOMAINS) in (0, 1)
    primary_pool = [t for t in EVENT_TEMPLATES if t["domain"] == domain]
    secondary_pool = [t for t in EVENT_TEMPLATES if t["domain"] == secondary_domain]
    return {
        "modality": MODALITY_SLOTS[index % len(MODALITY_SLOTS)],
        "domain": domain,
        "secondary_domain": secondary_domain,
        "use_secondary": use_secondary,
        "region_key": region.key,
        "persona_id": persona.pid,
        "primary_key": primary_pool[(index // len(DOMAINS)) % len(primary_pool)]["key"],
        "secondary_key": secondary_pool[(index // (len(DOMAINS) * len(secondary_pool))) % len(secondary_pool)]["key"] if use_secondary else None,
        "trap": trap,
        "difficulty": difficulty,
        "echo_trap": index % 11 == 0,
        "sensor_key": SENSOR_KEYS[(index * 3 + rng.randrange(0, 2)) % len(SENSOR_KEYS)],
        "acoustic_key": ACOUSTIC_KEYS[(index * 5 + rng.randrange(0, 3)) % len(ACOUSTIC_KEYS)],
    }


def build_bank(count: int, seed: int = DEFAULT_SEED, *, progress_every: int = 0) -> Iterator[BankItem]:
    """按 ``plan_item`` 的编排逐题生成（确定性、可复算）。"""
    for index in range(count):
        plan = plan_item(index, seed)
        item = build_item(
            seed, index,
            modality=plan["modality"],
            domain=plan["domain"],
            difficulty=plan["difficulty"],
            trap=plan["trap"],
            echo_trap=plan["echo_trap"],
            region_key=plan["region_key"],
            persona_id=plan["persona_id"],
            primary_key=plan["primary_key"],
            secondary=(plan["secondary_domain"], plan["secondary_key"]) if plan["use_secondary"] else None,
            sensor_key=plan["sensor_key"],
            acoustic_key=plan["acoustic_key"],
        )
        if progress_every and (index + 1) % progress_every == 0:
            print(f"[gen] {index + 1}/{count} 题已生成", flush=True)
        yield item


# ---------------------------------------------------------------------------
# 十三、题面/标答质量自检（生成即校验，绝不留空占位符或泄漏字段）
# ---------------------------------------------------------------------------

DIALECT_NAMES: Tuple[str, ...] = tuple(DIALECT_FLAVOR)


def iter_question_slices(question: Mapping[str, Any]) -> Iterator[Tuple[str, str, str]]:
    """遍历题面所有片段：(通道, 片段 id, 文本)。"""
    for snippet in (question.get("mic_stream") or []):
        yield CH_MIC, str(snippet.get("snippet_id", "")), str(snippet.get("text") or "")
    for message in (question.get("app_message_stream") or []):
        yield CH_APP, str(message.get("msg_id", "")), str(message.get("content") or "")
    for utterance in (question.get("user_dialogue_stream") or []):
        yield CH_UT, str(utterance.get("utterance_id", "")), str(utterance.get("raw_speech") or "")
    for speaker in ((question.get("voiceprint_cluster") or {}).get("speakers") or []):
        yield CH_VOICEPRINT, str(speaker.get("speaker_frag_id", "")), str(speaker.get("role") or "")
    for fragment in ((question.get("sensor_stream") or {}).get("fragments") or []):
        text = str(fragment.get("summary") or fragment.get("note") or "")
        yield CH_SENSOR, str(fragment.get("fragment_id", "")), text


def _walk_keys(payload: Any) -> Iterator[str]:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            yield str(key)
            yield from _walk_keys(value)
    elif isinstance(payload, (list, tuple)):
        for entry in payload:
            yield from _walk_keys(entry)



# ===========================================================================
# 出卷官 V3 契约：全天生活流（cleaned_daily_stream）+ 六维方向性标答
# （全局日总结 / dim:health / dim:social / dim:emotion / dim:finance / dim:career）
# ===========================================================================

#: 角色契约要求的六维（全局日总结 + 五个单维总结）。
ROLE_DIMENSIONS: Tuple[str, ...] = (
    "dim:global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career",
)

#: 断言家族：把语义意图映射到"绝对偏离红线"的判据族。
INTENT_VETO_FAMILY: Mapping[str, str] = {
    "ARGUMENT_CONFLICT": "CONFLICT_RUPTURE",
    "MARRIAGE_CRISIS_RUPTURE": "CONFLICT_RUPTURE",
    "PROMISE_REVERSAL_CONFLICT": "CONFLICT_RUPTURE",
    "CUSTODY_CHILD_CONFLICT": "CONFLICT_RUPTURE",
    "INHERITANCE_FAMILY_DISPUTE": "CONFLICT_RUPTURE",
    "DOG_KNOCK_CHILD_DISPUTE": "CONFLICT_CLAIM",
    "NEIGHBOR_FLOOD_DISPUTE": "LIFE_CONTRACT",
    "PIPE_BACKFLOW_COMPENSATION": "LIFE_CONTRACT",
    "RENTAL_DEPOSIT_DISPUTE": "LIFE_CONTRACT",
    "USED_CAR_FLOODED_DISPUTE": "LIFE_CONTRACT",
    "FOOD_DELIVERY_LOST_REFUND": "LIFE_LOGISTICS",
    "CRYPTO_PONZI_COLLAPSE": "FINANCE_FRAUD_LOSS",
    "DECORATION_RUNAWAY_FRAUD": "FINANCE_FRAUD_LOSS",
    "FRAUD_PHONE_POLICE_IMPERSONATION": "FINANCE_FRAUD_LOSS",
    "REFUND_SCAM_COMPENSATION": "FINANCE_FRAUD_LOSS",
    "PARTNER_SHELL_COMPANY_THEFT": "FINANCE_FRAUD_LOSS",
    "TRANSFER_FAILED_COUNTERPARTY": "TRAP_COUNTERFACTUAL",
    "EVIDENCE_WITHDRAWAL_DENIAL": "TRAP_COUNTERFACTUAL",
    "STAGED_FALL_CLAIM": "TRAP_COUNTERFACTUAL",
    "STAGED_FALL_COMPENSATION": "TRAP_COUNTERFACTUAL",
    "BANK_LOAN_OVERDUE_NOTICE": "FINANCE_DEBT",
    "DEBT_COLLECTION_OVERDUE": "FINANCE_DEBT",
    "PAYROLL_WAGE_ARREARS": "FINANCE_WAGE",
    "FUTURES_MARGIN_CALL": "FINANCE_MARKET",
    "ASYSITOLE_SYNC_FAINT": "HEALTH_CRISIS",
    "CARDIAC_VENTRICULAR_BURST": "HEALTH_CRISIS",
    "DRUG_INDUCED_HYPOGLYCEMIA": "HEALTH_CRISIS",
    "FALL_HIGH_G_IMPACT": "HEALTH_CRISIS",
    "MED_ALLERGY_ANAPHYLAXIS": "HEALTH_CRISIS",
    "RHABDOMYOLYSIS_DARK_URINE": "HEALTH_CRISIS",
    "STROKE_ONSET_DENIAL": "HEALTH_CRISIS",
    "GOUT_ACUTE_ATTACK": "HEALTH_CHRONIC",
    "PROJECT_FAILURE_REVIEW": "CAREER_SETBACK",
    "THESIS_BLIND_REVIEW": "CAREER_SETBACK",
    "JOB_INTERVIEW_RESULT": "CAREER_DECISION",
    "RESIGNATION_DECISION": "CAREER_DECISION",
    "TAX_INSPECTION_FALSE_INVOICE": "CAREER_LEGAL",
    "SAFETY_HAZARD_ON_SITE": "SAFETY_HAZARD",
    "WORKPLACE_HARASSMENT_RECORDING": "CAREER_HARASS",
    "FAMILY_ENTRUSTMENT": "SOCIAL_SUPPORT",
    "PARENT_CANCER_CONCEALED": "FAMILY_CONCEAL",
    "OVERSEAS_DRIVING_ACCIDENT": "ACCIDENT_OVERSEAS",
    "GENERIC": "GENERIC",
}

#: 【绝对偏离的红线判据】（铁律：方向反了就是一票否决，不按字眼扣分而是整题否决）。
VETO_RED_LINES: Mapping[str, Tuple[str, ...]] = {
    "CONFLICT_RUPTURE": ("打情骂俏/甜蜜互动", "和好如初/感情升温", "纯属工作讨论无冲突"),
    "CONFLICT_CLAIM": ("对方主动赔偿并道歉和解", "纯属误会双方握手言和", "佩戴者放弃索赔"),
    "FINANCE_FRAUD_LOSS": ("资金安全无损/对方按期归还", "投资大赚/收益翻倍", "只是营销广告并非真实损失"),
    "FINANCE_DEBT": ("债务已全部结清无纠纷", "对方免除全部欠款", "借款按约到账并如期归还"),
    "FINANCE_MARKET": ("稳赚不赔毫无风险", "仅模拟盘与真实资金无关", "收益翻倍大赚一笔"),
    "FINANCE_WAGE": ("工资已按时足额发放", "老板主动结清并当面道歉", "只是核对考勤并无纠纷"),
    "HEALTH_CRISIS": ("身体无大碍只是累了", "开玩笑口嗨并无不适", "症状自行消失无需就医"),
    "HEALTH_CHRONIC": ("身体健康无任何异常", "症状立刻消失且未用药", "纯属夸张吐槽"),
    "CAREER_SETBACK": ("升职加薪获表彰", "项目/论文大获成功受表扬", "面试通过并拿到更好机会"),
    "CAREER_DECISION": ("继续留任并获晋升", "只是口嗨并无真实决定", "结论与证据方向完全相反"),
    "CAREER_LEGAL": ("合规无任何问题", "检查纯属例行公事", "佩戴者已补缴了事"),
    "CAREER_HARASS": ("只是同事间友好玩笑", "受害者主动示好接受", "纯属误会已握手言和"),
    "SOCIAL_SUPPORT": ("亲友反目成仇", "无人理会拒绝托付", "仅是陌生人搭话"),
    "SOCIAL_BETRAYAL": ("同事热心帮忙解围", "合伙关系亲密无间", "只是例行公事对接"),
    "FAMILY_CONCEAL": ("家人坦然告知并共同面对", "老人身体无任何异常", "只是普通感冒复诊"),
    "LIFE_LOGISTICS": ("物品完好准时送达", "退款顺利无任何纠纷", "快递已当面签收"),
    "LIFE_CONTRACT": ("房东主动退还押金并道歉", "邻里和睦无任何纠纷", "装修按期完工验收合格"),
    "SAFETY_HAZARD": ("现场安全合规零隐患", "只是日常例会无风险", "已按流程申报无违规"),
    "ACCIDENT_OVERSEAS": ("旅途平安顺利无事故", "常规自驾游玩无伤情", "仅车辆小剐蹭无人员伤亡"),
    "TRAP_COUNTERFACTUAL": ("采信伪造截图与对冲假信息为真实发生", "忽略反证并把它写成提纯事实", "把陷阱片段当核心事实保留"),
    "GENERIC": ("与证据方向完全相反的结论", "凭空编造未发生的事实", "把口嗨当成真实决定"),
}

#: 情绪主线（dim:emotion）三种走向与红线。
EMOTION_ARCS: Mapping[str, Mapping[str, Any]] = {
    "NEGATIVE": {
        "arc": "清晨尚算平静 → 日间压抑强撑 → 夜间情绪崩溃或彻底沉默",
        "synonyms": ("情绪低落", "压抑到崩溃", "心态崩了", "强撑到破防", "情绪失控"),
        "red_lines": ("全天心情愉快轻松", "情绪平稳毫无波澜", "把冲突写成甜蜜互动"),
    },
    "POSITIVE": {
        "arc": "清晨略带倦意 → 日间兴奋上扬 → 夜间满足复盘",
        "synonyms": ("情绪高涨", "兴奋满足", "如释重负", "心情大好"),
        "red_lines": ("情绪崩溃绝望", "全天低落沮丧", "把好事写成灾难"),
    },
    "MIXED": {
        "arc": "日常平淡起伏 → 日间忙碌小波折 → 夜间归于平静或隐隐不安",
        "synonyms": ("情绪起伏", "平淡中带波折", "隐隐不安", "忙碌而疲惫"),
        "red_lines": ("情绪单一平坦与主线无关", "情绪走向与证据相反", "毫无情绪记录"),
    },
}

#: 强负面家族 → 情绪主线取 NEGATIVE。
STRONG_NEGATIVE_FAMILIES: FrozenSet[str] = frozenset({
    "CONFLICT_RUPTURE", "FINANCE_FRAUD_LOSS", "HEALTH_CRISIS", "CAREER_HARASS",
    "TRAP_COUNTERFACTUAL", "ACCIDENT_OVERSEAS", "FAMILY_CONCEAL", "SOCIAL_BETRAYAL",
    "SAFETY_HAZARD", "CAREER_LEGAL", "FINANCE_DEBT", "FINANCE_MARKET", "FINANCE_WAGE",
})
POSITIVE_FAMILIES: FrozenSet[str] = frozenset({"SOCIAL_SUPPORT"})


def _core_body(core: str) -> str:
    """从标答句子里取出"事实本体"（去掉领域定性头与要素尾缀），用于全局主线。"""
    m = re.search(r"）：(.*?)（关键要素", core)
    return (m.group(1) if m else core).strip()


def _directional_ground_truth(
    c: GenCtx,
    persona: Persona,
    gt_facts: Sequence[Mapping[str, Any]],
    has_trap: bool,
) -> Dict[str, Any]:
    """构建六维方向性标答：全局日总结 + 五维单维总结（含方向同义词簇与红线判据）。"""
    families = [INTENT_VETO_FAMILY.get(str(f["semantic_intent"]), "GENERIC") for f in gt_facts]
    by_dim: Dict[str, Mapping[str, Any]] = {}
    primary = gt_facts[0]
    primary_family = families[0]
    for fact, family in zip(gt_facts, families):
        dim = str(fact["dimension_id"])
        if dim in by_dim:
            continue
        by_dim[dim] = {
            "dimension_id": dim,
            "fact_ref": fact["fact_id"],
            "acceptable_synonyms": list(fact["directional_keywords"])[:3],
            "absolute_red_lines": list(VETO_RED_LINES.get(family, VETO_RED_LINES["GENERIC"])),
        }

    bodies = [_core_body(str(f["core_content"]))[:48] for f in gt_facts]
    storyline = "；".join(
        (f"主线：{bodies[0]}" if i == 0 else f"转折：{b}" ) for i, b in enumerate(bodies)
    )

    if any(f in STRONG_NEGATIVE_FAMILIES for f in families):
        mood = EMOTION_ARCS["NEGATIVE"]
    elif all(f in POSITIVE_FAMILIES for f in families):
        mood = EMOTION_ARCS["POSITIVE"]
    else:
        mood = EMOTION_ARCS["MIXED"]

    global_synonyms: List[str] = []
    for fact in gt_facts:
        for kw in fact["directional_keywords"]:
            if kw not in global_synonyms:
                global_synonyms.append(kw)
    dimensions: List[Dict[str, Any]] = [
        {
            "dimension_id": "dim:global",
            "direction_summary": storyline,
            "acceptable_synonyms": global_synonyms[:4],
            "absolute_red_lines": list(VETO_RED_LINES.get(primary_family, VETO_RED_LINES["GENERIC"])),
            "evidence_ref": str(primary["source_ref_id"]),
        },
        {
            "dimension_id": "dim:emotion",
            "direction_summary": mood["arc"],
            "acceptable_synonyms": list(mood["synonyms"]),
            "absolute_red_lines": list(mood["red_lines"]),
            "evidence_ref": str(primary["source_ref_id"]),
        },
    ]
    for dim in ROLE_DIMENSIONS:
        if dim in ("dim:global", "dim:emotion"):
            continue
        if dim in by_dim:
            dimensions.append(dict(by_dim[dim]))
        else:
            dimensions.append({
                "dimension_id": dim,
                "direction_summary": "本日无该维度关键事实",
                "acceptable_synonyms": ["无相关事件", "未涉及"],
                "absolute_red_lines": ["编造该维度事实=幻觉一票否决"],
            })
    # 生活契约维（dim:life）不属于角色六维，但事实真实存在时必须如实列出
    for dim, entry in by_dim.items():
        if dim not in ROLE_DIMENSIONS:
            merged = dict(entry)
            merged["dimension_id"] = dim
            dimensions.append(merged)

    block: Dict[str, Any] = {"dimensions": dimensions}
    if has_trap:
        block["counterfactual_note"] = "含真假对抗陷阱：采信伪造/对冲信息为真实事实 = 一票否决"
    return block


def audit_item(item: BankItem) -> List[str]:
    """单题自检：返回问题清单（空列表 = 完全合规）。"""
    problems: List[str] = []
    q, gt = item.question, item.gt

    # 1. 泄漏字段（分类器答案）绝不能出现在题面
    for key in _walk_keys(q):
        if key in FORBIDDEN_QUESTION_KEYS:
            problems.append(f"LEAK_FIELD:{key}")

    # 2. 片段 ID 全局唯一 + 空占位符
    all_slice_ids = [fid for _, fid, _ in iter_question_slices(q)]
    if len(set(all_slice_ids)) != len(all_slice_ids):
        duplicates = [i for i, n in collections.Counter(all_slice_ids).items() if n > 1]
        problems.append(f"DUPLICATE_FRAGMENT_ID:{duplicates[:3]}")
    for channel, fid, text in iter_question_slices(q):
        if channel in (CH_MIC, CH_APP, CH_UT) and not text.strip():
            problems.append(f"EMPTY_TEXT:{fid}")
        if not fid:
            problems.append("EMPTY_FRAGMENT_ID")

    # 3. 事实公平可解：锚点与方向词必须在证据里可溯源
    evidence_text = " ".join(text for _, _, text in iter_question_slices(q))
    for fact in gt["ground_truth_facts"]:
        anchors = [a for a in fact["anchor_entities"] if a != WEARER]
        if anchors and not any(a in evidence_text for a in anchors):
            problems.append(f"ANCHOR_UNGROUNDED:{fact['fact_id']}")
        hits = [kw for kw in fact["directional_keywords"] if kw and kw in evidence_text]
        if len(hits) < 2:
            problems.append(f"KEYWORD_UNGROUNDED:{fact['fact_id']}")
        if not str(fact["core_content"]).strip():
            problems.append(f"EMPTY_CORE:{fact['fact_id']}")
        if not fact["source_ref_id"]:
            problems.append(f"EMPTY_SOURCE:{fact['fact_id']}")

    # 4. 源引用必须指向真实存在的片段
    all_ids = {fid for _, fid, _ in iter_question_slices(q)}
    for fact in gt["ground_truth_facts"]:
        if fact["source_ref_id"] not in all_ids:
            problems.append(f"SOURCE_MISSING:{fact['fact_id']}")

    # 5. 垃圾纯净：垃圾片段不得复述事实锚点（防"剪枝即丢证据"的伪冲突）
    junk_ids = set(gt["ground_truth_junk_ids"])
    anchors_all = {a for fact in gt["ground_truth_facts"] for a in fact["anchor_entities"] if a != WEARER and len(a) >= 2}
    for _, fid, text in iter_question_slices(q):
        if fid in junk_ids and text:
            for a in anchors_all:
                if a in text:
                    problems.append(f"JUNK_ECHOES_ANCHOR:{fid}:{a}")

    # 6. 垃圾比例（≥92%：铁律四要求海量噪声中提纯少数事实）
    total = sum(1 for _ in iter_question_slices(q))
    if total:
        ratio = len(junk_ids) / total
        if ratio < 0.90:
            problems.append(f"JUNK_RATIO_LOW:{ratio:.3f}")
        if ratio > 0.99:
            problems.append(f"JUNK_RATIO_HIGH:{ratio:.3f}")

    # 7. 跨维度冲突：双事实必须落在不同维度
    dims = [f["dimension_id"] for f in gt["ground_truth_facts"]]
    if len(dims) > 1 and len(set(dims)) != len(dims):
        problems.append("SAME_DIMENSION_FACTS")

    # 8. 角色契约 V3：六维方向性标答 + 同义词簇 + 红线判据 + 全天时间窗
    dgt = gt.get("directional_ground_truth")
    if not isinstance(dgt, Mapping):
        problems.append("MISSING_DIRECTIONAL_GT")
    else:
        dims = {d.get("dimension_id") for d in dgt.get("dimensions", [])}
        for required in ROLE_DIMENSIONS:
            if required not in dims:
                problems.append(f"MISSING_ROLE_DIMENSION:{required}")
        for entry in dgt.get("dimensions", []):
            if len(entry.get("acceptable_synonyms", [])) < 2:
                problems.append(f"FEW_SYNONYMS:{entry.get('dimension_id')}")
            if not entry.get("absolute_red_lines"):
                problems.append(f"NO_RED_LINE:{entry.get('dimension_id')}")
    persona_block = q.get("persona")
    if not isinstance(persona_block, Mapping) or not persona_block.get("name"):
        problems.append("MISSING_PERSONA")
    day = q.get("cleaned_daily_stream")
    if not isinstance(day, Mapping) or not day.get("slices_total"):
        problems.append("MISSING_DAILY_STREAM")
    else:
        span = str(day.get("time_span", "~")).split("~")
        if len(span) != 2 or not all(len(x) == 5 and x[2] == ":" for x in span):
            problems.append(f"BAD_TIME_SPAN:{day.get('time_span')}")
        elif not (DAY_START_MIN <= int(span[0][:2]) * 60 + int(span[0][3:]) and
                  int(span[1][:2]) * 60 + int(span[1][3:]) <= DAY_START_MIN + DAY_SPAN_MIN):
            problems.append(f"OUT_OF_DAY_WINDOW:{day.get('time_span')}")
        if day.get("slices_total") != sum(1 for _ in iter_question_slices(q)):
            problems.append("DAILY_STREAM_COUNT_MISMATCH")

    # 9. 五大认知域配比（单题层面：主事实维度必须合法）
    for fact in gt["ground_truth_facts"]:
        if fact["dimension_id"] not in (DIM_HEALTH, DIM_FINANCE, DIM_SOCIAL, DIM_CAREER, DIM_LIFE):
            problems.append(f"BAD_DIMENSION:{fact['dimension_id']}")
    return problems


def bank_statistics(items: Sequence[BankItem]) -> Dict[str, Any]:
    """整卷统计（用于 manifest 与验收自检）。"""
    domain = collections.Counter()
    difficulty = collections.Counter()
    intent = collections.Counter()
    dialect = collections.Counter()
    persona = collections.Counter()
    anchor_covered = anchor_total = 0
    keyword_covered = keyword_total = 0
    cores: List[str] = []
    junk_ratios: List[float] = []
    facts_per_q = collections.Counter()
    trap_count = collections.Counter()
    echo_suspect = 0
    for item in items:
        q, gt = item.question, item.gt
        difficulty[str(q["difficulty"])] += 1
        persona[str(q["persona_tag"]).split("_")[0]] += 1
        facts_per_q[len(gt["ground_truth_facts"])] += 1
        total = sum(1 for _ in iter_question_slices(q))
        junk_ratios.append(len(gt["ground_truth_junk_ids"]) / max(total, 1))
        evidence_text = " ".join(text for _, _, text in iter_question_slices(q))
        for fact in gt["ground_truth_facts"]:
            intent[fact["semantic_intent"]] += 1
            domain[fact["dimension_id"]] += 1
            cores.append(str(fact["core_content"]))
            for a in fact["anchor_entities"]:
                anchor_total += 1
                if a == WEARER or a in evidence_text:
                    anchor_covered += 1
            for kw in fact["directional_keywords"]:
                keyword_total += 1
                if kw and kw in evidence_text:
                    keyword_covered += 1
        if any(kw in text for _, fid, text in iter_question_slices(q)
               if fid in set(gt["ground_truth_junk_ids"]) for kw in ECHOABLE_KEYWORDS):
            echo_suspect += 1
    fact_total = sum(domain.values())
    modality_share = collections.Counter()
    fact_channel = collections.Counter()
    role_dim_total = 0
    red_line_facts = 0
    span_minutes: List[int] = []
    for item in items:
        modality_share[str(item.question.get("modality_tag"))] += 1
        for fact in item.gt["ground_truth_facts"]:
            fact_channel[str(fact["source_ref_id"]).split("-")[-1][:1]] += 1
            if INTENT_VETO_FAMILY.get(str(fact["semantic_intent"]), "GENERIC") != "GENERIC":
                red_line_facts += 1
        dgt_block = item.gt.get("directional_ground_truth") or {}
        role_dim_total += len(dgt_block.get("dimensions", []))
        span = str(item.question.get("cleaned_daily_stream", {}).get("time_span", "")).split("~")
        if len(span) == 2 and all(len(x) == 5 for x in span):
            span_minutes.append(
                (int(span[1][:2]) * 60 + int(span[1][3:])) - (int(span[0][:2]) * 60 + int(span[0][3:]))
            )
    primary_domain = collections.Counter()
    for item in items:
        primary = item.gt["ground_truth_facts"][0]["dimension_id"] if item.gt["ground_truth_facts"] else "?"
        primary_domain[primary] += 1
    return {
        "questions": len(items),
        "role_dimensions_per_question": round(role_dim_total / max(len(items), 1), 2),
        "red_line_facts_share": round(red_line_facts / max(fact_total, 1), 4),
        "day_span_minutes_mean": round(sum(span_minutes) / max(len(span_minutes), 1), 1),
        "modality_share": {k: round(v / max(len(items), 1), 4) for k, v in modality_share.most_common()},
        "fact_source_channel_share": {k: round(v / max(sum(fact_channel.values()), 1), 4) for k, v in fact_channel.most_common()},
        "primary_domain_share": {k: round(v / max(len(items), 1), 4) for k, v in primary_domain.most_common()},
        "adversarial_share": round(difficulty.get("ADVERSARIAL", 0) / max(len(items), 1), 4),
        "facts_total": fact_total,
        "junk_total": sum(len(i.gt["ground_truth_junk_ids"]) for i in items),
        "facts_per_question": {str(k): v for k, v in sorted(facts_per_q.items())},
        "dimension_share": {k: round(v / max(fact_total, 1), 4) for k, v in domain.most_common()},
        "difficulty_share": {k: round(v / max(len(items), 1), 4) for k, v in difficulty.most_common()},
        "intent_kinds": len(intent),
        "intent_top": intent.most_common(12),
        "persona_coverage": len(persona),
        "anchor_grounded_rate": round(anchor_covered / max(anchor_total, 1), 4),
        "keyword_grounded_rate": round(keyword_covered / max(keyword_total, 1), 4),
        "core_unique_rate": round(len(set(cores)) / max(len(cores), 1), 4),
        "junk_ratio_mean": round(statistics.fmean(junk_ratios), 4) if junk_ratios else 0.0,
        "junk_ratio_min": round(min(junk_ratios), 4) if junk_ratios else 0.0,
        "echo_trap_questions": echo_suspect,
    }


# ---------------------------------------------------------------------------
# 十四、落盘与命令行入口
# ---------------------------------------------------------------------------


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


#: 交付文件名后缀。同一战队分支上已存在队友的 10K 卷（canonical 路径，
#: 由 `benchmarks/data_cleaning/generators/generator_01a0aa2c.py` 产出），本发生器
#: 是**独立实现的 V3 版**，因此输出统一带 `_v3` 后缀，**绝不覆盖队友成果**。
OUTPUT_SUFFIX = "_v3"


def _repo_relative(path: Path, root: Path) -> str:
    """把输出路径写成仓库相对路径（绝对/相对入参都能安全处理）。"""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def default_paths(root: Path) -> Tuple[Path, Path, Path]:
    base = root / "benchmarks" / "data_cleaning"
    return (
        base / "questions" / f"questions_{GENERATOR_AGENT}{OUTPUT_SUFFIX}.jsonl",
        base / "ground_truth" / f"gt_{GENERATOR_AGENT}{OUTPUT_SUFFIX}.jsonl",
        base / "questions" / f"manifest_{GENERATOR_AGENT}{OUTPUT_SUFFIX}.json",
    )


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    q_default, gt_default, manifest_default = default_paths(root)
    ap = argparse.ArgumentParser(description="AIOS 清洗竞技场 · 01a0aa2c 高熵出卷官")
    ap.add_argument("--count", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out-questions", type=Path, default=q_default)
    ap.add_argument("--out-gt", type=Path, default=gt_default)
    ap.add_argument("--manifest", type=Path, default=manifest_default)
    ap.add_argument("--progress-every", type=int, default=1000)
    ap.add_argument("--audit-sample", type=int, default=0, help="额外抽检 N 题并打印问题清单")
    args = ap.parse_args(argv)

    items: List[BankItem] = []
    for item in build_bank(args.count, args.seed, progress_every=args.progress_every):
        items.append(item)

    # 生成即校验：任何一题不合规都 fail-closed（绝不放行带泄漏/空占位符的题）
    problems: List[str] = []
    for item in items:
        for issue in audit_item(item):
            problems.append(f"{item.question['question_id']}:{issue}")
    if args.audit_sample:
        for item in items[: args.audit_sample]:
            local = audit_item(item)
            print(f"[audit] {item.question['question_id']}: {'OK' if not local else local[:3]}")

    stats = bank_statistics(items)
    if problems:
        head = problems[:10]
        raise SystemExit(f"【出卷自检失败】共 {len(problems)} 处问题，示例：{head}")

    n_q = write_jsonl(args.out_questions, (i.question for i in items))
    n_g = write_jsonl(args.out_gt, (i.gt for i in items))
    manifest = {
        "generator_agent": GENERATOR_AGENT,
        "generator_branch": GENERATOR_BRANCH,
        "seed": args.seed,
        "count": n_q,
        "questions_sha256": sha256_file(args.out_questions),
        "ground_truth_sha256": sha256_file(args.out_gt),
        "questions_path": _repo_relative(args.out_questions, root),
        "ground_truth_path": _repo_relative(args.out_gt, root),
        "statistics": stats,
        "audit": {"problems": 0, "verdict": "PASS"},
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
