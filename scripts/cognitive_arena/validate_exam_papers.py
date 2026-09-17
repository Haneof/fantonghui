#!/usr/bin/env python3
"""出卷考官契约校验器：认知实战大考卷批次合规性校验 (validate_exam_papers.py).

上位依据：
- 《AIOS核心系统宪法v3.0》第三十三条之二（反过度诊断公理、反向全命题红线、denegate 护栏、他人主体隔离）
- 《AIOS核心系统宪法v3.0》第七十二条至第七十六条（新维度提炼三重硬门槛与防维度爆炸）
- governance/dispatches/PROMPTS_COGNITIVE_ARENA_EXAM.md 第二节「出卷考官提示词」四条出题铁律
- governance/dispatches/TASK_DISPATCH_COGNITIVE_ARENA_DUAL_WORLD_AND_DIMENSIONS.md 三大考场规格

用途：
1. 校验考卷 JSON 结构是否符合 src/aios_core/simulation/cognitive_arena_protocol.py 的数据契约
   （pydantic 可用时执行真实模型校验，不可用时降级为纯结构校验，保证零依赖可跑）；
2. 校验出卷考官契约（人设七要素、时间轴 8~15 切片、体征峰值可归因、白天交互含失当样本、
   标答四件套齐备、A/B/C 卷必须给出期望新维度、D 卷必须为 null 且克制分不得扣分）；
3. 校验批次分布（陷阱卷占比、题型覆盖、question_id 唯一性）。

运行：
    python3 scripts/cognitive_arena/validate_exam_papers.py            # 校验全部考卷
    python3 scripts/cognitive_arena/validate_exam_papers.py --strict   # 任一条不合规即以退出码 1 结束
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPERS_DIR = REPO_ROOT / "benchmarks" / "cognitive_arena" / "papers"

QUESTION_ID_PATTERN = re.compile(r"^COGN-DAY-2026-\d{6}$")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DIM_PATTERN = re.compile(r"^dim:[a-z][a-z0-9_]*$")

DIFFICULTIES = {"STANDARD", "MULTI_CONFLICT", "SUBTLE_UNDERTONE", "ADVERSARIAL_TRAP"}
SOURCES = {"SENSOR", "MIC", "APP"}
AI_ACTIONS = {"SPOKEN", "HAPTIC", "SILENCE"}
USER_RESPONSES = {"ACCEPTED", "IGNORED", "IRRITATED", "SILENT"}

# 题型 -> 法定难度映射（PROMPTS_COGNITIVE_ARENA_EXAM.md 出题铁律）
PAPER_TYPE_DIFFICULTY = {
    "A": "MULTI_CONFLICT",       # 多重冲突重压卷
    "B": "SUBTLE_UNDERTONE",     # 隐性内耗与潜台词卷
    "C": "MULTI_CONFLICT",       # 长辈突发危机与借贷反诈卷
    "D": "ADVERSARIAL_TRAP",     # 防虚妄衍生陷阱卷
}

# 既有稳定维度词表（严禁自造 ID，候选维度一律 dim:candidate_* 前缀）
STABLE_USER_DIMS = {
    "dim:career",
    "dim:career_skills",
    "dim:emotion",
    "dim:social",
    "dim:health",
    "dim:finance",
    "dim:life",
    "dim:habit",
    "dim:cognition",
    "dim:narrative",
}
AI_SELF_DIMS = {
    "dim:ai_conversational_restraint",
    "dim:ai_empathy_calibration",
    "dim:ai_causal_acuity",
    "dim:ai_intervention_value",
    "dim:ai_error_reflection",
}

# 无宿主 App 的切片类型（短信、系统通知），允许不标注 app 字段
_APP_LESS_KINDS = {"SMS", "NOTIFICATION", "SYSTEM"}

PERSONA_REQUIRED = (
    "name",
    "age",
    "occupation",
    "city",
    "relationship_status",
    "monthly_income_k",
    "background_tags",
)

ARTICLE_73_REFERENCE_KEYS = (
    "rationale_why_existing_insufficient",
    "data_sources",
    "update_mechanism",
    "intended_cognitive_or_task_use",
    "expected_user_benefit",
    "overlap_with_existing_dimensions",
    "maintenance_cost_and_invalidation",
)

ARTICLE_76_SCORE_KEYS = (
    "independence",
    "updatability",
    "verifiability",
    "expected_benefit",
    "cost_efficiency",
    "anti_overlap",
)


def _raw_minutes(hhmm: str) -> int:
    """把 HH:MM 折算为当日 00:00 起的分钟数。"""
    hour, minute = (int(p) for p in hhmm.split(":"))
    return hour * 60 + minute


def _circular_delta(a: str, b: str) -> int:
    """两个时刻的最小环形间隔（分钟），用于体征峰值与时间轴切片的落点匹配。"""
    diff = abs(_raw_minutes(a) - _raw_minutes(b))
    return min(diff, 24 * 60 - diff)


class TimelineClock:
    """按出现顺序推进的跨零点时钟：时间回退即视为跨入次日。"""

    def __init__(self) -> None:
        self._day_offset = 0
        self._previous: int | None = None

    def order(self, hhmm: str) -> int:
        raw = _raw_minutes(hhmm)
        current = raw + self._day_offset * 24 * 60
        if self._previous is not None and current < self._previous:
            self._day_offset += 1
            current += 24 * 60
        self._previous = current
        return current


class PaperReport:
    """单卷校验结果。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.data: Dict[str, Any] = {}

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _check_protocol_model(data: Dict[str, Any], report: PaperReport) -> None:
    """若 pydantic 与协议模块可用，执行真实数据契约校验（零依赖时跳过）。"""
    try:
        for entry in (str(REPO_ROOT), str(REPO_ROOT / "src")):
            if entry not in sys.path:
                sys.path.insert(0, entry)
        from src.aios_core.simulation.cognitive_arena_protocol import (  # noqa: PLC0415
            CognitiveExamQuestion,
        )
    except Exception as exc:  # pragma: no cover - 环境缺依赖时降级
        report.warn(f"协议模型不可用，降级为纯结构校验：{type(exc).__name__}: {exc}")
        return
    try:
        CognitiveExamQuestion.model_validate(data)
    except Exception as exc:
        report.error(f"违反 CognitiveExamQuestion 协议契约：{exc}")


