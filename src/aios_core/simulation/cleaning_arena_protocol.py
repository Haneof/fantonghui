"""AIOS 3.0 云端大模型分布式对抗考场：数据清洗与真实事实提纯协议规范（V2 升级版：融入方向一致性与归因进化）。

最高指令长（老大）法定铁律与指示（2026-09-16）：
1. “不用接入外部 API！让几十个云端大模型接管 AIOS 底座，自己进行测试！”
2. “第一步：数据清洗！每个大模型独立出 1 万道题目，涵盖传感器/MIC录音/声纹/APP聊天/用户对话等乱七八糟高熵生活流！”
3. “大模型之间互相做题，绝对不做出题人自己的题目，而是 1 对多，1 个大模型做其他所有大模型的题目！”
4. “答案不能写死，只能以方向为准确答案！不能事实是发生了吵架，模型提取成了吵闹就判错！”
5. “用大量的测试进行经验总结，分析错题原因，然后提高模型的清洗准确度！这才是真正的测试！”
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field


class DifficultyLevel(StrEnum):
    EASY = "EASY"                # 噪声较少，主次分明（常规日常）
    MEDIUM = "MEDIUM"            # 噪声密集，多方会谈，掺杂短信验证码与营销推广
    HARD = "HARD"                # 高熵嘈杂，假意图、口嗨吹牛、隐性心血管危象、方言转写
    ADVERSARIAL = "ADVERSARIAL"  # 恶意对抗（文字钓鱼、真假欠条借据对冲、伪造传感器冲击）


class DirectionalSemanticFact(BaseModel):
    """具有方向性语义认定的标准核心事实（支持近义聚类与方向容差，拒绝死板字眼匹配）。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    fact_id: str = Field(..., description="事实全局唯一标识")
    dimension_id: str = Field(..., description="归属认知维度（如 dim:health, dim:finance, dim:social, dim:career）")
    semantic_intent: str = Field(..., description="核心语义意图方向，如 ARGUMENT_CONFLICT, DEBT_BORROWING, CARDIAC_BURST, PROMISE_AGREEMENT")
    anchor_entities: List[str] = Field(default_factory=list, description="关键实体锚点（如 ['老王', '佩戴者', '10万元']）")
    directional_keywords: List[str] = Field(
        default_factory=list,
        description="方向性同义词簇（如 ['吵架', '争吵', '冲突', '口角', '争执', '吵闹', '红脸']），只要命中簇内任一词即视为方向相符"
    )
    core_content: str = Field(..., description="基准事实描述（如 '与老王在茶馆发生激烈口角争执并涉及借款纠纷'）")
    source_ref_id: str = Field(..., description="原始输入片段 ID（作为不可篡改事实证据溯源）")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CleaningQuestion(BaseModel):
    """一道标准的大模型数据清洗对抗考题（10,000 道题库标准单题结构）。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str = Field(..., description="题目唯一编号（规范格式：Q_<generator_agent>_<00001~10000>）")
    generator_agent: str = Field(..., description="出题战队编号（如 agent-01）")
    timestamp_utc: str = Field(..., description="虚拟事件发生时间 ISO 8601")
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.MEDIUM)

    # 1. 外部传感器流（50Hz IMU / PPG / GPS / 气压计）
    sensor_stream: Dict[str, Any] = Field(
        default_factory=dict,
        description="高频体征流（raw_imu_g_force, heart_rate_bpm, pvc_burst_count, gps_loc, baro_hpa 等）"
    )

    # 2. MIC 麦克风录音切片（环境嘈杂杂音 vs 真实对话）
    mic_stream: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="录音切片列表（snippet_id, text, ambient_noise_db, duration_s, is_background_chatter 等）"
    )

    # 3. 声纹聚类记录（多说话人混杂，最多 24 人声纹碎片）
    voiceprint_cluster: Dict[str, Any] = Field(
        default_factory=dict,
        description="声纹分片（user_speaker_id, detected_speakers, lsh_embeddings）"
    )

    # 4. APP 杂乱消息流（微信群推销、砍一刀、垃圾短信验证码 vs 关键通知）
    app_message_stream: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="APP 消息列表（msg_id, app_name, sender, content, timestamp）"
    )

    # 5. 用户原话与自言自语（吐槽开玩笑、吹牛 vs 真实诉求与健康呼救）
    user_dialogue_stream: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="原话列表（utterance_id, raw_speech, context_scene, emotional_tone）"
    )

    # --- 出题方预留标准答案（Ground Truth） ---
    ground_truth_facts: List[DirectionalSemanticFact] = Field(
        ...,
        description="出题方认定的标准事实方向列表（必须被提纯保留）"
    )
    ground_truth_junk_ids: List[str] = Field(
        ...,
        description="出题方认定的垃圾干扰片段 ID 列表（必须被物理删除/剪枝）"
    )


class ExtractedFactSubmission(BaseModel):
    """答题战队大模型提炼出的事实项。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    fact_id: str
    dimension_id: str
    semantic_intent: str
    summary_text: str = Field(..., description="大模型提纯出的一句话事实描述")
    recognized_entities: List[str] = Field(default_factory=list)
    source_ref_id: str


