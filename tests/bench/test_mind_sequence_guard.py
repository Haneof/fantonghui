"""Cockpit slot layout tests.

The slot layout is stable for serialization and budgeting, but it must never
constrain the cognitive model's execution order.
"""

from __future__ import annotations

import pytest

from aios_core.cognition.mind_sequence import (
    MIND_SEQUENCE,
    STEP_CALIBRATE_BOND,
    STEP_INSPECT_FIELD,
    STEP_MIRROR_SELF,
    STEP_SET_POSTURE,
    MindSequenceError,
    MindSequenceRunner,
)


def _fill_out_of_order(runner: MindSequenceRunner) -> None:
    runner.begin()
    runner.advance(STEP_INSPECT_FIELD, {"evidence": ["e1"]}, tokens=10)
    runner.advance(STEP_SET_POSTURE, {"posture": "model_decides"}, tokens=10)
    runner.advance(STEP_MIRROR_SELF, {"identity": "AIOS AI 驾驶员"}, tokens=10)
    runner.advance(STEP_CALIBRATE_BOND, {"relationship": "evidence-linked"}, tokens=10)


def test_sequence_constant_is_stable_layout_not_reasoning_order() -> None:
    assert MIND_SEQUENCE == (
        "MIRROR_SELF",
        "CALIBRATE_BOND",
        "SET_POSTURE",
        "INSPECT_FIELD",
    )


def test_slots_accept_arbitrary_runtime_order() -> None:
    runner = MindSequenceRunner()
    _fill_out_of_order(runner)
    assert runner.completed is True
    assert runner.progress == 4
    assert runner.runtime_call_order() == (
        STEP_INSPECT_FIELD,
        STEP_SET_POSTURE,
        STEP_MIRROR_SELF,
        STEP_CALIBRATE_BOND,
    )


def test_slot_can_be_revised_without_rule_brain_backtracking_error() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_SET_POSTURE, {"posture": "first"}, tokens=9)
    runner.advance(STEP_SET_POSTURE, {"posture": "revised"}, tokens=7)
    assert runner.progress == 1
    assert runner.context_for(STEP_INSPECT_FIELD)["posture"] == "revised"
    assert runner.manifest_tokens() == 7


def test_context_exposes_currently_available_slots_regardless_of_layout_position() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_INSPECT_FIELD, {"evidence": "scene-first"}, tokens=1)
    assert runner.context_for(STEP_MIRROR_SELF)["evidence"] == "scene-first"


def test_token_budget_is_still_enforced_per_slot() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    with pytest.raises(MindSequenceError, match="超出该槽位预算"):
        runner.advance(STEP_MIRROR_SELF, {"identity": "x"}, tokens=99_999)


def test_unknown_slot_is_rejected() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    with pytest.raises(MindSequenceError, match="unknown cockpit slot"):
        runner.advance("SECRET_REASONING_STEP", {}, tokens=1)


def test_manifest_requires_all_slots_but_not_a_reasoning_sequence() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_INSPECT_FIELD, {"evidence": ["e1"]}, tokens=1)
    with pytest.raises(MindSequenceError, match="incomplete"):
        runner.as_manifest()


def test_manifest_serializes_stably_after_out_of_order_runtime_calls() -> None:
    runner = MindSequenceRunner()
    _fill_out_of_order(runner)
    manifest = runner.as_manifest()
    assert tuple(item["step"] for item in manifest["steps"]) == MIND_SEQUENCE
    assert manifest["steps"][0]["label"] == "①照镜子看自己"
    assert manifest["single_load"] is True
    assert manifest["backtracking_allowed"] is True
    assert manifest["cognitive_order_enforced"] is False
    assert manifest["token_count"] == 40


def test_begin_may_reset_an_abandoned_partial_assembly() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_MIRROR_SELF, {"identity": "old"}, tokens=1)
    runner.begin()
    assert runner.runs == 2
    assert runner.progress == 0
