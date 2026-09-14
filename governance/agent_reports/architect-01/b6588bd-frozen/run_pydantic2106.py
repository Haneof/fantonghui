"""Supplemental dependency-version run; uses the identical frozen test file."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys

out = Path(__file__).resolve().parent
source = out.parent / "xreview"
dependency = out.parent / "pyd210"
expected = "780cd8d978ec584faa7678dd98c0d3f4a9db2a18a05a82f019144c72f5885647"
digest = lambda: hashlib.sha256((out / "test_redteam_b6588bd.py").read_bytes()).hexdigest()
assert digest() == expected
env = os.environ | {"PYTHONPATH": str(dependency) + os.pathsep + str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
version = subprocess.check_output([sys.executable, "-c", "import sys,pydantic,pytest;print(sys.version);print('Pydantic',pydantic.__version__);print('pytest',pytest.__version__);assert pydantic.__version__=='2.10.6'"], env=env, text=True)
(out / "environment-pydantic2106.txt").write_text(version, encoding="utf-8")
records = []
for name, target, reference in [
    ("redteam-pydantic2106.log", str(out / "test_redteam_b6588bd.py"), False),
    ("formal-pydantic2106.log", "tests", False),
    ("reference-pydantic2106.log", "aios_core_r2_reference/tests", True),
]:
    src = source / ("aios_core_r2_reference/src" if reference else "src")
    job_env = env | {"PYTHONPATH": str(dependency) + os.pathsep + str(src)}
    cmd = [sys.executable, "-m", "pytest", "-o", "addopts=", "-o", "pythonpath=" + str(src), "-vv", target]
    assert digest() == expected
    start = datetime.now(timezone.utc).isoformat()
    with (out / name).open("wb") as log:
        result = subprocess.run(cmd, cwd=source, env=job_env, stdout=log, stderr=subprocess.STDOUT)
    assert digest() == expected
    records.append(dict(log=name, start=start, end=datetime.now(timezone.utc).isoformat(),
                        command=cmd, exit_code=result.returncode, test_sha256_before=expected,
                        test_sha256_after=digest()))
    (out / "execution-pydantic2106.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(name, result.returncode, flush=True)
