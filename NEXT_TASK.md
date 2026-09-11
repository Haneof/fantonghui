# NEXT TASK · AIOS V1.4 OS 主线

> 当前唯一架构依据：`docs/AIOS_Constitution_V1.4-r0.md`
> 当前 OS 主线：`aios/01_os/`

## 当前最高优先级

### 1. 架构迁移

把现有旧 Event/World/Memory/Attention/Wake 结构逐步迁移到：

```text
Observation
→ Global Timeline
→ Dimension
→ Trigger
→ AI Session
→ Inference Event
→ Help / Action
→ Outcome
→ AI Self Update
```

### 2. 禁止继续扩大旧架构

- 不新增旧三棵树 Runtime。
- 不新增旧 Relevance/Attention 语义判断。
- 不让本地小模型承担复杂语义判断。
- 不在 `core/` 增加新功能。

### 3. 当前开发顺序

```text
Observation Contract
→ Timeline
→ Dimension
→ Trigger
→ AI Session
→ Event/Cognition
→ Outcome/Self Update
→ 3D/UI
→ Phone
→ Wearable
```

## 验收要求

每完成一项，必须提供：

1. 修改文件清单
2. 实际运行命令
3. 原始 stdout/stderr
4. 测试结果
5. 与 V1.4 Contract 的一致性说明

**Agent 声称完成 ≠ 完成。实测证据才算完成。**
