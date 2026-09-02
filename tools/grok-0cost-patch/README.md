# Grok 0元购流水线 —— 精准补丁器

给 `run_0cost_grok_register.py` 注入 **1号1IP** 与 **错峰启动** 两项改造，并生成配套启动 `.bat`。

## 快速开始

```powershell
cd tools\grok-0cost-patch
.\apply_patch.ps1 -DryRun     # 先看 diff
.\apply_patch.ps1             # 确认无误再落盘
```

或直接调 Python：

```powershell
python exact_patch.py --reg "D:\API中转\grok\run_0cost_grok_register.py"
```

---

## 你原来那条命令为什么报错

```powershell
python -c "... print(f\"🔄 [Worker-{wid}] 强切IP | 响应:\", ...)"
```

PowerShell **不支持 `\"` 转义**——那是 CMD / bash 的语法。PS 里双引号字符串内要写双引号，只能用 `` `" `` 或 `""`。
于是解析器在第一个 `\"` 处就把字符串提前闭合了，后面的 `响应:\, r.read()...` 被当成命令名：

```
无法将"响应:\, r.read()..."项识别为 cmdlet、函数、脚本文件或可运行程序的名称。
CategoryInfo: ObjectNotFound ... CommandNotFoundException
```

**规则：不要在 PowerShell 里用 `python -c "长脚本"`。** 用单引号 here-string（`@'...'@`，不做任何插值/转义）落盘成 `.py` 再执行，或者干脆像本目录一样把脚本存成文件。

---

## 相比第一版 `exact_patch.py` 修了什么

| # | 原版问题 | 后果 | 本版做法 |
|---|---|---|---|
| 1 | 用「行首是空格/Tab」猜函数边界 | 遇到空行夹注释、装饰器就切错 | `ast` 取 `lineno`/`end_lineno`，含装饰器 |
| 2 | 硬编码 `"    while True:\n"` 和 8 空格缩进 | **`while True:` 若嵌在 `try:` 里（缩进 12），会被拍平到缩进 4 → 逻辑错乱/语法错误** | 从 AST 的 `col_offset` 推导真实缩进 |
| 3 | 无幂等保护 | 跑两次就有两份错峰 sleep，等待时间翻倍 | 用 `# === GROK-0COST-PATCH: ... ===` 标记，已存在则跳过 |
| 4 | 直接覆盖原文件 | 改坏了没得回滚 | 自动备份 `xxx.py.bak-YYYYmmdd-HHMMSS` |
| 5 | 头部块插在文件最前 | 会把模块 docstring 挤成普通字符串；`from __future__` 位置也可能违规 | 跳过 shebang / coding / docstring / `__future__` 后再插 |
| 6 | 无预览 | 只能改完再看 | `--dry-run` 出 unified diff |
| 7 | 切 IP 失败无回执 | 分不清切成功还是超时 | `_force_rotate_ip` 返回 `True/False`，`flush=True` 保证多进程日志不乱序 |

> 第 2 条是真会咬人的：本目录测试用例里那个 `while True:` 正好嵌在 `try:` 内（缩进 12），原版脚本会直接写坏。

## 注入后的代码长这样

```python
def worker_loop(worker_id: int):
    """每个 worker 的主循环。"""
    # === GROK-0COST-PATCH: stagger-start ===
    _delay = max(0, worker_id - 1) * 12 + _p_random.uniform(1.0, 3.0)
    print(f"🎲 [Worker-{worker_id}] 错峰等待 {_delay:.1f} 秒后启动...", flush=True)
    _p_time.sleep(_delay)
    # === GROK-0COST-PATCH: end stagger-start ===
    fails = 0
    try:
        while True:
            # === GROK-0COST-PATCH: rotate-per-loop ===
            _force_rotate_ip(worker_id)
            ok = register_once(worker_id)
            ...
```

Worker-1 立即启动，Worker-2 等 ~12s，Worker-3 等 ~24s，Worker-4 等 ~36s（各带 1–3s 随机抖动）。

## 生成的 .bat

GBK 编码 + CRLF 换行（中文 Windows CMD 直接可用），流程：
清洗节点 → 起代理中枢(10809 转发 / 10810 切 IP) → 起 Turnstile 打码(8889) → 预热 8s → 起 4 进程注册。

比原版多了 `.venv\Scripts\python.exe` 存在性检查，路径引号也收紧成 `set "PY=..."` 形式，避免路径含空格时炸掉。

## 回滚

```powershell
Copy-Item "D:\API中转\grok\run_0cost_grok_register.py.bak-20260902-150225" `
          "D:\API中转\grok\run_0cost_grok_register.py" -Force
```
