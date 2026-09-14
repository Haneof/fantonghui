"""Dependency contract helpers.

M0 freezes explicit version-aware dependency edges plus deterministic in-memory
cycle/reverse-query helpers. Persistent reverse indexing and correction
propagation remain M3 work.
"""

from .graph import (
    collect_impacted_dependents,
    find_dependency_cycle,
    validate_dependency_graph_acyclic,
)

__all__ = [
    "collect_impacted_dependents",
    "find_dependency_cycle",
    "validate_dependency_graph_acyclic",
]
