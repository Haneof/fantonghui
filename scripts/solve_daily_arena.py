"""Daily 题库求解运行器（Solver: 01a0aa2c-fantonghui）。

用法：
    python scripts/solve_daily_arena.py --questions /tmp/banks/daily_a2d.jsonl --gen-tag daily_01a0aa2d
    python scripts/solve_daily_arena.py --questions /tmp/banks/daily_a2e.jsonl --gen-tag daily_agent-aa2e

铁律：剥离 directional_ground_truth 盲做；solver_agent 恒为 01a0aa2c-fantonghui。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aios_core.ingest.daily_summarizer_01a0aa2c import SOLVER_AGENT, summarize

STRIP_KEYS = ("directional_ground_truth",)


def solve_file(questions_path: Path, gen_tag: str, out_path: Path, limit: int = 0) -> dict:
    n = 0
    t0 = time.perf_counter()
    max_ms = 0.0
    total_ms = 0.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(questions_path, encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            if q.get("generator_agent") == SOLVER_AGENT:
                raise SystemExit(f"拒绝自出自做：{q.get('question_id')}")
            blind = {k: v for k, v in q.items() if k not in STRIP_KEYS}
            ans = summarize(blind)
            fout.write(json.dumps(ans, ensure_ascii=False) + "\n")
            n += 1
            ms = ans.get("execution_time_ms", 0.0)
            max_ms = max(max_ms, ms)
            total_ms += ms
            if limit and n >= limit:
                break
            if n % 2000 == 0:
                print(f"  ... {n} solved", flush=True)
    dt = time.perf_counter() - t0
    return {"gen_tag": gen_tag, "count": n, "seconds": round(dt, 2),
            "avg_ms": round(total_ms / max(n, 1), 3), "max_ms": round(max_ms, 3),
            "out": str(out_path)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="")
    ap.add_argument("--gen-tag", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    qp = Path(args.questions)
    out = Path(args.out) if args.out else root / "benchmarks" / "daily_summary" / "answers" / f"ans_{SOLVER_AGENT}_on_{args.gen_tag}.jsonl"
    print(solve_file(qp, args.gen_tag, out, args.limit))


if __name__ == "__main__":
    main()
