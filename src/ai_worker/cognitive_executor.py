"""Primary AIOS R5/R6 session executor.

Unlike the legacy one-shot CockpitExecutor, this executor gives the model a bounded
capability loop over the World/Search plane plus controlled state-write capabilities.
The runtime decides only authorization/budgets/protocol; the model decides whether and
how to recall, compare, respond, stay silent, or write back learned state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from aios_core.runtime import (
    AISelfMemoryKind,
    AISelfWorldStoreV2,
    CapabilityRegistry,
    CognitivePolicyRegistry,
    CognitiveRuntime,
    ConversationStateStore,
    ConversationTimelineStore,
    ConversationTurn,
    ModelDirective,
    RuntimeTurnResult,
    WorldCapabilityBus,
)
from aios_core.runtime.cognitive_runtime import ModelHandler
from aios_core.runtime.state_capabilities import RuntimeStateCapabilityBus


class WorldStorePort(Protocol):
    """Public Core surface required by the Worker.

    The Worker deliberately depends on behavior instead of importing the storage
    implementation. Concrete store ownership remains inside Core.
    """

    db_path: str

    def current_world_revision(self) -> int: ...


@dataclass(frozen=True)
class CognitiveExecutionResult:
    runtime: RuntimeTurnResult
    raw_turn_ref: str
    conversation_state_version: int

    @property
    def response(self) -> str | None:
        return self.runtime.response

    @property
    def silenced(self) -> bool:
        return self.runtime.silenced


class CognitiveExecutor:
    """A durable session shell around the model-driven CognitiveRuntime."""

    _STATE_WRITE_CAPABILITIES = {
        "update_conversation_state",
        "record_ai_self_memory",
        "update_cognitive_policy",
    }

    def __init__(
        self,
        *,
        world_store: WorldStorePort,
        model_handler: ModelHandler,
        session_id: str,
        max_tool_rounds: int = 4,
        max_total_capability_calls: int = 12,
    ) -> None:
        if not session_id.strip():
            raise ValueError("session_id must be non-blank")
        self.world_store = world_store
        self.session_id = session_id
        self.timeline = ConversationTimelineStore(world_store.db_path)
        self.conversation_states = ConversationStateStore(world_store.db_path)
        self.ai_self_world = AISelfWorldStoreV2(world_store.db_path)
        self.policies = CognitivePolicyRegistry(world_store.db_path)

        self.registry = CapabilityRegistry()
        self.world_capabilities = WorldCapabilityBus(world_store)  # structural Core port
        self.world_capabilities.register_read_capabilities(self.registry)
        self.state_capabilities = RuntimeStateCapabilityBus(
            conversation_states=self.conversation_states,
            ai_self_world=self.ai_self_world,
            policies=self.policies,
        )
        self.state_capabilities.register_capabilities(self.registry)

        self.runtime = CognitiveRuntime(
            registry=self.registry,
            model_handler=model_handler,
            max_tool_rounds=max_tool_rounds,
            max_total_capability_calls=max_total_capability_calls,
            side_effect_authorizer=self._authorize_state_write,
        )

    def _authorize_state_write(self, spec, call, snapshot) -> bool:
        # This authorizer grants only the narrow structured runtime state writes
        # registered above. The handlers themselves still enforce evidence/version/R6.
        return spec.name in self._STATE_WRITE_CAPABILITIES

    def _next_turn_index(self) -> int:
        turns = self.timeline.list_turns(self.session_id, limit=1_000_000)
        return (turns[-1].turn_index + 1) if turns else 1

    def _minimal_cockpit(self, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        state = self.conversation_states.latest(self.session_id)
        identities = self.ai_self_world.latest_by_kind(AISelfMemoryKind.IDENTITY)
        relationships = self.ai_self_world.latest_by_kind(
            AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING
        )
        cockpit: dict[str, Any] = {
            "session_id": self.session_id,
            "world_revision": self.world_store.current_world_revision(),
            "conversation_working_state": (
                state.model_dump(mode="json") if state is not None else None
            ),
            "ai_self_identity": [item.model_dump(mode="json") for item in identities],
            "relationship_understanding": [
                item.model_dump(mode="json") for item in relationships
            ],
        }
        if extra:
            cockpit.update(dict(extra))
        return cockpit

    def execute_turn(
        self,
        user_input: str,
        *,
        wake_reason: str = "user_interaction",
        cockpit_extra: Mapping[str, Any] | None = None,
    ) -> CognitiveExecutionResult:
        result = self.runtime.run_turn(
            user_input,
            wake_reason=wake_reason,
            cockpit=self._minimal_cockpit(cockpit_extra),
        )

        # Raw dialogue is deterministic runtime bookkeeping, not a cognition decision.
        turn_index = self._next_turn_index()
        turn = ConversationTurn.create(
            session_id=self.session_id,
            turn_index=turn_index,
            user_text=user_input,
            assistant_text=result.response or "",
        )
        sealed = self.timeline.append(turn)
        state = self.conversation_states.latest(self.session_id)
        return CognitiveExecutionResult(
            runtime=result,
            raw_turn_ref=sealed.turn_id,
            conversation_state_version=state.version if state is not None else 0,
        )


__all__ = ["CognitiveExecutionResult", "CognitiveExecutor", "ModelDirective", "WorldStorePort"]
