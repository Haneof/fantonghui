"""考场流水线测试：阅卷方向性、归因进化、端到端跑通。"""

from __future__ import annotations

import json

import pytest

from aios_core.perception.cleaning_arena_runner import (
    attribute_failures,
    grade,
    run_arena,
)


def base_question(qid: str, intent: str = "ARGUMENT_CONFLICT") -> dict:
    return {
        "question_id": qid,
        "generator_agent": "rival-team",
        "difficulty": "MEDIUM",
        "sensor_stream": {"heart_rate_bpm": 84, "motion_state": "WALKING"},
        "mic_stream": [
            {
                "snippet_id": "mic_01",
                "speaker_id": "spk_x",
                "text": "塑料袋五毛一个！要不要袋子？",
                "is_junk": True,
            },
            {
                "snippet_id": "mic_02",
                "speaker_id": "spk_y",
                "text": "两人为40万借款纠纷吵得面红耳赤，口角冲突升级",
                "is_junk": False,
            },
        ],
        "app_message_stream": [
            {
                "msg_id": "msg_01",
                "app": "SMS",
                "sender": "垃圾短信",
                "content": "您的验证码是4829，5分钟内有效，请勿泄露",
                "is_junk": True,
            }
        ],
        "user_dialogue_stream": [],
        "ground_truth_junk_ids": ["mic_01", "msg_01"],
        "ground_truth_facts": [
            {
                "fact_id": "fact_01",
                "dimension_id": "dim:social",
                "semantic_intent": intent,
                "anchor_entities": ["吵架", "借款"],
                "directional_keywords": ["吵架", "争吵", "冲突", "口角", "吵闹"],
                "core_content": "两人为借款纠纷激烈争吵",
                "source_ref_id": "mic_02",
                "confidence": 0.95,
            }
        ],
    }


# --- 阅卷：方向性判定 ------------------------------------------------------


def test_synonym_direction_is_accepted():
    """老大指示：事实是"吵架"，提取成"吵闹"不得判错。"""
    q = base_question("Q1")
    sub = {
        "pruned_junk_ids": ["mic_01", "msg_01"],
        "extracted_facts": [
            {
                "fact_id": "s1",
                "dimension_id": "dim:social",
                "semantic_intent": "ARGUMENT_CONFLICT",
                "summary_text": "两人发生吵闹与借款争执",
                "recognized_entities": ["吵架", "借款"],
                "source_ref_id": "mic_02",
            }
        ],
    }
    score = grade(q, sub)
    assert score.direction_match_rate == 1.0
    assert score.verdict == "PASS"


def test_wrong_dimension_fails_match():
    q = base_question("Q2")
    sub = {
        "pruned_junk_ids": ["mic_01", "msg_01"],
        "extracted_facts": [
            {
                "fact_id": "s1",
                "dimension_id": "dim:health",
                "semantic_intent": "ARGUMENT_CONFLICT",
                "summary_text": "两人发生吵闹",
                "recognized_entities": ["吵架", "借款"],
                "source_ref_id": "mic_02",
            }
        ],
    }
    assert grade(q, sub).direction_match_rate == 0.0


def test_junk_leak_is_penalised():
    q = base_question("Q3")
    sub = {
        "pruned_junk_ids": ["mic_01"],  # 漏了 msg_01
        "extracted_facts": [
            {
                "fact_id": "s1",
                "dimension_id": "dim:social",
                "semantic_intent": "ARGUMENT_CONFLICT",
                "summary_text": "两人吵架",
                "recognized_entities": ["吵架", "借款"],
                "source_ref_id": "mic_02",
            }
        ],
    }
    score = grade(q, sub)
    assert score.junk_prune_rate == 0.5
    assert "msg_01" in score.leaked_junk


def test_hallucination_is_penalised():
    q = base_question("Q4")
    facts = [
        {
            "fact_id": f"s{i}",
            "dimension_id": "dim:social",
            "semantic_intent": "ARGUMENT_CONFLICT",
            "summary_text": "两人吵架",
            "recognized_entities": ["吵架", "借款"],
            "source_ref_id": "mic_02",
        }
        for i in range(4)
    ]
    sub = {"pruned_junk_ids": ["mic_01", "msg_01"], "extracted_facts": facts}
    score = grade(q, sub)
    assert score.hallucination_count == 3
    assert score.final_score < 100.0


def test_over_prune_is_recorded():
    q = base_question("Q5")
    sub = {
        "pruned_junk_ids": ["mic_01", "msg_01", "mic_02"],  # 误删了真实事实
        "extracted_facts": [],
    }
    score = grade(q, sub)
    assert "mic_02" in score.over_pruned


# --- 归因进化 -------------------------------------------------------------


def test_attribution_reports_noise_leak():
    q = base_question("Q6")
    sub = {"pruned_junk_ids": [], "extracted_facts": []}
    attributions = attribute_failures([grade(q, sub)])
    types = {a.error_type for a in attributions}
    assert "NOISE_LEAK" in types
    assert "INTENT_DRIFT" in types
    for a in attributions:
        assert a.upgrade_action, "每条归因必须给出可执行升级手段"
        assert a.root_cause_analysis


def test_attribution_empty_when_all_pass():
    q = base_question("Q7")
    sub = {
        "pruned_junk_ids": ["mic_01", "msg_01"],
        "extracted_facts": [
            {
                "fact_id": "s1",
                "dimension_id": "dim:social",
                "semantic_intent": "ARGUMENT_CONFLICT",
                "summary_text": "两人吵架争执",
                "recognized_entities": ["吵架", "借款"],
                "source_ref_id": "mic_02",
            }
        ],
    }
    assert attribute_failures([grade(q, sub)]) == []


# --- 端到端 ---------------------------------------------------------------


def test_run_arena_end_to_end(tmp_path):
    """小规模端到端：校准 -> 盲审答题 -> 阅卷 -> 归因，全链路跑通。"""
    path = tmp_path / "questions.jsonl"
    intents = ["ARGUMENT_CONFLICT", "PIPE_BACKFLOW_COMPENSATION"]
    with path.open("w", encoding="utf-8") as fh:
        for i in range(40):
            q = base_question(f"Q_{i:05d}", intents[i % 2])
            if i % 2:
                q["mic_stream"][1]["text"] = "租的房子下水管道倒灌，名贵物品全被泡了，找房东索赔"
                q["ground_truth_facts"][0]["dimension_id"] = "dim:life"
                q["ground_truth_facts"][0]["anchor_entities"] = ["下水倒灌", "索赔"]
                q["ground_truth_facts"][0]["directional_keywords"] = ["下水倒灌", "管道", "浸泡"]
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")

    answers = tmp_path / "answers.jsonl"
    result = run_arena(
        questions_path=path,
        solver_agent="agent-01a0aa2e",
        calibration_size=24,
        answers_path=answers,
    )
    assert result.generator_agent == "rival-team"
    assert result.solver_agent == "agent-01a0aa2e"
    assert result.evaluated == 16
    assert result.metrics["junk_prune_rate"] == 1.0
    assert result.p0["llm_calls"] == 0
    assert result.p0["budget_respected"] is True

    lines = answers.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 16
    payload = json.loads(lines[0])
    assert payload["solver_agent"] == "agent-01a0aa2e"
    assert payload["llm_tokens_used"] == 0
    # 答卷里不得回写任何出题方答案字段
    assert "ground_truth_facts" not in payload
    assert "ground_truth_junk_ids" not in payload


def test_run_arena_rejects_self_solving(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text(json.dumps(base_question("Q_0"), ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="禁止自出自做"):
        run_arena(questions_path=path, solver_agent="rival-team", calibration_size=1)
