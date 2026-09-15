"""V3.0.1 extension enums (freeze-line: CONST-V3.0.1 / M0').

These enums extend the R2 frozen surface WITHOUT mutating it. The R2 M0 gate
keeps its snapshot (schemas/r2/m0_contract_snapshot.json) byte-identical;
the M0' freeze is tracked by schemas/v3p1/m0p_contract_snapshot.json.

Stable-key anchors (ADJ-011): see governance/traceability_matrix.csv.
"""

from __future__ import annotations

from enum import StrEnum


class ObjectTypeV3(StrEnum):
    """First-class object types registered by the V3.0.1 contract patch.

    Parallel to (never overlapping) the R2 ``ObjectType`` namespace; both are
    serialized as bare strings in durable rows.
    """

    PREDICTION = "prediction"
    LIFE_CHAPTER = "life_chapter"
    COMMUNICATION_EXPERIENCE = "communication_experience"
    RETROSPECTIVE_ANNOTATION = "retrospective_annotation"
    TRIGGER_EXPRESSION = "trigger_expression"
    CONVERSATION_TURN = "conversation_turn"
    EXTRACTION_JOB = "extraction_job"
    MANIFEST_INSTANCE = "manifest_instance"
    NOTIFICATION_RECEIPT = "notification_receipt"
    RETENTION_TOMBSTONE = "retention_tombstone"
    DELETION_LOG = "deletion_log"
    BUDGET_LEDGER_ENTRY = "budget_ledger_entry"
    INVALIDATION_EPOCH = "invalidation_epoch"
    SPEAKER_CLUSTER = "speaker_cluster"


class TaskTypeV3(StrEnum):
    PREDICTION_CHECK = "prediction_check"
    SEMANTIC_REVIEW = "semantic_review"


class WakeSourceV3(StrEnum):
    RELATION_RHYTHM = "relation_rhythm"
    SEMANTIC_REVIEW = "semantic_review"
    INVALIDATION_REVIEW = "invalidation_review"


class PredictionStatus(StrEnum):
    PENDING = "pending"
    SUPPORTED = "supported"
    FALSIFIED = "falsified"
    INCONCLUSIVE = "inconclusive"
    EXPIRED = "expired"


class LifeChapterStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    ARCHIVED = "archived"
    REVISED = "revised"
    REJECTED = "rejected"


class TriState(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class TriggerOp(StrEnum):
    ATOM = "atom"
    ALL_OF = "all_of"
    ANY_OF = "any_of"
    NOT = "not"


class OutcomeDelivery(StrEnum):
    """投放回执分型（第 97 条 / ADJ-007）：无回应绝不等于拒绝。"""

    UNKNOWN = "unknown"
    DELIVERED = "delivered"
    SEEN = "seen"
    IGNORED = "ignored"
    REFUSED = "refused"


class RetentionClass(StrEnum):
    """ADJ-004：吊销权外的永存类 vs 可吊销类。"""

    REVOCATION_FREE = "revocation_free"  # 对象版本链/被引用观测/DeletionLog：永存
    REVOCABLE_RAW = "revocable_raw"  # 原始波形/图像/冗余副本：两阶段可吊销
    EPHEMERAL_SESSION = "ephemeral_session"  # 会话级缓存，TTL 硬上限


class TombstoneStage(StrEnum):
    STAGE1_SOFT = "stage1_soft"  # 引用仍可解析到墓碑
    STAGE2_SHREDDED = "stage2_shredded"  # 物理粉碎完成（不可逆终态）


class SpeakerClusterStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    TOMBSTONE = "tombstone"


class EpochState(StrEnum):
    DRAFT = "draft"
    MARKING = "marking"
    BUDGETED_REVIEW = "budgeted_review"
    CONTINUATION = "continuation"
    DONE = "done"
    QUARANTINED_PARTIAL = "quarantined_partial"


class TrustLane(StrEnum):
    """ADJ-004/M0-030：数据内容永不携带指令权。"""

    INSTRUCTION = "instruction"  # 系统/开发者指令道
    USER_DIALOG = "user_dialog"  # 用户对话道（可声明事实，不可注入指令）
    DATA = "data"  # OCR/群聊/字幕等纯数据道（一字不可为令）


class DepEdgeType(StrEnum):
    EVIDENCE_OF = "evidence_of"
    DERIVED_FROM = "derived_from"
    REVISION_OF = "revision_of"
    ENTITY_REF = "entity_ref"
    SUMMARY_OF = "summary_of"
    PREDICTION_CHECK = "prediction_check"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    SPANNED = "spanned"
    EXTRACTED = "extracted"
    SKIPPED = "skipped"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMMITTED = "committed"
    DEAD_LETTER = "dead_letter"


class InteractionChannel(StrEnum):
    HAPTIC = "haptic"
    VISUAL_GLANCE = "visual_glance"
    PRIVATE_AUDIO = "private_audio"  # 骨传导/私密听音——必须有 epoch
    SPEAKER = "speaker"  # 外放——必须有 epoch


class VerbosityLevel(StrEnum):
    CONCISE = "concise"
    NORMAL = "normal"
    DETAILED = "detailed"


class BudgetLane(StrEnum):
    NOTIFY = "notify"
    INVESTIGATE = "investigate"
    CHAPTER = "chapter"
    REVIEW = "review"
    EXTRACTION = "extraction"


class ManifestLane(StrEnum):
    NOTIFY = "notify"
    INVESTIGATE = "investigate"
    CHAPTER = "chapter"


class SafetyVerdict(StrEnum):
    OK = "ok"
    QUIET = "quiet"
    HARD_BLOCK = "hard_block"


class ProvenanceClass(StrEnum):
    """A 模型 provenance 裁决（ADJ/M0-008 UPGRADE 的载体字段语义）。"""

    OBSERVATION = "observation"
    EXTERNAL = "external"
    INFERENCE = "inference"
    INTROSPECTION = "introspection"
