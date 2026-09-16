"""盲测相关测试的共享夹具。

八阶段盲测（含 1,147,788 条原始样本的全量流式摄入）单次约 21 秒，因此整条
流水线在 **session 作用域**里只跑一次，所有阶段的断言共享同一份真实产物 ——
既保证"跑的就是同一个世界"，也避免在 98 个测试文件里重复付出 20 秒成本。
"""

from __future__ import annotations

import pathlib

import pytest

from aios_core.bench.adversarial_life_bench import GATE_PROFILE
from aios_core.bench.blind_bench_harness import BlindBenchHarness


@pytest.fixture(scope="session")
def gate_harness(tmp_path_factory: pytest.TempPathFactory) -> BlindBenchHarness:
    """一次性跑完 S1~S8 的 GATE 档位盲测（真实数据、真实落库、真实断言）。"""

    workdir = pathlib.Path(tmp_path_factory.mktemp("blind_bench_gate"))
    harness = BlindBenchHarness(workdir=workdir, profile=GATE_PROFILE)
    harness.run_all()
    return harness
