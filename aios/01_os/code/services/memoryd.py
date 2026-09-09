# -*- coding: utf-8 -*-
"""memoryd v3 · 记忆系统（人生树 + 递归摘要金字塔）
用户裁定（2026-09-09 05:53）：层级摘要必须是递归金字塔——
  L1 分钟总结 = 该分钟原始事件的凝缩
  L2 小时总结 = 60 份分钟总结的凝缩（输入只有分钟总结，不看原始事件）
  L3 日总结   = 当天全部小时总结的凝缩
  L4 周总结   = 7 份日总结的凝缩
  L5 月总结   = 当月全部日总结的凝缩
  L6 季度总结 = 3 份月总结的凝缩
每一层只吃上一层的产出 → 每层输入规模有界 → 未来接真 LLM 时 token 成本可控。
原始事件（raw_log）永远不直接进入 L2 以上的摘要。
"""
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

# 云端大模型（用户裁定：日总结及以上全部用大模型；本地只做底层提炼与触发判断）
try:
    from api_pool.gemini_pool import GeminiPool
    POOL = GeminiPool(model="gemini-flash-latest")
except Exception:
    POOL = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "run", "life_tree.db")
svc = AIOSService("memoryd", subscribe=[
    "evt.normalized", "sys.query.life", "sys.query.summary",
    "sys.cmd.summarize", "sys.cmd.rebuild_pyramid"])

_conn = None


def db():
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript("""
CREATE TABLE IF NOT EXISTS raw_log (
  id TEXT PRIMARY KEY, timestamp_s REAL NOT NULL, source TEXT NOT NULL,
  type TEXT NOT NULL, content TEXT NOT NULL, speaker TEXT, entities TEXT,
  mode_at_time TEXT, privacy_level INTEGER, entry_topic TEXT, correction_of TEXT);
CREATE INDEX IF NOT EXISTS idx_raw_ts ON raw_log(timestamp_s);
CREATE TABLE IF NOT EXISTS summary (
  id TEXT PRIMARY KEY, level TEXT NOT NULL,
  period_key TEXT NOT NULL, period_start REAL NOT NULL, period_end REAL NOT NULL,
  content TEXT NOT NULL, children TEXT NOT NULL, sources INTEGER NOT NULL,
  generated_at REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sum_lvl_pk ON summary(level, period_key);
""")
        # 旧表迁移：补 children/period_key/sources 列（旧库平滑升级）
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(summary)").fetchall()]
        if "children" not in cols:
            try:
                _conn.execute("DELETE FROM summary")   # 旧格式摘要全量废弃，重建金字塔
                _conn.execute("ALTER TABLE summary ADD COLUMN children TEXT NOT NULL DEFAULT '[]'")
                _conn.execute("ALTER TABLE summary ADD COLUMN sources INTEGER NOT NULL DEFAULT 0")
                _conn.execute("ALTER TABLE summary ADD COLUMN period_key TEXT NOT NULL DEFAULT ''")
                _conn.commit()
            except Exception:
                pass
    return _conn


def insert_event(ev):
    db().execute(
        "INSERT OR REPLACE INTO raw_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ev["id"], float(ev["ts"]), ev.get("source", "unknown"),
         ev.get("type", "unknown"), ev.get("content", ""),
         ev.get("speaker", "unknown"),
         json.dumps(ev.get("entities", []), ensure_ascii=False),
         ev.get("mode_at_time", "unknown"),
         int(ev.get("privacy_level", 1)),
         ev.get("entry_topic", ""), ev.get("correction_of")))
    db().commit()


def query(q):
    q = q or {}
    sql = "SELECT id, timestamp_s, source, type, content, speaker, entities FROM raw_log WHERE 1=1"
    args = []
    if q.get("from_ts") is not None:
        sql += " AND timestamp_s >= ?"; args.append(float(q["from_ts"]))
    if q.get("to_ts") is not None:
        sql += " AND timestamp_s <= ?"; args.append(float(q["to_ts"]))
    if q.get("type"):
        sql += " AND type = ?"; args.append(q["type"])
    sql += " ORDER BY timestamp_s ASC LIMIT ?"
    args.append(int(q.get("limit", 100)))
    rows = db().execute(sql, args).fetchall()
    return [{"id": r[0], "ts": r[1], "source": r[2], "type": r[3],
             "content": r[4], "speaker": r[5], "entities": json.loads(r[6] or "[]")}
            for r in rows]


