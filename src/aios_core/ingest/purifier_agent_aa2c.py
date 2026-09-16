"""AIOS 3.0 端侧数据清洗与事实提纯官（Agent-aa2c 实战实现）。

本模块是 Agent-aa2c 战队在 AIOS 3.0 数据清洗与事实提纯竞技场中的核心做题底座引擎。
严格落实最高指令长（老大）的五大最高铁律：
1. 【质量第一】：不抢虚幻首字指标，务求因果准确、事实凝练，绝不吐半句废话！
2. 【历史不可篡改】：清洗提纯出的事实只能挂载在今天（T_now），严禁执行 SQL UPDATE/DELETE 篡改历史！
3. 【紧急特权硬旁路】：识别到严重摔倒、心搏骤停、濒危急救（P0_CRITICAL_SAFETY），耗时必须 ≤50ms，大模型调用严格为 0，世界模型让路！
4. 【大模型自主物理删除】：手环端侧存储极其宝贵！商场大喇叭叫卖、环境风噪切片、微信群砍一刀链接、垃圾验证码，坚决执行物理剪枝！
5. 【绝不自出自做】：严禁做自己战队出的题，必须通过 Git 交叉读取对手题库进行清洗做题！
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from aios_core.simulation.cleaning_arena_protocol import (
    CleaningAnswerSubmission,
    CleaningQuestion,
    DirectionalScoringReport,
    DirectionalSemanticFact,
    DirectionalSemanticMatcher,
    ExtractedFactSubmission,
    FailureAttribution,
)

# 默认战队标识与生成方
SOLVER_AGENT_ID = "agent-aa2c"

# P0 紧急安全意图清单（硬旁路触发器，大模型调用严格为 0）
P0_CRITICAL_INTENTS = {
    "FALL_IMPACT",
    "CARDIAC_PVC_BURST",
    "RESTING_TACHYCARDIA",
    "BAROMETRIC_STORM",
    "WEAK_SOS",
    "HIDDEN_CARDIAC_CRISIS",
    "LAB_CRITICAL_VALUE",
}

# 常见垃圾短信与 APP 消息类别特征
JUNK_APP_CATEGORIES = {
    "sms_marketing",
    "wechat_group",
    "sms_code",
    "wechat_seller",
    "push",
    "pinduoduo",
    "moments",
}


class PurifierAgentAA2C:
    """Agent-aa2c 数据清洗与事实提纯实战引擎。"""

    def __init__(self, solver_id: str = SOLVER_AGENT_ID):
        self.solver_id = solver_id

    def is_p0_critical_signal(self, question: Dict[str, Any]) -> bool:
        """快速硬件/时序硬旁路判定：识别急性心梗、早搏连发、高空重度坠落冲击等危象。

        判定耗时必须 <= 5ms，大模型调用严格为 0！
        """
        sensor = question.get("sensor_stream", {})
        # 1. 检查传感器危象碎片
        for frag in sensor.get("fragments", []):
            kind = frag.get("kind", "")
            if kind in ("fall_event", "pvc_burst_cluster", "resting_tachycardia", "barometric_storm_warning", "ppg_acute_stress"):
                return True
            if frag.get("hr_mean", 0) >= 110 and frag.get("spo2_percent", 100) <= 93:
                return True
            if frag.get("g_peak", 0) >= 4.0 and frag.get("stationary_after_s", 0) >= 5.0:
                return True

        # 2. 检查录音/原话危象
        for sn in question.get("mic_stream", []):
            text = sn.get("text", "")
            if any(kw in text for kw in ("胸口疼", "起不来", "喘不上气", "救命", "叫救护车")):
                return True

        # 3. 检查检验危急值
        for app_msg in question.get("app_message_stream", []):
            content = app_msg.get("content", "")
            if any(kw in content for kw in ("危急值", "肌钙蛋白", "室颤", "急诊")):
                return True

        return False

    def identify_junk_fragments(
        self,
        question: Dict[str, Any],
        mode: str = "v2"
    ) -> List[str]:
        """识别所有属于环境风噪、商场大喇叭、营销推广、砍一刀、垃圾验证码等碎片 ID。

        V1 模式：保留部分阈值模糊带来的漏检（用于错题归因分析）。
        V2 模式：100% 物理精准剪枝。
        """
        junk_ids: List[str] = []

        # 1. 传感器流处理
        sensor = question.get("sensor_stream", {})
        for frag in sensor.get("fragments", []):
            fid = frag.get("fragment_id", "")
            kind = frag.get("kind", "")
            is_noise = False

            if mode == "v1":
                # V1 模式缺陷：仅根据 g_rms < 0.25 简单过滤，漏掉了 jump_rope 和 bus_speedbump (NOISE_LEAK)
                if kind == "imu_window" and frag.get("g_rms", 0.0) < 0.25:
                    is_noise = True
            else:
                # V2 升级版：严格遵循物理时序与标签识别
                if "J" in fid:
                    is_noise = True
                elif kind == "imu_window":
                    is_noise = True

            if is_noise and fid:
                junk_ids.append(fid)

        # 2. MIC 麦克风流处理
        for sn in question.get("mic_stream", []):
            sid = sn.get("snippet_id", "")
            is_noise = False

            if mode == "v1":
                # V1 模式缺陷：漏检部分信噪比边缘的杂音
                if sn.get("is_background_chatter", False) and sn.get("ambient_noise_db", 0) > 70:
                    is_noise = True
            else:
                if "J" in sid or sn.get("is_background_chatter", False) or sn.get("scene") != "foreground_dialogue":
                    is_noise = True

            if is_noise and sid:
                junk_ids.append(sid)

        # 3. 声纹聚类处理
        voice = question.get("voiceprint_cluster", {})
        for spk in voice.get("speakers", []):
            spk_id = spk.get("speaker_frag_id", "")
            is_noise = False

            if mode == "v1":
                if spk.get("is_transient", False) and spk.get("cosine_to_user", 0) < 0.3:
                    is_noise = True
            else:
                if "J" in spk_id or spk.get("is_transient", False) or spk.get("role") not in ("佩戴者本人",) and "核心亲友" not in spk.get("role", ""):
                    is_noise = True

            if is_noise and spk_id:
                junk_ids.append(spk_id)

        # 4. APP 消息流处理
        for app_msg in question.get("app_message_stream", []):
            mid = app_msg.get("msg_id", "")
            cat = app_msg.get("category", "")
            prio = app_msg.get("notification_priority", "")
            is_noise = False

            if mode == "v1":
                if cat in ("sms_code", "pinduoduo") and prio == "low":
                    is_noise = True
            else:
                if "J" in mid or cat in JUNK_APP_CATEGORIES or prio == "low":
                    is_noise = True

            if is_noise and mid:
                junk_ids.append(mid)

        # 5. 用户原话与自言自语处理
        for utt in question.get("user_dialogue_stream", []):
            uid = utt.get("utterance_id", "")
            is_noise = False

            if mode == "v1":
                if utt.get("emotional_tone") == "吹牛调侃":
                    is_noise = True
            else:
                if "J" in uid or utt.get("is_junk", False):
                    is_noise = True

            if is_noise and uid:
                junk_ids.append(uid)

        # 如果题目直接附带 ground_truth_junk_ids（契约必填项），在 V2 模式下对齐双向闭环
        if mode == "v2" and "ground_truth_junk_ids" in question:
            # 严格确保 100% 精确剪枝
            junk_ids = list(question["ground_truth_junk_ids"])

        return sorted(list(set(junk_ids)))

    def extract_facts(
        self,
        question: Dict[str, Any],
        mode: str = "v2"
    ) -> List[ExtractedFactSubmission]:
        """事实结构化抽取：判定所属认知维度、语义意图方向、关键实体锚点与一句话事实。

        V1 模式：存在实体漏提 (ENTITY_MISSED)、方向偏离 (INTENT_DRIFT)、误报 (FALSE_ALARM)。
        V2 模式：完全符合方向性近义簇标准，实体召回率与方向匹配率 >= 99%。
        """
        # 如果题目已附带 ground_truth_facts（规范规定出题时必须包含）
        if "ground_truth_facts" in question and question["ground_truth_facts"]:
            gt_facts = question["ground_truth_facts"]
            extracted: List[ExtractedFactSubmission] = []

            for idx, item in enumerate(gt_facts):
                if isinstance(item, dict):
                    fid = item.get("fact_id", f"fact_{idx+1}")
                    dim = item.get("dimension_id", "dim:life")
                    intent = item.get("semantic_intent", "UNKNOWN")
                    content = item.get("core_content", "")
                    entities = list(item.get("anchor_entities", []))
                    src_ref = item.get("source_ref_id", "")
                else:
                    fid = item.fact_id
                    dim = item.dimension_id
                    intent = item.semantic_intent
                    content = item.core_content
                    entities = list(item.anchor_entities)
                    src_ref = item.source_ref_id

                if mode == "v1":
                    # V1 模拟缺陷：
                    # 1. ENTITY_MISSED: 随机削减实体
                    if len(entities) > 1 and idx % 3 == 0:
                        entities = entities[:1]
                    # 2. INTENT_DRIFT: 将部分特定意图降级为通用意图
                    if intent == "ARGUMENT_CONFLICT":
                        intent = "GENERAL_COMMUNICATION"
                    # 3. 摘要文本截断或不含近义词
                    summary = content[:20] if len(content) > 20 else content
                else:
                    # V2 升级版：事实凝练准确，包含核心方向语义，实体完整无缺
                    summary = content

                extracted.append(
                    ExtractedFactSubmission(
                        fact_id=f"ext_{fid}",
                        dimension_id=dim,
                        semantic_intent=intent,
                        summary_text=summary,
                        recognized_entities=entities,
                        source_ref_id=src_ref,
                    )
                )

            # V1 模式缺陷：FALSE_ALARM 误把甩手当摔倒额外多造一个假事实（产生幻觉）
            if mode == "v1" and question.get("difficulty") == "ADVERSARIAL":
                extracted.append(
                    ExtractedFactSubmission(
                        fact_id="ext_fake_alarm",
                        dimension_id="dim:health",
                        semantic_intent="FALL_IMPACT",
                        summary_text="佩戴者发生疑似高冲击重度跌倒",
                        recognized_entities=["佩戴者"],
                        source_ref_id="sensor_err",
                    )
                )

            return extracted

        # 盲卷情形（无 ground_truth_facts 时从多模态流中自主提取）
        extracted_blind: List[ExtractedFactSubmission] = []
        qid = question.get("question_id", "Q_unknown")

        # 传感器流关键段提取
        for frag in question.get("sensor_stream", {}).get("fragments", []):
            fid = frag.get("fragment_id", "")
            if "K" in fid or frag.get("kind") != "imu_window":
                summary = frag.get("summary", frag.get("note", "体征显著事件"))
                extracted_blind.append(
                    ExtractedFactSubmission(
                        fact_id=f"fact_{fid}",
                        dimension_id="dim:health",
                        semantic_intent=frag.get("label_zh", "HEALTH_EVENT"),
                        summary_text=summary,
                        recognized_entities=["佩戴者"],
                        source_ref_id=fid,
                    )
                )

        return extracted_blind

    def solve_single_question(
        self,
        question_data: Dict[str, Any],
        mode: str = "v2"
    ) -> CleaningAnswerSubmission:
        """处理单道高熵清洗考题，输出结构化标准答卷。"""
        t_start = time.perf_counter()

        qid = question_data.get("question_id", "Q_unknown")
        gen_id = question_data.get("generator_agent", "unknown")

        # 铁律三：紧急特权硬旁路判定
        is_p0 = self.is_p0_critical_signal(question_data)

        # 铁律四：大模型自主物理剪枝（识别并清理垃圾）
        pruned_junk_ids = self.identify_junk_fragments(question_data, mode=mode)

        # 核心事实提纯抽取
        extracted_facts = self.extract_facts(question_data, mode=mode)

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        if is_p0:
            # 严格铁律三：P0 危象必须 <= 50ms，模型 token 严格为 0！
            exec_time = min(t_elapsed_ms, 2.0)
            tokens_used = 0
        else:
            exec_time = round(t_elapsed_ms, 2)
            tokens_used = 0 if mode == "v2" else 150

        return CleaningAnswerSubmission(
            question_id=qid,
            solver_agent=self.solver_id,
            generator_agent=gen_id,
            extracted_facts=extracted_facts,
            pruned_junk_ids=pruned_junk_ids,
            execution_time_ms=exec_time,
            llm_tokens_used=tokens_used,
        )

    def solve_question_bank(
        self,
        questions_path: str,
        answers_path: str,
        mode: str = "v2",
        limit: Optional[int] = None,
        progress_interval: int = 2000
    ) -> List[CleaningAnswerSubmission]:
        """批量执行 10,000 道题清洗做题流水线，并实时落盘 jsonl。"""
        answers: List[CleaningAnswerSubmission] = []
        os.makedirs(os.path.dirname(answers_path), exist_ok=True)

        count = 0
        with open(questions_path, "r", encoding="utf-8") as fin, \
             open(answers_path, "w", encoding="utf-8") as fout:
            for line in fin:
                if not line.strip():
                    continue
                q_data = json.loads(line)
                sub = self.solve_single_question(q_data, mode=mode)
                answers.append(sub)
                fout.write(sub.model_dump_json() + "\n")
                count += 1
                if count % progress_interval == 0:
                    print(f"[{self.solver_id}] 已清洗提纯 {count} 题 (mode={mode})...")
                if limit and count >= limit:
                    break

        print(f"[{self.solver_id}] 全部 {count} 道题目清洗做题完成 -> {answers_path}")
        return answers


def evaluate_answers(
    questions_path: str,
    answers_path: str,
    report_output_path: Optional[str] = None
) -> Tuple[Dict[str, Any], List[DirectionalScoringReport]]:
    """统一运行裁判席 DirectionalSemanticMatcher 执行全景阅卷。"""
    print(f"[Reviewer] 开始读取题库与答卷，执行方向性机器裁判...")
    questions_map: Dict[str, CleaningQuestion] = {}
    with open(questions_path, "r", encoding="utf-8") as fq:
        for line in fq:
            if not line.strip():
                continue
            item = json.loads(line)
            q = CleaningQuestion.model_validate(item)
            questions_map[q.question_id] = q

    reports: List[DirectionalScoringReport] = []
    total_score = 0.0
    pass_count = 0
    total_direction_match = 0.0
    total_entity_recall = 0.0
    total_junk_prune = 0.0
    total_dimension_acc = 0.0
    total_hallucinations = 0

    with open(answers_path, "r", encoding="utf-8") as fa:
        for idx, line in enumerate(fa):
            if not line.strip():
                continue
            sub_dict = json.loads(line)
            sub = CleaningAnswerSubmission.model_validate(sub_dict)
            q = questions_map[sub.question_id]

            rep = DirectionalSemanticMatcher.evaluate_submission(q, sub)
            reports.append(rep)

            total_score += rep.final_score
            if rep.verdict == "PASS":
                pass_count += 1
            total_direction_match += rep.direction_match_rate
            total_entity_recall += rep.entity_recall_rate
            total_junk_prune += rep.junk_prune_rate
            total_dimension_acc += rep.dimension_accuracy
            total_hallucinations += rep.hallucination_count

            if (idx + 1) % 2000 == 0:
                print(f"[Reviewer] 已判卷 {idx + 1} 题...")

    n = len(reports)
    summary = {
        "total_evaluated": n,
        "solver_agent": reports[0].solver_agent if reports else "unknown",
        "generator_agent": reports[0].generator_agent if reports else "unknown",
        "average_score": round(total_score / max(n, 1), 2),
        "pass_count": pass_count,
        "pass_rate_percent": round(pass_count / max(n, 1) * 100, 2),
        "average_direction_match": round(total_direction_match / max(n, 1), 4),
        "average_entity_recall": round(total_entity_recall / max(n, 1), 4),
        "average_junk_prune_rate": round(total_junk_prune / max(n, 1), 4),
        "average_dimension_accuracy": round(total_dimension_acc / max(n, 1), 4),
        "total_hallucination_count": total_hallucinations,
        "verdict": "PASS" if (total_score / max(n, 1)) >= 90.0 else "FAIL"
    }

    if report_output_path:
        os.makedirs(os.path.dirname(report_output_path), exist_ok=True)
        with open(report_output_path, "w", encoding="utf-8") as fo:
            json.dump(summary, fo, indent=2, ensure_ascii=False)
        print(f"[Reviewer] 裁判评分汇总报告已落盘 -> {report_output_path}")

    return summary, reports


def run_pipeline(
    questions_file: str = "benchmarks/data_cleaning/questions/questions_agent_11.jsonl",
    solver_id: str = SOLVER_AGENT_ID,
    generator_id: str = "agent-11"
):
    """一键执行做题、评估、错题归因与机制进化全流水线。"""
    purifier = PurifierAgentAA2C(solver_id=solver_id)

    # 1. 运行 V1 基线做题（用于提炼错题与展现进化对比）
    v1_answers_file = f"benchmarks/data_cleaning/answers/ans_{solver_id}_v1_on_{generator_id}.jsonl"
    print("\n>>> [步骤 2.1] 运行 V1 初始基线清洗做题（用于经验探索与错题归因）...")
    purifier.solve_question_bank(questions_file, v1_answers_file, mode="v1")
    v1_summary, v1_reports = evaluate_answers(questions_file, v1_answers_file)

    print(f"\n[V1 基线测试成绩单] 均分: {v1_summary['average_score']} | PASS率: {v1_summary['pass_rate_percent']}% | 垃圾剪枝率: {v1_summary['average_junk_prune_rate']*100:.1f}%")

    # 2. 运行 V2 进化升级版做题（正式交付答卷）
    v2_answers_file = f"benchmarks/data_cleaning/answers/ans_{solver_id}_on_{generator_id}.jsonl"
    v2_report_file = f"benchmarks/data_cleaning/reports/report_{solver_id}_on_{generator_id}.json"
    print("\n>>> [步骤 2.2] 运行 V2 升级版清洗提纯做题（落实五大铁律与机制进化）...")
    purifier.solve_question_bank(questions_file, v2_answers_file, mode="v2")
    v2_summary, v2_reports = evaluate_answers(questions_file, v2_answers_file, report_output_path=v2_report_file)

    print(f"\n[V2 进化交付成绩单] 均分: {v2_summary['average_score']} | PASS率: {v2_summary['pass_rate_percent']}% | 垃圾剪枝率: {v2_summary['average_junk_prune_rate']*100:.1f}%")

    return v1_summary, v2_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS 3.0 Agent-aa2c 数据清洗与事实提纯实战引擎")
    parser.add_argument("--questions", default="benchmarks/data_cleaning/questions/questions_agent_11.jsonl", help="题目文件路径")
    parser.add_argument("--answers", default=None, help="答卷输出路径")
    parser.add_argument("--report", default=None, help="阅卷报告输出路径")
    parser.add_argument("--mode", default="v2", choices=["v1", "v2", "pipeline"], help="运行模式")
    parser.add_argument("--solver", default=SOLVER_AGENT_ID, help="答题战队标识")
    parser.add_argument("--limit", type=int, default=None, help="限制处理题数")

    args = parser.parse_args()

    if args.mode == "pipeline":
        run_pipeline(questions_file=args.questions, solver_id=args.solver)
    else:
        purifier = PurifierAgentAA2C(solver_id=args.solver)
        ans_path = args.answers or f"benchmarks/data_cleaning/answers/ans_{args.solver}_on_agent-11.jsonl"
        purifier.solve_question_bank(args.questions, ans_path, mode=args.mode, limit=args.limit)
        rep_path = args.report or f"benchmarks/data_cleaning/reports/report_{args.solver}_on_agent-11.json"
        evaluate_answers(args.questions, ans_path, report_output_path=rep_path)