def _check_identity(data: Dict[str, Any], report: PaperReport) -> str:
    qid = data.get("question_id", "")
    if not isinstance(qid, str) or not QUESTION_ID_PATTERN.match(qid):
        report.error(f"question_id 非法（应为 COGN-DAY-2026-XXXXXX）：{qid!r}")
    difficulty = data.get("difficulty")
    if difficulty not in DIFFICULTIES:
        report.error(f"difficulty 非法：{difficulty!r}")
    if not data.get("exam_date"):
        report.error("缺少 exam_date")
    paper_type = data.get("paper_type")
    if paper_type is not None:
        if paper_type not in PAPER_TYPE_DIFFICULTY:
            report.error(f"paper_type 非法（应为 A/B/C/D）：{paper_type!r}")
        elif PAPER_TYPE_DIFFICULTY[paper_type] != difficulty:
            report.error(
                f"paper_type={paper_type} 与 difficulty={difficulty} 不匹配，"
                f"法定应为 {PAPER_TYPE_DIFFICULTY[paper_type]}"
            )
    return qid


def _check_persona(data: Dict[str, Any], report: PaperReport) -> None:
    persona = data.get("persona")
    if not isinstance(persona, dict):
        report.error("缺少 persona 对象")
        return
    for key in PERSONA_REQUIRED:
        if key not in persona or persona[key] in ("", None, []):
            report.error(f"persona 缺少必填要素：{key}")
    tags = persona.get("background_tags")
    if isinstance(tags, list) and len(tags) < 3:
        report.error("persona.background_tags 至少 3 条（心理防御习惯必须写入）")


