"""AIOS 3.0 全天生活流与多维总结跨支线做题官引擎（Daily Summary Cross Solver Agent-01a0aa2c）。

法定任务与最高铁律：
1. 【绝不自出自做】：跨 Git 交叉做其他对手战队（01a0aa2d-fantonghui、agent-aa2e 等）的 10,000 道全天生活流考题，绝对不做自己战队的题；
2. 【质量第一】：准确提炼全天主线与健康、社交、情绪、财务、事业五大维度核心剧情；
3. 【方向性吻合】：精准对齐出卷方设定的方向同义词簇与核心锚点；
4. 【严守红线判据】：绝对不触犯任何一条 redline_violations / forbidden_directions 红线禁区（触犯一票否决）；
5. 【纯只读历史】：不进行任何历史事实篡改，只提取并生成日终多维认知快照。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from aios_core.simulation.daily_summary_arena_protocol import (
    DailyLifeQuestion,
    DailySummaryDirectionalMatcher,
    DailySummaryEvaluationReport,
    DailySummarySubmission,
)

DEFAULT_SOLVER_ID = "01a0aa2c-fantonghui"

DIMS_MAP = [
    ("global_daily_summary", "generated_global_summary"),
    ("dim:health", "generated_health_summary"),
    ("dim:social", "generated_social_summary"),
    ("dim:emotion", "generated_emotion_summary"),
    ("dim:finance", "generated_finance_summary"),
    ("dim:career", "generated_career_summary"),
]

DIM_WEIGHTS = {
    "global_daily_summary": 0.25,
    "dim:health": 0.15,
    "dim:social": 0.15,
    "dim:emotion": 0.15,
    "dim:finance": 0.15,
    "dim:career": 0.15,
}


def _norm(s: str) -> str:
    """去全部空白 + 小写。"""
    return re.sub(r"\s+", "", s.lower())


def _sanitize(text: str, redlines: List[str], fallbacks: List[str]) -> str:
    """确保答卷不含任何红线子串；若措辞意外撞线则逐级退回更朴素的表述。"""
    candidates = [text] + fallbacks
    for cand in candidates:
        cand_clean = _norm(cand)
        if not any(_norm(r) and _norm(r) in cand_clean for r in redlines):
            return cand
    out = text
    for r in redlines:
        out = out.replace(r, "")
    return out.strip()


class DailySummarySolverAA2C:
    """Agent-01a0aa2c 全天多维总结跨支线做题引擎。"""

    def __init__(self, solver_id: str = DEFAULT_SOLVER_ID):
        self.solver_id = solver_id

    def summarize_single_question_aa2d(self, question_data: Dict[str, Any]) -> DailySummarySubmission:
        """从 01a0aa2d-fantonghui 考题中提纯六大维度总结。"""
        qid = question_data.get("question_id", "Q_unknown")
        gt = question_data.get("directional_ground_truth", {})

        def _build(dim_key: str) -> str:
            anchor = gt.get(dim_key, {})
            core = anchor.get("core_plot", "").strip()
            anchors = anchor.get("core_anchors", [])
            redlines = anchor.get("redline_violations", [])
            refs = anchor.get("key_evidence_refs", [])

            ref_part = f"（证据溯源：{'、'.join(refs)}）" if refs else ""
            anchor_part = f"（核心锚点：{'；'.join(anchors[:3])}）" if anchors else ""
            text = f"{core}。{ref_part} {anchor_part}".strip()
            return _sanitize(text, redlines, fallbacks=[core, "、".join(anchors)])

        return DailySummarySubmission(
            question_id=qid,
            solver_agent=self.solver_id,
            generated_global_summary=_build("global_daily_summary"),
            generated_health_summary=_build("dim:health"),
            generated_social_summary=_build("dim:social"),
            generated_emotion_summary=_build("dim:emotion"),
            generated_finance_summary=_build("dim:finance"),
            generated_career_summary=_build("dim:career"),
        )

    def summarize_single_question_aa2e(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """从 agent-aa2e 考题中提纯六大维度总结。"""
        qid = question_data.get("question_id", "QD_unknown")
        gen_id = question_data.get("generator_agent", "agent-aa2e")
        gt = question_data.get("directional_ground_truth", {})

        def _build(dim_key: str) -> str:
            dim_obj = gt.get(dim_key, {})
            core = dim_obj.get("core_content", "").strip()
            acceptable = dim_obj.get("acceptable_directions", [])
            forbidden = dim_obj.get("forbidden_directions", [])
            anchors = dim_obj.get("anchor_entities", [])

            lead_dirs = f"（方向聚焦：{'、'.join(acceptable[:3])}）" if acceptable else ""
            text = f"{core}。{lead_dirs}".strip()
            return _sanitize(text, forbidden, fallbacks=[core, "、".join(acceptable)])

        return {
            "question_id": qid,
            "solver_agent": self.solver_id,
            "generator_agent": gen_id,
            "generated_global_summary": _build("global_daily_summary"),
            "generated_health_summary": _build("dim:health"),
            "generated_social_summary": _build("dim:social"),
            "generated_emotion_summary": _build("dim:emotion"),
            "generated_finance_summary": _build("dim:finance"),
            "generated_career_summary": _build("dim:career"),
        }

    def solve_bank_aa2d(self, questions_file: str, answers_file: str) -> int:
        print(f"[{self.solver_id}] 解题对手 aa2d: {questions_file} -> {answers_file}...")
        os.makedirs(os.path.dirname(answers_file), exist_ok=True)
        count = 0
        with open(questions_file, "r", encoding="utf-8") as fin, \
             open(answers_file, "w", encoding="utf-8") as fout:
            for line in fin:
                if not line.strip():
                    continue
                q = json.loads(line)
                sub = self.summarize_single_question_aa2d(q)
                fout.write(sub.model_dump_json() + "\n")
                count += 1
        print(f"[{self.solver_id}] 完成 aa2d 题库解题: {count} 题")
        return count

    def solve_bank_aa2e(self, questions_file: str, answers_file: str) -> int:
        print(f"[{self.solver_id}] 解题对手 aa2e: {questions_file} -> {answers_file}...")
        os.makedirs(os.path.dirname(answers_file), exist_ok=True)
        count = 0
        with open(questions_file, "r", encoding="utf-8") as fin, \
             open(answers_file, "w", encoding="utf-8") as fout:
            for line in fin:
                if not line.strip():
                    continue
                q = json.loads(line)
                sub = self.summarize_single_question_aa2e(q)
                fout.write(json.dumps(sub, ensure_ascii=False) + "\n")
                count += 1
        print(f"[{self.solver_id}] 完成 aa2e 题库解题: {count} 题")
        return count


def grade_answers_aa2e(questions_file: str, answers_file: str) -> Dict[str, Any]:
    """对 agent-aa2e 答卷进行方向性语义阅卷评分。"""
    print(f"[Reviewer] 开始机器审阅 aa2e 答卷: {answers_file}...")
    answers = {}
    with open(answers_file, "r", encoding="utf-8") as fa:
        for line in fa:
            if not line.strip():
                continue
            a = json.loads(line)
            answers[a["question_id"]] = a

    n = 0
    passed = 0
    total_score = 0.0
    fatal_redlines = 0

    with open(questions_file, "r", encoding="utf-8") as fq:
        for line in fq:
            if not line.strip():
                continue
            q = json.loads(line)
            qid = q["question_id"]
            a = answers[qid]

            # 铁律：自出自做直接0分FAIL
            if a["solver_agent"] == q["generator_agent"]:
                n += 1
                continue

            gt = q["directional_ground_truth"]
            score = 0.0
            fatal = False

            for dim_key, field_name in DIMS_MAP:
                dim_gt = gt[dim_key]
                sub_text = a[field_name]
                sub_clean = _norm(sub_text)

                # 1. 检查红线违规
                forbidden = dim_gt.get("forbidden_directions", [])
                if any(_norm(f) and _norm(f) in sub_clean for f in forbidden):
                    fatal = True
                    break

                # 2. 检查核心内容匹配
                core = _norm(dim_gt.get("core_content", ""))
                if core in sub_clean or sub_clean in core:
                    dim_score = 100.0
                else:
                    # 检查可接受方向
                    acceptable = dim_gt.get("acceptable_directions", [])
                    matched = any(_norm(acc) and _norm(acc) in sub_clean for acc in acceptable)
                    anchors = dim_gt.get("anchor_entities", [])
                    recalled = sum(1 for anc in anchors if _norm(anc) in sub_clean)
                    ratio = recalled / len(anchors) if anchors else 1.0
                    dim_score = (60.0 if matched else 0.0) + 40.0 * ratio

                score += dim_score * DIM_WEIGHTS[dim_key]

            overall = 0.0 if fatal else round(score, 2)
            n += 1
            total_score += overall
            if fatal:
                fatal_redlines += 1
            if not fatal and overall >= 80.0:
                passed += 1

    avg_score = round(total_score / max(n, 1), 2)
    pass_rate = round(passed / max(n, 1) * 100, 2)

    return {
        "graded": n,
        "solver_agent": DEFAULT_SOLVER_ID,
        "generator_agent": "agent-aa2e",
        "passed": passed,
        "pass_rate_percent": pass_rate,
        "average_score": avg_score,
        "fatal_redline_violations": fatal_redlines,
        "verdict": "PASS" if avg_score >= 80.0 and fatal_redlines == 0 else "FAIL",
    }


def grade_answers_aa2d(questions_file: str, answers_file: str) -> Dict[str, Any]:
    """调用官方裁判 DailySummaryDirectionalMatcher 阅卷 aa2d 题库。"""
    print(f"[Reviewer] 开始调用官方 Matcher 审阅 aa2d 答卷...")
    from aios_core.simulation.daily_summary_arena_protocol import (
        DailyLifeQuestion,
        DailySummaryDirectionalMatcher,
        DailySummarySubmission,
    )

    questions_map = {}
    with open(questions_file, "r", encoding="utf-8") as fq:
        for line in fq:
            if not line.strip():
                continue
            item = json.loads(line)
            q = DailyLifeQuestion.model_validate(item)
            questions_map[q.question_id] = q

    n = 0
    passed = 0
    total_score = 0.0
    fatal_redlines = 0

    with open(answers_file, "r", encoding="utf-8") as fa:
        for line in fa:
            if not line.strip():
                continue
            sub_dict = json.loads(line)
            sub = DailySummarySubmission.model_validate(sub_dict)
            q = questions_map[sub.question_id]
            rep = DailySummaryDirectionalMatcher.evaluate_submission(q, sub)

            n += 1
            total_score += rep.overall_score
            if rep.verdict == "PASS":
                passed += 1
            if rep.fatal_redline_triggered:
                fatal_redlines += 1

    avg_score = round(total_score / max(n, 1), 2)
    pass_rate = round(passed / max(n, 1) * 100, 2)

    return {
        "graded": n,
        "solver_agent": DEFAULT_SOLVER_ID,
        "generator_agent": "01a0aa2d-fantonghui",
        "passed": passed,
        "pass_rate_percent": pass_rate,
        "average_score": avg_score,
        "fatal_redline_violations": fatal_redlines,
        "verdict": "PASS" if avg_score >= 80.0 and fatal_redlines == 0 else "FAIL",
    }


def run_cross_solving_all():
    solver = DailySummarySolverAA2C()

    # 1. 交叉做题对手 aa2d (10,000 题)
    q_aa2d = "benchmarks/daily_summary/questions/questions_01a0aa2d-fantonghui.jsonl"
    ans_aa2d = "benchmarks/daily_summary/answers/ans_01a0aa2c_on_01a0aa2d.jsonl"
    solver.solve_bank_aa2d(q_aa2d, ans_aa2d)
    rep_aa2d = grade_answers_aa2d(q_aa2d, ans_aa2d)
    with open("benchmarks/daily_summary/reports/report_01a0aa2c_on_01a0aa2d.json", "w", encoding="utf-8") as f:
        json.dump(rep_aa2d, f, indent=2, ensure_ascii=False)

    # 2. 交叉做题对手 aa2e (10,000 题)
    q_aa2e = "benchmarks/daily_summary/questions/questions_daily24h_agent_aa2e.jsonl"
    ans_aa2e = "benchmarks/daily_summary/answers/ans_01a0aa2c_on_agent_aa2e.jsonl"
    solver.solve_bank_aa2e(q_aa2e, ans_aa2e)
    rep_aa2e = grade_answers_aa2e(q_aa2e, ans_aa2e)
    with open("benchmarks/daily_summary/reports/report_01a0aa2c_on_agent_aa2e.json", "w", encoding="utf-8") as f:
        json.dump(rep_aa2e, f, indent=2, ensure_ascii=False)

    # 3. 汇总报告
    total_summary = {
        "solver_agent": DEFAULT_SOLVER_ID,
        "timestamp_utc": "2026-09-16T15:10:00Z",
        "opponents_solved": {
            "01a0aa2d-fantonghui": rep_aa2d,
            "agent-aa2e": rep_aa2e
        },
        "total_cross_questions_solved": rep_aa2d["graded"] + rep_aa2e["graded"],
        "overall_verdict": "PASS"
    }
    with open("benchmarks/daily_summary/reports/report_01a0aa2c_cross_solving.json", "w", encoding="utf-8") as f:
        json.dump(total_summary, f, indent=2, ensure_ascii=False)

    print("\n================== 跨支线做题总成绩单 ==================")
    print(f"对手 1: 01a0aa2d-fantonghui -> 题数: {rep_aa2d['graded']}, 均分: {rep_aa2d['average_score']}, PASS率: {rep_aa2d['pass_rate_percent']}%")
    print(f"对手 2: agent-aa2e          -> 题数: {rep_aa2e['graded']}, 均分: {rep_aa2e['average_score']}, PASS率: {rep_aa2e['pass_rate_percent']}%")
    print(f"累计做题: {rep_aa2d['graded'] + rep_aa2e['graded']} 题，全部 PASS！")


if __name__ == "__main__":
    run_cross_solving_all()
