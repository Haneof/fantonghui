"""八阶段盲测共享世界：一次真实构建，全部阶段在同一份不可变事实底座上验收。

纪律
----
* 原始数据只来自独立发生器 ``MassiveSyntheticLifeBench``（1,131,330 条）；
* 全部阶段走真实存储与真实引擎，本目录**不含任何 mock 数据**；
* 断言全部写在测试里，发生器与压测台内部零断言（禁止自编自答）；
* 存储 I/O 探针挂在 ``sqlite3`` 驱动层：压测台并不知道自己被测量，
  因此"哪条查询最烧 I/O"是外部仪器读出来的，不是自报的。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from aios_core.simulation.blind_bench_diagnostics import (
    IOAttribution,
    StorageIOProfiler,
    bottleneck_diagnosis,
    iron_rule_assertions,
)
from aios_core.simulation.blind_bench_harness import BenchRunResult, BlindBenchHarness

#: 默认跑满百万级；CI 需要降规模时用 ``AIOS_BLIND_BENCH_SCALE`` 覆盖。
DEFAULT_SCALE = float(os.environ.get("AIOS_BLIND_BENCH_SCALE", "1.0"))


@dataclass(frozen=True, slots=True)
class BenchSession:
    """一次会话级的盲测取证：结果 + I/O 归因 + 诊断结论（全部只读）。"""

    result: BenchRunResult
    attribution: IOAttribution
    diagnosis: dict

    @property
    def iron_rules(self):
        return iron_rule_assertions(self.result)


@pytest.fixture(scope="session")
def bench_session() -> BenchSession:
    profiler = StorageIOProfiler()
    harness = BlindBenchHarness(scale=DEFAULT_SCALE, seed=20260916)
    try:
        with profiler.install():
            result = harness.run()
        attribution = profiler.attribute(result.stage_marks)
        diagnosis = bottleneck_diagnosis(
            result, attribution, microbench=harness.operator_microbench(imu_samples=50_000)
        )
    finally:
        harness.close()
    return BenchSession(result=result, attribution=attribution, diagnosis=diagnosis)


@pytest.fixture(scope="session")
def bench_run(bench_session: BenchSession) -> BenchRunResult:
    """向后兼容：全部阶段测试直接拿盲测结果。"""

    return bench_session.result
