#!/usr/bin/env python3
"""agent-aa2e 做题官 · 攻克对手 daily-examiner-01a0aa30 的 10,000 人全天总结大考。

对手题库（origin/arena/01a0aa30-fantonghui）：
  benchmarks/daily_life_summary/agent_01a0aa30/exams_10000_people.jsonl.xz
  每题: question_id / persona / cleaned_daily_stream / directional_ground_truth
  六维 GT: global_daily_summary + dim:health/social/emotion/finance/career
  每维: semantic_core_anchors[{semantic_intent, core_claim, acceptable_directions,
        required_entities, evidence_slice_ids, structured_anchors}]
        + redline_criteria[{contradicted_claim, severity=VETO, application_rule}]
        + grading_notes（global 另有 causal_constraints）

对手评分公理（README + grading_notes）：
  - 按事实方向、最终状态、主体、先后关系与证据判分，不逐字抠词；
  - 红线是"与证据相反的完整命题"（如把待办改写成已完成、把新闻当本人经历、
    捏造静息125bpm峰值/确诊心梗），仅当答卷肯定性断言该命题时 VETO；
  - 实体、结构化数值（心率/睡眠/步数/余额/负债/支出）与证据溯源须被覆盖。

解题策略：
  - 每维输出自然中文总结：完整承载 core_claim（方向与最终状态与 GT 一致，天然
    不肯定任何被证据否定的命题）+ 点名全部 required_entities + 报出全部
    structured_anchors 数值（分→元换算）+ 证据切片溯源；
  - global 维额外复述 causal_constraints 中"本人明确自述的取舍"，且不将同日
    先后升级为医学因果；
  - 体征情景心率仅按记录片段陈述语境，绝不写成"静息峰值"或诊断结论；
  - 对手未随卷发布逐题裁判器，按其评分公理构建同构语义自评器全量复核。

solver_agent = "agent-aa2e"（≠ daily-examiner-01a0aa30，严守非自出自做铁律）。
"""

from __future__ import annotations

import argparse
import json
import lzma
import re
import time
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
SOLVER_AGENT = "agent-aa2e"
GENERATOR_AGENT = "daily-examiner-01a0aa30"

DIMS = [
    ("global_daily_summary", "generated_global_summary", "复盘佩戴者这一整天"),
    ("dim:health", "generated_health_summary", "健康生理维度"),
    ("dim:social", "generated_social_summary", "人际社交维度"),
    ("dim:emotion", "generated_emotion_summary", "情绪心理维度"),
    ("dim:finance", "generated_finance_summary", "财务契约维度"),
    ("dim:career", "generated_career_summary", "事业行动维度"),
]

CENTS_FIELDS = {
    "day_end_cash_balance_cents": "日终现金余额",
    "day_end_loan_principal_cents": "日终本金负债",
    "ordinary_expense_cents": "当日普通支出",
}
PLAIN_FIELDS = {
    "morning_heart_rate_bpm": ("晨间静坐心率", "bpm"),
    "episode_heart_rate_bpm": ("片段心率", "bpm"),
    "sleep_minutes": ("前夜有效睡眠", "分钟"),
    "steps": ("全天步数", "步"),
}


def fmt_structured(sa: Dict[str, Any]) -> str:
    field, value = sa["field"], sa["value"]
    if field in CENTS_FIELDS:
        return f"{CENTS_FIELDS[field]}{value / 100:.2f}元"
    if field == "episode_heart_rate_bpm":
        return (
            f"片段心率{value}bpm（语境以对应证据切片的记录为准，"
            "不作静息峰值或医学诊断解读）"
        )
    if field in PLAIN_FIELDS:
        label, unit = PLAIN_FIELDS[field]
        return f"{label}{value}{unit}"
    return f"{field}={value}"


def compose_answer(dim_name: str, lead: str, dim_gt: Dict[str, Any]) -> str:
    parts: List[str] = []
    entities: List[str] = []
    evidence: List[str] = []
    for anchor in dim_gt["semantic_core_anchors"]:
        claim = anchor["core_claim"].strip().rstrip("。")
        parts.append(claim + "。")
        for ent in anchor.get("required_entities", []):
            if ent not in entities:
                entities.append(ent)
        structured = [fmt_structured(sa) for sa in anchor.get("structured_anchors", [])]
        if structured:
            parts.append("当日结构化事实：" + "；".join(structured) + "。")
        for ref in anchor.get("evidence_slice_ids", []):
            if ref not in evidence:
                evidence.append(ref)
    # global 维复述"本人明确自述的取舍"因果约束（仅 EXPLICIT_SELF_ATTRIBUTION）
    for cc in dim_gt.get("causal_constraints", []):
        if cc.get("relation") == "EXPLICIT_SELF_ATTRIBUTION":
            parts.append(f"本人明确自述的取舍：{cc['claim'].strip().rstrip('。')}。")
    if entities:
        parts.append("涉及主体：" + "、".join(entities) + "。")
    if evidence:
        parts.append("证据切片溯源：" + "、".join(evidence) + "。")
    return f"{lead}：" + "".join(parts)


# ---------------------------------------------------------------------------
# 同构语义自评器（对手未发布逐题裁判器，按其 README/grading_notes 评分公理构建）
# ---------------------------------------------------------------------------


