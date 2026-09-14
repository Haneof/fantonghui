"""Evidence runner: does not edit tests or candidate, runs all suites even if red."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import pydantic
import pytest

root = Path(__file__).resolve().parent
candidate = Path(sys.argv[1]).resolve()
out = root / 'evidence' / ('pydantic-' + pydantic.__version__)
out.mkdir(parents=True, exist_ok=True)
test = root / 'test_adversarial_b658.py'
freeze = json.loads((root/'FREEZE.json').read_text())
sha = lambda: hashlib.sha256(test.read_bytes()).hexdigest()
assert sha() == freeze['sha256'], 'pre-run frozen test mismatch'
head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=candidate, text=True).strip()
assert head == freeze['candidate'], (head, freeze['candidate'])
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(candidate/'src'))
versions = dict(candidate_sha=head, python=sys.version, platform=platform.platform(),
                pydantic=pydantic.__version__, pytest=pytest.__version__, sqlite=sqlite3.sqlite_version,
                test_sha256_before=sha(), started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                audit_commit=os.environ.get('GITHUB_SHA'), github_run_id=os.environ.get('GITHUB_RUN_ID'),
                integer_digit_limit=sys.get_int_max_str_digits())
(out/'environment.json').write_text(json.dumps(versions,indent=2)+'\n')
subprocess.run([sys.executable,'-m','pip','freeze'],stdout=(out/'pip-freeze.txt').open('w'),check=True)
results = {}
def run(name, args, source):
    command = [sys.executable,'-m','pytest',*args,'-o','pythonpath='+str(source),'-o','addopts=','-p','no:cacheprovider']
    with (out/(name+'.log')).open('w') as log:
        log.write('COMMAND: '+repr(command)+'\nCANDIDATE: '+head+'\n'); log.flush()
        local = dict(env, PYTHONPATH=str(source))
        result = subprocess.run(command,cwd=candidate,env=local,stdout=log,stderr=subprocess.STDOUT)
    results[name] = result.returncode
    print(name, 'exit', result.returncode, flush=True)
run('collect-only',['--collect-only','-vv',str(test)],candidate/'src')
assert sha() == freeze['sha256'], 'post-collection frozen test mismatch'
run('redteam',['-vv','--tb=short',str(test)],candidate/'src')
run('formal',['-vv','--tb=short','tests'],candidate/'src')
reference = candidate/'aios_core_r2_reference'
run('reference',['-vv','--tb=short',str(reference/'tests')],reference/'src')
results['test_sha256_after'] = sha()
results['unchanged_test'] = sha() == freeze['sha256']
results['finished_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
(out/'exit-codes.json').write_text(json.dumps(results,indent=2)+'\n')
assert results['unchanged_test']
with (root/'SHA256SUMS').open('w') as f:
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name != 'SHA256SUMS' and '__pycache__' not in p.parts:
            f.write(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n')
# Workflow performs its explicit status check after preserving all evidence.
