"""Summaries - 日/周/月/年多尺度总结与时间金字塔物化视图。

M1-010R 实现：``PyramidAggregator`` / ``TimePyramidSummary``。
宪法第二十五至二十七条铁律：总结绝不是压缩删除，原始证据永存，
物化视图只增不改，无损下钻。
"""
from .pyramid_aggregator import (
    CONTINUOUS_ZOOM_SECONDS,
    SCALE_ORDER,
    PyramidAggregator,
    PyramidError,
    TimePyramidSummary,
    finer_than,
)

__all__ = [
    "CONTINUOUS_ZOOM_SECONDS",
    "SCALE_ORDER",
    "PyramidAggregator",
    "PyramidError",
    "TimePyramidSummary",
    "finer_than",
]
