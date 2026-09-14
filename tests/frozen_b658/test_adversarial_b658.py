"""NEW frozen gate probes for b6588bda; NOT the lost original 100 probes.
Freeze this file before collection/execution. Never change expected outcomes in place.
Only SQLiteWorldStore public operations are under test; direct SQL is used for
complete state inspection and explicitly labelled legacy/corruption fixtures.
"""
import json
import os
import sqlite3
import subprocess
import sys
from collections import UserDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict
from aios_core.contracts import (
    Observation, OperationRequest, ObjectRef, SourceRef, EvidenceSet,
    KnowledgeWindow, WorldObject, ObjectType,
)
from aios_core.contracts.models import EvidenceSelector
from aios_core.contracts.time import TemporalExtent
from aios_core.contracts.enums import ErrorCode
from aios_core.storage import SQLiteWorldStore, StoreError

CANDIDATE = 'b6588bdaaa36d9dace4f9959dda0a89a370e1674'
T = datetime(2026, 9, 14, 9, tzinfo=timezone.utc)
SLOTS = ['metadata', 'value', 'arguments', 'filters']
REFS = [ObjectRef, SourceRef]
TABLES = ('world_commits', 'object_revisions', 'operations', 'idempotency_records')


def common(oid, **kw):
    d = dict(object_id=oid, subject_id='gate-subject', learned_at=T,
             recorded_at=T, created_by='redteam-b658-new')
    d.update(kw)
    return d


def observation(oid='holder', cls=Observation, **kw):
    return cls(**common(oid, source_kind='audit', modality='json', **kw))


def operation(key='case', rev=1, **kw):
    d = dict(operation_id='op-'+key, operation_name='world.commit',
             expected_world_revision=rev, idempotency_key=key,
             reason='new frozen adversarial gate')
    d.update(kw)
    return OperationRequest(**d)


def state(store):
    with sqlite3.connect(store.db_path) as c:
        revision = int(c.execute("SELECT value FROM world_meta WHERE key='world_revision'").fetchone()[0])
        return (revision,) + tuple(tuple(c.execute('SELECT * FROM '+table+' ORDER BY 1,2').fetchall()) for table in TABLES)


def reject(store, objects, request, codes):
    """Even a raw exception or unexpected success must run the atomicity assertion."""
    if isinstance(codes, ErrorCode):
        codes = {codes}
    before = state(store)
    try:
        with pytest.raises(StoreError) as exc:
            store.commit(objects, request)
        assert exc.value.code in codes
    finally:
        assert state(store) == before, 'rejected request mutated complete durable state'


def replay(store, objects, request):
    before = state(store)
    try:
        result = store.commit(objects, request)
        assert result.idempotent_replay is True
    finally:
        assert state(store) == before, 'replay changed complete durable state'
    return result


def seeded(path):
    store = SQLiteWorldStore(path)
    store.commit([observation('anchor'), observation('future', learned_at=T+timedelta(hours=1),
                 recorded_at=T+timedelta(hours=1))], operation('seed', rev=0))
    return store


def at(slot, value):
    request = operation()
    if slot == 'value':
        obj = observation(value=value)
    elif slot == 'metadata':
        obj = observation(metadata={'probe': value})
    elif slot == 'arguments':
        obj = observation()
        request = operation(arguments={'probe': value})
    else:
        obj = EvidenceSet(**common('holder', learned_at=T+timedelta(hours=2), recorded_at=T+timedelta(hours=2)),
            purpose='frozen audit', knowledge_window=KnowledgeWindow(knowledge_cutoff=T, world_revision=1),
            member_refs=[ObjectRef(object_id='anchor', revision=1)], selection_method='explicit',
            selector=EvidenceSelector(selector_type='audit', subject_id='gate-subject',
                time_range=TemporalExtent.unknown_time(), algorithm_version='1', filters={'probe': value}))
    return obj, request


