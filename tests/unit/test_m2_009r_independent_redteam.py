"""M2-009R independent regression / red-team layer for the R5/R6 runtime.

Adversarial coverage:
- 200-round lossless rolling archive and evidence order;
- giant-turn cockpit context budget and assembly latency;
- model-selected text, including old trigger phrases, must remain byte-for-byte intact;
- empty/silent and punctuation-only model outputs remain legitimate model choices;
- deterministic prompt assembly for identical world/input/model-output sequences;
- frozen contracts and scheduler-compatible cockpit entry.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.cockpit import (
    ConversationRound,
    ConversationState,
    CockpitPipeline,
    SINGLE_SHOT_TOKEN_BUDGET,
    estimate_tokens,
)

UTC = timezone.utc
T_START = datetime(2026, 9, 15, 23, 0, tzinfo=UTC)

_CRISIS_LINES = (
    "他们突然把基本薪资砍了百分之三十，说是经营调整。",
    "调岗通知今晚发到邮箱，从技术负责人挪到行政岗。",
    "竞业协议里那条 80 万索赔，他们开始发律师函了。",
    "HR 说要么签新合同要么走人，只给了 24 小时。",
    "期权行权价和现在的估值差了一百倍，这就是他们要的稀释。",
    "我手里有三年连续加班的记录，还有降薪前后的工资流水。",
    "对方律师函里引用了竞业条款第 4.2 条，我没签过补充协议。",
    "今晚必须把证据链理清楚，明天早上九点约谈。",
)


def _line(round_no: int) -> str:
    return _CRISIS_LINES[round_no % len(_CRISIS_LINES)] + f"（第 {round_no} 轮）"


def _redteam_model_reply(state: ConversationState) -> str:
    evidence = state.dispute_evidence()
    anchor = evidence[-1] if evidence else "当前输入"
    return (
        f"模型回复保留证据锚：{anchor}。"
        "首先只是旧触发词测试，不应导致程序删句。"
        "保持积极心态也是原样保留测试。"
        "第四句继续存在。第五句继续存在。"
    )


def make_pipeline() -> CockpitPipeline:
    state = ConversationState(crisis_context="职业危机对抗线：恶意降薪 / 强制调岗 / 竞业索赔")
    return CockpitPipeline(
        state=state,
        budget=SINGLE_SHOT_TOKEN_BUDGET,
        window_size=6,
        reply_provider=_redteam_model_reply,
    )


class TestDeepScrollLosslessness:
    def test_200_rounds_window_archive_and_evidence_order(self):
        # 一次 process_round = 用户碎片 + 老友回复 = 2 条记录 → 100 次调用 = 200 轮
        pipeline = make_pipeline()
        for i in range(100):
            points = [f"争议点-{i:02d}"] if i % 10 == 0 else []
            result = pipeline.process_round(
                _line(i), occurred_at=T_START + timedelta(minutes=i), key_dispute_points=points
            )
            assert result.cockpit.token_count <= SINGLE_SHOT_TOKEN_BUDGET == 1500

        state = pipeline.state
        assert len(state.active_window()) == 6
        assert len(state.archived()) == 194
        assert state.total_rounds == 200
        # 无损：全量轮次 = 归档 + 活动窗口，顺序完整
        all_ids = [r.round_id for r in state.all_rounds()]
        assert len(all_ids) == len(set(all_ids)) == 200
        # 关键争议点全链路有序、无丢失（10 条，每 10 轮一条）
        evidence = state.dispute_evidence()
        assert evidence == tuple(f"争议点-{i:02d}" for i in range(0, 100, 10))

    def test_p95_assembly_within_15ms_over_200_rounds(self):
        pipeline = make_pipeline()
        latencies = []
        for i in range(200):
            latencies.append(pipeline.process_round(_line(i), occurred_at=T_START + timedelta(minutes=i)).assembly_ms)
        ordered = sorted(latencies)
        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
        assert p95 <= 15.0, f"200 轮看板组装 P95 = {p95:.2f}ms 超过 15ms 红线"


class TestGiantRoundHardCap:
    def test_twenty_k_char_round_stays_within_budget_and_fast(self):
        pipeline = make_pipeline()
        giant = "。".join(_CRISIS_LINES[i % len(_CRISIS_LINES)] for i in range(4000))
        assert estimate_tokens(giant) > 1500 * 5  # 确认万字级
        peak_ms = 0.0
        for i in range(60):
            text = giant if i == 25 else _line(i)
            result = pipeline.process_round(text, occurred_at=T_START + timedelta(minutes=i))
            assert result.cockpit.token_count <= 1500
            peak_ms = max(peak_ms, result.assembly_ms)
        assert peak_ms < 300.0  # 巨轮物理硬切路径不得失控（P95 由小轮主导，Windows时钟抖动容限）
        # 巨轮过后窗口/归档仍无损
        assert pipeline.state.total_rounds == 120
        assert len(pipeline.state.active_window()) == 6


class TestModelOutputPreservationRedTeam:
    def test_five_sentence_old_trigger_evasion_is_preserved(self):
        pipeline = make_pipeline()
        candidate = (
            "局面先别急。"
            "以我见过的案例，多数人都会过去。"
            "我为你准备了一系列的步骤。"
            "每天慢慢把情绪理顺。"
            "过段时间你会看到光。"
        )
        verdict = pipeline.guard.enforce(candidate)
        assert verdict.text == candidate
        assert verdict.sentence_count == 5
        assert verdict.intercepted is False
        assert verdict.violations == ()

    def test_old_preach_trigger_words_are_not_semantically_filtered(self):
        pipeline = make_pipeline()
        candidate = "这事确实难，先别慌。我给你推荐五点心理疏导方案。"
        verdict = pipeline.guard.enforce(candidate)
        assert verdict.text == candidate
        assert "心理疏导" in verdict.text
        assert verdict.intercepted is False

    def test_empty_reply_remains_model_selected_silence(self):
        verdict = make_pipeline().guard.enforce("")
        assert verdict.text == ""
        assert verdict.sentence_count == 0
        assert verdict.intercepted is False
        assert verdict.violations == ()

    def test_punctuation_only_reply_is_preserved_without_semantic_judgment(self):
        candidate = "…………"
        verdict = make_pipeline().guard.enforce(candidate)
        assert verdict.text == candidate
        assert verdict.intercepted is False

    def test_long_reply_is_not_posthoc_truncated(self):
        candidate = "。".join(["这是一句足够长的模型话术" * 8] * 3)
        verdict = make_pipeline().guard.enforce(candidate)
        assert verdict.text == candidate
        assert len(verdict.text) > 120
        assert verdict.intercepted is False


class TestRuntimeReplySourceContract:
    def test_process_round_preserves_injected_model_reply(self):
        pipeline = make_pipeline()
        candidate = (
            "模型完整回复。首先这个词保留。保持积极心态这个短语也保留。"
            "第四句。第五句。"
        )
        result = pipeline.process_round(
            _line(0),
            occurred_at=T_START,
            assistant_reply=candidate,
        )
        assert result.assistant_round.text == candidate
        assert result.verdict.text == candidate
        assert result.verdict.intercepted is False


class TestDeterminismAndContract:
    def test_identical_input_yields_identical_prompt_bytes(self):
        prompts = []
        for _ in range(2):
            pipeline = make_pipeline()
            for i in range(12):
                pipeline.process_round(
                    _line(i),
                    occurred_at=T_START + timedelta(minutes=i),
                    key_dispute_points=[f"争议点-{i:02d}"] if i % 4 == 0 else [],
                )
            prompts.append(pipeline.assemble_cockpit().prompt)
        assert prompts[0] == prompts[1]  # 同输入 = 同 Prompt（字节级）

    def test_round_model_is_frozen(self):
        round_ = ConversationRound(
            round_id="rt-r1",
            speaker="user",
            text="降薪通知",
            occurred_at=T_START,
        )
        with pytest.raises(ValidationError):
            round_.text = "篡改"  # frozen：轮次不可事后改写

    def test_scheduler_compatible_entry_within_budget(self):
        pipeline = make_pipeline()
        pipeline.process_round(_line(0), occurred_at=T_START)
        result = pipeline.execute("wake-rt-001")
        assert result["status"] == "COCKPIT_ASSEMBLED"
        assert result["token_count"] <= 1500
        assert estimate_tokens(result["prompt"]) <= 1500
