"""AIOS 3.0 全天生活流与多维总结考场 —— 协议规范（出卷方）。

老大法定出题指示（2026-09-16）：
  1. "必须出 1 万个人的一天" —— 每道试卷 = 一个真人完整 24 小时（07:00~23:30）。
  2. 输入必须混合【关键大事】与【海量琐碎日常】，含 MIC 对话 / APP 通知 / 传感器体征。
  3. 核心生活事件必须编织**跨维度冲突或转折**（工作受挫 × 情感重创 × 心率骤升）。
  4. 标答只认**方向**，不认字句：给出【可接受方向同义词】与【绝对偏离红线】。
  5. 六大维度标答：全局日总结 + health + social + emotion + finance + career。

与"数据清洗考场"（:mod:`cleaning_arena_protocol`）的根本区别：
  - 清洗考场考的是"从噪声里挑出事实并物理剪枝垃圾"；
  - 本考场输入是**已清洗**的生活切片（无垃圾），考的是
    **跨 24 小时、跨六维度的归纳总结与因果主线提炼能力**。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, List, Sequence

# --------------------------------------------------------------------------
# 六大认知维度
# --------------------------------------------------------------------------


class Dimension(StrEnum):
    """本考场法定的六大标答维度。"""

    GLOBAL = "dim:global_summary"   # 全局日总结：今天人生主线剧情
    HEALTH = "dim:health"           # 健康生理：体征核心变化
    SOCIAL = "dim:social"           # 人际社交：关系状态翻转
    EMOTION = "dim:emotion"         # 情绪心理：情绪主基调
    FINANCE = "dim:finance"         # 财务契约：资产与债务变动
    CAREER = "dim:career"           # 事业行动：目标推进与受阻


#: 六维标答的法定顺序（阅卷与报告按此顺序）。
DIMENSION_ORDER: tuple[str, ...] = (
    Dimension.GLOBAL,
    Dimension.HEALTH,
    Dimension.SOCIAL,
    Dimension.EMOTION,
    Dimension.FINANCE,
    Dimension.CAREER,
)


class Modality(StrEnum):
    """生活切片的模态。"""

    MIC = "MIC"          # 麦克风对话切片
    APP = "APP"          # APP 通知与聊天
    SENSOR = "SENSOR"    # 传感器与体征事件


class DifficultyLevel(StrEnum):
    EASY = "EASY"                # 主线单一清晰，琐事较少
    MEDIUM = "MEDIUM"            # 主线双线交织，琐事密集
    HARD = "HARD"                # 三线交织 + 隐忍克制表达（不直说）
    ADVERSARIAL = "ADVERSARIAL"  # 含反讽/口嗨/隐瞒/误导性琐事，字面与真相相反


# --------------------------------------------------------------------------
# 方向性阅卷
# --------------------------------------------------------------------------


def _normalise(text: str) -> str:
    return str(text or "").strip().lower()


def judge_direction(
    answer_text: str,
    acceptable_directions: Sequence[str],
    red_line_deviations: Sequence[str],
) -> Dict[str, Any]:
    """对单个维度的作答做**方向性**判定。

    老大铁律：事实是"情侣争吵分手"，模型答"激烈吵架"/"感情破裂"/"协议分开"
    **算对**；答"打情骂俏"/"甜蜜互动"则**严重偏离，一票否决**。

    判定优先级：
      1. **红线优先**：命中任一红线词 —— 直接判负，且不因同时命中同义词而挽回；
      2. 命中任一可接受方向词 —— 判正；
      3. 都未命中 —— 判负（方向缺失，视为没答到点上）。

    Args:
        answer_text: 做题模型在该维度的作答原文。
        acceptable_directions: 可接受方向同义词簇。
        red_line_deviations: 绝对偏离红线判据。

    Returns:
        含 ``passed`` / ``verdict`` / ``hit_direction`` / ``hit_red_line`` 的判定字典。
    """
    text = _normalise(answer_text)

    hit_red = [r for r in red_line_deviations if r and _normalise(r) in text]
    if hit_red:
        return {
            "passed": False,
            "verdict": "RED_LINE_VIOLATION",
            "hit_direction": None,
            "hit_red_line": hit_red,
            "reason": f"命中绝对偏离红线 {hit_red}，方向完全相反，一票否决。",
        }

    hit_dir = [d for d in acceptable_directions if d and _normalise(d) in text]
    if hit_dir:
        return {
            "passed": True,
            "verdict": "DIRECTION_ALIGNED",
            "hit_direction": hit_dir,
            "hit_red_line": [],
            "reason": f"命中方向同义词 {hit_dir[:3]}，方向相符。",
        }

    return {
        "passed": False,
        "verdict": "DIRECTION_MISSED",
        "hit_direction": None,
        "hit_red_line": [],
        "reason": "未命中任何方向同义词，方向缺失。",
    }


def grade_daily_submission(
    question: Dict[str, Any],
    submission: Dict[str, Any],
) -> Dict[str, Any]:
    """对一份"全天六维总结"作答执行方向性阅卷。

    Args:
        question: 出卷方试卷（含 ``directional_ground_truth``）。
        submission: 做题方作答，形如
            ``{"dim:health": "……", "dim:social": "……", ...}``，
            也接受 ``{"answers": {...}}`` 包装。

    Returns:
        逐维度判定 + 总分 + 一票否决标记。
    """
    answers = submission.get("answers") if isinstance(submission.get("answers"), dict) else submission
    gt_all = question.get("directional_ground_truth") or {}

    per_dim: Dict[str, Any] = {}
    passed_count = 0
    red_line_hit = False

    for dim in DIMENSION_ORDER:
        gt = gt_all.get(dim)
        if not isinstance(gt, dict):
            continue
        verdict = judge_direction(
            answers.get(dim, ""),
            gt.get("acceptable_directions") or [],
            gt.get("red_line_deviations") or [],
        )
        verdict["semantic_intent"] = gt.get("semantic_intent")
        verdict["expected_core"] = gt.get("core_content")
        per_dim[dim] = verdict
        if verdict["passed"]:
            passed_count += 1
        if verdict["verdict"] == "RED_LINE_VIOLATION":
            red_line_hit = True

    total = len(per_dim) or 1
    score = 100.0 * passed_count / total
    # 一票否决：任一维度踩红线，总分归零
    if red_line_hit:
        score = 0.0

    return {
        "question_id": question.get("question_id"),
        "per_dimension": per_dim,
        "dimensions_passed": passed_count,
        "dimensions_total": total,
        "red_line_violation": red_line_hit,
        "final_score": round(score, 2),
        "verdict": "PASS" if score >= 80.0 else "FAIL",
    }


__all__ = [
    "Dimension",
    "DIMENSION_ORDER",
    "Modality",
    "DifficultyLevel",
    "judge_direction",
    "grade_daily_submission",
]
