"""Synthetic probes of the limited self-check, not opponent benchmark scores."""
import copy
import runpy
from pathlib import Path

import pytest

EVAL = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/evaluate_daily_life_cross.py'))


def fixture():
    cases = {
        'global_daily_summary': ('CROSS_DIMENSION_DAILY_ARC', 'CROSS_DIMENSION_TRADEOFF', '工作改到明天并保留任务；朋友支持；已测体征稳定；退款已到账；决定休息。'),
        'dim:health': ('HEALTH_STABLE', 'STABLE_SAMPLED_VITALS', '已记录的体征稳定，不保证未观测时段。'),
        'dim:social': ('FRIEND_SUPPORT_CONFIRMED', 'FRIEND_SUPPORT', '朋友提供支持。'),
        'dim:emotion': ('EMOTION_SUPPORT', 'SELF_REPORTED', '我感到被理解。'),
        'dim:finance': ('FINANCE_REFUND_SETTLED', 'REFUND_SETTLED', '退款已到账。'),
        'dim:career': ('DEADLINE_RESCHEDULED', 'RESCHEDULED', '工作改到明天，任务保留。'),
    }
    q = {'question_id': 'SYNTHETIC', 'cleaned_daily_stream': [{'slice_id': d, 'content': t} for d, (_, _, t) in cases.items()]}
    key = {'question_id': 'SYNTHETIC', 'directional_ground_truth': {}}
    a = {'question_id': 'SYNTHETIC', 'generator_agent': 'another-examiner', 'solver_agent': 'agent-solver-01a0aa2d', 'summaries': {}}
    for d, (intent, state, text) in cases.items():
        key['directional_ground_truth'][d] = {'semantic_core_anchors': [{'semantic_intent': intent, 'evidence_slice_ids': [d], 'structured_anchors': []}]}
        a['summaries'][d] = {'summary_text': text, 'observed_status': state, 'evidence_refs': [d], 'numeric_facts': {}}
    key['directional_ground_truth']['dim:finance']['semantic_core_anchors'][0]['structured_anchors'] = [{'field': 'day_end_cash_balance_cents', 'value': 100}]
    a['summaries']['dim:finance']['numeric_facts']['closing_balance_cents'] = 100
    return q, key, a


def test_synonym_and_negative_caveat_not_a_forbidden_substring_veto():
    q, key, a = fixture()
    a['summaries']['dim:health']['summary_text'] += '不能由这些记录确诊心肌梗死。'
    r = EVAL['grade'](q, key, a)
    assert r['strict_evidence_pass']
    assert not r['free_text_redline_certified']


@pytest.mark.parametrize('value', [101, None, '100'])
def test_missing_wrong_or_wrong_type_number_does_not_pass(value):
    q, key, a = fixture()
    a['summaries']['dim:finance']['numeric_facts']['closing_balance_cents'] = value
    assert not EVAL['grade'](q, key, a)['structured_pass']


def test_metadata_alone_does_not_verify_direction():
    q, key, a = fixture()
    a['summaries']['dim:career']['summary_text'] = '你好。'
    r = EVAL['grade'](q, key, a)
    assert not r['structured_pass']
    assert 'DIRECTION_NOT_VERIFIED' in r['errors']


def test_final_state_reversal_is_not_interchangeable():
    q, key, a = fixture()
    a['summaries']['dim:career']['observed_status'] = 'TASK_CANCELLED'
    assert not EVAL['grade'](q, key, a)['structured_pass']


def test_invalid_reference_and_cross_person_answer_fail():
    q, key, a = fixture()
    bad = copy.deepcopy(a)
    bad['summaries']['dim:finance']['evidence_refs'].append('nonexistent')
    assert not EVAL['grade'](q, key, bad)['structured_pass']
    a['question_id'] = 'ANOTHER_PERSON'
    with pytest.raises(ValueError, match='identity'):
        EVAL['grade'](q, key, a)


def test_basic_local_negation_is_not_positive_evidence():
    assert not EVAL['has_contextual_expression']('没有恢复', ('恢复',))
    assert EVAL['has_contextual_expression']('款项尚未到账', ('尚未到账',))
