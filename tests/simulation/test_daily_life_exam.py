"""Exam publication QA only: no self-solving or semantic-score inflation."""
from __future__ import annotations

import copy
import json
import lzma
from pathlib import Path

import pytest

from simulator.daily_life_exam import (
    DIMENSIONS, FINANCE_TYPES, HEALTH_TYPES, Day, generate_question,
    person_name, publish, validate_archive, validate_question,
)
from simulator.daily_life_catalog import CAREER, SOCIAL


def test_exactly_ten_thousand_distinct_names():
    names = {person_name(i) for i in range(10000)}
    assert len(names) == 10000, "not merely 10,000 IDs for repeated people"


@pytest.mark.parametrize("index", [0, 1, 59, 256, 1234, 9999])
def test_complete_day_and_six_dimensions(index):
    q, _ = generate_question(index)
    stats = validate_question(q)
    assert set(q["directional_ground_truth"]) == set(DIMENSIONS), "all required summary dimensions"
    assert 140 <= stats["slices"] <= 230, "dense daily slices, not just a few major events"
    assert stats["anchors"] >= 6, "each dimension needs directional anchors"
    assert q["cleaned_daily_stream"][0]["timestamp"].endswith("T00:00:00+08:00"), "midnight start"
    assert q["cleaned_daily_stream"][-1]["timestamp"].endswith("T23:30:00+08:00"), "late-night endpoint"


def test_reproducible_per_person_independent_of_run_order():
    a, _ = generate_question(765, seed=2718)
    generate_question(44, seed=9876)
    b, _ = generate_question(765, seed=2718)
    c, _ = generate_question(765, seed=2719)
    assert a == b, "same index and seed must replay exactly"
    assert a != c, "seed changes substantive life evidence"


@pytest.mark.parametrize("finance", FINANCE_TYPES)
def test_all_finance_branches_reconcile(finance):
    day = Day(305, 73)
    day.finance = finance
    day.initial_debt = 900000 if finance.startswith("repay") else 0
    day.end_debt = day.initial_debt
    day.persona["starting_context"]["loan_principal_cents"] = day.initial_debt
    q, _ = day.build()
    validate_question(q)
    cash = [e["transaction"] for e in q["cleaned_daily_stream"] if "transaction" in e]
    extra = [t for t in cash if t["category"] != "ordinary_expense"]
    if finance in ("incoming_promised", "refund_pending", "loan_declined", "fraud_prevented"):
        assert not extra, "promises/applications/rumours cannot create settled cash entries"
    if finance == "loan_taken":
        assert extra[0]["category"] == "new_loan_principal", "borrowing is not salary/profit"


@pytest.mark.parametrize("health", HEALTH_TYPES)
def test_health_modes_keep_validity_and_motion_context(health):
    day = Day(902, 64)
    day.health = health
    q, _ = day.build()
    validate_question(q)
    anchor = q["directional_ground_truth"]["dim:health"]["semantic_core_anchors"][0]
    assert len(anchor["acceptable_directions"]) >= 3, "health supports semantic paraphrases"
    if health == "off_wrist_artifact":
        zero = [e for e in q["cleaned_daily_stream"] if e.get("measurements", {}).get("heart_rate_bpm") == 0]
        assert zero and all(e["measurements"]["signal_valid"] is False for e in zero), "zero PPG is explicitly invalid"
        assert "不能判为" in anchor["core_claim"], "artifact must not become a medical emergency label"
    if health == "exercise":
        assert "运动" in anchor["core_claim"], "motion context is not discarded"


def test_opposing_relationship_outcomes_preserve_final_state():
    for key, direction in (("breakup", "BREAKUP_CONFIRMED"), ("reconciled", "BREAKUP_WITHDRAWN")):
        day = Day(80, 66)
        day.social = next(s for s in SOCIAL if s["key"] == key)
        day.persona["contacts"][1]["role"] = day.social["role"]
        q, _ = day.build()
        validate_question(q)
        a = q["directional_ground_truth"]["dim:social"]["semantic_core_anchors"][0]
        assert a["semantic_intent"] == direction, "same early breakup phrase may have opposite final outcomes"
        assert len(a["evidence_slice_ids"]) == 2, "labels cite the opening and the final clarification"


