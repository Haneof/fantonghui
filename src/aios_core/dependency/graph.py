from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

from aios_core.contracts.models import Dependency
from aios_core.contracts.refs import ObjectRef

RefKey = tuple[str, int]


def _ref_key(ref: ObjectRef) -> RefKey:
    if ref.revision is None:
        raise ValueError("dependency graph requires pinned ObjectRef revisions")
    return (ref.object_id, ref.revision)


def find_dependency_cycle(
    dependencies: Iterable[Dependency],
) -> tuple[ObjectRef, ...] | None:
    """Return one exact-version Dependency cycle, or None when acyclic.

    This helper operates only on explicit Dependency records. Ordinary semantic
    Relation edges are intentionally outside this graph and may contain cycles.
    """

    adjacency: dict[RefKey, list[RefKey]] = defaultdict(list)
    refs: dict[RefKey, ObjectRef] = {}

    for edge in dependencies:
        dependent_key = _ref_key(edge.dependent_ref)
        dependency_key = _ref_key(edge.dependency_ref)
        adjacency[dependent_key].append(dependency_key)
        refs.setdefault(dependent_key, edge.dependent_ref)
        refs.setdefault(dependency_key, edge.dependency_ref)

    state: dict[RefKey, int] = {}
    stack: list[RefKey] = []
    stack_index: dict[RefKey, int] = {}

    def visit(node: RefKey) -> tuple[ObjectRef, ...] | None:
        state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)

        for next_node in adjacency.get(node, ()):
            next_state = state.get(next_node, 0)
            if next_state == 0:
                cycle = visit(next_node)
                if cycle is not None:
                    return cycle
            elif next_state == 1:
                start = stack_index[next_node]
                cycle_keys = stack[start:] + [next_node]
                return tuple(refs[key] for key in cycle_keys)

        stack.pop()
        stack_index.pop(node, None)
        state[node] = 2
        return None

    for node in sorted(refs):
        if state.get(node, 0) == 0:
            cycle = visit(node)
            if cycle is not None:
                return cycle
    return None


def validate_dependency_graph_acyclic(
    dependencies: Iterable[Dependency],
) -> None:
    """Reject a supplied proof/dependency graph when it contains a cycle."""

    cycle = find_dependency_cycle(dependencies)
    if cycle is None:
        return
    rendered = " -> ".join(
        f"{ref.object_id}@{ref.revision}" for ref in cycle
    )
    raise ValueError(f"dependency graph contains cycle: {rendered}")


def collect_impacted_dependents(
    dependencies: Iterable[Dependency],
    changed_ref: ObjectRef,
    *,
    transitive: bool = True,
) -> tuple[ObjectRef, ...]:
    """Reverse-scan Dependency records for objects affected by one exact revision.

    This is a deterministic in-memory contract helper, not the M3 persistent
    reverse index or automatic correction-propagation runtime.
    """

    changed_key = _ref_key(changed_ref)
    reverse: dict[RefKey, list[RefKey]] = defaultdict(list)
    refs: dict[RefKey, ObjectRef] = {changed_key: changed_ref}

    for edge in dependencies:
        dependent_key = _ref_key(edge.dependent_ref)
        dependency_key = _ref_key(edge.dependency_ref)
        reverse[dependency_key].append(dependent_key)
        refs.setdefault(dependent_key, edge.dependent_ref)
        refs.setdefault(dependency_key, edge.dependency_ref)

    for values in reverse.values():
        values.sort()

    queue: deque[RefKey] = deque([changed_key])
    visited: set[RefKey] = {changed_key}
    impacted: list[ObjectRef] = []

    while queue:
        current = queue.popleft()
        for dependent_key in reverse.get(current, ()):
            if dependent_key in visited:
                continue
            visited.add(dependent_key)
            impacted.append(refs[dependent_key])
            if transitive:
                queue.append(dependent_key)

    return tuple(impacted)
