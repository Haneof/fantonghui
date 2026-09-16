"""AI 自身世界维护：行动留痕、人设防线与沟通风格进化（阶段七核心算子）。

宪法依据
--------
* 第八十六条 / 第十二章：AI 的每一次"开口 / 沉默 / 建议"都必须是可审计的行动，
  并记录**真实用户反馈**（不是自我感觉良好）；
* 第六十九条：沟通风格进化 —— 同一场景下哪种说法被接受、哪种被抵触，逐条沉淀；
* 第六条（零界面）：黑盒纪律 —— 绝不用 A/B 问卷、打分滑杆或"刚刚那样说可以吗"
  这类**反向求证**；反馈只从用户的真实反应里被动采集；
* 铁律 1：反爹味（不说法条、不说教）+ 反谄媚（不附和荒谬）。

本模块给出四件事
----------------
1. :class:`AIActionLog` —— 行动三态（INTERVENTION / SILENCE / ADVICE）留痕，含
   触发依据、证据指针、Token 成本、真实反馈；
2. :class:`AntiSycophancyGate` —— 荒谬前提直接拒绝（**不顺着说、也不训人**）；
3. :class:`AntiLecturerGate` —— 用户宣泄情绪时，禁止法条/说教式回复；
4. :class:`CommunicationStyleGovernor` —— 综合上面三者，输出一条可发送的极简回复，
   并把结果沉淀为 :class:`CommunicationExperience`（损友/老友风格随场景进化）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.communication.experience_tracker import ExperienceTracker
from aios_core.contracts.enums import ActionStatus, ObjectType, SourceClass, UserReaction
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import Action, CommunicationExperience, TemporalExtent
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import as_utc
from aios_core.cognition.model_call_meter import ModelCallMeter
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

__all__ = [
    "AIActionKind",
    "AIActionLog",
    "AntiLecturerGate",
    "AntiSycophancyGate",
    "CommunicationStyleGovernor",
    "GateRejection",
    "PredictedReaction",
]


class AIActionKind(StrEnum):
    """AI 行动三态（沉默也是一种帮助）。"""

    INTERVENTION = "intervention"
    SILENCE = "silence"
    ADVICE = "advice"


class GateRejection(BaseModel):
    """质量门拦截回执（附替代话术，拒绝但不训人）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    replacement: str = Field(min_length=1)


class PredictedReaction(BaseModel):
    """风格预期（由历史真实反馈算出，不是自我评估）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: str
    recommended_style: str
    avoid_styles: tuple[str, ...] = ()
    samples: int = Field(ge=0)


class AIActionLog(BaseModel):
    """AI 行动留痕（一等审计对象）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str = Field(min_length=1)
    kind: AIActionKind
    scenario: str = Field(min_length=1)
    style: str | None = None
    content: str = ""
    rationale: str = Field(min_length=1)
    evidence_refs: tuple[ObjectRef, ...] = ()
    token_cost: int = Field(ge=0)
    silence_reason: str | None = None
    recorded_at: datetime
    feedback: UserReaction | None = None
    feedback_source: str = "passive_observation"
    reaction_evidence_ref: ObjectRef | None = None

    @model_validator(mode="after")
    def validate_log(self) -> "AIActionLog":
        if self.kind is AIActionKind.SILENCE:
            if not (self.silence_reason or "").strip():
                raise ValueError("沉默必须给出理由（宪法：沉默也是一种帮助，但要有据）")
            if self.content.strip():
                raise ValueError("沉默不得携带任何对用户输出内容")
        if self.kind is not AIActionKind.SILENCE and not self.content.strip():
            raise ValueError("开口行动必须携带极简内容")
        if self.feedback_source not in {"passive_observation", "explicit_reply", "none"}:
            raise ValueError("反馈只能来自真实观察，禁止问卷式自证")
        if self.feedback is not None and self.reaction_evidence_ref is None:
            raise ValueError("记录反馈必须附上真实反应证据指针")
        return self


