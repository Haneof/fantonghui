#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIOS 3.0 全天生活流与多维总结竞技场 —— 出卷官确定性引擎 (agent-01a0aa2c).

每卷 = 一个人的一整天 (07:00~23:30):
  persona (16 副人生人格) × plot arc (19 条跨维度冲突弧线, 含转折)
  + 已清洗生活流切片 (关键大事编织 + 海量琐碎日常 + 高难度诱饵)
  + 六维方向性语义标答 (global + health/social/emotion/finance/career),
    每维含: 核心句 / 可接受方向同义词 / 绝对偏离红线 / 关键实体 / 证据链.

产物:
  papers/papers_<gen>.jsonl       母卷 (题面 + 标答, 出卷官底稿)
  questions/questions_<gen>.jsonl 盲卷 (去标答, 给做题人)
  ground_truth/gt_<gen>.jsonl      独立标答卷
  reports/manifest_<gen>.json      分布统计与校验和

用法:
  python3 benchmarks/daily_summary/generators/daily_paper_generator.py
      [--count 1000] [--out-dir benchmarks/daily_summary] [--seed 0xD41] [--validate]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import string
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

GENERATOR_AGENT = "agent-01a0aa2c"
SEED_DEFAULT = 0xD417
TOTAL_DEFAULT = 1000
QUESTION_PREFIX = "D_agent-01a0aa2c_"

DIFFICULTY_WEIGHTS = [("EASY", 15), ("MEDIUM", 35), ("HARD", 30), ("ADVERSARIAL", 20)]
FILLER_COUNT = {"EASY": (6, 8), "MEDIUM": (10, 14), "HARD": (14, 20), "ADVERSARIAL": (14, 20)}

T0_MIN, T1_MIN = 7 * 60, 23 * 60 + 30  # 07:00 ~ 23:30


def T(fmt_min: int) -> str:  # minutes -> HH:MM
    return f"{fmt_min // 60:02d}:{fmt_min % 60:02d}"


def P(hhmm: str) -> int:  # HH:MM -> minutes
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def render(tpl: str, slots: Dict[str, str]) -> str:
    return string.Template(tpl).safe_substitute(slots)


# ---------------------------------------------------------------------------
# 16 副人生人格
# ---------------------------------------------------------------------------

PERSONAS: List[Dict[str, Any]] = [
    {"id": "P01", "name": "陈晓阳", "age": 17, "gender": "男", "occupation": "高三复读生",
     "life_stage": "高考备考", "city": "衡水", "household": "与父母同住, 母亲陪读",
     "traits": ["重度失眠", "焦虑躯体化", "父母高压"]},
    {"id": "P02", "name": "林浩", "age": 24, "gender": "男", "occupation": "大厂互联网外包程序员",
     "life_stage": "北漂合租", "city": "北京", "household": "隔断间合租",
     "traits": ["连续加班", "有女友", "租房漏水纠纷"]},
    {"id": "P03", "name": "苏晴", "age": 28, "gender": "女", "occupation": "孕晚期准妈妈(产假前)",
     "life_stage": "妊娠30周", "city": "杭州", "household": "与丈夫同住, 婆婆同城",
     "traits": ["妊娠期血糖偏高", "婆媳磨合", "数胎动"]},
    {"id": "P04", "name": "赵铁柱", "age": 32, "gender": "男", "occupation": "长途重卡货运司机",
     "life_stage": "跑长途养家", "city": "郑州", "household": "妻儿留守老家",
     "traits": ["疲劳驾驶", "路怒", "报喜不报忧"]},
    {"id": "P05", "name": "周建国", "age": 36, "gender": "男", "occupation": "待业(离异, 8岁儿子随前妻)",
     "life_stage": "失业再求职", "city": "武汉", "household": "独居, 周末接儿子",
     "traits": ["胃溃疡", "抚养费压力", "投简历石沉大海"]},
    {"id": "P06", "name": "高翔", "age": 42, "gender": "男", "occupation": "急诊科住院总医师",
     "life_stage": "连轴转中坚", "city": "上海", "household": "妻子+上小学女儿",
     "traits": ["24小时连轴", "缺席家庭", "高暴露风险"]},
    {"id": "P07", "name": "李大山", "age": 48, "gender": "男", "occupation": "建筑工地钢筋班包工头",
     "life_stage": "带班讨生活", "city": "重庆", "household": "妻子留守县城, 儿子读大学",
     "traits": ["痛风", "垫资发薪", "发包方扯皮"]},
    {"id": "P08", "name": "陈美玲", "age": 53, "gender": "女", "occupation": "民营企业财务总监",
     "life_stage": "更年期高管", "city": "深圳", "household": "丈夫+待嫁女儿",
     "traits": ["失眠盗汗", "税务风险", "女儿礼金纠纷"]},
    {"id": "P09", "name": "王秀英", "age": 65, "gender": "女", "occupation": "退休教师",
     "life_stage": "初老退休", "city": "成都", "household": "与老伴同住, 女儿同城",
     "traits": ["轻度健忘", "热心讲座", "老伴白内障"]},
    {"id": "P10", "name": "刘德贵", "age": 78, "gender": "男", "occupation": "独居退休工人",
     "life_stage": "空巢高龄", "city": "沈阳", "household": "独居, 儿女在外地",
     "traits": ["骨质疏松", "耳背", "不愿麻烦子女"]},
    {"id": "P11", "name": "张野", "age": 30, "gender": "男", "occupation": "户外领队/攀岩教练",
     "life_stage": "带队生涯", "city": "昆明", "household": "独居, 女友异地",
     "traits": ["体能强悍", "安全强迫症", "卫星电话盲区经验"]},
    {"id": "P12", "name": "何小飞", "age": 22, "gender": "男", "occupation": "外卖骑手",
     "life_stage": "城中村合租", "city": "广州", "household": "与老乡合租",
     "traits": ["膝盖滑囊炎", "超时罚款", "暴雨跑单"]},
    {"id": "P13", "name": "钱国富", "age": 45, "gender": "男", "occupation": "中式餐饮连锁店主(3家店)",
     "life_stage": "经营扩张", "city": "南京", "household": "妻子管账+上初中儿子",
     "traits": ["供应商催款", "抽检风险", "厨师难管"]},
    {"id": "P14", "name": "沈画", "age": 26, "gender": "女", "occupation": "独立自由插画师",
     "life_stage": "接单维生", "city": "大理", "household": "独居+一只猫",
     "traits": ["颈椎压迫手麻", "甲方改稿", "熬夜赶稿"]},
    {"id": "P15", "name": "郑敏", "age": 29, "gender": "女", "occupation": "电商运营专员",
     "life_stage": "大促备战", "city": "杭州", "household": "与男友同居",
     "traits": ["大促熬夜", "KPI重压", "偏头痛"]},
    {"id": "P16", "name": "吴刚", "age": 34, "gender": "男", "occupation": "银行客户经理",
     "life_stage": "房贷+6岁女儿", "city": "苏州", "household": "妻子+女儿+岳母",
     "traits": ["存款指标", "消保检查", "女儿怕黑"]},
]

# ---------------------------------------------------------------------------
# 琐碎日常填充池 (背景噪音, 不得左右主线)
# ---------------------------------------------------------------------------

def _fm(source: str, text: str, only=None, exclude=None, window=None):
    return {"source": source, "text": text,
            "only": set(only or []), "exclude": set(exclude or []),
            "window": window}


def _filler_ok(f: Dict[str, Any], pid: str) -> bool:
    if f["only"] and pid not in f["only"]:
        return False
    return pid not in f["exclude"]


_NOCT = {"P01", "P09", "P10"}          # 无同事语境
_SOLO = {"P04", "P05", "P10", "P11", "P12", "P14"}  # 独居/ solo, 无睡前家人
_ACTIVE = {"P11", "P12"}               # 高步数职业, 无散步/久坐语境

FILLER_MIC = [
    _fm("通勤路上", "地铁上给同事发语音: 电梯又排长队, 我晚五分钟到", exclude={"P09", "P10", "P04", "P01"}),
    _fm("咖啡店", "中杯美式去冰, 再要一份全麦三明治打包"),
    _fm("菜鸟驿站", "取件码后四位8846, 那个大箱子是前两天买的日用品"),
    _fm("便利店", "饭团加热一下, 再拿一瓶无糖乌龙茶"),
    _fm("同事闲聊", "中午吃啥？楼下新开了家黄焖鸡, 据说还行", exclude=_NOCT, window=(630, 810)),
    _fm("同事闲聊", "你看了昨晚的球没？最后三分钟绝杀, 太离谱了", exclude=_NOCT),
    _fm("邻居寒暄", "王阿姨买菜回来啦？今天西红柿多少钱一斤"),
    _fm("水果摊", "这葡萄甜不甜？称两斤, 再搭两个苹果"),
    _fm("外卖电话", "喂, 外卖放门口垫子上就行, 我走不开"),
    _fm("快递电话", "对, 放蜂巢柜就行, 回家我去拿"),
    _fm("晚饭商量", "晚上煮面条还是点外卖？冰箱里还有两个鸡蛋", window=(990, 1230)),
    _fm("睡前家人", "我先睡了, 你也早点休息, 记得关阳台灯", exclude=_SOLO, window=(1260, 1410)),
    _fm("电梯偶遇", "回来啦？这周末有啥安排, 天气预报说降温"),
    _fm("停车场", "师傅, 月卡续一个月, 还是那个车位", exclude={"P01", "P12"}),
    _fm("理发店", "两边推短一点, 上面稍微修修就行, 不办卡"),
    _fm("药店", "买一盒创可贴, 再拿一瓶碘伏棉签家用"),
    _fm("遛弯", "沿河边走了两圈, 风挺凉, 早点回去吧"),
    _fm("哄孩子", "再讲最后一个故事就睡觉, 明天还要早起", only={"P16"}, window=(1170, 1350)),
    _fm("喂猫", "罐头开了一半, 剩下的放冰箱明天吃", only={"P14"}),
    _fm("朋友闲聊", "周末去爬山？我看天气不错, 把那谁也叫上"),
    _fm("同学群语音", "聚餐时间定了周六晚上, 地点发群里了, 记得接龙"),
    _fm("父母日常", "妈, 我这儿都挺好, 你们注意身体, 降压药按时吃", exclude={"P10"}),
    _fm("午休", "趴桌上眯了二十分钟, 脖子都睡僵了", exclude={"P09", "P10"}, window=(690, 840)),
    _fm("茶水间", "这咖啡豆谁买的？挺香, 链接发我一下", exclude=_NOCT),
]
FILLER_APP = [
    _fm("外卖App", "订单已送达: 黄焖鸡米饭1份, 记得给个好评哦"),
    _fm("天气", "明天多云转阴, 气温18~26度, 出门建议带伞"),
    _fm("新闻推送", "今日热点: 多地迎来返程客流小高峰"),
    _fm("快递", "您的包裹已到达菜鸟驿站, 请凭取件码领取"),
    _fm("手环", "今日步数已同步, 手环电量剩余62%"),
    _fm("运营商", "话费余额不足20元提醒, 可通过App一键充值"),
    _fm("日历", "提醒: 明天上午10点团队例会, 别迟到", exclude=_NOCT),
    _fm("音乐", "根据您的喜好推荐: 深夜加班Lo-Fi歌单"),
    _fm("视频会员", "您追的剧更新了第18集, 今晚准时开播"),
    _fm("优惠券", "3张满50减10券即将过期, 点击查看"),
    _fm("运动", "本周已运动3次, 再坚持2次即可达成目标"),
    _fm("读书", "今日阅读15分钟, 已连续打卡第9天"),
    _fm("记账", "本月餐饮支出1420元, 较上月同期下降8%"),
    _fm("12306", "候补订单提醒: 周末车次余票紧张, 建议多选几个车次"),
    _fm("闹钟", "起床闹钟将在6:30响起, 已为您开启渐强模式"),
    _fm("云相册", "本周自动备份照片128张, 空间剩余充足"),
]
# 传感器填充: 固定时刻 (小抖动), 不得乱序
FILLER_SENSOR = [
    {"t": "07:20", "source": "体重秤", "text": "晨起空腹体重平稳, 较昨日无变化",
     "only": set(), "exclude": set()},
    {"t": "08:10", "source": "手环", "text": "晨间步行约15分钟, 心率轻度上升后回落",
     "only": set(), "exclude": {"P09", "P10", "P04"}},
    {"t": "12:40", "source": "手环", "text": "午间小睡约20分钟, 心率平稳在68bpm上下",
     "only": set(), "exclude": set()},
    {"t": "15:30", "source": "手环", "text": "连续静坐2小时, 手环震动提醒起身活动",
     "only": set(), "exclude": _ACTIVE},
    {"t": "18:30", "source": "手环", "text": "晚饭后散步约25分钟, 步速平缓",
     "only": set(), "exclude": _ACTIVE},
    {"t": "21:30", "source": "手环", "text": "睡前静坐心率回落至70bpm左右, 状态平稳",
     "only": set(), "exclude": set()},
]

SIGNAL_ZH = {"heart_rate": "心率", "sleep_fragment": "睡眠分段",
             "fall_impact": "跌倒冲击", "sedentary": "久坐"}

DECOYS = [
    {"key": "D1", "t": "08:40", "mod": "mic", "source": "地铁上听到",
     "text": "旁边两个陌生人为踩脚的事吵起来了, 乘务员过来劝开, 跟我没关系",
     "bg": "目睹陌生人争吵"},
    {"key": "D1", "t": "12:30", "mod": "app", "source": "小区业主群",
     "text": "楼上楼下两家为漏水在群里骂了99+条, 物业说下午去调解, 吃瓜即可",
     "bg": "邻里漏水骂战"},
    {"key": "D1", "t": "17:50", "mod": "mic", "source": "路口围观",
     "text": "两辆车轻微追尾, 车主理论了几句就挪车了, 我看了一眼就走",
     "bg": "路口追尾围观"},
    {"key": "D1", "t": "20:10", "mod": "app", "source": "大学同学群",
     "text": "班长发了200元红包庆祝二胎, 群里刷屏抢红包, 我抢了3块2",
     "bg": "同学群抢红包"},
    {"key": "D1", "t": "21:40", "mod": "app", "source": "朋友圈",
     "text": "刷到前同事晒马尔代夫蜜月照, 点了个赞就划过去了",
     "bg": "刷到他人晒幸福", "exclude": {"P01"}},
    {"key": "D1", "t": "07:50", "mod": "mic", "source": "早餐店隔壁桌",
     "text": "隔壁桌大哥吹牛说儿子年薪百万, 老板娘笑而不语, 听个乐呵",
     "bg": "听陌生人吹牛"},
]

GENERIC_BACKGROUND = ["买咖啡", "取快递", "点外卖", "抢红包", "天气提醒",
                      "新闻推送", "步数同步", "闲聊拼单", "追剧更新", "午休小睡"]

# ---------------------------------------------------------------------------
# 19 条跨维度人生弧线
# ---------------------------------------------------------------------------
# beats: {key, t, mod, source, texts[]}  (texts 抽1条; ${槽位}按卷采样)
# vitals_episodes: {key, t, signal, reading, context} (自动生成 sensor 切片)
# gt: 6维 {core, syn[], red[], entities[], evidence[beat keys]}
# twist: ADVERSARIAL 专用 {beat, patch:{dim: {suffix, syn_add[], red_add[]}},
#                          evidence_add:{dim:[keys]}}

ARCS: List[Dict[str, Any]] = []