def test_reschedule_does_not_magically_resolve_next_morning_care_conflict():
    # Find the combination from public generation plans, not by solving a paper.
    for index in range(1000):
        day = Day(index, 17)
        if day.career["key"] == "rescheduled" and day.social["key"] == "parent_pending":
            q, _ = day.build()
            text = q["directional_ground_truth"]["dim:career"]["semantic_core_anchors"][0]["core_claim"]
            assert "第二次改期尚未获批" in text, "another reschedule is requested, not falsely completed"
            validate_question(q)
            break
    else:
        pytest.fail("fixture seed did not cover the care/deadline conflict")


@pytest.mark.parametrize("corruption,match", [
    ("missing_dimension", "six complete"), ("dangling_evidence", "unresolvable"),
    ("fabricated_entity", "entity absent"), ("fabricated_value", "fabricated"),
    ("duplicate_id", "duplicate slice"), ("unsorted", "timestamps"),
    ("cash_mismatch", "cash ledger"), ("midnight_missing", "midnight"),
    ("label_leak", "leakage"),
])
def test_publication_rejects_corrupt_exams(corruption, match):
    q, _ = generate_question(18)
    q = copy.deepcopy(q)
    stream = q["cleaned_daily_stream"]
    truth = q["directional_ground_truth"]
    if corruption == "missing_dimension":
        del truth["dim:emotion"]
    elif corruption == "dangling_evidence":
        truth["dim:social"]["semantic_core_anchors"][0]["evidence_slice_ids"].append("UNKNOWN")
    elif corruption == "fabricated_entity":
        truth["dim:social"]["semantic_core_anchors"][0]["required_entities"].append("题面从未出现的实体")
    elif corruption == "fabricated_value":
        truth["dim:health"]["semantic_core_anchors"][0]["structured_anchors"][0]["value"] = 99999
    elif corruption == "duplicate_id":
        stream[1]["slice_id"] = stream[0]["slice_id"]
    elif corruption == "unsorted":
        stream[2], stream[3] = stream[3], stream[2]
    elif corruption == "cash_mismatch":
        next(e for e in stream if "transaction" in e)["transaction"]["amount_cents"] -= 100
    elif corruption == "midnight_missing":
        stream[0]["timestamp"] = stream[0]["timestamp"].replace("T00:00:", "T00:01:")
    else:
        stream[2]["importance"] = "core"
    with pytest.raises(ValueError, match=match):
        validate_question(q)


def test_cause_cannot_follow_its_effect():
    q, _ = generate_question(31)
    link = q["directional_ground_truth"]["global_daily_summary"]["causal_constraints"][0]
    link["cause_evidence_slice_ids"], link["effect_evidence_slice_ids"] = link["effect_evidence_slice_ids"], link["cause_evidence_slice_ids"]
    with pytest.raises(ValueError, match="backward"):
        validate_question(q)


def test_archives_replay_exactly_and_keep_truth_out_of_blind_input(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    ma = publish(a, count=5, seed=77)
    mb = publish(b, count=5, seed=77)
    assert ma == mb, "canonical compressed output must replay byte-for-byte"
    result = validate_archive(a)
    assert result["questions"] == result["distinct_people"] == 5, "five people, five days"
    with lzma.open(a / "questions_10000_people.blind.jsonl.xz", "rt", encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            assert set(q) == {"question_id", "persona", "cleaned_daily_stream"}, "no answers in blind records"
    with pytest.raises(FileExistsError):
        publish(a, count=5)


def test_tampered_archive_is_rejected(tmp_path):
    publish(tmp_path / "bank", count=1)
    archive = tmp_path / "bank/questions_10000_people.blind.jsonl.xz"
    archive.write_bytes(archive.read_bytes()[:-8])
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_archive(tmp_path / "bank")


def test_formal_schema_matches_example_when_validator_available():
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).resolve().parents[2] / "schemas/daily_life_exam.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for i in (0, 57, 9999):
        q, _ = generate_question(i)
        validator.validate(q)


def test_every_story_catalog_has_nonliteral_directional_criteria():
    for arc in CAREER + SOCIAL:
        assert len(arc["directions"]) >= 3 and arc["redline"], "each outcome supplies directional alternatives and contradiction rules"
