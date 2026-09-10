# AIOS AI Runtime V0.1

## 1. 目标

让 AI 不再是“一次 Prompt + 一次回答”，而是一个可以反复进入 AIOS World 的持续存在实例。

## 2. AI Wake Session

每次 AI 被唤醒，不是收到一条孤立事件，而是获得一个 World Access Session。

```text

AI Wake

  ↓

Identity

  ↓

Current World State

  ↓

Relevant World Changes

  ↓

Relevant Memory

  ↓

Cognitive World

  ↓

Growth

  ↓

Goals / Active Watches

  ↓

Think

```

## 3. AI 可见范围

默认看到：

- 当前世界状态

- 与触发变化相关的事件链

- 必要人物和关系

- 相关历史记忆

- 自己的相关认知

- 自己过去相关失败/经验

- 当前目标

不默认读取整个人生原始记录。

## 4. AI 输出类型

```text

THOUGHT

BELIEF_UPDATE

HYPOTHESIS

QUESTION

PREDICTION

DECISION

CAPABILITY_REQUEST

MESSAGE

WATCH_REQUEST

REFLECTION

```

模型输出首先进入系统审核层，再决定写入哪棵树或是否执行。

## 5. AI 与模型的关系

```text

AIOS AI Runtime

      ↓

Model Router

      ↓

GPT / Claude / Gemini / Local / Specialist

```

模型可以更换；AI Identity、Cognition、Growth 不变。

## 6. “AI 进入世界”的最低实现

第一版至少做到：

- AI 有持久 identity id。

- AI 有持久 Cognitive Tree。

- AI 有持久 Growth Tree。

- AI 每次 Wake 都看到当前 World State。

- AI 能引用过去的 Cognition 和 Growth。

- AI 可以产生 Watch。

- AI Action 的 Outcome 可以回到 AI。
