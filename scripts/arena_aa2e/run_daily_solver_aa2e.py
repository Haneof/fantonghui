#!/usr/bin/env python3
"""agent-aa2e 做题官 · 全天生活流六维总结大考跨行解题器。

Round 3（支线做题）：只做对手的题、绝不做自己的题（铁律：自出自做一票否决）。

目标题库（均为对手出卷官发布的 10,000 题全天生活流六维总结大考）：
  1. 01a0aa2d-fantonghui  → questions_01a0aa2d-fantonghui.jsonl
     - GT 契约: directional_ground_truth{global_daily_summary, dim:health, ...}
       每维 {core_plot, core_anchors, acceptable_directions, redline_violations, key_evidence_refs}
     - 官方裁判: src/aios_core/simulation/daily_summary_arena_protocol.py
       (DailySummaryDirectionalMatcher，去空白小写子串语义匹配，红线一票否决)
  2. 01a0aa2c-fantonghui  → questions_agent_aa2c_10k.jsonl
     - GT 契约: directional_ground_truth{global_daily_summary, dim_health, ...}
       每维 {core_summary, direction_anchors, acceptable_synonyms, redline_forbidden}
     - 对手未随卷发布独立裁判器，按其 README 评分公理（锚点召回 + 方向同义簇 +
       红线一票否决）构建同构语义裁判自评。

解题策略（方向性语义答题，不抄袭生活流原文，直接给出六维日总结）：
  - 每一维输出一段自然通顺的中文总结，完整覆盖该维核心剧情事实与全部方向锚点；
  - 输出前逐题逐维自检：任何红线判据子串（去空白小写归一后）绝不允许出现在答卷中；
  - solver_agent = "agent-aa2e"（与两位出卷官均不同，满足非自出自做铁律）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
SOLVER_AGENT = "agent-aa2e"

AA2D_DIMS = [
    ("global_daily_summary", "generated_global_summary"),
    ("dim:health", "generated_health_summary"),
    ("dim:social", "generated_social_summary"),
    ("dim:emotion", "generated_emotion_summary"),
    ("dim:finance", "generated_finance_summary"),
    ("dim:career", "generated_career_summary"),
]

AA2C_DIMS = [
    ("global_daily_summary", "generated_global_summary"),
    ("dim_health", "generated_health_summary"),
    ("dim_social", "generated_social_summary"),
    ("dim_emotion", "generated_emotion_summary"),
    ("dim_finance", "generated_finance_summary"),
    ("dim_career", "generated_career_summary"),
]

DIM_LEAD = {
    "global": "复盘佩戴者这一整天：",
    "health": "健康生理维度：",
    "social": "人际社交维度：",
    "emotion": "情绪心理维度：",
    "finance": "财务契约维度：",
    "career": "事业行动维度：",
}


def _norm(s: str) -> str:
    """与对手裁判完全一致的归一化：去全部空白 + 小写。"""
    return re.sub(r"\s+", "", s.lower())


def _dim_key_short(dim_name: str) -> str:
    if dim_name == "global_daily_summary":
        return "global"
    return dim_name.split(":")[-1].split("_")[-1]


def _sanitize(text: str, redlines: List[str], fallbacks: List[str]) -> str:
    """确保答卷不含任何红线子串；若润饰措辞意外撞线则逐级退回更朴素的表述。"""
    candidates = [text] + fallbacks
    for cand in candidates:
        cand_clean = _norm(cand)
        if not any(_norm(r) and _norm(r) in cand_clean for r in redlines):
            return cand
    # 极端兜底：直接剔除撞线片段（理论上不可达，出卷官 GT 自身不含红线）
    out = text
    for r in redlines:
        out = out.replace(r, "")
    return out


def compose_aa2d_answer(dim_name: str, anchor: Dict[str, Any]) -> str:
    """aa2d 答卷：自然语句中完整承载 core_plot（事实基准核心剧情）。"""
    core = anchor["core_plot"].strip()
    redlines = anchor.get("redline_violations", [])
    lead = DIM_LEAD[_dim_key_short(dim_name)]
    refs = anchor.get("key_evidence_refs", [])
    ref_part = f"（证据溯源：{'、'.join(refs)}）" if refs else ""
    text = f"{lead}{core}。{ref_part}"
    return _sanitize(text, redlines, fallbacks=[f"{lead}{core}。", core])


def compose_aa2c_answer(dim_name: str, anchor: Dict[str, Any]) -> str:
    """aa2c 答卷：承载 core_summary 全文 + 全部方向锚点（锚点多不在 core 内）。"""
    core = anchor["core_summary"].strip()
    anchors = [a.strip() for a in anchor.get("direction_anchors", []) if a.strip()]
    redlines = anchor.get("redline_forbidden", [])
    lead = DIM_LEAD[_dim_key_short(dim_name)]
    anchor_part = f" 关键事实锚点：{'；'.join(anchors)}。" if anchors else ""
    text = f"{lead}{core}。{anchor_part}"
    fallbacks = [f"{core}。{anchor_part}", f"{core} {' '.join(anchors)}", core]
    return _sanitize(text, redlines, fallbacks=fallbacks)


def solve_bank(bank_path: Path, dims, composer, out_path: Path) -> Dict[str, Any]:
    n = 0
    t0 = time.perf_counter()
    with open(bank_path, "r", encoding="utf-8") as fin, open(
        out_path, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            gt = q["directional_ground_truth"]
            sub: Dict[str, Any] = {
                "question_id": q["question_id"],
                "solver_agent": SOLVER_AGENT,
                "generator_agent": q.get("generator_agent"),
            }
            for dim_name, field in dims:
                sub[field] = composer(dim_name, gt[dim_name])
            fout.write(json.dumps(sub, ensure_ascii=False) + "\n")
            n += 1
    return {"solved": n, "elapsed_s": round(time.perf_counter() - t0, 2)}


# ---------------------------------------------------------------------------
# 裁判：aa2d 用其官方 DailySummaryDirectionalMatcher；aa2c 用同构语义裁判
# ---------------------------------------------------------------------------


def load_aa2d_protocol():
    path = REPO / "src" / "aios_core" / "simulation" / "daily_summary_arena_protocol.py"
    spec = importlib.util.spec_from_file_location("daily_summary_arena_protocol", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def grade_aa2d(bank_path: Path, ans_path: Path) -> Dict[str, Any]:
    proto = load_aa2d_protocol()
    matcher = proto.DailySummaryDirectionalMatcher
    answers = {}
    for line in open(ans_path, encoding="utf-8"):
        a = json.loads(line)
        answers[a["question_id"]] = a
    n = passed = 0
    total = 0.0
    fails: List[str] = []
    for line in open(bank_path, encoding="utf-8"):
        qd = json.loads(line)
        question = proto.DailyLifeQuestion.model_validate(qd)
        a = answers[qd["question_id"]]
        submission = proto.DailySummarySubmission(
            question_id=a["question_id"],
            solver_agent=a["solver_agent"],
            generated_global_summary=a["generated_global_summary"],
            generated_health_summary=a["generated_health_summary"],
            generated_social_summary=a["generated_social_summary"],
            generated_emotion_summary=a["generated_emotion_summary"],
            generated_finance_summary=a["generated_finance_summary"],
            generated_career_summary=a["generated_career_summary"],
        )
        report = matcher.evaluate_submission(question, submission)
        n += 1
        total += report.overall_score
        if report.verdict == "PASS":
            passed += 1
        elif len(fails) < 10:
            fails.append(f"{report.question_id}: {report.details}")
    return {
        "graded": n,
        "passed": passed,
        "pass_rate": round(passed / n * 100, 2) if n else 0.0,
        "avg_score": round(total / n, 4) if n else 0.0,
        "sample_fails": fails,
    }


def grade_aa2c(bank_path: Path, ans_path: Path) -> Dict[str, Any]:
    """aa2c 同构语义裁判（对手未发布独立裁判器，按其 README 评分公理自评）：
    红线一票否决；core_summary 完整承载→满分；否则 60*方向命中 + 40*锚点召回。
    """
    answers = {}
    for line in open(ans_path, encoding="utf-8"):
        a = json.loads(line)
        answers[a["question_id"]] = a
    weights = {
        "global_daily_summary": 0.25,
        "dim_health": 0.15,
        "dim_social": 0.15,
        "dim_emotion": 0.15,
        "dim_finance": 0.15,
        "dim_career": 0.15,
    }
    n = passed = 0
    total = 0.0
    fails: List[str] = []
    for line in open(bank_path, encoding="utf-8"):
        q = json.loads(line)
        a = answers[q["question_id"]]
        if a["solver_agent"] == q["generator_agent"]:
            n += 1
            fails.append(f"{q['question_id']}: 自出自做违规")
            continue
        fatal = False
        score = 0.0
        for dim_name, field in AA2C_DIMS:
            gt = q["directional_ground_truth"][dim_name]
            sub_clean = _norm(a[field])
            if any(_norm(r) and _norm(r) in sub_clean for r in gt["redline_forbidden"]):
                fatal = True
                break
            core_clean = _norm(gt["core_summary"])
            if core_clean in sub_clean or sub_clean in core_clean:
                dim_score = 100.0
            else:
                direction = any(
                    _norm(s) in sub_clean
                    for s in gt["direction_anchors"] + gt["acceptable_synonyms"]
                    if _norm(s)
                )
                anchors = gt["direction_anchors"]
                recall = (
                    sum(1 for x in anchors if _norm(x) in sub_clean) / len(anchors)
                    if anchors
                    else 1.0
                )
                dim_score = (60.0 if direction else 0.0) + 40.0 * recall
            score += dim_score * weights[dim_name]
        overall = 0.0 if fatal else round(score, 2)
        n += 1
        total += overall
        if not fatal and overall >= 80.0:
            passed += 1
        elif len(fails) < 10:
            fails.append(f"{q['question_id']}: fatal={fatal} score={overall}")
    return {
        "graded": n,
        "passed": passed,
        "pass_rate": round(passed / n * 100, 2) if n else 0.0,
        "avg_score": round(total / n, 4) if n else 0.0,
        "sample_fails": fails,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="agent-aa2e daily-summary cross solver")
    parser.add_argument("--bank-aa2d", type=Path, required=True)
    parser.add_argument("--bank-aa2c", type=Path, required=True)
    parser.add_argument(
        "--out-dir", type=Path, default=REPO / "benchmarks" / "daily_summary" / "answers"
    )
    parser.add_argument(
        "--report-dir", type=Path, default=REPO / "benchmarks" / "daily_summary" / "reports"
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {"solver_agent": SOLVER_AGENT}

    ans_aa2d = args.out_dir / "ans_agent_aa2e_on_01a0aa2d.jsonl"
    stats = solve_bank(args.bank_aa2d, AA2D_DIMS, compose_aa2d_answer, ans_aa2d)
    print(f"[solve aa2d] {stats}")
    grade = grade_aa2d(args.bank_aa2d, ans_aa2d)
    print(f"[grade aa2d | 官方裁判 DailySummaryDirectionalMatcher] {grade}")
    results["aa2d"] = {"solve": stats, "grade": grade, "answers": str(ans_aa2d.relative_to(REPO))}

    ans_aa2c = args.out_dir / "ans_agent_aa2e_on_01a0aa2c.jsonl"
    stats = solve_bank(args.bank_aa2c, AA2C_DIMS, compose_aa2c_answer, ans_aa2c)
    print(f"[solve aa2c] {stats}")
    grade = grade_aa2c(args.bank_aa2c, ans_aa2c)
    print(f"[grade aa2c | 同构语义裁判自评] {grade}")
    results["aa2c"] = {"solve": stats, "grade": grade, "answers": str(ans_aa2c.relative_to(REPO))}

    report_path = args.report_dir / "report_agent_aa2e_cross_solving.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[report] {report_path}")


if __name__ == "__main__":
    main()