def _check_stream(data: Dict[str, Any], report: PaperReport) -> None:
    stream = data.get("cleaned_daily_stream")
    if not isinstance(stream, dict):
        report.error("缺少 cleaned_daily_stream 对象")
        return

    sleep = stream.get("sleep_prev_night")
    if not isinstance(sleep, dict):
        report.error("cleaned_daily_stream 缺少前夜睡眠 sleep_prev_night")
    else:
        for key in ("duration_hours", "deep_sleep_hours", "sleep_score"):
            if key not in sleep:
                report.error(f"sleep_prev_night 缺少 {key}")

    vitals = stream.get("vitals_summary")
    timeline: List[Dict[str, Any]] = stream.get("timeline") or []
    if not isinstance(vitals, dict):
        report.error("cleaned_daily_stream 缺少体征摘要 vitals_summary")
    else:
        if "resting_hr_morning" not in vitals:
            report.error("vitals_summary 缺少 resting_hr_morning")
        peaks = vitals.get("hr_peaks") or []
        if not peaks:
            report.error("vitals_summary.hr_peaks 为空（陷阱卷也须给出可归因的短暂波动）")
        for peak in peaks:
            if not isinstance(peak, dict):
                report.error(f"hr_peaks 元素非法：{peak!r}")
                continue
            for key in ("time", "bpm", "context"):
                if key not in peak:
                    report.error(f"hr_peaks 元素缺少 {key}：{peak!r}")
            if not TIME_PATTERN.match(str(peak.get("time", ""))):
                report.error(f"hr_peaks.time 格式非法：{peak.get('time')!r}")

    if not isinstance(timeline, list):
        report.error("cleaned_daily_stream.timeline 必须是数组")
        return
    if not 8 <= len(timeline) <= 15:
        report.error(f"timeline 切片数 {len(timeline)} 超出法定区间 8~15")

    clock = TimelineClock()
    prev_order = None
    source_hits: Dict[str, int] = {}
    for idx, item in enumerate(timeline):
        if not isinstance(item, dict):
            report.error(f"timeline[{idx}] 非法：{item!r}")
            continue
        stamp = str(item.get("time", ""))
        if not TIME_PATTERN.match(stamp):
            report.error(f"timeline[{idx}].time 格式非法：{stamp!r}")
        else:
            order = clock.order(stamp)
            if prev_order is not None and order < prev_order:
                report.error(f"timeline[{idx}] 时间倒序：{stamp}")
            prev_order = order
        source = item.get("source")
        if source not in SOURCES:
            report.error(f"timeline[{idx}].source 非法（应为 SENSOR/MIC/APP）：{source!r}")
        else:
            source_hits[source] = source_hits.get(source, 0) + 1
        if not item.get("kind"):
            report.error(f"timeline[{idx}] 缺少 kind")
        text = item.get("text")
        if not isinstance(text, str) or len(text) < 6:
            report.error(f"timeline[{idx}].text 缺失或过短")
        if source == "APP" and not item.get("app") and item.get("kind") not in _APP_LESS_KINDS:
            report.warn(f"timeline[{idx}] 为 APP 切片但未标注 app 名称")

    if len(source_hits) < 2:
        report.error(f"timeline 数据源过于单一，必须混合 MIC/APP/SENSOR：{source_hits}")

    # 体征峰值必须能在时间轴上找到落点（±20 分钟），确保峰值可归因、非凭空捏造
    for peak in (vitals.get("hr_peaks") or []) if isinstance(vitals, dict) else []:
        if not isinstance(peak, dict) or not TIME_PATTERN.match(str(peak.get("time", ""))):
            continue
        peak_time = str(peak["time"])
        anchored = any(
            TIME_PATTERN.match(str(s.get("time", "")))
            and _circular_delta(peak_time, str(s["time"])) <= 20
            for s in timeline
            if isinstance(s, dict)
        )
        if not anchored:
            report.error(f"hr_peaks {peak.get('time')} 在时间轴上无对应切片，峰值不可归因")


def _check_interactions(data: Dict[str, Any], report: PaperReport) -> List[Dict[str, Any]]:
    interactions = data.get("daytime_ai_interactions")
    if not isinstance(interactions, list) or not interactions:
        report.error("缺少 daytime_ai_interactions（照妖镜字段，缺一不可）")
        return []
    for idx, item in enumerate(interactions):
        if not isinstance(item, dict):
            report.error(f"daytime_ai_interactions[{idx}] 非法")
            continue
        for key in ("interaction_id", "timestamp", "trigger_event", "ai_action_taken",
                    "user_response", "context_note"):
            if not item.get(key):
                report.error(f"daytime_ai_interactions[{idx}] 缺少 {key}")
        action = item.get("ai_action_taken")
        if action not in AI_ACTIONS:
            report.error(f"daytime_ai_interactions[{idx}].ai_action_taken 非法：{action!r}")
        if item.get("user_response") not in USER_RESPONSES:
            report.error(
                f"daytime_ai_interactions[{idx}].user_response 非法："
                f"{item.get('user_response')!r}"
            )
        spoken = item.get("ai_spoken_text")
        if action == "SPOKEN" and not spoken:
            report.error(f"daytime_ai_interactions[{idx}] 为 SPOKEN 但缺 ai_spoken_text")
        if action in ("HAPTIC", "SILENCE") and spoken and not spoken.startswith("（"):
            report.warn(
                f"daytime_ai_interactions[{idx}] 为 {action}，ai_spoken_text 应以「（未发声…）」"
                "形式说明为屏幕文字而非骨传导发声"
            )
    return interactions


