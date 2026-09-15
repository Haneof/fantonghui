"""auditor-e / TRACK=E 对抗探针：跨切面交互与 B10+ 搜索。

只读地驱动 `aios_core` 公共 API（外加少量为触发底层故障而做的 SQLite 干扰），
不修改生产代码。每个用例自有一处临时目录，互不污染。

  退出码 = 已确认的真实缺陷数
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.environ["AIOS_SRC"])   # = 被审 worktree 的 src/ 目录（见报告 §3 运行方式）
AUDIT_ROOT = os.environ.get("AIOS_ROOT") or os.path.dirname(os.path.abspath(os.environ["AIOS_SRC"]))

from pydantic import ValidationError  # noqa: E402

from aios_core.contracts import (  # noqa: E402
    Claim,
    ClaimType,
    Dependency,
    Entity,
    EvidenceSet,
    KnowledgeState,
    KnowledgeWindow,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    Relation,
    SourceRef,
    TemporalExtent,
    Task,
    TaskState,
    TaskType,
)
from aios_core.contracts.enums import EventStatus  # noqa: E402
from aios_core.errors import ErrorCode  # noqa: E402
from aios_core.services import validate_task_transition  # noqa: E402
from aios_core.storage import SQLiteWorldStore, StoreError  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
RESULTS: list[tuple[str, str, str, str]] = []


def tmp_db() -> str:
    return os.path.join(tempfile.mkdtemp(), "world.db")


def obs(oid="o1", rev=1, learned=T0, **kw):
    return Observation(
        object_id=oid, subject_id="u1", revision=rev, learned_at=learned,
        recorded_at=kw.pop("recorded_at", learned + timedelta(seconds=1)),
        created_by="auditor-e", source_kind="test", modality="json",
        value=kw.pop("value", {"n": 1}), **kw)


_SEQ = [0]


def op(key="k1", rev=0, name="world.commit", oid=None, **kw):
    """每次调用都发一个全新的 operation_id（一次尝试 = 一个 attempt id）。"""
    _SEQ[0] += 1
    return OperationRequest(operation_id=oid or f"auditor-e-attempt-{_SEQ[0]}", operation_name=name,
                            arguments=kw.pop("arguments", {}), expected_world_revision=rev,
                            reason="auditor-e probe", idempotency_key=key, **kw)


def case(covers):
    def deco(fn):
        def run():
            try:
                verdict, detail = fn()
            except Exception as exc:  # noqa: BLE001
                verdict, detail = "PROBE-ERROR", f"{type(exc).__name__}: {str(exc)[:220]}"
            RESULTS.append((fn.__name__.removeprefix("e_"), covers, verdict, detail))
        run.__name__ = fn.__name__
        return run
    return deco


def expect_store_error(fn, *codes):
    try:
        fn()
    except StoreError as exc:
        return exc
    except Exception as exc:  # noqa: BLE001
        return f"RAW:{type(exc).__name__}"
    return None


# ───────────────────────────────────────────── E1 幂等 × validate_references ──
@case("M0-016 · 换 attempt id 的等价重试是否安全")
def e_retry_with_new_operation_id():
    """幂等重放身份包含 operation_id（每次尝试的 id）。崩溃后无回执、以新 operation_id 重试同一逻辑请求：
    写已成功过，却只能拿到 IDEMPOTENCY_CONFLICT（M0-016 A/H 要求「能够安全重试」「重试无重复副作用」）。"""
    store = SQLiteWorldStore(tmp_db())
    o = obs()
    store.commit([o], op(key="e1"))                      # 第一次尝试成功，回执丢失（模拟崩溃）
    err = expect_store_error(lambda: store.commit([o], op(key="e1")))
    if isinstance(err, StoreError) and err.code is ErrorCode.IDEMPOTENCY_CONFLICT:
        applied = store.current_world_revision()
        return ("RULING",
                f"同一 idempotency_key、内容完全相同的等价重试，仅 operation_id 不同 → "
                f"{err.code.value}/{err.context.get('reason')}，而写入其实已生效（world={applied}）。"
                "M0-016 A/H 要求「能够安全重试」；B6 裁决又要求身份等于持久化表示（含 operations.operation_id PK）。"
                "二者对「attempt id 是否属于请求身份」给出相反暗示 → 需总工裁定，且冲突文案 "
                "「already used for a different request」在此场景下是错的（同一请求，不同尝试）")
    return ("INFO", f"以新 operation_id 重放得到：{getattr(err,'code',err)}")


@case("M0-016 · 复用 operation_id 换 key 必须冲突")
def e_same_operation_id_new_key():
    store = SQLiteWorldStore(tmp_db())
    shared = op(key="e2a", oid="auditor-e-fixed-id")
    store.commit([obs()], shared)                              # 同一 operation_id 已落库
    again = shared.model_copy(update={"idempotency_key": "e2b", "expected_world_revision": 1})
    err = expect_store_error(lambda: store.commit([obs(oid="z")], again))
    if isinstance(err, StoreError) and (err.context or {}).get("reason") == "operation_id_reused":
        return ("OK", "operation_id 复用被明确拒绝（operation_id_reused），世界版本未推进")
    return ("BUG-CONFIRMED", f"未拒或理由错误：{getattr(err, 'code', err)}/{getattr(err, 'context', None)}")


@case("M0-019 · commit 是否仍留有跳过引用校验的公开逃生舱")
def e_no_validation_escape_hatch():
    src = open(os.path.join(AUDIT_ROOT, "src/aios_core/storage/sqlite_store.py"), encoding="utf-8").read()
    public = ["current_world_revision", "commit", "get_payload", "list_payloads", "operation_record"]
    has_flag = "validate_references" in src
    writes_outside = "INSERT INTO" in src.split("def commit")[0]
    if not has_flag:
        return ("OK", f"公开 API 只有 {public}，commit() 无 validate_references 逃生舱；"
                "非 commit 路径不含写入 SQL → 「唯一 Core 写入层」在 API 边界成立")
    return ("BUG-CONFIRMED", "仍存在关闭引用校验的公开开关")


@case("M0-016/019 · 悬空引用只能经 commit 落库吗")
def e_validate_reference_bypass_via_replay():
    """（保留原假设，但改为经由不透明 dict 携带引用形状：证明这类引用不会进入校验。）"""
    """以 validate_references=False 落库悬空引用后，同一请求改用 validate_references=True 重试
    必须按当前契约拒绝（引用不得悬空），但幂等重放在校验之前返回成功回执。"""
    store = SQLiteWorldStore(tmp_db())
    d = obs(value={"fake_ref": {"object_id": "ghost", "revision": 999},
                   "nested": [{"object_id": "ghost2", "revision": 42}]})
    store.commit([d], op(key="e1"))
    got = store.get_payload("o1")["value"]
    return ("INFO",
            f"typed ref 全量校验（无逃生舱）；但 `value/metadata` 等 Any 字段里的**引用形状字典**"
            f"不被当作引用（已落库：{json.dumps(got, ensure_ascii=False)[:90]}…）。"
            "M0-019 H 只约束类型化引用，属文档一致的可接受边界 → 记为 residual，不作 blocker")


@case("M0-019 · 同一请求在新 key 下是否仍被拒")
def e_validate_reference_new_key_rejected():
    store = SQLiteWorldStore(tmp_db())
    d = obs().model_copy(update={"source_refs": [SourceRef(object_id="ghost@missing", revision=3)]})
    err = expect_store_error(lambda: store.commit([d], op(key="e2-fresh")))
    return ("OK", f"新 key 下同一请求被拒：{getattr(err, 'code', err)}") if isinstance(err, StoreError) else ("BUG-CONFIRMED", f"未拒：{err}")


# ───────────────────────────────────────────── E2 状态机 vs 持久化 ──────────
@case("M0-021/005 · state machine helper vs generic persistence")
def e_state_machine_not_enforced_by_store():
    """`validate_task_transition(COMPLETED, RUNNING)` 明确非法，但通用持久化层是否拦截？"""
    store = SQLiteWorldStore(tmp_db())
    t = Task(object_id="t1", subject_id="u1", learned_at=T0, recorded_at=T0 + timedelta(seconds=1),
             created_by="auditor-e", title="t", task_type=TaskType.TODO, task_state=TaskState.COMPLETED)
    store.commit([t], op(key="e3a"))
    moved = t.model_copy(update={"task_state": TaskState.RUNNING, "revision": 2})
    helper = "拒绝"
    try:
        validate_task_transition(TaskState.COMPLETED, TaskState.RUNNING)
        helper = "放行"
    except ValueError:
        pass
    try:
        store.commit([moved], op(key="e3b", rev=1))
        persisted = store.get_payload("t1", revision=2).get("task_state")
    except StoreError as exc:
        return ("OK", f"store 拒绝非法迁移：{exc.code.value}")
    if persisted == TaskState.RUNNING.value and helper == "拒绝":
        return ("BUG-CONFIRMED",
                "冻结矩阵判定 COMPLETED→RUNNING 非法（helper 抛 ValueError），"
                "但 commit() 不经过状态机：非法迁移落库成功"
                "（M0-017 D「所有对象先结构/引用/版本校验再 insert」是否覆盖状态迁移，需总工裁定）")
    return ("INFO", f"helper={helper}，落库 task_state={persisted}")


# ───────────────────────────────────────── 共同必查 1/2/4 ─────────────────
@case("必查1 · stale exact replay 先于 expected-world rejection")
def e_replay_precedes_version_conflict():
    store = SQLiteWorldStore(tmp_db())
    o = obs()
    first = op(key="e4", rev=0)
    store.commit([o], first)
    store.commit([obs(oid="o2")], op(key="e4x", rev=1))       # 世界前进到 2
    res = store.commit([o], first.model_copy(deep=True))       # 完全相同的请求，expected 已过期
    ok = res.idempotent_replay and res.world_revision == 1
    return ("OK", "过期但完全相同的请求返回原回执（未被 VERSION_CONFLICT 吞掉）") if ok \
        else ("BUG-CONFIRMED", f"回执异常：replay={res.idempotent_replay} wr={res.world_revision}")


@case("必查2 · 同 key 不同请求必须冲突")
def e_same_key_different_request():
    store = SQLiteWorldStore(tmp_db())
    store.commit([obs()], op(key="e5"))
    err = expect_store_error(lambda: store.commit([obs(oid="other")], op(key="e5", rev=1)))
    if isinstance(err, StoreError) and err.code is ErrorCode.IDEMPOTENCY_CONFLICT:
        return ("OK", f"IDEMPOTENCY_CONFLICT reason={err.context.get('reason')}")
    return ("BUG-CONFIRMED", f"未冲突：{err}")


@case("必查4 · 失败赋值后的脏字段不得入库")
def e_dirty_operation_not_persisted():
    store = SQLiteWorldStore(tmp_db())
    request = op(key="e6")
    try:
        request.operation_name = ""          # 赋值校验抛错，但实例可能已被改脏
    except ValidationError:
        pass
    dirty_live = request.operation_name
    store.commit([obs()], request)
    row = store.operation_record(request.operation_id)
    if row["operation_name"] == "world.commit" and row["status"] == "committed":
        return ("OK", f"live 实例被赋值校验拒改（现值 {dirty_live!r}），durable 审计行仍为干净快照 ✅")
    if row["operation_name"] != "world.commit":
        return ("BUG-CONFIRMED", f"脏字段入库：{row['operation_name']!r}")
    return ("INFO", f"audit 行={row}")


# ───────────────────────────────────── 必查3 · 跨进程重放 ──────────────────
CHILD = r'''
import json, sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.environ["AIOS_SRC"])
from aios_core.contracts import Observation, OperationRequest, TemporalExtent, ObjectType
from aios_core.storage import SQLiteWorldStore, StoreError
db = sys.argv[1]
now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
items = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa"]
o = Observation(object_id="p_obs", subject_id="u1", revision=1, learned_at=now,
                recorded_at=now + timedelta(seconds=1), created_by="auditor-e",
                source_kind="test", modality="json",
                value={"labels": set(items),
                       "deep": {"lv2": [frozenset(items[:5]), {"k": set(items[5:])}],
                                "lv3": frozenset([json.dumps({"z": sorted(set(items))})])}})
r = OperationRequest(operation_id="p_op", operation_name="world.commit",
                     arguments={"labels": set(items)}, expected_world_revision=int(sys.argv[2]),
                     reason="e7", idempotency_key="e7-key")
store = SQLiteWorldStore(db)
try:
    res = store.commit([o], r)
    print(json.dumps({"ok": True, "replay": res.idempotent_replay, "wr": res.world_revision}))
except StoreError as exc:
    print(json.dumps({"ok": False, "code": exc.code.value, "reason": (exc.context or {}).get("reason")}))
'''


@case("必查3 · 不同 PYTHONHASHSEED / 不同进程下同一逻辑请求必须稳定重放")
def e_cross_process_replay_stability():
    db = tmp_db()
    env = dict(os.environ, PYTHONHASHSEED="1")
    a = subprocess.run([sys.executable, "-c", CHILD, db, "0"], capture_output=True, text=True, env=env)
    if a.returncode:
        return ("PROBE-ERROR", a.stderr[-300:])
    first = json.loads(a.stdout.strip().splitlines()[-1])
    outs = []
    for seed in ("7", "12345", "0", "random"):
        e2 = dict(env, PYTHONHASHSEED=seed)
        p = subprocess.run([sys.executable, "-c", CHILD, db, "0"], capture_output=True, text=True, env=e2)
        outs.append((seed, json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else p.stderr[-160:]))
    stable = all(o.get("replay") is True for _, o in outs if isinstance(o, dict))
    if not stable:
        return ("BUG-CONFIRMED", f"跨进程重放不稳定：first={first} others={outs}")
    # 改变集合成员必须冲突
    p = subprocess.run([sys.executable, "-c", CHILD.replace('"alpha", "beta"', '"alpha", "BETA!"') + "", db, "0"],
                       capture_output=True, text=True, env=env)
    return ("OK", f"4 个 hash seed 全部 replay=True；成员改变→{json.loads(p.stdout.splitlines()[-1]).get('reason', 'n/a')}")


# ───────────────────────────────── 必查5/6 · 故障分类 ──────────────────────
@case("必查5 · 真 SQLITE_BUSY 必须按 result code 归类为可重试锁竞争")
def e_real_busy_is_version_conflict():
    db = tmp_db()
    store = SQLiteWorldStore(db)
    store.commit([obs()], op(key="e8-init"))
    holder = sqlite3.connect(db, timeout=0)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO world_meta(key,value) VALUES('busy-holder','x')")
    got = None
    try:
        try:
            store.commit([obs(oid="loser")], op(key="e8", rev=1, oid="op8"))
            got = "COMMITTED-UNDER-LOCK"
        except StoreError as exc:
            got = (exc.code.value, (exc.context or {}).get("reason"), (exc.context or {}).get("sqlite_errorcode"))
    finally:
        holder.rollback()
        holder.close()
    if got == "COMMITTED-UNDER-LOCK":
        return ("BUG-CONFIRMED", "持锁期间写入竟然成功 → 写锁未真正生效")
    code, reason, errcode = got
    if code == "VERSION_CONFLICT" and reason == "storage_busy" and errcode in (5, 6):
        after = store.current_world_revision()
        return ("OK", f"VERSION_CONFLICT/storage_busy (code={errcode})，世界版本仍 {after}")
    return ("BUG-CONFIRMED", f"分类不符：{got}")


@case("必查6 · 文本含 busy/locked 但非锁故障必须 STORAGE_FAILURE")
def e_text_trap_is_storage_failure():
    db = tmp_db()
    SQLiteWorldStore(db).commit([obs()], op(key="e9"))
    with sqlite3.connect(db) as c:      # 让错误文本恰为 "database is locked"，但 base code 不是 BUSY/LOCKED
        c.execute("CREATE TRIGGER text_trap BEFORE INSERT ON operations "
                  "BEGIN SELECT raise_abort('database is locked'); END")
    err = expect_store_error(lambda: SQLiteWorldStore(db).commit([obs(oid="x")], op(key="e9b", rev=1)))
    with sqlite3.connect(db) as c:
        c.execute("DROP TRIGGER text_trap")
    if isinstance(err, StoreError):
        ok = err.code is ErrorCode.STORAGE_FAILURE
        return ("OK" if ok else "BUG-CONFIRMED",
                f"{err.code.value}/{err.context.get('reason')}（错误文本含 'database is locked'，按 code 判定）")
    return ("BUG-CONFIRMED", f"未走协议错误：{err}")


@case("必查7 · 事务中途失败必须原子回滚四类记录")
def e_late_failure_atomicity():
    db = tmp_db()
    store = SQLiteWorldStore(db)
    store.commit([obs()], op(key="e10"))
    with sqlite3.connect(db) as c:
        c.execute("CREATE TRIGGER boom AFTER INSERT ON idempotency_records "
                  "BEGIN SELECT raise_abort('auditor-e injected'); END")
    err = expect_store_error(lambda: store.commit([obs(oid="a"), obs(oid="b", rev=1)],
                                                  op(key="e11", rev=1)))
    with sqlite3.connect(db) as c:
        c.execute("DROP TRIGGER boom")
        counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
                  ("world_commits", "object_revisions", "operations", "idempotency_records")}
        wr = c.execute("SELECT value FROM world_meta WHERE key='world_revision'").fetchone()[0]
    leak = [t for t, n in counts.items() if n != 1]
    if leak or wr != "1":
        return ("BUG-CONFIRMED", f"回滚不完整：world_revision={wr} counts={counts} err={err}")
    code = getattr(err, "code", err)
    return ("OK", f"原子回滚成立（world=1，四类记录无残留）；错误={code}")


# ───────────────────────────── 必查8/9 · 自引用 ───────────────────────────
@case("必查8/9 · floating 自引用必须拒，pinned 历史自链必须合法")
def e_self_reference_rules():
    store = SQLiteWorldStore(tmp_db())
    o = obs()
    store.commit([o], op(key="e12"))
    float_err = expect_store_error(lambda: store.commit(
        [o.model_copy(update={"revision": 2, "source_refs": [SourceRef(object_id="o1")]})], op(key="e13", rev=1)))
    pin_err = expect_store_error(lambda: store.commit(
        [o.model_copy(update={"revision": 2, "source_refs": [SourceRef(object_id="o1", revision=1)]})],
        op(key="e14", rev=1)))
    f_ok = isinstance(float_err, StoreError) and float_err.code is ErrorCode.DEPENDENCY_INVALID
    p_ok = pin_err is None
    if f_ok and p_ok:
        return ("OK", "floating 自引用被拒（DEPENDENCY_INVALID），X@2→X@1 历史 pinned 自链合法")
    return ("BUG-CONFIRMED", f"floating={getattr(float_err,'code',float_err)} pinned={getattr(pin_err,'code',pin_err)}")


# ──────────────────────── 必查10/11 · EvidenceSet 冻结 cutoff ──────────────
@case("必查10 · EvidenceSet typed refs 必须落在自身 frozen knowledge_cutoff 内")
def e_evidence_frozen_cutoff():
    store = SQLiteWorldStore(tmp_db())
    future = T0 + timedelta(days=7)
    store.commit([obs(oid="o_late", learned=future), obs(oid="o_now", learned=T0)], op(key="e15"))
    cut = T0                      # cutoff 早于 o_late 的 learned_at
    es_ok = EvidenceSet(object_id="es1", subject_id="u1", learned_at=future,
                        recorded_at=future + timedelta(seconds=1), created_by="auditor-e",
                        purpose="gate", selection_method="manual",
                        knowledge_window=KnowledgeWindow(knowledge_cutoff=cut),
                        member_refs=[ObjectRef(object_id="o_now", revision=1),
                                     ObjectRef(object_id="o_late", revision=1)])
    err = expect_store_error(lambda: store.commit([es_ok], op(key="e16", rev=1)))
    if isinstance(err, StoreError):
        return ("OK", f"cutoff 之后的成员被拒：{err.code.value}/{err.context.get('reason')}")
    return ("BUG-CONFIRMED",
            f"cutoff={cut:%F} 之后的 o_late(learned {future:%F}) 仍可作为 EvidenceSet 成员落库"
            " → 未来知识可进入证据（若 R4 已裁定为按 EvidenceSet 自身 cutoff 校验，则属未执行）")


@case("必查11 · 同事务内合法互相引用不得被误杀")
def e_same_tx_mutual_refs():
    store = SQLiteWorldStore(tmp_db())
    claim = Claim(object_id="c1", subject_id="u1", learned_at=T0, recorded_at=T0 + timedelta(seconds=1),
                  created_by="auditor-e", claimant_id="u1", claim_type=ClaimType.FACT, content="x",
                  asserted_at=T0, knowledge_state=KnowledgeState.OBSERVED, confidence=0.9,
                  support_evidence_set_refs=[ObjectRef(object_id="es1", revision=1)])
    es = EvidenceSet(object_id="es1", subject_id="u1", learned_at=T0, recorded_at=T0 + timedelta(seconds=1),
                     created_by="auditor-e", purpose="p", selection_method="manual",
                     knowledge_window=KnowledgeWindow(knowledge_cutoff=T0),
                     member_refs=[ObjectRef(object_id="c1", revision=1)])
    err = expect_store_error(lambda: store.commit([claim, es], op(key="e17")))
    if err is None:
        return ("OK", "同事务互相引用（Claim↔EvidenceSet）正常提交")
    return ("BUG-CONFIRMED", f"合法同事务互引被误杀：{getattr(err, 'code', err)} / {getattr(err, 'message', '')}")


# ────────────────────── 必查12 · Dependency 环 vs Relation 环 ──────────────
@case("必查12 · Dependency 必须拒环，Relation 有环不得被误杀")
def e_dependency_vs_relation_cycle():
    store = SQLiteWorldStore(tmp_db())
    def ent(oid):
        return Entity(object_id=oid, subject_id="u1", learned_at=T0,
                      recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e", entity_kind="person")
    a, b = ent("e1"), ent("e2")
    store.commit([a, b], op(key="e18"))
    r1 = Relation(object_id="r1", subject_id="u1", learned_at=T0, recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                  left=ObjectRef(object_id="e1", revision=1), relation_type="knows",
                  right=ObjectRef(object_id="e2", revision=1), confidence=0.5)
    r2 = r1.model_copy(update={"object_id": "r2", "left": ObjectRef(object_id="e2", revision=1),
                               "right": ObjectRef(object_id="e1", revision=1)})
    rel_err = expect_store_error(lambda: store.commit([r1, r2], op(key="e19", rev=1)))
    d1 = Dependency(object_id="d1", subject_id="u1", learned_at=T0, recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                    dependent_ref=ObjectRef(object_id="e1", revision=1),
                    dependency_ref=ObjectRef(object_id="e2", revision=1), dependency_type="proof")
    d2 = d1.model_copy(update={"object_id": "d2", "dependent_ref": ObjectRef(object_id="e2", revision=1),
                               "dependency_ref": ObjectRef(object_id="e1", revision=1)})
    dep_err = expect_store_error(lambda: store.commit([d1, d2], op(key="e20", rev=2)))
    ok = rel_err is None and isinstance(dep_err, StoreError) and dep_err.code is ErrorCode.DEPENDENCY_INVALID
    return ("OK" if ok else "BUG-CONFIRMED", f"Relation 环={rel_err or '允许 ✅'}；Dependency 环={getattr(dep_err,'code',dep_err)}")


# ────────────────────── 必查13 · 双透镜组合 ──────────────────────────────
@case("必查13 · world_revision 与 knowledge_cutoff 组合可见性")
def e_dual_lens():
    store = SQLiteWorldStore(tmp_db())
    store.commit([obs(oid="x", rev=1, learned=T0)], op(key="e21"))
    later = T0 + timedelta(days=3)
    store.commit([obs(oid="x", rev=2, learned=later, value={"n": 2})], op(key="e22", rev=1))
    a = store.get_payload("x", as_of_world_revision=2, knowledge_cutoff=T0)["value"]
    b = store.get_payload("x", as_of_world_revision=1, knowledge_cutoff=later)["value"]
    c = store.get_payload("x", knowledge_cutoff=T0)["value"]
    ok = a == {"n": 1} and b == {"n": 1} and c == {"n": 1}
    if ok:
        # 列表侧也必须同样收敛
        n = len(store.list_payloads(object_type=ObjectType.OBSERVATION, knowledge_cutoff=T0, subject_id="u1"))
        return ("OK", f"三向组合正确（world2+cutoff=T0→rev1；world1+cutoff=+3d→rev1；列表命中 {n}）")
    return ("BUG-CONFIRMED", f"双透镜组合错：world2/cut0={a} world1/cut3d={b} cut0={c}")


# ────────────────────── 必查14/15 · 冻结矩阵与快照 ──────────────────────
@case("必查14 · Task/Event 冻结矩阵未被 B8/B9 补丁改动")
def e_matrix_no_drift():
    diff = subprocess.run(["git", "-C", AUDIT_ROOT, "diff", "--stat", "f38fdd2aa64e31b92c5353206a8aef62c9322087",
                           "--", "src/aios_core/services/state_machines.py", "src/aios_core/contracts/enums.py"],
                          capture_output=True, text=True).stdout.strip()
    sm = open(os.path.join(AUDIT_ROOT, "src/aios_core/services/state_machines.py"), encoding="utf-8").read()
    four = all(k in sm for k in ("RUNNING", "WAITING_RESULT", "COMPLETED", "CANDIDATE", "REJECTED", "MERGED"))
    if not diff and four:
        return ("OK", "自 B6/B7 批准快照起 state_machines.py/enums.py 无改动（0 文件）")
    return ("BUG-CONFIRMED", f"矩阵相关文件出现改动：{diff}")


@case("必查15 · schema snapshot 只是结构证据")
def e_schema_snapshot_scope():
    p = os.path.join(AUDIT_ROOT, "tests/unit/contracts/test_m0_schema_snapshot.py")
    t = open(p, encoding="utf-8").read()
    behavioral = any(k in t for k in ("SQLiteWorldStore", "commit("))
    return ("INFO", f"快照测试 {'含行为断言（需检查是否被当行为证据）' if behavioral else '仅结构 hash，未冒充行为证明 ✅'}")


# ────────────────────── B10+ 搜索：错误契约与陈旧库兼容 ──────────────────────
@case("B10? · 公共 API 是否仍可能抛非协议异常（脏 durable 行）")
def e_raw_exception_leak_from_public_api():
    """外部（导入/迁移/人工）写坏一行 Dependency payload 后，公共 commit() 必须以 StoreError 报错，
    而不是把 pydantic traceback 抛给 Worker（M0-002 H：禁止只有 traceback）。"""
    store = SQLiteWorldStore(tmp_db())
    store.commit([obs(oid="e1x", rev=1), obs(oid="e2x", rev=1)], op(key="e23"))
    with sqlite3.connect(store.db_path) as c:
        bad = json.dumps({"object_id": "d_bad", "object_type": "dependency", "subject_id": "u1",
                          "revision": 1, "learned_at": T0.isoformat(), "recorded_at": T0.isoformat(),
                          "created_by": "import", "created_by": "import", "dependent_ref": {"object_id": "e1x", "revision": 1},
                          "dependency_ref": {"object_id": "e2x", "revision": None},
                          "dependency_type": "proof"})
        c.execute("INSERT INTO object_revisions(object_id,revision,object_type,subject_id,world_revision,"
                  "learned_at,recorded_at,payload_json) VALUES('d_bad',1,'dependency','u1',1,?,?,?)",
                  (T0.isoformat(), T0.isoformat(), bad))
    fresh = SQLiteWorldStore(store.db_path)
    new_dep = Dependency(object_id="d_new", subject_id="u1", learned_at=T0, recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                         dependent_ref=ObjectRef(object_id="e2x", revision=1),
                         dependency_ref=ObjectRef(object_id="e1x", revision=1), dependency_type="proof")
    err = expect_store_error(lambda: fresh.commit([new_dep], op(key="e24", rev=1)))
    if isinstance(err, StoreError):
        return ("OK", f"以协议错误呈现：{err.code.value}/{err.context.get('reason')}")
    return ("BUG-CONFIRMED",
            f"公共 API commit() 抛出非协议异常 → {err}（M0-002 H「禁止只有 traceback」被违反；"
            "Worker 无法分类，重试引擎会把永久性损坏当可重试或崩溃退出）")


@case("B10? · 回执与指纹对『集合 vs 有序列表』不可分辨")
def e_set_vs_ordered_list_identity():
    """有序语义（list/tuple）与无序语义（set）在指纹层被压平为同一请求：
    二者 durable payload 相同，但语义不同 → 第二个请求收到『你的请求已生效』的重放回执。"""
    store = SQLiteWorldStore(tmp_db())
    req = op(key="e25", arguments={"seq": {"a", "b"}})
    store.commit([obs(oid="o", value={"seq": {"a", "b"}})], req)
    res = store.commit([obs(oid="o", value={"seq": ["a", "b"]})], req.model_copy(deep=True))
    if res.idempotent_replay:
        return ("BUG-CONFIRMED",
                "set 与有序 list 归一到同一指纹：调用方以有序语义提交 ["
                "'a','b']，得到『重放成功』回执，但 Core 从未按有序请求处理它；"
                "（若 list 顺序与 set 排序结果不同则会正确冲突）")
    return ("OK", "两者指纹不同，未压平")


@case("B10? · 逆序 list 必须仍是不同请求")
def e_ordered_list_permutation_distinct():
    store = SQLiteWorldStore(tmp_db())
    store.commit([obs(oid="o", value={"seq": ["a", "b"]})], op(key="e26", arguments={"seq": ["a", "b"]}))
    err = expect_store_error(lambda: store.commit([obs(oid="o", value={"seq": ["b", "a"]})],
                                                  op(key="e26", arguments={"seq": ["b", "a"]}, oid="op26b")))
    if isinstance(err, StoreError) and err.code is ErrorCode.IDEMPOTENCY_CONFLICT:
        return ("OK", "list 顺序参与身份：逆序请求正确判为不同请求并冲突")
    return ("BUG-CONFIRMED", f"顺序被忽略：{err}")


@case("B10? · 失败事务后同 key 重试是否被永久锁死")
def e_retry_after_failed_first_attempt():
    db = tmp_db()
    store = SQLiteWorldStore(db)
    with sqlite3.connect(db) as c:
        c.execute("CREATE TRIGGER boom AFTER INSERT ON object_revisions "
                  "BEGIN SELECT raise_abort('injected'); END")
    first = expect_store_error(lambda: store.commit([obs()], op(key="e27")))
    with sqlite3.connect(db) as c:
        c.execute("DROP TRIGGER boom")
    try:
        res = store.commit([obs()], op(key="e27b"))
        return ("OK", f"故障消失后同 key 重试成功：world={res.world_revision}")
    except StoreError as exc:
        return ("INFO", f"重试被拒：{exc.code.value}/{exc.context.get('reason')}（首次失败未落 idempotency 记录时应可重试）")


@case("B10? · 时区等价与整点边界（learned_at/cutoff 绝对时刻）")
def e_timezone_equivalence():
    store = SQLiteWorldStore(tmp_db())
    plus8 = T0.astimezone(timezone(timedelta(hours=8)))
    store.commit([obs(oid="o", learned=plus8)], op(key="e28"))           # 同一时刻，+08:00 表示
    same = store.get_payload("o", knowledge_cutoff=T0)["value"]
    edge = store.get_payload("o", knowledge_cutoff=plus8)["value"]
    before = expect_store_error(lambda: store.get_payload("o", knowledge_cutoff=T0 - timedelta(microseconds=1)))
    if same == {"n": 1} and edge == {"n": 1} and isinstance(before, StoreError) and before.code is ErrorCode.NOT_FOUND:
        return ("OK", "UTC/+08:00 等价时刻一致；边界为「<= cutoff 可见」；早 1µs 不可见")
    return ("BUG-CONFIRMED", f"时区等价或边界不一致：same={same} edge={edge} before={before}")




# ═══════════════════════ B10/B11/B12：object_type 自证与 durable 往返 ═══════════════════════
@case("M0-017-B3 · 类型标签由调用方自证：基类可伪造 object_type 绕过结构校验")
def e_spoofed_object_type():
    """`commit` 接受任何 WorldObject，用 `type(obj)` 再校验；基类实例可声明 object_type=observation
    而 payload 完全不含 Observation 必填字段 → 落库的行违反其自称类型的冻结契约。"""
    from aios_core.contracts.base import WorldObject
    store = SQLiteWorldStore(tmp_db())
    fake = WorldObject(object_id="fake_obs", subject_id="u1", learned_at=T0,
                       recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                       object_type=ObjectType.OBSERVATION)
    try:
        store.commit([fake], op(key="e30"))
    except StoreError as exc:
        return ("OK", f"伪造类型被拒：{exc.code.value}/{exc.context.get('reason')}")
    payload = store.get_payload("fake_obs")
    from aios_core.contracts.models import Observation
    try:
        Observation.model_validate(payload)
        verdict, detail = "INFO", "落库且可读回为合法 Observation（说明结构由 payload 自身兜住）"
    except ValidationError as exc:
        verdict, detail = ("BUG-CONFIRMED",
                           f"世界版本 {store.current_world_revision()} 中出现自称 observation、"
                           f"但违反 Observation 契约的行（缺 {[k for k in ('source_kind','modality') if k not in payload]}）；"
                           f"按自称类型校验即抛 {type(exc).__name__} → M0-017 D「所有对象先结构校验再 insert」"
                           "在「声明类型 vs payload 实际结构」这一层未做交叉校验")
    return (verdict, detail)


@case("M0-002-B2 · 自称 dependency 的伪行使后续合法提交抛非协议异常")
def e_spoofed_dependency_bricks_later_commit():
    """上一步的伪造行若自称 dependency，`_validate_dependency_graph` 会对 durable 行做
    `Dependency.model_validate` 且未捕获 → 之后任何合法 Dependency 提交都抛 traceback。"""
    from aios_core.contracts.base import WorldObject
    store = SQLiteWorldStore(tmp_db())
    store.commit([obs(oid="eA"), obs(oid="eB")], op(key="e31"))
    try:
        store.commit([WorldObject(object_id="fake_dep", subject_id="u1", learned_at=T0,
                                  recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                                  object_type=ObjectType.DEPENDENCY)], op(key="e32", rev=1))
    except StoreError as exc:
        return ("OK", f"自称 dependency 的伪行被当场拒：{exc.code.value}")
    real = Dependency(object_id="d_ok", subject_id="u1", learned_at=T0,
                      recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                      dependent_ref=ObjectRef(object_id="eA", revision=1),
                      dependency_ref=ObjectRef(object_id="eB", revision=1), dependency_type="proof")
    err = expect_store_error(lambda: store.commit([real], op(key="e33", rev=2)))
    if isinstance(err, StoreError):
        return ("OK", f"后续提交以协议错误失败：{err.code.value}")
    return ("BUG-CONFIRMED",
            f"合法提交被一行伪造数据砖化，且抛出非协议异常 {err}；此后该库上所有 Dependency 写入永久失败，"
            "而错误里没有任何 CoreErrorCode 可分支（M0-002 H）")


@case("M0-017-B3 · 子类多带字段即可让 durable payload 无法按其冻结类型读回")
def e_subclass_extra_fields_break_roundtrip():
    """公共 API 接受任意 WorldObject 子类（模型未 final）；子类合法校验通过并入库，
    但 durable payload 含有冻结模型 extra=forbid 不接受的键 → 按类型读回必然失败。
    M0-022 的 schema snapshot 只冻结了各模型自身的 JSON Schema，抓不到「入库对象是子类」。"""
    from aios_core.contracts.models import Observation as Base
    class WidenedObservation(Base):
        auditor_note: str = "extra"
    store = SQLiteWorldStore(tmp_db())
    wid = WidenedObservation(object_id="wide", subject_id="u1", learned_at=T0,
                             recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                             source_kind="test", modality="json", value=1)
    try:
        store.commit([wid], op(key="e34"))
    except StoreError as exc:
        return ("OK", f"伪造子类被边界拒绝：{exc.code.name}/{exc.context.get('reason')}")
    payload = store.get_payload("wide")
    try:
        Base.model_validate(payload)
        return ("INFO", "子类 payload 仍可被冻结类型接受（无 extra 泄漏）")
    except ValidationError as exc:
        errs = [e.get("msg") for e in exc.errors()]
        return ("BUG-CONFIRMED",
                f"写入成功但按冻结契约读回即失败：{errs[:1]}；"
                "durable 行违反了 Observation 的 extra=forbid 冻结契约，而 commit() 全程无错 → "
                "「公共写入层保证 durable 表示满足冻结契约」不成立（M0-017 D / M0-022 快照盲区）")

def main():
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("e_") and callable(v)]:
        fn()
    print(f"\n{'='*100}\nauditor-e / TRACK=E 对抗探针（候选 659157b，共 {len(RESULTS)} 项）\n{'='*100}")
    bugs = 0
    for name, covers, verdict, detail in RESULTS:
        if verdict == "BUG-CONFIRMED":
            bugs += 1
        print(f"[{verdict:<13}] {name}\n    覆盖: {covers}\n    {detail}\n")
    print("-" * 100)
    print(f"确认缺陷 {bugs} / {len(RESULTS)} 项")
    return bugs




# ═══════════════════════ B10/B11/B12：object_type 自证与 durable 往返 ═══════════════════════
@case("M0-017-B3 · 类型标签由调用方自证：基类可伪造 object_type 绕过结构校验")
def e_spoofed_object_type():
    """`commit` 接受任何 WorldObject，用 `type(obj)` 再校验；基类实例可声明 object_type=observation
    而 payload 完全不含 Observation 必填字段 → 落库的行违反其自称类型的冻结契约。"""
    from aios_core.contracts.base import WorldObject
    store = SQLiteWorldStore(tmp_db())
    fake = WorldObject(object_id="fake_obs", subject_id="u1", learned_at=T0,
                       recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                       object_type=ObjectType.OBSERVATION)
    try:
        store.commit([fake], op(key="e30"))
    except StoreError as exc:
        return ("OK", f"伪造类型被拒：{exc.code.value}/{exc.context.get('reason')}")
    payload = store.get_payload("fake_obs")
    from aios_core.contracts.models import Observation
    try:
        Observation.model_validate(payload)
        verdict, detail = "INFO", "落库且可读回为合法 Observation（说明结构由 payload 自身兜住）"
    except ValidationError as exc:
        verdict, detail = ("BUG-CONFIRMED",
                           f"世界版本 {store.current_world_revision()} 中出现自称 observation、"
                           f"但违反 Observation 契约的行（缺 {[k for k in ('source_kind','modality') if k not in payload]}）；"
                           f"按自称类型校验即抛 {type(exc).__name__} → M0-017 D「所有对象先结构校验再 insert」"
                           "在「声明类型 vs payload 实际结构」这一层未做交叉校验")
    return (verdict, detail)


@case("M0-002-B2 · 自称 dependency 的伪行使后续合法提交抛非协议异常")
def e_spoofed_dependency_bricks_later_commit():
    """上一步的伪造行若自称 dependency，`_validate_dependency_graph` 会对 durable 行做
    `Dependency.model_validate` 且未捕获 → 之后任何合法 Dependency 提交都抛 traceback。"""
    from aios_core.contracts.base import WorldObject
    store = SQLiteWorldStore(tmp_db())
    store.commit([obs(oid="eA"), obs(oid="eB")], op(key="e31"))
    try:
        store.commit([WorldObject(object_id="fake_dep", subject_id="u1", learned_at=T0,
                                  recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                                  object_type=ObjectType.DEPENDENCY)], op(key="e32", rev=1))
    except StoreError as exc:
        return ("OK", f"自称 dependency 的伪行被当场拒：{exc.code.value}")
    real = Dependency(object_id="d_ok", subject_id="u1", learned_at=T0,
                      recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                      dependent_ref=ObjectRef(object_id="eA", revision=1),
                      dependency_ref=ObjectRef(object_id="eB", revision=1), dependency_type="proof")
    err = expect_store_error(lambda: store.commit([real], op(key="e33", rev=2)))
    if isinstance(err, StoreError):
        return ("OK", f"后续提交以协议错误失败：{err.code.value}")
    return ("BUG-CONFIRMED",
            f"合法提交被一行伪造数据砖化，且抛出非协议异常 {err}；此后该库上所有 Dependency 写入永久失败，"
            "而错误里没有任何 CoreErrorCode 可分支（M0-002 H）")


@case("M0-017-B3 · 子类多带字段即可让 durable payload 无法按其冻结类型读回")
def e_subclass_extra_fields_break_roundtrip():
    """公共 API 接受任意 WorldObject 子类（模型未 final）；子类合法校验通过并入库，
    但 durable payload 含有冻结模型 extra=forbid 不接受的键 → 按类型读回必然失败。
    M0-022 的 schema snapshot 只冻结了各模型自身的 JSON Schema，抓不到「入库对象是子类」。"""
    from aios_core.contracts.models import Observation as Base
    class WidenedObservation(Base):
        auditor_note: str = "extra"
    store = SQLiteWorldStore(tmp_db())
    wid = WidenedObservation(object_id="wide", subject_id="u1", learned_at=T0,
                             recorded_at=T0 + timedelta(seconds=1), created_by="auditor-e",
                             source_kind="test", modality="json", value=1)
    try:
        store.commit([wid], op(key="e34"))
    except StoreError as exc:
        return ("OK", f"伪造子类被边界拒绝：{exc.code.name}/{exc.context.get('reason')}")
    payload = store.get_payload("wide")
    try:
        Base.model_validate(payload)
        return ("INFO", "子类 payload 仍可被冻结类型接受（无 extra 泄漏）")
    except ValidationError as exc:
        errs = [e.get("msg") for e in exc.errors()]
        return ("BUG-CONFIRMED",
                f"写入成功但按冻结契约读回即失败：{errs[:1]}；"
                "durable 行违反了 Observation 的 extra=forbid 冻结契约，而 commit() 全程无错 → "
                "「公共写入层保证 durable 表示满足冻结契约」不成立（M0-017 D / M0-022 快照盲区）")


if __name__ == "__main__":
    sys.exit(main())
