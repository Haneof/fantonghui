#!/usr/bin/env python3
"""AIOS 3.0 认知实战大考题库 · 题面质量审计器（非评分器）。

职责边界：本脚本只做**题面工程质量审计**，不参与任何认知裁决、不做分数判定。
它回答的问题是：“这批卷子作为考试素材，是否存在穿帮、错配、重复、未渲染占位符？”

审计项：
  1. 协议兼容：整卷可被 CognitiveExamQuestion 解析
  2. 时间轴：8~15 切片、时间可解析且升序、来源/类型枚举合法
  3. 占位符：任何 {xxx} 残留一律报错
  4. 性别/关系词：与 persona 性别、关系状态冲突的称谓
  5. 场景错配：AI 交互 / 受挫现场 提到的场景（健身房、灵堂、病房、夜跑、公交…）
                必须与人设（职业域、爱好、通勤方式、题型）相容
  6. 重复度：同卷内重复切片、跨卷完全重复句子占比、候选维度分布同质化
  7. 人设唯一性：(姓名, 职业) 组合不得重复

用法：
    python3 scripts/cognitive_arena/audit_exam_bank.py --bank <bank_dir> [--json]
    python3 scripts/cognitive_arena/audit_exam_bank.py --bank /tmp/sample --top 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.simulation.cognitive_arena_protocol import (  # noqa: E402
    CognitiveExamQuestion,
)
from pools_stream import OCCUPATION_DOMAIN  # noqa: E402

PLACEHOLDER_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# 场景 → 相容条件（任一满足即可）
SCENE_RULES: List[Tuple[str, str]] = [
    ("健身房|深蹲|撸铁|杠铃", "hobby_sport"),
    ("夜跑|乡村小路|跑步节奏", "hobby_run"),
    ("骑行|电动车|单车", "commute_bike"),
    ("公交车|公交", "commute_bus"),
    ("地铁", "commute_metro"),
    ("灵堂|殡仪馆|告别厅|遗物|已故", "mourning"),
    ("病房|陪护|走廊过夜|护理垫|住院", "caregiving"),
    ("手术室|术前准备|抢救区|急诊|麻醉", "clinical"),
    ("教室|全班|讲台|上课|班会|学生", "teaching"),
    ("工地|返工|道岔|信号检修|监理", "field_work"),
    ("同传|会场|翻译", "interpreting"),
    ("驾驶|开车|堵车", "driving"),
]

OCC_SCENE_HINTS: List[Tuple[str, str]] = [
    ("医师|护士|技师|药师|医师|麻醉", "clinical"),
    ("教师|老师|辅导员|实训|实验员|园长", "teaching"),
    ("编辑|记者|策划|插画|摄影|剪辑|设计|律师|传译", "creative"),
    ("工地|检修|调度|货运|司机|环卫|物业|维保|农场", "field_work"),
]

RELATION_WORDS = ("妻子", "丈夫", "老公", "老婆", "岳父", "岳母", "公婆", "未婚妻", "未婚夫", "伴侣")


def parse_time(t: str) -> Optional[int]:
    m = TIME_RE.match(t)
    if not m:
        return None
    hh, mm = t.split(":")
    mins = int(hh) * 60 + int(mm)
    return mins + 1440 if int(hh) < 5 else mins


def load_bank(bank_dir: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    questions: List[Dict[str, Any]] = []
    problems: List[str] = []
    shards = sorted(bank_dir.glob("shard_*.json"))
    if not shards:
        problems.append(f"{bank_dir} 下没有找到 shard_*.json")
    for path in shards:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload["questions"] if isinstance(payload, dict) else payload
        questions.extend(items)
    return questions, problems


def scene_tokens(question: Dict[str, Any]) -> Dict[str, bool]:
    persona = question["persona"]
    occ = persona["occupation"]
    hobbies = " ".join(persona.get("hobbies", []))
    commute = persona.get("commute", "")
    domain = OCCUPATION_DOMAIN.get(occ, "OFFICE")
    flags = persona.get("relationship_flags", {})
    tokens = {
        "hobby_sport": any(k in hobbies for k in ("拳击", "夜跑", "骑行", "游泳", "羽毛球", "爬山", "健身")),
        "hobby_run": "夜跑" in hobbies or "晨跑" in hobbies,
        "commute_bike": ("骑行" in commute) or ("电动车" in commute) or ("骑行" in hobbies),
        "commute_bus": "公交" in commute,
        "commute_metro": "地铁" in commute,
        "driving": "自驾" in commute or "开车" in commute,
        "clinical": domain == "MEDICAL" or any(k in occ for k in ("医师", "护士", "技师", "药师")),
        "teaching": domain == "EDU" or any(k in occ for k in ("教师", "老师", "辅导员", "实训")),
        "interpreting": "同声传译" in occ,
        "field_work": domain == "FIELD" or any(k in occ for k in ("工地", "检修", "调度", "货运", "环卫", "物业", "维保")),
        "creative": domain == "CREATIVE" or any(k in occ for k in ("编辑", "记者", "策划", "插画", "摄影", "剪辑", "设计")),
    }
    # 哀伤/照护场景必须由题型保证：B（隐性内伤）可出现哀伤，C（长辈危机）可出现陪护
    tokens["mourning"] = question.get("exam_type") == "B" or any(k in occ for k in ("殡葬",))
    tokens["caregiving"] = question.get("exam_type") == "C"
    return tokens


def audit_question(question: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    qid = question.get("question_id", "<no-id>")

    try:
        CognitiveExamQuestion.model_validate(question)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"{qid}: 协议解析失败 {exc}")
        return issues

    persona = question["persona"]
    stream = question["cleaned_daily_stream"]
    timeline = stream.get("timeline", [])
    tokens = scene_tokens(question)

    if not (8 <= len(timeline) <= 15):
        issues.append(f"{qid}: 时间轴切片数 {len(timeline)} 不在 8~15")

    last = -1
    for slice_ in timeline:
        t = slice_.get("time", "")
        mins = parse_time(t)
        if mins is None:
            issues.append(f"{qid}: 时间格式非法 {t!r}")
            continue
        if mins < last:
            issues.append(f"{qid}: 时间轴倒序 {t} 出现在 {last} 之后")
        last = mins
        text = str(slice_.get("text", ""))
        if PLACEHOLDER_RE.search(text):
            issues.append(f"{qid}: 占位符未渲染 -> {text[:60]}")
        for pattern, token in SCENE_RULES:
            if re.search(pattern, text) and not tokens.get(token, False):
                issues.append(f"{qid}: 场景错配[{token}] -> {text[:70]}")
                break

    # AI 交互场景错配
    for inter in question.get("daytime_ai_interactions", []):
        blob = f"{inter.get('trigger_event', '')} {inter.get('context_note', '')}"
        if PLACEHOLDER_RE.search(blob):
            issues.append(f"{qid}: AI 交互占位符未渲染 -> {blob[:60]}")
        for pattern, token in SCENE_RULES:
            if re.search(pattern, blob) and not tokens.get(token, False):
                issues.append(f"{qid}: AI 交互场景错配[{token}] -> {blob[:70]}")
                break

    # 性别/关系称谓（只审剧情文本：时间轴 + AI 交互 + 人设字段，不审裁判扩展词表）
    gender = persona.get("gender")
    flags = persona.get("relationship_flags", {})
    persona_blob = json.dumps(persona, ensure_ascii=False)
    story_blob = json.dumps(
        {
            "timeline": timeline,
            "interactions": question.get("daytime_ai_interactions", []),
            "anchors": question["ground_truth"].get("user_summary_core_anchors", []),
        },
        ensure_ascii=False,
    )
    blob_all = persona_blob + story_blob
    if gender == "女":
        for word in ("岳父", "岳母", "丈夫", "老公"):
            if word in blob_all:
                issues.append(f"{qid}: 女性人设出现称谓 {word}")
    if gender == "男":
        for word in ("公婆", "婆婆", "妻子" if not flags.get("married") else "___never___"):
            if word in blob_all and word != "___never___":
                issues.append(f"{qid}: 男性人设出现称谓 {word}")
    if flags.get("single") and not flags.get("partner"):
        for word in ("妻子", "丈夫", "老公", "老婆", "伴侣"):
            if word in blob_all and "单身" not in blob_all.split(word)[0][-20:]:
                issues.append(f"{qid}: 单身人设出现 {word}")
                break
    tags = persona.get("background_tags", [])
    if "独居" in tags and (flags.get("married") or flags.get("has_child")):
        issues.append(f"{qid}: 背景标签“独居”与已婚/有子女冲突")
    if question.get("exam_type") != "C" and any(k in blob_all for k in ("住院", "护工", "陪护椅")):
        issues.append(f"{qid}: 非 C 卷出现长辈住院/陪护场景")

    # 同卷内重复句子
    texts = [str(s.get("text", "")) for s in timeline]
    dupes = [t for t, c in Counter(texts).items() if c > 1]
    for d in dupes[:2]:
        issues.append(f"{qid}: 同卷重复切片 -> {d[:50]}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="认知大考题库题面质量审计器")
    parser.add_argument("--bank", default=str(REPO_ROOT / "benchmarks/cognitive_arena/papers/exam_bank_1000"),
                        help="题库目录（含 shard_*.json）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--top", type=int, default=15, help="最多展示多少条问题")
    args = parser.parse_args()

    bank_dir = Path(args.bank)
    questions, problems = load_bank(bank_dir)

    all_issues: List[str] = list(problems)
    for q in questions:
        all_issues.extend(audit_question(q))

    # 跨卷重复度（整句完全一致）
    sentence_counter: Counter = Counter()
    for q in questions:
        for s in q["cleaned_daily_stream"].get("timeline", []):
            sentence_counter[str(s.get("text", ""))] += 1
    repeated = {t: c for t, c in sentence_counter.items() if c > 3}

    # 人设唯一性
    combos = Counter((q["persona"]["name"], q["persona"]["occupation"]) for q in questions)
    dup_personas = [k for k, v in combos.items() if v > 1]

    report = {
        "bank_dir": str(bank_dir),
        "total_questions": len(questions),
        "issues": all_issues,
        "issue_count": len(all_issues),
        "repeated_sentences_over_3": len(repeated),
        "duplicate_personas": dup_personas,
        "type_distribution": dict(Counter(q.get("exam_type") for q in questions)),
        "passed": not all_issues and not dup_personas,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"bank            : {report['bank_dir']}")
        print(f"questions       : {report['total_questions']}")
        print(f"type_distribution: {report['type_distribution']}")
        print(f"repeated_sentences(>3 卷): {report['repeated_sentences_over_3']}")
        print(f"duplicate personas: {len(dup_personas)}")
        for issue in all_issues[: args.top]:
            print(f"  [ISSUE] {issue}")
        if len(all_issues) > args.top:
            print(f"  ... 其余 {len(all_issues) - args.top} 条")
        print("PASS ✅ 题面审计通过" if report["passed"] else "FAIL ❌ 存在题面工程问题")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
