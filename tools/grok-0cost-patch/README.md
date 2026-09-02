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

---

# arena-pc-bridge.user.js (v1.5.0)

油猴脚本改版。原 v1.4.2 的问题与修复：

| 问题 | 后果 | v1.5.0 |
|---|---|---|
| `isValidCommand` 拒绝时无任何日志 | 命令静默消失，无从排查 | console.warn + 面板红字显示拒绝原因与原文 |
| `BROKEN_RE` 含无锚点 `\.\.\.` | 任何带省略号的命令全废 | 改为 `^(cmd\|dir\|test\|测试\|\.\.\.\|<\|>)$` 全串锚定 |
| `BROKEN_RE` 含无锚点 `\\n\|\\r\|\\t` | **Windows 路径躺枪**：`D:\report` `D:\new` `D:\temp` 全被拒 | 改为 `looksMangled()`：需同时出现 `\n` 与 `\"` 且无真实换行才判定转义损坏 |
| `collectCodeBlocks` 对元素节点只向下搜 | 流式渲染往 `<code>` 插 `<span>` 时整条命令漏执行（随机复现） | 元素节点同时 `closest()` 向上 + `querySelectorAll` 向下 |
| 剪贴板失败无兜底 | 页面失焦时 `writeText` 抛 `NotAllowedError`，结果蒸发 | 面板常驻显示结果 + 手动「复制」按钮 + 窗口重获焦点自动重试 |
| 无兜底扫描 | observer 漏帧 = 永久丢失 | 每 1.5s 全量重扫一次 |
| `processed` 按命令文本永久去重 | 同一命令无法重跑 | 改为按代码块元素去重（WeakSet） |
| 超时 60s | 长任务误判超时 | 默认 180s，油猴菜单可调 |

## 新增

- 右下角悬浮面板：状态灯 / 执行日志 / stdout / stderr，可拖拽、可折叠
- 油猴菜单：`设置 Bridge 地址`、`设置超时(秒)`

## 已知限制

Bridge 返回的 stdout 若为 cp936 字节而桥按其它编码解码，会出现中文乱码（内容本身无损）。
在命令开头加 `[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;$env:PYTHONIOENCODING='utf-8';` 可规避。

## v1.6.0 — 请求/响应对账

v1.5.0 之前无法判断回传结果对应哪条指令（结果里只有一大坨命令原文，肉眼无法核对）。
v1.6.0 给每次执行加了关联信息：

```
【GPT PC AGENT 本地执行结果】
id=28997b93  seq=3  耗时=2.4s  发出=2026-09-02 23:41:05  命令长度=855
```

- `id` = 命令原文 UTF-8 的 SHA-256 前 4 字节。发指令方可以离线算出同一个值：
  `python cmd_id.py "<命令原文>"`（已验证浏览器 `crypto.subtle` 与 Python `hashlib` 结果逐字节一致）
- `seq` = 本次页面会话内的自增序号，跳号即代表有指令丢失
- `耗时` / `发出` = 定位是否拿到了旧结果
- 同一条命令重复执行会标 `[第N次执行同一命令]`

### 无需升级脚本的替代方案

在命令首尾自带标签，标签会直接出现在 stdout 里，v1.4.2 也适用：

```powershell
$TAG='PING-7F3A';"BEGIN $TAG"; <实际工作>; "END $TAG rc=$LASTEXITCODE"
```

## v1.6.1 — 历史块处理修正

v1.6.0 用「启动后 2.5s 内出现 = 历史」判定，两头都不对：

- 渲染慢 → 老命令落在窗口外，被当新命令**真的重跑**（危险）
- 渲染快 → 刚发的新命令落在窗口内，被**静默吞掉**（实测：刷新页面后 28 个块全被忽略，含一条待执行的 PING）

v1.6.1 改为按命令 ID 去重并持久化：

- `executedIds` 存进 GM storage（保留最近 300 条），跨刷新有效
- 已执行过的 → 静默跳过，日志可查
- 历史里**没执行过**的 → 不自动跑，在面板上挂一行 `⏸ [id] 历史中未执行的命令` + 「▶ 执行」/「忽略」按钮
- 启动窗口之后出现的 → 正常自动执行

这样既不会重放老命令，也不会凭空丢指令。

---

# add_ip_guard.py — 出口 IP 守门

`exact_patch.py` 之后运行。在 `worker_loop` 的每轮循环开头，把 `_force_rotate_ip(worker_id)`
换成 `_wait_for_usable_ip(worker_id)`：切完 IP 后**实测出口**，不可用就一直等，绝不放行注册。

判定不可用：
1. 探测 `cdn-cgi/trace` 失败
2. 解析不出 `ip=`
3. **代理出口 IP == 本机直连出口 IP** → 代理压根没生效

顺手把 rotate 日志截断从 35 放宽到 120 字符（35 正好把 IP 截掉，妨碍排查）。

## 开发中踩的坑

守门函数体内部本身就有一行 `_force_rotate_ip(worker_id)`（8 空格缩进）。
最初的实现是「先注入守门代码，再全局 `replace(..., 1)` 改调用点」——
`replace` 命中的是文件里**最先出现**的那处，也就是守门函数自己的调用，
结果 `_wait_for_usable_ip` 调用自己，**无限递归，worker 一启动就爆栈**。

修法：先用 AST 定位 `worker_loop` 的行范围、只在该范围内替换，然后才注入守门代码。
测试用例 `递归自检` 固化了这一点：`_wait_for_usable_ip` 内必须仍是 `_force_rotate_ip`。
