"""大模型急救交互研判中枢单元测试（tests/wake/test_emergency_judge.py）。

覆盖老大的五大核心场景：
1. 首句关切：“还好吗？用不用叫救护车？”
2. 用户明确表达无碍（“没事不用叫”）-> 大模型判断不叫车，持续监护；
3. 用户明确求援（“快叫救护车，骨折了动不了”）-> 大模型立即判断叫车并外呼；
4. 隐性心血管危象（嘴上说没事但“胸口痛喘不上气”）-> 大模型一票否决盲目乐观，强制叫车；
5. 用户昏迷无回应（静默/无发声）-> 判定意识丧失，自动拨打 120！
6. 接入真实 LLM Callable 的 Prompt 组装与 JSON 解析闭环。
"""

from __future__ import annotations

import json
import pytest

from aios_core.wake.emergency_judge import (
    EmergencyAction,
    EmergencyDecision,
    EmergencyDialogueJudge,
    EmergencySeverity,
)


@pytest.fixture
def judge() -> EmergencyDialogueJudge:
    return EmergencyDialogueJudge(default_ambulance_number="120")


def test_initial_inquiry_generation(judge: EmergencyDialogueJudge) -> None:
    # 默认温和发问
    inquiry = judge.generate_initial_inquiry()
    assert inquiry == "还好吗？用不用叫救护车？"

    # 超高 G 值冲击下的警惕发问
    severe_vitals = {"axial_g_force": 5.4, "pvc_burst_count": 6}
    severe_inquiry = judge.generate_initial_inquiry(severe_vitals)
    assert "剧烈冲击" in severe_inquiry
    assert "叫救护车" in severe_inquiry


def test_user_explicit_refusal_cancels_ambulance(judge: EmergencyDialogueJudge) -> None:
    speech = "哎哟卧槽，摔死我了，不过没事，刚才坐空了，不用叫车，我缓缓就行"
    vitals = {"axial_g_force": 3.2, "heart_rate_bpm": 95}
    decision = judge.evaluate_response(speech, vitals)

    assert decision.call_ambulance is False
    assert decision.action in (EmergencyAction.STANDBY_MONITOR, EmergencyAction.DISMISS_FALSE_ALARM)
    assert decision.dispatch_phone_call is False
    assert "先不叫车" in decision.spoken_response or "缓一缓" in decision.spoken_response
    assert "明确表达拒绝" in decision.reasoning or "无碍" in decision.reasoning


def test_user_explicit_request_triggers_ambulance(judge: EmergencyDialogueJudge) -> None:
    speech = "快帮我叫救护车！我好疼啊，腿摔断了起不来了！"
    vitals = {"axial_g_force": 3.8, "heart_rate_bpm": 130}
    decision = judge.evaluate_response(speech, vitals)

    assert decision.call_ambulance is True
    assert decision.action is EmergencyAction.CALL_AMBULANCE
    assert decision.severity is EmergencySeverity.CRITICAL
    assert decision.dispatch_phone_call is True
    assert decision.phone_call_payload["vital_snapshot"]["heart_rate_bpm"] == 130
    assert "120" in decision.spoken_response and "呼叫" in decision.spoken_response


def test_subtle_cardiac_stroke_danger_overrides_refusal(judge: EmergencyDialogueJudge) -> None:
    # 用户口头说“没事”，但其实已经胸痛发闷喘不过气（急性心肌梗死典型特征）
    speech = "我没事，就是不知道为什么胸口闷得发慌，喘不上气来，眼前直发黑..."
    vitals = {"axial_g_force": 3.45, "heart_rate_bpm": 160, "pvc_burst_count": 7}
    decision = judge.evaluate_response(speech, vitals)

    # 大模型具备医学因果判断，一票否决用户的盲目乐观
    assert decision.call_ambulance is True
    assert decision.action is EmergencyAction.CALL_AMBULANCE
    assert decision.severity is EmergencySeverity.CRITICAL
    assert decision.dispatch_phone_call is True
    assert "症状很危险" in decision.spoken_response
    assert "心血管" in decision.reasoning or "急性发作" in decision.reasoning


def test_silence_and_no_response_triggers_ambulance(judge: EmergencyDialogueJudge) -> None:
    # 用户完全没有发声（重度昏迷 / 休克）
    vitals = {"axial_g_force": 4.1, "heart_rate_bpm": 145}
    for silent_input in (None, "", "   ", "[NO_SPEECH_DETECTED]", "[SILENCE]"):
        decision = judge.evaluate_response(silent_input, vitals)

        assert decision.call_ambulance is True
        assert decision.action is EmergencyAction.CALL_AMBULANCE
        assert decision.severity is EmergencySeverity.CRITICAL
        assert decision.dispatch_phone_call is True
        assert "无应答" in decision.spoken_response
        assert "昏迷" in decision.reasoning or "无应答" in decision.reasoning


def test_bystander_emergency_call(judge: EmergencyDialogueJudge) -> None:
    speech = "有人在吗？我看到路边这位老先生晕过去了，快叫120来急救！"
    decision = judge.evaluate_response(speech)

    assert decision.call_ambulance is True
    assert decision.action is EmergencyAction.CALL_AMBULANCE
    assert decision.dispatch_phone_call is True


def test_custom_llm_callable_integration(judge: EmergencyDialogueJudge) -> None:
    # 模拟真实 LLM 返回的 JSON 裁决
    captured_prompts = []

    def mock_llm(prompt: str) -> str:
        captured_prompts.append(prompt)
        return json.dumps({
            "action": "CALL_AMBULANCE",
            "call_ambulance": True,
            "spoken_response": "大模型判定您的骨折伤情严重，已为您接通 120！",
            "severity": "CRITICAL",
            "reasoning": "用户左腿剧痛且伴随骨擦音描述，高度疑似闭合性骨折，必须专业担架固定转运。"
        })

    speech = "我从楼梯滚下来了，左腿动不了，一碰就钻心地疼！"
    vitals = {"axial_g_force": 4.8}
    decision = judge.evaluate_response(speech, vitals, llm_callable=mock_llm)

    assert len(captured_prompts) == 1
    assert "左腿动不了" in captured_prompts[0]
    assert decision.call_ambulance is True
    assert decision.action is EmergencyAction.CALL_AMBULANCE
    assert "骨擦音" in decision.reasoning
    assert decision.dispatch_phone_call is True
