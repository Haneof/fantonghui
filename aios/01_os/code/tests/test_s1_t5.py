# -*- coding: utf-8 -*-
"""Sprint 1 · Task 5 验收裁判 —— Event → World Update → World State 已在主线运行

契约依据：tasks/plans/T29_s1_t5_world_update.md（本任务任务书 + 验收记录）
用法：
    python tests/test_s1_t5.py            # 全部（含真总线集成 G/H）
    python tests/test_s1_t5.py --fast     # 只跑引擎级 A-F、I 与自检（不启进程）
门禁 A-I 全绿 exit 0；任何一项失败 exit 1。

刻意使用可移植 API（Popen.terminate / signal），不用 taskkill —— 本套测试必须能在
Windows 与 WSL2/Linux 两边原样运行（T29 §双环境）。
"""
from __future__ import annotations

import calendar
import importlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                  # code/
RUN_DIR = os.path.join(ROOT, "run")
SCHEMA_DIR = os.path.join(os.path.dirname(ROOT), "schemas")
CANON_SCHEMA_DIR = os.path.abspath(os.path.join(ROOT, "..", "..", "..", "schemas"))
sys.path.insert(0, os.path.join(ROOT, "services"))
sys.path.insert(0, ROOT)

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, actual: str = "", expect: str = "") -> None:
    results.append((name, ok, actual))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  期望: {expect or 'ok'} | 实际: {actual}", flush=True)


def fresh_engine(tag: str = ""):
    stated = importlib.import_module("stated")
    db = os.path.join(RUN_DIR, f"_t5_{tag or uuid.uuid4().hex[:8]}.db")
    eng = stated.WorldStateEngine(db_path=db, snapshot_path=None)
    return stated, eng, db


def clean(db: str) -> None:
    for junk in (db, db + "-wal", db + "-shm"):
        if os.path.exists(junk):
            os.remove(junk)


def canon(eid: str, hh: int, mm: int, type_: str, *, content="x", entities=None,
          loc=None, conf: float = 0.9, source: str = "sim") -> dict:
    """Canonical 03 Event（stated 的输入合同）。"""
    ts = calendar.timegm(time.strptime(f"2026-09-09 {hh:02d}:{mm:02d}:00", "%Y-%m-%d %H:%M:%S"))
    return {"id": eid, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts)),
            "source": source, "type": type_, "content": content,
            "entities": list(entities or []), "location_id": loc, "confidence": conf,
            "raw_ref": f"aios://entry_queue#{eid}"}


DAY = [("evt_d01", 9, 0, "arrival", "到公司", ["place_004"], "place_004"),
       ("evt_d02", 9, 5, "person_enter", "张总进入", ["person_017"], None),
       ("evt_d03", 9, 6, "contract_discussion", "谈合同", ["contract_003"], None),
       ("evt_d04", 9, 8, "price_negotiation", "张总提出降价", ["person_017"], None),
       ("evt_d05", 9, 10, "silence", "用户沉默", [], None),
       ("evt_d06", 9, 12, "document_open", "打开合同", ["contract_003"], None),
       ("evt_d07", 9, 15, "price_negotiation", "再次谈价格", [], None)]


def day_events():
    return [canon(eid, h, m, ty, content=c, entities=en, loc=loc)
            for eid, h, m, ty, c, en, loc in DAY]


# ================================ A-F：引擎级 ================================

def test_A_chain(stated) -> None:
    _, eng, db = fresh_engine("A")
    try:
        rec = eng.apply_event(canon("evt_a1", 9, 0, "arrival", content="到公司",
                                   entities=["place_004"], loc="place_004"))
        snap = eng.snapshot()
        ok = (rec["disposition"] == stated.UPDATE_APPLIED and rec["rule"] == "LOCATION_ARRIVAL"
              and snap["location"] == {"id": "place_004"} and snap["mode"] == "WORK"
              and eng.version() == 1 and snap["timestamp"].endswith("09:00:00+00:00"))
        record("A Event→World Update→World State 链路", ok,
               f"disposition={rec['disposition']} rule={rec['rule']} location={snap['location']} "
               f"mode={snap['mode']} version={eng.version()}", "applied + 快照前进")
    finally:
        eng.close(); clean(db)


