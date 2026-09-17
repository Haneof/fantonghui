#!/usr/bin/env python3
"""AIOS 3.0 真实认知实战大考题库 · 协议兼容 + 宪法纪律双门禁校验器。

用法：
    python3 scripts/cognitive_arena/validate_exam_bank.py
    python3 scripts/cognitive_arena/validate_exam_bank.py --bank /tmp/sample --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from pools_dimensions import ANTI_DIAGNOSIS_REDLINES, DIMENSION_VOCABULARY  # noqa: E402

ALLOWED_SOURCES = {"MIC", "APP", "SENSOR"}
CONFLICT_MARKERS = ("分手", "离婚", "裁员", "被批评", "争吵", "吵架", "投诉", "住院", "诈骗", "被骂",
                    "扣钱", "离职", "打架", "病危", "急症", "危机", "受挫", "被否", "垫底", "罚")
NIGHT_MARKERS = ("深夜", "凌晨", "半夜", "夜里")
DAY_LO, DAY_HI = 7 * 60, 17 * 60
ID_PATTERN = re.compile(r"^COGN-DAY-2026-\d{6}$")
TYPE_RATIO = {"A": 0.42, "B": 0.30, "C": 0.18, "D": 0.10}
TYPE_DIFFICULTY = {
    "A": "MULTI_CONFLICT",
    "B": "SUBTLE_UNDERTONE",
    "C": "FAMILY_CRISIS_ANTI_FRAUD",
    "D": "ADVERSARIAL_TRAP",
}
REQUIRED_CANDIDATE_FIELDS = (
    "rationale_why_existing_insufficient",
    "data_sources",
    "update_mechanism",
    "intended_cognitive_or_task_use",
    "expected_user_benefit",
    "overlap_with_existing_dimensions",
    "maintenance_cost_and_invalidation",
)


def minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


def shard_sha256(payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def validate_question(raw: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    qid = raw.get("question_id", "<no-id>")
    exam_type = raw.get("exam_type")
    if exam_type not in TYPE_DIFFICULTY:
        errors.append(f"{qid}: exam_type 非法（{exam_type}）")
        return

    # --- 协议兼容：必须能被权威 pydantic 模型直接反序列化 ---
    try:
        from aios_core.simulation.cognitive_arena_protocol import CognitiveExamQuestion

        model = CognitiveExamQuestion.model_validate(raw)
        if str(model.difficulty) != TYPE_DIFFICULTY[exam_type]:
            errors.append(f"{qid}: difficulty 与 exam_type 不匹配（{model.difficulty}）")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{qid}: 协议反序列化失败 -> {type(exc).__name__}: {exc}")
        return

    # --- 时间轴结构 ---
    timeline = raw["cleaned_daily_stream"]["timeline"]
    if not 8 <= len(timeline) <= 15:
        errors.append(f"{qid}: 时间轴切片数 {len(timeline)} 不在 8~15 之间")
    seen_times: Counter = Counter()
    for sl in timeline:
        if not isinstance(sl, dict) or "text" not in sl:
            errors.append(f"{qid}: 时间轴存在非法切片 -> {sl!r}")
            continue
        seen_times[sl["time"]] += 1
        if sl["source"] not in ALLOWED_SOURCES:
            errors.append(f"{qid}: 非法来源 {sl['source']}")
        if sl["source"] == "APP" and not sl.get("app"):
            errors.append(f"{qid}: APP 切片缺少 app 字段（{sl['text'][:18]}）")
        try:
            m = minutes(sl["time"])
        except Exception:  # noqa: BLE001
            errors.append(f"{qid}: 时间格式非法 {sl['time']}")
            continue
        quoted = "“" in sl["text"] or "”" in sl["text"]
        retrospective = any(k in sl["text"] for k in ("晨间回顾", "前夜", "睡前回顾", "昨夜"))
        if (not quoted) and (not retrospective) and sl["source"] != "MIC" \
                and any(k in sl["text"] for k in NIGHT_MARKERS) and DAY_LO <= m <= DAY_HI:
            errors.append(f"{qid}: 夜间文案落在白天时段 {sl['time']}（{sl['text'][:24]}）")
        if "{" in sl["text"] or "}" in sl["text"]:
            errors.append(f"{qid}: 切片存在未替换占位符（{sl['text'][:24]}）")
    duplicate_times = [t for t, c in seen_times.items() if c > 2]
    if duplicate_times:
        warnings.append(f"{qid}: 多个切片共用同一时刻 {duplicate_times[:3]}")

    # --- 体征摘要 ---
    summary = raw["cleaned_daily_stream"]["vitals_summary"]
    if not summary["hr_peaks"]:
        errors.append(f"{qid}: 缺少心率峰值记录")
    if exam_type == "A" and not any(p["bpm"] >= 115 for p in summary["hr_peaks"]):
        errors.append(f"{qid}: 类型 A 必须含一次 >=115bpm 的静息应激峰值")

    # --- 白天手环交互（照妖镜）---
    interactions = raw["daytime_ai_interactions"]
    if not 1 <= len(interactions) <= 2:
        errors.append(f"{qid}: 手环交互数 {len(interactions)} 不在 1~2 之间")
    for item in interactions:
        if item["ai_action_taken"] == "SPOKEN" and not item.get("ai_spoken_text"):
            errors.append(f"{qid}: SPOKEN 交互缺少 ai_spoken_text")
        if item["ai_action_taken"] == "SILENCE" and item.get("ai_spoken_text"):
            errors.append(f"{qid}: SILENCE 交互不应带播报文本")
    responses = {i["user_response"] for i in interactions}
    if exam_type in {"A", "B", "C"} and not (responses & {"IGNORED", "IRRITATED"}):
        errors.append(f"{qid}: A/B/C 卷必须含至少一次被 IGNORED/IRRITATED 的打扰")

    # --- 标答与红线 ---
    ground_truth = raw["ground_truth"]
    redlines = ground_truth["anti_diagnosis_redlines"]
    if not redlines:
        errors.append(f"{qid}: 缺少反过度诊断红线")
    for redline in redlines:
        if not (redline.startswith("【") and redline.endswith("】")):
            errors.append(f"{qid}: 红线必须为【完整肯定性命题】形式 -> {redline[:24]}")
    if redlines and redlines != ANTI_DIAGNOSIS_REDLINES[exam_type]:
        warnings.append(f"{qid}: 红线与标准池不一致（允许定制，仅提示）")
    anchors = ground_truth["user_summary_core_anchors"]
    if not 3 <= len(anchors) <= 4:
        errors.append(f"{qid}: 核心锚点必须 3~4 个，当前 {len(anchors)}")
    for link in ground_truth["expected_causal_chain"]:
        for dim in (link["source_dim"], link["target_dim"]):
            if dim not in DIMENSION_VOCABULARY:
                errors.append(f"{qid}: 因果链维度不在词表内 -> {dim}")

    # --- AI 自省要求（照镜子）---
    demands = ground_truth["ai_self_review_demands"]
    if exam_type in {"A", "B", "C"}:
        if not demands.get("must_lower_restraint"):
            errors.append(f"{qid}: 存在被打扰交互却未要求下调克制分（虚伪满分风险）")
    if not demands.get("must_cover_dimensions"):
        errors.append(f"{qid}: 缺少 AI 自身五维度覆盖要求")

    # --- 新维度提炼（考场三）---
    extension = raw.get("judge_extensions", {})
    expected = ground_truth["expected_new_dimension"]
    if exam_type == "D":
        if expected is not None:
            errors.append(f"{qid}: 陷阱卷 expected_new_dimension 必须为 null")
        if not extension.get("must_judge_no_new_dimension"):
            errors.append(f"{qid}: 陷阱卷缺少 must_judge_no_new_dimension 口径")
        for sl in timeline:
            if any(k in sl["text"] for k in CONFLICT_MARKERS):
                errors.append(f"{qid}: 陷阱卷时间轴出现冲突类事件（{sl['text'][:24]}）")
        for item in interactions:
            if any(k in item["context_note"] for k in CONFLICT_MARKERS):
                errors.append(f"{qid}: 陷阱卷交互上下文出现冲突类事件（{item['context_note'][:24]}）")
    else:
        if not expected:
            errors.append(f"{qid}: A/B/C 卷必须给出 expected_new_dimension")
        candidate = extension.get("candidate_dimension_full")
        if not candidate:
            errors.append(f"{qid}: 缺少宪法第 73 条候选维度全文")
        else:
            if candidate.get("article_73_element_count") != 10:
                errors.append(f"{qid}: 第 73 条要素数不为 10")
            if len(candidate.get("article_76_self_scores", {})) != 6:
                errors.append(f"{qid}: 第 76 条自评分不为 6 项")
            for field in REQUIRED_CANDIDATE_FIELDS:
                if not candidate.get(field):
                    errors.append(f"{qid}: 候选维度缺少要素 {field}")
            if expected and candidate.get("dimension_id") != expected.get("dimension_id"):
                errors.append(f"{qid}: 候选维度与 expected_new_dimension 不一致")

    # --- C 卷反诈要求 ---
    if exam_type == "C":
        for field in ("fraud_red_flags", "safe_action_requirements", "dangerous_action_redlines"):
            if not extension.get(field):
                errors.append(f"{qid}: 类型 C 缺少 {field}")
        safe_text = " ".join(extension.get("safe_action_requirements", []))
        if not any(k in safe_text for k in ("官方", "96110", "110", "12333")):
            errors.append(f"{qid}: 类型 C 缺少官方核验类安全动作")


def validate(bank_dir: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    index_path = bank_dir / "index.json"
    if not index_path.exists():
        return {"passed": False, "errors": [f"缺少 index.json：{bank_dir}"], "warnings": [],
                "bank_id": None, "total_questions": 0, "validated_questions": 0,
                "type_distribution": {}}

    index = json.loads(index_path.read_text(encoding="utf-8"))
    questions: List[Dict[str, Any]] = []
    for shard in index["shards"]:
        shard_path = bank_dir / shard["file"]
        if not shard_path.exists():
            errors.append(f"缺少分片文件 {shard['file']}")
            continue
        payload = json.loads(shard_path.read_text(encoding="utf-8"))
        if shard_sha256(payload) != shard["sha256"]:
            errors.append(f"{shard['file']}: sha256 与 index.json 不一致")
        if payload["shard_id"] != shard["shard_id"]:
            errors.append(f"{shard['file']}: shard_id 不一致")
        if len(payload["questions"]) != shard["count"]:
            errors.append(f"{shard['file']}: 题量与 index 不一致")
        questions.extend(payload["questions"])

    if len(questions) != index["total_questions"]:
        errors.append(f"实际题量 {len(questions)} 与 index 声明 {index['total_questions']} 不一致")

    ids = [q["question_id"] for q in questions]
    if len(set(ids)) != len(ids):
        errors.append("question_id 存在重复")
    for qid in ids:
        if not ID_PATTERN.match(qid):
            errors.append(f"question_id 格式非法：{qid}")

    personas = [(q["persona"]["name"], q["persona"]["occupation"]) for q in questions]
    if len(set(personas)) != len(personas):
        dup = [p for p, c in Counter(personas).items() if c > 1][:3]
        errors.append(f"(姓名, 职业) 组合重复：{dup}")

    for raw in questions:
        validate_question(raw, errors, warnings)

    type_counts = Counter(q["exam_type"] for q in questions)
    total = len(questions) or 1
    ratio_report = {}
    for exam_type, ratio in TYPE_RATIO.items():
        actual = type_counts.get(exam_type, 0)
        ratio_report[exam_type] = {"count": actual, "ratio": round(actual / total, 4)}
        if questions and abs(actual / total - ratio) > 0.015:
            errors.append(f"题型 {exam_type} 占比 {actual / total:.4f} 偏离配额 {ratio}")

    return {
        "bank_id": index["bank_id"],
        "bank_dir": str(bank_dir),
        "total_questions": index["total_questions"],
        "validated_questions": len(questions),
        "type_distribution": ratio_report,
        "dimension_vocabulary_size": len(DIMENSION_VOCABULARY),
        "candidate_dimensions": len({q["ground_truth"]["expected_new_dimension"]["dimension_name"]
                                     for q in questions
                                     if q["ground_truth"]["expected_new_dimension"]}),
        "errors": errors,
        "warnings": warnings,
        "passed": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验真实认知实战大考题库")
    parser.add_argument("--bank", type=str,
                        default=str(REPO_ROOT / "benchmarks/cognitive_arena/papers/exam_bank_1000"),
                        help="题库目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = parser.parse_args()

    report = validate(Path(args.bank))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["passed"] else 1

    print(f"bank_id           : {report['bank_id']}")
    print(f"total_questions   : {report['total_questions']}")
    print(f"validated         : {report['validated_questions']}")
    print(f"type_distribution : {json.dumps(report['type_distribution'], ensure_ascii=False)}")
    print(f"candidate_dims    : {report['candidate_dimensions']}")
    print(f"warnings          : {len(report['warnings'])}")
    for warning in report["warnings"][:10]:
        print(f"  [warn] {warning}")
    if report["errors"]:
        for error in report["errors"][:40]:
            print(f"  [error] {error}")
        print(f"FAIL ❌ 共 {len(report['errors'])} 项不合规")
        return 1
    print("PASS ✅ 全部题卷通过协议兼容与宪法纪律校验")
    return 0


if __name__ == "__main__":
    sys.exit(main())