class CleaningAnswerSubmission(BaseModel):
    """答题战队提交的单题清洗提纯答案。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str = Field(..., description="对应的题目编号")
    solver_agent: str = Field(..., description="答题战队标识（如 agent-02）")
    generator_agent: str = Field(..., description="出题战队标识（如 agent-01，严格禁止 solver == generator）")
    extracted_facts: List[ExtractedFactSubmission] = Field(default_factory=list)
    pruned_junk_ids: List[str] = Field(default_factory=list, description="被物理标记删除的垃圾片段 ID")
    execution_time_ms: float = Field(default=0.0)
    llm_tokens_used: int = Field(default=0)


class DirectionalScoringReport(BaseModel):
    """方向性阅卷打分报告（方向正确即给分，杜绝死抠字眼）。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str
    solver_agent: str
    generator_agent: str
    is_self_solving_violation: bool = Field(default=False, description="是否自出自做违规（违规者直接 0 分一票否决）")
    direction_match_rate: float = Field(..., description="语义意图方向匹配率（如 争吵 vs 吵闹 -> 匹配成功）")
    entity_recall_rate: float = Field(..., description="关键实体召回率（老王、借款、10万）")
    dimension_accuracy: float = Field(..., description="维度归属正确率")
    junk_prune_rate: float = Field(..., description="垃圾剪枝删除率（铁律四）")
    hallucination_count: int = Field(default=0, description="凭空捏造事实违例数")
    final_score: float = Field(..., description="百分制总分")
    verdict: str = Field(..., description="PASS 或 FAIL（>= 90 为 PASS）")
    critique_notes: List[str] = Field(default_factory=list, description="裁判点评与扣分明细")


