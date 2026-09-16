# -*- coding: utf-8 -*-
"""副事件阈值扫参（训练切分自动调参 -> held-out 只做最终验证）。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "src" / "aios_core" / "ingest"))
sys.path.insert(0, str(ROOT / "scripts"))
from arena_solve_grade_01a0aa2d import load_jsonl, grade_bank, BANK_FILES
from purifier_01a0aa2d_fantonghui import AiosDataPurifier

def sweep(bank, knob, values, n=1500):
    qf, gtf = BANK_FILES[bank]
    qs = load_jsonl(ROOT / "benchmarks/data_cleaning/questions" / qf, 0, n)
    gts = load_jsonl(ROOT / "benchmarks/data_cleaning/ground_truth" / gtf, 0, n)
    for v in values:
        p = AiosDataPurifier()
        setattr(p, knob, v)
        answers = [p.solve(q) for q in qs]
        rep = grade_bank(qs, answers, gts)
        s = rep["final_scores"]
        print(f"  {bank} {knob}={v}: avg={sum(s)/len(s):.2f} pass={sum(1 for x in s if x>=90)/len(s):.1%} "
              f"dir={sum(rep['direction'])/len(s):.3f} ent={sum(rep['entity'])/len(s):.3f} halluc={rep['halluc']}")

if __name__ == "__main__":
    which = sys.argv[1]
    if which == "ft":
        sweep("fantonghui", "ft_sec_min", [4.0, 6.0, 8.0, 12.0, 16.0])
    else:
        sweep("01a0a9ff-fantonghui", "ff_sec_min", [6.0, 10.0, 14.0, 18.0, 24.0])