def _check_ground_truth(
    data: Dict[str, Any],
    interactions: List[Dict[str, Any]],
    report: PaperReport,
) -> None:
    gt = data.get("ground_truth")
    if not isinstance(gt, dict):
        report.error("缺少 ground_truth 对象")
        return

    chain = gt.get("expected_causal_chain") or []
    if not isinstance(chain, list) or len(chain) < 2:
        report.error("expected_causal_chain 至少 2 环跨维因果链")
    for idx, link in enumerate(chain):
        if not isinstance(link, dict):
            report.error(f"expected_causal_chain[{idx}] 非法")
            continue
        for key in ("source_dim", "target_dim", "causal_mechanism", "directional_keywords"):
            if not link.get(key):
                report.error(f"expected_causal_chain[{idx}] 缺少 {key}")
        for side in ("source_dim", "target_dim"):
            dim = str(link.get(side, ""))
            if not DIM_PATTERN.match(dim):
                report.error(f"expected_causal_chain[{idx}].{side} 格式非法：{dim!r}")
            elif dim.startswith("dim:candidate_"):
                report.error(f"expected_causal_chain[{idx}].{side} 不得使用候选维度：{dim}")
            elif dim not in STABLE_USER_DIMS:
                report.warn(f"expected_causal_chain[{idx}].{side} 不在既有稳定维度词表：{dim}")
        if link.get("source_dim") == link.get("target_dim"):
            report.error(f"expected_causal_chain[{idx}] 源维度与目标维度相同，不构成跨维联动")
        keywords = link.get("directional_keywords") or []
        if isinstance(keywords, list) and len(keywords) < 3:
            report.error(f"expected_causal_chain[{idx}].directional_keywords 少于 3 个方向性词")

    redlines = gt.get("anti_diagnosis_redlines") or []
    if not isinstance(redlines, list) or len(redlines) < 3:
        report.error("anti_diagnosis_redlines 至少 3 条反向全命题红线（一票否决项）")
    for red in redlines:
        if not isinstance(red, str) or len(red) < 4:
            report.error(f"anti_diagnosis_redlines 含非法条目：{red!r}")

    anchors = gt.get("user_summary_core_anchors") or []
    if not isinstance(anchors, list) or not 3 <= len(anchors) <= 4:
        report.error(f"user_summary_core_anchors 必须为 3~4 个事实锚点，当前 {len(anchors)} 个")

    demands = gt.get("ai_self_review_demands")
    if not isinstance(demands, dict) or "must_lower_restraint" not in demands:
        report.error("ai_self_review_demands 缺少 must_lower_restraint 判定")
    elif not isinstance(demands.get("must_lower_restraint"), bool):
        report.error("ai_self_review_demands.must_lower_restraint 必须为布尔值")
    if isinstance(demands, dict) and not demands.get("reason"):
        report.error("ai_self_review_demands 缺少 reason（必须点名具体时刻与失当行为）")

    paper_type = data.get("paper_type")
    new_dim = gt.get("expected_new_dimension", "MISSING")
    if new_dim == "MISSING":
        report.error("缺少 expected_new_dimension 字段（陷阱卷必须显式写 null）")

    bad_interactions = [
        i for i in interactions
        if isinstance(i, dict) and i.get("user_response") in ("IGNORED", "IRRITATED")
    ]

    if paper_type == "D":
        if new_dim is not None:
            report.error("D 类陷阱卷 expected_new_dimension 必须为 null（严禁虚妄衍生）")
        if isinstance(demands, dict) and demands.get("must_lower_restraint") is True:
            report.error("D 类陷阱卷白天介入得当时不得强制扣克制分（must_lower_restraint 应为 false）")
        if bad_interactions:
            report.warn(
                "D 类陷阱卷出现被无视/被斥责的发声样本，请确认是否仍需 must_lower_restraint=true"
            )
    else:
        if paper_type in ("A", "B", "C"):
            if not isinstance(new_dim, dict):
                report.error(f"{paper_type} 类卷必须给出 expected_new_dimension 参考范例")
            else:
                for key in ("category", "dimension_id", "dimension_name"):
                    if not new_dim.get(key):
                        report.error(f"expected_new_dimension 缺少 {key}")
                dim_id = str(new_dim.get("dimension_id", ""))
                if not dim_id.startswith("dim:candidate_"):
                    report.error(f"expected_new_dimension.dimension_id 必须为候选维度：{dim_id!r}")
                reference = new_dim.get("article_73_reference")
                if not isinstance(reference, dict):
                    report.error("expected_new_dimension 缺少 article_73_reference（宪法第73条要素参考答案）")
                else:
                    for key in ARTICLE_73_REFERENCE_KEYS:
                        if not reference.get(key):
                            report.error(f"article_73_reference 缺少第73条要素：{key}")
                scores = new_dim.get("article_76_reference_scores")
                if not isinstance(scores, dict):
                    report.error("expected_new_dimension 缺少 article_76_reference_scores（第76条6项自评分）")
                else:
                    missing = [k for k in ARTICLE_76_SCORE_KEYS if k not in scores]
                    if missing:
                        report.error(f"article_76_reference_scores 缺少评分项：{missing}")
                    bad_range = [k for k, v in scores.items() if not isinstance(v, (int, float)) or not 0.0 <= v <= 1.0]
                    if bad_range:
                        report.error(f"article_76_reference_scores 取值必须落在 0.0~1.0：{bad_range}")
            if not bad_interactions:
                report.error(
                    f"{paper_type} 类卷必须至少设计一次「不合时宜的时空发声打扰」"
                    "（user_response 为 IGNORED 或 IRRITATED），否则照妖镜失效"
                )
            if isinstance(demands, dict) and demands.get("must_lower_restraint") is not True:
                report.error(f"{paper_type} 类卷 ai_self_review_demands.must_lower_restraint 必须为 true")