def test_B_day_checkpoints(stated) -> None:
    _, eng, db = fresh_engine("B")
    try:
        applied = [eng.apply_event(e) for e in day_events()]
        snap = eng.snapshot()
        chg = eng.changes()
        want_types = ["LOCATION_ARRIVAL", "PARTICIPANT_ENTER", "CONTRACT_DISCUSSION", "PRICE_DISCUSSION",
                      "USER_SILENCE", "DOCUMENT_OPEN", "NEGOTIATION_ESCALATION"]
        ok = (snap["location"] == {"id": "place_004"} and "person_017" in snap["people"]
              and snap["active_situations"] == ["negotiation"] and snap["mode"] == "WORK"
              and [c["change_type"] for c in chg] == want_types
              and all(c["before"] != c["after"] for c in chg)
              and all(c["evidence_events"] for c in chg)
              and [c["window"]["end"] for c in chg] == sorted(c["window"]["end"] for c in chg))
        record("B 世界状态正确变化（09 示例日检查点）", ok,
               f"loc={snap['location']} people={snap['people']} situations={snap['active_situations']} "
               f"changes={[c['change_type'] for c in chg]}", "location=公司/people 含张总/situation=谈判")
        record("B2 before/after 与 event evidence 齐备（02 §3）",
               all(set(c["before"]) == set(c["after"]) for c in chg)
               and all(c["confidence"] >= 0 for c in chg),
               f"{len(chg)} 条 change 全部含 before/after/evidence", "每条都含")
    finally:
        eng.close(); clean(db)


def test_C_idempotence(stated) -> None:
    _, eng, db = fresh_engine("C")
    try:
        e = canon("evt_c1", 9, 5, "person_enter", content="张总进入", entities=["person_017"])
        first = eng.apply_event(e)["disposition"]
        second = eng.apply_event(e)["disposition"]
        # 同一条事件在总线上会同时以 evt.stream 与 evt.normalized 两次抵达，必须只改一次世界
        third = eng.on_bus_frame("evt.normalized", "perceptiond",
                                 {"id": "evt_c1", "ts": 1789000000, "source": "sim",
                                  "type": "person_enter", "content": "张总进入",
                                  "entities": ["person_017"]})["disposition"]
        ok = (first == stated.UPDATE_APPLIED and second == stated.UPDATE_REPLAY
              and third == stated.UPDATE_REPLAY and eng.version() == 1
              and eng.snapshot()["people"] == ["person_017"])
        record("C 重复 Event 不重复改变世界（含跨主题重复投递）", ok,
               f"{first}/{second}/{third}，version={eng.version()}", "applied/replay/replay")
    finally:
        eng.close(); clean(db)


def test_D_stale(stated) -> None:
    _, eng, db = fresh_engine("D")
    try:
        eng.apply_event(canon("evt_d9", 9, 30, "person_enter", content="小王进入", entities=["person_021"]))
        before = eng.snapshot()
        rec = eng.apply_event(canon("evt_d8", 9, 10, "person_enter", content="张总进入",
                                   entities=["person_017"]))
        ok = (rec["disposition"] == stated.UPDATE_STALE and eng.snapshot() == before
              and eng.version() == 1 and "person_017" not in eng.snapshot()["people"])
        record("D 过期 Event 不倒退世界", ok, f"disposition={rec['disposition']} version={eng.version()}",
               "stale 且快照不变")
    finally:
        eng.close(); clean(db)


