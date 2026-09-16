"""AIOS 认知子系统。

本会话（_independent2 系）交付 M5 面：检索经验蒸馏、维度生命周期、
人设镜面、共生决策。与同目录其他席位的并行实现（operation_experience.py /
dimension_engine.py / self_reflection.py）独立共存，互不覆盖。
"""

from aios_core.cognition.operation_experience_independent2 import (
    CorpusDoc,
    GoldenExperience,
    InsufficientEvidenceError,
    OperationExperienceDistiller,
    PathwayBenchmarkReport,
    PathwayId,
    RetrievalPathwayComparator,
)
from aios_core.cognition.dimension_engine_independent2 import (
    AnomalyChain,
    AnomalyObservation,
    CrossDimensionalAnomalyDetector,
    DimensionGateRejection,
    DimensionLifecycleEngine,
    DimensionState,
    Domain,
    HighOrderDimensionDistiller,
    QuotaExceededBlockError,
    RegistrationLockedError,
)
from aios_core.cognition.self_reflection_independent2 import (
    BootHaltError,
    DynamicRapportModel,
    EventClass,
    HumanlikeResponsePostureDecider,
    PostureDecision,
    RapportStage,
    RapportViolationError,
    ResponsePosture,
    SelfIdentityMirror,
    UrgencyLevel,
)
from aios_core.cognition.symbiotic_advisor_independent2 import (
    ActionableAdvice,
    EvidenceLedger,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    MomBirthdayGiftAdvisor,
    ObjectRef,
    SymbioticAdvisor,
    UnfoundedFabricationError,
)

__all__ = [
    "ActionableAdvice",
    "AnomalyChain",
    "AnomalyObservation",
    "BootHaltError",
    "CorpusDoc",
    "CrossDimensionalAnomalyDetector",
    "DimensionGateRejection",
    "DimensionLifecycleEngine",
    "DimensionState",
    "Domain",
    "DynamicRapportModel",
    "EventClass",
    "EvidenceLedger",
    "FraudPreventionAdvisor",
    "GoldenExperience",
    "HealthFatigueBreakerAdvisor",
    "HighOrderDimensionDistiller",
    "HumanlikeResponsePostureDecider",
    "InsufficientEvidenceError",
    "MomBirthdayGiftAdvisor",
    "ObjectRef",
    "OperationExperienceDistiller",
    "PathwayBenchmarkReport",
    "PathwayId",
    "PostureDecision",
    "QuotaExceededBlockError",
    "RapportStage",
    "RapportViolationError",
    "RegistrationLockedError",
    "ResponsePosture",
    "RetrievalPathwayComparator",
    "SelfIdentityMirror",
    "SymbioticAdvisor",
    "UnfoundedFabricationError",
    "UrgencyLevel",
]
