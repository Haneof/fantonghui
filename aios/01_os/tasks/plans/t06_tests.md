# T06 M0 验收测试套件（tests/test_m0.py）

- 里程碑：M0 · 负责代理：模拟测试代理 · 状态：🔵进行中 · 依赖：T01-T05 全部契约

## 目标

M0 门禁的自动化裁判：一条命令跑完全部验收（A1-A5），全绿 exit 0，任何一项失败 exit 1 并打印明细。**这是指挥官验收的执行工具，它的公正性就是验收的公正性。**

## 实现方式（规划）

`tests/test_m0.py` 流程：

1. **起栈**：子进程拉起 `aiosd/aiosd.py`（它会带起 bus + 15 服务）；cwd = code 根
2. **A3 心跳全绿**：轮询 `run/health.json`，20s 内 bus + 15 服务全部 state=up 且 last_hb 距今 <3s → PASS，否则 FAIL
3. **A1 事件互通**：以服务名 `testdriver` 裸连总线（契约 §2），发布 `sys.test.ping`（msg 含 id/ts/source/type/content），5s 内断言收到 `evt.hub.echo` → PASS/FAIL
4. **A2 击杀复活**：从 health.json 随机挑一个服务（非 bus），`taskkill /F /PID <pid>`，1.5s 内该服务 pid 变化且 state=up → PASS/FAIL
5. **A5 日志齐全**：`run/logs/` 非空日志文件 ≥15 个 → PASS/FAIL
6. 明细打印每项 PASS/FAIL 与耗时；全绿 exit 0
7. **finally 清理**：终止 aiosd 进程树（taskkill /T /F aiosd pid），确认 7800 端口释放

注意：全栈集成运行**由指挥官执行**；你自测只做 py_compile + 可用极简 mock 总线单测 simd/测试脚本的纯函数部分（测完清理）。

## 文件所有权

只许写：`code/tests/test_m0.py`、`code/tests/README.md`

## 验收标准

- [ ] A1-A5 五项裁判逻辑与契约 §8 完全一致
- [ ] 失败时输出可定位的明细（哪项、期望、实际）
- [ ] 清理彻底（无孤儿进程、端口释放）
- [ ] 指挥官实跑全绿

## 进度

| 时间 | 事项 | 结果 |
|---|---|---|
| 2026-09-09 01:55 | 任务书下达，代理开工 | 🔵 |

## 验收记录（指挥官填写）

（待代理交付后填写）

## 验收记录（指挥官填写）

### 2026-09-09 02:26 | 最高指挥官
- 验收方式：实跑 M0 验收套件 test_m0.py（A1-A5）+ 任务专项实测
- 结果：**通过 ✅**
- 明细：A3 心跳全绿 2.4s（15/15）· A1 事件互通 0.2s · A2 击杀复活 0.7s（门禁 1.5s）· A4 无契约违规 · A5 日志 16 个
- 执行说明：代理配额故障，指挥官 fallback 亲建（见 TXX_log.md），验收标准未降低
