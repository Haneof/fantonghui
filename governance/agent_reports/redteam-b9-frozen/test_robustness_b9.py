"""New black-box robustness gate, designed before inspecting b9 implementation.
All expectations are frozen before collection. No edits after observed outcomes.
This is not the unavailable 100-probe artifact. Corruption/fault fixtures affect
only per-test temporary SQLite databases, never candidate source or branches.
"""
import dataclasses
import json
import math
import sqlite3
from collections import ChainMap, UserList, deque, namedtuple
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest
from aios_core.contracts import (
    Observation, OperationRequest, ObjectRef, SourceRef, EvidenceSet, KnowledgeWindow,
)
from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.models import EvidenceSelector
from aios_core.contracts.time import TemporalExtent
from aios_core.storage import SQLiteWorldStore, StoreError

EXACT_SHA = 'b9b5921c3e31a40528b0b96e689ae721c334bd7c'
T = datetime(2026, 9, 14, 9, tzinfo=timezone.utc)
SLOTS = ('value', 'metadata', 'arguments', 'filters')
REFS = (ObjectRef, SourceRef)
TABLES = ('world_commits', 'object_revisions', 'operations', 'idempotency_records')


def base(oid, **kw):
    result = dict(object_id=oid, subject_id='robustness', learned_at=T,
                  recorded_at=T, created_by='new-black-box-review')
    result.update(kw)
    return result


def obj(oid='holder', **kw):
    return Observation(**base(oid, source_kind='audit', modality='json', **kw))


def req(key='case', revision=1, **kw):
    result = dict(operation_id='op-'+key, operation_name='world.commit',
                  expected_world_revision=revision, idempotency_key=key,
                  reason='frozen ordinary boundary review')
    result.update(kw)
    return OperationRequest(**result)


def snapshot(store):
    with sqlite3.connect(store.db_path) as c:
        world = int(c.execute("SELECT value FROM world_meta WHERE key='world_revision'").fetchone()[0])
        return (world,) + tuple(tuple(c.execute('SELECT * FROM '+t+' ORDER BY 1,2').fetchall()) for t in TABLES)


def rejected(store, objects, operation, codes):
    return rejected_call(store, lambda: store.commit(objects, operation), codes)


def rejected_call(store, call, codes):
    if isinstance(codes, ErrorCode): codes = {codes}
    before = snapshot(store)
    try:
        with pytest.raises(StoreError) as raised:
            call()
        assert raised.value.code in codes
    finally:
        assert snapshot(store) == before, 'failure path mutated world_revision or complete durable rows'


def exact_replay(store, objects, operation):
    before = snapshot(store)
    try:
        result = store.commit(objects, operation)
        assert result.idempotent_replay is True
        return result
    finally:
        assert snapshot(store) == before, 'replay changed complete durable state'


def seed(path):
    store = SQLiteWorldStore(path)
    store.commit([obj('anchor')], req('seed', revision=0))
    return store


def place(slot, payload):
    operation = req()
    if slot == 'value':
        item = obj(value=payload)
    elif slot == 'metadata':
        item = obj(metadata={'probe': payload})
    elif slot == 'arguments':
        item = obj()
        operation = req(arguments={'probe': payload})
    else:
        item = EvidenceSet(**base('holder', learned_at=T+timedelta(seconds=2), recorded_at=T+timedelta(seconds=2)),
            purpose='cutoff audit', knowledge_window=KnowledgeWindow(knowledge_cutoff=T, world_revision=1),
            member_refs=[ObjectRef(object_id='anchor', revision=1)], selection_method='explicit',
            selector=EvidenceSelector(selector_type='audit', subject_id='robustness',
                time_range=TemporalExtent.unknown_time(), algorithm_version='1', filters={'probe':payload}))
    return item, operation


def durable(store, slot):
    if slot == 'arguments':
        with sqlite3.connect(store.db_path) as c:
            return json.loads(c.execute("SELECT arguments_json FROM operations WHERE operation_id='op-case'").fetchone()[0])['probe']
    data = store.get_payload('holder')
    if slot == 'value': return data['value']
    if slot == 'metadata': return data['metadata']['probe']
    return data['selector']['filters']['probe']


@dataclasses.dataclass(frozen=True)
class Envelope:
    payload: object


Pair = namedtuple('Pair', ['payload'])
WRAPPERS = ('deque', 'dataclass', 'namedtuple', 'mapping-proxy', 'chainmap', 'userlist')


def wrapped(kind, value):
    if kind == 'deque': return deque([value])
    if kind == 'dataclass': return Envelope(payload=value)
    if kind == 'namedtuple': return Pair(payload=value)
    if kind == 'mapping-proxy': return MappingProxyType({'payload':value})
    if kind == 'chainmap': return ChainMap({'payload':value}, {})
    return UserList([value])


