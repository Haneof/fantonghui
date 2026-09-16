"""Authoring regression tests, NOT self-solving or scored examination attempts.

Uses only the standard library: python -m unittest tests.simulation.test_daily_life_question_bank
"""
import copy
import json
import lzma
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from benchmarks.daily_life.generator.__main__ import generate
from benchmarks.daily_life.generator.build import make_question, name_at
from benchmarks.daily_life.generator.validate import DIMENSIONS, iter_complete, validate_bank, validate_question


class DailyLifeAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = make_question(1)
        cls.examples = [make_question(i) for i in range(1, 73)]

    def test_repeatable_generation(self):
        self.assertEqual(make_question(1), self.sample)
        self.assertNotEqual(make_question(1, seed=1234), self.sample)

    def test_index_range_is_bounded(self):
        for index in [0, -1, 10001]:
            with self.assertRaises(ValueError):
                make_question(index)

    def test_ten_thousand_unique_person_names(self):
        self.assertEqual(len({name_at(i) for i in range(1, 10001)}), 10000)

    def test_role_coverage_and_all_example_invariants(self):
        self.assertEqual(len({q['persona']['occupation'] for q in self.examples}), 12)
        for q in self.examples:
            validate_question(q)

    def test_exact_contiguous_day_not_only_waking_hours(self):
        stream = self.sample['cleaned_daily_stream']
        self.assertEqual(stream[0]['timestamp'], '2026-09-16T00:00:00+08:00')
        self.assertEqual(stream[-1]['end_timestamp'], '2026-09-17T00:00:00+08:00')
        total = sum((datetime.fromisoformat(s['end_timestamp']) - datetime.fromisoformat(s['timestamp'])).total_seconds() for s in stream)
        self.assertEqual(total, 86400)
        self.assertGreaterEqual(len(stream), 220)

    def test_six_dimensions_with_nonliteral_directional_rubrics(self):
        gt = self.sample['directional_ground_truth']
        self.assertEqual(set(gt), set(DIMENSIONS))
        for block in gt.values():
            self.assertGreaterEqual(len(block['acceptable_directional_paraphrases']), 3)
            self.assertIn('不得要求逐字', block['scoring_policy'])
            self.assertTrue(all('否定' in r['applies_only_when'] for r in block['red_line_criteria']))

    def test_gap_rejected(self):
        q = copy.deepcopy(self.sample)
        q['cleaned_daily_stream'][0]['end_timestamp'] = '2026-09-16T05:00:00+08:00'
        with self.assertRaisesRegex(ValueError, 'Gap'):
            validate_question(q)

    def test_dangling_evidence_rejected(self):
        q = copy.deepcopy(self.sample)
        q['directional_ground_truth']['dim:social']['semantic_core_anchors'][0]['evidence_refs'] = ['not-a-slice']
        with self.assertRaisesRegex(ValueError, 'evidence reference'):
            validate_question(q)

    def test_unknown_ground_truth_person_rejected(self):
        q = copy.deepcopy(self.sample)
        q['directional_ground_truth']['dim:social']['semantic_core_anchors'][0]['entity_ids'] = ['unobserved-person']
        with self.assertRaisesRegex(ValueError, 'unobservable actor'):
            validate_question(q)

    def test_false_financial_total_rejected(self):
        q = copy.deepcopy(self.sample)
        snapshot = next(s['account_summary'] for s in q['cleaned_daily_stream'] if 'account_summary' in s)
        snapshot['closing_balance_cents'] += 100
        with self.assertRaisesRegex(ValueError, 'Cash reconciliation'):
            validate_question(q)

    def test_wrong_financial_owner_rejected(self):
        q = copy.deepcopy(self.sample)
        tx = next(s['transaction'] for s in q['cleaned_daily_stream'] if 'transaction' in s)
        tx['owner_id'] = q['persona']['contacts'][0]['entity_id']
        with self.assertRaisesRegex(ValueError, 'ownership'):
            validate_question(q)

    def test_backward_step_count_rejected(self):
        q = copy.deepcopy(self.sample)
        q['cleaned_daily_stream'][-1]['measurements']['cumulative_steps'] = 0
        with self.assertRaisesRegex(ValueError, 'went backwards'):
            validate_question(q)

    def test_bad_sleep_arithmetic_rejected(self):
        q = copy.deepcopy(self.sample)
        m = next(s['measurements'] for s in q['cleaned_daily_stream'] if 'sleep_minutes' in s.get('measurements', {}))
        m['sleep_minutes'] += 10
        with self.assertRaisesRegex(ValueError, 'Sleep arithmetic'):
            validate_question(q)

    def test_unsupported_answer_number_rejected(self):
        q = copy.deepcopy(self.sample)
        numeric = q['directional_ground_truth']['dim:finance']['semantic_core_anchors'][1]['numeric_anchors']
        numeric['major_item_cents'] += 1
        with self.assertRaisesRegex(ValueError, 'amount is absent'):
            validate_question(q)

    def test_off_wrist_quality_not_presented_as_valid_health_measurement(self):
        q = next(q for q in self.examples if '脱腕' in q['directional_ground_truth']['dim:health']['core_summary'])
        anchor = q['directional_ground_truth']['dim:health']['semantic_core_anchors'][1]
        self.assertFalse(anchor['numeric_anchors']['onset_measurement_valid'])
        bad = copy.deepcopy(q)
        bad['directional_ground_truth']['dim:health']['semantic_core_anchors'][1]['numeric_anchors']['onset_measurement_valid'] = True
        with self.assertRaisesRegex(ValueError, 'quality lack support'):
            validate_question(bad)

    def test_signed_loan_not_disbursed(self):
        q = next(q for q in self.examples if '合同已确认但尚未放款' in q['directional_ground_truth']['dim:finance']['core_summary'])
        snapshot = next(s['account_summary'] for s in q['cleaned_daily_stream'] if 'account_summary' in s)
        self.assertEqual(snapshot['new_disbursed_principal_cents'], 0)
        self.assertEqual(snapshot['posted_credits_cents'], 0)

    def test_urgent_day_does_not_claim_normal_home_sleep(self):
        q = next(q for q in self.examples if '已赴急诊' in q['directional_ground_truth']['dim:health']['core_summary'])
        self.assertIn('急诊留观', q['cleaned_daily_stream'][-1]['text'])
        self.assertIn('未入睡', q['cleaned_daily_stream'][-1]['text'])

    def test_hidden_importance_label_rejected(self):
        q = copy.deepcopy(self.sample)
        q['cleaned_daily_stream'][2]['is_core'] = True
        with self.assertRaisesRegex(ValueError, 'leaked'):
            validate_question(q)

    def test_existing_bank_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):
                generate(d)

    def test_stream_format_is_also_standard_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bank.json.xz'
            with lzma.open(path, 'wt', encoding='utf-8') as f:
                f.write('[\n' + json.dumps(self.sample, ensure_ascii=False) + '\n]\n')
            self.assertEqual(list(iter_complete(path)), [self.sample])
            with lzma.open(path, 'rt', encoding='utf-8') as f:
                self.assertEqual(json.load(f), [self.sample])

    def test_trailing_comma_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bad.json.xz'
            with lzma.open(path, 'wt', encoding='utf-8') as f:
                f.write('[\n{},\n]\n')
            with self.assertRaisesRegex(ValueError, 'trailing comma'):
                list(iter_complete(path))

    def test_duplicate_person_bank_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            q = self.sample
            with lzma.open(root / 'daily_life_10000.json.xz', 'wt', encoding='utf-8') as f:
                f.write('[\n' + json.dumps(q) + ',\n' + json.dumps(q) + '\n]\n')
            for filename, record in [('blind_questions.jsonl.xz', {k: v for k, v in q.items() if k != 'directional_ground_truth'}),
                                      ('directional_ground_truth.jsonl.xz', {'question_id': q['question_id'], 'directional_ground_truth': q['directional_ground_truth']})]:
                with lzma.open(root / filename, 'wt', encoding='utf-8') as f:
                    f.write((json.dumps(record) + '\n') * 2)
            with self.assertRaisesRegex(ValueError, 'Duplicate question'):
                validate_bank(root, expected_count=2)


if __name__ == '__main__':
    unittest.main()
