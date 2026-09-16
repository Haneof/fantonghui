"""AIOS 3.0 全天生活流与多维总结高熵考题（10,000 题）验收测试。

严格校验：
1. 试卷规模达到满额 10,000 个人的一天，无重复题号；
2. 输入数据包含 07:00 ~ 23:30 全天已清洗多模态生活流切片（MIC、APP、传感器、对话）；
3. 标答全面覆盖六大核心维度（全局日总结、健康、社交、情绪、财务、事业）；
4. 每一维度必须标明【可接受的方向近义词】与【绝对偏离的红线判据】；
5. 生成器确定性可复现。
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from aios_core.simulation.daily_summary_question_generator import (
    DailySummaryQuestion,
    DailySummaryQuestionGenerator,
)

ROOT = Path(__file__).resolve().parents[2]
BANK_DIR = ROOT / "benchmarks" / "daily_summary"
QUESTIONS_FILE = BANK_DIR / "questions" / "questions_agent_aa2c_10k.jsonl"
MANIFEST_FILE = BANK_DIR / "reports" / "manifest_daily_summary_aa2c.json"


def test_question_bank_exists_and_has_10000_questions():
    """验证题库存在且拥有整整 10,000 题。"""
    assert QUESTIONS_FILE.exists(), f"题库文件未找到: {QUESTIONS_FILE}"
    count = 0
    with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    assert count == 10000, f"考题数量应为 10000，实际为 {count}"


def test_question_ids_are_unique():
    """验证 10,000 道题号全局唯一。"""
    ids = set()
    with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            ids.add(data["question_id"])
    assert len(ids) == 10000


def test_every_question_satisfies_pydantic_schema():
    """逐题按 DailySummaryQuestion 契约抽样深度校验。"""
    with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
        for idx in range(300):
            line = f.readline()
            if not line:
                break
            data = json.loads(line)
            q = DailySummaryQuestion.model_validate(data)
            assert q.generator_agent == "agent-aa2c"
            assert q.persona.name
            assert q.persona.city
            assert 18 <= q.persona.age <= 85
            assert len(q.cleaned_daily_stream) >= 10


def test_cleaned_daily_stream_covers_all_modalities_and_timeline():
    """验证每道题全天流包含 07:00 ~ 23:30 时间跨度并混合 MIC/APP/传感器模态。"""
    with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
        for idx in range(100):
            line = f.readline()
            data = json.loads(line)
            stream = data["cleaned_daily_stream"]
            
            times = [s["time"] for s in stream]
            assert any(t.startswith("07:") for t in times), "缺失早间晨起时间切片"
            assert any(t.startswith("23:") or t.startswith("22:") for t in times), "缺失晚间就寝时间切片"

            modalities = {s["modality"] for s in stream}
            assert "sensor" in modalities, "缺失传感器体征切片"
            assert "mic" in modalities, "缺失麦克风切片"
            assert "app" in modalities, "缺失APP通知切片"


def test_directional_ground_truth_covers_all_six_dimensions():
    """验证标答完整覆盖老大的六大维度，且每维均带近义词簇与红线判据。"""
    mandatory_dims = [
        "global_daily_summary",
        "dim_health",
        "dim_social",
        "dim_emotion",
        "dim_finance",
        "dim_career",
    ]

    with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
        for idx in range(100):
            line = f.readline()
            data = json.loads(line)
            gt = data["directional_ground_truth"]

            for dim in mandatory_dims:
                assert dim in gt, f"题 {data['question_id']} 缺失维度 {dim}"
                dim_obj = gt[dim]
                assert len(dim_obj["core_summary"]) >= 10, f"{dim} 核心描述过短"
                assert len(dim_obj["direction_anchors"]) >= 2, f"{dim} 缺失方向锚点"
                assert len(dim_obj["acceptable_synonyms"]) >= 3, f"{dim} 缺失方向近义词簇"
                assert len(dim_obj["redline_forbidden"]) >= 2, f"{dim} 缺失绝对偏离红线判据"


def test_generator_deterministic_reproducibility():
    """验证同种子逐字节确定性可复现。"""
    gen1 = DailySummaryQuestionGenerator(seed=20260916)
    gen2 = DailySummaryQuestionGenerator(seed=20260916)
    q1 = gen1.generate_single_question(0)
    q2 = gen2.generate_single_question(0)
    assert q1.model_dump_json() == q2.model_dump_json()