# ================= 递归摘要金字塔 =================
# 层级链：RAW → MINUTE → HOURLY → DAILY → WEEKLY → MONTHLY → QUARTERLY
# 每层只吃上一层的 summary 行（MINUTE 层吃 raw_log），period 结束后才构建。
# 层级链（用户裁定 2026-09-09）：MINUTE→HOURLY→DAILY；DAILY 分两支→WEEKLY 与 MONTHLY；MONTHLY→QUARTERLY
LEVEL_ORDER = ["MINUTE", "HOURLY", "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"]
SRC_LEVEL = {"MINUTE": None, "HOURLY": "MINUTE", "DAILY": "HOURLY",
             "WEEKLY": "DAILY", "MONTHLY": "DAILY", "QUARTERLY": "MONTHLY"}


def period_info(level, ts):
    """某时间戳在 level 层的 (period_key, period_start, period_end)。本地时区。"""
    dt = datetime.fromtimestamp(ts)
    if level == "MINUTE":
        s = dt.replace(second=0, microsecond=0)
        key = s.strftime("%Y%m%d%H%M")
        e = s + timedelta(minutes=1)
    elif level == "HOURLY":
        s = dt.replace(minute=0, second=0, microsecond=0)
        key = s.strftime("%Y%m%d%H")
        e = s + timedelta(hours=1)
    elif level == "DAILY":
        s = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        key = s.strftime("%Y%m%d")
        e = s + timedelta(days=1)
    elif level == "WEEKLY":
        monday = dt - timedelta(days=dt.weekday())
        s = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        key = s.strftime("%G-W%V")
        e = s + timedelta(weeks=1)
    elif level == "MONTHLY":
        s = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        key = s.strftime("%Y%m")
        nm = (dt.replace(day=28) + timedelta(days=6)).replace(day=1)
        e = nm
    elif level == "QUARTERLY":
        qm = (dt.month - 1) // 3 * 3 + 1
        s = dt.replace(month=qm, day=1, hour=0, minute=0, second=0, microsecond=0)
        key = f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
        qm2 = qm + 3 if qm < 10 else 13
        e = s.replace(month=qm2) if qm2 <= 12 else s.replace(year=s.year + 1, month=1)
    else:
        raise ValueError(level)
    return key, s.timestamp(), e.timestamp()


def condense(level, items):
    """各层凝缩。用户裁定：MINUTE/HOURLY 用本地模型或规则（底层提炼）；
    DAILY 及以上必须用云端大模型真写（规则仅作云端失败时的降级）。"""
    n = len(items)
    heads = [c if len(c) <= 60 else c[:60] + "…" for _, _, _, c in items[:30]]
    if level in ("DAILY", "WEEKLY", "MONTHLY", "QUARTERLY") and POOL is not None:
        try:
            return cloud_write(level, items, heads)
        except Exception as e:
            svc.log(f"[降级] {level} 云端写作失败，规则版兑底: {e}")
    return f"{level}共{n}项来源；要点：" + "；".join(heads)


CLOUD_PROMPT = {
    "DAILY": "以下是林川某天按小时排列的记录摘要。请写一份不超过120字的当日日记：今天发生了什么、见了谁、有什么值得注意的（健康/情绪/承诺/异常）。用自然中文，不编造记录里没有的事实。\n记录：\n",
    "WEEKLY": "以下是林川某周各天的日记。请写一份不超过150字的周记：本周主线、人际动态、健康趋势、未完成的承诺。\n记录：\n",
    "MONTHLY": "以下是林川某月各天的日记。请写一份不超过200字的月度报告：本月主线、与重要人物的关系统计、健康/消费趋势、情绪状态。\n记录：\n",
    "QUARTERLY": "以下是林川某季度的各月报告。请写一份不超过250字的季度回顾：主线、人物关系变化、成长与风险。\n记录：\n",
}


def cloud_write(level, items, heads):
    """云端大模型真写（Gemini 轮换池）。失败抛异常由 condense 降级。"""
    lines = "\n".join(f"{i+1}. {c}" for i, c in enumerate(heads))
    prompt = CLOUD_PROMPT[level] + lines
    text = POOL.chat("你是 AIOS 腕上终端的记忆引擎。", prompt)
    return f"[AI] {text}"


