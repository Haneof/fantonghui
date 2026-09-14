"""Execute the frozen file against an unchanged checkout; retain all outputs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import pydantic
import pytest

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / "xreview"
CANDIDATE = "b6588bdaaa36d9dace4f9959dda0a89a370e1674"
EXPECTED = "780cd8d978ec584faa7678dd98c0d3f4a9db2a18a05a82f019144c72f5885647"
TEST = OUT / "test_redteam_b6588bd.py"
sha = lambda: hashlib.sha256(TEST.read_bytes()).hexdigest()
now = lambda: datetime.now(timezone.utc).isoformat()
assert sha() == EXPECTED
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
assert head == CANDIDATE
assert subprocess.check_output(["git", "status", "--porcelain"], cwd=SOURCE, text=True) == ""
(OUT / "candidate.txt").write_text(head + "\n", encoding="utf-8")
(OUT / "environment.txt").write_text(
    f"Python: {sys.version}\nExecutable: {sys.executable}\nPydantic: {pydantic.__version__}\n"
    f"pytest: {pytest.__version__}\nCandidate directory: {SOURCE}\n"
    f"Frozen SHA-256: {EXPECTED}\nStarted: {now()}\n", encoding="utf-8")
env = os.environ | {"PYTHONPATH": str(SOURCE / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
common = [sys.executable, "-m", "pytest", "-o", "addopts=", "-o", "pythonpath=" + str(SOURCE / "src")]
jobs = [
    ("collect-only.log", common + ["--collect-only", "-vv", str(TEST)]),
    ("redteam.log", common + ["-vv", "--tb=long", str(TEST)]),
    ("formal.log", common + ["-vv", "tests"]),
    ("reference.log", [sys.executable, "-m", "pytest", "-o", "addopts=", "-o",
        "pythonpath=" + str(SOURCE / "aios_core_r2_reference/src"), "-vv", "aios_core_r2_reference/tests"]),
]
records = []
for filename, command in jobs:
    before = sha()
    assert before == EXPECTED
    start = now()
    job_env = env if filename != "reference.log" else env | {"PYTHONPATH": str(SOURCE / "aios_core_r2_reference/src")}
    with (OUT / filename).open("wb") as log:
        result = subprocess.run(command, cwd=SOURCE, env=job_env, stdout=log, stderr=subprocess.STDOUT)
    after = sha()
    records.append(dict(log=filename, command=command, cwd=str(SOURCE), start=start, end=now(),
                        exit_code=result.returncode, test_sha256_before=before, test_sha256_after=after))
    (OUT / "execution.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    assert after == EXPECTED
    print(filename, "exit", result.returncode, flush=True)
    if filename == "collect-only.log" and result.returncode:
        raise SystemExit("Collection failed; test content remains frozen.")
assert subprocess.check_output(["git", "status", "--porcelain"], cwd=SOURCE, text=True) == ""
print("Frozen hash and candidate worktree unchanged.", flush=True)
