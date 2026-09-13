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
    REJECTED = "rejected"
    RETIRED = "retired"


class GoalStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"
    REJECTED = "rejected"


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
