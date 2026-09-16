"""Ingest - 端侧多模态接入与边缘清洗层（M1-001R / M1-001R-ADV）。

- ``EdgeMultimodalCleaner`` / ``QualityGate``：画质 < 0.4 垃圾图坚决抛弃，
  达标图只产纯文本 Caption，原始字节零保留；
- ``RawByteSink``：原始字节暂存池，``purge`` 物理粉碎（保留量审计口径）；
- ``VoiceprintLSHIndex``：128 维声纹 LSH（24 人高密流聚类，区分核心伙伴/路人）；
- ``VoiceprintTTLRegistry`` / ``VoiceprintLifecycleManager``：180 天 TTL
  墓碑状态机（热表/归档区，背景声纹自然淘汰）。
"""
from .multimodal_edge import (
    FEATURE_DIM,
    EdgeMultimodalCleaner,
    ImageSemanticObservation,
    QualityGate,
    RawByteSink,
    VoiceprintLSHIndex,
    VoiceprintLifecycleManager,
    VoiceprintProfile,
    VoiceprintTTLRegistry,
    assess_image_quality,
)

__all__ = [
    "FEATURE_DIM",
    "EdgeMultimodalCleaner",
    "ImageSemanticObservation",
    "QualityGate",
    "RawByteSink",
    "VoiceprintLSHIndex",
    "VoiceprintLifecycleManager",
    "VoiceprintProfile",
    "VoiceprintTTLRegistry",
    "assess_image_quality",
]
