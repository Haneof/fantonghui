"""心智四步序守卫（①照镜子→②校准羁绊→③确立姿态→④审视现场）的机械约束测试。

宪法要求的四步序过去只是文档，工程上任何一步都能被随手调用。这组用例把
"不可逆 / 不可跳步 / 不可越权读取 / 不可超预算 / 走完才准装载"钉成机械约束。
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


def _walk(runner: MindSequenceRunner, *, mirror_tokens: int = 10) -> None:
    runner.begin()
    runner.advance(STEP_MIRROR_SELF, {"identity": "老友"}, tokens=mirror_tokens)
    runner.advance(STEP_CALIBRATE_BOND, {"tier": "TRUSTED"}, tokens=10)
    runner.advance(STEP_SET_POSTURE, {"posture": "CRITICAL_SPOKEN"}, tokens=10)
    runner.advance(STEP_INSPECT_FIELD, {"evidence": ["e1"]}, tokens=10)


def test_sequence_order_is_the_constitutional_one() -> None:
    assert MIND_SEQUENCE == (
        "MIRROR_SELF",
        "CALIBRATE_BOND",
        "SET_POSTURE",
        "INSPECT_FIELD",
    ), "四步序定义被改动：必须严格对应 ①照镜子→②校准羁绊→③确立姿态→④审视现场"


def test_skipping_a_step_is_rejected() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    with pytest.raises(MindSequenceError, match="不可乱序"):
        runner.advance(STEP_SET_POSTURE, {"posture": "抢先定调"}, tokens=1)
    assert runner.progress == 0, "被拒绝的推进不得改变游标"


def test_going_backwards_is_rejected() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_MIRROR_SELF, {"identity": "老友"}, tokens=1)
    runner.advance(STEP_CALIBRATE_BOND, {"tier": "TRUSTED"}, tokens=1)
    with pytest.raises(MindSequenceError, match="不可乱序"):
        runner.advance(STEP_MIRROR_SELF, {"identity": "重来一遍"}, tokens=1)


def test_double_running_a_completed_sequence_is_rejected() -> None:
    runner = MindSequenceRunner()
    _walk(runner)
    with pytest.raises(MindSequenceError, match="不允许重复执行"):
        runner.advance(STEP_INSPECT_FIELD, {"evidence": []}, tokens=1)
    runner.begin()
    assert runner.runs == 2, "走完之后允许开启下一轮"


def test_unfinished_sequence_cannot_be_restarted() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_MIRROR_SELF, {"identity": "老友"}, tokens=1)
    with pytest.raises(MindSequenceError, match="禁止重开"):
        runner.begin()


def test_context_only_exposes_prior_steps() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_MIRROR_SELF, {"identity": "老友"}, tokens=1)
    context = runner.context_for(STEP_CALIBRATE_BOND)
    assert set(context) == {"identity"}, "第②步只应看到第①步的产物"
    with pytest.raises(MindSequenceError, match="不是当前步"):
        runner.context_for(STEP_INSPECT_FIELD)


def test_token_budget_is_enforced_per_step() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    with pytest.raises(MindSequenceError, match="超出该步预算"):
        runner.advance(STEP_MIRROR_SELF, {"identity": "老友"}, tokens=99_999)


def test_manifest_requires_a_complete_sequence() -> None:
    runner = MindSequenceRunner()
    runner.begin()
    runner.advance(STEP_MIRROR_SELF, {"identity": "老友"}, tokens=1)
    with pytest.raises(MindSequenceError, match="不允许装载驾驶舱"):
        runner.as_manifest()


def test_manifest_is_single_load_and_serialisable() -> None:
    runner = MindSequenceRunner()
    _walk(runner)
    manifest = runner.as_manifest()
    assert manifest["steps"][0]["label"] == "①照镜子看自己", "步骤标签必须与宪法口径逐字一致"
    assert manifest["order"][-1] == "④审视现场看世界", "最后一步必须是审视现场"
    assert manifest["single_load"] is True, "驾驶舱必须一次装载"
    assert manifest["backtracking_allowed"] is False, "四步序明确不可回退"
    assert manifest["token_count"] == 40, f"Token 记账必须等于各步之和，实际 {manifest['token_count']}"