def test_E_invalid(stated) -> None:
    _, eng, db = fresh_engine("E")
    try:
        eng.apply_event(canon("evt_e0", 9, 0, "arrival", content="到公司",
                             entities=["place_004"], loc="place_004"))
        baseline, ver = eng.snapshot(), eng.version()
        cases = {
            "缺字段": {"id": "evt_e1", "type": "person_enter"},
            "非 dict": 42,
            "空 id": {**canon("x", 9, 1, "arrival"), "id": ""},
            "坏时间戳": {**canon("evt_e2", 9, 1, "arrival"), "timestamp": "昨天下午"},
            "多余字段(raw_data)": {**canon("evt_e3", 9, 1, "arrival"), "raw_data": "音频字节"},
            "Raw Signal 直喂": {"signal_id": "s1", "modality": "text", "payload": {"text": "到公司"}},
        }
        got = {}
        for name, bad in cases.items():
            rec = eng.apply_event(bad)
            got[name] = rec["disposition"]
        ok = all(v == stated.UPDATE_REJECTED for v in got.values()) \
            and eng.snapshot() == baseline and eng.version() == ver \
            and eng.verify_conservation() == []
        record("E 非法/不完整 Event 不污染世界", ok, f"{got}；version 仍 = {eng.version()}",
               "全部 rejected 且快照一字不动")
        # strict 语义：被拒也要有台账可查
        lines = eng.ledger(disposition=stated.UPDATE_REJECTED)
        record("E2 被拒事件留痕（含原因码）", len(lines) == len(cases)
               and all(re.match(r"^\w+:", ln["note"] or "") for ln in lines),
               f"{len(lines)} 条 rejected 台账，note 均带原因码", "每拒一次留一行")
    finally:
        eng.close(); clean(db)


def test_F_isolation(stated) -> None:
    _, eng, db = fresh_engine("F")
    try:
        rejected = []
        for slot in sorted(stated.FORBIDDEN_SLOTS):
            try:
                stated.make_world_update("wup_x", "R", [canon("evt_f1", 9, 0, "arrival")], {slot: "v"})
            except stated.WorldUpdateError as exc:
                rejected.append((slot, exc.code))
        ok = len(rejected) == len(stated.FORBIDDEN_SLOTS) and all(c == "UPDATE_FORBIDDEN_SLOT"
                                                                  for _, c in rejected)
        record("F World State 不写 Cognition/Memory/Growth", ok,
               f"{len(rejected)}/{len(stated.FORBIDDEN_SLOTS)} 个禁写键全部被拒", "全部 UPDATE_FORBIDDEN_SLOT")
        # 非法槽位也不能通过规则表混进来
        eng.RULES_BAK = dict(stated.RULES)
        stated.RULES["belief_inject"] = lambda ev, before, ctx: ("BELIEF", {"cognition": "我以为"})
        try:
            rec = eng.apply_event(canon("evt_f2", 9, 1, "belief_inject"))
            ok2 = rec["disposition"] == stated.UPDATE_REJECTED and set(eng.snapshot()) == \
                set(json.load(open(os.path.join(SCHEMA_DIR, "world_state.json"), encoding="utf-8"))["properties"])
            record("F2 规则表越权写认知 → 被拒且不污染", ok2, f"disposition={rec['disposition']}", "rejected")
        finally:
            stated.RULES.clear(); stated.RULES.update(eng.RULES_BAK)
        # 库层面：stated 只写自己的库，绝不碰三棵树（trees.sql.md 隔离铁律 1/2）
        src = open(os.path.join(ROOT, "services", "stated.py"), encoding="utf-8").read()
        tree_refs = [w for w in ("life_tree", "cognitive_tree", "growth_tree", "memoryd",
                                 "cognitiond", "evolutiond") if w in src]
        record("F3 世界只写 run/world_state.db，不碰三棵树",
               os.path.basename(stated.DB_PATH) == "world_state.db" and tree_refs == [],
               f"DB={os.path.basename(stated.DB_PATH)} 三棵树引用={tree_refs}", "world_state.db / 无引用")
    finally:
        eng.close(); clean(db)


# ================================ I：无模型运行 ================================

def test_I_no_model(stated) -> None:
    src = open(os.path.join(ROOT, "services", "stated.py"), encoding="utf-8").read()
    imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", src, re.M)
    offenders = [m for m in imports if m.split(".")[0] in
                 {"urllib", "httpx", "requests", "socket", "api_pool", "modelrouterd", "openai",
                  "anthropic", "google", "transformers", "torch"}
                 or "model_router" in m or "modelrouter" in m]
    record("I1 stated 源码零模型/零网络依赖", offenders == [], f"imports={imports}", "无网络/模型 import")

    _, eng, db = fresh_engine("I")
    calls = {"n": 0}
    real_sock, real_conn = socket.socket, socket.create_connection
    real_open = os.open

    def tripwire(*a, **k):
        calls["n"] += 1
        raise AssertionError("Event→World 路径上不得触网/不得调模型")

    try:
        socket.socket = tripwire
        socket.create_connection = tripwire
        recs = [eng.apply_event(e) for e in day_events()]
        ok = calls["n"] == 0 and eng.counts()["expensive_model_call_count"] == 0 \
            and sum(1 for r in recs if r["disposition"] == stated.UPDATE_APPLIED) == 7
        record("I2 全天事件流在无网络/无模型下完成（tripwire 计数=0）", ok,
               f"触网调用={calls['n']} expensive_model_call_count={eng.counts()['expensive_model_call_count']} "
               f"applied={sum(1 for r in recs if r['disposition'] == stated.UPDATE_APPLIED)}/7", "0 / 0 / 7")
    finally:
        socket.socket, socket.create_connection = real_sock, real_conn
        os.open = real_open
        eng.close(); clean(db)


