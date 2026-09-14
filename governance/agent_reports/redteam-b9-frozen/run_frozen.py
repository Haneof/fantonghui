"""Collect and run immutable tests against an exact read-only candidate worktree."""
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

root=Path(__file__).resolve().parent
candidate=Path(sys.argv[1]).resolve()
out=root/'evidence'
out.mkdir(exist_ok=True)
freeze=json.loads((root/'TEST-FREEZE.json').read_text())
source=json.loads((root/'CANDIDATE-FREEZE.json').read_text())
def test_hashes():
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in freeze['tests']}
assert test_hashes()==freeze['tests']
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=candidate,text=True).strip()
assert head==freeze['candidate']==source['candidate']
assert sys.version_info[:3]==(3,12,14)
assert pydantic.__version__=='2.13.5'
assert pytest.__version__.startswith('8.')
for path,digest in source['source_sha256'].items():
    assert hashlib.sha256((candidate/path).read_bytes()).hexdigest()==digest
metadata={'candidate':head,'audit_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
          'python':sys.version,'pydantic':pydantic.__version__,'pytest':pytest.__version__,
          'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),
          'int_max_str_digits':sys.get_int_max_str_digits(),'test_hashes_before':test_hashes(),
          'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(out/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
subprocess.run([sys.executable,'-m','pip','freeze'],stdout=(out/'pip-freeze.txt').open('w'),check=True)
results={}
def run(name,args,pythonpath):
    cmd=[sys.executable,'-m','pytest',*args,'-o','pythonpath='+str(pythonpath),'-o','addopts=','-p','no:cacheprovider']
    env=dict(os.environ,PYTHONPATH=str(pythonpath),PYTHONDONTWRITEBYTECODE='1')
    with (out/(name+'.log')).open('w') as f:
        f.write('EXACT CANDIDATE: '+head+'\nCOMMAND: '+repr(cmd)+'\n');f.flush()
        result=subprocess.run(cmd,cwd=candidate,env=env,stdout=f,stderr=subprocess.STDOUT)
    results[name]=result.returncode
    assert test_hashes()==freeze['tests']
    print(name,'exit',result.returncode,flush=True)
run('collect-new',['--collect-only','-vv',str(root/'test_robustness_b9.py')],candidate/'src')
run('collect-regression',['--collect-only','-vv',str(root/'regression/test_adversarial_b658.py')],candidate/'src')
run('robustness',['-vv','--tb=short',str(root/'test_robustness_b9.py')],candidate/'src')
run('regression',['-vv','--tb=short',str(root/'regression/test_adversarial_b658.py')],candidate/'src')
run('formal',['-vv','--tb=short','tests'],candidate/'src')
reference=candidate/'aios_core_r2_reference'
run('reference',['-vv','--tb=short',str(reference/'tests')],reference/'src')
results.update(test_hashes_after=test_hashes(),unchanged_tests=test_hashes()==freeze['tests'],
               finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'exit-codes.json').write_text(json.dumps(results,indent=2)+'\n')
post={path:hashlib.sha256((candidate/path).read_bytes()).hexdigest() for path in source['source_sha256']}
(out/'source-integrity.json').write_text(json.dumps({'candidate':head,'source_files':len(post),'unchanged':post==source['source_sha256'],'worktree_status':subprocess.check_output(['git','status','--porcelain'],cwd=candidate,text=True)},indent=2)+'\n')
assert post==source['source_sha256']
# Preserve every log first; individual pytest exit codes remain explicit evidence.