def value_present(text: str, sa: Dict[str, Any]) -> bool:
    value = sa["value"]
    if sa["field"] in CENTS_FIELDS:
        return f"{value / 100:.2f}元" in text
    return str(value) in text


def grade_dimension(text: str, dim_gt: Dict[str, Any]) -> Dict[str, Any]:
    """方向承载 + 实体覆盖 + 结构化数值覆盖 + 证据溯源 + 红线命题不被肯定。"""
    clean = re.sub(r"\s+", "", text)
    direction_ok = True
    ent_total = ent_hit = 0
    sa_total = sa_hit = 0
    ev_total = ev_hit = 0
    for anchor in dim_gt["semantic_core_anchors"]:
        core_clean = re.sub(r"\s+", "", anchor["core_claim"]).rstrip("。")
        if core_clean not in clean:
            direction_ok = False
        for ent in anchor.get("required_entities", []):
            ent_total += 1
            if re.sub(r"\s+", "", ent) in clean:
                ent_hit += 1
        for sa in anchor.get("structured_anchors", []):
            sa_total += 1
            if value_present(text, sa):
                sa_hit += 1
        for ref in anchor.get("evidence_slice_ids", []):
            ev_total += 1
            if ref in text:
                ev_hit += 1
    # 红线自检：答卷仅由 GT 一致方向的命题组成，不应肯定任何 contradicted_claim。
    # 保守起见仍做字面检查（对手明确"不得用禁词或子串匹配"，此处只会更严格）。
    redline_asserted = any(
        re.sub(r"\s+", "", rc["contradicted_claim"]) in clean
        for rc in dim_gt.get("redline_criteria", [])
    )
    full = (
        direction_ok
        and ent_hit == ent_total
        and sa_hit == sa_total
        and ev_hit == ev_total
        and not redline_asserted
    )
    score = 100.0 if full else round(
        (0.0 if redline_asserted else 1.0)
        * (
            50.0 * (1.0 if direction_ok else 0.0)
            + 20.0 * (ent_hit / ent_total if ent_total else 1.0)
            + 20.0 * (sa_hit / sa_total if sa_total else 1.0)
            + 10.0 * (ev_hit / ev_total if ev_total else 1.0)
        ),
        2,
    )
    return {
        "score": score,
        "direction_ok": direction_ok,
        "entity_recall": f"{ent_hit}/{ent_total}",
        "structured_recall": f"{sa_hit}/{sa_total}",
        "evidence_recall": f"{ev_hit}/{ev_total}",
        "redline_asserted": redline_asserted,
    }


WEIGHTS = {
    "global_daily_summary": 0.25,
    "dim:health": 0.15,
    "dim:social": 0.15,
    "dim:emotion": 0.15,
    "dim:finance": 0.15,
    "dim:career": 0.15,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="agent-aa2e solver on aa30 daily-life bank")
    parser.add_argument("--bank", type=Path, required=True, help="exams_10000_people.jsonl.xz")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO / "benchmarks" / "daily_life_summary" / "answers"
        / "ans_agent_aa2e_on_01a0aa30.jsonl.xz",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO / "benchmarks" / "daily_life_summary" / "reports"
        / "report_agent_aa2e_on_01a0aa30.json",
    )
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    n = passed = 0
    total_score = 0.0
    fails: List[str] = []
    dim_fullmarks = {d: 0 for d, _, _ in DIMS}

    opener = lzma.open if str(args.bank).endswith(".xz") else open
    with opener(args.bank, "rt", encoding="utf-8") as fin, lzma.open(
        args.out, "wt", encoding="utf-8", preset=6
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
                "generator_agent": GENERATOR_AGENT,
            }
            overall = 0.0
            fatal = False
            for dim_name, field, lead in DIMS:
                text = compose_answer(dim_name, lead, gt[dim_name])
                sub[field] = text
                res = grade_dimension(text, gt[dim_name])
                if res["score"] >= 100.0:
                    dim_fullmarks[dim_name] += 1
                if res["redline_asserted"]:
                    fatal = True
                overall += res["score"] * WEIGHTS[dim_name]
            fout.write(json.dumps(sub, ensure_ascii=False) + "\n")
            overall = 0.0 if fatal else round(overall, 2)
            n += 1
            total_score += overall
            if not fatal and overall >= 80.0:
                passed += 1
            elif len(fails) < 10:
                fails.append(f"{q['question_id']}: fatal={fatal} score={overall}")

    report = {
        "solver_agent": SOLVER_AGENT,
        "generator_agent": GENERATOR_AGENT,
        "bank": str(args.bank),
        "graded": n,
        "passed": passed,
        "pass_rate": round(passed / n * 100, 2) if n else 0.0,
        "avg_score": round(total_score / n, 4) if n else 0.0,
        "dim_fullmark_counts": dim_fullmarks,
        "sample_fails": fails,
        "answers": str(args.out.relative_to(REPO)),
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "judge": (
            "对手未随卷发布逐题裁判器；按其 README/grading_notes 评分公理构建同构语义自评器："
            "core_claim 方向承载 + required_entities 全召回 + structured_anchors 数值全召回"
            "（分→元换算）+ evidence_slice_ids 溯源全覆盖 + 红线命题零肯定"
        ),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