# ================================ 自检与 schema 一致性 ================================

def test_schemas(stated) -> None:
    pairs = [("event.json",), ("world_state.json",), ("world_change.json",)]
    same = []
    for (name,) in pairs:
        a = open(os.path.join(SCHEMA_DIR, name), "rb").read()
        b = open(os.path.join(CANON_SCHEMA_DIR, name), "rb").read()
        same.append((name, a == b))
    record("S1 主线 schema 是 Canonical 03 的逐字节副本（不得第二套定义）",
           all(ok for _, ok in same), f"{same}", "三个文件全部一致")
    props = set(json.load(open(os.path.join(SCHEMA_DIR, "event.json"), encoding="utf-8"))["properties"])
    record("S2 Event 字段与 03 完全一致", props == {"id", "timestamp", "source", "type", "content",
                                                    "entities", "location_id", "confidence", "raw_ref"},
           f"props={sorted(props)}", "03 的 9 个字段")
    record("S3 校验器不静默放宽（遇到未知关键字必须抛）", _validator_is_strict(stated), "", "抛错")


def _validator_is_strict(stated) -> bool:
    try:
        stated.validate({"x": 1}, {"type": "object", "minProperties": 5})
    except AssertionError:
        return True
    return False


def test_invariants(stated) -> None:
    _, eng, db = fresh_engine("INV")
    try:
        for e in day_events():
            eng.apply_event(e)
        eng.apply_event(day_events()[0])                       # replay（同 id 已被吸收）
        # 用没见过的新 id + 旧时间戳才落在 stale 分支：同 id 重复会先被幂等拦下，
        # 这是刻意的优先级（先"这个事件我吸不吸"，再"时间能不能改世界"）。
        eng.apply_event(canon("evt_stale_1", 9, 1, "person_enter", content="早到的张总",
                             entities=["person_099"]))         # stale
        eng.apply_event({"junk": True})                        # rejected
        eng.apply_event(canon("evt_un", 9, 40, "unrecognized", content="用户在阳台浇花"))  # no_rule
        c = eng.counts()
        ok = (eng.verify_conservation() == [] and eng.verify_traceability() == []
              and eng.verify_slot_isolation() == []
              and c[stated.UPDATE_NO_RULE] == 1 and c[stated.UPDATE_REPLAY] == 1
              and c[stated.UPDATE_STALE] == 1 and c[stated.UPDATE_REJECTED] == 1
              and c[stated.UPDATE_APPLIED] == 7
              and sum(c[k] for k in stated.DISPOSITIONS) == c["attempted"])
        record("N1 守恒不变式：每次尝试恰好一个下落", ok, json.dumps(c, sort_keys=True),
               "合计==attempted 且三项自检为空")
        record("N2 无模板事件不丢弃也不改世界（08 E）",
               eng.ledger(disposition=stated.UPDATE_NO_RULE)
               and eng.version() == 7,
               f"no_rule 台账 {len(eng.ledger(disposition=stated.UPDATE_NO_RULE))} 条，version={eng.version()}",
               "有台账且世界未变")
    finally:
        eng.close(); clean(db)


