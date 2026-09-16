"""Simulation - 无界面高熵多维人生仿真推演（SIM-001）。

纯 Python、零 UI、可在无图形 Linux 服务器上持续跑批，为 AIOS 提供
海量真实压力测试：720 小时时空流 -> C01 边缘清洗 -> C06 倒排求交 ->
C02 账本持久化 -> C04 单看板装配 -> C05 回溯注记，全程 0 死锁、
内存平稳、原始二进制图片零滞留、Token 总量受控于月度预算。
"""

from .headless_life_driver import (
    HeadlessLifeDriver,
    InvertedIntersectionIndex,
    LifeStreamGenerator,
    SimConfig,
    SimulationReport,
    TOTAL_HOURS,
)

__all__ = [
    "HeadlessLifeDriver",
    "InvertedIntersectionIndex",
    "LifeStreamGenerator",
    "SimConfig",
    "SimulationReport",
    "TOTAL_HOURS",
]
