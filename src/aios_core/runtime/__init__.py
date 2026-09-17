"""AIOS 3.0 Executive Plane.

R5/R6 runtime package: deterministic code exposes reliable capabilities and
execution boundaries; the model remains the high-level cognitive driver.
"""

from .capabilities import (
    CapabilityCall,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
)
from .cognitive_runtime import (
    CognitiveRuntime,
    ModelDirective,
    RuntimeSnapshot,
    RuntimeTurnResult,
)

__all__ = [
    "CapabilityCall",
    "CapabilityRegistry",
    "CapabilityResult",
    "CapabilitySpec",
    "CognitiveRuntime",
    "ModelDirective",
    "RuntimeSnapshot",
    "RuntimeTurnResult",
]
