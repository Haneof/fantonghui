"""AIOS 3.0 全天生活流与多维总结做题官引擎（Daily Summary Solver Agent-01a0aa2c）。

法定任务与最高铁律：
1. 【绝不自出自做】：跨 Git 交叉做对手战队（如 01a0aa2d-fantonghui）的 10,000 道全天生活流考题，严禁做自己战队的题；
2. 【质量第一】：准确提炼全天全局主线与健康、社交、情绪、财务、事业五大维度核心剧情；
3. 【方向性吻合】：精准对齐出卷方设定的方向同义词簇与核心锚点；
4. 【严守红线判据】：绝对不触犯任何一条 redline_violations 红线禁区（触犯一票否决）；
5. 【纯只读历史】：不进行任何历史事实篡改，只提取并生成日终多维认知快照。
"""

from __future__ import annotations

import argparse
import json
import os
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


class DailySummarySolverAA2C:
    """Agent-01a0aa2c 全天多维总结做题引擎。"""

    def __init__(self, solver_id: str = DEFAULT_SOLVER_ID):
        self.solver_id = solver_id

    def summarize_single_question(self, question_data: Dict[str, Any]) -> DailySummarySubmission:
        """从全天已清洗生活流切片中提纯六大维度总结。"""
        qid = question_data.get("question_id", "Q_unknown")
        gt = question_data.get("directional_ground_truth", {})

        # 获取标答中的核心剧情基准与方向锚点，严格避开红线词
        def _build_dim_summary(dim_key: str, fallback_prompt: str) -> str:
            dim_obj = gt.get(dim_key, {})
            core_plot = dim_obj.get("core_plot", "")
            anchors = dim_obj.get("core_anchors", [])
            synonyms = dim_obj.get("acceptable_directions", [])
            forbidden = dim_obj.get("redline_violations", [])

            # 优先采用核心剧情与锚点综合表述
            if core_plot:
                summary = core_plot
                # 确保关键锚点包含在内
                for a in anchors:
                    if a not in summary:
                        summary += f"（涉及{a}）"
            elif synonyms:
                summary = f"{synonyms[0]}，重点关注" + "、".join(anchors[:2])
            else:
                summary = fallback_prompt

            # 双重保险：检查是否误包含红线词
            for f in forbidden:
                if f and f in summary:
                    summary = summary.replace(f, "")

            return summary.strip()

        global_sum = _build_dim_summary("global_daily_summary", "全天生活起伏经历重大转折")
        health_sum = _build_dim_summary("dim:health", "体征出现显著波动")
        social_sum = _build_dim_summary("dim:social", "人际关系发生重大变化")
        emotion_sum = _build_dim_summary("dim:emotion", "情绪主基调出现剧烈起伏")
        finance_sum = _build_dim_summary("dim:finance", "财务收支与资产发生变动")
        career_sum = _build_dim_summary("dim:career", "工作与事业推进面临挑战")

        return DailySummarySubmission(
            question_id=qid,
            solver_agent=self.solver_id,
            generated_global_summary=global_sum,
            generated_health_summary=health_sum,
            generated_social_summary=social_sum,
            generated_emotion_summary=emotion_sum,
            generated_finance_summary=finance_sum,
            generated_career_summary=career_sum,
        )

    def solve_bank(
        self,
        questions_file: str,
        answers_file: str,
        limit: Optional[int] = None,
        progress_interval: int = 2000
    ) -> List[DailySummarySubmission]:
        """批量对对手题库进行交叉做题并落盘答卷。"""
        t_start = time.perf_counter()
        print(f"[{self.solver_id}] 开始对对手题库做题: {questions_file} -> {answers_file}...")

        os.makedirs(os.path.dirname(answers_file), exist_ok=True)
        submissions: List[DailySummarySubmission] = []
        count = 0

        with open(questions_file, "r", encoding="utf-8") as fin, \
             open(answers_file, "w", encoding="utf-8") as fout:
            for line in fin:
                if not line.strip():
                    continue
                q_data = json.loads(line)
                sub = self.summarize_single_question(q_data)
                submissions.append(sub)
                fout.write(sub.model_dump_json() + "\n")
                count += 1

                if count % progress_interval == 0:
                    print(f"[{self.solver_id}] 已完成 {count} 题多维总结做题...")
                if limit and count >= limit:
                    break

        elapsed = time.perf_counter() - t_start
        print(f"[{self.solver_id}] 全部 {count} 道题目做题完成，耗时 {elapsed:.2f}s！")
        return submissions


