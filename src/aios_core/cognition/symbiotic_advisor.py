"""Deprecated compatibility surface.

The historical hard-coded birthday/fraud/fatigue advisors were removed under the
R5/R6 cognitive-runtime realignment. This module contains no semantic decision
logic. New code should import from evidence_grounded_advisor directly.
"""

from aios_core.cognition.evidence_grounded_advisor import (
    AdviceDecisionKind,
    ModelAdviceDecision,
)

ActionableAdvice = ModelAdviceDecision

__all__ = [
    "ActionableAdvice",
    "AdviceDecisionKind",
    "ModelAdviceDecision",
]
