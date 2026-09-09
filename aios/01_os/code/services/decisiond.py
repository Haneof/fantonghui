# -*- coding: utf-8 -*-
"""decisiond · 决策系统（M2 · T16 非对称阈值 + INFERRED≠KNOWN 校验）
- 订阅：sys.decision.request、evt.normalized
- 只读 cognitive_tree.db（sqlite3 只读连接 file:...?mode=ro），绝不写；读不到行 = 引用缺失
- 判定顺序严格（契约 tasks/contracts_m2.md §T16）：
  1. CITATION_MISSING   引用缺失（认知树查无）
  2. INFERRED_AS_KNOWN  推断当已知（宪法原则三：推断永不当事实用）
  3. FINANCIAL_HIGH_RISK 金融高风险动作 → REQUIRE_CONFIRM
  4. ACCEPT
- cites 为空列表 → 视为无引用 → ACCEPT（v0 约定）
- 对 evt.normalized：v0 仅接收，不处理
"""
import os
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COGNITIVE_DB_PATH = os.path.join(ROOT, "run", "cognitive_tree.db")

# 高风险金融动作集合（契约 §T16 规则 3）
FINANCIAL_ACTIONS = frozenset({"pay", "execute", "transfer"})

svc = AIOSService("decisiond", subscribe=["sys.decision.request", "evt.normalized"])


def _ro_uri(db_path):
    """本地路径 → SQLite 只读 URI：file:...?mode=ro"""
    return Path(db_path).as_uri() + "?mode=ro"


def fetch_cognitions(ids, db_path=COGNITIVE_DB_PATH):
    """只读查询认知树，返回 {认知id: epistemic}。
    - 连接 mode=ro，绝不写；每次新建并关闭，无持久句柄。
    - 读不到的行 = 引用缺失（契约 §T16 规则 1）。
    - 库/表不存在或任何只读异常 → 视作全部缺失（同样落入 CITATION_MISSING）。
    """
    ids = list(ids)
    if not ids:
        return {}
    found = {}
    try:
        conn = sqlite3.connect(_ro_uri(db_path), uri=True)
        try:
            ph = ",".join("?" for _ in ids)
            rows = conn.execute(
                "SELECT id, epistemic FROM cognition WHERE id IN (%s)" % ph,
                ids).fetchall()
            for rid, epistemic in rows:
                found[rid] = epistemic
        finally:
            conn.close()
    except sqlite3.Error as e:
        svc.log(f"[只读] 认知树访问失败（视为引用缺失）: {e}")
    return found


def decide(req, db_path=COGNITIVE_DB_PATH):
    """判定核心。返回 verdict dict（不含 req_id，由调用方拼回复主题）。
    sys.decision.request 载荷：{req_id, cites:[认知id...], risk_class, action}
    """
    cites = list(req.get("cites") or [])
    risk_class = req.get("risk_class", "")
    action = req.get("action", "")

    # v0 约定：cites 为空 → 无引用 → ACCEPT
    if not cites:
        return {"verdict": "ACCEPT"}

    found = fetch_cognitions(cites, db_path)

    # 规则 1：任一 cite 查无 → 引用缺失
    missing = [cid for cid in cites if cid not in found]
    if missing:
        return {"verdict": "REJECT", "reason": "CITATION_MISSING", "ids": missing}

    # 规则 2：任一 cite 认知 epistemic != KNOWN → 推断当已知
    inferred = [cid for cid in cites if found.get(cid) != "KNOWN"]
    if inferred:
        return {"verdict": "REJECT", "reason": "INFERRED_AS_KNOWN", "ids": inferred}

    # 规则 3：FINANCIAL + 高风险动作 → 需人工确认
    if risk_class == "FINANCIAL" and action in FINANCIAL_ACTIONS:
        return {"verdict": "REQUIRE_CONFIRM", "reason": "FINANCIAL_HIGH_RISK"}

    # 规则 4：通过
    return {"verdict": "ACCEPT"}


def on_event(topic, from_svc, msg):
    if topic == "sys.decision.request":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        svc.publish("evt.query.reply.%s" % req_id, decide(msg))
    elif topic == "evt.normalized":
        pass  # v0 仅接收，不处理


svc.on_event = on_event


# ---------------- 内联自测（python decisiond.py --selftest） ----------------
def _selftest():
    """手工建临时认知树（一条 INFERRED + 一条 KNOWN），验证判定各分支。
    清理策略：只做 SQL 级清空（DELETE FROM），不调用任何文件删除 API
    （遵守平台安全护栏对 destructive file API 的约束）；临时库置于系统临时目录，
    不污染项目 run/，残留为空表文件交由系统定期回收。
    """
    tmp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.dirname(ROOT)
    db_path = os.path.join(tmp_dir, "decisiond_selftest_cognitive_tree.db")

    fails = []

    def check(name, got, want):
        ok = (got == want)
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            print("  got =%r" % (got,))
            print("  want=%r" % (want,))
            fails.append(name)

    # 写侧：建表 + 清空 + 插入两条认知（SQL 数据操作，不触碰文件删除）
    w = sqlite3.connect(db_path)
    w.execute("CREATE TABLE IF NOT EXISTS cognition ("
              "id TEXT PRIMARY KEY, kind TEXT NOT NULL, conclusion TEXT NOT NULL,"
              "confidence REAL NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL,"
              "epistemic TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)")
    w.execute("DELETE FROM cognition")
    w.execute("INSERT INTO cognition VALUES (?,?,?,?,?,?,?,?,?)",
              ("inf-1", "HYPOTHESIS", "x", 0.60, "[]", "ACTIVE", "INFERRED", 0.0, 0.0))
    w.execute("INSERT INTO cognition VALUES (?,?,?,?,?,?,?,?,?)",
              ("k-1", "BELIEF", "y", 0.95, "[]", "ACTIVE", "KNOWN", 0.0, 0.0))
    w.commit()
    w.close()

    # 读侧：通过 decide() 内部只读 URI（mode=ro）读取并判定
    check("empty cites -> ACCEPT",
          decide({"cites": [], "risk_class": "FINANCIAL", "action": "pay"}, db_path),
          {"verdict": "ACCEPT"})
    check("CITATION_MISSING",
          decide({"cites": ["ghost"], "risk_class": "SAFETY", "action": "none"}, db_path),
          {"verdict": "REJECT", "reason": "CITATION_MISSING", "ids": ["ghost"]})
    check("INFERRED_AS_KNOWN",
          decide({"cites": ["inf-1"], "risk_class": "SAFETY", "action": "none"}, db_path),
          {"verdict": "REJECT", "reason": "INFERRED_AS_KNOWN", "ids": ["inf-1"]})
    check("FINANCIAL_HIGH_RISK",
          decide({"cites": ["k-1"], "risk_class": "FINANCIAL", "action": "pay"}, db_path),
          {"verdict": "REQUIRE_CONFIRM", "reason": "FINANCIAL_HIGH_RISK"})
    check("KNOWN SAFETY -> ACCEPT",
          decide({"cites": ["k-1"], "risk_class": "SAFETY", "action": "execute"}, db_path),
          {"verdict": "ACCEPT"})

    # 清理临时库数据（SQL 级清空，不删文件）
    w2 = sqlite3.connect(db_path)
    w2.execute("DELETE FROM cognition")
    w2.commit()
    w2.close()

    if fails:
        print("SELFTEST FAILED: %s" % fails)
        sys.exit(1)
    print("SELFTEST PASSED (5/5)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        svc.log("服务启动（M2 · T16 决策系统：非对称阈值 + INFERRED≠KNOWN 校验）")
        svc.run()
