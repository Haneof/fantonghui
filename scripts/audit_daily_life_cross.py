#!/usr/bin/env python3
"""Audit frozen daily-answer artifacts without loading ground truth or solver."""
import argparse
import hashlib
import json
import lzma
from collections import Counter
from itertools import zip_longest
from pathlib import Path

FIELDS = {'global_daily_summary': 'generated_global_summary', 'dim:health': 'generated_health_summary',
          'dim:social': 'generated_social_summary', 'dim:emotion': 'generated_emotion_summary',
          'dim:finance': 'generated_finance_summary', 'dim:career': 'generated_career_summary'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def audit(blind, run):
    run = Path(run)
    m = json.loads((run / 'manifest.json').read_text())
    require(sha(blind) == m['blind_sha256'], 'Blind hash mismatch')
    require(sha(run / 'answers.jsonl.xz') == m['answers_sha256'], 'Answer hash mismatch')
    ids, people, totals = set(), set(), Counter()
    with lzma.open(blind, 'rt') as qf, lzma.open(run / 'answers.jsonl.xz', 'rt') as af:
        for lines in zip_longest(qf, af):
            require(all(line is not None for line in lines), 'Row count mismatch')
            q, a = map(json.loads, lines)
            digest = hashlib.sha256(json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            require(a['input_record_sha256'] == digest, 'Per-question source hash mismatch')
            require(q['question_id'] == a['question_id'] and a['question_id'] not in ids, 'Question identity mismatch')
            require(q['persona']['person_id'] == a['person_id'] and a['person_id'] not in people, 'Person identity mismatch')
            ids.add(a['question_id'])
            people.add(a['person_id'])
            require(a['generator_agent'] == m['generator_agent'] and 'aa2d' not in a['generator_agent'].lower(), 'Self-solving')
            require(a['solver_agent'] == m['solver_agent'], 'Solver mismatch')
            require(a['recorded_at'] == m['recorded_at'], 'Recording time mismatch')
            require(a['source_day'] == q['persona']['date'], 'Historical event date changed')
            require(a['llm_calls'] == a['llm_tokens_used'] == 0, 'Model-call claim changed')
            require(set(a['summaries']) == set(FIELDS), 'Missing dimensions')
            sources = {s['slice_id']: s for s in q['cleaned_daily_stream']}
            for d, field in FIELDS.items():
                b = a['summaries'][d]
                refs = b['evidence_refs']
                require(refs and len(refs) == len(set(refs)) and set(refs) <= sources.keys(), 'Invalid evidence references')
                require(b['summary_text'] == a[field] and b['summary_text'].strip(), 'Submission alias/text mismatch')
                totals['valid_dimension_submissions'] += 1
            txs = {}
            for s in sources.values():
                if s.get('transaction', {}).get('status') == 'SETTLED':
                    t = s['transaction']
                    require(t['transaction_id'] not in txs or txs[t['transaction_id']] == t, 'Conflicting duplicate transaction')
                    txs[t['transaction_id']] = t
            numeric = a['summaries']['dim:finance']['numeric_facts']
            final = next(s['measurements'] for s in reversed(q['cleaned_daily_stream']) if 'net_cashflow_cents' in s.get('measurements', {}))
            opening = next(s['measurements'] for s in q['cleaned_daily_stream'] if s['speaker_or_source'] == '银行日初快照')
            require(numeric['net_cashflow_cents'] == sum(t['amount_cents'] for t in txs.values()) == final['net_cashflow_cents'], 'Transaction sum mismatch')
            require(numeric['opening_balance_cents'] == opening['cash_balance_cents'], 'Opening balance mismatch')
            require(numeric['opening_balance_cents'] + numeric['net_cashflow_cents'] == numeric['closing_balance_cents'], 'Cash reconciliation mismatch')
            require(numeric['ordinary_expense_cents'] == -sum(t['amount_cents'] for t in txs.values() if t.get('category') == 'ordinary_expense'), 'Expense ledger mismatch')
            principal_change = sum(t['amount_cents'] for t in txs.values() if t.get('category') in {'new_loan_principal', 'principal_repayment'})
            require(opening['loan_principal_cents'] + principal_change == numeric['closing_loan_principal_cents'], 'Principal reconciliation mismatch')
            require(numeric['closing_balance_cents'] == final['cash_balance_cents'], 'Closing balance mismatch')
            require(numeric['closing_loan_principal_cents'] == final['loan_principal_cents'], 'Debt balance mismatch')
            require(numeric['ordinary_expense_cents'] == final['ordinary_expense_cents'], 'Ordinary expense mismatch')
            totals['deduplicated_settled_transactions'] += len(txs)
            totals['questions'] += 1
            totals['input_slices'] += len(sources)
    require(totals['questions'] == 10000, 'Expected 10000 people')
    require(totals['input_slices'] == m['counts']['input_slices'], 'Manifest count mismatch')
    return {'verdict': 'PASS', 'totals': dict(totals), 'answers_sha256': m['answers_sha256'],
            'checks': ['source/artifact SHA256', '10000 distinct people', 'six dimensions and submission aliases',
                       'evidence reference existence', 'recorded-now versus historical date', 'ledger reconciliation'],
            'limits': 'This audit checks identity, provenance and arithmetic; it is not semantic correctness certification.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('blind', type=Path)
    p.add_argument('run', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    result = audit(args.blind, args.run)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
