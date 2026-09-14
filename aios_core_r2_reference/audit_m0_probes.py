"""M0 审计探针 / AUDIT-M0-R2 probes
=====================================
编号规则：`M0-0NN-B<k>` —— 每条缺陷挂在它的主责工单下（B=Bug），与母表 Issue 一一对应，
可直接据此开修复单；跨单影响写在「规格出处」列里，不再另造审计专用编号。

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
import re
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from aios_core.contracts import (  # noqa: E402
    Claim,
    ClaimType,
    DimensionDefinition,
    DimensionLifecycle,
    Entity,
    EventAnchor,
    EvidenceSet,
    Goal,
    GoalSourceType,
    KnowledgeState,
    KnowledgeWindow,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    SourceRef,
    TemporalExtent,
    new_object_id,
    utc_now,
)
from aios_core.contracts.enums import EventStatus, TaskState, TaskType  # noqa: E402
from aios_core.contracts.models import Task  # noqa: E402
from aios_core.storage import SQLiteWorldStore, StoreError  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src', 'aios_core')

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

def check_m0_009_b1():
    """M0-009-B1 EvidenceSet 成员是否受自身 knowledge_window 约束。"""
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


def check_m0_004_b1():
    """M0-004-B1 cutoff 比较是否按绝对时刻。"""
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


def check_m0_016_b1():
    """M0-016-B1 失败操作是否在 operations 表留痕。"""
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


def check_m0_016_b2():
    """M0-016-B2 同幂等键 + 不同载荷是否报冲突。"""
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


def check_m0_019_b1():
    """M0-019-B1 latest 写法的自我引证是否被拦截。"""
    store = _store()
    oid = new_object_id(ObjectType.OBSERVATION)
    try:
        store.commit([_obs(store_id=oid, refs=[SourceRef(object_id=oid)])], _op(0, 'a5'))
    except StoreError as exc:
        return 'PASS', f'被拒绝：{exc.code.value}'
    return 'GAP', '引用自身但不指定 revision（latest）可绕过自我引证检查'


def check_m0_015_b1():
    """M0-015-B1 依赖反查 API 是否存在。"""
    api = sorted(m for m in dir(SQLiteWorldStore) if not m.startswith('_'))
    needed = [m for m in api if 'depend' in m.lower() or 'referenc' in m.lower()]
    if needed:
        return 'PASS', f'存在反查接口：{needed}'
    return 'GAP', f'SQLiteWorldStore 公共 API 仅 {api}，无按引用反查能力（M0-015 H 不可达）'


def check_m0_002_b1():
    """M0-002-B1 已声明错误码是否都有抛出路径。"""
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


def check_m0_005_b1():
    """M0-005-B1 生命周期状态是否受控枚举。"""
    obj = _obs()
    obj.status = 'arbitrary-text'
    if obj.status == 'arbitrary-text':
        return 'GAP', 'WorldObject.status 为裸 str，任意值可写入（action/session/experience 状态同理）'
    return 'PASS', '状态字段受枚举约束'


def check_m0_018_b1():
    """M0-018-B1 并发双写与原子提交（M0-018 G 要求，仓库内无测试）。"""
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



def check_m0_019_b2():
    """M0-019-B2 自由字典里的引用绕过存在性校验；且读回不做契约校验。"""
    store = _store()
    smuggled = {'basis': {'object_id': 'obs_ghost', 'revision': 7}}
    try:
        store.commit([_obs(value={'n': 1}, refs=[])
                      .model_copy(update={'metadata': smuggled})], _op(0, 'a6'))
    except StoreError as exc:
        return 'PASS', f'被拒绝：{exc.code.value}'
    return ('GAP', 'metadata / data_quality / maintenance_policy / applicable_scope / completion_condition / payload / checkpoint 等 dict[str,Any] 内的字典形式引用'
            '不被 _collect_refs 识别 → 引用存在性与自证检查双双绕过；读回也不 model_validate')


def check_m0_011_b1():
    """M0-011-B1 宪法第二十一条：维度生命周期是否有受控转换。"""
    from aios_core.services import state_machines
    has = [n for n in dir(state_machines) if 'dimension' in n.lower()]
    if has:
        return 'PASS', f'存在维度生命周期校验：{has}'
    store = _store()
    retired = DimensionDefinition(object_id=new_object_id(ObjectType.DIMENSION_DEFINITION),
                                  subject_id='user_1', learned_at=NOW, recorded_at=NOW,
                                  created_by='audit', name='压力', description='d',
                                  data_shape='state_interval', lifecycle=DimensionLifecycle.RETIRED)
    store.commit([retired], _op(0, 'a7-retired'))
    revived = retired.model_copy(update={'lifecycle': DimensionLifecycle.ACTIVE, 'revision': 2})
    store.commit([revived], _op(1, 'a7-revive'))   # RETIRED → ACTIVE，无任何转换校验
    return ('GAP', 'state_machines 只有 Task/Event；RETIRED→ACTIVE、CANDIDATE→RETIRED 等任意跳无校验'
            '（母表 M0-021 也只冻结了 Task/Event）')


def check_m0_010_b1():
    """M0-010-B1 Summary.source_world_revision / Session.snapshot_world_revision 不校验是否存在。"""
    store = _store()
    from aios_core.contracts import Session, Summary
    from aios_core.contracts.refs import ObjectRef as _OR
    try:
        store.commit([
            Summary(object_id=new_object_id(ObjectType.SUMMARY), subject_id='user_1',
                    learned_at=NOW, recorded_at=NOW, created_by='audit',
                    summary_time=TemporalExtent.point(NOW), granularity='week',
                    source_world_revision=999),
            Session(object_id=new_object_id(ObjectType.SESSION), subject_id='user_1',
                    learned_at=NOW, recorded_at=NOW, created_by='audit',
                    snapshot_world_revision=12345),
        ], _op(0, 'a8'))
    except StoreError as exc:
        return 'PASS', f'被拒绝：{exc.code.value}'
    return ('GAP', 'world 只到 1，却可提交指向 revision 999 / 12345 的 Summary 与 Session'
            '（宪法第十八/十九条要求总结可展开、可重建）')


def check_m0_012_b1():
    """M0-012-B1 EventAnchor 状态与 merged/split/supersedes 引用不一致。"""
    store = _store()
    event = EventAnchor(object_id=new_object_id(ObjectType.EVENT), subject_id='user_1',
                        learned_at=NOW, recorded_at=NOW, created_by='audit',
                        title='运动会', interpretation='待定',
                        event_status=EventStatus.MERGED, confidence=0.5)
    try:
        store.commit([event], _op(0, 'a9'))
    except StoreError as exc:
        return 'PASS', f'被拒绝：{exc.code.value}'
    return ('GAP', 'status=MERGED 而 merged_into_ref=None 可提交；宪法第十三条'
            '「后来为何修正」的链条在契约层可被写成断头')


def check_m0_014_b1():
    """M0-014-B1 Task 时间语义与 EXPIRED 可达性。"""
    from aios_core.contracts import Task
    from aios_core.contracts.enums import TaskState, TaskType
    from aios_core.services import validate_task_transition
    bad = None
    try:
        validate_task_transition(TaskState.RUNNING, TaskState.EXPIRED)
    except ValueError as exc:
        bad = str(exc)
    t = Task(object_id=new_object_id(ObjectType.TASK), subject_id='user_1', learned_at=NOW,
             recorded_at=NOW, created_by='audit', task_type=TaskType.DEADLINE, title='复习',
             deadline=NOW - timedelta(days=1), next_wake_at=NOW + timedelta(days=1),
             task_state=TaskState.READY)
    msgs = []
    if bad:
        msgs.append('RUNNING→EXPIRED 被拒（过期任务只能 FAILED/CANCELLED）')
    if t.deadline < t.next_wake_at < t.deadline + timedelta(days=99):
        msgs.append(f'deadline 已过期({t.deadline:%m-%d}) 而 next_wake_at 在其后'
                    f'({t.next_wake_at:%m-%d})，模型不报错')
    return ('GAP' if msgs else 'PASS', '；'.join(msgs) or '一致')


def check_m0_003_b1():
    """M0-003-B1 ID 前缀与 object_type 不绑定（宪法第十五条 唯一编号）。"""
    store = _store()
    mismatched = Observation(object_id=new_object_id(ObjectType.ENTITY),  # ent_ 前缀
                             subject_id='user_1', revision=1,
                             occurred=TemporalExtent.point(NOW), learned_at=NOW, recorded_at=NOW,
                             created_by='audit', source_kind='chat', modality='text', value='x')
    try:
        store.commit([mismatched], _op(0, 'a11'))
    except StoreError as exc:
        return 'PASS', f'被拒绝：{exc.code.value}'
    return ('GAP', f"`ent_` 前缀的 ID 被登记为 object_type=observation（实测 {mismatched.object_id[:4]}…）"
            '→ 任何按前缀路由/索引的假设都不成立')


def check_m0_017_b1():
    """M0-017-B1 「所有写入通过唯一 Core 写入层」是否有数据库侧保障。

    规格写的是架构约束，但 SQLite 的外键是**每连接 opt-in**：默认连接不启用时，
    任何绕过 Core 的写入都能造出指向不存在 world revision 的孤儿对象。
    """
    payload_sql = ("INSERT INTO object_revisions(object_id, revision, object_type, subject_id, "
                   "world_revision, learned_at, recorded_at, payload_json) "
                   "VALUES('obs_raw', 1, 'observation', 'user_1', 4242, ?, ?, '{}')")

    def attempt(enable_fk):
        path = os.path.join(tempfile.mkdtemp(), 'world.db')
        SQLiteWorldStore(path)
        conn = sqlite3.connect(path)
        if enable_fk:
            conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute(payload_sql, (NOW.isoformat(), NOW.isoformat()))
            conn.commit()
            return 'accepted'
        except sqlite3.IntegrityError:
            return 'rejected'
        finally:
            conn.close()

    loose, strict = attempt(False), attempt(True)
    if loose == 'rejected':
        return 'PASS', '数据库侧已拒绝绕过 Core 的写入'
    detail = (f'默认连接 fk=0 → 孤儿对象写入成功（world_revision=4242 不存在）；'
              f'同一 SQL 在 fk=1 时 {strict}（FK 约束存在但是每连接 opt-in）'
              '；payload 为空字典也能读回 → 唯一写入层只是调用方自觉，缺 CHECK/触发器/只读账号')
    return 'GAP', detail


def check_m0_021_b1():
    """M0-021-B1 生命周期校验是否接在写入路径上（宪法第二十一条 + 完成定义「代码写完不算完成」）。

    `validate_task_transition` / `validate_event_transition` 只被 services/__init__ 导出、
    被测试调用；`commit()` 内没有任何调用 → 状态机是"可选工具"，不是写入约束。
    """
    store_dir = os.path.join(SRC, 'storage')
    commit_src = ''
    for fn in os.listdir(store_dir):
        if fn.endswith('.py'):
            t = open(os.path.join(store_dir, fn), encoding='utf-8').read()
            m = re.search(r'def commit\(.*?(?=\n    def |\Z)', t, re.S)
            if m:
                commit_src += m.group(0)
    wired = bool(re.search(r'validate_\w+_transition|state_machines', commit_src))
    if wired:
        return 'PASS', 'commit() 调用状态机校验'
    # 现场证明：非法转换直接提交也能落库
    store = _store()
    bad = Task(object_id=new_object_id(ObjectType.TASK), subject_id='user_1',
               learned_at=NOW, recorded_at=NOW, created_by='audit', title='t',
               task_type=TaskType.TODO, task_state=TaskState.COMPLETED)
    store.commit([bad], _op(0, 'a13-create'))
    illegal = bad.model_copy(update={'task_state': TaskState.RUNNING, 'revision': 2})
    try:
        store.commit([illegal], _op(1, 'a13-illegal'))
        accepted = True
    except Exception:  # noqa: BLE001
        accepted = False
    if accepted:
        from aios_core.services import validate_task_transition
        validator_rejects = True
        try:
            validate_task_transition(TaskState.COMPLETED, TaskState.RUNNING)
            validator_rejects = False
        except ValueError:
            pass
        if not validator_rejects:
            return ('ERROR', '前提失效：矩阵并未禁止 COMPLETED→RUNNING，需换用例')
        return ('GAP', 'validate_task_transition(COMPLETED, RUNNING) 明确禁止该转换，'
                '但同一转换经 commit() 直接落库成功 → store 从不调用状态机（调用次数 0），'
                '宪法第二十一条/完成定义所要求的"受控迁移"在写入路径上未接线；'
                'Dimension/Goal/Summary 更是连矩阵都没有（见 M0-011-B1）')
    return 'PASS', '非法转换被 store 拒绝'


CHECKS = [
    # (缺陷编号 = 主责工单-B*, 验收依据, 断言（不满足即 GAP）, 探针函数)
    ('M0-002-B1', 'G/H · R2 冻结项', '已声明的协议错误码都必须有抛出路径，错误对象须可携带上下文', check_m0_002_b1),
    ('M0-003-B1', 'G · 宪法第十五条', '对象 ID 前缀与 object_type 必须互相校验', check_m0_003_b1),
    ('M0-004-B1', 'H · 宪法第二条', '知识可见性必须按绝对时刻比较，禁止字符串序', check_m0_004_b1),
    ('M0-005-B1', 'H · 宪法第十三条', '生命周期状态必须是受控枚举，不得为裸 str', check_m0_005_b1),
    ('M0-009-B1', 'H · R2-04 · 宪法第四十六条', 'EvidenceSet 成员必须落在自身 knowledge_window 内', check_m0_009_b1),
    ('M0-010-B1', 'H · 宪法第十八/十九条', 'Summary/Session 的快照版本指针必须指向真实存在的 world revision', check_m0_010_b1),
    ('M0-011-B1', 'G · 宪法第二十一条', '维度生命周期必须有受控转换矩阵', check_m0_011_b1),
    ('M0-012-B1', 'H · 宪法第十三条', '事件状态必须与其 merged/split/supersedes 引用一致', check_m0_012_b1),
    ('M0-014-B1', 'D/H · 宪法第三十二/三条', '过期任务必须可进入 EXPIRED，deadline 与 next_wake_at 需自洽', check_m0_014_b1),
    ('M0-015-B1', 'H（§13 已承期待补）', '必须能按引用从底层对象反查受影响对象', check_m0_015_b1),
    ('M0-016-B1', 'H · 宪法第四十五条', '失败操作也必须进审计表（code+message+context）', check_m0_016_b1),
    ('M0-016-B2', 'G/H', '同幂等键不同载荷必须报 IDEMPOTENCY_CONFLICT，不得静默丢写', check_m0_016_b2),
    ('M0-017-B1', 'I · 架构唯一写入层', '数据库侧必须无法绕过 Core 写入', check_m0_017_b1),
    ('M0-018-B1', 'H · M0-017', '并发双写恰好一个成功且提交原子（行为已验证，仓库内缺此测试）', check_m0_018_b1),
    ('M0-019-B1', 'H · 宪法第八条', '对象不得以 latest 写法引用自身作为自身证据', check_m0_019_b1),
    ('M0-019-B2', 'H · 宪法第八条', '任何形态的引用都必须被验证；读回必须按模型校验', check_m0_019_b2),
    ('M0-021-B1', 'G · 宪法第二十一条', '生命周期校验必须接在 Core 写入路径上', check_m0_021_b1),
]


def main(argv):
    strict = '--strict' in argv
    print('\nAUDIT-M0-R2 探针  ·  被测：aios_core_r2_reference（M0-001…M0-019 参考实现）')
    print('─' * 108)
    print(f"{'缺陷编号':<12}{'规格出处':<22}{'期望':<44}{'实测':<10}说明")
    print('─' * 118)
    gaps = 0
    for tag, spec, expectation, fn in CHECKS:
        try:
            verdict, detail = fn()
        except Exception as exc:  # noqa: BLE001
            verdict, detail = 'ERROR', f'{type(exc).__name__}: {exc}'
        if verdict != 'PASS':
            gaps += 1
        print(f'{tag:<12}{spec:<23}{expectation[:42]:<45}{verdict:<11}{detail}')
    print('─' * 118)
    print(f'已确认与规格不匹配：{gaps} / {len(CHECKS)}\n')
    return 1 if (strict and gaps) else gaps


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
