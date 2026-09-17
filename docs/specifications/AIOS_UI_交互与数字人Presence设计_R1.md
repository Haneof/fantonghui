# AIOS UI 交互与数字人 Presence 设计 R1

> 状态：DESIGN PROPOSAL / UI LAYER ONLY  
> 适用分支：`design/ui-presence-r1`  
> 目标基线：`aios-3.0`  
> 约束：本设计不得侵入 AIOS Core 的世界、记忆、认知、证据、任务与存储语义；数字人仅作为 UI / Presence 表现层。

---

## 1. 设计目标

AIOS 现有输出形态以文字、语音、骨传导等为主。本设计新增一个低算力的“人物在场层（Presence Layer）”，使 AIOS 在手表、手机、桌面、AR 等终端上具备连续、稳定、可识别的真人化视觉载体。

该层的目标不是实时生成视频，而是以最小算力实现：

- 固定人物身份连续性；
- 固定真人声线或稳定 TTS 声线；
- 与语音同步的基础口型；
- 眨眼、眼神、点头、轻微身体动作；
- 根据交互场景切换头像、半身、坐姿、工作模式；
- 根据设备能力自动降级；
- 保持 AIOS Core 与 UI 渲染完全解耦。

核心原则：

> AIOS 决定“说什么、为什么说、是否应该说”；UI Presence 层只决定“如何出现、如何表达、在哪个终端呈现”。

---

## 2. 架构边界

推荐数据流：

```text
AIOS Core / AI Worker
    |
    |  response content / intent / context
    v
Communication Adapter
    |
    +--> Text
    +--> TTS / Bone Conduction
    +--> Presence Intent
             |
             v
       UI Presence Director
             |
        +----+----+---------+---------+
        |         |         |         |
      Avatar    Voice      Scene    Gesture
        |         |         |         |
        +---------+----+----+---------+
                       |
                       v
                Device Renderer
          Bracelet / Phone / PC / AR
```

### 2.1 Core 不应负责

AIOS Core 不应存储或执行：

- 逐帧脸部坐标；
- Viseme 帧数据；
- 视频生成任务；
- 衣服贴图；
- 场景资源；
- 表情动画；
- GPU 渲染状态；
- 设备图形接口逻辑。

### 2.2 Core 可提供的上层语义

Core / AI Worker 只需要提供有限的上层语义，例如：

```json
{
  "response_text": "提醒你一下，三点有会议。",
  "interaction_intent": "notify",
  "priority": "normal",
  "tone": "warm_neutral",
  "requires_attention": true
}
```

Presence 层再将其映射为具体 UI 状态。

---

## 3. Presence Mode

R1 建议只定义三种主模式，避免 UI 状态无限膨胀。

### 3.1 GLANCE — 短时通知

适用：

- 手表 / 手镯提醒；
- 日程通知；
- 新消息；
- 简短风险提示；
- 简短确认。

典型交互：

1. 手镯轻振；
2. 用户抬腕；
3. 表盘出现视觉扰动或“窗口缝隙”；
4. 原表盘 UI 被局部拉开 / 推开；
5. 数字人头部或头肩从窗口后出现；
6. 播放 1~10 秒简短语音；
7. 根据需要询问一个短确认；
8. 数字人退回，窗口合拢，恢复原表盘。

设计要求：

- 人物区域尽量小；
- 不做整帧实时生成；
- 入场 / 退场全部预制；
- 口型使用有限 Viseme；
- 允许仅头部 + 眼神 + 嘴部动画。

### 3.2 COMPANION — 普通交流 / 陪伴

适用：

- 日常聊天；
- 谈心；
- 陪伴式交流；
- 轻量建议；
- 非高信息密度问答。

推荐画面：

- 坐姿半身或 3/4 身；
- 固定身份；
- 固定或少量可切换场景；
- 少量衣服资产；
- 轻量 idle 动画；
- 口型、眨眼、眼神、点头、轻微姿态变化。

原则：

> 用户应感觉是在和“同一个人”长期交互，而不是每次生成一个新人物。

### 3.3 FOCUS — 工作 / 高信息密度模式

适用：

- 项目分析；
- 数据解释；
- 文档阅读；
- 决策辅助；
- 复杂事实问答。

人物在该模式下不应占据主要屏幕空间。

推荐布局：

```text
+------------------------------------------------+
| Avatar / Presence |       Main Workspace       |
|                   |   text / chart / files     |
|                   |   evidence / tasks         |
+------------------------------------------------+
```

