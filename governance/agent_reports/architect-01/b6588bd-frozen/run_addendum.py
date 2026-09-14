from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys

out = Path(__file__).resolve().parent
source = out.parent / "xreview"
digests = {
    "test_redteam_b6588bd.py": "780cd8d978ec584faa7678dd98c0d3f4a9db2a18a05a82f019144c72f5885647",
    "test_quality_addendum_b6588bd.py": "ca6a49dcb648bda2593c3d79f489205cae928c72d5eceae88f276b29c612d641",
}
check = lambda: {name: hashlib.sha256((out/name).read_bytes()).hexdigest() for name in digests}
assert check() == digests
assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip() == "b6588bdaaa36d9dace4f9959dda0a89a370e1674"
records=[]
both = [str(out/name) for name in digests]
jobs = [
    ("combined-collect-only.log", ["--collect-only", "-vv", *both], False, False),
    ("combined-suite.log", ["-vv", "--tb=long", *both], False, False),
    ("formal-after-addendum.log", ["-vv", "tests"], False, False),
    ("reference-after-addendum.log", ["-vv", "aios_core_r2_reference/tests"], True, False),
    ("combined-suite-pydantic2106.log", ["-vv", *both], False, True),
]
for name,args,reference,alternate in jobs:
    src=source/("aios_core_r2_reference/src" if reference else "src")
    path=str(src)
    if alternate: path=str(out.parent/"pyd210")+os.pathsep+path
    env=os.environ | {"PYTHONPATH":path, "PYTHONDONTWRITEBYTECODE":"1"}
    cmd=[sys.executable,"-m","pytest","-o","addopts=","-o","pythonpath="+str(src),*args]
    before=check(); assert before==digests
    start=datetime.now(timezone.utc).isoformat()
    with (out/name).open("wb") as log:
        result=subprocess.run(cmd,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
    after=check(); assert after==digests
    records.append(dict(log=name,command=cmd,start=start,end=datetime.now(timezone.utc).isoformat(),
        exit_code=result.returncode,sha256_before=before,sha256_after=after))
    (out/"execution-addendum.json").write_text(json.dumps(records,indent=2)+"\n")
    print(name,result.returncode,flush=True)
    if name=="combined-collect-only.log" and result.returncode: raise SystemExit("Collection failure preserved")
assert subprocess.check_output(["git","status","--porcelain"],cwd=source,text=True)==""