# A01 被批+分手 (示例弧)
ARCS.append({
    "arc_id": "A01_BREAKUP_AFTER_REBUKE", "title": "白天被批晚上分手",
    "personas": ["P02", "P15"],
    "slot_overrides": {"P15": {"partner": ["男友阿哲", "男友大伟", "男友陈默"]}},
    "slots": {
        "boss": ["王经理", "李总监", "张主管"],
        "partner": ["女友小雨", "女友晓雯", "女友思思"],
        "project": ["季度汇报", "Q3大促方案", "消保检查材料"],
        "mistake": ["数据口径全错", "漏了核心指标", "被客户当场否掉"],
        "place": ["楼下长椅上", "出租屋阳台上", "江边步道上"],
    },
    "beats": [
        {"key": "K1", "t": "09:40", "mod": "mic", "source": "${boss}",
         "texts": ["早会上${boss}当众发火: ${project}${mistake}, 今晚8点前必须交整改版!",
                   "部门会上${boss}点名批评:${project}做成这样${mistake}, 今晚重做一版发我!"]},
        {"key": "K2", "t": "12:15", "mod": "mic", "source": "同事大刘",
         "texts": ["大刘拍拍我: 别往心里去, ${boss}今天被大老板骂了, 拿咱们撒气",
                   "午饭时大刘安慰: 整改版我帮你过一遍数据, 先吃饭"]},
        {"key": "K3", "t": "15:30", "mod": "app", "source": "工作群",
         "texts": ["${boss}@所有人: 今晚8点前${project}整改版发群里, 过期自己看着办",
                   "工作群通知: ${project}整改评审提前到今晚8点, 相关人准时参加"]},
        {"key": "K4", "t": "19:20", "mod": "app", "source": "${partner}微信",
         "texts": ["${partner}: 我们分手吧, 你根本没时间谈恋爱, 祝你幸福 [对方已开启朋友验证]",
                   "${partner}: 想了一周了, 还是分开吧, 你忙你的前程, 我不等了"]},
        {"key": "K5", "t": "21:05", "mod": "mic", "source": "独白",
         "texts": ["一个人在${place}坐着, 给${partner}打了三个电话全被挂断, 语音也不回",
                   "在${place}吹冷风, 翻着和${partner}的聊天记录, 越看心越慌"]},
        {"key": "K6", "t": "23:10", "mod": "mic", "source": "独白",
         "texts": ["躺床上睁眼到半夜, 整改版一个字没改, 分手两个字在脑子里转, 失眠到天亮",
                   "凌晨失眠睡不着, ${project}和分手的事搅在一起, 心跳得厉害"]},
    ],
    "vitals": {"sleep": (4.6, 5.6), "rest_hr": (70, 76), "steps": (4500, 7500),
               "episodes": [
        {"key": "V1", "t": "09:45", "signal": "heart_rate", "reading": "108bpm",
         "context": "被${boss}当众批评时站立"},
        {"key": "V2", "t": "21:00", "signal": "heart_rate", "reading": "125bpm",
         "context": "接到分手微信后静坐${place}"},
    ]},
    "gt": {
        "global": {
            "core": "白天${project}被${boss}当众批评要求连夜整改, 晚间突遭${partner}提出分手, 全天从职业受挫滑向情感重创, 身心高压",
            "syn": ["工作受挫", "被领导批评", "当众挨批", "连夜整改", "恋人分手", "感情破裂",
                    "被分手", "失恋", "双重打击", "高压一天", "职业受挫", "情感重创"],
            "red": ["升职加薪", "求婚成功", "甜蜜互动", "打情骂俏", "岁月静好",
                    "心脏病发作", "婚姻美满", "一帆风顺"],
            "entities": ["${boss}", "${partner}", "${project}"], "evidence": ["K1", "K4", "K5"]},
        "dim:health": {
            "core": "日间因紧张心率偏快, 21点前后突发情绪性心动过速至125bpm, 夜间失眠, 疲劳累积",
            "syn": ["情绪性心动过速", "心率飙升", "125", "失眠", "紧张", "疲劳",
                    "交感兴奋", "睡眠不足", "心慌"],
            "red": ["心肌梗死", "心脏病发作", "器质性心脏病", "猝死", "酣睡整晚", "平稳正常"],
            "entities": ["125bpm", "失眠"], "evidence": ["V1", "V2", "K6"]},
        "dim:social": {
            "core": "与${boss}存在职业冲突挨批; 与${partner}关系破裂走向分手; 同事大刘给予安慰支持",
            "syn": ["被批评", "职业冲突", "分手", "关系破裂", "闹掰", "同事安慰", "情感支持"],
            "red": ["求婚", "复合", "甜蜜", "领导表扬", "众叛亲离", "人缘爆棚"],
            "entities": ["${boss}", "${partner}", "大刘"], "evidence": ["K1", "K2", "K4"]},
        "dim:emotion": {
            "core": "主基调焦虑委屈, 白天强撑改稿, 晚间因分手崩溃绝望, 深夜失眠反刍",
            "syn": ["焦虑", "委屈", "崩溃", "绝望", "失眠反刍", "难过", "压抑", "低落", "心碎"],
            "red": ["开心", "幸福", "兴奋", "平静满足", "毫不在意", "暴怒伤人"],
            "entities": ["${partner}"], "evidence": ["K4", "K5", "K6"]},
        "dim:finance": {
            "core": "当日无大额收支, 仅咖啡外卖等日常小额消费, 财务平稳无新增债务",
            "syn": ["无大额收支", "日常小额消费", "财务平稳", "无新增债务", "开销正常"],
            "red": ["大额债务", "巨额亏损", "欠薪", "破产", "一夜暴富", "工资翻倍"],
            "entities": [], "evidence": []},
        "dim:career": {
            "core": "${project}因${mistake}被否, 要求当晚整改重交, 面临返工压力与信任危机",
            "syn": ["${project}被否", "整改", "重做", "返工", "当众批评", "信任危机", "绩效压力"],
            "red": ["升职", "加薪", "表彰", "提前转正", "大获成功", "被开除"],
            "entities": ["${boss}", "${project}"], "evidence": ["K1", "K3"]},
    },
    "background": ["买咖啡", "取快递", "同事拼单"],
    "twist": {
        "beat": {"key": "T1", "t": "22:40", "mod": "mic", "source": "给发小打电话",
                 "texts": ["我跟发小说: 我没事, 早料到会分, 分就分吧, 明天还得交整改版呢 (说完又失眠到半夜)"]},
        "patch": {"dim:emotion": {
            "suffix": "; 对外逞强称没事, 但125bpm心率与整夜失眠暴露真实崩溃",
            "syn_add": ["逞强", "嘴硬", "口是心非"], "red_add": ["真心放下", "毫不在意"]}},
        "evidence_add": {"dim:emotion": ["T1"]},
    },
})

# A02 裁员传闻+房贷
ARCS.append({
    "arc_id": "A02_LAYOFF_RUMOR", "title": "裁员传闻与房贷压力",
    "personas": ["P02", "P15", "P16"],
    "slot_overrides": {"P02": {"loan": ["房租4500加花呗6000"]},
                       "P15": {"loan": ["房租4500加花呗6000"]},
                       "P16": {"loan": ["房贷8200月供"]}},
    "slots": {
        "hr": ["HR王姐", "人力李经理"],
        "colleague": ["隔壁组老张", "同组阿坤"],
        "loan": ["房贷8200月供", "房租4500加花呗6000"],
        "ratio": ["优化30%", "砍掉整条业务线"],
    },
    "beats": [
        {"key": "K1", "t": "10:20", "mod": "app", "source": "公司小道群",
         "texts": ["小道消息: 公司要${ratio}, 名单周五出, 据说35岁以上优先",
                   "群里疯传: ${ratio}, HR已经开始一个个约谈, 大家自求多福"]},
        {"key": "K2", "t": "11:05", "mod": "mic", "source": "茶水间",
         "texts": ["听说${colleague}上午被约谈了, 出来脸都白了, 工位收拾了一半",
                   "茶水间都在传:${colleague}被毕业了, 赔偿N+1, 下一个不知是谁"]},
        {"key": "K3", "t": "14:00", "mod": "mic", "source": "${hr}",
         "texts": ["${hr}把我叫去小会议室: 聊聊你对职业规划的想法? 全程打太极, 越听越慌",
                   "被${hr}约谈三十分钟, 话里话外让主动提, 我装听不懂混过去了"]},
        {"key": "K4", "t": "17:40", "mod": "app", "source": "银行短信",
         "texts": ["银行提醒:${loan}本月15号扣款, 请确保余额充足",
                   "还款日还有三天:${loan}, 卡里余额刚够, 不敢乱花一分钱"]},
        {"key": "K5", "t": "20:30", "mod": "mic", "source": "给父母打电话",
         "texts": ["妈问工作咋样, 我说挺好的还涨工资了, 挂了电话鼻子发酸",
                   "跟爸妈报喜不报忧: 公司效益好着呢, 让他们别担心, 手心全是汗"]},
        {"key": "K6", "t": "23:50", "mod": "mic", "source": "独白",
         "texts": ["数羊数到三千还失眠, 万一被裁${loan}断供, 房子就没了",
                   "凌晨失眠翻来覆去, 脑子里全是约谈和名单, 天快亮才眯了一会"]},
    ],
    "vitals": {"sleep": (3.4, 4.4), "rest_hr": (76, 82), "steps": (3500, 6000),
               "episodes": [
        {"key": "V1", "t": "14:05", "signal": "heart_rate", "reading": "112bpm",
         "context": "被${hr}约谈时静坐"},
        {"key": "V2", "t": "23:59", "signal": "sleep_fragment", "reading": "深睡仅40分钟",
         "context": "整夜辗转反侧"},
    ]},
    "gt": {
        "global": {
            "core": "裁员传闻笼罩叠加${loan}压力, 被${hr}约谈后整日惶恐, 靠隐瞒家人硬撑, 夜间严重失眠",
            "syn": ["裁员传闻", "优化名单", "被约谈", "惶恐", "房贷压力", "断供焦虑",
                    "隐瞒家人", "硬撑", "失眠", "朝不保夕"],
            "red": ["升职加薪", "公司扩张", "财务自由", "高枕无忧", "被重用", "提前退休"],
            "entities": ["${hr}", "${loan}"], "evidence": ["K1", "K3", "K4"]},
        "dim:health": {
            "core": "静息心率偏高, 约谈时紧张至112bpm, 夜间重度失眠深睡不足一小时, 疲劳透支",
            "syn": ["紧张", "112", "重度失眠", "深睡不足", "疲劳", "心慌", "睡眠差"],
            "red": ["心脏病发作", "猝死", "酣睡", "生龙活虎", "马拉松备战"],
            "entities": ["112bpm", "失眠"], "evidence": ["V1", "V2", "K6"]},
        "dim:social": {
            "core": "与公司关系紧张面临被优化; ${colleague}被约谈加剧兔死狐悲; 对父母报喜不报忧",
            "syn": ["被约谈", "兔死狐悲", "人心惶惶", "报喜不报忧", "隐瞒父母", "职场寒冬"],
            "red": ["领导器重", "团队和睦", "家庭坦诚", "众星捧月"],
            "entities": ["${hr}", "${colleague}"], "evidence": ["K2", "K3", "K5"]},
        "dim:emotion": {
            "core": "全天被恐惧和羞耻裹挟, 白天强装镇定, 深夜被断供想象淹没, 近乎崩溃边缘",
            "syn": ["恐惧", "惶恐", "羞耻", "强装镇定", "崩溃边缘", "焦虑", "绝望", "硬撑"],
            "red": ["开心", "淡定", "知足常乐", "无忧无虑", "意气风发"],
            "entities": ["${loan}"], "evidence": ["K3", "K5", "K6"]},
        "dim:finance": {
            "core": "${loan}还款日在即余额仅够, 叠加可能失业, 现金流极度脆弱不敢消费",
            "syn": ["${loan}", "还款日", "余额仅够", "现金流脆弱", "不敢消费", "断供风险", "失业风险"],
            "red": ["存款丰厚", "提前还贷", "理财大赚", "财务自由", "工资翻倍"],
            "entities": ["${loan}"], "evidence": ["K4", "K6"]},
        "dim:career": {
            "core": "公司传出${ratio}, 本人被${hr}约谈试探, 职业安全感崩塌, 尚未开始找下家",
            "syn": ["裁员", "${ratio}", "被约谈", "职业危机", "安全感崩塌", "优化名单"],
            "red": ["升职", "加薪", "被挖角", "拿到offer", "创业成功", "铁饭碗"],
            "entities": ["${hr}", "${ratio}"], "evidence": ["K1", "K2", "K3"]},
    },
    "background": ["买咖啡", "取快递", "点外卖"],
})

# A03 升职加薪 (正向)
ARCS.append({
    "arc_id": "A03_PROMOTION_RAISE", "title": "升职加薪落地",
    "personas": ["P02", "P15", "P16", "P06"],
    "slot_overrides": {"P02": {"family": ["妈妈", "女友"]},
                       "P15": {"family": ["妈妈", "男友"]},
                       "P16": {"family": ["妈妈", "老婆"]},
                       "P06": {"family": ["妻子", "女儿"]}},
    "slots": {
        "boss": ["王经理", "李总监", "科主任"],
        "reward": ["涨薪2000每月", "一次性奖金15000", "升一级加薪15%"],
        "treat": ["海底捞", "楼下日料店"],
        "family": ["妈妈", "女友", "老婆"],
    },
    "beats": [
        {"key": "K1", "t": "10:00", "mod": "mic", "source": "${boss}",
         "texts": ["${boss}把我叫去办公室: ${reward}定了, 继续好好干, 明年还有机会",
                   "谈话时${boss}宣布:${reward}, 这是组织对你今年表现的认可"]},
        {"key": "K2", "t": "12:30", "mod": "app", "source": "工资卡短信",
         "texts": ["工资卡入账短信:${reward}已到账, 看着余额多了一截, 嘴角压不住",
                   "银行短信:${reward}发放成功, 截图发给了${family}报喜"]},
        {"key": "K3", "t": "13:10", "mod": "mic", "source": "同事群",
         "texts": ["高兴请全组喝奶茶, 大刘起哄让我请大餐, 我说${treat}走起",
                   "同事们恭喜声一片, 有人酸溜溜说运气好, 我只当没听见"]},
        {"key": "K4", "t": "18:40", "mod": "mic", "source": "${treat}",
         "texts": ["晚上在${treat}请${family}和朋友吃饭庆祝, 干杯时眼眶有点热",
                   "${treat}里摆了一桌, ${family}说这半年辛苦没白费, 值了"]},
        {"key": "K5", "t": "21:00", "mod": "app", "source": "朋友圈",
         "texts": ["发了条朋友圈: 感恩所有帮助过我的人, 配图是晚餐合影, 点赞破百",
                   "朋友圈报喜后, 前同事纷纷留言恭喜, 还有猎头来加微信"]},
        {"key": "K6", "t": "22:30", "mod": "mic", "source": "独白",
         "texts": ["躺床上盘算: 明年目标再进一步, 先把欠的睡眠补回来",
                   "睡前跟${family}说: 这只是开始, 明年我要拿更高的目标"]},
    ],
    "vitals": {"sleep": (7.0, 8.0), "rest_hr": (60, 68), "steps": (7000, 11000),
               "episodes": [
        {"key": "V1", "t": "10:05", "signal": "heart_rate", "reading": "102bpm",
         "context": "听到${reward}时激动站立(正向情绪)"},
    ]},
    "gt": {
        "global": {
            "core": "${reward}正式落地, 白天受肯定晚上与亲友庆祝, 是收获感拉满的高光一天",
            "syn": ["升职", "加薪", "涨薪", "奖金到账", "受肯定", "庆祝", "高光", "收获", "报喜"],
            "red": ["被裁", "降薪", "分手", "重病", "欠薪", "挨批", "优化"],
            "entities": ["${boss}", "${reward}"], "evidence": ["K1", "K2", "K4"]},
        "dim:health": {
            "core": "体征平稳睡眠充足, 上午因激动心率短暂102bpm属正向情绪波动, 无异常",
            "syn": ["体征平稳", "睡眠充足", "正向波动", "激动", "状态好", "无异常"],
            "red": ["心脏病", "心梗", "失眠", "过劳", "晕倒", "体检异常"],
            "entities": ["102bpm"], "evidence": ["V1"]},
        "dim:social": {
            "core": "与${boss}及同事关系融洽获祝贺; 与${family}分享喜悦感情升温",
            "syn": ["获祝贺", "关系融洽", "分享喜悦", "感情升温", "请客", "人缘好"],
            "red": ["被孤立", "吵架", "分手", "众叛亲离", "领导打压"],
            "entities": ["${boss}", "${family}"], "evidence": ["K3", "K4", "K5"]},
        "dim:emotion": {
            "core": "全天振奋感恩, 上午惊喜中午得意晚上温情, 睡前充满干劲",
            "syn": ["振奋", "感恩", "惊喜", "得意", "温情", "干劲", "开心", "满足"],
            "red": ["抑郁", "崩溃", "焦虑", "绝望", "麻木", "暴怒"],
            "entities": [], "evidence": ["K1", "K4", "K6"]},
        "dim:finance": {
            "core": "${reward}到账, 收入上台阶, 庆祝请客属计划内小额支出",
            "syn": ["${reward}", "到账", "收入上涨", "请客", "计划内支出"],
            "red": ["亏损", "债务", "断供", "被骗", "入不敷出"],
            "entities": ["${reward}"], "evidence": ["K2", "K4"]},
        "dim:career": {
            "core": "升职加薪正式兑现, 年内表现获组织认可, 为明年更高目标铺路",
            "syn": ["升职", "加薪", "兑现", "获认可", "表现肯定", "更上一层"],
            "red": ["被否", "整改", "优化", "降级", "开除", "待业"],
            "entities": ["${boss}", "${reward}"], "evidence": ["K1", "K6"]},
    },
    "background": ["买咖啡", "取快递", "抢红包"],
})