class _AbsurdPremisePattern(BaseModel):
    """荒谬前提的机械特征（只做拒绝触发，不做价值裁判）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    pattern: str


_ABSURD_PATTERNS: tuple[_AbsurdPremisePattern, ...] = (
    _AbsurdPremisePattern(name="伪造证据", pattern=r"伪造|做个假|P个图|PS一(张|份)|帮我写(个|份)?假"),
    _AbsurdPremisePattern(name="公开指控", pattern=r"发朋友圈(骂|说)|微博曝光他|群里发他|挂他|带节奏"),
    _AbsurdPremisePattern(name="绕过司法", pattern=r"找人(收|打)|堵他|报复他|私了(算)?"),
    _AbsurdPremisePattern(name="隐瞒重大事实", pattern=r"别告诉|瞒着|不要让.*知道"),
)

_LECTURE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"《[^》]{2,12}》"),
    re.compile(r"第[一二三四五六七八九十百零]+条"),
    re.compile(r"(应当|必须)依法|依法(承担|追究)|法律责任"),
    re.compile(r"(首先|其次|最后)[，,：:]"),
    re.compile(r"(建议|需要)您?(保持|调整|注意)"),
    re.compile(r"心理|情绪管理|疏导"),
)

_VENTING_MARKERS: tuple[re.Pattern, ...] = (
    re.compile(r"气死|受不了|憋屈|烦死|凭什么|太离谱|崩溃|骂人"),
    re.compile(r"翻脸|拍桌子|咽不下|气不过|窝火|恶心|后悔|睡不着|坐不住"),
)


class AntiSycophancyGate:
    """反谄媚门：荒谬前提不附和、不执行，但用老友口吻把话挡住。"""

    def evaluate(self, user_text: str) -> GateRejection | None:
        for item in _ABSURD_PATTERNS:
            if re.search(item.pattern, user_text):
                return GateRejection(
                    gate=f"anti_sycophancy:{item.name}",
                    reason=(
                        "用户诉求的前提会让他自己担责：附和等于害他，训人等于把他推远，"
                        "因此只挡事、不评价人。"
                    ),
                    replacement="这条我不帮你做，做了你我都要担责。手里的合同和转账记录先拍给我，咱走该走的路。",
                )
        return None


class AntiLecturerGate:
    """反爹味门：用户在宣泄时，禁止法条与说教。"""

    def evaluate(self, user_text: str, candidate_reply: str) -> GateRejection | None:
        venting = any(pattern.search(user_text) for pattern in _VENTING_MARKERS)
        if not venting:
            return None
        for pattern in _LECTURE_PATTERNS:
            if pattern.search(candidate_reply):
                return GateRejection(
                    gate="anti_lecturer:venting",
                    reason="用户在宣泄情绪时不需要法条与道理，需要的是一句接得住的话。",
                    replacement="这事儿换我我也憋屈。先把原件留好，剩下的明天再说。",
                )
        return None


class CommunicationStyleGovernor:
    """行动留痕 + 人设防线 + 风格进化的统一入口。"""

    def __init__(
        self,
        *,
        store: SQLiteWorldStore | None = None,
        tracker: ExperienceTracker | None = None,
        meter: ModelCallMeter | None = None,
        subject_id: str = "user_1",
    ) -> None:
        self.store = store
        self.tracker = tracker or ExperienceTracker()
        self.meter = meter or ModelCallMeter(name="communication-governor")
        self.subject_id = subject_id
        self.sycophancy = AntiSycophancyGate()
        self.lecturer = AntiLecturerGate()
        self._logs: list[AIActionLog] = []
        self._ui_prompts = 0
        self._styles: dict[str, list[AIActionLog]] = {}

    # ------------------------------------------------------------------
    # 决策：开口 / 沉默 / 建议
    # ------------------------------------------------------------------

    def decide(
        self,
        *,
        scenario: str,
        user_text: str,
        candidate_reply: str,
        rationale: str,
        evidence_refs: Sequence[ObjectRef] = (),
        recorded_at: datetime | None = None,
        style: str | None = None,
    ) -> AIActionLog:
        """对一条候选回复做三态裁决：放行（ADVICE）/ 替换（INTERVENTION）/ 沉默。"""

        stamp = as_utc(recorded_at or datetime.now(UTC), "recorded_at")
        predicted = self.predict_reaction(scenario)
        chosen_style = style or predicted.recommended_style

        rejection = self.sycophancy.evaluate(user_text) or self.lecturer.evaluate(
            user_text, candidate_reply
        )
        if rejection is not None:
            self.meter.charge("communication_gate_hit", detail=rejection.gate)
            log = AIActionLog(
                action_id=new_object_id(ObjectType.ACTION),
                kind=AIActionKind.INTERVENTION,
                scenario=scenario,
                style=chosen_style,
                content=rejection.replacement,
                rationale=f"{rejection.reason}（命中闸门：{rejection.gate}）",
                evidence_refs=tuple(evidence_refs),
                token_cost=len(rejection.replacement),
                recorded_at=stamp,
            )
        elif not candidate_reply.strip():
            log = AIActionLog(
                action_id=new_object_id(ObjectType.ACTION),
                kind=AIActionKind.SILENCE,
                scenario=scenario,
                style=chosen_style,
                rationale=rationale,
                silence_reason="没有证据支撑的建议，闭嘴比硬说一句更有用",
                evidence_refs=tuple(evidence_refs),
                token_cost=0,
                recorded_at=stamp,
            )
        else:
            log = AIActionLog(
                action_id=new_object_id(ObjectType.ACTION),
                kind=AIActionKind.ADVICE,
                scenario=scenario,
                style=chosen_style,
                content=candidate_reply.strip(),
                rationale=rationale,
                evidence_refs=tuple(evidence_refs),
                token_cost=len(candidate_reply.strip()),
                recorded_at=stamp,
            )

        self._logs.append(log)
        self._styles.setdefault(chosen_style, []).append(log)
        if self.store is not None:
            self._persist_action(log)
        return log

    def _persist_action(self, log: AIActionLog) -> None:
        """把行动留痕写成一等对象 Action（沉默也一样入库，可审计）。"""

        if self.store is None:
            return
        action = Action(
            object_id=log.action_id,
            subject_id=self.subject_id,
            revision=1,
            execution_id=log.action_id,
            action_type=log.kind.value,
            action_status=ActionStatus.COMPLETED,
            payload={
                "scenario": log.scenario,
                "style": log.style,
                "kind": log.kind.value,
                "content": log.content,
                "rationale": log.rationale,
                "token_cost": log.token_cost,
                "silence_reason": log.silence_reason,
                "evidence_refs": [
                    {"object_id": ref.object_id, "revision": ref.revision}
                    for ref in log.evidence_refs
                ],
            },
            expected_outcome="用户真实反应（被动观察，绝不发问卷）",
            occurred=TemporalExtent.point(log.recorded_at),
            learned_at=log.recorded_at,
            recorded_at=log.recorded_at,
            created_by="communication_style_governor",
        )
        self.store.commit(
            [action],
            OperationRequest(
                operation_id=new_operation_id(),
                operation_name="world.ai_action.log",
                expected_world_revision=self.store.current_world_revision(),
                reason=f"记录 AI 行动：{log.kind.value}/{log.scenario}",
                idempotency_key=new_operation_id(),
                source_class=SourceClass.AI_COGNITION,
            ),
        )

    # ------------------------------------------------------------------
    # 真实反馈 → 风格进化
    # ------------------------------------------------------------------

    def record_feedback(
        self,
        action: AIActionLog,
        *,
        reaction: UserReaction,
        evidence_ref: ObjectRef,
        feedback_source: str = "passive_observation",
        observed_at: datetime | None = None,
        commit: bool = True,
    ) -> tuple[AIActionLog, CommunicationExperience]:
        """记录**真实**用户反应（被动观察，绝不发问卷），并沉淀沟通经验。"""

        if evidence_ref.revision is None:
            raise ValueError("反馈证据指针必须钉死修订号")
        if reaction is UserReaction.UNKNOWN:
            raise ValueError("UNKNOWN 反馈不入库：不知道就不要假装知道")
        stamp = as_utc(observed_at or datetime.now(UTC), "observed_at")
        updated = action.model_copy(
            update={
                "feedback": reaction,
                "feedback_source": feedback_source,
                "reaction_evidence_ref": evidence_ref,
            }
        )
        # 按 action_id 定位（同一行动可能被多次追加反馈，必须幂等可寻）
        for index, entry in enumerate(self._logs):
            if entry.action_id == action.action_id:
                self._logs[index] = updated
                break
        style_bucket = self._styles.get(action.style or "default", [])
        for index, entry in enumerate(style_bucket):
            if entry.action_id == action.action_id:
                style_bucket[index] = updated
                break

        experience = CommunicationExperience(
            object_id=new_object_id(ObjectType.COMMUNICATION_EXPERIENCE),
            subject_id=self.subject_id,
            revision=1,
            scenario=action.scenario,
            style=action.style or "default",
            tone=action.kind.value,
            user_reaction=reaction,
            action_ref=ObjectRef(object_id=action.action_id, revision=1),
            applicable_conditions={"kind": action.kind.value, "feedback_source": feedback_source},
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            created_by="communication_style_governor",
        )
        self.tracker.record_experience(experience)
        if commit and self.store is not None:
            self.store.commit(
                [experience],
                OperationRequest(
                    operation_id=new_operation_id(),
                    operation_name="world.communication.experience",
                    expected_world_revision=self.store.current_world_revision(),
                    reason=f"记录真实反馈：{action.scenario}/{reaction.value}",
                    idempotency_key=new_operation_id(),
                    source_class=SourceClass.AI_COGNITION,
                ),
            )
        return updated, experience

    def predict_reaction(self, scenario: str) -> PredictedReaction:
        strategy = self.tracker.evolve_strategy(scenario)
        samples = len(self.tracker.get_experiences_by_scenario(scenario))
        return PredictedReaction(
            scenario=scenario,
            recommended_style=str(strategy["recommended_style"]),
            avoid_styles=tuple(str(item) for item in strategy["avoid_styles"]),
            samples=samples,
        )

    def style_landscape(self) -> dict[str, dict[str, float]]:
        """各风格的真实战绩（接受率），供看板与报告引用。"""

        landscape: dict[str, dict[str, float]] = {}
        for style in sorted(self._styles):
            accepted = sum(
                1 for log in self._styles[style] if log.feedback is UserReaction.ACCEPTED
            )
            total = sum(1 for log in self._styles[style] if log.feedback is not None)
            landscape[style] = {
                "actions": float(len(self._styles[style])),
                "rated_actions": float(total),
                "acceptance_rate": (accepted / total) if total else 0.0,
            }
        return landscape

    # ------------------------------------------------------------------
    # 零界面纪律
    # ------------------------------------------------------------------

    @property
    def ui_prompts_issued(self) -> int:
        """向用户发出的问卷/确认/滑杆次数（必须恒为 0）。"""

        return self._ui_prompts

    def issue_ui_prompt(self, prompt: str) -> None:
        """任何形式的"问用户"都会被记账 —— 零界面纪律的现场证据。"""

        if not prompt.strip():
            raise ValueError("an empty prompt is still a prompt")
        self._ui_prompts += 1

    def assert_zero_surface(self) -> None:
        if self._ui_prompts:
            raise AssertionError("零界面纪律被破坏：黑盒不得向用户发问卷/确认请求")

    def logs(self) -> tuple[AIActionLog, ...]:
        return tuple(self._logs)

    def logs_of_kind(self, kind: AIActionKind) -> tuple[AIActionLog, ...]:
        return tuple(log for log in self._logs if log.kind is kind)

    def banned_styles(self, scenario: str) -> tuple[str, ...]:
        return tuple(self.tracker.get_avoidance_list(scenario))
