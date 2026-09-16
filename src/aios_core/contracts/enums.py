from __future__ import annotations

from enum import StrEnum


class ObjectType(StrEnum):
    OBSERVATION = "observation"
    ENTITY = "entity"
    RELATION = "relation"
    DIMENSION_DEFINITION = "dimension_definition"
    DIMENSION_MEMBERSHIP = "dimension_membership"
    DIMENSION_DERIVATION = "dimension_derivation"
    CLAIM = "claim"
    EVIDENCE_SET = "evidence_set"
    EVENT = "event"
    SUMMARY = "summary"
    GOAL = "goal"
    DEPENDENCY = "dependency"
    TASK = "task"
    WAKE = "wake"
    SESSION = "session"
    ACTION = "action"
    OUTCOME = "outcome"
    OPERATION_EXPERIENCE = "operation_experience"
    TOOL_PROPOSAL = "tool_proposal"
    # --- R4 修改案（M0-023~028）新增一等对象（批准前为候选契约） ---
    PREDICTION = "prediction"
    LIFE_CHAPTER = "life_chapter"
    REINTERPRETATION = "reinterpretation"
    COMMUNICATION_EXPERIENCE = "communication_experience"
    BUDGET_POLICY = "budget_policy"
    ASSEMBLY_POLICY = "assembly_policy"


class SourceClass(StrEnum):
    """写入来源分类（R4-02：第 79 条之二）。

    MAINTENANCE 对第 79 条机械触发评估不可见；SAFETY 由固件桥与内核调度器
    专属持有。豁免判定只读本字段，禁止以语义识别代替（第 77/106 条）。
    """

    USER = "user"
    SENSOR = "sensor"
    AI_COGNITION = "ai_cognition"
    MAINTENANCE = "maintenance"
    SAFETY = "safety"


class MaintenanceClass(StrEnum):
    """MAINTENANCE 写入必须声明的维护类别（R4-02）。"""

    STALE_MARK = "stale_mark"
    SUMMARY_REBUILD = "summary_rebuild"
    PRUNE = "prune"
    INDEX_META = "index_meta"
    POLICY_SYNC = "policy_sync"


class PredictionVerificationState(StrEnum):
    """第 50 条 Prediction 对撞状态机。"""

    PENDING = "pending"
    CORROBORATED = "corroborated"
    FALSIFIED = "falsified"
    EXPIRED = "expired"


class AnnotationSlot(StrEnum):
    """第 31 条之一（R4-01 改写）：Reinterpretation 注册制槽位。

    禁止自由槽名；新语义槽必须走第 72~76 条候选维度流程，防止维度爆炸
    （第 76 条）与标注语义泛化。
    """

    EMOTION = "emotion"
    MEANING = "meaning"
    IDENTITY_TAG = "identity_tag"


class UserReaction(StrEnum):
    """第 69 条：沟通经验记录的真实用户反应分类。"""

    ACCEPTED = "accepted"
    RESISTED = "resisted"
    IGNORED = "ignored"
    UNKNOWN = "unknown"


class BudgetScope(StrEnum):
    """第 86 条之一（R4-08）：预算作用域。"""

    TURN = "turn"
    DAY = "day"
    BACKGROUND_DAY = "background_day"
    MAINT_TASK = "maint_task"
    BAND_INGEST = "band_ingest"


class BudgetOnExceed(StrEnum):
    """超限处置策略（第 86 条之一）。安全通道不受预算豁免逻辑屏蔽。"""

    CHECKPOINT = "checkpoint"
    DEGRADE_RULES = "degrade_rules"
    DEFER_TO_IDLE = "defer_to_idle"
    HARD_DENY = "hard_deny"


class KnowledgeState(StrEnum):
    OBSERVED = "observed"
    REPORTED = "reported"
    INFERRED = "inferred"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class ClaimType(StrEnum):
    FACT = "fact"
    OPINION = "opinion"
    BELIEF = "belief"
    DESIRE = "desire"
    INTENTION = "intention"
    PLAN = "plan"
    PREDICTION = "prediction"
    PROMISE = "promise"
    PREFERENCE = "preference"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class EvidenceRole(StrEnum):
    SUPPORT = "support"
    COUNTER = "counter"
    CONTEXT = "context"


class EventStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    RESOLVED = "resolved"
    REVISED = "revised"
    REJECTED = "rejected"
    MERGED = "merged"
    SPLIT = "split"


class DimensionLifecycle(StrEnum):
    CANDIDATE = "candidate"
    TRIAL = "trial"
    ACTIVE = "active"
    LOW_ACTIVITY = "low_activity"
    DORMANT = "dormant"
    MERGED = "merged"
    SPLIT = "split"
    REVISED = "revised"
    REJECTED = "rejected"
    REACTIVATED = "reactivated"


class GoalStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class GoalSourceType(StrEnum):
    USER_EXPLICIT = "user_explicit"
    USER_INFERRED = "user_inferred"
    AI_SELF = "ai_self"
    APP = "app"
    EXTERNAL = "external"


class TaskType(StrEnum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    DEADLINE = "deadline"
    TODO = "todo"
    RECURRING = "recurring"
    FOLLOW_UP = "follow_up"
    OBSERVATION = "observation"
    VERIFICATION = "verification"
    MAINTENANCE = "maintenance"
    APP = "app"


class TaskState(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    WAITING_TIME = "waiting_time"
    WAITING_EVIDENCE = "waiting_evidence"
    WAITING_USER = "waiting_user"
    WAITING_RESULT = "waiting_result"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class WakeSource(StrEnum):
    MECHANICAL_CHANGE = "mechanical_change"
    KEYWORD_ENTITY = "keyword_entity"
    NO_UPDATE = "no_update"
    TASK_DUE = "task_due"
    WATCH_MATCH = "watch_match"
    USER_INTERACTION = "user_interaction"
    SAFETY = "safety"
    RECOVERY = "recovery"


class WakeState(StrEnum):
    NEW = "new"
    QUEUED = "queued"
    MERGED = "merged"
    RUNNING = "running"
    COMPLETED = "completed"
    SUPPRESSED = "suppressed"
    CANCELLED = "cancelled"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    CANCELLED = "cancelled"


class SummaryStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    PARTIAL = "partial"
    MISSING = "missing"


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"
    STALE_INDEX = "STALE_INDEX"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DEPENDENCY_INVALID = "DEPENDENCY_INVALID"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    STORAGE_FAILURE = "STORAGE_FAILURE"