# A04 体检惊魂
ARCS.append({
    "arc_id": "A04_MEDICAL_SCARE", "title": "体检异常与复查",
    "personas": ["P07", "P08", "P09", "P13"],
    "gt_overrides": {"P09": {"dim:career": {
        "core": "退休日常被就医打乱, 老年大学请假一天, 全天围着复查转",
        "syn": ["就医", "请假", "日常打乱", "围着复查转", "老年大学"],
        "red": ["升职", "签大单", "全勤", "被开除", "返聘"],
        "entities": ["${hospital}"], "evidence": ["K0", "K2"]}}},
    "slots": {
        "hospital": ["市第一人民医院", "省人民医院"],
        "indicator": ["肺部8mm小结节", "糖化血红蛋白9.2%", "肌钙蛋白轻度升高"],
        "doctor": ["李医生", "陈主任"],
        "family": ["老伴", "女儿", "儿子"],
        "exam": ["增强CT", "动态心电图", "糖耐量复查"],
        "cost": ["1200元", "800元"],
    },
    "beats": [
        {"key": "K0", "t": "09:00", "mod": "app", "source": "上午安排",
         "texts": ["上午请了半天假去${hospital}, 活儿先交给副手顶着",
                   "跟单位请假: 上午去${hospital}看报告, 下午回来"],
         "persona_texts": {"P09": [
                   "上午推了老年大学的课去${hospital}, 跟班长请了假",
                   "老年大学请假一天: 上午去${hospital}看报告"]}},
        {"key": "K1", "t": "08:30", "mod": "app", "source": "体检中心",
         "texts": ["体检报告推送:${indicator}, 提示尽快专科复查, 手一抖手机差点掉了",
                   "手机一亮是体检报告:${indicator}标红, 建议两周内复查"]},
        {"key": "K2", "t": "10:20", "mod": "mic", "source": "${doctor}",
         "texts": ["${doctor}看完片子说: 先别自己吓自己, 做个${exam}再看, 大概率没事",
                   "${doctor}: ${indicator}先复查个${exam}, 熬夜酒局都先停了"]},
        {"key": "K3", "t": "12:00", "mod": "mic", "source": "${family}",
         "texts": ["没敢跟${family}说实话, 只说复查个小毛病, 对方还没起疑",
                   "电话里${family}一听就急了: 早让你戒烟少喝酒你不听, 吵了几句"]},
        {"key": "K4", "t": "15:40", "mod": "app", "source": "医院缴费",
         "texts": ["${exam}缴费${cost}, 自费部分不少, 咬咬牙付了",
                   "缴费单:${exam}${cost}, 排到下周三做, 这几天只能干等"]},
        {"key": "K5", "t": "19:30", "mod": "mic", "source": "${family}",
         "texts": ["饭桌上${family}翻旧账: 去年就让你查你拖到今年, 万一有事咋办",
                   "晚上${family}边哭边数落, 我一声不敢吭, 默默把烟掐了"]},
        {"key": "K6", "t": "22:00", "mod": "mic", "source": "独白",
         "texts": ["躺床上翻来覆去, 万一复查不好, 家里老小可咋办",
                   "越想越怕, 把${exam}的注意事项看了三遍, 凌晨才迷糊着"]},
    ],
    "vitals": {"sleep": (4.6, 5.6), "rest_hr": (76, 84), "steps": (3500, 6000),
               "episodes": [
        {"key": "V1", "t": "08:35", "signal": "heart_rate", "reading": "118bpm",
         "context": "看到${indicator}报告时"},
        {"key": "V2", "t": "19:35", "signal": "heart_rate", "reading": "110bpm",
         "context": "与${family}争执时"},
    ]},
    "gt": {
        "global": {
            "core": "体检查出${indicator}赴${hospital}复查待定, 与${family}为此争执, 全天在恐慌与等待中煎熬",
            "syn": ["体检异常", "${indicator}", "复查待定", "恐慌", "等待煎熬", "家人争执", "虚惊待定"],
            "red": ["确诊癌症", "心梗发作", "病危", "手术成功", "完全健康", "报告正常"],
            "entities": ["${hospital}", "${indicator}", "${family}"], "evidence": ["K1", "K2", "K5"]},
        "dim:health": {
            "core": "${indicator}异常待${exam}复查, 当日两次情绪性心率升高, 睡眠差, 需戒烟酒等结果",
            "syn": ["${indicator}", "异常", "复查", "${exam}", "心率升高", "118", "睡眠差", "待定"],
            "red": ["确诊", "晚期", "心梗", "猝死", "痊愈", "一切正常"],
            "entities": ["${indicator}", "${exam}"], "evidence": ["K1", "K2", "V1"]},
        "dim:social": {
            "core": "与${family}因瞒报病情与旧习惯争执; 与${doctor}建立复查跟进关系",
            "syn": ["家人争执", "瞒报", "翻旧账", "医生跟进", "复查", "关心则乱"],
            "red": ["家庭和睦无争", "离婚", "断绝关系", "医患冲突"],
            "entities": ["${family}", "${doctor}"], "evidence": ["K3", "K5"]},
        "dim:emotion": {
            "core": "早惊慌午强撑晚后怕, 主基调是恐惧与自责, 深夜靠刷注意事项缓解焦虑",
            "syn": ["惊慌", "后怕", "恐惧", "自责", "强撑", "焦虑", "煎熬"],
            "red": ["满不在乎", "欣喜若狂", "心如止水", "暴怒伤人"],
            "entities": [], "evidence": ["K1", "K5", "K6"]},
        "dim:finance": {
            "core": "${exam}花费${cost}多为自费, 后续治疗费未知, 开始盘算家底",
            "syn": ["${cost}", "检查费", "自费", "盘算家底", "治疗费未知"],
            "red": ["巨额账单", "倾家荡产", "一夜暴富", "全额报销"],
            "entities": ["${exam}", "${cost}"], "evidence": ["K4"]},
        "dim:career": {
            "core": "因就医请假半天工作分心, 活儿交副手, 复查前无心推进正事",
            "syn": ["请假", "就医", "工作分心", "无心工作", "交副手"],
            "red": ["升职", "签大单", "全勤", "被开除", "项目成功"],
            "entities": ["${hospital}"], "evidence": ["K0", "K2"]},
    },
    "background": ["买咖啡", "取快递", "点外卖"],
    "twist": {
        "beat": {"key": "T1", "t": "13:00", "mod": "mic", "source": "给子女打电话",
                 "texts": ["跟孩子说: 我没事, 就是常规复查, 你们忙你们的别回来 (其实手一直在抖)"]},
        "patch": {"dim:emotion": {
            "suffix": "; 对子女逞强隐瞒, 独自承受恐惧",
            "syn_add": ["逞强", "隐瞒", "独自承受"], "red_add": ["坦然告知", "毫不在意"]}},
        "evidence_add": {"dim:emotion": ["T1"], "dim:social": ["T1"]},
    },
})

# A05 老人跌倒
ARCS.append({
    "arc_id": "A05_ELDER_FALL", "title": "老人跌倒送医",
    "personas": ["P10", "P09"],
    "slot_overrides": {"P10": {"patient": ["自己"]},
                       "P09": {"patient": ["老伴老刘"]}},
    "gt_overrides": {"P09": {
        "global": {
            "core": "老伴在${place}跌倒致${injury}送医留观, ${child}连夜赶回, 独居老两口安全风险拉响警报",
            "syn": ["老伴跌倒", "摔倒", "送医", "留观", "${injury}", "子女赶回", "独居风险", "虚惊一场"],
            "red": ["当场去世", "瘫痪", "安然无恙", "旅游", "体检正常"],
            "entities": ["${place}", "${child}", "${injury}"], "evidence": ["K1", "K4", "K6"]},
        "dim:health": {
            "core": "老伴${injury}留观无生命危险, 本人受惊116bpm, 老两口都需要人照应",
            "syn": ["老伴", "${injury}", "留观", "受惊", "116", "照应", "无生命危险"],
            "red": ["去世", "瘫痪", "脑出血病危", "毫发无损"],
            "entities": ["${place}", "${injury}"], "evidence": ["K1", "V1", "K4"]},
        "dim:emotion": {
            "core": "目睹老伴跌倒惊吓自责, 怕拖累${child}, 落定后转为后怕庆幸",
            "syn": ["惊吓", "自责", "拖累", "后怕", "庆幸", "焦急"],
            "red": ["开心", "无所谓", "大吵大闹", "绝望轻生"],
            "entities": ["${child}"], "evidence": ["K2", "K3", "K6"]}}},
    "slots": {
        "patient": ["自己", "老伴老刘"],
        "place": ["卫生间", "楼道台阶", "菜市场门口"],
        "child": ["儿子建国", "女儿小慧"],
        "hospital": ["市骨科医院", "区人民医院"],
        "injury": ["手腕骨折打了石膏", "髋部挫伤需留观", "额头缝了四针"],
        "cost": ["住院押金5000元", "检查加药费3200元"],
        "helper": ["邻居小赵", "楼下老李"],
    },
    "beats": [
        {"key": "K1", "t": "07:40", "mod": "sensor", "source": "手环IMU",
         "texts": ["${place}检测到8.2g冲击后静止90秒, 疑似跌倒, 已触发告警",
                   "早7点40${place}一次剧烈冲击, 随后长时间静止, 判定为跌倒事件"]},
        {"key": "K2", "t": "07:55", "mod": "mic", "source": "${helper}",
         "texts": ["${helper}听到动静赶来: 可别乱动, 我打120, 再给你儿女打电话",
                   "多亏${helper}发现得早, 扶着坐下, 第一时间叫了救护车"]},
        {"key": "K3", "t": "09:30", "mod": "app", "source": "${child}电话",
         "texts": ["${child}在电话里急了: 我马上请假赶回来, 你千万别乱动, 听医生的",
                   "${child}: 爸/妈你撑住, 我订了最近的高铁, 下午就到"]},
        {"key": "K4", "t": "11:20", "mod": "mic", "source": "急诊医生",
         "texts": ["急诊医生: ${injury}, 先留观两天, 万幸没伤到要害",
                   "医生说${injury}, 需要留院观察, 家属尽快赶到签字"]},
        {"key": "K5", "t": "15:00", "mod": "app", "source": "医院缴费",
         "texts": ["${cost}, ${child}手机远程缴的, 让老人安心治",
                   "缴费通知:${cost}, 好在医保能报大头"]},
        {"key": "K6", "t": "20:10", "mod": "mic", "source": "${child}",
         "texts": ["${child}赶到病床前: 出院就请个护工, 再装扶手和报警器, 不能再独居冒险了",
                   "病床前${child}红着眼: 以后每周视频查岗, 摔倒报警器必须24小时戴着"]},
    ],
    "vitals": {"sleep": (5.5, 6.5), "rest_hr": (72, 80), "steps": (800, 2000),
               "episodes": [
        {"key": "V1", "t": "07:40", "signal": "fall_impact", "reading": "8.2g冲击后静止90秒",
         "context": "${place}跌倒"},
        {"key": "V2", "t": "08:10", "signal": "heart_rate", "reading": "116bpm",
         "context": "跌倒后惊吓静卧"},
    ]},
    "gt": {
        "global": {
            "core": "老人在${place}跌倒致${injury}送医留观, ${child}连夜赶回, 暴露独居安全风险",
            "syn": ["老人跌倒", "摔倒", "送医", "留观", "${injury}", "子女赶回", "独居风险", "虚惊一场"],
            "red": ["当场去世", "瘫痪", "安然无恙", "旅游", "体检正常"],
            "entities": ["${place}", "${child}", "${injury}"], "evidence": ["K1", "K4", "K6"]},
        "dim:health": {
            "core": "${place}跌倒8.2g冲击, ${injury}, 留院观察, 万幸无生命危险",
            "syn": ["跌倒", "8.2g", "冲击", "${injury}", "留观", "观察", "骨折", "外伤"],
            "red": ["去世", "瘫痪", "脑出血病危", "毫发无损", "生龙活虎"],
            "entities": ["${place}", "${injury}"], "evidence": ["K1", "V1", "K4"]},
        "dim:social": {
            "core": "${helper}第一时间施救报警; ${child}放下一切赶回尽孝; 医患配合顺利",
            "syn": ["邻里相助", "施救", "子女赶回", "尽孝", "报警", "医患配合"],
            "red": ["无人问津", "子女不孝", "碰瓷", "医患冲突", "众叛亲离"],
            "entities": ["${helper}", "${child}"], "evidence": ["K2", "K3", "K6"]},
        "dim:emotion": {
            "core": "老人惊吓后怕且愧疚拖累子女; 子女焦急自责; 落定后转为后怕庆幸",
            "syn": ["惊吓", "后怕", "愧疚", "拖累", "焦急", "自责", "庆幸"],
            "red": ["开心", "无所谓", "大吵大闹", "绝望轻生"],
            "entities": ["${child}"], "evidence": ["K2", "K3", "K6"]},
        "dim:finance": {
            "core": "${cost}, 子女远程垫付, 医保覆盖大头, 另拟添置护工扶手开支",
            "syn": ["${cost}", "医药费", "垫付", "医保", "护工开支"],
            "red": ["天价账单", "无钱医治", "倾家荡产", "骗保"],
            "entities": ["${cost}"], "evidence": ["K5", "K6"]},
        "dim:career": {
            "core": "退休日常被就医打断; ${child}请假误工; 后续将安排护工与居家适老改造",
            "syn": ["就医", "请假", "误工", "护工", "适老改造", "日常打断"],
            "red": ["升职", "开工", "签单", "全勤", "退休金停发"],
            "entities": ["${child}"], "evidence": ["K3", "K6"]},
    },
    "background": ["买菜", "取快递", "听收音机"],
    "twist": {
        "beat": {"key": "T1", "t": "08:05", "mod": "mic", "source": "老人",
                 "texts": ["老人摆手: 躺躺就好, 别叫120, 别跟孩子说, 不能耽误他们上班 (被${helper}硬劝住)"],
                 "persona_texts": {"P09": [
                     "老伴摆手: 躺躺就好, 别叫120, 别跟孩子说, 不能耽误他们上班 (被我和${helper}硬劝住)"]}},
        "patch": {"dim:emotion": {
            "suffix": "; 初时逞强拒医怕拖累子女, 被邻里劝住才就医",
            "syn_add": ["逞强", "拒医", "怕拖累"], "red_add": ["主动求医", "毫不担心"]}},
        "evidence_add": {"dim:emotion": ["T1"]},
    },
})

# A06 孩子学校受伤
ARCS.append({
    "arc_id": "A06_CHILD_SCHOOL_ACCIDENT", "title": "孩子学校受伤",
    "personas": ["P16"],
    "slots": {
        "kid": ["女儿Mia6岁"],
        "teacher": ["王老师", "李老师"],
        "injury": ["额头磕破缝了三针", "手腕骨折打了石膏"],
        "spouse": ["老婆"],
        "cost": ["医药费2300元", "检查治疗费4100元"],
        "boss": ["王经理", "李总监"],
    },
    "beats": [
        {"key": "K1", "t": "10:10", "mod": "app", "source": "${teacher}电话",
         "texts": ["${teacher}来电:${kid}课间摔了, ${injury}, 你赶紧来医院一趟",
                   "学校电话很急:${kid}受伤${injury}, 校医已处理, 家长速到"]},
        {"key": "K2", "t": "10:40", "mod": "app", "source": "请假",
         "texts": ["跟${boss}请假:${boss}准了但说项目会你缺席, 纪要自己补",
                   "请假条秒批, ${boss}补了句: 下午评审你赶不回来就让小刘替你讲"]},
        {"key": "K3", "t": "12:30", "mod": "mic", "source": "急诊医生",
         "texts": ["医生:${injury}, 需观察一晚, 万幸没伤到骨头/要害, 家长别慌",
                   "医生处理完说: ${injury}, 回家静养一周, 有情况随时复诊"]},
        {"key": "K4", "t": "14:00", "mod": "app", "source": "${spouse}微信",
         "texts": ["${spouse}: 都怪你平时不管孩子! 野成这样! (语音60秒, 越说越激动)",
                   "跟${spouse}在微信里吵起来: 对方指责缺席陪伴, 我回呛工作不要了?"]},
        {"key": "K5", "t": "16:20", "mod": "app", "source": "医院缴费",
         "texts": ["${cost}, 学校说走校方责任险, 先垫付后理赔",
                   "缴费${cost}, 护士说记得留好票据, 保险理赔要用"]},
        {"key": "K6", "t": "21:30", "mod": "mic", "source": "病床前",
         "texts": ["哄${kid}睡觉: 以后慢点跑, 爸爸这周天天陪你, 心里愧疚得不行",
                   "${kid}睡前问还疼不疼转移话题, 我鼻子一酸, 保证以后多陪伴"]},
    ],
    "vitals": {"sleep": (5.6, 6.6), "rest_hr": (72, 78), "steps": (5000, 8000),
               "episodes": [
        {"key": "V1", "t": "10:12", "signal": "heart_rate", "reading": "120bpm",
         "context": "接到${teacher}电话时"},
    ]},
    "gt": {
        "global": {
            "core": "${kid}在校受伤${injury}送医, 请假陪护缺席工作, 与${spouse}爆发缺席指责争吵, 深夜自责",
            "syn": ["孩子受伤", "${injury}", "送医", "请假陪护", "夫妻争吵", "缺席指责", "自责"],
            "red": ["孩子无恙", "家庭和睦", "升职", "旅游", "孩子离家出走"],
            "entities": ["${kid}", "${injury}", "${spouse}"], "evidence": ["K1", "K3", "K4"]},
        "dim:health": {
            "core": "本人接电话时应激120bpm后回落; ${kid}${injury}需静养观察, 无大碍",
            "syn": ["应激", "120", "回落", "${injury}", "静养", "观察", "无大碍"],
            "red": ["病危", "重伤", "残疾", "本人晕倒", "猝死"],
            "entities": ["${kid}", "${injury}"], "evidence": ["V1", "K3"]},
        "dim:social": {
            "core": "与${spouse}因育儿缺席激烈争吵; 与${teacher}校方配合处理; 与${kid}愧疚修复",
            "syn": ["夫妻争吵", "育儿缺席", "指责", "校方配合", "愧疚修复", "陪伴承诺"],
            "red": ["离婚", "家暴", "老死不相往来", "师生恋", "医患冲突"],
            "entities": ["${spouse}", "${teacher}", "${kid}"], "evidence": ["K1", "K4", "K6"]},
        "dim:emotion": {
            "core": "上午惊惶下午委屈晚上愧疚, 主基调是为人父母的自责与后怕",
            "syn": ["惊惶", "委屈", "愧疚", "后怕", "自责", "心疼孩子"],
            "red": ["开心", "无所谓", "冷漠", "暴怒伤人", "幸灾乐祸"],
            "entities": ["${kid}"], "evidence": ["K1", "K4", "K6"]},
        "dim:finance": {
            "core": "${cost}先行垫付, 后续走校方责任险理赔, 另缺勤半天",
            "syn": ["${cost}", "垫付", "理赔", "校方责任险", "缺勤"],
            "red": ["巨额赔偿", "倾家荡产", "讹诈", "拒赔"],
            "entities": ["${cost}"], "evidence": ["K5", "K2"]},
        "dim:career": {
            "core": "临时请假缺席项目会与评审, 工作交同事代讲, 职场形象小受损",
            "syn": ["请假", "缺席", "评审", "代讲", "工作受影响"],
            "red": ["升职", "签单", "全勤", "被开除", "嘉奖"],
            "entities": ["${boss}"], "evidence": ["K2"]},
    },
    "background": ["买咖啡", "取快递", "点外卖"],
})