def durable_at(store, slot):
    if slot == 'arguments':
        with sqlite3.connect(store.db_path) as c:
            return json.loads(c.execute("SELECT arguments_json FROM operations WHERE operation_id='op-case'").fetchone()[0])['probe']
    obj = store.get_payload('holder')
    if slot == 'value':
        return obj['value']
    if slot == 'metadata':
        return obj['metadata']['probe']
    return obj['selector']['filters']['probe']


def legacy_fixture(store):
    """Simulate pre-fingerprint result rows; no arbitrary payload changes."""
    with sqlite3.connect(store.db_path) as c:
        data = json.loads(c.execute("SELECT result_json FROM idempotency_records WHERE idempotency_key='case'").fetchone()[0])
        data.pop('_request_fingerprint')
        c.execute("UPDATE idempotency_records SET result_json=? WHERE idempotency_key='case'", (json.dumps(data),))


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('direction', ['opaque-to-typed', 'typed-to-opaque'])
def test_x1_bidirectional_identity_restart_stale(tmp_path, slot, ref_cls, direction):
    store = seeded(tmp_path/'world.db')
    ref = ref_cls(object_id='anchor', revision=1)
    typed = at(slot, {'nested': [ref]})
    opaque = at(slot, {'nested': [ref.model_dump(mode='python')]})
    first, changed = (opaque, typed) if direction == 'opaque-to-typed' else (typed, opaque)
    store.commit([first[0]], first[1])
    restart = SQLiteWorldStore(store.db_path)
    assert restart.current_world_revision() > first[1].expected_world_revision
    replay(restart, [first[0]], first[1])
    reject(restart, [changed[0]], changed[1], ErrorCode.IDEMPOTENCY_CONFLICT)


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('ref_cls', REFS)
def test_x1_marker_spoof_is_not_reference_identity(tmp_path, slot, ref_cls):
    store = seeded(tmp_path/'world.db')
    ref = ref_cls(object_id='anchor', revision=1)
    marker = ['$aios-ref', 'object' if ref_cls is ObjectRef else 'source', 'anchor', 1]
    if ref_cls is SourceRef:
        marker.append(None)
    first, request = at(slot, marker)
    store.commit([first], request)
    changed, retry_request = at(slot, ref)
    reject(SQLiteWorldStore(store.db_path), [changed], retry_request, ErrorCode.IDEMPOTENCY_CONFLICT)


@pytest.mark.parametrize('slot', ['metadata', 'value', 'arguments'])
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('direction', ['opaque-to-typed', 'typed-to-opaque'])
def test_legacy_no_bidirectional_typed_opaque_false_replay(tmp_path, slot, ref_cls, direction):
    store = seeded(tmp_path/'world.db')
    ref = ref_cls(object_id='anchor', revision=1)
    typed, opaque = at(slot, ref), at(slot, ref.model_dump(mode='python'))
    first, changed = (opaque, typed) if direction == 'opaque-to-typed' else (typed, opaque)
    store.commit([first[0]], first[1])
    legacy_fixture(store)
    reject(SQLiteWorldStore(store.db_path), [changed[0]], changed[1], ErrorCode.IDEMPOTENCY_CONFLICT)


@pytest.mark.parametrize('slot', ['metadata', 'value', 'arguments'])
def test_legacy_pure_json_exact_replay(tmp_path, slot):
    store = seeded(tmp_path/'world.db')
    obj, request = at(slot, {'ordinary': [1, True, None, 'text']})
    store.commit([obj], request)
    legacy_fixture(store)
    replay(SQLiteWorldStore(store.db_path), [obj], request)


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('ref_cls', REFS)
def test_legacy_unverifiable_typed_exact_fails_closed(tmp_path, slot, ref_cls):
    store = seeded(tmp_path/'world.db')
    obj, request = at(slot, ref_cls(object_id='anchor', revision=1))
    store.commit([obj], request)
    legacy_fixture(store)
    reject(SQLiteWorldStore(store.db_path), [obj], request, ErrorCode.IDEMPOTENCY_CONFLICT)


