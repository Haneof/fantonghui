# T17 日志 · interactd（交互系统）

## 任务
实现 interactd 交互系统：五级介入通道选择，最低打扰优先。

## 产物
- 代码文件：`code/services/interactd.py`

## 自测结论
- `python -m py_compile services/interactd.py` → **通过**（PY_COMPILE_OK）
- 内联单测 `python services/interactd.py --selftest` → **PASSED (6/6)**
  - SOCIAL 默认 → VISUAL ✔
  - SOCIAL+high → BONE_CONDUCTION ✔
  - SAFETY → HAPTIC ✔
  - FINANCIAL → HAPTIC ✔
  - 其它(未知) → VISUAL ✔
  - 空 risk_class → VISUAL ✔

## 契约符合性（contracts_m3.md §T17）
- 订阅 `evt.normalized`、`sys.interact.request` ✔
- 非对称通道规则：SAFETY→HAPTIC / SOCIAL→(high?BONE_CONDUCTION:VISUAL) / FINANCIAL→HAPTIC / 其它→VISUAL ✔
- 结果发布 `evt.intervention` `{intervention_id, risk_class, channel, priority, ts}`（intervention_id=uuid4，ts=unix 秒）✔
- 回 `evt.query.reply.<req_id>` `{intervention_id, channel}` ✔
- 服务启动打日志 ✔
- evt.normalized v0 仅接收不处理 ✔

## 通道等级（记录）
VISUAL(0) < HAPTIC(1) < BONE_CONDUCTION(2) < EXECUTE(3)；SILENT_WATCH 表示不介入（v0 未产生，保留语义）。

## 纪律核对
- 仅标准库（os/sys/time/uuid + aios_sdk）✔
- UTF-8 声明 ✔
- 只写 interactd.py 一个名下文件 ✔
- 未跑全栈（集成验收由指挥官 test_m3.py 执行）✔

## 遗留
- 无。EXECUTE(3) 通道与 SILENT_WATCH 在 v0 需求中未触发，代码中保留等级常量与语义说明，待后续任务接入。

## 2026-09-09 03:20 | 最高指挥官
- 验收：test_m3.py 全栈实测，T17 相关项全部 PASS
- 结果：**通过 ✅**

> **执行方式**：DeepSeek V4 Pro 三路代理并发（交互 1m07s / 进化 4m09s / 路由 3m05s），首次交付即通过验收，零返工。test_m3.py 5/5 全绿。