# A07 投资亏损
ARCS.append({
    "arc_id": "A07_INVESTMENT_LOSS", "title": "投资暴跌与朋友赖账",
    "personas": ["P05", "P08", "P13", "P16"],
    "slot_overrides": {"P05": {"spouse": ["前妻", "我妈"]},
                       "P08": {"spouse": ["老公"]},
                       "P13": {"spouse": ["老婆"]},
                       "P16": {"spouse": ["老婆"]}},
    "gt_overrides": {"P05": {"dim:career": {
        "core": "全天沉迷行情与复盘, 简历一封没投, 求职停滞一日",
        "syn": ["沉迷行情", "复盘", "求职停滞", "没投简历", "分心"],
        "red": ["升职", "签单", "加薪", "拿到offer", "创业成功"],
        "entities": [], "evidence": ["K1", "K6"]}}},
    "slots": {
        "product": ["重仓的股票", "买的基金组合", "碰的虚拟币"],
        "loss": ["浮亏12万", "本金腰斩亏8万", "一天蒸发6万"],
        "friend": ["发小大刘", "老同学阿坤"],
        "debt": ["借出去的5万", "搭进去的3万"],
        "spouse": ["老婆", "老公", "家里人"],
    },
    "beats": [
        {"key": "K1", "t": "09:30", "mod": "app", "source": "行情软件",
         "texts": ["开盘${product}直接砸跌停, ${loss}, 手抖得拿不住手机",
                   "${product}一路跳水, ${loss}, 补仓的钱也没了"]},
        {"key": "K2", "t": "11:20", "mod": "mic", "source": "${friend}电话",
         "texts": ["${friend}来电:${debt}再缓缓, 我这边也周转不开了, 年底一定还",
                   "打电话催${friend}还${debt}, 对方诉苦说再宽限半年, 话不投机"]},
        {"key": "K3", "t": "13:00", "mod": "mic", "source": "${spouse}",
         "texts": ["${spouse}知道后炸了: 当初不让你碰你非不听, 现在全家喝西北风?",
                   "饭桌上${spouse}翻旧账: 去年赚的这下全吐回去还倒贴, 越说越气"]},
        {"key": "K4", "t": "15:00", "mod": "app", "source": "券商确认",
         "texts": ["咬牙清仓确认短信: 割肉离场, 账户只剩零头, 三年白干",
                   "券商成交回报: 全部清仓${loss}坐实, 销户的心都有了"]},
        {"key": "K5", "t": "18:30", "mod": "mic", "source": "饭桌亲戚",
         "texts": ["亲戚问最近投资咋样, 我打哈哈说还行, 低头扒饭不敢接话",
                   "席间有人炫耀抄底赚了, 我默默喝水, 像被扇了一耳光"]},
        {"key": "K6", "t": "23:00", "mod": "mic", "source": "独白",
         "texts": ["半夜拿计算器一笔笔算, ${loss}加${debt}要不回来, 整宿失眠没睡",
                   "凌晨三点失眠还在复盘: 贪婪加杠杆, 活该, 明天开始戒掉行情软件"]},
    ],
    "vitals": {"sleep": (4.0, 5.0), "rest_hr": (76, 84), "steps": (3000, 5500),
               "episodes": [
        {"key": "V1", "t": "09:35", "signal": "heart_rate", "reading": "115bpm",
         "context": "看到${loss}时静坐"},
    ]},
    "gt": {
        "global": {
            "core": "${product}暴跌${loss}割肉离场, ${friend}所欠${debt}又要不回, 与家人爆发争吵, 深夜失眠算账",
            "syn": ["暴跌", "${loss}", "割肉", "清仓", "亏损", "要不回欠款", "家人争吵", "失眠算账"],
            "red": ["大赚", "涨停", "财务自由", "欠款收回", "家庭和睦", "抄底成功"],
            "entities": ["${product}", "${loss}", "${friend}"], "evidence": ["K1", "K2", "K4"]},
        "dim:health": {
            "core": "受刺激心率115bpm, 整夜失眠复盘, 胃口全无, 神经高度紧绷",
            "syn": ["115", "失眠", "复盘", "紧绷", "胃口差", "心慌", "刺激"],
            "red": ["心脏病发", "猝死", "酣睡", "胃口大开", "跑马拉松"],
            "entities": ["失眠"], "evidence": ["V1", "K6"]},
        "dim:social": {
            "core": "与${friend}因${debt}生隙; 与${spouse}激烈争吵; 亲戚面前颜面扫地强撑",
            "syn": ["欠款生隙", "争吵", "翻旧账", "颜面扫地", "强撑", "催债"],
            "red": ["和解", "如数归还", "家庭和睦", "众星捧月"],
            "entities": ["${friend}", "${spouse}"], "evidence": ["K2", "K3", "K5"]},
        "dim:emotion": {
            "core": "从震惊到愤怒再到羞耻自责, 深夜陷入悔恨反刍, 接近崩溃",
            "syn": ["震惊", "愤怒", "羞耻", "自责", "悔恨", "反刍", "崩溃"],
            "red": ["开心", "淡定", "知足", "无所谓", "意气风发"],
            "entities": [], "evidence": ["K1", "K3", "K6"]},
        "dim:finance": {
            "core": "${product}${loss}已割肉坐实, ${debt}回收无望, 家庭资产大幅缩水",
            "syn": ["${loss}", "割肉", "坐实", "资产缩水", "欠款难收", "清仓"],
            "red": ["盈利", "回本", "欠款收回", "存款增加", "理财大赚"],
            "entities": ["${loss}", "${debt}"], "evidence": ["K1", "K2", "K4"]},
        "dim:career": {
            "core": "全天无心正业沉迷行情与复盘, 本职工作停滞一日",
            "syn": ["无心工作", "沉迷行情", "工作停滞", "分心"],
            "red": ["升职", "签单", "加薪", "创业成功", "被开除"],
            "entities": [], "evidence": ["K1", "K6"]},
    },
    "background": ["买咖啡", "取快递", "刷短视频"],
})

# A08 签约收款 (正向)
ARCS.append({
    "arc_id": "A08_CONTRACT_SIGNED", "title": "大单签约与尾款到账",
    "personas": ["P07", "P13"],
    "slots": {
        "partner": ["恒宇建材王总", "加盟商李老板", "商场张经理"],
        "amount": ["尾款28万", "加盟费15万", "结算款42万"],
        "crew": ["班组兄弟", "店员们"],
        "family": ["老婆", "家里人"],
    },
    "beats": [
        {"key": "K1", "t": "10:30", "mod": "mic", "source": "${partner}",
         "texts": ["跟${partner}最后拉扯一小时, 对方终于松口: 行, 按你说的办, 下午签约",
                   "谈判桌上${partner}拍板: 不磨了, ${amount}的事就这么定"]},
        {"key": "K2", "t": "14:00", "mod": "mic", "source": "签约现场",
         "texts": ["合同一式两份签字盖章, 悬了三个月的心终于落地",
                   "签字落章握手合影, ${partner}说: 合作愉快, 下期还找你"]},
        {"key": "K3", "t": "16:40", "mod": "app", "source": "银行短信",
         "texts": ["银行短信:${amount}已到账, 看着余额笑出声, 赶紧截图发群里",
                   "到账提醒:${amount}, 比约定的还早两天, 对方讲究"]},
        {"key": "K4", "t": "18:00", "mod": "mic", "source": "${crew}",
         "texts": ["晚上摆庆功宴, 给${crew}每人包了红包: 没你们卖力就没有今天",
                   "${crew}起哄敬酒, 我说: 钱已到账, 工资奖金明天一分不少发"]},
        {"key": "K5", "t": "20:20", "mod": "app", "source": "家庭群",
         "texts": ["家庭群报喜:${amount}到账了! ${family}回了三个大拇指",
                   "在家庭群发了签约合影, ${family}说: 这下能睡个安稳觉了"]},
        {"key": "K6", "t": "22:00", "mod": "mic", "source": "独白",
         "texts": ["睡前盘算: 明年再接一单, 规模扩大一倍, 好日子在后头",
                   "躺床上还在笑, 三个月的奔波值了, 明天开始张罗下一单"]},
    ],
    "vitals": {"sleep": (6.8, 7.8), "rest_hr": (64, 72), "steps": (8000, 13000),
               "episodes": [
        {"key": "V1", "t": "16:42", "signal": "heart_rate", "reading": "104bpm",
         "context": "看到${amount}到账时激动"},
    ]},
    "gt": {
        "global": {
            "core": "鏖战三月的大单终签约且${amount}到账, 晚上摆庆功宴, 苦尽甘来的丰收日",
            "syn": ["签约", "落定", "到账", "${amount}", "庆功", "丰收", "苦尽甘来", "合作愉快"],
            "red": ["毁约", "跑路", "欠款", "亏损", "官司", "资金链断裂"],
            "entities": ["${partner}", "${amount}"], "evidence": ["K2", "K3", "K4"]},
        "dim:health": {
            "core": "体征平稳睡眠好, 到账瞬间激动104bpm属正向波动, 连日疲惫一扫而空",
            "syn": ["平稳", "睡眠好", "正向波动", "104", "疲惫消散", "状态佳"],
            "red": ["心脏病", "过劳倒下", "失眠", "住院"],
            "entities": [], "evidence": ["V1"]},
        "dim:social": {
            "core": "与${partner}合作落定互信加深; 犒劳${crew}凝聚人心; 与${family}分享喜悦",
            "syn": ["合作落定", "互信", "犒劳", "凝聚", "分享喜悦", "报喜"],
            "red": ["翻脸", "讨薪", "众叛亲离", "家庭争吵"],
            "entities": ["${partner}", "${crew}"], "evidence": ["K2", "K4", "K5"]},
        "dim:emotion": {
            "core": "从上午紧张到下午狂喜再到晚上踏实, 主基调扬眉吐气",
            "syn": ["紧张", "狂喜", "踏实", "扬眉吐气", "开心", "满足"],
            "red": ["焦虑", "崩溃", "绝望", "抑郁", "暴怒"],
            "entities": [], "evidence": ["K1", "K3", "K6"]},
        "dim:finance": {
            "core": "${amount}到账现金流转正, 另支出庆功宴与红包, 财务大好",
            "syn": ["${amount}", "到账", "现金流转正", "财务大好", "回款"],
            "red": ["坏账", "亏损", "断链", "被骗", "入不敷出"],
            "entities": ["${amount}"], "evidence": ["K3", "K4"]},
        "dim:career": {
            "core": "关键合同落地开启新阶段, 口碑与规模双升, 已在谋划下一单",
            "syn": ["合同落地", "新阶段", "口碑", "扩大规模", "下一单"],
            "red": ["丢单", "停工", "吊销执照", "破产", "失业"],
            "entities": ["${partner}"], "evidence": ["K2", "K6"]},
    },
    "background": ["买咖啡", "取快递", "刷朋友圈"],
})

# A09 自由插画师维权
ARCS.append({
    "arc_id": "A09_FREELANCE_CLIENT_CONFLICT", "title": "甲方压稿与维权",
    "personas": ["P14"],
    "slots": {
        "client": ["蓝湾食品市场部", "游戏公司美术外包组"],
        "round": ["第18版", "第12版", "第9版"],
        "pay": ["尾款9000", "尾款1万2", "加急费3000"],
        "peer": ["同行阿梨", "画手群老猫"],
    },
    "beats": [
        {"key": "K1", "t": "10:00", "mod": "app", "source": "${client}",
         "texts": ["${client}: ${round}再调调, 感觉还是差点意思, ${pay}先压着等终版一起结",
                   "甲方消息: ${round}不行, 推倒重来吧, 对了${pay}流程先暂停"]},
        {"key": "K2", "t": "12:40", "mod": "mic", "source": "独白",
         "texts": ["颈椎僵得转不动, 右手手麻又犯了, 贴了膏药继续画, 全职自由职业的代价",
                   "画到一半手麻得握不住笔, 热敷十分钟才缓过来, 颈椎又在报警"]},
        {"key": "K3", "t": "15:20", "mod": "mic", "source": "${client}电话",
         "texts": ["电话里摊牌: 合同写明三版确稿, 超出要么加钱要么先结${pay}, 不能白嫖",
                   "据理力争一小时: 改可以, 按合同加钱, ${pay}今天必须先结一半"]},
        {"key": "K4", "t": "17:00", "mod": "app", "source": "${client}",
         "texts": ["对方妥协: 先结一半, 剩下终版后三天内结清, 停战",
                   "甲方松口: ${pay}先付50%, 后续修改按次计费, 算是守住了底线"]},
        {"key": "K5", "t": "19:30", "mod": "app", "source": "${peer}",
         "texts": ["跟${peer}吐槽全程, 对方说: 你算硬气的, 我上次被白嫖了整套",
                   "${peer}分享维权经验: 下次合同加杀手锏条款, 尾款比例提到40%"]},
        {"key": "K6", "t": "23:00", "mod": "mic", "source": "独白",
         "texts": ["熬夜赶终版, 脖子上敷着热毛巾, 猫在键盘上睡着了, 凌晨一点收工",
                   "改完终版已是深夜, 颈椎贴满膏药, 但想到守住${pay}就值了"]},
    ],
    "vitals": {"sleep": (5.0, 6.0), "rest_hr": (68, 74), "steps": (800, 1800),
               "episodes": [
        {"key": "V1", "t": "18:00", "signal": "sedentary", "reading": "连续静坐11小时",
         "context": "赶稿久坐, 颈椎手麻加重"},
        {"key": "V2", "t": "15:25", "signal": "heart_rate", "reading": "109bpm",
         "context": "与${client}电话争执时"},
    ]},
    "gt": {
        "global": {
            "core": "甲方${round}反复压稿并扣${pay}, 据理力争守住底线对方妥协先结一半, 代价是颈椎加重与熬夜赶稿",
            "syn": ["压稿", "反复修改", "扣尾款", "维权", "据理力争", "妥协", "守住底线", "熬夜赶稿"],
            "red": ["甲方爽快结款", "一稿过", "白嫖成功", "解约", "转行送外卖"],
            "entities": ["${client}", "${pay}"], "evidence": ["K1", "K3", "K4"]},
        "dim:health": {
            "core": "颈椎压迫致手麻加重, 久坐11小时, 熬夜赶稿睡眠不足, 身体透支",
            "syn": ["颈椎", "手麻", "久坐", "11小时", "熬夜", "睡眠不足", "透支", "膏药"],
            "red": ["生龙活虎", "马拉松", "体检优秀", "早睡早起"],
            "entities": ["颈椎", "手麻"], "evidence": ["K2", "V1", "K6"]},
        "dim:social": {
            "core": "与${client}从压榨对峙到达成妥协; 与${peer}抱团取暖交流经验",
            "syn": ["对峙", "妥协", "抱团", "同行支持", "谈判", "守住底线"],
            "red": ["成为朋友", "甲方道歉", "断交拉黑", "众叛亲离"],
            "entities": ["${client}", "${peer}"], "evidence": ["K3", "K4", "K5"]},
        "dim:emotion": {
            "core": "上午憋屈下午愤怒据理晚上疲惫释然, 主基调是打工人的不服与自救",
            "syn": ["憋屈", "愤怒", "不服", "释然", "疲惫", "自救", "硬气"],
            "red": ["开心", "躺平", "绝望", "认命", "暴怒伤人"],
            "entities": [], "evidence": ["K1", "K3", "K6"]},
        "dim:finance": {
            "core": "${pay}追回一半, 剩余终版后结清, 现金流暂时续上但仍有拖欠风险",
            "syn": ["${pay}", "追回一半", "结清", "现金流", "拖欠风险"],
            "red": ["全款到账", "一夜暴富", "血本无归", "被拉黑跑路"],
            "entities": ["${pay}"], "evidence": ["K1", "K4"]},
        "dim:career": {
            "core": "确立按合同收费边界逼退白嫖, 项目推进到终版, 职业议价能力+1",
            "syn": ["合同边界", "议价", "终版", "项目推进", "立规矩"],
            "red": ["丢单", "封杀", "转行", "失业", "一稿封神"],
            "entities": ["${client}"], "evidence": ["K3", "K4", "K6"]},
    },
    "background": ["喂猫", "取快递", "点外卖"],
})

