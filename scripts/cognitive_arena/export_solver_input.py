#!/usr/bin/env python3
"""考卷密封线导出器：生成只含题面、不含标答的做题模型输入 (export_solver_input.py).

依 governance/dispatches/TASK_DISPATCH_COGNITIVE_ARENA_DUAL_WORLD_AND_DIMENSIONS.md：
ground_truth 属「密封线内，交卷前做题模型不可见」。本脚本把 papers/ 下每一卷的题面
（persona / cleaned_daily_stream / daytime_ai_interactions）剥离标答后导出为 JSONL，
供各 Agent 战队以纯 Prompt 驱动大模型作答，严禁夹带任何标准答案字段。

运行：
    python3 scripts/cognitive_arena/export_solver_input.py
    python3 scripts/cognitive_arena/export_solver_input.py --out /tmp/solver_input.jsonl --include-legacy
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPERS_DIR = REPO_ROOT / "benchmarks" / "cognitive_arena" / "papers"
DEFAULT_OUT = REPO_ROOT / "benchmarks" / "cognitive_arena" / "solver_input" / "batch_20260917_solver_input.jsonl"

# 题面允许出现的字段白名单（其余一律视为密封内容剥离）
QUESTION_SIDE_FIELDS = (
    "question_id",
    "exam_date",
    "persona",
    "cleaned_daily_stream",
    "daytime_ai_interactions",
)
# 密封字段：标答、考官笔记，以及三个「泄题字段」
#   - title：直接写出命运主线与代偿结论，等于把考场一答案印在题面上
#   - difficulty：ADVERSARIAL_TRAP 一旦下发，考场三无需认知即可作答（propose=false）
#   - paper_type：A/B/C/D 题型标注同样会泄露「本卷是否应提炼新维度」
SEALED_FIELDS = ("ground_truth", "examiner_notes", "title", "difficulty", "paper_type")


def build_solver_input(data: Dict[str, Any]) -> Dict[str, Any]:
    """剥离标答与考官笔记，只保留做题模型可见的题面。"""
    payload = {field: data[field] for field in QUESTION_SIDE_FIELDS if field in data}
    leaked = [field for field in SEALED_FIELDS if field in payload]
    if leaked:
        raise ValueError(f"密封线破损，题面含密封字段：{leaked}")
    missing = [field for field in ("question_id", "persona", "cleaned_daily_stream") if field not in payload]
    if missing:
        raise ValueError(f"题面缺失必备字段：{missing}")
    return payload


def collect_papers(include_legacy: bool = False) -> List[Path]:
    paths = sorted(p for p in PAPERS_DIR.glob("*.json") if not p.name.startswith("batch_manifest"))
    if not include_legacy:
        paths = [p for p in paths if "paper_type" in json.loads(p.read_text(encoding="utf-8"))]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="导出做题模型输入（密封标答）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出 JSONL 路径")
    parser.add_argument("--include-legacy", action="store_true", help="一并导出无题型标注的历史标杆卷")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for path in collect_papers(args.include_legacy):
            data = json.loads(path.read_text(encoding="utf-8"))
            payload = build_solver_input(data)
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1

    print(f"已导出 {count} 卷题面 -> {out_path.relative_to(REPO_ROOT)}")
    print("提醒：ground_truth / examiner_notes / title / difficulty / paper_type 均未导出，")
    print("      属密封线内容，严禁随题面下发（difficulty 与题型标注会直接泄露考场三答案）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
