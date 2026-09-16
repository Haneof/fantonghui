"""Synthetic engineering regressions, not scored self-authored exam papers."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path

import pytest
from pydantic import ValidationError

from aios_core.summaries.cross_team_daily_solver import (
    BlindDailyQuestion, DIMS, DailyCrossSolver, DailyCrossSolverV2, SOLVER,
)
from evaluator.daily_cross_evaluation import validate_submission
from evaluator.daily_summary_aa2d_reference import DirectionalGroundTruthAnchor, DailySummaryDirectionalMatcher

ROOT = Path(__file__).resolve().parents[2]


def question(slices, **overrides):
    data = {"question_id": "opponent-test-only", "generator_agent": "other-team", "exam_date": "2024-03-14",
            "persona": {"name": "测试甲", "age": 32, "city": "测试城", "job": "工程师", "partner": "测试乙"},
            "cleaned_daily_stream": slices}
    return BlindDailyQuestion.model_validate({**data, **overrides})


def event(text, who="自己", src="mic", t="19:00", **kw):
    return {"t": t, "src": src, "text": text, **({"who": who} if src == "mic" else {"sender": who}), **kw}


def test_projection_schema_rejects_labels_and_hint_fields():
    for field in ("directional_ground_truth", "archetype", "trap", "day_signature", "difficulty"):
        with pytest.raises(ValidationError):
            question([event("普通问候")], **{field: "hidden answer"})
    with pytest.raises(ValidationError):
        question([event("普通问候", expected_intent="leak")])


@pytest.mark.parametrize("alias", [SOLVER, "daily-examiner-01a0aa30", "01a0aa30-fantonghui", "AGENT-SOLVER-01A0AA30"])
def test_no_self_solving_under_examiner_or_solver_alias(alias):
    q = question([event("普通问候")], generator_agent=alias)
    with pytest.raises(ValueError, match="self-solving"):
        DailyCrossSolverV2().solve(q)


def test_history_immutable_and_today_only_annotations():
    q = question([event("【账户通知】兼职稿费1,500元到账", "银行", "app")])
    original = copy.deepcopy(q.model_dump())
    now = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
    answer, audit = DailyCrossSolverV2().solve(q, now=now)
    assert q.model_dump() == original, "never mutate historical slices"
    assert audit["learned_at"] == audit["recorded_at"] == now.isoformat(), "append at today's time"
    assert audit["source_exam_date"] == "2024-03-14", "keep occurrence date separate"
    assert audit["llm_calls"] == audit["world_calls"] == 0, "this baseline performs no hidden model/world calls"
    assert all(answer[f"generated_{d}_summary"].strip() for d in DIMS), "six explicit nonempty summaries"
    with pytest.raises(ValueError, match="timezone"):
        DailyCrossSolverV2().solve(q, now=datetime(2026, 9, 16))


def test_app_sender_beats_spurious_mic_speaker():
    q = question([{"t": "19:00", "src": "app", "text": "口头offer确认：薪资上浮27%，下周回复", "sender": "HR", "who": "测试乙"}])
    # Construct the APP row directly because who on an APP is an irrelevant
    # foreign field but is present in some opponent source records.
    a, audit = DailyCrossSolverV2().solve(q)
    assert "口头offer" in a["generated_career_summary"], "HR notification remains a career fact"
    assert any(f["intent"] == "OFFER" for f in audit["facts"]), "sender is resolved by modality"


def test_partner_promotion_not_wearer_promotion():
    q = question([event("我升主管了！请你吃饭", "测试乙")])
    a, _ = DailyCrossSolverV2().solve(q)
    assert "伴侣分享自己升主管" in a["generated_social_summary"], "preserve the promoted person"
    assert "题面未提供" in a["generated_career_summary"], "do not invent the wearer's promotion"


def test_celeb_news_and_coworker_boast_are_not_personal_facts():
    q = question([event("【热搜】知名男星官宣分手（转发链接）", "大学同学群", "app"),
                  event("老子明天就辞职去旅游，哈哈哈！", "同事")])
    _, audit = DailyCrossSolverV2().solve(q)
    assert not audit["facts"], "quoted news and another person's joke do not establish wearer events"


def test_offer_and_unpaid_award_not_today_cash():
    q = question([event("季度创新奖名单公示，奖金随下月工资发放", "HR", "app"),
                  event("口头offer确认，下周回复", "HR", "app", t="20:00")])
    a, _ = DailyCrossSolverV2().solve(q)
    assert "未来发放" in a["generated_career_summary"], "award status preserves payment timing"
    assert "题面未提供" in a["generated_finance_summary"], "do not fabricate receipt of unpaid money"


def test_equity_float_loss_not_cash_debit_even_with_wrong_wrapper():
    q = question([event("【扣款通知】股票账户今日浮亏6,000元", "银行", "app")])
    a, _ = DailyCrossSolverV2().solve(q)
    assert "浮动损益" in a["generated_finance_summary"], "content wins over incorrect notification wrapper"
    assert "未提供已卖出或现金扣款依据" in a["generated_finance_summary"], "unrealized loss stays unrealized"


def test_non_named_criticism_not_false_personal_accusation():
    q = question([event("有些组的数据管理不好，我不点名！", "领导（大会）")])
    a, _ = DailyCrossSolverV2().solve(q)
    assert "是否指向本人并未明确" in a["generated_career_summary"], "do not manufacture a named accusation"


def test_leader_followup_preserved_without_inventing_written_report():
    q = question([event("P2事故定责：操作记录指向你账号，明早复盘", "运维群", "app", t="15:00"),
                  event("检讨明天给我，该是谁的问题就是谁的问题。", "领导", t="16:00")])
    a, audit = DailyCrossSolverV2().solve(q)
    assert "检讨形式未明确" in a["generated_career_summary"], "request exists but its written format is not given"
    assert {r["slice_index"] for r in audit["evidence"]["career"]} == {0, 1}, "both primary and follow-up evidence retained"


def test_health_algorithm_label_is_attributed_not_clinical_fact():
    q = question([event("心率由76bpm骤升至126bpm，持续约8分钟，判定情绪性心动过速", src="sensor")])
    a, _ = DailyCrossSolverV2().solve(q)
    assert "设备算法标注" in a["generated_health_summary"], "attribution retained"
    assert "不等于医生确诊" in a["generated_health_summary"], "no medical diagnosis from the benchmark tag"


def test_source_quotes_hashes_and_indices_resolve():
    q = question([event("【账户通知】网购退款580元原路退回", "银行", "app")])
    _, audit = DailyCrossSolverV2().solve(q)
    for refs in audit["evidence"].values():
        for ref in refs:
            s = q.cleaned_daily_stream[ref["slice_index"]]
            assert ref["source_sha256"] == hashlib.sha256(s.model_dump_json().encode()).hexdigest(), "evidence integrity"


def test_friend_request_does_not_imply_refusal_or_payment():
    q = question([event("5万，就周转两个月，咱俩什么交情……", "老友"),
                  event("（沉默十几秒）行，我知道了。（挂断）", "老友", t="19:02")])
    a, _ = DailyCrossSolverV2().solve(q)
    assert "未证明本人已出借或明确拒绝" in a["generated_social_summary"], "keep ambiguity instead of adopting a hidden plot"
    assert "题面未提供" in a["generated_finance_summary"], "request is not a settled transaction"


def test_reference_judge_empty_text_loophole_is_blocked():
    raw = {"question_id": "q", "solver_agent": SOLVER, **{f"generated_{d}_summary": "okay" for d in DIMS}}
    raw["generated_global_summary"] = "  "
    with pytest.raises(ValueError, match="empty"):
        validate_submission(raw, "q")
    raw["generated_global_summary"] = "nonempty"
    with pytest.raises(ValueError, match="identity"):
        validate_submission(raw, "another-q")


def test_reference_redline_is_literal_not_a_semantic_veto():
    truth = DirectionalGroundTruthAnchor(core_plot="没有借贷发生", acceptable_directions=["未借款"], redline_violations=["巨额负债"])
    result = DailySummaryDirectionalMatcher.evaluate_dimension("finance", "未发生巨额负债", truth)
    assert result.score == 0, "document the unchanged legacy judge's negation flaw, don't claim it is correct"


def test_bid_and_scope_do_not_magnify_into_unemployment():
    q = question([event("抱歉，上面换了供应商，合作暂时取消了。", "客户")])
    a, _ = DailyCrossSolverV2().solve(q)
    assert "不能扩大为全面失业" in a["generated_career_summary"], "limited cancellation scope preserved"


def test_v1_remains_available():
    q = question([event("检讨明天给我", "领导")])
    before, _ = DailyCrossSolver().solve(q)
    after, _ = DailyCrossSolverV2().solve(q)
    assert "题面未提供" in before["generated_career_summary"], "freeze the real baseline behavior"
    assert "检讨" in after["generated_career_summary"], "v2 includes previously missed followup"
