# 三棵树存储 Schema · V0.1（接口契约唯一权威源）

> 宪法原则二的物理落地：三库分文件、唯一写者、跨树只许 ID 引用。

## 隔离铁律

1. `life_tree.db`（写者 memoryd）/ `cognitive_tree.db`（写者 cognitiond）/ `growth_tree.db`（写者 evolutiond）三个独立 SQLite 文件
2. 任何服务不得跨库直写；跨树引用只允许 ID（不复制内容）
3. 每条认知记录强制 `confidence + evidence[] + status`
4. 下游消费必须连带置信度；INFERRED 当 KNOWN 用 → decisiond 校验拒绝（系统级 bug）

## 人生树（life_tree.db）

```sql
-- 原始日志归档（append-only，只增不改；修正=追加更正条目）
CREATE TABLE raw_log (
  id            TEXT PRIMARY KEY,   -- = Event.id
  timestamp_s   INTEGER NOT NULL,   -- 秒级时间戳
  source        TEXT NOT NULL,
  type          TEXT NOT NULL,
  content       TEXT NOT NULL,      -- 转写文本/描述/数值
  speaker       TEXT,               -- unknown / entity_id / "user-confirmed:xxx"
  entities      TEXT,               -- JSON array
  mode_at_time  TEXT,
  privacy_level INTEGER,
  correction_of TEXT                -- 非空=本条是对某事件的更正（追加式）
);

-- 分层摘要（小时/天/周/月/季/年）
CREATE TABLE summary (
  id          TEXT PRIMARY KEY,
  level       TEXT NOT NULL,        -- HOURLY/DAILY/WEEKLY/MONTHLY/QUARTERLY/YEARLY
  period_start INTEGER NOT NULL,
  period_end   INTEGER NOT NULL,
  content     TEXT NOT NULL,        -- 摘要正文
  key_entities TEXT,                -- JSON array of entity_id
  generated_at INTEGER NOT NULL
);

-- 多维主题树索引（只建索引不复制数据）
CREATE TABLE topic_index (
  topic       TEXT NOT NULL,        -- social/health/finance/interest/work/decision/...
  entity_id   TEXT,
  memory_ids  TEXT NOT NULL,        -- JSON array of raw_log.id
  updated_at  INTEGER NOT NULL
);
```

## 认知树（cognitive_tree.db）

```sql
CREATE TABLE cognition (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,      -- BELIEF / HYPOTHESIS / PREDICTION / UNKNOWN / SPEAKER_BINDING
  conclusion    TEXT NOT NULL,      -- "张总更在意交付而非价格"
  confidence    REAL NOT NULL,      -- 0.0–1.0，强制
  evidence      TEXT NOT NULL,      -- JSON array：人生树 raw_log.id / entity.id 引用链
  counter_evidence TEXT,            -- 反例证据链
  status        TEXT NOT NULL,      -- ACTIVE / REVISED / INVALIDATED / CONFLICT
  last_verified INTEGER,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
-- 说话人绑定推断（SPEAKER_BINDING）也存这里：绑定永远是推断，用户确认后转人生树事实
```

## 成长树（growth_tree.db）

```sql
CREATE TABLE growth (
  id             TEXT PRIMARY KEY,
  situation      TEXT NOT NULL,
  ai_judgment    TEXT NOT NULL,
  ai_action      TEXT,
  user_feedback  TEXT,              -- accepted/ignored/rejected/asked_more
  actual_result  TEXT,
  was_correct    BOOLEAN,
  error_analysis TEXT,
  lesson         TEXT,
  strategy_update TEXT,
  confidence     REAL NOT NULL
);

CREATE TABLE strategy_versions (    -- 策略版本链，可回退（宪法 6.9）
  version_id  TEXT PRIMARY KEY,
  strategy_key TEXT NOT NULL,
  payload     TEXT NOT NULL,        -- JSON
  reason      TEXT,
  created_at  INTEGER NOT NULL,
  active      BOOLEAN NOT NULL
);
```

## 消费规则

| 消费方 | 允许读 | 禁止 |
|---|---|---|
| decisiond | 三树（认知必须带置信度） | 把 INFERRED 当 KNOWN |
| interactd 首夜主动开口 | 已授权源 + 引用粒度校验（privacyd） | 超授权范围引用 |
| 云端 L3 | 脱敏摘要 + 最小充分上下文 | 原始语音/未脱敏内容 |
