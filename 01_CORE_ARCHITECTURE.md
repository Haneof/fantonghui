# AIOS Core Architecture V0.1

## 1. 架构目标

把 AIOS 宪法落实成一个真正可运行的底座，而不是一堆功能模块。

核心原则：

- AIOS 是持续存在的 World Runtime。

- AI 是进入这个 World 的认知与行动主体。

- Model 只是 AI Runtime 的算力提供者。

- Facts / Cognition / Growth 严格分离。

- 原始感知短暂存在，长期保存语义事件与世界历史。

- 大模型不是逐条消息过滤器。

## 2. 总体结构

```text

Hardware / RTOS / Linux

        |

        v

+-----------------------------+

| AIOS Core Runtime            |

|                             |

|  Device Adapter              |

|  Perception / Semanticizer   |

|  Event Runtime               |

|  Identity Runtime            |

|  World Runtime               |

|  State Runtime               |

|  Memory Runtime              |

|  Relevance Runtime           |

|  Attention / Wake Runtime    |

|  AI Runtime                  |

|  Capability Runtime          |

|  Permission / Safety         |

|  Interaction Runtime         |

|  Evolution Runtime           |

+-----------------------------+

        |

        v

Domain / Capability / UI

```

## 3. AIOS 的核心对象

### World

当前用户现实世界的统一表示。

### Event

世界中发生的一次可记录变化。

### Entity

世界里的长期实体：人、地点、物、组织等。

### Relationship

实体之间的关系及其历史。

### State

某一时刻的世界快照。

### Memory

过去发生过什么；用户人生树的底层事实与语义历史。

### Cognition

AI 对世界的判断、信念、假设和预测。

### Growth

AI 从行为结果中总结的经验和策略变化。

### Capability

AI 可以使用的能力。

### Action

能力真正执行产生的动作。

### Outcome

动作后的现实结果。

## 4. 四个最重要的运行域

### A. Perception Domain

把传感器、手机、外部输入变成 Semantic Event。

### B. World Domain

持续维护 World / Entity / State / Memory。

### C. Cognition Domain

AI 被唤醒后进入世界，读取 World + Cognitive World 并思考。

### D. Action Domain

通过 Capability -> Permission -> Safety -> Execution 改变现实。

## 5. 运行主链

```text

Raw Signal

  -> Semantic Event

  -> Event Fusion

  -> World Update

  -> State Change

  -> Relevance

  -> Attention

  -> Wake / Lease

  -> AI enters World

  -> Think / Judge / Plan

  -> Capability

  -> Permission / Safety

  -> Action

  -> Outcome

  -> Evolution

  -> World Update

```

## 6. 重要边界

Perception 不负责“用户需不需要帮助”。

Event Runtime 不负责“AI应该怎么做”。

World Runtime 不负责复杂判断。

Wake Runtime 不负责理解人生，只负责是否值得消耗认知资源。

AI Runtime 负责理解、推理、判断、规划、反思。

Capability Runtime 负责提供可执行动作。

Permission/Safety 负责是否允许执行。

Interaction Runtime 负责如何把结果呈现给用户。

Evolution Runtime 负责根据结果更新 AI 的长期策略与认知。