def invalid_value(kind):
    if kind == 'surrogate': return '\ud800'
    if kind == 'bytes': return b'\xff'
    if kind == 'object': return object()
    if kind == 'huge-int': return 10**5000
    if kind == 'nan': return float('nan')
    if kind == 'infinity': return float('inf')
    if kind == 'negative-infinity': return -float('inf')
    if kind == 'list-cycle':
        value = []; value.append(value); return value
    if kind == 'dict-cycle':
        value = {}; value['self'] = value; return value
    value = 'leaf'
    for _ in range(1500): value = [value]
    return value


@pytest.mark.parametrize('kind', ['surrogate', 'bytes', 'object', 'huge-int', 'nan', 'infinity', 'negative-infinity', 'list-cycle', 'dict-cycle', 'depth'])
@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('retry', [False, True])
def test_x2_serialization_protocol_atomicity(tmp_path, kind, slot, retry):
    store = seeded(tmp_path/'world.db')
    if retry:
        obj, request = at(slot, 'safe')
        store.commit([obj], request)
    obj, request = at(slot, invalid_value(kind))
    reject(SQLiteWorldStore(store.db_path), [obj], request,
           ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


class ExtraBag(BaseModel):
    model_config = ConfigDict(extra='allow')
    fixed: int = 1


class LooseObservation(Observation):
    model_config = ConfigDict(extra='allow')


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('copy_update', [False, True])
def test_x3_nested_extra_roundtrip_and_changed_retry(tmp_path, slot, copy_update):
    store = seeded(tmp_path/'world.db')
    bag = ExtraBag(note='A', child=ExtraBag(note='inner', payload={'answer': 42}))
    changed = bag.model_copy(update={'note': 'B'}) if copy_update else ExtraBag(note='B', child=bag.child)
    obj, request = at(slot, {'levels': [bag]})
    store.commit([obj], request)
    assert durable_at(store, slot) == {'levels': [json.loads(bag.model_dump_json())]}
    replay(SQLiteWorldStore(store.db_path), [obj], request)
    obj2, request2 = at(slot, {'levels': [changed]})
    reject(SQLiteWorldStore(store.db_path), [obj2], request2, ErrorCode.IDEMPOTENCY_CONFLICT)


@pytest.mark.parametrize('target', ['world', 'operation', 'ObjectRef', 'SourceRef'])
@pytest.mark.parametrize('field', ['rogue', '_rogue'])
@pytest.mark.parametrize('retry', [False, True])
def test_x3_dirty_unknown_fields_must_not_be_silently_erased(tmp_path, target, field, retry):
    store = seeded(tmp_path/'world.db')
    if target in ('ObjectRef', 'SourceRef'):
        ref_cls = ObjectRef if target == 'ObjectRef' else SourceRef
        ref = ref_cls(object_id='anchor', revision=1)
        clean, request = at('metadata', {'nested': [ref]})
        dirty, changed_request = at('metadata', {'nested': [ref.model_copy(update={field: 'payload'})]})
    else:
        clean, request = at('value', 'safe')
        dirty = clean.model_copy(update={field: 'payload'}) if target == 'world' else clean
        changed_request = request.model_copy(update={field: 'payload'}) if target == 'operation' else request
    if retry: store.commit([clean], request)
    reject(SQLiteWorldStore(store.db_path), [dirty], changed_request,
           ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize('retry', [False, True])
def test_b10_canonical_subtype_extra_allow_is_not_authority(tmp_path, retry):
    store = seeded(tmp_path/'world.db')
    obj, request = at('value', 'safe')
    if retry: store.commit([obj], request)
    dirty = observation(cls=LooseObservation, value='safe', unapproved=ExtraBag(note='must-not-drop'))
    reject(SQLiteWorldStore(store.db_path), [dirty], request,
           ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('revision', ['1', None])
def test_x4_canonical_ref_roundtrip_and_restart_retry(tmp_path, slot, ref_cls, revision):
    store = seeded(tmp_path/'world.db')
    canonical = ref_cls(object_id='anchor', revision=1 if revision == '1' else None)
    dirty = canonical.model_copy(update={'revision': revision})
    obj, request = at(slot, {'nested': [dirty]})
    store.commit([obj], request)
    persisted = durable_at(store, slot)['nested'][0]['revision']
    assert (type(persisted) is int and persisted == 1) if revision == '1' else persisted is None
    obj2, request2 = at(slot, {'nested': [canonical]})
    replay(SQLiteWorldStore(store.db_path), [obj2], request2)


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('revision', ['bad', -1, 0, 1.5, []], ids=['string', 'negative', 'zero', 'fractional', 'list'])
@pytest.mark.parametrize('retry', [False, True])
def test_x4_invalid_dirty_ref_atomic_rejection(tmp_path, slot, ref_cls, revision, retry):
    store = seeded(tmp_path/'world.db')
    ref = ref_cls(object_id='anchor', revision=1)
    if retry:
        obj, request = at(slot, ref)
        store.commit([obj], request)
    obj, request = at(slot, ref.model_copy(update={'revision': revision}))
    reject(SQLiteWorldStore(store.db_path), [obj], request,
           ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize('field,value', [
    ('expected_world_revision', 'bad'), ('expected_world_revision', []),
    ('expected_world_revision', None), ('expected_world_revision', -1),
    ('operation_id', []), ('operation_id', None), ('operation_id', ''),
    ('operation_id', '\ud800'), ('idempotency_key', []),
    ('idempotency_key', None), ('idempotency_key', ''), ('idempotency_key', '   '),
    ('idempotency_key', b'\xff'), ('idempotency_key', '\ud800'),
], ids=['rev-text','rev-list','rev-none','rev-negative','id-list','id-none','id-empty','id-surrogate','key-list','key-none','key-empty','key-blank','key-bytes-invalid','key-surrogate'])
@pytest.mark.parametrize('retry', [False, True])
def test_dirty_operation_routing_never_leaks_binder_values(tmp_path, field, value, retry):
    store = seeded(tmp_path/'world.db')
    obj, request = at('value', 'safe')
    if retry: store.commit([obj], request)
    dirty = request.model_copy(update={field: value})
    code = ErrorCode.IDEMPOTENCY_CONFLICT if retry and field != 'idempotency_key' else ErrorCode.INVALID_ARGUMENT
    reject(SQLiteWorldStore(store.db_path), [obj], dirty, code)


@pytest.mark.parametrize('field,value', [('expected_world_revision','1'), ('idempotency_key',b'case'), ('operation_id',b'op-case')])
@pytest.mark.parametrize('retry', [False, True])
def test_b6_coercible_operation_identity_normalizes_before_routing(tmp_path, field, value, retry):
    store = seeded(tmp_path/'world.db')
    obj, request = at('value', 'safe')
    dirty = request.model_copy(update={field: value})
    if retry:
        store.commit([obj], request)
        replay(SQLiteWorldStore(store.db_path), [obj], dirty)
    else:
        assert store.commit([obj], dirty).world_revision == 2
        replay(SQLiteWorldStore(store.db_path), [obj], request)


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('key', [1, 1.5, None, b'key', ('key',), False], ids=['int','float','none','bytes','tuple','bool'])
@pytest.mark.parametrize('retry', [False, True])
def test_b11_nested_mapping_keys_must_be_strings(tmp_path, slot, key, retry):
    store = seeded(tmp_path/'world.db')
    if retry:
        obj, request = at(slot, {'safe': 1})
        store.commit([obj], request)
    obj, request = at(slot, [UserDict({key: 'not-lossless'})])
    reject(SQLiteWorldStore(store.db_path), [obj], request,
           ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize('kind', ['missing', 'self-pinned', 'self-floating', 'cutoff'])
@pytest.mark.parametrize('ref_cls', REFS)
@pytest.mark.parametrize('container', ['list', 'tuple', 'mapping', 'set', 'frozenset'])
def test_b4_reference_validation_survives_containers(tmp_path, kind, ref_cls, container):
    store = seeded(tmp_path/'world.db')
    ref = ref_cls(object_id='missing' if kind == 'missing' else 'future' if kind == 'cutoff' else 'holder',
                  revision=None if kind == 'self-floating' else 1)
    wrapped = {'list': lambda: [ref], 'tuple': lambda: (ref,), 'mapping': lambda: UserDict({'r': ref}),
               'set': lambda: {ref}, 'frozenset': lambda: frozenset({ref})}[container]()
    obj, request = at('filters' if kind == 'cutoff' else 'metadata', wrapped)
    expected = ErrorCode.DEPENDENCY_INVALID if kind.startswith('self') else ErrorCode.NOT_FOUND
    # No frozen promise to accept ref-containing sets. Safe unsupported-container
    # rejection is allowed; successful invalid-ref persistence is never allowed.
    allowed = {expected, ErrorCode.INVALID_ARGUMENT} if container in ('set','frozenset') else {expected}
    reject(store, [obj], request, allowed)


@pytest.mark.parametrize('bad', [None, [], {}, 99, 'not-an-object-type'], ids=['none','list','dict','int','unknown'])
@pytest.mark.parametrize('retry', [False, True])
def test_b10_dirty_discriminator_uses_canonical_contract(tmp_path, bad, retry):
    store = seeded(tmp_path/'world.db')
    obj, request = at('value', 'safe')
    if retry: store.commit([obj], request)
    reject(SQLiteWorldStore(store.db_path), [obj.model_copy(update={'object_type':bad})], request,
           ErrorCode.IDEMPOTENCY_CONFLICT if retry else ErrorCode.INVALID_ARGUMENT)


def test_b10_base_class_cannot_impersonate_observation(tmp_path):
    store = seeded(tmp_path/'world.db')
    dirty = WorldObject(**common('holder', object_type=ObjectType.OBSERVATION))
    reject(store, [dirty], operation(), ErrorCode.INVALID_ARGUMENT)


@pytest.mark.parametrize('slot', SLOTS)
def test_b1_changed_nested_plain_data_conflicts(tmp_path, slot):
    store = seeded(tmp_path/'world.db')
    obj, request = at(slot, {'nested': [{'answer': 'A'}]})
    store.commit([obj], request)
    obj2, request2 = at(slot, {'nested': [{'answer': 'B'}]})
    reject(SQLiteWorldStore(store.db_path), [obj2], request2, ErrorCode.IDEMPOTENCY_CONFLICT)


@pytest.mark.parametrize('slot', SLOTS)
def test_b6_shared_acyclic_alias_and_json_coercions(tmp_path, slot):
    store = seeded(tmp_path/'world.db')
    shared = {'text': b'valid-utf8', 'ordered': ('a','b')}
    obj, request = at(slot, [shared, shared])
    store.commit([obj], request)
    obj2, request2 = at(slot, [{'text':'valid-utf8','ordered':['a','b']}, {'text':'valid-utf8','ordered':['a','b']}])
    replay(SQLiteWorldStore(store.db_path), [obj2], request2)


@pytest.mark.parametrize('slot', ['metadata', 'value', 'arguments'])
def test_b6_unordered_value_durable_normal_form_replay(tmp_path, slot):
    store = seeded(tmp_path/'world.db')
    obj, request = at(slot, {'unordered': frozenset({'alpha','beta'})})
    store.commit([obj], request)
    normal = durable_at(store, slot)
    obj2, request2 = at(slot, normal)
    replay(SQLiteWorldStore(store.db_path), [obj2], request2)


def test_cross_process_hash_seed_restart_preserves_complete_rows(tmp_path):
    store = seeded(tmp_path/'world.db')
    script = """import sys
from test_adversarial_b658 import at
from aios_core.storage import SQLiteWorldStore
obj, request = at('value', {'nested': {frozenset({'aa','bb'}), frozenset({'cc','dd'})}})
r = SQLiteWorldStore(sys.argv[1]).commit([obj], request)
print(r.idempotent_replay)
"""
    before = None
    for seed in ('37','179','991'):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        env['PYTHONPATH'] = str(Path(__file__).parent)+os.pathsep+os.environ['PYTHONPATH']
        result = subprocess.run([sys.executable, '-c', script, str(store.db_path)], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ('False' if before is None else 'True')
        if before is not None: assert state(store) == before
        before = state(store)
