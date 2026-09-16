#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIOS 3.0 高熵出卷官 · 全天生活流题库发生器（战队 01a0aa2d-fantonghui）。

法定使命（老大最高指令长 2026-09-16）：
  * 必须出 1 万个人的一天：10,000 道 07:00~23:30 全天真 实生活流考题；
  * 每道题混合【关键大事】与【海量琐碎日常】，且必须有跨维度冲突或转折；
  * 标答必须是**方向性语义标答**：给出全局日总结 + 健康/人际/情绪/财务/事业五维锚点，
    每个锚点附【可接受的方向同义词】与【绝对偏离的红线判据】。

五条铁律对齐：
  1. 质量第一：每条事实都有可溯源载体（source_ref_id），文案皆是可用生活流，绝无占位符；
  2. 历史不可篡改：题库只生成题目与标答，不触碰任何历史事实写改；
  3. 紧急特权：跌倒冲击/静息心动过速/隐匿心梗/微弱呼救等 P0 场景自带物理判据字段
     （raw_imu_g_force / stillness_seconds / pvc_burst_count / baro_hpa），端侧可硬旁路；
  4. 大模型自主物理删除：95% 碎片是垃圾（营销/风噪/报站/砍一刀/验证码/吹牛口头禅），
     全部落在 ground_truth_junk_ids 供物理剪枝；
  5. 绝不自出自做：generator_agent == solver_agent 时裁判直接 0 分一票否决，
     本发生器只出题，答题由其他战队跨 Git 完成。

公平性不变量（发生器自检，见 verify_bank）：
  * 每条标答事实的 source_ref_id 必须真实存在；
  * 每条标答事实的 anchor_entities 必须全部出现在该载体的证据文本里；
  * 每条标答事实的 directional_keywords 必须至少有一个词出现在该载体文本里；
  * 每道题垃圾占比 >= 95%（junk >= 19 * signals）；
  * 信号载体一律 is_junk=false，垃圾载体一律出现在 ground_truth_junk_ids。

确定性：全部由 --seed 派生的 random.Random(seed + index) 驱动，任何时刻重跑逐字节一致。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

GENERATOR_AGENT = "01a0aa2d-fantonghui"
DEFAULT_SEED = 20260916
DEFAULT_COUNT = 10_000
WINDOW_START = "07:00"
WINDOW_END = "23:30"

DIM_HEALTH = "dim:health"
DIM_FINANCE = "dim:finance"
DIM_SOCIAL = "dim:social"
DIM_CAREER = "dim:career"
DIM_EMOTION = "dim:emotion"
DIM_LIFE = "dim:life"

#: 标答五维锚点（老大法定格式：全局日总结 + 健康/人际/情绪/财务/事业）
ANCHOR_DIMS: Tuple[str, ...] = (DIM_HEALTH, DIM_SOCIAL, DIM_EMOTION, DIM_FINANCE, DIM_CAREER)

#: 出题流配额（调度书第二阶段规定：传感器30% / MIC30% / 声纹20% / APP15% / 原话5%）
FOCUS_QUOTA: Tuple[Tuple[str, int], ...] = (
    ("sensor", 3000), ("mic", 3000), ("voiceprint", 2000), ("app", 1500), ("dialogue", 500),
)

#: 难度配比（高熵对抗卷：以 HARD/ADVERSARIAL 为主）
DIFFICULTY_QUOTA: Tuple[Tuple[str, int], ...] = (
    ("EASY", 1500), ("MEDIUM", 3500), ("HARD", 3500), ("ADVERSARIAL", 1500),
)

#: 事实条数配比（1 条为主，少量多证据包）
FACT_COUNT_QUOTA: Tuple[int, ...] = (1,) * 70 + (2,) * 25 + (3,) * 5

#: 垃圾/信号配比红线：junk >= 19 * signal（即垃圾占比 >= 95%）
JUNK_PER_SIGNAL = 19

# ---------------------------------------------------------------------------
# 一、人设素材池（保证 10,000 名互不相同的佩戴者）
# ---------------------------------------------------------------------------

SURNAMES: Tuple[str, ...] = (
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗",
    "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹",
    "彭", "曾", "肖", "田", "董", "袁", "潘", "于", "蒋", "蔡",
    "余", "杜", "叶", "程", "苏", "魏", "吕", "丁", "任", "沈",
    "姚", "卢", "姜", "崔", "钟", "谭", "陆", "汪", "范", "金",
    "石", "廖", "贾", "夏", "韦", "付", "方", "白", "邹", "孟",
    "熊", "秦", "邱", "江", "尹", "薛", "闫", "段", "雷", "侯",
    "龙", "史", "陶", "黎", "贺", "顾", "毛", "郝", "龚", "邵",
    "万", "钱", "严", "覃", "武", "戴", "莫", "孔", "向", "汤",
)

GIVEN_NAMES: Tuple[str, ...] = (
    "伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋",
    "勇", "艳", "杰", "娟", "涛", "明", "超", "秀英", "霞", "平",
    "刚", "桂英", "建国", "文", "斌", "辉", "力", "鹏", "健", "雪",
    "梅", "红", "玉兰", "飞", "玉梅", "浩", "凯", "燕", "俊", "帆",
    "宇", "晨", "雷", "琳", "萍", "欣", "悦", "佳", "婷", "鑫",
    "博", "思远", "子涵", "雨欣", "梓萱", "一鸣", "浩然", "嘉怡", "晨曦", "若曦",
    "志强", "秀兰", "淑华", "秀珍", "桂芳", "淑英", "玉珍", "志刚", "建华", "建军",
    "国强", "志明", "文军", "海涛", "晓东", "晓峰", "丽娟", "丽华", "春梅", "红梅",
    "小燕", "丹丹", "婷婷", "倩倩", "玲玲", "晶晶", "颖", "倩", "露", "薇",
    "烨", "桐", "淼", "泓", "澜", "瑾", "珂", "琛", "铮", "磊磊",
)

CITIES: Tuple[str, ...] = (
    "北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "西安", "南京", "重庆",
    "天津", "郑州", "长沙", "青岛", "厦门", "苏州", "沈阳", "昆明", "合肥", "济南",
    "福州", "哈尔滨", "贵阳", "南昌", "太原", "石家庄", "南宁", "兰州", "海口", "乌鲁木齐",
)

OCCUPATIONS: Tuple[Tuple[str, str], ...] = (
    ("三甲医院护士", "医院"), ("中学班主任", "学校"), ("网约车司机", "交通"),
    ("外卖骑手", "配送"), ("建筑工长", "工地"), ("企业会计", "公司"),
    ("后端程序员", "公司"), ("渠道销售", "公司"), ("超市收银员", "商超"),
    ("快递分拣员", "物流"), ("执业律师", "律所"), ("房产中介", "门店"),
    ("银行客户经理", "银行"), ("电商运营", "公司"), ("工厂质检员", "工厂"),
    ("幼儿园老师", "幼儿园"), ("社区网格员", "社区"), ("基层公务员", "机关"),
    ("在读研究生", "高校"), ("创业公司老板", "公司"), ("装修瓦工", "工地"),
    ("连锁餐饮厨师", "餐饮"), ("急诊科医生", "医院"), ("药店店员", "药店"),
    ("保险经纪人", "公司"), ("出租车司机", "交通"), ("高校讲师", "高校"),
    ("物流调度员", "物流"), ("小区物业管家", "物业"), ("手机维修师", "门店"),
    ("带货主播", "直播基地"), ("月嫂", "家政"), ("消防员", "消防站"),
    ("派出所辅警", "派出所"), ("电力检修工", "供电所"), ("个体餐饮店主", "餐饮"),
    ("写字楼保安", "写字楼"), ("农业合作社理事长", "农村"), ("地铁站务员", "地铁"),
    ("跨境电商运营", "公司"),
)

FAMILY_STRUCTURES: Tuple[str, ...] = (
    "独居", "与父母同住", "已婚无孩", "已婚有娃", "单亲带娃", "异地务工",
    "三代同堂", "与伴侣合租", "退休独居", "夫妻异地",
)

CHRONIC_CONDITIONS: Tuple[str, ...] = (
    "高血压", "2型糖尿病", "心律失常", "哮喘", "慢性胃炎",
    "痛风", "抑郁症", "腰椎间盘突出", "甲状腺结节", "无基础病",
)

COMPANY_PREFIX: Tuple[str, ...] = (
    "华夏科技", "鼎盛实业", "启明智能", "鸿运物流", "长远建材", "安泰医疗", "嘉合传媒", "恒昌机械",
)
EXAM_ORGS: Tuple[str, ...] = ("省人事考试中心", "市公务员局", "市人力资源和社会保障局")
AIRLINES: Tuple[str, ...] = ("南方航空", "国铁12306", "东方航空", "春秋航空", "高铁12306")
COURTS: Tuple[str, ...] = ("区人民法院", "市中级人民法院", "铁路运输法院")
ARBITRATION: Tuple[str, ...] = ("劳动人事争议仲裁委员会", "市劳动仲裁委")
DETECT_ORGS: Tuple[str, ...] = ("中检机动车鉴定中心", "市二手车检测中心")
PROPERTY_ORGS: Tuple[str, ...] = ("物业服务中心", "住建局房屋安全科")

BANKS: Tuple[str, ...] = (
    "工商银行", "建设银行", "招商银行", "农业银行", "中国银行", "邮储银行", "交通银行", "兴业银行",
)
HOSPITALS: Tuple[str, ...] = (
    "市第一人民医院", "华西医院", "协和医院", "市中心医院", "省人民医院", "中医院", "儿童医院", "肿瘤医院",
)
ORGS: Tuple[str, ...] = (
    "区法院", "市中级法院", "派出所", "劳动仲裁委", "海关", "社保中心", "市场监管局", "物业服务中心",
)
PLACES: Tuple[str, ...] = (
    "老地方", "楼下茶馆", "小区门口", "公司会议室", "菜市场", "地铁4号线", "医院门诊楼",
    "工地项目部", "社区活动中心", "写字楼大堂", "楼下便利店", "门诊三楼", "老家县城", "出租屋",
)
AMOUNTS: Tuple[str, ...] = (
    "3万元", "5万元", "8万元", "10万元", "12万元", "18万元", "26万元", "35万元",
    "50万元", "80万元", "120万元", "6000元", "1.8万元", "2.6万元",
)
DATES: Tuple[str, ...] = (
    "下月15日", "本月底", "下周三", "12月22日", "明天上午", "月底前", "中秋前", "国庆后",
    "下周一", "今天晚上", "后天中午", "这个周五", "开学前", "月底结账前",
)
PETS: Tuple[str, ...] = ("狗", "猫")

#: 关系称谓（亲友/职场），用于生成关键当事人
CONTACT_ROLES: Tuple[str, ...] = (
    "妻子", "丈夫", "母亲", "父亲", "儿子", "女儿", "哥哥", "姐姐", "弟弟", "妹妹",
    "岳母", "婆婆", "合伙人", "同事", "领导", "下属", "房东", "租客", "中介", "律师",
    "主治医生", "护士长", "工头", "老同学", "表兄", "闺蜜", "前同事", "客户", "供应商", "项目主管",
)

SCENES: Tuple[str, ...] = (
    "home", "office", "commute", "mall", "hospital", "school",
    "construction", "street", "night_market", "gym", "station",
)


