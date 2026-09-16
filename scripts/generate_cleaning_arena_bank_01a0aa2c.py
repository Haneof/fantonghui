#!/usr/bin/env python3
"""AIOS 清洗竞技场 · 09 号战队题库生成入口（全人生谱系高熵出卷官）。

等价于 ``python -m aios_core.simulation.cleaning_arena_generator_01a0aa2c``，仅做路径与提示包装。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.simulation.cleaning_arena_generator_01a0aa2c import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