# A10 产检与婆媳
ARCS.append({
    "arc_id": "A10_PREGNANCY_CHECK", "title": "产检指标与月嫂之争",
    "personas": ["P03"],
    "slots": {
        "hospital": ["市妇保院", "省人民医院产科"],
        "indicator": ["血糖偏高", "血压140/90", "胎儿偏大两周"],
        "doctor": ["王主任", "李医生"],
        "spouse": ["老公", "孩儿爸"],
        "mil": ["婆婆", "我妈"],
        "item": ["2万的月嫂", "糖耐复查", "胎心仪"],
    },
    "beats": [
        {"key": "K1", "t": "08:00", "mod": "app", "source": "产检提醒",
         "texts": ["产检提醒: 今日30周大排畸复查, 空腹, 记得带小卡",
                   "医院短信: 您预约的今日产检请按时到, 需空腹抽血"]},
        {"key": "K2", "t": "10:30", "mod": "mic", "source": "${doctor}",
         "texts": ["${doctor}看着单子: ${indicator}, 先别慌, 管住嘴迈开腿, 两周后复查",
                   "${doctor}: ${indicator}是高危信号, 饮食单拿好, 有情况随时来"]},
        {"key": "K3", "t": "12:20", "mod": "mic", "source": "${mil}电话",
         "texts": ["${mil}来电: 请啥${item}, 我们当年都没这些, 把钱省下来买奶粉! 吵了几句",
                   "电话里为${item}吵起来: ${mil}嫌贵说智商税, 我说身体要紧互不相让"]},
        {"key": "K4", "t": "15:00", "mod": "mic", "source": "${spouse}",
         "texts": ["${spouse}两头劝: 妈那边我去说, ${item}该请请, 你安心养胎",
                   "${spouse}站我这边: 钱的事我来想办法, 你别动气, 对宝宝不好"]},
        {"key": "K5", "t": "18:00", "mod": "app", "source": "下单",
         "texts": ["下单了控糖食谱和${item}, 这个月育儿支出又超预算了",
                   "按${doctor}的单子买了吃的用的, 顺带约了两周后的复查号"]},
        {"key": "K6", "t": "21:30", "mod": "mic", "source": "数胎动",
         "texts": ["睡前数胎动: 一小时8次, 宝宝很给面子, 一天的糟心散了一半",
                   "摸着肚子跟宝宝说话: 你要乖, 妈妈把糖戒了, 咱们一起加油"]},
    ],
    "vitals": {"sleep": (6.2, 7.2), "rest_hr": (78, 86), "steps": (4500, 7000),
               "episodes": [
        {"key": "V1", "t": "12:25", "signal": "heart_rate", "reading": "105bpm",
         "context": "与${mil}为${item}争执时"},
    ]},
    "gt": {
        "global": {
            "core": "30周产检${indicator}需饮食管控复查, 又与${mil}为${item}争执, 靠${spouse}调解收场, 母子大体平稳",
            "syn": ["产检", "${indicator}", "复查", "月嫂之争", "婆媳争执", "调解", "母子平稳", "管控"],
            "red": ["流产", "早产", "胎儿危险", "离婚", "婆媳和睦无争"],
            "entities": ["${indicator}", "${mil}", "${item}"], "evidence": ["K2", "K3", "K4"]},
        "dim:health": {
            "core": "孕30周${indicator}亮黄灯, 需控糖饮食两周复查, 争执时心率105, 胎动正常",
            "syn": ["${indicator}", "黄灯", "控糖", "复查", "105", "胎动正常"],
            "red": ["大出血", "子痫", "胎儿窘迫", "住院保胎", "完全正常"],
            "entities": ["${indicator}"], "evidence": ["K2", "V1", "K6"]},
        "dim:social": {
            "core": "与${mil}因育儿观念冲突; ${spouse}居中调解站妻; 与${doctor}建立复查随访",
            "syn": ["婆媳冲突", "观念差异", "调解", "站队", "随访"],
            "red": ["婆媳反目", "离婚", "断绝关系", "从无争执"],
            "entities": ["${mil}", "${spouse}", "${doctor}"], "evidence": ["K3", "K4"]},
        "dim:emotion": {
            "core": "上午担忧中午委屈晚上被胎动治愈, 主基调先抑后扬",
            "syn": ["担忧", "委屈", "治愈", "先抑后扬", "母爱", "安心"],
            "red": ["产前抑郁", "崩溃", "绝望", "狂喜", "麻木"],
            "entities": [], "evidence": ["K2", "K3", "K6"]},
        "dim:finance": {
            "core": "新增${item}与控糖食品开支, 育儿预算超支, 复查费用待定",
            "syn": ["${item}", "超预算", "育儿开支", "复查费"],
            "red": ["巨额账单", "入不敷出", "中彩票", "存款翻倍"],
            "entities": ["${item}"], "evidence": ["K3", "K5"]},
        "dim:career": {
            "core": "产假前工作交接中, 今日全天请假产检, 职场暂时挂起",
            "syn": ["请假产检", "交接", "产假", "职场挂起"],
            "red": ["升职", "被裁", "复工", "创业"],
            "entities": [], "evidence": ["K1", "K2"]},
    },
    "background": ["买水果", "取快递", "刷母婴群"],
})

# A11 货车抛锚+盗刷
ARCS.append({
    "arc_id": "A11_TRUCK_BREAKDOWN", "title": "高速抛锚与油卡盗刷",
    "personas": ["P04"],
    "slots": {
        "place": ["京港澳高速驻马店段", "连霍高速服务区附近"],
        "fault": ["右后轮爆胎", "尿素泵故障锁速"],
        "owner": ["货主刘老板", "配货站老陈"],
        "fee": ["拖车800加维修2400", "换胎加急1800"],
        "theft": ["油卡异地盗刷1200", "ETC被盗刷860"],
        "family": ["老婆", "家里"],
    },
    "beats": [
        {"key": "K1", "t": "07:10", "mod": "mic", "source": "${owner}电话",
         "texts": ["${owner}催命: 这批货中午前必须到, 晚一小时扣500, 你看着办",
                   "一大早${owner}来电: 客户等着卸货, 今天必须到, 误了我找别人了"]},
        {"key": "K2", "t": "09:40", "mod": "mic", "source": "独白",
         "texts": ["${place}${fault}, 车直接趴窝, 三角牌一摆, 心凉了半截",
                   "一声巨响${fault}, 65吨的车晃了晃停在${place}应急道, 赶紧打双闪报警"]},
        {"key": "K3", "t": "10:20", "mod": "app", "source": "救援电话",
         "texts": ["救援+维修报价${fee}, 高速上没得选, 咬牙认了",
                   "打了三家救援比价, 最低也要${fee}, 只能先修"]},
        {"key": "K4", "t": "12:00", "mod": "app", "source": "油卡短信",
         "texts": ["油卡短信:${theft}, 车在${place}趴着, 卡却在两百公里外消费, 见鬼了",
                   "屋漏偏逢连夜雨:${theft}, 赶紧挂失报警, 钱不知追不追得回"]},
        {"key": "K5", "t": "15:30", "mod": "mic", "source": "${owner}电话",
         "texts": ["修好上路给${owner}回电, 对方骂了五分钟: 扣钱! 下次不用你了!",
                   "${owner}听说晚点直接开骂, 扣运费不说还威胁换人, 只能赔笑脸"]},
        {"key": "K6", "t": "21:00", "mod": "mic", "source": "给${family}打电话",
         "texts": ["跟${family}说一切顺利明天就到, 盗刷和扣钱的事一个字没敢提",
                   "报喜不报忧: 路上好着呢, 早点睡, 挂了电话盯着账单发愁"]},
    ],
    "vitals": {"sleep": (4.4, 5.4), "rest_hr": (74, 82), "steps": (2000, 4000),
               "episodes": [
        {"key": "V1", "t": "09:42", "signal": "heart_rate", "reading": "122bpm",
         "context": "${fault}抛锚瞬间惊吓"},
    ]},
    "gt": {
        "global": {
            "core": "${place}${fault}趴窝误点被扣运费, 又遭${theft}, 对${family}报喜不报忧独自扛下",
            "syn": ["抛锚", "${fault}", "趴窝", "误点", "扣运费", "盗刷", "报喜不报忧", "独自扛"],
            "red": ["一路顺风", "准时到达", "涨运费", "中彩票", "车祸重伤"],
            "entities": ["${place}", "${fault}", "${theft}"], "evidence": ["K2", "K4", "K5"]},
        "dim:health": {
            "core": "抛锚瞬间惊吓122bpm, 连日疲劳驾驶睡眠不足, 服务区凑合睡身体透支",
            "syn": ["惊吓", "122", "疲劳驾驶", "睡眠不足", "透支"],
            "red": ["车祸受伤", "猝死", "生龙活虎", "体检优秀"],
            "entities": [], "evidence": ["V1", "K2"]},
        "dim:social": {
            "core": "与${owner}因误点交恶被扣费威胁换人; 对${family}隐瞒实情",
            "syn": ["交恶", "扣费", "威胁换人", "隐瞒", "报喜不报忧", "赔笑脸"],
            "red": ["涨运费", "长期合作", "家庭坦诚", "称兄道弟"],
            "entities": ["${owner}"], "evidence": ["K1", "K5", "K6"]},
        "dim:emotion": {
            "core": "从被催的烦躁到抛锚的慌张再到被骂的憋屈, 深夜独自发愁",
            "syn": ["烦躁", "慌张", "憋屈", "发愁", "窝火", "硬扛"],
            "red": ["开心", "淡定", "路怒打人", "绝望轻生"],
            "entities": [], "evidence": ["K2", "K5", "K6"]},
        "dim:finance": {
            "core": "维修${fee}加${theft}加运费被扣, 跑一趟倒贴, 盗刷款追回未知",
            "syn": ["${fee}", "${theft}", "扣运费", "倒贴", "追回未知"],
            "red": ["大赚", "涨运费", "全额追回", "保险全赔"],
            "entities": ["${fee}", "${theft}"], "evidence": ["K3", "K4", "K5"]},
        "dim:career": {
            "core": "误点违约信誉受损, ${owner}威胁换人, 饭碗受到威胁",
            "syn": ["误点", "违约", "信誉受损", "威胁换人", "饭碗不稳"],
            "red": ["涨运费", "签长约", "买新车", "转行成功"],
            "entities": ["${owner}"], "evidence": ["K1", "K5"]},
    },
    "background": ["服务区泡面", "听收音机", "加油"],
})

# A12 急诊医生的一天
ARCS.append({
    "arc_id": "A12_DOCTOR_DISPUTE", "title": "医患冲突与连轴抢救",
    "personas": ["P06"],
    "slots": {
        "dispute": ["候诊插队引发推搡", "家属质疑过度检查拍桌子"],
        "leader": ["科主任", "医务科王科长"],
        "spouse": ["妻子", "老婆"],
        "hours": ["连轴24小时", "36小时没回家"],
        "patient": ["心梗大爷", "车祸小伙"],
    },
    "beats": [
        {"key": "K1", "t": "08:00", "mod": "mic", "source": "交班",
         "texts": ["交班: 昨夜抢救3台, ${patient}刚送ICU, 今天门诊加急诊连轴",
                   "晨会交班: 夜班收了11个, ${patient}最重, 白天继续顶"]},
        {"key": "K2", "t": "11:30", "mod": "mic", "source": "分诊台",
         "texts": ["分诊台炸了:${dispute}, 我被推了一把, 白大褂扣子都掉了",
                   "${dispute}, 保安赶来才拉开, 对方扬言投诉到卫健委"]},
        {"key": "K3", "t": "13:20", "mod": "mic", "source": "${leader}",
         "texts": ["${leader}: 先安抚家属, 晚上写个情况说明, 受委屈了我知道",
                   "${leader}拍肩: 按流程走, 说明写好, 剩下的组织担着"]},
        {"key": "K4", "t": "16:40", "mod": "mic", "source": "患者家属",
         "texts": ["一位家属下跪求加床: 医生求求你救救我爸, 协调半小时终于住进观察室",
                   "家属跪求加床收治, 心一软到处打电话, 总算把老人安顿进观察室"]},
        {"key": "K5", "t": "20:00", "mod": "app", "source": "${spouse}微信",
         "texts": ["${spouse}: 女儿家长会你又缺席, 老师问爸爸是干啥的孩子答不上来",
                   "${spouse}发来女儿的画: 我的爸爸在医院里, 从没参加过家长会"]},
        {"key": "K6", "t": "23:00", "mod": "mic", "source": "独白",
         "texts": ["${hours}, 靠在值班室椅子上就能睡着, 明早7点还出门诊",
                   "数了数今天看了80多个号, 腿肿了, 但${patient}稳定了, 值"]},
    ],
    "vitals": {"sleep": (1.5, 3.0), "rest_hr": (78, 86), "steps": (14000, 18000),
               "episodes": [
        {"key": "V1", "t": "11:32", "signal": "heart_rate", "reading": "128bpm",
         "context": "${dispute}被推搡时"},
    ]},
    "gt": {
        "global": {
            "core": "${hours}连轴抢救中遭遇${dispute}, 又跪求加床两头救火, 深夜缺席女儿家长会被${spouse}数落",
            "syn": ["连轴", "${hours}", "抢救", "医患冲突", "推搡", "投诉", "跪求加床",
                    "缺席家长会", "救火"],
            "red": ["休假", "被开除", "医疗事故", "收红包", "家庭和睦无怨"],
            "entities": ["${dispute}", "${patient}"], "evidence": ["K1", "K2", "K4"]},
        "dim:health": {
            "core": "睡眠不足3小时日行1.6万步, 冲突时应激128bpm, 身体严重透支",
            "syn": ["睡眠不足", "1.6万步", "128", "透支", "腿肿", "连轴", "应激"],
            "red": ["猝死", "晕倒", "住院", "生龙活虎", "休假充电"],
            "entities": [], "evidence": ["V1", "K6"]},
        "dim:social": {
            "core": "与闹事家属冲突后靠${leader}兜底; 助跪求家属获感激; 对${spouse}与女儿亏欠",
            "syn": ["医患冲突", "领导兜底", "助人", "感激", "亏欠家人", "缺席"],
            "red": ["收红包", "吃回扣", "家暴", "离婚", "众星捧月"],
            "entities": ["${leader}", "${spouse}"], "evidence": ["K2", "K3", "K5"]},
        "dim:emotion": {
            "core": "委屈与成就感交织: 被推委屈, 救人欣慰, 对女儿愧疚, 主基调疲惫而坚守",
            "syn": ["委屈", "欣慰", "愧疚", "疲惫", "坚守", "五味杂陈"],
            "red": ["狂喜", "麻木", "仇恨医患", "辞职", "崩溃大哭"],
            "entities": [], "evidence": ["K2", "K4", "K5"]},
        "dim:finance": {
            "core": "当日无个人大额收支, 只有食堂与交通小额消费",
            "syn": ["无大额收支", "小额消费", "平稳", "食堂交通", "无债务"],
            "red": ["收红包", "巨额收入", "欠薪", "破产"],
            "entities": [], "evidence": []},
        "dim:career": {
            "core": "高强度诊疗+纠纷处置两不误, 获${leader}认可, 但需补写情况说明应对投诉",
            "syn": ["高强度", "纠纷处置", "获认可", "情况说明", "应对投诉", "坚守岗位"],
            "red": ["吊销执照", "被开除", "升职", "跳槽", "医疗事故定责"],
            "entities": ["${leader}"], "evidence": ["K1", "K3", "K6"]},
    },
    "background": ["食堂吃饭", "喝咖啡", "取快递"],
    "twist": {
        "beat": {"key": "T1", "t": "18:00", "mod": "mic", "source": "同事",
                 "texts": ["同事让我换班休息, 我摆手: 我能顶, 病人比我更需要床位 (腿肿得鞋都紧了)"]},
        "patch": {"dim:emotion": {
            "suffix": "; 逞强拒换班, 透支硬顶",
            "syn_add": ["逞强", "硬顶", "拒休息"], "red_add": ["主动休假", "擅离职守"]}},
        "evidence_add": {"dim:emotion": ["T1"], "dim:health": ["T1"]},
    },
})

