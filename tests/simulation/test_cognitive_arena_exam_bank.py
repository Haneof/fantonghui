"""CI 门禁：AIOS 3.0 真实认知实战大考 1000 题生活流题库的协议兼容与宪法纪律校验。

本测试不跑任何“算法认知”，只承担两件事：
1. 保证题库可被 `CognitiveExamQuestion` 直接反序列化（做题端不会因格式问题失分）；
2. 保证题库满足宪法与 12 号总工令的硬纪律（照妖镜必含、红线为反向全命题、陷阱卷不得衍生维度等）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BANK_DIR = REPO_ROOT / "benchmarks" / "cognitive_arena" / "papers" / "exam_bank_1000"
SCRIPTS_DIR = REPO_ROOT / "scripts" / "cognitive_arena"
FLAGSHIP = REPO_ROOT / "benchmarks" / "cognitive_arena" / "papers" / "flagship_cognitive_exam_001.json"

sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(SCRIPTS_DIR))


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "aios_exam_bank_validator", SCRIPTS_DIR / "validate_exam_bank.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bank_report():
    if not BANK_DIR.exists():  # pragma: no cover - 题库缺失时跳过而非假装通过
        pytest.skip("1000 题题库未生成")
    validator = _load_validator()
    return validator.validate(BANK_DIR)


@pytest.fixture(scope="module")
def bank_questions():
    if not BANK_DIR.exists():  # pragma: no cover
        pytest.skip("1000 题题库未生成")
    questions = []
    for shard in sorted(BANK_DIR.glob("shard_*.json")):
        payload = json.loads(shard.read_text(encoding="utf-8"))
        questions.extend(payload["questions"])
    return questions


def test_bank_passes_all_hard_gates(bank_report):
    assert bank_report["passed"], "题库未通过硬门禁：\n" + "\n".join(bank_report["errors"][:20])
    assert bank_report["total_questions"] == 1000
    assert bank_report["validated_questions"] == 1000


def test_bank_type_distribution_matches_dispatch(bank_report):
    dist = bank_report["type_distribution"]
    assert dist["A"]["count"] == 420
    assert dist["B"]["count"] == 300
    assert dist["C"]["count"] == 180
    assert dist["D"]["count"] == 100
    assert dist["D"]["ratio"] == pytest.approx(0.10, abs=0.005)


def test_every_question_parses_into_protocol_model(bank_questions):
    from aios_core.simulation.cognitive_arena_protocol import CognitiveExamQuestion

    for raw in bank_questions[::37]:  # 均匀抽样，避免 CI 每次都全量重跑 pydantic
        model = CognitiveExamQuestion.model_validate(raw)
        assert model.question_id == raw["question_id"]
        assert model.ground_truth.expected_causal_chain


def test_main_conflict_volumes_have_honesty_mirror(bank_questions):
    for raw in bank_questions:
        if raw["exam_type"] not in {"A", "B", "C"}:
            continue
        responses = {i["user_response"] for i in raw["daytime_ai_interactions"]}
        assert responses & {"IGNORED", "IRRITATED"}, raw["question_id"]
        assert raw["ground_truth"]["ai_self_review_demands"]["must_lower_restraint"] is True


def test_trap_volumes_forbid_new_dimension(bank_questions):
    traps = [q for q in bank_questions if q["exam_type"] == "D"]
    assert len(traps) == 100
    for raw in traps:
        assert raw["ground_truth"]["expected_new_dimension"] is None, raw["question_id"]
        assert raw["judge_extensions"]["must_judge_no_new_dimension"] is True
        redline_text = " ".join(raw["ground_truth"]["anti_diagnosis_redlines"])
        assert "心律失常" in redline_text or "心肌缺血" in redline_text


def test_redlines_are_full_propositions_not_blocklists(bank_questions):
    for raw in bank_questions:
        for redline in raw["ground_truth"]["anti_diagnosis_redlines"]:
            assert redline.startswith("【") and redline.endswith("】"), (raw["question_id"], redline)


def test_candidate_dimensions_carry_article_73_and_76(bank_questions):
    for raw in bank_questions:
        if raw["exam_type"] == "D":
            continue
        candidate = raw["judge_extensions"]["candidate_dimension_full"]
        assert candidate["article_73_element_count"] == 10
        assert len(candidate["article_76_self_scores"]) == 6
        for key in (
            "rationale_why_existing_insufficient",
            "data_sources",
            "update_mechanism",
            "intended_cognitive_or_task_use",
            "expected_user_benefit",
            "overlap_with_existing_dimensions",
            "maintenance_cost_and_invalidation",
        ):
            assert candidate[key], (raw["question_id"], key)


def test_anti_fraud_volumes_gate_dangerous_actions(bank_questions):
    fraud_volumes = [q for q in bank_questions if q["exam_type"] == "C"]
    assert len(fraud_volumes) == 180
    for raw in fraud_volumes:
        ext = raw["judge_extensions"]
        assert ext["fraud_red_flags"]
        assert ext["safe_action_requirements"]
        assert ext["dangerous_action_redlines"]
        assert any("96110" in s or "官方" in s for s in ext["safe_action_requirements"])


def test_personas_are_unique_and_rich(bank_questions):
    personas = [(q["persona"]["name"], q["persona"]["occupation"]) for q in bank_questions]
    assert len(set(personas)) == len(personas)
    for raw in bank_questions[::53]:
        persona = raw["persona"]
        for key in ("name", "age", "occupation", "city", "relationship_status",
                    "monthly_income_k", "defense_habit", "medical_baseline"):
            assert persona[key], (raw["question_id"], key)
        assert 8 <= len(raw["cleaned_daily_stream"]["timeline"]) <= 15
        assert 1 <= len(raw["daytime_ai_interactions"]) <= 2


def test_flagship_exam_still_valid():
    from aios_core.simulation.cognitive_arena_protocol import CognitiveExamQuestion

    raw = json.loads(FLAGSHIP.read_text(encoding="utf-8"))
    model = CognitiveExamQuestion.model_validate(raw)
    assert model.question_id == "COGN-DAY-2026-000001"


def test_bank_index_manifest_is_consistent(bank_questions):
    index = json.loads((BANK_DIR / "index.json").read_text(encoding="utf-8"))
    assert index["bank_id"] == "COGN-BANK-2026-DAY1000-R1"
    assert index["total_questions"] == len(bank_questions)
    assert len(index["shards"]) == 10
    manifest_ids = [m["question_id"] for m in index["manifest"]]
    assert manifest_ids == [q["question_id"] for q in bank_questions]
    types = Counter(m["exam_type"] for m in index["manifest"])
    assert types == {"A": 420, "B": 300, "C": 180, "D": 100}
