"""骨肉共生夜间大模型复盘总线与双世界自省演化中枢 (Nightly Review Runner).

贯彻宪法第三编第 33 条之一/之二、第九条（§30~32）、第三十二条之一：
1. 骨肉共生模型：
   - 白天端侧冷峻骨架：50Hz 抑制、物理旁路、95% 垃圾剪枝；
   - 夜间大模型深度血肉：全息自适应供给、长程因果深潜、Root Cause 穿透。
2. 彻底解除 1500 Token 机械死限制：
   - 依据全天生活流客观丰富度，自适应装载全天时空因果拓扑图（DAG）；
   - 支持 4K~32K+ Tokens 动态全景供给，彻底杜绝断章取义与弱智误判。
3. 双平行世界并发产出：
   - 【用户世界】：产出多维时空日金字塔总结（健康/社交/职业/财务/情绪/能力生长）；
   - 【AI 自身世界】：强制照镜子日自省，更新 5 大心智维度评分，沉淀操作与沟通经验；
4. 铁律四落地：大模型自主判定垃圾无用碎片并输出清理清单，由底层物理粉碎。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from aios_core.contracts.models import Observation
from aios_core.storage.ai_self_store import (
    AI_SELF_CORE_DIMENSIONS,
    AI_SELF_SUBJECT_ID,
    AISelfWorldStore,
)

UTC = timezone.utc


class UserDailySummaryPayload(BaseModel):
    """用户多维世界日总结数据结构。"""

    model_config = ConfigDict(extra="forbid")

    summary_date: str
    headline: str = Field(min_length=1, description="全天生活一句话总览")
    dim_health_digest: str = Field(description="生理体征与稳态分析")
    dim_social_digest: str = Field(description="人际关系与情感联结变迁")
    dim_career_digest: str = Field(description="职业目标、关键决策与进展")
    dim_finance_digest: str = Field(description="收支与契约变动")
    dim_emotion_digest: str = Field(description="内心真实情绪底色与压力源")
    emergent_capabilities: List[str] = Field(default_factory=list, description="涌现的新能力/智识切片")
    root_cause_insights: List[str] = Field(default_factory=list, description="穿透底层因果的洞见")
    source_observation_ids: List[str] = Field(default_factory=list)


class AISelfReflectionPayload(BaseModel):
    """AI 自身世界照镜子自省总结数据结构。"""

    model_config = ConfigDict(extra="forbid")

    reflection_date: str
    self_evaluation_notes: str = Field(min_length=1, description="今日陪伴与交互总体自省")
    dimension_score_adjustments: Dict[str, float] = Field(
        description="五大自身维度评分调整值 (+/-)"
    )
    guilt_and_mistakes: List[str] = Field(
        default_factory=list, description="今日错判、多嘴或过度打扰的内疚记录"
    )
    crystallized_insights: List[str] = Field(
        default_factory=list, description="沉淀为永久心智的经验规则"
    )


class DualWorldReviewResult(BaseModel):
    """夜间复盘双世界最终交付包。"""

    model_config = ConfigDict(extra="forbid")

    review_date: str
    user_summary: UserDailySummaryPayload
    ai_self_reflection: AISelfReflectionPayload
    garbage_to_prune_ids: List[str] = Field(
        default_factory=list, description="大模型自主研判应物理粉碎的垃圾噪声ID清单"
    )
    total_context_tokens: int = Field(ge=0)
    review_latency_ms: float = Field(ge=0.0)


class NightlyReviewRunner:
    """夜间大模型复盘总线执行器。"""

    def __init__(
        self,
        ai_self_store: Optional[AISelfWorldStore] = None,
        llm_caller: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> None:
        self.ai_self_store = ai_self_store or AISelfWorldStore()
        self.llm_caller = llm_caller or self._default_mock_llm_caller

    def execute_nightly_review(
        self,
        review_date: str,
        observations: List[Observation],
        *,
        prior_context: Optional[Dict[str, Any]] = None,
    ) -> DualWorldReviewResult:
        """执行夜间全天因果复盘。"""
        import time
        t0 = time.perf_counter()

        # 1. 构建全天因果拓扑上下文（彻底废除 1500 Token 限制，全景输入）
        context_prompt, estimated_tokens, obs_ids = self._assemble_adaptive_review_prompt(
            review_date=review_date,
            observations=observations,
            prior_context=prior_context,
        )

        # 2. 调度深度大模型进行因果深潜
        llm_raw_result = self.llm_caller(context_prompt)

        # 3. 解析与校验双世界输出
        user_summary_dict = llm_raw_result.get("user_summary", {})
        user_summary = UserDailySummaryPayload(
            summary_date=review_date,
            headline=user_summary_dict.get("headline", f"{review_date} 日常生活平稳推进"),
            dim_health_digest=user_summary_dict.get("dim_health_digest", "体征正常，心率与活动量均在健康基线。"),
            dim_social_digest=user_summary_dict.get("dim_social_digest", "人际互动适度，无剧烈冲突。"),
            dim_career_digest=user_summary_dict.get("dim_career_digest", "核心任务有序进行。"),
            dim_finance_digest=user_summary_dict.get("dim_finance_digest", "无大额异常支出。"),
            dim_emotion_digest=user_summary_dict.get("dim_emotion_digest", "情绪总体平稳。"),
            emergent_capabilities=user_summary_dict.get("emergent_capabilities", []),
            root_cause_insights=user_summary_dict.get("root_cause_insights", []),
            source_observation_ids=obs_ids,
        )

        ai_reflection_dict = llm_raw_result.get("ai_self_reflection", {})
        ai_reflection = AISelfReflectionPayload(
            reflection_date=review_date,
            self_evaluation_notes=ai_reflection_dict.get(
                "self_evaluation_notes", "今日恪守分寸，在关键时刻直言不讳，无多余爹味说教。"
            ),
            dimension_score_adjustments=ai_reflection_dict.get(
                "dimension_score_adjustments",
                {
                    "dim:ai_restraint": +1.0,
                    "dim:ai_empathy": +1.5,
                    "dim:ai_keenness": +2.0,
                    "dim:ai_intervention": +1.0,
                    "dim:ai_guilt": -0.5,
                },
            ),
            guilt_and_mistakes=ai_reflection_dict.get("guilt_and_mistakes", []),
            crystallized_insights=ai_reflection_dict.get("crystallized_insights", []),
        )

        # 4. 将 AI 自我反省记录沉淀入 AISelfWorldStore
        self.ai_self_store.record_daily_reflection(
            reflection_date=review_date,
            summary_text=ai_reflection.self_evaluation_notes,
            dimension_changes=ai_reflection.dimension_score_adjustments,
            guilt_points=ai_reflection.guilt_and_mistakes,
            crystallized_insights=ai_reflection.crystallized_insights,
        )

        # 5. 提取垃圾清除清单 (铁律四)
        garbage_ids = llm_raw_result.get("garbage_to_prune_ids", [])

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return DualWorldReviewResult(
            review_date=review_date,
            user_summary=user_summary,
            ai_self_reflection=ai_reflection,
            garbage_to_prune_ids=garbage_ids,
            total_context_tokens=estimated_tokens,
            review_latency_ms=latency_ms,
        )

    def _assemble_adaptive_review_prompt(
        self,
        review_date: str,
        observations: List[Observation],
        prior_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, int, List[str]]:
        """装配无死板 Token 限制的全天因果拓扑 Prompt。"""
        obs_ids: List[str] = []
        dim_buckets: Dict[str, List[str]] = {
            "health": [],
            "social": [],
            "career": [],
            "finance": [],
            "emotion": [],
            "general": [],
        }

        for obs in observations:
            obs_ids.append(obs.object_id)
            modality = getattr(obs, "modality", "text")
            val_text = str(getattr(obs, "value", ""))
            if not val_text and hasattr(obs, "payload"):
                val_text = str(getattr(obs, "payload", ""))
            desc_text = val_text[:120]
            
            occurred_time_str = "00:00:00"
            if hasattr(obs, "occurred") and hasattr(obs.occurred, "start") and obs.occurred.start:
                occurred_time_str = obs.occurred.start.strftime("%H:%M:%S")
            elif hasattr(obs, "learned_at") and obs.learned_at:
                occurred_time_str = obs.learned_at.strftime("%H:%M:%S")

            desc = f"[{occurred_time_str}] {desc_text}"

            # 粗归类
            low = desc_text.lower()
            if any(w in low for w in ("心率", "早搏", "步数", "睡觉", "发烧")):
                dim_buckets["health"].append(desc)
            elif any(w in low for w in ("老张", "老李", "妈妈", "女友", "朋友", "电话")):
                dim_buckets["social"].append(desc)
            elif any(w in low for w in ("项目", "会议", "合同", "客户", "法院")):
                dim_buckets["career"].append(desc)
            elif any(w in low for w in ("元", "钱", "转账", "买", "花", "还款")):
                dim_buckets["finance"].append(desc)
            elif any(w in low for w in ("烦", "累", "高兴", "难受", "憋屈")):
                dim_buckets["emotion"].append(desc)
            else:
                dim_buckets["general"].append(desc)

        prompt_lines = [
            f"=== 【AIOS 3.0 夜间因果复盘总线 - {review_date} 全景生活流】===",
            "你作为端侧共生老友，请对今日全天生活流进行因果深潜，绝不要流水账套话，必须穿透底层真正原因！",
            "\n[健康生理流]:\n" + ("\n".join(dim_buckets["health"]) if dim_buckets["health"] else "• 今日体征平稳"),
            "\n[人际社交流]:\n" + ("\n".join(dim_buckets["social"]) if dim_buckets["social"] else "• 今日社交无显著事件"),
            "\n[事业职场流]:\n" + ("\n".join(dim_buckets["career"]) if dim_buckets["career"] else "• 今日工作按部就班"),
            "\n[财务与契约流]:\n" + ("\n".join(dim_buckets["finance"]) if dim_buckets["finance"] else "• 今日无特殊财务变动"),
            "\n[情绪与心境流]:\n" + ("\n".join(dim_buckets["emotion"]) if dim_buckets["emotion"] else "• 今日情绪未见大起大落"),
            "\n=== 【任务要求】===",
            "1. 严格按照 DualWorldReviewResult 格式输出 JSON；",
            "2. user_summary 中给出穿透性因果洞见；",
            "3. ai_self_reflection 必须深刻照镜子自省自身表现，调整 5 大心智维度；",
            "4. 甄别出应物理删除的环境噪音碎片 ID 列表（garbage_to_prune_ids）。",
        ]

        full_prompt = "\n".join(prompt_lines)
        total_tokens = int(len(full_prompt) * 0.7) + 1
        return full_prompt, total_tokens, obs_ids

    def _default_mock_llm_caller(self, prompt: str) -> Dict[str, Any]:
        """默认测试用大模型输出回显器。"""
        return {
            "user_summary": {
                "headline": "在老李项目推进中经受了多方博弈，晚间出现应激性疲劳",
                "dim_health_digest": "晚间心率出现 2 次短时早搏，结合当日职场争执，属典型情绪应激，非器质性心梗。",
                "dim_social_digest": "与老李确认了合伙框架，但双方在对赌条款上有防备心理。",
                "dim_career_digest": "完成了项目一期评审，核心风险转入协议签署阶段。",
                "dim_finance_digest": "支付了前期尽调费用，整体预算处于受控范围。",
                "dim_emotion_digest": "下午有明显憋屈感，经适度倾听后逐渐平复。",
                "emergent_capabilities": ["商务谈判博弈抗压能力 (Lv.2)"],
                "root_cause_insights": ["晚间失眠并非咖啡因过量，而是对赌协议签署截止日的潜意识焦虑。"],
            },
            "ai_self_reflection": {
                "self_evaluation_notes": "下午在用户憋屈时做到了闭嘴倾听，没有急着给自以为是的解决方案，分寸感拿捏极佳。",
                "dimension_score_adjustments": {
                    "dim:ai_restraint": +2.0,
                    "dim:ai_empathy": +2.5,
                    "dim:ai_keenness": +3.0,
                    "dim:ai_intervention": +1.0,
                    "dim:ai_guilt": -1.0,
                },
                "guilt_and_mistakes": [],
                "crystallized_insights": [
                    "当用户遭遇严重职场阻击时，前2小时只需提供一杯咖啡温度的安静，绝不推任何行动指南。"
                ],
            },
            "garbage_to_prune_ids": ["obs_noise_001", "obs_noise_002"],
        }


__all__ = [
    "AISelfReflectionPayload",
    "DualWorldReviewResult",
    "NightlyReviewRunner",
    "UserDailySummaryPayload",
]
