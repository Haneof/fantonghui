"""AIOS 3.0 全流程海量盲测基建（Massive Synthetic Life Bench）。

* :mod:`life_bench` —— 对抗性生命数据发生器 + 真值卷宗（对抗 Oracle）；
* :mod:`intake_pipeline` —— 阶段一百万级摄入清洗与边缘提纯；
* :mod:`press_harness` —— 8 大阶段一站式压测总编排与五大铁律审计。
"""

from aios_core.bench.intake_pipeline import (
    IntakeConfig,
    IntakeOutcome,
    RawIntakePipeline,
)
from aios_core.bench.life_bench import (
    BenchManifest,
    BenchWorld,
    MassiveLifeBench,
    RawSample,
)
from aios_core.bench.press_harness import PressConfig, PressReport, run_full_press

__all__ = [
    "RawSample",
    "BenchManifest",
    "BenchWorld",
    "MassiveLifeBench",
    "IntakeConfig",
    "IntakeOutcome",
    "RawIntakePipeline",
    "PressConfig",
    "PressReport",
    "run_full_press",
]
