"""P0 紧急特权硬旁路（老大铁律三）。

法定要求：
  - 识别到严重摔倒 / 心搏骤停 / 濒危急救信号（``P0_CRITICAL_SAFETY``）时，
    调度器入口首行直接穿透硬件蜂窝报警；
  - 穿透耗时必须 ``<= 50ms``；
  - **大模型调用次数严格为 0**，世界模型让路。

因此本模块是**纯确定性**的：只读传感器标量与极少量关键词，
不做分词、不做 n-gram 打分、不加载任何模型权重、不访问世界模型、不访问 DB。
典型单次判定耗时在微秒量级，留足 50ms 预算余量。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, Mapping, Sequence


class WakePriority(StrEnum):
    """唤醒优先级。P0 为最高特权，直通硬件报警。"""

    P0_CRITICAL_SAFETY = "P0_CRITICAL_SAFETY"
    P1_NORMAL = "P1_NORMAL"


#: 心率上界：>= 该值视为恶性心动过速 / 室速风险。
HR_TACHY_CRITICAL_BPM = 180
#: 心率下界：<= 该值视为心搏骤停 / 重度心动过缓。
HR_BRADY_CRITICAL_BPM = 40
#: 室性早搏爆发阈值：>= 该值视为恶性心律失常事件。
PVC_BURST_CRITICAL = 6
#: 自由落体/静止判定：跌倒后静止时长（秒）>= 该值视为失能跌倒。
FALL_PAUSE_CRITICAL_S = 3.0
#: 冲击加速度阈值（g）。
IMU_IMPACT_CRITICAL_G = 3.5

#: 运动状态中代表"跌倒"的标记（子串匹配，零成本）。
_FALL_MOTION_TOKENS = (
    "FALL_IMPACT_STATIC",
    "FALL_TILT_AFTER_PAUSE",
    "SYNCOPAL_SINK",
    "FALL",
    "SYNCOP",
)

#: 极少量濒危呼救关键词。子串匹配，不做任何模型推理。
_SOS_TOKENS = (
    "救命",
    "快叫救护车",
    "叫救护车",
    "120",
    "心搏骤停",
    "心脏骤停",
    "没有呼吸",
    "喘不上气",
    "胸口剧痛",
    "压榨性胸痛",
    "摔倒了起不来",
    "爬不起来",
)

#: 明确属于"假摔/演戏/碰瓷"的对冲标记 —— 用于避免误报（铁律一：质量第一）。
_FAKE_TOKENS = (
    "碰瓷",
    "假摔",
    "演戏",
    "讹",
)


@dataclass(frozen=True)
class P0Verdict:
    """P0 硬旁路判定结果。"""

    triggered: bool
    priority: WakePriority
    reasons: tuple[str, ...] = field(default_factory=tuple)
    elapsed_ms: float = 0.0
    llm_calls: int = 0  # 恒为 0，铁律三硬约束
    world_model_consulted: bool = False  # 恒为 False，世界模型让路

    @property
    def is_p0(self) -> bool:
        return self.triggered


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _peak_abs(series: Any) -> float:
    """取 IMU 序列的峰值绝对值。序列可能是标量、一维或二维。"""
    if series is None:
        return 0.0
    val = _as_float(series)
    if val is not None:
        return abs(val)
    if isinstance(series, Sequence) and not isinstance(series, (str, bytes)):
        peak = 0.0
        for item in series:
            peak = max(peak, _peak_abs(item))
        return peak
    return 0.0


def evaluate_p0_bypass(
    sensor_stream: Mapping[str, Any] | None,
    utterances: Sequence[str] = (),
) -> P0Verdict:
    """P0 紧急特权硬旁路判定（铁律三）。

    纯标量 + 子串判定，**零大模型调用、零世界模型查询**。

    Args:
        sensor_stream: 传感器流（heart_rate_bpm / pvc_burst_count / motion_state 等）。
        utterances: 可选的原话文本，仅做极少量濒危呼救关键词子串匹配。

    Returns:
        :class:`P0Verdict`，含是否触发、原因、实测耗时。
    """
    t0 = time.perf_counter()
    reasons: list[str] = []
    s: Mapping[str, Any] = sensor_stream or {}

    hr = _as_float(s.get("heart_rate_bpm"))
    if hr is not None:
        if hr >= HR_TACHY_CRITICAL_BPM:
            reasons.append(f"HR_TACHY_CRITICAL:{hr:.0f}bpm")
        elif hr <= HR_BRADY_CRITICAL_BPM:
            reasons.append(f"HR_BRADY_ARREST:{hr:.0f}bpm")

    pvc = _as_float(s.get("pvc_burst_count"))
    if pvc is not None and pvc >= PVC_BURST_CRITICAL:
        reasons.append(f"PVC_BURST:{pvc:.0f}")

    motion = str(s.get("motion_state") or "").upper()
    fall_flag = any(tok in motion for tok in _FALL_MOTION_TOKENS)

    pause = _as_float(s.get("pause_seconds"))
    if fall_flag and pause is not None and pause >= FALL_PAUSE_CRITICAL_S:
        reasons.append(f"FALL_WITH_STATIC_PAUSE:{pause:.1f}s")
    elif fall_flag and "IMPACT" in motion:
        peak_g = _peak_abs(s.get("raw_imu_g_force"))
        if peak_g >= IMU_IMPACT_CRITICAL_G:
            reasons.append(f"FALL_HIGH_G_IMPACT:{peak_g:.1f}g")

    label = str(s.get("sensor_label") or "")
    if label:
        if "骤停" in label or "恶性" in label:
            reasons.append(f"SENSOR_LABEL_CRITICAL:{label}")

    # 濒危呼救关键词（零模型调用）。含碰瓷/假摔对冲词时不单凭原话触发。
    for text in utterances:
        if not text:
            continue
        if any(bad in text for bad in _FAKE_TOKENS):
            continue
        for tok in _SOS_TOKENS:
            if tok in text:
                reasons.append(f"SOS_UTTERANCE:{tok}")
                break

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    triggered = bool(reasons)
    return P0Verdict(
        triggered=triggered,
        priority=WakePriority.P0_CRITICAL_SAFETY if triggered else WakePriority.P1_NORMAL,
        reasons=tuple(reasons),
        elapsed_ms=elapsed_ms,
        llm_calls=0,
        world_model_consulted=False,
    )


def evaluate_question_p0(question: Mapping[str, Any]) -> P0Verdict:
    """对一道清洗考题执行 P0 判定（调度器入口首行）。"""
    texts: list[str] = []
    for utt in question.get("user_dialogue_stream") or ():
        if isinstance(utt, Mapping):
            raw = utt.get("raw_speech")
            if isinstance(raw, str):
                texts.append(raw)
    for snip in question.get("mic_stream") or ():
        if isinstance(snip, Mapping):
            raw = snip.get("text")
            if isinstance(raw, str):
                texts.append(raw)
    return evaluate_p0_bypass(question.get("sensor_stream"), texts)


__all__ = [
    "WakePriority",
    "P0Verdict",
    "evaluate_p0_bypass",
    "evaluate_question_p0",
    "HR_TACHY_CRITICAL_BPM",
    "HR_BRADY_CRITICAL_BPM",
    "PVC_BURST_CRITICAL",
    "FALL_PAUSE_CRITICAL_S",
]
