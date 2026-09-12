# AIOS Repository Layout V1.4-r2

`aios/01_os/` 是唯一 OS 产品实现主线。文档规范统一位于 `docs/`。

## 当前结构

```text
aios/01_os/
├─ code/              # 生产代码
├─ services/          # 系统服务
├─ schemas/           # 数据与接口契约
├─ adapters/          # 手机、硬件、外部世界适配器
├─ simulator/         # PC/Linux 世界与设备模拟器
├─ tasks/             # OS 内部实现任务
└─ roadmap.md         # OS 主线路线

docs/
├─ AIOS_Constitution_V1.4-r2.md
├─ AIOS_Architecture_V1.4-r2.md
├─ 05_AI_RUNTIME.md
├─ 06_REPOSITORY_LAYOUT.md
├─ 07_DEVELOPMENT_PLAN.md
├─ 08_ACCEPTANCE_TESTS.md
└─ README.md

AIOS_DEVELOPMENT_TASKS.md     # 唯一实时任务账本
AIOS_PROJECT_EXECUTION_MASTER_V1.0.md
```

## 生产模块映射

```text
aios/01_os/code/
├─ system/             # 系统基础
├─ ingress/            # 现实接入 / Observation
├─ world/              # Timeline / 世界对象 / 关系 / 索引
├─ cognition/          # User/World + AI Dimensions / 认知
├─ trigger/            # Trigger / MODE / Watch
├─ ai_service/         # AI Session / Cognitive Runtime / Help
├─ capability/         # 统一能力接口与路由
├─ model/              # 模型接入与路由
├─ apps/               # AI 能力应用
├─ interaction/        # UI / 触摸 / 语音 / 震动等
└─ safety/             # 人身安全与紧急升级
```

实际代码可以继续细分，但不得创建与上述职责重复的第二套 Runtime。

## 模块边界

- `system`：生命周期、调度、存储、电源、权限、更新。
- `ingress`：获取现实数据，不能代替 AI 做复杂语义判断。
- `world`：事实、时间轴、实体、关系、事件、关键词/实体导航。
- `cognition`：长期用户世界与 AI 世界的动态认知。
- `trigger`：机械唤醒和模式状态，不代替 AI 判断。
- `ai_service`：统一 AI 服务，不区分两个独立的主动/被动 AI。
- `capability`：将 AI 意图映射为可执行能力。
- `model`：统一接入可替换 AI 模型。
- `apps`：专业 AI 能力领域，不复制传统手机应用。
- `interaction`：输入输出，不拥有独立认知。
- `safety`：安全协议和硬性升级边界。

## 适配器原则

第一阶段：

```text
PC/Linux
  ↓
Simulator
  ↓
完整 AIOS 软件
```

第二阶段：

```text
Phone Adapter
```

第三阶段：

```text
Wearable Adapter
```

模拟器、手机和手环都必须通过稳定接口进入 AIOS，不能反向污染核心认知模型。

## 禁止

- 根目录重新建立 `core/`、`schemas/`、`tests/` 第二套主线。
- 建立第二套 AI Runtime。
- 在每个 AI 能力应用内建立独立 Memory / Personality / Relationship。
- 把 UI 当作 AI 大脑。
- 把具体模型供应商写死进核心认知。
