"""aa30 盲卷求解运行器（Solver: 01a0aa2c-fantonghui，跨队交叉做题）。

用法：
    python scripts/solve_daily_arena_aa30.py --blind /tmp/aa30/questions_10000_people.blind.jsonl.xz

铁律：只读盲卷（不含标答）；solver_agent 恒为 01a0aa2c-fantonghui；
      引擎层已内置自出自做拒绝（generator_agent 命中本战队即抛错）。
"""
from __future__ import annotations

import argparse
import json
import lzma
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aios_core.ingest.daily_solver_aa30_01a0aa2c import SOLVER_AGENT, solve  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="aa30 盲卷求解")
    ap.add_argument("--blind", type=Path, default=Path("/tmp/aa30/questions_10000_people.blind.jsonl.xz"))
    ap.add_argument("--out", type=Path, default=Path(
        "benchmarks/daily_summary/answers/ans_01a0aa2c-fantonghui_on_daily-examiner-01a0aa30.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    n = 0
    t0 = time.perf_counter()
    max_ms = 0.0
    total_ms = 0.0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    opener = lzma.open if str(args.blind).endswith(".xz") else open
    with opener(args.blind, "rt", encoding="utf-8") as fin, \
            open(args.out, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            ans = solve(q)  # 引擎内置自做拒绝
            fout.write(json.dumps(ans, ensure_ascii=False) + "\n")
            n += 1
            ms = ans.get("execution_time_ms", 0.0)
            max_ms = max(max_ms, ms)
            total_ms += ms
            if n % 2000 == 0:
                print(f"  ... {n} solved ({time.perf_counter() - t0:.1f}s)", flush=True)
            if args.limit and n >= args.limit:
                break
    dt = time.perf_counter() - t0
    print(json.dumps({
        "solver_agent": SOLVER_AGENT,
        "target": "daily-examiner-01a0aa30",
        "count": n,
        "wall_seconds": round(dt, 2),
        "avg_ms": round(total_ms / max(n, 1), 3),
        "max_ms": round(max_ms, 3),
        "out": str(args.out),
        "llm_calls": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