def _contact_name(index: int, salt: int) -> str:
    """派生一个与佩戴者不同名的当事人姓名（确定性）。"""
    pos = (index * 37 + salt * 91 + 13) % (len(SURNAMES) * len(GIVEN_NAMES))
    return SURNAMES[pos % len(SURNAMES)] + GIVEN_NAMES[(pos // len(SURNAMES)) % len(GIVEN_NAMES)]


def build_persona(index: int) -> Dict[str, Any]:
    """第 index 位佩戴者的完整个体画像（10,000 人互不重名）。"""
    surname = SURNAMES[index % len(SURNAMES)]
    given = GIVEN_NAMES[(index // len(SURNAMES)) % len(GIVEN_NAMES)]
    name = surname + given
    gender = "女" if index % 2 == 0 else "男"
    age = 19 + (index * 7) % 47
    job, job_kind = OCCUPATIONS[(index * 17 + 3) % len(OCCUPATIONS)]
    if age > 32 and job == "在读研究生":
        job, job_kind = OCCUPATIONS[(index * 17 + 9) % len(OCCUPATIONS)]
    elif age < 26 and job in ("执业律师", "急诊科医生", "高校讲师"):
        job, job_kind = OCCUPATIONS[(index * 17 + 11) % len(OCCUPATIONS)]
    if age <= 22:
        family_pool = ("独居", "与父母同住", "与伴侣合租")
    elif age <= 29:
        family_pool = ("独居", "与父母同住", "与伴侣合租", "已婚无孩", "夫妻异地")
    elif age < 55:
        family_pool = tuple(f for f in FAMILY_STRUCTURES if f != "退休独居")
    else:
        family_pool = ("独居", "已婚无孩", "已婚有娃", "三代同堂", "退休独居", "夫妻异地")
    family = family_pool[(index * 11 + 5) % len(family_pool)]
    chronic = CHRONIC_CONDITIONS[(index * 13 + 7) % len(CHRONIC_CONDITIONS)]
    city = CITIES[(index * 19 + 2) % len(CITIES)]
    contact_count = 4
    contacts: List[Dict[str, str]] = []
    seen_names = {name}
    for k in range(contact_count):
        role = CONTACT_ROLES[(index * 7 + k * 23) % len(CONTACT_ROLES)]
        salt = k + 1
        candidate = _contact_name(index, salt)
        guard = 0
        while candidate in seen_names and guard < 24:  # 当事人不得与佩戴者或彼此重名
            salt += 5
            candidate = _contact_name(index, salt)
            guard += 1
        seen_names.add(candidate)
        contacts.append({"role": role, "name": candidate})
    kin = next((c for c in contacts if c["role"] in ("妻子", "丈夫", "母亲", "父亲", "儿子", "女儿")), contacts[0])
    work = next((c for c in contacts if c["role"] in ("领导", "同事", "项目主管", "下属", "合伙人")), contacts[1])
    return {
        "persona_id": f"P{index + 1:05d}",
        "name": name,
        "gender": gender,
        "age": age,
        "city": city,
        "job": job,
        "job_kind": job_kind,
        "family": family,
        "chronic": chronic,
        "pet": PETS[(index * 3) % len(PETS)],
        "contacts": contacts,
        "kinship": kin,
        "colleague": work,
        "tag": f"{family}/{job}/{age}岁/{chronic}",
    }


# ---------------------------------------------------------------------------
# 二、人生剧本骨架（30 条跨维度冲突主线；事实文本由信号目录填充）
# ---------------------------------------------------------------------------

ARCS: Tuple[Dict[str, Any], ...] = (
    {"id": "A01", "name": "职场受挫×亲密关系告急", "dims": (DIM_CAREER, DIM_SOCIAL),
     "tones": ("压抑", "委屈", "失落")},
    {"id": "A02", "name": "裁员降薪×家庭经济压力", "dims": (DIM_CAREER, DIM_FINANCE),
     "tones": ("焦虑", "不甘", "疲惫")},
    {"id": "A03", "name": "父母重病隐瞒×异乡赶回", "dims": (DIM_SOCIAL, DIM_HEALTH),
     "tones": ("揪心", "愧疚", "慌乱")},
    {"id": "A04", "name": "债务违约×朋友翻脸", "dims": (DIM_FINANCE, DIM_SOCIAL),
     "tones": ("愤怒", "寒心", "疲惫")},
    {"id": "A05", "name": "连班过劳×身体报警", "dims": (DIM_CAREER, DIM_HEALTH),
     "tones": ("硬撑", "后怕", "麻木")},
    {"id": "A06", "name": "投资崩盘×婚姻危机", "dims": (DIM_FINANCE, DIM_SOCIAL),
     "tones": ("崩溃", "羞耻", "绝望")},
    {"id": "A07", "name": "子女在校出事×请假受阻", "dims": (DIM_SOCIAL, DIM_CAREER),
     "tones": ("心急", "无奈", "自责")},
    {"id": "A08", "name": "装修跑路×家庭争吵", "dims": (DIM_FINANCE, DIM_SOCIAL),
     "tones": ("窝火", "疲惫", "无力")},
    {"id": "A09", "name": "体检异常×瞒着家人", "dims": (DIM_HEALTH, DIM_SOCIAL),
     "tones": ("恐惧", "故作镇定", "孤单")},
    {"id": "A10", "name": "合伙人背叛×事业根基动摇", "dims": (DIM_SOCIAL, DIM_CAREER),
     "tones": ("愕然", "愤怒", "不甘")},
    {"id": "A11", "name": "邻里纠纷×情绪溃堤", "dims": (DIM_SOCIAL, DIM_EMOTION),
     "tones": ("憋屈", "烦躁", "崩溃")},
    {"id": "A12", "name": "学业受挫×自我怀疑", "dims": (DIM_CAREER, DIM_EMOTION),
     "tones": ("挫败", "自我否定", "麻木")},
    {"id": "A13", "name": "隐性身体危象×独自扛着", "dims": (DIM_HEALTH, DIM_EMOTION),
     "tones": ("强撑", "心慌", "孤勇")},
    {"id": "A14", "name": "家中浸水索赔×夫妻嫌隙", "dims": (DIM_LIFE, DIM_SOCIAL),
     "tones": ("烦闷", "争执", "疲惫")},
    {"id": "A15", "name": "亲人托付×工作冲突", "dims": (DIM_SOCIAL, DIM_CAREER),
     "tones": ("两难", "愧疚", "焦灼")},
    {"id": "A16", "name": "身份被冒充×资金风险", "dims": (DIM_SOCIAL, DIM_FINANCE),
     "tones": ("警觉", "后怕", "庆幸")},
    {"id": "A17", "name": "过度消耗×急性损伤", "dims": (DIM_HEALTH, DIM_LIFE),
     "tones": ("逞强", "疼痛", "懊悔")},
    {"id": "A18", "name": "加班倒地×紧急送医", "dims": (DIM_CAREER, DIM_HEALTH),
     "tones": ("惊险", "虚弱", "后怕")},
    {"id": "A19", "name": "抚养权争夺×工作分神", "dims": (DIM_SOCIAL, DIM_CAREER),
     "tones": ("愤懑", "疲惫", "坚定")},
    {"id": "A20", "name": "医患冲突×职业危机", "dims": (DIM_CAREER, DIM_EMOTION),
     "tones": ("委屈", "压力", "克制")},
    {"id": "A21", "name": "天气突变×出行与健康受阻", "dims": (DIM_HEALTH, DIM_LIFE),
     "tones": ("不适", "烦躁", "谨慎")},
    {"id": "A22", "name": "行程中断×家庭节奏打乱", "dims": (DIM_LIFE, DIM_SOCIAL),
     "tones": ("烦躁", "无奈", "疲惫")},
    {"id": "A23", "name": "账户被盗刷×家庭信任裂痕", "dims": (DIM_FINANCE, DIM_SOCIAL),
     "tones": ("惊慌", "愤怒", "自责")},
    {"id": "A24", "name": "孩子高热×请假被拒", "dims": (DIM_HEALTH, DIM_CAREER),
     "tones": ("焦灼", "无力", "心疼")},
    {"id": "A25", "name": "感情推进×工作打断", "dims": (DIM_SOCIAL, DIM_CAREER),
     "tones": ("甜蜜", "烦躁", "无奈")},
    {"id": "A26", "name": "老友借钱×该不该借", "dims": (DIM_FINANCE, DIM_SOCIAL),
     "tones": ("犹豫", "心软", "警惕")},
    {"id": "A27", "name": "职场骚扰×决定举报", "dims": (DIM_CAREER, DIM_EMOTION),
     "tones": ("愤怒", "恐惧", "坚决")},
    {"id": "A28", "name": "独居跌倒×邻里相助", "dims": (DIM_HEALTH, DIM_SOCIAL),
     "tones": ("无助", "感激", "后怕")},
    {"id": "A29", "name": "错过家人重要时刻×情绪崩溃", "dims": (DIM_EMOTION, DIM_CAREER),
     "tones": ("自责", "崩溃", "失落")},
    {"id": "A30", "name": "借贷失控×债务雪球", "dims": (DIM_FINANCE, DIM_EMOTION),
     "tones": ("恐慌", "麻木", "绝望")},
)


__all__ = [
    "GENERATOR_AGENT", "DEFAULT_SEED", "DEFAULT_COUNT", "ANCHOR_DIMS", "FOCUS_QUOTA",
    "DIFFICULTY_QUOTA", "FACT_COUNT_QUOTA", "JUNK_PER_SIGNAL", "ARCS", "SIGNALS",
    "JUNK_FAMILIES", "build_persona", "build_question", "generate", "verify_bank", "selftest",
]


# ---------------------------------------------------------------------------
# 三、信号目录（真实核心事实：借贷/嘱托/欺诈/跌倒/危象/违约……）
#     字段说明：
#       modality : 该事实的**主载体流**（与调度书配额对应）
#       keywords : 方向近义词簇（必须在文本里至少命中一个 —— 公平性不变量）
#       fact     : 标准事实描述模板（方向性标答 core_content）
#       entities : 关键实体槽位（必须出现在载体证据文本里）
#       needs    : 人设前置条件（岗位类型），空表示通用
# ---------------------------------------------------------------------------

SIGNALS: Tuple[Dict[str, Any], ...] = (
    # ---- 传感器流：真实跌倒 / 早搏阵发 / 静息心动过速 / 气压骤降 / 脱腕误报 / 碰瓷 ----
    {"id": "FALL_IMPACT", "dim": DIM_HEALTH, "intent": "FALL_IMPACT", "modality": "sensor",
     "keywords": ("跌倒", "摔倒", "重摔", "倒地不起", "摔伤", "磕碰"),
     "fact": "佩戴者发生剧烈跌倒冲击（IMU 峰值 {g:.1f}g）后长时间静止 {still}s，疑似骨折或颅脑损伤",
     "entities": ("g", "still"),
     "texts": ("跌倒冲击波形：IMU 峰值 {g}g，冲击后长时间静止 {still}s（疑似骨折/颅脑损伤）",),
     "sensor_patch": {"motion_state": "FALL_IMPACT_STATIC", "sensor_mode": "S01_IMPACT_STATIC",
                      "g_series": (1.01, 0.98, 1.02, 10.4, 1.05, 0.99, 1.01, 1.03), "g_series_peak": True,
                      "heart_rate_bpm": 104, "pvc_burst_count": 0, "baro_hpa": 1009.4,
                      "stillness_seconds": 180, "label": "跌倒冲击波形 + 冲击后长时间静止"}},
    {"id": "PVC_BURST", "dim": DIM_HEALTH, "intent": "CARDIAC_PVC_BURST", "modality": "sensor",
     "keywords": ("室性早搏", "早搏连发", "阵发早搏", "心律失常", "PVC"),
     "fact": "夜间（{time}）连续出现 {n} 次室性早搏阵发，佩戴者主诉心悸与胸闷",
     "entities": ("n", "time"),
     "texts": ("夜间 {time} 连续出现 {n} 次室性早搏阵发（PVC Bursts），佩戴者主诉心悸胸闷",),
     "sensor_patch": {"motion_state": "SLEEP_SUPINE", "sensor_mode": "S02_PVC_BURST",
                      "g_series": (0.99, 1.0, 1.01, 0.98, 1.0, 0.99, 1.02, 1.0),
                      "heart_rate_bpm": 58, "pvc_burst_count": 7, "baro_hpa": 1007.2,
                      "label": "夜间室性早搏连续阵发（PVC Bursts）"}},
    {"id": "RESTING_TACHYCARDIA", "dim": DIM_HEALTH, "intent": "RESTING_TACHYCARDIA", "modality": "sensor",
     "keywords": ("静息心动过速", "心率骤升", "心动过速", "心跳过快", "心率异常"),
     "fact": "静息状态（{place}）心率持续 {hr}bpm 达 {mins} 分钟，伴出汗与手抖",
     "entities": ("hr", "mins", "place"),
     "texts": ("静息心动过速：{place}静坐时心率持续 {hr}bpm 达 {mins} 分钟，伴出汗与手抖",),
     "sensor_patch": {"motion_state": "SITTING_STILL", "sensor_mode": "S03_RESTING_TACHY",
                      "g_series": (1.0, 0.99, 1.01, 0.98, 1.0, 1.0, 0.99, 1.01),
                      "heart_rate_bpm": 128, "pvc_burst_count": 0, "baro_hpa": 1008.1,
                      "label": "静息心率持续 128bpm"}},
    {"id": "BARO_STORM_DROP", "dim": DIM_HEALTH, "intent": "BARO_STORM_DROP", "modality": "sensor",
     "keywords": ("气压骤降", "低气压", "天气突变", "气压跳水", "暴风雨"),
     "fact": "{city}气压 6 小时内骤降 {drop}hPa，佩戴者出现偏头痛与血压 156/96 的不适反应",
     "entities": ("city", "drop"),
     "texts": ("气压骤降：{city}气压 6 小时内跳水 {drop}hPa，佩戴者偏头痛、血压 156/96",),
     "sensor_patch": {"motion_state": "STEADY_WALK", "sensor_mode": "S04_BARO_DROP",
                      "g_series": (1.02, 0.99, 1.01, 1.0, 0.98, 1.02, 1.0, 0.99),
                      "heart_rate_bpm": 88, "pvc_burst_count": 0, "baro_hpa": 996.4,
                      "label": "气压 6 小时骤降 12.4hPa"}},
    {"id": "OFF_WRIST_FALSE_ALARM", "dim": DIM_HEALTH, "intent": "OFF_WRIST_FALSE_ALARM", "modality": "sensor",
     "keywords": ("脱腕", "未佩戴", "误报", "非真实事件", "光学信号丢失"),
     "fact": "{time} 手环检测到脱腕 {mins} 分钟，心率数据缺失，属未佩戴导致的误报而非真实事件",
     "entities": ("time", "mins"),
     "texts": ("{time} 检测到脱腕 {mins} 分钟、光学信号丢失，属未佩戴误报，非真实事件",),
     "sensor_patch": {"motion_state": "OFF_WRIST", "sensor_mode": "S00_OFF_WRIST",
                      "g_series": (0.0, 0.0, 0.01, 0.0, 0.0, 0.02, 0.0, 0.0),
                      "heart_rate_bpm": 0, "pvc_burst_count": 0, "baro_hpa": 1006.8,
                      "label": "脱腕未佩戴（光学信号丢失）"}},
    {"id": "FALL_IMPACT_FAKED", "dim": DIM_FINANCE, "intent": "FAKE_FALL_FRAUD", "modality": "sensor",
     "keywords": ("碰瓷", "诈伤", "假摔", "索赔", "无碰撞波峰"),
     "fact": "IMU 全程无碰撞波峰（峰值仅 {g:.1f}g）而{contact}顺势躺倒大声呼痛索赔 {amount}，判定为碰瓷诈伤",
     "entities": ("g", "contact", "amount"),
     "texts": ("IMU 仅记录轻微顺势躺倒、无碰撞波峰（峰值仅 {g}g），{contact}却大声呼痛索赔 {amount}，疑似碰瓷诈伤",),
     "sensor_patch": {"motion_state": "GENTLE_LIE_DOWN", "sensor_mode": "S05_GENTLE_LIE",
                      "g_series": (1.02, 1.0, 0.99, 1.01, 0.97, 1.0, 1.02, 1.0), "g_series_peak": True,
                      "heart_rate_bpm": 79, "pvc_burst_count": 0, "baro_hpa": 1012.2,
                      "label": "轻微顺势躺倒、无碰撞波峰"}},

    # ---- MIC 流：借贷约定 / 还款承诺 / 争吵 / 亲人嘱托 / 保密 / 加班 / 掏空公司 ----
    {"id": "DEBT_BORROWING", "dim": DIM_FINANCE, "intent": "DEBT_BORROWING", "modality": "mic", "cues": ("转你卡上", "打欠条", "打到你账上"),
     "texts": (
         "{contact}：那咱们说定了，{date}我借给你{amount}救急，借钱这事就咱俩知道。",
         "{contact}：钱我凑齐了，{date}先拿{amount}给你，剩下的我打欠条。",
         "我跟你交个实底，{date}前{amount}一分不少打到你账上。",
     ),
     "keywords": ("借款", "借钱", "欠款", "借款约定", "打欠条", "债务"),
     "fact": "与{contact}在{place}口头约定：{date}支付{amount}（借款/还款约定成立）",
     "entities": ("contact", "amount", "date"),
     "covers": ("place",)},
    {"id": "REPAYMENT_PROMISE", "dim": DIM_FINANCE, "intent": "REPAYMENT_PROMISE", "modality": "mic", "cues": ("还清", "还上", "分期"),
     "texts": (
         "{contact}：{date}我先还你{amount}，剩下分三个月还清，我的还款计划白纸黑字写给你。",
         "{contact}：这个月手头紧，{date}先还你{amount}，这还款承诺我认，你别急。",
     ),
     "keywords": ("还款承诺", "还款计划", "分期还款", "债务清偿", "还钱"),
     "fact": "{contact}承诺{date}归还{amount}，余款分期结清",
     "entities": ("contact", "amount", "date")},
    {"id": "ARGUMENT_CONFLICT", "dim": DIM_SOCIAL, "intent": "ARGUMENT_CONFLICT", "modality": "mic", "cues": ("红脸", "吵", "说法"),
     "texts": (
         "{contact}：你当着{place}跟我红脸？这事没完，{date}再说！",
         "{contact}：少跟我扯那些，{amount}的事你今天必须给我个说法！",
         "{contact}：我不管，你答应过的事，凭什么现在反悔？",
     ),
     "keywords": ("吵架", "争吵", "冲突", "口角", "争执", "吵闹", "红脸"),
     "fact": "与{contact}在{place}发生激烈口角争执，涉及{amount}的纠纷未解",
     "entities": ("contact", "place")},
    {"id": "FAMILY_ENTRUSTMENT", "dim": DIM_SOCIAL, "intent": "FAMILY_ENTRUSTMENT", "modality": "mic", "cues": ("交代", "托付", "钥匙"),
     "texts": (
         "{kin}：{date}我去住院做手术，{pet}每天喂两次、钥匙放{place}，家里的事就托付给你了。",
         "{kin}：我把话交代在前面，{date}要是我下不了手术台，{place}那个铁盒你收好。",
         "{kin}：这事托付给你了，{date}记得去{place}拿药，别忘了给我打电话。",
     ),
     "keywords": ("托付", "嘱托", "交代", "家事托付", "叮嘱", "安排"),
     "fact": "{kin}向佩戴者郑重托付家事：{date}住院手术，钥匙放在{place}，需照顾{pet}并跟进后续",
     "entities": ("kin", "date", "place", "pet")},
    {"id": "NDA_CONFIDENTIALITY", "dim": DIM_CAREER, "intent": "NDA_CONFIDENTIALITY", "modality": "mic",
     "texts": (
         "{contact}：这事烂在肚子里，出了{place}这张门谁也不许提，泄露要赔{amount}，商业机密懂吗。",
         "{contact}：方案只给你看，{place}的规矩你懂，签了保密协议泄露要赔{amount}。",
     ),
     "keywords": ("保密", "守口如瓶", "不外传", "商业机密", "保密协议", "不透露"),
     "fact": "在{place}与{contact}达成保密约定：核心方案/商业机密不得外传，违约赔付{amount}",
     "entities": ("contact", "place", "amount")},
    {"id": "WORK_OVERTIME", "dim": DIM_CAREER, "intent": "WORK_OVERTIME", "modality": "mic", "cues": ("加个班", "通宵", "连着上"),
     "texts": (
         "{contact}：这个今天必须交，你辛苦一下，晚上留下来加班。",
         "{contact}：项目节点提前了，今晚通宵也得把报表弄出来，这已经连续加班三天了。",
         "{contact}：这周你连着加班，调休的事以后再说。",
     ),
     "keywords": ("加班", "通宵", "超时工作", "加班压力", "连日工作"),
     "fact": "{contact}要求佩戴者当晚加班/连续作业赶交付，工作负荷超时",
     "entities": ("contact",)},
    {"id": "PARTNER_SHELL_IP_THEFT", "dim": DIM_CAREER, "intent": "PARTNER_SHELL_IP_THEFT", "modality": "mic", "cues": ("另起", "转走", "掏空"),
     "texts": (
         "{contact}另起炉灶开了家壳公司，客户名单和代码全转走了，公司账上只剩{amount}。",
         "查出来了，{contact}用壳公司把{amount}业务掏空，法人是他小舅子。",
     ),
     "keywords": ("掏空公司", "另起炉灶", "壳公司", "资产转移", "侵占", "背叛"),
     "fact": "查实{contact}另起壳公司转移客户与资产，公司被掏空{amount}",
     "entities": ("contact", "amount"),
     "needs": ("公司", "律所", "门店", "直播基地", "农村")},
    {"id": "MEDICAL_DISPUTE_PUSH", "dim": DIM_CAREER, "intent": "MEDICAL_DISPUTE_PUSH", "modality": "mic", "cues": ("闹起来了", "赔"),
     "texts": (
         "家属在{place}下跪又推搡，逼我们签{amount}的赔偿协议。",
         "走廊里那家人又闹起来了，说抢救不及时，非要医院赔{amount}。",
     ),
     "keywords": ("医患纠纷", "医闹", "推搡", "索赔", "下跪"),
     "fact": "患者家属在{place}下跪并推搡施压，要求赔偿{amount}，医患冲突升级",
     "entities": ("place", "amount"),
     "needs": ("医院",)},
    {"id": "WORKPLACE_HARASSMENT", "dim": DIM_CAREER, "intent": "WORKPLACE_HARASSMENT", "modality": "mic",
     "texts": (
         "领导半夜发那种消息，我全截图了，{date}就去投诉。",
         "我不想忍了，性骚扰的聊天记录我留着，{date}交到人事。",
     ),
     "keywords": ("性骚扰", "骚扰", "投诉", "取证", "举报"),
     "fact": "佩戴者遭遇上级言语/信息骚扰并已取证，决定{date}投诉举报",
     "entities": ("date",), "needs": ("公司", "医院", "学校", "高校", "机关", "银行", "门店", "工厂")},
    {"id": "NEIGHBOR_LEAK_DISPUTE", "dim": DIM_LIFE, "intent": "NEIGHBOR_LEAK_DISPUTE", "modality": "mic", "cues": ("漏水", "泡了天花板", "摊钱"),
     "texts": (
         "{contact}：我家也漏水！你要修大家摊钱，赔偿凭啥我全出？",
         "楼上{place}漏水泡了天花板，{contact}说不是他家的责任。",
     ),
     "keywords": ("邻里纠纷", "漏水", "责任推诿", "赔偿", "泡水"),
     "fact": "与{contact}因漏水责任与赔偿发生纠纷，双方互相推诿",
     "entities": ("contact",)},
    {"id": "RENOVATION_RUNAWAY", "dim": DIM_FINANCE, "intent": "RENOVATION_RUNAWAY", "modality": "mic", "cues": ("停工", "撤场", "预付款"),
     "texts": (
         "装修队把门一锁就走了，{amount}预付款打过去三个月，{contact}电话停机。",
         "工地停了半个月，{contact}说材料涨价要加钱，不然就撤场。",
     ),
     "keywords": ("装修跑路", "卷款跑路", "停工", "预付款", "加价"),
     "fact": "装修承包方{contact}收款{amount}后停工失联，装修款存在损失风险",
     "entities": ("contact", "amount")},
    {"id": "CRYPTO_PONZI_WOM", "dim": DIM_FINANCE, "intent": "CRYPTO_PONZI_COLLAPSE", "modality": "mic", "cues": ("资金盘", "提不出来", "崩"),
     "texts": (
         "{contact}：群里那个资金盘昨晚崩盘了，{amount}本金提现失败，客服全退群跑路。",
         "我劝过你的，那个高息理财就是资金盘，现在{amount}全砸里面了。",
     ),
     "keywords": ("庞氏骗局", "资金盘", "崩盘", "提现失败", "跑路", "血本无归"),
     "fact": "与{contact}确认高息理财实为资金盘并已崩盘，{amount}本金无法提现",
     "entities": ("contact", "amount")},
    {"id": "THESIS_BLIND_REVIEW", "dim": DIM_CAREER, "intent": "THESIS_BLIND_REVIEW", "modality": "mic", "cues": ("盲审", "大修", "重写"),
     "texts": (
         "论文盲审被判大修，评阅意见三条全是致命伤，{date}前必须改完。",
         "导师就回了两个字：重写。中期检查挂了，延期半年。",
     ),
     "keywords": ("盲审", "论文大修", "延期", "答辩", "导师"),
     "fact": "论文盲审被判大修/中期检查未通过，需在{date}前完成修改，学业进度受阻",
     "entities": ("date",), "needs": ("高校", "学校", "机关")},

    # ---- APP 流：大额转账 / 假转账 / 崩盘 / 对赌 / 检验单 / 预约 / 裁员 / 竞业 / 签约 / 传票 / 倒灌 ----
    {"id": "BANK_LARGE_TRANSFER", "dim": DIM_FINANCE, "intent": "BANK_LARGE_TRANSFER", "modality": "app", "cues": ("入账", "转出", "汇款"),
     "texts": (
         "【{bank}】您尾号{tail}账户{date}入账{amount}（跨行汇入，对方户名：{contact}），请核对。",
         "【{bank}】您尾号{tail}账户{date}转出{amount}（收款方：{contact}），余额 {balance}元。",
     ),
     "keywords": ("大额转账", "入账", "转出", "汇款", "资金流水", "到账"),
     "fact": "{date} 通过{bank}发生{amount}的大额转账（交易对手：{contact}）",
     "entities": ("bank", "amount", "contact")},
    {"id": "FAKE_TRANSFER_COUNTER", "dim": DIM_FINANCE, "intent": "FAKE_TRANSFER_COUNTER", "modality": "app",
     "texts": (
         "【{bank}】转账失败：对方账户状态异常，{amount}已原路退回，请勿轻信转账截图。",
         "【{bank}】安全提示：您收到的{amount}转账截图未经本行系统确认，疑似截图造假。",
     ),
     "keywords": ("假转账", "转账失败", "截图造假", "原路退回", "未到账"),
     "fact": "{bank}提示{amount}转账失败/截图存疑并原路退回，对方疑似假转账",
     "entities": ("bank", "amount")},
    {"id": "CRYPTO_PONZI_COLLAPSE", "dim": DIM_FINANCE, "intent": "CRYPTO_PONZI_COLLAPSE", "modality": "app",
     "texts": (
         "【{company}·理财群】您参与的量化理财群已解散（资金盘崩盘），{amount}提现失败，客服集体失联。",
         "【{company}·风控】风险提示：该平台为无牌资金盘，{amount}提现通道已关闭。",
     ),
     "keywords": ("庞氏骗局", "崩盘", "资金盘", "提现失败", "跑路", "血本无归"),
     "fact": "理财平台崩盘：{amount}本金无法提现，平台/客服失联，构成资金损失",
     "entities": ("company", "amount")},
    {"id": "FINANCING_BET_FAILURE", "dim": DIM_FINANCE, "intent": "FINANCING_BET_FAILURE", "modality": "app",
     "texts": (
         "【{company}】《对赌回购清偿通知函》：请于{date}前支付回购款{amount}，否则启动诉讼与财产保全。",
         "【{company}】融资款未如期到账，对赌义务触发，需承担连带清偿{amount}。",
     ),
     "keywords": ("对赌", "回购", "连带清偿", "融资失败", "诉讼保全"),
     "fact": "对赌失败触发回购义务：{date}前需支付{amount}，否则面临诉讼与财产保全",
     "entities": ("company", "amount", "date")},
    {"id": "LAB_CRITICAL_VALUE", "dim": DIM_HEALTH, "intent": "LAB_CRITICAL_VALUE", "modality": "app", "cues": ("尿酮体", "危急值", "ST 段"),
     "texts": (
         "【{hospital}】检验单：血糖 {glu}mmol/L，尿酮体阳性，血钾异常，请立即复诊。",
         "【{hospital}】危急值通知：肌钙蛋白升高，心电图提示 ST 段改变，请立即到急诊。",
     ),
     "keywords": ("检验异常", "危急值", "尿酮体阳性", "血糖过高", "复诊"),
     "fact": "{hospital}推送检验危急值：血糖{glu}mmol/L伴尿酮体阳性，需立即复诊",
     "entities": ("hospital", "glu")},
    {"id": "DIABETIC_KETOACIDOSIS", "dim": DIM_HEALTH, "intent": "DIABETIC_KETOACIDOSIS", "modality": "app", "cues": ("酮症", "尿酮体", "血糖"),
     "texts": (
         "【{hospital}】糖尿病随访：血糖 {glu}mmol/L，尿酮体阳性，警惕酮症酸中毒，请立即就医。",
         "【{hospital}】您已连续三日血糖偏高（峰值 {glu}mmol/L），建议急诊排查酮症。",
     ),
     "keywords": ("酮症酸中毒", "血糖过高", "尿酮体阳性", "糖尿病急症", "急诊"),
     "fact": "糖尿病随访提示血糖{glu}mmol/L、尿酮体阳性，存在酮症酸中毒风险",
     "entities": ("hospital", "glu")},
    {"id": "MEDICAL_APPOINTMENT", "dim": DIM_HEALTH, "intent": "MEDICAL_APPOINTMENT", "modality": "app",
     "texts": (
         "【{hospital}】挂号成功：您已预约{date} 门诊（{dept}），请提前 30 分钟到院取号。",
         "【{hospital}】复诊提醒：{date} {dept} 随访，请携带既往病历与化验单。",
     ),
     "keywords": ("门诊预约", "挂号成功", "复诊", "定期随访", "预约就诊"),
     "fact": "{hospital}确认{date}{dept}门诊/复诊预约成功",
     "entities": ("hospital", "date", "dept")},
    {"id": "MEDICATION_REMINDER", "dim": DIM_HEALTH, "intent": "MEDICATION_REMINDER", "modality": "app",
     "texts": (
         "【用药助手】{time} 服药提醒：{drug}，请按时用药，勿与酒精同服。",
         "【{hospital}】处方续方成功：{drug}，{date}前按时服药，出现不适立即停药就诊。",
     ),
     "keywords": ("服药提醒", "按时用药", "处方续方", "漏服", "用药"),
     "fact": "用药提醒/续方：需按时服用{drug}，注意用药禁忌",
     "entities": ("drug", "time")},
    {"id": "LAYOFF_DISPUTE", "dim": DIM_CAREER, "intent": "LAYOFF_DISPUTE", "modality": "app",
     "texts": (
         "【HR·{company}】裁员通知：请于{date}前签署离职补偿协议（{amount}），逾期视为自动放弃。",
         "【{arbitration}】劳动仲裁受理通知：您与公司的赔偿争议已立案，{date}开庭。",
     ),
     "keywords": ("裁员", "离职补偿", "劳动争议", "劳动仲裁", "赔偿"),
     "fact": "公司启动裁员/劳动争议：{date}前需签署补偿协议或进入仲裁",
     "entities": ("date",)},
    {"id": "NON_COMPETE_2M", "dim": DIM_CAREER, "intent": "NON_COMPETE_2M", "modality": "app",
     "texts": (
         "【{arbitration}】竞业限制提醒：竞业期 24 个月，违约金{amount}，请勿入职同业公司。",
         "【{company}·法务】法务函：您违反竞业限制协议，需赔付{amount}并停止同业任职。",
     ),
     "keywords": ("竞业限制", "违约金", "同业竞争", "限制协议"),
     "fact": "竞业限制协议约束：24 个月竞业期、违约金{amount}，存在违约争议",
     "entities": ("arbitration", "amount")},
    {"id": "EXAM_CIVIL_SERVICE", "dim": DIM_CAREER, "intent": "EXAM_CIVIL_SERVICE", "modality": "app",
     "texts": (
         "【{exam_org}】您已进入面试递补名单，{date}前提交政审材料，逾期视为放弃。",
         "【{exam_org}】录用公示：体检与政审通过后{date}报到，需提供无犯罪记录证明。",
     ),
     "keywords": ("公考", "面试递补", "政审", "录用公示", "体检"),
     "fact": "公考面试递补/录用流程：{date}前需提交政审材料，职业机会出现关键节点",
     "entities": ("date", "exam_org")},
    {"id": "CONTRACT_SIGNING", "dim": DIM_CAREER, "intent": "CONTRACT_SIGNING", "modality": "app",
     "texts": (
         "【{company}】{date} 10:00 与{contact}战略合作签约（{place}），合同金额{amount}，请携带公章。",
         "【{company}】合同评审通过：{date}与{contact}签署{amount}年度框架协议。",
     ),
     "keywords": ("签约", "合同签署", "合作签约", "框架协议", "公章"),
     "fact": "{date}在{place}与{contact}签署{amount}合作协议，进入关键商务节点",
     "entities": ("date", "company", "contact", "amount")},
    {"id": "COURT_SUMMONS", "dim": DIM_SOCIAL, "intent": "COURT_SUMMONS", "modality": "app",
     "texts": (
         "【{court}】开庭通知：您与{contact}的{case}案{date}开庭，请携带证据原件。",
         "【{court}】传票送达：{case}一案已立案受理，{date}前提交答辩状。",
     ),
     "keywords": ("开庭通知", "传票", "诉讼", "立案", "答辩状"),
     "fact": "{court}送达传票/开庭通知：与{contact}的{case}纠纷将于{date}开庭审理",
     "entities": ("court", "contact", "case", "date")},
    {"id": "CUSTODY_BATTLE_FORGED", "dim": DIM_SOCIAL, "intent": "CUSTODY_BATTLE_FORGED", "modality": "app",
     "texts": (
         "【{court}】调解通知：与{contact}的抚养权及伪造探视记录纠纷已受理，{date}调解。",
         "【{court}】证据交换通知：{contact}提交的探视记录经核查存在伪造，{date}开庭质证。",
     ),
     "keywords": ("抚养权争夺", "伪造记录", "探视权", "调解", "质证"),
     "fact": "抚养权纠纷升级：{contact}伪造探视记录，{date}由{court}调解/开庭质证",
     "entities": ("court", "contact", "date")},
    {"id": "PIPE_BACKFLOW_COMPENSATION", "dim": DIM_LIFE, "intent": "PIPE_BACKFLOW_COMPENSATION", "modality": "app",
     "texts": (
         "【{property_org}】定责书：{contact}户卫生间防水失效导致下水倒灌，负全责，建议协商赔偿{amount}。",
         "【{property_org}】报修回执：主管道堵塞引发倒灌，已浸湿地板与家具，定损{amount}。",
     ),
     "keywords": ("下水倒灌", "管道堵塞", "浸泡", "定责", "赔偿"),
     "fact": "{property_org}定责：管道堵塞/防水失效导致下水倒灌，家具地板被浸泡，定损{amount}",
     "entities": ("property_org", "amount", "contact")},
    {"id": "TRAVEL_DISRUPTION", "dim": DIM_LIFE, "intent": "TRAVEL_DISRUPTION", "modality": "app",
     "texts": (
         "【{airline}】航班取消：受天气影响，您{date}从{place}出发的航班已取消，可免费改签。",
         "【{airline}】行程提醒：{date} {place}道路积水封闭，预计延误 90 分钟，请调整出行计划。",
     ),
     "keywords": ("航班取消", "改签", "行程中断", "道路封闭", "延误"),
     "fact": "{airline}通知{date}行程中断（航班取消/道路封闭），出行计划被迫调整",
     "entities": ("airline", "date", "place")},
    {"id": "MEAL_EVENT", "dim": DIM_LIFE, "intent": "MEAL_EVENT", "modality": "app",
     "texts": (
         "【外卖】{date} 您的订单已送达{place}，餐品：{dish}，请及时取餐。",
         "【餐饮】{date} 20:30 已为您保留{place} 4 人桌（聚餐：{dish}）。",
     ),
     "keywords": ("外卖", "送餐", "取餐", "聚餐", "用餐"),
     "fact": "{date}就餐安排：{dish}已送达/已订座（{place}）",
     "entities": ("date", "place", "dish")},
    {"id": "DELIVERY_EVENT", "dim": DIM_LIFE, "intent": "DELIVERY_EVENT", "modality": "app",
     "texts": (
         "【快递】您的包裹已放{place}驿站货架 A{tail}，取件码 {code}，{date}前取走。",
         "【快递】派送中：快递员{contact}预计 {time} 送达，请保持电话畅通。",
     ),
     "keywords": ("快递", "取件码", "驿站", "签收", "包裹"),
     "fact": "快递包裹已到{place}驿站/派送中，取件码{code}，需{date}前取件",
     "entities": ("place", "code", "date")},
    {"id": "USED_CAR_FLOODED", "dim": DIM_FINANCE, "intent": "FLOODED_USED_CAR", "modality": "app",
     "texts": (
         "【{detect_org}】检测报告：{contact}卖出的二手车内饰含水率超标、线束锈蚀，判定为泡水车，涉诉{amount}。",
         "【{detect_org}】维权提示：卖家{contact}隐瞒泡水车事实，可主张退一赔三（{amount}）。",
     ),
     "keywords": ("泡水车", "隐瞒车况", "退一赔三", "检测报告", "维权"),
     "fact": "二手车检测确认车辆为泡水车，卖家{contact}隐瞒车况，涉诉金额{amount}",
     "entities": ("detect_org", "contact", "amount")},

    # ---- 原话流：微弱呼救 / 隐性心梗 / 自伤危机 / 剧痛 / 过敏 / 就医诉求 / 辞职 / 反讽讨债 ----
    {"id": "WEAK_SOS", "dim": DIM_HEALTH, "intent": "WEAK_SOS", "modality": "dialogue",
     "texts": (
         "（气声）……有人吗……喘不上气……谁来搭把手……",
         "……起不来……心口压得慌……救命……",
     ),
     "keywords": ("呼救", "求救", "喘不上气", "起不来", "搭把手", "救命"),
     "fact": "佩戴者以气声微弱呼救（喘不上气/起不来），属濒危求助信号",
     "entities": ()},
    {"id": "HIDDEN_CARDIAC_CRISIS", "dim": DIM_HEALTH, "intent": "HIDDEN_CARDIAC_CRISIS", "modality": "dialogue", "cues": ("胸口有点闷", "喘口气", "一身汗", "嘴硬"),
     "texts": (
         "没事没事，胸口憋闷得慌，我嘴硬说没事，歇会儿就好。",
         "我挺好，你别管我——就是喘憋得出汗，出这一身大汗，歇歇就过去了。",
     ),
     "keywords": ("嘴硬说没事", "胸口憋闷", "大汗", "喘憋", "心血管危象"),
     "fact": "佩戴者口头否认不适但伴大汗、胸口憋闷与喘憋，判定隐性心血管危象，应立即干预",
     "entities": ()},
    {"id": "MYOCARDIAL_INFARCTION_HIDDEN", "dim": DIM_HEALTH, "intent": "MYOCARDIAL_INFARCTION_HIDDEN", "modality": "dialogue", "cues": ("胃有点不舒服", "消化不良", "反酸"),
     "texts": (
         "胃部不适，我误判成消化不良了，可胸口压榨感和冷汗一直没退。",
         "反酸老毛病了……怎么今天胸口压榨感这么重，一身冷汗，怕是误判了。",
     ),
     "keywords": ("隐匿性心梗", "胃部不适", "冷汗", "胸口压榨感", "误判"),
     "fact": "佩戴者将胸痛误判为消化不良，实为隐匿性心梗先兆（胸口压榨感+冷汗）",
     "entities": ()},
    {"id": "SUICIDAL_CRISIS", "dim": DIM_HEALTH, "intent": "SUICIDAL_CRISIS", "modality": "dialogue", "cues": ("攒够整整一瓶", "不用醒过来"),
     "texts": (
         "药已经攒够整整一瓶了，{date}就在{place}结束吧，遗书我写好了。",
         "遗书我写好了，放在{place}，{date}之后的事就拜托你们了。",
     ),
     "keywords": ("自伤计划", "轻生", "遗书", "攒药", "不想活"),
     "fact": "佩戴者表达明确自伤计划（已备药/写遗书），属紧急心理危机需立即干预",
     "entities": ("place", "date")},
    {"id": "EMOTIONAL_CRISIS", "dim": DIM_EMOTION, "intent": "EMOTIONAL_CRISIS", "modality": "dialogue", "cues": ("活着没意思", "太难了"),
     "texts": (
         "撑不住了，我在{place}楼梯间哭了半小时，谁也不想见。",
         "今天真的太难了，一个人坐在这儿，觉得活着没意思，但我会撑住。",
     ),
     "keywords": ("情绪崩溃", "大哭", "撑不住", "没人理解", "绝望感"),
     "fact": "佩戴者在{place}情绪崩溃大哭，自述撑不住、没人理解，情绪负荷达到临界",
     "entities": ("place",)},
    {"id": "ACUTE_PAIN_ATTACK", "dim": DIM_HEALTH, "intent": "ACUTE_PAIN_ATTACK", "modality": "dialogue", "cues": ("疼得实在站不住", "疼得直不起来"),
     "texts": (
         "胃疼得实在站不住，{date}早上挂个号吧。",
         "腰疼得直不起来，得去买止痛药，实在扛不住了。",
     ),
     "keywords": ("急性疼痛", "疼得站不住", "站不住", "剧痛", "扛不住", "挂号", "挂个号"),
     "fact": "佩戴者急性疼痛发作（疼得站不住），需{date}就医处置",
     "entities": ("date",)},
    {"id": "DRUG_ANAPHYLAXIS", "dim": DIM_HEALTH, "intent": "DRUG_ANAPHYLAXIS", "modality": "dialogue", "cues": ("喘不上气", "说不出话", "起满疹子"),
     "texts": (
         "吃了头孢又喝了酒，嘴唇肿胀得说不出话，喘不上气——这是过敏反应。",
         "身上起满疹子，喉咙发紧，刚吃了海鲜，站都站不稳。",
     ),
     "keywords": ("过敏反应", "过敏性休克", "嘴唇肿胀", "喉咙发紧", "呼吸困难"),
     "fact": "佩戴者出现急性过敏反应（嘴唇肿胀/喉咙发紧/呼吸困难），存在过敏性休克风险",
     "entities": ()},
    {"id": "REAL_MEDICAL_REQUEST", "dim": DIM_HEALTH, "intent": "REAL_MEDICAL_REQUEST", "modality": "dialogue", "cues": ("去挂心内科", "做个心电图", "做个全面检查"),
     "texts": (
         "想好了，{date}请假看病，挂号去心内科，做个心电图和心脏彩超。",
         "不能再拖了，{date}请假去医院做个全面检查。",
     ),
     "keywords": ("就医诉求", "挂号", "检查", "看病", "请假就医"),
     "fact": "佩戴者提出真实就医诉求：{date}挂号就诊并做专项检查",
     "entities": ("date",)},
    {"id": "RESIGNATION_DECISION", "dim": DIM_CAREER, "intent": "RESIGNATION_DECISION", "modality": "dialogue",
     "texts": (
         "想明白了，{date}把辞职信递上去，这班我不上了。",
         "我算过了，裸辞，{date}交接完就走，别再劝我。",
     ),
     "keywords": ("辞职", "离职", "裸辞", "递交辞呈", "决定离职"),
     "fact": "佩戴者做出真实辞职决定：{date}递交辞职信/完成交接离职",
     "entities": ("date",)},
    {"id": "DEBT_DEFAULT_IRONY", "dim": DIM_FINANCE, "intent": "DEBT_DEFAULT_IRONY", "modality": "dialogue", "cues": ("电话都不接", "拉黑", "当初说"),
     "texts": (
         "呵，{contact}借了{amount}说{date}还，现在拖欠着连电话都不接，我倒成了坏人。",
         "好一个讲信用的人，{contact}的{amount}拖到{date}还没影，直接把我拉黑了。",
     ),
     "keywords": ("讨债", "违约", "失信", "拖欠", "拉黑", "不还钱", "反讽"),
     "fact": "佩戴者以反讽口吻讨债：{contact}未按{date}约定归还{amount}并失联",
     "entities": ("contact", "amount", "date")},
    {"id": "WAGE_ARREARS_IRONY", "dim": DIM_FINANCE, "intent": "WAGE_ARREARS_IRONY", "modality": "dialogue", "cues": ("工资拖", "血汗钱"),
     "texts": (
         "老板{contact}说资金周转，{amount}工资拖欠了三个月，讨薪还得看他脸色，真是我的福气。",
         "呵，{contact}的工地停工不给钱，{amount}血汗钱，我谢他八辈祖宗。",
     ),
     "keywords": ("讨薪", "拖欠工资", "欠薪", "工资没发", "反讽"),
     "fact": "佩戴者反讽讨薪：{contact}拖欠{amount}工资未发",
     "entities": ("contact", "amount")},
    {"id": "CONCEALED_CANCER", "dim": DIM_SOCIAL, "intent": "PARENT_CANCER_CONCEALED", "modality": "dialogue", "cues": ("瞒", "癌症", "病理报告"),
     "texts": (
         "妈瞒了三个月，病历藏在{place}，{date}才说出来是癌症晚期——家属隐瞒病情瞒报癌症。",
         "爸得了癌症（病历藏在{place}），家里瞒报病情一直不让我知道，我{date}才拿到病理报告。",
     ),
     "keywords": ("瞒报癌症", "癌症晚期隐瞒", "病历隐瞒", "化疗", "家属隐瞒病情"),
     "fact": "家属瞒报癌症晚期病情数月（病历藏于{place}），佩戴者{date}才得知",
     "entities": ("place", "date")},
    {"id": "DIVORCE_DECISION", "dim": DIM_SOCIAL, "intent": "DIVORCE_DECISION", "modality": "dialogue",
     "texts": (
         "{date}跟{contact}去民政局协议离婚，财产跟孩子的事一次谈清楚。",
         "过不下去了，{date}跟{contact}签离婚协议，房子归谁这条我不让。",
     ),
     "keywords": ("离婚", "协议离婚", "婚姻破裂", "分居", "财产分割"),
     "fact": "{date}与{contact}决定协议离婚，涉及财产与子女安排",
     "entities": ("date", "contact")},
    {"id": "HIDDEN_MARITAL_ASSETS", "dim": DIM_FINANCE, "intent": "HIDDEN_MARITAL_ASSETS", "modality": "dialogue", "cues": ("转给她姐", "不翼而飞", "流水"),
     "texts": (
         "{contact}把{amount}转给她姐了，账上只剩零头，离婚时想隐藏财产。",
         "查了流水才发现，{amount}婚内财产早被转移资产了，全是提前动手的。",
     ),
     "keywords": ("隐藏财产", "转移资产", "婚内财产", "隐匿存款", "流水"),
     "fact": "查实{contact}婚内转移/隐匿资产{amount}，涉及离婚财产分割争议",
     "entities": ("contact", "amount")},
    {"id": "DOG_KNOCK_CHILD", "dim": DIM_LIFE, "intent": "DOG_KNOCK_CHILD", "modality": "dialogue", "cues": ("遛狗不拴绳", "扑倒", "医药费"),
     "texts": (
         "小区里遛狗不拴绳，把我们家孩子扑倒了，{contact}连句道歉都没有，医药费{amount}也不认。",
         "大狗扑过来把孩子吓哭了，{contact}说狗不咬人，医药费{amount}谁来出？",
     ),
     "keywords": ("宠物犬", "扑倒", "幼童", "遛狗不拴绳", "医药费"),
     "fact": "未拴绳犬只扑倒幼童，{contact}拒担医药费{amount}，涉宠物侵权纠纷",
     "entities": ("contact", "amount")},

    # ---- 声纹流：本人绑定 / 亲友绑定 / 关键长谈 / 冒充亲友 ----
    {"id": "VOICE_BINDING_USER", "dim": DIM_SOCIAL, "intent": "VOICE_BINDING_USER", "modality": "voiceprint",
     "keywords": ("本人声纹确认", "佩戴者本人声纹", "本人声纹", "机主声纹绑定", "长期绑定", "锁定佩戴者", "声纹归属机主"),
     "fact": "当日声纹聚类稳定锚定佩戴者本人声纹（余弦 {cos:.2f}，{frags} 个碎片），完成机主长期绑定",
     "entities": (),
     "texts": ("声纹聚类：佩戴者本人声纹余弦 {cos}，{frags} 个碎片、跨 {days} 天复现，完成机主声纹长期绑定",)},
    {"id": "VOICE_BINDING_KEY_CONTACT", "dim": DIM_SOCIAL, "intent": "VOICE_BINDING_KEY_CONTACT", "modality": "voiceprint",
     "keywords": ("关键联系人声纹", "亲友声纹绑定", "熟人声纹", "声纹匹配至亲友", "核心联系人声纹"),
     "fact": "声纹聚类将{contact}（{role}）绑定为关键联系人（余弦 {cos:.2f}，{frags} 个碎片）",
     "entities": ("contact",),
     "texts": ("声纹聚类：{contact}（{role}）与已登记亲友声纹余弦 {cos}，{frags} 个碎片，绑定为关键联系人声纹",)},
    {"id": "KEY_CONVERSATION_WITH_CONTACT", "dim": DIM_SOCIAL, "intent": "KEY_CONVERSATION_WITH_CONTACT", "modality": "voiceprint",
     "keywords": ("长谈", "深谈", "商量", "交谈", "约定"),
     "fact": "佩戴者与关键联系人{contact}当日长时间交谈（累计 {mins} 分钟、{frags} 个碎片），就家庭/债务事项达成约定",
     "entities": ("contact", "mins"),
     "texts": ("佩戴者与{contact}当日长时间交谈累计 {mins} 分钟、{frags} 个碎片，围绕家事与债务反复商量并达成约定",)},
    {"id": "VOICE_IMPERSONATION_FRAUD", "dim": DIM_SOCIAL, "intent": "VOICE_IMPERSONATION_FRAUD", "modality": "voiceprint",
     "keywords": ("冒充", "冒充亲友", "声纹不符", "身份冒用", "可疑来电"),
     "fact": "声纹聚类发现自称{kin}的说话人声纹与真实亲友相似度仅 {cos:.2f}（远低于同簇阈值），判定为冒充亲友的可疑来电",
     "entities": ("kin",),
     "texts": ("声纹聚类发现自称{kin}的陌生来电（cluster_label=SPK_IMPOSTOR），其声纹与真实亲友余弦仅 {cos}，远低于同簇阈值，判定冒充亲友",)},
)


# ---------------------------------------------------------------------------
# 四、垃圾噪声目录（铁律四：95% 碎片必须可被物理剪枝）
#     declared=True 的碎片自带 is_junk=true 声明（端侧可直删）；
#     其余碎片不带声明，必须靠内容词表/信噪比/背景人声标记判定 —— 防止退化为纯声明剪枝。
#     trap=True 的碎片是**对抗陷阱**：语义上很像事实（吹牛/钓鱼/玩笑），但确属垃圾，
#     用于检验答题方是否会把口嗨/反讽/营销当成真实事实（幻觉红线）。
# ---------------------------------------------------------------------------

JUNK_FAMILIES: Tuple[Dict[str, Any], ...] = (
    # ---- mic：环境噪声 / 叫卖 / 报站 / 邻桌 / 家务 ----
    {"id": "mall_hawking", "modality": "mic", "scenes": ("mall", "street", "night_market"),
     "texts": ("（商场中庭促销叫卖：两块钱一串！现烤现卖！走过路过不要错过！）",
               "（导购广播：本商场周年庆，全场三折起，详情请到一楼服务台咨询）",
               "（摊主吆喝：最后三斤！清仓大甩卖，买一送一！）")},
    {"id": "subway_announce", "modality": "mic", "scenes": ("commute", "station"),
     "texts": ("（地铁广播：列车即将进站，请排队上车，注意脚下安全）",
               "（报站：下一站，人民广场，请下车的乘客提前做好准备）",
               "（站台广播：请勿倚靠屏蔽门，先下后上，谢谢配合）")},
    {"id": "wind_noise", "modality": "mic", "scenes": ("street", "commute"),
     "texts": ("（持续风噪，语音信噪比极低，无有效语义内容）",
               "（雨点敲击雨棚与远处车流底噪，无有效语音）",
               "（一次性塑料袋被风刮动的窸窣声，混有脚步回声）")},
    {"id": "crowd_chatter", "modality": "mic", "scenes": ("mall", "hospital", "station", "street"),
     "texts": ("（走廊多人交谈混杂，无法定位单一说话人）",
               "（邻桌两人聊孩子升学，与本日主线无关）",
               "（候诊区人群喧哗，夹杂叫号回声）")},
    {"id": "hospital_paging", "modality": "mic", "scenes": ("hospital",),
     "texts": ("（导医台广播：请 18 号郭先生到骨科 703 诊室就诊）",
               "（取报告提示：请患者到 4 楼内科取检验报告，报告一般 2 小时后出具）",
               "（保洁提示：请各位家属在候诊区等候，不要拥堵在诊室门口）")},
    {"id": "construction_noise", "modality": "mic", "scenes": ("construction", "street"),
     "texts": ("（锤子敲击墙体，间歇性，共 13 次）",
               "（电锤作业噪声约 88dB，伴随钢筋拖拽声）",
               "（吊机运转与金属碰撞声，无语音内容）")},
    {"id": "office_noise", "modality": "mic", "scenes": ("office",),
     "texts": ("（开放式办公区键盘敲击声密集，约 43dB）",
               "（打印机连续出纸与装订机声响）",
               "（会议室空调送风声与椅子挪动声）")},
    {"id": "home_chores", "modality": "mic", "scenes": ("home",),
     "texts": ("（洗衣机脱水运转，振动频率约 19.0Hz，持续 28 秒）",
               "（抽油烟机高档运转，约 66dB）",
               "（马桶冲水与水管回流声）")},
    {"id": "tv_show", "modality": "mic", "scenes": ("home", "night_market"),
     "texts": ("（电视综艺片头曲外放，音量较小，无对话价值）",
               "（短视频背景音乐：你是我的小呀小苹果，循环 3 次）",
               "（客厅音响播放评书，语速快且与本人无关）")},
    {"id": "pet_kid_noise", "modality": "mic", "scenes": ("home", "street"),
     "texts": ("（婴儿哭闹声持续 40 秒后逐渐安静）",
               "（宠物犬连续吠叫 9 次，随后停下）",
               "（孩子在地板上跑动的咚咚声与笑声）")},

    # ---- app：营销 / 砍一刀 / 验证码 / 群刷屏 ----
    {"id": "bargain_link", "modality": "app", "scenes": ("home", "office", "commute"),
     "texts": (("拼多多", "亲友群", "帮我砍一刀！就差你了，点击链接帮我助力一下~"),
               ("拼多多", "二姨", "我在砍价免费拿，帮我点一下，谢谢啦！[链接]"),
               ("小程序", "同学群", "一起来领现金红包，邀请 3 人即可提现，速戳！"))},
    {"id": "verify_code", "modality": "app", "scenes": ("home", "office", "commute"),
     "texts": (("短信", "95588", "【工商银行】您的验证码 739214，5 分钟内有效，请勿泄露给任何人。"),
               ("短信", "106903", "【平台】校验码 4491，用于登录验证，若非本人操作请忽略。"),
               ("短信", "106555", "【快递】取件码 8-2-1290，请到菜鸟驿站自取。"))},
    {"id": "loan_market", "modality": "app", "scenes": ("home",),
     "texts": (("短信", "106399", "【极速贷】恭喜您获得 30 万额度，无抵押、放款快，回复 Y 立即办理。"),
               ("短信", "106822", "【车抵贷】押证不押车，当天到账，额度最高 50 万，回 T 退订。"),
               ("APP推送", "金融助手", "您的信用额度已提升至 20 万，点击查看利率。"))},
    {"id": "gym_insurance", "modality": "app", "scenes": ("home", "gym"),
     "texts": (("短信", "106777", "【力健健身】年卡限时 999 元，私教体验课免费送，名额仅剩 3 个。"),
               ("短信", "95511", "【平安保险】您的医疗险即将到期，续保享 8 折，详情请点击。"),
               ("APP推送", "康康体检", "体检套餐 5 折促销，点击领取优惠券，仅限今日。"))},
    {"id": "edu_market", "modality": "app", "scenes": ("home",),
     "texts": (("短信", "106388", "【北大名师】考研冲刺班报名立减 2000，扫码进群领取资料。"),
               ("APP推送", "作业帮", "本周直播课免费听，点击预约，提分从今晚开始。"),
               ("短信", "106222", "【学历提升】在职本科报名截止本周，名额有限，加微信咨询。"))},
    {"id": "live_shop", "modality": "app", "scenes": ("home", "night_market"),
     "texts": (("抖音", "直播间", "您关注的主播正在直播：三折抢茅台，最后 100 单！"),
               ("淘宝", "店铺", "您收藏的商品降价了！满 199 减 30，今晚 8 点开抢。"),
               ("快手", "主播", "开播啦！今天全场福利价，前 50 名下单送赠品。"))},
    {"id": "group_memes", "modality": "app", "scenes": ("home", "office"),
     "texts": (("微信", "家族群", "[表情][表情][表情] 哈哈哈笑死我了 666666"),
               ("微信", "同事群", "早上好！[太阳][微笑] 元气满满的一天开始啦"),
               ("微信", "同学群", "收到收到，@所有人 明天记得带材料，队伍已接龙报名。"))},
    {"id": "job_market", "modality": "app", "scenes": ("home", "office"),
     "texts": (("APP推送", "BOSS直聘", "有 5 个新职位匹配您的简历，点击查看薪资详情。"),
               ("短信", "106688", "【猎头】年薪 40 万岗位虚位以待，回复 1 了解详情。"),
               ("微信", "中介小王", "哥，房子看好了吗？这周有特价房源，随时带看。"))},
    {"id": "wealth_market", "modality": "app", "scenes": ("home",),
     "texts": (("微信", "理财群", "内部消息：这只票下周必拉，跟上操作，稳健翻倍！"),
               ("APP推送", "财富顾问", "年化 12% 稳健理财，限时开放申购，点击了解。"),
               ("短信", "106999", "【荐股】添加老师微信，免费领取明日涨停名单，名额有限。"))},
    {"id": "drama_feed", "modality": "app", "scenes": ("home", "commute"),
     "texts": (("APP推送", "热搜", "热搜：某演员官宣结婚，评论区已炸锅。"),
               ("APP推送", "追剧", "您追的剧更新了第 12 集，会员抢先看。"),
               ("APP推送", "游戏", "体力已满，今日签到可领限定皮肤，速来领取。"))},

    # ---- dialogue：口头禅 / 吹牛 / 玩笑 / 自言自语（含对抗陷阱） ----
    {"id": "boast_drunk", "modality": "dialogue", "scenes": ("night_market", "home"),
     "trap": True, "tone": "醉酒吹牛",
     "texts": ("老子早晚当上 CEO，把那条街都买下来！", "下个月我就收购那家公司，全款拿下，你们等着看。",
               "我一个电话就能搞定董事长，这算什么事儿。")},
    {"id": "vent_idiom", "modality": "dialogue", "scenes": ("office", "home", "commute"),
     "trap": True, "tone": "口头禅宣泄",
     "texts": ("烦死了，再加班我就不活了。", "累死了，我要是猝死在工位上算不算工伤。",
               "这破班我是一天也上不下去了，想跳楼的心都有了。")},
    {"id": "self_mutter", "modality": "dialogue", "scenes": ("home", "mall", "street"),
     "texts": ("鸡蛋、牛奶、酱油……还差一卷纸，别忘买。", "钥匙放哪儿了，回头得买个挂钩。",
               "明天记得把快递取了，别忘了给老妈打电话。")},
    {"id": "weather_chat", "modality": "dialogue", "scenes": ("commute", "office", "street"),
     "texts": ("今天天真热，秋老虎还没走呢。", "预报说明天有雨，记得带伞。",
               "这天气说变就变，出门多穿件外套。")},
    {"id": "joke_borrow", "modality": "dialogue", "scenes": ("home", "office", "mall"),
     "trap": True, "tone": "玩笑调侃",
     "texts": ("借我一百万呗，我请你吃泡面！", "你请我吃饭吧，我这个月吃土了，哈哈。",
               "要是我中彩票了，分你一半，先借我十块买一张。")},
    {"id": "irony_vent", "modality": "dialogue", "scenes": ("office", "home", "street"),
     "trap": True, "tone": "反讽吐槽",
     "texts": ("真是我的福气，赶在周五下班前接到甲方电话。", "感谢领导画的大饼，我吃饱了。",
               "优秀，报销单又打回来了，第三次了。")},
    {"id": "drama_comment", "modality": "dialogue", "scenes": ("home", "commute"),
     "texts": ("这剧男主太气人了，我要弃剧。", "昨晚那场比赛看得我血压都高了，裁判太黑。",
               "刷了半宿短视频，眼睛都花了。")},

    # ---- voiceprint：一次性杂散人声（必须剔除的推销/路人/服务人员） ----
    {"id": "promoter_voice", "modality": "voiceprint", "scenes": ("mall", "street", "station"),
     "texts": ("促销主播：办卡吗今天有活动", "扫码地推：扫码送纸巾要不要", "试用装导购：小姐姐免费体验一下")},
    {"id": "courier_voice", "modality": "voiceprint", "scenes": ("home", "office", "street"),
     "texts": ("快递员：您的快递放驿站了", "外卖员：餐放门口了麻烦开下门", "跑腿小哥：东西已送达，麻烦确认")},
    {"id": "passerby_voice", "modality": "voiceprint", "scenes": ("street", "commute", "mall"),
     "texts": ("路人问路：请问地铁站怎么走", "发单页的：健身了解一下", "游客：这儿能拍照吗")},
    {"id": "service_voice", "modality": "voiceprint", "scenes": ("mall", "hospital", "gym"),
     "texts": ("收银员：一共 38 块 6，扫码还是现金", "客服：您好，请问有什么可以帮您", "前台：请出示一下预约码")},
    {"id": "crowd_voice", "modality": "voiceprint", "scenes": ("station", "mall", "street"),
     "texts": ("（人声模糊，仅 0.8 秒碎片）", "（两人说笑，内容不可辨）", "（远处广播员声音，混响严重）")},

    # ---- sensor：日常躯体噪声（正常波动，必须剪枝） ----
    {"id": "step_vibration", "modality": "sensor", "scenes": ("commute", "street", "home", "office", "mall", "station", "night_market"),
     "texts": ("50Hz 碎步晃动与抬腕动作，无冲击特征", "步态稳定，加速度峰值 1.4g，属日常行走")},
    {"id": "typing_tremor", "modality": "sensor", "scenes": ("office", "home"),
     "texts": ("指尖敲击桌面导致的微振动，峰值 1.1g", "鼠标滑动与键盘敲击引起的周期性抖动")},
    {"id": "subway_bump", "modality": "sensor", "scenes": ("commute", "station", "street", "night_market"),
     "texts": ("地铁车厢启停颠簸，峰值 2.1g，无跌倒语义", "公交急刹造成前倾摆动，峰值 2.6g")},
    {"id": "normal_hr", "modality": "sensor", "scenes": ("home", "office", "commute", "street", "hospital", "school", "mall", "station", "construction", "night_market", "gym"),
     "texts": ("日间心率平稳波动 62~84bpm，未见异常", "夜间窦性心律 56~64bpm，无早搏")},
    {"id": "chair_posture", "modality": "sensor", "scenes": ("office", "home", "school", "hospital", "gym"),
     "texts": ("落座与起身体动，加速度峰值 1.3g，无跌倒特征", "久坐后调整坐姿产生的缓慢倾角变化")},
    {"id": "pocket_shake", "modality": "sensor", "scenes": ("commute", "street", "mall", "night_market", "home"),
     "texts": ("口袋里手环随身体摆动，加速度峰值 1.6g", "拎物行走导致的手部摆动噪声")},
    {"id": "stair_step", "modality": "sensor", "scenes": ("home", "office", "station", "hospital", "school", "mall"),
     "texts": ("上下楼梯的周期性冲击，峰值 1.9g，节奏稳定", "扶梯站立时的轻微起伏，无冲击语义")},
    {"id": "sleep_turn", "modality": "sensor", "scenes": ("home", "hospital", "school"),
     "texts": ("夜间翻身与床架轻微振动，持续 12 秒", "睡眠体动导致的微弱加速度变化")},
    {"id": "phone_vibration", "modality": "sensor", "scenes": ("home", "office", "commute", "street", "mall"),
     "texts": ("手机来电震动传导至腕部，频率约 12Hz，持续 6 秒", "消息提醒引起的短暂腕部抖动")},
    {"id": "bag_swing", "modality": "sensor", "scenes": ("street", "mall", "night_market", "station"),
     "texts": ("拎手提袋摆臂带来的规律性加速度波动", "背包肩带晃动引起的躯干微震")},
    {"id": "elevator_ride", "modality": "sensor", "scenes": ("office", "hospital", "mall", "station"),
     "texts": ("电梯启停带来的垂直向加速度变化，峰值 1.2g", "轿厢运行中的持续低幅振动")},
    {"id": "cough_motion", "modality": "sensor", "scenes": ("home", "hospital", "office"),
     "texts": ("咳嗽引起的短时躯干抖动，无跌倒特征", "打喷嚏导致的瞬时加速度尖峰，峰值 1.5g")},
    {"id": "wrist_adjust", "modality": "sensor", "scenes": ("home", "office", "school", "hospital", "mall", "street"),
     "texts": ("摘戴与转动手环造成的姿态突变，无冲击特征", "调整表带松紧引起的短时信号漂移")},
    {"id": "static_idle", "modality": "sensor", "scenes": ("home", "office", "hospital", "gym"),
     "texts": ("静坐办公期间加速度接近 1.0g 基线", "卧床休息时无位移、无冲击")},
)


# ---------------------------------------------------------------------------
# 五、槽位池与渲染
# ---------------------------------------------------------------------------

APP_NAMES: Tuple[str, ...] = (
    "微信", "短信", "招商银行App", "钉钉", "美团", "支付宝", "高德地图", "医院App", "快递100", "HR系统",
)
CONTEXT_SCENES: Tuple[str, ...] = (
    "独处自述", "与家人对话", "与同事对话", "酒后闲聊", "通勤途中", "深夜失眠", "通话录音",
)
EMOTIONAL_TONES: Tuple[str, ...] = (
    "疲惫", "焦虑", "平静", "愤怒", "委屈", "勉强支撑", "低落", "警觉", "麻木",
)
CASES: Tuple[str, ...] = ("借款合同", "装修合同", "抚养权", "买卖合同", "劳动争议", "相邻关系", "服务合同")
DEPTS: Tuple[str, ...] = ("心内科", "内分泌科", "肿瘤内科", "骨科", "消化内科", "呼吸内科")
DRUGS: Tuple[str, ...] = ("二甲双胍 0.5g", "美托洛尔 25mg", "阿司匹林 100mg", "缬沙坦 80mg", "布洛芬缓释胶囊")
DISHES: Tuple[str, ...] = ("鲅鱼饺子", "小炒黄牛肉", "菌菇汤", "牛肉面", "麻辣香锅", "清蒸鲈鱼")
ACOUSTIC_ENVS: Tuple[str, ...] = (
    "A01_居家安静", "A02_写字楼键盘", "A03_地铁车厢", "A04_商场嘈杂",
    "A05_医院走廊", "A06_工地轰鸣", "A07_街边风雨", "A08_夜间卧室",
)
LINGUISTIC_TAGS: Tuple[str, ...] = (
    "普通话@清晰", "方言:川渝@转写", "方言:东北@转写", "口音:粤普@转写", "低声气声@ASR弱", "电话窄带@转写",
)
TIMES: Tuple[str, ...] = (
    "07:12", "07:48", "08:26", "09:05", "09:47", "10:31", "11:18", "12:04", "12:52", "13:37",
    "14:21", "15:08", "15:54", "16:40", "17:26", "18:12", "19:03", "19:49", "20:35", "21:18",
    "22:02", "22:41", "23:09", "23:28",
)
SCENE_LABELS: Mapping[str, str] = {
    "home": "家中", "office": "单位", "commute": "通勤路上", "mall": "商圈", "hospital": "医院",
    "school": "学校", "construction": "工地", "street": "街头", "night_market": "夜市",
    "gym": "健身房", "station": "车站",
}


def quota_sequence(quota: Sequence[Tuple[str, int]], count: int, rnd: random.Random) -> List[str]:
    """按配额把类别铺满 count 个位置，再用确定性洗牌打散（配额精确、位置随机）。"""
    total = sum(weight for _, weight in quota)
    items: List[str] = []
    for i in range(count):
        pos = (i * total) / count
        acc = 0
        for key, weight in quota:
            if pos < acc + weight:
                items.append(key)
                break
            acc += weight
        else:  # pragma: no cover - 浮点边界兜底
            items.append(quota[-1][0])
    rnd.shuffle(items)
    return items


def weighted_sequence(values: Sequence[Any], count: int, rnd: random.Random) -> List[Any]:
    """把取值序列按比例铺满 count 个位置（用于事实条数这类非二元配额）。"""
    total = len(values)
    items = [values[min(total - 1, int((i * total) / count))] for i in range(count)]
    rnd.shuffle(items)
    return items


def build_slots(persona: Mapping[str, Any], rnd: random.Random) -> Dict[str, Any]:
    """题目级槽位：人名、金额、日期、机构等全部在此绑定一次，全题一致。"""
    contacts = list(persona["contacts"])

    def pick_contact(offset: int) -> Tuple[str, str]:
        item = contacts[(rnd.randrange(len(contacts)) + offset) % len(contacts)]
        return item["name"], item["role"]

    contact, role = pick_contact(0)
    contact2, role2 = pick_contact(1)
    kin = persona["kinship"]
    colleague = persona["colleague"]
    amount, amount2 = rnd.sample(AMOUNTS, 2)
    date, date2 = rnd.sample(DATES, 2)
    place, place2 = rnd.sample(PLACES, 2)
    return {
        "name": persona["name"], "job": persona["job"], "city": persona["city"],
        "pet": persona["pet"], "chronic": persona["chronic"], "family": persona["family"],
        "contact": contact, "role": role, "contact2": contact2, "role2": role2,
        "kin": kin["name"], "kinrole": kin["role"],
        "colleague": colleague["name"], "colleaguerole": colleague["role"],
        "amount": amount, "amount2": amount2, "date": date, "date2": date2,
        "place": place, "place2": place2,
        "bank": rnd.choice(BANKS), "hospital": rnd.choice(HOSPITALS), "org": rnd.choice(ORGS),
        "company": f"{rnd.choice(COMPANY_PREFIX)}有限公司",
        "exam_org": rnd.choice(EXAM_ORGS), "airline": rnd.choice(AIRLINES),
        "court": rnd.choice(COURTS), "arbitration": rnd.choice(ARBITRATION),
        "detect_org": rnd.choice(DETECT_ORGS), "property_org": rnd.choice(PROPERTY_ORGS),
        "dept": rnd.choice(DEPTS), "drug": rnd.choice(DRUGS), "dish": rnd.choice(DISHES),
        "case": rnd.choice(CASES), "tail": f"{rnd.randrange(1000, 9999)}",
        "code": f"{rnd.choice('ABCD')}-{rnd.randrange(1, 9)}-{rnd.randrange(1000, 9999)}",
        "balance": f"{rnd.randrange(1, 90)},{rnd.randrange(100, 999)}",
        "glu": rnd.choice(("11.6", "14.2", "16.8", "19.4")),
        "time": rnd.choice(("22:38", "23:12", "23:41", "21:56", "02:14")),
        "g": round(rnd.uniform(9.0, 12.5), 1), "still": rnd.choice((120, 180, 240, 300)),
        "hr": rnd.choice((118, 124, 128, 132)), "mins": rnd.choice((18, 26, 34, 42, 55)),
        "frags": rnd.choice((24, 31, 38, 45)), "cos": round(rnd.uniform(0.90, 0.97), 2),
        "days": rnd.choice((12, 21, 30)), "n": rnd.choice((5, 6, 7, 9)), "drop": round(rnd.uniform(9.5, 15.0), 1),
    }


def render_signal(signal: Mapping[str, Any], slots: Mapping[str, Any], rnd: random.Random) -> Dict[str, Any]:
    """把一条信号渲染成：证据文本 + 标准事实 + 实体锚 + 方向词簇（公平性由断言兜底）。"""
    local = dict(slots)
    patch = signal.get("sensor_patch")
    if isinstance(patch, Mapping):
        for key in ("heart_rate_bpm", "pvc_burst_count", "baro_hpa", "stillness_seconds"):
            if key in patch:
                local[key] = patch[key]
        if patch.get("stillness_seconds"):
            local["still"] = patch["stillness_seconds"]
        if patch.get("pvc_burst_count"):
            local["n"] = patch["pvc_burst_count"]
        if patch.get("heart_rate_bpm"):
            local["hr"] = patch["heart_rate_bpm"]
    if signal["id"] == "BARO_STORM_DROP":
        local["drop"] = 12.4
    if signal["id"] == "FALL_IMPACT_FAKED":
        local["g"] = round(rnd.uniform(1.05, 1.35), 2)
    if signal["id"] == "FALL_IMPACT":
        local["g"] = round(rnd.uniform(9.2, 12.8), 1)
        local["still"] = rnd.choice((120, 180, 240, 300))
    if signal["id"] in ("VOICE_BINDING_USER", "VOICE_BINDING_KEY_CONTACT"):
        local["cos"] = round(rnd.uniform(0.92, 0.98), 2)
        local["frags"] = rnd.choice((28, 34, 41))
        local["days"] = rnd.choice((14, 21, 30))
    if signal["id"] == "KEY_CONVERSATION_WITH_CONTACT":
        local["mins"] = rnd.choice((36, 42, 51, 63))
        local["frags"] = rnd.choice((26, 33, 40))
    if signal["id"] == "VOICE_IMPERSONATION_FRAUD":
        local["cos"] = round(rnd.uniform(0.41, 0.62), 2)
    variants = list(signal["texts"])
    start = rnd.randrange(len(variants))
    ordered = variants[start:] + variants[:start]
    keywords = tuple(signal["keywords"])
    cues = tuple(signal.get("cues", ()))
    best: Tuple[Tuple[int, int, int], str, List[str]] | None = None
    for template in ordered:
        text = template.format(**local)
        entity_values = [str(local[key]) for key in signal.get("entities", ()) if local.get(key) is not None]
        entity_values = list(dict.fromkeys(entity_values))
        hits = sum(1 for value in entity_values if value in text)
        keyword_ok = any(word in text for word in keywords)
        scored = (1 if keyword_ok else 0, 1 if hits == len(entity_values) else 0, hits)
        if best is None or scored > best[0]:
            best = (scored, text, entity_values)
        if keyword_ok and hits == len(entity_values):
            break
    assert best is not None, f"信号 {signal['id']} 缺少证据文本"
    score, text, entity_values = best
    # 公平性纪律：方向词簇必须在证据文本中可读，锚点实体必须可溯源（不可溯源的锚点一律剔除）
    entities = [value for value in entity_values if value in text]
    core = signal["fact"].format(**local)
    return {
        "signal": signal, "text": text, "core": core, "entities": entities,
        "keywords": keywords, "cues": cues, "keyword_hit": score[0] == 1, "slots": local,
    }


# ---------------------------------------------------------------------------
# 六、选题与组装（一道题 = 一个人的一天）
# ---------------------------------------------------------------------------

def _needs_ok(signal: Mapping[str, Any], persona: Mapping[str, Any]) -> bool:
    needs = signal.get("needs") or ()
    return (not needs) or persona["job_kind"] in needs


def pick_signals(focus: str, arc: Mapping[str, Any], persona: Mapping[str, Any],
                 fact_n: int, rnd: random.Random) -> List[Dict[str, Any]]:
    """主事实必须落在配额指定的数据流上，其余事实换流换维度（跨维度冲突）。"""
    used_ids: set[str] = set()
    used_dims: set[str] = set()
    used_modalities: set[str] = set()
    prefer_dims = tuple(arc["dims"])
    chosen: List[Dict[str, Any]] = []

    def choose(modality: str, dims_pref: Sequence[str]) -> Dict[str, Any] | None:
        pool = [s for s in SIGNALS if s["modality"] == modality and s["id"] not in used_ids and _needs_ok(s, persona)]
        if not pool:
            pool = [s for s in SIGNALS if s["modality"] == modality and s["id"] not in used_ids]
        if not pool:
            return None
        preferred = [s for s in pool if s["dim"] in dims_pref] or pool
        fresh = [s for s in preferred if s["dim"] not in used_dims] or preferred
        return rnd.choice(fresh)

    primary = choose(focus, prefer_dims)
    if primary is None:
        for fallback in ("mic", "app", "dialogue", "sensor", "voiceprint"):
            primary = choose(fallback, prefer_dims)
            if primary is not None:
                break
    if primary is None:  # pragma: no cover - 目录恒非空
        raise RuntimeError("信号目录为空，无法生成题目")
    chosen.append(primary)
    used_ids.add(primary["id"])
    used_dims.add(primary["dim"])
    used_modalities.add(primary["modality"])

    while len(chosen) < fact_n:
        modalities = [m for m in ("mic", "app", "dialogue", "sensor", "voiceprint") if m not in used_modalities]
        options = [s for s in (choose(m, prefer_dims) for m in modalities) if s is not None]
        if not options:
            break
        cross_dim = [s for s in options if s["dim"] not in used_dims] or options
        nxt = rnd.choice(cross_dim)
        chosen.append(nxt)
        used_ids.add(nxt["id"])
        used_dims.add(nxt["dim"])
        used_modalities.add(nxt["modality"])
    return chosen


def _junk_texts(modality: str, scene: str, count: int, rnd: random.Random,
                used: List[str], force_trap: bool = False) -> List[Dict[str, Any]]:
    """按场景取垃圾模板（避免同题内重复，必要时插入对抗陷阱）。"""
    pool = [f for f in JUNK_FAMILIES if f["modality"] == modality]
    scene_pool = [f for f in pool if scene in f.get("scenes", ())] or pool
    traps = [f for f in scene_pool if f.get("trap")]
    order: List[Dict[str, Any]] = []
    if force_trap and traps:
        order.append(rnd.choice(traps))
    shuffled = list(scene_pool)
    rnd.shuffle(shuffled)
    order.extend(shuffled)
    out: List[Dict[str, Any]] = []
    i = 0
    while len(out) < count:
        family = order[i % len(order)]
        i += 1
        texts = [t for t in family["texts"] if t not in used]
        text = rnd.choice(texts or list(family["texts"]))
        used.append(text)
        out.append({"family": family, "text": text})
    return out


def _junk_payload(item: Mapping[str, Any]) -> Tuple[str, str, str]:
    """把垃圾模板归一为 (正文, 渠道, 发送方)：兼容 (渠道, 发送方, 正文) 写法。"""
    text = item["text"]
    if isinstance(text, (tuple, list)):
        parts = [str(part) for part in text]
        return parts[-1], parts[0], (parts[1] if len(parts) > 2 else "")
    return str(text), "", ""


def build_question(index: int, focus_list: Sequence[str], diff_list: Sequence[str],
                   factn_list: Sequence[int], seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """构造第 index 道题（问题 + 标答）。"""
    rnd = random.Random(seed * 1_000_003 + index)
    qnum = index + 1
    qid = f"Q_{GENERATOR_AGENT}_{qnum:05d}"
    persona = build_persona(index)
    arc = ARCS[index % len(ARCS)]
    focus = focus_list[index]
    difficulty = diff_list[index]
    fact_n = int(factn_list[index])
    signals = pick_signals(focus, arc, persona, fact_n, rnd)
    slots = build_slots(persona, rnd)
    rendered = [render_signal(sig, slots, rnd) for sig in signals]
    scene = arc_scene(arc, persona, rnd)

    event_times = sorted(rnd.sample(TIMES, min(len(TIMES), 6 + len(rendered))))
    signal_times = event_times[: len(rendered)]
    junk_times = list(TIMES)

    mic: List[Dict[str, Any]] = []
    app: List[Dict[str, Any]] = []
    dialogue: List[Dict[str, Any]] = []
    vp_speakers: List[Dict[str, Any]] = []
    junk_ids: List[str] = []
    facts: List[Dict[str, Any]] = []
    used_texts: List[str] = []
    trap_tag = "NONE"
    mic_i = app_i = dia_i = vp_i = fact_i = 0
    sensor_is_signal = False
    sensor_packet: Dict[str, Any] = {}

    for order, item in enumerate(rendered):
        sig = item["signal"]
        modality = sig["modality"]
        time = signal_times[order]
        item["_time"] = time
        if modality == "mic":
            mic_i += 1
            sid = f"{qnum:05d}-m{mic_i:02d}"
            mic.append({
                "snippet_id": sid, "speaker_id": "S01_user", "text": item["text"],
                "ambient_noise_db": rnd.randrange(44, 56), "snr_db": round(rnd.uniform(15.0, 23.0), 1),
                "duration_s": rnd.randrange(9, 26), "scene": "foreground_dialogue",
                "is_background_chatter": False, "asr_confidence": round(rnd.uniform(0.88, 0.97), 2),
                "is_junk": False, "timestamp": time,
            })
            source_id = sid
        elif modality == "app":
            app_i += 1
            sid = f"{qnum:05d}-a{app_i:02d}"
            app.append({
                "msg_id": sid, "app": SIGNAL_APP_CHANNELS.get(sig["intent"]) or rnd.choice(APP_NAMES),
                "sender": _signal_sender(sig, item["slots"]),
                "content": item["text"], "timestamp": time, "is_junk": False,
            })
            source_id = sid
        elif modality == "dialogue":
            dia_i += 1
            sid = f"{qnum:05d}-d{dia_i:02d}"
            dialogue.append({
                "utterance_id": sid, "raw_speech": item["text"],
                "context_scene": rnd.choice(CONTEXT_SCENES), "emotional_tone": rnd.choice(EMOTIONAL_TONES),
                "timestamp": time, "is_junk": False,
            })
            source_id = sid
        elif modality == "voiceprint":
            vp_i += 1
            sid = f"{qnum:05d}-vp{vp_i:02d}"
            entry: Dict[str, Any] = {
                "spk_id": sid, "is_junk": False, "timestamp": time,
                "sample_text": item["text"],
            }
            if sig["id"] == "VOICE_BINDING_USER":
                entry.update({"cluster_label": "USER_SELF", "role": "佩戴者本人",
                              "cosine_to_enrolled_user": round(rnd.uniform(0.94, 0.99), 2),
                              "n_fragments": item["slots"]["frags"], "recurrence_days_30d": item["slots"]["days"]})
                slots["user_speaker_id"] = sid
            elif sig["id"] == "VOICE_BINDING_KEY_CONTACT":
                entry.update({"cluster_label": "KEY_CONTACT", "role": f"{item['slots']['role']}",
                              "cosine_to_enrolled_user": round(rnd.uniform(0.86, 0.95), 2),
                              "cosine_to_contact_bank": round(rnd.uniform(0.88, 0.96), 2),
                              "n_fragments": item["slots"]["frags"], "recurrence_days_30d": item["slots"]["days"]})
            elif sig["id"] == "KEY_CONVERSATION_WITH_CONTACT":
                entry.update({"cluster_label": "KEY_CONTACT", "role": f"{item['slots']['role']}",
                              "cosine_to_contact_bank": round(rnd.uniform(0.86, 0.95), 2),
                              "n_fragments": item["slots"]["frags"], "total_talk_minutes": item["slots"]["mins"],
                              "recurrence_days_30d": item["slots"]["days"]})
            else:  # VOICE_IMPERSONATION_FRAUD
                entry.update({"cluster_label": "SPK_IMPOSTOR", "role": f"冒充{item['slots']['kin']}的陌生来电",
                              "cosine_to_enrolled_user": round(rnd.uniform(0.15, 0.4), 2),
                              "cosine_to_claimed_identity": item["slots"]["cos"],
                              "n_fragments": rnd.randrange(2, 6), "recurrence_days_30d": 0})
            vp_speakers.append(entry)
            source_id = sid
        else:  # sensor
            sensor_is_signal = True
            sid = f"{qnum:05d}-sen"
            patch = sig.get("sensor_patch") or {}
            g_series = list(patch.get("g_series", (1.0, 1.0, 1.0, 1.0)))
            if patch.get("g_series_peak") and item["slots"].get("g"):
                peak_at = max(range(len(g_series)), key=lambda i: g_series[i])  # 波形峰值与文案数值必须一致
                g_series[peak_at] = float(item["slots"]["g"])
            sensor_packet = {
                "packet_id": sid, "sampling_hz": 50,
                "raw_imu_g_force": g_series,
                "heart_rate_bpm": patch.get("heart_rate_bpm", item["slots"]["hr"]),
                "pvc_burst_count": patch.get("pvc_burst_count", 0),
                "baro_hpa": patch.get("baro_hpa", 1008.6),
                "motion_state": patch.get("motion_state", "STEADY_WALK"),
                "sensor_mode": patch.get("sensor_mode", "S00_DAILY"),
                "stillness_seconds": patch.get("stillness_seconds", 0),
                "steps": rnd.randrange(2200, 15800), "sleep_hours": round(rnd.uniform(4.4, 8.2), 1),
                "spo2_min": rnd.randrange(88, 99), "text": item["text"], "timestamp": time,
                "is_junk": False,
            }
            if patch.get("stillness_seconds"):
                sensor_packet["post_impact_immobility_s"] = patch["stillness_seconds"]
            source_id = sid
        fact_i += 1
        facts.append({
            "fact_id": f"{qid}-F{fact_i}", "dimension_id": sig["dim"], "semantic_intent": sig["intent"],
            "anchor_entities": item["entities"], "directional_keywords": list(item["keywords"]),
            "core_content": item["core"], "source_ref_id": source_id,
            "confidence": round(rnd.uniform(0.9, 0.99), 2),
        })

    # ---- 垃圾填充：目标 junk >= 19 * signals（垃圾占比 >= 95%）----
    target_junk = JUNK_PER_SIGNAL * fact_n + rnd.randint(0, 2)
    extra_sensor = 0
    if not sensor_is_signal:
        sensor_packet = _benign_sensor_packet(qnum, persona, rnd)
        junk_ids.append(sensor_packet["packet_id"])
    # 传感器噪声片段优先承担剪枝配额（最贴近“50Hz 碎步/打字震动/地铁颠簸”的真实噪声）
    extra_sensor = min(4, max(0, target_junk - len(junk_ids) - 8))
    sensor_junk_n = rnd.randint(2, 3) + extra_sensor
    sensor_frags = _sensor_junk_fragments(qnum, scene, sensor_junk_n, rnd, used_texts)
    for frag in sensor_frags:
        junk_ids.append(frag["fragment_id"])
    sensor_packet["noise_fragments"] = sensor_frags
    remaining = max(0, target_junk - len(junk_ids))
    counts = {"voiceprint": min(5, remaining), "app": 0, "mic": 0, "dialogue": 0}
    remaining -= counts["voiceprint"]
    rotation = ("app", "voiceprint", "mic", "app", "dialogue", "mic")
    i = 0
    while remaining > 0:
        counts[rotation[i % len(rotation)]] += 1
        i += 1
        remaining -= 1

    force_trap = difficulty == "ADVERSARIAL"
    mic_junk = _junk_texts("mic", scene, counts["mic"], rnd, used_texts)
    app_junk = _junk_texts("app", scene, counts["app"], rnd, used_texts)
    dia_junk = _junk_texts("dialogue", scene, counts["dialogue"], rnd, used_texts, force_trap=force_trap)
    vp_junk = _junk_texts("voiceprint", scene, counts["voiceprint"], rnd, used_texts)

    if force_trap:
        for item in dia_junk:
            if item["family"].get("trap"):
                trap_tag = item["family"]["id"]
                break
        else:
            trap_tag = "TRAP_DECLARED"
    declared_p = rnd.uniform(0.55, 0.75)
    for item in mic_junk:
        mic_i += 1
        sid = f"{qnum:05d}-m{mic_i:02d}"
        entry = {"snippet_id": sid, "text": item["text"],
                 "ambient_noise_db": rnd.randrange(58, 89), "snr_db": round(rnd.uniform(1.5, 9.0), 1),
                 "is_background_chatter": True}
        if rnd.random() < declared_p:
            entry["is_junk"] = True
        elif carrier_scene_hint(scene) == "outdoor":
            entry["acoustic_topology"] = "环境噪声"
        mic.append(entry)
        junk_ids.append(sid)
    for item in app_junk:
        app_i += 1
        sid = f"{qnum:05d}-a{app_i:02d}"
        content, channel, sender = _junk_payload(item)
        entry = {"msg_id": sid, "app": channel or rnd.choice(APP_NAMES), "content": content}
        if channel and sender:
            entry["sender"] = sender
        if rnd.random() < declared_p:
            entry["is_junk"] = True
        app.append(entry)
        junk_ids.append(sid)
    for item in dia_junk:
        dia_i += 1
        sid = f"{qnum:05d}-d{dia_i:02d}"
        entry = {"utterance_id": sid, "raw_speech": item["text"]}
        if item["family"].get("trap"):
            entry["emotional_tone"] = item["family"].get("tone") or rnd.choice(EMOTIONAL_TONES)
        if rnd.random() < declared_p:
            entry["is_junk"] = True
        dialogue.append(entry)
        junk_ids.append(sid)
    for item in vp_junk:
        vp_i += 1
        sid = f"{qnum:05d}-vp{vp_i:02d}"
        entry = {"spk_id": sid, "n_fragments": rnd.randrange(1, 6),
                 "cosine_to_enrolled_user": round(rnd.uniform(0.05, 0.34), 3),
                 "sample_text": item["text"][:16]}
        if rnd.random() < declared_p:
            entry["is_junk"] = True
        vp_speakers.append(entry)
        junk_ids.append(sid)

    question = {
        "question_id": qid, "generator_agent": GENERATOR_AGENT,
        "timestamp_utc": _timestamp(index),
        "difficulty": difficulty,
        "persona_id": persona["persona_id"], "persona_tag": persona["tag"],
        "persona": {k: persona[k] for k in ("name", "gender", "age", "city", "job", "family", "chronic")},
        "sensor_mode": sensor_packet.get("sensor_mode", "S00_DAILY"),
        "acoustic_env": ACOUSTIC_ENVS[(index * 3 + 1) % len(ACOUSTIC_ENVS)],
        "linguistic_tag": LINGUISTIC_TAGS[(index * 5 + 2) % len(LINGUISTIC_TAGS)],
        "trap_tag": trap_tag,
        "cleaned_daily_stream": _daily_stream(persona, focus, rendered, mic, vp_speakers, app, dialogue,
                                              sensor_packet, facts, junk_ids, index),
        "sensor_stream": sensor_packet,
        "mic_stream": mic,
        "voiceprint_cluster": {
            "user_speaker_id": slots.get("user_speaker_id", ""),
            "n_detected_speakers": len(vp_speakers),
            "speaker_count": len(vp_speakers),
            "detected_speakers": vp_speakers,
        },
        "app_message_stream": app,
        "user_dialogue_stream": dialogue,
        "directional_ground_truth": _directional_ground_truth(persona, arc, focus, rendered, difficulty),
    }
    ground_truth = {
        "question_id": qid, "generator_agent": GENERATOR_AGENT,
        "ground_truth_facts": facts,
        "ground_truth_junk_ids": junk_ids,
    }
    return question, ground_truth


def arc_scene(arc: Mapping[str, Any], persona: Mapping[str, Any], rnd: random.Random) -> str:
    """按人设岗位取当日主场景（垃圾噪声要与场景自洽）。"""
    job_kind = persona["job_kind"]
    mapping = {
        "医院": "hospital", "学校": "school", "幼儿园": "school", "高校": "school",
        "交通": "commute", "配送": "street", "工地": "construction", "物流": "station",
        "公司": "office", "机关": "office", "银行": "office", "写字楼": "office",
        "商超": "mall", "门店": "mall", "餐饮": "night_market", "直播基地": "home",
        "社区": "street", "派出所": "street", "地铁": "station", "供电所": "street",
        "工厂": "construction", "农村": "street", "家政": "home", "消防站": "street",
        "药店": "hospital", "律所": "office", "物业": "street",
    }
    base = mapping.get(job_kind, rnd.choice(SCENES))
    return base if rnd.random() < 0.75 else rnd.choice(SCENES)


#: 方向 -> 通知渠道（银行短信/HR 系统/医院 App…… 与内容自洽，避免渠道错配）
SIGNAL_APP_CHANNELS: Mapping[str, str] = {
    "BANK_LARGE_TRANSFER": "短信", "FAKE_TRANSFER_COUNTER": "短信",
    "CRYPTO_PONZI_COLLAPSE": "微信", "FINANCING_BET_FAILURE": "短信",
    "LAB_CRITICAL_VALUE": "医院App", "DIABETIC_KETOACIDOSIS": "医院App",
    "MEDICAL_APPOINTMENT": "医院App", "MEDICATION_REMINDER": "医院App",
    "LAYOFF_DISPUTE": "HR系统", "NON_COMPETE_2M": "HR系统",
    "CONTRACT_SIGNING": "钉钉", "EXAM_CIVIL_SERVICE": "短信",
    "COURT_SUMMONS": "短信", "CUSTODY_BATTLE_FORGED": "短信",
    "PIPE_BACKFLOW_COMPENSATION": "微信", "TRAVEL_DISRUPTION": "短信",
    "MEAL_EVENT": "美团", "DELIVERY_EVENT": "快递100", "USED_CAR_FLOODED": "微信",
}


def _signal_sender(signal: Mapping[str, Any], slots: Mapping[str, Any]) -> str:
    """信号消息的发送方（机构名），与正文中出现的机构保持一致。"""
    intent = signal["intent"]
    table = {
        "BANK_LARGE_TRANSFER": slots.get("bank"), "FAKE_TRANSFER_COUNTER": slots.get("bank"),
        "CRYPTO_PONZI_COLLAPSE": slots.get("company"), "FINANCING_BET_FAILURE": slots.get("company"),
        "LAB_CRITICAL_VALUE": slots.get("hospital"), "DIABETIC_KETOACIDOSIS": slots.get("hospital"),
        "MEDICAL_APPOINTMENT": slots.get("hospital"), "MEDICATION_REMINDER": slots.get("hospital"),
        "LAYOFF_DISPUTE": slots.get("company"), "NON_COMPETE_2M": slots.get("arbitration"),
        "CONTRACT_SIGNING": slots.get("company"), "EXAM_CIVIL_SERVICE": slots.get("exam_org"),
        "COURT_SUMMONS": slots.get("court"), "CUSTODY_BATTLE_FORGED": slots.get("court"),
        "PIPE_BACKFLOW_COMPENSATION": slots.get("property_org"), "TRAVEL_DISRUPTION": slots.get("airline"),
        "MEAL_EVENT": "美团外卖", "DELIVERY_EVENT": "快递100", "USED_CAR_FLOODED": slots.get("detect_org"),
    }
    return str(table.get(intent) or slots.get("org") or "")


def _peak_hr(sensor_packet: Mapping[str, Any], index: int) -> int:
    """当日峰值心率：生理事件题取事件心率，日常题取静息 + 运动中抬升。"""
    resting = int(sensor_packet.get("heart_rate_bpm") or 72)
    state = str(sensor_packet.get("motion_state") or "")
    if state in ("FALL_IMPACT_STATIC", "SITTING_STILL") and resting > 100:
        return resting
    return min(178, resting + 26 + index % 22)


def _benign_sensor_packet(qnum: int, persona: Mapping[str, Any], rnd: random.Random) -> Dict[str, Any]:
    """无核心体征事件的日常传感器包（整包判噪）。"""
    return {
        "packet_id": f"{qnum:05d}-sen", "sampling_hz": 50,
        "raw_imu_g_force": [round(rnd.uniform(0.96, 1.06), 3) for _ in range(8)],
        "heart_rate_bpm": rnd.randrange(58, 92), "pvc_burst_count": 0,
        "baro_hpa": round(rnd.uniform(1004.0, 1016.0), 1),
        "motion_state": rnd.choice(("STEADY_WALK", "SITTING_STILL", "SLEEP_SUPINE", "GENTLE_LIE_DOWN")),
        "sensor_mode": "S00_DAILY_ROUTINE", "stillness_seconds": 0,
        "steps": rnd.randrange(1800, 16200), "sleep_hours": round(rnd.uniform(4.2, 8.4), 1),
        "spo2_min": rnd.randrange(90, 99),
        "text": "全天体征平稳，未见跌倒冲击、早搏阵发或静息心动过速", "is_junk": True,
    }


def _sensor_junk_fragments(qnum: int, scene: str, count: int, rnd: random.Random,
                           used: List[str]) -> List[Dict[str, Any]]:
    """传感器噪声碎片：优先取本场景的日常噪声，同题内不重复（池子用尽才复用）。"""
    families = [f for f in JUNK_FAMILIES if f["modality"] == "sensor"]
    scene_families = [f for f in families if scene in f.get("scenes", ())]
    ordered = [*scene_families, *[f for f in families if f not in scene_families]]
    candidates: List[Tuple[str, str]] = []
    for family in ordered:
        for text in family["texts"]:
            if text not in used:
                candidates.append((family["id"], text))
    rnd.shuffle(candidates)
    candidates.sort(key=lambda pair: 0 if pair[0] in {f["id"] for f in scene_families} else 1)
    picked = candidates[:count]
    for _, text in picked:
        used.append(text)
    if len(picked) < count:  # 极端情况下（噪声池枯竭）允许复用，保证垃圾配额不打折
        extra = [pair for pair in candidates if pair not in picked] or candidates
        while len(picked) < count:
            picked.append(extra[len(picked) % len(extra)])
    out: List[Dict[str, Any]] = []
    for k, (kind, text) in enumerate(picked, start=1):
        out.append({"fragment_id": f"{qnum:05d}-sen-f{k:02d}", "kind": kind,
                    "text": text, "is_junk": True})
    return out


def _timestamp(index: int) -> str:
    month = index % 12 + 1
    day = index % 28 + 1
    hour = 7 + (index * 3) % 16
    minute = (index * 17) % 60
    return f"2026-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+08:00"


def _daily_stream(persona: Mapping[str, Any], focus: str, rendered: Sequence[Mapping[str, Any]],
                  mic: Sequence[Mapping[str, Any]], vp: Sequence[Mapping[str, Any]],
                  app: Sequence[Mapping[str, Any]], dialogue: Sequence[Mapping[str, Any]],
                  sensor_packet: Mapping[str, Any], facts: Sequence[Mapping[str, Any]],
                  junk_ids: Sequence[str], index: int) -> Dict[str, Any]:
    """全天已清洗生活流的宏观时间轴（07:00~23:30）与体征摘要。"""
    timeline: List[Dict[str, Any]] = []
    for item in rendered:
        sig = item["signal"]
        timeline.append({"time": sig.get("_time", "—"), "modality": sig["modality"],
                         "beat": item["core"][:48]})
    timeline.append({"time": "12:30", "modality": "mic", "beat": "午间环境杂音与叫卖（铁律四剪枝）"})
    timeline.append({"time": "18:40", "modality": "app", "beat": "营销推送与群消息刷屏（铁律四剪枝）"})
    total = len(junk_ids) + len(facts)
    return {
        "window": f"{WINDOW_START}-{WINDOW_END}",
        "focus_modality": focus,
        "timeline": timeline[:3],
        "vital_summary": {
            "resting_hr_bpm": int(sensor_packet.get("heart_rate_bpm") or 72),
            "peak_hr_bpm": _peak_hr(sensor_packet, index),
            "pvc_burst_count": int(sensor_packet.get("pvc_burst_count") or 0),
            "imu_peak_g": round(max(sensor_packet.get("raw_imu_g_force") or [1.0]), 2),
            "stillness_seconds": int(sensor_packet.get("stillness_seconds") or 0),
            "baro_hpa": float(sensor_packet.get("baro_hpa") or 1010.0),
            "steps": int(sensor_packet.get("steps") or 0),
            "sleep_hours": round(float(sensor_packet.get("sleep_hours") or 0.0), 1),
            "spo2_min": int(sensor_packet.get("spo2_min") or 96),
        },
        "slice_counts": {
            "sensor": 1, "mic": len(mic), "voiceprint": len(vp), "app": len(app), "dialogue": len(dialogue),
        },
        "junk_ratio": round(len(junk_ids) / max(total, 1), 4),
    }


_DIM_CN: Mapping[str, str] = {
    DIM_HEALTH: "健康生理", DIM_SOCIAL: "人际社交", DIM_EMOTION: "情绪心理",
    DIM_FINANCE: "财务契约", DIM_CAREER: "事业行动", DIM_LIFE: "生活事件",
}


_ARC_PAIR_CN: Mapping[Tuple[str, str], str] = {
    (DIM_CAREER, DIM_SOCIAL): "事业与人际交叉压力链",
    (DIM_CAREER, DIM_FINANCE): "收入与支出双线挤压",
    (DIM_SOCIAL, DIM_HEALTH): "亲情牵动与身体警报",
    (DIM_FINANCE, DIM_SOCIAL): "钱与情同时绷紧",
    (DIM_CAREER, DIM_HEALTH): "过劳与身体代价",
    (DIM_FINANCE, DIM_EMOTION): "债务压力与情绪下滑",
    (DIM_HEALTH, DIM_EMOTION): "身体告急与硬撑",
    (DIM_LIFE, DIM_SOCIAL): "生活琐事与关系摩擦",
    (DIM_SOCIAL, DIM_CAREER): "关系与工作互相牵扯",
    (DIM_HEALTH, DIM_LIFE): "身体状态改变当日节奏",
    (DIM_CAREER, DIM_EMOTION): "职场压力与情绪代价",
}


def _arc_label(fact_by_dim: Mapping[str, Mapping[str, Any]], arc: Mapping[str, Any]) -> str:
    """当日主线标签由**实际标答事实**的维度组合生成（不照抄预设骨架，避免题面与事实错位）。"""
    dims = list(fact_by_dim.keys())
    for i in range(len(dims)):
        for j in range(len(dims)):
            if i == j:
                continue
            pair = (dims[i], dims[j])
            if pair in _ARC_PAIR_CN:
                return _ARC_PAIR_CN[pair]
    if dims:
        return f"{_DIM_CN.get(dims[0], dims[0])}主线"
    return arc["name"]


def _red_lines(dim: str, intent: str) -> List[str]:
    """每个维度的绝对偏离红线（老大铁律：反向判定一票否决）。"""
    table = {
        DIM_HEALTH: ["不得把真实危象写成'无异常'", "不得把口嗨/气话当真实症状"],
        DIM_SOCIAL: ["不得把冲突争执写成甜蜜互动", "不得把冒充背叛写成信任加深"],
        DIM_EMOTION: ["不得把崩溃绝望写成心情愉悦"],
        DIM_FINANCE: ["不得把损失违约写成进账获利"],
        DIM_CAREER: ["不得把裁员受挫写成晋升加薪"],
        DIM_LIFE: ["不得把行程中断写成顺利抵达"],
    }
    return table.get(dim, ["不得反向判定的事实"])


# 平静维度锚点：方向同义词簇 + 红线判据（防止把噪声碎片或凭空推断当成实质事件）
_QUIET_ANCHORS: Dict[str, Dict[str, Any]] = {
    "dim:health": {
        "synonyms": ("无实质变动", "身体无异常", "体征平稳", "全天无不适", "未见健康事件"),
        "red_lines": ("凭空推断出跌倒、心悸、住院、确诊等健康事件", "把背景噪声或他人症状记成佩戴者的健康事实"),
    },
    "dim:social": {
        "synonyms": ("无实质变动", "人际无事", "社交如常", "未见冲突或亲密互动", "仅常规联络"),
        "red_lines": ("凭空推断出争吵、分手、和解、背叛等人际事件", "把群消息、营销短信、路人对话当成人际关系事实"),
    },
    "dim:emotion": {
        "synonyms": ("无实质变动", "情绪平稳", "心境如常", "无明显起伏", "未见情绪事件"),
        "red_lines": ("凭空推断出崩溃、狂喜、抑郁发作等情绪事件", "把带情绪的噪声文案（广告、段子、口头禅）当成真实情绪状态"),
    },
    "dim:finance": {
        "synonyms": ("无实质变动", "财务如常", "无资金动作", "未见收支异常", "日常消费"),
        "red_lines": ("凭空推断出借贷、投资、被骗、大额支出等财务事件", "把营销/诈骗短信当成佩戴者的真实财务事实"),
    },
    "dim:career": {
        "synonyms": ("无实质变动", "工作如常", "事业无波动", "无明显职场事件", "仅日常任务"),
        "red_lines": ("凭空推断出离职、晋升、被裁、项目成败等职场事件", "把招聘广告或他人工作内容当成佩戴者的事业事实"),
    },
}


def _directional_ground_truth(persona: Mapping[str, Any], arc: Mapping[str, Any], focus: str,
                              rendered: Sequence[Mapping[str, Any]], difficulty: str) -> Dict[str, Any]:
    """老大法定格式：全局日总结 + 健康/人际/情绪/财务/事业五维方向性锚点（含同义词与红线）。"""
    fact_by_dim: Dict[str, Mapping[str, Any]] = {}
    for item in rendered:
        fact_by_dim.setdefault(item["signal"]["dim"], item)
    anchors: Dict[str, Any] = {}
    for dim in ANCHOR_DIMS:
        item = fact_by_dim.get(dim)
        if item is not None:
            anchors[dim] = {
                "core": item["core"],
                "acceptable_synonyms": list(dict.fromkeys(item["keywords"]))[:5],
                "red_lines": "；".join(_red_lines(dim, item["signal"]["intent"])),
            }
        else:
            # 老大法定：五维锚点一律同构——即使当日该维度平静，也必须给出
            #【可接受的方向同义词】与【绝对偏离的红线判据】，杜绝“无标答可依”的判分空白。
            anchors[dim] = {
                "core": f"无实质变动：当日{_DIM_CN[dim]}仅有常规日常与噪声碎片",
                "acceptable_synonyms": list(_QUIET_ANCHORS[dim]["synonyms"]),
                "red_lines": "；".join(_QUIET_ANCHORS[dim]["red_lines"]),
                "is_quiet": True,
            }
    keywords: List[str] = []
    for item in rendered:
        keywords.extend(item["keywords"])
    tones: List[str] = []
    for item in rendered:
        for tone in SIGNAL_TONES.get(item["signal"]["intent"], ()):
            if tone not in tones:
                tones.append(tone)
    if not tones:
        tones = list(arc["tones"])
    main_line = "；".join(item["core"] for item in rendered)
    global_summary = {
        "core": (f"{persona['name']}（{persona['age']}岁{persona['job']}，{persona['family']}，{persona['city']}）"
                 f"今日主线：{main_line}。情绪底色：{'、'.join(tones[:3])}。"),
        "acceptable_synonyms": list(dict.fromkeys(keywords))[:6],
        "red_lines": "不得把当日主线写成相反方向；不得虚构未在证据流中出现的事实",
    }
    others = {
        dim: {
            "core": item["core"],
            "acceptable_synonyms": list(dict.fromkeys(item["keywords"]))[:5],
            "red_lines": "；".join(_red_lines(dim, item["signal"]["intent"])),
        }
        for dim, item in fact_by_dim.items() if dim not in ANCHOR_DIMS
    }
    return {
        "global_summary": global_summary,
        **anchors,
        **({"other_dimensions": others} if others else {}),
        "focus_modality": focus,
        "arc": _arc_label(fact_by_dim, arc),
    }


# ---------------------------------------------------------------------------
# 七、结构校验（发生器自检；绝不用于自出自做答题）
# ---------------------------------------------------------------------------

def _carrier_index(question: Mapping[str, Any]) -> Dict[str, str]:
    """载体 ID -> 证据文本（用于核对标答可溯源、实体与方向词落地）。"""
    index: Dict[str, str] = {}
    sensor = question.get("sensor_stream") or {}
    if sensor.get("packet_id"):
        index[sensor["packet_id"]] = str(sensor.get("text") or "")
    for entry in sensor.get("noise_fragments") or []:
        index[str(entry.get("fragment_id") or "")] = str(entry.get("text") or "")
    for entry in question.get("mic_stream") or []:
        index[entry.get("snippet_id", "")] = str(entry.get("text") or "")
    for entry in question.get("app_message_stream") or []:
        index[entry.get("msg_id", "")] = " ".join(str(entry.get(k) or "") for k in ("app", "sender", "content"))
    for entry in question.get("user_dialogue_stream") or []:
        index[entry.get("utterance_id", "")] = str(entry.get("raw_speech") or "")
    cluster = question.get("voiceprint_cluster") or {}
    for entry in cluster.get("detected_speakers") or []:
        index[entry.get("spk_id", "")] = " ".join(
            str(entry.get(k) or "") for k in ("cluster_label", "role", "sample_text"))
    index = {k: v for k, v in index.items() if k}
    return index


def verify_bank(questions_path: str | Path, gt_path: str | Path, limit: int | None = None,
                schema: bool = True) -> Dict[str, Any]:
    """逐题核对公平性不变量（标答可溯源、垃圾占比、维度词表、载体声明）。"""
    questions = _load_jsonl(questions_path)
    gts = {row["question_id"]: row for row in _load_jsonl(gt_path)}
    problems: List[str] = []
    counters = {
        "questions": 0, "facts": 0, "junk_ids": 0, "entity_ok": 0, "keyword_ok": 0,
        "source_ok": 0, "junk_ratio_min": 1.0, "pydantic_ok": 0,
    }
    focus_counts: Dict[str, int] = {}
    difficulty_counts: Dict[str, int] = {}
    fact_counts: Dict[int, int] = {}
    modality_fragments: Dict[str, int] = {}
    for i, question in enumerate(questions):
        if limit is not None and i >= limit:
            break
        qid = question.get("question_id")
        counters["questions"] += 1
        gt = gts.get(qid)
        if gt is None:
            problems.append(f"{qid}: 缺少标答记录")
            continue
        facts = gt.get("ground_truth_facts") or []
        junk = list(gt.get("ground_truth_junk_ids") or [])
        counters["facts"] += len(facts)
        counters["junk_ids"] += len(junk)
        focus = (question.get("cleaned_daily_stream") or {}).get("focus_modality")
        focus_counts[focus] = focus_counts.get(focus, 0) + 1
        difficulty = question.get("difficulty")
        difficulty_counts[difficulty] = difficulty_counts.get(difficulty, 0) + 1
        fact_counts[len(facts)] = fact_counts.get(len(facts), 0) + 1
        for key in ("mic_stream", "app_message_stream", "user_dialogue_stream"):
            modality_fragments[key] = modality_fragments.get(key, 0) + len(question.get(key) or [])
        modality_fragments["voiceprint"] = modality_fragments.get("voiceprint", 0) + len(
            (question.get("voiceprint_cluster") or {}).get("detected_speakers") or [])
        modality_fragments["sensor"] = modality_fragments.get("sensor", 0) + 1

        index = _carrier_index(question)
        if len(index) != len(set(index)):
            problems.append(f"{qid}: 载体 ID 重复")
        source_ids = {fact.get("source_ref_id") for fact in facts}
        for fact in facts:
            sid = fact.get("source_ref_id")
            text = index.get(sid or "")
            if text is None:
                problems.append(f"{qid}: 标答事实 {fact.get('fact_id')} 的载体 {sid} 不存在")
                continue
            counters["source_ok"] += 1
            missing = [e for e in fact.get("anchor_entities") or [] if e and e not in text]
            if missing:
                problems.append(f"{qid}: 事实 {fact.get('fact_id')} 实体 {missing} 未出现在载体证据中")
            else:
                counters["entity_ok"] += 1
            if any(word in text for word in fact.get("directional_keywords") or []):
                counters["keyword_ok"] += 1
            else:
                problems.append(f"{qid}: 事实 {fact.get('fact_id')} 方向词簇未在载体证据中命中")
        for jid in junk:
            if jid in source_ids:
                problems.append(f"{qid}: 垃圾 ID {jid} 同时是标答事实载体")
            if jid not in index:
                problems.append(f"{qid}: 垃圾 ID {jid} 不存在于任何数据流")
        total = len(junk) + len(facts)
        ratio = len(junk) / max(total, 1)
        counters["junk_ratio_min"] = min(counters["junk_ratio_min"], ratio)
        if ratio < 0.95:
            problems.append(f"{qid}: 垃圾占比 {ratio:.4f} < 0.95")
        for fact in facts:
            sid = fact.get("source_ref_id") or ""
            carrier = _find_carrier(question, sid)
            if carrier is not None and carrier.get("is_junk") is True:
                problems.append(f"{qid}: 标答载体 {sid} 被声明为垃圾")
        if schema and _pydantic_available():
            try:
                _validate_schema(question, gt)
                counters["pydantic_ok"] += 1
            except Exception as exc:  # pragma: no cover - 依赖 pydantic
                problems.append(f"{qid}: CleaningQuestion 契约校验失败: {exc}")
    return {
        "counters": counters,
        "focus_counts": focus_counts,
        "difficulty_counts": difficulty_counts,
        "fact_counts": fact_counts,
        "modality_fragments": modality_fragments,
        "problems": problems[:40],
        "problem_total": len(problems),
    }


def _find_carrier(question: Mapping[str, Any], carrier_id: str) -> Dict[str, Any] | None:
    sensor = question.get("sensor_stream") or {}
    if sensor.get("packet_id") == carrier_id:
        return sensor
    for key in ("mic_stream", "app_message_stream", "user_dialogue_stream"):
        for entry in question.get(key) or []:
            if carrier_id in (entry.get("snippet_id"), entry.get("msg_id"), entry.get("utterance_id")):
                return entry
    for entry in (question.get("voiceprint_cluster") or {}).get("detected_speakers") or []:
        if entry.get("spk_id") == carrier_id:
            return entry
    for entry in sensor.get("noise_fragments") or []:
        if entry.get("fragment_id") == carrier_id:
            return entry
    return None


def _pydantic_available() -> bool:
    try:
        import pydantic  # noqa: F401
    except Exception:  # pragma: no cover
        return False
    return True


def _validate_schema(question: Mapping[str, Any], gt: Mapping[str, Any]) -> None:
    from aios_core.simulation.cleaning_arena_protocol import CleaningQuestion  # type: ignore

    CleaningQuestion.model_validate({**dict(question), **dict(gt)})


def _load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _dump_jsonl(rows: Iterable[Mapping[str, Any]], path: str | Path) -> Tuple[int, str]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))  # 摘要必须覆盖落盘的全部字节（含行尾换行）
            count += 1
    return count, digest.hexdigest()


def selftest() -> int:
    """目录自检：所有信号模板渲染一遍，核对方向词簇与实体落地。"""
    failures: List[str] = []
    slots = build_slots(build_persona(3), random.Random(7))
    for signal in SIGNALS:
        declared = len(signal.get("entities", ()))
        ok_variants = 0
        for attempt, template in enumerate(signal["texts"]):
            rnd = random.Random(11 + attempt)
            rendered = render_signal({**signal, "texts": (template,)}, slots, rnd)
            full_entities = len(rendered["entities"]) == declared
            if rendered["keyword_hit"] and full_entities:
                ok_variants += 1
            elif attempt == 0:
                failures.append(
                    f"{signal['id']}: 首个变体公平性不足 keyword_hit={rendered['keyword_hit']} "
                    f"entities={rendered['entities']}/{declared} text={rendered['text']}"
                )
        if ok_variants == 0:
            failures.append(f"{signal['id']}: 全部 {len(signal['texts'])} 个变体均无法同时满足方向词簇与实体锚点")
        else:
            signal.setdefault("_ok_variants", ok_variants)
    for family in JUNK_FAMILIES:
        if not family.get("texts"):
            failures.append(f"垃圾族 {family['id']} 缺少文本")
        if family["modality"] not in ("mic", "app", "dialogue", "voiceprint", "sensor"):
            failures.append(f"垃圾族 {family['id']} 模态非法")
    print(f"信号目录 {len(SIGNALS)} 条 / 垃圾族 {len(JUNK_FAMILIES)} 条")
    if failures:
        print("自检失败:")
        for item in failures:
            print("  -", item)
        return 1
    print("自检通过：全部信号模板的方向词簇与实体均可在证据文本中命中")
    return 0


#: 每个方向的情绪底色（用于全局日总结，避免与事实错位）
SIGNAL_TONES: Mapping[str, Tuple[str, ...]] = {
    "FALL_IMPACT": ("惊险", "后怕"), "PVC_BURST": ("心慌", "警觉"),
    "RESTING_TACHYCARDIA": ("不适", "焦虑"), "BARO_STORM_DROP": ("沉闷", "不适"),
    "OFF_WRIST_FALSE_ALARM": ("乌龙", "警觉"), "FAKE_FALL_FRAUD": ("窝火", "戒备"),
    "DEBT_BORROWING": ("权衡", "谨慎"), "REPAYMENT_PROMISE": ("松口气", "将信将疑"),
    "ARGUMENT_CONFLICT": ("愤怒", "憋屈"), "FAMILY_ENTRUSTMENT": ("沉重", "牵挂"),
    "NDA_CONFIDENTIALITY": ("紧绷", "警觉"), "WORK_OVERTIME": ("疲惫", "硬撑"),
    "PARTNER_SHELL_IP_THEFT": ("愕然", "愤怒"), "MEDICAL_DISPUTE_PUSH": ("委屈", "克制"),
    "WORKPLACE_HARASSMENT": ("愤怒", "决绝"), "NEIGHBOR_LEAK_DISPUTE": ("烦闷", "争执"),
    "RENOVATION_RUNAWAY": ("窝火", "无力"), "CRYPTO_PONZI_WOM": ("崩溃", "自责"),
    "THESIS_BLIND_REVIEW": ("挫败", "自我怀疑"), "BANK_LARGE_TRANSFER": ("谨慎", "踏实"),
    "FAKE_TRANSFER_COUNTER": ("警惕", "后怕"), "CRYPTO_PONZI_COLLAPSE": ("崩溃", "绝望"),
    "FINANCING_BET_FAILURE": ("高压", "恐慌"), "LAB_CRITICAL_VALUE": ("恐惧", "急迫"),
    "DIABETIC_KETOACIDOSIS": ("恐惧", "急迫"), "MEDICAL_APPOINTMENT": ("务实", "安心"),
    "MEDICATION_REMINDER": ("日常", "小心"), "LAYOFF_DISPUTE": ("不安", "愤懑"),
    "NON_COMPETE_2M": ("紧绷", "无奈"), "EXAM_CIVIL_SERVICE": ("紧张", "期待"),
    "CONTRACT_SIGNING": ("务实", "积极"), "COURT_SUMMONS": ("紧张", "戒备"),
    "CUSTODY_BATTLE_FORGED": ("愤懑", "坚定"), "PIPE_BACKFLOW_COMPENSATION": ("烦闷", "疲惫"),
    "TRAVEL_DISRUPTION": ("烦躁", "无奈"), "MEAL_EVENT": ("日常", "松弛"),
    "DELIVERY_EVENT": ("日常", "平静"), "USED_CAR_FLOODED": ("窝火", "维权"),
    "WEAK_SOS": ("危急", "无助"), "HIDDEN_CARDIAC_CRISIS": ("强撑", "心慌"),
    "MYOCARDIAL_INFARCTION_HIDDEN": ("强撑", "危险误判"), "SUICIDAL_CRISIS": ("绝望", "危急"),
    "EMOTIONAL_CRISIS": ("崩溃", "孤单"), "ACUTE_PAIN_ATTACK": ("疼痛", "硬扛"),
    "DRUG_ANAPHYLAXIS": ("危急", "恐慌"), "REAL_MEDICAL_REQUEST": ("务实", "决心"),
    "RESIGNATION_DECISION": ("决绝", "释然"), "DEBT_DEFAULT_IRONY": ("反讽", "寒心"),
    "WAGE_ARREARS_IRONY": ("反讽", "疲惫"), "CONCEALED_CANCER": ("揪心", "愧疚"),
    "DIVORCE_DECISION": ("疲惫", "决绝"), "HIDDEN_MARITAL_ASSETS": ("寒心", "戒备"),
    "DOG_KNOCK_CHILD": ("气愤", "护犊"), "VOICE_BINDING_USER": ("安心", "日常"),
    "VOICE_BINDING_KEY_CONTACT": ("亲近", "踏实"), "KEY_CONVERSATION_WITH_CONTACT": ("亲近", "信任"),
    "VOICE_IMPERSONATION_FRAUD": ("警觉", "后怕"),
}


def carrier_scene_hint(scene: str) -> str:
    """场景是否偏户外（用于给非声明型垃圾补一条声学旁证）。"""
    return "outdoor" if scene in ("street", "commute", "station", "construction", "night_market") else "indoor"


def generate(count: int, seed: int, questions_path: str | Path, gt_path: str | Path,
             report_path: str | Path | None = None, manifest_path: str | Path | None = None,
             progress: bool = True) -> Dict[str, Any]:
    rnd = random.Random(seed)
    focus_list = quota_sequence(FOCUS_QUOTA, count, rnd)
    diff_list = quota_sequence(DIFFICULTY_QUOTA, count, rnd)
    factn_list = weighted_sequence(FACT_COUNT_QUOTA, count, rnd)

    def _rows() -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
        for index in range(count):
            yield build_question(index, focus_list, diff_list, factn_list, seed)

    questions: List[Dict[str, Any]] = []
    gts: List[Dict[str, Any]] = []
    for index, (question, gt) in enumerate(_rows()):
        questions.append(question)
        gts.append(gt)
        if progress and (index + 1) % 2000 == 0:
            print(f"  ... 已生成 {index + 1}/{count} 题", flush=True)
    q_count, q_hash = _dump_jsonl(questions, questions_path)
    g_count, g_hash = _dump_jsonl(gts, gt_path)
    summary = {
        "generator_agent": GENERATOR_AGENT,
        "seed": seed,
        "questions": q_count,
        "ground_truth_records": g_count,
        "questions_sha256": q_hash,
        "ground_truth_sha256": g_hash,
        "questions_bytes": Path(questions_path).stat().st_size,
        "ground_truth_bytes": Path(gt_path).stat().st_size,
        "focus_counts": _count(focus_list),
        "difficulty_counts": _count(diff_list),
        "fact_count_distribution": _count([str(x) for x in factn_list]),
        "verify": verify_bank(questions_path, gt_path),
    }
    if manifest_path is not None:
        Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
        Path(manifest_path).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if report_path is not None:
        _write_report(report_path, summary, questions[:1], gts[:1])
    return summary


def _count(items: Sequence[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in items:
        key = str(item)
        out[key] = out.get(key, 0) + 1
    return out


def _write_report(path: str | Path, summary: Mapping[str, Any], question_sample: Sequence[Mapping[str, Any]],
                  gt_sample: Sequence[Mapping[str, Any]]) -> None:
    verify = summary.get("verify") or {}
    counters = verify.get("counters") or {}
    lines = [
        "# 出卷报告 · AIOS 3.0 高熵全天生活流题库（战队 01a0aa2d-fantonghui）",
        "",
        f"- 出题方：`{GENERATOR_AGENT}`（本卷由其他战队跨 Git 交叉作答；`solver == generator` 一律 0 分）",
        f"- 题量：**{summary['questions']}** 道 / 标答：**{summary['ground_truth_records']}** 条",
        f"- 随机种子：`{summary['seed']}`（确定性发生器，重跑逐字节一致）",
        f"- questions sha256：`{summary['questions_sha256']}`",
        f"- ground_truth sha256：`{summary['ground_truth_sha256']}`",
        f"- 文件体积：questions {summary['questions_bytes'] / 1e6:.1f} MB / gt {summary['ground_truth_bytes'] / 1e6:.1f} MB",
        "",
        "## 一、配额达成（调度书规定）",
        "",
        "| 数据流 | 题数 |", "| --- | --- |",
    ]
    for key, value in sorted((summary.get("focus_counts") or {}).items()):
        lines.append(f"| {key} | {value} |")
    lines += ["", "| 难度 | 题数 |", "| --- | --- |"]
    for key, value in sorted((summary.get("difficulty_counts") or {}).items()):
        lines.append(f"| {key} | {value} |")
    lines += ["", "| 标答事实条数 | 题数 |", "| --- | --- |"]
    for key, value in sorted((summary.get("fact_count_distribution") or {}).items()):
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## 二、公平性不变量自检（发生器侧）",
        "",
        f"- 题数：{counters.get('questions', 0)}；标答事实：{counters.get('facts', 0)}；垃圾碎片：{counters.get('junk_ids', 0)}",
        f"- 载体可溯源：{counters.get('source_ok', 0)}/{counters.get('facts', 0)}",
        f"- 实体全部落地证据：{counters.get('entity_ok', 0)}/{counters.get('facts', 0)}",
        f"- 方向词簇命中证据：{counters.get('keyword_ok', 0)}/{counters.get('facts', 0)}",
        f"- CleaningQuestion 契约校验通过：{counters.get('pydantic_ok', 0)}",
        f"- 单题垃圾占比最小值：{counters.get('junk_ratio_min', 0):.4f}（红线 ≥ 0.95）",
        f"- 校验问题数：{verify.get('problem_total', 0)}",
        "",
        "## 三、标杆样例（第 1 题）",
        "",
        "```json",
        json.dumps({"question": _slim(question_sample[0]) if question_sample else None,
                    "ground_truth": _slim(gt_sample[0]) if gt_sample else None},
                   ensure_ascii=False, indent=2)[:2400],
        "```",
        "",
        "## 四、出题官自述",
        "",
        "1. 每道题 = 一个人的 24 小时（07:00~23:30）：传感器宏观体征包 + MIC 切片 + 声纹聚类 + APP 消息流 + 原话流；",
        "2. 五路证据按调度书配额铺满 10,000 题（传感器 3000 / MIC 3000 / 声纹 2000 / APP 1500 / 原话 500）；",
        "3. 全部标答均为方向性语义锚点：global_summary + dim:health / dim:social / dim:emotion / dim:finance / dim:career，",
        "   每条锚点附【可接受同义词簇】与【绝对偏离红线】；",
        "4. 95% 碎片为垃圾（营销/风噪/报站/砍一刀/验证码/吹牛口头禅），全部登记在 ground_truth_junk_ids 供物理剪枝；",
        "5. 对抗陷阱（醉酒吹牛、口头禅轻生、玩笑借钱、钓鱼短信、假摔碰瓷）与真实事实并存，检验答题方是否被高熵噪声带偏。",
        "",
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _slim(record: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """报告样例瘦身：长列表只留前 3 条（报告不承载全量数据）。"""
    if not record:
        return record
    out: Dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, list) and len(value) > 3:
            out[key] = [*value[:3], f"... 其余 {len(value) - 3} 条见题库原文"]
        else:
            out[key] = value
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 高熵出卷官（01a0aa2d-fantonghui）")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="题量（默认 10000）")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="确定性随机种子")
    parser.add_argument("--out-questions", default="benchmarks/data_cleaning/questions/"
                                                f"questions_{GENERATOR_AGENT}.jsonl")
    parser.add_argument("--out-ground-truth", default="benchmarks/data_cleaning/ground_truth/"
                                                     f"gt_{GENERATOR_AGENT}.jsonl")
    parser.add_argument("--report", default="benchmarks/data_cleaning/reports/"
                                           f"generation_report_{GENERATOR_AGENT}.md")
    parser.add_argument("--manifest", default="benchmarks/data_cleaning/questions/"
                                             f"manifest_{GENERATOR_AGENT}.json")
    parser.add_argument("--selftest", action="store_true", help="信号/垃圾目录自检")
    parser.add_argument("--verify-only", metavar="QUESTIONS", default=None,
                        help="只校验既有题库（需配合 --verify-gt）")
    parser.add_argument("--verify-gt", default=None, help="校验用标答路径")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 题（冒烟用）")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.verify_only:
        result = verify_bank(args.verify_only, args.verify_gt, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
        return 0 if result["problem_total"] == 0 else 1
    summary = generate(args.count, args.seed, args.out_questions, args.out_ground_truth,
                       report_path=args.report, manifest_path=args.manifest)
    print(json.dumps({k: v for k, v in summary.items() if k != "verify"}, ensure_ascii=False, indent=2))
    verify = summary["verify"]
    print(f"verify: problems={verify['problem_total']} counters={verify['counters']}")
    return 0 if verify["problem_total"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

