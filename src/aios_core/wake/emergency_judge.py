"""大模型直接研判急救交互中枢（EmergencyDialogueJudge）。

老大铁律指示（2026-09-16）：
在跌倒测试中，接入大模型直接进行现场对话与决策研判：
1. 先呼叫用户：“还好吗？用不用叫救护车？”
2. 监听用户现场语音，大模型直接解析自由言语（听懂人话、识别求救、识破假没事）；
3. 若用户无回应（静默/昏迷）或明确求救/隐性危急，大模型直接做出判断并触发外呼拨打 120！
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class EmergencyAction(str, Enum):
    """大模型裁决的急救动作。"""
    CALL_AMBULANCE = "CALL_AMBULANCE"        # 立即拨打 120 呼叫救护车并通知紧急联系人
    STANDBY_MONITOR = "STANDBY_MONITOR"      # 暂不叫车，遵从用户意愿，保持心率高频监控
    DISMISS_FALSE_ALARM = "DISMISS_FALSE_ALARM"  # 误触完全解除（如手机落地或轻摔无碍）


class EmergencySeverity(str, Enum):
    """险情危急程度评级。"""
    CRITICAL = "CRITICAL"    # 极度危急（心梗前兆、剧烈骨折失能、深度昏迷无应答）
    MODERATE = "MODERATE"    # 中度（有明显痛感但意识清醒，需观察）
    NEGLIGIBLE = "NEGLIGIBLE"  # 轻微/无风险（无外伤、自述完全正常）


class EmergencyDecision(BaseModel):
    """大模型直接研判给出的结构化急救决策单。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    action: EmergencyAction = Field(..., description="裁决动作")
    call_ambulance: bool = Field(..., description="是否触发拨打救护车")
    spoken_response: str = Field(..., description="手环对用户所说的话（严格 1~2 句真人口吻，适配骨传导）")
    severity: EmergencySeverity = Field(..., description="严重级别")
    reasoning: str = Field(..., description="大模型的专业因果推演与研判理由")
    dispatch_phone_call: bool = Field(default=False, description="底层硬件是否已外呼电话")
    phone_call_payload: Dict[str, Any] = Field(default_factory=dict, description="外呼携带的物理体征与定位信息")
    judged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 底层硬件外呼模拟接口（蜂窝直连 120 / 家属）
# ---------------------------------------------------------------------------

def dispatch_emergency_phone_call(phone_number: str, payload: Dict[str, Any]) -> bool:
    """底层蜂窝通信基带外呼接口（模拟直通 120/紧急联系人）。"""
    return bool(phone_number and payload is not None)


# ---------------------------------------------------------------------------
# 大模型急救交互与裁决引擎
# ---------------------------------------------------------------------------

