#!/usr/bin/env python3
"""Generate a deterministic 7D AIOS cleaning-arena question set.

Example::

    python scripts/generate_cleaning_questions.py \
        --generator-agent agent-01 \
        --output-dir benchmarks/data_cleaning

The command writes the question JSONL under ``questions/`` and the compact answer
key under ``ground_truth/``.  It is intentionally offline and streams records so a
10,000-question run does not retain the complete dataset in memory.
"""

from __future__ import annotations

from aios_core.simulation.question_generator import main


if __name__ == "__main__":
    raise SystemExit(main())
