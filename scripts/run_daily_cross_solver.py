#!/usr/bin/env python3
"""Solve a pinned, blinded opponent daily bank; no truth argument or evaluator import."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import lzma
from pathlib import Path
import subprocess
from time import perf_counter

from aios_core.summaries.cross_team_daily_solver import BlindDailyQuestion, DailyCrossSolver, DailyCrossSolverV2, SELF_ALIASES


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows(path):
    with lzma.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield BlindDailyQuestion.model_validate_json(line)


def run(questions, source_manifest, output, expected=10000, version="v2"):
    manifest = json.loads(Path(source_manifest).read_text(encoding="utf-8"))
    if sha(questions) != manifest["blind_archive_sha256"]:
        raise ValueError("input provenance hash mismatch")
    seen = set()
    for q in rows(questions):
        if q.question_id in seen:
            raise ValueError("duplicate question")
        if q.generator_agent.casefold() in {a.casefold() for a in SELF_ALIASES} or "01a0aa30" in q.generator_agent.casefold():
            raise ValueError("self-solving violation")
        if q.generator_agent != manifest["generator_agent"]:
            raise ValueError("opponent identity mismatch")
        seen.add(q.question_id)
    if len(seen) != expected or len(seen) != manifest["questions"]:
        raise ValueError("wrong question count")
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    if version not in ("v1", "v2"):
        raise ValueError("unknown solver version")
    solver = DailyCrossSolverV2() if version == "v2" else DailyCrossSolver()
    now = datetime.now(timezone.utc)
    start = perf_counter()
    answer_count = 0
    max_chars = 0
    with lzma.open(out / "answers.jsonl.xz", "xt", encoding="utf-8") as answers, \
         lzma.open(out / "audit.jsonl.xz", "xt", encoding="utf-8") as audits:
        for q in rows(questions):
            answer, audit = solver.solve(q, now=now)
            answers.write(json.dumps(answer, ensure_ascii=False, separators=(",", ":")) + "\n")
            audits.write(json.dumps(audit, ensure_ascii=False, separators=(",", ":")) + "\n")
            answer_count += 1
            max_chars = max(max_chars, sum(len(v) for k, v in answer.items() if k.startswith("generated_")))
    result = {"questions": answer_count, "solver_version": solver.version, "solver_agent": "agent-solver-01a0aa30",
              "generator_agent": manifest["generator_agent"], "source_commit": manifest["source_commit"],
              "source_manifest_sha256": sha(source_manifest), "blind_archive_sha256": sha(questions),
              "solver_sha256": sha("src/aios_core/summaries/cross_team_daily_solver.py"),
              "runner_sha256": sha(__file__), "started_at": now.isoformat(),
              "finished_at": datetime.now(timezone.utc).isoformat(), "wall_time_ms": (perf_counter() - start) * 1000,
              "llm_calls": 0, "world_calls": 0, "maximum_total_summary_characters": max_chars,
              "branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
              "method": "deterministic rules; no runtime LLM or medical real-time claims",
              "artifacts": {p.name: sha(p) for p in sorted(out.glob("*.xz"))}}
    (out / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-count", type=int, default=10000)
    parser.add_argument("--version", choices=["v1", "v2"], default="v2")
    args = parser.parse_args()
    run(args.questions, args.source_manifest, args.output, args.expected_count, args.version)
