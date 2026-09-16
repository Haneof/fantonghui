"""样卷出卷 CLI：生成、自审、落盘。

自审（audit）写盘前跑，任一条不过直接抛错：
1. 题量严格等于 N；
2. question_id 全局唯一；slice_id 题内唯一；时刻升序且落在 07:00~23:30；
3. 六维标答齐全，每维 core/anchors(key+accept)/redlines 非空；
4. 溯源：非 neutral 维 + global 的每个锚点（key 或其 accept）必须原文出现在本卷生活流中；
5. 熵底线：persona≥12 种、arc≥15 种、无整卷重复；
6. 每卷 15~25 切片，且 mic≥3、app≥3、sensor≥2。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from .builder import PaperBuilder, eligible_arcs, split_ground_truth
from .pools import ARCS, DIM_ORDER, PERSONAS

HERE = Path(__file__).resolve().parent
QDIR = HERE.parent / "questions"
GTDIR = HERE.parent / "ground_truth"


def _plan(rng: random.Random, n: int) -> List[tuple]:
    """persona 轮转 × 弧覆盖均衡（用量最少的合格弧优先，保证熵底线）。"""
    use = Counter()
    plan = []
    personas = PERSONAS[:]
    for i in range(n):
        if i % len(personas) == 0:
            rng.shuffle(personas)
        p = personas[i % len(personas)]
        cands = eligible_arcs(p)
        cands.sort(key=lambda a: (use[a["id"]], rng.random()))
        a = cands[0]
        use[a["id"]] += 1
        plan.append((p, a))
    return plan


def _stream_blob(q: Dict[str, Any]) -> str:
    parts = []
    for s in q["cleaned_daily_stream"]:
        parts.append(s.get("scene", ""))
        parts.append(s.get("speaker", ""))
        parts.append(s.get("source", ""))
        parts.append(s["text"])
    return "\n".join(parts)


def audit(papers: List[Dict[str, Any]], n: int) -> Dict[str, Any]:
    assert len(papers) == n, f"题量 {len(papers)} != {n}"
    qids = [p["question_id"] for p in papers]
    assert len(set(qids)) == n, "question_id 重复"
    personas, arcs, hashes = set(), Counter(), set()
    for p in papers:
        assert set(p["persona"].keys()) == {"name", "age", "gender", "job", "city",
                                            "family", "finance", "health"}, \
            f"{p['question_id']} persona 字段缺失"
        sl = p["cleaned_daily_stream"]
        assert 15 <= len(sl) <= 25, f"{p['question_id']} 切片数 {len(sl)} 越界"
        sids = [s["slice_id"] for s in sl]
        assert len(set(sids)) == len(sids), f"{p['question_id']} slice_id 重复"
        times = [s["time"] for s in sl]
        assert times == sorted(times), f"{p['question_id']} 时刻未排序"
        assert all("07:00" <= t <= "23:30" for t in times), f"{p['question_id']} 时刻越界"
        mods = Counter(s["modality"] for s in sl)
        assert mods["mic"] >= 3 and mods["app"] >= 3 and mods["sensor"] >= 2, \
            f"{p['question_id']} 模态不足 {dict(mods)}"
        gt = p["directional_ground_truth"]
        assert list(gt.keys()) == DIM_ORDER, f"{p['question_id']} 维度缺失"
        blob = _stream_blob(p)
        for dim in DIM_ORDER:
            d = gt[dim]
            assert d.get("core"), f"{p['question_id']}/{dim} core 空"
            assert d.get("anchors"), f"{p['question_id']}/{dim} anchors 空"
            assert all(a.get("key") and a.get("accept") for a in d["anchors"]), \
                f"{p['question_id']}/{dim} 锚点缺 key/accept"
            assert d.get("redlines"), f"{p['question_id']}/{dim} redlines 空"
            if not d.get("neutral"):
                for a in d["anchors"]:
                    cands = [a["key"], *a["accept"]]
                    assert any(c in blob for c in cands), \
                        f"{p['question_id']}/{dim} 锚点悬空：{a['key']}"
        personas.add(p["persona"]["name"])
        arcs[p["arc_id"]] += 1
        h = hashlib.md5(json.dumps(sl, ensure_ascii=False).encode()).hexdigest()
        assert h not in hashes, "整卷重复"
        hashes.add(h)
    assert len(personas) >= 12, f"persona 仅 {len(personas)} 种"
    assert len(arcs) >= 15, f"arc 仅 {len(arcs)} 种"
    return {"n": n, "personas": len(personas), "arcs": dict(arcs),
            "min_arc_use": min(arcs.values())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    builder = PaperBuilder(rng)
    papers = [builder.build(i + 1, p, a) for i, (p, a) in enumerate(_plan(rng, args.n))]
    stats = audit(papers, args.n)
    QDIR.mkdir(parents=True, exist_ok=True)
    GTDIR.mkdir(parents=True, exist_ok=True)
    full_p, blind_p = QDIR / "questions_daily_01a0aa2c.jsonl", QDIR / "questions_daily_01a0aa2c_blind.jsonl"
    gt_p = GTDIR / "gt_daily_01a0aa2c.jsonl"
    with open(full_p, "w", encoding="utf-8") as f, open(blind_p, "w", encoding="utf-8") as b, \
            open(gt_p, "w", encoding="utf-8") as g:
        for p in papers:
            blind, gt = split_ground_truth(p)
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
            b.write(json.dumps(blind, ensure_ascii=False) + "\n")
            g.write(json.dumps(gt, ensure_ascii=False) + "\n")
    print(json.dumps({"audit": "PASS", **stats,
                      "files": [str(full_p), str(blind_p), str(gt_p)]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
