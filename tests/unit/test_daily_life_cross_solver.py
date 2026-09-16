"""Engineering probes only; not counted as opponent questions or solver scores."""
import copy
from datetime import datetime, timezone

import pytest

from ai_worker.daily_life_cross_solver import DIMS, summarize

NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


def observation(sid, time, source, content='', **extra):
    return dict(slice_id=sid, timestamp=f'2026-08-01T{time}:00+08:00', speaker_or_source=source,
                modality='APP', content=content, **extra)


def question(extra=()):
    rows = [
        observation('start', '07:12', '银行日初快照', measurements={'cash_balance_cents': 10000, 'loan_principal_cents': 0}),
        observation('purchase', '08:00', '个人账户银行已入账回执', '早餐已付款', transaction={'transaction_id': 'tx1', 'amount_cents': -100, 'currency': 'CNY', 'status': 'SETTLED', 'category': 'ordinary_expense'}),
        observation('close', '23:25', '银行与个人账本日终对账', measurements={'cash_balance_cents': 9900, 'loan_principal_cents': 0, 'ordinary_expense_cents': 100, 'net_cashflow_cents': -100}), *extra]
    return {'question_id': 'DAY_external_probe_001', 'persona': {'person_id': 'p1', 'name': '测试者', 'date': '2026-08-01',
            'starting_context': {'task': '核对报告'}, 'contacts': [{'name': '主管', 'role': '负责人'}, {'name': '小陈', 'role': '伴侣'}]},
            'cleaned_daily_stream': sorted(rows, key=lambda s: s['timestamp'])}


def solve(q, **kw):
    return summarize(q, generator_agent='external-team', now=NOW, **kw)


def test_six_dimensions_and_today_recording_without_input_mutation():
    q = question()
    original = copy.deepcopy(q)
    a = solve(q)
    assert set(a['summaries']) == set(DIMS)
    assert a['source_day'] == '2026-08-01'
    assert a['recorded_at'].startswith('2026-09-16')
    assert a['llm_calls'] == a['llm_tokens_used'] == 0
    assert original == q


@pytest.mark.parametrize('generator', ['agent-examiner-01a0aa2d', 'agent-aa2d', '01a0aa2d-fantonghui'])
def test_author_aliases_rejected(generator):
    with pytest.raises(ValueError, match='self-solving'):
        summarize(question(), generator_agent=generator, now=NOW)


def test_nested_ground_truth_rejected():
    q = question()
    q['persona']['injected'] = {'directional_ground_truth': {'dim:health': 'secret'}}
    with pytest.raises(ValueError, match='Ground truth'):
        solve(q)


def test_retracted_breakup_not_treated_as_confirmed_breakup():
    q = question([observation('old', '19:30', '小陈', '我想分手'),
                  observation('new', '20:30', '小陈', '我撤回分手的话，双方同意继续交往')])
    a = solve(q)
    assert a['summaries']['dim:social']['observed_status'] == 'RECONCILED'
    assert a['summaries']['dim:social']['evidence_refs'] == ['old', 'new']


def test_contacts_can_be_reordered_without_changing_conclusions():
    q = question([observation('c', '15:30', '主管', '允许改到明天，任务保留')])
    a = solve(q)
    q['persona']['contacts'].reverse()
    assert solve(q)['summaries'] == a['summaries']


def test_repeated_transaction_is_not_double_counted():
    q = question()
    dup = copy.deepcopy(q['cleaned_daily_stream'][1])
    dup['slice_id'] = 'another-receipt'
    q['cleaned_daily_stream'].insert(2, dup)
    numeric = solve(q)['summaries']['dim:finance']['numeric_facts']
    assert numeric['net_cashflow_cents'] == -100
    assert numeric['settled_transaction_count'] == 1


def test_disagreeing_duplicate_transaction_rejected():
    q = question()
    dup = copy.deepcopy(q['cleaned_daily_stream'][1])
    dup['slice_id'] = 'another-receipt'
    dup['transaction']['amount_cents'] = -200
    q['cleaned_daily_stream'].insert(2, dup)
    with pytest.raises(ValueError, match='Conflicting duplicate'):
        solve(q)


def test_financial_reconciliation_mismatch_is_not_silently_accepted():
    q = question()
    q['cleaned_daily_stream'][-1]['measurements']['cash_balance_cents'] = 9000
    with pytest.raises(ValueError, match='reconciliation'):
        solve(q)


def test_invalid_zero_ppg_does_not_trigger_cardiac_arrest():
    q = question([observation('off', '21:05', '手环', measurements={'heart_rate_bpm': 0, 'signal_valid': False, 'worn': False}),
                  observation('valid', '21:28', '手环', measurements={'heart_rate_bpm': 76, 'signal_valid': True, 'worn': True})])
    b = solve(q)['summaries']['dim:health']
    assert b['observed_status'] == 'OFF_WRIST_ARTIFACT'
    assert b['numeric_facts']['valid_hr_peak_bpm'] == 76


def test_latest_valid_measurement_controls_recovery_not_first_peak():
    q = question([observation('high', '21:05', '手环', measurements={'heart_rate_bpm': 125, 'signal_valid': True, 'motion': 'seated'}),
                  observation('low', '21:28', '手环', measurements={'heart_rate_bpm': 82, 'signal_valid': True, 'motion': 'seated'})])
    assert solve(q)['summaries']['dim:health']['observed_status'] == 'RESTING_HIGH_RECOVERED'


def test_news_cannot_become_personal_emotion_or_relationship():
    q = question([observation('news', '13:00', '新闻订阅摘要', '影视人物分手后很难过也很委屈')])
    a = solve(q)
    assert a['summaries']['dim:social']['observed_status'] == 'UNRESOLVED'
    assert a['summaries']['dim:emotion']['observed_status'] == 'UNRESOLVED'


def test_naive_clock_rejected():
    with pytest.raises(ValueError, match='timezone'):
        summarize(question(), generator_agent='other', now=NOW.replace(tzinfo=None))


def test_v2_separates_episode_onset_from_maximum_and_keeps_joint_evidence():
    q = question([
        observation('high', '21:05', '手环', measurements={'heart_rate_bpm': 122, 'signal_valid': True, 'motion': 'seated'}),
        observation('higher', '21:28', '手环', measurements={'heart_rate_bpm': 126, 'signal_valid': True, 'motion': 'seated'}),
        observation('time', '14:00', '测试者', '工作时限与个人安排的时间冲突'),
        observation('boss', '15:00', '主管', '允许改到明天'),
        observation('decision', '22:00', '测试者', '因为今晚要陪诊，我决定再申请改到下午；第二次改期尚未获批')])
    a = solve(q, version=2)
    health = a['summaries']['dim:health']['numeric_facts']
    assert health['episode_hr_bpm'] == 122
    assert health['valid_hr_peak_bpm'] == 126
    career = a['summaries']['dim:career']
    assert set(career['evidence_refs']) == {'time', 'boss', 'decision'}
    assert '第二次改期尚未获批' in career['summary_text']


def test_v2_declined_loan_must_have_personal_decline_evidence():
    q = question([
        observation('trial', '13:00', '银行试算页面', '贷款试算仅供参考，未签合同，未放款'),
        observation('refusal', '16:00', '测试者', '我决定不申请这笔贷款，没有签字')])
    f = solve(q, version=2)['summaries']['dim:finance']
    assert 'refusal' in f['evidence_refs']
    assert '本人明确拒绝申请' in f['summary_text']
