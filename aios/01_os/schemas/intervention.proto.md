# 介入通道 Schema · V0.1（interactd 对 03_ui 的契约）

> 五级介入通道 + 最低打扰原则（宪法 6.8 修订案）。

## 五级通道

```protobuf
message Intervention {
  string id       = 1;
  string event_id = 2;   // 触发事件
  Level  level    = 3;   // 介入级别（最低打扰优先，能低不高）
  string payload  = 4;   // 通道负载（文字/振动模式/语音文本）
  ConfirmRule confirm = 5; // 是否需要用户确认（执行类强制）

  enum Level {
    SILENT_WATCH = 0;  // 不介入，只记录
    VISUAL       = 1;  // 静默视觉：屏幕关键词（不打断声音交流）
    HAPTIC       = 2;  // 触觉：振动语义编码
    BONE_CONDUCTION = 3; // 骨传导语音（私密）
    EXECUTE      = 4;  // 受控执行（付款码/导航/拨号，受 ConfirmRule 约束）
  }
}
```

## 通道选择规则（decisiond 决定，interactd 执行）

1. 最低打扰优先：VISUAL 能解决不用 HAPTIC，HAPTIC 能解决不语音
2. SOCIAL 场景默认不语音（打断谈话=社死）；FINANCIAL 执行必须 EXECUTE+二次确认
3. SAFETY 直达最高必要级（可跨级）
4. MODE 约束：睡眠模式下仅 SAFETY 可唤醒

## 振动语义基线（可自定义，用户与 AIOS 形成"触觉语言"）

| 模式 | 含义 |
|---|---|
| 短一下 | 普通信息 |
| 两下 | 有事需要看 |
| 较长/明显 | 着急 |
| 连续强提醒 | 很急 |
| 特殊高频 | 安全事件 |

## 用户反馈（回流 evolutiond）

accepted / ignored / rejected / asked_more —— 快速关闭类反馈提高该类事件阈值（Intervention Regret）。
