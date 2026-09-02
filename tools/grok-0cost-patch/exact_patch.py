# -*- coding: utf-8 -*-
"""
Grok 0元购流水线 —— 精准补丁器 (AST 版, 可重复执行)

修复原脚本的问题:
  1. 不再用「行首空格」猜函数边界, 改用 ast 定位 def 的 lineno/end_lineno
  2. while True: / 函数体 的缩进按原文推导, 不再硬编码 4/8 空格
  3. 幂等: 重复执行不会叠加多份错峰代码
  4. 写入前自动备份 xxx.py.bak-YYYYmmdd-HHMMSS
  5. ast.parse 校验失败则原文件保持不动
  6. 支持 --dry-run 只看 diff 不落盘

用法:
    python exact_patch.py
    python exact_patch.py --dry-run
    python exact_patch.py --reg "D:\\API中转\\grok\\run_0cost_grok_register.py"
"""
import argparse
import ast
import datetime
import difflib
import io
import os
import sys

DEFAULT_REG = r"D:\API中转\grok\run_0cost_grok_register.py"
DEFAULT_BAT = r"D:\API中转\grok\启动_Grok_0元购全自动流水线.bat"

MARK_HEADER = "# === GROK-0COST-PATCH: rotate-ip (auto-generated, do not edit by hand) ==="
MARK_DELAY = "# === GROK-0COST-PATCH: stagger-start ==="
MARK_ROTATE_CALL = "# === GROK-0COST-PATCH: rotate-per-loop ==="

ROTATE_BLOCK = '''{mark}
import random as _p_random
import time as _p_time
import urllib.request as _p_urlreq

ROTATE_URL = "http://127.0.0.1:10810/rotate"
ROTATE_TIMEOUT = 4


def _force_rotate_ip(worker_id=0):
    """通知代理中枢切换出口 IP (1号1IP)。失败只告警, 不中断注册流程。"""
    try:
        req = _p_urlreq.Request(ROTATE_URL, headers={{"Connection": "close"}})
        with _p_urlreq.urlopen(req, timeout=ROTATE_TIMEOUT) as resp:
            txt = resp.read().decode("utf-8", errors="ignore").strip()
        print(f"\\U0001F504 [Worker-{{worker_id}}] 代理中枢已切 IP | 响应: {{txt[:35]}}", flush=True)
        return True
    except Exception as e:
        print(f"\\u26A0\\uFE0F [Worker-{{worker_id}}] 切 IP 提示: {{e}}", flush=True)
        return False
# === GROK-0COST-PATCH: end rotate-ip ===
'''.format(mark=MARK_HEADER)


BAT_CODE = """@echo off
title Grok 0元购全自动流水线
cd /d "%~dp0"

set "PY=%~dp0..\\代理池\\IPDEEP中枢\\.venv\\Scripts\\python.exe"

if not exist "%PY%" (
    echo [错误] 找不到虚拟环境 Python: %PY%
    echo         请确认 代理池\\IPDEEP中枢\\.venv 已创建。
    pause
    exit /b 1
)

echo =======================================================================
echo [1/4] 步骤一：正在执行代理节点清洗与测速...
echo =======================================================================
if exist "%~dp0..\\代理池\\clean_nodes.py" (
    "%PY%" "%~dp0..\\代理池\\clean_nodes.py"
) else (
    echo [提示] 未找到 clean_nodes.py，跳过清洗直接启动
)

echo.
echo =======================================================================
echo [2/4] 步骤二：正在启动公共代理中枢 (10809转发 / 10810切IP)...
echo =======================================================================
start "Proxy" /D "%~dp0..\\代理池\\IPDEEP中枢" "%PY%" "proxy_relay.py"

echo.
echo =======================================================================
echo [3/4] 步骤三：正在启动 0元 Turnstile 本地打码引擎 (端口 8889)...
echo =======================================================================
start "Solver" /D "%~dp0..\\本地打码\\Turnstile解算" "%PY%" "services\\turnstile_solver\\start.py" --port 8889 --thread 4 --browser_type camoufox

echo.
echo [等待] 给中枢与打码引擎 8 秒预热时间...
timeout /t 8 /nobreak > nul

echo.
echo =======================================================================
echo [4/4] 步骤四：正在启动 Grok 4进程 (1号1IP + 错峰并发) 自动注册...
echo =======================================================================
"%PY%" -u "run_0cost_grok_register.py" 4

echo.
echo [完成] 流水线已退出。
pause
"""


