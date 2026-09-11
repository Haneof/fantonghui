# -*- coding: utf-8 -*-
"""test_s2_t_policy · 任务 J 接线验收：证明旋钮是"真被读取"，不是注册表里摆着好看

跑法（便携，零网络，不碰真实 run/ 状态）：
    cd aios/01_os/code && python3 tests/test_s2_t_policy.py
    python3 tests/test_s2_t_policy.py --fast     # 跳过子进程扫描类两条（慢 ~1s）

核心立场：**改注册表默认值 → 服务行为必须跟着变**。
凡是"改了数但行为不变"的旋钮，一律算假旋钮（= 仍然写死），本文件当场判失败。
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)

import policy                                    # noqa: E402
import services.evolutiond as ev                 # noqa: E402

REAL_REGISTRY = os.path.join(CODE, "policies_v0.json")
RESULTS = []


def rec(name, ok, got="", want=""):
    RESULTS.append((name, bool(ok)))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else "   got=%r want=%r" % (got, want)))


def temp_env(**changes):
    """把注册表拷到临时目录并按需改默认值，返回 (env_dir, registry_path)。
    changes: {"evolve.tune_ceiling": 0.5} —— 只改 default，其余字段原样（模拟"人改了一个数"）。
    """
    d = tempfile.mkdtemp(prefix="aios_policy_t_")
    with open(REAL_REGISTRY, encoding="utf-8") as f:
        doc = json.load(f)
    for kid, val in changes.items():
        for k in doc["knobs"]:
            if k["id"] == kid:
                k["default"] = val
    reg = os.path.join(d, "policies_v0.json")
    with open(reg, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return d, reg


def use_registry(reg, d):
    """把服务的唯一读取入口换到临时注册表（服务侧零改动，证明它没有第二处默认值）。"""
    policy._P = policy.Policy(registry=reg, overrides=os.path.join(d, "overrides.json"),
                              audit=os.path.join(d, "audit.jsonl"))
    return policy._P


def fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(ev.SCHEMA)
    return conn


# ---------------------------------------------------------------- 1. 读通与初值
def t_reads():
    d, reg = temp_env()
    try:
        p = use_registry(reg, d)
        with open(REAL_REGISTRY, encoding="utf-8") as f:
            doc = json.load(f)
        by = {k["id"]: k for k in doc["knobs"]}
        got = ev.prior("SAFETY")
        rec("1 服务读到的初值 == 注册表 default", got == by["evolve.prior.safety"]["default"], got,
            by["evolve.prior.safety"]["default"])
        # 改注册表 → 服务跟着变（假旋钮在这一条现形）
        new = 0.33
        dd, r2 = temp_env(**{"evolve.prior.safety": new})
        use_registry(r2, dd)
        rec("2 改注册表 default → 服务读到新值（未写死）", ev.prior("SAFETY") == new, ev.prior("SAFETY"), new)
        shutil.rmtree(dd, ignore_errors=True)
        use_registry(reg, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        policy._P = None


# ---------------------------------------------------------------- 2. 夹逼区间跟着注册表走
def t_clamp_bounds():
    """天花板/地板各自隔离一次：改哪个，结果就被哪个夹住——这才叫"读到了"。"""
    cases = [("evolve.tune_ceiling", 0.5, 0.0, {"SOCIAL": 0.4}, "rejected", 0.5, "3 天花板改 0.5 → 压在 0.5（旧默认 0.95）"),
             ("evolve.tune_floor", 0.0, 0.4, {"SOCIAL": 0.42}, "accepted", 0.4, "4 地板改 0.4 → 抬到 0.4（旧默认 0.05）")]
    for knob, ceil_v, floor_v, init, fb, want, label in [
            ("evolve.tune_ceiling", 0.5, 0.0, {"SOCIAL": 0.4}, "rejected", 0.5,
             "3 天花板改 0.5 → rejected 被压在 0.5（旧默认 0.95，说明读的是注册表）"),
            ("evolve.tune_floor", 1.0, 0.4, {"SOCIAL": 0.42}, "accepted", 0.4,
             "4 地板改 0.4 → accepted 被抬到 0.4（旧默认 0.05）")]:
        d, reg = temp_env(**{"evolve.tune_ceiling": ceil_v, "evolve.tune_floor": floor_v})
        try:
            use_registry(reg, d)
            conn = fresh_db()
            r = ev.apply_feedback({"thresholds": dict(init)}, conn, "i-" + knob, fb, "SOCIAL", {})
            rec(label, r["threshold"] == want, r["threshold"], want)
            conn.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)
            policy._P = None


# ---------------------------------------------------------------- 3. 安全类豁免：既真生效、也真可关
def t_safety_exempt():
    d, reg = temp_env()                       # 默认 exempt=true
    try:
        use_registry(reg, d)
        conn = fresh_db()
        st = {"thresholds": {"SAFETY": ev.prior("SAFETY")}}
        day1 = st["thresholds"]["SAFETY"]
        for i in range(100):
            ev.apply_feedback(st, conn, "s%d" % i, "rejected", "SAFETY", {})
        rec("5 验收 F：100 次嫌烦后 SAFETY 阈值与第一天逐位相同", st["thresholds"]["SAFETY"] == day1,
            st["thresholds"]["SAFETY"], day1)
        n = conn.execute("SELECT COUNT(*) FROM growth").fetchone()[0]
        rec("6 豁免不等于免记：growth 仍 100 条", n == 100, n, 100)
        # 反向证明开关本身没写死：把 default 改成 false → 行为立刻恢复漂移
        dd, r2 = temp_env(**{"evolve.safety_regret_exempt": False})
        use_registry(r2, dd)
        st2 = {"thresholds": {"SAFETY": 0.1}}
        ev.apply_feedback(st2, conn, "x", "rejected", "SAFETY", {})   # 注意：换的是注册表，DB 与代码都不动
        rec("7 关掉豁免开关 → 立刻恢复漂移（证明豁免由注册表控制，不是硬编码 if）",
            st2["thresholds"]["SAFETY"] == 0.25, st2["thresholds"]["SAFETY"], 0.25)
        shutil.rmtree(dd, ignore_errors=True)
        conn.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
        policy._P = None


# ---------------------------------------------------------------- 4. hublinkd 攒批窗口
def t_hublink_batch():
    d, reg = temp_env(**{"bus.batch_size": 2, "bus.batch_window_s": 3600.0})
    try:
        use_registry(reg, d)
        from services.hublinkd import EntryQueue
        q = EntryQueue(os.path.join(d, "q.db"))
        for i in range(5):
            q.persist({"id": "e%d" % i, "ts": time.time(), "payload": i})
        n = q._conn.execute("SELECT COUNT(*) FROM entry_queue").fetchone()[0]
        rec("8 batch_size=2 → 5 条里已提交 4 条、1 条还在窗口内", n == 4, n, 4)
        # 换一份注册表：size=1 表示每条立刻落盘（宪法「事件不许丢」的极端档）
        dd, r2 = temp_env(**{"bus.batch_size": 1, "bus.batch_window_s": 3600.0})
        use_registry(r2, dd)
        q2 = EntryQueue(os.path.join(dd, "q2.db"))
        for i in range(5):
            q2.persist({"id": "f%d" % i, "ts": time.time(), "payload": i})
        n2 = q2._conn.execute("SELECT COUNT(*) FROM entry_queue").fetchone()[0]
        rec("9 batch_size=1 → 5 条全部落盘（旋钮真在驱动落盘时机）", n2 == 5, n2, 5)
        # retention：retention_h=0 → 已转发的立刻可清
        q2.mark(["f%d" % i for i in range(5)])
        ee, r3 = temp_env(**{"bus.retention_h": 0})
        use_registry(r3, ee)
        q2.cleanup()
        left = q2._conn.execute("SELECT COUNT(*) FROM entry_queue").fetchone()[0]
        rec("10 retention_h=0 → 已转发事件即刻清理（保留期是可配的）", left == 0, left, 0)
        shutil.rmtree(ee, ignore_errors=True)
        shutil.rmtree(dd, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        policy._P = None


# ---------------------------------------------------------------- 5. 写入的四条拒绝 + 留痕
def t_refusals():
    d, reg = temp_env()
    try:
        p = use_registry(reg, d)
        try:
            p.set("sample.hr_hz", 99999, by="ai", reason="想常开"); ok = False
        except policy.PolicyError as e:
            ok = "越界" in str(e)
        rec("11 越界值被拒绝（且是拒绝不是夹紧）", ok)
        try:
            p.set("safety.fall_detect_hz", 1, by="ai", reason="省电"); ok = False
        except policy.PolicyError as e:
            ok = "T2 安全底线" in str(e)
        rec("12 AI 改安全底线被拒（理由要说对，不能被越界掩盖）", ok)
        try:
            p.set("safety.fall_detect_hz", 10, by="user", reason="想省电"); ok = False
        except policy.PolicyError as e:
            ok = "confirm" in str(e)
        rec("13 人改安全底线缺 --confirm 被拒", ok)
        p.set("sample.hr_hz", 0.1, by="user", reason="运动期提频")
        try:
            p.set("sample.hr_hz", 25, by="ai", reason="想提频"); ok = False
        except policy.PolicyError as e:
            ok = "钉住" in str(e)
        rec("14 用户钉住的值 AI 改不动（粘住语义）", ok)
        r = p.set("duty.escalate_confirm_s", 30, by="ai", reason="误触发多", pinned=False)
        rec("15 用户未钉住的 AI 调整可被再次调整", r["value"] == 30, r["value"], 30)
        p.reset("sample.hr_hz", by="user", reason="回默认")
        with open(REAL_REGISTRY, encoding="utf-8") as f:
            doc = json.load(f)
        default = [k for k in doc["knobs"] if k["id"] == "sample.hr_hz"][0]["default"]
        rec("16 reset 回到注册表默认（回滚有出口）", p.get("sample.hr_hz") == default,
            p.get("sample.hr_hz"), default)
        with open(p.audit_path, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
        last = lines[-1]
        rec("17 审计流水含 old/new/by/reason/hot_effect",
            all(k in last for k in ("old", "new", "by", "reason", "hot_effect")), sorted(last))
        rec("18 审计条数 == 成功写入次数（拒绝不留痕、成功必留痕）", len(lines) == 3, len(lines), 3)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        policy._P = None


# ---------------------------------------------------------------- 6. 注册表与扫描器自身
def t_scanner():
    if "--fast" in sys.argv:
        print("  SKIP  19/20/21（--fast：子进程扫描类跳过）")
        return
    r = subprocess.run([sys.executable, os.path.join(CODE, "policy_scan.py"), "--json"],
                       capture_output=True, text=True, cwd=CODE)
    doc = json.loads(r.stdout)
    rec("19 policy_scan 无 error", doc["ok"] and not doc["errors"], doc["errors"][:2])
    rec("20 接线数不回落（≥18 根被代码引用）", len(doc["referenced_ids"]) >= 18,
        len(doc["referenced_ids"]), ">=18")
    # RULE-7 反例：只动天花板（各 prior 自身区间仍合法）→ 只有交叉校验会响，证明 RULE-7 不是摆设
    d, reg = temp_env(**{"evolve.tune_ceiling": 0.5})
    try:
        env = dict(os.environ, AIO_POLICIES=reg)
        r2 = subprocess.run([sys.executable, os.path.join(CODE, "policy_scan.py"), "--json"],
                            capture_output=True, text=True, cwd=CODE, env=env)
        out = json.loads(r2.stdout)
        r7 = [e for e in out["errors"] if "RULE-7" in e]
        rec("21 RULE-7 抓到交叉区间脱钩（天花板 0.5 < prior.financial 0.8）",
            len(r7) >= 1 and "evolve.prior.financial" in r7[0], out["errors"][:2])
        rec("22 单看 RULE-1 不会误报（各旋钮自身区间仍合法）",
            not [e for e in out["errors"] if "RULE-1" in e], [e for e in out["errors"] if "RULE-1" in e][:1])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    print("=" * 74)
    print("Task J 接线验收 · 参数注册表 → 服务行为（改数必须变行为）")
    print("=" * 74)
    for fn in (t_reads, t_clamp_bounds, t_safety_exempt, t_hublink_batch, t_refusals, t_scanner):
        fn()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("-" * 74)
    print("结果: %d/%d 项通过" % (n_ok, len(RESULTS)))
    if n_ok != len(RESULTS):
        print("未通过项: %s" % [n for n, ok in RESULTS if not ok])
        sys.exit(1)


if __name__ == "__main__":
    main()
