#!/usr/bin/env python3
"""Optional independent full-bank JSON Schema check (requires jsonschema).

The standard-library publisher also checks chronology, references, identities,
blind-sidecar equality and financial reconciliation, which JSON Schema cannot.
This program validates data contracts only; it does not solve or score exams.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import lzma
from pathlib import Path
import platform

import jsonschema


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--schema", default="schemas/daily_life_exam.schema.json")
    parser.add_argument("--expected-count", type=int, default=10000)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    count, slices = 0, 0
    with lzma.open(args.archive, "rt", encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            validator.validate(record)
            count += 1
            slices += len(record["cleaned_daily_stream"])
    if count != args.expected_count:
        raise ValueError(f"expected {args.expected_count} exams, got {count}")
    report = {"verdict": "PASS", "check": "Draft 2020-12 JSON Schema plus format validation of every full record",
              "exam_count": count, "slice_count": slices, "archive_sha256": digest(args.archive),
              "schema_sha256": digest(args.schema), "validator_sha256": digest(__file__),
              "python_version": platform.python_version(), "jsonschema_version": version("jsonschema"),
              "completed_at": datetime.now(timezone.utc).isoformat(),
              "limits": "Contract validation, not evidence entailment, independent authorship or solver performance."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
