# AIOS Core —— 开始构建说明

## 当前唯一有效架构依据

**AIOS Constitution V1.4-r1** 是当前 AIOS 唯一有效 Constitution。

旧 Constitution、旧 `core/` Runtime、旧架构入口已经从 `aios` 分支删除。不要从 Git 历史恢复它们作为当前设计依据。

## 开发者第一入口

先读：

1. `docs/AIOS_Constitution_V1.4-r1.md`
2. `AIOS_DEVELOPMENT_TASKS.md`
3. `docs/05_AI_RUNTIME.md`
4. `docs/06_REPOSITORY_LAYOUT.md`
5. `docs/07_DEVELOPMENT_PLAN.md`
6. `docs/08_ACCEPTANCE_TESTS.md`

## 当前唯一产品主线

```text
aios/01_os/
```

## 当前规范主链

```text
Reality / Observation
    → Global Timeline
    → User / World Dimensions + AI Dimensions
    → Trigger
    → AI Session
    → Identity Bootstrap
    → Autonomous Context Construction
    → Cognitive Runtime
    → Help / Decision / Action / Silence
    → Outcome
    → Cognitive Delta
    → AI Self Update
    → Persistent Cognition / Handoff
```

## 两条不可混淆的概念

### Dimension Curve

Dimension 是基于唯一 Global Timeline 的动态观察视角；Dimension Point 是带时间、证据、来源、置信度的时间锚点。Dimension 不是静态字段、标签集合或当前快照。

### Cognitive Mechanism

Cognitive Mechanism 是 AI 认识世界、选择信息、形成假设、交叉验证和决定是否帮助的机制。除 Identity First 外，AIOS 不规定固定的 Dimension 阅读顺序。

## Identity First

任何 AI Instance 进入 AIOS 后必须先完成身份建立：

- 我是谁
- 我是运行在 AIOS 中的 AI Instance，而不是 AIOS 本身
- 当前 Session / Wake Reason
- 当前角色、责任、权限和能力
- 持久认知位于 AIOS，不等于当前 LLM Context

完成后，AI 才开始自主认识当前世界。

## 最终工程目标

AIOS 的目标不是堆积 Memory、Tools 或 App，而是建立一个持续运行的个人世界，让 AI 能基于长期世界、关系、经验、人格与结果，越来越懂用户，并在正确的时候提供真正有价值的帮助。