class FailureAttribution(BaseModel):
    """经验总结与错题归因（用于大模型总结失误并升级清洗机制）。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    error_type: str = Field(..., description="错误归因分类：NOISE_LEAK（垃圾未删）、ENTITY_MISSED（关键人遗漏）、INTENT_DRIFT（方向偏离）、FALSE_ALARM（误把玩笑当紧急）")
    sample_question_ids: List[str]
    root_cause_analysis: str = Field(..., description="大模型自我剖析：为什么漏检或误判")
    upgrade_action_taken: str = Field(..., description="采取的工程升级手段（优化提示词、调整声纹聚类阈值、增加反事实校验）")
    accuracy_before_vs_after: Dict[str, float] = Field(default_factory=dict, description="升级前后准确率对比")


class DirectionalSemanticMatcher:
    """裁判端方向性语义匹配评估器（严格落实老大法定指示：按方向判定，不抠字眼）。"""

    @staticmethod
    def is_direction_aligned(
        gt_fact: DirectionalSemanticFact,
        sub_fact: ExtractedFactSubmission
    ) -> tuple[bool, str]:
        """判断答题方提炼的事实是否与标准事实在同一个方向上。"""
        # 1. 维度必须大体对齐
        if gt_fact.dimension_id != sub_fact.dimension_id:
            return False, f"维度错位: 期望 {gt_fact.dimension_id}, 实际提交 {sub_fact.dimension_id}"

        # 2. 语义意图方向对齐（同一意图，或者语义意图包含关键字）
        gt_intent = gt_fact.semantic_intent.upper()
        sub_intent = sub_fact.semantic_intent.upper()

        intent_matched = (gt_intent == sub_intent) or (gt_intent in sub_intent) or (sub_intent in gt_intent)

        # 3. 检查同义词簇/近义方向覆盖（老王案吵架 vs 吵闹）
        keyword_matched = False
        if gt_fact.directional_keywords:
            for kw in gt_fact.directional_keywords:
                if kw in sub_fact.summary_text:
                    keyword_matched = True
                    break
        else:
            keyword_matched = True

        # 4. 关键实体交集
        gt_ents = set(gt_fact.anchor_entities)
        sub_ents = set(sub_fact.recognized_entities) | {e for e in gt_ents if e in sub_fact.summary_text}
        entity_overlap = len(gt_ents & sub_ents) / max(len(gt_ents), 1)

        # 只要意图一致或关键字命中簇内任一词，且核心实体没有张冠李戴，即视为方向相符！
        if (intent_matched or keyword_matched) and (entity_overlap >= 0.5 or not gt_ents):
            return True, "方向高度吻合（语义簇命中，实体覆盖合格）"
        
        return False, f"方向偏离: 意图命中={intent_matched}, 词簇命中={keyword_matched}, 实体覆盖={entity_overlap:.2f}"

    @classmethod
    def evaluate_submission(
        cls,
        question: CleaningQuestion,
        submission: CleaningAnswerSubmission
    ) -> DirectionalScoringReport:
        """对单题提交执行全景方向性评分。"""
        # 严格检查：1对多交叉做题，绝对禁止做自己的题目！
        if submission.solver_agent == question.generator_agent:
            return DirectionalScoringReport(
                question_id=question.question_id,
                solver_agent=submission.solver_agent,
                generator_agent=question.generator_agent,
                is_self_solving_violation=True,
                direction_match_rate=0.0,
                entity_recall_rate=0.0,
                dimension_accuracy=0.0,
                junk_prune_rate=0.0,
                hallucination_count=0,
                final_score=0.0,
                verdict="FAIL",
                critique_notes=["【严重违纪一票否决】禁止自出题自做！必须跨 Git 交叉做题！"]
            )

        notes: List[str] = []

        # 1. 垃圾剪枝率（铁律四）
        gt_junks = set(question.ground_truth_junk_ids)
        sub_pruned = set(submission.pruned_junk_ids)
        if gt_junks:
            junk_prune_rate = len(gt_junks & sub_pruned) / len(gt_junks)
        else:
            junk_prune_rate = 1.0

        if junk_prune_rate < 0.95:
            notes.append(f"垃圾剪枝不足: 遗留了 {len(gt_junks - sub_pruned)} 个垃圾片段未清理")

        # 2. 事实方向命中与实体召回
        matched_gt_count = 0
        dimension_correct_count = 0
        total_entity_overlap = 0.0

        for gt_fact in question.ground_truth_facts:
            best_aligned = False
            best_diag = ""
            for sub_fact in submission.extracted_facts:
                aligned, diag = cls.is_direction_aligned(gt_fact, sub_fact)
                if aligned:
                    best_aligned = True
                    best_diag = diag
                    if gt_fact.dimension_id == sub_fact.dimension_id:
                        dimension_correct_count += 1
                    # 计算实体
                    gt_ents = set(gt_fact.anchor_entities)
                    sub_ents = set(sub_fact.recognized_entities) | {e for e in gt_ents if e in sub_fact.summary_text}
                    total_entity_overlap += len(gt_ents & sub_ents) / max(len(gt_ents), 1)
                    break
            if best_aligned:
                matched_gt_count += 1
            else:
                notes.append(f"遗漏/偏离事实: {gt_fact.fact_id} ({gt_fact.core_content})")

        total_gt_facts = len(question.ground_truth_facts)
        direction_match_rate = matched_gt_count / max(total_gt_facts, 1)
        dimension_accuracy = dimension_correct_count / max(total_gt_facts, 1)
        entity_recall_rate = total_entity_overlap / max(total_gt_facts, 1)

        # 3. 幻觉检查（提取出的事实数量严重多于真实事实且无对应依据）
        hallucination_count = max(0, len(submission.extracted_facts) - total_gt_facts)
        if hallucination_count > 0:
            notes.append(f"疑似幻觉: 提炼出 {len(submission.extracted_facts)} 条，超出标准事实 {total_gt_facts} 条")

        # 4. 综合总分计算（满分 100）
        # 方向匹配占 40%，实体召回占 25%，垃圾剪枝占 25%，维度正确占 10%，幻觉扣分
        raw_score = (
            direction_match_rate * 40.0 +
            entity_recall_rate * 25.0 +
            junk_prune_rate * 25.0 +
            dimension_accuracy * 10.0 -
            hallucination_count * 15.0
        )
        final_score = max(0.0, min(100.0, raw_score))
        verdict = "PASS" if final_score >= 90.0 else "FAIL"

        return DirectionalScoringReport(
            question_id=question.question_id,
            solver_agent=submission.solver_agent,
            generator_agent=question.generator_agent,
            is_self_solving_violation=False,
            direction_match_rate=round(direction_match_rate, 4),
            entity_recall_rate=round(entity_recall_rate, 4),
            dimension_accuracy=round(dimension_accuracy, 4),
            junk_prune_rate=round(junk_prune_rate, 4),
            hallucination_count=hallucination_count,
            final_score=round(final_score, 2),
            verdict=verdict,
            critique_notes=notes
        )
