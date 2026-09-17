"""Controlled state-write capabilities for the R5 Executive Plane.

The model may *propose* structured state changes through these capabilities. Durable
stores enforce append-only versions, evidence requirements and R6 mutation authority;
the model never receives a raw SQL/update/delete capability.
"""

from __future__ import annotations

from typing import Any, Iterable

from .ai_self_world import AISelfMemoryKind, AISelfMemoryRecord, AISelfWorldStoreV2
from .capabilities import CapabilityKind, CapabilityRegistry, CapabilitySpec
from .conversation_state import ConversationStateStore, ConversationWorkingState
from .policy_registry import CognitivePolicyRegistry, CognitivePolicyVersion


class RuntimeStateCapabilityBus:
    def __init__(
        self,
        *,
        conversation_states: ConversationStateStore,
        ai_self_world: AISelfWorldStoreV2,
        policies: CognitivePolicyRegistry,
    ) -> None:
        self.conversation_states = conversation_states
        self.ai_self_world = ai_self_world
        self.policies = policies

    @staticmethod
    def _tuple(values: Iterable[str] | None) -> tuple[str, ...]:
        return tuple(values or ())

    def update_conversation_state(
        self,
        session_id: str,
        *,
        expected_version: int,
        current_topic: str | None = None,
        topic_branches: list[str] | None = None,
        open_loops: list[str] | None = None,
        unresolved_questions: list[str] | None = None,
        commitments: list[str] | None = None,
        key_turn_refs: list[str] | None = None,
        relevant_entity_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        latest = self.conversation_states.latest(session_id)
        durable_version = latest.version if latest is not None else 0
        if int(expected_version) != durable_version:
            raise ValueError(
                f"stale conversation state: expected_version={expected_version}, durable={durable_version}"
            )
        state = ConversationWorkingState(
            session_id=session_id,
            version=durable_version + 1,
            supersedes_version=durable_version if durable_version else None,
            current_topic=current_topic,
            topic_branches=self._tuple(topic_branches),
            open_loops=self._tuple(open_loops),
            unresolved_questions=self._tuple(unresolved_questions),
            commitments=self._tuple(commitments),
            key_turn_refs=self._tuple(key_turn_refs),
            relevant_entity_refs=self._tuple(relevant_entity_refs),
            evidence_refs=self._tuple(evidence_refs),
        )
        self.conversation_states.append(state)
        return state.model_dump(mode="json")

    def record_ai_self_memory(
        self,
        memory_key: str,
        kind: str,
        statement: str,
        *,
        expected_version: int,
        evidence_refs: list[str] | None = None,
        structured_data: dict[str, Any] | None = None,
        retracted: bool = False,
        retraction_reason: str | None = None,
    ) -> dict[str, Any]:
        parsed_kind = AISelfMemoryKind(kind)
        latest = self.ai_self_world.latest(memory_key)
        durable_version = latest.version if latest is not None else 0
        if int(expected_version) != durable_version:
            raise ValueError(
                f"stale AI self memory: expected_version={expected_version}, durable={durable_version}"
            )
        record = AISelfMemoryRecord.create(
            memory_key=memory_key,
            version=durable_version + 1,
            kind=parsed_kind,
            statement=statement,
            structured_data=structured_data,
            evidence_refs=self._tuple(evidence_refs),
            previous_record_id=latest.record_id if latest is not None else None,
            retracted=retracted,
            retraction_reason=retraction_reason,
        )
        self.ai_self_world.append(record)
        return record.model_dump(mode="json")

    def update_cognitive_policy(
        self,
        policy_id: str,
        *,
        expected_version: int,
        current_value: Any,
        reason: str,
        evidence_refs: list[str],
        changed_by: str = "ai_runtime",
    ) -> dict[str, Any]:
        current = self.policies.latest(policy_id)
        if current is None:
            raise KeyError(f"policy is not registered: {policy_id}")
        if int(expected_version) != current.version:
            raise ValueError(
                f"stale policy: expected_version={expected_version}, durable={current.version}"
            )
        next_version = CognitivePolicyVersion(
            policy_id=current.policy_id,
            scope=current.scope,
            policy_class=current.policy_class,
            default_value=current.default_value,
            current_value=current_value,
            allowed_range_or_choices=current.allowed_range_or_choices,
            mutable_by_ai=current.mutable_by_ai,
            reason=reason,
            evidence_refs=tuple(evidence_refs),
            changed_by=changed_by,
            version=current.version + 1,
            previous_version=current.version,
            evaluation_window=current.evaluation_window,
        )
        self.policies.append(next_version, actor_is_ai=True)
        return next_version.model_dump(mode="json")

    def register_capabilities(self, registry: CapabilityRegistry) -> None:
        registry.register(
            CapabilitySpec(
                name="update_conversation_state",
                description=(
                    "Append a new Conversation Working State version. Use only when the turn "
                    "creates useful topic/open-loop/commitment state; raw turns remain separate."
                ),
                kind=CapabilityKind.WRITE,
                side_effecting=True,
                input_schema={
                    "session_id": "string",
                    "expected_version": "int",
                    "current_topic": "string?",
                    "topic_branches": "string[]?",
                    "open_loops": "string[]?",
                    "unresolved_questions": "string[]?",
                    "commitments": "string[]?",
                    "key_turn_refs": "string[]?",
                    "relevant_entity_refs": "string[]?",
                    "evidence_refs": "string[]?",
                },
            ),
            self.update_conversation_state,
        )
        registry.register(
            CapabilitySpec(
                name="record_ai_self_memory",
                description=(
                    "Append evidence-linked AI self understanding/reflection/commitment. "
                    "Do not encode relationship meaning as an arbitrary score."
                ),
                kind=CapabilityKind.WRITE,
                side_effecting=True,
                input_schema={
                    "memory_key": "string",
                    "kind": "AISelfMemoryKind",
                    "statement": "string",
                    "expected_version": "int",
                    "evidence_refs": "string[]?",
                    "structured_data": "object?",
                    "retracted": "bool?",
                    "retraction_reason": "string?",
                },
            ),
            self.record_ai_self_memory,
        )
        registry.register(
            CapabilitySpec(
                name="update_cognitive_policy",
                description=(
                    "Append an evidence-backed value version to an already registered R6 "
                    "cognitive policy. Cannot create authority or alter hard-boundary class."
                ),
                kind=CapabilityKind.WRITE,
                side_effecting=True,
                input_schema={
                    "policy_id": "string",
                    "expected_version": "int",
                    "current_value": "any",
                    "reason": "string",
                    "evidence_refs": "string[]",
                },
            ),
            self.update_cognitive_policy,
        )
