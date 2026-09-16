#!/usr/bin/env python3
"""Freeze 10,000 cross-team daily summaries from a blind XZ JSONL bank.

No ground-truth CLI option. Use a new output directory for every version.
"""
import argparse
import hashlib
import json
import lzma
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ai_worker.daily_life_cross_solver import DIMS, SOLVER, summarize


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('blind', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--generator', required=True)
    ap.add_argument('--source-commit', required=True)
    ap.add_argument('--source-path', required=True)
    ap.add_argument('--expected-sha256', required=True)
    ap.add_argument('--version', type=int, choices=[1, 2], default=1)
    a = ap.parse_args()
    if sha(a.blind) != a.expected_sha256:
        ap.error('Blind-bank hash mismatch')
    a.output.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc)
    manifest = {'solver_agent': SOLVER, 'generator_agent': a.generator, 'version': a.version,
                'source_commit': a.source_commit, 'source_path': a.source_path,
                'blind_sha256': a.expected_sha256, 'recorded_at': now.isoformat(),
                'python': platform.python_version(), 'mode': 'deterministic rules and grounded extraction; no external model',
                'calibration_split': 'first 2000 input rows', 'holdout_split': 'remaining 8000 rows; no GT inspection until V2 frozen',
                'code_sha256': {p: sha(p) for p in ['src/ai_worker/daily_life_cross_solver.py', 'scripts/run_daily_life_cross.py']}}
    ids, people, latencies = set(), set(), []
    counts, states = Counter(), Counter()
    with lzma.open(a.blind, 'rt', encoding='utf-8') as bank, lzma.open(a.output / 'answers.jsonl.xz', 'xt', encoding='utf-8', preset=3) as dest:
        for line in bank:
            q = json.loads(line)
            qid, pid = q['question_id'], q['persona']['person_id']
            if qid in ids or pid in people:
                raise ValueError('Duplicate question or person')
            ids.add(qid)
            people.add(pid)
            answer = summarize(q, generator_agent=a.generator, now=now, version=a.version)
            refs = {s['slice_id'] for s in q['cleaned_daily_stream']}
            for dimension in DIMS:
                block = answer['summaries'][dimension]
                if not set(block['evidence_refs']) <= refs:
                    raise ValueError('Dangling evidence')
                states[dimension + ':' + block['observed_status']] += 1
            dest.write(json.dumps(answer, ensure_ascii=False, separators=(',', ':')) + '\n')
            counts['questions'] += 1
            counts['input_slices'] += len(q['cleaned_daily_stream'])
            counts['dimensions_submitted'] += len(answer['summaries'])
            latencies.append(answer['execution_time_ms'])
    if len(ids) != 10000:
        raise ValueError('This cross-exam requires exactly 10000 unique people')
    if sha(a.blind) != a.expected_sha256:
        raise ValueError('Input changed')
    manifest.update({'counts': dict(counts), 'states': dict(states), 'llm_calls': 0, 'database_writes': 0,
                     'raw_evidence_deletions': 0, 'execution_max_ms': max(latencies),
                     'execution_mean_ms': sum(latencies) / len(latencies),
                     'answers_sha256': sha(a.output / 'answers.jsonl.xz'),
                     'frozen_at': datetime.now(timezone.utc).isoformat()})
    with (a.output / 'manifest.json').open('x', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
