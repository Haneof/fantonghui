# -*- coding: utf-8 -*-
"""aios_console · AIOS 只读系统面板（Dev Console）—— 决策记录 docs/01 V0.2 §8 风险二的产物

定位（重要）：这是**验收夹具与取证入口**，不是产品 UI。宪法 §12.5 要求 UI/App/Hardware 在底层
闭环前保持空壳，本文件不违反它：它不呈现给用户，只让人类审查者在一屏之内看见底座在跑什么。

    python3 aios_console.py            # 打一次快照
    python3 aios_console.py --watch 2  # 每 2s 刷新
    python3 aios_console.py --json     # 机器可读（给 tests 与报告用）

硬约束：只读。数据源全部是 `run/` 下的快照文件与 SQLite（`mode=ro` URI），
零网络、零模型、零写操作——它没有能力改变它所显示的任何东西。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))          # code/
RUN = os.path.join(ROOT, "run")
CONSTITUTION = "V1.4-r0（2026-09-11 批准生效）"

WIDTH = 78
SLOTS = ("mode", "location", "people", "user", "environment",
         "active_situations", "tasks", "goals", "timestamp")
#: V1.4 迁移状态：面板必须如实显示未实装项，否则一次成功回放就会被误读成"架构已符合宪法"
MIGRATION = [("Observation Store / Global Timeline", "NOT_MIGRATED"),
             ("Dimension Registry / 曲线", "NOT_MIGRATED"),
             ("Trigger 六类（§4.3）", "P0 违宪待重写"),
             ("World State / Change（stated）", "MAINLINE ✓ 22/22"),
             ("Memory 三树 / 六跳金字塔", "MAINLINE ✓"),
             ("Safety 硬规则（safetyd）", "SHELL"),
             ("设置面 / 审计", "NOT_STARTED"),
             ("Syscall 表 v0", "契约已冻结，实现待补")]


def _read_json(name):
    try:
        with open(os.path.join(RUN, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _ro_query(db, sql, args=()):
    """只读连接；库不存在/表不存在 → None（面板不得因此崩掉，也不得假装数据为 0）。"""
    path = os.path.join(RUN, db)
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()
    except Exception:
        return None


def collect():
    snap = _read_json("world_state.json") or {}
    health = _read_json("health.json") or {}
    bus = _read_json("bus_stats.json") or {}
    lease = _read_json("lease_stats.json") or {}
    privacy = _read_json("privacy_snapshot.json") or {}

    disp = _ro_query("world_state.db",
                     "SELECT disposition, COUNT(*) FROM world_update GROUP BY disposition")
    n_applied = _ro_query("world_state.db", "SELECT COUNT(*) FROM applied_event")
    n_change = _ro_query("world_state.db",
                         "SELECT COUNT(*), MAX(version) FROM world_change")
    recent = _ro_query("world_state.db",
                       "SELECT id, change_type, window_start, COALESCE(before_json,''), "
                       "COALESCE(after_json,''), evidence_json FROM world_change "
                       "ORDER BY version DESC LIMIT ?", (5,))
    ents = _ro_query("entity_store.db",
                     "SELECT COUNT(*), SUM(CASE WHEN confidence=0 THEN 1 ELSE 0 END) FROM entities")
    ents = ents[0] if ents else None
    sha = _ro_query("world_state.db", "SELECT state_sha FROM world_state ORDER BY version DESC LIMIT 1")
    return {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "constitution": CONSTITUTION,
            "snapshot": snap, "health": health, "bus": bus, "lease": lease,
            "privacy": privacy, "disposition": dict(disp) if disp else None,
            "applied_events": n_applied[0][0] if n_applied else None,
            "changes": n_change[0][0] if n_change else None,
            "state_version": n_change[0][1] if n_change else None,
            "recent_changes": recent, "entities": ents,
            "state_sha": (sha[0][0] if sha else None)}


def dlen(text: str) -> int:
    """显示宽度：CJK/全角算 2 格，其余 1 格。直接用 len 会让中文行错列。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - dlen(text))


def fmt_num(v):
    return "—" if v is None else str(v)


def _bar(title):
    return "\n\033[1m── " + title + " \033[0m" + "─" * max(0, WIDTH - dlen(title) - 5) + "\n"


def _fmt(v):
    if isinstance(v, list):
        return ", ".join(str(x) if not isinstance(x, dict) else x.get("id", "?") for x in v) or "—"
    if isinstance(v, dict):
        return " ".join(f"{k}={_fmt(x)}" for k, x in v.items() if x not in (None, "", [], {})) or "—"
    return "—" if v in (None, "") else str(v)


