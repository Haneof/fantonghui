# -*- coding: utf-8 -*-
"""evolutiond · 进化系统（M3 · T18 Intervention Regret 对账闭环 + 成长树唯一写者）
- 成长树唯一写者：run/growth_tree.db（SQLite WAL + synchronous=NORMAL）
  - growth 表：每次介入反馈的完整对账记录
  - strategy_versions 表：阈值策略版本链（active 唯一，可回退）
- 订阅：evt.intervention、sys.interact.feedback、sys.evolve.rollback
- 阈值模型（内存 + strategy_versions 落库）：按 risk_class 维护（0-1，越高越谨慎）
  初值与步长**全部来自 policies_v0.json**（经 code/policy.py 唯一入口读取，代码内无兜底默认值）：
  evolve.prior.social=0.5 / prior.financial=0.8 / prior.safety=0.1 / prior.unknown=0.5
  evolve.delta.accepted=-0.05 / delta.rejected=+0.15 / delta.ignored=+0.02
  夹逼区间 evolve.tune_floor=0.05 / tune_ceiling=0.95
- 安全类豁免（§4.2-6 / 验收 F）：risk_class=SAFETY 时**不做阈值调整**，只记 growth 账。
  接线前实测：连续 100 次 rejected 把 SAFETY 从 0.1 学到 0.95——安全介入被「嫌烦」学成沉默，属 P0 违宪
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
import policy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "run", "growth_tree.db")

# 策略数字一律走注册表（T1/T2）。本文件不再保留任何数值字面量当默认值：
# 注册表缺失时 policy 当场报错，宁可不开跑，也不要一份「备用默认值」把写死偷偷带回来。
RISK_PRIOR = {"SOCIAL": "evolve.prior.social", "FINANCIAL": "evolve.prior.financial",
              "SAFETY": "evolve.prior.safety"}
FEEDBACK_KNOB = {"accepted": "evolve.delta.accepted", "rejected": "evolve.delta.rejected",
                 "ignored": "evolve.delta.ignored"}
KNOB_CLAMP_LOW, KNOB_CLAMP_HIGH = "evolve.tune_floor", "evolve.tune_ceiling"
KNOB_SAFETY_EXEMPT = "evolve.safety_regret_exempt"
KNOB_CACHE_MAX = "evolve.intervention_cache_max"
KNOB_PRIOR_UNKNOWN = "evolve.prior.unknown"


def prior(risk_class):
    """某 risk_class 的起始谨慎度（现读注册表，改完下次调用就跟）。"""
    return policy.get(RISK_PRIOR.get(risk_class, KNOB_PRIOR_UNKNOWN))


def default_thresholds():
    return {rc: prior(rc) for rc in RISK_PRIOR}

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
    "thresholds": default_thresholds(),      # risk_class -> 当前阈值（初值取自注册表）
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
    for rc, thr in default_thresholds().items():
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
def _clamp(cur, feedback, risk_class=None):
    """反馈 → 新阈值。步长与夹逼区间全部现读注册表（改了不重启，下一次调节就生效）。

    安全类豁免：risk_class=SAFETY 且 evolve.safety_regret_exempt 为真时原值返回——
    「用户嫌烦」不得把安全介入学成沉默（V1.4 §4.2-6；验收 F 要求 100 次后与第一天逐位相同）。
    """
    if risk_class == "SAFETY" and policy.get(KNOB_SAFETY_EXEMPT):
        return round(cur, 2)
    delta = policy.get(FEEDBACK_KNOB.get(feedback, "evolve.delta.ignored"))
    low, high = policy.get(KNOB_CLAMP_LOW), policy.get(KNOB_CLAMP_HIGH)
    return round(max(low, min(high, cur + delta)), 2)


def apply_feedback(state, conn, intervention_id, feedback, risk_class, meta=None, now=None):
    """对一条介入反馈做对账：调整阈值、写 growth + strategy_versions，返回回复 dict。
    - state["thresholds"]：内存阈值；risk_class 由调用方从 evt.intervention 缓存解析。
    - 每次变更：growth 表一条 + strategy_versions 新行（active=1，旧行 active=0）。
    """
    feedback = feedback if feedback in FEEDBACK_KNOB else "ignored"
    now = now if now is not None else time.time()
    meta = meta or {}
    thresholds = state["thresholds"]
    risk_class = risk_class or "UNKNOWN"

    old = thresholds.get(risk_class, prior(risk_class))
    exempt = (risk_class == "SAFETY" and bool(policy.get(KNOB_SAFETY_EXEMPT)))
    new = _clamp(old, feedback, risk_class)
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
         _ERROR_ANALYSIS.get(feedback, ""),
         ("安全类豁免 Regret：阈值保持 %s 不动（§4.2-6）" % old) if exempt else _LESSON.get(feedback, ""),
         "%s:%s->%s%s" % (risk_class, old, new, "(safety_exempt)" if exempt else ""), new, now))

    conn.execute("UPDATE strategy_versions SET active=0 WHERE strategy_key=?", (risk_class,))
    conn.execute("INSERT INTO strategy_versions "
                 "(strategy_key, threshold, reason, created_at, active) VALUES (?,?,?,?,1)",
                 (risk_class, new, ("feedback:%s:safety_exempt" if exempt else "feedback:%s") % feedback, now))
    conn.commit()
    return {"risk_class": risk_class, "threshold": new, "was_correct": bool(was_correct),
            "safety_exempt": exempt}


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
        return {"rolled_back": False, "threshold": thresholds.get(strategy_key, prior(strategy_key))}

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
        # 防膨胀：超上限丢弃最旧一半（上限 = evolve.intervention_cache_max，注册表可配）
        cap = int(policy.get(KNOB_CACHE_MAX))
        if len(_state["interventions"]) > cap:
            for k in list(_state["interventions"].keys())[:cap // 2]:
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

    st = {"thresholds": default_thresholds()}
    seed_and_load(st, conn)

    fails = []
    tally = {"n": 0}          # 计数实算：以前这里硬写 15/15，加断言也不会变——假计数比没计数更糟

    def check(name, got, want):
        tally["n"] += 1
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

    # 边界：rejected 撞天花板 / accepted 撞地板（用 FINANCIAL、SOCIAL 测——SAFETY 已豁免学习，拿它测边界是错的口径）
    stb = {"thresholds": {"FINANCIAL": 0.9, "SOCIAL": 0.06}}
    r3 = apply_feedback(stb, conn, "i-3", "rejected", "FINANCIAL", {})
    check("rejected 撞天花板 0.95", r3["threshold"], 0.95)
    r4 = apply_feedback(stb, conn, "i-4", "accepted", "SOCIAL", {})
    check("accepted 撞地板 0.05", r4["threshold"], 0.05)

    # 验收 F 的核心断言（本批补）：安全类被反复嫌烦也不许漂移，但账必须照记
    sts = {"thresholds": {"SAFETY": prior("SAFETY")}}
    day1 = sts["thresholds"]["SAFETY"]
    for i in range(100):
        apply_feedback(sts, conn, "s-%d" % i, "rejected", "SAFETY", {})
    check("100 次嫌烦后 SAFETY 阈值仍等于第一天", sts["thresholds"]["SAFETY"], day1)
    n_exempt_rows = conn.execute(
        "SELECT COUNT(*) FROM growth WHERE strategy_update LIKE '%safety_exempt%'").fetchone()[0]
    check("豁免期间 growth 照记 100 条", n_exempt_rows >= 100, True)

    # 无上一版本时 rollback 不翻车
    r0 = rollback({"thresholds": {"GHOST": 0.5}}, conn, "GHOST")
    check("无版本 rollback=false", r0["rolled_back"], False)

    # 清理（SQL 级清空，不删文件）
    conn.execute("DELETE FROM growth")
    conn.execute("DELETE FROM strategy_versions")
    conn.commit()
    conn.close()

    if fails:
        print("SELFTEST FAILED: %s（共 %d 项，通过 %d 项）" % (fails, tally["n"], tally["n"] - len(fails)))
        sys.exit(1)
    print("SELFTEST PASSED (%d/%d)" % (tally["n"], tally["n"]))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        seed_and_load(_state, db())
        svc.log("服务启动（M3 · T18 进化系统：Intervention Regret 对账闭环 + 成长树）")
        svc.run()
