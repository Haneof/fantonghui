# -*- coding: utf-8 -*-
"""agent-aa2e 做题官运行器：跨 Git 读取对手题库 -> 清洗提纯 -> 落盘答案。

铁律五硬校验：solver_agent 与 generator_agent 相同的题直接拒绝作答。
铁律二：只写入新的答案文件（挂载 T_now），不 UPDATE/DELETE 任何历史数据。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "purifier_agent_aa2e", REPO / "src/aios_core/ingest/purifier_agent_aa2e.py")
purifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(purifier)

QUESTIONS = REPO / "benchmarks/data_cleaning/questions/questions_fantonghui.jsonl"
ANSWERS = REPO / "benchmarks/data_cleaning/answers/ans_agent_aa2e_on_fantonghui.jsonl"


def main() -> None:
    t0 = time.perf_counter()
    n = 0
    p0_hits = 0
    refused = 0
    with QUESTIONS.open(encoding="utf-8") as fin, ANSWERS.open("w", encoding="utf-8") as fout:
        for line in fin:
            q = json.loads(line)
            # 铁律五：绝不自出自做
            if q.get("generator_agent") == purifier.SOLVER_AGENT:
                refused += 1
                continue
            t_start = time.perf_counter()
            ans = purifier.purify(q)
            ans["execution_time_ms"] = round((time.perf_counter() - t_start) * 1000.0, 4)
            ans["llm_tokens_used"] = 0
            if ans.pop("p0_bypass", None):
                p0_hits += 1
            fout.write(json.dumps(ans, ensure_ascii=False) + "\n")
            n += 1
    dt = time.perf_counter() - t0
    print(f"solved={n} refused_self={refused} p0_bypass_hits={p0_hits}")
    print(f"total={dt:.2f}s avg_per_question={dt / max(n, 1) * 1000:.3f}ms")
    print(f"answers -> {ANSWERS}")


if __name__ == "__main__":
    main()
