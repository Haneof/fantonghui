# -*- coding: utf-8 -*-
"""policy · T1/T2 策略参数的唯一读取入口（V1.4 §3.4 / 契约 12 号文档 Part A）

为什么要有这个文件：注册表如果只是一份 JSON，"参数可调"就是句空话——服务照样读自己的常量。
本模块把三件事收在一处，别处不许各写一套：
  1) 读：`get(id)` = 用户覆盖 > AI 调整值 > 注册表默认值；**注册表缺失即报错，绝不静默兜底**
     （自带一份"备用默认值"就是第二套实现，也正好是"写死"的复活形式）
  2) 写：`set(id, value, by=...)` 做界内校验（越界**拒绝**而不是夹紧——把用户要的 30 悄悄改成 5 是撒谎）
     T2 安全底线 `by="ai"` 一律拒绝；`by="user"` 必须 confirm + 代价说明
     用户钉住（pin）的值，AI 改不动，只能提申请
  3) 留痕：每次成功写入追加 `run/policy/audit.jsonl` 一行（谁改的/从多少改到多少/为什么）

热更新：按文件 mtime 重载，改完不重启就生效（注册表里 `hot_effect` 说明何时影响到下一条）。
回滚：`reset(id)` 回到注册表默认值；策略版本链本身仍归 `evolutiond.strategy_versions`，本模块不另建。

    python3 policy.py list
    python3 policy.py get trigger.insufficient_cap
    python3 policy.py set sample.hr_hz 120 --by ai --reason "用户在跑步，5 分钟点会漏"
    python3 policy.py set safety.fall_detect_hz 5 --by user --confirm --cost "漏报风险上升"
"""
from __future__ import annotations

import argparse
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))                  # aios/01_os/code
# AIO_POLICIES / AIO_POLICY_DIR 只给测试与双注册表对照用（判"旋钮是否真被读取"必须能换一份注册表）；
# 正常运行不需要设，也不存在第二套默认值。
REGISTRY = os.environ.get("AIO_POLICIES") or os.path.join(HERE, "policies_v0.json")
STATE_DIR = os.environ.get("AIO_POLICY_DIR") or os.path.join(HERE, "run", "policy")
OVERRIDES = os.path.join(STATE_DIR, "overrides.json")
AUDIT = os.path.join(STATE_DIR, "audit.jsonl")


