# AIOS 文档入口（V1.4）

> 当前有效架构：**AIOS Constitution V1.4-r0**。
>
> 旧 V1.2 / V1.3、旧 Core、旧 Runtime 只能作为历史参考，不得作为新代码设计依据。

## 开发者阅读顺序

1. `AIOS_Constitution_V1.4-r0.md` — 最高架构准则
2. `OS_ARCHITECTURE_V1.4.md` — OS 实现架构
3. `RUNTIME_CONTRACTS_V1.4.md` — Runtime 接口边界
4. `DATA_MODEL_V1.4.md` — Observation / Timeline / Dimension / Trigger / AI 数据模型
5. `DEVELOPMENT_PLAN_V1.4.md` — 当前开发顺序
6. `ACCEPTANCE_V1.4.md` — 验收标准

## 当前主线

产品 OS 主线只允许在：

```text
aios/01_os/
```

进行新开发。

## 明确禁止

- 不得继续在根目录旧 `00_*`～`09_*` 文档上设计新 Runtime。
- 不得继续扩展旧 `core/` 作为第二套 OS。
- 不得把 Semantic Event 当作底层第一公民；底层第一公民是 Observation。
- 不得在本地用小模型做复杂语义筛选；本地 Runtime 只做机械检测、清洗、记录、触发和资源控制。
- 不得让 UI 建立自己的 AI、Memory、Timeline 或 Wake Runtime。

## 历史资产

旧文档和旧代码不会因为失效而自动删除历史价值。需要复用算法时，必须先证明它与 V1.4 不冲突，再迁移到 `aios/01_os/`。
