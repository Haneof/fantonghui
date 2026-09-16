"""24h 日总结题库官方裁判（01a0aa2c-fantonghui）。

语义与 daily24h 系裁判一致：
* 单维：命中任一 forbidden_directions → 该维 0 分并整卷一票否决；
  core_content 双向子串命中 → 100；否则方向（任一 acceptable 双向命中）
  60/30 分 + 锚点召回 40 分；方向未命中且召回<0.3 → 0。
* 整卷：global 0.25 + 五维各 0.15；任一红线 → 总分 0 + FAIL；
  总分 ≥80 且无红线 → PASS。
* 自做（solver == generator）→ 0 分 FAIL。
* 与 a2d 系裁判一处有意差异：空答案按 0 分计（a2d 原协议空串双向包含恒真，空卷得满分，属裁判 bug，本裁判已修复）。

答卷字段：generated_global_summary / generated_health_summary /
generated_social_summary / generated_emotion_summary /
generated_finance_summary / generated_career_summary。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

WEIGHTS = {"global_daily_summary": 0.25, "dim:health": 0.15, "dim:social": 0.15,
           "dim:emotion": 0.15, "dim:finance": 0.15, "dim:career": 0.15}
SUBKEY = {"global_daily_summary": "generated_global_summary", "dim:health": "generated_health_summary",
          "dim:social": "generated_social_summary", "dim:emotion": "generated_emotion_summary",
          "dim:finance": "generated_finance_summary", "dim:career": "generated_career_summary"}
PASS_THRESHOLD = 80.0


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def evaluate_dimension(dim: str, submission_text: str, gt: dict) -> dict:
    sub = _clean(submission_text)
    core = _clean(gt.get("core_content", ""))
    reds = [r for r in gt.get("forbidden_directions", []) if _clean(r) and _clean(r) in sub]
    if reds:
        return {"dimension": dim, "score": 0.0, "direction_matched": False,
                "matched": None, "recalled": [], "missed": list(gt.get("anchor_entities", [])),
                "redlines": reds}
    if core and sub and (core in sub or sub in core):
        return {"dimension": dim, "score": 100.0, "direction_matched": True,
                "matched": "core_exact", "recalled": list(gt.get("anchor_entities", [])),
                "missed": [], "redlines": []}
    matched = None
    for syn in gt.get("acceptable_directions", []):
        c = _clean(syn)
        if c and sub and (c in sub or sub in c):
            matched = syn
            break
    anchors = gt.get("anchor_entities", [])
    recalled = [a for a in anchors if _clean(a) and _clean(a) in sub]
    missed = [a for a in anchors if a not in recalled]
    recall = len(recalled) / len(anchors) if anchors else 1.0
    if matched is None and recall < 0.3:
        score = 0.0
    else:
        score = round((60.0 if matched is not None else 30.0) + 40.0 * recall, 2)
    return {"dimension": dim, "score": score, "direction_matched": matched is not None,
            "matched": matched, "recalled": recalled, "missed": missed, "redlines": []}


def evaluate_paper(question: dict, submission: dict) -> dict:
    if submission.get("solver_agent") == question.get("generator_agent"):
        return {"question_id": question.get("question_id"), "overall": 0.0, "verdict": "FAIL",
                "fatal_redline": True, "dims": {},
                "details": "自出自做一票否决"}
    gt = question["directional_ground_truth"]
    dims, total, fatal = {}, 0.0, False
    for dim, w in WEIGHTS.items():
        r = evaluate_dimension(dim, submission.get(SUBKEY[dim], ""), gt[dim])
        dims[dim] = r
        total += r["score"] * w
        if r["redlines"]:
            fatal = True
    overall = 0.0 if fatal else round(total, 2)
    return {"question_id": question.get("question_id"), "overall": overall,
            "verdict": "PASS" if (overall >= PASS_THRESHOLD and not fatal) else "FAIL",
            "fatal_redline": fatal, "dims": dims,
            "details": "评审完成" if not fatal else "触碰红线一票否决"}


def evaluate_bank(questions_path: str, answers_path: str, limit: int = 0) -> dict:
    answers = {}
    with open(answers_path, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            answers[a["question_id"]] = a
    scores, verdicts, vetoes, n = [], {"PASS": 0, "FAIL": 0}, 0, 0
    dim_sum = {d: 0.0 for d in WEIGHTS}
    for line in open(questions_path, encoding="utf-8"):
        q = json.loads(line)
        qid = q["question_id"]
        if qid not in answers:
            continue
        r = evaluate_paper(q, answers[qid])
        scores.append(r["overall"])
        verdicts[r["verdict"]] += 1
        if r["fatal_redline"]:
            vetoes += 1
        for d in WEIGHTS:
            dim_sum[d] += r["dims"][d]["score"] if r["dims"] else 0.0
        n += 1
        if limit and n >= limit:
            break
    avg = round(sum(scores) / n, 4) if n else 0.0
    return {"count": n, "avg_overall": avg,
            "pass_rate": round(verdicts["PASS"] / max(n, 1), 4),
            "verdicts": verdicts, "redline_veto_papers": vetoes,
            "per_dim_avg": {d: round(v / max(n, 1), 4) for d, v in dim_sum.items()}}


if __name__ == "__main__":
    import sys
    q, a = sys.argv[1], sys.argv[2]
    lim = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    print(json.dumps(evaluate_bank(q, a, lim), ensure_ascii=False, indent=2))
