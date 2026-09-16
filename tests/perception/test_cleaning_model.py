"""校准认知模型测试：数据纪律、期望失分决策、知识库归纳。"""

from __future__ import annotations

import json

import pytest

from aios_core.perception.cleaning_model import (
    CalibratedCleaningModel,
    HALLUCINATION_PENALTY,
    MISSED_FACT_PENALTY,
    char_ngrams,
    roster_entities,
    surface_tokens,
)


def sample(qid: str, intent: str, dim: str, text: str, junk_text: str) -> dict:
    return {
        "question_id": qid,
        "generator_agent": "rival-team",
        "difficulty": "MEDIUM",
        "sensor_stream": {"heart_rate_bpm": 80},
        "mic_stream": [
            {"snippet_id": "mic_01", "text": junk_text, "is_junk": True},
            {"snippet_id": "mic_02", "text": text, "is_junk": False},
        ],
        "app_message_stream": [],
        "user_dialogue_stream": [],
        "ground_truth_junk_ids": ["mic_01"],
        "ground_truth_facts": [
            {
                "fact_id": "f1",
                "dimension_id": dim,
                "semantic_intent": intent,
                "anchor_entities": ["锚点A", "锚点B"],
                "directional_keywords": ["方向词1", "方向词2"],
                "core_content": text,
                "source_ref_id": "mic_02",
            }
        ],
    }


def corpus(n: int = 40) -> list[dict]:
    out = []
    for i in range(n):
        if i % 2:
            out.append(
                sample(
                    f"Q{i}",
                    "PIPE_BACKFLOW_COMPENSATION",
                    "dim:life",
                    "下水管道倒灌把客厅泡了，名贵物品浸泡要索赔",
                    "煎饼果子！热乎的煎饼果子！",
                )
            )
        else:
            out.append(
                sample(
                    f"Q{i}",
                    "ARGUMENT_CONFLICT",
                    "dim:social",
                    "两人为借款纠纷吵得面红耳赤，口角冲突升级",
                    "【帮我点一下】我只差0.01元就能提现100元现金！",
                )
            )
    return out


# --- 特征与抽取 -----------------------------------------------------------


def test_char_ngrams_basic():
    grams = char_ngrams("下水倒灌", sizes=(2,))
    assert "2:下水" in grams and "2:水倒" in grams and "2:倒灌" in grams


def test_surface_tokens_extracts_money_and_time():
    tokens = surface_tokens("明早九点前把那50万元料钱结了")
    assert any("50万元" in t for t in tokens)
    assert any("明早九点" in t for t in tokens)


def test_roster_entities_from_voiceprint_and_sender():
    q = {
        "voiceprint_cluster": {"known_bindings": {"spk_neighbor": "何欣怡", "spk_user": "大大（佩戴者）"}},
        "app_message_stream": [{"sender": "孙律师", "content": "x"}],
    }
    roster = roster_entities(q)
    assert "何欣怡" in roster
    assert "孙律师" in roster


# --- 拟合与知识库 ---------------------------------------------------------


def test_fit_builds_ontology_and_reports():
    model = CalibratedCleaningModel()
    report = model.fit(corpus())
    assert model.fitted
    assert report.calibration_questions > 0
    assert report.holdout_questions > 0
    assert "PIPE_BACKFLOW_COMPENSATION" in model.ontology
    assert "ARGUMENT_CONFLICT" in model.ontology
    profile = model.profile_for("ARGUMENT_CONFLICT")
    assert profile.dimension == "dim:social"
    assert "方向词1" in profile.keywords


def test_fit_rejects_empty_calibration():
    with pytest.raises(ValueError):
        CalibratedCleaningModel().fit([])


def test_junk_detection_after_calibration():
    model = CalibratedCleaningModel()
    model.fit(corpus())

    from aios_core.perception.cleaning_solver import _Fragment

    junk = _Fragment(kind="mic", frag_id="x", text="【帮我点一下】我只差0.01元就能提现100元现金！", index=0)
    real = _Fragment(kind="mic", frag_id="y", text="下水管道倒灌把客厅泡了，名贵物品浸泡要索赔", index=1)
    assert model.is_junk(junk) is True
    assert model.is_junk(real) is False


def test_intent_prediction_after_calibration():
    model = CalibratedCleaningModel()
    model.fit(corpus())
    intent = model.predict_intent("两人为借款纠纷吵得面红耳赤，口角冲突升级", {})
    assert intent == "ARGUMENT_CONFLICT"


def test_intent_alternatives_returns_ranked_list():
    model = CalibratedCleaningModel()
    model.fit(corpus())
    alts = model.intent_alternatives("下水管道倒灌把客厅泡了", {}, top_k=2)
    assert len(alts) <= 2
    assert alts[0] in model.ontology


# --- 期望失分决策（归因进化产物） ------------------------------------------


def test_cardinality_penalties_are_asymmetric():
    """多报与少报代价不同，决策必须体现这种不对称。"""
    assert HALLUCINATION_PENALTY == 15.0
    assert MISSED_FACT_PENALTY > HALLUCINATION_PENALTY


def test_cardinality_prefers_conservative_under_uncertainty():
    """条数后验平坦时，应偏向少报而非多报（多报每条硬扣 15 分）。"""
    from collections import Counter

    from aios_core.perception.cleaning_solver import _Fragment

    model = CalibratedCleaningModel()
    model.fit(corpus())
    clean = [_Fragment(kind="mic", frag_id="a", text="x", index=0)]
    key = model._cardinality_key("MEDIUM", clean)
    # 人为构造 1 条与 5 条各半的后验
    model.cardinality_table[key] = Counter({1: 50, 5: 50})
    assert model.predict_cardinality("MEDIUM", clean) <= 3


def test_cardinality_confident_case_matches_mode():
    from collections import Counter

    from aios_core.perception.cleaning_solver import _Fragment

    model = CalibratedCleaningModel()
    model.fit(corpus())
    clean = [_Fragment(kind="mic", frag_id="a", text="x", index=0)]
    key = model._cardinality_key("MEDIUM", clean)
    model.cardinality_table[key] = Counter({3: 100})
    assert model.predict_cardinality("MEDIUM", clean) == 3


# --- 数据纪律 -------------------------------------------------------------


def test_model_is_serialisable():
    model = CalibratedCleaningModel()
    model.fit(corpus())
    blob = model.to_dict()
    assert json.dumps(blob, ensure_ascii=False)
    assert "ontology" in blob and "report" in blob
