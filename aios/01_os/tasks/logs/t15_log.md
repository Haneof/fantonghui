# T15 工作日志 · attentiond 注意力引擎（算力租约发放/回收）

## 2026-09-09 02:5x | 租约代理（subagent）

### 交付
- `code/services/attentiond.py`：M2 · T15 租约代理 v0（Python 3.13 标准库 + aios_sdk）

### 实现要点
- 租约表（内存 dict）：`{lease_id: {event_id, deadline, state}}`，state ∈ ACTIVE/RELEASED/EXPIRED，`threading.Lock` 保护
- 订阅 `evt.stream` / `sys.lease.request` / `sys.lease.release`
- `sys.lease.request {req_id, event_id, budget_ms}` → `lease_id=uuid4`，`deadline=time.time()+budget_ms/1000` → 回 `evt.query.reply.<req_id> {lease_id, deadline, budget_ms}`
- `sys.lease.release {lease_id}` → 存在则置 RELEASED（幂等）→ 回 `{released:true}`；不存在回 `{released:false}`（无 req_id 时回 `evt.lease.released`）
- 后台线程每 0.2s：扫描 ACTIVE 且 now>deadline → EXPIRED → 发布 `evt.lease.expired {lease_id, event_id}`
- 每次变更后全量重写 `run/lease_stats.json {granted, active, released, expired}`；启动时落一份全零计数
- 对 `evt.stream`：v0 被动，不自动发租约
- 核心逻辑抽为 `LeaseEngine`（publish 可注入），与总线解耦，便于单测

### 自测结论
- `python -m py_compile services/attentiond.py` → **PY_COMPILE_OK**
- 内联单测（不连总线，直接调 LeaseEngine）17/17 全绿：
  - request(budget_ms=300) → deadline ≈ now+300ms（容差 ±0.05s）✓
  - release 后该租约不再触发 expired（expired 仅计 ACTIVE 超时者）✓
  - 超时扫描后 expired 计数 1 → 2 递增 ✓
  - 另覆盖：state 迁移、event_id 回填、reply 主题/字段、stats 文件落盘内容、释放不存在租约返回 False ✓

### 契约符合性
- 对齐 contracts_m2.md §T15 与 contracts.md §4（AIOSService 接口：hello/sub/hb 由 SDK 处理，仅用 publish/on_event）
- 文件所有权：仅写 `services/attentiond.py`；`run/lease_stats.json` 为运行期产物，非源码文件
- 未跑全栈（集成验收 test_m2.py 由指挥官执行）

### 遗留
- 内联单测的 stats 文件写于系统临时目录（`%TEMP%\t15_selftest_*.json`），为一次性验证产物，未触碰仓库 `run/` 目录，随系统临时目录自清；无 repo 内残留
- 释放路径的 `req_id` 契约未在 contracts_m2.md 明示，实现做了双兜底（有 req_id → query.reply，无 → evt.lease.released），与请求路径保持一致

## 2026-09-09 03:05 | 最高指挥官
- 验收：test_m2.py 全栈实测，T15 相关项全部 PASS
- 结果：**通过 ✅**

> **执行方式**：M2 恢复多代理并行——3 路代理用 DeepSeek V4 Pro（zai/tdpsk_deepseek-v4-pro-202606）并发开发（认知 4m6s / 租约 4m54s / 决策 9m54s），首次协同即通过验收。验收套件 test_m2.py 由指挥官编写（期间修正了测试脚本自身的 2 处 bug：漏 sub 订阅 + makefile 超时读法脆弱），代理代码本体零返工。test_m2.py 8/8 全绿。