# A13 讨薪与痛风
ARCS.append({
    "arc_id": "A13_WAGE_ARREARS", "title": "工人讨薪与堵门要账",
    "personas": ["P07"],
    "slots": {
        "contractor": ["总包方赵经理", "恒宇建材结算办"],
        "amount": ["20万结算款", "35万工程款"],
        "worker": ["老张等30名工人", "班组兄弟"],
        "family": ["老婆", "家里"],
        "med": ["双氯芬酸钠", "秋水仙碱"],
    },
    "beats": [
        {"key": "K1", "t": "08:30", "mod": "mic", "source": "${worker}",
         "texts": ["${worker}围住我: 下周五再不发工资就去住建局, 别怪兄弟们不讲情面",
                   "一早被工人堵在项目部: 血汗钱拖三个月了, 今天必须给个准信"]},
        {"key": "K2", "t": "10:00", "mod": "mic", "source": "${contractor}",
         "texts": ["堵${contractor}的门: 对方拿阴阳合同扯皮, 说验收没过一分没有",
                   "跟${contractor}拍桌子: 合同两份价, 你们这是欺负农民工, 我要仲裁!"]},
        {"key": "K3", "t": "12:30", "mod": "mic", "source": "独白",
         "texts": ["脚趾肿得像馒头下不了地, 痛风又犯了, 买盒${med}撑着",
                   "痛风发作脚疼得冒汗, 吞两粒${med}, 下午还得接着跑"]},
        {"key": "K4", "t": "15:30", "mod": "mic", "source": "${contractor}",
         "texts": ["磨了一天${contractor}松口: ${amount}先付一半, 剩下的验收完结清, 字据立好",
                   "${contractor}终于签字: ${amount}先付50%, 尾款下月结, 算撕开一道口子"]},
        {"key": "K5", "t": "18:00", "mod": "mic", "source": "${worker}",
         "texts": ["跟${worker}交底: 钱下周五分文不少到卡, 我拿人格担保, 大家先散了",
                   "安抚住工人: 下周五发钱, 谁也别去上访, 丢的人是咱们自己的"]},
        {"key": "K6", "t": "21:40", "mod": "app", "source": "${family}微信",
         "texts": ["${family}: 药吃了没? 脚还肿不? 早点回, 别跟人动手",
                   "${family}发来偏方和小视频: 痛风忌口表, 叮嘱我少喝酒"]},
    ],
    "vitals": {"sleep": (5.2, 6.2), "rest_hr": (76, 84), "steps": (9000, 13000),
               "episodes": [
        {"key": "V1", "t": "08:35", "signal": "heart_rate", "reading": "116bpm",
         "context": "被${worker}围堵时"},
    ]},
    "gt": {
        "global": {
            "core": "被${worker}讨薪围堵后堵${contractor}撕开${amount}先付一半, 忍痛风跑了一天, 暂时稳住两头",
            "syn": ["讨薪", "围堵", "堵门", "要账", "先付一半", "稳住", "撕开口子", "血汗钱"],
            "red": ["全额结清", "欠薪跑路", "打架斗殴", "上访", "破产"],
            "entities": ["${contractor}", "${amount}", "${worker}"], "evidence": ["K1", "K2", "K4"]},
        "dim:health": {
            "core": "痛风急性发作脚趾红肿剧痛, 靠${med}硬撑奔走, 围堵时应激116bpm",
            "syn": ["痛风", "红肿", "剧痛", "${med}", "硬撑", "116"],
            "red": ["截肢", "住院", "猝死", "生龙活虎", "痊愈"],
            "entities": ["痛风", "${med}"], "evidence": ["K3", "V1", "K6"]},
        "dim:social": {
            "core": "与${worker}从对峙到安抚稳住; 与${contractor}拍桌扯皮终达成分期; ${family}远程牵挂",
            "syn": ["对峙", "安抚", "拍桌", "分期", "牵挂", "人格担保"],
            "red": ["群殴", "上访", "断交", "众叛亲离", "称兄道弟"],
            "entities": ["${worker}", "${contractor}"], "evidence": ["K1", "K4", "K5"]},
        "dim:emotion": {
            "core": "早憋屈午愤怒晚踏实, 夹在工人与总包之间两头受气, 落定后如释重负",
            "syn": ["憋屈", "愤怒", "两头受气", "踏实", "如释重负", "硬扛"],
            "red": ["狂喜", "绝望", "麻木", "打人泄愤"],
            "entities": [], "evidence": ["K1", "K2", "K4"]},
        "dim:finance": {
            "core": "${amount}谈下先付一半, 工人工资下周五有着落, 自掏${med}药费",
            "syn": ["${amount}", "先付一半", "工资有着落", "分期", "回款"],
            "red": ["全额到账", "血本无归", "跑路", "高利贷"],
            "entities": ["${amount}"], "evidence": ["K4", "K5"]},
        "dim:career": {
            "core": "结算僵局撕开口子保住班组稳定, 但尾款仍悬, 下月继续攻坚",
            "syn": ["结算", "撕开口子", "班组稳定", "尾款仍悬", "攻坚"],
            "red": ["丢标", "停工", "吊销资质", "转行", "上市"],
            "entities": ["${contractor}"], "evidence": ["K2", "K4"]},
    },
    "background": ["工地盒饭", "买烟", "听戏"],
})

# A14 税务稽查
ARCS.append({
    "arc_id": "A14_TAX_AUDIT", "title": "税务稽查上门",
    "personas": ["P08", "P13"],
    "slot_overrides": {"P08": {"family": ["老公"]},
                       "P13": {"family": ["老婆", "家里老人"]}},
    "gt_overrides": {"P13": {
        "global": {
            "core": "税务稽查进场查出${issue}, 测算${amount}, 瞒家人连夜自查补救, 一夜愁白头",
            "syn": ["稽查", "进场", "自查", "${issue}", "补税", "${amount}", "瞒家人", "煎熬"],
            "red": ["偷税成功", "行贿过关", "销毁证据", "无事发生", "表彰诚信纳税"],
            "entities": ["${authority}", "${issue}", "${amount}"], "evidence": ["K1", "K2", "K4"]},
        "dim:health": {
            "core": "惊吓119bpm, 整夜只睡4小时, 胃疼老毛病又有抬头迹象",
            "syn": ["119", "失眠", "只睡4小时", "胃疼", "紧张", "惊吓"],
            "red": ["心脏病发", "猝死", "酣睡", "生龙活虎"],
            "entities": [], "evidence": ["V1", "K6"]}}},
    "slots": {
        "authority": ["稽查科陈科长", "专管员小周"],
        "issue": ["几张成本票是假发票", "进销项对不上差400万"],
        "amount": ["补税加罚款约18万", "补税滞纳金约25万"],
        "advisor": ["税务顾问老郑", "会计师事务所"],
        "family": ["老公", "家里老人"],
    },
    "beats": [
        {"key": "K1", "t": "09:30", "mod": "mic", "source": "${authority}",
         "texts": ["${authority}带着两人上门: 请提供近三年账册凭证, 配合检查",
                   "电话里${authority}很客气但不容商量: 明天进场, 账先自查一遍"]},
        {"key": "K2", "t": "11:00", "mod": "mic", "source": "自查",
         "texts": ["一自查后背发凉:${issue}, 当年图省事埋的雷, 今天炸了",
                   "翻出旧账:${issue}, 手心冒汗, 赶紧锁进抽屉"]},
        {"key": "K3", "t": "14:30", "mod": "mic", "source": "${advisor}",
         "texts": ["紧急约${advisor}: 对方说主动补正争取从轻, 千万别销毁证据",
                   "${advisor}看完直摇头: 先自查补税, 态度决定一半结果"]},
        {"key": "K4", "t": "17:20", "mod": "app", "source": "测算",
         "texts": ["初步测算:${amount}, 今晚失眠预定, 先跟老板通个气",
                   "${advisor}发来测算:${amount}, 建议分期, 听得我眼前发黑"]},
        {"key": "K5", "t": "19:00", "mod": "mic", "source": "${family}",
         "texts": ["${family}问咋脸色这么差, 我说更年期不舒服, 一个字不敢提",
                   "瞒着${family}: 公司例行检查, 小事, 其实手抖得端不住碗"],
         "persona_texts": {"P13": [
                   "${family}问咋脸色这么差, 我说年底结账忙的, 过两天就好, 一个字不敢提",
                   "瞒着${family}: 税务例行走访, 小事, 其实手抖得端不住碗"]}},
        {"key": "K6", "t": "23:40", "mod": "mic", "source": "独白",
         "texts": ["翻税法翻到半夜, 盗汗把睡衣湿透两回, 明天还得笑着迎检",
                   "凌晨还在列自查清单, 更年期加稽查, 双重暴击"],
         "persona_texts": {"P13": [
                   "翻税法翻到半夜, 烟灰缸堆满, 明天还得笑着迎检",
                   "凌晨还在列自查清单, 胃又开始隐隐作痛"]}},
    ],
    "vitals": {"sleep": (3.8, 4.8), "rest_hr": (78, 86), "steps": (3000, 5500),
               "episodes": [
        {"key": "V1", "t": "09:35", "signal": "heart_rate", "reading": "119bpm",
         "context": "得知稽查进场时"},
    ]},
    "gt": {
        "global": {
            "core": "税务稽查进场查出${issue}, 测算${amount}, 瞒家人连夜自查补救, 更年期叠加煎熬",
            "syn": ["稽查", "进场", "自查", "${issue}", "补税", "${amount}", "瞒家人", "煎熬"],
            "red": ["偷税成功", "行贿过关", "销毁证据", "无事发生", "表彰诚信纳税"],
            "entities": ["${authority}", "${issue}", "${amount}"], "evidence": ["K1", "K2", "K4"]},
        "dim:health": {
            "core": "惊吓119bpm, 更年期失眠盗汗加重, 整夜只睡4小时",
            "syn": ["119", "失眠", "盗汗", "更年期", "惊吓", "只睡4小时"],
            "red": ["心脏病发", "猝死", "酣睡", "冻龄"],
            "entities": [], "evidence": ["V1", "K6"]},
        "dim:social": {
            "core": "配合${authority}检查姿态端正; 求助${advisor}自救; 对${family}全面隐瞒",
            "syn": ["配合检查", "求助", "自救", "隐瞒家人", "端正态度"],
            "red": ["行贿", "对抗执法", "举报同事", "家庭坦诚"],
            "entities": ["${authority}", "${advisor}"], "evidence": ["K1", "K3", "K5"]},
        "dim:emotion": {
            "core": "从惊恐到羞愧再到强撑, 主基调后悔与硬扛",
            "syn": ["惊恐", "羞愧", "后悔", "强撑", "硬扛", "煎熬"],
            "red": ["开心", "无所谓", "理直气壮", "崩溃自首"],
            "entities": [], "evidence": ["K2", "K5", "K6"]},
        "dim:finance": {
            "core": "面临${amount}, 现金流承压, 正谋分期与补正从轻",
            "syn": ["${amount}", "补税", "罚款", "承压", "分期", "从轻"],
            "red": ["零处罚", "退税", "财务自由", "破产清算"],
            "entities": ["${amount}"], "evidence": ["K4"]},
        "dim:career": {
            "core": "职业声誉悬于稽查结果, 一天未干正事全力应对, 饭碗与前途承压",
            "syn": ["声誉", "应对检查", "全力", "前途承压", "自查"],
            "red": ["升职", "嘉奖", "跳槽成功", "被开除", "退休"],
            "entities": ["${authority}"], "evidence": ["K1", "K3", "K6"]},
    },
    "background": ["买咖啡", "取快递", "跳广场舞"],
})

# A15 保健品骗局
ARCS.append({
    "arc_id": "A15_RETIREE_SCAM", "title": "保健品洗脑与退费",
    "personas": ["P09"],
    "slots": {
        "scammer": ["健康讲座李教授", "推销员小赵"],
        "product": ["29800元理疗床垫", "19800保健品套餐"],
        "child": ["女儿", "儿子"],
        "friend": ["老姐妹王阿姨", "老同事刘姐"],
        "deposit": ["定金5000", "预付款3000"],
    },
    "beats": [
        {"key": "K1", "t": "09:00", "mod": "mic", "source": "${scammer}",
         "texts": ["讲座上${scammer}声泪俱下:${product}, 包治百病, 前十名半价! 我心动了",
                   "${scammer}拉着我的手: 阿姨你气色差就是缺这个, ${product}今天下单最划算"]},
        {"key": "K2", "t": "11:30", "mod": "app", "source": "交款",
         "texts": ["稀里糊涂交了${deposit}, 收据都没细看, 回家越想越不对",
                   "手机银行扣款${deposit}, 对方说不买不退, 脑子一热就付了"]},
        {"key": "K3", "t": "14:00", "mod": "mic", "source": "${child}",
         "texts": ["${child}知道后急了: 妈! 这是骗局! 新闻播过多少回了! 吵得我直哭",
                   "跟${child}大吵一架: 对方说我老糊涂, 我说你们平时不管现在来吼"]},
        {"key": "K4", "t": "16:30", "mod": "mic", "source": "${scammer}",
         "texts": ["拉着${child}去退钱, ${scammer}翻脸: 交了就不退, 爱上哪告上哪告",
                   "退费扯皮两小时, 对方耍赖, ${child}直接打了12315和110"]},
        {"key": "K5", "t": "18:30", "mod": "app", "source": "退款",
         "texts": ["市场监管介入后${deposit}退回来了, 还做了笔录, 虚惊一场",
                   "退款到账短信:${deposit}原路退回, 警察说这伙人已被盯上"]},
        {"key": "K6", "t": "21:00", "mod": "mic", "source": "${friend}电话",
         "texts": ["赶紧给${friend}打电话: 千万别去那个讲座, 我差点被骗两万! 对方说明天也不去了",
                   "跟${friend}互相提醒: 以后超过一千块先问子女, 再不贪小便宜"]},
    ],
    "vitals": {"sleep": (6.0, 7.0), "rest_hr": (72, 80), "steps": (5500, 8500),
               "episodes": [
        {"key": "V1", "t": "14:05", "signal": "heart_rate", "reading": "112bpm",
         "context": "与${child}争吵时"},
    ]},
    "gt": {
        "global": {
            "core": "听信讲座交${deposit}买${product}几被骗, 与${child}争吵后联手退费成功, 化险为夷",
            "syn": ["保健品骗局", "洗脑", "交定金", "被骗", "争吵", "退费", "化险为夷", "虚惊一场"],
            "red": ["买到神药", "治好百病", "钱打水漂", "断绝母女关系", "理财大赚"],
            "entities": ["${product}", "${deposit}", "${child}"], "evidence": ["K1", "K2", "K5"]},
        "dim:health": {
            "core": "争吵时心率112, 情绪大起大落, 好在无基础病发作, 夜间平稳",
            "syn": ["112", "情绪波动", "平稳", "无发作"],
            "red": ["心脏病发", "脑溢血", "住院", "猝死"],
            "entities": [], "evidence": ["V1"]},
        "dim:social": {
            "core": "与${child}先吵后和联手维权; 识破${scammer}嘴脸; 提醒${friend}避坑",
            "syn": ["先吵后和", "联手维权", "识破", "提醒", "母女和解"],
            "red": ["断绝关系", "老死不相往来", "加入传销", "众叛亲离"],
            "entities": ["${child}", "${scammer}", "${friend}"], "evidence": ["K3", "K4", "K6"]},
        "dim:emotion": {
            "core": "上午贪心心动下午委屈愤怒晚上后怕庆幸, 教训深刻",
            "syn": ["贪心", "委屈", "愤怒", "后怕", "庆幸", "教训"],
            "red": ["开心", "执迷不悟", "绝望", "麻木"],
            "entities": [], "evidence": ["K1", "K3", "K5"]},
        "dim:finance": {
            "core": "${deposit}失而复得, ${product}未成交止损, 养老钱保住",
            "syn": ["${deposit}", "失而复得", "止损", "保住", "退款"],
            "red": ["血本无归", "倾家荡产", "理财大赚", "买到赝品"],
            "entities": ["${deposit}", "${product}"], "evidence": ["K2", "K5"]},
        "dim:career": {
            "core": "退休生活主题日: 讲座踩坑与维权占据全天, 无其他安排",
            "syn": ["讲座", "维权", "退休生活", "占据全天"],
            "red": ["返聘", "创业", "打工", "领养老金被停"],
            "entities": [], "evidence": ["K1", "K4"]},
    },
    "background": ["买菜", "跳广场舞", "看电视剧"],
})

