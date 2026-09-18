"""AI Worker public surface.

R5/R6 primary execution path:
- CognitiveExecutor -> CognitiveRuntime -> CapabilityRegistry/WorldCapabilityBus.

Legacy one-shot cockpit components remain importable from their explicit modules
for migration only, but are intentionally not re-exported here as the default worker.
"""

from .cognitive_executor import (
    CognitiveExecutionResult,
    CognitiveExecutor,
    ModelDirective,
    WorldStorePort,
)
from .context_pipeline import AssembledContext, ContextAssemblyPipeline
from .manifest_optimizer import CockpitManifest, CockpitManifestOptimizer
from .stream_pipeline import (
    ActiveRollingWindow,
    ExtractedClaimCandidate,
    ProactiveAssociativeRecall,
    StreamingExtractWorker,
    ThreeStageStreamPipeline,
)

__all__ = [
    "ActiveRollingWindow",
    "AssembledContext",
    "CognitiveExecutionResult",
    "CognitiveExecutor",
    "CockpitManifest",
    "CockpitManifestOptimizer",
    "ContextAssemblyPipeline",
    "ExtractedClaimCandidate",
    "ModelDirective",
    "ProactiveAssociativeRecall",
    "StreamingExtractWorker",
    "ThreeStageStreamPipeline",
    "WorldStorePort",
]
