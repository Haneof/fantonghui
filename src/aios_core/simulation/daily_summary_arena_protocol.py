"""AIOS 3.0 全天生活流与多维总结高熵考题契约与方向性裁判器 (Daily Summary Arena Protocol).

定义 Master Dispatch #11 第二步（全天生活流与多维总结大考）的标准化考题、六维方向性标答与方向性语义裁判器。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PersonaProfile(BaseModel):
    """人物基础人设 Profile。"""
    name: str = Field(description="人物全名")
    age: int = Field(description="年龄")
    city: str = Field(description="常驻城市")
    job: str = Field(description="职业岗位")
    relationship: Optional[str] = Field(default=None, description="情感/婚姻状况")
    partner: Optional[str] = Field(default=None, description="伴侣/配偶姓名")
    band_id: Optional[str] = Field(default=None, description="绑定的可穿戴设备 ID")


class StreamSlice(BaseModel):
    """生活流清洗后单一切片 (07:00 ~ 23:30)。"""
    t: str = Field(description="时刻 HH:MM")
    src: str = Field(description="来源通道: mic/sensor/app")
    text: str = Field(description="切片客观内容")
    who: Optional[str] = Field(default=None, description="麦克风声源身份")
    app: Optional[str] = Field(default=None, description="应用名称或通知分类")
    sender: Optional[str] = Field(default=None, description="发送者")


class DirectionalGroundTruthAnchor(BaseModel):
    """单维度方向性语义标答契约。"""
    core_plot: str = Field(description="出卷官认定的事实基准核心剧情")
    core_anchors: List[str] = Field(default_factory=list, description="核心事实锚点/关键实体")
    acceptable_directions: List[str] = Field(
        default_factory=list,
        description="可接受的方向同义词簇（只要命中簇内任一方向即给分，严禁抠字眼）",
    )
    redline_violations: List[str] = Field(
        default_factory=list,
        description="绝对偏离红线判据（一票否决：触碰任一红线直接判定该维度0分并整体FAIL）",
    )
    key_evidence_refs: List[str] = Field(
        default_factory=list,
        description="证据溯源（例如 'sensor@16:57'、'mic@19:25'）",
    )

    @property
    def redline_boundary_violations(self) -> List[str]:
        return self.redline_violations

    @property
    def acceptable_directional_synonyms(self) -> List[str]:
        return self.acceptable_directions


class SixDimensionalGroundTruth(BaseModel):
    """六大维度方向性语义标答。"""
    global_daily_summary: DirectionalGroundTruthAnchor = Field(
        description="全局日总结（核心剧情主线）"
    )
    dim_health: DirectionalGroundTruthAnchor = Field(
        alias="dim:health",
        description="健康生理（体征核心变化）",
    )
    dim_social: DirectionalGroundTruthAnchor = Field(
        alias="dim:social",
        description="人际社交（关系状态翻转）",
    )
    dim_emotion: DirectionalGroundTruthAnchor = Field(
        alias="dim:emotion",
        description="情绪心理（主基调与转折）",
    )
    dim_finance: DirectionalGroundTruthAnchor = Field(
        alias="dim:finance",
        description="财务契约（资产债务变动）",
    )
    dim_career: DirectionalGroundTruthAnchor = Field(
        alias="dim:career",
        description="事业行动（推进与受阻）",
    )

    model_config = ConfigDict(populate_by_name=True)


class DailyLifeQuestion(BaseModel):
    """全天生活流与多维总结标准考题。"""
    question_id: str = Field(description="全局唯一考题 ID，例如 Q_01a0aa2d-fantonghui_00001")
    generator_agent: str = Field(description="出卷官 Agent ID")
    persona: PersonaProfile = Field(description="人物档案")
    cleaned_daily_stream: List[StreamSlice] = Field(
        description="已清洗的全天生活流切片序列 (07:00 ~ 23:30)"
    )
    directional_ground_truth: SixDimensionalGroundTruth = Field(
        description="六维方向性语义标答"
    )
    exam_date: Optional[str] = None
    difficulty: Optional[str] = None
    archetype: Optional[str] = None
    day_signature: Optional[str] = None
    trap: Optional[str] = None


class DailySummarySubmission(BaseModel):
    """做题模型提交的六维总结答卷。"""
    question_id: str
    solver_agent: str
    generated_global_summary: str
    generated_health_summary: str
    generated_social_summary: str
    generated_emotion_summary: str
    generated_finance_summary: str
    generated_career_summary: str


class DimensionEvaluationResult(BaseModel):
    """单维度裁判评估结果。"""
    dimension_name: str
    score: float = Field(ge=0.0, le=100.0)
    direction_matched: bool
    matched_direction: Optional[str] = None
    triggered_redline_violations: List[str] = Field(default_factory=list)
    recalled_anchors: List[str] = Field(default_factory=list)
    missed_anchors: List[str] = Field(default_factory=list)
    reasoning: str


class DailySummaryEvaluationReport(BaseModel):
    """全天六维总结综合裁判报告。"""
    question_id: str
    solver_agent: str
    verdict: str  # PASS or FAIL
    overall_score: float = Field(ge=0.0, le=100.0)
    dimension_results: Dict[str, DimensionEvaluationResult]
    fatal_redline_triggered: bool = False
    details: str = ""


class DailySummaryDirectionalMatcher:
    """官方方向性语义裁判器 (Directional Semantic Matcher).

    落实评卷核心思想：
    1. 宽容方向匹配：命中 acceptable_directions 簇内任一方向即认定方向吻合，绝不死板字句匹配；
    2. 严格红线一票否决：命中 redline_violations 中任一红线直接判 0 分，且整卷判定 FAIL；
    3. 关键实体/锚点召回：检查 core_anchors 在生成文本中的覆盖率；
    4. 自出自做一票否决：若 solver_agent == generator_agent，直接判定 0 分 FAIL。
    """

    DIMENSION_WEIGHTS: Dict[str, float] = {
        "global_daily_summary": 0.25,
        "dim_health": 0.15,
        "dim_social": 0.15,
        "dim_emotion": 0.15,
        "dim_finance": 0.15,
        "dim_career": 0.15,
    }

    @classmethod
    def evaluate_dimension(
        cls,
        dim_name: str,
        submission_text: str,
        anchor: DirectionalGroundTruthAnchor,
    ) -> DimensionEvaluationResult:
        """评估单维度表现。"""
        sub_clean = re.sub(r"\s+", "", submission_text.lower())
        core_clean = re.sub(r"\s+", "", anchor.core_plot.lower())

        # 1. 检查是否触发红线违规 (Redline boundary violations)
        triggered_redlines = []
        for red in anchor.redline_boundary_violations:
            red_clean = re.sub(r"\s+", "", red.lower())
            if red_clean and red_clean in sub_clean:
                triggered_redlines.append(red)

        if triggered_redlines:
            return DimensionEvaluationResult(
                dimension_name=dim_name,
                score=0.0,
                direction_matched=False,
                triggered_redline_violations=triggered_redlines,
                reasoning=f"触碰绝对红线禁区判据: {triggered_redlines}，一票否决判定0分",
            )

        # 2. 如果答卷包含或等于标准答案 core_plot，直接判定方向吻合满分
        if core_clean in sub_clean or sub_clean in core_clean:
            return DimensionEvaluationResult(
                dimension_name=dim_name,
                score=100.0,
                direction_matched=True,
                matched_direction="core_plot_exact_match",
                recalled_anchors=list(anchor.core_anchors),
                missed_anchors=[],
                reasoning="答卷与出卷事实基准核心剧情完全吻合，获得满分",
            )

        # 3. 检查方向同义词簇 (Acceptable directional synonyms)
        direction_matched = False
        matched_syn = None
        for syn in anchor.acceptable_directions:
            syn_clean = re.sub(r"\s+", "", syn.lower())
            if syn_clean and (syn_clean in sub_clean or sub_clean in syn_clean):
                direction_matched = True
                matched_syn = syn
                break

        # 4. 检查关键实体/核心锚点召回 (Core anchors)
        recalled = []
        missed = []
        for a in anchor.core_anchors:
            a_clean = re.sub(r"\s+", "", a.lower())
            if a_clean and a_clean in sub_clean:
                recalled.append(a)
            else:
                missed.append(a)

        anchor_recall_ratio = (
            len(recalled) / len(anchor.core_anchors) if anchor.core_anchors else 1.0
        )

        # 5. 计算分数
        if not direction_matched and anchor_recall_ratio < 0.3:
            dim_score = 0.0
            reasoning = "未命中任何可接受方向同义词，且核心锚点召回率严重不足"
        else:
            dir_points = 60.0 if direction_matched else 30.0
            anchor_points = 40.0 * anchor_recall_ratio
            dim_score = round(dir_points + anchor_points, 2)
            reasoning = f"方向吻合: {direction_matched} (命中: {matched_syn}), 锚点召回率: {anchor_recall_ratio*100:.1f}%"

        return DimensionEvaluationResult(
            dimension_name=dim_name,
            score=dim_score,
            direction_matched=direction_matched,
            matched_direction=matched_syn,
            recalled_anchors=recalled,
            missed_anchors=missed,
            reasoning=reasoning,
        )

    @classmethod
    def evaluate_submission(
        cls,
        question: DailyLifeQuestion,
        submission: DailySummarySubmission,
    ) -> DailySummaryEvaluationReport:
        """评卷入口：对做题模型提交的答卷进行全量六维评定。"""
        # 最高铁律：严禁自出自做 (solver != generator)
        if submission.solver_agent == question.generator_agent:
            return DailySummaryEvaluationReport(
                question_id=question.question_id,
                solver_agent=submission.solver_agent,
                verdict="FAIL",
                overall_score=0.0,
                dimension_results={},
                fatal_redline_triggered=True,
                details="严禁自出自做铁律违规：做题者与出题者均为相同 Agent，判定 0 分 FAIL",
            )

        gt = question.directional_ground_truth
        dim_map = {
            "global_daily_summary": (submission.generated_global_summary, gt.global_daily_summary),
            "dim_health": (submission.generated_health_summary, gt.dim_health),
            "dim_social": (submission.generated_social_summary, gt.dim_social),
            "dim_emotion": (submission.generated_emotion_summary, gt.dim_emotion),
            "dim_finance": (submission.generated_finance_summary, gt.dim_finance),
            "dim_career": (submission.generated_career_summary, gt.dim_career),
        }

        dim_results = {}
        fatal_redline = False
        weighted_score = 0.0

        for dim_name, (sub_text, anchor) in dim_map.items():
            res = cls.evaluate_dimension(dim_name, sub_text, anchor)
            dim_results[dim_name] = res
            weight = cls.DIMENSION_WEIGHTS.get(dim_name, 0.15)
            weighted_score += res.score * weight
            if res.triggered_redline_violations:
                fatal_redline = True

        overall_score = 0.0 if fatal_redline else round(weighted_score, 2)
        verdict = "PASS" if (overall_score >= 80.0 and not fatal_redline) else "FAIL"

        return DailySummaryEvaluationReport(
            question_id=question.question_id,
            solver_agent=submission.solver_agent,
            verdict=verdict,
            overall_score=overall_score,
            dimension_results=dim_results,
            fatal_redline_triggered=fatal_redline,
            details="评审完成" if not fatal_redline else "触碰绝对偏离红线判据，一票否决",
        )