class PolicyError(Exception):
    pass


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class Policy:
    def __init__(self, registry=None, overrides=None, audit=None):
        registry = registry or REGISTRY
        state = os.environ.get("AIO_POLICY_DIR") and os.path.join(os.environ["AIO_POLICY_DIR"], "policy") or STATE_DIR
        overrides = overrides or os.path.join(state, "overrides.json")
        audit = audit or os.path.join(state, "audit.jsonl")
        self.state_dir = os.path.dirname(overrides)
        self.registry_path, self.overrides_path, self.audit_path = registry, overrides, audit
        self._mtime = None
        self._ov_mtime = None
        self._doc = None
        self._ov = {}
        self._by_id = {}

    # ---------- 读 ----------
    def _reload(self):
        try:
            m = os.path.getmtime(self.registry_path)
        except OSError:
            raise PolicyError(f"注册表缺失：{self.registry_path}（宁可不开跑，也不用一份写死的备用默认值）")
        if m != self._mtime:
            with open(self.registry_path, encoding="utf-8") as f:
                self._doc = json.load(f)
            self._by_id = {k["id"]: k for k in self._doc.get("knobs", [])}
            self._mtime = m
        try:
            om = os.path.getmtime(self.overrides_path)
        except OSError:
            om = None
        if om != self._ov_mtime:
            self._ov = {}
            if om:
                try:
                    with open(self.overrides_path, encoding="utf-8") as f:
                        self._ov = json.load(f)
                except (ValueError, OSError):
                    self._ov = {}            # 覆盖文件坏了不影响默认值可用（但下面会记账）
            self._ov_mtime = om

    def knob(self, kid):
        self._reload()
        kb = self._by_id.get(kid)
        if kb is None:
            raise PolicyError(f"未登记的旋钮：{kid}（先在 policies_v0.json 建户口）")
        return kb

    def get(self, kid):
        """生效值 = 用户覆盖 > AI 调整值 > 注册表默认值。"""
        kb = self.knob(kid)
        rec = self._ov.get(kid)
        return rec["value"] if rec is not None else kb["default"]

    def origin(self, kid):
        rec = self._ov.get(kid)
        if rec is None:
            return "registry_default"
        return ("user_pinned" if rec.get("pinned") else "user") if rec.get("by") == "user" else "ai"

    def source(self, kid):
        self.knob(kid)
        return {"id": kid, "value": self.get(kid), "origin": self.origin(kid),
                "default": self._by_id[kid]["default"], "unit": self._by_id[kid].get("unit"),
                "floor": self._by_id[kid].get("floor"), "ceiling": self._by_id[kid].get("ceiling"),
                "safety_linked": bool(self._by_id[kid].get("safety_linked")),
                "hot_effect": self._by_id[kid].get("hot_effect")}

    def all(self):
        self._reload()
        out = []
        for kid in sorted(self._by_id):
            try:
                out.append(self.source(kid))
            except PolicyError:
                pass
        return out

    # ---------- 写 ----------
    def set(self, kid, value, by="ai", reason="", pinned=None, confirm=False, cost=None):
        kb = self.knob(kid)
        if by not in ("ai", "user"):
            raise PolicyError(f"by 只能是 ai 或 user，收到 {by}")
        v = self._coerce(kb, value)
        # 先判"有没有资格改"，再判"值合不合法"：理由错了比拒绝更糟
        if kb.get("safety_linked"):
            if by == "ai":
                raise PolicyError(f"T2 安全底线：{kid} 的 owner={kb.get('owner')}，AI 与自动学习无权放宽（宪法 §4.2-6、契约 12 Part A）")
            if not confirm:
                raise PolicyError(f"{kid} 属安全底线：人改必须带 --confirm（显式确认）")
            if not (cost and len(str(cost).strip()) >= 4):
                raise PolicyError(f"{kid} 属安全底线：必须写代价说明（例如「漏报风险上升」），不许改完就完")
        rec_old0 = self._ov.get(kid)
        if rec_old0 is not None and rec_old0.get("by") == "user" and by == "ai" and pinned_ok(rec_old0):
            raise PolicyError(f"{kid} 已被用户在设置面钉住（{rec_old0.get('reason') or '无理由'}）；AI 只能提申请，不能覆盖")
        lo, hi = kb.get("floor"), kb.get("ceiling")
        if kb.get("unit") == "bool":
            if not isinstance(v, bool):
                raise PolicyError(f"{kid} 是开关型，值必须是 true/false")
        elif not _is_num(v):
            raise PolicyError(f"{kid} 需要数值，收到 {value!r}")
        elif not (lo <= v <= hi):
            raise PolicyError(f"{kid} 越界：{v} ∉ [{lo}, {hi}]（界内才允许；越界我拒绝而不是夹紧）")
        rec_old = self._ov.get(kid)
        if rec_old is not None and rec_old.get("by") == "user" and by == "ai" and pinned_ok(rec_old):
            raise PolicyError(f"{kid} 已被用户在设置面钉住（{rec_old.get('reason') or '无理由'}）；AI 只能提申请，不能覆盖")
        if by == "user" and pinned is None:
            pinned = True                      # 人给的值得默认粘住，否则下一次 AI 自调就把它冲掉
        entry = {"value": v, "by": by, "pinned": bool(pinned), "reason": str(reason or ""),
                 "ts": time.time(), "old": rec_old["value"] if rec_old else kb["default"],
                 "safety_linked": bool(kb.get("safety_linked"))}
        if cost:
            entry["cost_notice"] = str(cost)
        self._ov[kid] = entry
        self._persist()
        self._audit(kid, entry, by, reason)
        return self.source(kid)

    def reset(self, kid, by="user", reason=""):
        kb = self.knob(kid)
        rec_old = self._ov.pop(kid, None)
        if rec_old is None:
            raise PolicyError(f"{kid} 本来就没有覆盖值，当前即注册表默认 {kb['default']}")
        self._persist()
        self._audit(kid, {"ts": time.time(), "value": kb["default"], "old": rec_old["value"],
                          "by": by, "pinned": False, "reason": reason or "reset_to_registry_default",
                          "safety_linked": bool(kb.get("safety_linked"))}, by, reason)
        return self.source(kid)

    def _coerce(self, kb, value):
        if isinstance(value, str):
            s = value.strip().lower()
            if kb.get("unit") == "bool":
                if s in ("1", "true", "yes", "on"):
                    return True
                if s in ("0", "false", "no", "off"):
                    return False
                raise PolicyError(f"{kb['id']} 是开关型，收到 {value!r}")
            try:
                return float(s) if ("." in s or "e" in s) else int(s)
            except ValueError:
                raise PolicyError(f"{kb['id']} 需要数值，收到 {value!r}")
        if kb.get("unit") == "bool" and value in (0, 1):
            return bool(value)
        return value

    # ---------- 留痕 ----------
    def _persist(self):
        os.makedirs(self.state_dir, exist_ok=True)
        tmp = self.overrides_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._ov, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.overrides_path)
        self._ov_mtime = os.path.getmtime(self.overrides_path)

    def _audit(self, kid, entry, by, reason):
        os.makedirs(self.state_dir, exist_ok=True)
        line = {"ts": entry["ts"], "knob": kid, "old": entry["old"], "new": entry["value"],
                "by": by, "pinned": entry.get("pinned", False), "reason": str(reason or ""),
                "safety_linked": entry.get("safety_linked", False),
                "hot_effect": self._by_id[kid].get("hot_effect")}
        if entry.get("cost_notice"):
            line["cost_notice"] = entry["cost_notice"]
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def pinned_ok(rec):
    """只有"用户钉住"才拦 AI；用户临时改一下（pinned=false）允许被 AI 再调。"""
    return rec.get("pinned") is not False and rec.get("by") == "user"