人物退居侧面，信息面板成为主角。

---

## 4. 手镯 / 手表交互规范

### 4.1 注意力触发

建议状态机：

```text
IDLE
  |
  | event requires attention
  v
HAPTIC_NOTIFY
  |
  | wrist_raise / tap
  v
WINDOW_OPEN
  |
  v
AVATAR_GLANCE
  |
  +--> user responds --> SHORT_DIALOG
  |
  +--> timeout -------> WINDOW_CLOSE
  v
IDLE
```

### 4.2 “拉开窗口”概念

表盘不应直接硬切成一张人脸。

建议视觉语义：

> AIOS 并不是替代表盘，而是暂时“从系统界面后面出现”。

可使用以下方式之一：

- 表盘沿对角线被拉开；
- UI 卡片向两侧滑开；
- 一个局部窗口像门一样打开；
- 数字人从圆形 / 方形窗口内探出；
- 通知结束后动画反向闭合。

这样可以建立 AIOS 的“在场感”，而不会破坏设备原本 UI 身份。

---

## 5. 低算力数字人实现

### 5.1 不采用实时整帧视频生成

R1 明确不推荐：

```text
Text -> TTS -> Video Diffusion / Full-frame Face Generation -> 1080p Video
```

原因：

- GPU 成本高；
- 延迟高；
- 并发差；
- 身份一致性难；
- 小屏设备收益极低。

### 5.2 推荐方案

```text
Text
  |
  v
TTS
  |
  +--> audio
  |
  +--> phoneme / viseme timeline
               |
               v
        Local Avatar Renderer
               |
        prebuilt assets + blend
```

运行时只动态改变：

1. 语音；
2. Viseme / 嘴型；
3. 少量行为状态。

其余均尽量使用本地预制资产。

### 5.3 Viseme

建议约 15~25 个主口型，例如：

- REST
- A
- E
- I
- O
- U
- M/B/P
- F/V
- L
- S/Z
- SH/CH
- R
- W/Q
- TH
- SMILE

可根据最终语言体系扩展，但不要按“每个字 / 每句话”录制。

### 5.4 过渡素材

为了减少机械感，可为常用嘴型准备 micro-transition：

- REST -> A
- A -> O
- O -> M
- M -> A
- A -> REST
- smile -> speech
- speech -> smile

必要时使用轻量 Landmark Warp 做小幅几何校正，而不是重新生成整张脸。

---

## 6. 人物身份连续性

AIOS 数字人应该有固定、长期稳定的视觉身份。

建议固定：

- 面部身份；
- 基础发型体系；
- 声线；
- 身高与身体比例；
- 基础表情习惯；
- 常用动作风格；
- 眨眼与眼神节奏；
- 主色调与 UI 风格。

可变化：

- 衣服；
- 场景；
- 光照；
- 姿势；
- 表情强度；
- 手势。

身份连续性优先级高于生成丰富度。

---

## 7. 场景与服装

场景 / 衣服切换由 UI Presence Director 根据上下文映射，不允许 LLM 直接逐帧控制。

推荐有限枚举：

```text
scene:
- glance_window
- day_room
- evening_room
- studio
- focus_workspace
- travel_context

wardrobe:
- daily_01
- casual_01
- casual_02
- formal_01
- outdoor_01
```

示例映射：

```text
短通知              -> glance_window + head_only
日常闲聊            -> day_room + daily_01
夜间谈心            -> evening_room + casual_01
正式工作讨论        -> studio/focus_workspace + formal_01
旅行相关长对话      -> travel_context + outdoor_01
```

R1 中应优先保证稳定，不追求大量随机组合。

---

## 8. Gesture / 非语言行为

LLM 不直接生成每帧骨骼数据，只输出高层行为意图。

例如：

```json
{
  "gesture": "explain_01",
  "expression": "gentle_smile",
  "pose": "sit_idle_03"
}
```

建议基础动作库：

- idle_01 / idle_02 / idle_03
- listen
- think
- nod
- smile
- explain_01
- explain_02
- emphasis
- lean_forward
- look_away_soft
- return_gaze
- open_window
- close_window

情绪表达不等于修改 AIOS 的认知状态，只是 UI 表现。

---

## 9. 非语言时序

Presence 层应支持少量“沉默动作”，提升自然感。

例如用户表达负面体验后：

```text
user finishes
  -> pause 0.5~1.0s
  -> gaze_soft
  -> lean_forward_01
  -> speak
```