# A16 骑手暴雨日
ARCS.append({
    "arc_id": "A16_RIDER_OVERTIME", "title": "暴雨超时与丢车",
    "personas": ["P12"],
    "slots": {
        "fine": ["超时罚款80加差评扣200", "两个差评扣400"],
        "bike": ["电瓶车被盗", "电瓶被偷"],
        "merchant": ["出餐慢的商户", "爆单的奶茶店"],
        "family": ["老妈", "家里"],
        "station": ["站长", "站里"],
    },
    "beats": [
        {"key": "K1", "t": "11:30", "mod": "app", "source": "天气加派单",
         "texts": ["暴雨红色预警, 单量却爆了, 系统一口气派了8单, 硬着头皮上",
                   "雨大到看不清路, 派单不停, 今天注定超时, 先跑了再说"]},
        {"key": "K2", "t": "13:20", "mod": "mic", "source": "${merchant}",
         "texts": ["${merchant}前等了40分钟, 理论几句吵起来: 你们爆单凭啥骑手背锅!",
                   "跟${merchant}吵红了脸: 餐不出超时算谁的? 店员说找平台去"]},
        {"key": "K3", "t": "14:00", "mod": "app", "source": "平台处罚",
         "texts": ["处罚通知:${fine}, 一上午白跑, 雨水混着汗往下淌",
                   "手机连震:${fine}, 今天等于白跑还倒贴电钱"]},
        {"key": "K4", "t": "17:50", "mod": "mic", "source": "独白",
         "texts": ["送完一单回来发现${bike}, 当场腿软, 赶紧报警调监控",
                   "${bike}! 车锁被剪断扔在地上, 蹲在雨里半天没起来"]},
        {"key": "K5", "t": "19:30", "mod": "mic", "source": "独白",
         "texts": ["滑囊炎的膝盖疼得钻心, 贴上膏药借了辆车继续跑晚高峰, 不跑房租就没了",
                   "滑囊炎的膝盖肿了, 咬牙再跑两小时, 今天不能空手回"]},
        {"key": "K6", "t": "22:00", "mod": "mic", "source": "给${family}打电话",
         "texts": ["跟${family}说今天跑了400多, 好着呢, 丢车罚款一个字没提",
                   "电话里笑呵呵: 妈我吃得好睡得香, 挂了电话数剩下的钱发愁"]},
    ],
    "vitals": {"sleep": (5.4, 6.4), "rest_hr": (70, 78), "steps": (16000, 20000),
               "episodes": [
        {"key": "V1", "t": "13:25", "signal": "heart_rate", "reading": "124bpm",
         "context": "暴雨中与${merchant}争吵时"},
    ]},
    "gt": {
        "global": {
            "core": "暴雨爆单连超时被${fine}, 又遭${bike}, 忍膝伤跑晚高峰, 对${family}报喜不报忧",
            "syn": ["暴雨", "爆单", "超时", "${fine}", "丢车", "${bike}", "忍伤跑单", "报喜不报忧"],
            "red": ["月入过万", "零差评", "买车", "中奖", "车祸重伤"],
            "entities": ["${fine}", "${bike}"], "evidence": ["K1", "K3", "K4"]},
        "dim:health": {
            "core": "膝盖滑囊炎发作仍冒雨跑单近2万步, 争吵时124bpm, 淋雨受寒风险高",
            "syn": ["滑囊炎", "膝盖", "冒雨", "2万步", "124", "淋雨", "硬撑"],
            "red": ["骨折", "住院", "猝死", "生龙活虎", "夺冠"],
            "entities": ["膝盖", "滑囊炎"], "evidence": ["V1", "K5"]},
        "dim:social": {
            "core": "与${merchant}为超时责任争吵; 报警求助寻车; 对${family}隐瞒实情",
            "syn": ["争吵", "超时责任", "报警", "寻车", "隐瞒", "报喜不报忧"],
            "red": ["打架", "被开除", "客户表扬", "家庭坦诚"],
            "entities": ["${merchant}", "${family}"], "evidence": ["K2", "K4", "K6"]},
        "dim:emotion": {
            "core": "憋屈愤怒与心酸交织, 丢车瞬间险些崩溃, 靠给母亲打电话回血",
            "syn": ["憋屈", "愤怒", "心酸", "险些崩溃", "回血", "硬扛"],
            "red": ["开心", "躺平", "仇恨社会", "绝望轻生"],
            "entities": [], "evidence": ["K3", "K4", "K6"]},
        "dim:finance": {
            "core": "${fine}叠加丢车损失, 今日倒贴, 房租着落堪忧",
            "syn": ["${fine}", "倒贴", "丢车损失", "房租堪忧", "白跑"],
            "red": ["日入过千", "奖金", "追回失车", "暴富"],
            "entities": ["${fine}"], "evidence": ["K3", "K4"]},
        "dim:career": {
            "core": "超时差评拉低评分影响派单权重, 丢车致运力中断, 生计承压",
            "syn": ["差评", "评分", "派单权重", "运力中断", "生计承压"],
            "red": ["升站长", "单王", "转正", "跳槽成功"],
            "entities": [], "evidence": ["K3", "K4", "K5"]},
    },
    "background": ["路边盒饭", "买雨衣", "充电"],
})

# A17 模考崩盘
ARCS.append({
    "arc_id": "A17_EXAM_FAILURE", "title": "模考崩盘与高压",
    "personas": ["P01"],
    "slots": {
        "subject": ["数学", "理综"],
        "score": ["总分412分", "班级倒数第8"],
        "teacher": ["班主任李老师", "年级主任"],
        "parent": ["妈妈", "爸爸"],
        "rival": ["同桌", "隔壁班第一"],
    },
    "beats": [
        {"key": "K1", "t": "08:00", "mod": "app", "source": "成绩群",
         "texts": ["模考成绩公布:${score}, ${subject}又没及格, 脑子嗡的一声",
                   "群里${score}排在${rival}后面一大截, 盯着屏幕手发抖"]},
        {"key": "K2", "t": "10:30", "mod": "mic", "source": "${teacher}",
         "texts": ["${teacher}谈话: 照这样下去一本线都危险, 你到底想不想考了?",
                   "被${teacher}叫去办公室: 心态崩了? 离高考没几天了, 给我稳住"]},
        {"key": "K3", "t": "12:10", "mod": "mic", "source": "${parent}电话",
         "texts": ["${parent}电话轰炸: 供你复读一年花了多少钱你知道吗? 不争气!",
                   "${parent}在电话里哭: 隔壁孩子保送了, 你连${score}都考不出来"]},
        {"key": "K4", "t": "15:00", "mod": "mic", "source": "独白",
         "texts": ["下午头晕心悸手抖, 校医说躯体化, 让先睡一觉别硬撑",
                   "心慌得做不进题, 躯体化发作趴在桌上喘气, 同桌吓得去叫了老师"]},
        {"key": "K5", "t": "18:30", "mod": "mic", "source": "${parent}",
         "texts": ["${parent}杀到学校陪读: 从今天起我天天盯着你, 手机没收",
                   "${parent}提着行李住进陪读房: 考不上好大学, 对不起所有人"]},
        {"key": "K6", "t": "23:30", "mod": "mic", "source": "独白",
         "texts": ["宿舍熄灯后失眠打手电刷${subject}, 脑子木的, 眼泪把卷子洇湿一块",
                   "夜里一点失眠睡不着, ${score}和${subject}错题在眼前晃, 明天6点又要起"]},
    ],
    "vitals": {"sleep": (4.0, 5.0), "rest_hr": (80, 88), "steps": (2500, 4500),
               "episodes": [
        {"key": "V1", "t": "08:05", "signal": "heart_rate", "reading": "121bpm",
         "context": "看到${score}时"},
        {"key": "V2", "t": "15:05", "signal": "heart_rate", "reading": "118bpm",
         "context": "焦虑躯体化心悸时"},
    ]},
    "gt": {
        "global": {
            "core": "模考${score}崩盘, 遭${teacher}约谈与${parent}高压, 出现焦虑躯体化仍熬夜刷题",
            "syn": ["模考崩盘", "${score}", "约谈", "高压", "躯体化", "熬夜刷题", "陪读"],
            "red": ["考第一", "保送", "轻松愉快", "辍学", "离家出走"],
            "entities": ["${score}", "${teacher}", "${parent}"], "evidence": ["K1", "K3", "K4"]},
        "dim:health": {
            "core": "焦虑致121bpm心悸头晕手抖(躯体化), 长期失眠, 需心理干预而非硬撑",
            "syn": ["121", "心悸", "头晕", "躯体化", "失眠", "心理干预"],
            "red": ["心脏病", "猝死", "装病", "生龙活虎"],
            "entities": ["躯体化", "失眠"], "evidence": ["V1", "V2", "K4"]},
        "dim:social": {
            "core": "与${teacher}约谈施压; 与${parent}高压对峙母子/父子紧绷; 与${rival}差距拉大失落",
            "syn": ["约谈", "施压", "高压", "紧绷", "差距", "失落", "陪读"],
            "red": ["师生恋", "离家出走", "断绝关系", "备受表扬"],
            "entities": ["${teacher}", "${parent}"], "evidence": ["K2", "K3", "K5"]},
        "dim:emotion": {
            "core": "羞耻恐惧自我否定三连, 白天崩溃晚上麻木刷题, 心理接近极限",
            "syn": ["羞耻", "恐惧", "自我否定", "崩溃", "麻木", "接近极限"],
            "red": ["开心", "自信", "无所谓", "自残", "狂喜"],
            "entities": [], "evidence": ["K1", "K4", "K6"]},
        "dim:finance": {
            "core": "复读与陪读开支由${parent}承担, 本人无收支, 愧疚转化为压力",
            "syn": ["复读开支", "陪读", "无收支", "愧疚"],
            "red": ["巨额零花钱", "打工", "欠债", "中奖"],
            "entities": [], "evidence": ["K3", "K5"]},
        "dim:career": {
            "core": "学业告急:${subject}拖后腿致${score}, 一本线岌岌可危, 被迫加码",
            "syn": ["学业告急", "${subject}", "${score}", "一本线", "加码", "拖后腿"],
            "red": ["保送", "状元", "退学", "留学", "满分"],
            "entities": ["${subject}", "${score}"], "evidence": ["K1", "K2", "K6"]},
    },
    "background": ["食堂吃饭", "买文具", "跑操"],
})

# A18 团圆 (正向)
ARCS.append({
    "arc_id": "A18_FAMILY_REUNION", "title": "久别团圆",
    "personas": ["P01", "P05", "P09", "P10"],
    "slot_overrides": {"P01": {"guest": ["外地打工的爸爸"]},
                       "P05": {"guest": ["儿子豆豆"]},
                       "P09": {"guest": ["儿子一家三口", "放假回来的孙子"]},
                       "P10": {"guest": ["儿子一家三口", "放假回来的孙子"]}},
    "slots": {
        "guest": ["外地打工的爸爸", "儿子一家三口", "放假回来的孙子"],
        "event": ["生日", "提前团圆", "乔迁暖房"],
        "dish": ["红烧肉", "饺子", "清蒸鱼"],
        "gift": ["新书包", "按摩仪", "全家福相框"],
    },
    "beats": [
        {"key": "K1", "t": "10:00", "mod": "mic", "source": "独白",
         "texts": ["一大早大扫除加买菜, ${dish}的材料备齐, 心里美滋滋",
                   "把家里里外外收拾一遍, ${guest}中午到, 可不能丢面"]},
        {"key": "K2", "t": "12:00", "mod": "mic", "source": "${guest}",
         "texts": ["${guest}进门放下大包小包, 拥抱寒暄, 眼眶都红了",
                   "盼了大半年的${guest}终于到家, 门口抱了个满怀"]},
        {"key": "K3", "t": "13:30", "mod": "mic", "source": "饭桌",
         "texts": ["饭桌上举杯:${event}快乐! 过去的不愉快一笔勾销, 以后常聚",
                   "吃着${dish}聊到${event}, 往日的隔阂在笑声里化了"]},
        {"key": "K4", "t": "16:00", "mod": "mic", "source": "散步",
         "texts": ["饭后一起散步拍照, 发了条朋友圈: 团圆就是最好的礼物",
                   "陪${guest}在小区走走, 拍了全家福, 笑得合不拢嘴"]},
        {"key": "K5", "t": "19:00", "mod": "app", "source": "家庭群",
         "texts": ["家庭群被团圆照刷屏, ${guest}还发了个大红包, 抢得热火朝天",
                   "家庭群里照片红包齐飞, 长辈们轮流语音, 热闹到深夜"]},
        {"key": "K6", "t": "21:30", "mod": "mic", "source": "独白",
         "texts": ["${guest}送的${gift}摆在床头, 今天是今年最开心的一天",
                   "睡前翻着合影傻笑, ${gift}就放枕边, 盼了大半年的团圆, 值了"]},
    ],
    "vitals": {"sleep": (7.0, 8.0), "rest_hr": (62, 72), "steps": (6000, 10000),
               "episodes": [
        {"key": "V1", "t": "12:05", "signal": "heart_rate", "reading": "100bpm",
         "context": "见到${guest}时高兴激动"},
    ]},
    "gt": {
        "global": {
            "core": "盼了大半年的${guest}到家${event}团圆, 隔阂消融共享天伦, 年度高光日",
            "syn": ["团圆", "${event}", "久别重逢", "隔阂消融", "天伦", "高光", "盼了大半年"],
            "red": ["吵架", "分手", "离婚", "离家出走", "葬礼", "决裂"],
            "entities": ["${guest}", "${event}"], "evidence": ["K2", "K3", "K4"]},
        "dim:health": {
            "core": "体征平稳睡眠好, 相见瞬间高兴100bpm属正向波动, 胃口开",
            "syn": ["平稳", "睡眠好", "正向波动", "100", "胃口好"],
            "red": ["心脏病", "住院", "失眠", "晕倒"],
            "entities": [], "evidence": ["V1"]},
        "dim:social": {
            "core": "与${guest}久别重逢亲情升温, 家庭群热闹, 关系修复",
            "syn": ["久别重逢", "亲情", "升温", "热闹", "修复", "团聚"],
            "red": ["决裂", "冷战", "断绝关系", "众叛亲离"],
            "entities": ["${guest}"], "evidence": ["K2", "K4", "K5"]},
        "dim:emotion": {
            "core": "从期待到狂喜再到温情满足, 全天被幸福感包裹",
            "syn": ["期待", "狂喜", "温情", "满足", "幸福", "开心"],
            "red": ["抑郁", "崩溃", "焦虑", "麻木", "暴怒"],
            "entities": [], "evidence": ["K1", "K3", "K6"]},
        "dim:finance": {
            "core": "团圆宴与${gift}属计划内开支, 另收到家庭群红包, 收支健康",
            "syn": ["计划内", "团圆宴", "红包", "收支健康"],
            "red": ["巨额开支", "欠债", "破产", "被骗"],
            "entities": ["${gift}"], "evidence": ["K3", "K5", "K6"]},
        "dim:career": {
            "core": "特意排出团圆档期, 工作学业为家庭让路一日, 节奏张弛有度",
            "syn": ["团圆档期", "让路", "张弛有度", "请假团圆"],
            "red": ["旷工", "被开除", "挂科", "丢单"],
            "entities": [], "evidence": ["K1", "K2"]},
    },
    "background": ["买菜", "打扫", "追剧"],
})

