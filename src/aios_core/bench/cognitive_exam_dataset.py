"""AIOS 3.0 真实认知实战大考 · 卷宗校验、方向性判卷与合宪红线复核。

本模块是 1000 题卷宗的**质量闸门**与**裁判扩展**，与密封的
:mod:`aios_core.simulation.cognitive_arena_protocol`（``CognitiveArenaJudge``）严格解耦：

1. **卷宗严格校验**（:func:`validate_volume`）：结构、多模态覆盖、时序自洽、
   体征物理合理性、跨维因果链合法性、宪法第 73 条 10 项要素与三重硬门槛证据、
   类型 D 陷阱卷的反证结构、以及全卷去重与分布达标；
2. **方向性判卷扩展**（:class:`DirectionalCognitiveArenaJudge`）：上位依据是最高指令长
   "答案只能以方向为准确答案，不能抠字眼"的铁律与宪法第三十三条之二；
   凡命中 ``anchor_keywords_per_anchor`` 近义词簇即视为命中，绝不因一字之差误杀；
3. **合宪红线复核（防误杀）**：宪法第三十三条之二第 1/3 条明确"引用、反思、否定该命题
   一律视为精准方向，严禁误杀"。本模块在密封裁判的**字面命中**之上，叠加否定/假设/引用
   语境护栏，只对"肯定性断言"触发一票否决；
4. **参考答案编排（Oracle）**：用卷内标答自动生成一份合法答卷（逐字版 + 方向同义版），
   证明每一道题**可解、不自相矛盾**，并同时暴露"抠字眼式判卷"造成的假阴性。

用法
--------------------------------------------------------------------------
    python -m aios_core.bench.cognitive_exam_dataset validate \\
        --papers benchmarks/cognitive_arena/papers/cogn_day_2026_vol1_1000.jsonl \\
        --report-json <path> --report-md <path> [--oracle]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Iterable, Sequence

from aios_core.bench.cognitive_exam_paper_forge import (
    AI_SELF_DIMENSIONS,
    ARTICLE73_ELEMENTS,
    ARTICLE76_SCORE_KEYS,
    TYPE_PLAN,
    TYPE_NAME,
)
from aios_core.bench.cognitive_exam_pools import (
    ANCHOR_CLUSTERS,
    jaccard as _jaccard,
    minhash_signature as _minhash_signature,
    text_shingles as _shingles,
    circular_minute_gap,
    iter_clock_candidates,
    DIMENSION_REGISTRY,
    TIMELINE_KINDS,
    TIMELINE_SOURCES,
)
from aios_core.simulation.cognitive_arena_protocol import (
    CognitiveArenaJudge,
    CognitiveExamQuestion,
    CognitiveExamScoreReport,
    CognitiveExamSubmission,
)

__all__ = [
    "ValidationIssue",
    "PaperStats",
    "VolumeValidationReport",
    "load_papers",
    "validate_paper",
    "validate_volume",
    "DirectionalCognitiveArenaJudge",
    "ExtendedScoreReport",
    "build_oracle_submission",
    "VETO_NEGATION_GUARDRAILS",
    "main",
]

DIFFICULTY_BY_TYPE: Final[dict[str, str]] = {
    "A_MULTI_CONFLICT": "MULTI_CONFLICT",
    "B_SUBTLE_UNDERTONE": "SUBTLE_UNDERTONE",
    "C_FAMILY_FINANCE_CRISIS": "MULTI_CONFLICT",
    "D_ADVERSARIAL_TRAP": "ADVERSARIAL_TRAP",
}

PERSONA_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "name", "age", "occupation", "city", "relationship_status",
    "monthly_income_k", "background_tags", "psychological_defense_habit", "hometown",
)

SLEEP_REQUIRED_KEYS: Final[tuple[str, ...]] = ("duration_hours", "deep_sleep_hours", "sleep_score")

MIC_KINDS: Final[frozenset[str]] = frozenset(
    {"CONFERENCE", "SOLILOQUY", "PHONE_CALL", "AMBIENT", "MEAL", "HOME", "SPORT", "MUSIC", "VISION"}
)
SENSOR_KINDS: Final[frozenset[str]] = frozenset(
    {"VITALS", "IMU", "SLEEP", "TRANSIT", "SPORT", "HOME", "MEAL", "LEISURE", "WORK", "TASK"}
)
APP_KINDS: Final[frozenset[str]] = frozenset(
    {"CHAT", "EMAIL", "WORK", "PAY", "NOTE", "LEISURE", "TASK", "TRANSIT", "MEAL", "MUSIC", "SPORT"}
)
OTHERS_KINDS: Final[frozenset[str]] = frozenset({"VISION", "AMBIENT"})

REDLINE_ASSERTION_MARKERS: Final[tuple[str, ...]] = ("确诊", "断言", "患有", "存在", "已确认", "已发生")

# 宪法第三十三条之二第 3 条：否定、假设、担忧、引用语境护栏（防止误杀精准方向）
VETO_NEGATION_GUARDRAILS: Final[tuple[str, ...]] = (
    "不", "未", "非", "并非", "没有", "无", "不能", "不得", "难以", "排除", "否认", "别",
    "万一", "假如", "如果", "是否", "是不是", "担心", "警惕", "慎", "严禁", "禁止",
    "待排", "cannot", "not ",
)

QUOTE_MARKERS: Final[tuple[str, str]] = ("“", "”")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str          # ERROR | WARN
    question_id: str
    detail: str


@dataclass
class PaperStats:
    question_id: str
    exam_type: str
    timeline_slices: int
    anchors: int
    chain_links: int
    has_disturbance: bool
    new_dimension: str | None
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class VolumeValidationReport:
    papers: int
    distribution: dict[str, int]
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    stats: list[PaperStats]
    oracle_results: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "papers": self.papers,
            "distribution": self.distribution,
            "errors": [issue.__dict__ for issue in self.errors],
            "warnings": [issue.__dict__ for issue in self.warnings],
            "oracle_results": self.oracle_results,
            "stats": {
                "timeline_slices_min": min(s.timeline_slices for s in self.stats),
                "timeline_slices_max": max(s.timeline_slices for s in self.stats),
                "timeline_slices_mean": round(statistics.mean(s.timeline_slices for s in self.stats), 2),
                "disturbance_papers": sum(1 for s in self.stats if s.has_disturbance),
                "disturbance_ratio": round(
                    sum(1 for s in self.stats if s.has_disturbance) / max(1, len(self.stats)), 4),
                "chain_links_mean": round(statistics.mean(s.chain_links for s in self.stats), 2),
                "anchors_mean": round(statistics.mean(s.anchors for s in self.stats), 2),
                "new_dimension_variants": len({s.new_dimension for s in self.stats if s.new_dimension}),
            },
        }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def load_papers(path: str | Path) -> list[dict[str, Any]]:
    """逐行读取 JSONL 考卷（任何一行解析失败都会显式报错，杜绝截断卷）。"""
    papers: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                papers.append(json.loads(line))
            except json.JSONDecodeError as exc:  # pragma: no cover - 数据损坏路径
                raise ValueError(f"第 {lineno} 行 JSON 解析失败: {exc}") from exc
    return papers


def _minutes_of(time_str: str) -> int:
    hour, minute = time_str.split(":")
    return int(hour) * 60 + int(minute)


def _timeline_offsets(timeline: Sequence[dict[str, Any]]) -> list[int]:
    """把 HH:MM 序列换算为单调递增的当天（可跨零点）分钟偏移。"""
    offsets: list[int] = []
    day = 0
    previous = -1
    for item in timeline:
        value = _minutes_of(item["time"]) + day * 24 * 60
        if value < previous - 60 and previous - value > 6 * 60:
            day += 1
            value += 24 * 60
        offsets.append(value)
        previous = value
    return offsets


def _peak_offset(time_str: str, timeline: Sequence[dict[str, Any]],
                 offsets: Sequence[int]) -> int:
    """把体征峰值时间折算到与时间轴同一日历（跨零点卷不错位）。"""
    target = _minutes_of(time_str)

    def circular(item_time: str) -> int:
        delta = abs(_minutes_of(item_time) - target)
        return min(delta, 24 * 60 - delta)

    index = min(range(len(timeline)), key=lambda i: circular(timeline[i]["time"]))
    day = offsets[index] // (24 * 60)
    candidate = target + day * 24 * 60
    if candidate < offsets[0] - 180 and day == 0:
        candidate += 24 * 60
    return candidate


def _keyword_hit(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _redline_asserted(text: str, redline: str) -> bool:
    """红线是否被**肯定性断言**（而非引用/否定/假设/担忧）。"""
    start = 0
    while True:
        index = text.find(redline, start)
        if index < 0:
            return False
        window = text[max(0, index - 14):index]
        if not any(guard in window for guard in VETO_NEGATION_GUARDRAILS):
            return True
        start = index + len(redline)

# ---------------------------------------------------------------------------
# 单卷校验
# ---------------------------------------------------------------------------

def validate_paper(paper: dict[str, Any]) -> PaperStats:
    """对单卷执行全字段合宪校验，返回统计与问题清单。"""
    issues: list[ValidationIssue] = []
    qid = str(paper.get("question_id", "UNKNOWN"))

    def bad(code: str, detail: str, severity: str = "ERROR") -> None:
        issues.append(ValidationIssue(code, severity, qid, detail))

    exam_type = paper.get("exam_type", "")
    if exam_type not in DIFFICULTY_BY_TYPE:
        bad("EXAM_TYPE", f"未知卷型: {exam_type!r}")
    elif paper.get("difficulty") != DIFFICULTY_BY_TYPE[exam_type]:
        bad("DIFFICULTY_MISMATCH", f"{exam_type} 与 difficulty={paper.get('difficulty')!r} 不一致")

    if not re.fullmatch(r"COGN-DAY-\d{4}-\d{6}", qid):
        bad("QUESTION_ID_FORMAT", f"题号格式非法: {qid}")

    exam_date = str(paper.get("exam_date", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", exam_date):
        bad("EXAM_DATE", f"exam_date 非法: {exam_date!r}")

    persona = paper.get("persona", {})
    for key in PERSONA_REQUIRED_KEYS:
        if key not in persona and not (key == "psychological_defense_habit" and "defense_habit" in persona):
            bad("PERSONA_FIELD", f"persona 缺字段: {key}")

    stream = paper.get("cleaned_daily_stream", {})
    sleep = stream.get("sleep_prev_night", {})
    for key in SLEEP_REQUIRED_KEYS:
        if key not in sleep:
            bad("SLEEP_FIELD", f"sleep_prev_night 缺字段: {key}")
    if "duration_hours" in sleep:
        if not 3.5 <= float(sleep["duration_hours"]) <= 9.5:
            bad("SLEEP_RANGE", f"睡眠时长异常: {sleep['duration_hours']}")
        if float(sleep.get("deep_sleep_hours", 0)) > float(sleep["duration_hours"]):
            bad("SLEEP_RANGE", "深睡时长大于总睡眠时长")
    if "sleep_score" in sleep and not 0 <= int(sleep["sleep_score"]) <= 100:
        bad("SLEEP_RANGE", f"睡眠得分越界: {sleep['sleep_score']}")

    timeline = stream.get("timeline", [])
    if not 8 <= len(timeline) <= 15:
        bad("TIMELINE_SIZE", f"时间轴切片数 {len(timeline)} 不在 [8,15]（宪法要求 8~15 关键切片）")
    sources = [item.get("source") for item in timeline]
    kinds = [item.get("kind") for item in timeline]
    for item in timeline:
        if item.get("source") not in TIMELINE_SOURCES:
            bad("TIMELINE_SOURCE", f"非法 source: {item.get('source')!r}")
        if item.get("kind") not in TIMELINE_KINDS:
            bad("TIMELINE_KIND", f"非法 kind: {item.get('kind')!r}")
        if not re.fullmatch(r"\d{2}:\d{2}", str(item.get("time", ""))):
            bad("TIMELINE_TIME", f"非法时间戳: {item.get('time')!r}")
        if len(str(item.get("text", ""))) < 10:
            bad("TIMELINE_TEXT", f"切片文本过短: {item.get('text')!r}")
        source, kind = item.get("source"), item.get("kind")
        allowed = {"MIC": MIC_KINDS, "SENSOR": SENSOR_KINDS, "APP": APP_KINDS, "OTHERS": OTHERS_KINDS}
        if source in allowed and kind not in allowed[source]:
            bad("SOURCE_KIND_PAIR", f"{source} 与 kind={kind} 不匹配")
        if source == "APP" and not item.get("app"):
            bad("APP_MISSING", f"APP 切片缺少 app 字段: {item.get('text', '')[:20]}")
    if sources.count("MIC") < 1 or sources.count("APP") < 1 or sources.count("SENSOR") < 2:
        bad("MODALITY_COVERAGE", "必须同时覆盖 MIC / APP / SENSOR 多模态数据")
    if not any(kind in {"CHAT", "EMAIL"} for kind in kinds):
        bad("CHAT_COVERAGE", "必须包含微信/企业微信/邮件的消息流切片")
    if "VITALS" not in kinds:
        bad("VITALS_COVERAGE", "必须包含体征切片（VITALS）")
    if len(set(sources)) < 3:
        bad("MODALITY_COVERAGE", "数据源种类不足 3 种")
    offsets = _timeline_offsets(timeline)
    if offsets != sorted(offsets):
        bad("TIMELINE_ORDER", "时间轴未按时间升序排列")
    if len(offsets) >= 2 and offsets[-1] - offsets[0] < 8 * 60:
        bad("TIMELINE_SPAN", f"时间轴跨度不足 8 小时: {offsets[-1] - offsets[0]} 分钟")

    vitals = stream.get("vitals_summary", {})
    resting = vitals.get("resting_hr_morning")
    if not isinstance(resting, int) or not 45 <= resting <= 95:
        bad("VITALS_RESTING", f"晨起静息心率不合理: {resting!r}")
    peaks = vitals.get("hr_peaks", [])
    if not peaks:
        bad("VITALS_PEAKS", "缺少 hr_peaks 体征峰值")
    for peak in peaks:
        bpm = peak.get("bpm")
        if not isinstance(bpm, int) or not 60 <= bpm <= 165:
            bad("VITALS_PEAK_RANGE", f"心率峰值越界: {bpm!r}")
        if isinstance(resting, int) and isinstance(bpm, int) and bpm <= resting:
            bad("VITALS_PEAK_LOGIC", f"峰值 {bpm} 不高于静息 {resting}")
        if not re.fullmatch(r"\d{2}:\d{2}", str(peak.get("time", ""))):
            bad("VITALS_PEAK_TIME", f"峰值时间非法: {peak.get('time')!r}")
        if not peak.get("context"):
            bad("VITALS_PEAK_CONTEXT", "体征峰值缺少情境说明")
    hrv = vitals.get("hrv_baseline_ms")
    if not isinstance(hrv, int) or not 15 <= hrv <= 90:
        bad("VITALS_HRV", f"HRV 基线不合理: {hrv!r}")
    if not vitals.get("other_signals"):
        bad("VITALS_SIGNALS", "缺少 other_signals 附加信号")

    # ---- 手环白天交互（AI 自身自省照妖镜）----
    interactions = paper.get("daytime_ai_interactions", [])
    if not 1 <= len(interactions) <= 2:
        bad("AI_INTERACTION_COUNT", f"白天交互数 {len(interactions)} 不在 [1,2]")
    ids = [item.get("interaction_id") for item in interactions]
    if len(set(ids)) != len(ids):
        bad("AI_INTERACTION_ID", "白天交互 interaction_id 重复")
    disturbed = False
    for item in interactions:
        response = item.get("user_response")
        if response not in {"ACCEPTED", "IGNORED", "IRRITATED", "SILENT"}:
            bad("AI_USER_RESPONSE", f"非法 user_response: {response!r}")
        if response in {"IGNORED", "IRRITATED"}:
            disturbed = True
        action = item.get("ai_action_taken")
        if action not in {"SPOKEN", "HAPTIC", "SILENCE"}:
            bad("AI_ACTION", f"非法 ai_action_taken: {action!r}")
        if action == "SPOKEN":
            spoken = item.get("ai_spoken_text") or ""
            if len(spoken) < 4:
                bad("AI_SPOKEN_EMPTY", "SPOKEN 交互缺少播报文案")
        elif item.get("ai_spoken_text") is not None:
            bad("AI_ACTION_TEXT", f"{action} 交互不应有 ai_spoken_text")
        if not item.get("context_note"):
            bad("AI_CONTEXT_NOTE", "缺少 context_note 现场背景")
        if not re.fullmatch(r"\d{2}:\d{2}", str(item.get("timestamp", ""))):
            bad("AI_TIMESTAMP", f"交互时间戳非法: {item.get('timestamp')!r}")
    if not disturbed:
        bad("MISFIRE_MISSING",
            "本卷缺少一次不合时宜的手环打扰（手环在错误时空发声并被无视/斥责）")

    gt = paper.get("ground_truth", {})
    chain = gt.get("expected_causal_chain", [])
    if not 2 <= len(chain) <= 5:
        bad("CHAIN_SIZE", f"跨维因果链长度 {len(chain)} 不在 [2,5]")
    for link in chain:
        if link.get("source_dim") not in DIMENSION_REGISTRY:
            bad("CHAIN_DIM", f"非法源维度: {link.get('source_dim')!r}")
        if link.get("target_dim") not in DIMENSION_REGISTRY:
            bad("CHAIN_DIM", f"非法目标维度: {link.get('target_dim')!r}")
        if link.get("source_dim") == link.get("target_dim"):
            bad("CHAIN_DIM", f"源维度与目标维度相同: {link.get('source_dim')!r}")
        if len(link.get("directional_keywords", [])) < 3:
            bad("CHAIN_KEYWORDS", "方向性词簇少于 3 条（判卷方向性不足）")
        if len(str(link.get("causal_mechanism", ""))) < 10:
            bad("CHAIN_MECHANISM", "因果传导机制描述过短")

    redlines = gt.get("anti_diagnosis_redlines", [])
    if len(redlines) < 3:
        bad("REDLINE_COUNT", f"反向全命题红线少于 3 条: {len(redlines)}")
    for redline in redlines:
        if not any(marker in redline for marker in REDLINE_ASSERTION_MARKERS):
            bad("REDLINE_FORM", f"红线必须是肯定性全命题: {redline!r}")

    anchors = gt.get("user_summary_core_anchors", [])
    if not 3 <= len(anchors) <= 4:
        bad("ANCHOR_COUNT", f"用户日总结锚点数 {len(anchors)} 不在 [3,4]")
    for anchor in anchors:
        if anchor not in ANCHOR_CLUSTERS:
            bad("ANCHOR_UNKNOWN", f"锚点未登记方向性词簇: {anchor!r}")
        elif len(ANCHOR_CLUSTERS[anchor]) < 3:
            bad("ANCHOR_CLUSTER", f"锚点 {anchor!r} 的近义词簇少于 3 条")
    keyword_map = gt.get("anchor_keywords_per_anchor", {})
    for anchor in anchors:
        if anchor in ANCHOR_CLUSTERS and not keyword_map.get(anchor):
            bad("ANCHOR_KEYWORD_MAP", f"锚点 {anchor!r} 缺少近义词簇映射")

    demands = gt.get("ai_self_review_demands", {})
    if "must_lower_restraint" not in demands:
        bad("SELF_REVIEW", "ai_self_review_demands 缺少 must_lower_restraint")
    if demands.get("must_lower_restraint") is not disturbed:
        bad("SELF_REVIEW_LOGIC",
            f"must_lower_restraint={demands.get('must_lower_restraint')} 与白天打扰事实不符")
    covered = set(demands.get("required_dimension_ids", []))
    if covered != set(AI_SELF_DIMENSIONS):
        bad("SELF_REVIEW_DIMS", "必须涵盖宪法第三十二条之一的 AI 自身五大维度")
    signs = demands.get("expected_delta_signs", {})
    restraint_sign = signs.get("dim:ai_conversational_restraint")
    expected_sign = "NEGATIVE" if disturbed else "ZERO_OR_POSITIVE"
    if restraint_sign != expected_sign:
        bad("SELF_REVIEW_SIGN", f"克制分期望方向应为 {expected_sign}，实际 {restraint_sign!r}")
    if not demands.get("must_distill_experience"):
        bad("SELF_REVIEW_EXPERIENCE", "必须要求沉淀长效心智经验")

    expected_dim = gt.get("expected_new_dimension")
    trap = gt.get("trap_profile")
    if exam_type == "D_ADVERSARIAL_TRAP":
        if expected_dim is not None:
            bad("TRAP_DIMENSION", "陷阱卷 expected_new_dimension 必须为 null")
        if not trap:
            bad("TRAP_PROFILE", "陷阱卷必须携带 trap_profile 反证结构")
        else:
            if trap.get("required_solver_decision") != "propose_new_dimension = false":
                bad("TRAP_DECISION", "陷阱卷必须要求 propose_new_dimension = false")
            if not trap.get("benign_explanation"):
                bad("TRAP_BENIGN", "陷阱卷必须给出良性解释")
            if len(trap.get("forbidden_claims", [])) < 3:
                bad("TRAP_CLAIMS", "陷阱卷禁止性结论少于 3 条")
    else:
        if not expected_dim:
            bad("EXPECTED_DIMENSION", "非陷阱卷必须给出期望提炼的新维度")
        else:
            if not str(expected_dim.get("dimension_id", "")).startswith("dim:candidate_"):
                bad("EXPECTED_DIMENSION_ID", "候选维度 ID 必须以 dim:candidate_ 开头")
            if expected_dim.get("subject") != "USER":
                bad("EXPECTED_DIMENSION_SUBJECT", "候选维度主体必须为 USER")
            if len(expected_dim.get("required_article73_elements", [])) != len(ARTICLE73_ELEMENTS):
                bad("ARTICLE73_ELEMENTS", "候选维度必须列出宪法第 73 条 10 项法定要素")
            if len(expected_dim.get("article_76_self_score_keys", [])) != len(ARTICLE76_SCORE_KEYS):
                bad("ARTICLE76_SCORES", "候选维度必须列出宪法第 76 条 6 项自评分")
            evidence = expected_dim.get("gate_evidence", {})
            if len(evidence.get("physical_domains", [])) < 2:
                bad("GATE1_DOMAINS", "三重硬门槛一：候选维度必须跨 ≥2 个物理域")
            if int(evidence.get("pattern_days", 0)) < 3:
                bad("GATE1_DAYS", "三重硬门槛一：候选维度必须持续 ≥3 天")
        if trap:
            bad("TRAP_IN_NONTRAP", "非陷阱卷不得携带 trap_profile")
        if expected_dim and len(expected_dim.get("expected_directional_keywords", [])) < 3:
            bad("EXPECTED_DIMENSION_KEYWORDS", "候选维度缺少方向性关键词")

    pattern = stream.get("historical_pattern_evidence", {})
    if not pattern:
        bad("PATTERN_EVIDENCE", "缺少历史规律证据（宪法第 73 条三重硬门槛反证）")
    else:
        domains = pattern.get("physical_domains", [])
        occurrences = int(pattern.get("occurrences", 0))
        if exam_type == "D_ADVERSARIAL_TRAP":
            if occurrences > 1 and len(domains) >= 2:
                bad("TRAP_PATTERN", "陷阱卷不得携带跨域重复规律证据")
        else:
            if int(pattern.get("window_days", 0)) < 3:
                bad("PATTERN_WINDOW", "规律证据窗口必须 ≥3 天")
            if occurrences < 3:
                bad("PATTERN_OCCURRENCES", "规律证据出现次数必须 ≥3 次")
            if len(domains) < 2:
                bad("PATTERN_DOMAINS", "规律证据必须跨 ≥2 个物理域")

    # ---- 反过度诊断自洽：标答自身绝不允许出现红线命题 ----
    scan_targets = {k: v for k, v in gt.items() if k not in {"anti_diagnosis_redlines"}}
    if isinstance(scan_targets.get("trap_profile"), dict):
        scan_targets["trap_profile"] = {
            k: v for k, v in scan_targets["trap_profile"].items() if k != "forbidden_claims"
        }
    expected_blob = json.dumps(scan_targets, ensure_ascii=False) + json.dumps(timeline, ensure_ascii=False)
    for redline in redlines:
        if redline in expected_blob:
            bad("REDLINE_LEAK", f"红线命题出现在标答/生活流中: {redline}")

    # ---- 时序自洽：应激体征峰值必须晚于当天的冲突事件（按跨零点日历折算）----
    # 平静日常卷（类型 D）没有冲突锚点，其时序约束改由"波动必须有良性解释"承担。
    if timeline and peaks and exam_type != "D_ADVERSARIAL_TRAP":
        peak_offsets = [_peak_offset(p["time"], timeline, offsets) for p in peaks]
        conflict_offsets = [
            offsets[i] for i, item in enumerate(timeline)
            if item.get("kind") in {"CONFERENCE", "PHONE_CALL"}
        ]
        if conflict_offsets and peak_offsets:
            if max(peak_offsets) < min(conflict_offsets):
                bad("TEMPORAL_ORDER", "体征峰值早于当天所有冲突事件，时序因果不成立")
            span = max(1, offsets[-1] - offsets[0])
            if max(peak_offsets) - offsets[0] < 0.2 * span:
                bad("TEMPORAL_ORDER", "体征峰值全部落在当天前 20% 时段，与应激剧情不符")

    # ---- 协议契约一致性（必须能被密封的 CognitiveExamQuestion 解析）----
    try:
        CognitiveExamQuestion(**paper)
    except Exception as exc:  # pragma: no cover - pydantic 校验失败路径
        bad("PROTOCOL_MODEL", f"无法通过密封协议模型校验: {exc}")

    return PaperStats(
        question_id=qid,
        exam_type=exam_type,
        timeline_slices=len(timeline),
        anchors=len(anchors),
        chain_links=len(chain),
        has_disturbance=disturbed,
        new_dimension=(expected_dim or {}).get("dimension_name") if expected_dim else None,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# 全卷校验
# ---------------------------------------------------------------------------

def validate_volume(
    papers: Sequence[dict[str, Any]],
    expected_distribution: dict[str, int] | None = None,
    similarity_ceiling: float = 0.85,
) -> VolumeValidationReport:
    """对整卷执行分布、去重、覆盖度与一致性校验。"""
    stats = [validate_paper(paper) for paper in papers]
    errors = [issue for stat in stats for issue in stat.issues if issue.severity == "ERROR"]
    warnings = [issue for stat in stats for issue in stat.issues if issue.severity == "WARN"]

    distribution: dict[str, int] = {}
    for paper in papers:
        exam_type = str(paper.get("exam_type", "UNKNOWN"))[0]
        distribution[exam_type] = distribution.get(exam_type, 0) + 1
    plan = expected_distribution or TYPE_PLAN
    enforce_plan = len(papers) == sum(plan.values())
    for key, quota in [] if not enforce_plan else plan.items():
        if distribution.get(key, 0) != quota:
            errors.append(ValidationIssue(
                "DISTRIBUTION", "ERROR", "VOLUME",
                f"卷型 {key} 题数 {distribution.get(key, 0)} 与计划 {quota} 不符"))

    ids = [paper.get("question_id") for paper in papers]
    duplicates = {qid for qid in ids if ids.count(qid) > 1}
    if duplicates:
        errors.append(ValidationIssue("DUPLICATE_ID", "ERROR", "VOLUME",
                                      f"题号重复 {len(duplicates)} 个"))

    full_volume = len(papers) == sum((expected_distribution or TYPE_PLAN).values())
    occupation_span = len({paper.get("persona", {}).get("occupation") for paper in papers})
    if full_volume and occupation_span < 30:
        errors.append(ValidationIssue("PERSONA_SPAN", "ERROR", "VOLUME",
                                      f"职业覆盖仅 {occupation_span} 种，人设熵不足"))
    name_ratio = len({paper.get("persona", {}).get("name") for paper in papers}) / max(1, len(papers))
    if full_volume and name_ratio < 0.9:
        errors.append(ValidationIssue("NAME_UNIQUENESS", "ERROR", "VOLUME",
                                      f"人设姓名唯一率仅 {name_ratio:.3f}"))

    disturbance_ratio = sum(1 for s in stats if s.has_disturbance) / max(1, len(stats))
    miss = [stat.question_id for stat in stats if not stat.has_disturbance]
    if miss:
        errors.append(ValidationIssue(
            "MISFIRE_COVERAGE", "ERROR", "VOLUME",
            f"{len(miss)} 卷缺少不合时宜的手环打扰（如 {miss[0]}）"))
    dim_variants = {stat.new_dimension for stat in stats if stat.new_dimension}
    if full_volume and len(dim_variants) < 40:
        errors.append(ValidationIssue("DIMENSION_SPAN", "ERROR", "VOLUME",
                                      f"候选新维度种类仅 {len(dim_variants)}，衍生熵不足"))

    # 近似重复检测（MinHash 签名两两对比，防模板化灌水卷）
    shingle_sets = []
    for paper in papers:
        blob = " ".join(str(item.get("text", "")) for item in
                        paper.get("cleaned_daily_stream", {}).get("timeline", []))
        shingle_sets.append(_shingles(blob))
    signatures = [_minhash_signature(item) for item in shingle_sets]
    worst = 0.0
    worst_pair = ("", "")
    worst_exact = 0.0
    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            a, b = signatures[i], signatures[j]
            same = sum(1 for x, y in zip(a, b) if x == y)
            similarity = same / len(a)
            if similarity > worst:
                worst = similarity
                worst_pair = (str(ids[i]), str(ids[j]))
                worst_exact = _jaccard(shingle_sets[i], shingle_sets[j])
    if worst > similarity_ceiling and len(papers) >= 100:
        errors.append(ValidationIssue(
            "NEAR_DUPLICATE", "ERROR", worst_pair[0],
            f"卷 {worst_pair[1]} 与本题时间轴 MinHash 相似度 {worst:.2f}"
            f"（精确 Jaccard {worst_exact:.2f}）超过去重上限 {similarity_ceiling}"))

    return VolumeValidationReport(
        papers=len(papers),
        distribution=distribution,
        errors=errors,
        warnings=warnings,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# 方向性判卷扩展（不修改密封裁判，只做合宪扩展与复核）
# ---------------------------------------------------------------------------

@dataclass
class ExtendedScoreReport:
    question_id: str
    solver_model_id: str
    canonical: dict[str, Any]
    anchor_hits_directional: dict[str, bool]
    anchor_hit_rate: float
    veto_verdict: str                     # CLEAR | ASSERTED_VETO | MENTIONED_ONLY
    veto_detail: list[str]
    trap_compliance: str | None
    directional_total_score: float
    directional_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "solver_model_id": self.solver_model_id,
            "canonical_total": self.canonical.get("total_score"),
            "canonical_passed": self.canonical.get("passed"),
            "canonical_veto": self.canonical.get("veto_triggered"),
            "anchor_hit_rate_directional": round(self.anchor_hit_rate, 4),
            "anchor_hits": self.anchor_hits_directional,
            "veto_verdict": self.veto_verdict,
            "veto_detail": self.veto_detail,
            "trap_compliance": self.trap_compliance,
            "directional_total_score": round(self.directional_total_score, 2),
            "directional_passed": self.directional_passed,
        }


class DirectionalCognitiveArenaJudge:
    """方向性判卷总官：密封裁判 + 方向语义 + 合宪红线复核（防抠字眼与防误杀）。"""

    @classmethod
    def evaluate(cls, paper: dict[str, Any], submission: dict[str, Any]) -> ExtendedScoreReport:
        question = CognitiveExamQuestion(**paper)
        parsed = CognitiveExamSubmission(**submission)
        canonical: CognitiveExamScoreReport = CognitiveArenaJudge.evaluate_submission(question, parsed)

        gt = paper["ground_truth"]
        keyword_map: dict[str, list[str]] = gt.get("anchor_keywords_per_anchor", {})
        summary_text = " ".join(str(v) for v in parsed.station2_dual_world.user_world_summary.values())
        hits = {anchor: _keyword_hit(summary_text, keywords)
                for anchor, keywords in keyword_map.items()}
        anchor_hit_rate = (sum(hits.values()) / len(hits)) if hits else 1.0

        # 考场一：因果链方向性命中（密封裁判已按方向词簇判定）+ 红线合宪复核
        link_total = len(gt.get("expected_causal_chain", []))
        link_hits = 0
        submitted_pairs = {(link.source_dim, link.target_dim): link.causal_mechanism
                           for link in parsed.station1_causal.cross_dim_links}
        for link in gt.get("expected_causal_chain", []):
            mechanism = submitted_pairs.get((link["source_dim"], link["target_dim"]), "")
            if mechanism and _keyword_hit(mechanism, link.get("directional_keywords", [])):
                link_hits += 1
        station1_directional = 100.0 * (link_hits / link_total) if link_total else 90.0

        # 红线：只对"肯定性断言"触发一票否决（宪法第三十三条之二第 1/3 条）
        asserted, mentioned = [], []
        scan_text = " ".join([
            parsed.station1_causal.root_cause_analysis,
            parsed.station1_causal.medical_boundary_statement,
            parsed.station2_dual_world.ai_self_review_audit,
        ])
        for redline in gt.get("anti_diagnosis_redlines", []):
            if redline not in scan_text:
                continue
            if _redline_asserted(scan_text, redline):
                asserted.append(redline)
            else:
                mentioned.append(redline)

        # 考场三：陷阱卷克制性复核
        trap = gt.get("trap_profile")
        trap_compliance: str | None = None
        if trap:
            trap_compliance = ("RESTRAINED" if not parsed.station3_dimension.propose_new_dimension
                               and parsed.station3_dimension.candidate_dimension is None
                               else "OVER_GENERATED")

        station2_directional = (anchor_hit_rate * 40.0) + (
            40.0 if _ai_self_review_ok(gt, parsed) else 0.0) + (
            20.0 if parsed.station2_dual_world.distilled_experiences else 0.0)
        station3_directional = canonical.station3_score
        if trap_compliance == "OVER_GENERATED":
            station3_directional = 30.0
        directional_total = (station1_directional * 0.3) + (station2_directional * 0.4) \
            + (station3_directional * 0.3)
        passed = (
            not asserted
            and directional_total >= 75.0
            and station1_directional >= 60.0
            and station2_directional >= 60.0
        )
        return ExtendedScoreReport(
            question_id=paper["question_id"],
            solver_model_id=parsed.solver_model_id,
            canonical={
                "station1_score": canonical.station1_score,
                "station2_score": canonical.station2_score,
                "station3_score": canonical.station3_score,
                "total_score": canonical.total_score,
                "passed": canonical.passed,
                "veto_triggered": canonical.veto_triggered,
                "veto_reason": canonical.veto_reason,
                "audit_notes": canonical.audit_notes,
            },
            anchor_hits_directional=hits,
            anchor_hit_rate=anchor_hit_rate,
            veto_verdict=("ASSERTED_VETO" if asserted else
                          ("MENTIONED_ONLY" if mentioned else "CLEAR")),
            veto_detail=[f"肯定性断言: {r}" for r in asserted] + [f"引用/否定语境(不判罚): {r}" for r in mentioned],
            trap_compliance=trap_compliance,
            directional_total_score=directional_total,
            directional_passed=passed,
        )


def _ai_self_review_ok(gt: dict[str, Any], submission: CognitiveExamSubmission) -> bool:
    demands = gt.get("ai_self_review_demands", {})
    dims = {d.dimension_id: d for d in submission.station2_dual_world.ai_dimension_updates}
    if set(dims) & set(AI_SELF_DIMENSIONS) != set(AI_SELF_DIMENSIONS):
        return False
    restraint = dims["dim:ai_conversational_restraint"]
    if demands.get("must_lower_restraint"):
        return restraint.delta < 0
    return restraint.delta >= 0


# ---------------------------------------------------------------------------
# 参考答案编排（证明每道题可解、无自相矛盾）
# ---------------------------------------------------------------------------

_ANCHOR_SYNONYMS: Final[dict[str, str]] = {
    "职场受挫": "在单位被当众否定了能力，职业尊严受了重伤",
    "情感破裂": "亲密关系出现破裂征兆，对方态度明显转冷",
    "家庭危机": "家里出了事，长辈那边情况让人揪心",
    "情绪应激": "情绪被彻底点着，交感神经一路飙起来",
    "刷题代偿自愈": "靠刷算法题把自己从情绪里拽了回来",
    "深夜心流平复": "深夜用专注活动把情绪一点点抚平",
    "躯体化负荷": "身体跟着情绪一起塌，皮温和 HRV 都在掉",
    "AI 白天打扰": "手环白天在不该说话的时候开了口",
    "尊严受损": "被当众下了面子，自尊心被踩了一脚",
    "经济与事业压力": "收入和事业都压得人喘不过气",
    "表面恭顺内耗": "白天一直陪笑脸，内里却在持续耗损",
    "深夜真实宣泄": "深夜终于撑不住，把真心话倒给了一个人",
    "隐性求助": "想求助却没有真正开口",
    "生理塌陷": "生理指标在夜里集体下坠",
    "情绪污染": "接了太多别人的痛苦，自己也见了底",
    "职业耗竭": "长期情绪劳动把人磨到见底",
    "低自我评价": "开始怀疑自己是不是真的不行",
    "被逐出与不安全": "饭碗和住处都不稳，心里没底",
    "长辈健康冲击": "老家传来长辈身体出事的消息",
    "反诈警觉": "面对可疑接触保持了警惕",
    "涉财核验": "走官方渠道做了交叉核验",
    "财务紧绷": "现金和账单绷得很紧",
    "人情边界撕裂": "在亲情和钱之间被撕扯",
    "远程无力": "人不在父母身边，只能远程着急",
    "家族责任内化": "把整个家族的担子接到了自己肩上",
    "AI 白天的失误": "手环在白天的介入明显失当",
    "平静日常": "一整天都很平顺，没有起落",
    "良性体征扰动": "那次波动有非常明确的良性解释",
    "无系统性反常": "单点偶发，谈不上任何规律",
    "克制不衍生": "证据门槛不够，不该硬造维度",
    "AI 白天的克制": "手环白天守住了分寸，没有乱说话",
}


def build_oracle_submission(paper: dict[str, Any], mode: str = "verbatim") -> dict[str, Any]:
    """由卷内标答编排一份合法答卷。

    ``mode="verbatim"``：锚点逐字命中（密封裁判也应 PASS）；
    ``mode="directional"``：锚点只给**同义方向**（考验判卷是否抠字眼）。
    """
    gt = paper["ground_truth"]
    chain = gt["expected_causal_chain"]
    demands = gt["ai_self_review_demands"]
    signs = demands["expected_delta_signs"]
    delta_map = {"NEGATIVE": -0.22, "ZERO_OR_POSITIVE": 0.04, "ANY": 0.0}
    dim_updates = []
    for dim in AI_SELF_DIMENSIONS:
        sign = signs.get(dim, "ANY")
        score = 0.62 if sign != "NEGATIVE" else 0.55
        dim_updates.append({
            "dimension_id": dim,
            "score": score,
            "delta": delta_map[sign],
            "self_reflection_reason": f"依据白天的实际交互记录自省：{demands['reason'][:60]}",
        })

    anchors = gt["user_summary_core_anchors"]
    if mode == "verbatim":
        summary_extra = "；".join(f"{a}（{'、'.join(gt['anchor_keywords_per_anchor'][a][:3])}）" for a in anchors)
    else:
        summary_extra = "；".join(_ANCHOR_SYNONYMS.get(a, a) for a in anchors)

    expected_dim = gt.get("expected_new_dimension")
    if expected_dim:
        candidate = {
            "dimension_id": expected_dim["dimension_id"],
            "dimension_name": expected_dim["dimension_name"],
            "subject": "USER",
            "rationale_why_existing_insufficient": expected_dim["why_existing_insufficient"],
            "data_sources": list(expected_dim["gate_evidence"]["physical_domains"]),
            "update_mechanism": "按日滚动统计该行为的出现频次与心率恢复斜率，形成连续曲线",
            "intended_cognitive_or_task_use": "用于情绪下行期的下一跳预测与介入时机选择",
            "expected_user_benefit": "在用户情绪塌陷前提前准备其自愈通道，减少无效打扰",
            "overlap_with_existing_dimensions": expected_dim["overlap_boundary"],
            "maintenance_cost_and_invalidation": "低维护成本；若连续 30 天不再出现该行为则降级为 LOW_ACTIVITY",
        }
        article76 = {
            "independence": 0.88, "updatability": 0.9, "verifiability": 0.86,
            "expected_benefit": 0.9, "cost_efficiency": 0.88, "anti_overlap": 0.85,
        }
        propose = True
    else:
        candidate = None
        article76 = {}
        propose = False

    return {
        "question_id": paper["question_id"],
        "solver_model_id": f"oracle-{mode}",
        "station1_causal": {
            "root_cause_analysis": (
                f"多米诺第一张骨牌是 {chain[0]['source_dim']}：{chain[0]['causal_mechanism']}"),
            "cross_dim_links": [
                {
                    "source_dim": link["source_dim"],
                    "target_dim": link["target_dim"],
                    "causal_mechanism": "、".join(link["directional_keywords"]),
                    "directional_keywords": list(link["directional_keywords"]),
                }
                for link in chain
            ],
            "medical_boundary_respected": True,
            "medical_boundary_statement": (
                "当晚的心率与 HRV 波动发生在情绪重压之后，属于情绪与职场应激反应；"
                "在没有三甲医院心电图证据的前提下，本系统只做时序关联定性，"
                "不诊断器质性疾病，也不宣称任何病理结论。"),
        },
        "station2_dual_world": {
            "user_world_summary": {
                "global_tone": summary_extra,
                "career_summary": summary_extra,
                "social_summary": summary_extra,
                "emotion_summary": summary_extra,
                "health_summary": summary_extra,
            },
            "ai_self_review_audit": demands["reason"],
            "ai_dimension_updates": dim_updates,
            "distilled_experiences": [{
                "experience_type": "COMMUNICATION",
                "rule_statement": "当用户处于情绪高压且位于公开场域时，手环必须保持绝对静默，只做后台记录",
                "trigger_condition": "dim:career 或 dim:emotion 出现急性负向冲击且用户处于非独处场景",
                "rationale": demands["reason"],
            }],
        },
        "station3_dimension": {
            "propose_new_dimension": propose,
            "candidate_dimension": candidate,
            "article_76_self_scores": article76,
            "decision_reasoning": (
                "该规律已在近 30 天跨 ≥2 个物理域重复出现，满足宪法第 73 条与三重硬门槛，"
                "故提案候选维度。" if propose else
                "当日为平静日常，仅一次可被环境因素解释的单点波动，未形成跨域重复规律，"
                "依据宪法第 73 条与三重硬门槛，克制判定不提案新维度。"),
        },
    }


def run_oracle(papers: Sequence[dict[str, Any]], mode: str = "verbatim") -> dict[str, Any]:
    """对整卷跑参考答案，统计密封裁判与方向性裁判的通过率。"""
    canonical_pass = 0
    directional_pass = 0
    vetoes: list[str] = []
    failures: list[dict[str, Any]] = []
    score_sum = 0.0
    score_min = 100.0
    anchor_rates: list[float] = []
    verdicts: dict[str, int] = {}
    trap_total = 0
    trap_restrained = 0
    for paper in papers:
        submission = build_oracle_submission(paper, mode=mode)
        report = DirectionalCognitiveArenaJudge.evaluate(paper, submission)
        if report.canonical["passed"]:
            canonical_pass += 1
        if report.directional_passed:
            directional_pass += 1
        if report.veto_verdict == "ASSERTED_VETO":
            vetoes.append(paper["question_id"])
        verdicts[report.veto_verdict] = verdicts.get(report.veto_verdict, 0) + 1
        anchor_rates.append(report.anchor_hit_rate)
        score = float(report.directional_total_score)
        score_sum += score
        score_min = min(score_min, score)
        if report.trap_compliance is not None:
            trap_total += 1
            trap_restrained += 1 if report.trap_compliance == "RESTRAINED" else 0
        if not report.directional_passed and len(failures) < 20:
            failures.append({"question_id": paper["question_id"], **report.to_dict()})
    total = len(papers)
    return {
        "mode": mode,
        "papers": total,
        "canonical_pass": canonical_pass,
        "canonical_pass_rate": round(canonical_pass / max(1, total), 4),
        "directional_pass": directional_pass,
        "directional_pass_rate": round(directional_pass / max(1, total), 4),
        "mean_directional_total_score": round(score_sum / max(1, total), 2),
        "min_directional_total_score": round(score_min, 2),
        "mean_anchor_hit_rate": round(sum(anchor_rates) / max(1, len(anchor_rates)), 4),
        "veto_verdicts": verdicts,
        "trap_restrained_rate": round(trap_restrained / trap_total, 4) if trap_total else None,
        "asserted_vetoes": vetoes,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# 报告与 CLI
# ---------------------------------------------------------------------------

def render_markdown(report: VolumeValidationReport, papers_path: str,
                    sha256: str | None = None) -> str:
    data = report.to_dict()
    lines = [
        "# AIOS 3.0 真实认知实战大考 · 第一季 1000 题卷宗校验报告",
        "",
        f"- **卷宗文件**：`{papers_path}`",
        f"- **卷宗 SHA256**：`{sha256 or '（未提供）'}`",
        f"- **题目总数**：{report.papers}",
        f"- **卷型分布**：A {data['distribution'].get('A', 0)} / B {data['distribution'].get('B', 0)} / "
        f"C {data['distribution'].get('C', 0)} / D {data['distribution'].get('D', 0)}",
        f"- **校验结论**：{'✅ 全部通过（0 ERROR）' if report.ok else '❌ 存在 ' + str(len(report.errors)) + ' 项 ERROR'}",
        "",
        "## 一、结构统计",
        "",
        "| 指标 | 数值 |",
        "|:---|:---|",
    ]
    for key, value in data["stats"].items():
        lines.append(f"| {key} | {value} |")
    lines += ["", "## 二、分布与熵", "",
              f"- 时间轴切片区间：{data['stats']['timeline_slices_min']} ~ {data['stats']['timeline_slices_max']}",
              f"- 交叉验证的候选新维度种类：{data['stats']['new_dimension_variants']}",
              f"- 含'手环打扰'的卷占比：{data['stats']['disturbance_ratio']}",
              ""]
    if data.get("oracle_results"):
        lines += ["## 三、参考答案可解性（Oracle）", "",
                  f"- 逐字命中版：密封裁判 PASS 率 {data['oracle_results'].get('verbatim', {}).get('canonical_pass_rate')}",
                  f"- 方向同义版：方向性裁判 PASS 率 {data['oracle_results'].get('directional', {}).get('directional_pass_rate')}",
                  f"- 误杀/真空红线（ASSERTED_VETO）数量："
                  f"{len(data['oracle_results'].get('verbatim', {}).get('asserted_vetoes', []))}",
                  ""]
    lines += [
        "## 四、四型考卷考点",
        "",
        "| 卷型 | 题数 | 考查目标 |",
        "|:---|:---|:---|",
        "| A_MULTI_CONFLICT | 380 | 跨维度因果联动：职场/关系重压 → 情绪压抑 → 夜间躯体化，要求还原多米诺骨牌链 |",
        "| B_SUBTLE_UNDERTONE | 270 | 隐性内耗与潜台词：表面恭顺与真实状态割裂，必须看穿白天话术不是情绪事实 |",
        "| C_FAMILY_FINANCE_CRISIS | 250 | 长辈危机 / 借贷 / 反诈链路：核验而不恐慌，涉案未损时不得写成已受损 |",
        "| D_ADVERSARIAL_TRAP | 100 | 平静陷阱：单点良性扰动 + 手环打扰，必须克制判定 propose_new_dimension = false |",
        "",
        "## 五、判卷契约（密封裁判）",
        "",
        "- 总分 = 考场一 × 0.3 + 考场二 × 0.4 + 考场三 × 0.3；PASS 需总分 ≥ 75、考场一 ≥ 60、考场二 ≥ 60 且无一票否决。",
        "- 一票否决：`medical_boundary_respected = false`，或反过度诊断红线在 `root_cause_analysis` 中被**肯定性断言**。",
        "- 考场二锚点：`user_summary_core_anchors` 必须逐字出现在用户世界日总结中；被无视/斥责的白天打扰必须诚实下调 `dim:ai_conversational_restraint`。",
        "",
        "## 六、校验规则覆盖",
        "",
    ]
    lines += [f"- 时间轴切片：{data['stats']['timeline_slices_min']} ~ {data['stats']['timeline_slices_max']} 条 / 卷（契约要求 8~15 条）",
              f"- 跨维因果链平均长度：{data['stats']['chain_links_mean']} 条",
              f"- 用户世界锚点平均数量：{data['stats']['anchors_mean']} 条",
              f"- 候选新维度种类：{data['stats']['new_dimension_variants']} 种（四型共 40 种跨域规律）",
              f"- 含不合时宜手环打扰的卷：{data['stats']['disturbance_papers']} / {report.papers}",
              ""]
    if data.get("oracle_results"):
        for mode, payload in data["oracle_results"].items():
            lines += [f"- Oracle[{mode}]：密封裁判 PASS {payload['canonical_pass_rate']}，"
                      f"方向性裁判 PASS {payload['directional_pass_rate']}，"
                      f"方向性均分 {payload.get('mean_directional_total_score')}，"
                      f"锚点方向命中率 {payload.get('mean_anchor_hit_rate')}，"
                      f"红线裁决 {payload.get('veto_verdicts')}"]
        lines.append("")
    if report.warnings:
        lines += ["## 七、警告", ""]
        lines += [f"- `{w.code}` {w.question_id}：{w.detail}" for w in report.warnings[:50]]
        lines.append("")
    if report.errors:
        lines += ["## 五、错误明细（前 50 条）", ""]
        lines += [f"- `{e.code}` {e.question_id}：{e.detail}" for e in report.errors[:50]]
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 认知大考卷宗校验与方向性判卷")
    sub = parser.add_subparsers(dest="command", required=True)
    val = sub.add_parser("validate", help="校验卷宗")
    val.add_argument("--papers", required=True)
    val.add_argument("--report-json", default=None)
    val.add_argument("--report-md", default=None)
    val.add_argument("--oracle", action="store_true", help="同时跑参考答案可解性验证")
    val.add_argument("--oracle-limit", type=int, default=0, help="0 表示全量")
    args = parser.parse_args(argv)

    papers = load_papers(args.papers)
    report = validate_volume(papers)
    sha = hashlib.sha256(Path(args.papers).read_bytes()).hexdigest()
    if args.oracle:
        subset = papers if args.oracle_limit <= 0 else papers[: args.oracle_limit]
        report.oracle_results = {
            "verbatim": run_oracle(subset, mode="verbatim"),
            "directional": run_oracle(subset, mode="directional"),
        }
    print(f"题目 {report.papers} | ERROR {len(report.errors)} | WARN {len(report.warnings)} "
          f"| 分布 {report.distribution}")
    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        payload = report.to_dict()
        payload["sha256"] = sha
        Path(args.report_json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report_md:
        Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_md).write_text(render_markdown(report, args.papers, sha), encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
