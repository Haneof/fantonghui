# -*- coding: utf-8 -*-
"""多维总结竞技场契约与方向性裁判单测 (合成数据, 不依赖任何标答卷)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aios_core.simulation.summary_arena_protocol import (  # noqa: E402
    BlindDailyQuestion,
    DailyGTRecord,
    DailyPaper,
    DirectionalGroundTruth,
    DirectionalSummaryJudge,
)

DIMS = ("global", "dim:health", "dim:social",
        "dim:emotion", "dim:finance", "dim:career")


def _anchor(core="核心句", syn=("a", "b"), red=("x", "y"), ents=()):
    return {"core_statement": core, "accepted_synonyms": list(syn),
            "red_lines": list(red), "key_entities": list(ents),
            "evidence_slice_ids": []}


def _gt():
    return DirectionalGroundTruth.model_validate({
        "global": _anchor("工作被批晚上分手", ("被批", "分手", "失恋"), ("升职", "甜蜜"), ("老板",)),
        "dim:health": _anchor("情绪性心动过速125", ("心动过速", "125", "失眠"), ("心梗", "猝死"), ("125bpm",)),
        "dim:social": _anchor("与女友分手", ("分手", "破裂", "闹掰"), ("求婚", "复合"), ("女友",)),
        "dim:emotion": _anchor("崩溃绝望", ("崩溃", "绝望", "难过"), ("开心", "幸福")),
        "dim:finance": _anchor("无大额收支", ("无大额", "平稳", "小额"), ("巨亏", "破产")),
        "dim:career": _anchor("汇报被否整改", ("被否", "整改", "返工"), ("升职", "嘉奖")),
        "background_to_ignore": ["买咖啡", "取快递"],
    })


def test_synonym_paraphrase_passes():
    gt = _gt()
    sub = {"global": "今天先被批晚上又分手失恋，老板也在场",
           "dim:health": "心动过速到125，整夜失眠",
           "dim:social": "和女友分手，感情破裂闹掰",
           "dim:emotion": "人崩溃了，绝望难过",
           "dim:finance": "没有无大额支出，开销平稳小额",
           "dim:career": "汇报被否，打回整改返工"}
    j = DirectionalSummaryJudge.judge(gt, sub)
    assert j.verdict == "PASS" and j.final_score >= 90


def test_red_line_vetoes_whole_paper():
    gt = _gt()
    sub = {d: "被批分手失恋老板" for d in DIMS}
    sub["dim:social"] = "两人甜蜜互动，打情骂俏"  # 触红线? 用真实红线
    sub["dim:social"] = "最后求婚成功，准备复合"  # 命中 求婚/复合
    j = DirectionalSummaryJudge.judge(gt, sub)
    assert j.verdict == "FAIL"
    veto = [v for v in j.dimension_verdicts if v.red_line_hit]
    assert len(veto) == 1 and veto[0].dimension == "dim:social"


def test_empty_submission_zero():
    j = DirectionalSummaryJudge.judge(_gt(), {})
    assert j.final_score == 0.0 and j.verdict == "FAIL"


def test_trivia_elevation_penalized():
    gt = _gt()
    base = {d: "被批分手失恋老板心动过速125失眠破裂闹掰女友崩溃绝望难过无大额平稳小额被否整改返工"
            for d in DIMS}
    j0 = DirectionalSummaryJudge.judge(gt, base)
    elevated = dict(base)
    elevated["global"] = base["global"] + "，还买咖啡取快递"
    j1 = DirectionalSummaryJudge.judge(gt, elevated)
    assert j1.trivia_elevated == ["买咖啡", "取快递"]
    assert j1.final_score == j0.final_score - 10.0


def _paper_dict(with_gt=True):
    d = {
        "question_id": "D_t_00001",
        "generator_agent": "g",
        "exam_date": "2026-09-16",
        "difficulty": "HARD",
        "persona": {"persona_id": "P02", "name": "林浩", "age": 24,
                    "gender": "男", "occupation": "程序员",
                    "life_stage": "北漂", "city": "北京", "household": "合租"},
        "cleaned_daily_stream": {
            "vitals_summary": {"sleep_hours_last_night": 5.2,
                               "wake_resting_hr_bpm": 72, "daily_steps": 6000,
                               "notable_episodes": []},
            "slices": [{"slice_id": "s1", "time": "09:40", "modality": "mic",
                        "source": "老板", "text": "重做"}]},
    }
    if with_gt:
        d["directional_ground_truth"] = {
            "global": _anchor(), "dim:health": _anchor(), "dim:social": _anchor(),
            "dim:emotion": _anchor(), "dim:finance": _anchor(),
            "dim:career": _anchor(), "background_to_ignore": []}
    return d


def test_paper_contracts_validate():
    DailyPaper.model_validate(_paper_dict(True))
    BlindDailyQuestion.model_validate(_paper_dict(False))
    DailyGTRecord.model_validate({"question_id": "D_t_00001",
                                  "generator_agent": "g",
                                  "difficulty": "HARD",
                                  "directional_ground_truth": _paper_dict(True)[
                                      "directional_ground_truth"]})