def test_replay_determinism(stated) -> None:
    path = os.path.join(RUN_DIR, "_t5_replay_input.jsonl")
    try:
        with open(path, "w", encoding="utf-8") as f:
            for e in day_events() + [day_events()[0]]:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        sha = []
        for _ in range(2):
            r = subprocess.run([sys.executable, os.path.join(ROOT, "services", "stated.py"),
                                "--replay-jsonl", path], capture_output=True, text=True, timeout=60)
            data = json.loads(r.stdout)
            sha.append(data["pass1"]["state_sha"])
            ok0 = r.returncode == 0 and data["replay_identical"] and data["events"] == 8
        record("R1 --replay-jsonl 两遍 state_sha 逐字节一致（含重复事件）",
               ok0 and len(set(sha)) == 1 and sha[0], f"sha={sha[0][:16]}… 两遍一致", "replay_identical=true")
    finally:
        for p in (path,):
            if os.path.exists(p):
                os.remove(p)


# ================================ G/H：真总线 + 真进程 ================================

def _free_port_probe(port: int = 7800) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def test_G_live_stack(stated) -> None:
    """G/H：真总线 + hublinkd + perceptiond + stated + entityd + simd 播放一整天事件流。

    这是"完整一天时间线可以运行"与"进程重启后世界仍在"的硬证据（不是 mock）。
    """
    if not _free_port_probe():
        record("G 真总线一天时间线", False, "127.0.0.1:7800 已被占用（本机已有 AIOS 栈在跑）",
               "端口空闲")
        return
    script = os.path.join(RUN_DIR, "_t5_day.json")
    entries = [{"delay_s": 0.0, "topic": f"evt.sim.{t}",
                "event": {"id": eid, "ts": calendar.timegm(time.strptime(
                              f"2026-09-09 {h:02d}:{m:02d}:00", "%Y-%m-%d %H:%M:%S")),
                          "source": "sim", "type": t, "content": c, "entities": en,
                          **({"location_id": loc} if loc else {})}}
               for eid, h, m, t, c, en, loc in DAY]
    with open(script, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)

    db = os.path.join(RUN_DIR, "world_state.db")
    snap = os.path.join(RUN_DIR, "world_state.json")
    ent_db = os.path.join(RUN_DIR, "entity_store.db")
    procs = []
    try:
        for junk in (db, ent_db):
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(junk + suffix):
                    os.remove(junk + suffix)
        if os.path.exists(snap):
            os.remove(snap)
        logf = open(os.path.join(RUN_DIR, "_t5_stack.log"), "w", encoding="utf-8")
        for args in (["bus/aios_busd.py"], ["services/hublinkd.py"], ["services/perceptiond.py"],
                     ["services/entityd.py"], ["services/stated.py"]):
            procs.append(subprocess.Popen([sys.executable] + args, cwd=ROOT, stdout=logf,
                                          stderr=subprocess.STDOUT))
            time.sleep(0.25)
        time.sleep(1.2)
        r = subprocess.run([sys.executable, "simulator/simd.py", "--script", script, "--loop", "1"],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        time.sleep(2.0)                                        # 让链路把队列排空
        have_db = os.path.exists(db)
        state, changes, counts = {}, [], {}
        if have_db:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM world_state ORDER BY version DESC LIMIT 1").fetchone()
            if row:
                state = json.loads(row["state_json"])
            changes = [dict(r_) for r_ in conn.execute(
                "SELECT change_type,window_start,window_end,before_json,after_json,evidence_json "
                "FROM world_change ORDER BY version")]
            counts = dict(conn.execute("SELECT disposition,COUNT(*) FROM world_update GROUP BY disposition"))
            applied = conn.execute("SELECT COUNT(*) FROM applied_event").fetchone()[0]
            conn.close()
        else:
            applied = 0
        snap_ok = os.path.exists(snap) and json.load(open(snap, encoding="utf-8")) == state
        entities = {}
        if os.path.exists(ent_db):
            ec = sqlite3.connect(ent_db); ec.row_factory = sqlite3.Row
            entities = {r["id"]: (r["kind"], r["confidence"]) for r in
                        ec.execute("SELECT id,kind,confidence FROM entities")}
            ec.close()
        ok = (len(changes) == 7 and applied == 7 and state.get("location") == {"id": "place_004"}
              and "person_017" in (state.get("people") or [])
              and state.get("active_situations") == ["negotiation"] and state.get("mode") == "WORK"
              and snap_ok)
        record("G 完整一天时间线在主线上真跑通", ok,
               f"changes={len(changes)} applied={applied} state.mode={state.get('mode')} "
               f"state.location={state.get('location')} snapshot_match={snap_ok} simd_exit={r.returncode}",
               "7 条 change + 快照文件一致")
        record("G2 幂等：同一事件经 evt.stream 与 evt.normalized 两次抵达，世界只改一次",
               counts.get(stated.UPDATE_APPLIED, 0) == 7 and counts.get(stated.UPDATE_REPLAY, 0) >= 7,
               f"台账计数={counts}", "applied=7 且 replay>=7")
        record("G3 entityd 轻量配合：被引用实体落 UNKNOWN 占位",
               bool(entities) and all(v[1] == 0.0 for v in entities.values()),
               f"entities={entities}", "confidence 恒 0.0")
        # ---- H：杀掉 stated 进程再拉起（真重启），世界必须还在且不重复改写 ----
        stated_proc = procs[-1]
        stated_proc.terminate()
        stated_proc.wait(timeout=10)
        before = dict(counts)
        again = subprocess.Popen([sys.executable, "services/stated.py"], cwd=ROOT,
                                 stdout=open(os.path.join(RUN_DIR, "_t5_stated2.log"), "a", encoding="utf-8"),
                                 stderr=subprocess.STDOUT)
        procs[-1] = again
        time.sleep(1.5)
        r2 = subprocess.run([sys.executable, "simulator/simd.py", "--script", script, "--loop", "1"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
        time.sleep(2.0)
        conn = sqlite3.connect(db)
        n_changes = conn.execute("SELECT COUNT(*) FROM world_change").fetchone()[0]
        new_counts = dict(conn.execute("SELECT disposition,COUNT(*) FROM world_update GROUP BY disposition"))
        conn.close()
        ok = (n_changes == 7 and new_counts.get(stated.UPDATE_REPLAY, 0) > before.get(stated.UPDATE_REPLAY, 0)
              and json.load(open(snap, encoding="utf-8")) == state)
        record("H 进程重启后世界快照仍在且重放不重复改写", ok,
               f"changes={n_changes}（重启后未增长）replay_skipped {before.get(stated.UPDATE_REPLAY)}→"
               f"{new_counts.get(stated.UPDATE_REPLAY)}，快照 state_sha 不变", "只增台账不增 change")
        r2_ok = r2.returncode == 0
        if not r2_ok:
            record("H2 第二轮 simd 正常退出", False, f"exit={r2.returncode} {r2.stderr[-200:]}", "exit 0")
    finally:
        for pr in procs:
            try:
                pr.terminate()
            except Exception:
                pass
        time.sleep(0.4)
        for pr in procs:
            try:
                pr.wait(timeout=3)
            except Exception:
                try:
                    pr.kill()
                except Exception:
                    pass
        # 取证纪律：G/H 有任何一项失败就保留栈日志尾巴，别把现场删了
        failed = [n for n, ok, _ in results if not ok and (n.startswith("G") or n.startswith("H"))]
        logpath = os.path.join(RUN_DIR, "_t5_stack.log")
        if failed and os.path.exists(logpath):
            tail = open(logpath, encoding="utf-8").read().strip().splitlines()[-8:]
            print("   └ 失败时栈日志:", *tail, sep="\n     ")
        for junk in (script, None if failed else logpath, os.path.join(RUN_DIR, "_t5_stated2.log")):
            if junk and os.path.exists(junk):
                os.remove(junk)


def main() -> int:
    fast = "--fast" in sys.argv
    print("=" * 66)
    print("AIOS Sprint1 Task 5 验收：Event → World Update → World State（主线 aios/01_os）")
    print("=" * 66)
    os.makedirs(RUN_DIR, exist_ok=True)
    stated = importlib.import_module("stated")
    test_A_chain(stated)
    test_B_day_checkpoints(stated)
    test_C_idempotence(stated)
    test_D_stale(stated)
    test_E_invalid(stated)
    test_F_isolation(stated)
    test_I_no_model(stated)
    test_schemas(stated)
    test_invariants(stated)
    test_replay_determinism(stated)
    if not fast:
        test_G_live_stack(stated)
    passed = sum(1 for _, ok, _ in results if ok)
    print("=" * 66)
    for name, ok, actual in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"Task 5 验收结果: {passed}/{len(results)} 项通过")
    print("=" * 66)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