# A19 户外遇险下撤
ARCS.append({
    "arc_id": "A19_OUTDOOR_RESCUE", "title": "高山遇险决断下撤",
    "personas": ["P11"],
    "slots": {
        "member": ["队员小杨", "新手阿杰"],
        "injury": ["崴脚加失温前兆", "高反头痛呕吐"],
        "place": ["垭口", "碎石坡", "峡谷"],
        "weather": ["暴雨加降温大雾", "冰雹加大风"],
        "base": ["大本营", "山下农家乐"],
    },
    "beats": [
        {"key": "K1", "t": "07:30", "mod": "mic", "source": "出发前",
         "texts": ["出发前逐人检查装备: 冲锋衣头灯急救包, 有一样不合格都不让上山",
                   "整队训话: 今天天气后半程转坏, 听我口令, 擅自行动的直接劝返"]},
        {"key": "K2", "t": "11:00", "mod": "mic", "source": "独白",
         "texts": ["${place}一带${weather}说来就来, 能见度不足十米, 队伍开始慌",
                   "走到${place}遭遇${weather}, 风大得站不稳, 赶紧找背风处清点人数"]},
        {"key": "K3", "t": "13:40", "mod": "mic", "source": "${member}",
         "texts": ["${member}${injury}, 脸色煞白走不了了, 全队气氛一下绷紧",
                   "${member}出状况:${injury}, 我一边急救一边安抚, 手都在抖"]},
        {"key": "K4", "t": "14:20", "mod": "mic", "source": "决断",
         "texts": ["当机立断: 放弃登顶全员下撤! 我背${member}走中间, 强驴前后压阵",
                   "下令下撤: 山永远在, 人必须安全回去, 反对者保留意见跟我走"]},
        {"key": "K5", "t": "17:30", "mod": "mic", "source": "${base}",
         "texts": ["全员安全抵达${base}, ${member}喝上热水缓过来, 大家鼓掌又后怕",
                   "回到${base}清点一个不少, ${member}已无大碍, 悬着的心落地"]},
        {"key": "K6", "t": "21:00", "mod": "app", "source": "复盘",
         "texts": ["连夜写复盘: 以后新手线强制装备清单加天气熔断线, 安全手册更新两条",
                   "复盘发群里: ${weather}预警其实早有, 下次必须提前12小时熔断"]},
    ],
    "vitals": {"sleep": (6.6, 7.6), "rest_hr": (52, 60), "steps": (22000, 30000),
               "episodes": [
        {"key": "V1", "t": "13:45", "signal": "heart_rate", "reading": "135bpm",
         "context": "高海拔负重处置${injury}时(运动性)"},
    ]},
    "gt": {
        "global": {
            "core": "${place}突遇${weather}, ${member}${injury}, 果断弃登顶全员下撤, 有惊无险并连夜复盘立规",
            "syn": ["突遇恶劣天气", "${weather}", "队员受伤", "${injury}", "果断下撤",
                    "弃登顶", "有惊无险", "复盘", "立规"],
            "red": ["登顶成功", "队员遇难", "失联", "见死不救", "继续冲顶"],
            "entities": ["${place}", "${member}", "${injury}"], "evidence": ["K2", "K3", "K4"]},
        "dim:health": {
            "core": "领队135bpm为高海拔运动性升高无异常; ${member}${injury}经处置恢复, 全员无大碍",
            "syn": ["135", "运动性", "无异常", "${injury}", "处置恢复", "无大碍"],
            "red": ["心梗", "猝死", "截肢", "失温身亡", "脑水肿病危"],
            "entities": ["${member}", "${injury}"], "evidence": ["V1", "K3", "K5"]},
        "dim:social": {
            "core": "领队决断服众, 队员互助压阵, 团队信任经考验加深",
            "syn": ["决断", "服众", "互助", "压阵", "信任", "团队"],
            "red": ["内讧", "抛弃队友", "投诉", "众叛亲离"],
            "entities": ["${member}"], "evidence": ["K4", "K5"]},
        "dim:emotion": {
            "core": "上午专注中午紧张下午决绝晚上后怕庆幸, 主基调专业冷静下的心跳",
            "syn": ["专注", "紧张", "决绝", "后怕", "庆幸", "冷静"],
            "red": ["狂喜", "崩溃", "麻木", "恐慌失控"],
            "entities": [], "evidence": ["K2", "K4", "K5"]},
        "dim:finance": {
            "core": "行程中断致尾款减免部分, 另增急救与交通开支, 小额亏损可承受",
            "syn": ["尾款减免", "小额亏损", "可承受", "急救开支"],
            "red": ["巨额赔偿", "破产", "跑路", "暴富"],
            "entities": [], "evidence": ["K4", "K5"]},
        "dim:career": {
            "core": "安全处置保住领队口碑, 复盘输出两条新規, 职业专业度+1",
            "syn": ["安全处置", "口碑", "复盘", "新規", "专业度"],
            "red": ["吊销执照", "封杀", "事故定责", "转行"],
            "entities": [], "evidence": ["K4", "K6"]},
    },
    "background": ["吃干粮", "拍照", "听歌"],
})

PERSONA_ARCS: Dict[str, List[int]] = {}
for _ai, _arc in enumerate(ARCS):
    for _pid in _arc["personas"]:
        PERSONA_ARCS.setdefault(_pid, []).append(_ai)


# ---------------------------------------------------------------------------
# 组卷引擎
# ---------------------------------------------------------------------------

def pick_difficulty(rng: random.Random) -> str:
    total = sum(w for _, w in DIFFICULTY_WEIGHTS)
    r = rng.uniform(0, total)
    acc = 0.0
    for name, w in DIFFICULTY_WEIGHTS:
        acc += w
        if r <= acc:
            return name
    return "MEDIUM"


def sample_slots(rng: random.Random, slot_pools: Dict[str, List[str]]) -> Dict[str, str]:
    return {k: rng.choice(v) for k, v in slot_pools.items()}


def build_paper(idx: int, rng: random.Random) -> Dict[str, Any]:
    qid = f"{QUESTION_PREFIX}{idx:05d}"
    persona = rng.choice(PERSONAS)
    arc = ARCS[rng.choice(PERSONA_ARCS[persona["id"]])]
    difficulty = pick_difficulty(rng)
    slot_pools = dict(arc["slots"])
    slot_pools.update(arc.get("slot_overrides", {}).get(persona["id"], {}))
    slots = sample_slots(rng, slot_pools)
    slots["name"] = persona["name"]
    day = 1 + (idx % 16)
    exam_date = f"2026-09-{day:02d}"

    # --- 关键节拍 (支持按人格替换文本变体) ---
    items: List[Dict[str, Any]] = []
    for b in arc["beats"]:
        t = max(T0_MIN, min(T1_MIN, P(b["t"]) + rng.randint(-8, 8)))
        texts = b.get("persona_texts", {}).get(persona["id"], b["texts"])
        items.append({"key": b["key"], "t": t, "mod": b["mod"],
                      "source": render(b["source"], slots),
                      "text": render(rng.choice(texts), slots)})
    # --- 体征事件 -> sensor 切片 ---
    vit = arc["vitals"]
    for ep in vit["episodes"]:
        t = max(T0_MIN, min(T1_MIN, P(ep["t"]) + rng.randint(-5, 5)))
        reading = render(ep["reading"], slots)
        context = render(ep["context"], slots)
        label = SIGNAL_ZH.get(ep["signal"], ep["signal"])
        items.append({"key": ep["key"], "t": t, "mod": "sensor",
                      "source": "手环体征",
                      "text": f"{T(t)} {label}读数{reading}({context})"})
    # --- ADVERSARIAL: 诱饵 + 隐藏 twist ---
    bg_extra: List[str] = []
    if difficulty == "ADVERSARIAL":
        decoy = rng.choice([d for d in DECOYS
                            if persona["id"] not in d.get("exclude", set())])
        t = max(T0_MIN, min(T1_MIN, P(decoy["t"]) + rng.randint(-15, 15)))
        items.append({"key": "D1", "t": t, "mod": decoy["mod"],
                      "source": decoy["source"], "text": decoy["text"]})
        bg_extra.append(decoy["bg"])
        if "twist" in arc:
            tw = arc["twist"]["beat"]
            t = max(T0_MIN, min(T1_MIN, P(tw["t"]) + rng.randint(-8, 8)))
            tw_texts = tw.get("persona_texts", {}).get(persona["id"], tw["texts"])
            items.append({"key": tw["key"], "t": t, "mod": tw["mod"],
                          "source": render(tw["source"], slots),
                          "text": render(rng.choice(tw_texts), slots)})
    # --- 琐碎填充 (人格过滤 + 卷内去重; 传感器填充固定时刻) ---
    n_fill = rng.randint(*FILLER_COUNT[difficulty])
    used_t = {it["t"] for it in items}
    used_fill: set = set()
    fillers_used = 0
    guard = 0
    while fillers_used < n_fill and guard < 600:
        guard += 1
        kind = rng.random()
        if kind < 0.5:
            pool, mod = FILLER_MIC, "mic"
        elif kind < 0.85:
            pool, mod = FILLER_APP, "app"
        else:
            pool, mod = FILLER_SENSOR, "sensor"
        fi = rng.randrange(len(pool))
        f = pool[fi]
        tag = (mod, fi)
        if tag in used_fill or not _filler_ok(f, persona["id"]):
            continue
        if mod == "sensor":
            t = max(T0_MIN, min(T1_MIN, P(f["t"]) + rng.randint(-5, 5)))
        elif f.get("window"):
            w0, w1 = f["window"]
            t = rng.randrange(max(T0_MIN, w0), min(T1_MIN, w1) + 1, 5)
        else:
            t = rng.randrange(T0_MIN, T1_MIN + 1, 5)
        if t in used_t:
            continue
        used_t.add(t)
        used_fill.add(tag)
        items.append({"key": f"F{fillers_used}", "t": t, "mod": mod,
                      "source": f["source"], "text": render(f["text"], slots)})
        fillers_used += 1

    items.sort(key=lambda x: (x["t"], x["key"]))
    key_to_slice: Dict[str, str] = {}
    slices: List[Dict[str, Any]] = []
    for i, it in enumerate(items, start=1):
        sid = f"{qid}-s{i:03d}"
        key_to_slice[it["key"]] = sid
        slices.append({"slice_id": sid, "time": T(it["t"]), "modality": it["mod"],
                       "source": it["source"], "text": it["text"]})

    # --- 体征宏观摘要 ---
    sleep_h = round(rng.uniform(*vit["sleep"]), 1)
    rest_hr = rng.randint(*vit["rest_hr"])
    steps = rng.randint(*vit["steps"])
    episodes = []
    for ep in vit["episodes"]:
        episodes.append({"time": T(next(it["t"] for it in items if it["key"] == ep["key"])),
                         "signal": ep["signal"],
                         "reading": render(ep["reading"], slots),
                         "context": render(ep["context"], slots)})

    # --- 六维方向标答 (支持按人格替换整维标答) ---
    gt: Dict[str, Any] = {}
    for dim_key in ("global", "dim:health", "dim:social",
                    "dim:emotion", "dim:finance", "dim:career"):
        g = arc.get("gt_overrides", {}).get(persona["id"], {}).get(dim_key, arc["gt"][dim_key])
        core = render(g["core"], slots)
        syn = [render(s, slots) for s in g["syn"]]
        red = [render(s, slots) for s in g["red"]]
        ents = [render(s, slots) for s in g.get("entities", [])]
        ev = [key_to_slice[k] for k in g.get("evidence", []) if k in key_to_slice]
        if difficulty == "ADVERSARIAL" and "twist" in arc:
            patch = arc["twist"].get("patch", {}).get(dim_key)
            if patch:
                core += patch.get("suffix", "")
                syn += patch.get("syn_add", [])
                red += patch.get("red_add", [])
            for k in arc["twist"].get("evidence_add", {}).get(dim_key, []):
                if k in key_to_slice and key_to_slice[k] not in ev:
                    ev.append(key_to_slice[k])
        gt[dim_key] = {"core_statement": core, "accepted_synonyms": syn,
                       "red_lines": red, "key_entities": ents,
                       "evidence_slice_ids": ev}
    gt["background_to_ignore"] = list(dict.fromkeys(
        [render(b, slots) for b in arc.get("background", [])]
        + bg_extra + GENERIC_BACKGROUND))

    paper = {
        "question_id": qid,
        "generator_agent": GENERATOR_AGENT,
        "exam_date": exam_date,
        "difficulty": difficulty,
        "persona": {"persona_id": persona["id"], "name": persona["name"],
                    "age": persona["age"], "gender": persona["gender"],
                    "occupation": persona["occupation"],
                    "life_stage": persona["life_stage"], "city": persona["city"],
                    "household": persona["household"], "traits": list(persona["traits"])},
        "cleaned_daily_stream": {
            "vitals_summary": {"sleep_hours_last_night": sleep_h,
                               "wake_resting_hr_bpm": rest_hr,
                               "daily_steps": steps,
                               "notable_episodes": episodes},
            "slices": slices,
        },
        "directional_ground_truth": gt,
        "_meta": {"arc_id": arc["arc_id"], "arc_title": arc["title"]},
    }
    return paper


def split_blind_gt(paper: Dict[str, Any]):
    blind = {k: paper[k] for k in ("question_id", "generator_agent", "exam_date",
                                  "difficulty", "persona", "cleaned_daily_stream")}
    gt = {"question_id": paper["question_id"], "generator_agent": paper["generator_agent"],
          "difficulty": paper["difficulty"],
          "directional_ground_truth": paper["directional_ground_truth"]}
    master = {k: v for k, v in paper.items() if k != "_meta"}
    master["_meta"] = paper["_meta"]
    return master, blind, gt


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            f.write(line + "\n")
            h.update((line + "\n").encode("utf-8"))
    return h.hexdigest()


def validate_papers(papers: List[Dict[str, Any]]) -> None:
    repo_src = Path(__file__).resolve().parents[3] / "src"
    sys.path.insert(0, str(repo_src))
    from aios_core.simulation.summary_arena_protocol import (  # noqa: E402
        BlindDailyQuestion, DailyGTRecord, DailyPaper)

    for p in papers:
        master, blind, gt = split_blind_gt(p)
        m = {k: v for k, v in master.items() if k != "_meta"}
        DailyPaper.model_validate(m)
        BlindDailyQuestion.model_validate(blind)
        DailyGTRecord.model_validate(gt)
        # 证据链可解 + 时间有序 + 标答非空
        sids = {s["slice_id"] for s in p["cleaned_daily_stream"]["slices"]}
        times = [s["time"] for s in p["cleaned_daily_stream"]["slices"]]
        assert times == sorted(times), p["question_id"]
        assert all(T0_MIN <= P(t) <= T1_MIN for t in times), p["question_id"]
        for dim in ("global", "dim:health", "dim:social",
                    "dim:emotion", "dim:finance", "dim:career"):
            a = p["directional_ground_truth"][dim]
            assert a["core_statement"] and len(a["accepted_synonyms"]) >= 4, (p["question_id"], dim)
            assert len(a["red_lines"]) >= 3, (p["question_id"], dim)
            assert all(e in sids for e in a["evidence_slice_ids"]), (p["question_id"], dim)
            overlap = set(a["accepted_synonyms"]) & set(a["red_lines"])
            assert not overlap, (p["question_id"], dim, overlap)
        # 同义与红线不得互串 (子串级)
        for dim in ("global", "dim:health", "dim:social",
                    "dim:emotion", "dim:finance", "dim:career"):
            a = p["directional_ground_truth"][dim]
            for s in a["accepted_synonyms"]:
                for r in a["red_lines"]:
                    assert not (s and r and (s in r or r in s)), (p["question_id"], dim, s, r)


def main() -> int:
    ap = argparse.ArgumentParser(description="全天生活流多维总结出卷引擎")
    ap.add_argument("--count", type=int, default=TOTAL_DEFAULT)
    ap.add_argument("--out-dir", default="benchmarks/daily_summary")
    ap.add_argument("--seed", type=lambda x: int(x, 0), default=SEED_DEFAULT)
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    papers = [build_paper(i, random.Random(f"{args.seed}:{i}"))
              for i in range(1, args.count + 1)]
    if args.validate:
        validate_papers(papers)
        print(f"[validate] {len(papers)} 卷全部通过 DailyPaper 契约校验")

    out = Path(args.out_dir)
    masters, blinds, gts = [], [], []
    for p in papers:
        m, b, g = split_blind_gt(p)
        masters.append(m)
        blinds.append(b)
        gts.append(g)
    mp = out / "papers" / f"papers_{GENERATOR_AGENT.replace('-', '_')}.jsonl"
    qp = out / "questions" / f"questions_{GENERATOR_AGENT.replace('-', '_')}.jsonl"
    gp = out / "ground_truth" / f"gt_{GENERATOR_AGENT.replace('-', '_')}.jsonl"
    # 母卷含内部 _meta, 落盘前剥离 (统计另存 manifest)
    masters_disk = [{k: v for k, v in m.items() if k != "_meta"} for m in masters]
    m_sha = write_jsonl(mp, masters_disk)
    q_sha = write_jsonl(qp, blinds)
    g_sha = write_jsonl(gp, gts)

    # 盲卷泄漏审计: 标答键不得出现在盲卷
    qp_text = qp.read_text(encoding="utf-8")
    for leak in ("core_statement", "accepted_synonyms", "red_lines", "background_to_ignore"):
        assert leak not in qp_text, f"盲卷泄漏: {leak}"

    manifest = {
        "generator_agent": GENERATOR_AGENT,
        "seed": hex(args.seed),
        "total_papers": len(papers),
        "persona_distribution": dict(Counter(p["persona"]["persona_id"] for p in papers)),
        "arc_distribution": dict(Counter(p["_meta"]["arc_id"] for p in papers)),
        "difficulty_distribution": dict(Counter(p["difficulty"] for p in papers)),
        "avg_slices_per_paper": round(sum(len(p["cleaned_daily_stream"]["slices"])
                                          for p in papers) / len(papers), 1),
        "files": {str(mp): {"sha256": m_sha}, str(qp): {"sha256": q_sha},
                  str(gp): {"sha256": g_sha}},
        "protocol": "src/aios_core/simulation/summary_arena_protocol.py::DailyPaper",
        "judge": "src/aios_core/simulation/summary_arena_protocol.py::DirectionalSummaryJudge",
        "note": "盲卷 questions_* 已审计无标答泄漏; 做题人只能读取 questions 文件.",
    }
    manifest_p = out / "reports" / f"manifest_{GENERATOR_AGENT.replace('-', '_')}.json"
    manifest_p.parent.mkdir(parents=True, exist_ok=True)
    manifest_p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
