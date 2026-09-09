# -*- coding: utf-8 -*-
"""evolutiond · 进化系统（M3 · T18 Intervention Regret 对账闭环 + 成长树唯一写者）
- 成长树唯一写者：run/growth_tree.db（SQLite WAL + synchronous=NORMAL）
  - growth 表：每次介入反馈的完整对账记录
  - strategy_versions 表：阈值策略版本链（active 唯一，可回退）
- 订阅：evt.intervention、sys.interact.feedback、sys.evolve.rollback
- 阈值模型（内存 + strategy_versions 落库）：按 risk_class 维护（0-1，越高越谨慎）
  初值 SOCIAL=0.5 / FINANCIAL=0.8 / SAFETY=0.1
  accepted→-0.05(下限 0.05)；rejected→+0.15(上限 0.95)；ignored→中性 +0.02
- 三棵树物理隔离：本服务只写 growth_tree.db（人生树 memoryd / 认知树 cognitiond）
"""
import json
import os
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "run", "growth_tree.db")

# 阈值初值（0-1，越高越谨慎）
DEFAULT_THRESHOLDS = {"SOCIAL": 0.5, "FINANCIAL": 0.8, "SAFETY": 0.1}
DEFAULT_UNKNOWN = 0.5          # 未知 risk_class 的兜底阈值
THRESHOLD_LOW = 0.05
THRESHOLD_HIGH = 0.95
FEEDBACK_DELTA = {"accepted": -0.05, "rejected": +0.15, "ignored": +0.02}

SCHEMA = """
CREATE TABLE IF NOT EXISTS growth (
  id TEXT PRIMARY KEY, situation TEXT, ai_judgment TEXT, ai_action TEXT,
  user_feedback TEXT, actual_result TEXT, was_correct INTEGER,
  error_analysis TEXT, lesson TEXT, strategy_update TEXT, confidence REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS strategy_versions (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_key TEXT,
  threshold REAL, reason TEXT, created_at REAL, active INTEGER);
CREATE INDEX IF NOT EXISTS idx_sv_key ON strategy_versions(strategy_key);
"""

_ERROR_ANALYSIS = {
    "accepted": "",
    "rejected": "介入判断过于激进，被用户拒绝",
    "ignored": "介入未被采纳（用户忽略）",
}
_LESSON = {
    "accepted": "介入得到认可，适度下调谨慎度",
    "rejected": "上调谨慎度，减少同类介入",
    "ignored": "微调谨慎度，压低低价值介入",
}

svc = AIOSService("evolutiond",
                  subscribe=["evt.intervention", "sys.interact.feedback", "sys.evolve.rollback"])

_conn = None
_state = {
    "thresholds": dict(DEFAULT_THRESHOLDS),  # risk_class -> 当前阈值（内存模型）
    "interventions": {},                     # intervention_id -> {risk_class, channel, priority, ts}
    "last": {},                              # 最近一次介入（兜底映射）
}