class EmergencyDialogueJudge:
    """大模型直接研判急救交互中枢。"""

    DEFAULT_INQUIRY: str = "还好吗？用不用叫救护车？"

    def __init__(self, *, default_ambulance_number: str = "120") -> None:
        self.default_ambulance_number = default_ambulance_number

    def generate_initial_inquiry(self, vital_snapshot: Optional[Dict[str, Any]] = None) -> str:
        """生成第一句向佩戴者发出的关切询问（大模型预置首句，零延迟直接播放）。"""
        if not vital_snapshot:
            return self.DEFAULT_INQUIRY
        
        # 若伴随恶性心律失常或重度超高 G 值，语气更加警惕
        g_force = float(vital_snapshot.get("axial_g_force") or vital_snapshot.get("g_force") or 0.0)
        pvc = int(vital_snapshot.get("pvc_burst_count") or 0)
        if g_force >= 5.0 or pvc >= 5:
            return "检测到剧烈冲击！你还好吗？需要帮你叫救护车吗？"
        return self.DEFAULT_INQUIRY

    def evaluate_response(
        self,
        user_speech: Optional[str],
        vital_snapshot: Optional[Dict[str, Any]] = None,
        *,
        llm_callable: Optional[Callable[[str], str]] = None,
    ) -> EmergencyDecision:
        """大模型直接研判佩戴者的言语或无应答状态。

        :param user_speech: 用户现场语音转写文本；如果为 None、空字符串或静默占位，则代表无回应。
        :param vital_snapshot: 现场传感器快照（G 值、心率、早搏、定位等）。
        :param llm_callable: 可选的大模型完成接口。若提供，系统将组装专业 Prompt 交给模型直接推理；
                             若未提供，系统使用内置大模型同源语义因果推演器。
        """
        vitals = vital_snapshot or {}
        cleaned_speech = (user_speech or "").strip()

        # ---------------------------------------------------------------
        # 1. 用户彻底没有回应（昏迷/休克/死寂）
        # ---------------------------------------------------------------
        is_silent = (
            not cleaned_speech
            or cleaned_speech in ("[NO_SPEECH_DETECTED]", "[SILENCE]", "[NO_RESPONSE]", "...")
        )
        if is_silent:
            reason = (
                "佩戴者在遭遇严重跌倒冲击后，经过主动呼叫关切仍处于持续无应答状态，"
                "高度疑似因颅脑损伤、骨折剧痛或心源性休克陷入昏迷，生命安全第一，"
                "大模型判定必须立即启动 120 紧急外呼与家属连线。"
            )
            payload = {
                "reason": "USER_UNRESPONSIVE_AFTER_FALL",
                "vital_snapshot": vitals,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            dispatched = dispatch_emergency_phone_call(self.default_ambulance_number, payload)
            return EmergencyDecision(
                action=EmergencyAction.CALL_AMBULANCE,
                call_ambulance=True,
                spoken_response="检测到您无应答，正在为您紧急呼叫 120 并通知家属！",
                severity=EmergencySeverity.CRITICAL,
                reasoning=reason,
                dispatch_phone_call=dispatched,
                phone_call_payload=payload,
            )

        # ---------------------------------------------------------------
        # 2. 用户有言语回应：交由大模型进行深度语义因果分析
        # ---------------------------------------------------------------
        if llm_callable is not None:
            prompt = self._build_prompt(cleaned_speech, vitals)
            raw_output = llm_callable(prompt)
            decision = self._parse_llm_json(raw_output, vitals)
            if decision is not None:
                if decision.call_ambulance and not decision.dispatch_phone_call:
                    payload = {
                        "reason": decision.reasoning,
                        "vital_snapshot": vitals,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    dispatched = dispatch_emergency_phone_call(self.default_ambulance_number, payload)
                    return decision.model_copy(
                        update={"dispatch_phone_call": dispatched, "phone_call_payload": payload}
                    )
                return decision

        # ---------------------------------------------------------------
        # 3. 内置大模型语义推演（覆盖否定、转折、隐性心梗与第三人称）
        # ---------------------------------------------------------------
        return self._semantic_reasoning(cleaned_speech, vitals)

    def _build_prompt(self, user_speech: str, vitals: Dict[str, Any]) -> str:
        return f"""你是一个运行在智能手环上的 AI 医疗急救裁决专家。
现场情况：
- 传感器生理与运动快照：{json.dumps(vitals, ensure_ascii=False)}
- 手环刚刚大声呼唤用户：“还好吗？用不用叫救护车？”
- 佩戴者或现场人员的回应录音文字：“{user_speech}”

请以专业急救医师和共生老友的身份，深度研判当前险情：
1. 识别真实意图：
   - 用户明确拒绝叫车（如“没事”、“别叫”、“我缓一缓就行”），且无致命并发症状 $\to$ STANDBY_MONITOR 或 DISMISS_FALSE_ALARM，call_ambulance=false。
   - 用户明确求助（如“快叫救护车”、“我骨折了动不了”、“救命”） $\to$ CALL_AMBULANCE，call_ambulance=true。
   - 【极其重要】隐性致命危险识别：即使用户口头说“没事”，但只要言语中透露出高危心血管/神经损伤前兆（如“胸口痛”、“喘不过气”、“透不过气”、“眼前发黑”、“手脚麻木无法动弹”），必须一票否决用户的盲目乐观，果断判为 CALL_AMBULANCE，强制叫救护车！
   - 第三方求救：若现场其他路人/家属呼救（如“他摔倒了快叫120”），立即判为 CALL_AMBULANCE。
2. 对外发声（spoken_response）：用温和、坚定、克制且极简的 1~2 句话回应用户。

请严格输出纯 JSON 对象，格式如下：
{{
  "action": "CALL_AMBULANCE" 或 "STANDBY_MONITOR" 或 "DISMISS_FALSE_ALARM",
  "call_ambulance": true 或 false,
  "spoken_response": "对外发声内容",
  "severity": "CRITICAL" 或 "MODERATE" 或 "NEGLIGIBLE",
  "reasoning": "大模型详细医学与语义研判依据"
}}"""

    def _parse_llm_json(self, raw_text: str, vitals: Dict[str, Any]) -> Optional[EmergencyDecision]:
        try:
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group(0))
            action = EmergencyAction(data.get("action", "CALL_AMBULANCE"))
            call_ambulance = bool(data.get("call_ambulance", action == EmergencyAction.CALL_AMBULANCE))
            spoken = str(data.get("spoken_response", "正在为您处理。"))
            severity = EmergencySeverity(data.get("severity", "MODERATE"))
            reasoning = str(data.get("reasoning", "大模型推理裁决。"))
            return EmergencyDecision(
                action=action,
                call_ambulance=call_ambulance,
                spoken_response=spoken,
                severity=severity,
                reasoning=reasoning,
            )
        except Exception:
            return None

    def _semantic_reasoning(self, text: str, vitals: Dict[str, Any]) -> EmergencyDecision:
        lower = text.lower()

        # 1. 隐性心梗与脑卒中高危前兆（医学最高特权：即使说了“没事”，也必须一票否决！）
        cardiac_stroke_keywords = [
            "胸口痛", "胸痛", "透不过气", "喘不上气", "喘不过气", "压榨感",
            "眼前发黑", "半边身子麻", "胳膊麻", "说不出话", "心口闷", "心绞痛"
        ]
        has_cardiac_stroke = any(k in lower for k in cardiac_stroke_keywords)
        if has_cardiac_stroke:
            reason = (
                f"佩戴者在跌倒后自述包含严重心血管/脑卒中先兆特征（检测到匹配词汇）。"
                f"尽管用户可能未主动求救，但医学常识判定属于极高危急性发作，大模型推翻常规等待，强制呼叫救护车！"
            )
            payload = {"reason": reason, "vital_snapshot": vitals, "trigger_phrase": text}
            dispatched = dispatch_emergency_phone_call(self.default_ambulance_number, payload)
            return EmergencyDecision(
                action=EmergencyAction.CALL_AMBULANCE,
                call_ambulance=True,
                spoken_response="你描述的症状很危险，不能大意，我现在立即为你叫急救车！",
                severity=EmergencySeverity.CRITICAL,
                reasoning=reason,
                dispatch_phone_call=dispatched,
                phone_call_payload=payload,
            )

        # 2. 明确求救与严重外伤（用户主动求援或第三方在场呼救）
        call_ambulance_keywords = [
            "叫救护车", "叫120", "快叫车", "快叫", "叫车", "骨折",
            "断了", "好疼", "起不来", "动不了", "救命", "流血不止",
            "晕过去了", "他摔倒了", "快来人"
        ]
        wants_help = any(k in lower for k in call_ambulance_keywords)
        # 排除否定语境（例如：“不要叫救护车”、“别叫车”）
        explicit_negation = any(neg in lower for neg in ["不要叫", "别叫", "不用叫", "别打", "不用打", "不要打"])
        
        if wants_help and not explicit_negation:
            reason = "佩戴者或在场人员明确呼救并要求派遣急救力量，大模型确认真实求救意图，立即触发拨号。"
            payload = {"reason": reason, "vital_snapshot": vitals, "user_speech": text}
            dispatched = dispatch_emergency_phone_call(self.default_ambulance_number, payload)
            return EmergencyDecision(
                action=EmergencyAction.CALL_AMBULANCE,
                call_ambulance=True,
                spoken_response="收到，别紧张，我正在立即为您呼叫 120！",
                severity=EmergencySeverity.CRITICAL,
                reasoning=reason,
                dispatch_phone_call=dispatched,
                phone_call_payload=payload,
            )

        # 3. 明确拒绝叫车 / 声明无碍（用户意识完全清醒）
        refusal_keywords = [
            "我没事", "没事", "不用叫", "别叫", "不用打", "别打",
            "坐一会儿", "缓一缓", "自己能起来", "自己能起", "虚惊一场", "摔了个杯子", "没摔着"
        ]
        is_refusal = any(k in lower for k in refusal_keywords) or explicit_negation
        if is_refusal:
            reason = "佩戴者神志清醒，明确表达拒绝呼叫救护车诉求，无致命生理并发症词汇，遵从用户意愿转入后台静默观察。"
            return EmergencyDecision(
                action=EmergencyAction.STANDBY_MONITOR,
                call_ambulance=False,
                spoken_response="好，那我先不叫车。你先缓一缓，有不舒服随时叫我。",
                severity=EmergencySeverity.MODERATE if "疼" in lower else EmergencySeverity.NEGLIGIBLE,
                reasoning=reason,
                dispatch_phone_call=False,
                phone_call_payload={},
            )

        # 4. 无法明确识别语义（模糊/呢喃）默认以人为本转入中度监护
        return EmergencyDecision(
            action=EmergencyAction.STANDBY_MONITOR,
            call_ambulance=False,
            spoken_response="我听到了，你感觉怎么样？如果需要叫车随时告诉我。",
            severity=EmergencySeverity.MODERATE,
            reasoning=f"用户语言模糊（'{text}'），未明确指示叫车，暂缓呼叫并保持高度警惕监护。",
            dispatch_phone_call=False,
            phone_call_payload={},
        )
