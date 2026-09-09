# T05 模拟事件源 + 剧本回放（simulator/）

- 里程碑：M0 · 负责代理：模拟测试代理 · 状态：🔵进行中 · 依赖：契约冻结

## 目标

给 OS 一副"假身体"：一个按剧本向总线发事件的模拟器，M0 验收和将来所有 PC 阶段开发都靠它喂事件。

## 实现方式（规划）

1. `simulator/simd.py`：
   - 以服务名 `simd` 走 SDK（或按契约裸连）接入总线
   - `--script <path> --loop N`：读剧本 JSON，按 delay_s 逐条发布 `{"t":"pub","topic":...,"msg":{...}}`
   - 剧本条目格式：`{"delay_s":0.5,"topic":"evt.sim.vital","event":{"id":"...","ts":0,"source":"sim","type":"vital","content":"心率 72"}}`（ts=0 表示发布时自动填当前时间；id 缺省自动 UUID）
2. `simulator/scripts/m0_smoke.json`：≥5 条事件，覆盖 vital / motion / message 至少三类，总时长 ≤10s
3. 自测：可起一个临时总线实例自测 simd 发布链路，**测完必须清理全部子进程**（不留占端口的僵尸）

## 文件所有权

只许写：`code/simulator/simd.py`、`code/simulator/scripts/*.json`、`code/simulator/README.md`

## 验收标准

- [ ] 剧本回放顺序与延迟正确
- [ ] 事件字段符合契约 §2（id/ts/source/type/content）
- [ ] 指挥官全栈验收中 simd 发布的事件可被服务收到

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
