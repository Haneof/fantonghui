# T04 十五个服务空壳（services/*.py）

- 里程碑：M0 · 负责代理：空壳代理 · 状态：🔵进行中 · 依赖：T02 SDK 契约冻结

## 目标

15 个服务的"入职报到版"：每人连上总线、报上名字、心跳常亮、收到事件记日志；其中两个接线成回声链路供 M0 验收。**不实现任何业务逻辑**（那是 M1-M3 的活）。

## 实现方式（规划）

1. 15 个文件：hublinkd / stated / safetyd / privacyd / modemgrd / attentiond / perceptiond / entityd / memoryd / cognitiond / decisiond / abilityd / interactd / evolutiond / modelrouterd
2. 标准模板（13 个普通空壳）：
   ```python
   from aios_sdk.aios_sdk import AIOSService
   svc = AIOSService("<name>", subscribe=["evt.#"],
                     on_event=lambda t, f, m: svc.log(f"收到 {t} 来自 {f}: {m.get('content','')}"))
   svc.log("服务启动（M0 空壳）")
   svc.run()
   ```
3. **回声链路（验收 A1 专用接线）**：
   - `hublinkd`：订阅 `["sys.test.#"]`，收到 `sys.test.ping` → `publish("evt.hub.echo", {"id":..,"ts":..,"source":"hublinkd","type":"echo","content":原始content})`
   - `perceptiond`：订阅 `["evt.#"]`，收到 `evt.hub.echo` → `log("【回声链路OK】" + content)`
4. `safetyd` 顶部注释标明 always_on（M0 行为与普通空壳一致）
5. 全部文件 `python -m py_compile` 自检

## 文件所有权

只许写：`code/services/hublinkd.py`、`stated.py`、`safetyd.py`、`privacyd.py`、`modemgrd.py`、`attentiond.py`、`perceptiond.py`、`entityd.py`、`memoryd.py`、`cognitiond.py`、`decisiond.py`、`abilityd.py`、`interactd.py`、`evolutiond.py`、`modelrouterd.py`

## 验收标准

- [ ] 15 个文件齐全，py_compile 全过
- [ ] 全部基于 SDK，无自行连总线代码（A4）
- [ ] 回声链路接线正确（A1 依赖）
- [ ] 指挥官全栈验收 A3 时 15 服务心跳全绿

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
