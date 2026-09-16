"""跨 Git 对手题库求解运行器（Solver: 01a0aa2c-fantonghui）。

用法：
    python scripts/solve_cleaning_arena.py --questions /tmp/opp/questions_agent_11.jsonl --gen-tag agent_11
    python scripts/solve_cleaning_arena.py --all  # 求解 /tmp/opp 下全部对手题库

铁律遵循：
* 求解前主动剥离 ground_truth_*/is_junk/junk_tag/note（盲做证明）；
* solver_agent 恒为 01a0aa2c-fantonghui，与任何出题方不同（防自做）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aios_core.ingest.purifier_01a0aa2c_fantonghui import SOLVER_AGENT, UniversalPurifier

STRIP_KEYS = ("ground_truth_facts", "ground_truth_junk_ids")
STRIP_ITEM_KEYS = ("is_junk", "junk_tag", "note")


def blind_question(q: dict) -> dict:
    """剥离一切答案泄漏字段，返回盲题。"""
    q = {k: v for k, v in q.items() if k not in STRIP_KEYS}
    for stream in ("mic_stream", "app_message_stream", "user_dialogue_stream"):
        items = q.get(stream)
        if isinstance(items, list):
            q[stream] = [{k: v for k, v in (it.items() if isinstance(it, dict) else []) if k not in STRIP_ITEM_KEYS}
                         if isinstance(it, dict) else it for it in items]
    ss = q.get("sensor_stream")
    if isinstance(ss, dict):
        ss = dict(ss)
        if isinstance(ss.get("fragments"), list):
            ss["fragments"] = [{k: v for k, v in f.items() if k not in STRIP_ITEM_KEYS} if isinstance(f, dict) else f
                                for f in ss["fragments"]]
        q["sensor_stream"] = ss
    vc = q.get("voiceprint_cluster")
    if isinstance(vc, dict):
        vc = dict(vc)
        if isinstance(vc.get("speakers"), list):
            vc["speakers"] = [{k: v for k, v in s.items() if k not in STRIP_ITEM_KEYS} if isinstance(s, dict) else s
                               for s in vc["speakers"]]
        q["voiceprint_cluster"] = vc
    return q


def solve_file(questions_path: Path, gen_tag: str, out_path: Path, limit: int = 0) -> dict:
    purifier = UniversalPurifier()
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
            ans = purifier.purify(blind_question(q))
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
            "p0_count": purifier.stats["p0_count"], "out": str(out_path)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="")
    ap.add_argument("--gen-tag", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.all:
        opp = Path("/tmp/opp")
        jobs = [
            (opp / "questions_agent_11.jsonl", "agent_11"),
            (opp / "questions_agent_a9f6.jsonl", "agent_a9f6"),
            (opp / "questions_fantonghui.jsonl", "fantonghui"),
            (opp / "questions_01a0a9ff-fantonghui.jsonl", "01a0a9ff-fantonghui"),
            (opp / "questions_agent-01.jsonl", "agent-01"),
        ]
        for qp, tag in jobs:
            if not qp.exists():
                print(f"SKIP missing {qp}")
                continue
            out = root / "benchmarks" / "data_cleaning" / "answers" / f"ans_{SOLVER_AGENT}_on_{tag}.jsonl"
            print(f"Solving {qp.name} -> {out.name} ...", flush=True)
            print(" ", solve_file(qp, tag, out, args.limit), flush=True)
    else:
        qp = Path(args.questions)
        out = Path(args.out) if args.out else root / "benchmarks" / "data_cleaning" / "answers" / f"ans_{SOLVER_AGENT}_on_{args.gen_tag}.jsonl"
        print(solve_file(qp, args.gen_tag, out, args.limit))


if __name__ == "__main__":
    main()
