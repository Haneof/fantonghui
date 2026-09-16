"""M5 认知层：检索经验、维度演化、人设镜面、共生决策。"""

from .dimension_engine import (
    CrossDimensionalAnomalyDetector,
    DimensionEngine,
    HighOrderDimensionDistiller,
    TripleGateMachine,
)
from .operation_experience import (
    CAMPAIGN_TOKEN_BUDGET,
    DistilledExperience,
    DistillerNotReadyError,
    ExperienceDemotedError,
    OperationExperienceDistiller,
)
from .self_reflection import (
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
    RapportTier,
    ResponsePosture,
    SelfIdentityMirror,
)
from .symbiotic_advisor import (
    ActionableAdvice,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    MindEvidenceStore,
    MomBirthdayGiftAdvisor,
)

__all__ = [
    "CAMPAIGN_TOKEN_BUDGET",
    "ActionableAdvice",
    "CrossDimensionalAnomalyDetector",
    "DimensionEngine",
    "DistilledExperience",
    "DistillerNotReadyError",
    "DynamicRapportModel",
    "ExperienceDemotedError",
    "FraudPreventionAdvisor",
    "HealthFatigueBreakerAdvisor",
    "HighOrderDimensionDistiller",
    "HumanlikeResponsePostureDecider",
    "MindEvidenceStore",
    "MomBirthdayGiftAdvisor",
    "OperationExperienceDistiller",
    "RapportTier",
    "ResponsePosture",
    "SelfIdentityMirror",
    "TripleGateMachine",
]
