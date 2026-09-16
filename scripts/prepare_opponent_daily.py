#!/usr/bin/env python3
"""Mechanical cross-Git projection, before solving; never read or print label values.

Fetch the opponent branch first. This reads only the specified paper blob, strips
all non-allowlisted fields, and stores the full original in a separate examiner
folder. Use separate process permissions for real blind evaluation; file layout
is not a security sandbox.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import lzma
from pathlib import Path
import re
import subprocess

FIELDS = ("question_id", "generator_agent", "exam_date", "persona", "cleaned_daily_stream")


def prepare(commit, branch, source_path, output, examiner_dir, expected=10000):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("pin a full Git commit SHA")
    out, examiner = Path(output), Path(examiner_dir)
    if out.resolve() == examiner.resolve() or out.resolve() in examiner.resolve().parents:
        raise ValueError("examiner files must not live in the blind output directory")
    raw = subprocess.check_output(["git", "show", f"{commit}:{source_path}"])
    records = [json.loads(line) for line in raw.splitlines()]
    ids = {q["question_id"] for q in records}
    names = {q["persona"]["name"] for q in records}
    authors = {q["generator_agent"] for q in records}
    if len(records) != expected or len(ids) != expected or len(names) != expected or len(authors) != 1:
        raise ValueError("count, person or author mismatch")
    author = next(iter(authors))
    if "01a0aa30" in author.casefold():
        raise ValueError("own-team paper prohibited")
    out.mkdir(parents=True, exist_ok=False)
    examiner.mkdir(parents=True, exist_ok=False)
    (examiner / "sealed_papers.jsonl").write_bytes(raw)
    qsha = hashlib.sha256()
    counts = Counter()
    with lzma.open(out / "questions.blind.jsonl.xz", "xt", encoding="utf-8") as blind:
        for q in records:
            b = {k: q[k] for k in FIELDS}
            line = json.dumps(b, ensure_ascii=False, separators=(",", ":")) + "\n"
            blind.write(line)
            qsha.update(line.encode())
            counts.update(s["src"] for s in b["cleaned_daily_stream"])
    blob = subprocess.check_output(["git", "rev-parse", f"{commit}:{source_path}"], text=True).strip()
    meta = {"source_branch": branch, "source_commit": commit, "source_path": source_path,
            "source_git_blob": blob, "source_sha256": hashlib.sha256(raw).hexdigest(),
            "solver_team": "01a0aa30", "generator_agent": author, "questions": expected,
            "unique_persona_names": len(names), "slice_counts": dict(counts),
            "blinding_allowlist": list(FIELDS),
            "removed_fields": ["directional_ground_truth", "archetype", "trap", "day_signature", "difficulty"],
            "blind_plain_sha256": qsha.hexdigest(),
            "blind_archive_sha256": hashlib.sha256((out / "questions.blind.jsonl.xz").read_bytes()).hexdigest(),
            "reference_judge_sha256": hashlib.sha256(Path("src/evaluator/daily_summary_aa2d_reference.py").read_bytes()).hexdigest(),
            "notes": "Projection only; did not import opponent answers, generator, or solver. Ground truth is sealed outside solver input; original full paper can be reproduced from pinned Git commit."}
    (out / "source_manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--examiner-dir", required=True)
    parser.add_argument("--expected-count", type=int, default=10000)
    args = parser.parse_args()
    prepare(args.commit, args.branch, args.source_path, args.output, args.examiner_dir, args.expected_count)
