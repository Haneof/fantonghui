"""调度域：条件驱动任务调度的双轨引擎（M2-005R）。

公开契约见 :mod:`aios_core.scheduler.conditional_engine`。
"""

from .conditional_engine import (
    LEVEL1_MECHANICAL_BUDGET_MS,
    MECHANICAL_CONDITION_KINDS,
    BoardAssembly,
    BoardEntry,
    Condition,
    ConditionKind,
    ConditionalTask,
    ConditionalTaskScheduler,
    DormantInvisibilityGuard,
    DormantVisibilityLeakError,
    EvaluationTier,
    FastTrackReport,
    GeoPosition,
    IllegalStateTransitionError,
    Level1FastTrack,
    MechanicalSignal,
    OpportunisticPiggyback,
    PiggybackReport,
    TaskState,
    TaskStateMachine,
    VitalSnapshot,
    WakeContext,
)

__all__ = [
    "LEVEL1_MECHANICAL_BUDGET_MS",
    "MECHANICAL_CONDITION_KINDS",
    "BoardAssembly",
    "BoardEntry",
    "Condition",
    "ConditionKind",
    "ConditionalTask",
    "ConditionalTaskScheduler",
    "DormantInvisibilityGuard",
    "DormantVisibilityLeakError",
    "EvaluationTier",
    "FastTrackReport",
    "GeoPosition",
    "IllegalStateTransitionError",
    "Level1FastTrack",
    "MechanicalSignal",
    "OpportunisticPiggyback",
    "PiggybackReport",
    "TaskState",
    "TaskStateMachine",
    "VitalSnapshot",
    "WakeContext",
]
