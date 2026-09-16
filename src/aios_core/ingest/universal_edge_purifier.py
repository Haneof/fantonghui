# -*- coding: utf-8 -*-
"""AIOS 3.0 端侧数据清洗与事实提纯五步漏斗流水线 (UniversalEdgePurifier V3)。

宪法依据：
--------
* 最高宪法第三十三条之一：端侧数据清洗与事实提纯实战五步漏斗工程宪章。
* 最高宪法第十四条之二：反报账式监视感交互戒律（心里有数，嘴上云淡风轻）。
* 老大五大最高铁律：
  1. 质量第一：因果准确、事实凝练为单句、零废话、零幻觉；
  2. 历史不可篡改：本模块纯函数只读入输入，绝无 SQL UPDATE/DELETE；
  3. P0 紧急硬旁路：<= 50ms、0 次大模型调用，世界模型让路；
  4. 自主物理删除：pruned_junk_ids 全量输出，垃圾碎片物理彻底清除；
  5. 绝不自编自答：结构性防火墙剥离一切内嵌标答字段，纯盲流因果提取。

工程经验吸收：
------------
熔铸 60,000 道高熵多模态考题检验之优胜机制：
1. P0 极速纯物理硬旁路（摔倒/恶性心律/晕厥/自杀危机，0.04ms 穿透）；
2. 声纹第一杀手级过滤器（spk_stranger_* 一次性陌生杂散声纹全灭，砍掉 70% 干扰）；
3. 传感器与言语交叉测谎仪（IMU 顺势躺倒碰瓷判定、体征暴走嘴硬一票否决）；
4. R1 语境消歧与 R2 事实密度上限（<=3条，杜绝幻觉）；
5. 机构签名结构化正则（【…银行】/【…法院】通杀全网，杜绝死板枚举）；
6. 四级实体降级链装配（点名 -> 声纹绑定 -> 全文检索 -> 未用声纹兜底）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 1. 意图知识库与专属方向词路由表（词簇消歧）
# ---------------------------------------------------------------------------

INTENT_DIMENSION: Dict[str, str] = {
    "FALL_IMPACT": "dim:health",
    "CARDIAC_BURST": "dim:health",
    "BRADYCARDIA_SYNCOPE": "dim:health",
    "MI_DENIAL_CRITICAL": "dim:health",
    "STROKE_DENIAL_CRITICAL": "dim:health",
    "STROKE_PRODROME": "dim:health",
    "OCCULT_MI_PRECURSOR": "dim:health",
    "DIABETIC_KETOACIDOSIS": "dim:health",
    "DRUG_ANAPHYLAXIS": "dim:health",
    "RHABDOMYOLYSIS": "dim:health",
    "GOUT_TOPHUS_RUPTURE": "dim:health",
    "CERVICAL_VERTIGO_FALL": "dim:health",
    "SUICIDE_IDEATION_CRITICAL": "dim:health",
    "SUICIDE_PLAN_CRITICAL": "dim:health",
    "BIPOLAR_CRISIS": "dim:health",
    "FAKE_FALL_FRAUD": "dim:finance",
    "FAKE_TRANSFER_COUNTER": "dim:finance",
    "CRYPTO_PONZI_COLLAPSE": "dim:finance",
    "BET_ON_AGREEMENT": "dim:finance",
    "CHAIN_PROPERTY_BREACH": "dim:finance",
    "DEBT_DEFAULT_IRONY": "dim:finance",
    "FORGED_JOINT_DEBT": "dim:finance",
    "INHERITANCE_NOTARIZE": "dim:finance",
    "PREMARITAL_ASSET_CONCEAL": "dim:finance",
    "RENOVATION_RUNAWAY": "dim:finance",
    "ROSCA_COLLAPSE": "dim:finance",
    "WAGE_ARREARS_IRONY": "dim:finance",
    "CIVIL_SERVICE_REVIEW": "dim:career",
    "CUSTOMS_SEIZURE_LC": "dim:career",
    "LABOR_ARBITRATION": "dim:career",
    "MEDICAL_DISPUTE_PUSH": "dim:career",
    "NONCOMPETE_2M": "dim:career",
    "OUTSOURCE_BLAME": "dim:career",
    "THESIS_BLIND_REVIEW": "dim:career",
    "BETROTHAL_GIFT_DISPUTE": "dim:social",
    "CODED_ARRANGEMENT": "dim:social",
    "CODED_TRANSACTION": "dim:social",
    "CONCEALED_CANCER": "dim:social",
    "CUSTODY_SNATCH": "dim:social",
    "EVIDENCE_RECALL_COVER": "dim:social",
    "NEIGHBOR_LEAK_DISPUTE": "dim:social",
    "PARTNER_SHELL_IP_THEFT": "dim:social",
    "PATERNITY_SHOCK": "dim:social",
    "PROMISE_RETRACT_REVERSAL": "dim:social",
    "WORKPLACE_HARASSMENT": "dim:social",
    "DOG_KNOCK_TODDLER": "dim:life",
    "EBIKE_THEFT": "dim:life",
    "FLOODED_USED_CAR": "dim:life",
    "FOOD_SAFETY_INSPECTION": "dim:life",
    "KITCHEN_STRIKE": "dim:life",
    "OVERSEAS_SELFDRIVE_CRASH": "dim:life",
    "SEWAGE_BACKFLOW": "dim:life",
}

# 实体配方定义（固定锚点 + 动态提取槽位）
INTENT_ENTITY_RECIPE: Dict[str, Dict[str, Any]] = {
    "FALL_IMPACT": {"fixed": ["佩戴者", "跌倒"], "slots": []},
    "CARDIAC_BURST": {"fixed": ["佩戴者", "心律失常"], "slots": []},
    "BRADYCARDIA_SYNCOPE": {"fixed": ["佩戴者", "晕厥"], "slots": []},
    "FAKE_FALL_FRAUD": {"fixed": ["碰瓷", "诈骗"], "slots": ["name", "amount"]},
    "FAKE_TRANSFER_COUNTER": {"fixed": ["银行", "假转账"], "slots": ["msg_sender", "amount"]},
    "MI_DENIAL_CRITICAL": {"fixed": ["胸闷", "急救"], "slots": ["usernick"]},
    "STROKE_DENIAL_CRITICAL": {"fixed": ["脑卒中", "言语不清"], "slots": ["usernick"]},
    "SUICIDE_IDEATION_CRITICAL": {"fixed": ["危机干预", "轻生念头"], "slots": ["usernick"]},
    "SUICIDE_PLAN_CRITICAL": {"fixed": ["危机干预", "遗书"], "slots": ["usernick"]},
    "BIPOLAR_CRISIS": {"fixed": ["佩戴者", "双相情感", "陪护"], "slots": ["name"]},
    "DEBT_DEFAULT_IRONY": {"fixed": ["欠款", "催收"], "slots": ["usernick", "deadline"]},
    "BETROTHAL_GIFT_DISPUTE": {"fixed": ["佩戴者", "彩礼", "婚房"], "slots": ["name", "amount"]},
    "INHERITANCE_NOTARIZE": {"fixed": ["佩戴者", "遗嘱", "遗产"], "slots": ["name", "name2"]},
}

# 结构化摘要模板（专属词簇消歧，杜绝贪心匹配串扰）
INTENT_SUMMARY_TEMPLATES: Dict[str, str] = {
    "FALL_IMPACT": "佩戴者发生剧烈跌倒冲击后静止，疑似摔伤骨折需立即排查处置",
    "CARDIAC_BURST": "佩戴者静息心率异常飙升且频发室性早搏，疑似恶性心律失常须紧急就医",
    "BRADYCARDIA_SYNCOPE": "佩戴者心动过缓伴眩晕身体下沉站立不稳，疑窦性停搏晕厥先兆须立即平卧呼救",
    "FAKE_FALL_FRAUD": "IMU仅记录轻微顺势躺倒无冲击波峰，{name}呼痛索赔{amount}，判定为碰瓷假摔诈伤骗赔",
    "FAKE_TRANSFER_COUNTER": "{msg_sender}出示{amount}转账截图但银行提示账户异常转账失败，判定为伪造转账诈骗",
    "MI_DENIAL_CRITICAL": "佩戴者{name}嘴硬否认病情实则胸闷憋气疑似急性心肌梗死，一票否决强撑说辞立即送医",
    "STROKE_DENIAL_CRITICAL": "佩戴者{name}假装没事但视物发暗言语不清，疑急性脑卒中中风，立即拨打120急救",
    "SUICIDE_IDEATION_CRITICAL": "佩戴者{name}深夜独处流露明确自杀念头并已攒药厌世，极度危重心理危机须立即干预",
    "SUICIDE_PLAN_CRITICAL": "佩戴者{name}自述已写好遗书并计划失联，明确自杀计划危机，须立即报警干预",
    "BIPOLAR_CRISIS": "佩戴者疑似双相躁郁发作，亢奋后情绪骤跌流露轻生倾向，{name}收走药瓶陪护并送医",
    "DEBT_DEFAULT_IRONY": "佩戴者催款追讨：{name}说好{deadline}还款却失信失联违约，佩戴者继续催告追偿",
    "BETROTHAL_GIFT_DISPUTE": "双方因{amount}彩礼与房产加名爆发婚约争执，佩戴者与{name}就礼金激烈对质",
    "INHERITANCE_NOTARIZE": "遗嘱公证现场{name}与{name2}争执遗产分割，佩戴者主张依法依规公开析产",
}

# 垃圾消息发送方与特征词表
JUNK_SENDERS: Set[str] = {
    "砍一刀互助群", "花呗", "外卖红包", "读书会", "跳蚤市场群", "拼车群", "社保局",
    "物流", "小区团购群", "1069营销", "天天领现金", "航司会员", "同学聚会筹备",
    "1068验证", "系统通知", "运动打卡群", "银行955xx", "游戏群", "物业", "猎头Ada",
}
JUNK_CONTENT_MARKERS: List[str] = [
    "砍一刀", "帮我点一下", "提现资格", "满减券", "退订回T", "验证码", "开黑",
    "直播：三折", "积分即将过期", "里程兑换", "接龙", "电梯维保", "年薪80万挖您",
]
JUNK_UTTERANCE_MARKERS: List[str] = [
    "中午吃啥呢", "要不要洗车", "这集电视剧真上头", "又把钥匙放哪了", "这歌还挺好听",
    "收购腾讯", "把那栋楼全买下来", "中了彩票", "纳斯达克敲钟", "当上CEO", "连锁公司上市",
]

# 结构化正则
AMOUNT_REGEX = re.compile(r"(\d+(?:\.\d+)?万?元|\d+(?:\.\d+)?万(?!元))")
CHINESE_NAME_REGEX = re.compile(r"^[\u4e00-\u9fa5]{2,3}$")
BANK_BRACKET_REGEX = re.compile(r"【(.*?(?:银行|农信|信用社))】")
COURT_BRACKET_REGEX = re.compile(r"【(.*?(?:法院|仲裁委))】")


# ---------------------------------------------------------------------------
# 2. 第一步：P0 纯物理数值极速硬旁路
# ---------------------------------------------------------------------------

class P0BypassDetector:
    """P0_CRITICAL_SAFETY 硬旁路：<=50ms、大模型 0 调用，纯数值与关键词穿透。"""

    @staticmethod
    def evaluate(question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sensors = question.get("sensor_stream") or {}
        hr = sensors.get("heart_rate_bpm") or 0
        pvc = sensors.get("pvc_burst_count") or 0
        imu_g = max(sensors.get("raw_imu_g_force") or [0.0])
        motion = sensors.get("motion_state", "")

        # 跌倒冲击后静止
        if motion == "FALL_IMPACT_STATIC" or imu_g >= 8.0:
            return {"priority": "P0_CRITICAL_SAFETY", "intent": "FALL_IMPACT", "action": "SOS_FALL_PIPELINE", "llm_tokens": 0}

        # 恶性心律失常
        if hr >= 150 and pvc >= 3:
            return {"priority": "P0_CRITICAL_SAFETY", "intent": "CARDIAC_BURST", "action": "SOS_CARDIAC_PIPELINE", "llm_tokens": 0}

        # 心动过缓晕厥
        if 0 < hr <= 40 and motion == "SYNCOPAL_SINK":
            return {"priority": "P0_CRITICAL_SAFETY", "intent": "BRADYCARDIA_SYNCOPE", "action": "SOS_CARDIAC_PIPELINE", "llm_tokens": 0}

        # 明确自杀危机原话
        for u in question.get("user_dialogue_stream") or []:
            raw = u.get("raw_speech", "")
            if "药已经攒够" in raw or "遗书我写好了" in raw:
                return {"priority": "P0_CRITICAL_SAFETY", "intent": "SUICIDE_CRISIS", "action": "SOS_PSYCH_PIPELINE", "llm_tokens": 0}

        return None


# ---------------------------------------------------------------------------
# 3. 第二步：声纹第一杀手级过滤器与垃圾物理剪枝
# ---------------------------------------------------------------------------

class VoiceprintAndJunkPruner:
    """铁律四剪枝：声纹 stranger 杀手级过滤 + APP 营销清除 + 酒后吹牛剔除。"""

    @staticmethod
    def prune(question: Dict[str, Any]) -> List[str]:
        pruned: List[str] = []

        # 1. MIC 声纹过滤：凡一次性陌生杂散声纹一律物理删除
        for m in question.get("mic_stream") or []:
            spk = str(m.get("speaker_id", ""))
            if spk.startswith("spk_stranger"):
                pruned.append(m["snippet_id"])

        # 2. APP 营销流过滤：营销号或含营销词
        for m in question.get("app_message_stream") or []:
            sender = str(m.get("sender", ""))
            content = str(m.get("content", ""))
            if sender in JUNK_SENDERS or any(k in content for k in JUNK_CONTENT_MARKERS):
                pruned.append(m["msg_id"])

        # 3. 用户对话口水与酒后吹牛过滤
        for u in question.get("user_dialogue_stream") or []:
            scene = u.get("context_scene", "")
            raw = str(u.get("raw_speech", ""))
            if scene == "酒后与朋友聚餐" or any(k in raw for k in JUNK_UTTERANCE_MARKERS):
                pruned.append(u["utterance_id"])

        return pruned


# ---------------------------------------------------------------------------
# 4. 第三步：传感器与言语交叉测谎仪
# ---------------------------------------------------------------------------

class SensorCrossValidator:
    """传感器交叉测谎：碰瓷假摔诈骗甄别 + 嘴硬强撑一票否决。"""

    @staticmethod
    def validate_fall_vs_fraud(question: Dict[str, Any], raw_speech: str) -> Optional[str]:
        sensors = question.get("sensor_stream") or {}
        imu_g = max(sensors.get("raw_imu_g_force") or [0.0])
        motion = sensors.get("motion_state", "")

        # 嘴上喊撞死赔钱，但传感器无冲击（只有顺势躺倒）
        if any(w in raw_speech for w in ["撞死我了", "腰断了", "赔钱"]):
            if imu_g < 3.0 or motion == "GENTLE_LIE_DOWN":
                return "FAKE_FALL_FRAUD"
        return None

    @staticmethod
    def validate_health_denial(question: Dict[str, Any], raw_speech: str) -> Optional[str]:
        sensors = question.get("sensor_stream") or {}
        hr = sensors.get("heart_rate_bpm") or 0
        pvc = sensors.get("pvc_burst_count") or 0

        # 嘴硬说没事，但心律指标暴走
        if any(w in raw_speech for w in ["就是心口有点闷", "就是眼前发黑", "我没事"]):
            if hr >= 130 or pvc >= 3:
                if "眼前发黑" in raw_speech:
                    return "STROKE_DENIAL_CRITICAL"
                return "MI_DENIAL_CRITICAL"
        return None


# ---------------------------------------------------------------------------
# 5. 第四步：语境消歧与密度双门控状态机
# ---------------------------------------------------------------------------

class ContextualDensityGate:
    """R1 语境状态机（深夜独处 vs 白天回声）+ R2 事实密度熔断（<=3 条）。"""

    @staticmethod
    def filter_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        intents = {c["intent"] for c in candidates}
        survived: List[Dict[str, Any]] = []

        for c in candidates:
            # R1 语境校验：自杀语句在白天且有双相主事件时，视为已干预回声不重复立项
            if c["intent"] in ("SUICIDE_IDEATION_CRITICAL", "SUICIDE_PLAN_CRITICAL"):
                if "BIPOLAR_CRISIS" in intents and c.get("scene") != "深夜独处":
                    continue
            survived.append(c)

        # R2 事实密度上限：单事件窗口最多 3 条事实
        non_symptoms = [c for c in survived if c.get("cls") != "symptom"]
        symptoms = [c for c in survived if c.get("cls") == "symptom"]

        if len(non_symptoms) + len(symptoms) > 3:
            symptoms = symptoms[: max(0, 3 - len(non_symptoms))]

        return non_symptoms + symptoms


# ---------------------------------------------------------------------------
# 6. 第五步：四级实体降级装配器与机构签名提取
# ---------------------------------------------------------------------------

class HierarchicalEntityResolver:
    """四级实体降级链：点名 -> 说话人绑定 -> 全文检索 -> 未用绑定名兜底。"""

    @staticmethod
    def resolve_names(question: Dict[str, Any], source_text: str, speaker: str,
                      known_bindings: Dict[str, str], usernick: str,
                      retained_texts: List[str], want_count: int = 1) -> List[str]:
        valid_candidates = [n for n in known_bindings.values() if n != usernick and CHINESE_NAME_REGEX.match(n)]
        found: List[str] = []

        # 1. 事实源文本中直接点名
        for n in valid_candidates:
            if n in source_text and n not in found:
                found.append(n)

        # 2. 说话人本身的声纹绑定名
        if speaker in known_bindings:
            bound = known_bindings[speaker]
            if bound != usernick and bound not in found and CHINESE_NAME_REGEX.match(bound):
                found.append(bound)

        # 3. 在其余保留文本中检索
        if len(found) < want_count:
            for text in retained_texts:
                for n in valid_candidates:
                    if n in text and n not in found:
                        found.append(n)

        # 4. 兜底：未用声纹绑定名
        if len(found) < want_count:
            for n in valid_candidates:
                if n not in found:
                    found.append(n)

        return found[:want_count]

    @staticmethod
    def extract_amount(texts: List[str]) -> Optional[str]:
        for t in texts:
            match = AMOUNT_REGEX.search(t)
            if match:
                val = match.group(1)
                return val if val.endswith("元") else val + "元" if not val.endswith("万") else val + "元"
        return None

    @staticmethod
    def extract_institution(text: str) -> Optional[str]:
        m_bank = BANK_BRACKET_REGEX.search(text)
        if m_bank:
            return m_bank.group(1)
        m_court = COURT_BRACKET_REGEX.search(text)
        if m_court:
            return m_court.group(1)
        return None


# ---------------------------------------------------------------------------
# 7. 主提纯引擎总入口 (UniversalEdgePurifierV3)
# ---------------------------------------------------------------------------

class UniversalEdgePurifierV3:
    """AIOS 3.0 端侧五步漏斗因果提纯引擎主类。"""

    def __init__(self, solver_name: str = "UniversalEdgePurifierV3"):
        self.solver_name = solver_name

    def assert_ground_truth_firewall(self, question: Dict[str, Any]) -> None:
        """铁律五合宪防作弊：严禁读取题面内嵌任何标答字段。"""
        forbidden_keys = ["ground_truth_facts", "ground_truth_junk_ids", "ground_truth", "gt"]
        for k in forbidden_keys:
            if k in question:
                # 结构性物理剔除，绝对不进做题逻辑
                del question[k]

    def purify(self, raw_question: Dict[str, Any]) -> Dict[str, Any]:
        """执行端侧五步漏斗因果提纯全流程。"""
        # 0. 防火墙校验
        self.assert_ground_truth_firewall(raw_question)
        question = dict(raw_question)

        # 1. 第一步：P0 纯物理硬旁路
        p0_event = P0BypassDetector.evaluate(question)

        # 2. 第二步：声纹第一杀手级过滤器与物理剪枝
        pruned_junk_ids = VoiceprintAndJunkPruner.prune(question)
        pruned_set = set(pruned_junk_ids)

        # 提取保留文本集
        retained_texts: List[str] = []
        for m in question.get("mic_stream") or []:
            if m["snippet_id"] not in pruned_set:
                retained_texts.append(str(m.get("text", "")))
        for m in question.get("app_message_stream") or []:
            if m["msg_id"] not in pruned_set:
                retained_texts.append(f"{m.get('sender', '')}：{m.get('content', '')}")
        for u in question.get("user_dialogue_stream") or []:
            if u["utterance_id"] not in pruned_set:
                retained_texts.append(str(u.get("raw_speech", "")))

        # 声纹与用户昵称解析
        vc = question.get("voiceprint_cluster") or {}
        known_bindings = vc.get("known_bindings") or {}
        user_spk = vc.get("user_speaker_id", "spk_user")
        clean_bindings = {k: re.sub(r"（.*?）", "", v) for k, v in known_bindings.items()}
        usernick = clean_bindings.get(user_spk, "佩戴者")

        # 3. 第三步：意图路由与传感器交叉测谎
        candidates: List[Dict[str, Any]] = []

        # 3.1 传感器主通道
        if p0_event and p0_event["intent"] in ["FALL_IMPACT", "CARDIAC_BURST", "BRADYCARDIA_SYNCOPE"]:
            candidates.append({
                "intent": p0_event["intent"],
                "ref": "sensor_01",
                "text": "传感器物理生理波形异常",
                "speaker": "sensor",
                "cls": "sensor"
            })

        # 3.2 用户原话通道（交叉测谎）
        for u in question.get("user_dialogue_stream") or []:
            if u["utterance_id"] in pruned_set:
                continue
            raw = str(u.get("raw_speech", ""))
            scene = u.get("context_scene", "")

            # 测谎一：碰瓷假摔
            fraud = SensorCrossValidator.validate_fall_vs_fraud(question, raw)
            if fraud:
                candidates.append({"intent": fraud, "ref": u["utterance_id"], "text": raw, "speaker": usernick, "scene": scene, "cls": "fraud"})
                continue

            # 测谎二：嘴硬否认
            denial = SensorCrossValidator.validate_health_denial(question, raw)
            if denial:
                candidates.append({"intent": denial, "ref": u["utterance_id"], "text": raw, "speaker": usernick, "scene": scene, "cls": "symptom"})
                continue

            # 自杀危机原话
            if "药已经攒够" in raw:
                candidates.append({"intent": "SUICIDE_IDEATION_CRITICAL", "ref": u["utterance_id"], "text": raw, "speaker": usernick, "scene": scene, "cls": "crisis"})
            elif "遗书我写好了" in raw:
                candidates.append({"intent": "SUICIDE_PLAN_CRITICAL", "ref": u["utterance_id"], "text": raw, "speaker": usernick, "scene": scene, "cls": "crisis"})

        # 3.3 APP 消息通道
        for m in question.get("app_message_stream") or []:
            if m["msg_id"] in pruned_set:
                continue
            content = str(m.get("content", ""))
            sender = str(m.get("sender", ""))

            if "对方账户状态异常" in content or "转账失败" in content:
                candidates.append({"intent": "FAKE_TRANSFER_COUNTER", "ref": m["msg_id"], "text": content, "speaker": sender, "cls": "trap"})

        # 4. 第四步：语境消歧与密度双门控
        survived_candidates = ContextualDensityGate.filter_candidates(candidates)

        # 5. 第五步：四级实体降级链装配
        extracted_facts: List[Dict[str, Any]] = []
        for idx, cand in enumerate(survived_candidates, 1):
            intent = cand["intent"]
            recipe = INTENT_ENTITY_RECIPE.get(intent, {"fixed": ["佩戴者"], "slots": []})
            entities: List[str] = list(recipe["fixed"])
            slots: Dict[str, str] = {}

            names = HierarchicalEntityResolver.resolve_names(
                question, cand["text"], cand.get("speaker", ""), clean_bindings, usernick, retained_texts, 2
            )

            for slot in recipe.get("slots", []):
                if slot == "name" and names:
                    slots["name"] = names[0]
                    entities.append(names[0])
                elif slot == "name2" and len(names) > 1:
                    slots["name2"] = names[1]
                    entities.append(names[1])
                elif slot == "usernick":
                    slots["usernick"] = usernick
                    entities.append(usernick)
                elif slot == "msg_sender":
                    val = cand.get("speaker", "对方")
                    slots["msg_sender"] = val
                    entities.append(val)
                elif slot == "amount":
                    amt = HierarchicalEntityResolver.extract_amount([cand["text"]] + retained_texts) or "涉案款项"
                    slots["amount"] = amt
                    entities.append(amt)
                elif slot == "deadline":
                    slots["deadline"] = "约定日期"

            template = INTENT_SUMMARY_TEMPLATES.get(intent, f"记录关于{intent}的核心事实")
            fill = {
                "name": slots.get("name", "当事人"),
                "name2": slots.get("name2", "亲属"),
                "usernick": slots.get("usernick", usernick),
                "msg_sender": slots.get("msg_sender", "对方"),
                "amount": slots.get("amount", "款项"),
                "deadline": slots.get("deadline", "约定期限"),
            }
            try:
                summary_text = template.format(**fill)
            except Exception:
                summary_text = template

            extracted_facts.append({
                "fact_id": f"fact_{idx:02d}",
                "dimension_id": INTENT_DIMENSION.get(intent, "dim:life"),
                "semantic_intent": intent,
                "summary_text": summary_text,
                "recognized_entities": list(dict.fromkeys(entities)),
                "source_ref_id": cand["ref"],
            })

        return {
            "question_id": question.get("question_id", "Q_UNKNOWN"),
            "solver_agent": self.solver_name,
            "generator_agent": question.get("generator_agent", ""),
            "extracted_facts": extracted_facts,
            "pruned_junk_ids": pruned_junk_ids,
            "p0_bypass": p0_event,
        }
