"""M0' contract snapshot gate (v3p1 extension surface).

The frozen snapshot ``schemas/v3p1/m0p_contract_snapshot.json`` pins the
v3.0.1 extension contracts (enums_v3, models_v3, state_machines_v3).
Any accidental drift of the new contracts fails this gate; intentional
changes require regenerating the snapshot via
``tools/governance/build_v3p1_snapshot.py --write`` and re-review.

The r2 frozen surface (``schemas/r2/m0_contract_snapshot.json``) is
*never* modified by M0' work; this gate also asserts that file is left
byte-identical to its committed digest during the M0' milestone by
simply not touching it — r2 has its own gate test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SNAPSHOT = REPO / "schemas" / "v3p1" / "m0p_contract_snapshot.json"
BUILDER = REPO / "tools" / "governance" / "build_v3p1_snapshot.py"

EXPECTED_TRANSITION_EDGES = {
    "prediction": 5,
    "life_chapter": 5,
    "epoch": 14,
    "speaker_cluster": 2,
    "tombstone": 1,
}


def test_snapshot_file_exists_and_is_parseable() -> None:
    assert SNAPSHOT.exists(), "schemas/v3p1/m0p_contract_snapshot.json missing"
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert data["gate_version"] == "M0P-V3.0.1"
    assert set(data.keys()) >= {"enums", "models", "transitions"}


def test_snapshot_matches_current_contracts() -> None:
    """Live contracts must hash-match the frozen v3p1 snapshot."""
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    assert result.returncode == 0, (
        "v3p1 snapshot drifted — regenerate via build_v3p1_snapshot.py --write "
        f"after review. stdout={result.stdout} stderr={result.stderr}"
    )


def test_frozen_transition_matrices_sizes() -> None:
    """Five state-machine matrices pinned at their M0' edge counts."""
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    transitions = data["transitions"]
    assert set(transitions.keys()) == set(EXPECTED_TRANSITION_EDGES)
    for name, expected_edges in EXPECTED_TRANSITION_EDGES.items():
        edges = sum(len(targets) for targets in transitions[name].values())
        assert edges == expected_edges, (
            f"{name}: {edges} edges != frozen {expected_edges}"
        )
