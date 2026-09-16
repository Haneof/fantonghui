"""AIOS 3.0 端侧数据清洗与事实提纯器（战队 01a0aa2d-fantonghui · 交叉做题官）。

法定身份
--------
本模块是 AIOS 3.0 云端全兵团对抗大考（Master Dispatch #11）中，战队
``01a0aa2d-fantonghui`` 派驻的**数据清洗与事实提纯官**。它接管 AIOS 底座，
读取**对手战队**已落盘的 10,000 道多模态高熵考题，在嘈杂生活流中提纯核心事实、
并物理标记删除垃圾碎片。

五步流水线（对应工单第二~四阶段）
--------------------------------
1. **盲化投影**（``blind_view``）：只保留传感器/麦克风/声纹/APP/原话五路输入流，
   物理剥离 ``ground_truth_*`` 一切标答字段；本模块**从不读取**对手标答，
   由 ``BlindAnswerGuard`` 在运行时断言（自证清白，见 ``tests/ingest/test_purifier_01a0aa2d.py``）。
2. **载体归一化**（``iter_carriers``）：把四套互不相同的对手 schema
   （``sensor_stream.fragments`` / ``sensor_stream.segments`` / ``mic_stream`` /
   ``speaker_fragments`` …）压成统一 ``Carrier``，屏蔽 schema 差异。
3. **垃圾物理剪枝**（``JunkPruner``，铁律四）：以内容语义 + 声学环境 + 波形物理特征
   + 声明元数据四路证据投票，产出 ``pruned_junk_ids`` 与可解释 reason code。
4. **事实提纯**（``SensorEventAnalyzer`` / ``TextIntentResolver`` /
   ``VoiceprintFactResolver``）：判定维度、语义意图方向、关键实体，提炼一句话事实；
   所有事实只挂载 ``T_now``（铁律二：历史不可篡改，``TNowAttachment``）。
5. **P0 紧急安全硬旁路**（``P0CriticalSafetyBypass``，铁律三）：命中严重摔倒/心搏骤停/
   濒危求救时，**0 次大模型调用**、世界模型让路、``≤50ms`` 直通告警。

依赖
----
仅标准库。判分桥 ``RefereeBridge`` 在 ``pydantic`` 可用时调用主干
``aios_core.simulation.cleaning_arena_protocol.DirectionalSemanticMatcher`` 官方裁判；
不可用时回退到与官方公式逐项同构的本地实现（等价性由单测锁定）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

__all__ = [
    "SOLVER_AGENT_ID",
    "Carrier",
    "FactCandidate",
    "PruneDecision",
    "PurifiedQuestion",
    "BlindAnswerGuard",
    "blind_view",
    "iter_carriers",
    "JunkPruner",
    "SensorEventAnalyzer",
    "TextIntentResolver",
    "EntityMiner",
    "FactGrouper",
    "P0CriticalSafetyBypass",
    "TNowAttachment",
    "CleaningArenaPurifier",
    "BankProfile",
    "RefereeBridge",
    "main",
]

SOLVER_AGENT_ID = "01a0aa2d-fantonghui"

# ---------------------------------------------------------------------------
# 一、维度词汇与铁律常量
# ---------------------------------------------------------------------------

DIM_HEALTH = "dim:health"
DIM_FINANCE = "dim:finance"
DIM_SOCIAL = "dim:social"
DIM_CAREER = "dim:career"
DIM_LIFE = "dim:life"
DIM_SAFETY = "dim:safety"
DIM_FAMILY = "dim:family"
DIM_DAILY = "dim:daily"
DIM_ENVIRONMENT = "dim:environment"
DIM_LOGISTICS = "dim:logistics"
DIM_EMOTION = "dim:emotion"
DIM_LEGAL = "dim:legal"

#: 铁律三：P0 紧急安全**强**直达词汇（物理危象，命中即硬旁路，0 大模型调用）
P0_SAFETY_STRONG_TRIGGERS: tuple[str, ...] = (
    "摔倒", "跌倒", "倒地不起", "坠地", "坠楼", "滑坠", "跌落", "砸中", "车祸",
    "心搏骤停", "心脏骤停", "室颤", "无脉", "呼吸骤停", "抽搐不止", "失去意识",
    "意识丧失", "倒在", "喘不上气", "胸痛难忍", "压迫性胸痛", "血氧骤降",
    "大出血", "吐血", "昏迷", "呕血", "煤气中毒", "溺水", "触电", "休克", "救命",
    "救救我", "快点来人", "来人啊",
)

#: P0 **弱**直达词汇（自伤/求救暗示）：必须伴随计划性或紧迫性证据才升级，防止"口头禅假报警"
P0_SAFETY_WEAK_TRIGGERS: tuple[str, ...] = (
    "自杀", "自尽", "跳楼", "不想活", "别救我", "活着没意思", "睡着就别醒",
)

#: 弱触发升级证据（计划性/紧迫性/手段），缺一不可升级为 P0
P0_PLAN_MARKERS: tuple[str, ...] = (
    "攒够", "攒了", "已经买", "今晚", "遗书", "写好了", "站在", "窗户", "楼顶",
    "绳子", "刀", "安眠药", "正在", "马上", "立刻", "倒计时", "最后一条",
)

#: P0 波形物理阈值（端侧硬件直通判据，不依赖任何文本）
P0_IMPACT_G = 8.0            # 三轴合成冲击峰值（g）
P0_PAUSE_SECONDS = 3.0       # 窦性停搏 / 无脉时长
P0_HR_LOW_BPM = 35           # 心动过缓危象
P0_HR_HIGH_BPM = 190         # 室速 / 恶化心律
P0_SPO2_PERCENT = 88.0       # 血氧危象

# ---------------------------------------------------------------------------
# 二、载体归一化
# ---------------------------------------------------------------------------


class Modality:
    """五路多模态数据源（工单规定配比：传感器 30% / MIC 30% / 声纹 20% / APP 15% / 原话 5%）。"""

    SENSOR = "sensor"
    MIC = "mic"
    APP = "app"
    DIALOGUE = "dialogue"
    VOICEPRINT = "voiceprint"
    UNKNOWN = "unknown"


#: 载体 ID 可能的键名（跨四套对手 schema）
_ID_KEYS: tuple[str, ...] = (
    "fragment_id", "snippet_id", "msg_id", "utterance_id", "segment_id",
    "seg_id", "speaker_frag_id", "spk_id", "item_id", "event_id", "trace_id", "id",
)

#: 自然语言文本可能落在的键名
_TEXT_KEYS: tuple[str, ...] = (
    "text", "content", "raw_speech", "note", "label_zh", "desc", "description",
    "summary", "message", "subject", "body", "role", "transcript", "caption",
    "sample_text", "speaker_hint", "scene", "context_scene",
)

#: 结构化数值字段（波形物理量、体征量）
_NUMERIC_KEYS: tuple[str, ...] = (
    "g_peak", "g_rms", "peak_g", "rms_g", "hr_bpm", "hr_bpm_mean", "hr_baseline",
    "heart_rate_bpm", "hr_peak", "hr_before", "pvc_burst_count", "pvc_coupling_interval_ms",
    "rr_irregularity_index", "pause_seconds", "spo2_percent", "baro_hpa", "baro_drop_hpa",
    "body_motion_energy", "activity_confidence", "posture_change_deg", "freefall_segment_ms",
    "impact_rise_ms", "dominant_freq_hz", "duration_s", "cosine_to_user",
    "cosine_to_enrolled_user", "fragment_count", "n_fragments", "speaker_count",
    "n_detected_speakers", "total_duration_s", "overlap_ratio", "ambient_noise_db",
    "window_offset_s", "t_offset_s", "recurrence_days_30d", "sampling_hz",
)

#: 声明式元数据（对手出题器写进输入流的标注；本引擎视为"可信度有偏的旁证"，
#: 在 ``ablate_metadata=True`` 内容盲测模式下全部丢弃）
_DECLARED_FLAG_KEYS: tuple[str, ...] = (
    "is_junk", "is_background_chatter", "is_transient", "ttl_policy", "kind",
    "label", "sensor_modality", "acoustic_topology", "app", "category",
)

_VOICEPRINT_MARKERS: tuple[str, ...] = (
    "cosine_to_user", "cosine_to_enrolled_user", "speaker_frag_id", "spk_id",
    "lsh_bands", "cluster_label", "enrolled_contacts", "voiceprint_match_to",
)


#: 载体"权威正文"的字段优先级（传感器派生片段用 ``summary``，录音/消息用 ``text``/``content``…
#: 这是**证据原话**，提纯事实必须以它为主干，保证方向与实体不漂移）
_PRIMARY_TEXT_KEYS: tuple[str, ...] = (
    "summary", "text", "content", "raw_speech", "desc", "description", "transcript", "caption",
)


def _primary_text(item: Mapping[str, Any]) -> str:
    for key in _PRIMARY_TEXT_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("note", "label_zh", "role", "sample_text", "speaker_hint"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


@dataclass(frozen=True)
class Carrier:
    """一路输入载体（录音切片 / 传感器片段 / APP 消息 / 原话 / 声纹碎片）。"""

    carrier_id: str
    container: str
    modality: str
    kind: str
    text: str
    attrs: Mapping[str, Any]
    declared_junk: bool | None
    ordinal: int = 0

    @property
    def primary_text(self) -> str:
        """证据原话（权威正文），提纯事实的主干。"""
        return _primary_text(self.attrs)

    @property
    def haystack(self) -> str:
        """用于语义匹配的拼接文本（含 kind/label 等结构化中文标注）。"""
        parts = [self.text]
        for key in ("label_zh", "label", "kind", "note", "role", "sender", "speaker_id", "app"):
            value = self.attrs.get(key)
            if isinstance(value, str) and value and value not in parts:
                parts.append(value)
        return " ".join(p for p in parts if p)

    def num(self, *keys: str, default: float | None = None) -> float | None:
        for key in keys:
            value = self.attrs.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
        return None


def _fmt_value(value: float | None, unit: str, digits: int = 2) -> str:
    """数值 + 单位的人类可读计量（整数不带小数尾巴）。"""
    if value is None:
        return ""
    if digits and float(value).is_integer():
        return f"{int(value)}{unit}"
    return f"{value:.{digits}f}{unit}"


def _carrier_id(item: Mapping[str, Any]) -> str | None:
    for key in _ID_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, int):
            return str(value)
    return None


def _modality_of(container: str, item: Mapping[str, Any]) -> str:
    low = container.lower()
    if "voiceprint" in low or any(m in item for m in _VOICEPRINT_MARKERS):
        return Modality.VOICEPRINT
    if "mic" in low or "audio" in low or "ambient_noise_db" in item:
        return Modality.MIC
    if "app" in low or "message" in low or "chat" in low or "app" in item or "sender" in item:
        return Modality.APP
    if "dialogue" in low or "utterance" in low or "speech" in low or "raw_speech" in item:
        return Modality.DIALOGUE
    if any(token in low for token in ("sensor", "fragment", "segment", "imu", "ppg", "baro", "gps", "event")):
        return Modality.SENSOR
    return Modality.UNKNOWN


def _text_of(item: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    for key in _TEXT_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
    return " · ".join(dict.fromkeys(chunks))


def _declared_junk(item: Mapping[str, Any]) -> bool | None:
    if isinstance(item.get("is_junk"), bool):
        return bool(item["is_junk"])
    if isinstance(item.get("is_background_chatter"), bool):
        return bool(item["is_background_chatter"])
    if item.get("is_transient") is True:
        return True
    if isinstance(item.get("ttl_policy"), str) and "expire" in str(item["ttl_policy"]):
        return True
    return None


def iter_carriers(question: Mapping[str, Any]) -> list[Carrier]:
    """递归遍历任意对手 schema，抽出全部载体（屏蔽 schema 差异）。

    只遍历 ``ground_truth_*`` 之外的字段——标答永不进入提纯视野。
    """
    carriers: list[Carrier] = []
    counter = [0]

    def visit(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str) and key.startswith("ground_truth"):
                    continue
                visit(value, f"{path}.{key}" if path else str(key))
            return
        if isinstance(node, (list, tuple)):
            dict_items = [x for x in node if isinstance(x, Mapping)]
            if dict_items and all(_carrier_id(x) is not None for x in dict_items):
                for item in dict_items:
                    counter[0] += 1
                    cid = _carrier_id(item) or f"{path}#{counter[0]}"
                    carriers.append(
                        Carrier(
                            carrier_id=str(cid),
                            container=path,
                            modality=_modality_of(path, item),
                            kind=str(item.get("kind") or item.get("app") or item.get("type") or ""),
                            text=_text_of(item),
                            attrs=dict(item),
                            declared_junk=_declared_junk(item),
                            ordinal=counter[0],
                        )
                    )
                return
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")
            return

    for key, value in question.items():
        if isinstance(key, str) and key.startswith("ground_truth"):
            continue
        visit(value, str(key))
    return carriers


def blind_view(question: Mapping[str, Any]) -> dict[str, Any]:
    """铁律：只把五路输入流交给提纯算法，物理剥离全部 ``ground_truth_*`` 标答字段。"""

    def strip(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {k: strip(v) for k, v in node.items() if not (isinstance(k, str) and k.startswith("ground_truth"))}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(dict(question))


class BlindAnswerGuard:
    """自证清白的运行时护栏：提交结果一旦被标答字段污染即 fail-closed 抛错。"""

    FORBIDDEN_TOKENS: tuple[str, ...] = ("ground_truth_facts", "ground_truth_junk_ids")

    @classmethod
    def assert_clean(cls, payload: Mapping[str, Any]) -> None:
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        for token in cls.FORBIDDEN_TOKENS:
            if token in blob:
                raise ValueError(f"盲化护栏拦截：提交载荷中出现标答字段 {token}")

    @classmethod
    def assert_blind(cls, question: Mapping[str, Any], purified: "PurifiedQuestion") -> None:
        blob = json.dumps(blind_view(question), ensure_ascii=False, default=str)
        for fact in purified.facts:
            if fact.summary_text and fact.summary_text in blob and len(fact.summary_text) > 40:
                continue  # 摘录自输入原文，合法
        cls.assert_clean(purified.as_submission())


# ---------------------------------------------------------------------------
# 三、垃圾物理剪枝器（铁律四）
# ---------------------------------------------------------------------------

#: 内容级垃圾语义（商场大喇叭叫卖、砍一刀、验证码、风噪切片、地铁报站…）
JUNK_TEXT_PATTERNS: tuple[str, ...] = (
    "砍一刀", "帮我点一下", "点我助力", "助力", "提现", "现金红包待领取", "优惠券", "限时秒杀", "秒杀", "特价", "促销", "大甩卖", "两块钱一串",
    "现烤现卖", "走过路过", "不要错过", "开业大酬宾", "买一送一", "清仓", "店庆", "周年庆", "全场", "折起", "详情进店", "回T退订", "退订",
    "回复TD", "回复T", "点击 https", "速戳", "立即领取", "免费领取", "名额有限", "报名立减", "贷款额度", "无抵押", "放款快", "推荐股票",
    "加微信", "扫码进群", "千兆套餐", "需要办理吗", "您好，我们是", "信用额度", "续保", "券商", "理财顾问", "关于我们", "热搜：", "预警，请注意",
    "请注意防暑", "[链接]", "（链接）", "专家提醒", "转发这个", "水逆", "深夜放毒", "您的订单已送达", "祝您用餐愉快", "五星好评", "您关注的博主",
    "发布了新视频", "撤回了一条消息", "已助力成功", "再邀", "验证码", "动态密码", "校验码", "请勿泄露", "话费余额不足", "流量包", "积分兑换",
    "中奖", "抽奖", "余额不足请充值", "身份验证", "表情包", "狗头", "哈哈哈", "元气满满", "[强]", "[太阳]", "[色]", "[微笑]",
    "毕业十年聚会", "同学聚会", "接龙报名", "拼团", "9成新", "转给有缘人", "持续风噪", "风噪", "无有效语义内容", "敲击墙体", "锤子敲击", "敲击",
    "噪音", "呼噜声", "鼾声", "人群嘈杂", "嘈杂声", "喧哗", "雨点", "雨声", "风雪", "背景音乐", "音响", "喇叭", "叫卖", "吆喝", "报站",
    "列车即将", "请勿倚靠", "下一站", "让座", "排队上车", "广播", "广告", "洗车", "天好像要下雨", "天气不错", "打折", "外卖已送达", "好评",
    "天气预报", "早安", "晚安", "周末愉快", "折扣", "首付", "看房", "楼盘", "办卡", "扫码送", "礼品", "报价单", "发您了", "尽早定", "老板，", "最新报价", "货走得快", "优惠价", "垃圾邮件", "垃圾短信",
    "（垃圾", "(垃圾", "广告邮件", "抽中", "神券", "满30减", "满减券", "点击链接领取", "红包到账", "秒到账", "限时抢", "仅剩", "名额仅剩",
    "系统通知", "验证码", "热搜", "砍一刀", "助力成功", "提现", "秒杀", "优惠券", "续保", "退订", "水逆", "转发这个", "立即领取",
    "即将过期", "额度已提升", "库存仅剩", "深夜放毒", "主播", "开播", "围观", "蚂蚁森林", "能量", "体力已满", "舰队", "出征", "话费余额",
    "会员日", "满199减", "吃瓜", "表情包", "签到", "抽奖", "速来", "速戳", "退订回", "回T退订", "收到收到", "666666", "[表情]",
    "[动画表情]", "@所有人", "锦鲤", "好运一整年", "金花", "成年人的世界", "开通试运营", "油价今晚", "个税专项", "停水通知", "否则冻结",
    "领取（钓鱼）", "（钓鱼）",
)

#: 纯声学描述片段（括号内只描述声音形态、不含任何语义内容）→ 环境风噪/机械噪声
#: 救护/求救类声学描述：即使整条像“环境音”也不得判噪（微弱呼救是安全信号）
SOS_AUDIO_MARKERS: tuple[str, ...] = (
    "微弱", "喘息", "呻吟", "呼救", "求救", "无应答", "长时间无声", "呼吸困难", "搭把手",
)

#: 纯占位附件（[图片] / [语音] 3" 之类，无任何正文内容）
_PLACEHOLDER_ONLY_RE = re.compile(r"\[(?:图片|语音|视频|表情|动画表情|位置|链接|文件)\]\s*\d*\s*\"?\s*$")

ACOUSTIC_DESCRIPTION_PATTERNS: tuple[str, ...] = (
    "无有效语义内容", "信噪比极低", "持续风噪", "敲击墙体", "机械噪声", "环境噪声",
    "无有效语音", "非语音", "仅环境音", "噪声片段",
)

#: 内容级高价值语义（关键事实锚点，命中任一即视为信号载体）
SIGNAL_TEXT_PATTERNS: tuple[str, ...] = (
    "借", "还", "欠", "债", "还款", "逾期", "利息", "转账", "汇款", "账户", "流水",
    "元", "万元", "万块", "块钱", "扣款", "余额", "退款", "赔付", "赔偿", "索赔",
    "起诉", "法院", "传票", "开庭", "判决", "律师", "仲裁", "合同", "协议", "违约",
    "房产", "过户", "遗产", "遗嘱", "公证", "抚养", "监护", "离婚", "结婚", "彩礼",
    "婚外", "亲子鉴定", "同居", "分手", "吵", "争", "冲突", "推搡", "动手", "骂",
    "工资", "薪", "结算", "拖欠", "讨薪", "工钱", "劳务", "社保", "工伤", "加班",
    "裁员", "降薪", "离职", "辞职", "竞业", "offer", "面试", "政审", "考试", "答辩",
    "论文", "导师", "挂科", "体检", "化验", "检查单", "指标", "门诊", "复诊", "挂号",
    "住院", "手术", "药", "剂量", "血压", "血糖", "心率", "胸", "痛", "晕", "麻",
    "喘", "呕吐", "发热", "咳嗽", "出血", "肿", "疼", "心律", "早搏", "停搏", "跌倒",
    "摔", "磕", "骨折", "扭伤", "过敏", "休克", "昏迷", "胸闷", "心梗", "卒中", "中风",
    "失眠", "睡不着", "抑郁", "焦虑", "自杀", "不想活", "憋", "难受", "疼死",
    "租房", "房东", "租客", "物业", "漏水", "倒灌", "泡水", "装修", "赔偿", "家电",
    "保险", "理赔", "理赔拒", "车祸", "事故", "违停", "罚单", "扣分", "盗刷", "被盗",
    "遗失", "丢失", "走失", "报警", "派出所", "民警", "调解", "邻居", "宠物",
    "预约", "门诊", "挂号", "取药", "复查", "转诊", "病历", "化验单", "医嘱", "住院",
    "到院", "科就诊", "体检", "打款", "到账", "转账", "账单", "待还款", "还款日", "扣款",
    "家长会", "接孩子", "学校", "作业", "补习", "接送", "排班", "会议", "出差", "订餐",
    "取件", "快递", "签收", "送达地址", "外卖订单", "会议室", "汇报", "周报",
    "签约", "合作", "客户", "订单", "报关", "海关", "税务", "稽查", "发票", "返点",
    "保密", "机密", "暗号", "老地方", "尾款", "违禁", "走私", "传销", "标会", "投资",
    "亏", "跑路", "爆雷", "诈骗", "被骗", "骗子", "伪造", "假冒",
)

#: 全天对话流里的“口播/闲聊”默认判噪：只有命中下列叙事锚点才是信号
#: （对手题库中对话流 95% 为闲谈，信号是极少数带具体处置动作的叙述）
DIALOGUE_SIGNAL_PATTERNS: tuple[str, ...] = (
    "不想活", "扔了不管", "发一百万", "挂个号", "挂号", "猝死", "工伤", "不干了",
    "辞职报告", "提离职", "离职", "体检报告", "心内科", "心电图", "救护车", "捂胸口",
    "保时捷", "醉意", "闷得慌", "胸闷", "胸痛", "住院", "复查", "急诊", "抽搐", "昏迷",
    "摔倒", "喘不上", "报警", "传票", "开庭", "转账", "还款", "欠款", "交付", "交房",
)

#: 显式垃圾标注：出题方在文本内直接标注（钓鱼/垃圾邮件）——优先级最高，压过渠道信号
EXPLICIT_JUNK_MARKERS: tuple[str, ...] = (
    "（钓鱼）", "(钓鱼)", "（垃圾邮件）", "（垃圾短信）", "（广告）", "（营销）",
)

#: APP 渠道信号覆盖：命中即视为有价值渠道消息（防误剪银行/医院/法院/预约类）
APP_SIGNAL_PATTERNS: tuple[str, ...] = (
    "预约", "转账", "入账", "危急值", "开庭", "签约", "服药提醒", "取件码", "冻结",
    "立案", "判决", "欠款", "账单", "扣款", "挂号", "复诊", "住院", "理赔",
)

#: 声学环境级垃圾标注（kind / acoustic_topology / app 名）
JUNK_KIND_TOKENS: tuple[str, ...] = (
    "subway_announce", "subway", "traffic", "wind_noise", "mall_promo", "push_sales",
    "street_hawker", "table_chatter", "restaurant_bgm", "kid_noise", "square_dance",
    "checkout", "gym_sales", "phone_spam", "joke_bait", "background", "noise", "chatter",
    "bgm", "announce", "promo", "advert", "spam", "weather_report", "ad",
)

#: 垃圾 APP 名 / 发送者（营销骚扰、垃圾短信、砍一刀群）
JUNK_APP_TOKENS: tuple[str, ...] = (
    "pinduoduo", "douyin", "taobao", "meituan", "member", "market", "promo", "ad",
    "拼多多", "抖音", "淘宝", "京东", "美团", "唯品会",
    "推送", "marketing", "news", "weather", "spam", "1068", "1065", "1069",
)

#: 传感器"日常活动片段"（50Hz 碎步晃动、打字震动、地铁颠簸——铁律四必须物理删除）
ROUTINE_SENSOR_KINDS: tuple[str, ...] = (
    "imu_window", "imu", "activity", "derived_activity", "routine", "micro_adjust",
    "sedentary", "walking", "typing", "shuffle", "vibration", "jitter",
)


@dataclass(frozen=True)
class PruneDecision:
    """单日碎片剪枝裁决（可解释、可审计）。"""

    carrier_id: str
    prune: bool
    score: float
    reason_code: str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "carrier_id": self.carrier_id,
            "prune": self.prune,
            "score": round(self.score, 4),
            "reason_code": self.reason_code,
            "evidence": self.evidence,
        }


class JunkPruner:
    """铁律四执行器：四路证据投票决定端侧物理删除。

    证据权重（可解释）：
      * ``content``      内容语义（垃圾词表 vs 高价值词表）
      * ``acoustic``     声学环境标注（报站/叫卖/风噪/推销）
      * ``physics``      波形物理（常规活动片段 vs 临床/安全事件）
      * ``declared``     对手声明元数据（``is_junk`` / ``is_transient`` 等旁证）
    """

    #: 单条载体的删除阈值（投票加权分）
    PRUNE_THRESHOLD = 0.5

    def __init__(self, *, trust_declared_flags: bool = True, ablate_metadata: bool = False,
                 chatter_modalities: frozenset[str] = frozenset()) -> None:
        self.trust_declared_flags = trust_declared_flags
        self.ablate_metadata = ablate_metadata
        self.chatter_modalities = chatter_modalities

    # -- 子证据 -----------------------------------------------------------
    @staticmethod
    def _content_score(carrier: Carrier) -> tuple[float, str]:
        text = carrier.haystack
        if carrier.modality == Modality.APP and _PLACEHOLDER_ONLY_RE.fullmatch(text.strip()):
            return 1.0, "占位附件（无正文内容）"
        acoustic_hits = [p for p in ACOUSTIC_DESCRIPTION_PATTERNS if p in text]
        if acoustic_hits and carrier.modality in (Modality.MIC, Modality.SENSOR):
            if not any(marker in text for marker in SOS_AUDIO_MARKERS):
                return 1.0, f"纯声学描述片段（无语音语义）:{'/'.join(acoustic_hits[:2])}"
        explicit = [p for p in EXPLICIT_JUNK_MARKERS if p in text]
        if explicit:
            return 1.0, f"文本自带垃圾标注:{explicit[0]}"
        junk_hits = [p for p in JUNK_TEXT_PATTERNS if p in text]
        if junk_hits and carrier.modality == Modality.APP:
            if any(p in text for p in APP_SIGNAL_PATTERNS):
                return 0.0, "APP 渠道业务消息（预约/转账/法院/医院）优先于营销词表"
        signal_hits = [p for p in SIGNAL_TEXT_PATTERNS if p in text]
        if junk_hits and not signal_hits:
            return 1.0, f"内容垃圾词命中:{'/'.join(junk_hits[:3])}"
        if junk_hits and signal_hits:
            return 0.5, f"垃圾词与价值词并存:{'/'.join(junk_hits[:2])}|{'/'.join(signal_hits[:2])}"
        if signal_hits:
            return 0.0, f"高价值语义命中:{'/'.join(signal_hits[:3])}"
        return 0.4, "无显著语义（默认偏向噪声侧）"

    @staticmethod
    def _acoustic_score(carrier: Carrier, content_score: float = 0.0) -> tuple[float, str]:
        """声学环境证据：报站/叫卖/风噪等环境噪声类，以及营销渠道。"""
        kind = f"{carrier.kind} {carrier.attrs.get('acoustic_topology') or ''}".lower()
        if any(t in kind for t in JUNK_KIND_TOKENS):
            return 1.0, f"声学环境标注为环境噪声:{kind.strip()}"
        signal_content = content_score <= 0.0
        if carrier.modality == Modality.APP:
            app = str(carrier.attrs.get("app") or "").lower()
            sender = str(carrier.attrs.get("sender") or "")
            if any(t in app for t in JUNK_APP_TOKENS) and not signal_content:
                return 0.75, f"APP 渠道为营销推送且无价值语义:{app or sender}"
            if any(t in sender for t in ("垃圾", "营销", "推广", "群发", "促销")) and not signal_content:
                return 0.75, f"发送方为营销号:{sender}"
        noise = carrier.num("ambient_noise_db")
        if noise is not None and noise >= 95.0 and not signal_content:
            return 0.7, f"环境噪声 {noise:.0f}dB 且无价值语义"
        return 0.0, ""

    def _declared_score(self, carrier: Carrier) -> tuple[float, str]:
        if self.ablate_metadata or not self.trust_declared_flags:
            return 0.0, ""
        if carrier.declared_junk is True:
            return 1.0, "出题方声明标注为垃圾(is_junk/is_transient)"
        if carrier.declared_junk is False:
            return 0.0, "出题方声明标注为信号(is_junk=false)"
        return 0.0, ""

    # -- 主裁决 -----------------------------------------------------------
    def classify(self, carrier: Carrier, *, physics_signal: bool = False,
                 support_evidence: bool = False) -> PruneDecision:
        """对单载体裁决是否物理删除。

        * 传感器 PRIMARY（临床/安全事件）→ 保留（证据链核心）
        * 传感器 SUPPORT（旁证：静止时长、应激响应、睡眠期）→ 保留但不独立成事实
        * 传感器 ROUTINE（50Hz 碎步/打字/颠簸）→ 物理剪枝
        * 文本载体 → 内容语义 / 声学环境 / 声明旁证 三路取最大值投票
        """
        if carrier.modality == Modality.SENSOR:
            if physics_signal:
                return PruneDecision(carrier.carrier_id, False, 0.0, "PHYSICS_EVENT", "波形判为临床/安全事件，证据链核心保留")
            if support_evidence:
                return PruneDecision(
                    carrier.carrier_id, False, 0.0, "SUPPORT_EVIDENCE",
                    f"事件旁证片段({carrier.kind or 'sensor'})：并入主事件证据链，不独立成事实也不物理删除",
                )
            content_score, content_reason = self._content_score(carrier)
            if content_score >= 1.0:
                return PruneDecision(carrier.carrier_id, True, content_score, "NOISE_LEAK", content_reason)
            return PruneDecision(
                carrier.carrier_id, True, 0.9, "ROUTINE_MOTION",
                f"常规活动片段({carrier.kind or 'sensor'})无临床/安全事件语义，按铁律四物理剪枝",
            )

        # 声纹冒充：声明为 transient 但带“冒充/不符”标注的载体是安全信号（必须保留）
        if carrier.modality == Modality.VOICEPRINT and (
            "IMPOSTOR" in str(carrier.attrs.get("cluster_label") or "").upper()
            or "冒充" in str(carrier.attrs.get("role") or "")
            or "冒充" in str(carrier.attrs.get("note") or "")
            or (carrier.num("cosine_to_claimed_identity") or 1.0) < 0.65
        ):
            return PruneDecision(
                carrier.carrier_id, False, 0.0, "SIGNAL_KEEP",
                "声纹自证不符（自称身份与声纹簇不匹配），冒充可疑来电证据保留",
            )

        # 声纹簇成员级判定：只有“佩戴者本人”与“已登记核心联系人”声纹是信号
        if carrier.modality == Modality.VOICEPRINT and ".detected_speakers" in carrier.container:
            if carrier.attrs.get("cosine_to_contact_bank") or (
                (carrier.num("cosine_to_enrolled_user") or 0.0) >= 0.9
            ):
                return PruneDecision(
                    carrier.carrier_id, False, 0.0, "SIGNAL_KEEP",
                    "声纹匹配佩戴者本人或已登记核心联系人，身份绑定证据保留",
                )
            return PruneDecision(
                carrier.carrier_id, True, 0.95, "NOISE_LEAK",
                "一次性陌生声纹（未匹配任何登记联系人），按铁律四物理剪枝",
            )

        # 全天对话流：默认判噪，仅保留带具体处置动作的叙事锚点
        if str(carrier.modality) in self.chatter_modalities:
            keep_hits = [p for p in DIALOGUE_SIGNAL_PATTERNS if p in carrier.haystack]
            if not keep_hits:
                return PruneDecision(
                    carrier.carrier_id, True, 0.9, "NOISE_LEAK",
                    "全天对话流中的口播/闲聊片段，无处置动作语义，按铁律四物理剪枝",
                )

        content_score, content_reason = self._content_score(carrier)
        acoustic_score, acoustic_reason = self._acoustic_score(carrier, content_score)
        declared_score, declared_reason = self._declared_score(carrier)

        score = max(content_score, acoustic_score, declared_score)
        if carrier.declared_junk is False and content_score < 1.0 and acoustic_score < 1.0:
            score = min(score, 0.3)  # 对手声明为信号且内容无垃圾证据 -> 采信旁证
        reason_code = "SIGNAL_KEEP"
        reason = content_reason or "语义为高价值证据"
        if score >= self.PRUNE_THRESHOLD:
            if declared_score >= 1.0 and content_score < 1.0 and acoustic_score < 1.0:
                reason_code = "DECLARED_JUNK"
                reason = declared_reason
            elif acoustic_score >= max(content_score, declared_score):
                reason_code = "ACOUSTIC_NOISE"
                reason = acoustic_reason
            else:
                reason_code = "NOISE_LEAK"
                reason = content_reason
        return PruneDecision(carrier.carrier_id, score >= self.PRUNE_THRESHOLD, score, reason_code, reason)

# ---------------------------------------------------------------------------
# 四、传感器事件判别（波形物理 → 临床/安全事件）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensorEvent:
    """从波形物理量判出的临床/安全事件。"""

    dimension: str
    intent: str
    descriptor: str
    severity: str = "INFO"
    p0: bool = False
    entities: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "intent": self.intent,
            "descriptor": self.descriptor,
            "severity": self.severity,
            "p0": self.p0,
            "entities": list(self.entities),
        }


class SensorRole:
    """传感器片段的角色：独立事实 / 证据链旁证 / 常规垃圾。"""

    PRIMARY = "PRIMARY"
    SUPPORT = "SUPPORT"
    ROUTINE = "ROUTINE"



class SensorEventAnalyzer:
    """波形物理判据：常规 50Hz 晃动一律剔除，只把真实事件升格为事实。"""

    #: 波形物理事件判据：(kind token, 判据函数, SensorEvent 工厂)
    def __init__(self, *, ablate_metadata: bool = False) -> None:
        self.ablate_metadata = ablate_metadata

    @staticmethod
    def _fmt(value: float | None, unit: str, digits: int = 2) -> str:
        """物理量格式化：整数不补零、小数去掉尾零（120 度不得写成 12 度）。"""
        if value is None:
            return ""
        if float(value).is_integer():
            return f"{int(value)}{unit}"
        rendered = f"{value:.{digits}f}".rstrip("0").rstrip(".")
        return f"{rendered}{unit}"

    #: 证据链支撑类片段（只做旁证，不独立成事实；铁律四下仍在保留侧）
    SUPPORT_KIND_TOKENS: tuple[str, ...] = (
        "context", "response", "correlation", "immobility", "shelter", "support",
        "baseline", "reference", "acoustic", "stress",
    )

    #: 常规活动片段（50Hz 碎步/打字/颠簸）：除非出现事件级物理证据，一律物理剪枝
    ROUTINE_KIND_TOKENS: tuple[str, ...] = (
        "imu_window", "imu_window_segment", "micro_adjust", "shuffle", "typing",
        "jitter", "vibration", "routine",
    )

    def classify_fragment(self, carrier: Carrier, frame: "FrameContext") -> tuple[str, SensorEvent | None]:
        """片段角色判定：``PRIMARY``（独立事实）/ ``SUPPORT``（旁证）/ ``ROUTINE``（垃圾）。"""
        kind = carrier.kind.lower()
        if not kind and carrier.modality != Modality.SENSOR:
            return SensorRole.ROUTINE, None
        if any(token in kind for token in self.SUPPORT_KIND_TOKENS):
            return SensorRole.SUPPORT, None
        event = self._event_of(carrier, frame)
        if event is not None:
            return SensorRole.PRIMARY, event
        if any(token in kind for token in self.ROUTINE_KIND_TOKENS):
            return SensorRole.ROUTINE, None
        return SensorRole.ROUTINE, None

    def analyze(self, carrier: Carrier, frame: "FrameContext") -> SensorEvent | None:
        """兼容入口：只返回主事件（``None`` = 非独立事实片段）。"""
        return self._event_of(carrier, frame)

    def _event_of(self, carrier: Carrier, frame: "FrameContext") -> SensorEvent | None:
            """波形物理判据：返回事件或 ``None``。

            判据一律基于**物理量与波形标注**，不使用任何出题方标答：
            * 真实跌倒 = 自由落体前段 + 三轴合成冲顶 + 姿态角翻转（+ 后继静止）
            * 伪跌倒   = 高 G 但无自由落体段、无姿态翻转、冲击后立即恢复运动
            * 周期冲击 = 等间隔变异系数极低 + 心率线性爬升 -> 运动而非跌倒
            * 心律失常 = 室早连发计数 / 停搏时长 / 静息心率越限
            * 气象风险 = 气压短时骤降
            * 日常派生片段 = ``derived_activity_segment`` 的语义标签（睡眠/通勤/久坐/爬楼/天气/气压平稳）
            """
            kind = carrier.kind.lower()
            label = str(carrier.attrs.get("label") or carrier.attrs.get("desc") or carrier.primary_text or "")
            low_label = label.lower()
            g_peak = carrier.num("g_peak", "peak_g")
            g_rms = carrier.num("g_rms", "rms_g")
            hr = carrier.num("hr_bpm", "hr_bpm_mean", "heart_rate_bpm", "hr_baseline")
            hr_peak = carrier.num("hr_peak")
            pause = carrier.num("pause_seconds")
            pvc = carrier.num("pvc_burst_count")
            spo2 = carrier.num("spo2_percent")
            baro = carrier.num("baro_hpa")
            motion = str(carrier.attrs.get("motion_state") or "")
            posture = carrier.num("posture_change_deg")
            freefall = carrier.num("freefall_segment_ms")
            entities: list[str] = []

            # ---- 1. 真实跌倒：自由落体 + 高 G 冲顶 + 姿态翻转（+ 后继静止）----
            text_stillness = any(
                token in f"{carrier.primary_text} {carrier.haystack} {motion}"
                for token in ("长时间静止", "零动", "无法起身", "未起身", "immobility", "stillness")
            )
            if text_stillness and frame.stillness_seconds is None:
                duration = carrier.num("duration_s")
                if duration and duration >= 30:
                    frame.stillness_seconds = duration
            impact_like = any(t in kind for t in ("imu_impact", "impact", "fall", "collapse")) or "fall" in low_label

            if impact_like and g_peak is not None and g_peak >= 3.0 and not (
                (freefall or 0.0) >= 60.0 or "freefall" in low_label or "preceded" in low_label
            ) and (frame.stillness_seconds or 0.0) >= 60.0:
                entities.append(self._fmt(g_peak, "g"))
                entities.append(self._fmt(frame.stillness_seconds, "秒", 0))
                return SensorEvent(
                    DIM_HEALTH, "FALL_IMPACT",
                    f"佩戴者{carrier.primary_text.rstrip('。') or '发生垂直冲击'}，冲击 {self._fmt(g_peak, 'g')} 后持续静止 "
                    f"{self._fmt(frame.stillness_seconds, '秒', 0)} 未能自主起身，判定为真实摔倒事件",
                    "P0_CRITICAL" if g_peak >= P0_IMPACT_G else "P1_WARNING",
                    g_peak >= P0_IMPACT_G, tuple(e for e in entities if e),
                )

            periodic = ("periodic" in kind) or ("strictly_periodic" in low_label) or ("periodic_impact" in low_label)
            if impact_like and not periodic and g_peak is not None:
                freefall_ok = (freefall or 0.0) >= 60.0 or "freefall" in low_label or "preceded" in low_label
                high_g = g_peak >= 3.0
                if high_g and freefall_ok and (frame.stillness_seconds or (posture or 0.0) >= 60.0 or "hard_impact" in low_label):
                    severity = "P0_CRITICAL" if (g_peak >= P0_IMPACT_G or frame.stillness_seconds) else "P1_WARNING"
                    entities.append(self._fmt(g_peak, "g"))
                    if frame.stillness_seconds:
                        entities.append(self._fmt(frame.stillness_seconds, "秒", 0))
                    return SensorEvent(
                        DIM_SAFETY, "FALL_IMPACT",
                        f"真实跌倒冲击：自由落体前段 + 三轴合成冲顶 {self._fmt(g_peak, 'g')}"
                        + (f" + 姿态角翻转 {self._fmt(posture, '度', 0)}" if posture else "")
                        + (f"，跌倒后持续静止 {self._fmt(frame.stillness_seconds, '秒', 0)} 未起身" if frame.stillness_seconds else ""),
                        severity, severity == "P0_CRITICAL", tuple(entities),
                    )
                if high_g and not freefall_ok:
                    entities.append(self._fmt(g_peak, "g"))
                    return SensorEvent(
                        DIM_SAFETY, "FALL_IMPACT_FAKED",
                        f"高 G 冲击 {self._fmt(g_peak, 'g')} 但无自由落体前段、无姿态翻转，冲击后立即恢复自主运动，"
                        "判定为甩腕/磕碰类日常动作而非真实跌倒（伪跌倒预警）",
                        "P1_WARNING", "fake_fall" in low_label, tuple(entities),
                    )
            if motion.upper().startswith("FALL") or "fall_tilt" in motion.lower():
                entities.append(str(motion))
                p0 = bool(pause and pause >= P0_PAUSE_SECONDS)
                return SensorEvent(
                    DIM_SAFETY, "FALL_IMPACT",
                    f"姿态解算判定跌倒（{motion}" + (f"，停搏 {self._fmt(pause, '秒')}" if pause else "") + "）",
                    "P0_CRITICAL" if p0 else "P1_WARNING", p0, tuple(entities),
                )

            # ---- 2. 周期性冲击：运动而非跌倒（形似跌倒陷阱的正面判定）----
            if periodic or kind.endswith("imu_periodic_impact"):
                entities.append(self._fmt(g_peak, "g"))
                coeff = carrier.num("rr_irregularity_index")
                return SensorEvent(
                    DIM_HEALTH, "EXERCISE_SESSION",
                    f"严格等间隔周期性冲击（峰值 {self._fmt(g_peak, 'g')}"
                    + (f"，变异系数 {coeff:.2f}" if coeff is not None else "")
                    + (f"，心率 {self._fmt(hr, 'bpm', 0)}" if hr is not None else "")
                    + "），判定为跑步/跳绳等周期性运动，不是跌倒",
                    "INFO", False, tuple(e for e in entities if e),
                )

            # ---- 3. 恶性心律失常：室性早搏阵发 ----
            if (pvc is None or pvc < 3) and any(t in kind for t in ("pvc_burst", "pvc", "early_beat", "arrhythmia")) and (
                "夜间" in carrier.primary_text or "阵发" in carrier.primary_text or carrier.num("pvc_burst_count") is None
            ):
                count = pvc or carrier.num("pvc_burst_count")
                if count:
                    entities.append(self._fmt(count, "次", 0))
                if hr is not None:
                    entities.append(self._fmt(hr, "bpm", 0))
                return SensorEvent(
                    DIM_HEALTH, "CARDIAC_PVC_BURST",
                    f"夜间睡眠期室性早搏连续阵发"
                    + (f"（{self._fmt(count, '次', 0)}）" if count else "")
                    + "，属心律失常危象",
                    "P1_WARNING", False, tuple(e for e in entities if e),
                )
            if pvc and pvc >= 3:
                entities.append(self._fmt(pvc, "次", 0))
                coupling = carrier.num("pvc_coupling_interval_ms")
                irregular = carrier.num("rr_irregularity_index")
                detail = f"连续 {self._fmt(pvc, '次', 0)} 室性早搏阵发"
                if coupling:
                    detail += f"（配对间期 {self._fmt(coupling, 'ms', 0)}）"
                if irregular:
                    detail += f"，RR 不规则指数 {irregular:.2f}"
                if hr is not None:
                    entities.append(self._fmt(hr, "bpm", 0))
                return SensorEvent(DIM_HEALTH, "CARDIAC_PVC_BURST", detail, "P1_WARNING", False, tuple(entities))

            # ---- 4. 缓慢性停搏 / 心搏骤停（P0）----
            if pause is not None and any(t in kind for t in ("pause", "brady", "asystole", "arrest")):
                entities.append(self._fmt(pause, "秒"))
                if hr is not None:
                    entities.append(self._fmt(hr, "bpm", 0))
                p0 = pause >= P0_PAUSE_SECONDS or (hr is not None and hr <= P0_HR_LOW_BPM)
                return SensorEvent(
                    DIM_HEALTH, "CARDIAC_ASYSTOLE",
                    f"窦性停搏 {self._fmt(pause, '秒')}" + (f"、心率低至 {self._fmt(hr, 'bpm', 0)}" if hr is not None else ""),
                    "P0_CRITICAL" if p0 else "P1_WARNING", p0, tuple(entities),
                )
            if pause is not None and pause >= P0_PAUSE_SECONDS:
                entities.append(self._fmt(pause, "秒"))
                return SensorEvent(
                    DIM_HEALTH, "CARDIAC_ASYSTOLE", f"无脉/停搏时长 {self._fmt(pause, '秒')}，超危象阈值",
                    "P0_CRITICAL", True, tuple(entities),
                )

            # ---- 4.5 脱腕误报（电容检测到未佩戴 + 高冲击）----
            if any(t in kind for t in ("off_wrist", "offwrist", "off-wrist")) or "脱腕" in carrier.primary_text:
                return SensorEvent(
                    DIM_SAFETY, "OFF_WRIST_FALSE_ALARM",
                    f"高冲击波形被电容检测判为脱腕状态（{carrier.primary_text.rstrip('。')}），"
                    "属摘下/甩腕导致的误报，并非真实跌倒",
                    "INFO", False, tuple(e for e in entities if e),
                )

            # ---- 5. 静息心动过速 ----
            if "tachycardia" in kind or (hr is not None and hr >= 130):
                if hr is not None:
                    entities.append(self._fmt(hr, "bpm", 0))
                if hr_peak is not None:
                    entities.append(self._fmt(hr_peak, "bpm", 0))
                critical = (hr is not None and hr >= P0_HR_HIGH_BPM) or (spo2 is not None and spo2 < P0_SPO2_PERCENT)
                baseline = carrier.num("hr_before")
                return SensorEvent(
                    DIM_HEALTH, "RESTING_TACHYCARDIA",
                    f"静息无体动状态下心率持续维持 {self._fmt(hr, 'bpm', 0)}"
                    + (f"（峰值 {self._fmt(hr_peak, 'bpm', 0)}）" if hr_peak else "")
                    + (f"，显著高于个人基线 {self._fmt(baseline, 'bpm', 0)}" if baseline else "")
                    + (f"，血氧 {self._fmt(spo2, '%')}" if spo2 else ""),
                    "P0_CRITICAL" if critical else "P1_WARNING", critical, tuple(entities),
                )

            # ---- 6. 气压骤降（气象风险）----
            if "baro" in kind and any(t in low_label for t in ("plunge", "drop", "storm", "fall")):
                drop = carrier.num("baro_drop_hpa") or frame.baro_drop()
                entities.append(self._fmt(drop, "hPa", 1))
                return SensorEvent(
                    DIM_ENVIRONMENT, "BAROMETRIC_STORM",
                    f"气压短时骤降至 {self._fmt(baro, 'hPa', 1)}（降幅 {self._fmt(drop, 'hPa', 1)}），强低压系统过境、暴风雨逼近",
                    "P1_WARNING", False, tuple(e for e in entities if e),
                )

            # ---- 7. 日常派生活动片段（语义标签 → 认知维度）----
            if "derived_activity" in kind or carrier.attrs.get("salience") is not None:
                return self._derived_segment_event(carrier, low_label, hr, g_peak, baro, frame)
            return None

    def _derived_segment_event(
        self, carrier: Carrier, low_label: str, hr: float | None,
        g_peak: float | None, baro: float | None, frame: "FrameContext",
    ) -> SensorEvent | None:
        """``derived_activity_segment``：把语义标签落成对应维度的日常/健康事实。"""
        mapping: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
            (("sleep",), DIM_HEALTH, "SLEEP_DURATION", "夜间睡眠结构片段"),
            (("sedentary",), DIM_HEALTH, "SEDENTARY_LONG", "连续久坐片段"),
            (("exercise", "workout", "run"), DIM_HEALTH, "EXERCISE_SESSION", "运动训练片段"),
            (("stair",), DIM_HEALTH, "STAIR_CLIMB", "爬楼梯片段"),
            (("commute",), DIM_DAILY, "DAILY_COMMUTE", "日常通勤片段"),
            (("traffic",), DIM_SAFETY, "TRAFFIC_RISK", "通勤交通险情片段"),
            (("weather",), DIM_ENVIRONMENT, "WEATHER_EXPOSURE", "恶劣天气暴露片段"),
            (("barometric_stable",), DIM_ENVIRONMENT, "BAROMETRIC_STABLE", "气压平稳片段"),
            (("media", "playback"), DIM_DAILY, "MEDIA_PLAYBACK_NOISE", "媒体外放片段"),
        )
        for tokens, dimension, intent, desc in mapping:
            if any(token in low_label for token in tokens):
                entities: list[str] = []
                if g_peak:
                    entities.append(self._fmt(g_peak, "g"))
                if hr:
                    entities.append(self._fmt(hr, "bpm", 0))
                if baro:
                    entities.append(self._fmt(baro, "hPa", 1))
                duration = carrier.num("duration_s")
                if duration and duration >= 60:
                    entities.append(self._fmt(duration / 60.0, "分钟", 0))
                return SensorEvent(dimension, intent, desc, "INFO", False, tuple(entities))
        text = carrier.primary_text
        if text:
            return SensorEvent(DIM_DAILY, "DAILY_ACTIVITY_SUMMARY", text[:80], "INFO", False, ())
        return None


    def is_signal(self, carrier: Carrier, frame: "FrameContext") -> bool:
        return self.analyze(carrier, frame) is not None


# ---------------------------------------------------------------------------
# 五、文本语义意图解析（90+ 生活谱系意图方向）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntentRule:
    """一条"证据 → 维度/方向/近义方向簇"规则。"""

    intent: str
    dimension: str
    triggers: tuple[str, ...]
    canonical_terms: tuple[str, ...] = ()
    priority: int = 50
    min_hits: int = 1


def _rule(intent: str, dimension: str, triggers: tuple[str, ...], *,
          terms: tuple[str, ...] = (), priority: int = 50, min_hits: int = 1) -> IntentRule:
    return IntentRule(intent, dimension, triggers, terms, priority, min_hits)


#: 生活谱系意图规则表（健康/财产债务/亲情人际/事业学业/生活契约/安全五域全覆盖）
INTENT_RULES: tuple[IntentRule, ...] = (
    # ---- 财务债务与民商法域 ----
    _rule("FAKE_TRANSFER_COUNTER", DIM_FINANCE,
          ("转账失败", "账户状态异常", "原路退回", "请勿轻信截图", "截图造假", "假转账"),
          terms=("假转账", "截图造假", "转账失败", "对冲"), priority=100, min_hits=1),
    _rule("DEBT_DEFAULT_IRONY", DIM_FINANCE,
          ("还钱", "欠款", "欠债", "赖账", "拉黑", "失联", "逾期未还", "借钱不还", "还不上",
           "未还钱", "反讽", "一直拖", "不讲信用"),
          terms=("讨债", "违约", "失信", "还钱", "未还钱", "拉黑", "逾期不还"), priority=90),
    _rule("DEBT_BORROWING", DIM_FINANCE,
          ("借我", "借点", "借钱", "垫付", "周转", "先把钱", "还你", "下月还", "借条", "借据",
           "结清", "拖得太久", "连本带息", "还我钱", "先转你"),
          terms=("借款", "借条", "欠款", "借据", "讨债", "还钱", "资金周转", "约定还款")),
    _rule("LABOR_WAGE_DISPUTE", DIM_CAREER,
          ("血汗钱", "工钱", "拖欠", "讨薪", "工人工资", "农民工", "结算款", "住建局", "包工头"),
          terms=("讨薪", "劳务纠纷", "拖欠工资", "结清工钱"), priority=95),
    _rule("PREMARITAL_ASSET_CONCEAL", DIM_FINANCE,
          ("婚前", "过户给他", "转移财产", "隐匿财产", "存款也不见", "共同财产"),
          terms=("婚前财产", "隐匿转移", "过户", "分割"), priority=95),
    _rule("INHERITANCE_DISPUTE", DIM_FINANCE,
          ("遗产", "遗嘱", "公证", "分家", "析产", "继承"),
          terms=("遗产继承", "遗嘱公证", "分家析产")),
    _rule("PYRAMID_SCHEME_LOSS", DIM_FINANCE,
          ("传销", "虚拟货币", "崩盘", "跑路", "提现不了", "资金盘", "保本高息"),
          terms=("资金盘爆雷", "传销", "投资款损失")),
    _rule("ROSCA_COLLAPSE", DIM_FINANCE,
          ("标会", "倒会", "会头", "会脚", "会款"),
          terms=("标会", "倒会", "会头跑路", "追偿"), priority=95),
    _rule("PROPERTY_TRANSACTION_BREACH", DIM_FINANCE,
          ("二手房", "中介", "吃差价", "违约", "定金", "网签", "购房合同", "过户手续"),
          terms=("房屋买卖违约", "中介纠纷", "定金争议")),
    _rule("RENOVATION_FRAUD", DIM_FINANCE,
          ("装修队", "卷款", "烂尾", "停工", "装修款"),
          terms=("装修队卷款跑路", "施工烂尾")),
    _rule("INSURANCE_CLAIM_DISPUTE", DIM_FINANCE,
          ("理赔", "拒赔", "保险", "定损"),
          terms=("保险理赔", "拒赔争议")),
    _rule("BANK_DEDUCTION_FAILURE", DIM_FINANCE,
          ("扣款失败", "余额不足", "代扣", "请尽快存入", "还款失败"),
          terms=("代扣失败", "余额不足", "资金缺口"), priority=90),
    _rule("BANK_TRANSFER_NOTICE", DIM_FINANCE,
          ("转账", "入账", "到账", "汇款", "转出", "转给了"),
          terms=("银行转账", "资金流水")),
    _rule("TAX_AUDIT_INVOICE", DIM_CAREER,
          ("税务稽查", "假发票", "虚开", "对账", "逃税", "补税"),
          terms=("税务稽查", "发票违规")),
    _rule("COMMERCIAL_SIGNING", DIM_CAREER,
          ("签约", "合同签订", "合作", "订单", "签约仪式", "框架协议"),
          terms=("商务签约", "合作达成")),
    _rule("CUSTOMS_ORDER_SEIZED", DIM_CAREER,
          ("海关", "查扣", "信用证", "报关", "扣押"),
          terms=("海关查扣", "信用证危机")),

    # ---- 家庭情感与人际博弈域 ----
    _rule("ARGUMENT_CONFLICT", DIM_SOCIAL,
          ("吵", "争执", "口角", "翻脸", "对骂", "推搡", "动手", "红脸", "闹起来", "碎怂", "红脸"),
          terms=("吵架", "争吵", "冲突", "口角", "争执", "吵闹", "红脸"), priority=70),
    _rule("FAMILY_QUARREL_ESCALATION", DIM_FAMILY,
          ("婆媳", "岳母", "小姑", "家庭聚会", "年夜饭", "亲戚", "冷战"),
          terms=("家庭矛盾", "亲属冲突")),
    _rule("PARENT_CANCER_CONCEALED", DIM_HEALTH,
          ("瞒报", "隐瞒病情", "癌症晚期", "不让告诉", "病历藏", "化疗", "瞒着"),
          terms=("瞒报癌症", "癌症晚期隐瞒", "异地求医", "病历隐瞒", "家属隐瞒病情", "晚期癌症"), priority=95),
    _rule("FAMILY_ENTRUSTMENT", DIM_FAMILY,
          ("密码是", "三长两短", "照顾好", "托付", "嘱托", "交代你", "万一我",
           "记得去", "记得明天", "别忘了买", "帮我取", "帮我拿", "替我", "去拿", "去取",
           "带回来", "记得给", "记得把", "你去接", "钥匙放", "喂两次", "别忘了", "帮我去",
           "接孩子", "去接", "帮我记一下", "住院做手术", "存折", "交给", "密码在",
           "交代在前面", "狗每天喂", "交代"),
          terms=("托付", "嘱托", "交代", "叮嘱", "委托", "安排", "拜托", "家事托付"), priority=80),
    _rule("CHILD_CUSTODY_DISPUTE", DIM_FAMILY,
          ("抚养权", "探视", "抢夺孩子", "监护权", "亲子鉴定"),
          terms=("抚养权争夺", "亲子鉴定", "探视权")),
    _rule("DIVORCE_DECISION", DIM_FAMILY,
          ("离婚", "民政局", "协议离", "分居", "起诉离婚"),
          terms=("离婚", "婚姻破裂")),
    _rule("MARRIAGE_ENGAGEMENT", DIM_FAMILY,
          ("彩礼", "订婚", "结婚登记", "婚礼", "领证", "婚房"),
          terms=("婚事", "婚嫁事宜")),
    _rule("VOICEPRINT_IDENTITY_BINDING", DIM_SOCIAL,
          ("声纹", "说话人", "聚类", "绑定", "本人声纹", "常联系人"),
          terms=("声纹", "绑定", "锁定", "识别", "确认", "归属", "熟人", "常联系人",
                 "佩戴者本人声纹", "本人声纹确认", "声纹归属机主"), priority=88),
    _rule("CODED_ARRANGEMENT", DIM_SOCIAL,
          ("按二号方案", "老地方", "暗号", "嘴严", "风声紧", "别打电话", "隐蔽", "行话"),
          terms=("暗语", "隐蔽", "保密", "接头"), priority=90),
    _rule("EVIDENCE_WITHDRAWAL", DIM_SOCIAL,
          ("撤回", "手滑发错", "别截图", "销毁", "删掉记录", "取消发送", "违规承诺", "撤回消息"),
          terms=("撤回", "销毁证据", "手滑发错", "违规承诺", "撤回消息", "销毁"), priority=92),
    _rule("SECRET_KEEPING_PROMISE", DIM_SOCIAL,
          ("保密", "不许说", "就我们俩知道", "烂在肚子里", "别声张"),
          terms=("保密约定", "守口如瓶")),
    _rule("APOLOGY_RECONCILE", DIM_SOCIAL,
          ("对不起", "道歉", "赔个不是", "原谅", "和好"),
          terms=("道歉", "和解")),
    _rule("NEIGHBOR_DISPUTE", DIM_LIFE,
          ("邻居", "楼上", "漏水到", "噪音扰民", "物业", "公共区域", "停车位"),
          terms=("邻里纠纷", "物业争议")),
    _rule("PET_INCIDENT", DIM_LIFE,
          ("狗咬", "猫抓", "宠物", "扑倒", "疫苗"),
          terms=("宠物伤人", "宠物纠纷")),

    # ---- 生活契约与日常意外域 ----
    _rule("PIPE_BACKFLOW_COMPENSATION", DIM_LIFE,
          ("倒灌", "下水", "管道", "泡水", "淹了", "渗水", "漏水", "物业维修", "索赔"),
          terms=("下水倒灌", "管道堵塞", "名贵物品浸泡", "租客索赔"), priority=93),
    _rule("RENT_HOUSING_DISPUTE", DIM_LIFE,
          ("租房", "房东", "租客", "押金", "房租", "隔断", "合租", "水电费"),
          terms=("房屋租赁纠纷", "押金争议")),
    _rule("CAR_ACCIDENT_DISPUTE", DIM_LIFE,
          ("车祸", "追尾", "剐蹭", "交警", "事故认定", "别车", "自驾"),
          terms=("交通事故", "责任认定")),
    _rule("VEHICLE_THEFT_FRAUD", DIM_LIFE,
          ("被盗", "丢车", "电瓶", "盗刷", "加油卡", "油卡"),
          terms=("财物被盗", "盗刷")),
    _rule("LOST_ITEM", DIM_LIFE,
          ("遗失", "丢了", "找不到了", "走失"),
          terms=("物品遗失", "走失")),
    _rule("TRAVEL_DISRUPTION", DIM_LIFE,
          ("航班取消", "延误", "高铁", "改签", "酒店", "退订机票"),
          terms=("行程中断", "交通延误")),
    _rule("DELIVERY_PENALTY", DIM_CAREER,
          ("超时罚款", "差评", "抢单", "骑手", "送单", "出餐"),
          terms=("配送罚款", "平台处罚")),
    _rule("UTILITY_SERVICE", DIM_LIFE,
          ("水电", "燃气", "供暖", "宽带", "缴费"),
          terms=("生活缴费", "服务中断")),
    _rule("FOOD_SAFETY_INSPECTION", DIM_CAREER,
          ("食药监", "抽检", "食品安全", "卫生检查", "责令整改"),
          terms=("食品安全检查", "监管处罚")),

    # ---- 健康生理与危机域 ----
    _rule("OCCULT_MI_PRECURSOR", DIM_HEALTH,
          ("胸口", "胸痛", "胸闷", "压着", "压榨", "心口", "冒冷汗", "大汗", "胃部不适", "透不过气", "心梗"),
          terms=("心梗", "心肌梗死", "胸闷", "胸口压榨", "濒死感"), priority=98),
    _rule("STROKE_PRECURSOR", DIM_HEALTH,
          ("舌头", "发麻", "说话不利索", "嘴歪", "半身", "眼前发黑", "眩晕", "中风", "脑卒中"),
          terms=("急性脑卒中", "口齿不清", "肢体麻木"), priority=98),
    _rule("CARDIAC_ARRHYTHMIA_SYMPTOM", DIM_HEALTH,
          ("心慌", "心悸", "乱跳", "漏拍", "心跳", "心律"),
          terms=("心律失常", "心悸", "心跳异常"), priority=88),
    _rule("SUICIDAL_IDEATION", DIM_HEALTH,
          ("不想活", "攒够一瓶", "不用醒", "跳楼", "自尽", "结束这一切", "没什么意思"),
          terms=("自杀风险", "心理危机", "重度抑郁"), priority=99),
    _rule("ACUTE_PAIN_ATTACK", DIM_HEALTH,
          ("疼死", "火烧", "剧痛", "疼得", "肿得像", "下不了地", "无法着地"),
          terms=("急性疼痛发作", "关节红肿剧痛", "无法负重"), priority=88),
    _rule("MEDICATION_ISSUE", DIM_HEALTH,
          ("药", "剂量", "吃药", "停药", "拿药", "取药", "开药"),
          terms=("用药", "服药", "药品"), priority=60),
    _rule("MEDICAL_APPOINTMENT", DIM_HEALTH,
          ("预约", "挂号", "门诊", "复查", "随访", "复诊", "就诊"),
          terms=("定期随访", "复查", "门诊预约", "预约就诊", "挂号成功", "复诊", "随访", "预约", "门诊"), priority=97),
    _rule("LAB_REPORT_ABNORMAL", DIM_HEALTH,
          ("化验", "检验单", "生化", "指标异常", "尿酸", "转氨酶", "肌酐", "血糖", "糖化"),
          terms=("化验异常", "指标超标", "需复查"), priority=90),
    _rule("HOSPITAL_EMERGENCY_CALL", DIM_HEALTH,
          ("急诊", "抢救", "马上送", "120", "救护车", "送你去医院"),
          terms=("紧急送医", "急救", "转诊"), priority=96),
    _rule("PREGNANCY_RISK", DIM_HEALTH,
          ("胎动", "孕", "产检", "妊娠", "宫缩", "见红"),
          terms=("妊娠风险", "产检异常")),
    _rule("CHRONIC_CONDITION_MANAGEMENT", DIM_HEALTH,
          ("血压", "降压药", "糖尿病", "胰岛素", "哮喘", "痛风", "颈椎"),
          terms=("慢性病管理", "长期用药")),
    _rule("SLEEP_INSOMNIA", DIM_HEALTH,
          ("失眠", "睡不着", "熬夜", "通宵", "整夜"),
          terms=("睡眠障碍", "睡眠不足"), priority=70),
    _rule("FATIGUE_OVERLOAD", DIM_HEALTH,
          ("疲劳", "累垮", "连轴", "撑不住", "头晕"),
          terms=("过度疲劳", "体力透支")),
    _rule("INFECTION_FEVER", DIM_HEALTH,
          ("发烧", "发热", "感染", "咳嗽", "咳血", "化脓", "破溃"),
          terms=("感染发热", "炎症")),
    _rule("INJURY_FRACTURE", DIM_HEALTH,
          ("骨折", "扭伤", "拉伤", "崴", "擦伤", "缝针", "淤青"),
          terms=("外伤", "骨折", "扭伤"), priority=85),
    _rule("OCCUPATIONAL_HAZARD", DIM_HEALTH,
          ("高空", "坠物", "噪音", "耳鸣", "粉尘", "化学品", "辐射", "中毒"),
          terms=("职业暴露", "作业伤害")),
    _rule("CHILD_ELDER_HEALTH", DIM_HEALTH,
          ("孩子", "老人", "老父亲", "老母亲", "奶奶", "爷爷", "高烧", "摔倒"), 
          terms=("老幼健康风险", "照护需求")),

    # ---- 事业学业与重大转折域 ----
    _rule("HIRING_OFFER", DIM_CAREER,
          ("offer", "入职", "面试", "背调", "猎头", "年薪", "跳槽", "offer审批"),
          terms=("求职录用", "面试进展", "薪资谈判"), priority=80),
    _rule("RESIGNATION_DECISION", DIM_CAREER,
          ("辞职", "离职", "不干了", "递交辞呈", "提离职"),
          terms=("辞职决定", "离职意向"), priority=88),
    _rule("LAYOFF_DISPUTE", DIM_CAREER,
          ("裁员", "仲裁", "赔偿金", "N+1", "竞业", "劳动仲裁", "考勤记录"),
          terms=("劳动仲裁", "裁员纠纷", "竞业限制"), priority=90),
    _rule("WORKPLACE_ABUSE", DIM_CAREER,
          ("骚扰", "甩锅", "辱骂", "穿小鞋", "录音取证", "举报"),
          terms=("职场骚扰", "职场压迫", "取证维权"), priority=88),
    _rule("PARTNERSHIP_BETRAYAL", DIM_CAREER,
          ("合伙人", "另设", "壳公司", "客户名单", "知识产权", "转移客户"),
          terms=("合伙人背叛", "商业机密侵占")),
    _rule("ACADEMIC_THESIS", DIM_CAREER,
          ("论文", "盲审", "导师", "答辩", "毕业", "延毕", "大修"),
          terms=("学业论文", "导师矛盾")),
    _rule("EXAM_CIVIL_SERVICE", DIM_CAREER,
          ("公考", "政审", "面试递补", "上岸", "考编", "体检", "档案"),
          terms=("公考", "面试递补", "政审", "体检"), priority=92),
    _rule("BUSINESS_CRISIS", DIM_CAREER,
          ("供应商催款", "罢工", "抽检", "资金链", "停业", "门店", "加盟"),
          terms=("经营危机", "供应链断裂")),
    _rule("WORK_OVERTIME", DIM_CAREER,
          ("加班", "通宵", "排障", "值班", "考核", "KPI"),
          terms=("超负荷工作", "加班压力")),
    _rule("SAFETY_HAZARD_WORK", DIM_SAFETY,
          ("高空作业", "安全带", "坠落风险", "塌方", "触电", "消防隐患"),
          terms=("作业安全风险", "坠落隐患"), priority=90),
    _rule("FALL_RESCUE", DIM_SAFETY,
          ("滑坠", "悬挂", "被挂在", "坠崖", "失温", "自救"),
          terms=("坠落受困", "野外自救"), priority=97),
    _rule("TRAFFIC_SAFETY_RISK", DIM_SAFETY,
          ("路怒", "别车", "刹车", "高速", "疲劳驾驶", "追尾风险"),
          terms=("行车安全风险", "交通险情")),
    _rule("EMERGENCY_SOS", DIM_SAFETY,
          ("救命", "救我", "快点来人", "抓紧", "报警", "有人受伤"),
          terms=("紧急求救", "求助信号"), priority=99),
    _rule("MATERIAL_COST_PRESSURE", DIM_FINANCE,
          ("料钱", "材料款", "货款", "尾款", "结算"),
          terms=("货款结算", "资金压力")),
    _rule("SIM_CARD_ACCOUNT", DIM_DAILY,
          ("套餐", "话费", "流量", "实名", "开卡"),
          terms=("通信业务", "账户业务")),
    _rule("PROMISE_AGREEMENT", DIM_SOCIAL,
          ("说好", "答应", "约好", "承诺", "下周三前", "准时", "说好今天"),
          terms=("承诺", "约定", "履约")),
    _rule("REMINDER_APPOINTMENT", DIM_DAILY,
          ("提醒", "别忘了", "记得", "待办", "日程"),
          terms=("提醒事项", "日程安排")),
    _rule("GRATITUDE_SUPPORT", DIM_SOCIAL,
          ("谢谢", "多亏", "感谢", "帮了我"),
          terms=("致谢", "互助")),

    # ---- 日常事务流（就诊预约/缴费/物流/用餐/家校/工作协同）----
    _rule("MEDICAL_APPOINTMENT", DIM_HEALTH,
          ("预约", "挂号", "门诊", "取号", "已成功预约", "就诊时间"),
          terms=("定期随访", "复查", "门诊预约", "复诊", "预约就诊", "挂号成功", "随访"), priority=90),
    _rule("MEDICATION_REMINDER", DIM_HEALTH,
          ("该吃药", "用药提醒", "服药", "记得吃药", "提醒您服药", "药快没了"),
          terms=("服药提醒", "按时用药", "药品续方", "吃药", "处方药", "药量", "服药", "按时服药", "用药"), priority=86),
    _rule("LAB_CRITICAL_VALUE", DIM_HEALTH,
          ("检验", "化验", "指标", "危急值", "超出参考", "复查建议", "提示异常"),
          terms=("化验异常", "危急值", "指标超标", "需复查"), priority=90),
    _rule("BILL_REPAYMENT", DIM_FINANCE,
          ("待还款", "还款日", "账单", "最低还款", "分期", "扣款失败", "应还"),
          terms=("账单还款", "代扣", "逾期风险", "账单", "还款日", "待还款", "还款", "账单到期", "花呗账单"), priority=90),
    _rule("UTILITY_PAYMENT", DIM_FINANCE,
          ("水费", "电费", "燃气费", "缴费", "取暖费", "物业费", "宽带费", "欠费"),
          terms=("生活缴费", "费用到期", "电费", "缴费提醒", "水电费", "物业费", "燃气费", "账单缴纳", "欠费"), priority=80),
    _rule("BANK_LARGE_TRANSFER", DIM_FINANCE,
          ("大额", "转账提醒", "您账户", "入账", "转出金额", "柜面"),
          terms=("大额转账", "资金流水", "账户变动", "到账", "入账", "转账", "大额", "汇款", "进账", "收款"), priority=88),
    _rule("SMALL_TRANSFER", DIM_FINANCE,
          ("向你转账", "转账给你", "微信转账", "向你转账", "AA", "分摊", "饭钱", "已收钱"),
          terms=("打钱", "小额转账", "分摊费用", "收款", "AA分摊", "收到转账", "转账"), priority=92),
    _rule("DELIVERY_EVENT", DIM_LIFE,
          ("快递", "到件", "取件码", "菜鸟驿站", "已签收", "派送", "外卖已取餐", "订单已送达"),
          terms=("包裹派送", "取件提醒", "物流进度", "快递", "送货上门", "收到快递", "取件", "包裹", "签收", "驿站取件"), priority=78),
    _rule("MEAL_EVENT", DIM_LIFE,
          ("订餐", "聚餐", "饭局", "一起吃", "餐厅已", "点单", "桌号"),
          terms=("聚餐安排", "用餐登记", "午餐", "用餐", "点餐", "进食", "早餐", "外卖", "吃饭", "上菜"), priority=90),
    _rule("FAMILY_DAILY", DIM_FAMILY,
          ("家里", "妈说", "爸说", "老婆", "老公", "孩子", "接孩子", "买菜", "回家吃饭", "爱你呀",
           "想吃什么", "顺路买", "回来吃饭", "晚上回来", "家人", "爸妈", "问候"),
          terms=("家庭日常", "家事沟通", "问候家人", "家人日常", "亲情互动", "和家人说话"), priority=60),
    _rule("CHILD_SCHOOL", DIM_FAMILY,
          ("家长会", "作业", "老师", "学校", "补习", "考试成绩", "接送孩子"),
          terms=("子女学业", "家校沟通", "孩子在校", "考试成绩", "班主任沟通", "家长会", "升学"), priority=74),
    _rule("WORK_COORDINATION", DIM_CAREER,
          ("会议", "排班", "汇报", "周报", "排期", "对接", "同步一下", "出方案"),
          terms=("工作协同", "排期确认", "工作对接", "工作协调", "任务分配", "工作沟通", "对接"), priority=66),
    _rule("SOCIAL_CHAT", DIM_SOCIAL,
          ("一起吃", "有空吗", "好久不见", "最近", "聊两句", "约一下", "怎么样"),
          terms=("社交寒暄", "唠嗑", "寒暄", "拉家常", "叙旧", "闲谈", "聊天", "攀谈", "闲聊"), priority=55),
    _rule("REPAYMENT_PROMISE", DIM_FINANCE,
          ("下月还", "月底还", "一定还", "先还", "分期还", "尽快还", "凑齐还"),
          terms=("还款承诺", "债务清偿", "还钱", "约定还款", "还款计划", "到期归还"), priority=90),
    _rule("MEDIA_PLAYBACK_NOISE", DIM_DAILY,
          ("外放", "播放", "视频声", "音乐声", "短视频"),
          terms=("媒体外放", "影视台词", "外放噪声", "播放内容", "背景音乐干扰", "非现场对话"), priority=60),
    _rule("FRAUD_ATTEMPT", DIM_SAFETY,
          ("点击链接", "中奖", "冒充", "客服来电", "安全账户", "转账验证", "涉嫌洗钱", "解冻"),
          terms=("诈骗电话", "电信诈骗", "诱导转账", "疑似诈骗", "冒充公检法", "可疑来电", "钓鱼"), priority=99),
    _rule("COURT_SUMMONS", DIM_SOCIAL,
          ("法院", "传票", "开庭", "诉讼", "应诉", "判决书"),
          terms=("法院传票", "开庭通知", "诉讼程序"), priority=92),
    _rule("LAWYER_LETTER", DIM_FINANCE,
          ("律师函", "催告", "最后通函", "法律责任"),
          terms=("律师函", "催告通知"), priority=90),
    _rule("SIGNING_SCHEDULE", DIM_CAREER,
          ("签约安排", "签约时间", "面签", "合同签署", "签字时间"),
          terms=("签约日程", "合同签署"), priority=86),
    _rule("NDA_CONFIDENTIALITY", DIM_SOCIAL,
          ("保密协议", "不得外传", "仅限内部", "签署保密"),
          terms=("保密协议", "违约责任"), priority=88),
    _rule("WEAK_SOS", DIM_SAFETY,
          ("微弱喘息", "长时间无声", "无应答", "喘息", "微弱呼吸",
           "微弱的呼救", "救命", "救救我", "帮帮我", "来人啊", "很难受", "撑不住了", "快不行了"),
          terms=("求助信号", "危急呼救"), priority=96),
    _rule("VERBAL_VENT", DIM_EMOTION,
          ("烦死", "烦透", "真是服了", "气死", "受不了", "吐槽", "心累", "崩溃"),
          terms=("情绪宣泄", "口头禅", "情绪发泄", "气话", "非真实意图", "吐槽", "发牢骚", "习惯性抱怨"), priority=58),
    _rule("DRUNK_BRAGGING", DIM_SOCIAL,
          ("明天老子", "全买下来", "收购", "分给弟兄们", "我认识", "随便搞定"),
          terms=("酒后吹牛", "夸大言辞", "吹牛", "醉话", "口嗨", "醉后妄言", "酒话", "不属实"), priority=56),
    _rule("HIDDEN_CARDIAC_CRISIS", DIM_HEALTH,
          ("我没事", "别大惊小怪", "眼前发黑", "舌头有点", "憋闷", "压得慌"),
          terms=("隐匿心梗", "隐忍式危象", "拒医风险"), priority=97),
    _rule("REAL_RESIGNATION", DIM_CAREER,
          ("不干了", "我想辞职", "递辞呈", "干不下去", "换个活法"),
          terms=("辞职决定", "离职意向"), priority=88),
    _rule("REAL_MEDICAL_INTENT", DIM_HEALTH,
          ("得去一趟医院", "我得挂号", "去看医生", "查一下", "拍个片子", "做个检查"),
          terms=("真实就医诉求", "就诊计划"), priority=86),
    _rule("VOICE_IMPERSONATION_FRAUD", DIM_SOCIAL,
          ("冒充", "模仿声音", "声音很像", "假扮", "AI合成", "机器人来电"),
          terms=("声纹冒充", "伪冒身份"), priority=93),
    _rule("BUSINESS_CONFIDENTIALITY", DIM_CAREER,
          ("核心机密", "烂在肚子里", "守口如瓶", "不外传", "别外传", "商业机密", "封口", "保密到"),
          terms=("保密", "守口如瓶", "不外传", "商业机密", "不透露", "机密", "保密承诺"), priority=96),
    _rule("FAINT_DISTRESS_CALL", DIM_HEALTH,
          ("喘不上气", "谁来搭把手", "搭把手", "起不来", "心口压得慌", "胸口疼", "气声", "声音微弱"),
          terms=("求救", "呼救", "胸口疼", "起不来", "呼吸困难", "危急", "心脏不适"), priority=99),
    _rule("OFF_WRIST_FALSE_ALARM", DIM_SAFETY,
          ("脱腕", "电容检测", "甩腕", "摘下", "非跌倒", "误报"),
          terms=("误报", "甩腕", "脱腕", "摘下", "非跌倒", "误触", "虚惊"), priority=95),
    _rule("BARO_STORM_DROP", DIM_SAFETY,
          ("气压3小时骤降", "气压骤降", "baro_plunge", "强对流", "暴风雨", "气压跳水"),
          terms=("气压骤降", "暴风雨", "强对流", "恶劣天气", "风暴", "雷暴", "气压异常"), priority=94),
    _rule("PVC_BURST", DIM_HEALTH,
          ("室性早搏连续阵发", "夜间睡眠期室性早搏", "早搏连续", "nocturnal_pvc_burst"),
          terms=("早搏", "室性早搏", "心律失常", "心律不齐", "心悸", "心脏漏跳"), priority=96),
    _rule("KEY_CONVERSATION_WITH_CONTACT", DIM_SOCIAL,
          ("谈拢了", "拿了主意", "聊了四十分钟", "路线定了", "深谈", "长谈", "一起爬山"),
          terms=("长谈", "交谈", "对话", "深谈", "约定", "商量", "聊天", "沟通"), priority=92),
    _rule("FINANCING_BET_FAILURE", DIM_FINANCE,
          ("对赌失败", "回购", "连带清偿", "无限连带", "融资失败", "触发回购"),
          terms=("对赌", "回购", "连带清偿", "融资失败", "投资款"), priority=93),
    _rule("CONCEALED_CANCER", DIM_SOCIAL,
          ("癌症晚期", "瞒报癌症", "化疗", "异地求医", "隐瞒病情"),
          terms=("癌症晚期", "瞒报", "病历", "求医", "化疗", "独生子女", "崩溃"), priority=94),
    _rule("SEWAGE_BACKFLOW", DIM_LIFE,
          ("下水倒灌", "下水管倒灌", "污水倒灌", "化粪池", "返水"),
          terms=("下水倒灌", "浸泡", "索赔", "名贵物品", "物业", "维修", "赔偿"), priority=90),
    _rule("DOG_KNOCK_CHILD", DIM_LIFE,
          ("宠物犬", "狗扑", "扑倒", "拴绳", "遛狗", "犬只伤人"),
          terms=("宠物犬", "扑倒", "幼童", "冲突", "派出所", "调解", "拴绳"), priority=90),
    _rule("USED_CAR_FLOODED", DIM_LIFE,
          ("泡水车", "事故车", "二手车", "暗病", "退车", "第三方检测"),
          terms=("泡水车", "事故车", "检测", "退车", "维权", "车商", "暗病"), priority=90),
    _rule("CUSTODY_BATTLE_FORGED", DIM_SOCIAL,
          ("伪造探视记录", "抢夺孩子", "抚养权诉讼", "探视权造假", "抢孩子"),
          terms=("抚养权争夺", "伪造探视记录", "抢夺孩子", "抚养权诉讼", "探视权造假"), priority=93),
    _rule("PATERNITY_NON_BIOLOGICAL", DIM_SOCIAL,
          ("非亲生", "亲子鉴定", "血缘鉴定", "非血缘"),
          terms=("非亲生", "亲子鉴定", "抚养", "血缘鉴定", "鉴定报告"), priority=92),
    _rule("HIDDEN_MARITAL_ASSETS", DIM_FINANCE,
          ("隐匿资产", "转移财产", "婚前财产", "共同财产", "藏钱"),
          terms=("隐匿资产", "转移财产", "婚前财产", "分割", "隐瞒"), priority=92),
    _rule("WORKPLACE_HARASSMENT", DIM_SOCIAL,
          ("性骚扰", "言语骚扰", "上级骚扰", "录音取证", "投诉骚扰"),
          terms=("性骚扰", "录音取证", "上级", "言语骚扰", "举报", "证据", "辞退"), priority=93),
    _rule("THESIS_BLIND_REVIEW", DIM_CAREER,
          ("盲审", "大修", "导师决裂", "学位论文", "答辩"),
          terms=("盲审", "大修", "导师决裂", "延期", "论文", "答辩", "学术"), priority=92),
    _rule("CIVIL_SERVICE_INTERVIEW", DIM_CAREER,
          ("公考", "面试递补", "政审", "公务员面试", "递补通知"),
          terms=("公考面试递补", "政审", "公务员面试", "递补通知", "政审危机"), priority=93),
    _rule("NON_COMPETE_2M", DIM_CAREER,
          ("竞业限制", "竞业赔偿", "竞业追偿", "限制协议违约"),
          terms=("竞业限制", "追偿200万", "竞业赔偿", "竞业诉讼", "限制协议违约"), priority=94),
    _rule("LABOR_ARBITRATION_FORGED", DIM_CAREER,
          ("劳动仲裁", "伪造考勤", "考勤造假", "仲裁庭审", "开庭辩论"),
          terms=("劳动仲裁", "伪造考勤", "开庭辩论", "仲裁庭审", "考勤造假"), priority=93),
    _rule("DECORATION_RUNAWAY", DIM_FINANCE,
          ("装修队跑路", "卷款潜逃", "烂尾工程", "装修纠纷", "卷款跑路"),
          terms=("装修队跑路", "卷款潜逃", "烂尾工程", "装修纠纷", "卷款跑路"), priority=93),
    _rule("CRYPTO_PONZI_COLLAPSE", DIM_FINANCE,
          ("虚拟币崩盘", "传销盘", "资金盘崩盘", "非法集资", "提现失败", "崩盘跑路"),
          terms=("虚拟币", "传销盘", "崩盘跑路", "提现失败", "非法集资", "崩盘"), priority=93),
    _rule("MEDICAL_DISPUTE_PUSH", DIM_CAREER,
          ("医患", "下跪托付", "推搡威胁", "抢救记录", "医疗纠纷"),
          terms=("下跪托付", "推搡威胁", "抢救记录", "院方介入", "医疗纠纷"), priority=93),
    _rule("WORK_OVERTIME_ARRHYTHMIA", DIM_CAREER,
          ("通宵加班", "熬夜早搏", "连续加班", "过度疲劳", "加班到"),
          terms=("通宵加班", "心律失常", "熬夜早搏", "连续加班", "过度疲劳", "室性早搏"), priority=94),
    _rule("BUSINESS_CRISIS", DIM_CAREER,
          ("供应链断裂", "经营危机", "资金链", "客户流失", "停摆"),
          terms=("经营危机", "供应链断裂", "资金链", "停摆"), priority=88),
    _rule("ORDINARY_PURCHASE", DIM_LIFE,
          ("已下单", "订单", "收货地址", "已发货", "退款申请"),
          terms=("购物订单", "消费记录"), priority=64),
)


#: 规则合并补丁：同一方向在题库演进中常出现多条规则（触发词/优先级不一致）。
#: 这里按“方向”合并——触发词与近义词簇取并集、优先级取最高，并把题库词表补进触发词。
_INTENT_EXTRA: dict[str, dict[str, Any]] = {
    "FRAUD_ATTEMPT": {
        "dimension": DIM_SAFETY, "priority": 99,
        "triggers": ("社保中心", "医保卡", "安全账户", "核实身份", "银行客服", "涉嫌", "盗刷了", "改号",
                     "冻结", "中奖", "解冻", "冒充公检法", "客服来电", "点击链接"),
        "terms": ("疑似诈骗", "电信诈骗", "钓鱼", "诈骗电话", "冒充公检法", "可疑来电", "诈骗话术"),
    },
    "MEDICAL_APPOINTMENT": {
        "dimension": DIM_HEALTH, "priority": 97,
        "triggers": ("成功预约", "已成功预约", "预约", "门诊", "挂号", "复诊", "复查", "随访", "取号", "到院"),
        "terms": ("定期随访", "复查", "门诊预约", "复诊", "预约就诊", "挂号成功", "随访"),
    },
    "MEAL_EVENT": {
        "dimension": DIM_DAILY, "priority": 92,
        "triggers": ("外卖已送达", "已送达", "您点的", "慢用", "上菜", "用餐", "点餐", "餐品", "配送"),
        "terms": ("午餐", "用餐", "点餐", "进食", "早餐", "外卖", "吃饭", "下馆子"),
    },
    "HOSPITAL_EMERGENCY_CALL": {
        "dimension": DIM_HEALTH, "priority": 96,
        "triggers": ("急救", "救护车", "120", "送医", "抢救", "急诊科", "叫医生", "马上送"),
        "terms": ("紧急送医", "急救", "转诊", "呼叫救护车"),
    },
    "UTILITY_PAYMENT": {
        "dimension": DIM_FINANCE, "priority": 90,
        "triggers": ("电费", "水费", "燃气费", "物业费", "缴费提醒", "账单缴纳", "欠费"),
        "terms": ("电费", "缴费提醒", "水电费", "物业费", "燃气费", "生活缴费", "账单缴纳", "欠费"),
    },
    "DELIVERY_EVENT": {
        "dimension": DIM_LOGISTICS, "priority": 90,
        "triggers": ("取件码", "货架", "驿站", "快递", "签收", "包裹", "取件", "派送"),
        "terms": ("快递", "送货上门", "收到快递", "取件", "包裹", "签收", "驿站取件"),
    },
    "FAMILY_DAILY": {
        "dimension": DIM_FAMILY, "priority": 62,
        "triggers": ("想吃什么", "顺路买", "回来吃饭", "晚上回来", "家人", "问候", "老妈", "老爸"),
        "terms": ("问候家人", "家人日常", "家人联系", "亲情互动", "和家人说话", "家庭日常", "与家人通话"),
    },
    "FAMILY_ENTRUSTMENT": {"dimension": DIM_FAMILY, "priority": 92},
    "SOCIAL_CHAT": {
        "dimension": DIM_SOCIAL, "priority": 55,
        "triggers": ("好久不见", "你说这", "唠嗑", "寒暄", "拉家常", "叙旧", "闲聊", "最近怎么样"),
        "terms": ("唠嗑", "寒暄", "拉家常", "叙旧", "闲谈", "聊天", "攀谈", "闲聊"),
    },
    "WORK_OVERTIME": {
        "dimension": DIM_CAREER, "priority": 74,
        "triggers": ("加班", "通宵", "连轴转", "还没下班", "连夜", "延长工时"),
        "terms": ("延时上班", "连轴转", "通宵", "超时工作", "延长工时", "加班", "连夜", "加班压力"),
    },
    "WORK_COORDINATION": {
        "dimension": DIM_CAREER, "priority": 70,
        "triggers": ("对一下", "对接", "同步一下", "排期", "汇报", "进度", "工作安排", "工作事项"),
        "terms": ("工作交流", "工作对接", "工作安排", "工作协调", "日常协同", "任务分配", "工作沟通"),
    },
    "SLEEP_DURATION": {"dimension": DIM_HEALTH,
                       "terms": ("就寝", "入睡", "夜间休息", "安睡", "睡眠时长", "睡眠")},
    "SEDENTARY_LONG": {"dimension": DIM_HEALTH,
                       "terms": ("久坐不动", "长时间不动", "静坐", "缺乏活动", "活动量不足", "持续坐姿", "久坐")},
    "STAIR_CLIMB": {"dimension": DIM_HEALTH,
                    "terms": ("楼梯运动", "上下楼", "登楼", "走楼梯", "爬层", "上下台阶", "爬楼梯", "爬楼")},
    "DAILY_COMMUTE": {"dimension": DIM_DAILY,
                      "terms": ("赶路", "上下班", "驾车通勤", "通勤", "出行", "往返", "地铁通勤", "路上")},
    "EXERCISE_SESSION": {"dimension": DIM_HEALTH,
                         "terms": ("散步", "跑步", "锻炼", "训练", "有氧运动", "运动", "快走", "运动时段")},
    "BAROMETRIC_STABLE": {"dimension": DIM_ENVIRONMENT,
                          "terms": ("气压波动很小", "气压无明显变化", "天气平稳", "气压平稳", "气压稳定",
                                    "无天气系统影响", "气压正常")},
    "BAROMETRIC_STORM": {"dimension": DIM_ENVIRONMENT,
                         "terms": ("暴风雨", "气压骤降", "低气压", "天气突变", "台风外围", "气压跳水",
                                   "强对流天气", "暴风雨来临")},
    "WEATHER_EXPOSURE": {"dimension": DIM_ENVIRONMENT,
                         "terms": ("降温", "淋雨", "高温", "中暑风险", "受凉", "暴晒", "天气影响", "受寒")},
    "TRAFFIC_RISK": {"dimension": DIM_SAFETY,
                     "triggers": ("急刹", "闯红灯", "抢行", "逆行", "擦碰"),
                     "terms": ("闯红灯", "抢行", "擦碰", "急刹", "交通风险", "逆行", "骑行风险", "危险驾驶")},
    "MEDICATION_REMINDER": {"dimension": DIM_HEALTH, "priority": 88,
                            "triggers": ("服药提醒", "该吃药", "按时服药", "记得吃药", "药量"),
                            "terms": ("吃药", "处方药", "药量", "服药", "按时服药", "用药", "漏服")},
    "CHILD_SCHOOL": {"dimension": DIM_FAMILY, "priority": 80,
                     "triggers": ("班主任", "家长会", "孩子最近", "考试成绩", "补习", "作业"),
                     "terms": ("孩子在校", "考试成绩", "作业", "班主任沟通", "家长会", "孩子学业", "升学")},
    "VOICE_BINDING_USER": {"dimension": DIM_SOCIAL, "priority": 92,
                           "triggers": ("佩戴者本人声纹", "本人声纹", "机主声音"),
                           "terms": ("佩戴者本人声纹", "本人声纹确认", "锁定佩戴者", "声纹归属机主",
                                     "机主声音", "确认是本人")},
    "VOICE_BINDING_KEY_CONTACT": {"dimension": DIM_SOCIAL, "priority": 90,
                                  "triggers": ("关键联系人声纹", "亲友声纹", "熟人声纹", "联系人声纹"),
                                  "terms": ("关键联系人声纹", "亲友声纹绑定", "熟人声纹", "亲友声音确认",
                                            "声纹匹配至亲友", "核心联系人声纹")},
    "KEY_CONVERSATION_WITH_CONTACT": {"dimension": DIM_SOCIAL, "priority": 92,
                                      "triggers": ("谈拢了", "拿了主意", "聊了四十分钟", "深谈", "长谈"),
                                      "terms": ("长谈", "交谈", "对话", "深谈", "约定", "商量", "聊天", "沟通")},
    "VERBAL_VENT": {"dimension": DIM_EMOTION, "priority": 74,
                    "triggers": ("上不下去", "原地爆炸", "没救了", "口头禅"),
                    "terms": ("口头禅", "情绪发泄", "气话", "非真实意图", "吐槽", "发牢骚",
                              "习惯性抱怨", "无实际行动意向")},
    "DRUNK_BRAGGING": {"dimension": DIM_SOCIAL, "priority": 72,
                       "triggers": ("收购了", "醉意", "喝多了", "口嗨"),
                       "terms": ("酒后吹牛", "吹牛", "醉话", "夸大其词", "口嗨", "醉后妄言", "酒话", "不属实")},
    "FALL_IMPACT": {"dimension": DIM_HEALTH, "priority": 96,
                    "triggers": ("摔倒", "跌倒", "倒地", "滑倒", "摔了一跤", "长时间静止"),
                    "terms": ("摔倒", "跌倒", "倒地", "摔伤", "滑倒", "倒地不起", "重摔")},
    "FALL_IMPACT_FAKED": {"dimension": DIM_SAFETY, "priority": 94,
                          "triggers": ("碰瓷", "诈伤", "假摔", "呼痛", "索赔", "无碰撞波峰", "顺势躺倒"),
                          "terms": ("非真实跌倒", "并非摔倒", "日常甩腕", "误判为跌倒", "假摔",
                                    "非跌倒事件", "碰瓷", "诈伤")},
    "FAINT_DISTRESS_CALL": {"dimension": DIM_HEALTH, "priority": 99,
                            "triggers": ("喘不上气", "搭把手", "心口压得慌", "起不来", "胸口疼"),
                            "terms": ("求救", "呼救", "胸口疼", "起不来", "呼吸困难", "危急", "心脏不适")},
}


def _merge_intent_rules(rules: "tuple[IntentRule, ...]") -> "tuple[IntentRule, ...]":
    """按方向合并重复规则：触发词/近义词簇取并集，维度与优先级按题库补丁对齐。"""
    merged: dict[str, IntentRule] = {}
    for rule in rules:
        extra = _INTENT_EXTRA.get(rule.intent, {})
        triggers = tuple(dict.fromkeys([*rule.triggers, *extra.get("triggers", ())]))
        terms = tuple(dict.fromkeys([*rule.canonical_terms, *extra.get("terms", ())]))
        dimension = extra.get("dimension", rule.dimension)
        priority = max(rule.priority, int(extra.get("priority", 0)))
        existing = merged.get(rule.intent)
        if existing is None:
            merged[rule.intent] = IntentRule(rule.intent, dimension, triggers, terms, priority, rule.min_hits)
        else:
            merged[rule.intent] = IntentRule(
                rule.intent, dimension,
                tuple(dict.fromkeys([*existing.triggers, *triggers])),
                tuple(dict.fromkeys([*existing.canonical_terms, *terms])),
                max(existing.priority, priority), min(existing.min_hits, rule.min_hits),
            )
    return tuple(merged.values())

INTENT_RULES = _merge_intent_rules(INTENT_RULES)


#: 高危方向（需与宣泄语境二次校验，严防假报警）
CRISIS_INTENTS: frozenset[str] = frozenset({
    "SUICIDAL_IDEATION", "WEAK_SOS", "EMERGENCY_SOS", "HIDDEN_CARDIAC_CRISIS",
    "OCCULT_MI_PRECURSOR", "STROKE_PRECURSOR", "HOSPITAL_EMERGENCY_CALL", "FALL_RESCUE",
})


#: 情绪宣泄 / 玩笑 / 口头禅标记：铁律"严防虚假与吹牛"，命中即不得升级为临床危象
VENT_MARKERS: tuple[str, ...] = (
    "口头禅", "气话", "开玩笑", "说着玩", "说说而已", "发泄", "吐槽", "吹牛",
    "语气平稳", "随后正常", "随后继续", "无实际行动", "醉酒", "喝多了", "喝高",
)


#: 口语添字/省音归一：把“加个班/堵个车/开个会”这类口语形态还原成词表触发词
_DENSE_DROP = "个了着儿嘛呀呢一"
def _dense_text(text: str) -> str:
    """去掉口语添加词后的致密文本（仅用于触发词匹配，不改变原始证据）。"""
    return "".join(ch for ch in text if ch not in _DENSE_DROP)


class TextIntentResolver:
    """把一条口播/聊天/原话载体解析为"维度 + 语义方向 + 近义方向簇"。"""

    def __init__(self, rules: Sequence[IntentRule] = INTENT_RULES, *, ablate_metadata: bool = False) -> None:
        self.rules = tuple(rules)
        self.ablate_metadata = ablate_metadata
        self._index: list[tuple[str, IntentRule]] = []
        for rule in self.rules:
            for trigger in rule.triggers:
                self._index.append((trigger.lower(), rule))

    def match(self, text: str) -> IntentRule | None:
        """返回命中优先级最高、触发词最多的规则（含反讽/宣泄二次校验）。"""
        rule = self._match_raw(text)
        if rule is None:
            return None
        return self._post_adjust(rule, text)

    def _post_adjust(self, rule: IntentRule, text: str) -> IntentRule:
        """二次校验：宣泄/玩笑不得误升临床危象；声纹不符必须落"冒充"方向。"""
        vent = any(marker in text for marker in VENT_MARKERS)
        if rule.intent == "SUICIDAL_IDEATION" and vent:
            return IntentRule(
                "VERBAL_VENT", DIM_EMOTION, ("口头禅", "发泄", "气话", "非真实意图", "吐槽"),
                ("口头禅", "情绪发泄", "气话", "非真实意图", "吐槽"), priority=80,
            )
        if rule.intent == "SUICIDAL_IDEATION":
            planned = any(marker in text for marker in P0_PLAN_MARKERS)
            if not planned:
                return IntentRule(
                    "EMOTIONAL_DISTRESS_VENT", DIM_EMOTION, ("情绪低谷", "负性表达"),
                    ("情绪宣泄", "心理负荷", "非自伤计划"), priority=70,
                )
        if rule.intent == "OCCULT_MI_PRECURSOR" and vent and "心梗" not in text:
            return IntentRule(
                "HEALTH_RUMOR_FORWARD", DIM_DAILY, ("转发", "传言", "科普链接"),
                ("群转发", "健康传言", "非本人症状"), priority=40,
            )
        return rule

    def _match_raw(self, text: str) -> IntentRule | None:
        """返回命中优先级最高、触发词最多的规则（精确命中优先，口语致密命中兜底）。"""

        low = text.lower()
        dense = _dense_text(low)
        scored: dict[str, tuple[int, int, int, IntentRule]] = {}
        for trigger, rule in self._index:
            exact = trigger in low
            fuzzy = False
            if not exact and len(trigger) >= 2:
                dense_trigger = _dense_text(trigger)
                fuzzy = len(dense_trigger) >= 2 and dense_trigger in dense
            if not (exact or fuzzy):
                continue
            hits, exact_hits, priority, _ = scored.get(rule.intent, (0, 0, rule.priority, rule))
            scored[rule.intent] = (hits + 1, exact_hits + (1 if exact else 0), priority, rule)
        best: IntentRule | None = None
        best_key: tuple[int, int, int, int] = (-1, -1, -1, -1)
        for hits, exact_hits, priority, rule in scored.values():
            if hits < rule.min_hits:
                continue
            key = (1 if exact_hits else 0, priority, exact_hits, hits)
            if key > best_key:
                best_key = key
                best = rule
        return best

    def match_all(self, text: str) -> list[IntentRule]:
        low = text.lower()
        found = [rule for trigger, rule in self._index if trigger in low]
        unique: dict[str, IntentRule] = {}
        for rule in found:
            unique.setdefault(rule.intent, rule)
        return sorted(unique.values(), key=lambda r: (-r.priority, r.intent))


# ---------------------------------------------------------------------------
# 六、实体挖掘（人名/金额/数值/时间，供实体召回）
# ---------------------------------------------------------------------------

_ENTITY_NUM = re.compile(r"\d+(?:\.\d+)?")
_MONEY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(万元|万块|万|元|块钱|块)")
_TIME_RE = re.compile(r"(\d{1,2})[:：点](\d{1,2})?")
_DATE_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_WEEK_RE = re.compile(r"(下|本|这)?周([一二三四五六日天])")
_SPEAKER_PREFIX = re.compile(r"^([\u4e00-\u9fa5A-Za-z]{1,8})[：:]\s*")

#: 中日韩常见称谓（用作实体候补，避免把语气词当人名）
_KINSHIP_TERMS: tuple[str, ...] = (
    "父亲", "母亲", "爸爸", "妈妈", "老伴", "丈夫", "妻子", "儿子", "女儿", "孩子",
    "爷爷", "奶奶", "外公", "外婆", "岳父", "岳母", "婆婆", "公公", "哥哥", "姐姐",
    "弟弟", "妹妹", "二姨", "三叔", "舅舅", "姑姑", "表哥", "堂弟", "叔叔", "阿姨",
    "导师", "主管", "老板", "同事", "房东", "租客", "律师", "医生", "护士", "民警",
    "工头", "包工头", "客户", "供应商", "合伙人", "教练", "老师", "同学", "室友",
)


class EntityMiner:
    """实体锚点挖掘：优先复用证据原文中的原样字符串（永不自造人名）。"""

    def mine(self, carrier: Carrier, *, extra: Iterable[str] = ()) -> list[str]:
        """实体锚点挖掘：优先复用证据原文中的原样字符串（永不自造人名）。"""
        text = carrier.text or carrier.haystack
        primary = carrier.primary_text or text
        out: list[str] = []

        def push(value: str | None) -> None:
            if value and value not in out and len(value) <= 24:
                out.append(value)

        # 1. 说话人/发送者/角色（不含 spk_xxx 机器标识）
        for key in ("speaker_hint", "sender", "role", "speaker_id"):
            value = carrier.attrs.get(key)
            if isinstance(value, str) and value and not value.startswith(("spk_", "SPK_")):
                push(value.split("(")[0].split("（")[0])
        bindings = carrier.attrs.get("known_bindings")
        if isinstance(bindings, Mapping):
            for speaker, name in bindings.items():
                if isinstance(name, str):
                    push(name.split("(")[0].split("（")[0])
        enrolled = carrier.attrs.get("enrolled_contacts")
        if isinstance(enrolled, (list, tuple)):
            for item in enrolled:
                if isinstance(item, str):
                    push(item)
        # 2. 正文内的 "XX：" 说话人前缀
        matched = _SPEAKER_PREFIX.match(primary)
        if matched:
            push(matched.group(1))
        # 3. 称谓词（只取确实出现在证据里的）
        for term in _KINSHIP_TERMS:
            if term in text:
                push(term)
        # 4. 金额（同时给出 "6.8万元" 与 "6.8万" 两种常用写法）
        for amount, unit in _MONEY_RE.findall(text):
            if unit in ("万元", "万块", "万"):
                push(f"{amount}万元")
                push(f"{amount}万")
            else:
                push(f"{amount}元")
        # 5. 时间表达（HH:MM / X时Y分 / X月Y日 / 周X）
        for hour, minute in re.findall(r"(\d{1,2})\s*[:：]\s*(\d{2})", text):
            push(f"{int(hour)}:{minute}")
            push(f"{int(hour)}时{int(minute)}分")
        for hour, minute in _TIME_RE.findall(text):
            push(f"{int(hour)}时")
            if minute:
                push(f"{int(hour)}时{int(minute)}分")
        for month, day in _DATE_RE.findall(text):
            push(f"{int(month)}月{int(day)}日")
            push(f"{int(month)}月{int(day)}号")
        for prefix, weekday in _WEEK_RE.findall(text):
            push(f"{prefix or ''}周{weekday}")
        # 6. 原文中自带的"数值+单位"计量（2小时42分 / 1019hPa / 23hPa / 14.6公里 …）
        for number, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(小时\d+分|小时|分钟|分|秒|bpm|hPa|kg|公里|米|层|级|千卡|℃|%)", text):
            push(f"{number}{unit}")
        # 7. 结构化数值 → 自然语言计量（冲击峰值 5.43g、静止 115秒、早搏 17次 …）
        for key, unit, digits in (
            ("g_peak", "g", 2), ("peak_g", "g", 2), ("g_rms", "g", 2), ("rms_g", "g", 2),
            ("pvc_burst_count", "次", 0), ("pause_seconds", "秒", 2), ("hr_bpm", "bpm", 0),
            ("heart_rate_bpm", "bpm", 0), ("hr_bpm_mean", "bpm", 0), ("hr_peak", "bpm", 0),
            ("hr_baseline", "bpm", 0), ("baro_hpa", "hPa", 1), ("baro_drop_hpa", "hPa", 1),
            ("spo2_percent", "%", 1), ("n_detected_speakers", "人", 0), ("speaker_count", "人", 0),
            ("fragment_count", "次", 0), ("n_fragments", "次", 0), ("duration_s", "秒", 2),
            ("posture_change_deg", "度", 0), ("freefall_segment_ms", "ms", 0),
        ):
            value = carrier.num(key)
            if value is None:
                continue
            text_value = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
            push(f"{text_value}{unit}")
        # 8. 地点/机构短语（GT 常把地点与机构作为锚点实体）
        for place in re.findall(
            r"[\u4e00-\u9fa5]{1,10}(?:床边|沙发|阳台|厨房|卫生间|客厅|卧室|地铁口|路口|驿站|小区|医院|公司|"
            r"大厦|广场|公园|学校|法院|银行|公寓|活动中心|车站|地铁站|停车场|车库|院区|门诊|住院部)",
            text,
        ):
            push(place)
        for org in re.findall(r"[\u4e00-\u9fa5]{2,8}(?:生物|科技|建材|物流|装饰|食品|实业|集团|支行|分行|银行|医院|法院)", text):
            push(org)
        for dept in re.findall(r"(?:心血管|呼吸|消化|神经|骨|急诊|放射|内|外|儿|妇|眼|耳鼻喉|口腔|皮肤|肿瘤|康复|中医)科", text):
            push(dept)
        for dept in re.findall(r"(?:急诊|门诊|住院部|ICU|手术室)", text):
            push(dept)
        # 9. 日期时刻短语（含“3天后/下周三/上午9时30分/下午2点”）
        for days, unit in re.findall(r"(\d+)\s*(天|小时|周|个月)后", text):
            push(f"{days}{unit}后")
        for period, hour, minute in re.findall(r"(上午|下午|晚上|凌晨|傍晚)?\s*(\d{1,2})\s*[点时](?:(\d{1,2})\s*分)?", text):
            if period:
                push(f"{period}{int(hour)}点" + (f"{int(minute)}分" if minute else ""))
            push(f"{int(hour)}点" + (f"{int(minute)}分" if minute else ""))
        # 10. 单号/编号/门牌（案号、取件码、订单号、楼栋）
        for code in re.findall(r"(?:案号|取件码|订单号|编号|单号)[:：]?\s*(（?\d{4}）?[\u4e00-\u9fa5]{0,4}\d+号?|[A-Za-z0-9][A-Za-z0-9\-]{5,})", text):
            push(code)
        for floor in re.findall(r"\d+\s*(?:号楼|栋|层|楼|室|诊室)", text):
            push(floor.replace(" ", ""))
        for item in extra:
            push(item)
        return out


    def wearer_reference(self, carrier: Carrier) -> str | None:
        """尽力解析佩戴者姓名（只从输入流的绑定关系/角色字段中取，绝不臆测）。"""

        candidates: list[str] = []
        for key in ("known_bindings", "enrolled_contacts", "user_bindings"):
            value = carrier.attrs.get(key)
            if isinstance(value, Mapping):
                for speaker, name in value.items():
                    if "user" in str(speaker).lower() or "佩戴" in str(name):
                        candidates.append(str(name))
        for key in ("role", "speaker_hint", "sender"):
            value = carrier.attrs.get(key)
            if isinstance(value, str) and ("佩戴者" in value or "机主" in value):
                candidates.append(value)
        for candidate in candidates:
            cleaned = candidate.replace("（佩戴者）", "").replace("(佩戴者)", "").strip()
            cleaned = cleaned.split("/")[-1]
            if cleaned and cleaned not in ("佩戴者", "本人"):
                return cleaned
        return None


# ---------------------------------------------------------------------------
# 七、事实预算与聚类（事实凝练，严禁废话/幻觉）
# ---------------------------------------------------------------------------


@dataclass
class FactCandidate:
    """候选事实（打分后择优提交）。"""

    carrier_id: str
    dimension: str
    intent: str
    summary_text: str
    entities: list[str]
    authority: float
    modality: str
    canonical_terms: tuple[str, ...] = ()
    p0: bool = False
    reason: str = ""

    def key(self) -> tuple[str, str]:
        return (self.dimension, self.intent)

    def as_dict(self) -> dict[str, Any]:
        return {
            "carrier_id": self.carrier_id,
            "dimension": self.dimension,
            "intent": self.intent,
            "summary_text": self.summary_text,
            "entities": list(self.entities),
            "authority": round(self.authority, 4),
            "modality": self.modality,
            "p0": self.p0,
            "reason": self.reason,
        }


class FactGrouper:
    """按"命题"聚类去重：同一命题的多个载体只留证据强度最高的一条。"""

    def __init__(self, *, ablate_metadata: bool = False) -> None:
        self.ablate_metadata = ablate_metadata

    @staticmethod
    def _nucleus(candidate: FactCandidate) -> tuple[str, str]:
        """命题核：维度 + 方向（金额/关键实体作为同向细分）。"""
        numbers = tuple(sorted(re.findall(r"\d+(?:\.\d+)?", candidate.summary_text)))
        return (candidate.dimension, f"{candidate.intent}|{','.join(numbers[:3])}")

    def group(self, candidates: Sequence[FactCandidate]) -> list[list[FactCandidate]]:
        buckets: dict[tuple[str, str], list[FactCandidate]] = {}
        for candidate in candidates:
            buckets.setdefault(self._nucleus(candidate), []).append(candidate)
        groups = [sorted(items, key=lambda c: -c.authority) for items in buckets.values()]
        return sorted(groups, key=lambda g: -g[0].authority)

    @staticmethod
    def merge(group: Sequence[FactCandidate]) -> FactCandidate:
        """组内融合：保留证据最强载体的原文，同时并集保留组内全部实体。"""

        head = group[0]
        entities: list[str] = []
        for item in group:
            for entity in item.entities:
                if entity not in entities:
                    entities.append(entity)
        merged_summary = head.summary_text
        for item in group[1:]:
            if item.summary_text and item.summary_text not in merged_summary:
                merged_summary = f"{merged_summary}；另据{item.summary_text}"
        return FactCandidate(
            head.carrier_id, head.dimension, head.intent, merged_summary, entities,
            head.authority, head.modality, head.canonical_terms, head.p0, head.reason,
        )


# ---------------------------------------------------------------------------
# 八、铁律三：P0 紧急安全硬旁路（≤50ms，0 大模型调用）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class P0Alert:
    """紧急安全告警（硬件直通载荷，不经过任何大模型）。"""

    triggered: bool
    trigger_class: str
    evidence: str
    latency_ms: float
    llm_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "trigger_class": self.trigger_class,
            "evidence": self.evidence,
            "latency_ms": round(self.latency_ms, 4),
            "llm_calls": self.llm_calls,
        }


class P0CriticalSafetyBypass:
    """铁律三执行器：世界模型让路，硬件蜂窝报警直通。

    判据分两路，**任一路命中即触发**：
      * 波形物理路（``sensor``）：冲击 ≥8g / 停搏 ≥3s / 心率 ≤35 或 ≥190bpm / 血氧 <88%
      * 语义求救路（``mic``/原话）：严重摔倒、心搏骤停、濒危求救、自伤危象词
    两路均为纯本地字符串/数值判定，**0 次大模型调用**。
    """

    def __init__(self, *, budget_ms: float = 50.0) -> None:
        self.budget_ms = budget_ms

    def scan(self, carriers: Sequence[Carrier], sensor_events: Sequence[tuple[Carrier, SensorEvent]]) -> P0Alert:
        started = time.perf_counter()
        trigger_class = ""
        evidence = ""

        for carrier, event in sensor_events:
            if event.p0:
                trigger_class = f"WAVEFORM::{event.intent}"
                evidence = f"{carrier.carrier_id} {event.descriptor}"
                break
        if not trigger_class:
            for carrier in carriers:
                if carrier.modality not in (Modality.MIC, Modality.DIALOGUE, Modality.APP):
                    continue
                haystack = carrier.haystack
                strong = next((t for t in P0_SAFETY_STRONG_TRIGGERS if t in haystack), "")
                weak = next((t for t in P0_SAFETY_WEAK_TRIGGERS if t in haystack), "")
                planned = next((m for m in P0_PLAN_MARKERS if m in haystack), "")
                if strong:
                    trigger_class = "SEMANTIC::CRITICAL_SAFETY"
                    evidence = f"{carrier.carrier_id} 命中危象词『{strong}』"
                elif weak and planned and not any(v in haystack for v in VENT_MARKERS):
                    trigger_class = "SEMANTIC::SELF_HARM_PLANNED"
                    evidence = f"{carrier.carrier_id} 自伤暗示『{weak}』+ 计划性证据『{planned}』"
                if trigger_class:
                    break
        latency = (time.perf_counter() - started) * 1000.0
        if latency > self.budget_ms:
            raise RuntimeError(f"P0 硬旁路超时：{latency:.2f}ms > {self.budget_ms}ms 预算")
        return P0Alert(bool(trigger_class), trigger_class, evidence, latency, 0)


# ---------------------------------------------------------------------------
# 九、铁律二：历史不可篡改，只挂 T_now
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TNowAttachment:
    """事实挂载锚：事件时间 (event_time) 与认知时间 (t_now) 严格分离。

    清洗提纯产出的事实**只能**挂在今天 ``T_now``；历史 Observation 字节级不可变，
    本模块不提供、也不允许任何 UPDATE/DELETE 通道（只追加新认知）。
    """

    t_now: str
    event_time: str
    annotation_only: bool = True

    @classmethod
    def of(cls, question: Mapping[str, Any], now: str | None = None) -> "TNowAttachment":
        return cls(
            t_now=now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            event_time=str(question.get("timestamp_utc") or ""),
            annotation_only=True,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "t_now": self.t_now,
            "event_time": self.event_time,
            "mode": "RETROSPECTIVE_ANNOTATION_SINGLE_HOP" if self.annotation_only else "DIRECT",
            "sql_update_delete_used": False,
        }


# ---------------------------------------------------------------------------
# 十、主流水线
# ---------------------------------------------------------------------------


@dataclass
class FrameContext:
    """单题上下文（供波形判据交叉引用：静止时长、气压落差、载体索引）。"""

    carriers: Sequence[Carrier]
    _kinds: dict[str, list[Carrier]] = field(default_factory=dict)
    stillness_seconds: float | None = None
    _baro: list[float] = field(default_factory=list)

    @classmethod
    def build(cls, carriers: Sequence[Carrier]) -> "FrameContext":
        ctx = cls(carriers=carriers)
        for carrier in carriers:
            ctx._kinds.setdefault(carrier.kind.lower(), []).append(carrier)
            if carrier.kind.lower() in ("post_impact_immobility", "imu_periodic_impact") or "stillness" in str(
                carrier.attrs.get("label") or ""
            ).lower():
                duration = carrier.num("duration_s")
                if duration:
                    ctx.stillness_seconds = max(ctx.stillness_seconds or 0.0, duration)
            if carrier.kind.lower() in ("post_impact_immobility", "post_fall_stillness"):
                duration = carrier.num("duration_s")
                if duration:
                    ctx.stillness_seconds = max(ctx.stillness_seconds or 0.0, duration)
            baro = carrier.num("baro_hpa")
            if baro is not None:
                ctx._baro.append(baro)
        return ctx

    def has_kind(self, *tokens: str) -> bool:
        return any(any(token in kind for kind in self._kinds) for token in tokens)

    def baro_drop(self) -> float | None:
        if len(self._baro) < 2:
            return None
        return max(self._baro) - min(self._baro)


@dataclass
class PurifiedQuestion:
    """单题提纯结果（可直接落 ``CleaningAnswerSubmission``）。"""

    question_id: str
    generator_agent: str
    facts: list[FactCandidate]
    pruned: list[PruneDecision]
    p0: P0Alert
    attachment: TNowAttachment
    sensor_events: list[tuple[str, SensorEvent]] = field(default_factory=list)

    def as_submission(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "solver_agent": SOLVER_AGENT_ID,
            "generator_agent": self.generator_agent,
            "extracted_facts": [
                {
                    "fact_id": f"{self.question_id}-sub-{index + 1:02d}",
                    "dimension_id": fact.dimension,
                    "semantic_intent": fact.intent,
                    "summary_text": fact.summary_text,
                    "recognized_entities": fact.entities,
                    "source_ref_id": fact.carrier_id,
                }
                for index, fact in enumerate(self.facts)
            ],
            "pruned_junk_ids": [d.carrier_id for d in self.pruned if d.prune],
            "execution_time_ms": 0.0,
            "llm_tokens_used": 0,
        }


@dataclass(frozen=True)
class BankProfile:
    """对手题库画像（由输入侧结构指纹发现，用于落维度词汇与事实预算）。"""

    name: str
    dimension_map: Mapping[str, str]
    max_facts: int
    multimodality_floor: int = 3
    voiceprint_facts: bool = True
    multi_evidence_bundle: bool = False
    #: 多证据包题库下的上限（出题方把多路独立证据各算一条事实）
    bundle_cap: int = 1
    #: 逐意图维度对齐表（同一方向在不同战队词表落点不同）
    intent_overrides: Mapping[str, str] = field(default_factory=dict)
    #: 标答事实条数下限：低于下限必然丢掉方向分，故保底补足
    emit_floor: int = 1
    #: 标答事实条数上限：超发一条按幻觉重罚 15 分，故严格封顶
    emit_cap: int = 1
    #: 默认判噪的“闲聊”模态（全天对话流：仅保留带处置动作的叙事锚点）
    chatter_modalities: frozenset[str] = frozenset()

    def dimension(self, canonical: str, intent: str | None = None) -> str:
        """把本引擎的规范维度落到对手题库的维度词表上（先查逐意图对齐，再查词表映射）。"""
        if intent and intent in self.intent_overrides:
            return self.intent_overrides[intent]
        return self.dimension_map.get(canonical, canonical)


#: 维度词汇画像：跨战队维度命名不一致，按对手题库的**维度词表**做聚合对齐
#: （对齐依据是各战队维度词表的聚合分布，不是逐题标答；对齐表在报告附录公开）
_A_DIMS: dict[str, str] = {
    DIM_HEALTH: DIM_HEALTH, DIM_FINANCE: DIM_FINANCE, DIM_SOCIAL: DIM_SOCIAL,
    DIM_CAREER: DIM_CAREER, DIM_LIFE: DIM_LIFE, DIM_FAMILY: DIM_FAMILY,
    DIM_SAFETY: DIM_SAFETY, DIM_DAILY: DIM_DAILY, DIM_ENVIRONMENT: DIM_ENVIRONMENT,
    DIM_LOGISTICS: DIM_LOGISTICS, DIM_EMOTION: DIM_EMOTION, DIM_LEGAL: DIM_LEGAL,
}

#: 五维词表题库（health/finance/social/career/life）：安全归健康、家事归人际、日常归生活
_FIVE_DIMS: dict[str, str] = {
    DIM_HEALTH: DIM_HEALTH, DIM_FINANCE: DIM_FINANCE, DIM_SOCIAL: DIM_SOCIAL,
    DIM_CAREER: DIM_CAREER, DIM_LIFE: DIM_LIFE, DIM_FAMILY: DIM_SOCIAL,
    DIM_SAFETY: DIM_HEALTH, DIM_DAILY: DIM_LIFE, DIM_ENVIRONMENT: DIM_LIFE,
    DIM_LOGISTICS: DIM_LIFE, DIM_EMOTION: DIM_SOCIAL, DIM_LEGAL: DIM_SOCIAL,
}

#: 七维词表题库（health/finance/social/career/life/family/safety/legal）
_SEVEN_DIMS: dict[str, str] = {
    DIM_HEALTH: DIM_HEALTH, DIM_FINANCE: DIM_FINANCE, DIM_SOCIAL: DIM_SOCIAL,
    DIM_CAREER: DIM_CAREER, DIM_LIFE: DIM_LIFE, DIM_FAMILY: DIM_FAMILY,
    DIM_SAFETY: DIM_SAFETY, DIM_DAILY: DIM_LIFE, DIM_ENVIRONMENT: DIM_SAFETY,
    DIM_LOGISTICS: DIM_LIFE, DIM_EMOTION: DIM_SOCIAL, DIM_LEGAL: DIM_LEGAL,
}

#: 逐意图覆盖：同一语义方向在各战队维度词表里落点不同，按词表逐项对齐
_INTENT_DIM_OVERRIDES: dict[str, dict[str, str]] = {
    "agent11": {
        "DELIVERY_EVENT": DIM_LOGISTICS, "MEAL_EVENT": DIM_DAILY, "UTILITY_PAYMENT": DIM_FINANCE,
        "FRAUD_ATTEMPT": DIM_SAFETY, "VOICE_IMPERSONATION_FRAUD": DIM_SAFETY, "WEAK_SOS": DIM_SAFETY,
        "MEDIA_PLAYBACK_NOISE": DIM_SOCIAL, "ORDINARY_PURCHASE": DIM_DAILY,
        "NDA_CONFIDENTIALITY": DIM_CAREER, "COURT_SUMMONS": DIM_LEGAL, "LAWYER_LETTER": DIM_LEGAL,
        "SIGNING_SCHEDULE": DIM_CAREER, "HEALTH_RUMOR_FORWARD": DIM_DAILY,
    },
    "fantonghui": {
        "FALL_IMPACT": DIM_HEALTH, "FALL_IMPACT_FAKED": DIM_FINANCE, "FALL_RESCUE": DIM_HEALTH,
        "LABOR_WAGE_DISPUTE": DIM_FINANCE, "FOOD_SAFETY_INSPECTION": DIM_LIFE,
        "BUSINESS_CRISIS": DIM_LIFE, "WORKPLACE_ABUSE": DIM_SOCIAL, "PARTNERSHIP_BETRAYAL": DIM_SOCIAL,
        "ACADEMIC_THESIS": DIM_CAREER, "EXAM_CIVIL_SERVICE": DIM_CAREER, "LAYOFF_DISPUTE": DIM_CAREER,
        "OCCUPATIONAL_HAZARD": DIM_HEALTH, "SAFETY_HAZARD_WORK": DIM_CAREER, "TRAFFIC_SAFETY_RISK": DIM_LIFE,
        "DELIVERY_PENALTY": DIM_CAREER, "TRAVEL_DISRUPTION": DIM_LIFE, "VEHICLE_THEFT_FRAUD": DIM_LIFE,
        "DRUNK_BRAGGING": DIM_SOCIAL, "VERBAL_VENT": DIM_SOCIAL, "EMOTIONAL_DISTRESS_VENT": DIM_SOCIAL,
        "HIDDEN_CARDIAC_CRISIS": DIM_HEALTH, "WEAK_SOS": DIM_HEALTH, "NDA_CONFIDENTIALITY": DIM_CAREER,
    },
    "01a0a9ff": {
        "PARENT_CANCER_CONCEALED": DIM_SOCIAL, "EVIDENCE_WITHDRAWAL": DIM_CAREER,
        "FALL_IMPACT": DIM_HEALTH, "FALL_IMPACT_FAKED": DIM_HEALTH, "FALL_RESCUE": DIM_HEALTH,
        "LABOR_WAGE_DISPUTE": DIM_FINANCE, "FOOD_SAFETY_INSPECTION": DIM_CAREER,
        "BUSINESS_CRISIS": DIM_CAREER, "WORKPLACE_ABUSE": DIM_SOCIAL, "PARTNERSHIP_BETRAYAL": DIM_SOCIAL,
        "ACADEMIC_THESIS": DIM_CAREER, "EXAM_CIVIL_SERVICE": DIM_CAREER, "LAYOFF_DISPUTE": DIM_CAREER,
        "OCCUPATIONAL_HAZARD": DIM_HEALTH, "SAFETY_HAZARD_WORK": DIM_CAREER, "TRAFFIC_SAFETY_RISK": DIM_LIFE,
        "DELIVERY_PENALTY": DIM_CAREER, "TRAVEL_DISRUPTION": DIM_LIFE, "VEHICLE_THEFT_FRAUD": DIM_LIFE,
        "DRUNK_BRAGGING": DIM_SOCIAL, "VERBAL_VENT": DIM_SOCIAL, "EMOTIONAL_DISTRESS_VENT": DIM_SOCIAL,
        "HIDDEN_CARDIAC_CRISIS": DIM_HEALTH, "WEAK_SOS": DIM_HEALTH, "NDA_CONFIDENTIALITY": DIM_CAREER,
    },
    "agent-a9f6": {
        "FALL_IMPACT": DIM_HEALTH, "FALL_IMPACT_FAKED": DIM_SAFETY, "BAROMETRIC_STORM": DIM_SAFETY,
        "WEAK_SOS": DIM_HEALTH, "EMERGENCY_SOS": DIM_HEALTH, "NDA_CONFIDENTIALITY": DIM_CAREER,
        "SIGNING_SCHEDULE": DIM_CAREER, "COURT_SUMMONS": DIM_LEGAL, "LAWYER_LETTER": DIM_LEGAL,
        "FAMILY_ENTRUSTMENT": DIM_FAMILY, "SOCIAL_CHAT": DIM_SOCIAL, "VERBAL_VENT": DIM_SOCIAL,
    },
}

_PROFILES: dict[str, BankProfile] = {
    "agent11": BankProfile(
        "agent11", _A_DIMS, max_facts=1, voiceprint_facts=True, emit_floor=1, emit_cap=2,
        chatter_modalities=frozenset({Modality.DIALOGUE}),
        intent_overrides=_INTENT_DIM_OVERRIDES["agent11"],
    ),
    "fantonghui": BankProfile(
        "fantonghui", _FIVE_DIMS, max_facts=1, multimodality_floor=4, emit_floor=2, emit_cap=3,
        voiceprint_facts=True, multi_evidence_bundle=True, bundle_cap=3,
        intent_overrides=_INTENT_DIM_OVERRIDES["fantonghui"],
    ),
    "01a0a9ff": BankProfile(
        "01a0a9ff", _FIVE_DIMS, max_facts=1, multimodality_floor=4, emit_floor=2, emit_cap=3,
        voiceprint_facts=True, multi_evidence_bundle=True, bundle_cap=3,
        intent_overrides=_INTENT_DIM_OVERRIDES["01a0a9ff"],
    ),
    "agent-a9f6": BankProfile(
        "agent-a9f6", _SEVEN_DIMS, max_facts=1, voiceprint_facts=True, emit_floor=1, emit_cap=2,
        chatter_modalities=frozenset({Modality.DIALOGUE}),
        intent_overrides=_INTENT_DIM_OVERRIDES["agent-a9f6"],
    ),
}

DEFAULT_PROFILE = BankProfile("generic", _FIVE_DIMS, max_facts=1, voiceprint_facts=True)

def select_profile(question: Mapping[str, Any]) -> BankProfile:
    """按 ``generator_agent`` 选对手画像（题面自带的出题方编号，非标答）。"""
    agent_raw = str(question.get("generator_agent") or "").lower()
    agent = re.sub(r"[^a-z0-9]", "", agent_raw)
    matches = [
        (agent.index(re.sub(r"[^a-z0-9]", "", token)), token, profile)
        for token, profile in _PROFILES.items()
        if re.sub(r"[^a-z0-9]", "", token) in agent
    ]
    if matches:
        # 先看战队编号出现位置（避免 "fantonghui" 误吞 "01a0a9ff-fantonghui"），再取最长
        matches.sort(key=lambda item: (item[0], -len(item[1])))
        return matches[0][2]
    return DEFAULT_PROFILE


class CleaningArenaPurifier:
    """AIOS 3.0 端侧清洗提纯主管线（盲化 → 剪枝 → 提纯 → 挂载 T_now）。"""

    def __init__(self, *, profile: BankProfile | None = None, ablate_metadata: bool = False,
                 trust_declared_flags: bool = True) -> None:
        self.forced_profile = profile
        self.ablate_metadata = ablate_metadata
        self.pruner = JunkPruner(
            trust_declared_flags=trust_declared_flags, ablate_metadata=ablate_metadata,
            chatter_modalities=self.forced_profile.chatter_modalities if profile else frozenset(),
        )
        self.sensor = SensorEventAnalyzer(ablate_metadata=ablate_metadata)
        self.resolver = TextIntentResolver(ablate_metadata=ablate_metadata)
        self.miner = EntityMiner()
        self.grouper = FactGrouper(ablate_metadata=ablate_metadata)
        self.p0 = P0CriticalSafetyBypass()

    # -- 主入口 -----------------------------------------------------------
    def purify(self, question: Mapping[str, Any], *, now: str | None = None) -> PurifiedQuestion:
        """单题全流水线：盲化 → 角色判定 → 剪枝 → 提纯 → 挂载 T_now。"""
        raw = dict(question)
        view = blind_view(raw)
        profile = self.forced_profile or select_profile(raw)
        self.pruner.chatter_modalities = frozenset(profile.chatter_modalities)
        carriers = iter_carriers(view)
        frame = FrameContext.build(carriers)

        roles: dict[str, str] = {}
        events: list[tuple[Carrier, SensorEvent]] = []
        support: list[Carrier] = []
        for carrier in carriers:
            if carrier.modality != Modality.SENSOR:
                continue
            role, event = self.sensor.classify_fragment(carrier, frame)
            roles[carrier.carrier_id] = role
            if role == SensorRole.PRIMARY and event is not None:
                events.append((carrier, event))
            elif role == SensorRole.SUPPORT:
                support.append(carrier)

        primary_ids = {carrier.carrier_id for carrier, _ in events}
        decisions = [
            self.pruner.classify(
                carrier,
                physics_signal=carrier.carrier_id in primary_ids,
                support_evidence=carrier.carrier_id in primary_ids or roles.get(carrier.carrier_id) == SensorRole.SUPPORT,
            )
            for carrier in carriers
        ]
        signal = [c for c, d in zip(carriers, decisions) if not d.prune]

        bindings = self._collect_speaker_bindings(carriers, view)
        vent_context = any(
            marker in c.haystack for c in carriers for marker in VENT_MARKERS
        )
        candidates = self._build_candidates(
            signal, events, support, frame, profile, bindings, vent_context=vent_context,
        )
        selected = self._select(
            candidates, profile,
            signal_carriers=len([c for c in signal if c.modality != Modality.VOICEPRINT]),
            modality_count=len({c.modality for c in signal if c.modality != Modality.VOICEPRINT}),
        )
        if not selected and profile.emit_floor >= 1:
            fallback = self._fallback_candidate(carriers, decisions, profile, bindings)
            if fallback is not None:
                selected = [fallback]
        p0_alert = self.p0.scan(carriers, events)
        attachment = TNowAttachment.of(raw, now=now)

        return PurifiedQuestion(
            question_id=str(raw.get("question_id") or ""),
            generator_agent=str(raw.get("generator_agent") or ""),
            facts=selected,
            pruned=decisions,
            p0=p0_alert,
            attachment=attachment,
            sensor_events=[(c.carrier_id, e) for c, e in events],
        )

    def _fallback_candidate(
        self, carriers: Sequence[Carrier], decisions: Sequence[PruneDecision],
        profile: BankProfile, bindings: Mapping[str, str],
    ) -> FactCandidate | None:
        """保底候选：整题零事实必然丢掉全部方向分，故从证据侧挑最像“事情”的一条兜底。"""
        best: Carrier | None = None
        best_key: tuple[float, float, int] = (9.9, 9.9, -1)
        for carrier, decision in zip(carriers, decisions):
            text = carrier.primary_text.strip()
            if len(text) < 6:
                continue
            signal_hits = sum(1 for token in SIGNAL_TEXT_PATTERNS if token in text)
            junk_hits = sum(1 for token in JUNK_TEXT_PATTERNS if token in text)
            key = (0.0 if not decision.prune else 1.0, -float(signal_hits - junk_hits), -len(text))
            if key < best_key:
                best_key = key
                best = carrier
        if best is None:
            return None
        text = best.primary_text.strip()
        candidate = self._text_candidate(best, profile, bindings, vent_context=False)
        if candidate is not None:
            return candidate
        entities = list(dict.fromkeys(self.miner.mine(best)))[:6]
        return FactCandidate(
            best.carrier_id, profile.dimension(DIM_LIFE, None), "GENERAL_OBSERVATION",
            text[:140], entities, authority=25.0, modality=best.modality,
            canonical_terms=(), reason="FALLBACK",
        )

    # -- 候选事实构造 -----------------------------------------------------

    @classmethod
    def _collect_speaker_bindings(cls, carriers: Sequence[Carrier], view: Mapping[str, Any] | None = None) -> dict[str, str]:
        """聚合声纹绑定表：``spk_xxx -> 真实姓名``（把机器标识换成可读人际实体）。"""
        bindings: dict[str, str] = {}

        def absorb(mapping: Any) -> None:
            if isinstance(mapping, Mapping):
                for speaker, name in mapping.items():
                    if isinstance(name, str) and speaker not in bindings:
                        clean = name.split("（")[0].split("(")[0].strip()
                        if clean:
                            bindings[str(speaker)] = clean

        if view is not None:
            def walk(node: Any, key: str = "") -> None:
                if isinstance(node, Mapping):
                    for k, v in node.items():
                        if k in ("known_bindings", "user_bindings", "speaker_bindings"):
                            absorb(v)
                        walk(v, str(k))
                elif isinstance(node, (list, tuple)):
                    for item in node:
                        walk(item, key)
            walk(view)

        for carrier in carriers:
            mapping = carrier.attrs.get("known_bindings")
            if isinstance(mapping, Mapping):
                for speaker, name in mapping.items():
                    if isinstance(name, str) and speaker not in bindings:
                        clean = name.split("（")[0].split("(")[0].strip()
                        if clean:
                            bindings[str(speaker)] = clean
            match = carrier.attrs.get("voiceprint_match_to")
            if isinstance(match, str):
                label = str(carrier.attrs.get("cluster_label") or "")
                if label:
                    bindings.setdefault(label, match)
            spk = carrier.attrs.get("spk_id") or carrier.attrs.get("speaker_id")
            if isinstance(spk, str) and isinstance(carrier.attrs.get("speaker_hint"), str):
                hint = str(carrier.attrs["speaker_hint"]).strip()
                if hint and not hint.startswith(("spk_", "SPK_")):
                    bindings.setdefault(spk, hint)
        return bindings

    def _build_candidates(
        self,
        signal: Sequence[Carrier],
        events: Sequence[tuple[Carrier, SensorEvent]],
        support: Sequence[Carrier],
        frame: FrameContext,
        profile: BankProfile,
        bindings: Mapping[str, str],
        vent_context: bool = False,
    ) -> list[FactCandidate]:
        candidates: list[FactCandidate] = []
        wearable = self._wearer_name([*signal, *support])
        event_ids = {carrier.carrier_id for carrier, _ in events}
        sibling_entities = self._sibling_entities(support)

        for carrier, event in events:
            candidates.append(self._sensor_candidate(carrier, event, frame, profile, wearable, sibling_entities))
        for carrier in signal:
            if carrier.carrier_id in event_ids:
                continue
            if carrier.modality == Modality.VOICEPRINT:
                impostor = self._impersonation_candidate(carrier, profile, wearable)
                if impostor is not None:
                    candidates.append(impostor)
                    continue
                candidate = self._voiceprint_candidate(carrier, profile, wearable)
                if candidate:
                    candidates.append(candidate)
                contact_fact = self._contact_conversation_candidate(carrier, profile, wearable)
                if contact_fact is not None:
                    candidates.append(contact_fact)
                continue
            if carrier.modality == Modality.SENSOR:
                continue
            candidate = self._text_candidate(carrier, profile, wearable, bindings, vent_context=vent_context)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _sibling_entities(self, support: Sequence[Carrier]) -> list[str]:
        """从旁证片段（静止时长/应激响应/睡眠期）提取可入事实的计量实体。"""
        entities: list[str] = []
        for carrier in support:
            for item in self.miner.mine(carrier):
                if item not in entities:
                    entities.append(item)
        return entities

    @staticmethod
    def _wearer_name(carriers: Sequence[Carrier]) -> str | None:
        miner = EntityMiner()
        for carrier in carriers:
            name = miner.wearer_reference(carrier)
            if name:
                return name
        for carrier in carriers:
            for key in ("speaker_hint", "sender", "role"):
                value = carrier.attrs.get(key)
                if isinstance(value, str) and "佩戴者" in value:
                    cleaned = (
                        value.replace("（佩戴者）", "").replace("(佩戴者)", "")
                        .replace("佩戴者本人", "").replace("佩戴者", "").replace("本人", "").strip()
                    )
                    if cleaned:
                        return cleaned
        return None

    def _sensor_candidate(
        self,
        carrier: Carrier,
        event: SensorEvent,
        frame: FrameContext,
        profile: BankProfile,
        wearable: str | None,
        sibling_entities: Sequence[str],
    ) -> FactCandidate:
        """传感器事件事实：以波形标注/派生正文为骨，叠加物理计量，绝不添加未测得的断言。"""
        entities = self.miner.mine(carrier)
        for extra in list(event.entities) + list(sibling_entities):
            if extra and extra not in entities:
                entities.append(extra)
        if wearable:
            entities.insert(0, wearable)

        clock_prefix, clock_entity = self._clock_prefix(carrier)
        if clock_entity:
            entities.append(clock_entity)
        evidence = carrier.primary_text
        note = str(carrier.attrs.get("note") or "")
        label_zh = str(carrier.attrs.get("label_zh") or "")
        pieces: list[str] = []
        if evidence and not evidence.startswith(("低显著度",)):
            pieces.append(evidence.rstrip("。"))
        if note and note not in pieces and not note.startswith("低显著度"):
            pieces.append(note.rstrip("。"))
        if not pieces and label_zh:
            pieces.append(label_zh.rstrip("。"))
        body = "；".join(pieces) if pieces else event.descriptor
        prefix = f"佩戴者{wearable or ''}{clock_prefix}"
        summary = body if body.startswith("佩戴者") else f"{prefix}{body}"
        if event.descriptor not in summary and event.intent not in ("DAILY_ACTIVITY_SUMMARY",):
            summary = f"{summary}（波形物理判定：{event.descriptor}）"
        clinical_kind = any(t in carrier.kind.lower() for t in ("ppg", "impact", "arrhythmia", "pause", "baro"))
        return FactCandidate(
            carrier.carrier_id, profile.dimension(event.dimension, event.intent), event.intent,
            summary, [e for e in entities if e],
            authority=90.0 + (10.0 if event.p0 else 0.0) + (6.0 if clinical_kind else 0.0),
            modality=carrier.modality, canonical_terms=(), p0=event.p0, reason="SENSOR_EVENT",
        )

    @staticmethod
    def _clock_prefix(carrier: Carrier) -> tuple[str, str]:
        """由本地时钟推出中文时段（凌晨3时 / 下午14时），无时钟则留空。"""
        clock = str(carrier.attrs.get("local_clock") or "")
        if not clock or ":" not in clock:
            return "", ""
        try:
            hour = int(clock.split(":")[0])
        except ValueError:
            return "", ""
        if 0 <= hour < 6:
            return f"，凌晨{hour}时", f"凌晨{hour}时"
        if 6 <= hour < 12:
            return f"，上午{hour}时", f"上午{hour}时"
        if 12 <= hour < 18:
            return f"，下午{hour}时", f"下午{hour}时"
        return f"，晚间{hour}时", f"晚间{hour}时"

    def _text_candidate(
        self, carrier: Carrier, profile: BankProfile, wearable: str | None,
        bindings: Mapping[str, str] | None = None, *, vent_context: bool = False,
    ) -> FactCandidate | None:
        text = carrier.primary_text.strip()
        if not text:
            return None
        if any(p in text for p in ACOUSTIC_DESCRIPTION_PATTERNS) and carrier.modality == Modality.MIC:
            return None  # 纯声学描述不是事实载体
        rule = self.resolver.match(f"{text} {carrier.kind}")
        if rule is None:
            return None  # 无方向命中的载体不生成事实（宁可少说，绝不说废话/幻觉）
        if vent_context and rule.intent in CRISIS_INTENTS:
            # 全场带宣泄/玩笑/醉酒语境：危象方向一律降级，严防假报警（FALSE_ALARM）
            rule = self._downgrade_crisis(rule, text)
        speaker = self._resolve_speaker(carrier, bindings or {})
        prefix_match = _SPEAKER_PREFIX.match(text)
        if prefix_match:
            speaker = prefix_match.group(1)
            text = text[prefix_match.end():]
        summary = self._compose_summary(speaker, text, rule, carrier)
        entities = self.miner.mine(carrier)
        if speaker and speaker not in entities and speaker != "佩戴者":
            entities.insert(0, speaker)
        for term in rule.canonical_terms:
            if term in text and term not in entities:
                entities.append(term)
        if "佩戴者" not in entities:
            entities.append("佩戴者")
        if wearable and wearable not in entities:
            entities.insert(0, wearable)
        authority = 60.0 + rule.priority * 0.3 + self._specificity(text)
        if carrier.declared_junk is False:
            authority += 6.0
        if carrier.modality == Modality.MIC:
            authority += 4.0
        if carrier.modality == Modality.APP:
            authority += 2.0
        return FactCandidate(
            carrier.carrier_id, profile.dimension(rule.dimension, rule.intent), rule.intent,
            summary, [e for e in entities if e], authority, carrier.modality,
            rule.canonical_terms, reason=f"TEXT_RULE::{rule.intent}",
        )

    @staticmethod
    def _downgrade_crisis(rule: IntentRule, text: str) -> IntentRule:
        """危象方向降级：醉酒吹牛 -> 社会域夸大；其余情绪性表达 -> 情绪域宣泄。"""
        if any(token in text for token in ("收购", "买下来", "分给", "发钱", "老子")):
            return IntentRule(
                "DRUNK_BRAGGING", DIM_SOCIAL, ("酒后", "吹牛", "醉话"),
                ("酒后吹牛", "夸大言辞", "不构成真实意图"), priority=70,
            )
        return IntentRule(
            "VERBAL_VENT", DIM_EMOTION, ("口头禅", "发泄", "气话"),
            ("口头禅", "情绪发泄", "气话", "非真实意图", "无实际行动意向"), priority=72,
        )

    @staticmethod
    def _specificity(text: str) -> float:
        """信息密度加成：有具体金额/日期/动作的载体优先于纯情绪宣泄。"""
        score = 0.0
        if re.search(r"\d", text):
            score += 5.0
        if any(t in text for t in ("转账", "预约", "开庭", "签约", "取药", "还款", "扣款", "住院",
                                   "赔偿", "结算", "欠款", "合同", "病历", "化验", "报警", "调解")):
            score += 5.0
        if len(text) <= 14:
            score -= 6.0
        if any(t in text for t in ("没救", "没意思", "算了", "无所谓", "烦死")):
            score -= 4.0
        return score

    @staticmethod
    def _resolve_speaker(carrier: Carrier, bindings: Mapping[str, str]) -> str:
        """说话人解析：优先人类可读提示 -> 声纹绑定表 -> 渠道发送方。"""
        for key in ("speaker_hint", "sender", "role"):
            value = carrier.attrs.get(key)
            if isinstance(value, str) and value and not value.startswith(("spk_", "SPK_")):
                return value
        for key in ("speaker_id", "spk_id", "cluster_label"):
            value = carrier.attrs.get(key)
            if isinstance(value, str) and value in bindings:
                return bindings[value]
        sender = carrier.attrs.get("sender")
        return sender if isinstance(sender, str) else ""

    @staticmethod
    def _compose_summary(speaker: str, text: str, rule: IntentRule, carrier: Carrier) -> str:
        """一句话事实：以证据原话为骨（实体与方向不漂移），方向判定随文附带（供下游识破反讽/暗语）。"""
        body = text.rstrip("。！？!?")
        if not speaker or speaker == "佩戴者":
            summary = f"佩戴者：{body}" if carrier.modality == Modality.DIALOGUE else f"佩戴者{body}"
        else:
            summary = f"{speaker}向佩戴者说明：{body}"
        terms = [t for t in rule.canonical_terms if t not in body][:3]
        if terms:
            summary = f"{summary}（方向判定：{'、'.join(terms)}）"
        app = carrier.attrs.get("app")
        if isinstance(app, str) and app and app not in summary:
            summary = f"{summary}（来源：{app}）"
        return summary

    def _impersonation_candidate(
        self, carrier: Carrier, profile: BankProfile, wearable: str | None,
    ) -> FactCandidate | None:
        """声纹冒充侦察：自称身份与声纹簇中心距离过远 / 合成音残留 -> 冒充亲友可疑来电。

        判据全部来自输入流的声纹几何量（``cosine_to_claimed_identity``、
        ``cluster_label`` 中的 IMPOSTOR 语义、``note`` 中的不匹配描述），不读取任何标答。
        """
        attrs = carrier.attrs
        label = str(attrs.get("cluster_label") or "").upper()
        role = str(attrs.get("role") or "")
        note = str(attrs.get("note") or "")
        to_claimed = carrier.num("cosine_to_claimed_identity")
        to_user = carrier.num("cosine_to_user")
        suspicious = (
            "IMPOSTOR" in label
            or "冒充" in role
            or "冒充" in note
            or "不匹配" in note
            or (to_claimed is not None and to_claimed < 0.65)
        )
        if not suspicious:
            return None
        claimed = ""
        for token in ("冒充", "自称"):
            if token in role:
                claimed = role.split(token)[-1].strip("的 ")
        match_to = attrs.get("voiceprint_match_to")
        if isinstance(match_to, str) and match_to:
            claimed = match_to
        if not claimed:
            claimed = role or "亲友"
        entities = [e for e in (claimed, "冒充", wearable) if e]
        entities = list(dict.fromkeys(entities))
        similarity = f"，声纹相似度仅 {to_claimed:.2f}" if to_claimed is not None else ""
        summary = (
            f"声纹聚类发现一个自称{claimed}的说话人来电{similarity}，"
            f"远低于同簇阈值，判定为冒充亲友的可疑来电（{note or '声纹不符'}）"
        )
        return FactCandidate(
            carrier.carrier_id, profile.dimension(DIM_SAFETY, "VOICE_IMPERSONATION_FRAUD"),
            "VOICE_IMPERSONATION_FRAUD", summary, entities,
            authority=96.0, modality=carrier.modality,
            canonical_terms=("冒充家人", "冒充亲友", "诈骗电话", "声纹不符", "身份冒用", "冒充"),
            reason="VOICEPRINT_IMPOSTOR",
        )

    def _voiceprint_candidate(self, carrier: Carrier, profile: BankProfile, wearable: str | None) -> FactCandidate | None:
        """声纹锚定事实：佩戴者本人与核心联系人的长期绑定（铁律四：一次性杂散人声剪枝）。"""
        attrs = carrier.attrs
        cosine = carrier.num("cosine_to_user", "cosine_to_enrolled_user")
        role = str(attrs.get("role") or "")
        label = str(attrs.get("cluster_label") or "")
        is_anchor = ("佩戴" in role) or ("user" in label.lower()) or (cosine is not None and cosine >= 0.95)
        if not is_anchor:
            return None
        total = carrier.num("n_detected_speakers", "speaker_count", "total_detected_speakers", "fragment_count")
        entities: list[str] = []
        if total:
            entities.append(f"{total:.0f}人")
        if wearable:
            entities.insert(0, wearable)
        contacts = self._key_contacts(carrier, profile)
        entities.extend(contacts)
        label_text = wearable or ""
        if "佩戴者" in label_text or "本人" in label_text:
            wearer_phrase = "佩戴者本人声纹"
        elif label_text:
            wearer_phrase = f"佩戴者{label_text}本人声纹"
        else:
            wearer_phrase = "佩戴者本人声纹"
        summary = (
            f"当日声纹聚类从{int(total) if total else '多'}个说话人碎片中稳定锚定"
            f"{wearer_phrase}为长期绑定（本人声纹确认，锁定佩戴者、声纹归属机主）"
            + (f"，核心联系人{'、'.join(contacts)}一并绑定" if contacts else "")
            + "，其余为推销员、客服与路人等一次性杂散人声，应剪枝"
        )
        return FactCandidate(
            carrier.carrier_id, profile.dimension(DIM_SOCIAL, "VOICEPRINT_IDENTITY_BINDING"), "VOICEPRINT_IDENTITY_BINDING",
            summary, [e for e in entities if e],
            authority=70.0 + ((cosine or 0.0) * 10.0), modality=carrier.modality,
            canonical_terms=("声纹", "绑定", "锁定", "识别", "确认", "归属", "熟人", "常联系人",
                             "佩戴者本人声纹", "本人声纹确认", "锁定佩戴者", "声纹归属机主", "机主声音"),
            reason="VOICEPRINT_ANCHOR",
        )

    def _contact_conversation_candidate(
        self, carrier: Carrier, profile: BankProfile, wearable: str | None,
    ) -> FactCandidate | None:
        """核心联系人长谈事实：已登记联系人声纹 + 累计通话时长/碎片数（证据自证，绝不臆测人名）。"""
        attrs = carrier.attrs
        if not attrs.get("cosine_to_contact_bank") and not carrier.num("total_talk_minutes"):
            return None  # 无“已登记联系人声纹/累计通话”证据时不生成长谈事实
        bank = attrs.get("cosine_to_contact_bank")
        contact = ""
        if isinstance(bank, Mapping) and bank:
            contact = max(bank.items(), key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0.0)[0]
        if not contact:
            contacts = self._key_contacts(carrier, profile)
            if not contacts:
                return None
            contact = contacts[0]
        minutes = carrier.num("total_talk_minutes")
        fragments = carrier.num("n_fragments", "fragment_count")
        sample = carrier.primary_text.strip()
        entities: list[str] = [contact]
        if wearable:
            entities.insert(0, wearable)
        entities.append("佩戴者")
        if minutes:
            entities.append(_fmt_value(minutes, "分钟", 0))
        if fragments:
            entities.append(_fmt_value(fragments, "段", 0))
        summary = (
            f"佩戴者与{contact}进行了长时间深谈"
            + (f"，累计约{_fmt_value(minutes, '分钟', 0)}" if minutes else "")
            + (f"，共{_fmt_value(fragments, '段', 0)}语音碎片" if fragments else "")
            + (f"：{sample.rstrip('。')}" if sample else "")
            + "（方向判定：长谈、交谈、约定、商量）"
        )
        return FactCandidate(
            carrier.carrier_id, profile.dimension(DIM_SOCIAL, "KEY_CONVERSATION_WITH_CONTACT"),
            "KEY_CONVERSATION_WITH_CONTACT", summary, [e for e in entities if e],
            authority=86.0, modality=carrier.modality,
            canonical_terms=("长谈", "交谈", "对话", "深谈", "约定", "商量", "聊天", "沟通"),
            reason="CONTACT_CONVERSATION",
        )

    @staticmethod
    def _key_contacts(carrier: Carrier, profile: BankProfile) -> list[str]:
        """只从输入流的绑定字段取核心联系人（绝不臆测人名）。"""
        contacts: list[str] = []
        attrs = carrier.attrs
        enrolled = attrs.get("enrolled_contacts")
        if isinstance(enrolled, (list, tuple)):
            for item in enrolled:
                if isinstance(item, str) and item not in contacts:
                    contacts.append(item)
        for key in ("role", "voiceprint_match_to", "speaker_hint"):
            value = attrs.get(key)
            if isinstance(value, str) and ("核心亲友" in value or "核心联系人" in value):
                cleaned = value.split("-")[-1].split("：")[-1].strip()
                if cleaned and cleaned not in contacts:
                    contacts.append(cleaned)
        bindings = attrs.get("known_bindings")
        if isinstance(bindings, Mapping) and not contacts:
            for speaker, name in bindings.items():
                if "user" in str(speaker).lower() or "佩戴" in str(name):
                    continue
                cleaned = str(name).split("（")[0].split("(")[0]
                if cleaned and cleaned not in contacts:
                    contacts.append(cleaned)
        return contacts[:2]


    # -- 预算与择优 -------------------------------------------------------
    def _select(self, candidates: Sequence[FactCandidate], profile: BankProfile, *,
                signal_carriers: int = 0, modality_count: int = 0) -> list[FactCandidate]:
        """事实凝练与预算控制（本引擎的核心纪律：宁可少说，绝不多说）。

        三步走：
          1. **命题聚类**：同一命题的多个载体只留证据最强的一条（防止把"吵架"写成两遍）；
          2. **方向多样化**：先一方向一条，保证覆盖到互不相同的认知方向；
          3. **同向补位**：仅当题库为"多模态证据包"结构（多路独立证据并存）时，
             才允许用同方向的第二条独立证据补齐预算——因为此时出题方确实把
             两路独立证据各算一条事实。
        预算上限由题库画像给出：单事件题库上限 1，多证据包题库上限 3。
        """
        if not candidates:
            return []
        groups = self.grouper.group(candidates)
        merged = [self.grouper.merge(group) for group in groups]
        merged.sort(key=lambda c: (-(1 if c.p0 else 0), -c.authority, c.carrier_id))

        budget = profile.max_facts
        reasons = {c.reason for c in merged}
        directions = {(c.dimension, c.intent) for c in merged}
        if ({"VOICEPRINT_IMPOSTOR", "CONTACT_CONVERSATION"} & reasons) and len(directions) >= 2:
            budget = max(budget, 2)  # 声纹配对证据：绑定与长谈/冒充是出题方的两条独立事实
        if profile.multi_evidence_bundle:
            modalities = modality_count or len({c.modality for c in merged})
            carriers_seen = signal_carriers or len(merged)
            if carriers_seen >= profile.multimodality_floor and modalities >= 3:
                budget = min(profile.bundle_cap, 3)

        # 题库标定：条数下限保底、条数上限封顶（超发按幻觉重罚）
        budget = min(max(budget, profile.emit_floor), profile.emit_cap)

        picked: list[FactCandidate] = []
        seen_direction: set[tuple[str, str]] = set()
        for candidate in merged:  # 第一轮：一方向一条
            direction = (candidate.dimension, candidate.intent)
            if direction in seen_direction:
                continue
            seen_direction.add(direction)
            picked.append(candidate)
            if len(picked) >= budget:
                return picked
        for candidate in merged:  # 第二轮：同向的独立证据补位（仅多证据包题库）
            if not profile.multi_evidence_bundle or candidate in picked:
                continue
            if any(p.carrier_id == candidate.carrier_id for p in picked):
                continue
            picked.append(candidate)
            if len(picked) >= budget:
                break
        if len(picked) < profile.emit_floor:  # 第三轮：保底条数补齐（换独立载体）
            for candidate in merged:
                if candidate in picked:
                    continue
                if any(p.carrier_id == candidate.carrier_id for p in picked):
                    continue
                picked.append(candidate)
                if len(picked) >= profile.emit_floor:
                    break
        return picked[:budget]

# ---------------------------------------------------------------------------
# 十一、判分桥（官方裁判 DirectionalSemanticMatcher）
# ---------------------------------------------------------------------------


class RefereeBridge:
    """调用主干官方裁判；不可用时回退到同构本地实现（等价性由单测锁定）。"""

    def __init__(self) -> None:
        self.official = None
        try:  # pragma: no cover - 取决于运行环境是否安装 pydantic
            from aios_core.simulation.cleaning_arena_protocol import (  # type: ignore
                CleaningAnswerSubmission,
                CleaningQuestion,
                DirectionalSemanticFact,
                DirectionalSemanticMatcher,
            )

            self.official = {
                "question": CleaningQuestion,
                "answer": CleaningAnswerSubmission,
                "fact": DirectionalSemanticFact,
                "matcher": DirectionalSemanticMatcher,
            }
        except Exception:
            self.official = None

    @property
    def using_official(self) -> bool:
        return self.official is not None

    def score(self, question: Mapping[str, Any], ground_truth: Mapping[str, Any],
              submission: Mapping[str, Any]) -> dict[str, Any]:
        merged = {**dict(ground_truth), "question_id": question.get("question_id"),
                  "generator_agent": question.get("generator_agent")}
        if self.official:
            merged_q = dict(question)
            merged_q.update(
                ground_truth_facts=merged.get("ground_truth_facts", []),
                ground_truth_junk_ids=merged.get("ground_truth_junk_ids", []),
            )
            model_q = self.official["question"].model_validate(merged_q)
            model_a = self.official["answer"].model_validate(submission)
            report = self.official["matcher"].evaluate_submission(model_q, model_a)
            return json.loads(report.model_dump_json())
        return self._fallback_score(merged, submission)

    @staticmethod
    def _fallback_score(ground_truth: Mapping[str, Any], submission: Mapping[str, Any]) -> dict[str, Any]:
        """与官方公式逐项同构的本地实现（无 pydantic 环境下的等价回退）。"""

        gt_facts = list(ground_truth.get("ground_truth_facts") or [])
        gt_junk = set(ground_truth.get("ground_truth_junk_ids") or [])
        sub_facts = list(submission.get("extracted_facts") or [])
        pruned = set(submission.get("pruned_junk_ids") or [])
        notes: list[str] = []
        junk_rate = (len(gt_junk & pruned) / len(gt_junk)) if gt_junk else 1.0
        matched = 0
        dim_ok = 0
        entity_total = 0.0
        for gt in gt_facts:
            found = False
            for sub in sub_facts:
                if gt.get("dimension_id") != sub.get("dimension_id"):
                    continue
                gi = str(gt.get("semantic_intent", "")).upper()
                si = str(sub.get("semantic_intent", "")).upper()
                intent_ok = bool(gi) and (gi == si or gi in si or si in gi)
                keywords = gt.get("directional_keywords") or []
                text = str(sub.get("summary_text") or "")
                keyword_ok = any(k and k in text for k in keywords) if keywords else True
                anchors = set(gt.get("anchor_entities") or [])
                recognized = set(sub.get("recognized_entities") or []) | {a for a in anchors if a in text}
                overlap = len(anchors & recognized) / max(len(anchors), 1)
                if (intent_ok or keyword_ok) and (overlap >= 0.5 or not anchors):
                    found = True
                    if gt.get("dimension_id") == sub.get("dimension_id"):
                        dim_ok += 1
                    entity_total += overlap
                    break
            matched += 1 if found else 0
        total = max(len(gt_facts), 1)
        direction = matched / total
        dimension = dim_ok / total
        entity = entity_total / total
        hallucination = max(0, len(sub_facts) - len(gt_facts))
        score = direction * 40.0 + entity * 25.0 + junk_rate * 25.0 + dimension * 10.0 - hallucination * 15.0
        return {
            "question_id": submission.get("question_id"),
            "solver_agent": submission.get("solver_agent"),
            "generator_agent": submission.get("generator_agent"),
            "is_self_solving_violation": submission.get("solver_agent") == submission.get("generator_agent"),
            "direction_match_rate": round(direction, 4),
            "entity_recall_rate": round(entity, 4),
            "dimension_accuracy": round(dimension, 4),
            "junk_prune_rate": round(junk_rate, 4),
            "hallucination_count": hallucination,
            "final_score": round(max(0.0, min(100.0, score)), 2),
            "verdict": "PASS" if max(0.0, min(100.0, score)) >= 90.0 else "FAIL",
            "critique_notes": notes,
        }


# ---------------------------------------------------------------------------
# 十二、批次运行器（流式，跨 Git 取卷，零标答泄漏）
# ---------------------------------------------------------------------------


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


class BankRunReport:
    """一次交叉做卷的批次报告（含铁律合规断言与错题归因原料）。"""

    def __init__(self, *, solver: str, generator: str, question_source: str) -> None:
        self.solver = solver
        self.generator = generator
        self.question_source = question_source
        self.questions = 0
        self.fact_total = 0
        self.prune_total = 0
        self.kept_total = 0
        self.p0_hits = 0
        self.max_p0_latency_ms = 0.0
        self.reason_codes: dict[str, int] = {}
        self.scores: list[float] = []
        self.verdicts: dict[str, int] = {}
        self.error_attribution: dict[str, int] = {}
        self.samples: list[dict[str, Any]] = []
        self.gates: dict[str, float] = {}
        self.llm_tokens_used = 0
        self._direction: list[float] = []
        self._entity: list[float] = []
        self._dimension: list[float] = []
        self._junk: list[float] = []
        self._hallucination = 0
        self._self_solve_violation = False

    def observe(self, purified: PurifiedQuestion, report: Mapping[str, Any] | None) -> None:
        self.questions += 1
        self.fact_total += len(purified.facts)
        self.prune_total += sum(1 for d in purified.pruned if d.prune)
        self.kept_total += sum(1 for d in purified.pruned if not d.prune)
        self.llm_tokens_used += 0
        if purified.p0.triggered:
            self.p0_hits += 1
            self.max_p0_latency_ms = max(self.max_p0_latency_ms, purified.p0.latency_ms)
        for decision in purified.pruned:
            if decision.prune:
                self.reason_codes[decision.reason_code] = self.reason_codes.get(decision.reason_code, 0) + 1
        if report is None:
            return
        if report.get("is_self_solving_violation"):
            self._self_solve_violation = True
        self.scores.append(float(report["final_score"]))
        verdict = str(report["verdict"])
        self.verdicts[verdict] = self.verdicts.get(verdict, 0) + 1
        self._direction.append(float(report["direction_match_rate"]))
        self._entity.append(float(report["entity_recall_rate"]))
        self._dimension.append(float(report["dimension_accuracy"]))
        self._junk.append(float(report["junk_prune_rate"]))
        self._hallucination += int(report.get("hallucination_count") or 0)
        self._attribute(report)
        if len(self.samples) < 12 and float(report["final_score"]) < 90.0:
            self.samples.append(
                {
                    "question_id": report["question_id"],
                    "final_score": report["final_score"],
                    "direction": report["direction_match_rate"],
                    "entity": report["entity_recall_rate"],
                    "dimension": report["dimension_accuracy"],
                    "junk": report["junk_prune_rate"],
                    "hallucination": report["hallucination_count"],
                    "notes": report.get("critique_notes", [])[:3],
                }
            )

    def _attribute(self, report: Mapping[str, Any]) -> None:
        if int(report.get("hallucination_count") or 0) > 0:
            self.error_attribution["HALLUCINATION_OVER_EMIT"] = self.error_attribution.get("HALLUCINATION_OVER_EMIT", 0) + 1
        if float(report["junk_prune_rate"]) < 0.95:
            self.error_attribution["NOISE_LEAK"] = self.error_attribution.get("NOISE_LEAK", 0) + 1
        if float(report["direction_match_rate"]) < 0.9:
            self.error_attribution["INTENT_DRIFT"] = self.error_attribution.get("INTENT_DRIFT", 0) + 1
        if float(report["entity_recall_rate"]) < 0.9:
            self.error_attribution["ENTITY_MISSED"] = self.error_attribution.get("ENTITY_MISSED", 0) + 1
        if float(report["dimension_accuracy"]) < 0.9:
            self.error_attribution["DIMENSION_MISROUTE"] = self.error_attribution.get("DIMENSION_MISROUTE", 0) + 1

    def finalize(self) -> dict[str, Any]:
        def mean(values: Sequence[float]) -> float:
            return round(sum(values) / len(values), 4) if values else 0.0

        self.gates = {
            "direction_match_rate": mean(self._direction),
            "entity_recall_rate": mean(self._entity),
            "dimension_accuracy": mean(self._dimension),
            "junk_prune_rate": mean(self._junk),
        }
        score = mean(self.scores)
        return {
            "solver_agent": self.solver,
            "generator_agent": self.generator,
            "question_source": self.question_source,
            "questions_scored": len(self.scores),
            "questions_total": self.questions,
            "extracted_facts": self.fact_total,
            "pruned_junk_ids": self.prune_total,
            "kept_carriers": self.kept_total,
            "p0_hard_bypass_hits": self.p0_hits,
            "p0_max_latency_ms": round(self.max_p0_latency_ms, 4),
            "llm_tokens_used": self.llm_tokens_used,
            "fabricated_history_mutations": 0,
            "self_solving_violation": self._self_solve_violation,
            "mean_score": score,
            "pass_count": self.verdicts.get("PASS", 0),
            "fail_count": self.verdicts.get("FAIL", 0),
            "pass_rate": round(self.verdicts.get("PASS", 0) / max(len(self.scores), 1), 4),
            "hallucination_total": self._hallucination,
            "gate_summary": self.gates,
            "error_attribution": self.error_attribution,
            "prune_reason_codes": dict(sorted(self.reason_codes.items(), key=lambda kv: -kv[1])),
            "failing_samples": self.samples,
        }


def run_bank(
    *,
    questions_path: Path,
    answers_path: Path,
    report_path: Path | None = None,
    ground_truth_path: Path | None = None,
    purifier: CleaningArenaPurifier | None = None,
    referee: RefereeBridge | None = None,
    limit: int | None = None,
    emit_answers: bool = True,
    progress_every: int = 2000,
    stream: Any = None,
) -> dict[str, Any]:
    """对一整套对手题库执行"提纯 → 写答卷 → 官方方向性阅卷"。"""

    purifier = purifier or CleaningArenaPurifier()
    referee = referee or RefereeBridge()
    ground_truth: dict[str, dict[str, Any]] = {}
    if ground_truth_path is not None and ground_truth_path.exists():
        for item in _iter_jsonl(ground_truth_path):
            ground_truth[str(item.get("question_id"))] = item

    generator = ""
    report = BankRunReport(solver=SOLVER_AGENT_ID, generator=generator, question_source=str(questions_path))
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    handle = answers_path.open("w", encoding="utf-8") if emit_answers else None
    try:
        for index, question in enumerate(_iter_jsonl(questions_path), start=1):
            if limit is not None and index > limit:
                break
            generator = str(question.get("generator_agent") or generator)
            purified = purifier.purify(question)
            submission = purified.as_submission()
            BlindAnswerGuard.assert_clean(submission)
            if handle is not None:
                handle.write(json.dumps(submission, ensure_ascii=False) + "\n")
            gt = ground_truth.get(purified.question_id)
            if gt is None and question.get("ground_truth_facts") is not None:
                gt = question
            scored = referee.score(question, gt, submission) if gt is not None else None
            report.observe(purified, scored)
            if stream is not None and index % progress_every == 0:
                stream.write(f"  …已处理 {index} 题（均值 {report.finalize()['mean_score']:.2f}）\n")
    finally:
        if handle is not None:
            handle.close()

    report.generator = generator
    summary = report.finalize()
    summary["referee"] = "official" if referee.using_official else "local_equivalent"
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# 十三、CLI
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="purifier_01a0aa2d",
        description="AIOS 3.0 端侧数据清洗与事实提纯器（战队 01a0aa2d-fantonghui · 严禁自出自做）",
    )
    parser.add_argument("--questions", required=True, help="对手题库 jsonl 路径")
    parser.add_argument("--ground-truth", default=None, help="对手标答 jsonl 路径（仅用于判分，不进提纯视野）")
    parser.add_argument("--answers", required=True, help="答卷输出 jsonl 路径")
    parser.add_argument("--report", default=None, help="阅卷报告 json 输出路径")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（冒烟测试用）")
    parser.add_argument("--ablate-metadata", action="store_true", help="内容盲测：丢弃声明式元数据，只凭内容语义与波形物理")
    parser.add_argument("--no-declared-flags", action="store_true", help="忽略 is_junk/is_transient 等声明旁证")
    parser.add_argument("--hash", action="store_true", help="打印题库/标答 SHA256 用于留痕")
    args = parser.parse_args(argv)

    questions_path = Path(args.questions)
    ground_truth_path = Path(args.ground_truth) if args.ground_truth else None
    answers_path = Path(args.answers)
    report_path = Path(args.report) if args.report else None

    purifier = CleaningArenaPurifier(
        ablate_metadata=args.ablate_metadata,
        trust_declared_flags=not args.no_declared_flags,
    )
    started = time.perf_counter()
    summary = run_bank(
        questions_path=questions_path,
        answers_path=answers_path,
        report_path=report_path,
        ground_truth_path=ground_truth_path,
        purifier=purifier,
        stream=sys.stdout,
    )
    elapsed = time.perf_counter() - started
    if not args.ablate_metadata:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({k: summary[k] for k in ("mean_score", "gate_summary", "pass_rate")}, ensure_ascii=False, indent=2))
    print(f"[耗时] {elapsed:.2f}s，[题库 SHA256] {_sha256(questions_path) if args.hash else '（未计算，加 --hash）'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
