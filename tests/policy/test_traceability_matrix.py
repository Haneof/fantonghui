"""追溯矩阵守宪门（M0' 冻结门第③条 / M0-023 CONFLICT/UNMAPPED=0）。

薄封装 + 变异回归：真矩阵必须全绿；被注入违例的副本必须被抓红。
后者回答"这门是绿的会不会只是断言写空了"——与 test_policy_gate_regression
同一种执法机关自证品味。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "tools" / "governance" / "check_traceability.py"
MATRIX = REPO / "governance" / "traceability_matrix.csv"


def run(matrix: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--check", "--matrix", str(matrix)],
        cwd=REPO, capture_output=True, text=True,
    )


def test_real_matrix_is_green() -> None:
    r = run(MATRIX)
    assert r.returncode == 0, f"真矩阵被判红:\n{r.stderr or r.stdout}"
    assert "CONFLICT/UNMAPPED=0" in r.stdout


def _mutated_copy(transform) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="trace-mut-"))
    dst = tmp / "matrix.csv"
    text = MATRIX.read_text(encoding="utf-8")
    dst.write_text(transform(text), encoding="utf-8")
    return dst


def test_gate_catches_injected_unmapped() -> None:
    dst = _mutated_copy(lambda t: t.replace("philosophy", "UNMAPPED", 1))
    try:
        r = run(dst)
        assert r.returncode == 1 and "UNMAPPED" in r.stderr
    finally:
        shutil.rmtree(dst.parent, ignore_errors=True)


def test_gate_catches_ghost_world_object() -> None:
    dst = _mutated_copy(lambda t: t.replace("Claim", "GhostObject", 1))
    try:
        r = run(dst)
        assert r.returncode == 1 and "GhostObject" in r.stderr
    finally:
        shutil.rmtree(dst.parent, ignore_errors=True)


def test_gate_catches_deleted_v_band_row() -> None:
    """删掉所有含 V45 的行——中试带覆盖缺口必须被抓（G1 场景带纪律）。"""
    lines = MATRIX.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if "V45" not in ln or ln.startswith("stable_key")]
    assert len(kept) < len(lines), "矩阵里居然没有 V45 行可删（预条件失败）"
    tmp = Path(tempfile.mkdtemp(prefix="trace-mut-"))
    dst = tmp / "matrix.csv"
    dst.write_text("".join(kept), encoding="utf-8")
    try:
        r = run(dst)
        assert r.returncode == 1 and ("V45" in r.stderr or "V21~V45" in r.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}", file=sys.stderr)
    sys.exit(1 if failed else 0)
