"""Registered AIOS tool proposals and executable pure-code mechanisms."""

from .adaptive_time_series_compressor import (
    AdaptiveTimeSeriesCompressor,
    CompressionReport,
    WaveformSample,
)
from .dual_lens_virtual_index import (
    AnnotationOverlay,
    AsKnownLens,
    DualLensVirtualIndexProjector,
    RegistryImmutableViolationError,
)
from .proposal_pipeline import ToolProposalPipeline

__all__ = [
    "AdaptiveTimeSeriesCompressor",
    "AnnotationOverlay",
    "AsKnownLens",
    "CompressionReport",
    "DualLensVirtualIndexProjector",
    "RegistryImmutableViolationError",
    "ToolProposalPipeline",
    "WaveformSample",
]
