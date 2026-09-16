#!/usr/bin/env python3
"""Transparent STRUCTURED self-evaluation; not the opponent's official judge.

No reference-summary copying, token-overlap grading or redline substring veto.
Checks named state equivalence, required numerical anchors and evidence links.
Small expression groups are a sanity check, not a universal semantic evaluator.
All groups require affirmative/contextual evidence, with basic local negation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import re
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path

STATE_MAP = {
    'HEALTH_STABLE': 'STABLE_SAMPLED_VITALS', 'HEALTH_STRESS_RECOVERED': 'RESTING_HIGH_RECOVERED',
    'HEALTH_STRESS_PERSISTENT': 'RESTING_HIGH_PERSISTENT', 'HEALTH_SHORT_SLEEP': 'SHORT_SLEEP',
    'HEALTH_EXERCISE': 'EXERCISE_RECOVERED', 'HEALTH_OFF_WRIST_ARTIFACT': 'OFF_WRIST_ARTIFACT',
    'BREAKUP_CONFIRMED': 'BREAKUP_CONFIRMED', 'BREAKUP_WITHDRAWN': 'RECONCILED',
    'CAREGIVING_PENDING_DIAGNOSIS': 'PARENT_VISIT_PENDING', 'CARE_RESPONSIBILITY_SHARED': 'CARE_SHARED',
    'COLLEAGUE_CONFLICT_REPAIRED': 'APOLOGY_REPAIRED', 'FRIEND_BOUNDARY_ACCEPTED': 'FRIEND_BOUNDARY',
    'FRIEND_SUPPORT_CONFIRMED': 'FRIEND_SUPPORT', 'LEASE_NEGOTIATION_PENDING': 'HOUSING_PENDING',
    'ALLEGATION_CORRECTED': 'CREDIT_CORRECTED', 'DEADLINE_RESCHEDULED': 'RESCHEDULED',
    'EXTRA_TASK_DECLINED': 'EXTRA_DECLINED', 'OFFER_UNDECIDED': 'OFFER_PENDING',
    'REJECTION_REVERSED': 'RECOVERED_APPROVAL', 'REVISION_PENDING': 'REVISION_PENDING',
    'SCOPE_REDUCED_CONTINUES': 'SCOPE_REDUCED', 'TASK_CANCELLED_LIMITED_SCOPE': 'TASK_CANCELLED',
    **{'FINANCE_' + state: state for state in ['FRAUD_PREVENTED', 'INCOMING_PROMISED', 'INCOMING_SETTLED', 'LOAN_DECLINED', 'LOAN_TAKEN', 'REFUND_PENDING', 'REFUND_SETTLED', 'REPAIR_PAID', 'REPAY_FULL', 'REPAY_PARTIAL']},
}
NUMBER_MAP = {'morning_heart_rate_bpm': 'morning_resting_hr_bpm', 'sleep_minutes': 'sleep_minutes', 'steps': 'steps',
              'episode_heart_rate_bpm': 'episode_hr_bpm', 'day_end_cash_balance_cents': 'closing_balance_cents',
              'day_end_loan_principal_cents': 'closing_loan_principal_cents', 'ordinary_expense_cents': 'ordinary_expense_cents'}
EMOTION_GROUPS = {
    'EMOTION_BREAKUP': [('难过', '委屈', '失落', '伤心')],
    'EMOTION_RECONCILED': [('委屈', '受伤', '难过'), ('松了口气', '缓解', '释然', '缓和')],
    'EMOTION_PARENT_PENDING': [('担心', '焦虑', '担忧', '不安')],
    'EMOTION_CARE_SHARED': [('松了口气', '缓解', '安心'), ('担心', '担忧', '检查')],
    'EMOTION_COWORKER_APOLOGY': [('憋屈', '委屈', '受伤'), ('更正', '道歉', '没那么生气', '缓解')],
    'EMOTION_FRIEND_BOUNDARY': [('压力', '焦虑', '质问'), ('放松', '缓解', '松了口气')],
    'EMOTION_SUPPORT': [('被理解', '支持', '倾听', '没那么孤立')],
    'EMOTION_HOUSING_PENDING': [('不安', '担心', '担忧', '不确定')],
}
STATE_GROUPS = {
    'STABLE_SAMPLED_VITALS': [('平稳', '稳定')],
    'RESTING_HIGH_RECOVERED': [('升高', '心动过速'), ('回落', '恢复')],
    'RESTING_HIGH_PERSISTENT': [('仍偏高', '持续', '仍高')],
    'SHORT_SLEEP': [('睡眠偏短', '睡眠不足', '短睡', '睡得短'), ('疲倦', '疲劳', '注意力')],
    'EXERCISE_RECOVERED': [('运动', '活动'), ('回落', '恢复')],
    'OFF_WRIST_ARTIFACT': [('脱腕', '无效', '伪迹')],
    'BREAKUP_CONFIRMED': [('确认结束', '确认分手', '明确分开')],
    'RECONCILED': [('撤回', '收回', '继续交往')],
    'PARENT_VISIT_PENDING': [('明早', '明天'), ('陪同', '陪诊', '复诊')],
    'CARE_SHARED': [('分担', '分工', '共同承担')],
    'APOLOGY_REPAIRED': [('道歉', '更正', '撤回'), ('合作', '分工')],
    'FRIEND_BOUNDARY': [('边界', '改约', '拒绝陪同')],
    'FRIEND_SUPPORT': [('支持', '倾听', '陪伴')],
    'HOUSING_PENDING': [('未谈妥', '尚未谈妥', '待议', '再议'), ('租约有效', '租约仍有效')],
    'CREDIT_CORRECTED': [('按时交付', '按时交'), ('更正', '澄清', '撤回')],
    'RESCHEDULED': [('改到明天', '延期', '改期'), ('保留', '继续')],
    'EXTRA_DECLINED': [('拒接', '拒绝', '不接额外'), ('现有', '原任务')],
    'OFFER_PENDING': [('口头', '邀请'), ('待明天', '待回复', '未签约', '尚未正式签约')],
    'RECOVERED_APPROVAL': [('复核通过', '核对通过', '更正后通过')],
    'REVISION_PENDING': [('未完成', '待复核', '留到明天')],
    'SCOPE_REDUCED': [('缩小', '收缩'), ('部分', '范围')],
    'TASK_CANCELLED': [('本次', '本事项', '具体'), ('取消', '停止')],
    'INCOMING_SETTLED': [('已实际入账', '已到账', '收入到账')],
    'INCOMING_PROMISED': [('尚未到账', '未到账', '承诺')],
    'REFUND_SETTLED': [('退款',), ('已入账', '到账')],
    'REFUND_PENDING': [('退款',), ('待审', '未到账', '无银行入账')],
    'LOAN_DECLINED': [('试算', '未借款', '拒绝贷款')],
    'LOAN_TAKEN': [('借款', '负债'), ('已放款', '到账')],
    'FRAUD_PREVENTED': [('未转账', '阻止', '未被骗')],
    'REPAY_FULL': [('全额偿还', '全部结清', '全额还清')],
    'REPAY_PARTIAL': [('部分偿还', '部分还款')],
    'REPAIR_PAID': [('支付', '已付'), ('维修',)],
}


def has_contextual_expression(text, words):
    # Do not reward a negated positive state. Negative-state phrases (未到账等)
    # are themselves valid propositions when their leading negation is included.
    for word in words:
        for match in re.finditer(re.escape(word), text):
            prefix = re.split(r'[，。；：！？]', text[:match.start()])[-1][-8:]
            if not re.search(r'(没有|并非|并不|不代表|不是|不能|不等于|未曾|尚未|不再)(?:很|已|已经)?$', prefix):
                return True
    return False


def expressed(text, groups):
    return bool(text.strip()) and all(has_contextual_expression(text, group) for group in groups)


def grade(q, key, a):
    if q['question_id'] != key['question_id'] or q['question_id'] != a['question_id']:
        raise ValueError('Question/answer/key identity mismatch')
    if 'aa2d' in a['generator_agent'] or a['solver_agent'] == a['generator_agent']:
        raise ValueError('Self-solving disqualification')
    observations = {s['slice_id']: s for s in q['cleaned_daily_stream']}
    results, errors = {}, []
    truths = key['directional_ground_truth']
    if set(a['summaries']) != set(truths):
        raise ValueError('Incomplete dimensions')
    for d, truth in truths.items():
        sub = a['summaries'][d]
        required_refs = {r for anchor in truth['semantic_core_anchors'] for r in anchor['evidence_slice_ids']}
        submitted_refs = set(sub['evidence_refs'])
        if not required_refs <= observations.keys():
            raise ValueError('Opponent GT contains an invalid evidence reference')
        unknown = submitted_refs - observations.keys()
        missing_refs = required_refs - submitted_refs
        numerical_errors = []
        for anchor in truth['semantic_core_anchors']:
            for n in anchor.get('structured_anchors', []):
                field = NUMBER_MAP[n['field']]
                predicted = sub['numeric_facts'].get(field)
                if predicted != n['value'] or type(predicted) is not type(n['value']):
                    numerical_errors.append({'field': field, 'expected': n['value'], 'actual': predicted,
                                             'type': 'NUMERIC_MISSING' if predicted is None else 'NUMERIC_CONTRADICTION'})
        intent = truth['semantic_core_anchors'][0]['semantic_intent']
        if d == 'global_daily_summary':
            # Populated after the underlying dimensions, plus explicit causal link.
            direction = True
        elif d == 'dim:emotion':
            direction = sub['observed_status'] == 'SELF_REPORTED' and expressed(sub['summary_text'], EMOTION_GROUPS[intent])
        else:
            expected_state = STATE_MAP[intent]
            direction = sub['observed_status'] == expected_state and expressed(sub['summary_text'], STATE_GROUPS[expected_state])
        numeric_total = sum(len(an.get('structured_anchors', [])) for an in truth['semantic_core_anchors'])
        number_rate = 1 - len(numerical_errors) / max(numeric_total, 1)
        ref_rate = len(submitted_refs & required_refs) / max(len(required_refs), 1)
        results[d] = {'direction_aligned': direction, 'expected_intent': intent,
                      'submitted_state': sub['observed_status'], 'evidence_recall': ref_rate,
                      'missing_evidence_ids': sorted(missing_refs), 'unknown_evidence_ids': sorted(unknown),
                      'numeric_total': numeric_total, 'numeric_errors': numerical_errors,
                      'numeric_recall': number_rate}
        if missing_refs:
            errors.append('EVIDENCE_INCOMPLETE')
        if unknown:
            errors.append('UNSUPPORTED_REFERENCE')
        errors.extend(n['type'] for n in numerical_errors)
    # Global storyline must express the four core axes and an actual decision,
    # not merely carry a plausible global status label.
    global_sub = a['summaries']['global_daily_summary']
    global_dir = all(results[d]['direction_aligned'] for d in results if d != 'global_daily_summary')
    for d in ['dim:career', 'dim:social', 'dim:health', 'dim:finance']:
        expected = STATE_MAP[truths[d]['semantic_core_anchors'][0]['semantic_intent']]
        global_dir &= expressed(global_sub['summary_text'], STATE_GROUPS[expected])
    causal_refs = set()
    for c in truths['global_daily_summary'].get('causal_constraints', []):
        if c['relation'] == 'EXPLICIT_SELF_ATTRIBUTION':
            causal_refs.update(c['cause_evidence_slice_ids'])
            causal_refs.update(c['effect_evidence_slice_ids'])
    global_dir &= causal_refs <= set(global_sub['evidence_refs'])
    global_dir &= has_contextual_expression(global_sub['summary_text'], ('决定', '取舍', '选择', '改期'))
    results['global_daily_summary']['direction_aligned'] = bool(global_dir)
    for r in results.values():
        if not r['direction_aligned']:
            errors.append('DIRECTION_NOT_VERIFIED')
        r['score'] = 50 * r['direction_aligned'] + 25 * r['numeric_recall'] + 25 * r['evidence_recall']
    score = sum(r['score'] for r in results.values()) / len(results)
    auto_pass = score >= 90 and all(r['direction_aligned'] and not r['numeric_errors'] and not r['unknown_evidence_ids'] for r in results.values())
    return {'question_id': q['question_id'], 'score': round(score, 6), 'structured_pass': auto_pass,
            'strict_evidence_pass': auto_pass and not errors, 'errors': sorted(set(errors)), 'dimensions': results,
            'free_text_redline_certified': False}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('blind', type=Path)
    ap.add_argument('ground_truth', type=Path)
    ap.add_argument('answers', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--split', choices=['calibration', 'holdout'], required=True)
    ap.add_argument('--gt-sha256', required=True)
    args = ap.parse_args()
    if digest(args.ground_truth) != args.gt_sha256:
        ap.error('GT hash mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    counts, sums = Counter(), Counter()
    dimension_counts = defaultdict(Counter)
    samples = defaultdict(list)
    seen = set()
    with lzma.open(args.blind, 'rt') as qs, lzma.open(args.ground_truth, 'rt') as gs, lzma.open(args.answers, 'rt') as ans, \
         lzma.open(args.output / 'scores.jsonl.xz', 'xt', encoding='utf-8', preset=3) as output:
        for index, lines in enumerate(zip_longest(qs, gs, ans)):
            if any(line is None for line in lines):
                raise ValueError('Input/key/answer row-count mismatch')
            if (index < 2000) != (args.split == 'calibration'):
                continue  # In calibration, no holdout GT JSON is parsed or graded.
            q, gt, a = map(json.loads, lines)
            if q['question_id'] in seen:
                raise ValueError('Duplicate question')
            seen.add(q['question_id'])
            r = grade(q, gt, a)
            output.write(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n')
            counts['questions'] += 1
            counts['structured_pass'] += r['structured_pass']
            counts['strict_evidence_pass'] += r['strict_evidence_pass']
            sums['score'] += r['score']
            for e in r['errors']:
                counts[e] += 1
                if len(samples[e]) < 10:
                    samples[e].append(q['question_id'])
            for d, result in r['dimensions'].items():
                c = dimension_counts[d]
                c['direction_aligned'] += result['direction_aligned']
                c['evidence_recall_sum'] += result['evidence_recall']
                c['numeric_total'] += result['numeric_total']
                c['numeric_errors'] += len(result['numeric_errors'])
                c['score_sum'] += result['score']
    n = counts['questions']
    if n != (2000 if args.split == 'calibration' else 8000):
        raise ValueError('Incorrect split size')
    summary = {'split': args.split, 'counts': dict(counts), 'mean_score': sums['score'] / n,
               'dimensions': dict(dimension_counts), 'error_examples': dict(samples),
               'answers_sha256': digest(args.answers), 'gt_sha256': args.gt_sha256,
               'evaluator_sha256': digest(__file__),
               'grading_type': 'custom finite-ontology structured self-check; NOT an official or independent semantic judge',
               'weights': {'state_and_expression': 50, 'numeric_anchors': 25, 'evidence_recall': 25},
               'limitations': 'Local expression groups and negation are incomplete; arbitrary paraphrases or contradictory free text may require human review. No universal free-text redline certification. Ground-truth core_claim is never copied into an answer.'}
    with (args.output / 'summary.json').open('x', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
