"""AIOS 3.0 云端大模型分布式对抗考场：数据清洗与真实事实提纯协议规范（Cleaning Arena Protocol）。

老大最高指示（2026-09-16）：
“不用接入API，我们这么多大模型开发团体是干嘛用的？让他们接管AIOS底座自己进行测试！
先从简单的数据清洗开始：你出几万道题目，每天基础数据维度各种乱七八糟的数据和有用信息等，
从外部传感器到MIC的杂七杂八录音文本和声纹记录，到APP杂七杂八的聊天，还有用户的对话等。
让云端AI自己出题，每人出1万，然后互相从别的GIT进行读取、做题！”

本协议统一全网 30+ 云端 AI 战队出题、做题、阅卷的标准数据格式与评分契约。
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DifficultyLevel(StrEnum):
    EASY = "EASY"            # 噪声较少，主次分明（常规日常）
    MEDIUM = "MEDIUM"        # 噪声密集，多方会谈，掺杂短信验证码与营销推广
    HARD = "HARD"            # 高熵嘈杂，假意图、口嗨吹牛、隐性心血管危象、方言转写
    ADVERSARIAL = "ADVERSARIAL"  # 恶意对抗（文字钓鱼、真假欠条借据对冲、伪造传感器冲击）


class FactItem(BaseModel):
    """标准答案中应当被提炼保留的核心事实。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    fact_id: str = Field(..., description="事实 ID")
    fact_type: str = Field(..., description="事实类别（HEALTH_EVENT, FINANCIAL_DEBT, SOCIAL_PROMISE, CAREER_MILESTONE, EMOTION_CRISIS）")
    dimension_id: str = Field(..., description="归属认知维度（如 dim:health, dim:finance, dim:social）")
    core_content: str = Field(..., description="必须保留的一句话客观事实或关键原话引用")
    source_ref_id: str = Field(..., description="对应的原始输入片段 ID（作为不可篡改证据锚点）")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CleaningQuestion(BaseModel):
    """一道标准的大模型数据清洗考题（涵盖多模态高噪生活流与标准答案）。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str = Field(..., description="题目唯一编号（如 Q_agent01_00001）")
    generator_agent: str = Field(..., description="出题战队标识（如 arena/agent-01）")
    timestamp_utc: str = Field(..., description="虚拟事件发生时间")
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.MEDIUM)

    # 1. 外部传感器流（IMU / PPG / GPS / 气压）
    sensor_stream: Dict[str, Any] = Field(
        default_factory=dict,
        description="包含 raw_imu_g_force, heart_rate_bpm, pvc_count, gps_loc 等"
    )

    # 2. MIC 麦克风录音转写切片（环境杂音 vs 真实对话）
    mic_stream: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="切片列表，包含 snippet_id, text, ambient_noise_db, duration_s"
    )

    # 3. 声纹聚类记录（多说话人混杂）
    voiceprint_cluster: Dict[str, Any] = Field(
        default_factory=dict,
        description="包含 user_speaker_id, detected_speakers, lsh_fingerprints"
    )

    # 4. APP 杂乱消息流（聊天、短信、推送）
    app_message_stream: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="消息列表，包含 msg_id, app_name, sender, content, timestamp"
    )

    # 5. 用户原话与自言自语（吐槽、吹牛 vs 真实诉求）
    user_dialogue_stream: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="原话列表，包含 utterance_id, raw_speech, context_scene"
    )

    # --- 标准答案 Ground Truth ---
    ground_truth_facts: List[FactItem] = Field(
        ...,
        description="出题方认定的标准核心事实列表（必须 100% 提纯保留）"
    )
    ground_truth_junk_ids: List[str] = Field(
        ...,
        description="出题方认定的垃圾数据 ID 列表（必须执行物理删除/剪枝）"
    )


class CleaningAnswerSubmission(BaseModel):
    """答题战队提交的清洗答案。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str = Field(..., description="对应的题目编号")
    solver_agent: str = Field(..., description="答题战队标识")
    extracted_facts: List[FactItem] = Field(..., description="答题战队大模型提炼出的事实列表")
    pruned_junk_ids: List[str] = Field(..., description="答题战队大模型判定物理删除的垃圾 ID 列表")
    execution_time_ms: float = Field(..., description="该题清洗提炼耗时（毫秒）")
    llm_token_consumed: int = Field(..., description="该题消耗的实际 Token 数")


class CleaningScoreResult(BaseModel):
    """阅卷裁判对单题的打分报告。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str
    solver_agent: str
    fact_precision: float = Field(..., description="事实查准率（提炼出的事实有多少是真实有用的）")
    fact_recall: float = Field(..., description="事实查全率（标准答案里的核心事实抓住了多少）")
    junk_prune_rate: float = Field(..., description="垃圾删除率（该删的广告和杂音删干净了多少，铁律四）")
    hallucination_count: int = Field(default=0, description="无中生有胡编事实次数")
    final_score: float = Field(..., description="综合得分 [0~100]")
    verdict: str = Field(..., description="PASS 或 FAIL")