def build_level(level):
    """构建某一层：吃上一层的 summary 行（MINUTE 层吃 raw_log），
    按 level 的 period 分组，period 已完结且无该层摘要的 → 凝缩入库。返回新建数。"""
    idx = LEVEL_ORDER.index(level)
    now = time.time()
    made = 0
    if level == "MINUTE":
        # 来源：全部原始事件（含历史），按分钟分组
        rows = db().execute("SELECT id, timestamp_s, type, content FROM raw_log ORDER BY timestamp_s").fetchall()
        groups = {}
        for rid, ts, typ, content in rows:
            key, ps, pe = period_info("MINUTE", ts)
            groups.setdefault(key, {"start": ps, "end": pe, "items": []})
            groups[key]["items"].append((rid, ts, typ, content))
        existing = {r[0] for r in db().execute(
            "SELECT period_key FROM summary WHERE level='MINUTE'").fetchall()}
        for key, g in sorted(groups.items()):
            if key in existing or g["end"] > now:      # 未完结不摘要
                continue
            items = [(i, t, 0, f"[{typ}] {content}") for i, t, typ, content in g["items"]]
            content = condense("本分钟", items)
            db().execute("INSERT OR REPLACE INTO summary VALUES (?,?,?,?,?,?,?,?,?)",
                         (str(uuid.uuid4()), "MINUTE", key, g["start"], g["end"],
                          content, json.dumps([i for i, *_ in g["items"]]),
                          len(items), time.time()))
            made += 1
        db().commit()
        return made
    # 上层：来源 = 上一层的 summary 行（父级关系按用户裁定：周/月均吃日总结）
    src_level = SRC_LEVEL[level]
    rows = db().execute(
        "SELECT id, period_key, period_start, period_end, content FROM summary "
        "WHERE level=? ORDER BY period_start", (src_level,)).fetchall()
    groups = {}
    for sid, pkey, ps, pe, content in rows:
        key, gps, gpe = period_info(level, ps)
        groups.setdefault(key, {"start": gps, "end": gpe, "items": []})
        groups[key]["items"].append((sid, ps, pe, content))
    existing = {r[0] for r in db().execute(
        "SELECT period_key FROM summary WHERE level=?", (level,)).fetchall()}
    for key, g in sorted(groups.items()):
        if key in existing or g["end"] > now:
            continue
        items = g["items"]
        content = condense(level, items)
        db().execute("INSERT OR REPLACE INTO summary VALUES (?,?,?,?,?,?,?,?,?)",
                     (str(uuid.uuid4()), level, key, g["start"], g["end"],
                      content, json.dumps([i for i, *_ in items]),
                      len(items), time.time()))
        made += 1
    db().commit()
    return made


def build_pyramid():
    """按依赖顺序逐层构建整座金字塔（幂等）。DAILY+ 层走云端真写，在独立线程内执行。"""
    counts = {}
    for level in LEVEL_ORDER:
        counts[level] = build_level(level)
    return counts


def on_event(topic, from_svc, msg):
    if topic == "evt.normalized":
        insert_event(msg)
    elif topic == "sys.query.life":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        svc.publish(f"evt.query.reply.{req_id}", {"results": query(msg.get("q", {}))})
    elif topic == "sys.query.summary":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        lvl = (msg or {}).get("level", "DAILY")
        rows = db().execute(
            "SELECT level, period_key, period_start, content, children, sources FROM summary "
            "WHERE level=? ORDER BY period_start DESC LIMIT ?",
            (lvl, int((msg or {}).get("limit", 10)))).fetchall()
        out = [{"level": r[0], "period": r[1], "start": r[2], "content": r[3],
                "children": json.loads(r[4]), "sources": r[5]} for r in rows]
        svc.publish(f"evt.query.reply.{req_id}", {"results": out})
    elif topic == "sys.cmd.summarize":
        req_id = str(msg.get("req_id", "tick"))
        counts = build_pyramid()
        svc.publish(f"evt.query.reply.{req_id}", {"built": counts})
    elif topic == "sys.cmd.rebuild_pyramid":
        # 云端真写耗时（107 次 Gemini 调用），放独立线程执行避免阻塞读线程
        def _do_rebuild():
            try:
                counts = build_pyramid()
                svc.publish("evt.pyramid.rebuilt", {"counts": counts})
            except Exception as e:
                svc.log(f"[异常] 重建: {e}")
        threading.Thread(target=_do_rebuild, daemon=True).start()


svc.on_event = on_event


def _tick():
    """周期构建：每 30s 幂等地补齐所有已完结周期的摘要。"""
    while True:
        time.sleep(30)
        try:
            build_pyramid()
        except Exception as e:
            svc.log(f"[异常] 金字塔构建: {e}")


threading.Thread(target=_tick, daemon=True).start()
svc.log("服务启动（M2.5 · 递归摘要金字塔：分钟→小时→日→周→月→季）")
svc.run()