def render(d, out=sys.stdout):
    w = out.write
    w(f"\033[2m\033[0K{'=' * WIDTH}\033[0m\n")
    w(f"\033[1m AIOS 只读系统面板\033[0m  {d['ts']}   宪法基准 {d['constitution']}\n")
    w("\033[2m 本面板无任何写权限；数据源 run/*.json 与 SQLite mode=ro\033[0m\n")
    w(f"\033[2m{'=' * WIDTH}\033[0m")

    # L0 承载
    w(_bar("L0 承载 · 服务在线"))
    svc = d["health"].get("services") or {}
    bsvc = d["bus"].get("services") or {}
    if not svc:
        w(" \033[33m无 health.json —— aiosd 未启动（python3 aiosd/aiosd.py）\033[0m\n")
    else:
        up = sum(1 for v in svc.values() if isinstance(v, dict) and v.get("state") == "up")
        hb = [v.get("last_hb") for v in bsvc.values() if isinstance(v, dict) and v.get("last_hb")]
        age = f"{time.time() - max(hb):.1f}s" if hb else "—"
        back = sum(int(v.get("qsize") or 0) for v in bsvc.values() if isinstance(v, dict))
        w(f" 在线 {up}/{len(svc)}   心跳最旧 {age}   总线侧队列积压合计={back}（反压信号）\n")
        w(" " + pad("服务", 16) + pad("状态", 11) + pad("重启", 5)
          + pad("收帧", 7) + pad("积压", 5) + "心跳\n")
        for name in sorted(svc):
            v = svc[name] or {}
            b = bsvc.get(name) or {}
            st, rs = v.get("state", "?"), v.get("restarts", 0)
            col = "\033[32m" if st == "up" else ("\033[31m" if st == "down" else "\033[33m")
            last = b.get("last_hb")
            w(f"  {col}●\033[0m " + pad(name, 14) + pad(str(st), 9) + pad(str(rs), 5)
              + pad(fmt_num(b.get("frames_in")), 5) + pad(fmt_num(b.get("qsize")), 6)
              + (f"{time.time() - last:.1f}s ago" if last else "—") + "\n")

    # L2 世界模型
    w(_bar("L2 用户世界模型 · 当前快照（事实槽位）"))
    if not d["snapshot"]:
        w(" \033[33m无 run/world_state.json —— 尚未有事件被应用进世界\033[0m\n")
    else:
        st = d["snapshot"].get("state", d["snapshot"])
        w(f" version={fmt_num(d['state_version'])}"
          f"  state_sha={str(d.get('state_sha') or '—')[:12]}"
          f"  ts={_fmt(st.get('timestamp'))}\n")
        for slot in SLOTS:
            val = _fmt(st.get(slot))
            w("    " + pad(slot, 18) + (val if dlen(val) <= WIDTH - 22 else val[:20] + "…") + "\n")

    # L1/L2 漏斗与守恒
    w(_bar("L1→L2 漏斗 · 下落守恒（08 §N 口径）"))
    ent_txt = "—"
    if d["entities"] and d["entities"][0] is not None:
        unknown = d["entities"][1] or 0
        ent_txt = f"{d['entities'][0]} 条（UNKNOWN 占位 {unknown}）"
    w(f" 已吸收事件={fmt_num(d['applied_events'])}   "
      f"World Change={fmt_num(d['changes'])}   实体登记={ent_txt}\n")
    if d["disposition"]:
        for k in ("applied", "no_rule", "no_slot_change", "stale", "replay_skipped", "rejected"):
            if k in d["disposition"]:
                w(f"   {k:<16}{d['disposition'][k]}\n")
        w(f"   合计={sum(d['disposition'].values())}（每次尝试恰好一个下落）\n")
    else:
        w("   \033[33m无 world_update 台账\033[0m\n")
    if d["recent_changes"]:
        w("\n最近 World Change（before → after，附证据）\n")
        for cid, ctype, ws, before, after, ev in reversed(d["recent_changes"]):
            try:
                b = _fmt(json.loads(before)); a = _fmt(json.loads(after))
            except Exception:
                b, a = before, after
            try:
                evn = len(json.loads(ev or "[]"))
            except Exception:
                evn = "?"
            w("   " + pad(cid, 11) + pad(str(ctype)[:21], 23) + str(ws)[11:] + "  "
              + b + " → " + a + f"  (证据 {evn})\n")

    # L3 治理
    w(_bar("L3 治理 · 隐私授权与算力预算"))
    if d["privacy"]:
        w("\n 源授权：" + "  ".join(f"{k}={v}" for k, v in list(d["privacy"].items())[:8]) + "\n")
    else:
        w(" \033[33m无 privacy_snapshot.json —— 全部源按未授权处理（默认拒绝，宪法第十章）\033[0m\n")
    if d["lease"]:
        w(f" 算力租约（纯机械配额，§4.3）：granted={d['lease'].get('granted', '—')} "
          f"active={d['lease'].get('active', '—')} released={d['lease'].get('released', '—')} "
          f"expired={d['lease'].get('expired', '—')}\n")
    else:
        w(" 算力租约：无数据\n")

    # V1.4 迁移进度（不许把演示当成完成）
    w(_bar("宪法 V1.4 迁移进度（本面板的诚实声明）") + "\n")
    for name, st in MIGRATION:
        col = "\033[32m" if "✓" in st else ("\033[31m" if "违宪" in st or "NOT" in st else "\033[33m")
        w("  " + col + pad(st, 24) + "\033[0m " + name + "\n")
    w("\n\033[2m 提示：上面出现红项期间，任何\"AIOS 已完成\"的表述均不成立（宪法 §12.6、STATUS 红线 9）。\033[0m\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=float, default=0, metavar="SEC", help="按周期刷新")
    ap.add_argument("--json", action="store_true", help="输出机器可读快照")
    args = ap.parse_args()
    while True:
        d = collect()
        if args.json:
            print(json.dumps(d, ensure_ascii=False, default=str))
        else:
            os.system("")           # 让 Windows 也认 ANSI；Linux 无副作用
            render(d)
        if args.watch <= 0:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
