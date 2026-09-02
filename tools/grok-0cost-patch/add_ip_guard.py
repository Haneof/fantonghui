# -*- coding: utf-8 -*-
"""给 run_0cost_grok_register.py 加「出口 IP 守门」：
出口不可用时一直等待，绝不放行注册（避免白烧邮箱与 35s 超时）。

判定不可用的条件：
  1. 探测 https://www.cloudflare.com/cdn-cgi/trace 失败
  2. 解析不出 ip=
  3. 代理出口 IP == 本机直连出口 IP  ->  说明代理压根没生效

幂等；写入前自动备份；ast 校验失败不落盘。
"""
import argparse
import ast
import datetime
import io
import os
import re

MARK = "# === GROK-0COST-PATCH: ip-guard ==="
MARK_END = "# === GROK-0COST-PATCH: end ip-guard ==="
ROTATE_END = "# === GROK-0COST-PATCH: end rotate-ip ==="

GUARD = '''

''' + MARK + '''
IPGUARD_TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
IPGUARD_PROXY = "http://127.0.0.1:10809"
IPGUARD_SLEEP = 20
_ipguard_direct_ip = None


def _ipguard_log(msg):
    f = globals().get("log_p")
    if callable(f):
        f(msg)
    else:
        print(msg, flush=True)


def _get_exit_ip(proxy=None, timeout=8):
    """返回 (ip, loc)。proxy=None 表示强制直连（绕开环境变量里的代理）。"""
    if proxy:
        opener = _p_urlreq.build_opener(
            _p_urlreq.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener = _p_urlreq.build_opener(_p_urlreq.ProxyHandler({}))
    req = _p_urlreq.Request(
        IPGUARD_TRACE_URL,
        headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    with opener.open(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="ignore")
    ip = loc = None
    for line in body.splitlines():
        if line.startswith("ip="):
            ip = line[3:].strip()
        elif line.startswith("loc="):
            loc = line[4:].strip()
    return ip, loc


def _wait_for_usable_ip(worker_id=0):
    """切 IP 并确认出口真的可用；不可用就一直等，绝不返回。"""
    global _ipguard_direct_ip
    if _ipguard_direct_ip is None:
        try:
            _ipguard_direct_ip, _d_loc = _get_exit_ip(None)
            _ipguard_log(
                f"[GUARD] 本机直连出口 IP = {_ipguard_direct_ip} "
                f"(代理出口若与此相同，即判定代理未生效)")
        except Exception as e:
            _ipguard_direct_ip = ""
            _ipguard_log(f"[GUARD] 取直连出口 IP 失败: {e}")

    attempt = 0
    while True:
        attempt += 1
        _force_rotate_ip(worker_id)
        reason = None
        ip = loc = None
        try:
            ip, loc = _get_exit_ip(IPGUARD_PROXY)
        except Exception as e:
            reason = f"探测出口失败: {e}"
        if reason is None:
            if not ip:
                reason = "响应里解析不出 ip="
            elif _ipguard_direct_ip and ip == _ipguard_direct_ip:
                reason = f"出口 {ip} 与直连相同，代理未生效"
        if reason is None:
            _ipguard_log(
                f"[GUARD] [Worker-{worker_id}] 出口可用 ip={ip} loc={loc}，放行注册")
            return ip
        _ipguard_log(
            f"[GUARD] [Worker-{worker_id}] 第 {attempt} 次检查未通过 ({reason})；"
            f"{IPGUARD_SLEEP}s 后重试，本轮不开始注册")
        _p_time.sleep(IPGUARD_SLEEP)
''' + MARK_END + '''
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reg", default=r"D:\API中转\grok\run_0cost_grok_register.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.reg):
        raise SystemExit("[FAIL] 找不到文件: %s" % args.reg)

    src = io.open(args.reg, encoding="utf-8-sig").read()
    out = src
    acts = []

    # 1) 先改调用点，且只在 worker_loop 的行范围内改。
    #    必须先于注入执行：守门函数体内部也有一行 _force_rotate_ip(worker_id)，
    #    若先注入再做全局 replace，会把守门函数自己的调用换掉 -> 无限递归。
    tree = ast.parse(out)
    worker = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "worker_loop":
            worker = node
            break
    if worker is None:
        raise SystemExit("[FAIL] 找不到 def worker_loop")

    lines = out.splitlines(keepends=True)
    lo, hi = worker.lineno - 1, worker.end_lineno
    hits = [i for i in range(lo, hi) if "_force_rotate_ip(worker_id)" in lines[i]]
    already = [i for i in range(lo, hi) if "_wait_for_usable_ip(worker_id)" in lines[i]]
    if hits:
        for i in hits:
            lines[i] = lines[i].replace("_force_rotate_ip(worker_id)",
                                        "_wait_for_usable_ip(worker_id)")
        out = "".join(lines)
        acts.append("worker_loop 内调用点改为 _wait_for_usable_ip (行 %s)"
                    % ", ".join(str(i + 1) for i in hits))
    elif already:
        acts.append("跳过调用点替换 (worker_loop 内已是守门版)")
    else:
        raise SystemExit("[FAIL] worker_loop 内找不到 _force_rotate_ip(worker_id)")

    # 2) 再注入守门代码块（紧跟 rotate 块之后）
    if MARK in out:
        acts.append("跳过守门代码注入 (已存在)")
    else:
        if ROTATE_END not in out:
            raise SystemExit("[FAIL] 找不到 rotate 块，请先跑 exact_patch.py")
        out = out.replace(ROTATE_END, ROTATE_END + GUARD, 1)
        acts.append("已注入 _get_exit_ip / _wait_for_usable_ip")

    # 3) 顺手放宽 rotate 日志截断，之前 35 字符正好把 IP 截掉
    out2, k = re.subn(r"\{txt\[:35\]\}", "{txt[:120]}", out)
    if k:
        out = out2
        acts.append("rotate 日志截断 35 -> 120 字符")

    ast.parse(out)

    print("---- 改动清单 ----")
    for a in acts:
        print("  *", a)

    if out == src:
        print("[SKIP] 无需改动")
        return
    if args.dry_run:
        print("[dry-run] 未写盘")
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-guard-%s" % (args.reg, stamp)
    io.open(bak, "w", encoding="utf-8", newline="").write(src)
    io.open(args.reg, "w", encoding="utf-8", newline="").write(out)
    print("[OK] 已写入，备份: %s" % bak)


if __name__ == "__main__":
    main()