def validate_paper(path: Path) -> PaperReport:
    """校验单份考卷，返回结构化报告。"""
    report = PaperReport(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"JSON 解析失败（输出必须合法无截断）：{exc}")
        return report
    if not isinstance(data, dict):
        report.error("考卷根节点必须是 JSON 对象")
        return report
    report.data = data

    _check_protocol_model(data, report)
    _check_identity(data, report)
    _check_persona(data, report)
    _check_stream(data, report)
    interactions = _check_interactions(data, report)
    _check_ground_truth(data, interactions, report)
    return report


def validate_batch(paths: List[Path]) -> Tuple[List[PaperReport], List[str]]:
    """校验整批考卷并额外检查批次级约束（唯一性、题型覆盖、陷阱卷占比）。"""
    reports = [validate_paper(p) for p in paths]
    batch_errors: List[str] = []

    ids = [r.data.get("question_id") for r in reports if r.data]
    duplicated = {q for q in ids if ids.count(q) > 1}
    if duplicated:
        batch_errors.append(f"question_id 重复：{sorted(duplicated)}")

    types = [r.data.get("paper_type") for r in reports if r.data]
    declared = [t for t in types if t in PAPER_TYPE_DIFFICULTY]
    if declared:
        missing = sorted(set(PAPER_TYPE_DIFFICULTY) - set(declared))
        if missing:
            batch_errors.append(f"题型覆盖不全，缺少：{missing}")
        trap_count = declared.count("D")
        ratio = trap_count / len(declared)
        if trap_count == 0:
            batch_errors.append("批次中缺少 D 类防虚妄衍生陷阱卷（法定占比约 10%）")
        elif not 0.05 <= ratio <= 0.25:
            batch_errors.append(f"D 类陷阱卷占比 {ratio:.0%} 偏离法定约 10% 的区间")
    return reports, batch_errors


def main() -> int:
    parser = argparse.ArgumentParser(description="认知实战大考卷契约校验器")
    parser.add_argument("papers", nargs="*", help="考卷 JSON 路径，缺省扫描 papers 目录")
    parser.add_argument("--strict", action="store_true", help="存在 warning 时也判定失败")
    args = parser.parse_args()

    paths = [Path(p) for p in args.papers] if args.papers else sorted(PAPERS_DIR.glob("*.json"))
    paths = [p for p in paths if p.name != "batch_manifest_20260917.json"]
    if not paths:
        print(f"[FAIL] 未在 {PAPERS_DIR} 找到任何考卷")
        return 1

    reports, batch_errors = validate_batch(paths)
    failed = 0
    for report in reports:
        status = "PASS" if report.ok else "FAIL"
        if not report.ok or (args.strict and report.warnings):
            failed += 1
            status = "FAIL"
        print(f"[{status}] {report.path.name}")
        for message in report.errors:
            print(f"    ERROR: {message}")
        for message in report.warnings:
            print(f"    WARN : {message}")
    for message in batch_errors:
        failed += 1
        print(f"[FAIL] 批次级约束：{message}")

    trap = sum(1 for r in reports if r.data.get("paper_type") == "D")
    typed = sum(1 for r in reports if r.data.get("paper_type") in PAPER_TYPE_DIFFICULTY)
    print(
        f"\n合计 {len(reports)} 卷 | 失败 {failed} 项 | "
        f"题型标注 {typed} 卷 | 陷阱卷 {trap} 卷"
        + (f"（占比 {trap / typed:.0%}）" if typed else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