# ---------------- 数据库 ----------------
def _connect(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")   # WAL 下 NORMAL：不逐条 fsync，吞吐数量级提升
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def db():
    global _conn
    if _conn is None:
        _conn = _connect(DB_PATH)
    return _conn


def seed_and_load(state, conn):
    """补齐初值版本（缺则插 active=1），并从 DB 恢复当前 active 阈值到内存。
    重启后经此恢复上次策略状态（内存 + 落库一致）。
    """
    for rc, thr in DEFAULT_THRESHOLDS.items():
        row = conn.execute("SELECT 1 FROM strategy_versions WHERE strategy_key=? LIMIT 1",
                           (rc,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO strategy_versions "
                         "(strategy_key, threshold, reason, created_at, active) "
                         "VALUES (?,?,?,?,1)", (rc, thr, "initial", time.time()))
    conn.commit()
    for key, thr in conn.execute(
            "SELECT strategy_key, threshold FROM strategy_versions WHERE active=1").fetchall():
        state["thresholds"][key] = thr


# ---------------- 阈值对账核心 ----------------
def _clamp(cur, feedback):
    delta = FEEDBACK_DELTA.get(feedback, FEEDBACK_DELTA["ignored"])
    return round(max(THRESHOLD_LOW, min(THRESHOLD_HIGH, cur + delta)), 2)


def apply_feedback(state, conn, intervention_id, feedback, risk_class, meta=None, now=None):
    """对一条介入反馈做对账：调整阈值、写 growth + strategy_versions，返回回复 dict。
    - state["thresholds"]：内存阈值；risk_class 由调用方从 evt.intervention 缓存解析。
    - 每次变更：growth 表一条 + strategy_versions 新行（active=1，旧行 active=0）。
    """
    feedback = feedback if feedback in FEEDBACK_DELTA else "ignored"
    now = now if now is not None else time.time()
    meta = meta or {}
    thresholds = state["thresholds"]
    risk_class = risk_class or "UNKNOWN"

    old = thresholds.get(risk_class, DEFAULT_UNKNOWN)
    new = _clamp(old, feedback)
    thresholds[risk_class] = new
    was_correct = 1 if feedback == "accepted" else 0

    conn.execute(
        "INSERT INTO growth (id, situation, ai_judgment, ai_action, user_feedback, "
        "actual_result, was_correct, error_analysis, lesson, strategy_update, "
        "confidence, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), "intervention:%s" % risk_class,
         json.dumps({"channel": meta.get("channel", ""), "priority": meta.get("priority", "")},
                    ensure_ascii=False),
         str(intervention_id or ""), feedback, feedback, was_correct,
         _ERROR_ANALYSIS.get(feedback, ""), _LESSON.get(feedback, ""),
         "%s:%s->%s" % (risk_class, old, new), new, now))

    conn.execute("UPDATE strategy_versions SET active=0 WHERE strategy_key=?", (risk_class,))
    conn.execute("INSERT INTO strategy_versions "
                 "(strategy_key, threshold, reason, created_at, active) VALUES (?,?,?,?,1)",
                 (risk_class, new, "feedback:%s" % feedback, now))
    conn.commit()
    return {"risk_class": risk_class, "threshold": new, "was_correct": bool(was_correct)}


def rollback(state, conn, strategy_key):
    """回退 strategy_key（= risk_class）到上一 active 版本，返回回复 dict。
    无上一版本（仅初值或无记录）→ rolled_back=false，返回当前阈值。
    """
    thresholds = state["thresholds"]
    active_row = conn.execute(
        "SELECT version_id, threshold FROM strategy_versions "
        "WHERE strategy_key=? AND active=1 ORDER BY version_id DESC LIMIT 1",
        (strategy_key,)).fetchone()
    if active_row is None:
        return {"rolled_back": False, "threshold": thresholds.get(strategy_key, DEFAULT_UNKNOWN)}

    prev_row = conn.execute(
        "SELECT version_id, threshold FROM strategy_versions "
        "WHERE strategy_key=? AND active=0 ORDER BY version_id DESC LIMIT 1",
        (strategy_key,)).fetchone()
    if prev_row is None:
        return {"rolled_back": False, "threshold": active_row[1]}

    conn.execute("UPDATE strategy_versions SET active=0 WHERE strategy_key=?", (strategy_key,))
    conn.execute("UPDATE strategy_versions SET active=1 WHERE version_id=?", (prev_row[0],))
    conn.commit()
    thresholds[strategy_key] = prev_row[1]
    return {"rolled_back": True, "threshold": prev_row[1]}


# ---------------- 事件回调 ----------------
def on_event(topic, from_svc, msg):
    if topic == "evt.intervention":
        iid = str(msg.get("intervention_id", uuid.uuid4()))
        meta = {"risk_class": msg.get("risk_class", ""),
                "channel": msg.get("channel", ""),
                "priority": msg.get("priority", ""),
                "ts": msg.get("ts", time.time())}
        _state["interventions"][iid] = meta
        _state["last"] = meta
        # 防膨胀：缓存超 1000 条丢弃最旧一半
        if len(_state["interventions"]) > 1000:
            for k in list(_state["interventions"].keys())[:500]:
                _state["interventions"].pop(k, None)
    elif topic == "sys.interact.feedback":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        iid = str(msg.get("intervention_id", ""))
        feedback = str(msg.get("feedback", "ignored"))
        meta = _state["interventions"].get(iid) or _state["last"] or {}
        risk_class = meta.get("risk_class") or "UNKNOWN"
        reply = apply_feedback(_state, db(), iid, feedback, risk_class, meta)
        svc.log("反馈对账 %s: %s %s->%s was_correct=%s" %
                (risk_class, feedback, "?",
                 reply["threshold"], reply["was_correct"]))
        svc.publish("evt.query.reply.%s" % req_id, reply)
    elif topic == "sys.evolve.rollback":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        strategy_key = str(msg.get("strategy_key", ""))
        reply = rollback(_state, db(), strategy_key)
        svc.log("策略回退 %s: rolled_back=%s threshold=%s" %
                (strategy_key or "(空)", reply["rolled_back"], reply["threshold"]))
        svc.publish("evt.query.reply.%s" % req_id, reply)


svc.on_event = on_event


# ---------------- 内联自测（python evolutiond.py --selftest） ----------------
def _selftest():
    """手工建临时库，验证 rejected 上调 / accepted 下调 / rollback 回退 /
    strategy_versions 行数增长。清理策略：仅 SQL 级清空（DELETE），不调用任何
    文件删除 API；临时库置于系统临时目录，不污染项目 run/。
    """
    tmp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.dirname(ROOT)
    db_path = os.path.join(tmp_dir, "evolutiond_selftest_growth_tree.db")
    conn = _connect(db_path)
    conn.execute("DELETE FROM growth")
    conn.execute("DELETE FROM strategy_versions")
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name='strategy_versions'")
    except sqlite3.Error:
        pass
    conn.commit()

    st = {"thresholds": dict(DEFAULT_THRESHOLDS)}
    seed_and_load(st, conn)

    fails = []

    def check(name, got, want):
        ok = (got == want)
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            print("  got =%r" % (got,))
            print("  want=%r" % (want,))
            fails.append(name)

    def sv_count(key):
        return conn.execute(
            "SELECT COUNT(*) FROM strategy_versions WHERE strategy_key=?", (key,)).fetchone()[0]

    base = sv_count("SOCIAL")
    check("seed 后 SOCIAL 阈值=0.5", st["thresholds"]["SOCIAL"], 0.5)
    check("seed 后 SOCIAL 版本行=1", base, 1)

    # rejected → 上调 0.15
    r1 = apply_feedback(st, conn, "i-1", "rejected", "SOCIAL",
                        {"channel": "VISUAL", "priority": "low"})
    check("rejected 上调 0.5->0.65", r1["threshold"], 0.65)
    check("rejected was_correct=false", r1["was_correct"], False)
    check("rejected 后版本行 +1", sv_count("SOCIAL"), base + 1)

    # accepted → 下调 0.05
    r2 = apply_feedback(st, conn, "i-2", "accepted", "SOCIAL",
                        {"channel": "VISUAL", "priority": "low"})
    check("accepted 下调 0.65->0.60", r2["threshold"], 0.60)
    check("accepted was_correct=true", r2["was_correct"], True)
    check("accepted 后版本行 +1", sv_count("SOCIAL"), base + 2)

    # rollback → 回退到上一 active 版本（0.65）
    rb = rollback(st, conn, "SOCIAL")
    check("rollback rolled_back=true", rb["rolled_back"], True)
    check("rollback 阈值=0.65", rb["threshold"], 0.65)
    check("rollback 后内存阈值=0.65", st["thresholds"]["SOCIAL"], 0.65)

    # growth 对账行：rejected + accepted 两条
    check("growth 行数=2", conn.execute("SELECT COUNT(*) FROM growth").fetchone()[0], 2)

    # 边界：rejected 上限 0.95 / accepted 下限 0.05
    stb = {"thresholds": {"FINANCIAL": 0.9, "SAFETY": 0.08}}
    r3 = apply_feedback(stb, conn, "i-3", "rejected", "FINANCIAL", {})
    check("rejected 上限 0.95", r3["threshold"], 0.95)
    r4 = apply_feedback(stb, conn, "i-4", "accepted", "SAFETY", {})
    check("accepted 下限 0.05", r4["threshold"], 0.05)

    # 无上一版本时 rollback 不翻车
    r0 = rollback({"thresholds": {"GHOST": 0.5}}, conn, "GHOST")
    check("无版本 rollback=false", r0["rolled_back"], False)

    # 清理（SQL 级清空，不删文件）
    conn.execute("DELETE FROM growth")
    conn.execute("DELETE FROM strategy_versions")
    conn.commit()
    conn.close()

    if fails:
        print("SELFTEST FAILED: %s" % fails)
        sys.exit(1)
    print("SELFTEST PASSED (15/15)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        seed_and_load(_state, db())
        svc.log("服务启动（M3 · T18 进化系统：Intervention Regret 对账闭环 + 成长树）")
        svc.run()