_P = None


def default():
    global _P
    if _P is None:
        _P = Policy()
    return _P


def get(kid):
    return default().get(kid)


def knob(kid):
    return default().knob(kid)


def set_value(kid, value, **kw):
    return default().set(kid, value, **kw)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("get"); g.add_argument("id")
    w = sub.add_parser("source"); w.add_argument("id")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("value")
    s.add_argument("--by", default="user"); s.add_argument("--reason", default="")
    s.add_argument("--no-pin", action="store_true"); s.add_argument("--confirm", action="store_true")
    s.add_argument("--cost", default="")
    r = sub.add_parser("reset"); r.add_argument("id"); r.add_argument("--reason", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    p = default()
    if a.cmd == "list":
        for row in p.all():
            star = "★" if row["origin"] != "registry_default" else " "
            lock = "🔒" if row["safety_linked"] else "  "
            print(f"{star}{lock} {row['id']:<34} {str(row['value']):>8} {row['unit']:<8}"
                  f" 界[{row['floor']}, {row['ceiling']}] 来源={row['origin']}")
        print(f"（★=已被覆盖，🔒=安全底线 AI 无权改；共 {len(p.all())} 根旋钮）")
    elif a.cmd == "get":
        print(p.get(a.id))
    elif a.cmd == "source":
        print(json.dumps(p.source(a.id), ensure_ascii=False, indent=1))
    elif a.cmd == "set":
        print(json.dumps(p.set(a.id, a.value, by=a.by, reason=a.reason, pinned=False if a.no_pin else None,
                              confirm=a.confirm, cost=a.cost), ensure_ascii=False))
    else:
        print(json.dumps(p.reset(a.id, by="user", reason=a.reason), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PolicyError as e:
        print(f"拒绝：{e}")
        raise SystemExit(2)
