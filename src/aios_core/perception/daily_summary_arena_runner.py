"""跨队"全天生活流多维总结"对抗跑场 CLI。

流程：读题 → 切校准/评测 → 盲视求解 → **按对手官方判分口径**阅卷 → 归因。

两套对手判分口径均在此实现（与对手仓库代码逐行对齐）：

``AA2C``（`question_bank_daily_01a0aa2c/judge.py`）
    命中红线 → 该维 0 分；neutral 维无红线即满分；
    否则 = 锚点覆盖率 × 100。总分 = 六维均值，PASS ≥ 60。

``AA2D``（`daily_summary_arena_protocol.py`）
    命中红线 → 该维 0 分且整卷 FAIL；答卷含 core_plot → 100；
    否则 = 方向命中 60（未命中 30）+ 40 × 锚点召回；
    若方向未命中且锚点召回 < 0.3 → 0。
    加权：global 0.25，其余各 0.15。PASS ≥ 80。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from aios_core.perception.daily_summary_solver import (
    AA2C_DIMS,
    AA2D_DIMS,
    DailySummarySolver,
    SolverConfig,
    assert_cross_team,
    blind_view,
    normalise,
)

AA2D_WEIGHTS: Dict[str, float] = {
    "global_daily_summary": 0.25,
    "dim:health": 0.15,
    "dim:social": 0.15,
    "dim:emotion": 0.15,
    "dim:finance": 0.15,
    "dim:career": 0.15,
}


# --------------------------------------------------------------------------
# 题库读取与标答规整
# --------------------------------------------------------------------------


def load_jsonl(path: Path, limit: int | None = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if limit is not None and len(rows) >= limit:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def gt_from_aa2c(gt_row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """把 aa2c 标答规整为求解器口径。"""
    out: Dict[str, Dict[str, Any]] = {}
    src = gt_row.get("directional_ground_truth") or {}
    for d in AA2C_DIMS:
        g = src.get(d) or {}
        out[d] = {
            "anchors": list(g.get("accepted_synonyms") or []),
            "directions": [],
            "redlines": list(g.get("red_lines") or []),
            "core": g.get("core_statement") or "",
            "neutral": bool(g.get("neutral")),
        }
    return out


def gt_from_aa2d(question: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """把 aa2d 内嵌标答规整为求解器口径。"""
    out: Dict[str, Dict[str, Any]] = {}
    src = question.get("directional_ground_truth") or {}
    for d in AA2D_DIMS:
        g = src.get(d) or {}
        out[d] = {
            "anchors": list(g.get("core_anchors") or []),
            "directions": list(g.get("acceptable_directions") or []),
            "redlines": list(g.get("redline_violations") or []),
            "core": g.get("core_plot") or "",
            "neutral": False,
        }
    return out


# --------------------------------------------------------------------------
# 阅卷（对手官方口径）
# --------------------------------------------------------------------------


def grade_aa2c(gt: Dict[str, Dict[str, Any]], answer: Dict[str, str]) -> Dict[str, Any]:
    dims: Dict[str, Any] = {}
    for d in AA2C_DIMS:
        g = gt[d]
        ans = normalise(answer.get(d, ""))
        vetoes = [r for r in g["redlines"] if r and normalise(r) in ans]
        if vetoes:
            dims[d] = {"score": 0.0, "veto": True, "hits": vetoes}
            continue
        if g.get("neutral"):
            dims[d] = {"score": 100.0, "veto": False, "hits": []}
            continue
        anchors = g["anchors"]
        if not anchors:
            dims[d] = {"score": 100.0, "veto": False, "hits": []}
            continue
        cov = sum(1 for a in anchors if a and normalise(a) in ans)
        dims[d] = {"score": round(100.0 * cov / len(anchors), 2), "veto": False, "hits": []}
    total = round(sum(v["score"] for v in dims.values()) / len(dims), 2)
    return {
        "total": total,
        "pass": total >= 60.0,
        "vetoes": [d for d, v in dims.items() if v["veto"]],
        "dims": dims,
    }


def grade_aa2d(gt: Dict[str, Dict[str, Any]], answer: Dict[str, str]) -> Dict[str, Any]:
    dims: Dict[str, Any] = {}
    fatal = False
    weighted = 0.0
    for d in AA2D_DIMS:
        g = gt[d]
        sub = normalise(answer.get(d, ""))
        core = normalise(g["core"])
        vetoes = [r for r in g["redlines"] if r and normalise(r) in sub]
        if vetoes:
            dims[d] = {"score": 0.0, "veto": True, "hits": vetoes, "dir": False, "recall": 0.0}
            fatal = True
            weighted += 0.0
            continue
        if core and (core in sub or (sub and sub in core)):
            dims[d] = {"score": 100.0, "veto": False, "hits": [], "dir": True, "recall": 1.0}
            weighted += 100.0 * AA2D_WEIGHTS[d]
            continue
        dir_hit = any(
            normalise(s) and (normalise(s) in sub or (sub and sub in normalise(s)))
            for s in g["directions"]
        )
        anchors = g["anchors"]
        recall = (
            sum(1 for a in anchors if a and normalise(a) in sub) / len(anchors)
            if anchors
            else 1.0
        )
        if not dir_hit and recall < 0.3:
            score = 0.0
        else:
            score = round((60.0 if dir_hit else 30.0) + 40.0 * recall, 2)
        dims[d] = {"score": score, "veto": False, "hits": [], "dir": dir_hit, "recall": recall}
        weighted += score * AA2D_WEIGHTS[d]
    total = 0.0 if fatal else round(weighted, 2)
    return {
        "total": total,
        "pass": total >= 80.0 and not fatal,
        "vetoes": [d for d, v in dims.items() if v["veto"]],
        "dims": dims,
    }


# --------------------------------------------------------------------------
# 跑场
# --------------------------------------------------------------------------


def run_arena(
    bank: str,
    questions: List[Dict[str, Any]],
    gts: List[Dict[str, Dict[str, Any]]],
    solver_agent: str,
    calibration_size: int,
    config: SolverConfig,
    seed: int = 20260916,
) -> Dict[str, Any]:
    """校准 → 盲解 → 阅卷。校准片与评测片严格不相交。"""
    dims = AA2C_DIMS if bank == "AA2C" else AA2D_DIMS
    grade = grade_aa2c if bank == "AA2C" else grade_aa2d

    order = list(range(len(questions)))
    random.Random(seed).shuffle(order)
    cal_idx = order[:calibration_size]
    eval_idx = order[calibration_size:]
    assert not (set(cal_idx) & set(eval_idx)), "校准片与评测片必须不相交"

    generator = str(questions[0].get("generator_agent", ""))
    assert_cross_team(solver_agent, generator)

    solver = DailySummarySolver(solver_agent=solver_agent, dims=dims, config=config)
    solver.fit((questions[i], gts[i]) for i in cal_idx)

    totals: List[float] = []
    passes = 0
    veto_papers = 0
    veto_dims = 0
    by_diff: Dict[str, List[float]] = {}
    dim_scores: Dict[str, List[float]] = {d: [] for d in dims}
    answers: List[Dict[str, Any]] = []

    for i in eval_idx:
        q = questions[i]
        ans = solver.solve(q)
        rep = grade(gts[i], ans)
        totals.append(rep["total"])
        passes += bool(rep["pass"])
        if rep["vetoes"]:
            veto_papers += 1
            veto_dims += len(rep["vetoes"])
        by_diff.setdefault(str(q.get("difficulty", "NA")), []).append(rep["total"])
        for d in dims:
            dim_scores[d].append(rep["dims"][d]["score"])
        answers.append(
            {
                "question_id": q.get("question_id"),
                "solver_agent": solver_agent,
                "generator_agent": generator,
                "answers": ans,
                "score": rep["total"],
                "pass": rep["pass"],
                "vetoes": rep["vetoes"],
            }
        )

    n = max(len(totals), 1)
    return {
        "bank": bank,
        "generator_agent": generator,
        "solver_agent": solver_agent,
        "n_total": len(questions),
        "n_calibration": len(cal_idx),
        "n_evaluated": len(totals),
        "mean_score": round(sum(totals) / n, 2),
        "pass_rate": round(passes / n, 4),
        "veto_paper_rate": round(veto_papers / n, 4),
        "veto_dim_count": veto_dims,
        "llm_calls": 0,
        "by_dimension": {d: round(sum(v) / max(len(v), 1), 2) for d, v in dim_scores.items()},
        "by_difficulty": {
            k: {"n": len(v), "mean": round(sum(v) / max(len(v), 1), 2)}
            for k, v in sorted(by_diff.items())
        },
        "config": {
            "top_k": config.top_k,
            "top_directions": config.top_directions,
            "df_ceiling": config.df_ceiling,
            "score_floor": config.score_floor,
            "redline_guard": config.redline_guard,
        },
    }, answers


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="跨队全天生活流多维总结跑场")
    ap.add_argument("--bank", choices=("AA2C", "AA2D"), required=True)
    ap.add_argument("--questions", type=Path, required=True)
    ap.add_argument("--ground-truth", type=Path, default=None, help="AA2C 需要独立标答文件")
    ap.add_argument("--solver-agent", default="agent-01a0aa2e")
    ap.add_argument("--calibration-size", type=int, default=300)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--top-k", type=int, default=14)
    ap.add_argument("--top-directions", type=int, default=8)
    ap.add_argument("--no-redline-guard", action="store_true")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--answers-out", type=Path, default=None)
    args = ap.parse_args(argv)

    questions = load_jsonl(args.questions, args.limit)
    if args.bank == "AA2C":
        if not args.ground_truth:
            ap.error("AA2C 必须提供 --ground-truth")
        gt_rows = {g["question_id"]: g for g in load_jsonl(args.ground_truth)}
        questions = [q for q in questions if q["question_id"] in gt_rows]
        gts = [gt_from_aa2c(gt_rows[q["question_id"]]) for q in questions]
    else:
        gts = [gt_from_aa2d(q) for q in questions]

    config = SolverConfig(
        top_k=args.top_k,
        top_directions=args.top_directions,
        redline_guard=not args.no_redline_guard,
    )
    report, answers = run_arena(
        args.bank, questions, gts, args.solver_agent, args.calibration_size, config
    )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.answers_out:
        args.answers_out.parent.mkdir(parents=True, exist_ok=True)
        with args.answers_out.open("w", encoding="utf-8") as fh:
            for a in answers:
                fh.write(json.dumps(a, ensure_ascii=False) + "\n")

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
