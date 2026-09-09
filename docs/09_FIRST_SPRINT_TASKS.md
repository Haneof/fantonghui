# AIOS Core 第一开发冲刺任务单 V0.1-r1

## Sprint 1：Event + World（对应 Phase 1）

### Task 1

建立项目目录、Runtime 骨架和统一 schema。

### Task 2

实现 Perception Runtime 的最小合同与 Simulator Adapter：Simulator 可注入 mock raw signal，并由适配器产出 Semantic Event；不接真实硬件、不接真实 ASR/视觉模型。

### Task 3

实现 Event 输入和 JSONL 持久化。

### Task 4

实现 Event 去重（最小实现）。去重属于 Event Runtime 既定职责（02 §1），实现在 `core/event/event_runtime.py`，不得放入其他目录。

### Task 5

实现 Entity。

### Task 6

实现 World State。

### Task 7

实现 Event -> World Update。

### Task 8

实现 World Change Delta。

### Task 9

做一个模拟器，能够按时间线播放用户的一天。

示例事件：

```text

09:00 到公司

09:05 张总进入

09:06 谈合同

09:08 张总提出降价

09:10 用户沉默

09:12 打开合同

09:15 再次谈价格

```

## Sprint 1 禁止事项

1. 不得修改 AIOS Constitution V1.2-r1。

2. 不得自行改变 Runtime 边界。

3. 不得提前开发 Sprint 2/3。

4. 不得接入大模型。

5. 不得用 Simulator 绕过 Perception Runtime。

6. 不得将去重实现到不属于 Event Runtime 的目录。

7. 不得自行宣布 READY/PASS，必须返回真实测试结果。

## Sprint 2：Memory（对应 Phase 2）

### Task 1

实现 RAW semantic event log。

### Task 2

实现 hourly/daily/weekly/monthly/quarterly/half-yearly/yearly/3year 摘要链。

### Task 3

实现 time index。

### Task 4

实现 entity index。

### Task 5

实现 domain/topic index。

### Task 6

确保事实、摘要、原始语义事件可追溯。

## Sprint 3：Relevance + Attention + Wake（对应 Phase 3）

### Task 1

去重策略调优 + 与 Event Fusion 联动（最小实现已在 Sprint 1 Task 4 落地）。

### Task 2

实现滑动时间窗口。

### Task 3

实现事件聚类 / Temporal Pattern。

### Task 4

实现趋势检测。

### Task 5

实现 baseline deviation。

### Task 6

实现 Relevance。

### Task 7

实现 Attention。

### Task 8

实现 Wake。

### Task 9

实现 Active Watch。

### Task 10

实现 Lease Manager。

## Sprint 4：AI Runtime（对应 Phase 4）

### Task 1

AI Identity。

### Task 2

Cognitive Tree。

### Task 3

Growth Tree。

### Task 4

World Access Session。

### Task 5

Model Router。

### Task 6

Structured Output。

## 第一阶段不要做的东西

- 不先做手环工业设计。

- 不先做完整手机 App。

- 不先做大量领域。

- 不先做“万能小模型”。

- 不把大模型放在 Event 前面。

- 不让每条 Event 都请求云端模型。

- 不让模型直接写 Memory fact。

- 不让模型绕过 Permission/Safety。
