"""样卷方向性阅卷器（无 LLM 基线版）。

模型作答格式：{"global": str, "dim:health": str, ...} 六维各一段。
判分：任一红线命中 → 该维 0 分并标记 veto；否则锚点覆盖率 × 100。
neutral 维：无红线即满分（缺席不断言即正确）。
总分 = 六维均值；PASS ≥ 60。
"""
from __future__ import annotations

from typing import Any, Dict, List

from .pools import DIM_ORDER

PASS_SCORE = 60.0


def _norm(s: str) -> str:
    return (s or "").replace(" ", "").replace("　", "")


def score_dim(gt_dim: Dict[str, Any], answer: str) -> Dict[str, Any]:
    ans = _norm(answer)
    veto_hits = [r for r in gt_dim.get("redlines", []) if r and _norm(r) in ans]
    if veto_hits:
        return {"score": 0.0, "veto": True, "veto_hits": veto_hits,
                "covered": [], "missed": [a["key"] for a in gt_dim.get("anchors", [])]}
    if gt_dim.get("neutral"):
        return {"score": 100.0, "veto": False, "veto_hits": [],
                "covered": ["(neutral)abstain"], "missed": []}
    covered, missed = [], []
    for a in gt_dim.get("anchors", []):
        cands = [a["key"], *a.get("accept", [])]
        if any(c and _norm(c) in ans for c in cands):
            covered.append(a["key"])
        else:
            missed.append(a["key"])
    n = len(covered) + len(missed)
    score = 100.0 * len(covered) / n if n else 100.0
    return {"score": round(score, 2), "veto": False, "veto_hits": [],
            "covered": covered, "missed": missed}


def score_paper(gt: Dict[str, Any], answer: Dict[str, str]) -> Dict[str, Any]:
    dims: Dict[str, Any] = {}
    for dim in DIM_ORDER:
        dims[dim] = score_dim(gt[dim], answer.get(dim, ""))
    total = round(sum(d["score"] for d in dims.values()) / len(dims), 2)
    vetoes = [d for d, r in dims.items() if r["veto"]]
    return {"total": total, "pass": total >= PASS_SCORE, "vetoes": vetoes, "dims": dims}


def score_bank(gts: List[Dict[str, Any]],
               answers: List[Dict[str, str]]) -> Dict[str, Any]:
    assert len(gts) == len(answers), "标答与作答数量不一致"
    per = [score_paper(g, a) for g, a in zip(gts, answers)]
    avg = round(sum(p["total"] for p in per) / len(per), 2) if per else 0.0
    pass_rate = round(sum(1 for p in per if p["pass"]) / len(per), 4) if per else 0.0
    veto_rate = round(sum(len(p["vetoes"]) for p in per) / (len(per) * len(DIM_ORDER)), 4) if per else 0.0
    return {"n": len(per), "avg": avg, "pass_rate": pass_rate,
            "veto_rate": veto_rate, "papers": per}
