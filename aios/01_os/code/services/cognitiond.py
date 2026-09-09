# -*- coding: utf-8 -*-
"""cognitiond · 认知系统（M2 · T14 认知树唯一写者）
- 认知树唯一写者：cognitive_tree.db（SQLite WAL，synchronous=NORMAL）
- 契约：tasks/contracts_m2.md §T14 / §认知树存储
- 订阅：evt.normalized、sys.cognition.assert、sys.query.cognition
- sys.cognition.assert 校验后落库（id=uuid4），回 evt.query.reply.<req_id>
- sys.query.cognition 按 epistemic 可空过滤，evidence 存 JSON 字符串、返回时还原为列表
- 三棵树物理隔离：本服务只写 cognitive_tree.db；人生树写者 memoryd（M1）、成长树写者 evolutiond（M3）
- 对 evt.normalized：v0 仅接收，不自动推导（自动推导是 M2 后续细化）
"""
import json
import os
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # code/
DB_PATH = os.path.join(ROOT, "run", "cognitive_tree.db")
svc = AIOSService("cognitiond", subscribe=["evt.normalized", "sys.cognition.assert", "sys.query.cognition"])

_conn = None

# 认知五状态（epistemic），与 contracts_m2.md 冻结一致
EPISTEMIC_STATES = {"KNOWN", "INFERRED", "HYPOTHESIS", "UNKNOWN", "CONFLICT"}


def db():
    """惰性建立 SQLite 连接；WAL + synchronous=NORMAL（性能经验）。"""
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")   # WAL 下 NORMAL：不逐条 fsync，吞吐数量级提升
        # schema 严格按 contracts_m2.md §认知树存储
        _conn.executescript("""
CREATE TABLE IF NOT EXISTS cognition (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,   -- BELIEF / HYPOTHESIS / PREDICTION / UNKNOWN / SPEAKER_BINDING
  conclusion TEXT NOT NULL,
  confidence REAL NOT NULL,   -- 0.0–1.0，强制
  evidence   TEXT NOT NULL,   -- JSON array，引用人生树 raw_log.id 或其他认知 id
  status     TEXT NOT NULL,   -- ACTIVE / REVISED / INVALIDATED / CONFLICT
  epistemic  TEXT NOT NULL,   -- KNOWN / INFERRED / HYPOTHESIS / UNKNOWN / CONFLICT
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cog_epistemic ON cognition(epistemic);
""")
        _conn.commit()
    return _conn


def _is_number(v):
    """判断是否为数字（排除 bool，bool 是 int 子类）。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_assert(msg):
    """校验 sys.cognition.assert 载荷，返回 (ok, reason)。"""
    kind = msg.get("kind")
    conclusion = msg.get("conclusion")
    confidence = msg.get("confidence")
    evidence = msg.get("evidence")
    epistemic = msg.get("epistemic")
    if not isinstance(kind, str) or not kind.strip():
        return False, "kind 缺失或非法（须为非空字符串）"
    if not isinstance(conclusion, str) or not conclusion.strip():
        return False, "conclusion 缺失或非法（须为非空字符串）"
    if not _is_number(confidence) or not (0.0 <= float(confidence) <= 1.0):
        return False, "confidence 须为 0-1 数字"
    if not isinstance(evidence, list):
        return False, "evidence 须为列表"
    if epistemic not in EPISTEMIC_STATES:
        return False, "epistemic 非法（须为 KNOWN/INFERRED/HYPOTHESIS/UNKNOWN/CONFLICT）"
    return True, None


def insert_cognition(kind, conclusion, confidence, evidence, epistemic, status="ACTIVE"):
    """落库一条认知，返回 uuid4 生成的 id。先落盘后应答。"""
    cid = str(uuid.uuid4())
    now = time.time()
    db().execute(
        "INSERT INTO cognition VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, kind, conclusion, float(confidence),
         json.dumps(evidence, ensure_ascii=False),
         status, epistemic, now, now))
    db().commit()
    return cid


def query_cognition(q):
    """按 q.epistemic 可空过滤；evidence JSON 字符串还原为列表。"""
    q = q or {}
    sql = ("SELECT id, kind, conclusion, confidence, evidence, status, epistemic "
           "FROM cognition WHERE 1=1")
    args = []
    if q.get("epistemic"):
        sql += " AND epistemic = ?"
        args.append(q["epistemic"])
    sql += " ORDER BY created_at ASC"
    rows = db().execute(sql, args).fetchall()
    return [{"id": r[0], "kind": r[1], "conclusion": r[2], "confidence": r[3],
             "evidence": json.loads(r[4] or "[]"), "status": r[5], "epistemic": r[6]}
            for r in rows]


def on_event(topic, from_svc, msg):
    if topic == "evt.normalized":
        # v0 仅接收，不自动推导（自动推导是 M2 后续细化）
        pass
    elif topic == "sys.cognition.assert":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        ok, reason = validate_assert(msg)
        if not ok:
            svc.publish(f"evt.query.reply.{req_id}", {"status": "rejected", "reason": reason})
            return
        cid = insert_cognition(msg["kind"], msg["conclusion"], msg["confidence"],
                               msg["evidence"], msg["epistemic"])
        svc.publish(f"evt.query.reply.{req_id}",
                    {"id": cid, "status": "stored",
                     "confidence": float(msg["confidence"]), "epistemic": msg["epistemic"]})
    elif topic == "sys.query.cognition":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        svc.publish(f"evt.query.reply.{req_id}", {"results": query_cognition(msg.get("q", {}))})


svc.on_event = on_event


def main():
    svc.log("服务启动（M2 · T14 认知树唯一写者）")
    svc.run()


if __name__ == "__main__":
    main()
