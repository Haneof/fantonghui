"""全天生活流试卷 —— 出卷方自检（发题前必须全绿）。

出卷官对自己的题库负责。本模块在题库落盘后做**全量结构与自洽审计**，
任何一条不合格都视为废题。检查项：

  S1 结构完整：四个法定顶层键齐备，六维标答齐备且字段完整。
  S2 时间轴：07:00~23:30 严格升序，切片 ID 唯一且连续。
  S3 模态合法：仅 MIC / APP / SENSOR，三种模态必须同时出现。
  S4 关键事件：必须同时含关键大事与琐碎日常（两者都不为空）。
  S5 标答无自相矛盾：方向同义词 与 红线判据 **不得有交集**。
  S6 红线非空：每一维都必须声明红线，否则"一票否决"无从谈起。
  S7 人设自洽：已婚人设不得出现"提分手"类弧。
  S8 无逐字重复切片：同一天内不得出现完全相同的两条内容。
  S9 跨维度编织：晚间情感重创必须伴随生理应激（体征维度可证）。
  S10 子串陷阱：红线词不得是任一同义词的子串（否则误杀正确答案）。
  S11 标答自噬：标准答案 core_content 不得命中自己的红线。
  S12 标答可达：core_content 必须命中至少一个方向同义词（杜绝死题）。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from aios_core.simulation.daily_life_exam_pools import DATING
from aios_core.simulation.daily_life_exam_protocol import (
    DIMENSION_ORDER,
    Modality,
)

REQUIRED_TOP_KEYS = ("question_id", "persona", "cleaned_daily_stream", "directional_ground_truth")
REQUIRED_GT_FIELDS = ("semantic_intent", "core_content", "acceptable_directions", "red_line_deviations")

#: 只有这些人际弧允许出现在"未婚恋爱"人设上。
DATING_ONLY_ARCS = frozenset({"BREAKUP", "PROPOSAL_ACCEPTED"})

#: 触发生理应激的情感重创弧。
SHOCK_ARCS = frozenset({"BREAKUP", "PARENT_ILLNESS", "PET_LOSS"})
STRESS_HEALTH_ARCS = frozenset({"EMOTIONAL_TACHYCARDIA", "PANIC_EPISODE"})


def validate_question(q: Dict[str, Any]) -> List[str]:
    """返回该题的违规清单；空列表 = 合格。"""
    errs: List[str] = []

    # S1 结构
    for k in REQUIRED_TOP_KEYS:
        if k not in q:
            errs.append(f"S1:missing_key:{k}")
    gt = q.get("directional_ground_truth", {})
    for dim in DIMENSION_ORDER:
        if dim not in gt:
            errs.append(f"S1:missing_dimension:{dim}")
            continue
        for f in REQUIRED_GT_FIELDS:
            if not gt[dim].get(f):
                errs.append(f"S1:empty_field:{dim}.{f}")

    stream = q.get("cleaned_daily_stream", [])
    if not stream:
        errs.append("S1:empty_stream")
        return errs

    # S2 时间轴
    mins = []
    for s in stream:
        h, m = s["timestamp"].split(":")
        mins.append(int(h) * 60 + int(m))
    if mins != sorted(mins):
        errs.append("S2:timestamps_not_sorted")
    if mins[0] < 7 * 60 or mins[-1] > 23 * 60 + 30:
        errs.append("S2:out_of_day_window")
    ids = [s["slice_id"] for s in stream]
    if len(set(ids)) != len(ids):
        errs.append("S2:duplicate_slice_id")

    # S3 模态
    mods = {s["modality"] for s in stream}
    illegal = mods - {Modality.MIC, Modality.APP, Modality.SENSOR}
    if illegal:
        errs.append(f"S3:illegal_modality:{sorted(illegal)}")
    for need in (Modality.MIC, Modality.APP, Modality.SENSOR):
        if need not in mods:
            errs.append(f"S3:missing_modality:{need}")

    # S4 大事 + 琐事必须共存
    key_n = sum(1 for s in stream if s.get("is_key_event"))
    triv_n = len(stream) - key_n
    if key_n == 0:
        errs.append("S4:no_key_event")
    if triv_n == 0:
        errs.append("S4:no_trivia")

    # S5/S6 标答自洽
    for dim in DIMENSION_ORDER:
        if dim not in gt:
            continue
        acc = set(gt[dim].get("acceptable_directions", []))
        red = set(gt[dim].get("red_line_deviations", []))
        overlap = acc & red
        if overlap:
            errs.append(f"S5:direction_redline_collision:{dim}:{sorted(overlap)}")
        if not red:
            errs.append(f"S6:no_red_line:{dim}")

        # S10 子串陷阱：判卷用子串匹配，红线词若是某同义词的子串
        # （典型如 红线"逾期" ⊂ 同义词"无逾期"），会把正确答案误判为一票否决。
        for r in red:
            for a in acc:
                if r != a and r in a:
                    errs.append(f"S10:redline_substring_of_direction:{dim}:{r}<{a}")

        # S11 标答自噬：标准答案本身不得命中自己的红线，
        # 否则"照抄标答"都会被判负，阅卷失去公信力。
        core = gt[dim].get("core_content", "")
        for r in red:
            if r in core:
                errs.append(f"S11:red_line_inside_own_core:{dim}:{r}")

        # S12 标答可达：忠实复述标准答案必须能命中至少一个方向同义词，
        # 否则该维度存在"答对也得不了分"的死题。
        if acc and core and not any(a in core for a in acc):
            errs.append(f"S12:core_hits_no_direction:{dim}")

    # S7 人设自洽
    sig = q.get("arc_signature", {})
    marital = q.get("persona", {}).get("marital_status")
    if sig.get("social") in DATING_ONLY_ARCS and marital not in DATING:
        errs.append(f"S7:marital_arc_mismatch:{marital}/{sig.get('social')}")

    # S8 无逐字重复
    dupes = [c for c, n in Counter(s["content"] for s in stream).items() if n > 1]
    if dupes:
        errs.append(f"S8:duplicate_slice_content:{len(dupes)}")

    # S9 跨维度编织
    if sig.get("social") in SHOCK_ARCS and sig.get("health") not in STRESS_HEALTH_ARCS:
        errs.append(f"S9:shock_without_physiological_response:{sig.get('health')}")

    return errs


def validate_bank(path: Path, limit: int | None = None) -> Dict[str, Any]:
    total = 0
    failed = 0
    reasons: Counter = Counter()
    samples: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    dup_ids = 0

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if limit is not None and total >= limit:
                break
            q = json.loads(line)
            total += 1
            if q["question_id"] in seen_ids:
                dup_ids += 1
            seen_ids.add(q["question_id"])
            errs = validate_question(q)
            if errs:
                failed += 1
                for e in errs:
                    reasons[e.split(":")[0] + ":" + e.split(":")[1]] += 1
                if len(samples) < 5:
                    samples.append({"question_id": q["question_id"], "errors": errs})

    return {
        "bank": str(path),
        "total_questions": total,
        "unique_question_ids": len(seen_ids),
        "duplicate_question_ids": dup_ids,
        "failed_questions": failed,
        "pass_rate": round((total - failed) / total, 6) if total else 0.0,
        "violation_histogram": dict(reasons.most_common()),
        "failure_samples": samples,
        "verdict": "ALL_GREEN" if failed == 0 and dup_ids == 0 else "REJECTED",
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="全天生活流题库自检")
    ap.add_argument("--bank", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    report = validate_bank(args.bank, args.limit)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if report["verdict"] == "ALL_GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