def read_source(path):
    with io.open(path, "r", encoding="utf-8-sig", errors="strict") as f:
        return f.read()


def find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def node_span(node):
    """返回 (start_line, end_line) 1-based 闭区间, 含装饰器。"""
    start = node.lineno
    for d in getattr(node, "decorator_list", []):
        start = min(start, d.lineno)
    return start, node.end_lineno


def first_real_stmt(func):
    """跳过 docstring, 返回函数体第一条真实语句。"""
    body = func.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1] if len(body) > 1 else None
    return body[0] if body else None


def find_while_true(func):
    """在 func 内找第一个 `while True:` (不下钻进嵌套函数)。"""
    stack = list(func.body)
    found = []
    while stack:
        node = stack.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.While):
            t = node.test
            if isinstance(t, ast.Constant) and t.value is True:
                found.append(node)
        for child in ast.iter_child_nodes(node):
            stack.append(child)
    found.sort(key=lambda n: n.lineno)
    return found[0] if found else None


def insertion_indent(node):
    return " " * node.col_offset


def patch_source(src):
    """返回 (new_src, [做过的改动描述])。"""
    actions = []
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    worker = find_func(tree, "worker_loop")
    if worker is None:
        raise SystemExit("[FAIL] 源码里找不到 def worker_loop(...)，请确认文件路径正确。")

    # ---- 收集所有编辑, 稍后按行号倒序执行, 避免行号漂移 ----
    edits = []  # (start_line_1based, end_line_1based_exclusive, [new lines])

    # 1) 旧的 _force_rotate_ip 整个删掉 (按 AST 边界, 不靠缩进猜)
    #    注意: 只删「不是本补丁生成的」那份, 否则重复执行会把自己的定义删掉
    if MARK_HEADER in src:
        actions.append("跳过删除 _force_rotate_ip (当前那份由本补丁生成)")
    else:
        old_rot = find_func(tree, "_force_rotate_ip")
        if old_rot is not None:
            s, e = node_span(old_rot)
            edits.append((s, e + 1, []))
            actions.append("删除旧的 _force_rotate_ip (第 %d-%d 行)" % (s, e))

    # 2) while True: 内首行插入 _force_rotate_ip(worker_id)
    if MARK_ROTATE_CALL in src:
        actions.append("跳过 rotate 调用注入 (已存在)")
    else:
        wnode = find_while_true(worker)
        if wnode is None:
            raise SystemExit("[FAIL] worker_loop 里找不到 `while True:`，无法注入切 IP 调用。")
        body_stmt = wnode.body[0]
        ind = " " * body_stmt.col_offset
        block = [
            "%s%s\n" % (ind, MARK_ROTATE_CALL),
            "%s_force_rotate_ip(worker_id)\n" % ind,
        ]
        edits.append((body_stmt.lineno, body_stmt.lineno, block))
        actions.append("在 while True: 首行注入 _force_rotate_ip(worker_id) (第 %d 行, 缩进 %d)"
                       % (body_stmt.lineno, body_stmt.col_offset))

    # 3) worker_loop 开头插入错峰等待
    if MARK_DELAY in src:
        actions.append("跳过错峰逻辑注入 (已存在)")
    else:
        anchor = first_real_stmt(worker)
        if anchor is None:
            raise SystemExit("[FAIL] worker_loop 函数体为空。")
        ind = " " * anchor.col_offset
        block = [
            "%s%s\n" % (ind, MARK_DELAY),
            "%s_delay = max(0, worker_id - 1) * 12 + _p_random.uniform(1.0, 3.0)\n" % ind,
            "%sprint(f\"\\U0001F3B2 [Worker-{worker_id}] 错峰等待 {_delay:.1f} 秒后启动...\", flush=True)\n" % ind,
            "%s_p_time.sleep(_delay)\n" % ind,
            "%s# === GROK-0COST-PATCH: end stagger-start ===\n" % ind,
        ]
        edits.append((anchor.lineno, anchor.lineno, block))
        actions.append("在 worker_loop 开头注入错峰等待 (第 %d 行, 缩进 %d)" % (anchor.lineno, anchor.col_offset))

    # ---- 倒序应用 ----
    for start, end, new in sorted(edits, key=lambda x: x[0], reverse=True):
        lines[start - 1:end - 1] = new

    out = "".join(lines)

    # 4) 头部 rotate 模块块 (放在 shebang / encoding / __future__ 之后)
    if MARK_HEADER in out:
        actions.append("跳过 rotate 头部块注入 (已存在)")
    else:
        head_lines = out.splitlines(keepends=True)
        htree = ast.parse(out)
        idx = len(head_lines)  # 兜底: 追加到文件末尾
        skip = 0
        # 跳过模块 docstring 与 __future__ 导入, 它们必须留在最前面
        while skip < len(htree.body):
            st = htree.body[skip]
            is_doc = (
                skip == 0
                and isinstance(st, ast.Expr)
                and isinstance(getattr(st, "value", None), ast.Constant)
                and isinstance(st.value.value, str)
            )
            is_future = isinstance(st, ast.ImportFrom) and st.module == "__future__"
            if is_doc or is_future:
                skip += 1
                continue
            break
        if skip < len(htree.body):
            idx = htree.body[skip].lineno - 1
        elif htree.body:
            idx = htree.body[-1].end_lineno
        head_lines[idx:idx] = ["\n" + ROTATE_BLOCK + "\n"]
        out = "".join(head_lines)
        actions.append("在第 %d 行前插入 _force_rotate_ip 定义块" % (idx + 1))

    ast.parse(out)  # 语法校验, 失败就抛异常, 不会写盘
    return out, actions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reg", default=DEFAULT_REG, help="run_0cost_grok_register.py 路径")
    ap.add_argument("--bat", default=DEFAULT_BAT, help="要生成的 .bat 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff, 不写文件")
    ap.add_argument("--no-bat", action="store_true", help="不生成 .bat")
    args = ap.parse_args()

    if not os.path.isfile(args.reg):
        raise SystemExit("[FAIL] 找不到文件: %s" % args.reg)

    src = read_source(args.reg)
    new_src, actions = patch_source(src)

    print("---- 改动清单 ----")
    for a in actions:
        print("  *", a)

    if src == new_src:
        print("[SKIP] 源码无需改动 (已是补丁后状态)。")
    elif args.dry_run:
        print("\n---- DIFF (dry-run, 未写盘) ----")
        for l in difflib.unified_diff(src.splitlines(True), new_src.splitlines(True),
                                      "before", "after", n=2):
            sys.stdout.write(l)
    else:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = "%s.bak-%s" % (args.reg, stamp)
        with io.open(bak, "w", encoding="utf-8", newline="") as f:
            f.write(src)
        with io.open(args.reg, "w", encoding="utf-8", newline="") as f:
            f.write(new_src)
        print("[OK] Python 源码修改成功 (已备份: %s)" % bak)

    if not args.no_bat:
        if args.dry_run:
            print("\n[dry-run] 将生成 bat: %s" % args.bat)
        else:
            with io.open(args.bat, "w", encoding="gbk", errors="replace", newline="\r\n") as f:
                f.write(BAT_CODE)
            print("[OK] 启动 .bat 已写入: %s" % args.bat)


if __name__ == "__main__":
    main()
