"""M0 审计探针 / AUDIT-M0-R1 probes
=====================================

可重跑的缺陷证据。不修改被测代码，只读地检验 `aios_core` 当前实现是否满足
《AIOS_Core_详细开发任务拆分_R2_总工程师版.md》中 M0 各单的 G（必须编写的测试）
与 H（验收标准）。

运行：
    cd aios_core_r2_reference
    python audit_m0_probes.py            # 打印对账表，退出码 = 已确认缺口数
    python audit_m0_probes.py --strict    # 有任何缺口即退出码 1（可用于 CI 门禁）

这些检查将来被修复后，应逐条搬进 tests/ 成为回归测试（母表 DoD 第 3 条）。
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from aios_core.contracts import (  # noqa: E402
    EvidenceSet,
    KnowledgeWindow,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    SourceRef,
    TemporalExtent,
    new_object_id,
)
from aios_core.storage import SQLiteWorldStore, StoreError  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _store() -> SQLiteWorldStore:
    return SQLiteWorldStore(os.path.join(tempfile.mkdtemp(), 'world.db'))


def _obs(store_id=None, revision=1, learned=NOW, refs=(), value='x'):
    return Observation(
        object_id=store_id or new_object_id(ObjectType.OBSERVATION),
        subject_id='user_1',
        revision=revision,
        occurred=TemporalExtent.point(NOW - timedelta(hours=1)),
        learned_at=learned,
        recorded_at=learned,
        created_by='audit',
        source_kind='chat',
        modality='text',
        value=value,
        source_refs=list(refs),
    )


def _op(expected_revision, key):
    return OperationRequest(
        operation_name='audit.probe',
        expected_world_revision=expected_revision,
        reason='audit',
        idempotency_key=key,
    )


# ── 各项检查：返回 (结果, 说明)。GAP 表示与规格不匹配 ──────────────────────────

def gap_a1_evidence_window():
    """A1 EvidenceSet 成员是否受自身 knowledge_window 约束。"""
    store = _store()
    late = _obs(learned=NOW + timedelta(days=5), value='future')
    store.commit([late], _op(0, 'a1-late'))
    evidence = EvidenceSet(
        object_id=new_object_id(ObjectType.EVIDENCE_SET),
        subject_id='user_1',
        learned_at=NOW,
        recorded_at=NOW,
        created_by='audit',
        purpose='audit',
        knowledge_window=KnowledgeWindow(knowledge_cutoff=NOW, world_revision=1),
        member_refs=[ObjectRef(object_id=late.object_id)],
        selection_method='manual',
    )
    try:
        store.commit([evidence], _op(1, 'a1-es'))
    except StoreError as exc:
        return 'PASS', f'被拒绝：{exc.code.value}'
    return 'GAP', 'cutoff 之后的 Observation 可以作为成员进入 EvidenceSet（未来信息进入证据）'


def gap_a2_timezone_cutoff():
    """A2 cutoff 比较是否按绝对时刻。"""
    store = _store()
    beijing = timezone(timedelta(hours=8))
    store.commit([_obs(store_id='obs_TZ', learned=datetime(2026, 9, 14, 20, 0, tzinfo=beijing))],
                 _op(0, 'a2'))
    try:
        store.get_payload('obs_TZ', knowledge_cutoff=datetime(2026, 9, 14, 13, 0, tzinfo=UTC))
    except StoreError as exc:
        return ('GAP', '12:00Z 已知的对象在 13:00Z 查询返回 '
                f'{exc.code.value}（learned_at 按字符串字典序比较，未按绝对时刻）')
    return 'PASS', '跨时区 cutoff 可见性正确'


def gap_a3_failed_op_audit():
    """A3 失败操作是否在 operations 表留痕。"""
    path = os.path.join(tempfile.mkdtemp(), 'world.db')
    store = SQLiteWorldStore(path)
    store.commit([_obs()], _op(0, 'a3-ok'))
    try:
        store.commit([_obs(revision=9)], _op(0, 'a3-bad'))
    except StoreError:
        pass
    conn = sqlite3.connect(path)
    rows = conn.execute('SELECT status, error_code FROM operations').fetchall()
    conn.close()
    if len(rows) >= 2:
        return 'PASS', f'失败操作已留痕：{rows}'
    return 'GAP', f'operations 表只有 {len(rows)} 行 {rows}；失败操作零留痕（审计不可查）'


def gap_a4_idempotency_args():
    """A4 同幂等键 + 不同载荷是否报冲突。"""
    store = _store()
    first = _obs(value='A')
    store.commit([first], _op(0, 'a4-key'))
    second = _obs(value='B')
    replay = store.commit([second], _op(1, 'a4-key'))
    try:
        store.get_payload(second.object_id)
        written = True
    except StoreError:
        written = False
    if not written and not replay.idempotent_replay:
        return 'PASS', '抛出 IDEMPOTENCY_CONFLICT 或明确拒绝'
    return ('GAP', f'第二次提交被静默当作重放（replay={replay.idempotent_replay}），'
            f'对象 B 是否落库={written}；IDEMPOTENCY_CONFLICT 未被使用')


def gap_a5_self_reference():
    """A5 latest 写法的自我引证是否被拦截。"""
    store = _store()
    oid = new_object_id(ObjectType.OBSERVATION)
    try:
        store.commit([_obs(store_id=oid, refs=[SourceRef(object_id=oid)])], _op(0, 'a5'))
    except StoreError as exc:
        return 'PASS', f'被拒绝：{exc.code.value}'
    return 'GAP', '引用自身但不指定 revision（latest）可绕过自我引证检查'


def gap_b1_dependency_reverse_lookup():
    """B1 依赖反查 API 是否存在。"""
    api = sorted(m for m in dir(SQLiteWorldStore) if not m.startswith('_'))
    needed = [m for m in api if 'depend' in m.lower() or 'referenc' in m.lower()]
    if needed:
        return 'PASS', f'存在反查接口：{needed}'
    return 'GAP', f'SQLiteWorldStore 公共 API 仅 {api}，无按引用反查能力（M0-015 H 不可达）'


def gap_b2_error_code_coverage():
    """B2 已声明错误码是否都有抛出路径。"""
    from aios_core.contracts.enums import ErrorCode
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
    source = ''
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.endswith('.py'):
                with open(os.path.join(dirpath, name), encoding='utf-8') as handle:
                    source += handle.read()
    dead = [c.value for c in ErrorCode if source.count(f'ErrorCode.{c.name}') == 0]
    if not dead:
        return 'PASS', f'{len(list(ErrorCode))} 个错误码均有抛出路径'
    return 'GAP', f'{len(dead)}/{len(list(ErrorCode))} 个错误码从未被抛出：{dead}'


def gap_b3_lifecycle_status():
    """B3 生命周期状态是否受控枚举。"""
    obj = _obs()
    obj.status = 'arbitrary-text'
    if obj.status == 'arbitrary-text':
        return 'GAP', 'WorldObject.status 为裸 str，任意值可写入（action/session/experience 状态同理）'
    return 'PASS', '状态字段受枚举约束'


def gap_c1_concurrency_and_atomicity():
    """C1 并发双写与原子提交（M0-018 G 要求，仓库内无测试）。"""
    path = os.path.join(tempfile.mkdtemp(), 'world.db')
    store = SQLiteWorldStore(path)
    results = {}

    def writer(index):
        try:
            store.commit([_obs()], _op(0, f'c1-{index}'))
            results[index] = 'ok'
        except StoreError as exc:
            results[index] = exc.code.value
        except Exception as exc:  # noqa: BLE001
            results[index] = f'{type(exc).__name__}: {exc}'

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if sorted(results.values()) == ['VERSION_CONFLICT', 'ok'] and store.current_world_revision() == 1:
        return 'PASS', f'恰好一个写入成功：{results}'
    return 'GAP', f'并发结果不符合“只有一个成功”：{results}，world={store.current_world_revision()}'


CHECKS = [
    ('A1', 'M0-009 / R2-04', 'EvidenceSet 成员必须落在自身 knowledge_window 内', gap_a1_evidence_window),
    ('A2', 'M0-004 / M0-020', '时间可见性必须按绝对时刻比较（禁止字符串序）', gap_a2_timezone_cutoff),
    ('A3', 'M0-016', '失败操作也必须进审计表（code+message+context）', gap_a3_failed_op_audit),
    ('A4', 'M0-016', '同幂等键不同载荷必须报 IDEMPOTENCY_CONFLICT，不得静默丢写', gap_a4_idempotency_args),
    ('A5', 'M0-019', '对象不得引用自身作为自身证据（含 latest 写法）', gap_a5_self_reference),
    ('B1', 'M0-015', '必须能按引用从底层对象反查受影响对象', gap_b1_dependency_reverse_lookup),
    ('B2', 'M0-002', '已声明的协议错误码都要有抛出路径', gap_b2_error_code_coverage),
    ('B3', 'M0-005', '生命周期状态必须受控', gap_b3_lifecycle_status),
    ('C1', 'M0-017 / M0-018', '并发双写恰好一个成功，且提交原子（仓库内无此测试）', gap_c1_concurrency_and_atomicity),
]


def main(argv):
    strict = '--strict' in argv
    print('\nAUDIT-M0-R1 探针  ·  被测：aios_core_r2_reference (contracts+storage)')
    print('─' * 108)
    print(f"{'编号':<5}{'规格出处':<20}{'期望':<46}{'实测':<10}说明")
    print('─' * 108)
    gaps = 0
    for tag, spec, expectation, fn in CHECKS:
        try:
            verdict, detail = fn()
        except Exception as exc:  # noqa: BLE001
            verdict, detail = 'ERROR', f'{type(exc).__name__}: {exc}'
        if verdict != 'PASS':
            gaps += 1
        print(f'{tag:<6}{spec:<21}{expectation[:44]:<47}{verdict:<11}{detail}')
    print('─' * 108)
    print(f'已确认与规格不匹配：{gaps} / {len(CHECKS)}\n')
    return 1 if (strict and gaps) else gaps


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
