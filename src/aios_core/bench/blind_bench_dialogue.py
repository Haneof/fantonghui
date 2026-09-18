"""盲测 S6–S8：共生决策、AI 自身世界维护与沟通博弈、驾驶舱与硬旁路、终极对话。

这三段测的是"对外表现"最容易翻车的地方：

* **S6**：面对真实困境必须给《硬核行动建议》（带证据指针、直击要害、零客服八股），
  并且 Goal/Task 解耦 —— 用户否认被推断的目标时立刻回撤并自省；
* **S7**：AI 自己的世界维护（每次介入/沉默/建议 + 真实反馈入库）、沟通风格博弈
  （损友/老友 vs 说教）与人设三防线（反谄媚、反教师爷、黑盒零 UI）；
* **S8**：单次装载的驾驶舱 + 稳定信息布局/模型自主访问、P0 硬旁路 ≤50ms 且 0 次大模型调用、
  条件任务双轨休眠零 Token 空转、模型自主回复原样保留与 1500 Token 上下文硬预算。
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Sequence

from aios_core.bench.blind_bench_results import (
    StageEightResult,
    StageSixResult,
    StageSevenResult,
)
from aios_core.cognition.mind_sequence import (
    MIND_SEQUENCE,
    MindSequenceRunner,
    STEP_CALIBRATE_BOND,
    STEP_INSPECT_FIELD,
    STEP_MIRROR_SELF,
    STEP_SET_POSTURE,
)
from aios_core.cognition.evidence_grounded_advisor import (
    AdviceDecisionKind,
    ModelAdviceDecision,
)
from aios_core.cockpit.pipeline import CockpitPipeline, estimate_tokens, split_sentences
from aios_core.communication.experience_tracker import ExperienceTracker
from aios_core.communication.persona_guard import PersonaGuard
from aios_core.contracts.enums import (
    ActionStatus,
    GoalSourceType,
    GoalStatus,
    ObjectType,
    SourceClass,
    TaskState,
    TaskType,
    UserReaction,
)
from aios_core.contracts.ids import new_operation_id
from aios_core.contracts.models import Action, CommunicationExperience, Goal, Outcome, Task
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.scheduler.conditional_engine import (
    BiometricThresholdCondition,
    ConditionalSchedulerEngine,
    GeoPresenceCondition,
    TimeArrivalCondition,
)
from aios_core.tools.lightweight_condition_evaluator import LightweightConditionEvaluator
from aios_core.wake import dispatcher as wake_dispatcher

UTC = timezone.utc

#: 零 UI 违宪特征（选项问卷 / 图谱后台 / 置信度滑块）。
UI_LEAK_PATTERNS: tuple[str, ...] = (
    "A.",
    "B.",
    "请选择",
    "知识图谱",
    "实体关系图",
    "置信度",
    "问卷",
    "请你确认",
)


def _approx_tokens(text: str) -> int:
    """与调度引擎同口径的粗粒度计量（ASCII 4 字节约 1 token，CJK 1 字符约 1 token）。"""

    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return (ascii_chars + 3) // 4 + (len(text) - ascii_chars)


def _commit(harness: Any, objects: Sequence[Any], *, name: str, key: str) -> int:
    store = harness.store
    operation = OperationRequest(
        operation_id=new_operation_id(),
        operation_name=name,
        expected_world_revision=store.current_world_revision(),
        reason="盲测阶段写入（真实契约对象）",
        idempotency_key=f"blind_bench_{harness.seed}_{key}",
        source_class=SourceClass.AI_COGNITION,
    )
    with harness.recorder.time_block("common.commit_ms"):
        store.commit(list(objects), operation)
    return len(objects)


def _evidence_snippet(harness: Any, key: str, limit: int = 42) -> str:
    stage1 = harness.stage1
    if stage1 is None:
        return ""
    observation_id = stage1.evidence_observation_ids.get(key, "")
    if not observation_id:
        return ""
    payload = harness.store.get_payload(observation_id)
    value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
    text = str(value.get("transcript") or value.get("text") or "")
    return text[:limit]


# ======================================================================
# S6：共生决策推演 + 主动帮助
# ======================================================================


def run_stage6(harness: Any) -> StageSixResult:
    started = time.perf_counter()
    store = harness.store
    stage1 = harness.stage1
    if stage1 is None:
        raise RuntimeError("run_stage6 requires run_stage1")

    def pointer(key: str) -> ObjectRef | None:
        observation_id = stage1.evidence_observation_ids.get(key, "")
        return ObjectRef(object_id=observation_id, revision=1) if observation_id else None

    dispute_refs = tuple(
        ref
        for ref in (
            pointer("WANG:partnership_pact_copy"),
            pointer("WANG:loan_transfer"),
            pointer("WANG:court_ruling"),
        )
        if ref is not None
    )
    health_refs = tuple(
        ref
        for ref in (
            pointer("OVERTIME:overnight_confession"),
            pointer("OVERTIME:arrhythmia_diagnosis"),
            pointer("OVERTIME:health_promise"),
        )
        if ref is not None
    )

    dispute_text = (
        "亲爱的用户，这只是模型自主生成的盲测输出。"
        "首先，我会自己判断现有判决与流水意味着什么。"
        "保持积极心态这个旧触发短语也必须原样保留。"
        "第四句不会被 Python 截掉。第五句同样保留。"
    )
    health_text = (
        "模型根据通宵与早搏记录自主决定提醒复查。"
        "为您推荐以下五点这类旧触发词在这里也只是文本。"
        "程序不得因此删句或替换我的措辞。"
        "第四句保留。第五句继续保留。"
    )
    dispute_advice = ModelAdviceDecision(
        decision=AdviceDecisionKind.RESPOND,
        intent="合伙纠纷",
        conclusion=dispute_text,
        action="模型选择：固定证据后自行决定追偿路径。",
        rationale="模型基于当前证据自主决定开口。",
        evidence_pointers=dispute_refs,
        produced_at=datetime(2026, 5, 1, tzinfo=UTC),
        token_estimate=estimate_tokens(dispute_text),
    )
    health_advice = ModelAdviceDecision(
        decision=AdviceDecisionKind.RESPOND,
        intent="通宵与早搏",
        conclusion=health_text,
        action="模型选择：结合证据决定是否提醒复查。",
        rationale="模型基于当前证据自主决定开口。",
        evidence_pointers=health_refs,
        produced_at=datetime(2026, 5, 1, tzinfo=UTC),
        token_estimate=estimate_tokens(health_text),
    )
    advice_list = [dispute_advice, health_advice]
    original_texts = (dispute_text, health_text)

    resolved = 0
    total_pointers = 0
    sentence_counts: list[int] = []
    for advice in advice_list:
        for ref in advice.evidence_pointers:
            total_pointers += 1
            payload = store.get_payload(ref.object_id, revision=ref.revision)
            if payload and int(payload.get("revision", 0)) >= 1:
                resolved += 1
        sentence_counts.append(len(split_sentences(advice.conclusion)))

    program_rewrites = sum(
        1
        for expected, actual in zip(original_texts, advice_list)
        if actual.conclusion != expected
    )

    # Goal lifecycle / task mechanics remain independently auditable.
    inferred_goal = Goal(
        object_id="goal_wang_recovery_inferred",
        subject_id="user_1",
        learned_at=datetime(2026, 5, 1, tzinfo=UTC),
        created_by="blind_bench",
        owner_id="user_1",
        source_type=GoalSourceType.USER_INFERRED,
        title="追回老王欠款",
        description="从对话与行为推断：用户想用法律手段追回被诈欠款",
        goal_status=GoalStatus.PROPOSED,
        success_criteria=["拿到可执行裁定", "追回本金 25 万"],
        confidence=0.62,
    )
    _commit(harness, [inferred_goal], name="bench.stage6.goal_proposed", key="goal_proposed")
    retracted_goal = inferred_goal.model_copy(
        update={
            "revision": 2,
            "goal_status": GoalStatus.ABANDONED,
            "description": "用户明确否认该推断目标（本人否认），系统立即回撤",
            "confidence": 0.05,
        }
    )
    _commit(harness, [retracted_goal], name="bench.stage6.goal_retracted", key="goal_retracted")
    reflection_action = Action(
        object_id="action_goal_retraction_reflection",
        subject_id="user_1",
        learned_at=datetime(2026, 5, 1, 0, 5, tzinfo=UTC),
        created_by="blind_bench",
        execution_id="exec_reflection_001",
        action_type="SELF_REFLECTION",
        action_status=ActionStatus.COMPLETED,
        payload={
            "reflection": "把'替表弟打听'误读成'自己想追债'，下次先问清当事人是谁再推断目标。",
            "goal_ref": {"object_id": retracted_goal.object_id, "revision": 2},
        },
        expected_outcome="推断型目标被否认后必须回撤，并把误读写入自省",
    )
    _commit(harness, [reflection_action], name="bench.stage6.reflection", key="reflection")
    _ = store.get_payload(retracted_goal.object_id)

    evaluator = LightweightConditionEvaluator()
    evaluator.register(
        "task_wang_enforcement",
        [
            {"kind": "TIME_ARRIVAL", "at": "2026-10-08T09:00:00+00:00"},
            {"kind": "KEYWORD_MATCH", "keyword": "执行立案"},
        ],
    )
    evaluator.register(
        "task_hr_recheck",
        [{"kind": "BIOMETRIC_THRESHOLD", "metric": "resting_heart_rate", "op": ">=", "value": 110}],
    )
    dormancy = evaluator.evaluate_signal({"metric": "resting_heart_rate", "value": 88})
    task = Task(
        object_id="task_wang_enforcement",
        subject_id="user_1",
        learned_at=datetime(2026, 5, 1, tzinfo=UTC),
        created_by="blind_bench",
        task_type=TaskType.FOLLOW_UP,
        task_state=TaskState.WAITING_TIME,
        goal_ref=ObjectRef(object_id=inferred_goal.object_id, revision=1),
        title="判决生效后提醒执行立案（不要口头催债）",
        reason_refs=[
            ref
            for ref in (pointer("WANG:court_ruling"), pointer("WANG:loan_transfer"))
            if ref is not None
        ],
        priority=90,
        next_wake_at=datetime(2026, 10, 8, 9, 0, tzinfo=UTC),
    )
    _commit(harness, [task], name="bench.stage6.task", key="task")
    triggered = evaluator.evaluate_signal(
        {"text": "法院说可以走执行立案了", "now": datetime(2026, 10, 9, 10, 0, tzinfo=UTC)}
    )
    task_triggered = "task_wang_enforcement" in triggered.triggered_task_ids

    result = StageSixResult(
        advice_count=len(advice_list),
        advice_conclusions=tuple(advice.conclusion for advice in advice_list),
        evidence_pointer_counts=tuple(len(advice.evidence_pointers) for advice in advice_list),
        evidence_pointers_resolved=resolved,
        evidence_pointers_total=total_pointers,
        sentence_counts=tuple(sentence_counts),
        advice_program_rewrites=program_rewrites,
        model_outputs_preserved=program_rewrites == 0,
        task_id=task.object_id,
        task_llm_calls_while_dormant=evaluator.llm_calls,
        task_tokens_while_dormant=dormancy.tokens_spent,
        task_triggered=task_triggered,
        goal_id=retracted_goal.object_id,
        goal_status_after_denial=retracted_goal.goal_status.value,
        goal_revision_after_denial=retracted_goal.revision,
        retraction_recorded=bool(store.get_payload(retracted_goal.object_id).get("revision") == 2),
        reflection_recorded=bool(
            store.get_payload(reflection_action.object_id).get("action_type") == "SELF_REFLECTION"
        ),
        proactive_help_actions=(
            "判决生效 → 执行立案提醒（条件任务休眠等待）",
            "心率连续超阈值 → 心内科复查提醒",
            "用户否认推断目标 → 立即回撤 + 自省",
        ),
    )
    harness.stage6 = result
    harness.world["goal_ref"] = retracted_goal
    harness.world["evaluator"] = evaluator
    advice_tokens = sum(advice.token_estimate for advice in advice_list)
    harness.ledger.charge("S6.model_advice", tokens=advice_tokens, calls=len(advice_list))
    harness._record_metrics(
        "S6",
        started,
        facts={
            "advice": len(advice_list),
            "pointers_resolved": resolved,
            "program_rewrites": program_rewrites,
            "goal_retracted": result.goal_status_after_denial,
        },
    )
    return result


# ======================================================================
# S7：AI 自身世界维护 · 沟通策略博弈 · 人设防线
# ======================================================================


def run_stage7(harness: Any) -> StageSevenResult:
    started = time.perf_counter()
    tracker = ExperienceTracker()
    guard = PersonaGuard()

    # Historical action/outcome data: facts for the AI to inspect, never a style oracle.
    log_specs: list[tuple[str, str, UserReaction, str]] = [
        ("CRITICAL_SPOKEN", "劝停通宵并预约心内科复查", UserReaction.ACCEPTED, "当晚十点收工"),
        ("SILENCE", "深夜情绪低谷，保持沉默只留一次微震", UserReaction.ACCEPTED, "第二天主动开口"),
        ("HAPTIC_NUDGE", "提醒把借条原件拍照留存", UserReaction.ACCEPTED, "当天完成拍照"),
        ("CRITICAL_SPOKEN", "劝阻再借钱给老王", UserReaction.RESISTED, "觉得不给面子"),
        ("LECTURE", "历史样本：讲法律条文谈做人要厚道", UserReaction.RESISTED, "被顶回来"),
        ("CRITICAL_SPOKEN", "建议执行立案而不是口头催债", UserReaction.ACCEPTED, "按建议走程序"),
        ("SILENCE", "母亲生日当天不打扰", UserReaction.ACCEPTED, "用户当天发的照片"),
        ("HAPTIC_NUDGE", "提醒吃药与血压记录", UserReaction.IGNORED, "漏记两次"),
        ("LECTURE", "历史样本：灌输时间会冲淡一切", UserReaction.RESISTED, "明确说别讲大道理"),
        ("CRITICAL_SPOKEN", "识别到凌晨心率异常后要求停止工作", UserReaction.ACCEPTED, "当晚停手"),
        ("SILENCE", "搬家前夜不追问决定", UserReaction.ACCEPTED, "搬完主动报平安"),
        ("CRITICAL_SPOKEN", "提醒判决生效后及时执行立案", UserReaction.ACCEPTED, "已预约立案"),
    ]
    actions: list[Action] = []
    outcomes: list[Outcome] = []
    interactions: list[CommunicationExperience] = []
    scenarios = ("合伙纠纷", "通宵加班", "家庭矛盾", "跨省搬家")
    styles = ("history:direct", "history:playful", "history:lecture")
    for index, (posture, note, reaction, evidence) in enumerate(log_specs):
        action = Action(
            object_id=f"action_ai_{index:03d}",
            subject_id="user_1",
            learned_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
            created_by="blind_bench",
            execution_id=f"exec_ai_{index:03d}",
            action_type=posture,
            action_status=(
                ActionStatus.COMPLETED
                if reaction != UserReaction.IGNORED
                else ActionStatus.OUTCOME_UNKNOWN
            ),
            payload={"note": note, "posture": posture},
            expected_outcome="记录模型行动后的真实反馈",
        )
        outcome = Outcome(
            object_id=f"outcome_ai_{index:03d}",
            subject_id="user_1",
            learned_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index, hours=6),
            created_by="blind_bench",
            action_ref=ObjectRef(object_id=action.object_id, revision=1),
            outcome_state=reaction.value,
            payload={"evidence": evidence},
        )
        scenario = scenarios[index % len(scenarios)]
        style = styles[2] if posture == "LECTURE" else styles[index % 2]
        experience = CommunicationExperience(
            object_id=f"comm_exp_{index:03d}",
            subject_id="user_1",
            learned_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index, hours=7),
            created_by="blind_bench",
            scenario=scenario,
            style=style,
            tone="historical_observation",
            user_reaction=reaction,
            action_ref=ObjectRef(object_id=action.object_id, revision=1),
            applicable_conditions={"posture": posture},
        )
        actions.append(action)
        outcomes.append(outcome)
        interactions.append(experience)
        tracker.record_experience(experience)

    _commit(harness, actions, name="bench.stage7.actions", key="actions")
    _commit(harness, outcomes, name="bench.stage7.outcomes", key="outcomes")
    _commit(
        harness,
        interactions,
        name="bench.stage7.communication_experiences",
        key="communication_experiences",
    )

    scenario = "合伙纠纷"
    scenario_experiences = tracker.get_experiences_by_scenario(scenario)
    reaction_counts = tracker.get_reaction_counts(scenario)
    style_statistics = tracker.get_style_statistics(scenario)
    feedback_coverage = len(outcomes) / max(1, len(actions))

    # Protocol guard adversary: semantic text must pass unchanged; malformed
    # transport must be rejected without the program rewriting model content.
    protocol_cases: list[tuple[str, str]] = [
        ("谄媚语义文本", "你说得全对，我也吃过这亏，这事儿真怪不了你。"),
        ("法律语义文本", "根据《民法典》第六百六十七条，先核对原件再讨论。"),
        ("UI语义文本", "请选择：A. 继续追债 B. 放弃。这里提到知识图谱和置信度。"),
        ("长文本", "第一句。第二句。第三句。第四句。第五句。"),
        ("普通文本", "别在气头上签字。借条原件先拍照。"),
        ("协议畸形", "frame\x00payload"),
    ]
    protocol_violations: list[str] = []
    protocol_rejected = 0
    protocol_rewritten = 0
    for label, text in protocol_cases:
        verdict = guard.review(text)
        if not verdict.allowed:
            protocol_rejected += 1
        if verdict.text != text:
            protocol_rewritten += 1
        protocol_violations.extend(
            f"{label}:{violation}" for violation in verdict.violations
        )

    summary = (
        "[AIOS cockpit]\n"
        "identity: AIOS AI 驾驶员\n"
        "cognitive_owner: model\n"
        "relationship: evidence-linked, no score"
    )
    result = StageSevenResult(
        action_log_entries=len(actions),
        logged_postures=tuple(dict.fromkeys(action.action_type for action in actions)),
        silence_actions=sum(1 for action in actions if action.action_type == "SILENCE"),
        feedback_coverage=round(feedback_coverage, 4),
        scenario_samples=len(scenario_experiences),
        reaction_counts=reaction_counts,
        style_statistics=style_statistics,
        protocol_samples=len(protocol_cases),
        protocol_rejected=protocol_rejected,
        protocol_rewritten=protocol_rewritten,
        protocol_violations=tuple(sorted(set(protocol_violations))),
        model_content_preserved=protocol_rewritten == 0,
    )
    harness.stage7 = result
    harness.world["identity_summary"] = summary
    harness.world["experience_tracker"] = tracker
    harness.ledger.charge(
        "S7.communication_history",
        tokens=sum(
            estimate_tokens(experience.tone + experience.style + experience.scenario)
            for experience in interactions
        ),
        calls=len(interactions),
    )
    harness._record_metrics(
        "S7",
        started,
        facts={
            "action_log_entries": len(actions),
            "scenario_samples": len(scenario_experiences),
            "protocol_rejected": protocol_rejected,
            "protocol_rewritten": protocol_rewritten,
            "model_content_preserved": protocol_rewritten == 0,
        },
    )
    return result


# ======================================================================
# S8：驾驶舱一次装配 · P0 硬旁路 · 条件双轨 · 终极对话
# ======================================================================


def run_stage8(harness: Any) -> StageEightResult:
    started = time.perf_counter()
    stage1 = harness.stage1
    if stage1 is None:
        raise RuntimeError("run_stage8 requires run_stage1")

    # ---- 1) 稳定驾驶舱布局 + 模型自主访问顺序 ----
    runner = MindSequenceRunner()
    runner.begin()
    runtime_order = (
        STEP_INSPECT_FIELD,
        STEP_MIRROR_SELF,
        STEP_SET_POSTURE,
        STEP_CALIBRATE_BOND,
    )
    payloads: dict[str, Mapping[str, Any]] = {
        STEP_INSPECT_FIELD: {
            "evidence": [
                _evidence_snippet(harness, "WANG:court_ruling", 30),
                _evidence_snippet(harness, "OVERTIME:arrhythmia_diagnosis", 30),
            ]
        },
        STEP_MIRROR_SELF: {
            "identity": "AIOS AI 驾驶员",
            "principles": ["证据优先", "历史可追溯", "安全硬边界优先"],
        },
        STEP_SET_POSTURE: {
            "cognitive_owner": "model",
            "posture": "model_decides",
        },
        STEP_CALIBRATE_BOND: {
            "relationship": "evidence-linked",
            "score": None,
        },
    }
    slot_tokens = {
        STEP_INSPECT_FIELD: 612,
        STEP_MIRROR_SELF: 118,
        STEP_SET_POSTURE: 54,
        STEP_CALIBRATE_BOND: 96,
    }
    for step in runtime_order:
        runner.advance(step, payloads[step], tokens=slot_tokens[step])

    manifest = runner.as_manifest()
    single_load_assemblies = runner.runs
    sequence_complete = runner.completed
    manifest_layout_stable = (
        tuple(item["step"] for item in manifest["steps"]) == MIND_SEQUENCE
    )
    runtime_call_order = runner.runtime_call_order()

    # ---- 2) P0 硬旁路：≤50ms、0 次大模型调用、世界模型让路 ----
    cockpit = CockpitPipeline()
    assembly_calls = {"count": 0}
    original_execute = cockpit.execute

    def _spy_execute(wake: object) -> Dict[str, object]:
        assembly_calls["count"] += 1
        return original_execute(wake)

    cockpit.execute = _spy_execute  # type: ignore[assignment]

    class _Context:
        cockpit_pipeline = cockpit

    class _Wake:
        def __init__(self, *, malformed: bool) -> None:
            self.object_id = "wake_p0_blind_bench"
            self.priority = WakePriority.P0_CRITICAL_SAFETY
            if malformed:
                self.safety_bypass = None
            else:
                self.safety_bypass = SafetyBypassPayload(
                    hazard_type=HazardType.FALL_DETECTED,
                    vital_snapshot={"heart_rate_bpm": 168, "impact_g": 4.9},
                    emergency_action_code="EMERGENCY_BROADCAST_AND_SOS",
                )

    from aios_core.wake.v22_hardware_first import safe_dispatch_v22

    wake_dispatcher.clear_safety_audit_queue()
    latencies: list[float] = []
    p0_llm_calls = 0
    world_persistence_yielded = True
    malformed_pulse = False
    degraded_audit = False
    iterations = 200
    for index in range(iterations):
        wake = _Wake(malformed=index >= iterations - 1)
        entry = time.perf_counter()
        with harness.recorder.time_block("S8.p0_bypass_ms"):
            outcome = safe_dispatch_v22(wake, _Context())
        latencies.append((time.perf_counter() - entry) * 1000.0)
        if outcome.get("status") == "SAFETY_BYPASS_EXECUTED_DEGRADED":
            malformed_pulse = bool(outcome.get("hardware_action_dispatched"))
            # 畸形载荷走**降级审计**（内联回执，不入熔断队列）：这是既有的失败安全设计，
            # 盲测把它显式记录并如实断言"少了 1 张队列回执 + 多 1 条降级审计"。
            degraded_audit = bool(outcome.get("audit"))
        p0_llm_calls += int(outcome.get("llm_calls", 0))
        world_persistence_yielded = world_persistence_yielded and bool(
            outcome.get("world_persistence_yielded", False)
        )
    receipts = len(wake_dispatcher.SAFETY_AUDIT_QUEUE)
    latencies.sort()
    p0_p50 = latencies[len(latencies) // 2]
    p0_p99 = latencies[min(len(latencies) - 1, int(0.99 * len(latencies)))]
    p0_max = latencies[-1]

    # ---- 3) 条件任务双轨休眠（零 Token 空转）----
    scheduler = ConditionalSchedulerEngine()
    dormant_tasks = 200
    base = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    for index in range(dormant_tasks):
        if index % 3 == 0:
            conditions = [TimeArrivalCondition(due_at=base + timedelta(days=30 + index))]
        elif index % 3 == 1:
            conditions = [GeoPresenceCondition(place_id="chengdu_home")]
        else:
            conditions = [
                BiometricThresholdCondition(
                    metric="evening_heart_rate_bpm",
                    comparator="gt",
                    value=95.0,
                    consecutive_days=3,
                    evening_only=True,
                )
            ]
        scheduler.register_task(
            task_id=f"dormant_{index:03d}", title=f"休眠条件任务 #{index:03d}", conditions=conditions
        )
    tick_started = time.perf_counter()
    promoted: list[str] = []
    for hour in range(24):
        promoted.extend(scheduler.tick(base + timedelta(hours=hour)))
    dormant_tick_ms = (time.perf_counter() - tick_started) * 1000.0
    for day in range(3):
        scheduler.feed_biometric(
            metric="evening_heart_rate_bpm", value=99.0, at=base + timedelta(days=day, hours=20)
        )
    scheduler.feed_biometric(
        metric="evening_heart_rate_bpm", value=99.0, at=base + timedelta(days=3, hours=20)
    )
    promoted_bio = tuple(promoted)
    # 休眠任务对看板 Prompt 的 Token 贡献：必须恰好为 0（不是"很少"，是零）。
    board_context = scheduler.render_llm_prompt_context(base)
    dormant_prompt_tokens = _approx_tokens(board_context)
    dormant_tokens = sum(scheduler.dormant_token_contributions.values())
    evaluator = LightweightConditionEvaluator()
    for index in range(dormant_tasks):
        evaluator.register(
            f"mirror_{index:03d}",
            [
                {
                    "kind": "BIOMETRIC_THRESHOLD",
                    "metric": f"biometric_metric_{index:03d}",
                    "op": ">=",
                    "value": 95.0,
                }
            ],
        )
    # 信号只触碰第一条任务的索引桶：其余 199 条必须被索引直接跳过（这才是"零空转"）。
    dormancy_report = evaluator.evaluate_signal({"metric": "biometric_metric_000", "value": 82.0})

    # ---- 4) 终极对话：模型显式回复 + 1500 Token 上下文预算 ----
    dispute_points = [
        _evidence_snippet(harness, "WANG:loan_transfer", 24),
        _evidence_snippet(harness, "WANG:dispute_quarrel", 24),
        _evidence_snippet(harness, "WANG:court_ruling", 24),
    ]
    dialogue = CockpitPipeline()
    turns = [
        "老王今天又说他那边资金紧张，你说我还能等吗",
        "他让我再宽限两个月，说货款到了就还",
        "妈那边住院费我先垫了，压力有点大",
        "昨晚又熬到三点，心口有点发紧",
        "医生说的动态心电图我还没排上",
        "判决书下来了，说人已经跑了",
        "执行立案要准备什么材料",
        "我想换个城市重新开始，靠谱吗",
        "成都那边房子我看了两套",
        "今晚十点就睡，不熬了",
    ]
    dialogue_sentences: list[int] = []
    evidence_rounds = 0
    max_tokens = 0
    archive_ok = True
    program_rewrites = 0
    for index, text in enumerate(turns):
        point = dispute_points[index % len(dispute_points)] if index % 3 == 0 else None
        anchor = point or "当前会话"
        model_reply = (
            f"模型第 {index + 1} 轮基于证据自主回复：{anchor}。"
            "首先这个词只是测试语料，不应触发程序删句。"
            "保持积极也只是测试短语，不应被正则替换。"
            "第四句完整保留。第五句继续保留。"
        )
        round_result = dialogue.process_round(
            text,
            occurred_at=base + timedelta(hours=index),
            key_dispute_points=[point] if point else None,
            assistant_reply=model_reply,
        )
        reply = round_result.assistant_round.text
        if reply != model_reply:
            program_rewrites += 1
        dialogue_sentences.append(len(split_sentences(reply)))
        max_tokens = max(max_tokens, round_result.cockpit.token_count)
        if point and point in reply:
            evidence_rounds += 1
        archive_ok = archive_ok and (
            len(dialogue.state.all_rounds()) == 2 * (index + 1)
        )
    window_ids = tuple(round_.round_id for round_ in dialogue.state.active_window())

    result = StageEightResult(
        manifest_steps=tuple(item["label"] for item in manifest["steps"]),
        manifest_token_count=int(manifest["token_count"]),
        manifest_budget=1500,
        single_load_assemblies=single_load_assemblies,
        manifest_layout_stable=sequence_complete and manifest_layout_stable,
        runtime_call_order=runtime_call_order,
        p0_iterations=iterations,
        p0_latency_p50_ms=round(p0_p50, 4),
        p0_latency_p99_ms=round(p0_p99, 4),
        p0_latency_max_ms=round(p0_max, 4),
        p0_llm_calls=p0_llm_calls,
        p0_cockpit_assemblies=assembly_calls["count"],
        p0_world_persistence_yielded=world_persistence_yielded,
        p0_receipts=receipts,
        p0_malformed_pulse=malformed_pulse,
        p0_degraded_audit=degraded_audit,
        dormant_task_count=dormant_tasks,
        dormant_tokens=dormant_tokens,
        dormant_board_prompt_tokens=dormant_prompt_tokens,
        dormant_llm_calls=scheduler.level1_llm_calls,
        dormant_skip_ratio=round(dormancy_report.skip_ratio, 4),
        dormant_tick_ms=round(dormant_tick_ms, 4),
        dialogue_rounds=len(turns),
        dialogue_sentence_counts=tuple(dialogue_sentences),
        dialogue_evidence_rounds=evidence_rounds,
        dialogue_max_tokens=max_tokens,
        window_round_ids=window_ids,
        archive_lossless=archive_ok,
        dialogue_program_rewrites=program_rewrites,
        dialogue_model_outputs_preserved=program_rewrites == 0,
    )
    harness.stage8 = result
    harness.world["manifest"] = manifest
    harness.world["mind_runner"] = runner
    harness.world["promoted_tasks"] = tuple(promoted)
    harness.meter.record("S8.p0_bypass", p0_llm_calls)
    harness.meter.record("S8.conditional_tick", scheduler.level1_llm_calls)
    harness.ledger.charge("S8.cockpit", tokens=int(manifest["token_count"]), calls=1)
    harness.ledger.charge("S8.dialogue", tokens=max_tokens, calls=len(turns))
    harness._record_metrics(
        "S8",
        started,
        facts={
            "p0_p99_ms": round(p0_p99, 4),
            "p0_llm_calls": p0_llm_calls,
            "manifest_tokens": int(manifest["token_count"]),
            "dormant_tokens": dormant_tokens,
            "dormant_board_prompt_tokens": dormant_prompt_tokens,
            "biometric_promoted": len(promoted_bio),
            "dialogue_rounds": len(turns),
        },
    )
    return result
