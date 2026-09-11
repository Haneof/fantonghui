"""场景测试的公共入口:走完整的 Sprint 1 主链。

必须经过 Perception Runtime(09 禁止事项 5),因此这里只调用 player.run()。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.simulator.player import run  # noqa: E402

SCENARIO = ROOT / "adapters/simulator/negotiation_timeline.txt"


def play(var_dir, noise: int = 0, fresh: bool = True) -> dict:
    return run(SCENARIO, Path(var_dir), "2026-09-09", noise=noise, fresh=fresh)
