# Event Schema · V0.1（接口契约唯一权威源）

> 本文件是 `Event` 的权威定义。02_hardware / 03_ui / 04_apps 引用本定义，不得复制。

## 设计依据

- 宪法 6.1 标准事件格式
- C1 修正案（2026-09-08 负责人确认）：秒级=时间戳精度；无事件不记录；语音转文字；人物绑定异步可修正

## 字段定义

```protobuf
message Event {
  string id            = 1;  // 事件唯一标识（UUIDv7，含时序）
  int64  timestamp_s   = 2;  // 秒级时间戳（事件发生时刻，Unix 秒，含时区信息由设备配置提供）
  Source source        = 3;  // 来源通道
  EventType type       = 4;  // 事件类型
  string content       = 5;  // 语义内容（转写文本/描述/数值 JSON）
  string speaker       = 6;  // 说话人：初始 unknown，异步绑定后为实体 ID 或推断标注
  repeated string entities = 7; // 关联实体 ID（初始可空，绑定后回填）
  float  confidence    = 8;  // 感知置信度 0.0–1.0
  string mode_at_time  = 9;  // 事件发生时 MODE（modemgrd 回填；unknown 合法）
  int32  privacy_level = 10; // 脱敏等级（privacyd 回填；0=仅本地，1=脱敏可上云，2=可原样）
  Status status        = 11; // 处理状态

  enum Source {
    SOURCE_UNKNOWN = 0;
    MIC            = 1;  // 麦克风（VAD 触发的语音转写）
    IMU_SPEAKER    = 2;  // IMU 说话检测（用户自己开口的辅助判定）
    IMU_MOTION     = 3;  // 姿态/运动
    PPG_VITAL      = 4;  // 生理体征
    PHONE_SYNC     = 5;  // 手机器官同步（聊天/日程/消费/通知）
    ABILITY        = 6;  // 能力系统执行结果
    USER           = 7;  // 用户直接操作/召唤
    CAMERA         = 8;  // 摄像头快照（拍照→视觉模型描述→立即删图）
  }

  enum EventType {
    EVENT_UNKNOWN   = 0;
    SPEECH          = 1;  // 一段话（用户/他人/未知，见 speaker）
    ENV_SOUND       = 2;  // 环境声音事件
    MOTION          = 3;  // 抬腕/跌倒/撞击/静止
    VITAL           = 4;  // 体征读数或异常
    PAYMENT         = 5;  // 消费事件
    MESSAGE         = 6;  // 社交消息（手机同步）
    SCHEDULE        = 7;  // 日程事件
    USER_TRIGGER    = 8;  // 用户一级触发（双击等，特权通道）
    SAFETY          = 9;  // 安全事件（反射世界直达）
    SYSTEM          = 10; // 系统自身事件
    VISUAL_SCENE    = 11; // 环境视觉快照（文字描述，图片即删）
  }

  enum Status { PENDING = 0; PROCESSED = 1; ARCHIVED = 2; UNRESOLVED = 3; }
}
```

## 说话人绑定协议（异步，可修正）

```
阶段1（当下）:  speaker = "unknown"，content 已落盘，时间戳不可变
阶段2（推断）:  cognitiond 产出绑定推断 → {speaker: entity_id, confidence: 0.87}
                写入认知树；Event.entities 回填，Event 本体不删改
阶段3（更正）:  用户否认 → 推断降置信/失效；人生树追加更正条目引用原事件 ID
铁律:          说话人身份永远是"推断"除非用户确认；用户确认为事实，写人生树
```

## 摄像头通道协议（拍照 → 描述 → 删图）

- **触发**：事件驱动快照（用户主动拍 / 场景触发），不做持续录像
- **管线**：拍照 → 视觉模型生成文字描述 → 产出 VISUAL_SCENE 事件（content = 描述文本）→ **图片立即删除**
- **图片生命周期**：仅存在于"描述生成"瞬间（raw_data 短暂引用）；任何存储介质不落盘长期图片（宪法 6.4.2：仅保留文字描述）
- **视觉模型路由**：默认本地小视觉模型（粗粒度场景/物体描述）；高价值时刻可请求云端视觉模型，但图片临时上传需用户单独授权，分析完成即删
- **隐私**：描述中涉及他人身份 → 按推断处理（认知树，带置信度），不得写成事实；描述上云过 privacyd 常规审查

## 无事件不记录（C1）

- 传感器静默时段不产生占位事件（没有"01s 无输入"这类记录）
- 时间戳只标注真实发生的事件；沉默时段在时间轴上自然为空
- 生理体征按低频基线采样（分钟级），异常时升级为事件

## 变更规则

本 schema 的任何字段变更 = 接口契约变更，需三目录（OS/硬件/UI/应用）评审。
