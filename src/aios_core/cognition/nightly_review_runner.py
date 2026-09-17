"""Nightly dual-world review runner for AIOS R5/R6.

The deterministic runtime prepares chronological evidence and validates output shape.
The model performs interpretation. AI-self reflection is persisted as an evidence-
linked forward version, not as fixed personality score deltas. Cleanup output is only
an auditable candidate list; physical deletion remains outside this module behind the
normal deterministic retention/reference/permission gates.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from aios_core.contracts.models import Observation
from aios_core.runtime.ai_self_world import (
    AISelfMemoryKind,
    AISelfMemoryRecord,
    AISelfWorldStoreV2,
)


class UserDailySummaryPayload(BaseModel):
    """Model-produced user-world review grounded in source observations."""

    model_config = ConfigDict(extra="forbid")

    summary_date: str
    headline: str = Field(min_length=1)
    dim_health_digest: str = ""
    dim_social_digest: str = ""
    dim_career_digest: str = ""
    dim_finance_digest: str = ""
    dim_emotion_digest: str = ""
    emergent_capabilities: List[str] = Field(default_factory=list)
    root_cause_insights: List[str] = Field(default_factory=list)
    source_observation_ids: List[str] = Field(default_factory=list)


class AISelfReflectionPayload(BaseModel):
    """Evidence-linked AI-self review; no hard-coded self-score board."""

    model_config = ConfigDict(extra="forbid")

    reflection_date: str
    self_evaluation_notes: str = Field(min_length=1)
    mistakes_or_misjudgments: List[str] = Field(default_factory=list)
    crystallized_insights: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)


class DualWorldReviewResult(BaseModel):
    """Validated review output plus non-destructive cleanup proposals."""

    model_config = ConfigDict(extra="forbid")

    review_date: str
    user_summary: UserDailySummaryPayload
    ai_self_reflection: AISelfReflectionPayload
    ai_self_record_id: str
    cleanup_candidate_ids: List[str] = Field(
        default_factory=list,
        description=(
            "AI-proposed low-value/noise candidates only. This field does not authorize "
            "tombstoning or physical deletion."
        ),
    )
    total_context_tokens: int = Field(ge=0)
    review_latency_ms: float = Field(ge=0.0)


class NightlyReviewRunner:
    """Prepare evidence, call the cognitive model, validate, and persist reflection."""

    def __init__(
        self,
        ai_self_store: Optional[AISelfWorldStoreV2] = None,
        llm_caller: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> None:
        # In production the caller should pass the shared world DB-backed store. The
        # in-memory default exists only as a compatibility/testing fallback.
        self.ai_self_store = ai_self_store or AISelfWorldStoreV2(":memory:")
        self.llm_caller = llm_caller or self._default_mock_llm_caller

    def execute_nightly_review(
        self,
        review_date: str,
        observations: List[Observation],
        *,
        prior_context: Optional[Dict[str, Any]] = None,
    ) -> DualWorldReviewResult:
        t0 = time.perf_counter()
        context_prompt, estimated_tokens, obs_ids = self._assemble_review_prompt(
            review_date=review_date,
            observations=observations,
            prior_context=prior_context,
        )
        llm_raw = self.llm_caller(context_prompt)

        user_raw = llm_raw.get("user_summary", {})
        user_summary = UserDailySummaryPayload(
            summary_date=review_date,
            headline=user_raw.get("headline", f"{review_date} 日复盘"),
            dim_health_digest=user_raw.get("dim_health_digest", ""),
            dim_social_digest=user_raw.get("dim_social_digest", ""),
            dim_career_digest=user_raw.get("dim_career_digest", ""),
            dim_finance_digest=user_raw.get("dim_finance_digest", ""),
            dim_emotion_digest=user_raw.get("dim_emotion_digest", ""),
            emergent_capabilities=list(user_raw.get("emergent_capabilities", [])),
            root_cause_insights=list(user_raw.get("root_cause_insights", [])),
            source_observation_ids=obs_ids,
        )

        self_raw = llm_raw.get("ai_self_reflection", {})
        model_evidence = [
            str(ref) for ref in self_raw.get("evidence_refs", []) if str(ref).strip()
        ]
        # The review itself was computed from these observations; they are the minimum
        # durable evidence even when the model neglects to echo explicit refs.
        evidence_refs = list(dict.fromkeys([*model_evidence, *obs_ids]))
        if not evidence_refs:
            # A reflection with no evidence would violate AISelfMemoryKind.REFLECTION.
            # Use a deterministic review anchor rather than inventing world evidence.
            evidence_refs = [f"review:{review_date}:empty-input"]

        ai_reflection = AISelfReflectionPayload(
            reflection_date=review_date,
            self_evaluation_notes=self_raw.get(
                "self_evaluation_notes",
                "本日没有足够证据形成更具体的自我反思。",
            ),
            mistakes_or_misjudgments=list(
                self_raw.get(
                    "mistakes_or_misjudgments",
                    self_raw.get("guilt_and_mistakes", []),
                )
            ),
            crystallized_insights=list(self_raw.get("crystallized_insights", [])),
            evidence_refs=evidence_refs,
        )

        memory_key = f"reflection:nightly:{review_date}"
        latest = self.ai_self_store.latest(memory_key)
        record = AISelfMemoryRecord.create(
            memory_key=memory_key,
            version=(latest.version + 1) if latest else 1,
            kind=AISelfMemoryKind.REFLECTION,
            statement=ai_reflection.self_evaluation_notes,
            structured_data={
                "mistakes_or_misjudgments": ai_reflection.mistakes_or_misjudgments,
                "crystallized_insights": ai_reflection.crystallized_insights,
                "review_date": review_date,
            },
            evidence_refs=tuple(evidence_refs),
            previous_record_id=latest.record_id if latest else None,
        )
        self.ai_self_store.append(record)

        cleanup_candidates = [
            str(item)
            for item in llm_raw.get(
                "cleanup_candidate_ids",
                llm_raw.get("garbage_to_prune_ids", []),
            )
            if str(item).strip()
        ]

        return DualWorldReviewResult(
            review_date=review_date,
            user_summary=user_summary,
            ai_self_reflection=ai_reflection,
            ai_self_record_id=record.record_id,
            cleanup_candidate_ids=cleanup_candidates,
            total_context_tokens=estimated_tokens,
            review_latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def _assemble_review_prompt(
        self,
        review_date: str,
        observations: List[Observation],
        prior_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, int, List[str]]:
        """Serialize evidence without keyword-based cognitive classification."""

        obs_ids: List[str] = []
        chronological: list[tuple[str, str]] = []
        for obs in observations:
            obs_ids.append(obs.object_id)
            occurred = getattr(getattr(obs, "occurred", None), "start", None)
            learned = getattr(obs, "learned_at", None)
            time_anchor = occurred or learned
            stamp = time_anchor.isoformat() if time_anchor is not None else "unknown-time"
            source_kind = str(getattr(obs, "source_kind", "unknown"))
            modality = str(getattr(obs, "modality", "unknown"))
            value = str(getattr(obs, "value", ""))
            chronological.append(
                (
                    stamp,
                    f"- ref={obs.object_id} occurred={stamp} source={source_kind} "
                    f"modality={modality} value={value}",
                )
            )
        chronological.sort(key=lambda item: item[0])

        lines = [
            f"=== AIOS nightly dual-world review: {review_date} ===",
            "The following items are evidence, not pre-classified conclusions.",
            "Infer user-world summaries and AI-self lessons from evidence; preserve uncertainty.",
            "Do not invent fixed relationship tiers or personality scores.",
            "If low-value/noise records are identified, return only cleanup_candidate_ids; "
            "you do not have physical deletion authority.",
            "",
            "[chronological evidence]",
            *(item[1] for item in chronological),
        ]
        if prior_context:
            lines.extend(
                [
                    "",
                    "[prior context supplied by runtime; treat as revisable context]",
                    str(prior_context),
                ]
            )
        lines.extend(
            [
                "",
                "[required JSON keys]",
                "user_summary: headline, dim_health_digest, dim_social_digest, "
                "dim_career_digest, dim_finance_digest, dim_emotion_digest, "
                "emergent_capabilities, root_cause_insights",
                "ai_self_reflection: self_evaluation_notes, mistakes_or_misjudgments, "
                "crystallized_insights, evidence_refs",
                "cleanup_candidate_ids",
            ]
        )
        prompt = "\n".join(lines)
        return prompt, int(len(prompt) * 0.7) + 1, obs_ids

    # Backward-compatible private alias for callers/tests that reached into the old
    # helper name. The implementation is the new evidence-only assembler.
    def _assemble_adaptive_review_prompt(
        self,
        review_date: str,
        observations: List[Observation],
        prior_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, int, List[str]]:
        return self._assemble_review_prompt(review_date, observations, prior_context)

    @staticmethod
    def _default_mock_llm_caller(prompt: str) -> Dict[str, Any]:
        """Deterministic test backend; production supplies a real model caller."""

        cleanup = ["obs_noise_001"] if "obs_noise_001" in prompt else []
        return {
            "user_summary": {
                "headline": "项目推进、财务支出与晚间体征变化需要结合当天上下文一起复盘",
                "dim_health_digest": "晚间存在体征变化，应结合当天压力、休息与后续观测保持不确定性。",
                "dim_social_digest": "与合作方存在重要沟通与边界协商。",
                "dim_career_digest": "项目进入协议与风险复核阶段。",
                "dim_finance_digest": "发生了与项目相关的明确支出。",
                "dim_emotion_digest": "当天存在压力线索，但不能只凭单条记录下固定心理标签。",
                "emergent_capabilities": [],
                "root_cause_insights": [
                    "对赌协议、项目推进和晚间体征变化在时间上相邻，值得进一步核对证据，不能直接等同因果。"
                ],
            },
            "ai_self_reflection": {
                "self_evaluation_notes": (
                    "复盘时应把事实、推断与未知分开；不因体征或关键词自动替用户下心理/关系结论。"
                ),
                "mistakes_or_misjudgments": [],
                "crystallized_insights": [
                    "重要跨域关联先查原始证据，再由 AI 判断是否真的存在因果。"
                ],
                "evidence_refs": [],
            },
            "cleanup_candidate_ids": cleanup,
        }


__all__ = [
    "AISelfReflectionPayload",
    "DualWorldReviewResult",
    "NightlyReviewRunner",
    "UserDailySummaryPayload",
]
