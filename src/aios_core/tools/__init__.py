"""AIOS 自研新工具/算子层。"""

from aios_core.tools.adaptive_time_series_compressor import (
    AdaptiveTimeSeriesCompressor,
    CompressionReport,
    WaveformSample,
)
from aios_core.tools.dual_lens_virtual_index import (
    AnnotationOverlay,
    AsKnownLens,
    DualLensVirtualIndexProjector,
    RegistryImmutableViolationError,
)

__all__ = [
    "AdaptiveTimeSeriesCompressor",
    "AnnotationOverlay",
    "AsKnownLens",
    "CompressionReport",
    "DualLensVirtualIndexProjector",
    "RegistryImmutableViolationError",
    "WaveformSample",
]
