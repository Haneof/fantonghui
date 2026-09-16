"""AIOS 3.0 AI 世界操作原语与动作机制 (AI World Operations).

提供符合宪法第十七章、第二十章与第二十四章的六大结构化操作机制：
- TimeLensOperator: 5D时间镜头滑动与多尺度无损缩放
- DimensionLensOperator: 维度开闭聚焦与时空横向对齐共振
- WorldNavigator: 实体拓扑超链接跳步与事件链因果穿透
- EvidenceDrillDownOperator: 分层指针下钻与按需微切片展开 (Token极省)
- CognitionOperator: 历史不可变今天打标签与单跳隔离认知增量
- ConditionalTaskOperator: 条件驱动零浪费任务调度
"""

from .adaptive_temporal_compressor import (
    AdaptiveTemporalCompressionOperator,
    CompressedObservation,
    CompressionReceipt,
    RawSemanticClass,
    SensorModality,
    TemporalSample,
    adaptive_compression_tool_proposal,
)
from .world_operator import (
    CognitionOperator,
    ConditionalTaskOperator,
    DimensionLensOperator,
    EvidenceDrillDownOperator,
    MultidimensionalSearchOperator,
    ScaleLevel,
    TimeLensOperator,
    WorldNavigator,
    WorldOperatorSuite,
)

__all__ = [
    "AdaptiveTemporalCompressionOperator",
    "CognitionOperator",
    "CompressedObservation",
    "CompressionReceipt",
    "ConditionalTaskOperator",
    "DimensionLensOperator",
    "EvidenceDrillDownOperator",
    "MultidimensionalSearchOperator",
    "RawSemanticClass",
    "ScaleLevel",
    "SensorModality",
    "TemporalSample",
    "TimeLensOperator",
    "WorldNavigator",
    "WorldOperatorSuite",
    "adaptive_compression_tool_proposal",
]
