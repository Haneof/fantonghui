"""Generate exactly 10,000 fictional person-days, or audit an existing bank.

python -m benchmarks.daily_life.generator generate --output <new-directory>
python -m benchmarks.daily_life.generator validate --output <existing-directory>
"""
from __future__ import annotations

import argparse
import json
import lzma
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from . import AUTHOR, VERSION
from .build import SEED, make_question
from .validate import sha256_file, validate_bank, validate_question


def write_json(path, data):
    with Path(path).open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def generate(output, seed=SEED):
    output = Path(output)
    # No silent overwrite of a published examination or its keys.
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    raw_sizes = {"complete": 4, "blind": 0, "ground_truth": 0}
    count = 10000
    with lzma.open(output / "daily_life_10000.json.xz", "xt", encoding="utf-8", preset=6) as complete, \
         lzma.open(output / "blind_questions.jsonl.xz", "xt", encoding="utf-8", preset=6) as blind, \
         lzma.open(output / "directional_ground_truth.jsonl.xz", "xt", encoding="utf-8", preset=3) as keys:
        complete.write("[\n")
        for i in range(1, count + 1):
            q = make_question(i, seed)
            validate_question(q)
            cq = json.dumps(q, ensure_ascii=False, separators=(",", ":")) + (",\n" if i < count else "\n")
            bq = json.dumps({k: v for k, v in q.items() if k != "directional_ground_truth"}, ensure_ascii=False, separators=(",", ":")) + "\n"
            gq = json.dumps({"question_id": q["question_id"], "directional_ground_truth": q["directional_ground_truth"]}, ensure_ascii=False, separators=(",", ":")) + "\n"
            complete.write(cq)
            blind.write(bq)
            keys.write(gq)
            for name, text in [("complete", cq), ("blind", bq), ("ground_truth", gq)]:
                raw_sizes[name] += len(text.encode("utf-8"))
            if i == 1:
                write_json(output / "sample_day_00001.json", q)
            if i % 1000 == 0:
                print(f"Generated {i}/10000 person-days", flush=True)
        complete.write("]\n")
    report = validate_bank(output)
    report["audited_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "validation_report.json", report)
    code = Path(__file__).parent
    manifest = {"author_agent": AUTHOR, "version": VERSION, "seed": seed,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(), "fictional": True,
                "dataset_date": "2026-09-16", "timezone": "Asia/Shanghai", "question_count": count,
                "complete_format": "XZ-compressed UTF-8 STANDARD JSON ARRAY (exactly 10000 objects)",
                "blind_format": "XZ-compressed UTF-8 JSON Lines, no directional_ground_truth field",
                "ground_truth_format": "XZ-compressed UTF-8 JSON Lines, joined only by question_id",
                "generation_method": "Seeded compositional simulation from author-written scenario inventory; no external API or real personal records",
                "elapsed_seconds": round(time.perf_counter() - started, 3), "python": platform.python_version(),
                "source_sha256": {f.name: sha256_file(f) for f in sorted(code.glob("*.py"))},
                "uncompressed_bytes": raw_sizes,
                "artifacts": {p.name: {"bytes": p.stat().st_size, "sha256": sha256_file(p)}
                              for p in sorted(output.iterdir()) if p.is_file()},
                "cross_team_policy": "Author team must not count solving this bank as opponent evaluation; only the blind file goes to independent solvers.",
                "validation_scope": "All 10000 rows independently reparsed, blind/GT splits compared, temporal coverage, account arithmetic and evidence references checked; not independent semantic model scoring."}
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "manifest": manifest, "validation": report}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "validate"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.output, args.seed)
    else:
        manifest = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
        for name, metadata in manifest["artifacts"].items():
            if sha256_file(args.output / name) != metadata["sha256"]:
                raise ValueError(f"Artifact hash mismatch: {name}")
        print(json.dumps(validate_bank(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
