# T19 工作日志（M3 · modelrouterd 模型路由）

## 2026-09-09 03:09 | 路由代理（subagent）

### 派单
- 任务 T19：实现 `services/modelrouterd.py`（模型路由：本地/云端调度 + 断网降级队列）。
- 契约依据：`tasks/contracts_m3.md §T19`、`tasks/contracts.md §2 §4`。

### 实现内容（services/modelrouterd.py）
- 标准库 `json / os / sys / threading / time / uuid` + `aios_sdk.AIOSService`，UTF-8。
- 订阅 `sys.model.request`、`sys.model.set_offline`、`evt.normalized`。
- 离线标志：内存布尔，初始 False，`threading.Lock` 保护。
  `sys.model.set_offline {offline}` → 更新标志 + 回 `{offline}`（有 req_id 回
  `evt.query.reply.<req_id>`，无 req_id 回固定主题 `evt.query.reply.model_offline`）。
- `route(task_type, payload)` 路由核心：
  - `simple_judgment/summarize` → `{routed:"local_stub", task_type, result}`（确定性桩）
  - `complex_reason/deep_chat`：
    - 在线 → `{routed:"cloud_mock", task_type, result}`
    - 离线 → append `run/model_degrade.json` → `{routed:"degraded_queued", task_type}`
  - 未知 task_type → 本地桩兜底（v0 约定，不崩溃）
- 降级队列 `run/model_degrade.json`：JSON array，每条 `{task_type, payload, ts}`；
  读-改-写（`threading.Lock` 保护），不存在则初始化 `[]`，读失败/非数组按空队列处理。
- 本地模型 v0 用确定性桩，不依赖真实 llama.cpp（真模型接入为后续任务）。

### 自测结论
- `python -m py_compile services\modelrouterd.py` → **exit=0 通过**。
- 内联单测 `python services\modelrouterd.py --selftest` → **11/11 全绿**：
  - simple_judgment / summarize → local_stub
  - complex_reason / deep_chat（在线）→ cloud_mock
  - set_offline(True) → 回 `{offline:true}`
  - complex_reason / deep_chat（离线）→ degraded_queued
  - 离线时 simple_judgment 仍 local_stub（简单任务仍本地）
  - 降级队列 append 2 条、条目含 task_type/payload/ts、首条 task_type=complex_reason
  - set_offline(False) → 回 `{offline:false}`；complex_reason 恢复在线 → cloud_mock
- 降级队列用系统临时目录下的独立文件（`%TEMP%\modelrouterd_selftest_degrade.json`）
  隔离，不污染项目 `run/model_degrade.json`。

### 契约符合性
- 路由分支、reply 载荷字段、离线降级行为与契约 §T19 完全一致；
  reply 走 `evt.query.reply.<req_id>`，符合总线契约 §2。
- 降级队列结构 `{task_type, payload, ts}` 与契约一致；线程锁保护读-改-写。
- 文件所有权：仅写 `services/modelrouterd.py`，未触碰 interactd.py / evolutiond.py / 其它。

### 遗留
1. 集成验收由指挥官执行 `tests/test_m3.py`（本代理未跑全栈）。
2. 安全护栏约束：本环境拦截 destructive file API，自测「清理」改为**写回 `[]` 的
   JSON 级清空**（未用文件删除 API）；空数组残留文件位于系统临时目录，可安全忽略。
3. 真模型接入（llama.cpp 等）为后续任务，v0 桩结果文本仅为确定性占位。

## 2026-09-09 03:20 | 最高指挥官
- 验收：test_m3.py 全栈实测，T19 相关项全部 PASS
- 结果：**通过 ✅**

> **执行方式**：DeepSeek V4 Pro 三路代理并发（交互 1m07s / 进化 4m09s / 路由 3m05s），首次交付即通过验收，零返工。test_m3.py 5/5 全绿。
