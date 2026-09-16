#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIOS 3.0 全天生活流与多维总结竞技场 —— 试卷契约与方向性裁判协议 (V1).

承接「数据清洗」之后的老二步大考: 输入为**一天已清洗生活流**
(07:00~23:30 的 MIC/APP/体征切片), 做题人须输出全局日总结 + 五维总结
(dim:health / dim:social / dim:emotion / dim:finance / dim:career).

老大铁律 —— 【方向性语义标答, 严禁死板字句匹配】:
  - 命中「可接受方向同义词」即算对 (情侣争吵分手 vs 激烈吵架/感情破裂 ⇒ 对);
  - 触碰「绝对偏离红线」一票否决 (答成 打情骂俏/甜蜜互动 ⇒ 该维 0 分).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class DifficultyLevel(StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    ADVERSARIAL = "ADVERSARIAL"


class SliceModality(StrEnum):
    MIC = "mic"
    APP = "app"
    SENSOR = "sensor"


class Persona(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    persona_id: str
    name: str
    age: int
    gender: str
    occupation: str
    life_stage: str
    city: str
    household: str
    traits: List[str] = Field(default_factory=list)


class DailySlice(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    slice_id: str
    time: str = Field(..., description="当日 HH:MM (07:00~23:30)")
    modality: SliceModality
    source: str = Field(..., description="说话人/APP 名/传感器名")
    text: str = Field(..., description="一句话切片内容")


class VitalsEpisode(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    time: str
    signal: str = Field(..., description="heart_rate / hrv_drop / fall_impact / sleep 等")
    reading: str = Field(..., description="读数, 如 '125bpm' / '8.2g后静止90秒'")
    context: str = Field(..., description="情境, 如 '接到分手微信后静坐'")


class VitalsSummary(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    sleep_hours_last_night: float
    wake_resting_hr_bpm: int
    daily_steps: int
    notable_episodes: List[VitalsEpisode] = Field(default_factory=list)


class CleanedDailyStream(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    vitals_summary: VitalsSummary
    slices: List[DailySlice]


class DirectionalAnchor(BaseModel):
    """单维度方向性标答: 核心句 + 同义方向簇 + 红线 + 实体 + 证据链."""
    model_config = ConfigDict(extra="ignore", frozen=True)

    core_statement: str = Field(..., description="基准核心句 (唯一事实基准)")
    accepted_synonyms: List[str] = Field(
        ..., description="可接受的方向同义词/短语, 命中即算方向正确")
    red_lines: List[str] = Field(
        ..., description="绝对偏离红线: 模型输出命中任一条即该维一票否决")
    key_entities: List[str] = Field(default_factory=list)
    evidence_slice_ids: List[str] = Field(default_factory=list)


class DirectionalGroundTruth(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    global_summary: DirectionalAnchor = Field(..., alias="global")
    dim_health: DirectionalAnchor = Field(..., alias="dim:health")
    dim_social: DirectionalAnchor = Field(..., alias="dim:social")
    dim_emotion: DirectionalAnchor = Field(..., alias="dim:emotion")
    dim_finance: DirectionalAnchor = Field(..., alias="dim:finance")
    dim_career: DirectionalAnchor = Field(..., alias="dim:career")
    background_to_ignore: List[str] = Field(
        default_factory=list, description="琐事/诱饵清单: 模型若将其拔高为主线应扣分")


class DailyPaper(BaseModel):
    """出卷官母卷: 题面 + 方向性标答 (仅出卷/裁判持有)."""
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    question_id: str
    generator_agent: str
    exam_date: str
    difficulty: DifficultyLevel
    persona: Persona
    cleaned_daily_stream: CleanedDailyStream
    directional_ground_truth: DirectionalGroundTruth


class BlindDailyQuestion(BaseModel):
    """盲卷: 给做题人的题面 (严禁含标答)."""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str
    generator_agent: str
    exam_date: str
    difficulty: DifficultyLevel
    persona: Persona
    cleaned_daily_stream: CleanedDailyStream


class DailyGTRecord(BaseModel):
    """独立标答卷记录."""
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    question_id: str
    generator_agent: str
    difficulty: DifficultyLevel
    directional_ground_truth: DirectionalGroundTruth


# ---------------------------------------------------------------------------
# 方向性裁判: 同义命中给分, 红线一票否决
# ---------------------------------------------------------------------------

DIMENSION_KEYS = ("global", "dim:health", "dim:social",
                  "dim:emotion", "dim:finance", "dim:career")
DIMENSION_WEIGHTS = {"global": 30.0, "dim:health": 14.0, "dim:social": 14.0,
                     "dim:emotion": 14.0, "dim:finance": 14.0, "dim:career": 14.0}


class DimensionVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    dimension: str
    red_line_hit: str | None = None
    synonym_hits: List[str] = Field(default_factory=list)
    entity_recall: float = 0.0
    score: float = 0.0


class SummaryJudgment(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str
    solver_agent: str
    generator_agent: str
    dimension_verdicts: List[DimensionVerdict]
    trivia_elevated: List[str] = Field(default_factory=list)
    final_score: float = 0.0
    verdict: str = "FAIL"


class DirectionalSummaryJudge:
    """六维方向性裁判 (确定性子串级判定, 不抠字眼)."""

    SYNONYM_COVERAGE_NEED = 2  # 命中 ≥2 个同义方向即方向满分

    @classmethod
    def judge(cls, gt: DirectionalGroundTruth,
              submission: Dict[str, str],
              *, question_id: str = "",
              solver_agent: str = "",
              generator_agent: str = "") -> SummaryJudgment:
        anchors = {"global": gt.global_summary,
                   "dim:health": gt.dim_health,
                   "dim:social": gt.dim_social,
                   "dim:emotion": gt.dim_emotion,
                   "dim:finance": gt.dim_finance,
                   "dim:career": gt.dim_career}
        verdicts: List[DimensionVerdict] = []
        total = 0.0
        any_red = False
        for dim in DIMENSION_KEYS:
            anchor = anchors[dim]
            text = (submission.get(dim, "") or "").strip()
            if not text:
                verdicts.append(DimensionVerdict(dimension=dim, score=0.0))
                continue
            red_hit: str | None = None
            for red in anchor.red_lines:
                if red and red in text:
                    red_hit = red
                    break
            if red_hit is not None:
                any_red = True
                verdicts.append(DimensionVerdict(
                    dimension=dim, red_line_hit=red_hit, score=0.0))
                continue
            hits = sorted({syn for syn in anchor.accepted_synonyms if syn and syn in text})
            coverage = min(1.0, len(hits) / cls.SYNONYM_COVERAGE_NEED)
            ents = anchor.key_entities or []
            recall = (sum(1 for e in ents if e and e in text) / len(ents)) if ents else 1.0
            dim_score = DIMENSION_WEIGHTS[dim] * (0.65 * coverage + 0.35 * recall)
            total += dim_score
            verdicts.append(DimensionVerdict(
                dimension=dim, synonym_hits=hits,
                entity_recall=round(recall, 4), score=round(dim_score, 2)))
        # 琐事拔高惩罚: 全局总结出现 background 琐事关键词 (按唯一项计)
        trivia: List[str] = []
        glob_text = (submission.get("global", "") or "")
        for item in dict.fromkeys(gt.background_to_ignore):
            if item and item in glob_text:
                trivia.append(item)
        total = max(0.0, total - 5.0 * len(trivia))
        final = round(min(100.0, total), 2)
        # 红线一票否决: 任一维度触红线, 整卷直接 FAIL (分数保留供诊断)
        verdict = "FAIL" if (any_red or final < 60.0) else "PASS"
        return SummaryJudgment(
            question_id=question_id, solver_agent=solver_agent,
            generator_agent=generator_agent, dimension_verdicts=verdicts,
            trivia_elevated=trivia, final_score=final, verdict=verdict)