这些行为应由有限状态机执行，不依赖实时视频生成。

---

## 10. 多设备表现

同一个 AIOS 身份可以存在于多个终端，但表现形式不同。

### Bracelet / Watch

- head / shoulder only
- 1~10 秒交互
- 强调触觉 + 语音
- 最低算力

### Phone

- 半身 / 3/4 身
- 可进入 Companion
- 可展示卡片和上下文

### Desktop

- Companion + Focus
- 人物可放在侧边栏或独立窗口
- 工作内容优先

### AR Glasses

- 可使用浮动头像或小比例人物
- 禁止长期遮挡主视野
- UI 事件必须可快速隐藏

### Future Robot

- AIOS 身份与记忆保持不变
- Robot body 只是另一种 Renderer / Embodiment

---

## 11. 计算与网络原则

服务器建议输出：

```json
{
  "audio": "...",
  "viseme_track": [],
  "presence": {
    "mode": "companion",
    "scene": "evening_room",
    "wardrobe": "casual_01",
    "pose": "sit_idle_02",
    "gesture": "nod",
    "expression": "warm_neutral"
  }
}
```

客户端完成：

- 嘴部合成；
- 眼神；
- 眨眼；
- 身体 idle；
- 手势播放；
- 场景渲染；
- 窗口入场 / 退场。

原则：

> 网络传递语义与动画状态，不传输为每个用户实时生成的完整人物视频流。

---

## 12. 降级策略

Presence 层必须支持 graceful degradation。

建议等级：

```text
L0  Text only
L1  Text + TTS
L2  Text + TTS + static portrait
L3  TTS + Viseme + blink
L4  TTS + Viseme + gesture + scene
L5  Full local presence experience
```

触发条件包括：

- 低电量；
- 高温；
- 网络较差；
- GPU / NPU 不可用；
- 后台状态；
- 用户关闭数字人；
- 无障碍模式。

---

## 13. 用户控制与隐私

用户必须能够：

- 关闭数字人；
- 关闭语音；
- 仅保留骨传导；
- 仅保留文字；
- 调整主动提醒强度；
- 禁用自动场景 / 衣服切换；
- 禁用摄像头感知；
- 选择人物风格或无人物模式。

Presence 层不得把“用户喜欢某种人物外观”自动提升为 Core 的事实判断或人格推理依据。

---

## 14. R1 MVP

第一版只实现：

1. 一个固定人物身份；
2. 一个固定声线；
3. GLANCE / COMPANION / FOCUS 三模式；
4. 一个手表“窗口拉开”交互；
5. 一个 Companion 坐姿场景；
6. 一个 Focus 侧边人物布局；
7. 15~25 个 Viseme；
8. 8~12 个基础动作；
9. 3~5 个表情状态；
10. 本地渲染与 L0~L4 降级；
11. UI Presence Director 有限状态机；
12. Core 不新增任何数字人渲染职责。

---

## 15. 非目标

R1 不做：

- 每次对话重新生成完整人物；
- 实时整帧 AI 视频；
- 无限服装 / 无限场景；
- LLM 逐帧控制动作；
- 将视觉人物身份写入 Core 认知语义；
- 用数字人替代复杂信息面板；
- 为了“拟人”强制所有回答都出现人物。

---

## 16. 验收标准

R1 UI Presence MVP 至少满足：

- AIOS Core 无新增渲染依赖；
- GLANCE 通知可独立运行；
- 表盘可完成 open -> avatar -> close 完整交互；
- TTS 与 Viseme 可同步；
- Companion 坐姿可持续运行而无需实时视频生成；
- Focus 模式下人物不遮挡主要信息；
- 设备可在低算力状态降级到静态头像 / 语音 / 文字；
- 同一人物在不同设备保持身份连续性；
- 视觉层故障不会影响 AIOS Core 的认知与任务执行。

---

## 17. 结论

AIOS 数字人应被视为 UI 中的 Presence / Embodiment 表现能力，而不是 Core 认知能力。

最终目标不是“生成一个会说话的视频”，而是让 AIOS 在不同终端上拥有一个连续、低成本、可识别、可降级的外在存在形式。

推荐技术路线：

> 固定人物身份 + 本地预制资产 + TTS + Viseme + 有限状态动作 + 多设备 Renderer。

该路线优先保证身份连续性、低延迟、低算力和大规模并发，而不是追求每一帧都由生成模型实时合成。