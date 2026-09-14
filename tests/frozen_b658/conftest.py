from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
os.environ["PYTHONPATH"] = str(ROOT / "src")