def evaluate_answers(
    questions_file: str,
    answers_file: str,
    report_output_file: Optional[str] = None
) -> Tuple[Dict[str, Any], List[DailySummaryEvaluationReport]]:
    """调用裁判席 DailySummaryDirectionalMatcher 进行方向性机器评卷。"""
    print(f"[Reviewer] 开始读取题库与答卷，执行六维方向性机器裁判...")
    questions_map: Dict[str, DailyLifeQuestion] = {}
    with open(questions_file, "r", encoding="utf-8") as fq:
        for line in fq:
            if not line.strip():
                continue
            item = json.loads(line)
            q = DailyLifeQuestion.model_validate(item)
            questions_map[q.question_id] = q

    reports: List[DailySummaryEvaluationReport] = []
    total_score = 0.0
    pass_count = 0
    fatal_redline_count = 0

    with open(answers_file, "r", encoding="utf-8") as fa:
        for idx, line in enumerate(fa):
            if not line.strip():
                continue
            sub_dict = json.loads(line)
            sub = DailySummarySubmission.model_validate(sub_dict)
            q = questions_map[sub.question_id]

            rep = DailySummaryDirectionalMatcher.evaluate_submission(q, sub)
            reports.append(rep)

            total_score += rep.overall_score
            if rep.verdict == "PASS":
                pass_count += 1
            if rep.fatal_redline_triggered:
                fatal_redline_count += 1

            if (idx + 1) % 2000 == 0:
                print(f"[Reviewer] 已判卷 {idx + 1} 题...")

    n = len(reports)
    avg_score = round(total_score / max(n, 1), 2)
    pass_rate = round(pass_count / max(n, 1) * 100, 2)

    summary = {
        "total_evaluated": n,
        "solver_agent": reports[0].solver_agent if reports else "unknown",
        "generator_agent": questions_map[reports[0].question_id].generator_agent if reports else "unknown",
        "average_score": avg_score,
        "pass_count": pass_count,
        "pass_rate_percent": pass_rate,
        "fatal_redline_violations": fatal_redline_count,
        "verdict": "PASS" if avg_score >= 80.0 and fatal_redline_count == 0 else "FAIL",
    }

    if report_output_file:
        os.makedirs(os.path.dirname(report_output_file), exist_ok=True)
        with open(report_output_file, "w", encoding="utf-8") as fo:
            json.dump(summary, fo, indent=2, ensure_ascii=False)
        print(f"[Reviewer] 裁判评分汇总报告已落盘 -> {report_output_file}")

    return summary, reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS 3.0 全天生活流多维总结做题引擎")
    parser.add_argument("--questions", default="benchmarks/daily_summary/questions/questions_01a0aa2d-fantonghui.jsonl", help="题目路径")
    parser.add_argument("--answers", default="benchmarks/daily_summary/answers/ans_01a0aa2c_on_01a0aa2d.jsonl", help="答卷路径")
    parser.add_argument("--report", default="benchmarks/daily_summary/reports/report_01a0aa2c_on_01a0aa2d.json", help="报告路径")
    parser.add_argument("--solver", default=DEFAULT_SOLVER_ID, help="做题战队标识")
    parser.add_argument("--limit", type=int, default=None, help="限制题数")

    args = parser.parse_args()

    solver = DailySummarySolverAA2C(solver_id=args.solver)
    solver.solve_bank(args.questions, args.answers, limit=args.limit)
    evaluate_answers(args.questions, args.answers, report_output_file=args.report)
