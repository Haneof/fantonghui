"""Ingest - 端侧多模态轻量化摄入（V3 §33：边缘轻量化，严禁高频灌水）。"""

from .multimodal_edge import (
    CAPTURE_PURGE_THRESHOLD,
    CaptureFrame,
    LSH_BAND_BITS,
    LSH_BANDS,
    VOICEPRINT_DIM,
    VOICEPRINT_MATCH_HAMMING,
    PurgeRecord,
    PurgeReport,
    RawByteSink,
    TTL_DAYS,
    TombstoneSweepReport,
    VoiceprintLSHEngine,
    VoiceprintObservation,
    VoiceprintRecord,
    VoiceprintTTLRegistry,
    assess_capture_quality,
)

__all__ = [
    "CAPTURE_PURGE_THRESHOLD",
    "CaptureFrame",
    "LSH_BAND_BITS",
    "LSH_BANDS",
    "VOICEPRINT_DIM",
    "VOICEPRINT_MATCH_HAMMING",
    "PurgeRecord",
    "PurgeReport",
    "RawByteSink",
    "TTL_DAYS",
    "TombstoneSweepReport",
    "VoiceprintLSHEngine",
    "VoiceprintObservation",
    "VoiceprintRecord",
    "VoiceprintTTLRegistry",
    "assess_capture_quality",
]