def plain(kind, value):
    return {'payload':value} if kind in ('dataclass','mapping-proxy','chainmap') else [value]


@pytest.mark.parametrize('kind', WRAPPERS)
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('slot', ('value','metadata','filters'))
def test_real_missing_refs_cannot_be_laundered_through_standard_wrappers(tmp_path, kind, ref_cls, slot):
    store = seed(tmp_path/'db')
    item, operation = place(slot, wrapped(kind, ref_cls(object_id='absent', revision=1)))
    # A container may be unsupported; accepting an unresolved real reference is not
    # an acceptable substitute for a controlled unsupported-container rejection.
    rejected(store, [item], operation, {ErrorCode.NOT_FOUND, ErrorCode.INVALID_ARGUMENT})


@pytest.mark.parametrize('kind', WRAPPERS)
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('slot', SLOTS)
def test_wrapped_typed_ref_does_not_alias_plain_json_on_restart(tmp_path, kind, ref_cls, slot):
    store = seed(tmp_path/'db')
    ref = ref_cls(object_id='anchor',revision=1)
    first, operation = place(slot, plain(kind, ref.model_dump(mode='python')))
    store.commit([first], operation)
    retry, altered_operation = place(slot, wrapped(kind, ref))
    rejected(SQLiteWorldStore(store.db_path), [retry], altered_operation, ErrorCode.IDEMPOTENCY_CONFLICT)
    exact_replay(SQLiteWorldStore(store.db_path), [first], operation)


@pytest.mark.parametrize('kind', ('deque','dataclass','namedtuple'))
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('slot', ('value','metadata'))
def test_accepted_wrapped_dirty_ref_is_canonical_not_a_string_revision(tmp_path, kind, ref_cls, slot):
    store = seed(tmp_path/'db')
    canonical = ref_cls(object_id='anchor',revision=1)
    dirty = canonical.model_copy(update={'revision':'1'})
    item, operation = place(slot, wrapped(kind, dirty))
    before = snapshot(store)
    try:
        store.commit([item], operation)
    except StoreError as e:
        assert e.code is ErrorCode.INVALID_ARGUMENT
        assert snapshot(store) == before
        return
    persisted = durable(store,slot)
    leaf = persisted['payload'] if kind=='dataclass' else persisted[0]
    assert type(leaf['revision']) is int and leaf['revision']==1
    canonical_item, canonical_op = place(slot, wrapped(kind,canonical))
    exact_replay(SQLiteWorldStore(store.db_path),[canonical_item],canonical_op)


@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('revision', [2**63, 2**128, 10**100], ids=['signed64-overflow','128-bit','100-digits'])
@pytest.mark.parametrize('slot', ('value','metadata','filters'))
@pytest.mark.parametrize('retry', [False, True])
def test_reference_integer_bounds_never_escape_sqlite_binder(tmp_path, ref_cls, revision, slot, retry):
    store = seed(tmp_path/'db')
    if retry:
        first, operation = place(slot, ref_cls(object_id='anchor',revision=1))
        store.commit([first],operation)
    item, operation = place(slot, ref_cls(object_id='anchor',revision=revision))
    codes = {ErrorCode.IDEMPOTENCY_CONFLICT} if retry else {ErrorCode.NOT_FOUND,ErrorCode.INVALID_ARGUMENT}
    rejected(SQLiteWorldStore(store.db_path),[item],operation,codes)


