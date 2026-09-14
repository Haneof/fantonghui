"""Supplementary observations, separately hashed before execution.
Does not change or replace the frozen 394 tests and does not assert bug outcomes.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from test_adversarial_b658 import (
    ObjectRef, SourceRef, at, seeded, state, SQLiteWorldStore,
)
from aios_core.storage.idempotency import request_fingerprint


def captured(call):
    try:
        value = call()
        return {'returned': value.model_dump() if hasattr(value,'model_dump') else value}
    except Exception as e:
        return {'exception':type(e).__name__, 'code':getattr(e,'code',None),
                'context':getattr(e,'context',None), 'message':str(e)}


def call_record(store, obj, req):
    before = state(store)
    result = captured(lambda: store.commit([obj],req))
    after = state(store)
    result.update(world_before=before[0], world_after=after[0], rows_unchanged=before==after,
                  before_sha256=hashlib.sha256(repr(before).encode()).hexdigest(),
                  after_sha256=hashlib.sha256(repr(after).encode()).hexdigest())
    return result


if len(sys.argv)>1 and sys.argv[1]=='legacy-seed':
    store = seeded(Path(sys.argv[2]))
    ref = ObjectRef(object_id='anchor',revision=1)
    obj,req = at('value',ref if sys.argv[3]=='typed' else ref.model_dump())
    store.commit([obj],req)
    print('legacy created')
    raise SystemExit

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    out = {'frozen_suite_modified':False}
    legacy_source = Path(sys.argv[1]).resolve()
    legacy_results = {}
    for mode in ('typed','opaque'):
        path = tmp/(mode+'.db')
        env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(legacy_source/'src'))
        child = subprocess.run([sys.executable,__file__,'legacy-seed',str(path),mode],env=env,capture_output=True,text=True)
        if child.returncode:
            raise RuntimeError(child.stderr)
        store = SQLiteWorldStore(path)
        ref = ObjectRef(object_id='anchor',revision=1)
        obj,req = at('value',ref.model_dump())
        legacy_results[mode] = {'durable_value':store.get_payload('holder')['value'],
                              'opaque_retry':call_record(store,obj,req)}
    out['actual_524_legacy_database'] = legacy_results
    out['unknown_field_controls'] = {}
    for target in ('world','operation','ObjectRef','SourceRef'):
        store = seeded(tmp/(target+'.db'))
        obj,req = at('value','safe')
        if target=='world':
            dirty = obj.model_copy(update={'_rogue':'payload'}); obj=dirty
        elif target=='operation':
            dirty = req.model_copy(update={'_rogue':'payload'}); req=dirty
        else:
            ref_cls = ObjectRef if target=='ObjectRef' else SourceRef
            dirty = ref_cls(object_id='anchor',revision=1).model_copy(update={'_rogue':'payload'})
            obj,req = at('metadata',dirty)
        out['unknown_field_controls'][target] = {
            'declared_private_attributes':list(type(dirty).__private_attributes__),
            'unknown_in_instance_dict':'_rogue' in vars(dirty),
            'canonical_validation':captured(lambda:type(dirty).model_validate(dict(vars(dirty)))),
            'store':call_record(store,obj,req),
        }
    store = seeded(tmp/'unordered.db')
    obj,req = at('value',{'unordered':frozenset({'alpha','beta'})})
    first_fp = request_fingerprint(req,[obj])
    first = call_record(store,obj,req)
    normal = store.get_payload('holder')['value']
    changed,req2 = at('value',normal)
    out['durable_normal_form'] = {'first':first,'durable_value':normal,
        'original_fingerprint':first_fp,'durable_form_fingerprint':request_fingerprint(req2,[changed]),
        'normal_form_retry':call_record(SQLiteWorldStore(store.db_path),changed,req2)}
    print(json.dumps(out,indent=2,ensure_ascii=True))