@pytest.mark.parametrize('field', ['learned_at','recorded_at','occurred'])
@pytest.mark.parametrize('edge', ['minimum-positive-offset','maximum-negative-offset'])
@pytest.mark.parametrize('retry', [False, True])
def test_calendar_utc_overflow_is_a_protocol_error(tmp_path, field, edge, retry):
    store = seed(tmp_path/'db')
    clean, operation = place('value','safe')
    if retry: store.commit([clean],operation)
    value = datetime(1,1,1,tzinfo=timezone(timedelta(hours=14))) if edge.startswith('minimum') else datetime(9999,12,31,23,59,59,tzinfo=timezone(-timedelta(hours=12)))
    if field=='occurred':
        value = TemporalExtent.unknown_time().model_copy(update={'unknown':False,'precision':'second','start':value,'end':value})
    dirty = clean.model_copy(update={field:value})
    rejected(SQLiteWorldStore(store.db_path),[dirty],operation,
             ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize('retry', [False, True])
def test_huge_world_revision_cannot_leak_integer_string_conversion(tmp_path, retry):
    store = seed(tmp_path/'db')
    item, operation = place('value','safe')
    if retry: store.commit([item],operation)
    dirty = operation.model_copy(update={'expected_world_revision':10**5000})
    codes = {ErrorCode.IDEMPOTENCY_CONFLICT} if retry else {ErrorCode.INVALID_ARGUMENT,ErrorCode.VERSION_CONFLICT}
    rejected(SQLiteWorldStore(store.db_path),[item],dirty,codes)


SCALARS = [
    ('embedded-nul','a\x00b','a\x00b'),
    ('astral-unicode','\U0001f642中文','\U0001f642中文'),
    ('combining-unicode','e\u0301','e\u0301'),
    ('decimal',Decimal('1.2300'),'1.2300'),
    ('uuid',UUID('12345678-1234-5678-1234-567812345678'),'12345678-1234-5678-1234-567812345678'),
    ('path',Path('a/b'),'a/b'),
    ('subnormal-float',5e-324,5e-324),
    ('maximum-float',float.fromhex('0x1.fffffffffffffp+1023'),float.fromhex('0x1.fffffffffffffp+1023')),
    ('negative-zero',-0.0,-0.0),
]


@pytest.mark.parametrize('name,value,normal',SCALARS,ids=[s[0] for s in SCALARS])
@pytest.mark.parametrize('slot',SLOTS)
def test_supported_scalars_roundtrip_to_their_durable_normal_form(tmp_path,name,value,normal,slot):
    store = seed(tmp_path/'db')
    item,operation = place(slot,{'value':value})
    store.commit([item],operation)
    actual = durable(store,slot)['value']
    assert actual==normal and type(actual) is type(normal)
    if name=='negative-zero': assert math.copysign(1,actual)==-1
    normalized,normal_request=place(slot,{'value':normal})
    exact_replay(SQLiteWorldStore(store.db_path),[normalized],normal_request)


@pytest.mark.parametrize('field', ['operation_id','idempotency_key'])
@pytest.mark.parametrize('identity', ['nul\x00inside',"quote' OR 1=1 --",'键🙂',' leading-and-trailing '])
def test_valid_opaque_identifiers_are_lossless_and_parameterized(tmp_path,field,identity):
    store = seed(tmp_path/'db')
    operation = req(**{field:identity})
    item = obj(value='safe')
    first = store.commit([item],operation)
    replay = exact_replay(SQLiteWorldStore(store.db_path),[item],operation)
    assert first.operation_id==replay.operation_id==operation.operation_id
    with sqlite3.connect(store.db_path) as c:
        row=c.execute('SELECT operation_id,idempotency_key FROM operations WHERE operation_id=?',(operation.operation_id,)).fetchone()
    assert row==(operation.operation_id,operation.idempotency_key)


@pytest.mark.parametrize('identity', ['nul\x00inside',"quote' OR 1=1 --",'对象🙂'])
@pytest.mark.parametrize('ref_cls',REFS)
def test_opaque_object_identifiers_resolve_without_truncation(tmp_path,identity,ref_cls):
    store = seed(tmp_path/'db')
    store.commit([obj(identity)],req('target'))
    reader=obj(value=ref_cls(object_id=identity,revision=1))
    request=req('reader',revision=2)
    store.commit([reader],request)
    assert store.get_payload(identity)['object_id']==identity
    exact_replay(SQLiteWorldStore(store.db_path),[reader],request)


def change_result(store, kind):
    with sqlite3.connect(store.db_path) as c:
        row=c.execute("SELECT result_json FROM idempotency_records WHERE idempotency_key='case'").fetchone()
        data=json.loads(row[0])
        if kind=='syntax': text='{'
        elif kind=='null': text='null'
        elif kind=='list': text='[]'
        else:
            if kind=='missing-field': data.pop('world_revision')
            if kind=='wrong-operation': data['operation_id']='some-other-operation'
            if kind=='wrong-world': data['world_revision']=99999
            if kind=='wrong-objects': data['object_refs']=[['not-the-committed-object',99]]
            if kind=='bad-fingerprint-type': data['_request_fingerprint']=[]
            if kind=='bad-fingerprint-format': data['_request_fingerprint']='not-a-sha256'
            text=json.dumps(data)
        c.execute("UPDATE idempotency_records SET result_json=? WHERE idempotency_key='case'",(text,))


@pytest.mark.parametrize('kind',['syntax','null','list','missing-field','wrong-operation','wrong-world','wrong-objects','bad-fingerprint-type','bad-fingerprint-format'])
def test_corrupt_cached_results_cannot_be_returned_or_blame_the_caller(tmp_path,kind):
    store=seed(tmp_path/'db')
    item,operation=place('value','safe')
    store.commit([item],operation)
    change_result(store,kind)
    rejected(SQLiteWorldStore(store.db_path),[item],operation,ErrorCode.STORAGE_FAILURE)


@pytest.mark.parametrize('invalid_json',['{','[1,','not-json'])
def test_corrupt_payload_read_is_classified_storage_failure(tmp_path,invalid_json):
    store=seed(tmp_path/'db')
    with sqlite3.connect(store.db_path) as c:
        c.execute("UPDATE object_revisions SET payload_json=? WHERE object_id='anchor'",(invalid_json,))
    rejected_call(store,lambda:store.get_payload('anchor'),ErrorCode.STORAGE_FAILURE)


@pytest.mark.parametrize('table',TABLES)
def test_late_sql_failure_rolls_back_every_row_and_does_not_consume_key(tmp_path,table):
    store=seed(tmp_path/'db')
    with sqlite3.connect(store.db_path) as c:
        c.execute('CREATE TRIGGER audit_fail BEFORE INSERT ON '+table+" BEGIN SELECT RAISE(ABORT, 'database is locked'); END")
    items=[obj('one',value='A'),obj('two',value='B')]
    operation=req()
    rejected(store,items,operation,ErrorCode.STORAGE_FAILURE)
    with sqlite3.connect(store.db_path) as c:c.execute('DROP TRIGGER audit_fail')
    result=store.commit(items,operation)
    assert result.world_revision==2 and result.idempotent_replay is False
    exact_replay(SQLiteWorldStore(store.db_path),items,operation)


@pytest.mark.parametrize('retry',[False,True])
def test_duplicate_object_batch_never_partially_commits(tmp_path,retry):
    store=seed(tmp_path/'db')
    item=obj()
    operation=req()
    if retry:store.commit([item],operation)
    rejected(store,[item,item.model_copy()],operation,ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


def test_same_transaction_mutual_refs_and_reversed_batch_exact_replay(tmp_path):
    store=seed(tmp_path/'db')
    one=obj('one',value=ObjectRef(object_id='two',revision=1))
    two=obj('two',source_refs=[SourceRef(object_id='one',revision=1)])
    operation=req()
    assert store.commit([one,two],operation).world_revision==2
    exact_replay(SQLiteWorldStore(store.db_path),[two,one],operation)


@pytest.mark.parametrize('revision',[None,2])
@pytest.mark.parametrize('ref_cls',REFS)
def test_current_self_reference_cannot_hide_behind_historical_version(tmp_path,revision,ref_cls):
    store=seed(tmp_path/'db')
    store.commit([obj()],req())
    item=obj(revision=2,value=ref_cls(object_id='holder',revision=revision))
    rejected(store,[item],req('second',revision=2),ErrorCode.DEPENDENCY_INVALID)


@pytest.mark.parametrize('ref_cls',REFS)
def test_pinned_historical_self_reference_is_valid_and_replayable(tmp_path,ref_cls):
    store=seed(tmp_path/'db')
    store.commit([obj()],req())
    item=obj(revision=2,value=ref_cls(object_id='holder',revision=1))
    operation=req('second',revision=2)
    assert store.commit([item],operation).world_revision==3
    exact_replay(SQLiteWorldStore(store.db_path),[item],operation)


@pytest.mark.parametrize('microseconds',[-1,0,1])
@pytest.mark.parametrize('ref_cls',REFS)
def test_evidence_cutoff_microsecond_edge_is_consistent(tmp_path,microseconds,ref_cls):
    store=SQLiteWorldStore(tmp_path/'db')
    target=obj('anchor',learned_at=T+timedelta(microseconds=microseconds),recorded_at=T+timedelta(seconds=1))
    store.commit([target],req('seed',revision=0))
    item,operation=place('filters',ref_cls(object_id='anchor',revision=1))
    if microseconds>0:
        rejected(store,[item],operation,ErrorCode.NOT_FOUND)
    else:
        assert store.commit([item],operation).world_revision==2
        exact_replay(SQLiteWorldStore(store.db_path),[item],operation)


def test_world_object_string_revision_and_iso_times_normalize_before_persistence(tmp_path):
    store=seed(tmp_path/'db')
    canonical=obj()
    dirty=canonical.model_copy(update={'revision':'1','learned_at':T.isoformat(),'recorded_at':T.isoformat()})
    operation=req()
    assert store.commit([dirty],operation).world_revision==2
    assert type(store.get_payload('holder')['revision']) is int
    exact_replay(SQLiteWorldStore(store.db_path),[canonical],operation)
